FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    MONGO_VERSION=7.0 \
    SERVER_ID=mongo-unknown \
    AGGREGATOR_PULL_ADDR=tcp://10.0.0.5:5555 \
    MONGO_URI=mongodb://localhost:27017/ \
    TELEMETRY_INTERVAL_S=10 \
    MONGO_REPLSET=

# Install MongoDB + Python for the telemetry sidecar
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates curl gnupg iputils-ping net-tools iperf3 \
       python3 python3-pip \
    && rm -rf /var/lib/apt/lists/* \
    # Add MongoDB GPG key and repo for Ubuntu 22.04 (jammy)
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://pgp.mongodb.com/server-${MONGO_VERSION}.asc | gpg --dearmor -o /etc/apt/keyrings/mongodb-server-${MONGO_VERSION}.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/mongodb-server-${MONGO_VERSION}.gpg arch=$(dpkg --print-architecture)] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/${MONGO_VERSION} multiverse" \
         > /etc/apt/sources.list.d/mongodb-org-${MONGO_VERSION}.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends mongodb-org \
    && rm -rf /var/lib/apt/lists/*

RUN pip3 install --no-cache-dir pyzmq psutil pymongo

# Data directory
RUN mkdir -p /data/db \
    && chown -R root:root /data/db

COPY mongo_telemetry.py /mongo_telemetry.py
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

VOLUME ["/data/db"]

# Expose default MongoDB port (documentational, networking is handled externally)
EXPOSE 27017

CMD ["/entrypoint.sh"]
