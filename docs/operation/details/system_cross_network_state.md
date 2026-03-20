# Cross-Network State & Telemetry Architecture

This document covers the architectural decisions related to multi-network deployment: how flow rules are installed across network boundaries, how nodes register themselves, and how telemetry state is federated across network domains.

---

## 1. Cross-Network Flow Rules & Double PacketIn Minimization

Each SDN controller can only install flow rules on its own domain's switches. For a packet destined to a VIP_SERVER or VIP_DADOS hosted in a different network, the source controller installs a rule on its **egress switch** only. The destination controller handles the remaining hop.

### Minimizing Double PacketIn via Switch-Level Tagging

The main risk is the packet arriving at the destination network's ingress switch and triggering a second `PacketIn` before the destination controller has installed its rule. This is avoided by:

1. **Tagging the packet at the source egress switch** (VLAN tag or MPLS label) before forwarding it across the inter-network link.
2. **Pre-installing a tag-matched rule** at the destination ingress switch:

   ```
   match: VLAN_ID=<VIP_DOMAIN_TAG>, in_port=inter_link_port
   action: strip_vlan → forward to VIP_SERVER
   ```

3. The destination controller installs these rules **proactively at VIP registration time**, not reactively on PacketIn.

This transforms the destination path from reactive (PacketIn → controller → FlowMod) to **proactive (pre-installed match → forward)**, eliminating the second PacketIn entirely.

---

## 2. Node Network Attachment & Controller Discovery

Network attachment for all containers (edge servers, storage nodes, aggregator) is performed **externally** by the admin scripts (`build_network_1.sh`, `build_network_2.sh`, `add_network_node.sh`, `add_network_storage_node.sh`). The scripts create the veth pair, move it into OVS, configure the container's IP/MAC via `nsenter`, and set the default gateway — the container itself takes no action.

1. **Admin scripts** perform the full veth + OVS + IP/MAC configuration from the host.
2. **Controller B** learns the new node's MAC and port on the first data-plane packet (PacketIn), via normal L2 learning.
3. **Controller B writes the topology change** directly to the Shared MongoDB.

Topology changes are **infrequent by nature** (node joins/leaves), so writing them directly to the shared state on each change is acceptable and keeps the controllers fully decoupled from each other.

Controller A discovers the new node on its next read of the Shared MongoDB topology snapshot, which fits the existing debit cache refresh pattern.

---

## 3. VIP Provisioning Lag is Acceptable

VIP_SERVER and VIP_DADOS are **threshold-triggered and pre-provisioned** — they are not consumed instantly. The provisioning sequence involves:

```
Telemetry breach detected → Threshold evaluation → Controller provisioning decision →
Container/VM spawn → Node startup & self-registration → Flow rules installed
```

This inherent lag (typically seconds to tens of seconds) means the telemetry pipeline does **not** need to be ultra-low latency. A few seconds of aggregation delay is acceptable and even desirable, as it prevents reacting to transient spikes that would resolve themselves before provisioning could complete.

---

## 4. Telemetry & Coordination Architecture

Two distinct concerns are handled by different mechanisms, each chosen for what it is actually designed for.

### 4.1 Telemetry path — ZeroMQ PUSH/PULL → PUB/SUB

Each edge server container pushes a small metric event to the domain's **Aggregator container** after every HTTP request completes. The aggregator buffers events in memory, computes a windowed summary every 5–10 s, and publishes it to the controller. **No database sits in the telemetry path.**

```
         Network A                                    Network B
┌──────────────────────────────────┐      ┌──────────────────────────────────┐
│  edge-server-1 ──┐               │      │  edge-server-1 ──┐               │
│  edge-server-2 ──┼─ ZMQ PUSH ──→ │      │  edge-server-2 ──┼─ ZMQ PUSH ──→ │
│  edge-server-N ──┘  (per-req,    │      │  edge-server-N ──┘  (per-req,    │
│  mongo-node ───┘   incl CPU/RAM) │      │  mongo-node ───┘   incl CPU/RAM) │
│                                  │      │                                  │
│  Aggregator A (ZMQ PULL)         │      │  Aggregator B (ZMQ PULL)         │
│   buffer events in memory        │      │   buffer events in memory        │
│   every 5–10 s:                  │      │   every 5–10 s:                  │
│     compute window summary       │      │     compute window summary       │
│     (CPU/RAM already in events)  │      │     (CPU/RAM already in events)  │
│   ZMQ PUB :5556                  │      │   ZMQ PUB :5556                  │
└────────┬─────────────────────────┘      └────────┬─────────────────────────┘
         │                                          │
         ├──────────────────────────────────────────┤
         │  windowed summaries cross domain         │
         │  (raw per-request events stay local)     │
         ↓                                          ↓
┌─────────────────────────┐            ┌─────────────────────────┐
│  Controller A (ZMQ SUB) │            │  Controller B (ZMQ SUB) │
│  subscribes to:         │            │  subscribes to:         │
│   - Aggregator A        │            │   - Aggregator A        │
│   - Aggregator B        │            │   - Aggregator B        │
│  latest_telemetry keyed │            │  latest_telemetry keyed │
│  by network_id          │            │  by network_id          │
│  Thread 2 reacts:       │            │  Thread 2 reacts:       │
│   own domain thresholds │            │   own domain thresholds │
│  Thread 1 reads all:    │            │  Thread 1 reads all:    │
│   WSM scores net1+net2  │            │   WSM scores net1+net2  │
└─────────────────────────┘            └─────────────────────────┘
```

