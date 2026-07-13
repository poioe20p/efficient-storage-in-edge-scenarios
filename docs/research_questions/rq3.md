
# RQ3 — Trigger Quality and Detection Accuracy

**Thesis pillar**: Trigger Quality
**Status**: Designed — ready for evaluation
**Thesis map**: [`tese/miscelineous/system_to_thesis_map_rq_v2.md`](../../tese/miscelineous/system_to_thesis_map_rq_v2.md)

---

## 1. Thesis Context

This thesis investigates whether collapsing three traditionally separated
control-plane concerns — **information acquisition** (monitoring), **backend
selection** (load balancing), and **infrastructure adaptation** (auto-scaling)
— into a single SDN controller process eliminates coordination gaps that
degrade service quality during demand shifts.

RQ1 characterized the **delivery** link: does push-mode telemetry beat
polling by eliminating the blind spot between scrapes? RQ2 characterized
the **action** link: does spawn-time routing awareness beat discovery-time
awareness by eliminating the LB discovery gap?

RQ3 moves upstream to the **detection** link: before the controller can
deliver information (RQ1) or act on it (RQ2), it must first recognize that
overload is occurring. The degradation score that triggers scale-up is a
weighted combination of CPU saturation and processing latency. The question
is whether this latency-aware multi-dimensional score detects stateful-service
overload earlier and with fewer false positives than a CPU-only threshold —
the default in every major autoscaling platform.

---

## 2. Research Question

> For stateful edge services where I/O latency often degrades before CPU
> saturates, does a latency-aware multi-dimensional degradation score
> detect overload earlier and with fewer false positives than a CPU-only
> threshold?

---

## 3. What Is Being Investigated

The controller's scaling policy evaluates each telemetry window using a
weighted degradation score. The canonical configuration (from the
golden config established across 15+ stability experiments;
see [`golden_config.md`](../operation/testing/golden_config.md)) is:

```
score = 0.40 × saturate((CPU% − 3) / 10) + 0.60 × saturate((T_proc_ms − 15) / 80)
```

Where:

- `saturate(x) = clamp(x, 0, 1)`
- CPU component: activates above 3%, saturates at 13%
- Latency component: activates above 15 ms, saturates at 95 ms
- Threshold: score ≥ 0.20 for 3 of 5 consecutive windows triggers scale-up
  (base threshold; increases by 0.10 after each scale-up, to 0.85 max —
  all trigger modes share the same adaptive mechanism)

The latency component carries 60% of the weight. This reflects the reality
of stateful edge services: MongoDB I/O operations dominate request latency,
and storage saturation manifests as rising `T_proc` before CPU utilization
spikes. A CPU-only threshold may miss this early I/O-bound degradation
signal entirely; a latency-only threshold may capture it but lose the
confirming signal that CPU provides.

The experiment compares three trigger compositions under identical workload,
delivery cadence (push), and routing policy (lifecycle). All three are
evaluated within the same sliding-window mechanism (3 of 5 windows). The
only difference is what the score measures.

### 3.1 Three Trigger Modes

| Mode                  | Weights                | Threshold           | Encodes                                                                                                                                           |
| --------------------- | ---------------------- | ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `degradation_score` | w_cpu=0.40, w_lat=0.60 | 0.20 (golden)       | Latency-aware multi-dimensional detection: the current system default, calibrated across 15+ stability experiments                                |
| `cpu_only`          | w_cpu=1.00, w_lat=0.00 | 0.20 (uncalibrated) | CPU-only threshold: the default in Kubernetes HPA, AWS ASG, and most autoscaling platforms — applied without domain-specific tuning              |
| `latency_only`      | w_cpu=0.00, w_lat=1.00 | 0.20 (uncalibrated) | Latency-only threshold: tests whether the latency dimension alone is sufficient, or whether multi-dimensional scoring provides additional benefit |

All three modes use the same 0.20 base threshold without recalibration.
This is intentional:

- `cpu_only` tests what happens when a standard CPU-threshold autoscaling
  policy is applied to a stateful edge workload. With the golden config's
  CPU floor of 3% and span of 10, CPU needs to reach approximately 5% to
  cross the 0.20 threshold — reachable at edge container levels (2–8%).
