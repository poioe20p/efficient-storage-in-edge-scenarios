# System Scenarios — Quick Reference

Condensed scenario descriptions to accompany the diagrams in `system_mechanisms.md`. Each entry states what is happening and which components are involved, without rationale or justification.

---

## Controller Thread Layout

Three concurrent threads. Thread 2 feeds Thread 1 in real-time and raises alerts to Thread 3 when thresholds are breached. Thread 3 mutates infrastructure and notifies Thread 1 of the change.

```mermaid
graph TD
    T1["Thread 1<br/>Real-Time Scheduler<br/>(Fast Path)"]
    T2["Thread 2<br/>Telemetry Monitor<br/>(Observer)"]
    T3C["Thread 3: Compute Manager<br/>(T_proc threshold)"]
    T3D["Thread 3: Data Manager<br/>(T_dados threshold)"]

    T2 -->|"T_proc breached<br/>compute alert"| T3C
    T2 -->|"T_dados breached<br/>data alert"| T3D
    T3C -->|"updated server registry"| T1
    T3D -->|"updated VIP_Dados DNAT<br/>(MDVBP tier map)"| T1
    T2 -->|"live T_proc per server<br/>(WSM input)"| T1
```

---

## Scenario 1 — New Client Request (VIP_Web + VIP_Dados, First Packet)

A client opens a connection to `VIP_Web:80`. The OVS switch punts the SYN to Thread 1. Thread 1 selects the best web server using the WSM cost formula and installs DNAT/SNAT rules. The web server then opens a connection to `VIP_Dados:27017`; Thread 1 intercepts that too, checks the active data-gravity tier from the MDVBP map, and installs DNAT/SNAT rules to the correct `mongod`. Both flows are then handled switch-only.

```mermaid
sequenceDiagram
    participant Client
    participant OVS as OVS Switch
    participant T1 as Controller Thread 1
    participant WebSrv as Selected Web Server
    participant VIPd as VIP_Dados (10.0.0.200)
    participant Mongo as Resolved mongod<br/>(Selective Sync Node / secondary / primary)

    Client->>OVS: TCP SYN to VIP_Web:80
    OVS->>T1: Packet-In (VIP_Web punt rule)
    Note right of T1: Lookup server registry<br/>Apply WSM (T_proc + Hops)<br/>→ Best = WebSrv_1
    T1->>OVS: FlowMod DNAT (VIP_Web → WebSrv_1)
    T1->>OVS: FlowMod SNAT (WebSrv_1 → VIP_Web)
    T1->>OVS: Packet-Out (first pkt)
    OVS->>WebSrv: Forwarded SYN
    WebSrv-->>OVS: SYN-ACK rewritten to VIP_Web
    OVS-->>Client: SYN-ACK from VIP_Web
    Note over Client,WebSrv: All further HTTP packets: switch-only

    WebSrv->>OVS: MongoDB query to VIP_Dados:27017
    OVS->>T1: Packet-In (VIP_Dados punt rule)
    Note right of T1: Lookup MDVBP map<br/>Active tier = Tier 1 (Selective Sync Node)<br/>→ Route to sync_node_ip
    T1->>OVS: FlowMod DNAT (VIP_Dados → sync_node_ip)
    T1->>OVS: FlowMod SNAT (sync_node_ip → VIP_Dados)
    T1->>OVS: Packet-Out (first pkt)
    OVS->>Mongo: MongoDB query to Selective Sync Node
    Mongo-->>OVS: MongoDB response (src=sync_node_ip)
    OVS-->>WebSrv: Response rewritten (src=VIP_Dados)
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
    participant Cache as Selective Sync Node (10.0.0.15)

    Note over Client,Cache: Phase 1 — ARP (proactive, no controller)
    Client->>OVS: ARP: Who has 10.0.0.100 (VIP_Web)?
    OVS-->>Client: ARP reply: 10.0.0.100 is-at VIP_Web_MAC
    WS->>OVS: ARP: Who has 10.0.0.200 (VIP_Dados)?
    OVS-->>WS: ARP reply: 10.0.0.200 is-at VIP_Dados_MAC

    Note over Client,Cache: Phase 2 — Client hits VIP_Web (controller selects web server)
    Client->>OVS: TCP SYN to 10.0.0.100:80
    OVS->>Ctrl: Packet-In (VIP_Web punt)
    Ctrl->>Ctrl: WSM(T_proc + Hops) → WS selected
    Ctrl->>OVS: Install DNAT+SNAT (VIP_Web ↔ WS)
    Ctrl->>OVS: Packet-Out

    Note over Client,Cache: Phase 3 — Web server hits VIP_Dados (controller selects mongod)
    WS->>OVS: TCP SYN to 10.0.0.200:27017
    OVS->>Ctrl: Packet-In (VIP_Dados punt)
    Ctrl->>Ctrl: MDVBP map: Tier 1 active → Selective Sync Node
    Ctrl->>OVS: Install DNAT+SNAT (VIP_Dados ↔ Cache)
    Ctrl->>OVS: Packet-Out

    Note over Client,Cache: Phase 4 — Ongoing (switch-only, no controller)
    Client->>OVS: HTTP GET /data
    OVS->>WS: Forwarded (DNAT applied)
    WS->>OVS: MongoDB query to VIP_Dados
    OVS->>Cache: Forwarded (DNAT applied)
    Cache-->>OVS: Response (src=cache)
    OVS-->>WS: Response rewritten (src=VIP_Dados)
    WS-->>OVS: HTTP 200 OK (src=WS)
    OVS-->>Client: HTTP 200 OK (src rewritten to VIP_Web)
```

