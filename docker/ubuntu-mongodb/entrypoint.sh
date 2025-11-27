# #!/bin/bash
# set -Eeuo pipefail
# IFS=$'\n\t'

# # MongoDB container entrypoint
# #
# # What it does:
# # - On first run (empty DBPATH), it starts mongod without auth temporarily to initialize:
# #   - Creates an admin root user if MONGO_ADMIN_USERNAME/MONGO_ADMIN_PASSWORD are set
# #   - Creates an application database if MONGO_DATABASE is set
# #   - Creates an application user with readWrite on that DB if MONGO_APP_USERNAME/MONGO_APP_PASSWORD are set
# #   - Then gracefully stops mongod and restarts it with --auth enabled
# # - On subsequent runs (non-empty DBPATH):
# #   - If root credentials are provided, starts mongod with --auth
# #   - Otherwise starts mongod without auth (backward compatibility)
# #
# # Usage:
# #   docker run -e MONGO_ADMIN_USERNAME=admin \
# #              -e MONGO_ADMIN_PASSWORD=secret \
# #              -e MONGO_DATABASE=appdb \
# #              -e MONGO_APP_USERNAME=appuser \
# #              -e MONGO_APP_PASSWORD=apppass \
# #              -v mongodb-data:/data/db <image>
# #
# #   For help inside the container:
# #     docker run --rm <image> --help
# #
# # Environment variables:
# #   MONGO_ADMIN_USERNAME         Admin user name (creates root@admin)
# #   MONGO_ADMIN_PASSWORD         Admin user password
# #   MONGO_DATABASE               Application database name (e.g., appdb)
# #   MONGO_APP_USERNAME           App user name (granted readWrite on MONGO_DATABASE)
# #   MONGO_APP_PASSWORD           App user password
# #   DBPATH                       Data path (default: /data/db)
# #   PORT                         MongoDB port (default: 27017)
# #   BIND_IP                      Bind address (default: 0.0.0.0)

# # Environment variables to control initialization and auth
# MONGO_ADMIN_USERNAME=${MONGO_ADMIN_USERNAME:-}
# MONGO_ADMIN_PASSWORD=${MONGO_ADMIN_PASSWORD:-}
# MONGO_APP_USERNAME=${MONGO_APP_USERNAME:-}
# MONGO_APP_PASSWORD=${MONGO_APP_PASSWORD:-}
# MONGO_DATABASE=${MONGO_DATABASE:-}
# MONGO_AUTH_MODE=${MONGO_AUTH_MODE:-auto}
# MONGO_KEYFILE_PATH=${MONGO_KEYFILE_PATH:-}

# DBPATH=${DBPATH:-/data/db}
# PORT=${PORT:-27017}
# BIND_IP=${BIND_IP:-0.0.0.0}

# log() { printf '[mongo-entrypoint] %s\n' "$*"; }

# # Remove stray Windows CRs from env vars (common when --env-file uses CRLF)
# strip_cr_var() {
#   local name="$1"
#   if [ -n "${!name:-}" ]; then
#     # shellcheck disable=SC2086
#     printf -v "$name" '%s' "${!name%$'\r'}"
#     # also remove any internal CRs just in case
#     printf -v "$name" '%s' "${!name//$'\r'/}"
#   fi
# }

# # Escape a Bash string for safe insertion into JS double-quoted strings
# js_escape() {
#   local s="$1"
#   # Escape backslashes and double quotes
#   s=${s//\\/\\\\}
#   s=${s//\"/\\\"}
#   printf '%s' "$s"
# }

# print_usage() {
#   cat <<EOF
# MongoDB init/auth entrypoint

# On first run (empty DBPATH), initializes optional users/DB/collection, then restarts with --auth.
# On subsequent runs, starts with --auth if root user envs are provided; otherwise without auth.

# Environment variables:
#   MONGO_ADMIN_USERNAME   Admin user name (creates root@admin)
#   MONGO_ADMIN_PASSWORD   Admin user password
#   MONGO_DATABASE         Application database name (e.g., appdb)
#   MONGO_APP_USERNAME     App user name (readWrite on MONGO_DATABASE)
#   MONGO_APP_PASSWORD     App user password
#   MONGO_AUTH_MODE        Authentication policy: auto (default), enabled, or disabled
#   MONGO_KEYFILE_PATH     Path to replica-set keyFile when auth is enabled
#   DBPATH                       Data path (default: ${DBPATH})
#   PORT                         MongoDB port (default: ${PORT})
#   BIND_IP                      Bind address (default: ${BIND_IP})

