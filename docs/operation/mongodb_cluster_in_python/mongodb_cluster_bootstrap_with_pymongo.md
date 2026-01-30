# Plan: Recreate the MongoDB Sharded Cluster Using PyMongo

## Goal
Recreate (idempotently) the same MongoDB sharded cluster that is currently bootstrapped by the bash automation:

- `source/scripts/build_setup.sh`
- `source/scripts/build_network_1.sh`
- `source/scripts/build_network_2.sh`

…but implement the *MongoDB cluster bootstrap* steps using the MongoDB Python SDK (PyMongo) inside `source/sdn_controller/usecases/build_mongodb_cluster/`.

This plan focuses on the MongoDB control-plane actions (replica set init, sharding, add shards, zones/ranges). Container + network orchestration can remain in bash initially, then optionally be migrated to Python.

### Scope / Assumptions
- The Docker containers and networking (routes/iptables/OVS) are already up, and MongoDB processes are listening on the documented IP:port endpoints.
- The Python bootstrap is expected to run in the same environment that can reach `192.168.100.4:27019/27020` and the shard endpoints (typically the Ubuntu VM/host namespace used by the lab scripts, not Windows).
- Authentication/TLS are treated as configurable inputs; the initial implementation should default to **no auth**, matching `source/scripts/build_setup.sh`.

---

## 1) Current Cluster Topology (What the Shell Scripts Build)

### 1.1 Processes
`build_setup.sh` and the network scripts start these components:

1) **Config server replica set**
- Container: `mongodb-config-server`
- Process: `mongod --configsvr --replSet configReplSet --port 27019 --bind_ip 192.168.100.4`
- Address used by clients: `192.168.100.4:27019`

2) **Shard 1 replica set**
- Container: `mongodb-n1` (from `build_network_1.sh`)
- Process: `mongod --shardsvr --replSet rs_net1 --port 27018 --bind_ip_all`
- IP inside lab: `10.0.0.4:27018`

3) **Shard 2 replica set**
- Container: `mongodb-n2` (from `build_network_2.sh`)
- Process: `mongod --shardsvr --replSet rs_net2 --port 27018 --bind_ip_all`
- IP inside lab: `10.0.1.4:27018`

4) **Router (`mongos`)**
- Container: `mongodb-router` (host network)
- Process: `mongos --configdb configReplSet/192.168.100.4:27019 --bind_ip 192.168.100.4 --port 27020`
- Address used by clients: `192.168.100.4:27020`

### 1.2 Network Reachability Assumptions
The router (`mongos`) is on the **host network**, but it needs to reach:

- Config server: `192.168.100.4:27019` (same host namespace)
- Shards: `10.0.0.4:27018` and `10.0.1.4:27018` (lab subnets)

The host routes are programmed in the network scripts:

- Network 1 adds a route so the host can reach `10.0.0.0/24` via the NAT router
- Network 2 adds a route so the host can reach `10.0.1.0/24` via the NAT router

Additionally, NAT rules expose shard ports on the router WAN IP (`192.168.100.2`):

- rs_net1: `192.168.100.2:27018  -> 10.0.0.4:27018`
- rs_net2: `192.168.100.2:27118  -> 10.0.1.4:27018`

…but `build_setup.sh` currently adds shards using the *internal* addresses (`10.0.x.4:27018`).

### 1.3 MongoDB Bootstrap Steps Done Today
From `build_setup.sh`:

1) Config RS init (`configReplSet`)
- Checks `rs.status()` (handles `NotYetInitialized`)
- Runs `rs.initiate({ _id: 'configReplSet', configsvr: true, members: [{host:'192.168.100.4:27019'}] })`
- Waits for PRIMARY

2) Shard RS init (`rs_net1`, `rs_net2`)
- Same pattern: check `rs.status()`, then `rs.initiate({...})`, wait for PRIMARY

3) Start `mongos`

4) Add shards (with retries)
- `sh.addShard('rs_net1/10.0.0.4:27018')`
- `sh.addShard('rs_net2/10.0.1.4:27018')`

5) Enable sharding and shard collection
- `sh.enableSharding('app_db')`
- `sh.shardCollection('app_db.events', { dpid: 1 })`

6) Zones and zone ranges
- `sh.addShardToZone('rs_net1', 'shard_zone_rs_net1')`
- `sh.addShardToZone('rs_net2', 'shard_zone_rs_net2')`
- `sh.updateZoneKeyRange('app_db.events', {dpid: NumberLong(start)}, {dpid: NumberLong(end)}, zoneName)`

