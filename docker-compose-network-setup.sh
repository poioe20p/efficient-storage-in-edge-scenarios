#!/bin/bash

# ============================================================================
# Docker Compose Network Setup Helper
# ============================================================================
#
# This script configures the network plumbing (veth pairs, namespaces, routes,
# and iptables rules) for containers managed by docker-compose.
#
# It performs the same network setup as build_network_1.sh and build_network_2.sh
# but works with containers that are already running via docker-compose.
#
# Usage:
#   ./docker-compose-network-setup.sh
#
# Prerequisites:
#   - docker-compose up -d must be run first
#   - All containers should be running
#   - User needs sudo privileges for network operations
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
# Configuration Variables
# ============================================================================
MONGO_HOST_IP=192.168.100.4
MONGO_RS_1_HOST_IP=10.0.0.4
MONGO_RS_2_HOST_IP=10.0.1.4
INTERNET_LINK_HOST_IP=${INTERNET_LINK_HOST_IP:-172.20.0.1/30}
INTERNET_LINK_ROUTER_IP=${INTERNET_LINK_ROUTER_IP:-172.20.0.2/30}
INTERNET_LINK_GW=${INTERNET_LINK_GW:-172.20.0.1}

# ============================================================================
# Step 0: Verify containers are running
# ============================================================================
log "Verifying required containers are running..."

REQUIRED_CONTAINERS=(ovs nat-router container1 container2 container3 container4 container5 mongodb-n1 mongodb-n2)

for container in "${REQUIRED_CONTAINERS[@]}"; do
    if ! docker ps --format '{{.Names}}' | grep -Fxq "$container"; then
        error "Container '$container' is not running. Please start it with docker-compose first."
        exit 1
    fi
done

log "All required containers are running."

# ============================================================================
# Step 1: Ensure host interface has required IP
# ============================================================================
log "Ensuring enp0s3 has IP 192.168.100.4/24..."
if ! ip link show enp0s3 &>/dev/null; then
    warn "Network interface enp0s3 not found. Skipping host IP assignment."
else
    if ip addr show dev enp0s3 | grep -q "192.168.100.4/24"; then
        log "enp0s3 already has 192.168.100.4/24 assigned."
    else
        sudo ip addr add 192.168.100.4/24 dev enp0s3 || warn "Failed to assign IP to enp0s3"
        log "Assigned 192.168.100.4/24 to enp0s3."
    fi
fi

# ============================================================================
# Step 2: Ensure IPTables FORWARD policy is ACCEPT
# ============================================================================
log "Verifying IPTables FORWARD policy..."
FORWARD_POLICY=$(sudo iptables -L FORWARD | grep "Chain FORWARD" | awk '{print $4}')
if [[ "$FORWARD_POLICY" != "ACCEPT" ]]; then
    log "FORWARD policy is not ACCEPT. Changing it to ACCEPT..."
    sudo iptables --policy FORWARD ACCEPT
fi

# ============================================================================
# Step 3: Setup Network 1 (ovs-br0, ovs-br2)
# ============================================================================
log "====================================================================="
log "Setting up Network 1 (ovs-br0, ovs-br2)..."
log "====================================================================="

# Create OVS bridges
log "Creating OVS bridges..."
docker exec ovs ovs-vsctl --may-exist add-br ovs-br0
docker exec ovs ovs-vsctl --may-exist add-br ovs-br2

# Clean up old veth pairs if they exist
log "Cleaning up old veth pairs..."
for IFACE in veth1 veth2 veth3 veth4 veth5 veth6 veth7 veth8 \
             veth1-peer veth2-peer veth3-peer veth4-peer veth5-peer veth6-peer veth7-peer veth8-peer; do
    if ip link show "$IFACE" >/dev/null 2>&1; then
        sudo ip link del "$IFACE" >/dev/null 2>&1 || true
    fi
done

# Create veth pairs for Network 1
log "Creating veth pairs for Network 1..."
sudo ip link add veth1 type veth peer name veth1-peer # container1
sudo ip link add veth2 type veth peer name veth2-peer # container2
sudo ip link add veth3 type veth peer name veth3-peer # router LAN side
sudo ip link add veth4 type veth peer name veth4-peer # router WAN side
sudo ip link add veth5 type veth peer name veth5-peer # mongodb-n1
sudo ip link add veth6 type veth peer name veth6-peer # router internet uplink
sudo ip link add veth7 type veth peer name veth7-peer # container5
sudo ip link add veth8 type veth peer name veth8-peer # ovs-br0 <-> ovs-br2 patch

