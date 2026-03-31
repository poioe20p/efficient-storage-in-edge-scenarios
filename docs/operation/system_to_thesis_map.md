# System-to-Thesis Proposal Mapping

How the implemented **Metadata-Driven Edge Orchestration** architecture — Double-VIP SDN routing, three-tier Data Gravity, decoupled Compute/Data Managers, and Selective Sync Nodes — maps to the promises made in the thesis proposal, where it fulfills them, and where gaps remain.

| Proposal Concern                         | System Mechanism                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | Status |
| :--------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :----: |
| **Spatio-temporal usage patterns** | **Spatial:** SDN controller knows the full network topology — which network a client is in, hop distance to every server, and which `VIP_DATA_N*` domain owns each document (encoded in the document ID prefix). **Temporal:** $T_{dados}$ delay thresholds trigger tier transitions in real-time. *(Tier 1 planned: TTL indexes with frequency-aware sliding-window retention would ensure Selective Sync Nodes hold only the currently relevant working set.)* |   ⚠️   |
| **Access frequency**               | *(Tier 1 planned):* Hit-count metadata on cached documents would drive **Smart Data Retention** (frequently accessed data has its TTL refreshed; cold data self-evicts). Cache hit rate and unique-data percentage would drive **tier escalation** (Tier 1 → Tier 2) or **tier demotion** (Tier 1 → Tier 0). Currently only Tier 0 ↔ Tier 2 transitions are implemented.                                                                                                                                                                    |   ⚠️   |
| **Coordinating auto-scaling**      | The controller's Thread 3 (`ElasticityManager`) consumes two independent alert types — `ComputeAlert` (responds to $T_{proc} > \tau_{proc}$) and `DataAlert` (responds to $T_{dados} > \tau_{dados}$). This decoupling ensures a compute bottleneck does not trigger data replication, and vice versa. *(MBFD placement heuristic and Data-Coupled Task Scheduling are planned future extensions.)*                                                                                   |   ✅   |
| **Unstructured metadata**          | MongoDB's schema-less BSON document model ingests heterogeneous edge service data — from sensor telemetry to application payloads — without central schema migrations.                                                                                                                                                                                                                                                                                                         |   ✅   |

---

## 1. Mapping to "Enquadramento" (Context & Problem)

**Proposal text:** *"Flexible data storage systems capable of handling both structured and unstructured metadata, such as access frequency or spatio-temporal usage patterns, have become critical. However, coordinating the auto-scaling of services based on such meta-information remains a complex and unresolved challenge."*

### Where the system is in agreement

* **Flexible storage that handles metadata:** MongoDB's schema-less document model directly implements the "flexible data storage capable of handling structured and unstructured metadata" the proposal describes. Spatio-temporal patterns ($T_{dados}$ thresholds) drive tier transitions in real-time. *(Tier 1 planned: TTL indexes and hit-count fields would add frequency-aware retention to the storage design.)*
* **Auto-scaling coordinated by meta-information:** Thread 3's two decoupled managers (Compute Manager and Data Manager) are driven exclusively by latency metadata — $T_{proc}$ and $T_{dados}$ — rather than static configuration or manual triggers. This is precisely the "coordination of auto-scaling based on meta-information" the proposal identifies as unresolved.
* **Spatio-temporal data popularity as the placement signal:** The three-tier Data Gravity hierarchy (Tier 0 → Tier 1 → Tier 2) directly operationalizes spatio-temporal popularity: spatial demand (which network is requesting data) and temporal demand ($T_{dados}$ sustained above threshold) together determine when and where data resources are deployed and reclaimed.

### Where it diverges or goes beyond

* The proposal frames the challenge generically ("meta-information"). The system separates meta-information into two distinct classes for two distinct purposes:
  * **Resource metrics** (CPU %, RAM, request count, active connections, replication lag, hop distance) are used for **real-time routing** (Thread 1 WSM cost functions) — they are *leading indicators* that predict where to send the next request before congestion manifests.
  * **Latency metrics** ($T_{proc}$, $T_{dados}$) are used for **scaling decisions** (Thread 3 threshold evaluation) — they are *lagging indicators* that confirm sustained QoE degradation, triggering infrastructure mutations.
  This dual-concern separation is a stronger architectural contribution than the proposal anticipated: routing and scaling consume *different* subsets of the same telemetry stream, each using the signal class best suited to its decision timescale.
* The proposal does not mention the **Dual-VIP** model or **L3-only traffic classification**. These are design innovations that emerged during implementation and go beyond the original framing.

---

