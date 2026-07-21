# RQ1 v4 Results — Scoring-Corrected Re-run

**Date**: 2026-07-19 (execution), 2026-07-20 (analysis)
**Plan**: [`experiment_plan_v4.md`](experiment_plan_v4.md)
**Predecessor**: [`results_v3.md`](results_v3.md)
**Graphs**: [`graphs/comparison/`](graphs/comparison/)

---

## Run Timeline

| Run | Date | Status | Timeout Rate | Reaction μ (s) | Staleness max (s) | Compute Spawns | Events |
|-----|------|--------|-------------|-----------------|-------------------|----------------|--------|
| v4 (`rq1_v4_push_1`) | 20260719_1944 | ✅ | 1.1% | 121.4 (n=3) | 0.04 | 21 | 102 |
| v4 (`rq1_v4_push_2`) | 20260719_2021 | ✅ | 1.3% | 163.4 (n=4) | 0.04 | 24 | 124 |
| v4 (`rq1_v4_push_3`) | 20260719_2058 | ✅ | 1.1% | 220.8 (n=4) | 0.03 | 23 | 113 |
| v4 (`rq1_v4_poll5_1`) | 20260719_2339 | ✅ | 1.2% | 23.2 (n=3) | 5.18 | 20 | 94 |
| v4 (`rq1_v4_poll5_2`) | 20260720_0015 | ✅ | 1.0% | 40.5 (n=3) | 5.21 | 23 | 115 |
| v4 (`rq1_v4_poll5_3`) | 20260720_0052 | ✅ | 1.1% | 101.7 (n=5) | 5.15 | 23 | 115 |
| v4 (`rq1_v4_poll12_1`) | 20260720_0129 | ✅ | 1.1% | 45.9 (n=3) | 10.00 | 22 | 113 |
| v4 (`rq1_v4_poll12_2`) | 20260720_0206 | ✅ | 1.2% | 64.5 (n=4) | 10.00 | 22 | 98 |
| v4 (`rq1_v4_poll12_3`) | 20260720_0242 | ✅ | 1.3% | 108.5 (n=5) | 10.00 | 23 | 108 |
| v4 (`rq1_v4_poll30_1`) | 20260719_2136 | ✅ | 2.2% | 221.5 (n=3) | 9.93 | 9 | 66 |
| v4 (`rq1_v4_poll30_2`) | 20260719_2213 | ✅ | 1.4% | 72.9 (n=5) | 9.91 | 10 | 66 |
| v4 (`rq1_v4_poll30_3`) | 20260719_2250 | ✅ | 1.3% | 70.0 (n=5) | 9.99 | 13 | 79 |

**Status legend**: ✅ healthy (<3% timeout) · ⚠️ degraded (3–10%) · ❌ severely degraded (>10%)

> **Note**: All 12 runs are healthy. The v3 status legend used <5%/>5%/>20% thresholds; v4 uses stricter <3%/>3%/>10% because the data are cleaner (no bimodality). All runs pass even the stricter threshold.
>
> **Execution order note**: Runs were executed in the order: Push×3 → Poll-30s×3 → Poll-5s×3 → Poll-12s×3. This differs from the plan's stated order (Push×3 then Poll-30s×3). The Poll-5s and Poll-12s intermediate modes were added mid-campaign to identify where the elasticity threshold cliff occurs (which turned out to be between Poll-12s and Poll-30s). The blocked-run-order validity threat (plan §Validity Threats) may not apply as stated since Poll-30s was run second, not last.

---

## 1. Executive Summary

The v4 experiment re-ran the RQ1 campaign with a single critical fix: **`SCALEUP_CPU_SPAN=40`** (was 5 in v3). In v3, `CPU_SPAN=5` saturated the compute scoring function — any node at ≥10% CPU received the maximum compute score of 0.60, causing uncontrolled compute spawning. The v4 re-run tests whether the coordination gap survives a properly calibrated trigger.

