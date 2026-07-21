#!/bin/bash

# ============================================================================
# Create N lightweight namespace-based test clients and attach them to a LAN.
#
# Each client is a Linux network namespace with a unique IP, MAC, and a
# dedicated veth pair connected to the OVS bridge — no container image needed.
#
# Veth ranges reserved for test clients (must not overlap with service nodes):
#   LAN 1 → veth150–veth245  (service nodes use 100–149)
#   LAN 2 → veth300–veth395  (service nodes use 250–299)
#
# This separation prevents the SDN controller's find_free_veth_index() from
# exhausting its range when test clients are active simultaneously.
# ============================================================================

set -euo pipefail

readonly SCRIPT_NAME="$(basename "$0")"
readonly OVS_CONTAINER="ovs"

declare -A LAN_BRIDGE=(   [1]="ovs-br0"  [2]="ovs-br1"  )
declare -A LAN_SUBNET=(   [1]="10.0.0"   [2]="10.0.1"   )
declare -A LAN_GATEWAY=(  [1]="10.0.0.1" [2]="10.0.1.1" )
# Test client veth ranges — separate from add_network_node.sh ranges (100–149, 250–299)
# Expanded from 50 to 96 slots per LAN for Pilot B (96 clients/LAN).
declare -A VETH_RANGE_START=( [1]=150 [2]=300 )
declare -A VETH_RANGE_END=(   [1]=245 [2]=395 )
# .1 = gateway, .252 = VIP_DATA recovery, .253 = VIP_SERVER, .254 = VIP_DATA_N{lan}
declare -A RESERVED_SUFFIX=( [1]="1 252 253 254" [2]="1 252 253 254" )

LAN=""
COUNT=""
PREFIX="test_client"
PID_OVS=""

usage() {
	cat <<EOF
Usage: $SCRIPT_NAME --lan <1|2> --count <N> [OPTIONS]

Create N namespace-based test clients and attach them to an OVS LAN.
Each client gets its own Linux network namespace, IP, MAC, and veth pair.

Required:
  --lan <1|2>        Target LAN
  --count <N>        Number of clients to create

Optional:
  --prefix <name>    Namespace name prefix (default: test_client)
  -h, --help         Show this help

Examples:
  $SCRIPT_NAME --lan 1 --count 4
  $SCRIPT_NAME --lan 2 --count 2 --prefix bench_client
EOF
	exit 0
}

die() {
	echo "ERROR: $*" >&2
	exit 1
}

ensure_ovs_namespace() {
	PID_OVS=$(docker inspect -f '{{.State.Pid}}' "$OVS_CONTAINER")
	sudo mkdir -p /var/run/netns
	sudo ln -sf "/proc/${PID_OVS}/ns/net" /var/run/netns/ovs
}

validate_requirements() {
	[[ -n "$LAN" ]]   || die "--lan is required."
	[[ -n "$COUNT" ]] || die "--count is required."
	[[ "$LAN" == "1" || "$LAN" == "2" ]] || die "--lan must be 1 or 2."
	[[ "$COUNT" =~ ^[1-9][0-9]*$ ]] || die "--count must be a positive integer."

	docker inspect -f '{{.State.Pid}}' "$OVS_CONTAINER" >/dev/null 2>&1 \
		|| die "Container '$OVS_CONTAINER' is not running."
	docker exec "$OVS_CONTAINER" ovs-vsctl br-exists "${LAN_BRIDGE[$LAN]}" \
		|| die "OVS bridge '${LAN_BRIDGE[$LAN]}' does not exist."
}

# Collect all IPs already in use on the target LAN subnet.
# Scans both running Docker containers and existing named namespaces.
collect_used_ips() {
	local subnet="${LAN_SUBNET[$LAN]}"
	local used=()

	for suffix in ${RESERVED_SUFFIX[$LAN]}; do
		used+=("${subnet}.${suffix}")
	done

	# Scan running containers
	local cid
	for cid in $(docker ps -q 2>/dev/null); do
		local pid
		pid=$(docker inspect -f '{{.State.Pid}}' "$cid" 2>/dev/null) || continue
		[[ "$pid" =~ ^[0-9]+$ ]] || continue
		local addrs
		addrs=$(sudo nsenter -t "$pid" -n ip -4 -o addr show 2>/dev/null \
			| grep -oE "${subnet//./\\.}\.[0-9]+" || true)
		local addr
		for addr in $addrs; do
			used+=("$addr")
		done
	done

	# Scan existing named namespaces (test clients from a prior invocation)
	local ns
	while read -r ns _rest; do
		local addrs
		addrs=$(sudo ip -n "$ns" -4 -o addr show 2>/dev/null \
			| grep -oE "${subnet//./\\.}\.[0-9]+" || true)
		local addr
		for addr in $addrs; do
			used+=("$addr")
		done
	done < <(ip netns list 2>/dev/null || true)

	printf '%s\n' "${used[@]}" | sort -u
}

