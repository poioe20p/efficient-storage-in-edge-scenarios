#!/usr/bin/env bash
set -euo pipefail

# Build optional --replSet argument: only passed when MONGO_REPLSET is non-empty.
MONGOD_ARGS="--bind_ip_all"
if [ -n "${MONGO_REPLSET:-}" ]; then
    MONGOD_ARGS="$MONGOD_ARGS --replSet $MONGO_REPLSET"
fi

# Start mongod in the background.
# shellcheck disable=SC2086
mongod $MONGOD_ARGS &
MONGOD_PID=$!

# Wait until mongod accepts connections before starting the sidecar.
until mongosh --quiet --eval "db.runCommand({ping:1})" >/dev/null 2>&1; do
    sleep 1
done

# Start the telemetry sidecar in the background.
# If it crashes, mongod (and therefore the container) keeps running.
python3 /mongo_telemetry.py &

# The container lives as long as mongod does.
wait $MONGOD_PID
