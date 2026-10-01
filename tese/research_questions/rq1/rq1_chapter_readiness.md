# RQ1 — Results-Chapter Readiness Dossier

> **Status:** 2026-10-01 (§5.2 written 2026-09-26; Ch3 §3.4 / §5.1 alignments
> 2026-09-28; observation table added 2026-09-28, trimmed to the two
> observation axes; results narrative interpretation pass; 2026-10-01:
> pre-registered expectations row added to `tab:rq1_design`; §5.2 exhibits
> re-ordered to sit after their invoking paragraphs) · **Purpose:** one map of the complete RQ1
> chain — question → design/research → expectations → evaluation → results →
> conclusion — so that Chapter 5 can be written without re-deriving anything.
> Companions: `rq1_results_section_draft.tex` (staged §5.2 text),
> `rq1_conclusions.md` (verdict record), `rq1.md` (framing provenance).

---

## 1. Question (fixed, `main.tex` §1.3 — no change needed)

> "How do three ways of delivering demand evidence to the controller, more
> specifically, event-preserving, delayed event-preserving, and latest-state,
> affect what the controller observes about overload, how it responds by
> scaling, and the quality of service users experience during a demand
> shift?"

The question has **three clauses**, and the staged results section answers
them in order:

| Question clause | §5.2 material |
| --- | --- |
| (a) what the controller observes about overload | exposure paragraph: delivered fraction, information age at decision (`tab:rq1_observation`; detection-delay and missed-window outcomes cut from reporting 2026-09-29 — derivable from the two axes, retained in the campaign record / appendix graphs) |
| (b) how it responds by scaling | usable-capacity ordering (A < B < C ≈ D) |
| (c) quality of service during the shift | episode endpoint p95 + outcome classes (timeout / failure / canceled) |

Contribution 1 (§1.6) and the Chapter 2 gap-table row (`tab:interface_gaps`)
use the same three-semantics wording — consistent, **no change needed**.

## 2. Design / research (Chapter 3 + Chapter 4)

- The three semantics named in the RQ are evaluated in a **4-arm design**,
  with the latest-state class realised in two lossy forms: **C** latest-state
  polling (30 s) and **D** sampled push (every 3rd completed window).
  Settled framing: `thesis_overview.md` §6-RQ1 and `rq1.md` §4 (2×2:
  completeness × delivery staleness). The staged §5.2 opening states this
  explicitly ("the latest-state class realised in two lossy forms").
- **Delivery machinery** (durable, sequence-numbered window log; ordered
  replay; delivery acknowledgement; sequence validation / gap recovery) —
  summarised in `rq1.md` ("Delivery-semantics machinery"); Chapter 4's TODO
  already lists the source implementations (Zmq / Polling / EventPreserving /
  DelayedEventPreserving / **SampledPush**).
- ✅ **Chapter 3 §3.4 sampled-push clause — APPLIED 2026-09-28:** the
  delivery-modes sentence now lists the sampled-push realisation alongside
  latest-state retrieval and ordered replay, closing the design-chapter
  alignment. Same day: the §5.1 RQ1 design table now reads "four telemetry
  delivery treatments … realising the three delivery semantics with the
  latest-state class in two forms" (was "four telemetry delivery
  semantics").

## 3. Expectations (pre-registered; authoritative text: v3 plan §2 and §7)

**Claim to test (plan §1):** after the platform fix and workload re-anchor,
arms that scale later (C/D) show measurably worse per-episode service quality
than A, with B in between.

- **H1 (control loop):** usable-capacity ordering A < B < C ≈ D reproduces.
- **H2 (user link — the new claim):** episode p95 ordering A < B < C ≈ D.
  Primary endpoint = **served-basis episode p95**; four pre-registered edges
  (delay A−B / D−C, loss A−D / B−C); exact Mann–Whitney; Cliff's δ + 95 % CI;
  no multiplicity correction. The plan flagged that **D may be strictly
  worst**, and that a D > C outcome would be a *valid* H2 confirmation.
- **H3:** non-surge phases stay clean in every arm.

**Verdicts** (`rq1_conclusions.md` F1–F5; campaign summary §5):

| | Verdict | Headline |
| --- | --- | --- |
| H1 | ✅ Confirmed | medians A 28.5 < B 59.6 < C 79.6 ≈ D 83.2 s; A<B and B<C in 7/7 blocks; C≈D (5/7) |
| H2 | ⚠️ Partially confirmed | loss A−D: δ = −1.000, p = 0.0006, perfect separation 7/7; delay A−B: p = 0.0012, 7/7 direction but bimodal; B−C n.s. (p = 0.209); C ≈ D (p = 0.456) |
| H3 | ✅ Confirmed | non-surge p95 ≈ 1.05–1.08 s everywhere; only tail timeouts (0.07–0.12 %) |

Timeouts were 0 in every episode, so (as pre-registered) the ordering is
carried entirely by p95; failure and canceled classes are reported alongside.

## 4. Evaluation — material for §5.1 "Experimental Setup" (RQ1 row)

One row of the per-RQ setup table:

| Field | RQ1 content |
| --- | --- |
| Treatment | telemetry delivery semantics — A: event-preserving (fresh + complete); B: delayed event-preserving (+30 s, no burst replay); C: latest-state polling (30 s, ~1/3 of windows); D: sampled push (every 3rd window, ~1/3) |
| Held constants | aggregation window (10 s), scaling policy and parameters, routing policy, workload, topology, resource limits (RQ1 holds the other two interfaces fixed) |
| Workload | co-loaded overload episode: 180 s at rate 1.2, client fraction 1.0, mix service_pressure 0.30 / content_lookup 0.35 / feed_ranking 0.15 / content_update 0.10 / content_aggregate 0.10; the four standard tails (baseline, recovery gap, demand drop, idle tail) unchanged. Do not claim a common phase list across RQs. |
| Experimental unit | one run, per-run mean of the two domains for latency metrics |
| Replication | 4 arms × n = 7 = 28 runs; seeds 3001–3007; counterbalanced (one run per arm per seed block) |
| Exclusions / flags | none excluded; reported flags: `delayed_3` domain asymmetry 5.26× (only run above the 3× line); `sp_6` cancellation outlier (21.2 %); B residual completed-without-status class (2.22 % vs 0.03–0.42 % elsewhere) |
| Statistical test | exact Mann–Whitney (complete enumeration, n = 7 vs 7) on the four pre-registered edges; Cliff's δ + 95 % bootstrap CI; direction = block-consistent replicates; no multiplicity correction |
| Integrity | 28/28 runs pass the platform gates (M1/M2/V1/I1/I2/D1/D2/D3; F1/F2 flagged); 0 in-episode timeouts; no harness collapse; post-campaign checks: per-bucket no-masking, clean run-to-run platform state, scale-down retry class closed |

## 5. Results (§5.2) — staged and verified

- **Text:** `rq1_results_section_draft.tex` — **inserted into `main.tex`
  §5.2 on 2026-09-26** (heading and label `sec:results_rq1_delivery`
  unchanged); the draft file is kept in sync. The delivery paragraph was
  trimmed on 2026-09-28 to reference the new observation table. On
  2026-09-29 the results narrative received an interpretation pass (aim-first
  framing sentence, per-result interpretation, reframed expectation
  deviations, answer-shaped closing; all numbers unchanged), and the
  two-column observation table was restored in `main.tex`.
- **Figure (one representative figure per RQ):** source
  `docs/operation/testing/experiment/v3/rq1/graphs/thesis/episode_latency_p95.png`
  → **copied to** `tese/images/rq1_episode_latency_p95.png` (2026-09-26).
  **Do NOT use `endpoint_latency_p95.png`** (run-wide pooled metric — diluted,
  not the pre-registered endpoint).
- **Tables:** `tab:rq1_observation` (delivery realisation and overload
  observability; added 2026-09-28, trimmed to the two treatment axes
  2026-09-29 — detection delay and missed windows are no longer reported;
  campaign record / appendix graphs retain them), `tab:rq1_arms` (per-arm
  summary), `tab:rq1_edges` (pre-registered contrasts).
- **2026-10-01:** `tab:rq1_design` gained a pre-registered expectations row (ordering A < B < C ≈ D on usable capacity and the served-basis episode p95; the sampled-push arm permitted to be strictly worst; non-surge quality clean in every arm). The four §5.2 result exhibits were re-ordered to sit after the paragraphs that invoke them (ISCTE near-invocation rule), in `main.tex` and in the staged draft.
- **Numbers:** all re-verified 2026-09-26 against the campaign summary, the
  stats CSV, and the run bundles (provenance comment in the draft header).
- **Optional appendix material** (not in the page-limited body):
  `completeness_vs_infoage`, `missed_overload`, `overload_detection_delay`,
  `scale_reaction_latency`, per-phase latency figures; per-run matrices;
  DF95 per-bucket table; scale-down integrity table
  (`docs/operation/testing/experiment/v3/rq1/scale_down/`).

## 6. Conclusion (Chapter 6) — material ready

- **§6.1 RQ→finding row (draft material):**
  *RQ1* → "On the evaluated testbed, incomplete demand evidence was the robust
  driver: ≈ 9× episode p95 with perfect separation (δ = −1.000, exact
  p = 0.0006, n = 7); delivery delay was significant in aggregate
  (p = 0.0012) but conditional on the platform's absorption margin (two of
  seven delayed replicates collapsed)."
  *Evidence:* §5.2, Tables 5.x, Figure 5.x. *Boundary:* single co-loaded
  regime and single testbed; per-run mean-of-domains unit; ordering claim
  qualified (B−C n.s.; C ≈ D).
- **§6.3 RQ1 limitations** (from `thesis_structure.md` §6.3 +
  `rq1_conclusions.md` §9): delay-arm bimodality (B−C n.s.); single regime /
  single platform; per-run mean-of-domains unit.
- ⚠ **Stale note in `main.tex` §6.3 TODO:** the current comment still says
  "n = 3 per condition" and "designed, not fully measured" — outdated. When
  writing Chapter 6, use the updated list from `thesis_structure.md` §6.3
  (campaigns complete; n = 7 per arm; RQ1-specific items as above).

## 7. Open decisions (neither blocks writing §5.2)

1. **Data-chart figure pipeline** — the thesis-figure instruction reads
   "every figure is drawn in draw.io"; result charts have no drawio genre.
   Recommendation: codify a carve-out for source-generated result charts
   (analysis pipeline) and record it in the instruction file.
2. **C4 archive** — whether to archive the three small campaign-stat files
   (`rq1_campaign_summary.md`, stats CSV, dataset CSV) locally; currently
   VM-only per the earlier choice.

## 8. Ready-to-write checklist

- [x] Question fixed in §1.3; three clauses map to the §5.2 structure
- [x] Design framing settled (4-arm realisation of the three semantics)
- [x] Chapter 3 §3.4 sampled-push clause — applied 2026-09-28
- [x] Expectations pre-registered (H1–H3 + four edges) and verdicts recorded
- [x] §5.1 evaluation facts for the RQ1 row (§4 of this dossier)
- [x] §5.2 text staged; numbers verified; figure + tables ready
- [x] §6.1 finding row and §6.3 limitations pointers prepared
- [x] Integration: figure copied, §5.2 inserted into `main.tex` (2026-09-26),
  build verified
- [ ] §6.3 TODO refresh (stale "n = 3" note) — when Chapter 6 is written
