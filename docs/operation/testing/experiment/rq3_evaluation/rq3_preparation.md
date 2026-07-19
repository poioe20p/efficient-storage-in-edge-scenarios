# RQ3 Preparation — Configuration, Signals, and Experiment Design

**Date**: 2026-07-18 · **Status**: Draft · **Depends on**: [RQ3 proposal](../../../../research_questions/rq3.md), [C4 calibration results](./calibration_results.md), [v6 mechanism necessity results](../../stability/mechanism_necessity/results_v6.md), [v5 results](../../stability/mechanism_necessity/results_v5.md), [golden config](../../golden_config.md)

---

## 1. Purpose

This document specifies the **concrete configuration, code changes, and experiment design** needed to execute the RQ3 trigger-composition evaluation. It covers:

- Resource configuration (Docker CPU/memory limits)
- Latency signal symmetry fix (code change)
- `compute_spike` phase redesign
- Threshold recalibration approach
- Expected metric ranges
- Experiment matrix with replicates

The conceptual rationale for RQ3 lives in [`rq3.md`](../../../../research_questions/rq3.md). This document is the **operational preparation** — the values, the commands, the expected outcomes.

---

## 2. Resource Configuration

### 2.1 Chosen Config: G0-v2 (Tightened Golden Config)

**Updated 2026-07-18**: G0 v1 at 0.10/0.30 CPUs with WAN=260ms showed marginal CPU drops (−12.6pp/−12.3pp) and I/O-wait dominance. v2 tightens limits and reduces WAN.

| Parameter | v1 | v2 | Rationale |
|-----------|----|----|-----------|
| `STORAGE_CPUS` | 0.10 | **0.08** | Push storage CPU higher in stress; widen ON/OFF gap |
| `EDGE_CPUS` | 0.30 | **0.25** | Push edge CPU higher; reduce I/O-wait fraction |
| `STORAGE_MEMORY` | 512m | 512m | Unchanged |
| `EDGE_MEMORY` | 256m | 256m | Unchanged |
| `WAN_RTT_MS` | 260 | **185** | Reduce I/O-wait dominance; make CPU a meaningful signal |
| `CLIENTS` | 48 | 48 | Unchanged |
| `CONTENT_ITEMS` | 6000 | 6000 | Unchanged |
| `USERS` | 100 | 100 | Unchanged |
| `VIP_HARD_TIMEOUT` | 60 | 60 | Unchanged |

### 2.2 Why Not C4?

C4 (`STORAGE_CPUS=0.04`, `EDGE_CPUS=0.06`) was the RQ3 calibration target. It achieved higher absolute CPU (storage 48–70%, edge 56–67%) but:

- **Baseline instability**: Edge CPU spikes to 72–92% in ~2 of 12 baseline windows. At the golden config, baseline is expected to be lower-variance (edge ~33%, storage ~14–17% with ON) — but this has NOT been verified with per-window data at CLIENTS=48. The G0 run must confirm baseline stability.
- **Cross-tier contamination**: At C4, both tiers are stressed simultaneously — when one tier's stress phase runs, the other tier's metrics also spike. This muddies per-tier trigger evaluation.
- **The golden config already shows a ~20pp drop** for both tiers. The absolute CPU level is secondary — the pre→post improvement is the signal.

### 2.3 Measured CPU Ranges at Golden Config (G0, 2026-07-18)

**Updated 2026-07-18**: G0 calibration runs completed. All values below are measured at CLIENTS=48, WAN=260ms, seed=42.

| Phase | Storage CPU (ON) | Storage CPU (OFF) | Edge CPU (ON) | Edge CPU (OFF) | Key Finding |
|-------|------------------|-------------------|---------------|----------------|-------------|
| `baseline` | 14.8% | 22.4% | 9.6% | 12.3% | Low utilization in all conditions |
| `storage_storm` (stress) | 32.6% | **45.2%** | 9.9% | 21.7% | Storage CPU drop −12.6pp (marginal) |
| `tier1_hotspot` | 17.6% | 18.5% | 6.3% | 12.0% | Tier 1 effectively absorbs cross-region load |
| `inter_hotspot_cooldown` | 15.2% | 20.3% | 7.2% | 21.6% | OFF run maintains elevated baseline |
| `reverse_hotspot` | 16.7% | 20.1% | 5.3% | 14.0% | Similar to tier1_hotspot pattern |
| `compute_spike` (stress) | 17.7% | 36.2% | 18.5% | **30.8%** | Edge CPU drop −12.3pp (marginal) |
| `demand_drop` (cooldown) | 14.5% | 19.2% | 7.2% | 20.5% | OFF run CPU remains elevated post-stress |