- `latency_only` tests whether the latency dimension alone captures the
  I/O-bound degradation signal, or whether CPU provides useful confirmation
  (fewer false positives from transient latency spikes).
- `degradation_score` tests whether the weighted combination outperforms
  either single-dimension trigger.

Three pairwise comparisons isolate distinct questions:

| Comparison                        | Question                                                                                                                                     |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| cpu_only vs latency_only          | **Does the dimension matter?** If latency_only detects I/O-bound overload that cpu_only misses, the latency signal is essential.       |
| latency_only vs degradation_score | **Does multi-dimensional help?** If degradation_score detects earlier or with fewer false positives, CPU provides useful confirmation. |
| cpu_only vs degradation_score     | **Is the proposed approach better than the default?** The original comparison, contextualized by the other two.                        |

### 3.2 What Is Held Constant

- Telemetry delivery: **push mode** (ZMQ at window close) — RQ1's optimal.
- Routing policy: `topology_lifecycle` (warm lease) — RQ2's optimal.
- Scaling policy: golden configuration thresholds and cooldowns (identical
  sliding window: 3 of 5 windows for compute, 2 of 5 for storage;
  adaptive threshold increment 0.10 per spawn, max 0.85).
- Workload: canonical `phases.json` (~28 min, 6 phases at golden sizing).
- Infrastructure: two-LAN topology, WAN_RTT_MS=260, CLIENTS=48,
  DEVICES=6000, NODES=100, STORAGE_CPUS=0.10, VIP_HARD_TIMEOUT=60.
- Aggregation window: 10 s.

Vary only: **the weights that compose the degradation score** for both
compute and storage tiers (`SCALEUP_W_CPU`, `SCALEUP_W_T_PROC`,
`SCALEUP_W_STORAGE_CPU`, `SCALEUP_W_T_DB`).

---

## 4. Why This Question Exists

### 4.1 Purpose

RQ3 tests whether **what** the controller monitors matters as much as
**how fast** it receives the information (RQ1) and **how quickly** it
routes traffic after acting (RQ2). Together the three RQs form a complete
causal chain:

```
Overload occurs
    │
    ▼
[RQ3: How well is it detected?]      ← Trigger quality
    │
    ▼
[RQ1: How fast does the controller   ← Delivery cadence
 learn about the detection?]
    │
    ▼
[RQ2: How fast does new capacity     ← Routing awareness
 receive traffic?]
    │
    ▼
System responds
```

### 4.2 Literature Gap

The monitoring literature has asked "what metric to use?" — Zhou & Yong
(2024) showed that HTTP 5xx-based HPA outperforms CPU-based HPA for Nginx
web servers. The auto-scaling literature has asked "should predictions be
corrected by real-time data?" — PAHPA (Xiao et al., 2026) proposed a
binary correction mechanism. But **no study has compared a latency-aware
multi-dimensional degradation score against a CPU-only threshold for
stateful edge services**, where I/O latency is the dominant failure mode
and CPU utilization is a lagging indicator.

Across all four literature domains surveyed for this thesis — auto-scaling,
SDN load balancing, monitoring & telemetry, and resource orchestration —
every paper that studies scaling triggers treats the metric as a given:
CPU utilization (Kubernetes HPA), request rate (AWS ASG), or a pre-defined
compound metric (OSM POL). None vary the trigger composition as an
experimental variable, and none test whether latency awareness provides
detection signal that CPU alone cannot capture.

### 4.3 What Each Condition Encodes

| Condition                       | Encodes                                                                                                                                                                                                                                                                                                                              |
| ------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `degradation_score`           | The proposed approach: latency-aware, multi-dimensional detection tuned for stateful services. If this detects overload earlier or with fewer false positives than either single-dimension trigger, the thesis has evidence that multi-dimensional scoring provides irreducible benefit.                                             |
| `cpu_only` (uncalibrated)     | The industry default: CPU-threshold autoscaling applied to a stateful edge workload without domain-specific tuning. If this fires later or produces more false positives, the thesis quantifies the cost of using the wrong dimension for stateful services.                                                                         |
| `latency_only` (uncalibrated) | The right dimension alone: latency-based scaling applied without CPU confirmation. If this matches degradation_score, the latency dimension is sufficient and CPU adds no benefit. If it produces more false positives (transient latency spikes triggering unnecessary spawns), multi-dimensional scoring provides filtering value. |

