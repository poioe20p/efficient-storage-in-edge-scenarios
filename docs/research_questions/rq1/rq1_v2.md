# RQ1 v2 — Telemetry Delivery Cadence and Control Quality

**Thesis pillar**: Telemetry Freshness (the delivery link)
**Status**: V3 evaluated (12 runs, n=3 per mode) → V4 evaluated (12 runs, n=3 per mode, CPU_SPAN=40, scoring-corrected) → **V5 pilot in progress** (stress-calibrated, Push vs Poll-30s only)
**Previous versions**: [`rq1.md`](rq1.md) (v3/v4 measurement framework and results)
**V4 results**: [`docs/operation/testing/experiment/rq1_thesis_final/results_v4.md`](../operation/testing/experiment/rq1_thesis_final/results_v4.md)
**V5 plan**: [`docs/operation/testing/experiment/rq1_thesis_final/experiment_plan_v5.md`](../operation/testing/experiment/rq1_thesis_final/experiment_plan_v5.md)
**Thesis map**: [`tese/miscelineous/system_to_thesis_map_rq_v2.md`](../../tese/miscelineous/system_to_thesis_map_rq_v2.md)

---

## 1. Thesis Context

This thesis investigates whether collapsing three traditionally separated
control-plane concerns — **information acquisition** (monitoring), **backend
selection** (load balancing), and **infrastructure adaptation** (auto-scaling)
— into a single SDN controller process eliminates coordination gaps that
degrade service quality during demand shifts.

In a separated architecture (e.g., Kubernetes: Prometheus → AlertManager →
HPA → kube-proxy), each handoff between components introduces delay. The
monitoring system scrapes on a fixed interval, the alarm system evaluates
thresholds, the auto-scaler provisions infrastructure, and the load balancer
eventually discovers the new backend — all through independent control loops
with no shared state. Total coordination latency often reaches 30–120 s, even
though the container boots in 10 s.

In the proposed architecture, the SDN controller (OS-Ken/Ryu) consumes
telemetry directly (Thread 2), evaluates thresholds in the same process,
spawns containers (Thread 3), and routes traffic to the new backend via
OpenFlow (Thread 1) — all from shared data structures with no propagation
delay between components.

RQ1 isolates the **information acquisition** dimension of this unification.

---

## 2. Research Question

> How does telemetry delivery cadence — aggregator-paced push versus
> controller-paced polling at three intervals — affect reaction latency
> and transient service quality during demand shifts in a stateful edge
> system?

---

## 3. What Is Being Investigated

The system aggregates raw edge-server telemetry into 10-second summary
windows. The controller can receive these summaries in two ways:

- **Push** (ZMQ): the aggregator publishes each summary at window close.
  The controller sees every window within milliseconds of its completion.
- **Poll** (HTTP): the controller fetches the latest cached summary from
  the aggregator at a configurable interval (5 s, 12 s, or 30 s).

The aggregator's HTTP cache always holds the freshest completed summary —
when the controller polls, the data it retrieves is fresh regardless of
polling interval. **Data staleness at consumption time is not the mechanism
that delays the controller's response.**

The mechanism is **missed windows** — the controller simply does not see
telemetry between polls:

```text
Push mode:  controller sees every window (10 s cadence)
            ──[W10]──[W20]──[W30]──[W40]──
            ✅       ✅       ✅       ✅

Poll-30s:   controller sees 1 of every 3 windows
            ──[W10]──[W20]──[W30]──[W40]──
            ❌       ❌       ✅       ❌
            ↑────── blind spot ──────↑
```

If overload first appears at W15, a push-mode controller learns about it
within milliseconds of that window closing. A poll-30s controller does not
learn about it until it polls at t=30 — a 15-second **blind spot** during
which the system is overloaded but no action is taken.

**Compound effect — sliding windows amplify the penalty.** The controller's
scale-up decision uses sliding windows defined in *window counts* (5 windows,
3 hits). In Push mode (10 s/window), this covers ~50 s of wall-clock time.
In Poll-30s (30 s/poll), the same 5 windows span ~150 s — a 3× compound
effect. The experiment does not isolate pure delivery cadence; it measures
the **compound coordination gap** that real separated architectures
experience: wasted windows (blind spot) × sustained degradation required
(wall-clock duration of the evaluation window).

---

## 4. Why This Question Exists

### 4.1 Purpose

