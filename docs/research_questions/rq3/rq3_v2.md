# RQ3 v2 — Trigger Composition Characterization

**Thesis pillar**: Detection (the signal link)
**Status**: Designed — measurement framework upgraded to v2, experiment pending
**Previous version**: [`rq3.md`](rq3.md) (v1 — conceptual measurement definitions)
**Gap basis**: [`global_literature_review.md`](../../tese/literature_review/global_literature_review.md) §7 Gap Matrix — zero papers across six domains vary trigger composition as an experimental variable.

---

## 1. Thesis Context

This thesis investigates whether collapsing three traditionally separated
control-plane concerns — **information acquisition** (monitoring), **backend
selection** (load balancing), and **infrastructure adaptation** (auto-scaling)
— into a single SDN controller process eliminates coordination gaps that
degrade service quality during demand shifts.

RQ1 characterised the **delivery** link: does push-mode telemetry (in-process)
beat polling (separated monitoring) by eliminating the blind spot between
scrapes? The mechanism was missed telemetry windows.

RQ2 characterises the **action** link: does spawn-time routing awareness
(warm lease, in-process) beat discovery-time awareness (slow-start ramp,
simulating a separated LB) by eliminating the discovery gap?

RQ3 characterises the **detection** link: what signals should enter the
degradation score that triggers scale-up? This is the third and final link
in the detection→delivery→action chain. RQ3 fills a documented literature
gap — across 60+ papers surveyed, **no paper varies trigger composition as
an experimental variable**. Every auto-scaling study treats its trigger
metric as a given (CPU for Kubernetes HPA, request rate for AWS ASG, a
pre-defined compound for OSM POL). RQ3 makes composition the independent
variable.

---

## 2. Research Question

> For stateful edge services under constrained resources, how does the
> composition of the degradation score — which signals are included and
> at what weight — affect detection behavior?

### 2.1 Decomposed Questions

| SQ | Question |
|---|---|
| **SQ3a** | Given identical floors, spans, thresholds, and sliding-window parameters, do different trigger compositions produce different false-positive rates during baseline? |
| **SQ3b** | Do different trigger compositions produce different detection sensitivity during stress — spawn count, time-to-first-spawn, and spawns missed? |
| **SQ3c** | Do detection differences produce measurable service quality differences — per-phase latency, timeout rate, and completed request volume? |

---

## 3. What Is Being Investigated

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
threshold increment. **Only the weights differ.**

### 3.2 Why This Formula

The degradation score combines CPU and processing latency because, in
stateful edge services backed by MongoDB, these two signals capture
different aspects of system health that neither captures alone:

**CPU utilization** reflects resource saturation — how close the container
is to its CPU limit. At constrained resources, baseline CPU fluctuates
substantially from non-workload sources: container startup, OVS flow
installation, MongoDB background operations. A CPU spike alone does not
mean the service is degraded.

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
emerged from pre-experiment calibration and are held constant for the
composite mode. Weight sensitivity is deferred to future work.

### 3.3 Three Trigger Modes

| Mode | Compute weights | Storage weights | Encodes |
|---|---|---|---|
| `degradation_score` | w_cpu=0.40, w_lat=0.60 | w_cpu=0.60, w_tdb=0.40 | **Cross-signal confirmation.** Both signals must spike simultaneously to trigger. The system default. |
| `cpu_only` | w_cpu=1.00, w_lat=0.00 | w_cpu=1.00, w_tdb=0.00 | **CPU only.** The industry default — Kubernetes HPA, AWS ASG, and most autoscaling platforms use CPU utilization as the sole trigger metric. |
| `latency_only` | w_cpu=0.00, w_lat=1.00 | w_cpu=0.00, w_tdb=1.00 | **Latency only.** The dimension that matters for I/O-bound stateful services — what users actually experience. |

### 3.4 Why Identical Parameters Are the Fair Comparison

All three modes use the same floors, spans, thresholds, and window counts.
A CPU spike of 82% produces the same CPU component value in every mode:
`sat((82 − floor) / span)`. The only difference is whether that component
contributes 40%, 100%, or 0% to the final score.

