FROM python:3.10-slim-bullseye

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
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
COPY logging.conf /etc/osken/logging.conf

# 3. Install Python Dependencies
# We pin eventlet to 0.33.3 to avoid SSL crashes common in newer versions
RUN pip install --upgrade pip setuptools wheel && \
    pip install os-ken==3.1.1 && \
    pip install eventlet python-dotenv pymongo networkx mininet

# 4. Define the Entrypoint
# We use 'python -m' to bypass potential PATH issues with the binary script.
ENTRYPOINT ["python3", "-m", "os_ken.cmd.manager"]

# 5. Default Command (Can be overridden by docker run)
# By default, show help if no script is provided
CMD ["--help"]