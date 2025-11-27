#!/bin/bash
set -euo pipefail

MONGO_HOST_IP=192.168.100.4
MONGO_ROUTER_PORT=27020
MONGO_CONFIG_PORT=27019
MONGO_ROUTER_BIND_IPS=192.168.100.4,127.0.0.1,0.0.0.0
MONGO_RS_1_HOST_IP=10.0.0.4
MONGO_RS_2_HOST_IP=10.0.1.4
ADMIN_USER=admin
ADMIN_PASS=admin-password

check_mongo_ok() {
    local output="$1"
    local description="$2"
    if ! echo "$output" | grep -Eq '"ok"\s*:\s*1'; then
        echo "${description} did not return ok: 1. Output:"
        printf '%s\n' "$output"
        exit 1
    fi
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

# if ip addr show dev enp0s3 | grep -q "192.168.100.5/24"; then
#     echo "enp0s3 already has 192.168.100.5/24 assigned."
# else
#     sudo ip addr add 192.168.100.5/24 dev enp0s3
#     echo "Assigned 192.168.100.5/24 to enp0s3."
# fi

# if ip addr show dev enp0s3 | grep -q "192.168.100.6/24"; then
#     echo "enp0s3 already has 192.168.100.6/24 assigned."
# else
#     sudo ip addr add 192.168.100.6/24 dev enp0s3
#     echo "Assigned 192.168.100.6/24 to enp0s3."
# fi

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

# docker exec -i mongodb-config-server mongosh --quiet --host 192.168.100.4 --port 27019 <<'EOF'
# cfg = rs.conf();
# cfg.members[0].host = "192.168.100.4:27019";
# rs.reconfig(cfg, {force: true});
# EOF

# ===============================================
# 4.2 - Ensure config server replica set host IP
# ===============================================
DESIRED_CONFIG_MEMBER="${MONGO_HOST_IP}:${MONGO_CONFIG_PORT}"
echo "Ensuring config server replica set advertises ${DESIRED_CONFIG_MEMBER}..."
set +e
CURRENT_CONFIG_MEMBER=$(docker exec mongodb-config-server mongosh --quiet --host 192.168.100.4 --port 27019 --eval "
var cfg;
try {
    cfg = rs.conf();
    if (cfg.members && cfg.members.length > 0) {
        print(cfg.members[0].host);
    } else {
        print('NO_MEMBERS');
    }
} catch (e) {
    print('ERROR:' + e);
}
")
HOST_STATUS=$?
set -e

if [[ ${HOST_STATUS} -ne 0 ]]; then
    echo "Failed to inspect config replica set members (exit ${HOST_STATUS}). Output:"
    echo "${CURRENT_CONFIG_MEMBER}"
    exit 1
fi

CLEAN_CONFIG_MEMBER=$(echo "${CURRENT_CONFIG_MEMBER}" | tr -d '\r\n"')

if [[ "${CLEAN_CONFIG_MEMBER}" == ERROR:* ]]; then
    echo "Unable to read config replica set configuration (${CLEAN_CONFIG_MEMBER})."
    exit 1
fi

if [[ "${CLEAN_CONFIG_MEMBER}" == "NO_MEMBERS" ]]; then
    echo "Config replica set reports no members despite initialization; aborting."
    exit 1
fi

if [[ "${CLEAN_CONFIG_MEMBER}" != "${DESIRED_CONFIG_MEMBER}" ]]; then
    echo "Config replica set member host '${CLEAN_CONFIG_MEMBER}' does not match desired '${DESIRED_CONFIG_MEMBER}'. Reconfiguring..."
    set +e
    RECONFIG_OUTPUT=$(docker exec -i mongodb-config-server mongosh --quiet --host 192.168.100.4 --port 27019 --eval "
JSON.stringify(
    rs.reconfig({
        _id: 'configReplSet',
        configsvr: true,
        members: [
            { _id: 0, host: '${MONGO_HOST_IP}:${MONGO_CONFIG_PORT}' }
        ]
    }, { force: true })
)
")
    RECONFIG_STATUS=$?
    set -e

    if [[ ${RECONFIG_STATUS} -ne 0 ]]; then
        echo "Failed to reconfigure config replica set host (exit ${RECONFIG_STATUS}). Output:"
        echo "${RECONFIG_OUTPUT}"
        exit 1
    fi

    check_mongo_ok "${RECONFIG_OUTPUT}" "Config replica set host reconfiguration"
    echo "Config replica set host updated successfully."
    sleep 2
else
    echo "Config replica set already advertises the desired host."
fi

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

# docker run -dit --name mongodb-n1 --network host \
#     --no-healthcheck \
#     -v mongodb-n1-data:/data/db ubuntu-mongodb mongod \
#     --shardsvr --replSet rs_net1 \
#     --dbpath "/data/db" \
#     --bind_ip 10.0.0.4 --port 27018

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

# docker run -dit --name mongodb-n2 --network host \
#     --no-healthcheck \
#     -v mongodb-n2-data:/data/db ubuntu-mongodb mongod \
#     --shardsvr --replSet rs_net2 \
#     --dbpath "/data/db" \
#     --bind_ip 10.0.1.4 --port 27018

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

# ==============================================
# 7 - Check if both replica sets are initialized as primary
# ==============================================
echo "Verifying MongoDB shard replica set statuses..."
declare -A RS_CONTAINER=( ["rs_net1"]="mongodb-n1" ["rs_net2"]="mongodb-n2" )
declare -A RS_HOST=( ["rs_net1"]="10.0.0.4" ["rs_net2"]="10.0.1.4" )

for REPLSET in rs_net1 rs_net2; do
    MAX_RS_RETRIES=3
    RS_RETRY_DELAY=2
    RS_READY=false

    CONTAINER="${RS_CONTAINER[$REPLSET]}"
    HOST_IP="${RS_HOST[$REPLSET]}"

    if [[ -z "${CONTAINER}" || -z "${HOST_IP}" ]]; then
        echo "Replica set '${REPLSET}' has no container/IP mapping; aborting."
        exit 1
    fi

    for attempt in $(seq 1 ${MAX_RS_RETRIES}); do
        echo "Replica set '${REPLSET}' status check attempt ${attempt}/${MAX_RS_RETRIES}..."
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
            echo "Failed to run rs.status() for '${REPLSET}' (exit ${STATUS_CODE}). Output:"
            echo "${STATUS_JSON}"
        else
            CLEAN_OUTPUT=$(echo "${STATUS_JSON}" | tr -d '\r\n')

            if [[ "${CLEAN_OUTPUT}" == ERROR:* ]]; then
                echo "Replica set '${REPLSET}' not ready yet (${CLEAN_OUTPUT})."
            elif [[ "${CLEAN_OUTPUT}" == "PRIMARY" ]] || echo "${CLEAN_OUTPUT}" | grep -Eq '"stateStr"\s*:\s*"PRIMARY"'; then
                echo "Replica set '${REPLSET}' reports PRIMARY state."
                RS_READY=true
                break
            else
                echo "Replica set '${REPLSET}' status is not PRIMARY or ok:1 yet. Output:"
                echo "${STATUS_JSON}"
            fi
        fi

        if [[ ${attempt} -lt ${MAX_RS_RETRIES} ]]; then
            echo "Retrying in ${RS_RETRY_DELAY}s..."
            sleep ${RS_RETRY_DELAY}
        fi
    done

    if [[ "${RS_READY}" != true ]]; then
        echo "Replica set '${REPLSET}' failed to become PRIMARY after ${MAX_RS_RETRIES} attempts."
        exit 1
    fi

    sleep 2
done

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

# Ensure mongos is fully connected to the config replica set before adding shards
echo "Waiting for MongoDB router to become ready..."
MAX_ROUTER_RETRIES=15
ROUTER_RETRY_DELAY=4
ROUTER_READY=false

for attempt in $(seq 1 ${MAX_ROUTER_RETRIES}); do
    echo "Router readiness check attempt ${attempt}/${MAX_ROUTER_RETRIES}..."
    set +e
    PING_RESULT=$(docker exec -i mongodb-router mongosh --quiet --host 192.168.100.4 --port 27020 --eval "JSON.stringify(db.adminCommand({ ping: 1 }))")
    PING_STATUS=$?
    GRID_RESULT=$(docker exec -i mongodb-router mongosh --quiet --host 192.168.100.4 --port 27020 --eval "JSON.stringify(db.adminCommand({ isdbgrid: 1 }))")
    GRID_STATUS=$?
    LIST_RESULT=$(docker exec -i mongodb-router mongosh --quiet --host 192.168.100.4 --port 27020 --eval "JSON.stringify(db.adminCommand({ listShards: 1 }))")
    LIST_STATUS=$?
    set -e

     if [[ ${PING_STATUS} -eq 0 && ${GRID_STATUS} -eq 0 && ${LIST_STATUS} -eq 0 ]] && \
         echo "${PING_RESULT}" | grep -Eq '"ok"\s*:\s*1' && \
         echo "${GRID_RESULT}" | grep -Eq '"ok"\s*:\s*1' && \
         echo "${LIST_RESULT}" | grep -Eq '"ok"\s*:\s*1'; then
        echo "MongoDB router is ready."
        ROUTER_READY=true
        break
    fi

    echo "Router not ready yet. Ping output: ${PING_RESULT}" >&2
     echo "isdbgrid output: ${GRID_RESULT}" >&2
     echo "listShards output: ${LIST_RESULT}" >&2

    if [[ ${attempt} -lt ${MAX_ROUTER_RETRIES} ]]; then
        echo "Retrying in ${ROUTER_RETRY_DELAY}s..."
        sleep ${ROUTER_RETRY_DELAY}
    fi
done

if [[ "${ROUTER_READY}" != true ]]; then
    echo "MongoDB router failed to become ready after ${MAX_ROUTER_RETRIES} attempts."
    exit 1
fi

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

    echo "Adding shard ${SHARD} (target ${TARGET})..."
    SHARD_SUCCESS=false
    LAST_STATUS_JSON=""

    for attempt in $(seq 1 ${MAX_SHARD_RETRIES}); do
        echo "Attempt ${attempt}/${MAX_SHARD_RETRIES}..."
        set +e
        LAST_STATUS_JSON=$(docker exec -it mongodb-router mongosh --quiet --host 192.168.100.4 --port 27020 --eval "
            JSON.stringify(sh.addShard('${TARGET}'))")
        STATUS_CODE=$?
        set -e

        if [[ ${STATUS_CODE} -eq 0 ]] && echo "${LAST_STATUS_JSON}" | grep -Eq '"ok"\s*:\s*1'; then
            SHARD_SUCCESS=true
            break
        fi

        echo "Shard ${SHARD} add attempt ${attempt} failed (exit ${STATUS_CODE}). Output:"
        echo "${LAST_STATUS_JSON}"

        if [[ ${attempt} -lt ${MAX_SHARD_RETRIES} ]]; then
            echo "Retrying in ${SHARD_RETRY_DELAY}s..."
            sleep ${SHARD_RETRY_DELAY}
        fi
    done

    if [[ "${SHARD_SUCCESS}" != true ]]; then
        echo "Failed to add shard ${SHARD} after ${MAX_SHARD_RETRIES} attempts."
        exit 1
    fi

    check_mongo_ok "${LAST_STATUS_JSON}" "Adding shard ${SHARD}"
    echo "Shard ${SHARD} added successfully."
    sleep ${SHARD_RETRY_DELAY}
done

# ========================================================
# 8.2 - Enable sharding for the database and collection
# =======================================================
echo "Enabling sharding for the database and collection..."
set +e
SHARD_DB_OUTPUT=$(docker exec -it mongodb-router mongosh --quiet --host 192.168.100.4 --port 27020 --eval "
    JSON.stringify(sh.enableSharding('app_db'))")
    SHARD_DB_STATUS=$?
SHARD_EVENTS_COLL_OUTPUT=$(docker exec -it mongodb-router mongosh --quiet --host 192.168.100.4 --port 27020 --eval "
    JSON.stringify(sh.shardCollection('app_db.events', { dpid: 1 }))")
    SHARD_COLL_STATUS=$?
SHARD_TOPOLOGY_COLL_OUTPUT=$(docker exec -it mongodb-router mongosh --quiet --host 192.168.100.4 --port 27020 --eval "
    JSON.stringify(sh.shardCollection('app_db.topology', { dpid: 1 }))")
    SHARD_TOPOLOGY_STATUS=$?
set -e

    if [[ ${SHARD_DB_STATUS} -ne 0 ]]; then
        echo "Failed to enable sharding for database 'app_db' (exit ${SHARD_DB_STATUS}). Output:"
        echo "${SHARD_DB_OUTPUT}"
        exit 1
    fi

    check_mongo_ok "${SHARD_DB_OUTPUT}" "Enabling sharding for database 'app_db'"

    if [[ ${SHARD_COLL_STATUS} -ne 0 ]]; then
        echo "Failed to shard collection 'app_db.events' (exit ${SHARD_COLL_STATUS}). Output:"
        echo "${SHARD_EVENTS_COLL_OUTPUT}"
        exit 1
    fi

    check_mongo_ok "${SHARD_EVENTS_COLL_OUTPUT}" "Sharding collection 'app_db.events'"

    if [[ ${SHARD_TOPOLOGY_STATUS} -ne 0 ]]; then
        echo "Failed to shard collection 'app_db.topology' (exit ${SHARD_TOPOLOGY_STATUS}). Output:"
        echo "${SHARD_TOPOLOGY_COLL_OUTPUT}"
        exit 1
    fi

    check_mongo_ok "${SHARD_TOPOLOGY_COLL_OUTPUT}" "Sharding collection 'app_db.topology'"
sleep 2


# # ==============================
# # 9 - Start SDN controller container
# # ==============================
# cd ..
# echo "Current directory for OS-Ken controller: $PWD"

# echo "Starting os-ken SDN controller container..."
# docker rm -f osken 2>/dev/null

# PWD=$(pwd)
# MONGO_ENV_FILE="$PWD/../.env-mongo"

# if [[ ! -f "$MONGO_ENV_FILE" ]]; then
#     echo "MongoDB environment file '$MONGO_ENV_FILE' not found. Aborting."
#     echo "Using direct environment variables instead."
#     docker run -dit --name osken --network host \
#         -v "$PWD":/workspace -w /workspace -e PYTHONPATH=/workspace \
#         -e MONGO_ROUTER_HOST="${MONGO_HOST_IP}" \
#         -e MONGO_ROUTER_PORT="${MONGO_ROUTER_PORT}" \
#         -e MONGO_CONFIG_HOST="${MONGO_HOST_IP}" \
#         -e MONGO_CONFIG_PORT="${MONGO_CONFIG_PORT}" \
#         osken-controller \
#         --verbose sdn_controller.osken_learn_and_log
# fi

# docker run -dit --name osken --network host \
#     --env-file "$MONGO_ENV_FILE" \
#     -v "$PWD":/workspace -w /workspace -e PYTHONPATH=/workspace \
#     osken-controller \
#     --verbose sdn_controller.osken_learn_and_log

# if [[ $? -ne 0 ]]; then
#     echo "Failed to start SDN controller container. Aborting."
#     exit 1
# fi

# cd scripts

# # ==============================
# # 9.1 - Point both OVS switches to the SDN controller
# # ==============================
# echo "Pointing OVS switches to the SDN controller..."
# docker exec ovs ovs-vsctl set-controller ovs-br0 tcp:127.0.0.1:6633
# docker exec ovs ovs-vsctl set-controller ovs-br1 tcp:127.0.0.1:6633

# docker exec ovs ovs-vsctl show

# if [[ $? -ne 0 ]]; then
#     echo "Failed to point OVS switches to SDN controller. Aborting."
#     exit 1
# fi

# echo "Build and setup of networks completed successfully."