# Docker Compose Quick Reference

Quick command reference for the docker-compose setup.

## Prerequisites

```bash
# Create environment file from template
cp .env.example .env-mongo

# Edit with your credentials
vim .env-mongo  # or nano, code, etc.
```

## Quick Start

```bash
# One-command deployment (recommended for first time)
./docker-compose-quickstart.sh --build

# Or step by step:
docker-compose build          # Build images
docker-compose up -d          # Start containers
./docker-compose-network-setup.sh   # Configure networking
./docker-compose-init-mongo.sh      # Initialize MongoDB
```

## Using Makefile

```bash
# Start everything
make quickstart

# Build images
make build

# Start containers
make up

# Stop containers
make down

# View logs
make logs
make logs-controller
make logs-mongo

# Get status
make status
make ovs-show
make mongo-status

# Run tests
make ping-test

# Clean up
make clean
make reset  # Full reset including network
```

## Common Operations

### Container Management

```bash
# Start all containers
docker-compose up -d

# Stop all containers
docker-compose down

# Restart specific service
docker-compose restart osken

# View logs
docker-compose logs -f mongodb-router

# Execute command in container
docker exec -it container1 bash
docker exec mongodb-router mongosh --host 192.168.100.4 --port 27020
```

### Network Diagnostics

```bash
# Check OVS configuration
docker exec ovs ovs-vsctl show
docker exec ovs ovs-ofctl dump-flows ovs-br0

# Check container connectivity
docker exec container1 ip addr
docker exec container1 ip route
docker exec container1 ping -c 4 10.0.0.4

# Check NAT router
docker exec nat-router ip addr
docker exec nat-router iptables -t nat -L -n -v
```

### MongoDB Operations

```bash
# Check cluster status
docker exec mongodb-router mongosh --host 192.168.100.4 --port 27020 --eval "sh.status()"

# Check config server
docker exec mongodb-config-server mongosh --host 192.168.100.4 --port 27019 --eval "rs.status()"

# Check shards
docker exec mongodb-n1 mongosh --host 10.0.0.4 --port 27018 --eval "rs.status()"
docker exec mongodb-n2 mongosh --host 10.0.1.4 --port 27018 --eval "rs.status()"

# Connect to router
docker exec -it mongodb-router mongosh --host 192.168.100.4 --port 27020
```

### Controller Operations

```bash
# View controller logs
docker-compose logs -f osken
docker-compose logs -f osken_2

# Restart controllers
docker-compose restart osken osken_2

# Configure controllers
docker exec ovs ovs-vsctl set-controller ovs-br0 tcp:127.0.0.1:6653
docker exec ovs ovs-vsctl set-controller ovs-br1 tcp:127.0.0.1:6654
```

## Troubleshooting

### Containers won't start

```bash
# Check status
docker-compose ps

# View logs
docker-compose logs <service-name>

# Rebuild and restart
docker-compose build <service-name>
docker-compose up -d --force-recreate <service-name>
```

### Network issues

```bash
# Re-run network setup
./docker-compose-network-setup.sh

# Check veth pairs
ip link show | grep veth

# Check routes
ip route show
docker exec nat-router ip route
```

### MongoDB initialization fails

```bash
# Re-run initialization
./docker-compose-init-mongo.sh

# Check if containers are reachable
docker exec mongodb-config-server mongosh --host 192.168.100.4 --port 27019 --eval "db.runCommand({ping:1})"
```

## Environment Variables

Key variables in `.env-mongo`:

```bash
MONGO_INITDB_ROOT_USERNAME=admin
MONGO_INITDB_ROOT_PASSWORD=admin-password
MONGO_ROUTER_HOST=192.168.100.4
MONGO_ROUTER_PORT=27020
OSKEN1_PORT=6653
OSKEN2_PORT=6654
```

## File Structure

```
.
├── docker-compose.yml              # Main compose configuration
├── docker-compose-network-setup.sh # Network topology setup
├── docker-compose-init-mongo.sh    # MongoDB initialization
├── docker-compose-quickstart.sh    # One-command deployment
├── Makefile                        # Convenient shortcuts
├── .env-mongo                      # Environment variables (create from .env.example)
├── .env.example                    # Template for .env-mongo
├── DOCKER_COMPOSE.md               # Comprehensive documentation
└── source/
    ├── docker/                     # Dockerfiles
    └── scripts/                    # Original scripts
```

## Service Overview

| Service | Container Name | Network Mode | Purpose |
|---------|----------------|--------------|---------|
| ovs | ovs | host | Open vSwitch |
| nat-router | nat-router | none | NAT/routing |
| mongodb-config-server | mongodb-config-server | host | Config server |
| mongodb-n1 | mongodb-n1 | none | Shard 1 |
| mongodb-n2 | mongodb-n2 | none | Shard 2 |
| mongodb-router | mongodb-router | host | mongos router |
| osken | osken | host | Controller 1 |
| osken_2 | osken_2 | host | Controller 2 |
| container1-5 | container1-5 | none | Test hosts |

## Network Topology

- **Network 1 (10.0.0.0/24)**: ovs-br0, ovs-br2 → container1, container2, container5, mongodb-n1
- **Network 2 (10.0.1.0/24)**: ovs-br1 → container3, container4, mongodb-n2
- **Management (192.168.100.0/24)**: Host, router, config server, mongos

## Ports

- **27019**: Config server
- **27020**: MongoDB router (mongos)
- **27018**: Shard (internal)
- **27118**: Shard 2 (via DNAT on router)
- **6653**: OS-Ken controller 1
- **6654**: OS-Ken controller 2

## Comparison with Original Scripts

| Operation | Original | Docker Compose |
|-----------|----------|----------------|
| Build images | `./source/scripts/build_images.sh` | `docker-compose build` or `make build` |
| Start lab | `./source/scripts/build_setup.sh` | `./docker-compose-quickstart.sh` or `make quickstart` |
| View logs | `docker logs <container>` | `docker-compose logs <service>` or `make logs` |
| Stop lab | Manual cleanup | `docker-compose down` or `make down` |
| Clean up | `./source/scripts/cleanup.sh` | `make clean` or `make reset` |

## Tips

1. **First time setup**: Use `make quickstart` or `./docker-compose-quickstart.sh --build`
2. **Development**: Use `docker-compose up -d` and restart individual services as needed
3. **Debugging**: Use `make logs-<service>` to view specific service logs
4. **Testing**: Use original test scripts in `source/scripts/`
5. **Cleanup**: Use `make reset` for complete cleanup

For detailed documentation, see [DOCKER_COMPOSE.md](DOCKER_COMPOSE.md).
