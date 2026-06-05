# Storage Persistent Reserve Plan

## Status

Implemented.

## Scope

Same-LAN Tier 2 storage only.

This plan introduces a persistent single reserve per LAN for storage scale-up
and recovery. It does not change compute elasticity and it does not add a
cross-LAN reserve model.

## Objective

Remove the first-step storage readiness gap from the critical path.

Today the system can only gain extra same-LAN storage capacity by cold-starting
a new dynamic storage node and waiting for it to become a usable `SECONDARY`.
That path is too slow to be the primary response to per-second client traffic
or to the first recovery event on an already stressed LAN.

The target model is:

1. each LAN always maintains exactly one reserved same-LAN storage node
2. the reserved node is a real joined `SECONDARY`
3. the reserved node stays out of `VIP_DATA` while reserved
4. the first storage load alert or the first recovery trigger activates the
   ready reserve immediately
5. reserve replenishment starts right after activation or reserve loss
6. only one reserve preparation may exist per LAN at a time

Cold-start creation still exists, but it moves off the first-response path.
Cold-start becomes the mechanism that replenishes the next reserve rather than
the mechanism that provides the first extra capacity only after a long wait.

## Locked Requirements

1. Each LAN must always maintain exactly one same-LAN storage reserve.
2. The reserve is created through the existing dynamic storage lifecycle.
3. The reserve must be a real heartbeating `SECONDARY`.
4. The reserve must be excluded from `VIP_DATA` while reserved.
5. The first storage load alert or the first recovery need consumes the ready
   reserve into active service.
6. Once the reserve is activated, lost, or found missing, the controller must
   start replenishing the next reserve immediately.
7. If the reserve is already `PREPARING`, the controller waits for it instead
   of creating a second reserve.
8. Storage growth therefore becomes stepwise: activate reserve, prepare next
   reserve, activate next reserve when ready.
9. Ordinary storage scale-down must never violate the active-capacity-plus-one-
   reserve floor.

## Recommended Direction

Implement a persistent single reserve slot per LAN, owned by Thread 2 and
backed by the existing Thread 3 storage creation path.

The reserve is controller state first, not a special container name. Once a
reserve is activated, it becomes an ordinary active dynamic storage node. The
next reserve is then created as a new dynamic node through the existing
cold-start path.

This is the correct trade-off for the current system because the observed
failure mode was not a lack of scale-up thresholds. It was the fact that the
first usable additional storage node only became available after a long async
replica-set join path.

## Hard Implementation Rules

These rules are intended to remove ambiguity for a weaker implementation model.

1. Implement the phases strictly in order.
2. Do not introduce a second reserve per LAN.
3. Do not identify the reserve by a fixed name such as `dyn0`.
4. Do not create a new reserve-only storage lifecycle; reuse the current
   storage-add path.
5. Do not change compute elasticity as part of this plan.
6. Do not let a reserved node enter VIP automatically on
   `rs_secondary_ready`.
7. Do not bypass the reserve path by spawning an ordinary active storage node
   while the reserve is already `PREPARING`.
8. Do not count a `PREPARING` reserve as satisfying the ready-reserve floor.

## Negative-Path Contract

These rules govern reserve failure, loss, and cleanup. They are as binding as
the positive-path rules above.

### Prepare Failure

1. Reserve prepare failures are owned **per LAN** in Thread 3 and drained
   **per LAN** in Thread 2. One controller must never consume or discard the
   other LAN's failure outcome.
2. A standby prepare that returns without a usable MAC is a **hard failure**,
   not a degraded success. Thread 3 must immediately clean up the container,
   release the allocator IP, and publish `ReservePrepareFailed`.
3. After a prepare failure, Thread 2 clears the `PREPARING` slot back to
   `NONE` (preserving any latched pending activation). Replenish retries
   **only on the next telemetry-cycle maintenance pass** — never from the
   failure handler itself.

### Pending Activation

4. A pending activation latched while the reserve is `PREPARING` carries
   forward across reserve replacement and expires after
   `_STORAGE_RESERVE_PENDING_WINDOWS` telemetry windows.
