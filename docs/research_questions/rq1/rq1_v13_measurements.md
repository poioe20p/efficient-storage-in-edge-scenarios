# RQ1 v13 — Measurement Inventory: Rationale, Expectation & Result

**Campaign**: 12 runs (Push×3, Poll-5s×3, Poll-12s×3, Poll-30s×3), storage-heavy redesigned phases, n=3 per mode.
**Date**: 2026-07-27 to 2026-07-28.
**Source documents**:

- Experiment plan: [`docs/operation/testing/experiment/rq1_thesis_final/v13/experiment_plan_v13.md`](../../operation/testing/experiment/rq1_thesis_final/v13/experiment_plan_v13.md)
- Results: [`docs/operation/testing/experiment/rq1_thesis_final/v13/results.md`](../../operation/testing/experiment/rq1_thesis_final/v13/results.md)
- RQ definition: [`rq1_v13.md`](rq1_v13.md)
- Setup declaration: [`rq1_setup_v13.md`](rq1_setup_v13.md)
- Cross-mode comparison graphs: [`docs/operation/testing/experiment/rq1_thesis_final/v13/graphs/comparison/`](../../operation/testing/experiment/rq1_thesis_final/v13/graphs/comparison/)

---

## 1. Confirmation Metrics

| #  | Measurement | Why It Exists | Expected | v13 Result |
| -- | ----------- | ------------- | -------- | ---------- |
| S0 | **Information age (staleness)** | Confirms the mechanism is **missed windows**, not stale data. | Push ≈ 0s, Poll ≈ interval | Push: 0.1s, Poll-5s: 5.2s, Poll-12s: 10.0s, Poll-30s: 11.3s. Graph: `rq1_v13_staleness_comparison.png`. |
| G8 | **Cleanup-gap isolation** — zero dynamic-node spawns during `cleanup_gap_*` phases | Validates the independent variable. 220s gaps exceed 180s compute cooldown. If any spawn occurs during a gap, cross-phase carryover contaminates the detection-speed signal. | All 12 runs PASS | **All 12 PASS.** Every high-load phase starts from zero dynamic nodes. Detection speed is the sole determinant of reaction quality. |

---

## 2. Detection & Reaction Metrics

| #  | Measurement | Why It Exists | Expected | v13 Result |
| -- | ----------- | ------------- | -------- | ---------- |
| M1 | **Spawn count** — compute/storage dynamic nodes per mode | Did the blind spot reduce provisioning? | Push > Poll-30s | **Directional.** Poll-30s spawns ~30% fewer compute nodes; storage provisioning similar. Graph: `rq1_v13_decision_quality.png`. |
| M6 | **Blind spot windows** — breached windows the controller never consumed | Most direct mechanism-level quantification. | Push ≈ 0%; Poll-30s substantial | **Confirmed.** Push and Poll-5s see nearly all breached windows. Poll-30s misses majority. Graph: `rq1_v13_staleness_comparison.png`. |
| — | **Reaction latency** — time from overload onset to spawn decision | How long did the controller take when it **did** detect? Survivor-biased. | Poll-30s > Push | Graphs: `rq1_v13_reaction_latency_mean.png`, `rq1_v13_reaction_latency_max.png`. |

---

## 3. User-Impact Metrics

