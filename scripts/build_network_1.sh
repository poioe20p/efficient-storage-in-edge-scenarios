#!/bin/bash

# ==============================
# 1 - Create OVS bridge and veth pairs
# =============================
echo "Creating OVS bridge ovs-br0..."
docker exec ovs ovs-vsctl add-br ovs-br0

echo "Creating veth pairs..."
sudo ip link add veth1 type veth peer name veth1-peer # container1
sudo ip link add veth2 type veth peer name veth2-peer # container2
sudo ip link add veth3 type veth peer name veth3-peer # router LAN side
sudo ip link add veth4 type veth peer name veth4-peer # router WAN side
sudo ip link add veth5 type veth peer name veth5-peer # mongodb

ip link list

# ==============================
# 3 - Attach veth peers to OVS bridge
# =============================
echo "Attaching veth peers to OVS bridge..."
docker exec ovs ip link set veth1 up # bring up interface connected to container1
docker exec ovs ip link set veth2 up # bring up interface connected to container2
docker exec ovs ip link set veth3 up # bring up interface connected to router LAN side
docker exec ovs ip link set veth5 up # bring up interface connected to mongodb

# ==============================
# Step 3.1: Move veth interfaces into OVS container's namespace
echo "Moving veth interfaces into OVS container's namespace..."
# ==============================
PID_OVS=$(docker inspect -f '{{.State.Pid}}' ovs)
sudo mkdir -p /var/run/netns
sudo ln -sf /proc/$PID_OVS/ns/net /var/run/netns/ovs
sudo ip link set veth1 netns ovs
sudo ip link set veth2 netns ovs
sudo ip link set veth3 netns ovs
sudo ip link set veth5 netns ovs

# ==============================
# Step 3.2: Attach veth interfaces to OVS bridge inside container
echo "Attaching veth interfaces to OVS bridge inside container..."
# ==============================
docker exec ovs ovs-vsctl add-port ovs-br0 veth1
docker exec ovs ovs-vsctl add-port ovs-br0 veth2
docker exec ovs ovs-vsctl add-port ovs-br0 veth3
docker exec ovs ovs-vsctl add-port ovs-br0 veth5

# ==============================
# Step 4: Launch containers
echo "Launching application containers..."
# ==============================
# --network none: prevents Docker from creating default network
# --privileged for NAT router: needed to run iptables inside it
docker run -dit --name container1 --network none ubuntu-host
docker run -dit --name container2 --network none ubuntu-host

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
  
  docker run -dit --name mongodb-n1 --network none \
    --env-file "$MONGO_ENV_FILE" \
    -v mongodb-data:/data/db \
    ubuntu-mongodb --shardsvr --replSet rs_net1
else
  echo "WARNING: MongoDB env file not found at $MONGO_ENV_FILE"
  echo "MongoDB will start without authentication!"
  docker run -dit --name mongodb-n1 --network none \
    -v mongodb-data:/data/db \
    ubuntu-mongodb --shardsvr --replSet rs_net1
fi

if [[ $? -ne 0 ]]; then
    echo "Failed to start application containers. Aborting."
    exit 1
fi

# Bind mongodb IP address to mongodb-n1-host for easier access
# docker network connect host mongodb-n1
# sleep 2
# # ==============================


# Get process IDs (needed to move interfaces into namespaces)
PID1=$(docker inspect -f '{{.State.Pid}}' container1)
PID2=$(docker inspect -f '{{.State.Pid}}' container2)
PID_ROUTER=$(docker inspect -f '{{.State.Pid}}' nat-router)
PID_MONGO=$(docker inspect -f '{{.State.Pid}}' mongodb-n1)

# ==============================
# Step 5: Move peer interfaces into the containers
echo "Moving veth peer interfaces into application containers..."
# ==============================
sudo ip link set veth1-peer netns $PID1
sudo ip link set veth2-peer netns $PID2
sudo ip link set veth3-peer netns $PID_ROUTER
sudo ip link set veth4-peer netns $PID_ROUTER   # router WAN side
sudo ip link set veth5-peer netns $PID_MONGO

# ==============================
# Step 6: Configure container1
echo "Configuring network interfaces inside containers..."
# ==============================
# nsenter lets you execute a command inside one or more Linux namespaces of an existing process.
# Containers have their own namespaces (<PID>); by entering the container’s network namespace,
# you can run ip/iptables as if you were inside the container’s network stack.

