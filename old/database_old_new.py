from config import MongoConfig
from sdn_controller.models.mongodb_host import MongodbHost, MongodbConfigServer, MongodbRouter
from pymongo import MongoClient, errors
import time


class NoAdminUserError(Exception):
    """Custom exception raised when the admin user does not exist after creation attempt."""
    pass

CONNECTIONS_ATTEMPTS = 3
MIN_KEY_LAN_1 = 1
MAX_KEY_LAN_1 = 10000000
MIN_KEY_LAN_2 = 10000001
MAX_KEY_LAN_2 = 20000000

class ConfigureMongoDBShardedCluster:
    """MongoDB orchestration for SDN controller: sets up replica sets, sharding, and collections."""

    def __init__(self, config: MongoConfig, shard_hosts: list[str]):
        self.config = config
        self.router_host = MongodbRouter(
            username=config.app_username,
            password=config.app_password,
            admin_username=config.admin_username,
            admin_password=config.admin_password
        )
        self.config_server = MongodbConfigServer(
            username=config.app_username,
            password=config.app_password,
            admin_username=config.admin_username,
            admin_password=config.admin_password
        )
        self.shard_hosts = [
            MongodbHost(
                host=host,
                username=config.app_username,
                password=config.app_password,
                replica_set_name=f"rs_shard_{i+1}",
                admin_username=config.admin_username,
                admin_password=config.admin_password
            ) for i, host in enumerate(shard_hosts)
        ]
        self._zone_cache = {}
    
    def setup_sharded_cluster(self):
        
        # Initiate config server replica set
        try:
            self.initiate_replica_set(self.config_server.replica_set_name,
                                    [{"_id": 0, "host": f"{self.config_server.host}:{self.config_server.port}"}],
                                    is_config_server=True)
        except Exception as exc:
            print(f"Error initiating config server replica set: {exc}")
            return
            
        # Initiate shard replica set
        for shard_host in self.shard_hosts:
            try:
                self.initiate_replica_set(shard_host.replica_set_name, [{"_id": 0, "host": f"{shard_host.host}:{shard_host.port}"}])
            except Exception as exc:
                print(f"Error initiating shard replica set for {shard_host.host}: {exc}")
                return
            
        # Connect to mongos/router
        router_admin_client = None
        for _ in range(CONNECTIONS_ATTEMPTS):
            try:
                router_admin_client = self.router_host.get_client_connection(admin=True, auth=True)
                router_admin_client.admin.command('ping')
                break
            except errors.PyMongoError as exc:
                print(f"Connection attempt to mongos/router failed: {exc}")
                time.sleep(2)
            except Exception as exc:
                print(f"Unexpected error when connecting to mongos/router: {exc}")
                return
                    
        if not router_admin_client:
            print("Failed to connect to mongos/router after multiple attempts.")
            return
        
        # Add shards to the cluster
        for shard_host in self.shard_hosts:
            for _ in range(CONNECTIONS_ATTEMPTS):
                try:
                    router_admin_client.admin.command('addShard', shard_host.get_shard_connection_string())
                    print(f"Added shard {shard_host.host} to the cluster.")
                    break
                except errors.OperationFailure as exc:
                    if 'already exists' in str(exc):
                        print(f"Shard {shard_host.host} already exists in the cluster.")
                        break
                    print(f"Failed to add shard {shard_host.host}: {exc}")
                    print("Retrying...")
                    time.sleep(2)
                except Exception as exc:
                    print(f"Unexpected error when adding shard {shard_host.host}: {exc}")
                    return 
        
        # Enable sharding for the application database
        try:
            router_admin_client.admin.command('enableSharding', self.config.database)
            print(f"Enabled sharding for database '{self.config.database}'.")
        except errors.PyMongoError as exc:
            print(f"PyMongo error when enabling sharding for database '{self.config.database}': {exc}")
        except Exception as exc:
            print(f"Unexpected error when enabling sharding for database '{self.config.database}': {exc}")
            return

        # Shard specific collections
        collections_to_shard = {'events': True, 'topology': True}
        for collection in collections_to_shard:
            for _ in range(CONNECTIONS_ATTEMPTS):            
                try:
                    router_admin_client.admin.command(
                        'shardCollection',
                        f"{self.config.database}.{collection}",
                        key={'shard_key': 1}
                    )
                    print(f"Sharded collection '{collection}' on key {{'shard_key': 1}}.")
                    collections_to_shard[collection] = False
                    break
                except errors.OperationFailure as exc:
                    print(f"PyMongo error when sharding collection '{collection}': {exc}")
                except Exception as exc:
                    print(f"Unexpected error when sharding collection '{collection}': {exc}")
                    print(f"Not retrying further for this collection. {collection} will not be sharded.")
                    break
        
        # Configure zones
        for collection, needs_sharding in collections_to_shard.items():
            if needs_sharding:
                continue
            for shard in self.shard_hosts:
                min_key = MIN_KEY_LAN_1
                max_key = MAX_KEY_LAN_1
                
                if shard.replica_set_name.endswith('_2'):
                    min_key = MIN_KEY_LAN_2
                    max_key = MAX_KEY_LAN_2
                    
                try:
                    self.configure_zones(router_admin_client, collection, shard, min_key, max_key)
                except Exception as exc:
                    print(f"Error configuring zones for collection '{collection}' on shard '{shard.host}': {exc}")
                    return
                
        # Setup admin and application users
        for i in range(CONNECTIONS_ATTEMPTS):
            try:
                self.create_admin_user()
                break
            except errors.OperationFailure as exc:
                print(f"PyMongo error when creating admin user: {exc}")
                if i == (CONNECTIONS_ATTEMPTS - 1):
                    print("Max creation attempts reached. Exiting. Failed to create admin user.")
                    return
                time.sleep(2)
            except Exception as exc:
                print(f"Unexpected error when creating admin user: {exc}")
                return
        
        with MongoClient(
            self.router_host.get_client_connection(admin=True, auth=True),
            connect=False,
            serverSelectionTimeoutMS=5000
        ) as admin_client:
            for i in range(CONNECTIONS_ATTEMPTS):
                try:
                    admin_client.admin.command('ping')
                    admin_db = admin_client["admin"]
                    users_info = admin_db.command("usersInfo", self.config.admin_username).get("users", [])
                    if not users_info:
                        print(f"Admin user '{self.config.admin_username}' does not exist after creation attempt.")
                        return
                    else:
                        print(f"Admin user '{self.config.admin_username}' verified.")
                        break
                except errors.OperationFailure as exc:
                    print(f"PyMongo error when verifying admin user: {exc}")
                    if i == (CONNECTIONS_ATTEMPTS - 1):
                        print("Max verification attempts reached. Exiting. Failed to verify admin user.")
                        return
                    print("Retrying... in 2 seconds.")
                    time.sleep(2)
                except Exception as exc:
                    print(f"Error verifying admin user: {exc}")
                    return

            for _ in range(CONNECTIONS_ATTEMPTS):
                try:
                    admin_client[self.config.database].command(
                        "createUser",
                        self.config.app_username,
                        pwd=self.config.app_password,
                        roles=[{"role": "readWrite", "db": self.config.database}],
                    )
                    print(f"Created application user '{self.config.app_username}'.")
                    break
                except errors.OperationFailure as exc:
                    print(f"PyMongo error when creating application user: {exc}")
                    print("Retrying... in 2 seconds.")
                    time.sleep(2)
                except Exception as exc:
                    print(f"Error creating application user: {exc}")
                    return
                

    def initiate_replica_set(self, replica_set_name: str, members: list[dict], is_config_server: bool = False):
        """Initiates the config server replica set."""
        # Implementation for initiating a replica set
        print(f"Initiating replica set '{replica_set_name}' with members: {[member['host'] for member in members]}")
        
        for member in members:
            member_admin_uri = f"mongodb://{member['host']}/admin"
            
            # Check if the replica set is already initiated
            try:
                with MongoClient(member_admin_uri, serverSelectionTimeoutMS=3000, connect=False) as client:
                    client.admin.command('replSetGetStatus')
                    print(f"Replica set '{replica_set_name}' already initiated on {member['host']}.")
                    return
            except errors.OperationFailure as exc:
                print(f"Replica set '{replica_set_name}' not initiated yet, with message {exc}.\nProceeding with initiation for {member_admin_uri}.")
            except errors.PyMongoError as exc:
                print(f"PyMongo error when checking replica set status on {member_admin_uri}: {exc}")
            except Exception as exc:
                print(f"Unexpected error when checking replica set status on {member_admin_uri}: {exc}")
                raise
            
            config_doc = {
                '_id': replica_set_name,
                'members': members
            }
            
            if is_config_server:
                config_doc['configsvr'] = True
            
            # Initiate the replica set
            try:
                with MongoClient(member_admin_uri, serverSelectionTimeoutMS=3000, connect=False) as client:
                    client.admin.command('ping')
                    client.admin.command('replSetInitiate', config_doc)
                    
                    rs_uri = f"mongodb://{member['host']}/?replicaSet={replica_set_name}"
                    self._wait_for_primary(rs_uri, replica_set_name)
                    
                    print(f"Initiated replica set '{replica_set_name}' on {member['host']}.")
                    break # Exit after successful initiation
            except errors.OperationFailure as exc:
                print(f"Failed to initiate replica set '{replica_set_name}' on {member['host']}: {exc}")
            except errors.PyMongoError as exc:
                print(f"PyMongo error when initiating replica set on {member['host']}: {exc}")
            except Exception as exc:
                print(f"Unexpected error when initiating replica set on {member['host']}: {exc}")
                raise

    def _wait_for_primary(self, uri: str, repl_name: str, timeout: int = 60) -> None:
        """Poll a replica set until it reaches PRIMARY state."""

        deadline = time.time() + timeout
        last_error = None
        while time.time() < deadline:
            try:
                with MongoClient(uri, serverSelectionTimeoutMS=3000, connect=False) as client:
                    status = client.admin.command('replSetGetStatus')
                    members = status.get('members', [])
                    for member in members:
                        if member.get('self') and member.get('stateStr') == 'PRIMARY':
                            print(
                                "Replica set %s reached PRIMARY state via %s",
                                repl_name,
                                self._scrub_uri(uri),
                            )
                            return
            except errors.OperationFailure as exc:
                last_error = exc
            except Exception as exc:
                last_error = exc
            time.sleep(2)

        raise RuntimeError(
            f"Replica set {repl_name} did not reach PRIMARY state within {timeout}s: {last_error}"
        )
    
    
    def configure_zones(self, router_client: MongoClient, collection: str, shard: MongodbHost, min_key: int, max_key: int):
        """Configures zone for a given collection and shard."""
        zone = f"{shard.replica_set_name}_zone"
        try:
            router_client.admin.command(
                'addShardToZone',
                shard.replica_set_name,
                zone=zone
            )
            print(f"Added shard {shard.replica_set_name} to zone '{zone}' for collection '{collection}'.")
        except errors.OperationFailure as exc:
            if 'already exists' in str(exc):
                print(f"Zone '{zone}' already exists for shard {shard.replica_set_name}.")
            else:
                print(f"PyMongo error when adding zone for collection '{collection}': {exc}")
                return
        except Exception as exc:
            print(f"Unexpected error when adding zone for collection '{collection}': {exc}")
            raise
        
        try:
            router_client.admin.command(
                'updateZoneKeyRange',
                self.config.database + '.' + collection,
                min={'shard_key': min_key},
                max={'shard_key': max_key},
                zone=zone
            )
            print(f"Updated zone key range for collection '{collection}' to zone '{zone}' with range [{min_key}, {max_key}).")
        except errors.OperationFailure as exc:
            if "overlap" in str(exc) or "already" in str(exc):
                print(f"Zone key range for collection '{collection}' already set for zone '{zone}'.")
            else:
                print(f"PyMongo error when updating zone key range for collection '{collection}': {exc}")
                return
        except Exception as exc:
            print(f"Unexpected error when updating zone key range for collection '{collection}': {exc}")
            raise
        
    def create_admin_user(self):
        # Create admin user if not exists    
        with MongoClient(
            self.router_host.get_client_connection(admin=True, auth=False),
            connect=False,
            serverSelectionTimeoutMS=5000
        ) as client:
            users_info = client.admin.command(
                "usersInfo",
                self.config.admin_username,
            ).get("users", [])

            if users_info:
                print(f"Admin user '{self.config.admin_username}' already present; skipping creation.")
                return
            try:
                client.admin.command(
                    'createUser',
                    self.config.admin_username,
                    pwd=self.config.admin_password,
                    roles=[{'role': 'root', 'db': 'admin'}]
                )
                print(f"Created admin user '{self.config.admin_username}'.")
            except errors.OperationFailure as exc:
                if "already exists" in str(exc):
                    print(f"Admin user '{self.config.admin_username}' already exists (detected during creation).")
                    return
                raise
