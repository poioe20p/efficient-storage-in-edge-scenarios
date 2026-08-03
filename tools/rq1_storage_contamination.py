"""RQ1 storage-signal contamination check.

Determines whether RQ1 storage scale-up decisions were driven by genuine DB
pressure (high request volume + sustained T_db) or by the same mean-latency
outlier contamination found in RQ2 (low-request windows where one slow request
inflates the mean).

RQ1 runs lack median_time_db_ms in their artifacts, so this uses request
volume as the proxy: RQ2's contamination occurred in low-request transition
windows (8-21 reqs). If RQ1's storage triggers coincide with high-request
windows carrying genuinely elevated avg_time_db_ms, the decisions were real.

Usage:
  python tools/rq1_storage_contamination.py <run_folder> [<run_folder>...]
Each folder must contain policy_state.csv and resource_stats.csv.
"""
from __future__ import annotations

import csv
import statistics
import sys


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def analyze(folder: str) -> None:
    ps = list(csv.DictReader(open(f"{folder}/policy_state.csv")))
    rs = list(csv.DictReader(open(f"{folder}/resource_stats.csv")))
    rsd = {}
    for r in rs:
        try:
            rsd[float(r["window_end"])] = r
        except (KeyError, ValueError):
            pass

    def near(ts: float):
        for we, r in rsd.items():
            if abs(we - ts) < 6:
                return r
        return None

    from collections import Counter

    print(f"== {folder} ==")
    for col in ("storage_triggered", "storage_candidate_selected", "storage_above_threshold",
                "compute_triggered", "compute_candidate_selected"):
        c = Counter((r.get(col, "") or "").lower() for r in ps)
        print(f"  {col}: {dict(c)}")

    trig = [
        r for r in ps
        if (r.get("storage_triggered") or "").lower() == "true"
        or (r.get("storage_candidate_selected") or "").lower() == "true"
    ]
    print(f"  storage actions: {len(trig)}")
    for r in trig[:15]:
        rsr = near(_f(r["window_end"]))
        reqs = rsr["total_requests"] if rsr else "?"
        avgb = rsr["avg_time_db_ms"] if rsr else "?"
        print(
            f"    phase={r['phase']:<20} signal={_f(r['storage_latency_signal_ms']):8.1f}ms "
            f"dyn={r['dynamic_storage_count']} reqs={reqs} avgTdb={avgb}"
        )

    print("  --- storage signal by request volume (non-baseline) ---")
    sig_rs = {}  # policy_state signal per window_end
    for r in ps:
        try:
            sig_rs[float(r["window_end"])] = _f(r["storage_latency_signal_ms"])
        except (KeyError, ValueError):
            pass
    low, mid, high = [], [], []
    for r in rs:
        we = _f(r["window_end"])
        sig = sig_rs.get(we)
        if sig is None:
            continue
        reqs = _f(r["total_requests"])
        if reqs < 50 and r["phase"] != "baseline":
            low.append(sig)
        elif 50 <= reqs < 200:
            mid.append(sig)
        elif reqs >= 200:
            high.append(sig)
    for name, vals in (("low-req(<50)", low), ("mid(50-200)", mid), ("high(>=200)", high)):
        if vals:
            print(
                f"    {name:<14} n={len(vals)} median={statistics.median(vals):.1f} "
                f"mean={statistics.mean(vals):.1f} max={max(vals):.1f}"
            )
    print()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    for f in sys.argv[1:]:
        analyze(f)
