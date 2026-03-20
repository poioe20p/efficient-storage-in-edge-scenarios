# Implementation Plan: Topology Mixin + Proactive Flow Rules

## Objective

Port the topology discovery and proactive flow-rule installation from
`old/usecases/topology_n1.py` / `topology_n2.py` into the live controller
(`source/sdn_controller/`), stripped of all dead code and DB dependencies.

- **Local topology**: discovery, hop cache, proactive L2 flow rules — one
  `_topology_worker` background greenthread per controller instance.
- **Peer topology sharing**: each controller **publishes** its local topology
  snapshot via a ZMQ PUB socket on every change, plus a periodic heartbeat.
  The peer's existing ZMQ SUB receive loop picks it up — **no extra thread,
  no extra infrastructure, no MongoDB**.

---

## Context: Why ZMQ and Not MongoDB Change Streams

The previous draft proposed a MongoDB Change Stream for peer topology.
That was rejected for the following reasons:

1. **Reuse over complexity.** There is already an event-driven ZMQ receive
   loop waiting for messages. Adding a second blocking cursor (Change Stream)
   means a second greenthread for infrastructure that already exists.
2. **Heartbeat closes the durability gap.** The `_topology_worker` republishes
   the full topology snapshot every `TOPOLOGY_HEARTBEAT_TICKS` ticks even with
   no change. A peer that restarts gets the current state within
   `TOPOLOGY_INTERVAL × TOPOLOGY_HEARTBEAT_TICKS` seconds — acceptable given
   the system's provisioning lag is already seconds-to-tens-of-seconds.
3. **ZMQ PUB/SUB natively supports multiple endpoints on one socket.** The
   same SUB socket that already subscribes to both aggregators simply
   `connect()`s to one more endpoint: the peer controller's PUB port.

Messages are disambiguated by a `"type"` field in the JSON payload.
Telemetry summaries from aggregators carry no `"type"` field (backward-
compatible). Topology snapshots carry `"type": "topology"`.

---

## Architecture: One Greenthread Per Concern

```
KenLearnAndLog (main_n1 / main_n2)
│
├── (inherited from TopologyMixin)
│   └── hub.spawn(_topology_worker)       ← local discovery + proactive flows
│                                             + ZMQ PUB topology on change/heartbeat
│
└── ZmqTelemetrySource (already present)
    └── hub.spawn(_receive_loop)          ← subscribes to:
          - Aggregator A  :5556  → TelemetrySummary  (unchanged)
          - Aggregator B  :5556  → TelemetrySummary  (unchanged)
          - Peer ctrl     :5557  → topology snapshot  (NEW endpoint, same socket)
```

---

## File Structure

```
source/sdn_controller/
  topology.py                ← NEW   TopologyMixin
  telemetry/
    zmq_source.py            ← EDIT  add topology message routing + on_topology_update callback
  main_n1.py                 ← EDIT  add TopologyMixin to MRO; move _telemetry into __init__; fix get_latest bug
  main_n2.py                 ← EDIT  same
```

No new packages.

---

## Environment Variables

All per-network config is injected via env vars (consistent with the
existing `AGGREGATOR_ENDPOINTS` pattern).

| Variable                     | Default (n1)                | Default (n2) | Description                                                                            |
| ---------------------------- | --------------------------- | ------------ | -------------------------------------------------------------------------------------- |
| `VIP_SERVER_IP`            | `10.0.0.100`              | same         | Global virtual IP for the compute/app server pool (same across both controllers)       |
| `VIP_DATA_IP`              | `10.0.0.101`              | same         | Global virtual IP for the storage (MongoDB) pool (same across both controllers)        |
| `VIP_SERVER_MAC`           | `aa:bb:cc:dd:ee:01`       | same         | Virtual MAC for the server VIP (same across both controllers)                          |
| `VIP_DATA_MAC`             | `aa:bb:cc:dd:ee:02`       | same         | Virtual MAC for the data/storage VIP (same across both controllers)                    |
| `NETWORK_ID`               | `lan1`                    | `lan2`     | Identifies this controller's domain in published snapshots                             |
| `SERVER_MACS`              | `""`                      | `""`       | Comma-separated MACs of compute/app servers behind the VIP (e.g.`00:00:00:00:00:02`) |
| `STORAGE_MACS`             | `""`                      | `""`       | Comma-separated MACs of storage (MongoDB) servers (e.g.`00:00:00:00:00:04`)          |
| `TOPOLOGY_INTERVAL`        | `1`                       | `1`        | Seconds between topology worker ticks                                                  |
| `TOPOLOGY_PUB_PORT`        | `5557`                    | `5557`     | Port this controller binds its topology PUB socket on                                  |
| `TOPOLOGY_HEARTBEAT_TICKS` | `30`                      | `30`       | Republish snapshot every N ticks even without change                                   |
| `AGGREGATOR_ENDPOINTS`     | `tcp://10.0.0.5:5556,...` | same         | Already present — unchanged                                                           |
| `PEER_TOPOLOGY_ENDPOINTS`  | `""`                      | `""`       | Comma-separated peer controller PUB addresses, e.g.`tcp://10.0.1.X:5557`             |

