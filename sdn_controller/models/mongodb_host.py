from typing import Optional
from pymongo import MongoClient

VALID_IP_SET =("127.0.0.1", "10.0.0.4", "10.0.1.4", "192.168.100.4")

class MongodbHost:
    """Represents a MongoDB host configuration."""

    def __init__(
        self,
        host: str = "10.0.1.4",
        port: int = 27018,
        name: str = "app_db",
        replica_set_name: str = "",
        admin_username: Optional[str] = None,
        admin_password: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None
    ):
        self.host = host
        self.port = port
        self.app_name = name
        self.username = username
        self.password = password
        self.admin_username = admin_username
        self.admin_password = admin_password
        self.replica_set_name = replica_set_name
    
    def get_simple_connection_string(self, add_app: bool = False) -> str:
        """Constructs the simple MongoDB connection string."""
        if add_app:
            return f"mongodb://{self.host}:{self.port}/{self.app_name}"
        else:
            return f"mongodb://{self.host}:{self.port}/"

    def get_auth_connection_string(self, add_app: bool = False, admin: bool = False) -> str:
        """Constructs the MongoDB connection string."""
        
        if admin:
            if self.admin_username and self.admin_password:
                if add_app:
                    return f"mongodb://{self.admin_username}:{self.admin_password}@{self.host}:{self.port}/{self.app_name}"
                return f"mongodb://{self.admin_username}:{self.admin_password}@{self.host}:{self.port}/"
            print("Admin credentials not provided. Returning unauthenticated connection string.")
            return self.get_simple_connection_string(add_app=add_app)
        else:
            if self.username and self.password:
                if add_app:
                    return f"mongodb://{self.username}:{self.password}@{self.host}:{self.port}/{self.app_name}"
                return f"mongodb://{self.username}:{self.password}@{self.host}:{self.port}/"
            print("User credentials not provided. Returning unauthenticated connection string.")
            return self.get_simple_connection_string(add_app=add_app)
    
    def get_client_connection(self, admin: bool = False, auth: bool = False) -> MongoClient:
        """Returns a MongoClient instance for the host."""
        if admin:
            if auth:
                conn_str = f"{self.get_auth_connection_string(admin=True)}"
            else:
                conn_str = f"{self.get_simple_connection_string()}"
        else:
            if auth:
                conn_str = self.get_auth_connection_string()
            else:
                conn_str = self.get_simple_connection_string()
        return MongoClient(conn_str, connect=False, serverSelectionTimeoutMS=5000)
    
    def get_shard_connection_string(self) -> str:
        """Constructs the MongoDB shard connection string."""
        return f"{self.replica_set_name}/{self.host}:{self.port}"
    
class MongodbRouter(MongodbHost):
    """Represents a MongoDB router configuration."""

    def __init__(self,
                 host: str = "192.168.100.1",
                 port: int = 27020,
                 name: str = "app_db",
                 replica_set_name: str = "configReplSet",
                 admin_username: Optional[str] = None,
                 admin_password: Optional[str] = None,
                 username: Optional[str] = None,
                 password: Optional[str] = None
                 ):
        super().__init__(host, port, name, replica_set_name, admin_username, admin_password, username, password)


class MongodbConfigServer(MongodbHost):
    """Represents a MongoDB config server configuration."""

    def __init__(self,
                 host: str = "192.168.100.1",
                 port: int = 27019,
                 name: str = "app_db",
                 replica_set_name: str = "configReplSet",
                 admin_username: Optional[str] = None,
                 admin_password: Optional[str] = None,
                 username: Optional[str] = None,
                 password: Optional[str] = None
                 ):
        super().__init__(host, port, name, replica_set_name, admin_username, admin_password, username, password)