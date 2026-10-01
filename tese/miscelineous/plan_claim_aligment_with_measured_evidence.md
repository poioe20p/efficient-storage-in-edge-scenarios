# Claim Alignment with Measured Evidence — Revision Plan

Tracking plan for `tese/main.tex` claim alignment (2026-09-03). Status:
`[x]` applied, `[-]` deferred, `[ ]` pending. Items are applied against the
section labels listed below; this file replaces the old inline `% REVISION`
comments in the thesis file.

## A. Must change before writing results

- [X] **A1** Narrow RQ2 (`sec:research_questions`), Contribution 3, and the
  related-work conclusion. Final wording: "Under compute-bound and
  data-access-bound demand, how does bottleneck-aware scale-up, compared
  with fixed single-tier policies, affect targeted-tier relief, service
  recovery, and resource use?" The compute/storage action space stays
  explicit in Contribution 3 ("bottleneck-aware scale-up (compute versus
  storage)"). Applied 2026-09-03; terminology settled 2026-09-03:
  bottleneck-aware for the RQ-level mechanism, resource-aware kept in the
  framing (design requirements, objectives, proposal bridge). Re-applied
  2026-09-04 after a concurrent rewrite restored `resource aware` in
  `sec:research_questions`. Action term unified to "scale-up" on
  2026-09-20 (§2.4 definitions).
- [X] **A2** RQ3 wording (`sec:research_questions`): servability criterion,
  lifecycle-driven vs periodic readiness-admission mechanisms. Applied
  2026-09-03; re-applied 2026-09-04 after a concurrent rewrite restored the
  `criterea` typo.
- [X] **A3** Contribution 5: comparative synthesis under the respective
  controlled workload regimes (robust / workload-bound / inconclusive).
  Applied 2026-09-03.
- [X] **A4** Novelty claims scoped to the reviewed literature. Applied
  2026-09-03.
- [X] **A5** Review methodology: sentence on re-verifying non-archived papers
  removed. Applied 2026-09-03.
- [X] **A6** Opening citations: RESOLVED 2026-09-04 by author decision —
  keep all three. Gurung2026 PDF added to the corpus
  (`tese/literature_review/Cloud_Revolution_Tracing_the_Origins_and_Rise_of_C.pdf`);
  ITU2025InternetTraffic and Gaudiaut2026MobileTrafficShare are retained as
  web sources with the author's approval.

- [-] **A7** Paper count: reconcile at the end against the final bibliography
  (corpus index says 42; text says 39). Deferred per author.

- [X] **A8** Appendix promise in `sec:research_methodology` deleted. Resolved
  2026-09-03; re-add when the statistical/gate appendix exists.

- [-] **A9** Abstract, keywords, date, acknowledgements, dedication: author
  will write at the end. (A draft abstract/keywords was applied 2026-09-03
  and later restored to placeholder by the author.)

## B. Required chapter work

- [X] **B1** `ch:system_architecture`: two-domain architecture figure (Fig. 3.1)
  APPLIED 2026-09-04 with `architecture_overview.png`; VIP routing sequence
  and telemetry delivery paths figures also wired. Traceability table
  (design requirement -> implemented mechanism -> RQ/evidence) dropped as
  optional per author.
- [ ] **B2** `ch:implementation`: replace all TODO shells with implementation
  text (testbed, OVS/Docker/MongoDB topology, telemetry pipeline, execution
  contexts, routing/admission logic, instrumentation, validation evidence).
- [X] **B3** `sec:experimental_setup`: one table per RQ (treatment, held
  constants, workload, experimental unit, replication, exclusions, statistical
  test). Do NOT claim a common nine-phase workload. APPLIED 2026-09-26:
  section written (four subsections: testbed, demand model, metrics, campaign
  designs); design tables `tab:rq1_design` / `tab:rq2_design` /
  `tab:rq3_design`; workloads stated per campaign (no common phase list).
- [X] **B4** `sec:results_rq1_delivery`: lead with latest-state ~9x episode p95
  (n=7, full separation); delayed arm significant but bimodal; no monotonic
  four-arm order; state the LAN-asymmetry replicate. APPLIED 2026-09-26:
  section written from the v3 campaign (28 runs, n=7 per arm); tables
  `tab:rq1_arms` / `tab:rq1_edges`; figure `fig:rq1_episode_p95`
  (`images/rq1_episode_latency_p95.png`).
- [X] **B5** `sec:results_rq2_action`: REWRITTEN to the measured shape and
  APPLIED 2026-09-28: consequence map (aligned storage benefit vs inaction,
  labelled cross-era comparison; resource-side wrong-action cost; bounded
  compute axis, with the start-up-transient correction replacing the v3
  "compute relief robust" claim); storage tail-latency gate reported not met
  (window-asymmetry cause); the 2 OOM exclusions stated; classifier
  commitment; sequence not confirmable. All three figures produced
  2026-10-01 (`fig:rq2_map`, `fig:rq2_engagement`, and the restyled
  `fig:rq2_relief` v2 render; generator
  `source/scripts/testing/analysis/rq2/scripts/generate_thesis_figures.py`);
  section numbers reconciled to the figures. Section cut pass applied
  2026-10-01 (redundancy removal: single home for the start-up transient,
  the window definitions, the expectations recap, the node-minutes numbers
  and the escalation diagnostic, which now carries the raised-rate
  distinction between a capacity shortage and a failure mode of another
  kind; saturation definition moved to §5.1 with
  `sec:metrics_definitions`; the §5.3 close now states the conditional
  rule, the benefit appearing where the served tier bounds the episode
  and absent where no capacity-bound queue forms).
  Follow-ups: re-sync `rq2_conclusions.md`; the unmetered replica-sync
  bandwidth caveat is carried to the Ch6 limitations.
