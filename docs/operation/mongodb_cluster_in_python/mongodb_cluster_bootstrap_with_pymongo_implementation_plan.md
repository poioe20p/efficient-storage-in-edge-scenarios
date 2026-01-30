# Implementation Plan: MongoDB Sharded Cluster Bootstrap with PyMongo

This document is the step-by-step implementation plan for building an idempotent MongoDB sharded-cluster bootstrapper in Python (PyMongo), matching the cluster built by the existing bash automation.

Related design doc: see `docs/operation/mongodb_cluster_bootstrap_with_pymongo.md`.

---

## 0) Preconditions (Do This First)

1) **Confirm where the code runs**
   - Run the Python bootstrap inside the environment that has reachability to:
     - `192.168.100.4:27019` (configsvr)
     - `192.168.100.4:27020` (mongos)
     - shard endpoints (either internal `10.0.x.4:27018` or NAT endpoints, depending on addressing strategy)
   - In this repo, that is typically the Ubuntu VM / host namespace used by the lab scripts.

2) **Pick an addressing strategy (must be consistent)**
   - Strategy A: internal shard addresses (matches scripts)
     - rs_net1: `10.0.0.4:27018`
     - rs_net2: `10.0.1.4:27018`
   - Strategy B: NAT-exposed shard addresses
     - rs_net1: `192.168.100.2:27018`
     - rs_net2: `192.168.100.2:27118`
   - Decision rule:
     - If `mongos` can reliably route to `10.0.0.0/24` and `10.0.1.0/24`, use Strategy A.
     - If routed firewall policies are strict and internal routing is flaky, use Strategy B.

3) **Ensure containers and networking are already up**
   - Continue using the existing bash scripts for orchestration in Phase A.

---

## 1) Dependencies and Repo Wiring

1) Dependencies
   - `pymongo` is already listed in `requirements.txt`.
   - Keep `dnspython` optional (only needed for SRV URIs; this lab uses direct host:port).

2) Decide code location (recommended)
   - Implement under: `source/sdn_controller/usecases/build_mongodb_cluster/`
   - Keep the bootstrapper independent of OS-Ken runtime so it can run standalone.

3) No CLI (explicit requirement)
    - Expose a single Python entrypoint as a callable:
       - `source/sdn_controller/usecases/build_mongodb_cluster/bootstrap.py` with `bootstrap_cluster()`.
    - The bootstrapper is invoked by importing and calling that function (e.g., from another Python module, from an OS-Ken startup hook, or from the bash orchestration layer).

Deliverable:
- A `bootstrap_cluster()` function that performs the same MongoDB bootstrap steps as `source/scripts/build_setup.sh` (replica sets, addShard, sharding, zones/ranges), but via PyMongo.

---

## 2) Configuration Model (Single Source of Truth)

1) Implement dataclasses
   - `MongoEndpoints`
     - configsvr host/port
     - mongos host/port
     - shard rs names + member endpoints
     - addressing strategy selection
   - `MongoAuth` (optional)
     - username/password/authSource
   - `BootstrapOptions`
     - timeouts, retry delays
     - dry-run
     - strict mode (fail on “exists but different”)

2) Configuration loading
   - Match `source/scripts/build_setup.sh` defaults first (no auth, fixed lab addresses):
     - configsvr: `192.168.100.4:27019` (replSet: `configReplSet`)
     - mongos: `192.168.100.4:27020`
     - shards: `rs_net1/10.0.0.4:27018`, `rs_net2/10.0.1.4:27018`
     - database: `app_db`, sharded collection: `app_db.events`, shard key: `{dpid: 1}`
     - zones: `shard_zone_rs_net1`, `shard_zone_rs_net2`, `ZONE_SIZE = 1_000_000_000`
   - Allow overriding hosts/ports via environment variables so the same code works when the lab IP plan changes.
   - Treat authentication as optional; only enable it if credentials are supplied.

Deliverable:
- A `load_config()` that prints a safe summary of endpoints/strategy and returns a validated config object.

---

## 3) Connection Utilities (Make Failures Fast and Explainable)

1) Build a client factory
   - `build_client(uri, *, direct: bool, appname: str, timeouts...)`
   - Always set `serverSelectionTimeoutMS` and `connectTimeoutMS`.

2) Add connectivity checks
   - `wait_for_mongo(uri, timeout_s)` loops `admin.command('ping')`.
   - Log which URI is being tested and the last error on timeout.

3) Topology-friendly connection modes
   - For not-yet-initiated single-node `mongod`, use `directConnection=true` when appropriate.

Deliverable:
- A small `mongo_client.py` (or similar) used by all bootstrap steps.

---

## 4) Replica Set Ensure Logic (Configsvr + Shards)

