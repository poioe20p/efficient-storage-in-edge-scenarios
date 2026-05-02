# Dockerfile: ubuntu-tools
FROM ubuntu:latest

# iproute2 provides `tc`, used by scripts/network/inject_wan_latency.sh
# to model inter-LAN WAN latency via netem (see docs/operation/topology).
RUN apt-get update && \
    apt-get install -y iputils-ping net-tools iproute2 && \
    apt-get clean

CMD ["/bin/bash"]
