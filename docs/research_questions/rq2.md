# RQ2 — Routing-Awareness Timing and the Coordination Gap

**Thesis pillar**: Backend Selection
**Status**: Evaluated — results available
**Experiment**: [`docs/operation/testing/experiment/rq2_evaluation/`](../operation/testing/experiment/rq2_evaluation/)
**Thesis map**: [`tese/miscelineous/system_to_thesis_map_rq_v2.md`](../../tese/miscelineous/system_to_thesis_map_rq_v2.md)

---

## 1. Thesis Context

This thesis investigates whether collapsing three traditionally separated
control-plane concerns — **information acquisition** (monitoring), **backend
selection** (load balancing), and **infrastructure adaptation** (auto-scaling)
— into a single SDN controller process eliminates coordination gaps that
degrade service quality during demand shifts.

RQ1 tested this for monitoring: does push-mode telemetry (in-process) beat
polling (separated monitoring) by eliminating the blind spot between scrapes?
The mechanism was **missed telemetry windows** — the controller simply doesn't
see what happened between polls.

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

When the controller's elasticity manager spawns a new backend (Thread 3),
the routing plane (Thread 1) can become aware of it in three ways:

### 3.1 Three Modes

| Mode | When routing becomes aware | Ramp-up mechanism | Encodes |
|---|---|---|---|
| `topology_host` | **Immediately** — unknown stats treated as best-case (0.0, near-zero cost). All backends tie at cost 0.0; round-robin tie-breaking distributes traffic evenly across the pool. No ramp-up, no priority window, no concept of backend readiness. | None — round-robin fair-share (no ramp, no warm lease) | **No lifecycle awareness.** Equivalent to a basic load balancer (HAProxy round-robin) with no backend readiness concept: new backends enter the pool immediately and receive ~1/N fair-share traffic, but serve it cold — before DB connections and caches warm. |
| `topology_slowstart` | **At discovery time** — when the first telemetry window containing the new backend arrives (0–10 s after spawn, averaging ~5 s). Until then: treated as worst-case (1.0, effectively invisible). After discovery: graduated weight ramp over a configurable TTL period. | Invisible until discovery, then graduated ramp | **Separated LB slow-start with coordination delay.** In a separated system, the LB doesn't know the backend exists until health checks pass. The backend is effectively invisible for the discovery gap — encoding the coordination delay that RQ1 also measures for monitoring. |
| `topology_lifecycle` | **At spawn time** — Thread 3 creates a warm lease atomically with pool registration. The routing plane sees the backend as "warm" and short-circuits the WSM to select it with priority. | Warm lease (bounded priority window, spawn-time atomic) | **Unified controller.** Routing knows about the spawn immediately because routing and scaling share the same process. No discovery delay, no coordination gap. |

### 3.2 The Coordination Gap in Routing

In a separated architecture, the sequence is:

```text
Separated (Kubernetes-style):
  Scaler spawns pod (t=0)
    → Pod boots (t=10s)
      → LB health check discovers pod (t=15s, first successful check)
        → Slow-start ramp begins (t=15s)
          → Pod reaches full weight (t=45s)

  Coordination gap: 15 s between spawn and discovery.
  Pod was ready at t=10s but the LB didn't know until t=15s.

Unified (SDN controller):
  Scaler spawns container (t=0)
    → Warm lease created (t=0, atomic with pool registration)
      → Router immediately biases toward new backend (t=0)
        → Warm lease expires, backend competes normally (t=45s)

  Coordination gap: 0 s. The router knew at spawn time.
```

The question is whether this gap is measurable in practice: does spawn-time
awareness (`topology_lifecycle`) produce faster or smoother load
redistribution than discovery-time slow-start (`topology_slowstart`), and
does either beat no ramp-up at all (`topology_host`)?

The modes also test a second timing dimension: **backend readiness** —
how long the container takes to warm up its DB connection pool and
internal caches (~5–10 s). The three modes differ in how they align
traffic arrival with this fixed warm-up period:

| Mode | Traffic starts | Backend warm at | Mismatch | Latency outcome |
|---|---|---|---|---|
| `topology_host` | t≈0 s | t≈5–10 s | **5–10 s gap** | Worst (200 ms p50 non-stress) |
| `topology_slowstart` | t≈10 s | t≈5–10 s | **~0 s gap** | Best (7 ms p50 non-stress) |
| `topology_lifecycle` | t≈0 s | t≈2–3 s | **~2 s gap** | Good (7 ms p50 non-stress) |

