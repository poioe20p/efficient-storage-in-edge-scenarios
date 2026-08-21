# RQ2 — Evaluation Design and Rationale (v2; superseded by v3)

> **Status:** 2026-08-04 · complements [`rq2.md`](rq2.md) (question + provenance)
> with the **v2 evaluation design** and the **evidence-framing rationale** for the
> v2 18-run campaign. It answers, in advance of the runs: *can this evaluation
> produce thesis-level results, and why?*
>
> **⚠️ Superseded (2026-08-10):** the v2 campaign was **aborted at run 13** — at
> the v2 config the data-bound cells could not show a storage scale-up benefit
> (storage never bound; reads stayed pinned to static primaries). The **v3
> campaign** rebased on the locked storage-bind config with a **persistent
> storage reserve** and is the **completed, evidence-bearing evaluation**
> (36 runs, 34 valid; `cloud-vm-rq2`, tag `rq2-v3-campaign-20260808`). The v3
> design, pre-registered gates, results, and claim framing are in
> [`rq2_conclusions.md`](rq2_conclusions.md) and the v3 experiment record:
> [`experiment_plan.md`](../../docs/operation/testing/experiment/v3/rq2/experiment_plan.md),
> [`results.md`](../../docs/operation/testing/experiment/v3/rq2/results.md),
> [`post_run_analysis.md`](../../docs/operation/testing/experiment/v3/rq2/post_run_analysis.md).
> The body below is retained verbatim as the **v2 design rationale** (provenance).
>
> **Sources (v2):** [`experiment_plan.md`](../../docs/operation/testing/experiment/v2/rq2/experiment_plan.md)
> (v2 section), [`run_matrix.md`](../../docs/operation/testing/experiment/v2/rq2/run_matrix.md) §10,
> [`analysis_focus.md`](../../docs/operation/testing/experiment/v2/rq2/analysis_focus.md) §7,
> [`rq2_v2_rework_plan.md`](../../docs/operation/testing/experiment/v2/rq2/rq2_v2_rework_plan.md);
> `thesis_overview.md` §5–§9; `thesis_structure.md` §5.3–§5.4, §7.3.

---

## 1. The question and what the evidence must show

**RQ2** (canonical wording, `tese/main.tex` §1.3): *under compute-bound and
data-access-bound demand, does bottleneck-aware selection of compute or storage
scale-out improve service recovery and resource management efficiency relative to
workload-agnostic fixed-priority policies when both actions are available?*

**Superseded paraphrase** (retained for provenance only): *under compute-bound
and data-access-bound demand, does a bottleneck-aware controller — choosing the
scale-out action (compute or storage) from tier telemetry — recover service
quality and use resources more efficiently than the single-tier fixed policies an
operator would otherwise configure?*

The evidence must support three claims:

- **H1 / SC2 (value of information):** `bottleneck_aware` recovers service
  quality like the correctly-aligned fixed arm **without knowing the regime in
  advance**, and beats the mis-aligned fixed arm.
- **H2 / SC1+SC3 (wrong-action cost):** the mis-aligned fixed arm stays degraded
  (no targeted-tier relief) and **wastes its action budget and node-minutes** on
  the wrong tier.
- **H3 / SC4 (decision quality):** the classifier-vs-episode agreement is above
  chance in the data-bound direction; in the compute-bound direction it is
  reported honestly (≈ chance is acceptable and documented).

---

## 2. The evaluation design (v2, 18 runs)

| cell | policy | episode | role |
|---|---|---|---|
| `cf_cb` | `fixed_compute_first` | compute-bound | aligned reference |
| `cf_db` | `fixed_compute_first` | data-bound | mis-aligned (H2) |
| `sf_cb` | `fixed_storage_first` | compute-bound | mis-aligned (H2) |
| `sf_db` | `fixed_storage_first` | data-bound | aligned reference |
| `ba_cb` | `bottleneck_aware` | compute-bound | H1 |
| `ba_db` | `bottleneck_aware` | data-bound | H1 |

- **n = 3 per cell**, 18 runs, **3 counterbalanced blocks** (seeds 2001–2003,
  distinct orders verified — `counterbalance_order_v2.csv`).
- **Held constant:** open-loop driver (`TRAFFIC_DRIVER_MODE=open_loop`,
  `CURL_MAX_TIME=300`, `INFLIGHT_WINDOW=1024`, `DRAIN_S=30`), single episode per
  run, data-path knobs, budget 4/tier/LAN, caps 6/6, telemetry reference,
  workload shape, topology. Only `SCALEUP_POLICY` varies.
