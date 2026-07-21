# RQ1 — Telemetry Delivery Cadence and Control Quality

**Thesis pillar**: Telemetry Freshness (the delivery link)
**Status**: V3 evaluated (12 runs, n=3 per mode). V4 rerun planned (6 runs, Push + Poll-30s only) — scoring-corrected after CPU_SPAN=5 bug discovery.
**Results**: [`docs/operation/testing/experiment/rq1_thesis_final/results_v3.md`](../operation/testing/experiment/rq1_thesis_final/results_v3.md)
**V4 plan**: [`docs/operation/testing/experiment/rq1_thesis_final/experiment_plan_v4.md`](../operation/testing/experiment/rq1_thesis_final/experiment_plan_v4.md)
**Comparison graphs**: [`docs/operation/testing/experiment/rq1_thesis_final/graphs/comparison/`](../operation/testing/experiment/rq1_thesis_final/graphs/comparison/)
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
which the system is overloaded but no action is taken. The controller
eventually receives fresh data, but it missed the critical intermediate
windows that showed the onset of overload.

**Compound effect — sliding windows amplify the penalty.** The controller's
scale-up decision uses sliding windows defined in *window counts* (5 windows,
3 hits). In Push mode (10 s/window), this covers ~50 s of wall-clock time.
In Poll-30s (30 s/poll), the same 5 windows span ~150 s — a 3× compound
effect. The experiment does not isolate pure delivery cadence; it measures
the **compound coordination gap** that real separated architectures
experience: wasted windows (blind spot) × sustained degradation required
(wall-clock duration of the evaluation window). This compound effect is
the thesis contribution — it is what makes the coordination gap a measurable
architectural property rather than an abstract latency budget.

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

Each mode tests a specific claim about the coordination gap. The rightmost
column maps each condition to the five-form evidence structure established
in the [global literature review](../../tese/literature_review/global_literature_review.md).

| Condition | Delivery | Blind spot | Encodes | Lit. evidence addressed |
|---|---|---|---|---|
| **Push** | ZMQ at window close | None | The unified architecture: telemetry arrives immediately, no handoff delay | Form 2: quantifies AdapPF's observation — *how much* better when every window is seen |
| **Poll-5s** | HTTP every 5 s | None (duplicates ~50% of polls) | Over-polling: wastes resources; proves the mechanism is missed windows, not stale data | Form 1: confirms Yaseen's "visibility gap" is ~0 s at consumption time — the HTTP cache works |
| **Poll-12s** | HTTP every 12 s | Minor (~1 of 6 windows missed) | Practical alternative — polls just after window close; shows the penalty is gradual, not binary | Form 4: bridges the monitoring→LB disconnect — the blind spot Caiza & Campoverde's "periodically" buries now has a measured cost |
| **Poll-30s** | HTTP every 30 s | Major (~2 of 3 windows missed) | Separated-architecture default: the equivalent of Prometheus scrape interval, CloudWatch metric period | Form 1+2+4: quantifies Wang et al.'s documented-but-unmeasured delivery gap; measures the symptom Pierro & Ullah observed (throughput ↓); tests Yaseen's claim that visibility gaps matter for infrastructure decisions |

Poll-30s is the critical condition. It encodes the architectural property
that every separated monitoring system imposes — the controller simply does
not see most of the telemetry it needs. If push and poll-30s produce
indistinguishable reaction latency and service quality, the coordination
gap exists on paper but is inconsequential at these cadences — a valid
bounding result. If Poll-30s is measurably worse, the thesis has evidence
that the gap is real, quantifiable, and architecturally significant.

**Result**: Poll-30s produced 4.3× higher mean timeout rate than Push
(25.5% vs 5.9%) and 2.3× higher mean reaction latency (75.7 s vs 33.2 s).
The gap is real and measurable. See [`results_v3.md`](../operation/testing/experiment/rq1_thesis_final/results_v3.md) for full analysis.

### 4.3 What Is Held Constant

The aggregation window is fixed at 10 s. Window size variation (1 s, 5 s,
30 s) — testing the freshness-versus-noise tradeoff — is deferred to future
work. All other parameters (workload, thresholds, infrastructure, routing
policy) use the RQ3-validated configuration.

### 4.4 Code-Level Mechanisms That Compound the Gap

A code audit of `source/sdn_controller/` identified three secondary
mechanisms beyond simple data freshness that compound the coordination gap
in Poll-30s. These are not confounds — they are the architectural
consequences of delivery cadence that real separated systems experience.

