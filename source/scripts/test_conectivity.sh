#!/bin/bash
set -euo pipefail

# Topology (from build_network_1.sh / build_network_2.sh):
#   LAN1 (ovs-br0, 10.0.0.0/24):
#     edge_server_n1          10.0.0.2   (gateway 10.0.0.1 via nat-router eth1)
#     edge_storage_server_n1  10.0.0.4   (gateway 10.0.0.1 via nat-router eth1)
#     aggregator_n1           10.0.0.5   (gateway 10.0.0.1 via nat-router eth1)
#   LAN2 (ovs-br1, 10.0.1.0/24):
#     edge_server_n2          10.0.1.2   (gateway 10.0.1.1 via nat-router eth2)
#     edge_storage_server_n2  10.0.1.3   (gateway 10.0.1.1 via nat-router eth2)
#     aggregator_n2           10.0.1.5   (gateway 10.0.1.1 via nat-router eth2)

PING_COUNT=${PING_COUNT:-3}
PING_TIMEOUT=${PING_TIMEOUT:-2}
DEFAULT_TARGETS=(8.8.8.8 google.com)
IFS=' ' read -r -a INTERNET_TARGETS <<< "${INTERNET_TARGETS:-${DEFAULT_TARGETS[*]}}"

LAN1_CONTAINERS=(edge_server_n1 edge_storage_server_n1 aggregator_n1)
LAN2_CONTAINERS=(edge_server_n2 edge_storage_server_n2 aggregator_n2)
LAN1_VIP=10.0.0.100
LAN2_VIP=10.0.1.100
LAN1_EDGE_IP=10.0.0.2
LAN1_MONGO_IP=10.0.0.4
LAN1_AGG_IP=10.0.0.5
LAN2_EDGE_IP=10.0.1.2
LAN2_MONGO_IP=10.0.1.4
LAN2_AGG_IP=10.0.1.5

print_usage() {
    cat <<'EOF'
Usage: ./test_conectivity.sh [lan1|lan2|cross|all]

  lan1   -> Ping between LAN1 hosts (edge_server_n1, edge_storage_server_n1) and out to the Internet.
  lan2   -> Ping between LAN2 hosts (edge_server_n2, edge_storage_server_n2) and out to the Internet.
  cross  -> Ping between LAN1 and LAN2 hosts.
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
    ping_from_container edge_server_n1 ${LAN1_MONGO_IP} "edge_storage_server_n1"
    ping_from_container edge_server_n1 ${LAN1_AGG_IP} "aggregator_n1"
    ping_from_container edge_storage_server_n1 ${LAN1_EDGE_IP} "edge_server_n1"
    ping_from_container aggregator_n1 ${LAN1_EDGE_IP} "edge_server_n1"
    ping_from_container aggregator_n1 ${LAN1_MONGO_IP} "edge_storage_server_n1"
    echo "=== LAN1 VIP connectivity ==="
    # ping_from_container edge_server_n1 ${LAN1_VIP} "LAN1 VIP"
    # ping_from_container edge_storage_server_n1 ${LAN1_VIP} "LAN1 VIP"
    echo "=== LAN1 Internet connectivity ==="
    # ping_internet_targets edge_server_n1
    # ping_internet_targets edge_storage_server_n1
}

run_lan2_tests() {
    echo "=== LAN2 connectivity ==="
    ping_from_container edge_server_n2 ${LAN2_MONGO_IP} "edge_storage_server_n2"
    ping_from_container edge_server_n2 ${LAN2_AGG_IP} "aggregator_n2"
    ping_from_container edge_storage_server_n2 ${LAN2_EDGE_IP} "edge_server_n2"
    ping_from_container aggregator_n2 ${LAN2_EDGE_IP} "edge_server_n2"
    ping_from_container aggregator_n2 ${LAN2_MONGO_IP} "edge_storage_server_n2"
    echo "=== LAN2 VIP connectivity ==="
    # ping_from_container edge_server_n2 ${LAN2_VIP} "LAN2 VIP"
    # ping_from_container edge_storage_server_n2 ${LAN2_VIP} "LAN2 VIP"
    echo "=== LAN2 Internet connectivity ==="
    # ping_internet_targets edge_server_n2
    # ping_internet_targets edge_storage_server_n2
}

run_cross_tests() {
    echo "=== Cross-LAN connectivity ==="
    ping_from_container edge_server_n1 ${LAN2_EDGE_IP} "LAN2 edge_server_n2"
    ping_from_container edge_server_n1 ${LAN2_MONGO_IP} "LAN2 mongodb_n2"
    ping_from_container edge_server_n1 ${LAN2_AGG_IP} "LAN2 aggregator_n2"
    ping_from_container edge_server_n2 ${LAN1_EDGE_IP} "LAN1 edge_server_n1"
    ping_from_container edge_server_n2 ${LAN1_MONGO_IP} "LAN1 mongodb_n1"
    ping_from_container edge_server_n2 ${LAN1_AGG_IP} "LAN1 aggregator_n1"
    echo "=== Cross-LAN VIP connectivity ==="
    # ping_from_container edge_server_n1 ${LAN1_VIP} "LAN1 VIP"
    # ping_from_container edge_server_n2 ${LAN2_VIP} "LAN2 VIP"
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