# Move veth interfaces into OVS namespace
log "Moving veth interfaces into OVS container namespace..."
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

# Bring up interfaces and attach to OVS bridges
log "Configuring OVS interfaces..."
docker exec ovs ip link set veth1 up
docker exec ovs ip link set veth2 up
docker exec ovs ip link set veth3 up
docker exec ovs ip link set veth5 up
docker exec ovs ip link set veth7 up
docker exec ovs ip link set veth8 up
docker exec ovs ip link set veth8-peer up

docker exec ovs ovs-vsctl --may-exist add-port ovs-br0 veth1
docker exec ovs ovs-vsctl --may-exist add-port ovs-br0 veth2
docker exec ovs ovs-vsctl --may-exist add-port ovs-br0 veth3
docker exec ovs ovs-vsctl --may-exist add-port ovs-br0 veth5
docker exec ovs ovs-vsctl --may-exist add-port ovs-br2 veth7
docker exec ovs ovs-vsctl --may-exist add-port ovs-br0 veth8
docker exec ovs ovs-vsctl --may-exist add-port ovs-br2 veth8-peer

# Get container PIDs
PID1=$(docker inspect -f '{{.State.Pid}}' container1)
PID2=$(docker inspect -f '{{.State.Pid}}' container2)
PID5=$(docker inspect -f '{{.State.Pid}}' container5)
PID_ROUTER=$(docker inspect -f '{{.State.Pid}}' nat-router)
PID_MONGO_N1=$(docker inspect -f '{{.State.Pid}}' mongodb-n1)

# Move peer interfaces into containers
log "Moving veth peers into container namespaces..."
sudo ip link set veth1-peer netns $PID1
sudo ip link set veth2-peer netns $PID2
sudo ip link set veth7-peer netns $PID5
sudo ip link set veth3-peer netns $PID_ROUTER
sudo ip link set veth4-peer netns $PID_ROUTER
sudo ip link set veth5-peer netns $PID_MONGO_N1
sudo ip link set veth6-peer netns $PID_ROUTER

# Configure container1
log "Configuring container1 network..."
sudo nsenter -t $PID1 -n ip link set veth1-peer name eth0
sudo nsenter -t $PID1 -n ip link set eth0 address 00:00:00:00:00:02
sudo nsenter -t $PID1 -n ip link set eth0 up
sudo nsenter -t $PID1 -n ip addr add 10.0.0.2/24 dev eth0
sudo nsenter -t $PID1 -n ip route add default via 10.0.0.1

# Configure container2
log "Configuring container2 network..."
sudo nsenter -t $PID2 -n ip link set veth2-peer name eth0
sudo nsenter -t $PID2 -n ip link set eth0 address 00:00:00:00:00:03
sudo nsenter -t $PID2 -n ip link set eth0 up
sudo nsenter -t $PID2 -n ip addr add 10.0.0.3/24 dev eth0
sudo nsenter -t $PID2 -n ip route add default via 10.0.0.1

# Configure container5
log "Configuring container5 network..."
sudo nsenter -t $PID5 -n ip link set veth7-peer name eth0
sudo nsenter -t $PID5 -n ip link set eth0 address 00:00:00:00:00:08
sudo nsenter -t $PID5 -n ip link set eth0 up
sudo nsenter -t $PID5 -n ip addr add 10.0.0.5/24 dev eth0
sudo nsenter -t $PID5 -n ip route add default via 10.0.0.1

# Configure mongodb-n1
log "Configuring mongodb-n1 network..."
sudo nsenter -t $PID_MONGO_N1 -n ip link set veth5-peer name eth0
sudo nsenter -t $PID_MONGO_N1 -n ip link set eth0 address 00:00:00:00:00:04
sudo nsenter -t $PID_MONGO_N1 -n ip link set eth0 up
sudo nsenter -t $PID_MONGO_N1 -n ip addr add 10.0.0.4/24 dev eth0
sudo nsenter -t $PID_MONGO_N1 -n ip route add default via 10.0.0.1

