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

The thesis title: *"A Cross-Layer SDN Orchestration Architecture for Stateful
Edge Services: Design and Experimental Characterization."*

The core concepts from the proposal that guide the framing:

- Edge computing — services deployed closer to users
- Programmable infrastructure (SDN) — network-level control
- Containerized stateful services — lightweight, portable, with data
- Metadata-driven decision-making — spatio-temporal data popularity
- Document-oriented storage — flexible schema for heterogeneous metadata

---

## Thesis Type: Design Science Research Methodology (DSRM)

This thesis follows the **Design Science Research Methodology (DSRM)**
(Peffers et al., 2007-8), grounded in the Design Science Research paradigm
(Hevner et al., 2004). DSRM is a six-activity process that creates innovative
artifacts and evaluates their utility.

**The artifact**: an SDN-orchestrated edge platform where monitoring, routing,
and scaling are co-located in a single controller, with three independently
tunable dimensions (telemetry freshness, backend selection policy, data
locality strategy).

**The evaluation**: a within-system experimental characterization of how each
dimension independently affects service quality during demand shifts.

The six DSRM activities (Peffers et al., 2007-8) map to the thesis:

| DSR Activity | Thesis mapping |
|---|---|
| 1. Problem Identification | Coordination-gap observation; literature review identifies no platform isolates these three dimensions |
| 2. Define Objectives | 6 proposal objectives + 3 research questions |
| 3. Design and Development | SDN controller, Double-VIP model, telemetry pipeline, tiered data gravity, Docker infrastructure |
| 4. Demonstration | 10-phase experimental workload, RQ1/RQ2/RQ3 runs, analysis toolchain |
| 5. Evaluation | 5 measurements per RQ, statistical treatment (Mann-Whitney U), validity analysis |
| 6. Communication | This dissertation |

The contribution is **characterizing the trade-off surface** across three
dimensions — not proving that the unified design is superior to separated
architectures.

---

## Chapter Structure

```
Chapter 1. Introduction
Chapter 2. Background and Related Work
Chapter 3. Architecture and Design of Proposed Solution for Edge Services
Chapter 4. Implementation of Proposed Solution
Chapter 5. Evaluation Methodology
Chapter 6. Experimental Results
Chapter 7. Conclusions and Future Work
```

7 chapters. Minimal, guideline-compliant.

---

## Chapter 1. Introduction

### 1.1. Context, Motivation, and Problem Statement

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

### 1.4. Research Methodology

**What to cover (1–2 pages):**

- Project type: Design Science Research Methodology (DSRM) (Peffers et al.,
  2007-8), grounded in the Design Science Research paradigm (Hevner et al.,
  2004). The artifact is the SDN-orchestrated edge platform; the evaluation
  is the within-system experimental characterization.
- Experimental design: within-system, single-variable manipulation. Vary one
  dimension while holding the other two constant. Same hardware, same workload,
  same infrastructure — only the variable under test changes.
- Comparison strategy: baselines encode architectural properties of separated
  systems (polling at 30s, topology-only routing, remote-only data), not
  specific competing products.
- Reference to Chapter~5 for full methodological detail.

### 1.5. Main Contributions of this Dissertation

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

### 1.6. Dissertation Structure

Brief paragraph outlining the 7 chapters.

---

## Chapter 2. Background and Related Work

### 2.1. Review Methodology

**What to cover (2–3 paragraphs):**

- **Databases searched**: IEEE Xplore, ACM Digital Library, Scopus, Google Scholar
- **Search terms and Boolean combinations**
- **Time range**: 2015–2025
- **Inclusion/exclusion criteria**
- **Numbers**: total found → after screening → final set

### 2.2. Edge Computing Architectures

**What to cover:**

- Edge vs. cloud vs. fog: definitions, latency tiers, resource constraints
- Containerization at the edge: Docker, lightweight virtualization
- Stateful vs. stateless edge services: why data locality matters

### 2.3. Resource Allocation in Edge Computing

**What to cover:**

- Compute and data resource allocation strategies
- Metadata-driven approaches to resource management
- Spatio-temporal data popularity and its role in allocation decisions

### 2.4. Elasticity and Auto-Scaling Mechanisms

**What to cover:**

- Taxonomy: threshold-based, predictive/proactive, ML-driven, reactive
- Industry systems: Kubernetes HPA/VPA, AWS Auto Scaling Groups, OpenStack Heat
- Control-loop cadences in production systems
- Separation benefits: fault isolation, independent scaling, modularity

### 2.5. Service Placement and Orchestration

**What to cover:**

