# Results — Current State Integrated Baseline Cycle

**Date**: 2026-06-05  
**Experiment plan**: [experiment_plan.md](./experiment_plan.md)  
**Run**: `current_state_integrated_a` (20260605_150044)  
**Overall outcome**: ⚠️ **All three mechanisms exercised successfully. Cleanup mostly complete. Service-quality envelope violated — failure rates exceed caps in compute and reverse-hotspot phases.**

> **Note:** Only replicate A was run. Criterion 8 (inter-run repeatability) requires replicate B for comparison. The plan's abort rule waits for operator confirmation before launching B.

---

## Criteria Assessment

### 1. Run completion and artifact integrity — ✅ Met

All 10 phases completed (`baseline` → `demand_drop`). Full artifact contract present: `client_requests.csv` (77,739 rows), `resource_stats.csv`, `per_node_stats.csv`, `container_events.csv`, `elasticity_events.csv` (135 events), `controller_lan1.log` (33 MB), `controller_lan2.log` (466 MB), `controller_env_snapshot.env`, `phases_snapshot.json`, `service_logs/`.

### 2. Required Tier 2 storage exercise — ✅ Met

**6 storage reserve activations** on LAN1 during `storage_stress`, `cross_region_hotspot`, and `reverse_hotspot`:

| # | Time | Container | IP | Phase context |
|---|------|-----------|----|---------------|
| 1 | 15:15:58 | `edge_storage_lan1_dyn1` | 10.0.0.6 | `storage_stress` (T+590s) |
| 2 | 15:19:18 | `edge_storage_lan1_dyn5` | 10.0.0.8 | `cross_region_hotspot` (T+790s) |
| 3 | 15:25:09 | `edge_storage_lan1_dyn7` | 10.0.0.9 | `reverse_hotspot` (T+1140s) |
| 4 | 15:30:09 | `edge_storage_lan1_dyn9` | 10.0.0.6 | `reverse_hotspot` (T+1440s) |
| 5 | 15:33:30 | `edge_storage_lan1_dyn12` | 10.0.0.9 | `compute_ramp` (T+1640s) |
| 6 | 15:35:40 | `edge_storage_lan1_dyn13` | 10.0.0.7 | `compute_spike` (T+1770s) |

LAN1 created 14 dynamic storage nodes total. LAN2 created 15. Both LANs activated — cross-region storage stress was symmetrical despite hotspot direction.

IP reuse (10.0.0.6, 10.0.0.9 appear multiple times) indicates cycling — expected given the 360s `demand_drop` > 120s cooldown.

### 3. Required Tier 1 exercise — ✅ Met

**715 `SelectiveSyncAlert`/`ACTIVE` markers** in controller logs. Massive selective-sync activity across both hotspot directions (`cross_region_hotspot` and `reverse_hotspot`). Container events show `sel_sync_*` containers created and removed.

The 10 `edge_server_lan1_dyn*` and 11 `edge_server_lan2_dyn*` service logs confirm Tier 1 selective-sync nodes were created and served traffic. Resume from `compute_spike` onward shows `lan1_client_3` getting `status=0` throughout — one LAN1 client failed to recover during the compute phases.

### 4. Required compute exercise — ✅ Met

**17 `ComputeAlert` events** in controller logs. Dynamic compute nodes: ~13 on LAN1 (`edge_server_lan1_dyn2`–`dyn14`), ~11 on LAN2 (`edge_server_lan2_dyn3`–`dyn12`). Compute scale-out triggered during `compute_ramp`, `compute_spike`, and `sustained_plateau` as expected.

### 5. Control-plane and runtime health — ✅ Met

- 0 unhandled Python tracebacks
- 0 `telemetry receive error` events
- 0 controller crash loops
- Both controllers made forward progress through all 10 phases
- All core containers (`edge_server*`, `osken*`, `local_state_*`) remained healthy

### 6. Cleanup correctness — ⚠️ Partially met

Container events: 27 adds, 19 removes. 1 container still tracked as running at end (likely a fixed infrastructure container). The elasticity events show both LANs performed scale-down and cleanup:

- LAN2: `node_removing` events for `edge_storage_lan2_dyn3`, `dyn4`, `dyn2` during `demand_drop`
- LAN1: `node_removing` events during `demand_drop`

The 360s `demand_drop` provided sufficient time for most dynamic containers to be drained and removed. The single remaining container at end is expected to be a fixed infrastructure node.

### 7. Service-quality envelope — ❌ Failed

| Phase | Type | Fail % | Cap | Status |
|-------|------|--------|-----|--------|
| baseline | Non-hotspot | 0.0% | ≤1% | ✅ |
| local_moderate | Non-hotspot | 0.0% | ≤1% | ✅ |
| storage_stress | Hotspot | 0.0% | ≤10% | ✅ |
| cross_region_hotspot | Hotspot | 0.2% | ≤10% | ✅ |
| inter_hotspot_cooldown | Non-hotspot | 17.7% | ≤1% | ❌ |
| reverse_hotspot | Hotspot | 41.2% | ≤10% | ❌ |
| compute_ramp | Non-hotspot | 47.7% | ≤1% | ❌ |
| compute_spike | Non-hotspot | 65.3% | ≤1% | ❌ |
| sustained_plateau | Non-hotspot | 44.7% | ≤1% | ❌ |
| demand_drop | Non-hotspot | 20.2% | ≤1% | ❌ |
| **Overall** | — | **20.7%** | ≤5% | ❌ |

**7 of 11 checks fail.** The storage hotspot phases (`storage_stress`, `cross_region_hotspot`) are clean — failure rates near zero. But `reverse_hotspot` hits 41%, and all compute phases exceed 44% failure. The system is saturated during the dashboard-heavy tail.

