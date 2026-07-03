import csv, os
from datetime import datetime
from collections import Counter

base = "source/scripts/testing/metrics"

# Compare per-node stats between healthy and degraded
pairs = [("push_1", "poll5_1"), ("push_3", "poll30_2")]

for degraded, healthy in pairs:
    print(f"\n=== {degraded} (degraded) vs {healthy} (healthy) ===")
    for target in [degraded, healthy]:
        for d in os.listdir(base):
            if target in d:
                pn_path = os.path.join(base, d, "per_node_stats.csv")
                if not os.path.exists(pn_path):
                    print(f"  {target}: NO per_node_stats.csv")
                    continue
                rows = list(csv.DictReader(open(pn_path)))
                
                # Check which columns exist
                if rows:
                    cols = list(rows[0].keys())
                    # Filter to storage_storm phase
                    storm_rows = [r for r in rows if r.get("phase") == "storage_storm"]
                    if storm_rows:
                        # Get unique containers
                        containers = set(r.get("container","?") for r in storm_rows)
                        print(f"  {target}: {len(storm_rows)} per-node rows, {len(containers)} unique containers during storage_storm")
                        
                        # Check for any containers with high CPU or latency
                        for r in storm_rows[:3]:
                            cpu = r.get("cpu_percent", "?")
                            lat = r.get("avg_time_db_ms", "?")
                            name = r.get("container", "?")
                            print(f"    {name}: cpu={cpu}%, db_lat={lat}ms")
                break
