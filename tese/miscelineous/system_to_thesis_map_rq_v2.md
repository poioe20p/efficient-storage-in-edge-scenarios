# System-to-Thesis RQ Map v2 — Cross-Layer SDN Orchestration

> **Status:** Reframed based on discussions (2026-06-06). This supersedes the original `system_to_thesis_map_rq_advanced.md` with a three-pillar framing: Telemetry Freshness, Backend Selection, and Data Locality — unified by an SDN cross-layer control plane.

The main purpose of this note is to answer five practical questions:

1. What are the strongest working research questions for the thesis?
2. Why are these questions academically defensible?
3. What concepts and comparison axes does each question involve?
4. What additional development is required before each question can be answered rigorously?
5. What measurements and scenarios are required to evaluate each question?

---

## 1. Thesis Framing

### Thesis Type & Contribution

This thesis is an **experimental examination** of cross-layer orchestration
for stateful edge services, conducted through a centralized SDN control plane
deployed over a controlled two-network edge topology. The SDN controller
collapses three traditionally separated concerns — telemetry collection, traffic
steering, and infrastructure scaling — into a single process with shared data
structures. This unification is not the hypothesis under test; it is the
**experimental apparatus** that makes the examination possible. By holding the
controller constant, each orchestration dimension can be varied independently
while the others are locked, isolating cause and effect within a single
infrastructure.

The contribution is **characterizing the trade-off surface** across three
dimensions of cross-layer orchestration — telemetry freshness, backend
selection policy, and data-locality strategy — and measuring how each
independently affects service quality during demand shifts. The thesis does
not claim that unifying these concerns is superior to separated architectures;
it accepts the latency reduction from collapsing handoffs as a given property
of the design and focuses instead on what can be learned by examining each
dimension through a cross-layer control point.

### Central Claim

> This thesis experimentally examines three dimensions of cross-layer SDN
> orchestration — **telemetry freshness**, **backend selection**, and
> **data locality** — characterizing how each independently affects service
> quality during demand shifts in stateful edge services. The SDN control
> plane serves as the experimental platform that enables isolated variation
> of each dimension, not as the object of comparison itself.

### The Three Pillars

| Pillar                        | RQ       | Core Question                                                                               |
| ----------------------------- | -------- | ------------------------------------------------------------------------------------------- |
| **Telemetry Freshness** | RQ1      | How does telemetry delivery cadence affect control quality during demand shifts?            |
| **Backend Selection**   | **RQ2** | **How does cross-layer metadata improve backend selection beyond L4 and L4+ baselines?**   |
| **Data Locality**       | RQ3      | How do data-locality readiness strategies trade off service benefit against operating cost? |

### Why SDN Is the Unifying Substrate

In conventional architectures, these three concerns are handled by separate components:

- **Telemetry collection** — a monitoring system (Prometheus, CloudWatch)
- **Load balancing** — a traffic manager (HAProxy, NGINX, ELB, kube-proxy)
- **Auto-scaling** — an infrastructure scaler (K8s HPA, AWS ASG, OpenStack Heat)

Each handoff between these components introduces a **coordination gap**: the monitoring system scrapes on a fixed interval, the alarm system evaluates thresholds, the auto-scaler provisions infrastructure, and the load balancer eventually discovers the new backend — all through independent control loops with no shared state.

Industry examples of this separation:

| System     | Monitoring                 | Routing               | Scaling                        | Coordination Model                                                                                                    |
| ---------- | -------------------------- | --------------------- | ------------------------------ | --------------------------------------------------------------------------------------------------------------------- |
| Kubernetes | Prometheus → AlertManager | kube-proxy / iptables | HPA / VPA / Cluster Autoscaler | Three independent control loops with different reconciliation intervals                                               |
| AWS        | CloudWatch                 | ELB / Route53         | ASG                            | Separate services with independent APIs; target group propagation delay is documented                                 |
| OpenStack  | Telemetry services         | Networking services   | Orchestration services         | Loosely coupled components communicating via message bus; no shared state between monitoring, networking, and compute |

