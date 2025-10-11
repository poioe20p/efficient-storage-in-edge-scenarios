FROM ubuntu:22.04

ENV [DEBIAN_FRONTEND=noninteractive, DB_URL=mongodb://10.0.0.4:27017/test]

# Base networking tools + MongoDB mongosh client
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates curl gnupg iputils-ping net-tools \
    && rm -rf /var/lib/apt/lists/* \
    # Add MongoDB repo (7.0 for jammy)
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://pgp.mongodb.com/server-7.0.asc | gpg --dearmor -o /etc/apt/keyrings/mongodb-server-7.0.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/mongodb-server-7.0.gpg arch=$(dpkg --print-architecture)] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" \
       > /etc/apt/sources.list.d/mongodb-org-7.0.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends mongodb-mongosh \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

CMD ["/bin/bash"]
