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
  topology ZMQ endpoints, receives `TelemetrySummary` updates, evaluates
  thresholds, and posts typed `Alert` objects to Thread 3's queue.
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
├── elasticity/
│   ├── __init__.py
│   ├── elasticity.py             # ElasticityManager — Thread 3 queue/dispatch
│   ├── node_common.py            # Shared types (NodeResult, RemovalResult, NodeInfo, …),
│   │                             #   constants (SCRIPTS_DIR), and _BaseNodeAdder helpers
│   ├── compute_node_manager.py   # ComputeNodeAdder — edge_server lifecycle + drain phases
│   └── storage_node_manager.py  # StorageNodeAdder — edge_storage_server lifecycle + rs.remove()
└── topology/
    └── topology.py               # TopologyMixin — VIP pool (add_server_mac, add_storage_mac, etc.)

source/scripts/network/
├── add_network_node.sh           # Attaches a running container to OVS LAN (veth + IP/MAC)
│                                 #   Used for both compute AND storage nodes
└── add_network_storage_node.sh   # ⚠ DEPRECATED — replaced by sidecar RS join (see below)
```

---

## Alert Types

Produced by Thread 2's `_on_telemetry_update` callback in `main_n1.py`, consumed
by Thread 3.

| Alert                     | Trigger                                          | Fields                                                                        |
| ------------------------- | ------------------------------------------------ | ----------------------------------------------------------------------------- |
| `ComputeAlert`          | Weighted compute score ≥ 0.40 (2-of-5 window)  | `lan`, `network_id`                                                         |
| `DataAlert`             | ~~Weighted storage score ≥ 0.40 (2-of-5 window)~~ **Adaptive threshold** (see below)  | `lan`, `network_id`, `rs_name`, `primary_container`, `port`          |
| `ScaleDownComputeAlert` | Underutilisation (7-of-12 window) or timeout   | `lan`, `network_id`, `container_name`, `mac`                          |
| `ScaleDownDataAlert`    | Underutilisation (~~7-of-12~~ **9-of-15** window) or timeout   | `lan`, `network_id`, `container_name`, `mac`, `ip`, `rs_name`, `primary_container`, `port` |
| `CleanupComputeAlert`   | `drain_complete` ZMQ event / telemetry timeout  | `mac`                                                                         |

Scale-up computes a weighted degradation score per tier:
`score = 0.3 × cpu_component + 0.7 × latency_component`, where each component
is normalised as `max(0, value − floor) / span`.

> **Compute** scale-up fires when the score is ≥ 0.40 in at least 2 of
> the last 5 evaluation windows (unchanged).
>
> **Storage** scale-up uses a **predictive adaptive threshold** (see
> [Predictive Threshold](#predictive-adaptive-storage-threshold-2026-04-13)
> below): `effective_τ = min(0.25 + dynamic_storage_count × 0.10, 0.65)`,
> with a 1-of-3 sliding window.

Scale-down uses a separate sliding window: compute fires when 7 of the last
12 windows are below threshold; **storage fires when 9 of the last 15**
windows are below threshold (~~was 7-of-12~~). Windows where latency exceeds
a timeout ceiling (default 5 000 ms) are treated as indeterminate and skipped
— preventing RS election or connectivity timeouts from poisoning the signal.

Thresholds are configured via environment variables (scale-up vars prefixed
with `SCALEUP_` to avoid collision with VIP routing weights):

**Scale-up (weighted degradation score)**

| Variable                          | Default | Description                                        |
| --------------------------------- | ------- | -------------------------------------------------- |
| `SCALEUP_W_CPU`                 | `0.3` | Compute score: CPU weight                          |
| `SCALEUP_W_T_PROC`             | `0.7` | Compute score: T_proc weight                       |
| `SCALEUP_CPU_FLOOR`            | `50`  | Compute CPU: below this → 0 contribution          |
| `SCALEUP_CPU_SPAN`             | `35`  | Compute CPU: normalisation range                   |
| `SCALEUP_T_PROC_FLOOR`         | `1`   | T_proc (ms): below this → 0 contribution          |
| `SCALEUP_T_PROC_SPAN`          | `11`  | T_proc (ms): normalisation range                   |
| `SCALEUP_W_STORAGE_CPU`        | `0.3` | Storage score: CPU weight                          |
| `SCALEUP_W_T_DB`               | `0.7` | Storage score: T_db weight                         |
| `SCALEUP_STORAGE_CPU_FLOOR`    | `50`  | Storage CPU: below this → 0 contribution          |
| `SCALEUP_STORAGE_CPU_SPAN`     | `35`  | Storage CPU: normalisation range                   |
| `SCALEUP_T_DB_FLOOR`           | `15`  | T_db (ms): below this → 0 contribution            |
| `SCALEUP_T_DB_SPAN`            | `75`  | T_db (ms): normalisation range                     |
| `SCALEUP_SCORE_THRESHOLD`      | `0.40`| Score ≥ this counts as "degraded" **(compute only — storage uses adaptive threshold below)** |
| `SCALEUP_WINDOW_SIZE`          | `5`   | Sliding window size **(compute only)**             |
| `SCALEUP_REQUIRED`             | `2`   | Required degraded windows **(compute only)**       |

**Adaptive storage scale-up threshold** (see [§ Predictive Threshold](#predictive-adaptive-storage-threshold-2026-04-13))

| Variable                              | Default  | Description                                        |
| ------------------------------------- | -------- | -------------------------------------------------- |
| `SCALEUP_STORAGE_BASE_THRESHOLD`    | `0.25` | Adaptive base threshold for storage scale-up       |
| `SCALEUP_STORAGE_THRESHOLD_INCREMENT`| `0.10` | Per-dynamic-storage-node increment                 |
| `SCALEUP_STORAGE_MAX_THRESHOLD`     | `0.65` | Adaptive threshold cap                             |
| `SCALEUP_STORAGE_WINDOW_SIZE`       | ~~`3`~~ **`5`**    | Sliding window size (storage only)                 |
| `SCALEUP_STORAGE_REQUIRED`          | ~~`1`~~ **`2`**    | Required degraded windows (storage only)           |
| `SCALEUP_STORAGE_COOLDOWN_S`       | `120`  | Post-scale-up cooldown before next storage scale-up (s) |

**Scale-down**

| Variable                          | Default | Description                                        |
| --------------------------------- | ------- | -------------------------------------------------- |
| `TAU_CPU_DOWN`                  | `65`  | Domain avg CPU below → compute idle              |
| `TAU_PROC_DOWN_MS`              | `5`   | Domain avg proc latency below → compute idle     |
| `TAU_STORAGE_CPU_DOWN`          | `60`  | Domain avg storage CPU below → storage idle      |
| `TAU_DB_DOWN_MS`                | `100` | Domain avg DB latency below → storage idle       |
| `SCALE_DOWN_COMPUTE_WINDOW_SIZE`| `12`  | Sliding window size for compute scale-down         |
| `SCALE_DOWN_COMPUTE_REQUIRED`   | `7`   | Required below-threshold windows (compute)         |
| `SCALE_DOWN_STORAGE_WINDOW_SIZE`| ~~`12`~~ **`15`**  | Sliding window size for storage scale-down         |
| `SCALE_DOWN_STORAGE_REQUIRED`   | ~~`7`~~ **`9`**   | Required below-threshold windows (storage)         |
| `SCALE_DOWN_PROC_TIMEOUT_CEILING_MS` | `5000` | Proc latency above → indeterminate window  |
| `SCALE_DOWN_DB_TIMEOUT_CEILING_MS`   | `5000` | DB latency above → indeterminate window    |
| `TELEMETRY_TIMEOUT_WINDOWS`     | `10`  | Absent windows before dead-node removal            |
| `SCALEDOWN_STORAGE_COOLDOWN_S`  | ~~`75`~~ **`120`**  | Post-scale-up cooldown before storage scale-down (s) |
| `SCALEDOWN_COMPUTE_COOLDOWN_S`  | `40`  | Post-scale-up cooldown before compute scale-down (s) |
| `NODE_BIRTH_GRACE_S`            | `60`  | Skip absent-node detection during node bootstrap (s) |

---

## Node Addition — Implemented

### Container Naming

Dynamic containers are named using a per-network sequence counter:
`{prefix}_{network_id}_dyn{counter}` — e.g. `edge_server_lan1_dyn1`,
`edge_storage_lan2_dyn3`.

### Lifecycle: `NodeAdder`

Each public method is a self-contained, timed, idempotent lifecycle. Every step
is individually timed with `time.perf_counter()`.

#### `add_edge_server(lan, name)`

| Step | Operation                                                                     | On failure                           |
| ---- | ----------------------------------------------------------------------------- | ------------------------------------ |
| 1    | `docker run -dit --network none --name <name> -e LAN_ID=lan<N> edge_server` | Return `FAILED`                    |
| 2    | `add_network_node.sh --lan <N> --name <name>`                               | Cleanup container, return `FAILED` |

#### `add_storage_node(lan, name, rs_name, primary_container, port)`

> **Updated 2026-04-13:** Step 2 now uses `add_network_node.sh` (network-only).
> RS join (`rs.add()`) is handled asynchronously by the `mongo_telemetry.py`
> sidecar inside the container, with retry/backoff. See
> [`implementation/predictive_threshold_and_async_rs_plan.md`](implementation/predictive_threshold_and_async_rs_plan.md)
> Phase 2.

| Step | Operation                                                                                                                                                                                                     | On failure                                    |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| 1    | `docker run -dit --network none --name <name> -v <name>-data:/data/db -e LAN_ID=lan<N> -e MONGO_REPLSET=<rs> -e MONGO_PORT=<port> -e RS_ADD_SELF=true -e RS_SEED_HOST=<primary_ip:port> edge_storage_server` | Return `FAILED`                             |
| 2    | `add_network_node.sh --lan <N> --name <name>`                                                                                                                                                                | Cleanup container + volume, return `FAILED` |
| *(async)* | Sidecar `_rs_self_join()` runs inside container: `rs.add()` with 5-attempt retry/backoff → `_wait_for_ready()` → emits `rs_secondary_ready`                                                           | Sidecar retries; controller not blocked      |

### Idempotency

Before calling `docker run`, `NodeAdder` inspects the container state:

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

`NodeAdder._run_script()` parses these via regex to populate `NodeResult.ip` and
`NodeResult.mac`.

### Post-Addition Registration (ElasticityManager)

On a successful `NodeResult`:

- **Compute:** `add_server_mac(mac)` + `register_backend_ip(mac, ip)` — the new
  server enters the VIP web pool and Thread 1 starts routing traffic to it.
- **Data:** `add_storage_mac(mac, domain=f"n{lan}")` + `register_backend_ip(mac, ip)`
  — the new storage node enters the VIP data pool for its domain.

If the script succeeds but MAC is not present in the output, a warning is logged
and VIP registration is skipped (the node is online but unreachable via VIP
until manually registered).

### Timing Model

Every `NodeResult` carries a `StepTimings` record:

| Field                  | What it measures                                                              | Typical range |
| ---------------------- | ----------------------------------------------------------------------------- | ------------- |
| `docker_run_s`       | `docker run` → container enters `running` state                          | 0.1 – 1 s    |
| `network_attach_s`   | veth creation → OVS port → IP config (+ rs.add for storage)                 | 1 – 10 s     |
| `replica_set_join_s` | Reserved for future split timing (currently absorbed in `network_attach_s`) | —            |
| `total_s`            | Wall clock from first step to last — includes inter-step overhead            | 1.5 – 15 s   |

Timings are emitted at `INFO` level by `log_timings()`.

### Audit Trail

Every operation (success or failure) is recorded in `ElasticityManager._active`,
a thread-safe list of dicts containing the alert, container name, and full
`NodeResult`. Accessible via `get_active_operations()` from any thread.

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

### `add_network_storage_node.sh`

> **⚠ DEPRECATED (2026-04-13):** This script is superseded by the sidecar-based
> async RS join. Storage nodes now use `add_network_node.sh` for network
> attachment; `rs.add()` is performed by `mongo_telemetry.py` inside the
> container. This script will be **deleted** once the async RS join is
> implemented. See
> [`implementation/predictive_threshold_and_async_rs_plan.md`](implementation/predictive_threshold_and_async_rs_plan.md)
> Phase 3.

~~Same as above, plus:~~

- ~~Runs `rs.add("IP:PORT")` against the replica-set primary.~~
- ~~Waits for the new member to reach `SECONDARY` state before completing.~~

### Per-LAN Constants

| Property           | LAN 1                                                | LAN 2           |
| ------------------ | ---------------------------------------------------- | --------------- |
| OVS bridge         | `ovs-br0`                                          | `ovs-br1`     |
| Subnet             | `10.0.0.0/24`                                      | `10.0.1.0/24` |
| Gateway IP         | `10.0.0.1`                                         | `10.0.1.1`    |
| Dynamic veth range | `10–19`                                           | `30–49`      |
| Reserved IPs       | `.1` (gw), `.100` (VIP_Web), `.200` (VIP_Data) | same            |

---

## Node Removal — Planned

Graceful scale-down will be added symmetrically to node addition. The design
uses a two-phase cooperative drain to avoid cutting active connections.

### Two-Phase Cooperative Drain

**Phase A — Controller-side isolation (immediate):**

1. Remove MAC from VIP pool (`remove_server_mac` / `remove_storage_mac`).
2. Storage only: `rs.remove(IP:PORT)` via the replica set primary.

**Phase B — Node drain + cleanup:**

1. Signal node to stop accepting work.
2. Wait for active work to finish (or timeout).
3. `docker stop` if still running after timeout.
4. Flush OVS flows for the MAC, remove OVS port, delete veth pair.
5. `docker rm` (and `docker volume rm` for storage).

### Drain by Node Type

|                      | Compute (`edge_server`)                                              | Storage (`edge_storage_server`)                                          |
| -------------------- | ---------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Drain signal         | `docker exec <name> curl -sS -X POST http://localhost:5000/drain`    | Phase A is sufficient —`rs.remove()` + VIP removal stop all new work    |
| Idle detection       | Flask active-request counter hits 0 → container calls `os._exit(0)` | Telemetry pipeline:`connections_current ≤ 1` in next ZMQ window (~10 s) |
| Who stops container? | Container exits itself; controller detects via `docker inspect` poll | Controller calls `docker stop` once idle confirmed                       |
| Timeout fallback     | Force-stop after 30 s                                                  | Force-stop after 15 s                                                      |

