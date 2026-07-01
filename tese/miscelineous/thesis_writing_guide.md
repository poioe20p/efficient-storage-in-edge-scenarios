# Thesis Writing Guide — Structure and Content Plan

> **Status**: Working guide · **Date**: 2026-06-30
> **Purpose**: Defines the chapter structure, topic coverage per section, and
> mapping to the methodology guidelines (`some_guidelines.md`). Does NOT
> contain prose — only what goes where and why.

---

## Thesis Framing (No IoT)

The thesis is framed around **edge computing** and **stateful web services** —
not IoT. The experimental workload is a **Multi-Region Content Discovery
Platform** deployed at the network edge: content items of diverse types
(articles, videos, podcasts, image galleries, events, tools, reviews,
discussions, curated lists) are ingested regionally and discovered globally
through tag-based personalized feeds. The workload is read-heavy with
periodic writes, handles heterogeneous data (different content types with
different structures), serves both data-locality (content lookups dominate)
and compute-analytics (feed ranking dominates) workloads, and experiences
demand shifts across regions.

The proposal title: *"Efficient Data Storage Using Programmable Containers
in Edge Computing."*

The core concepts from the proposal that guide the framing:

- Edge computing — services deployed closer to users
- Programmable infrastructure (SDN) — network-level control
- Containerized stateful services — lightweight, portable, with data
- Metadata-driven decision-making — spatio-temporal data popularity
- Document-oriented storage — flexible schema for heterogeneous metadata

---

## Thesis Type (per Guidelines)

**Applied + Experimental hybrid.**

- **Applied**: A prototype was built (SDN controller, Docker edge servers,
  MongoDB replica sets, telemetry pipeline) to demonstrate that three
  orchestration dimensions can be tuned independently from a single
  control point.
- **Experimental**: Each dimension is varied one at a time while holding the
  other two constant. The effect on dependent variables (reaction latency,
  service quality, control overhead) is measured.

The contribution is **characterizing the trade-off surface** across three
dimensions — not proving that the unified design is superior to separated
architectures.

---

## Chapter Structure

```
Chapter 1. Introduction
Chapter 2. Literature Review
Chapter 3. System Architecture
Chapter 4. Methodology
Chapter 5. Implementation
Chapter 6. Results and Discussion
Chapter 7. Conclusions and Future Work
```

7 chapters. Minimal, guideline-compliant.

---

## Chapter 1. Introduction

### 1.1. Context and Motivation

**What to cover:**

- **Edge computing**: services deployed closer to users, reducing latency
  and backbone traffic compared to centralized cloud.
- **Stateful services at the edge**: many edge services are not purely
  compute — they depend on data. The co-location of compute and data matters.
- **The conventional approach**: in edge and cloud platforms, three critical
  functions — monitoring (collecting service metrics), traffic routing
  (distributing requests across backends), and auto-scaling (adjusting
  infrastructure capacity) — are handled by separate control loops, even when
  they belong to the same platform. In Kubernetes, for example, the Horizontal
  Pod Autoscaler (HPA), kube-proxy, and the metrics pipeline (metrics-server,
  often Prometheus) are different components with independent reconciliation
  intervals. In OpenStack, Heat (orchestration), Neutron (networking), and
  Ceilometer (telemetry) are distinct services communicating via message bus.
  Each control loop has its own view of system state and its own decision
  cadence. The accumulation of these intervals — HPA sync period, scheduling
  latency, endpoint propagation — means that the time from overload detection
  to traffic reaching a new backend can be substantially longer than the
  container startup time alone.
- **Separation is deliberate and has well-understood benefits**: fault
  isolation (if monitoring fails, routing continues unaffected), independent
  scalability (each function can be scaled and optimized separately),
  modularity (components can be replaced or upgraded independently), and
  ecosystem maturity (each component benefits from dedicated testing and
  community maintenance).
- **This thesis does not argue that separation is wrong or that co-location
  is superior.** It asks a narrower, exploratory question: if these three
  functions are co-located in a single decision point — an SDN controller
  with shared data structures — what properties does this design exhibit?
  How do three controllable dimensions within that design (telemetry
  freshness, backend selection policy, and data locality strategy) each
  independently affect the system's ability to maintain service quality
  during demand shifts? The contribution is characterizing this design
  space, not adjudicating between architectural paradigms.
- **SDN as the enabling technology**: OpenFlow provides per-flow traffic
  steering at the network layer; a programmable controller (OS-Ken/Ryu)
  can consume telemetry, evaluate thresholds, spawn or drain containers,
  and install forwarding rules — all from the same process. This
  co-location is the **experimental apparatus**, not the hypothesis
  under test. It makes the three dimensions independently tunable,
  enabling controlled within-system experimentation.

**DO NOT mention:** IoT, smart cities, sensor data, device types, industrial
monitoring, or any IoT-specific scenario.

### 1.2. Objectives

**What to cover:**

The 6 objectives from the thesis proposal:

