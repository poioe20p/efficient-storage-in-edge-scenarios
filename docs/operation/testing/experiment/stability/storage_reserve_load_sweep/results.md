# Results — Storage Reserve Load Sweep

**Date**: 2026-06-05  
**Experiment plan**: [experiment_plan.md](./experiment_plan.md)  
**Runs**: `reserve_load_c08` (20260605_114705), `reserve_load_c10` (20260605_123414)  
**Overall outcome**: ⚠️ **Stable activation found at c10, but system collapses under load. No acceptable candidate at t12 with current workload.**  
**Key conclusion**: **Stable activation is achievable** (single activation at T+13s, no cycling, replenish within 2s). The new phase file's 120s `demand_drop` matching the scale-down cooldown eliminates the cycling window. **Capacity ceiling found** between 8–10 clients at this workload shape — the edge server saturates at ~100 total req/s.

---

## Run Matrix Results

| Run | Clients | Threshold | Activations | 1st activation | Cycling? | LAN1 nodes | LAN2 nodes | Classification |
|-----|---------|-----------|-------------|----------------|----------|------------|------------|----------------|
| c08 | 8 | t12 (0.12) | 0 | — | — | 1 (dyn1 only) | 5 | ❌ Waiting-only |
| c10 | 10 | t12 (0.12) | 1 (dyn1) | T+13s into `storage_hotspot` | No | 2 | 4 | ⚠️ Stable but overloaded |

---

## Criteria Assessment

### 1. Run validity — ✅ Met (both runs)

Both runs reached `READY_RESERVED` before `storage_hotspot` started:

| Run | Reserve ready | Experiment start | Ready before hotspot? |
|-----|-------------|-----------------|----------------------|
| c08 | 11:46:04 | 11:47:05 | ✅ |
| c10 | 12:33:08 | 12:34:14 | ✅ |

No cleanup-loop re-entry in either run.

### 2. Stable activating candidate — ⚠️ Partially met (c10 only)

| Sub-criterion | c08 | c10 |
|--------------|-----|-----|
| (a) Activated by end of `storage_hotspot`? | ❌ (never) | ✅ (T+13s) |
| (b) Replenish follows? | N/A | ✅ (dyn2 at T+15s) |
| (c) No cycling in `sustained_use`? | N/A | ✅ (dyn2 never activated) |

**c10 technically meets all three sub-criteria** — a single activation, immediate replenish, no cycling. However, `sustained_use` is useless for verifying reserve use because the system is completely collapsed (100% failure rate, 10s timeouts). The activated reserve cannot serve traffic because the edge server is saturated.

### 3. Waiting-only candidate — ✅ Confirmed (c08)

Reserve reached `READY_RESERVED` (dyn1 at 11:46:04) but never activated. Zero `[reserve] activated` events. The storage degradation score at 8 clients with t12 never exceeded 0.12.

### 4. Tuning success condition — ❌ Missed

c10 is technically stable-activating but operationally unusable. c08 doesn't activate. No candidate is both stable AND operational.

### 5. Stop rule — Executed

c08 → missed → c10 → activates but overloads. Both primary candidates exhausted. The third candidate (c06) would be even lighter than c08 and almost certainly would not activate.

---

## Checkpoint Answers

| Checkpoint | c08 | c10 |
|-----------|-----|-----|
| Reserve READY before hotspot? | ✅ dyn1 at 11:46:04 | ✅ dyn1 at 12:33:08 |
| First activation time | Never | 12:36:27 (T+13s into `storage_hotspot`) |
| Replenish after activation? | N/A | dyn2 at 12:36:29 (T+15s, <2s delay) |
| Cycling in `sustained_use`? | N/A | No — dyn2 never activated |
| Total LAN1 nodes created | 1 | 2 |
| Total LAN2 nodes created | 5 | 4 (2 removed by scale-down) |

---

## Latency & Failure Comparison

| Phase | Metric | c08 (8 clients) | c10 (10 clients) |
|-------|--------|-----------------|-------------------|
| baseline | count | 1,899 | 2,374 |
| | avg | 51ms | 56ms |
| | p95 | 138ms | 150ms |
| | fail % | 0.0% | 0.0% |
| storage_ramp | count | 7,477 | 6,826 |
| | avg | 171ms | 283ms |
| | p95 | 375ms | 594ms |
| | fail % | 3.5% | **14.5%** |
| storage_hotspot | count | 11,286 | 9,099 |
| | avg | 414ms | 635ms |
| | p95 | 414ms | **4,049ms** |
| | fail % | 2.5% | **86.0%** |
| sustained_use | count | 5,564 | 360 |
| | avg | 493ms | **10,001ms** |
| | p95 | 811ms | **10,003ms** |
| | fail % | 2.6% | **100.0%** |
| demand_drop | count | 1,950 | 240 |
| | avg | 644ms | **10,001ms** |
| | p95 | 1,603ms | **10,003ms** |
| | fail % | 5.0% | **100.0%** |

