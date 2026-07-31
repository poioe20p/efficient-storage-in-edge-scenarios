# RQ3 v6 — Theory Predictions

> Formalised predictions for the three trigger composition modes before the
> 9-run evaluation. These predictions are **falsifiable**: the experiment is
> designed so that every prediction either matches the data or is contradicted.
> Contradiction is informative — the thesis's "any outcome is informative"
> principle (§4.3 of rq3_v6.md) means that disproving a prediction bounds the
> contribution.

---

## 1. Causal Model

```
TRIGGER_COMPOSITION (w_cpu, w_lat)
  │
  ├─→ Detection Quality
  │     ├─ M1: FP spawns during baseline
  │     ├─ M2: Spawn count during stress
  │     ├─ M3: Time-to-first-spawn (TTFS)
  │     └─ M4: Missed detections
  │
  ├─→ Service Quality
  │     ├─ M5: Per-phase latency (p50/p95/p99)
  │     ├─ M6: Timeout rate
  │     └─ M7: Throughput (completed requests)
  │
  └─→ Provisioning Efficiency
        ├─ M8: Resource-time product (CPU-seconds provisioned)
        ├─ M9: Cross-tier spawn contamination
        └─ M10: Score component correlation
```

The degradation score at window *t* is:

```
score_t = w_cpu × saturate((CPU%_t − floor_cpu) / span_cpu)
        + w_lat × saturate((latency_t − floor_lat) / span_lat)
```

where `saturate(x) = max(0, min(1, x))`. Scale-up triggers when the score
exceeds the adaptive threshold for `REQUIRED` of the last `WINDOW_SIZE` windows.

---

## 2. Signal Behavior Under Workload

These predictions describe how each signal behaves under the 7-phase workload
at G0-v6 resources (0.08/0.25 CPUs, WAN=185 ms, 96 clients).

### 2.1 CPU Utilization

| Phase | Storage CPU (0.08) | Compute CPU (0.25) |
|-------|-------------------|---------------------|
| `baseline` | 1–5% — near-idle, below floor (1.5) | 5–15% — near-idle, below floor (10) |
| `storage_storm` | 15–40% — I/O-wait and MongoDB work. Pre-scale peak ~37% (C-W20) | 20–40% — moderate from request processing |
| `tier1_hotspot` | 10–25% — Tier 1 selective-sync overhead | 25–50% — lookup-heavy processing |
| `inter_hotspot_cooldown` | 1–5% — drain | 5–15% — drain |
| `reverse_hotspot` | 10–25% — symmetric to tier1_hotspot | 25–50% — symmetric |
| `compute_spike` | 1–10% — minimal storage I/O (5% cross-region) | 40–55% — feed_ranking saturates CPU. Pre-scale peak ~46–50% (C-DS1) |
| `demand_drop` | 1–5% — drain | 5–15% — drain |

**Key asymmetries**:
- Storage CPU is weak but real: −21.8pp pre→post drop during storage_storm
  (37.4% → 15.6%, C-W20). It crosses `STORAGE_CPU_FLOOR=1.5` reliably but
  with small magnitude.
- Compute CPU during compute_spike is strong: 40–55% range, well above
  `CPU_FLOOR=10`. Span=40 gives linear sensitivity across the full range.

### 2.2 Processing Latency

| Phase | T_db (storage) | T_proc (compute) |
|-------|----------------|------------------|
| `baseline` | <30 ms — local reads | 5–15 ms — healthy |
| `storage_storm` | 200–1000 ms — WAN reads dominate. Pre-scale peak ~939 ms (C-W20). Post-scale ~0.1 ms. | 15–40 ms — elevated from storage I/O wait |
| `tier1_hotspot` | 200–300 ms — Tier 1 sync reads (G0-v6) | 10–25 ms |
| `inter_hotspot_cooldown` | <30 ms — drain | 5–15 ms |
| `reverse_hotspot` | 200–850 ms — asymmetric (direction-dependent) | 10–25 ms |
| `compute_spike` | <30 ms — near-zero cross-region (5%) | 15–50 ms — CPU saturation pushes latency up, but not dramatically at 0.25 CPUs |
| `demand_drop` | <30 ms — drain | 5–15 ms |

