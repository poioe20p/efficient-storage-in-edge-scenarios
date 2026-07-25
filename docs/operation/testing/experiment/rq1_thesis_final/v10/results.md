# RQ1 v10 — Results

**Experiment**: [experiment_plan_v10.md](./experiment_plan_v10.md)  
**Date**: 2026-07-25  
**Status**: ❌ Gate failed — campaign stopped after P1–T3

## Run Timeline

| Run | Date | Status | Cumulative Analysis | Conclusions | Changes Made | Expectations for This Run |
|-----|------|--------|---------------------|-------------|--------------|--------------------------|
| v1 (P1–T3) | `2026-07-25` | ❌ | — (initial) | C2 pilot did not replicate; EDGE_CPUS=0.15 too aggressive | — (baseline, from C2 winner) | Push ≥85K, P30 ≤65K, Push TO≤3%, P30 TO≥4% |

---

### 1. Run v1 — P1–T3 (`2026-07-25`)

**Status**: ❌ — Gate failed on throughput AND timeout separation

#### Hypothesis (from plan)

> At EDGE_CPUS=0.15, Push completes ≥85K requests with ≤3% timeout; Poll-30s completes ≤65K with ≥4% timeout. No overlap. Full dose-response curve is monotonic.

#### Run Configuration

| Parameter | Value |
|-----------|-------|
| `EDGE_CPUS` | 0.15 (C2 winner from v9_calibration) |
| `CLIENTS` | 96 |
| `WAN_RTT_MS` | 185 |
| `STORAGE_CPUS` | 0.08 |
| `CURL_MAX_TIME` | 30 |
| Phases | 9-phase cleanup-gap (`phases.json`) |
| Controller env | `current_state_integrated.env` |

#### Results — Run-Level Summary

| Run | Requests | Timeout% | p50 (ms) | p95 (s) | p99 (s) | Spawns |
|-----|----------|----------|----------|---------|---------|--------|
| P1 (Push) | 74,178 | 3.3% | 28.7 | 12.8 | 30.0 | 38 |
| P2 (Push) | 67,349 | 4.8% | 43.1 | 15.1 | 30.0 | 37 |
| P3 (Push) | 79,805 | 3.5% | 129.4 | 12.6 | 30.0 | 40 |
| **Push μ** | **73,777** | **3.9%** | **67.1** | **13.5** | **30.0** | **38.3** |
| T1 (P30) | 61,804 | 3.3% | 58.5 | 17.8 | 30.0 | 34 |
| T2 (P30) | 64,079 | 4.7% | 16.5 | 17.6 | 30.0 | 36 |
| T3 (P30) | 65,658 | 2.9% | 83.2 | 16.4 | 30.0 | 35 |
| **P30 μ** | **63,847** | **3.6%** | **52.7** | **17.3** | **30.0** | **35.0** |

#### Gate Assessment

| Gate | Condition | Actual | Result |
|------|-----------|--------|--------|
| Throughput separation | Push ≥85K, P30 ≤65K | Push **73.8K**, P30 63.8K | ❌ Push 11.2K below threshold |
| Timeout separation | Push ≤3%, P30 ≥4% | Push **3.9%**, P30 **3.6%** | ❌ Direction inverted (P30 better) |
| No overlap | Push min > P30 max | Push min=67.3K, P30 max=65.7K | ⚠️ Barely (1.6K margin) |

#### Per-Phase Stress Comparison

| Phase | Push r/s | P30 r/s | Δ Thr. | Push TO% | P30 TO% | Push p50 | P30 p50 |
|-------|----------|---------|--------|----------|---------|----------|---------|
| `storage_storm` | 55.1 | 52.1 | −5.6% | 4.6% | **7.7%** | 7.9ms | 9.5ms |
| `tier1_hotspot` | 63.7 | 53.9 | −15.3% | **8.7%** | 5.5% | 8.5ms | 10.8ms |
| `reverse_hotspot` | 82.7 | 64.5 | −22.0% | **5.7%** | 3.6% | 7.9ms | 9.3ms |
| `compute_spike` | 119.1 | 94.2 | −20.9% | 1.6% | 2.1% | 955ms | 1215ms |

#### Why The C2 Pilot Didn't Replicate

| Metric | C2 Pilot Push | V10 Push μ | C2 Pilot P30 | V10 P30 μ |
|--------|:------------:|:----------:|:------------:|:---------:|
| Requests | **89,028** | 73,777 | 62,299 | 63,847 |
| Timeout | **2.0%** | 3.9% | 4.5% | 3.6% |
| p50 | **8.4ms** | 67.1ms | 43.6ms | 52.7ms |
| p95 | **9.2s** | 13.5s | 18.1s | 17.3s |

1. **Push degraded more than P30 improved.** C2 Push (89K) → v10 Push (74K, −17%). C2 P30 (62K) → v10 P30 (64K, flat). The system became uniformly more constrained, hitting Push harder.
2. **Timeout signal inverted.** C2: P30 2.3× worse. V10: P30 slightly better (−0.3pp). The strongest C2 signal vanished.
3. **The C2 pilot was n=1.** V10 n=3 reveals Push σ≈6K. C2's 89K Push is 2.5σ above the v10 mean — likely a lucky outlier.

#### Root Cause

At `EDGE_CPUS=0.15`, the static edge nodes saturate almost immediately under stress load. Push's ~14s detection advantage only matters when the system can absorb 14s of overload. At 0.15 CPUs, the damage is done before Push provisions — both modes fail similarly. Spawn counts converge (35–40 for both modes), confirming the elasticity mechanism triggers identically regardless of telemetry cadence.

#### Conclusions

1. **EDGE_CPUS=0.15 is past the fragility threshold for mode differentiation.** At this constraint level, the capacity floor is below what either mode can recover from within its detection window. The coordination gap exists (throughput still shows −15-22%) but doesn't cascade into timeout separation.
2. **Single-pilot calibration is unreliable.** C2's n=1 results were not representative of the n=3 distribution. Multi-replicate screening is necessary even for calibration.
3. **The dose-response curve is partially visible.** The throughput gradient (−5.6% → −22%) and p50 gradient confirm the mechanism works directionally, just not at a magnitude that produces clean endpoint separation.

#### Next Step

Return to v9_calibration matrix. Test **C1 (EDGE_CPUS=0.20)** at n=3 — the higher CPU headroom should restore Push's provisioning advantage window while still being constrained enough to produce a Poll-30s penalty. C1's pilot was also n=1 and may have been a false negative, mirroring C2's false positive.
