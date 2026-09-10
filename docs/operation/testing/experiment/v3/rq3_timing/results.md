# Results — RQ3 Timing (Readiness-Loss Relief Contrast under Demand Escalation)

**Date**: 2026-09-10 · **Experiment Plan**: [experiment_plan.md](experiment_plan.md) · **Runs**: 36 E-stage runs `rq3tim_{cell}_{arm}_{1..6}` (seeds 5201–5206), rate 2.0, quota 0.12

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
- ttr_order_hybrid_gt_reconcile: **false**
- event_only zero new-backend successes: 6/6 blocks

### H-T3 (timing-campaign)

- 16/18 none-cell runs clean (bad ≤ 1 %, tail ≤ 2 pp)
- none-cell bad > 1 %: block 3 none-hybrid 1.19 % (checkpoint 3.17)
- none-cell tail > 2 pp: block 5 none-reconcile 4.29 % (checkpoint 3.29)

### Mechanism / base (all 36 runs)

Mechanism exact per arm/cell · quota 0.12 match · floors ≥ 5,000 pooled / ≥ 1,000 per LAN · driver-clean (cancel < 0.6 %) · baseline clean (bad ≤ 1 %, http000 = 0) · no plateau scale-down · no mid-run restart.

## Judgment

**H-T1 (headline) — ✅ met, decisively.** The full-plateau contrast reproduced in 5/5 assessable blocks (median 7.64 pp ≥ 5 pp; MWU p = 0.00397, δ = 1.0), the onset co-primary reproduced in 5/5 blocks (median 28.01 pp), and event_only stayed bounded (median 10.6 % ≤ 25 %). This is the pre-registered core claim: under `loss_all`, `event_only` degrades visibly and boundedly while `hybrid`/`reconcile` recover. Direction consistent across all five assessable seeds; only block 4 (excluded, reconcile tail spike) did not contribute.

**H-T2 (relief completion + ordering) — ⚠️ partially met / ❌ missed on ordering.** The relief-completion component passed (hybrid ∧ reconcile tail ≤ 2 pp in 5/6 blocks; event_only zero new-backend successes in 6/6). The time-to-relief ordering component **failed**: hybrid median TTR (0.95 s) < reconcile (1.30 s), opposite of the plan's expectation that reconcile relieves ~10 s earlier than hybrid's 20 s fallback. Verification (admission-log timestamps vs `phase_bounds` onset) shows why: the first backend is spawned **27–35 s before** the plateau onset in all 12 control runs (spawn−onset = −26.9 to −35.4 s), i.e., during the baseline phase, and is admitted via fallback/poll before the plateau begins. The metric `timing_relief_metrics` (first dynamic-backend success after plateau onset) therefore returns ~0–8 s for both arms and does not measure the spawn→admit relief interval (~21 s per admission log). The metric is faithful to the plan's literal TTR definition, but the plan's assumption that spawns occur after plateau onset is empirically false at quota 0.12, so the ordering expectation was not actually exercised — **inconclusive as a measure of relief latency**, not evidence that reconcile relieves slower.

**H-T3 (none-cell health floor) — ⚠️ mostly clean; formally not met.** 16 of 18 no-fault runs meet both floors. The two breaches are marginal single-window stochastic humps — block 3 none-hybrid bad 1.19 % (0.19 pp over the 1 % ceiling) and block 5 none-reconcile tail 4.29 % (one 30-s spike) — the same transient class as preflight reconcile `_59`. Neither touches the H-T1 contrast (the Δ metric controls for fault-independent instability). Under the strict all-or-nothing gate `none_healthy = false`, but the no-fault baseline is substantively healthy and the breaches are consistent with the thin-headroom premise rather than a data-path fault.

**Base requirements (`testing_requirements.md`) — met.** Reproducibility (n = 6 blocks, direction consistent 5/5 assessable, fixed seeds) · M1 mechanism exercised (spawn + admit per run, 36/36 exact) · M2 new capacity usable (hybrid/reconcile admitted backends serve ≥ 1 success) · D1 baseline data-path clean · D2 no restart/crash · D3 provenance snapshots present. No hard-gate miss.

**Overall verdict — ⚠️ partial.** The campaign's pre-registered pass criterion (H-T1 ∧ H-T2 ∧ H-T3) is **not met**: H-T1 passes decisively; H-T2's relief-completion passes but its TTR-ordering component is untested (the metric does not measure the intended quantity); H-T3 is substantively near-clean (16/18) with two marginal no-fault transients. The thesis-relevant headline (visible, bounded, onset-transient degradation with recovery by fallback/polling) is fully supported.

## Root Causes

| # | Issue | Impact | Status |
|---|-------|--------|--------|
| 1 | First backend spawns 27–35 s **before** plateau onset (baseline) in all 12 control runs; `timing_relief_metrics` anchors at plateau onset, so TTR (0–8 s) does not measure the spawn→admit relief interval (~21 s) | H-T2 ordering component fails / untested | Confirmed (admission-log vs phase_bounds); metric faithful to the plan's literal definition, but the plan's post-onset-spawn assumption is false — re-anchor at spawn/readiness to actually test ordering |
| 2 | None-cell stochastic humps (bad 1.19 % b3; tail 4.29 % b5) breach the ≤1 %/≤2 pp health floor in 2/18 none-cell runs | H-T3 formally not met, substantively near-clean | Confirmed (checkpoints 3.17, 3.29); marginal single-window transients, consistent with thin headroom |
| 3 | Reconcile control tail spike (b4 4.08 %) | block 4 excluded from H-T1 | Confirmed (checkpoint 3.22); pre-registered exclusion applied correctly |

## Next Actions

1. H-T3 disposition — resolved: recorded as mostly clean (16/18) with two marginal single-window transients; no gate re-scoping required.
2. Decide H-T2 disposition: accept the TTR-ordering failure as reported, or re-anchor `timing_relief_metrics` (spawn/readiness-anchored) and re-analyze — a re-anchoring is analysis-only, does not require reruns.
3. Run `experiment-post-analysis` (post_run_analysis.md) and finalize the changelog.

## Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-09-10 | Initial results.md (E stage, 36 runs) | First campaign analysis; H-T1 pass, H-T2 ordering fail, H-T3 fail recorded |
