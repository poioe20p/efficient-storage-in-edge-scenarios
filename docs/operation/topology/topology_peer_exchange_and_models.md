# Topology Peer Exchange and Models

## 1. Purpose

This document describes how the SDN controller publishes its local topology
view to the peer controller over ZMQ, how it receives and merges the peer's
view, and the Pydantic models that define the inter-controller topology
snapshot contract. It covers publish triggers, stale-peer detection, wholesale
replacement rules for MAC roles and storage roles, and the reason flat
compatibility fields are preserved.

## 2. Current Files

- `source/sdn_controller/topology/models.py` — Pydantic v2 models for topology
  snapshots (`TopologyHostEntry`, `TopologyLinkEntry`,
  `TopologyNetworkSection`, `TopologySnapshot`).
- `source/sdn_controller/topology/topology.py` — `TopologyMixin`; contains
  `_publish_topology()` (PUB side) and `on_topology_update()` (receive side).
- `source/sdn_controller/telemetry/zmq_source.py` — `ZmqTelemetrySource`; the
  ZMQ SUB greenthread that receives JSON messages and dispatches topology
  snapshots to `on_topology_update()`.
- `source/sdn_controller/main_n1.py` (and `main_n2.py`) — wires the
  `on_topology_update` callback when constructing `ZmqTelemetrySource`.

## 3. Topology Models

All inter-controller topology messages are validated at the transport boundary
using Pydantic v2 models, defined in `models.py`:

```python
class TopologyHostEntry(BaseModel):
    mac: str
    dpid: int
    port_no: int
    ip: str | None = None          # populated for MAC→IP seeding

class TopologyLinkEntry(BaseModel):
    src_dpid: int
    src_port_no: int
    dst_dpid: int

class TopologyNetworkSection(BaseModel):
    hosts: list[TopologyHostEntry] = []
    links: list[TopologyLinkEntry] = []
    switches: list[int] = []

class TopologySnapshot(BaseModel):
    type: str = "topology"         # discriminator vs telemetry summaries
    network_id: str                # publishing controller's LAN identity
    networks: dict[str, TopologyNetworkSection] = {}
    hosts: list[TopologyHostEntry] = []      # flat compat fields
    links: list[TopologyLinkEntry] = []
    switches: list[int] = []
    hops: dict = {}
    ts: float = 0.0                # publish timestamp (time.time())
    avg_hop_count: float = 0.0
    server_macs: list[str] = []
    storage_macs_n1: list[str] = []
    storage_macs_n2: list[str] = []
    storage_roles: dict[str, str] = {}
```

## 4. Published Snapshot Shape

`_publish_topology()` constructs a `TopologySnapshot` with the following data:

| Field | Source | Notes |
|---|---|---|
| `type` | hardcoded default `"topology"` | Discriminates from telemetry summaries on the same ZMQ socket |
| `network_id` | `self._network_id` (from `LAN_ID` env var) | Identifies the publishing controller |
| `networks` | Local `TopologyNetworkSection` + peer section (if known) | Each section contains hosts, links, and switches |
| `hosts` | Flat copy of `local_section.hosts` | Duplicated from `networks[self._network_id].hosts` for backward compat |
| `links` | Flat copy of `local_section.links` | Duplicated from `networks[self._network_id].links` |
| `switches` | Flat copy of `local_section.switches` | Duplicated from `networks[self._network_id].switches` |
| `hops` | `self.hop_cache` | Full local hop cache for WSM cost computation |
| `ts` | `time.time()` | Publisher timestamp |
| `avg_hop_count` | `self._avg_hop_count` | Used by peer for cross-network hop penalty |
| `server_macs` | `list(self._local_server_macs)` | Local HTTP server MACs |
| `storage_macs_n1` | `list(self._local_storage_macs_n1)` | Local LAN 1 storage MACs |
| `storage_macs_n2` | `list(self._local_storage_macs_n2)` | Local LAN 2 storage MACs |
| `storage_roles` | `dict(self._local_storage_roles)` | Local RS role map for primary discovery |

The snapshot is serialized via `snapshot.model_dump_json()` and sent over a ZMQ
PUB socket using `send_string()` with the `zmq.NOBLOCK` flag (silently drops if
no subscriber is ready — normal at startup).

## 5. Publish Triggers

The `_topology_worker()` decides whether to publish after each poll cycle.
Topology is published on any of these triggers:

| Trigger | Condition | Reason |
|---|---|---|
| **First valid** | First tick where `sws`, `links`, and `hosts` are all non-empty | Bootstraps the peer's view |
| **Local change** | `hosts`, `links`, or `sws` differ from the previous snapshot | Propagates topology changes immediately |
| **Correction** | `_topo_correction_needed` was set by `on_topology_update()` (peer had a stale view of our network) | Repairs the peer's incorrect state |
| **Heartbeat** | Every `TOPOLOGY_HEARTBEAT_TICKS` ticks (default 30) with no other trigger | Ensures liveness and detects peer disconnection |

After publishing, `_topo_correction_needed` is reset to `False`.

## 6. Peer Update Receive Path

### Callback Wiring

In `main_n1.py` (and `main_n2.py`), the `ZmqTelemetrySource` is constructed
with `on_topology_update=self.on_topology_update`:

```python
self._telemetry_source = ZmqTelemetrySource(
    endpoints=_aggregator_endpoints + _peer_endpoints,
    on_update=self._on_telemetry_update,
    on_topology_update=self.on_topology_update,
)
```

Both telemetry summaries and topology snapshots arrive on the same ZMQ SUB
socket. The receiver distinguishes them by the `type` field in the JSON payload.

### `ZmqTelemetrySource._receive_loop`

1. Calls `self._socket.recv_json()` (via `eventlet.tpool.execute` to avoid
   blocking the OS-Ken event loop).
2. Checks `isinstance(data, dict) and data.get("type") == "topology"`.
3. If topology — calls `self._on_topology_update(data)`.
4. Otherwise — treats the message as a `TelemetrySummary`.

### `on_topology_update(data)`

1. **Validate** — calls `TopologySnapshot.model_validate(data)`. If parsing
   fails, logs a warning and returns.
2. **Stale-peer detection** — if the snapshot contains a `networks` entry for
   `self._network_id` (our own network), compares the set of MACs the peer
   thinks we have against `self.host_attachment`. If they differ, sets
   `_topo_correction_needed = True` so the next worker cycle republishes a
   corrective update.
3. **Extract peer data** — reads `snapshot.network_id` to identify the peer,
   then extracts `peer_hosts`, `peer_links`, and `peer_switches` from
   `snapshot.networks[peer_nid]`.
4. **Merge MAC roles** — replaces peer MAC role sets wholesale (see § 7).
5. **Seed IPs** — calls `register_backend_ip()` for each peer host that
   carries an `ip` field (see § 8).

## 7. Peer MAC and Role Replacement Rules

When `on_topology_update()` processes a valid snapshot, it performs a
**wholesale replacement** of all peer-scoped data. This ensures removals
(containers scaled down on the peer) propagate correctly — incremental
add/remove would leak stale entries.

```python
self._peer_server_macs     = set(snapshot.server_macs)
self._peer_storage_macs_n1 = set(snapshot.storage_macs_n1)
self._peer_storage_macs_n2 = set(snapshot.storage_macs_n2)
self._peer_storage_roles   = dict(snapshot.storage_roles)
self._peer_avg_hop_count   = snapshot.avg_hop_count
```

The same wholesale rule applies to `storage_roles`: the peer's `dict` is
replaced entirely rather than merged. This matches the fresh-rebuild approach
used on the local side and prevents stale `"primary"` entries from surviving
a peer RS re-election.

## 8. Peer Host IP Seeding

For each peer host that carries an `ip` field in `TopologyHostEntry`, the
receive path seeds the MAC-to-IP mapping:

```python
for h in self.peer_hosts.values():
    ip = h.get("ip")
    if ip:
        self.register_backend_ip(h["mac"], ip)
```

`register_backend_ip(mac, ip)` is defined in `VipRoutingMixin` (in
`vip_routing.py`). It populates `_mac_to_ip[mac]` and `_ip_to_mac[ip]` so that
VIP routing can resolve cross-network backend IPs without waiting for local
ARP snooping (which never fires for hosts on the peer LAN).

## 9. Backward-Compatibility Fields

The `TopologySnapshot` model includes flat fields `hosts`, `links`, and
`switches` at the top level, in addition to the structured `networks` dict.
These fields contain a copy of the publishing controller's own network section
data.

**Why they exist:** Older VIP routing code paths access
`snapshot.hosts` / `snapshot.links` / `snapshot.switches` directly instead of
navigating into `networks[network_id]`. Maintaining the flat fields avoids a
refactor of that consumer code while still providing the richer `networks`
structure for peer-exchange features (stale detection, per-network sections).

The flat fields are populated in `_publish_topology()`:

```python
snapshot = TopologySnapshot(
    network_id=self._network_id,
    networks=networks,
    # Flat local fields for backward-compat with routing code
    hosts=local_section.hosts,
    links=local_section.links,
    switches=local_section.switches,
    ...
)
```

New code should prefer the `networks` dict.
