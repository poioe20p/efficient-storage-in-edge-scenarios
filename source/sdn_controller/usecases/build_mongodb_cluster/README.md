# MongoDB Cluster Setup (Python Implementation)

This directory contains Python modules for setting up and configuring a MongoDB sharded cluster. This implementation replaces the MongoDB setup portions that were previously embedded in the bash script `build_setup.sh`.

## Architecture

The MongoDB cluster consists of:
- **Config Server**: A replica set for storing cluster metadata
- **Shard Replica Sets**: Two replica sets (rs_net1 and rs_net2) for data distribution
- **MongoDB Router (mongos)**: Routes queries to the appropriate shards

## Modules

### `config_server.py`
Handles MongoDB config server replica set initialization and verification.

**Main Class**: `ConfigServerManager`
- Initializes the config server replica set
- Verifies PRIMARY status
- Handles idempotent operations (skips if already initialized)

### `shard_replica_set.py`
Handles MongoDB shard replica set initialization and verification.

**Main Class**: `ShardReplicaSetManager`
- Initializes shard replica sets (rs_net1, rs_net2)
- Verifies PRIMARY status for each shard
- Supports multiple replica sets

### `router.py`
Handles MongoDB router (mongos) configuration including sharding setup.

**Main Class**: `RouterManager`
- Adds shards to the router
- Enables sharding on databases
- Configures collections for sharding
- Sets up shard zones and key ranges

### `setup_cluster.py`
Main orchestration script that coordinates the entire setup process.

**Main Function**: `setup_mongodb_cluster()`
- Orchestrates config server setup
- Orchestrates shard replica set initialization
- Configures router with sharding and zones

### `cli.py`
Command-line interface wrapper for easy execution.

## Usage

### From Command Line
```bash
# From the source directory
cd /path/to/source
python3 -m sdn_controller.usecases.build_mongodb_cluster.cli
```

### From build_setup.sh
The script is automatically called during the MongoDB setup phase:
```bash
python3 -m sdn_controller.usecases.build_mongodb_cluster.cli
```

### Programmatic Usage
```python
from sdn_controller.usecases.build_mongodb_cluster import setup_mongodb_cluster

success = setup_mongodb_cluster()
if not success:
    print("Setup failed")
```

## Configuration

The setup uses the following default configuration (defined in `setup_cluster.py`):

```python
MONGO_HOST_IP = "192.168.100.4"      # Config server and router host
MONGO_RS_1_HOST_IP = "10.0.0.4"      # Shard 1 host
MONGO_RS_2_HOST_IP = "10.0.1.4"      # Shard 2 host
ZONE_SIZE = 1000000000                # Zone size for sharding
```

### Sharding Configuration

- **Database**: `app_db`
- **Collection**: `app_db.events`
- **Shard Key**: `{ dpid: 1 }`
- **Zones**:
  - `shard_zone_rs_net1`: dpid range [0, 1000000000)
  - `shard_zone_rs_net2`: dpid range [1000000000, 2000000000)

## Prerequisites

Before running the setup:
1. Config server container (`mongodb-config-server`) must be running
2. Network 1 with mongodb-n1 container must be set up
3. Network 2 with mongodb-n2 container must be set up
4. Router container (`mongodb-router`) must be running

## Error Handling

All modules include comprehensive error handling:
- Check if replica sets are already initialized (idempotent)
- Verify PRIMARY status before proceeding
- Retry logic for cluster operations
- Clear error messages with output logging

## Integration with build_setup.sh

The bash script `build_setup.sh` has been modified to:
1. Start all necessary containers (config, shards, router)
2. Call the Python module for MongoDB initialization
3. Continue with SDN controller setup

This separation provides:
- Better error handling
- Easier testing and maintenance
- Clearer code organization
- Reusable Python modules

## Development

To add new features or modify the setup:

1. Modify the appropriate module (config_server, shard_replica_set, or router)
2. Update `setup_cluster.py` if the orchestration changes
3. Test with actual MongoDB containers
4. Update this README with any configuration changes