# Configure NAT router LAN side (eth1)
log "Configuring NAT router LAN interface (eth1)..."
sudo nsenter -t $PID_ROUTER -n ip link set veth3-peer name eth1
sudo nsenter -t $PID_ROUTER -n ip link set eth1 address 00:00:00:00:00:AA
sudo nsenter -t $PID_ROUTER -n ip link set eth1 up
sudo nsenter -t $PID_ROUTER -n ip addr add 10.0.0.1/24 dev eth1

# Enable IP forwarding in router
sudo nsenter -t $PID_ROUTER -n bash -c "echo 1 > /proc/sys/net/ipv4/ip_forward"

# Configure NAT router WAN side (eth0)
log "Configuring NAT router WAN interface (eth0)..."
sudo nsenter -t $PID_ROUTER -n ip link set veth4-peer name eth0
sudo nsenter -t $PID_ROUTER -n ip link set eth0 address 00:00:00:00:00:BB
sudo nsenter -t $PID_ROUTER -n ip link set eth0 up
sudo nsenter -t $PID_ROUTER -n ip addr add 192.168.100.2/24 dev eth0
sudo nsenter -t $PID_ROUTER -n ip route add default via 192.168.100.1

# Configure host side of router WAN connection
sudo ip link set veth4 up
sudo ip addr add 192.168.100.1/24 dev veth4

# Configure dedicated Internet uplink
log "Configuring dedicated Internet uplink..."
sudo ip link set veth6 up
sudo ip addr replace ${INTERNET_LINK_HOST_IP} dev veth6
sudo nsenter -t $PID_ROUTER -n ip link set veth6-peer name eth3
sudo nsenter -t $PID_ROUTER -n ip link set eth3 address 00:00:00:00:00:DD
sudo nsenter -t $PID_ROUTER -n ip link set eth3 up
sudo nsenter -t $PID_ROUTER -n ip addr replace ${INTERNET_LINK_ROUTER_IP} dev eth3
sudo nsenter -t $PID_ROUTER -n ip route replace default via ${INTERNET_LINK_GW} dev eth3
sudo nsenter -t $PID_ROUTER -n ip route replace 192.168.100.0/24 via 192.168.100.1 dev eth0

# Add host routes
log "Adding host routes for Network 1..."
if ! sudo ip route replace 10.0.0.0/24 via 192.168.100.2 dev veth4 >/dev/null 2>&1; then
    warn "Failed to program route to 10.0.0.0/24"
fi

# Enable IP forwarding on host
sudo sysctl -w net.ipv4.ip_forward=1

# Setup NAT on host
DEFAULT_UPLINK_IF=${DEFAULT_UPLINK_IF:-$(ip route get 8.8.8.8 2>/dev/null | awk '/dev/ {for (i=1;i<=NF;i++) if ($i=="dev") {print $(i+1); exit}}')}
if [[ -z "${DEFAULT_UPLINK_IF}" ]]; then
    DEFAULT_UPLINK_IF="enp0s3"
    warn "Unable to auto-detect uplink interface, defaulting to ${DEFAULT_UPLINK_IF}."
fi

log "Using ${DEFAULT_UPLINK_IF} as host uplink interface for MASQUERADE."
if ! sudo iptables -t nat -C POSTROUTING -s 192.168.100.0/24 -o "${DEFAULT_UPLINK_IF}" -j MASQUERADE 2>/dev/null; then
    sudo iptables -t nat -A POSTROUTING -s 192.168.100.0/24 -o "${DEFAULT_UPLINK_IF}" -j MASQUERADE
fi
if ! sudo iptables -t nat -C POSTROUTING -s 172.20.0.0/30 -o "${DEFAULT_UPLINK_IF}" -j MASQUERADE 2>/dev/null; then
    sudo iptables -t nat -A POSTROUTING -s 172.20.0.0/30 -o "${DEFAULT_UPLINK_IF}" -j MASQUERADE
fi

# Setup router NAT rules for Network 1
log "Setting up router NAT rules for Network 1..."
sudo nsenter -t $PID_ROUTER -n bash -c '
    if ! iptables -t nat -C POSTROUTING -s 10.0.0.0/24 ! -d 192.168.100.0/24 -o eth0 -j MASQUERADE 2>/dev/null; then
        iptables -t nat -A POSTROUTING -s 10.0.0.0/24 ! -d 192.168.100.0/24 -o eth0 -j MASQUERADE
    fi
'

