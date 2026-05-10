#!/bin/bash

# ============================================================================
# run_experiment.sh
#
# Full experiment orchestration for the phased edge IoT workload.
# Runs in order:
#   1. Create test client namespaces (LAN 1 + LAN 2)
#   2. Seed MongoDB: sensor_reports → device_registry → create_indexes
#   3. Export workload snapshot (devices + nodes → JSON)
#   4. Start resource stats collector (ZMQ subscriber → CSV)
#   5. Run traffic generator (phased HTTP load from namespaces)
#   6. Stop resource stats collector
#
# Edit the configuration variables below to match your deployment.
#
# Usage:
#   sudo ./run_experiment.sh [--batch-dir batch4] [--run-label c0] [--skip-clients] [--skip-seed] [--skip-snapshot]
#
# Flags (all optional):
#   --batch-dir DIR     Place the run folder under metrics/DIR/ (example: metrics/batch4/20260501_153012_c0)
#   --run-label LABEL    Append a config label to the metrics folder name (example: 20260501_153012_c0)
#   --skip-clients       Skip step 1 (test namespaces already created)
#   --skip-seed          Skip step 2 (data already seeded)
#   --skip-snapshot      Skip step 3 (snapshot already exported)
#   --snapshot-dir DIR   Override snapshot directory (default: REPO_ROOT/data/workload_snapshot)
#   --dry-run            Pass --dry-run to traffic_generator (no real requests)
# ============================================================================

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
readonly REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
readonly CONTROLLER_ENV_SOURCE="${SCRIPTS_DIR}/osken-controller.env"
readonly RUN_TIMESTAMP="$(date +%Y%m%d_%H%M%S)"

# ---------------------------------------------------------------------------
# Configuration — edit these to match your experiment
# ---------------------------------------------------------------------------

# Number of test client namespaces per LAN
CLIENTS_PER_LAN=3

# Namespace prefixes — produces lan1_client_1, lan1_client_2 … lan2_client_1, lan2_client_2 …
PREFIX_LAN1="lan1_client_"
PREFIX_LAN2="lan2_client_"

# Number of devices and nodes to seed per region
SEED_DEVICES=100
SEED_NODES=40

# MongoDB URIs for each region's primary
MONGO_LAN1="mongodb://10.0.0.4:27018/"
MONGO_LAN2="mongodb://10.0.1.4:27018/"

# Snapshot output directory
SNAPSHOT_DIR="${SCRIPT_DIR}/data/workload_snapshot"

# VIP_SERVER address
VIP="10.0.0.253:5000"

# Resource stats collector — ZMQ PUB addresses of the two aggregators
LAN1_PUB="tcp://10.0.0.5:5556"
LAN2_PUB="tcp://10.0.1.5:5556"
# SDN controller coordinator-state PUB endpoints (mirrors
# COORDINATOR_STATE_PUB_PORT in build_network_setup.sh: 5561=lan1, 5562=lan2).
# Both controllers run with --network host so 127.0.0.1 reaches them.
LAN1_COORD_PUB="tcp://127.0.0.1:5561"
LAN2_COORD_PUB="tcp://127.0.0.1:5562"

# Container life-cycle poller (diff-based docker ps)
CONTAINER_EVENTS_INTERVAL="${CONTAINER_EVENTS_INTERVAL:-1.0}"
CONTAINER_EVENTS_FILTER="${CONTAINER_EVENTS_FILTER:-^(edge_|sel_sync_|nat-router|osken|local_state_)}"

# PID of the background stats collector (set by run_collect_stats)
STATS_PID=""

# PIDs for controller log capture (set by run_capture_controller_logs)
CONTROLLER_LOG_PID1=""
CONTROLLER_LOG_PID2=""

# PID of the container event poller (set by run_poll_container_events)
CONTAINER_EVENTS_PID=""

# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------

SKIP_CLIENTS=false
SKIP_SEED=false
SKIP_SNAPSHOT=false
DRY_RUN=false
BATCH_DIR=""
RUN_LABEL=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --batch-dir)    shift; BATCH_DIR="$1" ;;
        --batch-dir=*)  BATCH_DIR="${1#*=}"    ;;
        --run-label)     shift; RUN_LABEL="$1"  ;;
        --run-label=*)   RUN_LABEL="${1#*=}"    ;;
        --skip-clients)   SKIP_CLIENTS=true  ;;
        --skip-seed)      SKIP_SEED=true     ;;
        --skip-snapshot)  SKIP_SNAPSHOT=true ;;
        --dry-run)        DRY_RUN=true       ;;
        --snapshot-dir)   shift; SNAPSHOT_DIR="$1" ;;
        --snapshot-dir=*) SNAPSHOT_DIR="${1#*=}" ;;
        -h|--help)
            sed -n '/^# Usage/,/^# -----/p' "$0" | grep '^#' | sed 's/^# *//'
            exit 0
            ;;
        *)
            echo "ERROR: unknown flag: $1" >&2
            exit 1
            ;;
    esac
    shift
