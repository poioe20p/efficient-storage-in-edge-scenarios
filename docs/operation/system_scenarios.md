# System Scenarios — Quick Reference

Condensed scenario descriptions to accompany the diagrams in `system_mechanisms.md`. Each entry states what is happening and which components are involved, without rationale or justification.

---

## Controller Thread Layout

Three concurrent execution contexts. The Telemetry Greenthread feeds Thread 1 in real-time and raises alerts to Thread 3 when thresholds are breached. Thread 3 mutates infrastructure and notifies Thread 1 of the change.

```mermaid
graph TD
    T1["Thread 1<br/>Real-Time Scheduler<br/>(Fast Path)"]
    T2["Telemetry Greenthread<br/>ZmqTelemetrySource<br/>(Observer)"]
    T3C["Thread 3: Compute Manager<br/>(T_proc threshold)"]
    T3D["Thread 3: Data Manager<br/>(T_dados threshold)"]

    T2 -->|"T_proc breached<br/>compute alert"| T3C
    T2 -->|"T_dados breached<br/>data alert"| T3D
    T3C -->|"updated server registry"| T1
    T3D -->|"updated VIP_DATA_N* DNAT"| T1
    T2 -->|"_server_stats / _storage_stats dicts<br/>(WSM input)"| T1
```

---

## Scenario 1 — New Client Request (VIP_SERVER + VIP_DATA_N*, First Packet)

A client opens a connection to `VIP_SERVER:80`. The OVS switch punts the SYN to Thread 1. Thread 1 selects the best web server using the WSM cost formula and installs DNAT/SNAT rules. The web server then opens a connection to `VIP_DATA_N1:27018`; Thread 1 intercepts that too, evaluates the storage WSM cost function for the corresponding domain, and installs DNAT/SNAT rules to the correct `mongod`. Both flows are then handled switch-only.

```mermaid
sequenceDiagram
    participant Client
    participant OVS as OVS Switch
    participant T1 as Controller Thread 1
    participant WebSrv as Selected Web Server
    participant VIPd as VIP_DATA_N1 (10.0.0.200)
    participant Mongo as Resolved mongod<br/>(secondary / primary)

    Client->>OVS: TCP SYN to VIP_SERVER:80
    OVS->>T1: Packet-In (VIP_SERVER punt rule)
    Note right of T1: Lookup server registry<br/>Apply WSM (CPU, RAM, Requests, Hops)<br/>→ Best = WebSrv_1
    T1->>OVS: FlowMod DNAT (VIP_SERVER → WebSrv_1)
    T1->>OVS: FlowMod SNAT (WebSrv_1 → VIP_SERVER)
    T1->>OVS: Packet-Out (first pkt)
    OVS->>WebSrv: Forwarded SYN
    WebSrv-->>OVS: SYN-ACK rewritten to VIP_SERVER
    OVS-->>Client: SYN-ACK from VIP_SERVER
    Note over Client,WebSrv: All further HTTP packets: switch-only

    WebSrv->>OVS: MongoDB query to VIP_DATA_N1:27018
    OVS->>T1: Packet-In (VIP_DATA_N1 punt rule)
    Note right of T1: Evaluate storage WSM<br/>(CPU, RAM, Connections, Lag, Hops)<br/>→ Best storage = mongod_1
    T1->>OVS: FlowMod DNAT (VIP_DATA_N1 → mongod_1_ip)
    T1->>OVS: FlowMod SNAT (mongod_1_ip → VIP_DATA_N1)
    T1->>OVS: Packet-Out (first pkt)
    OVS->>Mongo: MongoDB query to selected mongod
    Mongo-->>OVS: MongoDB response (src=mongod_1_ip)
    OVS-->>WebSrv: Response rewritten (src=VIP_DATA_N1)
    Note over WebSrv,Mongo: All further DB packets: switch-only
```

---

## Scenario 2 — Full Packet Lifecycle (ARP through HTTP Response)

Shows what happens from ARP resolution through a complete HTTP request/response cycle with both VIPs active.

