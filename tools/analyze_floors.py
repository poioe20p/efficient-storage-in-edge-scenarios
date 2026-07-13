"""Analyze C4 run artifacts to determine baseline vs stress CPU/latency metrics,
then compute degradation scores under current golden floors and proposed raised floors."""
import csv
import sys
import os

def stats(rows, phase, rel_min, rel_max, cols):
    matching = [r for r in rows if r.get('phase')==phase and rel_min <= float(r.get('relative_time',0)) <= rel_max]
    result = {}
    for col in cols:
        vals = [float(r[col]) for r in matching if r.get(col) and r[col].strip()]
        if vals:
            result[col] = {'min': min(vals), 'max': max(vals), 'avg': sum(vals)/len(vals), 'n': len(vals)}
    return result

def sat(x):
    return min(1.0, max(0.0, x))

run_dir = sys.argv[1] if len(sys.argv) > 1 else "source/scripts/testing/metrics/20260713_141638_cal_c4_both_tight"
csv_path = os.path.join(run_dir, "resource_stats.csv")

rows = []
with open(csv_path) as f:
    rows = list(csv.DictReader(f))

# ── Extract metrics ──
b = stats(rows, 'baseline', 0, 60, ['average_cpu_percent', 'avg_time_proc_ms', 'avg_storage_cpu_percent', 'avg_time_db_ms', 'p95_time_db_ms'])
s = stats(rows, 'storage_storm', 0, 60, ['avg_storage_cpu_percent', 'avg_time_db_ms', 'p95_time_db_ms'])
c = stats(rows, 'compute_spike', 0, 60, ['average_cpu_percent', 'avg_time_proc_ms'])

print("=== MEASURED METRICS (C4: STORAGE_CPUS=0.04, EDGE_CPUS=0.06) ===\n")

print("Baseline (0-60s, 1 req/s, 0% cross-region):")
for k,v in b.items():
    print(f"  {k}: avg={v['avg']:.1f}  min={v['min']:.1f}  max={v['max']:.1f}  n={v['n']}")

print("\nStorage_storm pre-scale (0-60s, 4 req/s, 90% cross-region):")
for k,v in s.items():
    print(f"  {k}: avg={v['avg']:.1f}  min={v['min']:.1f}  max={v['max']:.1f}  n={v['n']}")

print("\nCompute_spike pre-scale (0-60s, 4 req/s, feed_ranking=0.65):")
for k,v in c.items():
    print(f"  {k}: avg={v['avg']:.1f}  min={v['min']:.1f}  max={v['max']:.1f}  n={v['n']}")

print("\n\n=== SCORE ANALYSIS ===\n")

# ── Current golden floors ──
print("--- Current golden floors ---")
cpu_f, cpu_s = 3, 10
proc_f, proc_s = 15, 80
w_cpu, w_lat = 0.40, 0.60

baseline_comp = w_cpu * sat((b['average_cpu_percent']['avg']-cpu_f)/cpu_s) + w_lat * sat((b['avg_time_proc_ms']['avg']-proc_f)/proc_s)
stress_comp = w_cpu * sat((c['average_cpu_percent']['avg']-cpu_f)/cpu_s) + w_lat * sat((c['avg_time_proc_ms']['avg']-proc_f)/proc_s)
print(f"  Compute: bas={baseline_comp:.3f} stress={stress_comp:.3f} gap={stress_comp-baseline_comp:+.3f}")

scpu_f, scpu_s = 1.5, 5
tdb_f, tdb_s = 60, 250
w_scpu, w_tdb = 0.60, 0.40

baseline_tdb = b['avg_time_db_ms']['avg'] if b['avg_time_db_ms']['avg'] > 0 else 0
stress_tdb = s['avg_time_db_ms']['avg'] if s['avg_time_db_ms']['avg'] > 0 else 0
baseline_stor = w_scpu * sat((b['avg_storage_cpu_percent']['avg']-scpu_f)/scpu_s) + w_tdb * sat((baseline_tdb-tdb_f)/tdb_s)
stress_stor = w_scpu * sat((s['avg_storage_cpu_percent']['avg']-scpu_f)/scpu_s) + w_tdb * sat((stress_tdb-tdb_f)/tdb_s)
print(f"  Storage: bas={baseline_stor:.3f} stress={stress_stor:.3f} gap={stress_stor-baseline_stor:+.3f}")

# ── Proposed raised floors ──
print("\n--- Proposed raised floors ---")
# Compute: floor raised so baseline CPU gives partial score
for (cf, cs) in [(25, 20), (30, 20), (35, 25), (40, 30)]:
    bl = w_cpu * sat((b['average_cpu_percent']['avg']-cf)/cs) + w_lat * sat((b['avg_time_proc_ms']['avg']-proc_f)/proc_s)
    st = w_cpu * sat((c['average_cpu_percent']['avg']-cf)/cs) + w_lat * sat((c['avg_time_proc_ms']['avg']-proc_f)/proc_s)
    print(f"  Compute floor={cf} span={cs}: bas={bl:.3f} stress={st:.3f} gap={st-bl:+.3f}")

print()
# Storage: floor raised so baseline CPU gives partial score
for (sf, ss) in [(25, 10), (30, 10), (35, 15), (40, 20)]:
    bl = w_scpu * sat((b['avg_storage_cpu_percent']['avg']-sf)/ss) + w_tdb * sat((baseline_tdb-tdb_f)/tdb_s)
    st = w_scpu * sat((s['avg_storage_cpu_percent']['avg']-sf)/ss) + w_tdb * sat((stress_tdb-tdb_f)/tdb_s)
    print(f"  Storage floor={sf} span={ss}: bas={bl:.3f} stress={st:.3f} gap={st-bl:+.3f}")
