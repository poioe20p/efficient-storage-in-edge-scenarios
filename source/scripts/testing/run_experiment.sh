#!/bin/bash

# ============================================================================
# run_experiment.sh
#
# Full experiment orchestration for the phased edge content-discovery workload.
# Runs in order:
#   1. Create test client namespaces (LAN 1 + LAN 2)
#   2. Seed MongoDB: content_items → user_profiles → create_indexes
#   3. Export workload snapshot (content items + user profiles → JSON)
#   4. Start resource stats collector (ZMQ subscriber → CSV)
#   5. Run traffic generator (phased HTTP load from namespaces)
#   6. Stop resource stats collector
#
# Edit the configuration variables below to match your deployment.
#
# Usage:
#   sudo ./run_experiment.sh [--batch-dir batch4] [--run-label c0] [--skip-clients] [--skip-seed] [--skip-snapshot]
#   sudo ./run_experiment.sh --phases-config phases_custom.json --fault-plan fault_plan.json
#   sudo ./run_experiment.sh --clients-per-lan 6 --seed-content-items 600 --seed-users 100 \
#       --phases-config testing/phases_override/phases_tier1_smoke.json --run-label tier1_smoke
#
# Flags (all optional):
#   --batch-dir DIR     Place the run folder under metrics/DIR/ (example: metrics/batch4/20260501_153012_c0)
#   --run-label LABEL    Append a config label to the metrics folder name (example: 20260501_153012_c0)
#   --skip-clients       Skip step 1 (test namespaces already created)
#   --skip-seed          Skip step 2 (data already seeded)
#   --skip-snapshot      Skip step 3 (snapshot already exported)
#   --clients-per-lan N  Override the number of client namespaces created per LAN
#   --seed-content-items N Override the number of content items seeded per LAN
#   --seed-users N       Override the number of user profiles seeded per LAN
#   --snapshot-dir DIR   Override snapshot directory (default: REPO_ROOT/data/workload_snapshot)
#   --phases-config FILE Override the traffic-generator phases file
#   --fault-plan FILE    Optional fault-injection plan consumed by fault_injector.py
#   --dry-run            Pass --dry-run to traffic_generator (no real requests)
# ============================================================================

set -euo pipefail

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPTS_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
readonly REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
readonly DEFAULT_CONTROLLER_ENV_SOURCE="${SCRIPTS_DIR}/osken-controller.env"
readonly CONTROLLER_ENV_BASE_SOURCE="${OSKEN_ENV_FILE:-${DEFAULT_CONTROLLER_ENV_SOURCE}}"
readonly CONTROLLER_ENV_OVERRIDE_SOURCE="${OSKEN_ENV_OVERRIDE_FILE:-}"
readonly RUN_TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
TEMP_CONTROLLER_ENV_SOURCE=""

# ---------------------------------------------------------------------------
# Configuration — edit these to match your experiment
# ---------------------------------------------------------------------------

# Number of test client namespaces per LAN
CLIENTS_PER_LAN="${CLIENTS_PER_LAN:-3}"

# Namespace prefixes — produces lan1_client_1, lan1_client_2 … lan2_client_1, lan2_client_2 …
PREFIX_LAN1="lan1_client_"
PREFIX_LAN2="lan2_client_"

# Number of content items and user profiles to seed per region
SEED_CONTENT_ITEMS="${SEED_CONTENT_ITEMS:-100}"
SEED_USERS="${SEED_USERS:-40}"

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

# PID of the controller overhead sampler (set by run_sample_controller_stats)
CONTROLLER_STATS_PID=""

# PIDs for controller log capture (set by run_capture_controller_logs)
CONTROLLER_LOG_PID1=""
CONTROLLER_LOG_PID2=""

# PID of the container event poller (set by run_poll_container_events)
CONTAINER_EVENTS_PID=""

# PID of the service log capture helper (set by run_capture_service_logs)
SERVICE_LOG_PID=""