---

## 2) Target Python Design

### 2.1 What Goes in Python vs What Stays in Shell
**MongoDB Python SDK (PyMongo) can handle**:
- Replica set initiation and status polling
- Adding shards to `mongos`
- Enabling sharding, sharding collections
- Zones + tag ranges
- Verification queries

**PyMongo cannot handle** (directly):
- Creating Docker containers
- Network namespaces, veth pairs, OVS bridges, iptables rules

So the recommended incremental approach is:

- Phase A (now): keep network/container setup in bash (existing scripts)
- Phase B (now): move MongoDB bootstrap/config to Python (`build_mongodb_cluster`)
- Phase C (optional): migrate container orchestration to Python via Docker SDK (`docker` PyPI package) or `subprocess`

### 2.2 Proposed Python Module Layout
Implement under `source/sdn_controller/usecases/build_mongodb_cluster/` (split into a few small files; do not hide logic in `__init__.py`):

- `MongoEndpoints` (dataclass): host/ports for configsvr, mongos, shard members
- `MongoAuth` (dataclass): username/password/authSource (loaded from env or `.env-mongo`)
- `MongoBootstrapper` (class): methods below
- `bootstrap_cluster()` (function): single entrypoint that executes the full sequence

No CLI requirement:
- Do not build a separate CLI tool.
- The intended usage is to import and call `bootstrap_cluster()` (for example, from the bash orchestration layer or from another Python module).

Key methods:

- `wait_for_mongo(uri, timeout_s)`
- `build_client(uri, *, direct=False, appname='...', server_selection_timeout_ms=...)`
- `rs_is_initialized(client) -> bool`
- `rs_initiate_configsvr(client, hostport)`
- `rs_initiate_shard(client, replset_name, hostport)`
- `wait_for_primary(client, timeout_s)`
- `ensure_shard_added(mongos_client, shard_conn_string)`
- `ensure_sharding_enabled(mongos_client, db_name)`
- `ensure_collection_sharded(mongos_client, ns, key_doc)`
- `ensure_zone(mongos_client, shard_name, zone_name)`
- `ensure_zone_range(mongos_client, ns, min_doc, max_doc, zone)`

All `ensure_*` methods should be **idempotent**.

Design notes:
- Prefer explicit timeouts in all `MongoClient` instances (`serverSelectionTimeoutMS`, `connectTimeoutMS`) so failures are fast and diagnosable.
- For single-node replica sets that are not yet initiated, consider `directConnection=true` to avoid PyMongo waiting for a topology that does not exist yet.
- Keep logs actionable: print which URI is being contacted and which command failed.

---

## 3) Mapping Shell Commands to PyMongo Commands

### 3.1 Replica Set Initiation
Shell uses `rs.initiate()` via `mongosh`.

In PyMongo, use admin commands:

- Status:
  - `client.admin.command('replSetGetStatus')`
  - If it raises an `OperationFailure` with `codeName == 'NotYetInitialized'`, treat as not initialized.

- Initiate:
  - `client.admin.command('replSetInitiate', config_doc)`

- Wait for PRIMARY:
  - loop `replSetGetStatus` until a member has `stateStr == 'PRIMARY'`

### 3.2 Add Shards
Shell uses `sh.addShard(<replSet>/<host:port>)`.

In PyMongo:
- `mongos_client.admin.command('addShard', '<replSet>/<host:port>')`

Idempotency check:
- `mongos_client.admin.command('listShards')` and see if shard already exists.

### 3.3 Enable Sharding + Shard a Collection
Shell uses `sh.enableSharding(db)` and `sh.shardCollection(ns, key)`.

In PyMongo:
- `mongos_client.admin.command('enableSharding', 'app_db')`
- `mongos_client.admin.command('shardCollection', 'app_db.events', key={'dpid': 1})`

Idempotency checks:
- `mongos_client.config.databases.find_one({'_id': 'app_db'})` and verify `partitioned: true`
- `mongos_client.config.collections.find_one({'_id': 'app_db.events'})` and verify `key`

### 3.4 Zones and Zone Ranges
Shell uses `sh.addShardToZone(...)` and `sh.updateZoneKeyRange(...)`.

These are also server commands:

- Add shard to zone:
  - `mongos_client.admin.command({'addShardToZone': shard_name, 'zone': zone_name})`

