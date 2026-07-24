# RQ3 v2 — Trigger Divergence Calibration Results

**Date**: 2026-07-24 · **Status**: ✅ Main calibration complete (6/6 runs) · **Storage weight probe**: ⏳ Pending (§8 of plan)

---

## 1. Decision

**✅ GO — Proceed to 9-run RQ3 evaluation.** The G0-v6 thresholds produce clear three-way behavioural divergence between the three trigger modes. Storage CPU weight to be finalised by probe (§8).

---

## 2. Run Summary

| # | Label | Mode | Events | Node Timings | Policy-State Rows | Storage Spawns | Compute Spawns | Reserve Spawns |
|---|-------|------|:------:|:------------:|:-----------------:|:--------------:|:--------------:|:--------------:|
| C-DS1 | `20260724_012335_rq3_cal_ds_1` | degradation_score | 120 | 84 | 314 (157+157) | 24 | 7 | 26 |
| C-DS2 | `20260724_021026_rq3_cal_ds_2` | degradation_score | 122 | 88 | 319 (159+160) | 24 | 8 | 26 |
| C-CO1 | `20260724_025622_rq3_cal_cpu_1` | cpu_only | 163 | 103 | 316 (158+158) | 22 | 19 | 26 |
| C-CO2 | `20260724_034309_rq3_cal_cpu_2` | cpu_only | 171 | 109 | 314 (157+157) | 24 | 13 | 27 |
| C-LO1 | `20260724_042902_rq3_cal_lat_1` | latency_only | 61 | 49 | 315 (158+157) | 15 | 3 | 15 |
| C-LO2 | `20260724_051257_rq3_cal_lat_2` | latency_only | 68 | 54 | 312 (156+156) | 17 | 3 | 17 |

**Within-mode consistency**:
- degradation_score: 120–122 events (2% spread) ✅
- cpu_only: 163–171 events (5% spread) ✅
- latency_only: 61–68 events (11% spread) ✅

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

All three modes detected storage stress. cpu_only (22–24) and
degradation_score (24) produce similar storage spawn counts — the CPU
component at weight 0.60–1.00 dominates the storage score. latency_only
(15–17) is distinct. The storage CPU weight probe (§8 of plan) will
determine whether a lower weight produces meaningful separation.

### D3 — Score Component Divergence ✅

`compute_spike` phase, LAN1 mean scores:

| Mode | Rep 1 | Rep 2 | Mean |
|---|---|---|---|
| degradation_score | 0.293 | 0.297 | **0.295** |
| cpu_only | 0.438 | 0.469 | **0.454** |
| latency_only | 0.024 | 0.108 | **0.066** |

Clear three-way separation:
- **cpu_only**: Highest scores — CPU component dominates, crosses threshold most aggressively
- **degradation_score**: Middle scores — both components contribute but dilute each other (0.40 × CPU + 0.60 × T_proc)
- **latency_only**: Lowest scores — T_proc rarely crosses floor=25ms, keeping scores near zero except during peak stress

The score magnitudes directly reflect the weight composition. This is the strongest divergence signal.

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

## 5. Compute Pre→Post Improvement (G0-v6 Confirmed)

From per_node_stats.csv of C-DS1 (degradation_score, compute_spike):

| LAN | Pre-scale CPU | Post-scale CPU | Drop |
|---|---|---|---|
| lan1 | 46% | 23% | −23pp |
| lan2 | 50% | 22% | −28pp |

The ≥15pp improvement criterion from G0-v6 results_v4.md §8.4 is met on
both LANs. Scaling produces real compute relief.

---

## 6. Storage CPU Weight Probe — Pending

The degradation_score storage weight at 0.60 produces spawn counts identical
to cpu_only (24 vs 22–24), confirming the CPU component dominates. The probe
(§8 of calibration plan) will test W_STORAGE_CPU values of 0.10, 0.20, 0.30
to find a weight where:

1. CPU contributes measurably during storage_storm (W1)
2. T_db remains the primary driver (W2 — spawn count between C-LO's 15–17
   and C-DS's 24)
3. CPU-triggered spawns produce real T_db improvement (W3 — pre→post T_db
   drop)

If W3 fails at all weights, storage is latency-only by necessity — a valid
thesis finding that bounds trigger composition to compute-only for the
storage tier.