done

if [[ -n "$RUN_LABEL" ]] && [[ ! "$RUN_LABEL" =~ ^[A-Za-z0-9][A-Za-z0-9_-]*$ ]]; then
    echo "ERROR: invalid --run-label '$RUN_LABEL' (allowed: letters, numbers, '_' and '-')" >&2
    exit 1
fi

if [[ -n "$BATCH_DIR" ]] && [[ ! "$BATCH_DIR" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)*$ ]]; then
    echo "ERROR: invalid --batch-dir '$BATCH_DIR' (allowed: relative path segments with letters, numbers, '.', '_' and '-')" >&2
    exit 1
fi

readonly RUN_ID="${RUN_TIMESTAMP}${RUN_LABEL:+_${RUN_LABEL}}"
readonly METRICS_ROOT="${SCRIPT_DIR}/metrics"
readonly RUN_PARENT_DIR="${METRICS_ROOT}${BATCH_DIR:+/${BATCH_DIR}}"
readonly RUN_DIR="${RUN_PARENT_DIR}/${RUN_ID}"
readonly CONTROLLER_ENV_SNAPSHOT_OUTPUT="${RUN_DIR}/controller_env_snapshot.env"

# Traffic generator config and output
PHASES_CONFIG="${SCRIPT_DIR}/phases.json"
PHASES_SNAPSHOT_OUTPUT="${RUN_DIR}/phases_snapshot.json"
METRICS_OUTPUT="${RUN_DIR}/client_requests.csv"

# Resource stats collector outputs
RESOURCE_STATS_OUTPUT="${RUN_DIR}/resource_stats.csv"
PHASE_FILE="${RUN_DIR}/current_phase.txt"

# Container life-cycle poller (diff-based docker ps)
CONTAINER_EVENTS_OUTPUT="${RUN_DIR}/container_events.csv"

# Controller log capture — saved alongside resource stats
CONTROLLER_LOG_LAN1="${RUN_DIR}/controller_lan1.log"
CONTROLLER_LOG_LAN2="${RUN_DIR}/controller_lan2.log"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

step() { echo; echo "==> $*"; }
die()  { echo "ERROR: $*" >&2; exit 1; }

prepare_run_outputs() {
    step "Preparing run output folder"
    mkdir -p "$RUN_DIR"
    [[ -f "$PHASES_CONFIG" ]] || die "Phase config not found: $PHASES_CONFIG"
    [[ -f "$CONTROLLER_ENV_SOURCE" ]] || die "Controller env not found: $CONTROLLER_ENV_SOURCE"
    cp "$PHASES_CONFIG" "$PHASES_SNAPSHOT_OUTPUT"
    cp "$CONTROLLER_ENV_SOURCE" "$CONTROLLER_ENV_SNAPSHOT_OUTPUT"
    echo "  Run dir    : ${RUN_DIR}"
    echo "  Batch dir  : ${BATCH_DIR:-<none>}"
    echo "  Run label  : ${RUN_LABEL:-<none>}"
    echo "  Phase copy : ${PHASES_SNAPSHOT_OUTPUT}"
    echo "  Env copy   : ${CONTROLLER_ENV_SNAPSHOT_OUTPUT}"
}

# Build comma-separated namespace name lists for each LAN
# LAN1: lan1_client1, lan1_client2, …
# LAN2: lan2_client1, lan2_client2, …
build_client_lists() {
    local lan1="" lan2="" i
    for ((i = 1; i <= CLIENTS_PER_LAN; i++)); do
        lan1+="${lan1:+,}${PREFIX_LAN1}${i}"
        lan2+="${lan2:+,}${PREFIX_LAN2}${i}"
    done
    CLIENTS_LAN1="$lan1"
    CLIENTS_LAN2="$lan2"
}

# ---------------------------------------------------------------------------
# Step 1 — Create test client namespaces
# ---------------------------------------------------------------------------