---

## Scenario 3 — Thread 2 Observes a Threshold Breach

An Aggregation Script periodically reads per-server metrics from Local MongoDB and pushes summarised vectors to a pub/sub channel. Thread 2 subscribes to that channel, computes $T_{proc}$ from each summary, and fires the appropriate alert to Thread 3.

```mermaid
sequenceDiagram
    participant Servers as Server Containers
    participant LocalMongo as Local MongoDB Instance
    participant AggScript as Aggregation Script
    participant PubSub as Pub/Sub Channel
    participant T2 as Controller Thread 2
    participant Memory as In-Memory State
    participant TComp as Thread 3: Compute Manager
    participant TData as Thread 3: Data Manager

    Servers->>LocalMongo: insert/update metrics doc<br/>{T_total, T_dados, ram, ...}
    AggScript->>LocalMongo: Periodically read per-server metrics
    LocalMongo-->>AggScript: Metrics snapshot
    AggScript->>PubSub: Push summary vector<br/>{server_id, T_total, T_dados, ram, ...}
    PubSub-->>T2: Published summary (subscribed)
    T2->>Memory: Update per-server delay vector
    T2->>T2: Compute T_proc = T_total - T_dados
    Note over T2,Memory: Thread 1 reads Memory<br/>for WSM cost function (T_proc)
    T2->>T2: Evaluate compute threshold:<br/>T_proc > τ_proc?
    opt Compute threshold breached
        T2->>TComp: Alert: compute delay high<br/>(spawn/remove web servers)
    end
    T2->>T2: Evaluate data threshold:<br/>T_dados > τ_dados?
    opt Data threshold breached
        T2->>TData: Alert: data delay high<br/>(trigger Data Gravity transition)
    end
```

---

## Scenario 4 — Data Gravity Lifecycle (Tier 0 → 1 → 2 → 0)

Each network starts with only its own primary. As cross-network demand grows, Thread 3 deploys a cache, then a full secondary. When demand drops, resources are removed.

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

**Tier 1 — Selective Sync Node deployed in Net B:** `VIP_Dados` now routes to the Selective Sync Node. Hot collections are seeded via `mongodump | mongorestore` and kept current by one Change Stream per hot collection opened on the remote primary. A TTL index expires documents automatically.

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

**Tier 2 — Full Replica added in Net B:** `rs.add()` places a secondary of `rs_net1` in Net B. MongoDB oplog replication runs autonomously. `VIP_Dados` routes to the secondary.

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

**Tier 0 again — Demand dropped:** `rs.remove()` is called. `VIP_Dados` DNAT reverts to the remote primary. Edge storage freed.

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