## 2. Mapping to "Objectivos" (Specific Goals)

### Objective 1 — *"Analyze the state of the art in edge computing, resource orchestration, and metadata-aware data management."*

* **Status:** Literature review is thesis-document work, not a system mechanism. The [literature_review.tex](../../../tese/chapters/literature_review.tex) chapter addresses this.
* **System relevance:** The design rationale in `system_mechanisms.md` grounds the orchestration approach in observable latency signals ($T_{proc}$, $T_{dados}$) rather than workload-specific assumptions, making the mechanisms applicable across diverse edge service profiles.

### Objective 2 — *"Design a programmable system architecture that supports dynamic scaling and efficient resource allocation based on spatio-temporal data popularity."*

| Sub-requirement                           | Fulfillment | Detail                                                                                                                                                                                                                                  |
| :---------------------------------------- | :---------: | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Programmable**                    |     ✅     | Python-based OS-Ken (Ryu) SDN controller. All routing, scaling, and placement logic is software-defined — no hardware lock-in.                                                                                                         |
| **Dynamic scaling**                 |     ✅     | Two-tier data gravity (Tier 0 → Tier 2) and elastic compute (spawn/remove web server containers). Triggered by delay thresholds, not manual intervention. *(Tier 1 Selective Sync Node: planned.)*                                                                  |
| **Spatio-temporal data popularity** |     ✅     | **Spatial:** Network topology (hop distance, document-ID domain prefix). **Temporal:** $T_{dados}$ latency thresholds trigger Tier 0 → Tier 2 transitions. *(Tier 1 planned: TTL-based cache retention with hit-count sliding window, cache-hit-rate and unique-data-% metrics.)* |
| **Efficient resource allocation**   |     ✅     | Tier 2 deployed when $T_{dados} > \tau_{dados}$ sustained. Scale-in removes idle resources via two-phase cooperative drain. *(MBFD heuristic: planned. Tier 1 bounded working set: planned.)*                                                 |

### Objective 3 — *"Implement a functional prototype that integrates containerized services with adaptive, metadata-informed resource management."*

| Sub-requirement                  | Fulfillment | Detail                                                                                                                                                                                                                                                      |
| :------------------------------- | :---------: | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Containerized services** |     ✅     | Docker containers for web servers, MongoDB instances, and the SDN controller image (OS-Ken). *(Selective Sync Node containers: planned for Tier 1.)*                                                                                                                                                   |
| **Adaptive**               |     ✅     | The system adapts to demand in real-time: the Telemetry Greenthread observes latency → Thread 3 (ElasticityManager) mutates infrastructure → Thread 1 re-routes traffic. *(Selective Sync Node with autonomous Change Stream consumption: planned for Tier 1.)* |
| **Metadata-informed**      | ✅     | Metadata driving decisions: **Routing** (Thread 1) uses CPU %, RAM, request count, active connections, replication lag, and hop distance via multi-dimensional WSM cost functions. **Scaling** (Thread 3) uses $T_{proc}$ and $T_{dados}$ latency thresholds. Metrics collected per-request via ZMQ PUSH; windowed summaries published by the per-network Aggregator; the Telemetry Greenthread subscribes and resolves server_id → MAC before storing stats for Thread 1 consumption. *(Tier 1 planned: hit-count, cache-hit-rate, unique-data-% for tier transitions.)* |

### Objective 4 — *"Define and execute experimental scenarios that simulate realistic edge workloads and data usage patterns."*

| Sub-requirement               | Fulfillment | Detail                                                                                                                                                                                                                                                                                                             |
| :---------------------------- | :----------: | :----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Scenario definition** | ⚠️ Partial | `system_scenarios.md` describes 17 operational scenarios with sequence/topology diagrams. The dual-mode server (Raw Data Proxy + SSR) generates realistic workloads. However, formal experimental scenarios with controlled variables, baselines, and hypothesis-driven test plans are **not yet defined**. |
| **Realistic workloads** | ⚠️ Partial | The SSR mode generates 1–2 `VIP_DATA_N*` queries per HTTP request (template + content), creating a measurable Data Gravity Amplification Effect. The `generate_iperf_mongo_traffic.sh` script exists. Formal benchmarking suite is **pending**.                                                           |

### Objective 5 — *"Evaluate the system's performance using relevant metrics such as latency, scalability, and resource efficiency."*

