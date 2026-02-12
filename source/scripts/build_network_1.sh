#!/bin/bash

# ==============================
# 1 - Create OVS bridge and veth pairs
# =============================
echo "Creating OVS bridge ovs-br0..."
docker exec ovs ovs-vsctl add-br ovs-br0
docker exec ovs ovs-vsctl add-br ovs-br2

echo "Creating veth pairs..."
for IFACE in veth1 veth2 veth3 veth4 veth5 veth6 veth7 veth8 veth9 \
             veth1-peer veth2-peer veth3-peer veth4-peer veth5-peer veth6-peer veth7-peer veth8-peer veth9-peer; do
  if ip link show "$IFACE" >/dev/null 2>&1; then
    sudo ip link del "$IFACE" >/dev/null 2>&1 || true
  fi
done

# Add links to kernel
sudo ip link add veth1 type veth peer name veth1-peer # container1
sudo ip link add veth2 type veth peer name veth2-peer # container2
sudo ip link add veth3 type veth peer name veth3-peer # router LAN side
sudo ip link add veth4 type veth peer name veth4-peer # router WAN side
sudo ip link add veth5 type veth peer name veth5-peer # mongodb
sudo ip link add veth6 type veth peer name veth6-peer # router internet uplink
sudo ip link add veth7 type veth peer name veth7-peer # container5
sudo ip link add veth8 type veth peer name veth8-peer # ovs-br0 <-> ovs-br2 patch
sudo ip link add veth9 type veth peer name veth9-peer # mongodb-n3

# ==============================
# 3 - Attach veth peers to OVS bridge
# =============================
echo "Attaching veth peers to OVS bridge..."
docker exec ovs ip link set veth1 up # bring up interface connected to container1
docker exec ovs ip link set veth2 up # bring up interface connected to container2
docker exec ovs ip link set veth3 up # bring up interface connected to router LAN side
docker exec ovs ip link set veth5 up # bring up interface connected to mongodb
docker exec ovs ip link set veth7 up # bring up interface connected to container5
docker exec ovs ip link set veth8 up # bring up patch link on ovs-br0 side
docker exec ovs ip link set veth8-peer up # bring up patch link on ovs-br2 side
docker exec ovs ip link set veth9 up # bring up interface connected to mongodb-n3

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
sudo ip link set veth7 netns ovs
sudo ip link set veth8 netns ovs
sudo ip link set veth8-peer netns ovs
sudo ip link set veth9 netns ovs

# ==============================
# Step 3.2: Attach veth interfaces to OVS bridge inside container
echo "Attaching veth interfaces to OVS bridge inside container..."
# ==============================
docker exec ovs ovs-vsctl add-port ovs-br0 veth1
docker exec ovs ovs-vsctl add-port ovs-br0 veth2
docker exec ovs ovs-vsctl add-port ovs-br0 veth3
docker exec ovs ovs-vsctl add-port ovs-br0 veth5
docker exec ovs ovs-vsctl add-port ovs-br0 veth9
docker exec ovs ovs-vsctl add-port ovs-br2 veth7
docker exec ovs ovs-vsctl add-port ovs-br0 veth8 # ovs-br0 side of patch link
docker exec ovs ovs-vsctl add-port ovs-br2 veth8-peer # ovs-br2 side of patch link

# ==============================
# Step 4: Launch containers
echo "Launching application containers..."
# ==============================
# --network none: prevents Docker from creating default network
# --privileged for NAT router: needed to run iptables inside it
docker run -dit --name container1 --network none ubuntu-host
docker run -dit --name container2 --network none ubuntu-host
docker run -dit --name container5 --network none ubuntu-host

# Review as each network will have its own mongodb shard
# Load MongoDB env-file if present (to reuse init creds)
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
MONGO_ENV_FILE=${MONGO_ENV_FILE:-"${SCRIPT_DIR}/../.env-mongo"}

if [[ -f "$MONGO_ENV_FILE" ]]; then
  echo "Loading MongoDB environment from: $MONGO_ENV_FILE"
  docker run -dit --name mongodb-n1 --network none \
    --env-file "$MONGO_ENV_FILE" \
    --no-healthcheck \
    -v mongodb-n1-data:/data/db ubuntu-mongodb mongod \
    --shardsvr --replSet rs_net1 --bind_ip_all --port 27018
  
  docker run -dit --name mongodb-n3 --network none \
    --env-file "$MONGO_ENV_FILE" \
    --no-healthcheck \
    -v mongodb-n3-data:/data/db ubuntu-mongodb mongod \
    --shardsvr --replSet rs_net3 --bind_ip_all --port 27018
else
  echo "WARNING: MongoDB env file not found at $MONGO_ENV_FILE"
  echo "MongoDB will start without authentication!"
  docker run -dit --name mongodb-n1 --network none \
    --no-healthcheck \
    -v mongodb-n1-data:/data/db ubuntu-mongodb mongod \
    --shardsvr --replSet rs_net1 --bind_ip_all --port 27018
  
  docker run -dit --name mongodb-n3 --network none \
    --no-healthcheck \
    -v mongodb-n3-data:/data/db ubuntu-mongodb mongod \
    --shardsvr --replSet rs_net3 --bind_ip_all --port 27018
