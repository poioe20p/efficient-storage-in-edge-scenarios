#!/usr/bin/env python3
"""rq3_admission_analysis.py — RQ3 per-run readiness-propagation analysis.

From the RQ3 admission logs (``admission_log_lan1/lan2.csv``), the decision
logs (``decision_log_lan1/lan2.csv``), and ``client_requests.csv``, compute per
compute backend:

- ``spawn_complete -> app_ready_observed`` (app startup + first-observation
  quantization; readiness-criterion identity check across arms);
- **``spawn_complete -> admitted``** (the PRIMARY metric — D3, it embeds the
  propagation-delay quantization; true app-ready is unobservable between
  probes);
- ``admitted -> first_flow`` and ``first_flow -> first_success`` (from
  ``client_requests.csv`` joined on ``X-Backend-ID == container``, rows with
  request time >= admitted_ts; ``first_flow`` excludes ``unknown`` backend ids);
- ``scale decision -> usable capacity`` (decision-log ``scale_up``/ComputeAlert
  ts -> first_success);
- useful initial request share (fraction of requests served by this backend in
  the transition window that succeed);
- transition-window p50/p95/p99 latency + failure rate.

Emit per-run tables, the arm × replicate counterbalance matrix, and (when
multiple runs are given) a cross-arm summary with per-run variance.

Run-kind guard: only RQ3-arm runs (``READINESS_PROPAGATION`` in
``{direct, discovery}``) are processed.

Usage:
    python3 docs/research_questions/v2/rq3/rq3_admission_analysis.py \\
        RUN_DIR [RUN_DIR ...] [--transition-window-s 30] [--csv OUT]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
from datetime import datetime, timezone

_RQ3_ARMS = {"direct", "discovery"}
_EPISODE_SUBSTR = ("episode", "spike")


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
    with open(path, "r", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _load_admissions(run_dir: str) -> list[dict]:
    rows = []
    for lan in (1, 2):
        rows.extend(_load_csv(os.path.join(run_dir, f"admission_log_lan{lan}.csv")))
    return rows


def _as_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _as_int(v, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _iso_to_epoch(v: str) -> float:
    """Parse the driver's UTC ISO timestamp to epoch seconds."""
    try:
        s = v.strip()
        if not s:
            return 0.0
        if s.endswith("Z"):
            s = s.replace("Z", "+00:00")
        return datetime.fromisoformat(s).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _episode_label(run_dir: str) -> str:
    snap = os.path.join(run_dir, "phases_snapshot.json")
    if not os.path.exists(snap):
        return ""
    try:
        phases = json.load(open(snap, "r", encoding="utf-8")).get("phases", [])
    except Exception:
        return ""
    for ph in phases:
        name = ph.get("name", "")
        if any(s in name for s in _EPISODE_SUBSTR):
            return "compute_bound" if "compute" in name else "data_bound"
    return ""


def _scale_decision_ts(run_dir: str, lan: int, spawn_started_ts: float) -> float:
    """Nearest preceding ComputeAlert scale_up decision ts for a spawn."""
    best = 0.0
    for row in _load_csv(os.path.join(run_dir, f"decision_log_lan{lan}.csv")):
        if row.get("action_type") != "scale_up":
            continue
        if row.get("action") != "ComputeAlert":
            continue
        ts = _as_float(row.get("ts"))
        if 0 < ts <= spawn_started_ts and ts > best:
            best = ts
    return best


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * p
    f = int(k)
    c = f + 1 if f + 1 < len(ordered) else f
    return ordered[f] + (ordered[c] - ordered[f]) * (k - f)


def _process_run(run_dir: str, transition_window_s: float) -> dict:
    env = _parse_env(os.path.join(run_dir, "controller_env_snapshot.env"))
    arm = env.get("READINESS_PROPAGATION", "")
    result: dict = {"run_dir": run_dir, "arm": arm,
                    "episode": _episode_label(run_dir), "backends": []}

    client_rows = _load_csv(os.path.join(run_dir, "client_requests.csv"))
    for row in client_rows:
        row["_ts"] = _iso_to_epoch(row.get("completed_at", ""))

    for adm in _load_admissions(run_dir):
        if adm.get("result") != "admitted":
            continue
        container = adm.get("container", "")
        admitted_ts = _as_float(adm.get("admitted_ts"))
        spawn_complete_ts = _as_float(adm.get("spawn_complete_ts"))
        app_ready_ts = _as_float(adm.get("app_ready_ts"))
        lan = _as_int(adm.get("lan"))
        if admitted_ts <= 0 or not container:
            continue

        # Requests served by this backend after admission.
        served = [r for r in client_rows
                  if r.get("backend_id") == container and r["_ts"] >= admitted_ts
                  and r.get("backend_id") != "unknown"]
        first_flow = min((r["_ts"] for r in served), default=0.0)
        first_success = min(
            (r["_ts"] for r in served if _as_int(r.get("http_status")) in range(200, 300)),
            default=0.0,
        )
        transition = [r for r in served
                      if r["_ts"] <= admitted_ts + transition_window_s]
        transition_status = [_as_int(r.get("http_status")) for r in transition]
        failures = sum(1 for s in transition_status if s == 0 or s >= 400)
        transition_lat = [_as_float(r.get("latency_s")) for r in transition]

        result["backends"].append({
            "container": container,
            "lan": lan,
            "mode": adm.get("mode", ""),
            "spawn_complete_to_app_ready_s": (app_ready_ts - spawn_complete_ts
                                              if app_ready_ts > 0 else None),
            "spawn_complete_to_admitted_s": (admitted_ts - spawn_complete_ts
                                             if spawn_complete_ts > 0 else None),
            "admitted_to_first_flow_s": (first_flow - admitted_ts
                                         if first_flow > 0 else None),
            "first_flow_to_first_success_s": (first_success - first_flow
                                              if first_success > 0 and first_flow > 0 else None),
            "scale_decision_to_first_success_s": None,
            "useful_initial_share": ((len(transition) - failures) / len(transition)
                                     if transition else None),
            "transition_latency_p50": _percentile(transition_lat, 0.50),
            "transition_latency_p95": _percentile(transition_lat, 0.95),
            "transition_latency_p99": _percentile(transition_lat, 0.99),
            "transition_failure_rate": (failures / len(transition)
                                        if transition else None),
            "transition_requests": len(transition),
        })
        dec_ts = _scale_decision_ts(run_dir, lan, _as_float(adm.get("spawn_started_ts")))
        if dec_ts > 0 and first_success > 0:
            result["backends"][-1]["scale_decision_to_first_success_s"] = (
                first_success - dec_ts)

    return result


