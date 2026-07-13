"""Compare storage CPU across all Phase 1a calibration runs."""
import csv, os

base = 'source/scripts/testing/metrics'
runs = [
    ('C0_golden (0.25/0.25)', '20260713_111331_cal_c0_golden'),
    ('C1_stor006 (0.06/0.25)', '20260713_120450_cal_c1_stor_006'),
    ('C2_edge008 (0.25/0.08)', '20260713_124454_cal_c2_edge_008'),
    ('C3_both_mod (0.08/0.10)', '20260713_132905_cal_c3_both_mod'),
    ('C4_both_tight (0.04/0.06)', '20260713_141638_cal_c4_both_tight'),
]

for label, folder in runs:
    p = os.path.join(base, folder, 'resource_stats.csv')
    rows = list(csv.DictReader(open(p)))
    print(f'--- {label} ---')
    for phase in ['baseline', 'storage_storm', 'compute_spike']:
        match = [float(r['avg_storage_cpu_percent']) for r in rows
                 if r.get('phase')==phase
                 and 0<=float(r.get('relative_time',0))<=60
                 and r.get('avg_storage_cpu_percent')
                 and r['avg_storage_cpu_percent'].strip()]
        if match:
            a = sum(match)/len(match)
            edge_match = [float(r['average_cpu_percent']) for r in rows
                          if r.get('phase')==phase
                          and 0<=float(r.get('relative_time',0))<=60
                          and r.get('average_cpu_percent')
                          and r['average_cpu_percent'].strip()]
            edge_avg = sum(edge_match)/len(edge_match) if edge_match else 0
            print(f'  {phase:15s}  stor_cpu={a:5.1f}%  edge_cpu={edge_avg:5.1f}%  n={len(match)}')
    print()