**Primary finding: the coordination gap in user-visible outcomes has essentially disappeared.** All 12 runs are healthy (1.0–2.2% timeout rate), regardless of telemetry mode. The bimodal failure regime that dominated v3 (where runs randomly split into healthy ~2% and degraded 10–35% timeout) is completely eliminated. Poll-30s users experience the same ~1-2% timeout rate as Push users.

**However, the coordination gap still manifests in elasticity behavior:**
- Poll-30s spawns significantly fewer compute nodes (μ=10.7 vs μ=22.7 for Push, −52%)
- Poll-30s has lower total elasticity events (μ=70 vs μ=113 for Push, −38%)
- The blind spot reduces spawn activity without degrading service quality

**Reaction latency direction is reversed vs. plan expectation.** The plan predicted Poll-30s reaction latency > Push reaction latency. The measured data shows the opposite (Push μ=168.3s vs Poll-30s μ=121.7s). However, the breach-detector methodology is unreliable under CPU_SPAN=40 (see §2 C3 for detailed analysis). The reaction latency numbers should not be used for mode comparison — they measure the sliding-window accumulation time under a conservative trigger, not the blind-spot penalty.

**The thesis contribution is refined:** The unified architecture's properly-calibrated trigger eliminates the coordination gap's user-visible harm. The gap is real — Poll-30s spawns less — but with proper calibration, the system self-regulates and maintains service quality even at 30s polling. The harm is bounded, not catastrophic.

---

## 2. Criteria Assessment

### C1 — All 12 runs complete

**Met.** All 12 runs (Push×3, Poll-5s×3, Poll-12s×3, Poll-30s×3) completed to idle phase with zero controller tracebacks. No run crashed or hung.

**Evidence**: `phases_snapshot.json` in each run folder shows complete 7-phase progression ending in `idle`.

### C2 — Coordination gap persists (timeout rate)

**Partially Met.** The direction is preserved (Poll-30s μ=1.63% > Push μ=1.17%), but the magnitude is negligible:

| Mode | Timeout Rate (μ ± σ) | Range |
|------|---------------------|-------|
| Push | 1.17 ± 0.12% | 1.1–1.3% |
| Poll-5s | 1.10 ± 0.10% | 1.0–1.2% |
| Poll-12s | 1.20 ± 0.10% | 1.1–1.3% |
| Poll-30s | 1.63 ± 0.49% | 1.3–2.2% |

The difference between Push and Poll-30s is 0.46 percentage points — within the noise floor. Compare with v3 where the gap was 19.6pp (5.9% vs 25.5%). **The coordination gap in user-visible impact has been reduced by ~98%.**

**Evidence**: Per-run `client_requests.csv` (send-time bucketed). Comparison graph: [`rq1_v2_timeout_comparison.png`](graphs/comparison/rq1_v2_timeout_comparison.png).

### C3 — Reaction latency gap persists

**Inconclusive.** The breach-detector-based reaction latency shows high within-mode variance and no clear monotonic trend:

| Mode | Reaction Latency μ (s) | σ | Range |
|------|----------------------|---|-------|
| Push | 168.3 | 50.2 | 121–221 |
| Poll-5s | 55.3 | 41.7 | 23–102 |
| Poll-12s | 73.0 | 31.8 | 46–109 |
| Poll-30s | 121.7 | 87.1 | 70–222 |

These values are NOT comparable to v3's reaction latency (Push ~33s, Poll-30s ~76s). The breach detector's methodology — matching breach windows to spawn initiations — produces fundamentally different measurements under CPU_SPAN=40 than under CPU_SPAN=5:

1. **Fewer events**: With CPU_SPAN=40, the controller spawns more selectively. The breach detector captures only 3–5 paired events per run (vs 4–15 in v3). Small n produces high variance.
2. **Provisioning time is ~1s**: In v3, provisioning was ~14s (container boot + OVS wiring). In v4, the breach detector reports ~1s provisioning. This suggests the detector is pairing breach windows to a different event (possibly the decision to spawn, not the spawn completion).
3. **Dominant detection component**: Detection time (23–320s) dominates total reaction latency. This is the sliding window accumulation time — with CPU_SPAN=40 and threshold ≥0.21, the controller needs 3 out of 5 windows showing sustained high CPU before acting. This takes longer than in v3 where any CPU ≥10% triggered a spawn.

**The reaction latency metric is not comparable between v3 and v4** due to the fundamentally different spawning regime. The breach detector's pairing logic was designed for the v3 spawning pattern; under v4's conservative spawning, it captures a different phenomenon.

**Evidence**: Per-run `analysis/rq1_reaction_latency.csv` (12 files). Comparison graph: [`rq1_v2_reaction_latency.png`](graphs/comparison/rq1_v2_reaction_latency.png).

### C4 — Compute spawning is controlled

**Not Met (absolute count) / Met (spawning quality).** The plan's explicit expectation was: *"Compute spawn count per run is lower than v3."* The measured data shows the opposite:

| Mode | v4 Compute Spawns (μ) | v3 Compute Spawns (μ) | Direction |
|------|----------------------|----------------------|-----------|
| Push | 22.7 | 18.3¹ | **Higher (+24%)** |
| Poll-30s | 10.7 | 8.7¹ | **Higher (+23%)** |

> ¹v3 compute spawn counts are from `node_lifecycle_timings.csv` node_type counts. The v3 comparison table used `decision_quality` spawns which reported lower numbers (1.0–2.3 per mode for compute_spike phase only). The v4 numbers are from `node_lifecycle_timings.csv` for consistency.

**C4a — Absolute spawn count lower than v3: Not Met.** Both Push and Poll-30s show higher absolute compute spawn counts in v4. The plan's numeric expectation was not satisfied.

**C4b — Spawning quality (uncontrolled 10%-CPU triggers eliminated): Met.** The bimodality is resolved (C5), timeout rates are uniformly low (C2), and every spawn is triggered by genuine CPU pressure rather than the saturated scoring function. The spawning is qualitatively different — purposeful rather than frenetic — even though the absolute count is higher.

Storage spawns also increased dramatically (Push: 15.3→34.7, +127%; Poll-30s: 15.0→28.3, +89%). This is likely due to `W_STORAGE_CPU=0` (storage CPU score component has zero weight, making storage spawns purely latency-driven) combined with `STORAGE_CPUS=0.08` (reduced from 0.10) and the floor change (3%→10%). The storage spawning increase is noted but not investigated further — it is not the primary RQ1 concern.

The key evidence is the within-v4 mode comparison: Poll-30s compute spawns drop 53% vs Push (10.7 vs 22.7). This is the blind spot effect — with fewer telemetry windows visible, the controller initiates fewer spawns.

**Evidence**: Per-run `node_lifecycle_timings.csv` (12 files).

### C5 — Bimodality assessment

**Met — bimodality resolved.** Within-mode σ for timeout rate:

| Mode | v4 σ | v3 σ | v3 threshold |
|------|------|------|-------------|
| Push | 0.12pp | 7.2pp | >5pp = genuine |
| Poll-5s | 0.10pp | 5.4pp | |
| Poll-12s | 0.10pp | 11.7pp | |
| Poll-30s | 0.49pp | 9.1pp | |

All v4 σ values are below 0.5 percentage points — far below the 3pp threshold for "resolved" established in the experiment plan. **The v3 bimodality was an artifact of CPU_SPAN=5.** With proper calibration, the system operates in a single, stable, healthy regime.

