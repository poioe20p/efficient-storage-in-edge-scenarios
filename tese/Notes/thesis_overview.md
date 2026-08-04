# Thesis Overview - Telemetry, Scaling, and Traffic Admission in Stateful Edge Services

> **Status:** Current thesis framing, 2026-07-31.
>
> This document defines what the thesis studies, the state-of-the-art gap it addresses, its research questions, and the limits of its claims. It is the narrative reference for the thesis manuscript, research-question documents, and experiment plans.

---

## 1. What This Thesis Is

This thesis experimentally characterizes how **telemetry delivery**, **bottleneck-aware scaling action selection**, and **backend readiness propagation** affect an elastic, stateful edge service's ability to turn changing user demand into usable capacity.

The thesis does not ask whether SDN, Kubernetes, or a particular orchestrator is universally superior. It studies three control-loop interfaces within one controlled platform and measures their consequences for service behavior under changing demand.

The contribution is an experimentally grounded characterization of how an elastic, stateful edge service moves from observed demand to usable capacity.

---

## 2. Experimental Context

The experimental platform is a containerized edge-service environment with:

- client-generated application requests;
- stateful edge services backed by MongoDB;
- two network domains connected by emulated WAN latency;
- SDN-controlled Virtual IP routing through OpenFlow;
- telemetry aggregation from compute and storage containers;
- runtime compute and storage scale-out; and
- lifecycle-aware backend registration and removal.

The experimental subject is the **service offered to users**, not an isolated controller algorithm. Each experiment applies a controlled workload scenario and observes how the control plane affects service behavior.

Workload scenarios vary:

1. request intensity and demand-shift speed;
2. request mix, producing compute-bound or data-access-bound pressure;
3. duration of the demand episode; and
4. demand decrease and recovery after stress.

The primary outcomes are offered and completed requests, latency distributions, failures, action timing, resource use, and the time at which new capacity can actually serve requests.

Tier 1 selective synchronization and other data-locality mechanisms are platform capabilities. They are not primary independent variables in this thesis. They are disabled or held constant when necessary to prevent them from confounding telemetry, scaling-action, and traffic-admission experiments.

Unless an approved RQ protocol explicitly states otherwise, thesis evaluation runs disable Tier 1 selective synchronization, prepared persistent storage reserves, and cross-region storage placement. RQ2 may still use cold, same-LAN storage scale-out as an action under test.

---

## 3. State of the Art

Across the reviewed literature, the constraints of edge deployments are
framed less as absolute resource scarcity than as management and
coordination complexity: resources are heterogeneous and volatile, the
placement of capacity and the scheduling of requests are often decoupled,
and the components of an edge stack are administered across multiple
domains. This thesis addresses the measurable slice of that complexity —
the three control-loop interfaces defined in Section 4 — rather than
proposing a new scheduling, prediction, or optimization technique; it
follows the integration direction the literature calls for, using
standard mechanisms, and contributes a controlled experimental
characterization of those interfaces.

### 3.1 Monitoring and Telemetry

Monitoring research establishes that delivery design matters. Huang and Pierre's AdapPF varies Prometheus scrape intervals in geo-distributed cluster federations and shows that coarse collection can reduce scheduling quality, while adaptive collection can reduce monitoring traffic. Yaseen's survey of programmable network-wide monitoring identifies pull-based visibility gaps and calls for monitoring to be integrated with control and automation. Recent cloud-edge orchestration work also uses runtime telemetry for placement and rescheduling decisions, as recorded in the monitoring literature review.

These works establish that telemetry freshness, overhead, and orchestration quality are related. In the reviewed corpus, they do not distinguish between delayed but complete telemetry delivery and latest-state delivery that discards intermediate observations. They also do not trace those delivery semantics through a stateful service's scaling and traffic-admission path.

### 3.2 Auto-Scaling

