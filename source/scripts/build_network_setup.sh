#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OSKEN1_PORT=${OSKEN1_PORT:-6653}
OSKEN2_PORT=${OSKEN2_PORT:-6654}
OSKEN_ENV_FILE=${OSKEN_ENV_FILE:-"${SCRIPT_DIR}/osken-controller.env"}
WAN_ENV_FILE=${WAN_ENV_FILE:-"${SCRIPT_DIR}/wan.env"}

if [[ ! -f "${OSKEN_ENV_FILE}" ]]; then
    echo "Missing controller env file: ${OSKEN_ENV_FILE}" >&2
    echo "Expected at: ${SCRIPT_DIR}/osken-controller.env" >&2
    exit 1
fi

# Source WAN-emulation knobs (consumed by network/inject_wan_latency.sh from
# build_router.sh). All variables default to 0 if the file is absent.
if [[ -f "${WAN_ENV_FILE}" ]]; then
    set -a
    # shellcheck disable=SC1090
    source "${WAN_ENV_FILE}"
    set +a
fi


# ==============================
# Auxiliary functions
# ==============================
check_mongo_ok() {
    local output="$1"
    local description="$2"
    if ! echo "$output" | grep -Eq '"ok"\s*:\s*1'; then
        echo "${description} did not return ok: 1. Output:"
        printf '%s\n' "$output"
        exit 1
    fi
}

