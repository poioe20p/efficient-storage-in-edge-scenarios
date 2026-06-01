# System Scenarios — Workflow Companion

This document accompanies the [System Mechanisms](system_mechanisms.md) gateway
with concise scenario walkthroughs. Each scenario follows the same compact
template: trigger, participants, controller behaviour, and a pointer to the
authoritative subsystem reference.

---

## Scenario 1 — VIP Interception and Request Routing

**Trigger:** A client or edge-server opens a TCP connection to a Virtual IP
(`VIP_SERVER` for HTTP, `VIP_DATA_N*` for MongoDB).

**Participants:** OVS switch, controller Thread 1 (`VipRoutingMixin`), edge
server containers, MongoDB storage backends, inter-LAN router (for cross-
network backends).

**What happens:**

1. The OVS switch punts the first packet to the controller (priority-100 VIP
   punt rules).
2. Thread 1 scores candidate backends using multi-dimensional WSM cost
   functions fed by in-memory telemetry state, selects the best backend, and
   installs a DNAT+SNAT flow-rule pair at priority 200.
3. Thread 1 sends a Packet-Out for the first packet; subsequent packets in
   the same flow are forwarded entirely in the OVS switch.
4. When the flow rule expires (idle/hard timeout), the next packet triggers
   a fresh punt and re-selection.
5. For cross-network backends, Thread 1 resolves the output port through a
   3-step fallback (local graph → host attachment → peer_hosts + router port);
   the DNAT'd packet crosses the inter-LAN router, and the peer OVS switch
   delivers it via normal L2 forwarding — no second Packet-In fires on the
   remote controller.

**Detailed reference:** [VIP Routing Overview](vip_routing/vip_routing_overview.md)

---

## Scenario 2 — Telemetry Propagation

**Trigger:** An edge server completes an HTTP request or a MongoDB sidecar
detects activity.

**Participants:** Edge server containers, MongoDB sidecars, per-network ZMQ
aggregators, controller telemetry greenthread (`ZmqTelemetrySource`).

**What happens:**

1. Each edge server pushes a per-request metric event (latency, CPU, RAM) via
   ZMQ PUSH to its local aggregator. MongoDB sidecars push periodic
   `mongo_stats` snapshots (replication lag, member state, connections, CPU,
   RAM) via the same channel.
2. The per-network aggregator drains events into a windowed buffer and
   publishes a `TelemetrySummary` via ZMQ PUB every `WINDOW_S` seconds.
3. The controller's telemetry greenthread receives summaries from both
   aggregators, updates in-memory `_server_stats` and `_storage_stats` dicts
   (consumed by Thread 1 for WSM scoring), evaluates domain-level degradation
   thresholds, and submits typed alerts to Thread 3's priority queue.
4. The greenthread also processes control events (`drain_complete`,
   `rs_secondary_ready`) for container lifecycle management.

**Detailed reference:** [Telemetry Overview](telemetry/telemetry_overview.md)

---

## Scenario 3 — Compute Scale-Up and Scale-Down

**Trigger:** Sustained $T_{proc}$ (processing latency) above the adaptive
compute degradation threshold (scale-up), or sustained low CPU and latency
(scale-down).

**Participants:** Controller Thread 2 (telemetry → alert submission),
Thread 3 (`ElasticityManager`), Docker engine, OVS switch, edge server
containers.

**What happens (scale-up):**

1. The telemetry greenthread detects that $T_{proc}$ exceeds the adaptive
   threshold for 3 of the last 5 windows and submits a `ComputeAlert` to
   Thread 3's priority queue.
2. Thread 3 spawns a new `edge_server` container via `NodeAdder`, attaches it
   to the OVS switch, and registers the MAC in the `VIP_SERVER` pool with a
   warm lease — the new server is immediately eligible for WSM selection.

**What happens (scale-down):**

1. When both CPU and latency are below threshold for 7 of the last 12 windows,
   a `ScaleDownComputeAlert` is submitted.
2. Thread 3 executes a two-phase drain: Phase A removes the MAC from the VIP
   pool and sends `POST /drain` to the container. Phase B (triggered by
   `drain_complete` or timeout) tears down OVS ports, stops the container,
   and releases the IP.

**Detailed reference:** [Elasticity Overview](elasticy_manager/elasticity_overview.md)

---

## Scenario 4 — Storage Scale-Up and Scale-Down

**Trigger:** Sustained $T_{dados}$ (data-access latency) above the adaptive
storage degradation threshold (scale-up), or sustained underutilisation
(scale-down).