**Key asymmetries**:
- T_db during storage_storm is the dominant storage signal: massive elevation
  (200–1000 ms), far above `T_DB_FLOOR=60`. Span=250 gives good sensitivity.
- T_proc during compute_spike is moderate: 15–50 ms range. At `T_PROC_FLOOR=25`,
  the latency component crosses threshold but with smaller magnitude than CPU.

---

## 3. Mode Predictions — Compute Tier

### 3.1 degradation_score (0.40/0.60)

**Score dynamics**: Both CPU and latency contribute. During compute_spike,
CPU at 46–50% → `sat((46−10)/40)` = 0.90 → CPU component = 0.40×0.90 = 0.36.
T_proc at 25–50 ms → `sat((25−25)/80)` = 0.00–0.31 → latency component =
0.60×0.00–0.31 = 0.00–0.19. Total score ≈ 0.36–0.55.

Crosses `BASE_THRESHOLD=0.18` reliably. At 0.40 CPU weight, the CPU-alone
crossing point is CPU = 28% (0.40 × sat((28−10)/40) = 0.18). Since
compute_spike CPU is 40–55%, degradation_score crosses on CPU alone
throughout the stress phase — the latency component provides additional
margin but is not required for triggering. The "cross-signal confirmation"
model is most relevant near the threshold boundary (CPU 10–28%), where
latency must co-spike for the score to cross. At higher CPU, degradation_score
behaves as a scaled-down cpu_only.

> **Peer relief**: The setup doc defines `SCALEUP_COMPUTE_PEER_RELIEF=0.03`
> — the score is reduced by 0.03 per existing dynamic compute node. This
> curtails spawning after multiple nodes are active: the adaptive threshold
> escalates (+0.10 per spawn) while the effective score drops (−0.03 per
> peer). The score dynamics above describe the first-spawn condition;
> subsequent spawns require progressively higher raw scores.

**Predicted behavior**:

| Metric | Prediction | Rationale |
|--------|-----------|-----------|
| M1 — Baseline FPs | **Lowest of three modes** (0–1 per run) | CPU alone (5–15% → 0.00–0.12 component × 0.40 = 0.00–0.05) rarely crosses. Latency alone (5–15 ms → 0.00) never crosses. Both must spike simultaneously. |
| M2 — Compute spawns | **Middle** (~5–7 per run, C-W20 anchor) | Crosses threshold during compute_spike but with fewer spawns than cpu_only (both signals needed). More than latency_only (T_proc alone weak). |
| M3 — TTFS | **Middle** | Latency confirmation delays trigger relative to cpu_only, but CPU component activates earlier than pure-latency threshold crossing. |
| M4 — Missed detections | **Possible 1–2** | If a stress phase has CPU elevation without latency co-spike (e.g., early compute_spike before queue builds), composite may not fire. |
| M5 — Per-phase latency | **Middle in baseline, middle in compute_spike** | Fewer FP spawns → less unnecessary capacity in baseline → higher baseline latency than cpu_only. In compute_spike: fewer spawns than cpu_only but more than latency_only → middle latency. |
| M6 — Timeout rate | **<2% in all phases** | G0-v6 validated success rates ≥96.6% across all phases. Spawn count differences are unlikely to produce timeout-rate divergence at this resource level — all modes should stay below 2%. |
| M7 — Throughput | **Middle** | If fewer spawns = same throughput as cpu_only → waste. If fewer spawns = less throughput → under-detection. |
| M8 — Resource-time product | **Middle (~40% of cpu_only)** | Fewer spawns + peer relief → lower total CPU-seconds provisioned for compute tier. Expected ~5 spawns vs cpu_only's ~16 → ~31% as many node-seconds, but spawns may live longer (fewer nodes → less peer relief → each node handles more load). |
| M9 — Cross-tier contamination | **Low** | Storage stress phases (storage_storm) produce some compute CPU elevation (20–40%) but at 0.40 weight, the CPU component crossing threshold requires CPU >28%. Most storage-phase compute CPU is below this — contamination should be low. |
| M10 — Score component correlation | **High (r > 0.6) in compute_spike** | Both CPU and latency rise during genuine overload. The 0.40/0.60 weights mean both components contribute to the score when both signals are elevated. |

**Calibration evidence**: C-DS1/C-DS2: 7–8 compute spawns, D3 mean score 0.295.