1. Analyze the state of the art in edge computing, resource orchestration,
   and metadata-aware data management
2. Design a programmable system architecture supporting dynamic scaling based
   on spatio-temporal data popularity
3. Implement a functional prototype integrating containerized services with
   adaptive, metadata-informed resource management
4. Define and execute experimental scenarios simulating realistic edge
   workloads and data usage patterns
5. Evaluate system performance using latency, scalability, and resource
   efficiency metrics, comparing against baselines
6. Analyze and interpret results, discussing strengths, limitations, and
   future directions

### 1.3. Research Questions

**What to cover:**

The three-pillar RQ set from `system_to_thesis_map_rq_v2.md`:

| Pillar | RQ | Core Question |
|---|---|---|
| Telemetry Freshness | RQ1 | How does telemetry delivery cadence affect control quality during demand shifts? |
| Backend Selection | RQ2 | How does cross-layer metadata improve backend selection beyond L4 and L4+ baselines? |
| Data Locality | RQ3 | How do data-locality readiness strategies trade off service benefit against operating cost? |

Briefly state what each RQ isolates and how they relate — they are three
independently tunable dimensions of a unified orchestration design.

### 1.4. Methodology Overview

**What to cover (1–2 pages):**

- Project type: applied + experimental hybrid
- Experimental design: within-system, single-variable manipulation. Vary one
  dimension while holding the other two constant. Same hardware, same workload,
  same infrastructure — only the variable under test changes.
- Comparison strategy: baselines encode architectural properties of separated
  systems (polling at 30s, topology-only routing, remote-only data), not
  specific competing products.
- Reference to Chapter 4 for full methodological detail.

### 1.5. Contributions

**What to cover:**

1. Experimental characterization of the trade-off surface across three
   cross-layer orchestration dimensions (telemetry freshness, backend
   selection, data locality) — each independently varied and measured.
2. An SDN-based experimental platform where monitoring, routing, and scaling
   are co-located, enabling isolated variation of each dimension.
3. Empirical evidence on the relationship between telemetry delivery cadence
   and reaction latency during demand shifts (RQ1).
4. Quantification of cross-layer metadata benefit in backend selection
   compared to single-layer baselines (RQ2).
5. Characterization of the cost/benefit profile of data locality readiness
   strategies (RQ3).

### 1.6. Document Structure

Brief paragraph outlining the 7 chapters.

---

## Chapter 2. Literature Review

### 2.1. Review Method

**What to cover (2–3 paragraphs):**

- **Databases searched**: IEEE Xplore, ACM Digital Library, Scopus, Google
  Scholar
- **Search terms and Boolean combinations**: e.g., `("edge computing" OR
  "fog computing") AND ("auto-scaling" OR "elasticity") AND ("SDN" OR
  "software-defined networking")`, plus separate searches for data placement
  and document databases
- **Time range**: 2015–2025 (SDN and edge computing matured in this period)
- **Inclusion criteria**: peer-reviewed, English, relevant to edge
  orchestration / SDN / auto-scaling / data placement / document databases
- **Exclusion criteria**: not about edge/cloud infrastructure, purely
  theoretical with no systems context
- **Categorization framework**: papers grouped into five themes (see §2.2–2.6)
- **Numbers**: total found → after deduplication → after screening → final set
  (approximate ranges are acceptable; exact PRISMA-style numbers if available)

### 2.2. Edge Computing Architectures

**What to cover:**

- Edge vs. cloud vs. fog: definitions, latency tiers, resource constraints
- Containerization at the edge: Docker, lightweight virtualization,
  orchestration frameworks
- Stateful vs. stateless edge services: why data locality matters
- Reference architectures: multi-access edge computing (MEC), cloudlet, fog
  node

### 2.3. SDN and Programmable Infrastructure

**What to cover:**

- SDN principles: control/data plane separation, OpenFlow, programmable
  forwarding
- SDN controllers: Ryu/OS-Ken, ONOS, OpenDaylight — comparison of
  programmability models
- SDN for traffic engineering: per-flow routing, dynamic rule installation,
  ARP handling
- SDN at the edge: challenges (latency, reliability) and opportunities
  (topology awareness, L3 traffic-plane separation)

### 2.4. Auto-Scaling and Elasticity Mechanisms

**What to cover:**

- Taxonomy: threshold-based, predictive/proactive, ML-driven, reactive
- Industry systems: Kubernetes HPA/VPA, AWS Auto Scaling Groups, OpenStack
  Heat
- Scaling dimensions: horizontal vs. vertical, compute vs. data
- **Control-loop cadences in production systems**: each function in the
  monitoring → decision → routing chain operates on its own reconciliation
  interval. In Kubernetes: HPA default sync period (15 s), metrics scraping
  interval, pod scheduling latency, kube-proxy/EndpointSlice propagation.
  In OpenStack: Heat polling interval, Ceilometer sampling period, Neutron
  agent updates. The accumulation of these intervals determines the
  end-to-end reaction time to demand shifts — an observable property of
  the architecture, not a flaw.
