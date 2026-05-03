#!/bin/bash

# ============================================================================
# Configure NAT router external (WAN) side
# Internet uplink setup is intentionally disabled in this topology.
# ============================================================================

set -euo pipefail

echo "Configuring NAT router WAN interface..."

# Get router container PID if not set already
PID_ROUTER=${PID_ROUTER:-$(docker inspect -f '{{.State.Pid}}' nat-router)}

# Set up the veth pair for WAN (veth5).
# NOTE: the dedicated internet uplink (veth6/eth3) is disabled below.
# NOTE: veth1-4 are reserved for build_network_1.sh (OVS bridge ports for LAN1).
#       veth21-24 are reserved for build_network_2.sh (OVS bridge ports for LAN2).
echo "Creating veth pair for router WAN..."
for IFACE in veth5 veth6 veth5-peer veth6-peer; do
  if ip link show "$IFACE" >/dev/null 2>&1; then
    sudo ip link del "$IFACE" >/dev/null 2>&1 || true
  fi
done

# Add the WAN link to the kernel.
sudo ip link add veth5 type veth peer name veth5-peer # router WAN side
# sudo ip link add veth6 type veth peer name veth6-peer # dedicated internet uplink

# Move the WAN peer to the NAT router namespace.
sudo ip link set veth5-peer netns $PID_ROUTER
# sudo ip link set veth6-peer netns $PID_ROUTER

# Configure WAN interface (eth0)
sudo nsenter -t $PID_ROUTER -n ip link set veth5-peer name eth0
sudo nsenter -t $PID_ROUTER -n ip link set eth0 address 00:00:00:00:00:BB  # router WAN MAC
sudo nsenter -t $PID_ROUTER -n ip link set eth0 up
sudo nsenter -t $PID_ROUTER -n ip addr add 192.168.100.2/24 dev eth0  # router’s WAN IP
# sudo nsenter -t $PID_ROUTER -n ip route add default via 192.168.100.1  # host as gateway

sudo ip link set veth5 up
sudo ip addr add 192.168.100.1/24 dev veth5  # host acts as router's gateway

# Configure dedicated uplink between host and NAT router for Internet access (eth3).
# Disabled because this setup does not require outbound Internet connectivity.
# INTERNET_LINK_HOST_IP=${INTERNET_LINK_HOST_IP:-172.20.0.1/30}
# INTERNET_LINK_ROUTER_IP=${INTERNET_LINK_ROUTER_IP:-172.20.0.2/30}
# INTERNET_LINK_GW=${INTERNET_LINK_GW:-172.20.0.1}
#
# sudo ip link set veth6 up
# sudo ip addr replace ${INTERNET_LINK_HOST_IP} dev veth6
# sudo nsenter -t $PID_ROUTER -n ip link set veth6-peer name eth3
# sudo nsenter -t $PID_ROUTER -n ip link set eth3 address 00:00:00:00:00:DD
# sudo nsenter -t $PID_ROUTER -n ip link set eth3 up
# sudo nsenter -t $PID_ROUTER -n ip addr replace ${INTERNET_LINK_ROUTER_IP} dev eth3
# sudo nsenter -t $PID_ROUTER -n ip route replace default via ${INTERNET_LINK_GW} dev eth3
# sudo nsenter -t $PID_ROUTER -n ip route replace 192.168.100.0/24 via 192.168.100.1 dev eth0

# Ensure IP forwarding stays enabled after reconfiguring interfaces.
sudo nsenter -t $PID_ROUTER -n bash -c "
  echo 1 > /proc/sys/net/ipv4/ip_forward
"

# Ensure the host can reach both lab subnets via the NAT router WAN interface
echo "Ensuring host routes to 10.0.0.0/24 and 10.0.1.0/24 via 192.168.100.2..."
if ! sudo ip route replace 10.0.0.0/24 via 192.168.100.2 dev veth5 >/dev/null 2>&1; then
  echo "WARNING: failed to program route to 10.0.0.0/24; check host networking." >&2
else
  ip route show 10.0.0.0/24
fi
if ! sudo ip route replace 10.0.1.0/24 via 192.168.100.2 dev veth5 >/dev/null 2>&1; then
  echo "WARNING: failed to program route to 10.0.1.0/24; check host networking." >&2
else
  ip route show 10.0.1.0/24
fi

