# RQ3 v2 — Trigger Divergence Calibration Results

**Date**: 2026-07-24 · **Status**: ✅ Complete (8 runs: 6 divergence + 2 storage probe) · **Plan**: [`calibration_plan.md`](calibration_plan.md) (superseded by these results for final values)

---

## 1. Decision

**✅ GO — Proceed to 9-run RQ3 evaluation.** The G0-v6 thresholds produce clear three-way compute divergence. Storage CPU weight calibrated to 0.20 — CPU adds a real secondary signal without dominating T_db.

---

## 2. Run Summary

| # | Label | Mode | Events | Node Timings | Policy-State Rows | Storage Spawns | Compute Spawns |
|---|-------|------|:------:|:------------:|:-----------------:|:--------------:|:--------------:|
| C-DS1 | `20260724_012335_rq3_cal_ds_1` | degradation_score | 120 | 84 | 314 (157+157) | 24 | 7 |
| C-DS2 | `20260724_021026_rq3_cal_ds_2` | degradation_score | 122 | 88 | 319 (159+160) | 24 | 8 |
| C-CO1 | `20260724_025622_rq3_cal_cpu_1` | cpu_only | 163 | 103 | 316 (158+158) | 22 | 19 |
| C-CO2 | `20260724_034309_rq3_cal_cpu_2` | cpu_only | 171 | 109 | 314 (157+157) | 24 | 13 |
| C-LO1 | `20260724_042902_rq3_cal_lat_1` | latency_only | 61 | 49 | 315 (158+157) | 15 | 3 |
| C-LO2 | `20260724_051257_rq3_cal_lat_2` | latency_only | 68 | 54 | 312 (156+156) | 17 | 3 |

> **Note on spawn counts**: Storage and compute spawns are score-triggered only
> (counted via `[scale-up] storage triggered` and `[scale-up] compute triggered`
> in controller logs). Reserve spawns (`standby_storage: spawning reserve`,
> typically 1 per run from the persistent reserve mechanism) are excluded.
> The `STORAGE_PERSISTENT_RESERVE_ENABLED=1` mechanism pre-warms one storage
> node; these spawns are not degradation-score FPs and are counted separately
> in the D1 baseline FP analysis.

**Within-mode consistency**:
- degradation_score: 120–122 events (2% spread) ✅
- cpu_only: 163–171 events (5% spread) ✅
- latency_only: 61–68 events (11% spread) ⚠️ (higher than other modes but still within acceptable range for n=2; 9-run evaluation will provide n=3)

---

## 3. Divergence Check Results

### S4 — No Tracebacks ✅

Zero Python `Traceback` entries across all 12 controller logs (6 runs × 2 LANs).

### D1 — Baseline FP Divergence ⚠️ Inconclusive (expected)

| Mode | Compute FPs | Storage FPs |
|---|---|---|
| degradation_score | 2, 2 | 1, 2 |
| cpu_only | 2, 2 | 2, 2 |
| latency_only | 0, 0 | 1, 1 |

cpu_only = degradation_score for compute FPs (2=2). The 60s baseline at 10%
client fraction and 1 req/s produces near-floor CPU and T_proc — no mode
triggers meaningfully. This was anticipated in the plan's validity threats
(§9): the baseline phase is too short for robust FP measurement.

**Verdict**: Inconclusive but not blocking. D3 confirms behavioural separation.

### D2 — Stress Detection (Compute) ✅

| Mode | Rep 1 | Rep 2 | Verdict |
|---|---|---|---|
| degradation_score | 7 | 8 | ✅ Both ≥ 1 |
| cpu_only | 19 | 13 | ✅ Both ≥ 1 |
| latency_only | 3 | 3 | ✅ Both ≥ 1 |

All three modes detected compute stress. cpu_only spawned 2.3× more compute
nodes than degradation_score (16 avg vs 7.5 avg), confirming the CPU-only
trigger fires more aggressively on the same workload.

### D2b — Stress Detection (Storage) ✅

| Mode | Rep 1 | Rep 2 | Verdict |
|---|---|---|---|
| degradation_score | 24 | 24 | ✅ Both ≥ 1 |
| cpu_only | 22 | 24 | ✅ Both ≥ 1 |
| latency_only | 15 | 17 | ✅ Both ≥ 1 |

