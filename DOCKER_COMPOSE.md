# Docker Compose Setup Guide

This document explains how to use Docker Compose to manage the efficient-storage-in-edge-scenarios lab environment as an alternative to the existing shell scripts.

## Overview

The Docker Compose setup provides a declarative way to manage container lifecycle while still relying on companion scripts for complex network setup. This approach offers:

- **Simplified container management**: Start/stop all containers with single commands
- **Declarative configuration**: Services, volumes, and dependencies defined in YAML
- **Better development workflow**: Easier to understand and modify than complex shell scripts
- **Preserved functionality**: All features from the original scripts are maintained

## Important Notes

⚠️ **Docker Compose cannot fully replace the bash scripts** due to:

1. **Network namespace operations**: Creating and configuring veth pairs requires direct namespace manipulation
2. **Dynamic PID-based operations**: Container PIDs are needed for namespace operations
3. **Complex iptables rules**: NAT/DNAT/SNAT rules and routing require precise sequencing
4. **OVS configuration**: Switch setup and controller attachment needs timing coordination

The solution uses **Docker Compose for orchestration** + **companion script for network plumbing**.

## Prerequisites

1. **Docker and Docker Compose** installed
2. **Root/sudo privileges** for network operations
3. **MongoDB credentials** configured in `.env-mongo` (see [MongoDB setup](docs/setups/mongodb.md))
4. **Ubuntu VM environment** as documented in the project README

## Directory Structure

```
efficient-storage-in-edge-scenarios/
├── docker-compose.yml              # Main compose file (container definitions)
├── docker-compose-network-setup.sh # Network plumbing script
├── docker-compose-init-mongo.sh    # MongoDB initialization script
├── .env-mongo                      # MongoDB credentials (create this)
└── source/
    ├── docker/                     # Dockerfiles for each service
    └── scripts/                    # Original scripts (still useful for reference)
```

## Quick Start

### 1. Prepare MongoDB Credentials

Create `.env-mongo` in the project root:

```bash
# MongoDB Admin Credentials
MONGO_INITDB_ROOT_USERNAME=admin
MONGO_INITDB_ROOT_PASSWORD=admin-password

# MongoDB Application Credentials
MONGO_APP_USER=app_user
MONGO_APP_PASSWORD=app-password
MONGO_APP_DB=app_db

# MongoDB Connection Details
MONGO_ROUTER_HOST=192.168.100.4
MONGO_ROUTER_PORT=27020
MONGO_CONFIG_HOST=192.168.100.4
MONGO_CONFIG_PORT=27019
```

### 2. Build All Images

```bash
# Option 1: Using docker-compose
docker-compose build

# Option 2: Using the existing script (recommended for first-time setup)
cd source/scripts
./build_images.sh
```

### 3. Start All Containers

```bash
# Start all services in detached mode
docker-compose up -d

# Verify all containers are running
docker-compose ps
```

Expected output should show all services as "Up":
- ovs
- nat-router
- mongodb-config-server
- mongodb-n1, mongodb-n2
- mongodb-router
- osken, osken_2
- container1, container2, container3, container4, container5

### 4. Configure Network Topology

The network setup script creates veth pairs, configures namespaces, and sets up routing:

```bash
# Run the network setup script
./docker-compose-network-setup.sh
```

This script:
- Creates veth pairs for all containers
- Moves interfaces into correct namespaces
- Configures IP addresses and MAC addresses
- Sets up NAT router interfaces and routing
- Configures iptables rules for DNAT/SNAT
- Establishes host routes to lab networks

### 5. Initialize MongoDB Cluster

```bash
# Run the MongoDB initialization script
./docker-compose-init-mongo.sh
```

This script:
- Initializes config server replica set
- Initializes shard replica sets (rs_net1, rs_net2)
- Waits for all replica sets to elect PRIMARY
- Adds shards to the router
- Enables sharding on database and collections
- Configures shard zones and key ranges

### 6. Configure SDN Controllers

```bash
# Point OVS switches to the controllers
docker exec ovs ovs-vsctl set-controller ovs-br0 tcp:127.0.0.1:6653
docker exec ovs ovs-vsctl set-controller ovs-br1 tcp:127.0.0.1:6654
docker exec ovs ovs-vsctl set-controller ovs-br2 tcp:127.0.0.1:6653

# Verify controller connections
docker exec ovs ovs-vsctl show
```

### 7. Verify Setup

```bash
# Check connectivity (if test script exists)
cd source/scripts
./test_connectivity.sh

# Check MongoDB cluster status
docker exec mongodb-router mongosh --host 192.168.100.4 --port 27020 --eval "sh.status()"

# View controller logs
docker-compose logs -f osken
docker-compose logs -f osken_2
```

