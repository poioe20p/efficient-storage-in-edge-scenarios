#!/usr/bin/env python3
"""Extract latency percentiles and resource stats for all runs."""
import csv, os, glob, json

base = os.path.expanduser('~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics')
runs = sorted(glob.glob(os.path.join(base, '*rq1_v2final_*')))

for run_dir in runs:
    label = os.path.basename(run_dir)
    parts = label.split('_', 2)
    if len(parts) >= 3:
        label = parts[2]
    
    print(f'\n=== {label} ===')
    
    # Latency percentiles from client_requests.csv
    cr_file = os.path.join(run_dir, 'client_requests.csv')
    if os.path.exists(cr_file):
        ok_latencies = []
        with open(cr_file) as f:
            for row in csv.DictReader(f):
                if row.get('http_status','0') not in ('0',''):
                    try:
                        lat = float(row.get('latency_ms', 0))
                        if lat > 0:
                            ok_latencies.append(lat)
                    except:
                        pass
        
        if ok_latencies:
            ok_latencies.sort()
            n = len(ok_latencies)
            p50 = ok_latencies[int(n*0.50)]
            p95 = ok_latencies[int(n*0.95)]
            p99 = ok_latencies[int(n*0.99)]
            print(f'  OK latency (n={n}): p50={p50:.0f}ms, p95={p95:.0f}ms, p99={p99:.0f}ms')
    
    # Resource stats
    rs_file = os.path.join(run_dir, 'resource_stats.csv')
    if os.path.exists(rs_file):
        storage_counts = []; server_counts = []; tier1_counts = []
        with open(rs_file) as f:
            for row in csv.DictReader(f):
                try:
                    sc = int(row.get('storage_count', 0))
                    sv = int(row.get('server_count', 0))
                    t1 = int(row.get('tier1_lifecycle_active_count', 0))
                    storage_counts.append(sc)
                    server_counts.append(sv)
                    tier1_counts.append(t1)
                except:
                    pass
        
        if storage_counts:
            print(f'  Storage: baseline={storage_counts[:3] if len(storage_counts)>=3 else storage_counts}, max={max(storage_counts)}')
        if server_counts:
            print(f'  Server:  baseline={server_counts[:3] if len(server_counts)>=3 else server_counts}, max={max(server_counts)}')
        if tier1_counts:
            tw = sum(1 for v in tier1_counts if v > 0)
            print(f'  Tier1:   max={max(tier1_counts)}, active_windows={tw}')