A secondary experiment with **calibrated** thresholds (matching sensitivity
on a reference workload) for all three modes is deferred to future work. The
uncalibrated comparison answers the practical question: "If you take each of
these trigger strategies — the industry default, the right dimension alone,
and the proposed multi-dimensional approach — and apply them to the same
stateful edge workload, how do they compare?"

### 4.4 Integration with RQ1 and RQ2

RQ3 completes the detection→delivery→action chain. The synthesis chapter
(Ch. 8) reconstructs the compound coordination gap across all three links:

| Link      | RQ  | Gap measured                                                                                                            | Penalty                                                                      |
| --------- | --- | ----------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Detection | RQ3 | Wrong trigger dimension (CPU-only) may detect later or with more noise; latency-aware scoring captures I/O-bound signal | Quantified via breach detection time delta and false positive/negative rates |
| Delivery  | RQ1 | Poll-30s blind spot: 2 of 3 windows missed                                                                              | ~43 s added to breach detection (projected)                                  |
| Action    | RQ2 | Slowstart discovery gap: backend invisible                                                                              | ~31 s added to time-to-first-traffic (measured, n=9)                         |

The compound penalty of a fully separated architecture with a CPU-only
trigger may be unbounded — if the trigger never fires, no amount of
delivery freshness or routing awareness can compensate.

---

## 5. How It Is Measured

### 5.1 Breach Detection Time

```
breach_detection = spawn_start_ts − breach_window_end
```

The breach window is identified by an independent observer (`breach_detector.py`)
that computes the degradation score from telemetry data using the same formula
and thresholds the controller uses. For CPU-only mode, the observer uses the
same weights as the controller (w_cpu=1.0, w_lat=0.0). This preserves
methodological separation: the observer measures "when was overload visible
in telemetry according to the active trigger," not "when the controller
decided to act."

Comparison across three modes: does the degradation score's breach window
precede the CPU-only score's breach window? Does latency-only match the
degradation score's detection timing, or does CPU confirmation provide
additional lead time? If latency rises before CPU in stateful services,
latency_only and degradation_score should both detect overload earlier
than cpu_only — the question is whether degradation_score's CPU component
filters noise (fewer false positives from transient latency spikes) without
delaying detection.

### 5.2 False Positive Rate

```
false_positive_rate = spawns_during_baseline / total_spawns
```

A false positive is a spawn initiated during the baseline phase (low load,
where the static infrastructure should suffice). Both triggers use the same
sliding window (3 of 5 windows) and cooldown (45 s for compute). The
comparison tests whether CPU-only produces more spurious spawns because CPU
spikes from non-workload sources (container startup, MongoDB background
operations, OVS flow installation) cross the threshold without corresponding
latency degradation.

### 5.3 False Negative Rate

A false negative is a failure to spawn during a high-load phase where the
degradation score successfully triggers. Operationalized as:

Computed pairwise for all three modes. If degradation_score triggers N
spawns during `storage_storm` and cpu_only triggers M < N, the false
negative count is N − M. The latency_only mode provides a reference point:
if latency_only matches degradation_score's spawn count but cpu_only
misses spawns, the latency dimension is the essential signal that cpu_only
lacks. If latency_only triggers more spawns than degradation_score without
corresponding service improvement, those extra spawns are false positives
from transient latency noise.

### 5.4 Service Quality During Transitions

Same metrics as RQ1 and RQ2: per-phase p50/p95 latency, timeout rate, and
completed request volume from `client_requests.csv`. The comparison tests
whether CPU-only's delayed or absent spawns produce measurably worse
service quality during demand shifts.

### 5.5 Measurement Chain