run_create_clients() {
    step "Creating test client namespaces"
    local create_script="${REPO_ROOT}/source/scripts/network/clients/create_test_clients.sh"
    [[ -x "$create_script" ]] || die "Not found or not executable: $create_script"

    echo "  LAN 1: ${CLIENTS_PER_LAN} clients (prefix: ${PREFIX_LAN1})"
    bash "$create_script" --lan 1 --count "$CLIENTS_PER_LAN" --prefix "$PREFIX_LAN1"

    echo "  LAN 2: ${CLIENTS_PER_LAN} clients (prefix: ${PREFIX_LAN2})"
    bash "$create_script" --lan 2 --count "$CLIENTS_PER_LAN" --prefix "$PREFIX_LAN2"
}

# ---------------------------------------------------------------------------
# Step 2 — Seed MongoDB
# ---------------------------------------------------------------------------

run_seed() {
    step "Seeding MongoDB"

    echo "  sensor_reports (${SEED_DEVICES} devices/region)"
    python3 "${SCRIPT_DIR}/sensor_reports.py" \
        --mongo-lan1 "$MONGO_LAN1" --mongo-lan2 "$MONGO_LAN2" \
        --devices "$SEED_DEVICES"

    echo "  device_registry (${SEED_NODES} nodes/region, ${SEED_DEVICES} device IDs)"
    python3 "${SCRIPT_DIR}/device_registry.py" \
        --mongo-lan1 "$MONGO_LAN1" --mongo-lan2 "$MONGO_LAN2" \
        --nodes "$SEED_NODES" --devices "$SEED_DEVICES"

    echo "  create_indexes"
    python3 "${SCRIPT_DIR}/create_indexes.py" \
        --mongo-lan1 "$MONGO_LAN1" --mongo-lan2 "$MONGO_LAN2"
}

# ---------------------------------------------------------------------------
# Step 3 — Export workload snapshot
# ---------------------------------------------------------------------------

run_snapshot() {
    step "Exporting workload snapshot → ${SNAPSHOT_DIR}"
    python3 "${SCRIPT_DIR}/export_workload_snapshot.py" \
        --mongo-lan1 "$MONGO_LAN1" --mongo-lan2 "$MONGO_LAN2" \
        --output-dir "$SNAPSHOT_DIR"
}

# ---------------------------------------------------------------------------
# Step 4 — Resource stats collector
# ---------------------------------------------------------------------------

run_collect_stats() {
    step "Starting resource stats collector"
    echo "  LAN1 PUB : ${LAN1_PUB}"
    echo "  LAN2 PUB : ${LAN2_PUB}"
    echo "  LAN1 coord: ${LAN1_COORD_PUB}"
    echo "  LAN2 coord: ${LAN2_COORD_PUB}"
    echo "  Output   : ${RESOURCE_STATS_OUTPUT}"
    python3 "${SCRIPT_DIR}/collect_resource_stats.py" \
        --lan1-pub "$LAN1_PUB" \
        --lan2-pub "$LAN2_PUB" \
        --lan1-coord-pub "$LAN1_COORD_PUB" \
        --lan2-coord-pub "$LAN2_COORD_PUB" \
        --output   "$RESOURCE_STATS_OUTPUT" \
        --phase-file "$PHASE_FILE" &
    STATS_PID=$!
    echo "  Collector PID: ${STATS_PID}"
    sleep 1  # allow ZMQ subscriber handshake to complete before traffic starts
}

stop_collect_stats() {
    [[ -z "${STATS_PID:-}" ]] && return 0
    echo; echo "==> Stopping resource stats collector (PID ${STATS_PID})"
    kill -TERM "$STATS_PID" 2>/dev/null || true
    wait "$STATS_PID" 2>/dev/null || true
    STATS_PID=""
}

# ---------------------------------------------------------------------------
# Step 4b — Capture controller logs (docker logs -f)
# ---------------------------------------------------------------------------

run_capture_controller_logs() {
    step "Capturing controller logs"
    echo "  LAN1 → ${CONTROLLER_LOG_LAN1}"
    echo "  LAN2 → ${CONTROLLER_LOG_LAN2}"
    docker logs -f osken   > "$CONTROLLER_LOG_LAN1" 2>&1 &
    CONTROLLER_LOG_PID1=$!
    docker logs -f osken_2 > "$CONTROLLER_LOG_LAN2" 2>&1 &
    CONTROLLER_LOG_PID2=$!
    echo "  PIDs: ${CONTROLLER_LOG_PID1}, ${CONTROLLER_LOG_PID2}"
}

