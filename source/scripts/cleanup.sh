#!/bin/bash

# Robust cleanup utility for network artifacts and Docker resources.
#
# Usage:
#   ./cleanup.sh            # Clean everything (network + docker)
#   ./cleanup.sh -n|--network  # Clean only network artifacts
#   ./cleanup.sh -d|--docker   # Clean only Docker containers (and related)
#   ./cleanup.sh -s|--stop-containers  # Stop running containers (no removal)
#   ./cleanup.sh --images      # Also remove project images tagged :latest
#   NAT_IFACE=<iface> NAT_SUBNET=192.168.100.0/24 ./cleanup.sh   # Override defaults when NAT cleanup is needed
#
# Notes:
# - This script is intended to run on Linux/WSL with required privileges.
# - It uses sudo when needed for network operations if not run as root.

set -Eeuo pipefail
IFS=$'\n\t'

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

print_usage() {
	cat <<EOF
Usage: $SCRIPT_NAME [options]

Options:
	-n, --network    Clean only network artifacts
	-d, --docker     Clean only Docker resources (containers, dangling images, networks)
	-s, --stop-containers  Stop all running containers (no removal)
	    --images     Remove project images tagged :latest (in addition to selected mode)
	-v, --volumes            Remove edge_storage_server volumes
	-r, --reset              Remove all containers and prune edge_storage_server volumes
	    --image-filter NAME  Scope stop/remove operations to containers from image NAME
	-h, --help               Show this help
EOF
}

# Early help: if first arg is -h/--help, print usage and exit 0
if [[ ${1-} == "-h" || ${1-} == "--help" ]]; then
		print_usage
		exit 0
fi

# Defaults (can be overridden via env)
# NAT_IFACE=${NAT_IFACE:-enp0s9}
NAT_IFACE=${NAT_IFACE:}
NAT_SUBNET=${NAT_SUBNET:-192.168.100.0/24}



# Detect sudo usage for privileged cmds
need_sudo() {
	if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
		return 1
	fi
	return 0
}

SUDO=""
if need_sudo; then
	if command -v sudo >/dev/null 2>&1; then
		SUDO="sudo"
	else
		warn "Not running as root and 'sudo' is not available; privileged operations may fail."
	fi
fi

require_cmd() {
	command -v "$1" >/dev/null 2>&1 || { error "Required command not found: $1"; exit 127; }
}

ip_safe_del_link() {
	local link="$1"
	if $SUDO ip link show "$link" >/dev/null 2>&1; then
		$SUDO ip link del "$link" || warn "Failed to delete link: $link"
	else
		log "Link not present, skipping: $link"
	fi
}

iptables_safe_delete_nat() {
	local subnet="$1"; shift
	local iface="$1"
	if [[ -z "$iface" ]]; then
		log "NAT_IFACE not set; skipping NAT rule cleanup."
		return 0
	fi
	# Attempt to delete MASQUERADE rule if present
	if $SUDO iptables -t nat -C POSTROUTING -s "$subnet" -o "$iface" -j MASQUERADE >/dev/null 2>&1; then
		$SUDO iptables -t nat -D POSTROUTING -s "$subnet" -o "$iface" -j MASQUERADE || warn "Failed to delete NAT rule"
	else
		log "NAT rule not present, skipping."
	fi
}

network_cleanup() {
	log "🧹 Cleaning up network artifacts"
	require_cmd ip
	# veth pairs to remove (both ends handled by single 'del')
	local veths=(veth1 veth2 veth3 veth4 veth5 veth6)
	for v in "${veths[@]}"; do
		ip_safe_del_link "$v"
	done

	# Flush host-side IP config (best-effort)
	if $SUDO ip link show veth5 >/dev/null 2>&1; then
		$SUDO ip addr flush dev veth5 || warn "Failed to flush addresses on veth5"
	fi

	# Remove OVS netns symlink if it exists
	if [[ -L /var/run/netns/ovs || -e /var/run/netns/ovs ]]; then
		$SUDO rm -f /var/run/netns/ovs || warn "Failed to remove /var/run/netns/ovs"
	else
		log "/var/run/netns/ovs not present, skipping."
	fi

	# Remove NAT rule
	if command -v iptables >/dev/null 2>&1; then
		iptables_safe_delete_nat "$NAT_SUBNET" "$NAT_IFACE"
	else
		warn "iptables not available; skipping NAT cleanup."
	fi

	log "✅ Network cleanup complete."
}

docker_cmd() {
	# choose docker or sudo docker
	if command -v docker >/dev/null 2>&1; then
		if [[ "${EUID:-$(id -u)}" -eq 0 ]] || id -nG 2>/dev/null | grep -q '\bdocker\b'; then
			echo docker
		elif command -v sudo >/dev/null 2>&1; then
			echo "sudo docker"
		else
			echo docker
		fi
	else
		echo ""
	fi
}