```
Trigger mode: degradation_score → latency_only → cpu_only
  ↓
  → breach detection time: earliest (both dims) → early (latency dim) → later (CPU dim lags)
  → false positives: lowest (CPU filters latency noise) → moderate (latency spikes) → low (CPU is conservative)
  → false negatives: baseline → similar to baseline → higher (misses I/O-bound overload)
  → service quality (stress phases): best → good → worst
```

---

## 6. Evaluation Design

Nine runs, three per mode, using the canonical workload. All runs use
push-mode telemetry and topology_lifecycle routing — the optimal
downstream links. This mirrors RQ2's 9-run design (3 modes × 3 replicates).

| Run                    | Trigger           | Weights                | Threshold |
| ---------------------- | ----------------- | ---------------------- | --------- |
| **R3-DS** (×3)  | degradation_score | w_cpu=0.40, w_lat=0.60 | 0.20      |
| **R3-CPU** (×3) | cpu_only          | w_cpu=1.00, w_lat=0.00 | 0.20      |
| **R3-LAT** (×3) | latency_only      | w_cpu=0.00, w_lat=1.00 | 0.20      |

Hold constant:

- Telemetry delivery: push mode (ZMQ)
- Routing policy: `topology_lifecycle`
- Scaling policy: golden config thresholds (sliding window 3/5,
  adaptive threshold 0.10 per spawn, cooldown 45 s for compute,
  120 s for storage)
- Workload: canonical `phases.json` (~28 min, 6 phases)
- Infrastructure: `WAN_RTT_MS=260`, `CLIENTS=48`, `DEVICES=6000`,
  `NODES=100`, `STORAGE_CPUS=0.10`, `VIP_HARD_TIMEOUT=60`,
  `RANDOM_SEED=42`
- All other env vars: golden configuration
  (`current_state_integrated.env`)

Vary only: `SCALEUP_W_CPU`, `SCALEUP_W_T_PROC`, `SCALEUP_W_STORAGE_CPU`,
`SCALEUP_W_T_DB`.

### 6.1 Run Order

Grouped by trigger: all `degradation_score` reps → all `cpu_only` reps →
all `latency_only` reps. Between runs: cleanup + VM reboot as per standard
protocol.

### 6.2 Success Criteria

1. **All 9 runs complete** to idle phase with zero controller tracebacks.
2. **R3-DS replicates RQ1 push baseline behaviour** — expected bimodality
   (1–2 healthy runs with ≤2% timeout in storage_storm, 1 degraded run).
   Confirms the golden config baseline.
3. **R3-CPU produces a distinguishable outcome** — either fires later,
   produces different spawn counts, or shows different false positive/
   negative rates compared to degradation_score.
4. **R3-LAT provides the triangulation point** — shows whether latency
   alone matches degradation_score (dimension is sufficient) or whether
   CPU confirmation provides measurable benefit (multi-dimensional
   advantage).
5. **Within-mode variance is estimable** — n=3 allows μ ± σ for breach
   detection time and spawn counts per mode.

---

## 7. Expected Outcomes

1. **The latency dimension detects I/O-bound overload earlier than CPU alone.**
   Because `T_proc` rises before CPU saturates in stateful services (MongoDB
   operations block the request handler while the CPU waits on I/O),
   `latency_only` and `degradation_score` should both register degradation
   earlier than `cpu_only` — by approximately 1–2 telemetry windows
   (10–20 s). This confirms that the *dimension* matters more than the
   *weighting*.
2. **CPU-only may fire but with worse timing.** With the golden config's
   lower thresholds (CPU floor 3%, base threshold 0.20), CPU-only needs
   approximately 5% CPU to trigger — reachable at edge container levels
   (2–8%). The question is not *whether* it fires, but *when* and *with
   what noise*. CPU spikes from non-workload sources (container startup,
   MongoDB background operations, OVS flow installation) may cross the
   threshold without corresponding latency degradation, producing false
   positives. Conversely, I/O-bound overload may not push CPU high enough
   to trigger, producing false negatives.
