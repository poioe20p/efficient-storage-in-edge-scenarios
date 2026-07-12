import csv
from collections import defaultdict

RUN = '/home/testop/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/20260711_003240_rq3_v5_tier1/client_requests.csv'

phases = defaultdict(lambda: {'total': 0, 'succ': 0})
statuses = defaultdict(int)
latencies = {'<1s': 0, '1-5s': 0, '5-30s': 0, '30-60s': 0, '60s+': 0}

with open(RUN) as f:
    for row in csv.DictReader(f):
        if 'lan1' not in row['client_ns']:
            continue
        ph = row['phase']
        phases[ph]['total'] += 1
        if row['http_status'] == '200':
            phases[ph]['succ'] += 1
        if ph == 'cross_region_pressure':
            statuses[row['http_status']] += 1
            lat = float(row['latency_s'])
            if lat < 1: latencies['<1s'] += 1
            elif lat < 5: latencies['1-5s'] += 1
            elif lat < 30: latencies['5-30s'] += 1
            elif lat < 60: latencies['30-60s'] += 1
            else: latencies['60s+'] += 1

print("=== Tier1 LAN1 per-phase ===")
for ph in sorted(phases):
    t = phases[ph]
    print(f"  {ph}: {t['succ']}/{t['total']} ({t['succ']*100/t['total']:.1f}%)")

print("\n=== Tier1 LAN1 status codes (cross_region_pressure) ===")
for s in sorted(statuses, key=lambda x: int(x)):
    print(f"  status={s}: {statuses[s]}")

print("\n=== Tier1 LAN1 latency distribution (cross_region_pressure) ===")
for k in latencies:
    print(f"  {k}: {latencies[k]}")
