# Implementation Plan & Guide — VIP Recovery Removal

**Date**: 2026-06-07
**Status**: Plan — awaiting approval
**Scope**: Edge-side `vip_data_mongo_runtime.py`, `edge_server_config.py` + Controller-side cleanup in `ingress.py`, `selection.py`, `state.py`, `config.py`, `vip_routing.py`, `flows.py`, `topology/topology.py`, `main_n*.py`, `compute_node_manager.py`, `telemetry/models.py`
**Depends on**: [conntrack_vip_routing](../conntrack_vip_routing/conntrack_vip_routing_plan.md) (deployed together)

## 1. Motivation

The VIP recovery mechanism was designed to work around stale OVS flow rules.
When a storage backend was removed from the VIP_DATA pool, the existing DNAT
flow rule continued routing new connections to the dead backend for up to
120 seconds. The recovery VIP (`10.0.0.252` / `10.0.1.252`) provided an
alternate IP address that forced a fresh `select_storage` call — bypassing
the stale rule.

The [conntrack_vip_routing plan](../conntrack_vip_routing/conntrack_vip_routing_plan.md)
eliminates stale rules at the source by:
1. Using OVS conntrack so forward rules can be safely deleted while
   connections are in flight
2. Proactively deleting forward rules on `unregister_storage_backend`

With stale rules gone, the recovery VIP is no longer needed. This plan
removes the recovery VIP infrastructure from both the edge server and the
controller.

**Evidence from v5.x experiments**: The recovery path had a 0-51% success
rate across runs. It was never a reliable mechanism — it was a workaround
for a problem that conntrack now solves definitively.

## 2. What Gets Removed

### Edge Server

| Component | Location | Why removed |
|-----------|----------|-------------|
| `vip_data_recovery_per_domain` | Module-level dict | Recovery VIP addresses no longer needed |
| `_LanEpochState.recovery_vip_ip` | Dataclass field | No recovery mode |
| `_MongoEpoch.recovery_expires_at` | Dataclass field | No recovery sessions |
| `_rebind_request_lease_after_autoreconnect()` | Function (~60 lines) | Core rotation logic — gone |
| `_rotate_epoch_if_current_locked()` | Function (~40 lines) | No rotation |
| `_rotate_epoch_if_current()` | Function (~15 lines) | No rotation |
| `_collect_expired_recovery_epochs()` | Function (~20 lines) | No recovery epochs to expire |
| `_roll_expired_recovery_epochs()` | Function (~25 lines) | No rollback needed |
| `_snapshot_vip_ip_for_epoch()` | Function (~15 lines) | Only called from rollback |
| Recovery logic in `run_with_request_lease()` | Retry loop | Simplified to backoff-only |
| `RequestLease.rebinds_used` | Dataclass field | No rebinding |
| `RequestLease.max_rebinds` logic | Conditional | No rotation path |
| `vip_data_recovery_session_max_age_s` | Config field | No recovery sessions |

### Controller

| Component | Location | Why removed |
|-----------|----------|-------------|
| Recovery VIP bindings | `_iter_vip_bindings()` in `ingress.py` | No recovery VIPs to punt |
| Recovery dispatch | `handle_vip_packet_in()` in `ingress.py` | No recovery traffic to handle |
| `recovery` parameter | `_handle_vip_data()` in `ingress.py` | All traffic is normal |
| Recovery VIP MAC/IP selection | `_handle_vip_data()` | Only normal VIPs |
| TCP port scoping for recovery | `_handle_vip_data()` | Narrow rules removed |
| `recovery` parameter | `select_storage()` in `selection.py` | No recovery selection |
| `_filter_previous_normal_backend()` | `selection.py` | No recovery filtering |
| `_remember_normal_storage_choice()` | `state.py` | No normal-choice memory |
| `_forget_normal_storage_choice()` | `state.py` | No normal-choice memory |
| `_last_normal_storage_choice` | `state.py` init | No memory dict |
| `_VIP_DATA_RECOVERY_IDLE_TIMEOUT` | `config.py` | No recovery rules |
| `_VIP_DATA_RECOVERY_HARD_TIMEOUT` | `config.py` | No recovery rules |
| Recovery VIP attributes | `topology/topology.py` | No recovery IPs |
| Recovery distress helpers | `main_n1.py`, `main_n2.py` | `_RECOVERY_DISTRESS_OUTCOMES`, `_domain_summary_has_recovery_distress()` |
| Recovery distress definitions | `telemetry/models.py` | `_RECOVERY_DISTRESS_OUTCOMES` frozenset, `DomainSummary.has_recovery_distress()` |
| Recovery VIP from `select_storage()` | `vip_routing.py` facade | No recovery param; update docstring to remove recovery VIP attribute references |
| Recovery narrow-flow params | `_vip_routing/flows.py` | `tcp_src_port`/`tcp_dst_port` params only used by recovery path; docstring references recovery |
| Recovery env vars in edge-server launch | `elasticity/compute_node_manager.py` | No `VIP_DATA_RECOVERY_*` env vars passed to containers |

