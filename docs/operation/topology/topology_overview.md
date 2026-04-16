# Topology — Overview

## Purpose

The topology subsystem is the foundation of the SDN controller. It discovers the
local OpenFlow network (switches, hosts, links), computes shortest-path hop
counts, maintains VIP backend pools, and shares its view with the peer
controller over ZMQ. The topology layer feeds its data (hop cache, VIP pools,
host attachment map) into the VIP routing mixin.

---

## Architecture

```
                        ┌──────────────────────────────────────────────┐
                        │             SDN Controller (N1)             │
                        │                                             │
  OpenFlow switch ◄────►│  Thread 1 (OS-Ken event loop)               │
       (OVS)            │    ├─ packet_in_handler                     │
                        │    │    └─ L2 learning (reactive fallback)  │
                        │    │                                        │
                        │    └─ _topology_worker (greenthread)        │
                        │         ├─ poll local topology              │
                        │         ├─ _rebuild_hop_cache()             │
                        │         ├─ _rebuild_vip_pools()             │
                        │         ├─ install proactive L2 flows       │
                        │         └─ _publish_topology() via ZMQ PUB  │
                        │                                             │
                        │  Thread 2 (ZMQ subscriber)                  │
                        │    └─ on_topology_update()                  │
                        │         ├─ validate TopologySnapshot        │
                        │         ├─ merge peer MAC roles             │
                        │         └─ seed _mac_to_ip for peer hosts   │
                        └──────────────┬───────────────────────────────┘
                                       │ ZMQ PUB/SUB
                                       ▼
                        ┌──────────────────────────────────────────────┐
                        │             SDN Controller (N2)             │
                        │         (mirrors the same architecture)     │
                        └──────────────────────────────────────────────┘
```

---

## File Layout

```
source/sdn_controller/
├── topology/
│   ├── __init__.py
│   ├── models.py                 # Pydantic models for topology snapshots
│   └── topology.py               # TopologyMixin — discovery, proactive flows,
│                                 #   ZMQ PUB peer sharing, hop cache, VIP pools
```

---

## Topology Discovery and Proactive Flows

### Local Discovery

The `_topology_worker` greenthread runs every `_topology_interval` seconds
(default 1, from `TOPOLOGY_INTERVAL` env var). Each iteration:

1. Queries the OS-Ken topology API for current switches, hosts, and links.
2. Filters out hosts whose MAC is in `_router_mac_blocklist` (derived from
   `ROUTER_MAC_BLOCKLIST` env var) to prevent routers from appearing as
   backends.
3. Builds a `host_attachment` dict mapping `mac → (dpid, port_no)` for all
   locally discovered hosts.
4. Compares the new topology against the previous snapshot; if anything changed
   (or a correction/heartbeat is due), the worker triggers downstream updates.

### Hop Cache

`_rebuild_hop_cache()` constructs a NetworkX `DiGraph` from the discovered
switches and links. For every pair of hosts it computes the shortest path
length and stores it in `hop_cache[src_mac][dst_mac]`. The maximum hop count
is cached in `_hop_cache_max` for WSM normalization. An `_avg_hop_count`
(average over all local pairs) is computed and included in published topology
snapshots — the peer controller uses this value as `_peer_avg_hop_count` for
its cross-network hop penalty estimate.

### Proactive L2 Flow Installation

When the topology changes, the worker installs proactive forwarding rules for
every known host:

| Priority | Purpose                         | Match                         | Action                    |
|----------|---------------------------------|-------------------------------|---------------------------|
| 0        | Table-miss                      | (wildcard)                    | Send to controller        |
| 1        | ARP flood                       | `eth_type=0x0806`             | Flood                     |
| 5        | Proactive L2 forwarding         | `eth_dst=<host_mac>`          | Output to computed port   |
| 10       | Reactive L2 (from packet_in)    | `in_port, eth_dst`            | Output to learned port    |

Proactive rules (priority 5) cover every locally and peer-discovered host.
A deduplication set (`_installed_flow_keys`) prevents reinstalling identical
rules. When a switch reconnects, `_state_change_handler` flushes all stale
flows and reinstalls the table-miss rule, then calls `_on_datapath_connected()`
so mixins higher in the MRO (e.g. `VipRoutingMixin`) can reinstall their own
rules.