`PEER_TOPOLOGY_ENDPOINTS` is appended to the existing endpoint list passed
to `ZmqTelemetrySource` — same SUB socket, one more `connect()`.

`SERVER_MACS` and `STORAGE_MACS` are **statically set at deployment time** from
the fixed MAC assignments in the build scripts. They are empty by default so the
controller starts cleanly; Thread 3 provisioning can call `add_server_mac()` /
`add_storage_mac()` at runtime to register additional dynamically provisioned
hosts.

---

## Steps

### Phase 1 — `topology.py`: TopologyMixin class

Create `source/sdn_controller/topology.py`.

#### 1.1 Imports

```python
import os
import logging
import time
import zmq
import networkx as nx
from os_ken import cfg
from os_ken.controller import ofp_event
from os_ken.controller.handler import MAIN_DISPATCHER, DEAD_DISPATCHER, set_ev_cls
from os_ken.lib import hub
from os_ken.topology.api import get_all_link, get_host
from os_ken.base import app_manager

logger = logging.getLogger(__name__)
```

#### 1.2 `__init__`

Reads env vars, initialises all state, binds ZMQ PUB socket, spawns
`_topology_worker`. Does **not** spawn a second greenthread.

```python
def __init__(self, *args, **kwargs):
    super().__init__(*args, **kwargs)
    cfg.CONF.observe_links = True

    # Global VIPs — identical on both controllers
    self.vip_server_ip  = os.environ.get("VIP_SERVER_IP",  "10.0.0.100")
    self.vip_data_ip    = os.environ.get("VIP_DATA_IP",    "10.0.0.101")
    self.vip_server_mac = os.environ.get("VIP_SERVER_MAC", "aa:bb:cc:dd:ee:01")
    self.vip_data_mac   = os.environ.get("VIP_DATA_MAC",   "aa:bb:cc:dd:ee:02")

    self._network_id           = os.environ.get("NETWORK_ID", "lan1")
    self._topology_interval    = max(1, int(os.environ.get("TOPOLOGY_INTERVAL", "1")))
    self._heartbeat_ticks      = max(1, int(os.environ.get("TOPOLOGY_HEARTBEAT_TICKS", "30")))
    self._topology_pub_port    = int(os.environ.get("TOPOLOGY_PUB_PORT", "5557"))

    self._server_macs: set[str] = {
        m.strip() for m in os.environ.get("SERVER_MACS", "").split(",") if m.strip()
    }
    self._storage_macs: set[str] = {
        m.strip() for m in os.environ.get("STORAGE_MACS", "").split(",") if m.strip()
    }

    # VIP pools — rebuilt every tick from host_attachment + peer_hosts filtered by MAC sets
    self.vip_server_pool:  dict[str, dict] = {}   # mac -> {mac, dpid, port_no}
    self.vip_storage_pool: dict[str, dict] = {}   # mac -> {mac, dpid, port_no}

    # Local topology state
    self.net             = nx.DiGraph()
    self.sws:    list    = []
    self.links:  list    = []
    self.hosts:  list    = []
    self._sws_prev:   list = []
    self._links_prev: list = []
    self._hosts_prev: list = []
    self.host_attachment: dict = {}   # mac -> (dpid, port_no)
    self.hop_cache:       dict = {}   # host_mac -> {server_mac: hops}
    self._hop_cache_max:  int  = 1
    self._installed_flow_keys: set = set()
    self._arp_rules_installed:  set = set()
    self._topology_api_app           = None
    self._topology_api_lookup_warned = False
    self._topology_initialized       = False
    self._topology_tick:     int     = 0

    self._router_mac_blocklist = {
        "00:00:00:00:00:aa", "00:00:00:00:00:bb",
        "00:00:00:00:00:cc", "00:00:00:00:00:dd",
        "00:00:00:00:00:AA", "00:00:00:00:00:BB",
        "00:00:00:00:00:CC", "00:00:00:00:00:DD",
    }

    # Peer topology — written by on_topology_update() called from ZmqTelemetrySource
    self.peer_hosts:       dict = {}   # mac -> {"mac", "dpid", "port_no"}
    self.peer_links:       list = []
    self.peer_switches:    list = []
    self._peer_network_id: str  = ""   # set from received snapshot's network_id
    # Set to True by on_topology_update when the peer's snapshot contains a stale
    # view of this controller's own local network; triggers an immediate republish.
    self._topo_correction_needed: bool = False

    # ZMQ PUB for outgoing topology snapshots
    self._topo_pub_ctx    = zmq.Context()
    self._topo_pub_socket = self._topo_pub_ctx.socket(zmq.PUB)
    self._topo_pub_socket.bind(f"tcp://*:{self._topology_pub_port}")
    logger.info("topology PUB bound on tcp://*:%d", self._topology_pub_port)

    hub.spawn(self._topology_worker)
```