**ZeroMQ socket patterns:**

| Leg | Pattern | Rationale |
|---|---|---|
| Edge server → Aggregator | **PUSH / PULL** | Many-to-one. Fair-queued. No subscription logic needed on the sending side. |
| Aggregator → Controller | **PUB / SUB** | One-to-many. Each aggregator PUB socket is subscribed to by **both** controllers. Controller reconnects and resubscribes transparently after restart. |

**Why both controllers subscribe to both aggregators:**
- `VIP_Web` selection is cross-domain — Controller A may route a client to a server in Network B, and vice versa.
- The WSM cost function scores **all candidate servers** across both networks. It requires `T_proc` for every server, regardless of which domain it lives in.
- Each controller therefore maintains `latest_telemetry` keyed by `network_id`, updated on every incoming summary from either aggregator.
- Provisioning decisions (Threads 3) remain domain-scoped: Controller A only provisions resources in Network A, Controller B only in Network B. Cross-domain telemetry is consumed read-only for scoring.

**Why ZeroMQ and not a broker (MQTT/Redis):**
- No extra infrastructure required — the aggregator container is the only addition per domain.
- Brokerless: each leg is a direct TCP socket. ZeroMQ PUB supports multiple concurrent subscribers natively.
- Fire-and-forget semantics (`PUSH`/`PUB`) match the transient nature of telemetry events exactly.

**Why no database in the telemetry path:**
- Telemetry summaries are **transient events**, not durable state. Buffering them in memory inside the aggregator is correct.
- **Raw per-request events never leave the local domain** — only the windowed summaries (aggregated, anonymised averages) cross domain boundaries to inform the peer controller's WSM scoring.
- Controllers hold latest state in memory. Restart state loss is acceptable (topology is fixed; active VIPs are re-detected on the next demand event).

#### Per-request metric event (edge server → aggregator)

Each edge server pushes one JSON-serialised event per completed HTTP request over the ZeroMQ PUSH socket. CPU and RAM are sampled via `psutil` at send time — no Docker API access is required.

Telemetry is encapsulated in `telemetry.py` with a `MetricSender` abstraction, keeping `app.py` free of transport concerns:

```python
# telemetry.py — runs inside each edge_server container

class MetricSender(ABC):
    @abstractmethod
    def send(self, event: dict) -> None: ...

class ZmqMetricSender(MetricSender):
    def __init__(self) -> None:
        addr = os.environ.get("AGGREGATOR_PULL_ADDR", "")
        self._sock = None
        if addr:
            ctx = zmq.Context.instance()
            self._sock = ctx.socket(zmq.PUSH)
            self._sock.connect(addr)  # e.g. tcp://10.0.0.5:5555

    def send(self, event: dict) -> None:
        if self._sock is None:
            return
        try:
            self._sock.send_json(event, zmq.NOBLOCK)
        except zmq.Again:
            pass

def _build_event(time_total_ms: float, time_db_ms: float, status_code: int, request_type: str) -> dict:
    return {
        "server_id":    SERVER_ID,
        "ts":           time.time(),
        "time_total_ms": time_total_ms,
        "time_db_ms":    time_db_ms,
        "status_code":  status_code,
        "request_type": request_type,  # "read" | "write"
        "cpu_percent":  psutil.cpu_percent(),
        "ram_used_mb":  psutil.virtual_memory().used / (1024 * 1024),
    }

def init_telemetry(app: Flask, sender: MetricSender | None = None) -> None:
    _sender = sender or ZmqMetricSender()

    @app.before_request
    def _start_timer() -> None:
        g.time_start = time.monotonic()
        g.time_db_elapsed = 0.0

    @app.after_request
    def _emit_metric(response):
        time_total = (time.monotonic() - g.time_start) * 1000
        _sender.send(_build_event(
            time_total_ms=time_total,
            time_db_ms=g.time_db_elapsed * 1000,
            status_code=response.status_code,
            request_type="write" if request.method in ("POST", "PUT", "PATCH", "DELETE") else "read",
        ))
        return response
```

