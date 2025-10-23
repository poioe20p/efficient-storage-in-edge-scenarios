FROM python:3.11-slim

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

RUN pip install --upgrade pip setuptools wheel && \
	pip install os-ken && \
	pip install python-dotenv pymongo

ENTRYPOINT ["osken-manager"]
CMD ["--verbose", "sdn_controller.osken_learn_and_log"]