- **Validity gates (per run):** G2 episode induction, budget binds, 0×
  `NotPrimaryOrSecondary`, no controller restart, per-run driver self-test.
- The `ba-strict` sticky-commitment arm is **implemented and unit-tested but
  not run** in this campaign (see §6).

---

## 3. Can n = 3 still yield thesis-level results? — The rationale

The thesis answer is **yes**, on five grounds, each documented here so the
manuscript can defend the design up front.

### 3.1 The effects are orders of magnitude, not marginal

The v1 campaign (same cells, same workload shape) measured ~40–50× latency gaps
in the compute-bound episode (aligned p50 ≈ 3–4 ms vs mis-aligned ≈ 163 ms) and
≥ 12× in the data-bound episode (mis-aligned p99 pinned at the 30 s timeout cap
vs aligned ≤ 2.5 s, plus ~2–4× failure rates). With effects of this size the
between-arm signal dwarfs run-to-run system noise: three replicates with
**3/3 direction consistency** are sufficient to establish the qualitative
conclusion. This is a signal-detection argument: the power to *mis*-detect a 40×
effect at n=3 is negligible.

### 3.2 Each replicate is a high-precision estimate, not a single measurement

A single run aggregates tens of thousands of requests and ~260 controller
decision windows. The per-run episode median is a stable estimator of the
run's service behavior. The **run remains the experimental unit** (thesis §8 —
requests within a run are not independent observations), but the within-run
aggregation is exactly why three runs are not "three data points": each run
already averages a large population. This is what makes per-replicate scatter
interpretable rather than anecdotal.

### 3.3 A pre-registered effect-size framework is legitimate evidence

The statistics are **pre-registered** (`analysis_focus.md` §7.4): per episode,
the headline pair (aligned vs mis-aligned) and two primary pairs (`ba` vs
mis-aligned, `ba` vs aligned with a 1.5× equivalence margin), evaluated with
**Cliff's delta** (non-parametric effect size, threshold ≥ 0.6 = large) and
**direction consistency across all 3 replicates**. Mann–Whitney U is computed
and reported **descriptively** (at n=3 the minimum possible p is 0.10, so no
α claim is made). This is a standard, defensible inferential standard for
experimental systems research when effects are large; the thesis simply never
uses "statistically significant" language.

### 3.4 Internal validity — the real thesis risk — is controlled

The principal threat to a systems-thesis result is not sampling error but
confounding. The design controls it: only the policy varies between compared
cells; blocks are counterbalanced; the episode induction is independently
validated (G2); the data path is verified (0× NotPrimary — storage scale-out
yields real read capacity); the budget binds observably; and the driver is
gate-checked per run. A well-controlled design with large, direction-consistent
effects is solid even at n=3; an uncontrolled design would not be saved by n=30.

### 3.5 The claims are scoped

The thesis claims are bounded by `thesis_overview.md` §9: *within the evaluated
two-domain stateful edge testbed and workload families, the control-loop
interfaces affect observable service behavior.* n=3 supports exactly this scope
and nothing broader (no generalizability, no SLA claims, no product comparison).

---

## 4. The statistics framework — what is and is not claimed

