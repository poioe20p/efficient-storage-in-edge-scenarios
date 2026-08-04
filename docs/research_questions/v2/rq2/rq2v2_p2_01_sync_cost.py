#!/usr/bin/env python3
"""rq2v2_p2_01_sync_cost.py — RQ2 v2 replica-sync action cost per storage member.

Measures the MongoDB initial-sync cost paid when a storage member is added to
the replica set during an RQ2 run. Evidence sources (plan Phase 2.1):

- ``service_logs/edge_storage_*.log`` (``docker logs --timestamps`` + MongoDB
  7.0 structured log): the ``STARTUP2`` state transition (initial sync start),
  the ``SECONDARY`` transition (initial sync complete), and the
  ``initial sync done`` message carrying ``bytesToCopy``; the sidecar's
  ``rs_secondary_ready`` marker is used as a fallback for SECONDARY.
- ``container_events.csv``: the ``added`` observation for the member (fallback
  for the sync-start timestamp).
- ``resource_stats*.csv`` / ``per_node_stats.csv``: storage CPU during the
  sync window (per-member from ``per_node_stats.csv`` when the member is
  identified, else LAN-wide from ``resource_stats.csv`` /
  ``resource_stats_debug.csv``).

Output columns (``sync_cost.csv``, timestamps are epoch seconds on the same
wall-clock timebase as ``decision_log_lan{1,2}.csv`` ``ts``):

- ``member_id``: storage container name (one replica-set member per container).
- ``add_ts``: sync start — first STARTUP2 transition, else ``added`` event.
- ``first_secondary_ts``: first SECONDARY transition, else ``rs_secondary_ready``.
- ``sync_duration_s`` = ``first_secondary_ts - add_ts`` (null when incomplete).
- ``bytes_applied``: ``bytesToCopy`` from the ``initial sync done`` message
  (null when unobtainable — sync duration + storage CPU are the primary
  metrics).
- ``storage_cpu_during_sync_pct``: mean storage CPU across resource-stats
  windows whose ``window_end`` falls inside the sync window.
- ``source``: which evidence produced the timestamps (e.g. ``startup2+secondary``,
  ``added+rs_secondary_ready``).

Robustness: a cell that adds no storage produces a header-only ``sync_cost.csv``
and a printed notice — the tool never fails on missing evidence.

Run-kind guard: only RQ2-arm runs are processed (matches the sibling RQ2
analyzers).

Usage:
    python3 docs/research_questions/v2/rq2/rq2v2_p2_01_sync_cost.py RUN_DIR [--output FILE]
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from datetime import datetime, timezone

_RQ2_ARMS = {"fixed_compute_first", "fixed_storage_first", "bottleneck_aware"}

_TS_RE = re.compile(
    r"^\s*(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?"
    r"(Z|[+-]\d{2}:?\d{2})?"
)

_SYNC_DONE_RE = re.compile(r'"bytesToCopy"\s*:\s*(\d+)')
_SYNC_DONE_RE_ALT = re.compile(r'"bytesApplied"\s*:\s*(\d+)')


def _parse_env(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def _as_float(v, default: float | None = None) -> float | None:
    if v is None:
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _fmt(v, nd: int = 3) -> str:
    """Format a float or None for CSV output (empty string for None)."""
    if v is None:
        return ""
    return f"{v:.{nd}f}"


def _epoch_from_iso(s) -> float | None:
    """Parse an ISO-8601 wall-clock timestamp (UTC) into epoch seconds.

    Tolerates docker-log RFC3339Nano timestamps (any fractional precision,
    ``Z`` or ``+hh:mm`` offset) and plain float strings (already epoch).
    """
    if s is None:
        return None
    s = str(s).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        pass
    m = _TS_RE.match(s)
    if not m:
        return None
    y, mo, d, h, mi, sec = (int(g) for g in m.groups()[:6])
    frac = m.group(7) or ""
    tz = m.group(8) or ""
    frac_sec = float("0." + frac) if frac else 0.0
    dt = datetime(y, mo, d, h, mi, sec, tzinfo=timezone.utc)
    epoch = dt.timestamp() + frac_sec
    if tz and tz != "Z":
        sign = 1 if tz[0] == "+" else -1
        hhmm = tz[1:].replace(":", "")
        offset = sign * (int(hhmm[:2]) * 3600 + int(hhmm[2:]) * 60)
        epoch -= offset
    return epoch


def _split_log_line(line: str) -> tuple[float | None, str]:
    """Split a ``docker logs --timestamps`` line into (epoch, content)."""
    m = _TS_RE.match(line)
    if m and m.end() < len(line) and line[m.end()] in (" ", "\t"):
        return _epoch_from_iso(m.group(0)), line[m.end():]
    return None, line


def _bytes_to_copy(content: str) -> int | None:
    for rx in (_SYNC_DONE_RE, _SYNC_DONE_RE_ALT):
        m = rx.search(content)
        if m:
            return int(m.group(1))
    m = re.search(r"bytesToCopy[:\s]+(\d+)", content)
    return int(m.group(1)) if m else None


def _parse_service_log(path: str) -> list[tuple[float, str, object]]:
    """Return chronologically-ordered (epoch, kind, extra) sync evidence.

    kind: ``startup2`` | ``secondary`` | ``initsync_done``; extra carries the
    secondary source (``mongod`` | ``sidecar``) or the bytesToCopy value.
    """
    events: list[tuple[float, str, object]] = []
    if not os.path.exists(path):
        return events
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line:
                continue
            epoch, content = _split_log_line(line)
            if epoch is None:
                continue
            low = content.lower()
            if "transition to state secondary" in low or "transition to secondary" in low:
                events.append((epoch, "secondary", "mongod"))
            elif "startup2" in low:
                events.append((epoch, "startup2", None))
            elif "rs_secondary_ready" in low:
                events.append((epoch, "secondary", "sidecar"))
            elif "starting an initial sync" in low or "initial sync attempt" in low:
                events.append((epoch, "initsync_start", None))
            elif "initial sync done" in low or "finished initial sync" in low:
                events.append((epoch, "initsync_done", _bytes_to_copy(content)))
    return events


def _sync_events(log_dir: str, member: str) -> dict:
    out: dict = {"startup2": None, "secondary": None,
                 "secondary_source": None, "bytes": None,
                 "initsync_seen": False}
    for epoch, kind, extra in _parse_service_log(os.path.join(log_dir, f"{member}.log")):
        if kind == "startup2" and out["startup2"] is None:
            out["startup2"] = epoch
        elif kind == "secondary" and out["secondary"] is None:
            out["secondary"] = epoch
            out["secondary_source"] = extra
        elif kind == "initsync_start" or kind == "initsync_done":
            out["initsync_seen"] = True
            if kind == "initsync_done" and extra is not None:
                # Last completed attempt's bytesToCopy (chronological order).
                out["bytes"] = extra
    return out


def _storage_spawns(run_dir: str) -> dict[str, dict]:
    """member -> {'added_epoch': float|None} from container_events.csv."""
    out: dict[str, dict] = {}
    path = os.path.join(run_dir, "container_events.csv")
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            name = (row.get("container") or "").strip()
            if not name.startswith("edge_storage_"):
                continue
            if (row.get("event") or "").strip() != "added":
                continue
            out.setdefault(name, {})["added_epoch"] = _epoch_from_iso(row.get("timestamp_iso"))
    return out


def _storage_cpu_during_sync(run_dir: str, member: str,
                             add_epoch: float | None,
                             sec_epoch: float | None) -> tuple[float | None, str]:
    """Mean storage CPU over resource-stats windows inside [add, secondary]."""
    if add_epoch is None or sec_epoch is None or sec_epoch <= add_epoch:
        return None, ""
    # 1) Per-member storage CPU from per_node_stats.csv when identifiable.
    per_node = os.path.join(run_dir, "per_node_stats.csv")
    if os.path.exists(per_node):
        vals = []
        with open(per_node, "r", encoding="utf-8", errors="replace") as fh:
            for row in csv.DictReader(fh):
                if (row.get("role") or "").strip() != "storage":
                    continue
                if (row.get("server_id") or "").strip() != member:
                    continue
                we = _as_float(row.get("window_end"))
                cpu = _as_float(row.get("cpu_percent"))
                if we is None or cpu is None:
                    continue
                if add_epoch <= we <= sec_epoch:
                    vals.append(cpu)
        if vals:
            return sum(vals) / len(vals), "per_node_stats"
    # 2) LAN-wide storage CPU from resource_stats.csv / resource_stats_debug.csv.
    for fname, col in (("resource_stats.csv", "avg_storage_cpu_percent"),
                       ("resource_stats_debug.csv", "median_storage_cpu_percent")):
        vals = []
        path = os.path.join(run_dir, fname)
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for row in csv.DictReader(fh):
                we = _as_float(row.get("window_end"))
                cpu = _as_float(row.get(col))
                if we is None or cpu is None:
                    continue
                if add_epoch <= we <= sec_epoch:
                    vals.append(cpu)
        if vals:
            return sum(vals) / len(vals), fname
    return None, ""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir")
    ap.add_argument("--output", default="",
                    help="sync-cost CSV output (default: RUN_DIR/sync_cost.csv)")
    args = ap.parse_args()

    run_dir = args.run_dir
    env = _parse_env(os.path.join(run_dir, "controller_env_snapshot.env"))
    policy = env.get("SCALEUP_POLICY", "dual")
    if policy not in _RQ2_ARMS:
        print(f"[skip] {run_dir}: SCALEUP_POLICY={policy!r} — not an RQ2 run")
        return 0

    out_path = args.output or os.path.join(run_dir, "sync_cost.csv")
    spawns = _storage_spawns(run_dir)
    log_dir = os.path.join(run_dir, "service_logs")

    # Members = union of container_events spawns and storage service logs.
    members = set(spawns)
    if os.path.isdir(log_dir):
        for name in os.listdir(log_dir):
            if name.startswith("edge_storage_") and name.endswith(".log"):
                members.add(name[: -len(".log")])

    cols = ["member_id", "add_ts", "first_secondary_ts", "sync_duration_s",
            "bytes_applied", "storage_cpu_during_sync_pct", "source"]
    rows = []
    no_evidence = []
    for member in sorted(members):
        ev = _sync_events(log_dir, member)
        added_epoch = spawns.get(member, {}).get("added_epoch")
        # A lone STARTUP2 without a join marker is the static primary at
        # replica-set init (no initial sync) — not a sync-cost event.
        if (added_epoch is None and ev["secondary"] is None
                and not ev["initsync_seen"]):
            no_evidence.append(member)
            continue
        add_epoch = ev["startup2"] if ev["startup2"] is not None else added_epoch
        sec_epoch = ev["secondary"]
        sync_duration = (sec_epoch - add_epoch) if (add_epoch is not None and sec_epoch is not None) else None
        cpu, cpu_src = _storage_cpu_during_sync(run_dir, member, add_epoch, sec_epoch)
        add_tag = "startup2" if ev["startup2"] is not None else "added"
        sec_tag = "secondary" if ev["secondary_source"] == "mongod" else \
            ("rs_secondary_ready" if ev["secondary"] is not None else "")
        source = add_tag if not sec_tag else f"{add_tag}+{sec_tag}"
        rows.append({
            "member_id": member,
            "add_ts": _fmt(add_epoch) if add_epoch is not None else "",
            "first_secondary_ts": _fmt(sec_epoch) if sec_epoch is not None else "",
            "sync_duration_s": _fmt(sync_duration) if sync_duration is not None else "",
            "bytes_applied": ev["bytes"] if ev["bytes"] is not None else "",
            "storage_cpu_during_sync_pct": _fmt(cpu) if cpu is not None else "",
            "source": source,
        })

    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"RQ2 sync-cost analysis — run {os.path.basename(run_dir)} (policy={policy})")
    print(f"  members considered : {len(members)}")
    print(f"  rows written       : {len(rows)} -> {out_path}")
    if no_evidence:
        print(f"  no sync evidence   : {len(no_evidence)} members "
              f"({', '.join(sorted(no_evidence))})")
    if rows:
        durations = [r["sync_duration_s"] for r in rows if r["sync_duration_s"]]
        bytes_vals = [r["bytes_applied"] for r in rows if r["bytes_applied"] != ""]
        cpus = [r["storage_cpu_during_sync_pct"] for r in rows
                if r["storage_cpu_during_sync_pct"] != ""]
        if durations:
            ds = sorted(float(d) for d in durations)
            print(f"  median sync_duration_s : {ds[len(ds)//2]:.1f} "
                  f"({len(ds)} members)")
        if bytes_vals:
            bs = sorted(int(b) for b in bytes_vals)
            print(f"  median bytes_applied   : {bs[len(bs)//2]:,} "
                  f"({len(bs)} members)")
        if cpus:
            cs = sorted(float(c) for c in cpus)
            print(f"  median storage_cpu_pct : {cs[len(cs)//2]:.1f} "
                  f"({len(cs)} members)")
        if cpu_src:
            print(f"  storage CPU source     : {cpu_src}")
    else:
        print("  notice: no storage sync evidence found (e.g. cell added no "
              "storage) — header-only output written, no failure")
    return 0


if __name__ == "__main__":
    sys.exit(main())