```mermaid
sequenceDiagram
    participant Client as Client (10.0.0.2)
    participant OVS as OVS Bridge (ovs-br0)
    participant Ctrl as Controller (Thread 1)
    participant WS as Web Server (10.0.0.4)
    participant Backend as mongod backend (10.0.0.15)

    Note over Client,Backend: Phase 1 — ARP (proactive, no controller)
    Client->>OVS: ARP: Who has 10.0.0.100 (VIP_SERVER)?
    OVS-->>Client: ARP reply: 10.0.0.100 is-at VIP_SERVER_MAC
    WS->>OVS: ARP: Who has 10.0.0.200 (VIP_DATA_N1)?
    OVS-->>WS: ARP reply: 10.0.0.200 is-at VIP_DATA_N1_MAC

    Note over Client,Backend: Phase 2 — Client hits VIP_SERVER (controller selects web server)
    Client->>OVS: TCP SYN to 10.0.0.100:80
    OVS->>Ctrl: Packet-In (VIP_SERVER punt)
    Ctrl->>Ctrl: WSM(CPU, RAM, Requests, Hops) → WS selected
    Ctrl->>OVS: Install DNAT+SNAT (VIP_SERVER ↔ WS)
    Ctrl->>OVS: Packet-Out

    Note over Client,Backend: Phase 3 — Web server hits VIP_DATA_N1 (controller selects mongod)
    WS->>OVS: TCP SYN to 10.0.0.200:27018
    OVS->>Ctrl: Packet-In (VIP_DATA_N1 punt)
    Ctrl->>Ctrl: Storage WSM → best mongod backend
    Ctrl->>OVS: Install DNAT+SNAT (VIP_DATA_N1 ↔ Backend)
    Ctrl->>OVS: Packet-Out

    Note over Client,Backend: Phase 4 — Ongoing (switch-only, no controller)
    Client->>OVS: HTTP GET /data
    OVS->>WS: Forwarded (DNAT applied)
    WS->>OVS: MongoDB query to VIP_DATA_N1
    OVS->>Backend: Forwarded (DNAT applied)
    Backend-->>OVS: Response (src=backend)
    OVS-->>WS: Response rewritten (src=VIP_DATA_N1)
    WS-->>OVS: HTTP 200 OK (src=WS)
    OVS-->>Client: HTTP 200 OK (src rewritten to VIP_SERVER)
```

---

## Scenario 3 — Telemetry Greenthread Observes a Threshold Breach

Edge servers push per-request metrics via ZMQ PUSH to the per-network Aggregator. The Aggregator publishes windowed summaries via ZMQ PUB. The Telemetry Greenthread (ZmqTelemetrySource) subscribes, updates in-memory state for Thread 1's WSM cost functions, computes $T_{proc}$ from each summary, and fires the appropriate alert to Thread 3 (ElasticityManager).

```mermaid
sequenceDiagram
    participant Servers as Edge Server Containers
    participant Agg as Aggregator (ZMQ PULL→PUB)
    participant T2 as Telemetry Greenthread<br/>(ZmqTelemetrySource)
    participant Memory as In-Memory State
    participant TComp as Thread 3: Compute Manager
    participant TData as Thread 3: Data Manager

    Servers->>Agg: ZMQ PUSH per-request metric<br/>{T_total_ms, T_dados_ms, cpu, ram}
    Note over Agg: Window aggregation (10 s)
    Agg-->>T2: ZMQ PUB: TelemetrySummary
    T2->>Memory: update_server_stats → _server_stats[mac]<br/>update_storage_stats → _storage_stats[mac]
    T2->>T2: Compute T_proc = T_total - T_dados
    Note over T2,Memory: Thread 1 reads _server_stats<br/>and _storage_stats for WSM cost functions
    T2->>T2: Evaluate compute threshold:<br/>T_proc > τ_proc?
    opt Compute threshold breached
        T2->>TComp: submit_alert(ComputeAlert)
    end
    T2->>T2: Evaluate data threshold:<br/>T_dados > τ_dados?
    opt Data threshold breached
        T2->>TData: submit_alert(DataAlert)
    end
```

---

## Scenario 4 — Data Gravity Lifecycle (Tier 0 → 1 → 2 → 0)

Each network starts with only its own primary. As cross-network demand grows, Thread 3 deploys a cache, then a full secondary. When demand drops, resources are removed.

> **Note:** Tier 1 (Selective Sync Node) is implemented and feature-flagged behind `SS_ENABLED` (default `0`). With the flag off, only the Tier 0 → Tier 2 → Tier 0 lifecycle is exercised.

**Tier 0 — Base State:** Two isolated primaries, no replication, no caching.