| Mechanism | Push | Poll-30s | Impact |
|---|---|---|---|
| Scale-up sliding window wall-clock duration | ~50 s (5 windows × 10 s) | ~150 s (5 windows × 30 s) | Requires 3× more sustained degradation to trigger a reaction |
| Dead-node detection timeout | ~180 s (18 windows × 10 s) | ~540 s (18 windows × 30 s) | Crashed nodes block scale-up for 9 min in poll mode vs 3 min in push |
| VIP routing server-stats staleness | ≤10 s | ≤30 s | Poll-30s routing decisions may use up to 30 s-stale load data, sending disproportionate traffic to overloaded servers |

These mechanisms are documented in the [experiment plan v4](../operation/testing/experiment/rq1_thesis_final/experiment_plan_v4.md) validity threats.
They are inherent to the window-count-based design and are identical in v3
and v4 — the v4 rerun does not change them.

---

## 5. How It Is Measured

Five measurements answer the question. **Measurement 2 is the core thesis
evidence** — the others provide confirmation, context, and cost assessment.

### 5.1 Information Age at Consumption — Confirmation

```
consumed_at − window_end
```

Both timestamps use `time.time()` on the same host. **Expected: ~0 s for all
modes.** The HTTP cache always holds the freshest completed summary — push
and poll are indistinguishable by this metric. This measurement confirms the
delivery pipeline is healthy; it does not differentiate between modes.

### 5.2 Reaction Latency — Core Evidence

```
total_reaction_s = breach_detection_s + provision_time_s
```

Computed from per-event `rq1_reaction_latency.csv` across all replicates.

- **Breach detection** (`breach_detection_s`): time from breach window end
  to spawn initiation. Dominated by controller evaluation logic (sliding
  window, cooldown). In Poll-30s the blind spot adds up to 30 s per missed
  window, AND the sliding window's wall-clock duration triples (150 s vs
  50 s) — the measured penalty is the compound of both effects.
  **This is the segment where the polling penalty appears.**
- **Provisioning** (`provision_time_s`): container boot + OVS wiring.
  Measured as constant ~14 s across all modes — the penalty is entirely
  in detection, not in provisioning.

**Result**: Detection grows with polling interval (Push ~19 s → Poll-30s
~62 s); provisioning is flat (~14 s). The mechanism is confirmed:
polling delays *when the controller learns*, not *how fast it provisions*.

The breach window is identified by an independent observer
(`breach_detector.py`) using the same formula and thresholds as the
controller. It fires on the first individual window where
`score ≥ threshold` — measuring "when overload was visible in telemetry,"
not "when the controller decided to act." This preserves methodological
separation between detection timing and controller decision logic.

### 5.3 Transient Service Quality — User-Visible Impact

p95/p99 latency, failure rate, and completed requests compared across
workload phases (`compute_spike`, `storage_stress`, `demand_drop`, etc.)
using the existing analysis CLIs (`cli_simple_run`, `cli_phase_summary`).

### 5.4 Control-Plane Overhead — Cost

Controller CPU% and RSS (MB) via `docker stats` sampled every 5 s on both
`osken` and `osken_2` containers. Polling traffic volume is estimated from
`POLL_INTERVAL_S` and summary size (~2–10 KB per poll).

### 5.5 Scaling Outcome Description — Behavioral Divergence

A per-phase descriptive table comparing what was visible in telemetry
against what the controller did: total telemetry windows, how many showed
overload, peak degradation score, and how many spawns the controller
initiated and completed. No classification labels — the gap between
breached-windows and completed-spawns is the observable fact. The thesis
interprets this alongside reaction latency to answer: as the blind spot
widens, does the controller still respond adequately?

### 5.6 Measurement Chain

```JavaScript
Polling interval ↑
  → missed windows between polls ↑   (the mechanism)
  → breach-detection segment ↑        (measurement 5.2 — core evidence)
  → transient service quality ↓       (measurement 5.3 — user impact)
  → scaling outcomes may diverge      (measurement 5.5 — behavioral)
```

Information age at consumption (measurement 5.1) is ~0 s for all modes —
it confirms the pipeline is healthy but does not appear in the causal chain.

---

## 6. Evaluation Design (Executed)

The experiment was executed as a 12-run campaign (n=3 replicates × 4 modes)
using the RQ1 workload (`phases.json`, 7 phases, ~28 min per run). All runs
used `CLIENTS=48`, `DEVICES=6000`, `NODES=100`, `WAN_RTT_MS=200`,
`CURL_MAX_TIME=30`, `VIP_HARD_TIMEOUT=60`, `RANDOM_SEED=42`, and thresholds
from `current_state_integrated.env`. Full container + volume reset
(`cleanup.sh -r`) between runs ensured identical initial state.

