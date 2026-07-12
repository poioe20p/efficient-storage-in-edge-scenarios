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
weighted degradation score:

```
score = 0.40 × saturate((CPU% − 5) / 10) + 0.60 × saturate((T_proc_ms − 20) / 80)
```

Where:
- `saturate(x) = clamp(x, 0, 1)`
- CPU component: activates above 5%, saturates at 15%
- Latency component: activates above 20 ms, saturates at 100 ms
- Threshold: score ≥ 0.45 for 3 of 5 consecutive windows triggers scale-up
  (base threshold; increases by 0.10 after each scale-up, to 0.85 max —
  both trigger modes share the same adaptive mechanism)

The latency component carries 60% of the weight. This reflects the reality
of stateful edge services: MongoDB I/O operations dominate request latency,
and storage saturation manifests as rising `T_proc` before CPU utilization
spikes. A CPU-only threshold may miss this early I/O-bound degradation
signal entirely.

The experiment compares the current degradation score against a CPU-only
threshold under identical workload, delivery cadence (push), and routing
policy (lifecycle). Both triggers are evaluated within the same sliding-window
mechanism (3 of 5 windows). The only difference is what the score measures.

### 3.1 Two Trigger Modes

| Mode | Weights | Threshold | Encodes |
|---|---|---|---|
| `degradation_score` | w_cpu=0.40, w_lat=0.60 | 0.45 (golden) | Latency-aware multi-dimensional detection: the current system default |
| `cpu_only` | w_cpu=1.00, w_lat=0.00 | 0.45 (uncalibrated, same as golden) | CPU-only threshold: the default in Kubernetes HPA, AWS ASG, and most autoscaling platforms |

The CPU-only mode uses the same 0.45 threshold without recalibration.
This is intentional: it tests what happens when a standard CPU-threshold
autoscaling policy is applied directly to a stateful edge workload. If
CPU-only never fires because edge container CPU levels stay below the
threshold, that is the finding — CPU-based autoscaling is fundamentally
mismatched to I/O-bound stateful services.

### 3.2 What Is Held Constant

- Telemetry delivery: **push mode** (ZMQ at window close) — RQ1's optimal.
- Routing policy: `topology_lifecycle` (warm lease) — RQ2's optimal.
- Scaling policy: golden configuration thresholds and cooldowns (identical
  sliding window: 3 of 5 windows for compute, 2 of 5 for storage).
- Workload: canonical `phases.json`.
- Infrastructure: two-LAN topology, WAN emulation, containerized services.
- Aggregation window: 10 s.

Vary only: **the weights that compose the degradation score**
(`SCALEUP_W_CPU` and `SCALEUP_W_T_PROC` env vars).

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

| Condition | Encodes |
|---|---|
| `degradation_score` | The proposed approach: latency-aware, multi-dimensional detection tuned for stateful services. If this detects overload earlier or with fewer false positives, the thesis has evidence that trigger composition matters independently of delivery cadence and routing awareness. |
| `cpu_only` (uncalibrated) | The industry default: CPU-threshold autoscaling applied to a stateful edge workload without domain-specific tuning. If this never fires, the thesis has evidence that CPU-based autoscaling is mismatched to I/O-bound services. If it fires but produces worse outcomes, the thesis quantifies the cost of the default. |

