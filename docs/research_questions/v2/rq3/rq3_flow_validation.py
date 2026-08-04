#!/usr/bin/env python3
"""rq3_flow_validation.py — RQ3 flow-isolation + admission-leak validity.

Verifies the RQ3 measurement assumptions (D5, D2):

- **Check A (no pre-admission traffic):** no request in ``client_requests.csv``
  is attributed to a backend before its ``admitted_ts``.
- **Check B (no post-removal traffic):** after a backend is removed (from
  ``container_events.csv``), no request is attributed to it (no stale pinned
  flow survives removal).
- **Check C (flow-delete coverage):** the number of ``request_complete``
  handling log lines (``vip_server: client flows deleted``) vs the number of
  **measured requests** (``status`` in ``{completed, timeout}`` — dropped/
  canceled never reach the service and emit no ``request_complete``); reported
  as a coverage ratio. **Hard at coverage >= 0.9** (below =>
  instrumentation-degraded run) per RQ3 v2 §2.8.
- **Check D (client model):** no two requests from the same client share a
  source port within a short reuse window (one fresh TCP connection per
  request). The criterion is intentionally NOT "different backend per request"
  (under ``topology_host`` the newest backend legitimately wins repeatedly).
  **Tolerated <= 1% reuse; > 1% fails the run** (one-connection-per-request is
  a precondition for flow isolation; the D5 async-delete caveat is within the
  1% allowance) per RQ3 v2 §2.8. Unknown ports (``""`` / ``"0"`` — capture
  failure) are excluded from both numerator and denominator; an unknown
  fraction > 50% reports the run as instrumentation-degraded (exit 2).

Run-kind guard: only RQ3-arm runs (``READINESS_PROPAGATION`` in
``{direct, discovery}``) are processed.

Usage:
    python3 docs/research_questions/v2/rq3/rq3_flow_validation.py RUN_DIR \
        [--reuse-window-s 2.0]
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime

_RQ3_ARMS = {"direct", "discovery", "discovery_15"}
_REMOVAL_EVENTS = {"die", "stop", "kill", "remove", "removed"}
_REMOVAL_STATES = {"dead", "exited", "removed", "removing"}


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


def _load_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    import csv
    with open(path, "r", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _as_int(v, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _iso_to_epoch(v: str) -> float:
    try:
        s = v.strip()
        if not s:
            return 0.0
        if s.endswith("Z"):
            s = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _load_admissions(run_dir: str) -> list[dict]:
    rows = []
    for lan in (1, 2):
        rows.extend(_load_csv(os.path.join(run_dir, f"admission_log_lan{lan}.csv")))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser(description="RQ3 flow-isolation validity")
    ap.add_argument("run_dir", help="RQ3 run folder")
    ap.add_argument("--reuse-window-s", type=float, default=2.0,
                    help="Check D source-port reuse window (s)")
    args = ap.parse_args()

    env = _parse_env(os.path.join(args.run_dir, "controller_env_snapshot.env"))
    arm = env.get("READINESS_PROPAGATION", "")
    if arm not in _RQ3_ARMS:
        print(f"SKIP {args.run_dir}: READINESS_PROPAGATION={arm!r} "
              f"(not an RQ3 arm)", file=sys.stderr)
        return 0

    print(f"=== {args.run_dir}  arm={arm} ===")

    admissions = _load_admissions(args.run_dir)
    admitted = [a for a in admissions if a.get("result") == "admitted"]
    admitted_ts = {a.get("container"): float(a.get("admitted_ts") or 0)
                   for a in admitted if a.get("admitted_ts")}
    abandoned = [a for a in admissions if a.get("result") == "abandoned"]
    print(f"  admissions: {len(admitted)} admitted, {len(abandoned)} abandoned")

    client_rows = _load_csv(os.path.join(args.run_dir, "client_requests.csv"))
    for row in client_rows:
        row["_ts"] = _iso_to_epoch(row.get("completed_at", ""))

    abandoned_names = {a.get("container") for a in admissions
                       if a.get("result") == "abandoned"}

    # ── Check A: no pre-admission traffic (and no traffic to abandoned nodes) ──
    violations_a = []
    for row in client_rows:
        backend = row.get("backend_id", "")
        if backend == "unknown":
            continue
        if backend in abandoned_names:
            # A never-admitted backend must never serve traffic.
            if row["_ts"] > 0:
                violations_a.append((backend, row["_ts"], -1.0))
            continue
        if backend in admitted_ts and row["_ts"] > 0 and row["_ts"] < admitted_ts[backend]:
            violations_a.append((backend, row["_ts"], admitted_ts[backend]))
    print(f"  Check A (no pre-admission / abandoned traffic): "
          f"{len(violations_a)} violation(s) "
          f"{'PASS' if not violations_a else 'FAIL'}")

    # ── Check B: no post-removal traffic (container_events.csv) ──
    events = _load_csv(os.path.join(args.run_dir, "container_events.csv"))
    removal_ts: dict[str, float] = {}
    for ev in events:
        if ev.get("container") not in admitted_ts:
            continue
        event = ev.get("event", "")
        state = ev.get("state", "")
        # A removal is a terminal event (die/stop/kill/remove) OR a
        # state_change that lands in a terminal state (dead/exited/removing/
        # removed). The benign `created -> running` startup transition must
        # NOT be treated as a removal.
        is_removal = (event in _REMOVAL_EVENTS
                      or (event == "state_change" and state in _REMOVAL_STATES)
                      or state in _REMOVAL_STATES)
        if is_removal:
            t = _iso_to_epoch(ev.get("timestamp_iso", ""))
            if t > 0:
                removal_ts.setdefault(ev["container"], t)
    violations_b = []
    for row in client_rows:
        backend = row.get("backend_id", "")
        if backend in removal_ts and row["_ts"] > removal_ts[backend]:
            violations_b.append((backend, row["_ts"], removal_ts[backend]))
    if not events:
        print("  Check B (no post-removal traffic): SKIPPED (no container_events.csv)")
    else:
        print(f"  Check B (no post-removal traffic): {len(violations_b)} violation(s) "
              f"(removals tracked={len(removal_ts)}) "
              f"{'PASS' if not violations_b else 'FAIL'}")

    # ── Check C: flow-delete coverage ──
    deletes = 0
    for lan in (1, 2):
        log_path = os.path.join(args.run_dir, f"controller_lan{lan}.log")
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
                # Only request_complete-driven deletes are counted (the
                # controller logs this exact prefix in state.py).
                deletes += sum(1 for line in fh
                               if "request_complete: client flows deleted" in line)
    # Measured = completed requests only: request_complete is emitted after a
    # response is flushed, so timeout/dropped/canceled rows never produce a
    # delete event (a timeout is exactly the degraded case RQ3 measures).
    measured = [r for r in client_rows
                if r.get("status", "") == "completed"]
    if not measured and client_rows:
        measured = client_rows  # legacy CSV without a status column
    measured_n = len(measured)
    if deletes == 0:
        print("  Check C (flow-delete coverage): SKIPPED "
              "(no 'client flows deleted' lines in controller logs)")
        check_c_fail = False
    else:
        coverage = deletes / measured_n if measured_n else 0.0
        check_c_fail = coverage < 0.9
        print(f"  Check C (flow-delete coverage): deletes={deletes} "
              f"requests={measured_n} coverage={coverage:.2f} "
              f"{'PASS' if not check_c_fail else 'FAIL (< 0.9)'}")

    # ── Check D: one fresh connection per request (source-port reuse) ──
    # Unknown ports ("", "0" — capture failure) are excluded from BOTH the
    # numerator and denominator; an unknown fraction > 50% reports the run as
    # instrumentation-degraded (exit 2), not a hard fail.
    by_client: dict[str, list[tuple[float, str]]] = {}
    for row in client_rows:
        cns = row.get("client_ns", "")
        if not cns:
            continue
        by_client.setdefault(cns, []).append(
            (row["_ts"], row.get("source_port", "")))
    violations_d = 0
    with_port = 0
    unknown_d = 0
    for cns, entries in by_client.items():
        entries.sort(key=lambda x: x[0])
        seen: dict[str, float] = {}
        for t, port in entries:
            if not port or port == "0":
                unknown_d += 1
                continue
            with_port += 1
            if port in seen and t - seen[port] < args.reuse_window_s:
                violations_d += 1
            seen[port] = t
    total_d = with_port + unknown_d
    reuse_rate = (violations_d / with_port) if with_port else 0.0
    unknown_rate = (unknown_d / total_d) if total_d else 0.0
    check_d_fail = reuse_rate > 0.01
    check_d_degraded = (not check_d_fail) and unknown_rate > 0.50
    check_d_status = ("PASS (<= 1%)"
                      if not (check_d_fail or check_d_degraded)
                      else ("FAIL (> 1%)" if check_d_fail
                            else "DEGRADED (>50% unknown)"))
    print(f"  Check D (one fresh connection per request): "
          f"{violations_d} reuse violation(s) / {with_port} with port "
          f"rate={reuse_rate:.4f} unknown={unknown_rate:.2%} {check_d_status}")

    hard_fail = bool(violations_a or violations_b or check_d_fail)
    print("  => flow-isolation valid"
          if not (hard_fail or check_c_fail or check_d_degraded)
          else ("  => flow-isolation VIOLATIONS — investigate"
                if hard_fail
                else "  => flow-isolation DEGRADED "
                     "(Check C < 0.9 or Check D >50% unknown ports)"))

    # 0 = valid; 1 = hard violation (A/B/D); 2 = instrumentation-degraded (C/D).
    if hard_fail:
        return 1
    if check_c_fail or check_d_degraded:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