| Mode | Delivery | Blind spot | Replicates | Timeout rate (μ ± σ) | Reaction latency (μ) |
|---|---|---|---|---|---|
| **Push** | ZMQ at window close | None | n=3 | 5.9 ± 7.2% | 33.2 s |
| **Poll-5s** | HTTP every 5 s | None | n=3 | 8.1 ± 5.4% | 39.6 s |
| **Poll-12s** | HTTP every 12 s | ~1 of 6 windows missed | n=3 | 14.7 ± 11.7% | 48.1 s |
| **Poll-30s** | HTTP every 30 s | ~2 of 3 windows missed | n=3 | 25.5 ± 9.1% | 75.7 s |

Full operational details — run matrix, shell commands, pre-run checklist,
artifact contract, success criteria, and validity threats — are in the
[experiment plan](../operation/testing/experiment/rq1_thesis_final/experiment_plan_v3.md).
Complete results in [`results_v3.md`](../operation/testing/experiment/rq1_thesis_final/results_v3.md).

---

## 7. Outcomes (Evaluated)

All four expectations were tested with n=3 replicates per mode (12 total
runs, RANDOM_SEED=42, identical workload). Full results in
[`results_v3.md`](../operation/testing/experiment/rq1_thesis_final/results_v3.md).

1. **Information age at consumption** — ✅ Confirmed. ~0 s for all four
   modes (Push: 0.039 s, Poll-5s: 5.181 s, Poll-12s: 9.984 s, Poll-30s:
   9.945 s). The HTTP cache delivers fresh data; the mechanism is missed
   windows, not stale data at consumption time.

2. **Reaction latency increases with polling interval** — ✅ Confirmed.
   Push: 33.2 s, Poll-5s: 39.6 s, Poll-12s: 48.1 s, Poll-30s: 75.7 s.
   Monotonic trend holds. The breach-detection segment accounts for the
   increase; provisioning is constant (~14 s across all modes).

3. **Transient service quality degrades** — ✅ Confirmed in mean, with
   caveat. Timeout rate increases monotonically: Push 5.9%, Poll-5s 8.1%,
   Poll-12s 14.7%, Poll-30s 25.5%. However, within-mode variance is large
   (σ = 7–12 percentage points) due to a **bimodal operational regime**:
   each mode splits into healthy (~1–2% timeout) and degraded (10–35%
   timeout) runs. This bimodality persists despite RANDOM_SEED=42 and
   `cleanup.sh -r` — it is genuine system non-determinism, not a
   measurement artifact or workload confound. The storage_storm phase is
   the inflection point where the system bifurcates.

4. **Control-plane overhead** — ✅ Confirmed modest. CPU: 14.2% (Push),
   14.0% (Poll-5s/12s), 11.0% (Poll-30s). RAM: 86–94 MB across all modes.
   Polling does not impose meaningful overhead at these cadences.

5. **Scaling outcomes diverge** — ✅ Confirmed. Poll-30s runs spawn fewer
   compute nodes (6–11 per run vs 15–20 for Push/Poll-5s/Poll-12s) and
   exhibit a runaway degradation loop in the worst case (poll30_1:
   115.3 s reaction latency, 35.1% timeout rate). All four elasticity
   mechanisms exercise in all 12 runs (storage scale-out, compute
   scale-up, Tier 1 selective sync, reserve activation).

**Unexpected finding — bimodality**: The bimodal split within each mode
is the most significant result. It shows that at this scale (48 clients,
6000 devices, 100 nodes), the system operates near a phase transition
between healthy and degraded regimes. This phenomenon is invisible to any
single-run experiment and only becomes measurable with n=3 replication and
identical workload seeding.

---

## 8. Related Documents

| Document                                                                                                                              | Purpose                                                                                |
| ------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| [`system_to_thesis_map_rq_v2.md`](../../tese/miscelineous/system_to_thesis_map_rq_v2.md)                                               | Full three-pillar thesis framing; RQ1 in context of RQ2 and RQ3                        |
| [`experiment_plan.md`](../operation/testing/experiment/rq1_evaluation/experiment_plan.md)                                              | Operational experiment plan: run matrix, commands, artifact contract, success criteria |
| [`analysis_toolchain.md`](../operation/testing/analysis_toolchain.md)                                                                  | Analysis CLI reference: how each measurement is produced from run artifacts            |
| [`golden_config.md`](../operation/testing/golden_config.md)                                                                            | Canonical workload sizing, thresholds, and toggles                                     |
| [`rq1_instrumentation_verification/results.md`](../operation/testing/experiment/stability/rq1_instrumentation_verification/results.md) | Evidence that the measurement pipeline works; §5 confirms staleness ~0 for all modes  |
