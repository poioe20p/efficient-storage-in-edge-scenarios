# System Architecture Design: Workflow, Sequence and MongoDB Mechanisms

## 1. Architecture Overview

The lab runs two isolated LAN segments inside Docker, each managed by an OpenFlow 1.3 SDN controller (OS-Ken). A sharded MongoDB cluster stores packet events and topology snapshots, while a NAT router interconnects the LANs and provides external connectivity. A Virtual IP (VIP) service allows clients to reach a server pool through a single address; the controller selects the best backend based on hop count and link debit.

```mermaid
graph TB
    subgraph Host["Host Machine (Ubuntu VM)"]
        direction TB
        Controller["OS-Ken SDN Controller<br/>(osken_learn_and_log)"]
        ConfigSvr["MongoDB Config Server<br/>(configReplSet, port 27019)"]
        Mongos["MongoDB Router (mongos)<br/>(port 27017)"]
    end

    subgraph LAN1["LAN 1 (10.0.0.0/24)"]
        OVS_BR0["OVS Bridge ovs-br0"]
        H1["container1<br/>10.0.0.2"]
        H2["container2<br/>10.0.0.3"]
        Mongo1["mongodb-n1 (rs_net1)<br/>10.0.0.4:27018"]
    end

    subgraph LAN2["LAN 2 (10.0.1.0/24)"]
        OVS_BR1["OVS Bridge ovs-br1"]
        H3["container3<br/>10.0.1.2"]
        H4["container4<br/>10.0.1.3"]
        Mongo2["mongodb-n2 (rs_net2)<br/>10.0.1.4:27018"]
    end

    Router["NAT Router<br/>eth1: 10.0.0.1<br/>eth2: 10.0.1.1<br/>eth0: 192.168.100.2"]

    Controller -- "OpenFlow 1.3" --> OVS_BR0
    Controller -- "OpenFlow 1.3" --> OVS_BR1
    Controller -- "read/write events" --> Mongos

    H1 -- "veth1" --> OVS_BR0
    H2 -- "veth2" --> OVS_BR0
    Mongo1 -- "veth5" --> OVS_BR0
    Router -- "eth1 (veth3)" --> OVS_BR0

    H3 -- "veth7" --> OVS_BR1
    H4 -- "veth8" --> OVS_BR1
    Mongo2 -- "veth11" --> OVS_BR1
    Router -- "eth2 (veth12)" --> OVS_BR1

    Mongos --> ConfigSvr
    Mongos -- "DNAT via router<br/>:27018" --> Mongo1
    Mongos -- "DNAT via router<br/>:27118" --> Mongo2
```

### Docker Containers

| Container | Image | Role |
|---|---|---|
| `ovs` | `ovs-container` | Open vSwitch with bridges `ovs-br0` and `ovs-br1` |
| `container1` – `container4` | `ubuntu-host` | User/client hosts on each LAN |
| `mongodb-n1` | `ubuntu-mongodb` | Shard replica set `rs_net1` (LAN 1) |
| `mongodb-n2` | `ubuntu-mongodb` | Shard replica set `rs_net2` (LAN 2) |
| `mongodb-config-server` | `ubuntu-mongodb` | Config server replica set `configReplSet` |
| `mongodb-router` | `ubuntu-mongodb` | `mongos` query router |
| `nat-router` | `ubuntu-nat-router` | Inter-LAN routing, DNAT/SNAT for shard exposure |
| `ryu` | OS-Ken image | SDN controller (runs on host network) |

---

## 2. MongoDB Mechanisms

```mermaid
graph LR
    Client["SDN Controller<br/>(pymongo)"] --> Mongos["mongos<br/>(Query Router)"]
    Mongos --> CS["Config Server RS<br/>(configReplSet)"]
    Mongos --> S1["Shard rs_net1<br/>(10.0.0.4:27018)"]
    Mongos --> S2["Shard rs_net2<br/>(10.0.1.4:27018)"]
    CS -. "chunk ranges<br/>& metadata" .-> Mongos
```

