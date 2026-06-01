# Compute Telemetry

## 1. Purpose

The compute-side telemetry producer runs inside every `edge_server` container.
It emits per-HTTP-request latency, DB timing decomposition, and resource-usage
metrics to the per-network aggregator via ZMQ PUSH.

## 2. Current Files

- `source/docker/edge_server/source/telemetry.py` — `MetricSender` ABC,
  `ZmqMetricSender`, Flask `before_request`/`after_request` hooks, heartbeat
  loop, and cgroup-based resource accounting.
- `source/docker/edge_server/source/db_monitor.py` — pymongo `CommandListener`
  (`_DbTimingListener`) that accumulates per-request read/write DB command
  durations on Flask `g`.

## 3. Server Identity and Aggregator Address

Each container identifies itself by its **MAC address**, discovered from
`/sys/class/net/<iface>/address`. The lookup prefers the `IFACE` env var
(default `eth0`) and falls back to scanning all non-loopback interfaces. The
MAC is used as `server_id` throughout the pipeline and matches the key in the
controller's VIP pool.

Two override paths exist for controlled environments:

- `OWN_MAC` — if set and matches the MAC regex, it is used directly instead of
  sysfs discovery. Invalid values are logged and ignored.
- `OWN_IP` — validated IPv4 override for `_discover_own_ip()`, used primarily
  by the storage sidecar but available here for symmetry.

The aggregator address is resolved at startup:

1. `AGGREGATOR_PULL_ADDR` env var, if set explicitly.
2. Otherwise derived from `LAN_ID` (e.g. `lan1` → `tcp://10.0.0.5:5555`,
   `lan2` → `tcp://10.0.1.5:5555`).

`SERVER_MAC` is computed at module load. If the network interface is not yet
available (container starts with `--network none`), it caches `"unknown"` and
`_get_server_mac()` re-discovers on first use.

## 4. Request Event Emission

`init_telemetry(app, sender=None, get_drain_state=None)` wires up Flask hooks
and background threads. Called once at app startup.

### `before_request`

Initialises per-request state on Flask `g`:

- `g.time_start` — `time.monotonic()` baseline.
- `g.time_db_elapsed` — accumulated seconds inside `timed_db()` blocks.
- `g.time_db_read_s`, `g.time_db_write_s`, `g.time_db_cmd_count` — populated
  by the `_DbTimingListener` (see §5).
- `g.access_records`, `g.op_counts`, `g.time_db_per_lan` — selective-sync
  piggyback containers (see §9).
- `g.request_lease_outcomes` — projected lease outcomes appended near response
  end by `app.py`.

### `after_request`

Builds and emits one event per HTTP response. Fields:

| Field | Source |
| ----- | ------ |
| `server_id` | `_get_server_mac()` |
| `ts` | `time.time()` |
| `time_total_ms` | `(monotonic() - g.time_start) * 1000` |
| `time_db_ms` | `g.time_db_elapsed * 1000` |
| `time_db_read_ms` | `g.time_db_read_s * 1000` |
| `time_db_write_ms` | `g.time_db_write_s * 1000` |
| `time_db_cmd_count` | `g.time_db_cmd_count` |
| `status_code` | `response.status_code` |
| `request_type` | `"write"` for POST/PUT/PATCH/DELETE, `"read"` otherwise |
| `cpu_percent` | `container_cpu_percent()` (cached, 1 s TTL) |
| `ram_used_mb` | `container_ram_used_mb()` |
| `state` | `get_drain_state()` (typically `"active"` or `"draining"`) |

The event is sent via `ZmqMetricSender.send()` with `zmq.NOBLOCK` — the HTTP
response is never blocked by a slow or unavailable aggregator.

## 5. DB Timing Decomposition

`_DbTimingListener` (registered globally via `db_monitor.register()`) is a
pymongo `CommandListener` that classifies every MongoDB command into one of
three families:

| Family | Commands | Accumulator |
| ------ | -------- | ----------- |
| Reads | `find`, `aggregate`, `count`, `distinct`, `getMore`, `findAndModify` | `g.time_db_read_s` |
| Writes | `insert`, `update`, `delete` | `g.time_db_write_s` |
| Ignored | `hello`, `isMaster`, `ping`, `buildInfo`, `saslStart`, `saslContinue`, `endSessions`, `getParameter`, `killCursors`, `listDatabases`, `listCollections`, `listIndexes`, `connectionStatus` | *(skipped)* |

Commands outside `_IGNORED_CMDS` that are neither reads nor writes still
increment `g.time_db_cmd_count` but do not accumulate read/write time. The
listener also records the last command name, database, target collection,
failure flag, and duration on `g` for diagnostic logging.

