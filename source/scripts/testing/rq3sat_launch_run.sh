#!/usr/bin/env bash
# RQ3 saturation re-run launcher (runs on the cloud VM at ~/efficient-storage-in-edge-scenarios).
# usage: bash rq3sat_launch_run.sh <env_file> <label> <seed> <edge_cpus> [extra_make_vars]
#   e.g. bash rq3sat_launch_run.sh rq3sat_direct.env rq3sat_probe_pa 3001 0.25
# Runs the standard prerequisite chain under open-loop at 48 clients
# (CLIENTS=24 per LAN), the saturation workload (phases_rq3_saturation.json),
# Mongo pool 6, and the flow-isolation data path. See
# docs/operation/testing/experiment/rq3_saturation/experiment_plan.md.
#
# IMPORTANT (env propagation): sudo has env_reset, so exported env vars are
# stripped before `make` runs. All launch knobs MUST be make command-line vars
# (make vars survive sudo; exported env vars do not).
# - EDGE_FLOW_ISOLATION=1 MUST be on the make line: build_network_1/2.sh
#   default it to 0, and RQ3 flow isolation requires the STATIC edges to emit
#   request_complete (preflight §4.1). The arm env file carries it for the
#   controller/dynamic edges; the make var covers setup_network.
# - The Mongo data-path knobs MUST be on the make line too: build_network_1/2.sh
#   read ${EDGE_MONGO_MAX_POOL_SIZE:-1} from the shell at setup_network, so
#   base (static) edges get pool 1 unless passed here (G2 calib3 finding).
set -u
cd ~/efficient-storage-in-edge-scenarios || exit 1
ENV_FILE="$1"
LABEL="$2"
SEED="${3:-3001}"
EDGE_CPUS="${4:-0.25}"
EXTRA="${5:-}"
ulimit -n 65535
exec sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE="../../docs/operation/testing/experiment/rq3_saturation/env/$ENV_FILE" \
  RUN_LABEL="$LABEL" \
  PHASES_CONFIG=testing/phases_override/phases_rq3_saturation.json \
  CLIENTS=24 CONTENT_ITEMS=3000 USERS=100 DATA_SEED=42 \
  TRAFFIC_DRIVER_MODE=open_loop CURL_MAX_TIME=300 INFLIGHT_WINDOW=1024 DRAIN_S=30 \
  STORAGE_CPUS=0.08 EDGE_CPUS="$EDGE_CPUS" WAN_RTT_MS=185 RANDOM_SEED="$SEED" \
  EDGE_MONGO_READ_PREFERENCE=secondaryPreferred EDGE_MONGO_MAX_POOL_SIZE=6 \
  VIP_DATA_PER_CONNECTION_FLOWS=1 EDGE_FLOW_ISOLATION=1 \
  $EXTRA \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
