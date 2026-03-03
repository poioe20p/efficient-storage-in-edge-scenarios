#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

MONGO_HOST_IP=192.168.100.4
MONGO_ROUTER_PORT=27020
MONGO_CONFIG_PORT=27019
MONGO_ROUTER_BIND_IPS=192.168.100.4,127.0.0.1,0.0.0.0
MONGO_RS_1_HOST_IP=10.0.0.4
MONGO_RS_2_HOST_IP=10.0.1.4
MONGO_RS_3_HOST_IP=10.0.0.6
MONGO_RS_4_HOST_IP=10.0.1.5
MONGO_RS_1_MEMBER2_IP=10.0.0.6
MONGO_RS_2_MEMBER2_IP=10.0.1.5
ADMIN_USER=admin
ADMIN_PASS=admin-password
OSKEN1_PORT=${OSKEN1_PORT:-6653}
OSKEN2_PORT=${OSKEN2_PORT:-6654}

# OS-Ken controller runtime knobs live in an env file (used by both controller containers).
OSKEN_ENV_FILE=${OSKEN_ENV_FILE:-"${SCRIPT_DIR}/osken-controller.env"}

if [[ ! -f "${OSKEN_ENV_FILE}" ]]; then
    echo "Missing controller env file: ${OSKEN_ENV_FILE}" >&2
    echo "Expected at: ${SCRIPT_DIR}/osken-controller.env" >&2
    exit 1
fi

check_mongo_ok() {
    local output="$1"
    local description="$2"
    if ! echo "$output" | grep -Eq '"ok"\s*:\s*1'; then
        echo "${description} did not return ok: 1. Output:"
        printf '%s\n' "$output"
        exit 1
    fi
}

