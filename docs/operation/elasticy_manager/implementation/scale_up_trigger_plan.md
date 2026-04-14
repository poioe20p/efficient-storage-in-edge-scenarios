# Scale-Up Trigger — Implementation Plan

> **Status:** Implemented. This document reflects the current weighted
> degradation score approach in `main_n1.py` / `main_n2.py`.
>
> **Partial supersession (2026-04-13):** The **storage** tier now uses a
> separate **predictive adaptive threshold** instead of the shared
> `SCALEUP_SCORE_THRESHOLD`. Compute retains the parameters described here.
> See [`predictive_threshold_and_async_rs_plan.md`](predictive_threshold_and_async_rs_plan.md)
> for the storage-specific formula and parameters.

## Overview

The scale-up trigger decides **when to add a new server or storage node**.
It watches two numbers that the aggregator publishes every telemetry window
(~10 s): **CPU usage** and **latency** (processing time or DB time). From
those two numbers it computes a single **degradation score** between 0 and 1+.
When that score stays high for enough consecutive windows the controller tells
Thread 3 to spin up a new container.

This approach replaces the earlier AND-gate logic (CPU > τ AND latency > τ
for 2 consecutive windows) which had a dead zone: under saturation, CPU
sometimes drops while latency spikes (throughput collapse), so neither
condition fires at the same time.

---

## Why Not a Simple Threshold?

The old approach required CPU **and** latency to both be above a fixed
threshold at the same time. That creates a dead zone:

| Scenario | CPU | Latency | Old AND-gate | Problem |
|---|---|---|---|---|
| Normal saturation | High | High | ✓ fires | Works |
| Throughput collapse | **Drops** (fewer requests) | **Spikes** | ✗ misses | CPU drops *because* the system is overwhelmed — fewer requests complete |
| Large query | Low | High | ✗ correct | Not capacity-bound — adding nodes wouldn't help |

The weighted score fixes this: latency carries 70% of the weight, so even if
CPU drops during a spike, the score still crosses the threshold when latency
is high enough.

---

## The Degradation Score — Plain English

Think of it as a "how bad is it?" number. It blends CPU and latency into one
value:

```
score = (weight_cpu × cpu_component) + (weight_latency × latency_component)
```

Each component is normalised to roughly 0–1:

```
cpu_component     = max(0, cpu% − floor) / span
latency_component = max(0, latency_ms − floor) / span
```

- **Floor** = the value below which we don't care (baseline noise).
  If CPU is 40% and the floor is 50%, the component is 0.
- **Span** = how wide the "interesting" range is.
  Floor 50 + span 35 means 85% CPU → component = 1.0.
- Values above floor+span give a component > 1.0 — that's fine, the score
  just goes higher.

### Actual code

```python
@staticmethod
def _degradation_score(cpu, latency, w_cpu, w_lat,
                       cpu_floor, cpu_span, lat_floor, lat_span):
    cpu_component = max(0.0, cpu - cpu_floor) / cpu_span if cpu_span else 0.0
    lat_component = max(0.0, latency - lat_floor) / lat_span if lat_span else 0.0
    return w_cpu * cpu_component + w_lat * lat_component
```

### Default parameters

There are two independent scores — one for **storage** (DB tier) and one for
**compute** (edge server tier):

| Parameter | Storage | Compute | Meaning |
|---|---|---|---|
| CPU weight | 0.3 | 0.3 | CPU counts for 30% of the score |
| Latency weight | 0.7 | 0.7 | Latency counts for 70% of the score |
| CPU floor | 50% | 50% | Below 50% CPU → 0 contribution |
| CPU span | 35 | 35 | 85% CPU → CPU component = 1.0 |
| Latency floor | 15 ms (T_db) | 1 ms (T_proc) | Below this → 0 contribution |
| Latency span | 75 ms | 11 ms | Floor+span → latency component = 1.0 |

Latency gets 70% weight because it directly measures user impact. CPU gets
30% because it captures capacity pressure even when latency hasn't spiked yet.

---

## The Sliding Window — When Does It Actually Fire?

A single high score could be a fluke (one slow query, a brief GC pause). So
the controller keeps a **sliding window** of the last N evaluations and only
triggers when enough of them had a high score.

**Defaults:** score ≥ **0.85** in at least **3 out of the last 5** windows.

> **Note (2026-04-13):** These are the historical defaults. The current
> **compute** defaults are τ=0.40, 2-of-5. **Storage** now uses a separate
> adaptive threshold: base=0.25, +0.10/node, max=0.65, 1-of-3 window.

```
Window:   [True, True, False, True, False]
Count:     3 out of 5  →  ≥ 3 required  →  FIRES
```

### Actual code

