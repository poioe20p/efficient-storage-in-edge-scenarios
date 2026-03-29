# Plan: Telemetry Heartbeat

## Goal

Nodes currently only send telemetry when they complete a request. A node that is
idle or overloaded goes silent, starving the aggregator of fresh data — and leaving
the cost function working from stale cached stats. This plan adds a periodic
heartbeat so that every node reports its presence (and current CPU/RAM) at most once
per minute, even when no requests are completing.

`last_report_ts` is threaded through to the Pydantic models so a future staleness
cost plan can consume it without revisiting the aggregator or transport layer. No
changes to the SDN controller or cost functions are in scope here.

---

## Files to Change

| File | Action |
|------|--------|
| `source/docker/edge_storage_server/mongo_telemetry.py` | Uncomment 2 lines — heartbeat logic already scaffolded |
| `source/docker/edge_server/source/telemetry.py` | Add `_heartbeat_loop()` daemon thread |
| `source/docker/local_state_server/aggregator.py` | Track `last_seen` per server; add `last_report_ts` to summaries; surface heartbeat-only nodes |
| `source/sdn_controller/telemetry/models.py` | Add `last_report_ts: float = 0.0` to `ServerSummary` and `StorageServerSummary` |

---

## Phase 1 — Storage sidecar (trivial — already scaffolded)

In `mongo_telemetry.py`, uncomment the two lines in `_push_stats()`:

```python
# Before:
    if activity:
        event_type = "mongo_stats"
    # elif now - _last_send_ts >= HEARTBEAT_INTERVAL_S:
    #     event_type = "heartbeat"
    else:
        logger.debug("No client activity — skipping telemetry push")
        return

# After:
    if activity:
        event_type = "mongo_stats"
    elif now - _last_send_ts >= HEARTBEAT_INTERVAL_S:
        event_type = "heartbeat"
    else:
        logger.debug("No client activity — skipping telemetry push")
        return
```

`HEARTBEAT_INTERVAL_S`, `_last_send_ts`, and the `event_type` branching are
already in place. The resulting heartbeat event is structurally identical to a
`mongo_stats` event (includes `repl_lag_s`, `connections_current`, `cpu_percent`,
`ram_used_mb`) — only `event_type` differs.

---

## Phase 2 — Edge server (new background thread)

`telemetry.py` currently only sends events from HTTP request hooks. A daemon
thread publishing heartbeats outside the request-response cycle is the minimal
addition.

### 2a — New imports and constant

```python
# Add to imports at top of file:
import threading

# Add after existing module-level constants:
HEARTBEAT_INTERVAL_S: float = float(os.environ.get("HEARTBEAT_INTERVAL_S", "60"))
```

### 2b — Heartbeat loop function

The loop polls every second and only fires if `HEARTBEAT_INTERVAL_S` have elapsed
since the last time **any** telemetry (request-driven or heartbeat) was sent. The
shared `last_sent` list is a single-element mutable container updated by both the
heartbeat loop itself and by `_emit_metric` after every HTTP request, so a busy
node that completes requests frequently will never send redundant heartbeats.

```python
def _heartbeat_loop(sender: MetricSender, last_sent: list[float]) -> None:
    while True:
        time.sleep(1.0)
        if time.monotonic() - last_sent[0] >= HEARTBEAT_INTERVAL_S:
            last_sent[0] = time.monotonic()
            event = {
                "event_type":  "heartbeat",
                "server_id":   SERVER_MAC,
                "ts":          time.time(),
                "cpu_percent": psutil.cpu_percent(),
                "ram_used_mb": psutil.virtual_memory().used / 1_048_576,
            }
            sender.send(event)
```

### 2c — Spawn from `init_telemetry()`

`_last_sent` is initialised to `time.monotonic()` (not `0.0`) so the heartbeat
doesn't fire immediately on startup before any real traffic has had a chance to
arrive. `_emit_metric` updates it after every request, resetting the countdown.

```python
def init_telemetry(app: Flask, sender: MetricSender | None = None) -> None:
    _sender = sender or ZmqMetricSender()

    _last_sent: list[float] = [time.monotonic()]
    threading.Thread(target=_heartbeat_loop, args=(_sender, _last_sent), daemon=True).start()

    @app.before_request
    def _start_timer() -> None:
        ...

    @app.after_request
    def _emit_metric(response):
        ...
        _sender.send(event)
        _last_sent[0] = time.monotonic()   # reset heartbeat countdown
        return response
```

---

## Phase 3 — Aggregator: track `last_report_ts` and surface heartbeat-only nodes

### 3a — Build `last_seen` from all events in the window

Add immediately after `window, _buffer[:] = list(_buffer), []`:

```python
last_seen: dict[str, float] = {}
for event in window:
    sid = event.get("server_id")
    ts  = event.get("ts", 0.0)
    if sid and ts > last_seen.get(sid, 0.0):
        last_seen[sid] = ts
```