- **Separation benefits**: fault isolation (a metrics pipeline failure does
  not break routing), independent scaling (monitoring scales independently
  of the load balancer), modularity (components are replaceable), and
  specialization (each component is optimized for its specific function).

### 2.5. Metadata-Driven Data Placement and Replication

**What to cover:**

- Spatio-temporal data popularity models: how access patterns change over
  time and across locations
- Replica placement strategies: static, dynamic, popularity-aware
- Data gravity: the concept that data attracts computation — relevant for
  stateful edge services
- Tiered storage: hot/warm/cold data classification, tier transitions
- Existing approaches: consistent hashing, geographically distributed
  replication, cache hierarchies

### 2.6. Document-Oriented Databases for Edge Environments

**What to cover:**

- NoSQL landscape: key-value, document, column-family, graph — why document
  model suits edge data
- MongoDB specifically:
  - **Schema-less document model**: heterogeneous data types with different
    structures coexist in one collection without schema migrations
  - **Replica set API**: programmatic `rs.add()` / `rs.remove()` enables
    elastic data tiering — members join and leave under controller direction
  - **Connection handling**: connection pooling, `retryReads`, concurrent
    client support provide fault-tolerance for edge services
  - **Horizontal read scaling**: secondary reads distribute query load without
    requiring sharding at the target deployment scale
- Comparison with relational databases for edge use: schema flexibility,
  horizontal scaling, operational simplicity
- Existing work on MongoDB at the edge

### 2.7. Synthesis

**What to cover:**

- Each domain — edge architectures, SDN, auto-scaling, data placement, and
  document databases — treats monitoring, routing, and data management as
  separate concerns managed by independent control loops. This separation
  is a deliberate architectural choice with documented benefits (fault
  isolation, modularity, independent scalability).
- The literature extensively documents the properties of each function in
  isolation: optimal scraping intervals for monitoring, efficient load
  balancing algorithms, data placement heuristics. But these are studied
  as independent problems with independent solutions.
- No existing work examines these three dimensions as **independently
  tunable levers within a single control point** where they share state
  and can be varied one at a time while the others are held constant.
- The consequence of this gap in the experimental record is that the
  **relative importance** of each dimension is unknown. If an architect
  can only improve one thing — fresher telemetry, smarter routing, or
  better data placement — which should it be? The literature provides
  no empirical basis for answering this question because no platform
  exists that isolates these dimensions.
- This is the space the present thesis explores: not claiming that
  co-location is superior to separation, but constructing the platform
  that makes these dimensions independently testable, and then
  characterizing the trade-off surface that emerges.

---

## Chapter 3. System Architecture

### 3.1. Design Principles

**What to cover:**

- Cross-layer orchestration: monitoring, routing, and scaling as tunable
  dimensions of a single control point
- Single process, shared data structures: Thread 1 (routing), Thread 2
  (telemetry), Thread 3 (elasticity) — no propagation delay between them
- Tiered data gravity: Tier 0 (remote only, zero local infrastructure),
  Tier 1 (selective sync, bounded working set), Tier 2 (full local replica)
- Decoupled compute and data scaling: ComputeAlert vs. DataAlert respond
  to different latency signals ($T_{proc}$ vs. $T_{dados}$)
- Domain-agnostic observability: the controller observes latency and resource
  metrics — any containerized request/response service produces these signals

### 3.2. Architecture Overview

**What to cover:**

- Component diagram (produce from `docs/diagrams/`):
  - Two edge networks (LAN1, LAN2) connected via WAN link
  - Each LAN: OVS switch, edge servers, storage servers, clients
  - SDN controller (OS-Ken) with three greenthreads
  - Double-VIP model: `VIP_SERVER` (compute traffic), `VIP_DATA_N1` /
    `VIP_DATA_N2` (data traffic per region)
  - Docker containers for all service components
  - Telemetry pipeline: edge servers → ZMQ PUSH → Aggregator → ZMQ PUB /
    HTTP cache → Controller
- Interaction flows between components
- How the controller discovers topology during setup

### 3.3. Telemetry Pipeline

**What to cover:**

- Per-request instrumentation on edge servers ($T_{total}$, $T_{proc}$,
  $T_{dados}$, CPU, RAM)
- ZMQ PUSH from edge servers to per-network Aggregator
- Aggregator: 10-second windowed summaries, ZMQ PUB to controller, HTTP
  cache for polling
- Controller telemetry source abstraction: `ZmqTelemetrySource` (push) and
  `PollingTelemetrySource` (poll)
- Polling mechanism: configurable `POLL_INTERVAL_S`, deduplication by
  `window_end`, always-fresh cache
- Telemetry schema: what fields are in each summary, what the controller
  consumes

### 3.4. Routing and Backend Selection

**What to cover:**

