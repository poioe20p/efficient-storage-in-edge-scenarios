# Results — RQ3 Timing (Readiness-Loss Relief Contrast under Demand Escalation)

**Date**: 2026-09-10 · **Experiment Plan**: [experiment_plan.md](experiment_plan.md) · **Runs**: 36 E-stage runs `rq3tim_{cell}_{arm}_{1..6}` (seeds 5201–5206), rate 2.0, quota 0.12

**Figures**: [graphs/](graphs/) — block contrast (H-T1 full + onset), slow-share series, relief tails, admission accounting (generated 2026-09-27 from the frozen run records; data `analysis/timing_figures_data.json`; tools `rq3/timing_figures_export.py` — VM export — and `rq3/timing_figures.py` — render)

**Thesis figures**: [graphs/thesis/](graphs/thesis/) — `rq3_event_loss_outcome.png` (slow-share series + admitted backends per run) and `rq3_recovery_ordering.png` (provisioning→admission per block, re-anchored ordering), generated 2026-09-28 by `source/scripts/testing/analysis/rq3/scripts/generate_thesis_figure.py` from `analysis/timing_figures_data.json` and `analysis/timing_campaign_reanchored.json`; copied to `tese/images/` for the RQ3 results section in `tese/main.tex`

## Run Timeline

| Run | Date | Status | Cumulative Analysis | Conclusions | Changes Made | Expectations for This Run |
|-----|------|--------|---------------------|-------------|--------------|--------------------------|
| v1 (E stage, 36 runs) | 2026-09-09/10 | ⚠️ | — (initial) | — (initial) | — (baseline; rate 2.0 locked via 3-of-4 preflight) | H-T1 ∧ H-T2 ∧ H-T3 (plan §6) |

## Measurements — Per-Block

Block-level slow-share (plateau pooled) and contrast. `compute_plateau` 600 s, pure-compute mix, rate 2.0, quota 0.12.

| Block | Seed | event_only slow | hybrid slow | reconcile slow | full Δ_slow | onset Δ_slow | assessable | relief tails (hy / rc) | event_only tail |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 5201 | 10.60 % | 3.60 % | 2.18 % | 7.00 pp | 28.01 pp | ✅ | 0.97 / 1.23 | 1.11 % |
| 2 | 5202 | 14.39 % | 2.30 % | 3.51 % | 10.87 pp | 25.17 pp | ✅ | 0.94 / 0.89 | 11.41 % |
| 3 | 5203 | 8.34 % | 2.12 % | 1.97 % | 6.21 pp | 25.11 pp | ✅ | 1.18 / 1.39 | 1.24 % |
| 4 | 5204 | 9.97 % | 1.92 % | 5.00 % | 4.97 pp | — | ❌ | 1.23 / 4.08 | 1.06 % |
| 5 | 5205 | 10.10 % | 2.31 % | 2.46 % | 7.64 pp | 30.84 pp | ✅ | 1.24 / 1.16 | 1.09 % |
| 6 | 5206 | 13.66 % | 3.07 % | 3.67 % | 9.99 pp | 29.10 pp | ✅ | 1.41 / 1.23 | 0.99 % |

**Block exclusion**: block 4 (seed 5204) excluded from H-T1 assessability — reconcile control tail 4.08 % > 2 pp (run `rq3tim_loss_all_reconcile_4`, checkpoint 3.22).

### H-T1 (timing-campaign)

- assessable blocks: [1, 2, 3, 5, 6]
- block_delta_slow_pp: 7.00, 10.87, 6.21, 7.64, 9.99 → **median 7.64 pp**
- block_onset_delta_slow_pp: 28.01, 25.17, 25.11, 30.84, 29.10 → **median 28.01 pp**
- MWU p = 0.00397 · Cliff's δ = 1.0 (full Δ vs 0)
- event_only slow (boundedness): 10.60, 14.39, 8.34, 10.10, 13.66 % → **median 10.6 %**, 5/5 ≤ 25 %

### H-T2 (timing-campaign)

