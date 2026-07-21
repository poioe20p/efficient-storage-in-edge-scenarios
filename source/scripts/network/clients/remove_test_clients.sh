#!/bin/bash

# ============================================================================
# Remove namespace-based test clients created by create_test_clients.sh.
#
# For each namespace, this script:
#   1. Identifies the associated OVS veth by probing the kernel peer ifindex
#   2. Detaches the veth from the OVS bridge and deletes the pair
#   3. Flushes any stale OVS flow rules referencing the client MAC
#   4. Deletes the network namespace
# ============================================================================

set -euo pipefail

readonly SCRIPT_NAME="$(basename "$0")"
readonly OVS_CONTAINER="ovs"

declare -A LAN_BRIDGE=(     [1]="ovs-br0"  [2]="ovs-br1"  )
# Test client veth range — must match create_test_clients.sh
# Expanded from 50 to 96 slots per LAN for Pilot B (96 clients/LAN).
# LAN2 shifted to 300-395 to avoid collision with service nodes (250-299).
declare -A VETH_RANGE_START=( [1]=150 [2]=300 )
declare -A VETH_RANGE_END=(   [1]=245 [2]=395 )

LAN=""
PREFIX="test_client"
NS_SINGLE=""
PID_OVS=""

usage() {
	cat <<EOF
Usage: $SCRIPT_NAME --lan <1|2> [OPTIONS]

Remove namespace-based test clients created by create_test_clients.sh.

Required:
  --lan <1|2>        Target LAN (needed to identify the OVS bridge)

Optional:
  --prefix <name>    Remove all namespaces with this prefix (default: test_client)
  --name <ns_name>   Remove a single namespace by name
  -h, --help         Show this help

Examples:
  $SCRIPT_NAME --lan 1
  $SCRIPT_NAME --lan 2 --prefix bench_client
  $SCRIPT_NAME --lan 1 --name test_client_3
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
	[[ -n "$LAN" ]] || die "--lan is required."
	[[ "$LAN" == "1" || "$LAN" == "2" ]] || die "--lan must be 1 or 2."

	docker inspect -f '{{.State.Pid}}' "$OVS_CONTAINER" >/dev/null 2>&1 \
		|| die "Container '$OVS_CONTAINER' is not running."
}

# Find which veth in the test client range is the peer of eth0 inside NS.
# Uses the kernel's ifindex encoded in the "eth0@if<N>" notation to match
# against the OVS-side veth ifindex. Prints the veth index on success.
find_veth_for_namespace() {
	local ns="$1"
	local start="${VETH_RANGE_START[$LAN]}"
	local end="${VETH_RANGE_END[$LAN]}"

	# "eth0@if7" → peer (OVS-side) has ifindex 7 inside the OVS namespace
	local peer_ifindex
	peer_ifindex=$(sudo ip -n "$ns" -o link show eth0 2>/dev/null \
		| grep -oE 'eth0@if[0-9]+' | grep -oE '[0-9]+$' || true)

	[[ -n "$peer_ifindex" ]] || return 1

	local idx
	for idx in $(seq "$start" "$end"); do
		local ifidx
		# "7: veth50@if6:" → field 1 before the first colon is the ifindex
		ifidx=$(docker exec "$OVS_CONTAINER" ip -o link show "veth${idx}" 2>/dev/null \
			| awk -F: '{print $1}' || true)
		[[ -n "$ifidx" ]] || continue
		if [[ "$ifidx" == "$peer_ifindex" ]]; then
			echo "$idx"
			return 0
		fi
	done

	return 1
}

remove_client() {
	local ns="$1"
	local bridge="${LAN_BRIDGE[$LAN]}"

	echo "  Removing '${ns}'..."

	# Get the MAC before teardown so we can flush flow rules
	local mac
	mac=$(sudo ip -n "$ns" -o link show eth0 2>/dev/null \
		| grep -oE '([0-9a-f]{2}:){5}[0-9a-f]{2}' | head -1 || true)

	# Identify and remove the associated veth pair
	local veth_idx
	if veth_idx=$(find_veth_for_namespace "$ns"); then
		local ovs_veth="veth${veth_idx}"
		docker exec "$OVS_CONTAINER" ovs-vsctl del-port "$bridge" "$ovs_veth" 2>/dev/null || true
		# Deleting one end of the veth pair removes both
		sudo nsenter -t "$PID_OVS" -n ip link del "$ovs_veth" 2>/dev/null || true
	else
		echo "  [warn] Could not locate veth for '${ns}' — bridge port may already be removed."
	fi

	# Flush any stale OVS flow rules referencing this client's MAC
	if [[ -n "$mac" ]]; then
		docker exec "$OVS_CONTAINER" ovs-ofctl del-flows "$bridge" "dl_src=${mac}" 2>/dev/null || true
		docker exec "$OVS_CONTAINER" ovs-ofctl del-flows "$bridge" "dl_dst=${mac}" 2>/dev/null || true
	fi

	sudo ip netns del "$ns"
}

main() {
	validate_requirements
	ensure_ovs_namespace

	local namespaces=()

	if [[ -n "$NS_SINGLE" ]]; then
		ip netns list 2>/dev/null | awk '{print $1}' | grep -qxF "$NS_SINGLE" \
			|| die "Namespace '${NS_SINGLE}' does not exist."
		namespaces=("$NS_SINGLE")
	else
		# Collect all namespaces whose name starts with <PREFIX>_
		local ns
		while read -r ns _rest; do
			[[ "$ns" == "${PREFIX}_"* ]] && namespaces+=("$ns") || true
		done < <(ip netns list 2>/dev/null || true)

		if [[ ${#namespaces[@]} -eq 0 ]]; then
			echo "No namespaces found matching prefix '${PREFIX}'."
			exit 0
		fi
	fi

	echo "============================================================================"
	echo "Removing ${#namespaces[@]} test client(s) from LAN ${LAN}"
	echo "============================================================================"

	local ns
	for ns in "${namespaces[@]}"; do
		remove_client "$ns"
	done

	echo "============================================================================"
	echo "Done. Removed ${#namespaces[@]} client(s)."
	echo "============================================================================"
}

while [[ $# -gt 0 ]]; do
	case "$1" in
		--lan)
			LAN="$2"
			shift 2
			;;
		--prefix)
			PREFIX="$2"
			shift 2
			;;
		--name)
			NS_SINGLE="$2"
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