In the proposed architecture, the SDN controller (OS-Ken/Ryu) consumes telemetry directly (Thread 2), routes traffic per-flow via OpenFlow (Thread 1), and mutates infrastructure by spawning/draining containers (Thread 3) — all from a single process with shared data structures. There are no handoff delays between components because there are no separate components.

**The thesis does not claim SDN is universally better.** It characterizes *what the unification enables and what it costs*, under controlled edge conditions. A negative or nuanced result is still a valid contribution: knowing that the coordination gap matters only above a certain demand threshold is useful knowledge.

### Relationship to the Thesis Proposal

While the initial proposal emphasized metadata-driven scaling as the central contribution, architecture development revealed that telemetry freshness and backend selection are equally critical dimensions of cross-layer orchestration. The three-pillar investigation presented here **operationalizes** the proposal's high-level goals ("coordinate auto-scaling based on meta-information") by decomposing the problem into evaluable, independently testable dimensions. The proposal's emphasis on spatio-temporal data popularity is preserved in RQ2 (cross-layer backend selection) and RQ3 (data-locality readiness strategies).

---

## 2. RQ Selection Principles

The chosen RQs should satisfy all of the following conditions:

1. They must ask about a **systems trade-off or control problem**, not merely restate a feature.
2. They must be **empirically answerable** with measurable variables and controlled baselines.
3. They must **isolate the main independent variable** instead of changing several architectural dimensions at once.
4. They must remain faithful to the implemented system unless explicitly marked as requiring further development.
5. They must support a clear methodology chapter and a defensible results chapter.
6. Each RQ's baselines must encode the **architectural alternative** of separated control loops — so that the comparison is not against a specific competing product but against the *property* those products share (stale state, single-layer visibility, or absent data locality).

For this reason, the recommended RQ set below separates:

- **telemetry freshness** from **delivery mechanism** (RQ1)
- **single-layer** from **cross-layer backend selection** (RQ2)
- **cold-start capacity** from **reserved or pre-synchronized capacity** (RQ3)

---

## 3. How SDN Ties the Three Pillars Together

This section establishes *why* SDN is load-bearing in the architecture — not merely the tool that happened to be used.

### 3.1 The Coordination Gap Problem

In a separated architecture, every handoff between components introduces delay:

```text
Separated (Kubernetes-style):
  Prometheus scrapes (every 10s)
    → AlertManager evaluates (delay: up to scrape interval)
      → HPA updates replica count (delay: sync period)
        → Scheduler places pod (delay: scheduling latency)
          → kube-proxy updates iptables (delay: endpoint slice propagation)
            → Traffic reaches new pod

  Total coordination latency: often 30–120s, even though the pod booted in 10s.

Unified (SDN controller):
  Telemetry greenthread receives ZMQ summary
    → (same process) evaluates thresholds, posts Alert to priority queue
      → ElasticityManager spawns container, registers MAC in VIP pool
        → Thread 1 reads VIP pool (same data structure), includes new backend in WSM cost
          → Next TCP SYN steered to new backend via OpenFlow rule

  Total coordination latency: container boot time + ~1s for OVS wiring.
```

### 3.2 What SDN Specifically Enables

