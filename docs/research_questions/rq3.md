# RQ3 — Trigger Composition Characterization

**Thesis pillar**: Detection
**Status**: Designed
**Gap basis**: [`global_literature_review.md`](../../tese/literature_review/global_literature_review.md) §7 Gap Matrix — zero papers across six domains vary trigger composition as an experimental variable.

---

## 1. What the Literature Gap Is

The global literature review surveys 60+ papers across six domains. The gap
matrix (§7) identifies four dimensions no paper addresses simultaneously.
One column — **trigger composition varied?** — is empty. Every paper that
studies auto-scaling triggers treats the metric as a given: CPU utilization
(Kubernetes HPA), request rate (AWS ASG), or a pre-defined compound metric
(OSM POL). None vary what goes into the trigger and measure what happens.

RQ3 fills this column. It does not claim a better formula. It characterizes
what each composition does under the same conditions.

### 1.1 Prerequisite: Scaling Must Produce Visible Improvement

For trigger composition to be a meaningful variable, scaling up must
demonstrably improve the conditions the trigger measures: CPU utilization
and processing latency. If adding capacity does not reduce CPU or latency,
then the choice of trigger is irrelevant — no composition can detect
overload that scaling cannot relieve.

This prerequisite must be satisfied at whatever resource configuration is
chosen for the evaluation. The resource limits are not fixed in advance;
they are selected from the range explored during pre-experiment calibration
to meet a specific condition: **during a stress phase, the pre-scale window
shows elevated CPU and latency, and the post-scale window (after spawns
complete) shows a measurable reduction in both.**

Two bodies of prior work identify candidate configurations:

**Mechanism necessity experiments (v6)**. At WAN = 260 ms with storage
`--cpus` = 0.10–0.15 and edge `--cpus` = 0.30, enabling Tier 1 selective
sync reduced median tier1_hotspot latency by 39 % (5,922 ms → 3,633 ms).
Storage elasticity at these CPU limits produced measurable CPU distribution
across additional MongoDB nodes. These experiments confirm the system
responds to provisioning changes.

**Phase 1a resource calibration (C0–C5)**. A range of `STORAGE_CPUS`
(0.10 → 0.03) and `EDGE_CPUS` (0.30 → 0.03) was tested. Multiple
configurations produced stress-phase overload with successful scale-up.
The winning configuration for RQ3 is whichever configuration shows the
clearest pre-scale → post-scale improvement in both CPU and latency for
both compute and storage tiers — not necessarily C4.

The comparison structure for each RQ3 run is: **non-stress baseline →
pre-scale stress onset → post-scale stabilized stress**. The degradation
score must cross threshold during pre-scale stress; the post-scale window
must show reduced CPU and latency relative to pre-scale; and this cycle
must hold for both tiers. The resource configuration that best satisfies
this condition is selected before the 9-run evaluation begins.

---

## 2. Research Question

> *For stateful edge services under constrained resources, how does the
> composition of the degradation score — which signals are included and
> at what weight — affect detection behavior?*

### 2.1 Decomposed Questions

| SQ             | Question                                                                                                                                                            |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **SQ3a** | Given identical floors, spans, thresholds, and sliding-window parameters, do different trigger compositions produce different false-positive rates during baseline? |
| **SQ3b** | Do different trigger compositions produce different detection sensitivity during stress — spawn count, time-to-first-spawn, and spawns missed?                     |
| **SQ3c** | Do detection differences produce measurable service quality differences — per-phase latency, timeout rate, and completed request volume?                           |

---

## 3. What Is Being Measured

### 3.0 Why This Formula

The degradation score combines CPU and processing latency because, in
stateful edge services backed by MongoDB, these two signals capture
different aspects of system health that neither captures alone:

**CPU utilization** reflects resource saturation — how close the container
is to its CPU limit. At C4 constraints, baseline CPU fluctuates
substantially (22–92 % in 5 s windows on the aggregator node) from
non-workload sources: container startup, OVS flow installation, MongoDB
background operations. A CPU spike alone does not mean the service is
degraded.

**Processing latency** reflects service quality — how long requests take.
For compute (T_proc), it captures end-to-end request duration including
MongoDB I/O. For storage (T_db), it captures database operation latency.
Latency rises when the database is saturated, when reads go cross-region
over WAN, or when request queues build up. But transient latency spikes
occur without CPU pressure — a single slow MongoDB operation, a WAN
fluctuation, or a client burst.

**Together**, the two signals cross-validate: a simultaneous spike in both
dimensions indicates genuine overload — the machine is saturated AND
requests are suffering. A spike in only one dimension is more likely noise.
This is why the formula has the structure it does, and why the comparison
of single-dimension vs. composite triggers is meaningful: it tests whether
both signals together provide information that either alone lacks.

The specific weights (0.40/0.60 for compute, 0.60/0.40 for storage)
emerged from pre-experiment calibration at C4 and are held constant for
the composite mode. Weight sensitivity is deferred to future work.

