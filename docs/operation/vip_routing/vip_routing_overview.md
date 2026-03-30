# VIP Routing — Overview

## Purpose

`VipRoutingMixin` intercepts traffic destined for virtual IP addresses and
load-balances it across backend containers using multi-dimensional WSM (Weighted
Sum Model) cost functions. It handles ARP virtualization, DNAT/SNAT flow rule
installation, and cross-network forwarding via the inter-LAN router.

This is **not a new thread**. All methods run inline in Thread 1's
`packet_in_handler` — same greenthread, same event loop. State written by
Thread 2 (`_server_stats`, `_storage_stats`) is read here without locks because
eventlet uses cooperative switching and these dicts are only mutated between
yield points.

---

## Architecture

```
KenLearnAndLog(VipRoutingMixin, TopologyMixin, OSKenApp)
       │
       ├── Thread 1 (OS-Ken event loop) ─── packet_in_handler()
       │       │
       │       ├─ snoop_arp()  ─────────────► learn IP ↔ MAC
       │       │
       │       ├─ Is VIP packet? ──Yes──► handle_vip_packet_in()
       │       │                              ├─ ARP for VIP? → _reply_vip_arp()
       │       │                              ├─ VIP_SERVER?   → select_server() + DNAT/SNAT
       │       │                              ├─ VIP_DATA_N1?  → select_storage("n1") + DNAT/SNAT
       │       │                              └─ VIP_DATA_N2?  → select_storage("n2") + DNAT/SNAT
       │       │
       │       └─ Not VIP ────────────► existing L2 learning logic
       │
       ├── Thread 2 (ZMQ subscriber) ── _on_telemetry_update()
       │       ├─ update_server_stats()    → _server_stats dict
       │       └─ update_storage_stats()   → _storage_stats dict
       │
       └── Thread 3 (elasticity) ── register_backend_ip() after spawning new containers
```

`VipRoutingMixin` must sit **before** `TopologyMixin` in the class MRO so that
its `_on_datapath_connected` hook runs first and installs VIP punt rules after
a switch reconnect.

---

## File Layout

```
source/sdn_controller/
├── main_n1.py / main_n2.py       # Controller entry points — class MRO:
│                                 #   KenLearnAndLog(VipRoutingMixin, TopologyMixin, OSKenApp)
│                                 #   _on_telemetry_update() → update stats + threshold alerts
├── vip_routing.py                # VipRoutingMixin — ARP snooping, VIP intercept,
│                                 #   WSM cost functions, DNAT/SNAT rule pairs
```

---

## VIP Addresses

Three virtual IP addresses are managed. The IPs and MACs are configured via
environment variables and stored as attributes on `TopologyMixin` (see the
[Topology Overview](../topology/topology_overview.md)):

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

## MAC → IP Resolution

For DNAT/SNAT rules the controller needs both the MAC and IP of the selected
backend. The `_mac_to_ip` / `_ip_to_mac` dictionaries (defined in
`VipRoutingMixin.__init__`) are populated from three sources:

1. **ARP snooping** (`snoop_arp()`) — any ARP packet that reaches the controller
   has its sender IP/MAC recorded. This is the authoritative source and
   overwrites static seeds.
2. **Flush + ping bootstrap** — instead of `arping` (which may not be installed
   in containers), the network setup scripts use flush + ping to force ARP
   resolution at startup.
3. **Peer topology seeding** — `TopologyMixin.on_topology_update()` calls
   `register_backend_ip(mac, ip)` for every peer host that carries an `ip`
   field in its `TopologyHostEntry`. This ensures the controller can route to
   peer backends immediately without waiting for cross-network ARP traffic.

`register_backend_ip()` is also called by Thread 3 (elasticity manager) after
spawning a new container, so VIP routing can reach the new backend before its
first ARP reaches the controller.

---

## ARP Interception

When a client sends an ARP request for any VIP address, the controller generates
a crafted ARP reply with the VIP's virtual MAC address. This is reactive
(triggered by `packet_in` via `_reply_vip_arp()`).

To ensure VIP ARP requests always reach the controller instead of being flooded
by the topology layer's ARP flood rule (priority 1), persistent punt rules are
installed at priority 100:

- `install_vip_arp_punt_rules()` — matches `eth_type=0x0806, arp_tpa=<VIP_IP>`,
  outputs to controller.
- `install_vip_punt_rules()` — matches `eth_type=0x0800, ipv4_dst=<VIP_IP>`,
  outputs to controller.

