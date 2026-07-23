#!/usr/bin/env python3
"""Extract spawn-to-service metrics from a single run folder.

Computes per-spawn-event metrics for RQ2 v3:
  - TTFT        (time-to-first-traffic)
  - TFR         (time-to-first-response)
  - init_time   (TFR − TTFT, backend initialisation proxy)
  - initial_share (fraction of VIP traffic in first visible window)

Usage:
    python -m source.scripts.testing.analysis.rq2.extract_spawn_metrics \\
        <run_dir> [--mode topology_host] [--out analysis/rq2_spawn_metrics.csv]
"""
from __future__ import annotations

import argparse
import csv
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_ts(ts_str: str) -> float | None:
    """Parse ISO-8601 timestamp to Unix seconds."""
    try:
        return datetime.fromisoformat(ts_str.replace("Z", "+00:00")).timestamp()
    except (ValueError, TypeError):
        return None


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Step 1 — Extract spawn events from controller logs
# ---------------------------------------------------------------------------

def extract_compute_spawns(run_dir: Path) -> list[dict]:
    """Parse controller_lan*.log for compute spawn events.

    Returns list of dicts with keys:
      spawn_ts    — Unix timestamp of the spawn log line
      container   — container name (e.g. edge_server_lan1_dyn2)
      mac         — MAC address
      lan         — "lan1" or "lan2"
    """
    spawns: list[dict] = []
    for lan_label in ("lan1", "lan2"):
        log_path = run_dir / f"controller_{lan_label}.log"
        if not log_path.exists():
            continue
        with open(log_path) as f:
            for line in f:
                # Log format: [elasticity] compute: spawning <name> on LAN <n> (ip=... mac=...)
                if "spawning" not in line or "compute:" not in line:
                    continue
                parts = line.split(" ")
                if len(parts) < 3:
                    continue
                iso_ts = parts[0] + "T" + parts[1].split(",")[0]
                unix_ts = _parse_ts(iso_ts)
                if unix_ts is None:
                    continue

                # Container name: between "spawning" and "on"
                container_match = re.search(r"spawning\s+(\S+)\s+on", line)
                container = container_match.group(1) if container_match else None

                # MAC: mac=00:00:00:00:02:09
                mac_match = re.search(r"mac=([0-9a-f:]+)", line)
                mac = mac_match.group(1) if mac_match else None

                if unix_ts and container:
                    spawns.append({
                        "spawn_ts": unix_ts,
                        "container": container,
                        "mac": mac,
                        "lan": lan_label,
                    })
    return spawns


# ---------------------------------------------------------------------------
# Step 2 — Compute TTFT from per_node_stats.csv
# ---------------------------------------------------------------------------

def compute_ttft(spawns: list[dict], run_dir: Path) -> dict[int, float | None]:
    """Match each spawn to its first telemetry window with request_count > 0.

    Returns dict mapping spawn index → TTFT in seconds, or None if unmatched.
    """
    pns_path = run_dir / "per_node_stats.csv"
    if not pns_path.exists():
        return {i: None for i in range(len(spawns))}

    # Build: mac → first_window_end (Unix seconds)
    first_window: dict[str, float] = {}
    with open(pns_path) as f:
        for row in csv.DictReader(f):
            mac = row.get("server_id", "").strip()
            rc = int(row.get("request_count", 0))
            we = _safe_float(row.get("window_end"))
            if mac and rc > 0 and mac not in first_window and we > 0:
                first_window[mac] = we

    ttft: dict[int, float | None] = {}
    for i, sp in enumerate(spawns):
        mac = sp["mac"]
        if mac and mac in first_window:
            ttft_val = first_window[mac] - sp["spawn_ts"]
            if 0 <= ttft_val <= 600:
                ttft[i] = ttft_val
            else:
                ttft[i] = None
        else:
            ttft[i] = None
    return ttft


# ---------------------------------------------------------------------------
# Step 3 — Compute TFR from client_requests.csv
# ---------------------------------------------------------------------------

def compute_tfr(spawns: list[dict], run_dir: Path) -> dict[int, float | None]:
    """Match each spawn to its first HTTP response via the backend_id column.

    Returns dict mapping spawn index → TFR in seconds, or None if unmatched.
    """
    cr_path = run_dir / "client_requests.csv"
    if not cr_path.exists():
        return {i: None for i in range(len(spawns))}

    # Read all rows, grouping completed_at by backend_id
    backend_timestamps: dict[str, list[float]] = defaultdict(list)
    with open(cr_path) as f:
        reader = csv.DictReader(f)
        if "backend_id" not in (reader.fieldnames or []):
            print(f"  [WARN] client_requests.csv has no 'backend_id' column — TFR unavailable")
            return {i: None for i in range(len(spawns))}
        for row in reader:
            bid = row.get("backend_id", "").strip()
            completed = _parse_ts(row.get("completed_at", ""))
            if bid and completed is not None and completed > 0:
                backend_timestamps[bid].append(completed)

    tfr: dict[int, float | None] = {}
    for i, sp in enumerate(spawns):
        container = sp["container"]
        if container and container in backend_timestamps:
            # First response after spawn
            candidates = [ts for ts in backend_timestamps[container]
                          if ts >= sp["spawn_ts"]]
            if candidates:
                tfr_val = min(candidates) - sp["spawn_ts"]
                tfr[i] = tfr_val if 0 <= tfr_val <= 600 else None
            else:
                tfr[i] = None
        else:
            tfr[i] = None
    return tfr


