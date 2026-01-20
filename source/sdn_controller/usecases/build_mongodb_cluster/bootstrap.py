from __future__ import annotations

import time
from typing import Dict, Iterable, List, Optional

from bson.int64 import Int64
from pymongo import ASCENDING, MongoClient
from pymongo.errors import OperationFailure, PyMongoError

from .config import (
    MongoClusterConfig,
    MongoEndpoint,
    ReplicaSetConfig,
    load_cluster_config,
)


class MongoBootstrapper:
    def __init__(self, config: MongoClusterConfig):
        self.config = config

    def bootstrap(self) -> None:
        self._ensure_replica_set(self.config.config_replicaset, "config server")
        for shard in self.config.shards:
            self._ensure_replica_set(shard, f"shard {shard.name}")

        mongos_client = self._build_client(
            self.config.mongos, appname="mongo-bootstrap-mongos"
        )
        try:
            self._wait_for_ping(
                mongos_client,
                f"mongos at {self.config.mongos.as_hostport()}",
                self.config.options.readiness_timeout_s,
            )
            shards = self._ensure_shards_registered(mongos_client)
            self._ensure_sharding_enabled(mongos_client)
            self._ensure_collection_sharded(mongos_client)
            self._ensure_zones(mongos_client)
            self._print_summary(mongos_client, shards)
        finally:
            mongos_client.close()

    def _ensure_replica_set(self, rs_config: ReplicaSetConfig, description: str) -> None:
        endpoint = rs_config.members[0]
        client = self._build_client(
            endpoint, appname=f"mongo-bootstrap-{rs_config.name}", direct=True
        )
        try:
            self._wait_for_ping(
                client,
                f"{description} at {endpoint.as_hostport()}",
                self.config.options.readiness_timeout_s,
            )
            status = self._safe_repl_status(client)
            if status is None:
                print(f"[mongo-bootstrap] Initiating replica set {rs_config.name}")
                self._initiate_replica_set(client, rs_config)
            else:
                self._assert_members_match(rs_config, status)
            self._wait_for_primary(client, rs_config)
        finally:
            client.close()

    def _wait_for_ping(self, client: MongoClient, label: str, timeout_s: float) -> None:
        deadline = time.time() + timeout_s
        last_error: Optional[Exception] = None
        while time.time() < deadline:
            try:
                client.admin.command("ping")
                return
            except PyMongoError as exc:
                last_error = exc
                time.sleep(self.config.options.retry_interval_s)
        raise TimeoutError(f"Timed out waiting for {label}: {last_error}")

    def _safe_repl_status(self, client: MongoClient) -> Optional[Dict]:
        try:
            return client.admin.command("replSetGetStatus")
        except OperationFailure as exc:
            code_name = exc.details.get("codeName") if exc.details else None
            if exc.code == 94 or code_name == "NotYetInitialized":
                return None
            raise

    def _initiate_replica_set(
        self, client: MongoClient, rs_config: ReplicaSetConfig
    ) -> None:
        members = [
            {"_id": idx, "host": endpoint.as_hostport()}
            for idx, endpoint in enumerate(rs_config.members)
        ]
        config_doc: Dict = {"_id": rs_config.name, "members": members}
        if rs_config.is_config_server:
            config_doc["configsvr"] = True
        client.admin.command("replSetInitiate", config_doc)

    def _assert_members_match(
        self, rs_config: ReplicaSetConfig, status: Dict
    ) -> None:
        expected = {endpoint.as_hostport() for endpoint in rs_config.members}
        actual = {member.get("name") for member in status.get("members", [])}
        if expected != actual:
            raise RuntimeError(
                f"Replica set {rs_config.name} members {actual} != expected {expected}"
            )

    def _wait_for_primary(self, client: MongoClient, rs_config: ReplicaSetConfig) -> None:
        deadline = time.time() + self.config.options.rs_primary_timeout_s
        while time.time() < deadline:
            status = self._safe_repl_status(client)
            if status:
                for member in status.get("members", []):
                    if member.get("stateStr") == "PRIMARY":
                        print(
                            f"[mongo-bootstrap] Replica set {rs_config.name} PRIMARY at {member.get('name')}"
                        )
                        return
            time.sleep(self.config.options.retry_interval_s)
        raise TimeoutError(f"Timed out waiting for PRIMARY in {rs_config.name}")

    def _ensure_shards_registered(self, mongos_client: MongoClient) -> List[Dict]:
        shards = self._list_shards(mongos_client)
        for shard_config in self.config.shards:
            expected_host = self._shard_connection_string(shard_config)
            existing = next(
                (sh for sh in shards if sh.get("_id") == shard_config.name), None
            )
            if existing:
                if existing.get("host") != expected_host:
                    raise RuntimeError(
                        f"Shard {shard_config.name} already registered with host "
                        f"{existing.get('host')} (expected {expected_host})"
                    )
                continue
            print(
                f"[mongo-bootstrap] Adding shard {shard_config.name} ({expected_host})"
            )
            mongos_client.admin.command("addShard", expected_host)
            shards = self._list_shards(mongos_client)
        return shards

    def _list_shards(self, mongos_client: MongoClient) -> List[Dict]:
        result = mongos_client.admin.command("listShards")
        return result.get("shards", [])

    def _ensure_sharding_enabled(self, mongos_client: MongoClient) -> None:
        config_db = mongos_client.get_database("config")
        db_doc = config_db["databases"].find_one({"_id": self.config.database})
        if db_doc and db_doc.get("partitioned"):
            return
        print(
            f"[mongo-bootstrap] Enabling sharding for database {self.config.database}"
        )
        mongos_client.admin.command("enableSharding", self.config.database)

    def _ensure_collection_sharded(self, mongos_client: MongoClient) -> None:
        namespace = self.config.collection_namespace
        config_db = mongos_client.get_database("config")
        coll_doc = config_db["collections"].find_one({"_id": namespace})
        db = mongos_client[self.config.database]
        index_spec = [
            (field, ASCENDING if direction >= 0 else -1)
            for field, direction in self.config.shard_key.items()
        ]
        db[self.config.collection].create_index(index_spec, name="dpid_1", background=False)
        if coll_doc:
            if coll_doc.get("key") != self.config.shard_key:
                raise RuntimeError(
                    f"Collection {namespace} already sharded with key {coll_doc.get('key')}"
                )
            return
        print(f"[mongo-bootstrap] Sharding collection {namespace}")
        mongos_client.admin.command(
            "shardCollection", namespace, key=self.config.shard_key
        )

    def _ensure_zones(self, mongos_client: MongoClient) -> None:
        namespace = self.config.collection_namespace
        for idx, shard in enumerate(self.config.shards):
            if not shard.zone_name:
                continue
            zone = shard.zone_name
            self._ensure_zone_assignment(mongos_client, shard.name, zone)
            lower = Int64(idx * self.config.zone_size)
            upper = Int64((idx + 1) * self.config.zone_size)
            self._ensure_zone_range(mongos_client, namespace, lower, upper, zone)

    def _ensure_zone_assignment(
        self, mongos_client: MongoClient, shard_name: str, zone_name: str
    ) -> None:
        config_db = mongos_client.get_database("config")
        shard_doc = config_db["shards"].find_one({"_id": shard_name})
        if shard_doc and zone_name in shard_doc.get("tags", []):
            return
        print(
            f"[mongo-bootstrap] Assigning shard {shard_name} to zone {zone_name}"
        )
        mongos_client.admin.command(
            {"addShardToZone": shard_name, "zone": zone_name}
        )

    def _ensure_zone_range(
        self,
        mongos_client: MongoClient,
        namespace: str,
        lower: Int64,
        upper: Int64,
        zone: str,
    ) -> None:
        config_db = mongos_client.get_database("config")
        query = {
            "ns": namespace,
            "min": {"dpid": lower},
            "max": {"dpid": upper},
            "tag": zone,
        }
        existing = config_db["tags"].find_one(query)
        if existing:
            return
        print(
            f"[mongo-bootstrap] Configuring zone range {namespace} {lower} -> {upper} for {zone}"
        )
        mongos_client.admin.command(
            {
                "updateZoneKeyRange": namespace,
                "min": {"dpid": lower},
                "max": {"dpid": upper},
                "zone": zone,
            }
        )

    def _print_summary(self, mongos_client: MongoClient, shards: List[Dict]) -> None:
        print("\n[mongo-bootstrap] Summary")
        config_primary = self._fetch_primary(self.config.config_replicaset)
        print(
            f"  Config replica set {self.config.config_replicaset.name} primary: {config_primary}"
        )
        print("  Shards:")
        for shard in shards:
            print(f"    - {shard.get('_id')}: {shard.get('host')}")
        namespace = self.config.collection_namespace
        config_db = mongos_client.get_database("config")
        coll_doc = config_db["collections"].find_one({"_id": namespace})
        print(f"  Collection {namespace} shard key: {coll_doc.get('key') if coll_doc else 'n/a'}")
        tag_counts = self._group_tag_counts(config_db["tags"].find({"ns": namespace}))
        for zone, count in tag_counts.items():
            print(f"  Zone {zone}: {count} range(s)")

    def _fetch_primary(self, rs_config: ReplicaSetConfig) -> str:
        endpoint = rs_config.members[0]
        client = self._build_client(
            endpoint, appname=f"mongo-bootstrap-summary-{rs_config.name}", direct=True
        )
        try:
            status = self._safe_repl_status(client)
            if not status:
                return "not-initialized"
            for member in status.get("members", []):
                if member.get("stateStr") == "PRIMARY":
                    return str(member.get("name"))
            return "no-primary"
        finally:
            client.close()

    def _group_tag_counts(self, documents: Iterable[Dict]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for doc in documents:
            tag = doc.get("tag")
            counts[tag] = counts.get(tag, 0) + 1
        return counts

    def _build_client(
        self,
        endpoint: MongoEndpoint,
        *,
        appname: str,
        direct: bool = False,
        replica_set: Optional[str] = None,
    ) -> MongoClient:
        kwargs = {
            "appname": appname,
            "serverSelectionTimeoutMS": self.config.options.server_selection_timeout_ms,
            "connectTimeoutMS": self.config.options.connect_timeout_ms,
            "socketTimeoutMS": self.config.options.socket_timeout_ms,
        }
        if direct:
            kwargs["directConnection"] = True
        if replica_set:
            kwargs["replicaSet"] = replica_set
        if self.config.auth:
            kwargs["username"] = self.config.auth.username
            kwargs["password"] = self.config.auth.password
            if self.config.auth.auth_source:
                kwargs["authSource"] = self.config.auth.auth_source
        uri = f"mongodb://{endpoint.host}:{endpoint.port}"
        return MongoClient(uri, **kwargs)

    def _shard_connection_string(self, shard: ReplicaSetConfig) -> str:
        return f"{shard.name}/{shard.primary_hostport()}"


def bootstrap_cluster(config: Optional[MongoClusterConfig] = None) -> None:
    cluster_config = config or load_cluster_config()
    MongoBootstrapper(cluster_config).bootstrap()


__all__ = ["MongoBootstrapper", "bootstrap_cluster"]
