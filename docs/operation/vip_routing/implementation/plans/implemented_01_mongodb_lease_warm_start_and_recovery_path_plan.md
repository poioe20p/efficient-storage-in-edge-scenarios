# Plan: MongoDB Lease Follow-Up After Warm/Recovery Baseline

**Status:** Proposed follow-up on top of an implemented baseline

This file keeps the `01_` umbrella-plan position in the lease sequence, but it
no longer tracks the already-landed warm-start and recovery-path baseline.

The current runtime already has:

- bounded controller-side warm storage leases
- recovery VIPs and narrow recovery flow installation
- LAN-scoped epoch rotation in the edge server
- config-only, idempotent `/vip_data` updates

This umbrella plan now focuses only on the remaining MongoDB lease semantics
that still sit above that implemented baseline.

## TL;DR

Remaining MongoDB lease work is:

1. add a request-scoped lease state machine above the implemented LAN-scoped
   epoch model
2. optionally add controller-side failed-backend avoidance, but only after
   request-level recovery failure becomes explicit
3. refine replay-safety and observability only if experiments still need them

## Implemented Baseline

- [vip_routing.py](../../../../../source/sdn_controller/vip_routing.py)
  already owns bounded warm storage leases, recovery VIP packet handling, and
  narrow recovery DNAT/SNAT rules.
- [main_n1.py](../../../../../source/sdn_controller/main_n1.py) and
  [main_n2.py](../../../../../source/sdn_controller/main_n2.py) already admit
  promoted storage backends and mark them warm without the old refresh queue.
- [app.py](../../../../../source/docker/edge_server/source/app.py) already
  seeds a fixed startup LAN registry, rotates current epochs to recovery on
  connection-level failure, rolls recovery epochs back in background
  housekeeping, and keeps `/vip_data` config-only and idempotent.
- [topology.py](../../../../../source/sdn_controller/topology/topology.py),
  [osken-controller.env](../../../../../source/scripts/osken-controller.env),
  [build_network_1.sh](../../../../../source/scripts/network/build_network_1.sh),
  [build_network_2.sh](../../../../../source/scripts/network/build_network_2.sh),
  [compute_node_manager.py](../../../../../source/sdn_controller/elasticity/compute_node_manager.py),
  [node_common.py](../../../../../source/sdn_controller/elasticity/node_common.py),
  and [add_network_node.sh](../../../../../source/scripts/network/add_network_node.sh)
  already carry the recovery-VIP configuration and reserved-address assumptions
  needed by that baseline.
- [vip_data_recovery_epoch_model.md](../vip_data_recovery_epoch_model.md),
  [vip_routing_overview.md](../../vip_routing_overview.md), and
  [system_mechanisms.md](../../../system_mechanisms.md) already describe that
  implemented state.

## Remaining Problem

The implemented epoch model fixes storage-path recovery ownership, but
request-level MongoDB lease semantics are still implicit.

The remaining gaps are:

1. multiple `timed_db(...)` blocks in one HTTP request still look like repeated
   independent storage checkouts instead of one request-owned lease
2. request replay-safety, one bounded failure-driven rebind, and one clear
  shared decision owner per LAN are not yet explicit first-class design
  rules
3. controller-side failed-backend avoidance needs a terminal request-level
   recovery-failure signal, not just a recovery PacketIn

## Approved Focus

- Treat the current warm/recovery baseline as implemented context, not pending
  work.
- Focus new work on MongoDB lease semantics above the epoch model.
- Keep the controller as the only backend selector.
- Keep `/vip_data` as a configuration surface only; this follow-up does not
  reopen refresh fan-out.
- Keep the current LAN-scoped epoch model as the lower-level owner of the
  `MongoClient`, breaker, bound VIP, and retirement lifecycle.
- Treat the LAN authority state as the only shared decision owner for one LAN:
  current epoch selection, fresh-request admission, and rebind classification
  must be linearized there.
- Layer request-scoped lease behavior above epochs rather than replacing the
  epoch model.
- Make failed-backend avoidance optional and dependent on request-level
  recovery outcome, not on every reconnect.