If `cpu_only` were given a higher floor to suppress false positives, that
higher floor would also suppress stress detection — the comparison would
test calibration asymmetry, not trigger composition. Identical parameters
mean any behavioral difference is caused by the weights alone. The false
positive rate differences between modes are the finding, not a calibration
artifact to be eliminated.

### 3.5 What Is Held Constant

| Parameter | Fixed because |
|---|---|
| Resource constraints | Selected from Phase 1a calibration — the config where pre-scale→post-scale improvement is clearest (§3.6) |
| Telemetry delivery (push) | Eliminates the monitoring blind spot (RQ1's domain) |
| Routing policy (warm lease) | Eliminates the LB discovery gap (RQ2's domain) |
| Workload (`phases.json`) | Identical across all runs |
| Floors, spans, thresholds, window size, REQUIRED count, cooldowns, adaptive increment | Identical across all modes |
| RANDOM_SEED | Workload reproducibility |

Vary only: score weights (`SCALEUP_W_CPU`, `SCALEUP_W_T_PROC`,
`SCALEUP_W_STORAGE_CPU`, `SCALEUP_W_T_DB`).

### 3.6 Prerequisite: Scaling Must Produce Visible Improvement

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

**Mechanism necessity experiments (v6).** At WAN = 260 ms with storage
`--cpus` = 0.10–0.15 and edge `--cpus` = 0.30, enabling Tier 1 selective
sync reduced median tier1_hotspot latency by 39 % (5,922 ms → 3,633 ms).
Storage elasticity at these CPU limits produced measurable CPU distribution
across additional MongoDB nodes. These experiments confirm the system
responds to provisioning changes.

**Phase 1a resource calibration (C0–C5).** A range of `STORAGE_CPUS`
(0.10 → 0.03) and `EDGE_CPUS` (0.30 → 0.03) was tested. Multiple
configurations produced stress-phase overload with successful scale-up.
The winning configuration for RQ3 is whichever configuration shows the
clearest pre-scale→post-scale improvement in both CPU and latency for
both compute and storage tiers — not necessarily C4.

The comparison structure for each RQ3 run is: **non-stress baseline →
pre-scale stress onset → post-scale stabilized stress**. The degradation
score must cross threshold during pre-scale stress; the post-scale window
must show reduced CPU and latency relative to pre-scale; and this cycle
must hold for both tiers. The resource configuration that best satisfies
this condition is selected before the 9-run evaluation begins.

---

## 4. Why This Question Exists

### 4.1 It Fills a Documented Gap

The global literature review's gap matrix (§7) shows: across 60+ papers in
six domains, no paper varies trigger composition experimentally. The
auto-scaling literature treats the trigger metric as a given. RQ3 asks
what happens when you change it.

### 4.2 It Completes the Detection→Delivery→Action Chain

| RQ | Link | What it characterises |
|---|---|---|
| RQ3 | **Detection** | What signals trigger action — which dimensions enter the score and at what weight |
| RQ1 | **Delivery** | How fast signals arrive — push (every window) vs poll (blind spots between scrapes) |
| RQ2 | **Action** | How fast new capacity receives traffic — spawn-time warm lease vs discovery-time ramp |

Three links, three characterisations. RQ3 completes the thesis's
three-pillar evaluation of the unified control plane.

### 4.3 Any Outcome Is Informative

- If all three modes produce identical behavior: trigger composition doesn't
  matter at the calibrated resource level. The detection link is not the
  bottleneck — delivery (RQ1) or action (RQ2) dominate.
- If `cpu_only` produces more false positives during baseline (CPU spikes
  without latency still cross threshold): CPU carries noise that latency
  confirmation filters. The industry default is suboptimal for stateful
  edge services.
- If `latency_only` produces more false positives (transient latency spikes
  without CPU still cross threshold): latency carries noise that CPU
  confirmation filters.
- If composite produces the fewest false positives AND equivalent or better
  stress detection: cross-signal confirmation filters noise that either
  single dimension triggers on, without sacrificing sensitivity.

---

## 5. How It Is Measured

The v2 measurement framework decomposes trigger composition effects into
seven metrics (M1–M7) organised by what they measure: **detection quality**
and **service quality**. Together they triangulate the impact of signal
composition from every angle — whether the trigger fires when it should not
(false positives), whether it fires when it should (sensitivity), whether
it fires quickly enough (speed), and whether detection differences propagate
to user-visible outcomes.

### 5.1 Detection Quality — M1–M4

Measures the **direct mechanism**: how trigger composition affects the
controller's decision to scale.

#### M1 — Baseline False-Positive Spawns

**Purpose**: Does the trigger fire during quiescent state when no stress
is present? Counts score-triggered spawns during the `baseline` phase.
Reserve spawns (persistent storage mechanism) are excluded. This is the
primary SQ3a metric.

**Expectation**: `cpu_only` > `latency_only` > `degradation_score`. CPU
spikes during baseline (from container startup, OVS flow installation,
MongoDB background operations) cross the threshold when CPU is the only
signal — there is no latency confirmation to filter them. `latency_only`
may also produce FPs from transient T_proc spikes, but less frequently
at constrained resources. Composite requires both to spike simultaneously,
which happens least often.

#### M2 — Stress Spawn Count

**Purpose**: Does the trigger fire enough during genuine overload? Counts
score-triggered spawns per stress phase (`storage_storm`, `tier1_hotspot`,
`reverse_hotspot`, `compute_spike`), compared across three modes with n=3
replicates. This is the primary SQ3b sensitivity metric.

**Expectation**: All three modes should fire during stress — CPU reaches
saturation and T_proc rises during compute_spike; T_db rises during
storage_storm. The differences are in spawn count: does `latency_only`
fire more often (because latency rises before CPU saturates)? Does
composite fire fewer times (because it waits for both signals)?

#### M3 — Time-to-First-Spawn (TTFS)

```
ttfs = first_spawn_start_ts − phase_start_ts
```

**Purpose**: How quickly does each mode respond to stress onset? Computed
per stress phase, per mode. Box plot with individual spawn events as
scatter dots across replicates.

**Expectation**: `latency_only` may fire earlier than `cpu_only` because
T_proc rises before CPU saturates — queueing precedes saturation. Composite
may fire at an intermediate time. Wide IQR within a mode indicates
inconsistent detection timing.

#### M4 — Missed Detections

**Purpose**: Did the trigger fail to fire when it should have? Identifies
stress phases where mean per-node CPU exceeds threshold AND p95 latency
exceeds threshold, yet fewer than 1 spawn occurred within the phase time
bounds. Accounts for the controller's adaptive threshold escalation.

**Expectation**: Composite may miss detections that single-dimension modes
catch, if the threshold is calibrated such that simultaneous spikes are
required but rarely co-occur within the same window. Single-dimension modes
should miss fewer (they have only one condition to satisfy). If all modes
detect equally, detection sensitivity is not the bottleneck — a valid
bounding result.

### 5.2 Service Quality — M5–M7

Measures the **user-visible outcome**: whether detection differences
propagate to latency, timeouts, and throughput.

#### M5 — Per-Phase Latency

**Purpose**: Do users experience different latency depending on which
signals trigger scaling? Computes p50/p95/p99 latency per phase per mode,
disaggregated so that non-stress phases (where routing quality dominates)
are not conflated with storage phases (where I/O dominates) or compute
phases (where CPU saturation and routing interact).

**Phase-dependent latency regimes (theoretical expectation):**

| Phase type | Phases | Dominant latency factor | Expected mode effect |
|---|---|---|---|
| **Baseline** | baseline | Routing quality — the only phase guaranteed to start with no prior stress carryover | Mode differences most visible. FP spawns during baseline may create unnecessary capacity that lowers latency — a perverse "benefit" of false positives |
| **Storage stress** | storage_storm, tier1_hotspot, reverse_hotspot | Storage I/O (content_update, content_aggregate) | All modes expected to converge — I/O dominates routing choice and trigger composition |
| **Compute stress** | compute_spike | CPU saturation (feed_ranking, service_pressure) | Modes may diverge — uneven spawn counts create different capacity levels |
| **Post-stress** | inter_hotspot_cooldown, demand_drop | Mixed — residual effects from preceding stress phase | Mode differences attenuated relative to baseline; backends from preceding stress phases may still be alive |

**Expectation**: Mode differences largest in baseline (routing quality,
FP spawns). Convergence in storage stress (I/O dominates). Possible
divergence in compute stress (capacity differences matter). Attenuated
effects in post-stress phases.

#### M6 — Timeout Rate

**Purpose**: Did users experience outright failures? Per-phase timeout
rate (latency ≥ 29.9 s). The user-visible harm metric. If a mode misses
spawns, users should experience more timeouts.

**Expectation**: All modes should show low timeout rates if the resource
configuration is calibrated correctly (§3.6). Differences, if any, would
indicate that a mode is failing to detect real overload — a detection
failure with user-visible consequences.

#### M7 — Throughput

**Purpose**: Did detection differences affect completed work? Completed
requests per stress phase, compared across modes. This is the **key
empirical question** for RQ3:

- If `cpu_only` spawns more nodes but throughput is identical to composite:
  the extra spawns are **waste** — composite filtering is valuable, it
  achieves the same outcome with fewer resources.
- If `cpu_only` spawns more nodes AND completes more requests: composite
  is **under-detecting** — it misses real overload that additional capacity
  would relieve.
- If all modes show identical spawn counts and throughput: trigger
  composition does not matter at this resource level — detection is not
  the bottleneck.

**Expectation**: This is the empirical question the experiment answers.
The thesis does not pre-commit to an outcome.

### 5.3 Diagnostic — Score Component Decomposition

Per-window breakdown of the degradation score into its CPU and latency
components, shown as a multi-panel line chart (one panel per mode, one
representative replicate per mode — the median replicate by total spawn
count). Horizontal dashed line at the trigger threshold. Shaded regions
mark stress phases.

This graph explains **why** the modes behaved differently. It shows whether
`cpu_only` fires on CPU spikes that composite ignores (confirming the noise
filtering hypothesis), whether `latency_only` fires earlier than `cpu_only`
(confirming the queueing-before-saturation hypothesis), and whether
composite requires both signals to cross simultaneously (confirming the
cross-validation hypothesis).

This is a diagnostic, not primary evidence — the statistical separation
between modes is established by G1–G7 with error bars across replicates.
G8 provides the mechanistic narrative.

### 5.4 Measurement Chain (Causal Model)

```text
TRIGGER_COMPOSITION (w_cpu, w_lat)
  │
  ├─→ Detection Quality (§5.1)
  │     ├─ FP spawns during baseline (M1) ─────── does it fire when it shouldn't?
  │     ├─ Spawn count during stress (M2) ──────── does it fire enough when it should?
  │     ├─ TTFS (M3) ───────────────────────────── how quickly does it respond?
  │     ├─ Missed detections (M4) ──────────────── does it fail to fire when it should?
  │     └─ Score decomposition (G8) ────────────── what signal drives the decision?
  │
  └─→ Service Quality (§5.2)
        ├─ Per-phase latency (M5) ──────────────── user experience across all phases
        ├─ Timeout rate (M6) ────────────────────── outright failures
        └─ Throughput (M7) ──────────────────────── completed work — waste or under-detection?
```

The causal interpretation: trigger composition determines **which signals**
contribute to the degradation score (CPU only, latency only, or both).
This determines **when** the score crosses threshold — during genuine
overload (correct detection), during baseline noise (false positive), or
never during overload (missed detection). Spawn count and timing (M2, M3)
determine **how much** capacity is available and **when** it arrives.
Available capacity determines **what** latency, timeout rate, and throughput
users experience (M5, M6, M7).

Detection quality (§5.1) measures the **direct mechanism**. Service quality
(§5.2) measures the **user-visible outcome**. The diagnostic decomposition
(G8) provides the **mechanistic explanation** for observed differences.
All three are necessary: mechanism without user impact is academic; user
impact without mechanism is unexplained.

### 5.5 Success Criteria (C1–C8)

| # | Criterion | Maps to | Expectation |
|---|---|---|---|
| C1 | Run completion | — | All 9 runs complete → idle, zero controller tracebacks |
| C2 | Within-mode consistency | M1–M7 | n=3 replicates per mode show consistent spawn counts and latency profiles |
| C3 | Baseline FP separation | M1, G1 | At least one pairwise comparison shows distinguishable FP spawn counts between modes |
| C4 | Stress detection separation | M2, M3, G2, G3 | At least one pairwise comparison shows distinguishable spawn counts or TTFS |
| C5 | Missed detection asymmetry | M4 | At least one mode misses ≥1 detection that another mode catches, OR all modes detect equally (valid bounding result) |
| C6 | Service quality separation | M5, G4 | At least one pairwise comparison shows distinguishable per-phase latency |
| C7 | Throughput-waste relationship | M7, G7 | If spawn counts differ between modes, throughput either differs (under-detection) or does not (waste) — both outcomes are informative |
| C8 | Scaling prerequisite | §3.6 | Pre-scale→post-scale improvement in CPU and latency confirmed at selected resource configuration |

---

## 6. Graph Summary

### 6.1 Thesis Graphs (G1–G8)

| # | Graph | Domain | Type | Variance shown via | What it captures |
|---|---|---|---|---|---|
| **G1** | Baseline FP Spawns by Mode | Detection | Grouped bar, 3 bars (DS/CPU/LAT). Error bars: SEM across n=3 replicates. Scatter dots: per-replicate values. | SEM + scatter dots | Which modes fire unnecessarily during quiescent state. The primary SQ3a graph. |
| **G1b** | FP Spawn Score Components at Trigger | Detection | 2D scatter: x=CPU component, y=Latency component, color=mode. One point per FP spawn event (aggregated across replicates). | Position in 2D space | What combination of signal values triggered each FP spawn. Reveals whether cpu_only FPs are "pure CPU" spikes (high CPU, low latency — genuine noise) or mixed (both high — borderline, composite would also fire). |
| **G2** | Stress Spawn Count by Mode and Phase | Detection | Grouped bar, one group per stress phase (4 phases), 3 bars per group (DS/CPU/LAT). Error bars: SEM. Scatter dots: per-replicate. | SEM + scatter dots | Detection sensitivity across all stress phases. Shows whether mode differences are consistent across storage and compute stress. |
| **G3** | TTFS Distribution by Mode and Phase | Detection | Box plot per mode per stress phase, individual spawn events as scatter dots (aggregated across replicates). | Box/IQR + per-event dots | How quickly each mode responds to stress onset. Wide IQR indicates inconsistent detection timing. |
| **G4** | Per-Phase p50 Latency by Mode | Service Quality | Grouped bar, one group per phase (all phases), 3 bars per group (DS/CPU/LAT). Error bars: SEM. Scatter dots: per-replicate. | SEM + scatter dots | **The master service-quality graph.** The full timeline — when does trigger composition affect user experience? Baseline: mode differences most visible. Storage: convergence expected. Compute: possible divergence. |
| **G5** | Baseline p50 Latency by Mode | Service Quality | Grouped bar, 1 group (baseline), 3 bars (DS/CPU/LAT). Error bars: SEM. Scatter dots: per-replicate. | SEM + scatter dots | The cleanest measurement — no carryover backends, no residual load. If FP spawns during baseline lower latency, the "false positive" had a real benefit — a nuanced finding. |
| **G5b** | Latency by Phase Type | Service Quality | Grouped bar, 4 groups (baseline, storage-stress, compute-stress, post-stress), 3 bars per group. Error bars: SEM. Scatter dots: per-replicate. | SEM + scatter dots | Tests the phase-dependent regime model: convergence under storage I/O, possible divergence under compute, routing-quality effects in baseline, attenuated effects post-stress. |
| **G6** | Timeout Rate by Mode and Phase | Service Quality | Grouped bar, one group per phase, 3 bars per group. Error bars: SEM. Scatter dots: per-replicate. | SEM + scatter dots | User-visible harm. Complements M7 (throughput) — timeouts are catastrophic failure; throughput gap is graceful degradation. |
| **G7** | Throughput by Mode and Stress Phase | Service Quality | Grouped bar, one group per stress phase, 3 bars per group. Error bars: SEM. Scatter dots: per-replicate. | SEM + scatter dots | Completed requests. The key RQ3-specific empirical question: do extra spawns translate to more completed work (under-detection) or not (waste)? |
| **G8** | Score Component Decomposition Over Time | Diagnostic | Multi-panel line chart: 3 panels (one per mode, median replicate by spawn count). X-axis: telemetry windows. Two lines: CPU component and latency component. Horizontal dashed line at threshold. Shaded regions: stress phases. | N/A (single illustrative run per mode) | What signal drives detection in each mode. Shows whether cpu_only fires on CPU spikes that composite ignores, whether latency_only fires earlier, whether composite requires both to cross simultaneously. |

### 6.2 Graph Inventory

| # | Graph | Domain | Shows variance? |
|---|---|---|---|
| G1 | Baseline FP Spawns by Mode | Detection | ✅ SEM + scatter |
| G1b | FP Spawn Score Components | Detection | ✅ 2D position |
| G2 | Stress Spawn Count by Mode and Phase | Detection | ✅ SEM + scatter |
| G3 | TTFS Distribution by Mode and Phase | Detection | ✅ Box + scatter dots |
| G4 | Per-Phase p50 Latency by Mode | Service Quality | ✅ SEM + scatter |
| G5 | Baseline p50 Latency by Mode | Service Quality | ✅ SEM + scatter |
| G5b | Latency by Phase Type | Service Quality | ✅ SEM + scatter |
| G6 | Timeout Rate by Mode and Phase | Service Quality | ✅ SEM + scatter |
| G7 | Throughput by Mode and Stress Phase | Service Quality | ✅ SEM + scatter |
| G8 | Score Component Decomposition | Diagnostic | N/A (illustrative) |

**Total**: 8 primary graphs + 2 sub-graphs (G1b, G5b) = 10 graphs.
G4 is the master service-quality graph (RQ2's G6 analog).
G7 is the most RQ3-specific graph — it answers whether trigger composition
affects completed work.
G1b is the most mechanism-specific graph — it reveals what combination of
signals triggers each false positive, distinguishing pure noise from
borderline cases.

---

## 7. Evaluation Design

Nine runs, three per mode. All at the resource configuration selected in
§3.6, all with identical parameters.

| Run | Trigger | Compute weights | Storage weights |
|---|---|---|---|
| **R3-DS** (×3) | degradation_score | 0.40 / 0.60 | 0.60 / 0.40 |
| **R3-CPU** (×3) | cpu_only | 1.00 / 0.00 | 1.00 / 0.00 |
| **R3-LAT** (×3) | latency_only | 0.00 / 1.00 | 0.00 / 1.00 |

### 7.1 Parameter Selection

Floors, spans, and thresholds are applied identically to all three modes.
The recommended starting point is the Phase 1c calibration values (C3b
config), adjusted for whichever resource configuration is selected in
§3.6. Any parameter set that is reasonable for all modes is valid — the
comparison is between trigger compositions under the same conditions,
not between parameter sets.

### 7.2 Run Order

Grouped by trigger. Between runs: full cleanup + VM reboot.

---

## 8. Expected Outcomes

### 8.1 Baseline Behavior (SQ3a)

`cpu_only` will produce more FPs than composite because CPU spikes during
baseline cross the threshold when CPU is the only signal — there is no
latency confirmation to filter them. `latency_only` will also produce more
FPs because transient T_proc spikes cross the threshold when latency is
the only signal.

The composite score requires both to spike simultaneously, which happens
less often. The FP rate difference between modes is the evidence that
cross-signal confirmation filters noise.

### 8.2 Stress Detection (SQ3b)

All three modes should fire during stress — CPU reaches saturation and
T_proc rises during compute_spike. The differences are in spawn count
(does `latency_only` fire more often?) and timing (does latency fire
earlier than CPU?).

### 8.3 Service Quality (SQ3c)

If extra spawns from single-dimension modes don't improve service quality,
those spawns are waste — the system scaled unnecessarily. If missed spawns
from a mode produce worse service quality, that mode is failing to detect
real overload. If spawn counts differ but service quality is identical,
detection differences are real but inconsequential at this resource level.

### 8.4 RQ3 ↔ RQ1/RQ2 Parallel

| | RQ1 (Delivery) | RQ2 (Action) | RQ3 (Detection) |
|---|---|---|---|
| **Coordination gap** | Polling blind spot — controller misses telemetry windows between polls | Discovery gap — routing plane does not know about new backends until telemetry arrives | Signal gap — single-dimension triggers fire on noise or miss overload that cross-signal confirmation would filter or catch |
| **Separated baseline** | Poll mode — controller fetches at intervals | `topology_slowstart` — routing discovers backends via telemetry | `cpu_only` — the industry default, CPU-only trigger |
| **Unified approach** | Push mode — every window delivered at close | `topology_lifecycle` — warm lease at spawn time | `degradation_score` — cross-signal confirmation, both dimensions |
| **Core measurement** | Reaction latency, blind spot windows | TTFT + TFR — how fast routing acts and how fast the backend serves | FP spawns + stress spawn count — does it fire when it shouldn't, and does it fire enough when it should? |
| **User impact** | Timeout rate, throughput gap | Per-phase latency, initial load share | Per-phase latency, timeout rate, throughput — waste vs under-detection |

Together, RQ1, RQ2, and RQ3 characterise whether collapsing three control-plane
concerns into a single process — detection (what signals), delivery (how fast),
and action (how quickly capacity is utilised) — eliminates coordination gaps
that degrade service quality during demand shifts.

---

## 9. Development Required

### 9.1 Trigger Mode Selection

Already supported via environment variables in `scaling_config.py`. No
code changes needed.

### 9.2 Env Override Files

Three files under `source/scripts/testing/controller_env_overrides/`,
all derived from the same base configuration, varying only the four
weight variables.

### 9.3 Breach Detector

`breach_detector.py` replays recorded telemetry through each mode's score
function offline. Reads weights from the same env vars as the controller.
Used for TTFS measurement (M3) and score component decomposition (G8).

---

## 10. Validity Threats

| Threat | Mitigation |
|---|---|
| **The chosen floors/thresholds may advantage one mode.** The parameters are applied identically to all modes. If a reviewer argues that `cpu_only` should have a higher CPU floor, the response is: that higher floor would also suppress stress detection. The parameters must be the same for all modes because changing them would test calibration, not composition. |
| **The composite score has more parameters.** It has two degrees of freedom (two weights) vs one for single-dimension modes. This is inherent to the comparison — the thesis does not claim parameter-count fairness. It claims that the literature has never varied composition, and these three compositions represent points in the design space worth characterising. |
| **n=3 provides limited statistical power.** Three replicates allow μ ± σ. Consistency across replicates within a mode, combined with non-overlapping ranges between modes, is the evidentiary standard. |
| **Storage and compute tiers may respond differently.** Storage uses T_db; compute uses T_proc. The two tiers are analyzed separately. Consistent results across both strengthen the finding. |
| **Signal aggregation happens at the edge server, not the controller.** Both signals share a measurement interval because the edge server measures them during request processing. The controller receives the pre-aggregated summary and evaluates it. |

---

## 11. Related Documents

| Document | Purpose |
|---|---|
| [`rq3.md`](rq3.md) | Previous version (v1) — conceptual measurement definitions |
| [`rq3_setup_v2.md`](rq3_setup_v2.md) | Canonical experiment setup declaration — phases, resource limits, scoring parameters, run matrix |
| [`rq1_v2.md`](../rq1/rq1_v2.md) | RQ1 definition — direct methodological parallel for measurement framework |
| [`rq1_setup_v8.md`](../rq1/rq1_setup_v8.md) | RQ1 setup — resource limits and scoring parameters shared with RQ3 |
| [`rq2_v3.md`](../rq2/rq2_v3.md) | RQ2 definition — graph specification and causal model pattern |
| [`rq2_setup_v3.md`](../rq2/rq2_setup_v3.md) | RQ2 setup — structural template for setup declaration |
| [`global_literature_review.md`](../../tese/literature_review/global_literature_review.md) | Literature gap — trigger composition column (§7) |
| [`calibration_results.md`](../operation/testing/experiment/rq3_evaluation/calibration_results.md) | C4 baseline calibration — parameter starting point |
| [`calibration_plan.md`](../operation/testing/experiment/rq3_evaluation/calibration_plan.md) | Full calibration plan |
| [`system_to_thesis_map_rq_v2.md`](../../tese/miscelineous/system_to_thesis_map_rq_v2.md) | Full three-pillar thesis framing |
| [`../../source/sdn_controller/scaling_config.py`](../../source/sdn_controller/scaling_config.py) | Weight and threshold configuration |
| [`../../source/sdn_controller/scaling_policy.py`](../../source/sdn_controller/scaling_policy.py) | Degradation score implementation |
