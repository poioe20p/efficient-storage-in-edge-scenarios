# System Architecture Design: Workflow, Sequence and MongoDB Mechanisms

## 1. SDN Controller and OpenFlow Mechanisms

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
