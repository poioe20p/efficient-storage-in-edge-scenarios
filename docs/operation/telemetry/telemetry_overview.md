# Telemetry Pipeline — Overview

## Purpose

The telemetry pipeline collects latency, resource usage, and liveness data from
every edge container, aggregates it in per-network time windows, and delivers
structured summaries to the SDN controller. The controller uses these summaries
for two purposes:

1. **VIP routing cost functions (Thread 1)** — per-server stats feed the WSM
   scoring that selects which backend receives the next VIP-routed request.
2. **Elasticity threshold evaluation (Thread 2 → Thread 3)** — domain-level
   averages are compared against configurable thresholds to trigger scale-out
   alerts.

---

## Architecture: End-to-End Data Flow

```
  edge_server (Flask)            edge_storage_server (mongod)
  ┌──────────────────┐           ┌────────────────────────────┐
  │ telemetry.py     │           │ mongo_telemetry.py         │
  │  after_request → │           │  opcounter delta →         │
  │  ZMQ PUSH event  │           │  ZMQ PUSH event            │
  │  heartbeat loop  │           │  heartbeat on idle         │
  └────────┬─────────┘           └─────────────┬──────────────┘
           │                                   │
           └──────────┬────────────────────────┘
                      ▼
           ┌────────────────────┐
           │  aggregator.py     │
           │  ZMQ PULL (:5555)  │  ← collects all events
           │  window (10 s)     │  ← groups, averages
           │  ZMQ PUB  (:5556)  │  → publishes TelemetrySummary
           └────────┬───────────┘
                    ▼
           ┌─────────────────────────────────────────┐
           │  SDN Controller (ZmqTelemetrySource)    │
           │  ZMQ SUB ← subscribes to all aggregators│
           │                                         │
           │  on_update callback:                    │
           │    • update_server_stats()  (Thread 1)  │
           │    • update_storage_stats() (Thread 1)  │
           │    • threshold check → Thread 3 alerts  │
           └─────────────────────────────────────────┘
```

One aggregator runs per network (e.g. `aggregator_n1` on LAN 1,
`aggregator_n2` on LAN 2). Each controller subscribes to **both** aggregators
because VIP routing is cross-domain — a controller may route a client to a
server in the peer network, and the WSM cost function scores all candidate
servers across both networks.

---

## File Layout

### Telemetry Senders

```
source/docker/edge_server/source/
  telemetry.py          # MetricSender ABC, ZmqMetricSender, Flask hooks, heartbeat loop
  db_monitor.py         # pymongo CommandListener — per-request read/write DB time

source/docker/edge_storage_server/
  mongo_telemetry.py    # MongoDB sidecar: opcounter-based activity detection,
                        #   ZMQ PUSH of mongo_stats / heartbeat events
```

### Aggregator

```
source/docker/local_state_server/
  aggregator.py         # ZMQ PULL/PUB, windowed aggregation, publishes TelemetrySummary
```

### Controller-Side Receiver

```
source/sdn_controller/telemetry/
  __init__.py
  models.py             # Pydantic models (TelemetrySummary, ServerSummary, etc.)
  source.py             # TelemetryEventSource ABC
  zmq_source.py         # ZmqTelemetrySource — ZMQ SUB, eventlet greenthread
```

---

## Edge Server Telemetry (`telemetry.py`)

### Server Identification

Each container identifies itself by its **MAC address**, discovered from
`/sys/class/net/eth0/address` (or the first non-loopback interface). The MAC
is used as `server_id` throughout the pipeline and matches the key in the
controller's VIP pool.

The aggregator address is derived from the `LAN_ID` env var
(e.g. `lan1` → `tcp://10.0.0.5:5555`), or set explicitly via
`AGGREGATOR_PULL_ADDR`.

### Per-Request Events

Flask hooks emit a ZMQ PUSH event after every HTTP request:

```json
{
  "server_id":         "00:00:00:00:00:02",
  "ts":                1742126400.0,
  "time_total_ms":     85.2,
  "time_db_ms":        47.1,
  "time_db_read_ms":   31.4,
  "time_db_write_ms":  15.2,
  "time_db_cmd_count": 6,
  "status_code":       200,
  "request_type":      "read",
  "cpu_percent":       34.7,
  "ram_used_mb":       128.3
}
```

| Field             | Source                                                                        |
| ----------------- | ----------------------------------------------------------------------------- |
| `time_total_ms` | Wall clock from `before_request` to `after_request`                       |
| `time_db_ms`    | Accumulated via the `timed_db()` context manager wrapping all MongoDB calls |
| `time_db_read_ms` | Sum of pymongo read-command durations via `CommandListener` (`find`, `aggregate`, `count`, `distinct`, `getMore`, `findAndModify`) |
| `time_db_write_ms` | Sum of pymongo write-command durations via `CommandListener` (`insert`, `update`, `delete`) |
| `time_db_cmd_count` | Non-internal command count during the request |
| `cpu_percent`   | `psutil.cpu_percent()`                                                      |
| `ram_used_mb`   | `psutil.virtual_memory().used / 1 MiB`                                      |
| `request_type`  | `"write"` for POST/PUT/PATCH/DELETE, `"read"` otherwise                   |

> `time_db_read_ms + time_db_write_ms` is not expected to equal `time_db_ms`
> exactly. `time_db_ms` wraps the `timed_db` block (connection checkout, server
> selection, serialization); the listener measures only command RTT. The gap is
> diagnostic — see [implementation/db_timing_decomposition.md](implementation/db_timing_decomposition.md).

`zmq.NOBLOCK` ensures the hook never blocks the HTTP response — events are
silently dropped if the aggregator is temporarily unavailable.

### Tier 1 Selective-Sync Fields (piggyback)

The per-request event also carries three optional fields used by the Tier 1
selective-sync subsystem. They are populated by the
`platform_cache._CachedCollection` wrapper via
request-scoped Flask `g` and shipped verbatism on the existing event — no
new ZMQ event type, no new thread. For requests that never touch a wrapped
collection (health / drain / wait_time) all three fields are empty / `{}`.

| Field                   | Shape                                                       | Source                                                                                   |
| ----------------------- | ----------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `time_db_ms_per_lan`  | `{owner_lan: ms}`                                         | Existing `g.time_db_per_lan` (ms) accumulated by `timed_db(lan)` per owning LAN        |
| `access_records`      | `[{owner_lan, collection, doc_id}, ...]`                  | One entry per wrapped **cross-region** point read (`find_one({"_id": X})`)             |
| `op_counts`           | `{owner_lan: {collection: {op_type: count}}}`             | Every wrapped call (reads + writes) increments one leaf                                |

The local_state_server aggregator folds these at window close into three
roll-ups on each `ServerSummary`:

- `t_db_p95_ms_per_lan` — `statistics.quantiles(..., n=20)[18]` per owner_lan
  across every request's `time_db_ms_per_lan` sample.
- `op_counters` — leaf-sum over the `{owner_lan → coll → op_type}` tree.
- `access` — per `(owner_lan, collection)`: `total_hits` (derived from
  `op_counters` read op-types — single source of truth), `cross_region_hits`,
  and the top-`SS_TOP_DOCS_PER_EDGE` `doc_id`s by hit count.

The controller's `selective_sync.hotness` module consumes these fields via
stateless reducers (`merge_edge_access`, `breach_this_window`, `write_ratio`,
`total_reads`).

### Heartbeat Events

A daemon thread sends a heartbeat every `HEARTBEAT_INTERVAL_S` (default 60 s)
when the server is idle. The countdown resets after every request-driven event,
so a busy server never sends redundant heartbeats.