auto_assign_ip() {
	local subnet="${LAN_SUBNET[$LAN]}"
	local used
	used=$(collect_used_ips)

	local host
	# Start from .56 — octets .2–.55 are reserved for dynamic service nodes
	# added via add_network_node.sh / add_network_storage_node.sh.
	# Expanded from .56-.105 to .56-.151 for Pilot B (96 clients/LAN).
	for host in $(seq 56 151); do
		local candidate="${subnet}.${host}"
		if ! echo "$used" | grep -qxF "$candidate"; then
			echo "$candidate"
			return 0
		fi
	done

	die "No free IP address available in ${subnet}.56-151 (test client range)."}
}

auto_generate_mac() {
	local ip="$1"
	local host_octet="${ip##*.}"
	printf '00:00:00:00:%02x:%02x' "$LAN" "$host_octet"
}

find_free_veth_index() {
	local start="${VETH_RANGE_START[$LAN]}"
	local end="${VETH_RANGE_END[$LAN]}"
	local idx

	for idx in $(seq "$start" "$end"); do
		if ! ip link show "veth${idx}" >/dev/null 2>&1 \
			&& ! sudo nsenter -t "$PID_OVS" -n ip link show "veth${idx}" >/dev/null 2>&1; then
			echo "$idx"
			return 0
		fi
	done

	die "No free veth index in range ${start}-${end} for LAN ${LAN}."
}

create_client() {
	local ns_name="$1"
	local bridge="${LAN_BRIDGE[$LAN]}"
	local gateway="${LAN_GATEWAY[$LAN]}"

	# Skip if the namespace already exists
	if ip netns list 2>/dev/null | awk '{print $1}' | grep -qxF "$ns_name"; then
		echo "  Skipping '${ns_name}' — namespace already exists."
		return 0
	fi

	local ip
	ip=$(auto_assign_ip)
	local mac
	mac=$(auto_generate_mac "$ip")
	local veth_idx
	veth_idx=$(find_free_veth_index)

	local ovs_veth="veth${veth_idx}"
	local ns_veth="veth${veth_idx}-peer"

	echo "  Creating '${ns_name}' — IP=${ip} MAC=${mac} veth=${ovs_veth}"

	# Create the namespace and bring up loopback
	sudo ip netns add "$ns_name"
	sudo ip netns exec "$ns_name" ip link set lo up

	# Create veth pair on the host
	sudo ip link add "$ovs_veth" type veth peer name "$ns_veth"

	# Move OVS-side end into OVS namespace and attach to bridge
	sudo ip link set "$ovs_veth" netns ovs
	docker exec "$OVS_CONTAINER" ip link set "$ovs_veth" up
	docker exec "$OVS_CONTAINER" ovs-vsctl add-port "$bridge" "$ovs_veth"

	# Move peer into the namespace, configure IP/MAC/routing
	sudo ip link set "$ns_veth" netns "$ns_name"
	sudo ip netns exec "$ns_name" ip link set "$ns_veth" name eth0
	sudo ip netns exec "$ns_name" ip link set eth0 address "$mac"
	sudo ip netns exec "$ns_name" ip link set eth0 up
	sudo ip netns exec "$ns_name" ip addr add "${ip}/24" dev eth0
	sudo ip netns exec "$ns_name" ip route add default via "$gateway"

	# Machine-readable result — one line per client
	echo "RESULT_NS=${ns_name} RESULT_IP=${ip} RESULT_MAC=${mac}"
}

main() {
	validate_requirements
	ensure_ovs_namespace

	echo "============================================================================"
	echo "Creating ${COUNT} test client(s) on LAN ${LAN} (prefix: ${PREFIX})"
	echo "============================================================================"

	local i
	for i in $(seq 1 "$COUNT"); do
		create_client "${PREFIX}_${i}"
	done

	echo "============================================================================"
	echo "Done. Created ${COUNT} client(s) on LAN ${LAN}."
	echo "To send requests: sudo ip netns exec ${PREFIX}_1 curl http://${LAN_GATEWAY[$LAN]%.*}.100:80/"
	echo "============================================================================"
}

while [[ $# -gt 0 ]]; do
	case "$1" in
		--lan)
			LAN="$2"
			shift 2
			;;
		--count)
			COUNT="$2"
			shift 2
			;;
		--prefix)
			PREFIX="$2"
			shift 2
			;;
		-h|--help)
			usage
			;;
		*)
			die "Unknown option: $1"
			;;
	esac
done

main