```python
def _evaluate_scale_up(self, ds, lan, network_id):
    # ── Storage score ──
    storage_score = self._degradation_score(
        ds.avg_storage_cpu_percent, ds.avg_time_db_ms,
        _W_STORAGE_CPU, _W_T_DB,
        _STORAGE_CPU_FLOOR, _STORAGE_CPU_SPAN,
        _T_DB_FLOOR, _T_DB_SPAN,
    )
    above = storage_score >= _SCALE_UP_SCORE_THRESHOLD
    self._scale_up_storage_window.append(above)       # deque(maxlen=6)

    if sum(self._scale_up_storage_window) >= _SCALE_UP_REQUIRED:  # 4
        self._scale_up_storage_window.clear()
        self._scale_down_storage_window.clear()  # cross-direction reset
        self._elasticity.submit_alert(DataAlert(...))

    # ── Compute score ── (same pattern)
    compute_score = self._degradation_score(
        ds.average_cpu_percent, ds.avg_time_proc_ms,
        _W_CPU, _W_T_PROC,
        _CPU_FLOOR, _CPU_SPAN,
        _T_PROC_FLOOR, _T_PROC_SPAN,
    )
    above = compute_score >= _SCALE_UP_SCORE_THRESHOLD
    self._scale_up_compute_window.append(above)

    if sum(self._scale_up_compute_window) >= _SCALE_UP_REQUIRED:
        self._scale_up_compute_window.clear()
        self._scale_down_compute_window.clear()
        self._elasticity.submit_alert(ComputeAlert(...))
```

### Why 3-of-5 instead of the old 2-consecutive?

The old 2-consecutive approach was too fragile: one "good" window in the
middle of sustained degradation reset the counter to 0. The sliding window
tolerates up to 2 dips without losing the accumulated evidence, while being
more responsive (~30 s to fire vs ~40 s with 4-of-6).

---

## Asymmetry: Scale Up Fast, Scale Down Slow

| Direction | Window | Requirement | Wall-clock (~10 s/window) | Why |
|---|---|---|---|---|
| Scale-up | 5 | 3 of 5 above | ~50 s | React fast when users are affected |
| Scale-down | 12 | 7 of 12 below | ~120 s | Don't remove a node during a brief lull |

This is standard practice — K8s HPA uses 5 min stabilisation for scale-down
vs 0 s for scale-up.

---

## Cross-Direction Reset

When a scale-up fires, the scale-down sliding window is **cleared**. This
means the system needs 7 fresh idle windows before it can remove a node —
it can't reuse idle windows from before the scale-up.

The reverse also applies: when scale-down fires, the scale-up window is
cleared.

---

## No Explicit Cooldown

No cooldown timer is needed. Five mechanisms together prevent thrashing:

| Mechanism | What it prevents |
|---|---|
| `is_busy()` | Blocks all evaluation while Thread 3 is adding/removing (~30–180 s) |
| 3-of-5 sliding window | Ignores single-window spikes |
| 7-of-12 scale-down window | Tolerates up to 5 bad windows among 12 |
| Cross-direction reset | Forces fresh evidence after any scaling action |
| Timeout ceiling (5 s) | RS elections / connectivity timeouts don't poison scale-down |

---

## Environment Variables

All scale-up env vars are prefixed with `SCALEUP_` to avoid collision with
VIP routing weights (`W_CPU`, `W_STORAGE_CPU`) defined in `osken-controller.env`.

### Scale-up (weighted score)

| Env var | Default | Description |
|---|---|---|
| `SCALEUP_W_STORAGE_CPU` | `0.3` | Storage score: CPU weight |
| `SCALEUP_W_T_DB` | `0.7` | Storage score: T_db weight |
| `SCALEUP_STORAGE_CPU_FLOOR` | `50` | Storage CPU: below this → 0 |
| `SCALEUP_STORAGE_CPU_SPAN` | `35` | Storage CPU: range width |
| `SCALEUP_T_DB_FLOOR` | `15` | T_db (ms): below this → 0 |
| `SCALEUP_T_DB_SPAN` | `75` | T_db (ms): range width |
| `SCALEUP_W_CPU` | `0.3` | Compute score: CPU weight |
| `SCALEUP_W_T_PROC` | `0.7` | Compute score: T_proc weight |
| `SCALEUP_CPU_FLOOR` | `50` | Compute CPU: below this → 0 |
| `SCALEUP_CPU_SPAN` | `35` | Compute CPU: range width |
| `SCALEUP_T_PROC_FLOOR` | `1` | T_proc (ms): below this → 0 |
| `SCALEUP_T_PROC_SPAN` | `11` | T_proc (ms): range width |
| `SCALEUP_SCORE_THRESHOLD` | `0.85` | Score must be ≥ this to count as "degraded" |
| `SCALEUP_WINDOW_SIZE` | `6` | Number of recent windows to consider |
| `SCALEUP_REQUIRED` | `4` | How many of those windows must be degraded |

