#!/bin/bash

# ============================================================================
# Docker Compose MongoDB Initialization Script
# ============================================================================
#
# This script initializes the MongoDB sharded cluster for containers managed
# by docker-compose. It performs:
#   1. Config server replica set initialization
#   2. Shard replica set initialization (rs_net1, rs_net2)
#   3. Adding shards to the router
#   4. Enabling sharding on database and collections
#   5. Configuring shard zones and key ranges
#
# Usage:
#   ./docker-compose-init-mongo.sh
#
# Prerequisites:
#   - docker-compose up -d must be run first
#   - Network setup must be complete (docker-compose-network-setup.sh)
#   - All MongoDB containers should be running and reachable
#
# ============================================================================

set -euo pipefail

SCRIPT_NAME=$(basename "$0")

log()   { printf '[INFO] %s\n' "$*"; }
warn()  { printf '[WARN] %s\n' "$*" 1>&2; }
error() { printf '[ERROR] %s\n' "$*" 1>&2; }

cleanup_trap() {
    local ec=$?
    if [[ $ec -ne 0 ]]; then
        error "${SCRIPT_NAME} failed (exit $ec). Review messages above."
    fi
}

trap 'error "Command failed at line ${LINENO}: ${BASH_COMMAND}"' ERR
trap cleanup_trap EXIT

# ============================================================================
# Configuration
# ============================================================================
MONGO_HOST_IP=192.168.100.4
MONGO_ROUTER_PORT=27020
MONGO_CONFIG_PORT=27019
MONGO_RS_1_HOST_IP=10.0.0.4
MONGO_RS_2_HOST_IP=10.0.1.4

# ============================================================================
# Helper Functions
# ============================================================================
check_mongo_ok() {
    local output="$1"
    local description="$2"
    if ! echo "$output" | grep -Eq '"ok"\s*:\s*1'; then
        error "${description} did not return ok: 1. Output:"
        printf '%s\n' "$output"
        return 1
    fi
    return 0
}

# ============================================================================
# Step 1: Initialize Config Server Replica Set
# ============================================================================
log "====================================================================="
log "Initializing MongoDB Config Server Replica Set"
log "====================================================================="