# Enable IP forwarding + NAT on host for Internet access.
# Disabled because this setup does not require outbound Internet connectivity.
# sudo sysctl -w net.ipv4.ip_forward=1
# DEFAULT_UPLINK_IF=${DEFAULT_UPLINK_IF:-$(ip route get 8.8.8.8 2>/dev/null | awk '/dev/ {for (i=1;i<=NF;i++) if ($i=="dev") {print $(i+1); exit}}')}
# if [[ -z "${DEFAULT_UPLINK_IF}" ]]; then
#   DEFAULT_UPLINK_IF="enp0s3"
#   echo "WARNING: Unable to auto-detect uplink interface, defaulting to ${DEFAULT_UPLINK_IF}." >&2
# else
#   echo "Using ${DEFAULT_UPLINK_IF} as host uplink interface for MASQUERADE."
# fi
# if ! sudo iptables -t nat -C POSTROUTING -s 192.168.100.0/24 -o "${DEFAULT_UPLINK_IF}" -j MASQUERADE 2>/dev/null; then
#   sudo iptables -t nat -A POSTROUTING -s 192.168.100.0/24 -o "${DEFAULT_UPLINK_IF}" -j MASQUERADE
# fi
# if ! sudo iptables -t nat -C POSTROUTING -s 172.20.0.0/30 -o "${DEFAULT_UPLINK_IF}" -j MASQUERADE 2>/dev/null; then
#   sudo iptables -t nat -A POSTROUTING -s 172.20.0.0/30 -o "${DEFAULT_UPLINK_IF}" -j MASQUERADE
# fi
#
# # MASQUERADE Internet-bound LAN1 and LAN2 traffic
# sudo nsenter -t $PID_ROUTER -n bash -c '
#   if ! iptables -t nat -C POSTROUTING -s 10.0.0.0/24 ! -d 192.168.100.0/24 -o eth0 -j MASQUERADE 2>/dev/null; then
#     iptables -t nat -A POSTROUTING -s 10.0.0.0/24 ! -d 192.168.100.0/24 -o eth0 -j MASQUERADE
#   fi
#   if ! iptables -t nat -C POSTROUTING -s 10.0.1.0/24 ! -d 192.168.100.0/24 -o eth0 -j MASQUERADE 2>/dev/null; then
#     iptables -t nat -A POSTROUTING -s 10.0.1.0/24 ! -d 192.168.100.0/24 -o eth0 -j MASQUERADE
#   fi
# '
#
# # Masquerade both LANs when traffic leaves through the dedicated Internet uplink (eth3).
# sudo nsenter -t $PID_ROUTER -n bash -c '
#   for SUBNET in 10.0.0.0/24 10.0.1.0/24; do
#     if ! iptables -t nat -C POSTROUTING -s ${SUBNET} -o eth3 -j MASQUERADE 2>/dev/null; then
#       iptables -t nat -A POSTROUTING -s ${SUBNET} -o eth3 -j MASQUERADE
#     fi
#   done
# '

# Forward traffic between all interface pairs (WAN↔LAN1, WAN↔LAN2, LAN1↔LAN2)
sudo nsenter -t $PID_ROUTER -n iptables -A FORWARD -i eth0 -o eth1 -j ACCEPT
sudo nsenter -t $PID_ROUTER -n iptables -A FORWARD -i eth1 -o eth0 -j ACCEPT
sudo nsenter -t $PID_ROUTER -n iptables -A FORWARD -i eth0 -o eth2 -j ACCEPT
sudo nsenter -t $PID_ROUTER -n iptables -A FORWARD -i eth2 -o eth0 -j ACCEPT
# Cross-LAN forwarding (needed for inter-LAN connectivity)
sudo nsenter -t $PID_ROUTER -n iptables -A FORWARD -i eth1 -o eth2 -j ACCEPT
sudo nsenter -t $PID_ROUTER -n iptables -A FORWARD -i eth2 -o eth1 -j ACCEPT

# Expose MongoDB members via DNAT/SNAT
# edge_storage_server_n1 (10.0.0.4:27018) exposed as 192.168.100.2:27018
sudo nsenter -t $PID_ROUTER -n iptables -t nat -A PREROUTING -i eth0 -p tcp \
  -d 192.168.100.2 --dport 27018 -j DNAT --to-destination 10.0.0.4:27018
sudo nsenter -t $PID_ROUTER -n iptables -t nat -A POSTROUTING -o eth1 -p tcp \
  -s 10.0.0.4 --sport 27018 -j SNAT --to-source 192.168.100.2:27018

# NETWORK 2 MongoDB 
# ------------------------
# edge_storage_server_n2 (10.0.1.4:27018) exposed as 192.168.100.2:27118
sudo nsenter -t $PID_ROUTER -n iptables -t nat -A PREROUTING -i eth0 -p tcp \
  -d 192.168.100.2 --dport 27118 -j DNAT --to-destination 10.0.1.4:27018
sudo nsenter -t $PID_ROUTER -n iptables -t nat -A POSTROUTING -o eth2 -p tcp \
  -s 10.0.1.4 --sport 27018 -j SNAT --to-source 192.168.100.2:27118

echo "============================================================================"
echo "NAT router configuration complete."
echo "============================================================================"

# ============================================================================
# WAN emulation — apply tc netem on inter-LAN egress (eth1, eth2).
# Reads WAN_RTT_MS / WAN_JITTER_MS / WAN_LOSS_PCT / WAN_RATE_KBIT from the
# environment (sourced from scripts/wan.env in build_network_setup.sh).
# No-op when all knobs are 0.
# ============================================================================
SCRIPT_DIR_BR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_ROUTER="${PID_ROUTER}" bash "${SCRIPT_DIR_BR}/inject_wan_latency.sh"