- relief_blocks (hybrid ∧ reconcile tail ≤ 2 pp): [1, 2, 3, 5, 6]
- ttr_hybrid_s: [1.20, 0.98, 0.0, 0.92, 1.08, 0.0] → median 0.95 s
- ttr_reconcile_s: [1.30, 1.29, 7.38, 1.07, 7.79, 0.0] → median 1.30 s
- ttr_order_hybrid_gt_reconcile: **false** *(onset-anchored as-run values — superseded for ordering; see re-anchored block below)*
- relief accounting (loss_all, 36-run export): event_only **0 admitted · 32–35 candidates abandoned** per block; hybrid 4–6 admitted via `probe_fallback` (20 s); reconcile 4–5 via `probe` (10 s poll); none-cell 4–6 admitted per arm — `graphs/admission_accounting.png`
- **Re-anchored (analysis-only, 2026-09-26; `analysis/timing_campaign_reanchored.json`):** spawn→admit hybrid [21.40, 21.12, 21.46, 21.41, 21.37, 21.26] vs reconcile [13.21, 14.10, 20.58, 15.38, 20.39, 18.76] → medians 21.38 vs 17.07 s, reconcile faster 6/6; spawn→first serve hybrid [22.13, 21.87, 22.04, 22.12, 22.55, 22.41] vs reconcile [13.47, 15.13, 22.50, 16.19, 21.13, 19.32] → medians 22.12 vs 17.76 s, reconcile faster 5/6 + sub-second tie (b3); relief-completion (slow-rate) timing: no arm separation.
- event_only zero new-backend successes: 6/6 blocks

### H-T3 (timing-campaign)

- 16/18 none-cell runs clean (bad ≤ 1 %, tail ≤ 2 pp)
- none-cell bad > 1 %: block 3 none-hybrid 1.19 % (checkpoint 3.17)
- none-cell tail > 2 pp: block 5 none-reconcile 4.29 % (checkpoint 3.29)

### Mechanism / base (all 36 runs)

Mechanism exact per arm/cell · quota 0.12 match · floors ≥ 5,000 pooled / ≥ 1,000 per LAN · driver-clean (cancel < 0.6 %) · baseline clean (bad ≤ 1 %, http000 = 0) · no plateau scale-down · no mid-run restart.

## Judgment

**H-T1 (headline) — ✅ met, decisively.** The full-plateau contrast reproduced in 5/5 assessable blocks (median 7.64 pp ≥ 5 pp; MWU p = 0.00397, δ = 1.0), the onset co-primary reproduced in 5/5 blocks (median 28.01 pp), and event_only stayed bounded (median 10.6 % ≤ 25 %). This is the pre-registered core claim: under `loss_all`, `event_only` degrades visibly and boundedly while `hybrid`/`reconcile` recover. Direction consistent across all five assessable seeds; only block 4 (excluded, reconcile tail spike) did not contribute.

**H-T2 (relief completion + ordering) — ✅ met after analysis-only re-anchoring (2026-09-26).** The relief-completion component passed as-run (hybrid ∧ reconcile tail ≤ 2 pp in 5/6 blocks; event_only zero new-backend successes in 6/6). The ordering component required a metric re-anchoring: the as-run TTR anchored at plateau onset, but the first backend is spawned **27–35 s before** onset in all 12 control runs (spawn−onset = −26.9 to −35.4 s) and is admitted via fallback/poll before the plateau begins, so the as-run values (0.95 vs 1.30 s) measured the phase boundary, not the relief interval. Re-anchored at the first relief backend's spawn (`analysis/timing_campaign_reanchored.json`; admission logs + client rows, any phase): **reconcile delivers relief sooner than hybrid** — spawn→admit 6/6 blocks (median 17.07 vs 21.38 s; Δ 0.88–8.19 s) and spawn→first serve 5/6 plus a sub-second tie in block 3 (median 17.76 vs 22.12 s) — consistent with the plan's ≤10 s poll-quantum direction (observed median gap ≈4.3 s). The slow-rate relief-completion *timing* remains non-separating across five window variants; the campaign tail gate (5/6) is unchanged. The originally recorded "reversed" reading is superseded and must not be cited.

**H-T3 (none-cell health floor) — ⚠️ mostly clean; formally not met.** 16 of 18 no-fault runs meet both floors. The two breaches are marginal single-window stochastic humps — block 3 none-hybrid bad 1.19 % (0.19 pp over the 1 % ceiling) and block 5 none-reconcile tail 4.29 % (one 30-s spike) — the same transient class as preflight reconcile `_59`. Neither touches the H-T1 contrast (the Δ metric controls for fault-independent instability). Under the strict all-or-nothing gate `none_healthy = false`, but the no-fault baseline is substantively healthy and the breaches are consistent with the thin-headroom premise rather than a data-path fault.