| Mechanism | Purpose in This System |
|---|---|
| **Sharding** | The `events` collection is sharded by `dpid` (datapath ID). Each switch's events land on the shard in the same LAN segment, keeping writes local. |
| **Shard Key (`dpid`)** | Integer datapath IDs are split into zone ranges (`_zone_size` chunks). `dpid` values are mapped to `rs_net1` or `rs_net2` so `mongos` routes writes to the correct shard without scatter-gather. |
| **Replica Sets** | Each shard (`rs_net1`, `rs_net2`) and the config server (`configReplSet`) run as single-node replica sets. This enables `replSetInitiate`, oplog replication, and automatic primary election. |
| **Config Server** | Stores chunk-to-shard mappings, database metadata, and zone definitions. `mongos` caches this metadata to route queries. |
| **mongos (Query Router)** | Single entry point for the controller. Routes reads/writes to the correct shard based on the shard key. The controller connects only to `mongos`, never directly to shards. |
| **Zone Sharding** | `dpid` ranges are assigned to zones (`rs_net1`, `rs_net2`) via `sh.updateZoneKeyRange()`. This guarantees data locality: LAN 1 switch events stay on `rs_net1`. |
| **Replace-by-ID** | `EventRepository` replaces documents by `_id == dpid` to keep shard keys stable and avoid unbounded collection growth. |

---

## 3. SDN Controller and OpenFlow Mechanisms

| Component | Mechanism | Description |
|---|---|---|
| **OS-Ken Controller** | `KenLearnAndLog` | Base learning-switch app. Learns MAC→port mappings reactively and logs packet events to MongoDB via `mongos`. |
| **OpenFlow 1.3 Table-Miss** | Priority 0, action `OUTPUT:CONTROLLER` | Installed on switch connect. Sends all unmatched packets to the controller for MAC learning. |
| **Reactive L2 Learning** | Priority 10, match `(in_port, eth_src, eth_dst)` | Once a MAC is learned, a flow rule is installed so subsequent frames are forwarded in hardware without controller involvement. |
| **Proactive Topology Flows** | `topology_n1.py` / `topology_n2.py` | Compute shortest paths via NetworkX on the local LAN topology and install host-to-host forwarding rules proactively. |
| **Port Stats Polling** | `OFPPortStatsRequest` / `OFPPortStatsReply` | Periodic polling computes per-port bitrate (rx/tx bps). Server-facing port debit is persisted to MongoDB (`debits` collection) via `DebitRepository`. |
| **VIP Punt Rule** | Priority 100, match `ipv4_dst=VIP, ICMP/TCP/UDP` | Ensures the first packet to the VIP address reaches the controller for backend selection. |
| **DNAT/SNAT Flows** | Priority 200, installed on client edge switch | After backend selection, the controller rewrites destination (DNAT) and source (SNAT) IP/MAC so the client sees only the VIP while traffic reaches the real server. |
| **ARP Reply Rule** | Priority 200, proactive (via `ovs-ofctl`) | The switch replies to ARP requests for the VIP directly, advertising `VIP_MAC`. No controller involvement needed for ARP. |

---

## 4. Scenario: Client HTTP Request to VIP Server Pool

A client host sends a request (e.g., TCP connection) to the **Virtual IP (VIP)** `10.0.0.100`. The SDN controller selects the best MongoDB backend server based on **hop count** and **server link debit**, installs NAT rewrite rules, and the client communicates transparently with the chosen backend.

