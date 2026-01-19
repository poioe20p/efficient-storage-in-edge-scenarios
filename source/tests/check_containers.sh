#!/bin/bash

# Validate that the lab containers expected from build_setup.sh are running.

set -euo pipefail

print_usage() {
  cat <<'EOF'
Usage: ./check_containers.sh

Checks that the containers expected from the lab setup are running.

Environment:
  REQUIRE_OSKEN=1   Also require os-ken controller containers (osken, osken_2).
EOF
}

require_docker() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "docker is not available in PATH." >&2
    exit 1
  fi
}

container_running() {
  local name=$1
  docker ps --format '{{.Names}}' | grep -Fxq "$name"
}

main() {
  if [[ "${1:-}" =~ ^(-h|--help|help)$ ]]; then
    print_usage
    exit 0
  fi

  require_docker

  local -a required=(
    ovs nat-router mongodb-config-server mongodb-router mongodb-n1 mongodb-n2
    container1 container2 container3 container4 container5
  )

  if [[ "${REQUIRE_OSKEN:-0}" == "1" ]]; then
    required+=(osken osken_2)
  fi

  local missing=0
  for name in "${required[@]}"; do
    if ! container_running "$name"; then
      echo "Missing container: $name" >&2
      missing=1
    fi
  done

  if [[ $missing -ne 0 ]]; then
    echo "One or more required containers are not running." >&2
    echo "Running containers:" >&2
    docker ps --format '  - {{.Names}}'
    exit 1
  fi

  echo "All required containers are running."
}

main "$@"