def _summarize(run_dir: str, r: dict) -> None:
    print(f"\n=== {run_dir}  arm={r['arm']}  episode={r['episode']} "
          f"backends={len(r['backends'])} ===")
    if not r["backends"]:
        print("  (no admitted compute backends)")
        return
    hdr = ("container", "lan", "start->ready", "start->admit", "admit->1stflow",
           "1stflow->1stok", "dec->1stok", "useful_share", "p50", "p95", "p99",
           "fail_rate", "n")
    print("  " + "\t".join(hdr))
    for b in r["backends"]:
        def _f(v):
            return "" if v is None else f"{v:.3f}"
        print("  " + "\t".join([
            b["container"], str(b["lan"]),
            _f(b["spawn_complete_to_app_ready_s"]),
            _f(b["spawn_complete_to_admitted_s"]),
            _f(b["admitted_to_first_flow_s"]),
            _f(b["first_flow_to_first_success_s"]),
            _f(b["scale_decision_to_first_success_s"]),
            "" if b["useful_initial_share"] is None
            else f"{b['useful_initial_share']:.3f}",
            f"{b['transition_latency_p50']:.3f}",
            f"{b['transition_latency_p95']:.3f}",
            f"{b['transition_latency_p99']:.3f}",
            "" if b["transition_failure_rate"] is None
            else f"{b['transition_failure_rate']:.3f}",
            str(b["transition_requests"]),
        ]))


def _cross_arm(results: list[dict]) -> None:
    print("\n=== Cross-arm summary (primary: spawn_complete -> admitted) ===")
    by_arm: dict[str, list[float]] = {}
    for r in results:
        by_arm.setdefault(r["arm"], []).extend(
            b["spawn_complete_to_admitted_s"]
            for b in r["backends"] if b["spawn_complete_to_admitted_s"] is not None)
    for arm in sorted(by_arm):
        vals = by_arm[arm]
        if not vals:
            print(f"  {arm}: (no data)")
            continue
        mean = statistics.mean(vals)
        stdev = statistics.stdev(vals) if len(vals) > 1 else 0.0
        median = statistics.median(vals)
        print(f"  {arm}: n={len(vals)} mean={mean:.3f}s "
              f"median={median:.3f}s stdev={stdev:.3f}s "
              f"min={min(vals):.3f}s max={max(vals):.3f}s")


def main() -> int:
    ap = argparse.ArgumentParser(description="RQ3 admission analysis")
    ap.add_argument("run_dirs", nargs="+", help="RQ3 run folder(s)")
    ap.add_argument("--transition-window-s", type=float, default=30.0,
                    help="useful-initial-share transition window (s)")
    ap.add_argument("--csv", help="optional aggregated output CSV")
    args = ap.parse_args()

    results = []
    for run_dir in args.run_dirs:
        env = _parse_env(os.path.join(run_dir, "controller_env_snapshot.env"))
        arm = env.get("READINESS_PROPAGATION", "")
        if arm not in _RQ3_ARMS:
            print(f"SKIP {run_dir}: READINESS_PROPAGATION={arm!r} "
                  f"(not an RQ3 arm)", file=sys.stderr)
            continue
        r = _process_run(run_dir, args.transition_window_s)
        results.append(r)
        _summarize(run_dir, r)

    _cross_arm(results)

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            fieldnames = ["run_dir", "arm", "episode", "container", "lan", "mode",
                          "spawn_complete_to_app_ready_s",
                          "spawn_complete_to_admitted_s", "admitted_to_first_flow_s",
                          "first_flow_to_first_success_s",
                          "scale_decision_to_first_success_s", "useful_initial_share",
                          "transition_latency_p50", "transition_latency_p95",
                          "transition_latency_p99", "transition_failure_rate",
                          "transition_requests"]
            w = csv.DictWriter(fh, fieldnames=fieldnames)
            w.writeheader()
            for r in results:
                for b in r["backends"]:
                    row = {"run_dir": r["run_dir"], "arm": r["arm"],
                           "episode": r["episode"], **b}
                    w.writerow(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
