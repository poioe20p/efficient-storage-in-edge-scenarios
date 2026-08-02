# RQ2 — Bottleneck-Aware Scaling Action

> **Status:** 2026-07-31 · idea-provenance document (current framing).
> **Framing source:** `tese/Notes/thesis_overview.md` §6-RQ2.
> **Related:** `tese/Notes/purpose_evidence_map.md` (I2, P4, P5, P6); `tese/literature_review/global_literature_review.md` (§2.5, §4.4, §10).
> **Legacy:** the older "backend-selection policy modes (host/slowstart/lifecycle)" framing and `Notas.txt` are superseded by `thesis_overview.md` §5.

---

## 1. Research question

> **Under compute-bound and data-access-bound demand, does a bottleneck-aware controller — choosing the scale-out action (compute or storage) from tier telemetry — recover service quality and use resources more efficiently than the single-tier fixed policies an operator would otherwise configure (compute-only or storage-only)?**
>
> Working restatement of `thesis_overview.md` §6-RQ2 (which uses the original "workload-agnostic fixed-priority policies when both actions are available" wording). The comparison is a **value-of-information** study: the fixed policies are the status quo an operator would configure, not a strawman.

## 2. Position in the chain

This RQ studies the **decision/action interface** of the control loop:

```text
Demand shift
  -> telemetry observation
  -> [RQ2] scaling decision + action selection  <-  this RQ
  -> capacity action
  -> backend readiness
  -> routing admission
  -> successful user request
```