### What Stays

| Component | Why kept |
|-----------|----------|
| `_MongoEpoch.mode` field | Kept as `"normal"` for log backward-compatibility; can be removed in follow-up cleanup |
| `recent_failures` counter | Observability — track failure patterns without gating rotation |
| Backoff config (`mongo_retry_backoff_ms`, `mongo_retry_max_attempts`) | Core retry mechanism |
| `serverSelectionTimeoutMS=3000` | pymongo connection timeout |
| `_MongoEpoch.last_failure_at` | Diagnostic timestamp |
| `_close_drained_epochs()` and retiring epoch lifecycle | Normal VIP update path (`PUT /vip_data`) still needs epoch retirement |
| `mongo_consecutive_failure_threshold` | **Becomes dead config** after `run_with_request_lease` simplification — no code reads it. Remove from `edge_server_config.py` (see Step 1.13) |

## 3. Step-by-Step Implementation

### Phase 1 — Edge Server Recovery Removal

**Primary file**: `source/docker/edge_server/source/vip_data_mongo_runtime.py`
**Secondary file**: `source/docker/edge_server/source/edge_server_config.py`

#### Step 1.1 — Remove recovery VIP configuration

Delete the `vip_data_recovery_per_domain` dictionary:

```python
# REMOVE this entire block:
vip_data_recovery_per_domain = {
    "lan1": os.environ.get("VIP_DATA_RECOVERY_N1_IP", "10.0.0.252"),
    "lan2": os.environ.get("VIP_DATA_RECOVERY_N2_IP", "10.0.1.252"),
}
```

#### Step 1.2 — Simplify `_seed_epoch_states_from_config`

Remove recovery LAN validation and `recovery_vip_ip` assignment:

```python
# BEFORE:
def _seed_epoch_states_from_config() -> None:
    configured_lans = set(vip_data_per_domain)
    recovery_lans = set(vip_data_recovery_per_domain)
    if configured_lans != recovery_lans:
        raise StorageVipConfigurationError(...)
    seeded: dict[str, _LanEpochState] = {}
    for lan in sorted(configured_lans):
        seeded[lan] = _LanEpochState(
            normal_vip_ip=vip_data_per_domain[lan],
            recovery_vip_ip=vip_data_recovery_per_domain[lan],  # REMOVE
        )
    ...

# AFTER:
def _seed_epoch_states_from_config() -> None:
    configured_lans = set(vip_data_per_domain)
    seeded: dict[str, _LanEpochState] = {}
    for lan in sorted(configured_lans):
        seeded[lan] = _LanEpochState(
            normal_vip_ip=vip_data_per_domain[lan],
        )
    with _epoch_states_registry_lock:
        _epoch_states.clear()
        _epoch_states.update(seeded)
```

#### Step 1.3 — Simplify `_LanEpochState`

```python
# BEFORE:
@dataclass
class _LanEpochState:
    lifecycle_lock: threading.Lock = field(default_factory=threading.Lock)
    normal_vip_ip: str | None = None
    recovery_vip_ip: str | None = None     # REMOVE
    current: _MongoEpoch | None = None
    retiring: list[_MongoEpoch] = field(default_factory=list)
    next_epoch_id: int = 1

# AFTER:
@dataclass
class _LanEpochState:
    lifecycle_lock: threading.Lock = field(default_factory=threading.Lock)
    normal_vip_ip: str | None = None
    current: _MongoEpoch | None = None
    retiring: list[_MongoEpoch] = field(default_factory=list)
    next_epoch_id: int = 1
```

#### Step 1.4 — Simplify `_MongoEpoch`