**Static-only periodic emission.** Heartbeats are only meaningful for
**static** nodes (`edge_server_n{1,2}`, `edge_storage_server_n{1,2}`), which
are excluded from scale-down and can legitimately sit idle. The image default
is `HEARTBEAT_ENABLED=false`, and only the literal string `true` enables the
periodic heartbeat thread. Dynamic nodes keep the default disabled and emit no
periodic heartbeats (their idleness is handled by the underutilisation
scale-down path; true failure is handled by the telemetry-window absence
timeout, `TELEMETRY_TIMEOUT_WINDOWS × WINDOW_S`, default 180 s). Static
containers opt in explicitly via `HEARTBEAT_ENABLED=true` in their docker run
commands. See
[../other/heartbeat_dynamic_node_gate_plan.md](../other/heartbeat_dynamic_node_gate_plan.md)
for the rationale.

Each `edge_server` also emits one bootstrap `heartbeat`-shape sample once a
real interface MAC is available. That bootstrap sample is not a replacement for
periodic heartbeats; it only makes a newly spawned backend visible before its
first real HTTP request.

| Env var | Default | Effect |
|---|---|---|
| `HEARTBEAT_INTERVAL_S` | `60` | Idle heartbeat period (seconds). |
| `HEARTBEAT_ENABLED` | `false` | When `true`, enables the periodic heartbeat emitter. Set explicitly on static containers via [build_network_1.sh](../../../source/scripts/network/build_network_1.sh) / [build_network_2.sh](../../../source/scripts/network/build_network_2.sh); dynamic nodes keep the default disabled. |

```json
{
  "event_type":  "heartbeat",
  "server_id":   "00:00:00:00:00:02",
  "ts":          1742126860.0,
  "cpu_percent": 2.1,
  "ram_used_mb": 128.3
}
```

### Architecture: `MetricSender` ABC

`telemetry.py` defines a `MetricSender` abstract class with a single
`send(event)` method. The production implementation is `ZmqMetricSender`.
The ABC allows injecting a test double for unit testing without a live
ZMQ socket.

`init_telemetry(app, sender=None)` wires up `before_request`/`after_request`
hooks, starts a short-lived bootstrap probe, and, when
`HEARTBEAT_ENABLED=true` (static containers only), spawns the periodic
heartbeat thread. Called once at app startup.

---

## Storage Sidecar Telemetry (`mongo_telemetry.py`)

The `edge_storage_server` runs a bare `mongod` with no application layer. A
lightweight Python sidecar runs alongside it (started by `entrypoint.sh`) and
pushes periodic stats to the same aggregator PULL socket.

### Activity-Based Push (Opcounters Delta)

The sidecar does **not** push on every poll cycle. It uses
`serverStatus.opcounters` to detect whether real client operations occurred
since the last poll:

- **CRUD opcounters** (`insert`, `query`, `update`, `delete`, `getmore`) —
  any delta > 0 means client activity → push `mongo_stats` event.
- **`command` opcounter is ignored** — in a replica set, internal
  heartbeat/election commands inflate it every cycle even when idle.
- **First poll** — captures the baseline without reporting, so the sidecar's
  own 3 internal MongoDB connections don't produce a spurious event.
- **First `SECONDARY` transition** — immediately pushes one bootstrap
  `mongo_stats` sample after `_wait_for_ready()` confirms the node is a
  `SECONDARY`, so the controller can see a newly promoted backend before the
  next normal activity-driven poll.

When idle, a `heartbeat` event is sent every `HEARTBEAT_INTERVAL_S` (default
60 s) for liveness — **only when `HEARTBEAT_ENABLED=true`**, which is set
explicitly on the static primary DB container. Dynamic storage secondaries keep
the default `HEARTBEAT_ENABLED=false` and emit no periodic heartbeat; their
idleness is reclaimed by scale-down and true failure by the telemetry-window
absence timeout.

### `mongo_stats` Event

```json
{
  "event_type":          "mongo_stats",
  "server_id":           "00:00:00:00:00:06",
  "ts":                  1742126400.0,
  "repl_lag_s":          1.2,
  "member_state":        "SECONDARY",
  "connections_current": 4,
  "cpu_percent":         12.3,
  "ram_used_mb":         256.7
}
```

