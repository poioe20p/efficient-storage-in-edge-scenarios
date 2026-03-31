#!/usr/bin/env bash
set -euo pipefail

# Build mongod arguments from env vars.
MONGOD_ARGS="--bind_ip_all"
if [ -n "${MONGO_REPLSET:-}" ]; then
    MONGOD_ARGS="$MONGOD_ARGS --replSet $MONGO_REPLSET"
fi
if [ -n "${MONGO_PORT:-}" ]; then
    MONGOD_ARGS="$MONGOD_ARGS --port $MONGO_PORT"
fi

# Derive MONGO_URI from MONGO_PORT so the sidecar connects to the right port.
export MONGO_URI="${MONGO_URI:-mongodb://localhost:${MONGO_PORT:-27018}/}"

# Start mongod in the background.
# shellcheck disable=SC2086
mongod $MONGOD_ARGS &
MONGOD_PID=$!

# Wait until mongod accepts connections before starting the sidecar.
until mongosh --port "${MONGO_PORT:-27018}" --quiet --eval "db.runCommand({ping:1})" >/dev/null 2>&1; do
    sleep 1
done

# Start the telemetry sidecar in the background.
# If it crashes, mongod (and therefore the container) keeps running.
python3 /mongo_telemetry.py &

# The container lives as long as mongod does.
wait $MONGOD_PID