wait_for_controller_connected() {
    local bridge="$1"
    local max_retries="${2:-30}"
    local retry_delay="${3:-2}"
    local attempt

    echo "Waiting for SDN controller to connect to ${bridge}..."
    for attempt in $(seq 1 "${max_retries}"); do
        local connected
        connected=$(docker exec ovs ovs-vsctl show 2>/dev/null \
            | awk "/Bridge ${bridge}/{found=1} found && /is_connected: true/{print; exit}")
        if [[ -n "${connected}" ]]; then
            echo "Controller connected to ${bridge}."
            return 0
        fi
        echo "  Controller not yet connected to ${bridge} (${attempt}/${max_retries})..."
        sleep "${retry_delay}"
    done

    echo "Controller failed to connect to ${bridge} after ${max_retries} attempts." >&2
    exit 1
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

# echo "Ensuring enp0s3 has IP 192.168.100.4/24..."
# if ! ip link show enp0s3 &>/dev/null; then
#     echo "Network interface enp0s3 not found. Aborting."
#     exit 1
# fi

# if ip addr show dev enp0s3 | grep -q "192.168.100.4/24"; then
#     echo "enp0s3 already has 192.168.100.4/24 assigned."
# else
#     sudo ip addr add 192.168.100.4/24 dev enp0s3
#     echo "Assigned 192.168.100.4/24 to enp0s3."
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
sleep 1


# ===============================
# 2 - Start nat-router container
# ===============================
echo "Starting NAT router container..."
docker run -dit --name nat-router --privileged --network none ubuntu-nat-router

if [[ $? -ne 0 ]]; then
    echo "Failed to start NAT router container. Aborting."
    exit 1
fi
sleep 1


# ==============================
# 3 - Run build_network_1.sh to setup first network
# ==============================
echo "Building first network (network 1)..."
./network/build_network_1.sh
if [[ $? -ne 0 ]]; then
    echo "Failed to build first network. Aborting."
    exit 1
fi
sleep 1


# =============================
# 3.1 - Initialize the edge_storage_server_n1 replica set
# =============================
echo "Initializing replica set for edge_storage_server_n1..."
set +e
RS_STATUS_CHECK=$(docker exec -i edge_storage_server_n1 mongosh --host 10.0.0.4 --port 27018 --quiet --eval "
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
    INIT_OUTPUT=$(docker exec -i edge_storage_server_n1 mongosh --host 10.0.0.4 --port 27018 --quiet --eval "
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
# 4 - Run build_network_2.sh to setup second network
# ==============================
echo "Building second network (network 2)..."
./network/build_network_2.sh
if [[ $? -ne 0 ]]; then
    echo "Failed to build second network. Aborting."
    exit 1
fi
sleep 2


# ==============================
# 5 - Initialize the edge_storage_server_n2 replica set
# ==============================
echo "Initializing replica set for edge_storage_server_n2..."
set +e
RS_STATUS_CHECK=$(docker exec -i edge_storage_server_n2 mongosh --quiet --host 10.0.1.4 --port 27018 --quiet --eval "
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
    echo "Edge storage server replica set already initialized. Skipping rs.initiate."
else
    set +e
    INIT_OUTPUT=$(docker exec -i edge_storage_server_n2 mongosh --quiet --host 10.0.1.4 --port 27018 --quiet --eval "
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


# ==============================
# 6 - Configure Router WAN and Routes
# ==============================
echo "Configuring router WAN interfaces and port-forwardings..."
./network/build_router.sh
if [[ $? -ne 0 ]]; then
    echo "Failed to configure router. Aborting."
    exit 1
fi
sleep 2


# ==============================================
# 7 - Check if both replica sets are initialized as primary
# ==============================================
echo "Verifying edge_storage_server replica set statuses..."
ensure_rs_primary "rs_net1" "edge_storage_server_n1" "10.0.0.4" "27018" "15" "5"
ensure_rs_primary "rs_net2" "edge_storage_server_n2" "10.0.1.4" "27018" "15" "5"


# ==============================
# 8 - Start SDN controller container
# ==============================
cd "${ROOT_DIR}"
echo "Current directory for OS-Ken controller: $PWD"

echo "Starting os-ken SDN controller container..."
docker rm -f osken 2>/dev/null

docker run -dit --name osken --network host \
    --privileged --pid=host \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "$PWD":/workspace -w /workspace -e PYTHONPATH=/workspace \
    --env-file "${OSKEN_ENV_FILE}" \
    -e LAN_ID=lan1 \
    -e TOPOLOGY_PUB_PORT=5559 \
    -e PEER_TOPOLOGY_ENDPOINTS=tcp://127.0.0.1:5560 \
    -e COORDINATOR_STATE_PUB_PORT=5561 \
    -e SERVER_MACS="00:00:00:00:00:02" \
    -e ROUTER_MAC="00:00:00:00:00:AA" \
    osken-controller --observe-links --ofp-tcp-listen-port "${OSKEN1_PORT}" \
        --log-config-file /etc/osken/logging.conf \
        sdn_controller.main_n1

docker run -dit --name osken_2 --network host \
    --privileged --pid=host \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v "$PWD":/workspace -w /workspace -e PYTHONPATH=/workspace \
    --env-file "${OSKEN_ENV_FILE}" \
    -e LAN_ID=lan2 \
    -e TOPOLOGY_PUB_PORT=5560 \
    -e PEER_TOPOLOGY_ENDPOINTS=tcp://127.0.0.1:5559 \
    -e COORDINATOR_STATE_PUB_PORT=5562 \
    -e SERVER_MACS="00:00:00:00:00:05" \
    -e ROUTER_MAC="00:00:00:00:00:CC" \
    osken-controller --observe-links --ofp-tcp-listen-port "${OSKEN2_PORT}" \
        --log-config-file /etc/osken/logging.conf \
        sdn_controller.main_n2
    # Specify the lan2 VIP IP via environment variable to diferentiate from the ones in .env file

if [[ $? -ne 0 ]]; then
    echo "Failed to start SDN controller container. Aborting."
    exit 1
fi

cd "${SCRIPT_DIR}"


# ==============================
# 8.1 - Point both OVS switches to the SDN controller
# ==============================
echo "Pointing OVS switches to the SDN controllers..."
docker exec ovs ovs-vsctl set-controller ovs-br0 tcp:127.0.0.1:${OSKEN1_PORT}
docker exec ovs ovs-vsctl set-controller ovs-br1 tcp:127.0.0.1:${OSKEN2_PORT}

if [[ $? -ne 0 ]]; then
    echo "Failed to point OVS switches to SDN controller. Aborting."
    exit 1
fi


# NOTE: VIP ARP replies are handled by the SDN controller itself via
# install_vip_arp_punt_rules (priority=100 punt rules).  Installing static
# OVS flows here at priority=200 would override the controller's punt rules,
# preventing snoop_arp from ever learning MAC->IP mappings.

docker exec ovs ovs-vsctl show
echo "Build and setup of networks completed successfully."

# ==============================
# 9 - Seed controller ARP tables via connectivity tests
# ==============================
# Pinging all hosts triggers ARP traffic through OVS, which the SDN controllers
# snoop to populate their IP<->MAC tables before any real client connects.
# Wait until both controllers have an active OpenFlow channel before sending
# pings — otherwise ARP packets pass through OVS unseen and the IP<->MAC maps
# remain empty, causing intermittent VIP routing failures.
echo "Waiting for SDN controllers to establish OpenFlow connections..."
wait_for_controller_connected "ovs-br0"
wait_for_controller_connected "ovs-br1"

sleep 5

echo "Running connectivity tests to seed controller ARP tables..."
"${SCRIPT_DIR}/test_conectivity.sh" all || echo "WARNING: some connectivity tests failed; ARP seeding may be incomplete."

./network/clients/remove_test_clients.sh --lan 1 --prefix lan1_client
./network/clients/remove_test_clients.sh --lan 2 --prefix lan2_client