| Architectural Property                               | Why SDN Is Necessary                                                                                                                                                                                                                                                                                                            | What It Enables for the RQs                                                                                                                                                                                                                                            |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Double-VIP model**                           | MongoDB drivers discover replica-set topology and connect to all members directly. The controller must prevent this for tiered data placement — the driver must see a single stable address (`VIP_DATA_N1`) regardless of which physical node serves it. ARP interception + per-flow OpenFlow DNAT/SNAT achieves this at L3. | RQ2: backend selection policy is enforced at the network layer, not in application code. RQ3: tier transitions are transparent to the edge server — it never knows which physical node backs the VIP.                                                                 |
| **Per-flow routing with cross-layer metadata** | Traditional L4 LBs (HAProxy, NGINX stream) cannot consume replica-state telemetry (replication lag, member state). OpenFlow enables per-TCP-connection steering based on WSM cost functions that incorporate host load AND replica state AND topology.                                                                          | RQ2: the`topology_host_replica` policy mode has no equivalent in separated architectures — this is the experimental condition that tests whether cross-layer metadata produces measurable improvement beyond the `topology_only` and `topology_host` baselines. |
| **Same-process routing and scaling**           | Thread 1 (routing) and Thread 3 (scaling) share the VIP pool data structure. When Thread 3 adds or drains a backend, Thread 1 sees the change immediately — no API call, no eventual consistency, no propagation delay.                                                                                                        | RQ1 & RQ3: the reaction latency measurement reflects only telemetry freshness and infrastructure provisioning time — not an additional control-plane propagation gap.                                                                                                 |
| **L3 traffic-plane separation**                | `VIP_SERVER` (compute) and `VIP_DATA_N*` (data) are separate virtual IPs with separate WSM cost functions and separate backend pools. This separation is enforced by OpenFlow rules at the network layer, not by application configuration that can be misconfigured.                                                       | RQ2: compute-plane and data-plane selection policies can be evaluated independently under the same infrastructure.                                                                                                                                                     |
| **Topology as a first-class input**            | The controller builds the network topology during setup (which MAC is in which LAN, hop distances). This feeds directly into routing cost functions and placement decisions — the controller knows*where* every resource is, not just its health status.                                                                     | RQ2:`topology_only` and `topology_host` policies use topology as the baseline layer. RQ3: cross-LAN placement decisions depend on topology awareness.                                                                                                              |

### 3.3 Honest Scope

What this thesis does **not** claim:

- That SDN is strictly superior to all alternative architectures
- That the coordination gap matters equally for all workloads (it may be negligible for steady-state, low-churn scenarios)
- That the approach scales to large deployments (the testbed is a controlled two-network topology with a fixed set of infrastructure containers serving simulated workloads)
- That the Double-VIP model generalizes beyond MongoDB replica sets

What it **does** claim:

- That telemetry freshness, metadata awareness, and data locality each independently affect service quality during demand shifts
- That SDN provides a unified substrate for varying each dimension while holding the others constant, enabling controlled within-system comparison
- That characterizing the trade-off surface for each dimension — even with negative or nuanced results — is a valid contribution

---

## 4. Comparison Strategy

### 4.1 What We Compare Against

The thesis does **not** compare against a specific competing product (Kubernetes, OpenStack, etc.). Such a comparison would be invalid: different hardware, different scale, different workload, different optimization maturity.

Instead, each RQ's baselines encode the **architectural property** that separated systems share. The comparison isolates one variable at a time within the same infrastructure:

| RQ            | Baseline Condition                            | Separated-System Property It Encodes                                                                                                |
| ------------- | --------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| **RQ1** | Polling at 12 s / 30 s intervals              | Stale monitoring → delayed decisions (Prometheus scrape interval → AlertManager → HPA; CloudWatch metric period → Alarm → ASG) |
| **RQ2** | `topology_only` / `topology_host`         | Single-layer visibility: L4 LB (haproxy leastconn) or L4+ LB with host health checks — no replica-state awareness                  |
| **RQ3** | Remote serving only / cold-start full replica | No data locality (naïve edge deployment) or reactive-only elasticity (ASG-style cold-start, pay full sync cost on every trigger)   |

### 4.2 Why This Is Methodologically Valid

- **Same hardware, same workload, same infrastructure** — only the variable under test changes
- **Each RQ holds the other pillars constant** — RQ1 varies telemetry but locks routing and scaling policy; RQ2 varies selection policy but locks telemetry and scaling; RQ3 varies locality strategy but locks telemetry and routing
- **The baselines are real operating modes of the system**, not simulated strawmen — the system genuinely runs in polling mode, topology-only mode, and remote-only mode
- **Isolation of causation** — a system-vs-system comparison (e.g., "my controller vs. Kubernetes") would confound dozens of variables (language runtime, container runtime, network stack, tuning). Varying one architectural property within the same system isolates the effect

### 4.3 Future Work: Compound Coordination Delay Injection

