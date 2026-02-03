## Plan: Make Mongo instances data-driven

Move “how many mongods/mongos/configsvr exist” out of Python code and into a single declarative cluster spec (YAML/JSON/env). The `build_mongodb_cluster` code should consume that spec to (a) init config server RS, (b) init each shard RS, (c) add shards to mongos, and (d) configure zones/ranges. This makes adding/removing instances a spec edit (plus Docker topology changes), not a code edit.

### Steps 1–5
1. Define a `ClusterSpec` schema (router/configsvr/shards/zones/collections) and document it in [source/sdn_controller/usecases/build_mongodb_cluster/README.md](source/sdn_controller/usecases/build_mongodb_cluster/README.md).
2. Add a spec loader (e.g., new `cluster_spec.py`) that reads `MONGO_CLUSTER_SPEC_PATH` (YAML/JSON) or `MONGO_CLUSTER_SPEC_JSON`, with defaults matching current behavior in [source/sdn_controller/usecases/build_mongodb_cluster/setup_cluster.py](source/sdn_controller/usecases/build_mongodb_cluster/setup_cluster.py).
3. Refactor orchestration to iterate over `spec.shards[]` instead of hardcoded shard lists in [source/sdn_controller/usecases/build_mongodb_cluster/setup_cluster.py](source/sdn_controller/usecases/build_mongodb_cluster/setup_cluster.py) and/or [source/sdn_controller/usecases/build_mongodb_cluster/cluster_manager.py](source/sdn_controller/usecases/build_mongodb_cluster/cluster_manager.py).
4. Extend `ShardReplicaSet` and `ConfigServer` to accept `members[]` (still defaulting to single-member), so scaling a replica set becomes a spec change in [source/sdn_controller/usecases/build_mongodb_cluster/shard_replica_set.py](source/sdn_controller/usecases/build_mongodb_cluster/shard_replica_set.py) and [source/sdn_controller/usecases/build_mongodb_cluster/config_server.py](source/sdn_controller/usecases/build_mongodb_cluster/config_server.py).
5. Make zones stable by preferring explicit per-shard ranges in the spec (avoid “index-based zone math”), implemented where zoning is configured in [source/sdn_controller/usecases/build_mongodb_cluster/router.py](source/sdn_controller/usecases/build_mongodb_cluster/router.py).

### Further Considerations
1. Do you want “auto zones” (`zone_size` + shard ordering) or explicit ranges (safer when adding/removing shards)?
2. Should “where to run mongosh” be fixed to the router container (simplifies exec), or kept per-component via `connect_via.container`?
3. If you plan multi-member replica sets, decide whether to support `rs.add()` idempotently or only `rs.initiate()` from scratch.
