FROM python:3.10-slim-bullseye

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        git \
        libxml2-dev \
        libxslt1-dev \
        libffi-dev \
        libssl-dev \
        netcat-openbsd \
        wget \
        ca-certificates \
        gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install MongoDB mongos (7.0) for bullseye with proper key handling
RUN wget -qO /tmp/mongodb-server-7.0.asc https://www.mongodb.org/static/pgp/server-7.0.asc && \
    gpg --dearmor -o /usr/share/keyrings/mongodb-server-7.0.gpg /tmp/mongodb-server-7.0.asc && \
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg] https://repo.mongodb.org/apt/debian bullseye/mongodb-org/7.0 main" > /etc/apt/sources.list.d/mongodb-org-7.0.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends mongodb-org-mongos && \
    rm -rf /var/lib/apt/lists/* /tmp/mongodb-server-7.0.asc

WORKDIR /workspace

RUN pip install --upgrade pip setuptools wheel && \
    pip install "git+https://github.com/openstack/os-ken.git" && \
    pip install eventlet==0.33.3 python-dotenv pymongo

# Use python module execution instead of binary shim to avoid PATH issues
ENTRYPOINT ["python3", "-m", "os_ken.cmd.manager"]

# Default Arguments
CMD ["--verbose", "sdn_controller.osken_learn_and_log"]