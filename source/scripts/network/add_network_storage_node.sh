#!/bin/bash

# ============================================================================
# Attach a running MongoDB container to an existing LAN and join a replica set
# ============================================================================
# Prerequisites:
#   The container must already be running with --replSet <rs_name> --bind_ip_all
#   Example:
#     docker run -dit --name edge_storage_server_n1_member2 --network none \
#       -v edge_storage_server_n1_member2-data:/data/db edge_storage_server mongod \
#       --replSet rs_net1 --bind_ip_all --port 27018
# ============================================================================

set -euo pipefail

readonly SCRIPT_NAME="$(basename "$0")"
readonly OVS_CONTAINER="ovs"

declare -A LAN_BRIDGE=( [1]="ovs-br0" [2]="ovs-br1" )
declare -A LAN_SUBNET=( [1]="10.0.0" [2]="10.0.1" )
declare -A LAN_GATEWAY=( [1]="10.0.0.1" [2]="10.0.1.1" )
declare -A LAN_DEFAULT_RS=( [1]="rs_net1" [2]="rs_net2" )
declare -A LAN_DEFAULT_PRIMARY_CONTAINER=( [1]="edge_storage_server_n1" [2]="edge_storage_server_n2" )
declare -A VETH_RANGE_START=( [1]=10 [2]=30 )
declare -A VETH_RANGE_END=( [1]=19 [2]=49 )
declare -A RESERVED_SUFFIX=( [1]="1 100" [2]="1 100" )

LAN=""
CONTAINER_NAME=""
IP=""
MAC=""
IFACE_NAME="eth0"
PORT=27018
RS_NAME=""
PRIMARY_CONTAINER=""
PID_OVS=""

