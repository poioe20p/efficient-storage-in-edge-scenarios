#!/usr/bin/env python3
"""rq1v2_p4_01_lan2_asymmetry.py — Arm C lan2 plateau asymmetry investigation.

RQ1 v1 found a run-invariant Arm C (poll) lan2 plateau failure asymmetry
(11-12% lan2 vs 2-4% lan1) with no analogue in A/B. This script investigates
whether it reproduces under the v2 open-loop campaign and looks for its cause:

Per analyzed run, per arm:
  - plateau failure_rate and timeout_rate per LAN (phase_service_quality.csv);
  - plateau offered requests per LAN (load distribution — is lan2 offered more?);
  - per-backend request counts (client_requests.csv `backend_id`) per LAN
    (VIP routing balance — is one backend saturated?);
  - delivered-window counts per LAN (telemetry_delivery_log_lan{1,2}.csv)
    (poll delivery fairness — does lan2 lose more windows?).

Aggregates across replicates per arm and emits a verdict:
  ASYMMETRIC  — median |lan2 - lan1| > threshold (2 pp) on failure or
                timeout rate AND the sign holds in >= 60% of runs with a
                defined delta (min 2)
  BALANCED    — no such systematic per-LAN difference
  INCONSISTENT — large per-run deltas but mixed sign
  INSUFFICIENT DATA — no runs with defined rates

Output: ``lan2_asymmetry.csv`` (per run + per arm summary) and a console
verdict. Pre-flight usage: run against the open-loop G2 calibration runs to
check whether the asymmetry reproduces before blocks start; full analysis
after the campaign.

Usage:
    python3 docs/operation/testing/experiment/v2/rq1/rq1v2_p4_01_lan2_asymmetry.py \
        --run-dirs-ep "..." --run-dirs-delayed "..." \
        --run-dirs-ls "..." --run-dirs-sp "..." \
        [--output lan2_asymmetry.csv]
"""

from __future__ import annotations

import argparse
import csv
import math
import os
import sys

ANALYSIS_SUBDIR = os.path.join("analysis", "rq1_delivery")
ARMS = ("ep", "delayed", "ls", "sp")
ARM_LABELS = {"ep": "A ep", "delayed": "B delayed", "ls": "C ls", "sp": "D sp"}
THRESHOLD_PP = 2.0                 # |lan2 - lan1| percentage points