A secondary experiment with a **calibrated** CPU-only threshold (matching
the degradation score's sensitivity on a reference workload) is deferred
to future work. The uncalibrated comparison is the honest one: it answers
"what happens if you take the industry default and apply it to this
problem?"

### 4.4 Integration with RQ1 and RQ2

RQ3 completes the detection→delivery→action chain. The synthesis chapter
(Ch. 8) reconstructs the compound coordination gap across all three links:

| Link | RQ | Gap measured | Penalty |
|---|---|---|---|
| Detection | RQ3 | CPU-only may miss I/O-bound overload entirely | None or infinite (never triggers) |
| Delivery | RQ1 | Poll-30s blind spot: 2 of 3 windows missed | ~43 s added to breach detection |
| Action | RQ2 | Slowstart discovery gap: backend invisible | ~31 s added to time-to-first-traffic |

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

Comparison: does the degradation score's breach window precede the CPU-only
score's breach window? If latency rises before CPU, the degradation score
should detect overload 1–2 telemetry windows (10–20 s) earlier.

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

```
false_negatives = spawns_degradation_score − spawns_cpu_only during stress phases
```

If the degradation score triggers N spawns during `storage_storm` and
CPU-only triggers M < N, the false negative count is N − M. If CPU-only
triggers zero spawns during any stress phase, the false negative rate is
100% — CPU-only is blind to this category of overload.

### 5.4 Service Quality During Transitions

Same metrics as RQ1 and RQ2: per-phase p50/p95 latency, timeout rate, and
completed request volume from `client_requests.csv`. The comparison tests
whether CPU-only's delayed or absent spawns produce measurably worse
service quality during demand shifts.

### 5.5 Measurement Chain

```
Trigger mode: degradation_score → cpu_only
  ↓
  → breach detection time: earlier (latency leads CPU) → later or never
  → false positives: low (latency filters CPU noise) → potentially higher
  → false negatives: baseline → higher (misses I/O-bound overload)
  → service quality (stress phases): better → worse or undefined
```

---

## 6. Evaluation Design

Six runs, three per mode, using the canonical workload. All runs use
push-mode telemetry and topology_lifecycle routing — the optimal
downstream links.

| Run | Trigger | Weights | Threshold |
|---|---|---|---|
| **R3-DS** (×3) | degradation_score | w_cpu=0.40, w_lat=0.60 | 0.45 |
| **R3-CPU** (×3) | cpu_only | w_cpu=1.00, w_lat=0.00 | 0.45 |

Hold constant:
- Telemetry delivery: push mode (ZMQ)
- Routing policy: `topology_lifecycle`
- Scaling policy: golden config thresholds (sliding window 3/5, cooldown 45 s)
- Workload: canonical `phases.json` (~28 min, 10 phases)
- Infrastructure: `CLIENTS=8`, `DEVICES=600`, `NODES=100`, `RANDOM_SEED=42`
- All other env vars: golden configuration

Vary only: `SCALEUP_W_CPU` and `SCALEUP_W_T_PROC`.

### 6.1 Run Order

Grouped by trigger: all `degradation_score` reps → all `cpu_only` reps.
Between runs: cleanup + VM reboot as per standard protocol.

### 6.2 Success Criteria

1. **All 6 runs complete** to idle phase with zero controller tracebacks.
2. **R3-DS replicates RQ1 push bimodality** — 1–2 healthy runs (≤2% timeout
   in storage_storm), 1 degraded run (17–60% timeout). Confirms the baseline.
3. **R3-CPU produces a distinguishable outcome** — either zero spawns (CPU
   never crosses threshold) or consistently degraded spawn timing.
4. **Within-mode variance is estimable** — n=3 allows μ ± σ for breach
   detection time and spawn counts.

---

## 7. Expected Outcomes

1. **The degradation score detects I/O-bound overload earlier than CPU-only.**
   Because `T_proc` rises before CPU saturates in stateful services (MongoDB
   operations block the request handler, but the CPU is waiting on I/O, not
   computing), the latency component of the degradation score should register
   degradation 1–2 telemetry windows before CPU alone crosses the threshold.

2. **CPU-only may never fire at realistic edge CPU levels.** Edge containers
   in this system typically operate at 2–8% CPU. The CPU component of the
   degradation score uses a 5% floor and saturates at 15%. A CPU-only score
   needs the raw CPU value to reach approximately 9.5% to cross the 0.45
   threshold alone. If edge CPU never reaches this level — because the
   bottleneck is storage I/O, not compute — then CPU-only produces zero
   spawns. This is the strongest possible result: it demonstrates that
   CPU-based autoscaling, the default in every major platform, is structurally
   incapable of responding to the dominant failure mode in stateful edge
   services.

3. **If CPU-only does fire**, it may do so later and with more false positives.
   CPU spikes from non-workload sources (container startup, MongoDB background
   operations, OVS flow installation) may cross the threshold without
   corresponding latency degradation, producing spurious spawns during
   low-load phases.

4. **The bimodality observed in RQ1 provides context.** RQ1 v3 showed that
   the system operates near a phase transition: some runs handle storage_storm
   with 1–2% timeout, others degrade to 17–60%. If the degradation score's
   latency component is what keeps the system near this boundary — detecting
   overload early enough to sometimes succeed — then CPU-only should
   consistently fall on the degraded side of the bifurcation, eliminating
   the bimodality in favor of deterministic degradation.

If CPU-only performs equivalently to the degradation score after calibration
(deferred to future work), the thesis can bound the problem: at this workload
scale, trigger composition matters less than delivery cadence and routing
awareness. The coordination gap is primarily about *when* information arrives
and *how quickly* actions take effect, not about *what* information is
collected.

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

- `testing/controller_env_overrides/rq3_degradation_score.env` → golden defaults (or explicit `SCALEUP_W_CPU=0.40`, `SCALEUP_W_T_PROC=0.60`, `SCALEUP_W_STORAGE_CPU=0.70`, `SCALEUP_W_T_DB=0.30`)
- `testing/controller_env_overrides/rq3_cpu_only.env` → `SCALEUP_W_CPU=1.0`, `SCALEUP_W_T_PROC=0.0`, `SCALEUP_W_STORAGE_CPU=1.0`, `SCALEUP_W_T_DB=0.0`

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

| Threat | Mitigation |
|---|---|
| **CPU-only may never fire.** Edge CPU levels (2–8%) may never cross the 0.45 threshold with w_cpu=1.0. | This is not a threat — it is the **central finding**. The thesis reports: "CPU-only threshold with industry-standard configuration produced zero spawns across 3 runs. The workload's dominant failure mode (storage I/O saturation) is invisible to CPU-based autoscaling." |
| **The uncalibrated threshold comparison may be considered unfair.** CPU-only uses the same 0.45 threshold that was calibrated for the weighted score. | The experiment explicitly tests the *uncalibrated* industry default. A calibrated comparison (matching sensitivity on a reference workload) is identified as future work. The uncalibrated comparison answers the practical question: "If you take a standard CPU-HPA and point it at a stateful edge service, does it work?" The answer is valuable either way. |
| **Bimodality from RQ1 may obscure the RQ3 signal.** If both triggers produce bimodal healthy/degraded splits, n=3 may not statistically separate them. | The primary comparison is qualitative: does CPU-only fire at all? If it produces zero spawns, the result is binary and conclusive regardless of variance. If it fires but produces bimodal outcomes similar to the degradation score, that is also a finding — trigger quality is not the bottleneck at this scale. |
| **The breach detector must use the same weights as the controller.** If the observer uses different weights than the active trigger, breach detection time measurements are invalid. | The breach detector reads weights from the same env vars as the controller. A pre-run validation step confirms weight agreement before each experiment. |
| **Storage degradation score weights also need to be changed.** The degradation score is used for both compute and storage scale-up. CPU-only should apply to both tiers for consistency. | The storage score uses separate weights (`SCALEUP_W_STORAGE_CPU`, `SCALEUP_W_T_DB`). These must also be set to CPU-only (w_storage_cpu=1.0, w_t_db=0.0) for a consistent trigger regime. Both env var sets are included in the override files. |

---

## 10. RQ3↔RQ1↔RQ2 Relationship

| | RQ3 (Detection) | RQ1 (Delivery) | RQ2 (Action) |
|---|---|---|---|
| **Coordination gap** | Trigger blindness: CPU-only cannot see I/O-bound overload | Polling blind spot: controller misses telemetry windows between polls | Discovery gap: routing plane doesn't know about new backends |
| **Baseline** | cpu_only (w_cpu=1.0, w_lat=0.0) | Poll-30s (2 of 3 windows missed) | topology_slowstart (invisible until discovery) |
| **Proposed** | degradation_score (w_cpu=0.40, w_lat=0.60) | Push (every window, no blind spot) | topology_lifecycle (warm lease at spawn time) |
| **Core measurement** | Breach detection time, false positive/negative rate | Reaction latency (spawn_done − breach_window_end) | Time-to-first-traffic, initial load share |
| **Coordination penalty** | Delayed or absent detection (I/O-bound overload invisible to CPU) | Extra breach-detection time from missed windows (~43 s for poll-30s) | Extra telemetry window before first traffic (~31 s for slowstart) |

Together, RQ3, RQ1, and RQ2 characterize the three-link causal chain from
overload detection to traffic redistribution. The synthesis chapter (Ch. 8)
reconstructs the compound coordination gap across all three links.

---

## 11. Related Documents

| Document | Purpose |
|---|---|
| [`system_to_thesis_map_rq_v2.md`](../../tese/miscelineous/system_to_thesis_map_rq_v2.md) | Full three-pillar thesis framing |
| [`rq1.md`](../research_questions/rq1.md) | RQ1 design — delivery cadence |
| [`rq2.md`](../research_questions/rq2.md) | RQ2 design — routing awareness |
| [`../../source/sdn_controller/scaling_policy.py`](../../source/sdn_controller/scaling_policy.py) | Degradation score implementation |
| [`../../source/sdn_controller/scaling_config.py`](../../source/sdn_controller/scaling_config.py) | Weight and threshold configuration |
| [`../operation/testing/experiment/rq1_evaluation/`](../operation/testing/experiment/rq1_evaluation/) | RQ1 experiment plan and results |
| [`../operation/testing/experiment/rq2_evaluation/`](../operation/testing/experiment/rq2_evaluation/) | RQ2 experiment plan and results |
