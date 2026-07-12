# System-to-Thesis RQ Map v2 — Cross-Layer SDN Orchestration

> **Status:** Reframed based on discussions (2026-06-06, updated 2026-07-12). This supersedes the original `system_to_thesis_map_rq_advanced.md` with a three-pillar framing: Trigger Quality, Telemetry Freshness, and Backend Selection — unified by an SDN cross-layer control plane. The synthesis chapter reconstructs the compound coordination gap from all three RQs.

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

The contribution is **characterizing the coordination gap** that separated
architectures impose between monitoring, routing, and scaling — and measuring
how each link in the detection→delivery→action chain independently affects
service quality during demand shifts. The thesis does not claim that unifying
these concerns is superior to separated architectures; it uses the unified SDN
controller as an experimental apparatus to isolate and measure coordination
delays that every existing architecture accepts as given. The synthesis
chapter reconstructs the compound coordination tax from the three RQs,
producing the first experimental quantification of the cumulative latency
that three-layer separation imposes on stateful edge services.

### Central Claim

> This thesis experimentally examines three links in the detection→delivery→action
> chain of cross-layer SDN orchestration — **trigger quality** (what is
> monitored), **telemetry freshness** (how fast it arrives), and **backend
> selection** (how quickly new capacity receives traffic) — characterizing
> how each independently affects service quality during demand shifts in
> stateful edge services. The SDN control plane serves as the experimental
> platform that enables isolated variation of each link; the synthesis
> chapter reconstructs the compound coordination tax from all three.

### The Three Pillars

| Pillar                        | RQ       | Core Question                                                                               |
| ----------------------------- | -------- | ------------------------------------------------------------------------------------------- |
| **Trigger Quality**     | RQ3      | Does a latency-aware degradation score detect stateful-service overload earlier than a CPU-only threshold? |
| **Telemetry Freshness** | RQ1      | How does telemetry delivery cadence affect reaction latency during demand shifts?            |
| **Backend Selection**   | RQ2      | How does routing-plane awareness timing affect load redistribution quality during scale-up?   |

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

While the initial proposal emphasized metadata-driven scaling as the central
contribution, architecture development revealed that the coordination gap
between monitoring, routing, and scaling is the more fundamental research
problem — and one that the literature has never characterized. The three-pillar
investigation presented here **operationalizes** the proposal's high-level
goals ("coordinate auto-scaling based on meta-information") by decomposing
the coordination gap into three independently testable links: detection
(RQ3), delivery (RQ1), and action (RQ2). The proposal's emphasis on
spatio-temporal data popularity informed the degradation score's latency-aware
design (RQ3) and the topology-aware backend selection policies (RQ2). Data
placement strategies (Tier 0/1/2) are discussed in the synthesis chapter as
a natural extension of the unified architecture, but their experimental
evaluation is deferred to future work.

---

## 2. RQ Selection Principles

The chosen RQs should satisfy all of the following conditions:

1. They must ask about a **systems trade-off or control problem**, not merely restate a feature.
2. They must be **empirically answerable** with measurable variables and controlled baselines.
3. They must **isolate the main independent variable** instead of changing several architectural dimensions at once.
4. They must remain faithful to the implemented system unless explicitly marked as requiring further development.
5. They must support a clear methodology chapter and a defensible results chapter.
6. Each RQ's baselines must encode the **architectural alternative** of separated control loops — so that the comparison is not against a specific competing product but against the *property* those products share (stale state, single-layer visibility, or trigger blindness).

For this reason, the recommended RQ set below separates:

- **trigger composition** from **delivery mechanism** (RQ3)
- **telemetry freshness** from **delivery mechanism** (RQ1)
- **discovery-time** from **spawn-time routing awareness** (RQ2)

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
| **Per-flow routing with cross-layer metadata** | Traditional L4 LBs (HAProxy, NGINX stream) can consume host-level metrics (CPU, RAM, connections) but cannot consume scaling-lifecycle state (warm leases, drain flags) without custom inter-component integration. OpenFlow enables per-TCP-connection steering based on WSM cost functions that incorporate host load AND scaling lifecycle AND topology — all from shared in-process state. | RQ2: the `topology_lifecycle` policy mode adds spawn-time warm leases — testing whether in-process lifecycle state produces measurable improvement in load redistribution beyond what a standard LB can achieve without custom scaler integration. |
| **Same-process routing and scaling**           | Thread 1 (routing) and Thread 3 (scaling) share the VIP pool data structure. When Thread 3 adds or drains a backend, Thread 1 sees the change immediately — no API call, no eventual consistency, no propagation delay.                                                                                                        | RQ1 & RQ3: the reaction latency measurement reflects only telemetry freshness and infrastructure provisioning time — not an additional control-plane propagation gap.                                                                                                 |
| **L3 traffic-plane separation**                | `VIP_SERVER` (compute) and `VIP_DATA_N*` (data) are separate virtual IPs with separate WSM cost functions and separate backend pools. This separation is enforced by OpenFlow rules at the network layer, not by application configuration that can be misconfigured.                                                       | RQ2: compute-plane and data-plane selection policies can be evaluated independently under the same infrastructure.                                                                                                                                                     |
| **Topology as a first-class input**            | The controller builds the network topology during setup (which MAC is in which LAN, hop distances). This feeds directly into routing cost functions and placement decisions — the controller knows*where* every resource is, not just its health status.                                                                     | RQ2: both `topology_host` and `topology_lifecycle` modes use topology as a cost dimension. RQ3: cross-LAN placement decisions depend on topology awareness.                                                                                                              |

### 3.3 Honest Scope

What this thesis does **not** claim:

- That SDN is strictly superior to all alternative architectures
- That the coordination gap matters equally for all workloads (it may be negligible for steady-state, low-churn scenarios)
- That the approach scales to large deployments (the testbed is a controlled two-network topology with a fixed set of infrastructure containers serving simulated workloads)
- That the Double-VIP model generalizes beyond MongoDB replica sets

What it **does** claim:

- That trigger composition, telemetry freshness, and routing awareness each independently affect service quality during demand shifts
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
| **RQ2** | `topology_slowstart` (invisible until discovery, then graduated ramp) | Discovery-time backend awareness — separated LB doesn't know backend exists until health checks pass; coordination delay between spawn and routing-plane awareness |
| **RQ3** | CPU-only threshold (w_cpu=1.0, w_lat=0.0, threshold=0.45 uncalibrated) | Trigger blindness to I/O-bound overload — the default in Kubernetes HPA, AWS ASG, and most autoscaling platforms |

### 4.2 Why This Is Methodologically Valid

- **Same hardware, same workload, same infrastructure** — only the variable under test changes
- **Each RQ holds the other pillars constant** — RQ1 varies telemetry but locks routing and trigger policy; RQ2 varies selection policy but locks telemetry and trigger; RQ3 varies trigger composition but locks telemetry and routing
- **The baselines are real operating modes of the system**, not simulated strawmen — the system genuinely runs in polling mode, slowstart mode, and CPU-only mode
- **Isolation of causation** — a system-vs-system comparison (e.g., "my controller vs. Kubernetes") would confound dozens of variables (language runtime, container runtime, network stack, tuning). Varying one architectural property within the same system isolates the effect

### 4.3 Synthesis: The Compound Coordination Gap (Chapter 8)

The synthesis chapter reconstructs the compound coordination gap from the
three RQ results without requiring additional experiments. RQ3 provides the
detection penalty (CPU-only may miss I/O-bound overload entirely). RQ1 provides
the delivery penalty (poll-30s adds ~43 s to breach detection). RQ2 provides
the action penalty (slowstart adds ~31 s to time-to-first-traffic). The
synthesis constructs a single timeline showing the cumulative latency from
overload onset to traffic reaching new capacity in a fully separated
architecture versus the unified architecture:

| Architecture | Detection | Delivery | Action | Provisioning | Total |
|---|---|---|---|---|---|
| Fully separated | CPU-only: never or late | Poll-30s: +~43 s | Slowstart: +~31 s | ~10 s | ~84 s (coordination overhead ~74 s + provisioning ~10 s) |
| Fully unified | Degradation score: early | Push: ~0 s | Lifecycle: ~0 s | ~10 s | ~10 s + early detection lead |

The coordination tax — the unnecessary latency imposed by three-layer
separation — is approximately 74 seconds under the conditions tested, or
unbounded if the CPU-only trigger never fires. This is the first experimental
quantification of the phenomenon that Wang et al. documented, Pierro & Ullah
observed as a side effect, and Yaseen (2025) called for at the network layer
but that no prior work has translated to orchestration latency.

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

## RQ2. Routing-Awareness Timing and the Coordination Gap

