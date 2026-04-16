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
  "server_id":     "00:00:00:00:00:02",
  "ts":            1742126400.0,
  "time_total_ms": 85.2,
  "time_db_ms":    47.1,
  "status_code":   200,
  "request_type":  "read",
  "cpu_percent":   34.7,
  "ram_used_mb":   128.3
}
```

| Field             | Source                                                                        |
| ----------------- | ----------------------------------------------------------------------------- |
| `time_total_ms` | Wall clock from `before_request` to `after_request`                       |
| `time_db_ms`    | Accumulated via the `timed_db()` context manager wrapping all MongoDB calls |
| `cpu_percent`   | `psutil.cpu_percent()`                                                      |
| `ram_used_mb`   | `psutil.virtual_memory().used / 1 MiB`                                      |
| `request_type`  | `"write"` for POST/PUT/PATCH/DELETE, `"read"` otherwise                   |

`zmq.NOBLOCK` ensures the hook never blocks the HTTP response — events are
silently dropped if the aggregator is temporarily unavailable.

### Heartbeat Events

A daemon thread sends a heartbeat every `HEARTBEAT_INTERVAL_S` (default 60 s)
when the server is idle. The countdown resets after every request-driven event,
so a busy server never sends redundant heartbeats.

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
hooks and spawns the heartbeat thread. Called once at app startup.

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

When idle, a `heartbeat` event is sent every `HEARTBEAT_INTERVAL_S` (default
60 s) for liveness.

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
as liveness signals.

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

1. **Classify events** by `event_type`:

   - No `event_type` → HTTP event from edge servers
   - `"mongo_stats"` → storage sidecar activity
   - `"heartbeat"` → liveness signal (either type)
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