- Update zone key range:
  - `mongos_client.admin.command({
      'updateZoneKeyRange': 'app_db.events',
      'min': {'dpid': <Int64>},
      'max': {'dpid': <Int64>},
      'zone': zone_name,
    })`

Important: use 64-bit integer types (`bson.int64.Int64`) to match `NumberLong(...)`.

Idempotency checks:
- `mongos_client.config.shards.find_one({'_id': shard_name})` and inspect `tags` / zone mapping
- `mongos_client.config.tags.find({'ns': 'app_db.events', 'tag': zone_name})` for existing ranges

---

## 4) Critical Decision: Which Addresses to Use for Shards

The current scripts add shards using `10.0.x.4:27018`.

This works only if `mongos` can reach those lab subnets via host routing and the host firewall allows forwarded/routed traffic.

### Option A (match current scripts): add shards by internal IPs
- Add shards as:
  - `rs_net1/10.0.0.4:27018`
  - `rs_net2/10.0.1.4:27018`

Pros:
- Matches the network design and the rs.initiate `host` values already used.

Cons:
- Sensitive to host firewall defaults (notably UFW `deny (routed)`), and to correct host routes.

### Option B (more firewall-friendly): add shards by NAT-exposed WAN endpoints
- Add shards as:
  - `rs_net1/192.168.100.2:27018`
  - `rs_net2/192.168.100.2:27118`

If we do this, the replica set config (`rs.initiate`) should also advertise those same host:port values, otherwise `mongos` may learn a member address it cannot reach.

Pros:
- Routes through the NAT router’s WAN interface (often easier to firewall explicitly).

Cons:
- Requires aligning replica set member `host` strings with the NAT endpoints.

**Recommendation:** implement Option A first (faithful reproduction), but code should allow switching to Option B via configuration to unblock environments with strict routed firewall policies.

---

## 5) Robustness Requirements (Python Implementation)

### 5.1 Idempotency
Re-running the bootstrap should not fail if parts already exist.

Plan:
- Wrap every action as `ensure_*`.
- Prefer read-before-write checks.
- Treat common “already exists” errors as success.

### 5.2 Retries and Timeouts
Mongo services can take seconds to elect a PRIMARY.

Plan:
- Implement `retry(func, timeout_s, delay_s, backoff)` helper.
- Use clear progress logs like the shell scripts (attempt counters).

### 5.3 Connectivity Diagnostics
The `mongos` error you hit (`Could not find host matching read preference ... for set configReplSet`) is typically *reachability* from `mongos` to configsvr.

Plan:
- Before `addShard`, verify:
  - `mongos_client.admin.command('ping')`
  - `mongos_client.admin.command('getShardMap')` (or `listShards`) after configsvr is PRIMARY
- Verify config RS:
  - `config_client.admin.command('replSetGetStatus')` returns PRIMARY

Also document firewall prerequisites:
- Host must allow TCP: `27019`, `27020`, and shard access (`27018`) across the chosen path.

### 5.4 Known Pitfalls / Drawbacks (Call These Out Up-Front)

#### A) Replica set “advertised host” mismatch (most common sharding failure)
MongoDB replica sets advertise member addresses via the `host` strings stored in the replica set config. `mongos` learns those addresses and will try to connect to them.

- If you `rs.initiate()` with `10.0.0.4:27018` but later add the shard using a NAT endpoint (`192.168.100.2:27018`), `mongos` may still try `10.0.0.4:27018` and fail if it cannot route there.
- Conversely, initiating with NAT endpoints can break intra-lab connectivity assumptions if other components expect internal IPs.

Mitigation: treat “addressing strategy” (internal vs NAT) as a first-class config, and ensure **replica set member host strings** and **addShard connection strings** use the same reachable addresses.

#### B) PyMongo topology discovery + timeouts can hide root cause
PyMongo may block on server selection when it cannot find a PRIMARY / cannot reach a member.

- Without timeouts, failures can look like “hangs”.
- Errors like `Could not find host matching read preference ... for set configReplSet` often indicate that `mongos` cannot reach the config server PRIMARY, not that the command is wrong.

Mitigation: set `serverSelectionTimeoutMS` + log the underlying exception; separately test reachability (`ping`) to each endpoint before running higher-level steps.

#### C) Idempotency is not just “ignore already exists”
Some states are “already exists but different”, which require a deliberate decision rather than silently continuing.