Slowstart's discovery delay doubles as a warm-up window. Lifecycle's
warm lease concentrates traffic, accelerating cache population. Host
dilutes traffic via round-robin — the backend never receives enough
concentrated load to warm up efficiently.

### 3.3 What Is Held Constant

- Telemetry delivery: **push mode** (ZMQ at window close) — RQ1's optimal.
- Scaling policy: golden configuration thresholds and cooldowns.
- Workload: canonical 10-phase `phases.json`.
- Infrastructure: two-LAN topology, WAN emulation, containerized services.
- Double-VIP model: `VIP_SERVER` + `VIP_DATA_N1` + `VIP_DATA_N2`.
- WSM weights and dimensions: identical across all modes (CPU, RAM, requests,
  connections, hops).
- Replica lag is empirically zero at this workload — not a differentiator.

Vary only: **when and how the routing plane becomes aware of a new backend**
(`BACKEND_SELECTION_POLICY` env var).

---

## 4. Why This Question Exists

### 4.1 Purpose

RQ2 tests whether the **coordination gap in routing** — the delay between
spawn and routing-plane awareness — measurably affects load redistribution
quality. RQ1 tested the same phenomenon for monitoring (push vs poll).
Together they characterize whether co-locating the control plane eliminates
delays that matter in practice.

The thesis does not claim the unified approach is superior. It characterizes
the trade-off: if spawn-time awareness produces faster redistribution, the
coordination gap is measurable and co-location eliminates it. If all three
modes redistribute load equally well, the gap exists on paper but is
inconsequential at this scale — still a valid finding.

### 4.2 What Each Condition Encodes

| Condition | Encodes |
|---|---|
| `topology_host` | **No lifecycle awareness — round-robin fair-share with cold-start latency.** Unknown stats → best-case (0.0). All backends tie at cost 0.0 → round-robin distributes ~1/N fair share (~30%). Backends receive traffic immediately but serve it cold — DB connections and caches not yet warm. Encodes a basic load balancer with no backend readiness concept. |
| `topology_slowstart` | **Separated LB slow-start with coordination gap.** Backend invisible (worst-case, 1.0) until telemetry arrives (0–10 s, avg ~5 s). Then graduated ramp at discovery. The discovery gap is the coordination delay — same phenomenon RQ1 measures. Smoothest ramp but slowest start. |
| `topology_lifecycle` | **Spawn-time warm lease.** Zero discovery gap — routing aware at spawn time (atomic with pool registration). Warm lease provides a bounded priority window — controlled ramp, no cold-start herd. Balanced: fast start, controlled transition. |

### 4.3 Integration with RQ3

RQ3 provisions backends (Tier 2 cold/warm spawns). RQ2 determines how
quickly those backends receive traffic after they're provisioned:

| RQ3 provides | RQ2 determines |
|---|---|
| Compute scale-up → new edge server spawned | How fast does it start receiving traffic? (Redistribution time) |
| Tier 2 cold → new storage replica spawned | How fast does it reach equilibrium load share? |

The synthesis: **RQ3 controls what capacity exists; RQ2 controls how
quickly that capacity is utilized.** Warm provisioning (RQ3) without
spawn-time routing awareness (RQ2) means idle capacity. Spawn-time
awareness (RQ2) without provisioning (RQ3) means nothing to route to.

---

## 5. How It Is Measured

The experiment tests two timing dimensions simultaneously: **awareness
timing** — when the routing plane learns about the new backend (§5.1–§5.2)
— and **readiness timing** — how long the backend takes to warm up and
whether traffic arrival aligns with that window (§5.3).

### 5.1 Traffic Allocation — TTFT and Initial Load Share

**Time-to-First-Traffic (TTFT):**
```
ttft = t(first_request_arrives_at_new_backend) − spawn_done_ts
```

**Initial Load Share:**
```
initial_share = new_backend_request_count / total_VIP_requests_in_first_window
```

Computed for each scale-up event from `controller_lan*.log` (spawn timestamp,
backend MAC) and `per_node_stats.csv` (first window with `request_count > 0`).

| Mode | TTFT | Initial share | Mechanism |
|---|---|---|---|
| `topology_host` | 51 s (variable, 0–251 s) | 30% (~1/N fair share) | Round-robin distributes evenly; counter state determines when new backend first wins |
| `topology_slowstart` | 71 s (slowest, consistent) | 55% | Invisible until telemetry discovery (~10 s); graduated ramp thereafter |
| `topology_lifecycle` | 40 s (fastest, consistent) | 73% (highest) | Warm lease at spawn time short-circuits WSM |

