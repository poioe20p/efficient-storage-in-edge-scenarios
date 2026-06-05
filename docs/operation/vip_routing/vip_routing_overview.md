# VIP Routing -- Overview

## Purpose

`VipRoutingMixin` intercepts traffic destined for virtual IP addresses and
load-balances it across backend containers using multi-dimensional WSM
(Weighted Sum Model) cost functions. It handles ARP virtualization, DNAT/SNAT
flow rule installation, and cross-network forwarding via the inter-LAN router.

This is **not a new thread**. All methods run inline in Thread 1's
`packet_in_handler` -- same greenthread, same event loop. State written by
Thread 2 (`_server_stats`, `_storage_stats`) is read here without locks because
eventlet uses cooperative switching and these dicts are only mutated between
yield points.

---

## Architecture Summary

`VipRoutingMixin` must sit **before** `TopologyMixin` in the class MRO so that
its `_on_datapath_connected` override is the cooperative hook reached by the
topology reconnect path after stale flows are flushed and the table-miss rule
is reinstalled.

### Internal Implementation Split

The public `VipRoutingMixin` in `source/sdn_controller/vip_routing.py` is now a
thin facade. It preserves the controller-facing API and cooperative lifecycle
hooks while delegating implementation to the private
`source/sdn_controller/_vip_routing/` package:

- `config.py` -- shared constants, logger, and `WarmLease`
- `state.py` -- controller-owned mutable state, backend lifecycle hooks, and
  telemetry cache updates
- `selection.py` -- server and storage selection, warm-lease claiming,
  recovery filtering, and round-robin tie-breaking
- `flows.py` -- DNAT/SNAT flow construction and first-packet `PacketOut`
- `ingress.py` -- ARP snooping, VIP packet dispatch, ARP replies, and punt
  rule installation

### Thread 1 -- VIP Interception and Routing

The OS-Ken event loop drives `packet_in_handler()`, which snoops ARP traffic,
crafts VIP ARP replies, and dispatches VIP IP packets to backend selection.
Once a backend is chosen, DNAT/SNAT flow rule pairs are installed at priority
200 with configurable timeouts. Normal VIP flows use `VIP_IDLE_TIMEOUT` (30 s)
and `VIP_HARD_TIMEOUT` (120 s); recovery VIP flows use narrower timeouts
(`VIP_DATA_RECOVERY_IDLE_TIMEOUT` 40 s, `VIP_DATA_RECOVERY_HARD_TIMEOUT` 45 s)
to bound recovery-path state. When the DNAT rule expires, the priority-100
punt rule resumes and triggers fresh backend selection.

### Thread 2 -- Telemetry-Fed Selector Updates and Storage Promotion

The ZMQ subscriber callback calls `update_server_stats()` and
`update_storage_stats()` to refresh the per-backend telemetry snapshots that
feed WSM scoring. It also promotes newly observed `SECONDARY` storage nodes
into the appropriate `VIP_DATA` membership set and marks a short storage warm
lease, making the promoted backend eligible for the next fresh storage
selection.

### Thread 3 -- Backend Admission Hooks for Compute Warm Leases

The elasticity manager calls `register_new_server_backend()` after spawning new
edge-server containers, which adds the MAC to `VIP_SERVER`, seeds the backend
IP, and creates a compute warm lease in one controller-side step.

### Edge-Side VIP_DATA Epoch and Recovery Runtime

Separate from the controller, each edge server (`app.py`) manages per-LAN epoch
lifecycle state: a current epoch, retiring epochs, a circuit breaker, and
request-local lease tracking. `AutoReconnect` rotates the current epoch to a
recovery epoch bound to `VIP_DATA_RECOVERY_*`, while background housekeeping
rolls expired recovery epochs back to normal. The controller installs narrow
TCP-port-scoped recovery rules for the recovery VIP path, but recovery
selection does not guarantee a different backend unless the chosen VIP path
differs.

---

## Document Map

| Topic | Document |
| ----- | -------- |
| VIP interception, ARP handling, punt rules, DNAT/SNAT installation, and flow priorities | [VIP Interception and Flow Rules](vip_routing_interception_and_flow_rules.md) |
| Backend selection (WSM scoring), warm leases, and controller lifecycle hooks | [Backend Selection and Warm Leases](vip_routing_backend_selection_and_warm_leases.md) |
| Cross-network forwarding, backend IP/MAC resolution, and router-MAC return path | [Cross-Network Forwarding and Backend Resolution](vip_routing_cross_network_forwarding_and_backend_resolution.md) |
| Edge-side VIP_DATA epochs, recovery rotation, circuit breaker, and housekeeping | [VIP_DATA Edge Epoch and Recovery](vip_data_edge_epoch_and_recovery.md) |

---

## Diagram Map

| Diagram | File |
| ------- | ---- |
| VIP_SERVER routing (client to edge server) | [`diagram/vip_server_routing.drawio`](diagram/vip_server_routing.drawio) |
| VIP_DATA routing (edge server to storage) | [`diagram/vip_data_routing.drawio`](diagram/vip_data_routing.drawio) |

---

## Tier Coverage

VIP routing covers **Tier 0** (direct cross-region read over `VIP_DATA_N*`) and
**Tier 2** (full replica-set member behind the owner LAN's `VIP_DATA`). It does
**not** participate in Tier 1 selective-sync selection. Tier 1 is routed
**client-side** inside the edge-server container: the `cached_collection(...)`
wrapper consults the controller-broadcast `tier1_manifest` and short-circuits
point-lookups on hot document IDs to the local standalone `mongod`; all other
reads and every write fall through to `VIP_DATA_N*` as normal. See the
[Selective Sync Overview](../selective_sync/selective_sync_overview.md).

---

## Current Implementation Reference

| Reference | File |
| --------- | ---- |
| Controller-side VIP routing facade | `source/sdn_controller/vip_routing.py` |
| Controller-side VIP routing internals | `source/sdn_controller/_vip_routing/config.py`, `source/sdn_controller/_vip_routing/state.py`, `source/sdn_controller/_vip_routing/selection.py`, `source/sdn_controller/_vip_routing/flows.py`, `source/sdn_controller/_vip_routing/ingress.py` |
| Controller entry points (MRO, telemetry callback) | `source/sdn_controller/main_n1.py`, `source/sdn_controller/main_n2.py` |
| Edge server VIP_DATA runtime | `source/docker/edge_server/source/vip_data_mongo_runtime.py` |
| Edge server control-plane VIP update route | `source/docker/edge_server/source/control_plane_routes.py` |
| Edge server app and routes | `source/docker/edge_server/source/app.py` |
