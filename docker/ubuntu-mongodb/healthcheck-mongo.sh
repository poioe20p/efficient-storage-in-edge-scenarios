#!/usr/bin/env bash
set -euo pipefail

# Strip trailing CR if env file used CRLF on Windows
strip_cr() {
  local v="$1"
  v="${v%$'\r'}"; v="${v//$'\r'/}"
  printf '%s' "$v"
}

ADMIN_USER=$(strip_cr "${MONGO_ADMIN_USERNAME:-}")
ADMIN_PASS=$(strip_cr "${MONGO_ADMIN_PASSWORD:-}")
APP_DB=$(strip_cr "${MONGO_DATABASE:-}")
APP_USER=$(strip_cr "${MONGO_APP_USERNAME:-}")
APP_PASS=$(strip_cr "${MONGO_APP_PASSWORD:-}")

# 1) Try without auth first (non-auth setups)
if mongosh --quiet --eval "db.adminCommand('ping')" >/dev/null 2>&1; then
  exit 0
fi

# 2) Try root credentials against admin
if [[ -n "$ADMIN_USER" && -n "$ADMIN_PASS" ]]; then
  if mongosh --quiet "mongodb://${ADMIN_USER}:${ADMIN_PASS}@127.0.0.1:27017/admin" --eval "db.adminCommand('ping')" >/dev/null 2>&1; then
    exit 0
  fi
fi

# 3) Try app credentials against app DB, if provided
if [[ -n "$APP_DB" && -n "$APP_USER" && -n "$APP_PASS" ]]; then
  if mongosh --quiet "mongodb://${APP_USER}:${APP_PASS}@127.0.0.1:27017/${APP_DB}?authSource=${APP_DB}" --eval "db.runCommand({ping:1})" >/dev/null 2>&1; then
    exit 0
  fi
fi

exit 1
