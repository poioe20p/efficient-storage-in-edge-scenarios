# Phase 2 - Storage Persistent Reserve Preparation and Readiness

## Status

Implemented.

## Primary Outcome

Prepare one same-LAN storage reserve per LAN through the current storage add
path and hold it outside `VIP_DATA` once it becomes ready.

## Scope

1. Add a dedicated reserve-preparation alert to Thread 3.
2. Prepare one reserve per LAN when the feature is enabled and the LAN does not
   already have a reserve.
3. Reuse the current storage add lifecycle instead of inventing a new reserve-
   only bootstrap path.
4. Enable heartbeat for the reserve while it remains reserved.
5. Keep the reserve out of VIP admission after `SECONDARY` readiness.
6. Keep reserve preparation singleton per LAN.

## Design Rules

1. Reserve creation must reuse `StorageNodeAdder.add_storage_node(...)`.
2. Reserve identity must be tracked in controller state, not by a fixed name
   such as `dyn0`.
3. While the reserve is `PREPARING`, later prepare requests for the same LAN
   are suppressed.
4. A ready reserve must heartbeat so the controller can distinguish ready
   reserve from missing reserve.

## Step-By-Step Plan

1. Add `PrepareStandbyStorageAlert` in
   `source/sdn_controller/elasticity/elasticity.py`.
2. Add a one-shot Thread 2 helper in `main_n1.py` and `main_n2.py` that
   submits reserve preparation when:
   1. the feature is enabled
   2. the reserve slot is `NONE`
   3. the local primary is visible and healthy enough to admit a new member
3. Extend `StorageNodeAdder.add_storage_node(...)` in
   `source/sdn_controller/elasticity/storage_node_manager.py` with a
   `heartbeat_enabled` override.
4. When Thread 3 records reserve creation success, publish the resulting
   `NodeInfo` with `standby_reserved=True`.
5. Update `ControlEventDispatcher.process_secondary_events(...)` so
   `rs_secondary_ready` marks a reserved node as `READY_RESERVED` and skips VIP
   admission.
6. Apply the same reserved-node gate to the telemetry fallback promotion path.

## Exact Edit Targets

Implement only these responsibilities in this phase.

1. In `source/sdn_controller/elasticity/elasticity.py`, add
   `PrepareStandbyStorageAlert` and the Thread 3 dispatch path that creates a
   reserve through the existing storage add path.
2. In `source/sdn_controller/elasticity/storage_node_manager.py`, add the
   `heartbeat_enabled` parameter and pass the corresponding environment setting
   into the storage container launch path.
3. In `source/sdn_controller/main_n1.py` and `source/sdn_controller/main_n2.py`,
   add only the helper that submits reserve preparation when the slot is
   `NONE` and the primary is available.
4. In `source/sdn_controller/control_events.py`, change ready handling so a
   reserved node becomes `READY_RESERVED` instead of entering VIP.
5. Keep the same-LAN load trigger path unchanged in this phase. The reserve may
   become ready, but it is not yet consumed by `DataAlert`.

## Do Not Do In This Phase

1. Do not make `DataAlert` consume the reserve yet.
2. Do not add reserve replenishment yet.
3. Do not add recovery-distress activation yet.
4. Do not add scale-down reserve-floor enforcement yet.
5. Do not use a fixed reserve name such as `dyn0`.

## Code Sketches

### Thread 3 Alert

```python
@dataclass(frozen=True)
class PrepareStandbyStorageAlert:
    lan: int
    network_id: str
    rs_name: str
    primary_container: str
    port: int = 27018
```

### Thread 2 Preparation Hook

```python
def _maybe_prepare_storage_reserve(self, summary: TelemetrySummary, lan: int) -> None:
    if not _STORAGE_PERSISTENT_RESERVE_ENABLED:
        return
    if not self._node_registry.should_prepare_storage_reserve(lan):
        return
    if not any(ss.member_state == "PRIMARY" for ss in summary.storage_servers.values()):
        return

    self._elasticity.submit(
        PrepareStandbyStorageAlert(
            lan=lan,
            network_id=summary.network_id,
            rs_name=f"rs_net{lan}",
            primary_container=f"edge_storage_server_n{lan}",
        )
    )
    self._node_registry.mark_storage_reserve_prepare_submitted(lan)
```

### Heartbeat Override

```python
def add_storage_node(
    self,
    lan: int,
    name: str,
    rs_name: str,
    port: int = 27018,
    ip: str | None = None,
    mac: str | None = None,
    heartbeat_enabled: bool = False,
) -> NodeResult:
    ...
```

## Readiness Semantics

When a reserve reaches `SECONDARY`:

1. Thread 2 marks the slot `READY_RESERVED`.
2. The reserve stays outside `VIP_DATA`.
3. The reserve remains excluded from ordinary dynamic storage counts.
4. The reserve becomes immediately activatable by later phases.

## Verification Targets

1. Exactly one reserve preparation may be in flight per LAN.
2. The ready reserve is visible in controller state and heartbeats normally.
3. The ready reserve is not added to the VIP pool.
4. Dynamic threshold accounting still behaves as if the reserve does not count
   as active service capacity.
5. A standby prepare that returns without a usable MAC is treated as a hard
   failure: the container is cleaned up immediately, the allocator IP is
   released, and Thread 2 receives a `ReservePrepareFailed` outcome so the
   slot can return to `NONE` for next-cycle retry.

## Phase 2 Is Complete When

1. One reserve preparation can be submitted per LAN.
2. The prepared reserve can reach `READY_RESERVED` through the normal
   `rs_secondary_ready` path.
3. The ready reserve is still outside VIP.
4. A second reserve is not prepared while the first is still `PREPARING`.
