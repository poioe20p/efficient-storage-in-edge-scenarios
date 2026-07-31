# RQ3 v6 — Trigger Composition Characterization

**Thesis pillar**: Detection (the signal link)
**Status**: ✅ Ready for evaluation — measurement framework finalized, calibration complete, experiment plan at [`rq3_evaluation/v6/`](../../operation/testing/experiment/rq3_evaluation/v6/experiment_plan_v6.md)
**Supersedes**: [`rq3_v2.md`](rq3_v2.md) (v2 — storage weights 0.60/0.40, calibration pending)
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

### 3.3 Three Trigger Modes

| Mode | Compute weights | Storage weights | Encodes |
|---|---|---|---|
| `degradation_score` | w_cpu=0.40, w_lat=0.60 | w_cpu=**0.20**, w_tdb=**0.80** | **Cross-signal confirmation.** Both signals must spike simultaneously to trigger. The system default. |
| `cpu_only` | w_cpu=1.00, w_lat=0.00 | w_cpu=1.00, w_tdb=0.00 | **CPU only.** The industry default — Kubernetes HPA, AWS ASG, and most autoscaling platforms use CPU utilization as the sole trigger metric. |
| `latency_only` | w_cpu=0.00, w_lat=1.00 | w_cpu=0.00, w_tdb=1.00 | **Latency only.** The dimension that matters for I/O-bound stateful services — what users actually experience. |