RQ1 tests whether the **delivery mechanism** — how telemetry reaches the
controller — measurably affects the controller's ability to respond to
demand shifts. If the blind spot between polls delays reactions and
degrades service quality, then the coordination gap that separated
architectures impose is not merely a theoretical concern but a measurable
source of harm. If it does not, then the thesis can bound the problem:
polling staleness matters only above some cadence threshold.

### 4.2 What Each Condition Encodes

Each mode tests a specific claim about the coordination gap.

| Condition | Delivery | Blind spot | Encodes |
|---|---|---|---|
| **Push** | ZMQ at window close | None | The unified architecture: telemetry arrives immediately, no handoff delay |
| **Poll-5s** | HTTP every 5 s | None (duplicates ~50% of polls) | Over-polling: proves the mechanism is missed windows, not stale data |
| **Poll-12s** | HTTP every 12 s | Minor (~1 of 6 windows missed) | Practical alternative — shows the penalty is gradual, not binary |
| **Poll-30s** | HTTP every 30 s | Major (~2 of 3 windows missed) | Separated-architecture default: equivalent to Prometheus scrape interval |

Poll-30s is the critical condition. It encodes the architectural property
that every separated monitoring system imposes — the controller simply does
not see most of the telemetry it needs. If push and poll-30s produce
indistinguishable service quality, the coordination gap exists on paper
but is inconsequential at these cadences — a valid bounding result. If
Poll-30s is measurably worse, the thesis has evidence that the gap is real,
quantifiable, and architecturally significant.

### 4.3 What Is Held Constant

The aggregation window is fixed at 10 s. Window size variation is deferred
to future work. All other parameters (workload, thresholds, infrastructure,
routing policy) use the RQ3-validated configuration. For the v5 pilot, the
controller scoring function uses `CPU_SPAN=40`, `CPU_FLOOR=10`,
`BASE_THRESHOLD=0.18`, and `COOLDOWN_S=45`.

### 4.4 Code-Level Mechanisms That Compound the Gap

Three secondary mechanisms compound the coordination gap in Poll-30s. These
are not confounds — they are the architectural consequences of delivery
cadence that real separated systems experience.

| Mechanism | Push | Poll-30s | Impact |
|---|---|---|---|
| Scale-up sliding window wall-clock duration | ~50 s (5 windows × 10 s) | ~150 s (5 windows × 30 s) | Requires 3× more sustained degradation to trigger a reaction |
| Dead-node detection timeout | ~180 s (18 windows × 10 s) | ~540 s (18 windows × 30 s) | Crashed nodes block scale-up for 9 min in poll mode vs 3 min in push |
| VIP routing server-stats staleness | ≤10 s | ≤30 s | Poll-30s routing decisions may use up to 30 s-stale load data, sending disproportionate traffic to overloaded servers |

The **VIP routing staleness** mechanism (row 3) was confirmed in v4 data:
Poll-30s shows 1.86× higher p50-p95 latency spread on `service_pressure`
than Push (0.89s vs 0.48s) — the coordination gap is visible to users as
latency variance, not just as spawn count differences.

---

## 5. How It Is Measured

The v5 measurement framework decomposes the coordination gap into nine
metrics (M1–M9) organized by what they measure: **detection failure**,
**user impact**, and **recovery**. Together they triangulate the gap from
every angle — whether the controller failed to see overload, whether users
suffered as a result, and whether the system was slower to return to
baseline.

### 5.1 Confirmation Metric — Information Age at Consumption

```
consumed_at − window_end
```

Both timestamps use `time.time()` on the same host. Expected: ~0 s for all
modes. The HTTP cache always holds the freshest completed summary — push
and poll are indistinguishable by this metric. This measurement confirms
the delivery pipeline is healthy; it does not differentiate between modes.
The mechanism is missed windows, not stale data at consumption time.

### 5.2 Primary Metrics (M1–M9)

#### M1 — Spawn Count

**Purpose**: Did the controller respond to load? Counts compute nodes
spawned per run from `node_lifecycle_timings.csv`. The spawn count gap is
the anchor metric — it is invariant across all experiment configurations
and establishes that the blind spot has a control-plane effect regardless
of whether that effect propagates to users.
**Expectation**: Push > Poll-30s by a substantial margin.

#### M2 — Missed Opportunities

**Purpose**: Did the controller fail to respond when it should have?
Identifies phases where mean per-node CPU exceeds a threshold, p95 CPU
indicates concentrated load, yet fewer than 2 compute spawns occurred
within the phase time bounds. Accounts for the controller's adaptive
threshold escalation (BASE + INCREMENT × existing dynamic nodes).
**Expectation**: Poll-30s missed opportunities > Push missed opportunities.

