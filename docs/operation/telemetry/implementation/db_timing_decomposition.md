# DB Timing Decomposition

## Objective

Split the single `time_db_ms` field currently emitted by edge servers into
**read time**, **write time**, and **command count** so that latency analysis
can distinguish application-side DB work from replication/write-concern floors,
and so that the elasticity layer has a diagnostic signal for why `T_db` moves
independently from request rate.

Three new per-request fields are added to the telemetry event schema and
propagated end-to-end: edge server â†’ aggregator â†’ controller â†’ CSV.

| Field | Unit | Semantics |
|---|---|---|
| `time_db_read_ms` | ms | Sum of pymongo command durations for `find`, `aggregate`, `count`, `distinct`, `getMore`, `findAndModify` |
| `time_db_write_ms` | ms | Sum of pymongo command durations for `insert`, `update`, `delete` |
| `time_db_cmd_count` | int | Number of non-internal commands issued during the request |

A domain-level `avg_repl_lag_ms` surfaced by the collector is in scope because
it's the only way to correlate the write-path floor to replica-set health
without reading each node's Mongo log. The field already exists per storage
node; the collector aggregates it into the domain CSV.

## Impact on the telemetry mechanism

Reference: [`../telemetry_overview.md`](../telemetry_overview.md).

| Stage | Current | After this plan |
|---|---|---|
| Edge server `telemetry.py` | emits `time_db_ms` (wall clock around `timed_db`) | also emits `time_db_read_ms`, `time_db_write_ms`, `time_db_cmd_count` populated by a pymongo `CommandListener` |
| Aggregator `aggregator.py` | per-server HTTP stats mean `avg_time_db_ms` | additionally mean the three new fields per server; add the same three to the domain summary |
| Controller `telemetry/models.py` | `ServerSummary` / `DomainSummary` carry `avg_time_db_ms` | carry the three new averages as optional, default-0 fields (backward-compatible) |
| Collector `collect_resource_stats.py` | writes domain `resource_stats.csv` | appends `avg_repl_lag_ms`, `avg_time_db_read_ms`, `avg_time_db_write_ms`, `avg_time_db_cmd_count` |

The flow direction, transport, and windowing are unchanged. No new ZMQ
endpoint; no new consumer path; optional pydantic fields mean mixed-version
aggregator/controller deployments keep parsing.

### Path taken by `avg_repl_lag_ms`

Unlike the three `time_db_*` fields, `avg_repl_lag_ms` is **not** propagated
through `DomainSummary`. The collector reads the per-node `avg_repl_lag_s`
field directly from the raw aggregator payload (`summary["storage_servers"]`)
and aggregates it to milliseconds at CSV-write time. This keeps the
controller-side pydantic models focused on request-path latency and avoids
pushing a storage-only field through the shared domain summary.

### CSV column naming â€” `avg_*` instead of `median_*`

Every existing column in `resource_stats.csv` uses the `median_*` prefix
(`median_time_proc_ms`, `median_time_db_ms`, `median_cpu_percent`, â€¦) because
it records the per-window central tendency across servers. The four new
columns deliberately use the `avg_*` prefix instead:

- `avg_time_db_read_ms`, `avg_time_db_write_ms`, `avg_time_db_cmd_count` are
  already **means** in the aggregator domain summary; they enter the CSV
  verbatim without a second reduction. Renaming them to `median_*` would be
  misleading.
- `avg_repl_lag_ms` is a mean over storage nodes (see above); labelling it
  `median_*` would be equally wrong.
- The OLS regression in `cli_tdb_drivers` requires means, not medians.

The gap between a future `median_time_db_*` and the matching `avg_*` is itself
diagnostic (skewed distribution of per-request DB durations), so a follow-up
could add medians as separate columns without renaming these.

### Known non-identity

`time_db_read_ms + time_db_write_ms â‰  time_db_ms` exactly. `time_db_ms` wraps
the `timed_db` block (includes connection checkout, server selection,
serialization); the listener measures only command RTT. The gap is itself
diagnostic â€” a large gap means the driver is blocking outside command
execution.

### Filtered commands

