# Thesis Writing Guide — Structure and Content Plan

> **Status**: Working guide · **Date**: 2026-07-12
> **Purpose**: Defines the chapter structure, topic coverage per section, and
> mapping to the methodology guidelines (`some_guidelines.md`). Does NOT
> contain prose — only what goes where and why.
>
> **Argumentative backbone**: `tese/literature_review/global_literature_review.md`
> provides the four-domain survey, cross-dimensional gap matrix, and synthesis
> that Chapter 2 translates into thesis prose. The three-link RQ framing
> (detection→delivery→action) is defined in `system_to_thesis_map_rq_v2.md`.

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
and scaling are co-located in a single controller process with shared data
structures. This unification is the **experimental apparatus** — not the
hypothesis under test. It enables isolated variation of each link in the
detection→delivery→action chain.

**The evaluation**: a within-system experimental characterization of how
three links in the coordination chain — trigger quality (what is monitored),
telemetry freshness (how fast it arrives), and backend selection (how quickly
new capacity receives traffic) — each independently affect service quality
during demand shifts.

The six DSRM activities (Peffers et al., 2007-8) map to the thesis:

| DSR Activity | Thesis mapping |
|---|---|
| 1. Problem Identification | Coordination-gap observation; four-domain literature review identifies no platform isolates the detection→delivery→action chain |
| 2. Define Objectives | 6 proposal objectives + 3 research questions |
| 3. Design and Development | SDN controller, Double-VIP model, telemetry pipeline, tiered data gravity, Docker infrastructure |
| 4. Demonstration | 10-phase experimental workload, RQ3/RQ1/RQ2 runs, analysis toolchain |
| 5. Evaluation | Per-RQ measurements, statistical treatment (Mann-Whitney U, Cliff's delta), validity analysis |
| 6. Communication | This dissertation |

The contribution is **characterizing the coordination gap** that separated
architectures impose — quantifying the cumulative latency from overload onset
to traffic reaching new capacity across the detection, delivery, and action
links. The thesis does not claim that unification is superior to separation.

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

> **Note**: The RQ map v2 (§8) proposes an 8-chapter structure with separate
> per-RQ chapters (Ch5=RQ1, Ch6=RQ2, Ch7=RQ3, Ch8=Synthesis & Conclusion).
> This thesis consolidates all three RQs into a single Chapter 6 (Experimental
> Results) organized along the detection→delivery→action chain, with synthesis
> as §6.6. Consolidation keeps the chapter count guideline-compliant while
> preserving the causal narrative arc.

---

## Chapter 1. Introduction

### 1.1. Context, Motivation, and Problem Statement

**What to cover (structured as 6 paragraphs, each with a distinct job):**

- **¶1 — Edge computing + stateful services**: Edge computing brings services
  closer to users, reducing latency and backbone traffic. Many edge services
  are **stateful** — they depend on data co-located with compute. Introduces
  the Multi-Region Content Discovery Platform as the representative workload.
  Edge is resource-constrained, heterogeneous, and variable — lightweight
  containerized services are the natural deployment model.

- **¶2 — The conventional approach: three separate control loops**: In
  production edge/cloud platforms, three critical functions — **monitoring**
  (collecting service metrics), **traffic routing** (distributing requests
  across backends), and **auto-scaling** (adjusting infrastructure capacity)
  — are handled by separate components. Concrete examples: Kubernetes
  (Prometheus → AlertManager → HPA → kube-proxy), AWS (CloudWatch → ASG →
  ELB), OpenStack (Ceilometer → Heat → Neutron). Each component has its own
  reconciliation interval, its own view of system state, its own decision
  cadence. This separation is the **unexamined default** — no paper across
  four literature domains argues for or against it; it is simply how systems
  are built.

- **¶3 — The coordination gap**: Every handoff between these components
  introduces delay — not because any component is slow, but because they
  operate on independent cycles with no shared state. The accumulation of
  intervals (scrape period + alarm evaluation + sync period + scheduling +
  endpoint propagation) means traffic can take 30–120s to reach a new
  backend that booted in 10s. This is the **coordination gap**: three
  independent delays compounded across the detection→delivery→action chain.

- **¶4 — Separation is deliberate, not broken**: Acknowledges the benefits:
  fault isolation, independent scalability, modularity, ecosystem maturity.
  This thesis does **not** argue that separation is wrong or that co-location
  is universally superior. It asks a narrower question: *if these functions
  are co-located in a single decision point, what properties does this
  design exhibit?* And — critically — *can the coordination gap be isolated
  and measured by varying each link independently?*

- **¶5 — SDN as the enabling substrate**: Software-Defined Networking makes
  co-location possible. An OpenFlow controller (OS-Ken/Ryu) can consume
  telemetry directly (Thread 2), route traffic per-flow (Thread 1), and
  spawn/drain containers (Thread 3) — all from a single process with shared
  data structures. The SDN controller is the **experimental apparatus** that
  makes each link independently tunable; it is not the hypothesis under test.

- **¶6 — The three links and the gap this thesis fills**: Introduces the
  detection→delivery→action chain: **trigger quality** (does the system
  recognize overload?), **telemetry freshness** (how fast does the controller
  learn about it?), **backend selection** (how quickly does new capacity
  receive traffic?). States the research gap: no existing platform isolates
  these three links for independent experimental characterization. States
  what this thesis does: characterize each link and reconstruct the compound
  coordination tax.

- **¶7 — Central claim (thesis statement)**: A single, clear paragraph that
  states what the thesis argues. Use the central claim from
  `system_to_thesis_map_rq_v2.md` §1 as the template: *"This thesis
  experimentally examines three links in the detection→delivery→action chain
  of cross-layer SDN orchestration — trigger quality, telemetry freshness,
  and backend selection — characterizing how each independently affects
  service quality during demand shifts in stateful edge services."* The
  SDN controller is the experimental apparatus; the contribution is
  characterizing the coordination gap, not adjudicating between
  architectural paradigms.

- **Honest scope statement**: A brief paragraph (can be part of ¶7 or
  immediately after) that explicitly states what the thesis does **not**
  claim. From the RQ map v2 §3.3 and global lit review §6.2:
  - Does not claim SDN is superior to Kubernetes, NFV MANO, or any
    specific platform.
  - Does not claim the coordination gap matters equally for all workloads.
  - Does not claim the approach scales to large deployments (controlled
    two-network topology).
  - Does not claim the Double-VIP model generalizes beyond MongoDB
    replica sets.
  This is critical for academic defensibility — it preempts the critique
  of "you didn't compare against Kubernetes at scale" by making clear that
  was never the claim.

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

The three-link RQ set from `system_to_thesis_map_rq_v2.md`. The three RQs
form a causal chain — detection → delivery → action — where each link is
varied independently while the other two are held constant:

| Link | RQ | Core Question |
|---|---|---|
| **Detection** | RQ3 | For stateful edge services where I/O latency often degrades before CPU saturates, does a latency-aware multi-dimensional degradation score detect overload earlier and with fewer false positives than a CPU-only threshold? |
| **Delivery** | RQ1 | How does telemetry delivery cadence — aggregator-paced push versus controller-paced polling at three intervals — affect reaction latency and transient service quality during demand shifts? |
| **Action** | RQ2 | How does the timing of routing-plane awareness relative to backend spawn — at spawn time (warm lease, in-process) versus at discovery time (slow-start ramp, simulating a separated LB) versus no ramp-up — affect load redistribution quality during scale-up events? |

Each RQ paragraph should state: (a) the core question, (b) which link in the
chain it isolates, (c) the conditions being compared, and (d) what
architectural property the baseline encodes:

- **RQ3 baseline**: CPU-only threshold (w_cpu=1.0, w_lat=0.0) — the industry
  default applied to a stateful edge workload where I/O latency is the
  dominant failure mode.
- **RQ1 baseline**: Poll-30s (2 of 3 telemetry windows missed) — the
  Prometheus scrape interval / CloudWatch metric period that separated
  monitoring systems impose.
- **RQ2 baseline**: `topology_slowstart` — backend invisible until telemetry
  discovery (0–10 s after spawn), then graduated ramp. Encodes the
  separated-LB property: the load balancer does not know the backend exists
  until health checks pass.

Data placement strategies (Tier 0/1/2) are discussed in the architecture
(Chapter 3) and synthesis (Chapter 6) as infrastructure that the unified
controller enables, but their experimental evaluation is deferred to future
work.

### 1.4. Research Methodology

**What to cover (1–2 pages):**

- Project type: Design Science Research Methodology (DSRM) (Peffers et al.,
  2007-8), grounded in the Design Science Research paradigm (Hevner et al.,
  2004). The artifact is the SDN-orchestrated edge platform; the evaluation
  is the within-system experimental characterization.
- Experimental design: within-system, single-variable manipulation. Vary one
  link in the detection→delivery→action chain while holding the other two
  constant. Same hardware, same workload, same infrastructure — only the
  variable under test changes.
- Comparison strategy: baselines encode architectural properties of separated
  systems (CPU-only threshold, poll-30s, discovery-time slow-start), not
  specific competing products.
- Reference to Chapter~5 for full methodological detail.

### 1.5. Main Contributions of this Dissertation

**What to cover:**

1. Experimental characterization of the coordination gap across three links
   in the detection→delivery→action chain — trigger quality, telemetry
   freshness, and backend selection — each independently varied and measured
   under controlled demand shifts.
2. An SDN-based experimental platform where monitoring, routing, and scaling
   are co-located in a single controller process with shared data structures,
   enabling isolated variation of each link.
3. Empirical evidence quantifying the relationship between trigger
   composition (latency-aware degradation score vs. CPU-only threshold)
   and overload detection quality in stateful edge services (RQ3).
4. Empirical evidence quantifying the relationship between telemetry delivery
   cadence (push vs. poll at multiple intervals) and reaction latency,
   including segmentation into breach-detection and provisioning
   components (RQ1).
5. First experimental quantification of the spawn-to-discovery coordination
   gap in backend selection — measuring the load-redistribution penalty of
   discovery-time awareness (slow-start) versus spawn-time awareness (warm
   lease) versus no ramp-up (RQ2).

### 1.6. Dissertation Structure

Brief paragraph outlining the 7 chapters.

---

## Chapter 2. Background and Related Work

> **Argumentative backbone**: `tese/literature_review/global_literature_review.md`
> provides the complete synthesis — the four-domain survey, the cross-dimensional
> gap matrix, and the argument that the coordination gap is the unexamined
> default. This chapter translates that synthesis into thesis prose.

### 2.1. Review Methodology

**What to cover (2–3 paragraphs):**

- **Databases searched**: IEEE Xplore, ACM Digital Library, Scopus, Google Scholar
- **Search terms and Boolean combinations**
- **Time range**: 2015–2025
- **Four domains surveyed**: Auto Scaling, Load Balancing on SDN, Monitoring &
  Telemetry, Resource Orchestration on SDN
- **Inclusion/exclusion criteria**
- **Numbers**: total found → after screening → final set

### 2.2. The Unexamined Default: Three-Layer Separation

**What to cover:**

- Every major architecture for edge service orchestration — Kubernetes, NFV
  MANO frameworks (OSM, ONAP), MEC platforms — separates monitoring, routing,
  and scaling into independent components.
- Table showing the three functions across Kubernetes, NFV MANO, and MEC:
  each uses different components for monitoring, routing, and scaling.
- This separation is **not presented as a design choice** in the literature.
  It is simply how systems are built. No paper argues *for* separation or
  *against* co-location — it is the unexamined default.
- The consequence: a **coordination gap** — accumulated latency between
  overload onset and traffic reaching new capacity. This gap has been
  *documented* (Wang et al., SDNFV architecture), *observed as a side effect*
  (Pierro & Ullah, K8s HPA evaluation), and *called for at the network layer*
  (Yaseen, 2025) — but never isolated, measured, or varied as an independent
  experimental variable.

### 2.3. Auto Scaling

**What to cover (domain survey):**

- What the domain studies: *when* and *by how much* to scale. Sophisticated
  algorithms — multi-metric hybrid frameworks (HyMetricScaler, Feng et al.),
  ML-based forecasting (Toka et al., 2021, IEEE TNSM), topology-aware deep
  learning (De Silva et al., 2026), predictive analytics with real-time
  correction (PAHPA, Xiao et al., 2026).
- What it systematically ignores: monitoring freshness, LB discovery timing,
  and trigger composition are treated as givens. None are varied
  experimentally.
- Strongest gap evidence: Ghorab et al. (2020) call for joint treatment of
  LB and auto-scaling — the closest any paper comes to recognizing the
  coordination gap, yet only goes two layers deep and keeps components
  separate. Pierro & Ullah observe throughput *decreasing* with more pods
  due to orchestration overhead — they observe the symptom but treat it as
  a side effect, not an object of study.
- **Finding**: No auto-scaling paper varies monitoring freshness, LB discovery
  timing, or trigger composition as independent experimental variables.

### 2.4. Load Balancing on SDN

**What to cover (domain survey):**

- What the domain studies: algorithm design — *which* backend receives each
  request. Thirty metrics taxonomised across 41 papers (Alrammahi & Bhaya,
  2022): throughput, latency, jitter, concurrency, energy, packet loss.
  Recent surveys covering 120+ papers (Belgaum et al., 2020; Mawale &
  Wankhade, 2025).
- What it systematically ignores: not one of the 30 taxonomised metrics
  concerns data freshness, collection cadence, or information staleness.
  The word "periodically" appears in paper after paper — "the controller
  periodically gathers data" (Caiza & Campoverde, 2024) — without any paper
  asking what happens if "periodically" is 5 s versus 30 s.
- Strongest gap evidence: Caiza & Campoverde (2024) propose WSM-based
  multi-resource LB — the same algorithmic approach this thesis uses — but
  describe metric collection only as occurring "periodically," burying the
  research question in an adverb. Zhang & Guo (2014) used the same
  "periodically detects" a decade earlier with no progress.
- **Finding**: No SDN load balancing paper varies metric collection cadence
  as an experimental variable, compares push versus pull telemetry delivery,
  or evaluates LB under a changing backend pool.

### 2.5. Monitoring & Telemetry

**What to cover (domain survey):**

- What the domain studies: monitoring as an end in itself — optimising scrape
  intervals to save cross-cluster bandwidth (AdapPF, Huang & Pierre, 2023),
  aggregating per-server metrics (Acala, Huang & Pierre, 2024), enriching
  the metric set (Zhou & Yong, 2024), complementing predictions with
  real-time correction (PAHPA, Xiao et al., 2026).
- What it systematically ignores: the consumer of telemetry — the scaling or
  routing system that acts on the metrics — is always out of scope. The
  monitoring→decision interface is a one-way data pipe.
- Strongest gap evidence: AdapPF (Huang & Pierre, 2023) is the only paper
  across all four domains that varies scrape interval and measures an effect
  on a downstream decision — but frames it as a bandwidth-saving mechanism,
  not as a decision-quality dimension. Yaseen (2025) concludes that "modern
  networks demand monitoring frameworks that are not only scalable and
  real-time but also tightly integrated with network control and automation"
  — a call this thesis answers.
- **Finding**: No monitoring paper varies telemetry delivery cadence as a
  spectrum, measures the downstream effect on both scaling reaction latency
  and load redistribution quality, or co-locates monitoring with the scaling
  and routing systems it feeds.

### 2.6. Resource Orchestration on SDN

**What to cover (domain survey):**

- What the domain studies: resource allocation in pure SDN (Zehra & Shah,
  2017), QoS-aware InterCloud management (Aliyu et al., 2017), SDN-based
  edge resource optimisation (Nain et al., 2024 — 29-page systematic review),
  industrial IoT orchestration (Okwuibe et al., 2020), cross-layer cognitive
  orchestration (Rafiee et al., 2024).
- What it systematically ignores: SDN is always the *network* layer — it
  "facilitates" edge computing but is never the orchestration platform itself.
  Compute is Kubernetes' job; monitoring is InfluxDB's job. The separation
  is architectural, not accidental.
- Strongest gap evidence: Okwuibe et al. (2020) deploy the closest technology
  stack to this thesis — Docker + SDN + edge + MongoDB — but orchestration
  is split across three separate systems. Nain et al. (2024) explicitly note
  that prior work "does not consider other important aspects of load
  balancing, resource allocation, and computational offloading" together.
  Breitbach et al. (2019) study n-replication data placement (mirroring
  Tier 0→1→2) but at the application layer with no SDN integration.
- **Finding**: No paper co-locates monitoring, routing, and scaling in a
  single SDN controller process. SDN is always the network layer, never the
  orchestration platform.

### 2.7. Summary and Research Gaps

**What to cover:**

- **The cross-dimensional gap matrix**: present a table showing every paper
  reviewed across all four domains against four gap dimensions: monitoring
  freshness varied?, LB discovery timing varied?, trigger composition
  varied?, components co-located?. The matrix shows this thesis is the only
  row where all four dimensions are addressed. (Source:
  `global_literature_review.md` §3.)

- **Why the gap matters**: three independently documented but never-connected
  observations: (1) Wang et al. document the spawn-to-LB-inclusion delay but
  accept it as an implementation detail; (2) Pierro & Ullah observe throughput
  degradation from orchestration overhead but treat it as a side effect;
  (3) Yaseen (2025) calls for monitoring integrated with control and
  automation but does not operationalise it.

- **The compound coordination tax**: in a fully separated architecture with
  CPU-only trigger, the total coordination latency is unbounded (trigger may
  never fire) or approximately 84 s (projected 43 s delivery penalty +
  measured 31 s action penalty + 10 s provisioning). The 31 s action penalty
  is empirically confirmed (RQ2, n=9); the 43 s delivery penalty awaits RQ1
  experimental confirmation.

- **The gap this thesis fills**: no existing work isolates the
  detection→delivery→action chain for independent experimental
  characterization. This thesis does exactly that, using the SDN controller
  as the experimental apparatus.

> **Note on chapter structure**: The RQ map v2 (§8) proposes 8 chapters with
> separate per-RQ chapters. This thesis consolidates to 7 chapters with all
> three RQs in Chapter 6, organized along the detection→delivery→action
> chain (RQ3→RQ1→RQ2→Synthesis). The RQ map's proposed per-RQ chapter content
> maps directly to §6.1–§6.3 of this guide.

---

## Chapter 3. Architecture and Design of Proposed Solution for Edge Services

### 3.1. Design Requirements

**What to cover:**

- **Cross-layer orchestration**: monitoring, routing, and scaling as three
  links of a single control chain — the detection→delivery→action pipeline
  — co-located in one process. This is the architectural precondition for
  isolated variation of each link.
- **Single control point, shared data structures**: Thread 1 (routing),
  Thread 2 (telemetry), Thread 3 (elasticity) — no propagation delay between
  them because there are no separate components.
- **Tiered data gravity**: Tier 0 (remote only, zero local infrastructure),
  Tier 1 (selective sync, bounded working set), Tier 2 (full local replica).
  Graduated cost/benefit: pay infrastructure cost only when sustained demand
  justifies it.
- **Decoupled compute and data scaling**: ComputeAlert vs. DataAlert respond
  to different latency signals ($T_{proc}$ vs. $T_{dados}$). A CPU spike
  spawns a web server, not a database replica.
- **Domain-agnostic observability**: the controller observes latency and
  resource metrics — any containerized request/response service produces
  these signals. The telemetry pipeline works identically for edge servers
  and MongoDB sidecars.

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
- Three backend selection policy modes: `topology_host` (no ramp-up,
  cold-start WSM), `topology_slowstart` (invisible until discovery, graduated
  ramp), `topology_lifecycle` (spawn-time warm lease)

#### Data

**What to cover:**

- Data scaling design: $T_{dados}$ threshold; Tier 0 → Tier 2 transitions;
  MongoDB replica set management via rs.add()/rs.remove()
- Tier 1 Selective Sync Node: design description (honest scope — partial
  implementation, experimental validation deferred to future work)
- Scale-down: two-phase cooperative drain, cooldown-gated evaluation

### 3.4. Monitoring and Decision Engine

**What to cover:**

- Telemetry pipeline design: per-request instrumentation → ZMQ PUSH →
  Aggregator → 10 s summaries → ZMQ PUB / HTTP cache → Controller
- Push (ZMQ) and poll (HTTP) delivery modes
- Degradation score formula: weighted combination of CPU saturation (40%)
  and processing latency (60%). The latency component dominates because,
  in stateful edge services, MongoDB I/O drives request latency — $T_{proc}$
  rises before CPU saturates. CPU-only threshold (w_cpu=1.0, w_lat=0.0) is
  the industry-default alternative.
- Sliding window evaluation; alert submission to priority queue

### 3.5. Control Workflow

**What to cover:**

- End-to-end control flow: telemetry arrival → degradation score evaluation →
  threshold comparison → sliding window → alert → spawn/drain → VIP
  registration → OpenFlow rule update
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
- Three backend selection policy modes implemented via
  `BACKEND_SELECTION_POLICY` env var: warm lease (`topology_lifecycle`),
  slow-start ramp (`topology_slowstart`), no ramp-up (`topology_host`)

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
- Degradation score with configurable weights via env vars
  (`SCALEUP_W_CPU`, `SCALEUP_W_T_PROC`); ElasticityManager
- Key algorithm pseudo-code: degradation score → threshold → sliding window →
  alert → spawn pipeline

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
- Overall aim: characterize the coordination gap by varying each link in the
  detection→delivery→action chain independently — trigger quality (RQ3),
  telemetry freshness (RQ1), and backend selection (RQ2) — and measuring
  how each affects service quality during demand shifts.
- Six DSRM activities mapped to thesis chapters.
- DSR artifact types: constructs (VIP, WSM, degradation score), models
  (three-thread architecture), methods (telemetry pipeline, elasticity
  algorithm), instantiations (working prototype).

### 5.2. Evaluation Scenarios

**What to cover:**

- Within-system, single-variable manipulation. Vary one link in the
  detection→delivery→action chain while holding the other two constant.
- Comparison strategy: baselines encode architectural properties of separated
  systems, not specific competing products.
- Why not system-vs-system comparison (would confound dozens of variables).
- Each RQ holds the other two links constant.

### 5.3. Performance Metrics

**What to cover:**

Reaction latency, service quality (p95/p99, failure rate), control overhead
(CPU%, RSS), load distribution, detection accuracy (false positive/negative
rate for RQ3). Independent breach detector for methodological separation.

**Independent variables (detection→delivery→action chain):**

| Link | RQ | Conditions |
|---|---|---|
| Detection — Trigger Quality | RQ3 | degradation_score (w_cpu=0.40, w_lat=0.60), cpu_only (w_cpu=1.00, w_lat=0.00) |
| Delivery — Telemetry Freshness | RQ1 | Push (ZMQ), Poll-5s, Poll-12s, Poll-30s |
| Action — Backend Selection | RQ2 | topology_host (no ramp-up), topology_slowstart (discovery-time ramp), topology_lifecycle (spawn-time warm lease) |

**Dependent variables:**

| Variable | Measurement | RQ |
|---|---|---|
| Reaction latency | `spawn_done_ts − breach_window_end` (segmented: breach-detection + provisioning) | RQ1, RQ3 |
| Service quality | p95/p99 latency, failure rate, completed requests per phase | RQ1, RQ2, RQ3 |
| Control overhead | Controller CPU%, RSS (MB), polling traffic volume | RQ1 |
| Load redistribution | Request count per backend, time-to-equilibrium, ramp shape | RQ2 |
| Detection accuracy | False positive rate (spawns during baseline), false negative rate (missed spawns during overload) | RQ3 |

**Controlled variables (held constant across all conditions):**

- Workload shape: canonical `phases.json` (10 phases, ~28 min)
- Infrastructure sizing: `CLIENTS=8`, `DEVICES=600`, `NODES=100`
- Scaling thresholds: golden config (`current_state_integrated.env`)
- Aggregation window: 10 s
- Container images: same build for all runs
- WAN profile: `metro` (WAN_RTT_MS=10 unless testing WAN effect)
- Per-RQ locks: RQ1 holds golden trigger + topology_lifecycle; RQ2 holds push telemetry + golden trigger; RQ3 holds push telemetry + topology_lifecycle

### 5.4. Experimental Procedure with Results Statistical Analysis

**What to cover:**

- Procedure: pre-run → setup → run → post-run → copy-back → cross-run comparison
- Measurement instrumentation — timing (`consumed_at`, breach_detector.py),
  analysis toolchain (CLIs → PNGs + CSVs), independent breach detector
- Repetition: n=3 per condition; RANDOM_SEED=42 for identical workload;
  `cleanup.sh -r` for identical initial state
- Statistical tests: Mann-Whitney U, Cliff's delta, per-phase aggregation
- Validity and reliability (internal, external, repeatability)



## Chapter 6. Experimental Results

> **Order follows the detection→delivery→action chain**: RQ3 (detection) →
> RQ1 (delivery) → RQ2 (action) → Synthesis (compound coordination gap).

### 6.1. Trigger Quality — Overload Detection (RQ3)

**What to cover:**

- Breach detection time: `spawn_start_ts − breach_window_end` compared
  across degradation_score vs. cpu_only modes.
- False positive rate: spawns during baseline phase / total spawns.
- False negative rate: spawns missed during stress phases relative to
  degradation_score baseline.
- Service quality during transitions: per-phase p50/p95 latency, timeout
  rate, completed request volume.
- **Key finding (projected)**: CPU-only may never fire at realistic edge
  CPU levels (2–8%) for I/O-bound stateful services — CPU-based autoscaling
  is structurally incapable of responding to storage-driven degradation.

### 6.2. Telemetry Freshness — Delivery Cadence (RQ1)

**What to cover:**

- Reaction latency across delivery cadences (Push, Poll-5s, Poll-12s,
  Poll-30s). Breach-detection segment vs. provisioning segment.
- Decision staleness: `consumed_at − window_end` (confirms all modes
  sub-second — the mechanism is missed windows, not data staleness).
- Service quality (p95/p99, failure rate) per cadence.
- Control-plane overhead per mode.
- Scaling outcome description: per-phase table comparing breached windows
  vs. spawns completed.

### 6.3. Backend Selection — Routing Awareness (RQ2)

**What to cover:**

- Load redistribution time: `spawn_done_ts` → equilibrium load share
  (±10% of per-backend mean) across three modes.
- Transition-window service quality: p95/p99 latency and failure rate in
  the compute_spike phase after scale-up events.
- Per-mode redistribution profile: request share over time for the new
  backend, showing ramp shape (none vs. graduated vs. warm lease).
- **Key finding (empirically confirmed, n=9)**: discovery-time slow-start
  imposes a measured ~31 s action penalty — new capacity sits idle for one
  full telemetry window.

### 6.4. Network Performance

**What to cover:**

- Control-plane overhead (CPU%, RSS); cross-LAN latency
- WAN emulation effects; telemetry delivery overhead

### 6.5. Scalability Analysis

**What to cover:**

- Behavior under increasing load; scaling outcome description
  (breached windows vs. spawns completed); mechanism activation patterns

### 6.6. Discussion — The Compound Coordination Gap

**What to cover (synthesis across RQ3→RQ1→RQ2):**

- Reconstruct the compound coordination tax from the three RQ results:
  | Architecture | Detection | Delivery | Action | Provisioning | Total |
  |---|---|---|---|---|---|
  | Fully separated | CPU-only: never or late | Poll-30s: +~43 s (projected) | Slowstart: +31 s (measured) | ~10 s | ~84 s or unbounded |
  | Fully unified | Degradation score: early | Push: ~0 s | Lifecycle: ~0 s | ~10 s | ~10 s + early detection lead |
- The coordination tax — unnecessary latency imposed by three-layer separation
  — is approximately 74 s (43 s delivery + 31 s action) under the conditions
  tested, or unbounded if the CPU-only trigger never fires.
- This is the first experimental quantification of the phenomenon that Wang
  et al. documented, Pierro & Ullah observed as a side effect, and Yaseen
  (2025) called for at the network layer.
- Which link matters most? Sharpest trade-offs? What's negligible?
- Implications for edge system designers.
- Data placement strategies (Tier 0/1/2) as infrastructure context: the
  unified architecture enables tiered data gravity; experimental
  characterization of data locality trade-offs is deferred to future work.



## Chapter 7. Conclusions and Future Work

### 7.1. Summary of Findings

**What to cover:**

- **RQ3 (Trigger Quality)**: A latency-aware degradation score detects
  I/O-bound overload that a CPU-only threshold misses entirely in stateful
  edge services. [Finding from results.]
- **RQ1 (Telemetry Freshness)**: Telemetry delivery cadence affects reaction
  latency through missed windows, not data staleness. The blind spot between
  polls translates into slower breach detection. The effect on service
  quality is [finding].
- **RQ2 (Backend Selection)**: The spawn-to-discovery coordination gap is
  measurable: discovery-time slow-start imposes a ~31 s action penalty
  (empirically confirmed). Spawn-time warm leases eliminate this gap.
- **Cross-RQ synthesis**: In a fully separated architecture, the compound
  coordination tax is approximately 74 s (or unbounded with CPU-only trigger).
  In the unified architecture, it is approximately 10 s (provisioning only).
  The thesis is the first to isolate and quantify each component of this tax.

### 7.2. Contributions Revisited

**What to cover:**

Restate the 5 contributions from §1.5, now with evidence from results.

### 7.3. Limitations

**What to cover:**

- Controlled testbed (two-network topology, fixed infrastructure) — patterns
  generalize, magnitudes do not
- Simulated workload — real user behavior may differ
- Single-window-size (10 s) — window size variation deferred to future work
- Tier 1 Selective Sync partial implementation — not experimentally validated
- Limited statistical power — n=3 per condition; results are indicative,
  not conclusive at scale
- RQ1 and RQ3 results are projected/designed — experimental confirmation
  pending (RQ2 is empirically confirmed, n=9)
- MongoDB-specific mechanisms (Double-VIP) — principle generalizes, mechanism
  may not
- Compound coordination delay tested per-link — the compounded effect of
  full separation synthesized from individual RQ results, not tested as a
  single experiment

### 7.4. Future Work

**What to cover:**

- Compound coordination delay injection experiment (emulate full separation
  with configurable delays at both handoff points simultaneously)
- Aggregation window size variation (freshness vs. noise trade-off)
- Tier 1 Selective Sync full implementation and experimental validation
- Data locality experimental characterization (Tier 0 vs. Tier 1 vs. Tier 2
  cold vs. Tier 2 warm — designed, deferred from RQ3 scope)
- Larger-scale deployment (more networks, more nodes)
- Different database backends (test Double-VIP principle with other systems)
- Real-world workload traces instead of synthetic phases
- ML-driven threshold adaptation vs. static thresholds

---

## Mapping to Guidelines Requirements

| Guidelines requirement | Where covered |
|---|---|
| Project type stated (DSR) | §1.4, §5.1 |
| Overall aim | §5.1 |
| Objectives formulated as achievable sub-goals | §1.2 (6 objectives), §5.1 (methods mapped) |
| Method identified per objective | §5.1 (table) |
| Literature analysis method (not just summary) | §2.1 |
| Implementation validation (not code listing) | §4.5 |
| Experimental design with independent/dependent/controlled variables | §5.2–5.4 |
| Statistical significance | §5.4 |
| Validity (internal, external) | §5.4 |
| Reliability (repeatability) | §5.4 |
| Results with evidence | §6.1–6.6 |
| Descriptive tables (scaling outcome, gap matrix) | §6.2, §2.7 |
| Limitations discussed | §7.3 |
| Future work | §7.4 |

---

## Source Documents for Each Chapter

| Chapter | Primary source documents |
|---|---|
| 1. Introduction | `thesis_proposal_aspects.txt`, `system_to_thesis_map_rq_v2.md` |
| 2. Background and Related Work | `tese/literature_review/global_literature_review.md`, per-domain READMEs, `references.bib`, `some_guidelines.md` |
| 3. Architecture and Design | `docs/operation/` (all subfolders) |
| 4. Implementation | `source/sdn_controller/`, `source/docker/`, `source/scripts/testing/` |
| 5. Evaluation Methodology | `system_to_thesis_map_rq_v2.md`, `docs/research_questions/rq1.md`, `docs/research_questions/rq2.md`, `docs/operation/testing/experiment/`, `docs/operation/testing/analysis_toolchain.md`, `some_guidelines.md` |
| 6. Experimental Results | `docs/operation/testing/experiment/rq*/results.md`, `source/scripts/testing/metrics/` |
| 7. Conclusions and Future Work | Synthesis from Chapters 1–6 |

---

## Writing Order Recommendation

The chapters do not need to be written in document order. Recommended sequence:

1. **Chapter 3 (Architecture and Design)** — You know the system best. Start here.
2. **Chapter 4 (Implementation)** — Complements Chapter 3. Write in parallel.
3. **Chapter 2 (Background and Related Work)** — The `global_literature_review.md` provides the complete argumentative backbone. Translate into prose.
4. **Chapter 5 (Evaluation Methodology)** — Largely exists in planning docs and the v2 RQ map. Formalize.
5. **Chapter 6 (Experimental Results)** — RQ2 data ready (n=9). RQ1 and RQ3 pending evaluation. Write RQ2 section first.
6. **Chapter 1 (Introduction)** — Write LAST, once all findings are clear.
7. **Chapter 7 (Conclusions and Future Work)** — Write LAST.

---

## Quick Checks

- [ ] Title: *A Cross-Layer SDN Orchestration Architecture for Stateful Edge Services: Design and Experimental Characterization*
- [ ] Methodology: DSRM (Peffers et al., 2007-8) + DSR paradigm (Hevner et al., 2004)
- [ ] No IoT language anywhere — Multi-Region Content Discovery Platform
- [ ] Three RQs form a detection→delivery→action chain (RQ3→RQ1→RQ2)
- [ ] RQ3 = Trigger Quality (degradation_score vs. cpu_only), not Data Locality
- [ ] RQ2 baselines = topology_host / topology_slowstart / topology_lifecycle
- [ ] Data locality discussed in architecture + synthesis, experimental eval deferred
- [ ] Each chapter has `% TODO` comments in `main.tex`
- [ ] Chapter 6 results order: RQ3 → RQ1 → RQ2 → Synthesis