```python
# BEFORE:
@dataclass
class _MongoEpoch:
    epoch_id: int
    mode: str
    vip_ip: str
    client: MongoClient | None = None
    client_created_at: float | None = None
    first_lease_at: float | None = None
    lease_count: int = 0
    retiring: bool = False
    retire_requested_at: float | None = None
    drain_deadline: float | None = None
    recovery_expires_at: float | None = None    # REMOVE
    last_failure_at: float = 0.0
    recent_failures: int = 0

# AFTER:
@dataclass
class _MongoEpoch:
    epoch_id: int
    mode: str                    # Always "normal" — kept for log compat
    vip_ip: str
    client: MongoClient | None = None
    client_created_at: float | None = None
    first_lease_at: float | None = None
    lease_count: int = 0
    retiring: bool = False
    retire_requested_at: float | None = None
    drain_deadline: float | None = None
    last_failure_at: float = 0.0
    recent_failures: int = 0     # Observability — no longer gates rotation
```

#### Step 1.5 — Remove recovery from `_get_or_create_epoch_client`

```python
# BEFORE (lines ~208-211):
if epoch.mode == "recovery" and epoch.recovery_expires_at is None:
    epoch.recovery_expires_at = (
        epoch.client_created_at + VIP_DATA_RECOVERY_SESSION_MAX_AGE_S
    )

# AFTER:
# This block is removed. Epochs are always "normal" mode.
# The client is created with the normal VIP only.
```

#### Step 1.6 — Remove `_rebind_request_lease_after_autoreconnect`

Delete the entire function (~60 lines, currently lines 281-340). This was
the core of the epoch rotation mechanism — it checked if the failed epoch was
normal, rotated to recovery, adopted the new epoch, and handled recovery
failure with accelerated expiry. None of this is needed.

#### Step 1.7 — Simplify `run_with_request_lease`

Replace the current retry loop (which has rotation branches) with a simple
backoff-only loop:

```python
def run_with_request_lease(
    lan: str,
    *,
    op_name: str,
    replay_safe: bool,
    fn: Callable[[Any], T],
) -> T:
    registry = _get_request_lease_registry()
    lease = registry.get(lan)
    if lease is not None and lease.lifecycle == RequestLeaseLifecycle.FAILED:
        raise PyMongoError(f"request lease already failed for {lan}")
    if lease is not None and lease.lifecycle == RequestLeaseLifecycle.COMPLETED:
        raise PyMongoError(f"request lease already completed for {lan}")

    lease = lease or _get_or_bind_request_lease(lan)
    lease.replay_safe = lease.replay_safe and replay_safe

    attempts = 0
    while True:
        attempts += 1
        try:
            return _run_db_op_once(lan, lease, op_name, fn)
        except AutoReconnect:
            # _run_db_op_once already incremented lease.epoch.recent_failures
            if attempts <= CONFIG.mongo_retry_max_attempts:
                backoff_ms = CONFIG.mongo_retry_backoff_ms * (2 ** (attempts - 1))
                time.sleep(backoff_ms / 1000.0)
                continue

            # Exhausted all retry attempts
            lease.lifecycle = RequestLeaseLifecycle.FAILED
            lease.terminal_reason = f"{op_name}:retries_exhausted"
            raise
```

Key changes from current code:
- No `rotate_now` check — rotation removed entirely
- No `_rebind_request_lease_after_autoreconnect` call
- No `max_rebinds` logic
- Backoff progression: 100ms → 200ms → 400ms (unchanged)
- After 3 backoff attempts → propagate failure as 503 (unchanged behavior
  for exhausted retries)

#### Step 1.8 — Remove recovery rotation functions

Delete these functions entirely:
- `_rotate_epoch_if_current_locked()` (~40 lines)
- `_rotate_epoch_if_current()` (~15 lines)
- `_collect_expired_recovery_epochs()` (~20 lines)
- `_roll_expired_recovery_epochs()` (~25 lines)
- `_snapshot_vip_ip_for_epoch()` (~15 lines)

The `_rotate_current_epoch_locked()` function is KEPT — it's used by
`PUT /vip_data` for normal VIP updates (changing the VIP address when the
controller reassigns it). This is a legitimate use of epoch rotation that
does not involve recovery.

#### Step 1.9 — Remove housekeeping recovery rollback