### 3.2 cpu_only (1.00/0.00)

**Score dynamics**: Only CPU contributes. During compute_spike, CPU at 46–50%
→ CPU component = 1.00×0.90 = 0.90. Score = 0.90. Far above threshold.

During baseline, CPU at 5–15% → CPU component = 1.00×0.00–0.12 = 0.00–0.12.
Baseline CPU spikes (container startup, OVS, MongoDB background) at 15–20%
→ 0.12–0.25 — can cross `BASE_THRESHOLD=0.18`.

**Predicted behavior**:

| Metric | Prediction | Rationale |
|--------|-----------|-----------|
| M1 — Baseline FPs | **Highest of three modes** (1–3 per run) | CPU spikes during baseline cross threshold without latency confirmation to filter them. |
| M2 — Compute spawns | **Highest** (13–19 per run, calibration) | Pure CPU signal saturates easily. Every sustained CPU elevation triggers. |
| M3 — TTFS | **Fastest** | Single signal — no waiting for latency to confirm. Crosses as soon as CPU rises. |
| M4 — Missed detections | **Fewest (0)** | One condition (CPU high) is easier to satisfy than two. |
| M5 — Per-phase latency | **Lowest in baseline (FP benefit), lowest in compute_spike** | Extra FP spawns during baseline lower latency (a perverse benefit). More spawns during compute_spike = more capacity = lower latency. |
| M6 — Timeout rate | **<2% in all phases** | Highest spawn count = most capacity. Should have the lowest timeout rate, but all modes expected <2% at this resource level. |
| M7 — Throughput | **Highest or equal to degradation_score** | If extra spawns → more throughput → under-detection by composite. If extra spawns → same throughput → waste. |
| M8 — Resource-time product | **Highest (~2.5× of degradation_score)** | 13–19 spawns each living through cooldown → highest total CPU-seconds. If throughput is identical to degradation_score, this is pure waste. If throughput is higher, the extra cost may be justified. |
| M9 — Cross-tier contamination | **Highest — may trigger compute on storage stress** | w_cpu=1.00 means any compute CPU above 10% contributes fully. Storage-phase compute CPU of 20–40% produces scores of 0.25–0.75 — easily crossing BASE_THRESHOLD=0.18. cpu_only cannot distinguish *which* tier is stressed. |
| M10 — Score component correlation | **Undefined (no latency component)** | Score is CPU-only by definition. r is undefined for the latency component. This is the definitional weakness: the mode is structurally blind to latency. |

**Calibration evidence**: C-CO1/C-CO2: 13–19 compute spawns, D3 mean score 0.454.

### 3.3 latency_only (0.00/1.00)

**Score dynamics**: Only T_proc contributes. During compute_spike, T_proc at
15–50 ms → `sat((15−25)/80)` = 0.00 to `sat((50−25)/80)` = 0.31. Score =
0.00–0.31.

Crosses `BASE_THRESHOLD=0.18` only when T_proc > ~40 ms. Much of compute_spike
may sit below this — T_proc at 0.25 CPUs with 5% cross-region I/O is not
dramatically elevated.

**Predicted behavior**:

| Metric | Prediction | Rationale |
|--------|-----------|-----------|
| M1 — Baseline FPs | **Middle** (0–1 per run) | T_proc at 5–15 ms → 0.00 — below floor. Transient spikes above 25 ms possible but infrequent at 0.25 CPUs. |
| M2 — Compute spawns | **Lowest** (~3 per run, calibration) | T_proc rarely crosses 25 ms with enough magnitude at this workload. compute_spike is feed_ranking-heavy (CPU-bound), not I/O-bound. |
| M3 — TTFS | **Slowest (or tied with degradation_score)** | T_proc rises after CPU saturation — queue builds, then latency rises. Detection may be delayed relative to CPU-only. |
| M4 — Missed detections | **Most (1–3)** | T_proc alone may miss CPU-saturated phases where latency hasn't risen enough. |
| M5 — Per-phase latency | **Highest in compute_spike** | Fewer spawns → less capacity → higher latency during compute saturation. Baseline: highest (no FP spawns to create unnecessary capacity). |
| M6 — Timeout rate | **Potentially highest** | Fewest spawns = least capacity. If any mode exceeds 2% timeout rate, it will be latency_only. |
| M7 — Throughput | **Lowest in compute_spike** | Fewer spawns → less capacity → fewer completed requests. |
| M8 — Resource-time product | **Lowest** | ~3 spawns → minimal CPU-seconds provisioned. If throughput is only marginally lower than degradation_score, this is the most efficient mode — minimal provisioning, near-maximal throughput. |
| M9 — Cross-tier contamination | **Lowest** | w_t_proc=1.00, w_cpu=0.00. During storage stress, T_proc is 15–40 ms — below T_PROC_FLOOR=25 for much of the phase. Contamination should be near-zero. |
| M10 — Score component correlation | **Undefined (no CPU component)** | Score is latency-only. r is undefined for the CPU component. The mode is structurally blind to CPU saturation. |

