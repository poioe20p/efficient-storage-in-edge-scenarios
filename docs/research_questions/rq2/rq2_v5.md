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

---

## 6. Graph Summary

12 graphs (same set as v3, corrected data):

| Graph | Content | Affected by fix? |
|-------|---------|-----------------|
| G1 — TTFT Distribution | Box plot per mode + scatter dots | ✅ TTFT values corrected |
| G2 — TFR Distribution | Box plot per mode + scatter dots | — (TFR from client_requests.csv) |
| G2b — TTFT vs TFR Scatter | 2D scatter, shape=mode | ✅ TTFT axis corrected |
| G3 — Backend Initialisation Time | Box plot per mode + scatter dots | ✅ Derived from TTFT + TFR |
| G4 — Initial Load Share | Box plot per mode + scatter dots | — (share from window aggregates) |
| G4b — TTFT vs Initial Share Scatter | 2D scatter, shape=mode, dot size=pool size | ✅ TTFT axis corrected |
| G5 — Baseline p50 Latency | Grouped bar + scatter dots | — (latency from client_requests.csv) |
| G5b — Non-Stress p50 Latency | Grouped bar per phase + scatter dots | — |
| G6 — Per-Phase p50 Latency | Grouped bar, all phases + scatter dots | — |
| G7 — Latency Percentiles | Grouped bar p50/p95/p99 + scatter dots | — |
| G8 — Latency by Phase Type (p95) | Grouped bar, 4 groups + scatter dots | — |
| G8b — Latency by Phase Type (p50) | Grouped bar, 4 groups + scatter dots | — |

---

## 7. Relationship to v3 and v4

| | v3 | v4 | v5 |
|---|---|---|---|
| **What** | Initial RQ2 campaign | Warm-lease round-robin fix | Full re-run, corrected architecture |
| **Runs** | 9 new runs | 3 new Lifecycle runs | 9 new runs |
| **Key finding** | Coordination gap: 20.4 s (inflated) | Fix had no effect; MAC-reuse bug discovered | Tests corrected scoring + MAC-reuse fix |
| **Status** | Invalidated | Negative result | This experiment |

v4 tested a warm-lease round-robin fix in `_claim_warm_backend()`. The fix did
not change median TTFT (20.9 s both ways) but tripled Lifecycle IQR
(10.8→49.6 s). v5 reverts to the original `max(started_ts)` policy and runs
with the fully corrected architecture. See
[`v4/results.md`](../../operation/testing/experiment/rq2_evaluation/v4/results.md).

---

## 8. References

- v3 methodology: [`rq2_v3.md`](rq2_v3.md)
- v3 setup: [`rq2_setup_v3.md`](rq2_setup_v3.md)
- v5 experiment plan: [`../operation/testing/experiment/rq2_evaluation/v5/experiment_plan_v5.md`](../../operation/testing/experiment/rq2_evaluation/v5/experiment_plan_v5.md)
- v5 setup: [`rq2_setup_v5.md`](rq2_setup_v5.md)
- v4 results (warm-lease negative result): [`../operation/testing/experiment/rq2_evaluation/v4/results.md`](../../operation/testing/experiment/rq2_evaluation/v4/results.md)
- RQ1 v4 (scoring correction reference): [`../operation/testing/experiment/rq1_thesis_final/v4/experiment_plan_v4.md`](../../operation/testing/experiment/rq1_thesis_final/v4/experiment_plan_v4.md)
- Extraction fix: [`source/scripts/testing/analysis/rq2/extract_spawn_metrics.py`](../../../source/scripts/testing/analysis/rq2/extract_spawn_metrics.py)