All three modes detected storage stress. cpu_only (22–24) and the
pre-calibration degradation_score at W_STORAGE_CPU=0.60 (24) produce similar
storage spawn counts — the CPU component at high weight dominates the storage
score. latency_only (15–17) is distinct. This motivated the storage CPU weight
probe (§6), which reduced degradation_score storage weight from 0.60 to 0.20,
bringing spawns to 18 — between cpu_only and latency_only.

### D3 — Score Component Divergence ✅

`compute_spike` phase, LAN1 mean scores:

| Mode | Rep 1 | Rep 2 | Mean |
|---|---|---|---|
| degradation_score | 0.293 | 0.297 | **0.295** (1.4% spread) |
| cpu_only | 0.438 | 0.469 | **0.454** (7% spread) |
| latency_only | 0.024 | 0.108 | **0.066** (350% spread) ⚠️ |

Clear three-way separation in mean scores:
- **cpu_only**: Highest scores — CPU component dominates, crosses threshold most aggressively
- **degradation_score**: Middle scores — both components contribute but dilute each other (0.40 × CPU + 0.60 × T_proc)
- **latency_only**: Lowest mean — T_proc rarely crosses floor=25ms at this workload level

**Caveat — latency_only within-mode variance**: The 350% spread between
latency_only replicates (0.024 vs 0.108) is substantially larger than the
other modes' spreads (1.4% and 7%). This suggests latency_only behaviour
may be more sensitive to run-to-run workload alignment, as T_proc at floor=25ms
to span=80 has a narrow dynamic range. Despite the variance, both latency_only
replicates remain clearly below degradation_score (mean 0.295), so the
three-way ordering is preserved. The 9-run evaluation (n=3 per mode) will
provide a third replicate to narrow the latency_only variance estimate.

The score magnitudes directly reflect the weight composition.

---

## 4. Aggregate Divergence Picture

```text
           Events  Compute Spawns  D3 Mean Score
cpu_only:    167        16              0.454
   ds:       121         7.5            0.295
lat_only:     64.5       3              0.066
```

Three independent metrics (total elasticity activity, compute spawn counts,
per-phase score magnitudes) all show the same three-way ordering. The
divergence is systematic, not noise-driven.

---

## 5. Compute Pre→Post Improvement (C-DS1, degradation_score)

From per_node_stats.csv of C-DS1 (degradation_score, compute_spike):

| LAN | Pre-scale CPU | Post-scale CPU | Drop |
|---|---|---|---|
| lan1 | 46% | 23% | −23pp |
| lan2 | 50% | 22% | −28pp |

The ≥15pp improvement criterion from G0-v6 results_v4.md §5 (success criteria
S2) is met on both LANs. Scaling produces real compute relief. This confirms
the pre→post improvement prerequisite from rq3_v2.md §3.6 for the
degradation_score mode at the G0-v6 resource configuration.

---

## 6. Storage CPU Weight Probe — Complete

### 6.1 Probe Runs

| # | Label | W_STORAGE_CPU | Events | Storage Spawns | Compute Spawns | Status |
|---|-------|:------------:|:------:|:-------------:|:-------------:|--------|
| C-W20 | `20260724_091456_rq3_cal_ds_w20` | 0.20 | 81 | 18 | 5 | ✅ Complete |
| C-W20_R | `20260724_100100_rq3_cal_ds_w20_rep` | 0.20 | — | 12* | — | ⚠️ Partial (stalled mid-run) |

> \* C-W20_R stalled during `inter_hotspot_cooldown` (SSH keepalive drop;
> the `make` process on the VM was unaffected but client processes exited
> prematurely). The 12 storage spawns cover `storage_storm` + `tier1_hotspot`
> only, not the full 7-phase workload. The storage spawn rate per completed
> stress phase (12 spawns / 2 phases = 6/phase) is comparable to C-W20's
> rate (18 spawns / 3 storage-relevant phases ≈ 6/phase), providing weak
> directional confirmation. Not used as primary evidence for W1–W3.

### 6.2 W1–W3 Evaluation (C-W20)