In `_epoch_housekeeping_loop()`, remove the recovery rollback call:

```python
# BEFORE:
def _epoch_housekeeping_loop() -> None:
    sweep_interval = max(1.0, min(MONGO_CLIENT_RETIRE_GRACE_S / 2.0, 5.0))
    while True:
        time.sleep(sweep_interval)
        try:
            _roll_expired_recovery_epochs()    # REMOVE
            _close_drained_epochs()
        except Exception:
            log.exception("epoch housekeeping sweep failed")

# AFTER:
def _epoch_housekeeping_loop() -> None:
    sweep_interval = max(1.0, min(MONGO_CLIENT_RETIRE_GRACE_S / 2.0, 5.0))
    while True:
        time.sleep(sweep_interval)
        try:
            _close_drained_epochs()
        except Exception:
            log.exception("epoch housekeeping sweep failed")
```

#### Step 1.10 — Simplify `RequestLease`

```python
# BEFORE:
@dataclass
class RequestLease:
    lan: str
    epoch: _MongoEpoch
    first_bound_at: float
    lifecycle: RequestLeaseLifecycle = RequestLeaseLifecycle.ACTIVE
    replay_safe: bool = True
    rebinds_used: int = 0               # REMOVE
    terminal_reason: str | None = None

# AFTER:
@dataclass
class RequestLease:
    lan: str
    epoch: _MongoEpoch
    first_bound_at: float
    lifecycle: RequestLeaseLifecycle = RequestLeaseLifecycle.ACTIVE
    replay_safe: bool = True
    terminal_reason: str | None = None
```

#### Step 1.11 — Update `_project_request_lease_outcome`

```python
# BEFORE (lines ~690-710):
def _project_request_lease_outcome(lease: RequestLease) -> dict[str, Any]:
    ...
    if projected_lifecycle == RequestLeaseLifecycle.FAILED:
        outcome = "failure_terminal"
    elif lease.rebinds_used > 0:          # REMOVE this branch
        outcome = "success_after_rebind"
    else:
        outcome = "success_normal"
    return {
        ...
        "rebinds_used": lease.rebinds_used,  # REMOVE
        ...
    }

# AFTER:
def _project_request_lease_outcome(lease: RequestLease) -> dict[str, Any]:
    projected_lifecycle = (
        RequestLeaseLifecycle.FAILED
        if lease.lifecycle == RequestLeaseLifecycle.FAILED
        else RequestLeaseLifecycle.COMPLETED
    )
    if projected_lifecycle == RequestLeaseLifecycle.FAILED:
        outcome = "failure_terminal"
    else:
        outcome = "success_normal"
    return {
        "lan": lease.lan,
        "epoch_id": lease.epoch.epoch_id,
        "epoch_mode": lease.epoch.mode,
        "lifecycle": projected_lifecycle.name,
        "outcome": outcome,
        "replay_safe": lease.replay_safe,
        "terminal_reason": lease.terminal_reason,
    }
```

#### Step 1.12 — Update log message format

Update `log_request_lease_outcome` to remove `rebinds_used` from the format
string. Update `log_db_failure` if it references `_rebind_request_lease_after_autoreconnect`.

#### Step 1.13 — Remove config from edge_server_config.py

```python
# REMOVE from dataclass fields:
vip_data_recovery_session_max_age_s: float
mongo_consecutive_failure_threshold: int

# REMOVE from from_env():
vip_data_recovery_session_max_age_s=float(
    os.environ.get("VIP_DATA_RECOVERY_SESSION_MAX_AGE_S", "35")
),
mongo_consecutive_failure_threshold=int(
    os.environ.get("MONGO_CONSECUTIVE_FAILURE_THRESHOLD", "5")
),
```

`mongo_consecutive_failure_threshold` was only used by the recovery rotation
branch in `run_with_request_lease` (the `rotate_now = epoch.recent_failures >= threshold`
check). After Step 1.7 simplifies the retry loop to backoff-only, this config
is dead — nothing reads it.

Also remove the module-level constant in `vip_data_mongo_runtime.py`:

```python
# REMOVE:
VIP_DATA_RECOVERY_SESSION_MAX_AGE_S = CONFIG.vip_data_recovery_session_max_age_s
```

### Phase 2 — Controller-Side Recovery Cleanup

