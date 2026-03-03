#!/bin/bash

# ==========================================================================
# Build a single lab network (OVS + hosts + MongoDB shard members)
#
# Parameters (flags):
#   --containers, -c         number of application containers to create
#   --mongo-containers, -m   number of MongoDB containers (shard members) to create
#   --lan, -l                LAN network address (expects a /24; accepts 10.0.X.0 or 10.0.X.0/24)
#   --bridges, -b            number of OVS bridges to create for this LAN (>= 1)
#
# Notes:
# - This script assumes the OVS container is running as "ovs" and the NAT
#   router container is running as "nat-router".
# - When multiple bridges are requested, extra bridges are connected to the
#   primary bridge using veth patch links inside the OVS namespace.
# - Host/Mongo placement across bridges:
#     * router + all mongo members + first N app containers go on primary bridge
#     * remaining app containers are round-robin assigned to extra bridges
#   (override N with PRIMARY_BRIDGE_CONTAINER_COUNT).
# ==========================================================================

set -euo pipefail

SCRIPT_NAME="$(basename "$0")"
readonly SCRIPT_NAME

usage() {
	cat <<EOF
Usage:
	${SCRIPT_NAME} --containers <N> --mongo-containers <N> --lan <10.0.X.0[/24]> --bridges <N>

Flags:
	-c, --containers         Number of application containers
	-m, --mongo-containers   Number of MongoDB shard member containers
	-l, --lan                LAN base CIDR (10.0.X.0 or 10.0.X.0/24)
	-b, --bridges            Number of OVS bridges for this LAN
	-h, --help               Show help

Examples:
	${SCRIPT_NAME} --containers 2 --mongo-containers 2 --lan 10.0.1.0/24 --bridges 1
	${SCRIPT_NAME} -c 3 -m 2 -l 10.0.0.0 -b 2

Environment variables:
	MONGO_ENV_FILE                 Path to .env-mongo (default: ../.env-mongo relative to this script)
	PRIMARY_BRIDGE_CONTAINER_COUNT How many app containers attach to the primary bridge (default: 2)
	MONGO_WAN_PORT_BASE            Base WAN port for first mongo member (default: 27018 + net_id*100)
	MONGO_WAN_PORT_STEP            Port step per additional mongo member (default: 100)
	MONGO_WAN_PORTS                Comma list of overrides: "mongodb-n2=27118,mongodb-n4=27218"
	ROUTER_WAN_IP                  Router WAN IP used for DNAT/SNAT (default: 192.168.100.2)
	ROUTER_WAN_HOST_IFACE          Host iface towards router WAN (default: veth4)
EOF
}

die() {
	echo "Error: $*" >&2
	exit 1
}

require_cmd() {
	local cmd="$1"
	command -v "$cmd" >/dev/null 2>&1 || die "Missing required command: ${cmd}"
}

is_uint() {
	[[ "$1" =~ ^[0-9]+$ ]]
}