**Calibration evidence**: C-LO1/C-LO2: 3 compute spawns each, D3 mean score
0.066 (but 350% spread between replicates — high variance).

---

## 4. Mode Predictions — Storage Tier

### 4.1 degradation_score (0.20/0.80)

**Score dynamics**: T_db dominates (0.80), CPU is secondary (0.20). During
storage_storm, T_db at 200–1000 ms → `sat((200−60)/250)` = 0.56 to
`sat((1000−60)/250)` = 1.00 (capped) → latency component = 0.80×0.56–1.00 =
0.45–0.80. CPU at 15–40% → `sat((15−1.5)/5)` = 1.00 (capped for most values
above ~6%) → CPU component = 0.20×1.00 = 0.20. Total score = 0.65–1.00.

Crosses `STORAGE_BASE_THRESHOLD=0.35` very reliably. The 0.20 CPU weight adds
a small but consistent boost (0.20) that helps push borderline T_db values
above threshold.

**Predicted behavior**:

| Metric | Prediction | Rationale |
|--------|-----------|-----------|
| M1 — Baseline FPs | **Lowest** (0–1) | T_db <30 ms → 0.00. Storage CPU 1–5% → `sat((1−1.5)/5)` = 0.00 to `sat((5−1.5)/5)` = 0.70 × 0.20 = 0.14. CPU alone cannot cross 0.35. Both must spike. |
| M2 — Storage spawns | **Middle** (~18, C-W20 anchor) | T_db drives triggering with CPU adding a consistent ~0.20 boost. Between latency_only (T_db-only) and cpu_only (CPU-dominated). |
| M3 — TTFS | **Middle** | CPU boost helps trigger slightly earlier than pure T_db. |
| M4 — Missed detections | **0–1** | T_db elevation during storage_storm is massive — hard to miss. |
| M5 — Per-phase latency | **Converges with other modes** | Storage I/O dominates latency during storage phases — all modes detect, all modes spawn, all modes get relief. |
| M6 — Timeout rate | **<2% in all phases** | Storage stress detection is reliable across modes — timeout rates should converge. |
| M7 — Throughput | **Converges** | Storage stress detection is reliable across all modes — throughput differences should be minimal. |
| M8 — Resource-time product | **Middle** | ~18 storage spawns. More than latency_only (15–17) but less than cpu_only (22–24). If throughput converges, the extra spawns vs latency_only are mild waste — the 0.20 CPU boost adds ~1–3 extra nodes. |
| M9 — Cross-tier contamination | **Low** | Compute-phase CPU (compute_spike) at 1–10% storage CPU → below STORAGE_CPU_FLOOR=1.5 for most of the phase. Storage spawns during compute_spike should be minimal. |
| M10 — Score component correlation | **Moderate (r ≈ 0.3–0.5)** | T_db and storage CPU both rise during storage_storm (I/O-wait drives CPU), but the correlation is weaker than compute: T_db spikes can occur without CPU co-spike (a single slow WAN read), and CPU can rise from MongoDB background ops without T_db spikes. |

**Calibration evidence**: C-W20: 18 storage spawns, T_db 939→0.1ms, CPU 37.4→15.6%.

### 4.2 cpu_only (1.00/0.00)

**Score dynamics**: Only storage CPU. During storage_storm, CPU at 15–40% →
CPU component = 1.00×1.00 = 1.00 (saturates at CPU >6.5%, which is almost
always during storage_storm). Score = 1.00.

**Predicted behavior**:

| Metric | Prediction | Rationale |
|--------|-----------|-----------|
| M1 — Baseline FPs | **Highest** (1–3) | Storage CPU spikes during baseline (MongoDB background operations, container startup) can cross 0.35. Low CPU floor (1.5) makes this easier than compute. |
| M2 — Storage spawns | **Highest** (22–24, calibration) | CPU saturates the score immediately during any storage activity. Triggers on any CPU elevation. |
| M3 — TTFS | **Fastest** | Single signal, immediate saturation. |
| M4 — Missed detections | **Fewest (0)** | One condition (CPU high) is easier to satisfy than two. |
| M5 — Per-phase latency | **Lowest in storage phases** | More spawns → more MongoDB nodes → better read distribution. But T_db is the real bottleneck — extra nodes may not reduce I/O-bound latency proportionally. |
| M6 — Timeout rate | **<2% in all phases** | Most spawns = most capacity. Should be lowest, but all modes expected <2%. |
| M7 — Throughput | **Equal to degradation_score** | Storage I/O is the bottleneck, not CPU. Extra CPU-triggered spawns may be waste. |
| M8 — Resource-time product | **Highest** | 22–24 spawns, each saturating the score immediately → most storage nodes provisioned. If throughput is identical to degradation_score, these extra nodes are pure waste — CPU-triggered storage spawns that don't reduce I/O-bound latency. |
| M9 — Cross-tier contamination | **Highest — may trigger storage on compute stress** | w_storage_cpu=1.00 with STORAGE_CPU_FLOOR=1.5. Compute_spike storage CPU at 1–10% → score 0.00–1.00. Upper range crosses STORAGE_BASE_THRESHOLD=0.35. Storage nodes may spawn during compute stress despite no storage I/O pressure. |
| M10 — Score component correlation | **Undefined (no latency component)** | Score is CPU-only. Structurally blind to T_db — the actual bottleneck. |

**Calibration evidence**: C-CO1/C-CO2: 22–24 storage spawns.

### 4.3 latency_only (0.00/1.00)

**Score dynamics**: Only T_db. During storage_storm, T_db at 200–1000 ms →
latency component = 1.00×0.56–1.00 = 0.56–1.00. Score = 0.56–1.00.

**Predicted behavior**:

| Metric | Prediction | Rationale |
|--------|-----------|-----------|
| M1 — Baseline FPs | **Middle** (0–1) | T_db <30 ms → 0.00. Transient spikes above 60 ms possible from MongoDB background ops. |
| M2 — Storage spawns | **Lowest** (15–17, calibration) | T_db alone triggers slightly less often than T_db+CPU. The 0.20 CPU boost in degradation_score pushes borderline windows above threshold. |
| M3 — TTFS | **Slowest** | T_db must rise above 60 ms before triggering. CPU rises earlier (I/O-wait) but is ignored. |
| M4 — Missed detections | **0–1** | T_db elevation is massive — hard to miss. But without the 0.20 CPU boost, borderline windows may fall below threshold. |
| M5 — Per-phase latency | **Converges with other modes** | Storage I/O dominates — spawn count differences have limited impact on I/O-bound latency. |
| M6 — Timeout rate | **<2% in all phases** | Fewest spawns, but storage I/O is the bottleneck — extra nodes don't reduce I/O-bound latency proportionally. |
| M7 — Throughput | **Converges** | Fewer spawns = fewer MongoDB nodes, but I/O dominates — throughput differences should be minimal. |
| M8 — Resource-time product | **Lowest** | 15–17 spawns, T_db-only triggering. Fewest storage nodes provisioned. If throughput converges with other modes, this is the most efficient — minimal provisioning, same outcome. |
| M9 — Cross-tier contamination | **Lowest** | w_t_db=1.00, w_storage_cpu=0.00. Compute_spike T_db <30 ms (5% cross-region) → below T_DB_FLOOR=60. Storage spawns during compute stress should be near-zero. |
| M10 — Score component correlation | **Undefined (no CPU component)** | Score is latency-only. Structurally blind to storage CPU — but at 0.08 CPUs this is the correct choice (CPU is weak). |

**Calibration evidence**: C-LO1/C-LO2: 15–17 storage spawns.

---

## 5. Summary Prediction Table

### 5.1 Detection Quality

