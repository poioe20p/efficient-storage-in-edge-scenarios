# Tier 1 Selective Sync — Overview

## Purpose

Selective sync is a middle tier between Tier 0 (cross-region read over `VIP_DATA`) and Tier 2 (full replica-set extension via `rs.add()`). It places a standalone `mongod` container in the **consumer LAN** that holds only the *hot subset* of documents being read cross-region for a given owner LAN, kept current by MongoDB Change Streams with a `$match` filter restricted to those documents. Edge servers short-circuit point-lookup reads to it via a client-side **manifest**; cold reads still flow over `VIP_DATA` to the owner LAN's RS primary.

The decision to promote, reconfigure, or drain a Tier 1 node is made entirely by the **consumer controller** from its local `TelemetrySummary`. There is no cross-controller event protocol — the peer RS primary is discovered via the existing topology PUB/SUB fabric, and the forwarder inside the container connects to the owner primary as an ordinary authenticated client.

Feature-flagged behind `SS_ENABLED` (default `1` = full lifecycle; set `0` for a baseline run where the wrapper still tracks access but never consults Tier 1).

---

## Where it sits in the tier hierarchy

| Tier | What it is | Who decides | Placement |
|---|---|---|---|
| 0 | Cross-region read over `VIP_DATA` — no local copy | VIP routing | Owner LAN RS primary |
| **1** | **Standalone `mongod` + per-collection Change Stream forwarder, `$match`-filtered to a hot doc set** | **Consumer controller — `PromotionCoordinator.evaluate()`** | **Consumer LAN** |
| 2 | Full replica-set member added to the owner RS via `rs.add()` | Storage scale-up in `scaling_policy.py` | Typically same-LAN today (`rs_net{lan}`); cross-LAN variant is future work |