#### 1.3 Runtime host registration

Called by Thread 3 provisioning when a host is added or removed. Both methods
trigger a `_rebuild_hop_cache()` so the hop distances stay current.

```python
def add_server_mac(self, mac: str) -> None:
    self._server_macs.add(mac)
    self._rebuild_hop_cache()

def remove_server_mac(self, mac: str) -> None:
    self._server_macs.discard(mac)
    self._rebuild_hop_cache()

def add_storage_mac(self, mac: str) -> None:
    self._storage_macs.add(mac)
    self._rebuild_hop_cache()

def remove_storage_mac(self, mac: str) -> None:
    self._storage_macs.discard(mac)
    self._rebuild_hop_cache()
```

#### 1.4 Query helpers (used by Thread 1 scheduling)

```python
def get_edge_switch(self, host_mac: str):
    return self.host_attachment.get(host_mac)

def get_hops(self, host_mac: str, server_mac: str):
    return self.hop_cache.get(host_mac, {}).get(server_mac)

def get_next_hop_port(self, edge_dpid: int, client_mac: str, server_mac: str):
    try:
        path = nx.shortest_path(self.net, client_mac, server_mac)
        idx  = path.index(edge_dpid)
        return self.net[edge_dpid][path[idx + 1]]["port"]
    except (nx.NetworkXNoPath, nx.NodeNotFound, ValueError, IndexError, KeyError):
        return None
```

#### 1.5 `on_topology_update(data: dict)` — peer topology callback

Called by `ZmqTelemetrySource._receive_loop` when a message with
`"type": "topology"` arrives from the peer controller's PUB socket.

Each controller now publishes its **global** topology snapshot (local + accumulated
peer data). When the receiving controller parses that snapshot it checks whether
the sender's view of the receiver's own local network is stale and, if so,
immediately republishes rather than waiting for the next heartbeat tick.

```python
def on_topology_update(self, data: dict) -> None:
    # Extract the section that describes THIS controller's own local network,
    # if the sender included it (present when sender has already received our topology).
    peer_view_of_local = data.get("networks", {}).get(self._network_id)
    if peer_view_of_local is not None and self.host_attachment:
        peer_known_macs = {h["mac"] for h in peer_view_of_local.get("hosts", [])}
        local_macs      = set(self.host_attachment.keys())
        if peer_known_macs != local_macs:
            logger.info(
                "peer has stale view of %s (%d vs %d hosts) — triggering immediate republish",
                self._network_id, len(peer_known_macs), len(local_macs),
            )
            self._topo_correction_needed = True

    # Accept the peer's local-network data and record its network_id
    peer_nid  = data.get("network_id", "")
    local_net = data.get("networks", {}).get(peer_nid, {})
    self._peer_network_id = peer_nid
    self.peer_hosts    = {h["mac"]: h for h in local_net.get("hosts", [])}
    self.peer_links    = local_net.get("links", [])
    self.peer_switches = local_net.get("switches", [])
    logger.debug(
        "peer topology updated from %s: %d hosts",
        data.get("network_id", "?"), len(self.peer_hosts)
    )
```

#### 1.6 `_state_change_handler`

Kept in the mixin because it manages `self._datapath_by_id` (declared in
parent via `super().__init__`) and must fire on OS-Ken state events.

