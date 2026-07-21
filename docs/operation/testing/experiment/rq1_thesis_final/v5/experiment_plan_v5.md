# RQ1 v5 — Stress-Calibrated Pilot

**Status**: 📋 Planned · **Date**: 2026-07-20
**Predecessor**: [`experiment_plan_v4.md`](experiment_plan_v4.md) · [`results_v4.md`](results_v4.md)

## Intent

v4 proved that with CPU_SPAN=40, the telemetry delivery mode does not affect
user-visible outcomes — all 12 runs (Push, Poll-5s, Poll-12s, Poll-30s) had
1.0–2.2% timeout rates. However, v4 also showed that Poll-30s spawns **52% fewer**
compute nodes than Push (10.7 vs 22.7) and completes **46% fewer** requests in
compute_spike (97 vs 181 rps). The coordination gap exists at the control-plane
level but never crosses the threshold where it causes user-visible failure.

The v4 system has **headroom**: it only needs ~8 compute nodes to survive the
workload, and even Poll-30s' 11 nodes clears that bar. The spawn count gap
(23 vs 11) is invisible because both are above the survival threshold.

**v5 eliminates that headroom** so the spawn count difference becomes the
difference between surviving and failing.

Two independent stress mechanisms are piloted sequentially:

| Pilot | Mechanism | What it tests |
|-------|-----------|---------------|
| **A** | Compressed phases (180s→90s) | Poll-30s nodes arrive after the phase ends — the 90s minimum decision time + 14s provisioning means the node comes online at t≈104s, after the 90s phase. Poll-30s is "always a phase late." |
| **B** | Double clients (48→96) + raise MAX_DYNAMIC_COMPUTE | Doubles CPU demand AND removes the provisioning ceiling so Push can demonstrate its full spawning advantage. Poll-30s' fewer nodes + stale routing compound. |

Pilot A runs first. If it produces a clear signal (Poll-30s timeout rate > 2× Push),
the campaign expands Pilot A to all 4 modes at n=3. If Pilot A does not separate
the modes, Pilot B runs as fallback. If neither works, the stress hypothesis is
falsified and a different approach is needed.

## Hypothesis / Expected Outcome

1. **Pilot A (compressed phases)**: Poll-30s throughput substantially below
   Push because Poll-30s nodes arrive after the phase they were spawned for.
   The minimum decision time (3 polls × 30s = 90s) plus provisioning (~14s)
   means nodes come online at t≈104s — after a 90s phase ends. With cooldown
   (45s) preventing a second spawn, Poll-30s gets at most 1 spawn per phase,
   arriving too late. Push decides by t≈30-50s with the node online by
   t≈45-65s, providing 25-45s of relief within the phase.

2. **Pilot B (double clients + raised cap)**: Three mechanisms compound:
   - **#1 Scale-up gap**: Poll-30s spawns fewer nodes (blind spot delays
     detection). With `MAX_DYNAMIC_COMPUTE=12` (raised from 8), Push can
     demonstrate its full spawning capacity (~30-35 nodes) while Poll-30s
     remains blind-spot-limited (~15-18 nodes).
   - **#2 Stale routing**: Poll-30s VIP routing uses up to 30s-stale CPU
     data. Requests get routed to servers that were idle 30s ago but are
     now overloaded → high latency variance. At 96 clients, the load
     imbalance amplifies.
   - **#3 Scale-down lag**: Poll-30s holds nodes longer after load drops
     (slow to detect cooldown). At higher load, this wastes more resources.

3. **Spawn count gap persists**: Poll-30s spawns fewer compute nodes than
   Push regardless of which pilot runs — the blind spot is invariant.

## v4 Routing Staleness — Already Visible

**The coordination gap IS visible to users in v4 — just not in timeout rates.**
A latency variance analysis of v4's `service_pressure` endpoint in
compute_spike reveals:

| Mode | p50-p95 spread | vs Push |
|------|---------------|---------|
| Push | 0.48s | — |
| Poll-5s | 0.27s | 0.56× |
| Poll-12s | 0.78s | 1.63× |
| **Poll-30s** | **0.89s** | **1.86×** |

Poll-30s users experience nearly 2× higher p95 latency than Push users
on the same endpoint during the same phase. The p99 gap is even wider
(1.29–1.70s vs 0.62–0.99s). Some requests finish in 3ms; others take 1.7s.