fi

# If any docker run fails, abort early.
if [[ $? -ne 0 ]]; then
  echo "Failed to start application containers. Aborting."
  exit 1
fi


# ==============================
# Get process IDs (needed to move interfaces into namespaces)
PID1=$(docker inspect -f '{{.State.Pid}}' container1)
PID2=$(docker inspect -f '{{.State.Pid}}' container2)
PID5=$(docker inspect -f '{{.State.Pid}}' container5)
PID_ROUTER=$(docker inspect -f '{{.State.Pid}}' nat-router)
PID_MONGO=$(docker inspect -f '{{.State.Pid}}' mongodb-n1)
PID_MONGO2=$(docker inspect -f '{{.State.Pid}}' mongodb-n3)

# ==============================
# Step 5: Move peer interfaces into the containers
echo "Moving veth peer interfaces into application containers..."
# ==============================
sudo ip link set veth1-peer netns $PID1
sudo ip link set veth2-peer netns $PID2
sudo ip link set veth7-peer netns $PID5
sudo ip link set veth3-peer netns $PID_ROUTER
sudo ip link set veth4-peer netns $PID_ROUTER   # router WAN side
sudo ip link set veth5-peer netns $PID_MONGO
sudo ip link set veth6-peer netns $PID_ROUTER   # router dedicated uplink
sudo ip link set veth9-peer netns $PID_MONGO2

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

# Configure container5
sudo nsenter -t $PID5 -n ip link set veth7-peer name eth0
sudo nsenter -t $PID5 -n ip link set eth0 address 00:00:00:00:00:08   # static MAC
sudo nsenter -t $PID5 -n ip link set eth0 up
sudo nsenter -t $PID5 -n ip addr add 10.0.0.5/24 dev eth0
sudo nsenter -t $PID5 -n ip route add default via 10.0.0.1

# Configure mongodb container
sudo nsenter -t $PID_MONGO -n ip link set veth5-peer name eth0
sudo nsenter -t $PID_MONGO -n ip link set eth0 address 00:00:00:00:00:04   # static MAC
sudo nsenter -t $PID_MONGO -n ip link set eth0 up
sudo nsenter -t $PID_MONGO -n ip addr add 10.0.0.4/24 dev eth0
sudo nsenter -t $PID_MONGO -n ip route add default via 10.0.0.1

# Configure mongodb-n3 container
sudo nsenter -t $PID_MONGO2 -n ip link set veth9-peer name eth0
sudo nsenter -t $PID_MONGO2 -n ip link set eth0 address 00:00:00:00:00:09   # static MAC
sudo nsenter -t $PID_MONGO2 -n ip link set eth0 up
sudo nsenter -t $PID_MONGO2 -n ip addr add 10.0.0.6/24 dev eth0
sudo nsenter -t $PID_MONGO2 -n ip route add default via 10.0.0.1

# ==============================
# Step 7: Configure NAT router internal (LAN side)
echo "Configuring NAT router interfaces..."
# ==============================
sudo nsenter -t $PID_ROUTER -n ip link set veth3-peer name eth1
sudo nsenter -t $PID_ROUTER -n ip link set eth1 address 00:00:00:00:00:AA  # router LAN MAC
sudo nsenter -t $PID_ROUTER -n ip link set eth1 up
sudo nsenter -t $PID_ROUTER -n ip addr add 10.0.0.1/24 dev eth1  # default GW for LAN

# Enable IP forwarding inside the router namespace (no blanket MASQUERADE so we
# can control how shard ports are exposed)
sudo nsenter -t $PID_ROUTER -n bash -c "
  echo 1 > /proc/sys/net/ipv4/ip_forward
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

# Ensure IP forwarding stays enabled after reconfiguring interfaces.
sudo nsenter -t $PID_ROUTER -n bash -c "
  echo 1 > /proc/sys/net/ipv4/ip_forward
"

sudo ip link set veth4 up
sudo ip addr add 192.168.100.1/24 dev veth4  # host acts as router’s gateway

# Configure dedicated uplink between host and NAT router for Internet access.
INTERNET_LINK_HOST_IP=${INTERNET_LINK_HOST_IP:-172.20.0.1/30}
INTERNET_LINK_ROUTER_IP=${INTERNET_LINK_ROUTER_IP:-172.20.0.2/30}
INTERNET_LINK_GW=${INTERNET_LINK_GW:-172.20.0.1}
sudo ip link set veth6 up
sudo ip addr replace ${INTERNET_LINK_HOST_IP} dev veth6
sudo nsenter -t $PID_ROUTER -n ip link set veth6-peer name eth3
sudo nsenter -t $PID_ROUTER -n ip link set eth3 address 00:00:00:00:00:DD
sudo nsenter -t $PID_ROUTER -n ip link set eth3 up
sudo nsenter -t $PID_ROUTER -n ip addr replace ${INTERNET_LINK_ROUTER_IP} dev eth3
sudo nsenter -t $PID_ROUTER -n ip route replace default via ${INTERNET_LINK_GW} dev eth3
sudo nsenter -t $PID_ROUTER -n ip route replace 192.168.100.0/24 via 192.168.100.1 dev eth0

