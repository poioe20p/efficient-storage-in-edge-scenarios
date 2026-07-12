# RQ2 Results — Routing-Awareness Coordination Gap

**Experiment**: RQ2 Evaluation  
**Date**: 2026-07-06 (runs) / 2026-07-07 (analysis)  
**Plan**: [`experiment_plan.md`](./experiment_plan.md)  
**Graphs**: [`graphs/20260707_campaign_analysis/`](./graphs/20260707_campaign_analysis/)

---

## Run Timeline

| Run | Date | Mode | Status | Events (LAN1/LAN2) |
|-----|------|------|:------:|--------------------|
| `rq2_th_1` | 2026-07-06 17:18 | topology_host | ✅ | 291 / 301 |
| `rq2_th_2` | 2026-07-06 18:18 | topology_host | ✅ | 222 / 257 |
| `rq2_th_3` | 2026-07-06 19:00 | topology_host | ✅ | 261 / 261 |
| `rq2_ss_1` | 2026-07-06 19:42 | topology_slowstart | ✅ | 262 / 276 |
| `rq2_ss_2` | 2026-07-06 20:24 | topology_slowstart | ✅ | 265 / 271 |
| `rq2_ss_3` | 2026-07-06 21:05 | topology_slowstart | ✅ | 260 / 255 |
| `rq2_tl_1` | 2026-07-06 21:46 | topology_lifecycle | ✅ | 268 / 271 |
| `rq2_tl_2` | 2026-07-06 22:28 | topology_lifecycle | ✅ | 265 / 264 |
| `rq2_tl_3` | 2026-07-06 23:10 | topology_lifecycle | ✅ | 253 / 231 |

**All 9 runs at**: CLIENTS=32, RANDOM_SEED=42, rate=4.0, WAN_RTT_MS=50, SS_ENABLED=0.

---

## Experiment Summary

Three routing-plane awareness modes compared under identical workload:

| Mode | When routing becomes aware of new backend | Mechanism |
|------|-------------------------------------------|-----------|
| `topology_host` | Immediately — unknown stats treated as 0.0 (best-case); all backends tie at cost 0.0, round-robin distributes evenly | Round-robin fair-share; no ramp, no warm lease, no backend readiness concept |
| `topology_slowstart` | At discovery (first telemetry window, 0–10 s post-spawn) | Invisible (penalty 1.0) until discovery, then graduated ramp |
| `topology_lifecycle` | At spawn time (atomic with pool registration) | Warm lease with bounded priority window (30–45 s) |

**What changed**: Only `BACKEND_SELECTION_POLICY`. Workload, scaling thresholds, telemetry (push), topology, and WSM weights held constant across all 9 runs.

**Key finding**: The experiment tests two timing dimensions simultaneously. The **coordination gap** — the delay between spawn and routing-plane awareness — is measurable through initial load share (how much traffic a new backend receives immediately) and time-to-first-traffic (how long until it receives any traffic). The **readiness gap** — the mismatch between when traffic arrives and when the backend is warm enough to serve it efficiently — proves equally consequential: modes that align traffic with warm-up (slowstart, lifecycle) achieve 7 ms p50 non-stress, while host's 5–10 s mismatch produces 200 ms. Redistribution-to-equilibrium time proved unmeasurable under continuous stress because the architecture precludes steady-state load shares by design.

---

## Graph Explanations

### Graph 1 — Initial Load Share

> **What fraction of VIP-routed traffic does a single newly-spawned backend capture in its first telemetry window?**

Each bar shows the per-mode mean of per-run means. Black dots are per-replicate values (3 runs per mode). The y-axis is percentage (0–100%).

**Reading**: `topology_lifecycle` backends capture 73% of traffic immediately (warm lease priority short-circuits the WSM). `topology_slowstart` gets 55% (invisible until discovery, then ramp begins). `topology_host` gets only 30% (unknown stats → no WSM advantage).

**Thesis meaning**: The warm lease delivers **2.5× more immediate traffic** than cold-start. This is the coordination gap in the routing plane quantified as traffic allocation — a lifecycle backend does real work from t=0, while a host backend waits.

**Statistical confidence**: Cohen's d = 3.69 (Large). 3 replicates sufficient.

---

