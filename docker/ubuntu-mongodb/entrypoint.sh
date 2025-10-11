#!/usr/bin/env bash
set -Eeuo pipefail
IFS=$'\n\t'

# MongoDB container entrypoint
#
# What it does:
# - On first run (empty DBPATH), it starts mongod without auth temporarily to initialize:
#   - Creates an admin root user if MONGO_INITDB_ROOT_USERNAME/PASSWORD are set
#   - Creates an application database if MONGO_INITDB_DATABASE is set
#   - Creates an application user with readWrite on that DB if MONGO_INITDB_USERNAME/PASSWORD are set
#   - Optionally pre-creates a collection if MONGO_INITDB_COLLECTION is set
#   - Then gracefully stops mongod and restarts it with --auth enabled
# - On subsequent runs (non-empty DBPATH):
#   - If root credentials are provided, starts mongod with --auth
#   - Otherwise starts mongod without auth (backward compatibility)
#
# Usage:
#   docker run -e MONGO_INITDB_ROOT_USERNAME=admin \
#              -e MONGO_INITDB_ROOT_PASSWORD=secret \
#              -e MONGO_INITDB_DATABASE=appdb \
#              -e MONGO_INITDB_USERNAME=appuser \
#              -e MONGO_INITDB_PASSWORD=apppass \
#              -e MONGO_INITDB_COLLECTION=items \
#              -v mongodb-data:/data/db <image>
#
#   For help inside the container:
#     docker run --rm <image> --help
#
# Environment variables:
#   MONGO_INITDB_ROOT_USERNAME   Admin user name (creates root@admin)
#   MONGO_INITDB_ROOT_PASSWORD   Admin user password
#   MONGO_INITDB_DATABASE        Application database name (e.g., appdb)
#   MONGO_INITDB_USERNAME        App user name (granted readWrite on MONGO_INITDB_DATABASE)
#   MONGO_INITDB_PASSWORD        App user password
#   MONGO_INITDB_COLLECTION      Optional collection to pre-create in MONGO_INITDB_DATABASE
#   DBPATH                       Data path (default: /data/db)
#   PORT                         MongoDB port (default: 27017)
#   BIND_IP                      Bind address (default: 0.0.0.0)

# Environment variables to control initialization and auth
MONGO_INITDB_ROOT_USERNAME=${MONGO_INITDB_ROOT_USERNAME:-}
MONGO_INITDB_ROOT_PASSWORD=${MONGO_INITDB_ROOT_PASSWORD:-}
MONGO_INITDB_DATABASE=${MONGO_INITDB_DATABASE:-}
MONGO_INITDB_USERNAME=${MONGO_INITDB_USERNAME:-}
MONGO_INITDB_PASSWORD=${MONGO_INITDB_PASSWORD:-}
MONGO_INITDB_COLLECTION=${MONGO_INITDB_COLLECTION:-}

DBPATH=${DBPATH:-/data/db}
PORT=${PORT:-27017}
BIND_IP=${BIND_IP:-0.0.0.0}

log() { printf '[mongo-entrypoint] %s\n' "$*"; }

print_usage() {
  cat <<EOF
MongoDB init/auth entrypoint

On first run (empty DBPATH), initializes optional users/DB/collection, then restarts with --auth.
On subsequent runs, starts with --auth if root user envs are provided; otherwise without auth.

Environment variables:
  MONGO_INITDB_ROOT_USERNAME   Admin user name (creates root@admin)
  MONGO_INITDB_ROOT_PASSWORD   Admin user password
  MONGO_INITDB_DATABASE        Application database name (e.g., appdb)
  MONGO_INITDB_USERNAME        App user name (readWrite on MONGO_INITDB_DATABASE)
  MONGO_INITDB_PASSWORD        App user password
  MONGO_INITDB_COLLECTION      Optional collection to pre-create
  DBPATH                       Data path (default: ${DBPATH})
  PORT                         MongoDB port (default: ${PORT})
  BIND_IP                      Bind address (default: ${BIND_IP})

Examples:
  docker run -e MONGO_INITDB_ROOT_USERNAME=admin \\
             -e MONGO_INITDB_ROOT_PASSWORD=secret \\
             -e MONGO_INITDB_DATABASE=appdb \\
             -e MONGO_INITDB_USERNAME=appuser \\
             -e MONGO_INITDB_PASSWORD=apppass \\
             -e MONGO_INITDB_COLLECTION=items \\
             -v mongodb-data:/data/db <image>
EOF
}

