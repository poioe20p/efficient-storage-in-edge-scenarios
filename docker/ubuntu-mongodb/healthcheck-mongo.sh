#!/usr/bin/env bash
set -euo pipefail

# Try without auth first (for non-auth setups)
if mongosh --quiet --eval "db.adminCommand('ping')" >/dev/null 2>&1; then
  exit 0
fi

# If auth is enabled, try with root credentials if provided
if [[ -n "${MONGO_INITDB_ROOT_USERNAME:-}" && -n "${MONGO_INITDB_ROOT_PASSWORD:-}" ]]; then
  if mongosh --quiet "mongodb://${MONGO_INITDB_ROOT_USERNAME}:${MONGO_INITDB_ROOT_PASSWORD}@127.0.0.1:27017/admin" --eval "db.adminCommand('ping')" >/dev/null 2>&1; then
    exit 0
  fi
fi

exit 1