### 3.1 The Detection Mechanism

The controller receives telemetry summaries from edge servers. Each summary
contains CPU utilization and processing latency (T_proc for compute, T_db
for storage) measured over the same window. The controller evaluates a
degradation score:

```
score = w_cpu × saturate((CPU% − floor_cpu) / span_cpu)
      + w_lat × saturate((latency_ms − floor_lat) / span_lat)
```

When the score exceeds a threshold for a configurable number of consecutive
windows, the controller triggers scale-up. All trigger modes share the same
floors, spans, thresholds, sliding-window mechanism, cooldowns, and adaptive
threshold increment. Only the weights differ.

### 3.2 Three Trigger Modes

| Mode                  | Compute weights        | Storage weights        | Encodes                                                                           |
| --------------------- | ---------------------- | ---------------------- | --------------------------------------------------------------------------------- |
| `degradation_score` | w_cpu=0.40, w_lat=0.60 | w_cpu=0.60, w_tdb=0.40 | Both signals. The system default.                                                 |
| `cpu_only`          | w_cpu=1.00, w_lat=0.00 | w_cpu=1.00, w_tdb=0.00 | CPU only. The default in Kubernetes HPA, AWS ASG, and most autoscaling platforms. |
| `latency_only`      | w_cpu=0.00, w_lat=1.00 | w_cpu=0.00, w_tdb=1.00 | Latency only. The dimension that matters for I/O-bound stateful services.         |

### 3.3 Why Identical Parameters Are the Fair Comparison

All three modes use the same floors, spans, thresholds, and window counts.
A CPU spike of 82% produces the same CPU component value in every mode:
`sat((82 − floor) / span)`. The only difference is whether that component
contributes 40%, 100%, or 0% to the final score.

If cpu_only were given a higher floor to suppress FPs, that higher floor
would also suppress stress detection — the comparison would test calibration
asymmetry, not trigger composition. Identical parameters mean any behavioral
difference is caused by the weights alone. The FP rate differences between
modes are the finding, not a calibration artifact to be eliminated.

### 3.4 What Is Held Constant

| Parameter                                                                             | Fixed because                                            |
| ------------------------------------------------------------------------------------- | -------------------------------------------------------- |
| Resource constraints | Selected from Phase 1a calibration — the config where pre-scale → post-scale improvement is clearest (§1.1) |
| Telemetry delivery (push)                                                             | Eliminates the monitoring blind spot                     |
| Routing policy (warm lease)                                                           | Eliminates the LB discovery gap                          |
| Workload (`phases.json`)                                                            | Identical across all runs                                |
| Floors, spans, thresholds, window size, REQUIRED count, cooldowns, adaptive increment | Identical across all modes                               |
| RANDOM_SEED                                                                           | Workload reproducibility                                 |

Vary only: score weights (`SCALEUP_W_CPU`, `SCALEUP_W_T_PROC`,
`SCALEUP_W_STORAGE_CPU`, `SCALEUP_W_T_DB`).

---

## 4. Why This Question Exists

### 4.1 It Fills a Documented Gap

The global literature review's gap matrix (§7) shows: across 60+ papers in
six domains, no paper varies trigger composition experimentally. The
auto-scaling literature treats the trigger metric as a given. RQ3 asks
what happens when you change it.

### 4.2 It Completes the Detection→Delivery→Action Chain

RQ1 characterizes delivery (how fast signals arrive). RQ2 characterizes
action (how fast new capacity receives traffic). RQ3 characterizes detection
(what signals trigger action). Three links, three characterizations.

### 4.3 Any Outcome Is Informative

- If all three modes produce identical behavior: trigger composition doesn't
  matter at C4. The detection link is not the bottleneck.
- If cpu_only produces more FPs during baseline (CPU spikes without latency
  still cross threshold): CPU carries noise that latency confirmation filters.
- If latency_only produces more FPs (transient latency spikes without CPU
  still cross threshold): latency carries noise that CPU confirmation filters.
- If composite produces the fewest FPs: cross-signal confirmation filters
  noise that either single dimension triggers on.

---

## 5. How It Is Measured

### 5.1 Baseline False Positives (SQ3a)

Score-triggered spawns during the baseline phase. Reserve spawns (persistent
storage mechanism) excluded. Compared across the three modes.

### 5.2 Spawn Count Per Stress Phase (SQ3b)

Spawns during `storage_storm` and `compute_spike`, counted per mode across
3 replicates.

### 5.3 Time-to-First-Spawn (SQ3b)

```
ttfs = first_spawn_start_ts − phase_start_ts
```

How quickly each mode responds to the onset of a stress phase.

### 5.4 Service Quality (SQ3c)

Per-phase p50/p95 latency, timeout rate, and completed request volume.
Compared across modes — a mode that misses spawns during stress should
show higher latency and timeout rates.

### 5.5 Score Component Decomposition

