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
- `source/sdn_controller/telemetry/polling_source.py` — `PollingTelemetrySource`
  (HTTP polling, concurrent aggregator requests, dedup by `window_seq`).
- `source/sdn_controller/telemetry/event_preserving_source.py` —
  `EventPreservingTelemetrySource` (HTTP window-log pull, in-order, ack).
- `source/sdn_controller/telemetry/delayed_source.py` —
  `DelayedEventPreservingTelemetrySource` (HTTP window-log pull + FIFO hold
  queue, release at `window_end + DELAY_S`).
- `source/sdn_controller/telemetry/delivery_log.py` — shared CSV delivery
  logger + best-effort ack client.
- `source/sdn_controller/main_n1.py` — `_on_telemetry_update()` callback,
  `_run_housekeeping()` ticker, `_log_and_update_stats()`,
  `update_server_stats()`, `update_storage_stats()`.

## 3. Telemetry Models

All per-node dicts (`servers`, `storage_servers`) are keyed by the node's MAC
address. Pydantic validates inbound JSON at the transport boundary — invalid
messages are caught and logged before reaching controller logic.

```
TelemetrySummary
  ├── network_id: str
  ├── window_end: float
  ├── window_seq: int | None                  (None for control mini-summaries)
  ├── window_id: str | None                   (f"{network_id}:{window_seq}")
  ├── overload: bool                           (producer-side label, RQ1)
  ├── servers: dict[str, ServerSummary]
  ├── storage_servers: dict[str, StorageServerSummary]   (default: {})
  ├── domain_summary: DomainSummary | None                (None in mini-summaries and empty windows)
  └── control_events: list[dict]                          (drain_complete, rs_secondary_ready, …)
```

