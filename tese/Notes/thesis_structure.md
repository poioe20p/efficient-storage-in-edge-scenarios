# Thesis Structure — Restructure Blueprint for `tese/main.tex`

> **Status:** 2026-07-31 (blueprint) · **2026-08-01:** comment-level alignment of
> `main.tex` done. **2026-08-02:** the four stale section headings renamed (Results
> chapter now RQ1→RQ2→RQ3 + "Discussion: Synthesis Across Interfaces"); the in-file
> `% NOTE` flags removed. **2026-08-13:** the final RQ campaigns are **complete**
> (RQ1 telemetry delivery semantics, RQ2 bottleneck-aware action, RQ3 readiness
> propagation) — Ch.6 is written from completed evidence, not from a pending
> design. The **content rewrite** of each chapter is still pending and happens only
> after explicit approval, chapter by chapter.
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
| §1.2 Objectives (`sec:objectives`) | **Draft.** Derive the 6 objectives from the new RQs + apparatus: (1) co-located controller apparatus with independently configurable interfaces; (2) characterise telemetry delivery semantics; (3) characterise bottleneck-aware action selection; (4) characterise readiness propagation → traffic admission; (5) reconstruct the demand→usable-capacity timeline; (6) methodology/validation. |
| §1.3 Research Questions (`sec:research_questions`) | **Rewrite** with the three new RQs (verbatim from `thesis_overview.md` §6). Optionally keep old ones in a footnote as superseded/calibration. |
| §1.4 Research Methodology (`sec:research_methodology`) | Keep (DSRM — Peffers et al.; Hevner et al.). Unchanged. |
| §1.5 Contributions (`sec:contributions`) | **Re-derive the 5 contributions** around interface characterization (see purpose map P7). |
| §1.6 Dissertation Structure (`sec:document_structure`) | **Update** chapter list + note results chapter now ordered RQ1→RQ2→RQ3. |

### Chapter 2 — Background and Related Work (`ch:literature_review`)

Reorder domain sections to follow the chain **Monitoring → Auto-Scaling → SDN-LB →
Orchestration** (old order was Auto-Scaling, SDN-LB, Monitoring, Orchestration).
Each section is re-cast around the interface it informs (see purpose map P5).

| Section | Action |
|---|---|
| §2.1 Review Methodology (`sec:review_method`) | Keep (databases, search terms, inclusion/exclusion). |
| §2.2 The Unexamined Default (`sec:lit_three_layer_separation`) | **Reframe** consequence as "three interfaces between separated components are where time/quality are lost". Keep the K8s/NFV-MANO/MEC table. |
| §2.3 Monitoring & Telemetry (`sec:lit_monitoring`) → **RQ1** | **Re-cast.** Evidence: AdapPF (`MEASURED`), Yaseen (visibility gaps, `DOCUMENTED`), Caiza & Zhang "periodically" (`TAXONOMY-GAP`), Belgaum (`SILENCE` — *inattention only*). Include the freshness evidence hierarchy. End with the RQ1 gap statement (delayed-but-complete vs latest-state, traced through scaling+admission). |
| §2.4 Auto Scaling (`sec:lit_auto_scaling`) → **RQ2** | **Re-cast.** Evidence: Qu et al. (database tier ignored), Pelle ("functions and data in sync"), Ghorab (joint LB+scaling). Studies *when/how many*, never *which action type*. End with the RQ2 gap statement. |
| §2.5 Load Balancing on SDN (`sec:lit_sdn_lb`) → **RQ3** | **Re-cast.** Evidence: Wang et al. (synchronisation-before-inclusion), Pierro & Ullah (service-discovery-latency symptom), Pourghebleh/Achir (SD freshness), the **"same gap, three names"** table (monitoring/SD/LB). End with the RQ3 gap statement. |
| §2.6 Resource Orchestration on SDN (`sec:lit_sdn_orchestration`) | Keep; frame as the *platform rationale*: co-location as the answer to "structurally unaskable" (purpose map P6; §6.2 closest-attempts table). |
| §2.7 Summary & Research Gaps (`sec:lit_synthesis`) | **Rewrite.** Replace the old ~74 s synthesis with: (a) **updated gap matrix** — columns must change to the NEW interface dimensions: *telemetry delivery semantics varied? / scaling-action type varied? / readiness→admission varied? / co-located & independently tunable?* (re-derive from `global_literature_review.md` §7, which still uses old columns); (b) the interface-gap statement (purpose map P4/P5); (c) explicitly *not* a summed penalty. |
| §2.8 Edge Storage related work (2026-08-01, corpus trimmed) | **New related-work block.** Full verdicts in `global_literature_review.md` §10. The edge-storage papers now live in `02_action_selection_rq2/` (Ferreira et al. 2024 — edge-DB survey, the RQ2 DB-side citation; SEND 2021 — co-location adjacency, must be delimited; Malazi et al. 2022 — nearest RQ2 neighbour, "dynamic" = re-placement, not tier selection) and `99_reference/` (Wei & Wang 2023 — old-idea ancestor, self-declared static; Lujic et al. 2017 — forecasting boundary). No paper in the corpus threatens RQ1/RQ3; RQ2 requires the 3-claim rewording in purpose map I2. |