### Scale-down (unchanged from `node_removal_plan.md`)

| Env var | Default | Description |
|---|---|---|
| `TAU_CPU_DOWN` | `65` | Compute CPU below → idle |
| `TAU_PROC_DOWN_MS` | `5` | T_proc below → idle |
| `TAU_STORAGE_CPU_DOWN` | `60` | Storage CPU below → idle |
| `TAU_DB_DOWN_MS` | `100` | T_db below → idle |
| `SCALE_DOWN_COMPUTE_WINDOW_SIZE` | `12` | Sliding window size (compute) |
| `SCALE_DOWN_COMPUTE_REQUIRED` | `7` | Required below-threshold windows |
| `SCALE_DOWN_STORAGE_WINDOW_SIZE` | `12` | Sliding window size (storage) |
| `SCALE_DOWN_STORAGE_REQUIRED` | `7` | Required below-threshold windows |
| `SCALE_DOWN_PROC_TIMEOUT_CEILING_MS` | `5000` | T_proc above → skip window |
| `SCALE_DOWN_DB_TIMEOUT_CEILING_MS` | `5000` | T_db above → skip window |

---

## Instance State

### In `__init__()`

```python
# Scale-up: per-tier sliding-window deques (True = score above threshold)
self._scale_up_compute_window: deque[bool] = deque(maxlen=_SCALE_UP_WINDOW_SIZE)
self._scale_up_storage_window: deque[bool] = deque(maxlen=_SCALE_UP_WINDOW_SIZE)
```

These replaced the old `_scale_up_compute_consecutive: int` and
`_scale_up_storage_consecutive: int` counters.

---

## Worked Example

Given a telemetry window with: **storage CPU = 72%**, **T_db = 85 ms**

```
cpu_component = max(0, 72 - 50) / 35 = 22/35 = 0.629
lat_component = max(0, 85 - 15) / 75 = 70/75 = 0.933
score         = 0.3 × 0.629  +  0.7 × 0.933
              = 0.189         +  0.653
              = 0.842
```

Score 0.842 < 0.85 → this window counts as **not degraded**.

If T_db were 90 ms instead:

```
lat_component = max(0, 90 - 15) / 75 = 75/75 = 1.0
score         = 0.3 × 0.629 + 0.7 × 1.0 = 0.889
```

Score 0.889 ≥ 0.85 → this window counts as **degraded** (True in the deque).

---

## Verification

| # | Scenario | Expected |
|---|---|---|
| 1 | Score ≥ 0.85 for 3 of 5 windows | Scale-up alert fires; scale-down window cleared |
| 2 | Score ≥ 0.85 for 2 of 5 windows | No alert — insufficient evidence |
| 3 | CPU high but latency low (score < 0.85) | No alert — working hard but keeping up |
| 4 | CPU low but latency very high (score ≥ 0.85) | Alert fires — latency alone can push score over 0.85 because it has 70% weight |
| 5 | Scale-up fires → load drops → 7/12 below | Scale-down fires (needs fresh windows because cross-direction reset) |
| 6 | `is_busy()=True` | No window updates, no alerts |
| 7 | Two dips in the middle of sustained stress | Tolerated — 3-of-5 still passes with two False |
| 8 | Compute degraded, storage fine | Only ComputeAlert fires; storage window unaffected |

---

## Design Decisions

| Decision | Rationale |
|---|---|
| Weighted score (not AND gate) | AND gate has a dead zone during throughput collapse: CPU drops when latency spikes because fewer requests complete. The weighted score captures this because latency carries 70% of the weight. |
| 70/30 latency/CPU split | Latency is the direct user-facing signal. CPU is a supporting indicator of capacity pressure. Validated against 3 experiment runs showing clean separation between healthy and degraded phases. |
| 3-of-5 sliding window (not consecutive) | Consecutive counters reset on a single good window. The sliding window tolerates brief fluctuations during sustained degradation. More responsive than 4/6 while still tolerating 2 noisy windows. |
| `SCALEUP_` env var prefix | Avoids collision with VIP routing weights (`W_CPU`, `W_STORAGE_CPU`) in `osken-controller.env` which serve a different purpose (weighted shortest-path cost function). |
| Score can exceed 1.0 | By design — values above floor+span just push the score higher. No clamping needed because the threshold check is ≥, not ==. |
| Storage and compute evaluated independently | A storage bottleneck should add a storage node; a compute bottleneck should add a compute server. They don't block each other. |

---

## Files Changed

| File | What changed |
|---|---|
| `source/sdn_controller/main_n1.py` | Replaced threshold constants with score parameters, added `_degradation_score()`, rewrote `_evaluate_scale_up()` |
| `source/sdn_controller/main_n2.py` | Same changes (evaluates compute before storage, opposite order from n1) |