# Ensure the host can reach the lab subnet (10.0.0.0/24) for tools like MongoDB Compass
echo "Ensuring host route to 10.0.0.0/24 via 192.168.100.2..."
if ! sudo ip route replace 10.0.0.0/24 via 192.168.100.2 dev veth4 >/dev/null 2>&1; then
  echo "WARNING: failed to program route to 10.0.0.0/24; check host networking." >&2
else
  ip route show 10.0.0.0/24
fi

# Enable IP forwarding + NAT on host for Internet access (auto-detect uplink or
# fall back to enp0s3 if detection fails).
sudo sysctl -w net.ipv4.ip_forward=1
DEFAULT_UPLINK_IF=${DEFAULT_UPLINK_IF:-$(ip route get 8.8.8.8 2>/dev/null | awk '/dev/ {for (i=1;i<=NF;i++) if ($i=="dev") {print $(i+1); exit}}')}
if [[ -z "${DEFAULT_UPLINK_IF}" ]]; then
  DEFAULT_UPLINK_IF="enp0s3"
  echo "WARNING: Unable to auto-detect uplink interface, defaulting to ${DEFAULT_UPLINK_IF}." >&2
else
  echo "Using ${DEFAULT_UPLINK_IF} as host uplink interface for MASQUERADE."
fi
if ! sudo iptables -t nat -C POSTROUTING -s 192.168.100.0/24 -o "${DEFAULT_UPLINK_IF}" -j MASQUERADE 2>/dev/null; then
  sudo iptables -t nat -A POSTROUTING -s 192.168.100.0/24 -o "${DEFAULT_UPLINK_IF}" -j MASQUERADE
fi
if ! sudo iptables -t nat -C POSTROUTING -s 172.20.0.0/30 -o "${DEFAULT_UPLINK_IF}" -j MASQUERADE 2>/dev/null; then
  sudo iptables -t nat -A POSTROUTING -s 172.20.0.0/30 -o "${DEFAULT_UPLINK_IF}" -j MASQUERADE
fi

# MASQUERADE Internet-bound LAN1 traffic (skip host subnet so sharding flows
# keep original 10.x source addresses).
sudo nsenter -t $PID_ROUTER -n bash -c '
  if ! iptables -t nat -C POSTROUTING -s 10.0.0.0/24 ! -d 192.168.100.0/24 -o eth0 -j MASQUERADE 2>/dev/null; then
    iptables -t nat -A POSTROUTING -s 10.0.0.0/24 ! -d 192.168.100.0/24 -o eth0 -j MASQUERADE
  fi
'

# Masquerade both LANs when traffic leaves through the dedicated Internet uplink (eth3).
sudo nsenter -t $PID_ROUTER -n bash -c '
  for SUBNET in 10.0.0.0/24 10.0.1.0/24; do
    if ! iptables -t nat -C POSTROUTING -s ${SUBNET} -o eth3 -j MASQUERADE 2>/dev/null; then
      iptables -t nat -A POSTROUTING -s ${SUBNET} -o eth3 -j MASQUERADE
    fi
  done
'

# Forward shard traffic between the WAN (eth0) and LAN (eth1) sides.
sudo nsenter -t $PID_ROUTER -n iptables -A FORWARD -i eth0 -o eth1 -j ACCEPT
sudo nsenter -t $PID_ROUTER -n iptables -A FORWARD -i eth1 -o eth0 -j ACCEPT

# Expose MongoDB shard members via 192.168.100.2:<port> using DNAT/SNAT so
# mongos/configsvr can reference the router address while traffic still lands
# on the 10.0.0.0/24 LAN.
#
# NOTE: Both shard containers listen on 27018 internally; we expose a unique
# WAN-side port per member to avoid collisions.

# mongodb-n1 (10.0.0.4:27018) exposed as 192.168.100.2:27018
sudo nsenter -t $PID_ROUTER -n iptables -t nat -A PREROUTING -i eth0 -p tcp \
  -d 192.168.100.2 --dport 27018 -j DNAT --to-destination 10.0.0.4:27018
sudo nsenter -t $PID_ROUTER -n iptables -t nat -A POSTROUTING -o eth1 -p tcp \
  -s 10.0.0.4 --sport 27018 -j SNAT --to-source 192.168.100.2:27018

# mongodb-n3 (10.0.0.6:27018) exposed as 192.168.100.2:27118
sudo nsenter -t $PID_ROUTER -n iptables -t nat -A PREROUTING -i eth0 -p tcp \
  -d 192.168.100.2 --dport 27118 -j DNAT --to-destination 10.0.0.6:27018
sudo nsenter -t $PID_ROUTER -n iptables -t nat -A POSTROUTING -o eth1 -p tcp \
  -s 10.0.0.6 --sport 27018 -j SNAT --to-source 192.168.100.2:27118


# Show OVS status
docker exec ovs ovs-vsctl show