Which metric triggers which transition, and what Thread 1 does to `VIP_Dados` on each.

```mermaid
graph LR
    T0["Tier 0<br/>Direct Routing<br/>(VIP_Dados → remote primary)"] -->|"T_dados ≥ τ_dados"| T1["Tier 1<br/>Selective Sync Node<br/>(VIP_Dados → Selective Sync Node)"]
    T1 -->|"cache hit < 20%<br/>OR T_dados drops"| T0
    T1 -->|"unique data %<br/>> 50% of remote DB"| T2["Tier 2<br/>Full Replica<br/>(VIP_Dados → local secondary)"]
    T2 -->|"T_dados drops<br/>below threshold"| T0

    style T0 fill:#69b,stroke:#333,color:#fff
    style T1 fill:#f9f,stroke:#333,color:#000
    style T2 fill:#f96,stroke:#333,color:#fff
```

---

## Scenario 6 — Scale-Out: Adding a Replica Secondary (Tier 2)

Thread 3 (Data Manager) first decommissions the Selective Sync Node (closes its Change Streams and lets the TTL index expire remaining docs), then runs `docker run` for a new `mongod`, attaches it to the OVS switch, calls `rs.add()` on the primary, waits for initial sync, and notifies Thread 1 to update the `VIP_Dados` DNAT rule.

```mermaid
sequenceDiagram
    participant T3 as Thread 3: Data Manager
    participant Consumer as Change Stream Consumer
    participant SyncNode as Selective Sync Node
    participant Docker as Docker Engine
    participant OVS as OVS Switch (Net B)
    participant NewMongo as New MongoDB Secondary
    participant Primary as rs_net1 Primary (Net A)
    participant T1 as Controller Thread 1

    Note over T3: T_dados > τ_dados (sustained)<br/>Promote to Tier 2

    T3->>Consumer: 1. Close all Change Streams<br/>(stop writes to Selective Sync Node)
    T3->>SyncNode: 2. Decommission: stop container<br/>(TTL index expires remaining docs)
    T3->>T1: 3. Temporarily route VIP_Dados → remote primary
    T3->>Docker: 4. docker run mongod<br/>(--replSet rs_net1, Net B subnet)
    Docker-->>NewMongo: Container starts
    T3->>OVS: 5. ovs-vsctl add-port<br/>(attach veth to switch)
    T3->>Primary: 6. rs.add("new_member_ip:27017")
    NewMongo->>Primary: 7. Initial sync<br/>(oplog tailing begins)
    Primary-->>NewMongo: Data replication stream
    Note over NewMongo: MongoDB auto-syncs from<br/>primary. No manual data copy.
    T3->>T1: 8. Update MDVBP map: Tier 2 active<br/>VIP_Dados for Net B → secondary_ip
    Note over T1: Next VIP_Dados Packet-In from Net B:<br/>DNAT → secondary_ip (local, low T_dados)
```

---

## Scenario 7 — Scale-Out: Spawning a New Web Server (Compute)

Thread 3 (Compute Manager) runs a new web server container with the two VIP connection strings pre-configured, attaches it to the switch, and registers it with Thread 1 for `VIP_Web` routing.

```mermaid
sequenceDiagram
    participant T3 as Thread 3: Compute Manager
    participant Docker as Docker Engine
    participant OVS as OVS Switch
    participant Server as New Web Server Container
    participant T1 as Controller Thread 1

    Note over T3: T_proc > τ_proc:<br/>Compute Manager spawns new web server

    T3->>Docker: 1. docker run web-server<br/>(env: DB_CONNECTION=VIP_Dados,<br/>       DB_CONNECTION_WRITE=VIP_Dados_Write)
    Docker-->>Server: Container starts<br/>(connects to VIP_Dados for all reads)
    T3->>OVS: 2. ovs-vsctl add-port<br/>(attach veth to switch)
    T3->>OVS: 3. ip addr add<br/>(assign IP in target subnet)
    Note over Server: App reads env vars on boot:<br/>DB_CONNECTION = VIP_Dados:27017<br/>DB_CONNECTION_WRITE = VIP_Dados_Write:27017<br/>SDN decides which mongod responds
    T3->>T1: 4. Register new server in<br/>server registry + MDVBP map
    Note over T1: New web server available<br/>for VIP_Web routing (WSM scoring)
```