| Sub-requirement               |   Fulfillment   | Detail                                                                                                                                                                                                           |
| :---------------------------- | :-------------: | :--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Latency metrics**     | ✅ Instrumented | $T_{total}$, $T_{dados}$, $T_{proc}$ are measured per-request and pushed via ZMQ PUSH to the per-network Aggregator. The Telemetry Greenthread evaluates them in real-time via ZMQ SUB (Aggregator publishes windowed summaries).                                                                         |
| **Scalability**         |   ✅ Designed   | Elastic scale-out/in for both compute and data. Independent replica sets per network avoid sharding complexity.                                                                                                  |
| **Resource efficiency** |   ✅ Designed   | Tiered hierarchy minimizes edge storage: Tier 0 = zero infrastructure; Tier 2 = full replica only when justified by sustained $T_{dados}$ threshold breach. Scale-in via two-phase cooperative drain reclaims resources. *(Tier 1 bounded working set and MBFD active-server minimization: planned.)* |
| **Formal benchmarking** |   ❌ Pending   | No formal comparison against baselines (static replication, round-robin LB, etc.) has been executed yet. The metrics are collected but the comparative evaluation is**future work**.                       |

### Objective 6 — *"Analyze and interpret results, discussing strengths, limitations, and future directions."*

* **Status:** ❌ Pending. This depends on completing Objective 4 and 5 first. Will be addressed in the thesis methodology and results chapters.

---

## 3. Mapping to "Actividades" (Activities)

### Phase 1 — Literature Review (1.1–1.3)

* **Status:** Thesis-document work. Covered in [literature_review.tex](../../../tese/chapters/literature_review.tex).

### Phase 2 — Solution Design & Implementation

#### Activity 2.1: *"Design a system architecture that integrates programmable control, dynamic scaling, and container-based resource abstraction."*

* **Fulfilled by:** The three-thread controller architecture + Docker containers + OVS switches.
  * **Programmable control:** OS-Ken SDN controller with three concurrent threads (Fast Path, Observer, Slow Path). OpenFlow rules installed dynamically per-connection.
  * **Dynamic scaling:** `ElasticityManager` with decoupled `ComputeAlert` and `DataAlert` handling, independently triggered by $T_{proc}$ and $T_{dados}$ thresholds. *(MBFD placement heuristic: planned.)*
  * **Container-based resource abstraction:** Web servers and MongoDB instances are all Docker containers managed by Thread 3 (`ElasticityManager` + `NodeAdder`). *(Planned: Selective Sync Node containers for Tier 1, embedding Change Stream consumer logic in the container image.)*
* **Status:** ✅ Designed and documented.

#### Activity 2.2: *"Specify system components, interaction flows, and decision-making algorithms, especially for handling spatio-temporal metadata."*

* **Fulfilled by:**
  * **Routing algorithms (Thread 1):** Multi-dimensional WSM cost functions for both compute and data routing:
    * Server: $Cost_j^{web} = w_{cpu} \cdot \frac{CPU_j}{CPU_{max}} + w_{ram} \cdot \frac{RAM_j}{RAM_{max}} + w_{req} \cdot \frac{Req_j}{Req_{max}} + w_{hops} \cdot \frac{Hops_j}{Hops_{max}}$
    * Storage: $Cost_j^{data} = w_{cpu}^{s} \cdot \frac{CPU_j}{CPU_{max}} + w_{ram}^{s} \cdot \frac{RAM_j}{RAM_{max}} + w_{conn}^{s} \cdot \frac{Conn_j}{Conn_{max}} + w_{lag}^{s} \cdot \frac{Lag_j}{Lag_{max}} + w_{hops}^{s} \cdot \frac{Hops_j}{Hops_{max}}$
  * **Placement algorithm (Thread 3):** Simple threshold-based spawning: $T_{proc} > \tau_{proc}$ → spawn compute; $T_{dados} > \tau_{dados}$ → spawn storage. *(MBFD heuristic with multi-dimensional scoring: planned.)*
  * **Tier transition rules (Thread 3 Data Manager):**
    * Tier 0 → 2: $T_{dados} \geq \tau_{dados}$ (sustained)
    * Tier 2 → 0: $T_{dados}$ sustained below threshold
    * *(Planned — Tier 1 transitions: Tier 0 → 1 on $T_{dados} \geq \tau_{dados}$; Tier 1 → 0 on cache hit rate < 20%; Tier 1 → 2 on unique data % > 50%)*
  * *(Planned — Tier 1)* **Data retention algorithm (Selective Sync Node):** Frequency-aware sliding window — on each read, `last_accessed` would be reset (extending TTL) and `hit_count` incremented. Cold data would self-evict via MongoDB TTL indexes.
