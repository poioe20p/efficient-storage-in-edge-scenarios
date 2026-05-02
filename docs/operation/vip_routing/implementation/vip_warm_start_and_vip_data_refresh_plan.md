# Plan: VIP Warm Start and VIP_DATA Client Refresh

This is the umbrella plan for the VIP warm-start work. It keeps the approved
cross-cutting decisions in one place and delegates the detailed implementation
work to smaller subplans.

## TL;DR

Implement the approved Approach A in one phase:

- Reuse the existing edge-server `PUT /vip_data` control path in
  [app.py](../../../../source/docker/edge_server/source/app.py) so the
  controller can trigger eviction of the cached MongoDB client for a given
  owner LAN.
- Keep the controller as the only backend selector. The edge server does not
  learn a concrete storage backend; it only drops the cached client so the next
  request opens a fresh connection to `VIP_DATA`.
- Add synchronized bounded warm-start preference for newly VIP-eligible
  dynamic backends in
  [vip_routing.py](../../../../source/sdn_controller/vip_routing.py).
- Fix `HEARTBEAT_ENABLED` parsing in both telemetry senders, and keep the
  static-node launch scripts/docs on `HEARTBEAT_ENABLED=true` before relying
  on bootstrap telemetry as a new behavior.
- Start the storage warm period when a dynamic storage node becomes
  `SECONDARY`, pair it with one bootstrap `mongo_stats` event, record one
  pending `VIP_DATA` refresh in Thread 2, and trigger a bounded refresh of
  local edge-server Mongo clients only after a later Thread 2 telemetry pass
  sees the promoted backend become visible in the concrete `VIP_DATA` pool.
- Start the compute warm period when a dynamic compute node is added to the
  `VIP_SERVER` pool, pair it with one bootstrap edge-server telemetry sample,
  but keep compute traffic movement strictly passive: only natural new HTTP
  connections or natural VIP flow expiry can land on the new backend.
- Use a longer warm period for compute than for storage, and keep it at least
  above the current `VIP_HARD_TIMEOUT`, because this phase does not force live
  HTTP connection migration.

---

## Decisions

- **Storage control surface:** reuse `PUT /vip_data` in
  [app.py](../../../../source/docker/edge_server/source/app.py) instead of
  adding a new endpoint.
- **Selector ownership:** the controller still selects the storage backend via
  `VIP_DATA`; the edge server never receives a direct `backend_ip` override.
- **Warm policy:** use bounded warm leases (time + selection budget), not an
  unbounded preference.
- **Warm lease ownership:** keep warm-lease state in `VipRoutingMixin`, but
  guard lease create/prune/consume operations with a small `threading.Lock`
  because compute admission still happens from native Thread 3.
- **Warm lease pruning:** prune only terminally stale leases (expired or out of
  tokens). A backend that is not yet visible in the concrete VIP pool or not
  yet claimable due to IP visibility lag is temporarily ineligible, not stale.
- **Storage activation point:** mark a dynamic storage backend warm only after
  it becomes `SECONDARY` and is admitted into the storage membership set;
  refresh waits for the later concrete VIP-pool rebuild.
- **Compute activation point:** mark a dynamic compute backend warm as soon as
  it is added to `VIP_SERVER`.
- **Heartbeat baseline:** fix `HEARTBEAT_ENABLED` parsing in both telemetry
  senders before layering bootstrap telemetry on top, and keep the static-node
  launch scripts/docs on `HEARTBEAT_ENABLED=true` in the same phase, so the
  plan matches the existing docs model where dynamic nodes are otherwise
  idle-silent.
- **Heartbeat sender safety:** initialize request-telemetry heartbeat state
  independently of the heartbeat thread so dynamic edge servers still emit
  normal request telemetry when `HEARTBEAT_ENABLED=false`.
- **Storage refresh trigger:** create the storage warm lease as soon as the
  backend is promoted to `SECONDARY`, record a pending refresh in Thread 2,
  and delay `_refresh_vip_data_clients()` until a later
  `_on_telemetry_update()` sees the backend in `vip_storage_pool_*` with a
  backend IP.
- **Compute traffic movement:** no forced HTTP disconnect, no temporary
  redirect rule, no per-connection VIP_SERVER flow specialization in this
  phase.
- **Compute warm duration:** the default compute warm window must be longer
  than the current `VIP_HARD_TIMEOUT`, not shorter, because VIP_SERVER remains
  affinity-sticky for existing clients.
- **Mongo client safety:** centralize client retirement in one helper and use
  it from `PUT /vip_data`, `AutoReconnect` recovery, and the `T_dados`
  threshold path; future requests must stop reusing the client immediately,
  while in-flight requests keep the old client until the grace period expires.

---

## Why This Shape

The current code already exposes the two control points this plan needs:

1. [vip_routing.py](../../../../source/sdn_controller/vip_routing.py) owns the
   WSM backend choice for `VIP_SERVER` and `VIP_DATA`.
2. [app.py](../../../../source/docker/edge_server/source/app.py) already keeps
   one cached `MongoClient` per owner LAN and already exposes `PUT /vip_data`.