```mermaid
graph LR
    subgraph Network A
        RS1_P["rs_net1<br/>PRIMARY<br/>(Net A data)"]
    end
    subgraph Network B
        RS2_P["rs_net2<br/>PRIMARY<br/>(Net B data)"]
    end

    RS1_P -.-|"no link"| RS2_P

    style RS1_P fill:#4a9,stroke:#333,color:#fff
    style RS2_P fill:#4a9,stroke:#333,color:#fff
```

**Tier 1 — Selective Sync Node deployed in Net B:** `VIP_DATA_N*` now routes to the Selective Sync Node. Hot collections are seeded via `mongodump | mongorestore` and kept current by one Change Stream per hot collection opened on the remote primary. A TTL index expires documents automatically.

```mermaid
graph LR
    subgraph Network A
        RS1_P2["rs_net1<br/>PRIMARY<br/>(Net A data)"]
    end
    subgraph Network B
        RS1_C["Selective Sync Node<br/>(standalone mongod + TTL)"]
        RS2_P2["rs_net2<br/>PRIMARY<br/>(Net B data)"]
    end

    RS1_P2 -.->|"Change Stream per hot collection"| RS1_C

    style RS1_P2 fill:#4a9,stroke:#333,color:#fff
    style RS1_C fill:#f9f,stroke:#333,color:#000
    style RS2_P2 fill:#4a9,stroke:#333,color:#fff
```

**Tier 2 — Full Replica added in Net B:** `rs.add()` places a secondary of `rs_net1` in Net B. MongoDB oplog replication runs autonomously. `VIP_DATA_N*` routes to the secondary.

```mermaid
graph LR
    subgraph Network A
        RS1_P3["rs_net1<br/>PRIMARY<br/>(Net A data)"]
    end
    subgraph Network B
        RS1_S["rs_net1<br/>SECONDARY<br/>(Net A data replica)"]
        RS2_P3["rs_net2<br/>PRIMARY<br/>(Net B data)"]
    end

    RS1_P3 -->|"oplog replication (mongodb autonmous mechanism)"| RS1_S

    style RS1_P3 fill:#4a9,stroke:#333,color:#fff
    style RS1_S fill:#f96,stroke:#333,color:#fff
    style RS2_P3 fill:#4a9,stroke:#333,color:#fff
```

**Tier 0 again — Demand dropped:** `rs.remove()` is called. `VIP_DATA_N*` DNAT reverts to the remote primary. Edge storage freed.

```mermaid
graph LR
    subgraph Network A
        RS1_P4["rs_net1<br/>PRIMARY<br/>(Net A data)"]
    end
    subgraph Network B
        RS1_S4["rs_net1<br/>REPLICA / SELECTIVE SYNC NODE<br/>(removed)"]
        RS2_P4["rs_net2<br/>PRIMARY<br/>(Net B data)"]
    end

    RS1_P4 -.-|"traffic stopped"| RS1_S4

    style RS1_P4 fill:#4a9,stroke:#333,color:#fff
    style RS1_S4 fill:#999,stroke:#666,color:#fff,stroke-dasharray: 5 5
    style RS2_P4 fill:#4a9,stroke:#333,color:#fff
```

---

## Scenario 5 — Tier Transition Map

> **Note:** Tier 1 transitions require `SS_ENABLED=1`; with the default flag off, only Tier 0 ↔ Tier 2 transitions occur.

Which metric triggers which transition, and what Thread 1 does to `VIP_DATA_N*` on each.

```mermaid
graph LR
    T0["Tier 0<br/>Direct Routing<br/>(VIP_DATA_N* → remote primary)"] -->|"T_dados ≥ τ_dados"| T1["Tier 1<br/>Selective Sync Node<br/>(VIP_DATA_N* → Selective Sync Node)"]
    T1 -->|"cache hit < 20%<br/>OR T_dados drops"| T0
    T1 -->|"unique data %<br/>> 50% of remote DB"| T2["Tier 2<br/>Full Replica<br/>(VIP_DATA_N* → local secondary)"]
    T2 -->|"T_dados drops<br/>below threshold"| T0

    style T0 fill:#69b,stroke:#333,color:#fff
    style T1 fill:#f9f,stroke:#333,color:#000
    style T2 fill:#f96,stroke:#333,color:#fff
```

---