**Key findings from G0**:
- **Edge CPU is NOT the bottleneck**: At CLIENTS=48 with 96 feed_ranking/s, G0-OFF edge CPU reaches only 30.8% — far below the predicted 90–100%. The edge server is I/O-wait-bound on MongoDB responses, not CPU-bound. This explains the extreme latency (median 13,720ms OFF, 3,795ms ON) despite low CPU.
- **Storage CPU drop is smaller than v6**: −12.6pp at WAN=260ms vs −19.2pp at WAN=160ms (v6 S2). Higher WAN reduces cross-region request throughput to MongoDB, decreasing pre-scale CPU pressure.
- **CPU is a weak stress signal at 0.10/0.30 limits**: The containers are so CPU-constrained that they become I/O-bound before reaching high CPU utilization. CPU-based degradation scoring may need complementing with latency-only or latency-weighted triggers.
- **Symmetric signal raises baseline scores**: G0-ON baseline compute_score = 0.295 (above 0.20 threshold in 78% of windows) vs expected ~0.20 with old avg-only signal. Threshold recalibration needed.

### 2.4 Launch Command (G0-v2)

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=rq3_g0_v2 \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=185 CLIENTS=48 CONTENT_ITEMS=6000 USERS=100 \
  STORAGE_CPUS=0.08 EDGE_CPUS=0.25 \
  STORAGE_MEMORY=512m EDGE_MEMORY=256m \
  RANDOM_SEED=42 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

---

## 3. Latency Signal: Mean-Only (G0-v2 Decision)

### 3.1 Rationale

G0 v1 used `max(avg, p95)` for both tiers (the "symmetric signal"). Analysis revealed this is counterproductive: when a significant fraction of requests hit the 30s client timeout, p95 measures the timeout ceiling (30,001ms), not the system's actual performance. The p95 value is timeout-censored and misleading as a trigger input.

**G0-v2 decision**: Both tiers use **mean-only** latency signals. This is consistent with the autoscaling literature — all 16 reviewed papers use mean (or rate/ratio) for triggering, never percentiles. p95 remains collected in telemetry for SLO monitoring but is excluded from the degradation score.

### 3.2 Signal Specification

| Tier | Signal | Source |
|------|--------|--------|
| **Compute** | `ds.avg_time_proc_ms` | `scaling_policy.py:compute_latency_signal()` |
| **Storage** | `ds.avg_time_db_ms` | `scaling_policy.py:storage_latency_signal()` |

### 3.3 Implementation

A one-line change in `scaling_policy.py` for each method:

```python
@staticmethod
def compute_latency_signal(ds: DomainSummary) -> float:
    return ds.avg_time_proc_ms

@staticmethod
def storage_latency_signal(ds: DomainSummary) -> float:
    return ds.avg_time_db_ms
```

The p95 computation in `aggregator.py` and `models.py` is **preserved** — p95 remains available for monitoring and analysis, just not for trigger decisions.

```python
# Existing (line ~413):
p95_time_db     = _p95(time_dbs_all)

# Add:
p95_time_proc   = _p95(time_procs_all)
```

Include in the `domain_summary` dict:

```python
"p95_time_proc_ms":        p95_time_proc,
```

Also add to the `else` branch (line ~429):

```python
p95_time_proc = 0.0
```

#### B. `source/sdn_controller/telemetry/models.py`

Add field to `DomainSummary`:

```python
p95_time_proc_ms: float = 0.0
```

#### C. `source/sdn_controller/scaling_policy.py`

Both methods changed to mean-only:

```python
@staticmethod
def compute_latency_signal(ds: DomainSummary) -> float:
    """Mean proc latency — avoids timeout-censored p95 contamination."""
    return ds.avg_time_proc_ms

@staticmethod
def storage_latency_signal(ds: DomainSummary) -> float:
    """Mean DB latency — avoids timeout-censored p95 contamination."""
    return ds.avg_time_db_ms
```