parse_lan() {
	# Accept 10.0.X.0 or 10.0.X.0/24. Outputs: LAN_IP_BASE LAN_CIDR NET_ID
	local input="$1"
	local ip
	local cidr

	if [[ "$input" == */* ]]; then
		ip="${input%/*}"
		cidr="${input#*/}"
	else
		ip="$input"
		cidr="24"
	fi

	[[ "$cidr" == "24" ]] || die "Only /24 LANs are supported (got /${cidr})."

	# shellcheck disable=SC2001
	if ! echo "$ip" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$'; then
		die "Invalid LAN address '${input}'"
	fi

	IFS='.' read -r o1 o2 o3 o4 <<<"$ip"
	[[ "$o1" == "10" && "$o2" == "0" ]] || die "LAN must be in 10.0.X.0/24 (got ${ip}/${cidr})"
	[[ "$o4" == "0" ]] || die "LAN base address must end with .0 (got ${ip})"
	[[ "$o3" =~ ^[0-9]+$ ]] || die "Invalid third octet in LAN: ${ip}"

	echo "${o1}.${o2}.${o3}.0" "${o1}.${o2}.${o3}.0/${cidr}" "${o3}"
}

ensure_netns_link() {
	local ns_name="$1"
	local pid="$2"
	sudo mkdir -p /var/run/netns
	sudo ln -sf "/proc/${pid}/ns/net" "/var/run/netns/${ns_name}"
}

create_veth_pair() {
	local a="$1"
	local b="$2"
	if ip link show "$a" >/dev/null 2>&1; then
		sudo ip link del "$a" >/dev/null 2>&1 || true
	fi
	if ip link show "$b" >/dev/null 2>&1; then
		sudo ip link del "$b" >/dev/null 2>&1 || true
	fi
	sudo ip link add "$a" type veth peer name "$b"
}

mac_for_id() {
	# Deterministic-ish MAC: 02:00:<net_id>:00:00:<id>
	local net_id="$1"
	local host_id="$2"

	# Format as 2-digit hex
	local net_hex
	local host_hex
	net_hex=$(printf '%02x' "$net_id")
	host_hex=$(printf '%02x' "$host_id")
	echo "02:00:${net_hex}:00:00:${host_hex}"
}

container_name_for_index() {
	# Keep compatibility with existing naming for net_id 0/1 when possible.
	# net0: container1, container2, then container5+...
	# net1: container3, container4, then container7+...
	local net_id="$1"
	local idx0="$2" # 0-based
	if (( idx0 < 2 )); then
		echo "container$((net_id * 2 + 1 + idx0))"
	else
		echo "container$((5 + net_id * 2 + (idx0 - 2)))"
	fi
}

mongo_name_for_index() {
	# net0: mongodb-n1, mongodb-n3, mongodb-n5...
	# net1: mongodb-n2, mongodb-n4, mongodb-n6...
	local net_id="$1"
	local idx0="$2" # 0-based
	echo "mongodb-n$((net_id + 1 + idx0 * 2))"
}

bridge_names() {
	# Output an array-like list of bridge names.
	# Primary: ovs-br<net_id>
	# Extra: ovs-br<net_id + 2*i>
	local net_id="$1"
	local count="$2"
	local i
	local names=()
	names+=("ovs-br${net_id}")
	for ((i = 1; i < count; i++)); do
		names+=("ovs-br$((net_id + 2 * i))")
	done
	printf '%s\n' "${names[@]}"
}

parse_mongo_wan_port_overrides() {
	# Parses MONGO_WAN_PORTS into an associative array MONGO_WAN_PORT_OVERRIDE
	# Format: "mongodb-n2=27118,mongodb-n4=27218"
	local input="${1:-}"
	declare -gA MONGO_WAN_PORT_OVERRIDE=()

	[[ -n "$input" ]] || return 0
	local pair
	IFS=',' read -r -a pairs <<<"$input"
	for pair in "${pairs[@]}"; do
		[[ "$pair" == *"="* ]] || die "Invalid MONGO_WAN_PORTS entry '${pair}' (expected name=port)"
		local name="${pair%%=*}"
		local port="${pair#*=}"
		is_uint "$port" || die "Invalid port for ${name}: ${port}"
		MONGO_WAN_PORT_OVERRIDE["$name"]="$port"
	done
}

parse_args() {
	# Outputs (via echo): app_count mongo_count lan_input bridge_count
	local app_count=""
	local mongo_count=""
	local lan_input=""
	local bridge_count=""

	# Backward-compatible positional form:
	#   build_network.sh <app_container_count> <mongo_container_count> <lan_cidr> <bridge_count>
	if [[ $# -eq 4 && "$1" != -* && "$2" != -* && "$3" != -* && "$4" != -* ]]; then
		echo "$1" "$2" "$3" "$4"
		return 0
	fi

	while [[ $# -gt 0 ]]; do
		case "$1" in
			-c|--containers)
				shift
				[[ $# -gt 0 ]] || die "Missing value for --containers"
				app_count="$1"
				;;
			-m|--mongo-containers|--mongo_containers)
				shift
				[[ $# -gt 0 ]] || die "Missing value for --mongo-containers"
				mongo_count="$1"
				;;
			-l|--lan)
				shift
				[[ $# -gt 0 ]] || die "Missing value for --lan"
				lan_input="$1"
				;;
			-b|--bridges)
				shift
				[[ $# -gt 0 ]] || die "Missing value for --bridges"
				bridge_count="$1"
				;;
			-h|--help)
				usage
				exit 0
				;;
			*)
				die "Unknown argument: $1 (use --help)"
				;;
		esac
		shift
	done

	[[ -n "$app_count" ]] || die "Missing required flag: --containers"
	[[ -n "$mongo_count" ]] || die "Missing required flag: --mongo-containers"
	[[ -n "$lan_input" ]] || die "Missing required flag: --lan"
	[[ -n "$bridge_count" ]] || die "Missing required flag: --bridges"

	echo "$app_count" "$mongo_count" "$lan_input" "$bridge_count"
}

main() {
	local app_count
	local mongo_count
	local lan_input
	local bridge_count
	read -r app_count mongo_count lan_input bridge_count < <(parse_args "$@")

	is_uint "$app_count" || die "app_container_count must be an integer"
	is_uint "$mongo_count" || die "mongo_container_count must be an integer"
	is_uint "$bridge_count" || die "bridge_count must be an integer"

	(( app_count >= 0 )) || die "app_container_count must be >= 0"
	(( mongo_count >= 0 )) || die "mongo_container_count must be >= 0"
	(( bridge_count >= 1 )) || die "bridge_count must be >= 1"

	require_cmd docker
	require_cmd ip
	require_cmd nsenter
	require_cmd sudo

	docker inspect ovs >/dev/null 2>&1 || die "Required container 'ovs' not found"
	docker inspect nat-router >/dev/null 2>&1 || die "Required container 'nat-router' not found"

	local lan_base
	local lan_cidr
	local net_id
	read -r lan_base lan_cidr net_id < <(parse_lan "$lan_input")
	local lan_prefix="${lan_base%0}"
	local gateway_ip="${lan_prefix}1"

	local router_wan_ip="${ROUTER_WAN_IP:-192.168.100.2}"
	local router_wan_host_iface="${ROUTER_WAN_HOST_IFACE:-veth4}"

	local primary_bridge_container_count="${PRIMARY_BRIDGE_CONTAINER_COUNT:-2}"
	is_uint "$primary_bridge_container_count" || die "PRIMARY_BRIDGE_CONTAINER_COUNT must be an integer"

	# Replica set naming convention:
	local repl_set="rs_net$((net_id + 1))"

	# Mongo runs on a fixed internal port across the lab.
	local mongo_internal_port=27018

	local script_dir
	script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
	local default_mongo_env_file="${script_dir}/../.env-mongo"
	local mongo_env_file="${MONGO_ENV_FILE:-${default_mongo_env_file}}"

	local ovs_pid
	ovs_pid=$(docker inspect -f '{{.State.Pid}}' ovs)
	ensure_netns_link ovs "$ovs_pid"

	local router_pid
	router_pid=$(docker inspect -f '{{.State.Pid}}' nat-router)

	# Build bridge list
	mapfile -t bridges < <(bridge_names "$net_id" "$bridge_count")
	local primary_bridge="${bridges[0]}"

	echo "Creating OVS bridges for LAN ${lan_cidr} (net_id=${net_id})..."
	local br
	for br in "${bridges[@]}"; do
		docker exec ovs ovs-vsctl --may-exist add-br "$br"
	done

	# Plan veth pairs
	# - app container ports: veth<n>-to-ovs / veth<n>-peer
	# - router LAN port: veth-router-<net_id>
	# - mongo ports: veth-mongo-<net_id>-<i>
	# - patch links (if bridge_count>1): veth-patch-<net_id>-<i> and -peer
	local i
	local -a app_veth_ovs=()
	local -a app_veth_peer=()
	local -a app_container_names=()
	for ((i = 0; i < app_count; i++)); do
		local name
		name=$(container_name_for_index "$net_id" "$i")
		app_container_names+=("$name")
		app_veth_ovs+=("veth-n${net_id}-c${i}")
		app_veth_peer+=("veth-n${net_id}-c${i}-peer")
	done

	local router_veth_ovs="veth-n${net_id}-router"
	local router_veth_peer="veth-n${net_id}-router-peer"

	local -a mongo_veth_ovs=()
	local -a mongo_veth_peer=()
	local -a mongo_container_names=()
	for ((i = 0; i < mongo_count; i++)); do
		local mname
		mname=$(mongo_name_for_index "$net_id" "$i")
		mongo_container_names+=("$mname")
		mongo_veth_ovs+=("veth-n${net_id}-mongo${i}")
		mongo_veth_peer+=("veth-n${net_id}-mongo${i}-peer")
	done

	local -a patch_veth_a=()
	local -a patch_veth_b=()
	if (( bridge_count > 1 )); then
		for ((i = 1; i < bridge_count; i++)); do
			patch_veth_a+=("veth-n${net_id}-patch${i}")
			patch_veth_b+=("veth-n${net_id}-patch${i}-peer")
		done
	fi

	echo "Creating veth pairs..."
	for ((i = 0; i < app_count; i++)); do
		create_veth_pair "${app_veth_ovs[$i]}" "${app_veth_peer[$i]}"
	done
	create_veth_pair "$router_veth_ovs" "$router_veth_peer"
	for ((i = 0; i < mongo_count; i++)); do
		create_veth_pair "${mongo_veth_ovs[$i]}" "${mongo_veth_peer[$i]}"
	done
	for ((i = 0; i < ${#patch_veth_a[@]}; i++)); do
		create_veth_pair "${patch_veth_a[$i]}" "${patch_veth_b[$i]}"
	done

	echo "Attaching veth ports to OVS..."
	# Bring up OVS-facing ends (OVS container uses host netns via --network host).
	for ((i = 0; i < app_count; i++)); do
		docker exec ovs ip link set "${app_veth_ovs[$i]}" up
	done
	docker exec ovs ip link set "$router_veth_ovs" up
	for ((i = 0; i < mongo_count; i++)); do
		docker exec ovs ip link set "${mongo_veth_ovs[$i]}" up
	done
	for ((i = 0; i < ${#patch_veth_a[@]}; i++)); do
		docker exec ovs ip link set "${patch_veth_a[$i]}" up
		docker exec ovs ip link set "${patch_veth_b[$i]}" up
	done

	# Keep the same pattern as other scripts: move to ovs netns + add ports.
	for ((i = 0; i < app_count; i++)); do
		sudo ip link set "${app_veth_ovs[$i]}" netns ovs
	done
	sudo ip link set "$router_veth_ovs" netns ovs
	for ((i = 0; i < mongo_count; i++)); do
		sudo ip link set "${mongo_veth_ovs[$i]}" netns ovs
	done
	for ((i = 0; i < ${#patch_veth_a[@]}; i++)); do
		sudo ip link set "${patch_veth_a[$i]}" netns ovs
		sudo ip link set "${patch_veth_b[$i]}" netns ovs
	done

	# Bridge assignment:
	# - primary gets router + all mongo + first primary_bridge_container_count app containers
	# - remaining apps distributed across extra bridges (if any)
	local assigned_bridge
	for ((i = 0; i < app_count; i++)); do
		if (( i < primary_bridge_container_count || bridge_count == 1 )); then
			assigned_bridge="$primary_bridge"
		else
			# Round-robin across extra bridges
			local extra_idx=$(((i - primary_bridge_container_count) % (bridge_count - 1) + 1))
			assigned_bridge="${bridges[$extra_idx]}"
		fi
		docker exec ovs ovs-vsctl --may-exist add-port "$assigned_bridge" "${app_veth_ovs[$i]}"
	done

	docker exec ovs ovs-vsctl --may-exist add-port "$primary_bridge" "$router_veth_ovs"
	for ((i = 0; i < mongo_count; i++)); do
		docker exec ovs ovs-vsctl --may-exist add-port "$primary_bridge" "${mongo_veth_ovs[$i]}"
	done

	# Patch links: connect each extra bridge to primary bridge.
	if (( bridge_count > 1 )); then
		for ((i = 1; i < bridge_count; i++)); do
			local a="${patch_veth_a[$((i - 1))]}"
			local b="${patch_veth_b[$((i - 1))]}"
			docker exec ovs ovs-vsctl --may-exist add-port "$primary_bridge" "$a"
			docker exec ovs ovs-vsctl --may-exist add-port "${bridges[$i]}" "$b"
		done
	fi

	echo "Launching application containers (network none)..."
	for ((i = 0; i < app_count; i++)); do
		docker run -dit --name "${app_container_names[$i]}" --network none ubuntu-host
	done

	echo "Launching MongoDB containers (network none)..."
	if [[ -f "$mongo_env_file" ]]; then
		echo "Loading MongoDB environment from: ${mongo_env_file}"
	else
		echo "WARNING: MongoDB env file not found at ${mongo_env_file}"
		echo "MongoDB will start without authentication!"
	fi

	for ((i = 0; i < mongo_count; i++)); do
		local mname="${mongo_container_names[$i]}"
		local volume_name="${mname}-data"
		if [[ -f "$mongo_env_file" ]]; then
			docker run -dit --name "$mname" --network none \
				--env-file "$mongo_env_file" \
				--no-healthcheck \
				-v "${volume_name}:/data/db" ubuntu-mongodb mongod \
				--shardsvr --replSet "$repl_set" --bind_ip_all --port "$mongo_internal_port"
		else
			docker run -dit --name "$mname" --network none \
				--no-healthcheck \
				-v "${volume_name}:/data/db" ubuntu-mongodb mongod \
				--shardsvr --replSet "$repl_set" --bind_ip_all --port "$mongo_internal_port"
		fi
	done

	echo "Moving veth peers into container namespaces..."
	local -a app_pids=()
	for ((i = 0; i < app_count; i++)); do
		app_pids+=("$(docker inspect -f '{{.State.Pid}}' "${app_container_names[$i]}")")
		sudo ip link set "${app_veth_peer[$i]}" netns "${app_pids[$i]}"
	done

	local -a mongo_pids=()
	for ((i = 0; i < mongo_count; i++)); do
		mongo_pids+=("$(docker inspect -f '{{.State.Pid}}' "${mongo_container_names[$i]}")")
		sudo ip link set "${mongo_veth_peer[$i]}" netns "${mongo_pids[$i]}"
	done

	sudo ip link set "$router_veth_peer" netns "$router_pid"

	echo "Configuring container interfaces and routes..."
	# Addressing plan: .1 router, then apps from .2.., then mongo after apps.
	local host_id=2
	for ((i = 0; i < app_count; i++)); do
		local pid="${app_pids[$i]}"
		local ip_addr="${lan_prefix}${host_id}"
		local mac
		mac=$(mac_for_id "$net_id" "$host_id")
		sudo nsenter -t "$pid" -n ip link set "${app_veth_peer[$i]}" name eth0
		sudo nsenter -t "$pid" -n ip link set eth0 address "$mac"
		sudo nsenter -t "$pid" -n ip link set eth0 up
		sudo nsenter -t "$pid" -n ip addr add "${ip_addr}/24" dev eth0
		sudo nsenter -t "$pid" -n ip route replace default via "$gateway_ip"
		host_id=$((host_id + 1))
	done

	for ((i = 0; i < mongo_count; i++)); do
		local pid="${mongo_pids[$i]}"
		local ip_addr="${lan_prefix}${host_id}"
		local mac
		mac=$(mac_for_id "$net_id" "$host_id")
		sudo nsenter -t "$pid" -n ip link set "${mongo_veth_peer[$i]}" name eth0
		sudo nsenter -t "$pid" -n ip link set eth0 address "$mac"
		sudo nsenter -t "$pid" -n ip link set eth0 up
		sudo nsenter -t "$pid" -n ip addr add "${ip_addr}/24" dev eth0
		sudo nsenter -t "$pid" -n ip route replace default via "$gateway_ip"
		host_id=$((host_id + 1))
	done

	echo "Configuring NAT router LAN interface for ${lan_cidr}..."
	local router_lan_if="eth$((net_id + 1))"
	sudo nsenter -t "$router_pid" -n ip link set "$router_veth_peer" name "$router_lan_if"
	sudo nsenter -t "$router_pid" -n ip link set "$router_lan_if" up
	sudo nsenter -t "$router_pid" -n ip addr replace "${gateway_ip}/24" dev "$router_lan_if"

	# Enable IP forwarding
	sudo nsenter -t "$router_pid" -n bash -c 'echo 1 > /proc/sys/net/ipv4/ip_forward'

	# Ensure host route (best-effort; requires router WAN to be present)
	echo "Ensuring host route to ${lan_cidr} via ${router_wan_ip}..."
	if ip link show "${router_wan_host_iface}" >/dev/null 2>&1; then
		if ! sudo ip route replace "${lan_cidr}" via "${router_wan_ip}" dev "${router_wan_host_iface}" >/dev/null 2>&1; then
			echo "WARNING: failed to program host route to ${lan_cidr}; check host networking." >&2
		else
			ip route show "${lan_cidr}" || true
		fi
	else
		echo "WARNING: host interface ${router_wan_host_iface} not found; skipping host route install." >&2
	fi

	# Router NAT (best-effort) and forward rules between WAN (eth0) and this LAN
	# Keep 10.0.x.0/24 source addresses intact for traffic that stays in 192.168.100.0/24
	sudo nsenter -t "$router_pid" -n bash -c "
		if ! iptables -t nat -C POSTROUTING -s ${lan_cidr} ! -d 192.168.100.0/24 -o eth0 -j MASQUERADE 2>/dev/null; then
			iptables -t nat -A POSTROUTING -s ${lan_cidr} ! -d 192.168.100.0/24 -o eth0 -j MASQUERADE
		fi
	"

	sudo nsenter -t "$router_pid" -n bash -c "
		if ! iptables -C FORWARD -i eth0 -o ${router_lan_if} -j ACCEPT 2>/dev/null; then
			iptables -A FORWARD -i eth0 -o ${router_lan_if} -j ACCEPT
		fi
		if ! iptables -C FORWARD -i ${router_lan_if} -o eth0 -j ACCEPT 2>/dev/null; then
			iptables -A FORWARD -i ${router_lan_if} -o eth0 -j ACCEPT
		fi
	"

	# Expose MongoDB shard members via router WAN IP using DNAT/SNAT
	local mongo_wan_port_base
	mongo_wan_port_base="${MONGO_WAN_PORT_BASE:-$((27018 + net_id * 100))}"
	local mongo_wan_port_step
	mongo_wan_port_step="${MONGO_WAN_PORT_STEP:-100}"
	is_uint "$mongo_wan_port_base" || die "MONGO_WAN_PORT_BASE must be an integer"
	is_uint "$mongo_wan_port_step" || die "MONGO_WAN_PORT_STEP must be an integer"
	parse_mongo_wan_port_overrides "${MONGO_WAN_PORTS:-}"

	for ((i = 0; i < mongo_count; i++)); do
		local mname="${mongo_container_names[$i]}"
		local mhost_ip
		# mongo IP is after apps: gateway(.1), apps(.2..), then mongo starts at (.2+app_count)
		mhost_ip="${lan_prefix}$((2 + app_count + i))"
		local wan_port=$((mongo_wan_port_base + i * mongo_wan_port_step))
		if [[ -n "${MONGO_WAN_PORT_OVERRIDE[${mname}]:-}" ]]; then
			wan_port="${MONGO_WAN_PORT_OVERRIDE[${mname}]}"
		fi

		echo "Exposing ${mname} (${mhost_ip}:${mongo_internal_port}) as ${router_wan_ip}:${wan_port}"

		sudo nsenter -t "$router_pid" -n bash -c "
			if ! iptables -t nat -C PREROUTING -i eth0 -p tcp -d ${router_wan_ip} --dport ${wan_port} \
				-j DNAT --to-destination ${mhost_ip}:${mongo_internal_port} 2>/dev/null; then
				iptables -t nat -A PREROUTING -i eth0 -p tcp -d ${router_wan_ip} --dport ${wan_port} \
					-j DNAT --to-destination ${mhost_ip}:${mongo_internal_port}
			fi
			if ! iptables -t nat -C POSTROUTING -o ${router_lan_if} -p tcp -s ${mhost_ip} --sport ${mongo_internal_port} \
				-j SNAT --to-source ${router_wan_ip}:${wan_port} 2>/dev/null; then
				iptables -t nat -A POSTROUTING -o ${router_lan_if} -p tcp -s ${mhost_ip} --sport ${mongo_internal_port} \
					-j SNAT --to-source ${router_wan_ip}:${wan_port}
			fi
		"
	done

	echo "OVS status:"
	docker exec ovs ovs-vsctl show
}

main "$@"