# ---------------------------------------------------------------------------
# Step 4 — Initial load share (from per_node_stats first window)
# ---------------------------------------------------------------------------

def compute_initial_share(spawns: list[dict], run_dir: Path) -> dict[int, float | None]:
    """Compute the fraction of VIP traffic captured by the new backend in its
    first visible telemetry window.

    Uses per_node_stats.csv: for the first window where request_count > 0 for
    the spawn MAC, compute request_count / total_requests_in_that_window
    (summed across all backends reporting in the same window).
    """
    pns_path = run_dir / "per_node_stats.csv"
    if not pns_path.exists():
        return {i: None for i in range(len(spawns))}

    # First pass: build window_totals and per-MAC first-window data
    window_totals: dict[float, int] = {}
    first_window_data: dict[str, tuple[float, int]] = {}  # mac → (window_end, request_count)
    with open(pns_path) as f:
        for row in csv.DictReader(f):
            mac = row.get("server_id", "").strip()
            rc = int(row.get("request_count", 0))
            we = _safe_float(row.get("window_end"))
            if not mac or we <= 0:
                continue
            window_totals[we] = window_totals.get(we, 0) + rc
            if rc > 0 and mac not in first_window_data:
                first_window_data[mac] = (we, rc)

    init_share: dict[int, float | None] = {}
    for i, sp in enumerate(spawns):
        mac = sp["mac"]
        if mac and mac in first_window_data:
            we, rc = first_window_data[mac]
            total = window_totals.get(we, 0)
            init_share[i] = rc / total if total > 0 else None
        else:
            init_share[i] = None
    return init_share


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Extract RQ2 spawn metrics from a run folder")
    parser.add_argument("run_dir", type=Path, help="Path to run folder")
    parser.add_argument("--mode", default="unknown", help="Routing mode label")
    parser.add_argument("--out", type=Path, default=None,
                        help="Output CSV path (default: <run_dir>/analysis/rq2_spawn_metrics.csv)")
    args = parser.parse_args()

    run_dir = args.run_dir
    if not run_dir.is_dir():
        print(f"ERROR: {run_dir} is not a directory")
        return 1

    print(f"Extracting spawn metrics from {run_dir.name}")

    spawns = extract_compute_spawns(run_dir)
    print(f"  Compute spawn events: {len(spawns)}")
    if not spawns:
        print("  No compute spawns found — nothing to do.")
        return 0

    ttft = compute_ttft(spawns, run_dir)
    tfr = compute_tfr(spawns, run_dir)
    init_share = compute_initial_share(spawns, run_dir)

    # Assemble rows
    rows: list[dict] = []
    n_ttft = n_tfr = 0
    for i, sp in enumerate(spawns):
        ttft_val = ttft.get(i)
        tfr_val = tfr.get(i)
        init_val = init_share.get(i)
        if ttft_val is not None:
            n_ttft += 1
        if tfr_val is not None:
            n_tfr += 1
        rows.append({
            "spawn_ts": sp["spawn_ts"],
            "container": sp["container"],
            "mac": sp.get("mac", ""),
            "lan": sp["lan"],
            "mode": args.mode,
            "ttft_s": f"{ttft_val:.1f}" if ttft_val is not None else "",
            "tfr_s": f"{tfr_val:.1f}" if tfr_val is not None else "",
            "init_time_s": f"{(tfr_val - ttft_val):.1f}" if (ttft_val is not None and tfr_val is not None) else "",
            "initial_share": f"{init_val:.4f}" if init_val is not None else "",
        })

    print(f"  TTFT matched:  {n_ttft}/{len(spawns)}")
    print(f"  TFR matched:   {n_tfr}/{len(spawns)}")

    # Write output
    out_path = args.out or (run_dir / "analysis" / "rq2_spawn_metrics.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["spawn_ts", "container", "mac", "lan", "mode",
                  "ttft_s", "tfr_s", "init_time_s", "initial_share"]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  Wrote {len(rows)} rows → {out_path}")

    # Quick summary
    for metric_name, col in [("TTFT", "ttft_s"), ("TFR", "tfr_s"),
                              ("Init Time", "init_time_s"),
                              ("Initial Share", "initial_share")]:
        vals = [float(r[col]) for r in rows if r[col]]
        if vals:
            print(f"  {metric_name}: n={len(vals)}  "
                  f"median={np.median(vals):.1f}  "
                  f"mean={np.mean(vals):.1f}  "
                  f"p95={np.percentile(vals, 95):.1f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