## Scenario 6 — Scale-Out: Adding a Replica Secondary (Tier 2)

Thread 3 (ElasticityManager, Data Manager alert) runs `docker run` for a new `mongod`, attaches it to the OVS switch via `add_network_storage_node.sh`, calls `rs.add()` on the primary, waits for initial sync, and notifies Thread 1 to update the `VIP_DATA_N*` DNAT rule.

```mermaid
sequenceDiagram
    participant T3 as Thread 3 (ElasticityManager)
    participant Docker as Docker Engine
    participant OVS as OVS Switch (Net B)
    participant NewMongo as New MongoDB Secondary
    participant Primary as rs_net1 Primary (Net A)
    participant T1 as Controller Thread 1

    Note over T3: T_dados > τ_dados (sustained)<br/>Promote to Tier 2

    T3->>Docker: 1. docker run mongod<br/>(--replSet rs_net1, Net B subnet)
    Docker-->>NewMongo: Container starts
    T3->>OVS: 2. ovs-vsctl add-port<br/>(attach veth to switch)
    T3->>Primary: 3. rs.add("new_member_ip:27018")
    NewMongo->>Primary: 4. Initial sync<br/>(oplog tailing begins)
    Primary-->>NewMongo: Data replication stream
    Note over NewMongo: MongoDB auto-syncs from<br/>primary. No manual data copy.
    T3->>T1: 5. Update storage pool: Tier 2 active<br/>VIP_DATA_N* for Net B → secondary_ip
    Note over T1: Next VIP_DATA_N* Packet-In from Net B:<br/>DNAT → secondary_ip (local, low T_dados)
```

---

## Scenario 7 — Scale-Out: Spawning a New Web Server (Compute)

Thread 3 (ElasticityManager) runs a new web server container with the two VIP connection strings pre-configured, attaches it to the switch, and registers it with Thread 1 for `VIP_SERVER` routing.

```mermaid
sequenceDiagram
    participant T3 as Thread 3 (ElasticityManager)
    participant Docker as Docker Engine
    participant OVS as OVS Switch
    participant Server as New Web Server Container
    participant T1 as Controller Thread 1

    Note over T3: T_proc > τ_proc:<br/>Compute Manager spawns new web server

    T3->>Docker: 1. docker run web-server<br/>(env: DB_CONNECTION=VIP_DATA_N1,<br/>       DB_CONNECTION_WRITE=VIP_DATA_N1)
    Docker-->>Server: Container starts<br/>(connects to VIP_DATA_N1 for all reads)
    T3->>OVS: 2. ovs-vsctl add-port<br/>(attach veth to switch)
    T3->>OVS: 3. ip addr add<br/>(assign IP in target subnet)
    Note over Server: App reads env vars on boot:<br/>DB_CONNECTION = VIP_DATA_N1:27018<br/>DB_CONNECTION_WRITE = VIP_DATA_N1:27018<br/>SDN decides which mongod responds<br/>(writes always routed to local primary)
    T3->>T1: 4. Register new server in<br/>server registry (VIP pool)
    Note over T1: New web server available<br/>for VIP_SERVER routing (WSM scoring)
```

---

## Scenario 8 — Selective Sync Node Layout

> **Note:** Tier 1 is feature-flagged behind `SS_ENABLED`. See `system_mechanisms.md` §1.6 and [`selective_sync/selective_sync_overview.md`](selective_sync/selective_sync_overview.md) for the implementation.

A standalone `mongod` (not a replica set member) is deployed as the Selective Sync Node. Hot collections are identified by an access tracking script that tails `system.profile` on Local MongoDB, seeded via `mongodump | mongorestore`, and kept current by one Change Stream per hot collection opened on the remote primary. A Change Stream consumer script writes incoming documents with a `ttl_expires` field; MongoDB's TTL index handles expiry. The OVS switch applies the `VIP_DATA_N*` DNAT rule to route queries to the node.