- [ ] **B6** `sec:results_rq3_readiness`: readiness-to-routing admission
  quantization; lead with ~6-7 s timing difference, then end-to-end
  first-success; transition-window timeout/failure harm null; n=7-per-arm
  run-level comparison primary, per-backend stratification supporting;
  reconcile v2 fixed-image and v3 saturation campaigns explicitly (no merged
  sample sizes).
- [X] **B7** `sec:results_network` / `sec:results_scalability`: remove both
  headings unless dedicated evidence exists. APPLIED 2026-09-26: both headings
  removed; the salvageable control-overhead item (controller CPU/RSS from
  `controller_stats.csv`) is carried as a TODO in `sec:discussion`; the
  cross-LAN/WAN/telemetry-overhead and scale-behaviour items dropped (no
  dedicated evidence; scale coverage lives in the RQ sections and Ch.6).
- [ ] **B8** `sec:discussion`: conceptual synthesis only — no summed effect
  sizes, no universal "most important interface" claim.
- [ ] **B9** `ch:conclusions`: per-RQ answer table (question / supported answer
  / evidence / boundary); evidence-backed contributions; serious limitations
  (controlled testbed, emulated WAN, single host, n, MongoDB-specific
  mechanisms).

## C. Scope and evidence rules

- [X] **C1** Environment described as an emulated two-domain, single-host
  testbed; no claim of real geo-distributed WAN performance — APPLIED
  2026-09-04: scope note at the end of `sec:architecture_overview`; the B2
  (`sec:impl_infraestructure`) and B3 (`sec:experimental_setup`) statements
  will reinforce it when written.
- [X] **C2** Tier 1, cross-domain placement, and cold replica joining are
  platform capabilities or held-constant context where unevaluated — APPLIED
  2026-09-04 (compressed tier paragraph in `sec:elastic_data`);
  re-applied 2026-09-04 after a concurrent rewrite re-expanded it.
- [X] **C3** RQ1 evidence: state delayed-arm bimodality and one LAN-asymmetry
  replicate. APPLIED 2026-09-26: both stated in `sec:results_rq1_delivery`
  (collapsed B replicates 65.3 s and 64.7 s; `delayed_3` domain asymmetry
  21.1 s vs 4.0 s).
- [ ] **C4** Archive the RQ1 raw dataset and statistics locally before making
  reproducibility claims.

## Editorial fixes applied while working

- 2026-09-03: restored the missing `\section{Load Balancing on SDN}`
  (`sec:lit_sdn_lb`) heading, which had been lost between the Auto Scaling and
  SDN-Based Orchestration Platforms sections.
- 2026-09-03: RQ2 terminology settled as "bottleneck-aware scale-out" (RQ2,
  Contribution 3, related-work conclusion, Chapter 5 section title,
  chapter outline); "resource-aware" retained only in framing contexts
  (design requirements, objectives, proposal bridge). Action term later
  unified to "scale-up" (2026-09-20, §2.4 definitions).
- 2026-09-03: RQ3 typo "criterea" fixed to "criterion".
- 2026-09-04: scaling-policy formulas moved from `sec:elastic_compute` into a
  shared, tier-generic `sec:scaling_policy` subsection; per-equation
  `where:` lists replace the notation table (Polonio reference-thesis
  convention); `sec:elastic_compute` and `sec:elastic_data` now reference
  the shared policy.
- 2026-09-05: DSRM "Objectives of a solution" reframed to state the
  platform's purpose (make the chain interfaces measurable so their
  contribution to resource orchestration can be evaluated), rather than
  only describing the artefact type; compressed the same day to remove
  repetition with the Design-and-development item.
- 2026-09-05: platform artifact removed from `sec:contributions` (the
  platform is the measurement instrument, not a defended deliverable;
  reference-thesis comparison confirmed the difference). Contributions are
  now four: the RQ1/RQ2/RQ3 characterisations and the synthesis, with
  bottleneck-aware selection and readiness-admission quantification wording;
  `sec:contributions_revisited` TODO updated to four.
- 2026-09-04: figures wired — `demand_to_capacity_chain_v2`,
  `sdn_load_balancing_v2` (uncommented), `architecture_overview` (Fig. 3.1),
  `vip_routing_sequence`, `telemetry_delivery_paths`; removed the Ch. 2
  `monitoring_telemetry_pipeline` figure (image dropped by author).
- 2026-09-26: RQ1 results section written — `sec:results_rq1_delivery`
  (§5.2) populated from the v3 campaign (staged draft applied to
  `main.tex`); B4 and C3 closed; figure
  `images/rq1_episode_latency_p95.png` added.
- 2026-09-28: RQ1 design-chapter alignment — Chapter 3 delivery-modes
  sentence now lists the sampled-push realisation; §5.1 RQ1 design table
  reworded to "four telemetry delivery treatments … realising the three
  delivery semantics with the latest-state class in two forms".
- 2026-10-01: RQ1-completion alignment pass — §2.4: 'delay or blindness' →
  'delay or degradation'; 'scaling and traffic-admission path' → 'from
  observation to user-visible consequence'. §2.6: 'the freshness of demand
  evidence' → 'the delivery of demand evidence (its freshness and
  completeness)'. §5.2: expectations row ('permitted' → 'expected' for the
  sampled-push worst case) and the 'on usable capacity' gloss on the
  replicated-ordering sentence. Ch1 and Ch3 audited clean (no changes).
