#!/usr/bin/env python3
"""Extract cross-region read counts per telemetry window from controller log."""
import json, sys
from collections import defaultdict

phase_reads = defaultdict(list)
current_phase = None

with open(sys.argv[1]) as f:
    in_json = False
    json_lines = []
    for line in f:
        if 'Phase 1/4' in line:
            current_phase = 'baseline'
        elif 'Phase 2/4' in line:
            current_phase = 'cross_region_pressure'
        elif 'Phase 3/4' in line:
            current_phase = 'sustained_pressure'
        elif 'Phase 4/4' in line:
            current_phase = 'cooldown'

        if 'telemetry full summary' in line:
            in_json = True
            json_lines = []
            continue
        if in_json:
            if line.strip().startswith('2026-') or line.strip().startswith('==>'):
                in_json = False
                try:
                    data = json.loads(''.join(json_lines))
                    for srv in data.get('servers', {}).values():
                        for peer_lan, colls in srv.get('op_counters', {}).items():
                            if peer_lan == data.get('network_id', ''):
                                continue
                            total = sum(
                                sum(ops.values()) if isinstance(ops, dict) else 0
                                for ops in colls.values()
                            )
                            if total > 0 and current_phase:
                                phase_reads[current_phase].append(total)
                except Exception:
                    pass
            else:
                json_lines.append(line)

for phase in ['baseline', 'cross_region_pressure', 'sustained_pressure', 'cooldown']:
    reads = phase_reads.get(phase, [])
    if reads:
        s = sorted(reads)
        n = len(s)
        print(f'{phase}: n={n} min={min(s)} p25={s[n//4]} p50={s[n//2]} p75={s[3*n//4]} max={max(s)} avg={sum(s)/n:.0f}')
        print(f'  first 10: {s[:10]}')
        print(f'  last 10:  {s[-10:]}')
    else:
        print(f'{phase}: no data')