- Service placement algorithms and orchestration frameworks
- Data gravity concepts and tiered storage at the edge
- Cache hierarchies and edge-local data strategies
- Document-oriented databases (MongoDB): schema-less model, replica set API,
  connection pooling, horizontal read scaling

### 2.6. Software-Defined Networking for Edge Systems

**What to cover:**

- SDN principles: control/data plane separation, OpenFlow, programmable forwarding
- SDN controllers: Ryu/OS-Ken, ONOS, OpenDaylight
- SDN for traffic engineering: per-flow routing, dynamic rule installation
- SDN at the edge: challenges and opportunities
- Double-VIP concepts for L3 traffic-plane separation

### 2.7. Summary and Research Gaps

**What to cover:**

- Each domain treats monitoring, routing, and data management as separate
  concerns managed by independent control loops. This separation is a
  deliberate architectural choice with documented benefits.
- No existing work examines these three dimensions as **independently
  tunable levers within a single control point** where they share state
  and can be varied one at a time while the others are held constant.
- The consequence: the **relative importance** of each dimension is unknown.
- This thesis builds the platform that makes them independently testable
  and characterizes the trade-off surface that emerges.

---

## Chapter 3. Architecture and Design of Proposed Solution for Edge Services

### 3.1. Design Requirements

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

- Component diagram: two edge networks (LAN1, LAN2) + WAN link; OVS switches,
  edge servers, storage servers, clients; SDN controller with 3 greenthreads;
  Double-VIP model; Docker containers; telemetry pipeline
- Interaction flows between components

### 3.3. Distributed Elastic Allocation of Resources

#### Services

**What to cover:**

- Compute scaling design: $T_{proc}$ threshold; edge server containers;
  VIP_SERVER pool registration; WSM cost functions for compute plane
- Policy modes: topology_only, topology_host, topology_host_replica

#### Data

**What to cover:**

- Data scaling design: $T_{dados}$ threshold; Tier 0 → Tier 2 transitions;
  MongoDB replica set management via rs.add()/rs.remove()
- Tier 1 Selective Sync Node: design description (honest scope — partial
  implementation, full validation deferred to future work)
- Scale-down: two-phase cooperative drain, cooldown-gated evaluation

### 3.4. Monitoring and Decision Engine

**What to cover:**

- Telemetry pipeline design: per-request instrumentation → ZMQ PUSH →
  Aggregator → 10 s summaries → ZMQ PUB / HTTP cache → Controller
- Push (ZMQ) and poll (HTTP) delivery modes
- Degradation score formula; dynamic threshold with diminishing increments
  for storage, peer relief for compute
- Sliding window evaluation; alert submission to priority queue

### 3.5. Control Workflow

**What to cover:**

- End-to-end control flow: telemetry arrival → evaluation → alert →
  spawn/drain → VIP registration → OpenFlow rule update
- Three-thread model: Thread 1 (routing), Thread 2 (telemetry), Thread 3
  (elasticity) — shared data structures, no propagation delay
- Double-VIP ARP interception + DNAT/SNAT; L3 traffic-plane separation

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

## Chapter 4. Implementation of Proposed Solution

### 4.1. Experimental Infrastructure

**What to cover:**

- Docker containers; OVS topology (two LANs + WAN bridge, tc-netem)
- WAN emulation profiles; cloud VM host

### 4.2. Distributed Elastic Allocation of Resources

#### Services

**What to cover:**

- Edge server: Python/Flask; container lifecycle (build, start, health check,
  OVS wiring, drain, removal); VIP_SERVER registration

#### Data

**What to cover:**

- MongoDB replica sets; programmatic rs.add()/rs.remove()
- VIP_DATA routing; epoch recovery; retryReads; connection pooling
- Storage container lifecycle; conntrack-based routing for VIP_DATA

### 4.3. Monitoring and Decision Engine

**What to cover:**

- Aggregator (ZMQ PUB/SUB + HTTP cache); collect_resource_stats.py
  (domain + debug + per-node CSVs)
- Telemetry source abstraction (ZmqTelemetrySource, PollingTelemetrySource)
- ElasticityManager; key algorithm pseudo-code

### 4.4. Control Workflow

**What to cover:**

- OS-Ken/Ryu controller; 3 greenthreads; shared data structures
- Double-VIP ARP interception + DNAT/SNAT via OpenFlow
- Degradation score → threshold → sliding window → alert → spawn pipeline

### 4.5. Implementation Validation

**What to cover (per guidelines — do NOT list code):**

- Golden-config stability experiments (15+ runs, variance ≤0.23%)
- Mechanism validation (Tier 2, Tier 1, compute, conntrack)
- Algorithm correctness via stable behavior, not code inspection



