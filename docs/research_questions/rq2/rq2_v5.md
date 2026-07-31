# RQ2 v5 — Routing-Awareness Timing and the Coordination Gap (Corrected Re-run)

**Thesis pillar**: Backend Selection (the action link)
**Status**: Full re-run — 9 new runs with corrected architecture (scoring + extraction)
**Experiment plan**: [`docs/operation/testing/experiment/rq2_evaluation/v5/experiment_plan_v5.md`](../../operation/testing/experiment/rq2_evaluation/v5/experiment_plan_v5.md)
**Setup declaration**: [`rq2_setup_v5.md`](rq2_setup_v5.md)
**Predecessor**: [`rq2_v3.md`](rq2_v3.md) — v3 campaign (invalidated by architectural scoring issues + MAC-reuse extraction bug)

---

## 1. Thesis Context

This thesis investigates whether collapsing three traditionally separated
control-plane concerns — **information acquisition** (monitoring), **backend
selection** (load balancing), and **infrastructure adaptation** (auto-scaling)
— into a single SDN controller process eliminates coordination gaps that
degrade service quality during demand shifts.

RQ1 tested this for monitoring: does push-mode telemetry (in-process) beat
polling (separated monitoring) by eliminating the blind spot between scrapes?

RQ2 tests the same phenomenon in the **routing plane**: when the scaler spawns
a new backend, does the routing plane become aware of it **at spawn time**
(in-process, atomic with pool registration) or **at discovery time** (after
the backend appears in telemetry, as a separated LB would discover it)? And
does spawn-time awareness produce measurably better load redistribution?

---

## 2. Research Question

> How does the timing of routing-plane awareness relative to backend spawn
> — at spawn time (warm lease, in-process) versus at discovery time
> (slow-start ramp, simulating a separated LB) versus no ramp-up — affect
> load redistribution quality during scale-up events in a stateful edge
> system?

---

## 3. What Is Being Investigated

Identical to v3. Three modes isolate routing-awareness timing:

| Mode | When routing becomes aware | Mechanism | Encodes |
|---|---|---|---|
| `topology_host` | Immediately (t=0) | Unknown stats → 0.0, round-robin distributes evenly | No integration between provisioner and LB |
| `topology_slowstart` | At discovery (first telemetry post-spawn) | Invisible (penalty 1.0) until discovery, then graduated ramp | Separated LB with coordination delay |
| `topology_lifecycle` | At spawn time (atomic with pool registration) | Warm lease with bounded priority window (45 s) | Unified controller — zero coordination gap |

