# Controller Telemetry Consumer

## 1. Purpose

The SDN controller consumes aggregated telemetry summaries published by the
per-network aggregators. It uses these summaries to drive VIP routing cost
scoring, elasticity decisions, storage-role synchronisation, and selective-sync
coordination.

## 2. Current Files

- `source/sdn_controller/telemetry/models.py` — Pydantic models
  (`TelemetrySummary`, `ServerSummary`, `StorageServerSummary`,
  `DomainSummary`, `SelectiveSyncCollectionStats`, `EdgeAccessStats`).
- `source/sdn_controller/telemetry/source.py` — `TelemetryEventSource` ABC.
- `source/sdn_controller/telemetry/zmq_source.py` — `ZmqTelemetrySource`
  (ZMQ SUB, `eventlet.tpool.execute` bridge, `_receive_loop`).
- `source/sdn_controller/main_n1.py` — `_on_telemetry_update()` callback,
  `_log_and_update_stats()`, `update_server_stats()`,
  `update_storage_stats()`.

## 3. Telemetry Models

All per-node dicts (`servers`, `storage_servers`) are keyed by the node's MAC
address. Pydantic validates inbound JSON at the transport boundary — invalid
messages are caught and logged before reaching controller logic.

```
TelemetrySummary
  ├── network_id: str
  ├── window_end: float
  ├── servers: dict[str, ServerSummary]
  ├── storage_servers: dict[str, StorageServerSummary]   (default: {})
  ├── domain_summary: DomainSummary | None                (None in mini-summaries)
  └── control_events: list[dict]                          (drain_complete, rs_secondary_ready, …)
```

`ServerSummary` carries per-compute-node latency, error rate, CPU/RAM, and
selective-sync roll-up fields (`access`, `t_db_p95_ms_per_lan`, `op_counters`,
`state`).

`StorageServerSummary` carries per-storage-node replica lag, connections,
CPU/RAM, `member_state`, and `selective_sync_per_collection`.

`DomainSummary` carries window-level aggregates (mean, median, p95) across all
HTTP events plus storage-level CPU/RAM means.

Fields with defaults (e.g. `last_report_ts=0.0`, `avg_time_db_read_ms=0.0`)
ensure backward compatibility with payloads from older aggregators.

## 4. Event-Source Interface

`TelemetryEventSource` is a transport-agnostic ABC with two methods:

- `start()` — begin receiving summaries in the background.
- `get_latest(network_id)` → `TelemetrySummary | None` — return the cached
  latest summary. Thread 1 uses this for WSM cost scoring.

The ZMQ transport is the current implementation. A future
`MongoTelemetrySource` (Change Streams) would satisfy the same interface
without touching controller code.

## 5. ZMQ Subscription and Receive Path

`ZmqTelemetrySource` is instantiated at controller startup with:

- `endpoints` — list of aggregator PUB addresses (both networks) plus optional
  peer topology endpoints, sourced from `AGGREGATOR_ENDPOINTS` and
  `PEER_TOPOLOGY_ENDPOINTS` env vars.
- `on_update` — callback (`_on_telemetry_update`).
- `on_topology_update` — callback for peer topology snapshots.

A single ZMQ SUB socket connects to all endpoints and subscribes to all topics
(`zmq.SUBSCRIBE, b""`).

### Receive Loop

`start()` spawns a background greenthread via `os_ken.lib.hub.spawn` that runs
`_receive_loop()`. The loop uses **`eventlet.tpool.execute(self._socket.recv_json)`**
to bridge the blocking ZMQ `recv` call into eventlet's cooperative scheduler.
This ensures the OpenFlow event loop continues processing PacketIn events while
waiting for the next telemetry summary — it does **not** use `zmq.green`.

The loop handles two message types on the same channel:

- **Telemetry summaries** (no `type` field) — parsed via
  `TelemetrySummary.model_validate()`. Real summaries (non-empty `servers` or
  `storage_servers`) are cached in `_latest` keyed by `network_id`.
  Mini-summaries (control-event pass-throughs) are **not** cached, to avoid
  corrupting WSM cost inputs with empty server maps.