```mermaid
graph LR
    subgraph Network A
        PrimaryA["rs_net1 Primary<br/>(Source of Truth)"]
    end

    subgraph Network B
        ClientB[User Client]
        AppB["Web Server Container<br/>(queries VIP_DATA_N* only)"]
        OVS["OVS Switch<br/>(DNAT: VIP_DATA_N* → Selective Sync Node)"]
        CacheB["Selective Sync Node<br/>(standalone mongod)<br/>Change Stream consumer + TTL"]
    end

    PrimaryA -.->|"Change Stream per hot collection<br/>(consumer writes with ttl_expires)"| CacheB
    ClientB -->|"HTTP to VIP_SERVER"| AppB
    AppB -->|"query to VIP_DATA_N*:27018"| OVS
    OVS -->|"DNAT → Selective Sync Node (Tier 1)"| CacheB

    style CacheB fill:#f9f,stroke:#333,stroke-width:2px
    style PrimaryA fill:#4a9,stroke:#333
    style OVS fill:#aaf,stroke:#333
```

---

## Scenario 9 — Selective Sync Node Deployment Sequence

> **Note:** Tier 1 is feature-flagged behind `SS_ENABLED`. See `system_mechanisms.md` §1.6 and [`selective_sync/selective_sync_overview.md`](selective_sync/selective_sync_overview.md) for the implementation.

Thread 3 (Data Manager) deploys the Selective Sync Node: identifies hot collections via an access tracking script that tails `system.profile` on Local MongoDB, seeds them from the remote primary using `mongodump | mongorestore`, opens one Change Stream per hot collection via the Change Stream consumer, attaches the node to the network, and signals Thread 1 to switch the `VIP_DATA_N*` DNAT rule.

```mermaid
sequenceDiagram
    participant T3 as Controller Thread 3<br/>(Data Manager)
    participant Docker as Docker Engine
    participant OVS as OVS Switch (Net B)
    participant AccessTrack as Access Tracking Script
    participant SyncNode as Selective Sync Node<br/>(standalone mongod)
    participant Consumer as Change Stream Consumer
    participant Primary as rs_net1 Primary (Net A)
    participant T1 as Controller Thread 1
    participant Memory as In-Memory State

    Note over T3: T_dados > τ_dados:<br/>VIP_DATA_N* routing to remote primary

    T3->>AccessTrack: 1. Tail system.profile on Local MongoDB<br/>to identify hot collections
    AccessTrack-->>T3: Hot collection list
    T3->>Docker: 2. docker run selective-sync-node<br/>(standalone mongod, TTL indexes)
    Docker-->>SyncNode: Container starts
    T3->>Primary: 3. mongodump hot collections | mongorestore<br/>→ SyncNode (initial seed)
    Primary-->>SyncNode: Hot collection documents
    T3->>Consumer: 4. Open one Change Stream per hot collection<br/>(writes docs with ttl_expires field)
    Consumer->>Primary: Watch change stream
    Primary-->>Consumer: Incremental changes
    Consumer->>SyncNode: Write incoming docs (with ttl_expires)
    T3->>OVS: 5. ovs-vsctl add-port<br/>(attach veth to switch)
    T3->>OVS: 6. ip addr add<br/>(assign IP in Net B subnet)
    T3->>Memory: 7. Update MDVBP map:<br/>Tier 1 active in Net B — sync_node_ip assigned
    T3->>T1: 8. Signal: update VIP_DATA_N* DNAT for Net B
    Note over T1: Next Packet-In for VIP_DATA_N*<br/>from Net B web server:<br/>DNAT → sync_node_ip (instead of remote primary)
    Note over Consumer,Primary: Change Streams continue streaming.<br/>TTL index expires documents automatically.
```

---

## Scenario 10 — Server: Read Request Flow

The web server receives an HTTP GET, queries `VIP_DATA_N*:27018` (unaware of which `mongod` actually answers), measures $T_{dados}$, and returns the response. The OVS switch applies the active DNAT rule transparently.

```mermaid
sequenceDiagram
    participant Client
    participant Server as Web Server Container
    participant VIPd as VIP_DATA_N*:27018
    participant OVS as OVS Switch
    participant Mongo as mongod (resolved by SDN)<br/>(Tier 0=remote primary / Tier 2=secondary)

    Client->>Server: HTTP GET /data
    Server->>Server: Process request, build query
    Server->>VIPd: db.collection.find(query)<br/>(single conn string: VIP_DATA_N*)
    VIPd->>OVS: Packet hits VIP_DATA_N* DNAT rule
    OVS->>Mongo: Forwarded to current tier endpoint<br/>(Tier 0=remote primary / Tier 2=secondary)
    Mongo-->>OVS: Query result
    OVS-->>Server: Result rewritten (src=VIP_DATA_N*)
    Server-->>Client: HTTP 200 OK (JSON or HTML)
    Note over Server: Server measures T_dados = time<br/>VIP_DATA_N* took to respond<br/>T_proc = T_total - T_dados
```

