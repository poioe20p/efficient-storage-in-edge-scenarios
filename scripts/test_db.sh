#!/usr/bin/env bash

# Test script: both hosts write then read from MongoDB
# - Each host (container1 and container2 by default) inserts one document with a random field and a 'from' tag
# - Then the script waits 3 seconds (or after MongoDB becomes reachable)
# - Then each host reads and prints all documents from the collection
#
# Requirements:
# - host containers have mongosh installed (ubuntu-host/2 images should include mongodb-mongosh)
# - MongoDB is reachable at the URL below (adjust if you use auth)

set -euo pipefail

# ---- Helpers ----
log() {
  echo "[test_db] $*"
}

# Warning logger (non-fatal diagnostics)
warn() {
  echo "[test_db][WARN] $*" 1>&2
}

# Helper: strip Windows CR from a variable by name (when env file has CRLF)
strip_cr_var() {
  local name="$1"
  if [[ -n "${!name-}" ]]; then
    # shellcheck disable=SC2086
    printf -v "$name" '%s' "${!name//$'\r'/}"
  fi
}

# Helper: URL-encode username/password for Mongo URI
url_encode() {
  local s="$1" out="" i c
  for (( i=0; i<${#s}; i++ )); do
    c="${s:i:1}"
    case "$c" in
      [a-zA-Z0-9._~-]) out+="$c" ;;
      *) printf -v hex '%%%02X' "'${c}'"; out+="$hex" ;;
    esac
  done
  printf '%s' "$out"
}

# Helper: mask password in URI for logs
mask_url() {
  sed -E 's#(mongodb://[^:/]+):([^@]*)@#\1:***@#' <<<"$1"
}

# Load MongoDB env-file if present (to reuse init creds)
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
MONGO_ENV_FILE=${MONGO_ENV_FILE:-"${SCRIPT_DIR}/../.env-mongo"}
if [[ -f "$MONGO_ENV_FILE" ]]; then
  # Export all simple KEY=VALUE entries from the env file
  set -a
  . "$MONGO_ENV_FILE"
  set +a
fi

# ---- Config (override via environment where applicable) ----
CONTAINER1=${CONTAINER1:-container1}
CONTAINER2=${CONTAINER2:-container2}

# If parts are provided, assemble MONGO_URL; else default to test DB
MONGO_HOST=${MONGO_HOST:-10.0.0.4}
MONGO_PORT=${MONGO_PORT:-27017}
# Prefer DB from env init if present, otherwise default to 'test'
MONGO_DB=${MONGO_DB:-${MONGO_DATABASE:-test}}
MONGO_USER=${MONGO_APP_USERNAME:-${MONGO_USER:-}}
MONGO_PASS=${MONGO_APP_PASSWORD:-${MONGO_PASS:-}}
MONGO_ADMIN_USER=${MONGO_ADMIN_USERNAME:-}
MONGO_DATABASE_VALUE=${MONGO_DATABASE:-}

# Sanitize possible CRLF artifacts from env/Windows
for v in CONTAINER1 CONTAINER2 MONGO_HOST MONGO_PORT MONGO_DB MONGO_USER MONGO_PASS MONGO_AUTHSOURCE MONGO_URL MONGO_ADMIN_USER MONGO_DATABASE_VALUE; do
  strip_cr_var "$v"
done

# Infer authSource if not provided:
# - If using the root username from init, default to 'admin'
# - Else prefer app database from init, else fall back to MONGO_DB
if [[ -z "${MONGO_AUTHSOURCE:-}" ]]; then
  if [[ -n "$MONGO_ADMIN_USER" && "$MONGO_USER" == "$MONGO_ADMIN_USER" ]]; then
    MONGO_AUTHSOURCE=admin
  elif [[ -n "$MONGO_DATABASE_VALUE" ]]; then
    MONGO_AUTHSOURCE="$MONGO_DATABASE_VALUE"
  else
    MONGO_AUTHSOURCE="$MONGO_DB"
  fi
fi

# Build URLs: if user provided MONGO_URL, use it for both ping and CRUD.
# Otherwise, construct:
#  - MONGO_URL_APP: targets the application DB (for inserts/reads)
#  - MONGO_URL_PING: targets the authSource DB (for readiness ping)
if [[ -n "${MONGO_URL:-}" ]]; then
  MONGO_URL_APP="$MONGO_URL"
  MONGO_URL_PING="$MONGO_URL"
else
  if [[ -n "$MONGO_USER" && -n "$MONGO_PASS" ]]; then
      UENC="$(url_encode "$MONGO_USER")"
      PENC="$(url_encode "$MONGO_PASS")"
      MONGO_URL_APP="mongodb://${UENC}:${PENC}@${MONGO_HOST}:${MONGO_PORT}/${MONGO_DB}?authSource=${MONGO_AUTHSOURCE}"
      MONGO_URL_PING="mongodb://${UENC}:${PENC}@${MONGO_HOST}:${MONGO_PORT}/${MONGO_AUTHSOURCE}?authSource=${MONGO_AUTHSOURCE}"
  else
    MONGO_URL_APP="mongodb://${MONGO_HOST}:${MONGO_PORT}/${MONGO_DB}"
    MONGO_URL_PING="$MONGO_URL_APP"
  fi
fi

# Collection in use (fixed for this setup)
COLLECTION="items"
# Readiness wait configuration
MONGO_WAIT_TRIES=${MONGO_WAIT_TRIES:-20}
MONGO_WAIT_SLEEP=${MONGO_WAIT_SLEEP:-1}

# If you use auth, set MONGO_URL to include creds, e.g.:
# export MONGO_URL="mongodb://admin:secret@10.0.0.4:27017/test?authSource=admin"

print_usage() {
  cat <<EOF
Usage: $(basename "$0") [--help]

Environment:
  CONTAINER1         First host container name (default: ${CONTAINER1})
  CONTAINER2         Second host container name (default: ${CONTAINER2})
  MONGO_URL          MongoDB connection string (constructed from parts if not set)
  MONGO_HOST         MongoDB host (default: ${MONGO_HOST})
  MONGO_PORT         MongoDB port (default: ${MONGO_PORT})
  MONGO_DB           MongoDB database name (default: ${MONGO_DB})
  MONGO_AUTHSOURCE   Authentication DB (default: ${MONGO_AUTHSOURCE}; set to 'admin' if using root)
  MONGO_USER         MongoDB user (required unless MONGO_URL includes credentials)
  MONGO_PASS         MongoDB password (required unless MONGO_URL includes credentials)
  MONGO_APP_USERNAME Same as MONGO_USER but picked up automatically when set
  MONGO_APP_PASSWORD Same as MONGO_PASS but picked up automatically when set
  MONGO_ADMIN_USERNAME Root user name (used to infer authSource=admin when matching MONGO_USER)
  COLLECTION         MongoDB collection (fixed: ${COLLECTION})
  MONGO_WAIT_TRIES   Max attempts to wait for Mongo (default: ${MONGO_WAIT_TRIES})
  MONGO_WAIT_SLEEP   Seconds between attempts (default: ${MONGO_WAIT_SLEEP})

Example:
  MONGO_URL="mongodb://10.0.0.4:27017/test" ./test_db.sh
EOF
}

if [[ ${1-} == "-h" || ${1-} == "--help" ]]; then
  print_usage
  exit 0
fi

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { log "ERROR: required command not found: $1"; exit 127; }
}