Internal driver chatter is excluded from both buckets and from the count:
`hello`, `isMaster`, `ismaster`, `ping`, `buildInfo`, `saslStart`,
`saslContinue`, `endSessions`, `getParameter`, `killCursors`,
`listDatabases`, `listCollections`, `listIndexes`, `connectionStatus`.

`getMore` is counted as read. This over-counts "logical queries" when large
cursors are iterated; documented here so downstream analysis interprets the
count correctly.

---

## File map

| Action | Path |
|---|---|
| New | `source/docker/edge_server/source/db_monitor.py` |
| Edit | `source/docker/edge_server/source/app.py` |
| Edit | `source/docker/edge_server/source/telemetry.py` |
| Edit | `source/docker/local_state_server/aggregator.py` |
| Edit | `source/sdn_controller/telemetry/models.py` |
| Edit | `source/scripts/testing/collect_resource_stats.py` (new columns only; `per_node_stats.csv` belongs to the testing plan) |

---

## Execution order

### 1. Edge server â€” `CommandListener`

pymongo (unpinned â‰¥ 4.0) invokes `CommandListener` callbacks synchronously on
the thread that issued the command, so Flask's request-local `g` is safe to
use directly. The listener wraps `g` access in `try/except RuntimeError` so
driver-internal operations outside a request context (e.g. connection pool
heartbeats) do not fail.

**`source/docker/edge_server/source/db_monitor.py` (new)**

```python
"""pymongo CommandListener that accumulates per-request read/write DB time."""
from pymongo import monitoring
from flask import g

_READ_CMDS = {
    "find", "aggregate", "count", "distinct",
    "getMore", "findAndModify",
}
_WRITE_CMDS = {"insert", "update", "delete"}
_IGNORED_CMDS = {
    "hello", "isMaster", "ismaster", "ping", "buildInfo",
    "saslStart", "saslContinue", "endSessions",
    "getParameter", "killCursors", "listDatabases",
    "listCollections", "listIndexes", "connectionStatus",
}


class _DbTimingListener(monitoring.CommandListener):
    def started(self, event):
        pass

    def succeeded(self, event):
        self._record(event.command_name, event.duration_micros)

    def failed(self, event):
        self._record(event.command_name, event.duration_micros)

    @staticmethod
    def _record(cmd: str, dur_us: int) -> None:
        if cmd in _IGNORED_CMDS:
            return
        dur_s = dur_us / 1_000_000.0
        try:
            if cmd in _READ_CMDS:
                g.time_db_read_s = getattr(g, "time_db_read_s", 0.0) + dur_s
            elif cmd in _WRITE_CMDS:
                g.time_db_write_s = getattr(g, "time_db_write_s", 0.0) + dur_s
            g.time_db_cmd_count = getattr(g, "time_db_cmd_count", 0) + 1
        except RuntimeError:
            # Outside Flask request context (driver-internal op) â€” ignore.
            pass


_listener_registered = False


def register() -> None:
    """Idempotent global registration. Call once at app import time."""
    global _listener_registered
    if _listener_registered:
        return
    monitoring.register(_DbTimingListener())
    _listener_registered = True
```

**`source/docker/edge_server/source/app.py`** â€” register before any `MongoClient`:

```python
from db_monitor import register as _register_db_monitor
_register_db_monitor()
```

**`source/docker/edge_server/source/telemetry.py`** â€” reset per request and
extend the event:

```python
@app.before_request
def _start_timer() -> None:
    g.time_start = time.monotonic()
    g.time_db_elapsed = 0.0
    g.time_db_read_s = 0.0
    g.time_db_write_s = 0.0
    g.time_db_cmd_count = 0


def _build_event(
    time_total_ms: float,
    time_db_ms: float,
    time_db_read_ms: float,
    time_db_write_ms: float,
    time_db_cmd_count: int,
    status_code: int,
    request_type: str,
) -> dict:
    return {
        "server_id": _get_server_mac(),
        "ts": time.time(),
        "time_total_ms": time_total_ms,
        "time_db_ms": time_db_ms,
        "time_db_read_ms": time_db_read_ms,
        "time_db_write_ms": time_db_write_ms,
        "time_db_cmd_count": time_db_cmd_count,
        "status_code": status_code,
        "request_type": request_type,
        "cpu_percent": psutil.cpu_percent(),
        "ram_used_mb": psutil.virtual_memory().used / (1024 * 1024),
    }

# In _emit_metric:
event = _build_event(
    time_total_ms=time_total,
    time_db_ms=g.time_db_elapsed * 1000,
    time_db_read_ms=getattr(g, "time_db_read_s", 0.0) * 1000,
    time_db_write_ms=getattr(g, "time_db_write_s", 0.0) * 1000,
    time_db_cmd_count=getattr(g, "time_db_cmd_count", 0),
    status_code=response.status_code,
    request_type="write" if request.method in ("POST", "PUT", "PATCH", "DELETE") else "read",
)
```

