#!/bin/bash
# -e: exit immediately if any command fails
# -u: treat unset variables as errors (catches empty PID_AGG etc.)
# -o pipefail: a pipeline fails if any command in it fails, not just the last
set -euo pipefail

# ==============================
# Helper: get_container_pid <container_name> [timeout_s]
# Retries until the container has a non-zero PID or the timeout is reached.
# If the container has exited early, prints its logs and aborts.
# ==============================
get_container_pid() {
    local container="$1"
    local timeout="${2:-5}"
    local elapsed=0
    local pid=0
    local status

    while [[ $elapsed -lt $timeout ]]; do
        status=$(docker inspect -f '{{.State.Status}}' "$container" 2>/dev/null || true)
        if [[ "$status" == "exited" || "$status" == "dead" ]]; then
            echo "Error: container '$container' exited unexpectedly." >&2
            echo "--- logs for $container ---" >&2
            docker logs "$container" >&2 || true
            exit 1
        fi
        pid=$(docker inspect -f '{{.State.Pid}}' "$container" 2>/dev/null || echo 0)
        if [[ "$pid" -gt 0 ]]; then
            echo "$pid"
            return 0
        fi
        sleep 1
        (( elapsed++ )) || true
    done

    echo "Error: timed out waiting for PID of container '$container'." >&2
    echo "--- logs for $container ---" >&2
    docker logs "$container" >&2 || true
    exit 1
}

# ==============================
# 1 - Create OVS bridge and veth pairs
# =============================
echo "Creating OVS bridge ovs-br1..."
docker exec ovs ovs-vsctl add-br ovs-br1

echo "Creating veth pairs..."
for IFACE in veth21 veth22 veth23 veth24 veth21-peer veth22-peer veth23-peer veth24-peer; do
  if ip link show "$IFACE" >/dev/null 2>&1; then
    sudo ip link del "$IFACE" >/dev/null 2>&1 || true
  fi
done
# Add links to kernel
# NOTE: veth5 and veth6 are reserved for build_router.sh (router WAN and Internet uplink).
sudo ip link add veth21 type veth peer name veth21-peer # edge_server_n2
sudo ip link add veth22 type veth peer name veth22-peer # edge_storage_server_n2
sudo ip link add veth23 type veth peer name veth23-peer # router LAN side
sudo ip link add veth24 type veth peer name veth24-peer # aggregator_n2

# ==============================
# Step 3.1: Move veth interfaces into OVS container's namespace
echo "Moving veth interfaces into OVS container's namespace..."
# ==============================
PID_OVS=$(docker inspect -f '{{.State.Pid}}' ovs)
sudo mkdir -p /var/run/netns
sudo ln -sf /proc/$PID_OVS/ns/net /var/run/netns/ovs
sudo ip link set veth21 netns ovs
sudo ip link set veth22 netns ovs
sudo ip link set veth23 netns ovs
sudo ip link set veth24 netns ovs

# ==============================
# Step 3.2: Attach veth interfaces to OVS bridge inside container
echo "Attaching veth interfaces to OVS bridge inside container..."
# ==============================
docker exec ovs ovs-vsctl add-port ovs-br1 veth21
docker exec ovs ovs-vsctl add-port ovs-br1 veth22
docker exec ovs ovs-vsctl add-port ovs-br1 veth23
docker exec ovs ovs-vsctl add-port ovs-br1 veth24

# ==============================
# Step 3.3: Bring up veth interfaces inside OVS namespace (must happen after netns move)
echo "Bringing up veth interfaces inside OVS namespace..."
# ==============================
docker exec ovs ip link set veth21 up # interface connected to edge_server_n2
docker exec ovs ip link set veth22 up # interface connected to edge_storage_server_n2
docker exec ovs ip link set veth23 up # interface connected to router LAN side
docker exec ovs ip link set veth24 up # interface connected to aggregator_n2

# ==============================
# Step 4: Launch containers
echo "Launching application containers..."
# ==============================
# --network none: prevents Docker from creating default network
# --privileged for NAT router: needed to run iptables inside it
docker run -dit --name edge_server_n2 --network none \
  -e LAN_ID=lan2 \
  -e AGGREGATOR_PULL_ADDR=tcp://10.0.1.5:5555 \
  -e LOG_LEVEL=INFO \
  -e HEARTBEAT_ENABLED=1 \
  edge_server

