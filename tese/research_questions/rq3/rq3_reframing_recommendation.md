# RQ3 Reframing Recommendation — From Notification Transport to Usable-Capacity Realization

> **Status:** proposed reframing, 2026-09-06.
> **Scope:** conceptual and literature review only. This document does not alter the frozen RQ3 treatments, metrics, or low-headroom campaign contract.

## 1. Decision

A broader and better-supported premise exists:

> **Horizontal scale-out is not complete when a backend is created or even when it becomes application-ready. It is complete only when the backend is safely admitted to the routing path, receives traffic, and begins relieving incumbent capacity.**

RQ3 should therefore be based on **usable-capacity realization during a dynamic membership transition**, specifically the handoff from backend lifecycle completion to load-balancer admission and traffic contribution.

Direct lifecycle notification and periodic discovery remain legitimate experimental treatments, but they become **two implementations of readiness-admission coordination**, not the intellectual premise of the RQ.

This distinction removes the weak or nearly tautological formulation “is an immediate event faster than waiting for a timer?” The substantive question becomes whether coordination delay leaves ready capacity dark long enough to delay incumbent relief or degrade service when headroom is limited.

## 2. Why the current premise is too narrow

The existing direct-versus-polling formulation has three limitations:

1. Under identical readiness semantics and reliable delivery, immediate notification is expected to beat a periodic scan on admission latency by construction.
2. It elevates a transport implementation choice to the level of the research problem, obscuring the cross-layer problem that scaling and traffic activation are separate steps.
3. It encourages an unjustified universal conclusion that direct notification is “better,” although polling provides loose coupling and state reconciliation while event-driven operation requires delivery, restart-recovery, deduplication, and fallback semantics.

The completed timing evidence remains valid. The change is interpretive: it quantifies one implementation of the **readiness-to-service handoff**, rather than attempting to establish a universal event-versus-polling preference.

## 3. Literature basis

### 3.1 Convergent premise across the selected papers

| Source                                                           | Directly supported concept                                                                                                                                                                                                                                              | Role in the revised premise                                                                                                                         | Claim boundary                                                                                                                                                                       |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Belgaum et al. (2020)                                            | Dynamic load balancing responds to changing requirements; its objectives include response time, throughput, resource use, and overhead.                                                                                                                                 | Establishes that membership and traffic decisions must adapt at runtime and be judged by system outcomes.                                           | A survey of selection techniques; it does not study backend readiness.                                                                                                               |
| Llorens-Carrodeguas et al. (2021)                                | Load-balancing and auto-scaling policies should be aware of one another to improve QoS and resource efficiency. Their controller combines monitoring, scaling, and load balancing, activates new instances, and directs traffic only to healthy VNFs.                   | Strong basis for treating scale-out and traffic activation as a coordinated lifecycle rather than independent functions.                            | It reports activation at coarse granularity and does not isolate verified-readiness-to-admission latency.                                                                            |
| Neghabi et al. (2018)                                            | Periodic controller synchronization trades synchronization overhead against intervals of state desynchronization, which can produce black holes or forwarding loops.                                                                                                    | Supports freshness/consistency as a general control-state trade-off.                                                                                | The discussed state is multi-controller network state, not application readiness; use only as an adjacent analogy.                                                                   |
| Abdelltif et al. (2018)                                          | A transition algorithm applies new server weights while deciding whether existing connections remain on the previous server and new flows use the new selection.                                                                                                        | Shows that load-balancer reconfiguration is a transition requiring explicit flow-safe handling, not an instantaneous pool update.                   | No autoscaling or readiness treatment is isolated.                                                                                                                                   |
| Bogdanov et al., Kurma (2018)                                    | Provisioning delay includes detecting demand, acquiring/starting instances, and warming/integrating them into a working cluster. The paper connects this delay to SLO violations and wasteful over-provisioning and uses fast redistribution while capacity catches up. | Strong basis for defining scale-out completion at usable service capacity and assessing both SLO and resource consequences.                         | Geo-distributed storage redirection differs from intra-domain compute-backend admission.                                                                                             |
| Ni et al., SmartLB (2021), DOI 10.1109/NFV-SDN53031.2021.9665167 | After an NF is initialized, the manager sends a scale signal; the SmartNIC activates the port, recomputes weights, assigns new flows, preserves affinity, and rebalances traffic in less than two seconds in its experiment.                                            | Closest direct precedent for an initialized instance crossing an autoscaler/load-balancer handoff before it contributes traffic.                    | It reports the combined process and does not isolate the post-readiness handoff or compare admission semantics/headroom regimes. This paper is not yet present in`references.bib`. |
| AlKhatib, Sawalha, and AlZu'bi overview (2020)                   | Describes current/new server selections plus a transient flow table used while servers are reconfigured.                                                                                                                                                                | Secondary support for treating membership changes as a transition state.                                                                            | Overview-level evidence; not a readiness or autoscaling evaluation.                                                                                                                  |

