# Storage Telemetry

## 1. Purpose

The storage-side telemetry producer runs as a lightweight Python sidecar
alongside `mongod` inside every `edge_storage_server` container. It pushes
replica-set state, connection counts, and resource-usage metrics to the
per-network aggregator via ZMQ PUSH.

## 2. Current Files

- `source/docker/edge_storage_server/mongo_telemetry.py` — opcounter-based
  activity detection, `mongo_stats` / heartbeat event emission, RS self-join,
  RS readiness wait, and cgroup-based resource accounting.

## 3. Local MongoDB Inspection

The sidecar inspects the MongoDB server running **inside its own container**,
not an arbitrary replica-set member selected after topology discovery. It uses
`_local_mongo_client()` which returns a `MongoClient` with
`directConnection=True` pinned to `MONGO_URI` (default
`mongodb://localhost:27018/`). This keeps readiness checks, telemetry queries,
and replica-set state inspection anchored to the local `mongod`.

## 4. Activity Detection via Opcounters Delta

The sidecar does **not** push on every poll cycle. It reads
`serverStatus.opcounters` and compares against the previous poll's snapshot:

- **CRUD opcounters** — `insert`, `query`, `update`, `delete`, `getmore`. Any
  positive delta means real client activity → emit a `mongo_stats` event.
- **`command` opcounter is ignored** — in a replica set, internal
  heartbeat/election commands inflate it every cycle even when idle.
- **First poll** — captures the baseline without reporting
  (`_prev_opcounters` starts as `None`). The sidecar's own 3 internal MongoDB
  connections (created by `MongoClient`) therefore do not produce a spurious
  `mongo_stats` event before any real client has connected.
- **First `SECONDARY` transition** — immediately pushes one bootstrap
  `mongo_stats` sample after `_wait_for_ready()` confirms the node is
  `SECONDARY`, so the controller can see a newly promoted backend before the
  next normal activity-driven poll.
- **Failure reset** — if `serverStatus` or `replSetGetStatus` raises
  `PyMongoError`, `_prev_opcounters` is reset to `None` so the next
  successful poll always emits.

## 5. `mongo_stats` Payload

```
{
  "event_type":          "mongo_stats",
  "server_id":           "<MAC>",
  "ts":                  <unix_epoch>,
  "repl_lag_s":          <float | None>,
  "member_state":        "<PRIMARY|SECONDARY|...>",
  "connections_current": <int>,
  "cpu_percent":         <float>,
  "ram_used_mb":         <float>
}
```

| Field | Source |
| ----- | ------ |
| `repl_lag_s` | `replSetGetStatus` — seconds behind primary. `0.0` if this IS the primary; `None` if standalone (RS not initialised). |
| `member_state` | `replSetGetStatus` — RS state string (e.g. `"SECONDARY"`, `"PRIMARY"`). Used by the controller's VIP promotion fallback path. |
| `connections_current` | `serverStatus.connections.current`. Set to `-1` on query failure. |
| `cpu_percent` | `container_cpu_percent()` — cgroup-based (see §6). |
| `ram_used_mb` | `container_ram_used_mb()` — cgroup-based (see §6). |

## 6. Container Resource Accounting

CPU and RAM are read from the container's **cgroup files**, not from `psutil`
(which reports host-wide `/proc` values).

**CPU:** `container_cpu_percent()` normalises to the container's quota
(100% = full quota). Reads `cpu.stat` (cgroup v2) or `cpuacct.usage` (cgroup
v1), computes delta between successive polls, and divides by
`_effective_cpu_count()`. The first call returns 0.0 (no baseline yet). No
caching layer — polled periodically by the telemetry loop at `INTERVAL_S`
(default 0.5 s), so delta windows are naturally wide enough.

**RAM:** `container_ram_used_mb()` reads `memory.current` (cgroup v2) or
`memory.usage_in_bytes` (cgroup v1), converted to MiB.

## 7. Heartbeats and Bootstrap Visibility

### Emission Decision (`_push_stats`)

Each poll cycle, `_push_stats` decides whether to emit and what event type:

1. **Bootstrap `SECONDARY`** — if `force_bootstrap_secondary=True`,
   `member_state == "SECONDARY"`, and the bootstrap hasn't been sent yet →
   `mongo_stats`.
2. **Activity-driven** — if `_has_client_activity()` returns `True` →
   `mongo_stats`.
3. **Heartbeat** — if `HEARTBEAT_ENABLED` and the interval has elapsed since
   the last send → `heartbeat`.
4. Otherwise, skip emission.

### Static-vs-Dynamic Gating

`HEARTBEAT_ENABLED` defaults to `false`. Only the literal env-var string
`"true"` enables periodic heartbeats:

- **Static containers** (the primary DB `edge_storage_server_n{1,2}`) opt in
  via `HEARTBEAT_ENABLED=true` in their docker run command. Heartbeats are
  their only liveness signal during quiet periods.
- **Dynamic storage secondaries** keep the default disabled. Their idleness is
  reclaimed by scale-down; true failure is detected by the telemetry-window
  absence timeout (`TELEMETRY_TIMEOUT_WINDOWS × WINDOW_S`, default 180 s).

### ZMQ Socket Creation

The ZMQ PUSH socket is created **after** `_rs_self_join()` (which ensures eth0
exists via `_wait_for_network()`) but **before** `_wait_for_ready()`. This
means diagnostic heartbeats can reach the controller even if the RS join fails
or the node is stuck in `STARTUP2`.

### `rs_secondary_ready` Control Event

When `_wait_for_ready()` returns `"SECONDARY"`, the sidecar immediately emits a
`rs_secondary_ready` control event (fast path for VIP promotion) followed by
`_push_stats(force_bootstrap_secondary=True)`. If the state is `"PRIMARY"`, no
event is emitted. If the state is `None` (timeout), the sidecar enters the
telemetry loop anyway so the controller still receives diagnostics.

## 8. Replica-State Notes

- **`_repl_lag_and_state()`** computes replication lag as
  `(primary_optime - my_optime).total_seconds()`, clamped to `>= 0.0`. Returns
  `(0.0, "PRIMARY")` for primaries and `(None, None)` for standalones.
- **`_log_repl_transition()`** logs state changes (e.g. `STARTUP2 → SECONDARY`)
  and lag bucket transitions (`lt1s` / `lt5s` / `ge5s`) at INFO level.
- **`member_state`** is the **latest** RS state per poll. The aggregator
  carries forward the last-reported `member_state` in each window summary,
  which the controller uses for VIP promotion fallback.

## 9. Related Components

- **Aggregation** — [aggregation_publication/aggregator.md](../aggregation_publication/aggregator.md)
- **Controller consumption** — [controller_side/controller_telemetry_consumer.md](../controller_side/controller_telemetry_consumer.md)
- **Compute producer** — [compute_telemetry.md](compute_telemetry.md)
- **Selective-sync producer** — [selective_sync_telemetry.md](selective_sync_telemetry.md)
