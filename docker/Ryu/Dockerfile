FROM python:3.9-slim

ENV PYTHONUNBUFFERED=1 \
	PIP_NO_CACHE_DIR=1

# # Eventlet's greendns shim in upstream Ryu cannot handle PyMongo's
# # getaddrinfo(type=...) call, so disable it to avoid heartbeat failures.
ENV EVENTLET_NO_GREENDNS=1

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

COPY ryu/ /workspace/ryu/
COPY docker/Ryu/entrypoint.sh /usr/local/bin/ryu-entrypoint.sh

RUN pip install --upgrade pip setuptools wheel && \
	pip install -e /workspace/ryu && \
	pip install os-ken && \
	pip install python-dotenv pymongo && \
	chmod +x /usr/local/bin/ryu-entrypoint.sh
	
# run ryu-manager as an entrypoint is needed because of how docker handles CMD
# ryu-manager is the console entry script installed with the Ryu (or OS-Ken) Python package.
# When pip installs the package it reads the console_scripts entry points in the package’s setup.py 
# and drops a launcher into /usr/local/bin/. Because that directory lives on the container’s PATH, 
# Docker can invoke it by name; our ENTRYPOINT ["ryu-manager"] simply runs that preinstalled executable,
# which imports the package’s code and boots the controller runtime.
ENTRYPOINT ["/usr/local/bin/ryu-entrypoint.sh"]
CMD ["--verbose", "sdn_controller.ryu_learn_and_log"]