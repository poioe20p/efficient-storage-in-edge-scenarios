# Phase 4 - Storage Persistent Reserve Recovery, Floor, and Visibility

## Status

Implemented.

## Primary Outcome

Make recovery distress a first-class reserve activation trigger, enforce the
reserve floor during storage scale-down, and document how the persistent
reserve lifecycle should be interpreted in experiment artifacts.

## Scope

1. Preserve edge-side recovery distress signals through the aggregator and into
   controller telemetry.
2. Activate or wait on the reserve when recovery distress is observed.
3. Mark the LAN degraded while a required reserve is missing or still
   preparing.
4. Block ordinary storage scale-down whenever it would violate the active-plus-
   reserve floor.
5. Add stable log markers and artifact interpretation rules for reserve
   lifecycle events.

## Recovery Trigger Path

The edge server already has the raw signal needed for a recovery trigger.
The missing work is preserving it through controller telemetry.

Phase 4 should carry request-lease outcome data through:

1. `source/docker/local_state_server/aggregator.py`
2. `source/sdn_controller/telemetry/models.py`
3. `main_n1.py` and `main_n2.py`

The controller should then treat any of the following as recovery distress for
the affected LAN:

1. one or more recovery rebind outcomes
2. one or more terminal recovery failures
3. one or more circuit-open outcomes

## Step-By-Step Plan

1. Extend the aggregator summary with request-lease outcome counts per LAN.
2. Extend `DomainSummary` with those counts and a helper such as
   `has_recovery_distress(lan)`.
3. In `main_n1.py` and `main_n2.py`, evaluate recovery distress alongside the
   ordinary scale-up path.
4. Route recovery distress through the same reserve-trigger helper used for
   load alerts.
5. If the reserve is `PREPARING`, keep the controller in degraded wait mode and
   do not submit a second reserve preparation.
6. Add a scale-down guard that refuses to remove an ordinary active dynamic
   storage node unless the LAN will still retain one ready reserve after the
   removal.
7. Add stable reserve lifecycle log markers and testing guidance.

## Exact Edit Targets

Implement only these responsibilities in this phase.

1. In `source/docker/local_state_server/aggregator.py`, preserve the raw
   request-lease outcome counters into the controller-facing summary.
2. In `source/sdn_controller/telemetry/models.py`, add the recovery-distress
   summary field and the helper that interprets it.
3. In `source/sdn_controller/main_n1.py` and `source/sdn_controller/main_n2.py`,
   call the same reserve-trigger helper with `reason="recovery"` when the
   summarized distress signal is present.
4. In `source/sdn_controller/node_registry.py` or the mediator layer, add the
   guard that blocks ordinary storage scale-down unless the LAN still retains a
   ready reserve after removal.
5. In the documentation files listed below, add the operational explanation of
   reserve preparation versus reserve activation.

## Do Not Do In This Phase

1. Do not invent a second recovery-only activation path.
2. Do not bypass the existing reserve-trigger helper for recovery.
3. Do not let a `PREPARING` reserve cause duplicate reserve creation under
   repeated recovery distress.
4. Do not count a `PREPARING` reserve as satisfying the reserve floor for
   ordinary storage scale-down.

## Code Sketches

### Domain Summary Helper

```python
@dataclass
class DomainSummary:
    ...
    request_lease_outcomes_per_lan: dict[str, dict[str, int]] = field(default_factory=dict)

    def has_recovery_distress(self, lan: str) -> bool:
        outcomes = self.request_lease_outcomes_per_lan.get(lan, {})
        return (
            outcomes.get("recovery_rebind", 0) > 0
            or outcomes.get("terminal_recovery_failure", 0) > 0
            or outcomes.get("circuit_open", 0) > 0
        )
```

### Reserve Floor Guard

```python
def can_scale_down_storage(self, candidate_mac: str, lan: int) -> bool:
    slot = self.get_storage_reserve_slot(lan)
    if slot.state != "READY_RESERVED":
        return False
    info = self.get_node_info(candidate_mac)
    return info is not None and not info.standby_reserved
```

### Stable Log Grammar

```text
[reserve] prepare_submitted lan=%d
[reserve] preparing lan=%d name=%s ip=%s mac=%s
[reserve] ready_reserved lan=%d name=%s ip=%s mac=%s
[reserve] activated lan=%d name=%s ip=%s mac=%s reason=%s
[reserve] waiting_ready lan=%d reason=%s
[reserve] lost lan=%d mac=%s
[reserve] replenish_submitted lan=%d
```

## Artifact Interpretation Rules

1. Reserve creation is not the same thing as user-visible same-LAN storage
   scale-up. The user-visible event is reserve activation.
2. While the reserve is `PREPARING`, repeated alerts should be interpreted as
   waiting pressure, not as duplicate missing scale-up attempts.
3. Reserve loss and reserve replenishment should be identifiable directly from
   controller logs.

## Reserve-Loss Handling Contract

When a reserved node is detected absent by `detect_absent(...)`:

1. **Clear the reserve slot first** via `mark_storage_reserve_lost(mac)`.
   This must happen while the node is still in the registry so the slot can
   be located and cleared. Pending activation fields are preserved for
   bounded carry-forward to the replacement reserve.
2. **Then unregister** the node from registry tracking via
   `unregister_reserved_node(mac)`.
3. **Then submit cleanup** via `CleanupReserveAlert`. The cleanup handler
   uses **best-effort RS eviction**:
   - If `ip`, `rs_name`, and `primary_container` are all present, call
     `remove_storage_node(..., best_effort_rs_remove=True)`.  This attempts
     `rs.remove()` via the primary but **always** proceeds to container
     and network teardown even when primary lookup fails, `rs.remove()`
     returns non-``ok:1``, or RS-wait confirmation times out.
   - If metadata is incomplete (the reserve never reached the RS-add
     stage), use container-only teardown via `_cleanup_container(...)`.
4. Do **not** retry preparation from the loss handler. Next-cycle maintenance
   will see the `NONE` slot and submit a new `PrepareStandbyStorageAlert`.

Reversing steps 1 and 2 (unregistering before slot-clear) will leave the
reserve slot uncleared and block replenish indefinitely.

### Best-Effort RS Eviction Log Grammar

```text
[node_remove] primary_not_found_assume_not_joined name=%s member=%s
[node_remove] rs_remove_succeeded name=%s member=%s
[node_remove] rs_remove_non_ok name=%s member=%s
[node_remove] rs_remove_wait_timeout name=%s member=%s
[node_remove] storage done: container=%s
[node_remove] storage FAILED: container=%s
```

### Allocator Release Rule

The allocator IP is released **only when the teardown script succeeds**.
If the teardown script fails, the IP stays allocated so the failed
identity is never reused by a future node.  This rule applies to both
reserve-loss cleanup and partial reserve-prepare cleanup.

## Verification Targets

1. Recovery distress can activate the ready reserve without waiting for a new
   storage score window.
2. Recovery distress during `PREPARING` keeps the system in degraded wait mode
   instead of spawning a second reserve.
3. Ordinary storage scale-down cannot violate the active-plus-ready-reserve
   floor.
4. Controller logs and testing artifacts distinguish reserve preparation from
   reserve activation.

## Phase 4 Is Complete When

1. Recovery distress triggers the same reserve path as load.
2. Recovery distress does not create duplicate reserve work while the reserve
   is already preparing.
3. A `READY_RESERVED` reserve is required before ordinary storage scale-down is
   allowed.
4. Controller logs clearly distinguish reserve preparation, reserve readiness,
   reserve activation, reserve loss, and reserve replenish submission.

This phase closes the persistent reserve control loop.

