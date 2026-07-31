# Purpose Evidence Map — Why This Thesis, and the Evidence Behind Each Claim

> **Status:** 2026-07-31. Companion to `thesis_overview.md` (framing) and
> `../literature_review/global_literature_review.md` (evidence corpus).
> **Quote source:** all verbatim quotes below come from
> `tese/literature_review/global_literature_review.md`; section numbers (§) refer to it.
> **Full BibTeX:** `tese/references.bib`.
>
> **Purpose:** map every step of the thesis's argument — *why it matters* →
> *what the gap is* → *what the thesis does* — to concrete, quotable evidence,
> so the motivation and literature-review chapters can be written directly from
> this file.

---

## How to read this map

Each purpose step **P#** is a claim the thesis must establish. Under it:
papers, verbatim quotes, where each quote lives, and its **evidence strength**.

### Strength legend

| Mark | Meaning | How to use in the manuscript |
|---|---|---|
| `MEASURED` | An experimental result exists (some consumer effect was quantified) | Strongest; cite as measured fact |
| `DOCUMENTED` | The phenomenon is explicitly described, but never measured | Quote to establish existence |
| `SYMPTOM` | Degraded performance observed, cause *misattributed* | Quote to show the effect is real and unclaimed |
| `CALLED-FOR` | The community explicitly requests integration/study | Quote to show the need is recognised |
| `TAXONOMY-GAP` | Absent from a comprehensive taxonomy | Cite as "even the surveys miss it" |
| `SILENCE` | Not addressed anywhere | At most evidence of *inattention* — **never** evidence of importance |
| `FRAMING` | The thesis's own definition (no external citation) | State plainly as the thesis's construct |

### The single most important rule (from the Belgaum correction)

> **Absence ≠ importance.** If a 76-paper review says nothing about a topic,
> that proves only that the community has not studied it — not that it matters.
> The defensible gap is never *"X is important"*; it is:
> **"X is documented/observed/called-for, but never isolated and measured in this
> chain."** Every use of a `SILENCE` or `TAXONOMY-GAP` quote must be framed this
> way.

---

## The thesis's core claim (one sentence)

> **Given varying demand, the quality of an elastic stateful edge service's
> recovery — from observed demand to usable capacity — is governed by three
> control-loop interfaces: telemetry delivery semantics (RQ1), bottleneck-aware
> scaling-action selection (RQ2), and backend readiness propagation (RQ3).**

---

## P1 — Edge services are stateful, latency-sensitive, and face varying demand

**Claim:** geo-distributed stateful services live at the edge, their users feel
latency, and their demand varies over time.