> **Relocated from `context_motivation.md` ¶8 (2026-08-14):** the compressed
> motivation no longer deep-dives. Use in Ch.2: Llorens/Qu component facts +
> AdapPF evidence → §2.3 Monitoring (RQ1) / §2.5 SDN-LB (RQ3); Okwuibe
> component split → §2.2; the "never isolated along the full chain" synthesis
> and the Luo/Yaseen remedy direction → §2.7 gap statement.

### Chapter 3 — Architecture and Design (`ch:system_architecture`)

| Section | Action |
|---|---|
| Chapter intro | **Add framing:** the architecture is the *experimental apparatus* making each interface independently configurable while the rest of the service stays controlled (`thesis_overview.md` §5). |
| §3.1 Design Requirements (`sec:design_requirements`) | Keep; add "each control-loop interface independently tunable". |
| §3.2 Architecture (`sec:architecture_overview`) | Keep (two geo-distributed networks + WAN, OVS, double-VIP, 3-thread controller, telemetry pipeline). |
| §3.3 Elastic Allocation (`sec:elastic_allocation`) | Compute: **replace** the three backend-selection policy modes with the RQ3 readiness-propagation model (direct lifecycle notification vs periodic discovery; warm-lease/slow-start held constant). Data: keep Tier 0→2, Tier 1 Selective Sync described **as capability, out of scope** for evaluation. |
| §3.4 Monitoring & Decision Engine (`sec:monitoring_decision`) | Keep degradation score; describe the **implemented** RQ1 delivery-semantics design (event-preserving / delayed / latest-state / sampled-push; durable window log) and the RQ2 bottleneck classification + `PolicyGate`. |
| §3.5 Control Workflow (`sec:control_workflow`) | Keep; extend the end-to-end flow to readiness→admission (`thesis_overview.md` §5 event trace). |

### Chapter 4 — Implementation (`ch:implementation`)

| Section | Action |
|---|---|
| §4.1 Experimental infrastructure (`sec:impl_infraestructure`) | Keep (Docker, OVS, tc-netem WAN, cloud VM). Fix typo in section key if desired. |
| §4.2 Elastic allocation (`sec:impl_elastic`) | **Update.** Compute: describe as implemented — readiness-gated registration, pending-backend registry, flow-isolation mode, event-driven `app_ready` admission (RQ3); old `BACKEND_SELECTION_POLICY` host/slowstart/lifecycle framing removed. Data: `rs.add()/rs.remove()`, `VIP_DATA`, conntrack (keep); persistent storage reserve. |
| §4.3 Monitoring & Decision Engine (`sec:impl_monitoring`) | **Update.** Describe as implemented: sequence-numbered telemetry-window log (RQ1: `telemetry_delivery_log_*.csv`, event-preserving/delayed/latest-state/sampled-push sources); bottleneck classification + `PolicyGate` (RQ2); decision log (`_log_decision`); readiness gate + `admit_source` (RQ3). |
| §4.4 Control Workflow (`sec:impl_control`) | Keep; add readiness→admission handoff. |
| §4.5 Implementation Validation (`sec:impl_validation`) | Keep (golden-config stability, mechanism validation); reframe to the new extensions. |