log "Checking if config server replica set is already initialized..."
set +e
RS_STATUS_CHECK=$(docker exec mongodb-config-server mongosh --quiet --host 192.168.100.4 --port 27019 --eval "
var status;
try {
    status = rs.status();
    if (status.members && status.members.length > 0) {
        print('ALREADY_INITIALIZED');
    } else {
        print('NOT_INITIALIZED');
    }
} catch (e) {
    if (e.codeName === 'NotYetInitialized') {
        print('NOT_INITIALIZED');
    } else {
        print('STATUS_ERROR:' + e);
    }
}
")
RS_STATUS_CODE=$?
set -e

CLEAN_RS_STATUS=$(echo "${RS_STATUS_CHECK}" | tr -d '\r\n"')
if [[ ${RS_STATUS_CODE} -eq 0 && "${CLEAN_RS_STATUS}" == "ALREADY_INITIALIZED" ]]; then
    log "Config server replica set already initialized. Skipping rs.initiate."
else
    log "Replica set not initialized yet. Running rs.initiate..."
    set +e
    INIT_OUTPUT=$(docker exec -i mongodb-config-server mongosh --quiet --host 192.168.100.4 --port 27019 --eval "
JSON.stringify(
    rs.initiate({
        _id: 'configReplSet',
        configsvr: true,
        members: [
            { _id: 0, host: '192.168.100.4:27019' }
        ]
    })
)
")
    INIT_STATUS=$?
    set -e

    if [[ ${INIT_STATUS} -ne 0 ]]; then
        error "Failed to initialize MongoDB config server replica set (exit ${INIT_STATUS}). Output:"
        echo "${INIT_OUTPUT}"
        exit 1
    fi

    check_mongo_ok "${INIT_OUTPUT}" "Config server replica set initialization"
    log "Config server replica set initialization returned ok: 1."
    sleep 2
fi

# Verify config server is PRIMARY
log "Verifying config server replica set status..."
MAX_RS_RETRIES=5
RS_RETRY_DELAY=3
RS_READY=false

for attempt in $(seq 1 ${MAX_RS_RETRIES}); do
    log "Replica set status check attempt ${attempt}/${MAX_RS_RETRIES}..."
    set +e
    STATE_STR=$(docker exec mongodb-config-server mongosh --quiet --host 192.168.100.4 --port 27019 --eval "
var status;
try {
    status = rs.status();
    if (status.members && status.members.some(member => member.stateStr === 'PRIMARY')) {
        print('PRIMARY');
    } else if (status.members && status.members.length > 0) {
        print(status.members[0].stateStr);
    } else {
        print('UNKNOWN');
    }
} catch (e) {
    print('ERROR:' + e);
}
")
    STATUS_STATUS=$?
    set -e

    if [[ ${STATUS_STATUS} -ne 0 ]]; then
        warn "Failed to run rs.status() (exit ${STATUS_STATUS}). Output: ${STATE_STR}"
    else
        CLEAN_STATE=$(echo "${STATE_STR}" | tr -d '\r\n"')
        if [[ "${CLEAN_STATE}" == "PRIMARY" ]]; then
            log "Config server replica set member is PRIMARY."
            RS_READY=true
            break
        else
            log "Replica set state is '${CLEAN_STATE}', not PRIMARY yet."
        fi
    fi

    if [[ ${attempt} -lt ${MAX_RS_RETRIES} ]]; then
        log "Retrying in ${RS_RETRY_DELAY}s..."
        sleep ${RS_RETRY_DELAY}
    fi
done

if [[ "${RS_READY}" != true ]]; then
    error "Config server replica set failed to reach PRIMARY state after ${MAX_RS_RETRIES} attempts."
    exit 1
fi

# ============================================================================
# Step 2: Initialize Shard Replica Sets
# ============================================================================
log "====================================================================="
log "Initializing MongoDB Shard Replica Sets"
log "====================================================================="

# Initialize rs_net1
log "Initializing replica set rs_net1..."
set +e
RS_STATUS_CHECK=$(docker exec -i mongodb-n1 mongosh --host 10.0.0.4 --port 27018 --quiet --eval "
var status;
try {
    status = rs.status();
    if (status.members && status.members.length > 0) {
        print('ALREADY_INITIALIZED');
    } else {
        print('NOT_INITIALIZED');
    }
} catch (e) {
    if (e.codeName === 'NotYetInitialized') {
        print('NOT_INITIALIZED');
    } else {
        print('STATUS_ERROR:' + e);
    }
}
")
RS_STATUS_CODE=$?
set -e

CLEAN_RS_STATUS=$(echo "${RS_STATUS_CHECK}" | tr -d '\r\n"')
if [[ ${RS_STATUS_CODE} -eq 0 && "${CLEAN_RS_STATUS}" == "ALREADY_INITIALIZED" ]]; then
    log "Replica set rs_net1 already initialized. Skipping rs.initiate."
else
    log "Replica set rs_net1 not initialized yet. Running rs.initiate..."
    set +e
    INIT_OUTPUT=$(docker exec -i mongodb-n1 mongosh --host 10.0.0.4 --port 27018 --quiet --eval "
    JSON.stringify(
    rs.initiate({
        _id: 'rs_net1',
        members: [
        { _id: 0, host: '10.0.0.4:27018' }
        ]
    })
    )
    ")
    set -e
    check_mongo_ok "${INIT_OUTPUT}" "Replica set 'rs_net1' initialization"
    log "rs_net1 initialization returned ok."
    sleep 2
fi

# Initialize rs_net2
log "Initializing replica set rs_net2..."
set +e
RS_STATUS_CHECK=$(docker exec -i mongodb-n2 mongosh --quiet --host 10.0.1.4 --port 27018 --quiet --eval "
var status;
try {
    status = rs.status();
    if (status.members && status.members.length > 0) {
        print('ALREADY_INITIALIZED');
    } else {
        print('NOT_INITIALIZED');
    }
} catch (e) {
    if (e.codeName === 'NotYetInitialized') {
        print('NOT_INITIALIZED');
    } else {
        print('STATUS_ERROR:' + e);
    }
}
")
RS_STATUS_CODE=$?
set -e

CLEAN_RS_STATUS=$(echo "${RS_STATUS_CHECK}" | tr -d '\r\n"')
if [[ ${RS_STATUS_CODE} -eq 0 && "${CLEAN_RS_STATUS}" == "ALREADY_INITIALIZED" ]]; then
    log "Replica set rs_net2 already initialized. Skipping rs.initiate."
else
    log "Replica set rs_net2 not initialized yet. Running rs.initiate..."
    set +e
    INIT_OUTPUT=$(docker exec -i mongodb-n2 mongosh --quiet --host 10.0.1.4 --port 27018 --quiet --eval "
    JSON.stringify(
    rs.initiate({
        _id: 'rs_net2',
        members: [
        { _id: 0, host: '10.0.1.4:27018' }
        ]
    })
    )
    ")
    set -e
    check_mongo_ok "${INIT_OUTPUT}" "Replica set 'rs_net2' initialization"
    log "rs_net2 initialization returned ok."
    sleep 2
fi

# ============================================================================
# Step 3: Verify Shard Replica Sets are PRIMARY
# ============================================================================
log "====================================================================="
log "Verifying Shard Replica Sets Status"
log "====================================================================="

declare -A RS_CONTAINER=( ["rs_net1"]="mongodb-n1" ["rs_net2"]="mongodb-n2" )
declare -A RS_HOST=( ["rs_net1"]="10.0.0.4" ["rs_net2"]="10.0.1.4" )

for REPLSET in rs_net1 rs_net2; do
    MAX_RS_RETRIES=5
    RS_RETRY_DELAY=3
    RS_READY=false

    CONTAINER="${RS_CONTAINER[$REPLSET]}"
    HOST_IP="${RS_HOST[$REPLSET]}"

    log "Checking replica set '${REPLSET}' status..."

    for attempt in $(seq 1 ${MAX_RS_RETRIES}); do
        log "Attempt ${attempt}/${MAX_RS_RETRIES} for '${REPLSET}'..."
        set +e
        STATUS_JSON=$(docker exec -i "${CONTAINER}" mongosh --quiet --host "${HOST_IP}" --port 27018 --quiet --eval "
var status;
try {
    status = rs.status();
    if (status.members && status.members.some(member => member.stateStr === 'PRIMARY')) {
        print('PRIMARY');
    } else if (status.members && status.members.length > 0) {
        print(status.members[0].stateStr);
    } else {
        print('UNKNOWN');
    }
} catch (e) {
    print('ERROR:' + e);
}
")
        STATUS_CODE=$?
        set -e

        if [[ ${STATUS_CODE} -ne 0 ]]; then
            warn "Failed to run rs.status() for '${REPLSET}' (exit ${STATUS_CODE})"
        else
            CLEAN_OUTPUT=$(echo "${STATUS_JSON}" | tr -d '\r\n')

            if [[ "${CLEAN_OUTPUT}" == "PRIMARY" ]]; then
                log "Replica set '${REPLSET}' reports PRIMARY state."
                RS_READY=true
                break
            else
                log "Replica set '${REPLSET}' status is '${CLEAN_OUTPUT}', not PRIMARY yet."
            fi
        fi

        if [[ ${attempt} -lt ${MAX_RS_RETRIES} ]]; then
            log "Retrying in ${RS_RETRY_DELAY}s..."
            sleep ${RS_RETRY_DELAY}
        fi
    done

    if [[ "${RS_READY}" != true ]]; then
        error "Replica set '${REPLSET}' failed to become PRIMARY after ${MAX_RS_RETRIES} attempts."
        exit 1
    fi

    sleep 2
done

# ============================================================================
# Step 4: Add Shards to Router
# ============================================================================
log "====================================================================="
log "Adding Shards to MongoDB Router"
log "====================================================================="

declare -A SHARD_CONNECTIONS=( ["rs_net1"]="rs_net1/10.0.0.4:27018" ["rs_net2"]="rs_net2/10.0.1.4:27018" )
MAX_SHARD_RETRIES=5
SHARD_RETRY_DELAY=3

for SHARD in rs_net1 rs_net2; do
    TARGET="${SHARD_CONNECTIONS[$SHARD]}"
    log "Adding shard ${SHARD} (target ${TARGET})..."
    SHARD_SUCCESS=false
    LAST_STATUS_JSON=""

    for attempt in $(seq 1 ${MAX_SHARD_RETRIES}); do
        log "Attempt ${attempt}/${MAX_SHARD_RETRIES}..."
        set +e
        LAST_STATUS_JSON=$(docker exec -it mongodb-router mongosh --quiet --host 192.168.100.4 --port 27020 --eval "
            JSON.stringify(sh.addShard('${TARGET}'))")
        STATUS_CODE=$?
        set -e

        if [[ ${STATUS_CODE} -eq 0 ]] && echo "${LAST_STATUS_JSON}" | grep -Eq '"ok"\s*:\s*1'; then
            SHARD_SUCCESS=true
            break
        fi

        warn "Shard ${SHARD} add attempt ${attempt} failed (exit ${STATUS_CODE})"

        if [[ ${attempt} -lt ${MAX_SHARD_RETRIES} ]]; then
            log "Retrying in ${SHARD_RETRY_DELAY}s..."
            sleep ${SHARD_RETRY_DELAY}
        fi
    done

    if [[ "${SHARD_SUCCESS}" != true ]]; then
        error "Failed to add shard ${SHARD} after ${MAX_SHARD_RETRIES} attempts."
        exit 1
    fi

    check_mongo_ok "${LAST_STATUS_JSON}" "Adding shard ${SHARD}"
    log "Shard ${SHARD} added successfully."
    sleep ${SHARD_RETRY_DELAY}
done

# ============================================================================
# Step 5: Enable Sharding on Database and Collection
# ============================================================================
log "====================================================================="
log "Enabling Sharding on Database and Collection"
log "====================================================================="

set +e
SHARD_DB_OUTPUT=$(docker exec -it mongodb-router mongosh --quiet --host 192.168.100.4 --port 27020 --eval "
    JSON.stringify(sh.enableSharding('app_db'))")
SHARD_DB_STATUS=$?

SHARD_EVENTS_COLL_OUTPUT=$(docker exec -it mongodb-router mongosh --quiet --host 192.168.100.4 --port 27020 --eval "
    JSON.stringify(sh.shardCollection('app_db.events', { dpid: 1 }))")
SHARD_COLL_STATUS=$?
set -e

if [[ ${SHARD_DB_STATUS} -ne 0 ]]; then
    error "Failed to enable sharding for database 'app_db' (exit ${SHARD_DB_STATUS})"
    exit 1
fi

check_mongo_ok "${SHARD_DB_OUTPUT}" "Enabling sharding for database 'app_db'"

if [[ ${SHARD_COLL_STATUS} -ne 0 ]]; then
    error "Failed to shard collection 'app_db.events' (exit ${SHARD_COLL_STATUS})"
    exit 1
fi

check_mongo_ok "${SHARD_EVENTS_COLL_OUTPUT}" "Sharding collection 'app_db.events'"

sleep 2

# ============================================================================
# Step 6: Configure Shard Zones and Key Ranges
# ============================================================================
log "====================================================================="
log "Configuring Shard Zones and Key Ranges"
log "====================================================================="

ZONE_SIZE=1000000000
SHARD_ORDER=(rs_net1 rs_net2)
declare -A SHARD_ZONES=( [rs_net1]="shard_zone_rs_net1" [rs_net2]="shard_zone_rs_net2" )

for idx in "${!SHARD_ORDER[@]}"; do
    SHARD_NAME="${SHARD_ORDER[$idx]}"
    ZONE_NAME="${SHARD_ZONES[$SHARD_NAME]}"
    RANGE_START=$(( idx * ZONE_SIZE ))
    RANGE_END=$(( RANGE_START + ZONE_SIZE ))

    log "Assigning zone ${ZONE_NAME} to shard ${SHARD_NAME} for dpid [${RANGE_START}, ${RANGE_END})."

    set +e
    ADD_ZONE_OUTPUT=$(docker exec -it mongodb-router mongosh --quiet --host 192.168.100.4 --port 27020 --eval "JSON.stringify(sh.addShardToZone('${SHARD_NAME}', '${ZONE_NAME}'))")
    ADD_ZONE_STATUS=$?
    set -e

    if [[ ${ADD_ZONE_STATUS} -ne 0 ]]; then
        error "Failed to assign zone ${ZONE_NAME} to shard ${SHARD_NAME} (exit ${ADD_ZONE_STATUS})"
        exit 1
    fi

    check_mongo_ok "${ADD_ZONE_OUTPUT}" "Adding zone ${ZONE_NAME} to shard ${SHARD_NAME}"

    for COLLECTION in "app_db.events"; do
        log "Tagging collection ${COLLECTION} range [${RANGE_START}, ${RANGE_END}) with zone ${ZONE_NAME}."
        set +e
        RANGE_OUTPUT=$(docker exec -it mongodb-router mongosh --quiet --host 192.168.100.4 --port 27020 --eval "
JSON.stringify(
    sh.updateZoneKeyRange(
        '${COLLECTION}',
        { dpid: NumberLong(${RANGE_START}) },
        { dpid: NumberLong(${RANGE_END}) },
        '${ZONE_NAME}'
    )
)")
        RANGE_STATUS=$?
        set -e

        if [[ ${RANGE_STATUS} -ne 0 ]]; then
            error "Failed to tag ${COLLECTION} zone range for ${ZONE_NAME} (exit ${RANGE_STATUS})"
            exit 1
        fi

        check_mongo_ok "${RANGE_OUTPUT}" "Adding zone range for ${COLLECTION} (${ZONE_NAME})"
    done
done

log "Shard zones and key ranges configured successfully."

# ============================================================================
# Summary
# ============================================================================
log "====================================================================="
log "MongoDB Cluster Initialization Complete!"
log "====================================================================="
log ""
log "Summary:"
log "  - Config server replica set: INITIALIZED"
log "  - Shard rs_net1: INITIALIZED and ADDED"
log "  - Shard rs_net2: INITIALIZED and ADDED"
log "  - Database 'app_db': SHARDING ENABLED"
log "  - Collection 'app_db.events': SHARDED on {dpid: 1}"
log "  - Shard zones: CONFIGURED"
log ""
log "Verify cluster status with:"
log "  docker exec mongodb-router mongosh --host 192.168.100.4 --port 27020 --eval 'sh.status()'"
