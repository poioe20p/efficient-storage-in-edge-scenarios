import csv, os, subprocess, sys
from collections import defaultdict

BASE = sys.argv[1] if len(sys.argv) > 1 else 'source/scripts/testing/metrics/20260607_154628_current_state_integrated_b'

# ===== 1. Artifact Inventory =====
required = ['client_requests.csv','resource_stats.csv','resource_stats_debug.csv',
            'policy_state.csv','per_node_stats.csv','container_events.csv',
            'elasticity_events.csv','controller_lan1.log','controller_lan2.log',
            'controller_env_snapshot.env','phases_snapshot.json','service_logs']
print('=== 1. ARTIFACT INVENTORY ===')
for f in required:
    path = os.path.join(BASE, f)
    exists = os.path.exists(path)
    size = os.path.getsize(path) if exists else 0
    status = 'OK' if exists else 'MISSING'
    print('  %s: %s (%d bytes)' % (status, f, size))

# ===== 2. Run Completion =====
cp_path = os.path.join(BASE, 'current_phase.txt')
if os.path.exists(cp_path):
    with open(cp_path) as f:
        print('\n=== 2. RUN COMPLETION ===')
        print('  Final phase: %s' % f.read().strip())
else:
    print('\n=== 2. RUN COMPLETION ===')
    print('  current_phase.txt NOT FOUND')

# ===== 3. Per-Phase Failures =====
print('\n=== 3. PER-PHASE FAILURE RATES ===')
phases = defaultdict(lambda: {'ok': 0, 'fail': 0})
with open(os.path.join(BASE, 'client_requests.csv')) as f:
    for r in csv.DictReader(f):
        s = int(r['http_status'])
        if 200 <= s < 300: phases[r['phase']]['ok'] += 1
        else: phases[r['phase']]['fail'] += 1
order = ['baseline','local_moderate','storage_stress','cross_region_hotspot',
         'inter_hotspot_cooldown','reverse_hotspot','compute_ramp',
         'compute_spike','sustained_plateau','demand_drop']
for ph in order:
    if ph in phases:
        d = phases[ph]; t = d['ok'] + d['fail']
        rt = d['fail'] / t * 100 if t else 0
        print('  %-28s %5d/%6d  %6.1f%%' % (ph, d['fail'], t, rt))
to = sum(v['ok'] for v in phases.values())
tf = sum(v['fail'] for v in phases.values())
tt = to + tf
print('  %-28s %5d/%6d  %6.1f%%' % ('OVERALL', tf, tt, tf/tt*100))

# ===== 4. Tier 2 Storage =====
print('\n=== 4. TIER 2 STORAGE ===')
with open(os.path.join(BASE, 'resource_stats.csv')) as f:
    reader = csv.DictReader(f)
    max_sc = 0
    sc_above_1 = []
    for row in reader:
        sc = int(row.get('storage_count', '0'))
        if sc > max_sc: max_sc = sc
        if sc > 1:
            sc_above_1.append((row['timestamp'], row.get('phase','?'), sc))
print('  Max storage_count: %d' % max_sc)
print('  storage_count > 1 in %d rows' % len(sc_above_1))
if sc_above_1:
    print('  First: %s' % str(sc_above_1[0]))
    print('  Last:  %s' % str(sc_above_1[-1]))

# ===== 5. Tier 1 Selective-Sync =====
print('\n=== 5. TIER 1 SELECTIVE-SYNC ===')
for lan in ['lan1', 'lan2']:
    log = os.path.join(BASE, 'controller_%s.log' % lan)
    if os.path.exists(log):
        r = subprocess.run(['grep', '-c', 'SelectiveSyncAlert', log], capture_output=True, text=True)
        print('  controller_%s: SelectiveSyncAlert count = %s' % (lan, r.stdout.strip()))
        r2 = subprocess.run(['grep', '-c', 'ACTIVE', log], capture_output=True, text=True)
        print('  controller_%s: ACTIVE count = %s' % (lan, r2.stdout.strip()))
