#!/usr/bin/env python3
"""rq3_admission_analysis.py — RQ3 v2 per-run readiness-propagation analysis.

RQ3 v2 contract (``docs/operation/testing/experiment/v2/rq3/rq3_v2_rework_plan.md``
§2.1/§2.4/§2.5):

- **Status-aware service quality** over the open-loop driver CSV (14th
  ``status`` column): failure = ``completed`` & ``http_status != 200``;
  ``timeout_rate`` = ``status=timeout`` / (offered - canceled - dropped);
  ``dropped``/``canceled`` counted in offered, excluded from latency + failure,
  reported separately.
- **Headline (between-arm consequence):** pool-wide (old-backend) ``timeout_rate``
  over the **gap window** ``[spawn_started, admitted]`` — spike-phase-truncated
  via the generator ``phase`` label (requests outside the spike phase are
  excluded, so a slow backend admitted after the spike->cleanup boundary
  contributes timing metrics only, per §2.4).
- **Supporting:** gap-window ``failure_rate`` (completed-only), useful initial
  request share over ``[spawn_started, admitted + TRANSITION_WINDOW_S]``
  (pool-wide), scale-decision -> usable-capacity.
- **Secondary / manipulation:** ``spawn_complete -> admitted`` quantization,
  ``admitted -> first_flow``, ``first_flow -> first_success``,
  transition-window latency/failure for the new backend, ``admit_source`` event
  fraction (>= 0.80 gate in ``direct`` runs), readiness-criterion identity
   (post-admission confirming ``/ready`` probe, reported via the controller
   log).
- **Run-level aggregation:** per-run median over backends; >= 20 attributed
  requests per backend for the share/failure/timeout metrics; min-admissions
  gate (>= 1 admitted backend per LAN) -> run flagged ``void``.
- **Baseline (context only):** pool-wide ``timeout_rate`` over
  ``[max(spawn_started - BASELINE_S, spike_start), spawn_started]``,
  spike-phase-truncated; ``gap_delta_pp`` = gap - baseline (>= ``GAP_DELTA_PP``
  flags a "degrading gap" — context, not a verdict, per §2.7).

Run-kind guard: only RQ3-arm runs (``READINESS_PROPAGATION`` in
``{direct, discovery, discovery_15}``) are processed.

Usage:
    python3 docs/research_questions/v2/rq3/rq3_admission_analysis.py \\
        RUN_DIR [RUN_DIR ...] [--transition-window-s 30] [--baseline-s 60] \\
        [--gap-delta-pp 5.0] [--csv OUT]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
from datetime import datetime, timezone

_RQ3_ARMS = {"direct", "discovery", "discovery_15"}
# Episode phases: the RQ3 compute episode's spike phase name(s). Requests in
# any other phase are excluded from gap/baseline/transition windows (RQ3 v2
# truncation rule, §2.4).
_SPIKE_SUBSTR = ("spike", "compute_spike", "episode")
_TIMEOUT = "timeout"
_COMPLETED = "completed"
_CANCELED = "canceled"
_DROPPED = "dropped"
# Minimum attributed requests for a backend-level share/failure/timeout metric.
_MIN_REQUESTS = 20
# Minimum admitted backends per LAN for a non-void run.
_MIN_ADMISSIONS_PER_LAN = 1
# Event-driven fraction below which a `direct` run is instrumentation-degraded.
_EVENT_FRACTION_GATE = 0.80


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


def _req_ts(row: dict) -> float:
    """Completion timestamp (epoch) with a sent_at fallback."""
    t = _iso_to_epoch(row.get("completed_at", ""))
    if t <= 0:
        t = _iso_to_epoch(row.get("sent_at", ""))
    return t


def _req_status(row: dict) -> str:
    """Driver status class; legacy CSVs without the column default to completed."""
    st = (row.get("status") or "").strip()
    if st:
        return st
    return _COMPLETED if (row.get("http_status") or "") else ""


def _is_spike_phase(name: str) -> bool:
    n = (name or "").lower()
    return any(s in n for s in _SPIKE_SUBSTR)


def _episode_label(run_dir: str) -> str:
    snap = os.path.join(run_dir, "phases_snapshot.json")
    if not os.path.exists(snap):
        return ""
    try:
        phases = json.load(open(snap, "r", encoding="utf-8")).get("phases", [])
    except Exception:
        return ""
    for ph in phases:
        if _is_spike_phase(ph.get("name", "")):
            return "compute_bound"
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


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    k = (len(ordered) - 1) * p
    f = int(k)
    c = f + 1 if f + 1 < len(ordered) else f
    return ordered[f] + (ordered[c] - ordered[f]) * (k - f)


def _rate(rows: list[dict], kind: str) -> float | None:
    """Rate helpers over a row subset. Returns None when undefined (n < 1).

    timeout_rate = timeout / (offered - canceled - dropped)
    failure_rate = (completed & http != 200) / completed
    """
    if kind == "timeout":
        # Denominator = offered - dropped - canceled (i.e. completed + timeout).
        denom = [r for r in rows if _req_status(r) in (_COMPLETED, _TIMEOUT)]
        if not denom:
            return None
        return sum(1 for r in rows if _req_status(r) == _TIMEOUT) / len(denom)
    if kind == "failure":
        completed = [r for r in rows if _req_status(r) == _COMPLETED]
        if not completed:
            return None
        return sum(1 for r in completed if _as_int(r.get("http_status")) not in
                   range(200, 300)) / len(completed)
    raise ValueError(kind)


def _success_share(rows: list[dict]) -> float | None:
    """Useful initial request share: successes over offered (excl dropped/canceled)."""
    offered = [r for r in rows if _req_status(r) in (_COMPLETED, _TIMEOUT)]
    if not offered:
        return None
    successes = sum(
        1 for r in offered
        if _req_status(r) == _COMPLETED
        and _as_int(r.get("http_status")) in range(200, 300)
    )
    return successes / len(offered)


def _median(vals: list[float]) -> float | None:
    if not vals:
        return None
    return statistics.median(vals)


def _gap_requests_per_lan(client_rows: list[dict], backends: list[dict],
                          lan: int) -> int:
    """Distinct spike-phase requests in the union gap window for one LAN.

    Window = [min(spawn_started), max(admitted)) across that LAN's admitted
    backends; counts rows whose ``client_lan`` matches and that are not
    attributed to a new backend of that LAN. A distinct-request count (not
    summed per-backend windows, which overlap and would double-count).
    """
    if not backends:
        return 0
    starts = [b["spawn_started_ts"] for b in backends
              if b.get("spawn_started_ts")]
    ends = [b["admitted_ts"] for b in backends if b.get("admitted_ts")]
    if not starts or not ends:
        return 0
    lo, hi = min(starts), max(ends)
    prefix = f"lan{lan}"
    containers = {b["container"] for b in backends}
    return sum(
        1 for r in client_rows
        if _is_spike_phase(r.get("phase", ""))
        and (r.get("client_lan") or "").startswith(prefix)
        and lo <= r["_ts"] < hi
        and r.get("backend_id") not in containers
    )


def _process_run(run_dir: str, transition_window_s: float, baseline_s: float,
                 gap_delta_pp: float) -> dict:
    env = _parse_env(os.path.join(run_dir, "controller_env_snapshot.env"))
    arm = env.get("READINESS_PROPAGATION", "")
    discovery_s = _as_float(env.get("DISCOVERY_POLL_INTERVAL_S"))
    # Arm re-labeling: the discovery_15 sensitivity cell is a `discovery`
    # regime with DISCOVERY_POLL_INTERVAL_S=15 (only the interval differs, per
    # the canonical-env rule), so the arm label is derived from the interval.
    if arm == "discovery" and abs(discovery_s - 15.0) < 1e-9:
        arm = "discovery_15"
    result: dict = {
        "run_dir": run_dir, "arm": arm, "discovery_interval_s": discovery_s,
        "episode": _episode_label(run_dir), "backends": [], "void": False,
        "void_reason": "", "event_fraction": None,
        "event_fraction_degraded": False,
    }

    client_rows = _load_csv(os.path.join(run_dir, "client_requests.csv"))
    for row in client_rows:
        row["_ts"] = _req_ts(row)

    per_lan: dict[int, list[dict]] = {1: [], 2: []}
    for adm in _load_admissions(run_dir):
        if adm.get("result") != "admitted":
            continue
        container = adm.get("container", "")
        admitted_ts = _as_float(adm.get("admitted_ts"))
        spawn_started_ts = _as_float(adm.get("spawn_started_ts"))
        spawn_complete_ts = _as_float(adm.get("spawn_complete_ts"))
        app_ready_ts = _as_float(adm.get("app_ready_ts"))
        lan = _as_int(adm.get("lan"))
        admit_source = (adm.get("admit_source") or "probe").strip()
        if admitted_ts <= 0 or not container:
            continue

        # ---- Gap window (headline): pool-wide, spike-phase-truncated ----
        gap = [r for r in client_rows
               if _is_spike_phase(r.get("phase", ""))
               and r["_ts"] >= spawn_started_ts and r["_ts"] < admitted_ts
               and r.get("backend_id") != container]
        baseline = [r for r in client_rows
                    if _is_spike_phase(r.get("phase", ""))
                    and r["_ts"] >= spawn_started_ts - baseline_s
                    and r["_ts"] < spawn_started_ts
                    and r.get("backend_id") != container]

        # ---- Useful initial share (pool-wide) + transition (new backend) ----
        useful = [r for r in client_rows
                  if _is_spike_phase(r.get("phase", ""))
                  and r["_ts"] >= spawn_started_ts
                  and r["_ts"] <= admitted_ts + transition_window_s]
        served = [r for r in client_rows
                  if r.get("backend_id") == container
                  and r.get("backend_id") != "unknown"
                  and r["_ts"] >= admitted_ts
                  and _req_status(r) in (_COMPLETED, _TIMEOUT)]
        transition = [r for r in served
                      if _is_spike_phase(r.get("phase", ""))
                      and r["_ts"] <= admitted_ts + transition_window_s]

        first_flow = min((r["_ts"] for r in served), default=0.0)
        first_success = min(
            (r["_ts"] for r in served
             if _req_status(r) == _COMPLETED
             and _as_int(r.get("http_status")) in range(200, 300)),
            default=0.0,
        )

        gap_timeout = _rate(gap, "timeout")
        gap_failure = _rate(gap, "failure")
        # Request-count rule applies to share/failure/timeout metrics only and
        # counts ATTRIBUTED requests (completed + timeout; dropped/canceled
        # never reached the service).
        if len([r for r in gap if _req_status(r) in (_COMPLETED, _TIMEOUT)]) < _MIN_REQUESTS:
            gap_timeout = None
        if len([r for r in gap if _req_status(r) == _COMPLETED]) < _MIN_REQUESTS:
            gap_failure = None
        baseline_timeout = _rate(baseline, "timeout")
        if len([r for r in baseline
                if _req_status(r) in (_COMPLETED, _TIMEOUT)]) < _MIN_REQUESTS:
            baseline_timeout = None

        gap_delta = (
            (gap_timeout - baseline_timeout) * 100.0
            if gap_timeout is not None and baseline_timeout is not None else None
        )

        transition_lat = [
            _as_float(r.get("latency_s")) for r in transition
            if _req_status(r) == _COMPLETED
        ]

        useful_share = _success_share(useful)
        if len([r for r in useful
                if _req_status(r) in (_COMPLETED, _TIMEOUT)]) < _MIN_REQUESTS:
            useful_share = None
        transition_to = _rate(transition, "timeout")
        if len([r for r in transition
                if _req_status(r) in (_COMPLETED, _TIMEOUT)]) < _MIN_REQUESTS:
            transition_to = None
        transition_fr = _rate(transition, "failure")
        if len([r for r in transition
                if _req_status(r) == _COMPLETED]) < _MIN_REQUESTS:
            transition_fr = None

        backend = {
            "container": container,
            "lan": lan,
            "mode": adm.get("mode", ""),
            "admit_source": admit_source,
            "spawn_started_ts": spawn_started_ts,
            "admitted_ts": admitted_ts,
            "spawn_complete_to_app_ready_s": (app_ready_ts - spawn_complete_ts
                                              if app_ready_ts > 0 else None),
            "spawn_complete_to_admitted_s": (admitted_ts - spawn_complete_ts
                                             if spawn_complete_ts > 0 else None),
            "admitted_to_first_flow_s": (first_flow - admitted_ts
                                         if first_flow > 0 else None),
            "first_flow_to_first_success_s": (first_success - first_flow
                                              if first_success > 0 and first_flow > 0 else None),
            "scale_decision_to_first_success_s": None,
            "useful_initial_share": useful_share,
            "gap_timeout_rate": gap_timeout,
            "gap_failure_rate": gap_failure,
            "baseline_timeout_rate": baseline_timeout,
            "gap_delta_pp": gap_delta,
            "transition_timeout_rate": transition_to,
            "transition_failure_rate": transition_fr,
            "transition_latency_p50": _percentile(transition_lat, 0.50),
            "transition_latency_p95": _percentile(transition_lat, 0.95),
            "transition_latency_p99": _percentile(transition_lat, 0.99),
            "transition_requests": len(transition),
            "gap_requests": len(gap),
        }
        dec_ts = _scale_decision_ts(run_dir, lan, spawn_started_ts)
        if dec_ts > 0 and first_success > 0:
            backend["scale_decision_to_first_success_s"] = first_success - dec_ts
        result["backends"].append(backend)
        per_lan.setdefault(lan, []).append(backend)

    # ---- Run-level aggregation + gates ----
    for lan, items in per_lan.items():
        if len(items) < _MIN_ADMISSIONS_PER_LAN:
            result["void"] = True
            result["void_reason"] = (
                f"lan{lan} admitted backends < {_MIN_ADMISSIONS_PER_LAN}")

    def _rmed(key):
        return _median([b[key] for b in result["backends"]
                        if b[key] is not None])

    result.update({
        "backends_total": len(result["backends"]),
        "backends_lan1": len(per_lan.get(1, [])),
        "backends_lan2": len(per_lan.get(2, [])),
        "gap_timeout_rate_median": _rmed("gap_timeout_rate"),
        "gap_failure_rate_median": _rmed("gap_failure_rate"),
        "useful_share_median": _rmed("useful_initial_share"),
        "scale_to_first_success_median_s": _rmed("scale_decision_to_first_success_s"),
        "spawn_to_admitted_median_s": _rmed("spawn_complete_to_admitted_s"),
        "admitted_to_first_flow_median_s": _rmed("admitted_to_first_flow_s"),
        "transition_timeout_rate_median": _rmed("transition_timeout_rate"),
        "transition_failure_rate_median": _rmed("transition_failure_rate"),
        "gap_requests_total": sum(b["gap_requests"] for b in result["backends"]),
        # Per-LAN DISTINCT gap-request counts (union window per LAN) so the
        # pre-flight measurability gate (>= 20 gap-window requests per LAN,
        # plan §2.7/§9) is enforceable and not double-counted.
        "gap_requests_lan1": _gap_requests_per_lan(client_rows,
                                                    per_lan.get(1, []), 1),
        "gap_requests_lan2": _gap_requests_per_lan(client_rows,
                                                    per_lan.get(2, []), 2),
    })

    event_admits = sum(1 for b in result["backends"] if b["admit_source"] == "event")
    if result["backends"]:
        result["event_fraction"] = event_admits / len(result["backends"])
    if (arm == "direct" and result["event_fraction"] is not None
            and result["event_fraction"] < _EVENT_FRACTION_GATE):
        result["event_fraction_degraded"] = True
    # Context flag: at least one backend's gap window degraded >= GAP_DELTA_PP
    # above its spike-phase baseline (interpretation only, per plan §2.7).
    result["degrading_gap"] = any(
        b["gap_delta_pp"] is not None and b["gap_delta_pp"] >= gap_delta_pp
        for b in result["backends"])
    return result


def _fmt(v) -> str:
    return "" if v is None else f"{v:.3f}"


def _summarize(run_dir: str, r: dict) -> None:
    print(f"\n=== {run_dir}  arm={r['arm']}  episode={r['episode']} "
          f"backends={r['backends_total']} (lan1={r['backends_lan1']}, "
          f"lan2={r['backends_lan2']})  void={r['void']} {r['void_reason']}")
    if not r["backends"]:
        print("  (no admitted compute backends)")
        return
    hdr = ("container", "lan", "src", "start->admit", "admit->1stflow", "dec->1stok",
           "gap_to", "gap_fr", "gap_delta_pp", "useful_share", "trans_to", "trans_fr",
           "p50", "p95", "p99", "gap_n")
    print("  " + "\t".join(hdr))
    for b in r["backends"]:
        print("  " + "\t".join([
            b["container"], str(b["lan"]), b["admit_source"][:8],
            _fmt(b["spawn_complete_to_admitted_s"]),
            _fmt(b["admitted_to_first_flow_s"]),
            _fmt(b["scale_decision_to_first_success_s"]),
            _fmt(b["gap_timeout_rate"]), _fmt(b["gap_failure_rate"]),
            _fmt(b["gap_delta_pp"]),
            "" if b["useful_initial_share"] is None
            else f"{b['useful_initial_share']:.3f}",
            _fmt(b["transition_timeout_rate"]), _fmt(b["transition_failure_rate"]),
            f"{b['transition_latency_p50']:.3f}", f"{b['transition_latency_p95']:.3f}",
            f"{b['transition_latency_p99']:.3f}", str(b["gap_requests"]),
        ]))
    print(f"  run-level medians: gap_timeout={_fmt(r['gap_timeout_rate_median'])} "
          f"gap_failure={_fmt(r['gap_failure_rate_median'])} "
          f"useful_share={_fmt(r['useful_share_median'])} "
          f"scale->1stok={_fmt(r['scale_to_first_success_median_s'])}s "
          f"start->admit={_fmt(r['spawn_to_admitted_median_s'])}s")
    if r["arm"] == "direct":
        print(f"  event_fraction={_fmt(r['event_fraction'])} "
              f"({'OK' if not r['event_fraction_degraded'] else 'INSTRUMENTATION-DEGRADED'})")


def _cross_arm(results: list[dict]) -> None:
    print("\n=== Cross-arm summary (run-level medians; primary = gap timeout_rate) ===")
    by_arm: dict[str, dict[str, list[float]]] = {}
    for r in results:
        if r["void"]:
            continue
        by_arm.setdefault(r["arm"], {})
        for key in ("gap_timeout_rate_median", "gap_failure_rate_median",
                    "useful_share_median", "spawn_to_admitted_median_s",
                    "scale_to_first_success_median_s"):
            v = r[key]
            if v is not None:
                by_arm[r["arm"]].setdefault(key, []).append(v)
    for arm in sorted(by_arm):
        d = by_arm[arm]
        n = len(d.get("gap_timeout_rate_median", []))
        print(f"  {arm}: runs={n}")
        for key in ("gap_timeout_rate_median", "gap_failure_rate_median",
                    "useful_share_median", "spawn_to_admitted_median_s",
                    "scale_to_first_success_median_s"):
            vals = d.get(key, [])
            if not vals:
                continue
            print(f"    {key}: n={len(vals)} mean={statistics.mean(vals):.4f} "
                  f"median={statistics.median(vals):.4f} "
                  f"min={min(vals):.4f} max={max(vals):.4f}")


def main() -> int:
    ap = argparse.ArgumentParser(description="RQ3 admission analysis (v2)")
    ap.add_argument("run_dirs", nargs="+", help="RQ3 run folder(s)")
    ap.add_argument("--transition-window-s", type=float, default=30.0,
                    help="useful-initial-share transition window (s)")
    ap.add_argument("--baseline-s", type=float, default=60.0,
                    help="spike-phase baseline window length (s)")
    ap.add_argument("--gap-delta-pp", type=float, default=5.0,
                    help="degrading-gap context flag threshold (pp)")
    ap.add_argument("--csv", help="optional per-run aggregated output CSV")
    args = ap.parse_args()

    results = []
    for run_dir in args.run_dirs:
        env = _parse_env(os.path.join(run_dir, "controller_env_snapshot.env"))
        arm = env.get("READINESS_PROPAGATION", "")
        if arm not in _RQ3_ARMS:
            print(f"SKIP {run_dir}: READINESS_PROPAGATION={arm!r} "
                  f"(not an RQ3 arm)", file=sys.stderr)
            continue
        r = _process_run(run_dir, args.transition_window_s, args.baseline_s,
                         args.gap_delta_pp)
        results.append(r)
        _summarize(run_dir, r)

    _cross_arm(results)

    if args.csv:
        cols = [
            "run_dir", "arm", "discovery_interval_s", "episode", "void",
            "void_reason", "backends_total", "backends_lan1", "backends_lan2",
            "gap_timeout_rate_median", "gap_failure_rate_median",
            "useful_share_median", "scale_to_first_success_median_s",
            "spawn_to_admitted_median_s", "admitted_to_first_flow_median_s",
            "transition_timeout_rate_median", "transition_failure_rate_median",
            "gap_requests_total", "gap_requests_lan1", "gap_requests_lan2",
            "event_fraction", "event_fraction_degraded",
            "degrading_gap",
        ]
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=cols)
            writer.writeheader()
            for r in results:
                writer.writerow({c: r.get(c, "") for c in cols})
        print(f"\nwrote per-run summary: {args.csv}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