---

## Scenario 8 — Selective Sync Node Layout

A standalone `mongod` (not a replica set member) is deployed as the Selective Sync Node. Hot collections are identified by an access tracking script that tails `system.profile` on Local MongoDB, seeded via `mongodump | mongorestore`, and kept current by one Change Stream per hot collection opened on the remote primary. A Change Stream consumer script writes incoming documents with a `ttl_expires` field; MongoDB's TTL index handles expiry. The OVS switch applies the `VIP_Dados` DNAT rule to route queries to the node.

```mermaid
graph LR
    subgraph Network A
        PrimaryA["rs_net1 Primary<br/>(Source of Truth)"]
    end

    subgraph Network B
        ClientB[User Client]
        AppB["Web Server Container<br/>(queries VIP_Dados only)"]
        OVS["OVS Switch<br/>(DNAT: VIP_Dados → Selective Sync Node)"]
        CacheB["Selective Sync Node<br/>(standalone mongod)<br/>Change Stream consumer + TTL"]
    end

    PrimaryA -.->|"Change Stream per hot collection<br/>(consumer writes with ttl_expires)"| CacheB
    ClientB -->|"HTTP to VIP_Web"| AppB
    AppB -->|"query to VIP_Dados:27017"| OVS
    OVS -->|"DNAT → Selective Sync Node (Tier 1)"| CacheB

    style CacheB fill:#f9f,stroke:#333,stroke-width:2px
    style PrimaryA fill:#4a9,stroke:#333
    style OVS fill:#aaf,stroke:#333
```

---

## Scenario 9 — Selective Sync Node Deployment Sequence

Thread 3 (Data Manager) deploys the Selective Sync Node: identifies hot collections via an access tracking script that tails `system.profile` on Local MongoDB, seeds them from the remote primary using `mongodump | mongorestore`, opens one Change Stream per hot collection via the Change Stream consumer, attaches the node to the network, and signals Thread 1 to switch the `VIP_Dados` DNAT rule.

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

    Note over T3: T_dados > τ_dados:<br/>VIP_Dados routing to remote primary

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
    T3->>T1: 8. Signal: update VIP_Dados DNAT for Net B
    Note over T1: Next Packet-In for VIP_Dados<br/>from Net B web server:<br/>DNAT → sync_node_ip (instead of remote primary)
    Note over Consumer,Primary: Change Streams continue streaming.<br/>TTL index expires documents automatically.
```

---

## Scenario 10 — Server: Read Request Flow

The web server receives an HTTP GET, queries `VIP_Dados:27017` (unaware of which `mongod` actually answers), measures $T_{dados}$, and returns the response. The OVS switch applies the active DNAT rule transparently.

```mermaid
sequenceDiagram
    participant Client
    participant Server as Web Server Container
    participant VIPd as VIP_Dados:27017
    participant OVS as OVS Switch
    participant Mongo as mongod (resolved by SDN)<br/>(cache / secondary / primary)

    Client->>Server: HTTP GET /data
    Server->>Server: Process request, build query
    Server->>VIPd: db.collection.find(query)<br/>(single conn string: VIP_Dados)
    VIPd->>OVS: Packet hits VIP_Dados DNAT rule
    OVS->>Mongo: Forwarded to current tier endpoint<br/>(Tier 0=remote primary / Tier 1=Selective Sync Node / Tier 2=secondary)
    Mongo-->>OVS: Query result
    OVS-->>Server: Result rewritten (src=VIP_Dados)
    Server-->>Client: HTTP 200 OK (JSON or HTML)
    Note over Server: Server measures T_dados = time<br/>VIP_Dados took to respond<br/>T_proc = T_total - T_dados