# Examples:
#   docker run -e MONGO_ADMIN_USERNAME=admin \\
#              -e MONGO_ADMIN_PASSWORD=secret \\
#              -e MONGO_DATABASE=appdb \\
#              -e MONGO_APP_USERNAME=appuser \\
#              -e MONGO_APP_PASSWORD=apppass \\
#              -v mongodb-data:/data/db <image>
# EOF
# }

# # Early help if requested
# if [[ ${1-} == "-h" || ${1-} == "--help" ]]; then
#   print_usage
#   exit 0
# fi

# MONGOD_EXTRA_ARGS=("$@")

# # Sanitize CRLF on relevant env vars
# for v in MONGO_ADMIN_USERNAME MONGO_ADMIN_PASSWORD MONGO_APP_USERNAME MONGO_APP_PASSWORD MONGO_DATABASE DBPATH PORT BIND_IP MONGO_AUTH_MODE MONGO_KEYFILE_PATH; do
#   strip_cr_var "$v"
# done

# IN_REPLSET=false
# REPLSET_NAME=""
# for ((idx=0; idx<${#MONGOD_EXTRA_ARGS[@]}; ++idx)); do
#   arg=${MONGOD_EXTRA_ARGS[idx]}
#   if [[ "$arg" == "--replSet" ]]; then
#     IN_REPLSET=true
#     if (( idx + 1 < ${#MONGOD_EXTRA_ARGS[@]} )); then
#       REPLSET_NAME=${MONGOD_EXTRA_ARGS[idx+1]}
#     fi
#     break
#   fi
# done

# WANT_AUTH=false
# if [[ -n "$MONGO_ADMIN_USERNAME" && -n "$MONGO_ADMIN_PASSWORD" ]]; then
#   WANT_AUTH=true
# fi

# AUTH_ENABLED=false
# case "$MONGO_AUTH_MODE" in
#   enabled)
#     if [[ "$WANT_AUTH" != true ]]; then
#       log "MONGO_AUTH_MODE=enabled but admin credentials are missing; cannot enable auth."
#       exit 1
#     fi
#     AUTH_ENABLED=true
#     ;;
#   disabled)
#     AUTH_ENABLED=false
#     ;;
#   auto)
#     if [[ "$WANT_AUTH" == true ]]; then
#       AUTH_ENABLED=true
#     fi
#     ;;
#   *)
#     log "Unknown MONGO_AUTH_MODE='$MONGO_AUTH_MODE'; defaulting to auto."
#     if [[ "$WANT_AUTH" == true ]]; then
#       AUTH_ENABLED=true
#     fi
#     ;;
# esac

# if [[ "$AUTH_ENABLED" == true ]]; then
#   if [[ -n "$MONGO_KEYFILE_PATH" ]]; then
#     if [[ ! -f "$MONGO_KEYFILE_PATH" ]]; then
#       log "Key file not found at $MONGO_KEYFILE_PATH; authentication will be disabled."
#       AUTH_ENABLED=false
#     else
#       chmod 600 "$MONGO_KEYFILE_PATH"
#     fi
#   elif [[ "$IN_REPLSET" == true ]]; then
#     if [[ "$MONGO_AUTH_MODE" == "enabled" ]]; then
#       log "Replica set ${REPLSET_NAME:-<unknown>} requires MONGO_KEYFILE_PATH when auth is enabled."
#       exit 1
#     fi
#     log "Replica set ${REPLSET_NAME:-<unknown>} requested but no key file provided; running without auth."
#     AUTH_ENABLED=false
#   fi
# fi

# if [[ "$AUTH_ENABLED" == true ]]; then
#   log "Authentication enabled (mode=$MONGO_AUTH_MODE)."
# else
#   log "Authentication disabled (mode=$MONGO_AUTH_MODE)."
# fi