`window_seq` discriminates summary kinds: **control mini-summaries** have
`window_seq=None`; **real windows** — including empty/idle windows with empty
`servers` / `storage_servers` — always carry a monotonic `window_seq`. Empty
windows are real windows: the empty-window early return in § 7 keys on empty
server maps, but `_last_summary` (the Design-B ticker's state) advances through
them because they carry a `window_seq`.

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

Four implementations exist:

| Transport | Class | Mode |
|---|---|---|
| ZMQ PUB/SUB | `ZmqTelemetrySource` | Push (default, `TELEMETRY_SOURCE=zmq`) |
| HTTP polling | `PollingTelemetrySource` | Poll (`TELEMETRY_SOURCE=poll`) |
| HTTP window-log pull | `EventPreservingTelemetrySource` | Event-preserving (`TELEMETRY_SOURCE=event_preserving`) |
| HTTP window-log pull + delay | `DelayedEventPreservingTelemetrySource` | Delayed event-preserving (`TELEMETRY_SOURCE=delayed_event_preserving`) |

All sources retrieve from both aggregators (each controller sees both LANs).
Only the delivery mechanism differs.

## 5. ZMQ Subscription and Receive Path (Push Mode)

In push mode (`TELEMETRY_SOURCE=zmq`, default) the controller creates a
single `ZmqTelemetrySource` that receives telemetry summaries, control
events, and topology snapshots on one ZMQ SUB socket. In poll mode
(`TELEMETRY_SOURCE=poll`) telemetry summaries arrive via HTTP polling
(see § 10) while a ZMQ SUB socket remains active for control events and
topology only.

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

In the non-ZMQ delivery modes (§ 10) a separate ZMQ SUB control channel is
kept for control events and topology; its forward predicate is
`summary.window_seq is None` — only control mini-summaries pass through.
Empty real windows (which carry a `window_seq`) are never forwarded on ZMQ,
so they cannot bypass `DELAY_S` or skip the delivery log.

## 6. Cached Latest Summary Access

`get_latest(network_id)` returns the most recent real (non-mini) summary for a
given network. Thread 1 uses this for WSM cost scoring; the scale-up path uses
it to fetch the peer network's domain summary for cross-domain threshold
evaluation.

## 7. Controller Update Flow

`_on_telemetry_update(summary)` is the Thread 2 callback. Execution order:

1. **Network gate** — ignores summaries not matching this controller's
   `LAN_ID`.
2. **`_last_summary` guard** — for local-LAN summaries, a real window
   (`window_seq is not None`, including empty windows) is cached as
   `_last_summary`; control mini-summaries (`window_seq=None`) never update
   it. This is the Design-B ticker's single source of truth — peer-LAN
   summaries and mini-summaries never reach it.
3. **Node registry sync** — synchronises node tracking (Thread 3 → Thread 2).
4. **Control events** — processes `drain_complete` (cleanup submission) and
   `rs_secondary_ready` (VIP promotion + warm lease).
5. **Empty-window early return** — control mini-summaries and empty real
   windows both have empty `servers` / `storage_servers` and return here
   (after the `_last_summary` guard, so the ticker still observes empty
   windows). Also guards against `domain_summary=None` on non-mini summaries.
6. **Stats logging & Thread 1 update** — prints domain metrics, calls
   `update_server_stats(summary.servers)` and
   `update_storage_stats(summary.storage_servers)` to feed Thread 1's VIP
   routing cost functions.
7. **Storage-role sync** — calls `sync_storage_roles(summary.storage_servers)`
   to keep the topology snapshot's `storage_roles` accurate.
8. **Selective-sync coordinator** — calls
   `_selective_sync_coordinator.evaluate(summary)` for hotness evaluation and
   coordinator-state machine transitions. Publishes the resulting coordinator
   snapshot via `CoordinatorStatePublisher`.
9. **Fallback VIP promotion** — promotes storage nodes from telemetry when
   `member_state == "SECONDARY"` (fallback path for VIP registration).
10. **Reserve & cross-region** — processes reserve prepare failures,
    maintains the persistent storage reserve (prepare / tick pending
    activation / auto-activate), and evaluates cross-region warm-standby
    activation.
11. **Scale-up evaluation** — in the `dual` (default) mode delegates to
    `_scaling_policy.evaluate_scale_up()`; in RQ2 arms (`SCALEUP_POLICY` ≠
    `dual`) it evaluates per-tier `ScaleUpVerdict`s and routes selection
    through `PolicyGate.select()`, emitting at most one action per window.
    Both paths are gated by active-operation and per-tier block flags, and
    submit resulting alerts to the elasticity manager.

Absent-node detection and scale-down evaluation were **removed** from this
callback and moved to the fixed ticker (see below) — they are never duplicated
here.

### Design-B Housekeeping Split (Fixed Ticker)

`_housekeeping_loop` is an eventlet greenthread in the same hub as the
delivery/poll/control loops. It sleeps `CONTROL_TICK_S` (default 10 s) and
runs `_run_housekeeping()` — time-based work moved off telemetry arrival so
it runs on a fixed clock rather than on delivery cadence:

- **Absent-node detection** — `_node_registry.detect_absent(s)` returns MACs
  whose last reported presence is older than `_TELEMETRY_TIMEOUT_S`. Nodes
  with a pending drain submit Phase B cleanup; an absent reserve is handled
  as reserve loss; otherwise a scale-down alert is submitted.
- **Scale-down evaluation** — compute and storage, once per delivered
  `window_seq` (`_last_scale_eval_seq`), preserving cooldown and `is_busy()`
  gating. Empty windows (`domain_summary=None`) skip evaluation but still
  advance `_last_scale_eval_seq`.
- The tick only acts when `_last_summary` is a real local-LAN window
  (`window_seq is not None`); `_run_housekeeping` contains **no
  blocking/yielding calls** so it stays atomic between greenthread yield
  points.
- **All modes:** the split is controller-level and applies to every delivery
  mode, including `zmq` — RQ2/RQ3 re-runs also use time-based housekeeping.
  Scale-down dedups per `window_seq` (at most once per window); windows
  delivered between ticks are intentionally not individually evaluated (it is
  a time-based check of the latest delivered state; `CONTROL_TICK_S = WINDOW_S`
  gives one consideration per window in steady state).
- **Restart caveat:** exactly-once delivery holds absent controller restarts. A
  mid-run restart re-pulls from the durable window log and re-delivers windows
  (duplicate decisions); the RQ1 protocol must not restart controllers mid-run.

### Decision Log

`_log_decision(action_type, action, window_id)` appends a CSV row
(`ts, network_id, window_id, action_type, action`) to `DECISION_LOG_PATH`
(default `/tmp/decision_log.csv`) at every Thread-2 capacity-action submission
site: scale-up per-alert submit, compute/storage scale-down submit, absent-node
cleanup, reserve-loss cleanup, reserve activation, cross-region activation,
and cancel-compute-drain.

### Flow Isolation (RQ3)

The control-event dispatcher also handles `request_complete` events
(`process_flow_events` in `source/sdn_controller/control_events.py`): when
`VIP_FLOW_ISOLATION=1` (default `0`), each `request_complete` deletes that
client's `VIP_SERVER` DNAT+SNAT flow using the recorded `_vip_server_client_map`
binding, forcing a fresh backend-selection event per request. It is a no-op
when `VIP_FLOW_ISOLATION=0`. See
[RQ3 — Readiness Propagation and Traffic Admission](../../../research_questions/v2/rq3/rq3_preparation.md).

## 8. Control Events Versus Window Summaries

Control events (`drain_complete`, `rs_secondary_ready`) arrive as
mini-summaries — `TelemetrySummary` frames with empty `servers` /
`storage_servers`, no `domain_summary`, a populated `control_events` list, and
`window_seq=None`.

The aggregator forwards these immediately (not batched in the window). The
controller processes them on arrival via the same `_on_telemetry_update`
callback path but returns early after step 5 (the empty-window early return).

Mini-summaries are discriminated by `window_seq=None` — empty real windows
also have empty server maps but carry a `window_seq` and are real windows.
This separation means control events never pollute the cached `_latest` summary
map, the `_last_summary` ticker state, or the domain-level aggregate statistics
used for scaling decisions.

## 9. Current Downstream Consumers

Telemetry summaries feed four controller subsystems:

| Consumer                              | Thread        | Summary Fields Used                                                                                                                |
| ------------------------------------- | ------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| **VIP routing**                 | Thread 1      | `servers[*].avg_time_total_ms`, `avg_time_db_ms`, `avg_time_proc_ms`, `avg_cpu_percent`, `error_rate`, `request_count` |
| **Elasticity**                  | Thread 2 → 3 | `domain_summary.*`, `servers[*].last_report_ts`, `storage_servers[*].sample_count`                                           |
| **Storage-role sync**           | Thread 2      | `storage_servers[*].member_state`                                                                                                |
| **Selective-sync coordination** | Thread 2      | `servers[*].access`, `op_counters`, `t_db_p95_ms_per_lan`; `storage_servers[*].selective_sync_per_collection`              |

## 10. HTTP Delivery Modes (RQ1)

Three HTTP delivery modes exist alongside the default ZMQ push:

- **`poll`** — `PollingTelemetrySource` polls both aggregators' latest-summary
  cache endpoints at a configurable interval (`POLL_INTERVAL_S`, default 10 s).
  Both aggregators are polled **concurrently** via `hub.spawn` so the two
  summaries arrive at nearly the same instant, minimising skew between the
  controller's LAN1/LAN2 data views. Deduplication is keyed by `window_seq`
  (robust to aggregator-restart seq resume). Every observed window — including
  empty ones — is passed to `on_update` and recorded in the delivery log; only
  non-empty windows are cached in `_latest` (empty windows would corrupt WSM
  inputs).
- **`event_preserving`** — `EventPreservingTelemetrySource` pulls windows in
  order from the durable window log (`GET /windows?after_seq=last_seq&limit=1`),
  records a delivery-log row + best-effort ack per window, and advances
  `last_seq`. On `410 aged_out` it records a gap row for the full missed range
  and advances (defensive gap recovery).
- **`delayed_event_preserving`** — `DelayedEventPreservingTelemetrySource`
  pulls in order exactly as `event_preserving` but holds each window in a FIFO
  queue and releases it when `now ≥ window_end + DELAY_S` (default 30 s). No
  replay / no backfill; backlog drains one-per-step at due times.

**Control events** (`drain_complete`, `rs_secondary_ready`) and **peer
topology snapshots** remain on **ZMQ push** — they are urgent operational
signals that must always arrive immediately, regardless of the telemetry
delivery mechanism under test. In every non-ZMQ mode the controller keeps a
ZMQ SUB control channel whose forward predicate is `summary.window_seq is None`:
only control mini-summaries pass through, so empty real windows can never
bypass `DELAY_S` or skip the delivery log.

An unknown `TELEMETRY_SOURCE` value is logged and falls back to `poll`.

See `docs/operation/telemetry/implementation/rq1_delivery_semantics/rq1_delivery_semantics_plan.md`.
