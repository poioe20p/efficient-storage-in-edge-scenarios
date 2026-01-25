#!/usr/bin/env python3
"""MongoDB Router (mongos) configuration module."""

import subprocess
import time
from typing import Dict, List


class RouterManager:
    """Manages MongoDB router (mongos) configuration including sharding."""

    def __init__(
        self,
        container_name: str = "mongodb-router",
        host: str = "192.168.100.4",
        port: int = 27020
    ):
        self.container_name = container_name
        self.host = host
        self.port = port

    def _execute_mongo_command(self, command: str) -> tuple[int, str]:
        """Execute a MongoDB command via docker exec mongosh."""
        docker_cmd = [
            "docker", "exec", "-it", self.container_name,
            "mongosh", "--quiet",
            "--host", self.host,
            "--port", str(self.port),
            "--eval", command
        ]
        result = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True
        )
        return result.returncode, result.stdout + result.stderr

    def add_shard(self, shard_name: str, connection_string: str, max_retries: int = 5, retry_delay: int = 2) -> bool:
        """Add a shard to the MongoDB router."""
        print(f"Adding shard {shard_name} (target {connection_string})...")
        
        for attempt in range(1, max_retries + 1):
            print(f"Attempt {attempt}/{max_retries}...")
            
            command = f"JSON.stringify(sh.addShard('{connection_string}'))"
            returncode, output = self._execute_mongo_command(command)
            
            if returncode == 0 and '"ok":1' in output.replace(' ', ''):
                print(f"Shard {shard_name} added successfully.")
                return True
            
            print(f"Shard {shard_name} add attempt {attempt} failed (exit {returncode}). Output:")
            print(output)
            
            if attempt < max_retries:
                print(f"Retrying in {retry_delay}s...")
                time.sleep(retry_delay)

        print(f"Failed to add shard {shard_name} after {max_retries} attempts.")
        return False

    def enable_sharding(self, database: str) -> bool:
        """Enable sharding for a database."""
        print(f"Enabling sharding for database '{database}'...")
        
        command = f"JSON.stringify(sh.enableSharding('{database}'))"
        returncode, output = self._execute_mongo_command(command)
        
        if returncode != 0:
            print(f"Failed to enable sharding for database '{database}' (exit {returncode}). Output:")
            print(output)
            return False

        if '"ok"' not in output or '"ok":1' not in output.replace(' ', ''):
            print(f"Enabling sharding for database '{database}' did not return ok: 1. Output:")
            print(output)
            return False

        print(f"Sharding enabled for database '{database}'.")
        return True

    def shard_collection(self, collection: str, shard_key: Dict[str, int]) -> bool:
        """Shard a collection with the specified shard key."""
        print(f"Sharding collection '{collection}' with key {shard_key}...")
        
        # Format shard key for MongoDB command
        shard_key_str = ", ".join([f"{k}: {v}" for k, v in shard_key.items()])
        
        command = f"JSON.stringify(sh.shardCollection('{collection}', {{ {shard_key_str} }}))"
        returncode, output = self._execute_mongo_command(command)
        
        if returncode != 0:
            print(f"Failed to shard collection '{collection}' (exit {returncode}). Output:")
            print(output)
            return False

        if '"ok"' not in output or '"ok":1' not in output.replace(' ', ''):
            print(f"Sharding collection '{collection}' did not return ok: 1. Output:")
            print(output)
            return False

        print(f"Collection '{collection}' sharded successfully.")
        return True

    def add_shard_to_zone(self, shard_name: str, zone_name: str) -> bool:
        """Assign a zone to a shard."""
        print(f"Assigning zone {zone_name} to shard {shard_name}...")
        
        command = f"JSON.stringify(sh.addShardToZone('{shard_name}', '{zone_name}'))"
        returncode, output = self._execute_mongo_command(command)
        
        if returncode != 0:
            print(f"Failed to assign zone {zone_name} to shard {shard_name} (exit {returncode}). Output:")
            print(output)
            return False

        if '"ok"' not in output or '"ok":1' not in output.replace(' ', ''):
            print(f"Adding zone {zone_name} to shard {shard_name} did not return ok: 1. Output:")
            print(output)
            return False

        print(f"Zone {zone_name} assigned to shard {shard_name}.")
        return True

    def update_zone_key_range(
        self, 
        collection: str, 
        min_key: Dict[str, int], 
        max_key: Dict[str, int], 
        zone_name: str
    ) -> bool:
        """Tag a collection range with a zone."""
        print(f"Tagging collection {collection} range [{min_key}, {max_key}) with zone {zone_name}.")
        
        # Format key ranges for MongoDB command
        min_key_str = ", ".join([f"{k}: NumberLong({v})" for k, v in min_key.items()])
        max_key_str = ", ".join([f"{k}: NumberLong({v})" for k, v in max_key.items()])
        
        command = f"""
JSON.stringify(
    sh.updateZoneKeyRange(
        '{collection}',
        {{ {min_key_str} }},
        {{ {max_key_str} }},
        '{zone_name}'
    )
)
"""
        returncode, output = self._execute_mongo_command(command)
        
        if returncode != 0:
            print(f"Failed to tag {collection} zone range for {zone_name} (exit {returncode}). Output:")
            print(output)
            return False

        if '"ok"' not in output or '"ok":1' not in output.replace(' ', ''):
            print(f"Adding zone range for {collection} ({zone_name}) did not return ok: 1. Output:")
            print(output)
            return False

        print(f"Zone range for {collection} ({zone_name}) configured successfully.")
        return True

    def configure_sharding(
        self,
        shards: List[Dict[str, str]],
        database: str,
        collections: List[Dict[str, any]],
        zones: List[Dict[str, any]]
    ) -> bool:
        """Complete sharding configuration: add shards, enable sharding, configure zones."""
        
        # Add shards
        for shard in shards:
            time.sleep(2)
            if not self.add_shard(shard['name'], shard['connection_string']):
                return False

        # Enable sharding for database
        if not self.enable_sharding(database):
            return False

        # Shard collections
        for collection in collections:
            if not self.shard_collection(collection['name'], collection['shard_key']):
                return False

        # Configure zones
        for zone in zones:
            if not self.add_shard_to_zone(zone['shard_name'], zone['zone_name']):
                return False

            for collection in zone['collections']:
                if not self.update_zone_key_range(
                    collection['name'],
                    collection['min_key'],
                    collection['max_key'],
                    zone['zone_name']
                ):
                    return False

        print("Shard zones and key ranges configured successfully.")
        return True