| Evidence | Quote / source | Where | Strength |
|---|---|---|---|
| Traffic growth | 7 exabytes in 2025, >2× since 2020 — `\parencite{ITU2025InternetTraffic}` | Ch.1 motivation | `MEASURED` (statistics) |
| Mobile/edge is the access gateway | `\parencite{Gaudiaut2026MobileTrafficShare}` | Ch.1 motivation | `MEASURED` |
| Edge = resources closer to users, lower latency | Cao et al. (2020); Satyanarayanan (2017) — "The Emergence of Edge Computing" | Ch.1 motivation | `DOCUMENTED` (position/overview) |
| Edge ≠ cloud replacement; complement | Cao et al. (2020) | Ch.1 motivation | `DOCUMENTED` |
| Demand varies (existence in the world) | **Delegated to workload-characterisation literature** (see [Demand model](#demand-model-and-the-justification-of-variable-demand)) — the auto-scaling field's shared premise | Ch.1 + Ch.5 | `MEASURED`/`DOCUMENTED` (verify DOIs before citing) |
| Stateful, MongoDB-backed service | System design docs; replica sets, tiered placement | Ch.1, Ch.3 | `FRAMING` (the apparatus) |
| Demand varies (in the apparatus) | Imposed phases profile, quantified below | Ch.5 | `FRAMING` + derived stats |

**Use in thesis:** Ch.1 §Context-Motivation (growth → edge → latency-sensitive
stateful services → variable demand as the driver, latency as the outcome).

---

## P2 — The object of study is the path from demand change to *usable capacity*

**Claim:** a scale event is not finished when a container boots; it is finished
when the new capacity actually serves a successful request. This path is the
thesis's unit of analysis.

> "This instrumentation distinguishes the time to create a container from the
> time to create **usable service capacity**." — `thesis_overview.md` §5

The chain (from `thesis_overview.md` §4):

```text
Demand shift
  -> telemetry observation
  -> scaling decision
  -> capacity action
  -> backend readiness
  -> routing admission
  -> successful user request
```

**Use in thesis:** Ch.1 (define the object) + Ch.5 (define the recorded event
trace: workload onset → window completion → decision → provisioning →
readiness → admission → first success → recovery).

---

## P3 — The chain is normally built from independent components (the unexamined default)

**Claim:** every major orchestration architecture separates monitoring, routing,
and scaling into independent components with independent control loops. This is
presented as the default, never as a design choice.

| Evidence | Quote / source | Where | Strength |
|---|---|---|---|
| K8s / NFV MANO / MEC separation table | Prometheus→AlertManager / kube-proxy / HPA; OSM MON / SDN+HAProxy / OSM POL→LCM; InfluxDB / SDN / K8s scheduler | global_review §1 | `DOCUMENTED` (architecture) |
| Separation is architectural, not accidental | Okwuibe et al. (2020) — Docker+SDN+edge+MongoDB, orchestration split across 3 systems (SDN forwarding, K8s lifecycles, InfluxDB+PowerAPI monitoring) | global_review §2.7 | `DOCUMENTED` |
| MANO lacks native LB | "Well-known MANO frameworks, such as OSM and ONAP, lack native load-balancing services. Thereby, they rely on specific virtual functions (e.g., HAProxy) that need to be deployed along with the pool members." — Llorens-Carrodeguas et al. (2021) | global_review §2.7 | `DOCUMENTED` |
| Even integrated SDN steering keeps components external | Llorens-Carrodeguas et al. (2021) — OSM MON → OSM POL → OSM LCM → SDN controller, API handoffs | global_review §2.7 | `DOCUMENTED` |

**Use in thesis:** Ch.2 §The-Unexamined-Default (keep the table; reframe the
consequence as "three interfaces between separated components are where time and
quality are lost").

---

## P4 — The interfaces are documented, symptomatic, and called for — never isolated

**Claim:** the literature describes the coordination gap, observes its symptoms,
and calls for its study — in five distinct forms — but never isolates any
interface as an independent experimental variable.

### Form 1 — Documented but not measured (`DOCUMENTED`)

| Paper | Quote |
|---|---|
| Wang et al. (SDNFV) | "After synchronization completes, the proxy notifies LB-C to include the instance in session allocation." (spawn→synchronisation→LB inclusion; never varied) |
| Xu et al. (2021, NEP) | "VM placement and end-user request scheduling strategies" decoupled ⇒ "Resource usage is highly unbalanced across servers… across sites." |
| Yaseen (2025) | "SNMP polling operates on a pull-based model with periodic queries, introducing latency and potential data loss especially under congestion. This can lead to visibility gaps." |
| Podolskiy et al. (IaaS) | "The reactive nature of autoscaling solutions jeopardizes the ability of cloud applications to meet the QoS requirements under the dynamically changing load." |
| Ghorab et al. (2020) | "We believe that the load balancing algorithm affects the number of VNF instances. It is also possible that adding another instance, due to inappropriate load balancing, may not improve the poor QoS." |
| Pourghebleh et al. (2020, SD) | "the freshness of the data still remains a problem" (passing remark, not a research dimension) |

### Form 2 — Symptoms observed, cause misattributed (`SYMPTOM`)

| Paper | Symptom | Their explanation |
|---|---|---|
| Pierro & Ullah (K8s HPA) | Throughput **decreases** as pods are added | "orchestration overhead introduced by container coordination mechanisms, including increased scheduling complexity, **service discovery latency**, and load balancing distribution inefficiencies." |
| Xu et al. (NEP) | Resource imbalance across servers/sites | Workload pattern variability (not the decoupling itself) |
| Podolskiy et al. | QoS violation under load spikes | Reactive scaling is inherently slow |
| AdapPF (Huang & Pierre, 2023) | **Far more pending pods** with 60 s scraping than 5 s under high load | Contribution framed as bandwidth-saving adaptive interval, not decision-quality characterisation |

### Form 3 — Called for but not pursued (`CALLED-FOR`)

| Paper | Quote |
|---|---|
| Sofia et al. (2023, Movek8s) | Lists "data freshness" as an orchestration parameter ("Avoid processing/forwarding stale data"); "one of the key challenges in container orchestrators such as Kubernetes is to be able to provide a cross-layer orchestration, thus allowing placement decisions to occur based on real-time resource demands that relate with the application and computational nodes; with the network; and also with the data." |
| Yaseen (2025) | "Modern networks demand monitoring frameworks that are not only scalable and real-time but also tightly integrated with network control and automation." |
| Ghorab et al. (2020) | "The only work that has investigated VNF load balancing and auto-scaling in a unified manner may be [19]… and does not tune any of them to find out the effects on the whole functionality." |
| Pelle et al. (2022) | "Functions and data must be orchestrated in sync." (deployment-time only) |
| Nain et al. (2024) | "we observed that there is still room in the literature to focus on these crucial aspects of EC and the behavior of SDN while integrating with EC." |
| Qu et al. (2018) | "the database tier is often considered dynamically unscalable and ignored by auto-scalers." |

**Use in thesis:** Ch.2 — one subsection per Form (documented / symptomatic /
called-for), each ending with "never isolated or measured."

---

## P5 — Three interfaces, each with its own evidence chain

### I1 — Monitoring → decision (RQ1, telemetry delivery semantics)

| Evidence | Detail | Strength |
|---|---|---|
| **AdapPF** (Huang & Pierre, 2023) | Varies scrape interval; 60 s vs 5 s changes scheduling accuracy under high load; adaptive cadence ≈ 36% traffic saving. **The only paper that varies freshness with a measured downstream effect — for ONE consumer (a scheduler).** | `MEASURED` |
| **Yaseen** (2025) | Pull-based polling → "visibility gaps" (see P4/F1). | `DOCUMENTED` |
| **Caiza & Campoverde** (2024) | WSM multi-resource policy — closest algorithmic cousin to the thesis — describes collection only as occurring "periodically"; the period is an implementation detail, not a variable. | `TAXONOMY-GAP` |
| **Zhang & Guo** (2014) | Same "periodically" pattern, a decade earlier, unchanged. | `TAXONOMY-GAP` |
| **Belgaum et al.** (2020) | 76-paper SDN-LB review; open issues = security, controller placement, AI; **nothing about freshness**. | `SILENCE` — *inattention only, do not cite as importance* |

**The RQ1 gap statement:** AdapPF proves freshness matters for a scheduler; this
thesis isolates *which* failure — **delay but complete** (delayed
event-preserving) vs **lost intermediate evidence** (latest-state) — matters for a
*stateful service's* scaling + admission chain, and measures magnitude per mode.
No reviewed paper distinguishes the two semantics or traces them through scaling
and admission.

### I2 — Decision → capacity action (RQ2, bottleneck-aware scaling action)

| Evidence | Detail | Strength |
|---|---|---|
| **Qu et al.** (2018) | "the database tier is often considered dynamically unscalable and ignored by auto-scalers" — the data tier is a blind spot in auto-scaling. | `TAXONOMY-GAP` |
| **Pelle et al.** (2022) | "Functions and data must be orchestrated in sync" — but at deployment time, not runtime action selection. | `CALLED-FOR` |
| **Ghorab et al.** (2020) | LB and scaling interact (weighted resource signals); called for joint co-variation. | `DOCUMENTED` + `CALLED-FOR` |
| Auto-scaling literature in general | Studies *when* and *how many* to scale; monitoring is an input, not a variable; the action type (compute vs storage) is fixed by the operator. | `TAXONOMY-GAP` |
| **Ferreira et al.** (2024) — ACM CSUR, edge/fog databases | Authoritative edge-DB survey has **no elasticity/runtime-scaling axis**; DB scalability treated as static replication/sharding/placement design; "increasing the number of replicas" listed as future work. | `TAXONOMY-GAP` (citable) |
| **Wei & Wang** (2023) — popularity-based placement + LB | The *old-thesis* idea: popularity drives placement; explicitly "the placement decision is static". | `DOCUMENTED` (self-declared static) |

**The RQ2 gap statement (three claims; only the third is novel):**

1. Compute auto-scaling scales edge servers and leaves the DB tier out of the runtime control loop.
2. Edge-DB research (Ferreira et al. 2024) treats database scalability as a **static/design-time** replication–sharding–placement decision — not as runtime capacity control.
3. **No surveyed system makes a closed-loop, telemetry-driven decision of which tier — compute or storage — to scale from an observed bottleneck, and none co-locates monitoring + scaling + routing over both tiers with shared state.**

**The cost of the scaling action itself (the honest claim):** scaling the data
tier is not "just more replicas". In this apparatus the storage action is a
MongoDB member addition (`rs.add()`), which triggers **replica sync — real
bandwidth consumption and transient overload** on the new member and the existing
set. The edge-storage corpus models placement/replication *cost* as a static
objective (e.g., erasure-code cost-optimal placement, Jin et al. 2023); it does
**not** model the runtime cost of *performing* the scaling action during a live
episode. The thesis therefore measures not only relief but the **cost of the
action itself** (sync bandwidth/overload), and scopes honestly: cold, same-LAN
`rs.add/remove` only — full placement/consistency semantics are out of scope.

### I3 — Ready backend → traffic admission (RQ3, readiness propagation)

| Evidence | Detail | Strength |
|---|---|---|
| **Wang et al.** (SDNFV) | "After synchronization completes, the proxy notifies LB-C to include the instance in session allocation." — the spawn→inclusion delay is documented, never varied. | `DOCUMENTED` |
| **Pierro & Ullah** | "service discovery latency" named among orchestration-overhead symptoms. | `SYMPTOM` |
| **Pourghebleh et al.** (2020) / **Achir et al.** (2022) | SD field: "the freshness of the data still remains a problem"; the most comprehensive SD taxonomy (60+ papers) has **no category for discovery timing or registry freshness**. | `DOCUMENTED` / `TAXONOMY-GAP` |
| **The same gap, three names** (strongest cross-domain evidence) | Monitoring calls it "visibility gaps" (knowledge of *load*); SD calls it "freshness still a problem" (knowledge of *existence*); LB calls it "synchronisation-before-inclusion" (knowledge of *readiness*) — three fields, one phenomenon, no cross-citation. | `DOCUMENTED` (synthesis) |
| SDN-LB literature in general | Asks "given available backend state, which backend?" — treats pool availability/readiness as established fact. | `TAXONOMY-GAP` |

**The RQ3 gap statement:** no study isolates the path from a backend becoming
application-ready to it becoming *eligible to receive traffic*, holding the
backend-selection function fixed. (Warm-lease priority and slow-start ramps are
held constant; only the **propagation mechanism** — direct lifecycle notification
vs periodic discovery — varies.)

**Use in thesis:** Ch.2 — one subsection per interface (I1/I2/I3), each ending
with its RQ and gap statement above.

---

## P6 — The question was structurally unaskable in any existing platform

**Claim:** no platform has ever co-located monitoring, routing, and scaling as
explicit, independently tunable functions, so the interface questions could not
be asked.

| Evidence | Detail | Strength |
|---|---|---|
| Paradigm mapping (Serverless / Offloading / Data-Sync / IoT / Container) | Serverless has all three but "bundled opaquely inside the platform — none exposed as tunable dimensions"; every other paradigm omits at least one function. | global_review §6.1 | `DOCUMENTED` |
| Closest attempts table | Hung et al. (monitoring+routing only); Carella CLO (App↔Network, no scaling); Sofia Movek8s (extends K8s, cannot co-locate); Ghorab (joint LB+scaling, separate components). | global_review §6.2 | `DOCUMENTED` |
| **SEND** (Nicolaescu et al. 2021) — closest co-location precedent | Logically centralized control point (e.g., an SDN controller) ingests periodic stats and makes runtime data-placement **and** function-instantiation decisions — monitoring + placement co-located. **Lacks:** resource-tier scaling and routing/LB admission. Cite and delimit: 2 of the 3 functions, never the full triple. | `DOCUMENTED` (adjacency) |
| Three structural reasons | (1) independent toolchain evolution; (2) each field's abstraction served its question (LB: "given accurate state, which backend?"; scaling: "when/how many?"; monitoring: "how to collect efficiently?"); (3) no single configuration interface exposes cadence + routing + trigger as co-variable dimensions. | global_review §6.3 | `FRAMING` (synthesis) |

**Use in thesis:** Ch.2 final subsection + Ch.3 (the architecture is the answer
to "structurally unaskable": a single process with shared state where each
interface is a configurable variable).

---

## P7 — The contribution is a characterization, not a superiority claim

**Claim (what the thesis claims / does not claim):**

- **Claims:** within the evaluated two-domain stateful edge testbed and workload
  families, the three control-loop interfaces affect observable service behaviour
  (latency, failures, timing to usable capacity, node-minutes).
- **Does not claim:** SDN/K8s superiority; co-location universally better than
  separation; generalisation to every workload/topology; meeting a real SLA;
  production-readiness or fault tolerance; Tier 0/1/2 placement as the main
  contribution. (`thesis_overview.md` §9)

**Use in thesis:** Ch.1 contributions + Ch.7 conclusions/limitations. Keeps
reviewers from reading a superiority claim the thesis never makes.

---

## The freshness evidence hierarchy (correction note — keep visible)

Never order these as if they were equal evidence:

1. **AdapPF** — `MEASURED` (5 s vs 60 s affects scheduling accuracy; 36% traffic saving). Proves freshness matters **for one consumer (a scheduler)**.
2. **Yaseen** — `DOCUMENTED` (pull polling → visibility gaps). Strong conceptual.
3. **Usman et al. (2022)** — "appropriate measurement intervals" on constrained edge is explicitly unresolved (open problem; verify exact wording/DOI before quoting).
4. **Belgaum (2020) silence** — `SILENCE`/inattention only. Use as a *scope boundary* ("even a 76-paper review has no dimension for this"), **never** as evidence of importance.

**The honest motivation:** *AdapPF proved freshness matters for a scheduler. We
ask whether it matters for a stateful edge service's scaling + admission chain,
and we measure magnitude and mechanism per interface — which AdapPF did not do.*

---

## Demand model and the justification of variable demand

*For "how do I prove variable demand exists and matters" — the three-layer
answer (details in conversation notes; the thesis must contain this reasoning).*

1. **Existence in the world** → delegated to workload-characterisation literature
   (families to verify before citing: web/cloud burstiness & self-similarity —
   Crovella–Bestavros; classic web traces — Arlitt–Williamson; datacenter —
   Benson et al.; cloud cluster traces — Mishra/Reiss et al.; autoscaling surveys
   premised on variability — Lorido-Botrán et al. 2014). The thesis *adopts* the
   premise; it does not re-establish it.
2. **Existence in the apparatus** → the imposed phases profile, quantified
   (from `docs/operation/testing/experiment/v2/rq1_experiment/phases_rq1_delivery.json`):

   | Phase | dur (s) | rate/client | client frac | **aggregate** | mix note |
   |---|---|---|---|---|---|
   | baseline | 60 | 1.0 | 0.10 | **0.10** | lookup .60 / ranking .25 / pressure .15 |
   | overload_surge | 150 | 5.0 | 1.00 | **5.00** | lookup .80; +update/aggregate ops |
   | drain_1 | 60 | 0.5 | 0.05 | 0.025 | service mix |
   | demand_drop | 150 | 0.3 | 0.05 | 0.015 | quiescent |
   | tail | 60 | 0.5 | 0.05 | 0.025 | quiescent |

   Derived properties to *report* (not assert): **peak-to-baseline ≈ 50×**;
   **composition shift** (the surge is differently-shaped traffic, enabling RQ2);
   **duty cycle** (surge ≈ 31% of run, long recovery tail); **step transitions**
   (harsher than real ramps — state it, or add a ramp axis); **spatial dimension
   absent** (`cross_region_ratio = 0.0` — temporal + compositional variability only).
3. **Importance** → (a) *logical*: the interface treatments vary only the recovery
   mechanism, so **any between-arm difference is direct evidence that variability
   is consequential**; (b) *absolute magnitude*: a **static/no-adaptation control
   arm** (currently absent — recommend adding) under the same 50× profile shows
   how much worse than *no adaptation* the reactive path is (under-provision →
   latency/failures; over-provision → wasted node-minutes).

**Non-claim:** the profile is not production traffic; it *instantiates variability
types documented in the literature*. The thesis claims mechanism-level, not
workload-level, validity.

---

## Where each piece lands in the manuscript

| Purpose step | Manuscript location |
|---|---|
| P1 (edge, latency-sensitive, varying demand) | Ch.1 §Context-Motivation; Ch.5 §Demand model |
| P2 (demand → usable capacity) | Ch.1 (object of study); Ch.5 §Event trace |
| P3 (three-layer separation) | Ch.2 §The-Unexamined-Default |
| P4 (documented/symptomatic/called-for) | Ch.2 §Per-Form subsections |
| P5-I1 / I2 / I3 (interface evidence) | Ch.2 §Monitoring, §Auto-Scaling, §SDN-LB → RQ1/RQ2/RQ3 |
| P6 (structurally unaskable) | Ch.2 §Synthesis; Ch.3 (architecture as answer) |
| P7 (characterization, not superiority) | Ch.1 §Contributions; Ch.7 §Limitations |
| Freshness hierarchy | Ch.2 §Monitoring (footnote-level honesty) |
| Demand model | Ch.5 §Evaluation scenarios; Ch.1 motivation |

---

## Source pointers

- Framing: `tese/Notes/thesis_overview.md` (§1–§10).
- Evidence corpus with forms/gap matrix: `tese/literature_review/global_literature_review.md`
  (§1 three-layer default; §2 Form 1; §3 Form 2; §4 Form 3; §5 Form 4 incl. the
  "same gap, three names" table; §6 Form 5; §7 summary + gap matrix).
- Per-domain State of the Art and paper analysis: the six domain READMEs under
  `tese/literature_review/`.
- BibTeX: `tese/references.bib` (all papers above have entries).
- Imposed demand profile: `docs/operation/testing/experiment/v2/rq1_experiment/phases_rq1_delivery.json`.
