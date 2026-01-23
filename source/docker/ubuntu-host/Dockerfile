FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
DB_URL=mongodb://10.0.0.4:27017/test \
MONGO_VERSION=7.0

# Base networking tools + MongoDB mongosh client
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates curl gnupg iputils-ping net-tools iperf3 \
    && rm -rf /var/lib/apt/lists/* \
    # Add MongoDB repo (7.0 for jammy)
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://pgp.mongodb.com/server-${MONGO_VERSION}.asc | gpg --dearmor -o /etc/apt/keyrings/mongodb-server-${MONGO_VERSION}.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/mongodb-server-${MONGO_VERSION}.gpg arch=$(dpkg --print-architecture)] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/${MONGO_VERSION} multiverse" \
       > /etc/apt/sources.list.d/mongodb-org-${MONGO_VERSION}.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends mongodb-mongosh \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

CMD ["/bin/bash"]