### New Alert Types (planned)

| Alert                     | Fields                                                                                                     |
| ------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `ScaleDownComputeAlert` | `lan`, `network_id`, `container_name`, `ip`, `mac`                                               |
| `ScaleDownDataAlert`    | `lan`, `network_id`, `container_name`, `ip`, `mac`, `rs_name`, `primary_container`, `port` |

`ip` and `mac` are passed from the caller (available from the original
`NodeResult` at addition time) to avoid re-discovery race conditions.

### New `NodeAdder` Methods (planned)

- `remove_edge_server(lan, name, mac, drain_timeout=30)` — drain signal →
  wait for exit → force-stop → flush OVS flows → remove port/veth → `docker rm`.
- `remove_storage_node(lan, name, mac, ip, rs_name, primary_container, port, drain_timeout=15)` — rs.remove → wait for idle → stop → flush → cleanup → volume rm.

### New Shell Scripts (planned)

- `remove_network_node.sh --graceful` — drain + network teardown for compute.
- `remove_network_storage_node.sh --graceful` — RS removal + drain + network
  teardown for storage.

Both scripts will add `--graceful` and `--drain-timeout` flags; without
`--graceful` they retain immediate-removal behaviour for backward compatibility.

### Scale-Down Detection (deferred)

The policy for *when* to remove a node (scale-down thresholds) is a separate
concern. The removal mechanism will be implemented and tested before the
detection logic is layered on top. Once ready, Thread 2 will submit
`ScaleDownComputeAlert` / `ScaleDownDataAlert` to the queue via
`submit_alert()`.

