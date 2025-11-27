import logging
import time
from urllib.parse import urlparse, urlunparse
from config import MongoConfig, DEFAULT_MONGO_HOST_IP
from pymongo import MongoClient, errors
from typing import Optional
from models.mongodb_host import MongodbHost, MongodbConfigServer, MongodbRouter

logger = logging.getLogger(__name__)

CONFIG_REPL_SET = "configReplSet"

class MongoDatabase:
    """MongoDB orchestration for SDN controller: sets up replica sets, sharding, and collections."""

    def __init__(self, config: MongoConfig):
        self._config = config
        self.router_host = MongodbRouter(
            username=config.app_username,
            password=config.app_password,
            admin_username=config.admin_username,
            admin_password=config.admin_password
        )
        router_host = getattr(config, "router_host", "localhost")
        router_port_raw = getattr(config, "router_port", "27017")
        router_port = int(router_port_raw) if str(router_port_raw).isdigit() else 27017

        candidate_hosts = []
        for candidate in [router_host, getattr(config, "config_host", None), DEFAULT_MONGO_HOST_IP]:
            if candidate and candidate not in candidate_hosts:
                candidate_hosts.append(candidate)

        last_exception = None
        self.mongo_router_client = None
        router_retry_attempts = 10
        router_retry_delay = 3

        for candidate_host in candidate_hosts:
            router_uri_with_auth = config.admin_uri(host=candidate_host, port=router_port) #"mongodb://%s:%s@%s:%s/admin"
            router_uri_no_auth = f"mongodb://{candidate_host}:{router_port}/admin"

            def _attempt_connection(uri: str, label: str):
                nonlocal last_exception
                for attempt in range(1, router_retry_attempts + 1):
                    try:
                        client = MongoClient(
                            host=uri,
                            connect=False,
                            serverSelectionTimeoutMS=5000,
                        )
                        client.admin.command("ping")
                        return client
                    except errors.OperationFailure as exc:
                        raise exc
                    except Exception as exc:  # pylint: disable=broad-except
                        last_exception = exc
                        logger.debug(
                            "Router ping attempt %d/%d via %s (%s) failed: %s",
                            attempt,
                            router_retry_attempts,
                            label,
                            uri,
                            exc,
                        )
                        time.sleep(router_retry_delay)
                if last_exception is not None:
                    raise last_exception
                raise RuntimeError(
                    f"Ping attempts exhausted for router uri {uri}"
                )

            try:
                client = _attempt_connection(router_uri_with_auth, "auth")
                self.mongo_router_client = client
                self._router_host = candidate_host
                self._router_port = router_port
                self._router_uri_no_auth = router_uri_no_auth
                self._router_uri = router_uri_with_auth
                last_exception = None
                break
            except errors.OperationFailure as exc:
                if exc.code not in (13, 18):
                    last_exception = exc
                    logger.debug(
                        "Router auth ping failed via %s:%s with non-auth error: %s",
                        candidate_host,
                        router_port,
                        exc,
                    )
                    continue
                logger.debug(
                    "Router ping with credentials failed via %s:%s (%s); retrying without auth",
                    candidate_host,
                    router_port,
                    exc,
                )
                try:
                    client = _attempt_connection(router_uri_no_auth, "no-auth")
                    self.mongo_router_client = client
                    self._router_host = candidate_host
                    self._router_port = router_port
                    self._router_uri_no_auth = router_uri_no_auth
                    self._router_uri = router_uri_no_auth
                    last_exception = None
                    break
                except Exception as inner_exc:  # pylint: disable=broad-except
                    last_exception = inner_exc
                    logger.debug(
                        "Router ping without auth failed via %s:%s: %s",
                        candidate_host,
                        router_port,
                        inner_exc,
                    )
                    continue
            except Exception as exc:  # pylint: disable=broad-except
                last_exception = exc
                logger.debug(
                    "Router ping failed via %s:%s: %s",
                    candidate_host,
                    router_port,
                    exc,
                )
                continue

        if self.mongo_router_client is None:
            raise RuntimeError(
                "Unable to contact Mongo router using configured hosts"
            ) from last_exception

        self.db = None
        self._zone_cache = {}

    def setup_sharded_cluster(self, db_name: str, config: MongoConfig) -> None:
        """
        Orchestrate replica sets and sharding using MongoConfig.
        Uses config.hosts and config.port for all DBs; assumes same credentials/port.
        """
        hosts = config.hosts
        port = config.port
        repl_sets = config.replica_sets
        errors_found = []
        retry_attempts = 5
        retry_delay = 5
        config_host = getattr(config, "config_host", "localhost")
        config_port_raw = getattr(config, "config_port", "27019")
        config_port = int(config_port_raw) if str(config_port_raw).isdigit() else 27019

        # Step 0: Ensure config server replica set is initialized
        for attempt in range(1, retry_attempts + 1):
            try:
                config_uri = config.admin_uri(host=config_host, port=config_port) #"mongodb://%s:%s@%s:%s/admin"
                self._ensure_replica_set(
                    uri=config_uri,
                    repl_name=CONFIG_REPL_SET,
                    members=[{"_id": 0, "host": f"{config_host}:{config_port}"}],
                    is_config=True,
                    fallback_uris=[f"mongodb://{config_host}:{config_port}/?directConnection=true"],
                )
                break
            except Exception as exc:
                if attempt == retry_attempts:
                    msg = f"Config server replica-set init error: {exc}"
                    logger.error(msg)
                    errors_found.append(msg)
                else:
                    logger.warning(
                        "Config server init attempt %d/%d failed: %s",
                        attempt,
                        retry_attempts,
                        exc,
                    )
                    time.sleep(retry_delay)

        # Step 1: Initialize shard replica sets
        shard_targets = []
        for i, host in enumerate(hosts):
            success = False
            for attempt in range(1, retry_attempts + 1):
                try:
                    admin_uri = config.admin_uri(host=host, port=port) #"mongodb://%s:%s@%s:%s/admin"
                    self._ensure_replica_set(
                        uri=admin_uri,
                        repl_name=repl_sets[i],
                        members=[{"_id": 0, "host": f"{host}:{port}"}],
                        fallback_uris=[f"mongodb://{host}:{port}/?directConnection=true"],
                    )
                    success = True
                    break
                except Exception as exc:
                    if attempt == retry_attempts:
                        msg = f"Replica-set init error for {host}: {exc}"
                        logger.error(msg)
                        errors_found.append(msg)
                    else:
                        logger.warning(
                            "Replica-set init attempt %d/%d for %s failed: %s",
                            attempt,
                            retry_attempts,
                            host,
                            exc,
                        )
                        time.sleep(retry_delay)
            if success:
                shard_targets.append((repl_sets[i], host))
            else:
                logger.warning(
                    "Skipping shard %s for host %s due to initialization failure",
                    repl_sets[i],
                    host,
                )

        # Step 2: Connect to mongos/router (assume self.client is mongos)
        try:
            self.mongo_router_client.admin.command('ping') #
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
        for shard_name, host in shard_targets:
            shard_uri = f"{shard_name}/{host}:{port}"
            for attempt in range(1, retry_attempts + 1):
                try:
                    admin.command('addShard', shard_uri)
                    break
                except errors.OperationFailure as exc:
                    message = str(exc)
                    if 'already exists' in message:
                        logger.debug("Shard %s already registered", shard_name)
                        break
                    if attempt == retry_attempts:
                        msg = f"Add shard error ({shard_uri}): {exc}"
                        logger.error(msg)
                        errors_found.append(msg)
                    else:
                        logger.warning(
                            "Add shard attempt %d/%d for %s failed: %s",
                            attempt,
                            retry_attempts,
                            shard_uri,
                            exc,
                        )
                        time.sleep(retry_delay)
                except Exception as exc:
                    if attempt == retry_attempts:
                        msg = f"Add shard error ({shard_uri}): {exc}"
                        logger.error(msg)
                        errors_found.append(msg)
                    else:
                        logger.warning(
                            "Add shard attempt %d/%d for %s failed: %s",
                            attempt,
                            retry_attempts,
                            shard_uri,
                            exc,
                        )
                        time.sleep(retry_delay)

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

        # Shard 'events' and 'topology' collections by datapath id (dpid)
        for coll in ['events', 'topology']:
            try:
                admin.command(
                    'shardCollection',
                    f"{db_name}.{coll}",
                    key={'dpid': 1}
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
            logger.warning("Skipping zone configuration because previous errors were detected")
        else:
            try:
                self._configure_zones(admin, db_name, config, repl_sets)
            except Exception as exc:
                msg = f"Zone configuration error: {exc}"
                logger.error(msg)
                errors_found.append(msg)

        try:
            self._ensure_users(config)
        except Exception as exc:
            msg = f"User setup error: {exc}"
            logger.error(msg)
            errors_found.append(msg)

        if errors_found:
            raise RuntimeError("; ".join(errors_found))

    def _configure_zones(self, admin_db, db_name: str, config: MongoConfig, repl_sets) -> None:
        zone_map = getattr(config, "dpid_to_shard_map", {})
        if not zone_map:
            logger.debug("No DPID zone mapping provided; skipping zone configuration")
            return
        self._apply_zone_mapping(admin_db, db_name, repl_sets, zone_map)

    def ensure_zone_assignment(self, mapping, db_name: Optional[str] = None) -> None:
        if not mapping:
            return
        db_name = db_name or getattr(self._config, "database", None)
        if not db_name:
            raise ValueError("Database name must be supplied for zone assignment")
        admin_db = self.mongo_router_client['admin']
        repl_sets = getattr(self._config, "replica_sets", [])
        self._apply_zone_mapping(admin_db, db_name, repl_sets, mapping)

    def _apply_zone_mapping(self, admin_db, db_name: str, repl_sets, zone_map) -> None:
        known_shards = set(repl_sets)
        zone_names = {}
        for shard in set(zone_map.values()):
            if shard not in known_shards:
                raise ValueError(f"Unknown shard '{shard}' in DPID zone mapping")
            zone = f"{shard}_zone"
            zone_names[shard] = zone
            try:
                admin_db.command('addShardToZone', shard, zone=zone)
                logger.info("Added shard %s to zone %s", shard, zone)
            except errors.OperationFailure as exc:
                message = str(exc).lower()
                if "already" in message and "zone" in message:
                    logger.debug("Shard %s already associated with zone %s", shard, zone)
                else:
                    raise

        collections = ['events', 'topology']
        for dpid_value, shard in zone_map.items():
            try:
                dpid_int = int(dpid_value)
            except (TypeError, ValueError):
                logger.debug("Skipping non-integer DPID key %r", dpid_value)
                continue
            cached = self._zone_cache.get(dpid_int)
            if cached == shard:
                continue
            zone = zone_names[shard]
            min_key = {'dpid': dpid_int}
            max_key = {'dpid': dpid_int + 1}
            for coll in collections:
                namespace = f"{db_name}.{coll}"
                try:
                    admin_db.command(
                        'updateZoneKeyRange',
                        namespace,
                        min=min_key,
                        max=max_key,
                        zone=zone,
                    )
                    logger.info(
                        "Assigned dpid %s to shard %s via zone %s for %s",
                        dpid_int,
                        shard,
                        zone,
                        coll,
                    )
                except errors.OperationFailure as exc:
                    message = str(exc).lower()
                    if "overlap" in message or "already" in message:
                        logger.debug(
                            "Zone key range for %s dpid %s already configured: %s",
                            coll,
                            dpid_int,
                            exc,
                        )
                    else:
                        raise
            self._zone_cache[dpid_int] = shard

    def _ensure_users(self, config: MongoConfig) -> None:
        """Ensure admin and application users exist on the mongos router."""

        admin_user = config.admin_username
        admin_password = config.admin_password
        app_user = config.app_username
        app_password = config.app_password
        app_db = config.database

        router_noauth_uri = f"mongodb://{self._router_host}:{self._router_port}/admin"

        try:
            with MongoClient(
                router_noauth_uri,
                connect=False,
                serverSelectionTimeoutMS=5000,
            ) as client:
                client.admin.command(
                    "createUser",
                    admin_user,
                    pwd=admin_password,
                    roles=[{"role": "root", "db": "admin"}],
                )
                logger.info(
                    "Created admin user %s on mongos %s:%s",
                    admin_user,
                    self._router_host,
                    self._router_port,
                )
        except errors.OperationFailure as exc:
            code = getattr(exc, "code", None)
            message = str(exc)
            if code in (51003,) or "already exists" in message:
                logger.debug("Admin user %s already exists on mongos", admin_user)
            elif code in (13, 18):
                logger.debug(
                    "Admin user creation without auth blocked (likely already exists): %s",
                    exc,
                )
            else:
                raise
        except Exception as exc:
            logger.debug(
                "Admin user creation without auth failed via %s:%s: %s",
                self._router_host,
                self._router_port,
                exc,
            )

        admin_auth_uri = config.admin_uri(host=self._router_host, port=self._router_port) #"mongodb://%s:%s@%s:%s/admin"

        for attempt in range(3):
            try:
                with MongoClient(
                    admin_auth_uri,
                    connect=False,
                    serverSelectionTimeoutMS=5000,
                ) as admin_client:
                    admin_client.admin.command("ping")
                    admin_db = admin_client["admin"]
                    users_info = admin_db.command("usersInfo", admin_user).get("users", [])
                    if not users_info:
                        raise RuntimeError(
                            f"Admin user {admin_user} does not exist after creation attempt"
                        )

                    try:
                        admin_client[app_db].command(
                            "createUser",
                            app_user,
                            pwd=app_password,
                            roles=[{"role": "readWrite", "db": app_db}],
                        )
                        logger.info(
                            "Created application user %s with readWrite on %s",
                            app_user,
                            app_db,
                        )
                    except errors.OperationFailure as exc:
                        code = getattr(exc, "code", None)
                        message = str(exc)
                        if code in (51003,) or "already exists" in message:
                            logger.debug(
                                "Application user %s already exists in %s",
                                app_user,
                                app_db,
                            )
                        else:
                            raise
                    break
            except errors.OperationFailure as exc:
                code = getattr(exc, "code", None)
                if code == 18 and attempt < 2:
                    logger.debug(
                        "Admin authentication failed on attempt %d, retrying: %s",
                        attempt + 1,
                        exc,
                    )
                    time.sleep(2)
                    continue
                raise RuntimeError(
                    "Admin authentication failed using configured credentials"
                ) from exc

        if self._router_uri != admin_auth_uri:
            try:
                self.mongo_router_client.close()
            except Exception:
                pass
            self.mongo_router_client = MongoClient(
                host=admin_auth_uri,
                connect=False,
                serverSelectionTimeoutMS=5000,
            )
            self.mongo_router_client.admin.command("ping")
            self._router_uri = admin_auth_uri

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

        rs_uri = _with_replica_query_param(uri) #<uri>?replicaSet=<repl_name>"
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
