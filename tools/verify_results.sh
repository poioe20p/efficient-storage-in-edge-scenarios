#!/bin/bash
D="$HOME/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics"
for RUN in 20260708_002403_rq3_ground_rate_r4 20260708_005504_rq3_ground_cold 20260708_012512_rq3_ground_warm 20260708_015444_rq3_ground_tier1 20260708_022352_rq3_ground_samelan 20260708_025444_rq3_ground_reverse; do
  RD="$D/$RUN"
  echo "=== $RUN ==="
  echo "TB_LAN1=$(grep -c Traceback $RD/controller_lan1.log 2>/dev/null || echo 0)"
  echo "TB_LAN2=$(grep -c Traceback $RD/controller_lan2.log 2>/dev/null || echo 0)"
  echo "COLD_LAN1=$(grep -c 'cross-region-cold.*SPAWN' $RD/controller_lan1.log 2>/dev/null || echo 0)"
  echo "COLD_LAN2=$(grep -c 'cross-region-cold.*SPAWN' $RD/controller_lan2.log 2>/dev/null || echo 0)"
  echo "RESERVE_L2=$(grep -c 'cross-region-reserve' $RD/controller_lan2.log 2>/dev/null || echo 0)"
  echo "TIER1_L2=$(grep -cE '(PromotionCoordinator|tier1|SelectiveSync)' $RD/controller_lan2.log 2>/dev/null || echo 0)"
  echo "NR_L2=$(grep -c '\[node_ready\]' $RD/controller_lan2.log 2>/dev/null || echo 0)"
  echo "CROSSREG_L2=$(grep -c 'cross-region' $RD/controller_lan2.log 2>/dev/null || echo 0)"
  echo ""
done
