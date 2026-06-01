# VIP_DATA Edge Epoch and Recovery

## 1. Purpose

This document describes the edge-server-side VIP_DATA runtime: how each edge
server manages per-LAN MongoDB connection epochs, handles failure recovery via
`AutoReconnect` rotation, enforces circuit-breaker protection, and runs
background housekeeping. It covers the edge-side implementation only --
controller-side VIP_DATA routing, DNAT/SNAT installation, and backend
selection are documented separately.

## 2. Current Files

| File | Role |
|------|------|
| `source/docker/edge_server/source/app.py` | Module-level epoch state seeding, housekeeping startup, request teardown hooks |
| `source/docker/edge_server/source/vip_data_mongo_runtime.py` | `_MongoEpoch`, `_LanEpochState`, `_CircuitBreaker`, `timed_db()`, `run_with_request_lease()`, epoch leasing, rotation, housekeeping, `T_dados` accumulation |
| `source/docker/edge_server/source/control_plane_routes.py` | `PUT /vip_data` route -- validates payload, delegates to `apply_vip_update()` |
| `source/docker/edge_server/source/edge_request_lifecycle.py` | `_check_tdados_threshold` after-request hook (observation-only) |
| `source/docker/edge_server/source/edge_server_config.py` | Configuration defaults (`tau_dados_ms`, `circuit_cooldown_s`, `mongo_client_retire_grace_s`, `vip_data_recovery_session_max_age_s`) |

## 3. Fixed LAN Registry and VIP Configuration

### Startup Seeding

`_seed_epoch_states_from_config()` runs at module import time (before
telemetry startup and before the housekeeping thread begins). It constructs
the `_epoch_states` registry from two module-level dictionaries:

```python
vip_data_per_domain = {
    "lan1": "10.0.0.254",
    "lan2": "10.0.1.254",
}
vip_data_recovery_per_domain = {
    "lan1": os.environ.get("VIP_DATA_RECOVERY_N1_IP", "10.0.0.252"),
    "lan2": os.environ.get("VIP_DATA_RECOVERY_N2_IP", "10.0.1.252"),
}
```

Startup validation requires **matching LAN sets** between normal and recovery
VIP maps. If the LAN sets differ, `StorageVipConfigurationError` is raised and
the process fails fast before any telemetry or background threads start.

### Per-LAN State (`_LanEpochState`)

Each LAN entry in `_epoch_states` holds:

| Field | Purpose |
|-------|---------|
| `lifecycle_lock` | Per-LAN `threading.Lock` guarding all epoch transitions |
| `normal_vip_ip` | Current normal VIP IP for the LAN |
| `recovery_vip_ip` | Current recovery VIP IP for the LAN |
| `breaker` | Lazy-initialized `_CircuitBreaker` shared by all requests for that LAN |
| `current` | The active `_MongoEpoch` (normal or recovery) |
| `retiring` | List of epochs that have been rotated out but still hold leases |
| `next_epoch_id` | Monotonic epoch ID counter |

### Epoch (`_MongoEpoch`)

Each epoch owns:

| Field | Purpose |
|-------|---------|
| `epoch_id` | Monotonic integer identity |
| `mode` | `"normal"` or `"recovery"` |
| `vip_ip` | Bound VIP address for this epoch's connections |
| `client` | Lazy `MongoClient` (created on first use, `maxPoolSize=1`) |
| `client_created_at` | Timestamp when the client was first materialized |
| `first_lease_at` | Timestamp of the first request lease against this epoch |
| `lease_count` | Number of active request leases |
| `retiring` / `retire_requested_at` / `drain_deadline` | Retirement bookkeeping |
| `recovery_expires_at` | Bounded recovery expiry (set when the recovery client is first created) |

## 4. Request Boundary and Epoch Leasing

### `timed_db(lan)` -- Legacy Context Manager

The `timed_db(lan)` context manager is the simpler entry point. It:

1. Sets `g.db_last_lan = lan` for failure attribution.
2. Checks for an existing request lease for `lan` in `g.db_request_leases`.
   If one exists and has already failed or completed, raises `PyMongoError`.
3. If no lease exists, calls `_get_or_bind_request_lease(lan)` which checks
   the per-LAN circuit breaker and binds a new `RequestLease` to the current
   epoch.
4. Sets `replay_safe = False` (legacy compatibility).
5. Lazily creates the epoch's `MongoClient` if needed.
6. Yields `client[DB_NAME]`.
7. On `AutoReconnect`, records the breaker failure and re-raises (no rebind).
8. On success, records the breaker success.
9. In `finally`, accumulates elapsed time into `T_dados` per LAN.

### `run_with_request_lease(lan, op_name, replay_safe, fn)` -- Preferred API

The preferred serving-path API wraps an explicit DB operation with bounded
rebind semantics:

1. Checks for existing request lease (rejects failed/completed leases).
2. Binds or reuses a request lease.
3. Sets `replay_safe` (AND-combined with the lease's existing flag).
4. Executes the operation via `_run_db_op_once()`.
5. On `AutoReconnect`, attempts **exactly one rebind** if and only if:
   - This is the first `AutoReconnect` for this operation (`attempts == 1`).
   - The lease has not already been rebound (`rebinds_used == 0`).
   - The operation is marked `replay_safe`.
   - The failed epoch was in `normal` mode (recovery epochs cannot rebind).
   If rebind is allowed, `_rebind_request_lease_after_autoreconnect()` rotates
   the current epoch to recovery (with compare-and-swap), adopts the new
   epoch, and retries. If rebind is not allowed, the lease is marked `FAILED`
   and the `AutoReconnect` propagates.

### Request Lease Lifecycle

A `RequestLease` binds one Flask request to one `_MongoEpoch` per LAN. Key
guarantees:

- **At most one lease per LAN per request.** Repeated DB operations reuse the
  same lease and the same epoch.
- **Lease outlives epoch rotation.** If the current LAN epoch advances, an
  already-bound request keeps using its leased epoch and that epoch's
  `MongoClient`. Only newly admitted requests bind to the newer current epoch.
- **Leases are released once per request** during teardown (via
  `_release_epoch()`), not on each `timed_db(...)` exit.

Important clarification: a newer current epoch does not by itself imply a
different MongoDB backend member. When both the old leased epoch and the newer
current epoch are normal and still target the same `VIP_DATA` address,
controller-side steady-state `VIP_DATA` routing remains broad rather than
per-request or per-epoch. The old request continues using the client and any
connection established through its leased epoch, while a fresh normal epoch may
still be routed to the same backend again. Distinct epoch objects therefore
represent request ownership, cutover, and recovery boundaries, not guaranteed
backend-member separation. A clearly different controller-visible path appears
when the runtime rotates to a recovery VIP or when a normal VIP update changes
the bound VIP for newly created epochs.

## 5. Normal VIP Updates and Recovery Rotation

### `PUT /vip_data` -- Normal VIP Update

`control_plane_routes.py` exposes `PUT /vip_data`:

1. `prepare_vip_update_payload()` validates the JSON body up front.
2. `find_unknown_vip_update_lans()` checks for LANs not in the fixed registry.
   Unknown LANs return JSON `400` with the list of unknown LANs.
3. `apply_vip_update(payload)` iterates over the payload:
   - For each LAN, if the normal VIP has changed, `_rotate_current_epoch_locked()`
     replaces the current epoch with a new normal epoch bound to the new VIP.
   - The old epoch is marked retiring (not force-closed).
4. Returns JSON `200` with the new VIP configuration and list of changed LANs.

Key property: an already leased old epoch keeps its original VIP path. Only
newly admitted requests use the replacement epoch.

### `AutoReconnect` -- Recovery Rotation

When a MongoDB operation raises `AutoReconnect`:

1. `_rebind_request_lease_after_autoreconnect()` is called.
2. If the failed epoch is still the current epoch and is in `normal` mode,
   `_rotate_epoch_if_current_locked()` performs a **compare-and-swap**:
   - Marks the failed current epoch as retiring.
   - Creates a new current recovery epoch bound to `VIP_DATA_RECOVERY_*`.
3. If another request already rotated the epoch (CAS fails), the already-rotated
   epoch is adopted instead -- no duplicate rotation occurs.
4. The request lease is rebound to the new epoch; the old epoch's lease count
   is decremented.

Key constraints:

- Recovery epochs **cannot rebind again**. If a recovery epoch itself fails
  with `AutoReconnect`, the lease is marked `FAILED` and the error propagates.
- At most one rebind per request lease (`rebinds_used < 1`).
- Recovery rotation creates exactly one new current epoch even under
  overlapping concurrent failures on the same old epoch.

## 6. Per-LAN Breaker and `T_dados` Observation

### Circuit Breaker (`_CircuitBreaker`)

Each LAN owns exactly one `_CircuitBreaker` inside its `_LanEpochState`.
Concurrent requests for the same LAN share one breaker state.

| State | Behaviour |
|-------|-----------|
| `CLOSED` | Normal operation -- `check()` returns `True` immediately |
| `OPEN` | Fail-fast -- `check()` returns `False` unless cooldown has elapsed |
| `HALF_OPEN` | One probe allowed -- `check()` returns `True`; success → `CLOSED`, failure → re-`OPEN` |

The breaker trips on `AutoReconnect` via `_record_breaker_outcome_if_authoritative()`,
which only records the outcome if the failing epoch is still the current epoch
(avoiding stale failure attribution from draining epochs). The breaker stays
`OPEN` for `CIRCUIT_COOLDOWN_S` seconds (default **5 s**).

`CircuitOpenError` inherits from `PyMongoError`, so existing `except PyMongoError`
handlers return 503 without code changes -- but the response is near-instant
instead of blocking on `serverSelectionTimeoutMS` (3 s).

The breaker only blocks **first acquisition** of a new request lease. It does
not revoke reuse of a lease the current request already holds.

### `T_dados` -- Observation-Only

`_accumulate_tdados(lan, elapsed)` tracks cumulative MongoDB time per LAN in
`g.time_db_per_lan`. The `_check_tdados_threshold` after-request hook (in
`edge_request_lifecycle.py`) iterates over the per-LAN totals and logs a debug
message when a LAN's elapsed time exceeds `TAU_DADOS_MS` (default **65 ms**).

`T_dados` is **observation-only**:

- It does **not** rotate epochs.
- It does **not** retire or evict clients.
- It does **not** suppress or extend recovery lifecycle.
- Threshold breaches are logged and preserved for telemetry/elasticity logic.

Recovery lifecycle is owned by epoch state and housekeeping, not by
request-end timing heuristics.

## 7. Housekeeping and Retiring Epochs

A dedicated daemon thread (`mongo-epoch-housekeeping`) runs
`_epoch_housekeeping_loop()` with a sweep interval of
`max(1.0, min(RETIRE_GRACE_S / 2, 5.0))` seconds.

### Recovery Rollback (`_roll_expired_recovery_epochs()`)

1. Scans all LANs for current recovery epochs whose `recovery_expires_at` has
   elapsed. The recovery window starts when the recovery `MongoClient` is first
   materialized (`VIP_DATA_RECOVERY_SESSION_MAX_AGE_S`, default **35 s**).
2. For each expired recovery epoch, performs a compare-and-swap rotation back
   to a normal epoch bound to the LAN's current normal VIP.
3. If a LAN hits `StorageVipConfigurationError` (missing normal VIP), the error
   is logged and housekeeping continues for other LANs.

### Retiring Epoch Drain (`_close_drained_epochs()`)

1. Scans all LANs' `retiring` lists.
2. Epochs with `lease_count == 0` have their `MongoClient` closed and are
   removed from the retiring list.
3. Epochs with active leases past their `drain_deadline`
   (`MONGO_CLIENT_RETIRE_GRACE_S`, default **30 s**) produce overdue-drain
   warnings but are **not** force-closed.
4. Unexpected close failures are caught and logged; the loop continues.

### Single-Start Guarantee

`start_epoch_housekeeping()` uses a module-level lock to ensure exactly one
housekeeping thread runs per process, preventing duplicate close/rollback
sweeps against the shared epoch registry.

## 8. Relationship to Controller-Side VIP_DATA Routing

The edge-server epoch runtime interacts with controller-side VIP routing at
three touch points:

1. **Normal VIP connections** (`VIP_DATA_N1` / `VIP_DATA_N2`): The edge server
   opens `MongoClient` connections to the normal VIP. The controller installs
   broad DNAT/SNAT rules (no TCP port scoping) with standard timeouts (30 s
   idle / 120 s hard). The controller's `select_storage()` runs the full WSM
   cost function.

2. **Recovery VIP connections** (`VIP_DATA_RECOVERY_N1` / `VIP_DATA_RECOVERY_N2`):
   After an `AutoReconnect` rotates the current epoch to recovery, the edge
   server opens connections to the recovery VIP. The controller installs
   narrow per-connection DNAT/SNAT rules (TCP port scoped, `tcp_dst=27018`)
   with shorter timeouts (40 s idle / 45 s hard). The controller's
   `select_storage(recovery=True)` excludes the remembered last-normal backend
   when another candidate exists.

3. **`PUT /vip_data` updates**: Changing the normal VIP on the edge server
   causes newly admitted requests to target a different VIP address. The
   controller treats this as a fresh `PacketIn` and performs normal backend
   selection. The edge server does not coordinate with the controller during
   the update -- it simply rotates its local epoch.

The edge server does **not** duplicate controller selector logic. It delegates
all backend choice to the controller via the VIP address it connects to. The
edge server's recovery responsibility is limited to blast-radius reduction
(separating new requests from old leased state) and bounded retry (at most one
rebind per request).

## 9. Current Implementation Reference

| Reference | File |
|-----------|------|
| Edge-side epoch model baseline (this document's primary source) | [`implementation/vip_data_recovery_epoch_model.md`](implementation/vip_data_recovery_epoch_model.md) |
| Controller-side VIP routing (DNAT/SNAT, recovery narrow flow) | [`vip_routing_interception_and_flow_rules.md`](vip_routing_interception_and_flow_rules.md) |
| Controller-side backend selection and warm leases | [`vip_routing_backend_selection_and_warm_leases.md`](vip_routing_backend_selection_and_warm_leases.md) |
| System-level mechanisms and request lifecycle | [`../system_mechanisms.md`](../system_mechanisms.md) |

### Key Configuration Defaults

| Env Var | Default | Purpose |
|---------|---------|---------|
| `TAU_DADOS_MS` | `65` | Per-request DB time threshold for observation logging (ms) |
| `CIRCUIT_COOLDOWN_S` | `5` | Circuit breaker cooldown before HALF_OPEN probe (s) |
| `MONGO_CLIENT_RETIRE_GRACE_S` | `30` | Grace period before overdue-drain warnings for retiring epochs (s) |
| `VIP_DATA_RECOVERY_SESSION_MAX_AGE_S` | `35` | Maximum age of a recovery epoch before housekeeping rolls it back to normal (s) |