usage() {
	cat <<EOF
Usage: $SCRIPT_NAME --lan <1|2> --name <container> [OPTIONS]

Attach an already-running MongoDB container to an existing LAN and join its replica set.

Required:
  --lan <1|2>                  Target LAN
  --name, -n <container>       Running Docker container name

Optional:
  --ip <x.x.x.x>               IP address (auto-assigned if omitted)
  --mac <XX:XX:XX:XX:XX:XX>    MAC address (auto-generated if omitted)
  --iface <name>               Interface name inside the container (default: eth0)
  --port <port>                MongoDB port (default: 27018)
  --rs-name <name>             Replica set name (default: rs_net1 / rs_net2 based on LAN)
  --primary <container>        Container to run rs.add() on (default: edge_storage_server_n[LAN])
  -h, --help                   Show this help

Examples:
  $SCRIPT_NAME --lan 1 --name edge_storage_server_n1_member2
  $SCRIPT_NAME --lan 2 --name edge_storage_server_n2_member2 --ip 10.0.1.5 --rs-name rs_net2
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
	[[ -n "$CONTAINER_NAME" ]] || die "--name is required."

	local state
	state=$(docker inspect -f '{{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null) \
		|| die "Container '$CONTAINER_NAME' does not exist."
	[[ "$state" == "running" ]] \
		|| die "Container '$CONTAINER_NAME' is not running (state: ${state})."

	state=$(docker inspect -f '{{.State.Status}}' "$PRIMARY_CONTAINER" 2>/dev/null) \
		|| die "Primary container '$PRIMARY_CONTAINER' does not exist."
	[[ "$state" == "running" ]] \
		|| die "Primary container '$PRIMARY_CONTAINER' is not running (state: ${state})."

	docker inspect -f '{{.State.Pid}}' "$OVS_CONTAINER" >/dev/null 2>&1 \
		|| die "Container '$OVS_CONTAINER' is not running."

	docker exec "$OVS_CONTAINER" ovs-vsctl br-exists "${LAN_BRIDGE[$LAN]}" \
		|| die "OVS bridge '${LAN_BRIDGE[$LAN]}' does not exist."
}

collect_used_ips() {
	local subnet="${LAN_SUBNET[$LAN]}"
	local used=()
	local suffix

	for suffix in ${RESERVED_SUFFIX[$LAN]}; do
		used+=("${subnet}.${suffix}")
	done

	local cid
	for cid in $(docker ps -q); do
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

	printf '%s\n' "${used[@]}" | sort -u
}

validate_ip_not_taken() {
	local used
	used=$(collect_used_ips)
	if echo "$used" | grep -qxF "$IP"; then
		die "IP $IP is already in use on LAN ${LAN}."
	fi
}

auto_assign_ip() {
	local subnet="${LAN_SUBNET[$LAN]}"
	local used
	used=$(collect_used_ips)

	local host
	for host in $(seq 2 254); do
		local candidate="${subnet}.${host}"
		if ! echo "$used" | grep -qxF "$candidate"; then
			echo "$candidate"
			return 0
		fi
	done

	die "No free IP address available in ${subnet}.0/24."
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

cleanup_stale_veth() {
	local ovs_veth="$1"
	if ip link show "$ovs_veth" >/dev/null 2>&1; then
		sudo ip link del "$ovs_veth" >/dev/null 2>&1 || true
	fi
}

# Remove all OVS flow entries that reference the given MAC as either source or
# destination. Prevents stale flows from a prior attachment on a different port
# from silently dropping traffic to/from the re-attached container.
flush_stale_mac_flows() {
	local bridge="$1"
	local mac="$2"

	echo "Flushing stale OVS flows for MAC ${mac} on ${bridge}..."
	docker exec "$OVS_CONTAINER" ovs-ofctl del-flows "$bridge" "dl_src=${mac}" 2>/dev/null || true
	docker exec "$OVS_CONTAINER" ovs-ofctl del-flows "$bridge" "dl_dst=${mac}" 2>/dev/null || true
}

# Find the current primary host:port by querying PRIMARY_CONTAINER
find_primary_host() {
	local primary_host
	set +e
	primary_host=$(docker exec -i "$PRIMARY_CONTAINER" mongosh --quiet --port "$PORT" --eval "
try {
    var m = db.adminCommand({ isMaster: 1 });
    print(m.primary);
} catch(e) {
    print('ERROR:' + e);
}
" 2>/dev/null | tr -d '\r\n')
	set -e

	[[ -z "$primary_host" || "$primary_host" == ERROR:* ]] \
		&& die "Could not determine primary of '${RS_NAME}' via '${PRIMARY_CONTAINER}': ${primary_host}"

	echo "$primary_host"  # e.g. 10.0.0.4:27018
}

rs_add_member() {
	local new_host="${IP}:${PORT}"
	local primary_host="$1"   # host:port of current primary
	local primary_ip="${primary_host%%:*}"
	local primary_port="${primary_host##*:}"

	echo "Running rs.add('${new_host}') via primary ${primary_host}..."
	set +e
	local output
	output=$(docker exec -i "$PRIMARY_CONTAINER" mongosh --quiet \
		--host "$primary_ip" --port "$primary_port" --eval "
try {
    var result = rs.add('${new_host}');
    print(JSON.stringify(result));
} catch(e) {
    print('ERROR:' + e);
}
" 2>/dev/null)
	set -e

	if echo "$output" | grep -q '^ERROR:'; then
		echo "rs.add() threw an exception:"
		printf '%s\n' "$output"
		die "rs.add('${new_host}') failed."
	fi

	if ! echo "$output" | grep -Eq '"ok"\s*:\s*1'; then
		echo "rs.add() did not return ok:1. Output:"
		printf '%s\n' "$output"
		die "rs.add('${new_host}') failed."
	fi

	echo "rs.add('${new_host}') succeeded."
}

ensure_rs_secondary() {
	local new_host="${IP}:${PORT}"
	local primary_host="$1"
	local primary_ip="${primary_host%%:*}"
	local primary_port="${primary_host##*:}"
	local max_retries="${2:-10}"
	local retry_delay="${3:-3}"

	echo "Waiting for '${CONTAINER_NAME}' (${new_host}) to reach SECONDARY state..."

	local attempt
	for attempt in $(seq 1 "${max_retries}"); do
		echo "  Status check attempt ${attempt}/${max_retries}..."
		set +e
		local state
		state=$(docker exec -i "$PRIMARY_CONTAINER" mongosh --quiet \
			--host "$primary_ip" --port "$primary_port" --eval "
try {
    var status = rs.status();
    var member = status.members.find(m => m.name === '${new_host}');
    print(member ? member.stateStr : 'NOT_FOUND');
} catch(e) {
    print('ERROR:' + e);
}
" 2>/dev/null | tr -d '\r\n')
		set -e

		case "$state" in
			SECONDARY)
				echo "  ✅ ${new_host} is SECONDARY."
				return 0
				;;
			STARTUP*|RECOVERING)
				echo "  Still syncing (${state}), retrying in ${retry_delay}s..."
				;;
			NOT_FOUND)
				echo "  Member not yet visible in rs.status(), retrying in ${retry_delay}s..."
				;;
			ERROR:*)
				echo "  rs.status() error: ${state}, retrying in ${retry_delay}s..."
				;;
			*)
				echo "  Unexpected state '${state}', retrying in ${retry_delay}s..."
				;;
		esac

		sleep "${retry_delay}"
	done

	die "'${new_host}' did not reach SECONDARY after ${max_retries} attempts."
}