**Coordination-gap penalty**: the TTFT difference between slowstart and
lifecycle (31 s ≈ one extra telemetry window) and the initial-share
difference (−18 pp). These parallel RQ1's breach-detection penalty from
polling blind spots.

Equilibrium-based redistribution proved unmeasurable — 0 of 47 events
stabilised under continuous stress because phase transitions and scale-down
precede steady-state. TTFT and initial share capture the coordination gap
without requiring the system to stabilise.

### 5.2 Service Quality — Per-Phase Latency

p50/p95/p99 latency disaggregated by phase and LAN, from `client_requests.csv`.

| Mode | Non-stress p50 (lan1) | Stress p50 | p95 (all) |
|---|---|---|---|
| `topology_host` | 200 ms | ~200–600 ms | ~2500 ms |
| `topology_slowstart` | 7 ms | ~200–600 ms | ~2500 ms |
| `topology_lifecycle` | 7 ms | ~200–600 ms | ~2500 ms |

Host's non-stress penalty comes from traffic hitting cold backends during
the warm-up window. In stress phases, MongoDB I/O dominates regardless of
routing policy. Failure rate is 0% across all modes; the 30 s client timeout
ceiling affects ~1–3% of requests independent of mode.

### 5.3 Readiness Alignment

Routing-plane awareness controls *when* traffic arrives. But the backend
is not instantaneously ready — its DB connection pool and internal caches
take ~5–10 s to warm up. The three modes differ in how they align traffic
arrival with this fixed warm-up period, producing a second timing dimension:

| Mode | Traffic starts | Backend warm | Mismatch | Outcome |
|---|---|---|---|---|
| `topology_host` | t≈0 s | t≈5–10 s | **5–10 s gap** | Traffic hits cold backend → worst latency |
| `topology_slowstart` | t≈10 s (after discovery) | t≈5–10 s | **~0 s gap** | Traffic arrives when warm → best latency |
| `topology_lifecycle` | t≈0 s (warm lease) | t≈2–3 s | **~2 s gap** | Concentrated traffic accelerates warm-up → good latency |

Slowstart's discovery delay doubles as a warm-up window — the backend
becomes visible only after it has had time to prepare. Lifecycle's warm
lease concentrates 100% of traffic on one backend, accelerating cache
population and narrowing the mismatch to ~2 s. Host dilutes traffic via
round-robin across all backends — the new backend never receives enough
concentrated load to warm up efficiently, producing the largest mismatch
and the worst latency.

Together, awareness timing and readiness timing characterise the two
constraints that routing policy must satisfy: **traffic should arrive as
soon as possible, but not before the backend is ready to serve it.**

### 5.4 Measurement Chain

```
Routing mode: topology_host → topology_slowstart → topology_lifecycle
  ↓
  → TTFT: variable (51 s) → slowest (71 s) → fastest (40 s)
  → initial share: 30% (fair-share) → 55% (ramp) → 73% (warm lease)
  → coordination gap: N/A → 31 s penalty vs lifecycle → baseline
  → service quality (non-stress): 200 ms lan1 → 7 ms → 7 ms
  → service quality (stress): all converge — storage I/O dominates
  → readiness mismatch: 5–10 s → ~0 s → ~2 s
```

---

## 6. Evaluation Design

Nine runs, three per mode, using a two-cycle scale-up workout workload.
All runs use push-mode telemetry and the golden configuration.

| Run | Mode | Routing awareness | Ramp-up |
|---|---|---|---|
| **R2-TH** | `topology_host` | Immediate (pool entry), unknown stats → 0.0 (best-case) | None — cold-start herd |
| **R2-SS** | `topology_slowstart` | Discovery-time (first telemetry, 0–10 s after spawn) | Invisible (1.0) → graduated ramp at discovery |
| **R2-TL** | `topology_lifecycle` | Spawn-time (atomic with pool registration) | Warm lease (bounded priority window) |

Hold constant:
- Telemetry delivery: push mode (ZMQ)
- Scaling policy: golden config thresholds
- Workload: `phases_rq2.json` (9-phase, two-cycle, all-local, rate=4.0)
- Infrastructure: `CLIENTS=32`, `CONTENT_ITEMS=6000`, `USERS=100`, `RANDOM_SEED=42`
- WSM weights and dimensions

Vary only: `BACKEND_SELECTION_POLICY` env var.

