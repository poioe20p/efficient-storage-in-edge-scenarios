import logging
import time
from urllib.parse import urlparse, urlunparse

from config import MongoConfig
from pymongo import MongoClient, errors


logger = logging.getLogger(__name__)

CONFIG_REPL_SET = "configReplSet"


class MongoDatabase:
    """MongoDB orchestration for SDN controller: sets up replica sets, sharding, and collections."""

    def __init__(self, config: MongoConfig):
        self._config = config
        router_host = getattr(config, "router_host", "localhost")
        router_port_raw = getattr(config, "router_port", "27017")
        router_port = int(router_port_raw) if str(router_port_raw).isdigit() else 27017
        router_uri_with_auth = config.admin_uri(host=router_host, port=router_port)
        router_uri_no_auth = f"mongodb://{router_host}:{router_port}/admin"
        self._router_host = router_host
        self._router_port = router_port
        self._router_uri_no_auth = router_uri_no_auth
        self.mongo_router_client: MongoClient = MongoClient(
            host=router_uri_with_auth,
            connect=False,
            serverSelectionTimeoutMS=5000,
        )
        try:
            self.mongo_router_client.admin.command("ping")
            self._router_uri = router_uri_with_auth
        except errors.OperationFailure as exc:
            if exc.code not in (13, 18):  # Unauthorized / AuthenticationFailed
                raise
            logger.debug(
                "Router ping with credentials failed (%s); retrying without auth", exc
            )
            self.mongo_router_client.close()
            self.mongo_router_client = MongoClient(
                host=router_uri_no_auth,
                connect=False,
                serverSelectionTimeoutMS=5000,
            )
            self.mongo_router_client.admin.command("ping")
            self._router_uri = router_uri_no_auth
        except Exception:
            # Defer other connection issues to later setup steps
            self._router_uri = router_uri_with_auth
        self.db = None

    def setup_sharded_cluster(self, db_name: str, config: MongoConfig) -> None:
        """
        Orchestrate replica sets and sharding using MongoConfig.
        Uses config.hosts and config.port for all DBs; assumes same credentials/port.
        """
        hosts = config.hosts
        port = config.port
        repl_sets = [f"rs_net{i+1}" for i in range(len(hosts))]
        errors_found = []
        config_host = getattr(config, "config_host", "localhost")
        config_port_raw = getattr(config, "config_port", "27019")
        config_port = int(config_port_raw) if str(config_port_raw).isdigit() else 27019

        # Step 0: Ensure config server replica set is initialized
        try:
            config_uri = config.admin_uri(host=config_host, port=config_port)
            self._ensure_replica_set(
                uri=config_uri,
                repl_name=CONFIG_REPL_SET,
                members=[{"_id": 0, "host": f"{config_host}:{config_port}"}],
                is_config=True,
                fallback_uris=[f"mongodb://{config_host}:{config_port}/?directConnection=true"],
            )
        except Exception as exc:
            msg = f"Config server replica-set init error: {exc}"
            logger.error(msg)
            errors_found.append(msg)

        # Step 1: Initialize shard replica sets
        for i, host in enumerate(hosts):
            try:
                admin_uri = config.admin_uri(host=host, port=port)
                self._ensure_replica_set(
                    uri=admin_uri,
                    repl_name=repl_sets[i],
                    members=[{"_id": 0, "host": f"{host}:{port}"}],
                    fallback_uris=[f"mongodb://{host}:{port}/?directConnection=true"],
                )
            except Exception as exc:
                msg = f"Replica-set init error for {host}: {exc}"
                logger.error(msg)
                errors_found.append(msg)

        # Step 2: Connect to mongos/router (assume self.client is mongos)
        try:
            self.mongo_router_client.admin.command('ping')
            logger.debug(
                "Router MongoDB reachable at %s:%s",
                self._router_host,
                self._router_port,
            )
        except Exception as exc:
            msg = f"Error connecting to router MongoDB: {exc}"
            logger.error(msg)
            raise RuntimeError(msg)

        # Step 3: Add shards
        admin = self.mongo_router_client['admin']
        for i, host in enumerate(hosts):
            shard_uri = f"{repl_sets[i]}/{host}:{port}"
            try:
                admin.command('addShard', shard_uri)
            except errors.OperationFailure as exc:
                if 'already exists' not in str(exc):
                    msg = f"Add shard error ({shard_uri}): {exc}"
                    logger.error(msg)
                    errors_found.append(msg)
            except Exception as exc:
                msg = f"Add shard error ({shard_uri}): {exc}"   
                logger.error(msg)
                errors_found.append(msg)

        # Step 4: Enable sharding and shard collections
        try:
            admin.command('enableSharding', db_name)
        except errors.OperationFailure as exc:
            if 'already enabled' not in str(exc):
                msg = f"Enable sharding error: {exc}"
                logger.error(msg)
                errors_found.append(msg)
        except Exception as exc:
            msg = f"Enable sharding error: {exc}"
            logger.error(msg)
            errors_found.append(msg)

        # Shard 'events' and 'topology' collections by datapath id (dpid) hash
        for coll in ['events', 'topology']:
            try:
                admin.command(
                    'shardCollection',
                    f"{db_name}.{coll}",
                    key={'dpid': 'hashed'}
                )
            except errors.OperationFailure as exc:
                if 'is already sharded' not in str(exc):
                    msg = f"Shard collection error ({coll}): {exc}"
                    logger.error(msg)
                    errors_found.append(msg)
            except Exception as exc:
                msg = f"Shard collection error ({coll}): {exc}"
                logger.error(msg)
                errors_found.append(msg)

        if errors_found:
            raise RuntimeError("; ".join(errors_found))

    def _ensure_replica_set(
        self,
        uri: str,
        repl_name: str,
        members,
        is_config: bool = False,
        fallback_uris=None,
    ) -> None:
        """Ensure the replica set referenced by ``uri`` is initialized and PRIMARY."""

        candidates = [uri] + list(fallback_uris or [])
        last_exc = None
        for candidate in candidates:
            try:
                self._ensure_replica_set_with_uri(
                    uri=candidate,
                    repl_name=repl_name,
                    members=members,
                    is_config=is_config,
                )
                return
            except errors.OperationFailure as exc:
                last_exc = exc
                if exc.code == 18 and candidate is not candidates[-1]:
                    logger.debug(
                        "Replica set %s auth failed via %s; trying next URI",
                        repl_name,
                        self._scrub_uri(candidate),
                    )
                    continue
                raise
            except Exception as exc:
                last_exc = exc
                if candidate is not candidates[-1]:
                    logger.debug(
                        "Replica set %s init via %s failed (%s); trying next URI",
                        repl_name,
                        self._scrub_uri(candidate),
                        exc,
                    )
                    continue
                raise

        if last_exc:
            raise last_exc

    def _ensure_replica_set_with_uri(self, uri: str, repl_name: str, members, is_config: bool) -> None:
        """Internal helper that performs replica-set init using a specific URI."""

        def _with_replica_query_param(base_uri: str) -> str:
            parsed = urlparse(base_uri)
            query = f"replicaSet={repl_name}" if not parsed.query else f"{parsed.query}&replicaSet={repl_name}"
            return urlunparse(parsed._replace(query=query))

        display_uri = self._scrub_uri(uri)

        # First, check current status.
        try:
            with MongoClient(uri, serverSelectionTimeoutMS=3000, connect=False) as client:
                client.admin.command('replSetGetStatus')
                logger.debug("Replica set %s already initialized at %s", repl_name, display_uri)
                return
        except errors.OperationFailure as exc:
            if exc.code != 94:  # 94 == NotYetInitialized
                raise
        except Exception as exc:
            logger.debug("Replica set status check failed for %s via %s: %s", repl_name, display_uri, exc)

        config_doc = {
            '_id': repl_name,
            'members': members,
        }
        if is_config:
            config_doc['configsvr'] = True

        logger.info("Initializing replica set %s via %s", repl_name, display_uri)
        with MongoClient(uri, serverSelectionTimeoutMS=5000, connect=False) as client:
            client.admin.command('ping')
            client.admin.command('replSetInitiate', config_doc)

        rs_uri = _with_replica_query_param(uri)
        self._wait_for_primary(rs_uri, repl_name)

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
                            logger.info(
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

    @staticmethod
    def _scrub_uri(uri: str) -> str:
        """Remove credentials from a MongoDB URI for logging purposes."""

        if "@" not in uri:
            return uri
        parsed = urlparse(uri)
        netloc = parsed.hostname or ""
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"
        return urlunparse(parsed._replace(netloc=netloc))

    def ensure_event_collection(self) -> None:
        if self.db is None:
            return
        if "events" not in self.db.list_collection_names():
            self.db.create_collection("events")
            # self.db.create_collection(
            #     "events",
            #     {
            #         "timeseries": {
            #             "timeField": "ts",
            #             "metaField": "metadata",
            #             "granularity": "seconds",
            #         }
            #     },
            # )
        # self.db.events.create_index(
        #     {"createdAt": 1},
        #     expireAfterSeconds=60 * 60 * 12,
        # )

    def ensure_topology_collection(self) -> None:
        if self.db is None:
            return
        if "topology" not in self.db.list_collection_names():
            self.db.create_collection("topology")
