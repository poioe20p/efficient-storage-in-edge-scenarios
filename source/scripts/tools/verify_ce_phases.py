import csv, os, json

base = "source/scripts/testing/metrics"

for d in os.listdir(base):
    if "push_1" in d:
        ce_path = os.path.join(base, d, "container_events.csv")
        if not os.path.exists(ce_path):
            print("NO container_events.csv")
            continue
        
        rows = list(csv.DictReader(open(ce_path)))
        
        # Get phases
        ps_path = os.path.join(base, d, "phases_snapshot.json")
        phases = []
        if os.path.exists(ps_path):
            phases_data = json.load(open(ps_path))
            t = 0
            for p in phases_data["phases"]:
                phases.append((p["name"], t, t + p["duration_s"]))
                t += p["duration_s"]
        
        print("=== Phase boundaries ===")
        for name, start, end in phases:
            print(f"  {name}: {start}-{end}s")
        
        print("\n=== All 'added' events with timestamps ===")
        added = [r for r in rows if r.get("event","").lower() == "added"]
        for r in added:
            ts = float(r.get("timestamp_s", 0))
            # Determine phase
            ph = "unknown"
            for name, start, end in phases:
                if start <= ts <= end:
                    ph = name
                    break
            print(f"  ts={ts:>8.1f}s  phase_col={r.get('phase','?'):<25s}  actual_phase={ph:<25s}  type={r.get('container_type','?')}")
        
        print(f"\n  Total added events: {len(added)}")
        
        # Show unique phase values in the column
        from collections import Counter
        phase_col_values = Counter(r.get("phase","?") for r in added)
        print(f"  Phase column values: {dict(phase_col_values)}")
        break
