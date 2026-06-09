#!/bin/bash
echo '=== Run A — epoch rotations ==='
for log in ~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/20260608_131830_current_state_integrated_a/service_logs/edge_server_n*.log; do
  name=$(basename $log)
  count=$(grep -c 'epoch.*rotation\|recovery_epoch_failed\|AutoReconnect' $log 2>/dev/null || echo 0)
  echo "  ${name}: ${count}"
done

echo ''
echo '=== Run B — epoch rotations ==='
for log in ~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/20260608_140225_current_state_integrated_b/service_logs/edge_server_n*.log; do
  name=$(basename $log)
  count=$(grep -c 'epoch.*rotation\|recovery_epoch_failed\|AutoReconnect' $log 2>/dev/null || echo 0)
  echo "  ${name}: ${count}"
done

echo ''
echo '=== Run A — mechanism stats ==='
python3 -c "
import csv
with open('/home/testop/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/20260608_131830_current_state_integrated_a/resource_stats.csv') as f:
    r = csv.DictReader(f)
    ct1_max = ct2_max = sc_max = sv_max = 0
    sel_active = False
    for row in r:
        ct1_max = max(ct1_max, int(row.get('conntrack_entries_n1', 0) or 0))
        ct2_max = max(ct2_max, int(row.get('conntrack_entries_n2', 0) or 0))
        sc_max = max(sc_max, int(row.get('storage_count', 0) or 0))
        sv_max = max(sv_max, int(row.get('server_count', 0) or 0))
        if (row.get('tier1_lifecycle_active_count', '') or '').strip():
            sel_active = True
    print(f'  Conntrack max: n1={ct1_max}, n2={ct2_max}')
    print(f'  Storage max: {sc_max}, Server max: {sv_max}')
    print(f'  Tier 1 selective-sync active: {sel_active}')
"

echo ''
echo '=== Run B — mechanism stats ==='
python3 -c "
import csv
with open('/home/testop/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/20260608_140225_current_state_integrated_b/resource_stats.csv') as f:
    r = csv.DictReader(f)
    ct1_max = ct2_max = sc_max = sv_max = 0
    sel_active = False
    for row in r:
        ct1_max = max(ct1_max, int(row.get('conntrack_entries_n1', 0) or 0))
        ct2_max = max(ct2_max, int(row.get('conntrack_entries_n2', 0) or 0))
        sc_max = max(sc_max, int(row.get('storage_count', 0) or 0))
        sv_max = max(sv_max, int(row.get('server_count', 0) or 0))
        if (row.get('tier1_lifecycle_active_count', '') or '').strip():
            sel_active = True
    print(f'  Conntrack max: n1={ct1_max}, n2={ct2_max}')
    print(f'  Storage max: {sc_max}, Server max: {sv_max}')
    print(f'  Tier 1 selective-sync active: {sel_active}')
"

echo ''
echo '=== Container event types ==='
echo 'Run A:'
awk -F',' 'NR>1 {print $4}' ~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/20260608_131830_current_state_integrated_a/container_events.csv | sort | uniq -c | sort -rn
echo 'Run B:'
awk -F',' 'NR>1 {print $4}' ~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/20260608_140225_current_state_integrated_b/container_events.csv | sort | uniq -c | sort -rn