# # Start mongod without auth to bootstrap if needed
# start_mongod_noauth() {
#   log "Starting mongod (no auth) for initialization..."
#   mongod --bind_ip_all --dbpath "$DBPATH" --port "$PORT" "${MONGOD_EXTRA_ARGS[@]}" --fork --logpath /var/log/mongod_init.log
# }

# stop_mongod() {
#   log "Stopping mongod..."
#   mongosh --quiet --eval "db.getSiblingDB('admin').shutdownServer()" || true
#   # give it a moment
#   sleep 1
# }

# start_mongod_with_auth() {
#   log "Starting mongod with authorization enabled..."
#   local args=(--bind_ip "$BIND_IP" --dbpath "$DBPATH" --port "$PORT")
#   args+=("${MONGOD_EXTRA_ARGS[@]}")
#   if [[ -n "$MONGO_KEYFILE_PATH" ]]; then
#     args+=(--keyFile "$MONGO_KEYFILE_PATH")
#   fi
#   args+=(--auth)
#   exec mongod "${args[@]}"
# }

# start_mongod_without_auth() {
#   log "Starting mongod without authorization..."
#   local args=(--bind_ip "$BIND_IP" --dbpath "$DBPATH" --port "$PORT")
#   args+=("${MONGOD_EXTRA_ARGS[@]}")
#   exec mongod "${args[@]}"
# }

# init_js_tmp=$(mktemp)
# trap 'rm -f "$init_js_tmp"' EXIT

# needs_init=true
# if [[ -d "$DBPATH" ]]; then
#   # Consider database initialized if there are collection files
#   if find "$DBPATH" -mindepth 1 -type f | grep -q .; then
#     needs_init=false
#   fi
# fi

# if $needs_init; then
#   start_mongod_noauth

#   if [[ "$AUTH_ENABLED" == true ]]; then
#     RU_E=$(js_escape "$MONGO_ADMIN_USERNAME")
#     RP_E=$(js_escape "$MONGO_ADMIN_PASSWORD")
#     cat >"$init_js_tmp" <<JS
# // Create admin user
# const adminDb = db.getSiblingDB('admin');
# adminDb.createUser({user: "$RU_E", pwd: "$RP_E", roles: [ { role: 'root', db: 'admin' } ]});
# JS
#     mongosh --quiet "mongodb://127.0.0.1:${PORT}" --file "$init_js_tmp"
#     log "Created root user in admin DB."

#     if [[ -n "$MONGO_DATABASE" ]]; then
#       DB_E=$(js_escape "$MONGO_DATABASE")
#       if [[ -n "$MONGO_APP_USERNAME" && -n "$MONGO_APP_PASSWORD" ]]; then
#         AU_E=$(js_escape "$MONGO_APP_USERNAME")
#         AP_E=$(js_escape "$MONGO_APP_PASSWORD")
# cat >"$init_js_tmp" <<JS
# const appDb = db.getSiblingDB("$DB_E");
# appDb.createUser({user: "$AU_E", pwd: "$AP_E", roles: [ { role: 'readWrite', db: "$DB_E" } ]});
# JS
#         mongosh --quiet "mongodb://127.0.0.1:${PORT}" --file "$init_js_tmp"
#         log "Created app user '$MONGO_APP_USERNAME' in '$MONGO_DATABASE'."
#       else
#         log "No application user credentials supplied; skipping user creation for '$MONGO_DATABASE'."
#       fi
#     elif [[ -n "$MONGO_APP_USERNAME" || -n "$MONGO_APP_PASSWORD" ]]; then
#       log "Application user credentials provided but MONGO_DATABASE is empty; skipping app user creation."
#     fi
#   elif [[ "$WANT_AUTH" == true ]]; then
#     log "Admin credentials provided but authentication disabled; skipping user creation."
#   fi

#   stop_mongod

#   if [[ "$AUTH_ENABLED" == true ]]; then
#     start_mongod_with_auth
#   else
#     start_mongod_without_auth
#   fi
# else
#   if [[ "$AUTH_ENABLED" == true ]]; then
#     start_mongod_with_auth
#   else
#     log "Database appears initialized and authentication disabled; starting without auth."
#     start_mongod_without_auth
#   fi
# fi
