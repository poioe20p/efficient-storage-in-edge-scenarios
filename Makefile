.PHONY: help build up down restart logs status clean test-connectivity quickstart init-mongo setup-network

# Default target
help:
	@echo "Docker Compose Makefile for efficient-storage-in-edge-scenarios"
	@echo ""
	@echo "Available targets:"
	@echo "  make help              - Show this help message"
	@echo "  make build             - Build all Docker images"
	@echo "  make up                - Start all containers"
	@echo "  make down              - Stop all containers"
	@echo "  make restart           - Restart all containers"
	@echo "  make logs              - View logs from all containers"
	@echo "  make status            - Show status of all containers"
	@echo "  make clean             - Stop containers and clean up"
	@echo "  make quickstart        - Build, start, configure everything"
	@echo "  make setup-network     - Configure network topology only"
	@echo "  make init-mongo        - Initialize MongoDB cluster only"
	@echo "  make test-connectivity - Run connectivity tests"
	@echo ""
	@echo "Service-specific targets:"
	@echo "  make logs-ovs          - View OVS logs"
	@echo "  make logs-mongo        - View MongoDB router logs"
	@echo "  make logs-controller   - View SDN controller logs"
	@echo ""
	@echo "Advanced targets:"
	@echo "  make shell-container1  - Open shell in container1"
	@echo "  make shell-nat         - Open shell in NAT router"
	@echo "  make ovs-show          - Show OVS configuration"
	@echo "  make mongo-status      - Show MongoDB cluster status"
	@echo ""

# Build all images
build:
	docker-compose build

# Start all containers
up:
	docker-compose up -d

# Stop all containers
down:
	docker-compose down

# Restart all containers
restart:
	docker-compose restart

# View logs from all containers
logs:
	docker-compose logs -f

# Show container status
status:
	docker-compose ps

# Clean up containers and volumes
clean:
	docker-compose down -v

# Quick start - full setup
quickstart:
	@echo "Starting full deployment..."
	./docker-compose-quickstart.sh --build

# Setup network topology
setup-network:
	@echo "Configuring network topology..."
	./docker-compose-network-setup.sh

# Initialize MongoDB cluster
init-mongo:
	@echo "Initializing MongoDB cluster..."
	./docker-compose-init-mongo.sh

# Run connectivity tests
test-connectivity:
	@if [ -f source/scripts/test_connectivity.sh ]; then \
		cd source/scripts && ./test_connectivity.sh; \
	else \
		echo "Test script not found!"; \
	fi

# Service-specific log targets
logs-ovs:
	docker-compose logs -f ovs

logs-mongo:
	docker-compose logs -f mongodb-router

logs-controller:
	docker-compose logs -f osken osken_2

logs-shard1:
	docker-compose logs -f mongodb-n1

logs-shard2:
	docker-compose logs -f mongodb-n2

# Shell access targets
shell-container1:
	docker exec -it container1 bash

shell-container2:
	docker exec -it container2 bash

shell-container3:
	docker exec -it container3 bash

shell-nat:
	docker exec -it nat-router bash

shell-ovs:
	docker exec -it ovs bash

# Diagnostic targets
ovs-show:
	docker exec ovs ovs-vsctl show

ovs-flows-br0:
	docker exec ovs ovs-ofctl dump-flows ovs-br0

ovs-flows-br1:
	docker exec ovs ovs-ofctl dump-flows ovs-br1

mongo-status:
	docker exec mongodb-router mongosh --host 192.168.100.4 --port 27020 --eval "sh.status()"

mongo-config-status:
	docker exec mongodb-config-server mongosh --host 192.168.100.4 --port 27019 --eval "rs.status()"

mongo-shard1-status:
	docker exec mongodb-n1 mongosh --host 10.0.0.4 --port 27018 --eval "rs.status()"

mongo-shard2-status:
	docker exec mongodb-n2 mongosh --host 10.0.1.4 --port 27018 --eval "rs.status()"

# Network diagnostics
ping-test:
	@echo "Testing connectivity from container1 to mongodb-n1..."
	docker exec container1 ping -c 4 10.0.0.4
	@echo ""
	@echo "Testing connectivity from container3 to mongodb-n2..."
	docker exec container3 ping -c 4 10.0.1.4

# Controller configuration
set-controllers:
	@echo "Configuring OVS controllers..."
	docker exec ovs ovs-vsctl set-controller ovs-br0 tcp:127.0.0.1:6653
	docker exec ovs ovs-vsctl set-controller ovs-br1 tcp:127.0.0.1:6654
	docker exec ovs ovs-vsctl set-controller ovs-br2 tcp:127.0.0.1:6653
	@echo "Controllers configured."

# Full reset
reset:
	@echo "Performing full reset..."
	docker-compose down -v
	@if [ -f source/scripts/cleanup.sh ]; then \
		cd source/scripts && ./cleanup.sh --reset; \
	fi
	@echo "Reset complete."