### 6.1 Run Order

Grouped by mode: all `topology_host` reps → all `topology_slowstart` reps →
all `topology_lifecycle` reps. Between every run: cleanup + VM reboot.

**Full experiment plan**: [`experiment_plan.md`](../operation/testing/experiment/rq2_evaluation/experiment_plan.md)

### 6.2 Scale-Up Requirement

Calibrated at `CLIENTS=32`. All modes survive (0% failure rate).
`topology_host` fails at `CLIENTS=48` (cold backends overloaded before warm-up completes).

---

## 7. Expected Outcomes

1. **The coordination gap is quantifiable through TTFT and initial load share.**
   `topology_lifecycle` achieves the fastest TTFT (median 40 s) and highest
   initial share (73%) because the warm lease routes traffic from t=0.
   `topology_slowstart` is the slowest (median 71 s TTFT, 55% share) because
   the backend is invisible during the discovery gap. `topology_host` is
   variable (median 51 s, range 0–251 s) because the round-robin counter
   state at spawn time determines whether the new backend wins the first
   cycle; its 30% initial share reflects 1/N fair-share distribution, not
   a herd effect.

2. **Redistribution-to-equilibrium is not reachable under continuous stress.**
   The architecture precludes steady-state load shares by design — backends
   spawn mid-overload and are removed during cooldown before load can
   stabilize. This is not a threat to validity but a finding: in
   continuously-scaling edge systems, redistribution quality must be measured
   through immediate allocation metrics (TTFT and initial share), not
   convergence time.

3. **Service-quality impact is phase-dependent and LAN-localised.**
   During non-stress phases, `topology_host` shows elevated p50 latency on
   the spawn LAN (200 ms vs 7 ms for other modes) because round-robin routes
   traffic to cold backends before DB connections and caches warm.
   `topology_slowstart` and `topology_lifecycle` have indistinguishable
   p50 latency (~7 ms non-stress, ~140 ms aggregate) — the discovery gap
   and warm lease differ in traffic-allocation timing, not per-request speed.
   During stress phases, all three modes converge (~200–600 ms p50) because
   MongoDB I/O dominates regardless of routing policy. Tail latency (p95)
   is storage-bound across all modes (~2500 ms, indistinguishable).

4. **The coordination-gap penalty** is the difference in TTFT between
   `topology_slowstart` and `topology_lifecycle` (31 s, or ~1 extra
   telemetry window) and the difference in initial share (−18 pp).
   These directly parallel RQ1's breach-detection penalty from polling
   blind spots.

5. **The round-robin tie-breaking mechanism is the hidden driver of
   `topology_host` behaviour.** When all backends tie at WSM cost 0.0,
   the round-robin counter distributes traffic evenly — producing the
   observed ~30% initial share (approximately 1/N fair share). There is
   no "herd" or single "winner" — `topology_host`'s name reflects a
   host-based LB with no topology awareness, not a thundering herd.
   The latency penalty arises from the mismatch between immediate traffic
   and backend warm-up time, not from overloading.

If no mode is clearly dominant — lifecycle is fastest for traffic
allocation, slowstart achieves the best latency by aligning traffic
arrival with warm-up completion, host is fair-share
but slow — the thesis has characterized a genuine trade-off surface
rather than declaring a winner. That's the stronger contribution.

---

## 8. Development Required

### 8.1 Policy Mode Implementation

Add `BACKEND_SELECTION_POLICY` env var to `_vip_routing/config.py`:

```python
_BACKEND_SELECTION_POLICY = os.environ.get(
    "BACKEND_SELECTION_POLICY", "topology_lifecycle"
)
```

Three modes in `_vip_routing/selection.py`:

| Mode | Behavior |
|---|---|
| `topology_host` | Skip `_claim_warm_backend()`. Unknown stats → 0.0 (best-case). All backends tie at cost 0.0; round-robin tie-breaking distributes traffic evenly (~1/N fair share). No ramp, no warm lease — backends receive traffic immediately but serve it cold. |
| `topology_slowstart` | Skip `_claim_warm_backend()`. Unknown stats → 1.0 (worst-case). Backend is effectively invisible until first telemetry arrives (0–10 s, avg ~5 s). At discovery: start a graduated cost penalty that decays linearly from 1.0 to 0.0 over the warm-lease TTL — simulating discovery-time slow-start ramp. |
| `topology_lifecycle` | Current behavior unchanged — warm lease at spawn time via `_claim_warm_backend()`. |