| Metric | Predicted ordering (most → least) | Key pairwise comparison |
|--------|----------------------------------|------------------------|
| M1 — Baseline FP spawns (compute) | cpu_only > latency_only > degradation_score | cpu_only vs degradation_score — does latency confirmation filter CPU noise? |
| M1 — Baseline FP spawns (storage) | cpu_only > latency_only ≥ degradation_score | cpu_only vs degradation_score — does T_db confirmation filter storage CPU noise? |
| M2 — Stress spawn count (compute) | cpu_only > degradation_score > latency_only | Three-way ordering — is the separation statistically distinguishable? |
| M2 — Stress spawn count (storage) | cpu_only > degradation_score > latency_only | degradation_score vs latency_only — does 0.20 CPU weight produce meaningful separation from T_db-only? |
| M3 — TTFS (both tiers) | cpu_only (fastest) > degradation_score > latency_only (slowest) | cpu_only vs latency_only — does queueing-before-saturation produce measurable TTFS differences? |
| M4 — Missed detections | latency_only (most) > degradation_score > cpu_only (fewest) | latency_only vs cpu_only — is single-dimension detection more reliable? |

### 5.2 Service Quality

| Metric | Predicted ordering | Key pairwise comparison |
|--------|-------------------|------------------------|
| M5 — Baseline latency | cpu_only (lowest, FP benefit) < degradation_score < latency_only (highest) | cpu_only vs degradation_score — do FP spawns create measurable latency benefit? |
| M5 — Storage-phase latency | Converged (all modes similar) | Within 10% — storage I/O dominates trigger composition differences |
| M5 — Compute-phase latency | cpu_only (lowest) < degradation_score < latency_only (highest) | degradation_score vs latency_only — does spawn count difference translate to latency difference? |
| M6 — Timeout rate | All modes <2% (if calibrated correctly) | Any mode >5% = calibration failure |
| M7 — Throughput (compute) | cpu_only ≥ degradation_score ≥ latency_only | cpu_only vs degradation_score — **the key RQ3 question**: waste or under-detection? |
| M7 — Throughput (storage) | Converged (within 5%) | Storage I/O is the bottleneck, not CPU capacity |
| M8 — Resource-time product (compute) | cpu_only (highest) > degradation_score > latency_only (lowest) | cpu_only vs degradation_score — does 2.5× more CPU-seconds buy any throughput? |
| M8 — Resource-time product (storage) | cpu_only (highest) > degradation_score > latency_only (lowest) | cpu_only vs degradation_score — does CPU-triggered storage spawning waste resources? |
| M9 — Cross-tier contamination | cpu_only (highest) > degradation_score > latency_only (lowest) | cpu_only — does the industry default spawn nodes for the wrong tier? |
| M10 — Score component correlation | degradation_score (high) > single-dimension modes (undefined) | degradation_score — does the composite score measure a single underlying phenomenon (overload) or two independent noise sources? |

### 5.3 Two-Tier Asymmetry

| Dimension | Compute tier (0.25 CPUs) | Storage tier (0.08 CPUs) |
|-----------|--------------------------|--------------------------|
| Both signals independently meaningful? | ✅ Yes — CPU 40–55%, T_proc 15–50 ms | ⚠️ Partial — T_db 200–1000 ms (strong), CPU 15–40% (weak but real) |
| Expected divergence | Three-way | Partial (degradation_score between extremes) |
| Thesis implication | Trigger composition matters where signals are independently meaningful | The space is bounded by resource constraints — at tighter limits, one signal dominates |

---

## 6. Falsification Conditions

Each prediction has a specific falsification condition. If observed, the
corresponding thesis claim is weakened:

| # | If observed... | Then... |
|---|---|---|
| F1 | All three modes produce identical spawn counts (±10%) in ALL stress phases (storage_storm, tier1_hotspot, reverse_hotspot, compute_spike) for BOTH tiers | Trigger composition does not matter at this resource level. The detection link is not the bottleneck. (Baseline and cooldown phases excluded — zero spawns expected for all modes.) |
| F2 | degradation_score produces MORE FPs than cpu_only in baseline | Cross-signal confirmation does NOT filter noise — it amplifies it. The formula structure is wrong. **Note**: The calibration's D1 check was inconclusive (60s baseline too short). If the experiment's baseline also lacks statistical power for FP measurement, F2 may not be evaluable — flag this in analysis. |
| F3 | latency_only produces MORE compute spawns than cpu_only | T_proc is a stronger signal than CPU at this workload. The industry default (CPU-only) is suboptimal in the opposite direction than predicted. |
| F4 | Throughput is identical across modes despite spawn count differences ≥2× in at least one tier | Extra spawns are pure waste. Composite is optimal. |
| F5 | Throughput differs meaningfully (>10%) between modes with the largest spawn-count difference | Composite under-detects — it misses real overload. Sub-proportional throughput differences (spawns 2× higher but throughput only 5% higher) also suggest waste, with a minor capacity benefit. |
| F6 | Storage tier shows three-way divergence (cpu_only, degradation_score, latency_only all distinguishable) | Storage CPU at 0.08 is a stronger signal than expected. The resource bound is wider than predicted. |
| F7 | Storage tier shows complete convergence (all three modes identical in spawn count) | Storage CPU at 0.08 is pure noise. The 0.20 weight is wasted — T_db alone is sufficient. |
| F8 | latency_only TTFS ≤ cpu_only TTFS in compute_spike | Queueing-before-saturation does not produce measurable TTFS differences — CPU rises fast enough that latency-only detection is not delayed. |
| F9 | cpu_only resource-time product ≤ 1.5× degradation_score despite ≥2× spawn count | The extra spawns are short-lived — cpu_only nodes die quickly (peer relief + cooldown), so the provisioning cost is not proportional to spawn count. |
| F10 | Cross-tier contamination >30% in any mode | The G0-v6 resource configuration does not provide clean tier separation. Trigger composition interacts with tier isolation — single-dimension modes cannot distinguish which tier is stressed. |
| F11 | degradation_score score component correlation r < 0.3 during compute_spike | CPU and latency are independent noise sources at this workload. The two-signal formula combines unrelated signals rather than cross-validating a single overload phenomenon. |
| F12 | M8 Resource-time product ordering is the same as M2 spawn count ordering for BOTH tiers | Resource cost is proportional to spawn count — node lifetimes are similar across modes. Cooldown and peer relief do not differentiate modes. |

---

## 7. Calibration Anchors

Expected values grounded in the 8-run divergence calibration:

| Anchor | Value | Source | n |
|--------|-------|--------|---|
| DS compute spawns | ~5 (C-W20, n=1) or 7–8 (C-DS1/C-DS2, n=2 at same compute weights 0.40/0.60, different storage weights 0.60/0.40) | C-W20 uses final calibrated storage weights (0.20/0.80); C-DS1/C-DS2 predate the storage probe. The ~5 anchor is the calibrated-config value; if the n=3 evaluation produces 7–8, storage→compute cross-tier interaction may explain the discrepancy. |
| DS storage spawns | 18 | C-W20 (0.20/0.80) | 1 |
| CO compute spawns | 13–19 | C-CO1, C-CO2 | 2 |
| CO storage spawns | 22–24 | C-CO1, C-CO2 | 2 |
| LO compute spawns | 3 | C-LO1, C-LO2 | 2 |
| LO storage spawns | 15–17 | C-LO1, C-LO2 | 2 |
| D3 mean score (cpu_only) | 0.454 | compute_spike, LAN1 mean of 2 replicates | 2 |
| D3 mean score (degradation_score) | 0.295 | compute_spike, LAN1 mean of 2 replicates (C-DS1/C-DS2, pre-probe storage weights 0.60/0.40 — compute score is independent of storage weights, so this anchor is valid). LAN2 data also available but LAN1 is the calibration's primary reference. | 2 |
| D3 mean score (latency_only) | 0.066 | compute_spike, LAN1 mean of 2 replicates (warning: 350% spread between replicates 0.024 vs 0.108) | 2 |
| Storage pre→post CPU drop | −21.8pp | C-W20, storage_storm | 1 |
| Storage pre→post T_db drop | −939ms | C-W20, storage_storm | 1 |

> **Note**: DS compute and DS storage anchors are n=1. The n=3 evaluation
> will provide the first robust estimates. If true means are outside these
> ranges, update predictions accordingly.

---

## 8. Extended Graph Inventory