3. **The three-mode spectrum reveals whether multi-dimensional scoring
   provides irreducible benefit.** Three scenarios:

   - `latency_only ≈ degradation_score` (both beat cpu_only): the latency
     dimension is sufficient; multi-dimensional scoring adds no benefit.
     The thesis bounds the problem — trigger quality matters, but only
     because of dimension choice, not weighting.
   - `degradation_score > latency_only > cpu_only`: multi-dimensional
     scoring provides measurable benefit over either single dimension.
     The thesis quantifies how much.
   - All three indistinguishable: trigger quality is not the bottleneck
     at this workload scale. The coordination gap is primarily about
     delivery cadence (RQ1) and routing awareness (RQ2). Still a valid
     finding — it bounds the problem.
4. **The bimodality observed in RQ1 v3 provides context.** RQ1 showed that
   the system operates near a phase transition: some runs handle
   storage_storm with 1–2% timeout, others degrade to 17–60%. RQ3 tests
   whether trigger composition shifts this phase boundary — if
   `degradation_score` keeps the system near the boundary (sometimes
   healthy, sometimes degraded) while `cpu_only` consistently falls on
   the degraded side, the thesis has evidence that trigger quality is
   the mechanism behind RQ1's bimodality.

Any outcome — degradation_score dominates, latency_only suffices, or all
three are equivalent — is a valid contribution. The thesis characterizes
the detection link of the coordination gap regardless of which direction
the evidence points.

---

## 8. Development Required

### 8.1 Trigger Mode Selection

The degradation score already accepts weights via environment variables
in `scaling_config.py`:

```python
_W_CPU    = float(os.environ.get("SCALEUP_W_CPU",    "0.40"))
_W_T_PROC = float(os.environ.get("SCALEUP_W_T_PROC", "0.60"))
```

No code changes needed. The CPU-only mode is activated by:

```env
SCALEUP_W_CPU=1.0
SCALEUP_W_T_PROC=0.0
```

### 8.2 Controller Env Overrides

- `testing/controller_env_overrides/rq3_degradation_score.env` → golden defaults (or explicit `SCALEUP_W_CPU=0.40`, `SCALEUP_W_T_PROC=0.60`, `SCALEUP_W_STORAGE_CPU=0.60`, `SCALEUP_W_T_DB=0.40`)
- `testing/controller_env_overrides/rq3_cpu_only.env` → `SCALEUP_W_CPU=1.0`, `SCALEUP_W_T_PROC=0.0`, `SCALEUP_W_STORAGE_CPU=1.0`, `SCALEUP_W_T_DB=0.0`
- `testing/controller_env_overrides/rq3_latency_only.env` → `SCALEUP_W_CPU=0.0`, `SCALEUP_W_T_PROC=1.0`, `SCALEUP_W_STORAGE_CPU=0.0`, `SCALEUP_W_T_DB=1.0`

Both compute and storage weights must be set for a consistent trigger regime.

### 8.3 Breach Detector Configuration

The independent breach detector (`breach_detector.py`, to be created as part
of RQ3 preparation) must use the same weights as the active trigger mode.
It replicates the degradation score calculation from `scaling_policy.py`
but operates on recorded telemetry data as an offline observer. The detector
reads weights from the same env vars as the controller. A pre-run validation
step confirms weight agreement between controller and observer before each
experiment.

---

## 9. Validity Threats

