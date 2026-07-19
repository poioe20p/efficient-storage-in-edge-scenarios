# Results — RQ3 Golden-Config Baseline (G0) — v1

**Date**: 2026-07-18 · **Experiment Plan**: [experiment_plan.md](./experiment_plan.md) · **Preparation**: [rq3_preparation.md](./rq3_preparation.md)

> **v2 results**: See [results_v2.md](./results_v2.md) for the tightened config (185ms/0.08/0.25, mean-only signals).

---

## Run Timeline

| Run | Date | Status | Key Finding |
|-----|------|--------|-------------|
| v1 G0-ON (`20260718_120847_rq3_g0_on`) | 2026-07-18 12:08 | ⚠️ | CPU drops marginal (−12.6pp/−12.3pp). WAN=260ms causes I/O-wait. p95 timeout-censored. compute_spike at 2 r/s too aggressive. |
| v1 G0-OFF (`20260718_125214_rq3_g0_off`) | 2026-07-18 12:52 | ⚠️ | Single-node saturation confirmed. OFF run dropped for v2 — within-phase pre/post replaces cross-run comparison. |
| **v2 G0** (`20260718_155421_rq3_g0_v2`) | 2026-07-18 15:54 | ✅ | All issues solved — see [results_v2.md](./results_v2.md). |

---

## 1. Run v1 G0-ON — Elasticity ON

**Status**: ⚠️ — CPU drops marginal, compute_spike latency critical, but system stable

### 1.1 Configuration

| Parameter | Value |
|-----------|-------|
| Elasticity | ON (MAX_DYNAMIC_COMPUTE=6, MAX_DYNAMIC_STORAGE=5) |
| CPU limits | STORAGE=0.10, EDGE=0.30 |
| WAN | 260ms |
| Clients | 48 |
| Seed | 42 |
| VIP_HARD_TIMEOUT | 60s |
| SS_ENABLED | 1 (Tier 1 ON) |
| Env override | `current_state_integrated.env` |
| Trigger mode | degradation_score (W_CPU=0.40/W_T_PROC=0.60, W_STORAGE_CPU=0.60/W_T_DB=0.40) |

### 1.2 Per-Phase Resource Metrics

| Phase | Edge CPU | Storage CPU | T_proc (avg) | T_db (avg) | Servers | Storage Nodes | Reqs/5s |
|-------|----------|-------------|-------------|-----------|---------|---------------|---------|
| baseline | 9.6% | 14.8% | 1.2ms | 1.9ms | 0.9 | 3.6 | 30 |
| storage_storm | 9.9% | **32.6%** | 1.3ms | 411ms | 3.2 | 4.5 | 157 |
| tier1_hotspot | 6.3% | 17.6% | 0.9ms | 2,431ms | 4.0 | 5.5 | 102 |
| inter_hotspot_cooldown | 7.2% | 15.2% | 1.7ms | 7ms | 2.0 | 5.6 | 42 |
| reverse_hotspot | 5.3% | 16.7% | 0.8ms | 5,674ms | 3.7 | 5.9 | 74 |
| compute_spike | **18.5%** | 17.7% | 14.3ms | 5,808ms | 2.6 | 5.8 | 58 |
| demand_drop | 7.2% | 14.5% | 9.6ms | 343ms | 1.8 | 5.8 | 32 |

### 1.3 Per-Phase Latency

| Phase | n | Success | Median | p95 | p99 | Max |
|-------|---|---------|--------|-----|-----|-----|
| baseline | 469 | 99.6% | 6ms | 984ms | 1,153ms | 30,001ms |
| storage_storm | 8,303 | 96.8% | 51ms | 13,102ms | 30,002ms | 30,007ms |
| tier1_hotspot | 4,394 | 95.6% | 1,336ms | 12,849ms | 30,002ms | 30,004ms |
| inter_hotspot_cooldown | 2,018 | 99.5% | 7ms | 1,405ms | 1,506ms | 30,001ms |
| reverse_hotspot | 2,951 | 93.4% | 1,707ms | 30,001ms | 30,002ms | 30,006ms |
| **compute_spike** | **2,415** | **87.9%** | **3,795ms** | **30,001ms** | **30,002ms** | **30,008ms** |
| demand_drop | 1,679 | 97.6% | 6ms | 1,419ms | 1,626ms | 30,002ms |

