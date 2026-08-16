# Thesis Structure — Restructure Blueprint for `tese/main.tex`

> **Status (2026-08-16):** blueprint for the `main.tex` content rewrite. Comment
> alignment (2026-08-01) and section-heading renames (2026-08-02) are done. The
> final RQ campaigns are **complete** (RQ1 delivery semantics, RQ2 bottleneck-aware
> action, RQ3 readiness propagation), so the Results chapter (now Ch.5) is written
> from completed evidence. **2026-08-16 decision:** the dedicated Evaluation
> Methodology chapter is removed — method folds into §1.4, scenarios/metrics into
> a Results-chapter "Experimental Setup" section (house standard: Cuco §1.7 /
> Polónio §1.4). Chapter rewrites are pending and proceed only after explicit approval.
> **Why:** `main.tex` carried the **pre-reframe** structure: old RQ set
> (RQ1 telemetry freshness, RQ2 backend selection, RQ3 trigger composition), the
> "detection→delivery→action" narrative, and the unmeasured ~74 s coordination tax.
> The approved framing is `tese/Notes/thesis_overview.md` (Telemetry, Scaling,
> and Traffic Admission). This document is the blueprint for the **content**
> restructuring of `main.tex`.
>
> Companion: `tese/Notes/purpose_evidence_map.md` (the evidence for each claim,
> with verbatim quotes).

---

## 0. What changed and why `main.tex` must change

### 0.1 The research questions (the headline change)

| | OLD (in `main.tex` now) | NEW (approved) |
|---|---|---|
| RQ1 | Telemetry **Freshness** — push vs poll at 5 s/12 s/30 s | Telemetry **Delivery Semantics** — event-preserving vs delayed event-preserving vs latest-state |
| RQ2 | Backend **Selection** — topology_host/slowstart/lifecycle | **Bottleneck-Aware Scaling Action** — compute-first/storage-first fixed vs bottleneck-aware choice of compute or storage scale-out |
| RQ3 | **Trigger Quality** — degradation_score vs cpu_only | **Readiness Propagation & Traffic Admission** — direct lifecycle notification vs periodic discovery |

The **pre-reframe** RQ1/RQ2/RQ3 campaigns are **supporting platform/calibration
evidence only** (`thesis_overview.md` §5); the **completed campaigns are the
final evidence**. Old backend-selection modes (host/slowstart/lifecycle)
are superseded: RQ3 now holds warm-lease priority and slow-start ramps constant
and varies only the readiness-propagation mechanism (`thesis_overview.md` §6-RQ3).

### 0.2 Two claims that must NOT appear as results

- The **~74 s / ~84 s "compound coordination tax"** in the lit-review summary and
  Discussion is **not a measured result** (43 s projected + 31 s measured, added
  across unmatched experiments). `thesis_overview.md` §7: *"It does not infer an
  end-to-end coordination penalty by adding values from unmatched experiments."*
  The thesis may *synthesise* measured segments **only after** they are measured
  under a common workload/config. **Rewrite, do not reuse, the old numbers.**
- The old RQ3 "no paper varies trigger composition" claim is false (Ghorab uses
  weighted CPU/memory; Zhou & Yong use 5xx HPA) — the new framing does not depend
  on it; drop it.

### 0.3 Scope guards to respect in every results claim

Tier 1 selective sync, prepared persistent storage reserves, and cross-region
storage placement are **disabled/hidden** in evaluation runs; the synchronous
curl driver is **calibration/secondary** until the open-loop driver replaces it
(`thesis_overview.md` §2, §8). Do not let results text overclaim these.

- **Cost of the scaling action itself (RQ2 honesty):** a storage scale-out is not
  "just more replicas" — `rs.add()` triggers replica sync (bandwidth + transient
  overload). The thesis must measure the action's own cost (sync bandwidth/
  overload), not only the relief, and scope the claim to cold, same-LAN
  `rs.add/remove` (full placement/consistency semantics out of scope).

### 0.4 Page budget and appendix policy

The main body is page-limited; the appendix is not. Global rules:

- **Appendix (unlimited):** full run matrices and per-run graphs (RQ1 28 runs,
  RQ2 36 runs, RQ3 12+ runs); controller/env configs and `phases_*.json`; code
  and schemas (telemetry-window log, `PolicyGate`, `admit_source`); protocol/tool
  background (OpenFlow pipeline, ZMQ, MongoDB replica-set internals); the full
  literature gap matrix; per-RQ gate/pre-registration rules and statistical
  formulas.