docker_cleanup() {
	local DOCKER
	DOCKER=$(docker_cmd)
	if [[ -z "$DOCKER" ]]; then
		warn "Docker not installed; skipping Docker cleanup."
		return 0
	fi

	log "🧹 Cleaning up Docker resources"

	# Build optional ancestor filter
	local filter_args=()
	if [[ -n "$IMAGE_FILTER" ]]; then
		filter_args=(--filter "ancestor=${IMAGE_FILTER}")
		log "Filtering containers by image: ${IMAGE_FILTER}"
	fi

	# Stop and remove containers (all, or filtered by image)
	local cids
	if cids=$(${DOCKER} ps -aq "${filter_args[@]}" 2>/dev/null); then
		if [[ -n "$cids" ]]; then
			${DOCKER} stop $cids >/dev/null 2>&1 || true
			${DOCKER} rm -f $cids >/dev/null 2>&1 || true
			log "Removed containers: $(echo "$cids" | wc -w)"
		else
			log "No containers to remove."
		fi
	else
		warn "Failed to list containers."
	fi

	# Optionally remove dangling images and networks created by this project
	# Remove dangling images
	local dangling
	if dangling=$(${DOCKER} images -f dangling=true -q 2>/dev/null); then
		if [[ -n "$dangling" ]]; then
			${DOCKER} rmi -f $dangling >/dev/null 2>&1 || true
			log "Removed dangling images: $(echo "$dangling" | wc -w)"
		else
			log "No dangling images to remove."
		fi
	fi

	# Prune unused networks (safe, doesn't touch in-use networks)
	${DOCKER} network prune -f >/dev/null 2>&1 || true
	# Prune build cache
	${DOCKER} builder prune -f >/dev/null 2>&1 || true

	log "✅ Docker cleanup complete."
}

# Stop running containers without removing them
stop_containers() {
	local DOCKER
	DOCKER=$(docker_cmd)
	if [[ -z "$DOCKER" ]]; then
		warn "Docker not installed; skipping container stop."
		return 0
	fi

	log "⏸️ Stopping running containers"

	# Build optional ancestor filter
	local filter_args=()
	if [[ -n "$IMAGE_FILTER" ]]; then
		filter_args=(--filter "ancestor=${IMAGE_FILTER}")
		log "Filtering containers by image: ${IMAGE_FILTER}"
	fi

	local running
	if running=$(${DOCKER} ps -q "${filter_args[@]}" 2>/dev/null); then
		if [[ -n "$running" ]]; then
			${DOCKER} stop $running >/dev/null 2>&1 || warn "Failed to stop one or more containers"
			log "Stopped containers: $(echo "$running" | wc -w)"
		else
			log "No running containers to stop."
		fi
	else
		warn "Failed to list running containers."
	fi
}

# Remove project images tagged :latest
images_cleanup() {
	local DOCKER
	DOCKER=$(docker_cmd)
	if [[ -z "$DOCKER" ]]; then
		warn "Docker not installed; skipping image removal."
		return 0
	fi
	# Project image tags (must match build_images.sh)
	local images=(
		ovs-container
		ubuntu-nat-router
		edge_server
		edge_storage_server
		osken-controller
		local_state_server
	)
	local removed=0
	for img in "${images[@]}"; do
		if ${DOCKER} images -q "${img}:latest" >/dev/null 2>&1; then
			# images -q prints ID or nothing; capture and check non-empty
			local id
			id=$(${DOCKER} images -q "${img}:latest" | head -n 1)
			if [[ -n "$id" ]]; then
				${DOCKER} rmi -f "${img}:latest" >/dev/null 2>&1 || true
				((++removed))
				log "Removed image: ${img}:latest"
			fi
		fi
	done
	if [[ $removed -eq 0 ]]; then
		log "No project :latest images found to remove."
	else
		log "✅ Removed ${removed} project image(s)."
	fi
}

list_dynamic_storage_volumes() {
	local docker_cli="$1"
	# Elasticity names dynamic storage nodes as edge_storage_lanX_dynY.
	${docker_cli} volume ls --format '{{.Name}}' 2>/dev/null \
		| grep -E '^edge_storage_lan[0-9]+_dyn[0-9]+-data$' || true
}