**compute_spike latency distribution**: 15.6% < 1s, 36.7% 1–5s, 21.4% 5–10s, 15.4% 10–20s, 1.1% 20–30s, **9.9% hit 30s timeout** (sum 100.1% due to rounding).

### 1.4 Elasticity Activity

| Metric | LAN1 | LAN2 | Total |
|--------|------|------|-------|
| Scale-up triggers (controller logs) | 17 | 19 | 36 |
| T_proc_signal mentions in logs | 166 | 164 | 330 |
| Unique dynamic containers | — | — | 37 (21 edge, 12 storage, 4 sel_sync) |
| Container spawn events (added) | — | — | 31 |
| Elasticity events (CSV) | 82 | 84 | 166 |
| Node lifecycle rows | — | — | 93 |
| Policy state rows | 159 | 159 | 318 |

Container events breakdown: 31 added, 13 initial, 19 removed, 25 final. Storage scale-ups fired first (during storage_storm), compute scale-ups followed during compute_spike and tier1_hotspot.

### 1.5 Degradation Score Behavior

| Phase | Compute Score (mean) | Storage Score (mean) | Above Threshold (comp) |
|-------|---------------------|---------------------|----------------------|
| baseline | 0.295 | 0.600 | 14/18 windows |
| storage_storm | 0.354 | 0.659 | 49/53 |
| tier1_hotspot | 0.252 | 0.974 | 27/42 |
| inter_hotspot_cooldown | 0.256 | 0.606 | 42/61 |
| reverse_hotspot | 0.182 | 0.986 | 19/41 |
| compute_spike | 0.390 | 0.981 | 40/42 |
| demand_drop | 0.255 | 0.639 | 36/61 |

**Key observation**: Baseline compute score (0.295) exceeds the 0.20 threshold in 78% of windows. Most baseline compute_score values are exactly 0.400 — the W_CPU=0.40 weight-only floor when T_proc < 15ms. The 0.295 mean is pulled down by zero-request windows at phase transitions. The symmetric signal's effect is inconclusive — the structural floor dominates.

### 1.6 Controller Errors

- LAN1: 24 ERROR lines — all `reconfigure sel_sync_lan1_dyn6 failed`. Transient; non-blocking.
- LAN2: 18 ERROR lines — same pattern.
- No controller crashes. No OOM kills. No tracebacks.

---

## 2. Run v1 G0-OFF — Elasticity OFF

**Status**: ⚠️ — Successfully captured single-node saturation, CPU drops vs G0-ON are marginal

### 2.1 Configuration

| Parameter | Value |
|-----------|-------|
| Elasticity | OFF (MAX_DYNAMIC_COMPUTE=0, MAX_DYNAMIC_STORAGE=0) |
| STORAGE_PERSISTENT_RESERVE_ENABLED | 0 |
| SS_ENABLED | 1 (Tier 1 ON — sel_sync nodes still spawn) |
| All other params | Same as G0-ON (see §1.1) |
| Env override | `rq3_g0_off.env` (one-shot, removed after run) |

### 2.2 Per-Phase Resource Metrics

| Phase | Edge CPU | Storage CPU | T_proc (avg) | T_db (avg) | Servers | Storage Nodes | Reqs/5s |
|-------|----------|-------------|-------------|-----------|---------|---------------|---------|
| baseline | 15.2%¹ | 22.8% | 1.0ms | 2.7ms | 1.0 | 1.0 | 38 |
| storage_storm | 21.7% | **45.2%** | 1.7ms | 2,411ms | 1.0 | 1.1² | 82 |
| tier1_hotspot | 12.0% | 18.5% | 0.9ms | 9,113ms | 1.0 | 1.0 | 42 |
| inter_hotspot_cooldown | 21.6% | 20.3% | 2.3ms | 2.6ms | 1.0 | 1.0 | 36 |
| reverse_hotspot | 14.0% | 20.1% | 0.8ms | 9,697ms | 1.0 | 1.0 | 45 |
| compute_spike | **30.8%** | 36.2% | 15.9ms | 10,726ms | 1.0 | 1.0 | 31 |
| demand_drop | 20.5% | 19.2% | 1.9ms | 2.6ms | 1.0 | 1.0 | 35 |

¹ Excludes one anomalous negative measurement (−19.3% at 12:52:33Z, lan2); valid mean of 11 rows = 15.2%.
² storage_count reaches 2 in some windows due to sel_sync containers. No dynamic edge_storage nodes spawned. ✅ C3 PASSES.

