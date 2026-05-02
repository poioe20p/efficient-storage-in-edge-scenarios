#!/usr/bin/env python3
"""
parse_elasticity_logs.py — Extract elasticity scaling events from SDN controller logs.

Reads controller log files (captured via ``docker logs``) and outputs a CSV
with one row per scaling event, suitable for correlation with resource_stats.csv.

Usage:
    python parse_elasticity_logs.py controller_lan1.log controller_lan2.log -o elasticity_events.csv
    python parse_elasticity_logs.py controller_lan1.log --controller-names lan1 -o events.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Timestamp regex — matches the logging.conf format: "2026-04-11 19:48:13,456"
# ---------------------------------------------------------------------------

_TS = r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3})"

# ---------------------------------------------------------------------------
# Event patterns — each tuple: (compiled regex, event builder function)
#
# Builder signature: (match, controller) -> dict with keys:
#   timestamp, controller, event_type, node_type, container, mac, ip, detail
# ---------------------------------------------------------------------------

PATTERNS: list[tuple[re.Pattern, callable]] = []


def _maybe_float(value: str):
    value = value.strip().lower()
    if value in {"n/a", "none", "null"}:
        return None
    return float(value)


def _pat(pattern: str):
    """Decorator that registers a regex pattern and its builder."""
    compiled = re.compile(pattern)

    def decorator(fn):
        PATTERNS.append((compiled, fn))
        return fn

    return decorator


def _row(ts, controller, event_type, node_type="", container="", mac="", ip="", detail=None):
    return {
        "timestamp": ts,
        "controller": controller,
        "event_type": event_type,
        "node_type": node_type,
        "container": container,
        "mac": mac,
        "ip": ip,
        "detail": json.dumps(detail) if detail else "",
    }


# --- Scale-up triggers ---

@_pat(_TS + r" (?:INFO|DEBUG) .+\[scale-up\] storage triggered: (\d+)/(\d+) windows ≥ ([\d.]+) "
      r"\(eff_τ=([\d.]+), dyn_nodes=(\d+), last score=([\d.]+), cpu_s=([\d.]+)%, T_db=([\d.]+)ms\) on (\S+)")
def _scaleup_storage_triggered(m, ctrl):
    return _row(m.group(1), ctrl, "scale_up_triggered", "storage", detail={
        "windows_hit": int(m.group(2)), "windows_total": int(m.group(3)),
        "threshold": float(m.group(4)), "effective_threshold": float(m.group(5)),
        "dyn_nodes": int(m.group(6)), "score": float(m.group(7)),
        "cpu_pct": float(m.group(8)), "t_db_ms": float(m.group(9)),
        "network": m.group(10),
    })


@_pat(_TS + r" (?:INFO|DEBUG) .+\[scale-up\] compute triggered: (\d+)/(\d+) windows ≥ ([\d.]+) "
      r"\(τ_eff=([\d.]+), τ_base=([\d.]+), peer_relief=([\d.]+), peer_score=([^,]+), dyn=(\d+), last score=([\d.]+), cpu=([\d.]+)%, T_proc=([\d.]+)ms\) on (\S+)")
def _scaleup_compute_triggered_peer_aware(m, ctrl):
    return _row(m.group(1), ctrl, "scale_up_triggered", "compute", detail={
        "windows_hit": int(m.group(2)), "windows_total": int(m.group(3)),
        "threshold": float(m.group(4)), "effective_threshold": float(m.group(5)),
        "base_threshold": float(m.group(6)), "peer_relief": float(m.group(7)),
        "peer_score": _maybe_float(m.group(8)), "dyn_nodes": int(m.group(9)),
        "score": float(m.group(10)), "cpu_pct": float(m.group(11)),
        "t_proc_ms": float(m.group(12)), "network": m.group(13),
    })


@_pat(_TS + r" (?:INFO|DEBUG) .+\[scale-up\] compute triggered: (\d+)/(\d+) windows ≥ ([\d.]+) "
      r"\(last score=([\d.]+), cpu=([\d.]+)%, T_proc=([\d.]+)ms\) on (\S+)")
def _scaleup_compute_triggered(m, ctrl):
    return _row(m.group(1), ctrl, "scale_up_triggered", "compute", detail={
        "windows_hit": int(m.group(2)), "windows_total": int(m.group(3)),
        "threshold": float(m.group(4)), "score": float(m.group(5)),
        "cpu_pct": float(m.group(6)), "t_proc_ms": float(m.group(7)),
        "network": m.group(8),
    })


# --- Scale-up score (window entry, not yet triggered) ---

@_pat(_TS + r" (?:INFO|DEBUG) .+\[scale-up\] storage score=([\d.]+) \(τ_eff=([\d.]+), base=([\d.]+) \+(\d+)×([\d.]+)\) "
      r"cpu_s=([\d.]+)% T_db=([\d.]+)ms  window=(\d+)/(\d+) on (\S+)")
def _scaleup_storage_score(m, ctrl):
    return _row(m.group(1), ctrl, "scale_up_score", "storage", detail={
        "score": float(m.group(2)), "effective_threshold": float(m.group(3)),
        "base_threshold": float(m.group(4)), "dyn_nodes": int(m.group(5)),
        "threshold_increment": float(m.group(6)),
        "cpu_pct": float(m.group(7)), "t_db_ms": float(m.group(8)),
        "window_pos": int(m.group(9)), "window_total": int(m.group(10)),
        "network": m.group(11),
    })


@_pat(_TS + r" (?:INFO|DEBUG) .+\[scale-up\] compute score=([\d.]+) "
      r"\(τ_eff=([\d.]+), τ_base=([\d.]+), peer_relief=([\d.]+), peer_score=([^,]+), dyn=(\d+)\) "
      r"cpu=([\d.]+)% T_proc=([\d.]+)ms window=(\d+)/(\d+) on (\S+)")
def _scaleup_compute_score_peer_aware(m, ctrl):
    return _row(m.group(1), ctrl, "scale_up_score", "compute", detail={
        "score": float(m.group(2)), "effective_threshold": float(m.group(3)),
        "base_threshold": float(m.group(4)), "peer_relief": float(m.group(5)),
        "peer_score": _maybe_float(m.group(6)), "dyn_nodes": int(m.group(7)),
        "cpu_pct": float(m.group(8)), "t_proc_ms": float(m.group(9)),
        "window_pos": int(m.group(10)), "window_total": int(m.group(11)),
        "network": m.group(12),
    })


@_pat(_TS + r" (?:INFO|DEBUG) .+\[scale-up\] compute score=([\d.]+) \(τ=([\d.]+)\) "
      r"cpu=([\d.]+)% T_proc=([\d.]+)ms  window=(\d+)/(\d+) on (\S+)")
def _scaleup_compute_score(m, ctrl):
    return _row(m.group(1), ctrl, "scale_up_score", "compute", detail={
        "score": float(m.group(2)), "threshold": float(m.group(3)),
        "cpu_pct": float(m.group(4)), "t_proc_ms": float(m.group(5)),
        "window_pos": int(m.group(6)), "window_total": int(m.group(7)),
        "network": m.group(8),
    })


# --- Spawning ---

@_pat(_TS + r" INFO .+\[elasticity\] compute: spawning (\S+) on LAN (\d+)")
def _spawning_compute(m, ctrl):
    return _row(m.group(1), ctrl, "node_spawning", "compute",
                container=m.group(2), detail={"lan": int(m.group(3))})


@_pat(_TS + r" INFO .+\[elasticity\] data: spawning (\S+) on LAN (\d+)")
def _spawning_data(m, ctrl):
    return _row(m.group(1), ctrl, "node_spawning", "storage",
                container=m.group(2), detail={"lan": int(m.group(3))})


# --- Online ---

@_pat(_TS + r" INFO .+\[elasticity\] compute: (\S+) online  ip=(\S+)  mac=(\S+)")
def _online_compute(m, ctrl):
    return _row(m.group(1), ctrl, "node_online", "compute",
                container=m.group(2), ip=m.group(3), mac=m.group(4))


@_pat(_TS + r" INFO .+\[elasticity\] data: (\S+) online  ip=(\S+)  mac=(\S+)")
def _online_data(m, ctrl):
    return _row(m.group(1), ctrl, "node_online", "storage",
                container=m.group(2), ip=m.group(3), mac=m.group(4))


# --- Node add timing ---

@_pat(_TS + r" INFO .+\[node_add\] timing  container=(\S+)  docker_run=([\d.]+)s"
      r"  net_attach=([\d.]+)s  rs_join=([\d.]+)s  total=([\d.]+)s  state=(\S+)")
def _node_add_timing(m, ctrl):
    return _row(m.group(1), ctrl, "node_add_timing", container=m.group(2), detail={
        "docker_run_s": float(m.group(3)), "net_attach_s": float(m.group(4)),
        "rs_join_s": float(m.group(5)), "total_s": float(m.group(6)),
        "state": m.group(7),
    })


# --- Scale-down triggers ---

@_pat(_TS + r" INFO .+\[scale-down\] compute underutilisation: (\d+)/(\d+) "
      r"windows below threshold — removing (\S+)")
def _scaledown_compute(m, ctrl):
    return _row(m.group(1), ctrl, "scale_down_triggered", "compute",
                container=m.group(4), detail={
                    "windows_hit": int(m.group(2)), "windows_total": int(m.group(3)),
                })


@_pat(_TS + r" INFO .+\[scale-down\] storage underutilisation: (\d+)/(\d+) "
      r"windows below threshold — removing (\S+)")
def _scaledown_storage(m, ctrl):
    return _row(m.group(1), ctrl, "scale_down_triggered", "storage",
                container=m.group(4), detail={
                    "windows_hit": int(m.group(2)), "windows_total": int(m.group(3)),
                })


# --- Scale-down: removing ---

@_pat(_TS + r" INFO .+\[elasticity\] scale_down_compute: removing (\S+) \(mac=(\S+)\)")
def _removing_compute(m, ctrl):
    return _row(m.group(1), ctrl, "node_removing", "compute",
                container=m.group(2), mac=m.group(3))


@_pat(_TS + r" INFO .+\[elasticity\] scale_down_data: removing (\S+) \(mac=(\S+)\)")
def _removing_data(m, ctrl):
    return _row(m.group(1), ctrl, "node_removing", "storage",
                container=m.group(2), mac=m.group(3))


# --- Drain complete ---

@_pat(_TS + r" INFO .+\[scale-down\] drain_complete received for mac=(\S+)")
def _drain_complete(m, ctrl):
    return _row(m.group(1), ctrl, "drain_complete", mac=m.group(2))


# --- Cleanup done ---

@_pat(_TS + r" INFO .+\[elasticity\] cleanup_compute done: container=(\S+)")
def _cleanup_compute_done(m, ctrl):
    return _row(m.group(1), ctrl, "cleanup_done", "compute", container=m.group(2))


@_pat(_TS + r" INFO .+\[elasticity\] scale_down_data done: container=(\S+)")
def _cleanup_data_done(m, ctrl):
    return _row(m.group(1), ctrl, "cleanup_done", "storage", container=m.group(2))


# --- Node remove timing ---

@_pat(_TS + r" INFO .+\[node_remove\] timing  container=(\S+)  drain_signal=([\d.]+)s"
      r"  net_cleanup=([\d.]+)s  total=([\d.]+)s  state=(\S+)")
def _node_remove_timing(m, ctrl):
    return _row(m.group(1), ctrl, "node_remove_timing", container=m.group(2), detail={
        "drain_signal_s": float(m.group(3)), "net_cleanup_s": float(m.group(4)),
        "total_s": float(m.group(5)), "state": m.group(6),
    })


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

def parse_log(path: Path, controller: str) -> list[dict]:
    events = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            for regex, builder in PATTERNS:
                m = regex.search(line)
                if m:
                    events.append(builder(m, controller))
                    break
    return events


def infer_controller_name(path: Path) -> str:
    name = path.stem.lower()
    if "lan1" in name or "osken_1" in name or name == "osken":
        return "lan1"
    if "lan2" in name or "osken_2" in name:
        return "lan2"
    return name


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

CSV_COLUMNS = ["timestamp", "controller", "event_type", "node_type",
               "container", "mac", "ip", "detail"]


def main():
    parser = argparse.ArgumentParser(
        description="Parse SDN controller logs into elasticity_events.csv")
    parser.add_argument("logs", nargs="+", type=Path, help="Controller log file(s)")
    parser.add_argument("-o", "--output", type=Path, default=Path("elasticity_events.csv"),
                        help="Output CSV path (default: elasticity_events.csv)")
    parser.add_argument("--controller-names", nargs="*",
                        help="Controller name for each log file (inferred from filename if omitted)")
    args = parser.parse_args()

    if args.controller_names and len(args.controller_names) != len(args.logs):
        print("ERROR: --controller-names count must match number of log files", file=sys.stderr)
        sys.exit(1)

    all_events: list[dict] = []
    for i, log_path in enumerate(args.logs):
        if not log_path.exists():
            print(f"WARNING: {log_path} not found — skipping", file=sys.stderr)
            continue
        ctrl = args.controller_names[i] if args.controller_names else infer_controller_name(log_path)
        events = parse_log(log_path, ctrl)
        all_events.extend(events)
        print(f"  {log_path}: {len(events)} events (controller={ctrl})", file=sys.stderr)

    all_events.sort(key=lambda e: e["timestamp"])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(all_events)

    print(f"Wrote {len(all_events)} events → {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
