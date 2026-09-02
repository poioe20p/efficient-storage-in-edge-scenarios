#!/usr/bin/env bash
# research_q3 release-mechanism comparison launcher (runs on the cloud VM at
# ~/efficient-storage-in-edge-scenarios).
# usage: bash research_q3_launch_run.sh <env_file> <label> <seed>
#   e.g. bash research_q3_launch_run.sh arm_stabilized.env rq3rel_cal_s1 42
# research_q3 arms: RELEASE_MECHANISM in {off, drained, immediate, stabilized}
# (docs/operation/testing/experiment/research_q3). Resource shaping matches the
# RQ3 v3 storage-constrained regime (EDGE_CPUS=0.08 / STORAGE_CPUS=0.25) so the
# release mechanism is the only variable axis between runs.
# Uses the canonical phases.json (no PHASES_CONFIG override).
set -u
cd ~/efficient-storage-in-edge-scenarios || exit 1
ENV_FILE="$1"
LABEL="$2"
SEED="${3:-42}"
ulimit -n 65535
exec sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE="../../docs/operation/testing/experiment/research_q3/env/$ENV_FILE" \
  RUN_LABEL="$LABEL" \
  CLIENTS=24 CONTENT_ITEMS=3000 USERS=100 DATA_SEED=42 \
  TRAFFIC_DRIVER_MODE=open_loop CURL_MAX_TIME=300 INFLIGHT_WINDOW=1024 DRAIN_S=30 \
  STORAGE_CPUS=0.25 EDGE_CPUS=0.08 WAN_RTT_MS=185 RANDOM_SEED="${SEED:-42}" \
  EDGE_MONGO_READ_PREFERENCE=secondaryPreferred EDGE_MONGO_MAX_POOL_SIZE=6 \
  VIP_DATA_PER_CONNECTION_FLOWS=1 EDGE_FLOW_ISOLATION=1 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
