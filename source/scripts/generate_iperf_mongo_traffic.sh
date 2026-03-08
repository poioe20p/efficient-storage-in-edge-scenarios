#!/usr/bin/env bash
set -euo pipefail

# Generates traffic to the MongoDB shard containers using iperf3.
# Note: iperf3 generates throughput traffic (TCP/UDP), not ICMP ping.
# Defaults target:
#   LAN1 VIP: 10.0.0.100
#   LAN2 VIP: 10.0.1.100

DURATION_SEC=10
PARALLEL_STREAMS=1
SERVER_PORT=5201
AUTO_PORT=1
USE_UDP=0
UDP_BANDWIDTH=10M

# Safety: upper bound for blocking docker exec calls.
# Applied on the host side (this script), so it does not depend on utilities
# inside containers. 0 disables timeouts.
DOCKER_EXEC_TIMEOUT_SEC=0

# When multiple clients run concurrently, reusing the same server port can make
# iperf3 reject sessions (single-test server instances) and clients may surface
# confusing errors like "unable to send control message".
# Default behavior: if more than one client job is scheduled, use a unique port
# per job (base port + job index) and start matching servers on all backends.
FORCE_SINGLE_PORT=0

LAN1_CLIENTS_RAW=edge_server_n1
LAN2_CLIENTS_RAW=edge_server_n2

# Track whether the user explicitly set LAN client lists.
# If they set only one side, disable the other side (instead of using defaults)
# to avoid generating unintended traffic.
LAN1_CLIENTS_SET=0
LAN2_CLIENTS_SET=0

LAN1_MONGO_CONTAINER=mongodb_n1
LAN2_MONGO_CONTAINER=mongodb_n2

LAN1_MONGO_IP=10.0.0.100
LAN2_MONGO_IP=10.0.1.100

# Static mapping for client containers -> IPs, as configured by:
# - source/scripts/build_network_1.sh (LAN1)
# - source/scripts/build_network_2.sh (LAN2)
# Note: containers use --network none, so Docker can't report these IPs.
declare -A CLIENT_IP_BY_CONTAINER=(
  [edge_server_n1]="10.0.0.2"
  [mongodb_n1]="10.0.0.4"
  [edge_server_n2]="10.0.1.2"
  [mongodb_n2]="10.0.1.3"
)

format_clients_with_ips() {
  local -n clients=$1
  local -a formatted=()

  local c
  for c in "${clients[@]}"; do
    local ip="${CLIENT_IP_BY_CONTAINER[$c]-}"
    if [[ -n "$ip" ]]; then
      formatted+=("${c}(${ip})")
    else
      formatted+=("$c")
    fi
  done

  printf '%s' "${formatted[*]}"
}