Auto-scaling research has extensively studied scaling algorithms, indicators, prediction, and resource allocation. Qu, Calheiros, and Buyya provide a taxonomy of web-application auto-scalers centered on dimensions such as scaling indicators, resource estimation, and scaling timing; it discusses monitoring interval as an operational trade-off, but does not make telemetry freshness or delivery semantics a taxonomy dimension. Toka et al. model and improve Kubernetes edge scaling through machine learning. Zhou and Yong show that changing the monitored metric can improve HPA behavior. Ghorab et al. show that load balancing and VNF auto-scaling interact, including under weighted resource signals. Llorens-Carrodeguas et al. integrate SDN traffic steering with horizontal VNF scaling while retaining external monitoring and lifecycle components.

This literature largely studies **when** to scale and **how many** instances to create. In the reviewed corpus, it does not directly test whether a stateful edge controller should choose a compute-capacity action or a storage-capacity action according to the bottleneck observed in service telemetry.

### 3.3 SDN Load Balancing

SDN load-balancing research has established a mature progression from static policies to multi-resource and predictive selection policies. Belgaum et al. review SDN load-balancing techniques, while Caiza and Campoverde evaluate a multi-resource weighted selection policy. These and related SDN load-balancing studies evaluate throughput, latency, and utilization under a fixed or already available backend pool.

This literature primarily asks: **given available backend state, which backend should receive the next flow?** It generally treats backend availability and health as established facts. Wang et al.'s SDNFV architecture explicitly describes a delay between instance synchronization and load-balancer inclusion, but does not experimentally vary that delay. In the reviewed corpus, no study isolates the path from a backend becoming application-ready to that backend becoming eligible to receive traffic while holding the backend-selection function fixed.

### 3.4 Resource Orchestration in Edge Environments

Resource-orchestration literature recognizes the need for cross-layer context. Sofia et al. propose context-aware cross-layer orchestration for containerized applications. Nain et al.'s review identifies continuing challenges in integrating SDN with edge computing. Okwuibe et al. demonstrate a close technology stack involving containers, SDN, and edge services, but retain separate monitoring, container-orchestration, and network-control systems. Malazi et al. identify fragmented evaluation practice in dynamic MEC service placement.

These works motivate integrated orchestration, but they do not provide a controlled causal characterization of the three interfaces examined here: telemetry observation, scaling-action selection, and traffic admission after backend readiness.

---

## 4. Research Gap

The thesis does not claim that monitoring, auto-scaling, load balancing, or cross-layer orchestration are new research areas. They are established areas. The narrower gap is at the interfaces between them.

| Interface | Open question addressed by this thesis |
| --- | --- |
| Telemetry to decision | Does a controller behave differently when demand evidence arrives late but complete, versus when intermediate observations are absent? |
| Decision to capacity action | Under stateful workloads, does selecting compute or storage scale-out according to the observed bottleneck improve recovery and resource efficiency? |
| Ready backend to traffic | Once a backend is ready, how much does propagation of readiness to the routing plane affect when that backend becomes usable capacity? |

These interfaces matter because user-visible service quality depends on the entire path:

```text
Demand shift
  -> telemetry observation
  -> scaling decision
  -> capacity action
  -> backend readiness
  -> routing admission
  -> successful user request
```

A controller can have a sophisticated scaling algorithm and still react poorly if it misses relevant evidence, scales the wrong resource tier, or leaves ready capacity unavailable to traffic.

---

## 5. Thesis Approach

The SDN controller and its co-resident telemetry, elasticity, and Virtual IP routing paths form the experimental apparatus. Their shared process boundary and explicit lifecycle hooks make individual interfaces configurable while other parts of the service remain controlled.

For each demand episode, the experiment records:

1. workload onset;
2. telemetry-window completion and controller observation;
3. scaling decision and selected action;
4. provisioning start and completion;
5. application-readiness confirmation;
6. backend admission to the routing pool;
7. first routed request and first successful response; and
8. recovery after demand falls.