Examples:
- Replica set already initialized, but with a different `_id`, `configsvr` flag, or member `host` string.
- Sharded collection exists with a different shard key than expected.
- Zone ranges exist but do not match the desired `ZONE_SIZE` or overlap (MongoDB will reject overlaps).

Mitigation: for each `ensure_*`, define a strict “expected state” and fail fast with a helpful diff if the cluster is initialized in an incompatible way (unless a `--force` mode is explicitly added later).

#### D) Sharding prerequisites: indexes and shard key type correctness
For range-based sharding on `{ dpid: 1 }`:
- The collection must have a compatible index for the shard key (implementation should ensure `db.events.create_index([('dpid', 1)])` before `shardCollection`).
- The inserted documents must use the same type consistently (e.g., integers). If `dpid` is sometimes a string, routing and zone ranges may not behave as intended.

Mitigation: ensure index; validate a small sample write/read with `dpid` as an integer and confirm `explain()` shows targeted routing.

#### E) Zone key ranges are subtle (bounds + overlap)
`updateZoneKeyRange` uses half-open intervals: `[min, max)` in practice. Getting endpoints wrong can create gaps/overlaps.

- Overlapping ranges are rejected.
- Gaps may cause inserts to fall outside any zone and be balanced unexpectedly.

Mitigation: compute ranges deterministically, use `bson.int64.Int64` for bounds, and verify ranges by querying `config.tags`.

#### F) Ordering and readiness dependencies
The bootstrap must respect the real readiness chain:
- configsvr RS PRIMARY must exist before `mongos` becomes fully functional.
- shards must be reachable and have PRIMARYs before `addShard` succeeds.

Mitigation: explicit wait loops per component with bounded timeouts; do not conflate “container started” with “MongoDB ready”.

#### G) Auth/TLS drift between environments
If the lab later enables authentication or TLS, the bootstrap will start failing unless it is designed for it.

Mitigation: keep auth parameters centralized and optional; support `authSource` and explicit `username/password` via env vars.

---

## 6) Implementation Steps (What to Build Next)

1) Add dependency
- Ensure `pymongo` is in `requirements.txt` (and `dnspython` if using SRV URIs).

2) Add a runnable entrypoint in Python
- Either:
  - a small CLI script (recommended) under `source/sdn_controller/usecases/build_mongodb_cluster/` that can be executed from the host, or
  - integrate into existing controller bootstrapping.

3) Implement connectivity + RS initialization
- Connect to configsvr at `192.168.100.4:27019`
- `ensure_config_rs_initialized()`
- Start / verify shard mongods are up (initially assume the containers are already running)
- `ensure_shard_rs_initialized(rs_net1, hostport)`
- `ensure_shard_rs_initialized(rs_net2, hostport)`

4) Connect to `mongos` and configure sharding
- `ensure_shard_added(rs_net1/...)`
- `ensure_shard_added(rs_net2/...)`
- `ensure_sharding_enabled('app_db')`
- `ensure_collection_sharded('app_db.events', {'dpid': 1})`

5) Configure zones and ranges
- Derive the same constants as bash:
  - `ZONE_SIZE = 1_000_000_000`
  - order: `[rs_net1, rs_net2]`
  - zones: `shard_zone_rs_net1`, `shard_zone_rs_net2`
- Apply `addShardToZone` and `updateZoneKeyRange`.

6) Verification summary (print-only)
- Print:
  - config RS status
  - listShards output (names only)
  - config.collections entry for `app_db.events`
  - config.tags ranges count per zone

---

## 7) Acceptance Criteria

- Running the Python bootstrap after the containers are up produces a working sharded cluster.
- Re-running the Python bootstrap succeeds (no destructive resets required).
- `mongos` on `192.168.100.4:27020` accepts writes to `app_db.events` and routes by `dpid`.
- Zones and tag ranges exist for both shards using the same `ZONE_SIZE` strategy.

Additional verification strongly recommended:
- `db.events.getIndexes()` includes an index that prefixes `dpid`.
- `mongos` can run `db.events.find({dpid: <value>}).explain('queryPlanner')` and show targeted shard routing.

---

## 8) Nice-to-Have Extensions

- Add a `--dry-run` mode that prints the actions that would be taken.
- Add a `--reset` mode that drops cluster metadata (dangerous; only for clean-room dev).
- Migrate container orchestration to Python:
  - use Docker SDK to start containers (still requires root for netns/iptables/OVS parts)
  - or keep shell for networking but use Docker SDK for Mongo containers only.