---

## Known Issues — Scale-Up / Scale-Down Thrashing (2026-04-11 run)

Analysis of the `20260411_235936` test run exposed a **scale-up → immediate
scale-down** thrashing loop that caused 5 400+ HTTP errors across ~4 minutes
during the `compute_spike` phase. Root causes: no post-scale-up cooldown (now
proposed as per-tier: storage 75 s / compute 40 s), threshold too high
(τ=0.85, 3-of-5 → proposed 0.70, 2-of-5), and absent-node detection counting
boot delay as idleness.

Full analysis, code snippets, and implementation plan:
**[`implementation/thrashing_fix_plan.md`](implementation/thrashing_fix_plan.md)**

---

## Storage Node Reliability Fixes (2026-04-12 run)

Analysis of the `20260412_204044` test run (with τ=0.40) revealed a **cascade
failure**: 30 storage spawn attempts, 5 succeeded at `rs.add()`, but **zero
reached the VIP storage pool**. Two root causes:

1. **Stale RS members causing `rs.add()` "Already present" errors (86% failure
   rate):** When a spawn fails *after* `rs.add()` succeeds (or the container is
   removed without `rs.remove()`), a phantom RS member remains at that IP:port.
   The next spawn to the same IP collides with the phantom.

2. **`rs_secondary_ready` event lost — nodes never join VIP:** The sidecar
   (`mongo_telemetry.py`) created its ZMQ PUSH socket at module-import time,
   *before* `eth0` existed (container starts with `--network none`). The one-shot
   `rs_secondary_ready` event was sent via `NOBLOCK` before the TCP connection
   was established. Since the controller had no fallback mechanism, the storage
   node never received traffic, keeping T_db elevated indefinitely → DataAlert
   storm.