That means storage can get an active warm-start without changing routing
ownership: the controller tells the edge server to evict the cached client, the
next request opens a new `VIP_DATA` connection, and the controller applies the
warm-start preference at selection time.

Compute does not have an equivalent safe control boundary today. Because live
HTTP cutover is intentionally avoided, compute warm-start must rely on natural
new connections and therefore needs a longer grace period.

Both bootstrap telemetry pushes can reuse event shapes the aggregator already
understands: an edge-server bootstrap can use the existing `heartbeat` shape,
and the storage bootstrap can use the existing `mongo_stats` shape. That avoids
introducing a new telemetry schema just for warm-start visibility.

The plan also has to stay aligned with the current topology and threading
contracts. `add_server_mac()` and `add_storage_mac()` update membership sets,
not necessarily an immediately claimable pool snapshot, and compute admission
still comes from the native elasticity thread. The warm-start logic therefore
needs explicit synchronization and must treat pool-visibility lag as a
temporary not-claimable state rather than a reason to delete the lease.

For Tier 2 storage specifically, the existing Thread 2 mediator already owns
both `rs_secondary_ready` handling and telemetry-fallback promotion inside
`_on_telemetry_update()`. That makes Thread 2 the right place to record a
one-shot pending refresh when promotion happens and to resolve that refresh on
later telemetry passes once `vip_storage_pool_*` and `_mac_to_ip` show the new
backend is actually claimable. A spawned poll helper would add another timing
path without giving the controller a stronger correctness signal.

---

## Scope

### In scope

- Warm-start preference for newly eligible dynamic storage and compute nodes.
- A controller-to-edge-server mechanism for evicting cached Mongo clients so
  future requests open a fresh `VIP_DATA` connection.
- Correct `HEARTBEAT_ENABLED` parsing so the telemetry baseline matches the
  documented static-vs-dynamic heartbeat split before bootstrap sends are
  layered on top.
- Same-phase rollout updates for the static heartbeat launch scripts so the new
  boolean contract does not disable static-node heartbeats.
- One bootstrap telemetry push from both dynamic edge servers and dynamic
  storage nodes when they first become routable through the normal VIP path.
- Separate warm windows for storage and compute, with compute longer than
  storage.

### Out of scope

- Forced VIP_SERVER migration of live HTTP connections.
- Per-connection or 5-tuple VIP_SERVER rules.
- Controller-driven targeted repunt for degraded-window reselection.
- Direct backend steering inside the edge server.
- Cross-controller fan-out of `VIP_DATA` refreshes to peer-LAN edge servers.
  Phase 1 keeps the active refresh local to the controller that owns the edge
  servers it can already address directly.

---

## Subplans

This umbrella plan delegates detailed implementation work to three smaller
subplans.

1. [vip_warm_leases_plan.md](./vip_warm_leases_plan.md)
   Covers warm-start configuration, synchronized warm-lease state in
   `VipRoutingMixin`, compute admission into `VIP_SERVER`, and the explicit
   "natural-move only" boundary for compute traffic.

2. [vip_data_thread2_refresh_plan.md](./vip_data_thread2_refresh_plan.md)
   Covers Tier 2 storage promotion, Thread 2 pending-refresh bookkeeping,
   bounded local `VIP_DATA` refresh fan-out, and Mongo client retirement
   semantics in the edge server.

3. [vip_bootstrap_telemetry_rollout_plan.md](./vip_bootstrap_telemetry_rollout_plan.md)
   Covers `HEARTBEAT_ENABLED` normalization, bootstrap edge/storage telemetry,
   and the static-node script rollout that preserves the documented heartbeat
   baseline.

---

## Preferred Implementation Order

1. Land [vip_warm_leases_plan.md](./vip_warm_leases_plan.md) first.
   It provides the warm-lease primitives used by both the compute and storage
   paths.

2. Land [vip_bootstrap_telemetry_rollout_plan.md](./vip_bootstrap_telemetry_rollout_plan.md)
   second.
  It fixes the telemetry baseline before integrated validation relies on the
  new bootstrap samples.

3. Land [vip_data_thread2_refresh_plan.md](./vip_data_thread2_refresh_plan.md)
   third.
   It wires storage promotion and refresh behavior on top of the warm-lease
   primitives and uses the corrected telemetry baseline during validation.

4. Run integrated verification across all three subplans.

The implementation still lands as one coherent phase; the split only reduces
document size and keeps each file aligned with one control surface.

---

## Cross-Plan Integration Points

- `VipRoutingMixin` remains the only place that chooses warm-preferred
  backends for `VIP_SERVER` and `VIP_DATA` traffic.
- Thread 2 in [main_n1.py](../../../../source/sdn_controller/main_n1.py) and
  [main_n2.py](../../../../source/sdn_controller/main_n2.py) owns storage
  pending-refresh bookkeeping and the readiness check that resolves it.
- `PUT /vip_data` remains an eviction-only control surface; the edge server is
  never told which concrete storage backend to use.