## Scope

### In scope

- request-scoped storage leases per owner LAN inside one HTTP request
- explicit request lease lifecycle, one bounded failure-driven rebind,
  terminal failure, and completion
- conservative replay-safety gating for bounded rebinding
- one per-LAN authority for fresh admission, current-versus-stale
  classification, and current-epoch-aware breaker state
- terminal recovery-failure signaling from the edge server to the controller
- optional short-lived failed-backend avoidance keyed by
  `(edge_server_mac, domain)`
- documentation and observability updates needed to explain the lease layer

### Out of scope

- controller-side warm-lease implementation
- recovery VIP introduction, recovery-VIP env wiring, or narrow recovery flow
  installation
- `/vip_data` idempotence, startup LAN registry seeding, or epoch housekeeping
  baseline
- controller-driven `/vip_data` refresh fan-out
- direct backend steering inside the edge server
- compute routing or compute scale-up changes

## Remaining Phase Breakdown

### Phase 1 - Request-Scoped Lease State Machine

Reference:
[implemented_02_mongodb_lease_request_state_machine_plan.md](./implemented_02_mongodb_lease_request_state_machine_plan.md)

Add a request-scoped lease layer above the implemented LAN-scoped epoch model.

This phase should:

- create one request-owned lease per owner LAN instead of treating each
  `timed_db(...)` block as a fresh checkout
- preserve stable backend reuse within that request-owned lease
- model one bounded failure-driven rebind separately from normal healthy reuse
- linearize fresh admission, epoch binding, and rebind classification through
  one shared per-LAN authority state
- fail conservatively when replay safety is no longer guaranteed

This phase is edge-server focused. It should not reopen the controller-side
recovery-VIP plumbing that is already live.

### Phase 2 - Failed-Backend Avoidance After Terminal Recovery Failure

Reference:
[implemented_03_mongodb_lease_failed_backend_avoidance_plan.md](./implemented_03_mongodb_lease_failed_backend_avoidance_plan.md)

Only after Phase 1 makes request-level lease outcomes explicit, optionally add
a short-lived controller-side "avoid last failed backend" memory.

This phase should:

- arm avoidance only from a terminal request-level recovery failure
- preserve the existing warm-first then WSM storage-selection order on the
  filtered pool
- fall back safely to the full pool if avoidance would empty the candidate set
- remain storage-specific and temporary

### Phase 3 - Optional Replay-Safety and Observability Refinement

Reference:
[implemented_02_mongodb_lease_request_state_machine_plan.md](./implemented_02_mongodb_lease_request_state_machine_plan.md)

Only if experiments need finer behavior after Phases 1 and 2, refine the
lease layer with:

- more explicit replay-safety annotations for provably safe operations
- request-terminal lease outcome telemetry for experiments and thesis material
- doc and diagram updates that make the request-lease layer visible alongside
  the epoch baseline

These refinements are optional follow-up, not prerequisites for the current
warm/recovery baseline.

## Supporting Plans and Baseline Docs

- [vip_data_recovery_epoch_model.md](../vip_data_recovery_epoch_model.md)
  documents the implemented LAN-scoped epoch baseline that this umbrella plan
  now builds on.
- [implemented_02_mongodb_lease_request_state_machine_plan.md](./implemented_02_mongodb_lease_request_state_machine_plan.md)
  defines the request-scoped lease layer, one bounded request-level rebind,
  and one shared per-LAN authority for concurrency-sensitive decisions.
- [implemented_02_mongodb_lease_request_state_machine/README.md](./implemented_02_mongodb_lease_request_state_machine/README.md)
  decomposes the request-lease work into implementation-ready phase subplans
  with code sketches at the `app.py`, `platform_cache.py`, and `telemetry.py`
  seams.
- [implemented_03_mongodb_lease_failed_backend_avoidance_plan.md](./implemented_03_mongodb_lease_failed_backend_avoidance_plan.md)
  defines the optional controller-side failed-backend avoidance that depends
  on Phase 1.