**Acceptance:** emitted HTTP events carry the three new fields; a sample of
real traffic shows `time_db_ms â‰¥ time_db_read_ms + time_db_write_ms` and the
gap is small relative to command RTT.

### 2. Aggregator â€” per-server and domain means

Use `.get(..., 0)` when reading event fields so a pre-Step-1 edge server
doesn't crash aggregation during rolling upgrades.

```python
# per-server block, inside the for server_id, events loop
servers[server_id] = {
    # ... existing fields ...
    "avg_time_db_read_ms":   statistics.mean(e.get("time_db_read_ms", 0)  for e in events),
    "avg_time_db_write_ms":  statistics.mean(e.get("time_db_write_ms", 0) for e in events),
    "avg_time_db_cmd_count": statistics.mean(e.get("time_db_cmd_count", 0) for e in events),
}

# domain summary, inside the if http_events: branch
summary["domain_summary"].update({
    "avg_time_db_read_ms":   statistics.mean(e.get("time_db_read_ms", 0)  for e in http_events),
    "avg_time_db_write_ms":  statistics.mean(e.get("time_db_write_ms", 0) for e in http_events),
    "avg_time_db_cmd_count": statistics.mean(e.get("time_db_cmd_count", 0) for e in http_events),
})
```

**Acceptance:** subscribing a raw ZMQ SUB to the aggregator PUB socket shows
the three new fields on both per-server and domain summaries.

### 3. Controller â€” extend pydantic models

```python
# source/sdn_controller/telemetry/models.py
class ServerSummary(BaseModel):
    avg_time_total_ms: float
    avg_time_db_ms: float
    avg_time_proc_ms: float
    request_count: int
    error_rate: float
    avg_cpu_percent: float
    avg_ram_used_mb: float
    last_report_ts: float = 0.0
    # New â€” defaulted for backward compatibility with pre-Step 2 aggregators.
    avg_time_db_read_ms: float = 0.0
    avg_time_db_write_ms: float = 0.0
    avg_time_db_cmd_count: float = 0.0


class DomainSummary(BaseModel):
    total_requests: int
    avg_time_proc_ms: float
    avg_time_db_ms: float
    average_cpu_percent: float
    peak_time_total_ms: float
    avg_storage_cpu_percent: float = 0.0
    avg_time_db_read_ms: float = 0.0
    avg_time_db_write_ms: float = 0.0
    avg_time_db_cmd_count: float = 0.0
```

**Acceptance:** controller parses payloads from both new and legacy
aggregators; no schema errors in logs.

### 4. Collector â€” append domain CSV columns

Only the four domain-level columns are added here. The new `per_node_stats.csv`
output is defined in the testing plan
[`analysis_toolchain.md`](../../testing/analysis_toolchain.md).

```python
# source/scripts/testing/collect_resource_stats.py
FIELDNAMES = [
    "timestamp", "phase", "network_id", "window_end", "total_requests",
    "median_cpu_percent", "median_ram_used_mb",
    "median_storage_cpu_percent", "median_storage_ram_used_mb",
    "median_time_proc_ms", "median_time_db_ms", "median_time_total_ms",
    "server_count", "storage_count",
    # --- appended columns ---
    "avg_repl_lag_ms",
    "avg_time_db_read_ms",
    "avg_time_db_write_ms",
    "avg_time_db_cmd_count",
]


def _domain_avg_repl_lag_ms(storage: dict) -> float:
    lags = [s.get("avg_repl_lag_s") for s in storage.values()
            if s.get("avg_repl_lag_s") is not None]
    return (statistics.mean(lags) * 1000.0) if lags else 0.0


# inside the poll loop, after populating the existing row:
row["avg_repl_lag_ms"]        = _domain_avg_repl_lag_ms(summary.get("storage_servers", {}))
row["avg_time_db_read_ms"]    = domain.get("avg_time_db_read_ms", "")
row["avg_time_db_write_ms"]   = domain.get("avg_time_db_write_ms", "")
row["avg_time_db_cmd_count"]  = domain.get("avg_time_db_cmd_count", "")
```