# Returns lines of the form "host:port STATE" for every member in the replica set.
# Non-fatal: prints a warning and returns an empty string on failure.
get_rs_members() {
	local primary_host="$1"
	local primary_ip="${primary_host%%:*}"
	local primary_port="${primary_host##*:}"

	set +e
	local output
	output=$(docker exec -i "$PRIMARY_CONTAINER" mongosh --quiet \
		--host "$primary_ip" --port "$primary_port" --eval "
var status = rs.status();
status.members.forEach(function(m) { print(m.name + ' ' + m.stateStr); });
" 2>/dev/null)
	set -e

	echo "$output"
}

main() {
	validate_requirements
	ensure_ovs_namespace

	local bridge="${LAN_BRIDGE[$LAN]}"
	local gateway="${LAN_GATEWAY[$LAN]}"

	echo "============================================================================"
	echo "Attaching storage container '${CONTAINER_NAME}' to LAN ${LAN}"
	echo "============================================================================"

	if [[ -z "$IP" ]]; then
		IP=$(auto_assign_ip)
		echo "Auto-assigned IP: ${IP}"
	else
		validate_ip_not_taken
	fi

	if [[ -z "$MAC" ]]; then
		MAC=$(auto_generate_mac "$IP")
		echo "Auto-generated MAC: ${MAC}"
	fi

	local veth_idx
	veth_idx=$(find_free_veth_index)

	local ovs_veth="veth${veth_idx}"
	local container_veth="veth${veth_idx}-peer"

	echo "Using veth pair: ${ovs_veth} <-> ${container_veth}"

	cleanup_stale_veth "$ovs_veth"

	echo "Creating veth pair..."
	sudo ip link add "$ovs_veth" type veth peer name "$container_veth"

	echo "Attaching ${ovs_veth} to OVS bridge ${bridge}..."
	sudo ip link set "$ovs_veth" netns ovs
	docker exec "$OVS_CONTAINER" ip link set "$ovs_veth" up
	docker exec "$OVS_CONTAINER" ovs-vsctl add-port "$bridge" "$ovs_veth"

	# Purge any stale flows from a prior attachment of this MAC on a different
	# port — otherwise the controller routes replies to the old dead port.
	flush_stale_mac_flows "$bridge" "$MAC"

	local pid
	pid=$(docker inspect -f '{{.State.Pid}}' "$CONTAINER_NAME")

	echo "Moving ${container_veth} into container namespace (PID ${pid})..."
	sudo ip link set "$container_veth" netns "$pid"

	echo "Configuring ${IFACE_NAME} inside '${CONTAINER_NAME}'..."
	sudo nsenter -t "$pid" -n ip link set "$container_veth" name "$IFACE_NAME"
	sudo nsenter -t "$pid" -n ip link set "$IFACE_NAME" address "$MAC"
	sudo nsenter -t "$pid" -n ip link set "$IFACE_NAME" up
	sudo nsenter -t "$pid" -n ip addr add "${IP}/24" dev "$IFACE_NAME"
	sudo nsenter -t "$pid" -n ip route add default via "$gateway"

	echo
	echo "============================================================================"
	echo "Network node added successfully"
	echo "============================================================================"
	echo "  Container      : ${CONTAINER_NAME}"
	echo "  LAN            : ${LAN} (${bridge})"
	echo "  IP             : ${IP}/24"
	echo "  MAC            : ${MAC}"
	echo "  Gateway        : ${gateway}"
	echo "  Switch port    : ${ovs_veth} (inside OVS / ${bridge})"
	echo "  Container link : ${container_veth} -> ${IFACE_NAME} (inside ${CONTAINER_NAME})"
	echo "============================================================================"

	# ============================================================================
	# Replica set membership
	# ============================================================================
	echo
	echo "============================================================================"
	echo "Joining replica set '${RS_NAME}'"
	echo "============================================================================"

	local primary_host
	primary_host=$(find_primary_host)
	echo "  Primary: ${primary_host}"

	rs_add_member "$primary_host"

	ensure_rs_secondary "$primary_host"

	local rs_members
	rs_members=$(get_rs_members "$primary_host")

	echo
	echo "============================================================================"
	echo "Storage node joined successfully"
	echo "============================================================================"
	echo "  Container      : ${CONTAINER_NAME}"
	echo "  Replica set    : ${RS_NAME}"
	echo "  New member     : ${IP}:${PORT}"
	echo "  Primary        : ${primary_host}"
	echo "  Members        :"
	if [[ -n "$rs_members" ]]; then
		while IFS= read -r line; do
			[[ -z "$line" ]] && continue
			local host state
			host="${line%% *}"
			state="${line##* }"
			printf '    %-25s %s\n' "$host" "$state"
		done <<< "$rs_members"
	else
		echo "    ⚠️  Could not retrieve member list"
	fi
	echo "============================================================================"
}

# ============================================================================
# Argument parsing
# ============================================================================
while [[ $# -gt 0 ]]; do
	case "$1" in
		--lan)
			LAN="$2"
			shift 2
			;;
		--name|-n)
			CONTAINER_NAME="$2"
			shift 2
			;;
		--ip)
			IP="$2"
			shift 2
			;;
		--mac)
			MAC="$2"
			shift 2
			;;
		--iface)
			IFACE_NAME="$2"
			shift 2
			;;
		--port)
			PORT="$2"
			shift 2
			;;
		--rs-name)
			RS_NAME="$2"
			shift 2
			;;
		--primary)
			PRIMARY_CONTAINER="$2"
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

# Apply defaults that depend on LAN (must be after arg parsing)
[[ -n "$LAN" ]] || die "--lan is required."
[[ -z "$RS_NAME" ]] && RS_NAME="${LAN_DEFAULT_RS[$LAN]}"
[[ -z "$PRIMARY_CONTAINER" ]] && PRIMARY_CONTAINER="${LAN_DEFAULT_PRIMARY_CONTAINER[$LAN]}"

main