| | Claimed | Not claimed |
|---|---|---|
| Direction of effect (which arm is better on p95/timeout/failure) | ✅ with 3/3 replicate consistency | — |
| Magnitude (Cliff's delta, medians, per-replicate spread) | ✅ reported; ≥ 0.6 = large | — |
| Equivalence (`ba` within 1.5× of aligned) | ✅ reported | — |
| Statistical significance (p < 0.05) | ❌ **never** | MWU is descriptive at n=3 (min p = 0.10) |
| Censoring | ✅ percentile values at the 300 s cap flagged `CENSORED`, excluded from tests | — |
| Missing values | ✅ comparisons run only where all 3 runs per cell have a defined value | — |

Pre-registration is recorded in the experiment docs (`experiment_plan.md` v2
SC1–SC6, `analysis_focus.md` §7.4, `rq2v2_p2_03_stats.py`), so the thesis can
state that thresholds and comparisons were fixed before the runs.

---

## 5. Success criteria (SC1–SC6) — analyst-checkable

| # | Criterion | Metric / threshold | Verdict source |
|---|---|---|---|
| SC1 | Cross-over (headline) | per episode, aligned beats mis-aligned on p95 + `timeout_rate`: Cliff's delta ≥ 0.6 **and** 3/3 direction | `rq2v2_p2_03_stats.py` + per-cell tables |
| SC2 | Value of information | `ba` beats mis-aligned (≥ 0.6, 3/3) **and** within 1.5× of aligned median | stats + per-cell tables |
| SC3 | Wrong-action cost | mis-aligned: no targeted-tier relief, budget exhausted on wrong tier, node-minutes/1000 ≥ aligned and ≥ `ba` | relief/relief-flatten + node-minutes |
| SC4 | Classification | `ba` agreement > 50 % in db; cb reported honestly | decision-analysis tool |
| SC5 | Mechanics | budget binds 4/tier/LAN; G2 pass; 0× NotPrimary; no restart; driver gate | per-run gates |
| SC6 | Efficiency | `ba` node-minutes/1000 ≤ mis-aligned | node-minutes |

Each SC yields a yes/no the analyst can verify — this is what makes the
conclusions "clear" despite n=3: the checks are explicit and pre-registered.

---

## 6. Honest limitations and how the thesis handles them

| Limitation | Impact | Thesis handling |
|---|---|---|
| MWU underpowered at n=3 (min p = 0.10) | No significance claim possible | Pre-registered effect-size framework (§3.3, §4); MWU reported descriptively; no "significant" language anywhere |
| No in-campaign no-scale control arm | "Mis-aligned ≈ doing nothing" is not directly measured in v2 | Supported by (a) absence of targeted-tier relief in the mis-aligned arm and (b) the separately validated v1 control group — stated as such, not overclaimed |
| `ba-strict` not run | Capacity-vs-classification (is `ba_db`'s edge capacity or classification?) is not fully disentangled | The thesis claims "telemetry-driven selection recovers like the aligned arm"; the capacity caveat is stated and left as future work |
| v1 magnitudes were measured with the censoring/sync-driver artifact | v1 is motivation, not evidence | v2 reruns on the open-loop driver; v1 retained only as supporting/characterization |
| **Risk:** if v2 effects under open-loop are smaller than v1 suggested, n=3 is thin | Direction could survive while magnitude claims weaken | Sequential block check: after Block 1, verify direction + Cliff's delta magnitude; documented decision rule (continue vs flag) — blocks are independent, so the campaign can stop early without wasted runs |
| Single testbed, emulated WAN, MongoDB-specific | Limited external validity | Standard thesis scope statement (thesis_overview §9) |

---

## 7. What the thesis can conclude (scoped wording guidance)

With SC1–SC4 holding, the thesis may state, in effect-size language:

1. **The fixed policy's choice matters.** The mis-aligned fixed arm shows no
   targeted-tier relief, exhausts its action budget on the wrong tier, and
   consumes ≥ the aligned arm's node-minutes, while its episode p95 and timeout
   rate remain far above the aligned arm's (large effect, consistent across all
   3 replicates).
2. **Telemetry-driven selection recovers service quality like the aligned arm
   without knowing the regime in advance** — `bottleneck_aware` is within the
   aligned arm's range on p95/timeout/failure in both episodes and strictly
   better than the mis-aligned arm (large effect, 3/3).
3. **The classifier is reliable in the data-bound direction** (agreement above
   chance in all replicates) **and ≈ chance in the compute-bound direction**
   (reported; a documented limitation, not a hidden failure).

**Wording rules:** use "consistent across all three replicates", "large effect
(Cliff's delta ≥ 0.6)", "within the aligned arm's range"; never "significant",
"proves", or "optimal". The manuscript's statistics section (`thesis_structure.md`
§5.4) already records that MWU is descriptive at n=3.

---

## 8. Cross-references

- `rq2.md` — research question, gap, hypotheses (this folder).
- **v3 (completed evidence):** [`rq2_conclusions.md`](rq2_conclusions.md) and
  `docs/operation/testing/experiment/v3/rq2/` — `experiment_plan.md` (pre-registered
  gates), `results.md` (36 runs, 34 valid), `post_run_analysis.md`, `analysis/`,
  `graphs/comparison/` + `graphs/thesis/`.
- `docs/operation/testing/experiment/v2/rq2/experiment_plan.md` — v2 section (SC1–SC6).
- `docs/operation/testing/experiment/v2/rq2/run_matrix.md` §10 — 18-run matrix, blocks.
- `docs/operation/testing/experiment/v2/rq2/analysis_focus.md` §7 — measurement + stats contract.
- `docs/operation/testing/experiment/v2/rq2/rq2_v2_rework_plan.md` — implementation + Phase 5.
- `docs/operation/testing/experiment/v2/rq2/analysis/campaign_dataset.csv` — per-run dataset.
- `docs/research_questions/v2/rq2/rq2v2_p2_03_stats.py` — stats tool (effect-size hierarchy).
- `thesis_overview.md` §5–§9; `thesis_structure.md` §5.3–§5.4, §7.3.