The controller-side recovery removal is covered in detail in the
[conntrack_vip_routing plan](../conntrack_vip_routing/conntrack_vip_routing_plan.md)
Phase 3 (§3.1-§3.6). This section summarizes the changes for completeness.

#### Summary of controller changes

| File | Change |
|------|--------|
| `_vip_routing/ingress.py` | Remove 2 recovery bindings from `_iter_vip_bindings()`, remove recovery dispatch from `handle_vip_packet_in()`, remove `recovery` parameter and narrow-flow logic from `_handle_vip_data()` |
| `_vip_routing/selection.py` | Remove `recovery` param from `select_storage()`, remove `_filter_previous_normal_backend()` |
| `_vip_routing/state.py` | Remove `_remember_normal_storage_choice()`, `_forget_normal_storage_choice()`, `_last_normal_storage_choice` |
| `_vip_routing/config.py` | Remove `_VIP_DATA_RECOVERY_IDLE_TIMEOUT`, `_VIP_DATA_RECOVERY_HARD_TIMEOUT` |
| `vip_routing.py` | Remove `recovery` param from `select_storage()` facade, update docstring |
| `topology/topology.py` | Remove `vip_data_recovery_n*_ip/mac` attribute initialization (lines 34-37) |
| `main_n1.py`, `main_n2.py` | Remove `_RECOVERY_DISTRESS_OUTCOMES` and `_domain_summary_has_recovery_distress()` |
| `telemetry/models.py` | Remove `_RECOVERY_DISTRESS_OUTCOMES` frozenset and `DomainSummary.has_recovery_distress()` method |
| `_vip_routing/flows.py` | Remove `tcp_src_port`/`tcp_dst_port` parameters from `install_vip_dnat_snat()` (only used by recovery narrow-flow); update docstring to remove recovery reference |
| `vip_routing.py` (mixin docstring) | Remove `vip_data_recovery_n*_ip/mac` from the "Depends on TopologyMixin attributes" list in the class docstring |
| `elasticity/compute_node_manager.py` | Remove 3 `VIP_DATA_RECOVERY_*` env vars from `_docker_run_server` |

#### Step 2.1 — Remove TCP port scoping from `_handle_vip_data()` in `ingress.py`

The TCP port extraction block (currently lines ~197-207) only executes when
`recovery=True`. It extracts `tcp_src_port`/`tcp_dst_port` to narrow flow
rules to a single TCP connection. After removing the `recovery` parameter,
this entire block and the two local variables are dead code:

```python
# REMOVE this entire block:
tcp_src_port = None
tcp_dst_port = None
if recovery:
    tcp_pkt = pkt.get_protocol(tcp_lib.tcp)
    if ip_proto != 6 or tcp_pkt is None or tcp_pkt.dst_port != 27018:
        logger.warning(
            "vip_data(%s) recovery: non-Mongo recovery packet dropped proto=%s dst_port=%s",
            domain,
            ip_proto,
            getattr(tcp_pkt, "dst_port", None),
        )
        return True
    tcp_src_port = tcp_pkt.src_port
    tcp_dst_port = tcp_pkt.dst_port
```

After removal, the call to `flows.install_vip_dnat_snat()` no longer passes
`tcp_src_port`/`tcp_dst_port` or recovery-specific `idle_timeout`/`hard_timeout`.

#### Step 2.2 — Remove recovery narrow-flow params from `flows.py`

Remove the `tcp_src_port` and `tcp_dst_port` parameters from
`install_vip_dnat_snat()` — they were only ever passed by the recovery path
in `_handle_vip_data()`. Also remove the `has_tcp_ports` conditional and
the `tcp_src`/`tcp_dst` match fields. Update the docstring to remove the
paragraph about recovery narrow-flow rules.

#### Step 2.3 — Remove recovery distress from `telemetry/models.py`

Remove:
- `_RECOVERY_DISTRESS_OUTCOMES` module-level frozenset (lines 15-20)
- `DomainSummary.has_recovery_distress()` method (lines 111-113)

The `request_lease_outcomes_per_lan` field on `DomainSummary` is **kept** —
it still carries `success_normal` and `failure_terminal` outcomes which
remain meaningful for observability after recovery removal.

### Phase 3 — Documentation

#### Step 3.1 — Update `vip_routing_backend_selection_and_warm_leases.md`