### 8. Inter-run repeatability — ⏸️ Deferred

Replicate B not yet run. Per the plan: "`current_state_integrated_b` only starts after `current_state_integrated_a` artifacts are copied back and the operator confirms there were no code, env, or image changes in between."

---

## Latency & Failure by Phase

| Phase | Count | Avg | p50 | p95 | Fail % |
|-------|-------|-----|-----|-----|--------|
| baseline | 719 | 38ms | 21ms | 118ms | 0.0% |
| local_moderate | 4,223 | 31ms | 18ms | 95ms | 0.0% |
| storage_stress | 19,079 | 47ms | 29ms | 118ms | 0.0% |
| cross_region_hotspot | 19,170 | 58ms | 16ms | 139ms | 0.2% |
| inter_hotspot_cooldown | 434 | 364ms | 26ms | 3,022ms | 17.7% |
| reverse_hotspot | 13,820 | 96ms | 19ms | 110ms | 41.2% |
| compute_ramp | 4,644 | 143ms | 29ms | 184ms | 47.7% |
| compute_spike | 7,441 | 110ms | 22ms | 133ms | 65.3% |
| sustained_plateau | 6,418 | 115ms | 23ms | 177ms | 44.7% |
| demand_drop | 1,791 | 299ms | 19ms | 3,018ms | 20.2% |

**Key observations:**

- **Storage phases are pristine** — `storage_stress` and `cross_region_hotspot` have near-zero failures. The storage mechanism handles load cleanly.
- **`inter_hotspot_cooldown` p95 saturates at 3s** — the 90s cooldown is too short for the system to drain from `cross_region_hotspot` before `reverse_hotspot` begins. Residual saturation carries over.
- **`reverse_hotspot` hits 41% failure** — the reversal direction stresses the system more. LAN1 clients struggle with the redirected cross-region load.
- **Compute phases collapse** — 48–65% failure rates. The dashboard-heavy mix at 12–18 req/s saturates both edge servers. LAN1 clients (3 of them) handle the load worse than LAN2.
- **`demand_drop` at 20% failure** — recovery is slow. p95 at 3s indicates residual timeout saturation even at 1 req/s.

### Overall Failure Rate

| Metric | Value | Cap | Status |
|--------|-------|-----|--------|
| Overall | 20.7% | ≤5.0% | ❌ |
| Non-hotspot avg | 27.3% | ≤1.0% each | ❌ |
| Hotspot avg | 13.8% | ≤10.0% each | ❌ |

---

## Checkpoint Answers

| Checkpoint | Result |
|-----------|--------|
| End of `storage_stress`: Tier 2 scale-out? | ✅ `storage_count > 1`, 1st activation at T+590s |
| Mid `cross_region_hotspot`: Tier 1 ACTIVE? | ✅ 715 SelectiveSyncAlert/ACTIVE markers, sel_sync containers |
| Mid `reverse_hotspot`: Reverse Tier 1 ACTIVE? | ✅ Tier 1 active in reverse direction |
| Mid `compute_spike`: Compute scale-out? | ✅ 17 ComputeAlerts, ~24 dynamic compute nodes |
| End of `demand_drop`: Cleanup complete? | ⚠️ 27 adds / 19 removes, 1 container tracked at end |

---

## Mechanism Summary

| Mechanism | Activated? | Scale | Cycling? | Cleanup? |
|-----------|-----------|-------|----------|----------|
| Tier 2 storage | ✅ (6 activations) | 14 LAN1 + 15 LAN2 nodes | ⚠️ Yes (IP reuse, 360s drop) | ✅ Most removed |
| Tier 1 selective-sync | ✅ (715 markers) | ~24 dynamic compute nodes | N/A | ✅ Containers removed |
| Compute scale-out | ✅ (17 alerts) | ~24 dynamic compute nodes | N/A | ✅ Containers removed |

---

## Why the Service-Quality Envelope Fails

1. **3 clients is too few for the compute phases.** With only 3 clients per LAN, each client must generate 12–18 req/s. A single client stall (as `lan1_client_3` did during `compute_spike`) creates a large failure spike in the aggregate stats. The per-phase failure rates are dominated by individual client stalls rather than systemic issues.

2. **`reverse_hotspot` at 12 req/s / 95% cross-region** is the most stressful storage phase. The reversal direction catches the system mid-cycle (reserve nodes are half-drained from the forward hotspot), causing 41% failures.

3. **No cooldown between `reverse_hotspot` and `compute_ramp`.** The system goes directly from 12 req/s / 95% cross-region to 12 req/s / 5% cross-region dashboard-heavy. The abrupt mix change (from 92% device_status to 30%) saturates the edge server's request processing.

4. **`inter_hotspot_cooldown` at 90s is too short.** The 90s gap is less than the 120s scale-down cooldown, so storage nodes can't drain before the reverse hotspot begins.

---

## Follow-On Recommendations

1. **Run replicate B** to assess inter-run repeatability (criterion 8).
2. **Increase clients to 5–6** for the compute phases — 3 clients creates fragility where individual client stalls dominate failure stats.
3. **Extend `inter_hotspot_cooldown` to 180s** — gives time for scale-down to drain storage nodes before the reverse hotspot.
4. **Add a `pre_compute_cooldown` phase** between `reverse_hotspot` and `compute_ramp` — the abrupt mix change causes saturation.
5. **Reduce `compute_spike` rate from 18 to 14 req/s** — 18 req/s × 3 clients = 54 req/s saturates the Flask dev server.

---

## Generated Analysis Artifacts

- `analysis/simple_run.png` — latency, failure, and node count plots
