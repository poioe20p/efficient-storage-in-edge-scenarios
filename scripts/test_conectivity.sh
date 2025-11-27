#!/bin/bash
set -euo pipefail

PING_COUNT=${PING_COUNT:-3}
PING_TIMEOUT=${PING_TIMEOUT:-2}
DEFAULT_TARGETS=(8.8.8.8 google.com)
IFS=' ' read -r -a INTERNET_TARGETS <<< "${INTERNET_TARGETS:-${DEFAULT_TARGETS[*]}}"

LAN1_CONTAINERS=(container1 container2)
LAN2_CONTAINERS=(container3 container4)

print_usage() {
    cat <<'EOF'
Usage: ./test_conectivity.sh [lan1|lan2|cross|all]

  lan1   -> Ping between LAN1 hosts (container1, container2) and out to the Internet.
  lan2   -> Ping between LAN2 hosts (container3, container4) and out to the Internet.
  cross  -> Ping between LAN1 and LAN2 hosts as well as shard nodes.
  all    -> Run lan1, lan2, and cross suites sequentially.

Environment:
    PING_COUNT / PING_TIMEOUT   -> Adjust ping aggressiveness (defaults 3 / 2s).
    INTERNET_TARGETS            -> Space-separated list of IPs/hosts (default "8.8.8.8 google.com").

If no argument is supplied, you will be prompted to choose an option.
EOF
}

ensure_container() {
    local name=$1
    if ! docker ps --format '{{.Names}}' | grep -Fxq "$name"; then
        echo "Container '$name' is not running. Please start the lab setup before running tests." >&2
        exit 1
    fi
}

ping_from_container() {
    local source=$1
    local target=$2
    local label=$3
    ensure_container "$source"
    echo "[${source}] -> ${label} (${target})"
    if docker exec "$source" ping -c ${PING_COUNT} -W ${PING_TIMEOUT} "$target" >/dev/null; then
        echo "  ✅ Reachable"
    else
        echo "  ❌ Failed" >&2
    fi
}

ping_internet_targets() {
    local source=$1
    for target in "${INTERNET_TARGETS[@]}"; do
        ping_from_container "$source" "$target" "Internet (${target})"
    done
}

run_lan1_tests() {
    echo "=== LAN1 connectivity ==="
    ping_from_container container1 10.0.0.3 "container2"
    ping_from_container container2 10.0.0.4 "mongodb-n1"
    ping_internet_targets container1
    ping_internet_targets container2
}

run_lan2_tests() {
    echo "=== LAN2 connectivity ==="
    ping_from_container container3 10.0.1.3 "container4"
    ping_from_container container4 10.0.1.4 "mongodb-n2"
    ping_internet_targets container3
    ping_internet_targets container4
}

run_cross_tests() {
    echo "=== Cross-LAN connectivity ==="
    ping_from_container container1 10.0.1.2 "LAN2 container3"
    ping_from_container container1 10.0.1.4 "LAN2 mongodb-n2"
    ping_from_container container3 10.0.0.2 "LAN1 container1"
    ping_from_container container3 10.0.0.4 "LAN1 mongodb-n1"
}

main() {
    local choice=${1:-}
    if [[ -z "$choice" ]]; then
        print_usage
        read -rp "Select test suite: " choice
    fi

    case "$choice" in
        lan1)
            run_lan1_tests
            ;;
        lan2)
            run_lan2_tests
            ;;
        cross|lan1lan2|lan2lan1)
            run_cross_tests
            ;;
        all)
            run_lan1_tests
            run_lan2_tests
            run_cross_tests
            ;;
        -h|--help|help)
            print_usage
            ;;
        *)
            echo "Unknown option '$choice'." >&2
            print_usage
            exit 1
            ;;
    esac
}

main "$@"
