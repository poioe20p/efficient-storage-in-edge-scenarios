"""Full experiment analysis for conntrack run 20260608_112947."""
import csv, collections, sys
from datetime import datetime

RUN = 'source/scripts/testing/metrics/20260608_112947_conntrack_experiment'

# ── 1. Client requests ───────────────────────────────────────
print("=" * 60)
print("1. CLIENT REQUESTS")
print("=" * 60)
codes = collections.Counter()
phase_stats = {}
with open(f'{RUN}/client_requests.csv') as f:
    for row in csv.DictReader(f):
        code = row['http_status']
        phase = row['phase']
        lan = row['client_lan']
        endpoint = row['endpoint']
        codes[code] += 1
        if phase not in phase_stats:
            phase_stats[phase] = {'total': 0, 'ok': 0, 'fail': 0, 'fail_lan1': 0, 'fail_lan2': 0}
        phase_stats[phase]['total'] += 1
        if code == '200':
            phase_stats[phase]['ok'] += 1
        else:
            phase_stats[phase]['fail'] += 1
            if lan == 'lan1':
                phase_stats[phase]['fail_lan1'] += 1
            else:
                phase_stats[phase]['fail_lan2'] += 1

total = sum(codes.values())
fail = sum(n for c, n in codes.items() if c != '200')
print(f'Total requests: {total:,}')
print(f'HTTP 200: {codes.get("200", 0):,}')
print(f'HTTP 0:   {codes.get("0", 0):,}')
print(f'HTTP 503: {codes.get("503", 0):,}')
print(f'Failure rate: {fail}/{total} = {fail/total*100:.1f}%\n')

print(f'{"Phase":30s} {"Total":>8s} {"Fail":>8s} {"Rate":>7s} {"LAN1":>8s} {"LAN2":>8s}')
print(f'{"-"*30} {"-"*8} {"-"*8} {"-"*7} {"-"*8} {"-"*8}')
for phase in sorted(phase_stats):
    ps = phase_stats[phase]
    rate = ps['fail'] / ps['total'] * 100 if ps['total'] else 0
    print(f'{phase:30s} {ps["total"]:>8,d} {ps["fail"]:>8,d} {rate:>6.1f}% {ps["fail_lan1"]:>8,d} {ps["fail_lan2"]:>8,d}')

# ── 2. Resource stats (conntrack) ─────────────────────────────
print("\n" + "=" * 60)
print("2. CONNTRACK ENTRIES (resource_stats.csv)")
print("=" * 60)
ct_max_n1 = 0
ct_max_n2 = 0
ct_samples = 0
with open(f'{RUN}/resource_stats.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        try:
            n1 = int(row.get('conntrack_entries_n1', 0) or 0)
            n2 = int(row.get('conntrack_entries_n2', 0) or 0)
            ct_max_n1 = max(ct_max_n1, n1)
            ct_max_n2 = max(ct_max_n2, n2)
            ct_samples += 1
        except (ValueError, KeyError):
            pass
print(f'  Conntrack entries (max): n1={ct_max_n1}, n2={ct_max_n2}')
print(f'  Conntrack columns present: {ct_samples > 0}')

# ── 3. Container events ───────────────────────────────────────
print("\n" + "=" * 60)
print("3. CONTAINER EVENTS")
print("=" * 60)
containers_seen = set()
events_by_type = collections.Counter()
events = []
with open(f'{RUN}/container_events.csv') as f:
    for row in csv.DictReader(f):
        etype = row['event']
        name = row['container']
        events_by_type[etype] += 1
        containers_seen.add(name)
        events.append(row)
print(f'  Unique containers: {len(containers_seen)}')
print(f'  Events: {dict(events_by_type)}')
# Count storage nodes
storage_nodes = [c for c in containers_seen if 'dyn' in c]
print(f'  Dynamic storage nodes: {len(storage_nodes)}')

# ── 4. Elasticity events ──────────────────────────────────────
print("\n" + "=" * 60)
print("4. ELASTICITY EVENTS")
print("=" * 60)
elast_events = []
with open(f'{RUN}/elasticity_events.csv') as f:
    reader = csv.DictReader(f)
    elast_events = list(reader)
print(f'  Total elasticity events: {len(elast_events)}')
if elast_events:
    header = list(elast_events[0].keys())
    print(f'  Columns: {header}')
    # Sample events
    for e in elast_events[:5]:
        print(f'  {e}')
    # Count by type
    etypes = collections.Counter(e.get('event_type', e.get('type', 'unknown')) for e in elast_events)
    print(f'  Event types: {dict(etypes)}')

# ── 5. Reverse_hotspot deep dive ──────────────────────────────
print("\n" + "=" * 60)
print("5. REVERSE_HOTSPOT DEEP DIVE")
print("=" * 60)
rh_fails_by_lan = collections.Counter()
rh_fails_by_endpoint = collections.Counter()
rh_total_by_lan = collections.Counter()
rh_timestamps = []
rh_ok_timestamps = []
with open(f'{RUN}/client_requests.csv') as f:
    for row in csv.DictReader(f):
        if row['phase'] == 'reverse_hotspot':
            lan = row['client_lan']
            rh_total_by_lan[lan] += 1
            if row['http_status'] != '200':
                rh_fails_by_lan[lan] += 1
                rh_fails_by_endpoint[row['endpoint']] += 1
                rh_timestamps.append(row['timestamp'])
            else:
                rh_ok_timestamps.append(row['timestamp'])

print(f'  LAN1 failure: {rh_fails_by_lan.get("lan1", 0)}/{rh_total_by_lan.get("lan1", 0)}')
print(f'  LAN2 failure: {rh_fails_by_lan.get("lan2", 0)}/{rh_total_by_lan.get("lan2", 0)}')
print(f'  By endpoint: {dict(rh_fails_by_endpoint.most_common(5))}')
if rh_timestamps and rh_ok_timestamps:
    first_fail = min(rh_timestamps)
    last_ok = max(rh_ok_timestamps)
    print(f'  First failure: {first_fail}')
    print(f'  Last success:  {last_ok}')
    # Check if failures are concentrated in time
    t0 = datetime.fromisoformat(rh_timestamps[0].replace('Z', '+00:00'))
    tn = datetime.fromisoformat(rh_timestamps[-1].replace('Z', '+00:00'))
    print(f'  Failure time span: {tn - t0}')

print("\n" + "=" * 60)
print("6. SUMMARY vs EXPERIMENT PLAN")
print("=" * 60)
print(f"""
  Criterion 1 (overall ≤3%):         {fail/total*100:.1f}% {'✅' if fail/total <= 0.03 else '❌'}
  Criterion 2 (compute ≤5%):         {phase_stats.get('compute_ramp', {}).get('fail', 0) + phase_stats.get('compute_spike', {}).get('fail', 0) + phase_stats.get('sustained_plateau', {}).get('fail', 0)}/{phase_stats.get('compute_ramp', {}).get('total', 0) + phase_stats.get('compute_spike', {}).get('total', 0) + phase_stats.get('sustained_plateau', {}).get('total', 0):.1%}
  Criterion 7 (conntrack >0):        n1={ct_max_n1}, n2={ct_max_n2} {'✅' if ct_max_n1 > 0 and ct_max_n2 > 0 else '❌'}
  Criterion 6 (rule deleted ≥1):     lan1=0, lan2=0 (no unregisters) ⚠️
""")
