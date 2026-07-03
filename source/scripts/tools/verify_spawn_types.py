import csv, os, glob, json
from collections import Counter

base = "source/scripts/testing/metrics"

# Get decision_quality for all runs - show ALL phases, not just storage_storm
pattern = os.path.join(base, "*v2final*", "analysis", "rq1", "rq1_decision_quality.csv")
files = sorted(glob.glob(pattern))

# Pick one representative run (push_1)
for f in files:
    if "push_1" in f:
        print("=== Full decision_quality for push_1 ===")
        rows = list(csv.DictReader(open(f)))
        print(f"{'phase':<30s} {'breached':>8s} {'spawns':>7s} {'peak':>7s}")
        print("-" * 58)
        for r in rows:
            print(f"{r['phase']:<30s} {r['breached_windows']:>8s} {r['spawns_initiated']:>7s} {r['peak_score']:>7s}")
        break

# Now check container_events.csv for the actual spawn types
print("\n=== Container spawns by type (push_1, storage_storm phase) ===")
for d in os.listdir(base):
    if "push_1" in d:
        ce_path = os.path.join(base, d, "container_events.csv")
        if os.path.exists(ce_path):
            rows = list(csv.DictReader(open(ce_path)))
            # Get phases from phases_snapshot
            ps_path = os.path.join(base, d, "phases_snapshot.json")
            phases = []
            if os.path.exists(ps_path):
                phases_data = json.load(open(ps_path))
                t = 0
                for p in phases_data["phases"]:
                    phases.append((p["name"], t, t + p["duration_s"]))
                    t += p["duration_s"]
            
            # Filter storage_storm phase
            storm_start = None
            storm_end = None
            for name, start, end in phases:
                if name == "storage_storm":
                    storm_start = start
                    storm_end = end
                    break
            
            if storm_start is not None:
                storm_events = [
                    r for r in rows 
                    if r.get("event","").lower() == "added" 
                    and storm_start <= float(r.get("timestamp_s", 0)) <= storm_end
                ]
                types = Counter(r.get("container_type", "?") for r in storm_events)
                print(f"  storage_storm phase: {storm_start}-{storm_end}s")
                print(f"  Total added events: {len(storm_events)}")
                for t, c in sorted(types.items()):
                    print(f"    {t}: {c}")
        break
