FROM python:3.9-slim

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
	&& rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY /ryu/ /workspace/ryu/

RUN pip install --upgrade pip setuptools wheel && \
	pip install -e /workspace/ryu && \
	pip install python-dotenv pymongo

ENTRYPOINT ["ryu-manager"]
CMD ["--verbose", "ryu.app.simple_switch_13"]
