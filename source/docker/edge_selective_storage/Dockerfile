# source/docker/edge_selective_storage/Dockerfile
#
# Tier 1 "selective sync" storage node:
#   - mongod running standalone (no --replSet) on port 27018.
#   - mongo_telemetry sidecar (inherited from edge_storage_server) reporting
#     host + member state as STANDALONE_CACHE.
#   - selective_sync_supervisor.py running one ForwarderWorker thread per
#     hot collection, plus a Flask admin endpoint on :5001.
#
# Build ordering: requires edge_storage_server:latest to be built first.
FROM edge_storage_server:latest

RUN pip3 install --no-cache-dir flask

COPY config.py /config.py
COPY resume_token.py /resume_token.py
COPY telemetry.py /telemetry.py
COPY forwarder.py /forwarder.py
COPY admin.py /admin.py
COPY selective_sync_supervisor.py /selective_sync_supervisor.py
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Admin endpoint (POST /forwarder_config) for live reconfigure.
EXPOSE 5001

# Persistent resume-token storage per collection.
VOLUME ["/var/lib/selective_sync"]

CMD ["/entrypoint.sh"]