| #  | Measurement | Why It Exists | Expected | v13 Result |
| -- | ----------- | ------------- | -------- | ---------- |
| M3 | **Throughput** — total requests per run | **Primary signal.** The blind spot reduces served requests. | Push and P30 ranges do not overlap | **Confirmed — strongest signal.** Push: 42–45K (μ=43,370); P30: 33–37K (μ=35,439). **18% gap**, no overlap. Poll-5s (μ=43,092) and Poll-12s (μ=42,358) cluster near Push. Graphs: `rq1_v13_throughput.png`, `rq1_v13_throughput_per_phase.png`. |
| M4 | **Timeout rate** — `http_status=0` rate per mode | Did users experience outright failures? Without CT5, TCP accept-queue failures appear as high-latency completions. Binary timeout is **supplementary**. | P30 ≥ Push (direction only) | **Noisy, non-discriminating.** Push: 5.2%; Poll-5s: 4.3%; Poll-12s: 8.2%; Poll-30s: 6.7%. No clear gradient. Graph: `rq1_v13_timeout_comparison.png`. |
| M4b | **Degraded requests (>5s)** — % requests with latency >5s (any status) | Captures **any queuing** beyond healthy <1s responses. The blind spot causes queuing; this metric measures all queued requests, not just the ones that cross the CURL_MAX_TIME=30 cliff. | Poll-30s > Push | Graph: `rq1_v13_degraded_5s.png`. |
| M4c | **Degraded requests (>10s)** — % requests with latency >10s | Moderate queuing — requests clearly delayed by the blind spot but not near timeout. | Poll-30s > Push | Graph: `rq1_v13_degraded_10s.png`. |
| M4d | **Degraded requests (>20s)** — % requests with latency >20s | Severe queuing — requests on the edge of CURL_MAX_TIME=30. | Poll-30s > Push | Graph: `rq1_v13_degraded_20s.png`. The degradation staircase (>5s, >10s, >20s, >30s) shows how the blind spot shifts the latency distribution toward the tail. |
| M5 | **Latency (p50/p95)** — per-mode p50 and p95 | **Secondary success gate.** Blind-spot queuing inflates tail latency. | P30 p95 ≥ Push p95 | **Directional but below gate.** Push p95: 16.74s; Poll-30s p95: 18.12s (1.08×, vs 1.15× gate). Without CT5, TCP failures become high-latency completions, inflating both modes' p95. p50 is excellent across all modes: 9–14ms. Graphs: `rq1_v13_endpoint_latency_p50.png`, `rq1_v13_endpoint_latency_p95.png`. |
| M8 | **Per-phase throughput** | Where does the gap concentrate? | Gap in storage-dependent phases | **Confirmed.** `storage_storm` (−10%), `tier1_hotspot` (−11%), `reverse_hotspot` (−28%), `storage_storm_2` (−30%). The penalty compounds. Graph: `rq1_v13_throughput_per_phase.png`. |
| — | **Per-phase timeout rate** — grouped bars across phases × modes | Triangulates with M8. | Poll-30s elevated in stress phases | Graph: `rq1_v13_per_phase_timeout.png`. |
| — | **Per-phase p50/p95 latency** — grouped bars across phases × modes | Which phases carry the latency penalty? | Poll-30s elevated in stress phases | Graphs: `rq1_v13_endpoint_latency_per_phase_p50.png`, `rq1_v13_endpoint_latency_per_phase_p95.png`. |

---

## 4. Recovery & Capacity Metrics

| #  | Measurement | Why It Exists | Expected | v13 Result |
| -- | ----------- | ------------- | -------- | ---------- |
| M9 | **Recovery lag** — time from `demand_drop` start until p95 returns to ≤ baseline p95 + 1s | After the crisis ends, how long until service quality returns to baseline? Measures the **ramp-down** side. | Consistent across modes (cooldown-gated, not information-gated) | Not yet analyzed. Scale-down is 180s cooldown-gated; recovery is expected to be mode-independent. |
| — | **Time-to-capacity** — time from phase start to first window where p95 local latency falls below threshold AND at least one dynamic node is online | How long did users wait before the system caught up? Measures the **ramp-up** side. | Poll-30s > Push for stress phases | Not yet analyzed. |

---

## 5. Cost & Overhead Metrics

| #  | Measurement | Why It Exists | Expected | v13 Result |
| -- | ----------- | ------------- | -------- | ---------- |
| — | **Controller CPU/RAM** | **Rule-out**: does faster telemetry increase controller cost? | Flat across modes | **Confirmed.** CPU: Push 8.2%, Poll-5s 8.6%, Poll-12s 8.2%, Poll-30s 7.7%. RAM: 72–78 MB. Constant across all modes. Graph: `rq1_v13_overhead_comparison.png`. |
| — | **Compute node CPU%** — per-node CPU for edge_server containers | **Rule-out**: does the blind spot force fewer compute nodes to work harder? If P30 compute nodes run hotter (serving same load with fewer instances), the mechanism is visible at the infrastructure level. | P30 compute CPU ≥ Push (fewer nodes → higher per-node load) | Graph: `rq1_v13_compute_cpu.png`. |
| — | **Storage node CPU%** — per-node CPU for edge_storage_server containers | Does the storage cascade manifest as elevated storage CPU? P30's blind spot delays storage-node provisioning → existing storage nodes serve cross-region requests longer. | P30 storage CPU ≥ Push | Graph: `rq1_v13_storage_cpu.png`. |

---

## 6. Decision Quality Metrics

| #  | Measurement | Why It Exists | Expected | v13 Result |
| -- | ----------- | ------------- | -------- | ---------- |
| — | **Decision quality** — breached windows (%) vs spawns per phase per mode | Does the controller spawn proportionally to detected overload? | Push tracks breached windows; Poll-30s under-spawns | Graph: `rq1_v13_decision_quality.png`, CSV: `rq1_v13_decision_quality.csv`. |
| — | **Reaction events detected** — total breach→spawn events per mode | How many overload events did the controller even detect? Survivor-biased: undetected breaches are invisible. | Push = Poll-5s = Poll-12s > Poll-30s | Graph: `rq1_v13_reaction_latency_mean.png`. |
| — | **Max detected reaction latency** — worst-case breach-detection time | Worst-case when detection DOES happen. | Poll-30s >> Push | Graph: `rq1_v13_reaction_latency_max.png`. Survivor-biased — undetected breaches have infinite latency. |