def _load_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _f(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _parse_run_dirs(values):
    out = []
    for v in values or []:
        out.extend(v.split())
    result = []
    for p in out:
        if os.path.isdir(p):
            result.append(os.path.abspath(p))
        else:
            print(f"[warn] run folder not found (dropped): {p}")
    return result


def _run_rows(run_dir):
    """Per-run per-LAN plateau rates + load distribution + delivery counts."""
    ad = os.path.join(run_dir, ANALYSIS_SUBDIR)
    sq = _load_rows(os.path.join(ad, "phase_service_quality.csv"))
    plateau = {r["network_id"]: r for r in sq
               if (r.get("phase") or "").strip() == "compute_plateau"}
    # Rates are read directly from the analyzer output (the canonical values).
    # The open-loop driver has no literal `status` column, so the analyzer
    # writes failure_rate over `offered` (legacy denominator) and leaves
    # timeout_rate blank — blank cells parse to None, never a fabricated 0.
    # Legacy v1 folders have blank status columns too; same handling applies
    # (their archived rates stay v1-convention). Recomputing from the raw CSV
    # would require re-implementing the analyzer's outcome contract, so we do
    # not do that here.
    out = {}
    for lan in ("lan1", "lan2"):
        r = plateau.get(lan, {})
        offered = int(r.get("offered") or 0)
        out[f"{lan}_offered"] = offered
        out[f"{lan}_failure_rate"] = _f(r.get("failure_rate"))
        out[f"{lan}_timeout_rate"] = _f(r.get("timeout_rate"))
    # Delivery counts per LAN (poll delivery fairness / loss asymmetry),
    # deduped by window_id like the analyzer.
    for lan in ("lan1", "lan2"):
        dl = _load_rows(os.path.join(run_dir, f"telemetry_delivery_log_{lan}.csv"))
        out[f"{lan}_delivered"] = len(
            {(x.get("window_id") or "").strip() for x in dl
             if (x.get("window_id") or "").strip()})
    # Load distribution: plateau requests per backend per LAN (client_requests).
    req = _load_rows(os.path.join(run_dir, "client_requests.csv"))
    per_backend = {"lan1": {}, "lan2": {}}
    for x in req:
        if (x.get("phase") or "").strip() != "compute_plateau":
            continue
        lan = (x.get("client_lan") or "").strip()
        if lan not in per_backend:
            continue
        bid = (x.get("backend_id") or "").strip() or "unknown"
        per_backend[lan][bid] = per_backend[lan].get(bid, 0) + 1
    out["per_backend_lan1"] = per_backend["lan1"]
    out["per_backend_lan2"] = per_backend["lan2"]
    return out


def _verdict(rows, metric):
    """(median_delta_pp, n_defined, consistent, verdict) for one metric.

    ASYMMETRIC requires |median of the SIGNED (lan2 - lan1) deltas| >
    threshold AND the sign to hold in >= 60%% of NON-ZERO deltas (min 2). The
    median is robust to a couple of outlier runs; a single run cannot be a
    pattern."""
    deltas = []
    for r in rows:
        a, b = _f(r.get(f"lan1_{metric}")), _f(r.get(f"lan2_{metric}"))
        if a is not None and b is not None:
            deltas.append((b - a) * 100.0)      # lan2 minus lan1, in pp
    n = len(deltas)
    if n == 0:
        return None, 0, False, "INSUFFICIENT DATA (no defined rates)"
    s = sorted(deltas)
    mid = n // 2
    median_delta = s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2.0
    nonzero = [d for d in deltas if d != 0]
    same_sign = sum(1 for d in nonzero if (d > 0) == (median_delta > 0))
    consistent = (len(nonzero) >= 2
                  and same_sign >= max(2, math.ceil(0.6 * len(nonzero))))
    if n == 1:
        return median_delta, n, False, "BALANCED (single run — not a pattern)"
    if abs(median_delta) > THRESHOLD_PP and consistent:
        return median_delta, n, consistent, "ASYMMETRIC"
    if abs(median_delta) > THRESHOLD_PP:
        return median_delta, n, consistent, "INCONSISTENT (large but mixed-sign)"
    return median_delta, n, consistent, "BALANCED"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    for arm in ARMS:
        ap.add_argument(f"--run-dirs-{arm}", action="append", default=[],
                        metavar="DIR", help=f"{ARM_LABELS[arm]} run folders")
    ap.add_argument("--output", default="lan2_asymmetry.csv",
                    help="output CSV (default: lan2_asymmetry.csv)")
    args = ap.parse_args()

    rows = []
    for arm in ARMS:
        for rd in _parse_run_dirs(getattr(args, f"run_dirs_{arm}")):
            if not os.path.isdir(os.path.join(rd, ANALYSIS_SUBDIR)):
                print(f"[warn] {arm}: no analysis/ subdir — dropped: {rd}")
                continue
            m = _run_rows(rd)
            m["arm"] = arm
            m["run"] = os.path.basename(rd)
            rows.append(m)

    if not rows:
        sys.stderr.write("ERROR: no valid analyzed run folders supplied.\n")
        return 2

    summary = []
    print("\nRQ1 v2 lan2-asymmetry investigation")
    for arm in ARMS:
        arm_rows = [r for r in rows if r["arm"] == arm]
        if not arm_rows:
            continue
        print(f"\n  {ARM_LABELS[arm]} — {len(arm_rows)} run(s)")
        for metric, label in (("failure_rate", "plateau failure rate"),
                              ("timeout_rate", "plateau timeout rate")):
            delta, defined, _consistent, verdict = _verdict(arm_rows, metric)
            if delta is None:
                print(f"    {label:<22} {verdict}")
            else:
                print(f"    {label:<22} lan2-lan1 median {delta:+.2f} pp "
                      f"({defined} runs with defined rates) -> {verdict}")
            summary.append({"arm": arm, "metric": metric,
                            "delta_pp": (f"{delta:.2f}"
                                          if delta is not None else ""),
                            "n_runs": defined, "verdict": verdict})

        # Delivery-fairness check: delivered-window counts per LAN (poll loss
        # asymmetry), written to the CSV and printed.
        dl = {"lan1": 0, "lan2": 0}
        for r in arm_rows:
            for lan in ("lan1", "lan2"):
                dl[lan] += int(r.get(f"{lan}_delivered") or 0)
        if dl["lan1"] or dl["lan2"]:
            print(f"    delivered windows lan1={dl['lan1']} lan2={dl['lan2']}")
            for lan in ("lan1", "lan2"):
                summary.append({"arm": arm, "metric": f"delivered_{lan}",
                                "delta_pp": str(dl[lan]),
                                "n_runs": len(arm_rows), "verdict": "count"})

        # Load-distribution check (informational): total offered per LAN and
        # per-backend balance.
        tot = {"lan1": 0, "lan2": 0}
        backends = {"lan1": {}, "lan2": {}}
        for r in arm_rows:
            for lan in ("lan1", "lan2"):
                tot[lan] += int(r.get(f"{lan}_offered") or 0)
                for bid, cnt in r.get(f"per_backend_{lan}", {}).items():
                    backends[lan][bid] = backends[lan].get(bid, 0) + cnt
        if tot["lan1"] or tot["lan2"]:
            ratio = (f"{tot['lan2'] / tot['lan1']:.2f}"
                     if tot["lan1"] > 0 else "n/a")
            print(f"    offered lan1={tot['lan1']} lan2={tot['lan2']} "
                  f"(ratio {ratio})")
        for lan in ("lan1", "lan2"):
            if backends[lan]:
                entries = sorted(backends[lan].items(),
                                 key=lambda kv: -kv[1])[:3]
                print(f"    {lan} top backends: "
                      + ", ".join(f"{k}={v}" for k, v in entries))

    cols = ["arm", "metric", "delta_pp", "n_runs", "verdict"]
    with open(args.output, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summary)
    print(f"\n  wrote {args.output} ({len(summary)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
