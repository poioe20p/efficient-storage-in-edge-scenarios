#!/usr/bin/env bash
# Enhanced connectivity test script for multi-network setups
# Usage:
#   ./test_connectivity.sh -n lan1           # test only LAN1 (10.0.0.0/24)
#   ./test_connectivity.sh -n lan2           # test only LAN2 (10.0.1.0/24)
#   ./test_connectivity.sh -n lan1 lan2      # test both LANs and cross-network connectivity
#   ./test_connectivity.sh --help            # show help

set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_NAME=$(basename "$0")

# Network definitions
LAN1_CONTAINERS=(container1 container2 mongodb-n1)
LAN1_IPS=(10.0.0.2 10.0.0.3 10.0.0.4)
LAN1_GW=10.0.0.1

LAN2_CONTAINERS=(container3 container4 mongodb-n2)
LAN2_IPS=(10.0.1.2 10.0.1.3 10.0.1.4)
LAN2_GW=10.0.1.1

INTERNET_HOST=${INTERNET_HOST:-www.google.com}
PING_COUNT=${PING_COUNT:-2}
PING_TIMEOUT=${PING_TIMEOUT:-2}

log()  { printf '[INFO] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*" 1>&2; }
err()  { printf '[ERROR] %s\n' "$*" 1>&2; }

print_usage() {
  cat <<EOF
Usage: $SCRIPT_NAME -n lan1|lan2 [lan1 lan2]

Options:
  -n, --network lan1        Test LAN1 only (10.0.0.0/24)
  -n, --network lan2        Test LAN2 only (10.0.1.0/24)
  -n, --network lan1 lan2   Test both LANs and cross-network connectivity
  --help                    Show this help

Environment overrides:
  INTERNET_HOST (default: ${INTERNET_HOST})
  PING_COUNT (default: ${PING_COUNT}), PING_TIMEOUT (default: ${PING_TIMEOUT})
EOF
}

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { err "Required command not found: $1"; exit 127; }
}

require_container() {
  local name="$1"
  if ! docker ps --format '{{.Names}}' | grep -Fxq "$name"; then
    err "Container '$name' is not running."
    exit 1
  fi
}

exec_in() {
  local name="$1"; shift
  docker exec "$name" bash -lc "$*"
}

has_cmd_in() {
  local name="$1"; shift
  exec_in "$name" "command -v $* >/dev/null 2>&1"
}

ping_from_to() {
  local from="$1" ip="$2" label="$3"
  if has_cmd_in "$from" ping; then
    if exec_in "$from" "ping -c ${PING_COUNT} -W ${PING_TIMEOUT} ${ip} >/dev/null"; then
      log "${from}: ping to ${label} (${ip}) OK"
      return 0
    else
      err "${from}: ping to ${label} (${ip}) FAILED"
      return 1
    fi
  else
    warn "${from}: 'ping' not available; skipping ICMP test to ${label} (${ip})"
    return 2
  fi
}

internet_test() {
  local from="$1" host="$2"
  local ok=1
  if has_cmd_in "$from" ping; then
    if exec_in "$from" "ping -c ${PING_COUNT} -W ${PING_TIMEOUT} ${host} >/dev/null"; then
      log "${from}: internet ICMP to ${host} OK"
      ok=0
    else
      warn "${from}: internet ICMP to ${host} failed; trying HTTP"
    fi
  fi
  if [[ $ok -ne 0 ]]; then
    if has_cmd_in "$from" curl; then
      if exec_in "$from" "curl -Is --max-time 5 https://${host} >/dev/null"; then
        log "${from}: internet HTTP to https://${host} OK"
        ok=0
      else
        err "${from}: internet HTTP to https://${host} FAILED"
      fi
    else
      warn "${from}: 'curl' not available; skipping HTTP test"
    fi
  fi
  return $ok
}

test_lan() {
  local containers=("${!1}")
  local ips=("${!2}")
  local gw="$3"
  local label="$4"
  local failures=0
  # Intra-LAN tests
  for i in {0..2}; do
    require_container "${containers[$i]}"
    for j in {0..2}; do
      if [[ $i -ne $j ]]; then
        ping_from_to "${containers[$i]}" "${ips[$j]}" "${containers[$j]}" || ((failures++))
      fi
    done
    ping_from_to "${containers[$i]}" "$gw" "gateway" || ((failures++))
    internet_test "${containers[$i]}" "$INTERNET_HOST" || ((failures++))
  done
  return $failures
}

test_cross_lan() {
  local c1=("${LAN1_CONTAINERS[@]}")
  local i1=("${LAN1_IPS[@]}")
  local c2=("${LAN2_CONTAINERS[@]}")
  local i2=("${LAN2_IPS[@]}")
  local failures=0
  # Each LAN1 container pings each LAN2 IP
  for i in {0..2}; do
    require_container "${c1[$i]}"
    for j in {0..2}; do
      require_container "${c2[$j]}"
      ping_from_to "${c1[$i]}" "${i2[$j]}" "${c2[$j]}" || ((failures++))
      ping_from_to "${c2[$j]}" "${i1[$i]}" "${c1[$i]}" || ((failures++))
    done
  done
  return $failures
}

main() {
  require_cmd docker
  if [[ $# -eq 0 ]]; then
    print_usage
    exit 1
  fi
  local networks=()
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -n|--network)
        shift
        while [[ $# -gt 0 && ! "$1" =~ ^- ]]; do
          networks+=("$1")
          shift
        done
        ;;
      --help|-h)
        print_usage
        exit 0
        ;;
      *)
        err "Unknown argument: $1"
        print_usage
        exit 2
        ;;
    esac
  done
  if [[ ${#networks[@]} -eq 0 ]]; then
    err "No network specified."
    print_usage
    exit 2
  fi
  local failures=0
  for net in "${networks[@]}"; do
    case "$net" in
      lan1)
        log "Testing LAN1 (10.0.0.0/24) connectivity..."
        test_lan LAN1_CONTAINERS[@] LAN1_IPS[@] "$LAN1_GW" "LAN1" || ((failures++))
        ;;
      lan2)
        log "Testing LAN2 (10.0.1.0/24) connectivity..."
        test_lan LAN2_CONTAINERS[@] LAN2_IPS[@] "$LAN2_GW" "LAN2" || ((failures++))
        ;;
      *)
        err "Unknown network: $net"
        print_usage
        exit 2
        ;;
    esac
  done
  if [[ " ${networks[@]} " =~ "lan1" ]] && [[ " ${networks[@]} " =~ "lan2" ]]; then
    log "Testing cross-LAN connectivity (LAN1 <-> LAN2)..."
    test_cross_lan || ((failures++))
  fi
  if [[ $failures -eq 0 ]]; then
    log "✅ All connectivity checks passed."
    exit 0
  else
    err "❌ Connectivity checks failed: ${failures} issue(s) detected."
    exit 1
  fi
}

main "$@"
