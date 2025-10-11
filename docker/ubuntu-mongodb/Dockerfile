FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install MongoDB (from MongoDB upstream APT repo)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates curl gnupg iputils-ping net-tools \
	&& rm -rf /var/lib/apt/lists/* \
	# Add MongoDB GPG key and repo for Ubuntu 22.04 (jammy)
	&& mkdir -p /etc/apt/keyrings \
	&& curl -fsSL https://pgp.mongodb.com/server-7.0.asc | gpg --dearmor -o /etc/apt/keyrings/mongodb-server-7.0.gpg \
	&& echo "deb [signed-by=/etc/apt/keyrings/mongodb-server-7.0.gpg arch=$(dpkg --print-architecture)] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" \
	     > /etc/apt/sources.list.d/mongodb-org-7.0.list \
	&& apt-get update \
	&& apt-get install -y --no-install-recommends mongodb-org \
	&& rm -rf /var/lib/apt/lists/*

# Data directory
RUN mkdir -p /data/db \
	&& chown -R root:root /data/db

VOLUME ["/data/db"]

# Expose default MongoDB port (documentational, networking is handled externally)
EXPOSE 27017

# Healthcheck script that works with or without auth (uses env if provided)
COPY healthcheck-mongo.sh /usr/local/bin/healthcheck-mongo.sh
RUN chmod +x /usr/local/bin/healthcheck-mongo.sh
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=5 CMD /usr/local/bin/healthcheck-mongo.sh || exit 1

# Add entrypoint for initialization and auth enablement
COPY entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["mongod"]

