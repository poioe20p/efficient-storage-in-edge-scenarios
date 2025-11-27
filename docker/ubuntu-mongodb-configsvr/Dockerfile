FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
MONGO_VERSION=7.0

# Install MongoDB (from MongoDB upstream APT repo)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates curl gnupg iputils-ping net-tools \
    && rm -rf /var/lib/apt/lists/* \
    # Add MongoDB GPG key and repo for Ubuntu 22.04 (jammy)
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://pgp.mongodb.com/server-${MONGO_VERSION}.asc | gpg --dearmor -o /etc/apt/keyrings/mongodb-server-${MONGO_VERSION}.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/mongodb-server-${MONGO_VERSION}.gpg arch=$(dpkg --print-architecture)] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/${MONGO_VERSION} multiverse" \
         > /etc/apt/sources.list.d/mongodb-org-${MONGO_VERSION}.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends mongodb-org \
    && rm -rf /var/lib/apt/lists/*

# Data directory for config server
RUN mkdir -p /data/configdb \
    && chown -R root:root /data/configdb

VOLUME ["/data/configdb"]

# Expose default config server port
EXPOSE 27019

## No custom entrypoint needed; Docker will run CMD directly
CMD ["mongod", "--configsvr", "--replSet", "configReplSet", "--port", "27019", "--dbpath", "/data/configdb", "--bind_ip_all"]