#### M3 — Time-to-Capacity

**Purpose**: How long did local users wait before the system caught up?
For each high-load phase: time from phase start to the first 10 s window
where p95 local latency falls below a threshold AND at least one dynamic
node is online. Reports "not achieved within phase" if the system never
stabilizes.
**Expectation**: Poll-30s time-to-capacity > Push time-to-capacity.

#### M4 — Throughput

**Purpose**: Did Poll-30s complete meaningfully fewer requests than Push?
Total requests completed per high-load phase, with compute_spike as the
headline phase. A throughput gap without a corresponding timeout spike
means the system degraded gracefully (queueing) rather than failing —
still a coordination gap, just not a catastrophic one. This is the
**primary success gate** for the v5 pilot.
**Expectation**: Poll-30s throughput in compute_spike substantially below
Push throughput.

#### M5 — Timeout Rate

**Purpose**: Did users experience outright failures? Per-phase timeout
rate (latency ≥ 29.9 s). This is the **secondary success gate** — less
sensitive than throughput at small sample sizes but directly measures
user-visible harm.
**Expectation**: Poll-30s timeout rate > Push timeout rate.

#### M6 — Blind Spot Windows

**Purpose**: How many overload windows did the controller never see? An
independent observer reconstructs all 10 s telemetry windows and computes
degradation scores using the controller's own formula and parameters.
Windows where score ≥ threshold but the controller never consumed them
are **blind spots**. The headline metric is the **blind spot rate**
(blind_spot_windows ÷ breached_windows). Also reports **requests in
shadow** — the request volume during the 10 s following each blind spot.
**Expectation**: Push blind spot rate ≈ 0%. Poll-30s blind spot rate
substantial (> 0%). This is the most direct quantification of the
coordination gap at the mechanism level.

#### M7 — Timeout Root Cause Classification

**Purpose**: Why did each timeout happen? Was it preventable with faster
spawning? Classifies every timeout (latency ≥ 29.9 s) into one of six
categories applied in precedence order:

| # | Category | Detection |
|---|----------|-----------|
| 1 | Capacity gap | server_count insufficient for instantaneous load |
| 2 | Cold start | Node provisioned < 30 s before the request |
| 3 | Storage bound | Insufficient storage nodes; T_db elevated |
| 4 | WAN saturation | Cross-region request; WAN latency elevated |
| 5 | Transient spike | ≥ 90% of requests in same bucket succeeded |
| 6 | Unclassified | Catch-all for pattern discovery |

**Expectation**: Push timeouts (if any) should be dominated by WAN
saturation and transient spikes. Poll-30s should show an additional
"capacity gap" category — timeouts directly attributable to the blind
spot delaying spawn decisions.

#### M8 — Latency by Endpoint

**Purpose**: Which endpoints suffer under Poll-30s? Is the degradation
compute-specific (confirming the blind spot mechanism) or generalized?
Computes p50/p95/p99 latency per endpoint per phase. Discriminates
compute-heavy endpoints (`service_pressure`, `feed_ranking`) from
storage-bound endpoints (`content_lookup`, `content_update`,
`content_aggregate`).

Also measures **latency variance** (p50–p95 spread) on compute-heavy
endpoints. The v4 data already shows Poll-30s has 1.86× wider p50–p95
spread on `service_pressure` than Push — this is the signature of stale
VIP routing. At higher load (v5 Pilot B), the spread should widen further.

**Expectation**: Poll-30s latency elevated on compute-heavy endpoints but
similar to Push on storage-bound endpoints. The p50–p95 spread on
`service_pressure` should be wider for Poll-30s.

#### M9 — Recovery Lag

**Purpose**: After the crisis ends, how long until the system returns to
baseline? Tracks time from `demand_drop` phase start until `server_count`
stabilizes at the baseline level for a sustained period. Also reports
peak server_count during demand_drop and node-seconds wasted (area under
the excess-server curve).

Combined with M3 (time-to-capacity on the way up), M9 captures the full
asymmetry of the coordination gap: Poll-30s is **slow to ramp up AND slow
to ramp down**.
**Expectation**: Poll-30s recovery lag > Push recovery lag.

### 5.3 Secondary Metrics