**Participants:** Controller Thread 2, Thread 3, Docker engine, OVS switch,
MongoDB sidecars, replica set primaries.

**What happens (scale-up):**

1. The telemetry greenthread detects that $T_{dados}$ exceeds the diminishing-
   increment adaptive threshold for 2 of the last 5 windows and submits a
   `DataAlert`.
2. Thread 3 spawns an `edge_storage_server` container, attaches it to the
   network, and returns. The container's sidecar performs async `rs.add()`
   and emits `rs_secondary_ready` when the node reaches SECONDARY state.
3. On `rs_secondary_ready`, the controller promotes the new backend into the
   `VIP_DATA` pool with a short warm lease — it becomes eligible for storage
   selection via normal `VIP_DATA` routing.

**What happens (scale-down):**

1. When 7 of 12 windows show idle storage, a `ScaleDownDataAlert` is
   submitted.
2. Thread 3 removes the MAC from the `VIP_DATA` pool, calls `rs.remove()`,
   and then runs the network teardown script to clean up the container, OVS
   port, volume, and IP.

**Detailed reference:** [Elasticity Overview](elasticy_manager/elasticity_overview.md)
and [VIP Routing Overview](vip_routing/vip_routing_overview.md)

---

## Scenario 5 — Selective Sync Promotion and Drain

**Trigger (promotion):** Sustained cross-region read demand on a specific
collection — p95 $T_{dados}$ breach, cross-region footprint above threshold,
read-heavy operation mix, and cooldown elapsed.

**Trigger (drain):** Hot set cools (all collections below hit threshold),
Change Stream lag exceeds staleness limit, or (future) Tier 2 cross-LAN
supersede.

**Participants:** Consumer-side controller (`PromotionCoordinator`),
Thread 3 (`ElasticityManager`), Docker engine, OVS switch, edge server
containers, `edge_selective_storage` container, owner-LAN RS primary.

**What happens (promotion):**

1. The `PromotionCoordinator` evaluates per-collection access counters and
   cross-region latency every telemetry window. When the promotion predicate
   is met, it submits a `SelectiveSyncAlert` to Thread 3.
2. Thread 3 spawns an `edge_selective_storage` container (standalone `mongod`
   + per-collection Change-Stream forwarders). Once the container reports
   ready, the coordinator broadcasts a `tier1_manifest` to every edge server
   in the consumer LAN.
3. Edge servers receive the manifest. The `cached_collection(...)` wrapper
   consults it on every point-lookup `find_one({"_id": ...})`:
   — if the `_id` is in the manifest for `(owner_lan, collection)`, the read
   is served from the local Tier 1 `mongod` on port `27018`.
   — cold reads and all writes fall through to `VIP_DATA` as normal.
4. The controller does **not** route `VIP_DATA` to the selective-sync node.
   Tier 1 selection is entirely client-side and manifest-driven.

**What happens (drain):**

1. Phase A: the coordinator revokes the manifest (broadcasts `host: null`),
   sends `POST /drain` to the Tier 1 supervisor, and records a `PendingDrain`.
2. The supervisor stops all `ForwarderWorker` threads (each persists a final
   resume token), emits `drain_complete` via ZMQ, and shuts down `mongod`
   cleanly.
3. Phase B (on `drain_complete`): Thread 3 tears down OVS ports and removes
   the container. A cooldown prevents immediate re-promotion.

**What must not be said about Tier 1:**

- The controller does **not** route `VIP_DATA` to the selective-sync node.
- VIP routing does **not** perform Tier 1 backend selection.
- Tier 1 does **not** replace normal `VIP_DATA` fallback behaviour.

**Detailed reference:** [Selective Sync Overview](selective_sync/selective_sync_overview.md)

---

## Scenario Map to Authoritative Docs

| Scenario | Primary Reference |
|:---|:---|
| VIP interception and request routing | [VIP Routing Overview](vip_routing/vip_routing_overview.md) |
| Telemetry propagation | [Telemetry Overview](telemetry/telemetry_overview.md) |
| Compute scale-up / scale-down | [Elasticity Overview](elasticy_manager/elasticity_overview.md) |
| Storage scale-up / scale-down | [Elasticity Overview](elasticy_manager/elasticity_overview.md) and [VIP Routing Overview](vip_routing/vip_routing_overview.md) |
| Selective sync promotion and drain | [Selective Sync Overview](selective_sync/selective_sync_overview.md) |