```python
@set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
def _state_change_handler(self, ev):
    datapath = ev.datapath
    if ev.state == MAIN_DISPATCHER:
        entry = (datapath, datapath.id)
        if entry not in self.sws:
            self.sws.append(entry)
        self._datapath_by_id[datapath.id] = entry
    elif ev.state == DEAD_DISPATCHER:
        entry = (datapath, datapath.id)
        if entry in self.sws:
            self.sws.remove(entry)
        self._datapath_by_id.pop(datapath.id, None)
```

#### 1.7 Internal helpers — ported verbatim from old code

- `check_link(link_in, links_list)` — deduplication guard
- `_get_topology_api_app()` — lazy OS-Ken topology API resolution with
  warn-once logging
- `get_sws_links_hosts()` — rebuilds `self.net`, `self.hosts`, `self.links`,
  `self.host_attachment`
- `_rebuild_hop_cache()` — recomputes `hop_cache` from
  `(self._server_macs | self._storage_macs) ∩ self.host_attachment`
  (union of both sets so hop distances are available for every backend pool)

#### 1.8 `_topology_worker` greenthread

```
loop every _topology_interval seconds:
  _topology_tick += 1
  get_sws_links_hosts()
  _rebuild_hop_cache()
  _rebuild_vip_pools()

  changed    = hosts/links/sws differ from prev snapshots
  first_valid = not _topology_initialized and sws and links and hosts

  if first_valid or changed:
    _install_local_topology_flows()
    _topology_initialized = True
    logger.info("topology installed: %d sw %d links %d hosts", ...)

  update prev snapshots (_sws_prev, _links_prev, _hosts_prev)

  should_publish = (
    first_valid
    or changed
    or _topo_correction_needed          ← peer has stale view of us
    or _topology_tick % _heartbeat_ticks == 0
  )
  if should_publish and sws:
    _publish_topology()
    _topo_correction_needed = False

  exceptions → logger.error; KeyboardInterrupt → break
```

`_topology_initialized` replaces the old `topology_has_been_stored` +
`last_topology_store_time` pair. The `_topology_tick % _heartbeat_ticks`
guard guarantees the peer always gets a fresh snapshot after reconnect
without any polling.

#### 1.9 `_publish_topology()`

Serialises current local topology and sends via the PUB socket.
`zmq.NOBLOCK` — dropped silently if no subscriber is connected yet.

Each snapshot now carries the controller's **global view** under a `"networks"`
dict keyed by network ID. The receiver uses this to detect if the sender has a
stale copy of the receiver's own local network (see §1.5).

```python
def _publish_topology(self) -> None:
    local_section = {
        "hosts":    [
            {"mac": mac, "dpid": dpid, "port_no": port_no}
            for mac, (dpid, port_no) in self.host_attachment.items()
        ],
        "links":    [
            {"src_dpid": l[0], "src_port_no": l[2], "dst_dpid": l[1]}
            for l in self.links
        ],
        "switches": [sw[1] for sw in self.sws],
    }
    # Reconstruct peer's network section from accumulated peer data
    peer_section = {
        "hosts":    list(self.peer_hosts.values()),
        "links":    self.peer_links,
        "switches": self.peer_switches,
    }
    networks = {self._network_id: local_section}
    if self._peer_network_id:
        networks[self._peer_network_id] = peer_section
    snapshot = {
        "type":       "topology",
        "network_id":  self._network_id,
        "networks":    networks,
        # Keep flat local fields for backward-compat with §2.2 routing
        "hosts":    local_section["hosts"],
        "links":    local_section["links"],
        "switches": local_section["switches"],
        "hops":     self.hop_cache,
        "ts":       time.time(),
    }
    try:
        self._topo_pub_socket.send_json(snapshot, zmq.NOBLOCK)
    except zmq.Again:
        pass  # no subscriber yet — normal at startup
```

#### 1.10 Flow installation helpers — ported verbatim

#### 1.11 `_rebuild_vip_pools()`

Merges local `host_attachment` and peer `peer_hosts` into a single combined
source, then filters by each MAC membership set. Called every topology tick
(cheap dict comprehension over already-computed data — no I/O).

```python
def _rebuild_vip_pools(self) -> None:
    # Normalise local entries to the same shape as peer_hosts
    combined: dict[str, dict] = {
        mac: {"mac": mac, "dpid": dpid, "port_no": port_no}
        for mac, (dpid, port_no) in self.host_attachment.items()
    }
    # peer_hosts already has shape {mac: {"mac", "dpid", "port_no"}}
    combined |= self.peer_hosts

    self.vip_server_pool  = {mac: combined[mac] for mac in self._server_macs  if mac in combined}
    self.vip_storage_pool = {mac: combined[mac] for mac in self._storage_macs if mac in combined}
```

