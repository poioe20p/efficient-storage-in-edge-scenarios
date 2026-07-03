import csv, os, sys
from collections import Counter

base = "source/scripts/testing/metrics"
runs_info = [
    ("rq1_v2final_push_1", 12.57),
    ("rq1_v2final_push_2", 12.95),
    ("rq1_v2final_push_3", 60.63),
    ("rq1_v2final_poll5_1", 1.37),
    ("rq1_v2final_poll5_2", 13.82),
    ("rq1_v2final_poll5_3", 8.98),
    ("rq1_v2final_poll12_1", 1.74),
    ("rq1_v2final_poll12_2", 15.73),
    ("rq1_v2final_poll12_3", 1.92),
    ("rq1_v2final_poll30_1", 17.05),
    ("rq1_v2final_poll30_2", 1.58),
    ("rq1_v2final_poll30_3", 43.39),
]

for rname, rate in runs_info:
    for d in os.listdir(base):
        if rname in d:
            rpath = os.path.join(base, d, "resource_stats.csv")
            if not os.path.exists(rpath):
                print(f"{rname}: NO resource_stats.csv")
                continue
            rows = list(csv.DictReader(open(rpath)))
            # Get min/max storage and compute counts
            storage_vals = [int(r["storage_count"]) for r in rows if r.get("storage_count","").isdigit()]
            compute_vals = [int(r["server_count"]) for r in rows if r.get("server_count","").isdigit()]
            tier1_vals = [int(r["tier1_lifecycle_active_count"]) for r in rows if r.get("tier1_lifecycle_active_count","").isdigit()]
            
            # Count scale events
            storage_changes = sum(1 for i in range(1, len(storage_vals)) if storage_vals[i] != storage_vals[i-1])
            compute_changes = sum(1 for i in range(1, len(compute_vals)) if compute_vals[i] != compute_vals[i-1])
            
            print(f"{rname:<30s} fail={rate:>5.1f}%  "
                  f"storage: {min(storage_vals)}-{max(storage_vals)} ({storage_changes} changes)  "
                  f"compute: {min(compute_vals)}-{max(compute_vals)} ({compute_changes} changes)  "
                  f"tier1_max={max(tier1_vals) if tier1_vals else 0}")
            break