### 2.3 Per-Phase Latency

| Phase | n | Success | Median | p95 | Max |
|-------|---|---------|--------|-----|-----|
| baseline | 469 | 100.0% | 6ms | 1,087ms | 1,639ms |
| storage_storm | 4,129 | 93.2% | 152ms | 30,001ms | 30,009ms |
| tier1_hotspot | 1,724 | 88.9% | 11,356ms | 30,001ms | 30,003ms |
| inter_hotspot_cooldown | 2,165 | 99.7% | 7ms | 1,042ms | 1,471ms |
| reverse_hotspot | 1,762 | 89.0% | 12,204ms | 30,001ms | 30,005ms |
| **compute_spike** | **1,294** | **82.1%** | **13,720ms** | **30,002ms** | **30,006ms** |
| demand_drop | 2,159 | 99.7% | 7ms | 1,077ms | 1,600ms |

### 2.4 Elasticity Verification

| Metric | G0-OFF |
|--------|--------|
| Elasticity events | 12 (6 LAN1 + 6 LAN2) |
| Dynamic edge_server nodes | **0** ✅ |
| Dynamic edge_storage nodes | **0** ✅ |
| sel_sync dynamic containers | 12 (expected — SS_ENABLED=1) |
| Scale-up triggers | 0 (MAX_DYNAMIC=0 prevents all) |
| Controller errors | 42 (all sel_sync reconfigure timeouts; non-blocking) |

### 2.5 Degradation Score Behavior

| Phase | Compute Score (mean) | Storage Score (mean) |
|-------|---------------------|---------------------|
| baseline | 0.367 | 0.600 |
| storage_storm | 0.392 | 0.742 |
| tier1_hotspot | 0.379 | 0.967 |
| inter_hotspot_cooldown | 0.400 | 0.590 |
| reverse_hotspot | 0.396 | 0.975 |
| compute_spike | 0.398 | 0.990 |
| demand_drop | 0.400 | 0.580 |

---

## 3. Cross-Run Comparison: Hypothesis Assessment

### 3.1 H1: Storage CPU drop ≥15pp in storage_storm

| Metric | G0-OFF | G0-ON | Δ |
|--------|--------|-------|---|
| Storage CPU (storage_storm) | 45.2% | 32.6% | **−12.6pp** |

**Verdict**: ❌ NOT MET. Below 15pp but ≥10pp → MARGINAL. WAN=260ms reduces cross-region throughput to MongoDB, decreasing pre-scale CPU pressure.

### 3.2 H2: Compute CPU drop ≥15pp in compute_spike

| Metric | G0-OFF | G0-ON | Δ |
|--------|--------|-------|---|
| Edge CPU (compute_spike) | 30.8% | 18.5% | **−12.3pp** |

**Verdict**: ❌ NOT MET. Below 15pp but ≥10pp → MARGINAL. Edge CPU unexpectedly low at 30.8% despite 96 feed_ranking/s — edge server is I/O-wait-bound on MongoDB responses at WAN=260ms, not CPU-bound. CPU is a weak signal when latency-bound.

### 3.3 H3: Post-scale compute_spike latency likely exceeds 1,500ms

| Metric | Value |
|--------|-------|
| G0-ON compute_spike median latency | **3,795ms** |
| G0-OFF compute_spike median latency | 13,720ms |

**Verdict**: ✅ CONFIRMED. Both ON and OFF show extreme latency. Phase redesign required.

### 3.4 H4: Symmetric signal does not cause false-positive floods

| Metric | G0-ON |
|--------|-------|
| Baseline compute score (mean) | 0.295 (above 0.20 threshold in 78% of windows) |
| Baseline scale-up events | 0 |

**Verdict**: ⚠️ PARTIALLY MET. The symmetric signal produces elevated baseline scores, but cooldown mechanisms prevented false-positive scale-ups during baseline.

### 3.5 Success Criteria Summary