- `_install_local_topology_flows()`
- `proactive_flow_rule_install(sw, p)`
- `send_all_flow_rules_proactively()`
- `_install_path_flows(path)`

---

### Phase 2 — Edit `zmq_source.py`

Extend the receive loop to route topology messages without breaking existing
telemetry behaviour.

#### 2.1 Add `on_topology_update` parameter

```python
def __init__(self, endpoints: list[str], on_update=None, on_topology_update=None) -> None:
    ...
    self._on_topology_update = on_topology_update
```

#### 2.2 Route by `"type"` field in `_receive_loop`

```python
data = eventlet.tpool.execute(self._socket.recv_json)
if isinstance(data, dict) and data.get("type") == "topology":
    if self._on_topology_update is not None:
        self._on_topology_update(data)
else:
    summary = TelemetrySummary.model_validate(data)
    self._latest[summary.network_id] = summary
    if self._on_update is not None:
        self._on_update(summary)
```

Aggregator messages carry no `"type"` field — this branch is fully
backward-compatible.

---

### Phase 3 — Edit `main_n1.py` *(parallel with Phase 4)*

1. Add `from .topology import TopologyMixin`.
2. Parse `PEER_TOPOLOGY_ENDPOINTS` (same pattern as `AGGREGATOR_ENDPOINTS`).
3. Move `_telemetry` construction from module level into `KenLearnAndLog.__init__`
   so the `on_topology_update=self.on_topology_update` callback can reference
   the instance. Pass the combined endpoint list
   (`AGGREGATOR_ENDPOINTS + PEER_TOPOLOGY_ENDPOINTS`).
4. Update class declaration:
   ```python
   class KenLearnAndLog(TopologyMixin, app_manager.OSKenApp):
   ```
5. Remove the stale `get_latest("lan1")` call at the bottom of
   `packet_in_handler` — the ZMQ `on_update` callback already prints;
   calling it again here creates double-printing and couples Thread 1 to
   telemetry consumption (Thread 2's concern).

### Phase 4 — Edit `main_n2.py` *(parallel with Phase 3)*

Same as Phase 3. The only difference is the default `NETWORK_ID` is `lan2`
(set via env var — no code change needed).

---

## What Is Explicitly NOT Ported

| Dropped                                                     | Reason                                                |
| ----------------------------------------------------------- | ----------------------------------------------------- |
| MongoDB Change Stream for peer topology                     | Replaced by ZMQ PUB heartbeat on `_topology_worker` |
| `store_topology_in_db()` / `TopologyRepository`         | Thread 3 provisioning concern, not discovery          |
| `CalculateGlobalTopology` + field                         | Thread 3 scheduling concern                           |
| `global_net` (n1 only)                                    | Unused after DB calls removed                         |
| `topology_has_been_stored` + `last_topology_store_time` | Replaced by `_topology_initialized`                 |
| Commented-out `eventlet.spawn_n` blocks                   | Dead code                                             |
| `MongodbRouter` import                                    | Not needed here                                       |
| `self.cnt` modulo counter                                 | Replaced by `_topology_tick` + change-detection     |
| Module-level `_telemetry` construction                    | Moved into `__init__` — no import side-effects     |
| `print()` every 40th tick                                 | Replaced by `logger.info/debug` on change-detection |

---

## Verification

1. **Import**: `python -c "from source.sdn_controller.main_n1 import KenLearnAndLog"` — no errors.
2. **MRO**: `KenLearnAndLog.__mro__` has `TopologyMixin` before `OSKenApp`.
3. **PUB binds**: controller logs `topology PUB bound on tcp://*:5557` at startup.
4. **Heartbeat**: `_publish_topology()` fires every 30 ticks even without topology change.
5. **Peer routing**: inject `{"type": "topology", "network_id": "lan2", "hosts": [...], ...}`
   into the SUB socket; `on_topology_update` is called and `peer_hosts` is populated.
6. **VIP pools populated**: set `SERVER_MACS=00:00:00:00:00:02` and
   `STORAGE_MACS=00:00:00:00:00:04`; after the first topology tick,
   `vip_server_pool` and `vip_storage_pool` each contain one entry with correct
   `{mac, dpid, port_no}`. Inject a peer host with a storage MAC; verify it
   appears in `vip_storage_pool` on the next tick.
7. **No double print**: only one `[telemetry]` line per summary in controller stdout.