> **Storage weight calibration**: The v2 document proposed 0.60/0.40 for
> storage. Divergence calibration (§3.7) found that at 0.08 CPUs, storage
> CPU at 0.60 dominated T_db (24 spawns, indistinguishable from cpu_only's
> 22–24). A storage CPU weight probe reduced it to **0.20**, producing 18
> spawns — between cpu_only (22–24) and latency_only (15–17). CPU carries
> a real secondary signal at 0.08 CPUs, but T_db is the primary driver.

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
| Resource constraints | G0-v6 validated: STORAGE_CPUS=0.08, EDGE_CPUS=0.25, WAN_RTT_MS=185 ms (§3.7) |
| Telemetry delivery (push) | Eliminates the monitoring blind spot (RQ1's domain) |
| Routing policy (warm lease) | Eliminates the LB discovery gap (RQ2's domain) |
| Workload (`phases_rq1_7phase.json`) | Identical across all runs — 7 phases, 1,440 s |
| Floors, spans, thresholds, window size, REQUIRED count, cooldowns, adaptive increment | Identical across all modes (G0-v6 values, §3.7) |
| Latency signal | Mean-only (`avg_time_proc_ms`, `avg_time_db_ms`) — avoids timeout-censored p95 contamination |
| RANDOM_SEED=42, DATA_SEED=42 | Workload reproducibility |

Vary only: score weights (`SCALEUP_W_CPU`, `SCALEUP_W_T_PROC`,
`SCALEUP_W_STORAGE_CPU`, `SCALEUP_W_T_DB`).

### 3.6 Prerequisite: Scaling Must Produce Visible Improvement

For trigger composition to be a meaningful variable, scaling up must
demonstrably improve the conditions the trigger measures: CPU utilization
and processing latency. If adding capacity does not reduce CPU or latency,
then the choice of trigger is irrelevant — no composition can detect
overload that scaling cannot relieve.

This prerequisite was validated at the G0-v6 resource configuration:

- **compute_spike**: CPU pre→post drop of 23–28pp on both LANs (degradation_score mode)
- **storage_storm**: T_db pre→post drop from 939ms → 0.1ms (−939ms); storage CPU 37.4% → 15.6% (−21.8pp)
- **All success rates ≥ 96.6%** across all phases

The comparison structure for each RQ3 run is: **non-stress baseline →
pre-scale stress onset → post-scale stabilized stress**. The degradation
score must cross threshold during pre-scale stress; the post-scale window
must show reduced CPU and latency relative to pre-scale; and this cycle
must hold for both tiers.

### 3.7 Divergence Calibration — Summary

An 8-run calibration campaign ([`calibration_results_v2.md`](../../operation/testing/experiment/rq3_evaluation/v5/calibration_results_v2.md))
confirmed that G0-v6 thresholds produce behavioral divergence across all
three modes:

| Check | Result |
|---|---|
| **S4 — No tracebacks** | ✅ Zero across 12 controller logs |
| **D1 — Baseline FP divergence** | ⚠️ Inconclusive (60s baseline too short for robust FP measurement) |
| **D2 — Compute stress detection** | ✅ All three modes detected stress. cpu_only spawned 2.3× more than degradation_score (16 vs 7.5 avg) |
| **D2b — Storage stress detection** | ✅ All three modes detected stress. cpu_only (22–24) and pre-calibration degradation_score (24) similar → motivated storage weight probe |
| **D3 — Score component divergence** | ✅ Three-way separation: cpu_only 0.454 > degradation_score 0.295 > latency_only 0.066 |

**G0-v6 thresholds (definitive):**

| Parameter | Compute | Storage |
|---|---|---|
| CPU_FLOOR | 10 | 1.5 |
| CPU_SPAN | 40 | 5 |
| T_PROC_FLOOR / T_DB_FLOOR | 25 ms | 60 ms |
| T_PROC_SPAN / T_DB_SPAN | 80 | 250 ms |
| BASE_THRESHOLD | 0.18 | 0.35 |
| WINDOW_SIZE | 5 | 5 |
| REQUIRED | 3 | 2 |
| COOLDOWN_S | 45 | 120 |

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

The v6 measurement framework decomposes trigger composition effects into
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

> **Measurement risk**: The v5 calibration's D1 baseline FP check was
> inconclusive — 60s of baseline at 10% client fraction was too short for
> robust FP measurement. The v6 configuration increases baseline client
> fraction to 50% to improve statistical power, but FP counts may still
> be sparse (0–3 per run). Non-overlapping SEM bars may not be achievable
> with n=3. If baseline FP separation is not statistically distinguishable,
> C3 may need to rely on qualitative comparison or be marked inconclusive.

#### M2 — Stress Spawn Count

**Purpose**: Does the trigger fire enough during genuine overload? Counts
score-triggered spawns per stress phase (`storage_storm`, `tier1_hotspot`,
`reverse_hotspot`, `compute_spike`), per tier, compared across three modes
with n=3 replicates. This is the primary SQ3b sensitivity metric.

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
stress phases where per-node mean CPU exceeds threshold AND per-node mean
latency exceeds threshold, yet fewer than 1 spawn occurred within the phase
time bounds. Uses mean latency (not p95) because the controller's trigger
evaluates mean latency. Accounts for the controller's adaptive threshold
escalation.

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

### 5.3 Provisioning Efficiency — M8–M10

Measures the **resource cost** and **cross-tier behavior** that M1–M7 do
not capture. These metrics complete the picture: M7 asks whether extra
spawning helps; M8 answers at what cost.

#### M8 — Resource-Time Product

```
RTP = Σ (spawn_count_i × time_alive_i)  per mode, per tier, per run
```

**Purpose**: How much total provisioning does each mode consume? Aggregates
node-seconds across the entire run — a spawn that lives 300s costs 10× more
than one that lives 30s. Complements M7 to produce an efficiency ratio
(throughput ÷ RTP).

**Expectation**: `cpu_only` (highest) > `degradation_score` (middle) >
`latency_only` (lowest). If cpu_only provisioned 2.5× more CPU-seconds
than degradation_score but achieved identical throughput, the extra
spawns are quantifiable waste. If cpu_only's extra cost is partly offset
by shorter node lifetimes (peer relief kills nodes faster when more peers
exist), the efficiency gap narrows.

#### M9 — Cross-Tier Spawn Contamination

```
Contamination_AB = spawns_in_tier_A_during_tier_B_stress / total_spawns_tier_A
```

**Purpose**: Does a mode spawn nodes for the wrong tier? If cpu_only spawns
compute nodes during storage_storm (where compute CPU rises from request
processing, not saturation), the mode cannot distinguish *which* tier is
stressed. This directly tests the G0-v6 tier separation claim.

**Expectation**: `cpu_only` (highest — any CPU elevation triggers regardless
of tier) > `degradation_score` (low — latency confirmation filters cross-tier
noise) > `latency_only` (lowest — latency signal is tier-specific).

#### M10 — Score Component Correlation

```
r = Pearson(CPU_component[t], Latency_component[t])  per mode, per run, per phase
```

**Purpose**: Do CPU and latency components move together? In degradation_score,
a high correlation supports the cross-validation model — both signals reflect
the same underlying overload phenomenon, not independent noise. In
single-dimension modes, one component is always zero → r is undefined by
construction — the mode is structurally blind to that dimension.

**Expectation**: degradation_score: r > 0.5 during stress phases (both signals
rise together). cpu_only and latency_only: r is undefined (one component
always zero). This is not a finding to be discovered — it's a definitional
property of the weight structure. M10 quantifies what G8 shows visually.

### 5.4 Diagnostic — Score Component Decomposition (G8)

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

### 5.5 Measurement Chain (Causal Model)

```text
TRIGGER_COMPOSITION (w_cpu, w_lat)
  │
  ├─→ Detection Quality (§5.1)
  │     ├─ M1: FP spawns during baseline
  │     ├─ M2: Spawn count during stress
  │     ├─ M3: Time-to-first-spawn
  │     ├─ M4: Missed detections
  │     └─ G8: Score decomposition (diagnostic)
  │
  ├─→ Service Quality (§5.2)
  │     ├─ M5: Per-phase latency
  │     ├─ M6: Timeout rate
  │     └─ M7: Throughput
  │
  └─→ Provisioning Efficiency (§5.3)
        ├─ M8: Resource-time product
        ├─ M9: Cross-tier contamination
        └─ M10: Score component correlation
```

The causal interpretation: trigger composition determines **which signals**
contribute to the degradation score (CPU only, latency only, or both).
This determines **when** the score crosses threshold — during genuine
overload (correct detection), during baseline noise (false positive), or
never during overload (missed detection). Spawn count and timing (M2, M3)
determine **how much** capacity is available and **when** it arrives.
Available capacity determines **what** latency, timeout rate, and throughput
users experience (M5, M6, M7).

### 5.5 Success Criteria (C1–C8)

| # | Criterion | Maps to | Expectation |
|---|---|---|---|
| C1 | Run completion | — | All 9 runs complete, zero controller tracebacks |
| C2 | Within-mode consistency | M1–M7 | n=3 replicates per mode show consistent spawn counts and latency profiles |
| C3 | Baseline FP separation | M1, G1 | At least one pairwise comparison shows distinguishable FP spawn counts between modes |
| C4 | Stress detection separation | M2, M3, G2, G3 | At least one pairwise comparison shows distinguishable spawn counts or TTFS |
| C5 | Missed detection asymmetry | M4 | At least one mode misses ≥1 detection that another mode catches, OR all modes detect equally (valid bounding result) |
| C6 | Service quality separation | M5, G4 | At least one pairwise comparison shows distinguishable per-phase latency |
| C7 | Throughput-waste relationship | M7, G7 | If spawn counts differ between modes, throughput either differs (under-detection) or does not (waste) — both outcomes are informative |
| C8 | Scaling prerequisite | §3.6 | Pre-scale→post-scale improvement in CPU and latency confirmed at G0-v6 resource configuration |
| C9 | Efficiency separation | M8, G7b, G9 | At least one pairwise comparison shows distinguishable resource-time product between modes |
| C10 | Cross-tier contamination asymmetry | M9, G11 | cpu_only shows measurably higher cross-tier contamination than degradation_score |
| C11 | Score correlation | M10 | degradation_score shows r > 0.4 between CPU and latency components during stress phases |

---

## 6. Graph Summary

### 6.1 Thesis Graphs (G1–G8 + G1b + G5b + G7b + G9–G12 = 16 Graphs)

| # | Graph | Domain | Type | Variance | What it captures |
|---|---|---|---|---|---|
| **G1** | Baseline FP Spawns by Mode | Detection | Grouped bar, 3 bars. SEM + scatter dots (n=3). | SEM + scatter dots | Which modes fire unnecessarily during quiescent state. Primary SQ3a graph. |
| **G1b** | FP Spawn Score Components at Trigger | Detection | 2D scatter: x=CPU component, y=Latency component, color=mode. One point per FP spawn event. | Position in 2D space | What combination of signal values triggered each FP. Distinguishes pure-CPU noise from borderline. |
| **G2** | Stress Spawn Count by Mode & Phase | Detection | Grouped bar, 3 bars per stress phase. SEM + scatter dots. | SEM + scatter dots | Detection sensitivity across all stress phases. Mode consistency across storage vs compute stress. |
| **G3** | TTFS Distribution by Mode & Phase | Detection | Box plot per mode per phase, per-event scatter dots. | Box/IQR + dots | How quickly each mode responds to stress onset. Wide IQR = inconsistent timing. |
| **G4** | Per-Phase p50 Latency by Mode | Service Quality | Grouped bar, all 7 phases, 3 bars each. SEM + scatter dots. | SEM + scatter dots | **Master service-quality graph.** When does trigger composition affect user experience? |
| **G5** | Baseline p50 Latency by Mode | Service Quality | Grouped bar, 1 group, 3 bars. SEM + scatter dots. | SEM + scatter dots | Cleanest measurement — no carryover backends. If FPs lower latency, the "false positive" had real benefit. |
| **G5b** | Latency by Phase Type | Service Quality | Grouped bar, 4 phase-type groups, 3 bars each. SEM + scatter dots. | SEM + scatter dots | Tests phase-dependent regime model: convergence under I/O, divergence under CPU. |
| **G6** | Timeout Rate by Mode & Phase | Service Quality | Grouped bar, all phases, 3 bars each. SEM + scatter dots. | SEM + scatter dots | User-visible harm. Complements M7. |
| **G7** | Throughput by Mode & Stress Phase | Service Quality | Grouped bar, stress phases, 3 bars each. SEM + scatter dots. | SEM + scatter dots | **Most RQ3-specific.** Extra spawns = more work (under-detection) or same work (waste)? |
| **G8** | Score Component Decomposition | Diagnostic | 3-panel line chart (one per mode, median replicate). CPU + latency components, threshold line, stress phase shading. | N/A (illustrative) | **Why** modes behaved differently. Shows cpu_only fires on CPU spikes composite ignores, latency_only fires earlier, composite requires both. |

### 6.2 Extended Graphs — Provisioning Efficiency & Node Overhead

| # | Graph | Domain | Type | Variance | What it captures |
|---|---|---|---|---|---|
| **G7b** | Throughput-per-Resource by Mode | Efficiency | Grouped bar, stress phases, 3 bars each. SEM + scatter dots. | SEM + scatter dots | Efficiency ratio: completed requests ÷ CPU-seconds provisioned. Complements G7 — answers "at what cost?" |
| **G9** | Cumulative Resource-Time by Mode & Tier | Efficiency | Grouped bar, 2 groups (compute, storage), 3 bars each. SEM + scatter dots. | SEM + scatter dots | Total CPU-seconds provisioned per tier. Decomposes waste: compute vs storage cost. |
| **G10** | Dynamic Node Count Over Time | Overhead | 3-panel line chart (one per mode, median replicate). Solid: compute. Dashed: storage. Shaded: stress phases. | N/A (illustrative) | The "shape" of scaling. Node accumulation, cooldown drain, cross-phase persistence. |
| **G10b** | Peak & Mean Node Count by Mode & Tier | Overhead | Grouped bar, 2 groups, 3 bars each. Two sub-panels: peak, mean. SEM + scatter dots. | SEM + scatter dots | Peak = worst-case. Mean = average overhead. Short-lived nodes = high peak, low mean. |
| **G11** | Cross-Tier Spawn Contamination by Mode | Diagnostic | Grouped bar, 2 groups (compute-during-storage, storage-during-compute), 3 bars each. SEM + scatter dots. | SEM + scatter dots | M9 visualized. Does cpu_only spawn nodes for the wrong tier? |
| **G12** | Node Lifetime Distribution by Mode & Tier | Diagnostic | Box plot per mode per tier, per-node lifetimes as scatter dots. | Box/IQR + dots | How long do spawned nodes live? Explains G9: many short-lived nodes = lower cost than spawn count suggests. |

---

## 7. Evaluation Design

### 7.1 Run Matrix

Nine runs, three per mode. All at G0-v6 resource configuration, all with
identical parameters. Only the four weight variables differ.

| Run | Trigger | Compute weights | Storage weights |
|---|---|---|---|
| **R3-DS** (×3) | degradation_score | 0.40 / 0.60 | **0.20 / 0.80** |
| **R3-CPU** (×3) | cpu_only | 1.00 / 0.00 | 1.00 / 0.00 |
| **R3-LAT** (×3) | latency_only | 0.00 / 1.00 | 0.00 / 1.00 |

**Implementation**: [`experiment_plan_v6.md`](../../operation/testing/experiment/rq3_evaluation/v6/experiment_plan_v6.md)

### 7.2 Phases

The 7-phase workload from `phases_rq1_7phase.json`:

| # | Phase | Duration | Rate/client | Cross-region | Purpose |
|---|-------|----------|-------------|--------------|---------|
| 1 | `baseline` | 60 s | 1.0 | 0% | M1 — FP spawn measurement |
| 2 | `storage_storm` | 240 s | 4.0 | 90% | Storage tier detection |
| 3 | `tier1_hotspot` | 180 s | 5.0 | 95% | Tier 1 selective-sync stress |
| 4 | `inter_hotspot_cooldown` | 300 s | 1.0 | 0% | Drain between hotspots |
| 5 | `reverse_hotspot` | 180 s | 5.0 | 95% | Second hotspot direction |
| 6 | `compute_spike` | 180 s | 4.0 | 5% | **Pure compute isolation** — feed_ranking 65% |
| 7 | `demand_drop` | 300 s | 1.0 | 0% | Extended drain for scale-down |

> **compute_spike mix**: `{content_lookup: 0.20, feed_ranking: 0.65,
> service_pressure: 0.15}` at 5% cross-region. Feed_ranking is CPU-intensive
> (ranking computation); storage I/O is minimal. This is a realistic compute
> workload, not an artificial 100%-pressure benchmark. The calibration's D3
> divergence check used this exact mix and produced clear three-way separation.

---

## 8. Expected Outcomes

### 8.1 Baseline Behavior (SQ3a)

`cpu_only` will produce more FPs than composite because CPU spikes during
baseline cross the threshold when CPU is the only signal — there is no
latency confirmation to filter them. `latency_only` may also produce FPs
from transient T_proc spikes, but less frequently at 0.25 CPUs.

The composite score requires both to spike simultaneously, which happens
least often. The FP rate difference between modes is the evidence that
cross-signal confirmation filters noise.

**Calibration evidence**: D1 baseline FP measurement was inconclusive (60s
baseline too short). The 9-run evaluation with n=3 per mode will provide
robust FP counts.

### 8.2 Stress Detection (SQ3b)

All three modes should fire during stress — CPU reaches saturation and
T_proc rises during compute_spike; T_db rises during storage_storm. The
differences are in spawn count and timing.

**Calibration evidence**:
- **Compute**: cpu_only spawned 2.3× more than degradation_score (16 vs
  7.5 avg); latency_only spawned fewest (3 avg). Three-way divergence
  confirmed (D2).
- **Storage**: At calibrated 0.20/0.80, degradation_score (~18 spawns)
  should sit between cpu_only (22–24) and latency_only (15–17). Partial
  separation — CPU is a real but weak secondary signal at 0.08 CPUs.

### 8.3 Service Quality (SQ3c)

In baseline, mode differences should be most visible — FP spawns may create
unnecessary capacity that lowers latency. In storage stress, modes should
converge (I/O dominates). In compute stress, modes may diverge (spawn count
differences create different capacity levels).

The throughput-waste relationship (M7, G7) is the key empirical question:
if degradation_score achieves the same throughput as cpu_only with fewer
spawns, cross-signal confirmation is filtering waste. If cpu_only achieves
higher throughput, composite is under-detecting.

### 8.4 Two-Tier Asymmetry

The G0-v6 resource configuration creates an asymmetry that is itself a
finding:

- **Compute tier** (0.25 CPUs): Both CPU and T_proc are independently
  meaningful signals. Trigger composition produces clear three-way
  divergence.
- **Storage tier** (0.08 CPUs): CPU is a real but weak signal (−21.8pp
  pre→post). T_db is the primary driver. Trigger composition produces
  partial separation — the space of meaningful trigger inputs is bounded
  by resource constraints.

This bounds the thesis contribution: the unified control plane's detection
link matters where the resource regime provides two independently meaningful
signals. At tighter limits, one signal dominates.

---

## References

- [Experiment Plan v6](../../operation/testing/experiment/rq3_evaluation/v6/experiment_plan_v6.md) — implementation details, launch commands, artifact contract
- [Setup Declaration v6](rq3_setup_v6.md) — canonical parameter reference, env file contents
- [Theory Predictions v6](rq3_theory_prediction_v6.md) — formalised predictions per mode per tier
- [Divergence Calibration Results](../../operation/testing/experiment/rq3_evaluation/v5/calibration_results_v2.md) — 8-run calibration, D1–D3 checks, storage weight probe
- [RQ3 Cross-Mode Comparison Skill](../../../.github/skills/rq3-cross-mode-comparison/SKILL.md) — graph generation workflow (note: update v5 paths to v6 before running)
