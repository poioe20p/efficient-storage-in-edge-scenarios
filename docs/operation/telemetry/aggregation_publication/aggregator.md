# Aggregator

## 1. Purpose

One aggregator container runs per network. It collects raw events from all
producers on that network via ZMQ PULL, buffers them into time windows, reduces
them into per-server and domain-level summaries, publishes the summaries
via ZMQ PUB (push), persists every window to a durable window log, and serves
the log over HTTP (poll + RQ1 delivery modes). See § 12 and § 13.

## 2. Current File

- `source/docker/local_state_server/aggregator.py` — single-module
  implementation: receive loop, publish loop, classification, windowed
  reduction, selective-sync folding.

## 3. Network Placement and Sockets

Each aggregator is deployed as `aggregator_n{1,2}` on the corresponding LAN:

| Property | LAN 1 | LAN 2 |
| -------- | ----- | ----- |
| Container | `aggregator_n1` | `aggregator_n2` |
| IP | `10.0.0.5` | `10.0.1.5` |
| ZMQ PULL | `tcp://0.0.0.0:5555` | `tcp://0.0.0.0:5555` |
| ZMQ PUB | `tcp://0.0.0.0:5556` | `tcp://0.0.0.0:5556` |

The PULL address can be overridden via `PULL_ADDR`; PUB via `PUB_ADDR`.
Producers derive the PULL address from `AGGREGATOR_PULL_ADDR` or `LAN_ID`
(e.g. `lan1` → `tcp://10.0.0.5:5555`).

`NETWORK_ID` is set from the environment and included in every published
summary so the controller can identify which network a summary came from.

## 4. Receive-Loop Classification

The `_receive_loop` runs on a daemon thread, blocking on
`pull.recv_json()`. Each received frame is classified:

### Control Events (immediate forwarding)

If `_extract_control_events()` returns a non-empty list, the frame is
published immediately as a mini-summary and **not** buffered into the
aggregation window. See § 5.

### Window Events (buffered)

Otherwise the frame is appended to `_buffer` under `threading.Lock`. The
publish loop classifies buffered events into five buckets:

| Bucket | Classifier | Key field |
| ------ | ---------- | --------- |
| HTTP request | `_is_http_event()` — requires `server_id`, `time_total_ms`, `time_db_ms`, `status_code`, `cpu_percent`, `ram_used_mb` | `server_id` |
| `mongo_stats` | `_is_mongo_event()` — `event_type == "mongo_stats"` plus `server_id`, `connections_current`, `cpu_percent`, `ram_used_mb` | `server_id` |
| Heartbeat | `_is_heartbeat_event()` — `event_type == "heartbeat"` with non-empty `server_id` | `server_id` |
| Selective-sync | `_is_selective_sync_event()` — has `selective_sync_per_collection` dict and either `server_mac` or `server_id` | `server_mac` or `server_id` |
| Malformed | Any frame not matching the above | *(dropped & logged)* |

Malformed frames are logged with their keys and dropped — one bad producer
frame cannot terminate the telemetry plane.

## 5. Immediate Control-Event Forwarding

`_extract_control_events()` recognises two shapes:

1. **Top-level** — `event_type` is `"drain_complete"` or
   `"rs_secondary_ready"`.
2. **Wrapped** — `control_events` is a list of dicts, each with a recognised
   `event_type`. Non-dict entries and unsupported event types are logged and
   dropped.

Extracted control events are published immediately as a **mini-summary**:

```json
{
  "network_id":     "<NETWORK_ID>",
  "window_end":     <unix_epoch>,
  "servers":        {},
  "storage_servers": {},
  "control_events": [<extracted events>]
}
```

The controller processes these on arrival without waiting for the next window
close. Control-event frames are **not** buffered into the window.

`request_complete` (RQ3 flow isolation) is now a whitelisted control-event type
and is forwarded the same way in control mini-summaries. See
[RQ3 — Readiness Propagation and Traffic Admission](../../../research_questions/v2/rq3/rq3_preparation.md).

## 6. Windowed Aggregation

Every `WINDOW_S` seconds (default 10), the publish loop:

1. Drains `_buffer` under lock into a local `window` list.
2. Computes `last_seen` — per-`server_id` max `ts` across all events.
3. Classifies events into the five buckets (§ 4).
4. Reduces HTTP events → `servers` (§ 7).
5. Reduces `mongo_stats` events → `storage_servers` (§ 8).
6. Promotes heartbeat-only nodes (§ 9).
7. Folds selective-sync frames (§ 11).
8. Computes domain summary (§ 10).
9. Publishes the `TelemetrySummary` JSON frame on the PUB socket (§ 12).

Every `WINDOW_S` interval is a window with a monotonic `window_seq`
(`window_id = f"{NETWORK_ID}:{window_seq}"`). Since 2026-07-31 (RQ1 delivery
semantics) **every window is always published** — a window with no valid
events still closes with `servers={}`, `storage_servers={}`,
`domain_summary=None`, `overload=False`, and its `window_seq`, so the window
universe stays contiguous for the analyzer.

## 7. HTTP Server Summaries

