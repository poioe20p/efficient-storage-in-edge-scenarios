#!/usr/bin/env bash

# Connectivity test script
# - Verifies inter-container connectivity between host1, host2, and mongodb by IP
# - Verifies reachability to the default gateway and the internet (ICMP and HTTP as fallback)
#
# Defaults reflect the setup used in this repo:
#   host1 (container1) -> 10.0.0.2
#   host2 (container2) -> 10.0.0.3
#   mongodb            -> 10.0.0.4
#   gateway (router)   -> 10.0.0.1
#
# Usage:
#   ./scripts/test_setup.sh            # run all tests with defaults
#   ./scripts/test_setup.sh --help     # show help
#
# Environment overrides:
#   CONTAINER1, CONTAINER2, MONGO      # container names (default: container1, container2, mongodb)
#   IP1, IP2, IP_MONGO, GW_IP          # IP addresses (defaults as above)
#   INTERNET_HOST                      # host to test DNS/HTTP (default: www.google.com)
#   PING_COUNT, PING_TIMEOUT           # ping parameters (default: 2, 2 seconds)

set -Eeuo pipefail
IFS=$'\n\t'

SCRIPT_NAME=$(basename "$0")

log()  { printf '[INFO] %s\n' "$*"; }
warn() { printf '[WARN] %s\n' "$*" 1>&2; }
err()  { printf '[ERROR] %s\n' "$*" 1>&2; }

print_usage() {
	cat <<EOF
Usage: $SCRIPT_NAME [--help]

Runs connectivity checks from each container to the others, the gateway, and the internet.

Defaults:
	Containers: container1 (10.0.0.2), container2 (10.0.0.3), mongodb (10.0.0.4), gateway (10.0.0.1)

Environment overrides:
	CONTAINER1, CONTAINER2, MONGO
	IP1, IP2, IP_MONGO, GW_IP
	INTERNET_HOST (default: ${INTERNET_HOST:-www.google.com})
	PING_COUNT (default: ${PING_COUNT:-2}), PING_TIMEOUT (default: ${PING_TIMEOUT:-2})
EOF
}

if [[ ${1-} == "-h" || ${1-} == "--help" ]]; then
	print_usage
	exit 0
fi

# Defaults
CONTAINER1=${CONTAINER1:-container1}
CONTAINER2=${CONTAINER2:-container2}
MONGO=${MONGO:-mongodb}
IP1=${IP1:-10.0.0.2}
IP2=${IP2:-10.0.0.3}
IP_MONGO=${IP_MONGO:-10.0.0.4}
GW_IP=${GW_IP:-10.0.0.1}
INTERNET_HOST=${INTERNET_HOST:-www.google.com}
PING_COUNT=${PING_COUNT:-2}
PING_TIMEOUT=${PING_TIMEOUT:-2}

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
	# Try ICMP if available
	if has_cmd_in "$from" ping; then
		if exec_in "$from" "ping -c ${PING_COUNT} -W ${PING_TIMEOUT} ${host} >/dev/null"; then
			log "${from}: internet ICMP to ${host} OK"
			ok=0
		else
			warn "${from}: internet ICMP to ${host} failed; trying HTTP"
		fi
	fi
	# Fallback to HTTP HEAD via curl if available
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

main() {
	require_cmd docker
	log "Testing connectivity"
	log "Containers: ${CONTAINER1}(${IP1}), ${CONTAINER2}(${IP2}), ${MONGO}(${IP_MONGO}) | GW=${GW_IP} | Internet=${INTERNET_HOST}"

	require_container "$CONTAINER1"
	require_container "$CONTAINER2"
	require_container "$MONGO"

	local failures=0

	# From CONTAINER1
	ping_from_to "$CONTAINER1" "$IP2" "host2"      || ((failures++))
	ping_from_to "$CONTAINER1" "$IP_MONGO" "mongodb" || ((failures++))
	ping_from_to "$CONTAINER1" "$GW_IP" "gateway"    || ((failures++))
	internet_test "$CONTAINER1" "$INTERNET_HOST"      || ((failures++))

	# From CONTAINER2
	ping_from_to "$CONTAINER2" "$IP1" "host1"       || ((failures++))
	ping_from_to "$CONTAINER2" "$IP_MONGO" "mongodb" || ((failures++))
	ping_from_to "$CONTAINER2" "$GW_IP" "gateway"    || ((failures++))
	internet_test "$CONTAINER2" "$INTERNET_HOST"      || ((failures++))

	# From MONGO container
	ping_from_to "$MONGO" "$IP1" "host1"            || ((failures++))
	ping_from_to "$MONGO" "$IP2" "host2"            || ((failures++))
	ping_from_to "$MONGO" "$GW_IP" "gateway"        || ((failures++))
	internet_test "$MONGO" "$INTERNET_HOST"          || ((failures++))

	if [[ $failures -eq 0 ]]; then
		log "✅ All connectivity checks passed."
		exit 0
	else
		err "❌ Connectivity checks failed: ${failures} issue(s) detected."
		exit 1
	fi
}

main "$@"

