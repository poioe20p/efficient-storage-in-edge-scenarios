import csv, collections

codes = collections.Counter()
phases = collections.Counter()
failures = []

import sys
path = sys.argv[1] if len(sys.argv) > 1 else 'source/scripts/testing/metrics/20260608_112947_conntrack_experiment/client_requests.csv'
with open(path) as f:
    r = csv.DictReader(f)
    for row in r:
        codes[row['http_status']] += 1
        phases[row['phase']] += 1
        if row['http_status'] != '200':
            failures.append(row)

print('=== HTTP Codes ===')
for code, count in codes.most_common():
    print(f'  {code}: {count}')
total = sum(codes.values())
print(f'  TOTAL: {total}')
print()

print('=== Phases ===')
for phase, count in phases.most_common():
    print(f'  {phase}: {count}')
print()

fail = sum(c for code, c in codes.items() if code != '200')
print(f'Failure rate: {fail}/{total} = {fail/total*100:.1f}%')
print()

if failures:
    print('=== Non-200 requests ===')
    for row in failures[:20]:
        print(f"  {row['timestamp'][:19]} {row['phase']:25s} {row['endpoint']:20s} HTTP={row['http_status']:4s} {row['latency_s']}s")