A cross-cutting synthesis experiment beyond the scope of the current evaluation could inject configurable delay at both handoff points simultaneously (telemetry→routing and alert→action), characterizing the *compounded* cost of full separation. This would directly test whether the coordination gap — the architectural property that motivated the unified design — produces measurable degradation beyond what any single-dimension delay produces. This experiment is deferred to future work because it requires emulating a separated control plane within the unified codebase, which is a non-trivial instrumentation task. The three RQs in this thesis test each dimension independently; the compound interaction remains an open question.

---

## 5. Advanced Working RQ Set

---

## RQ1. Telemetry Freshness and Delivery Cadence

> **RQ1.** How does telemetry delivery cadence affect controller decision staleness, reaction latency, and transient service quality during demand shifts in a stateful edge system?

### Why RQ1 Is a Strong RQ

This RQ isolates the **delivery mechanism** as a control-plane design choice.
The system aggregates telemetry into summaries over a fixed 10 s window. The
question is whether the controller should receive these summaries via
aggregator-paced push (ZMQ at window close) or controller-paced poll (HTTP at
a configurable interval), and what **blind spot** each mechanism introduces
between telemetry windows.

Polling at intervals slower than the window (e.g., 30 s) encodes the
architectural property of separated monitoring systems: the controller
**misses intermediate windows** — it sees 1 of every 3 telemetry snapshots.
This is the same property that Prometheus scrape intervals or CloudWatch
metric periods impose on separated architectures: the monitoring system
has no visibility into what happened between scrapes. Polling faster than
the window (e.g., 5 s) exercises the deduplication path and measures whether
over-polling wastes resources without benefit — every window is caught, but
half the polls return a duplicate already seen.

The aggregation window size is held constant at 10 s. Varying window size
(1 s, 5 s, 30 s) to test the freshness-versus-noise tradeoff is deferred to
future work — it requires making the window configurable in the aggregator
and scaling policy, which is a separate development axis.

### Concepts Involved in RQ1

- push versus poll delivery cadence
- blind spot between telemetry windows
- reaction latency (breach visible → node operational)
- transient service quality across workload phases
- control-plane overhead (CPU, RAM, polling traffic)
- scaling outcome description (overload vs. controller action)

### Why RQ1 Matches the Current Architecture

The controller consumes telemetry through an abstract source boundary
(`telemetry/source.py`) with two implementations:

- `ZmqTelemetrySource` — push: aggregator publishes summaries at window
  close via ZMQ PUB/SUB
- `PollingTelemetrySource` — poll: controller fetches the latest cached
  summary from the aggregator's HTTP endpoint at a configurable interval

The aggregator caches each completed summary in memory and exposes it via
a lightweight HTTP handler (`GET /latest_summary`). The polling source
deduplicates by `window_end` — repeated polls that return the same summary
are ignored. The summary schema and raw telemetry emission are identical
across both delivery modes.

### Development Required for RQ1

Completed:

1. Polling telemetry source on the controller side (`polling_source.py`).
2. HTTP summary cache on the aggregator (`_SummaryHandler` on port 5558).
3. `consumed_at` timing instrumentation in the collector (same-row
   `time.time()` pairing by `(network_id, window_end)`, with row buffering
   for late coordinator frames in poll mode).
4. Controller overhead sampler (`sample_controller_stats.py`) — periodic
   `docker stats` on both controller containers.

Not required:

- Varying the aggregation window size (held constant at 10 s).
- Storing raw edge telemetry in a database.
- Replacing the aggregator with a database-only architecture.

### Measurements Required for RQ1

1. **Decision staleness** (information age at consumption)
   `consumed_at − window_end` per telemetry row. Both timestamps use
   `time.time()` on the same host. **All modes: sub-second.** Push mode
   receives the summary at window close via ZMQ. Poll mode retrieves the
   freshest cached summary from the aggregator's HTTP endpoint — the cache
   is always updated at window close, so the retrieved data is fresh
   regardless of polling interval. This measurement confirms the delivery
   pipeline works correctly; it does not differentiate between modes.

   The mechanism that actually delays the controller's response is not
   data staleness at consumption time but **missed windows** — the
   controller simply does not see telemetry between polls. The
   breach-detection segment of reaction latency (measurement 2) captures
   this blind-spot penalty: the controller cannot act on a breach window
   it has not yet received.