- **Topology snapshots** (`"type": "topology"`) — forwarded to
  `on_topology_update`.

Parsing or receive errors are caught and logged; the loop continues.

## 6. Cached Latest Summary Access

`get_latest(network_id)` returns the most recent real (non-mini) summary for a
given network. Thread 1 uses this for WSM cost scoring; the scale-up path uses
it to fetch the peer network's domain summary for cross-domain threshold
evaluation.

## 7. Controller Update Flow

`_on_telemetry_update(summary)` is the Thread 2 callback. Execution order:

1. **Network gate** — ignores summaries not matching this controller's
   `LAN_ID`.
2. **Node registry sync** — synchronises node tracking (Thread 3 → Thread 2).
3. **Control events** — processes `drain_complete` (cleanup submission) and
   `rs_secondary_ready` (VIP promotion + warm lease).
4. **Mini-summary early return** — if both `servers` and `storage_servers` are
   empty, returns immediately. Also guards against `domain_summary=None` on
   non-mini summaries.
5. **Stats logging & Thread 1 update** — prints domain metrics, calls
   `update_server_stats(summary.servers)` and
   `update_storage_stats(summary.storage_servers)` to feed Thread 1's VIP
   routing cost functions.
6. **Storage-role sync** — calls `sync_storage_roles(summary.storage_servers)`
   to keep the topology snapshot's `storage_roles` accurate.
7. **Selective-sync coordinator** — calls
   `_selective_sync_coordinator.evaluate(summary)` for hotness evaluation and
   coordinator-state machine transitions. Publishes the resulting coordinator
   snapshot via `CoordinatorStatePublisher`.
8. **Fallback VIP promotion** — promotes storage nodes from telemetry when
   `member_state == "SECONDARY"` (fallback path for VIP registration).
9. **Absent-node detection** — `_node_registry.detect_absent(summary)` returns
   MACs that have timed out. Nodes with a pending drain submit Phase B cleanup;
   otherwise a scale-down alert is submitted.
10. **Scale-up evaluation** — delegates to
    `_scaling_policy.evaluate_scale_up()`, gated by active-operation and
    per-tier block flags. Submits resulting alerts to the elasticity manager.
11. **Scale-down evaluation** — delegates to
    `_scaling_policy.evaluate_scale_down_compute()` and
    `_scaling_policy.evaluate_scale_down_storage()`, each gated by cooldown
    timers. Picks candidates and submits alerts.

## 8. Control Events Versus Window Summaries

Control events (`drain_complete`, `rs_secondary_ready`) arrive as
mini-summaries — `TelemetrySummary` frames with empty `servers` /
`storage_servers`, no `domain_summary`, and a populated `control_events` list.

The aggregator forwards these immediately (not batched in the window). The
controller processes them on arrival via the same `_on_telemetry_update`
callback path but returns early after step 4 (the mini-summary early return).

This separation means control events never pollute the cached `_latest` summary
map or the domain-level aggregate statistics used for scaling decisions.

## 9. Current Downstream Consumers

Telemetry summaries feed four controller subsystems:

| Consumer                              | Thread        | Summary Fields Used                                                                                                                |
| ------------------------------------- | ------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| **VIP routing**                 | Thread 1      | `servers[*].avg_time_total_ms`, `avg_time_db_ms`, `avg_time_proc_ms`, `avg_cpu_percent`, `error_rate`, `request_count` |
| **Elasticity**                  | Thread 2 → 3 | `domain_summary.*`, `servers[*].last_report_ts`, `storage_servers[*].sample_count`                                           |
| **Storage-role sync**           | Thread 2      | `storage_servers[*].member_state`                                                                                                |
| **Selective-sync coordination** | Thread 2      | `servers[*].access`, `op_counters`, `t_db_p95_ms_per_lan`; `storage_servers[*].selective_sync_per_collection`              |

## 10. Short Future Transport Note

The current ZMQ SUB path is functional. A future transport revision may move
summaries to HTTP with periodic ingest and backpressure (the
`TelemetryEventSource` ABC already isolates the transport from controller
logic). This is an optimisation, not a blocker for the current pipeline.