# -t to specify target namespace by PID
# -n to specify network namespace
# Configure container1
sudo nsenter -t $PID1 -n ip link set veth1-peer name eth0
sudo nsenter -t $PID1 -n ip link set eth0 address 00:00:00:00:00:02   # static MAC
sudo nsenter -t $PID1 -n ip link set eth0 up
sudo nsenter -t $PID1 -n ip addr add 10.0.0.2/24 dev eth0
sudo nsenter -t $PID1 -n ip route add default via 10.0.0.1  # router as gateway

# Configure container2
sudo nsenter -t $PID2 -n ip link set veth2-peer name eth0
sudo nsenter -t $PID2 -n ip link set eth0 address 00:00:00:00:00:03   # static MAC
sudo nsenter -t $PID2 -n ip link set eth0 up
sudo nsenter -t $PID2 -n ip addr add 10.0.0.3/24 dev eth0
sudo nsenter -t $PID2 -n ip route add default via 10.0.0.1

# Configure mongodb container
sudo nsenter -t $PID_MONGO -n ip link set veth5-peer name eth0
sudo nsenter -t $PID_MONGO -n ip link set eth0 address 00:00:00:00:00:04   # static MAC
sudo nsenter -t $PID_MONGO -n ip link set eth0 up
sudo nsenter -t $PID_MONGO -n ip addr add 10.0.0.4/24 dev eth0
sudo nsenter -t $PID_MONGO -n ip route add default via 10.0.0.1

# ==============================
# Step 7: Configure NAT router internal (LAN side)
echo "Configuring NAT router interfaces..."
# ==============================
sudo nsenter -t $PID_ROUTER -n ip link set veth3-peer name eth1
sudo nsenter -t $PID_ROUTER -n ip link set eth1 address 00:00:00:00:00:AA  # router LAN MAC
sudo nsenter -t $PID_ROUTER -n ip link set eth1 up
sudo nsenter -t $PID_ROUTER -n ip addr add 10.0.0.1/24 dev eth1  # default GW for LAN

# Enable IP forwarding + NAT in the router
sudo nsenter -t $PID_ROUTER -n bash -c "
  echo 1 > /proc/sys/net/ipv4/ip_forward
  iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
"
# ==============================
# Step 8 - Configure NAT router external (WAN) side
# ==============================
echo "Configuring NAT router WAN interface..."
PID_ROUTER=$(docker inspect -f '{{.State.Pid}}' nat-router)
sudo nsenter -t $PID_ROUTER -n ip link set veth4-peer name eth0
sudo nsenter -t $PID_ROUTER -n ip link set eth0 address 00:00:00:00:00:BB  # router LAN MAC
sudo nsenter -t $PID_ROUTER -n ip link set eth0 up
sudo nsenter -t $PID_ROUTER -n ip addr add 192.168.100.2/24 dev eth0  # router’s WAN IP
sudo nsenter -t $PID_ROUTER -n ip route add default via 192.168.100.1  # host as gateway

# Enable IP forwarding + NAT in the router
sudo nsenter -t $PID_ROUTER -n bash -c "
  echo 1 > /proc/sys/net/ipv4/ip_forward
  iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE
"

sudo ip link set veth4 up
sudo ip addr add 192.168.100.1/24 dev veth4  # host acts as router’s gateway

# Ensure the host can reach the lab subnet (10.0.0.0/24) for tools like MongoDB Compass
echo "Ensuring host route to 10.0.0.0/24 via 192.168.100.2..."
if ! sudo ip route replace 10.0.0.0/24 via 192.168.100.2 dev veth4 >/dev/null 2>&1; then
  echo "WARNING: failed to program route to 10.0.0.0/24; check host networking." >&2
else
  ip route show 10.0.0.0/24
fi

# Enable IP forwarding + NAT on host for Internet access
# You need to adjust below enp0s3 to the network interface VM is using
sudo sysctl -w net.ipv4.ip_forward=1
sudo iptables -t nat -A POSTROUTING -s 192.168.100.0/24 -o enp0s3 -j MASQUERADE

# Show OVS status
docker exec ovs ovs-vsctl show