- Weighted Sum Model (WSM) cost functions for compute and data planes
- Policy modes (the independent variable for RQ2):
  - `topology_only`: hop distance only (encodes L4 load balancer with no
    health checks)
  - `topology_host`: hops + CPU, RAM, request count/connections (encodes
    HAProxy/NGINX with host health checks)
  - `topology_host_replica`: all above + replication lag, member state
    (cross-layer — only possible with SDN)
- Per-flow OpenFlow rule installation: TCP SYN triggers cost evaluation,
  rule installed for the connection duration
- Double-VIP ARP interception + DNAT/SNAT: MongoDB driver sees a single
  stable address regardless of which physical node backs it
- L3 traffic-plane separation: `VIP_SERVER` and `VIP_DATA_N*` are
  independently managed

### 3.5. Elasticity and Data Gravity Tiers

**What to cover:**

- ElasticityManager (Thread 3): consumes ComputeAlert and DataAlert from
  a priority queue
- Compute scaling: triggered by $T_{proc}$ sustained above threshold,
  spawns edge server containers, registers MAC in VIP_SERVER pool
- Data scaling (Tier 0 → Tier 2): triggered by $T_{dados}$ sustained above
  threshold, spawns MongoDB instances, adds to replica set via `rs.add()`,
  registers in VIP_DATA pool
- Tier 1 Selective Sync Node: design description (partial implementation,
  honest scope — see gap note below)
- Scale-down: two-phase cooperative drain, cooldown-gated evaluation
- Threshold configuration: degradation score formula, dynamic threshold
  with diminishing increments for storage, peer relief for compute

**Honest scope note on Tier 1:**
Tier 1 (Selective Sync Node) exists in the architecture design as the
intermediate tier between remote-only (Tier 0) and full replica (Tier 2).
The current prototype exercises Tier 0 ↔ Tier 2 transitions. Tier 1 is
described as a design component; its full experimental validation is
deferred to future work.

### 3.6. Experimental Workload

**What to cover:**

- A **Multi-Region Content Discovery Platform** deployed across two edge
  networks. Content items of diverse types are ingested regionally and
  discovered globally through tag-based personalized feeds.
- **Data model** (2 collections):
  - `content_items`: one document per content item. Heterogeneous document
    types (article, video, podcast, image_gallery, event, tool, review,
    discussion, curated_list) with type-specific payload and metadata
    fields — no uniform schema across types. Tagged by topic (news,
    entertainment, sports, technology, finance, health, education, science,
    premium, trending, featured, archived).
  - `user_profiles`: one document per user. Three profile tiers (focused:
    1–2 tags, broad: 3–4 tags, global: 5–6 tags). Contains subscribed tags
    and followed content items. Per-content-type relevance overrides
    replace a uniform threshold.
- **Request types** (3 endpoints):
  1. `content_lookup` (`GET /content/<id>?requester=<user_id>`): fetches a
     specific content item by ID, enriches with per-user relevance baseline
     from the requester's profile. Involves cross-region reads when the
     content and requester are in different regions. Primary data-locality
     driver.
  2. `feed_ranking` (`GET /feed/<user_id>?limit=N`): ranks and summarizes
     content items matching the user's subscribed tags across all regions.
     Involves multi-region queries, tag-based filtering, and CPU-side
     4-factor relevance scoring. Primary compute driver.
  3. `service_pressure` (`GET /service_pressure?window_min=&limit=`): local
     support-state summary of recent request activity. No database traffic.
     Service introspection endpoint.
- **Two-regime interpretation**:
  - Data-locality regime: `content_lookup` requests dominate → stresses
    cross-region data access and storage scaling
  - Compute-analytics regime: `feed_ranking` requests dominate → stresses
    edge-server CPU and compute scaling
- **10-phase demand schedule**: phases transition between regimes, vary
  request rate (1–17 req/s/client), and vary cross-region ratio (0–95%)
- **Why this workload**: read-heavy (creates data gravity), heterogeneous
  document types (justifies document model and schema-less design),
  controlled phase transitions (enables before/after measurement within a
  single run), two independent stress dimensions (data-locality and compute)
  that can be isolated, user-specific parameterization (per-user relevance
  overrides exercise per-request metadata enrichment)

**DO NOT mention:** IoT, sensors, devices, temperature, humidity, firmware,
industrial monitoring, smart cities, or any domain-specific framing.

---

## Chapter 4. Methodology

### 4.1. Research Approach

**What to cover:**

- Project type (per guidelines): applied + experimental hybrid
- Overall aim: characterize how telemetry freshness, backend selection
  policy, and data locality each independently affect service quality
  during demand shifts in a cross-layer SDN-orchestrated edge system
- Four objectives with methods mapped:

| Objective | Method | Output |
|---|---|---|
| 1. Understand the state of the art | Literature analysis | Chapter 2 — categorization, gap identification |
| 2. Build a platform that isolates three dimensions | Implementation (prototype construction) | SDN controller + edge servers + telemetry pipeline + MongoDB replica sets |
| 3. Test each dimension experimentally | Controlled experiment (within-system, single-variable) | RQ1/RQ2/RQ3 results |
| 4. Interpret the trade-off surface | Comparative analysis of experimental data | Chapters 6–7 — what matters most, trade-offs, limitations |