### Graph 2 — Time-to-First-Traffic (TTFT)

> **How many seconds after spawn does a new backend receive its first request?**

Each bar is the per-mode median TTFT. Black dots are per-replicate medians. Lower is better.

**Reading**: `topology_lifecycle` median = 40 s (warm lease routes traffic from the first telemetry window). `topology_slowstart` median = 71 s (backend invisible during discovery gap → waits for next telemetry window). `topology_host` median = 51 s but per-replicate dots show extreme variance: one run at 251 s, another at 35 s — round-robin tie-breaking is fast when the counter aligns, slow when it doesn't.

**Thesis meaning**: The warm lease cuts TTFT nearly in half compared to the separated-LB simulation (40 s vs 71 s). The discovery gap in slowstart forces backends to wait an extra full telemetry window before receiving any traffic. Host is unpredictable — the round-robin counter state at spawn time determines whether the backend wins the first cycle.

**Statistical confidence**: Lifecycle vs Slowstart d = 0.87 (Medium–Large). Host within-mode variance prevents reliable conclusion against host.

---

### Graph 3 — Latency Percentiles (p50 / p95 / p99)

> **What latency do users experience under each routing mode, aggregated across all phases?**

Grouped bar chart: blue = median (p50), red = p95, dark = p99. All requests from all runs per mode.

**Reading**: `topology_host` p50 = 317 ms — **2.3× worse** than `topology_slowstart` (140 ms) and `topology_lifecycle` (144 ms). However, this aggregate masks phase dependence: host's penalty is concentrated in **non-stress phases on lan1** (200 ms vs 7 ms for other modes), where cold backends serve traffic before DB connections and caches warm. During stress phases, all three modes converge (~200–600 ms p50) because MongoDB I/O dominates. p95 latency is ~2500 ms across all modes — indistinguishable.

**Thesis meaning**: `topology_host`'s latency penalty comes from the mismatch between immediate traffic arrival (round-robin fair-share) and backend warm-up time. `topology_slowstart` achieves the best latency because its discovery delay aligns traffic arrival (~10 s post-spawn) with warm-up completion. `topology_lifecycle` routes traffic immediately but concentrated volume accelerates cache population, matching slowstart's latency. Tail latency is storage-bound regardless of routing policy.

