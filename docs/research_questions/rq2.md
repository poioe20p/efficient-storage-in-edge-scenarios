# RQ2 — Routing-Awareness Timing and the Coordination Gap

**Thesis pillar**: Backend Selection
**Status**: Implemented — ready for evaluation
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
| `topology_host` | **Immediately** — unknown stats treated as best-case (0.0, near-zero cost). Backend enters pool and wins every WSM competition from the first flow. No ramp-up, no priority window. | None — cold-start WSM (leastconn-style) | **No ramp-up, cold-start thundering herd.** Equivalent to HAProxy leastconn with no slow-start: a new backend with 0 connections wins all new traffic immediately. Fastest redistribution, least controlled. |
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
| `topology_host` | **Cold-start thundering herd.** Unknown stats → best-case (0.0, near-zero cost) → new backend wins every WSM competition from the first flow. Fastest redistribution, least controlled. Encodes HAProxy leastconn with no slow-start. |
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

Two measurements. **Measurement 1 (load redistribution time) is the core
evidence** — it directly quantifies the coordination gap in routing.
Measurement 2 captures the user-visible impact.

### 5.1 Load Redistribution Time — Core Evidence

```
redistribution_time = t_new_backend_reaches_equilibrium − spawn_done_ts
```

Measured after each scale-up event:

1. Identify `spawn_done_ts` from `container_events.csv`.
2. From `per_node_stats.csv`, track the new backend's request share over time.
3. Determine when its share stabilizes within ±10% of the per-backend mean.

Expected:

- `topology_host`: **Immediate thundering herd.** Unknown stats → best-case
  (near-zero cost) → new backend wins every WSM competition from the first
  flow. Fastest redistribution, but uncontrolled — may overwhelm a cold
  backend. Encodes HAProxy leastconn without slow-start.

- `topology_slowstart`: **Invisible then graduated ramp.** Backend is
  worst-case (1.0) until the first telemetry window closes (0–10 s after
  spawn, averaging ~5 s) — effectively invisible, receiving no traffic.
  Then the discovery-time ramp begins: graduated weight increase from
  worst-case to normal over the TTL period. The discovery gap is the
  **coordination delay** — the routing plane doesn't know the backend
  exists until telemetry proves it's alive.

- `topology_lifecycle`: **Immediate controlled ramp.** Warm lease at spawn
  time → backend receives priority traffic from t=0 → bounded priority
  window → normal competition when the lease expires. No cold-start herd,
  no discovery gap. Balanced: fast start, controlled transition.

The three modes now have genuinely distinct behaviors across the entire
timeline:
- `topology_host`: instant herd (0.0) → fastest, uncontrolled
- `topology_slowstart`: invisible (1.0) → graduated ramp at discovery → slowest start, smoothest
- `topology_lifecycle`: warm lease from t=0 → controlled ramp, zero gap

The key comparison is `topology_slowstart` vs `topology_lifecycle`: the
difference in redistribution time is the **coordination-gap penalty** in
the routing plane — directly parallel to RQ1's breach-detection penalty
from polling blind spots.

### 5.2 Per-Phase Service Quality — User-Visible Impact

p95/p99 latency and failure rate during the transition windows after
scale-up events. A mode with faster redistribution should show lower
latency and fewer failures during the `compute_spike` phase.

### 5.3 Measurement Chain

```
Routing mode: topology_host → topology_slowstart → topology_lifecycle
  ↓
  → redistribution: instant herd → invisible-then-ramp → instant controlled
  → coordination gap: none → 0–10 s discovery delay → none
  → transition-window service quality: variable (herd) → smooth (ramp) → smooth (warm lease)
```

---

## 6. Evaluation Design

Three runs, one per mode, using the canonical 10-phase workload. All runs
use push-mode telemetry and the golden configuration.

| Run | Mode | Routing awareness | Ramp-up |
|---|---|---|---|
| **R2-TH** | `topology_host` | Immediate (pool entry), unknown stats → 0.0 (best-case) | None — cold-start herd |
| **R2-SS** | `topology_slowstart` | Discovery-time (first telemetry, 0–10 s after spawn) | Invisible (1.0) → graduated ramp at discovery |
| **R2-TL** | `topology_lifecycle` | Spawn-time (atomic with pool registration) | Warm lease (bounded priority window) |

Hold constant:
- Telemetry delivery: push mode (ZMQ)
- Scaling policy: golden config thresholds
- Workload: `phases.json`
- Infrastructure: `CLIENTS=8`, `DEVICES=600`, `NODES=100`
- WSM weights and dimensions