Held fixed: action availability, per-tier resource caps, action budget, cooldowns, telemetry delivery (RQ1's event-preserving reference), backend-admission condition. Only *which capacity action the controller chooses* varies.

---

## 3. Where the idea stems from (the basis)

The seed is a simple realistic observation:

> **"Everyone scales edge servers. But a stateful service also bottlenecks on its data path — and when the database is the bottleneck, adding edge servers doesn't just fail to help, it pushes more requests into a saturated database."**

The papers that ground this RQ:

| Paper | What it establishes | Strength | Role in the basis |
|---|---|---|---|
| **Qu et al. (2018)** — auto-scaling taxonomy | *"the database tier is often considered dynamically unscalable and ignored by auto-scalers."* | `TAXONOMY-GAP` | The data tier is a blind spot in auto-scaling — the core premise. |
| **Pelle et al. (2022)** | *"Functions and data must be orchestrated in sync."* | `CALLED-FOR` | The compute+data coupling is recognised — but only at deployment time, not runtime action selection. |
| **Ghorab et al. (2020)** | LB and scaling interact (weighted CPU/memory signals); *"adding another instance, due to inappropriate load balancing, may not improve the poor QoS."* | `DOCUMENTED` + `CALLED-FOR` | Scaling the *wrong thing* is a real, described failure; called for joint co-variation, never tuned. |
| **Ferreira et al. (2024)** — ACM CSUR, edge/fog databases | The authoritative edge-DB survey has **no elasticity/runtime-scaling axis**; DB scalability treated as static replication/sharding/placement; "increasing the number of replicas" is future work. | `TAXONOMY-GAP` (citable) | **The DB-side citation for the gap:** DB literature treats DB scaling statically, so runtime DB scaling is genuinely open. |
| **Wei & Wang (2023)** — popularity-based placement + LB | The thesis's *former* idea: popularity drives placement; explicitly *"the placement decision is static."* | `DOCUMENTED` (self-declared static) | Old-idea ancestor; must be cited and distanced. |
| **Jin et al. (2023)** — erasure-code cost-optimal placement | Static placement minimising storage *cost* (ILP, simulation). | `DOCUMENTED` | Shows the corpus models placement *cost* statically — not the runtime cost of *performing* a scale action. |
| **Malazi et al. (2022)** — Dynamic Service Placement SLR | "Dynamic" = re-placement over time from workload prediction — a deployment/decision-time construct, not runtime compute-vs-storage tier choice. Also: few works handle *bursty/non-stochastic* demand. | `DOCUMENTED` | Nearest neighbor to "dynamic"; must be delimited. Its demand critique supports the controlled-demand design (C5). |
| **Taleb et al. (2025)**, **Sonkoly et al. (2021)**, **Torabi et al. (2022)**, **Bahrami et al. (2023)**, **Kaur et al. (2022)** | Placement surveys/reviews; most proposals are static; online/runtime resource allocation is flagged as an open issue. | `DOCUMENTED` | Reinforce the static-placement premise (see `global_literature_review.md` §10.4). |

### The gap statement (three claims; only the third is novel)

1. Compute auto-scaling scales edge servers and leaves the DB tier out of the runtime control loop.
2. Edge-DB research (Ferreira et al. 2024) treats database scalability as a **static/design-time** replication–sharding–placement decision — not as runtime capacity control.
3. **No surveyed system makes a closed-loop, telemetry-driven decision of which tier — compute or storage — to scale from an observed bottleneck, and none co-locates monitoring + scaling + routing over both tiers with shared state.**

### The cost of the scaling action itself (the honest claim)

Scaling the data tier is **not "just more replicas"**. A MongoDB member addition (`rs.add()`) triggers **replica sync — real bandwidth consumption and transient overload** on the new member and the existing set. The corpus models placement/replication *cost* as a static objective (e.g., Jin et al. 2023); it does **not** model the runtime cost of *performing* the scaling action during a live episode. RQ2 therefore measures **relief and the action's own cost** (sync bandwidth/overload), scoped honestly to cold, same-LAN `rs.add/remove` — full placement/consistency semantics are out of scope.

---

## 4. Experiment design (summary)

Three policies, both actions always available:

1. **Compute-first** fixed priority (counterbalanced baseline).
2. **Storage-first** fixed priority (counterbalanced baseline).
3. **Bottleneck-aware** — selects the action from tier-specific telemetry.

Compute-bound and data-access-bound episodes are **constructed and validated independently** of the policy outcome. A policy gate selects one action from a declared bottleneck classification and logs: induced episode label, evidence, selected action, rejected action, action budget. Tier 1, prepared storage reserves, and cross-region placement are disabled.

### What the fixed policies are (concrete semantics)

From the `PolicyGate` design in `docs/research_questions/v2/rq2/rq2_preparation.md` (L175–177):

```text
fixed_compute_first: ("compute",)   if compute_v.fired else ()
fixed_storage_first: ("storage",)   if storage_v.fired else ()
bottleneck_aware:    both fired → classify(); one fired → that tier
```

- **`fixed_compute_first`** = *only ever scale the compute tier*: when the compute signal breaches, submit an edge-server add; **never** scale storage; if the compute signal does not fire, do nothing.
- **`fixed_storage_first`** = the mirror: *only ever scale the storage tier* (`rs.add()`), never compute.
- **`bottleneck_aware`** = classify the bottleneck from tier-specific telemetry (with a pre-registered margin `BOTTLENECK_CLASSIFY_MARGIN`) and submit the matching action.

| Episode | compute-first | storage-first | bottleneck-aware |
|---|---|---|---|
| **compute-bound** (compute signal fires) | adds compute → relief ✓ | adds storage → no relief, **wasted sync bandwidth** ✗ | adds compute → relief ✓ |
| **data-access-bound** (storage signal fires) | compute may not fire → **does nothing**; service stays degraded ✗ | adds storage → relief ✓ | adds storage → relief ✓ |
| **both / mixed** | adds compute only (partial) | adds storage only (partial) | classifies → selects the pressured tier(s) |

The middle row is the heart of the claim: a compute-only controller has **no signal path to storage pressure** — the "leaves the DB tier out of the runtime loop" gap made concrete. The action budget (`ACTION_BUDGET_PER_TIER`, default 4) caps actions per tier, so a fixed arm's *wasted* actions also surface in efficiency (node-minutes, sync overhead). Bottleneck-aware can still misclassify (the margin is finite) — the comparison is informative, not rigged.

### Primary measurements

Time to recover the bottleneck-specific pressure · time to usable capacity · p50/p95/p99 latency · failures and completed offered demand · compute and storage node-minutes · number of scale actions · whether the selected action produces measurable relief in the targeted tier · **cost of the action itself (replica-sync bandwidth and transient overload)**.

### Required extension (implementation)

Policy gate that selects one scaling action from a declared bottleneck classification, with full decision logging (episode label, evidence, selected/rejected action, action budget).

---

## 5. Honesty / scope notes

- Does **not** claim multi-metric triggers are new (Ghorab, Zhou & Yong already use weighted/custom metrics). The novel axis is **which capacity action** is taken, not which metric triggers.
- The comparison is a *decision-quality* characterisation (does telemetry-driven selection actually pick the right action, and what does a wrong action cost?), not a "smart vs strawman" comparison.
- The storage action is deliberately the simplest possible data action (cold, same-LAN `rs.add/remove`) to keep it a single variable; the action's own cost is measured, not assumed free.
- Any *between-arm difference* is evidence that the decision interface is consequential.

### Why this isn't tautological (defense against the "obviousness" objection)

> Choosing to scale the bottleneck tier is trivially correct only given **perfect
> bottleneck knowledge, free/instant actions, and a static bottleneck**. In a live
> stateful service all three fail: the bottleneck must be *classified* from noisy,
> delayed, tier-specific telemetry; a storage action carries real replica-sync cost;
> and pressure can migrate between tiers as actions take effect. RQ2 therefore does
> not test *whether* the right resource is better — it tests whether a controller can
> reliably **detect** the right resource from the telemetry it already has, and whether
> that detection is worth more than the cost of being wrong.

**The obvious part vs. the measured part:**

| Obvious (not what we test) | Non-trivial (what RQ2 measures) |
|---|---|
| If you knew the bottleneck, scale that tier | The controller must **infer** the bottleneck from windowed, aggregated counters; the degradation score (CPU 40% + latency 60%) cannot by itself distinguish compute-bound from data-access-bound pressure |
| "Right resource" is a clean binary | Pressure is **mixed and can shift** — scaling compute can push more requests into a saturated data path, moving the bottleneck |
| Actions are free and instant | **Storage actions are expensive** (`rs.add()` → replica sync: bandwidth + transient overload); compute actions are cheap — acting is a cost/benefit call, not a free pick |
| The status quo is "scale the right resource" | The status quo is **always scale compute**; the question is whether the machinery to make the obvious choice *possible* (classification + action gate) is worth anything |

**Plausible null outcomes (why the result is genuinely uncertain):**

- The testbed workload is mostly compute-bound anyway → storage-first rarely matters and the added complexity buys nothing.
- Classification is too noisy under the aggregation windows → the selector acts on wrong labels as often as right ones.
- The storage action is so slow/expensive (replica sync) that acting on it never beats doing nothing or adding compute + letting routing adapt.
- Cooldowns / scale-down gate the benefit away before it materializes.

**Value-of-information framing:** this is the same shape as AdapPF in RQ1's corpus —
that *freshness* degrades scheduling is not profound, but its magnitude had to be
measured. RQ2 measures the sibling quantity: how much *imperfect, delayed,
tier-specific information* about which tier to scale is worth in a live system.

---

## 6. Papers to cite in related work (Ch.2)

Qu et al. (2018) · Pelle et al. (2022) · Ghorab et al. (2020) · **Ferreira et al. (2024)** · **Wei & Wang (2023)** · Jin et al. (2023) · Malazi et al. (2022) · Taleb et al. (2025) · Sonkoly et al. (2021) · Torabi et al. (2022) · Bahrami et al. (2023) · Kaur et al. (2022) · plus the Auto-Scaling and Edge Storage README SOTA.

## 7. Cross-references

- Purpose map: `tese/Notes/purpose_evidence_map.md` → I2 (interface evidence + 3-claim gap + action-cost), P6 (SEND delimitation).
- Global review: `tese/literature_review/global_literature_review.md` → §2.5 (LB/scaling interaction), §4.4 (joint compute+data), **§10 (Edge Storage threat assessment)**.
- Thesis structure: `tese/Notes/thesis_structure.md` → §0.3 (action-cost guard), §2.8 (Edge Storage corpus), §5.3 (metrics).
- Implementation plan (docs): `docs/research_questions/v2/rq2/rq2_preparation.md`.
