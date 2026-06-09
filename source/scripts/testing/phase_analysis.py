import csv, collections, sys

path = sys.argv[1] if len(sys.argv) > 1 else 'source/scripts/testing/metrics/20260608_112947_conntrack_experiment/client_requests.csv'

codes = collections.Counter()
phases = collections.Counter()
phase_stats = {}  # phase -> {total, fail_0, fail_503, ok}

with open(path) as f:
    r = csv.DictReader(f)
    for row in r:
        code = row['http_status']
        phase = row['phase']
        codes[code] += 1
        phases[phase] += 1
        if phase not in phase_stats:
            phase_stats[phase] = {'total': 0, 'ok': 0, 'fail_0': 0, 'fail_503': 0}
        phase_stats[phase]['total'] += 1
        if code == '200':
            phase_stats[phase]['ok'] += 1
        elif code == '0':
            phase_stats[phase]['fail_0'] += 1
        elif code == '503':
            phase_stats[phase]['fail_503'] += 1

print('=== Overall ===')
total = sum(codes.values())
fail = sum(c for code, c in codes.items() if code != '200')
print(f'  Total: {total}, OK: {codes["200"]}, Fail: {fail} ({fail/total*100:.1f}%)')
print(f'  HTTP 0: {codes.get("0", 0)}, HTTP 503: {codes.get("503", 0)}')
print()

print('=== Per-Phase ===')
print(f'  {"Phase":30s} {"Total":>8s} {"OK":>8s} {"Fail":>8s} {"Rate":>8s} {"HTTP0":>8s} {"HTTP503":>8s}')
print(f'  {"-"*30} {"-"*8} {"-"*8} {"-"*8} {"-"*8} {"-"*8} {"-"*8}')
for phase in sorted(phase_stats):
    ps = phase_stats[phase]
    f = ps['fail_0'] + ps['fail_503']
    rate = f / ps['total'] * 100
    print(f'  {phase:30s} {ps["total"]:>8d} {ps["ok"]:>8d} {f:>8d} {rate:>7.1f}% {ps["fail_0"]:>8d} {ps["fail_503"]:>8d}')

# Check if storage stress phases have lower failure than compute
print()
print('=== Phase Categories ===')
storage_phases = ['storage_stress', 'cross_region_hotspot', 'reverse_hotspot']
compute_phases = ['compute_ramp', 'compute_spike', 'sustained_plateau']

for cat, phases_list in [('Storage-churn', storage_phases), ('Compute', compute_phases)]:
    t = sum(phase_stats[p]['total'] for p in phases_list if p in phase_stats)
    f = sum(phase_stats[p]['fail_0'] + phase_stats[p]['fail_503'] for p in phases_list if p in phase_stats)
    print(f'  {cat}: {f}/{t} = {f/t*100:.1f}%' if t > 0 else f'  {cat}: no data')