Commands issued outside a Flask request context (driver-internal operations)
are silently skipped via `RuntimeError` guard on `g` access.

> `time_db_read_ms + time_db_write_ms` is not expected to equal `time_db_ms`.
> `time_db_ms` wraps the `timed_db()` context manager (connection checkout,
> server selection, serialisation); the listener measures only command RTT.
> The gap is diagnostic.

## 6. Container Resource Accounting

CPU and RAM are read from the container's **cgroup files**, not from `psutil`
(which reports host-wide `/proc` values that are not namespaced inside Docker).

**CPU:** `container_cpu_percent()` returns a percentage normalised to the
container's quota (100% = full quota). The implementation:

- Reads `cpu.stat` (cgroup v2) or `cpuacct.usage` (cgroup v1) for cumulative
  CPU usage in microseconds.
- Computes delta between successive calls, divided by elapsed wall-clock time.
- Normalises by `_effective_cpu_count()` — the container's cgroup quota
  (`cpu.max` or `cpu.cfs_quota_us / cpu.cfs_period_us`), falling back to
  `os.cpu_count()`.
- Applies a **1-second cache TTL** so per-request emissions don't sample
  sub-millisecond windows from the same baseline.

**RAM:** `container_ram_used_mb()` reads `memory.current` (cgroup v2) or
`memory.usage_in_bytes` (cgroup v1), converted to MiB.

## 7. Heartbeats and Bootstrap Visibility

### Periodic Heartbeats

A daemon thread sends a heartbeat every `HEARTBEAT_INTERVAL_S` (default 60 s)
when the server has not emitted a request-driven event within that interval.
The countdown resets after every `after_request` emission, so a busy server
never sends redundant heartbeats.

Heartbeats are gated by `HEARTBEAT_ENABLED`:

- Default: `false`. Dynamic nodes keep this disabled — idleness is handled by
  scale-down, and failure by the telemetry-window absence timeout.
- Static containers (`edge_server_n{1,2}`) opt in via
  `HEARTBEAT_ENABLED=true` in their docker run command.

The heartbeat event carries `cpu_percent`, `ram_used_mb`, and `state` in
addition to `server_id` and `ts`.

### Bootstrap Heartbeat

A separate one-shot thread (`_bootstrap_heartbeat_loop`) polls until a real
MAC address is available, then emits a single heartbeat-shaped event. This
makes a newly spawned backend visible to the controller before its first real
HTTP request. Once sent, the thread exits.

## 8. Sender Abstraction and Startup Wiring

`MetricSender` is an ABC with a single `send(event: dict) -> None` method. The
production implementation is `ZmqMetricSender`, which:

- Resolves the aggregator address from `AGGREGATOR_PULL_ADDR` or `LAN_ID`.
- Creates a ZMQ PUSH socket and connects at construction time.
- Sends with `zmq.NOBLOCK`; silently drops events on `zmq.Again`.

The ABC allows injecting a test double for unit testing without a live ZMQ
socket.

`init_telemetry()` accepts an optional `sender` and `get_drain_state` callable
(defaulting to `lambda: "active"`), then:

1. If `HEARTBEAT_ENABLED`, spawns the periodic heartbeat daemon thread.
2. Always spawns the bootstrap heartbeat thread.
3. Registers `before_request` and `after_request` Flask hooks.

## 9. Relationship to Selective-Sync Fields

The per-request event also carries selective-sync piggyback fields populated
by the `platform_cache._CachedCollection` wrapper via Flask `g`:

- `time_db_ms_per_lan` — per-owner-LAN DB time accumulated by `timed_db(lan)`.
- `access_records` — one entry per cross-region point read.
- `op_counts` — `{owner_lan: {collection: {op_type: count}}}` tree.

These ride on the existing event path — no new ZMQ event type, no new thread.
For requests that never touch a wrapped collection, all three fields are empty.
Detailed field semantics and aggregator folding are documented in
[selective_sync_telemetry.md](selective_sync_telemetry.md).

## 10. Related Components

- **Aggregation** — [aggregation_publication/aggregator.md](../aggregation_publication/aggregator.md)
- **Controller consumption** — [controller_side/controller_telemetry_consumer.md](../controller_side/controller_telemetry_consumer.md)
- **Storage producer** — [storage_telemetry.md](storage_telemetry.md)
- **Selective-sync producer** — [selective_sync_telemetry.md](selective_sync_telemetry.md)
- **DB timing deep-dive** — [implementation/db_timing_decomposition.md](../implementation/db_timing_decomposition.md)