| # | Criterion | Target | Actual | Verdict |
|---|-----------|--------|--------|---------|
| S1 | Storage CPU drop (storage_storm) | ≥15pp | **12.6pp** | ⚠️ Marginal |
| S2 | Compute CPU drop (compute_spike) | ≥15pp | **12.3pp** | ⚠️ Marginal |
| S3 | Post-scale compute_spike median latency | ≤1,500ms | **3,795ms** | ❌ Fail (expected) |
| S4 | G0-OFF stability (success ≥70%) | ≥70% | **82.1–100%** | ✅ Met |
| S5 | G0-ON stability (success ≥85%) | ≥85% | **87.9–99.6%** | ⚠️ Met (marginal in compute_spike) |
| C1 | T_proc_signal in controller logs | Present | 330 mentions | ✅ Met¹ |
| C2 | ≥12 resource_stats rows per phase | ≥12 | 18–61 per phase | ✅ Met |
| C3 | G0-OFF single-node saturation | No dyn nodes | 0 edge/storage dyn | ✅ Met |

¹ Log-derived counts cannot be independently re-verified from CSVs. Controller logs exceed 50MB. See §5.

### 3.6 Calibration Data Quality

| Metric | G0-ON | G0-OFF |
|--------|-------|--------|
| resource_stats rows (total) | 318 | 308 |
| Phases captured | 7/7 | 7/7 + idle |
| Client requests captured | 22,229 | 13,702 |
| Policy state rows | 318 (159+159) | 308 (153+155) |

---

## 4. Decision Tree Outcome (v1)

Per §8.3 of the experiment plan (superseded by v2 — see [results_v2.md](./results_v2.md)):

| Condition | Status |
|-----------|--------|
| S1 AND S2 ≥ 15pp | ❌ Both marginal (12.6pp, 12.3pp) |
| S1 OR S2 < 15pp but ≥ 10pp | ✅ Both fall here |
| S3 ≤ 1,500ms | ❌ 3,795ms (expected failure) |
| S4 + S5 met | ✅ Both met |

**v1 Decision**: ⚠️ MARGINAL — led to v2 reconfiguration with tighter CPUs, reduced WAN, mean-only signals, and compute_spike redesign. v2 resolved all issues (see [results_v2.md](./results_v2.md)).

---

## 5. Validity Threats Realized

| Threat | G0 Outcome |
|--------|-----------|
| **Single seed (42)** | Not yet tested. G3 verification run needed after calibration. |
| **Symmetric signal not calibrated** | Baseline compute_score (0.295) dominated by W_CPU=0.40 floor, not p95 sensitivity. Effect on thresholds inconclusive. |
| **Edge CPU at CLIENTS=48 unmeasured** | Now measured: 30.8% (OFF), 18.5% (ON) in compute_spike. Lower than expected — CPU not the bottleneck. |
| **compute_spike saturation** | Confirmed — both ON (3,795ms) and OFF (13,720ms) show extreme latency. Phase redesign mandatory. |
| **Cross-tier contamination** | I/O-wait dominates: edge server blocked on MongoDB responses, suppressing CPU under load. |
| **Data quality: negative CPU measurement** | G0-OFF resource_stats.csv contains one anomalous row (−19.3% at 12:52:33Z, lan2). Excluded from baseline mean. |
| **Verifiability of log-derived claims** | Controller logs exceed 50MB. Scale-up trigger counts and error counts are analyst-verified but not independently reproducible. |

---

## 6. Raw Data Artifacts

| Artifact | G0-ON | G0-OFF |
|----------|-------|--------|
| Run folder | `20260718_120847_rq3_g0_on/` | `20260718_125214_rq3_g0_off/` |
| client_requests.csv | 22,229 rows | 13,702 rows |
| resource_stats.csv | 318 rows | 308 rows |
| policy_state.csv | 318 rows | 308 rows |
| elasticity_events.csv | 166 events | 12 events |
| container_events.csv | 103 events | 26 events |
| node_lifecycle_timings.csv | 93 rows | 12 rows |
| controller_lan1.log | ✅ | ✅ |
| controller_lan2.log | ✅ | ✅ |
| service_logs/ | ✅ (static + dyn) | ✅ (static only) |

---

## A. Post-Analysis Cleanup

- [x] Cloud VM cleaned after all runs
- [x] One-shot `rq3_g0_off.env` removed
- [x] compute_spike phase redesigned (0.5 r/s, 80/20 mix) — v2
- [x] Thresholds recalibrated (W_CPU=0.60, T_PROC_FLOOR=25, τ=0.18) — v2
- [x] Latency signals changed to mean-only (both tiers) — v2
- [x] v2 analysis complete — [results_v2.md](./results_v2.md)
- [ ] RQ3 9-run trigger composition matrix — **next step**