5. Expiry clears only the pending-activation fields (`activation_pending`,
   `pending_reason`, `pending_windows_remaining`). It does **not** clear
   reserve maintenance or the slot state.

### Reserve Loss

6. When a reserved node is detected absent, the mediator must process loss in
   this exact order:
   1. Clear the reserve slot identity (preserving pending activation).
   2. Unregister the node from registry tracking.
   3. Submit `CleanupReserveAlert` to Thread 3.
   Reversing steps 1 and 2 will leave the slot uncleared and block replenish.

### Reserve Cleanup

7. Reserve cleanup uses **best-effort RS eviction**: attempt `rs.remove()`
   via the primary, but always continue to container/network teardown
   regardless of the RS-eviction outcome.
8. If current-primary discovery fails during reserve cleanup, the code
   assumes the member never joined and proceeds directly to teardown.
   This is **not** a cleanup failure.
9. If `rs.remove()` returns non-``ok:1`` or RS-wait confirmation times
   out, the warning is logged and teardown continues. The cleanup is
   still considered successful if the teardown script succeeds.
10. Reserve cleanup is a dedicated Thread 3 alert path
   (`CleanupReserveAlert`). It must never reuse ordinary scale-down drain
   or VIP isolation — the reserve never served edge traffic.
11. The allocator IP is released **only when teardown succeeds**.  If the
   teardown script fails the IP stays allocated so a future node gets a
   fresh identity.
12. Ordinary storage scale-down must **never** use best-effort mode —
   the strict `remove_storage_node(...)` contract is unchanged for
   active dynamic storage.

## Ordered Implementation Contract

Implement in this exact order:

1. Phase 1: state and accounting only
2. Phase 2: reserve preparation and ready gating
3. Phase 3: load-trigger activation and immediate replenish
4. Phase 4: recovery-trigger activation, reserve-floor enforcement, and final
   observability

Do not start a later phase before the earlier phase has its own code changes,
tests, and documentation updates complete.

## Runtime Model

For each LAN, Thread 2 maintains one controller-side reserve slot:

1. `NONE` - no reserve exists yet
2. `PREPARING` - reserve creation is already in flight
3. `READY_RESERVED` - reserve is alive, joined, visible, and still outside VIP

The trigger semantics become:

1. If a storage load alert fires and the reserve is `READY_RESERVED`, activate
   the reserve immediately and start preparing the next reserve.
2. If a storage load alert fires and the reserve is `PREPARING`, mark that the
   reserve should be activated as soon as it becomes ready, then wait.
3. If recovery distress is observed and the reserve is `READY_RESERVED`,
   activate the reserve immediately and start preparing the next reserve.
4. If recovery distress is observed and the reserve is `PREPARING`, keep the
   current service path running in degraded mode and wait for the reserve to
   become ready.
5. If the reserve is missing, submit exactly one reserve preparation for that
   LAN and mark the LAN as degraded until coverage returns.

The reserve model is intentionally single-file and same-LAN only. It gives the
system deterministic first-step storage readiness without introducing a pool of
prewarmed nodes or a second reserve per LAN.

## Phase Map

| Phase | Focus | Outcome |
| --- | --- | --- |
| [Phase 1](./phase_1_storage_persistent_reserve_state_and_accounting.md) | Reserve state and accounting | Adds controller-side reserve slot state and keeps reserved nodes out of ordinary dynamic accounting |
| [Phase 2](./phase_2_storage_persistent_reserve_preparation_and_readiness.md) | Reserve preparation | Prepares one reserve per LAN through the current storage lifecycle and holds it outside VIP |
| [Phase 3](./phase_3_storage_persistent_reserve_activation_and_replenishment.md) | Load-driven activation and replenish | Makes the reserve the first-step same-LAN storage scale-up action and starts immediate replenish |
| [Phase 4](./phase_4_storage_persistent_reserve_recovery_floor_and_visibility.md) | Recovery trigger, scale-down floor, and operational visibility | Adds controller-visible recovery triggers, degraded waiting semantics, reserve-floor enforcement, and analysis guidance |

## Why This Sequence