require_container() {
  local name="$1"
  if ! docker ps --format '{{.Names}}' | grep -Fxq "$name"; then
    log "ERROR: container '$name' is not running."
    exit 1
  fi

  # Strip Windows CR (\r) if the env file used CRLF line endings to avoid malformed URLs
  # Removed CR stripping from here, handled by strip_cr_var
}

check_mongosh() {
  local name="$1"
  if ! docker exec "$name" bash -lc 'command -v mongosh >/dev/null 2>&1'; then
    log "ERROR: mongosh not found in container '$name'"
    exit 1
  fi
}

wait_for_mongo() {
  local name="$1"
  log "Waiting for MongoDB to be reachable from ${name} (tries=${MONGO_WAIT_TRIES}, sleep=${MONGO_WAIT_SLEEP}s)..."
  local i
  for (( i=1; i<=MONGO_WAIT_TRIES; i++ )); do
  if docker exec "$name" bash -lc "mongosh --quiet '${MONGO_URL_PING}' --eval 'db.runCommand({ping:1})'" >/dev/null 2>"/tmp/mongosh_err_${name}.log"; then
      log "MongoDB reachable from ${name}."
      return 0
    fi
    sleep "${MONGO_WAIT_SLEEP}"
  done
  # Show last mongosh error to help diagnose (auth vs network)
  if [[ -f "/tmp/mongosh_err_${name}.log" ]]; then
    warn "mongosh last error from ${name}: $(tail -n 1 "/tmp/mongosh_err_${name}.log" | tr -d '\r')"
  fi
  log "ERROR: MongoDB not reachable from ${name} after ${MONGO_WAIT_TRIES} attempts."
  exit 1
}

