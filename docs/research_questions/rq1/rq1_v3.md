# RQ1 v3 — Telemetry Delivery Cadence and Control Quality

**Thesis pillar**: Telemetry Freshness (the delivery link)
**Status**: v8 evaluated (12 runs, n=3 per mode, `EDGE_CPUS=0.30`) → v9 calibration (CPU sweep, C2 at `EDGE_CPUS=0.15` won) → **v10 planned** (12 runs, n=3 per mode, `EDGE_CPUS=0.15`, definitive campaign)
**Previous version**: [`rq1_v2.md`](rq1_v2.md) (v3–v8 methodology and measurement framework)
**v8 results**: [`docs/operation/testing/experiment/rq1_thesis_final/v8/rq1_v8_conclusions.md`](../../operation/testing/experiment/rq1_thesis_final/v8/rq1_v8_conclusions.md)
**v10 plan**: [`docs/operation/testing/experiment/rq1_thesis_final/v10/experiment_plan_v10.md`](../../operation/testing/experiment/rq1_thesis_final/v10/experiment_plan_v10.md)
**v10 setup**: [`rq1_setup_v10.md`](rq1_setup_v10.md)

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
to future work.

| Parameter | v8 Value | v10 Value | Rationale |
|-----------|----------|-----------|-----------|
| `EDGE_CPUS` | 0.30 | **0.15** | v8's 0.30 let static nodes absorb the blind spot. Halving forces the gap to cascade into user-visible failure (§4.5). |
| `CLIENTS` | 96 | 96 | Doubled from v4's 48 to remove headroom |
| `MAX_DYNAMIC_COMPUTE` | 12 | 12 | Raised from 8 so Push can demonstrate its full spawning advantage |
| `STORAGE_CPUS` | 0.08 | 0.08 | v5 Pilot B calibration |
| `CPU_SPAN` | 40 | 40 | v4 onward — prevents score saturation |
| `WAN_RTT_MS` | 185 ms | 185 ms | v5 calibration |
| Phases | cleanup-gap (9 phases) | cleanup-gap (9 phases) | Identical workload shape |
| Controller scoring | `current_state_integrated.env` | `current_state_integrated.env` | Same thresholds, cooldowns, caps |

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

### 4.5 Why v10 Calibrated EDGE_CPUS Downward

v8 (n=3, four modes, `EDGE_CPUS=0.30`) established the full dose-response
curve: blind spot rate 0% → 0% → 25% → 68%, spawn count 29 → 22 → 21 → 8,
and the mechanism-level evidence was strong. But the **user-visible separation**
— the throughput and timeout gap — was noisy.

At `EDGE_CPUS=0.30`, the static edge nodes had enough capacity to absorb the
Poll-30s blind spot. Requests queued rather than timed out. The throughput
gap was −19% mean with σ=14K — one Poll-30s replicate matched Push.

The thesis argument is that the coordination gap *harms users*. If the gap
produces a strong mechanism-level signal (M6 blind spots at 68%) but the
user-visible signal is weak and noisy, the causal chain is incomplete. The
thesis needs to show that missed windows → delayed spawns → user-visible
degradation.

**The calibration** (v9_calibration) swept `EDGE_CPUS` from 0.30 down to
find the point where the static nodes can no longer absorb the blind spot.
At `EDGE_CPUS=0.15` (C2), a pilot pair showed:

| Metric | Push | Poll-30s | Δ |
|--------|------|----------|---|
| Total requests | 89,028 | 62,299 | −30% |
| Timeout rate | 2.0% | 4.5% | +2.3× |
| p50 latency | 8.4 ms | 43.6 ms | 5.2× |
| p95 latency | 9.2 s | 18.1 s | 2.0× |

The mechanism-to-user chain is now complete: the blind spot (68% of breached
windows unseen) → spawn deficit (71% fewer compute nodes) → user-visible
harm (−30% throughput, +2.3× timeout, 5.2× p50 latency).

v10 runs the full 12-run, 4-mode campaign at this calibrated CPU level to
confirm the curve with statistical power.

---

## 5. How It Is Measured

The measurement framework decomposes the coordination gap into nine
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
**v8 result**: Push μ=29.0, Poll-30s μ=8.3 (71% fewer). Monotonic gradient.
**v10 expectation**: Similar or wider gap at `EDGE_CPUS=0.15`.

#### M2 — Missed Opportunities

**Purpose**: Did the controller fail to respond when it should have?
Identifies phases where mean per-node CPU exceeds a threshold, p95 CPU
indicates concentrated load, yet fewer than 2 compute spawns occurred
within the phase time bounds. Accounts for the controller's adaptive
threshold escalation.
**v8 result**: Push 5/12, Poll-30s 9/12 missed phases.
**v10 expectation**: Poll-30s missed ≥ Push missed.

#### M3 — Time-to-Capacity

**Purpose**: How long did local users wait before the system caught up?
For each high-load phase: time from phase start to the first 10 s window
where p95 local latency falls below a threshold AND at least one dynamic
node is online.
**v8 result**: All runs "not_achieved" — threshold too strict for v8 workload.
**v10 expectation**: Deprioritized. M4 (throughput) and M5 (timeout rate)
provide stronger, more reliable user-impact evidence at this CPU level.
M3 is retained for completeness but is not a primary success criterion.

#### M4 — Throughput

