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
OSKEN1_PORT=${OSKEN1_PORT:-6653}
OSKEN2_PORT=${OSKEN2_PORT:-6654}

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
# 4 - Initialize MongoDB cluster using Python
# ==============================
# Note: The MongoDB initialization steps are now handled by Python scripts
# in the build_mongodb_cluster module. This provides better error handling
# and maintainability.

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
# 5.1 - Python MongoDB setup will be called after both networks are up
# =============================

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
# 6.1 - Python MongoDB setup will be called after both networks and router are up
# =============================

# ==============================
# 7 - Start mongodb router container
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

# ==============================================
# 8 - Initialize MongoDB cluster with Python
# ==============================================
echo "Initializing MongoDB cluster using Python..."
cd ..
python3 -m sdn_controller.usecases.build_mongodb_cluster.cli

if [[ $? -ne 0 ]]; then
    echo "Failed to initialize MongoDB cluster. Aborting."
    exit 1
fi
cd scripts

# ==============================
# 9 - Start SDN controller container
# ==============================
cd ..
echo "Current directory for OS-Ken controller: $PWD"

echo "Starting os-ken SDN controller container..."
docker rm -f osken 2>/dev/null

PWD=$(pwd)
MONGO_ENV_FILE="$PWD/../.env-mongo"

if [[ ! -f "$MONGO_ENV_FILE" ]]; then
    echo "MongoDB environment file '$MONGO_ENV_FILE' not found. Aborting."
    echo "Using direct environment variables instead."
    docker run -dit --name osken --network host \
        -v "$PWD":/workspace -w /workspace -e PYTHONPATH=/workspace \
        -e MONGO_ROUTER_HOST="${MONGO_HOST_IP}" \
        -e MONGO_ROUTER_PORT="${MONGO_ROUTER_PORT}" \
        -e MONGO_CONFIG_HOST="${MONGO_HOST_IP}" \
        -e MONGO_CONFIG_PORT="${MONGO_CONFIG_PORT}" \
        osken-controller --observe-links --ofp-tcp-listen-port "${OSKEN1_PORT}" \
            --log-config-file /etc/osken/logging.conf \
            os_ken.topology.switches sdn_controller.calculate_stats_n1

    docker run -dit --name osken_2 --network host \
        -v "$PWD":/workspace -w /workspace -e PYTHONPATH=/workspace \
        -e MONGO_ROUTER_HOST="${MONGO_HOST_IP}" \
        -e MONGO_ROUTER_PORT="${MONGO_ROUTER_PORT}" \
        -e MONGO_CONFIG_HOST="${MONGO_HOST_IP}" \
        -e MONGO_CONFIG_PORT="${MONGO_CONFIG_PORT}" \
        osken-controller --observe-links --ofp-tcp-listen-port "${OSKEN2_PORT}" \
            --log-config-file /etc/osken/logging.conf \
            os_ken.topology.switches sdn_controller.calculate_stats_n2

else
    docker run -dit --name osken --network host \
        --env-file "$MONGO_ENV_FILE" \
        -v "$PWD":/workspace -w /workspace -e PYTHONPATH=/workspace \
        osken-controller --observe-links --ofp-tcp-listen-port "${OSKEN1_PORT}" \
            --log-config-file /etc/osken/logging.conf \
            os_ken.topology.switches sdn_controller.calculate_stats_n1

    docker run -dit --name osken_2 --network host \
        --env-file "$MONGO_ENV_FILE" \
        -v "$PWD":/workspace -w /workspace -e PYTHONPATH=/workspace \
        osken-controller --observe-links --ofp-tcp-listen-port "${OSKEN2_PORT}" \
            --log-config-file /etc/osken/logging.conf \
            os_ken.topology.switches sdn_controller.calculate_stats_n2
fi

if [[ $? -ne 0 ]]; then
    echo "Failed to start SDN controller container. Aborting."
    exit 1
fi

cd scripts

# ==============================
# 9.1 - Point both OVS switches to the SDN controller
# ==============================
echo "Pointing OVS switches to the SDN controllers..."
docker exec ovs ovs-vsctl set-controller ovs-br0 tcp:127.0.0.1:${OSKEN1_PORT}
docker exec ovs ovs-vsctl set-controller ovs-br2 tcp:127.0.0.1:${OSKEN1_PORT}
docker exec ovs ovs-vsctl set-controller ovs-br1 tcp:127.0.0.1:${OSKEN2_PORT}
# docker exec ovs ovs-vsctl set-controller ovs-br1 tcp:127.0.0.1:${OSKEN1_PORT}

docker exec ovs ovs-vsctl show

if [[ $? -ne 0 ]]; then
    echo "Failed to point OVS switches to SDN controller. Aborting."
    exit 1
fi

echo "Build and setup of networks completed successfully."