2. **Reaction latency** — the **output** that matters for the thesis
   `spawn_done_ts − breach_window_end`. The breach window is identified by
   independently computing `degradation_score` from telemetry data (same
   formula and thresholds the controller uses). The endpoint is
   `spawn_done` (container online, VIP wired) — not `spawn_start` (spawn
   initiated but not yet routing traffic). Segmented into:

   - Breach detection: `spawn_start_ts − breach_window_end`
   - Provisioning: `spawn_done_ts − spawn_start_ts`
3. **Transient service quality**
   p95/p99 latency, failure rate, and completed requests compared across
   workload phases (baseline, compute_spike, demand_drop, etc.). Per-phase
   aggregates from the existing analysis toolchain (`cli_simple_run`,
   `cli_phase_summary`) capture how service quality changes when the
   workload transitions between phases.
4. **Control-plane overhead**
   Controller CPU% and RSS (MB) sampled every 5 s via `docker stats` on
   both `osken` and `osken_2` containers. Polling traffic volume estimated
   from `POLL_INTERVAL_S` and summary size (~2–10 KB per poll).
5. **Scaling outcome description**
   A per-phase descriptive table comparing what was visible in telemetry
   against what the controller did. For each workload phase: total telemetry
   windows, how many showed overload (degradation_score >= threshold), peak
   degradation score observed, and how many spawns the controller initiated
   and completed. No classification labels — the gap between breached-windows
   and completed-spawns is the observable fact (the sliding window mechanism
   means a window may breach without triggering a spawn, which is expected
   behavior). The thesis interprets this gap alongside reaction latency to
   answer: as the blind spot widens, does the controller still respond
   adequately?

### Evaluation Design for RQ1

All conditions use a 10 s aggregation window. Delivery cadence is the
independent variable:

| Condition          | Delivery            | Blind spot                                                 | What it tests                                                                                            |
| ------------------ | ------------------- | ---------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| **Push**     | ZMQ at window close | None — sees every window                                  | Baseline: no coordination gap                                                                            |
| **Poll-5s**  | HTTP every 5 s      | None — catches every window (dedup filters ~50% of polls) | Faster than window: exercises dedup, no blind spot                                                       |
| **Poll-12s** | HTTP every 12 s     | ~1 of 6 windows missed (desync headroom)                   | Fair comparison: polls just after window close, minor blind spot                                         |
| **Poll-30s** | HTTP every 30 s     | ~2 of 3 windows missed                                     | Blind monitoring: controller sees 1 of 3 telemetry snapshots. Encodes the CloudWatch/Prometheus property |

**Why Poll-12s.** The aggregator and controller are independent processes
with independent clocks. At exactly 10 s polling, a poll could land just
before the window boundary and read the old summary. Poll-12s (window +
headroom) ensures the controller always polls after a new summary is
available. Poll-5s achieves the same goal by polling fast enough that every
window is caught regardless of drift. Both strategies are included so the
evaluation can compare them.

Hold constant:

- Workload shape (canonical `phases.json`; the shorter `phases_rq1_verify.json` used during instrumentation verification)
- Scaling thresholds (`current_state_integrated.env` golden config; `rq1_verify.env` used during verification with shortened cooldown)
- Routing policy
- Summary schema
- Aggregation window (10 s)

Vary only:

- Delivery mode and polling interval

---

## RQ2. Metadata-Aware Backend Selection

> **RQ2.** To what extent does metadata-aware backend selection improve load distribution and request handling compared with topology-only and topology-plus-host-load selection in a stateful edge system?

### Why RQ2 Is a Strong RQ

This is a strong RQ because it asks about **backend selection**, not about elasticity or infrastructure size. It tests whether adding richer state to the selection logic improves outcomes beyond simpler policies.

It is also strong because it can be evaluated while holding the underlying substrate constant:

- same controllers
- same VIP model
- same traffic generator
- same infrastructure
- different selection policies only

### Concepts Involved in RQ2

- topology-aware routing
- host-load-aware routing
- replica-state-aware routing
- cross-layer optimization
- compute plane versus data plane
- leading indicators for steering
- stateful backend admissibility and freshness

### Architectural Framing: What Each Policy Mode Represents