```mermaid
sequenceDiagram
    participant Client as Client Host<br/>(container1, 10.0.0.2)
    participant OVS as OVS Bridge<br/>(ovs-br0)
    participant Ctrl as OS-Ken Controller<br/>(KenLearnAndLog)
    participant Mongo as MongoDB Debit<br/>(mongos → debits)
    participant Backend as Selected Backend<br/>(e.g. mongodb-n1, 10.0.0.4)

    Note over Client,Backend: Phase 1 — ARP Resolution (handled in-switch)
    Client->>OVS: ARP request: Who has 10.0.0.100?
    OVS-->>Client: ARP reply: 10.0.0.100 is-at aa:bb:cc:dd:ee:ff<br/>(proactive OVS flow, priority 200)

    Note over Client,Backend: Phase 2 — First Packet (controller selects backend)
    Client->>OVS: TCP SYN to 10.0.0.100 (VIP)<br/>dst_mac=aa:bb:cc:dd:ee:ff
    OVS->>Ctrl: PacketIn (VIP punt rule, priority 100)

    Ctrl->>Ctrl: Parse packet: client_mac, client_ip,<br/>ip_proto, src_port, dst_port
    Ctrl->>Mongo: Read latest debit snapshot<br/>(DebitRepository.get_debit_by_lan_id)
    Mongo-->>Ctrl: Server debit bps per server MAC
    Ctrl->>Ctrl: Compute hop count from topology graph<br/>(NetworkX shortest path)
    Ctrl->>Ctrl: Score = 0.3 × (hops/max_hops)<br/>+ 0.7 × min(1, debit/norm_bps)<br/>Select server with lowest score

    Ctrl->>OVS: Install DNAT flow (priority 200):<br/>match(VIP dst) → set_field(backend IP/MAC),<br/>output(next_hop_port)
    Ctrl->>OVS: Install SNAT flow (priority 200):<br/>match(backend src) → set_field(VIP IP/MAC),<br/>output(client_port)
    Ctrl->>OVS: PacketOut first packet with DNAT actions

    Note over Client,Backend: Phase 3 — Ongoing Traffic (switch-only, no controller)
    OVS->>Backend: Forwarded packet:<br/>dst rewritten to 10.0.0.4
    Backend-->>OVS: Response packet:<br/>src=10.0.0.4
    OVS-->>Client: Response with SNAT:<br/>src rewritten to 10.0.0.100 (VIP)
    Client->>OVS: Subsequent packets match DNAT flow
    OVS->>Backend: Forwarded directly (no controller)
```

### What Happens at Each Step

1. **ARP Resolution** — The client ARPs for the VIP (`10.0.0.100`). A proactive OpenFlow rule (installed via `ovs-ofctl` in the setup scripts) makes the switch reply with `VIP_MAC = aa:bb:cc:dd:ee:ff`. The controller is not involved.

2. **First Packet → Controller** — The client sends the first TCP SYN (or ICMP echo) to the VIP. The VIP punt flow (priority 100) sends this packet to the controller as a `PacketIn` event.

3. **Backend Selection** — The controller:
   - Reads the cached **server link debit** (bps) from MongoDB (`debits` collection via `DebitRepository`).
   - Looks up the **hop count** from the client to each server using the NetworkX topology graph.
   - Computes a weighted score: `score = 0.3 × (hops / max_hops) + 0.7 × min(1, debit_bps / norm_bps)`.
   - Selects the server with the **lowest score** (closest and least loaded).

4. **DNAT/SNAT Flow Installation** — The controller installs two OpenFlow rules on the **client's edge switch** (priority 200):
   - **DNAT** (forward path): rewrites `dst_ip` from VIP → backend IP, `dst_mac` from VIP MAC → backend MAC, and outputs to the next-hop port.
   - **SNAT** (return path): rewrites `src_ip` from backend IP → VIP, `src_mac` from backend MAC → VIP MAC, and outputs to the client port.
   - Both rules have an `idle_timeout` so stale mappings expire and new flows can be re-evaluated.

5. **Ongoing Traffic** — All subsequent packets in both directions are handled entirely by the switch using the installed DNAT/SNAT rules. The controller is not involved, and the client always sees traffic coming from the VIP address.

### Components Used in This Scenario

| Layer | Component | Role |
|---|---|---|
| **Docker** | `container1` (client), `ovs` (switch), `mongodb-n1` or `mongodb-n2` (backend) | Client host, OpenFlow switch, database server |
| **OpenFlow** | ARP reply flow (P200), VIP punt flow (P100), DNAT/SNAT flows (P200) | ARP handling, first-packet redirect, packet rewriting |
| **Controller** | `KenLearnAndLog` + `topology_n1.py` | Backend selection logic, flow installation, topology graph |
| **MongoDB** | `debits` collection (via `mongos`), `DebitRepository` | Server load data for cost-based selection |
| **MongoDB Sharding** | `mongos` routes debit reads to the correct shard by `lan_id` | Data locality for telemetry |