Both are reinstalled automatically via the `_on_datapath_connected` hook
whenever a switch reconnects and stale flows are flushed.

Only ICMP (1), TCP (6), and UDP (17) are handled as valid `ip_proto` match
values. Other protocols (ESP, GRE, etc.) are passed through to normal L2
processing.

---

## Backend Selection — WSM Cost Functions

### Server Selection (VIP_SERVER)

`select_server(client_mac)` picks the HTTP server with the lowest cost:

$$Cost_j = w_{cpu} \cdot \frac{CPU_j}{CPU_{max}} + w_{ram} \cdot \frac{RAM_j}{RAM_{max}} + w_{req} \cdot \frac{Req_j}{Req_{max}} + w_{hops} \cdot \frac{Hops_j}{Hops_{max}}$$

Default weights: `W_CPU=0.2`, `W_RAM=0.2`, `W_REQUESTS=0.2`, `W_HOPS=0.4`.

### Storage Selection (VIP_DATA)

`select_storage(domain, client_mac)` picks the storage node with the lowest cost
from the domain's pool (`vip_storage_pool_n1` or `vip_storage_pool_n2`):

$$Cost_j = w_{cpu} \cdot \frac{CPU_j}{CPU_{max}} + w_{ram} \cdot \frac{RAM_j}{RAM_{max}} + w_{conn} \cdot \frac{Conn_j}{Conn_{max}} + w_{lag} \cdot \frac{Lag_j}{Lag_{max}} + w_{hops} \cdot \frac{Hops_j}{Hops_{max}}$$

Default weights: `W_STORAGE_CPU=0.2`, `W_STORAGE_RAM=0.2`,
`W_STORAGE_CONNECTIONS=0.1`, `W_STORAGE_LAG=0.2`, `W_STORAGE_HOPS=0.3`.

### Cold-Start and Tie-Breaking

- **Unknown telemetry:** backends without stats are assigned worst-case
  normalized scores (1.0) across all resource dimensions, preventing
  unmeasured nodes from being accidentally preferred over measured ones.
- **Round-robin:** when multiple backends share the lowest cost (common during
  cold start when all values are 0.0), a round-robin counter distributes
  traffic evenly. Each domain's storage pool has its own counter.

### Hop Estimation

Hops for each backend are resolved in priority order:

| Condition                  | Hops assigned                              |
|----------------------------|--------------------------------------------|
| Path in `hop_cache`        | Real shortest-path length                  |
| Local, no path yet         | `max(_avg_hop_count, 1.0)`                 |
| Cross-network (peer)       | `max(_avg_hop_count, 1.0) + max(_peer_avg_hop_count, 1.0)` |
| Truly unknown MAC          | `hops_max` (worst case)                    |

The `_avg_hop_count` is computed by `TopologyMixin._rebuild_hop_cache()` and
published in `TopologySnapshot.avg_hop_count`. The peer's value is stored as
`_peer_avg_hop_count` on receipt. The `max(..., 1.0)` guard prevents cold-start
zero values from making cross-network backends appear free.

---

## DNAT / SNAT Rule Installation

Once a backend is selected, `_install_vip_dnat_snat()` installs a flow rule
pair and Packet-Outs the first packet:

| Rule | Priority | Match | Actions |
|------|----------|-------|---------|
| **DNAT** | 200 | `eth_src=client_mac, eth_dst=VIP_MAC, ipv4_src=client_ip, ipv4_dst=VIP_IP, ip_proto` | `set_field(eth_dst=backend_mac, ipv4_dst=backend_ip)`, output to backend port |
| **SNAT** | 200 | `eth_src=backend_mac, eth_dst=client_mac, ipv4_src=backend_ip, ipv4_dst=client_ip, ip_proto` | `set_field(eth_src=VIP_MAC, ipv4_src=VIP_IP)`, output to client port |

Both rules have configurable idle/hard timeouts (`VIP_IDLE_TIMEOUT=30s`,
`VIP_HARD_TIMEOUT=120s`). When the DNAT rule expires, the priority-100 punt
rule resumes and triggers fresh backend selection.

**Source port exclusion:** TCP/UDP source port is intentionally omitted from the
match. For VIP_DATA, one rule per `(web_server_ip, domain_VIP)` pair covers all
concurrent MongoDB connections from that server, preventing tier-transition read
inconsistency. For VIP_SERVER, it ensures per-client server affinity across
parallel HTTP sub-connections.

