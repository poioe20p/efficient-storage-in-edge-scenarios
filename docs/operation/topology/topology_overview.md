# Topology — Overview

## Purpose

The topology subsystem is the foundation of the SDN controller. It discovers the
local OpenFlow network (switches, hosts, links), computes shortest-path hop
counts, maintains VIP backend pools, and shares its view with the peer
controller over ZMQ. The topology layer feeds its data (hop cache, VIP pools,
host attachment map) into the VIP routing mixin, and exposes the `storage_roles`
contract used by the selective sync subsystem.

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

## Document Map

| Document | Contents |
|---|---|
| [Local Discovery and Proactive Flows](topology_local_discovery_and_flows.md) | OS-Ken dependency, discovery poll loop, router filtering (built-in blocklist), host attachment, hop cache, switch reconnect handling, proactive flow installation (local hosts only), reactive learning boundary |
| [Backend Roles and VIP Pools](topology_backend_roles_and_vip_pools.md) | VIP address set (including recovery VIPs), MAC role sets, dynamic registration, VIP pool rebuild rules, storage role tracking, peer primary resolution contract (`27018`) |
| [Peer Exchange and Models](topology_peer_exchange_and_models.md) | Topology models (`type`, `ts`, `storage_roles`), snapshot shape, publish triggers, receive path, peer MAC/role replacement, host IP seeding, backward-compatibility fields |

---

## Related Subsystems

- **VIP Routing** — consumes the hop cache, VIP pools, and host attachment map
  from topology to compute WSM costs. See the
  [VIP Routing Overview](../vip_routing/vip_routing_overview.md).
- **Selective Sync (Tier 1)** — consumes the `storage_roles` contract (via
  `resolve_peer_primary()`) from topology to discover the peer RS primary
  endpoint. See the
  [Selective Sync Overview](../selective_sync/selective_sync_overview.md).

---

## WAN Emulation

Inter-LAN latency is shaped via `tc netem` on the nat-router's inter-LAN
interfaces (`eth1`/`eth2`). Configuration lives in
[`source/scripts/wan.env`](../../../source/scripts/wan.env) and is applied by
[`source/scripts/network/inject_wan_latency.sh`](../../../source/scripts/network/inject_wan_latency.sh).
The Internet uplink (`eth3`) is left unshaped. Runtime re-tuning uses
[`source/scripts/tools/wan_set.sh`](../../../source/scripts/tools/wan_set.sh).

Profiles (`WAN_RTT_MS`): `lab` (0), `metro` (10, default), `regional` (40),
`inter-continental` (150).

---

## Environment Variables

| Variable | Default | Purpose |
|---|---|---|
| `LAN_ID` | `lan1` | Network identity for published topology snapshots |
| `TOPOLOGY_INTERVAL` | `1` | Seconds between topology worker polls |
| `TOPOLOGY_HEARTBEAT_TICKS` | `30` | Publish a heartbeat every N ticks with no change |
| `TOPOLOGY_PUB_PORT` | `5557` | ZMQ PUB bind port for outgoing topology snapshots |
| `PEER_TOPOLOGY_ENDPOINTS` | *(empty)* | Comma-separated peer controller PUB addresses |
| `SERVER_MACS` | *(empty)* | Comma-separated initial HTTP server MACs |
| `STORAGE_MACS_N1` | *(empty)* | Comma-separated initial LAN 1 storage MACs |
| `STORAGE_MACS_N2` | *(empty)* | Comma-separated initial LAN 2 storage MACs |
| `VIP_SERVER_IP` | `10.0.0.253` | Virtual IP for HTTP edge servers |
| `VIP_SERVER_MAC` | `aa:bb:cc:dd:ee:01` | Virtual MAC for VIP_SERVER |
| `VIP_DATA_N1_IP` | `10.0.0.254` | Virtual IP for LAN 1 MongoDB storage |
| `VIP_DATA_N1_MAC` | `aa:bb:cc:dd:ee:02` | Virtual MAC for VIP_DATA_N1 |
| `VIP_DATA_N2_IP` | `10.0.1.254` | Virtual IP for LAN 2 MongoDB storage |
| `VIP_DATA_N2_MAC` | `aa:bb:cc:dd:ee:03` | Virtual MAC for VIP_DATA_N2 |
| `VIP_DATA_RECOVERY_N1_IP` | `10.0.0.252` | Virtual IP for LAN 1 recovery MongoDB storage |
| `VIP_DATA_RECOVERY_N1_MAC` | `aa:bb:cc:dd:ee:12` | Virtual MAC for VIP_DATA_RECOVERY_N1 |
| `VIP_DATA_RECOVERY_N2_IP` | `10.0.1.252` | Virtual IP for LAN 2 recovery MongoDB storage |
| `VIP_DATA_RECOVERY_N2_MAC` | `aa:bb:cc:dd:ee:13` | Virtual MAC for VIP_DATA_RECOVERY_N2 |
| `WAN_RTT_MS` | `10` | Inter-LAN round-trip delay (split into two one-way halves) |
| `WAN_JITTER_MS` | `0` | netem jitter added to each one-way delay |
| `WAN_LOSS_PCT` | `0` | netem packet loss percentage on inter-LAN links |
| `WAN_RATE_KBIT` | `0` | netem rate cap on inter-LAN links (`0` = uncapped) |


