#!/usr/bin/env python3
"""Investigate: scale-down behavior and HTTP-0 failure root causes."""
import csv, os, subprocess, sys
from collections import Counter

BASE = '/home/testop/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics'

# ─── 1. Compute scale-down check ───────────────────────────
print("=" * 60)
print("1. COMPUTE SCALE-DOWN CHECK")
print("=" * 60)
# Check what compute containers exist now
result = subprocess.run(['sudo', 'docker', 'ps', '--format', '{{.Names}} {{.Image}}'], 
                       capture_output=True, text=True)
all_containers = result.stdout.strip().split('\n')
edge_servers = [c.split()[0] for c in all_containers if 'edge_server' in c]
print(f"  Edge server containers running: {len(edge_servers)}")
for c in sorted(edge_servers):
    print(f"    {c}")
dyn_containers = [c.split()[0] for c in all_containers if 'dyn' in c or 'sel_sync' in c]
print(f"  Dynamic containers running: {len(dyn_containers)}")
for c in sorted(dyn_containers):
    print(f"    {c}")

# ─── 2. Edge server error analysis ─────────────────────────
print("\n" + "=" * 60)
print("2. EDGE SERVER ERROR ROOT CAUSE ANALYSIS")
print("=" * 60)

for run_name, run_dir in [('Run A', f'{BASE}/20260608_131830_current_state_integrated_a'),
                           ('Run B', f'{BASE}/20260608_140225_current_state_integrated_b')]:
    print(f"\n--- {run_name} ---")
    for server in ['edge_server_n1', 'edge_server_n2']:
        log_path = f'{run_dir}/service_logs/{server}.log'
        if not os.path.exists(log_path):
            print(f"  {server}: log not found")
            continue
        
        # Count error types
        error_types = Counter()
        with open(log_path, errors='replace') as f:
            for line in f:
                if 'ERROR' in line or 'error' in line.lower():
                    # Classify the error
                    if 'AutoReconnect' in line:
                        error_types['AutoReconnect'] += 1
                    elif 'CircuitOpenError' in line or 'circuit' in line.lower():
                        error_types['CircuitOpenError'] += 1
                    elif 'ServerSelectionTimeoutError' in line or 'serverSelectionTimeout' in line:
                        error_types['ServerSelectionTimeout'] += 1
                    elif 'ConnectionRefusedError' in line or 'refused' in line.lower():
                        error_types['ConnectionRefused'] += 1
                    elif 'TimeoutError' in line or 'timeout' in line.lower():
                        error_types['Timeout'] += 1
                    elif 'getMore' in line:
                        error_types['getMore_failure'] += 1
                    elif 'epoch' in line.lower() or 'recovery' in line.lower():
                        error_types['EpochRecovery'] += 1
                    elif 'breaker' in line.lower():
                        error_types['Breaker'] += 1
                    else:
                        error_types['Other'] += 1
        
        print(f"  {server}: {sum(error_types.values())} total errors")
        for etype, count in error_types.most_common(10):
            print(f"    {etype}: {count}")
        
        # Sample actual error lines
        if error_types:
            print(f"  Sample errors ({server}):")
            samples = []
            with open(log_path, errors='replace') as f:
                for line in f:
                    if 'ERROR' in line:
                        samples.append(line.strip()[:200])
                        if len(samples) >= 5:
                            break
            for s in samples:
                print(f"    {s}")

# ─── 3. Storage pool instability check ─────────────────────
print("\n" + "=" * 60)
print("3. STORAGE POOL STABILITY")
print("=" * 60)

for run_name, run_dir in [('Run A', f'{BASE}/20260608_131830_current_state_integrated_a'),
                           ('Run B', f'{BASE}/20260608_140225_current_state_integrated_b')]:
    print(f"\n--- {run_name} ---")
    rs_path = f'{run_dir}/resource_stats.csv'
    
    # Count storage_count and server_count transitions
    prev_sc = prev_sv = None
    sc_transitions = 0
    sv_transitions = 0
    sc_values = Counter()
    sv_values = Counter()
    
    with open(rs_path) as f:
        for row in csv.DictReader(f):
            sc = row.get('storage_count', '0')
            sv = row.get('server_count', '0')
            sc_values[sc] += 1
            sv_values[sv] += 1
            if sc != prev_sc and prev_sc is not None:
                sc_transitions += 1
            if sv != prev_sv and prev_sv is not None:
                sv_transitions += 1
            prev_sc = sc
            prev_sv = sv
    
    print(f"  storage_count transitions: {sc_transitions}")
    print(f"  storage_count values: {dict(sc_values)}")
    print(f"  server_count transitions: {sv_transitions}")
    print(f"  server_count values: {dict(sv_values)}")
    
    # Check if transitions correlate with phase boundaries
    # Get phase timestamps from phases_snapshot
    import json
    with open(f'{run_dir}/phases_snapshot.json') as f:
        phases = json.load(f)
    
    print(f"  Phases in run:")
    for p in phases.get('phases', []):
        print(f"    {p.get('name', '?'):30s} {p.get('duration_s', 0):>4d}s")

# ─── 4. HTTP-0 failure timing vs mechanism activity ────────
print("\n" + "=" * 60)
print("4. HTTP-0 FAILURE TIMING vs MECHANISM EVENTS")
print("=" * 60)

for run_name, run_dir in [('Run A', f'{BASE}/20260608_131830_current_state_integrated_a'),
                           ('Run B', f'{BASE}/20260608_140225_current_state_integrated_b')]:
    print(f"\n--- {run_name} ---")
    
    # Get failure timestamps by phase
    phase_failures = {}
    with open(f'{run_dir}/client_requests.csv') as f:
        for row in csv.DictReader(f):
            if row['http_status'] != '200':
                phase = row['phase']
                if phase not in phase_failures:
                    phase_failures[phase] = []
                phase_failures[phase].append(row['timestamp'])
    
    # Get mechanism events from container_events
    mechanism_events = []
    with open(f'{run_dir}/container_events.csv') as f:
        for row in csv.DictReader(f):
            if row['event'] in ('added', 'removed'):
                mechanism_events.append({
                    'ts': row['timestamp_iso'],
                    'type': row['event'],
                    'container': row['container'],
                    'phase': row['phase']
                })
    
    # Check if failures coincide with add/remove events
    for phase, failures in sorted(phase_failures.items()):
        if len(failures) == 0:
            continue
        # Find mechanism events in this phase
        phase_events = [e for e in mechanism_events if e['phase'] == phase]
        if phase_events:
            storage_adds = [e for e in phase_events if 'storage' in e['container'] and e['type'] == 'added']
            storage_rems = [e for e in phase_events if 'storage' in e['container'] and e['type'] == 'removed']
            compute_adds = [e for e in phase_events if 'edge_server' in e['container'] and e['type'] == 'added']
            first_fail = min(failures)
            last_fail = max(failures)
            print(f"  {phase:30s}: {len(failures):>6,d} failures | storage +{len(storage_adds)}/-{len(storage_rems)} | compute +{len(compute_adds)}")
            print(f"    Failure window: {first_fail[:19]} → {last_fail[:19]}")
