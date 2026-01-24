#!/bin/bash

# ============================================================================
# Docker Compose Quick Start Script
# ============================================================================
#
# This script provides a convenient wrapper to start the entire lab
# environment using docker-compose.
#
# Usage:
#   ./docker-compose-quickstart.sh [options]
#
# Options:
#   --build         Build images before starting (same as docker-compose build)
#   --no-network    Skip network setup (containers only)
#   --no-mongo      Skip MongoDB initialization
#   --clean         Clean up before starting
#   -h, --help      Show this help message
#
# ============================================================================

set -euo pipefail

SCRIPT_NAME=$(basename "$0")
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

log()   { printf '[INFO] %s\n' "$*"; }
warn()  { printf '[WARN] %s\n' "$*" 1>&2; }
error() { printf '[ERROR] %s\n' "$*" 1>&2; }

print_usage() {
    cat <<EOF
Usage: $SCRIPT_NAME [options]

This script starts the entire lab environment using docker-compose.

Options:
    --build         Build images before starting
    --no-network    Skip network setup (containers only)
    --no-mongo      Skip MongoDB initialization
    --clean         Clean up before starting
    -h, --help      Show this help message

Steps performed:
    1. (Optional) Clean up existing environment
    2. (Optional) Build Docker images
    3. Start containers with docker-compose
    4. Configure network topology
    5. Initialize MongoDB cluster
    6. Configure SDN controllers
    7. Display status

Prerequisites:
    - .env-mongo file must exist (copy from .env.example)
    - Docker and Docker Compose installed
    - Root/sudo privileges for network operations

EOF
}

# Parse arguments
DO_BUILD=false
DO_CLEAN=false
SKIP_NETWORK=false
SKIP_MONGO=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --build)
            DO_BUILD=true
            shift
            ;;
        --no-network)
            SKIP_NETWORK=true
            shift
            ;;
        --no-mongo)
            SKIP_MONGO=true
            shift
            ;;
        --clean)
            DO_CLEAN=true
            shift
            ;;
        -h|--help)
            print_usage
            exit 0
            ;;
        *)
            error "Unknown option: $1"
            print_usage
            exit 1
            ;;
    esac
done

# ============================================================================
# Step 0: Verify prerequisites
# ============================================================================
log "====================================================================="
log "Docker Compose Quick Start"
log "====================================================================="

# Check for .env-mongo
if [[ ! -f "${SCRIPT_DIR}/.env-mongo" ]]; then
    error "File .env-mongo not found!"
    error "Please create .env-mongo from .env.example:"
    error "  cp .env.example .env-mongo"
    error "  # Edit .env-mongo with your credentials"
    exit 1
fi

log "✓ Found .env-mongo configuration"

# Check for docker-compose
if ! command -v docker-compose >/dev/null 2>&1 && ! docker compose version >/dev/null 2>&1; then
    error "docker-compose not found!"
    error "Please install Docker Compose: https://docs.docker.com/compose/install/"
    exit 1
fi

# Determine docker-compose command
if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
else
    COMPOSE_CMD="docker-compose"
fi

log "✓ Using: ${COMPOSE_CMD}"

# ============================================================================
# Step 1: Clean up (if requested)
# ============================================================================
if [[ "$DO_CLEAN" == true ]]; then
    log "====================================================================="
    log "Cleaning up existing environment..."
    log "====================================================================="
    
    if [[ -f "${SCRIPT_DIR}/source/scripts/cleanup.sh" ]]; then
        cd "${SCRIPT_DIR}/source/scripts"
        ./cleanup.sh -v
        cd "${SCRIPT_DIR}"
    else
        ${COMPOSE_CMD} down -v 2>/dev/null || true
    fi
    
    log "✓ Cleanup complete"
fi

# ============================================================================
# Step 2: Build images (if requested)
# ============================================================================
if [[ "$DO_BUILD" == true ]]; then
    log "====================================================================="
    log "Building Docker images..."
    log "====================================================================="
    
    ${COMPOSE_CMD} build
    
    log "✓ Images built successfully"