---

## Scenario 11 — Server: Write Request Flow

The web server sends a write to the local primary. The SDN routes writes directly to the local primary via static DNAT rules (write-path isolation). The primary acknowledges the write.

```mermaid
sequenceDiagram
    participant Client
    participant Server as Web Server Container
    participant VIPdw as Local Primary:27018
    participant Primary as rs_netX Primary<br/>(always local to data origin)

    Client->>Server: HTTP POST /data
    Server->>VIPdw: db.collection.insertOne(doc)<br/>(write path — always routes to primary)
    Note over VIPdw,Primary: SDN routes writes directly<br/>to local primary (write-path isolation)
    Primary-->>Server: Write acknowledged
    Server-->>Client: HTTP 201 Created
```

---

## Scenario 12 — Server: Metric Reporting (ZMQ PUSH)

After each HTTP request, the web server pushes a per-request metric event via ZMQ PUSH to the per-network Aggregator. There is no database in the telemetry path.

```mermaid
sequenceDiagram
    participant Server as Server Container
    participant Agg as Aggregator<br/>(ZMQ PULL :5555)
    participant T2 as Telemetry Greenthread<br/>(ZMQ SUB)

    Server->>Agg: ZMQ PUSH per-request metric<br/>{server_id, T_total_ms, T_dados_ms,<br/>cpu_percent, ram_used_mb}
    Note over Agg: Window aggregation (10 s)
    Agg-->>T2: ZMQ PUB: TelemetrySummary<br/>(windowed per-server averages)
    Note over T2: Updates _server_stats<br/>for Thread 1 WSM cost functions
```

---

## Scenario 13 — ZMQ Telemetry Pipeline Overview

All server containers push per-request metrics via ZMQ PUSH to the per-network Aggregator. MongoDB sidecars also push periodic snapshots. The Aggregator publishes windowed summaries via ZMQ PUB. The Telemetry Greenthread subscribes and updates in-memory state.

```mermaid
graph TD
    S1["Server 1"] -->|"ZMQ PUSH<br/>per-request metric"| Agg["Aggregator<br/>(ZMQ PULL :5555 / PUB :5556)"]
    S2["Server 2"] -->|"ZMQ PUSH"| Agg
    S3["Server N"] -->|"ZMQ PUSH"| Agg
    MS["mongod sidecar"] -->|"ZMQ PUSH<br/>mongo_stats"| Agg
    Agg -->|"ZMQ PUB<br/>TelemetrySummary"| T2["Telemetry Greenthread<br/>(ZmqTelemetrySource)"]
```

---

## Scenario 14 — Telemetry: Threshold Breach Detected

A server reports high $T_{dados}$. The Aggregator publishes the windowed summary. The Telemetry Greenthread receives it, computes $T_{proc}$, finds $T_{dados}$ above threshold, and submits a DataAlert to the ElasticityManager queue.

```mermaid
sequenceDiagram
    participant Server as Server Container
    participant Agg as Aggregator (ZMQ PULL→PUB)
    participant T2 as Telemetry Greenthread<br/>(ZmqTelemetrySource)
    participant Memory as In-Memory State

    Server->>Agg: ZMQ PUSH {T_total_ms: 95, T_dados_ms: 82, ...}
    Note over Agg: Window aggregation
    Agg-->>T2: ZMQ PUB: TelemetrySummary<br/>{server_id: "srv_1", avg_time_total_ms: 95, avg_time_db_ms: 82}
    T2->>Memory: update_server_stats(srv_1)
    T2->>T2: Compute T_proc = 95 - 82 = 13 ms
    T2->>T2: Check compute threshold: T_proc=13 < τ_proc → OK
    T2->>T2: Check data threshold: T_dados=82 > τ_dados → BREACH
    T2->>T2: submit_alert(DataAlert) → ElasticityManager queue
```

---

## Scenario 15 — SSR: Edge-Based (Tier 2 active; Tier 1 feature-flagged)

A `GET /view/profile` request triggers two `VIP_DATA_N*` queries (template + data). Both are served locally because the SDN DNAT rule routes `VIP_DATA_N*` to a local cache or secondary. $T_{dados} \approx 2 \times \text{LAN latency}$.