insert_item() {
  local name="$1"; shift
  local from_label="$1"; shift
  # JS creates a random payload and inserts one document
  local js
  js="const r=Math.floor(Math.random()*1000000); db.${COLLECTION}.insertOne({from: '${from_label}', ts: new Date(), rand: r, note: 'hello from '+ '${from_label}'});"
  log "Inserting from ${from_label} via ${name}"
  docker exec "$name" bash -lc "mongosh --quiet '${MONGO_URL_APP}' --eval \"${js}\"" >/dev/null
}

read_all() {
  local name="$1"; shift
  local from_label="$1"; shift
  local js
  js="printjson(db.${COLLECTION}.find().toArray())"
  log "Reading all items via ${from_label} (${name})"
  docker exec "$name" bash -lc "mongosh --quiet '${MONGO_URL_APP}' --eval \"${js}\""
}

main() {
  require_cmd docker
  log "Using containers: ${CONTAINER1}, ${CONTAINER2}"
  log "Mongo URL (app): $(mask_url "${MONGO_URL_APP}")"
  log "Mongo URL (ping): $(mask_url "${MONGO_URL_PING}")"

  require_container "$CONTAINER1"
  require_container "$CONTAINER2"
  check_mongosh "$CONTAINER1"
  check_mongosh "$CONTAINER2"

  # Authentication required: ensure we have credentials either via parts or in MONGO_URL
  if [[ -z "$MONGO_USER" || -z "$MONGO_PASS" ]]; then
    if [[ "${MONGO_URL_APP}" != *"mongodb://"*"@"* ]]; then
      log "ERROR: Authentication enabled. Set MONGO_APP_USERNAME/MONGO_APP_PASSWORD (or MONGO_USER/MONGO_PASS), or provide MONGO_URL with credentials."
      exit 2
    fi
  fi

  # Quick network diagnostic: can we ping the Mongo host IP?
  if docker exec "$CONTAINER1" bash -lc "command -v ping >/dev/null 2>&1"; then
    if ! docker exec "$CONTAINER1" bash -lc "ping -c 1 -W 1 ${MONGO_HOST} >/dev/null"; then
      warn "Network ping to ${MONGO_HOST} failed from ${CONTAINER1}. Check OVS wiring and IP assignments."
    else
      log "Network ping to ${MONGO_HOST} OK from ${CONTAINER1}."
    fi
  fi

  # Ensure MongoDB is ready before inserting (auth and service)
  wait_for_mongo "$CONTAINER1"

  # Step 1: Both insert an item
  insert_item "$CONTAINER1" host1
  insert_item "$CONTAINER2" host2

  # Step 2: Wait 3 seconds
  log "Waiting 3 seconds before reads..."
  sleep 3

  # Step 3: Both read all items
  read_all "$CONTAINER1" host1
  read_all "$CONTAINER2" host2

  log "Done."
}

main "$@"