### 3b — Propagate into HTTP server summaries

```python
servers[server_id] = {
    "avg_time_total_ms": statistics.mean(time_totals),
    "avg_time_db_ms":    statistics.mean(time_db),
    "avg_time_proc_ms":  statistics.mean(time_procs),
    "request_count":     len(events),
    "error_rate":        errors / len(events),
    "avg_cpu_percent":   statistics.mean([event["cpu_percent"] for event in events]),
    "avg_ram_used_mb":   statistics.mean([event["ram_used_mb"] for event in events]),
    "last_report_ts":    last_seen.get(server_id, 0.0),   # ← NEW
}
```

### 3c — Propagate into storage summaries

```python
storage_servers[server_id] = {
    "avg_repl_lag_s":  statistics.mean(lags) if lags else None,
    "avg_connections": statistics.mean([e["connections_current"] for e in events]),
    "avg_cpu_percent": statistics.mean([e["cpu_percent"] for e in events]),
    "avg_ram_used_mb": statistics.mean([e["ram_used_mb"] for e in events]),
    "sample_count":    len(events),
    "last_report_ts":  last_seen.get(server_id, 0.0),     # ← NEW
}
```

### 3d — Add heartbeat-only entries for nodes that were silent on data

After both `servers` and `storage_servers` dicts are fully built, add:

```python
heartbeats = [e for e in window if e.get("event_type") == "heartbeat"]
for hb in heartbeats:
    sid = hb.get("server_id")
    if not sid:
        continue
    if "connections_current" in hb:          # storage sidecar heartbeat
        if sid not in storage_servers:
            storage_servers[sid] = {
                "avg_repl_lag_s":  hb.get("repl_lag_s"),
                "avg_connections": float(hb.get("connections_current", 0)),
                "avg_cpu_percent": hb.get("cpu_percent", 0.0),
                "avg_ram_used_mb": hb.get("ram_used_mb", 0.0),
                "sample_count":    0,
                "last_report_ts":  last_seen[sid],
            }
    else:                                     # edge server heartbeat
        if sid not in servers:
            servers[sid] = {
                "avg_time_total_ms": 0.0,
                "avg_time_db_ms":    0.0,
                "avg_time_proc_ms":  0.0,
                "request_count":     0,
                "error_rate":        0.0,
                "avg_cpu_percent":   hb.get("cpu_percent", 0.0),
                "avg_ram_used_mb":   hb.get("ram_used_mb", 0.0),
                "last_report_ts":    last_seen[sid],
            }
```

Disambiguation: `connections_current` in the heartbeat event reliably separates
storage sidecar heartbeats from edge server heartbeats without adding a new field
to the event schema.

Heartbeat-only entries use `request_count=0` and zero HTTP latency fields so they
are **inert in domain-summary calculations** but still visible to the controller's
`_server_stats`/`_storage_stats` cache.

---

## Phase 4 — Pydantic models

Add `last_report_ts: float = 0.0` with a default so deserialization of payloads
from pre-heartbeat aggregators is backward-compatible. No existing unit tests need
updating.

```python
class ServerSummary(BaseModel):
    avg_time_total_ms: float
    avg_time_db_ms: float
    avg_time_proc_ms: float
    request_count: int
    error_rate: float
    avg_cpu_percent: float
    avg_ram_used_mb: float
    last_report_ts: float = 0.0          # ← NEW


class StorageServerSummary(BaseModel):
    avg_repl_lag_s: float | None
    avg_connections: float
    avg_cpu_percent: float
    avg_ram_used_mb: float
    sample_count: int
    last_report_ts: float = 0.0          # ← NEW
```

---

## Verification

1. Run `mongo_telemetry.py` against a local Mongo with no writes — confirm a
   `heartbeat` event appears in the ZMQ log after ≤60 s of silence.
2. Run the edge Flask server and make no requests — confirm a `heartbeat` event is
   PUSHed after 60 s.
3. In a composed network, check aggregator logs: idle servers that only sent
   heartbeats still appear in the published summary with `request_count=0` and a
   valid `last_report_ts`.
4. Validate Pydantic: a JSON payload without `last_report_ts` still deserializes
   successfully (default `0.0`).

---

## Further Considerations

- **`HEARTBEAT_INTERVAL_S` env var** — should be added to whichever compose / env
  file configures the edge containers (e.g. `scripts/osken-controller.env` or the
  `Dockerfile` defaults). Default `60` is already baked into both sender modules.
- **Staleness cost function** — consuming `last_report_ts` in `select_server()` /
  `select_storage()` is explicitly deferred to a separate plan. Weight placeholders
  `W_STALENESS`, `W_STORAGE_STALENESS`, and `STALENESS_MAX_S` will be defined there.
- **`last_report_ts = 0.0` sentinel** — the downstream staleness plan should treat
  `0.0` as "not yet seen / cold start" and assign benefit-of-the-doubt (no penalty).