stop_capture_controller_logs() {
    for pid_var in CONTROLLER_LOG_PID1 CONTROLLER_LOG_PID2; do
        local pid="${!pid_var}"
        [[ -z "${pid:-}" ]] && continue
        kill -TERM "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
        eval "$pid_var="
    done
}

# ---------------------------------------------------------------------------
# Step 4c — Container life-cycle poller (diff-based docker ps)
# ---------------------------------------------------------------------------

run_poll_container_events() {
    step "Starting container event poller"
    echo "  Interval : ${CONTAINER_EVENTS_INTERVAL}s"
    echo "  Filter   : ${CONTAINER_EVENTS_FILTER}"
    echo "  Output   : ${CONTAINER_EVENTS_OUTPUT}"
    python3 "${SCRIPT_DIR}/poll_container_events.py" \
        --interval     "$CONTAINER_EVENTS_INTERVAL" \
        --filter-regex "$CONTAINER_EVENTS_FILTER" \
        --phase-file   "$PHASE_FILE" \
        --output       "$CONTAINER_EVENTS_OUTPUT" &
    CONTAINER_EVENTS_PID=$!
    echo "  Poller PID: ${CONTAINER_EVENTS_PID}"
}

stop_poll_container_events() {
    [[ -z "${CONTAINER_EVENTS_PID:-}" ]] && return 0
    echo; echo "==> Stopping container event poller (PID ${CONTAINER_EVENTS_PID})"
    kill -TERM "$CONTAINER_EVENTS_PID" 2>/dev/null || true
    wait "$CONTAINER_EVENTS_PID" 2>/dev/null || true
    CONTAINER_EVENTS_PID=""
}

# ---------------------------------------------------------------------------
# Step 5 — Run traffic generator
# ---------------------------------------------------------------------------

run_traffic() {
    step "Running traffic generator"
    echo "  LAN1 clients : ${CLIENTS_LAN1}"
    echo "  LAN2 clients : ${CLIENTS_LAN2}"
    echo "  Config       : ${PHASES_CONFIG}"
    echo "  Output       : ${METRICS_OUTPUT}"

    local extra_flags=()
    "$DRY_RUN" && extra_flags+=("--dry-run")

    python3 "${SCRIPT_DIR}/traffic_generator.py" \
        --config        "$PHASES_CONFIG" \
        --clients-lan1  "$CLIENTS_LAN1" \
        --clients-lan2  "$CLIENTS_LAN2" \
        --snapshot-dir  "$SNAPSHOT_DIR" \
        --output        "$METRICS_OUTPUT" \
        --vip           "$VIP" \
        "${extra_flags[@]}"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

build_client_lists

echo "======================================================"
echo " Edge IoT Experiment — Full Run"
echo "======================================================"
echo " Batch dir   : ${BATCH_DIR:-<none>}"
echo " Clients/LAN : ${CLIENTS_PER_LAN}  (${CLIENTS_LAN1} | ${CLIENTS_LAN2})"
echo " Devices/LAN : ${SEED_DEVICES}"
echo " Nodes/LAN   : ${SEED_NODES}"
echo " Snapshot    : ${SNAPSHOT_DIR}"
echo " Output      : ${METRICS_OUTPUT}"
echo " Resource    : ${RESOURCE_STATS_OUTPUT}"
echo " Phase file  : ${PHASE_FILE}"
echo " VIP         : ${VIP}"
echo " Dry-run     : ${DRY_RUN}"
echo "======================================================"

# Stop the stats collector on any exit (normal, error, or signal)
trap 'stop_capture_controller_logs; stop_poll_container_events; stop_collect_stats' EXIT

prepare_run_outputs
"$SKIP_CLIENTS"  || run_create_clients
"$SKIP_SEED"     || run_seed
"$SKIP_SNAPSHOT" || run_snapshot
run_collect_stats
run_capture_controller_logs
run_poll_container_events
run_traffic
stop_poll_container_events
stop_collect_stats

step "Experiment complete"
echo "Results        : ${METRICS_OUTPUT}"
echo "Resource stats : ${RESOURCE_STATS_OUTPUT}"
echo "Container events: ${CONTAINER_EVENTS_OUTPUT}"
echo "Phase config   : ${PHASES_SNAPSHOT_OUTPUT}"
echo "Controller logs: ${CONTROLLER_LOG_LAN1}"
echo "               : ${CONTROLLER_LOG_LAN2}"