| Field                             | Source                                                                                                                               |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `repl_lag_s`                    | `replSetGetStatus` — seconds behind primary. `0.0` if this IS the primary; `None` if standalone.                              |
| `member_state`                  | `replSetGetStatus` — RS state string (e.g. `"SECONDARY"`, `"PRIMARY"`). Used by the controller's VIP promotion fallback path. |
| `connections_current`           | `serverStatus.connections.current`                                                                                                 |
| `cpu_percent` / `ram_used_mb` | `psutil`                                                                                                                           |

### Heartbeat Event

Identical structure to `mongo_stats` but with `"event_type": "heartbeat"`.
The aggregator filters these out of summary calculations — they only serve
as liveness signals. The edge-server bootstrap sample reuses this exact shape,
so the aggregator treats it as a normal heartbeat event.

### Tier 1 Selective-Sync Supervisor Event

The `edge_selective_storage` supervisor (`source/docker/edge_selective_storage/telemetry.py`)
pushes a per-collection frame to the same aggregator PULL socket, keyed by the
supervisor container's MAC (`server_mac`):

```json
{
  "server_mac": "00:00:00:00:00:0e",
  "member_state": "STANDALONE_CACHE",
  "selective_sync_per_collection": {
    "sensor_reports": { "lag_s": 0.8, "resume_token_age_s": 1.4, "hot_doc_count": 200 }
  },
  "ts": 1742126400.0
}
```

