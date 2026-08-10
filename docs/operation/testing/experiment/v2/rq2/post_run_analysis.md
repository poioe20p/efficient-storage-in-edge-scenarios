# Post-Run Analysis — RQ2 Bottleneck-Aware Scaling

**Date**: 2026-08-05 · **Plan**: [experiment_plan.md](experiment_plan.md) · **Results**: [results.md](results.md) · **Dataset**: [analysis/campaign_dataset.csv](analysis/campaign_dataset.csv) (v2, 36 runs) · **Graphs**: [graphs/20260805/](graphs/20260805/) · **Stats**: [analysis/stats_summary.csv](analysis/stats_summary.csv)

---

## 0. v2 36-run campaign (2026-08-05) — mechanically complete, CONFOUNDED

> **This revision supersedes §1–§4 (the v1 18-run analysis, retained below) as
> the RQ2 v2 post-run analysis.** The v2 campaign (open-loop driver, n=6, 36
> runs, seeds 2001–2006) completed **36/36 with exit 0 and all gates passed**,
> but the analysis shows it is **confounded by a load-calibration failure**:
> the open-loop offered load exceeded the platform's sustainable capacity in
> both episodes, so no cell operated in a healthy baseline regime and the
> pre-registered success criteria cannot be cleanly evaluated. **The campaign
> must be re-calibrated and re-run before any thesis conclusion is drawn.**

### 0.1 Objective (v2)

Unchanged from §1: does telemetry determine *which* capacity action is taken,
and what does a wrong action cost? v2 removed the v1 G1–G5 gaps (open-loop
driver, `CURL_MAX_TIME=300`, distinct `timeout` class, n=6 with exact MWU,
sync-cost + relief-flatten measurement).

### 0.2 Mechanism (v2)

Same 3-arm × 2-episode crossed design, 6 counterbalanced blocks (seeds
2001–2006). Open-loop driver: 48 active clients, episode rate 3.0 req/s/client
(cb) / 1.5 req/s/client (db) = **144 / 72 req/s offered**; `INFLIGHT_WINDOW=1024`
per client; per-run driver self-test gate. Per-run analyzers:
`rq2_bottleneck_validation.py`, `rq2_decision_analysis.py`,
`rq2_relief_analysis.py`, `rq2v2_p2_02_relief_flatten.py`,
`rq2v2_p2_01_sync_cost.py`, `rq2_node_minutes.py`, `extract_spawn_metrics.py`,
`metrics_stats.py`.

### 0.3 Results (v2)

**Headline: the campaign did not validate SC1–SC6 as pre-registered.**

| # | Criterion | Verdict | Key evidence (median of 6) |
|---|-----------|---------|------------------------------|
| 1 | Artifact + decision-log contract | ✅ | 36/36; full 20-column rows; open-loop knobs in every env snapshot |
| 2 | Episode induction (G2) | ✅ | 36/36 PASS (independent median validator) |
| 3 | Fixed-arm suppression | ✅ | cf never storage, sf never compute (36 runs) |
| 4 | ba selects pressured tier (SC4) | ✅ | ba_db agreement 77.9 % (> chance, 6/6); ba_cb 50.8 % ≈ chance (honest) |
| 5 | Budget binds (SC5 mechanics) | ✅ | 4/tier/LAN in all scaled cells; T9.8 OK; 0× NotPrimary; no restart |
| 6 | Relief in targeted tier | ⚠️ | In-tier recovery 4–6/8–16; relief-flatten signal 63–69 % (db) — but no cell is service-healthy (ep p50 ≥ 2.6 s) |
| 7 | Scale-down + T9.8 | ✅ | Present where scaled; no cooldown violation |
| 8 | Cross-over (SC1) | ❌ | **Not reproduced / inverted in db**: aligned `sf_db` 49.8 % vs mis-aligned `cf_db` 19.7 % timeout (6/6 wrong direction, p = 0.0022); cb cf-vs-sf not significant (p = 0.394) |
| 9 | Efficiency / node-minutes (SC6) | ❌ as written → pre-registered dual-budget finding | ba_db 5.812 node-min/1000 (both budgets, 8+8) vs sf_db 2.404 / cf_db 2.841; reported as a finding (bounded budget, quality without episode knowledge) |
| 10 | Stats / sync-cost | ⚠️ | Exact MWU at n=6 (min p = 0.0022) but headline pairs not significant or anti-hypothesis; storage initial-sync ≈ 10 s @ 54–70 % storage CPU |

**The overload, with evidence:**
- Offered 144 / 72 req/s vs sustained service 119 (cf_cb), 36 (cf_db), 34
  (sf_db), 62 (ba_db) req/s — offered exceeds capacity in both episodes.