```mermaid
sequenceDiagram
    participant User
    participant App as Web Server Container<br/>(Edge Node)
    participant VIPd as VIP_DATA_N*:27018
    participant LocalMongo as Local mongod<br/>(cache or secondary — resolved by SDN)

    User->>App: GET /view/profile

    rect rgb(240, 248, 255)
        Note right of App: SSR — 2 VIP_DATA_N* queries<br/>(both served locally by SDN DNAT)
        App->>VIPd: 1. Find Template ("profile_layout")
        VIPd-->>App: <html><body><h1>{{name}}</h1>...
        App->>VIPd: 2. Find Data ({id: 123})
        VIPd-->>App: {name: "Alice", role: "Admin"}
    end

    Note over App: T_dados = time for both VIP_DATA_N* queries<br/>T_proc = merge template + serialise HTML
    App-->>User: HTTP 200 OK (Rendered HTML)
```

---

## Scenario 16 — SSR: No Local Data (Tier 0)

Same `GET /view/profile` request, but `VIP_DATA_N*` is routing to the remote primary. Both queries cross the network. $T_{dados} \approx 2 \times \text{Remote RTT}$.

```mermaid
sequenceDiagram
    participant User
    participant App as Web Server Container<br/>(Edge Node)
    participant VIPd as VIP_DATA_N*:27018
    participant RemoteMongo as Remote Primary<br/>(cross-network — resolved by SDN)

    User->>App: GET /view/profile

    rect rgb(255, 240, 240)
        Note right of App: SSR — No local data<br/>Both VIP_DATA_N* queries cross the network
        App->>VIPd: 1. Find Template ("profile_layout")
        VIPd-->>App: (after cross-network RTT)
        App->>VIPd: 2. Find Data ({id: 123})
        VIPd-->>App: (after cross-network RTT)
    end

    Note over App: T_dados ≈ 2 × Remote RTT<br/>Total: T_total = T_dados + T_proc
    App-->>User: HTTP 200 OK (Rendered HTML)
```

---

## Scenario 17 — End-to-End: Full Control Loop

The complete cycle from a server pushing a metric to the controller taking infrastructure action.

```mermaid
sequenceDiagram
    participant Server as Server Container
    participant Agg as Aggregator (ZMQ PULL→PUB)
    participant T2 as Telemetry Greenthread<br/>(ZmqTelemetrySource)
    participant T3comp as Thread 3: ElasticityManager<br/>(ComputeAlert)
    participant T3data as Thread 3: ElasticityManager<br/>(DataAlert)
    participant T1 as Controller Thread 1
    participant Docker as Docker Engine
    participant OVS as OVS Switch

    Server->>Agg: ZMQ PUSH per-request metric<br/>{T_total_ms, T_dados_ms, cpu, ram}
    Note over Agg: Window aggregation (10 s)
    Agg-->>T2: ZMQ PUB: TelemetrySummary
    T2->>T2: Update _server_stats / _storage_stats
    T2->>T2: Compute T_proc = T_total - T_dados

    Note over T2,T1: Normal: Thread 1 uses _server_stats<br/>for WSM cost function (VIP_SERVER routing)

    alt T_proc > τ_proc (compute bottleneck)
        T2->>T3comp: submit_alert(ComputeAlert)
        T3comp->>Docker: Spawn new web server (NodeAdder)
        T3comp->>OVS: Attach to network (add_network_node.sh)
        T3comp->>T1: add_server_mac → update VIP pool
        Note over T1: New web server available<br/>for VIP_SERVER routing
    else T_dados > τ_dados (data bottleneck)
        T2->>T3data: submit_alert(DataAlert)
        T3data->>T3data: Evaluate tier transition
        T3data->>Docker: Spawn replica (NodeAdder)
        T3data->>OVS: Attach to network (add_network_storage_node.sh)
        T3data->>T1: add_storage_mac → update VIP_DATA_N* pool
        Note over T1: Next VIP_DATA_N* Packet-In<br/>routes to new local endpoint
    else idle (scale-in)
        T2->>T3comp: submit_alert(ScaleDownComputeAlert)
        T3comp->>Docker: Two-phase drain → remove container
        T3comp->>OVS: Flush flows, remove port
        T3comp->>T1: remove_server_mac → update VIP pool
    end
```
