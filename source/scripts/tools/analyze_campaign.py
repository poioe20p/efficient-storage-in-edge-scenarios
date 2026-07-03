#!/usr/bin/env python3
"""Quick campaign analysis: per-phase failure rates for all runs."""
import csv, os, glob

base = os.path.expanduser('~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics')
runs = sorted(glob.glob(os.path.join(base, '*rq1_v2final_*')))
phases_order = ['baseline','storage_storm','tier1_hotspot','inter_hotspot_cooldown','reverse_hotspot','compute_spike','demand_drop']

for run_dir in runs:
    label = os.path.basename(run_dir)
    parts = label.split('_', 2)
    if len(parts) >= 3:
        label = parts[2]
    
    cr_file = os.path.join(run_dir, 'client_requests.csv')
    if not os.path.exists(cr_file):
        print(f'{label}: NO client_requests.csv')
        continue
    
    total = 0; failed = 0
    phase_counts = {}; phase_fails = {}
    with open(cr_file) as f:
        for row in csv.DictReader(f):
            total += 1
            ph = row.get('phase','?')
            phase_counts[ph] = phase_counts.get(ph,0) + 1
            if row.get('http_status','200') not in ('200','201','204','301','302','304'):
                failed += 1
                phase_fails[ph] = phase_fails.get(ph,0) + 1
    
    rate = failed/total*100 if total else 0
    parts_list = []
    for ph in phases_order:
        pc = phase_counts.get(ph, 0)
        pf = phase_fails.get(ph, 0)
        pr = pf/pc*100 if pc else 0
        parts_list.append(f'{ph}={pr:.1f}%')
    
    print(f'{label:35s}: {total:6d} reqs, {failed:4d} fails ({rate:5.1f}%)')
    print(f'  {" | ".join(parts_list)}')