The policy modes are not arbitrary — they form a spectrum from single-layer to cross-layer visibility, each corresponding to what a different class of real-world load balancer can achieve:

| Policy Mode               | Allowed Metadata                             | Equivalent Real-World System                                               | Limitation                                                                                     |
| ------------------------- | -------------------------------------------- | -------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `topology_only`         | Hop distance only                            | DNS geo-routing, anycast, simple L4 LB with no health checks               | No load awareness — routes to nearest regardless of congestion                                |
| `topology_host`         | Hops + CPU, RAM, request count / connections | HAProxy/NGINX with least-connections + custom host health checks           | Host-aware but no replica-state visibility — cannot avoid routing reads to lagged secondaries |
| `topology_host_replica` | All above + replication lag, member state    | **Your cross-layer WSM** — no equivalent in separated architectures | Requires SDN to consume and act on replica-state telemetry at per-flow granularity             |

### Why RQ2 Matches the Current Architecture

The current routing layer already uses a weighted cost model in:

- [`../../source/sdn_controller/vip_routing.py`](../../source/sdn_controller/vip_routing.py)

The key point, however, is that a rigorous RQ2 cannot be answered by merely changing numeric weights. It needs **explicit policy modes** that define which metadata each policy is allowed to use.

This question should be evaluated separately on the two current traffic planes:

1. **Compute plane**: `VIP_SERVER`
2. **Data plane**: `VIP_DATA_N*`

### Development Required for RQ2

Required for rigorous comparison:

1. Add explicit backend-selection policy modes.
2. Hold all non-policy behavior constant.
3. Define clearly which metadata each mode may use.
4. Evaluate compute and data planes separately, even if the thesis keeps a unified RQ.

Recommended policy family:

1. `topology_only`
   - allowed inputs: hop distance only
2. `topology_host`
   - allowed inputs: hops, CPU, RAM, request count / connections
3. `topology_host_replica`
   - allowed inputs: hops, host load, and replica-state metadata such as replication lag

Instrumentation that would help:

- structured trace logging of candidate scores and exclusion reasons
- per-policy request assignment counts
- explicit tagging of compute-plane versus data-plane decisions in analysis

### Measurements Required for RQ2

Compute-plane measurements:

1. p95/p99 request latency
2. failure rate
3. request distribution across servers
4. Jain's fairness index over compute CPU usage
5. spillover frequency to peer-LAN backends

Data-plane measurements:

1. p95/p99 DB-side latency contribution
2. failure rate under data stress
3. fraction of reads routed to lagged or stressed backends
4. hop count and cross-LAN routing frequency
5. storage CPU balance and connection balance across eligible nodes

Shared measurements:

1. routing churn or instability
2. number of policy-induced bad choices under constructed stress cases
3. per-phase latency and fairness rather than only whole-run averages

### Evaluation Design for RQ2

Hold constant:

- telemetry acquisition mode
- scaling behavior
- workload
- flow timeouts

Vary only:

- policy mode

Important methodological note:

RQ2 should not be answered with a single aggregate statement such as "cross-layer is better." It should show **where** the richer policy helps:

- under compute-heavy imbalance
- under storage lag or replica-state asymmetry
- under cross-LAN spillover opportunities

### Main Validity Threats for RQ2

- weight tuning can masquerade as algorithmic improvement if policy modes are not explicit
- low backend diversity can make differences too small to interpret
- mixing compute and data-plane effects in one aggregate metric can hide the actual cause

---

## RQ3. Partial Replication vs. Cold and Reserved Capacity

> **RQ3.** Under shifting cross-region demand, how do remote serving, selective partial replication, cold-start full replica placement, and reserved-standby full replica promotion trade off service benefit, activation overhead, and lifecycle complexity?

### Why RQ3 Is a Strong RQ

This is the strongest version of the elasticity-and-locality question because it does **not** reduce elasticity to generic horizontal scaling. Instead, it compares several strategies with different readiness and cost profiles:

1. do nothing and serve remotely
2. place only the hot subset locally
3. provision a full local replica reactively
4. keep a pre-synchronized standby that can be admitted quickly