volumes_cleanup() {
	log "🧹 Removing edge_storage_server volumes"
	local DOCKER
	DOCKER=$(docker_cmd)
	if [[ -z "$DOCKER" ]]; then
		warn "Docker not installed; skipping volume removal."
		return 0
	fi
	# Base node volumes
	local volumes=(edge_storage_server_n1-data edge_storage_server_n2-data)
	local removed=0
	for vol in "${volumes[@]}"; do
		if ${DOCKER} volume inspect "$vol" >/dev/null 2>&1; then
			if ${DOCKER} volume rm "$vol" >/dev/null 2>&1; then
				log "Removed volume: $vol"
				((++removed))
			else
				warn "Failed to remove volume: $vol"
			fi
		else
			log "Volume not present, skipping: $vol"
		fi
	done
	local extra_vols
	extra_vols=$(list_dynamic_storage_volumes "$DOCKER")
	for vol in $extra_vols; do
		if ${DOCKER} volume rm "$vol" >/dev/null 2>&1; then
			log "Removed extra node volume: $vol"
			((++removed))
		else
			warn "Failed to remove extra node volume: $vol"
		fi
	done
	if [[ $removed -gt 0 ]]; then
		log "✅ Removed ${removed} volume(s)."
	fi
}

reset_cleanup() {
	log "♻️ Performing full reset (containers + edge_storage_server volumes)"
	local DOCKER
	DOCKER=$(docker_cmd)
	if [[ -z "$DOCKER" ]]; then
		warn "Docker not installed; skipping reset."
		return 0
	fi

	local containers
	if containers=$(${DOCKER} ps -aq 2>/dev/null); then
		if [[ -n "$containers" ]]; then
			${DOCKER} container rm -f $containers >/dev/null 2>&1 || warn "Failed to remove one or more containers"
		else
			log "No containers to remove."
		fi
	else
		warn "Failed to list containers for reset."
	fi

	# Ensure named storage containers are removed even if stopped
	${DOCKER} container rm -f edge_storage_server_n1 edge_storage_server_n2 >/dev/null 2>&1 || true

	# Base node volumes
	local volumes=(edge_storage_server_n1-data edge_storage_server_n2-data)
	local removed=0
	for vol in "${volumes[@]}"; do
		if ${DOCKER} volume inspect "$vol" >/dev/null 2>&1; then
			if ${DOCKER} volume rm -f "$vol" >/dev/null 2>&1; then
				log "Removed volume: $vol"
				((++removed))
			else
				warn "Failed to remove volume: $vol"
			fi
		else
			log "Volume not present, skipping: $vol"
		fi
	done
	local extra_vols
	extra_vols=$(list_dynamic_storage_volumes "$DOCKER")
	for vol in $extra_vols; do
		if ${DOCKER} volume rm -f "$vol" >/dev/null 2>&1; then
			log "Removed extra node volume: $vol"
			((++removed))
		else
			warn "Failed to remove extra node volume: $vol"
		fi
	done
	if [[ $removed -gt 0 ]]; then
			log "✅ Reset removed ${removed} edge_storage_server volume(s)."
	fi
}

MODE="all"  # all | network | docker
DO_IMAGES=false
DO_VOLUMES=false
DO_RESET=false
DO_STOP_CONTAINERS=false
MODE_SELECTED=false
IMAGE_FILTER=""
while [[ $# -gt 0 ]]; do
	case "$1" in
		-n|--network)
			MODE="network"; MODE_SELECTED=true; shift ;;
		-d|--docker)
			MODE="docker"; MODE_SELECTED=true; shift ;;
		-s|--stop-containers)
			DO_STOP_CONTAINERS=true; shift ;;
		-i|--images)
			DO_IMAGES=true; shift ;;
		-v|--volumes)
			DO_VOLUMES=true; shift ;;
		-r|--reset)
			DO_RESET=true; shift ;;
		--image-filter)
			[[ -z "${2-}" ]] && { error "--image-filter requires an argument"; exit 2; }
			IMAGE_FILTER="$2"; shift 2 ;;
		-h|--help)
			print_usage; exit 0 ;;
		*)
			error "Unknown option: $1"; print_usage; exit 2 ;;
	esac
done

if [[ "$DO_STOP_CONTAINERS" == true && "$MODE_SELECTED" == false && "$MODE" == "all" ]]; then
	MODE="none"
fi

case "$MODE" in
	none)
		;;
	all)
		network_cleanup
		docker_cleanup
		;;
	network)
		network_cleanup
		;;
	docker)
		docker_cleanup
		;;
esac

# Optional stop-only handling (can be combined with other flags)
if [[ "$DO_STOP_CONTAINERS" == true ]]; then
	stop_containers
fi

# Optional images removal
if [[ "$DO_IMAGES" == true ]]; then
    images_cleanup
fi

# Optional volume removal
if [[ "$DO_VOLUMES" == true ]]; then
	volumes_cleanup
fi

# Reset option (containers + edge_storage_server volumes)
if [[ "$DO_RESET" == true ]]; then
	reset_cleanup
fi

log "🎯 Cleanup finished ($MODE)."