# Implementation Plan: Modular Telemetry Event Source

## Objective

Add a `TelemetryEventSource` abstract interface to the SDN controller that decouples the controller from the telemetry transport layer. The interface exposes `get_latest()` — the only method the controller (Thread 1) needs. ZeroMQ is the first implementation. A future MongoDB Change Stream implementation would satisfy the same interface without touching controller code.

---

## File Structure

```
source/sdn_controller/
  telemetry/
    __init__.py
    models.py             ← Pydantic models (TelemetrySummary, DomainSummary, ServerSummary)
    source.py             ← TelemetryEventSource ABC
    zmq_source.py         ← ZmqTelemetrySource (ZMQ SUB, owns its own thread)
  main.py                 ← KenLearnAndLog (Thread 1) — constructs and holds the source
```

No separate `TelemetryMonitor` class. The source owns its receive loop and latest-state cache internally. The controller calls `source.get_latest(network_id)`.

---

## Steps

### Phase 1 — Pydantic Models

**`source/sdn_controller/telemetry/models.py`**

Typed representation of the aggregator payload. Pydantic validates the incoming JSON
and rejects malformed messages at the boundary rather than letting bad data propagate
as untyped dicts into controller logic.

```python
from pydantic import BaseModel


class ServerSummary(BaseModel):
    avg_time_total_ms: float
    avg_time_db_ms: float
    avg_time_proc_ms: float
    request_count: int
    error_rate: float
    avg_cpu_percent: float
    avg_ram_used_mb: float


class DomainSummary(BaseModel):
    total_requests: int
    avg_time_proc_ms: float
    avg_time_db_ms: float
    average_cpu_percent: float
    peak_time_total_ms: float


class TelemetrySummary(BaseModel):
    network_id: str
    window_end: float
    servers: dict[str, ServerSummary]
    domain_summary: DomainSummary
```

### Phase 2 — Abstract Interface *(depends on Phase 1)*

```python
from abc import ABC, abstractmethod

from .models import TelemetrySummary


class TelemetryEventSource(ABC):
    """Transport-agnostic interface for telemetry state access.

    All transport-specific configuration (endpoints, credentials, etc.) is
    handled in each implementation's __init__. The controller only ever
    calls start() once at startup, then get_latest() on demand.
    """

    @abstractmethod
    def start(self) -> None:
        """Begin receiving summaries in the background.

        For ZMQ: spawns the daemon receive thread.
        For a future MongoDB source: opens the Change Stream cursor.
        Called once at controller startup.
        """

    @abstractmethod
    def get_latest(self, network_id: str) -> TelemetrySummary | None:
        """Return the most recently received summary for network_id, or None
        if no summary has been received yet.
        """
```

### Phase 3 — ZeroMQ Implementation *(depends on Phases 1 & 2)*

**`source/sdn_controller/telemetry/zmq_source.py`**

The ZMQ source owns its receive loop as an eventlet greenthread. Each incoming JSON
payload is parsed with `TelemetrySummary.model_validate()` at the boundary — invalid
messages raise a `ValidationError` caught by the broad `except`, logged, and discarded.

> **Why `zmq.green` instead of plain `zmq` + `threading.Thread`:**
> OS-Ken (os-ken) runs on eventlet. If `threading.Thread` is used, its `__init__`
> creates native `RLock` objects. When eventlet's monkey-patching fires afterwards it
> cannot patch locks that already exist, producing `"N RLock(s) were not greened"`
> warnings and potential deadlocks. `zmq.green` is pyzmq's built-in eventlet backend:
> it registers the socket file descriptor with the eventlet hub so `recv_json()` yields
> cooperatively instead of blocking. `os_ken.lib.hub.spawn` replaces
> `threading.Thread`, and no `Lock` is needed because cooperative greenthreads never
> interleave within a single statement.

```python
import logging

import zmq.green as zmq
from os_ken.lib import hub

from .models import TelemetrySummary
from .source import TelemetryEventSource

logger = logging.getLogger(__name__)


class ZmqTelemetrySource(TelemetryEventSource):
    def __init__(self, endpoints: list[str], on_update=None) -> None:
        self._ctx = zmq.Context()
        self._socket: zmq.Socket = self._ctx.socket(zmq.SUB)
        for ep in endpoints:
            self._socket.connect(ep)
            logger.info("telemetry: will subscribe to %s", ep)
        self._socket.setsockopt(zmq.SUBSCRIBE, b"")
        self._latest: dict[str, TelemetrySummary] = {}
        self._on_update = on_update

    def start(self) -> None:
        hub.spawn(self._receive_loop)

    def get_latest(self, network_id: str) -> TelemetrySummary | None:
        return self._latest.get(network_id)

    def _receive_loop(self) -> None:
        while True:
            try:
                summary = TelemetrySummary.model_validate(self._socket.recv_json())
                self._latest[summary.network_id] = summary
                if self._on_update is not None:
                    self._on_update(summary)
                logger.debug(
                    "telemetry update network=%s proc_ms=%.1f db_ms=%.1f",
                    summary.network_id,
                    summary.domain_summary.avg_time_proc_ms,
                    summary.domain_summary.avg_time_db_ms,
                )
            except Exception as exc:
                logger.warning("telemetry receive error: %s", exc)
```

### Phase 4 — Wire into main.py *(depends on Phase 3)*

Thread 1 (`KenLearnAndLog`) holds the source and calls `get_latest()` in the WSM cost
calculation. No separate monitor class required.

