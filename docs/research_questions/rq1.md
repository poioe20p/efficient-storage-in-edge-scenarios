# RQ1 — Telemetry Delivery Cadence and Control Quality

**Thesis pillar**: Information Acquisition
**Status**: Designed — ready for evaluation
**Evaluation plan**: [`docs/operation/testing/experiment/rq1_evaluation/experiment_plan.md`](../operation/testing/experiment/rq1_evaluation/experiment_plan.md)
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

| Condition          | Delivery            | Blind spot                                                | Encodes                                                                                       |
| ------------------ | ------------------- | --------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| **Push**     | ZMQ at window close | None                                                      | The unified architecture: telemetry arrives immediately, no handoff delay                     |
| **Poll-5s**  | HTTP every 5 s      | None (catches every window; ~50% of polls are duplicates) | Over-polling: wastes resources without benefit                                                |
| **Poll-12s** | HTTP every 12 s     | Minor (~1 of 6 windows missed)                            | Practical alternative to push — polls just after window close with headroom for clock desync |
| **Poll-30s** | HTTP every 30 s     | Major (~2 of 3 windows missed)                            | Separated-architecture property: Prometheus scrape interval, CloudWatch metric period         |

Poll-30s is the critical condition. If the controller sees only 1 of every 3
telemetry snapshots and its reaction to overload is measurably slower or its
service quality measurably worse, then the thesis has evidence that the
coordination gap matters. If push and poll-30s produce indistinguishable
reaction latency, the thesis has evidence that the gap is real on paper but
inconsequential at these cadences — still a valid contribution.

### 4.3 What Is Held Constant

The aggregation window is fixed at 10 s. Window size variation (1 s, 5 s,
30 s) — testing the freshness-versus-noise tradeoff — is deferred to future
work. All other parameters (workload, thresholds, infrastructure, routing
policy) use the [golden configuration](../operation/testing/golden_config.md)
proven stable across 15+ prior stability experiments.

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
spawn_done_ts − breach_window_end
```

Segmented into:

- **Breach detection** (`spawn_start_ts − breach_window_end`): time from the
  first telemetry window showing overload to spawn initiation. In push mode
  this is dominated by the controller's evaluation logic (sliding window,
  cooldown, ~10–20 s). In poll-30s the blind spot adds up to 30 s on top.
  **This is the segment where the polling penalty appears.**
- **Provisioning** (`spawn_done_ts − spawn_start_ts`): container boot time +
  OVS wiring. Expected constant (~1–2 s) across all modes.

The breach window is identified by an independent observer
(`breach_detector.py`) that computes `degradation_score` from telemetry
data using the same formula and thresholds the controller uses. It fires on
the first individual window where `score ≥ threshold` — it does not
replicate the controller's sliding window mechanism. This preserves the
methodological separation: the breach detector measures "when was overload
visible in telemetry," not "when the controller decided to act."

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

## 6. Evaluation Design

Four runs, one per condition, using the canonical 10-phase integrated
workload (`phases.json`, ~28 min). All runs use the [golden
configuration](../operation/testing/golden_config.md): `CLIENTS=8`,
`DEVICES=600`, `NODES=100`, thresholds from `current_state_integrated.env`.

| Run                | Delivery            | Blind spot                         |
| ------------------ | ------------------- | ---------------------------------- |
| **Push**     | ZMQ at window close | None                               |
| **Poll-5s**  | HTTP every 5 s      | None (dedup filters ~50% of polls) |
| **Poll-12s** | HTTP every 12 s     | ~1 of 6 windows missed             |
| **Poll-30s** | HTTP every 30 s     | ~2 of 3 windows missed             |

Full operational details — run matrix, shell commands, pre-run checklist,
artifact contract, success criteria, and validity threats — are in the
[evaluation experiment plan](../operation/testing/experiment/rq1_evaluation/experiment_plan.md).

---

## 7. Expected Outcomes

1. **Information age at consumption** is ~0 s for all four conditions.
   Confirms the delivery pipeline is healthy and the HTTP cache works.
2. **Reaction latency increases with polling interval.** The
   breach-detection segment grows as the blind spot widens. Push and
   poll-5s should be comparable (both catch every window). Poll-12s may
   show a small increase. Poll-30s should show the largest detection
   latency.
3. **Transient service quality degrades** when the blind spot prolongs
   overload. p95/p99 latency and failure rate are higher in demand-shift
   phases under poll-30s compared to push.
4. **Control-plane overhead** differs modestly between push (persistent
   ZMQ greenthread) and poll (periodic HTTP GET).
5. **Scaling outcomes may diverge** under poll-30s: spawns may arrive
   after the demand spike has passed.

If expectation 2 does not hold — reaction latency is indistinguishable
across modes — the thesis can bound the problem: the coordination gap
exists on paper but does not translate into measurably slower reactions
at cadences up to 30 s. If it does hold, the thesis can quantify the
relationship: a polling interval of *X* seconds adds up to *Y* seconds to
breach detection time.

---

## 8. Related Documents

| Document                                                                                                                              | Purpose                                                                                |
| ------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| [`system_to_thesis_map_rq_v2.md`](../../tese/miscelineous/system_to_thesis_map_rq_v2.md)                                               | Full three-pillar thesis framing; RQ1 in context of RQ2 and RQ3                        |
| [`experiment_plan.md`](../operation/testing/experiment/rq1_evaluation/experiment_plan.md)                                              | Operational experiment plan: run matrix, commands, artifact contract, success criteria |
| [`analysis_toolchain.md`](../operation/testing/analysis_toolchain.md)                                                                  | Analysis CLI reference: how each measurement is produced from run artifacts            |
| [`golden_config.md`](../operation/testing/golden_config.md)                                                                            | Canonical workload sizing, thresholds, and toggles                                     |
| [`rq1_instrumentation_verification/results.md`](../operation/testing/experiment/stability/rq1_instrumentation_verification/results.md) | Evidence that the measurement pipeline works; §5 confirms staleness ~0 for all modes  |
