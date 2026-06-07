import csv
from collections import defaultdict
p = defaultdict(lambda: {'o':0,'f':0})
with open('source/scripts/testing/metrics/20260607_144234_current_state_integrated_a/client_requests.csv') as f:
    for r in csv.DictReader(f):
        s = int(r['http_status'])
        if 200<=s<300: p[r['phase']]['o']+=1
        else: p[r['phase']]['f']+=1
order = ['baseline','local_moderate','storage_stress','cross_region_hotspot','inter_hotspot_cooldown','reverse_hotspot','compute_ramp','compute_spike','sustained_plateau','demand_drop']
for ph in order:
    if ph in p:
        d=p[ph]; t=d['o']+d['f']; rt=d['f']/t*100 if t else 0
        print('  %-30s %6d/%6d  %6.1f%%' % (ph, d['f'], t, rt))
to=sum(v['o'] for v in p.values()); tf=sum(v['f'] for v in p.values()); tt=to+tf
print('OVERALL: %d reqs, %d fail (%.1f%%)' % (tt, tf, tf/tt*100))
