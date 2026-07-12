#!/usr/bin/env python3
"""Verify all claims in results_v5.md against cloud VM run data."""
import csv, json, os, re
from collections import defaultdict

BASE = os.path.expanduser('~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics')

runs = [
    ('Remote', '20260710_225316_rq3_v5_remote'),
    ('Cold',   '20260710_232625_rq3_v5_tier2_cold'),
    ('Warm',   '20260710_235938_rq3_v5_tier2_warm'),
    ('Tier1',  '20260711_003240_rq3_v5_tier1'),
]

SEP = '=' * 80

# ============================================================
# 1. PER-PHASE SUCCESS RATES & LATENCY
# ============================================================
print(SEP)
print('1. PER-PHASE SUCCESS RATES and LATENCY')
print(SEP)

for name, run in runs:
    d = os.path.join(BASE, run)
    pc = defaultdict(lambda: {'lan1': [0,0], 'lan2': [0,0]})
    lats = defaultdict(lambda: {'lan1': [], 'lan2': []})
    
    with open(os.path.join(d, 'client_requests.csv')) as f:
        for row in csv.DictReader(f):
            lan = 'lan1' if row.get('client_lan','') == 'lan1' else 'lan2'
            ph = row.get('phase','')
            pc[ph][lan][0] += 1
            if row.get('http_status','') == '200':
                pc[ph][lan][1] += 1
            try:
                lats[ph][lan].append(float(row.get('latency_s', 0)))
            except:
                pass
    
    print()
    print('=== {} ==='.format(name))
    ta = 0
    sa = 0
    for ph in ['baseline', 'cross_region_pressure', 'sustained_pressure', 'cooldown']:
        for lan in ['lan1', 'lan2']:
            t, s = pc[ph][lan]
            ta += t
            sa += s
            r = '{:.1f}%'.format(s/t*100) if t > 0 else 'N/A'
            ll = sorted(lats[ph][lan])
            p50 = ll[len(ll)//2] if ll else 0
            p95_idx = min(int(len(ll) * 0.95), len(ll) - 1)
            p95 = ll[p95_idx] if ll else 0
            print('  {:30s} {:5s} n={:6d} succ={:6d} rate={:>7s} p50={:.2f}s p95={:.2f}s'.format(
                ph, lan, t, s, r, p50, p95))
    overall_rate = '{:.1f}%'.format(sa/ta*100) if ta > 0 else 'N/A'
    print('  {:30s} {:5s} n={:6d} succ={:6d} rate={}'.format('TOTAL', '', ta, sa, overall_rate))
    
    # Overall stats
    all_lats = []
    for ph in ['baseline', 'cross_region_pressure', 'sustained_pressure', 'cooldown']:
        for lan in ['lan1', 'lan2']:
            all_lats.extend(lats[ph][lan])
    all_lats.sort()
    if all_lats:
        overall_p95 = all_lats[min(int(len(all_lats)*0.95), len(all_lats)-1)]
        mean_lat = sum(all_lats) / len(all_lats)
        print('  Overall mean={:.2f}s  overall p95={:.2f}s'.format(mean_lat, overall_p95))

# ============================================================
# 2. COLD GATE LOGS
# ============================================================
print()
print(SEP)
print('2. COLD GATE LOGS: xreg_reads timeline')
print(SEP)

for name, run in [('Cold', '20260710_232625_rq3_v5_tier2_cold')]:
    d = os.path.join(BASE, run)
    lp = os.path.join(d, 'controller_lan2.log')
    with open(lp) as f:
        lines = f.readlines()
    
    print()
    print('--- {} Gate Events ---'.format(name))
    count = 0
    for line in lines:
        if 'xreg_reads=' in line:
            count += 1
            ts_m = re.search(r'(\d{2}:\d{2}:\d{2})', line)
            ts = ts_m.group(1) if ts_m else '?'
            xr_m = re.search(r'xreg_reads=(\d+)', line)
            xr = xr_m.group(1) if xr_m else '?'
            p95_m = re.search(r'p95=(\d+)', line)
            p95 = 'p95=' + p95_m.group(1) + 'ms' if p95_m else ''
            
            gate = ''
            if 'PASS' in line:
                gate = 'PASS'
            elif 'BLOCKED' in line:
                gate = 'BLOCKED'
            breach = 'BREACH' if 'BREACH' in line else ''
            
            print('  {} {:8s} xreg={:>5s} {:15s} {}'.format(ts, gate, xr, p95, breach))
    print('  Total gate evaluations with xreg_reads: {}'.format(count))

# ============================================================
# 3. WARM GATE LOGS
# ============================================================
print()
print(SEP)
print('3. WARM GATE LOGS: xreg_reads timeline')
print(SEP)

for name, run in [('Warm', '20260710_235938_rq3_v5_tier2_warm')]:
    d = os.path.join(BASE, run)
    lp = os.path.join(d, 'controller_lan2.log')
    with open(lp) as f:
        lines = f.readlines()
    
    print()
    print('--- {} Gate Events ---'.format(name))
    count = 0
    blocked_zero = 0
    for line in lines:
        if 'xreg_reads=' in line:
            count += 1
            ts_m = re.search(r'(\d{2}:\d{2}:\d{2})', line)
            ts = ts_m.group(1) if ts_m else '?'
            xr_m = re.search(r'xreg_reads=(\d+)', line)
            xr = xr_m.group(1) if xr_m else '?'
            p95_m = re.search(r'p95=(\d+)', line)
            p95 = 'p95=' + p95_m.group(1) + 'ms' if p95_m else ''
            
            gate = ''
            if 'PASS' in line:
                gate = 'PASS'
            elif 'BLOCKED' in line:
                gate = 'BLOCKED'
            breach = 'BREACH' if 'BREACH' in line else ''
            
            if gate == 'BLOCKED' and xr == '0':
                blocked_zero += 1
            
            print('  {} {:8s} xreg={:>5s} {:15s} {}'.format(ts, gate, xr, p95, breach))
    print('  Total gate evaluations: {}'.format(count))
    print('  Of which BLOCKED with xreg=0: {}'.format(blocked_zero))

# ============================================================
# 4. SPAWN & ACTIVATION EVENTS
# ============================================================
print()
print(SEP)
print('4. COLD SPAWN and WARM ACTIVATION EVENTS')
print(SEP)

for name, run in [('Cold', '20260710_232625_rq3_v5_tier2_cold'),
                  ('Warm', '20260710_235938_rq3_v5_tier2_warm')]:
    d = os.path.join(BASE, run)
    lp = os.path.join(d, 'controller_lan2.log')
    with open(lp) as f:
        lines = f.readlines()
    
    print()
    print('--- {} Key Events ---'.format(name))
    keywords = ['SPAWN submitted', '[cross-region-reserve]', '[cross-region-cold]',
                'ACTIVATED', 'prepare_submitted', 'reason=load']
    for line in lines:
        found_kw = None
        for kw in keywords:
            if kw in line:
                found_kw = kw
                break
        if found_kw:
            ts_m = re.search(r'(\d{2}:\d{2}:\d{2})', line)
            ts = ts_m.group(1) if ts_m else '?'
            stripped = line.rstrip()
            # Try to extract key snippet
            idx = stripped.find(found_kw)
            start = max(0, idx - 50)
            snippet = stripped[start:start+350]
            print('  {}  ...{}'.format(ts, snippet))

# ============================================================
# 5. ELASTICITY & CONTAINER EVENT COUNTS
# ============================================================
print()
print(SEP)
print('5. ELASTICITY and CONTAINER EVENT COUNTS')
print(SEP)

for name, run in runs:
    d = os.path.join(BASE, run)
    for fname in ['elasticity_events.csv', 'container_events.csv']:
        fp = os.path.join(d, fname)
        if os.path.exists(fp):
            with open(fp) as f:
                cnt = sum(1 for _ in f) - 1  # minus header
            print('  {:10s} {:25s}: {}'.format(name, fname, cnt))
        else:
            print('  {:10s} {:25s}: MISSING'.format(name, fname))

# ============================================================
# 6. TIER1 FULL [tier1] LOG
# ============================================================
print()
print(SEP)
print('6. TIER1 FULL [tier1] LOG')
print(SEP)

d = os.path.join(BASE, '20260711_003240_rq3_v5_tier1')
lp = os.path.join(d, 'controller_lan2.log')
with open(lp) as f:
    lines = f.readlines()

tier1_lines = [(i, line) for i, line in enumerate(lines) if '[tier1]' in line]
print('Total [tier1] entries on LAN2: {}'.format(len(tier1_lines)))
for i, (idx, line) in enumerate(tier1_lines):
    ts_m = re.search(r'(\d{2}:\d{2}:\d{2})', line)
    ts = ts_m.group(1) if ts_m else '?'
    stripped = line.rstrip()
    if len(stripped) > 350:
        stripped = stripped[-350:]
    print('  [{:3d}] {}  {}'.format(i+1, ts, stripped))

# Check controller_lan1.log too
lp1 = os.path.join(d, 'controller_lan1.log')
with open(lp1) as f:
    lines1 = f.readlines()
t1_lan1 = sum(1 for line in lines1 if '[tier1]' in line)
print('Total [tier1] entries on LAN1: {}'.format(t1_lan1))

# ============================================================
# 7. PHASE TIMING & CROSS-REGION RATIO VERIFICATION
# ============================================================
print()
print(SEP)
print('7. PHASE TIMING and CROSS-REGION RATIO (from phases_snapshot.json)')
print(SEP)

# Results_v5.md header says cross_region=0.9 for pressure, but phases show 0.95
for name, run in runs:
    d = os.path.join(BASE, run)
    pp = os.path.join(d, 'phases_snapshot.json')
    if os.path.exists(pp):
        with open(pp) as f:
            data = json.load(f)
        for p in data['phases']:
            cr = str(p.get('cross_region_ratio', 'N/A'))
            print('  {} {:30s} duration={:4d}s rate={} cross_region={}'.format(
                name, p['name'], p['duration_s'], p['rate_per_client'], cr))

# ============================================================
# 8. WARM LOAD ACTIVATIONS DETAIL
# ============================================================
print()
print(SEP)
print('8. WARM LOAD-BASED ACTIVATIONS (controller_lan2.log)')
print(SEP)

d = os.path.join(BASE, '20260710_235938_rq3_v5_tier2_warm')
lp = os.path.join(d, 'controller_lan2.log')
with open(lp) as f:
    lines = f.readlines()

print()
print('All [reserve] activated events on LAN2:')
for line in lines:
    if 'activated' in line.lower():
        ts_m = re.search(r'(\d{2}:\d{2}:\d{2})', line)
        ts = ts_m.group(1) if ts_m else '?'
        # Extract container name
        c_m = re.search(r'container[= ]+(\S+)', line)
        container = c_m.group(1) if c_m else '?'
        # Extract reason
        r_m = re.search(r'reason[= ]+(\S+)', line)
        reason = r_m.group(1) if r_m else '?'
        stripped = line.rstrip()
        if len(stripped) > 300:
            stripped = '...' + stripped[-280:]
        print('  {}  reason={} container={}'.format(ts, reason, container))
        print('       {}'.format(stripped))

# ============================================================
# 9. SUSTAINED PRESSURE CHECK
# ============================================================
print()
print(SEP)
print('9. SUSTAINED_PRESSURE SUCCESS RATE CHECK (all 4 strategies)')
print(SEP)

for name, run in runs:
    d = os.path.join(BASE, run)
    sp_total = 0
    sp_success = 0
    with open(os.path.join(d, 'client_requests.csv')) as f:
        for row in csv.DictReader(f):
            if row.get('phase', '') == 'sustained_pressure':
                sp_total += 1
                if row.get('http_status', '') == '200':
                    sp_success += 1
    rate = '{:.1f}%'.format(sp_success/sp_total*100) if sp_total > 0 else 'N/A'
    print('  {}: sustained_pressure total={} success={} rate={}'.format(name, sp_total, sp_success, rate))

# ============================================================
# 10. REMOTE P95 CHECK
# ============================================================
print()
print(SEP)
print('10. REMOTE CROSS-REGION PRESSURE P95 (claims p95=5.67s overall)')
print(SEP)

d = os.path.join(BASE, '20260710_225316_rq3_v5_remote')
lats_pressure = []
with open(os.path.join(d, 'client_requests.csv')) as f:
    for row in csv.DictReader(f):
        if row.get('phase', '') == 'cross_region_pressure':
            try:
                lats_pressure.append(float(row.get('latency_s', 0)))
            except:
                pass
lats_pressure.sort()
if lats_pressure:
    p50_p = lats_pressure[len(lats_pressure)//2]
    p95_p = lats_pressure[min(int(len(lats_pressure)*0.95), len(lats_pressure)-1)]
    print('  Remote cross_region_pressure phase: n={} p50={:.2f}s p95={:.2f}s'.format(
        len(lats_pressure), p50_p, p95_p))

print()
print('Done.')
