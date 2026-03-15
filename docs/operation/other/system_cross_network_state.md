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

## 2. Node Self-Registration Across Networks

When Controller A provisions a new edge or storage node inside Network B, the node does not need to contact Controller A directly. Instead:

1. **The node's startup script** sends an initial packet (ARP, ping, or application-level hello) into the local OVS switch of Network B.
2. **Controller B** receives the `PacketIn`, learns the node's MAC and port, and updates its local topology.
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

### 4.1 Telemetry path — pub/sub

Aggregation scripts push windowed summaries **directly to the controller** via pub/sub. No shared database sits in the telemetry path.

```
         Network A                              Network B
┌──────────────────────────┐        ┌──────────────────────────┐
│ Edge/Storage Nodes       │        │ Edge/Storage Nodes       │
│   ↓ raw telemetry        │        │   ↓ raw telemetry        │
│ Local MongoDB A          │        │ Local MongoDB B          │
│   ↓ aggregation script   │        │   ↓ aggregation script   │
│   (5–10s window summary) │        │   (5–10s window summary) │
│   ↓ pub/sub push         │        │   ↓ pub/sub push         │
└──────────┬───────────────┘        └──────────┬───────────────┘
           ↓                                    ↓
    Controller A                        Controller B
    (reacts: provisions                  (reacts: provisions
     VIPs in its domain)                 VIPs in its domain)
```

Why pub/sub and not a shared database for telemetry:
- Telemetry summaries are **transient events**, not durable state. Pub/sub is the right tool.
- A shared database would be introduced solely as an event bus — adding infrastructure with no benefit over a purpose-built message transport.
- Controllers hold latest state in memory. Restart state loss is acceptable (topology is fixed; active VIPs are re-detected on the next demand event).
- Raw telemetry **never leaves the local domain**.

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
| **Local MongoDB (per network)** | Raw node metrics, per-node granularity | Edge/storage nodes directly | High (1–5 s per node) |
| **Aggregation Script (per network)** | Pushes windowed summaries to controllers via pub/sub | Background script alongside Local MongoDB | Medium (5–10 s windows) |
| **Shared MongoDB** | VIP registry, topology snapshots | Controllers only (on VIP/topology change) | Low (on-change) |

### Write/read summary

| Component | Writes to | Reads from |
|---|---|---|
| Edge/Storage Nodes | Local MongoDB (raw metrics) | — |
| Aggregation Script | — (pub/sub push to controller) | Local MongoDB |
| Controllers | Shared MongoDB (VIP registry, topology) | Shared MongoDB (VIP registry, topology) |
| Shared MongoDB | — | Source of truth for cross-domain coordination |

---

## 5. Controllers as Pure Event-Driven Consumers

Controllers **do not perform telemetry aggregation**. Aggregation is the responsibility of the per-network aggregation script, keeping the controller focused on control-plane decisions.

Controllers subscribe to the pub/sub channel for their network domain. The aggregation script publishes only when a windowed summary is ready (5–10 s cadence); the controller is idle between publications:

```python
# Pseudocode — controller pub/sub subscriber
for message in pubsub.subscribe(topic=f"telemetry.{domain}"):
    summary = parse(message)
    if summary.avg_T_proc > TAU_PROC:
        trigger_compute_provisioning(summary)
    if summary.avg_T_dados > TAU_DADOS:
        trigger_data_gravity_transition(summary)
```

This means:
- **Controllers are idle** when the system is healthy — no polling, no database cursor to maintain.
- **Provisioning is triggered** only when a published summary signals a threshold breach.
- The aggregation script and the controller are fully **decoupled** — either can restart independently.
