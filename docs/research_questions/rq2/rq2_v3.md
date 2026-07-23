# RQ2 — Routing-Awareness Timing and the Coordination Gap

**Thesis pillar**: Backend Selection (the action link)
**Status**: Designed — experiment plan v3 ready, pending execution
**Experiment plan**: [`docs/operation/testing/experiment/rq2_evaluation/v3/experiment_plan_v3.md`](../../operation/testing/experiment/rq2_evaluation/v3/experiment_plan_v3.md)
**Setup declaration**: [`rq2_setup_v3.md`](rq2_setup_v3.md)

---

## 1. Thesis Context

This thesis investigates whether collapsing three traditionally separated
control-plane concerns — **information acquisition** (monitoring), **backend
selection** (load balancing), and **infrastructure adaptation** (auto-scaling)
— into a single SDN controller process eliminates coordination gaps that
degrade service quality during demand shifts.

RQ1 tested this for monitoring: does push-mode telemetry (in-process) beat
polling (separated monitoring) by eliminating the blind spot between scrapes?
The mechanism was **missed telemetry windows** — the controller simply does
not see what happened between polls.

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

When the controller's elasticity manager spawns a new backend, the routing
plane can become aware of it in three ways:

### 3.1 Three Modes

| Mode | When routing becomes aware | Ramp-up mechanism | Encodes |
|---|---|---|---|
| `topology_host` | **Immediately** — unknown stats default to 0.0 (best-case). All backends tie at cost 0.0; round-robin tie-breaking distributes traffic evenly across the pool. | None — round-robin fair-share | **No integration between provisioner and LB.** The LB discovers backends via pool membership alone — no health-check gating, no slow-start ramp, no awareness that the backend is new. The backend appears in the pool and receives traffic immediately, but may not yet be ready to serve it. This is the baseline. |
| `topology_slowstart` | **At discovery time** — when the first telemetry arrives containing the new backend. Until then: unknown stats default to 0.0 (neutral); a slow-start penalty of 1.0 is applied on top, making the backend effectively invisible. After discovery: the penalty decays linearly from 1.0 to 0.0 over the warm-lease TTL. | Invisible (penalty 1.0) until discovery, then graduated ramp | **Separated LB slow-start with coordination delay.** In a separated system, the LB does not know the backend exists until health checks pass. The backend is effectively invisible for the discovery gap — encoding the coordination delay that RQ1 also measures for monitoring. |
| `topology_lifecycle` | **At spawn time** — warm lease created atomically with pool registration. The routing plane short-circuits the weighted server model (WSM) to select the warm backend with priority. Unknown stats default to 1.0 (worst-case) but are irrelevant — the warm-lease path bypasses the WSM cost function entirely. | Warm lease (bounded priority window, spawn-time atomic) | **Unified controller.** Routing knows about the spawn immediately because routing and scaling share the same process. No discovery delay, no coordination gap. |

### 3.2 The Coordination Gap in Routing

In a separated architecture, the sequence is:

```text
Separated (Kubernetes-style):
  Scaler spawns pod (t=0)
    → Pod boots
      → LB health check discovers pod (first successful check)
        → Slow-start ramp begins
          → Pod reaches full weight

  Coordination gap: the delay between spawn and LB discovery.

Unified (SDN controller):
  Scaler spawns container (t=0)
    → Warm lease created (t=0, atomic with pool registration)
      → Router immediately routes to new backend (t=0)
        → Warm lease expires, backend competes normally

  Coordination gap: 0 s.
```

The question is whether this gap is measurable in practice.

### 3.3 What Is Held Constant

- Telemetry delivery: **push mode** (ZMQ at window close) — RQ1's optimal delivery.
- Weighted Server Model (WSM) weights and dimensions: identical across all modes.
- Infrastructure: two-LAN topology, WAN emulation, containerized services.
- Persistent storage reserve: **enabled** (`STORAGE_PERSISTENT_RESERVE_ENABLED=1`).
- Tier 1 selective sync: **disabled** (`SS_ENABLED=0`) — isolates routing mechanism from Tier 1 pool effects.

Vary only: **when and how the routing plane becomes aware of a new backend**
(`BACKEND_SELECTION_POLICY`).