| Threat                                                                                                                                                                                                                                                   | Mitigation                                                                                                                                                                                                                                                                                                                                  |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **CPU-only may fire but at the wrong times.** With the golden config's CPU floor of 3% and base threshold of 0.20, CPU-only needs approximately 5% CPU to trigger — reachable at edge levels. The risk is not "never fires" but "fires on noise." | The three-mode design triangulates this: if latency_only detects the same overload without the false positives, CPU confirmation is unnecessary. If degradation_score filters noise better than latency_only, multi-dimensional scoring provides value. Either way, the three-way comparison isolates the mechanism.                        |
| **The uncalibrated threshold comparison may be considered unfair.** All three modes use 0.20 — the threshold calibrated for the weighted score, not for single-dimension use.                                                                     | The experiment explicitly tests the*uncalibrated* modes. A calibrated comparison (matching sensitivity on a reference workload) is identified as future work. The uncalibrated comparison answers the practical question: "If you take each strategy and apply it to the same workload without per-strategy tuning, how do they compare?" |
| **Bimodality from RQ1 may obscure the RQ3 signal.** If both triggers produce bimodal healthy/degraded splits, n=3 may not statistically separate them.                                                                                             | The primary comparison is qualitative: does CPU-only fire at all? If it produces zero spawns, the result is binary and conclusive regardless of variance. If it fires but produces bimodal outcomes similar to the degradation score, that is also a finding — trigger quality is not the bottleneck at this scale.                        |
| **The breach detector must use the same weights as the controller.** If the observer uses different weights than the active trigger, breach detection time measurements are invalid.                                                               | The breach detector reads weights from the same env vars as the controller. A pre-run validation step confirms weight agreement before each experiment.                                                                                                                                                                                     |
| **Storage degradation score weights also need to be changed.** The degradation score is used for both compute and storage scale-up. CPU-only should apply to both tiers for consistency.                                                           | The storage score uses separate weights (`SCALEUP_W_STORAGE_CPU`, `SCALEUP_W_T_DB`). These must also be set to CPU-only (w_storage_cpu=1.0, w_t_db=0.0) for a consistent trigger regime. Both env var sets are included in the override files.                                                                                          |

---

## 10. RQ3↔RQ1↔RQ2 Relationship

|                                | RQ3 (Detection)                                                                                                                                                 | RQ1 (Delivery)                                                                  | RQ2 (Action)                                                                |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| **Coordination gap**     | Wrong trigger dimension: CPU-only detects later/noisier than latency-aware; latency-only may lack CPU confirmation                                              | Polling blind spot: controller misses telemetry windows between polls           | Discovery gap: routing plane doesn't know about new backends                |
| **Baseline**             | cpu_only (w_cpu=1.0, w_lat=0.0)                                                                                                                                 | Poll-30s (2 of 3 windows missed)                                                | topology_slowstart (invisible until discovery)                              |
| **Proposed**             | degradation_score (w_cpu=0.40, w_lat=0.60) + latency_only triangulation                                                                                         | Push (every window, no blind spot)                                              | topology_lifecycle (warm lease at spawn time)                               |
| **Core measurement**     | Breach detection time, false positive/negative rate (pairwise)                                                                                                  | Reaction latency (spawn_done − breach_window_end)                              | Time-to-first-traffic, initial load share                                   |
| **Coordination penalty** | Detection delay from wrong dimension (quantified via breach detection time delta); noise from transient CPU/latency spikes (quantified via false positive rate) | Extra breach-detection time from missed windows (~43 s for poll-30s, projected) | Extra telemetry window before first traffic (~31 s for slowstart, measured) |

Together, RQ3, RQ1, and RQ2 characterize the three-link causal chain from
overload detection to traffic redistribution. The synthesis chapter (Ch. 8)
reconstructs the compound coordination gap across all three links.

---

## 11. Related Documents

| Document                                                                                              | Purpose                            |
| ----------------------------------------------------------------------------------------------------- | ---------------------------------- |
| [`system_to_thesis_map_rq_v2.md`](../../tese/miscelineous/system_to_thesis_map_rq_v2.md)             | Full three-pillar thesis framing   |
| [`rq1.md`](../research_questions/rq1.md)                                                             | RQ1 design — delivery cadence     |
| [`rq2.md`](../research_questions/rq2.md)                                                             | RQ2 design — routing awareness    |
| [`../../source/sdn_controller/scaling_policy.py`](../../source/sdn_controller/scaling_policy.py)     | Degradation score implementation   |
| [`../../source/sdn_controller/scaling_config.py`](../../source/sdn_controller/scaling_config.py)     | Weight and threshold configuration |
| [`../operation/testing/experiment/rq1_evaluation/`](../operation/testing/experiment/rq1_evaluation/) | RQ1 experiment plan and results    |
| [`../operation/testing/experiment/rq2_evaluation/`](../operation/testing/experiment/rq2_evaluation/) | RQ2 experiment plan and results    |