Per-window breakdown of score into CPU and latency components. Shows which
dimension drives the score in each mode during each phase. Diagnostic, not
primary evidence.

---

## 6. Evaluation Design

Nine runs, three per mode. All at the resource configuration selected in §1.1, all with identical parameters.

| Run                    | Trigger           | Compute weights | Storage weights |
| ---------------------- | ----------------- | --------------- | --------------- |
| **R3-DS** (×3)  | degradation_score | 0.40 / 0.60     | 0.60 / 0.40     |
| **R3-CPU** (×3) | cpu_only          | 1.00 / 0.00     | 1.00 / 0.00     |
| **R3-LAT** (×3) | latency_only      | 0.00 / 1.00     | 0.00 / 1.00     |

### 6.1 Parameter Selection

Floors, spans, and thresholds are applied identically to all three modes.
The recommended starting point is the Phase 1c calibration values (C3b
config), adjusted for whichever resource configuration is selected in
§1.1. Any parameter set that is reasonable for all modes is valid — the
comparison is between trigger compositions under the same conditions,
not between parameter sets.

### 6.2 Run Order

Grouped by trigger. Between runs: full cleanup + VM reboot.

### 6.3 Success Criteria

1. All 9 runs complete with zero controller tracebacks.
2. Within-mode consistency across 3 replicates.
3. At least one pairwise comparison produces distinguishable spawn counts
   or service quality outcomes.

---

## 7. Expected Outcomes

### 7.1 Baseline Behavior (SQ3a)

cpu_only will produce more FPs than composite because CPU spikes during
baseline (72–92% in 5 s windows) cross the threshold when CPU is the only
signal — there is no latency confirmation to filter them. latency_only will
also produce more FPs because transient T_proc spikes (100–255ms) cross
the threshold when latency is the only signal.

The composite score requires both to spike simultaneously, which happens
less often. The FP rate difference between modes is the evidence that
cross-signal confirmation filters noise.

### 7.2 Stress Detection (SQ3b)

All three modes should fire during stress — CPU reaches 68–84% and T_proc
reaches 180–255ms during compute_spike. The differences are in spawn count
(does latency-only fire more often?) and timing (does latency fire earlier
than CPU?).

### 7.3 Service Quality (SQ3c)

If extra spawns from single-dimension modes don't improve service quality,
those spawns are waste — the system scaled unnecessarily. If missed spawns
from a mode produce worse service quality, that mode is failing to detect
real overload.

---

## 8. Development Required

### 8.1 Trigger Mode Selection

Already supported via environment variables in `scaling_config.py`. No
code changes needed.

### 8.2 Env Override Files

Three files under `source/scripts/testing/controller_env_overrides/`,
all derived from the same base configuration, varying only the four
weight variables.

### 8.3 Breach Detector

`breach_detector.py` replays recorded telemetry through each mode's score
function offline. Reads weights from the same env vars as the controller.
Used for time-to-first-spawn measurement.

---

## 9. Validity Threats

| Threat                                                                                                                                                                                                                                                                                                                                                                          | Mitigation |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------- |
| **The chosen floors/thresholds may advantage one mode.** The parameters are applied identically to all modes. If a reviewer argues that cpu_only should have a higher CPU floor, the response is: that higher floor would also suppress stress detection. The parameters must be the same for all modes because changing them would test calibration, not composition.    |            |
| **The composite score has more parameters.** It has two degrees of freedom (two weights) vs one for single-dimension modes. This is inherent to the comparison — the thesis does not claim parameter-count fairness. It claims that the literature has never varied composition, and these three compositions represent points in the design space worth characterizing. |            |
| **n=3 provides limited statistical power.** Three replicates allow μ ± σ. Consistency across replicates within a mode, combined with non-overlapping ranges between modes, is the evidentiary standard.                                                                                                                                                                |            |
| **Storage and compute tiers may respond differently.** Storage uses T_db; compute uses T_proc. The two tiers are analyzed separately. Consistent results across both strengthen the finding.                                                                                                                                                                              |            |
| **Signal aggregation happens at the edge server, not the controller.** Both signals share a measurement interval because the edge server measures them during request processing. The controller receives the pre-aggregated summary and evaluates it.                                                                                                                    |            |

---

## 10. Related Documents

| Document                                                                                           | Purpose                                             |
| -------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| [`global_literature_review.md`](../../tese/literature_review/global_literature_review.md)         | Literature gap — trigger composition column (§7)  |
| [`calibration_results.md`](../operation/testing/experiment/rq3_evaluation/calibration_results.md) | C4 baseline calibration — parameter starting point |
| [`calibration_plan.md`](../operation/testing/experiment/rq3_evaluation/calibration_plan.md)       | Full calibration plan                               |
| [`scaling_config.py`](../../source/sdn_controller/scaling_config.py)                              | Weight and threshold configuration                  |
| [`scaling_policy.py`](../../source/sdn_controller/scaling_policy.py)                              | Degradation score implementation                    |