### 3.4 Rationale for Mean-Only

- **Timeout censorship**: G0 v1 showed p95_time_db = 30,001ms because ≥10% of requests hit the 30s client timeout. p95 measures the timeout, not the system.
- **Literature standard**: All 16 autoscaling papers reviewed use mean, rate, or ratio for triggers — never percentiles. Percentiles are for SLO monitoring, not triggering.
- **p95 preserved for monitoring**: The aggregator and models still compute p95_time_proc and p95_time_db. They're available for analysis but excluded from degradation scores.

---

## 4. `compute_spike` Phase Redesign

### 4.1 Problem

At the current `compute_spike` phase (`2 r/s`, 100% `feed_ranking`):

- **v5 Run D** (elasticity OFF, CLIENTS=8, 16 feed_ranking/s): single edge server CPU = 50.7%, median latency = 8,505ms (fully saturated).
- **v5 Run A** (elasticity ON, CLIENTS=8, 16 feed_ranking/s): 1–4 edge servers, per-server load ~4–16 req/s, median latency = 2,443ms — even WITH 4 servers, latency exceeds 1,500ms.
- **At CLIENTS=48** (96 feed_ranking/s): single-server saturation would be essentially total — well above 50.7% CPU, likely 90–100%. Even with 4 servers (24 req/s each), per-server load is 1.5× v5 Run A's per-server peak, so latency would exceed 2,443ms.

The phase saturates the system beyond what scaling can fix at 48 clients. Feed_ranking is inherently CPU-intensive; adding more edge servers distributes load but cannot bring per-request latency under 500ms at these volumes.

### 4.2 Design Goal

- Pre-scale: single edge server CPU reaches ~50% — enough to trigger scale-up
- Post-scale: with 3–4 edge servers, latency drops under **1,500ms** (ideally under 500ms)
- The phase must still be recognizably "compute-heavy" to distinguish it from the storage-heavy phases

### 4.3 Proposed Changes to `phases.json`

**⚠️ v5 data shows that 16 feed_ranking/s on a single 0.30-CPU server already reaches 50.7% CPU (Run D). 36 feed_ranking/s would saturate the server completely (estimated 90–100% CPU), not the claimed 45–55%. The redesign must use a lower rate.**

| Parameter | Current | Proposed | Rationale |
|-----------|---------|-----------|-----------|
| `rate_per_client` | `2.0` | **`0.5`** | 24 req/s total. v5 shows 16 feed_ranking/s = 50.7% CPU on 1 server; 24/s should push to ~60–75% — enough to trigger. |
| `cross_region_ratio` | `0.0` | `0.0` | Unchanged — compute spike is local |
| `mix.feed_ranking` | `1.0` | **`0.80`** | Still compute-dominant (19 feed_ranking/s), but 20% lighter endpoints prevent total saturation |
| `mix.content_lookup` | — | **`0.20`** | Lightweight local reads |

Expected load: 48 clients × 0.5 r/s × 0.80 = 19 feed_ranking/s. Single edge server at 0.30 CPUs: estimated CPU ~55–75% (v5 baseline: 16/s → 50.7%). With 3–4 servers post-scale: 5–6 feed_ranking/s each — similar to v5 Run A's per-server load (~4 req/s), where latency was 2,443ms. Post-scale latency target of ≤1,500ms is plausible but not guaranteed — v5 Run A at 4 req/s/server still exceeded 1,500ms. If post-scale latency remains above 1,500ms, reduce rate further to 0.3 r/s.

**Trade-off note**: Adding `content_lookup` to the mix changes the phase from "pure compute saturation" to "compute-dominant mixed workload." The latency signal now includes DB time from `content_lookup` requests that didn't exist before. This weakens experimental control — you can no longer say "this phase stresses only CPU." However, for RQ3's trigger-composition question, this is acceptable: the three modes will all experience the same mixed workload, so the comparison remains fair.

### 4.4 Alternative: Keep 2 r/s, Lower FEED_INTEGRITY_WORK_FACTOR

Instead of reducing the rate, make each feed_ranking request lighter by reducing `FEED_INTEGRITY_WORK_FACTOR` from its current value (200 in calibration). This preserves the request volume while reducing per-request CPU cost.

