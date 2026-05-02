# Elasticity & Placement Manager — Overview

## Purpose

The Elasticity Manager (Thread 3) is responsible for mutating the infrastructure
in response to latency breaches and underutilisation signals detected by Thread 2.
It handles spawning **and gracefully removing** `edge_server` and
`edge_storage_server` containers at runtime and wiring/unwiring them from the
running network.

---

## Architecture: Three-Thread Interaction

```
Thread 2 (Observer/ZMQ)     Thread 3 (Elasticity Mgr)      Infrastructure
       │                              │
       │── Alert(type, lan) ────────►│
       │                              │── NodeAdder.add_edge_server()
       │                              │      ├─ docker run           (timed)
       │                              │      ├─ add_network_node.sh  (timed)
       │                              │      └─ returns NodeResult (ip, mac, timings)
       │                              │
       │                              │── TopologyMixin.add_server_mac()
       │                              │── TopologyMixin.register_backend_ip()
       │                              │      └─ Thread 1 picks up the new server via VIP pool
```

- **Thread 1** (SDN controller main loop) — handles OpenFlow events, reactive
  L2 learning, and VIP routing. Never touches Thread 3 directly; it reads the
  shared VIP pool that Thread 3 mutates through `TopologyMixin`.
- **Thread 2** (`ZmqTelemetrySource`) — subscribes to aggregator and peer
  topology ZMQ endpoints, receives `TelemetrySummary` updates, caches the most
  recent peer-domain summary, evaluates local thresholds, and posts typed
  `Alert` objects to Thread 3's queue.
- **Thread 3** (`ElasticityManager`) — a long-lived daemon thread blocking on a
  `queue.PriorityQueue`. Pops alerts in priority order (storage scale-up first)
  and dispatches them to the appropriate handler, which calls `NodeAdder` for
  the actual container lifecycle.

---

## File Layout

```
source/sdn_controller/
├── main_n1.py                    # Controller entry point — instantiates ElasticityManager,
│                                 #   posts alerts from Thread 2 callback
├── scaling_config.py             # Environment-backed compute/storage thresholds and cooldowns
├── scaling_policy.py             # Thread 2 decision engine — sliding windows, adaptive thresholds, peer-aware compute bias
├── vip_routing.py                # Thread 1 VIP_SERVER / VIP_DATA selection and DNAT/SNAT flow installation
├── elasticity/
│   ├── __init__.py
│   ├── elasticity.py             # ElasticityManager — Thread 3 queue/dispatch
│   ├── node_common.py            # Shared types (NodeResult, RemovalResult, NodeInfo, …),
│   │                             #   constants (SCRIPTS_DIR), and _BaseNodeAdder helpers
│   ├── compute_node_manager.py   # ComputeNodeAdder — edge_server lifecycle + drain phases
│   └── storage_node_manager.py   # StorageNodeAdder — edge_storage_server lifecycle + rs.remove()
└── topology/
    └── topology.py               # TopologyMixin — VIP pool (add_server_mac, add_storage_mac, etc.)

source/scripts/network/
├── add_network_node.sh               # Attaches a running container to OVS LAN (veth + IP/MAC)
│                                     #   Used for both compute AND storage nodes
├── remove_network_node.sh            # Compute node teardown: docker stop + flow flush + OVS/veth cleanup + docker rm
└── remove_network_storage_node.sh    # Storage node teardown: docker stop + flow flush + OVS/veth + docker rm + volume rm
```

---

## Sequence Diagrams

- [Compute scale-up sequence](./diagrams/compute_scale_up.drawio) - threshold trigger to queue dispatch, node creation, and VIP registration.
- [Compute scale-down sequence](./diagrams/compute_scale_down.drawio) - underutilisation trigger, drain phase, cleanup event, and final teardown.
- [Storage scale-up sequence](./diagrams/storage_scale_up.drawio) - predictive threshold trigger, node creation, async replica-set join, and deferred VIP data promotion.
- [Storage scale-down sequence](./diagrams/storage_scale_down.drawio) - VIP isolation, replica-set removal, teardown script, and allocator release.
- [Tier 1 scale-up sequence](./diagrams/tier1_scale_up.drawio) - selective-sync promotion, local cache provisioning, and manifest fan-out to consumer edge servers.
- [Tier 1 scale-down sequence](./diagrams/tier1_scale_down.drawio) - manifest-first isolation, async drain completion, cleanup, and fallback to VIP_DATA.

---

## Alert Types

Produced by Thread 2's `_on_telemetry_update` callback in `main_n1.py`, consumed
by Thread 3.

| Alert                     | Trigger                                          | Fields                                                                                                     |
| ------------------------- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------- |
| `ComputeAlert`          | Adaptive compute threshold with peer-aware bias (3-of-5 window, 45 s compute scale-up cooldown) | `lan`, `network_id`                                                                                    |
| `DataAlert`             | Adaptive storage threshold (see below)           | `lan`, `network_id`, `rs_name`, `primary_container`, `port`                                      |
| `ScaleDownComputeAlert` | Underutilisation (7-of-12 window) or timeout     | `lan`, `network_id`, `container_name`, `mac`, `ip`                                               |
| `ScaleDownDataAlert`    | Underutilisation (7-of-12 window) or timeout     | `lan`, `network_id`, `container_name`, `mac`, `ip`, `rs_name`, `primary_container`, `port` |
| `CleanupComputeAlert`   | `drain_complete` ZMQ event / telemetry timeout | `mac`                                                                                                    |

