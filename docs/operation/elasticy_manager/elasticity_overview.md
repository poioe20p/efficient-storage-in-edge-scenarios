# Elasticity & Placement Manager — Overview

## Purpose

The Elasticity Manager (Thread 3) is responsible for mutating the infrastructure
in response to latency breaches and underutilization signals detected by Thread 2.
It handles spawning **and gracefully removing** `edge_server` and
`edge_storage_server` containers at runtime and wiring/unwiring them from the
running network.

---

## Architecture: Three-Thread Interaction

```text
Thread 2 (Observer/ZMQ)     Thread 3 (Elasticity Mgr)      Infrastructure
       │                              │
       │── Alert(type, lan) ─────────►│
       │                              │── NodeAdder.add_edge_server()
       │                              │      ├─ docker run           (timed)
       │                              │      ├─ add_network_node.sh  (timed)
       │                              │      └─ returns NodeResult (ip, mac, timings)
       │                              │
       │                              │── TopologyMixin.register_new_server_backend()
       │                              │      └─ Thread 1 picks up the new server via VIP pool + warm lease
```

- **Thread 1** (SDN controller main loop) — handles OpenFlow events, reactive
  L2 learning, and VIP routing. Never touches Thread 3 directly; it reads the
  shared VIP pool that Thread 3 mutates through `TopologyMixin`.
- **Thread 2** (`ZmqTelemetrySource`) — subscribes to aggregator and peer
  topology ZMQ endpoints, receives `TelemetrySummary` updates, caches the most
  recent peer-domain summary, evaluates local thresholds, and posts typed
  `Alert` objects to Thread 3's queue. In RQ2 arms (`SCALEUP_POLICY` ≠ `dual`)
  a `PolicyGate` selects **at most one** scale-up action per window from a
  declared bottleneck classification (see
  [`rq2_preparation.md`](../../research_questions/v2/rq2/rq2_preparation.md)).
- **Thread 3** (`ElasticityManager`) — a long-lived daemon thread blocking on a
  `queue.PriorityQueue`. Pops alerts in priority order (storage scale-up first)
  and dispatches them to the appropriate handler, which calls `NodeAdder` for
  the actual container lifecycle.

---

## Document Map

- [Orchestration](orchestration/elasticity_manager_orchestration.md) — Thread interaction, alert types, queue dispatch, busy/pending-drain state, cleanup dispatch, and handoffs.
- [Compute Scale-Up](scale_up/compute_scale_up.md) — Trigger path, degradation score, adaptive threshold, cooldowns, provisioning, and VIP admission.
- [Storage Scale-Up](scale_up/storage_scale_up.md) — Trigger path, diminishing-increment threshold, async replica-set join, deferred VIP_DATA promotion, and standby-first reference.
- [Compute Scale-Down](scale_down/compute_scale_down.md) — Idle detection, candidate selection, Phase A/B drain, cancel, and instrumentation.
- [Storage Scale-Down](scale_down/storage_scale_down.md) — Idle detection, VIP isolation, replica-set removal, script cleanup, and failure timeout.

---

## Diagram Map

- [Compute scale-up sequence](./diagrams/compute_scale_up.drawio)
- [Compute scale-down sequence](./diagrams/compute_scale_down.drawio)
- [Storage scale-up sequence](./diagrams/storage_scale_up.drawio)
- [Storage scale-down sequence](./diagrams/storage_scale_down.drawio)

Tier 1 diagrams live alongside the Tier 1 documentation:

- [Tier 1 scale-up sequence](./diagrams/tier1_scale_up.drawio)
- [Tier 1 scale-down sequence](./diagrams/tier1_scale_down.drawio)

---

## Tier 1 Selective Sync

Tier 1 selective sync promotes a hot subset of documents from a remote LAN's
replica set to a local `edge_selective_storage` container whenever sustained
cross-region latency breaches `TAU_DADOS_MS`. It is orthogonal to the
compute/storage scale-up paths: rather than adding capacity, it moves read
traffic to a closer node.

The full subsystem write-up — promotion predicate, state machine, priority
ordering, two-phase teardown, manifest protocol, and config-knob rationale —
lives in
[`selective_sync/selective_sync_overview.md`](../selective_sync/selective_sync_overview.md).

---

