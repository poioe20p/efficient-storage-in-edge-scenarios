#!/bin/bash

# ============================================================================
# run_experiment.sh
#
# Full experiment orchestration for the 4-phase edge IoT workload.
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
#   sudo ./run_experiment.sh [--skip-clients] [--skip-seed] [--skip-snapshot]
#
# Flags (all optional):
#   --skip-clients       Skip step 1 (test namespaces already created)
#   --skip-seed          Skip step 2 (data already seeded)
#   --skip-snapshot      Skip step 3 (snapshot already exported)
#   --snapshot-dir DIR   Override snapshot directory (default: REPO_ROOT/data/workload_snapshot)
#   --dry-run            Pass --dry-run to traffic_generator (no real requests)
# ============================================================================

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
readonly RUN_ID="$(date +%Y%m%d_%H%M%S)"
readonly RUN_DIR="${SCRIPT_DIR}/metrics/${RUN_ID}"

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

# Traffic generator config and output
PHASES_CONFIG="${SCRIPT_DIR}/phases.json"
PHASES_SNAPSHOT_OUTPUT="${RUN_DIR}/phases_snapshot.json"
METRICS_OUTPUT="${RUN_DIR}/client_requests.csv"

# VIP_SERVER address
VIP="10.0.0.253:5000"

# Resource stats collector — ZMQ PUB addresses of the two aggregators
LAN1_PUB="tcp://10.0.0.5:5556"
LAN2_PUB="tcp://10.0.1.5:5556"
RESOURCE_STATS_OUTPUT="${RUN_DIR}/resource_stats.csv"
PHASE_FILE="${RUN_DIR}/current_phase.txt"

# Controller log capture — saved alongside resource stats
CONTROLLER_LOG_LAN1="${RUN_DIR}/controller_lan1.log"
CONTROLLER_LOG_LAN2="${RUN_DIR}/controller_lan2.log"

# PID of the background stats collector (set by run_collect_stats)
STATS_PID=""

# PIDs for controller log capture (set by run_capture_controller_logs)
CONTROLLER_LOG_PID1=""
CONTROLLER_LOG_PID2=""

# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------

SKIP_CLIENTS=false
SKIP_SEED=false
SKIP_SNAPSHOT=false
DRY_RUN=false

while [[ $# -gt 0 ]]; do
    case "$1" in
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

step() { echo; echo "==> $*"; }
die()  { echo "ERROR: $*" >&2; exit 1; }

prepare_run_outputs() {
    step "Preparing run output folder"
    mkdir -p "$RUN_DIR"
    [[ -f "$PHASES_CONFIG" ]] || die "Phase config not found: $PHASES_CONFIG"
    cp "$PHASES_CONFIG" "$PHASES_SNAPSHOT_OUTPUT"
    echo "  Run dir    : ${RUN_DIR}"
    echo "  Phase copy : ${PHASES_SNAPSHOT_OUTPUT}"
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
    echo "  Output   : ${RESOURCE_STATS_OUTPUT}"
    python3 "${SCRIPT_DIR}/collect_resource_stats.py" \
        --lan1-pub "$LAN1_PUB" \
        --lan2-pub "$LAN2_PUB" \
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
trap 'stop_capture_controller_logs; stop_collect_stats' EXIT

prepare_run_outputs
"$SKIP_CLIENTS"  || run_create_clients
"$SKIP_SEED"     || run_seed
"$SKIP_SNAPSHOT" || run_snapshot
run_collect_stats
run_capture_controller_logs
run_traffic
stop_collect_stats

step "Experiment complete"
echo "Results      : ${METRICS_OUTPUT}"
echo "Resource stats: ${RESOURCE_STATS_OUTPUT}"
echo "Phase config : ${PHASES_SNAPSHOT_OUTPUT}"
echo "Controller logs: ${CONTROLLER_LOG_LAN1}"
echo "              : ${CONTROLLER_LOG_LAN2}"