# Early help if requested
if [[ ${1-} == "-h" || ${1-} == "--help" ]]; then
  print_usage
  exit 0
fi

# Start mongod without auth to bootstrap if needed
start_mongod_noauth() {
  log "Starting mongod (no auth) for initialization..."
  mongod --bind_ip_all --dbpath "$DBPATH" --port "$PORT" --fork --logpath /var/log/mongod_init.log
}

stop_mongod() {
  log "Stopping mongod..."
  mongosh --quiet --eval "db.getSiblingDB('admin').shutdownServer()" || true
  # give it a moment
  sleep 1
}

enable_auth_and_exec() {
  # Replace current process with mongod with authorization enabled
  log "Starting mongod with authorization enabled..."
  exec mongod --bind_ip "$BIND_IP" --dbpath "$DBPATH" --port "$PORT" --auth
}

init_js_tmp=$(mktemp)
trap 'rm -f "$init_js_tmp"' EXIT

needs_init=true
if [[ -d "$DBPATH" ]]; then
  # Consider database initialized if there are collection files
  if find "$DBPATH" -mindepth 1 -type f | grep -q .; then
    needs_init=false
  fi
fi

if $needs_init; then
  start_mongod_noauth

  if [[ -n "$MONGO_INITDB_ROOT_USERNAME" && -n "$MONGO_INITDB_ROOT_PASSWORD" ]]; then
    cat >"$init_js_tmp" <<JS
// Create admin user
use admin;
db.createUser({user: "$MONGO_INITDB_ROOT_USERNAME", pwd: "$MONGO_INITDB_ROOT_PASSWORD", roles: [ { role: 'root', db: 'admin' } ]});
JS
    mongosh --quiet "$init_js_tmp"
    log "Created root user in admin DB."
  fi

  if [[ -n "$MONGO_INITDB_DATABASE" ]]; then
    # If app user specified, create it
    if [[ -n "$MONGO_INITDB_USERNAME" && -n "$MONGO_INITDB_PASSWORD" ]]; then
      cat >"$init_js_tmp" <<JS
use $MONGO_INITDB_DATABASE;
db.createUser({user: "$MONGO_INITDB_USERNAME", pwd: "$MONGO_INITDB_PASSWORD", roles: [ { role: 'readWrite', db: '$MONGO_INITDB_DATABASE' } ]});
JS
      mongosh --quiet "$init_js_tmp"
      log "Created app user '$MONGO_INITDB_USERNAME' in '$MONGO_INITDB_DATABASE'."
    fi

    # Optionally pre-create collection
    if [[ -n "$MONGO_INITDB_COLLECTION" ]]; then
      cat >"$init_js_tmp" <<JS
use $MONGO_INITDB_DATABASE;
db.createCollection('$MONGO_INITDB_COLLECTION');
JS
      mongosh --quiet "$init_js_tmp"
      log "Created collection '$MONGO_INITDB_COLLECTION' in '$MONGO_INITDB_DATABASE'."
    fi
  fi

  stop_mongod
  enable_auth_and_exec
else
  # Already initialized - just start with auth if root is configured, otherwise without auth
  if [[ -n "$MONGO_INITDB_ROOT_USERNAME" && -n "$MONGO_INITDB_ROOT_PASSWORD" ]]; then
    enable_auth_and_exec
  else
    log "Database appears initialized and no root user provided; starting without auth."
    exec mongod --bind_ip "$BIND_IP" --dbpath "$DBPATH" --port "$PORT"
  fi
fi