The strategies are not arbitrary features of the system — they form a **monotonic spectrum** from zero-infrastructure/no-readiness to pre-provisioned/high-readiness. The research contribution is characterizing where on this spectrum edge demand regimes justify the cost.

### Readiness-Cost Spectrum

| Strategy                                              | Readiness                          | Idle Cost                                 | Activation Cost                             | Cloud/Industry Analogue                                            |
| ----------------------------------------------------- | ---------------------------------- | ----------------------------------------- | ------------------------------------------- | ------------------------------------------------------------------ |
| **Remote serving only** (Tier 0)                | Immediate (already serving)        | Zero                                      | Zero (but high per-request latency)         | No CDN, direct origin fetch                                        |
| **Selective partial replication** (Tier 1)      | Medium (hot-set sync needed)       | Low (bounded cache via TTL)               | Medium (Change Stream setup + initial sync) | CDN-style partial caching with invalidation                        |
| **Cold-start full replica** (Tier 2 cold)       | Low (full sync from scratch)       | Zero                                      | High (full initial sync, oplog catch-up)    | ASG cold-start; pay full provisioning cost on every trigger        |
| **Reserved-standby full replica** (Tier 2 warm) | High (pre-synced, needs promotion) | Medium (idle CPU/RAM/replication traffic) | Low (admission only)                        | Reserved instances / provisioned concurrency / pre-warmed K8s pods |

### Concepts Involved in RQ3

- cross-region demand shifts
- data locality
- selective partial replication
- cold-start elasticity
- reserved capacity / warm elasticity
- sync tax
- time-to-benefit
- reservation tax
- lifecycle complexity and cleanup debt

### Strategy Family for Evaluating RQ3

1. **Remote serving only**
   - baseline
   - no local copy
2. **Selective partial replication**
   - Tier 1-style hot-set replication
3. **Cold-start full replica placement**
   - full remote replica created only after the demand breach
4. **Reserved-standby full replica promotion**
   - pre-created and pre-synchronized standby excluded from service until promotion
5. **Hybrid first-step reserved policy**
   - first extra node uses reserved capacity
   - additional nodes remain cold-start elastic

### Development Required for RQ3

Required for the strongest version of this RQ:

1. Implement **true consumer-LAN full replica placement**, not only same-LAN replica-set growth.
2. Integrate that placement into the controller's locality logic.
3. Implement a **reserved-standby mode** for the first full-replica promotion.
4. Add instrumentation for activation timestamps, sync progress, and admission-to-service timing.
5. Measure cleanup debt explicitly.

Reserved capacity should be interpreted as a **warm elasticity mode**, not as the removal of elasticity from the thesis. It changes the trade-off from:

- pay cold-start cost only on demand

to:

- pay idle reservation cost in exchange for faster burst response

The most defensible reserved-capacity design is likely:

- reserve capacity only for the **first** full scale-up
- use cold-start growth only for later additional replicas

This keeps the comparison realistic for edge environments with limited idle resources.

### Measurements Required for RQ3

Service-benefit measurements:

1. p95/p99 latency during cross-region hotspot phases
2. failure rate and completed request volume
3. phase-specific recovery behavior after a demand surge

Activation-overhead measurements:

1. **Activation latency**
   - breach detected to backend eligible for routing
2. **Sync tax**
   - time, CPU, and bandwidth spent before a cold full replica becomes usable
3. **Time-to-benefit**
   - breach detected to latency recovery or service stabilization

Steady-state overhead measurements:

1. **Reservation tax**
   - idle CPU/RAM/storage/replication traffic for standby capacity
2. extra node-hours or container-hours consumed by each strategy
3. background replication cost while standby is not yet serving

Lifecycle-complexity measurements:

1. cleanup debt
2. failed removals
3. lingering containers at run end
4. post-cleanup stale control work
5. control-plane exceptions caused by scale-down or reconfiguration

### Evaluation Design for RQ3

The workload should include different demand regimes, not just a single long-cycle run:

1. brief burst
2. medium-duration hotspot
3. sustained hotspot
4. reversed hotspot direction