**Trade-off**: Changing `FEED_INTEGRITY_WORK_FACTOR` changes the nature of the compute work — it's no longer the same "heavy" feed_ranking. The rate reduction is more honest: same work, less of it.

**Recommendation**: Reduce rate (Option 4.3). Keep `FEED_INTEGRITY_WORK_FACTOR` at its default.

---

## 5. Threshold Calibration Approach

### 5.1 Why Recalibrate?

The C3b calibration thresholds were tuned for C4 resources:

| Parameter | C3b Value | Why It Worked at C4 | Problem at Golden Config |
|-----------|-----------|---------------------|--------------------------|
| `SCALEUP_CPU_FLOOR` | 70 | Baseline edge CPU spiked to 72–84% | Golden baseline edge CPU is ~33% — floor=70 makes CPU component always 0 |
| `SCALEUP_CPU_SPAN` | 20 | Stress edge CPU 68–84% | Golden stress edge CPU is ~51% — span=20 gives sat((51−70)/20) = 0.0 |
| `SCALEUP_T_PROC_FLOOR` | 80 | Baseline T_proc spikes to 100–255ms | Golden baseline T_proc is lower — need to measure |
| `SCALEUP_STORAGE_CPU_FLOOR` | 40 | Baseline storage CPU 40–49% | Golden baseline storage CPU is ~14–17% (ON) — floor=40 makes component always 0 |
| `SCALEUP_STORAGE_CPU_SPAN` | 25 | Stress storage CPU 55–76% | Golden stress storage CPU is ~46% (OFF) — narrower range |

**The C3b calibration is invalid for the golden config.** New calibration is required.

### 5.2 Calibration Strategy

**Prerequisite**: The symmetric signal code change (§3) must be deployed BEFORE calibration. The G0 run must use the new `max(avg, p95)` signal for compute.

The calibration needs BOTH ON-run and OFF-run data:
- **ON-run baseline**: to set floors just above normal operation (so non-stress phases produce score ≈ 0)
- **OFF-run stress**: to set spans so stress-phase metrics produce score ≥ threshold (typically 0.50–0.70)

The approach:

1. **G0-ON**: Measure baseline + stress metrics with elasticity ON (1 run)
2. **G0-OFF**: Measure stress metrics with elasticity OFF (1 run) — reveals true pre-scale saturation levels
3. **Set floors** just above G0-ON baseline values — so non-stress phases produce score ≈ 0
4. **Set spans** so G0-OFF stress values produce score ≥ 0.50 — enough to cross threshold
5. **Tune base thresholds** so score crosses during stress, not during baseline/cooldown
6. **Determine REQUIRED window counts** during calibration — do NOT assume C3b values (3-of-5 storage, 2-of-5 compute). At golden config with lower baseline variance, `REQUIRED=2` (the default) may be sufficient. Calibration will reveal whether single-window spikes occur.

Preliminary floor/span estimates (to be confirmed by G0 measurement):

| Parameter | Expected Range | Basis |
|-----------|---------------|-------|
| `SCALEUP_CPU_FLOOR` | 35–45 | Baseline edge CPU ~33%, set floor just above |
| `SCALEUP_CPU_SPAN` | 15–25 | Stress edge CPU ~51%, span gives partial-to-full saturation |
| `SCALEUP_T_PROC_FLOOR` | 50–100 | Baseline T_proc to be measured; set above baseline avg |
| `SCALEUP_T_PROC_SPAN` | 80–150 | Stress T_proc to be measured |
| `SCALEUP_STORAGE_CPU_FLOOR` | 18–25 | Baseline storage CPU ~14–17% (ON), set above |
| `SCALEUP_STORAGE_CPU_SPAN` | 15–25 | Stress storage CPU ~46% (OFF) |
| `SCALEUP_T_DB_FLOOR` | 100–200 | Baseline T_db to be measured |
| `SCALEUP_T_DB_SPAN` | 200–300 | Stress T_db to be measured |

### 5.3 Calibration Runs

