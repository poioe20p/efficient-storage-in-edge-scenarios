import csv, os
from datetime import datetime

base = "source/scripts/testing/metrics"

# Compare controller CPU: push_1 (degraded) vs poll5_1 (healthy)
pairs = [("push_1", "poll5_1"), ("push_3", "poll30_2")]

for degraded, healthy in pairs:
    print(f"\n=== Controller CPU: {degraded} (degraded) vs {healthy} (healthy) ===")
    for target in [degraded, healthy]:
        for d in os.listdir(base):
            if target in d:
                cs_path = os.path.join(base, d, "controller_stats.csv")
                if not os.path.exists(cs_path):
                    print(f"  {target}: NO controller_stats.csv")
                    continue
                rows = list(csv.DictReader(open(cs_path)))
                if not rows:
                    print(f"  {target}: empty controller_stats.csv")
                    continue
                
                cpus = []
                mems = []
                for r in rows:
                    try:
                        cpu = float(r.get("cpu_percent", 0))
                        mem = float(r.get("mem_usage_mb", 0))
                        cpus.append(cpu)
                        mems.append(mem)
                    except (ValueError, TypeError):
                        pass
                
                if cpus:
                    cpus_sorted = sorted(cpus)
                    n = len(cpus_sorted)
                    print(f"  {target}: {n} samples, "
                          f"cpu: min={min(cpus):.1f}% p50={cpus_sorted[n//2]:.1f}% "
                          f"p95={cpus_sorted[int(n*0.95)]:.1f}% max={max(cpus):.1f}%, "
                          f"mem: min={min(mems):.0f}MB p50={sorted(mems)[n//2]:.0f}MB max={max(mems):.0f}MB")
                break