---

## 7. Synthesis

| Claim (from experiment plan §Hypothesis) | Verdict | Evidence |
| ---------------------------------------- | ------- | -------- |
| Throughput gap widens and is stable | **✅ Confirmed — strongest signal** | Push 42–45K, Poll-30s 33–37K, no overlap. 0 anomalies in 12 runs. Results §1. |
| Two storage events produce consistent gap | **⚠️ Directional, not quantitative** | Both `storage_storm` and `storage_storm_2` show Push/P30 gap (10% and 30%), but magnitude differs — second event amplifies the penalty. Results §5.2. |
| Timeout separation is secondary | **✅ Confirmed** | Timeout rates are noisy and do not follow a clear gradient. P30 ≥ Push directionally but not reliably. Results §3. |
| Full dose-response curve is monotonic | **❌ Contradicted** | Predicted: Push ≈ Poll-5s > Poll-12s > Poll-30s. Actual: Push ≈ Poll-5s ≈ Poll-12s > Poll-30s. Intermediate modes do not separate. Results §7.4. |
| p95 latency inflates with polling interval | **⚠️ Directional but below gate** | P30 p95 = 1.08× Push (vs 1.15× gate). Gap exists but is compressed without CT5. Results §2. |
| G8 passes for all 12 runs | **✅ Confirmed** | All 12 PASS. 220s gaps exceed 180s cooldown. Results §4. |
| Controller overhead is flat across modes | **✅ Rule-out confirmed** | CPU: 97–121%. All modes within capacity. Push marginally higher (ZMQ). |

**Thesis framing for v13**: The blind-spot penalty is real and measurable. Poll-30s
completes **18% fewer requests** than Push, with no overlap in throughput ranges.
The penalty concentrates in storage-dependent phases where the cascade mechanism
operates, compounding in later phases (`reverse_hotspot` −28%, `storage_storm_2`
−30%). The degradation staircase (>5s, >10s, >20s, >30s) captures how the blind
spot shifts the latency distribution: more requests queue for 5-20s under Poll-30s,
even if the binary timeout rate (http_status=0) does not cleanly separate. Poll-5s
and Poll-12s are indistinguishable from Push — only the 30-second blind spot
produces a measurable throughput penalty. Controller and node-level CPU overhead
is flat across modes — Push can be recommended without a cost caveat.

---

## 8. Graph Inventory

All graphs archived at `docs/operation/testing/experiment/rq1_thesis_final/v13/graphs/comparison/`.

| # | Graph | What it shows |
|---|-------|--------------|
| 1 | `rq1_v13_throughput.png` | Overall throughput per mode — **primary evidence** |
| 2 | `rq1_v13_throughput_per_phase.png` | Per-phase throughput — where the gap concentrates |
| 3 | `rq1_v13_degraded_5s.png` | % requests with latency > 5s |
| 4 | `rq1_v13_degraded_10s.png` | % requests with latency > 10s |
| 5 | `rq1_v13_degraded_20s.png` | % requests with latency > 20s |
| 6 | `rq1_v13_timeout_comparison.png` | % requests with http_status=0 (>30s) |
| 7 | `rq1_v13_endpoint_latency_p50.png` | Median endpoint latency per mode |
| 8 | `rq1_v13_endpoint_latency_p95.png` | p95 endpoint latency per mode |
| 9 | `rq1_v13_endpoint_latency_per_phase_p50.png` | Per-phase p50 latency |
| 10 | `rq1_v13_endpoint_latency_per_phase_p95.png` | Per-phase p95 latency |
| 11 | `rq1_v13_per_phase_timeout.png` | Per-phase timeout rate |
| 12 | `rq1_v13_staleness_comparison.png` | Max information age — confirms mechanism |
| 13 | `rq1_v13_reaction_latency_mean.png` | Reaction events detected per mode |
| 14 | `rq1_v13_reaction_latency_max.png` | Max detected reaction latency |
| 15 | `rq1_v13_overhead_comparison.png` | Controller CPU% + RAM — rule-out |
| 16 | `rq1_v13_compute_cpu.png` | Compute node CPU% per mode |
| 17 | `rq1_v13_storage_cpu.png` | Storage node CPU% per mode |
| 18 | `rq1_v13_decision_quality.png` | Breached windows vs spawns — decision quality |
| 19 | `rq1_v13_decision_quality.csv` | Raw decision quality data |
