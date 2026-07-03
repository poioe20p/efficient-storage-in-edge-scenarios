import csv, os, glob

base = "source/scripts/testing/metrics"
pattern = os.path.join(base, "*v2final*", "analysis", "rq1", "rq1_decision_quality.csv")
files = sorted(glob.glob(pattern))

print(f"{'Run':<35s} {'breached':>8s} {'spawns':>7s} {'peak':>7s} {'windows':>8s}")
print("-" * 70)
for f in files:
    # Extract run name from path
    parts = f.split(os.sep)
    run_dir = parts[3]  # e.g., 20260703_004628_rq1_v2final_push_1
    run_label = run_dir.split("_", 3)[-1] if "_" in run_dir else run_dir  # rq1_v2final_push_1
    
    rows = list(csv.DictReader(open(f)))
    storm = [r for r in rows if r["phase"] == "storage_storm"]
    if storm:
        s = storm[0]
        print(f"{run_label:<35s} {s['breached_windows']:>8s} {s['spawns_initiated']:>7s} {s['peak_score']:>7s} {s['total_windows']:>8s}")