In `app.py`, telemetry is wired with a single call:

```python
# app.py
from telemetry import init_telemetry
...
init_telemetry(app)
```

`g.time_db_elapsed` is intended to be set by the MongoDB query helper: wrap every `collection.find()` / `insert_one()` call to record how long it blocks.

The `MetricSender` interface allows swapping the transport without touching `app.py` or the hooks — e.g. `init_telemetry(app, HttpMetricSender(...))`.

#### Aggregator container

The aggregator has its own `local_state_server` image (`aggregator.py`). CPU and RAM stats are carried inside each event (sampled by `psutil` on the edge server), so the aggregator requires no Docker API access.

```python
# aggregator.py — runs inside the aggregator container
import os, time, threading, statistics
import zmq

WINDOW_S   = float(os.environ.get("WINDOW_S", "10"))
NETWORK_ID = os.environ["NETWORK_ID"]

ctx  = zmq.Context()
pull = ctx.socket(zmq.PULL)
pull.bind(os.environ.get("PULL_ADDR", "tcp://0.0.0.0:5555"))
pub  = ctx.socket(zmq.PUB)
pub.bind(os.environ.get("PUB_ADDR", "tcp://0.0.0.0:5556"))

_buffer: list = []
_lock = threading.Lock()

def _receive_loop() -> None:
    while True:
        event = pull.recv_json()
        with _lock:
            _buffer.append(event)

def _publish_loop() -> None:
    while True:
        time.sleep(WINDOW_S)
        with _lock:
            window, _buffer[:] = list(_buffer), []
        if not window:
            continue

        by_server: dict = {}
        for event in window:
            by_server.setdefault(event["server_id"], []).append(event)

        servers = {}
        for server_id, events in by_server.items():
            time_totals = [event["time_total_ms"] for event in events]
            time_db     = [event["time_db_ms"]    for event in events]
            time_procs  = [event["time_total_ms"] - event["time_db_ms"] for event in events]
            errors      = sum(1 for event in events if event["status_code"] >= 500)
            servers[server_id] = {
                "avg_time_total_ms": statistics.mean(time_totals),
                "avg_time_db_ms":    statistics.mean(time_db),
                "avg_time_proc_ms":  statistics.mean(time_procs),
                "request_count":     len(events),
                "error_rate":        errors / len(events),
                "avg_cpu_percent":   statistics.mean([e["cpu_percent"] for e in events]),
                "avg_ram_used_mb":   statistics.mean([e["ram_used_mb"] for e in events]),
            }

        avg_time_proc   = statistics.mean([e["time_total_ms"] - e["time_db_ms"] for e in window])
        avg_time_db     = statistics.mean([e["time_db_ms"] for e in window])
        avg_cpu_percent = statistics.mean([e["cpu_percent"] for e in window])
        summary = {
            "network_id": NETWORK_ID,
            "window_end": time.time(),
            "servers":    servers,
            "domain_summary": {
                "total_requests":    len(window),
                "avg_time_proc_ms":  avg_time_proc,
                "avg_time_db_ms":    avg_time_db,
                "average_cpu_percent": avg_cpu_percent,
                "peak_time_total_ms": max(e["time_total_ms"] for e in window),
            },
        }
        pub.send_json(summary)

threading.Thread(target=_receive_loop, daemon=True).start()
_publish_loop()
```

#### Windowed summary message (aggregator → controller)

```json
{
  "network_id": "net1",
  "window_end": 1742126410.5,
  "servers": {
    "edge-server-net1-1": {
      "avg_time_total_ms": 85.2,
      "avg_time_db_ms":    47.1,
      "avg_time_proc_ms":  38.1,
      "request_count":     142,
      "error_rate":        0.02,
      "avg_cpu_percent":   34.7,
      "avg_ram_used_mb":   128.3
    }
  },
  "domain_summary": {
    "total_requests":     260,
    "avg_time_proc_ms":   38.7,
    "avg_time_db_ms":     49.4,
    "average_cpu_percent": 31.2,
    "peak_time_total_ms": 210.5
  }
}
```