# PID of the fault injector helper (set by run_fault_injector)
FAULT_INJECTOR_PID=""

# ---------------------------------------------------------------------------
# Flags
# ---------------------------------------------------------------------------

SKIP_CLIENTS=false
SKIP_SEED=false
SKIP_SNAPSHOT=false
DRY_RUN=false
BATCH_DIR=""
RUN_LABEL=""
PHASES_CONFIG_OVERRIDE=""
FAULT_PLAN=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --batch-dir)    shift; BATCH_DIR="$1" ;;
        --batch-dir=*)  BATCH_DIR="${1#*=}"    ;;
        --run-label)     shift; RUN_LABEL="$1"  ;;
        --run-label=*)   RUN_LABEL="${1#*=}"    ;;
        --skip-clients)   SKIP_CLIENTS=true  ;;
        --skip-seed)      SKIP_SEED=true     ;;
        --skip-snapshot)  SKIP_SNAPSHOT=true ;;
        --clients-per-lan) shift; CLIENTS_PER_LAN="$1" ;;
        --clients-per-lan=*) CLIENTS_PER_LAN="${1#*=}" ;;
        --seed-content-items)   shift; SEED_CONTENT_ITEMS="$1" ;;
        --seed-content-items=*) SEED_CONTENT_ITEMS="${1#*=}" ;;
        --seed-users)     shift; SEED_USERS="$1" ;;
        --seed-users=*)   SEED_USERS="${1#*=}" ;;
        --dry-run)        DRY_RUN=true       ;;
        --snapshot-dir)   shift; SNAPSHOT_DIR="$1" ;;
        --snapshot-dir=*) SNAPSHOT_DIR="${1#*=}" ;;
        --phases-config)   shift; PHASES_CONFIG_OVERRIDE="$1" ;;
        --phases-config=*) PHASES_CONFIG_OVERRIDE="${1#*=}" ;;
        --fault-plan)      shift; FAULT_PLAN="$1" ;;
        --fault-plan=*)    FAULT_PLAN="${1#*=}" ;;
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

step() { echo; echo "==> $*"; }
die()  { echo "ERROR: $*" >&2; exit 1; }

require_positive_int() {
    local name="$1"
    local value="$2"

    [[ "$value" =~ ^[1-9][0-9]*$ ]] || die "invalid ${name} '${value}' (expected positive integer)"
}

require_positive_int "--clients-per-lan" "$CLIENTS_PER_LAN"
require_positive_int "--seed-content-items" "$SEED_CONTENT_ITEMS"
require_positive_int "--seed-users" "$SEED_USERS"