* **Status:** ✅ Fully specified.

#### Activity 2.3: *"Implement a prototype system using appropriate development tools, emphasizing modularity and alignment with edge computing constraints."*

* **Fulfilled by:** Python SDN controller, Docker containers, OVS switches, MongoDB instances, bash network setup scripts.
* **Modularity:** The three threads, decoupled Compute/Data managers, and clean separation of VIP_SERVER / VIP_DATA_N* traffic planes demonstrate modularity.
* **Edge constraints:** Scale-in via two-phase cooperative drain removes idle resources. *(Planned: Tier 1 caches with bounded memory via TTL self-eviction; MBFD active-server minimization.)*
* **Status:** ⚠️ In progress — core controller logic and container images exist, but full end-to-end integration testing is incomplete.

### Phase 3 — Experimental Evaluation

#### Activity 3.1: *"Define evaluation objectives and formulate research hypotheses related to scalability, responsiveness, and data accessibility."*

* **Status:** ❌ Pending. The system collects the right metrics ($T_{total}$, $T_{dados}$, $T_{proc}$, hit rates) but formal hypotheses have not been stated.

#### Activity 3.2: *"Design and configure experimental scenarios, including representative workloads, edge network topologies, and varying data popularity trends."*

* **Status:** ⚠️ Partial. Network topologies are scriptable (`build_network_1.sh`, `build_network_2.sh`). Traffic generation exists (`generate_iperf_mongo_traffic.sh`). Formal experimental design with controlled data-popularity trends is **pending**.

#### Activity 3.3: *"Use a document-oriented database to manage and query data with associated meta-information, supporting realistic edge data use cases."*

* **Fulfilled by:** MongoDB is used in **six distinct roles** that validate it as an active infrastructure component, not merely a data store:
  1. **Document model** — schema-less ingestion of heterogeneous edge service data.
  2. **TTL indexes** — *(planned for Tier 1)* self-managing cache eviction.
  3. **Oplog + replica sets** — autonomous Tier 2 data synchronization via `rs.add()` / `rs.remove()`.
  4. **VIP-based connection control** — SDN prevents driver topology discovery; structural isolation at the network layer.
  5. **Change Streams** — *(planned for Tier 1):* per-collection Change Streams from the remote primary would be consumed by the Change Stream consumer script in each Selective Sync Node. Controller telemetry uses ZMQ PUSH/PUB/SUB: servers push per-request metrics via ZMQ PUSH to the per-network Aggregator; the Telemetry Greenthread subscribes to the Aggregator's ZMQ PUB socket.
  6. **Traffic-plane separation** — `VIP_DATA_N*` (data queries, SDN-routed per data-gravity tier) with write-path isolation (writes always routed to the local primary).
* **Realistic edge use cases:** The dual-mode server handles both Raw Data Proxy (`/api/` — IoT, sensor data) and Server-Side Rendering (`/view/` — user profiles, dashboards). The SSR mode produces a measurable **Data Gravity Amplification Effect** (2× `VIP_DATA_N*` queries per HTTP request).
* **Status:** ✅ Designed and documented.

#### Activity 3.4: *"Execute experiments and collect metrics such as response time, resource utilization, and data replication effectiveness."*

* **Status:** ❌ Pending. The metric collection pipeline is fully designed (server → ZMQ PUSH → Aggregator → ZMQ PUB → Telemetry Greenthread), but formal experiment execution and data collection have not been completed.

### Phase 4 — Results Analysis & Validation (4.1–4.4)

* **Status:** ❌ Pending. Depends on Phase 3 completion.

---

## 4. Key Innovations Beyond the Proposal

The following design decisions were not explicitly anticipated in the proposal but emerged during architecture development. They strengthen the thesis contribution:

| Innovation                                  | What it does                                                                                                                             | Why it matters                                                                                                                                                                                                              |
| :------------------------------------------ | :--------------------------------------------------------------------------------------------------------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Double-VIP model**                  | `VIP_SERVER` (compute routing) and `VIP_DATA_N*` (data routing per domain) cleanly separate the two traffic planes at L3. No deep packet inspection. | Eliminates the need for `mongos`, config servers, and application-level routing logic. The MongoDB driver sees one stable address.                                                                                        |
| **Elimination of sharding**           | Independent replica sets per network replace the original sharded design. No shard keys, no zone ranges, no `sh.moveChunk()`.          | Dramatically simplifies bootstrap (two `rs.initiate()` commands) and eliminates the heavyweight chunk-migration mechanism.                                                                                                |
| **Dual-concern telemetry separation** | Resource metrics (CPU, RAM, connections, hops) drive **routing** (Thread 1); latency metrics ($T_{proc}$, $T_{dados}$) drive **scaling** (Thread 3). Each concern uses the signal class matched to its decision timescale. | Routing uses *leading indicators* to steer traffic proactively; scaling uses *lagging indicators* to confirm sustained QoE degradation before mutating infrastructure. This avoids both premature scaling (CPU spike ≠ capacity problem) and sluggish routing (waiting for latency to rise before avoiding overloaded nodes). |
| **Decoupled Compute/Data managers**   | Thread 3 splits into two independent managers responding to different delay signals.                                                     | A compute bottleneck doesn't trigger unnecessary data replication. A data locality problem doesn't spawn unnecessary web servers. Correct remediation for each bottleneck type.                                             |
| **Document-ID-encoded routing**       | The domain prefix in each document ID (e.g.,`"net2::sensor_xyz_002"`) tells the web server which `VIP_DATA_N*` to connect to.          | Zero overhead: no directory lookup, no controller query, no extra RTT. The routing decision is baked into the data at write time.                                                                                           |
| **Data Gravity Amplification Effect** | SSR workloads trigger 2×`VIP_DATA_N*` queries per HTTP request, amplifying both the cost of remote data and the benefit of local data.  | Provides the strongest empirical argument for topology-aware data placement and makes tier transition decisions faster and more decisive.                                                                                   |

I'm not sure if these are really inovations, I think the inovation is perphaps create an architecture that handles all these different aspects as whole rather?

---

## 5. Gap Summary

| Area                                              |      Status      | What's needed                                                                                    |
| :------------------------------------------------ | :--------------: | :----------------------------------------------------------------------------------------------- |
| Architecture design                               |   ✅ Complete   | —                                                                                               |
| Decision algorithms                               |   ✅ Specified   | WSM, tier transition rules (Tier 0 ↔ 2). *(Planned: MBFD, Tier 1 transitions, frequency-aware retention)*                                      |
| Prototype implementation                          | ⚠️ In progress | End-to-end integration testing of Tier 0 ↔ Tier 2. Tier 1 (Selective Sync Node) not yet implemented                                                |
| Formal hypotheses                                 |    ❌ Pending    | Testable claims about latency reduction, resource efficiency, scalability                        |
| Experimental design                               |   ⚠️ Partial   | Controlled scenarios with variable data popularity, baselines for comparison                     |
| Benchmarking & evaluation                         |    ❌ Pending    | Execute experiments, collect metrics, compare against static replication / round-robin baselines |
| Results analysis                                  |    ❌ Pending    | Depends on benchmarking                                                                          |
| Thesis writing (lit review, methodology, results) | ⚠️ In progress | Chapters started but not complete                                                                |

---

## 6. Defense Argument

When the jury asks: *"How does your system improve over existing edge approaches?"*

> Existing systems treat network routing, compute scaling, and data placement as three independent problems — each managed by a separate subsystem with no shared context.
>
> This thesis contributes a **cross-layer orchestration framework** where a single SDN controller consumes multi-dimensional telemetry and applies it through two distinct decision loops:
>
> - **Routing** (Thread 1): multi-dimensional WSM cost functions use CPU utilization, RAM usage, request count (for servers) / active connections and replication lag (for storage), and hop distance as *leading indicators* to steer each new connection to the least-loaded, most-local backend.
> - **Scaling** (Thread 3): latency thresholds ($T_{proc} > \tau_{proc}$, $T_{dados} > \tau_{dados}$) serve as *lagging indicators* that confirm sustained QoE degradation, triggering infrastructure mutations — spawning web servers for compute bottlenecks, or triggering a **three-tier Data Gravity** transition for data-locality bottlenecks.
>
> The system is **lightweight by default** (Tier 0: zero additional infrastructure) and **scalable by design** (Tier 2: full replica when demand justifies it; Tier 1 Selective Sync Node: planned). It only consumes edge resources when — and for as long as — demand justifies them, then automatically reclaims them.
>
> The **Double-VIP** model structurally prevents the MongoDB driver from making independent routing decisions — ensuring that data-path authority resides exclusively in the network layer. This is architecturally stronger than application-level `directConnection=true` because the isolation guarantee is enforced at L3, independent of driver behavior.
>
> The result is a system where **data moves toward consumers that need it, and only for as long as they need it** — directly addressing the proposal's "unresolved challenge" of coordinating auto-scaling with spatio-temporal data patterns.
