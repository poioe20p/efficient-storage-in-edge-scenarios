#!/usr/bin/env python3
"""Test MIN_READS_TO_ACTIVATE gate against actual telemetry from a run log."""
import json, sys, os

sys.path.insert(0, os.path.expanduser('~/efficient-storage-in-edge-scenarios/source/sdn_controller'))
from telemetry.models import TelemetrySummary

log_path = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    '~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/20260709_081240_rq3_v2_tier2_cold/controller_lan2.log'
)

_WRITE_OPS = frozenset({
    "insert", "insert_one", "insert_many",
    "update", "update_one", "update_many",
    "delete", "delete_one", "delete_many",
    "find_one_and_update", "find_one_and_replace", "find_one_and_delete",
})

peer_lan = "lan1"  # N2's peer
MIN_READS = 50
pass_count = 0
block_count = 0

with open(log_path) as f:
    content = f.read()

blocks = content.split('telemetry full summary:')
for block in blocks[1:]:
    if 'op_counters' not in block:
        continue
    json_start = block.find('{')
    if json_start < 0:
        continue
    depth = 0
    json_end = json_start
    for i in range(json_start, len(block)):
        if block[i] == '{':
            depth += 1
        elif block[i] == '}':
            depth -= 1
            if depth == 0:
                json_end = i + 1
                break
    json_str = block[json_start:json_end]
    try:
        data = json.loads(json_str)
        summary = TelemetrySummary.model_validate(data)
        for mac, srv in summary.servers.items():
            oc = srv.op_counters
            if peer_lan not in oc or not oc[peer_lan]:
                continue
            xreg_reads = 0
            for coll, ops in oc[peer_lan].items():
                for op, count in ops.items():
                    if op not in _WRITE_OPS:
                        xreg_reads += count
            passed = xreg_reads >= MIN_READS
            if passed:
                pass_count += 1
            else:
                block_count += 1
            if pass_count + block_count <= 10:
                print(f'  xreg_reads={xreg_reads} {"PASS" if passed else "BLOCK"}  ops={oc[peer_lan]}')
            break  # one server per window
    except Exception as e:
        pass

print(f'\nTotal: {pass_count} PASS, {block_count} BLOCK (threshold={MIN_READS})')