`member_state="STANDALONE_CACHE"` marks the frame as a Tier 1 container so the
topology layer never advertises it as an RS member (see
[`storage_roles`](../topology/topology_overview.md#storage-rs-roles-storage_roles)).

**Aggregator handling.** These frames are routed into a separate `ss_events`
bucket before the normal `mongo_events` reduction. For each event, the
aggregator walks `selective_sync_per_collection` in `ts` order and applies a
**last-writer-wins** overwrite onto `StorageServerSummary.selective_sync_per_collection`:
per-collection entries are replaced, not merged, so the summary always
reflects the freshest lag / resume-token-age / hot-doc-count for each
collection in the window. Storage-facing fields (`avg_repl_lag_s`,
`avg_connections`, `avg_cpu_percent`, `avg_ram_used_mb`, `sample_count`)
default to `0.0` / `None` / `0` so an entry can exist for a container that
emitted *only* selective-sync frames in a given window.

### Control Events

Control events are latency-sensitive signals that should reach the controller
without waiting for the next aggregation window. The aggregator extracts both
top-level and wrapped control events in the receive loop, then publishes them
as mini-summaries with empty `servers` / `storage_servers` and a populated
`control_events` list.

Two producer shapes exist today:

1. Top-level control frames from compute/storage producers:

   ```json
   {
     "event_type": "drain_complete",
     "server_id": "00:00:00:00:00:02",
     "ts": 1742126400.0
   }
   ```

2. Wrapped Tier 1 selective-storage control frames:

   ```json
   {
     "server_mac": "00:00:00:00:00:0e",
     "member_state": "STANDALONE_CACHE",
     "control_events": [
       {
         "event_type": "drain_complete",
         "server_id": "00:00:00:00:00:0e",
         "reason": "scale_down_selective",
         "ts": 1742126400.0
       }
     ],
     "ts": 1742126400.0
   }
   ```

Wrapped Tier 1 control frames are accepted by the aggregator receive loop and
forwarded as immediate mini-summaries, matching the top-level compute/storage
control-event path.

---

## Aggregator (`aggregator.py`)

One aggregator container runs per network, deployed by the build network
scripts. It acts as the bridge between many-to-one event collection and
one-to-many summary publishing.

### Network Assignment

| Property       | LAN 1                  | LAN 2                  |
| -------------- | ---------------------- | ---------------------- |
| Container name | `aggregator_n1`      | `aggregator_n2`      |
| Image          | `local_state_server` | `local_state_server` |
| IP             | `10.0.0.5/24`        | `10.0.1.5/24`        |
| ZMQ PULL       | `:5555`              | `:5555`              |
| ZMQ PUB        | `:5556`              | `:5556`              |

### Windowed Aggregation

Events are collected into a buffer (thread-safe via `threading.Lock`).
Every `WINDOW_S` seconds (default 10), the buffer is drained and processed:

1. **Classify events** by explicit schema.

    The classifier recognizes HTTP request events by top-level `server_id` plus
    request timing, status, CPU, and RAM fields. It recognizes `"mongo_stats"`
    frames by `server_id`, connection, CPU, and RAM fields; `"heartbeat"`
    frames by `server_id`; and Tier 1 selective-sync stats by
    `selective_sync_per_collection` plus `server_mac` or `server_id`. Top-level
    control `event_type` values and wrapped `control_events` are forwarded as
    immediate mini-summaries from the receive loop. Malformed or unsupported
    frames are logged and dropped so one bad producer frame cannot terminate the
    telemetry plane.

2. **Per-server HTTP stats** — grouped by `server_id`, averaged over the window:

   | Output Field          | Computation                                              |
   | --------------------- | -------------------------------------------------------- |
   | `avg_time_total_ms` | mean of `time_total_ms`                                |
   | `avg_time_db_ms`    | mean of `time_db_ms`                                   |
   | `avg_time_proc_ms`  | mean of `time_total_ms - time_db_ms`                   |
   | `request_count`     | count of events                                          |
   | `error_rate`        | fraction with `status_code >= 500`                     |
   | `avg_cpu_percent`   | mean of `cpu_percent`                                  |
   | `avg_ram_used_mb`   | mean of `ram_used_mb`                                  |
   | `last_report_ts`    | most recent `ts` from any event (including heartbeats) |
   | `avg_time_db_read_ms` | mean of `time_db_read_ms` |
   | `avg_time_db_write_ms` | mean of `time_db_write_ms` |
   | `avg_time_db_cmd_count` | mean of `time_db_cmd_count` |
3. **Per-server storage stats** — grouped by `server_id` from `mongo_stats` events:

   | Output Field        | Computation                                                              |
   | ------------------- | ------------------------------------------------------------------------ |
   | `avg_repl_lag_s`  | mean of `repl_lag_s` (or `None` if all standalone)                   |
   | `avg_connections` | mean of `connections_current`                                          |
   | `avg_cpu_percent` | mean of `cpu_percent`                                                  |
   | `avg_ram_used_mb` | mean of `ram_used_mb`                                                  |
   | `sample_count`    | count of `mongo_stats` events                                          |
   | `last_report_ts`  | most recent `ts`                                                       |
   | `member_state`    | latest RS state string (e.g.`"SECONDARY"`) from `mongo_stats` events |
4. **Heartbeat-only nodes** — if a node sent only heartbeats (no data events)
   in the window, it still appears in the summary with `request_count=0` (HTTP)
   or `sample_count=0` (storage) and zero latency fields, so the controller
   knows it's alive.
5. **Domain summary** — computed from HTTP events only:

   | Output Field            | Computation                                                   |
   | ----------------------- | ------------------------------------------------------------- |
   | `total_requests`      | count of all HTTP events                                      |
   | `avg_time_proc_ms`    | mean of `time_total_ms - time_db_ms` across all HTTP events |
   | `avg_time_db_ms`      | mean of `time_db_ms` across all HTTP events                 |
   | `average_cpu_percent` | mean of `cpu_percent` across all HTTP events                |
   | `peak_time_total_ms`  | max of `time_total_ms` across all HTTP events               |
   | `avg_time_db_read_ms` | mean of `time_db_read_ms` across all HTTP events |
   | `avg_time_db_write_ms` | mean of `time_db_write_ms` across all HTTP events |
   | `avg_time_db_cmd_count` | mean of `time_db_cmd_count` across all HTTP events |

The aggregated summary is published as JSON on the ZMQ PUB socket.

---

## Controller-Side Receiver

### Pydantic Models (`models.py`)

All per-node dicts (`servers`, `storage_servers`) are keyed by the node's
MAC address. Pydantic validates the incoming JSON at the transport boundary —
invalid messages are caught and logged before reaching controller logic.

```
TelemetrySummary
  ├── network_id: str
  ├── window_end: float
  ├── servers: dict[str, ServerSummary]
  ├── storage_servers: dict[str, StorageServerSummary]  (default: {})
  ├── domain_summary: DomainSummary | None        (absent in mini-summaries)
  └── control_events: list[dict]                  (drain_complete, rs_secondary_ready, etc.)
```

`last_report_ts: float = 0.0` is present on both `ServerSummary` and
`StorageServerSummary` with a default, so deserialization of payloads from
pre-heartbeat aggregators is backward-compatible.

`ServerSummary` and `DomainSummary` also carry `avg_time_db_read_ms`,
`avg_time_db_write_ms`, and `avg_time_db_cmd_count` as optional fields
defaulted to `0.0`. Payloads from pre-decomposition aggregators parse
unchanged.

### Abstract Interface (`source.py`)

`TelemetryEventSource` is a transport-agnostic ABC with two methods:

- `start()` — begin receiving summaries in the background.
- `get_latest(network_id)` → `TelemetrySummary | None` — return the cached
  latest summary. Thread 1 uses this for WSM cost scoring.

A future `MongoTelemetrySource` (Change Streams) would satisfy the same
interface without touching controller code.

### ZMQ Implementation (`zmq_source.py`)

`ZmqTelemetrySource` connects a ZMQ SUB socket to each aggregator (and
optional peer topology endpoints). A background greenthread
(`os_ken.lib.hub.spawn`) runs the receive loop.

The receive loop uses `eventlet.tpool.execute(self._socket.recv_json)` to
bridge the blocking ZMQ recv into eventlet's cooperative scheduler — this
ensures the OpenFlow event loop continues processing PacketIn events while
waiting for the next telemetry summary.

The source handles two message types on the same ZMQ channel:

- **Telemetry summaries** (no `type` field) — parsed via
  `TelemetrySummary.model_validate()`, cached in `_latest`, and forwarded
  to `on_update` callback.
- **Topology snapshots** (`"type": "topology"`) — forwarded to
  `on_topology_update` callback for peer topology synchronization.

### Controller Integration (`main_n1.py`)

The controller subscribes to both aggregator endpoints plus any peer topology
endpoints, configured via environment variables:

| Variable                    | Default                                     | Description                                            |
| --------------------------- | ------------------------------------------- | ------------------------------------------------------ |
| `AGGREGATOR_ENDPOINTS`    | `tcp://10.0.0.5:5556,tcp://10.0.1.5:5556` | Comma-separated aggregator PUB addresses               |
| `PEER_TOPOLOGY_ENDPOINTS` | *(empty)*                                 | Comma-separated peer controller topology PUB addresses |

The `_on_telemetry_update` callback (Thread 2):

1. Ignores summaries not matching this controller's `LAN_ID`.
2. Processes control events (`drain_complete` → submit `CleanupComputeAlert`;
   `rs_secondary_ready` → promote storage node to VIP pool).
3. Synchronises node tracking (newly seen MACs, absent-node detection with
   birth grace period).
4. Calls `update_server_stats(summary.servers)` and
   `update_storage_stats(summary.storage_servers)` to feed Thread 1's VIP
   routing cost functions.
5. Promotes storage nodes from telemetry when `member_state == "SECONDARY"`
   (fallback path for VIP registration — see elasticity overview).
6. Evaluates domain-level thresholds using a **weighted degradation score**
   per tier (compute and storage separately) with configurable sliding
   windows. See [`elasticy_manager/elasticity_overview.md`](../elasticy_manager/elasticity_overview.md)
   for threshold parameters and anti-thrashing mechanisms.

---

## Planned / Not Yet Implemented / Still to be developed as a concept

### Staleness Cost Function

`last_report_ts` is threaded through the entire pipeline (senders → aggregator
→ models) but is not yet consumed by the WSM cost functions. A future staleness
plan will define weights (`W_STALENESS`, `W_STORAGE_STALENESS`, `STALENESS_MAX_S`)
so that nodes that stop reporting are penalized in server selection.
`last_report_ts = 0.0` will be treated as "not yet seen / cold start" with no
penalty.