Tier 1 and Tier 2 are **mutually exclusive per `(owner_lan → consumer_lan)` direction** — but only when Tier 2 is itself cross-LAN. See [Lifecycle § Drain signals](#drain-signals) below.

---

## Mechanism

- **Container** — `source/docker/edge_selective_storage/` builds a small image: a `mongod` (no `--replSet`), a Flask admin port, and a supervisor that spawns one `ForwarderWorker` per hot collection. Each worker opens one Change Stream cursor against the owner primary with a `$match` pinned to the hot doc ids for its collection, applies events locally, and persists a resume token to disk for crash recovery.
- **Client-side routing** — `source/docker/edge_server/source/platform_cache.py` wraps every collection access with a `cached_collection(...)` helper. When a point-lookup's `_id` is in the current `tier1_manifest` for `(owner_lan, collection)`, the read is served from the local Tier 1 `mongod` on port `27018`; otherwise it falls through to `VIP_DATA`. Writes always bypass the cache.
- **Promotion decision** — `source/sdn_controller/selective_sync/promotion.py` (`PromotionCoordinator`). Runs once per telemetry window on the consumer-side `_on_telemetry_update` callback. Predicate = sustained QoE breach (M-of-N on `t_db_p95_ms_per_lan[owner_lan]`) ∧ cross-region footprint ≥ `SS_PROMOTION_CROSS_REGION_THRESHOLD` ∧ read-heavy op mix (`write_ratio ≤ SS_WRITE_RATIO_MAX`) ∧ cooldown elapsed.
- **Peer primary resolution** — `topology.resolve_peer_primary(peer_network_id)` joins the cached peer `storage_macs_n*` with the new peer `storage_roles` map (MAC → `"primary"` / `"secondary"` / `""`). Each controller advertises its own LAN's roles in every topology snapshot, populated each window from `TelemetrySummary.storage_servers[*].member_state` via `TopologyMixin.sync_storage_roles(...)`. Selective-sync containers carry `member_state="STANDALONE_CACHE"` → role `""`, so they are never advertised as RS members.

---

## Data path

```
Edge server (consumer LAN)
  └─ cached_collection("sensor_reports").find_one({"_id": "lan1::device-7"})
        │
        ├── manifest knows "lan1::device-7"?
        │       ├─ yes → Tier 1 mongod (local LAN, port 27018)       ← hot
        │       └─ no  → fall through to VIP_DATA → owner RS primary ← cold / writes
        │
        └── access counters + op_counters + time_db_ms_per_lan piggybacked
            onto the edge-server per-request telemetry event.
```

All cross-LAN traffic in the Tier 1 control path is the **data-plane** Change Stream cursor (consumer-side forwarder → owner RS primary on port `27018`). There are no new controller-to-controller control messages.

---

## Lifecycle

State machine per `owner_lan`, owned by `PromotionCoordinator`:

```
NONE ──evaluate()──► SPAWNING ──on_spawned()──► ACTIVE ──delta──► ACTIVE (reconfigure)
                                                   │
                                            drain(reason)
                                                   ▼
                                               DRAINING ──Phase B──► NONE  (cooldown)
```

### Elasticity alerts

Four dataclasses ride the existing elasticity priority queue (no new thread, no new transport):

| Alert | Emitter | Purpose |
|---|---|---|
| `SelectiveSyncAlert` | `PromotionCoordinator._spawn` | Spawn container + register node, then `on_spawned` flips to ACTIVE and broadcasts the first manifest. |
| `SelectiveSyncReconfigureAlert` | Coordinator hot-set delta | Manifest-first rebroadcast, then `POST /forwarder_config` to widen / narrow the `$match` filter live. |
| `ScaleDownSelectiveAlert` | `PromotionCoordinator.drain(...)` | Phase A: revoke manifest, `POST /drain`, record `PendingDrain`. |
| `CleanupSelectiveAlert` | `ControlEventDispatcher` via `elasticity.submit_cleanup(mac)` | Phase B: OVS teardown + `docker rm` after `drain_complete`. |

### Priority ordering

`_ALERT_PRIORITY` in [`elasticity.py`](../../../source/sdn_controller/elasticity/elasticity.py) (lower = higher priority). Tier 2 keeps top priority; Tier 1 sits just below; cleanup alerts sit beside their paired scale-down alerts so a pending Phase B always wins over a fresh scale-down of the same tier. An `itertools.count()` tie-breaker preserves FIFO order within a priority.

| # | Alert | Rationale |
|---|---|---|
| 1 | `DataAlert` | Tier 2 full-replica scale-up — supersedes Tier 1. |
| 2 | `SelectiveSyncAlert` | Tier 1 promotion. |
| 3 | `SelectiveSyncReconfigureAlert` | Live filter update on an ACTIVE Tier 1 node. |
| 4 | `ComputeAlert` | Edge-server scale-up. |
| 5 | `CleanupComputeAlert` | Compute Phase B. |
| 6 | `CleanupSelectiveAlert` | Tier 1 Phase B. |
| 7 | `CancelComputeDrainAlert` | Lower-priority compute drain cancel submitted after compute scale-up. |
| 8 | `ScaleDownDataAlert` | Tier 2 teardown. |
| 9 | `ScaleDownSelectiveAlert` | Tier 1 Phase A. |
| 10 | `ScaleDownComputeAlert` | Compute Phase A. |

### Two-phase teardown

Tier 1 reuses the existing compute drain pattern — no new threads, no new event types, no new dispatcher methods.

**Phase A** — `_handle_scale_down_selective`:

1. Broadcast manifest revocation (`host: null`, `collections: {}`) so edge servers stop routing reads to the container *before* the forwarder closes its Change Streams.
2. `POST /drain` on the supervisor's Flask admin port (5001) with a 2 s timeout. Returns 202.
3. Record a `PendingDrain(mac, veth="", container_name, lan, initiated_ts, drain_signaled, ip, node_type="selective_storage")` in `ElasticityManager._pending_drains`.
4. If the drain HTTP call fails (timeout, non-2xx, connection refused), submit `CleanupSelectiveAlert` immediately instead of waiting for the `drain_complete` event.

**Phase B** — `_handle_cleanup_selective`:

1. Triggered either by `ControlEventDispatcher.process_drain_events` calling `elasticity.submit_cleanup(mac)` (routed on `PendingDrain.node_type` → `CleanupSelectiveAlert`), or by the existing telemetry-window timeout fallback.
2. Call `SelectiveStorageNodeAdder.remove_selective_storage_node(...)` — OVS port/veth cleanup via `remove_network_storage_node.sh --skip-rs` (Tier 1 is never in the VIP pool; no DNAT flush needed).
3. Release the IP from the allocator, clear `_pending_drains[mac]`, notify Thread 2 via `_removal_complete_macs`.

**Supervisor-side drain** (`edge_selective_storage/admin.py::POST /drain`):

1. Return `202 Accepted` immediately; the rest runs on a daemon thread named `drain`.
2. Under `_workers_lock`, stop every `ForwarderWorker` — this persists a final resume token for every collection, so the next promotion of the same owner region can tail from the last applied change.
3. Emit a `drain_complete` control-event frame via `telemetry.emit_control_event("drain_complete", server_id=...)`.
4. `MongoClient("mongodb://localhost:27018/").admin.command({"shutdown": 1})` — clean `mongod` shutdown.

Workers stop *before* `mongod` exits, guaranteeing final resume-token persistence even when the container is about to be removed.

### `submit_cleanup` dispatch

`ElasticityManager.submit_cleanup(mac)` is the single Phase B entry point. It looks up `_pending_drains[mac].node_type` and submits either `CleanupComputeAlert` or `CleanupSelectiveAlert`; unknown MACs fall back to `CleanupComputeAlert` with a warning so a stray `drain_complete` event can't wedge the queue. [`control_events.py::process_drain_events`](../../../source/sdn_controller/control_events.py) calls it directly — one dispatch site handles both tiers.

### Drain signals

All drain paths go through the same `PromotionCoordinator.drain(owner_lan, reason)` entry point.

| Signal | Condition | Source |
|---|---|---|
| Cold-set | Every collection in the hot set has been below `SS_SCALEDOWN_THRESHOLD` cross-region hits for `SS_SCALEDOWN_WINDOW` consecutive windows. Partial cold sets trigger a shrink-reconfigure instead. | `hotness.merge_edge_access` + per-collection `cold_windows` ring on `_Entry`. |
| Staleness | *Any* collection's Change Stream `lag_s` exceeds `SS_STALENESS_LIMIT_S`. Shared `mongod` + shared remote connection means one bad lag implicates all collections. | `StorageServerSummary.selective_sync_per_collection` (last-writer-wins per collection). |
| Tier 2 supersedes **(dormant)** | A **cross-LAN** `DataAlert` fires for the same direction while Tier 1 is ACTIVE. `DataAlert` today is always same-LAN (`cross_lan_rs=False`, `owner_lan=None`); the supersede hook in `main_n*.py` is inert until a cross-LAN RS variant exists. | `main_n*.py` at the scale-up submission loop, guarded on `alert.cross_lan_rs and alert.owner_lan is not None`. |

All three paths set `entry.cooldown_until = now + SS_COOLDOWN_S` and clear the M-of-N breach ring so stale history can't short-circuit the next promotion cycle.

#### Tier 2 supersede hook (dormant)

The third drain signal is wired but dormant: today `DataAlert` is always *same-LAN* (adds a secondary to `rs_net{lan}` in the consumer's own LAN), and a same-LAN secondary does **not** replace a Tier 1 node — they address different axes (local CPU/IO headroom vs cross-LAN read offload). Draining Tier 1 on every `DataAlert` would be incorrect.

The supersede relationship only holds when the Tier 2 scale-up is itself cross-LAN — i.e. the `DataAlert` extends the replica set *across* LANs, placing a secondary of the owner RS into the consumer LAN. That variant does not exist in the current codebase; it is future work on the `DataAlert` axis.

The hook is therefore guarded on a `cross_lan_rs: bool = False` flag plus an `owner_lan: str | None = None` field on `DataAlert`, both defaulting to values that make the guard False for every alert emitted today:

```python
# main_n*.py — at the scale-up submission loop
if (isinstance(alert, DataAlert)
        and getattr(alert, "cross_lan_rs", False)
        and getattr(alert, "owner_lan", None) is not None):
    self._selective_sync_coordinator.drain(
        alert.owner_lan, reason="tier2_supersedes")
self._elasticity.submit(alert)
```

`PromotionCoordinator.drain()` is idempotent and safe to call even if the guard ever lets a spurious alert through — it short-circuits on `_State.NONE`. Cold-set and staleness remain the only drain signals that fire today.

---

## Manifest

When the coordinator reaches ACTIVE (via `on_spawned()`) or after a successful reconfigure, it calls the `broadcast_tier1_manifest` closure in `main_n*.py`, which `PUT`s the manifest to every edge server in the consumer LAN. Revocation is performed by the elasticity manager directly in `_handle_scale_down_selective` during Phase A teardown.

The edge server exposes `PUT /tier1_manifest` ([`app.py`](../../../source/docker/edge_server/source/app.py)). The body is keyed by `owner_lan` and lists every hot collection served by the corresponding Tier 1 node:

```json
{
    "owner_lan": "lan1",
    "host": "10.0.1.10:27018",
    "collections": {
        "sensor_reports":  ["lan1::device-7", "lan1::device-42"],
        "device_registry": ["lan1::device-7"]
    }
}
```

`host: null` or `collections: {}` revokes the manifest and closes the per-owner `MongoClient` on the edge server. Handler: `platform_cache.set_tier1_manifest()`.

---

## Config knobs

Controller-side (`source/sdn_controller/scaling_config.py`):

| Knob | Role |
|---|---|
| `SS_ENABLED` | Master switch. `0` = baseline (wrapper runs but never consults Tier 1); `1` = full lifecycle enabled. |
| `SS_PROMOTION_CROSS_REGION_THRESHOLD` | Fraction of reads served cross-region before a collection is promotion-eligible. |
| `SS_WRITE_RATIO_MAX` | Max `writes / (reads + writes)` on a candidate collection. Tier 1 replicates reads only. |
| `SS_MIN_READS_PER_WINDOW` | Absolute read-count floor before the cross-region ratio is trusted. |
| `SS_HOT_DOC_LIMIT` | Controller-side cap on hot doc ids per `(owner_lan, collection)` after merging all edge frames. |
| `SS_STALENESS_LIMIT_S` | Change Stream lag ceiling — exceeded on any collection → teardown. |
| `SS_SCALEDOWN_THRESHOLD` / `SS_SCALEDOWN_WINDOW` | Cold-window accounting per collection. |
| `SS_COOLDOWN_S` | Post-teardown dwell time before the same `(owner_lan)` can be promoted again. |
| `SS_BREACH_WINDOWS_N` / `SS_BREACH_WINDOWS_M` | M-of-N debounce on the sustained-QoE-breach gate (defaults 2-of-5). |
| `SS_MAX_TTL_S` | Optional cached-doc TTL; `0` disables. Belt-and-suspenders guard against forwarder stalls. |

> **Testbed note — WAN emulation.** The breach gate compares peer-LAN p95 to
> `TAU_DADOS_MS` (default `65 ms` in [`edge_server/source/app.py`](../../../source/docker/edge_server/source/app.py)
> and [`selective_sync/hotness.py`](../../../source/sdn_controller/selective_sync/hotness.py)).
> The lab raw inter-LAN path is ~5–15 ms, so Tier 1 stays silent unless the
> nat-router applies `tc netem` shaping. Bringup defaults to the `metro`
> profile (`WAN_RTT_MS=10 ms`); see
> [Topology — WAN Emulation](../topology/topology_overview.md#wan-emulation-inter-lan-latency).

Edge-side (`source/docker/local_state_server/aggregator.py`):

| Knob | Role |
|---|---|
| `SS_TOP_DOCS_PER_EDGE` | Per-edge cap on doc-id count per `(owner_lan, collection)` in an outgoing telemetry frame. |

---

## Coordinator state probe

Each telemetry window the controller emits a coordinator-state snapshot via a dedicated ZMQ PUB socket so external observers (the resource-stats collector, log-analysis scripts) can see the live state machine without parsing controller logs.

- Bound on `tcp://*:${COORDINATOR_STATE_PUB_PORT}` (`5561` for `lan1`, `5562` for `lan2` per [`build_network_setup.sh`](../../../source/scripts/build_network_setup.sh); `0` disables).
- One frame per window, published immediately after `PromotionCoordinator.evaluate(summary)` in `main_n*.py`.
- Frame schema (JSON):

  ```json
  {
    "network_id": "lan1",
    "window_end": 1777064910.123,
    "owners": {
      "lan1": {
        "state": "NONE",
        "breach_ring_filled": 0,
        "breach_ring_capacity": 5,
        "cooldown_remaining_s": 0.0,
        "hot_collections": [],
        "hot_doc_total": 0,
        "container": null
      }
    }
  }
  ```

- Implementation: [`source/sdn_controller/selective_sync/state_publisher.py`](../../../source/sdn_controller/selective_sync/state_publisher.py) (`Tier1OwnerState`, `CoordinatorStatePublisher`) + `PromotionCoordinator.snapshot()`.
- Consumer: [`source/scripts/testing/collect_resource_stats.py`](../../../source/scripts/testing/collect_resource_stats.py) merges the latest frame per `network_id` into each row of `resource_stats.csv` via the helpers in [`tier1_stats.py`](../../../source/scripts/testing/tier1_stats.py). In that CSV contract, `tier1_lifecycle_active_count` is derived from `Tier1OwnerState.state == "ACTIVE"`, while `tier1_active_count` remains the supply-side reporting count derived from `selective_sync_per_collection`. See [`testing/testing_overview.md`](../testing/testing_overview.md) for the full CSV column list.

---

## See also

- Coordinator — [`source/sdn_controller/selective_sync/promotion.py`](../../../source/sdn_controller/selective_sync/promotion.py)
- Hotness reducers — [`source/sdn_controller/selective_sync/hotness.py`](../../../source/sdn_controller/selective_sync/hotness.py)
- Supervisor / forwarder — [`source/docker/edge_selective_storage/`](../../../source/docker/edge_selective_storage/)
- Edge-server wrapper — [`source/docker/edge_server/source/platform_cache.py`](../../../source/docker/edge_server/source/platform_cache.py)
- Telemetry model extensions (`ServerSummary.access`, `t_db_p95_ms_per_lan`, `op_counters`, `StorageServerSummary.selective_sync_per_collection`) — [`telemetry/telemetry_overview.md`](../telemetry/telemetry_overview.md)
- Topology `storage_roles` + `resolve_peer_primary` — [`topology/topology_overview.md`](../topology/topology_overview.md)
- VIP routing overview (Tier 0 path) — [`vip_routing/vip_routing_overview.md`](../vip_routing/vip_routing_overview.md)
- Elasticity Manager overview — [`elasticy_manager/elasticity_overview.md`](../elasticy_manager/elasticity_overview.md)
