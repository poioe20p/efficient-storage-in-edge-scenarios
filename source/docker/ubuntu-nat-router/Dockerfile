# Dockerfile: ubuntu-tools
FROM ubuntu:latest

RUN apt-get update && \
    apt-get install -y iputils-ping net-tools && \
    apt-get clean

CMD ["/bin/bash"]