---

## 4. Why This Question Exists

### 4.1 Purpose

RQ2 tests whether the **coordination gap in routing** — the delay between
spawn and routing-plane awareness — measurably affects load redistribution
quality. RQ1 tested the same phenomenon for monitoring. Together they
characterise whether co-locating the control plane eliminates delays that
matter in practice.

The thesis does not claim the unified approach is superior. It characterises
the trade-off: if spawn-time awareness produces faster redistribution, the
coordination gap is measurable and co-location eliminates it. If all three
modes redistribute load equally well, the gap exists on paper but is
inconsequential at this scale — still a valid finding.

### 4.2 What Each Condition Encodes

| Condition | Encodes |
|---|---|
| `topology_host` | **No integration between provisioner and LB.** Unknown stats → 0.0 (best-case). All backends tie at cost 0.0 → round-robin distributes traffic evenly. No ramp, no priority window — the backend is just another pool member. |
| `topology_slowstart` | **Separated LB slow-start with coordination gap.** Backend invisible (stats 0.0 + penalty 1.0) until telemetry arrives. Then graduated ramp at discovery. The discovery gap is the coordination delay — same phenomenon RQ1 measures. |
| `topology_lifecycle` | **Spawn-time warm lease.** Zero discovery gap — routing aware at spawn time. Warm lease provides a bounded priority window — controlled ramp with immediate priority. |

### 4.3 Integration with RQ3

RQ3 characterises the **detection** link — what signals trigger scale-up.
RQ2 characterises the **action** link — how quickly newly provisioned backends
receive traffic and begin serving after they are spawned.

| RQ3 determines | RQ2 determines |
|---|---|
| What signals trigger a spawn | How fast the spawned backend receives its first request (TTFT) and its first response (TFR) |
| How early overload is detected | How much immediate traffic the new backend captures (initial load share) |

The synthesis: **RQ3 controls when and why capacity is created; RQ2
controls how quickly that capacity is utilised and becomes serviceable.**
Detection without fast routing means spawns occur but capacity sits idle.
Fast routing without detection means nothing to route to.

---

## 5. How It Is Measured

Three measurement domains answer the question. **§5.1 (Spawn-to-Service Timing)
is the core thesis evidence** — §5.2 (Service Quality) provides user-visible
impact assessment. Each measurement specifies the thesis-level graphs that
visualise it.