with open(os.path.join(BASE, 'container_events.csv')) as f:
    sel_sync = [row for row in csv.DictReader(f) if 'sel_sync' in row.get('container_name','')]
    print('  sel_sync container events: %d' % len(sel_sync))
    for ev in sel_sync[:5]:
        print('    %s %s %s' % (ev.get('timestamp','?'), ev.get('container_name','?'), ev.get('event','?')))

# ===== 6. Compute Exercise =====
print('\n=== 6. COMPUTE EXERCISE ===')
with open(os.path.join(BASE, 'resource_stats.csv')) as f:
    reader = csv.DictReader(f)
    max_srv = 0
    for row in reader:
        sc = int(row.get('server_count', '0'))
        if sc > max_srv: max_srv = sc
print('  Max server_count: %d' % max_srv)
with open(os.path.join(BASE, 'container_events.csv')) as f:
    compute_adds = [row for row in csv.DictReader(f) if 'edge_server' in row.get('container_name','') and row.get('event','') == 'add']
    print('  Dynamic compute adds: %d' % len(compute_adds))
    for ev in compute_adds[:5]:
        print('    %s %s' % (ev.get('timestamp','?'), ev.get('container_name','?')))

# ===== 7. Controller Health =====
print('\n=== 7. CONTROLLER HEALTH ===')
for lan in ['lan1', 'lan2']:
    log = os.path.join(BASE, 'controller_%s.log' % lan)
    if os.path.exists(log):
        r = subprocess.run(['grep', '-c', 'Traceback', log], capture_output=True, text=True)
        print('  controller_%s: Python tracebacks = %s' % (lan, r.stdout.strip()))

# ===== 8. Cleanup =====
print('\n=== 8. CLEANUP ===')
with open(os.path.join(BASE, 'container_events.csv')) as f:
    events = list(csv.DictReader(f))
    adds = [e for e in events if e.get('event') == 'add']
    removes = [e for e in events if e.get('event') in ('remove','removed')]
    print('  Container adds: %d, removes: %d' % (len(adds), len(removes)))
    running = set()
    for e in events:
        if e.get('event') == 'add': running.add(e.get('container_name'))
        elif e.get('event') in ('remove','removed'): running.discard(e.get('container_name'))
    if running:
        print('  Containers still running at end: %d' % len(running))
        for c in sorted(running): print('    ' + c)
    else:
        print('  All containers removed by end')

# ===== 9. Service-Quality Per-Criterion =====
print('\n=== 9. SERVICE-QUALITY ENVELOPE ===')
caps = {
    'baseline': ('non-hotspot', 1.0),
    'local_moderate': ('non-hotspot', 1.0),
    'storage_stress': ('hotspot', 10.0),
    'cross_region_hotspot': ('hotspot', 10.0),
    'inter_hotspot_cooldown': ('non-hotspot', 1.0),
    'reverse_hotspot': ('hotspot', 10.0),
    'compute_ramp': ('non-hotspot', 1.0),
    'compute_spike': ('non-hotspot', 1.0),
    'sustained_plateau': ('non-hotspot', 1.0),
    'demand_drop': ('non-hotspot', 1.0),
}
all_pass = True
for ph in order:
    if ph in phases:
        d = phases[ph]; t = d['ok'] + d['fail']
        rate = d['fail'] / t * 100 if t else 0
        cat, cap = caps[ph]
        passed = rate <= cap
        if not passed: all_pass = False
        mark = 'PASS' if passed else 'FAIL'
        print('  %-28s %6.1f%% <= %4.1f%% (%s) %s' % (ph, rate, cap, cat, mark))
overall_rate = tf / tt * 100 if tt else 0
overall_pass = overall_rate <= 5.0
if not overall_pass: all_pass = False
print('  %-28s %6.1f%% <= %4.1f%% (overall) %s' % ('OVERALL', overall_rate, 5.0, 'PASS' if overall_pass else 'FAIL'))
print('\n  ALL CRITERIA PASS: %s' % ('YES' if all_pass else 'NO'))