### 4.1 Config server RS (`configReplSet`)

1) Detect initialization
   - Call `replSetGetStatus`.
   - Treat `NotYetInitialized` as “not initialized”.

2) Initiate if needed
   - `replSetInitiate` with:
     - `_id: 'configReplSet'`
     - `configsvr: true`
     - member: `192.168.100.4:27019` (or configured endpoint)

3) Wait for PRIMARY
   - Poll `replSetGetStatus` until a member is `PRIMARY`.

### 4.2 Shard replica sets (`rs_net1`, `rs_net2`)

1) Detect initialization (same pattern)
2) Initiate if needed
   - Use the selected addressing strategy for the member `host` string.
3) Wait for PRIMARY

Strictness rule:
- If already initialized, validate:
  - replset name matches
  - member host matches the chosen addressing strategy
- If mismatched, fail fast with a clear message (unless a future `--force` is added).

Deliverable:
- `ensure_config_rs_initialized()`
- `ensure_shard_rs_initialized(replset_name, member_hostport)`

---

## 5) Sharding Ensure Logic (via `mongos`)

### 5.1 Validate `mongos` readiness

1) `ping` mongos
2) Confirm configsvr visibility
   - Run `listShards` (may be empty initially) or `getShardMap`.

### 5.2 Add shards (idempotent)

1) List current shards
   - `mongos.admin.command('listShards')`
2) Add shard if missing
   - `mongos.admin.command('addShard', f"{replset}/{member_hostport}")`
3) Re-list shards for confirmation

### 5.3 Enable sharding + shard the collection

1) Enable sharding on database
   - `enableSharding('app_db')`
2) Ensure shard-key index exists
   - Create index on `app_db.events` for `{ dpid: 1 }`.
3) Shard the collection
   - `shardCollection('app_db.events', key={'dpid': 1})`

Idempotency checks:
- `config.databases` for `partitioned: true`
- `config.collections` for shard key equality

Deliverable:
- `ensure_shard_added()`
- `ensure_sharding_enabled()`
- `ensure_collection_sharded()`

---

## 6) Zones and Zone Ranges (Deterministic and Verified)

1) Define constants
   - `ZONE_SIZE = 1_000_000_000`
   - zone names:
     - `shard_zone_rs_net1`
     - `shard_zone_rs_net2`

2) Assign shards to zones
   - `addShardToZone` for each shard

3) Define ranges over `dpid` space
   - Use `bson.int64.Int64` for `min/max`.
   - Compute ranges deterministically and avoid overlap.

4) Apply ranges with `updateZoneKeyRange`

5) Verify ranges
   - Query `config.tags` and count ranges per zone.

Deliverable:
- `ensure_zone(shard_name, zone_name)`
- `ensure_zone_range(ns, min_doc, max_doc, zone)`

---

## 7) End-to-End “Bootstrap” Orchestrator

1) Implement `bootstrap()` ordering (recommended)
   1. Wait for configsvr endpoint
   2. Ensure config RS initialized + PRIMARY
   3. Wait for shard endpoints
   4. Ensure shard RSs initialized + PRIMARY
   5. Wait for mongos endpoint
   6. Ensure shards added
   7. Ensure sharding enabled + collection sharded
   8. Ensure zones + ranges
   9. Print verification summary

2) Add `--dry-run`
   - Print actions without making changes.

3) Add `--strict/--non-strict`
   - Strict: fail on incompatible existing state.
   - Non-strict: best-effort ensure steps (still no destructive resets).

Deliverable:
- A single `bootstrap()` callable used by the CLI.

---

## 8) Verification Checklist (Automatable Output)

The CLI should print (at minimum):

1) Config RS: PRIMARY exists
2) Shards: `listShards` includes `rs_net1` and `rs_net2`
3) Sharding:
   - `config.databases` shows `app_db` partitioned
   - `config.collections` shows `app_db.events` with `key: {dpid: 1}`
4) Index:
   - `app_db.events` has an index starting with `dpid`
5) Zones:
   - `config.tags` has expected number of ranges per zone
6) Sanity write:
   - Insert two docs with different `dpid` values and confirm queries succeed

---

## 9) Integration (Optional, After Standalone Works)

1) Add a script hook
   - Option A: call Python bootstrap from existing bash setup scripts.
   - Option B: run manually after `./source/scripts/build_setup.sh`.

2) Controller integration
   - Only if needed: run bootstrap before controller starts logging.

---

## 10) Definition of Done

- Re-running the CLI completes without errors (idempotent).
- Cluster routes writes by `dpid` through `mongos` at `192.168.100.4:27020`.
- Zone ranges exist and are consistent with `ZONE_SIZE`.
- Failures are diagnosable (timeouts, endpoint printed, actionable error messages).