# Review as each network will have its own mongodb shard
# Load MongoDB env-file if present (to reuse init creds)
echo "Starting MongoDB shard member container edge_storage_server_n2..."
docker run -dit --name edge_storage_server_n2 --network none \
  --no-healthcheck \
  -e LAN_ID=lan2 \
  -e AGGREGATOR_PULL_ADDR=tcp://10.0.1.5:5555 \
  -e MONGO_REPLSET=rs_net2 \
  -e MONGO_PORT=27018 \
  -e TELEMETRY_INTERVAL_S=10 \
  -e LOG_LEVEL=INFO \
  -e HEARTBEAT_ENABLED=1 \
  -v edge_storage_server_n2-data:/data/db edge_storage_server

echo "Starting aggregator_n2 container..."
docker run -dit --name aggregator_n2 --network none \
  -e NETWORK_ID=lan2 \
  -e PULL_ADDR=tcp://0.0.0.0:5555 \
  -e PUB_ADDR=tcp://0.0.0.0:5556 \
  -e WINDOW_S=10 \
  -e LOG_LEVEL=DEBUG \
  local_state_server

if [[ $? -ne 0 ]]; then
    echo "Failed to start application containers. Aborting."
    exit 1
fi

# Get process IDs (needed to move interfaces into namespaces)
PID=$(get_container_pid edge_server_n2)
PID_ROUTER=$(get_container_pid nat-router)
PID_MONGO=$(get_container_pid edge_storage_server_n2)
PID_AGG=$(get_container_pid aggregator_n2)

# ==============================
# Step 5: Move peer interfaces into the containers
echo "Moving veth peer interfaces into application containers..."
# ==============================
sudo ip link set veth21-peer netns $PID
sudo ip link set veth22-peer netns $PID_MONGO
sudo ip link set veth23-peer netns $PID_ROUTER
sudo ip link set veth24-peer netns $PID_AGG

# ==============================
# Step 6: Configure edge_storage_server_n2
echo "Configuring network interfaces inside containers..."
# ==============================
# nsenter lets you execute a command inside one or more Linux namespaces of an existing process.
# Containers have their own namespaces (<PID>); by entering the container’s network namespace,
# you can run ip/iptables as if you were inside the container’s network stack.

# -t to specify target namespace by PID
# -n to specify network namespace
# Configure edge_server_n2 container
sudo nsenter -t $PID -n ip link set veth21-peer name eth0
sudo nsenter -t $PID -n ip link set eth0 address 00:00:00:00:00:05   # static MAC
sudo nsenter -t $PID -n ip link set eth0 up
sudo nsenter -t $PID -n ip addr add 10.0.1.2/24 dev eth0
sudo nsenter -t $PID -n ip route add default via 10.0.1.1  # router as gateway

# Configure edge_storage_server_n2 container
sudo nsenter -t $PID_MONGO -n ip link set veth22-peer name eth0
sudo nsenter -t $PID_MONGO -n ip link set eth0 address 00:00:00:00:00:06   # static MAC
sudo nsenter -t $PID_MONGO -n ip link set eth0 up
sudo nsenter -t $PID_MONGO -n ip addr add 10.0.1.4/24 dev eth0
sudo nsenter -t $PID_MONGO -n ip route add default via 10.0.1.1

# Configure aggregator_n2 container
sudo nsenter -t $PID_AGG -n ip link set veth24-peer name eth0
sudo nsenter -t $PID_AGG -n ip link set eth0 address 00:00:00:00:00:07
sudo nsenter -t $PID_AGG -n ip link set eth0 up
sudo nsenter -t $PID_AGG -n ip addr add 10.0.1.5/24 dev eth0
sudo nsenter -t $PID_AGG -n ip route add default via 10.0.1.1

# ==============================
# Step 7: Configure NAT router internal (LAN side)
echo "Configuring NAT router interfaces..."
# ==============================
sudo nsenter -t $PID_ROUTER -n ip link set veth23-peer name eth2 # port number 3 on OVS (veth23 <-> ovs-br1)
sudo nsenter -t $PID_ROUTER -n ip link set eth2 address 00:00:00:00:00:CC  # router LAN MAC
sudo nsenter -t $PID_ROUTER -n ip link set eth2 up
sudo nsenter -t $PID_ROUTER -n ip addr add 10.0.1.1/24 dev eth2  # default GW for LAN


# Show OVS status
docker exec ovs ovs-vsctl show