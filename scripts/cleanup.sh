#!/usr/bin/env bash

# Robust cleanup utility for network artifacts and Docker resources.
#
# Usage:
#   ./cleanup.sh            # Clean everything (network + docker)
#   ./cleanup.sh -n|--network  # Clean only network artifacts
#   ./cleanup.sh -d|--docker   # Clean only Docker containers (and related)
#   ./cleanup.sh --images      # Also remove project images tagged :latest
#   NAT_IFACE=enp0s9 NAT_SUBNET=192.168.100.0/24 ./cleanup.sh   # Override defaults
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
	    --images     Remove project images tagged :latest (in addition to selected mode)
	-h, --help       Show this help

Environment:
	NAT_IFACE   Network interface for NAT rule (default: $NAT_IFACE)
	NAT_SUBNET  Subnet for NAT rule deletion (default: $NAT_SUBNET)
EOF
}

# Early help: if first arg is -h/--help, print usage and exit 0
if [[ ${1-} == "-h" || ${1-} == "--help" ]]; then
		print_usage
		exit 0
fi

# Defaults (can be overridden via env)
NAT_IFACE=${NAT_IFACE:-enp0s9}
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
	local veths=(veth1 veth2 veth3 veth4 veth5)
	for v in "${veths[@]}"; do
		ip_safe_del_link "$v"
	done

	# Flush host-side IP config (best-effort)
	if $SUDO ip link show veth4 >/dev/null 2>&1; then
		$SUDO ip addr flush dev veth4 || warn "Failed to flush addresses on veth4"
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

	# Stop and remove all containers
	local cids
	if cids=$(${DOCKER} ps -aq 2>/dev/null); then
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
		ubuntu-host-1
		ubuntu-host-2
		ubuntu-mongodb
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

MODE="all"  # all | network | docker
DO_IMAGES=false
while [[ $# -gt 0 ]]; do
	case "$1" in
		-n|--network)
			MODE="network"; shift ;;
		-d|--docker)
			MODE="docker"; shift ;;
		-i|--images)
			DO_IMAGES=true; shift ;;
		-h|--help)
			print_usage; exit 0 ;;
		*)
			error "Unknown option: $1"; print_usage; exit 2 ;;
	esac
done

case "$MODE" in
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

# Optional images removal
if [[ "$DO_IMAGES" == true ]]; then
    images_cleanup
fi

log "🎯 Cleanup finished ($MODE)."