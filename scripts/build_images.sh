#!/bin/bash

# Ensure we're running under bash even if invoked via sh
if [ -z "${BASH_VERSION:-}" ]; then
	exec bash "$0" "$@"
fi

# Robust, explicit Docker image builder with error handling.
#
# Usage:
#   ./build_images.sh                # Build all images
#   ./build_images.sh OVS            # Build only the OVS image (by directory name)
#   ./build_images.sh ovs-container  # Build only the OVS image (by tag)
#   ./build_images.sh OVS ubuntu-host ubuntu-mongodb  # Build selected images
#
# Notes:
# - The script auto-detects the project root based on its own location.
# - It will try to use "docker" directly if you have permission; otherwise it will use "sudo docker" when available.

set -Eeuo pipefail
IFS=$'\n\t'

### Error handling and logging
SCRIPT_NAME=$(basename "$0")

log()   { printf '[INFO] %s\n' "$*"; }
warn()  { printf '[WARN] %s\n' "$*" 1>&2; }
error() { printf '[ERROR] %s\n' "$*" 1>&2; }

cleanup() {
	local exit_code=$?
	if [[ $exit_code -ne 0 ]]; then
		error "A failure occurred (exit $exit_code). See logs above."
	fi
}

trap 'error "Command failed at line ${LINENO}: ${BASH_COMMAND}"' ERR
trap cleanup EXIT

print_usage() {
		cat <<EOF
Usage:
	./build_images.sh                # Build all images
	./build_images.sh OVS            # Build only the OVS image (by directory name)
	./build_images.sh ovs-container  # Build only the OVS image (by tag)
	./build_images.sh OVS ubuntu-host ubuntu-mongodb  # Build selected images

Options:
	-r, --reset NAME   Remove the running/stopped container associated with NAME before rebuilding.
	-h, --help         Show this help message and exit.

Notes:
- The script auto-detects the project root based on its own location.
- It will try to use "docker" directly if you have permission; otherwise it will use "sudo docker" when available.
EOF
}

RESET_TARGETS=()
POSITIONAL_ARGS=()

while [[ $# -gt 0 ]]; do
	case "$1" in
		-h|--help)
			print_usage
			exit 0
			;;
		-r|--reset)
			if [[ $# -lt 2 ]]; then
				error "Option $1 requires a container or image name argument."
				exit 1
			fi
			RESET_TARGETS+=("$2")
			shift 2
			;;
		--)
			shift
			POSITIONAL_ARGS+=("$@")
			break
			;;
		-*)
			error "Unknown option: $1"
			print_usage
			exit 1
			;;
		*)
			POSITIONAL_ARGS+=("$1")
			shift
			;;
	esac
done

set -- "${POSITIONAL_ARGS[@]}"

### Resolve paths (script lives in repo/scripts; docker dir is repo/docker)
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
DOCKER_DIR="${REPO_ROOT}/docker"
MONGO_ENV_FILE="${REPO_ROOT}/.env-mongo"

# Export variables in MONGO_ENV_FILE for use as build args if needed
if [[ -f "$MONGO_ENV_FILE" ]]; then
	log "Loading MongoDB environment from: $MONGO_ENV_FILE"
	# Export all simple KEY=VALUE entries from the env file
	set -a
	source "$MONGO_ENV_FILE"
	set +a
else
	log "MongoDB env file not found at: $MONGO_ENV_FILE"
	log "MongoDB image will build, but container may start without authentication!"
fi


[[ -d "$DOCKER_DIR" ]] || {
	error "Docker directory not found at: $DOCKER_DIR"
	error "Ensure the repository structure is intact."
	exit 1
}

### Requirements checks
require_command() {
	command -v "$1" >/dev/null 2>&1 || { error "Required command not found: $1"; exit 127; }
}

require_command docker

# Decide how to call Docker (directly or via sudo)
docker_cmd() {
	# If we're root, use docker directly
	if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
		echo docker
		return
	fi
	# If user is in docker group, use docker directly
	if command -v id >/dev/null 2>&1 && id -nG 2>/dev/null | grep -qw docker; then
		echo docker
		return
	fi
	# Else try sudo if present
	if command -v sudo >/dev/null 2>&1; then
		echo "sudo docker"
		return
	fi
	# Fallback: likely to fail due to permissions, but be explicit
	warn "You may not have permission to run Docker without sudo."
	echo docker
}

DOCKER=$(docker_cmd)

log "Building images..."
log "Repository root: $REPO_ROOT"
log "Docker build context base: $DOCKER_DIR"
log "Docker command: $DOCKER"