## Chapter 5. Evaluation Methodology

### 5.1. Experimental Objectives

**What to cover:**

- Project type: **Design Science Research Methodology (DSRM)** (Peffers
  et al., 2007-8), grounded in the Design Science Research paradigm
  (Hevner et al., 2004).
- Overall aim: characterize how telemetry freshness, backend selection,
  and data locality each independently affect service quality during
  demand shifts.
- Six DSRM activities mapped to thesis chapters.
- DSR artifact types: constructs (VIP, WSM, degradation score), models
  (three-thread architecture), methods (telemetry pipeline, elasticity
  algorithm), instantiations (working prototype).

### 5.2. Evaluation Scenarios

**What to cover:**

- Within-system, single-variable manipulation
- Comparison strategy: baselines encode architectural properties, not products
- Why not system-vs-system comparison
- Each RQ holds the other pillars constant

### 5.3. Performance Metrics

**What to cover:**

Reaction latency, service quality (p95/p99, failure rate), control overhead
(CPU%, RSS), load distribution, operating cost. Independent breach detector
for methodological separation.

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

### 5.4. Experimental Procedure with Results Statistical Analysis

**What to cover:**

- Procedure: pre-run → setup → run → post-run → copy-back → cross-run comparison
- Measurement instrumentation — timing (`consumed_at`, breach_detector.py),
  analysis toolchain (CLIs → PNGs + CSVs), independent breach detector
- Repetition: runs per condition, conditional replication
- Statistical tests: Mann-Whitney U, Cliff's delta, per-phase aggregation
- Validity and reliability (internal, external, repeatability)



## Chapter 6. Experimental Results

### 6.1. Resource Allocation Efficiency

**What to cover:**

- Does the system deploy resources only when justified?
- Storage and compute node counts across phases. Tier transitions observed.

### 6.2. Elastic Scaling Performance

**What to cover:**

- RQ1 — Reaction latency across delivery cadences (Push, Poll-5s, Poll-12s,
  Poll-30s). Breach-detection segment vs. provisioning segment.
- Service quality (p95/p99, failure rate) per cadence.
- Control-plane overhead per mode.

### 6.3. Service Placement Effectiveness

**What to cover:**

- RQ2 — Load distribution and latency per backend selection policy
  (topology_only, topology_host, topology_host_replica)
- RQ3 — Service quality vs. operating cost per locality strategy
  (remote-only, cold-start, reserved-standby)

### 6.4. Network Performance

**What to cover:**

- Control-plane overhead (CPU%, RSS); cross-LAN latency
- WAN emulation effects; telemetry delivery overhead

### 6.5. Scalability Analysis

**What to cover:**

- Behavior under increasing load; scaling outcome description
  (breached windows vs. spawns completed); mechanism activation patterns

### 6.6. Discussion

**What to cover:**

- Cross-RQ synthesis. Which dimension matters most?
- Sharpest trade-offs? What's negligible?
- Implications for edge system designers.



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
| Project type stated (DSR) | §1.4, §4.1 |
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
| 1. Introduction | `thesis_proposal_aspects.txt`, `system_to_thesis_map_rq_v2.md` |
| 2. Background and Related Work | `references.bib`, `some_guidelines.md` |
| 3. Architecture and Design | `docs/operation/` (all subfolders) |
| 4. Implementation | `source/sdn_controller/`, `source/docker/`, `source/scripts/testing/` |
| 5. Evaluation Methodology | `system_to_thesis_map_rq_v2.md`, `docs/research_questions/rq1.md`, `docs/operation/testing/experiment/`, `docs/operation/testing/analysis_toolchain.md`, `some_guidelines.md` |
| 6. Experimental Results | `docs/operation/testing/experiment/rq1_evaluation/results.md`, `source/scripts/testing/metrics/` |
| 7. Conclusions and Future Work | Synthesis from Chapters 1–6 |

---

## Writing Order Recommendation

The chapters do not need to be written in document order. Recommended sequence:

1. **Chapter 3 (Architecture and Design)** — You know the system best. Start here.
2. **Chapter 4 (Implementation)** — Complements Chapter 3. Write in parallel.
3. **Chapter 5 (Evaluation Methodology)** — Largely exists in planning docs. Formalize.
4. **Chapter 6 (Experimental Results)** — RQ1 data ready.
5. **Chapter 2 (Background and Related Work)** — Chip away throughout.
6. **Chapter 1 (Introduction)** — Write LAST.
7. **Chapter 7 (Conclusions and Future Work)** — Write LAST.