This instrumentation distinguishes the time to create a container from the time to create **usable service capacity**.

Existing RQ1, RQ2, and RQ3 campaigns are supporting platform and calibration evidence. Their telemetry-cadence, routing-policy-bundle, and trigger-composition framing is superseded by this document. They are not direct final evidence for the redesigned research questions until the interventions and measurements below are implemented and evaluated.

The **RQ2 final protocol is implemented** (2026-08-04): the open-loop driver (§8), the `ba-strict` sticky-commitment arm (implemented, optional follow-up), and the v2 measurement/statistics layer (effect-size statistics at n=3 — Cliff's delta + 3/3 direction consistency, sync-cost, relief-flatten) are in place; the **18-run (6 cells × 3) v2 campaign execution remains**.

The **RQ3 final protocol is implemented** (2026-08-04): the readiness gate and flow-isolation mechanism (`rq3_preparation.md`) plus the v2 evaluation design — event-driven `direct` arm (approach A: admission on an `app_ready` control event, no probe before admission), a 10 s periodic `discovery` arm, and a 15 s sensitivity cell; open-loop driver; pre-registered gap-window consequence metrics; MWU + Cliff's delta mirroring the RQ2 v2 stats layer; per-arm knob verification and selftest gates. The **13-run v2 campaign execution remains** (on `cloud-vm-rq3`).

The **RQ1 final protocol is implemented** (2026-08-04): the 4-arm completeness ×
info-age factorial (event-preserving, delayed, poll, and a **sampled-push**
arm that delivers every third window immediately) with the open-loop driver,
the status-aware measurement contract, and the pre-registered statistics
(factorial-edge Mann–Whitney U + Cliff's delta, non-surge C8 verdict); the
**20-run (4 arms × 5) v2 campaign execution remains**.

---

## 6. Research Questions

### RQ1 - Telemetry Delivery Semantics

> **How do verified event-preserving, delayed event-preserving, and latest-state telemetry delivery semantics affect overload observability, scaling response, and transient service quality in a stateful edge service?**

The experiment compares (full 2×2 factorial, RQ1 v2 protocol implemented
2026-08-04):

- an event-preserving reference that delivers every completed telemetry window exactly once in source order (fresh + complete);
- delayed event-preserving delivery of the same ordered windows, with a fixed, pre-registered delay and no burst replay (stale + complete);
- latest-state polling, where the consumer obtains only the most recent completed window and intermediate windows are not delivered (stale + lossy); and
- **sampled-push** delivery, where every Nth completed window is delivered immediately and the intermediate windows are dropped (fresh + lossy) — the cell that lets the delay-vs-loss attribution be drawn cleanly.

The aggregation window, scaling policy, routing policy, workload, topology, and resource limits remain fixed. The controller evaluates each delivered window when it arrives, so the effect of the specified delay on the decision timeline is intentional and measurable. The pre-registered primary reaction metric is usable-capacity latency; the first-decision latency is descriptive-only because delivery timing confounds it in the delayed/poll/sampled arms.

The purpose is not to claim that monitoring cadence has never been studied. AdapPF already shows that collection interval affects scheduler quality. This RQ isolates a more specific question: whether the controller is harmed mainly by delay, by loss of intermediate demand evidence, or by both.

Primary measurements include:

- completed and missed overload windows;
- information age and delivery delay;
- time from demand shift to scaling decision;
- time from demand shift to usable capacity;
- offered and completed requests;
- latency distributions and failure rate; and
- controller and telemetry overhead.

**Required extension:** create a durable, sequence-numbered telemetry-window log with retention, ordered replay, delivery acknowledgement, and shared event identifiers. The current ZMQ PUB/SUB path is not assumed to be event-preserving until sequence validation and gap recovery are implemented.

### RQ2 - Bottleneck-Aware Scaling Action

> **Under compute-bound and data-access-bound demand, does bottleneck-aware selection of compute or storage scale-out improve service recovery and resource efficiency relative to workload-agnostic fixed-priority policies when both actions are available?**

The experiment compares:

- counterbalanced compute-first and storage-first fixed-priority policies; and
- a bottleneck-aware policy that selects compute or storage scale-out from tier-specific telemetry.

Compute-bound and data-access-bound workload episodes are constructed separately and validated before comparison so that the induced bottleneck is known independently of the policy outcome. All policies have the same compute and storage action availability, per-tier resource caps, action budget, cooldowns, telemetry delivery, and backend-admission condition. Tier 1, prepared storage reserves, and cross-region storage placement remain disabled.

This RQ does not claim that multi-metric triggers are new. It asks a different question: whether telemetry should determine **which capacity action** is taken in a stateful service. A compute-only policy may be reported as a secondary engineering reference, but it is not used to attribute an effect specifically to bottleneck classification.

Primary measurements include:

- time to recover the bottleneck-specific pressure;
- time to usable capacity;
- p50, p95, and p99 latency;
- failures and completed offered demand;
- compute and storage node-minutes;
- number of scale actions; and
- whether the selected action produces measurable relief in the targeted tier.

**Required extension:** introduce a policy gate that selects one scaling action from a declared bottleneck classification, while logging the known induced episode label, evidence, selected action, rejected action, and action budget for every decision.

### RQ3 - Readiness Propagation and Traffic Admission

> **For newly created compute backends that satisfy the same application-readiness criterion, how does direct lifecycle notification versus periodic discovery affect the time until a ready backend contributes usable capacity?**

The experiment compares:

- direct registration of a backend after a verified application-readiness event; and
- periodic discovery of the same readiness state, with direct registration suppressed until the discovery result arrives.

The experiment is limited to compute backends because the current storage path has a distinct MongoDB SECONDARY readiness event. Both conditions use the same readiness probe, routing cost function, load-balancing weights, pool state, workload, and resource limits. Warm-lease priority and slow-start ramps are disabled in both conditions. The experiment does not compare the controller with Kubernetes, HAProxy, or another external load balancer. It isolates only the propagation of readiness information.

The request driver schedules fresh TCP connections after backend readiness. The RQ3 experiment uses a dedicated flow-isolation mode in which each measurement request receives a unique connection tuple and the controller removes its corresponding VIP flow after the response. Existing flows are excluded before the timing interval begins. This guarantees one fresh backend-selection event per measured request and prevents flow affinity from being mistaken for a readiness-propagation effect.

This RQ is motivated by work such as Wang et al.'s SDNFV architecture, which documents synchronization before load-balancer inclusion, and by SDN load-balancing literature that generally assumes an already available backend pool.

Primary measurements include:

- backend-ready to routing-admitted delay;
- routing-admitted to first-flow delay;
- first-flow to first-successful-response delay;
- useful initial request share;
- transition-window latency and failures; and
- time from scale decision to usable capacity.

**Required extension:** add a compute readiness probe and pending-backend registry; delay all pool admission until readiness succeeds; suppress direct admission in the discovery condition; and decouple propagation from backend-selection policy, warm-lease priority, and ramp behavior. **Implemented** (2026-08-04) and extended by the v2 protocol: the `direct` arm is genuinely event-driven (the edge emits an `app_ready` control event at readiness; the controller admits on the event with no probe before admission — measured via an `admit_source` admission-log column), and a `discovery_15` sensitivity cell shows the quantization cost scales with the discovery period. Primary consequence metrics are anchored to the **admission gap** (pool-wide old-backend `timeout_rate`/`failure_rate` over `[spawn_started, admitted]`), where the propagation quantization tail is observable, rather than the new backend's post-admission window.

---

## 7. Relationship Between the Research Questions

The RQs examine consecutive but separately controlled interfaces:

```text
RQ1: What demand evidence reaches the controller?
  ->
RQ2: What capacity action does the controller choose?
  ->
RQ3: When does ready capacity become available to users?
```

Each RQ uses a controlled reference condition for the other two interfaces. This avoids interpreting a telemetry effect as a routing effect, or a routing effect as an auto-scaling effect.

The synthesis combines measured timing segments only after they have been measured under a common workload, resource configuration, and event schema. It does not infer an end-to-end coordination penalty by adding values from unmatched experiments.

---

## 8. Evaluation Principles

The thesis uses the following methodological requirements:

- The experimental unit is the independent run, not an individual request or individual scale event.
- Workload order is randomized or blocked to reduce host-state and time effects.
- Runs reset persistent containers, data state, manifests, and controller state.
- Primary comparisons use a scheduled open-loop driver that preserves a pre-specified offered-load process independently of response latency. This requirement follows Schroeder, Wierman & Harchol-Balter, *Open Versus Closed: A Cautionary Tale* (NSDI 2006): closed-loop models mask overload, and a latency-coupled driver makes the offered load differ per arm — as the RQ1 cross-campaign record acknowledges. The current synchronous curl driver is calibration or secondary evidence only until it is replaced for the final RQ campaigns; the RQ2 and RQ1 v2 protocols implement the replacement (see §5).
- Offered request load is recorded separately from completed requests.
- Every treatment uses the same application-readiness criterion.
- The controller records a common event trace from demand observation through first successful traffic.
- Tier 1 selective synchronization and other optional mechanisms are disabled or fixed when they would confound the tested interface.
- Results report per-run variation, effect sizes, and uncertainty rather than relying on pooled request counts as independent observations.

---

## 9. Scope and Limits

This thesis can claim that, within the evaluated two-domain stateful edge testbed and workload families, the three control-loop interfaces affect observable service behavior.

It does not claim:

- that the controller is superior to Kubernetes, OSM, HAProxy, or cloud provider services;
- that co-location is universally better than component separation;
- that the measured effects generalize to every edge workload or topology;
- that a particular latency distribution meets a real-world SLA;
- that the platform is production-ready or resilient to controller failure, node failure, multi-tenancy, or adversarial conditions; or
- that Tier 0, Tier 1, and Tier 2 data placement are evaluated as the main thesis contribution.

---

## 10. Relationship to Other Documents

| Document | Relationship |
| --- | --- |
| `tese/literature_review/README.md` | Corpus index: RQ → folder mapping and the core citation set. |
| `tese/literature_review/01_telemetry_rq1/README.md` | Telemetry state of the art and the delivery-semantics gap (RQ1). |
| `tese/literature_review/02_action_selection_rq2/README.md` | Auto-scaling and edge-storage state of the art and the bottleneck-to-action gap (RQ2). |
| `tese/literature_review/03_readiness_admission_rq3/README.md` | SDN load-balancing and service-discovery state of the art and the readiness-propagation gap (RQ3). |
| `tese/literature_review/04_context_edge/README.md` | Edge framing and platform context (introduction). |
| `tese/literature_review/05_context_orchestration/README.md` | Edge orchestration context and integration/scope boundaries. |
| `tese/literature_review/99_reference/README.md` | Background/reserve sources; not core evidence. |
| `tese/literature_review/global_literature_review.md` | Evidence ledger (synthesis + gap matrix); §1–§7 framing is superseded — see its banner. |
| `docs/operation/system_mechanisms.md` | Verified platform architecture and current mechanisms. |
| `docs/research_questions/` | Prior RQ documents and campaigns using the superseded framing. Replacement RQ definitions, measurement contracts, and experiment designs must be created before final thesis evaluation. |
| `tese/chapters/` | Thesis chapters; claims in the manuscript must not exceed this overview. |

---

*This document should be updated only when the approved thesis scope, research questions, or evidence boundaries change.*
