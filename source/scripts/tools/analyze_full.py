#!/usr/bin/env python3
"""Full campaign analysis: per-phase failure, latency percentiles, resource stats."""
import csv, os, glob

base = os.path.expanduser('~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics')
runs = sorted(glob.glob(os.path.join(base, '*rq1_v2final_*')))
phases_order = ['baseline','storage_storm','tier1_hotspot','inter_hotspot_cooldown','reverse_hotspot','compute_spike','demand_drop']

print('=' * 100)
print(f'{"Run":35s} {"Reqs":>6s} {"Fail%":>6s} {"p50s":>6s} {"p95s":>6s} {"p99s":>6s} {"StorMax":>7s} {"SrvMax":>6s} {"T1Win":>5s}')
print('-' * 100)

for run_dir in runs:
    label = os.path.basename(run_dir)
    parts = label.split('_', 2)
    if len(parts) >= 3:
        label = parts[2]
    
    cr_file = os.path.join(run_dir, 'client_requests.csv')
    if not os.path.exists(cr_file):
        continue
    
    total = 0; failed = 0
    phase_counts = {}; phase_fails = {}
    ok_latencies = []
    
    with open(cr_file) as f:
        for row in csv.DictReader(f):
            total += 1
            ph = row.get('phase','?')
            phase_counts[ph] = phase_counts.get(ph,0) + 1
            status = row.get('http_status','200')
            if status not in ('200','201','204','301','302','304'):
                failed += 1
                phase_fails[ph] = phase_fails.get(ph,0) + 1
            else:
                try:
                    lat = float(row.get('latency_s', 0))
                    if lat > 0 and lat < 60:  # reasonable bound
                        ok_latencies.append(lat)
                except:
                    pass
    
    rate = failed/total*100 if total else 0
    
    # Latency percentiles
    p50 = p95 = p99 = 0
    if ok_latencies:
        ok_latencies.sort()
        n = len(ok_latencies)
        p50 = ok_latencies[int(n*0.50)]
        p95 = ok_latencies[min(int(n*0.95), n-1)]
        p99 = ok_latencies[min(int(n*0.99), n-1)]
    
    # Resource stats
    rs_file = os.path.join(run_dir, 'resource_stats.csv')
    storage_max = server_max = t1_win = 0
    if os.path.exists(rs_file):
        storage_counts = []; server_counts = []; tier1_counts = []
        with open(rs_file) as f:
            for row in csv.DictReader(f):
                try:
                    storage_counts.append(int(row.get('storage_count', 0)))
                    server_counts.append(int(row.get('server_count', 0)))
                    tier1_counts.append(int(row.get('tier1_lifecycle_active_count', 0)))
                except:
                    pass
        storage_max = max(storage_counts) if storage_counts else 0
        server_max = max(server_counts) if server_counts else 0
        t1_win = sum(1 for v in tier1_counts if v > 0) if tier1_counts else 0
    
    print(f'{label:35s} {total:6d} {rate:6.1f}% {p50:6.1f} {p95:6.1f} {p99:6.1f} {storage_max:7d} {server_max:6d} {t1_win:5d}')

print('=' * 100)

# Per-mode summaries
print('\n--- Per-Mode Summary ---')
modes = {'push': [], 'poll5': [], 'poll12': [], 'poll30': []}
for run_dir in runs:
    label = os.path.basename(run_dir)
    cr_file = os.path.join(run_dir, 'client_requests.csv')
    if not os.path.exists(cr_file):
        continue
    total = 0; failed = 0
    with open(cr_file) as f:
        for row in csv.DictReader(f):
            total += 1
            if row.get('http_status','200') not in ('200','201','204','301','302','304'):
                failed += 1
    rate = failed/total*100 if total else 0
    if '_push_' in label: modes['push'].append(rate)
    elif '_poll5_' in label: modes['poll5'].append(rate)
    elif '_poll12_' in label: modes['poll12'].append(rate)
    elif '_poll30_' in label: modes['poll30'].append(rate)

for mode, rates in modes.items():
    if rates:
        mu = sum(rates)/len(rates)
        rate_strs = [f'{r:.1f}%' for r in rates]
        print(f'{mode}: rates={rate_strs}, mean={mu:.1f}%')
