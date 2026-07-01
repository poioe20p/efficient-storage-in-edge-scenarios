"""Latency validation for v5 runs."""
import csv, os

base = os.path.join("source", "scripts", "testing", "metrics")
runs = [
    ("v5 A", "_v5a_cr.csv"),
    ("v5 B", "_v5b_cr.csv"),
    ("v5 C", "_v5c_cr.csv"),
    ("v5 D", "_v5d_cr.csv"),
]

for label, f in runs:
    rows = list(csv.DictReader(open(os.path.join(base, f))))
    # Per-phase latency
    from collections import defaultdict
    phase_lats = defaultdict(list)
    for r in rows:
        try:
            lat = float(r.get("latency_s", 0) or 0)
            if lat > 0:
                phase_lats[r["phase"]].append(lat * 1000)
        except (ValueError, TypeError):
            pass

    print(f"--- {label} ---")
    for phase in sorted(phase_lats.keys()):
        lats = sorted(phase_lats[phase])
        n = len(lats)
        if n > 0:
            print(f"  {phase:30s} n={n:>6} mean={sum(lats)/n:7.0f}ms median={lats[n//2]:7.0f}ms p95={lats[int(n*0.95)]:7.0f}ms p99={lats[int(n*0.99)]:7.0f}ms")
    print()