- §6 (Storage Selection): Remove `recovery` parameter from `select_storage()` signature description, remove recovery filtering from selection order
- §9 ("Recovery Avoidance via Last Normal Choice"): Remove entire section — `_filter_previous_normal_backend()`, `_remember_normal_storage_choice()`, `_forget_normal_storage_choice()`, and `_last_normal_storage_choice` no longer exist
- §11 (Flow Timeouts table): Remove `VIP_DATA_RECOVERY_IDLE_TIMEOUT` and `VIP_DATA_RECOVERY_HARD_TIMEOUT` rows

#### Step 3.2 — Update `vip_data_edge_epoch_and_recovery.md`

Add a deprecation notice at the top:

> **2026-06-07**: The VIP recovery mechanism (epoch rotation to recovery VIP)
> has been removed. Stale flow rule elimination is now handled by the
> controller via [OVS conntrack-based flow rules](../conntrack_vip_routing/conntrack_vip_routing_plan.md)
> and proactive rule deletion on backend unregister. The edge server no
> longer rotates epochs — it retries on the normal VIP with exponential
> backoff.

Update sections:
- §3 (Epoch fields table): Remove `recovery_expires_at`, add `recent_failures`
- §4 (`run_with_request_lease` description): Replace recovery rotation
  description with backoff-only description
- §5 "AutoReconnect — Recovery Rotation": Replace with "AutoReconnect — Backoff Retry"
- §5a (Retry Architecture): Update to note rotation is removed
- §7 "Recovery Rollback": Remove or mark as deleted
- §8 (Controller interaction): Remove recovery VIP touch point #2

#### Step 3.3 — Update `vip_routing_interception_and_flow_rules.md`

- §4 (VIP Address Binding Set): Remove recovery bindings from table
- §9 (Recovery narrow-flow): Mark as removed, add cross-reference

#### Step 3.4 — Update `vip_routing_overview.md`

Remove references to `VIP_DATA_RECOVERY_*` addresses and recovery flow.

## 4. File Map

| File | Action | Phase |
|------|--------|-------|
| `source/docker/edge_server/source/vip_data_mongo_runtime.py` | **Major surgery** — remove recovery (~200 lines deleted), simplify retry loop | 1 |
| `source/docker/edge_server/source/edge_server_config.py` | **Modify** — remove `vip_data_recovery_session_max_age_s` | 1 |
| `source/sdn_controller/_vip_routing/ingress.py` | **Modify** — remove recovery bindings/dispatch/handler | 2 |
| `source/sdn_controller/_vip_routing/selection.py` | **Modify** — remove recovery param and filter | 2 |
| `source/sdn_controller/_vip_routing/state.py` | **Modify** — remove recovery memory helpers | 2 |
| `source/sdn_controller/_vip_routing/config.py` | **Modify** — remove recovery timeouts | 2 |
| `source/sdn_controller/_vip_routing/flows.py` | **Modify** — remove `tcp_src_port`/`tcp_dst_port` params, update docstring | 2 |
| `source/sdn_controller/vip_routing.py` | **Modify** — remove recovery from facade and docstring | 2 |
| `source/sdn_controller/topology/topology.py` | **Modify** — remove recovery VIP attribute initialization (lines 34-37) | 2 |
| `source/sdn_controller/main_n1.py` | **Modify** — remove `_RECOVERY_DISTRESS_OUTCOMES` and `_domain_summary_has_recovery_distress()` | 2 |
| `source/sdn_controller/main_n2.py` | **Modify** — remove `_RECOVERY_DISTRESS_OUTCOMES` and `_domain_summary_has_recovery_distress()` | 2 |
| `source/sdn_controller/telemetry/models.py` | **Modify** — remove `_RECOVERY_DISTRESS_OUTCOMES` frozenset and `DomainSummary.has_recovery_distress()` | 2 |
| `source/sdn_controller/elasticity/compute_node_manager.py` | **Modify** — remove 3 `VIP_DATA_RECOVERY_*` env vars from `_docker_run_server` | 2 |
| `docs/operation/vip_routing/vip_routing_backend_selection_and_warm_leases.md` | **Update** — remove §9 Recovery Avoidance, remove recovery param from §6, remove recovery timeouts from §11 | 3 |
| `docs/operation/vip_routing/vip_data_edge_epoch_and_recovery.md` | **Update** — document recovery removal | 3 |
| `docs/operation/vip_routing/vip_routing_interception_and_flow_rules.md` | **Update** — remove recovery § | 3 |
| `docs/operation/vip_routing/vip_routing_overview.md` | **Update** — remove recovery references | 3 |