### 3.2 Corrected research gap

The literature does **not** support saying that dynamic membership transitions are entirely unmeasured. Llorens-Carrodeguas et al. report instance activation, and SmartLB measures a scale-up-to-rebalancing process.

A narrower and defensible gap is:

> Prior work establishes that auto-scaling and load balancing must be coordinated, incorporates instance integration into provisioning delay, and implements lifecycle-safe membership transitions. However, within the reviewed corpus, these systems are evaluated as integrated designs: they do not isolate the **post-readiness handoff from lifecycle completion to actual traffic contribution** while holding the readiness criterion, scaling action, backend-selection function, workload, and resource limits constant. Nor do they test whether delay at that handoff becomes a transient service-quality cost when incumbent headroom is constrained.

That is the gap the current apparatus and low-headroom extension can address.

## 4. Recommended conceptual model

```text
Demand increase
  → overload observation
  → scale decision
  → backend provisioning
  → verified application readiness
  → readiness-admission handoff       [RQ3 treatment]
  → routing-pool eligibility
  → first useful traffic
  → incumbent-load relief
  → service recovery
```

The key intermediate state is **ready-but-dark capacity**: a backend that satisfies the common servability criterion but is not yet eligible for traffic. RQ3 asks how the duration of this state affects scaled-capacity realization and whether its consequences depend on available headroom.

### Constructs

- **System problem:** realizing usable capacity during horizontal scale-out.
- **Interface studied:** lifecycle/readiness state to routing admission.
- **Experimental factor:** readiness-admission coordination semantics.
- **Implementations compared:** lifecycle-coupled immediate admission and periodically reconciled admission.
- **Mediator:** duration of ready-but-dark capacity.
- **Outcomes:** readiness-to-admission delay, decision-to-first-success time, incumbent CPU relief, and transition-window service quality.
- **Boundary condition:** incumbent compute headroom.
- **Supporting robustness condition:** total lifecycle-event-source absence and fallback liveness; not selective event loss.

## 5. Recommended RQ wording

### Preferred concise wording

> **RQ3 — During compute scale-out in an edge service, how does readiness-admission coordination affect the realization of usable capacity, incumbent-backend relief, and transient service quality when incumbent compute headroom is constrained?**

The methods section should then identify the two operational treatments:

> Readiness-admission coordination is operationalized as (i) lifecycle-coupled admission immediately after the shared servability criterion is verified and (ii) admission when the same state is observed by periodic reconciliation.

### More explicit alternative

> **RQ3 — For newly provisioned compute backends satisfying an identical servability criterion, how do lifecycle-coupled and periodically reconciled readiness admission affect scaled-capacity realization, measured by activation delay, incumbent-load relief, and transition-window service quality?**

### Useful decomposition

- **RQ3a — Realization delay:** How long after verified readiness does new capacity become routing-eligible and serve its first successful request?
- **RQ3b — Operational consequence:** Under constrained headroom, does ready-but-dark capacity prolong incumbent pressure or degrade transition-window service quality?
- **RQ3c — Supporting robustness:** When the lifecycle event source is absent, does fallback reconciliation preserve eventual admission, and what observed delay/QoE cost accompanies it?

RQ3c must remain supporting evidence unless the event-absence cell is replicated as an inferential campaign.

## 6. Fit with existing evidence