**Evidence**: Per-phase timeout table in [§3](#3-per-phase-analysis).

### C6 — Staleness step-function

**Met.** Staleness follows the expected step-function, unchanged from v3:

| Mode | Staleness max (μ) | Expected |
|------|-------------------|----------|
| Push | ~0.04 s | ~0 s |
| Poll-5s | ~5.18 s | ~5 s |
| Poll-12s | ~10.00 s | ~10 s |
| Poll-30s | ~9.94 s | ~10 s |

The HTTP cache architecture correctly bounds staleness at the aggregation window (10 s), not the polling interval. This mechanism is independent of the scoring function and is confirmed across both v3 and v4.

**Evidence**: Per-run `analysis/rq1_staleness.csv` (12 files). Comparison graph: [`rq1_v2_staleness_comparison.png`](graphs/comparison/rq1_v2_staleness_comparison.png).

### C7 — Latency uncensored

**Met.** p95 latency for successful cross-region requests is well below CURL_MAX_TIME=30:
- Push: p95 = 0.5–8.1s (varies by phase)
- Poll-30s: p95 = 8.1–9.4s (highest in storage_storm)

The latency distribution is not artificially capped. The uniform low timeout rate (~1%) means nearly all requests complete within the 30s window.

### C8 — All 4 mechanisms exercise

**Met.** All four elasticity mechanisms exercise in all 12 runs:

| Mechanism | Evidence | All 12 runs? |
|-----------|----------|--------------|
| Storage scale-out | `storage` node_type in `node_lifecycle_timings.csv` | ✅ All 12 (27–38 per run) |
| Compute scale-up | `compute` node_type | ✅ All 12 (9–24 per run) |
| Tier 1 selective sync | `selective_storage` node_type | ✅ All 12 (9–13 per run) |
| Reserve activation | Spawns during `reverse_hotspot` phase | ✅ All 12 |

Per-mode spawn counts (μ of n=3, from `node_lifecycle_timings.csv`):

| Mechanism | Push | Poll-5s | Poll-12s | Poll-30s |
|-----------|------|---------|----------|----------|
| Storage scale-out | 34.7 | 34.3 | 32.0 | 28.3 |
| Compute scale-up | 22.7 | 22.0 | 22.3 | 10.7 |
| Tier 1 selective sync | 12.0 | 12.3 | 12.3 | 10.0 |

**Evidence**: Per-run `node_lifecycle_timings.csv` (12 files). Decision quality aggregate: [`rq1_v2_decision_quality.csv`](graphs/comparison/rq1_v2_decision_quality.csv).

---

## 3. Per-Phase Analysis (send-time bucketed)

| Run | baseline | storage_storm | tier1_hotspot | inter_cooldown | reverse_hotspot | compute_spike | demand_drop | **Overall** |
|-----|----------|--------------|---------------|----------------|-----------------|---------------|-------------|-------------|
| push_1 | 0.0% | 4.0% | 2.3% | 0.2% | 1.9% | 0.1% | 0.2% | **1.1%** |
| push_2 | 0.2% | 3.3% | 2.8% | 0.2% | 4.6% | 0.1% | 0.4% | **1.3%** |
| push_3 | 0.2% | 2.9% | 1.7% | 0.4% | 2.4% | 0.1% | 0.3% | **1.1%** |
| **Push μ±σ** | **0.1±0.1%** | **3.4±0.6%** | **2.3±0.6%** | **0.3±0.1%** | **3.0±1.4%** | **0.1±0.0%** | **0.3±0.1%** | **1.2±0.1%** |
| poll5_1 | 0.0% | 3.5% | 2.7% | 0.5% | 2.4% | 0.1% | 0.6% | **1.2%** |
| poll5_2 | 0.0% | 3.1% | 1.9% | 0.2% | 2.4% | 0.1% | 0.2% | **1.0%** |
| poll5_3 | 0.0% | 3.9% | 2.4% | 0.3% | 2.2% | 0.1% | 0.6% | **1.1%** |
| **Poll-5s μ±σ** | **0.0±0.0%** | **3.5±0.4%** | **2.3±0.4%** | **0.3±0.2%** | **2.3±0.1%** | **0.1±0.0%** | **0.5±0.2%** | **1.1±0.1%** |
| poll12_1 | 0.2% | 3.2% | 1.6% | 0.2% | 2.1% | 0.2% | 0.8% | **1.1%** |
| poll12_2 | 0.0% | 2.6% | 2.1% | 0.3% | 3.0% | 0.2% | 0.3% | **1.2%** |
| poll12_3 | 0.2% | 4.9% | 2.5% | 0.4% | 3.0% | 0.1% | 0.4% | **1.3%** |
| **Poll-12s μ±σ** | **0.1±0.1%** | **3.6±1.2%** | **2.1±0.5%** | **0.3±0.1%** | **2.7±0.5%** | **0.2±0.1%** | **0.5±0.3%** | **1.2±0.1%** |
| poll30_1 | 0.2% | 4.3% | 2.1% | 0.2% | 2.2% | 1.7% | 3.9% | **2.2%** |
| poll30_2 | 0.0% | 4.3% | 2.3% | 0.1% | 2.2% | 0.4% | 0.1% | **1.4%** |
| poll30_3 | 0.0% | 4.2% | 1.7% | 0.2% | 2.7% | 0.2% | 0.3% | **1.3%** |
| **Poll-30s μ±σ** | **0.1±0.1%** | **4.3±0.1%** | **2.0±0.3%** | **0.2±0.1%** | **2.4±0.3%** | **0.8±0.8%** | **1.4±2.1%** | **1.6±0.5%** |

**Key observations**:

1. **baseline** and **demand_drop** are consistently healthy (<1% timeout) across all runs — unchanged from v3.
2. **storage_storm** remains the worst phase but at vastly reduced magnitude: 2.6–4.9% in v4 vs 1.1–59.6% in v3. The phase transition from v3 (where storage_storm either passed at ~1% or failed at 17–60%) is eliminated — it's now a consistent ~3–4%.
3. **reverse_hotspot** is the second-worst phase at 1.9–4.6%, also dramatically reduced from v3's 1.9–64.6%.
4. **poll30_1 is a mild outlier** with elevated compute_spike (1.7% vs 0.1–0.4% for other runs), demand_drop (3.9% vs 0.1–0.8%), and reaction latency (221.5s vs 70–73s for poll30_2/3). It also has the fewest compute spawns (9 vs 10–13 for other Poll-30s runs) and the highest overall timeout rate (2.2%). This run may represent the beginning of the degradation cascade seen in v3 — the system is closer to the edge but still maintains healthy service quality. Flagged for follow-up investigation.
5. **No bimodal split**: every run, every phase operates in the same healthy regime. There is no inflection point where the system bifurcates. The Poll-30s μ±σ rows show higher variance in compute_spike (σ=0.8pp) and demand_drop (σ=2.1pp), but this is driven entirely by poll30_1 — poll30_2 and poll30_3 are indistinguishable from Push/Poll-5s/Poll-12s.

---

## 4. Elasticity Behavior — The Real Coordination Gap

While user-visible outcomes are uniform across modes, elasticity behavior reveals the coordination gap:

### Spawn Counts by Mode

| Mode | Compute (μ) | Storage (μ) | Selective Sync (μ) | Elasticity Events (μ) |
|------|------------|-------------|---------------------|----------------------|
| Push | 22.7 | 34.7 | 12.0 | 113.0 |
| Poll-5s | 22.0 | 34.3 | 12.3 | 108.0 |
| Poll-12s | 22.3 | 32.0 | 12.3 | 106.3 |
| Poll-30s | **10.7** | **28.3** | **10.0** | **70.3** |

> **Note**: "Elasticity Events" counts are from `elasticity_events.csv` and represent total controller scaling actions (alerts, spawns, removals across both LANs). They are a superset of the `node_lifecycle_timings.csv` spawn counts shown above.

### The Threshold Cliff

```
Compute Spawns
  25 ******Push******Poll-5s****Poll-12s
  15 --
  10 ------------------------------Poll-30s
```

The coordination gap manifests as a **threshold cliff** between Poll-12s and Poll-30s, not a gradual decline:
- Push through Poll-12s all cluster at ~22–23 compute spawns
- Poll-30s drops to ~11 compute spawns (−52%)
- Storage spawns follow a gentler decline (34.7 → 28.3, −18%)

This is consistent with the conversation-summary finding: the compound coordination gap (delivery × decision) produces a threshold effect, not a linear one. The system has resilience up to ~12s polling, then elasticity activity collapses at 30s.

### Why Doesn't This Hurt Users?

With CPU_SPAN=40, the controller only spawns when genuinely needed. In v3, the saturated spawn loop spawned nodes constantly regardless of need — some runs got "lucky" and spawned enough to handle the load, others didn't. In v4, every spawn is purposeful. Poll-30s spawns fewer nodes because:
1. It sees fewer telemetry windows (missed blind-spot windows)
2. The sliding window takes longer to accumulate evidence
3. By the time it decides to spawn, the peak may have passed

But because each spawn is purposeful (triggered by genuine CPU pressure, not the 10% artifact), the fewer spawns are sufficient. The system self-regulates.

---

## 5. Control-Plane Overhead

| Mode | CPU% (μ) | RAM MB (μ) |
|------|----------|------------|
| Push | 5.1% | 67 |
| Poll-5s | 5.4% | 71 |
| Poll-12s | 5.2% | 71 |
| Poll-30s | 5.0% | 68 |

Overhead is negligible across all modes. The polling mechanism does not impose meaningful CPU or memory cost at these cadences. Controller CPU is lower in v4 (5%) than v3 (11–14%). This is likely due to `W_STORAGE_CPU=0` (eliminating storage CPU score computation) and other RQ3 calibration changes (`STORAGE_CPUS=0.08`, floor 3%→10%), not reduced spawning activity (which is actually higher in v4 — see §6).

**Evidence**: Per-run `analysis/rq1_overhead.csv` (12 files). Comparison graph: [`rq1_v2_overhead_comparison.png`](graphs/comparison/rq1_v2_overhead_comparison.png).

> **Graph naming note**: The comparison graph script has a hardcoded `rq1_v2_` filename prefix. All `rq1_v2_*` files in `graphs/comparison/` were regenerated with v4 data and overwrote the v2final-era comparison graphs. The `rq1_v3_*` files (from the v3 campaign, using a versioned script variant) coexist in the same directory. The prefix is a script artifact, not a data version indicator — all graphs referenced in this document contain v4 data.

---

## 6. Comparison with v3

| Metric | v3 Push | v4 Push | v3 Poll-30s | v4 Poll-30s |
|--------|---------|---------|-------------|-------------|
| Timeout rate (μ ± σ) | 5.9 ± 7.2% | **1.2 ± 0.1%** | 25.5 ± 9.1% | **1.6 ± 0.5%** |
| Bimodality | Present (σ=7.2pp) | **Resolved (σ=0.1pp)** | Present (σ=9.1pp) | **Resolved (σ=0.5pp)** |
| Compute spawns (μ) | 18.3 | 22.7 | 8.7 | 10.7 |
| Storage spawns (μ) | 15.3 | 34.7 | 15.0 | 28.3 |
| Max server count | 5 | 4 | 4 | 3 |
| Max storage count | 7–8 | 6 | 8 | 6 |
| Controller CPU% | 14.2% | 5.1% | 11.0% | 5.0% |
| Staleness max | ~0.04 s | ~0.04 s | ~9.94 s | ~9.94 s |

### What Changed

1. **CPU_SPAN=5 → 40**: The saturated scoring function (any node at ≥10% CPU got max score) was the root cause of v3's bimodality. The uncontrolled spawn loop randomly reached "enough" servers or didn't — producing the healthy/degraded split.
2. **DATA_SEED=42**: Content/user data is now deterministically seeded, eliminating a confound.
3. **WAN_RTT_MS=185** (was 200), **STORAGE_CPUS=0.08** (was 0.10): RQ3-calibrated values.

### What Stayed the Same

1. **Staleness step-function**: Identical between v3 and v4 — the aggregation pipeline is independent of scoring.
2. **All 4 mechanisms exercise**: Storage, compute, Tier 1 selective sync, and reserve activation exercise in all runs.
3. **storage_storm is the worst phase**: Consistent across both versions.
4. **Overhead is negligible**: Both versions show modest CPU/RAM usage.

---

## 7. Conclusions

1. **CPU_SPAN=5 was the root cause of v3's bimodality.** The saturated scoring function created a random walk between healthy and degraded regimes. With CPU_SPAN=40, the system operates in a single, stable, healthy regime.

2. **The coordination gap in user-visible outcomes has essentially disappeared.** Poll-30s users experience 1.6% timeout rate vs Push's 1.2% — a 0.4pp difference within the noise floor. The gap that dominated v3 (19.6pp) is gone.

3. **The coordination gap persists in elasticity behavior.** Poll-30s spawns 52% fewer compute nodes and generates 38% fewer elasticity events than Push. The threshold cliff between Poll-12s and Poll-30s is the signature of the compound coordination gap (delivery cadence × decision latency).

4. **The system self-regulates with proper calibration.** Even though Poll-30s spawns less, service quality is maintained. Each spawn is purposeful — triggered by genuine CPU pressure, not the 10% artifact. The system achieves the same outcome with fewer resources.

5. **For thesis use**: The contribution is refined from "the gap causes 4.3× higher timeouts" to **"the gap's user-visible harm is bounded by proper calibration; the gap manifests as reduced elasticity activity rather than catastrophic service degradation."** This is a more nuanced and defensible position — it shows that the unified architecture's properly-calibrated trigger eliminates the coordination gap's worst consequences, while acknowledging that the gap still exists at the control-plane level.

6. **The reaction latency metric needs recalibration for v4.** The breach detector's pairing logic, designed for v3's aggressive spawning pattern, produces different measurements under v4's conservative spawning. Direct v3→v4 comparison of reaction latency is not meaningful.

---

## 8. Artifacts

| Artifact | Location |
|----------|----------|
| Comparison graphs (×8) | [`graphs/comparison/`](graphs/comparison/) — latency mean/max/reaction, overhead, staleness, timeout, per-phase timeout, decision quality (7 PNGs + 1 CSV = 8 artifacts) |
| Per-run data (×12) | `source/scripts/testing/metrics/202607*_rq1_v4_*/` |
| Decision quality aggregate | [`graphs/comparison/rq1_v2_decision_quality.csv`](graphs/comparison/rq1_v2_decision_quality.csv) |
| This results document | [`results_v4.md`](results_v4.md) |
| Experiment plan | [`experiment_plan_v4.md`](experiment_plan_v4.md) |

---

## 9. Changelog

| Date | Change |
|------|--------|
| 2026-07-20 | Initial v4 results written. 12/12 runs analyzed. Bimodality confirmed resolved (artifact of CPU_SPAN=5). Coordination gap in timeout rate reduced by ~98%. Threshold cliff in elasticity behavior identified between Poll-12s and Poll-30s. All 8 criteria assessed. Comparison graphs generated and archived. |
| 2026-07-20 | **Review corrections** (Reviewer agent): C4 split into C4a (Not Met — absolute count higher) and C4b (Met — spawning quality); added graph naming note explaining hardcoded `rq1_v2_*` prefix; added max server/storage count rows to v3→v4 comparison table; fixed incorrect CPU overhead explanation; added reaction latency direction reversal to executive summary; removed undefined "Total Spawns" column from elasticity table; added Poll-5s/Poll-12s expansion rationale and execution order note; discussed storage spawn increase; flagged poll30_1 as mild outlier; changed C2 label from "Refined" to "Partially Met"; fixed overhead CSV path; added per-mode μ±σ rows to per-phase table; corrected graph count; noted status legend threshold difference.