# Masquerade both LANs through Internet uplink
sudo nsenter -t $PID_ROUTER -n bash -c '
    for SUBNET in 10.0.0.0/24 10.0.1.0/24; do
        if ! iptables -t nat -C POSTROUTING -s ${SUBNET} -o eth3 -j MASQUERADE 2>/dev/null; then
            iptables -t nat -A POSTROUTING -s ${SUBNET} -o eth3 -j MASQUERADE
        fi
    done
'

# Setup forwarding rules
sudo nsenter -t $PID_ROUTER -n iptables -A FORWARD -i eth0 -o eth1 -j ACCEPT 2>/dev/null || true
sudo nsenter -t $PID_ROUTER -n iptables -A FORWARD -i eth1 -o eth0 -j ACCEPT 2>/dev/null || true

# Expose mongodb-n1 via DNAT/SNAT
log "Setting up DNAT/SNAT for mongodb-n1..."
sudo nsenter -t $PID_ROUTER -n iptables -t nat -A PREROUTING -i eth0 -p tcp \
    -d 192.168.100.2 --dport 27018 -j DNAT --to-destination 10.0.0.4:27018 2>/dev/null || true
sudo nsenter -t $PID_ROUTER -n iptables -t nat -A POSTROUTING -o eth1 -p tcp \
    -s 10.0.0.4 --sport 27018 -j SNAT --to-source 192.168.100.2:27018 2>/dev/null || true

log "Network 1 setup complete."

# ============================================================================
# Step 4: Setup Network 2 (ovs-br1)
# ============================================================================
log "====================================================================="
log "Setting up Network 2 (ovs-br1)..."
log "====================================================================="

# Create OVS bridge
log "Creating OVS bridge ovs-br1..."
docker exec ovs ovs-vsctl --may-exist add-br ovs-br1

# Clean up old veth pairs if they exist
log "Cleaning up old veth pairs for Network 2..."
for IFACE in veth10 veth11 veth12 veth13 veth10-peer veth11-peer veth12-peer veth13-peer; do
    if ip link show "$IFACE" >/dev/null 2>&1; then
        sudo ip link del "$IFACE" >/dev/null 2>&1 || true
    fi
done

# Create veth pairs for Network 2
log "Creating veth pairs for Network 2..."
sudo ip link add veth10 type veth peer name veth10-peer # container3
sudo ip link add veth11 type veth peer name veth11-peer # container4
sudo ip link add veth12 type veth peer name veth12-peer # router LAN side
sudo ip link add veth13 type veth peer name veth13-peer # mongodb-n2

# Move veth interfaces into OVS namespace
log "Moving veth interfaces into OVS container namespace..."
sudo ip link set veth10 netns ovs
sudo ip link set veth11 netns ovs
sudo ip link set veth12 netns ovs
sudo ip link set veth13 netns ovs

# Bring up interfaces and attach to OVS bridge
log "Configuring OVS interfaces for Network 2..."
docker exec ovs ip link set veth10 up
docker exec ovs ip link set veth11 up
docker exec ovs ip link set veth12 up
docker exec ovs ip link set veth13 up

docker exec ovs ovs-vsctl --may-exist add-port ovs-br1 veth10
docker exec ovs ovs-vsctl --may-exist add-port ovs-br1 veth11
docker exec ovs ovs-vsctl --may-exist add-port ovs-br1 veth12
docker exec ovs ovs-vsctl --may-exist add-port ovs-br1 veth13

# Get container PIDs
PID3=$(docker inspect -f '{{.State.Pid}}' container3)
PID4=$(docker inspect -f '{{.State.Pid}}' container4)
PID_MONGO_N2=$(docker inspect -f '{{.State.Pid}}' mongodb-n2)

# Move peer interfaces into containers
log "Moving veth peers into container namespaces for Network 2..."
sudo ip link set veth10-peer netns $PID3
sudo ip link set veth11-peer netns $PID4
sudo ip link set veth12-peer netns $PID_ROUTER
sudo ip link set veth13-peer netns $PID_MONGO_N2

# Configure container3
log "Configuring container3 network..."
sudo nsenter -t $PID3 -n ip link set veth10-peer name eth0
sudo nsenter -t $PID3 -n ip link set eth0 address 00:00:00:00:00:05
sudo nsenter -t $PID3 -n ip link set eth0 up
sudo nsenter -t $PID3 -n ip addr add 10.0.1.2/24 dev eth0
sudo nsenter -t $PID3 -n ip route add default via 10.0.1.1