**Statistical confidence** (Cohen's d):
- Host vs Slowstart p50: d = 2.16 (Large) — **conclusive**
- Slowstart vs Lifecycle p50: d = −0.21 (Small) — **indistinguishable**
- All p95 comparisons: d < 0.22 (Small) — **indistinguishable**

---

### Graph 3b — p95 Latency: Stress vs Non-Stress Phases

> **Does the routing mode affect tail latency differently under load vs at rest?**

Orange bars = stress phases (`storage_storm` + `compute_spike`, rate=4.0). Green bars = non-stress phases (baseline, cooldown, demand_drop, rate=1.0).

**Reading**: Stress p95 is ~2600 ms across all modes — the workload dominates. Non-stress p95 is ~350–1650 ms, with `topology_host` notably worse (1646 ms) than `topology_slowstart` (361 ms) and `topology_lifecycle` (360 ms). Even at low load, host's cold-start behavior degrades tail latency.

**Thesis meaning**: The routing policy matters most at low load (where cold backends have no stress load to mask warm-up latency) and becomes indistinguishable at high load (where storage operations dominate all modes equally).

---

### Graph 4 — Cumulative Load at Spawn

> **How many total requests does a new backend serve across its first telemetry window?**

Bar chart with per-replicate dots. Measures the *volume* of immediate work, complementing Graph 1's *share* metric.

**Reading**: `topology_host` backends serve ~3360 requests in their first window, `topology_slowstart` ~2310, `topology_lifecycle` ~2830. Host serves the most absolute requests because it triggers more spawn events (18 total vs 8 for lifecycle), creating a larger total request pool — not because of traffic concentration. The round-robin tie-breaking distributes traffic evenly among all backends.

**Thesis meaning**: Initial share (Graph 1) and cumulative load (Graph 4) tell different stories. Lifecycle gives each new backend a large slice of the pie (73% share). Host gives each backend a small slice (30%) of a larger pie (more total requests due to more spawn events). Slowstart has the lowest absolute load because capacity sits idle during the discovery gap.

---

### Graph 5 — Coordination Gap (Initial Share Difference)

> **How much immediate traffic is gained or lost by switching routing policies?**

Pairwise bar chart showing the difference in initial load share between modes. Positive bars = the second mode gets more traffic. Negative bars = the second mode gets less.

**Reading**:
- **Slowstart vs Lifecycle = −18 percentage points**: Slowstart loses 18 pp of traffic vs Lifecycle. This IS the coordination gap — traffic that sits idle during the discovery window because the routing plane doesn't know the backend exists.
- **Lifecycle vs Host = +43 pp**: Warm lease delivers 43 pp more traffic than cold-start.
- **Slowstart vs Host = +25 pp**: Even with the discovery delay, slowstart beats cold-start.

**Thesis meaning**: This graph is the RQ2 equivalent of RQ1's breach-detection penalty. Just as RQ1 quantified how much monitoring information is lost during polling blind spots, Graph 5 quantifies how much routing capacity is wasted during the discovery gap. The warm lease recaptures that capacity by making routing aware at spawn time.

---

## Overall Conclusions

### What the experiment proved (conclusive, d ≥ 1.2)

1. **Warm lease gives new backends 2.5× the immediate traffic** of cold-start (73% vs 30% initial share). The coordination gap in routing is real and large.

2. **`topology_host` has elevated median latency during non-stress phases** (200 ms on lan1 vs 7 ms for other modes), caused by cold backends receiving traffic via round-robin before DB connections and caches warm. During stress phases, latency converges across all modes. The aggregate 2.3× headline is driven by lan1 non-stress phases, not a uniform degradation.

3. **`topology_slowstart` and `topology_lifecycle` have indistinguishable per-request latency** (7 ms p50 non-stress, ~140 ms aggregate). The discovery gap and warm lease differ in traffic-allocation timing (TTFT, initial share), not per-request speed once traffic flows. Slowstart achieves the best latency by aligning traffic arrival with backend warm-up completion; lifecycle matches it because concentrated traffic accelerates cache warming.

### What the experiment could not prove (d < 0.5, 3 reps insufficient)

4. **Tail latency (p95) differences between modes are statistical noise**. All three converge at ~2500 ms because storage operations dominate the tail regardless of routing policy. More replicates would be needed to detect the small true difference, if one exists.

### What was discovered during the experiment

5. **Redistribution-to-equilibrium is not measurable in a continuously-scaling edge system**. Backends spawn mid-overload and are removed during cooldown before reaching steady-state load shares. The architecture precludes equilibrium — this is not a failure of the experiment but a property of the system. The appropriate metrics are **initial load share** (immediate allocation) and **time-to-first-traffic** (discovery gap).

6. **`topology_host` is inherently unpredictable**. Its per-replicate variance is always the highest across all metrics. Round-robin tie-breaking depends on the counter state at spawn time — sometimes the new backend wins the first cycle (0.2 s TTFT), sometimes it waits many cycles (251 s TTFT).

7. **Round-robin tie-breaking, not herd behaviour, drives `topology_host` traffic distribution.** All backends tie at WSM cost 0.0 (unknown stats → best-case), so the round-robin counter distributes traffic evenly across the pool. The ~30% initial share is approximately 1/N fair share. The latency penalty comes from cold backends serving requests before warming up, not from overloading.

8. **The 30-second client timeout affects ~1–3% of requests across ALL modes**, with per-run (not per-mode) variation. The 0.00% failure rate reflects that timeouts are counted as slow successes, not errors. Timeout rate is workload-driven, not routing-mode-driven.

---

## References

- **Experiment plan**: [`experiment_plan.md`](./experiment_plan.md)
- **RQ2 definition**: [`docs/research_questions/rq2.md`](../../../research_questions/rq2.md)
- **Analysis CLI**: `source/scripts/testing/analysis/rq2/cli_rq2_redistribution.py`
- **Graph generation**: `source/scripts/testing/analysis/rq2/regenerate_rq2_graphs.py`
- **TTFT extraction**: `source/scripts/testing/analysis/rq2/extract_ttft.py`
- **Effect size analysis**: `source/scripts/testing/analysis/rq2/effect_sizes.py`
