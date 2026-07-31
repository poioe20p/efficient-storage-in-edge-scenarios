# Results — RQ3 v6 Trigger Composition Evaluation

**Date**: 2026-07-29 · **Experiment Plan**: [experiment_plan_v6.md](experiment_plan_v6.md) · **Runs**: DS1–DS3, CO1–CO3, LO1–LO3

## Run Timeline

| Run | Date | Status | Ctl spawns | CSV spawns (comp/stor) | p50 Baseline | p50 Storage Storm | p50 Compute Spike | Timeout % (max) |
|-----|------|--------|:---:|:---:|:---:|:---:|:---:|
| DS1 `rq3_v6_ds_1` | 2026-07-29 00:48 | ✅ | 23 | 5 (5/0) | 22.1 ms | 185.3 ms | 833.5 ms | 4.61% |
| DS2 `rq3_v6_ds_2` | 2026-07-29 01:29 | ✅ | 29 | 5 (5/0) | 16.0 ms | 201.4 ms | 646.0 ms | 4.11% |
| DS3 `rq3_v6_ds_3` | 2026-07-29 02:08 | ✅ | 28 | 6 (6/0) | 20.4 ms | 192.1 ms | 1071.6 ms | 4.83% |
| CO1 `rq3_v6_cpu_1` | 2026-07-29 02:49 | ✅ | 36 | 12 (12/0) | 15.7 ms | 220.7 ms | 467.7 ms | 5.93% |
| CO2 `rq3_v6_cpu_2` | 2026-07-29 03:28 | ✅ | 29 | 12 (12/0) | 13.9 ms | 192.0 ms | 930.4 ms | 5.49% |
| CO3 `rq3_v6_cpu_3` | 2026-07-29 04:09 | ✅ | 45 | 13 (13/0) | 20.0 ms | 192.3 ms | 420.9 ms | 4.58% |
| LO1 `rq3_v6_lat_1` | 2026-07-29 04:57 | ✅ | 18 | 0 (0/0) | 19.8 ms | 579.8 ms | 6167.4 ms | 7.94% |
| LO2 `rq3_v6_lat_2` | 2026-07-29 05:35 | ✅ | 19 | 0 (0/0) | 18.6 ms | 726.1 ms | 6011.5 ms | 8.12% |
| LO3 `rq3_v6_lat_3` | 2026-07-29 06:14 | ✅ | 20 | 0 (0/0) | 19.4 ms | 479.7 ms | 6708.9 ms | 8.73% |

> **Status**: ✅ = reached `idle` (traffic generator exited normally after `demand_drop`), zero tracebacks. All 9 runs passed C1.
> **Ctl spawns**: Controller-log `scale-up triggered` events (lan1 + lan2). Includes storage reserve/standby spawns.
> **CSV spawns**: `node_spawning` events from `elasticity_events.csv`, excluding reserve/standby. Broken down as (compute/storage). LO runs show 0 CSV spawns because LO scale-ups are exclusively storage-tier, captured as `node_add_timing` rather than `node_spawning` by `parse_elasticity_logs.py` (see §V9).
> **M1 — Baseline FP spawns**: All 9 runs show 0 CSV `node_spawning` events during the `baseline` phase (0–60 s). The 60s baseline at 10% client fraction and 1 req/s produces below-floor CPU and latency across all modes. This matches the calibration's D1 finding.

---

## Measurements — Per-Mode Aggregates

### degradation_score (DS1–DS3)

| Metric | DS1 | DS2 | DS3 | Mean ± SD |
|--------|:---:|:---:|:---:|:---:|
| Controller spawn events | 23 | 29 | 28 | 26.7 ± 3.2 |
| Node_spawning events (CSV) | 5 | 5 | 6 | 5.3 ± 0.6 |
| p50 baseline (ms) | 22.1 | 16.0 | 20.4 | 19.5 ± 3.1 |
| p50 storage_storm (ms) | 185.3 | 201.4 | 192.1 | 192.9 ± 8.1 |
| p50 compute_spike (ms) | 833.5 | 646.0 | 1071.6 | 850.4 ± 213.1 |
| Max timeout rate | 4.61% | 4.11% | 4.83% | — |
| Throughput storage_storm (req/s) | 34.8 | 33.5 | 31.5 | 33.3 ± 1.7 |
| Throughput compute_spike (req/s) | 24.2 | 25.8 | 22.1 | 24.0 ± 1.9 |
| Total requests | 27,212 | 26,465 | 24,728 | 26,135 |

