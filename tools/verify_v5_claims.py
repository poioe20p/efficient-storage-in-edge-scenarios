#!/usr/bin/env python3
"""Verify claims in results_v5.md against actual run data."""
import csv, json, os, sys
from collections import defaultdict

BASE = os.path.expanduser("~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics")

runs = {
    'Remote': '20260710_225316_rq3_v5_remote',
    'Cold':   '20260710_232625_rq3_v5_tier2_cold',
    'Warm':   '20260710_235938_rq3_v5_tier2_warm',
    'Tier1':  '20260711_003240_rq3_v5_tier1',
}

print("=" * 80)
print("CLAIM VERIFICATION: Per-Phase Success Rates")
print("=" * 80)

for name, run in runs.items():
    d = os.path.join(BASE, run)
    pc = defaultdict(lambda: {'lan1': [0, 0], 'lan2': [0, 0]})
    
    # Per-phase latency percentiles
    latencies = defaultdict(lambda: {'lan1': [], 'lan2': []})
    
    try:
        with open(os.path.join(d, 'client_requests.csv')) as f:
            for row in csv.DictReader(f):
                lan = 'lan1' if row.get('client_lan', '') == 'lan1' else 'lan2'
                phase = row.get('phase', '')
                pc[phase][lan][0] += 1
                if row.get('success', '') == 'True':
                    pc[phase][lan][1] += 1
                try:
                    lat = float(row.get('latency_s', 0))
                except:
                    lat = 0
                latencies[phase][lan].append(lat)
    except Exception as e:
        print(f'{name}: ERROR reading CSV - {e}')
        continue

    print(f'\n=== {name} ({run}) ===')
    ta = 0; sa = 0
    for ph in ['baseline', 'cross_region_pressure', 'sustained_pressure', 'cooldown']:
        for lan in ['lan1', 'lan2']:
            t, s = pc[ph][lan]
            ta += t; sa += s
            r = f'{s/t*100:.1f}%' if t > 0 else 'N/A'
            
            # Compute p50, p95
            lats = sorted(latencies[ph][lan])
            p50 = lats[len(lats)//2] if lats else 0
            p95_idx = int(len(lats) * 0.95)
            p95 = lats[min(p95_idx, len(lats)-1)] if lats else 0
            
            print(f'  {ph:30s} {lan:5s}  n={t:6d}  succ={s:6d}  rate={r:>7s}  p50={p50:.2f}s  p95={p95:.2f}s')
    print(f'  {"TOTAL":30s} {"":5s}  n={ta:6d}  succ={sa:6d}  rate={sa/ta*100:.1f}%')

# Check controller logs
print("\n" + "=" * 80)
print("CLAIM VERIFICATION: Controller Log Event Counts")
print("=" * 80)

for name, run in runs.items():
    d = os.path.join(BASE, run)
    counts = {}
    for logfile in ['controller_lan1.log', 'controller_lan2.log']:
        lp = os.path.join(d, logfile)
        if os.path.exists(lp):
            with open(lp) as f:
                content = f.read()
            counts[f'{logfile}_xreg_reads_lines'] = content.count('[cross-region-reads]')
            counts[f'{logfile}_cross_region_reserve'] = content.count('[cross-region-reserve]')
            counts[f'{logfile}_cross_region_cold'] = content.count('[cross-region-cold]')
            counts[f'{logfile}_tier1'] = content.count('[tier1]')
            counts[f'{logfile}_SPAWN'] = content.count('SPAWN submitted')
            counts[f'{logfile}_ACTIVATED'] = content.count('ACTIVATED')
            counts[f'{logfile}_BREACH'] = content.count('BREACH')
            counts[f'{logfile}_PASS'] = content.count('PASS')
            counts[f'{logfile}_BLOCKED'] = content.count('BLOCKED')
            counts[f'{logfile}_prepare_submitted'] = content.count('prepare_submitted')
            counts[f'{logfile}_promote'] = content.count('promote')
            counts[f'{logfile}_node_ready'] = content.count('[node_ready]')
            counts[f'{logfile}_load_activation'] = content.count('reason=load')
    
    print(f'\n--- {name} ---')
    for k, v in sorted(counts.items()):
        if v > 0:
            print(f'  {k}: {v}')

# Check elasticity events
print("\n" + "=" * 80)
print("CLAIM VERIFICATION: Elasticity Events")
print("=" * 80)

for name, run in runs.items():
    d = os.path.join(BASE, run)
    ep = os.path.join(d, 'elasticity_events.csv')
    if os.path.exists(ep):
        with open(ep) as f:
            count = sum(1 for _ in f) - 1  # minus header
        print(f'  {name}: {count} elasticity events')
    else:
        print(f'  {name}: elasticity_events.csv NOT FOUND')

    # Container events
    cp = os.path.join(d, 'container_events.csv')
    if os.path.exists(cp):
        with open(cp) as f:
            count = sum(1 for _ in f) - 1
        print(f'  {name}: {count} container events')
    else:
        print(f'  {name}: container_events.csv NOT FOUND')

# Check phases snapshot for timing
print("\n" + "=" * 80)
print("CLAIM VERIFICATION: Phase Timing (from phases_snapshot.json)")
print("=" * 80)

for name, run in runs.items():
    d = os.path.join(BASE, run)
    pp = os.path.join(d, 'phases_snapshot.json')
    if os.path.exists(pp):
        with open(pp) as f:
            data = json.load(f)
        print(f'\n--- {name} ---')
        for p in data['phases']:
            cr = p.get('cross_region_ratio', 'N/A')
            print(f'  {p["name"]:30s}  duration={p["duration_s"]:4d}s  rate={p["rate_per_client"]}  cross_region={cr}')

# Specific gate log extractions
print("\n" + "=" * 80)
print("CLAIM VERIFICATION: Gate PASS/BLOCKED Timeline (Cold & Warm)")
print("=" * 80)

for name, run in [('Cold', '20260710_232625_rq3_v5_tier2_cold'), ('Warm', '20260710_235938_rq3_v5_tier2_warm')]:
    d = os.path.join(BASE, run)
    lp = os.path.join(d, 'controller_lan2.log')
    if os.path.exists(lp):
        with open(lp) as f:
            lines = f.readlines()
        print(f'\n--- {name} Gate Events ---')
        for line in lines:
            if '[cross-region-reads]' in line:
                # Extract xreg_reads count
                import re
                m = re.search(r'xreg_reads=(\d+)', line)
                xreg = m.group(1) if m else '?'
                # Extract timestamp
                ts_match = re.search(r'(\d{2}:\d{2}:\d{2})', line)
                ts = ts_match.group(1) if ts_match else '?'
                gate = 'PASS' if 'PASS' in line else 'BLOCKED' if 'BLOCKED' in line else '?'
                # Extract p95 if present
                p95_match = re.search(r'p95=(\d+)', line)
                p95 = p95_match.group(1) + 'ms' if p95_match else ''
                breach = 'BREACH' if 'BREACH' in line else ''
                print(f'  {ts}  {gate:8s}  xreg_reads={xreg:>5s}  {p95}  {breach}')

print("\n" + "=" * 80)
print("CLAIM VERIFICATION: Tier1 Log Entries")
print("=" * 80)

for name, run in [('Tier1', '20260711_003240_rq3_v5_tier1')]:
    d = os.path.join(BASE, run)
    for logfile in ['controller_lan1.log', 'controller_lan2.log']:
        lp = os.path.join(d, logfile)
        if os.path.exists(lp):
            with open(lp) as f:
                lines = f.readlines()
            count = 0
            print(f'\n--- {name} {logfile} [tier1] entries ---')
            for line in lines:
                if '[tier1]' in line:
                    count += 1
                    import re
                    ts_match = re.search(r'(\d{2}:\d{2}:\d{2})', line)
                    ts = ts_match.group(1) if ts_match else '?'
                    if count <= 5 or 'promote' in line.lower() or 'manifest' in line.lower() or 'drain' in line.lower():
                        print(f'  [{count:3d}] {ts}  {line.rstrip()[-200:]}')
            print(f'  Total [tier1] entries in {logfile}: {count}')

print("\nDone.")
