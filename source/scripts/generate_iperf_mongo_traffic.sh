#!/usr/bin/env bash
set -euo pipefail

# Generates traffic to the MongoDB shard containers using iperf3.
# Note: iperf3 generates throughput traffic (TCP/UDP), not ICMP ping.
# Defaults target:
#   LAN1 MongoDB (mongodb-n1): MAC 00:00:00:00:00:04, IP 10.0.0.4
#   LAN2 MongoDB (mongodb-n2): MAC 00:00:00:00:00:07, IP 10.0.1.4

DURATION_SEC=10
PARALLEL_STREAMS=1
SERVER_PORT=5201
USE_UDP=0
UDP_BANDWIDTH=10M

LAN1_CLIENT_CONTAINER=container1
LAN2_CLIENT_CONTAINER=container3

LAN1_MONGO_CONTAINER=mongodb-n1
LAN2_MONGO_CONTAINER=mongodb-n2

LAN1_MONGO_IP=10.0.0.4
LAN2_MONGO_IP=10.0.1.4

usage() {
  cat <<'EOF'
Usage:
  ./source/scripts/generate_iperf_mongo_traffic.sh [options]

Options:
  --duration <sec>           Seconds per iperf run (default: 10)
  --streams <n>              iperf3 -P value for TCP (default: 1)
  --port <port>              iperf3 server port (default: 5201)
  --udp                       Use UDP (-u). If set, --streams is ignored.
  --bandwidth <rate>         UDP target bandwidth (-b) (default: 10M)

  --lan1-client <container>  Client container in LAN1 (default: container1)
  --lan2-client <container>  Client container in LAN2 (default: container3)

  --lan1-mongo <container>   MongoDB container in LAN1 (default: mongodb-n1)
  --lan2-mongo <container>   MongoDB container in LAN2 (default: mongodb-n2)
  --lan1-ip <ip>             MongoDB IP in LAN1 (default: 10.0.0.4)
  --lan2-ip <ip>             MongoDB IP in LAN2 (default: 10.0.1.4)

  -h, --help                 Show help

Examples:
  ./source/scripts/generate_iperf_mongo_traffic.sh --duration 30 --streams 4
  ./source/scripts/generate_iperf_mongo_traffic.sh --udp --bandwidth 50M
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

is_uint() {
  [[ "$1" =~ ^[0-9]+$ ]]
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      -h|--help)
        usage
        exit 0
        ;;
      --duration)
        [[ $# -ge 2 ]] || die "--duration requires a value"
        DURATION_SEC="$2"
        shift 2
        ;;
      --streams)
        [[ $# -ge 2 ]] || die "--streams requires a value"
        PARALLEL_STREAMS="$2"
        shift 2
        ;;
      --port)
        [[ $# -ge 2 ]] || die "--port requires a value"
        SERVER_PORT="$2"
        shift 2
        ;;
      --udp)
        USE_UDP=1
        shift
        ;;
      --bandwidth)
        [[ $# -ge 2 ]] || die "--bandwidth requires a value"
        UDP_BANDWIDTH="$2"
        shift 2
        ;;
      --lan1-client)
        [[ $# -ge 2 ]] || die "--lan1-client requires a value"
        LAN1_CLIENT_CONTAINER="$2"
        shift 2
        ;;
      --lan2-client)
        [[ $# -ge 2 ]] || die "--lan2-client requires a value"
        LAN2_CLIENT_CONTAINER="$2"
        shift 2
        ;;
      --lan1-mongo)
        [[ $# -ge 2 ]] || die "--lan1-mongo requires a value"
        LAN1_MONGO_CONTAINER="$2"
        shift 2
        ;;
      --lan2-mongo)
        [[ $# -ge 2 ]] || die "--lan2-mongo requires a value"
        LAN2_MONGO_CONTAINER="$2"
        shift 2
        ;;
      --lan1-ip)
        [[ $# -ge 2 ]] || die "--lan1-ip requires a value"
        LAN1_MONGO_IP="$2"
        shift 2
        ;;
      --lan2-ip)
        [[ $# -ge 2 ]] || die "--lan2-ip requires a value"
        LAN2_MONGO_IP="$2"
        shift 2
        ;;
      *)
        die "Unknown argument: $1 (use --help)"
        ;;
    esac
  done

  is_uint "$DURATION_SEC" || die "--duration must be an integer (got: $DURATION_SEC)"
  is_uint "$SERVER_PORT" || die "--port must be an integer (got: $SERVER_PORT)"
  if [[ "$USE_UDP" != "1" ]]; then
    is_uint "$PARALLEL_STREAMS" || die "--streams must be an integer (got: $PARALLEL_STREAMS)"
    [[ "$PARALLEL_STREAMS" -ge 1 ]] || die "--streams must be >= 1"
  fi
  [[ "$DURATION_SEC" -ge 1 ]] || die "--duration must be >= 1"
}

require_cmd() {
  local cmd=$1
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "ERROR: missing required command: $cmd" >&2
    exit 1
  }
}

ensure_container_running() {
  local name=$1
  local running

  if ! running="$(docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null)"; then
    echo "ERROR: container not found: $name" >&2
    exit 1
  fi

  if [[ "$running" != "true" ]]; then
    echo "ERROR: container is not running: $name" >&2
    exit 1
  fi
}

container_has_iperf3() {
  local name=$1
  docker exec "$name" sh -lc 'command -v iperf3 >/dev/null 2>&1'
}

ensure_iperf3_in_container() {
  local name=$1
  if container_has_iperf3 "$name"; then
    return 0
  fi

  echo "ERROR: iperf3 is not installed in container: $name" >&2
  echo "Build the images with iperf3 baked in (e.g. ./source/scripts/build_images.sh) and recreate containers." >&2
  exit 1
}

start_iperf3_server() {
  local name=$1
  local port=$2

  # Kill previous iperf3 servers (best-effort).
  docker exec "$name" sh -lc "pkill -f 'iperf3 -s' >/dev/null 2>&1 || true"

  # -D daemonizes; -p selects a fixed port.
  docker exec "$name" sh -lc "iperf3 -s -D -p $port"
}

stop_iperf3_server() {
  local name=$1
  docker exec "$name" sh -lc "pkill -f 'iperf3 -s' >/dev/null 2>&1 || true"
}

run_iperf3_client() {
  local client_container=$1
  local server_ip=$2
  local port=$3

  local args=("-c" "$server_ip" "-p" "$port" "-t" "$DURATION_SEC")

  if [[ "$USE_UDP" == "1" ]]; then
    args+=("-u" "-b" "$UDP_BANDWIDTH")
  else
    args+=("-P" "$PARALLEL_STREAMS")
  fi

  docker exec "$client_container" iperf3 "${args[@]}"
}

main() {
  parse_args "$@"

  require_cmd docker

  ensure_container_running "$LAN1_MONGO_CONTAINER"
  ensure_container_running "$LAN2_MONGO_CONTAINER"
  ensure_container_running "$LAN1_CLIENT_CONTAINER"
  ensure_container_running "$LAN2_CLIENT_CONTAINER"

  ensure_iperf3_in_container "$LAN1_MONGO_CONTAINER"
  ensure_iperf3_in_container "$LAN2_MONGO_CONTAINER"
  ensure_iperf3_in_container "$LAN1_CLIENT_CONTAINER"
  ensure_iperf3_in_container "$LAN2_CLIENT_CONTAINER"

  echo "Starting iperf3 servers on MongoDB containers..." >&2
  start_iperf3_server "$LAN1_MONGO_CONTAINER" "$SERVER_PORT"
  start_iperf3_server "$LAN2_MONGO_CONTAINER" "$SERVER_PORT"

  cleanup() {
    stop_iperf3_server "$LAN1_MONGO_CONTAINER" || true
    stop_iperf3_server "$LAN2_MONGO_CONTAINER" || true
  }
  trap cleanup EXIT INT TERM

  echo "Running iperf3 clients:" >&2
  echo "  LAN1: $LAN1_CLIENT_CONTAINER -> $LAN1_MONGO_IP (mongodb MAC 00:00:00:00:00:04)" >&2
  echo "  LAN2: $LAN2_CLIENT_CONTAINER -> $LAN2_MONGO_IP (mongodb MAC 00:00:00:00:00:07)" >&2

  # Run both at the same time to generate concurrent load.
  run_iperf3_client "$LAN1_CLIENT_CONTAINER" "$LAN1_MONGO_IP" "$SERVER_PORT" &
  pid1=$!
  run_iperf3_client "$LAN2_CLIENT_CONTAINER" "$LAN2_MONGO_IP" "$SERVER_PORT" &
  pid2=$!

  wait "$pid1"
  wait "$pid2"

  echo "Done." >&2
}

main "$@"