**Acceptance:** after a â‰¥ 60 s collection, `resource_stats.csv` contains the
four new columns with non-zero values during any request-carrying phase.

---

## Risks

| Risk | Mitigation |
|---|---|
| Listener fires outside a Flask context â†’ `RuntimeError` from `g` | `try/except RuntimeError` in `_record`; driver connection monitors silently ignored |
| Identity `read+write==total` doesn't hold | Documented as expected; the gap is diagnostic |
| pymongo major version bump changes listener threading | Step 1 acceptance covers this; if sync semantics ever change, `g` access must be replaced with a thread-local keyed by `threading.get_ident()` correlated to request id |
| Mixed-version rolling upgrade | `.get(..., 0)` in aggregator; `= 0.0` defaults in pydantic models |

## Overview file changes â€” `telemetry_overview.md`

The following edits to [`../telemetry_overview.md`](../telemetry_overview.md) are
required so the overview reflects the new schema once this plan ships.

### 1. Per-Request Events â€” add three fields to the example and field table

Extend the JSON example under **"Per-Request Events"**:

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

Append three rows to the field table:

| Field | Source |
|---|---|
| `time_db_read_ms` | Sum of pymongo read-command durations via `CommandListener` (`find`, `aggregate`, `count`, `distinct`, `getMore`, `findAndModify`) |
| `time_db_write_ms` | Sum of pymongo write-command durations via `CommandListener` (`insert`, `update`, `delete`) |
| `time_db_cmd_count` | Non-internal command count during the request |

Add a short note after the table:

> `time_db_read_ms + time_db_write_ms` is not expected to equal `time_db_ms`
> exactly. `time_db_ms` wraps the `timed_db` block (connection checkout, server
> selection, serialization); the listener measures only command RTT. The gap is
> diagnostic â€” see [implementation/db_timing_decomposition.md](implementation/db_timing_decomposition.md).

### 2. File Layout â€” add `db_monitor.py`

Under **"Telemetry Senders"**, add the new module:

```
source/docker/edge_server/source/
  telemetry.py          # MetricSender ABC, ZmqMetricSender, Flask hooks, heartbeat loop
  db_monitor.py         # pymongo CommandListener â€” per-request read/write DB time
```

### 3. Aggregator â€” extend the per-server and domain tables

Under **"Windowed Aggregation â†’ Per-server HTTP stats"**, add three rows:

| Output Field | Computation |
|---|---|
| `avg_time_db_read_ms` | mean of `time_db_read_ms` |
| `avg_time_db_write_ms` | mean of `time_db_write_ms` |
| `avg_time_db_cmd_count` | mean of `time_db_cmd_count` |

Under **"Domain summary"**, add the same three rows (keyed off
`http_events`).

### 4. Controller-Side Receiver â€” note optional fields

Under **"Pydantic Models"**, append a bullet after the `last_report_ts`
compatibility note:

> `ServerSummary` and `DomainSummary` also carry `avg_time_db_read_ms`,
> `avg_time_db_write_ms`, and `avg_time_db_cmd_count` as optional fields
> defaulted to `0.0`. Payloads from pre-decomposition aggregators parse
> unchanged.

## Cross-references

- Umbrella investigation: [`../../elasticy_manager/implementation/plans/metric_drivers_investigation_plan.md`](../../elasticy_manager/implementation/plans/metric_drivers_investigation_plan.md)
- Consumes the new fields: [`../../testing/analysis_toolchain.md`](../../testing/analysis_toolchain.md) (CLI `cli_tdb_drivers`)