- Same-run control: baseline/`demand_drop` (48 req/s) p50 ≈ 7 ms vs episode
  (144 req/s) p50 ≈ 2.8 s in `cf_cb_1` — queue-overload, not a regression.
- The **G2 calibration runs themselves were overloaded** (`ba_cb_cal2` p50 ≈
  3.1 s / 15 % timeout; `ba_db_cal2` p50 ≈ 67 s / 22 % timeout) and were
  accepted — the calibration checked only the drop-free window
  (`window/rate > 300 s`), not service capacity.
- Data-bound storage path: `avg_time_db_ms` 3 s (ba_db) to 11 s (sf_db) vs
  v1's ~100–250 ms — MongoDB saturated under open-loop concurrency
  (`INFLIGHT_WINDOW=1024` vs the sync driver's 1 in-flight/client).
- 0× `NotPrimaryOrSecondary` and no controller restart across all 36 runs —
  the saturation is genuine capacity, not a read-preference defect.

**What the v2 campaign *did* establish (robust, 6/6):**
- The **open-loop driver works as intended** — offered load is preserved
  across arms (no latency-coupled divergence; G1 genuinely removed), which is
  precisely why the overload is now visible instead of masked.
- **`ba_db` is the most robust data-bound cell**: 8.7–12.9 % timeout, ≤ 1.66 %
  failure, ep p50 ≤ 2.6 s — 6/6 better than both fixed arms, incl. the aligned
  `sf_db` (43–53 % timeout). A real, reproducible value-of-information signal.
- **Mechanics are clean**: budget binds, T9.8 holds, classifier asymmetry
  reported honestly (db strong, cb ≈ chance), sync-cost quantified.

### 0.4 Gaps & Next Steps (v2)

1. **Re-calibrate the load before re-running**: lower episode rates so the
   aligned arms reach a healthy baseline (e.g. ≤ 1.0 req/s/client cb) **and**
   make the G2 gate validate service capacity (not just the drop-free window);
   for the data-bound episode consider bounding open-loop concurrency or
   raising `STORAGE_CPUS` / pool size.
2. **Probe the ~120 req/s compute-bound ceiling** (43 % CPU at 0.4 ms service —
   a non-CPU bottleneck, e.g. WAN emulation / aggregator / VIP flow pinning).
3. **Re-run the 36-run campaign** on the re-calibrated load, then evaluate
   SC1–SC6 as pre-registered (incl. the SC6 dual-budget rule).
4. Retain this dataset as the **overload-characterization record** (bounds the
   platform's capacity envelope under the open-loop driver).
5. Update this post-run analysis after the re-run.

---

## v1 18-run campaign (2026-08-04) — prior revision (supporting record)

> Retained below as the v1/supporting record. Its caveats (G1 latency-coupled
> driver, G2 30 s censoring, G3 n=3) keep it from being final thesis evidence;
> the v2 section above is the current record.

### 1. Objective

Answer the thesis RQ2: **under compute-bound and data-access-bound demand, does a
bottleneck-aware controller — choosing the scale-out action (compute or storage)
from tier telemetry — recover service quality and use resources more efficiently
than the fixed compute-only or storage-only policies an operator would otherwise
configure?** The campaign isolates the value-of-information question: does
telemetry determine *which* capacity action is taken, and what does a wrong
action cost?

Hypotheses: **H1** (right action) — `bottleneck_aware` selects the pressured tier
and matches the correctly-aligned fixed arm; **H2** (wrong-action cost) — the
mis-aligned fixed arm wastes its budget on the wrong tier and stays degraded;
**H3** (decision quality) — classifier-vs-episode agreement is above chance.

Independent variable: `SCALEUP_POLICY ∈ {fixed_compute_first, fixed_storage_first,
bottleneck_aware}` crossed with episode type (compute-bound | data-bound), single
episode per run, 3 replicates per cell (18 main runs; 4 pre-flights gated the
campaign).

## 2. Mechanism

Three policy arms ran the same calibrated single-episode workload
(baseline → episode 600 s → recovery_gap → demand_drop) under the control-group
platform (Option B: caps 6/6 above the 4/tier/LAN action budget; median latency
signal; composite storage signal with storage-CPU floor 35; scale-down 3-of-6
compute / 3-of-5 storage with fire-keyed cooldown protection). Only
`SCALEUP_POLICY` varied. Episode files were calibrated (G2, pre-flight) so
`service_pressure 1.0` induces a clean compute bottleneck (DB-free) and the
data-access mix (`content_lookup/update/aggregate`) induces a DB bottleneck.

Per run: `rq2_bottleneck_validation.py` (independent raw-window median
verdict), `rq2_decision_analysis.py` (decision universe, action counts, budget,
classifier agreement, T9.8), `rq2_relief_analysis.py` (time-to-recover),
`rq2_node_minutes.py` (efficiency), `extract_spawn_metrics.py` (time-to-usable-
capacity), plus `metrics_stats.py` latency/resource summaries. The campaign was
counterbalanced in 3 blocks of 6 cells.

## 3. Results

### Success criteria verdicts

| # | Criterion | Verdict | Key evidence |
|---|-----------|---------|--------------|
| 1 | Artifact + decision-log contract | ✅ | 18/18; full 20-column rows; dedup no-op |
| 2 | Episode induction (G2) | ✅ | 18/18 PASS; cb: proc 0.2–0.8 ms ≫ db 0; db: db 103–307 ms ≫ proc, storage CPU 27–55 % |
| 3 | Fixed-arm suppression | ✅ | cf never storage, sf never compute (18 runs) |
| 4 | ba selects pressured tier | ✅ | cb → compute 8/LAN; db → storage 8/LAN |
| 5 | Budget binds | ✅ | 4/tier/LAN reached in all scaled cells |
| 6 | Relief in targeted tier | ⚠️ | Aligned arms ~50 % in-tier recovery (20–51 s); cf_db recovers wrong tier but stays degraded |
| 7 | Scale-down + T9.8 | ✅ | Present where scaled; no cooldown violation in 18 runs |
| 8 | Cross-over contrast | ✅ | cb: cf≈ba beat sf (p95 221/234 vs 376 ms); db: ba≥sf≫cf (cf p99=30 s timeouts, failures 1.0–3.4 %) |
| 9 | Efficiency / node-minutes | ✅ | cf_db wastes 4.2–4.7 comp node-min/1000; ba_db 2.5+1.8, best db failure rate |
| 10 | RQ1 semantics / no restart | ✅ | 18/18 |

### What the campaign established

- **The data-path fix held end-to-end.** Every data-bound run served reads from
  storage secondaries (0× `NotPrimaryOrSecondary` in all service logs) with the
  three knobs present in every env snapshot — so storage scale-out produced real
  usable read capacity (TTFT 29–40 s) and the cross-over was measurable, not
  confounded (unlike the deleted pre-fix Block-1 set).
- **H1 supported.** `bottleneck_aware` matched the aligned fixed arm on quality
  and, in the data-bound episode, was the best cell: p95 1165–1313 ms, p99
  ≤2.5 s (no 30 s tail), failures 0.39–0.79 %, vs the aligned `sf` arm's 30 s
  p99 tail in 2/3 replicates and the mis-aligned `cf` arm's 30 s p99 in 3/3.
- **H2 supported.** The mis-aligned arms showed exactly the predicted signature:
  `cf_db` pinned p99 at the 30 s timeout with the highest failures, spending 4.2–
  4.7 compute node-min/1000 on a data-bound episode; `sf_cb` spent storage
  actions (1/LAN) that relieved nothing (p50 ~160 ms vs ~3–4 ms for the aligned
  arms).
- **H3 supported (with a caveat).** `ba` classifier-vs-episode agreement
  54–77 % across 6 runs, all above chance; the residual compute-bound storage
  fires (0–2/LAN) are the accepted floor-35 latency-tail behavior, and the
  agreement denominator (both-eligible episode windows) is the conservative one.
- **Efficiency nuance.** The bottleneck-aware arm is not the cheapest — that is
  the correctly-aligned fixed arm, which exploits a known regime — but it is the
  most robust: it avoids the mis-aligned arm's waste and matches the aligned
  arm's quality without knowing the regime in advance.

## 4. Gaps & Next Steps

- **Relief measurement (criterion 6) is partial.** In the pure-compute episode
  the compute score stays near its threshold even after scale-out, so in-tier
  recovery is low (0–4/8) in `cf_cb`/`ba_cb`; the relief tool's recovery
  definition (score falls under threshold) is a conservative proxy. A follow-up
  could add "score flattening after action" as a secondary relief signal.
- **`sf_db` tail (30 s p99 in 2/3 replicates).** The aligned storage-first arm
  shows residual tail timeouts during storage scale-out transients that `ba_db`
  does not. Worth one thesis paragraph; not a harness defect, but its cause
  (replica-sync/readiness transients vs VIP convergence) is not isolated here.
- **Node-minutes approximation.** Uses decision-row timing (D4 caveat); fine for
  relative arm comparison, not for absolute capacity accounting.
- **No scale-to-capacity stress on the aligned compute arm** beyond 8 spawns;
  the budget (4/LAN) binds before caps (6/6), so cap-vs-budget interplay beyond
  exhaustion was not observable in this campaign.
- **Raw artifacts are on `cloud-vm` only** (25 folders). Regeneration of
  `campaign_dataset.csv`/graphs is possible via
  `rq2_bottleneck_aware_campaign.py` if a re-analysis is ever needed.
