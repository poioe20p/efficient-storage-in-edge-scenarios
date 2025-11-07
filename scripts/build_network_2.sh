#!/bin/bash

# ==============================
# 1 - Create OVS bridge and veth pairs
# =============================
echo "Creating OVS bridge ovs-br1..."
docker exec ovs ovs-vsctl add-br ovs-br1

echo "Creating veth pairs..."
sudo ip link add veth10 type veth peer name veth10-peer # container3
sudo ip link add veth11 type veth peer name veth11-peer # container4
sudo ip link add veth12 type veth peer name veth12-peer # router LAN side
sudo ip link add veth13 type veth peer name veth13-peer # mongodb

ip link list

# ==============================
# 3 - Attach veth peers to OVS bridge
# =============================
echo "Attaching veth peers to OVS bridge..."
docker exec ovs ip link set veth10 up # bring up interface connected to container3
docker exec ovs ip link set veth11 up # bring up interface connected to container4
docker exec ovs ip link set veth12 up # bring up interface connected to router LAN side
docker exec ovs ip link set veth13 up # bring up interface connected to mongodb

# ==============================
# Step 3.1: Move veth interfaces into OVS container's namespace
echo "Moving veth interfaces into OVS container's namespace..."
# ==============================
PID_OVS=$(docker inspect -f '{{.State.Pid}}' ovs)
sudo mkdir -p /var/run/netns
sudo ln -sf /proc/$PID_OVS/ns/net /var/run/netns/ovs
sudo ip link set veth10 netns ovs
sudo ip link set veth11 netns ovs
sudo ip link set veth12 netns ovs
sudo ip link set veth13 netns ovs

# ==============================
# Step 3.2: Attach veth interfaces to OVS bridge inside container
echo "Attaching veth interfaces to OVS bridge inside container..."
# ==============================
docker exec ovs ovs-vsctl add-port ovs-br1 veth10
docker exec ovs ovs-vsctl add-port ovs-br1 veth11
docker exec ovs ovs-vsctl add-port ovs-br1 veth12
docker exec ovs ovs-vsctl add-port ovs-br1 veth13

# ==============================
# Step 4: Launch containers
echo "Launching application containers..."
# ==============================
# --network none: prevents Docker from creating default network
# --privileged for NAT router: needed to run iptables inside it
docker run -dit --name container3 --network none ubuntu-host
docker run -dit --name container4 --network none ubuntu-host

# Review as each network will have its own mongodb shard
# Load MongoDB env-file if present (to reuse init creds)
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
MONGO_ENV_FILE=${MONGO_ENV_FILE:-"${SCRIPT_DIR}/../.env-mongo"}
echo "Using MongoDB env file: $MONGO_ENV_FILE"
if [[ -f "$MONGO_ENV_FILE" ]]; then
  echo "Loading MongoDB environment from: $MONGO_ENV_FILE"
  # Export all simple KEY=VALUE entries from the env file
  set -a
  source "$MONGO_ENV_FILE"
  set +a
  
  docker run -dit --name mongodb-n2 --network none \
    --env-file "$MONGO_ENV_FILE" \
    -v mongodb-n2-data:/data/db \
    ubuntu-mongodb --shardsvr --replSet rs_net2
else
  echo "WARNING: MongoDB env file not found at $MONGO_ENV_FILE"
  echo "MongoDB will start without authentication!"
  docker run -dit --name mongodb-n2 --network none \
    -v mongodb-n2-data:/data/db \
    ubuntu-mongodb --shardsvr --replSet rs_net2
fi

if [[ $? -ne 0 ]]; then
    echo "Failed to start application containers. Aborting."
    exit 1
fi

# Get process IDs (needed to move interfaces into namespaces)
PID3=$(docker inspect -f '{{.State.Pid}}' container3)
PID4=$(docker inspect -f '{{.State.Pid}}' container4)
PID_ROUTER=$(docker inspect -f '{{.State.Pid}}' nat-router)
PID_MONGO=$(docker inspect -f '{{.State.Pid}}' mongodb-n2)

# ==============================
# Step 5: Move peer interfaces into the containers
echo "Moving veth peer interfaces into application containers..."
# ==============================
sudo ip link set veth10-peer netns $PID3
sudo ip link set veth11-peer netns $PID4
sudo ip link set veth12-peer netns $PID_ROUTER
sudo ip link set veth13-peer netns $PID_MONGO

# ==============================
# Step 6: Configure container3
echo "Configuring network interfaces inside containers..."
# ==============================
# nsenter lets you execute a command inside one or more Linux namespaces of an existing process.
# Containers have their own namespaces (<PID>); by entering the container’s network namespace,
# you can run ip/iptables as if you were inside the container’s network stack.

# -t to specify target namespace by PID
# -n to specify network namespace
# Configure container3
sudo nsenter -t $PID3 -n ip link set veth10-peer name eth0
sudo nsenter -t $PID3 -n ip link set eth0 address 00:00:00:00:00:05   # static MAC
sudo nsenter -t $PID3 -n ip link set eth0 up
sudo nsenter -t $PID3 -n ip addr add 10.0.1.2/24 dev eth0
sudo nsenter -t $PID3 -n ip route add default via 10.0.1.1  # router as gateway

# Configure container4
sudo nsenter -t $PID4 -n ip link set veth11-peer name eth0
sudo nsenter -t $PID4 -n ip link set eth0 address 00:00:00:00:00:06   # static MAC
sudo nsenter -t $PID4 -n ip link set eth0 up
sudo nsenter -t $PID4 -n ip addr add 10.0.1.3/24 dev eth0
sudo nsenter -t $PID4 -n ip route add default via 10.0.1.1

# Configure mongodb container
sudo nsenter -t $PID_MONGO -n ip link set veth13-peer name eth0
sudo nsenter -t $PID_MONGO -n ip link set eth0 address 00:00:00:00:00:07   # static MAC
sudo nsenter -t $PID_MONGO -n ip link set eth0 up
sudo nsenter -t $PID_MONGO -n ip addr add 10.0.1.4/24 dev eth0
sudo nsenter -t $PID_MONGO -n ip route add default via 10.0.1.1

# ==============================
# Step 7: Configure NAT router internal (LAN side)
echo "Configuring NAT router interfaces..."
# ==============================
sudo nsenter -t $PID_ROUTER -n ip link set veth12-peer name eth2
sudo nsenter -t $PID_ROUTER -n ip link set eth2 address 00:00:00:00:00:CC  # router LAN MAC
sudo nsenter -t $PID_ROUTER -n ip link set eth2 up
sudo nsenter -t $PID_ROUTER -n ip addr add 10.0.1.1/24 dev eth2  # default GW for LAN


# ==============================
# Step 8: Ensure host routing for Network 2
# ==============================

# Ensure the host can reach the lab subnet (10.0.1.0/24) for tools like MongoDB Compass
echo "Ensuring host route to 10.0.1.0/24 via 192.168.100.2..."
if ! sudo ip route replace 10.0.1.0/24 via 192.168.100.2 dev veth4 >/dev/null 2>&1; then
  echo "WARNING: failed to program route to 10.0.1.0/24; check host networking." >&2
else
  ip route show 10.0.1.0/24
fi

# Show OVS status
docker exec ovs ovs-vsctl show