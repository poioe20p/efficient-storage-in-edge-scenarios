#!/bin/bash

# ============================================================================
# Docker Compose Environment Validation Script
# ============================================================================
#
# This script validates that the environment is properly configured before
# running the docker-compose setup.
#
# Usage:
#   ./docker-compose-validate.sh
#
# ============================================================================

set -euo pipefail

SCRIPT_NAME=$(basename "$0")
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

pass() { echo -e "${GREEN}✓${NC} $*"; }
fail() { echo -e "${RED}✗${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
info() { echo "ℹ $*"; }

ERRORS=0
WARNINGS=0

echo "====================================================================="
echo "Docker Compose Environment Validation"
echo "====================================================================="
echo ""

# ============================================================================
# Check Docker
# ============================================================================
echo "Checking Docker installation..."

if command -v docker >/dev/null 2>&1; then
    DOCKER_VERSION=$(docker --version)
    pass "Docker installed: $DOCKER_VERSION"
else
    fail "Docker not found. Please install Docker."
    ((ERRORS++))
fi

# Check Docker daemon
if docker info >/dev/null 2>&1; then
    pass "Docker daemon is running"
else
    fail "Docker daemon is not running or not accessible"
    ((ERRORS++))
fi

# ============================================================================
# Check Docker Compose
# ============================================================================
echo ""
echo "Checking Docker Compose..."

if docker compose version >/dev/null 2>&1; then
    COMPOSE_VERSION=$(docker compose version)
    pass "Docker Compose installed: $COMPOSE_VERSION"
    COMPOSE_CMD="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_VERSION=$(docker-compose --version)
    pass "Docker Compose (standalone) installed: $COMPOSE_VERSION"
    COMPOSE_CMD="docker-compose"
else
    fail "Docker Compose not found. Please install Docker Compose."
    ((ERRORS++))
fi

# ============================================================================
# Check sudo/root access
# ============================================================================
echo ""
echo "Checking privileges..."

if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    pass "Running as root"
elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    pass "sudo access available (passwordless)"
elif command -v sudo >/dev/null 2>&1; then
    warn "sudo requires password (you'll be prompted during network setup)"
    ((WARNINGS++))
else
    fail "No sudo access. Network setup requires elevated privileges."
    ((ERRORS++))
fi

# ============================================================================
# Check required commands
# ============================================================================
echo ""
echo "Checking required commands..."

REQUIRED_CMDS=(ip iptables nsenter bash)

for cmd in "${REQUIRED_CMDS[@]}"; do
    if command -v "$cmd" >/dev/null 2>&1; then
        pass "$cmd available"
    else
        fail "$cmd not found (required for network setup)"
        ((ERRORS++))
    fi
done

# ============================================================================
# Check environment file
# ============================================================================
echo ""
echo "Checking environment configuration..."

if [[ -f "${SCRIPT_DIR}/.env-mongo" ]]; then
    pass ".env-mongo file exists"
    
    # Check for required variables
    REQUIRED_VARS=(
        "MONGO_INITDB_ROOT_USERNAME"
        "MONGO_INITDB_ROOT_PASSWORD"
        "MONGO_ROUTER_HOST"
        "MONGO_ROUTER_PORT"
    )
    
    for var in "${REQUIRED_VARS[@]}"; do
        if grep -q "^${var}=" "${SCRIPT_DIR}/.env-mongo" 2>/dev/null; then
            pass "  $var defined"
        else
            warn "  $var not found in .env-mongo"
            ((WARNINGS++))
        fi
    done
else
    warn ".env-mongo file not found"
    info "  Copy from template: cp .env.example .env-mongo"
    ((WARNINGS++))
fi

if [[ -f "${SCRIPT_DIR}/.env.example" ]]; then
    pass ".env.example template available"
else
    warn ".env.example template not found"
    ((WARNINGS++))
fi

# ============================================================================
# Check project files
# ============================================================================
echo ""
echo "Checking project files..."

PROJECT_FILES=(
    "docker-compose.yml"
    "docker-compose-network-setup.sh"
    "docker-compose-init-mongo.sh"
    "docker-compose-quickstart.sh"
    "Makefile"
    "DOCKER_COMPOSE.md"
)

for file in "${PROJECT_FILES[@]}"; do
    if [[ -f "${SCRIPT_DIR}/${file}" ]]; then
        pass "$file present"
    else
        fail "$file missing"
        ((ERRORS++))
    fi
done

# Check if scripts are executable
SCRIPTS=(
    "docker-compose-network-setup.sh"
    "docker-compose-init-mongo.sh"
    "docker-compose-quickstart.sh"
)

for script in "${SCRIPTS[@]}"; do
    if [[ -x "${SCRIPT_DIR}/${script}" ]]; then
        pass "  $script is executable"
    else
        warn "  $script not executable (run: chmod +x $script)"
        ((WARNINGS++))
    fi
done

# ============================================================================
# Check Dockerfiles
# ============================================================================
echo ""
echo "Checking Dockerfiles..."

DOCKERFILES=(
    "source/docker/OVS/Dockerfile"
    "source/docker/ubuntu-nat-router/Dockerfile"
    "source/docker/ubuntu-host/Dockerfile"
    "source/docker/ubuntu-mongodb/Dockerfile"
    "source/docker/ubuntu-mongodb-configsvr/Dockerfile"
    "source/docker/ubuntu-mongodb-router/Dockerfile"
    "source/docker/os-ken/Dockerfile"
)

for dockerfile in "${DOCKERFILES[@]}"; do
    if [[ -f "${SCRIPT_DIR}/${dockerfile}" ]]; then
        pass "$(basename $(dirname $dockerfile)) Dockerfile present"
    else
        fail "$dockerfile missing"
        ((ERRORS++))
    fi
done

# ============================================================================
# Check network interface
# ============================================================================
echo ""
echo "Checking network interface..."

if ip link show enp0s3 >/dev/null 2>&1; then
    pass "Network interface enp0s3 exists"
    
    # Check if it has expected IP
    if ip addr show dev enp0s3 | grep -q "192.168.100.4/24"; then
        pass "  enp0s3 has IP 192.168.100.4/24"
    else
        warn "  enp0s3 doesn't have expected IP 192.168.100.4/24"
        info "  Setup script will configure it"
        ((WARNINGS++))
    fi
else
    warn "Network interface enp0s3 not found"
    info "  This may be expected if your host uses a different interface name"
    info "  Verify DEFAULT_UPLINK_IF in your environment"
    ((WARNINGS++))
fi

# ============================================================================
# Check kernel modules
# ============================================================================
echo ""
echo "Checking kernel modules..."

if [[ -d /lib/modules ]]; then
    pass "/lib/modules directory exists (required for OVS)"
else
    fail "/lib/modules directory not found (OVS container won't work)"
    ((ERRORS++))
fi

# ============================================================================
# Check existing containers
# ============================================================================
echo ""
echo "Checking for existing containers..."

if docker ps -a --format '{{.Names}}' | grep -qE '^(ovs|nat-router|mongodb|container[1-5]|osken)'; then
    warn "Some project containers already exist"
    info "  Run 'make clean' or 'docker-compose down' to remove them"
    ((WARNINGS++))
else
    pass "No conflicting containers found"
fi

# ============================================================================
# Validate docker-compose.yml
# ============================================================================
echo ""
echo "Validating docker-compose.yml..."

if [[ -n "${COMPOSE_CMD:-}" ]]; then
    if ${COMPOSE_CMD} config --quiet 2>&1 | grep -v "version.*obsolete" | grep -v "env file.*not found" >/dev/null; then
        warn "docker-compose.yml has validation issues"
        ${COMPOSE_CMD} config --quiet 2>&1 | grep -v "version.*obsolete" | grep -v "env file.*not found" || true
        ((WARNINGS++))
    else
        pass "docker-compose.yml is valid"
    fi
fi

# ============================================================================
# Summary
# ============================================================================
echo ""
echo "====================================================================="
echo "Validation Summary"
echo "====================================================================="

if [[ $ERRORS -eq 0 && $WARNINGS -eq 0 ]]; then
    echo -e "${GREEN}✓ Environment is ready for docker-compose deployment!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. If not already done: cp .env.example .env-mongo"
    echo "  2. Edit .env-mongo with your credentials"
    echo "  3. Run: ./docker-compose-quickstart.sh --build"
    echo "     or:  make quickstart"
    exit 0
elif [[ $ERRORS -eq 0 ]]; then
    echo -e "${YELLOW}⚠ Environment is mostly ready with $WARNINGS warning(s)${NC}"
    echo ""
    echo "You can proceed, but review the warnings above."
    echo ""
    echo "Next steps:"
    echo "  1. Address warnings if possible"
    echo "  2. Run: ./docker-compose-quickstart.sh --build"
    echo "     or:  make quickstart"
    exit 0
else
    echo -e "${RED}✗ Environment is not ready: $ERRORS error(s), $WARNINGS warning(s)${NC}"
    echo ""
    echo "Please fix the errors above before proceeding."
    exit 1
fi