> **Note on storage node telemetry:** `edge_storage_server` runs `mongo_telemetry.py` which pushes periodic events (keyed `event_type: "mongo_stats"`) with `repl_lag_s`, `connections_current`, `cpu_percent`, and `ram_used_mb` to the same aggregator PULL socket. The aggregator currently groups all events uniformly by `server_id`; dedicated `storage_nodes` aggregation in the summary is a future extension.

### 4.2 Cross-domain coordination state — Shared MongoDB

VIP registry and topology snapshots require **durable, readable state**. Pub/sub cannot serve a controller that needs to read current state independently of whether a recent event was published. The Shared MongoDB is retained exclusively for these two concerns:

```
    Controller A                        Controller B
         ↓ writes on VIP/topology change      ↓ writes on VIP/topology change
                      Shared MongoDB
                      - VIP registry (cross-domain)
                      - topology snapshots
                         ↑ read on demand by either controller
```

| Layer | Stores | Updated by | Frequency |
|---|---|---|---|
| **Aggregator container (per network)** | In-memory event buffer only — no persistence | Receives ZeroMQ PUSH events from edge servers | Continuous (per-request events) |
| **Shared MongoDB** | VIP registry, topology snapshots | Controllers only (on VIP/topology change) | Low (on-change) |

### Write/read summary

| Component | Writes to | Reads from |
|---|---|---|
| Edge/Storage Server Containers | ZeroMQ PUSH to Aggregator (telemetry) | — |
| Aggregator Container | ZeroMQ PUB summary to Controller | In-memory event buffer |
| Controllers | Shared MongoDB (VIP registry, topology) | Shared MongoDB (VIP registry, topology) |
| Shared MongoDB | — | Source of truth for cross-domain coordination |

---

## 5. Controllers as Pure Event-Driven Consumers

Controllers **do not perform telemetry aggregation**. Aggregation is the responsibility of the per-network aggregator container, keeping the controller focused on control-plane decisions.

The controller's Thread 2 runs a blocking ZeroMQ SUB receive loop. It is idle between publications (every 5–10 s) and updates a shared in-memory state dict that Threads 1 and 3 read:

```python
# controller — Thread 2: telemetry subscriber
# Subscribes to ALL aggregators (own domain + peer domains).
# latest_telemetry is keyed by network_id and read by Thread 1 (WSM) and Thread 3 (provisioning).
import zmq, json, os

OWN_DOMAIN  = os.environ["NETWORK_ID"]      # e.g. "net1"
TAU_PROC    = float(os.environ["TAU_PROC"])  # compute saturation threshold (ms)
TAU_DADOS   = float(os.environ["TAU_DADOS"]) # data-tier threshold (ms)

# Comma-separated list of all aggregator PUB addresses across all domains
# e.g. "tcp://aggregator-net1:5556,tcp://aggregator-net2:5556"
AGGREGATOR_ADDRS = os.environ["AGGREGATOR_PUB_ADDRS"].split(",")

ctx = zmq.Context.instance()
sub = ctx.socket(zmq.SUB)
for addr in AGGREGATOR_ADDRS:
    sub.connect(addr)                        # connect to each aggregator
sub.setsockopt_string(zmq.SUBSCRIBE, "")    # receive all messages from all

while True:
    summary = sub.recv_json()               # blocks until any aggregator publishes
    network_id = summary["network_id"]

    # Update shared in-memory state — keyed by network_id
    # Thread 1 reads latest_telemetry[net1] AND latest_telemetry[net2] for WSM scoring
    latest_telemetry[network_id] = summary

    # Provisioning decisions are domain-scoped:
    # only react to threshold breaches in OWN domain
    if network_id != OWN_DOMAIN:
        continue

    avg_t_proc  = summary["domain_summary"]["avg_T_proc_ms"]
    avg_t_dados = summary["domain_summary"]["avg_T_dados_ms"]

    if avg_t_proc > TAU_PROC:
        trigger_compute_provisioning(summary)    # → Thread 3 / Compute Manager

    if avg_t_dados > TAU_DADOS:
        trigger_data_gravity_transition(summary) # → Thread 3 / Data Manager
```

Thread 2 is the **single writer** to `latest_telemetry`. Threads 1 and 3 are readers only — no locks needed for simple dict reads under Python's GIL.

**Key invariants:**
- **Thread 1 (WSM scoring)** reads `latest_telemetry` for all networks to score cross-domain server candidates.
- **Thread 3 (provisioning)** only acts on summaries from `OWN_DOMAIN` — a controller never provisions resources in another controller's domain.
- **Cross-domain telemetry is read-only input** to the cost function; it never triggers local provisioning.
- **Controllers are idle** between publications — no polling, no database cursor to maintain.
- The aggregator and the controller are fully **decoupled** — either can restart independently without affecting the other.