```

---

## Scenario 11 — Server: Write Request Flow

The web server sends a write to `VIP_Dados_Write:27017`. The SDN routes this VIP via a static DNAT rule to the local primary. The primary acknowledges the write.

```mermaid
sequenceDiagram
    participant Client
    participant Server as Web Server Container
    participant VIPdw as VIP_Dados_Write:27017
    participant Primary as rs_netX Primary<br/>(always local to data origin)

    Client->>Server: HTTP POST /data
    Server->>VIPdw: db.collection.insertOne(doc)<br/>(write VIP — always routes to primary)
    Note over VIPdw,Primary: SDN DNAT: VIP_Dados_Write<br/>→ local primary (static rule)
    Primary-->>Server: Write acknowledged
    Server-->>Client: HTTP 201 Created
```

---

## Scenario 12 — Server: Metric Reporting

A background collector thread in the web server snapshots the delay ring buffers and resource metrics and writes a single document (upsert by `_id`) to Local MongoDB. The Aggregation Script periodically reads from Local MongoDB and pushes a summary to the pub/sub channel that Thread 2 subscribes to.

```mermaid
sequenceDiagram
    participant Server as Server Container
    participant Collector as Metrics Collector<br/>(background thread)
    participant LocalMongo as Local MongoDB Container
    participant AggScript as Aggregation Script
    participant PubSub as Pub/Sub Channel

    loop Every N seconds
        Collector->>Server: Snapshot delay ring buffers<br/>Read RAM, Storage
        Collector->>LocalMongo: db.metrics.updateOne(<br/>  {_id: server_id},<br/>  {$set: {T_total_ms: 42, T_dados_ms: 35,<br/>          ram: 62, storage: 30, connections: 12}},<br/>  {upsert: true}<br/>)
    end
    AggScript->>LocalMongo: Periodically read metrics
    LocalMongo-->>AggScript: Metrics snapshot
    AggScript->>PubSub: Push summary vector
    Note over PubSub: Thread 2 subscribes to<br/>pub/sub channel
```

---

## Scenario 13 — Local MongoDB and Pub/Sub Overview

All server containers write to the same `metrics` collection in Local MongoDB. An Aggregation Script reads from this collection and pushes summarised vectors to a pub/sub channel. Thread 2 subscribes to that channel and receives the summaries.

```mermaid
graph TD
    S1["Server 1"] -->|"updateOne<br/>(metrics)"| LocalMongo["Local MongoDB<br/>(metrics collection)"]
    S2["Server 2"] -->|"updateOne<br/>(metrics)"| LocalMongo
    S3["Server N"] -->|"updateOne<br/>(metrics)"| LocalMongo
    LocalMongo -->|"periodic read"| AggScript["Aggregation Script"]
    AggScript -->|"push summary vector"| PubSub["Pub/Sub Channel"]
    PubSub -->|"subscribed push"| T2["Controller Thread 2"]
```

---

## Scenario 14 — Pub/Sub: Threshold Breach Detected

A server reports high $T_{dados}$. The Aggregation Script reads from Local MongoDB and publishes the summary to the pub/sub channel. Thread 2 receives the published message, computes $T_{proc}$, finds $T_{dados}$ above threshold, and triggers the Data Manager.

```mermaid
sequenceDiagram
    participant Server as Server Container
    participant LocalMongo as Local MongoDB
    participant AggScript as Aggregation Script
    participant PubSub as Pub/Sub Channel
    participant T2 as Controller Thread 2
    participant Memory as In-Memory State

    Note over T2,PubSub: On startup: Thread 2 subscribes<br/>to pub/sub channel

    Server->>LocalMongo: updateOne({_id: "srv_1"}, {T_total_ms: 95, T_dados_ms: 82, ...})
    AggScript->>LocalMongo: Periodic read metrics
    LocalMongo-->>AggScript: {_id: "srv_1", T_total_ms: 95, T_dados_ms: 82, ...}
    AggScript->>PubSub: Publish summary:<br/>{server_id: "srv_1", T_total_ms: 95, T_dados_ms: 82}
    PubSub-->>T2: Push published message
    T2->>Memory: Update srv_1: T_total=95, T_dados=82
    T2->>T2: Compute T_proc = 95 - 82 = 13 ms
    T2->>T2: Check compute threshold: T_proc=13 < τ_proc → OK
    T2->>T2: Check data threshold: T_dados=82 > τ_dados → BREACH
    T2->>T2: Trigger Data Manager alert (Thread 3)
