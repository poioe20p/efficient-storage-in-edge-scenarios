#!/usr/bin/env python3
"""MongoDB Shard Replica Set initialization module."""

import subprocess
import time
from typing import Dict, Any


class ShardReplicaSetManager:
    """Manages MongoDB shard replica set initialization and verification."""

    def __init__(
        self,
        container_name: str,
        host: str,
        port: int = 27018,
        replica_set_name: str = ""
    ):
        self.container_name = container_name
        self.host = host
        self.port = port
        self.replica_set_name = replica_set_name

    def _execute_mongo_command(self, command: str) -> tuple[int, str]:
        """Execute a MongoDB command via docker exec mongosh."""
        docker_cmd = [
            "docker", "exec", "-i", self.container_name,
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

    def check_replica_set_status(self) -> str:
        """Check if replica set is already initialized."""
        command = """
var status;
try {
    status = rs.status();
    if (status.members && status.members.length > 0) {
        print('ALREADY_INITIALIZED');
    } else {
        print('NOT_INITIALIZED');
    }
} catch (e) {
    if (e.codeName === 'NotYetInitialized') {
        print('NOT_INITIALIZED');
    } else {
        print('STATUS_ERROR:' + e);
    }
}
"""
        returncode, output = self._execute_mongo_command(command)
        clean_output = output.strip().replace('\r', '').replace('\n', '')
        
        if returncode == 0 and "ALREADY_INITIALIZED" in clean_output:
            return "ALREADY_INITIALIZED"
        return "NOT_INITIALIZED"

    def initialize_replica_set(self) -> bool:
        """Initialize the shard replica set."""
        print(f"Initializing MongoDB replica set '{self.replica_set_name}' on {self.container_name}...")
        
        # Check if already initialized
        status = self.check_replica_set_status()
        if status == "ALREADY_INITIALIZED":
            print(f"Replica set '{self.replica_set_name}' already initialized. Skipping rs.initiate.")
            return True

        # Initialize replica set
        print("Replica set not initialized yet. Running rs.initiate...")
        command = f"""
JSON.stringify(
    rs.initiate({{
        _id: '{self.replica_set_name}',
        members: [
            {{ _id: 0, host: '{self.host}:{self.port}' }}
        ]
    }})
)
"""
        returncode, output = self._execute_mongo_command(command)
        
        if returncode != 0:
            print(f"Failed to initialize replica set '{self.replica_set_name}' (exit {returncode}). Output:")
            print(output)
            return False

        # Check for ok: 1
        if '"ok"' not in output or '"ok":1' not in output.replace(' ', ''):
            print(f"Replica set '{self.replica_set_name}' initialization did not return ok: 1. Output:")
            print(output)
            return False

        print(f"Initialization returned ok: {output.strip()}")
        time.sleep(2)
        return True

    def verify_primary_status(self, max_retries: int = 3, retry_delay: int = 2) -> bool:
        """Verify that the replica set has a PRIMARY member."""
        print(f"Verifying replica set '{self.replica_set_name}' status...")
        
        for attempt in range(1, max_retries + 1):
            print(f"Replica set '{self.replica_set_name}' status check attempt {attempt}/{max_retries}...")
            
            command = """
var status;
try {
    status = rs.status();
    if (status.members && status.members.some(member => member.stateStr === 'PRIMARY')) {
        print('PRIMARY');
    } else if (status.members && status.members.length > 0) {
        print(status.members[0].stateStr);
    } else {
        print('UNKNOWN');
    }
} catch (e) {
    print('ERROR:' + e);
}
"""
            returncode, output = self._execute_mongo_command(command)
            
            if returncode != 0:
                print(f"Failed to run rs.status() for '{self.replica_set_name}' (exit {returncode}). Output:")
                print(output)
            else:
                clean_output = output.strip().replace('\r', '').replace('\n', '')
                
                if clean_output.startswith("ERROR:"):
                    print(f"Replica set '{self.replica_set_name}' not ready yet ({clean_output}).")
                elif clean_output == "PRIMARY" or '"stateStr":"PRIMARY"' in output.replace(' ', ''):
                    print(f"Replica set '{self.replica_set_name}' reports PRIMARY state.")
                    return True
                else:
                    print(f"Replica set '{self.replica_set_name}' status is not PRIMARY yet. Output:")
                    print(output)

            if attempt < max_retries:
                print(f"Retrying in {retry_delay}s...")
                time.sleep(retry_delay)

        print(f"Replica set '{self.replica_set_name}' failed to become PRIMARY after {max_retries} attempts.")
        return False

    def setup(self) -> bool:
        """Complete setup: initialize and verify shard replica set."""
        if not self.initialize_replica_set():
            return False
        
        if not self.verify_primary_status():
            return False
        
        time.sleep(2)
        return True