### Chapter 5 — Evaluation Methodology (`ch:methodology`)

| Section | Action |
|---|---|
| §5.1 Experimental Objectives (`sec:experimental_objectives`) | **Rewrite** around the three new RQs (vary each interface independently; DSRM framing unchanged). |
| §5.2 Evaluation Scenarios (`sec:evaluation_scenarios`) | **Rewrite.** Add the **demand model** (purpose map §Demand model): the quantified imposed profile (50× surge, mix shift, duty cycle, recovery), temporal+compositional variability (spatial disabled), step transitions stated. Add the recommended **static/no-adaptation control arm**. Comparison strategy: baselines encode architectural properties, not competing products. |
| §5.3 Performance Metrics (`sec:performance_metrics`) | **Rewrite** to the new RQ metrics (`thesis_overview.md` §6 per-RQ primary measurements): RQ1 (completed/missed overload windows, information age, decision timing), RQ2 (bottleneck-specific recovery, node-minutes, relief in targeted tier), RQ3 (ready→admitted→first-flow→first-success delays, useful initial request share, **gap-window pool `timeout_rate`/`failure_rate` over `[spawn_started, admitted]`**), plus latency/failure/timeout and control overhead, and — for RQ2 — the **cost of the scaling action itself** (replica-sync bandwidth and transient overload during `rs.add()`). Independent breach detector; per-RQ locks updated to the new controls. |
| §5.4 Procedure & Statistical Analysis (`sec:experiment_procedure`) | Keep (per-run unit, Mann-Whitney U, Cliff's delta, per-phase aggregation, validity). Open-loop driver requirement + calibration-only status of the sync curl driver: **implemented and the caveat lifted — all three final campaigns completed**: RQ1 (telemetry delivery semantics, 4 arms × n=7 = 28 runs, seeds 3001–3007); RQ2 (bottleneck-aware action selection, 6 cells × 6 = 36 runs, 34 valid — 2 documented MEMCG OOM incidents); RQ3 (readiness propagation, n=6/arm = 12 runs, plus a 15 s sensitivity cell and a boundary probe). Stats: pre-registered Mann–Whitney U + Cliff's delta on pre-registered edges; CIs reported in full. |

### Chapter 6 — Experimental Results (`ch:results`)

**Order** changes from *RQ3 → RQ1 → RQ2* (old chain) to **RQ1 → RQ2 → RQ3**
(new chain: observe → decide/act → admit).

| Section | Action |
|---|---|
| §6.1 RQ1 — Telemetry Delivery Semantics | **New results section** (replaces old "Telemetry Freshness"). |
| §6.2 RQ2 — Bottleneck-Aware Scaling Action | **New results section** (replaces old "Backend Selection"). |
| §6.3 RQ3 — Readiness Propagation & Traffic Admission | **New results section** (replaces old "Trigger Quality"). |
| §6.4 Network Performance (`sec:results_network`) | Keep. |
| §6.5 Scalability Analysis (`sec:results_scalability`) | Keep; reframe around efficiency (node-minutes) and action timing. |
| §6.6 Discussion (`sec:discussion`) | **Rewrite — drop the old ~74 s table.** Reconstruct the demand→usable-capacity timeline **from measured segments under a common workload/config only** (`thesis_overview.md` §7). Report per-interface effect sizes and uncertainty; identify which interface dominates; implications for designers. No summed penalty across unmatched experiments. |

> **Honesty guard:** old RQ2's ~31 s discovery-time slowstart penalty was
> empirically confirmed (n=9) *under the old framing*. Under the new framing it
> is not automatically RQ3 evidence — the new RQ3 protocol must be measured.
> Old runs are calibration/secondary only.

### Chapter 7 — Conclusions and Future Work (`ch:conclusions`)

| Section | Action |
|---|---|
| §7.1 Conclusions (`sec:conclusions`) | **Rewrite** around the three new RQ findings. |
| §7.2 Research Contributions (`sec:contributions_revisited`) | Restate the re-derived 5 contributions with results evidence. |
| §7.3 Limitations (`sec:limitations`) | **Update to the completed evidence**: pre-reframe campaigns calibration-only; all three RQ campaigns complete. **RQ2**: storage user-visible p95 benefit **not statistically demonstrated** (pre-registered gate not met; CI includes 1.0; causes: PRE/POST window asymmetry + bottleneck-aware second-tier churn); 2 MEMCG OOM incidents as a platform limitation (256 MB / 512 MB caps); replica-sync **bandwidth not metered** (join time + node-minutes + transient CPU/latency measured instead). **RQ3**: gap-window **user-harm consequence null** at every load (pre-registered-acceptable; "why timing matters" argued by mechanism); container-bind stall (~10 s, both arms, measured covariate, controlled by stratification); storage-replica extension closed as null. **RQ1**: delay arm seed-dependent/bimodal (delay−latest-state n.s.); single regime, single platform; per-run mean-of-LANs unit. Common: synthetic workload + imposed profile (not production); no SLA claims; single testbed; MongoDB-specific mechanisms; n=6–7 per cell/arm (sufficient for observed effect sizes; modest stratum-level precision). |
| §7.4 Future Work (`sec:future_work`) | Keep + update: end-to-end coordination experiment (now the explicit synthesis target); window-size freshness/noise trade-off; Tier 1 full implementation; data-locality characterization (Tier 0/1/2); larger scale; real traces; ML thresholds; **static-capacity control arm** as a follow-up magnitude study. |

---

## 3. Old → new section mapping (quick reference)

| Old (`main.tex` now) | New (this blueprint) |
|---|---|
| §1.3 old RQ1/RQ2/RQ3 | §1.3 new RQ1/RQ2/RQ3 (old → footnote/calibration) |
| §2.3 Auto Scaling / §2.4 SDN-LB / §2.5 Monitoring / §2.6 Orchestration | Reordered: Monitoring(RQ1) → Auto-Scaling(RQ2) → SDN-LB(RQ3) → Orchestration |
| §2.7 summary with ~74 s tax | §2.7 interface-gap statement + updated gap matrix (new columns) |
| §3.3 compute: host/slowstart/lifecycle | readiness-propagation model (direct/discovery), ramps constant |
| §4.3 telemetry sources (push/poll cadence) | delivery-semantics log + event-preserving/delayed/latest-state sources |
| §5.3 metrics for old RQs | metrics for new RQs (see overview §6) |
| §6.1 RQ3 trigger / §6.2 RQ1 telemetry / §6.3 RQ2 backend | §6.1 RQ1 delivery → §6.2 RQ2 scaling → §6.3 RQ3 admission |
| §6.6 Discussion ~74 s table | measured-segments-only synthesis |

---

## 4. Must-fix hygiene list in `main.tex` (independent of framing)

Status: **comments DONE (2026-08-01)**; prose/heading items still open.

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
   text before editing — human-in-the-loop).
3. Rewrite **Ch.2** using `purpose_evidence_map.md` quotes; update the gap matrix
   columns (needs a small edit to `global_literature_review.md` §7 matrix too —
   separate approval).
4. Update **Ch.3/Ch.4/Ch.5** (architecture/implementation/methodology) to the new
   extensions.
5. Results **Ch.6** written from the **completed RQ campaigns** — evidence
   sources: `tese/research_questions/{rq1/rq1_conclusions.md,
   rq2/rq2_conclusions.md, rq3/rq3_evaluation_conclusions.md}`. The
   **pre-reframe** campaigns remain calibration-only; the completed campaigns
   are the final evidence.
6. Update dependent docs that still reference old RQs/framing (e.g. the
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
