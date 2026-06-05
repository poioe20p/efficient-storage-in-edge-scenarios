# Phase 1 - Storage Persistent Reserve State and Accounting

## Status

Implemented.

## Primary Outcome

Add a controller-side reserve slot model that treats reserved storage as a
distinct state rather than as ordinary active dynamic capacity.

## Scope

1. Add the persistent reserve feature flag and any reserve-specific config
   constants.
2. Extend controller-side node metadata so a storage node can be marked as
   reserved.
3. Add one reserve slot per LAN, owned by Thread 2.
4. Exclude reserved storage from ordinary dynamic storage accounting.
5. Prepare the registry helpers needed by later phases for reserve creation,
   readiness, activation, and loss handling.
6. Keep the live load and recovery trigger path unchanged in this phase.

## Why This Phase Must Exist First

The current storage elasticity path assumes every tracked dynamic storage node
is one of two things:

1. active capacity that should count toward scale-up threshold progression
2. removable capacity that can be selected by ordinary storage scale-down

That assumption is wrong for a persistent reserve.

Without new state, a reserved node would:

1. raise the adaptive storage threshold even before it served traffic
2. become the default LIFO scale-down candidate
3. be routed through ordinary scale-down alerts when it should instead be
   interpreted as reserve loss

## Reserve Slot Model

Thread 2 should own one reserve slot per LAN.

| State | Meaning | Counts as active dynamic storage | Eligible for ordinary scale-down | Eligible for VIP admission |
| --- | --- | --- | --- | --- |
| `NONE` | No reserve exists yet | No | No | No |
| `PREPARING` | Reserve creation is already in flight | No | No | No |
| `READY_RESERVED` | Reserve is ready and heartbeat-visible but still reserved | No | No | No |

The reserve slot should not attempt to remember already activated reserve
nodes. Once activated, that node becomes ordinary active dynamic storage again.

## Step-By-Step Plan

1. Add `STORAGE_PERSISTENT_RESERVE_ENABLED` in
   `source/sdn_controller/scaling_config.py`.
2. Extend `NodeInfo` in `source/sdn_controller/elasticity/node_common.py`
   with `standby_reserved: bool = False`.
3. Add a `StorageReserveSlot` data structure in
   `source/sdn_controller/node_registry.py`.
4. Create reserve-slot helpers such as:
   1. `get_storage_reserve_slot(lan)`
   2. `should_prepare_storage_reserve(lan)`
   3. `mark_storage_reserve_prepare_submitted(lan)`
   4. `mark_storage_reserve_ready(mac)`
   5. `latch_storage_reserve_activation(lan, reason)`
   6. `consume_ready_storage_reserve(lan)`
   7. `mark_storage_reserve_lost(mac)`
5. Change `count_dynamic("storage")` so it ignores `NodeInfo` entries whose
   `standby_reserved` flag is still true.
6. Change `find_last_dynamic("storage")` so it skips reserved nodes.
7. Change `build_scale_down_alert(...)` so reserved nodes do not produce
   ordinary `ScaleDownDataAlert` objects.
8. Keep reserve-loss handling separate from ordinary absence-driven removal.

## Exact Edit Targets

Implement only these responsibilities in this phase.

1. In `source/sdn_controller/scaling_config.py`, add the feature flag only.
2. In `source/sdn_controller/elasticity/node_common.py`, add only the
   `standby_reserved` metadata bit to `NodeInfo`.
3. In `source/sdn_controller/node_registry.py`, add the reserve slot data
   structure and the helper methods that only manipulate reserve state.
4. In `source/sdn_controller/node_registry.py`, update `count_dynamic`,
   `find_last_dynamic`, and `build_scale_down_alert` so reserved nodes are
   invisible to ordinary active-storage accounting.
5. Do not modify `main_n1.py`, `main_n2.py`, `control_events.py`, or Thread 3
   behavior yet beyond compile-time scaffolding required by new types.

## Do Not Do In This Phase

1. Do not submit reserve-preparation alerts yet.
2. Do not change VIP admission behavior yet.
3. Do not add recovery-distress telemetry yet.
4. Do not change storage scale-up trigger behavior yet.
5. Do not add final reserve log grammar yet.

## Code Sketches

### Config

```python
_STORAGE_PERSISTENT_RESERVE_ENABLED = int(
    os.environ.get("STORAGE_PERSISTENT_RESERVE_ENABLED", "0")
)
```

### Node Metadata

```python
@dataclass
class NodeInfo:
    mac: str
    lan: int
    network_id: str
    name: str
    ip: str
    node_type: str
    rs_name: str = ""
    primary_container: str = ""
    port: int = 27018
    owner_lan: str = ""
    spawn_started_monotonic_s: float = 0.0
    ready_logged: bool = False
    standby_reserved: bool = False
```

### Reserve Slot

```python
@dataclass
class StorageReserveSlot:
    lan: int
    state: str = "NONE"
    mac: str = ""
    ip: str = ""
    name: str = ""
    activation_pending: bool = False
    pending_reason: str = ""
```

## Verification Targets

1. A reserved storage node does not change `count_dynamic("storage")`.
2. A reserved storage node does not become the ordinary LIFO scale-down
   candidate.
3. Reserve loss is visible as reserve loss, not as ordinary storage drain or
   ordinary absent-node removal.
4. No live scale-up or recovery behavior changes yet in this phase.

## Phase 1 Is Complete When

1. A `NodeInfo` marked `standby_reserved=True` can be tracked safely.
2. The reserve slot can represent `NONE`, `PREPARING`, and `READY_RESERVED`.
3. Storage threshold counts ignore reserved nodes.
4. Ordinary storage scale-down selection ignores reserved nodes.
5. No actual reserve creation, activation, or recovery-trigger behavior exists
   yet.