declare -A CONTAINER_NAME_MAP=(
	["ovs"]="ovs"
	["ovs-container"]="ovs"
	# ["ryu"]="ryu"
	# ["ryu-controller"]="ryu"
	["os-ken"]="osken"
	["osken-controller"]="osken"
	["ubuntu-host"]="container1"
	["ubuntu-host"]="container2"
	["ubuntu-nat-router"]="nat-router"
	["ubuntu-mongodb"]="mongodb"
	["container1"]="container1"
	["container2"]="container2"
	["nat-router"]="nat-router"
	["mongodb"]="mongodb"
	["mongodb-config-server"]="mongodb-config-server"
	["mongodb-router"]="mongodb-router"
	["ubuntu-mongodb-router"]="mongodb-router"
)

resolve_container_name() {
	local dir_l=${1,,}
	local tag_l=${2,,}
	if [[ -n ${CONTAINER_NAME_MAP[$dir_l]:-} ]]; then
		printf '%s' "${CONTAINER_NAME_MAP[$dir_l]}"
		return
	fi
	if [[ -n ${CONTAINER_NAME_MAP[$tag_l]:-} ]]; then
		printf '%s' "${CONTAINER_NAME_MAP[$tag_l]}"
		return
	fi
	printf '%s' ""
}

matches_reset_target() {
	local target_l=${1,,}
	local dir_l=${2,,}
	local tag_l=${3,,}
	local container_l=${4,,}
	if [[ $target_l == "$dir_l" || $target_l == "$tag_l" ]]; then
		return 0
	fi
	if [[ -n $container_l && $target_l == "$container_l" ]]; then
		return 0
	fi
	return 1
}

reset_container() {
	local target="$1"
	local container_name="$2"
	if [[ -z $container_name ]]; then
		container_name=${target,,}
	fi
	if ${DOCKER} ps -a --format '{{.Names}}' | grep -Fxq "$container_name"; then
		log "Reset requested for '$target': removing container '$container_name'..."
		${DOCKER} rm -f "$container_name" >/dev/null
		log "Container '$container_name' removed."
	else
		log "Reset requested for '$target', but no container named '$container_name' was found."
	fi
}

declare -A RESET_APPLIED=()

### Define images: "directory:tag"
IMAGES=(
	"OVS:ovs-container"
	"ubuntu-nat-router:ubuntu-nat-router"
	"ubuntu-host:ubuntu-host"
	"ubuntu-mongodb:ubuntu-mongodb"
	"os-ken:osken-controller"
	"ubuntu-mongodb-configsvr:mongodb-config-server"
	"ubuntu-mongodb-router:mongodb-router"
)

### Build helper
build_image() {
	local dir="$1"
	local tag="$2"
	local ctx="$DOCKER_DIR/$dir"
	local dockerfile="$ctx/Dockerfile"

	[[ -d "$ctx" ]] || { error "Build directory not found: $ctx"; return 2; }
	[[ -f "$dockerfile" ]] || { error "Dockerfile not found: $dockerfile"; return 2; }

	log "Building image '$tag' from '$dir'..."
	# You can add build args here if needed, e.g., --pull or --no-cache via env flags
	${DOCKER} build -t "$tag" -f "$dockerfile" "$ctx"
	log "Image built: $tag"
}

### Selection logic: if args provided, filter by dir or tag; else build all
should_build() {
	# Returns 0 if the current image matches selection; 1 otherwise
	local dir="$1"; shift
	local tag="$1"; shift

	# If no selection, build all
	[[ $# -eq 0 ]] && return 0

	local sel
	for sel in "$@"; do
		if [[ "$sel" == "$dir" || "$sel" == "$tag" ]]; then
			return 0
		fi
	done
	return 1
}

SELECTION=("$@")

build_count=0
for entry in "${IMAGES[@]}"; do
	IFS=":" read -r dir tag <<<"$entry"
	if should_build "$dir" "$tag" "${SELECTION[@]}"; then
		container_name=$(resolve_container_name "$dir" "$tag")
		if ((${#RESET_TARGETS[@]})); then
			for idx in "${!RESET_TARGETS[@]}"; do
				target=${RESET_TARGETS[$idx]}
				if [[ -n ${RESET_APPLIED[$idx]:-} ]]; then
					continue
				fi
				if matches_reset_target "$target" "$dir" "$tag" "$container_name"; then
					reset_container "$target" "$container_name"
					RESET_APPLIED[$idx]=1
				fi
			done
		fi
		build_image "$dir" "$tag"
		# Use pre-increment to avoid set -e exiting when previous value is 0
		((++build_count))
	else
		log "Skipping $dir ($tag)"
	fi
done

if ((${#RESET_TARGETS[@]})); then
	for idx in "${!RESET_TARGETS[@]}"; do
		if [[ -z ${RESET_APPLIED[$idx]:-} ]]; then
			warn "Reset requested for '${RESET_TARGETS[$idx]}', but no matching image was built."
		fi
	done
fi

if [[ $build_count -eq 0 ]]; then
	warn "No images selected to build. Check your arguments."
	exit 0
fi

log "All requested images built ($build_count). Listing local images:"
${DOCKER} images
