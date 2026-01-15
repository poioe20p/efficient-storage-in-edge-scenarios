# Docker Quick Commands Cheat Sheet

A minimal set of everyday Docker commands with brief notes.

## Setup and Info~

- `docker --version` — show client version
- `docker info` — system-wide info (daemon, storage, etc.)
- `docker login` — authenticate to a registry
- `docker logout` — remove registry creds

## Images

- `docker pull ubuntu:22.04` — download image
- `docker images` — list local images
- `docker image ls` — same as above
- `docker rmi IMAGE` — remove image
- `docker image prune` — remove unused (dangling) images
- `docker build -t NAME:TAG .` — build image from Dockerfile
- `docker tag SRC:TAG DEST:TAG` — retag image
- `docker push NAME:TAG` — upload to registry
- `docker history IMAGE` — show image layer history
- `docker inspect IMAGE` — low-level details (JSON)
- `docker build --no-cache -t <name> <where>` -

## Containers (run/exec/stop)

- `docker run IMAGE` — run container (foreground)
- `docker run -it IMAGE bash` — interactive shell
- `docker run -d IMAGE` — run detached (background)
- `docker run --name NAME IMAGE` — set container name
- `docker run -p 8080:80 IMAGE` — map host 8080 -> container 80
- `docker run -v HOST_PATH:CONT_PATH IMAGE` — bind mount
- `docker run --rm IMAGE` — auto-remove on exit
- `docker ps` — list running containers
- `docker ps -a` — list all (including exited)
- `docker stop CONTAINER` — graceful stop
- `docker kill CONTAINER` — force stop (SIGKILL)
- `docker start CONTAINER` — start existing container
- `docker restart CONTAINER` — restart container
- `docker rm CONTAINER` — remove container
- `docker logs CONTAINER` — show logs
- `docker logs -f CONTAINER` — follow logs
- `docker exec -it CONTAINER bash` — run command in running container
- `docker cp CONTAINER:SRC HOST_DST` — copy from container
- `docker cp HOST_SRC CONTAINER:DST` — copy to container
- `docker rename OLD NEW` — rename container
- `docker attach CONTAINER` — attach to STDIN/STDOUT

## Networks

- `docker network ls` — list networks
- `docker network create NAME` — create network
- `docker network inspect NAME` — details
- `docker network rm NAME` — remove network
- `docker run --network NAME IMAGE` — attach container to network

## Volumes and Storage

- `docker volume ls` — list volumes
- `docker volume create NAME` — create volume
- `docker volume inspect NAME` — details
- `docker volume rm NAME` — remove volume
- `docker system df` — disk usage (images/containers/volumes)
- `docker system prune` — remove unused data (confirm prompt)
- `docker system prune -a` — also remove unused images

## Inspect and Debug

- `docker inspect CONTAINER` — detailed config/state
- `docker top CONTAINER` — processes inside container
- `docker stats` — live CPU/mem/IO usage
- `docker events` — real-time events stream
- `docker port CONTAINER` — port mappings

## Registries and Cleanup

- `docker image prune -a` — remove all unused images