Alert dispatch uses a `PriorityQueue` — storage scale-up has highest priority
(1), compute scale-up next (2), then cleanup (3), storage removal (4), and
compute removal (5). Tie-breaking uses a monotonic sequence counter for FIFO
within the same priority.

### Scale-Up Degradation Score

Scale-up computes a weighted degradation score per tier:

- **Storage:** `score = 0.7 × cpu_component + 0.3 × latency_component` (CPU-dominant
  — scaling directly reduces CPU contention, while T_db only drops indirectly
  because `directConnection=True` means each edge server runs the same query
  regardless of how many storage nodes exist).
- **Compute:** `score = 0.4 × cpu_component + 0.6 × latency_component`.

Each component is normalised as `max(0, value − floor) / span`.

**Compute** now uses a **local-first adaptive threshold** with a small
peer-health bias:

`effective_τ_compute = min(base + dynamic_compute_count × increment + peer_relief, max_threshold)`

with runtime defaults:

- `base = 0.30`
- `increment = 0.10`
- `max_threshold = 0.55`
- `peer_relief = 0.03` only when the cached peer compute score is `≤ 0.35`
- `T_proc` scoring band recalibrated to `1.5–4.5 ms` (`floor=1.5`, `span=3.0`)
- `CPU` scoring band recalibrated to `45–90 %` (`floor=45`, `span=45`)
- compute trigger requires **3 of the last 5** windows
- after a compute scale-up, compute scale-up evaluation is suppressed for **45 s**
- hard cap: **4 dynamic compute nodes** per LAN

If the peer `DomainSummary` is unavailable, `peer_relief = 0` and the decision
falls back to purely local adaptive compute scaling.