### 4.2. Experimental Design

**What to cover:**

- **Design type**: within-system, single-variable manipulation. Vary one
  independent variable while holding all others constant.
- **Comparison strategy**: baselines are real operating modes of the system
  that encode architectural properties of separated architectures:
  - RQ1: Poll-30s encodes the Prometheus/CloudWatch scrape-interval property
  - RQ2: topology_only encodes L4 LB without health checks
  - RQ3: remote-only encodes naïve edge deployment with no data locality
- **Why not system-vs-system**: comparing "this controller vs. Kubernetes"
  would confound dozens of variables (language runtime, container runtime,
  network stack, tuning maturity). Varying one architectural property within
  the same infrastructure isolates the effect.
- **Each RQ holds the other pillars constant**: RQ1 varies telemetry but
  locks routing and locality; RQ2 varies backend policy but locks telemetry
  and locality; RQ3 varies locality but locks telemetry and routing.

### 4.3. Variables

**Independent variables:**

| Dimension | RQ | Conditions |
|---|---|---|
| Telemetry delivery cadence | RQ1 | Push (ZMQ), Poll-5s, Poll-12s, Poll-30s |
| Backend selection policy | RQ2 | topology_only, topology_host, topology_host_replica |
| Data locality strategy | RQ3 | Remote-only (Tier 0), cold-start full replica (Tier 2), reserved-standby (Tier 2 pre-provisioned) |

**Dependent variables:**

| Variable | Measurement | RQ |
|---|---|---|
| Reaction latency | `spawn_done_ts − breach_window_end` (segmented) | RQ1 |
| Service quality | p95/p99 latency, failure rate, completed requests per phase | RQ1, RQ2, RQ3 |
| Control overhead | Controller CPU%, RSS (MB), polling traffic volume | RQ1 |
| Load distribution | Request count per backend, CPU balance (old vs. new nodes) | RQ2 |
| Operating cost | Sync overhead, storage footprint, container count over time | RQ3 |

**Controlled variables (held constant across all conditions):**

- Workload shape: canonical `phases.json` (10 phases, ~28 min)
- Infrastructure sizing: `CLIENTS=8`, `DEVICES=600`, `NODES=100`
- Scaling thresholds: golden config (`current_state_integrated.env`)
- Aggregation window: 10 s
- Container images: same build for all runs
- WAN profile: `metro` (WAN_RTT_MS=10 unless testing WAN effect)

### 4.4. Measurement Instrumentation

**What to cover:**

- **Timing instrumentation**:
  - `consumed_at` timestamp paired with `window_end` in
    `resource_stats_debug.csv` — same-host `time.time()` pairing
  - `breach_detector.py` — independent observer that computes
    `degradation_score` using the same formula and thresholds as the
    controller, but fires on the first individual window (does not
    replicate the sliding window). This preserves methodological
    separation: the detector measures "when was overload visible in
    telemetry," not "when the controller decided to act."
  - Spawn event tracking: `elasticity_events.csv` (parsed from controller
    logs) provides `spawn_start_ts` and `spawn_done_ts`
- **Analysis toolchain** (all read-only, post-run):
  - `cli/timings.py` → staleness and reaction latency
  - `cli/overhead.py` → controller CPU/RAM
  - `cli_rq1_decision_quality.py` → scaling outcome description
  - `cli_simple_run.py` → latency, failure rate, node counts
  - `cli_phase_summary.py` → per-phase aggregates
  - `cli_simple_compare.py` → cross-run comparison
- **Overhead sampler** (`sample_controller_stats.py`): periodic `docker stats`
  on controller containers during experiments

### 4.5. Experiment Procedure

**What to cover:**

```
1. Pre-run: reboot cloud VM, rebuild images if code changed, verify configs
2. Setup: make setup_network → create_clients → setup_test_data
3. Run: make run_experiment with run-specific env vars
4. Post-run (on cloud VM):
   a. Parse controller logs → elasticity_events.csv
   b. Run all analysis CLIs
   c. Delete raw controller logs (already parsed)
5. Copy-back: scp reduced run folder to local machine
6. Cross-run: cli_simple_compare across all conditions
```

Reference the RQ1 experiment plan (`experiment_plan.md`) for full operational
details.

### 4.6. Repetition and Statistical Treatment

**What to cover:**

- **Runs per condition**: initially 1 per condition. If the two tightest
  conditions (e.g., Push and Poll-5s for RQ1) show ≤2 pp difference in
  overall failure rate, add a second replicate per condition. This treats
  replication as a conditional extension, not a fixed requirement.
