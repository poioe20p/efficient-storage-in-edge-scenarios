#!/usr/bin/env python3
"""control_run_trajectory.py — phase-wise node-count + signal snapshot for a
control-group run (resource_stats.csv).

Reports, per phase: window count, median T_db / T_proc (the avg_time_* columns
carry the aggregator MEDIAN), storage/server counts, and request volume. Used
to verify the control group exercises its mechanisms like the mean-era
envelope (storage adds ~4-5/LAN, in-window scale-down, bounded growth).

Usage:
    python3 tools/control_run_trajectory.py <resource_stats.csv>
"""

import csv
import sys
from collections import defaultdict


def q(vals, p):
    s = sorted(vals)
    return s[min(len(s) - 1, int(p * len(s)))]


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
    by = defaultdict(list)
    for r in rows:
        by[r.get("phase", "?")].append(r)

    order = ["baseline", "compute_plateau", "recovery_gap", "demand_drop"]
    print(f"{'phase':16s} {'n':>4s} {'reqs_p50':>8s} {'medTdb_p25':>10s} "
          f"{'medTdb_p50':>10s} {'medTdb_p75':>10s} {'medTdb_p90':>10s} "
          f"{'medTproc':>8s} {'st_p50':>6s} {'st_max':>6s} {'sv_p50':>6s} {'sv_max':>6s}")
    for ph in order + [k for k in sorted(by) if k not in order]:
        g = by.get(ph, [])
        if not g:
            continue
        reqs = [float(r["total_requests"]) for r in g if r.get("total_requests")]
        med_db = [float(r["avg_time_db_ms"]) for r in g if r.get("avg_time_db_ms")]
        med_proc = [float(r["avg_time_proc_ms"]) for r in g if r.get("avg_time_proc_ms")]
        st = [int(float(r["storage_count"])) for r in g if r.get("storage_count")]
        sv = [int(float(r["server_count"])) for r in g if r.get("server_count")]
        print(f"{ph:16s} {len(g):4d} {q(reqs, 0.5):8.0f} {q(med_db, 0.25):10.1f} "
              f"{q(med_db, 0.5):10.1f} {q(med_db, 0.75):10.1f} {q(med_db, 0.9):10.1f} "
              f"{q(med_proc, 0.5):8.1f} "
              f"{q(st, 0.5):6.1f} {max(st):6d} {q(sv, 0.5):6.1f} {max(sv):6d}")


if __name__ == "__main__":
    main()