| Run | Elasticity | Purpose | Expected Duration |
|-----|-----------|---------|-------------------|
| **G0-ON** | ON | Measure baseline + post-scale metrics at golden config | 1 full workload |
| **G0-OFF** | OFF (`MAX_DYNAMIC_STORAGE=0`, `MAX_DYNAMIC_COMPUTE=0`) | Measure true pre-scale saturation levels | 1 full workload |
| **G1** | ON | Initial calibration with estimated floors/thresholds from G0 data | 1 full workload |
| **G2** | ON | Refinement if G1 has false positives or missed triggers | 1 full workload |
| **G3** | ON | Verification with different seed | 1 full workload |

Estimated: 3–5 runs to converge. The OFF run (G0-OFF) is essential — without it, stress-phase spans cannot be calibrated.

---

## 6. Expected Metrics

### 6.1 CPU Ranges

See §2.3. Key stress-phase pre-scale values:

| Tier | Stress Phase | Pre-scale CPU (OFF) | Post-scale CPU (ON) | Expected Drop |
|------|-------------|--------------------|--------------------|---------------|
| Storage | `storage_storm` | ~46% | ~27% | **−19pp** |
| Compute | `compute_spike` | ~51% | ~29% | **−22pp** |

### 6.2 Latency Ranges (End-to-End, Median)

**⚠️ For RQ3, Tier 1 is always ON (`SS_ENABLED=1`). Tier 1 OFF latencies are shown for context only — they are NOT measured in the RQ3 experiment.**

Framed as: *"The system delivers sub-50ms latency for local requests and reduces cross-region latency by 39% via Tier 1 selective sync."*

| Phase | Cross-Region | Expected Median (Tier 1 ON) | Notes |
|-------|-------------|---------------------------|-------|
| `baseline` | 0% | **20–50ms** | Local, low latency. v5: 24ms, v6 T9: 19ms. |
| `storage_storm` | 90% | **60–100ms** | v6 T9: 67ms. Tier 1 cache handles most cross-region reads. Without Tier 1: unknown — v6 T10 median was 50ms but with 22.3% failure rate (censored; slow requests killed by timeout). |
| `tier1_hotspot` | 95% | **3,500–4,000ms** | v6 T9: 3,633ms. WAN RTT at 260ms dominates. Without Tier 1: 5,922ms (T10). The 39% reduction is the Tier 1 benefit. |
| `inter_hotspot_cooldown` | 0% | **20–50ms** | Local, low latency. v6 T9: 27ms. |
| `compute_spike` | 0% | **Unknown at CLIENTS=48** | v6 T9: 3,392ms at 2 r/s pure feed_ranking — but this is pre-redesign. After §4.3 redesign (0.5 r/s, mixed): expected 500–1,500ms post-scale. Must be verified in G0. |
| `cooldown` | 0% | **20–50ms** | Local, low latency. v6 T9: 27ms. |

### 6.3 Internal Latency Signals (what the controller measures)

| Tier | Non-Stress (baseline) | Stress | Signal Definition |
|------|----------------------|--------|-------------------|
| **Compute** (T_proc) | avg ~50–100ms, p95 ~100–200ms | avg ~150–300ms, p95 ~300–500ms | `max(avg_time_proc_ms, p95_time_proc_ms)` |
| **Storage** (T_db) | avg ~100–300ms, p95 ~200–800ms | avg ~500–2,000ms, p95 ~2,000–5,000ms | `max(avg_time_db_ms, p95_time_db_ms)` |

> These are preliminary estimates. Actual values will be measured during G0 calibration.

---

## 7. Experiment Matrix

**⚠️ BLOCKED on calibration (§5).** The experiment matrix cannot proceed until:
1. The symmetric signal code change (§3) is deployed
2. The G0-ON and G0-OFF calibration runs are complete
3. Floors, spans, thresholds, and REQUIRED counts are determined for the golden config
4. The `compute_spike` phase redesign (§4.3) is validated in G0
5. The three env override files are created with concrete values

The matrix below is the TARGET design. Actual values (thresholds, seeds, labels) will be filled in after calibration.

### 7.1 RQ3 Trigger Modes

Three modes, identical parameters except weights:

| Mode | `W_CPU` / `W_T_PROC` | `W_STORAGE_CPU` / `W_T_DB` | Env Override File |
|------|----------------------|---------------------------|-------------------|
| **degradation_score** | 0.40 / 0.60 | 0.60 / 0.40 | `rq3_golden_composite.env` |
| **cpu_only** | 1.00 / 0.00 | 1.00 / 0.00 | `rq3_golden_cpu_only.env` |
| **latency_only** | 0.00 / 1.00 | 0.00 / 1.00 | `rq3_golden_latency_only.env` |