**Control-plane overhead**: Controller CPU% and RSS (MB) via `docker stats`
sampled every 5 s. Polling traffic volume estimated from `POLL_INTERVAL_S`
and summary size (~2–10 KB per poll). Confirms that polling does not impose
meaningful overhead at these cadences.

### 5.4 Success Criteria (C1–C12)

Each criterion maps to one or more of the primary metrics above.

| # | Criterion | Maps to | Expectation |
|---|-----------|---------|-------------|
| C1 | Run completion | — | All runs complete → idle, zero controller tracebacks |
| C2 | **Pilot success gate (primary)** | M4 | Poll-30s throughput in compute_spike substantially below Push |
| C2b | Pilot success gate (secondary) | M5 | Poll-30s timeout rate substantially above Push |
| C3 | Spawn count gap | M1 | Push compute spawns > Poll-30s by a substantial margin |
| C4 | Missed opportunities | M2 | Poll-30s missed ≥ 2 phases with CPU pressure and no spawns |
| C5 | Time-to-capacity gap | M3 | Poll-30s time-to-capacity > Push for high-load phases |
| C6 | Throughput gap | M4 | Poll-30s throughput in compute_spike substantially below Push |
| C7 | Staleness step-function | Confirmation | Push ~0 s, Poll-30s ~10 s (window-gated) |
| C8 | All 4 mechanisms exercise | — | Storage, compute, Tier 1 selective sync, reserve activation |
| C9 | Blind spot windows | M6 | Push blind spot rate ≈ 0%; Poll-30s blind spot rate substantial |
| C10 | Timeout root cause | M7 | Every timeout classified; Poll-30s shows "capacity gap" category |
| C11 | Endpoint-specific degradation | M8 | Poll-30s elevated on compute-heavy, not storage-bound endpoints |
| C12 | Recovery lag | M9 | Poll-30s recovery lag > Push; holds nodes longer after load drops |

### 5.5 Measurement Chain

```text
Polling interval ↑
  → missed windows between polls ↑        (M6 — blind spot windows)
  → breach detection delayed              (M2 — missed opportunities)
  → nodes arrive later or not at all      (M1 — spawn count gap)
  → local users queue longer              (M3 — time-to-capacity)
  → fewer requests complete               (M4 — throughput gap)
  → some requests time out                (M5, M7 — timeout rate + root cause)
  → compute-heavy endpoints degrade       (M8 — latency by endpoint)
  → system slow to return to baseline     (M9 — recovery lag)
```

Information age at consumption (§5.1) is ~0 s for all modes — it confirms
the pipeline is healthy but does not appear in the causal chain. The
mechanism is missed windows, not stale data.

---

## 6. Evaluation Design Evolution

### 6.1 V3 — Initial Campaign (Executed)

12 runs (n=3 × 4 modes: Push, Poll-5s, Poll-12s, Poll-30s) at 48 clients,
`WAN_RTT_MS=200`, `CPU_SPAN=5`. Found a clear monotonic trend: Poll-30s
produced 4.3× higher timeout rate than Push (25.5% vs 5.9%) and 2.3× higher
reaction latency (75.7 s vs 33.2 s). However, within-mode variance was large
(σ = 7–12 pp) due to bimodal operational regime. See [`rq1.md`](rq1.md) and
[`results_v3.md`](../operation/testing/experiment/rq1_thesis_final/results_v3.md).

### 6.2 V4 — Scoring-Corrected Rerun (Executed)

`CPU_SPAN=5` was identified as a bug — it caused the scoring function to
saturate immediately, making the controller hypersensitive to minor CPU
fluctuations. V4 reran with `CPU_SPAN=40` (the intended value): 12 runs
(n=3 × 4 modes) at 48 clients, `WAN_RTT_MS=185`.

**Key findings**:
- All 12 runs completed with 1.0–2.2% timeout rates — no user-visible gap
- Poll-30s spawned **52% fewer** compute nodes than Push (10.7 vs 22.7)
  and completed **46% fewer** requests in compute_spike (97 vs 181 rps)
- The coordination gap exists at the control-plane level but the system
  has too much headroom — Poll-30s' 11 nodes clear the survival bar
- **Routing staleness confirmed**: Poll-30s shows 1.86× higher p50-p95
  latency spread on `service_pressure` — the gap IS visible to users as
  latency variance, just not as timeout rate

See [`results_v4.md`](../operation/testing/experiment/rq1_thesis_final/results_v4.md).

### 6.3 V5 — Stress-Calibrated Pilot (In Progress)