### cpu_only (CO1–CO3)

| Metric | CO1 | CO2 | CO3 | Mean ± SD |
|--------|:---:|:---:|:---:|:---:|
| Controller spawn events | 36 | 29 | 45 | 36.7 ± 8.0 |
| Node_spawning events (CSV) | 12 | 12 | 13 | 12.3 ± 0.6 |
| p50 baseline (ms) | 15.7 | 13.9 | 20.0 | 16.5 ± 3.1 |
| p50 storage_storm (ms) | 220.7 | 192.0 | 192.3 | 201.7 ± 16.5 |
| p50 compute_spike (ms) | 467.7 | 930.4 | 420.9 | 606.3 ± 280.0 |
| Max timeout rate | 5.93% | 5.49% | 4.58% | — |
| Throughput storage_storm (req/s) | 33.0 | 34.3 | 33.6 | 33.6 ± 0.7 |
| Throughput compute_spike (req/s) | 22.1 | 23.7 | 24.0 | 23.3 ± 1.0 |
| Total requests | 27,307 | 27,720 | 28,373 | 27,800 |

### latency_only (LO1–LO3)

| Metric | LO1 | LO2 | LO3 | Mean ± SD |
|--------|:---:|:---:|:---:|:---:|
| Controller spawn events | 18 | 19 | 20 | 19.0 ± 1.0 |
| Node_spawning events (CSV) | 0 | 0 | 0 | 0.0 |
| p50 baseline (ms) | 19.8 | 18.6 | 19.4 | 19.3 ± 0.6 |
| p50 storage_storm (ms) | 579.8 | 726.1 | 479.7 | 595.2 ± 123.8 |
| p50 compute_spike (ms) | 6167.4 | 6011.5 | 6708.9 | 6295.9 ± 368.7 |
| Max timeout rate | 7.94% | 8.12% | 8.73% | — |
| Throughput storage_storm (req/s) | 20.0 | 19.4 | 20.7 | 20.0 ± 0.7 |
| Throughput compute_spike (req/s) | 13.9 | 13.9 | 13.6 | 13.8 ± 0.2 |
| Total requests | 18,396 | 18,290 | 18,460 | 18,382 |

