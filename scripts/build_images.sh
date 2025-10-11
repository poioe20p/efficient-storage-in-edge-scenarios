#!/usr/bin/env bash

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
#   ./build_images.sh OVS ubuntu-host-1 ubuntu-mongodb  # Build selected images
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
	./build_images.sh OVS ubuntu-host-1 ubuntu-mongodb  # Build selected images

Notes:
- The script auto-detects the project root based on its own location.
- It will try to use "docker" directly if you have permission; otherwise it will use "sudo docker" when available.
EOF
}

# Early help: if first arg is -h/--help, print usage and exit 0
if [[ ${1-} == "-h" || ${1-} == "--help" ]]; then
		print_usage
		exit 0
fi

### Resolve paths (script lives in repo/scripts; docker dir is repo/docker)
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "${SCRIPT_DIR}/.." && pwd)
DOCKER_DIR="${REPO_ROOT}/docker"

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

### Define images: "directory:tag"
IMAGES=(
	"OVS:ovs-container"
	"ubuntu-nat-router:ubuntu-nat-router"
	"ubuntu-host-1:ubuntu-host-1"
	"ubuntu-host-2:ubuntu-host-2"
	"ubuntu-mongodb:ubuntu-mongodb"
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
	${DOCKER} build -t "$tag" "$ctx"
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
		build_image "$dir" "$tag"
		# Use pre-increment to avoid set -e exiting when previous value is 0
		((++build_count))
	else
		log "Skipping $dir ($tag)"
	fi
done

if [[ $build_count -eq 0 ]]; then
	warn "No images selected to build. Check your arguments."
	exit 0
fi

log "All requested images built ($build_count). Listing local images:"
${DOCKER} images