---

## VIP Configuration

Three virtual IP addresses are used:

| VIP             | Env Vars (IP / MAC)                       | Purpose                                    |
|-----------------|-------------------------------------------|--------------------------------------------|
| **VIP_SERVER**  | `VIP_SERVER_IP`, `VIP_SERVER_MAC`         | HTTP edge servers (shared across domains)  |
| **VIP_DATA_N1** | `VIP_DATA_N1_IP`, `VIP_DATA_N1_MAC`      | MongoDB storage on LAN 1                  |
| **VIP_DATA_N2** | `VIP_DATA_N2_IP`, `VIP_DATA_N2_MAC`      | MongoDB storage on LAN 2                  |

VIP_DATA is per-domain: edge servers on LAN 1 connect to `VIP_DATA_N1` to reach
LAN 1's MongoDB replica set, and to `VIP_DATA_N2` to reach LAN 2's. This
separation allows the WSM cost function to independently select the best storage
node in each domain.

---

## MAC Role Management

### Role Sets

Backends are classified into roles by MAC address. Each role is split into local
and peer sets, with a `@property` union:

| Property       | Local set              | Peer set               | Purpose                            |
|----------------|------------------------|------------------------|------------------------------------|
| `server_macs`  | `_local_server_macs`   | `_peer_server_macs`    | HTTP edge server containers        |
| `storage_macs_n1` | `_local_storage_macs_n1` | `_peer_storage_macs_n1` | MongoDB storage containers (LAN 1) |
| `storage_macs_n2` | `_local_storage_macs_n2` | `_peer_storage_macs_n2` | MongoDB storage containers (LAN 2) |

### Seeding

Local MAC sets are seeded at startup from environment variables:

- `SERVER_MACS` — comma-separated MACs for HTTP backends.
- `STORAGE_MACS_N1` — comma-separated MACs for LAN 1 storage.
- `STORAGE_MACS_N2` — comma-separated MACs for LAN 2 storage.

### Dynamic Updates

Thread 3 (elasticity manager) calls `add_server_mac(mac)` or
`add_storage_mac(mac, domain)` after spawning a new container. These methods
append to the local set and automatically propagate via the next topology
publish cycle.

### Peer MAC Merge

When a `TopologySnapshot` arrives from the peer controller, the receiver
performs a wholesale replacement of the peer MAC sets from the snapshot's
`server_macs`, `storage_macs_n1`, and `storage_macs_n2` fields. This ensures
both controllers converge on the same global view.

---

## VIP Pool Rebuild

`_rebuild_vip_pools()` is called whenever the topology changes. It merges
`host_attachment` (locally discovered hosts) with `peer_hosts` (hosts
reported by the peer controller), then filters by MAC role membership:

```
vip_server_pool      = {mac: entry for mac in server_macs     if mac in merged}
vip_storage_pool_n1  = {mac: entry for mac in storage_macs_n1 if mac in merged}
vip_storage_pool_n2  = {mac: entry for mac in storage_macs_n2 if mac in merged}
```

Each pool entry contains `{"mac": ..., "dpid": ..., "port_no": ...}`. Only
hosts that are both configured (via MAC role) **and** topologically reachable
appear in the pool.

---

## Peer Topology Sharing

### Publishing

`_publish_topology()` builds a `TopologySnapshot` containing:

- `network_id` — this controller's identity (e.g. `"n1"`).
- `networks` — a dict with one entry keyed by `network_id`, containing a
  `TopologyNetworkSection` with the local hosts, links, and switch list.
- `hops` — the full local hop cache.
- `server_macs`, `storage_macs_n1`, `storage_macs_n2` — current local MAC role
  sets (so the peer can merge them).
- `avg_hop_count` — average local hop distance (used by the peer for
  cross-network penalty estimation).

The snapshot is serialized via `model_dump_json()` and sent over a ZMQ PUB
socket using `send_string()`.

Topology is published on three triggers:
1. **Change** — the local view differs from the previous snapshot.
2. **Heartbeat** — every `TOPOLOGY_HEARTBEAT_TICKS` topology ticks with no
   change (default 30 ticks × 1 s interval = 30 s).