**Instrumentation note:** TFR (§5.1.2) requires per-backend response
tracking — the first HTTP response timestamp for each newly spawned backend.
This instrumentation must be added before the experiment runs. Current
artifacts (`per_node_stats.csv`, `client_requests.csv`) do not natively
support per-backend response correlation. The implementation approach is:
capture the first `completed_at` in `client_requests.csv` that maps to a
specific backend (via the backend's IP or MAC, correlated from the
controller's node registry at spawn time).

**Variance is a first-class finding across ALL measurements.** The three
modes differ not only in central tendency (median, mean) but in the spread
of their distributions. Host's round-robin mechanism produces inherently
variable behaviour; lifecycle's warm lease is deterministic. Every graph
must show both central tendency AND variance — through box plots with
scatter dots for per-event metrics, and error bars (SEM) with per-replicate
scatter dots for per-phase aggregate metrics.

---

### 5.1 Spawn-to-Service Timing — Core Evidence

Captures the **coordination gap** through four interrelated timing metrics,
each isolating a different segment of the spawn-to-service pipeline. All
metrics are computed per **compute** spawn event only. Storage spawns are
excluded — storage backends follow a different warm-up path (30 s warm-lease
TTL vs 45 s for compute) and serve a different traffic mix, which would
confound the routing-plane comparison.

**Measurement resolution:** TTFT and TFR rely on telemetry data with ~10 s
window granularity. Individual per-request timestamps are not available in
current telemetry — first traffic is detected as the first window where
`request_count > 0` for the new backend. This discretization is acknowledged
as a limitation. The TFR − TTFT difference inherits this resolution; values
below ~10 s should be interpreted as "within the same telemetry window."

#### 5.1.1 TTFT — Time-to-First-Traffic

```
ttft = t(first_request_arrives_at_new_backend) − spawn_done_ts
```

Computed per spawn event. Measures how quickly the routing plane sends
traffic to the new backend after it is spawned. This isolates the
**awareness timing** — the coordination gap between spawn and routing action.

#### 5.1.2 TFR — Time-to-First-Response

```
tfr = t(first_response_sent_by_new_backend) − spawn_done_ts
```

Computed per spawn event. Measures how quickly the new backend actually
serves its first client response. This captures the full spawn-to-service
pipeline: routing awareness + backend initialisation.

#### 5.1.3 Backend Initialisation Time

```
init_time = tfr − ttft
```

The difference between first response and first request. This approximates
the time the backend spends between receiving its first request and serving
its first response — DB connection establishment, cache warming,
application-level preparation. It does not measure when the backend becomes
*fully* ready (caches may continue populating in background threads after
the first response). It is the best available proxy for readiness given
current instrumentation, but should be interpreted as "time from first
traffic to first service" rather than "time to full readiness."

#### 5.1.4 Initial Load Share

```
initial_share = new_backend_request_count / total_VIP_requests_in_first_window
```

The fraction of VIP traffic the new backend captures in its first visible
telemetry window. Computed per spawn event. Measures how aggressively the
routing plane redirects traffic — the magnitude of the routing response,
independent of its speed.

#### 5.1.5 Why These Metrics Together

TTFT alone does not tell the full story. A backend could receive traffic
quickly (low TTFT) but take a long time to serve its first response (high
TFR), indicating that routing was fast but the backend was not ready. The
TFR − TTFT gap reveals whether the routing mechanism aligns traffic arrival
with backend readiness. Initial load share adds the magnitude dimension:
how much traffic, not just how soon.

**Expected mechanism-driven patterns (theoretical, not empirical):**

| Mode | TTFT driver | TFR driver | Initial share driver |
|---|---|---|---|
| `topology_host` | Round-robin counter state — backend wins when its turn arrives. | TTFT + backend initialisation time. | ~1/N fair share in the first post-spawn window. Every backend ties at cost 0.0 (no telemetry yet); round-robin distributes evenly. This property holds only until the first telemetry window populates per-backend stats. |
| `topology_slowstart` | Discovery delay + ramp duration. Backend invisible until first telemetry. | TTFT + backend initialisation time. Whether the discovery gap allows initialisation to complete before traffic arrives is an open empirical question — not assumed. | Graduated ramp — starts low, builds to full weight as penalty decays. |
| `topology_lifecycle` | Warm lease at t=0 — selected immediately via WSM bypass. | TTFT + backend initialisation time. Concentrated traffic may accelerate initialisation — this is an empirical question the experiment tests, not an assumption. | Priority routing — WSM short-circuited during warm lease. |

> **Implementation note:** Warm leases are created unconditionally for all
> backends at spawn time (in `register_new_server_backend()`). Only
> `topology_lifecycle` consumes them via `_claim_warm_backend()`;
> `topology_host` and `topology_slowstart` ignore them. The creation is
> harmless overhead — the lease exists but is never checked.

#### Thesis Graphs for Measurement 5.1

| Graph | Type | Variance shown via | What it captures |
|---|---|---|---|
| **G1 — TTFT Distribution by Mode** | Box plot per mode, individual spawn events as scatter dots | Box/IQR + per-event dots | How quickly routing sends traffic to the new backend. Host's wide IQR (round-robin lottery) vs lifecycle's tight cluster (deterministic warm lease). |
| **G2 — TFR Distribution by Mode** | Box plot per mode, individual spawn events as scatter dots | Box/IQR + per-event dots | How quickly the new backend serves its first response. Captures the full spawn-to-service pipeline. |
| **G2b — TTFT vs TFR Scatter by Mode** | 2D scatter: x=TTFT, y=TFR, color=mode, one point per spawn event | Position of each point in (TTFT, TFR) space | The relationship between awareness speed and service readiness. Points on the diagonal (TFR ≈ TTFT) indicate the backend was ready when traffic arrived. Points above the diagonal indicate backend initialisation delay. |
| **G3 — Backend Initialisation Time by Mode** | Box plot per mode, individual spawn events as scatter dots | Box/IQR + per-event dots | TFR − TTFT per spawn event. Isolates backend initialisation from routing awareness. Reveals whether routing mechanisms differ in how well they align traffic with backend readiness. |
| **G4 — Initial Load Share Distribution by Mode** | Box plot per mode, individual spawn events as scatter dots | Box/IQR + per-event dots | How aggressively each mode redirects traffic. Aggressiveness (share) is the magnitude counterpart to speed (TTFT/TFR). |
| **G4b — TTFT vs Initial Share Scatter by Mode** | 2D scatter: x=TTFT, y=InitialShare, color=mode, one point per spawn event | Position of each point in (TTFT, Share) space | The joint distribution of speed and magnitude. Reveals whether faster traffic (low TTFT) correlates with higher share, and whether the relationship differs by mode. |

---

### 5.2 Per-Phase Service Quality — User-Visible Impact

Captures the **end-user experience** across the full workload timeline.
Answers: do the routing mechanisms produce different latency profiles under
different load conditions, and do they converge when storage I/O dominates?

**Per-phase p50/p95/p99 latency**, disaggregated by phase and mode.

**Phase-dependent latency regimes (theoretical expectation):**

| Phase type | Phases | Dominant latency factor | Expected mode effect |
|---|---|---|---|
| **Non-stress** | baseline | Backend readiness and routing quality — the only phase guaranteed to start with no prior stress carryover | Modes may differ — routing mechanism determines how traffic is distributed and whether backends are ready |
| **Post-stress** | cooldowns, demand_drop | Mixed — residual effects from preceding stress phase (draining backends, partially warm caches) | Mode differences may be attenuated relative to baseline; backends from preceding stress phases may still be alive |
| **Storage stress** | storage_storm, storage_storm_2 | Storage I/O (content_update, content_aggregate) | All modes expected to converge — storage I/O dominates routing choice |
| **Compute stress** | compute_spike, compute_spike_2 | CPU saturation (feed_ranking, service_pressure) | Modes may diverge — uneven load distribution could create hotspots |

**Why phase disaggregation matters:** A whole-run average conflates non-stress
phases (where routing quality is the dominant factor) with storage phases
(where I/O dominates). The per-phase breakdown reveals *when* routing matters
and *when* it does not — bounding the scope of the routing-plane coordination
gap.

#### Thesis Graphs for Measurement 5.2

| Graph | Type | Variance shown via | What it captures |
|---|---|---|---|
| **G5 — Baseline p50 Latency by Mode** | Grouped bar chart, one group (baseline phase), three bars (host/slowstart/lifecycle). Error bars: SEM across n=3 replicates. Scatter dots: per-replicate values. | Error bars (SEM) + per-replicate scatter dots | Routing quality in the only phase guaranteed to start from quiescent state — no carryover backends, no residual load. The cleanest measurement of whether routing mechanism alone affects user-visible latency. |
| **G5b — Non-Stress p50 Latency by Mode** | Grouped bar chart, one group per low-load phase (baseline, cooldowns, demand_drop), three bars per group (host/slowstart/lifecycle). Error bars: SEM across n=3 replicates. Scatter dots: per-replicate values. | Error bars (SEM) + per-replicate scatter dots | Routing quality across all low-load phases, including post-stress transitional phases. Complements G5 by showing whether baseline effects persist or attenuate after stress. |
| **G6 — Per-Phase p50 Latency by Mode** | Grouped bar chart, one group per phase (9 phases), three bars per group (host/slowstart/lifecycle). Error bars: SEM across n=3 replicates. Scatter dots: per-replicate values. | Error bars (SEM) + per-replicate scatter dots | The full timeline. Mode differences visible in baseline, attenuated in post-stress phases, convergence expected in storage_storm, possible divergence in compute_spike. **This is the master service-quality graph.** |
| **G7 — Per-Mode Latency Percentiles (p50/p95/p99)** | Grouped bar chart, one group per mode, three bars per group (p50, p95, p99). Error bars: SEM across n=3 replicates. Scatter dots: per-replicate values. | Error bars (SEM) + per-replicate scatter dots | Aggregate view across all phases. Reveals whether routing choice affects median experience, tail latency, both, or neither. |
| **G8 — Latency by Phase Type** | Grouped bar chart, four groups (baseline, post-stress, storage stress, compute stress), three bars per group (host/slowstart/lifecycle). Error bars: SEM across n=3 replicates. Scatter dots: per-replicate values. | Error bars (SEM) + per-replicate scatter dots | Confirms or refutes the phase-dependent regime model. Storage group: bars expected near-equal (I/O dominates). Baseline: routing quality differences most visible. Post-stress: tests whether effects persist. Compute: possible divergence. |

---

### 5.3 Failure Rate — Safety Check

HTTP status ≠ 200 count / total requests, per mode. Reported as a statistic
in the results narrative.

---

### 5.4 Measurement Chain (Causal Model)

```text
BACKEND_SELECTION_POLICY
  │
  ├─→ Spawn-to-Service Timing (§5.1)
  │     ├─ TTFT (G1) ──────────────── when does routing send traffic?
  │     ├─ TFR (G2) ───────────────── when does the backend serve?
  │     ├─ TTFT × TFR 2D (G2b) ────── awareness vs readiness relationship
  │     ├─ Init Time (G3) ─────────── how long to become ready after traffic?
  │     ├─ Initial Share (G4) ──────── how much traffic is redirected?
  │     └─ TTFT × Share 2D (G4b) ──── speed vs magnitude relationship
  │
  └─→ Service Quality (§5.2)
        ├─ Baseline p50 (G5) ──────── routing quality from quiescent state
        ├─ Non-Stress p50 (G5b) ────── routing quality across all low-load phases
        ├─ Per-Phase p50 (G6) ──────── when does routing matter? (master graph)
        ├─ Aggregate Percentiles (G7) ─ median vs tail
        └─ By Phase Type (G8) ──────── convergence vs divergence per regime
```

The causal interpretation: `BACKEND_SELECTION_POLICY` determines **when**
routing becomes aware of a new backend and **how** traffic is distributed
(concentrated via warm lease vs diluted via round-robin). These determine
**how quickly** a backend receives traffic (TTFT) and **whether** it is
ready when traffic arrives (TFR − TTFT). Together these determine **what**
latency users experience (service quality).

The spawn-to-service metrics (§5.1) are the **direct mechanisms**. Service
quality (§5.2) is the **user-visible outcome**. Both are necessary to fully
answer RQ2: a mechanism without user impact is academic; user impact without
mechanism is unexplained.

---

## 6. Graph Summary

| # | Graph | Domain | Shows variance? |
|---|---|---|---|
| G1 | TTFT Distribution by Mode | Spawn-to-Service | ✅ Box + scatter dots |
| G2 | TFR Distribution by Mode | Spawn-to-Service | ✅ Box + scatter dots |
| G2b | TTFT vs TFR Scatter by Mode | Spawn-to-Service | ✅ Position in 2D space |
| G3 | Backend Initialisation Time by Mode | Spawn-to-Service | ✅ Box + scatter dots |
| G4 | Initial Load Share Distribution by Mode | Spawn-to-Service | ✅ Box + scatter dots |
| G4b | TTFT vs Initial Share Scatter by Mode | Spawn-to-Service | ✅ Position in 2D space |
| G5 | Baseline p50 Latency by Mode | Service Quality | ✅ Error bars + scatter |
| G5b | Non-Stress p50 Latency by Mode | Service Quality | ✅ Error bars + scatter |
| G6 | Per-Phase p50 Latency by Mode | Service Quality | ✅ Error bars + scatter |
| G7 | Per-Mode Latency Percentiles | Service Quality | ✅ Error bars + scatter |
| G8 | Latency by Phase Type | Service Quality | ✅ Error bars + scatter |

**Total**: 11 graphs (G1–G8 + G2b, G4b, G5b). G6 is the master service-quality
graph. G2b and G4b are the most RQ2-specific graphs — they capture the two
key relationships (speed vs readiness, speed vs magnitude) that characterise
the routing-plane coordination gap. The suffixed graphs (G2b, G4b, G5b) are
numbered as sub-graphs because they are 2D or supplementary views derived
from the same data as their parent graphs.

---

## 7. Expected Outcomes

These are mechanism-derived expectations, to be verified or refuted by the
experimental data. No numerical predictions are made — the experiment
measures what the system does under each mode, without assuming outcomes.

1. **Routing awareness timing affects spawn-to-service speed.** The warm
   lease (lifecycle) should route traffic faster than discovery-based
   awareness (slowstart) because it eliminates the telemetry discovery gap.
   Round-robin (host) should exhibit higher variance because the counter
   state at spawn time determines when the new backend first wins a cycle.

2. **Routing aggressiveness differs by mechanism.** Warm-lease priority
   (lifecycle) concentrates traffic on the new backend. Slow-start ramp
   (slowstart) introduces traffic gradually. Round-robin (host) distributes
   evenly regardless of backend newness.

3. **Backend initialisation time (TFR − TTFT) is an empirical question.**
   Whether concentrated traffic (lifecycle) accelerates initialisation,
   whether the discovery gap (slowstart) allows initialisation to complete
   before traffic arrives, and whether diluted traffic (host) extends
   initialisation — these are hypotheses the experiment tests, not
   assumptions the document makes.

4. **Service-quality impact is phase-dependent.** Under baseline (the only
   phase guaranteed to start from quiescent state with no carryover),
   routing quality is the dominant latency factor — mode differences should
   be most visible. Under storage load, I/O dominates — all modes should
   converge. Under compute load, uneven distribution may create hotspots —
   modes may diverge. Post-stress phases (cooldowns, demand_drop) may show
   attenuated effects due to residual backends from preceding stress phases.

5. **Variance is a finding.** If host's round-robin produces wider TTFT and
   TFR distributions than lifecycle's deterministic warm lease, the
   predictability of the routing mechanism is itself a dimension of
   redistribution quality — not just how fast, but how reliably fast.

No single mode is expected to dominate all metrics. Lifecycle should be
fastest and most aggressive. Slowstart should be the most gradual. Host
should be the most variable. If these trade-offs are borne out, the thesis
has characterised a genuine trade-off surface rather than declaring a
winner — which is the stronger contribution.

---

## 8. RQ2 ↔ RQ1 Parallel

| | RQ1 (Telemetry Freshness) | RQ2 (Backend Selection) |
|---|---|---|
| **Coordination gap** | Polling blind spot — controller misses telemetry windows between polls | Discovery gap — routing plane does not know about new backends until telemetry arrives |
| **Separated baseline** | Poll mode — controller fetches at intervals, missing intermediate windows | `topology_slowstart` — routing discovers backends via telemetry, not at spawn |
| **Unified approach** | Push mode — every window delivered at close, no blind spot | `topology_lifecycle` — warm lease at spawn time, no discovery gap |
| **Core measurement** | Reaction latency: `breach_detection_s + provision_time_s` | TTFT + TFR — how fast routing acts and how fast the backend serves |
| **Secondary measurement** | Timeout rate, throughput gap | Per-phase latency, initial load share |
| **User impact** | Failed or delayed requests during overload | Elevated latency if routing sends traffic to unready backends |

Together, RQ1 and RQ2 characterise whether the coordination gap — in
monitoring and in routing — produces measurable delays that co-location
eliminates.

---

## 9. Related Documents

| Document | Purpose |
|---|---|
| [`rq1.md`](../rq1/rq1.md) | RQ1 definition — direct methodological parallel |
| [`rq2_setup_v3.md`](rq2_setup_v3.md) | Canonical experiment setup declaration |
| [`experiment_plan_v3.md`](../../operation/testing/experiment/rq2_evaluation/v3/experiment_plan_v3.md) | Operational experiment plan |
| [`system_to_thesis_map_rq_v2.md`](../../../tese/miscelineous/system_to_thesis_map_rq_v2.md) | Full three-pillar thesis framing |
| [`../../source/sdn_controller/_vip_routing/selection.py`](../../../source/sdn_controller/_vip_routing/selection.py) | WSM cost functions and warm-lease logic |
| [`../../source/sdn_controller/_vip_routing/state.py`](../../../source/sdn_controller/_vip_routing/state.py) | Warm-lease lifecycle management |
