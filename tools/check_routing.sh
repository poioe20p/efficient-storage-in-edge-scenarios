#!/bin/bash
BASE="source/scripts/testing/metrics/20260607_154628_current_state_integrated_b"
echo "=== VIP routing changes (total) ==="
grep -c "dnat/snat installed\|dnat/snat updated\|dnat/snat removed" $BASE/controller_lan1.log $BASE/controller_lan2.log
echo ""
echo "=== Routing changes per phase (lan1+lan2) ==="
for phase in storage_stress cross_region_hotspot reverse_hotspot compute_ramp compute_spike sustained_plateau demand_drop; do
  count=$(grep "dnat/snat installed" $BASE/controller_lan1.log $BASE/controller_lan2.log 2>/dev/null | grep -c "$phase" 2>/dev/null || echo 0)
  echo "  $phase: $count"
done
echo ""
echo "=== Sample DNAT changes during compute phases ==="
grep "dnat/snat" $BASE/controller_lan1.log $BASE/controller_lan2.log | grep -E "compute_ramp|compute_spike|sustained_plateau" | head -5
echo ""
echo "=== Dashboard failure sample (n1) ==="
grep "ERROR db_failure.*dashboard" $BASE/service_logs/edge_server_n1.log | head -3
echo ""
echo "=== Failure tdados_s values (n1, first 10) ==="
grep "ERROR db_failure.*dashboard" $BASE/service_logs/edge_server_n1.log | head -10 | grep -oP 'tdados_s=\K[0-9.]+'
