#!/usr/bin/env bash
# RQ1 v2 run launcher (runs on the cloud VM at ~/efficient-storage-in-edge-scenarios).
# usage: bash rq1_launch_run.sh <env_file> <label> <seed> [extra_make_vars]
# Runs the standard prerequisite chain under open-loop with the calibrated
# scale, raising the fd limit so INFLIGHT_WINDOW=1024 per-client sockets cannot
# exhaust the worker's descriptors. All campaign runs use this launcher.
# Arm C (poll) must pass POLL_INTERVAL_S=30 as extra_make_vars — build_network
# reads it from the shell and Docker -e overrides the env file.
#
# IMPORTANT (env propagation): sudo has env_reset, so exported env vars are
# stripped before `make` runs. All launch knobs MUST be passed as make
# command-line variables (make vars survive sudo; exported env vars do not).
# The Mongo data-path knobs MUST be on the make line too: build_network_1/2.sh
# read ${EDGE_MONGO_MAX_POOL_SIZE:-1} from the shell at setup_network, so base
# (static) edge servers get pool 1 unless these are passed here (G2 calib3
# finding: dynamic spawns had pool 6 via the env file, but base servers stayed
# at pool 1 -> DB serialization -> latency collapse persisted).
#
# Pool size (2026-08-05 G2 sweep): pool 12 (rate 2.0/1.5 + churn guard) still
# collapsed (p50 16-17s) — 4 edges x 12 = 48 concurrent Mongo ops thrash the
# storage tier at STORAGE_CPUS=0.08. Reverted to pool 6 (6 conns/edge = RQ2's
# proven config: ba_db_cal4 at rate 1.5 completes 87%/p50 2s). Rate 1.5 + pool
# 6 + churn guard = the RQ2-comparable bounded-overload test.
set -u
cd ~/efficient-storage-in-edge-scenarios || exit 1
ENV_FILE="$1"
LABEL="$2"
SEED="${3:-2001}"
EXTRA="${4:-}"
ulimit -n 65535
exec sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE="../../docs/operation/testing/experiment/v2/rq1/env/$ENV_FILE" \
  RUN_LABEL="$LABEL" \
  PHASES_CONFIG=testing/phases_override/phases_rq1_stress_plateau.json \
  CLIENTS=24 CONTENT_ITEMS=3000 USERS=100 DATA_SEED=42 \
  TRAFFIC_DRIVER_MODE=open_loop CURL_MAX_TIME=300 INFLIGHT_WINDOW=1024 DRAIN_S=30 \
  STORAGE_CPUS=0.08 EDGE_CPUS=0.15 WAN_RTT_MS=185 RANDOM_SEED="$SEED" \
  EDGE_MONGO_READ_PREFERENCE=secondaryPreferred EDGE_MONGO_MAX_POOL_SIZE=6 VIP_DATA_PER_CONNECTION_FLOWS=1 \
  $EXTRA \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