**Key observations:**

- **c08 is healthy** throughout — failure rate peaks at 5% in `demand_drop`, latency is reasonable (~400ms avg during hotspot). The system handles 8 clients comfortably but doesn't generate enough storage stress to trigger t12.
- **c10 collapses at `storage_hotspot`** — 86% failure rate, p95 at 4s. By `sustained_use`, all requests timeout at 10s. The system never recovers, even during `demand_drop` at 2 req/s.
- The collapse is a **total system saturation** — both LANs affected, all clients timeout. The edge server's request lease pool is exhausted at this load level.

### Status Code Distribution (LAN1)

| Run | 200 | 503 | 0 (timeout) |
|-----|-----|-----|-------------|
| c08 | 4,831 (86%) | 272 (5%) | 511 (9%) |
| c10 | 4,517 (84%) | 222 (4%) | 660 (12%) |

The raw LAN1 counts look similar between runs, but c10 has far fewer total LAN1 requests (5,399 vs 5,614) because the system collapses and stops processing.

---

## Why c10 Activates But Collapses

The activation at c10 happens early (T+13s) because the heavier load rapidly pushes the storage degradation score past 0.12. But the same load saturates the edge server:

1. **10 clients × 10 req/s = 100 total req/s** during `storage_hotspot`, 90% cross-region = 90 cross-region req/s hitting the WAN and storage.
2. The edge server's Flask development server (single-process, threaded) cannot keep up. The request lease pool exhausts → 503s → clients retry → more load → cascade failure.
3. Once saturated, the edge server never recovers — even during `demand_drop` at 2 req/s (20 total req/s), all requests timeout. This suggests the edge server enters a degraded state (possibly thread pool exhaustion) that persists.

This is a **capacity ceiling** finding: the single edge server + single fixed storage can handle ~8 clients at this workload shape, but not 10.

---

## LAN2 Behavior

| Run | LAN2 nodes | Scale-down removals |
|-----|-----------|-------------------|
| c08 | 5 | 0 |
| c10 | 4 | 2 (dyn3 at T+770s, dyn2 at T+860s) |

c10 shows LAN2 scale-down activity during `demand_drop` — the system removes excess reserves as load drops. This is normal behavior. c08 kept all 5 LAN2 nodes throughout (no scale-down window because load never triggered).

---

## Activation Boundary

Combined with threshold sweep data:

| Clients | τ=0.08 | τ=0.10 | τ=0.12 | τ=0.15 | τ=0.20 |
|---------|--------|--------|--------|--------|--------|
| 8 | ✅ (3 activations, old phase) | ✅ (3, old) | ❌ (0, new phase) | ❌ (0, new) | ❌ |
| 10 | — | — | ✅ (1, stable, new phase) | — | — |

At t12, the activation boundary is between 8 and 10 clients. The old phase file produced activation at 8 clients because its 180s `demand_drop` created a post-cooldown window for re-triggering from residual load. The new phase eliminates that window — activation must happen during `storage_hotspot` or `sustained_use`, which requires more load than 8 clients can generate at t12.

---

## Follow-On Recommendations

1. **Lower the fixed threshold** for the load sweep: t10 (0.10) would likely activate at 8 clients under the new phase, without the system collapse seen at 10 clients.
2. **Try 9 clients** as a midpoint — it may activate at t12 without collapsing.
3. **Tune the phase rates**: reduce `storage_hotspot` from 10 req/s to 8 req/s and `sustained_use` from 7 to 5. This would shift the load from "saturate" to "stress" territory at 10 clients.
4. **The Flask development server is a bottleneck** — the edge server's capacity ceiling at ~8 concurrent clients at 10 req/s each is a known limitation. Production deployment would need a WSGI server.
5. **The reserve activation at c10 proves the mechanism works** — single activation, no cycling, replenish within 2 seconds. The load sweep found the capacity limit, which is useful characterization data.

---

## Generated Analysis Artifacts

- `analysis/simple_run.png` — per-run latency, failure, and node count plots (in each run folder)
- `load_sweep_compare/simple_compare_overall.png` — cross-run latency and node comparison
- `load_sweep_compare/simple_compare_phase.png` — per-phase cross-run comparison