### Fix A — Stale RS member cleanup (`add_network_storage_node.sh`)

Added `rs_cleanup_stale_member()`: before every `rs.add()`, queries
`rs.status().members` for an existing entry at the target `host:port`. If found,
calls `rs.remove()` first + brief wait, then proceeds. Idempotent — no-op when
clean. Phantom members (priority 0, non-voting) cause minimal harm but this
prevents the "Already present" error that blocked 86% of spawns.

### Fix C — Reliable SECONDARY detection (sidecar + telemetry pipeline)

**Part 1 — Early ZMQ socket (`mongo_telemetry.py`):** The ZMQ PUSH socket is
created in `main()` **after** `_rs_self_join()` (which ensures eth0 exists via
`_wait_for_network()`) but **before** `_wait_for_ready()`. This means telemetry
and heartbeats can flow even while the node is syncing to SECONDARY (or blocked
due to a failed RS join). `_wait_for_ready()` now has a configurable timeout
(`RS_READY_TIMEOUT_S`, default 300 s) — on timeout the sidecar falls through to
the telemetry loop, giving the controller visibility into the stuck node.
The `rs_secondary_ready` event is emitted immediately after `_wait_for_ready()`
returns `"SECONDARY"` — this is the **fast path** for VIP promotion.

> **History:** Originally (Fix C, 2026-04-12) the socket was deferred until
> *after* `_wait_for_ready()`. A follow-up test (2026-04-13, run `154833`)
> showed this caused an infinite block when RS join failed — the sidecar
> never created the ZMQ socket, so no telemetry or events reached the
> controller. See
> [`implementation/sidecar_zmq_timeout_fix.md`](implementation/sidecar_zmq_timeout_fix.md).