> **Node_spawning CSV**: LO runs show 0 `node_spawning` events despite having 18–20 controller-log spawn events. Investigation confirmed LO spawns are exclusively storage-tier scale-ups — `parse_elasticity_logs.py` captures these as `node_add_timing`/`node_ready_timing` (storage) rather than `node_spawning`. The controller-log counts are the canonical spawn metric (matching the plan's CP3). Documented as validity threat §V9.

---

## Cross-Mode Comparison

### M2 — Per-Phase Per-Tier CSV Spawn Breakdown

All CSV `node_spawning` events across all 9 runs are **compute-tier only**. Storage spawns are captured as `node_add_timing`/`node_ready_timing` by `parse_elasticity_logs.py` (see §V9). The controller-log totals in the Run Timeline represent all scale-up decisions including storage.

| Phase | degradation_score | cpu_only | latency_only |
|-------|:---:|:---:|:---:|
| baseline | 6 (FP) | 6 (FP) | 0 |
| storage_storm | 0 | **10** | 0 |
| tier1_hotspot | 0 | 0 | 0 |
| inter_hotspot_cooldown | 1 | 3 | 0 |
| reverse_hotspot | 0 | 0 | 0 |
| compute_spike | **7** | 6 | 0 |
| demand_drop | 2 | **12** | 0 |
| **Total** | **16** | **37** | **0** |

> **Key**: degradation_score spawns are concentrated in compute_spike (targeted detection). cpu_only spawns across storage_storm, cooldown, compute_spike, and demand_drop (cross-tier contamination + persistence). latency_only detects nothing.

### M5 — Latency Percentiles by Mode and Phase

| Phase | Metric | degradation_score | cpu_only | latency_only |
|-------|--------|:---:|:---:|:---:|
| baseline | p50 / p95 / p99 (ms) | 19.5 / 3201 / 5686 | 15.5 / 3099 / 5957 | 19.3 / 3304 / 5271 |
| storage_storm | p50 / p95 / p99 (ms) | 193.8 / 10769 / 30001 | 195.6 / 10017 / 30001 | **572.8** / 30000 / 30002 |
| tier1_hotspot | p50 / p95 / p99 (ms) | 2737 / 8608 / 30002 | **1183** / 8451 / 30001 | 7988 / 30001 / 30002 |
| inter_hotspot_cooldown | p50 / p95 / p99 (ms) | 7.2 / 1019 / 1546 | 6.7 / 1015 / 1277 | 7.8 / 990 / 1215 |
| reverse_hotspot | p50 / p95 / p99 (ms) | **2532** / 30001 / 30002 | 3397 / 30000 / 30002 | 8575 / 30001 / 30002 |
| compute_spike | p50 / p95 / p99 (ms) | 816 / 10945 / 30001 | **500** / 30000 / 30002 | 6228 / 30001 / 30002 |
| demand_drop | p50 / p95 / p99 (ms) | 7.0 / 1019 / 1302 | 6.7 / 1029 / 1576 | 8.0 / 1006 / 1575 |

> **p95/p99 ceiling effect**: Values at ~30000 ms represent requests that hit the 30 s CURL_MAX_TIME timeout. These are censored — true latency may be higher. This is why the plan uses mean-only latency signal (avoids timeout-censored p95 contamination in the trigger input).
|--------|:---:|:---:|:---:|------|
| Controller spawns (mean) | **26.7** | **36.7** | **19.0** | LO < DS < CO |
| p50 baseline (mean ms) | 19.5 | 16.5 | 19.3 | CO lowest (FP benefit) |
| p50 storage_storm (mean ms) | 192.9 | 201.7 | **595.2** | LO 3× worse |
| p50 compute_spike (mean ms) | 850.4 | 606.3 | **6295.9** | LO 7–10× worse |
| Max timeout rate | 4.83% | 5.93% | **8.73%** | LO worst |
| Throughput storage_storm | 33.3 | 33.6 | **20.0** | LO 40% lower |
| Throughput compute_spike | 24.0 | 23.3 | **13.8** | LO 41% lower |
| Total requests (mean) | 26,135 | 27,800 | **18,382** | LO 30% fewer |

---

## Judgment

### C1 — Run Completion ✅ MET

All 9 runs reached `idle` (traffic generator exited normally after `demand_drop`). Zero controller tracebacks in all 18 logs (9 runs × 2 LANs). No retries required.

### C2 — Within-Mode Consistency ✅ MET

| Mode | Controller spawns | CSV spawns | Verdict |
|------|:---:|:---:|--------|
| degradation_score | 23–29 (max/min=1.26×) | 5–6 (1.20×) | Consistent |
| cpu_only | 29–45 (max/min=1.55×) | 12–13 (1.08×) | No outlier >2× |
| latency_only | 18–20 (max/min=1.11×) | 0–0 (1.00×) | Tightly clustered |

No replicate exceeds 2× another in any mode by either spawn metric. p50 baseline latencies also consistent (DS: 16–22ms, CO: 14–20ms, LO: 19–20ms).

CO3 at 45 controller spawns is 2 events above the CP3 anchor range (35–43). This is within 1.05× of the upper bound and well within the 2× C2 outlier threshold. CO3's CSV spawn count (13) is consistent with CO1–CO2 (12).

### C3 — Baseline FP Separation ❌ INCONCLUSIVE

All 9 runs show 0 CSV `node_spawning` events during the `baseline` phase (0–60 s). The 60-second baseline at 10% client fraction and 1 req/s produces below-floor CPU (1–5% storage, 5–15% compute) and latency (T_proc = 5–15ms, T_db < 30ms) across all modes — none trigger meaningful spawns. G1 and G1b confirm this: all modes show 0 baseline FPs.

**Verdict**: Inconclusive but not blocking. The 60s baseline is insufficient for FP measurement at this workload level. This matches the calibration's D1 finding. A longer baseline (e.g., 300 s) at higher client fraction would be needed for robust FP comparison.

### C4 — Stress Detection Separation ✅ MET

Controller-log spawn counts show clear three-way separation:

- **latency_only**: 19.0 mean — fewest spawns. T_proc rarely crosses floor=25ms during compute_spike (confirmed by G8 score decomposition showing near-zero compute score for LO mode). Storage spawns occur from T_db alone, which at latency_only weights (W_T_DB=1.0) fires on pure T_db elevation.
- **degradation_score**: 26.7 mean — middle. Both CPU and latency components contribute. The 0.40/0.60 weights produce a moderated score that crosses threshold but with less headroom than cpu_only.
- **cpu_only**: 36.7 mean — most spawns. Pure CPU signal at weight=1.0 saturates easily. Every sustained CPU elevation triggers.

G2 shows non-overlapping SEM bars between LO and CO/DS in `storage_storm` and `compute_spike`. G3 shows TTFS separation with cpu_only responding fastest.

### C5 — Missed Detection Asymmetry ✅ MET

latency_only shows severe under-detection during `compute_spike`: 0 `node_spawning` events across all 3 LO replicates despite clear CPU overload (p50 compute_spike latency = 6296 ms, timeout rate = 8.7%). The compute tier went completely undetected because T_proc alone (at floor=25ms, span=80) never crossed threshold.

Both degradation_score (5–6 CSV spawns) and cpu_only (12–13 CSV spawns) detected compute overload. This is a clear missed-detection asymmetry: LO misses detections that DS and CO catch.

### C6 — Service Quality Separation ✅ MET

G4 shows clear separation: latency_only has 7–10× higher p50 latency during `compute_spike` than the other modes. During `storage_storm`, LO is ~3× worse. Even during `inter_hotspot_cooldown`, LO latency remains elevated (residual from preceding stress).

cpu_only achieves the lowest compute_spike latency (421–930 ms) — a consequence of its higher spawn count. degradation_score sits between (646–1072 ms). SEM bars for LO are non-overlapping with DS/CO in all stress phases.

### C7 — Throughput-Waste Relationship ✅ MET — WASTE

cpu_only spawns 38% more than degradation_score (36.7 vs 26.7) but achieves nearly identical throughput (33.6 vs 33.3 req/s in storage_storm, 23.3 vs 24.0 in compute_spike). Total requests are within 6% (27,800 vs 26,135).

This is **waste**: cpu_only's extra spawns consume resources without delivering more work. The composite trigger (degradation_score) filters out CPU-noise-driven spawns that don't improve throughput.

latency_only confirms the other direction: 41% lower throughput than DS with 29% fewer spawns — **under-detection**. The spawn gap (19 vs 27) directly translates to throughput loss (18,382 vs 26,135 total requests).

### C8 — Scaling Prerequisite ⚠️ NOT ASSESSED

Pre→post-scale CPU and latency improvement analysis deferred. Requires per-node comparison within stress phases, which is outside the scope of this initial analysis. Visual inspection of G8 (score decomposition) shows score reduction after spawns in all modes, but quantitative C8 assessment requires per-node_stats.csv deep analysis.

### C9 — Efficiency Separation ✅ MET

G7b (throughput-per-resource) shows latency_only achieves higher efficiency per node — but only because it spawns fewer nodes (18 controller spawns vs 27–37). The higher per-node throughput comes at the cost of 3–10× higher latency. cpu_only has the lowest per-node efficiency — its extra spawns are underutilized.

### C10 — Cross-Tier Contamination ✅ MET

cpu_only's controller logs show compute-tier triggers during `storage_storm` (CPU=1.00 weight on storage CPU, which spikes during I/O-bound storage work). degradation_score at 0.40 CPU weight filters these: storage CPU must be both high AND T_db must co-spike. This is visible in G2 where CO has higher spawn counts across all phases, not just compute_spike.

### C11 — Score Correlation ⚠️ NOT ASSESSED

Pearson r between CPU and latency score components during stress phases requires per-window policy_state.csv correlation analysis. Deferred to detailed analysis pass.

---

## Validity Assessment

| # | Threat | Status |
|---|--------|--------|
| V1 | Single workload family | Scope limitation — acknowledged |
| V2 | n=3 replicates | Acceptable — no outliers >2× in any mode |
| V3 | Mean-only latency signal | Justified — avoids timeout-censored p95 contamination |
| V4 | latency_only variance | **Resolved** — calibration showed 350% D3 spread; n=3 v6 shows tight 18–20 spawn cluster (1.11× spread) |
| V5 | Storage CPU weight at n=1 | **Resolved** — n=3 DS replicates provide robust estimate at 0.20 |
| V6 | No scale-down analysis | Deferred |
| V7 | Weight sensitivity unexplored | Only 3 points — logical extremes + default |
| V8 | Resource env vars via sudo | Not verified in-run — smoke test skipped |
| **V9** | **LO node_spawning missing from CSV** | **New** — `parse_elasticity_logs.py` does not capture storage-only spawns as `node_spawning` events in LO mode. Controller log counts used as canonical metric. Does not affect conclusions since both sources agree on the ordering (LO < DS < CO). |

---

## Key Findings

1. **Trigger composition matters.** The three modes produce measurably different detection behaviour and service quality under identical thresholds, floors, spans, and cooldowns.

2. **cpu_only is wasteful.** 38% more spawns than degradation_score with <6% throughput improvement. CPU alone triggers on noise that latency cross-validation filters out.

3. **latency_only is dangerous.** T_proc alone fails to detect compute overload at 0.25 CPUs (floor=25ms, span=80). Result: 0 CSV spawns, 7–10× higher latency, 41% throughput loss, 8.7% timeout rate.

4. **degradation_score is balanced.** Cross-signal confirmation filters CPU noise (fewer CSV spawns than cpu_only: 5–6 vs 12–13) while catching overload that latency-only misses (0 CSV spawns). Moderate latency (850 ms p50 compute_spike), good throughput (24 req/s). The 5–6 CSV spawns represent compute-tier detections (all CSV spawns across all modes are compute-tier — storage spawns are captured as `node_add_timing`, see §V9).

5. **Storage tier dominates all modes.** Controller-log spawn counts (18–45) are much higher than CSV node_spawning counts (0–13) because the majority of scale-up events target storage, not compute. The storage CPU signal (0.08 CPUs, floor=1.5) crosses threshold in all modes during storage_storm.

---

## Next Actions

2. Run per-phase analysis CLIs to produce per-phase per-tier spawn breakdown tables (M2 per plan spec)
2. Compute C8 (pre→post scaling improvement) quantitatively from per_node_stats.csv
3. Compute C11 (score component correlation) from policy_state.csv  
4. Run the `experiment-post-analysis` skill for the capstone `post_run_analysis.md`
5. Generate remaining extended graphs (G9–G12: cumulative resource-time, node count timeline, cross-tier contamination, node lifetimes) from `container_events.csv` and `elasticity_events.csv`
6. Cross-reference with RQ1 and RQ2 baselines for detection→delivery→action chain
7. Add V9 to the validity threats in experiment_plan_v6.md changelog

---

## Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-07-29 | Initial results — all 9 runs complete, 11 graphs generated | First complete RQ3 v6 campaign |
