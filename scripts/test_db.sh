#!/usr/bin/env bash

# Test script: both hosts write then read from MongoDB
# - Each host (container1 and container2 by default) inserts one document with a random field and a 'from' tag
# - Then the script waits 3 seconds (or after MongoDB becomes reachable)
# - Then each host reads and prints all documents from the collection
#
# Requirements:
# - host containers have mongosh installed (ubuntu-host-1/2 images should include mongodb-mongosh)
# - MongoDB is reachable at the URL below (adjust if you use auth)

set -euo pipefail

# ---- Config (override via environment) ----
CONTAINER1=${CONTAINER1:-container1}
CONTAINER2=${CONTAINER2:-container2}

# If parts are provided, assemble MONGO_URL; else default to test DB
MONGO_HOST=${MONGO_HOST:-10.0.0.4}
MONGO_PORT=${MONGO_PORT:-27017}
MONGO_DB=${MONGO_DB:-test}
MONGO_USER=${MONGO_USER:-}
MONGO_PASS=${MONGO_PASS:-}

if [[ -n "$MONGO_USER" && -n "$MONGO_PASS" ]]; then
  MONGO_URL=${MONGO_URL:-"mongodb://${MONGO_USER}:${MONGO_PASS}@${MONGO_HOST}:${MONGO_PORT}/${MONGO_DB}?authSource=${MONGO_DB}"}
else
  MONGO_URL=${MONGO_URL:-"mongodb://${MONGO_HOST}:${MONGO_PORT}/${MONGO_DB}"}
fi

COLLECTION=${COLLECTION:-items}
# Readiness wait configuration
MONGO_WAIT_TRIES=${MONGO_WAIT_TRIES:-20}
MONGO_WAIT_SLEEP=${MONGO_WAIT_SLEEP:-1}

# If you use auth, set MONGO_URL to include creds, e.g.:
# export MONGO_URL="mongodb://admin:secret@10.0.0.4:27017/test?authSource=admin"

log() {
  echo "[test_db] $*"
}

print_usage() {
  cat <<EOF
Usage: $(basename "$0") [--help]

Environment overrides:
  CONTAINER1         First host container name (default: ${CONTAINER1})
  CONTAINER2         Second host container name (default: ${CONTAINER2})
  MONGO_URL          MongoDB connection string (default constructed from parts)
  MONGO_HOST         MongoDB host (default: ${MONGO_HOST})
  MONGO_PORT         MongoDB port (default: ${MONGO_PORT})
  MONGO_DB           MongoDB database name (default: ${MONGO_DB})
  MONGO_USER         MongoDB user (optional)
  MONGO_PASS         MongoDB password (optional)
  COLLECTION         MongoDB collection (default: ${COLLECTION})
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
    if docker exec "$name" bash -lc "mongosh --quiet '${MONGO_URL}' --eval 'db.runCommand({ping:1})'" >/dev/null 2>&1; then
      log "MongoDB reachable from ${name}."
      return 0
    fi
    sleep "${MONGO_WAIT_SLEEP}"
  done
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
  docker exec "$name" bash -lc "mongosh --quiet '${MONGO_URL}' --eval \"${js}\"" >/dev/null
}

read_all() {
  local name="$1"; shift
  local from_label="$1"; shift
  local js
  js="printjson(db.${COLLECTION}.find().toArray())"
  log "Reading all items via ${from_label} (${name})"
  docker exec "$name" bash -lc "mongosh --quiet '${MONGO_URL}' --eval \"${js}\""
}

main() {
  require_cmd docker
  log "Using containers: ${CONTAINER1}, ${CONTAINER2}"
  log "Mongo URL: ${MONGO_URL}"
  log "Collection: ${COLLECTION}"

  require_container "$CONTAINER1"
  require_container "$CONTAINER2"
  check_mongosh "$CONTAINER1"
  check_mongosh "$CONTAINER2"

  # Ensure MongoDB is ready before inserting
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