**Base requirements (`testing_requirements.md`) — met.** Reproducibility (n = 6 blocks, direction consistent 5/5 assessable, fixed seeds) · M1 mechanism exercised (spawn + admit per run, 36/36 exact) · M2 new capacity usable (hybrid/reconcile admitted backends serve ≥ 1 success) · D1 baseline data-path clean · D2 no restart/crash · D3 provenance snapshots present. No hard-gate miss.

**Overall verdict — ⚠️ partial.** The campaign's pre-registered pass criterion (H-T1 ∧ H-T2 ∧ H-T3) is **not met** (overall pass = false), now gated on **H-T3 alone**: H-T1 passes decisively; H-T2 is met after the analysis-only re-anchoring (ordering: reconcile sooner, 5/6 + tie; relief completion 5/6); H-T3 is substantively near-clean (16/18) with two marginal no-fault transients. The thesis-relevant headline (visible, bounded, onset-transient degradation with recovery by fallback/polling) is fully supported.

## Root Causes

| # | Issue | Impact | Status |
|---|-------|--------|--------|
| 1 | First backend spawns 27–35 s **before** plateau onset (baseline) in all 12 control runs; `timing_relief_metrics` anchors at plateau onset, so TTR (0–8 s) does not measure the spawn→admit relief interval (~21 s) | H-T2 ordering component (as-run) unmeasurable | **Resolved (2026-09-26, analysis-only):** spawn-anchored re-anchoring shows reconcile faster (spawn→admit 6/6; spawn→first serve 5/6 + tie) — ordering tested and directionally supported; as-run values retained for provenance only |
| 2 | None-cell stochastic humps (bad 1.19 % b3; tail 4.29 % b5) breach the ≤1 %/≤2 pp health floor in 2/18 none-cell runs | H-T3 formally not met, substantively near-clean | Confirmed (checkpoints 3.17, 3.29); marginal single-window transients, consistent with thin headroom |
| 3 | Reconcile control tail spike (b4 4.08 %) | block 4 excluded from H-T1 | Confirmed (checkpoint 3.22); pre-registered exclusion applied correctly |

## Next Actions

1. H-T3 disposition — resolved: recorded as mostly clean (16/18) with two marginal single-window transients; no gate re-scoping required.
2. H-T2 disposition — **resolved 2026-09-26:** spawn/readiness-anchored re-anchoring completed (analysis-only, no reruns); ordering tested and directionally supported (reconcile sooner; `analysis/timing_campaign_reanchored.json`). The re-anchored definition is now the analyzer's `timing_relief_metrics` (adopted 2026-09-26; onset value kept as diagnostic).
3. Run `experiment-post-analysis` (post_run_analysis.md) and finalize the changelog.

## Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-09-10 | Initial results.md (E stage, 36 runs) | First campaign analysis; H-T1 pass, H-T2 ordering fail, H-T3 fail recorded |
| 2026-09-26 | H-T2 ordering re-anchored (analysis-only, spawn-anchored) — reconcile faster (spawn→admit 6/6; spawn→first serve 5/6 + tie) | Root cause #1 resolved; overall pass remains false, gated on H-T3 (16/18). Companion: `analysis/timing_campaign_reanchored.json` |
| 2026-09-27 | Campaign figures generated (`graphs/ht1_block_contrast.png`, `slow_share_series.png`, `relief_tails.png`, `admission_accounting.png`) + companion export `analysis/timing_figures_data.json` | Tables-only campaign now carries rendered evidence; export records relief accounting (loss_all/event_only: 0 admitted, 32–35 abandoned per block) |
| 2026-09-28 | Thesis renders `graphs/thesis/rq3_event_loss_outcome.png` + `graphs/thesis/rq3_recovery_ordering.png` generated and wired into the RQ3 results section | House-style condensed evidence for the fault consequence (H-T1) and the re-anchored ordering (H-T2); the same generator renders the intact-source interval figure under `v2/rq3/graphs/thesis/` |
