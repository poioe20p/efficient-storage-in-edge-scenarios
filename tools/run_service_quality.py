#!/usr/bin/env python3
"""run_service_quality.py — service-quality snapshot for a completed run.

Reads client_requests.csv and reports, per phase: request count, error %,
p50/p95/p99 latency (successful), and per-endpoint error % (control-group
validation: scalable error% <= ~3%, p50/p95 well below no-scale).

Usage:
    python3 tools/run_service_quality.py <client_requests.csv>
"""

import csv
import statistics
import sys
from collections import defaultdict


def pct(vals, q):
    s = sorted(vals)
    return s[min(len(s) - 1, int(q * len(s)))]


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    by_phase = defaultdict(list)
    total = 0
    with open(sys.argv[1], encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            total += 1
            phase = row.get("phase", "?")
            try:
                status = int(row["http_status"])
                lat = float(row["latency_s"])
            except (ValueError, KeyError):
                continue
            err = status >= 400 or status == 0
            by_phase[phase].append((err, lat, row.get("endpoint", "")))

    print(f"total requests: {total}\n")
    order = ["baseline", "compute_plateau", "recovery_gap", "demand_drop"]
    print(f"{'phase':16s} {'n':>7s} {'err%':>7s} {'p50_s':>7s} {'p95_s':>7s} "
          f"{'p99_s':>7s} {'mean_s':>7s}")
    for ph in order + [k for k in sorted(by_phase) if k not in order]:
        g = by_phase.get(ph, [])
        if not g:
            continue
        n = len(g)
        errs = sum(1 for e, _, _ in g if e)
        lats = [lat for e, lat, _ in g if not e]
        if lats:
            print(f"{ph:16s} {n:7d} {100.0*errs/n:7.2f} {pct(lats, 0.5):7.3f} "
                  f"{pct(lats, 0.95):7.3f} {pct(lats, 0.99):7.3f} "
                  f"{statistics.mean(lats):7.3f}")
        else:
            print(f"{ph:16s} {n:7d} {100.0*errs/n:7.2f} {'-':>7s} {'-':>7s} "
                  f"{'-':>7s} {'-':>7s}")

    # endpoint error breakdown (plateau, the loaded phase)
    ep = defaultdict(lambda: [0, 0])
    for e, _, endpoint in by_phase.get("compute_plateau", []):
        ep[endpoint][1] += 1
        if e:
            ep[endpoint][0] += 1
    print(f"\nplateau per-endpoint error%:")
    for k, (errs, n) in sorted(ep.items(), key=lambda kv: -kv[1][1]):
        print(f"  {k:22s} n={n:6d} err%={100.0*errs/n:6.2f}")


if __name__ == "__main__":
    main()