```python
import os

from .telemetry.models import TelemetrySummary
from .telemetry.zmq_source import ZmqTelemetrySource


def _print_summary(summary: TelemetrySummary) -> None:
    ds = summary.domain_summary
    print(
        f"[telemetry] network={summary.network_id} "
        f"proc_ms={ds.avg_time_proc_ms:.1f} "
        f"db_ms={ds.avg_time_db_ms:.1f} "
        f"requests={ds.total_requests} "
        f"cpu={ds.average_cpu_percent:.1f}%"
    )


_AGGREGATOR_ENDPOINTS = [
    ep.strip()
    for ep in os.environ.get("AGGREGATOR_ENDPOINTS", "tcp://127.0.0.1:5556").split(",")
    if ep.strip()
]

_telemetry = ZmqTelemetrySource(endpoints=_AGGREGATOR_ENDPOINTS, on_update=_print_summary)
_telemetry.start()


class KenLearnAndLog(app_manager.OSKenApp):
    # ... existing code ...

    def _wsm_cost(self, server_id: str, hops: int) -> float | None:
        theta = 0.5
        all_summaries = [
            _telemetry.get_latest(nid) for nid in ("net1", "net2")
        ]
        proc_values = [
            s.domain_summary.avg_time_proc_ms
            for s in all_summaries if s is not None
        ]
        if not proc_values:
            return None
        t_proc_max = max(proc_values)
        if t_proc_max == 0:
            return 0.0

        summary = _telemetry.get_latest(_server_network(server_id))
        if summary is None:
            return None

        hops_max = _max_known_hops()
        return (
            theta * (summary.domain_summary.avg_time_proc_ms / t_proc_max)
            + (1 - theta) * (hops / hops_max)
        )
```

---

## Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Payload typing | Pydantic `TelemetrySummary` model | Validates at the transport boundary. Bad messages are caught and logged before they reach controller logic. Attribute access replaces error-prone dict key strings. |
| Controller-facing API | `get_latest(network_id) -> TelemetrySummary \| None` on the ABC | Thread 1 needs cached state, not a blocking event stream. Typed return means the controller never does unguarded dict access. |
| `receive()` visibility | Private implementation detail | Each transport decides how to keep state current. The controller never calls `receive()`. |
| Background mechanism | `hub.spawn` (eventlet greenthread) via `os_ken.lib.hub` | Idiomatic os-ken concurrency. No real OS thread is created, so no native `RLock` objects are created outside eventlet's control. |
| ZMQ backend | `zmq.green` (pyzmq's eventlet backend) | `recv_json()` yields cooperatively to the hub rather than blocking. The OpenFlow event loop continues processing `PacketIn` events while waiting for the next telemetry summary. |
| Thread safety / locking | None required | Cooperative greenthreads never interleave within a single statement. `self._latest[key] = value` is atomic from the greenthread scheduler's perspective. |
| `SUBSCRIBE` filter | `b""` (all messages) | Receives everything from the aggregator. Can be scoped to a topic prefix later if needed. |
| Scope | Interface + ZMQ only | Threshold evaluation and typed alert events (for Thread 3) are deferred to the next step. |

---

## Architecture Alignment

Both controllers subscribe to **both** aggregators:

- `VIP_Web` selection is cross-domain — a controller may route a client to a server in the peer network.
- The WSM cost function scores all candidate servers across both networks and requires `T_proc` for every server.
- Each controller maintains `latest_telemetry` keyed by `network_id`, updated on every incoming summary from either aggregator.
- Provisioning decisions (Thread 3) remain domain-scoped; cross-domain telemetry is consumed read-only for scoring.

See [system_cross_network_state.md](../details/system_cross_network_state.md) for the full pub/sub topology diagram.

---

## Acceptance Criteria

- `ZmqTelemetrySource` can be tested in isolation: run `aggregator.py` locally, call `connect()`, wait one window period, and confirm `get_latest("net1")` returns a parsed dict.
- The eventlet hub keeps processing `PacketIn` events (flow rules still install) while the receive thread is blocked on `recv_json()` waiting for the next summary.
- `get_latest()` returns `None` before the first summary arrives and the latest dict immediately after.
- Replacing `ZmqTelemetrySource` with a future `MongoTelemetrySource` requires no changes to `KenLearnAndLog` or anywhere else that holds a `TelemetryEventSource` reference.

---

## Aggregator Payload Reference

Published by `aggregator.py` via ZMQ PUB on port `5556`. Field names are taken
directly from the source:

```json
{
  "network_id": "net1",
  "window_end": 1742300400.0,
  "servers": {
    "server-1": {
      "avg_time_total_ms": 44.0,
      "avg_time_db_ms": 11.5,
      "avg_time_proc_ms": 32.5,
      "request_count": 120,
      "error_rate": 0.0,
      "avg_cpu_percent": 22.4,
      "avg_ram_used_mb": 310.0
    }
  },
  "domain_summary": {
    "total_requests": 360,
    "avg_time_proc_ms": 33.1,
    "avg_time_db_ms": 12.1,
    "average_cpu_percent": 21.8,
    "peak_time_total_ms": 98.3
  }
}
```

The controller accesses domain-level thresholds via:

```python
summary["domain_summary"]["avg_time_proc_ms"]   # T_proc — compute threshold input
summary["domain_summary"]["avg_time_db_ms"]     # T_dados — data threshold input
summary["domain_summary"]["average_cpu_percent"]
summary["servers"][server_id]["avg_time_proc_ms"]  # per-server WSM scoring
```
