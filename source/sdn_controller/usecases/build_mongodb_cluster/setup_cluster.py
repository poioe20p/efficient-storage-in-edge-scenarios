#!/usr/bin/env python3
"""Main orchestration script for MongoDB cluster setup."""

import sys
from .config_server import ConfigServerManager
from .shard_replica_set import ShardReplicaSetManager
from .router import RouterManager


def setup_mongodb_cluster():
    """
    Main function to orchestrate MongoDB cluster setup.
    This replaces the MongoDB-specific parts of build_setup.sh.
    """
    
    # Configuration
    MONGO_HOST_IP = "192.168.100.4"
    MONGO_RS_1_HOST_IP = "10.0.0.4"
    MONGO_RS_2_HOST_IP = "10.0.1.4"
    ZONE_SIZE = 1000000000
    
    print("=" * 80)
    print("Starting MongoDB Cluster Setup")
    print("=" * 80)
    
    # Step 1: Initialize Config Server
    print("\n" + "=" * 80)
    print("Step 1: Initialize MongoDB Config Server")
    print("=" * 80)
    config_server = ConfigServerManager(
        container_name="mongodb-config-server",
        host=MONGO_HOST_IP,
        port=27019,
        replica_set_name="configReplSet"
    )
    
    if not config_server.setup():
        print("Failed to setup config server. Aborting.")
        return False
    
    # Step 2: Initialize Shard Replica Sets
    print("\n" + "=" * 80)
    print("Step 2: Initialize Shard Replica Sets")
    print("=" * 80)
    
    # Network 1 replica set
    print("\nInitializing rs_net1...")
    rs_net1 = ShardReplicaSetManager(
        container_name="mongodb-n1",
        host=MONGO_RS_1_HOST_IP,
        port=27018,
        replica_set_name="rs_net1"
    )
    
    if not rs_net1.setup():
        print("Failed to setup rs_net1. Aborting.")
        return False
    
    # Network 2 replica set
    print("\nInitializing rs_net2...")
    rs_net2 = ShardReplicaSetManager(
        container_name="mongodb-n2",
        host=MONGO_RS_2_HOST_IP,
        port=27018,
        replica_set_name="rs_net2"
    )
    
    if not rs_net2.setup():
        print("Failed to setup rs_net2. Aborting.")
        return False
    
    # Step 3: Configure Router (mongos)
    print("\n" + "=" * 80)
    print("Step 3: Configure MongoDB Router (mongos)")
    print("=" * 80)
    
    router = RouterManager(
        container_name="mongodb-router",
        host=MONGO_HOST_IP,
        port=27020
    )
    
    # Define shards
    shards = [
        {
            "name": "rs_net1",
            "connection_string": f"rs_net1/{MONGO_RS_1_HOST_IP}:27018"
        },
        {
            "name": "rs_net2",
            "connection_string": f"rs_net2/{MONGO_RS_2_HOST_IP}:27018"
        }
    ]
    
    # Define collections to shard
    collections = [
        {
            "name": "app_db.events",
            "shard_key": {"dpid": 1}
        }
    ]
    
    # Define zones with their ranges
    zones = [
        {
            "shard_name": "rs_net1",
            "zone_name": "shard_zone_rs_net1",
            "collections": [
                {
                    "name": "app_db.events",
                    "min_key": {"dpid": 0},
                    "max_key": {"dpid": ZONE_SIZE}
                }
            ]
        },
        {
            "shard_name": "rs_net2",
            "zone_name": "shard_zone_rs_net2",
            "collections": [
                {
                    "name": "app_db.events",
                    "min_key": {"dpid": ZONE_SIZE},
                    "max_key": {"dpid": 2 * ZONE_SIZE}
                }
            ]
        }
    ]
    
    if not router.configure_sharding(
        shards=shards,
        database="app_db",
        collections=collections,
        zones=zones
    ):
        print("Failed to configure router. Aborting.")
        return False
    
    print("\n" + "=" * 80)
    print("MongoDB Cluster Setup Completed Successfully")
    print("=" * 80)
    return True


if __name__ == "__main__":
    success = setup_mongodb_cluster()
    sys.exit(0 if success else 1)