**This is the signature of stale VIP routing** (mechanism #2 below):
the VIP routing WSM uses `_server_stats` refreshed only when telemetry
arrives. In Poll-30s, routing decisions use up to 30s-stale CPU data,
sending some requests to overloaded servers while idle servers sit unused.
The result is high latency variance, not high mean latency — exactly what
the data shows.

**v5 builds on this**: if routing staleness already produces 2× p95
latency at 48 clients, at 96 clients the effect should amplify. And if
`MAX_DYNAMIC_COMPUTE` is raised to let Push demonstrate its full spawning
capacity, the scale-up gap (mechanism #1) compounds with the routing
gap (mechanism #2).

## RQ Linkage

**Thesis RQ1**: How does telemetry delivery cadence affect reaction latency
and transient service quality during demand shifts?

**v5 contribution**: v4 showed the gap exists in spawn behavior but doesn't
hurt users — the system has too much headroom. v5 establishes the **boundary
condition**: at what stress level does the spawn gap become a service gap?

**Independent variable**: Telemetry mode (Push vs Poll-30s), crossed with
stress mechanism (compressed phases or double clients).

## New Metrics (replacing reaction latency)

The v4 breach-detector-based reaction latency metric is **retired** for v5.
It measured sliding-window accumulation time, not the coordination gap.
Three replacement metrics are introduced:

### M1 — Spawn Count (primary, existing)
Compute nodes spawned per run, from `node_lifecycle_timings.csv`.
**Measures**: Did the controller respond to load?
**Expectation**: Push > Poll-30s by ≥40%.

### M2 — Missed Opportunities (new)
Count of phases where the controller should have spawned but didn't.

**Definition**: A phase where ALL of the following hold:
1. Mean per-node CPU > 20% during the phase (genuine compute pressure; at
   CPU_SPAN=40 and CPU_FLOOR=10, 20% CPU contributes 0.15 to the degradation
   score — below the 0.18 first-spawn threshold alone, but combined with
   T_proc it indicates real load)
2. p95 per-node CPU > 40% (the load is concentrated, not just background)
3. Fewer than 2 compute spawns with `add_time` falling within the phase
   time bounds (controller didn't respond)

**Why 20%/40%?** The `SCALEUP_COMPUTE_BASE_THRESHOLD=0.18` with `W_CPU=0.60`
and `CPU_FLOOR=10, CPU_SPAN=40` means a node at 20% CPU contributes
degradation_score = 0.60 × (20-10)/40 = 0.15. This is below the 0.18
threshold alone, but with T_proc contribution it crosses. The p95 > 40%
condition ensures the load is concentrated on some nodes (not uniformly
low), which is what the scoring function's span is designed to detect.
These thresholds are intentionally slightly below the scoring trigger
point to capture "should have spawned" rather than "did spawn."

**Adaptive threshold note**: The controller's actual threshold escalates
with each dynamic node (BASE=0.18 + INCREMENT=0.10 per existing node).
M2 accounts for this by checking the controller's effective threshold at
the time of each window (from the controller env override + spawn count
at that window from `node_lifecycle_timings`). A phase with 2 existing
dynamic nodes has threshold=0.38 — CPU at 20% (score 0.15) would correctly
NOT trigger, and M2 should NOT flag it. The algorithm must track the
effective threshold per window, not assume a fixed 0.18.

**Source**: `per_node_stats.csv` (cpu_percent, phase) + `node_lifecycle_timings.csv`
(node_type=compute, add_time).
**Measures**: Did the controller fail to respond when it should have?
**Expectation**: Poll-30s missed opportunities > Push missed opportunities.

**Algorithm sketch** (for CLI implementation):
```python
for each high-load phase:
    cpu_samples = per_node_stats where phase == ph
    if mean(cpu_samples) > 20 AND p95(cpu_samples) > 40:
        spawns = count node_lifecycle_timings where node_type=compute
                 AND add_time within [phase_start, phase_end]
        if spawns < 2:
            missed += 1
```

### M3 — Time-to-Capacity (new)
For each high-load phase: time from phase start to when sufficient compute
nodes are online that local requests are handled without queueing.

**Definition**:
1. Partition `client_requests.csv` into 10s buckets aligned with
   `resource_stats.csv` sampling intervals (both use 10s windows).
2. For each bucket, identify **local requests**: `client_lan == target_region`.
   Exclude `feed_ranking` in phases where `cross_region_ratio > 0` (it is
   cross-region in those phases; in phases with `cross_region_ratio=0`,
   `feed_ranking` requests are local and should be included).
3. Compute p95 latency_s for local requests in that bucket.
4. The **capacity point** is the first bucket where p95 local latency < 0.5s
   AND `server_count` ≥ 2 (at least one dynamic node online).
5. **Time-to-capacity** = bucket_start_time − phase_start_time.
6. If no bucket in the phase reaches the capacity point, report as
   "not achieved within phase."

**Why p95 < 0.5s?** Local requests (client_lan == target_region) in v4
baseline phase have latency_s ≈ 0.003-0.04s. During high-load phases,
queueing at overloaded edge servers elevates local latency. When enough
compute nodes are online to absorb the load, local latency should return
to near-baseline. The 0.5s threshold is conservative — well above baseline
(~0.01s) but well below cross-region WAN RTT (~0.185s one-way).

**Source**: `resource_stats.csv` (server_count, timestamp) +
`client_requests.csv` (latency_s, phase, client_lan, target_region, endpoint).
**Measures**: How long did local users wait before the system caught up?
**Expectation**: Poll-30s time-to-capacity > Push time-to-capacity, and
Poll-30s more frequently reports "not achieved within phase."

**Algorithm sketch** (for CLI implementation):
```python
for each high-load phase:
    phase_start = phases_snapshot[phase].start_time
    for each 10s bucket in [phase_start, phase_start + duration]:
        local_reqs = client_requests where phase == ph
                     AND client_lan == target_region
                     AND endpoint != 'feed_ranking'
                     AND sent_at within bucket
        if count(local_reqs) >= 10:  # sufficient sample
            p95 = percentile(local_reqs.latency_s, 95)
            srv = resource_stats.server_count at bucket
            if p95 < 0.5 AND srv >= 2:
                time_to_capacity = bucket.start - phase_start
                break
    if not found:
        time_to_capacity = "not achieved"
```

### M4 — Throughput (existing, now primary)

Total requests completed per high-load phase. This is the **primary signal**
for the coordination gap — the system with fewer node-seconds of capacity
completes fewer requests.

**Definition**: For each high-load phase (storage_storm, tier1_hotspot,
reverse_hotspot, compute_spike), count all rows in `client_requests.csv`
where `phase == <phase_name>`. Report as both **total requests** and
**requests per second** (total / duration_s).

**Per-phase comparison table** (expected pattern from v4):

| Phase | Push (v4) | Poll-30s (v4) | Gap (v4) | v5 Pilot A expected |
|-------|-----------|---------------|----------|---------------------|
| storage_storm | ~7,000 reqs (29 rps) | ~6,400 reqs (27 rps) | −9% | Gap widens |
| tier1_hotspot | ~7,800 reqs (43 rps) | ~8,600 reqs (48 rps) | +10%* | Gap widens |
| reverse_hotspot | ~9,500 reqs (53 rps) | ~8,600 reqs (48 rps) | −9% | Gap widens |
| **compute_spike** | **~32,600 reqs (181 rps)** | **~17,500 reqs (97 rps)** | **−46%** | **Gap should persist or widen** |

> *tier1_hotspot reversed in v4 — Poll-30s completed more requests because
> nodes spawned during storage_storm were still online. This cross-phase
> carryover is expected and diagnostically useful.

**Success gate (C2 primary)**: Poll-30s throughput in compute_spike < 70%
of Push throughput (i.e., gap > 30%). This threshold is set below the
v4 gap of 46% to allow for run-to-run variance while still requiring a
meaningful separation.

**Source**: `client_requests.csv` (phase column). Phase durations from
`phases_snapshot.json`.

**Measures**: Did Poll-30s complete meaningfully fewer requests than Push?
A throughput gap without a corresponding timeout spike means the system
degraded gracefully (queueing) rather than failing — still a coordination
gap, just not a catastrophic one.

**Expectation**: Throughput gap should be largest in compute_spike (the
highest-intensity phase) and should widen in v5 relative to v4. The gap
quantifies "how much work was left undone because nodes arrived too late."

### M5 — Timeout Rate (existing, now the success gate)
Overall and per-phase timeout rate (latency_s ≥ 29.9s).
**Measures**: Did users experience failures?
**Success gate**: Poll-30s timeout rate > 2× Push timeout rate.

### M6 — Blind Spot Windows (new)
Quantifies the telemetry windows the controller **should have seen** but
didn't, and the load that went unanswered as a result.

**Concept**: An independent observer computes the degradation score for every
10s aggregation window using the same formula as the controller
(`W_CPU × clamp((cpu−FLOOR)/SPAN, 0, 1) + W_T_PROC × ...`).
Windows where score ≥ threshold are **breach windows** — the controller
should consider spawning. In Push mode, the controller receives every
window via ZMQ. In Poll mode, it only receives windows when it polls.

A **blind spot window** is a breach window that the controller never
consumed because no poll occurred during the interval that window was
available.

**Definition**:
1. Reconstruct all 10s telemetry windows from `per_node_stats.csv` and
   `resource_stats.csv` (both sampled at 10s intervals).
2. For each window, compute `degradation_score` using the controller's
   scoring formula with the parameters from `current_state_integrated.env`.
3. Determine the threshold at each window using the controller's sliding
   window logic (increments after each spawn, resets on cooldown).
4. A window is **breached** if score ≥ threshold.
5. Determine **consumed** windows from the controller's telemetry log
   (ZMQ delivery timestamps for Push, poll timestamps for Poll).
6. A **blind spot window** = breached AND NOT consumed.
7. For each blind spot window, record:
   - `window_end` timestamp
   - `degradation_score` and `threshold`
   - `cpu_percent` (mean and p95 of nodes in that window)
   - `request_count` in the following window (requests that could have
     been routed to a new node had the controller known)

**Aggregate metrics** — these are the **primary counts** to report per run:

| Count | Definition | Push (expected) | Poll-30s (expected) |
|-------|-----------|-----------------|---------------------|
| **Total windows** | All 10s telemetry windows in the run | ~144 (24 min ÷ 10s) | Same (independent observer) |
| **Breached windows** | Windows where score ≥ threshold | Same as Poll-30s* | Same as Push* |
| **Consumed windows** | Breached windows the controller received | ~100% of breached | ~33% of breached |
| **Blind spot windows** | Breached AND NOT consumed | **~0** | **~67% of breached** |
| **Blind spot rate** | Blind spot ÷ Breached | ≤2% (ZMQ is best-effort; allow ≤1 dropped window) | ~67% |
| **Requests in shadow** | Requests in the 10s window following each blind spot | ~0 | Substantial (quantified per-run) |

> *Same workload, same scoring formula — the independent observer computes
> identical breaches for both modes.

**Per-phase blind spot breakdown** — report for each high-load phase:

| Phase | Total windows | Breached | Consumed | Blind spots | Blind spot rate | Requests in shadow |
|-------|--------------|----------|----------|-------------|-----------------|-------------------|
| storage_storm | 12 (120s) | ? | ? | ? | ?% | ? |
| tier1_hotspot | 9 (90s) | ? | ? | ? | ?% | ? |
| reverse_hotspot | 9 (90s) | ? | ? | ? | ?% | ? |
| compute_spike | 9 (90s) | ? | ? | ? | ?% | ? |

The **blind spot rate** is the headline number: what fraction of "the
controller should have known about this overload" did it actually miss?
For Push this should be zero. For Poll-30s it should be substantial —
directly quantifying the coordination gap at the mechanism level.

**Requests in shadow** quantifies the impact: these are requests that
arrived while the controller was blind to overload. Some of them may have
timed out (captured by M7); others just experienced elevated latency.
Together, the blind spot rate + requests in shadow answer: "how many
windows did the controller miss, and how many users were affected?"

> *Same workload, same scoring formula — the independent observer computes
> the same breaches. Only consumption differs.

**Source**: `per_node_stats.csv` + `resource_stats.csv` (window reconstruction),
`controller_env_snapshot.env` (scoring parameters),
`controller_lan1.log`/`controller_lan2.log` (consumed window timestamps).

**Measures**: How many overload windows did the controller never see?
What was the load during those blind spots?

**Expectation**: Push has zero blind spot windows (blind spot rate = 0%).
Poll-30s misses ~67% of breached windows (blind spot rate ≈ 67%).
The requests-in-shadow count for Poll-30s should be substantial and
concentrated in high-load phases. **This is the most direct quantification
of the coordination gap**: X% of overload events went unseen by the
controller because of the delivery cadence.

> **Implementation note**: This requires parsing the controller log to
> extract telemetry consumption timestamps (ZMQ delivery or poll response).
> For Push mode, ZMQ delivery is per-window (every 10s). For Poll mode,
> the log should record each poll and the window_end of the summary returned.
> If the controller log does not currently record consumed window timestamps,
> a log enhancement is a prerequisite (see Prerequisites).

### M7 — Timeout Root Cause Classification (new)
Every timeout (latency_s ≥ 29.9s) is classified into a root cause category
using the system state at the time the request was in flight.

**Categories** (applied in precedence order — first match wins):

| # | Category | Definition | Detection |
|---|----------|-----------|-----------|
| 1 | **Capacity gap** | `server_count` was insufficient for instantaneous load; CPU on available nodes was high | `server_count` at (sent_at) < server_count needed for that window's rps (rps ÷ 8 rps/node, rounded up) AND p95 CPU > 40% |
| 2 | **Cold start** | Node was provisioned < 30s before the request; first requests hit cold caches | `node_lifecycle_timings` shows a compute node `add_time` within [sent_at − 30s, sent_at] |
| 3 | **Storage bound** | `storage_count` was insufficient; T_db was elevated | `storage_count` < 3 AND median T_db > 200ms in that 10s bucket |
| 4 | **WAN saturation** | Cross-region request where WAN RTT + queueing exceeded 30s | `client_lan != target_region` AND p95 cross-region latency in that 10s bucket > 25s |
| 5 | **Transient spike** | Isolated timeout; ≥ 90% of requests in the same 10s bucket succeeded | `success_rate` in same (phase, endpoint, 10s_bucket) ≥ 90% |
| 6 | **Unclassified** | Does not match any category above | Catch-all for pattern discovery |

**Output**: Per-run CSV `analysis/rq1_timeout_root_cause.csv` with columns:
`sent_at, phase, endpoint, client_lan, target_region, latency_s, category, server_count, storage_count, cpu_p95, t_db_median, note`

**Aggregate**: Per-mode stacked bar chart showing timeout composition
(capacity gap vs WAN saturation vs cold start vs storage bound vs transient).
If the coordination gap is real, Poll-30s should show a higher proportion of
**capacity gap** timeouts than Push.

**Source**: `client_requests.csv` (timeout events), `resource_stats.csv`
(server/storage count), `per_node_stats.csv` (CPU), `node_lifecycle_timings.csv`
(node add times).

**Measures**: Why did each timeout happen? Was it preventable with faster
spawning?

**Expectation**: In Push mode, timeouts (if any) should be dominated by WAN
saturation and transient spikes — the system had enough nodes but some
requests hit the 30s cap naturally. In Poll-30s, an additional category
should appear: **capacity gap** — requests that timed out because the
controller hadn't spawned enough nodes yet, directly attributable to the
blind spot.

> **v4 backport**: M6 and M7 can be applied retrospectively to the v4 data
> to validate the methodology before the v5 pilot. If v4 shows zero blind
> spot impact (consistent with the uniform timeout rates), that confirms
> the metrics are calibrated correctly and v4 genuinely had headroom. If
> v4 shows unexpected blind spot impact, it reveals hidden degradation
> that the timeout rate didn't capture — valuable in itself.

### M8 — Latency by Endpoint (new)

Overall p95 latency hides which part of the system is under stress. Breaking
latency down by endpoint reveals whether timeouts are caused by the compute
spawn gap (affecting compute-heavy endpoints) or by storage/WAN bottlenecks
(unaffected by faster compute spawning).

**Definition**: For each high-load phase, compute p50/p95/p99 latency_s
for each endpoint separately. Report as a heatmap table.

**Endpoints and what they stress**:

| Endpoint | Primary bottleneck | If degraded, indicates |
|----------|-------------------|----------------------|
| `service_pressure` | Compute CPU | Compute spawn gap (directly affected by blind spot) |
| `feed_ranking` | Compute CPU + cross-region DB | Combined compute + storage gap |
| `content_lookup` | Cross-region DB read | Storage count or WAN saturation |
| `content_update` | Local DB write | Storage I/O, not compute |
| `content_aggregate` | Local DB aggregation | Storage I/O, not compute |

**Expected pattern if coordination gap is real**:

| Endpoint | Push p95 (expected) | Poll-30s p95 (expected) | Interpretation |
|----------|--------------------|------------------------|----------------|
| `service_pressure` | < 1s | **Elevated (> 2s)** | Compute nodes arrived late → queueing on fewer nodes |
| `feed_ranking` | 7–9s (cross-region) | **Elevated (> 10s)** | Fewer compute nodes + cross-region delay compound |
| `content_lookup` | 8–9s (cross-region) | Similar to Push | Storage-driven, not affected by compute spawn gap |
| `content_update` | < 0.1s | Similar to Push | Local writes, unaffected |
| `content_aggregate` | < 0.1s | Similar to Push | Local reads, unaffected |

The **differential**: if Poll-30s latency is elevated specifically on
`service_pressure` and `feed_ranking` (compute-heavy endpoints) but NOT on
`content_lookup`/`content_update`/`content_aggregate` (storage-bound
endpoints), the degradation is directly attributable to the compute spawn
gap — the blind spot mechanism. If ALL endpoints are equally elevated, the
bottleneck is elsewhere (VM capacity, OVS bridge, WAN).

**Source**: `client_requests.csv` (endpoint, latency_s, phase).

**Measures**: Which endpoints suffer under Poll-30s? Is the degradation
compute-specific (confirming the blind spot mechanism) or generalized?

**Expectation**: Poll-30s shows elevated latency on `service_pressure` and
`feed_ranking` relative to Push, but similar latency on storage-bound
endpoints. This endpoint-specific degradation pattern is the signature of
the compute spawn gap.\n\n> **v4 finding**: The p50-p95 latency **spread** on `service_pressure`\n> is already 1.86× higher for Poll-30s than Push (0.89s vs 0.48s) — the\n> routing staleness signal. At 96 clients (Pilot B), this spread should\n> widen further as stale CPU data causes more load imbalance. The spread\n> (not just absolute p95) is the expected primary signal for Pilot B.

### M9 — Recovery Lag (new)

The coordination gap is symmetric: if Poll-30s is slow to detect overload,
it should also be slow to detect that load has dropped. After the final
high-load phase (`demand_drop`), how long does each mode hold onto
dynamically-spawned nodes?

**Definition**:
1. Identify `demand_drop` phase start time from `phases_snapshot.json`.
2. Track `server_count` from `resource_stats.csv` from demand_drop start
   until it stabilizes at ≤ 2 (the baseline level before any spawning).
3. **Recovery lag** = time from demand_drop start to first 10s window where
   `server_count` ≤ 2 AND remains ≤ 2 for at least 3 consecutive windows
   (60s of stability — the cooldown window).
4. Also report: **peak server_count** during demand_drop (how many nodes
   were still online when load dropped) and **node-seconds wasted** (area
   under the server_count curve above baseline during demand_drop).

**Why this matters**: If Poll-30s holds nodes longer because it doesn't
poll frequently enough to detect the load drop, it wastes resources.
Combined with M3 (time-to-capacity on the way up) and M9 (recovery lag on
the way down), the full asymmetry of the coordination gap is captured:
Poll-30s is **slow to ramp up AND slow to ramp down**.

**Source**: `resource_stats.csv` (server_count, phase), `phases_snapshot.json`
(phase start times).

**Measures**: After the crisis ends, how long until the system returns to
baseline? Is Poll-30s slower to scale down?

**Expectation**: Poll-30s recovery lag > Push recovery lag. Poll-30s may
hold 2–3 extra nodes for 60–120s longer than Push because the controller
doesn't poll frequently enough to observe that CPU has dropped below the
scale-down threshold. This is the scale-**down** side of the blind spot.

| Metric | Push (expected) | Poll-30s (expected) |
|--------|-----------------|---------------------|
| Recovery lag | ~60–120s | **> 120s** |
| Peak server_count in demand_drop | 2–3 | **3–4** |
| Node-seconds wasted | Lower | **Higher** |

## Independent Variable & Held-Constant Set

| Parameter | v4 Value | v5 Pilot A | v5 Pilot B | Notes |
|-----------|----------|------------|------------|-------|
| **Telemetry mode** | Push / Poll-30s | Push / Poll-30s | Push / Poll-30s | Independent variable |
| **Phase durations** | 60–300s | **30–150s (halved)** | 60–300s | Pilot A stress mechanism |
| **CLIENTS** | 48 | 48 | **96** | Pilot B stress mechanism |
| `SCALEUP_CPU_SPAN` | 40 | 40 | 40 | Held constant |
| `WAN_RTT_MS` | 185 | 185 | 185 | Held constant |
| `CURL_MAX_TIME` | 30 | 30 | 30 | Held constant |
| `VIP_HARD_TIMEOUT` | 60 | 60 | 60 | Held constant |
| `DEVICES` | 6000 | 6000 | 6000 | Held constant |
| `NODES` | 100 | 100 | 100 | Held constant |
| `STORAGE_CPUS` | 0.08 | 0.08 | 0.08 | Held constant |
| `RANDOM_SEED` | 42 | 42 | 42 | Held constant |
| `DATA_SEED` | 42 | 42 | 42 | Held constant |
| Controller env | `current_state_integrated.env` | Same | Same | Held constant |
| `MAX_DYNAMIC_COMPUTE` | 8 (concurrent per LAN) | 8 | **12** | Pilot B raises cap to let Push demonstrate full spawning advantage. v4's 22.7 compute spawns is **cumulative**; the cap of 8 is **concurrent**. At 96 clients, ~24 nodes needed — cap of 8 would ceiling both modes. Raised to 12 per LAN (24 total) to remove the provisioning ceiling. |
| `SCALEUP_COMPUTE_COOLDOWN_S` | 45 | 45 | 45 | Held constant. Critical for Pilot A: prevents second spawn within same 90s phase. |
| `SCALEUP_COMPUTE_REQUIRED` | 3 | 3 | 3 | Held constant. Minimum hits in 5-window sliding window. |
| `SCALEUP_COMPUTE_BASE_THRESHOLD` | 0.18 | 0.18 | 0.18 | Held constant. First-spawn threshold. |
| `SCALEUP_CPU_FLOOR` | 10 | 10 | 10 | Held constant. CPU% below this contributes zero score. |
| `SCALEUP_W_CPU` | 0.60 | 0.60 | 0.60 | Held constant. Weight of CPU in degradation score. |
| `cleanup.sh -r` between runs | Yes | Yes | Yes | Held constant |

## Pilot A — Compressed Phases

### Rationale

In v4, the sliding window for compute scale-up requires 3 hits out of 5
windows (`SCALEUP_COMPUTE_REQUIRED=3`, `SCALEUP_COMPUTE_WINDOW_SIZE=5`).
In Push (10 s/window) the minimum decision time is 3 windows × 10 s = 30 s
(if the first 3 windows all show degradation). In Poll-30s (30 s/poll) the
minimum is 3 polls × 30 s = 90 s.

At v4's 180s phases, Push decides by t≈30-50s and the node is online by
t≈45-65s (provisioning ~14s), providing ~115-135s of relief within the
phase. Poll-30s decides by t≈90s and the node is online by t≈105s,
providing ~75s of relief. Both fit — Poll-30s is slower but still helps.

At 90s phases, the dynamic changes:

```text
Phase:              |-------- 90s --------|
Push:   [decide@40s] [online@55s]  |---35s relief---|
Poll30:              [poll1]  [poll2]  [decide@90s]  [online@105s]
                                          ↑ spawn decision       ↑ node ready
                                          └── at phase boundary  └── AFTER phase ends
```

**The harm mechanism is not "can't decide" — it's "always a phase late."**
Poll-30s CAN accumulate 3 consecutive above-threshold polls within 90s and
trigger a spawn at the phase boundary. But provisioning (~14s) means the
node comes online at t≈105s — after the phase ends. The node provides zero
relief for the phase it was spawned for.

Push, seeing windows every 10s, decides by t≈30-50s and the node is online
by t≈45-65s — providing 25-45s of relief within the same phase.

**Compound effect across sequential high-load phases**: With compressed
phases (storage_storm→tier1_hotspot→reverse_hotspot→compute_spike all at
90-120s), Poll-30s nodes arrive one phase late. A node spawned for
storage_storm helps tier1_hotspot; a node for tier1_hotspot helps
reverse_hotspot. Poll-30s is perpetually behind the demand curve, while
Push stays ahead.

**Cooldown amplifies the gap**: `SCALEUP_COMPUTE_COOLDOWN_S=45` means a
second spawn cannot be evaluated until t=135s (90+45) — well after the
90s phase. Push can evaluate a second spawn at t≈85s (40+45) — still
within the phase. Poll-30s gets at most 1 spawn decision per compressed
phase; Push gets 2.

**Throughput difference, not timeout rate, is the expected signal**:
Compressed phases generate exactly the same instantaneous load (same
rate_per_client, same client count) as v4, but for half the duration.
Total requests per phase are halved — the denominator for timeout rate
shrinks. With fewer total requests, timeout rate becomes noisier.
The cleaner signal is **throughput** (M4): Poll-30s should complete
fewer total requests per phase because it has fewer node-seconds of
capacity available within the phase window.

The compressed phases.json halves all durations:

| Phase | v4 Duration | v5 Pilot A |
|-------|------------|------------|
| baseline | 60s | 30s |
| storage_storm | 240s | 120s |
| tier1_hotspot | 180s | 90s |
| inter_hotspot_cooldown | 300s | 150s |
| reverse_hotspot | 180s | 90s |
| compute_spike | 180s | 90s |
| demand_drop | 300s | 150s |

**Total run duration**: ~24 min → ~12 min.

### Run Matrix

| # | Label | `TELEMETRY_SOURCE` | `POLL_INTERVAL_S` | Phases | CLIENTS |
|---|-------|---------------------|--------------------|--------|---------|
| A1 | `rq1_v5_pilotA_push_1` | `zmq` | — | `phases.json` (durations halved) | 48 |
| A2 | `rq1_v5_pilotA_push_2` | `zmq` | — | `phases.json` (durations halved) | 48 |
| A3 | `rq1_v5_pilotA_poll30_1` | `poll` | 30 | `phases.json` (durations halved) | 48 |
| A4 | `rq1_v5_pilotA_poll30_2` | `poll` | 30 | `phases.json` (durations halved) | 48 |

**Total: 4 runs.** Run order: A1→A2→A3→A4. ~2h campaign (4 × 12 min + cleanup).

### Pilot A Success Gate

**Primary gate (throughput)**: Poll-30s throughput in compute_spike (M4)
< 70% of Push throughput. This is the expected signal — Poll-30s nodes
arrive too late to process the full phase workload.

**Secondary gate (timeout rate)**: Poll-30s timeout rate > 2× Push timeout
rate. This may not trigger even if the mechanism works, because timeout
rate has a smaller denominator (fewer total requests in compressed phases)
and the system may degrade gracefully (queueing) rather than failing
(timeouts).

**n=2 power note**: With n=2, the statistical power is low. v4's Poll-30s
σ=0.49pp on timeout rate means a 2× difference (~1.5pp absolute) is within
sampling noise. The throughput gate (M4) is expected to be more robust
because throughput is a count, not a ratio, and the v4 gap was 46%.

- **If pass (either gate)**: Expand to full campaign — all 4 modes (Push,
  Poll-5s, Poll-12s, Poll-30s) × n=3 with compressed phases. 12 runs total.
  Expansion run order: randomize within each mode block.
- **If fail (both gates)**: Proceed to Pilot B. Restore canonical phases.json
  (verify with Gate 6: duration_s = 60, 240, 180, 300, 180, 180, 300).

## Pilot B — Double Clients (Fallback)

### Rationale

Pilot A showed that compressing phases caps BOTH modes equally — the phase
duration, not telemetry cadence, becomes the bottleneck. Pilot B takes the
opposite approach: canonical 180s phases so Push can spawn freely, then
increases demand to expose the gap.

Three mechanisms compound in Pilot B:

**#1 Scale-up gap (primary)**: Poll-30s' blind spot means it spawns fewer
nodes. At 48 clients (v4), Push spawns 22.7 compute nodes and Poll-30s
spawns 10.7 — a 52% gap. At 96 clients, with `MAX_DYNAMIC_COMPUTE=12`,
Push should spawn 30-35 nodes (cumulative) while Poll-30s remains limited
to 15-18 by the blind spot.

**#2 Stale routing (amplified)**: v4 already shows Poll-30s has 1.86×
higher p50-p95 latency spread on `service_pressure` — the signature of
stale VIP routing. At 96 clients, the load imbalance from stale CPU data
amplifies: more requests hit overloaded servers, widening the variance gap.

**#3 Scale-down lag (secondary)**: Poll-30s holds nodes longer after load
drops. At higher client counts, wasted node-seconds increase.

At 48 clients, v4 compute_spike generated ~181 rps. Each compute node handles
~8 rps. Poll-30s spawns 11 nodes → ~88 rps capacity. The 2:1 demand:capacity
ratio causes graceful slowdown (visible in latency variance), not failure.

At 96 clients, demand roughly doubles to ~360 rps against Poll-30s' ~120 rps
capacity (15 nodes × 8 rps) — a 3:1 ratio. With stale routing sending
disproportionate traffic to already-overloaded nodes, some servers hit 100%
CPU while others idle. Queues build, timeouts spike.

### Run Matrix

| # | Label | `TELEMETRY_SOURCE` | `POLL_INTERVAL_S` | Phases | CLIENTS |
|---|-------|---------------------|--------------------|--------|---------|
| B1 | `rq1_v5_pilotB_push_1` | `zmq` | — | `phases.json` (canonical durations) | **96** |
| B2 | `rq1_v5_pilotB_push_2` | `zmq` | — | `phases.json` (canonical durations) | **96** |
| B3 | `rq1_v5_pilotB_poll30_1` | `poll` | 30 | `phases.json` (canonical durations) | **96** |
| B4 | `rq1_v5_pilotB_poll30_2` | `poll` | 30 | `phases.json` (canonical durations) | **96** |

**Total: 4 runs.** Run order: B1→B2→B3→B4. ~2.5h campaign (4 × 28 min + cleanup).

> **Note**: Pilot B uses `MAX_DYNAMIC_COMPUTE=12` (raised from 8). Edit
> `current_state_integrated.env` before Pilot B and restore after. The run
> folder's `controller_env_snapshot.env` captures the variant used. Gate 8
> verifies the change.

### Pilot B Success Gate

- **Pass**: Poll-30s timeout rate (μ of n=2) > 2× Push timeout rate (μ of n=2)
- **If pass**: Expand to full campaign — all 4 modes × n=3 at 96 clients. 12 runs total.
- **If fail**: Both stress mechanisms failed to separate the modes. The coordination gap, while real at the control-plane level (52% fewer spawns), does not cause user-visible degradation even under substantial stress. This is a valid bounding result for the thesis.

## Run Configuration

### Pilot A — Per-Run Invocation

```bash
# 1. Edit phases.json: halve all duration_s values (see table above)
#    Save the result as source/scripts/testing/phases.json
#    (The canonical phases.json is edited in place per the project convention)

# 2. Launch
ssh -o ServerAliveInterval=60 cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=<LABEL> \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=185 CLIENTS=48 DEVICES=6000 NODES=100 STORAGE_CPUS=0.08 \
  CURL_MAX_TIME=30 RANDOM_SEED=42 DATA_SEED=42 \
  > /tmp/<LABEL>.log 2>&1 &"

# 3. Wait for completion (~12 min)

# 4. Post-run analysis (see Post-Run Workflow below)

# 5. Cleanup + reboot
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo bash source/scripts/cleanup.sh -r"
ssh cloud-vm "sudo reboot"
```

### Pilot B — Per-Run Invocation

Same as Pilot A except `CLIENTS=96`, `MAX_DYNAMIC_COMPUTE=12`, and canonical `phases.json` (unmodified durations).

### Mode-Specific Flags

| Mode | Extra `make` flags |
|------|--------------------|
| Push | *(none — zmq is default)* |
| Poll-30s | `TELEMETRY_SOURCE=poll POLL_INTERVAL_S=30` |

### Pre-Run Verification Gates

Same 4 gates as v4 plan:
1. `SCALEUP_CPU_SPAN=40` in env override
2. Controller loads `cpu_span=40` at runtime
3. `SKIP_SEED ?= 1` in Makefile
4. `POLL_INTERVAL_S=30` at runtime (poll mode only). **Updated for v5**: the grep pattern must use `*rq1_v5_pilot*_poll30*` (not the v4 `*rq1_v4_poll30*` prefix).

Plus three new gates:
5. **Phase durations (Pilot A)**: After editing phases.json, verify compressed durations:
```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  python3 -c \"import json; [print(p['name'], p['duration_s']) for p in json.load(open('source/scripts/testing/phases.json'))['phases']]\""
# Expected: baseline=30, storage_storm=120, tier1_hotspot=90, ...
```

6. **Phase durations (Pilot B, after Pilot A)**: If Pilot A fails and Pilot B runs, verify canonical durations are restored:
```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  python3 -c \"import json; [print(p['name'], p['duration_s']) for p in json.load(open('source/scripts/testing/phases.json'))['phases']]\""
# Expected: baseline=60, storage_storm=240, tier1_hotspot=180, ...
```

7. **Pilot B VM pre-flight**: Before running Pilot B at 96 clients, run a 60s smoke test:
```bash
# Launch a 60s baseline-only run at 96 clients, abort after 120s
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  timeout 120 sudo -n make -C source/scripts setup_network create_clients run_experiment \
  RUN_LABEL=rq1_v5_smoke_test \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=185 CLIENTS=96 DEVICES=6000 NODES=100 STORAGE_CPUS=0.08 \
  CURL_MAX_TIME=30 RANDOM_SEED=42 DATA_SEED=42"
# Monitor: if static node CPU > 95% or OVS bridge CPU > 80%, the VM is bottlenecked.
# If bottlenecked, fall back to 72 clients instead of 96.
```

8. **MAX_DYNAMIC_COMPUTE (Pilot B)**: Verify the raised cap is in effect:
```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  grep 'MAX_DYNAMIC_COMPUTE' source/scripts/testing/controller_env_overrides/current_state_integrated.env"
# Expected: MAX_DYNAMIC_COMPUTE=12
```

### Post-Run Workflow (per run)

```bash
RUN_DIR="source/scripts/testing/metrics/<timestamp>_<label>"

# Fix ownership
sudo chown -R testop:testop "$RUN_DIR"

# Parse controller logs → elasticity events
python3 source/scripts/tools/parse_elasticity_logs.py \
  "$RUN_DIR/controller_lan1.log" "$RUN_DIR/controller_lan2.log" \
  -o "$RUN_DIR/elasticity_events.csv" \
  --timings-output "$RUN_DIR/node_lifecycle_timings.csv"

# Statistics
python3 source/scripts/tools/metrics_stats.py "$RUN_DIR" --by-phase --by-lan --by-endpoint
python3 source/scripts/tools/metrics_stats.py -r "$RUN_DIR/resource_stats.csv" --by-phase --by-network

# RQ1 analysis CLIs (existing)
python3 -m source.scripts.testing.analysis.rq1.cli.timings --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.rq1.cli.decision_quality --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.rq1.cli.overhead --run-dir "$RUN_DIR"

# NEW: Missed opportunities analysis (M2)
python3 -m source.scripts.testing.analysis.rq1.cli.missed_opportunities --run-dir "$RUN_DIR"

# NEW: Time-to-capacity analysis (M3)
python3 -m source.scripts.testing.analysis.rq1.cli.time_to_capacity --run-dir "$RUN_DIR"

# NEW: Blind spot window analysis (M6) — REQUIRES controller logs
# This MUST run before log cleanup (parses telemetry consumption timestamps)
python3 -m source.scripts.testing.analysis.rq1.cli.blind_spot_windows --run-dir "$RUN_DIR"

# NEW: Timeout root cause classification (M7)
python3 -m source.scripts.testing.analysis.rq1.cli.timeout_root_cause --run-dir "$RUN_DIR"

# NEW: Latency by endpoint breakdown (M8)
python3 -m source.scripts.testing.analysis.rq1.cli.endpoint_latency --run-dir "$RUN_DIR"

# NEW: Recovery lag analysis (M9)
python3 -m source.scripts.testing.analysis.rq1.cli.recovery_lag --run-dir "$RUN_DIR"

# Cleanup large artifacts — only after M6 completes (M6 needs controller logs)
rm "$RUN_DIR/controller_lan1.log" "$RUN_DIR/controller_lan2.log"
rm -rf "$RUN_DIR/service_logs/"
```

> **Note**: All six new CLIs are implemented and verified against v4 data.
> M3 (time_to_capacity) reports "not_achieved" for v4's 180s phases — the
> 0.5s local p95 threshold may need calibration for Pilot A's 90s phases.
>
> **Critical ordering**: `cli.blind_spot_windows` (M6) reads consumed window
> timestamps from `resource_stats_debug.csv` (produced by `parse_elasticity_logs.py`).
> `parse_elasticity_logs.py` must run first, then M6, then log cleanup.
> No controller log enhancement is needed — the existing pipeline already
> captures consumed window timestamps.

## Focus & Evidence

| Artifact | What it shows | Priority | Metric |
|----------|---------------|----------|--------|
| `client_requests.csv` | Per-phase timeout rate, throughput (rps) | **Primary** | M4, M5 |
| `node_lifecycle_timings.csv` | Compute/storage spawn counts | **Primary** | M1 |
| `per_node_stats.csv` + `node_lifecycle_timings.csv` | Phases with CPU pressure but no spawns | **Primary** | M2 (new) |
| `resource_stats.csv` + `client_requests.csv` | Time from phase start to capacity | **Primary** | M3 (new) |
| `per_node_stats.csv` + `controller_lan*.log` | Windows breached but not consumed by controller | **Primary** | M6 (new) |
| `client_requests.csv` + `resource_stats.csv` + `per_node_stats.csv` | Root cause of every timeout | **Primary** | M7 (new) |
| `client_requests.csv` | Per-endpoint latency breakdown (p50/p95/p99) | **Primary** | M8 (new) |
| `resource_stats.csv` + `phases_snapshot.json` | Time from demand_drop to baseline server_count | **Primary** | M9 (new) |
| `elasticity_events.csv` | Scaling event count and timing | Secondary | — |
| `analysis/rq1_staleness.csv` | Information age per mode | Secondary | — |
| `analysis/rq1_overhead.csv` | Controller CPU/RAM | Secondary | — |
| `phases_snapshot.json` | Phase order, durations, request mix | Reference | — |

## Metrics & Success Criteria

| # | Criterion | Expectation |
|---|-----------|-------------|
| C1 | All 4 pilot runs complete | 4/4 → idle, zero controller tracebacks |
| C2 | **Pilot success gate (primary)** | Poll-30s throughput in compute_spike (M4) < 70% of Push throughput |
| C2b | **Pilot success gate (secondary)** | Poll-30s timeout rate (μ) > 2× Push timeout rate (μ) |
| C3 | Spawn count gap (M1) | Push compute spawns > Poll-30s compute spawns (≥40% gap) |
| C4 | Missed opportunities (M2) | Poll-30s missed ≥ 2 phases with CPU > 20% and no spawns |
| C5 | Time-to-capacity gap (M3) | Poll-30s time-to-capacity > Push for high-load phases |
| C6 | Throughput gap (M4) | Poll-30s throughput in compute_spike < 70% of Push throughput (gap > 30%). Report absolute gap (requests) and relative gap (%). Also report per-phase throughput for all high-load phases. |
| C7 | Staleness step-function | Push ~0s, Poll-30s ~10s (window-gated, unchanged) |
| C8 | All 4 mechanisms exercise | Storage, compute, Tier 1 selective sync, reserve activation |
| C9 | Blind spot windows (M6) | Push blind spot rate ≤ 2% (ZMQ is best-effort; ≤1 dropped window acceptable). Poll-30s blind spot rate > 0% with explicit counts: total windows, breached, consumed, blind spots, blind spot rate, and requests in shadow. Blind spots should concentrate in high-load phases. |
| C10 | Timeout root cause (M7) | Every timeout classified. Poll-30s shows "capacity gap" timeouts; Push timeouts (if any) are WAN saturation or transient. Report per-category counts and percentages. |
| C11 | Endpoint-specific degradation (M8) | Poll-30s latency elevated on compute-heavy endpoints (service_pressure, feed_ranking) but NOT on storage-bound endpoints (content_lookup, content_update, content_aggregate). Report per-endpoint p50/p95/p99 per phase. |
| C12 | Recovery lag (M9) | Poll-30s recovery lag > Push recovery lag. Poll-30s holds dynamically-spawned nodes longer after load drops. Report recovery lag (seconds), peak server_count in demand_drop, and node-seconds wasted. |

## Pilot Decision Logic

```
Pilot A (compressed phases, 4 runs)
    │
    ├── C2/C2b PASS (throughput gap OR timeout gap)
    │       │
    │       └── Expand Pilot A to full campaign:
    │           12 runs (4 modes × n=3) with compressed phases
    │
    └── C2/C2b FAIL
            │
            ├── Restore canonical phases.json (verify Gate 6)
            ├── Run Pilot B (96 clients, 4 runs)
            │       │
            │       ├── C2/C2b PASS
            │       │       └── Expand Pilot B to full campaign:
            │       │           12 runs (4 modes × n=3) at 96 clients
            │       │
            │       └── C2/C2b FAIL
            │               └── Both mechanisms failed.
            │                   The coordination gap does not cause
            │                   user-visible failure under tested stress.
            │                   Document as bounding result.
```

## Prerequisites (Blockers)

| # | Item | Status |
|---|------|--------|
| 1 | Compressed `phases.json` | **Manual edit** before Pilot A. Verify with Gate 5. Restore after Pilot A; verify with Gate 6. |
| 2 | `cli.missed_opportunities` — M2 analysis | ✅ **Implemented**. Verified against v4 data. |
| 3 | `cli.time_to_capacity` — M3 analysis | ✅ **Implemented**. 0.5s threshold may need calibration for Pilot A (v4 phases are 180s and p95 local latency never dropped below 0.5s; 90s phases should show sharper recovery). |
| 4 | `cli.blind_spot_windows` — M6 analysis | ✅ **Implemented**. No controller log enhancement needed — uses existing `resource_stats_debug.csv` (produced by `parse_elasticity_logs.py`). Verified against v4: Push 0% blind spot, Poll-5s 0%, Poll-12s 18-25%, Poll-30s 53-58%. |
| 5 | `cli.timeout_root_cause` — M7 analysis | ✅ **Implemented**. Backported to v4: 0% capacity_gap timeouts across all 12 runs (72-77% storage_bound, 16-29% transient_spike). Confirms v4 headroom interpretation. |
| 6 | `cli.endpoint_latency` — M8 analysis | ✅ **Implemented**. Verified against v4 data. |
| 7 | `cli.recovery_lag` — M9 analysis | ✅ **Implemented**. Verified against v4 data. |
| 8 | VM capacity for 96 clients (Pilot B) | **Verify with pre-flight** (Gate 7). If VM CPU saturates, fall back to 72 clients. |
| 9 | `MAX_DYNAMIC_COMPUTE=12` for Pilot B | **Edit `current_state_integrated.env`** before Pilot B. Verify with Gate 8. Restore to 8 after Pilot B. |

> **Note on prerequisite 1**: The project convention is to edit `phases.json`
> in place, never create `phases_<variant>.json` duplicates. The run folder's
`phases_snapshot.json` captures the variant used. After Pilot A, restore
the canonical durations. Gate 5 verifies compression; Gate 6 verifies
restoration. If the operator forgets restoration, Pilot B will run with
wrong durations — Gate 6 is the safety check.
>
> **Note on prerequisites 2-5**: The algorithm sketches in M2, M3, M6, and M7
provide enough detail for implementation. M7 can be backported to v4 data
immediately (no new CLIs needed for v4 — manual CSV analysis suffices for
validation). M6 requires controller log parsing for consumed window timestamps;
if the controller does not currently log telemetry consumption events, a log
enhancement is needed before M6 can be computed. For the pilot (n=4), M2, M3,
and M7 can be computed manually if CLIs are not ready. The CLIs are required
for the full 12-run campaign.

> **v4 backport recommendation**: Run M7 (timeout root cause) on the v4 data
> before the v5 pilot. This validates the classification methodology and may
> reveal whether v4's 1-2% timeouts were WAN saturation (expected) or early
> signs of capacity gaps (would change the v4 interpretation).

## Validity Threats & Limitations

| Threat | Mitigation |
|--------|------------|
| n=2 per mode | Low statistical power. The primary success gate uses **throughput** (M4, a count metric) rather than timeout rate (a ratio). Throughput differences of 30%+ were observed in v4 (46% gap) and are less susceptible to small-sample noise than timeout rates (σ=0.49pp on a ~1.5% base). If both gates fail, the pilot is inconclusive, not a proof of absence. |
| Pilot A: Poll-30s may still trigger within 90s | The minimum decision time for Poll-30s is 3 consecutive above-threshold polls = 90s. If load is intense enough that all 3 polls trigger, the spawn decision fires at t=90s. But provisioning (~14s) means the node arrives at t=104s — after the 90s phase. The mechanism is "node arrives too late," not "controller can't decide." The cooldown (45s) prevents a second spawn within the phase. |
| Pilot A: Push may also fail to provide relief in 90s | Push's minimum decision time is 3 windows × 10s = 30s + 14s provisioning = 44s. With cooldown of 45s, Push can trigger a second spawn at t=75s (30+45) with the node online at t=89s — barely within the 90s phase. Push may also struggle. If both modes show similar throughput, the phases are too short for ANY mode to matter — a valid bounding result. |
| Pilot A: total requests halved reduces timeout count | The denominator for timeout rate shrinks. Mitigation: use throughput (M4, total requests completed) as the primary gate, not timeout rate. Throughput measures absolute work done, not a ratio. |
| Pilot B: VM becomes bottleneck at 96 clients | Pre-flight smoke test (Gate 7) runs 60s of baseline at 96 clients. If static node CPU > 95% or OVS bridge CPU > 80%, fall back to 72 clients. The fallback still increases demand by 50% (72/48) and may be sufficient to expose the gap. |
| Blocked run order | Push runs first in both pilots. If the VM's performance drifts, the mode effect is confounded with time. Accepted as a limitation for the pilot. The full campaign (if expanded) will run all Push runs first to minimize env override changes, then Poll-5s, Poll-12s, Poll-30s. |
| `phases.json` edit/restore risk | Manual edit of the canonical phases file between pilots. Mitigation: Gate 5 verifies compression before Pilot A; Gate 6 verifies restoration before Pilot B. The run folder's `phases_snapshot.json` provides an immutable record. |
| New analysis CLIs not yet implemented | Six CLIs (M2, M3, M6, M7, M8, M9) specified with algorithm sketches. If delayed, M2, M3, M7, M8, M9 can be computed manually for the pilot (n=4 runs) from existing CSVs. M6 requires controller logs and cannot be manual. CLIs required for full 12-run campaign. |
| Poll-phase alignment jitter | The Poll-30s cycle starts at controller boot, not at phase start. The first poll within a phase can occur anywhere from t=0s to t=29s. This ±15s jitter is 17% of a 90s phase — it materially affects whether 2 or 3 polls land within the phase. Mitigation: report actual poll timestamps relative to phase starts. If jitter explains anomalous results, synchronize the poll cycle for the full campaign. |
| MAX_DYNAMIC_COMPUTE=12 still caps Push at high load | At 96 clients × 2.0 rps = 192 rps of service_pressure. If each node handles ~8 rps, ~24 nodes are needed. The cap of 12/LAN (24 total) matches this requirement. Push at 30-35 cumulative spawns with 12 concurrent should be sufficient. Poll-30s at 15-18 cumulative with 12 concurrent has headroom in the cap — the blind spot, not the cap, is the binding constraint. |
| Pilot B infeasibility | If Pilot A fails AND the VM cannot handle even 72 clients, the campaign dead-ends. Contingency: document the bounding result — "the coordination gap exists (52% fewer spawns) but does not cause user-visible harm even under 2× phase compression. VM capacity prevents testing higher absolute load." This is a valid thesis result (the gap is real but bounded). |

## Artifact Contract

Same as v4 plan, plus new analysis outputs:

| New artifact | Location | Metric |
|--------------|----------|--------|
| Missed opportunities CSV | `<run_dir>/analysis/rq1_missed_opportunities.csv` | M2 |
| Time-to-capacity CSV | `<run_dir>/analysis/rq1_time_to_capacity.csv` | M3 |
| Blind spot windows CSV | `<run_dir>/analysis/rq1_blind_spot_windows.csv` | M6 |
| Timeout root cause CSV | `<run_dir>/analysis/rq1_timeout_root_cause.csv` | M7 |
| Endpoint latency CSV | `<run_dir>/analysis/rq1_endpoint_latency.csv` | M8 |
| Recovery lag CSV | `<run_dir>/analysis/rq1_recovery_lag.csv` | M9 |

Standard run-folder layout from `docs/operation/testing/testing_overview.md`
applies, with controller logs deleted after `elasticity_events.csv` and
`node_lifecycle_timings.csv` are generated.

Graphs archived to `docs/operation/testing/experiment/rq1_thesis_final/graphs/v5_pilot/`.

## Changelog

| Date | Change |
|------|--------|
| 2026-07-20 | v5 pilot plan created. Two sequential pilots: A (compressed phases) and B (96 clients). n=2 per mode. New metrics M1-M9 with reaction latency retired. Six new analysis CLIs specified. Success gate uses throughput (M4) as primary, timeout rate (M5) as secondary. Pilot decision logic with fallback and VM pre-flight (Gate 7). |
| 2026-07-20 | **Review corrections** (Reviewer agent): Fixed Pilot A mechanism — changed from "150s sliding window cannot complete" to "90s minimum decision + 14s provisioning = node arrives after phase ends, cooldown prevents second spawn." Added cooldown and threshold parameters to held-constant table. Switched primary success gate from timeout rate to throughput (more robust with compressed phases' smaller denominator). Added M2/M3 algorithm sketches. Added Pilot B VM pre-flight smoke test (Gate 7) with 72-client fallback. Added phases.json restoration verification gate (Gate 6). Fixed v4→v5 label prefix in Gate 4. Clarified MAX_DYNAMIC_COMPUTE as concurrent cap vs cumulative spawn count. Added Pilot B infeasibility contingency. Fixed phases.json naming in run matrix tables. |
| 2026-07-20 | **Added M6 and M7**: Blind Spot Windows and Timeout Root Cause Classification. Both directly measure the coordination gap's mechanism and impact. |
| 2026-07-20 | **Added M8 and M9**: Latency by Endpoint (per-endpoint p50/p95/p99 heatmap to isolate compute-specific degradation) and Recovery Lag (time from demand_drop to baseline server_count — the scale-down side of the blind spot). M8 and M9 require only existing CSVs, no controller log dependency. Can be backported to v4 immediately. Added C11 and C12 criteria. Prerequisites now 8 items, post-run workflow has 6 new CLIs. |
| 2026-07-20 | **All CLIs implemented and v4 backport complete**: Six CLIs implemented and verified. M6 backport: Push 0% blind spot, Poll-5s 0%, Poll-12s 18-25%, Poll-30s 53-58%. M7 backport: 0% capacity_gap timeouts in all 12 v4 runs (72-77% storage_bound, 16-29% transient_spike) — confirms v4 headroom interpretation. No controller log enhancement needed for M6 (existing `resource_stats_debug.csv` already has consumed timestamps). Updated Intent, Hypothesis, Prerequisites, and Post-Run notes with corrected Pilot A mechanism and implementation status. |
| 2026-07-20 | **Pilot A executed and analyzed**: Both success gates failed (C2 throughput ratio 122%, C2b timeout rates identical at ~1.3%). Compressed phases capped both modes equally — Push spawned only 5 compute nodes (vs 23 in v4), Poll-30s spawned 4. Mechanism confirmed (M6: 80% blind spot rate for Poll-30s) but invisible to users. Cross-phase carryover dominated. Proceeding to Pilot B. |
| 2026-07-20 | **Plan refined with v4 routing staleness finding and mechanisms #1-3**: v4 latency variance analysis shows Poll-30s has 1.86× higher p50-p95 spread on service_pressure — routing staleness IS already visible at 48 clients. Pilot B now raises MAX_DYNAMIC_COMPUTE to 12 (from 8) to remove the provisioning ceiling. Three compounding mechanisms documented: #1 scale-up gap, #2 stale VIP routing, #3 scale-down lag. Hypothesis updated to expect latency variance gap (not just timeout gap) as the primary user-visible signal. |
| 2026-07-20 | **Pilot B executed and analyzed**: Both C2 gates FAIL (throughput 80% vs <70% threshold; timeout 1.4× vs >2× threshold). Spawn gap confirmed at 41% (C3 PASS). Blind spot rate 64% for Poll-30s vs 0% for Push (C9 PASS). Zero capacity_gap timeouts (M7). Latency variance 1.8× wider for Poll-30s (C11 PASS). M3 non-discriminating at 96 clients (all "not_achieved"). M9 recovery lag similar across modes. **Bounding result**: coordination gap exists and is measurable at the mechanism level (64% blind spot, 41% fewer spawns) but does not cause catastrophic user-visible failure. System degrades gracefully through queueing. Documented in [`results_v5.md`](results_v5.md). |