- [implemented_03_mongodb_lease_failed_backend_avoidance/README.md](./implemented_03_mongodb_lease_failed_backend_avoidance/README.md)
  decomposes the optional controller-side avoidance work into event,
  controller-state, and selector-filtering subplans.
- [edge_storage_connection_hard_failure_epoch_plan.md](../../../other/edge_storage_connection_hard_failure_epoch_plan.md)
  provides the deeper design background for the implemented epoch baseline.

## Consolidated File Ownership

- [app.py](../../../../../source/docker/edge_server/source/app.py)
  request-scoped lease lifecycle, linearized admit-and-bind and rebind
  decisions, request teardown, and terminal recovery-failure emission.
- [platform_cache.py](../../../../../source/docker/edge_server/source/platform_cache.py)
  request-level operation tracking and any replay-safety refinement needed by
  the lease state machine.
- [control_events.py](../../../../../source/sdn_controller/control_events.py)
  carries terminal lease-failure events from the edge-server side into
  controller-side handling.
- [vip_routing.py](../../../../../source/sdn_controller/vip_routing.py)
  optional failed-backend avoidance, last-choice tracking, and filtered
  recovery candidate selection.
- [osken-controller.env](../../../../../source/scripts/osken-controller.env)
  optional avoidance TTL and attempt-budget knobs if Phase 2 lands.

## Consolidated Verification

Validate the remaining MongoDB lease work with lease-specific checks rather
than re-verifying already-landed warm/recovery plumbing.

### Phase 1 checks

- one HTTP request that touches the same owner LAN multiple times creates one
  request lease and one final release
- one HTTP request can hold distinct leases for distinct owner LANs without
  mixing them
- a read-only request can use one bounded failure-driven rebind and continue,
  whether by authoritative cutover or by stale-epoch catch-up
- a replay-unsafe request fails instead of silently rebinding after connection
  failure

### Phase 2 checks

- after terminal recovery failure, the next bounded recovery selection avoids
  the prior backend when an alternative exists
- single-backend pools fall back safely to the full pool instead of dropping
  traffic
- avoidance expiry and attempt budgets remain bounded and monotonic

### Phase 3 checks

- telemetry can distinguish healthy completion, one-rebind recovery or
  catch-up, and terminal recovery failure
- updated docs describe request-scoped lease ownership and one shared per-LAN
  authority without regressing the implemented epoch baseline

## Dependencies

- no new external packages
- builds on the implemented LAN-scoped epoch model in
  [app.py](../../../../../source/docker/edge_server/source/app.py)
- builds on the implemented recovery-VIP handling and narrow recovery rules in
  [vip_routing.py](../../../../../source/sdn_controller/vip_routing.py)
- assumes the current warm-lease invalidation and recovery-VIP config wiring
  remain unchanged
- [implemented_03_mongodb_lease_failed_backend_avoidance_plan.md](./implemented_03_mongodb_lease_failed_backend_avoidance_plan.md)
  depends on
  [implemented_02_mongodb_lease_request_state_machine_plan.md](./implemented_02_mongodb_lease_request_state_machine_plan.md)
  landing first

## Documentation Updates

Update these documents when the remaining MongoDB lease work lands:

- [vip_routing_overview.md](../../vip_routing_overview.md)
  explain the ownership split between LAN-scoped epochs and request-scoped
  leases.
- [system_mechanisms.md](../../../system_mechanisms.md)
  describe request-local lease reuse, one shared per-LAN authority, bounded
  rebinding, terminal failure, and optional failed-backend avoidance.
- [vip_data_recovery_epoch_model.md](../vip_data_recovery_epoch_model.md)
  keep the epoch-baseline doc aligned with the new request-lease layer above
  it.
- [edge_storage_connection_epoch_visuals.md](../../../other/edge_storage_connection_epoch_visuals.md)
  update diagrams if the request-lease layer becomes part of the thesis-facing
  explanation.

## Deferred Follow-Up

- explicit per-operation replay annotations beyond the conservative default
- broader experiment-only observability if lease outcome counters are needed
- broader controller-side backend exclusion or cross-controller coordination
  if the short-lived avoidance model proves insufficient