- **Body (keep only):** the demand model + metric definitions; one summary table
  per claim (median [95 % CI], Cliff's δ, p); one representative figure per RQ;
  a compact 4-row gap matrix. Do not repeat implementation detail in the Results
  chapter — reference Ch.3/Ch.4 instead.

---

## 1. Title and front matter

Current title: *A Cross-Layer SDN Orchestration Architecture for Stateful Edge
Services*. The framing is now the **coordination interfaces**, not an SDN
superiority claim — options (final choice is yours):

- *Telemetry, Scaling, and Traffic Admission in Stateful Edge Services: An Experimental Study of Control-Loop Coordination*
- *Coordinating Telemetry, Scaling, and Traffic Admission in Stateful Edge Services*
- *From Demand to Usable Capacity: Telemetry, Scaling, and Traffic Admission in Stateful Edge Services*

Notes:
- Keep "stateful edge services" (accurate, present in old title).
- Drop or de-emphasise "Cross-Layer SDN ... Architecture" as the headline — the
  thesis is an *experimental characterization on an SDN-based apparatus*, not an
  architecture-superiority claim (`thesis_overview.md` §1, §9).
- **Abstract** (250-word limit) and **keywords** must be rewritten around the new
  RQs + demand-to-usable-capacity object. Draft before editing.
- **Acronyms to add** in `main.tex` `\acronyms{}`: `DSRM` (Design Science Research
  Methodology), `EP`/`LS` (event-preserving / latest-state) if used as mode
  labels, `TTFS` (time-to-first-success) if used.

---

## 2. Chapter-by-chapter blueprint

### Chapter 1 — Introduction (`ch:introduction`)

| Section | Action |
|---|---|
| §1.1 Context, Motivation, Problem (`sec:context_motivation`) | **Rewrite tail.** Keep: traffic-growth figure/ITU, edge positioning (Cao, Satyanarayanan), "coordination delays ... handoff delays" opening. **Fix**: finish the incomplete sentence "Despite the advantages edge computing also faces, some difficulties regarding resource scarcity, reliability and " (complete or delete); remove the stale commented-out paragraph block above it. Add: demand variability as the *driver* (latency = outcome metric, **no SLA claims**), and the demand→usable-capacity chain as the problem (see purpose map P1–P2). ¶6 expands "costs of dispersal" beyond per-site scarcity to the full complexity taxonomy: management complexity + weaker security (Satyanarayanan), heterogeneity + demand volatility (Luo 2021), production over-provisioning/imbalance + placement-scheduling decoupling (Xu NEP 2021, newly added), multi-owner/multidomain resources (Liu 2019). ¶8 gains a SOTA-positioning sentence: the thesis follows the integration direction surveys call for (Luo joint CCS; Yaseen integrated monitoring) with standard mechanisms, contributing co-location + measurement, not a new algorithm. Ismail 2015 (Docker eval) intentionally not cited. |
| §1.2 Objectives (`sec:objectives`) | **Draft** (house standard 2026-08-14 — see `miscelineous/objectives_recommendation.md`). **One primary objective** — single aim sentence: investigate & characterise the three interfaces (telemetry delivery → scaling action → traffic admission) in a stateful edge service under demand shifts, via a co-located apparatus that suppresses the coordination gap (handoff delays) and in which each interface is deliberately engineered as an independently variable dimension — + **secondary objectives**: (1) co-located apparatus with independently configurable interfaces; (2) characterise telemetry delivery semantics; (3) characterise bottleneck-aware action selection; (4) characterise readiness propagation → traffic admission; (5) reconstruct the demand→usable-capacity timeline. ~~(6) methodology/validation~~ → **not an objective; moved to §1.4 (DSRM).** |
| §1.3 Research Questions (`sec:research_questions`) | **Rewrite** with the three new RQs (verbatim from `thesis_overview.md` §6). House standard: RQs live in their own section, separate from objectives (Polónio §1.3, Cuco §1.6). Optionally keep old ones in a footnote as superseded/calibration. |
| §1.4 Research Methodology (`sec:research_methodology`) | **Expand** to carry the whole method (house standard: Cuco §1.7, Polónio §1.4). DSRM (Peffers et al.; Hevner et al.) + evaluation procedure **absorbed from the removed Ch.5 §5.4**: per-run experimental unit; scheduled open-loop driver (pre-specified offered-load process); pre-registered Mann–Whitney U + Cliff's delta on pre-registered edges, CIs in full; per-phase aggregation; validity (internal/external/repeatability). Gate rules + formulas → appendix. |
| §1.5 Contributions (`sec:contributions`) | **Re-derive the 5 contributions** around interface characterization (see purpose map P7). |
| §1.6 Dissertation Structure (`sec:document_structure`) | **Update** chapter list (now **6 chapters**; Results = Ch.5, Conclusions = Ch.6) + note results ordered RQ1→RQ2→RQ3. |

### Chapter 2 — Background and Related Work (`ch:literature_review`)

Reorder domain sections to follow the chain **Monitoring → Auto-Scaling → SDN-LB →
Orchestration** (old order was Auto-Scaling, SDN-LB, Monitoring, Orchestration).
Each section is re-cast around the interface it informs (see purpose map P5).
Page budget: keep background to what the RQs need; protocol/tool background
(OpenFlow pipeline, ZMQ, MongoDB replica-set internals) → appendix.

| Section | Action |
|---|---|
| §2.1 Review Methodology (`sec:review_method`) | Keep (databases, search terms, inclusion/exclusion). |
| §2.2 The Unexamined Default (`sec:lit_three_layer_separation`) | **Reframe** as "three interfaces between separated components are where time/quality are lost". Compress to 1–2 paragraphs (framing device, not evidence); K8s/NFV-MANO/MEC table → appendix. |
| §2.3 Monitoring & Telemetry (`sec:lit_monitoring`) → **RQ1** | **Re-cast.** Evidence: AdapPF (`MEASURED`), Yaseen (visibility gaps, `DOCUMENTED`), Caiza & Zhang "periodically" (`TAXONOMY-GAP`), Belgaum (`SILENCE` — *inattention only*). Include the freshness evidence hierarchy. End with the RQ1 gap statement (delayed-but-complete vs latest-state, traced through scaling+admission). |
| §2.4 Auto Scaling (`sec:lit_auto_scaling`) → **RQ2** | **Re-cast.** Evidence: Qu et al. (database tier ignored), Pelle ("functions and data in sync"), Ghorab (joint LB+scaling). Studies *when/how many*, never *which action type*. End with the RQ2 gap statement. |
| §2.5 Load Balancing on SDN (`sec:lit_sdn_lb`) → **RQ3** | **Re-cast.** Evidence: Wang et al. (synchronisation-before-inclusion), Pierro & Ullah (service-discovery-latency symptom), Pourghebleh/Achir (SD freshness), the **"same gap, three names"** table (monitoring/SD/LB). End with the RQ3 gap statement. |
| §2.6 Resource Orchestration on SDN (`sec:lit_sdn_orchestration`) | Keep; frame as the *platform rationale*: co-location as the answer to "structurally unaskable" (purpose map P6; §6.2 closest-attempts table). |
| §2.7 Summary & Research Gaps (`sec:lit_synthesis`) | **Rewrite.** Replace the old ~74 s synthesis with: (a) **updated gap matrix** — columns must change to the NEW interface dimensions: *telemetry delivery semantics varied? / scaling-action type varied? / readiness→admission varied? / co-located & independently tunable?* (re-derive from `global_literature_review.md` §7, which still uses old columns; **full matrix → appendix, body keeps a compact 4-row version**); (b) the interface-gap statement (purpose map P4/P5); (c) explicitly *not* a summed penalty. |
| §2.8 Edge Storage related work (2026-08-01, corpus trimmed) | **New related-work block** — 1 paragraph in body; verdicts + locations → appendix (`global_literature_review.md` §10). Key roles: Ferreira = RQ2 DB-side citation; SEND = co-location adjacency (delimit); Malazi = nearest RQ2 neighbour (re-placement, not tier selection); Wei & Wang / Lujic = background. No paper threatens RQ1/RQ3; RQ2 needs the I2 rewording in `purpose_evidence_map.md`. |

### Chapter 3 — Architecture and Design (`ch:system_architecture`)

Conceptual only: diagrams + mechanism rationale. Concrete config, code, and
component listings → Ch.4 or appendix. Do not describe the same component twice —
the §3.3/§4.2, §3.4/§4.3, §3.5/§4.4 pairs must split design vs implementation,
not repeat each other.

| Section | Action |
|---|---|
| Chapter intro | **Add framing:** the architecture is the *experimental apparatus* that suppresses the coordination gap (the handoff delays between separate control loops), so each interface's own delay can be measured without cross-component handoffs as a confound. Each interface is then deliberately engineered as an independently configurable dimension; because co-location couples the components, this orthogonality is a design achievement, not a free consequence of co-location, and the rest of the service stays controlled (`thesis_overview.md` §5). |
| §3.1 Design Requirements (`sec:design_requirements`) | Keep; add "each control-loop interface independently tunable". |
| §3.2 Architecture (`sec:architecture_overview`) | Keep (two geo-distributed networks + WAN, OVS, double-VIP, 3-thread controller, telemetry pipeline). |
| §3.3 Elastic Allocation (`sec:elastic_allocation`) | Compute: **replace** the three backend-selection policy modes with the RQ3 readiness-propagation model (direct lifecycle notification vs periodic discovery; warm-lease/slow-start held constant). Data: keep Tier 0→2, Tier 1 Selective Sync described **as capability, out of scope** for evaluation. |
| §3.4 Monitoring & Decision Engine (`sec:monitoring_decision`) | Keep degradation score; describe the **implemented** RQ1 delivery-semantics design (event-preserving / delayed / latest-state / sampled-push; durable window log) and the RQ2 bottleneck classification + `PolicyGate`. |
| §3.5 Control Workflow (`sec:control_workflow`) | Keep; extend the end-to-end flow to readiness→admission (`thesis_overview.md` §5 event trace). |

### Chapter 4 — Implementation (`ch:implementation`)

Only the deltas: what was actually built that Ch.3 did not already specify.
Env/config tables and code → appendix.

| Section | Action |
|---|---|
| §4.1 Experimental infrastructure (`sec:impl_infraestructure`) | Keep (Docker, OVS, tc-netem WAN, cloud VM). Fix typo in section key if desired. |
| §4.2 Elastic allocation (`sec:impl_elastic`) | **Update.** Compute: describe as implemented — readiness-gated registration, pending-backend registry, flow-isolation mode, event-driven `app_ready` admission (RQ3); old `BACKEND_SELECTION_POLICY` host/slowstart/lifecycle framing removed. Data: `rs.add()/rs.remove()`, `VIP_DATA`, conntrack (keep); persistent storage reserve. |
| §4.3 Monitoring & Decision Engine (`sec:impl_monitoring`) | **Update.** Describe as implemented: sequence-numbered telemetry-window log (RQ1: `telemetry_delivery_log_*.csv`, event-preserving/delayed/latest-state/sampled-push sources); bottleneck classification + `PolicyGate` (RQ2); decision log (`_log_decision`); readiness gate + `admit_source` (RQ3). |
| §4.4 Control Workflow (`sec:impl_control`) | Keep; add readiness→admission handoff. |
| §4.5 Implementation Validation (`sec:impl_validation`) | Keep (golden-config stability, mechanism validation); reframe to the new extensions. |

### Chapter 5 — Experimental Results (`ch:results`)

**Order** changes from *RQ3 → RQ1 → RQ2* (old chain) to **RQ1 → RQ2 → RQ3**
(new chain: observe → decide/act → admit). A new leading **Experimental Setup**
section absorbs the removed Ch.5 §5.2 (scenarios/demand model) + §5.3 (metrics);
the statistical procedure moved to §1.4. Summary tables only — full run matrices
and per-run graphs → appendix.

| Section | Action |
|---|---|
| §5.1 Experimental Setup (`sec:experimental_setup`) | **New** — absorbs removed Ch.5 §5.2–§5.3: within-system single-variable manipulation; baselines encode architectural properties, not competing products; each RQ holds the other two interfaces constant; demand model / 10-phase workload (`thesis_overview.md` §2). Metrics: reaction latency (demand shift → usable capacity, segmented per RQ); service quality (p50/p95/p99, failure rate, offered vs completed); control overhead (CPU%, RSS); per-RQ outcomes (RQ1 windows/info-age/delivery delay; RQ2 bottleneck-recovery/node-minutes/relief; RQ3 ready→admitted→first-flow→first-success, useful initial request share); RQ2 action cost (replica-sync bandwidth/overload during `rs.add()`). Per-RQ locks per `thesis_overview.md` §6. |
| §5.2 RQ1 — Telemetry Delivery Semantics | **New results section** (replaces old "Telemetry Freshness"). |
| §5.3 RQ2 — Bottleneck-Aware Scaling Action | **New results section** (replaces old "Backend Selection"). |
| §5.4 RQ3 — Readiness Propagation & Traffic Admission | **New results section** (replaces old "Trigger Quality"). |
| §5.5 Network Performance (`sec:results_network`) | **Cut or move to appendix** — legacy platform characterization, not RQ evidence; keep only if it directly supports an RQ claim. |
| §5.6 Scalability Analysis (`sec:results_scalability`) | **Cut or move to appendix** — legacy; efficiency (node-minutes) and action timing already reported per RQ. |
| §5.7 Discussion (`sec:discussion`) | **Rewrite** (per §0.2). Reconstruct the demand→usable-capacity timeline **from measured segments under a common workload/config only** (`thesis_overview.md` §7). Report per-interface effect sizes and uncertainty; identify which interface dominates; implications for designers. |

> **Honesty guard:** old RQ2's ~31 s discovery-time slowstart penalty was
> empirically confirmed (n=9) *under the old framing*. Under the new framing it
> is not automatically RQ3 evidence — the new RQ3 protocol must be measured.
> Old runs are calibration/secondary only.

### Chapter 6 — Conclusions and Future Work (`ch:conclusions`)

| Section | Action |
|---|---|
| §6.1 Conclusions (`sec:conclusions`) | **Rewrite** around the three new RQ findings, structured as an explicit **RQ → finding** mapping (house pattern: Polónio Ch.6 answer table; Cuco §6.1 numbered answers). |
| §6.2 Research Contributions (`sec:contributions_revisited`) | Restate the re-derived 5 contributions with results evidence. |
| §6.3 Limitations (`sec:limitations`) | **Update to the completed evidence** (evidence status per §0.1). **RQ2**: storage user-visible p95 benefit **not statistically demonstrated** (pre-registered gate not met; CI includes 1.0; causes: PRE/POST window asymmetry + bottleneck-aware second-tier churn); 2 MEMCG OOM incidents as a platform limitation (256 MB / 512 MB caps); replica-sync **bandwidth not metered** (join time + node-minutes + transient CPU/latency measured instead). **RQ3**: gap-window **user-harm consequence null** at every load (pre-registered-acceptable; "why timing matters" argued by mechanism); container-bind stall (~10 s, both arms, measured covariate, controlled by stratification); storage-replica extension closed as null. **RQ1**: delay arm seed-dependent/bimodal (delay−latest-state n.s.); single regime, single platform; per-run mean-of-LANs unit. Common: synthetic workload + imposed profile (not production); no SLA claims; single testbed; MongoDB-specific mechanisms; n=6–7 per cell/arm (sufficient for observed effect sizes; modest stratum-level precision). |
| §6.4 Future Work (`sec:future_work`) | Keep + update: end-to-end coordination experiment (now the explicit synthesis target); window-size freshness/noise trade-off; Tier 1 full implementation; data-locality characterization (Tier 0/1/2); larger scale; real traces; ML thresholds; **static-capacity control arm** as a follow-up magnitude study. |

---

## 3. Old → new section mapping (quick reference)

| Old (`main.tex` now) | New (this blueprint) |
|---|---|
| §1.3 old RQ1/RQ2/RQ3 | §1.3 new RQ1/RQ2/RQ3 (old → footnote/calibration) |
| §2.3 Auto Scaling / §2.4 SDN-LB / §2.5 Monitoring / §2.6 Orchestration | Reordered: Monitoring(RQ1) → Auto-Scaling(RQ2) → SDN-LB(RQ3) → Orchestration |
| §2.7 summary with ~74 s tax | §2.7 interface-gap statement + updated gap matrix (new columns) |
| §3.3 compute: host/slowstart/lifecycle | readiness-propagation model (direct/discovery), ramps constant |
| §4.3 telemetry sources (push/poll cadence) | delivery-semantics log + event-preserving/delayed/latest-state sources |
| Ch.5 Evaluation Methodology (removed) | §1.4 method (DSRM + stats) + §5.1 "Experimental Setup" in Results |
| §5.3 metrics for old RQs | §5.1 Experimental Setup metrics (see overview §6) |
| §6.1 RQ3 trigger / §6.2 RQ1 telemetry / §6.3 RQ2 backend | §5.2 RQ1 delivery → §5.3 RQ2 scaling → §5.4 RQ3 admission |
| §6.6 Discussion ~74 s table | §5.7 measured-segments-only synthesis |

---

## 4. Must-fix hygiene list in `main.tex` (independent of framing)

Status: **comments DONE (2026-08-01)**; prose/heading items still open.

- [ ] Remove `\chapter{Evaluation Methodology}` (Ch.5) — fold §5.4 into §1.4,
  §5.2–§5.3 into a new Results-chapter "Experimental Setup" section, delete §5.1.
  *(blueprint only — `main.tex` not yet changed)*
- [ ] Incomplete sentence in §1.1: *"Despite the advantages edge computing also faces,
  some difficulties regarding resource scarcity, reliability and "* — finish or remove. *(prose — pending)*
- [x] Stale commented-out paragraph block in §1.1 (the "Orchestrating edge web
  services…" comment) — replaced with a superseded-framing note (2026-08-01). *(comment — done)*
- [x] TODO comments referencing **old** RQs in §1.3, §5, §6 — replaced with new RQs. *(comments — done)*
- [x] Old numbers "74 s / 84 s / 31 s / 43 s" in §2.7 and §6.6 comments — removed/reframed
  as measured-segments-only in comments. *(comments — done; content rewrite pending)*
- [x] Old backend-selection mode names (`topology_host`, `topology_slowstart`,
  `topology_lifecycle`) — mapped in comments to the RQ3 apparatus, and the four
  stale **section headings renamed** (2026-08-02) to the current RQ labels.
  *(comments + headings — done)*
- [ ] Typos spotted in **prose** (needs your go-ahead): "surprassed" → surpassed,
  "highliting" → highlighting, "arrise" → arise, "complitment" → complement,
  "arquitecture" → architecture (ch.3), "infraestructure" → infrastructure (ch.4).

---

## 5. Order of work / approvals

1. **Approve this blueprint** (or adjust chapter ordering, title, section names).
2. **Draft abstract + keywords + §1.2 objectives + §1.5 contributions** (present
   text before editing — human-in-the-loop). Objectives draft:
   `miscelineous/objectives_recommendation.md`.
3. Rewrite **Ch.2** using `purpose_evidence_map.md` quotes; update the gap matrix
   columns (needs a small edit to `global_literature_review.md` §7 matrix too —
   separate approval).
4. Update **Ch.3/Ch.4** (architecture/implementation) to the new extensions,
   deduplicating the §3.3/§4.2, §3.4/§4.3, §3.5/§4.4 pairs (Ch.3 conceptual,
   Ch.4 deltas).
5. **Remove `\chapter{Evaluation Methodology}`** — fold §5.4 into §1.4,
   §5.2–§5.3 into a Results-chapter "Experimental Setup" section, delete §5.1.
6. Results **Ch.5** written from the **completed RQ campaigns** — evidence
   sources: `tese/research_questions/{rq1/rq1_conclusions.md,
   rq2/rq2_conclusions.md, rq3/rq3_evaluation_conclusions.md}` (evidence
   status per §0.1).
7. Update dependent docs that still reference old RQs/framing (e.g. the
   `tese/literature_review/` folder READMEs — already reorganised 2026-08-01 into
   RQ folders — plus `docs/research_questions/*`, `.github/skills/rq*-cross-mode-comparison`)
   as the manuscript lands — each is a separate change set.

---

## 6. Source pointers

- Framing + RQs + evaluation principles + scope: `tese/Notes/thesis_overview.md` (§1–§10).
- Evidence/quotes per purpose step: `tese/Notes/purpose_evidence_map.md`.
- Gap forms + old matrix: `tese/literature_review/global_literature_review.md` (§1–§7; banner flags superseded framing).
- Corpus (RQ-mapped): `tese/literature_review/README.md` and the folder READMEs.
- Demand profile: `source/scripts/testing/phases_override/phases_stress_plateau.json` (control group, 2026-08-01).
- New RQ implementation plans: `docs/research_questions/rq{1,2,3}/rq*_preparation.md`;
  current experiment plans: `docs/operation/testing/experiment/v3/rq{1,2,3}/experiment_plan.md`.
- Final evidence (conclusions): `tese/research_questions/rq1/rq1_conclusions.md`,
  `tese/research_questions/rq2/rq2_conclusions.md`,
  `tese/research_questions/rq3/rq3_evaluation_conclusions.md`.