## 5. Edge Server Retry Behavior After Removal

With recovery removed, the retry path is:

```
Request → _run_db_op_once → AutoReconnect
  → attempts=1: sleep 100ms → retry on same normal VIP
  → attempts=2: sleep 200ms → retry on same normal VIP
  → attempts=3: sleep 400ms → retry on same normal VIP
  → attempts=4: mark FAILED → propagate 503

Total retry window: ~700ms of backoff + ~3s serverSelectionTimeoutMS
  = ~3.7s before terminal failure.

During this window:
  - If the normal VIP's flow rule was deleted (by conntrack plan Phase 2),
    the next SYN triggers a fresh select_storage() → new rule installed
    → request succeeds within one retry cycle (~100ms).
  - If the flow rule still exists but points to a dead backend, pymongo
    times out after serverSelectionTimeoutMS (3s) → next retry.
    After 10s idle, the stale rule expires → fresh selection.
  - If the flow rule is healthy, pymongo's retryReads=True reconnects
    transparently within the 3s timeout.
```

## 6. Dependencies & Deployment Order

1. **Must deploy together with** [conntrack_vip_routing](../conntrack_vip_routing/conntrack_vip_routing_plan.md).
   Deploying recovery removal without conntrack would leave the edge server
   with no recovery path and the controller with stale flow rules — causing
   30-120s failure windows with no workaround.
2. Edge server changes require Docker image rebuild.
3. Controller changes are Python-only — file sync + restart.
4. No new environment variables. Several env vars become unused:
   - `VIP_DATA_RECOVERY_N1_IP` / `VIP_DATA_RECOVERY_N2_IP` — no longer read by any component
   - `VIP_DATA_RECOVERY_N1_MAC` / `VIP_DATA_RECOVERY_N2_MAC` — no longer read
   - `VIP_DATA_RECOVERY_SESSION_MAX_AGE_S` — no longer read
   - `VIP_DATA_RECOVERY_IDLE_TIMEOUT` / `VIP_DATA_RECOVERY_HARD_TIMEOUT` — no longer read
   These can be removed from env files in a follow-up cleanup.
5. `compute_node_manager.py` line 218-220: the `_docker_run_server` method must stop passing
   `VIP_DATA_RECOVERY_N1_IP`, `VIP_DATA_RECOVERY_N2_IP`, and
   `VIP_DATA_RECOVERY_SESSION_MAX_AGE_S` as `-e` flags to new edge server containers.

## 7. Rollback Plan

If recovery removal causes issues:
1. Revert `vip_data_mongo_runtime.py` to pre-removal state
2. Revert `edge_server_config.py` to include `vip_data_recovery_session_max_age_s`
3. Rebuild edge server Docker image
4. Restore controller-side recovery (revert ingress.py, selection.py,
   state.py, config.py, vip_routing.py, topology/topology.py, main_n*.py,
   compute_node_manager.py)
5. Restart controllers

The recovery removal is independent of conntrack — either can be rolled
back without affecting the other. However, note that WITHOUT conntrack
(rolled back) and WITH recovery (rolled back), the system returns to the
v5.5 B state (6.7% overall failure).

## 8. Testing & Validation

- [ ] Edge server starts without `StorageVipConfigurationError` (no longer
  validates recovery LAN set)
- [ ] `_seed_epoch_states_from_config()` creates states without
  `recovery_vip_ip`
- [ ] `_get_or_create_epoch_client` creates clients only in normal mode
- [ ] No "Rotated epoch" log lines with `mode=recovery`
- [ ] No "Created MongoClient ... mode=recovery" log lines
- [ ] No "recovery_expired" log lines from housekeeping
- [ ] `run_with_request_lease` retries on same epoch without rotation
- [ ] After 3 backoff attempts, returns 503 with
  `terminal_reason="...:retries_exhausted"`
- [ ] `outcome=success_after_rebind` no longer appears in lease outcome logs
- [ ] Controller logs show no recovery VIP references
- [ ] Full `current_state_long_cycle` experiment with conntrack: overall ≤3%