**Part 2 — `member_state` in telemetry pipeline:** The sidecar now includes the
replica-set `stateStr` (e.g., `"SECONDARY"`, `"PRIMARY"`) in every `mongo_stats`
and `heartbeat` event. This field is propagated through:
- **Aggregator** (`aggregator.py`): picks the latest `member_state` from the
  window and includes it in both active and heartbeat-only storage summaries.
- **Model** (`StorageServerSummary`): new field `member_state: str | None = None`.

**Part 3 — Telemetry-based VIP promotion (controllers):** A new method
`_promote_storage_from_telemetry()` in `_on_telemetry_update()` checks each
storage node in the summary: if `member_state == "SECONDARY"` and the MAC is in
`_active` but not yet in the VIP storage pool, it calls `add_storage_mac()`.
This is the **fallback path** — fires ~2-4 s after the fast path on the next
aggregation window, ensuring VIP promotion even if the control event is lost.

### Files modified
| File | Change |
| ---- | ------ |
| `source/scripts/network/add_network_storage_node.sh` | `rs_cleanup_stale_member()` + called before `rs_add_member()` |
| `source/docker/edge_storage_server/mongo_telemetry.py` | Deferred ZMQ socket; `_repl_lag_and_state()` returns `(lag, state)`; `member_state` in events |
| `source/docker/local_state_server/aggregator.py` | `member_state` propagated in storage summaries |
| `source/sdn_controller/telemetry/models.py` | `member_state` field on `StorageServerSummary` |
| `source/sdn_controller/main_n1.py` | `_promote_storage_from_telemetry()` fallback |
| `source/sdn_controller/main_n2.py` | `_promote_storage_from_telemetry()` fallback |

Full analysis and implementation plan:
**[`implementation/storage_reliability_plan.md`](implementation/storage_reliability_plan.md)**