Estimated: ~40 lines across `selection.py` and `config.py`.

### 8.2 Controller Env Overrides

- `testing/controller_env_overrides/rq2_topology_host.env` → `BACKEND_SELECTION_POLICY=topology_host`
- `testing/controller_env_overrides/rq2_topology_slowstart.env` → `BACKEND_SELECTION_POLICY=topology_slowstart`

Default (no override) preserves `topology_lifecycle`.

---

## 9. Validity Threats

| Threat | Mitigation |
|---|---|
| **Round-robin fair-share in `topology_host` gives new backends traffic immediately but cold — producing elevated latency.** Without a ramp or warm lease, backends serve requests before DB connections and caches warm. | This is not a threat — it's a **finding**. The thesis characterizes the trade-off: immediate traffic allocation vs. per-request latency. Slowstart delays traffic until the backend is warm (best latency, slowest TTFT). Lifecycle routes traffic immediately but with concentrated volume that accelerates warm-up (fastest TTFT, good latency). Host routes traffic immediately but diluted across round-robin — the backend never gets enough concentrated traffic to warm up fast (worst latency). |
| **The discovery gap (0–10 s, avg ~5 s) may dominate `topology_slowstart`.** The backend is invisible for one telemetry window — capacity sits idle during that window. | This is the coordination delay. The TTFT difference (71 s vs 40 s) quantifies it. Slowstart's idle-capacity period is measurable. |
| **Redistribution-to-equilibrium may not be reachable under continuous stress.** Backends spawn mid-overload and are removed during cooldown before load stabilizes. | Confirmed: 0 of 47 events reached equilibrium. The measurement framework now uses TTFT and initial load share — metrics that capture the coordination gap without requiring the system to stabilize. This is not a failure but a finding about edge-system dynamics. |
| **Three replicates per mode may not detect small effects.** | Cohen's d analysis: large effects (initial share, host p50) are conclusive at n=3. Small effects (p95 differences, d < 0.22) are indistinguishable — reported honestly as null results. |
| **`topology_host` shows extreme within-mode variance.** | The round-robin tie-breaking is timing-dependent — whether the new backend wins the first cycle depends on the counter state at spawn time. Per-replicate scatter dots on all graphs expose this variance. The variance itself is a finding: without a ramp or lease, traffic arrival timing is unpredictable. |

---

## 10. RQ2↔RQ1 Parallel

| | RQ1 (Monitoring) | RQ2 (Routing) |
|---|---|---|
| **Coordination gap** | Polling blind spot (controller misses telemetry windows between polls) | Discovery gap (routing plane doesn't know about new backends until telemetry arrives) |
| **Baseline** | Poll-30s (2 of 3 windows missed) | `topology_slowstart` (invisible until discovery, 0–10 s after spawn) |
| **Proposed** | Push (every window, no blind spot) | `topology_lifecycle` (warm lease at spawn time, no discovery gap) |
| **Core measurement** | Reaction latency (spawn_done − breach_window_end) | Time-to-first-traffic (first_request − spawn_done) + initial load share |
| **Coordination penalty** | Extra breach-detection time from missed windows | Extra telemetry window before first traffic (71 s vs 40 s); 18 pp less initial share |

Together, RQ1 and RQ2 characterize whether the coordination gap — in
monitoring and in routing — produces measurable delays that co-location
eliminates. Neither claims superiority; both report what was measured.

---

## 11. Related Documents

| Document | Purpose |
|---|---|
| [`system_to_thesis_map_rq_v2.md`](../../tese/miscelineous/system_to_thesis_map_rq_v2.md) | Full three-pillar thesis framing |
| [`rq1.md`](../research_questions/rq1.md) | RQ1 design — direct methodological parallel |
| [`experiment_plan.md`](../operation/testing/experiment/rq2_evaluation/experiment_plan.md) | Operational experiment plan (9-run design) |
| [`results.md`](../operation/testing/experiment/rq2_evaluation/results.md) | Experiment results and graph explanations |
| [`../../source/sdn_controller/_vip_routing/selection.py`](../../source/sdn_controller/_vip_routing/selection.py) | Current WSM cost functions and warm-lease logic |
| [`../../source/sdn_controller/_vip_routing/state.py`](../../source/sdn_controller/_vip_routing/state.py) | Warm-lease lifecycle management |
| [`../../source/sdn_controller/scaling_config.py`](../../source/sdn_controller/scaling_config.py) | Warm-lease TTL knobs |