resolve_path_from_scripts_dir() {
    local path="$1"

    if [[ -z "$path" ]]; then
        printf '%s\n' ""
        return 0
    fi

    if [[ "$path" == /* ]]; then
        printf '%s\n' "$path"
        return 0
    fi

    printf '%s\n' "${SCRIPTS_DIR}/${path#./}"
}

apply_env_override_file() {
    local target_path="$1"
    local override_path="$2"
    local line=""
    local key=""
    local temp_path=""

    while IFS= read -r line || [[ -n "$line" ]]; do
        if [[ -z "$line" || "$line" =~ ^[[:space:]]*# ]]; then
            continue
        fi

        if [[ "$line" != *=* ]]; then
            die "invalid controller env override line: ${line}"
        fi

        key="${line%%=*}"
        temp_path="$(mktemp)"
        awk -v key="$key" -v newline="$line" '
            $0 ~ "^" key "=" { next }
            { print }
            END { print newline }
        ' "$target_path" > "$temp_path"
        mv "$temp_path" "$target_path"
    done < "$override_path"
}

prepare_controller_env_source() {
    local base_env_path=""
    local override_env_path=""

    base_env_path="$(resolve_path_from_scripts_dir "$CONTROLLER_ENV_BASE_SOURCE")"
    override_env_path="$(resolve_path_from_scripts_dir "$CONTROLLER_ENV_OVERRIDE_SOURCE")"

    [[ -f "$base_env_path" ]] || die "Controller env not found: $base_env_path"

    if [[ -z "$override_env_path" ]]; then
        CONTROLLER_ENV_SOURCE="$base_env_path"
        return 0
    fi

    [[ -f "$override_env_path" ]] || die "Controller env override not found: $override_env_path"
    TEMP_CONTROLLER_ENV_SOURCE="$(mktemp)"
    cp "$base_env_path" "$TEMP_CONTROLLER_ENV_SOURCE"
    apply_env_override_file "$TEMP_CONTROLLER_ENV_SOURCE" "$override_env_path"
    CONTROLLER_ENV_SOURCE="$TEMP_CONTROLLER_ENV_SOURCE"
}

cleanup_temp_controller_env() {
    if [[ -n "$TEMP_CONTROLLER_ENV_SOURCE" && -f "$TEMP_CONTROLLER_ENV_SOURCE" ]]; then
        rm -f "$TEMP_CONTROLLER_ENV_SOURCE"
    fi
}

prepare_controller_env_source

readonly RUN_ID="${RUN_TIMESTAMP}${RUN_LABEL:+_${RUN_LABEL}}"
readonly METRICS_ROOT="${SCRIPT_DIR}/metrics"
readonly RUN_PARENT_DIR="${METRICS_ROOT}${BATCH_DIR:+/${BATCH_DIR}}"
readonly RUN_DIR="${RUN_PARENT_DIR}/${RUN_ID}"
readonly CONTROLLER_ENV_SNAPSHOT_OUTPUT="${RUN_DIR}/controller_env_snapshot.env"

# Traffic generator config and output
PHASES_CONFIG="${SCRIPT_DIR}/phases.json"
PHASES_SNAPSHOT_OUTPUT="${RUN_DIR}/phases_snapshot.json"
METRICS_OUTPUT="${RUN_DIR}/client_requests.csv"

if [[ -n "$PHASES_CONFIG_OVERRIDE" ]]; then
    PHASES_CONFIG="$PHASES_CONFIG_OVERRIDE"
fi

# Resource stats collector outputs
RESOURCE_STATS_OUTPUT="${RUN_DIR}/resource_stats.csv"
RESOURCE_STATS_DEBUG_OUTPUT="${RUN_DIR}/resource_stats_debug.csv"
PHASE_FILE="${RUN_DIR}/current_phase.txt"

# Post-run reconstructed artifacts
POLICY_STATE_OUTPUT="${RUN_DIR}/policy_state.csv"
ELASTICITY_EVENTS_OUTPUT="${RUN_DIR}/elasticity_events.csv"

# Container life-cycle poller (diff-based docker ps)
CONTAINER_EVENTS_OUTPUT="${RUN_DIR}/container_events.csv"

# Controller log capture — saved alongside resource stats
CONTROLLER_LOG_LAN1="${RUN_DIR}/controller_lan1.log"
CONTROLLER_LOG_LAN2="${RUN_DIR}/controller_lan2.log"

# Service logs — one file per edge/storage container observed during the run
SERVICE_LOG_DIR="${RUN_DIR}/service_logs"

# Optional fault-injection artifacts
FAULT_PLAN_SNAPSHOT_OUTPUT="${RUN_DIR}/fault_plan_snapshot.json"
FAULT_EVENTS_OUTPUT="${RUN_DIR}/experiment_fault_events.csv"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

prepare_run_outputs() {
    step "Preparing run output folder"
    mkdir -p "$RUN_DIR"
    [[ -f "$PHASES_CONFIG" ]] || die "Phase config not found: $PHASES_CONFIG"
    [[ -f "$CONTROLLER_ENV_SOURCE" ]] || die "Controller env not found: $CONTROLLER_ENV_SOURCE"
    if [[ -n "$FAULT_PLAN" ]]; then
        [[ -f "$FAULT_PLAN" ]] || die "Fault plan not found: $FAULT_PLAN"
    fi
    cp "$PHASES_CONFIG" "$PHASES_SNAPSHOT_OUTPUT"
    cp "$CONTROLLER_ENV_SOURCE" "$CONTROLLER_ENV_SNAPSHOT_OUTPUT"
    if [[ -n "$FAULT_PLAN" ]]; then
        cp "$FAULT_PLAN" "$FAULT_PLAN_SNAPSHOT_OUTPUT"
    fi
    echo "  Run dir    : ${RUN_DIR}"
    echo "  Batch dir  : ${BATCH_DIR:-<none>}"
    echo "  Run label  : ${RUN_LABEL:-<none>}"
    echo "  Phase copy : ${PHASES_SNAPSHOT_OUTPUT}"
    echo "  Env copy   : ${CONTROLLER_ENV_SNAPSHOT_OUTPUT}"
    if [[ -n "$FAULT_PLAN" ]]; then
        echo "  Fault copy : ${FAULT_PLAN_SNAPSHOT_OUTPUT}"
        echo "  Fault log  : ${FAULT_EVENTS_OUTPUT}"
    fi
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
    [[ -f "$create_script" ]] || die "Not found: $create_script"

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

    echo "  content_items (${SEED_CONTENT_ITEMS} content items/region)"
    python3 "${SCRIPT_DIR}/seed_content_items.py" \
        --mongo-lan1 "$MONGO_LAN1" --mongo-lan2 "$MONGO_LAN2" \
        --content-items "$SEED_CONTENT_ITEMS"

    echo "  user_profiles (${SEED_USERS} users/region, ${SEED_CONTENT_ITEMS} content IDs)"
    python3 "${SCRIPT_DIR}/seed_user_profiles.py" \
        --mongo-lan1 "$MONGO_LAN1" --mongo-lan2 "$MONGO_LAN2" \
        --users "$SEED_USERS" --content-items "$SEED_CONTENT_ITEMS"

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
    echo "  Debug    : ${RESOURCE_STATS_DEBUG_OUTPUT}"
    python3 "${SCRIPT_DIR}/collect_resource_stats.py" \
        --lan1-pub "$LAN1_PUB" \
        --lan2-pub "$LAN2_PUB" \
        --lan1-coord-pub "$LAN1_COORD_PUB" \
        --lan2-coord-pub "$LAN2_COORD_PUB" \
        --output       "$RESOURCE_STATS_OUTPUT" \
        --output-debug "$RESOURCE_STATS_DEBUG_OUTPUT" \
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
# Step 4c — Controller overhead sampler
# ---------------------------------------------------------------------------

CONTROLLER_STATS_OUTPUT="${RUN_DIR}/controller_stats.csv"

run_sample_controller_stats() {
    step "Starting controller overhead sampler"
    echo "  Containers : osken, osken_2"
    echo "  Interval   : 5s"
    echo "  Output     : ${CONTROLLER_STATS_OUTPUT}"
    python3 "${SCRIPT_DIR}/sample_controller_stats.py" \
        --output "${CONTROLLER_STATS_OUTPUT}" \
        --phase-file "${PHASE_FILE}" \
        --interval 5 \
        --containers osken,osken_2 &
    CONTROLLER_STATS_PID=$!
    echo "  Sampler PID: ${CONTROLLER_STATS_PID}"
}

stop_sample_controller_stats() {
    [[ -z "${CONTROLLER_STATS_PID:-}" ]] && return 0
    echo; echo "==> Stopping controller overhead sampler (PID ${CONTROLLER_STATS_PID})"
    kill -TERM "$CONTROLLER_STATS_PID" 2>/dev/null || true
    wait "$CONTROLLER_STATS_PID" 2>/dev/null || true
    CONTROLLER_STATS_PID=""
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
# Step 4c — Capture edge/storage service logs during the run
# ---------------------------------------------------------------------------

run_capture_service_logs() {
    step "Capturing service logs"
    echo "  Output   : ${SERVICE_LOG_DIR}"
    python3 "${SCRIPT_DIR}/capture_service_logs.py" \
        --output-dir "$SERVICE_LOG_DIR" &
    SERVICE_LOG_PID=$!
    echo "  Helper PID: ${SERVICE_LOG_PID}"
}

stop_capture_service_logs() {
    [[ -z "${SERVICE_LOG_PID:-}" ]] && return 0
    echo; echo "==> Stopping service log capture (PID ${SERVICE_LOG_PID})"
    kill -TERM "$SERVICE_LOG_PID" 2>/dev/null || true
    wait "$SERVICE_LOG_PID" 2>/dev/null || true
    SERVICE_LOG_PID=""
}

# ---------------------------------------------------------------------------
# Step 4d — Optional fault injector
# ---------------------------------------------------------------------------

run_fault_injector() {
    [[ -z "$FAULT_PLAN" ]] && return 0

    step "Starting fault injector"
    echo "  Plan     : ${FAULT_PLAN}"
    echo "  Phase    : ${PHASE_FILE}"
    echo "  Output   : ${FAULT_EVENTS_OUTPUT}"
    python3 "${SCRIPT_DIR}/fault_injector.py" \
        --plan "$FAULT_PLAN" \
        --phase-file "$PHASE_FILE" \
        --controller-log-lan1 "$CONTROLLER_LOG_LAN1" \
        --controller-log-lan2 "$CONTROLLER_LOG_LAN2" \
        --output "$FAULT_EVENTS_OUTPUT" &
    FAULT_INJECTOR_PID=$!
    echo "  Helper PID: ${FAULT_INJECTOR_PID}"
}

stop_fault_injector() {
    [[ -z "${FAULT_INJECTOR_PID:-}" ]] && return 0
    echo; echo "==> Stopping fault injector (PID ${FAULT_INJECTOR_PID})"
    kill -TERM "$FAULT_INJECTOR_PID" 2>/dev/null || true
    wait "$FAULT_INJECTOR_PID" 2>/dev/null || true
    FAULT_INJECTOR_PID=""
}

# ---------------------------------------------------------------------------
# Step 4e — Container life-cycle poller (diff-based docker ps)
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
# Post-run artifact generation (Step 8 — policy_state.csv reconstruction)
# ---------------------------------------------------------------------------

generate_elasticity_events() {
    step "Generating elasticity events from controller logs"
    echo "  LAN1 log : ${CONTROLLER_LOG_LAN1}"
    echo "  LAN2 log : ${CONTROLLER_LOG_LAN2}"
    echo "  Output   : ${ELASTICITY_EVENTS_OUTPUT}"
    python3 "${SCRIPTS_DIR}/tools/parse_elasticity_logs.py" \
        "$CONTROLLER_LOG_LAN1" \
        "$CONTROLLER_LOG_LAN2" \
        -o "$ELASTICITY_EVENTS_OUTPUT" \
        || echo "  WARNING: elasticity event generation failed (non-fatal)" >&2
}

generate_policy_state() {
    step "Reconstructing policy state from run artifacts"
    echo "  Resource stats  : ${RESOURCE_STATS_OUTPUT}"
    echo "  Resource debug  : ${RESOURCE_STATS_DEBUG_OUTPUT}"
    echo "  Per-node stats  : ${RUN_DIR}/per_node_stats.csv"
    echo "  Container events: ${CONTAINER_EVENTS_OUTPUT}"
    echo "  Controller env  : ${CONTROLLER_ENV_SNAPSHOT_OUTPUT}"
    echo "  Elasticity evts : ${ELASTICITY_EVENTS_OUTPUT}"
    echo "  Controller logs : ${CONTROLLER_LOG_LAN1}, ${CONTROLLER_LOG_LAN2}"
    echo "  Output          : ${POLICY_STATE_OUTPUT}"
    python3 "${SCRIPTS_DIR}/tools/reconstruct_policy_state.py" \
        --resource-stats       "$RESOURCE_STATS_OUTPUT" \
        --resource-stats-debug "$RESOURCE_STATS_DEBUG_OUTPUT" \
        --per-node-stats       "${RUN_DIR}/per_node_stats.csv" \
        --container-events     "$CONTAINER_EVENTS_OUTPUT" \
        --controller-env       "$CONTROLLER_ENV_SNAPSHOT_OUTPUT" \
        --elasticity-events    "$ELASTICITY_EVENTS_OUTPUT" \
        --controller-log-lan1  "$CONTROLLER_LOG_LAN1" \
        --controller-log-lan2  "$CONTROLLER_LOG_LAN2" \
        --output               "$POLICY_STATE_OUTPUT" \
        || echo "  WARNING: policy state reconstruction failed (non-fatal)" >&2
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

build_client_lists

echo "======================================================"
echo " Edge Content Discovery Experiment — Full Run"
echo "======================================================"
echo " Batch dir   : ${BATCH_DIR:-<none>}"
echo " Clients/LAN : ${CLIENTS_PER_LAN}  (${CLIENTS_LAN1} | ${CLIENTS_LAN2})"
echo " Content/LAN : ${SEED_CONTENT_ITEMS}"
echo " Users/LAN   : ${SEED_USERS}"
echo " Snapshot    : ${SNAPSHOT_DIR}"
echo " Output      : ${METRICS_OUTPUT}"
echo " Resource    : ${RESOURCE_STATS_OUTPUT}"
echo " Phase file  : ${PHASE_FILE}"
echo " VIP         : ${VIP}"
echo " Phases cfg  : ${PHASES_CONFIG}"
echo " Fault plan  : ${FAULT_PLAN:-<none>}"
echo " Dry-run     : ${DRY_RUN}"
echo "======================================================"

# Stop the run-scoped helpers on any exit (normal, error, or signal)
trap 'stop_fault_injector; stop_capture_service_logs; stop_capture_controller_logs; stop_poll_container_events; stop_sample_controller_stats; stop_collect_stats; cleanup_temp_controller_env' EXIT

prepare_run_outputs
"$SKIP_CLIENTS"  || run_create_clients
"$SKIP_SEED"     || run_seed
"$SKIP_SNAPSHOT" || run_snapshot
run_collect_stats
run_sample_controller_stats
run_capture_controller_logs
run_capture_service_logs
run_fault_injector
run_poll_container_events
run_traffic
stop_fault_injector
stop_poll_container_events
stop_capture_service_logs
stop_sample_controller_stats
stop_collect_stats

# Post-run artifact reconstruction
generate_elasticity_events
generate_policy_state

step "Experiment complete"
echo "Results          : ${METRICS_OUTPUT}"
echo "Resource stats   : ${RESOURCE_STATS_OUTPUT}"
echo "Resource debug   : ${RESOURCE_STATS_DEBUG_OUTPUT}"
echo "Policy state     : ${POLICY_STATE_OUTPUT}"
echo "Elasticity events: ${ELASTICITY_EVENTS_OUTPUT}"
echo "Container events : ${CONTAINER_EVENTS_OUTPUT}"
echo "Phase config     : ${PHASES_SNAPSHOT_OUTPUT}"
if [[ -n "$FAULT_PLAN" ]]; then
    echo "Fault plan     : ${FAULT_PLAN_SNAPSHOT_OUTPUT}"
    echo "Fault events   : ${FAULT_EVENTS_OUTPUT}"
fi
echo "Controller logs: ${CONTROLLER_LOG_LAN1}"
echo "               : ${CONTROLLER_LOG_LAN2}"
echo "Service logs   : ${SERVICE_LOG_DIR}"