> **Note (2026-04-13):** Fix A (`rs_cleanup_stale_member` in
> `add_network_storage_node.sh`) is **superseded** by the sidecar-based
> `_rs_self_join()` which performs the same stale cleanup before `rs.add()`,
> with retry/backoff. See
> [`implementation/predictive_threshold_and_async_rs_plan.md`](implementation/predictive_threshold_and_async_rs_plan.md).

---

## Predictive Adaptive Storage Threshold (2026-04-13)

Analysis of the `20260413` test run exposed that the fixed threshold (τ=0.40,
2/5 window) triggers too late — ~20 s from first degradation, during which
the 34–45 s provisioning pipeline hasn't even started. Combined with FIFO
queue serialisation (compute processed before storage) and RS join failures
under load, this creates 80 s storage blackouts.

**Fix:** Replace the shared fixed threshold with a **predictive adaptive
threshold** for storage scale-up. Compute keeps the existing parameters.

### Adaptive Formula

```
effective_τ = min(base + dynamic_storage_count × increment, max_threshold)
           = min(0.25 + N × 0.10, 0.65)
```

Where `N` = number of pending + active dynamic storage nodes for that LAN.

| Dynamic nodes | Effective τ | Meaning |
|:---:|:---:|---|
| 0 | 0.25 | First scale-up: low bar → early detection |
| 1 | 0.35 | Second node: moderate bar → filters transient spikes |
| 2 | 0.45 | Third node: ~current threshold level |
| 4+ | 0.65 | Cap: only genuine saturation triggers more |

Storage sliding window: **1-of-3** (was 2-of-5). First breach triggers.

### Scale-Down Protection

| Parameter | Old | New | Reason |
|-----------|-----|-----|--------|
| Storage cooldown | 75 s | **120 s** | Proactively added nodes need time to absorb load |
| Storage window | 7/12 | **9/15** | More sustained signal before removal |

### Queue Priority

Thread 3's queue is upgraded from `queue.Queue` (FIFO) to
`queue.PriorityQueue`. When both a `DataAlert` and `ComputeAlert` arrive
simultaneously, storage goes first (priority 1 vs 2) — saving ~17 s that was
previously wasted on compute provisioning before storage.

### Async RS Join via Sidecar

RS join (`rs.add()`) is moved from `add_network_storage_node.sh` into the
container's `mongo_telemetry.py` sidecar. The sidecar discovers the primary
via `RS_SEED_HOST` env var, performs `rs.add()` with 5-attempt
retry/exponential backoff, then waits for SECONDARY state. The controller
returns after network attach (~5-12 s) instead of waiting for RS sync (~34-45 s).

This resolves the cascading `"Could not determine primary"` failures observed
under high CPU load.

Full analysis and implementation plan:
**[`implementation/predictive_threshold_and_async_rs_plan.md`](implementation/predictive_threshold_and_async_rs_plan.md)**

---

## Warm Volume Snapshot for Storage Scale-Up (2026-04-13)

Even with async RS join, a new storage node must perform a **full initial sync**
from the primary (~20–30 s, primary CPU ~95 %). This optimisation pre-seeds the
new node's data volume with a recent WiredTiger snapshot so it only replays the
oplog delta (~1–3 s).

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

### Interaction with Other Fixes

| Fix | Interaction |
|-----|-------------|
| Predictive adaptive threshold | Independent — earlier detection + warm vol = faster response |
| Async RS join | Complementary — warm vol reduces oplog replay from ~20 s to ~1–3 s |
| Priority queue | Independent |

### New Environment Variables

| Variable | Where | Default | Description |
|----------|-------|---------|-------------|
| `WARM_SNAPSHOT_ENABLED` | Primary sidecar | `false` | Enable periodic warm snapshot |
| `WARM_SNAPSHOT_INTERVAL_S` | Primary sidecar | `300` | Seconds between snapshots |
| `WARM_SNAPSHOT_CPU_CEILING` | Primary sidecar | `70` | Skip snapshot if CPU% exceeds |
| `WARM_SNAPSHOT_DIR` | Primary sidecar | `/warm` | Mount point for warm volume |
| `WARM_VOLUME_MAX_AGE_S` | Controller | `600` | Max snapshot age before fallback |

Full implementation plan:
**[`implementation/warm_volume_snapshot_plan.md`](implementation/warm_volume_snapshot_plan.md)**
