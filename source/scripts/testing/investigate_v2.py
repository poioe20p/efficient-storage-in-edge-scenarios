#!/usr/bin/env python3
"""Investigate: (1) Storage scale-down — threshold vs code issue
               (2) Compute churn → HTTP-0 mechanism"""
import csv, os, re, subprocess
from collections import Counter, defaultdict

BASE = '/home/testop/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics'

# ─── 1. STORAGE SCALE-DOWN ──────────────────────────────────
print("=" * 70)
print("1. STORAGE SCALE-DOWN INVESTIGATION")
print("=" * 70)

for run_name, run_dir in [('Run A', f'{BASE}/20260608_131830_current_state_integrated_a'),
                           ('Run B', f'{BASE}/20260608_140225_current_state_integrated_b')]:
    print(f"\n--- {run_name} ---")
    
    # Search controller logs for scale-down decisions
    for lan in ['lan1', 'lan2']:
        log_path = f'{run_dir}/controller_{lan}.log'
        if not os.path.exists(log_path):
            continue
        
        scale_down_lines = []
        with open(log_path, errors='replace') as f:
            for line in f:
                if 'scale_down' in line.lower() or 'scaledown' in line.lower():
                    scale_down_lines.append(line.strip()[:250])
        
        # Separate storage vs compute
        storage_lines = [l for l in scale_down_lines if 'storage' in l.lower()]
        compute_lines = [l for l in scale_down_lines if 'compute' in l.lower() or 'server' in l.lower()]
        
        print(f"  {lan}: {len(storage_lines)} storage scale-down, {len(compute_lines)} compute scale-down log lines")
        
        if storage_lines:
            print(f"    Storage samples:")
            for l in storage_lines[:5]:
                print(f"      {l[:200]}")
        
        if compute_lines:
            print(f"    Compute samples:")
            for l in compute_lines[:3]:
                print(f"      {l[:200]}")

# ─── 2. COMPUTE CHURN → HTTP-0 MECHANISM ────────────────────
print("\n" + "=" * 70)
print("2. COMPUTE CHURN → HTTP-0 CORRELATION")
print("=" * 70)

for run_name, run_dir in [('Run B', f'{BASE}/20260608_140225_current_state_integrated_b')]:
    print(f"\n--- {run_name}: Timing correlation ---")
    
    # Get compute add/remove events with exact timestamps
    compute_events = []
    with open(f'{run_dir}/container_events.csv') as f:
        for row in csv.DictReader(f):
            name = row['container']
            if 'edge_server' in name and row['event'] in ('added', 'removed'):
                compute_events.append({
                    'ts': row['timestamp_iso'],
                    'type': row['event'],
                    'name': name,
                    'phase': row['phase']
                })
    
    # Get HTTP-0 failure clusters
    fail_clusters = []
    current_cluster = []
    prev_ts = None
    with open(f'{run_dir}/client_requests.csv') as f:
        for row in csv.DictReader(f):
            if row['http_status'] != '200':
                ts = row['timestamp']
                if prev_ts is None:
                    current_cluster = [row]
                elif (pd := abs(parse_ts_diff(ts, prev_ts))) < 5:  # 5s gap = same cluster
                    current_cluster.append(row)
                else:
                    if len(current_cluster) >= 10:
                        fail_clusters.append(current_cluster)
                    current_cluster = [row]
                prev_ts = ts
    
    # Check if failure clusters immediately follow compute events
    for event in compute_events:
        event_ts = event['ts']
        # Find failures within 10s after this event
        nearby = []
        with open(f'{run_dir}/client_requests.csv') as f:
            for row in csv.DictReader(f):
                if row['http_status'] != '200':
                    diff = parse_ts_diff(row['timestamp'], event_ts)
                    if diff is not None and 0 <= diff <= 10:
                        nearby.append(row)
        if len(nearby) >= 5:
            print(f"  {event['type']:8s} {event['name']:30s} at {event_ts[:19]} → {len(nearby)} failures within 10s")

# ─── 3. SCALE-DOWN CODE CHECK ──────────────────────────────
print("\n" + "=" * 70)
print("3. SCALE-DOWN CODE PATH CHECK")
print("=" * 70)

# Check if the env variables are read correctly
print("  Checking scaling_config.py for scale-down parameters...")
sc_path = '/home/testop/efficient-storage-in-edge-scenarios/source/sdn_controller/scaling_config.py'
if os.path.exists(sc_path):
    with open(sc_path) as f:
        content = f.read()
    
    # Find storage scale-down settings
    for pattern in ['SCALE_DOWN_STORAGE', 'SCALEDOWN_STORAGE', 'scale_down_storage', 'storage.*scale.*down']:
        matches = re.findall(rf'.{{0,100}}{pattern}.{{0,100}}', content, re.IGNORECASE)
        for m in matches:
            print(f"    {m.strip()[:150]}")

def parse_ts_diff(ts1, ts2):
    """Parse ISO timestamps and return diff in seconds, or None."""
    try:
        from datetime import datetime
        t1 = datetime.fromisoformat(ts1.replace('Z', '+00:00'))
        t2 = datetime.fromisoformat(ts2.replace('Z', '+00:00'))
        return abs((t1 - t2).total_seconds())
    except:
        return None
