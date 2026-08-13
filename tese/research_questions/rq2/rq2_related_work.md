# RQ2 — Related Work Positioning

> **Status:** 2026-08-13 · literature positioning for RQ2's contribution.
> **Updated:** 2026-08-13 · extracted from `tese/literature_review/02_action_selection_rq2/README.md`
> (the RQ2 state-of-the-art ledger) and `tese/literature_review/global_literature_review.md` (§2.5, §4.4, §10).
> **Related:** [`rq2.md`](rq2.md) §3 (the basis table, seed ideas);
> [`rq2_conclusions.md`](rq2_conclusions.md) (evidence and claim framing);
> `tese/literature_review/02_action_selection_rq2/README.md` (per-paper ledger, includes "What NOT to claim").
> **Role:** the "what's already done / what's missing / where we land" comparison for the Ch.2
> auto-scaling + edge-storage related-work section, and for positioning the contribution in the viva.

---

## 1. What the papers touching this topic claim and contribute

The papers that touch RQ2's slice — compute vs storage capacity action at the edge — each do a piece of it.
The per-paper evidence, with what each explicitly does **not** do (the delimiters that define RQ2's gap):

| Paper | Claim / contribution | What they explicitly do **not** do (the gap) |
|---|---|---|
| **Qu, Calheiros & Buyya 2018** — auto-scaling taxonomy (ACM CSUR) | Canonical auto-scaling taxonomy; documents that the DB tier is *"often considered dynamically unscalable and ignored by auto-scalers"* | Doesn't test delivery semantics or compute-vs-storage choice; the DB remark characterizes surveyed work, not proof |
| **Li et al. 2020** — heterogeneity-aware elastic provisioning (FGCS) — **closest RQ2 precedent** | Provisions cloud instances **and** data replicas jointly, from **forecast** workload (hybrid ARIMA/BP) | Forecast-driven, **never from a live observed bottleneck**; measures cost/utilization, not user-visible latency or usable capacity |
| **Nicolaescu et al. 2021 (SEND)** — INFOCOM | Logically centralized manager ingests periodic stats → decides data relocation/replication + function placement + routing (co-location over data and functions) | Has monitoring + placement, but **no resource-tier scaling and no routing admission** — not a compute-vs-storage capacity action from a bottleneck |
| **Ferreira, Coelho & Pereira 2024** — edge/fog DB survey (ACM CSUR) | Authoritative DB-side survey; DB scalability treated largely as replication/sharding/placement **design** | Discusses replication and FaaS scaling, but does not study bottleneck-selected tier action |
| **Malazi et al. 2022** — MEC dynamic service placement SLR (IEEE Access) | "Dynamic" placement = re-placement/relocation from prediction, lifecycle, forwarding | Not runtime compute-vs-storage tier choice |
| **Toka et al. 2021** — ML-based scaling for K8s edge clusters (IEEE TNSM) | ML-based edge scaling, formal HPA model; treats metrics→HPA pipeline as fixed infrastructure | **Compute-only**; no storage action or bottleneck classification |
| **Tong et al. 2026 (SynScale)** — IEEE TSC | Spatiotemporal collaborative autoscaling (multi-agent RL); instance counts ±2, fixed 30 s interval | Compute-only; "storage" = per-server container disk, not a DB tier; simulated |
| **Breitbach et al. 2019** — context-aware data/task placement (IEEE PerCom) | Runtime MAPE loop creates data replicas when queuing time crosses a threshold (real testbed, n-replication spectrum) | Adapts only **data** replicas at runtime; does not choose compute-vs-storage from a bottleneck; no SDN/routing |

> **Cross-check with `rq2.md` §3.** The basis table there adds the seed-side citations
> (Pelle et al. 2022 — "functions and data must be orchestrated in sync"; Ghorab et al. 2020 —
> LB/scaling interaction, "adding another instance … may not improve the poor QoS"; Wei & Wang 2023;
> Jin et al. 2023; Taleb/Sonkoly/Torabi/Bahrami/Kaur placement reviews). Those reinforce the same
> two premises: (i) the DB tier is a blind spot in auto-scaling, and (ii) the corpus models placement
> and scaling costs statically. The ledger above is the RQ2-specific SOTA slice; §3 of `rq2.md` is
> the idea provenance. Both are consistent with the same gap statement (§3 below).

## 2. Where RQ2 actually sits relative to these

The honest reading: RQ2's slice is **narrow but specific**, and the closest neighbors already do adjacent things.

1. **vs Li et al. (closest):** Li already does *joint compute+data provisioning*. The differentiator is
   **forecast-driven vs live-observed-bottleneck-driven**. That is a real difference: forecast provisioning
   cannot react to an unforecasted regime shift — RQ2 measures whether telemetry-driven selection works when
   you *can't* predict. This is the value-of-information contribution.
2. **vs Breitbach et al.:** runtime *data* scaling is **not** new (Breitbach adapts replicas at runtime from a
   threshold — the ledger explicitly warns "do NOT say deployment-time only"). What's new is the **selection
   between the two tiers** from the observed bottleneck — Breitbach never chooses *which* tier.
3. **vs SEND:** co-location of monitoring+placement+routing over data/functions is **not** new. What SEND
   lacks is the **resource-tier scaling action** — RQ2 adds the scaling-decision layer over the shared state.
4. **vs compute-only (Toka, SynScale):** they scale only compute; RQ2 is the *measured* case of leaving the DB
   tier out vs including it — the DB blind spot made concrete.

## 3. The gap statement (thesis-ready)

> Auto-scaling research optimises *when* and *how many* instances to create, leaving the capacity-action type
> (compute vs storage) as an architectural given (Qu et al.; Toka et al.; SynScale). Edge-storage research treats
> database elasticity as design-time replication/sharding/placement (Ferreira et al.) or as forecast-driven
> provisioning (Li et al.), and the closest co-location precedent (SEND) omits resource-tier scaling and routing
> admission. **Within the reviewed corpus, no system selects the capacity action — compute or storage scale-out —
> from a live observed bottleneck while sharing monitoring, scaling, and routing state.** RQ2 compares fixed-priority
> and bottleneck-aware policies under validated compute-bound and data-access-bound episodes, and measures the cost
> of the storage action itself (`rs.add()` replica sync), which the corpus models only statically.

Two contributions follow from this:

- **C1 — the selection step:** telemetry-driven choice of *which* tier to scale, from a live observed bottleneck,
  over shared monitoring/scaling/routing state (no reviewed system does this).
- **C2 — the action's own cost:** RQ2 measures the cost of *performing* a storage scale action (replica sync /
  join time / node-minutes / time-to-usable-capacity), which the corpus models only statically (Jin et al. model
  placement *cost* statically; RQ2 measures *runtime* cost).

## 4. What this means for the argument

The topic is **not** empty — Li, Breitbach, and SEND each do a piece of it. That is the risk (a reviewer can say
"the hard parts are already done; the selection step is the easy bit"). The defense:

- The slice **no** reviewed paper does — *the live-bottleneck-driven choice between tiers, on a real testbed, with
  the action's own cost measured* — is precisely what RQ2 executes.
- The results are the value-of-information findings that justify the slice: the magnitude of the DB blind spot
  (wrong-action cost when the DB is the bottleneck), the churn cost of committing correctly, and the
  measurement-contract difficulty of the storage-QoS comparison — all made concrete rather than argued.

---

*Source ledger: `tese/literature_review/02_action_selection_rq2/README.md` (per-paper role, one-line finding,
"What NOT to claim" per paper). Global framing: `tese/literature_review/global_literature_review.md`
(framing banner — corpus-bounded claims; universal statements must be reworded to "within the reviewed corpus").*
