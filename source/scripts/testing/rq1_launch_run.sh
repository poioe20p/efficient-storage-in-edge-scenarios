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
# proven config: ba_db_cal4 at rate 1.5 completes 87%/p50 2s).
#
# Plateau calibration (2026-08-05, rq1_g2_rate15_p6 FAIL): pool 6 + rate 1.5 +
# churn guard still collapsed (p50 16s, timeout 66-68%) with a STABLE fleet ->
# pool size disproved as root cause. Root cause re-investigation: the compute
# tier is the bottleneck (edge CPU 55-73% med, peaks 99% at EDGE_CPUS=0.15),
# not storage. feed_ranking actually costs 3 DB ops (1 user_profiles + 1
# content_items.find per LAN x 2) not 2 -> plateau demand = 54 DB ops/s/LAN at
# rate 1.5, ~29% above RQ2's proven ~42. Fixes applied together: rate 1.5->1.2
# (~45 DB ops/s/LAN — corrected accounting 2026-08-05: content_lookup=2 ops,
# feed_ranking=3 ops; at/above RQ2's ~42 cliff, so plateau stability is watched
# per replicate), mix rebalanced (feed_ranking 0.4->0.2, service_pressure
# 0.3->0.2, content_lookup 0.2->0.35, content_update 0.05->0.15,
# content_aggregate 0.05->0.1), EDGE_CPUS 0.15->0.25.
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
  TRAFFIC_DRIVER_MODE=open_loop CURL_MAX_TIME=300 AIOHTTP_SOCK_CONNECT_TIMEOUT=300 INFLIGHT_WINDOW=1024 DRAIN_S=30 \
  CLIENT_TCP_SYN_RETRIES=9 \
  STORAGE_CPUS=0.08 EDGE_CPUS=0.25 WAN_RTT_MS=185 RANDOM_SEED="$SEED" \
  EDGE_MONGO_READ_PREFERENCE=secondaryPreferred EDGE_MONGO_MAX_POOL_SIZE=6 VIP_DATA_PER_CONNECTION_FLOWS=1 \
  $EXTRA \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