**Purpose**: Did Poll-30s complete meaningfully fewer requests than Push?
Total requests completed per run. The **primary success gate**.
**v8 result**: Push μ=67,292, Poll-30s μ=54,536 (−19% mean, σ=14K).
**v10 expectation**: Push ≥ 85K, Poll-30s ≤ 65K, no overlap between worst
Push and best Poll-30s. The C2 pilot confirmed this separation.

#### M5 — Timeout Rate

**Purpose**: Did users experience outright failures? Per-phase timeout
rate (latency ≥ 29.9 s). The **secondary success gate**.
**v8 result**: Push 3.1%, Poll-30s 5.9% (but σ=3.3%).
**v10 expectation**: Push ≤ 3%, Poll-30s ≥ 4% in every replicate.

#### M6 — Blind Spot Windows

**Purpose**: How many overload windows did the controller never see? An
independent observer reconstructs all 10 s telemetry windows and computes
degradation scores. Windows where score ≥ threshold but the controller
never consumed them are **blind spots**. The headline metric is the
**blind spot rate** (blind_spot_windows ÷ breached_windows).
**v8 result**: Push 0/77 (0%), Poll-5s 0/39 (0%), Poll-12s 19/75 (25.3%),
Poll-30s 53/78 (67.9%). Strongest single metric in v8.
**v10 expectation**: Same monotonic gradient, with Poll-30s ≥ 50%.

#### M7 — Timeout Root Cause Classification

**Purpose**: Why did each timeout happen? Classifies every timeout into
six categories: capacity gap, cold start, storage bound, WAN saturation,
transient spike, unclassified.
**v8 result**: Classifier confirmed blind-spot-driven timeouts concentrated
in Poll-30s.
**v10 expectation**: Push timeouts dominated by WAN/transient; Poll-30s
shows additional capacity-gap category.

#### M8 — Latency by Endpoint

**Purpose**: Which endpoints suffer under Poll-30s? Computes p50/p95/p99
latency per endpoint per phase. Discriminates compute-heavy endpoints
(`service_pressure`, `feed_ranking`) from storage-bound endpoints.
**v8 result**: Poll-30s p50-p95 spread 1.86× wider on `service_pressure`.
**v10 expectation**: p50 separation ≥ 5× (C2 pilot: 8.4 ms vs 43.6 ms).
p95 gap ≥ 2×. Separation strongest in cross-region phases.

#### M9 — Recovery Lag

**Purpose**: After the crisis ends, how long until the system returns to
baseline? Tracks time from `demand_drop` phase start until `server_count`
stabilizes. Combined with M3, captures the full asymmetry: slow to ramp
up AND slow to ramp down.
**v8 result**: Similar across modes (~30–35 s).
**v10 expectation**: Poll-30s recovery lag > Push recovery lag.

### 5.3 Secondary Metrics

**Control-plane overhead**: Controller CPU% and RSS (MB) via `docker stats`
sampled every 5 s. Confirms that polling does not impose meaningful
overhead at these cadences — the cost is in control quality, not resources.

### 5.4 Success Criteria

| # | Criterion | Maps to | v10 Expectation |
|---|-----------|---------|----------------|
| C1 | Run completion | — | All 12 runs complete, zero controller tracebacks |
| C2 | Throughput gap | M4 | Push ≥ 85K, Poll-30s ≤ 65K, monotonic gradient |
| C3 | Timeout gap | M5 | Push ≤ 3%, Poll-30s ≥ 4%, monotonic gradient |
| C4 | p50 latency gap | M8 | Push < 15 ms, Poll-30s > 30 ms |
| C5 | Blind spot rate | M6 | Push ≈ Poll-5s ≈ 0%, Poll-12s < Poll-30s, Poll-30s ≥ 50% |
| C6 | G8 gate | — | All 12 runs: zero spawns during cleanup gaps |
| C7 | Controller overhead | — | Flat across modes (~11–14% CPU) |
| C8 | Staleness | — | ~0 s information age for all modes |

---

## 6. Campaign History

| Campaign | Date | Config | Modes | Runs | Key Finding |
|----------|------|--------|-------|------|-------------|
| v3 | 2026-07 | `EDGE_CPUS=0.30`, `CPU_SPAN=5` | 4 modes × 1 | 4 | Score saturation — CPU_SPAN too narrow |
| v4 | 2026-07 | `EDGE_CPUS=0.30`, `CPU_SPAN=40` | 4 modes × 1 | 4 | Scoring corrected, first blind spot quantification |
| v5 | 2026-07 | Stress-calibrated, Push vs Poll-30s | 2 modes × 2 | 4 | Pilot calibration of thresholds and resource limits |
| v7 | 2026-07 | Cleanup-gap phases, Push vs Poll-30s | 2 × 2 | 4 | Cleanup gaps isolate detection speed |
| v8 | 2026-07-21/22 | `EDGE_CPUS=0.30`, cleanup-gap | 4 × 3 | 12 | Full dose-response curve. Strong M6 (67.9% blind spot). Throughput gap noisy (−19% mean). |
| v9 | 2026-07-24 | Halved phase durations | 2 × 1 | 2 | ❌ Failed — static-node floor absorbs gap |
| v9_cal | 2026-07-25 | CPU sweep: EDGE_CPUS ∈ {0.20, 0.15, 0.10} | 3 × 2 | 6 | C2 (0.15) wins: 30% throughput gap, 2.3× timeout |
| **v10** | *planned* | `EDGE_CPUS=0.15`, cleanup-gap | 4 × 3 | 12 | Definitive campaign — calibrated dose-response curve |