| Check | Measurement | Result | Verdict |
|---|---|---|---|
| **W1 — CPU contribution visible** | `storage_score` during `storage_storm` above `storage_base_threshold` (all rows, both LANs) | 54/54 rows (100%) | ✅ CPU component crosses threshold consistently |
| **W2 — T_db still primary driver** | Storage spawn count vs C-LO (15–17, T_db-only baseline) and pre-calibration C-DS at W_STORAGE_CPU=0.60 (24) | 18 spawns | ✅ Between T_db-only baseline and CPU-dominated 0.60 weight |
| **W3 — Pre→post improvement** | CPU and T_db pre-scale (first 15 rows) vs post-scale (last 15 rows) of `storage_storm` | CPU: 37.4→15.6% (−21.8pp), T_db: 939→0.1ms (−939ms) | ✅ Real relief in both dimensions |

> **Note on measurement windows**: The plan §8.4 specified 120s (W1) and 60s (W3)
> windows aligned with phase boundaries. The per_node_stats.csv rows are
> ~10s apart but spread across both LANs and multiple node types, producing
> more rows than wall-clock seconds. The analysis used all available
> storage_storm rows (W1, 54 rows ≈ 270s per LAN equivalent) and first/last
> 15 rows (W3, ≈ 75s equivalent). These windows are broader than the plan
> specification but capture the same pre→post trajectory. The 9-run evaluation
> will use phase-aligned windows per the plan.

### 6.3 Storage Pre→Post (Both Signals)

From `per_node_stats.csv` of C-W20, `storage_storm` phase (first 15 vs last 15 rows):

| Metric | Pre-scale | Post-scale | Change |
|---|---|---|---|
| **Storage CPU** | 37.4% | 15.6% | −21.8pp |
| **T_db** | 939ms | 0.1ms | −939ms |

Both signals improve post-scale. Storage CPU at 0.08 CPUs is not pure
I/O-wait noise — it carries a real signal that correlates with storage load.
The 0.20 weight captures this real signal as a minority contributor while
T_db (weight 0.80) remains the primary driver.

> **Note on C4 comparison**: At C4 resources (0.04 CPUs, WAN=260ms), storage
> CPU reached 55–76% during storage_storm (v4 calibration_results.md §4).
> At G0-v6 (0.08 CPUs, WAN=185ms), storage CPU is lower (37%) because the
> looser CPU limit reduces saturation. The G0-v6 pre→post drop of −21.8pp
> is the relevant evidence for this calibration — the C4 data is provided
> as context for the resource sensitivity of storage CPU, not as a direct
> comparison.

### 6.4 Final Storage Weights

| Mode | W_STORAGE_CPU | W_T_DB | Rationale |
|---|---|---|---|
| **degradation_score** | **0.20** | **0.80** | CPU adds real secondary signal; T_db dominates |
| cpu_only | 1.00 | 0.00 | Extreme — CPU alone (tests the upper bound) |
| latency_only | 0.00 | 1.00 | Genuine latency-only baseline (15–17 spawns) |

---

## 7. Final Configuration Summary

| Parameter | degradation_score | cpu_only | latency_only |
|---|---|---|---|
| Compute: W_CPU / W_T_PROC | 0.40 / 0.60 | 1.00 / 0.00 | 0.00 / 1.00 |
| Storage: W_STORAGE_CPU / W_T_DB | **0.20 / 0.80** | 1.00 / 0.00 | 0.00 / 1.00 |
| All other parameters | Identical across modes (G0-v6 thresholds) |

**Expected thesis narrative**:
- **Compute**: Three-way divergence — trigger composition matters where both signals are meaningful
- **Storage**: cpu_only (22–24, CPU-driven) vs degradation_score post-calibration (18, T_db-driven with CPU secondary) vs latency_only (15–17, T_db-only). Partial separation — CPU carries a real but weak signal at 0.08 CPUs; T_db is the primary storage scaling signal. The calibration reduced degradation_score from 0.60 (24 spawns, CPU-dominated) to 0.20 (18 spawns, T_db-dominated with CPU secondary), creating meaningful separation from both cpu_only and latency_only. This bounds the trigger composition space: only the compute tier has two independently meaningful signals at this resource level.
