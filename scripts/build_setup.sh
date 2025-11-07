#!/bin/bash
set -euo pipefail

MONGO_HOST_IP=${MONGO_HOST_IP:-192.168.100.1}
MONGO_ROUTER_PORT=${MONGO_ROUTER_PORT:-27020}
MONGO_CONFIG_PORT=${MONGO_CONFIG_PORT:-27019}

# ==============================
# 0 - Cleanup old runs
# ==============================
echo "Cleaning up network and Docker resources..."
./cleanup.sh

if [[ $? -ne 0 ]]; then
    echo "Cleanup failed. Aborting build_networks.sh."
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
# 3 - Run build_network_1.sh to setup first network
# ==============================
echo "Building first network (network 1)..."
./build_network_1.sh
if [[ $? -ne 0 ]]; then
    echo "Failed to build first network. Aborting."
    exit 1
fi
sleep 2


# ==============================
# 4 - Run build_network_2.sh to setup second network
# ==============================
echo "Building second network (network 2)..."
./build_network_2.sh
if [[ $? -ne 0 ]]; then
    echo "Failed to build second network. Aborting."
    exit 1
fi
sleep 2


# ==============================
# 5 - Start mongodb config server container
# ==============================
echo "Starting MongoDB config server container..."
docker run -dit --name mongodb-config-server --network host \
    -v mongodb-configdb:/data/configdb \
    mongodb-config-server mongod \
        --configsvr \
        --bind_ip "${MONGO_HOST_IP},127.0.0.1" \
    --replSet configReplSet \
        --dbpath /data/configdb \
    --port "${MONGO_CONFIG_PORT}"

if [[ $? -ne 0 ]]; then
    echo "Failed to start MongoDB config server container. Aborting."
    exit 1
fi
sleep 2

# ==============================
# 6 - Start mongodb router container
# ==============================
echo "Starting MongoDB router container..."
docker run -dit --name mongodb-router --network host \
    mongodb-router:latest mongos \
        --configdb "configReplSet/${MONGO_HOST_IP}:${MONGO_CONFIG_PORT}" \
    --bind_ip "${MONGO_HOST_IP}" \
        --port "${MONGO_ROUTER_PORT}"

if [[ $? -ne 0 ]]; then
    echo "Failed to start MongoDB router container. Aborting."
    exit 1
fi
sleep 2


# ==============================
# 7 - Start SDN controller container
# ==============================
cd ..
echo "Current directory for OS-Ken controller: $PWD"

echo "Starting os-ken SDN controller container..."
docker rm -f osken 2>/dev/null

docker run -dit --name osken --network host \
    -v "$PWD":/workspace -w /workspace -e PYTHONPATH=/workspace \
    -e MONGO_ROUTER_HOST="${MONGO_HOST_IP}" \
    -e MONGO_ROUTER_PORT="${MONGO_ROUTER_PORT}" \
    -e MONGO_CONFIG_HOST="${MONGO_HOST_IP}" \
    -e MONGO_CONFIG_PORT="${MONGO_CONFIG_PORT}" \
  osken-controller \
  --verbose sdn_controller.osken_learn_and_log

if [[ $? -ne 0 ]]; then
    echo "Failed to start SDN controller container. Aborting."
    exit 1
fi

cd scripts

# ==============================
# 7.1 - Point both OVS switches to the SDN controller
# ==============================
echo "Pointing OVS switches to the SDN controller..."
docker exec ovs ovs-vsctl set-controller ovs-br0 tcp:127.0.0.1:6633
docker exec ovs ovs-vsctl set-controller ovs-br1 tcp:127.0.0.1:6633

docker exec ovs ovs-vsctl show

if [[ $? -ne 0 ]]; then
    echo "Failed to point OVS switches to SDN controller. Aborting."
    exit 1
fi

echo "Build and setup of networks completed successfully."