For full mechanism descriptions, mode encodings, and the coordination gap
sequence diagrams, see [`rq2_v3.md` §3](rq2_v3.md#3-what-is-being-investigated).

---

## 4. Why This Question Exists

Identical to v3. RQ2 characterises the **action link** — how quickly newly
provisioned backends receive traffic and begin serving after they are spawned.
With RQ3 (detection) and RQ1 (monitoring), this completes the control-plane
coordination chain.

For full purpose, encoding, and RQ3 integration, see [`rq2_v3.md` §4](rq2_v3.md#4-why-this-question-exists).

---

## 5. How It Is Measured

Identical to v3 with two corrections:

### 5.0 What Changed from v3

Two categories of fix justify the v5 re-run:

**A. Scoring Architecture (from RQ1 v4)**

RQ1 v4 demonstrated that `SCALEUP_CPU_SPAN=5` saturated compute scoring across
all prior experiments. v5 uses the corrected golden config:

| Parameter | v3 (effectively) | v5 | Impact |
|---|---|---|---|
| `SCALEUP_CPU_SPAN` | 40 (env was correct) | 40 | Code-level fixes ensure it is respected |
| `SCALEUP_CPU_FLOOR` | 10 | 10 | Noise-triggered spawns in idle phases eliminated |
| `SCALEUP_W_STORAGE_CPU` | 0 | 0 | Storage spawns triggered by latency, not CPU I/O noise |
| `MAX_DYNAMIC_STORAGE` / `COMPUTE` | 8 / 12 | 8 / 12 | Matches golden config |
| `STORAGE_CPUS` | 0.08 | 0.08 | RQ3-calibrated resource profile |

The canonical `rq2_topology_*.env` files had drifted from `current_state_integrated.env` (stale values: `MAX_DYNAMIC_STORAGE=5`, `COMPUTE=6`, `SCALEUP_STORAGE_BASE_THRESHOLD=0.18`). v5 aligned them permanently.

**B. MAC-Reuse Extraction Fix (from v4)**

v3's `compute_ttft()` in `extract_spawn_metrics.py` used:

```python
if mac not in first_window:
    first_window[mac] = we  # first-window-ever for this MAC
```

Docker reuses MAC addresses across container lifetimes. When a new container
reuses a previous container's MAC, the extraction picked up the **old**
container's first window. This inflated TTFT by 10–30 s for Slowstart and
Lifecycle modes.

v5 fixes this by collecting all windows per MAC and matching the first window
with `window_end >= spawn_ts`:

```diff
- Build dict: mac → first_window_end (first-window-ever)
+ Collect ALL windows per MAC, then per spawn:
+   find first window_end >= spawn_ts with request_count > 0
```

**Impact on v3 measurements:**

| Mode | TTFT med (v3) | TTFT med (v4-corrected) | TTFT matches (v3→v4) |
|------|--------------|------------------------|---------------------|
| Host | 10.7 s | ~10.9 s | 17 → ~34 |
| Slowstart | 51.0 s | ~30.4 s | 18 → ~49 |
| Lifecycle | 30.6 s | ~20.9 s | 17 → ~36 |
| Coordination gap | 20.4 s | ~9.5 s | — |

### 5.1–5.4 Measurement Definitions

All metric definitions, graph specifications, and measurement rationale are
identical to v3. See [`rq2_v3.md` §5](rq2_v3.md#5-how-it-is-measured).
The only change: all TTFT values and derived metrics (init_time) are computed
with the corrected `first-window-after-spawn` algorithm.

### 5.5 Theoretical Expectations

Before empirical measurement, what does theory predict for each mode? This
section derives expectations from the system's routing primitives — flow-level
steering, WSM cost functions, telemetry window cadence, and warm-lease
mechanics — independently of any experimental data.

#### 5.5.1 TTFT — Time to First Traffic

**Lifecycle.** The warm lease is created atomically with pool registration
at $t = t_{\text{spawn}}$. The WSM cost function is bypassed entirely —
`_claim_warm_backend()` short-circuits normal scoring. The very next Packet-In
matching the VIP selects the warm backend. With 96 clients at rate 4.0,
new-flow inter-arrival is sub-second. Theoretical TTFT: $\approx 0$. The
coordination gap is zero by construction. Variance: **low** — the warm lease
is deterministic; the only stochastic element is when the next new flow
arrives, and at high load this gap is negligible.

**Host.** The backend enters the pool with unknown stats defaulting to $0.0$
(best-case). All $N$ backends tie at cost $0.0$; the round-robin tie-breaker
cycles through them. The new backend receives traffic when the counter lands
on it. With $N$ backends and new-flow arrival rate $\lambda$, the expected
wait is approximately $(N-1)/(2\lambda)$. However, only **new** flows trigger
backend selection — existing flows are pinned by OVS flow rules (idle timeout
30 s, hard timeout 60 s). The new backend must wait for genuinely new client
sessions. Theoretical TTFT: **moderate and variable** (seconds to tens of
seconds). Variance: **high** — round-robin counter position at spawn time is
effectively random, and pool size $N$ varies across spawn events.

**Slowstart.** Two sequential delays compose the TTFT:

1. **Discovery gap.** The backend is invisible (stats $0.0$ + penalty $1.0$,
   effective cost $= 1.0$) until the first telemetry window containing its
   stats arrives. This takes one aggregation window:
   $\Delta_{\text{discovery}} \approx 10\text{ s}$.

2. **Ramp-to-competitive.** After discovery, the penalty decays linearly:
   $p(t) = 1.0 - (t - t_{\text{discovery}})/45$. The backend becomes
   selectable when its effective cost falls below the minimum cost among
   existing backends: $p(t) \leq \min_{i \neq \text{new}} \text{WSM}_i$. Under
   heavy load (compute spike phases), existing backends have elevated costs
   ($0.4$–$0.6$); the new backend's WSM cost is $0.0$ (no telemetry yet), so
   it becomes competitive at $t - t_{\text{discovery}} \approx 18$–$27\text{
   s}$.

Theoretical TTFT: $\Delta_{\text{discovery}} + \Delta_{\text{ramp}} \approx
28$–$37\text{ s}$. Variance: **moderate** — the discovery delay is bounded by
window alignment ($\pm 5\text{ s}$); ramp-to-competitive time varies with the
load on existing backends (lighter load $\rightarrow$ lower existing costs
$\rightarrow$ longer ramp).

**Theoretical TTFT ordering:** $\text{Lifecycle} \ll \text{Host} <
\text{Slowstart}$. The coordination gap (Slowstart − Lifecycle) is
theoretically $\approx 28$–$37\text{ s}$.

#### 5.5.2 TFR and the Cold-Start Wildcard

TFR = TTFT + init_time, where init_time is the backend's preparation time
after receiving its first request (DB connection establishment, cache warming,
application-level preparation). This is the largest theoretical unknown.

**If the backend is fully ready at $t_{\text{spawn}}$:** TFR $\approx$ TTFT
for all modes. The TTFT ordering carries through — Lifecycle wins decisively.

**If the backend requires non-trivial warm-up after spawn:** a theoretical
inversion is possible.

| Mode | Scenario | Theoretical TFR |
|---|---|---|
| Lifecycle | Traffic arrives immediately. Backend is cold. Requests queue while initialisation completes. | Dominated by cold-start penalty ($t_{\text{init}}$) |
| Host | Traffic arrives after moderate delay. Some initialisation may have completed during the wait. | TTFT${}_{\text{host}}$ + init_residual |
| Slowstart | Traffic arrives after $\approx 28$–$37\text{ s}$. Backend has had ample time to fully initialise. | TTFT${}_{\text{slowstart}}$ (init_time $\approx 0$) |

If $t_{\text{init}}$ exceeds the coordination gap ($28$–$37\text{ s}$),
Slowstart's long TTFT becomes a **feature** — it gives the backend time to
warm up before traffic hits. Lifecycle's zero coordination gap becomes a
**liability** — it routes traffic to a backend that is not yet ready. Whether
this inversion occurs is the central empirical question RQ2 must resolve.

#### 5.5.3 Initial Load Share

**Lifecycle.** The warm lease gives the new backend priority for all new flows
during the 45 s window. In the first telemetry window, the backend captures
essentially all new flows. If new flows constitute fraction $f_{\text{new}}$
of total traffic: $\text{share}_{\text{lifecycle}} \approx f_{\text{new}}$.
This is **concentrated routing**.

**Host.** Round-robin distributes new flows evenly across $N$ backends:
$\text{share}_{\text{host}} \approx f_{\text{new}} / N$. This is **diluted
routing** — the backend gets its fair share, nothing more.

**Slowstart.** During the ramp, the penalty suppresses selection. In the first
post-discovery window, the backend's share is negligible.

Theoretical ordering: **Lifecycle $\gg$ Host $>$ Slowstart**.

#### 5.5.4 Service Quality by Phase Regime

Routing mechanism affects latency only when the bottleneck is at the compute
layer. When storage I/O dominates, all modes should converge.

| Phase type | Phases | Dominant factor | Theoretical mode effect |
|---|---|---|---|
| **Baseline** | baseline | Routing quality; quiescent start, no carryover backends | Lifecycle potentially best (immediate relief) or worst (cold start); Host moderate/stable; Slowstart transiently elevated (existing backends overloaded during invisible period) |
| **Compute stress** | compute_spike, compute_spike_2 | CPU saturation; uneven distribution creates hotspots | Lifecycle strongest advantage — concentrated routing relieves overloaded backends fastest. Host: diluted, relief slower. Slowstart: worst — invisible period prolongs overload |
| **Storage stress** | storage_storm, storage_storm_2 | MongoDB I/O dominates | **All modes converge** — routing cannot fix a database bottleneck |
| **Post-stress** | cooldowns, demand_drop | Mixed; residual backends from stress phases still alive (scale-down cooldown 180 s) | Mode differences **attenuated** relative to baseline; larger pool sizes dilute routing effects |

#### 5.5.5 Variance as a Theoretical Prediction

The three modes encode fundamentally different stochastic structures. Variance
is therefore a first-class theoretical prediction, not measurement noise:

| Mode | Dominant variance source | Theoretical IQR |
|---|---|---|
| Host | Round-robin counter position (random), flow churn (random), pool size $N$ (varies across spawn events) | **High** |
| Slowstart | Load on existing backends determines ramp threshold crossing (moderate variance); discovery window alignment ($\pm 5\text{ s}$) | **Moderate** |
| Lifecycle | Container startup time (small); `max(started_ts)` stacking when multiple spawns overlap | **Low** (single spawn), **elevated** (overlapping spawns) |

Host's round-robin is inherently a lottery — two identical spawn events can
produce very different TTFT depending on counter position. Lifecycle's warm
lease is deterministic — every spawn gets immediate priority. If the data
shows Host with wide IQR and Lifecycle with tight clustering, that is evidence
that the mechanism, not random chance, drives the difference.

#### 5.5.6 Summary

| | Lifecycle | Host | Slowstart |
|---|---|---|---|
| TTFT | $\approx 0$ | $\approx 5$–$20\text{ s}$ | $\approx 28$–$37\text{ s}$ |
| Coordination gap | — | $5$–$20\text{ s}$ | $28$–$37\text{ s}$ |
| Initial share | Very high ($\approx f_{\text{new}}$) | $f_{\text{new}} / N$ | $\approx 0$ |
| TTFT variance | Low | High | Moderate |
| Cold-start risk | **High** | Moderate | **Low** |
| Compute-stress advantage | Strongest | Moderate | Weakest |
| Storage-stress convergence | Yes | Yes | Yes |

The theoretical prediction is unambiguous on **awareness timing**: Lifecycle
wins, Slowstart loses, Host sits between. The coordination gap is real and
theoretically large ($\approx 30\text{ s}$).

The theoretical **ambiguity** is whether awareness timing translates to better
**service quality**. Two competing forces:

1. **Fast routing is good** — it relieves overloaded backends sooner.
2. **Slow routing may be good** — it gives the backend time to initialise
   before traffic hits.

Which force dominates depends on the backend cold-start penalty — a parameter
theory cannot resolve. This is the empirical question RQ2 exists to answer.

---

## 6. Graph Summary

17 graphs: 12 inherited from v3 (G1–G8b, corrected data) + 5 new (G9–G13) added
to capture theoretical predictions from §5.5 that the original graph set could
not express.

### 6.1 Spawn-to-Service Graphs (G1–G4b)

| Graph | Content | Affected by fix? | §5.5 prediction tested |
|-------|---------|-----------------|------------------------|
| G1 — TTFT Distribution | Box plot per mode + scatter dots | ✅ TTFT values corrected | Lifecycle ≪ Host < Slowstart; Host variance highest |
| G2 — TFR Distribution | Box plot per mode + scatter dots | — (TFR from client_requests.csv) | Cold-start inversion if Lifecycle TFR ≫ Lifecycle TTFT |
| G2b — TTFT vs TFR Scatter | 2D scatter, shape=mode | ✅ TTFT axis corrected | Diagonal = ready; above diagonal = cold start |
| G3 — Backend Initialisation Time | Box plot per mode + scatter dots | ✅ Derived from TTFT + TFR | Is init_time mode-dependent? |
| G4 — Initial Load Share | Box plot per mode + scatter dots | — (share from window aggregates) | Lifecycle ≫ Host > Slowstart |
| G4b — TTFT vs Initial Share Scatter | 2D scatter, shape=mode, dot size=pool size | ✅ TTFT axis corrected | Fast + concentrated (Lifecycle) vs slow + diluted (Slowstart) |

### 6.2 Service Quality Graphs (G5–G8b)

| Graph | Content | Affected by fix? | §5.5 prediction tested |
|-------|---------|-----------------|------------------------|
| G5 — Baseline p50 Latency | Grouped bar + scatter dots | — (latency from client_requests.csv) | Cleanest routing-quality comparison; quiescent start |
| G5b — Non-Stress p50 Latency | Grouped bar per phase + scatter dots | — | Effects persist or attenuate after stress? |
| G6 — Per-Phase p50 Latency | Grouped bar, all phases + scatter dots | — | **Master graph** — when does routing matter? |
| G7 — Latency Percentiles | Grouped bar p50/p95/p99 + scatter dots | — | Aggregate median vs. tail |
| G8 — Latency by Phase Type (p95) | Grouped bar, 4 groups + scatter dots | — | Convergence in storage, divergence in compute? |
| G8b — Latency by Phase Type (p50) | Grouped bar, 4 groups + scatter dots | — | Same as G8, p50 perspective |

### 6.3 Mechanism & Robustness Graphs (G9–G13) — New in v5

These graphs fill gaps between theoretical predictions (§5.5) and what the
original 12-graph set could show. They address three questions the theory
raises but the original graphs cannot answer: (a) *does* fast routing actually
relieve overloaded backends? (b) *is* there a cold-start liability? and
(c) *do* the modes differ at the tail, not just the median?

| Graph | Content | Data source | §5.5 prediction tested |
|-------|---------|-------------|------------------------|
| **G9 — CPU Relief After Spawn** | Grouped bar: mean CPU of existing backends in the 3 windows before vs. 3 windows after each spawn event, per mode. Error bars: SEM across all spawn events. Scatter dots: per-spawn values. One bar group per mode. | `rq2_spawn_metrics.csv` (spawn_ts) + `per_node_stats.csv` (`cpu_percent`, `server_id`, `role`, `window_end`) | **Mechanism graph.** Lifecycle should show the largest CPU drop post-spawn (concentrated routing → fastest relief). Slowstart should show the smallest drop or even a rise (invisible period prolongs overload). Host should sit between. This directly connects routing timing to its claimed benefit. |
| **G10 — Per-Phase p95 Latency** | Grouped bar, one group per phase (9 phases), three bars per group (host/slowstart/lifecycle). Error bars: SEM across n=3 replicates. Scatter dots: per-replicate values. | `client_requests.csv` (`latency_s`, `phase`) | **Tail latency.** Hotspot divergence from uneven load distribution lives in p95, not p50. If Lifecycle's concentrated routing occasionally overwhelms a cold backend, it shows as p95 elevation in compute phases even if p50 looks similar across modes. Storage phases: all modes expected to converge at p95 as well. |
| **G11 — Timeout Rate by Mode** | Grouped bar: fraction of requests with `http_status ≠ 200` (timeouts + errors), per mode. Optional split by phase type (Baseline, Compute stress, Storage stress, Post-stress). Error bars: SEM across n=3 replicates. | `client_requests.csv` (`http_status`) | **Cold-start liability test.** If Lifecycle routes traffic to unready backends, timeout rate should be elevated during compute stress phases relative to Host and Slowstart. If all modes have similar timeout rates, the cold-start risk is theoretical only. |
| **G12 — TTFT/TFR by Spawn Order** | 2D scatter: x = spawn ordinal (1st, 2nd, … Nth spawn in the run), y = TTFT (left panel) or TFR (right panel). Color = mode. One point per spawn event. | `rq2_spawn_metrics.csv` (`spawn_ts` → ordinal, `ttft_s`, `tfr_s`) | **Cold-start persistence.** If cold-start penalty is a first-spawn-only phenomenon, Lifecycle TTFT/TFR should converge to Host levels after the 2nd or 3rd spawn. If it persists across all spawns, the penalty is inherent to the mechanism, not an initialization artifact. |
| **G13 — Throughput by Phase** | Grouped bar: mean requests/second per phase per mode. Error bars: SEM across n=3 replicates. Scatter dots: per-replicate values. | `resource_stats.csv` (`request_count`, `window_end` → phase) or `client_requests.csv` (count / phase duration) | **Throughput/latency trade-off.** If Lifecycle's concentrated routing causes request queuing on a cold backend, total throughput may dip during compute stress phases even if latency stays steady (slow requests eventually succeed). If throughput is identical across modes, latency differences are not confounded by throughput changes. |

---

## 7. Relationship to v3 and v4

| | v3 | v4 | v5 |
|---|---|---|---|
| **What** | Initial RQ2 campaign | Warm-lease round-robin fix | Full re-run, corrected architecture |
| **Runs** | 9 new runs | 3 new Lifecycle runs | 9 new runs |
| **Key finding** | Coordination gap: 20.4 s (inflated) | Fix had no effect; MAC-reuse bug discovered | Tests corrected scoring + MAC-reuse fix |
| **Status** | Invalidated | Negative result | This experiment |

v4 tested a warm-lease round-robin fix. The fix did not change median TTFT
(20.9 s both ways) but tripled Lifecycle IQR (10.8→49.6 s). v5 adopts
**round-robin** as the warm-lease policy — confirmed superior to `max(started_ts)`
by head-to-head comparison (p95: 163 s vs 428 s). See
[`v4/results.md`](../../operation/testing/experiment/rq2_evaluation/v4/results.md)
and [`v5/results.md`](../../operation/testing/experiment/rq2_evaluation/v5/results.md).

---

## 8. References

- v3 methodology: [`rq2_v3.md`](rq2_v3.md)
- v3 setup: [`rq2_setup_v3.md`](rq2_setup_v3.md)
- v5 experiment plan: [`../operation/testing/experiment/rq2_evaluation/v5/experiment_plan_v5.md`](../../operation/testing/experiment/rq2_evaluation/v5/experiment_plan_v5.md)
- v5 setup: [`rq2_setup_v5.md`](rq2_setup_v5.md)
- v4 results (warm-lease negative result): [`../operation/testing/experiment/rq2_evaluation/v4/results.md`](../../operation/testing/experiment/rq2_evaluation/v4/results.md)
- RQ1 v4 (scoring correction reference): [`../operation/testing/experiment/rq1_thesis_final/v4/experiment_plan_v4.md`](../../operation/testing/experiment/rq1_thesis_final/v4/experiment_plan_v4.md)
- Extraction fix: [`source/scripts/testing/analysis/rq2/extract_spawn_metrics.py`](../../../source/scripts/testing/analysis/rq2/extract_spawn_metrics.py)