Vary only: `BACKEND_SELECTION_POLICY` env var.

### 6.1 Run Order

**R2-TH → R2-SS → R2-TL.** R2-TH is the simplest baseline (no ramp-up).
R2-SS simulates the separated-LB coordination gap. R2-TL is the unified
controller approach.

### 6.2 Scale-Up Requirement

At least one scale-up event must occur during the run for redistribution
time to be measurable. If `CLIENTS=8` does not trigger compute scale-up,
increase client count or lower the threshold.

---

## 7. Expected Outcomes

1. **Redistribution speed vs. control forms a trade-off.**
   `topology_host` reaches equilibrium fastest (instant cold-start herd)
   but with the highest transition-window latency variance.
   `topology_slowstart` is smoothest (graduated ramp from discovery) but
   leaves capacity completely idle during the discovery gap (0–10 s).
   `topology_lifecycle` balances both — controlled ramp from t=0, no
   discovery gap, no cold-start herd.

2. **Transition-window service quality is best** under `topology_lifecycle`
   (no discovery gap, controlled ramp). If `topology_slowstart` and
   `topology_lifecycle` produce indistinguishable quality, the thesis
   bounds the result: the coordination gap in routing is measurable in
   redistribution timing but doesn't translate into user-visible impact
   at this scale.

3. **The coordination-gap penalty** is quantified as the difference between
   `topology_slowstart` and `topology_lifecycle` in redistribution time —
   directly parallel to RQ1's breach-detection penalty from polling blind
   spots.

If no mode is clearly dominant — each occupies a different point on the
speed-vs-control spectrum — the thesis has characterized a genuine
trade-off surface rather than declaring a winner. That's the stronger
contribution.

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
| `topology_host` | Skip `_claim_warm_backend()`. Unknown stats → 0.0 (best-case). Backend enters pool and wins every WSM competition immediately — cold-start thundering herd (leastconn-style). |
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
| **Cold-start thundering herd may make `topology_host` redistribute fastest with no latency penalty.** The new backend wins every competition immediately — if the cold backend handles the load fine, ramp-up mechanisms (warm lease or slow-start) add control but not speed. | This is not a threat — it's a potential **finding**. The thesis characterizes the trade-off: speed vs. control. |
| **The discovery gap (0–10 s, avg ~5 s) may dominate `topology_slowstart`.** The backend is invisible for one telemetry window — capacity sits idle during that window. | This is the coordination delay. The thesis honestly reports whether this idle-capacity period measurably degrades service quality. |
| **Single run per condition.** | Golden config demonstrated ≤0.23% variance across 15+ runs. Multi-run replication if needed. |
| **Scale-up may not trigger at `CLIENTS=8`.** | Increase client count or lower threshold. The mechanism necessity experiments confirmed triggers at `CLIENTS=48`. |

---

## 10. RQ2↔RQ1 Parallel

| | RQ1 (Monitoring) | RQ2 (Routing) |
|---|---|---|
| **Coordination gap** | Polling blind spot (controller misses telemetry windows between polls) | Discovery gap (routing plane doesn't know about new backends until telemetry arrives) |
| **Baseline** | Poll-30s (2 of 3 windows missed) | `topology_slowstart` (invisible until discovery, 0–10 s after spawn, avg ~5 s) |
| **Proposed** | Push (every window, no blind spot) | `topology_lifecycle` (warm lease at spawn time, no discovery gap) |
| **Core measurement** | Reaction latency (spawn_done − breach_window_end) | Redistribution time (equilibrium − spawn_done) |

Together, RQ1 and RQ2 characterize whether the coordination gap — in
monitoring and in routing — produces measurable delays that co-location
eliminates. Neither claims superiority; both report what was measured.

---

## 11. Related Documents

| Document | Purpose |
|---|---|
| [`system_to_thesis_map_rq_v2.md`](../../tese/miscelineous/system_to_thesis_map_rq_v2.md) | Full three-pillar thesis framing |
| [`rq1.md`](../research_questions/rq1.md) | RQ1 design — direct methodological parallel |
| TBD `experiment_plan.md` | Operational experiment plan |
| [`../../source/sdn_controller/_vip_routing/selection.py`](../../source/sdn_controller/_vip_routing/selection.py) | Current WSM cost functions and warm-lease logic |
| [`../../source/sdn_controller/_vip_routing/state.py`](../../source/sdn_controller/_vip_routing/state.py) | Warm-lease lifecycle management |
| [`../../source/sdn_controller/scaling_config.py`](../../source/sdn_controller/scaling_config.py) | Warm-lease TTL knobs |