# Configure container4
log "Configuring container4 network..."
sudo nsenter -t $PID4 -n ip link set veth11-peer name eth0
sudo nsenter -t $PID4 -n ip link set eth0 address 00:00:00:00:00:06
sudo nsenter -t $PID4 -n ip link set eth0 up
sudo nsenter -t $PID4 -n ip addr add 10.0.1.3/24 dev eth0
sudo nsenter -t $PID4 -n ip route add default via 10.0.1.1

# Configure mongodb-n2
log "Configuring mongodb-n2 network..."
sudo nsenter -t $PID_MONGO_N2 -n ip link set veth13-peer name eth0
sudo nsenter -t $PID_MONGO_N2 -n ip link set eth0 address 00:00:00:00:00:07
sudo nsenter -t $PID_MONGO_N2 -n ip link set eth0 up
sudo nsenter -t $PID_MONGO_N2 -n ip addr add 10.0.1.4/24 dev eth0
sudo nsenter -t $PID_MONGO_N2 -n ip route add default via 10.0.1.1

# Configure NAT router LAN side for Network 2 (eth2)
log "Configuring NAT router LAN interface (eth2) for Network 2..."
sudo nsenter -t $PID_ROUTER -n ip link set veth12-peer name eth2
sudo nsenter -t $PID_ROUTER -n ip link set eth2 address 00:00:00:00:00:CC
sudo nsenter -t $PID_ROUTER -n ip link set eth2 up
sudo nsenter -t $PID_ROUTER -n ip addr add 10.0.1.1/24 dev eth2

# Add host routes for Network 2
log "Adding host routes for Network 2..."
if ! sudo ip route replace 10.0.1.0/24 via 192.168.100.2 dev veth4 >/dev/null 2>&1; then
    warn "Failed to program route to 10.0.1.0/24"
fi

# Setup router NAT rules for Network 2
log "Setting up router NAT rules for Network 2..."
sudo nsenter -t $PID_ROUTER -n bash -c '
    if ! iptables -t nat -C POSTROUTING -s 10.0.1.0/24 ! -d 192.168.100.0/24 -o eth0 -j MASQUERADE 2>/dev/null; then
        iptables -t nat -A POSTROUTING -s 10.0.1.0/24 ! -d 192.168.100.0/24 -o eth0 -j MASQUERADE
    fi
'

# Setup forwarding rules for Network 2
sudo nsenter -t $PID_ROUTER -n iptables -A FORWARD -i eth0 -o eth2 -j ACCEPT 2>/dev/null || true
sudo nsenter -t $PID_ROUTER -n iptables -A FORWARD -i eth2 -o eth0 -j ACCEPT 2>/dev/null || true

# Expose mongodb-n2 via DNAT/SNAT
log "Setting up DNAT/SNAT for mongodb-n2..."
sudo nsenter -t $PID_ROUTER -n iptables -t nat -A PREROUTING -i eth0 -p tcp \
    -d 192.168.100.2 --dport 27118 -j DNAT --to-destination 10.0.1.4:27018 2>/dev/null || true
sudo nsenter -t $PID_ROUTER -n iptables -t nat -A POSTROUTING -o eth2 -p tcp \
    -s 10.0.1.4 --sport 27018 -j SNAT --to-source 192.168.100.2:27118 2>/dev/null || true

log "Network 2 setup complete."

# ============================================================================
# Step 5: Show OVS status
# ============================================================================
log "====================================================================="
log "Displaying OVS configuration..."
log "====================================================================="
docker exec ovs ovs-vsctl show

log "====================================================================="
log "Network setup completed successfully!"
log "====================================================================="
log ""
log "Next steps:"
log "  1. Initialize MongoDB replica sets using the build_setup.sh initialization logic"
log "  2. Point OVS switches to SDN controllers:"
log "     docker exec ovs ovs-vsctl set-controller ovs-br0 tcp:127.0.0.1:6653"
log "     docker exec ovs ovs-vsctl set-controller ovs-br1 tcp:127.0.0.1:6654"
log "     docker exec ovs ovs-vsctl set-controller ovs-br2 tcp:127.0.0.1:6653"
log "  3. Run connectivity tests: ./source/scripts/test_connectivity.sh"