- **Statistical tests**: Mann-Whitney U test for comparing reaction latency
  distributions across conditions (non-parametric — does not assume normal
  distribution). Effect size (Cliff's delta) reported alongside p-values.
- **Per-phase aggregation**: mean, median, p95, p99 for latency metrics;
  failure rate as proportion with Wilson confidence intervals.
- **Handling variance**: the RQ1 v2 replicate experience demonstrated that
  single runs can show spurious trends (e.g., monotonic degradation in v2
  that disappeared in replicates). Where n is small, results are reported
  with explicit caveats about statistical power.

### 4.7. Validity and Reliability

**Internal validity:**

| Threat | Mitigation |
|---|---|
| Confounding variables (different hardware, different workload) | Same infrastructure, same workload, same phases — only the independent variable changes |
| Measurement validity | `breach_detector.py` is independent of the controller; `consumed_at` and `window_end` use `time.time()` on the same host |
| Experimenter bias | Analysis CLIs are scripted, not manual; controller logs are machine-parsed |

**External validity (generalizability):**

| Limitation | Treatment |
|---|---|
| Two-network topology, fixed infrastructure | Findings characterize relationships between variables, not absolute performance numbers. Generalizability of *patterns*, not magnitudes. |
| Simulated workload, not real users | Standard in systems research. Workload design justified in §3.6. |
| MongoDB-specific Double-VIP model | The *principle* of cross-layer metadata generalizes; the specific mechanism may not. Separated in discussion. |

**Reliability (repeatability):**

| Threat | Mitigation |
|---|---|
| Stochastic system behavior | Repeat runs (see §4.6). Golden config proven stable across 15+ prior experiments. |
| Environmental drift | Pre-run host reboot; Docker containers provide environment isolation. |
| Clock skew | `time.time()` on same host; NTP adjustment over ~28 min run is negligible. |

---

## Chapter 5. Implementation

### 5.1. SDN Controller

**What to cover:**

- OS-Ken (Ryu) framework: event-driven, greenthread-based concurrency
- Three greenthreads:
  - Thread 1 (Fast Path / Routing): per-flow OpenFlow rule installation,
    VIP pool management, WSM cost evaluation
  - Thread 2 (Observer / Telemetry): telemetry source abstraction,
    degradation score evaluation, alert submission
  - Thread 3 (Slow Path / Elasticity): ElasticityManager with decoupled
    ComputeAlert and DataAlert handling, NodeAdder, scale-down evaluation
- Shared data structures: VIP pool, node registry, telemetry store
- Key algorithm: degradation score → threshold comparison → sliding window
  → alert → spawn. Include pseudo-code for the scaling decision path.
- Telemetry source abstraction: `ZmqTelemetrySource` and
  `PollingTelemetrySource` implementing a common interface

### 5.2. Edge Service and Storage

**What to cover:**

- Edge server: Python/Flask, serving three endpoints — `content_lookup`
  (`GET /content/<id>`), `feed_ranking` (`GET /feed/<user_id>`), and
  `service_pressure` (`GET /service_pressure`) — as described in §3.6
- MongoDB connection management: `VIP_DATA` routing, epoch recovery,
  `retryReads`, connection pooling
- Storage server: MongoDB instances managed by the controller, added/removed
  from replica sets via `rs.add()` / `rs.remove()`
- Docker container lifecycle: image build, startup, health checks, OVS
  wiring, drain, removal

### 5.3. Network Infrastructure

**What to cover:**

- OVS topology: two LANs + WAN bridge, emulated latency via `tc-netem`
- Double-VIP model implementation: ARP interception (controller replies to
  ARP requests for VIP addresses), per-flow DNAT/SNAT via OpenFlow
- Conntrack-based routing for VIP_DATA: eliminates stale-rule failures
  during storage churn
- WAN emulation profiles (`metro`, etc.)

### 5.4. Analysis Toolchain

**What to cover:**

- Telemetry collection: Aggregator (Python, ZMQ PUB/SUB + HTTP),
  `collect_resource_stats.py` (domain + debug + per-node CSVs)
- Post-run pipeline:
  - `parse_elasticity_logs.py` → `elasticity_events.csv`
  - `sample_controller_stats.py` → `controller_stats.csv`
  - Analysis CLIs (see §4.4) → PNGs + summary tables under
    `<run_dir>/analysis/`
- Read-only design: toolchain does not modify telemetry, scaling, or
  traffic generation

### 5.5. Implementation Validation

**What to cover (per guidelines — do NOT list code):**

- **Golden-config stability experiments**: 15+ runs under identical
  conditions to establish baseline variance. Key finding: overall failure
  rate variance reduced to ≤0.23% across replicates.
- **What stability validates**: the implementation is not introducing
  non-deterministic behavior from race conditions, resource leaks, or
  configuration drift. The experimental platform is stable enough that
  differences between conditions can be attributed to the independent
  variable.
- **Mechanism validation**: all four mechanisms (Tier 2 storage scale-out,
  Tier 1 selective sync, compute scale-out, conntrack routing) exercised
  and confirmed operational across the stability campaign.
- **Algorithm correctness**: pseudo-code for degradation score, threshold
  evaluation, and WSM cost functions is presented in §5.1. Correctness is
  demonstrated through stable behavior under controlled conditions, not
  through code inspection.

---

## Chapter 6. Results and Discussion

### 6.1. RQ1 — Telemetry Freshness and Delivery Cadence

**6.1.1. Information Age at Consumption (Confirmation)**

- Measurement: `consumed_at − window_end`
- Expected and observed: ~0 s for all four conditions (Push, Poll-5s,
  Poll-12s, Poll-30s)
- Interpretation: the HTTP cache works correctly — data is always fresh at
  consumption time regardless of polling interval. This confirms the delivery
  pipeline is healthy but does not differentiate between modes. The
  differentiating mechanism is missed windows (see 6.1.2).
- Figure: time-series per LAN, phase-shaded, horizontal dashed line at 0

**6.1.2. Reaction Latency (Core Evidence)**

- Measurement: `spawn_done_ts − breach_window_end`, segmented into breach
  detection and provisioning
- Comparison: Push vs. Poll-5s vs. Poll-12s vs. Poll-30s
- Key finding: breach-detection segment grows with polling interval.
  Provisioning segment is constant (~1–2 s) across all modes.
- Interpretation: the blind spot between polls directly translates into
  slower reaction. Push mode detects overload within ~10–20 s (sliding
  window + cooldown); Poll-30s adds up to 30 s on top.
- Figure: stacked bar per scaling event; per-phase summary table
- Statistical treatment: Mann-Whitney U across conditions, effect size

**6.1.3. Transient Service Quality**

- Measurement: p95/p99 latency, failure rate per workload phase
- Comparison across the four delivery cadence conditions
- Key finding: failure rate and tail latency increase with polling interval
  during demand-shift phases (`compute_spike`, `storage_stress`)
- Figures: `simple_run.png` per condition; `simple_compare_phase.png` across
  all four conditions

**6.1.4. Control-Plane Overhead**

- Measurement: controller CPU%, RSS (MB), polling traffic volume
- Comparison across delivery modes
- Key finding: overhead differences are modest. Push mode has a persistent
  ZMQ subscriber greenthread; poll mode has periodic HTTP GETs.
- Figure: CPU% + RSS(MB) time-series, phase-shaded

**6.1.5. Scaling Outcome Description**

- Measurement: per-phase table comparing breached windows (overload visible
  in telemetry) vs. spawns completed (controller action)
- No classification labels — the gap is the observable fact
- Interpretation: as the blind spot widens, spawns may arrive after the
  demand spike has passed (behavioral divergence)

**6.1.6. Statistical Treatment and Interpretation**

- Summary of statistical findings across all five measurements
- Whether the causal chain (polling interval ↑ → missed windows ↑ →
  breach-detection segment ↑ → service quality ↓) is supported
- If the evidence is inconclusive (e.g., high variance across replicates):
  bounded conclusions, explicitly stated

### 6.2. RQ2 — Metadata-Aware Backend Selection

**6.2.1. Compute-Plane Load Distribution**

- Measurement: request count per backend, CPU balance (old vs. new nodes)
  under each policy mode
- Comparison: `topology_only` vs. `topology_host` vs. `topology_host_replica`
- Interpretation: does adding host load (topology_host) improve distribution
  beyond topology alone? Does adding replica state (topology_host_replica)
  further improve it?

**6.2.2. Data-Plane Latency per Policy Mode**

- Measurement: $T_{dados}$ (data-access latency) under each policy mode
- Comparison across the three policy modes
- Interpretation: does replica-state awareness (avoiding lagged secondaries)
  produce measurable latency improvement for data-plane requests?

**6.2.3. Cross-Layer Metadata Benefit Quantification**

- Quantify the marginal benefit of each additional metadata layer
  (topology → topology_host → topology_host_replica)
- Discussion: where is the sharpest improvement? Is the benefit
  workload-dependent?

### 6.3. RQ3 — Data Locality Strategies

**6.3.1. Service Quality Under Each Locality Strategy**

- Measurement: p95/p99 latency, failure rate under remote-only (Tier 0),
  cold-start full replica (Tier 2), and reserved-standby strategies
- Comparison across strategies during cross-region demand phases
- Interpretation: does pre-positioning data eliminate the cold-start
  penalty? At what operating cost?

**6.3.2. Operating Cost**

- Measurement: sync overhead (replication traffic, CPU), storage footprint
  (disk usage per container), container count over time
- Comparison across locality strategies
- Interpretation: what is the resource cost of maintaining data locality?
  Is it justified by the service-quality benefit?

**6.3.3. Trade-Off Characterization**

- Service benefit vs. operating cost for each strategy
- Where is the Pareto frontier? Which strategy dominates under which
  workload conditions?

### 6.4. Cross-RQ Synthesis

**What to cover:**

- Across all three RQs: which orchestration dimension has the largest
  effect on service quality during demand shifts?
- Where are the sharpest trade-offs (e.g., data locality has large benefit
  but high operating cost; telemetry freshness has moderate benefit but
  near-zero cost)?
- What is negligible? (e.g., control-plane overhead differences across
  delivery modes)
- How do the three dimensions interact? (Qualitative discussion — formal
  interaction testing is future work.)
- What does this mean for an edge system designer? If you can only tune
  one thing, which should it be?

---

## Chapter 7. Conclusions and Future Work

### 7.1. Summary of Findings

**What to cover:**

- RQ1: Telemetry delivery cadence affects reaction latency through missed
  windows, not data staleness. The blind spot between polls translates into
  slower breach detection. The effect on service quality is [finding].
- RQ2: Cross-layer metadata improves backend selection by [finding] compared
  to single-layer baselines. The marginal benefit of replica-state awareness
  is [finding].
- RQ3: Data locality strategies present a trade-off: [finding] service
  benefit vs. [finding] operating cost. The Pareto-optimal strategy depends
  on [condition].
- Cross-RQ: The dimension with the largest effect is [finding].

### 7.2. Contributions Revisited

**What to cover:**

Restate the 5 contributions from §1.5, now with evidence from results.

### 7.3. Limitations

**What to cover:**

- Controlled testbed (two-network topology, fixed infrastructure) — patterns
  generalize, magnitudes do not
- Simulated workload — real user behavior may differ
- Single-window-size (10 s) — window size variation deferred to future work
- Tier 1 partial implementation — selective sync not experimentally validated
- Limited statistical power — n per condition is small; results are
  indicative, not conclusive at scale
- MongoDB-specific mechanisms (Double-VIP) — principle generalizes, mechanism
  may not
- Compound coordination delay not tested — each dimension varied
  independently; the compounded effect of full separation is future work

### 7.4. Future Work

**What to cover:**

- Compound coordination delay injection experiment (emulate separated control
  plane within unified codebase)
- Aggregation window size variation (freshness vs. noise trade-off)
- Tier 1 Selective Sync full implementation and experimental validation
- Larger-scale deployment (more networks, more nodes)
- Different database backends (test Double-VIP principle with other systems)
- Real-world workload traces instead of synthetic phases
- ML-driven threshold adaptation vs. static thresholds

---

## Mapping to Guidelines Requirements

| Guidelines requirement | Where covered |
|---|---|
| Project type stated | §1.4, §4.1 |
| Overall aim | §4.1 |
| Objectives formulated as achievable sub-goals | §1.2 (6 objectives), §4.1 (methods mapped) |
| Method identified per objective | §4.1 (table) |
| Literature analysis method (not just summary) | §2.1 |
| Implementation validation (not code listing) | §5.5 |
| Experimental design with independent/dependent/controlled variables | §4.2–4.5 |
| Statistical significance | §4.6, §6.1.6 |
| Validity (internal, external) | §4.7 |
| Reliability (repeatability) | §4.7 |
| Results with evidence | §6.1–6.4 |
| Descriptive tables (scaling outcome) | §6.1.5 |
| Limitations discussed | §7.3 |
| Future work | §7.4 |

---

## Source Documents for Each Chapter

| Chapter | Primary source documents |
|---|---|
| 1. Introduction | `thesis_proposal_aspects.txt`, `system_to_thesis_map_rq_v2.md` §1 |
| 2. Literature Review | `references.bib`, `some_guidelines.md` §Literature Analysis |
| 3. System Architecture | `docs/operation/system_mechanisms.md`, `docs/operation/system_scenarios.md`, `docs/operation/vip_routing/`, `docs/operation/elasticy_manager/`, `docs/operation/telemetry/`, `docs/operation/testing/testing_workloads.md` |
| 4. Methodology | `system_to_thesis_map_rq_v2.md`, `docs/research_questions/rq1.md`, `docs/operation/testing/experiment/rq1_evaluation/experiment_plan.md`, `docs/operation/testing/analysis_toolchain.md`, `some_guidelines.md` |
| 5. Implementation | `source/sdn_controller/`, `source/docker/`, `source/scripts/testing/`, `docs/operation/testing/implementation/` |
| 6. Results | `docs/operation/testing/experiment/rq1_evaluation/results.md`, `docs/operation/testing/experiment/stability/`, `source/scripts/testing/metrics/` |
| 7. Conclusions | Synthesis from Chapters 1–6 |

---

## Writing Order Recommendation

The chapters do not need to be written in document order. Recommended sequence:

1. **Chapter 3 (System Architecture)** — You know the system best. Write this first to solidify the description.
2. **Chapter 4 (Methodology)** — Largely exists in planning docs. Formalize.
3. **Chapter 5 (Implementation)** — Complements Chapter 3. The two can be written in parallel.
4. **Chapter 2 (Literature Review)** — Requires the most external reading. Start early, finish incrementally.
5. **Chapter 6 (Results)** — Depends on completed experiments. RQ1 section can be written now.
6. **Chapter 1 (Introduction)** — Write LAST, when you know exactly what the thesis argues.
7. **Chapter 7 (Conclusions)** — Write LAST, after results are complete.