3. **Correction** — a stale peer view was detected in the incoming snapshot.

### Receiving

`on_topology_update(data)` is the callback invoked by Thread 2 when a ZMQ
message arrives from the peer controller:

1. Validates the JSON payload via `TopologySnapshot.model_validate()`.
2. Extracts the peer's network section, hosts, and hops.
3. Checks for staleness: if the peer's snapshot includes a view of our own
   network that disagrees with our current state, it sets
   `_topo_correction_needed = True` so the next worker cycle publishes a
   corrective update.
4. Replaces peer MAC role sets wholesale.
5. Seeds `_mac_to_ip` for each peer host that carries an `ip` field, via
   `register_backend_ip()`.

---

## Pydantic Models

All inter-controller topology messages are validated at the transport boundary
using Pydantic v2 models:

```python
class TopologyHostEntry(BaseModel):
    mac: str
    dpid: int
    port_no: int
    ip: str | None = None          # added for MAC→IP seeding

class TopologyLinkEntry(BaseModel):
    src_dpid: int
    src_port_no: int
    dst_dpid: int

class TopologyNetworkSection(BaseModel):
    hosts: list[TopologyHostEntry]
    links: list[TopologyLinkEntry]
    switches: list[int]

class TopologySnapshot(BaseModel):
    network_id: str
    networks: dict[str, TopologyNetworkSection] = {}
    hosts: list[TopologyHostEntry] = []          # flat compat fields
    links: list[TopologyLinkEntry] = []
    switches: list[int] = []
    hops: dict[str, dict[str, int]] = {}
    server_macs: list[str] = []
    storage_macs_n1: list[str] = []
    storage_macs_n2: list[str] = []
    avg_hop_count: float = 0.0
```

---

## Flow Priority Summary (Topology Layer)

| Priority | Rule                           | Installed by          |
|----------|--------------------------------|-----------------------|
| 0        | Table-miss → controller        | TopologyMixin         |
| 1        | ARP flood                      | TopologyMixin         |
| 5        | Proactive L2 forwarding        | TopologyMixin         |
| 10       | Reactive L2 learning           | main_n*.py            |

Higher-priority rules (100, 200) are installed by `VipRoutingMixin` — see the
[VIP Routing Overview](../vip_routing/vip_routing_overview.md).

---

## Environment Variables

| Variable                       | Default                      | Purpose                                            |
|--------------------------------|------------------------------|----------------------------------------------------|
| `LAN_ID`                      | `lan1`                       | Network identity for published topology snapshots  |
| `TOPOLOGY_INTERVAL`           | `1`                          | Seconds between topology worker polls              |
| `TOPOLOGY_HEARTBEAT_TICKS`    | `30`                         | Publish a heartbeat every N ticks with no change   |
| `TOPOLOGY_PUB_PORT`           | `5557`                       | ZMQ PUB bind port for outgoing topology snapshots  |
| `PEER_TOPOLOGY_ENDPOINTS`     | *(empty)*                    | Comma-separated peer controller PUB addresses      |
| `SERVER_MACS`                 | *(empty)*                    | Comma-separated initial HTTP server MACs           |
| `STORAGE_MACS_N1`             | *(empty)*                    | Comma-separated initial LAN 1 storage MACs         |
| `STORAGE_MACS_N2`             | *(empty)*                    | Comma-separated initial LAN 2 storage MACs         |
| `VIP_SERVER_IP`               | `10.0.0.253`                 | Virtual IP for HTTP edge servers                   |
| `VIP_SERVER_MAC`              | `aa:bb:cc:dd:ee:01`          | Virtual MAC for VIP_SERVER                         |
| `VIP_DATA_N1_IP`              | `10.0.0.254`                 | Virtual IP for LAN 1 MongoDB storage               |
| `VIP_DATA_N1_MAC`             | `aa:bb:cc:dd:ee:02`          | Virtual MAC for VIP_DATA_N1                        |
| `VIP_DATA_N2_IP`              | `10.0.1.254`                 | Virtual IP for LAN 2 MongoDB storage               |
| `VIP_DATA_N2_MAC`             | `aa:bb:cc:dd:ee:03`          | Virtual MAC for VIP_DATA_N2                        |