1. Phase 1 comes first because the current controller assumes every tracked
   dynamic storage node either counts toward thresholds or can later be removed.
   That is false for a reserved node.
2. Phase 2 comes second because reserve creation should reuse the current
   storage creation path instead of inventing a second storage bootstrap path.
3. Phase 3 changes the meaning of same-LAN storage scale-up from "spawn now"
   to "activate now, replenish next".
4. Phase 4 closes the loop by making recovery distress a first-class trigger,
   enforcing the reserve floor during scale-down, and documenting how the new
   lifecycle should be interpreted in experiment artifacts.

## File Map

Expected implementation files:

1. `source/sdn_controller/scaling_config.py`
2. `source/sdn_controller/node_registry.py`
3. `source/sdn_controller/control_events.py`
4. `source/sdn_controller/main_n1.py`
5. `source/sdn_controller/main_n2.py`
6. `source/sdn_controller/scaling_policy.py`
7. `source/sdn_controller/telemetry/models.py`
8. `source/sdn_controller/elasticity/elasticity.py`
9. `source/sdn_controller/elasticity/node_common.py`
10. `source/sdn_controller/elasticity/storage_node_manager.py`
11. `source/docker/local_state_server/aggregator.py`

Expected documentation updates after implementation:

1. `docs/operation/elasticy_manager/scale_up/storage_scale_up.md`
2. `docs/operation/elasticy_manager/elasticity_overview.md`
3. `docs/operation/system_mechanisms.md`

## Exact Ownership By File

Use this as the implementation handoff map.

1. `source/sdn_controller/node_registry.py`
   Owns reserve slot state, reserve helper methods, and exclusion of reserved
   nodes from ordinary storage accounting.
2. `source/sdn_controller/elasticity/node_common.py`
   Owns the `NodeInfo` metadata bit that marks a node as reserved.
3. `source/sdn_controller/elasticity/elasticity.py`
   Owns the new reserve-preparation alert type and Thread 3 dispatch.
4. `source/sdn_controller/elasticity/storage_node_manager.py`
   Owns storage creation details and the heartbeat override used for reserve
   creation.
5. `source/sdn_controller/control_events.py`
   Owns the ready-state gate that decides whether a ready storage node enters
   VIP immediately or becomes `READY_RESERVED`.
6. `source/sdn_controller/main_n1.py` and `source/sdn_controller/main_n2.py`
   Own reserve preparation submission, reserve activation, waiting semantics,
   and reserve replenish submission.
7. `source/sdn_controller/scaling_policy.py`
   Owns cooldown/reset bookkeeping for storage activation, but not reserve slot
   state.
8. `source/docker/local_state_server/aggregator.py` and
   `source/sdn_controller/telemetry/models.py`
   Own the controller-visible recovery-distress signal used in Phase 4.

## Phase Exit Criteria

1. Phase 1 is done only when reserved nodes can exist in controller state
   without affecting ordinary storage counts or ordinary storage scale-down.
2. Phase 2 is done only when one reserve per LAN can be prepared, can reach
   `READY_RESERVED`, and still stays out of VIP.
3. Phase 3 is done only when a same-LAN load trigger consumes a ready reserve,
   does not create a second reserve while preparing, and immediately starts the
   next reserve preparation.
4. Phase 4 is done only when a recovery-distress signal can use the same
   reserve trigger path and ordinary storage scale-down cannot violate the
   ready-reserve floor.

## Notes For Implementation

1. Do not use a fixed reserve identity such as `dyn0`. Reserve identity should
   live in controller state, not in a permanent container name.
2. Reuse the existing warm admission path when a reserve is activated so the
   newly exposed backend receives the same bounded preference as any other
   fresh storage backend.
3. Keep reserve preparation singleton per LAN. Repeated triggers during
   `PREPARING` should only latch intent and wait.
4. Treat reserve activation as the authoritative first-step same-LAN storage
   scale-up event for cooldown and scale-down reset purposes.
5. When a reserve activates, that same node immediately stops being a reserve
   and becomes ordinary active dynamic storage.
6. Replenishment must prepare a new reserve node. It must not try to turn the
   just-activated node back into a reserve later.