## Decision-Signal Statistics: Mean vs Median (and the Composite)

> Design principle, validated 2026-08-03 — full evidence chain in
> [`docs/operation/testing/experiment/v2/mean_vs_median_signal_finding.md`](../testing/experiment/v2/mean_vs_median_signal_finding.md).

Every `ScalingPolicy` decision signal consumes **one statistic** of a
per-window metric. The statistic is chosen by the **nature of the metric's
distribution**:

| Metric | Distribution | Statistic | Why |
|---|---|---|---|
| **Latency** (`T_db`, `T_proc`) | right-skewed, **unbounded** outliers (30 s `CURL_MAX_TIME` tail, cold reads; measured `med/mean ≈ 0.01` in the plateau — mean ~650 ms vs median ~4–16 ms) | **median** (`median_time_*_ms`) | median = the *typical request's* experience. In low-volume windows one slow request can move the mean by orders of magnitude → false "degraded" windows |
| **CPU** (compute, storage) | **bounded [0, 100%]** — an unbounded sample is physically impossible | **mean** (`average_*_cpu_percent`) | mean = average utilization over the window, which is exactly what determines queuing/saturation; no outlier can contaminate it |

The statistic is selected by `LATENCY_SIGNAL_MODE` — `mean` (legacy, RQ1,
byte-identical) or `median` (control group / RQ2+), with a fallback to the mean
when a pre-median aggregator does not publish the median.

**Why a pure-latency median is insufficient for the storage tier:** the median
has too little dynamic range in the control workload (plateau p25 ~4 ms vs
demand_drop ~2.6 ms → ~1.4 ms of separation), so a pure-latency `TAU` either
churns the plateau or fails to reclaim in `demand_drop` (measured: 12–17 %
plateau error vs mean-era 1.31 %). The storage tier therefore uses a
**composite signal** (control G0-v4): storage CPU (**mean** — bounded,
differentiates load: plateau p50 44–47 % vs demand_drop ~18 %) + median DB
latency, and a **CPU-aware scale-down gate** (`STORAGE_SCALE_DOWN_CPU_AWARE=1`
→ below = storage CPU < 22 % AND median DB < 8 ms). This reproduces the
mean-era envelope (2.0 % error, 3.0 concurrent storage, storage CPU 31.2 % ≈
mean-era 31.9 %) and is documented per mechanism in
[`scale_up/`](scale_up/), [`scale_down/`](scale_down/).

---

## Compute Readiness Gate (RQ3)

The compute spawn path now has an optional readiness gate
(`ReadinessGate`, `source/sdn_controller/readiness_gate.py`), active only when
`READINESS_PROPAGATION != "off"` (default `off`). When active, a spawned
`edge_server` backend is held `PendingBackend` until its `/ready` endpoint
returns `200`, which gates its `VIP_SERVER` admission; a backend that never
becomes ready within `READINESS_PROBE_MAX_S` is abandoned and fully torn down
(container, OVS veth/port, host entries, IP release). See
[RQ3 — Readiness Propagation and Traffic Admission](../../research_questions/v2/rq3/rq3_preparation.md).

---

## Implementation Plans

- [RQ2 bottleneck-aware scaling action](../../research_questions/v2/rq2/rq2_preparation.md) — policy gate selecting one scale-up action from a declared bottleneck classification (compute-first / storage-first / bottleneck-aware arms), per-tier action budget, per-decision evidence log.
- [Scale-down instrumentation](implementation/scale_down_instrumentation.md) — DEBUG/INFO observability for the scale-down decision path.
- [Metric drivers investigation](implementation/plans/metric_drivers_investigation_plan.md) — umbrella investigation into what drives CPU / T_db / T_proc.
- [Storage persistent reserve](implementation/storage_persistent_reserve/README.md) — phased implementation plan for a persistent same-LAN storage reserve that activates on first load or recovery and replenishes immediately after activation.
- [Compute graceful scale-down](implementation/compute_graceful_scale_down/README.md) — phased implementation for async two-phase drain.
- [Storage standby-first scale-up](implementation/storage_standby_first_scaleup/README.md) — phased implementation for pre-warmed Tier 2 standbys.
- [Documentation split](implementation/plans/elasticity_documentation_split_plan.md) — this split plan.