## Common Operations

### View Container Logs

```bash
# All services
docker-compose logs -f

# Specific service
docker-compose logs -f mongodb-n1
docker-compose logs -f osken

# Last 100 lines
docker-compose logs --tail=100 ovs
```

### Restart Services

```bash
# Restart all services
docker-compose restart

# Restart specific service
docker-compose restart mongodb-n1

# Restart controllers
docker-compose restart osken osken_2
```

### Stop All Services

```bash
# Stop all services (containers remain, can be restarted)
docker-compose stop

# Stop and remove all containers (volumes preserved)
docker-compose down

# Remove everything including volumes
docker-compose down -v
```

### Rebuild Specific Service

```bash
# Rebuild and recreate a specific service
docker-compose up -d --build --force-recreate osken

# Rebuild a service from scratch
docker-compose build --no-cache osken
docker-compose up -d osken
```

### Execute Commands in Containers

```bash
# MongoDB operations
docker-compose exec mongodb-n1 mongosh --host 10.0.0.4 --port 27018

# Network diagnostics
docker-compose exec container1 ping -c 4 10.0.0.4
docker-compose exec container3 ping -c 4 10.0.1.4

# OVS operations
docker-compose exec ovs ovs-vsctl show
docker-compose exec ovs ovs-ofctl dump-flows ovs-br0
```

## Network Architecture

The compose setup maintains the same network architecture as the original scripts:

### Network 1 (10.0.0.0/24)
- **ovs-br0**: OVS bridge
- **ovs-br2**: Secondary OVS bridge (connected via veth8/veth8-peer)
- **container1**: 10.0.0.2
- **container2**: 10.0.0.3
- **mongodb-n1**: 10.0.0.4 (shard rs_net1)
- **container5**: 10.0.0.5
- **NAT router eth1**: 10.0.0.1 (gateway)

### Network 2 (10.0.1.0/24)
- **ovs-br1**: OVS bridge
- **container3**: 10.0.1.2
- **container4**: 10.0.1.3
- **mongodb-n2**: 10.0.1.4 (shard rs_net2)
- **NAT router eth2**: 10.0.1.1 (gateway)

### Management Network (192.168.100.0/24)
- **Host (enp0s3)**: 192.168.100.4
- **Host (veth4)**: 192.168.100.1
- **NAT router eth0**: 192.168.100.2
- **MongoDB config server**: 192.168.100.4:27019
- **MongoDB router**: 192.168.100.4:27020

### Port Mappings
- **MongoDB config server**: 27019
- **MongoDB router (mongos)**: 27020
- **MongoDB shard 1** (via DNAT): 192.168.100.2:27018 → 10.0.0.4:27018
- **MongoDB shard 2** (via DNAT): 192.168.100.2:27118 → 10.0.1.4:27018
- **OS-Ken controller 1**: 6653 (controls ovs-br0, ovs-br2)
- **OS-Ken controller 2**: 6654 (controls ovs-br1)

## Environment Variables

The compose file supports customization via environment variables:

```bash
# MongoDB connection
export MONGO_ROUTER_HOST=192.168.100.4
export MONGO_ROUTER_PORT=27020
export MONGO_CONFIG_HOST=192.168.100.4
export MONGO_CONFIG_PORT=27019

# OS-Ken controller ports
export OSKEN1_PORT=6653
export OSKEN2_PORT=6654

# Network configuration (for setup script)
export INTERNET_LINK_HOST_IP=172.20.0.1/30
export INTERNET_LINK_ROUTER_IP=172.20.0.2/30
export DEFAULT_UPLINK_IF=enp0s3
```

## Troubleshooting

### Containers fail to start

```bash
# Check service status
docker-compose ps

# View logs
docker-compose logs <service-name>

# Restart problematic service
docker-compose restart <service-name>
```

### Network connectivity issues

```bash
# Verify veth pairs exist
ip link show | grep veth

# Check container IPs
docker exec container1 ip addr show eth0

# Verify routing
docker exec container1 ip route
docker exec nat-router ip route

# Check iptables rules
docker exec nat-router iptables -t nat -L -n -v
```

### MongoDB replica set issues

```bash
# Check replica set status
docker exec mongodb-n1 mongosh --host 10.0.0.4 --port 27018 --eval "rs.status()"
docker exec mongodb-n2 mongosh --host 10.0.1.4 --port 27018 --eval "rs.status()"

# Check config server
docker exec mongodb-config-server mongosh --host 192.168.100.4 --port 27019 --eval "rs.status()"

# Check shard configuration
docker exec mongodb-router mongosh --host 192.168.100.4 --port 27020 --eval "sh.status()"
```