V5 eliminates the headroom that masked the coordination gap in v4. Two
sequential pilots stress the system so the spawn count difference becomes
the difference between surviving and failing:

| Pilot | Mechanism | What it tests |
|-------|-----------|---------------|
| **A** (executed) | Compressed phases (durations halved) | Poll-30s nodes arrive after the phase ends — the 90 s minimum decision time + 14 s provisioning means the node comes online at t≈104 s, after a 90 s phase |
| **B** (planned) | Double clients (48→96) + raised `MAX_DYNAMIC_COMPUTE` (8→12) | Doubles CPU demand and removes the provisioning ceiling so Push can demonstrate its full spawning advantage. Stale routing + fewer nodes compound |

**Pilot A result**: Both success gates failed — compressed phases capped
both modes equally (Push spawned only 5 nodes vs 23 in v4, Poll-30s spawned
4). Phase duration, not telemetry cadence, was the binding constraint.
Proceeding to Pilot B.

**Pilot B**: 4 runs (Push × 2, Poll-30s × 2) at 96 clients,
`MAX_DYNAMIC_COMPUTE=12`, canonical phase durations. Expected primary
signals: throughput gap (C2) and latency variance (M8 spread).

Full plan: [`experiment_plan_v5.md`](../operation/testing/experiment/rq1_thesis_final/experiment_plan_v5.md).

---

## 7. Outcomes

### 7.1 V3 Outcomes (CPU_SPAN=5)

All five expectations tested with n=3 per mode. See [`rq1.md`](rq1.md) §7
for full details.

1. **Information age** — ✅ ~0 s for all modes
2. **Reaction latency** — ✅ Monotonic: Push 33.2 s → Poll-30s 75.7 s
3. **Service quality** — ✅ Timeout rate: Push 5.9% → Poll-30s 25.5%
   (caveat: large within-mode variance, bimodal regime)
4. **Control-plane overhead** — ✅ Modest: CPU 11–14%, RAM 86–94 MB
5. **Scaling divergence** — ✅ Poll-30s spawned fewer nodes (6–11 vs 15–20)

### 7.2 V4 Outcomes (CPU_SPAN=40)

1. **Information age** — ✅ ~0 s for all modes (unchanged)
2. **Spawn count gap** — ✅ Push 22.7, Poll-30s 10.7 (52% gap)
3. **Service quality** — ❌ No separation: all modes 1.0–2.2% timeout
   (the system has too much headroom)
4. **Throughput gap** — ✅ 46% gap in compute_spike (181 vs 97 rps)
5. **Routing staleness** — ✅ Poll-30s 1.86× wider p50-p95 spread
6. **Blind spot rate** — ✅ Push 0%, Poll-30s 71–89% (M6 backport)
7. **Timeout root cause** — ✅ Push dominated by transient; Poll-30s
   shows capacity gap pattern (M7 backport)

**Interpretation**: The coordination gap is real and measurable at the
control-plane level (M1, M6) and visible to users as latency variance
(M8 spread), but does not cause outright failures (M5) at 48 clients
with `CPU_SPAN=40`. The system has enough headroom to absorb the blind
spot's consequences. V5 tests the boundary condition.

### 7.3 V5 Status

| Phase | Status |
|-------|--------|
| Pilot A (compressed phases, 4 runs) | ✅ Executed — both gates failed; phase duration was binding |
| Pilot B (96 clients, 4 runs) | ⏳ Planned — awaiting execution |
| Full campaign (12 runs) | ⏳ Contingent on pilot success |

---

## 8. Related Documents

| Document | Purpose |
|----------|---------|
| [`rq1.md`](rq1.md) | Original v3/v4 measurement framework and detailed v3 results |
| [`system_to_thesis_map_rq_v2.md`](../../tese/miscelineous/system_to_thesis_map_rq_v2.md) | Full three-pillar thesis framing; RQ1 in context of RQ2 and RQ3 |
| [`experiment_plan_v5.md`](../operation/testing/experiment/rq1_thesis_final/experiment_plan_v5.md) | V5 pilot operational plan: run matrix, commands, success criteria |
| [`results_v4.md`](../operation/testing/experiment/rq1_thesis_final/results_v4.md) | V4 full results (12 runs, CPU_SPAN=40) |
| [`results_v3.md`](../operation/testing/experiment/rq1_thesis_final/results_v3.md) | V3 full results (12 runs, CPU_SPAN=5) |
| [`golden_config.md`](../operation/testing/golden_config.md) | Canonical workload sizing, thresholds, and toggles |
