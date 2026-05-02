#!/usr/bin/env bash
# source/docker/edge_selective_storage/entrypoint.sh
#
# Boots a standalone mongod (no --replSet), waits for it to accept
# connections, then launches the telemetry sidecar and the selective-sync
# supervisor. mongod is the foreground process so the container's lifetime
# is tied to it.

set -euo pipefail

MONGO_PORT="${MONGO_PORT:-27018}"

# mongod args: standalone (no --replSet, unlike edge_storage_server).
MONGOD_ARGS="--bind_ip_all --port ${MONGO_PORT}"

# Derive MONGO_URI from MONGO_PORT so the telemetry sidecar connects
# to the right port (same contract as edge_storage_server/entrypoint.sh).
export MONGO_URI="${MONGO_URI:-mongodb://localhost:${MONGO_PORT}/}"

# Ensure the resume-token directory exists before the supervisor starts.
mkdir -p /var/lib/selective_sync

# Forward SIGTERM to mongod so it gets a clean shutdown (quiesce).
trap 'kill -TERM "$MONGOD_PID" 2>/dev/null || true; wait "$MONGOD_PID"; exit $?' SIGTERM

# shellcheck disable=SC2086
mongod $MONGOD_ARGS &
MONGOD_PID=$!

# Wait for mongod to accept connections before launching dependants.
until mongosh --port "${MONGO_PORT}" --quiet \
        --eval "db.runCommand({ping:1})" >/dev/null 2>&1; do
    sleep 1
done

# Telemetry sidecar (host + STANDALONE_CACHE state).
# If it crashes, mongod (and therefore the container) keeps running.
python3 /mongo_telemetry.py &

# Selective-sync supervisor: one ForwarderWorker per hot collection
# plus the /forwarder_config admin endpoint.
python3 /selective_sync_supervisor.py &

# Container lives as long as mongod does.
wait "$MONGOD_PID"
