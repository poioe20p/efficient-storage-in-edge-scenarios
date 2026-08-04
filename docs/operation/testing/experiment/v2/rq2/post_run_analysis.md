# Post-Run Analysis — RQ2 Bottleneck-Aware Scaling

**Date**: 2026-08-04 · **Plan**: [experiment_plan.md](experiment_plan.md) · **Results**: [results.md](results.md) · **Dataset**: [analysis/campaign_dataset.csv](analysis/campaign_dataset.csv) · **Graphs**: [graphs/comparison/](graphs/comparison/)

## 1. Objective

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