- [control_events.py](../../../../source/sdn_controller/control_events.py) can
  keep its current callback contract if the controllers pass a wrapper.
- [topology.py](../../../../source/sdn_controller/topology/topology.py) keeps
  current VIP pool membership behavior; pool visibility lag is treated as
  temporary non-claimability, not stale state.
- `VIP_SERVER` remains natural-move only in this phase.

---

## Consolidated File Ownership

- [vip_warm_leases_plan.md](./vip_warm_leases_plan.md)
  modifies [scaling_config.py](../../../../source/sdn_controller/scaling_config.py),
  [vip_routing.py](../../../../source/sdn_controller/vip_routing.py), and
  [elasticity.py](../../../../source/sdn_controller/elasticity/elasticity.py).
- [vip_data_thread2_refresh_plan.md](./vip_data_thread2_refresh_plan.md)
  modifies [main_n1.py](../../../../source/sdn_controller/main_n1.py),
  [main_n2.py](../../../../source/sdn_controller/main_n2.py),
  [vip_routing.py](../../../../source/sdn_controller/vip_routing.py), and
  [app.py](../../../../source/docker/edge_server/source/app.py).
- [vip_bootstrap_telemetry_rollout_plan.md](./vip_bootstrap_telemetry_rollout_plan.md)
  modifies [telemetry.py](../../../../source/docker/edge_server/source/telemetry.py),
  [mongo_telemetry.py](../../../../source/docker/edge_storage_server/mongo_telemetry.py),
  [build_network_1.sh](../../../../source/scripts/network/build_network_1.sh),
  and [build_network_2.sh](../../../../source/scripts/network/build_network_2.sh).

Files intentionally unchanged in this phase:

- [control_events.py](../../../../source/sdn_controller/control_events.py)
- [topology.py](../../../../source/sdn_controller/topology/topology.py)

---

## Consolidated Verification

1. **Heartbeat baseline**
   Dynamic nodes stay idle-silent by default, static nodes keep periodic
   heartbeats after the `true`/`false` rollout, and normal edge-server request
   telemetry still works when the heartbeat thread is disabled.

2. **Storage promotion path**
   A Tier 2 storage backend becomes warm at `SECONDARY`, records exactly one
  pending refresh in Thread 2, emits one bootstrap `mongo_stats` sample, and
  triggers `PUT /vip_data` only after a later full telemetry pass sees it in
  the concrete storage pool with a known backend IP.

3. **Storage reconnect safety**
   A `VIP_DATA` refresh retires the cached Mongo client for future requests
   without breaking in-flight requests, and the same retirement path is used by
   `/vip_data`, `AutoReconnect`, and `T_dados` eviction.

4. **Warm selection and expiry**
   The next eligible `VIP_DATA` or `VIP_SERVER` packet-in can consume the warm
   lease before steady-state WSM resumes, and both lease types expire cleanly
   by time or token budget.

5. **No regression in drain/remove**
   Existing compute drain and scale-down behavior still works after the Mongo
   client retirement and warm-admission changes.

---

## Dependencies

- No new external packages.
- Reuse existing Flask, `requests`, PyMongo, and OS-Ken surfaces.
- Reuse the aggregator's existing `heartbeat` and `mongo_stats` event shapes
  for bootstrap visibility; no new telemetry schema is required.
- Reuse the existing Tier 1 controller-to-edge-server HTTP control pattern in
  [main_n1.py](../../../../source/sdn_controller/main_n1.py) and
  [main_n2.py](../../../../source/sdn_controller/main_n2.py) as the model for
  the new `VIP_DATA` refresh fan-out, including per-target request-failure
  handling.

---

## Documentation Updates

Update these documents once implementation lands:

- [vip_routing_overview.md](../vip_routing_overview.md)
  Add a warm-lease subsection and explain that compute warm-up is passive while
  storage warm-up can actively trigger future `VIP_DATA` reconnections.
- [telemetry_overview.md](../../telemetry/telemetry_overview.md)
  Document the corrected `HEARTBEAT_ENABLED` contract and both bootstrap
  telemetry pushes.
- [heartbeat_dynamic_node_gate_plan.md](../../other/heartbeat_dynamic_node_gate_plan.md)
  Update examples and rollout notes to use the same strict `true` / `false`
  contract as the implementation plan.
- [system_mechanisms.md](../../system_mechanisms.md)
  Describe the controller-driven Mongo-client eviction control, bounded warm
  preference, bootstrap telemetry, and Thread 2 pending-refresh behavior.
- [elasticity_overview.md](../../elasticy_manager/elasticity_overview.md)
  Note that compute admission into `VIP_SERVER` now creates a compute warm
  lease, and storage promotion to `SECONDARY` creates a storage warm lease,
  pending refresh record, and bootstrap `mongo_stats` sample.

---

## Deferred Follow-Up

These are intentionally deferred until this narrower phase is validated:

- cross-controller `VIP_DATA` refresh fan-out for peer-LAN edge servers
- degraded-window targeted reselection for future requests
- VIP_SERVER soft-close or drain-assisted warm rebalance
- per-connection VIP_SERVER steering