The main value of RQ3 is not to show that one strategy is universally best. It is to determine **when** the faster readiness of reserved capacity justifies its idle cost, and **when** partial replication is sufficient without escalating to a full remote copy.

Hold constant:

- telemetry acquisition mode
- routing policy
- workload shape

Vary only:

- data-locality strategy (remote / selective / cold full / warm standby)

### Main Validity Threats for RQ3

- if full-replica placement remains same-LAN only, the cross-region interpretation weakens substantially
- standby cost must be measured explicitly rather than assumed to be small
- Tier 1 observability gaps can still confound comparisons if not instrumented clearly

### Fallback Narrower RQ if the Stronger Version Is Not Implemented

If consumer-LAN full replica placement and reserved standby are not implemented in time, the narrower fallback RQ is:

> What service-quality benefit and lifecycle cost does selective partial replication provide under shifting cross-region demand compared with remote serving only?

This fallback is weaker, but still defensible.

---

## 6. Cross-RQ Measurement Matrix

| RQ            | Main Independent Variable                                                                         | Main Dependent Variables                                                                                           | Required Development                                                                    | Existing Support Level |
| ------------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------- | ---------------------- |
| **RQ1** | Delivery cadence (push vs. polling interval)                                                      | Decision staleness, reaction latency, transient p95/p99, control overhead, scaling outcome description             | Polling telemetry source, summary persistence, timing instrumentation, overhead sampler | High                   |
| **RQ2** | Backend-selection policy mode (`topology_only` / `topology_host` / `topology_host_replica`) | Latency, fairness, failure rate, bad-choice frequency, spillover behavior, compute-plane vs. data-plane separation | Explicit policy modes, per-policy traceability                                          | Medium                 |
| **RQ3** | Locality / readiness strategy (remote / selective / cold full / warm standby)                     | Latency recovery, activation cost, sync tax, reservation tax, cleanup debt                                         | Consumer-LAN full replica, reserved standby, timing and lifecycle instrumentation       | Low to Medium          |

---

## 7. Development Priorities Implied by the RQs

If the thesis follows this RQ set, the implementation priorities should be:

1. **Polling telemetry source + aggregator boundary persistence**
   - required for RQ1 (delivery cadence dimension) — COMPLETED
2. **Timing instrumentation for staleness and reaction latency**
   - required for RQ1 (`consumed_at` pairing, breach detection from telemetry) — COMPLETED
3. **Controller overhead sampler + analysis CLIs**
   - required for RQ1 (control-plane overhead, scaling outcome description) — COMPLETED
4. **Explicit routing policy modes**
   - required for RQ2 (`topology_only`, `topology_host`, `topology_host_replica`)
5. **Consumer-LAN full replica placement**
   - required for the stronger RQ3 (cross-region locality)
6. **Reserved-standby first-scale promotion path**
   - strongest extension for making elasticity itself a central thesis contribution

---

## 8. Thesis Chapter Mapping (Proposed)

| Chapter                   | Content                                                                                                                                                   | Feeds Into                    |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| 1. Introduction           | Problem statement, three-pillar framing, SDN-as-unifier motivation, industry contrast, proposal alignment                                                 | —                            |
| 2. Literature Review      | Edge orchestration, SDN control planes, telemetry acquisition models, multi-layer load balancing, data locality & elasticity, coordination gap literature | —                            |
| 3. System Architecture    | Three-thread controller, Double-VIP model, telemetry fabric, elasticity manager, data gravity tiers, selective sync                                       | Methodology basis for all RQs |
| 4. Methodology            | RQ formulation, evaluation design, measurement definitions, baseline rationale, held-constant sets                                                        | All RQs                       |
| 5. RQ1 Evaluation         | Telemetry freshness and delivery cadence results                                                                                                          | Telemetry Freshness pillar    |
| 6. RQ2 Evaluation         | Metadata-aware backend selection results                                                                                                                  | Backend Selection pillar      |
| 7. RQ3 Evaluation         | Data-locality readiness strategy results                                                                                                                  | Data Locality pillar          |
| 8. Synthesis & Conclusion | Cross-pillar findings, what SDN unification enables, limitations, future work                                                                             | Thesis defense                |