ensure_rs_member() {
    local container="$1"
    local host_ip="$2"
    local member_host="$3"

    set +e
    local has_member
    has_member=$(docker exec -i "$container" mongosh --quiet --host "$host_ip" --port 27018 --eval "
var conf = rs.conf();
var target = '${member_host}';
var present = conf.members && conf.members.some(m => m.host === target);
print(present ? 'YES' : 'NO');
")
    local status=$?
    set -e

    if [[ $status -ne 0 ]]; then
        echo "Failed to query replica set config for ${container} (${host_ip})."
        exit 1
    fi

    local cleaned
    cleaned=$(echo "$has_member" | tr -d '\r\n' | tail -n 1)
    if [[ "$cleaned" == "YES" ]]; then
        echo "Replica set member ${member_host} already present."
        return 0
    fi

    echo "Adding replica set member ${member_host}..."
    set +e
    local add_output
    add_output=$(docker exec -i "$container" mongosh --quiet --host "$host_ip" --port 27018 --eval "JSON.stringify(rs.add('${member_host}'))")
    local add_status=$?
    set -e

    if [[ $add_status -ne 0 ]]; then
        echo "Failed to add replica set member ${member_host} (exit ${add_status}). Output:"
        echo "$add_output"
        exit 1
    fi

    check_mongo_ok "$add_output" "Adding replica set member ${member_host}"
}

ensure_rs_primary() {
    local replset_name="$1"
    local container="$2"
    local host_ip="$3"
    local port="${4:-27018}"
    local max_retries="${5:-3}"
    local retry_delay="${6:-2}"

    echo "Verifying replica set '${replset_name}' reports PRIMARY..."

    local attempt
    for attempt in $(seq 1 "${max_retries}"); do
        echo "Replica set '${replset_name}' status check attempt ${attempt}/${max_retries}..."
        set +e
        local status_json
        status_json=$(docker exec -i "${container}" mongosh --quiet --host "${host_ip}" --port "${port}" --eval "
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
        local status_code=$?
        set -e

        if [[ ${status_code} -ne 0 ]]; then
            echo "Failed to run rs.status() for '${replset_name}' (exit ${status_code}). Output:"
            echo "${status_json}"
        else
            local cleaned_output
            cleaned_output=$(echo "${status_json}" | tr -d '\r\n')

            if [[ "${cleaned_output}" == ERROR:* ]]; then
                echo "Replica set '${replset_name}' not ready yet (${cleaned_output})."
            elif [[ "${cleaned_output}" == "PRIMARY" ]] || echo "${cleaned_output}" | grep -Eq '"stateStr"\s*:\s*"PRIMARY"'; then
                echo "Replica set '${replset_name}' reports PRIMARY state."
                return 0
            else
                echo "Replica set '${replset_name}' status is not PRIMARY yet. Output:"
                echo "${status_json}"
            fi
        fi

        if [[ ${attempt} -lt ${max_retries} ]]; then
            echo "Retrying in ${retry_delay}s..."
            sleep "${retry_delay}"
        fi
    done

    echo "Replica set '${replset_name}' failed to become PRIMARY after ${max_retries} attempts."
    exit 1
}

ensure_shard_added() {
    local router_container="$1"
    local mongos_host="$2"
    local mongos_port="$3"
    local shard_name="$4"
    local shard_connection_string="$5"
    local max_retries="${6:-5}"
    local retry_delay="${7:-2}"

    echo "Adding shard ${shard_name} to mongos with retries (target ${shard_connection_string})..."

    local attempt
    local last_status_json=""

    for attempt in $(seq 1 "${max_retries}"); do
        echo "Attempt ${attempt}/${max_retries}..."
        set +e
        last_status_json=$(docker exec -i "${router_container}" mongosh --quiet --host "${mongos_host}" --port "${mongos_port}" --eval "JSON.stringify(sh.addShard('${shard_connection_string}'))")
        local status_code=$?
        set -e

        if [[ ${status_code} -eq 0 ]] && echo "${last_status_json}" | grep -Eq '"ok"\s*:\s*1'; then
            check_mongo_ok "${last_status_json}" "Adding shard ${shard_name}"
            echo "Shard ${shard_name} added successfully."
            return 0
        fi

        echo "Shard ${shard_name} add attempt ${attempt} failed (exit ${status_code}). Output:"
        echo "${last_status_json}"

        if [[ ${attempt} -lt ${max_retries} ]]; then
            echo "Retrying in ${retry_delay}s..."
            sleep "${retry_delay}"
        fi
    done

    echo "Failed to add shard ${shard_name} after ${max_retries} attempts."
    exit 1
}

ensure_db_and_collection_sharded() {
    local router_container="$1"
    local mongos_host="$2"
    local mongos_port="$3"
    local db_name="$4"
    local collection_fqdn="$5"   # e.g. app_db.events
    local shard_key_js="$6"      # e.g. "{ dpid: 1 }"

    echo "Enabling sharding for database '${db_name}' and sharding collection '${collection_fqdn}'..."

    set +e
    local shard_db_output
    shard_db_output=$(docker exec -i "${router_container}" mongosh --quiet --host "${mongos_host}" --port "${mongos_port}" --eval "JSON.stringify(sh.enableSharding('${db_name}'))")
    local shard_db_status=$?

    local shard_coll_output
    shard_coll_output=$(docker exec -i "${router_container}" mongosh --quiet --host "${mongos_host}" --port "${mongos_port}" --eval "JSON.stringify(sh.shardCollection('${collection_fqdn}', ${shard_key_js}))")
    local shard_coll_status=$?
    set -e

    if [[ ${shard_db_status} -ne 0 ]]; then
        echo "Failed to enable sharding for database '${db_name}' (exit ${shard_db_status}). Output:"
        echo "${shard_db_output}"
        exit 1
    fi
    check_mongo_ok "${shard_db_output}" "Enabling sharding for database '${db_name}'"

    if [[ ${shard_coll_status} -ne 0 ]]; then
        echo "Failed to shard collection '${collection_fqdn}' (exit ${shard_coll_status}). Output:"
        echo "${shard_coll_output}"
        exit 1
    fi
    check_mongo_ok "${shard_coll_output}" "Sharding collection '${collection_fqdn}'"
}

configure_shard_zones_and_ranges() {
    local router_container="$1"
    local mongos_host="$2"
    local mongos_port="$3"
    local zone_size="$4"
    local collection_fqdn="$5"  # e.g. app_db.events
    shift 5

    if [[ $# -lt 2 || $(( $# % 2 )) -ne 0 ]]; then
        echo "configure_shard_zones_and_ranges expects shard/zone pairs: <shard1> <zone1> [<shard2> <zone2> ...]" >&2
        exit 1
    fi

    echo "Adding shard zones and zone key ranges (zone_size=${zone_size})..."

    local idx=0
    while [[ $# -gt 0 ]]; do
        local shard_name="$1"
        local zone_name="$2"
        shift 2

        local range_start=$(( idx * zone_size ))
        local range_end=$(( range_start + zone_size ))

        echo "Assigning zone ${zone_name} to shard ${shard_name} for dpid [${range_start}, ${range_end})."

        set +e
        local add_zone_output
        add_zone_output=$(docker exec -i "${router_container}" mongosh --quiet --host "${mongos_host}" --port "${mongos_port}" --eval "JSON.stringify(sh.addShardToZone('${shard_name}', '${zone_name}'))")
        local add_zone_status=$?
        set -e

        if [[ ${add_zone_status} -ne 0 ]]; then
            echo "Failed to assign zone ${zone_name} to shard ${shard_name} (exit ${add_zone_status}). Output:"
            echo "${add_zone_output}"
            exit 1
        fi
        check_mongo_ok "${add_zone_output}" "Adding zone ${zone_name} to shard ${shard_name}"

        echo "Tagging collection ${collection_fqdn} range [${range_start}, ${range_end}) with zone ${zone_name}."
        set +e
        local range_output
        range_output=$(docker exec -i "${router_container}" mongosh --quiet --host "${mongos_host}" --port "${mongos_port}" --eval "
JSON.stringify(
    sh.updateZoneKeyRange(
        '${collection_fqdn}',
        { dpid: NumberLong(${range_start}) },
        { dpid: NumberLong(${range_end}) },
        '${zone_name}'
    )
)")
        local range_status=$?
        set -e

        if [[ ${range_status} -ne 0 ]]; then
            echo "Failed to tag ${collection_fqdn} zone range for ${zone_name} (exit ${range_status}). Output:"
            echo "${range_output}"
            exit 1
        fi
        check_mongo_ok "${range_output}" "Adding zone range for ${collection_fqdn} (${zone_name})"

        idx=$((idx + 1))
    done

    echo "Shard zones and key ranges configured successfully."
}

# ==============================
# 0 - Cleanup old runs
# ==============================
echo "Cleaning up network and Docker resources..."
./cleanup.sh -v

if [[ $? -ne 0 ]]; then
    echo "Cleanup failed. Aborting build_setup.sh."
    exit 1
fi

# ==============================
# 0.5 - Ensure IPTables FORWARD policy is ACCEPT
# ==============================
echo "Verifying IPTTables FORWARD policy..."
FORWARD_POLICY=$(sudo iptables -L FORWARD | grep "Chain FORWARD" | awk '{print $4}')
if [[ "$FORWARD_POLICY" != "ACCEPT" ]]; then
    echo "FORWARD policy is not ACCEPT. Changing it to ACCEPT..."
    sudo iptables --policy FORWARD ACCEPT
fi

echo "Ensuring enp0s3 has IP 192.168.100.4/24..."
if ! ip link show enp0s3 &>/dev/null; then
    echo "Network interface enp0s3 not found. Aborting."
    exit 1
fi

if ip addr show dev enp0s3 | grep -q "192.168.100.4/24"; then
    echo "enp0s3 already has 192.168.100.4/24 assigned."
else
    sudo ip addr add 192.168.100.4/24 dev enp0s3
    echo "Assigned 192.168.100.4/24 to enp0s3."
fi

# ==============================
# 1 - Start OVS container
# ==============================
# -dit: run in background, interactive, with tty
# --privileged: needed to run OVS
# --cap-add=NET_ADMIN: needed to create/manage network interfaces
# --cap-add=SYS_MODULE: needed to load kernel modules (OVS datapath)
# --network host: use host network (needed for SDN controller communication)
# -v /lib/modules:/lib/modules: share host kernel modules with container
echo "Starting OVS container..."
docker run -dit --name ovs --privileged \
  --cap-add=NET_ADMIN --cap-add=SYS_MODULE \
  --network host \
  -v /lib/modules:/lib/modules \
  ovs-container

if [[ $? -ne 0 ]]; then
    echo "Failed to start OVS container. Aborting."
    exit 1
fi

sleep 2


# ===============================
# 2 - Start nat-router container
# ===============================
echo "Starting NAT router container..."
docker run -dit --name nat-router --privileged --network none ubuntu-nat-router

if [[ $? -ne 0 ]]; then
    echo "Failed to start NAT router container. Aborting."
    exit 1
fi

# ==============================
# 3 - Start mongodb config server container
# ==============================
echo "Starting MongoDB config server container..."
docker run -di --name mongodb-config-server --network host \
    -v mongodb-configdb:/data/configdb \
    mongodb-config-server mongod \
    --configsvr \
    --replSet configReplSet \
    --port 27019 \
    --dbpath "/data/configdb" \
    --bind_ip 192.168.100.4

if [[ $? -ne 0 ]]; then
    echo "Failed to start MongoDB config server container. Aborting."
    exit 1
fi
sleep 2

# ==============================
# 4 - Initialize the MongoDB config server replica set
# ==============================
echo "Initializing MongoDB config server replica set..."
echo "Checking if config server replica set is already initialized..."
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
    echo "Config server replica set already initialized. Skipping rs.initiate."
else
        echo "Replica set not initialized yet. Running rs.initiate..."
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
                echo "Failed to initialize MongoDB config server replica set (exit ${INIT_STATUS}). Output:"
                echo "${INIT_OUTPUT}"
                exit 1
        fi

        check_mongo_ok "${INIT_OUTPUT}" "Config server replica set initialization"
        echo "Config server replica set initialization returned ok: 1."
        sleep 2
fi

# =====================================
# 4.1 - Verify config server replica set status
# =====================================
echo "Verifying MongoDB config server replica set status..."
MAX_RS_RETRIES=3
RS_RETRY_DELAY=2
RS_READY=false

for attempt in $(seq 1 ${MAX_RS_RETRIES}); do
        echo "Replica set status check attempt ${attempt}/${MAX_RS_RETRIES}..."
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
        echo "Failed to run rs.status() (exit ${STATUS_STATUS}). Output:"
        echo "${STATE_STR}"
    else
        CLEAN_STATE=$(echo "${STATE_STR}" | tr -d '\r\n"')
        if [[ "${CLEAN_STATE}" == "PRIMARY" ]]; then
            echo "Config server replica set member is PRIMARY."
            RS_READY=true
            break
        elif [[ "${CLEAN_STATE}" == ERROR:* ]]; then
            echo "Replica set not ready yet (${CLEAN_STATE})."
        else
            echo "Replica set state is '${CLEAN_STATE}', not PRIMARY yet."
        fi
    fi

    if [[ ${attempt} -lt ${MAX_RS_RETRIES} ]]; then
        echo "Retrying in ${RS_RETRY_DELAY}s..."
        sleep ${RS_RETRY_DELAY}
    fi
done

if [[ "${RS_READY}" != true ]]; then
    echo "Config server replica set failed to reach PRIMARY state after ${MAX_RS_RETRIES} attempts."
    exit 1
fi
sleep 2

# ==============================
# 5 - Run build_network_1.sh to setup first network
# ==============================
echo "Building first network (network 1)..."
./build_network_1.sh
if [[ $? -ne 0 ]]; then
    echo "Failed to build first network. Aborting."
    exit 1
fi
sleep 2

# =============================
# 5.1 - Initialize the mongodb-n1 replica set
# =============================
echo "Initializing MongoDB replica set for mongodb-n1..."
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
    echo "Config server replica set already initialized. Skipping rs.initiate."
else
    echo "Replica set not initialized yet. Running rs.initiate..."
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
    echo "Initialization returned ok with value -> ${INIT_OUTPUT}."
    sleep 2

fi

# =============================
# 5.2 - Initialize the mongodb-n3 replica set (separate shard)
# =============================
echo "Initializing MongoDB replica set for mongodb-n3..."
set +e
RS_STATUS_CHECK=$(docker exec -i mongodb-n3 mongosh --host "${MONGO_RS_3_HOST_IP}" --port 27018 --quiet --eval "
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
    echo "Replica set for mongodb-n3 already initialized. Skipping rs.initiate."
else
    echo "Replica set for mongodb-n3 not initialized yet. Running rs.initiate..."
    set +e
    INIT_OUTPUT=$(docker exec -i mongodb-n3 mongosh --host "${MONGO_RS_3_HOST_IP}" --port 27018 --quiet --eval "
    JSON.stringify(
    rs.initiate({
        _id: 'rs_net3',
        members: [
        { _id: 0, host: '${MONGO_RS_3_HOST_IP}:27018' }
        ]
    })
    )
    ")
    set -e
    check_mongo_ok "${INIT_OUTPUT}" "Replica set 'rs_net3' initialization"
    echo "Initialization returned ok with value -> ${INIT_OUTPUT}."
    sleep 2
fi

# ==============================
# 6 - Run build_network_2.sh to setup second network
# ==============================
echo "Building second network (network 2)..."
./build_network_2.sh
if [[ $? -ne 0 ]]; then
    echo "Failed to build second network. Aborting."
    exit 1
fi
sleep 2

# =============================
# 6.1 - Initialize the mongodb-n2 replica set
# =============================
echo "Initializing MongoDB replica set for mongodb-n2..."
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
    echo "Config server replica set already initialized. Skipping rs.initiate."
else
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
    echo "Initialization returned ok with value -> ${INIT_OUTPUT}."
    sleep 2

fi

# =============================
# 6.2 - Initialize the mongodb-n4 replica set (separate shard)
# =============================
echo "Initializing MongoDB replica set for mongodb-n4..."
set +e
RS_STATUS_CHECK=$(docker exec -i mongodb-n4 mongosh --quiet --host "${MONGO_RS_4_HOST_IP}" --port 27018 --quiet --eval "
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
    echo "Replica set for mongodb-n4 already initialized. Skipping rs.initiate."
else
    set +e
    INIT_OUTPUT=$(docker exec -i mongodb-n4 mongosh --quiet --host "${MONGO_RS_4_HOST_IP}" --port 27018 --quiet --eval "
    JSON.stringify(
    rs.initiate({
        _id: 'rs_net4',
        members: [
        { _id: 0, host: '${MONGO_RS_4_HOST_IP}:27018' }
        ]
    })
    )
    ")
    set -e
    check_mongo_ok "${INIT_OUTPUT}" "Replica set 'rs_net4' initialization"
    echo "Initialization returned ok with value -> ${INIT_OUTPUT}."
    sleep 2
fi

# ==============================================
# 7 - Check if both replica sets are initialized as primary
# ==============================================
echo "Verifying MongoDB shard replica set statuses..."
ensure_rs_primary "rs_net1" "mongodb-n1" "10.0.0.4" "27018" "3" "2"
ensure_rs_primary "rs_net2" "mongodb-n2" "10.0.1.4" "27018" "3" "2"
ensure_rs_primary "rs_net3" "mongodb-n3" "${MONGO_RS_3_HOST_IP}" "27018" "3" "2"
ensure_rs_primary "rs_net4" "mongodb-n4" "${MONGO_RS_4_HOST_IP}" "27018" "3" "2"

sleep 2

# ==============================
# 8 - Start mongodb router container
# ==============================
echo "Starting MongoDB router container..."
docker run -dit --name mongodb-router --network host \
    mongodb-router:latest mongos \
    --configdb configReplSet/192.168.100.4:27019 \
    --bind_ip 192.168.100.4 \
    --port 27020

if [[ $? -ne 0 ]]; then
    echo "Failed to start MongoDB router container. Aborting."
    exit 1
fi
sleep 2

# ========================================
# 8.1 - Add both shard replica sets to the router
# ========================================
echo "Adding shard replica sets to the MongoDB router with retries..."
declare -A SHARD_CONNECTIONS=( ["rs_net1"]="rs_net1/10.0.0.4:27018" ["rs_net2"]="rs_net2/10.0.1.4:27018" )
MAX_SHARD_RETRIES=5
SHARD_RETRY_DELAY=2

for SHARD in rs_net1 rs_net2; do
    TARGET="${SHARD_CONNECTIONS[$SHARD]}"
    if [[ -z "${TARGET}" ]]; then
        echo "No shard connection string defined for '${SHARD}'. Aborting."
        exit 1
    fi

    ensure_shard_added "mongodb-router" "${MONGO_HOST_IP}" "${MONGO_ROUTER_PORT}" "${SHARD}" "${TARGET}" "${MAX_SHARD_RETRIES}" "${SHARD_RETRY_DELAY}"
    sleep "${SHARD_RETRY_DELAY}"
done

# ========================================================
# 8.2 - Enable sharding for the database and collection
# =======================================================
ensure_db_and_collection_sharded "mongodb-router" "${MONGO_HOST_IP}" "${MONGO_ROUTER_PORT}" "app_db" "app_db.events" "{ dpid: 1 }"
sleep 2


# ===============================================
# 8.3 Add shard zones and shard key ranges
# ===============================================
ZONE_SIZE=1000000000
configure_shard_zones_and_ranges "mongodb-router" "${MONGO_HOST_IP}" "${MONGO_ROUTER_PORT}" "${ZONE_SIZE}" "app_db.events" \
    "rs_net1" "shard_zone_rs_net1" \
    "rs_net2" "shard_zone_rs_net2"

# ==============================
# 9 - Start SDN controller container
# ==============================
cd "${ROOT_DIR}"
echo "Current directory for OS-Ken controller: $PWD"

echo "Starting os-ken SDN controller container..."
docker rm -f osken 2>/dev/null

docker run -dit --name osken --network host \
    -v "$PWD":/workspace -w /workspace -e PYTHONPATH=/workspace \
    --env-file "${OSKEN_ENV_FILE}" \
    osken-controller --observe-links --ofp-tcp-listen-port "${OSKEN1_PORT}" \
        --log-config-file /etc/osken/logging.conf \
        os_ken.topology.switches sdn_controller.calculate_stats_n1

docker run -dit --name osken_2 --network host \
    -v "$PWD":/workspace -w /workspace -e PYTHONPATH=/workspace \
    --env-file "${OSKEN_ENV_FILE}" \
    -e LAN_ID=lan2 \
    -e VIP_IP="10.0.1.100" \
    osken-controller --observe-links --ofp-tcp-listen-port "${OSKEN2_PORT}" \
        --log-config-file /etc/osken/logging.conf \
        os_ken.topology.switches sdn_controller.calculate_stats_n2

if [[ $? -ne 0 ]]; then
    echo "Failed to start SDN controller container. Aborting."
    exit 1
fi

cd "${SCRIPT_DIR}"

# ==============================
# 9.1 - Point both OVS switches to the SDN controller
# ==============================
echo "Pointing OVS switches to the SDN controllers..."
docker exec ovs ovs-vsctl set-controller ovs-br0 tcp:127.0.0.1:${OSKEN1_PORT}
docker exec ovs ovs-vsctl set-controller ovs-br2 tcp:127.0.0.1:${OSKEN1_PORT}
docker exec ovs ovs-vsctl set-controller ovs-br1 tcp:127.0.0.1:${OSKEN2_PORT}

docker exec ovs ovs-vsctl show

if [[ $? -ne 0 ]]; then
    echo "Failed to point OVS switches to SDN controller. Aborting."
    exit 1
fi

# ==============================
# 9.2 - Install VIP ARP reply flows (Anycast service IPs)
# ==============================
VIP_IP_LAN1=10.0.0.100
VIP_IP_LAN2=10.0.1.100
VIP_MAC=aa:bb:cc:dd:ee:ff

install_vip_arp_reply_flow() {
    local bridge="$1"
    local vip_ip="$2"
    local vip_mac="$3"

    local match="priority=200,arp,arp_op=1,arp_tpa=${vip_ip}"
    local flow="${match},actions=move:NXM_OF_ETH_SRC[]->NXM_OF_ETH_DST[],set_field:${vip_mac}->eth_src,set_field:2->arp_op,move:NXM_NX_ARP_SHA[]->NXM_NX_ARP_THA[],set_field:${vip_mac}->arp_sha,move:NXM_OF_ARP_SPA[]->NXM_OF_ARP_TPA[],set_field:${vip_ip}->arp_spa,IN_PORT"

    echo "Installing VIP ARP reply flow on ${bridge} for ${vip_ip} (${vip_mac})"
    docker exec ovs ovs-ofctl -O OpenFlow13 --strict del-flows "${bridge}" "${match}" >/dev/null 2>&1 || true
    docker exec ovs ovs-ofctl -O OpenFlow13 add-flow "${bridge}" "${flow}" || true
}

install_vip_arp_reply_flow ovs-br0 "${VIP_IP_LAN1}" "${VIP_MAC}"
install_vip_arp_reply_flow ovs-br2 "${VIP_IP_LAN1}" "${VIP_MAC}"
install_vip_arp_reply_flow ovs-br1 "${VIP_IP_LAN2}" "${VIP_MAC}"

echo "Build and setup of networks completed successfully."