```

---

## Scenario 15 — SSR: Edge-Based (Tier 1 or Tier 2 active)

A `GET /view/profile` request triggers two `VIP_Dados` queries (template + data). Both are served locally because the SDN DNAT rule routes `VIP_Dados` to a local cache or secondary. $T_{dados} \approx 2 \times \text{LAN latency}$.

```mermaid
sequenceDiagram
    participant User
    participant App as Web Server Container<br/>(Edge Node)
    participant VIPd as VIP_Dados:27017
    participant LocalMongo as Local mongod<br/>(cache or secondary — resolved by SDN)

    User->>App: GET /view/profile

    rect rgb(240, 248, 255)
        Note right of App: SSR — 2 VIP_Dados queries<br/>(both served locally by SDN DNAT)
        App->>VIPd: 1. Find Template ("profile_layout")
        VIPd-->>App: <html><body><h1>{{name}}</h1>...
        App->>VIPd: 2. Find Data ({id: 123})
        VIPd-->>App: {name: "Alice", role: "Admin"}
    end

    Note over App: T_dados = time for both VIP_Dados queries<br/>T_proc = merge template + serialise HTML
    App-->>User: HTTP 200 OK (Rendered HTML)
```

---

## Scenario 16 — SSR: No Local Data (Tier 0)

Same `GET /view/profile` request, but `VIP_Dados` is routing to the remote primary. Both queries cross the network. $T_{dados} \approx 2 \times \text{Remote RTT}$.

```mermaid
sequenceDiagram
    participant User
    participant App as Web Server Container<br/>(Edge Node)
    participant VIPd as VIP_Dados:27017
    participant RemoteMongo as Remote Primary<br/>(cross-network — resolved by SDN)

    User->>App: GET /view/profile

    rect rgb(255, 240, 240)
        Note right of App: SSR — No local data<br/>Both VIP_Dados queries cross the network
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

The complete cycle from a server reporting a metric to the controller taking infrastructure action.

```mermaid
sequenceDiagram
    participant Server as Server Container
    participant LocalMongo as Local MongoDB
    participant AggScript as Aggregation Script
    participant PubSub as Pub/Sub Channel
    participant T2 as Controller Thread 2
    participant T3comp as Thread 3: Compute Manager
    participant T3data as Thread 3: Data Manager
    participant T1 as Controller Thread 1
    participant Docker as Docker Engine
    participant OVS as OVS Switch

    Server->>LocalMongo: Periodic metric update (T_total, T_dados, ram, ...)
    AggScript->>LocalMongo: Read metrics
    LocalMongo-->>AggScript: Metrics snapshot
    AggScript->>PubSub: Push summary vector
    PubSub-->>T2: Published message (subscribed)
    T2->>T2: Update in-memory state
    T2->>T2: Compute T_proc = T_total - T_dados

    Note over T2,T1: Normal: Thread 1 uses T_proc<br/>for WSM cost function (VIP_Web routing)

    alt T_proc > τ_proc (compute bottleneck)
        T2->>T3comp: Alert: compute delay high
        T3comp->>T3comp: Run MBFD on compute space
        T3comp->>Docker: Spawn new web server
        T3comp->>OVS: Attach to network
        T3comp->>T1: Update server registry
        Note over T1: New web server available<br/>for VIP_Web routing
    else T_dados > τ_dados (data bottleneck)
        T2->>T3data: Alert: data delay high
        T3data->>T3data: Evaluate tier transition
        T3data->>Docker: Spawn cache or replica
        T3data->>OVS: Attach to network
        T3data->>T1: Update VIP_Dados DNAT in MDVBP map
        Note over T1: Next VIP_Dados Packet-In<br/>routes to new local endpoint
    else idle (scale-in)
        T2->>T3comp: Alert: server idle
        T3comp->>Docker: Remove container
        T3comp->>OVS: Remove port
        T3comp->>T1: Update server registry
    end
```
