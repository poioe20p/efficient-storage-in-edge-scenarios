# Quick Start Guide: MongoDB Python Setup

## Overview

The MongoDB cluster setup has been migrated to Python for better maintainability. This guide explains how to use the new Python-based setup.

## How It Works

### Automatic (via build_setup.sh)

The Python setup is automatically called when you run:
```bash
cd source/scripts
./build_setup.sh
```

The script will:
1. Start all containers (config, shards, router)
2. Call the Python module: `python3 -m sdn_controller.usecases.build_mongodb_cluster.cli`
3. Continue with SDN controller setup

### Manual Execution

To run the MongoDB setup separately:
```bash
cd source
python3 -m sdn_controller.usecases.build_mongodb_cluster.cli
```

**Prerequisites:**
- Config server container (`mongodb-config-server`) must be running
- Network containers (`mongodb-n1`, `mongodb-n2`) must be running
- Router container (`mongodb-router`) must be running

## Module Structure

```
source/sdn_controller/usecases/build_mongodb_cluster/
├── __init__.py              # Package exports
├── cli.py                   # Command-line interface
├── setup_cluster.py         # Main orchestration
├── config_server.py         # Config server initialization
├── shard_replica_set.py     # Shard replica set setup
├── router.py                # Router configuration
└── README.md                # Detailed documentation
```

## Configuration

Default configuration (in `setup_cluster.py`):
```python
MONGO_HOST_IP = "192.168.100.4"      # Config/router host
MONGO_RS_1_HOST_IP = "10.0.0.4"      # Shard 1 host
MONGO_RS_2_HOST_IP = "10.0.1.4"      # Shard 2 host
ZONE_SIZE = 1000000000                # Zone size for sharding
```

To modify these values, edit `setup_cluster.py`.

## Programmatic Usage

You can import and use the modules in your own Python code:

```python
# Import the main function
from sdn_controller.usecases.build_mongodb_cluster import setup_mongodb_cluster

# Run the setup
success = setup_mongodb_cluster()
if success:
    print("MongoDB cluster initialized successfully")
else:
    print("Failed to initialize MongoDB cluster")
```

Or use individual managers:

```python
from sdn_controller.usecases.build_mongodb_cluster import (
    ConfigServerManager,
    ShardReplicaSetManager,
    RouterManager
)

# Initialize config server
config_mgr = ConfigServerManager(
    container_name="mongodb-config-server",
    host="192.168.100.4",
    port=27019,
    replica_set_name="configReplSet"
)
if config_mgr.setup():
    print("Config server ready")

# Initialize shard replica set
shard_mgr = ShardReplicaSetManager(
    container_name="mongodb-n1",
    host="10.0.0.4",
    port=27018,
    replica_set_name="rs_net1"
)
if shard_mgr.setup():
    print("Shard replica set ready")
```

## Running Tests

Unit tests are located in `source/tests/test_mongodb_setup.py`:

```bash
cd source
python3 tests/test_mongodb_setup.py
```

Expected output:
```
test_initialization ... ok
test_initialization_custom_values ... ok
...
----------------------------------------------------------------------
Ran 13 tests in 0.005s

OK
```

## Troubleshooting

### "No such container" errors

Make sure all containers are running:
```bash
docker ps | grep -E 'mongodb-config-server|mongodb-n1|mongodb-n2|mongodb-router'
```

### "Failed to initialize replica set"

Check container logs:
```bash
docker logs mongodb-config-server
docker logs mongodb-n1
docker logs mongodb-n2
```

### Import errors

Make sure you're running from the `source` directory or PYTHONPATH is set correctly:
```bash
export PYTHONPATH=/path/to/source:$PYTHONPATH
```

## What Changed?

### Before (bash)
MongoDB setup was embedded in `build_setup.sh` with ~440 lines of bash code:
- Hard to test
- Difficult to maintain
- Limited error handling

### After (Python)
MongoDB setup is in dedicated Python modules:
- Clean separation of concerns
- Unit tests available
- Better error handling
- Reusable components
- Comprehensive documentation

## Compatibility

✅ The new Python setup is **100% compatible** with the old bash implementation:
- Same containers
- Same IPs and ports
- Same replica set names
- Same database/collection configuration
- Same sharding setup

## For Developers

### Adding New Features

1. Modify the appropriate module (config_server.py, shard_replica_set.py, or router.py)
2. Update `setup_cluster.py` if orchestration changes
3. Add unit tests in `test_mongodb_setup.py`
4. Update documentation

### Code Style

- Use type hints where appropriate
- Add docstrings to classes and methods
- Follow PEP 8 style guidelines
- Include error handling and logging

### Testing Changes

Before committing:
```bash
# Check Python syntax
python3 -m py_compile source/sdn_controller/usecases/build_mongodb_cluster/*.py

# Run unit tests
cd source && python3 tests/test_mongodb_setup.py

# Check bash syntax
bash -n source/scripts/build_setup.sh
```

## Further Reading

- `source/sdn_controller/usecases/build_mongodb_cluster/README.md` - Detailed module documentation
- `MONGODB_MIGRATION.md` - Migration summary and rationale
- `docs/setups/sdn_controller_and_mongodb.md` - Network architecture
- MongoDB documentation: https://docs.mongodb.com/manual/sharding/

## Support

For issues or questions:
1. Check the logs: `docker logs <container-name>`
2. Review the documentation in the README files
3. Run the unit tests to verify the setup
4. Check MongoDB status: `docker exec mongodb-router mongosh --eval "sh.status()"`