**Storage** scale-up uses a **diminishing-increment adaptive threshold** (see
[§ Diminishing-Increment Storage Threshold](#diminishing-increment-adaptive-storage-threshold)):
each successive dynamic storage node raises the effective threshold by an increment that
halves with every node added (floored at a minimum), so early nodes face a rapidly rising
bar while later nodes face a near-flat ceiling. Trigger requires **2 of the last 5**
windows. A 120 s cooldown suppresses further storage scale-up evaluation after each
trigger. The latency component is tail-aware: Thread 2 scores storage against
`max(avg_time_db_ms, p95_time_db_ms)` so sustained tail growth can trigger Tier 2
before the mean fully rises. Hard cap: **5 dynamic storage nodes** per LAN.

### Peer-aware compute scaling and VIP spillover

The compute policy remains **per LAN** because the scale-up action is local:
LAN1 spawns in LAN1 and LAN2 spawns in LAN2. The peer LAN is used only as a
small threshold bias when it is healthy enough to act as a real spillover path.

This scaling logic is paired with a VIP_SERVER routing recalibration in Thread 1.
`vip_routing.py` reduces `W_HOPS` from `0.40` to `0.28`, making cross-LAN
server selection more willing when the local server is clearly more loaded.
Without that routing change, peer-aware compute relief would be much less useful
because the local server would remain too sticky.

### Scale-Down Sliding Window

Scale-down uses a separate sliding window per tier. Both CPU and latency must
be below threshold simultaneously for a window to count as "idle" (AND-gate —
prevents false positives from data-bound latency spike7 of the last 12s when
7 of the last 12 windows are idle; storage fires when 7 of the last 12 windows
are idle. Windows where latency exceeds a timeout ceiling (default 5 000 ms)
are treated as indeterminate and skipped — preventing RS election or connectivity
timeouts from poisoning the signal.

**Instrumentation (from `implementation/scale_down_instrumentation.md`).**
Each evaluation emits a single DEBUG line carrying all predicate inputs
(`cpu`, `proc`/`db`, `below`, `hits/required`, `armed`); a one-shot INFO
line is emitted on the rising edge of `armed`. Behaviour of the predicate
is unchanged. Log grammar is defined as a stable contract consumed by the
analysis toolchain (`cli_scale_down`).

### Anti-Thrashing Mechanisms

Seven mechanisms prevent scale-up / scale-down thrashing:

| Mechanism                 | Description |
| ------------------------- | ----------- |
| Active + pending-drain gates | Active Thread 3 handlers block all scaling evaluation. Pending drains still block scale-down globally, but scale-up is target-specific: pending compute drains block only compute scale-up, and pending Tier 1 selective drains block neither compute nor storage scale-up |
| Sliding window            | Requires sustained signal (not single-window spikes) |
| Cross-direction reset     | Scale-up clears the scale-down window (and vice versa) |
| Compute scale-up cooldown | After compute scale-up: suppress further compute scale-up evaluation for 45 s |
| Per-tier cooldowns        | After scale-up: storage 120 s / compute 40 s before scale-down resumes |
| Birth grace               | Newly added nodes skip absent-node detection for 60 s during bootstrap |
| Hard caps                 | `MAX_DYNAMIC_STORAGE=5` / `MAX_DYNAMIC_COMPUTE=4` per LAN — structurally prevents container-saturation death spiral |

### Environment Variables

Thresholds are configured via environment variables (scale-up vars prefixed
with `SCALEUP_` to avoid collision with VIP routing weights):

**Scale-up (weighted degradation score)**

| Variable                      | Default  | Description                                                                                         |
| ----------------------------- | -------- | --------------------------------------------------------------------------------------------------- |
| `SCALEUP_W_CPU`             | `0.40` | Compute score: CPU weight                                                                           |
| `SCALEUP_W_T_PROC`          | `0.60` | Compute score: T_proc weight                                                                        |
| `SCALEUP_CPU_FLOOR`         | `45`   | Compute CPU: below this → 0 contribution                                                           |
| `SCALEUP_CPU_SPAN`          | `45`   | Compute CPU: normalisation range (45 + 45 = 90 % saturation)                                        |
| `SCALEUP_T_PROC_FLOOR`      | `1.5`  | T_proc (ms): below this → 0 contribution                                                           |
| `SCALEUP_T_PROC_SPAN`       | `3.0`  | T_proc (ms): main compute-latency scoring range (1.5 + 3.0 = 4.5 ms saturation)                    |
| `SCALEUP_COMPUTE_BASE_THRESHOLD` | `0.30` | Adaptive compute base threshold                                                                   |
| `SCALEUP_COMPUTE_THRESHOLD_INCREMENT` | `0.10` | Per-dynamic-compute-node threshold increment                                                 |
| `SCALEUP_COMPUTE_MAX_THRESHOLD` | `0.55` | Adaptive compute threshold cap                                                                    |
| `SCALEUP_COMPUTE_COOLDOWN_S` | `45` | Post-scale-up compute cooldown before next compute scale-up evaluation (s)                           |
| `SCALEUP_COMPUTE_PEER_RELIEF` | `0.03` | Extra threshold bias when the peer LAN is healthy enough to absorb spillover                      |
| `SCALEUP_COMPUTE_PEER_HEALTH_THRESHOLD` | `0.35` | Peer compute score at or below this enables `peer_relief`                                  |
| `SCALEUP_WINDOW_SIZE`       | `5`    | Sliding window size (compute only)                                                                  |
| `SCALEUP_REQUIRED`          | `3`    | Required degraded windows (compute only)                                                            |
| `SCALEUP_W_STORAGE_CPU`     | `0.7`  | Storage score: CPU weight (dominant — scaling fixes CPU contention)                                  |
| `SCALEUP_W_T_DB`            | `0.3`  | Storage score: T_db weight (secondary contention indicator)                                          |
| `SCALEUP_STORAGE_CPU_FLOOR` | `45`   | Storage CPU: below this → 0 contribution                                                           |
| `SCALEUP_STORAGE_CPU_SPAN`  | `45`   | Storage CPU: normalisation range (45 + 45 = 90 % saturation)                                        |
| `SCALEUP_T_DB_FLOOR`        | `15`   | T_db (ms): below this → 0 contribution                                                             |
| `SCALEUP_T_DB_SPAN`         | `50`   | T_db (ms): normalisation range (15 + 50 = 65 ms saturation)                                         |
| `MAX_DYNAMIC_COMPUTE`      | `4`    | Hard cap: max dynamic compute nodes per LAN                                                          |
| `MAX_DYNAMIC_STORAGE`      | `5`    | Hard cap: max dynamic storage nodes per LAN (MongoDB ≤ 7 voting members)                            |
Diminishing-increment storage scale-up threshold** (see [§ Diminishing-Increment Storage Threshold](#diminishing-increment-adaptive-storage-threshold))

| Variable                                | Default  | Description                                                      |
| --------------------------------------- | -------- | ---------------------------------------------------------------- |
| `SCALEUP_STORAGE_BASE_THRESHOLD`      | `0.35` | Adaptive base threshold for storage scale-up                     |
| `SCALEUP_STORAGE_THRESHOLD_INCREMENT` | `0.15` | Starting per-node increment (halves with each additional node)   |
| `SCALEUP_STORAGE_MIN_INCREMENT`       | `0.05` | Floor for the per-node increment                                 |
| `SCALEUP_STORAGE_MAX_THRESHOLD`       | `0.70` | Adaptive threshold cap                                           |
| `SCALEUP_STORAGE_WINDOW_SIZE`         | `5`    | Sliding window size (storage only)                               |
| `SCALEUP_STORAGE_REQUIRED`            | `2`    | Required degraded windows (storage only)                         |
| `SCALEUP_STORAGE_COOLDOWN_S`          | `120`  | Post-scale-up cooldown before next storage scale-up (s)                   |
| `SCALEUP_STORAGE_REQUIRED`            | `2`    | Required degraded windows (storage only)                         |
| `SCALEUP_STORAGE_COOLDOWN_S`          | `120`  | Post-scale-up cooldown before next storage scale-up (s)          |

**VIP_SERVER routing weights**

| Variable | Default | Description |
| -------- | ------- | ----------- |
| `W_CPU` | `0.3` | CPU contribution to VIP_SERVER backend cost |
| `W_RAM` | `0.1` | RAM contribution to VIP_SERVER backend cost |
| `W_REQUESTS` | `0.2` | Request-count contribution to VIP_SERVER backend cost |
| `W_HOPS` | `0.28` | Hop-cost contribution to VIP_SERVER backend cost |

**Scale-down**

| Variable                               | Default  | Description                                          |
| -------------------------------------- | -------- | ---------------------------------------------------- |
| `TAU_CPU_DOWN`                       | `65`   | Domain avg storage CPU below → storage idle         |
| `TAU_DB_DOWN_MS`                     | `100`  | Domain avg DB latency below → storage idle          |
| `SCALE_DOWN_COMPUTE_WINDOW_SIZE`     | `12`   | Sliding window size for compute scale-down           |
| `SCALE_DOWN_COMPUTE_REQUIRED`        | `7`    | Required below-threshold windows (compute)           |
| `SCALE_DOWN_STORAGE_WINDOW_SIZE`     | `12`   | Sliding window size for storage scale-down           |
| `SCALE_DOWN_STORAGE_REQUIRED`        | `7`    | Required below-threshold windows (compute)           |
| `SCALE_DOWN_STORAGE_WINDOW_SIZE`     | `12`   | Sliding window size for storage scale-down           |
| `SCALE_DOWN_STORAGE_REQUIRED`        | `7`    | Required below-threshold windows (storage)           |
| `SCALE_DOWN_PROC_TIMEOUT_CEILING_MS` | `5000` | Proc latency above → indeterminate window           |
| `SCALE_DOWN_DB_TIMEOUT_CEILING_MS`   | `5000` | DB latency above → indeterminate window             |
| `TELEMETRY_TIMEOUT_WINDOWS`          | `18`   | Absent windows before dead-node removal (180 s raw absence tolerance; dynamic nodes don't heartbeat, so this is the sole failure detector for them) |
| `SCALEDOWN_STORAGE_COOLDOWN_S`       | `120`  | Post-scale-up cooldown before storage scale-down (s) |
| `SCALEDOWN_COMPUTE_COOLDOWN_S`       | `40`   | Post-scale-up cooldown before compute scale-down (s) |
| `NODE_BIRTH_GRACE_S`                 | `60`   | Skip absent-node detection during node bootstrap (s) |

---

## Tier 1 Selective Sync

Tier 1 selective sync promotes a hot subset of documents from a remote LAN's
replica set to a local `edge_selective_storage` container whenever sustained
cross-region latency breaches `TAU_DADOS_MS`. It is orthogonal to the
compute / storage scale-up paths above: rather than adding capacity, it moves
read traffic to a closer node. Implemented and feature-flagged behind
`SS_ENABLED` (default `0`).

Four new alert dataclasses share the existing Thread 2 → Thread 3 priority
queue — no new transport, no new thread:

| Alert | Phase | Handler |
|---|---|---|
| `SelectiveSyncAlert` | spawn | `_handle_selective_sync` → `SelectiveStorageNodeAdder.add_selective_storage_node` |
| `SelectiveSyncReconfigureAlert` | live update | `_handle_selective_sync_reconfigure` → manifest broadcast + `POST /forwarder_config` |
| `ScaleDownSelectiveAlert` | teardown Phase A | `_handle_scale_down_selective` → revoke manifest, `POST /drain`, record `PendingDrain` |
| `CleanupSelectiveAlert` | teardown Phase B | `_handle_cleanup_selective` → OVS teardown + `docker rm` on `drain_complete` |

Teardown reuses the compute drain pattern: the supervisor emits
`drain_complete` from its `POST /drain` handler, the existing
`ControlEventDispatcher.process_drain_events` calls
`elasticity.submit_cleanup(mac)`, and the generalized dispatcher routes by
`PendingDrain.node_type`.

### Wiring into `main_n*.py`

The Tier 1 lifecycle is driven by a **consumer-side** `PromotionCoordinator`
(`source/sdn_controller/selective_sync/promotion.py`). It is not part of the
elasticity manager but is wired into it at startup via two setters on
`ElasticityManager`:

- `attach_selective_sync_coordinator(coordinator)` — lets
  `_handle_selective_sync` call `coordinator.on_spawned(...)` after a
  successful spawn (`SPAWNING → ACTIVE`) and `coordinator.drain(..., reason="spawn_failed")`
  on a failure, without the coordinator needing to exist when
  `ElasticityManager` is constructed.
- `attach_tier1_broadcaster(broadcast_fn)` — injects the HTTP manifest
  broadcast closure (`PUT /tier1_manifest` against every local edge server)
  used by the coordinator on promotion, reconfigure, and drain.

`main_n*.py` then calls `coordinator.evaluate(summary)` from
`_on_telemetry_update` immediately after `sync_storage_roles(...)`, so the
coordinator runs once per consumer-side telemetry window with fresh peer
role information.

### Dormant Tier 2 supersede hook

Tier 1 and Tier 2 are mutually exclusive per `(owner_lan → consumer_lan)`
direction **only when Tier 2 is itself cross-LAN**. Today `DataAlert` is
always same-LAN (adds a secondary to `rs_net{lan}`) and ships with
`cross_lan_rs=False`, `owner_lan=None`. At the scale-up submission loop in
`main_n*.py` each `DataAlert` is checked:

```python
if (isinstance(alert, DataAlert)
        and getattr(alert, "cross_lan_rs", False)
        and getattr(alert, "owner_lan", None) is not None):
    self._selective_sync_coordinator.drain(alert.owner_lan, reason="tier2_supersedes")
self._elasticity.submit(alert)
```

The branch is inert with today's code — no existing producer emits a
cross-LAN `DataAlert`. It is in place so that a future cross-LAN RS variant
correctly drains any Tier 1 node for the same direction *before* the Tier 2
spawn lands. See [`selective_sync_overview.md` — Tier 2 supersede hook](../selective_sync/selective_sync_overview.md#tier-2-supersede-hook-dormant).

Full subsystem write-up — promotion predicate, state machine, priority
ordering, two-phase teardown, manifest protocol, and config-knob rationale —
is in [`selective_sync/selective_sync_overview.md`](../selective_sync/selective_sync_overview.md).
Source: [`source/sdn_controller/selective_sync/`](../../../source/sdn_controller/selective_sync/)
and [`source/docker/edge_selective_storage/`](../../../source/docker/edge_selective_storage/).

With `SS_ENABLED=0` the edge-server `cached_collection` wrapper and
telemetry enrichment still run, but no manifest is ever broadcast — behaviour
is identical to baseline.

### Selective-sync knobs

| Variable                     | Default | Purpose                                                                                                     |
| ---------------------------- | :-----: | ----------------------------------------------------------------------------------------------------------- |
| `SS_ENABLED`               |  `0`  | Master switch for the whole subsystem. `0` disables promotion; wrapper remains active but no-op.          |
| `SS_HOT_DOC_LIMIT`         |  `50` | Final cap on hot-doc list after merging per-edge `top_docs` across all edges in a consumer LAN.           |
| `SS_MIN_READS_PER_WINDOW`  |  `30` | Floor on total reads for (`owner_lan`, `coll`) before a promotion can fire — filters trivial bursts. |
| `SS_WRITE_RATIO_MAX`       | `0.30`  | Upper bound on write ratio for (`owner_lan`, `coll`); above this, promotion is blocked.                 |
| `SS_TOP_DOCS_PER_EDGE`     |  `30` | Per-edge cap on `top_docs` list shipped in each `ServerSummary.access` entry (set on the aggregator).   |
| `TAU_DADOS_MS`             | `65`    | Per-LAN p95 latency threshold; single deployment knob shared by edge server and controller.               |

---

## Implementation Plans

- [`implementation/metric_drivers_investigation_plan.md`](implementation/metric_drivers_investigation_plan.md)
  — umbrella investigation into what actually drives CPU / T_db / T_proc.
- [`implementation/scale_down_instrumentation.md`](implementation/scale_down_instrumentation.md)
  — DEBUG/INFO observability for the scale-down decision path.
- [`implementation/scaling_threshold_tuning_and_caps.md`](implementation/scaling_threshold_tuning_and_caps.md)
  — threshold tuning and hard-cap rationale (existing).

> Scale-down evaluation transitions are observable via the DEBUG/INFO log
> lines specified in [`implementation/scale_down_instrumentation.md`](implementation/scale_down_instrumentation.md).

---

## Node Addition

### Container Naming

Dynamic containers are named using a per-network sequence counter:
`{prefix}_{network_id}_dyn{counter}` — e.g. `edge_server_lan1_dyn1`,
`edge_storage_lan2_dyn3`.

### IP/MAC Allocation

The `IpAllocator` class (in `node_common.py`) pre-assigns IP and MAC from
Python, eliminating the O(N) container scan that the shell script previously
performed. Each LAN has its own allocator (lazy-created on first use).
Dynamic nodes use suffixes 6–55 (`10.0.{lan-1}.{suffix}`), with MACs derived
deterministically: `00:00:00:00:{lan:02x}:{suffix:02x}`. Released IPs are
returned to the pool for reuse.

### Lifecycle: `ComputeNodeAdder` / `StorageNodeAdder`

Each public method is a self-contained, timed, idempotent lifecycle. Every step
is individually timed with `time.perf_counter()`.

#### `add_edge_server(lan, name, ip, mac)`

| Step | Operation                                                                                              | On failure                           |
| ---- | ------------------------------------------------------------------------------------------------------ | ------------------------------------ |
| 1    | `docker run -dit --network none --name <name> -e LAN_ID=lan<N> -e CONTAINER_NAME=<name> edge_server` | Return `FAILED`                    |
| 2    | `add_network_node.sh --lan <N> --name <name> --ip <ip> --mac <mac>`                                  | Cleanup container, return `FAILED` |

#### `add_storage_node(lan, name, rs_name, port, ip, mac)`

RS join (`rs.add()`) is handled asynchronously by the `mongo_telemetry.py`
sidecar inside the container, with 5-attempt retry/exponential backoff. The
primary IP is derived from LAN topology convention (`10.0.{lan-1}.4`).

| Step        | Operation                                                                                                                                                                                                      | On failure                                    |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| 1           | `docker run -dit --network none --name <name> -v <name>-data:/data/db -e LAN_ID=lan<N> -e MONGO_REPLSET=<rs> -e MONGO_PORT=<port> -e RS_ADD_SELF=true -e RS_SEED_HOST=<primary_ip:port> edge_storage_server` | Return `FAILED`                             |
| 2           | `add_network_node.sh --lan <N> --name <name> --ip <ip> --mac <mac>`                                                                                                                                          | Cleanup container + volume, return `FAILED` |
| *(async)* | Sidecar `_rs_self_join()` runs inside container: `rs.add()` with retry/backoff → `_wait_for_ready()` → emits `rs_secondary_ready`                                                                    | Sidecar retries; controller not blocked       |

### Idempotency

Before calling `docker run`, the node manager inspects the container state:

| Existing state | Action                                              |
| -------------- | --------------------------------------------------- |
| Not found      | Create normally                                     |
| Running        | Skip `docker run`, proceed to next step           |
| Stopped/exited | Remove container (and volume for storage), recreate |

For storage nodes, stale volumes are always cleaned up before `docker run` to
avoid replica-set ID clashes from a previous failed attempt.

### Script Output Parsing

Both shell scripts emit machine-readable lines at the end of a successful run:

```
RESULT_IP=10.0.0.7
RESULT_MAC=00:00:00:00:01:07
```

`_BaseNodeAdder._run_script()` parses these via regex to populate `NodeResult.ip`
and `NodeResult.mac`.

### Post-Addition Registration (ElasticityManager)

On a successful `NodeResult`:

- **Compute:** `add_server_mac(mac)` + `register_backend_ip(mac, ip)` — the new
  server enters the VIP web pool immediately.
- **Storage:** `register_backend_ip(mac, ip)` only — VIP registration is
  **deferred** until the sidecar emits `rs_secondary_ready` (fast path) or
  until the telemetry pipeline detects `member_state == "SECONDARY"` (fallback
  path, ~2-4 s delay). This prevents routing traffic to a storage node that
  hasn't finished its initial sync.

Both paths notify Thread 2 via `consume_addition_completions()` so it can
track the new MAC for scale-down decisions (LIFO ordering).

### Storage VIP Promotion (Dual Path)

1. **Fast path — `rs_secondary_ready` control event:** The sidecar emits a
   one-shot event when the node reaches SECONDARY. The controller's SUB
   handler calls `add_storage_mac()` immediately.
2. **Fallback — telemetry-based `member_state` detection:** The sidecar includes
   the RS `stateStr` in every `mongo_stats` and `heartbeat` event. The
   aggregator propagates it via `StorageServerSummary.member_state`. The
   controller's `_promote_storage_from_telemetry()` method checks each storage
   node in the summary and promotes it to the VIP pool if SECONDARY and not
   already registered.

### Timing Model

Every `NodeResult` carries a `StepTimings` record:

| Field                  | What it measures                                                              | Typical range |
| ---------------------- | ----------------------------------------------------------------------------- | ------------- |
| `docker_run_s`       | `docker run` → container enters `running` state                          | 0.1 – 1 s    |
| `network_attach_s`   | veth creation → OVS port → IP config                                        | 1 – 10 s     |
| `replica_set_join_s` | Reserved for future split timing (currently absorbed in `network_attach_s`) | —            |
| `total_s`            | Wall clock from first step to last — includes inter-step overhead            | 1.5 – 15 s   |

Timings are emitted at `INFO` level by `log_timings()`.

### Audit Trail

Every operation (success or failure) is recorded in
`ElasticityManager._operation_log`, a thread-safe list of dicts containing the
alert, container name, and full `NodeResult` / `RemovalResult`. Accessible via
`get_active_operations()` from any thread.

---

## Node Removal

Graceful scale-down is implemented symmetrically to node addition. Two
independent triggers can initiate removal:

- **Underutilisation** — CPU and latency metrics below scale-down thresholds
  for a sustained period (sliding window). Only dynamically added nodes are
  eligible — static servers and primary DB containers are never removed.
  This is the **graceful** path for idle dynamic nodes.
- **Telemetry timeout** — dynamic node absent from 18 consecutive telemetry
  windows (180 s) → assumed dead. This is a **failure detector**, not an
  idleness detector: dynamic nodes don't emit periodic heartbeats (the image
  default `HEARTBEAT_ENABLED=false` is inherited; only static containers set
  `HEARTBEAT_ENABLED=true` — see
  [../other/heartbeat_dynamic_node_gate_plan.md](../other/heartbeat_dynamic_node_gate_plan.md)),
  so any idle-but-alive node is removed by the underutilisation path well
  before this fires. The 180 s is the raw absence tolerance for crashed or
  network-partitioned nodes.

### Compute Node Removal — Async Two-Phase Drain

Compute removal uses a **self-exit model**: the controller isolates the node,
signals it to drain, and the container exits itself once idle. The controller
then cleans up the network. This avoids blocking Thread 3 for the unbounded
duration of in-flight request completion.

**Phase A — `_handle_scale_down_compute(alert)` [Thread 3, <1 s]:**

1. `remove_server_mac(mac)` — immediate; Thread 1 stops routing to this node.
2. Discover veth via `nsenter` (container still running, netns alive).
3. Store `PendingDrain(mac, veth, name, lan, ts)`.
4. `docker exec curl -X POST http://localhost:5000/drain` (3-attempt retry).
   - 200 → container will self-exit after in-flight requests complete.
   - Fails → node is dead; submit `CleanupComputeAlert` immediately.
5. **Return** — Thread 3 is free for other operations.

**Phase B — `_handle_cleanup_compute(alert)` [Thread 3, ~5–10 s]:**

Triggered by `drain_complete` ZMQ event or telemetry timeout fallback.

1. Lookup `PendingDrain` by MAC.
2. Run `remove_network_node.sh --lan <N> --name <name> --veth <veth> --mac <mac>`.
   - Script handles: `docker stop` (safety net) → flow flush → OVS del-port →
     veth deletion → `docker rm`.
3. Release IP back to `IpAllocator`.
4. Delete `PendingDrain` entry; notify Thread 2 via `consume_removal_completions()`.

**Drain endpoint (`/drain`):** Sets `_draining = True` → `before_request`
returns 503 for new requests → drain monitor sends `drain_complete` ZMQ event
when `active_requests == 0` → exits via `os._exit(0)`.

### Storage Node Removal — Synchronous

Storage removal stays synchronous — all operations are server-side and bounded
(~50 s worst case). There is no drain concept for mongod; `rs.remove()` plus
VIP removal suffice. It assumes that underutilization means that no flows rules are installed for the storage server.

**`_handle_scale_down_data(alert)` [Thread 3]:**

1. `remove_storage_mac(mac, domain)` — immediate; no new DNAT flows installed.
2. `rs.remove(IP:PORT)` via the RS primary (Python-side):
   - `_find_rs_primary()` — queries `isMaster` on the known primary container.
   - `_rs_remove_member()` — executes `rs.remove()` via `mongosh`.
   - `_wait_rs_member_removed()` — polls `rs.status()` until member is gone
     (max 10 retries × 3 s).
3. Run `remove_network_storage_node.sh --lan <N> --name <name> --skip-rs ...`.
   - `--skip-rs`: script skips `rs.remove()` (already done in Python).
   - Script handles: DNAT flow flush → `docker stop --time 15` → OVS port/veth
     deletion → `docker rm` → `docker volume rm`.
4. Release IP; notify Thread 2.

**Possible Improvement:** Off all dynamically added nodes removed the one that the flows rules that are related to vip_data dont exist or havent been used for the longest time.

### Removal Timing Model

Every `RemovalResult` carries a `RemovalTimings` record:

| Field                 | What it measures                               |
| --------------------- | ---------------------------------------------- |
| `drain_signal_s`    | Time to send drain signal (Phase A)            |
| `drain_wait_s`      | Time waiting for container exit / idle timeout |
| `network_cleanup_s` | Shell script execution (flow flush + teardown) |
| `total_s`           | Wall-clock start to finish                     |

### Busy Flag and Pending Drains

`ElasticityManager.is_busy()` returns `True` while Thread 3 is executing any
handler or while a Phase A drain is pending. Thread 2 uses this stricter gate
for scale-down and other general checks. For scale-up, Thread 2 now calls
`blocks_compute_scale_up()` and `blocks_storage_scale_up()` instead of using a
single global boolean. Pending compute drains block only compute scale-up;
pending Tier 1 selective drains block neither compute nor storage scale-up.
Storage removal remains a one-phase operation today, so storage scale-up is
blocked only while a storage handler is actively running.

---

## Network Attachment Scripts

### `add_network_node.sh`

Attaches an already-running `--network none` Docker container to an OVS LAN.

```
add_network_node.sh --lan <1|2> --name <container> [--ip <x.x.x.x>] [--mac <XX:..>]
```

Steps:

1. Resolve OVS bridge, subnet, and gateway from `--lan`.
2. Auto-assign IP (scan running containers + named namespaces) if `--ip` omitted.
3. Auto-generate MAC from LAN index and host octet if `--mac` omitted.
4. Pick next free veth index (range `10–19` for LAN 1, `30–49` for LAN 2).
5. Create veth pair, move one end into OVS namespace, attach to bridge.
6. Move peer end into the container namespace, configure IP/MAC/routes.
7. Print summary and emit `RESULT_IP` / `RESULT_MAC`.

### `remove_network_node.sh`

Tears down a compute node's OVS attachment and removes the container.

```
remove_network_node.sh --lan <1|2> --name <container> --veth <veth> --mac <mac>
```

The `--veth` argument is discovered by the controller in Phase A (while the
container is still running) and passed here so the script can skip `nsenter`
discovery after the container has exited.

### `remove_network_storage_node.sh`

Tears down a storage node: DNAT flow flush → `docker stop` → OVS/veth cleanup →
`docker rm` → volume removal.

```
remove_network_storage_node.sh --lan <1|2> --name <container> [--skip-rs] [--keep-volume]
```

`--skip-rs` is used when `rs.remove()` was already performed in Python.

### Per-LAN Constants

| Property           | LAN 1                                                | LAN 2           |
| ------------------ | ---------------------------------------------------- | --------------- |
| OVS bridge         | `ovs-br0`                                          | `ovs-br1`     |
| Subnet             | `10.0.0.0/24`                                      | `10.0.1.0/24` |
| Gateway IP         | `10.0.0.1`                                         | `10.0.1.1`    |
| Dynamic veth range | `10–19`                                           | `30–49`      |
| Reserved IPs       | `.1` (gw), `.100` (VIP_Web), `.200` (VIP_Data) | same            |

---Diminishing-Increment Adaptive Storage Threshold

Storage scale-up uses a **diminishing-increment adaptive threshold** instead of the
adaptive compute policy described above. Each successive dynamic storage node raises
the effective threshold by an increment that **halves with every node added**, floored
at a minimum value. This provides aggressive early resistance — the first few nodes
face a rapidly rising bar — while still allowing the system to react to genuine
saturation at high node counts, where the minimum floor keeps the threshold climbing.

### Adaptive Formula

```
effective_τ = min(base + Σᵢ₌₀ⁿ⁻¹ max(increment × 0.5ⁱ, min_increment), max_threshold)
```

Where `n` = number of pending + active dynamic storage nodes for that LAN.

| Dynamic nodes | Per-node increment | Cumulative threshold |
| :-----------: | :----------------: | :------------------: |
|       0       |         —          |         0.35         |
|       1       |       0.150        |         0.50         |
|       2       |       0.075        |        0.575         |
|       3       |    0.050 (min)     |        0.625         |
|       4       |       0.050        |        0.675         |
|   **5 = cap** |         —          |      hard limit      |

Storage sliding window: **2-of-5** with a 120 s scale-up cooldown after each
trigger, filtering transient spikes and preventing runaway scaling
|      10+      |     0.020 each     |     0.70 (capped)    |

Storage sliding window: **2-of-5** with a 120 s scale-up cooldown after each
trigger, filtering transient spikes and preventing runaway scaling.

---

## Async RS Join via Sidecar

RS join (`rs.add()`) is performed inside the container by the
`mongo_telemetry.py` sidecar, not by the controller or a shell script. The
sidecar discovers the primary via `RS_SEED_HOST` env var, performs `rs.add()`
with 5-attempt retry/exponential backoff, then waits for SECONDARY state (with
a configurable timeout: `RS_READY_TIMEOUT_S`, default 300 s).

The sidecar creates its ZMQ socket **after** `_rs_self_join()` (which waits for
eth0 + seed connectivity) but **before** `_wait_for_ready()`. This ensures
telemetry flows even while the node is syncing, and prevents an infinite block
if RS join fails.

The controller returns after network attach (~5-12 s) instead of waiting for
RS sync (~34-45 s), allowing Thread 3 to process other alerts.

### Stale RS Member Cleanup

The sidecar's `_rs_self_join()` performs a single `replSetReconfig` that both
removes any stale member at the same `host:port` and adds the new member —
eliminating the "Already present" errors that previously caused 86% spawn
failure rates.

---

## Warm Volume Snapshot for Storage Scale-Up — Planned

> **Status:** Not yet implemented.

Even with async RS join, a new storage node must perform a **full initial sync**
from the primary (~20–30 s, primary CPU ~95 %). This optimisation would pre-seed
the new node's data volume with a recent WiredTiger snapshot so it only replays
the oplog delta (~1–3 s).

### How It Works

1. **Primary sidecar** (`mongo_telemetry.py`) runs a background thread that
   periodically snapshots `/data/db` → `/warm` under `fsyncLock`. The warm
   volume (`rs_net{lan}_warm`) is a Docker named volume mounted on the primary.
2. **Controller** (`storage_node_manager.py`), before `docker run`, clones the
   warm volume into the new node's `{name}-data` volume using
   `_acquire_warm_volume()`. If the snapshot is missing or stale (> 600 s), the
   system falls back to an empty volume (current behaviour — full initial sync).

### Write Pause

`fsyncLock` blocks **all client writes** for the duration of the file copy —
typically **0.5–5 s** for 50–200 MB datasets. The snapshot only runs when CPU
is below 70 % and repeats every 5 minutes, making this infrequent.

### New Environment Variables

| Variable                      | Where           | Default   | Description                      |
| ----------------------------- | --------------- | --------- | -------------------------------- |
| `WARM_SNAPSHOT_ENABLED`     | Primary sidecar | `false` | Enable periodic warm snapshot    |
| `WARM_SNAPSHOT_INTERVAL_S`  | Primary sidecar | `300`   | Seconds between snapshots        |
| `WARM_SNAPSHOT_CPU_CEILING` | Primary sidecar | `70`    | Skip snapshot if CPU% exceeds    |
| `WARM_SNAPSHOT_DIR`         | Primary sidecar | `/warm` | Mount point for warm volume      |
| `WARM_VOLUME_MAX_AGE_S`     | Controller      | `600`   | Max snapshot age before fallback |

Full implementation plan:
**[`implementation/warm_volume_snapshot_plan.md`](implementation/warm_volume_snapshot_plan.md)**