usage() {
  cat <<'EOF'
Usage:
  ./source/scripts/generate_iperf_mongo_traffic.sh [options]

Options:
  --duration <sec>           Seconds per iperf run (default: 10)
  --streams <n>              iperf3 -P value for TCP (default: 1 stream per client connection)
  --port <port>              iperf3 server port (default: 5201)
  --no-auto-port              Do not auto-pick a free port (default: auto)
  --single-port               Force all clients to reuse the same port (default: per-job ports when multiple clients)
  --udp                       Use UDP (-u). If set, --streams is ignored.
  --bandwidth <rate>         UDP target bandwidth (-b) (default: 10M)
  --tcp-rate <rate>          TCP pacing rate (iperf3 --fq-rate, optional)
  --exec-timeout <sec>       Timeout for docker exec calls (default: auto; 0 disables)

  Note: If you explicitly set --lan1-clients, LAN2 is disabled unless you also
        explicitly set --lan2-clients (and vice-versa). Use --lan1-only/--lan2-only
        for clarity.

  --lan1-clients <list>      Comma-separated LAN1 clients (default: edge_server_n1)
  --lan2-clients <list>      Comma-separated LAN2 clients (default: edge_server_n2)
  --lan1-only                Run only LAN1 clients
  --lan2-only                Run only LAN2 clients

  --lan1-mongo <container>   MongoDB container in LAN1 (default: mongodb_n1)
  --lan2-mongo <container>   MongoDB container in LAN2 (default: mongodb_n2)
  --lan1-ip <ip>             Target IP in LAN1 (default: 10.0.0.100 VIP)
  --lan2-ip <ip>             Target IP in LAN2 (default: 10.0.1.100 VIP)

  -h, --help                 Show help

Examples:
  ./source/scripts/generate_iperf_mongo_traffic.sh --duration 30 --streams 4
  ./source/scripts/generate_iperf_mongo_traffic.sh --udp --bandwidth 50M
  ./source/scripts/generate_iperf_mongo_traffic.sh --lan1-only --tcp-rate 7M
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
      --no-auto-port)
        AUTO_PORT=0
        shift
        ;;
      --single-port)
        FORCE_SINGLE_PORT=1
        shift
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
      --tcp-rate)
        [[ $# -ge 2 ]] || die "--tcp-rate requires a value"
        TCP_RATE="$2"
        shift 2
        ;;
      --exec-timeout)
        [[ $# -ge 2 ]] || die "--exec-timeout requires a value"
        DOCKER_EXEC_TIMEOUT_SEC="$2"
        shift 2
        ;;
      --lan1-clients)
        [[ $# -ge 2 ]] || die "--lan1-clients requires a value"
        LAN1_CLIENTS_RAW="$2"
        LAN1_CLIENTS_SET=1
        shift 2
        ;;
      --lan2-clients)
        [[ $# -ge 2 ]] || die "--lan2-clients requires a value"
        LAN2_CLIENTS_RAW="$2"
        LAN2_CLIENTS_SET=1
        shift 2
        ;;
      --lan1-only)
        LAN2_CLIENTS_RAW=""
        LAN1_CLIENTS_SET=1
        shift
        ;;
      --lan2-only)
        LAN1_CLIENTS_RAW=""
        LAN2_CLIENTS_SET=1
        shift
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
  is_uint "$DOCKER_EXEC_TIMEOUT_SEC" || die "--exec-timeout must be an integer (got: $DOCKER_EXEC_TIMEOUT_SEC)"
  if [[ "$USE_UDP" != "1" ]]; then
    is_uint "$PARALLEL_STREAMS" || die "--streams must be an integer (got: $PARALLEL_STREAMS)"
    [[ "$PARALLEL_STREAMS" -ge 1 ]] || die "--streams must be >= 1"
  fi
  [[ "$DURATION_SEC" -ge 1 ]] || die "--duration must be >= 1"

  if [[ -n "${UDP_BANDWIDTH:-}" && "$USE_UDP" != "1" ]]; then
    # This is a common footgun: --bandwidth only applies to UDP mode.
    # Keep it as a warning (not fatal) so existing scripts still run.
    echo "WARN: --bandwidth is only used with --udp; running TCP." >&2
  fi

  # If the user explicitly set one side's clients, disable the other side unless
  # it was explicitly set too. This keeps the default behavior when no explicit
  # --lan*-clients flags are passed.
  if [[ "$LAN1_CLIENTS_SET" == "1" && "$LAN2_CLIENTS_SET" != "1" ]]; then
    LAN2_CLIENTS_RAW=""
  elif [[ "$LAN2_CLIENTS_SET" == "1" && "$LAN1_CLIENTS_SET" != "1" ]]; then
    LAN1_CLIENTS_RAW=""
  fi
}

docker_exec() {
  # Wrapper to prevent indefinite hangs.
  # - If DOCKER_EXEC_TIMEOUT_SEC is 0, run docker exec directly.
  # - Else, use `timeout` on the host.
  if [[ "$DOCKER_EXEC_TIMEOUT_SEC" -eq 0 ]]; then
    docker exec "$@"
    return
  fi

  require_cmd timeout
  timeout --preserve-status "$DOCKER_EXEC_TIMEOUT_SEC" docker exec "$@"
}

parse_clients() {
  local raw=$1
  local -n out=$2
  out=()

  if [[ -z "$raw" ]]; then
    return 0
  fi

  IFS=',' read -r -a out <<< "$raw"
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
  docker_exec "$name" sh -lc 'command -v iperf3 >/dev/null 2>&1'
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

stop_iperf3_server() {
  local name=$1
  local port=$2

  docker_exec "$name" sh -lc '
    port="$1"
    pidfile="/tmp/iperf3_server_${port}.pid"
    if [ -f "$pidfile" ]; then
      pid="$(cat "$pidfile" 2>/dev/null || true)"
      if [ -n "$pid" ]; then
        kill "$pid" >/dev/null 2>&1 || true
      fi
      rm -f "$pidfile" >/dev/null 2>&1 || true
    fi
  ' -- "$port" >/dev/null 2>&1 || true
}

try_start_iperf3_server() {
  local name=$1
  local port=$2

  local pidfile="/tmp/iperf3_server_${port}.pid"
  local logfile="/tmp/iperf3_server_${port}.log"

  docker_exec "$name" sh -lc "
    rm -f '$pidfile' '$logfile';
    iperf3 -s -p '$port' -D -1 --pidfile '$pidfile' --logfile '$logfile'
  " >/dev/null 2>&1 || return 1

  docker_exec "$name" sh -lc "
    [ -f '$pidfile' ] && kill -0 \"\$(cat '$pidfile')\" >/dev/null 2>&1
  " >/dev/null 2>&1
}

stop_iperf3_server_multiport() {
  local name=$1
  shift
  local -a ports=("$@");

  local p
  for p in "${ports[@]}"; do
    stop_iperf3_server "$name" "$p" || true
  done
}

pick_port_range_and_start_servers_multi() {
  local base_port=$1
  local count=$2
  shift 2
  local -a containers=("$@");

  local max_tries=20
  local try=0
  local base

  [[ "$count" -ge 1 ]] || die "internal: port range count must be >= 1"
  if [[ ${#containers[@]} -eq 0 ]]; then
    die "no iperf3 server containers selected"
  fi

  while [[ "$try" -lt "$max_tries" ]]; do
    base=$((base_port + try))

    # Best-effort cleanup for this candidate range.
    local p
    for p in $(seq 0 $((count - 1))); do
      local port=$((base + p))
      local c
      for c in "${containers[@]}"; do
        stop_iperf3_server "$c" "$port" || true
      done
    done

    local ok=1
    for p in $(seq 0 $((count - 1))); do
      local port=$((base + p))
      local c
      for c in "${containers[@]}"; do
        if ! try_start_iperf3_server "$c" "$port"; then
          ok=0
          break
        fi
      done
      [[ "$ok" -eq 1 ]] || break
    done

    if [[ "$ok" -eq 1 ]]; then
      SERVER_PORT="$base"
      return 0
    fi

    # Tear down any servers we started in this attempt.
    for p in $(seq 0 $((count - 1))); do
      local port=$((base + p))
      local c
      for c in "${containers[@]}"; do
        stop_iperf3_server "$c" "$port" || true
      done
    done

    try=$((try + 1))
  done

  die "could not start iperf3 servers for port range after ${max_tries} attempts (base port: ${base_port}, count: ${count})"
}

pick_port_and_start_servers_multi() {
  local base_port=$1
  shift
  local -a containers=("$@");

  local max_tries=20
  local try=0
  local port

  if [[ ${#containers[@]} -eq 0 ]]; then
    die "no iperf3 server containers selected"
  fi

  while [[ "$try" -lt "$max_tries" ]]; do
    port=$((base_port + try))

    for c in "${containers[@]}"; do
      stop_iperf3_server "$c" "$port" || true
    done

    local ok=1
    for c in "${containers[@]}"; do
      if ! try_start_iperf3_server "$c" "$port"; then
        ok=0
        break
      fi
    done

    if [[ "$ok" -eq 1 ]]; then
      SERVER_PORT="$port"
      return 0
    fi

    for c in "${containers[@]}"; do
      stop_iperf3_server "$c" "$port" || true
    done

    try=$((try + 1))
  done

  echo "---- iperf3 server log (${containers[0]}) ----" >&2
  docker exec "${containers[0]}" sh -lc "tail -n 80 /tmp/iperf3_server_${base_port}.log 2>/dev/null || true" >&2 || true
  die "could not start iperf3 servers after ${max_tries} attempts (base port: ${base_port})"
}

start_iperf3_servers_fixed_multi() {
  local port=$1
  shift
  local -a containers=("$@");

  if [[ ${#containers[@]} -eq 0 ]]; then
    die "no iperf3 server containers selected"
  fi

  for c in "${containers[@]}"; do
    start_iperf3_server "$c" "$port"
  done
}

pick_port_and_start_servers() {
  local base_port=$1
  local max_tries=20
  local try=0
  local port

  while [[ "$try" -lt "$max_tries" ]]; do
    port=$((base_port + try))

    stop_iperf3_server "$LAN1_MONGO_CONTAINER" "$port" || true
    stop_iperf3_server "$LAN2_MONGO_CONTAINER" "$port" || true

    if try_start_iperf3_server "$LAN1_MONGO_CONTAINER" "$port" && try_start_iperf3_server "$LAN2_MONGO_CONTAINER" "$port"; then
      SERVER_PORT="$port"
      return 0
    fi

    stop_iperf3_server "$LAN1_MONGO_CONTAINER" "$port" || true
    stop_iperf3_server "$LAN2_MONGO_CONTAINER" "$port" || true
    try=$((try + 1))
  done

  echo "---- iperf3 server log ($LAN1_MONGO_CONTAINER) ----" >&2
  docker exec "$LAN1_MONGO_CONTAINER" sh -lc "tail -n 80 /tmp/iperf3_server_${base_port}.log 2>/dev/null || true" >&2 || true
  die "could not start iperf3 servers after ${max_tries} attempts (base port: ${base_port})"
}

pick_port_and_start_server_single() {
  local name=$1
  local base_port=$2
  local max_tries=20
  local try=0
  local port

  while [[ "$try" -lt "$max_tries" ]]; do
    port=$((base_port + try))

    stop_iperf3_server "$name" "$port" || true
    if try_start_iperf3_server "$name" "$port"; then
      SERVER_PORT="$port"
      return 0
    fi

    stop_iperf3_server "$name" "$port" || true
    try=$((try + 1))
  done

  echo "---- iperf3 server log ($name) ----" >&2
  docker exec "$name" sh -lc "tail -n 80 /tmp/iperf3_server_${base_port}.log 2>/dev/null || true" >&2 || true
  die "could not start iperf3 server after ${max_tries} attempts (base port: ${base_port})"
}

start_iperf3_server() {
  local name=$1
  local port=$2

  local pidfile="/tmp/iperf3_server_${port}.pid"
  local logfile="/tmp/iperf3_server_${port}.log"

  stop_iperf3_server "$name" "$port" || true
  if ! try_start_iperf3_server "$name" "$port"; then
    echo "---- iperf3 server log ($name) ----" >&2
    docker exec "$name" sh -lc "test -f '$logfile' && tail -n 80 '$logfile' || true" >&2 || true
    die "failed to start iperf3 server in container: $name"
  fi
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
    if [[ -n "${TCP_RATE:-}" ]]; then
      args+=("--fq-rate" "$TCP_RATE")
    fi
  fi

  docker_exec "$client_container" iperf3 "${args[@]}"
}

main() {
  parse_args "$@"

  # Default docker exec timeout: duration + a small buffer (server setup + handshake).
  if [[ "$DOCKER_EXEC_TIMEOUT_SEC" -eq 0 ]]; then
    DOCKER_EXEC_TIMEOUT_SEC=$((DURATION_SEC + 25))
  fi

  parse_clients "${LAN1_CLIENTS_RAW}" LAN1_CLIENTS
  parse_clients "${LAN2_CLIENTS_RAW}" LAN2_CLIENTS

  if [[ ${#LAN1_CLIENTS[@]} -eq 0 && ${#LAN2_CLIENTS[@]} -eq 0 ]]; then
    die "no clients selected (use --lan1-clients/--lan2-clients)"
  fi

  require_cmd docker

  server_containers=()
  if [[ ${#LAN1_CLIENTS[@]} -gt 0 ]]; then
    server_containers+=("$LAN1_MONGO_CONTAINER")
  fi
  if [[ ${#LAN2_CLIENTS[@]} -gt 0 ]]; then
    server_containers+=("$LAN2_MONGO_CONTAINER")
  fi

  if [[ ${#LAN1_CLIENTS[@]} -gt 0 ]]; then
    ensure_container_running "$LAN1_MONGO_CONTAINER"
    ensure_iperf3_in_container "$LAN1_MONGO_CONTAINER"
    for client in "${LAN1_CLIENTS[@]}"; do
      ensure_container_running "$client"
      ensure_iperf3_in_container "$client"
    done
  fi

  if [[ ${#LAN2_CLIENTS[@]} -gt 0 ]]; then
    ensure_container_running "$LAN2_MONGO_CONTAINER"
    ensure_iperf3_in_container "$LAN2_MONGO_CONTAINER"
    for client in "${LAN2_CLIENTS[@]}"; do
      ensure_container_running "$client"
      ensure_iperf3_in_container "$client"
    done
  fi

  # Compute how many concurrent client jobs will run.
  total_jobs=0
  total_jobs=$((total_jobs + ${#LAN1_CLIENTS[@]}))
  total_jobs=$((total_jobs + ${#LAN2_CLIENTS[@]}))

  MULTI_PORT=0
  if [[ "$FORCE_SINGLE_PORT" != "1" && "$total_jobs" -gt 1 ]]; then
    MULTI_PORT=1
  fi

  echo "Starting iperf3 servers on MongoDB containers..." >&2
  if [[ "$AUTO_PORT" == "1" ]]; then
    if [[ "$MULTI_PORT" == "1" ]]; then
      pick_port_range_and_start_servers_multi "$SERVER_PORT" "$total_jobs" "${server_containers[@]}"
    else
      pick_port_and_start_servers_multi "$SERVER_PORT" "${server_containers[@]}"
    fi
  else
    if [[ "$MULTI_PORT" == "1" ]]; then
      pick_port_range_and_start_servers_multi "$SERVER_PORT" "$total_jobs" "${server_containers[@]}"
    else
      start_iperf3_servers_fixed_multi "$SERVER_PORT" "${server_containers[@]}"
    fi
  fi

  # Build port list for cleanup.
  ports=()
  if [[ "$MULTI_PORT" == "1" ]]; then
    for i in $(seq 0 $((total_jobs - 1))); do
      ports+=("$((SERVER_PORT + i))")
    done
  else
    ports+=("$SERVER_PORT")
  fi

  cleanup() {
    for c in "${server_containers[@]}"; do
      stop_iperf3_server_multiport "$c" "${ports[@]}" || true
    done
  }
  trap cleanup EXIT INT TERM

  echo "Running iperf3 clients:" >&2
  if [[ ${#LAN1_CLIENTS[@]} -gt 0 ]]; then
    echo "  LAN1: $(format_clients_with_ips LAN1_CLIENTS) -> $LAN1_MONGO_IP (VIP)" >&2
  fi
  if [[ ${#LAN2_CLIENTS[@]} -gt 0 ]]; then
    echo "  LAN2: $(format_clients_with_ips LAN2_CLIENTS) -> $LAN2_MONGO_IP (VIP)" >&2
  fi
  echo "  port: $SERVER_PORT" >&2
  if [[ "$MULTI_PORT" == "1" ]]; then
    echo "  multi-port: base=$SERVER_PORT jobs=$total_jobs" >&2
  fi

  # Run clients at the same time to generate concurrent load.
  pids=()

  job_idx=0

  for client in "${LAN1_CLIENTS[@]}"; do
    port="$SERVER_PORT"
    if [[ "$MULTI_PORT" == "1" ]]; then
      port=$((SERVER_PORT + job_idx))
    fi
    run_iperf3_client "$client" "$LAN1_MONGO_IP" "$port" &
    pids+=("$!")
    job_idx=$((job_idx + 1))
  done

  for client in "${LAN2_CLIENTS[@]}"; do
    port="$SERVER_PORT"
    if [[ "$MULTI_PORT" == "1" ]]; then
      port=$((SERVER_PORT + job_idx))
    fi
    run_iperf3_client "$client" "$LAN2_MONGO_IP" "$port" &
    pids+=("$!")
    job_idx=$((job_idx + 1))
  done

  for pid in "${pids[@]}"; do
    wait "$pid"
  done

  echo "Done." >&2
}

main "$@"