The original 10 graphs (G1–G8 + G1b + G5b from `rq3_v6.md` §6) cover
detection quality (G1–G3, G8), service quality (G4–G7), and diagnostics.
The extensions below add **provisioning efficiency** and **node overhead**
graphs to complete the picture.

### 8.1 Efficiency Graphs

| # | Graph | Type | What it shows |
|---|---|---|---|
| **G7b** | Throughput-per-Resource by Mode | Grouped bar, one group per stress phase (compute + storage tiers side-by-side), 3 bars each. SEM + scatter dots. | Throughput ÷ Resource-time product. Efficiency ratio: how much completed work per CPU-second provisioned. If cpu_only has 2.5× the resource cost but same throughput → G7b shows a 2.5× efficiency gap. The companion to G7 — G7 asks "does extra spawning help?", G7b asks "at what cost?" |
| **G9** | Cumulative Resource-Time by Mode & Tier | Grouped bar, 2 groups (compute tier, storage tier), 3 bars each. SEM + scatter dots. | Total CPU-seconds provisioned across the entire run, per mode, per tier. Decomposes the "waste" claim: is cpu_only's extra cost concentrated in compute (where CPU signal is strong) or storage (where it's weak/I/O-dominated)? |

### 8.2 Node Overhead Graphs

| # | Graph | Type | What it shows |
|---|---|---|---|
| **G10** | Dynamic Node Count Over Time | Multi-panel line chart: 3 panels (one per mode, median replicate). Solid line: compute nodes. Dashed line: storage nodes. Shaded regions: stress phases. | The "shape" of scaling per mode. Shows node accumulation, cooldown drain, and cross-phase persistence. cpu_only should show rapid spikes that persist; degradation_score should show more gradual ramp; latency_only should show flatter profile with fewer nodes. |
| **G10b** | Peak and Mean Node Count by Mode & Tier | Grouped bar, 2 groups (compute, storage), 3 bars each. SEM + scatter dots. Two sub-panels: peak count and mean count. | Peak = worst-case provisioning. Mean = average overhead across the run. If cpu_only peaks at 8 storage nodes vs degradation_score's 5, but both mean ~3, the extra nodes are short-lived — the peak is alarming but the mean tells the real cost story. |

### 8.3 Diagnostic Graphs

| # | Graph | Type | What it shows |
|---|---|---|---|
| **G11** | Cross-Tier Spawn Contamination by Mode | Grouped bar, 2 groups (compute spawns during storage phases, storage spawns during compute phases), 3 bars each. SEM + scatter dots. | M9 visualized. Directly tests tier isolation: does cpu_only spawn compute nodes during storage_storm? Does it spawn storage nodes during compute_spike? If contamination is >20% in any mode, tier separation is compromised. |
| **G12** | Node Lifetime Distribution by Mode & Tier | Box plot per mode per tier, per-node lifetimes as scatter dots. | How long do spawned nodes live? If cpu_only spawns are short-lived (peer relief + cooldown kills them), the resource cost is lower than spawn count suggests. If degradation_score spawns live longer (fewer peers → less peer relief), the efficiency advantage narrows. |

### 8.4 Updated Graph Count

| Category | Graphs | Count |
|---|---|---|
| Detection Quality | G1, G1b, G2, G3 | 4 |
| Service Quality | G4, G5, G5b, G6, G7 | 5 |
| Provisioning Efficiency | G7b, G9 | 2 |
| Node Overhead | G10, G10b | 2 |
| Diagnostic | G8, G11, G12 | 3 |
| **Total** | | **16** |

---

## References

- [RQ3 v6 — Trigger Composition Characterization](rq3_v6.md) — measurement framework, M1–M10, G1–G12
- [RQ3 v6 — Experiment Setup Declaration](rq3_setup_v6.md) — canonical parameters
- [Experiment Plan v6](../../operation/testing/experiment/rq3_evaluation/v6/experiment_plan_v6.md) — implementation
- [RQ3 Cross-Mode Comparison Skill](../../../.github/skills/rq3-cross-mode-comparison/SKILL.md) — graph generation workflow (update v5→v6, add G7b–G12)
- [Divergence Calibration Results](../../operation/testing/experiment/rq3_evaluation/v5/calibration_results_v2.md) — calibration anchors