**Output port resolution:** `get_next_hop_port()` is preferred for multi-switch
topologies. Falls back to `host_attachment` for single-switch (backend directly
connected). For cross-network backends, falls back to `ROUTER_OVS_PORT`.

---

## Cross-Network Routing

When the selected backend resides on the peer LAN (MAC found in `peer_hosts`),
the packet must traverse the inter-LAN router:

### Forward Path (Client → VIP → Cross-Network Backend)

1. DNAT rule outputs to `ROUTER_OVS_PORT` (OVS port connected to the router).
2. `eth_dst` is set to `ROUTER_MAC` (the router's LAN-side interface MAC) — not
   the final backend MAC — so the router's kernel accepts the frame for L3
   forwarding.
3. Router forwards based on `ipv4_dst`, rewrites MACs (standard L3 hop-by-hop).
4. Packet arrives at the peer LAN's OVS as a normal L2 frame addressed to the
   backend — no second VIP interception occurs.

### Return Path (Backend → Client)

1. Backend responds normally; peer LAN forwards to router.
2. Router rewrites `eth_src` to its own LAN MAC.
3. SNAT rule on the originating controller matches `eth_src=ROUTER_MAC`
   (not the real backend MAC) and rewrites `eth_src→VIP_MAC`,
   `ipv4_src→VIP_IP`.
4. Client sees the response from the VIP address.

### Configuration

| Variable         | Purpose                                                  |
|------------------|----------------------------------------------------------|
| `ROUTER_OVS_PORT`| OVS port number connected to the inter-LAN router (0 = disabled) |
| `ROUTER_MAC`     | Router's LAN-side interface MAC (per controller)         |

Each controller receives its own `ROUTER_MAC` via `-e ROUTER_MAC=...` in the
`docker run` command in `build_network_setup.sh`.

---

## Telemetry Integration

Thread 2's `_on_telemetry_update()` callback (in `main_n*.py`) calls:

- `update_server_stats(servers)` — stores per-server `ServerSummary` (CPU, RAM,
  request count) keyed by MAC. Read by `select_server()`.
- `update_storage_stats(storage_servers)` — stores per-storage
  `StorageServerSummary` (CPU, RAM, connections, replication lag) keyed by MAC.
  Read by `select_storage()`.

Each container discovers its own MAC from `eth0` and includes it in telemetry
events. The aggregator forwards it as the dict key, establishing the link
between telemetry and VIP pool entries.

---

## Flow Priority Summary

| Priority | Rule                           | Trigger               |
|----------|--------------------------------|-----------------------|
| 100      | VIP ARP punt → controller      | Switch connect        |
| 100      | VIP IP punt → controller       | Switch connect        |
| 200      | DNAT/SNAT (per-client, timed)  | First VIP packet-in   |

Lower-priority rules (0–10) are installed by `TopologyMixin` — see the
[Topology Overview](../topology/topology_overview.md).

---

## Environment Variables

| Variable                    | Default | Purpose                                            |
|-----------------------------|---------|----------------------------------------------------|
| `W_CPU`                    | `0.2`   | Server WSM weight for CPU                          |
| `W_RAM`                    | `0.2`   | Server WSM weight for RAM                          |
| `W_REQUESTS`               | `0.2`   | Server WSM weight for request count                |
| `W_HOPS`                   | `0.4`   | Server WSM weight for hop distance                 |
| `W_STORAGE_CPU`            | `0.2`   | Storage WSM weight for CPU                         |
| `W_STORAGE_RAM`            | `0.2`   | Storage WSM weight for RAM                         |
| `W_STORAGE_CONNECTIONS`    | `0.1`   | Storage WSM weight for connection count            |
| `W_STORAGE_LAG`            | `0.2`   | Storage WSM weight for replication lag             |
| `W_STORAGE_HOPS`           | `0.3`   | Storage WSM weight for hop distance                |
| `VIP_IDLE_TIMEOUT`         | `30`    | DNAT/SNAT idle timeout (seconds)                   |
| `VIP_HARD_TIMEOUT`         | `120`   | DNAT/SNAT hard timeout (seconds)                   |
| `ROUTER_OVS_PORT`          | `0`     | OVS port to inter-LAN router (0 = disabled)       |
| `ROUTER_MAC`               | —       | Router LAN-side MAC for cross-network SNAT match   |

---

## Planned / Not Yet Implemented

- **Staleness cost function** — an additional WSM dimension penalizing backends
  whose telemetry has gone stale, so idle or unresponsive nodes are
  deprioritized instead of frozen at their last known cost.