All other parameters (floors, spans, thresholds, cooldowns, REQUIRED counts) are **identical** across modes — only the weights change. These parameters will be determined during calibration (§5) and written into three env override files that differ ONLY in the weight variables.

### 7.2 Run Matrix

**3 modes × 3 replicates = 9 runs**, all at golden config. Seeds TBD after calibration — use the same 3 seeds across all modes for comparability.

| Run | Mode | Seed | Label |
|-----|------|------|-------|
| R1 | degradation_score | 42 | `rq3_golden_comp_r1` |
| R2 | degradation_score | 99 | `rq3_golden_comp_r2` |
| R3 | degradation_score | 17 | `rq3_golden_comp_r3` |
| R4 | cpu_only | 42 | `rq3_golden_cpu_r1` |
| R5 | cpu_only | 99 | `rq3_golden_cpu_r2` |
| R6 | cpu_only | 17 | `rq3_golden_cpu_r3` |
| R7 | latency_only | 42 | `rq3_golden_lat_r1` |
| R8 | latency_only | 99 | `rq3_golden_lat_r2` |
| R9 | latency_only | 17 | `rq3_golden_lat_r3` |

**Why 3 replicates**: v5/v6 were single-replicate experiments. Single-replicate noise makes it impossible to distinguish a 3–4% difference from random variance. Three replicates per mode give a distribution, not a point estimate.

### 7.3 Prerequisite Verification

The G0-OFF and G0-ON calibration runs (§5.3) serve double duty as the scaling prerequisite verification:

| Run | Elasticity | Tier 1 | Purpose |
|-----|-----------|--------|---------|
| G0-OFF | OFF (`MAX_DYNAMIC_STORAGE=0`, `MAX_DYNAMIC_COMPUTE=0`) | **ON** (`SS_ENABLED=1`) | Measure pre-scale CPU peak. Tier 1 kept ON because it's always ON in RQ3 — the prerequisite should match experimental conditions. |
| G0-ON | ON | ON | Measure post-scale CPU drop. |

If G0-ON − G0-OFF CPU drop ≥ 15pp for both tiers, proceed. If the drop is below 15pp, the golden config at CLIENTS=48 is not constrained enough — consider tightening CPU limits slightly (e.g., STORAGE_CPUS=0.08, EDGE_CPUS=0.25) and re-run G0.

---

## 8. Success Criteria

### 8.1 Scaling Prerequisite (V1/V2)

| # | Metric | Target |
|---|--------|--------|
| 1 | Storage CPU drop (pre-scale − post-scale) | **≥15pp** within `storage_storm` |
| 2 | Compute CPU drop (pre-scale − post-scale) | **≥15pp** within `compute_spike` |
| 3 | Post-scale compute_spike median latency | **≤1,500ms** |
| 4 | System stability | No OOM kills, success ≥85% |

### 8.2 RQ3 Trigger Composition (9-run matrix)

| # | Metric | Target |
|---|--------|--------|
| 5 | Each mode triggers scale-up during its target stress phase | ≥2 of 3 replicates per mode |
| 6 | Baseline false positives | ≤1 per run (score-triggered only; reserve spawns excluded) |
| 7 | Cross-mode comparison | Qualitative: describe differences in trigger timing, sensitivity, and stability — not "which is best" |
| 8 | System stability | No OOM kills, no controller tracebacks |

---

## 9. Latency Framing for Thesis

**Do not claim "low-latency system" without qualification.** For RQ3, Tier 1 is always ON. The relevant latency story:

- **Local requests** (baseline, cooldown, inter_hotspot): 20–50ms median — genuinely low latency
- **Cross-region requests with Tier 1** (storage_storm, tier1_hotspot): 60–4,000ms. Local cache hits are fast (60–100ms in storage_storm); cache misses pay WAN RTT (3,500–4,000ms in tier1_hotspot). This is 39% faster than without Tier 1 — the mechanism works, but cross-region requests are NOT low-latency.
- **Compute-heavy requests** (compute_spike, post-scale): target 500–1,500ms — acceptable but not low. The controller intervenes before full saturation (8,505ms without scaling).

