from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class MongoEndpoint:
    host: str
    port: int

    def as_hostport(self) -> str:
        return f"{self.host}:{self.port}"


@dataclass(frozen=True)
class MongoAuth:
    username: str
    password: str
    auth_source: Optional[str] = None


@dataclass(frozen=True)
class BootstrapOptions:
    readiness_timeout_s: float = 60.0
    rs_primary_timeout_s: float = 180.0
    retry_interval_s: float = 2.0
    server_selection_timeout_ms: int = 2000
    connect_timeout_ms: int = 2000
    socket_timeout_ms: int = 2000


@dataclass(frozen=True)
class ReplicaSetConfig:
    name: str
    members: List[MongoEndpoint]
    is_config_server: bool = False
    zone_name: Optional[str] = None

    def primary_hostport(self) -> str:
        if not self.members:
            raise ValueError(f"Replica set {self.name} must have at least one member")
        return self.members[0].as_hostport()


@dataclass(frozen=True)
class MongoClusterConfig:
    config_replicaset: ReplicaSetConfig
    shards: List[ReplicaSetConfig]
    mongos: MongoEndpoint
    database: str
    collection: str
    shard_key: Dict[str, int]
    zone_size: int
    options: BootstrapOptions = field(default_factory=BootstrapOptions)
    auth: Optional[MongoAuth] = None

    @property
    def collection_namespace(self) -> str:
        return f"{self.database}.{self.collection}"


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw else default


def _load_auth() -> Optional[MongoAuth]:
    username = os.getenv("MONGO_USERNAME")
    password = os.getenv("MONGO_PASSWORD")
    if not username or not password:
        return None
    auth_source = os.getenv("MONGO_AUTHSOURCE", "admin")
    return MongoAuth(username=username, password=password, auth_source=auth_source)


def load_cluster_config() -> MongoClusterConfig:
    config_host = os.getenv("MONGO_CONFIG_HOST", "192.168.100.4")
    config_port = _env_int("MONGO_CONFIG_PORT", 27019)
    config_rs = os.getenv("MONGO_CONFIG_RS", "configReplSet")

    mongos_host = os.getenv("MONGO_MONGOS_HOST", "192.168.100.4")
    mongos_port = _env_int("MONGO_MONGOS_PORT", 27020)

    shard_defaults = (
        ("rs_net1", "shard_zone_rs_net1", "MONGO_RS_NET1_HOST", "MONGO_RS_NET1_PORT", "10.0.0.4", 27018),
        ("rs_net2", "shard_zone_rs_net2", "MONGO_RS_NET2_HOST", "MONGO_RS_NET2_PORT", "10.0.1.4", 27018),
    )

    shards: List[ReplicaSetConfig] = []
    for name, zone, host_env, port_env, default_host, default_port in shard_defaults:
        host = os.getenv(host_env, default_host)
        port = _env_int(port_env, default_port)
        shards.append(
            ReplicaSetConfig(
                name=name,
                members=[MongoEndpoint(host=host, port=port)],
                zone_name=zone,
            )
        )

    options = BootstrapOptions()
    auth = _load_auth()
    zone_size = _env_int("MONGO_ZONE_SIZE", 1_000_000_000)

    return MongoClusterConfig(
        config_replicaset=ReplicaSetConfig(
            name=config_rs,
            members=[MongoEndpoint(host=config_host, port=config_port)],
            is_config_server=True,
        ),
        shards=shards,
        mongos=MongoEndpoint(host=mongos_host, port=mongos_port),
        database=os.getenv("MONGO_APP_DB", "app_db"),
        collection=os.getenv("MONGO_APP_COLLECTION", "events"),
        shard_key={"dpid": 1},
        zone_size=zone_size,
        options=options,
        auth=auth,
    )


__all__ = [
    "BootstrapOptions",
    "MongoAuth",
    "MongoClusterConfig",
    "MongoEndpoint",
    "ReplicaSetConfig",
    "load_cluster_config",
]
