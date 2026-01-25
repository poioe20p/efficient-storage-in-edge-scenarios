#!/usr/bin/env python3
"""
MongoDB Cluster Manager for SDN Controller integration.

This module provides a comprehensive interface for managing MongoDB cluster lifecycle
from the SDN controller, including setup, shutdown, restart, and adding new shards.
"""

import subprocess
import time
from typing import List, Dict, Optional, Any
from .config_server import ConfigServerManager
from .shard_replica_set import ShardReplicaSetManager
from .router import RouterManager


class MongoDBClusterManager:
    """
    Manages the complete MongoDB cluster lifecycle for SDN controller integration.
    
    This class provides methods to:
    - Initialize the MongoDB cluster (config server, shards, router)
    - Add new replica sets/shards dynamically
    - Shutdown the cluster
    - Restart the cluster
    - Check cluster health status
    """
    
    def __init__(
        self,
        config_server_host: str = "192.168.100.4",
        config_server_port: int = 27019,
        router_host: str = "192.168.100.4",
        router_port: int = 27020,
        zone_size: int = 1000000000
    ):
        """
        Initialize the MongoDB Cluster Manager.
        
        Args:
            config_server_host: IP address for config server
            config_server_port: Port for config server
            router_host: IP address for mongos router
            router_port: Port for mongos router
            zone_size: Size of each shard zone for data distribution
        """
        self.config_server_host = config_server_host
        self.config_server_port = config_server_port
        self.router_host = router_host
        self.router_port = router_port
        self.zone_size = zone_size
        
        # Managers for cluster components
        self.config_server = None
        self.router = None
        self.shards = {}  # shard_name -> ShardReplicaSetManager
        
    def initialize_cluster(
        self,
        shard_configs: Optional[List[Dict[str, Any]]] = None,
        database: str = "app_db",
        collections: Optional[List[Dict[str, Any]]] = None
    ) -> bool:
        """
        Initialize the complete MongoDB cluster.
        
        Args:
            shard_configs: List of shard configurations, e.g.:
                [
                    {"name": "rs_net1", "container": "mongodb-n1", "host": "10.0.0.4", "port": 27018},
                    {"name": "rs_net2", "container": "mongodb-n2", "host": "10.0.1.4", "port": 27018}
                ]
            database: Database name to enable sharding on
            collections: Collections to shard, e.g.:
                [{"name": "app_db.events", "shard_key": {"dpid": 1}}]
        
        Returns:
            bool: True if successful, False otherwise
        """
        # Default configurations
        if shard_configs is None:
            shard_configs = [
                {
                    "name": "rs_net1",
                    "container": "mongodb-n1",
                    "host": "10.0.0.4",
                    "port": 27018
                },
                {
                    "name": "rs_net2",
                    "container": "mongodb-n2",
                    "host": "10.0.1.4",
                    "port": 27018
                }
            ]
        
        if collections is None:
            collections = [{"name": "app_db.events", "shard_key": {"dpid": 1}}]
        
        # Step 1: Initialize Config Server
        print("Initializing MongoDB Config Server...")
        self.config_server = ConfigServerManager(
            container_name="mongodb-config-server",
            host=self.config_server_host,
            port=self.config_server_port,
            replica_set_name="configReplSet"
        )
        
        if not self.config_server.setup():
            print("Failed to setup config server.")
            return False
        
        # Step 2: Initialize Shard Replica Sets
        print("\nInitializing Shard Replica Sets...")
        for shard_config in shard_configs:
            shard_name = shard_config["name"]
            print(f"\nInitializing {shard_name}...")
            
            shard_manager = ShardReplicaSetManager(
                container_name=shard_config["container"],
                host=shard_config["host"],
                port=shard_config.get("port", 27018),
                replica_set_name=shard_name
            )
            
            if not shard_manager.setup():
                print(f"Failed to setup {shard_name}.")
                return False
            
            self.shards[shard_name] = shard_manager
        
        # Step 3: Configure Router
        print("\nConfiguring MongoDB Router...")
        self.router = RouterManager(
            container_name="mongodb-router",
            host=self.router_host,
            port=self.router_port
        )
        
        # Prepare shard connection strings
        shards = [
            {
                "name": config["name"],
                "connection_string": f"{config['name']}/{config['host']}:{config.get('port', 27018)}"
            }
            for config in shard_configs
        ]
        
        # Prepare zones
        zones = []
        for idx, shard_config in enumerate(shard_configs):
            shard_name = shard_config["name"]
            zone_name = f"shard_zone_{shard_name}"
            range_start = idx * self.zone_size
            range_end = range_start + self.zone_size
            
            zone = {
                "shard_name": shard_name,
                "zone_name": zone_name,
                "collections": [
                    {
                        "name": col["name"],
                        "min_key": {"dpid": range_start},
                        "max_key": {"dpid": range_end}
                    }
                    for col in collections
                ]
            }
            zones.append(zone)
        
        if not self.router.configure_sharding(
            shards=shards,
            database=database,
            collections=collections,
            zones=zones
        ):
            print("Failed to configure router.")
            return False
        
        print("\nMongoDB Cluster Initialization Completed Successfully")
        return True
    
    def add_shard(
        self,
        shard_name: str,
        container_name: str,
        host: str,
        port: int = 27018,
        collections: Optional[List[str]] = None
    ) -> bool:
        """
        Add a new shard to the existing cluster.
        
        Args:
            shard_name: Name of the new replica set (e.g., "rs_net3")
            container_name: Docker container name (e.g., "mongodb-n3")
            host: IP address of the shard
            port: Port number (default: 27018)
            collections: List of collections to configure zones for (default: ["app_db.events"])
        
        Returns:
            bool: True if successful, False otherwise
        """
        if collections is None:
            collections = ["app_db.events"]
        
        print(f"\nAdding new shard: {shard_name}")
        
        # Step 1: Initialize the new replica set
        shard_manager = ShardReplicaSetManager(
            container_name=container_name,
            host=host,
            port=port,
            replica_set_name=shard_name
        )
        
        if not shard_manager.setup():
            print(f"Failed to initialize replica set {shard_name}.")
            return False
        
        self.shards[shard_name] = shard_manager
        
        # Step 2: Add shard to router
        connection_string = f"{shard_name}/{host}:{port}"
        if not self.router.add_shard(shard_name, connection_string):
            print(f"Failed to add shard {shard_name} to router.")
            return False
        
        # Step 3: Configure zone for the new shard
        zone_name = f"shard_zone_{shard_name}"
        shard_index = len(self.shards) - 1
        range_start = shard_index * self.zone_size
        range_end = range_start + self.zone_size
        
        if not self.router.add_shard_to_zone(shard_name, zone_name):
            print(f"Failed to assign zone {zone_name} to shard {shard_name}.")
            return False
        
        # Configure zone ranges for each collection
        for collection in collections:
            if not self.router.update_zone_key_range(
                collection,
                {"dpid": range_start},
                {"dpid": range_end},
                zone_name
            ):
                print(f"Failed to configure zone range for {collection}.")
                return False
        
        print(f"Shard {shard_name} added successfully")
        return True
    
    def check_cluster_health(self) -> Dict[str, Any]:
        """
        Check the health status of the MongoDB cluster.
        
        Returns:
            dict: Health status including config server, shards, and router status
        """
        health = {
            "config_server": "unknown",
            "shards": {},
            "router": "unknown"
        }
        
        # Check config server
        if self.config_server:
            try:
                status = self.config_server.check_replica_set_status()
                health["config_server"] = status
            except Exception as e:
                health["config_server"] = f"error: {str(e)}"
        
        # Check shards
        for shard_name, shard_manager in self.shards.items():
            try:
                status = shard_manager.check_replica_set_status()
                health["shards"][shard_name] = status
            except Exception as e:
                health["shards"][shard_name] = f"error: {str(e)}"
        
        # Check router (basic connectivity test)
        try:
            if self.router:
                # Try to execute a simple command
                result = subprocess.run(
                    ["docker", "exec", self.router.container_name, "mongosh",
                     "--quiet", "--host", self.router.host, "--port", str(self.router.port),
                     "--eval", "db.adminCommand({ping: 1})"],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode == 0:
                    health["router"] = "ok"
                else:
                    health["router"] = "error"
        except Exception as e:
            health["router"] = f"error: {str(e)}"
        
        return health
    
    def shutdown_cluster(self) -> bool:
        """
        Shutdown the MongoDB cluster (stop containers).
        
        Note: This stops the Docker containers. Use with caution.
        
        Returns:
            bool: True if successful, False otherwise
        """
        print("Shutting down MongoDB cluster...")
        success = True
        
        # Stop router
        if self.router:
            try:
                subprocess.run(
                    ["docker", "stop", self.router.container_name],
                    check=True,
                    capture_output=True
                )
                print(f"Stopped router: {self.router.container_name}")
            except subprocess.CalledProcessError as e:
                print(f"Failed to stop router: {e}")
                success = False
        
        # Stop shards
        for shard_name, shard_manager in self.shards.items():
            try:
                subprocess.run(
                    ["docker", "stop", shard_manager.container_name],
                    check=True,
                    capture_output=True
                )
                print(f"Stopped shard: {shard_manager.container_name}")
            except subprocess.CalledProcessError as e:
                print(f"Failed to stop shard {shard_name}: {e}")
                success = False
        
        # Stop config server
        if self.config_server:
            try:
                subprocess.run(
                    ["docker", "stop", self.config_server.container_name],
                    check=True,
                    capture_output=True
                )
                print(f"Stopped config server: {self.config_server.container_name}")
            except subprocess.CalledProcessError as e:
                print(f"Failed to stop config server: {e}")
                success = False
        
        return success
    
    def restart_cluster(self) -> bool:
        """
        Restart the MongoDB cluster (restart containers).
        
        Returns:
            bool: True if successful, False otherwise
        """
        print("Restarting MongoDB cluster...")
        success = True
        
        # Restart config server first
        if self.config_server:
            try:
                subprocess.run(
                    ["docker", "restart", self.config_server.container_name],
                    check=True,
                    capture_output=True
                )
                print(f"Restarted config server: {self.config_server.container_name}")
                time.sleep(2)
            except subprocess.CalledProcessError as e:
                print(f"Failed to restart config server: {e}")
                success = False
        
        # Restart shards
        for shard_name, shard_manager in self.shards.items():
            try:
                subprocess.run(
                    ["docker", "restart", shard_manager.container_name],
                    check=True,
                    capture_output=True
                )
                print(f"Restarted shard: {shard_manager.container_name}")
                time.sleep(1)
            except subprocess.CalledProcessError as e:
                print(f"Failed to restart shard {shard_name}: {e}")
                success = False
        
        # Restart router
        if self.router:
            try:
                subprocess.run(
                    ["docker", "restart", self.router.container_name],
                    check=True,
                    capture_output=True
                )
                print(f"Restarted router: {self.router.container_name}")
                time.sleep(2)
            except subprocess.CalledProcessError as e:
                print(f"Failed to restart router: {e}")
                success = False
        
        return success


# Legacy function for backwards compatibility
def setup_mongodb_cluster():
    """
    Legacy function to maintain backwards compatibility.
    Use MongoDBClusterManager class for more control.
    """
    manager = MongoDBClusterManager()
    return manager.initialize_cluster()
