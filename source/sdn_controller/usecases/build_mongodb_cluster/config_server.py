#!/usr/bin/env python3
"""MongoDB Config Server initialization module."""

import subprocess
import time
import json
from typing import Dict, Any, Optional


class ConfigServerManager:
    """Manages MongoDB config server initialization and verification."""

    def __init__(
        self,
        container_name: str = "mongodb-config-server",
        host: str = "192.168.100.4",
        port: int = 27019,
        replica_set_name: str = "configReplSet"
    ):
        self.container_name = container_name
        self.host = host
        self.port = port
        self.replica_set_name = replica_set_name

    def _execute_mongo_command(self, command: str) -> tuple[int, str]:
        """Execute a MongoDB command via docker exec mongosh."""
        docker_cmd = [
            "docker", "exec", self.container_name,
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
        """Initialize the config server replica set."""
        print(f"Initializing MongoDB config server replica set '{self.replica_set_name}'...")
        
        # Check if already initialized
        status = self.check_replica_set_status()
        if status == "ALREADY_INITIALIZED":
            print("Config server replica set already initialized. Skipping rs.initiate.")
            return True

        # Initialize replica set
        print("Replica set not initialized yet. Running rs.initiate...")
        command = f"""
JSON.stringify(
    rs.initiate({{
        _id: '{self.replica_set_name}',
        configsvr: true,
        members: [
            {{ _id: 0, host: '{self.host}:{self.port}' }}
        ]
    }})
)
"""
        returncode, output = self._execute_mongo_command(command)
        
        if returncode != 0:
            print(f"Failed to initialize MongoDB config server replica set (exit {returncode}). Output:")
            print(output)
            return False

        # Check for ok: 1
        if '"ok"' not in output or '"ok":1' not in output.replace(' ', ''):
            print("Config server replica set initialization did not return ok: 1. Output:")
            print(output)
            return False

        print("Config server replica set initialization returned ok: 1.")
        time.sleep(2)
        return True

    def verify_primary_status(self, max_retries: int = 3, retry_delay: int = 2) -> bool:
        """Verify that the replica set has a PRIMARY member."""
        print("Verifying MongoDB config server replica set status...")
        
        for attempt in range(1, max_retries + 1):
            print(f"Replica set status check attempt {attempt}/{max_retries}...")
            
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
                print(f"Failed to run rs.status() (exit {returncode}). Output:")
                print(output)
            else:
                clean_state = output.strip().replace('\r', '').replace('\n', '').replace('"', '')
                if clean_state == "PRIMARY":
                    print("Config server replica set member is PRIMARY.")
                    return True
                elif clean_state.startswith("ERROR:"):
                    print(f"Replica set not ready yet ({clean_state}).")
                else:
                    print(f"Replica set state is '{clean_state}', not PRIMARY yet.")

            if attempt < max_retries:
                print(f"Retrying in {retry_delay}s...")
                time.sleep(retry_delay)

        print(f"Config server replica set failed to reach PRIMARY state after {max_retries} attempts.")
        return False

    def setup(self) -> bool:
        """Complete setup: initialize and verify config server."""
        if not self.initialize_replica_set():
            return False
        
        if not self.verify_primary_status():
            return False
        
        time.sleep(2)
        return True