| Evidence                             | What it supports under the revised premise                                                                                                                                                       | What it does not support                                                                                                                                             |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Completed direct/discovery campaigns | The admission mechanism changes ready-to-admit and decision-to-first-success timing; newly admitted compute capacity serves traffic and relieves incumbents.                                     | Universal superiority of event-driven systems; architecture-level superiority of co-location.                                                                        |
| Original P4 regime                   | Ready-but-dark delay existed, but the tested platform absorbed it without gap-window timeout/failure harm.                                                                                       | A claim that the delay is harmless under all loads or infrastructures.                                                                                               |
| Low-headroom extension               | If completed, tests whether the realization delay becomes a p95/timeout/failure consequence when incumbents have little reserve. The plateau-ready anchor makes the treatment window measurable. | Until completion, no low-headroom consequence can be claimed. A cross-regime causal interaction should not be overstated without comparable analysis across regimes. |
| Event-source-absence cell            | Can demonstrate fallback liveness and describe observed cost under total producer absence.                                                                                                       | Robustness to selective loss, duplication, reordering, controller restart, or arbitrary network partitions.                                                          |

### Interpretation of possible low-headroom outcomes

- **Positive QoE contrast:** at the tested quota/workload, delayed admission consumed the available resilience margin. Immediate lifecycle-coupled admission reduced the transient cost of converting ready capacity into serving capacity.
- **Null QoE contrast:** the timing advantage remains real, but the tested service still absorbs it; no user-facing preference is established for that regime.
- **Mixed contrast:** treat headroom/workload as a boundary condition and report heterogeneity rather than a universal mechanism ranking.

## 7. Alternative premises that require new treatments

These are conceptually valid but cannot be inferred from the current direct/discovery binary.

| Alternative question                                      | Minimum new treatments required                                                                 | Why current evidence is insufficient                                                                 |
| --------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Lifecycle safety versus activation speed                  | Optimistic admission before verified readiness vs readiness-gated admission                     | Both current arms share the same readiness gate, so safety is held constant rather than manipulated. |
| Immediate versus progressive traffic activation           | Full-weight admission vs slow-start/ramped admission                                            | Warm-lease priority and ramps are disabled in both current arms.                                     |
| Timeliness versus convergence robustness                  | Event-only, polling-only, and event-plus-reconciliation under controlled loss/restart cases     | The planned cell covers total event-source absence only and has descriptive n=2 scope.               |
| Integrated versus separated control planes                | Co-located handoff vs an explicit remote/brokered or independently operated control-plane arm   | Both current treatments run in the same co-located apparatus.                                        |
| SLO-aware redistribution during provisioning              | No redistribution vs temporary local/cross-domain redistribution while new capacity initializes | The current treatment changes admission timing, not a Kurma-like redistribution policy.              |
| Membership consistency under controller desynchronization | Controlled stale/partitioned controller-state cases                                             | The current discovery lag is not evidence of multi-controller consistency faults.                    |

If the objective is a genuinely new, non-binary RQ rather than a stronger interpretation of existing evidence, the best redesign is **event-only vs periodic reconciliation vs hybrid event-plus-reconciliation under controlled event loss and restart**. It directly tests the timeliness–robustness trade-off, but it requires a new campaign and should not be reconstructed from the existing data.

## 8. Recommended thesis changes after approval

1. Replace the premise “direct notification versus polling” with **usable-capacity realization through readiness-admission coordination** in the Introduction, RQ statement, contribution, and Results discussion.
2. Keep direct and periodic mechanisms explicit in Experimental Design as operational treatments; do not hide or rename the manipulated factor.
3. Revise claims that the membership transition “remains unmeasured.” SmartLB measures a combined transition; the defensible claim is that the post-readiness handoff has not been isolated under controlled invariants.
4. Move Ni et al. (SmartLB) from background reserve into the core RQ3 related work and add its BibTeX entry.
5. Use Llorens-Carrodeguas, Kurma, and SmartLB as the main conceptual chain; use Belgaum/Neghabi/Abdelltif as delimiting or supporting sources.
6. Present direct notification as the faster tested coordination implementation, not as universally superior. The practical recommendation should be event-driven activation plus periodic reconciliation/fallback when both low latency and convergence are required.
7. Do not state the low-headroom implication as a finding until the quota screen, main paired runs, and validity gates are complete.

## 9. Bottom line

The strongest revised premise is not “push beats polling.” It is:

> **Elastic capacity has no operational value until the routing plane safely turns it into serving capacity; the coordination delay in that handoff consumes time and potentially the system's headroom.**

This premise is broader, is supported jointly by the selected literature, preserves the validity of the completed RQ3 evidence, and gives the low-headroom campaign a non-trivial purpose: determining when a measured capacity-realization delay becomes an observable service consequence.