> **RQ2.** How does the timing of routing-plane awareness relative to backend spawn — at spawn time (warm lease, in-process) versus at discovery time (slow-start ramp, simulating a separated LB) versus no ramp-up — affect load redistribution quality during scale-up events in a stateful edge system?

### Why RQ2 Is a Strong RQ

This RQ tests the **coordination gap in the routing plane** — the same
phenomenon RQ1 tests for monitoring (push vs poll). When the scaler spawns
a new backend, a separated LB discovers it via health checks (discovery-time
awareness). The unified controller knows about it at spawn time because
routing and scaling share the same process. Three modes characterize the
spectrum from no ramp-up to spawn-time awareness.

This parallels RQ1 methodologically: both ask whether co-location eliminates
a measurable delay. Neither claims superiority; both report what was measured.

### Concepts Involved in RQ2

- routing-plane awareness timing (spawn-time vs. discovery-time)
- coordination gap in backend discovery
- warm lease (spawn-time atomic, bounded priority window)
- slow-start ramp (discovery-time graduated weight increase)
- load redistribution time (spawn → equilibrium)

### Architectural Framing: What Each Mode Represents

| Mode | Awareness timing | Ramp-up | Encodes |
|---|---|---|---|
| `topology_host` | Immediate (pool entry), unknown stats → best-case (0.0) | None — cold-start WSM (leastconn-style) | No ramp-up, cold-start thundering herd. Fastest redistribution, least controlled. |
| `topology_slowstart` | Discovery-time (first telemetry, 0–10 s after spawn, avg ~5 s). Until then: worst-case (1.0, effectively invisible). | Graduated weight ramp starting at discovery | Backend invisible until discovery (separated LB doesn't know it exists), then graduated ramp. The discovery gap is the coordination delay. |
| `topology_lifecycle` | Spawn-time (atomic with pool registration) | Warm lease (bounded priority window) | Unified controller. Balanced: fast start, controlled transition, zero discovery gap. |

All other parameters (WSM weights, host-load dimensions, pool structure,
telemetry delivery) are identical across modes.

### Why RQ2 Matches the Current Architecture

The warm-lease mechanism already exists in `_vip_routing/selection.py`
(`_claim_warm_backend`, `mark_server_backend_warm`, `mark_storage_backend_warm`).
The cold-start WSM behavior (worst-case when stats unknown) is also already
implemented. What's needed is a policy-mode gate to disable warm leases and,
for `topology_slowstart`, a graduated slow-start ramp in the WSM.

### Development Required for RQ2

1. Add `BACKEND_SELECTION_POLICY` env var to `_vip_routing/config.py`.
2. In `select_server` and `select_storage`:
   - `topology_host`: skip `_claim_warm_backend()`. Unknown stats → 0.0
     (best-case). Backend wins every WSM competition immediately —
     cold-start thundering herd (leastconn-style).
   - `topology_slowstart`: skip `_claim_warm_backend()`. Unknown stats → 1.0
     (worst-case). Backend is invisible until first telemetry (0–10 s,
     avg ~5 s). At discovery: start a graduated cost penalty decaying
     linearly from 1.0 to 0.0 over the warm-lease TTL — simulating
     discovery-time slow-start ramp.
   - `topology_lifecycle`: unchanged (current behavior).
3. Create env overrides for `topology_host` and `topology_slowstart`.

Estimated: ~40 lines across `selection.py` and `config.py`.

### Measurements Required for RQ2

1. **Load redistribution time** — `spawn_done_ts` → equilibrium load share
   (±10% of per-backend mean). Core evidence.
2. **Transition-window service quality** — p95/p99 latency and failure rate
   in the `compute_spike` phase after scale-up events.
3. **Per-mode redistribution profile** — request share over time for the new
   backend, showing ramp shape.

### Evaluation Design for RQ2

Three runs, one per mode:

| Run | Mode | Ramp-up |
|---|---|---|
| **R2-TH** | `topology_host` | None |
| **R2-SS** | `topology_slowstart` | Graduated ramp at discovery |
| **R2-TL** | `topology_lifecycle` | Warm lease at spawn time |

Hold constant: push-mode telemetry, golden config thresholds, canonical
workload, WSM weights, Double-VIP pool structure.

Vary only: `BACKEND_SELECTION_POLICY`.

### Main Validity Threats for RQ2

- **Cold-start thundering herd may make `topology_host` redistribute fastest with no latency penalty.** The new backend wins every competition immediately — if the cold backend handles the load fine, ramp-up mechanisms add control but not speed. This is not a threat — it's a potential finding characterizing the speed-vs-control trade-off.
- **The discovery gap (0–10 s, avg ~5 s) may dominate `topology_slowstart`.** The backend is invisible for one telemetry window — capacity sits idle. This is the coordination delay. The thesis honestly reports whether it matters.
- Replica lag is empirically zero at this workload — the thesis acknowledges
  this and focuses on dimensions that actually vary.

---

## RQ3. Trigger Quality and Detection Accuracy

> **RQ3.** For stateful edge services where I/O latency often degrades before
> CPU saturates, does a latency-aware multi-dimensional degradation score
> detect overload earlier and with fewer false positives than a CPU-only
> threshold?

### Why RQ3 Is a Strong RQ

This RQ isolates the **detection** link of the coordination gap. Before the
controller can deliver information (RQ1) or act on it (RQ2), it must first
recognize that overload is occurring. The degradation score that triggers
scale-up is a weighted combination of CPU saturation (40%) and processing
latency (60%). The latency component dominates because, in stateful edge
services, MongoDB I/O operations drive request latency — T_proc rises before
CPU saturates.

The literature has asked "what metric to use?" — Zhou & Yong (2024) showed
HTTP 5xx-based HPA outperforms CPU-based HPA for Nginx. PAHPA (Xiao et al.,
2026) proposed real-time monitoring as a binary correction to predictions.
But **no study has compared a latency-aware multi-dimensional score against
a CPU-only threshold for stateful edge services**, where I/O latency is the
dominant failure mode and CPU is a lagging indicator.

Across all four literature domains surveyed for this thesis, every paper that
studies scaling triggers treats the metric as a given: CPU utilization
(Kubernetes HPA), request rate (AWS ASG), or a pre-defined compound metric
(OSM POL). None vary trigger composition as an experimental variable.

### Concepts Involved in RQ3

- degradation score composition (CPU vs latency weighting)
- breach detection time (earliness of overload recognition)
- false positive rate (spawns during low-load phases)
- false negative rate (missed spawns during overload)
- I/O-bound vs CPU-bound overload detection
- trigger blindness to storage-driven degradation

### Architectural Framing: What Each Mode Represents

| Mode | Weights | Threshold | Encodes |
|---|---|---|---|
| `degradation_score` | w_cpu=0.40, w_lat=0.60 | 0.45 (golden) | Latency-aware multi-dimensional detection tuned for stateful services |
| `cpu_only` | w_cpu=1.00, w_lat=0.00 | 0.45 (uncalibrated) | CPU-only threshold: the industry default applied without domain-specific tuning |

All other parameters (sliding window, cooldowns, delivery cadence, routing
policy) are identical across modes.

### Why RQ3 Matches the Current Architecture

The degradation score already accepts weights via environment variables in
`scaling_config.py`:

```python
_W_CPU    = float(os.environ.get("SCALEUP_W_CPU",    "0.40"))
_W_T_PROC = float(os.environ.get("SCALEUP_W_T_PROC", "0.60"))
```

No code changes are needed. The CPU-only mode is activated by setting
`SCALEUP_W_CPU=1.0` and `SCALEUP_W_T_PROC=0.0`. The storage tier uses
separate weights (`SCALEUP_W_STORAGE_CPU`, `SCALEUP_W_T_DB`) which must
also be set to CPU-only for consistency.

### Development Required for RQ3

1. Create env override files for `degradation_score` and `cpu_only` modes.
2. Ensure the independent breach detector (`breach_detector.py`) reads
   weights from the same env vars as the controller.
3. Add a pre-run validation step that confirms weight agreement between
   controller and observer.

Estimated: env override files only. Zero code changes.

### Measurements Required for RQ3

1. **Breach detection time** — `spawn_start_ts − breach_window_end`,
   compared across trigger modes. Core evidence for detection earliness.
2. **False positive rate** — spawns during baseline phase / total spawns.
3. **False negative rate** — spawns missed during stress phases relative
   to the degradation score baseline.
4. **Service quality during transitions** — per-phase p50/p95 latency,
   timeout rate, and completed request volume.

### Evaluation Design for RQ3

Six runs, three per mode:

| Run | Trigger | Weights |
|---|---|---|
| **R3-DS** (×3) | degradation_score | w_cpu=0.40, w_lat=0.60 |
| **R3-CPU** (×3) | cpu_only | w_cpu=1.00, w_lat=0.00 |

Hold constant: push-mode telemetry, topology_lifecycle routing, golden
config thresholds, canonical workload.

Vary only: `SCALEUP_W_CPU` and `SCALEUP_W_T_PROC` (and storage equivalents).

### Main Validity Threats for RQ3

- **CPU-only may never fire at realistic edge CPU levels (2–8%).** This is not a threat — it is the central finding: CPU-based autoscaling is structurally incapable of responding to I/O-bound overload in stateful edge services.
- **The uncalibrated threshold may be considered unfair.** The experiment explicitly tests the industry default without recalibration. A calibrated comparison is identified as future work.
- **Bimodality from RQ1 may obscure the signal.** If both triggers produce bimodal outcomes, n=3 may not separate them. But if CPU-only produces zero spawns, the result is binary and conclusive.

---

## 6. Cross-RQ Measurement Matrix

| RQ            | Main Independent Variable                                                                         | Main Dependent Variables                                                                                           | Required Development                                                                    | Existing Support Level |
| ------------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------- | ---------------------- |
| **RQ1** | Delivery cadence (push vs. polling interval)                                                      | Decision staleness, reaction latency, transient p95/p99, control overhead, scaling outcome description             | Polling telemetry source, summary persistence, timing instrumentation, overhead sampler | High                   |
| **RQ2** | Routing awareness timing (cold-start herd / discovery-time slow-start / spawn-time warm lease) | Load redistribution time, transition-window service quality, per-mode redistribution profile (speed vs. control trade-off) | Policy-mode gating + slow-start ramp in WSM cost functions | High |
| **RQ3** | Trigger composition (degradation score vs CPU-only threshold) | Breach detection time, false positive/negative rate, per-phase service quality | Env var toggle (SCALEUP_W_CPU, SCALEUP_W_T_PROC) | High (zero code changes) |

---

## 7. Development Priorities Implied by the RQs

If the thesis follows this RQ set, the implementation priorities should be:

1. **Polling telemetry source + aggregator boundary persistence**
   - required for RQ1 (delivery cadence dimension) — COMPLETED
2. **Timing instrumentation for staleness and reaction latency**
   - required for RQ1 (`consumed_at` pairing, breach detection from telemetry) — COMPLETED
3. **Controller overhead sampler + analysis CLIs**
   - required for RQ1 (control-plane overhead, scaling outcome description) — COMPLETED
4. **Explicit routing policy-mode gating + slow-start ramp + per-mode unknown-stats treatment**
   - required for RQ2 (`topology_host`: best-case herd, `topology_slowstart`: worst-case invisible → ramp, `topology_lifecycle`: spawn-time warm lease)
5. **Trigger mode env var overrides**
   - required for RQ3 (cpu_only vs degradation_score)
6. **Breach detector weight synchronization**
   - required for RQ3 (independent observer must use same weights as controller)

---

## 8. Thesis Chapter Mapping (Proposed)

| Chapter                   | Content                                                                                                                                                   | Feeds Into                    |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------- |
| 1. Introduction           | Problem statement, three-pillar framing, SDN-as-unifier motivation, industry contrast, proposal alignment                                                 | —                            |
| 2. Literature Review      | Edge orchestration, SDN control planes, telemetry acquisition models, multi-layer load balancing, coordination gap literature | —                            |
| 3. System Architecture    | Three-thread controller, Double-VIP model, telemetry fabric, elasticity manager, data gravity tiers, selective sync                                       | Methodology basis for all RQs |
| 4. Methodology            | RQ formulation, evaluation design, measurement definitions, baseline rationale, held-constant sets                                                        | All RQs                       |
| 5. RQ1 Evaluation         | Telemetry freshness and delivery cadence results                                                                                                          | Telemetry Freshness pillar    |
| 6. RQ2 Evaluation         | Routing-awareness timing results (coordination gap in backend discovery)                                                                                                                  | Backend Selection pillar      |
| 7. RQ3 Evaluation         | Trigger quality results (degradation score vs CPU-only threshold)                                                                                         | Detection Quality pillar      |
| 8. Synthesis & Conclusion | Compound coordination gap reconstruction from RQ1+RQ2+RQ3; the 74-second coordination tax; what SDN unification enables; limitations; future work        | Thesis defense                |
