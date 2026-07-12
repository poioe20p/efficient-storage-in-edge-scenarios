import json, sys

for label, path in [
    ('Cold', '/home/testop/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/20260710_232625_rq3_v5_tier2_cold/controller_lan2.log'),
    ('Warm', '/home/testop/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/20260710_235938_rq3_v5_tier2_warm/controller_lan2.log'),
]:
    with open(path) as f:
        found = 0
        for line in f:
            if '"servers"' in line and '"op_counters"' in line and '"lan1"' in line:
                d = json.loads(line.strip())
                servers = d.get('servers', {})
                for sid, srv in servers.items():
                    oc = srv.get('op_counters', {})
                    ld = oc.get('lan1', {})
                    if ld:
                        ci = ld.get('content_items', {})
                        reads = sum(ci.values())
                        print(f'{label} [{found}] srv={sid[:30]} lan1_reads={reads} ops={list(ci.keys())}')
                        found += 1
                        if found >= 3:
                            break
                if found >= 3:
                    break
        if found == 0:
            print(f'{label}: NO entries with lan1 in op_counters found')