fi

# ============================================================================
# Step 3: Ensure IPTables FORWARD policy is ACCEPT
# ============================================================================
log "====================================================================="
log "Configuring host networking..."
log "====================================================================="

log "Verifying IPTables FORWARD policy..."
FORWARD_POLICY=$(sudo iptables -L FORWARD | grep "Chain FORWARD" | awk '{print $4}')
if [[ "$FORWARD_POLICY" != "ACCEPT" ]]; then
    log "Setting FORWARD policy to ACCEPT..."
    sudo iptables --policy FORWARD ACCEPT
fi

log "✓ Host networking configured"

# ============================================================================
# Step 4: Start containers
# ============================================================================
log "====================================================================="
log "Starting containers with docker-compose..."
log "====================================================================="

${COMPOSE_CMD} up -d

# Wait for containers to be ready
sleep 5

log "✓ Containers started"

# Show container status
log ""
log "Container status:"
${COMPOSE_CMD} ps

# ============================================================================
# Step 5: Configure network topology (unless skipped)
# ============================================================================
if [[ "$SKIP_NETWORK" == false ]]; then
    log "====================================================================="
    log "Configuring network topology..."
    log "====================================================================="
    
    if [[ -f "${SCRIPT_DIR}/docker-compose-network-setup.sh" ]]; then
        "${SCRIPT_DIR}/docker-compose-network-setup.sh"
        log "✓ Network topology configured"
    else
        error "Network setup script not found!"
        exit 1
    fi
else
    warn "Skipping network setup (--no-network specified)"
fi

# ============================================================================
# Step 6: Initialize MongoDB cluster (unless skipped)
# ============================================================================
if [[ "$SKIP_MONGO" == false ]]; then
    log "====================================================================="
    log "Initializing MongoDB cluster..."
    log "====================================================================="
    
    # Wait a bit for network to stabilize
    sleep 3
    
    if [[ -f "${SCRIPT_DIR}/docker-compose-init-mongo.sh" ]]; then
        "${SCRIPT_DIR}/docker-compose-init-mongo.sh"
        log "✓ MongoDB cluster initialized"
    else
        error "MongoDB initialization script not found!"
        exit 1
    fi
else
    warn "Skipping MongoDB initialization (--no-mongo specified)"
fi

# ============================================================================
# Step 7: Configure SDN controllers
# ============================================================================
log "====================================================================="
log "Configuring SDN controllers..."
log "====================================================================="

# Wait for controllers to be ready
sleep 3

log "Pointing OVS switches to controllers..."
docker exec ovs ovs-vsctl set-controller ovs-br0 tcp:127.0.0.1:6653 || warn "Failed to set controller for ovs-br0"
docker exec ovs ovs-vsctl set-controller ovs-br1 tcp:127.0.0.1:6654 || warn "Failed to set controller for ovs-br1"
docker exec ovs ovs-vsctl set-controller ovs-br2 tcp:127.0.0.1:6653 || warn "Failed to set controller for ovs-br2"

log "✓ SDN controllers configured"

# ============================================================================
# Step 8: Display final status
# ============================================================================
log "====================================================================="
log "Deployment Summary"
log "====================================================================="
log ""
log "✓ All containers running"
log "✓ Network topology configured"
log "✓ MongoDB cluster initialized"
log "✓ SDN controllers connected"
log ""
log "View status:"
log "  Containers:  ${COMPOSE_CMD} ps"
log "  OVS:         docker exec ovs ovs-vsctl show"
log "  MongoDB:     docker exec mongodb-router mongosh --host 192.168.100.4 --port 27020 --eval 'sh.status()'"
log "  Controller:  ${COMPOSE_CMD} logs -f osken"
log ""
log "Run tests:"
log "  Connectivity: cd source/scripts && ./test_connectivity.sh"
log ""
log "Stop environment:"
log "  ${COMPOSE_CMD} down"
log ""
log "====================================================================="
log "Lab environment is ready!"
log "====================================================================="