**Recommended framing**: *"The system delivers sub-50ms latency for local requests. For cross-region access, Tier 1 selective sync reduces latency by 39% compared to direct WAN MongoDB reads. The degradation score — which combines CPU and latency signals — detects overload and triggers scale-up before latency exceeds the 1,500ms operational ceiling for compute-bound workloads."*

This is honest: local is fast, cross-region is improved by the mechanism (not solved — physics limits apply), and the controller intervenes before things get too bad for local compute work.

---

## 10. Open Questions

1. **compute_spike rate**: Is 0.5 r/s the right value? If pre-scale CPU at 0.5 r/s is too low to trigger scale-up, increase to 0.7 r/s. If post-scale latency still exceeds 1,500ms, reduce to 0.3 r/s. The G0 run will answer this.

2. **Edge CPU at CLIENTS=48 with elasticity OFF**: All edge CPU estimates for the golden config are extrapolated from v5 CLIENTS=8 data. The actual single-server edge CPU at 48 clients is unknown and must be measured in G0-OFF. This is a critical unknown — if edge CPU at 48 clients is much higher than expected, the compute_spike redesign may need further adjustment.

3. **T_proc p95 at golden config**: What is the actual p95 T_proc during baseline and stress at CLIENTS=48? Needed for floor calibration. The G0 run will measure this. Note: the `p95_time_proc_ms` field does not currently exist in `DomainSummary` — the symmetric signal code change (§3) must be deployed first.

4. **Storage signal at golden config**: With `max(avg, p95)` for T_db, what's the typical signal value during baseline? At C4, p95 dominated. At golden config, average may dominate since there's less pressure on MongoDB.

5. **Tier 1 interaction with latency_only mode**: The latency_only mode uses only T_proc/T_db signals. Since Tier 1 eliminates cross-region DB reads for cached content, it reduces T_db during `tier1_hotspot`. This means latency_only may be less sensitive to cross-region overload than cpu_only or degradation_score. This is an expected characteristic — it's part of the trigger-composition characterization, not a bug.

6. **Should p90 be used instead of p95?** p95 at C4 showed extreme spikes (T_db p95 = 4,908ms in stress, 1,401ms in baseline). p90 would be less volatile while still capturing tail behavior. However, p90 is not currently computed anywhere — switching would require another aggregator change (adding `_p90`). Decision deferred to G0 measurement — if p95 causes excessive noise at golden config, implement p90.

7. **Phases.json edit scope**: Editing `phases.json` for the `compute_spike` redesign changes the canonical workload for ALL experiments, not just RQ3. If other experiment families depend on the current `compute_spike` definition (2 r/s, 100% feed_ranking), they would be affected. Consider whether to use a `phases_override/` file instead. **Decision deferred.**

8. **Env override file strategy**: The canonical-file rules (copilot-instructions.md) specify exactly ONE canonical env override (`current_state_integrated.env`). RQ3 needs three mode-specific overrides that differ only in weights. These should be separate files (not editing the canonical override), but this creates multiple env files. This needs explicit resolution: either the canonical rule is relaxed for RQ3, or a different mechanism (e.g., command-line weight overrides) is used.

---

## 11. Files to Create or Modify

| File | Action | Purpose |
|------|--------|---------|
| `source/docker/local_state_server/aggregator.py` | Edit | Add `p95_time_proc` computation |
| `source/sdn_controller/telemetry/models.py` | Edit | Add `p95_time_proc_ms` to `DomainSummary` |
| `source/sdn_controller/scaling_policy.py` | Edit | Add `compute_latency_signal`, use in compute evaluation |
| `source/scripts/testing/phases.json` | Edit | Redesign `compute_spike` phase |
| `source/scripts/testing/controller_env_overrides/rq3_golden_composite.env` | Create | degradation_score weights at golden config thresholds |
| `source/scripts/testing/controller_env_overrides/rq3_golden_cpu_only.env` | Create | cpu_only weights |
| `source/scripts/testing/controller_env_overrides/rq3_golden_latency_only.env` | Create | latency_only weights |
| `docs/operation/testing/experiment/rq3_evaluation/rq3_preparation.md` | Create | This document |