### Controller connection issues

```bash
# Check if controllers are running
docker-compose ps osken osken_2

# View controller logs
docker-compose logs osken
docker-compose logs osken_2

# Check OVS controller configuration
docker exec ovs ovs-vsctl show
docker exec ovs ovs-vsctl get-controller ovs-br0
docker exec ovs ovs-vsctl get-controller ovs-br1
```

## Cleanup

### Partial Cleanup (keep images and volumes)

```bash
docker-compose down
```

### Full Cleanup (remove everything)

```bash
# Stop and remove containers, networks
docker-compose down

# Remove volumes
docker-compose down -v

# Remove network artifacts (veth pairs, routes, iptables rules)
cd source/scripts
./cleanup.sh --network

# Remove images
./cleanup.sh --images
```

### Reset to Clean State

```bash
# Use the original cleanup script for thorough cleanup
cd source/scripts
./cleanup.sh --reset

# Or manually
docker-compose down -v
sudo ip link del veth1 2>/dev/null || true
sudo ip link del veth10 2>/dev/null || true
# ... etc for all veth pairs
```

## Comparison with Original Scripts

### Advantages of Docker Compose

| Feature | Original Scripts | Docker Compose |
|---------|-----------------|----------------|
| Container lifecycle | Manual `docker run` commands | Declarative `docker-compose.yml` |
| Service dependencies | Manual sequencing in scripts | Built-in `depends_on` |
| Volume management | Manual volume creation | Automatic volume management |
| Environment variables | Scattered across scripts | Centralized `.env-mongo` |
| Logs | `docker logs` for each container | `docker-compose logs` for all |
| Restart | Manually stop/start each | `docker-compose restart` |
| Development | Edit and re-run scripts | `docker-compose up -d` |

### When to Use Original Scripts

Use `source/scripts/build_setup.sh` when:
- You need the fully automated end-to-end setup
- You're setting up for the first time
- You want the reference implementation

Use Docker Compose when:
- You're doing iterative development
- You need to restart specific services frequently
- You want better control over individual components
- You're familiar with container orchestration tools

## Advanced Usage

### Running with Custom Configuration

Create a `docker-compose.override.yml`:

```yaml
version: '3.8'

services:
  osken:
    environment:
      - LOG_LEVEL=DEBUG
  
  mongodb-n1:
    command: >
      mongod
      --shardsvr
      --replSet rs_net1
      --bind_ip_all
      --port 27018
      --slowms 100
```

### Selective Service Management

```bash
# Start only infrastructure services
docker-compose up -d ovs nat-router

# Start only MongoDB services
docker-compose up -d mongodb-config-server mongodb-n1 mongodb-n2 mongodb-router

# Start only one network
docker-compose up -d container1 container2 container5 mongodb-n1
```

### Development Workflow

```bash
# 1. Make changes to controller code
vim source/sdn_controller/calculate_stats_n1.py

# 2. Restart controller to pick up changes (volume mounted)
docker-compose restart osken

# 3. View logs
docker-compose logs -f osken

# 4. If image changes needed
docker-compose build osken
docker-compose up -d --force-recreate osken
```

## Integration with Existing Tools

The Docker Compose setup is designed to work alongside existing project tools:

```bash
# Use original test scripts
cd source/scripts
./test_connectivity.sh
./test_db.sh

# Use original cleanup when needed
./cleanup.sh --network  # Clean network without stopping compose services

# Mix and match
docker-compose up -d  # Start with compose
# ... do work ...
./cleanup.sh --reset  # Full cleanup with original script
```

## Future Enhancements

Potential improvements to the Docker Compose setup:

1. **Healthchecks**: Add proper health checks for all services
2. **Init containers**: Automated MongoDB initialization via init containers
3. **Network plugins**: Explore Docker network plugins for veth automation
4. **Profiles**: Use compose profiles for different deployment scenarios
5. **Makefile**: Add Makefile targets for common operations

## Getting Help

- **Documentation**: See `docs/` directory for detailed network and setup documentation
- **Issues**: Check existing scripts in `source/scripts/` for reference implementation
- **Logs**: Always check logs with `docker-compose logs <service>` when debugging

## Summary

The Docker Compose setup provides a modern, maintainable way to manage the lab environment while preserving all functionality from the original scripts. It strikes a balance between ease of use and the complexity required for this advanced networking scenario.

For the complete automated setup, the original `build_setup.sh` script remains the recommended approach. Docker Compose shines for development, debugging, and selective service management.