HTTP events are grouped by `server_id`. For each server:

| Output Field | Computation |
| ------------ | ----------- |
| `avg_time_total_ms` | `mean(time_total_ms)` |
| `avg_time_db_ms` | `mean(time_db_ms)` |
| `avg_time_proc_ms` | `mean(time_total_ms - time_db_ms)` |
| `request_count` | `len(events)` |
| `error_rate` | fraction with `status_code >= 500` |
| `avg_cpu_percent` | `mean(cpu_percent)` |
| `avg_ram_used_mb` | `mean(ram_used_mb)` |
| `last_report_ts` | `max(ts)` across all events for this server |
| `state` | `state` from the latest event (by `ts`) |
| `avg_time_db_read_ms` | `mean(time_db_read_ms)` |
| `avg_time_db_write_ms` | `mean(time_db_write_ms)` |
| `avg_time_db_cmd_count` | `mean(time_db_cmd_count)` |

Additionally, three selective-sync roll-ups are folded per server:

- `t_db_p95_ms_per_lan` — p95 of `time_db_ms_per_lan` per owner LAN, computed
  via `statistics.quantiles(n=20, method="inclusive")[18]`.
- `op_counters` — leaf-sum of `op_counts` across all requests.
- `access` — per `(owner_lan, collection)`: `total_hits` (derived from
  `op_counters` non-write ops), `cross_region_hits`, and top-
  `SS_TOP_DOCS_PER_EDGE` `doc_id`s by hit count.

## 8. Storage Server Summaries

`mongo_stats` events are grouped by `server_id`. For each storage server:

| Output Field | Computation |
| ------------ | ----------- |
| `avg_repl_lag_s` | `mean(repl_lag_s)` across non-`None` values; `None` if all standalone |
| `avg_connections` | `mean(connections_current)` |
| `avg_cpu_percent` | `mean(cpu_percent)` |
| `avg_ram_used_mb` | `mean(ram_used_mb)` |
| `sample_count` | `len(events)` |
| `last_report_ts` | `max(ts)` across all events for this server |
| `member_state` | `member_state` from the **last** event in the window (by arrival order) |

## 9. Heartbeat-Only Nodes

After HTTP and storage reduction, heartbeat events are processed. A node that
sent only heartbeats in this window still appears in the summary:

- **Storage heartbeat** (has `connections_current`): creates a
  `storage_servers` entry with `sample_count=0` and point-in-time resource
  values from the heartbeat.
- **HTTP heartbeat** (no `connections_current`): creates or refreshes a
  `servers` entry with `request_count=0`, `error_rate=0.0`, and zero latency
  fields. Existing entries are updated only for `last_report_ts` and `state`.

This ensures the controller knows the node is alive even during quiet periods.

## 10. Domain Summary

Computed from HTTP events only. If no HTTP events arrived, all fields default
to 0.0 (means and medians) or 0 (counts).

In addition to the mean-based fields the aggregator emits median and p95
statistics for the controller's degradation scoring:

| Output Field | Computation |
| ------------ | ----------- |
| `total_requests` | `len(http_events)` |
| `avg_time_proc_ms` | `mean(time_total_ms - time_db_ms)` |
| `median_time_proc_ms` | `median(time_total_ms - time_db_ms)` |
| `avg_time_db_ms` | `mean(time_db_ms)` |
| `median_time_db_ms` | `median(time_db_ms)` |
| `p95_time_db_ms` | p95 of `time_db_ms` via `statistics.quantiles` |
| `average_cpu_percent` | `mean(cpu_percent)` |
| `median_cpu_percent` | `median(cpu_percent)` |
| `peak_time_total_ms` | `max(time_total_ms)` |
| `median_time_total_ms` | `median(time_total_ms)` |
| `median_ram_used_mb` | `median(ram_used_mb)` |
| `avg_storage_cpu_percent` | `mean(avg_cpu_percent)` across all `storage_servers` |
| `median_storage_cpu_percent` | `median(avg_cpu_percent)` across all `storage_servers` |
| `median_storage_ram_used_mb` | `median(avg_ram_used_mb)` across all `storage_servers` |
| `avg_time_db_read_ms` | `mean(time_db_read_ms)` |
| `avg_time_db_write_ms` | `mean(time_db_write_ms)` |
| `avg_time_db_cmd_count` | `mean(time_db_cmd_count)` |

## 11. Selective-Sync Folding

Selective-sync frames (`ss_events`) are processed **after** `mongo_stats`
reduction but before domain summary computation.

For each frame, sorted by `ts` ascending:

1. The frame's `server_mac` (or `server_id`) creates or locates a
   `storage_servers` entry. If the entry didn't exist, it's initialised with
   zero/`None` storage fields and `sample_count=0`.
2. `member_state` and `last_report_ts` are refreshed from each frame.
3. `selective_sync_per_collection` entries are **overwritten**
   (last-writer-wins) per collection — not merged or averaged. This ensures
   the summary carries the freshest `lag_s`, `resume_token_age_s`, and
   `hot_doc_count` for each collection.

Per-collection fields stored on `StorageServerSummary`:

| Field | Source |
| ----- | ------ |
| `lag_s` | `compute_lag_s()` — wall-clock seconds behind the Change Stream |
| `resume_token_age_s` | Provided by the supervisor caller |
| `hot_doc_count` | Provided by the supervisor caller |

## 12. Publication Contract and Failure Handling

### Summary Shape

Every published frame is a JSON object matching the `TelemetrySummary` model:

```
{
  "network_id":      str,
  "window_end":      float,
  "window_seq":      int | null,     # monotonic; None for control mini-summaries
  "window_id":       str | null,     # f"{NETWORK_ID}:{window_seq}"
  "overload":        bool,           # producer-side label (RQ1, see below)
  "servers":         dict[str, ServerSummary],
  "storage_servers": dict[str, StorageServerSummary],
  "control_events":  list[dict],
  "domain_summary":  DomainSummary | null
}
```

Mini-summaries (control events) have empty `servers` / `storage_servers`, no
`domain_summary`, and `window_seq=None`. Full window summaries — including
empty windows — have `control_events: []` and a set `window_seq`.

### Failure Handling

- **Non-dict frames** — logged with type and dropped.
- **Malformed window events** — logged with keys, `event_type`, `server_id`,
  `server_mac` and dropped. The rest of the window is processed normally.
- **Unsupported control event types** — logged and dropped from the
  `control_events` list.
- **Empty window** — always published (RQ1): a fully-idle window still closes
  as a real window with a `window_seq` (see § 6). Never skipped.
- **ZMQ send failures** — not explicitly caught; `send_json` may raise
  `zmq.Again` if no subscribers are connected (PUB socket semantics), but the
  aggregator does not retry — the next window's summary will carry fresh data.

### Overload Labelling (RQ1)

Since 2026-07-31 each real window carries a producer-side `overload: bool`
label computed at publish time — only when `domain_summary` is not None
(empty windows are always `overload=False`):

```python
error_rate = (statistics.mean(s.error_rate for s in servers.values())
              if servers else 0.0)
overload = (domain_summary["average_cpu_percent"] >= OVERLOAD_CPU_PCT
            or domain_summary["peak_time_total_ms"] >= OVERLOAD_PEAK_LATENCY_MS
            or error_rate >= OVERLOAD_ERROR_RATE)
```

Thresholds are pre-registered per run via `OVERLOAD_CPU_PCT` (default `5.0`),
`OVERLOAD_PEAK_LATENCY_MS` (default `1000`), and `OVERLOAD_ERROR_RATE` (default
`0.05`, a fraction) — identical across arms/runs. This is a documented proxy,
**not** a replication of the controller's internal `degradation_score`.

## 13. HTTP Window-Log Server (Polling & RQ1 Delivery Modes)

Since 2026-06-11 the aggregator serves telemetry over HTTP on port
`SUMMARY_CACHE_PORT` (default `5558`). Since 2026-07-31 (RQ1 delivery
semantics) the server is a `ThreadingHTTPServer` backed by the durable window
log, not just the latest-summary cache.

### Endpoints

- `GET /latest_summary` — most recent full-window `TelemetrySummary` JSON
  (cached after every publish); `{}` before the first window closes.
- `GET /window?seq=N` — `200` with the window; `404 {"error":"not_found","seq":N}`
  if unknown; `410 {"error":"aged_out","seq":N,"first_available_seq":X}` if the
  seq has fallen out of the in-memory ring.
- `GET /windows?after_seq=N&limit=K` — `200 {"windows":[...],"next_after_seq":M,"truncated":bool}`
  (default `limit` 100); `410 {"error":"aged_out","after_seq":N,"first_available_seq":X}`.
- `POST /ack` — body `{"window_id":…,"window_seq":N,"delivered_at":ts}` →
  `200 {"ok":true}`; appends to the **separate** `ack_log.jsonl`.

### Window Log (Durable JSONL)

- Every published window is appended to `WINDOW_LOG_PATH` (default
  `/tmp/window_log.jsonl`) **and** an in-memory ring of size
  `WINDOW_LOG_RETENTION` (default `10000`), guarded by a lock shared with the
  publish loop, HTTP handler threads, and boot load.
- On boot the JSONL tail is reloaded into the ring and `window_seq` resumes
  from the last seq in the file (0 if none) — **restart-continuous**, so a
  consumer's `last_seq` stays valid across an aggregator restart.
- `GET /window` and `GET /windows` replay from this log; seqs older than the
  ring's first entry answer `410 aged_out` with `first_available_seq`.
- Control mini-summaries are **never** logged or served — only real windows.

### Controller Usage

Polling controllers send `GET /latest_summary` to both aggregators
concurrently at a configurable interval (`POLL_INTERVAL_S`, default 10 s);
RQ1 event-preserving sources pull `GET /windows?after_seq=…` and ack via
`POST /ack`. See `source/sdn_controller/telemetry/polling_source.py`,
`event_preserving_source.py`, `delayed_source.py`, and
`docs/operation/telemetry/implementation/rq1_delivery_semantics/rq1_delivery_semantics_plan.md`.
