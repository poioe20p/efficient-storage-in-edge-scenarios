# Run Summary — `reserve_use_rebind_t08`

**Run folder**: `source/scripts/testing/metrics/20260605_095057_reserve_use_rebind_t08/`  
**Experiment plan**: `docs/operation/testing/experiment/stability/storage_reserve_use_validation/experiment_plan.md`  
**Date**: 2026-06-05 09:50:57 UTC  
**Config**: `storage_reserve_threshold_t08.env` (SCALEUP_STORAGE_BASE_THRESHOLD=0.08)  
**Workload**: 8 clients/LAN, 600 devices, 100 nodes, hotspot `lan2_to_lan1` at 90% cross-region  
**Phases**: baseline (60s) → activation_probe (300s) → vip_rebind_gap (45s) → post_activation_use (180s) → demand_drop (120s)

---

## Verdict

**Reserve used after rebind gap — `reserve-used` classification reached.** The experiment plan's use-validation gate is satisfied: a fresh `MongoClient` was created during the `vip_rebind_gap` (epoch=2, recovery mode), and the post-gap controller routing targeted the activated reserve (`real=10.0.0.7`) via the recovery VIP path. However, LAN1 edge servers collapsed during `post_activation_use` with all requests returning `status=0`, meaning the reserve carried recovery-path traffic but the normal data plane was degraded.

---

## Plan Expectation Checklist

### Activation validity — ✅ Met
- `[reserve] activated lan=1 name=edge_storage_lan1_dyn1 ip=10.0.0.6 reason=load` at 09:51:24 (T+27s)
- `[reserve] activated lan=1 name=edge_storage_lan1_dyn2 ip=10.0.0.7 reason=load` at 09:55:05 (T+248s)

### Fresh-session validity — ✅ Met
- `Created MongoClient for lan1 epoch=2 mode=recovery via mongodb://10.0.0.252:27018/` at 09:54:49 — during `vip_rebind_gap`, before `post_activation_use`
- `maxIdleTimeMS=30000` — the 45s `vip_rebind_gap` exceeds the idle timeout, forcing a fresh connection

### Reserve-used classification — ✅ Met
- `vip_data(n1): client=10.0.0.2 -> vip=10.0.0.252 -> real=10.0.0.7 recovery=True` at 09:55:15 — 10s into `post_activation_use`
- Multiple subsequent routings to `10.0.0.7` at 09:55:39 and 09:55:55
- Routing used recovery VIP (`10.0.0.252`) with `recovery=True` — recovery-distress path activated

### Storage-side corroboration — ✅ Met
- `per_node_stats.csv` present — `request_count > 0` confirmed for activated reserves
- `resource_stats.csv` and `resource_stats_debug.csv` present (collector sync working)

---

## Per-Phase Latency

| Phase | Count | Mean | p50 | p95 | p99 |
|-------|-------|------|-----|-----|-----|
| baseline | 1,553 | 191ms | 18ms | 235ms | 6.2s |
| activation_probe | 19,688 | 178ms | 27ms | 218ms | 6.0s |
| vip_rebind_gap | 763 | 577ms | 48ms | **10.0s** | 10.0s |
| post_activation_use | 6,914 | 389ms | 159ms | 344ms | 10.0s |
| demand_drop | 1,058 | 973ms | 44ms | **10.0s** | 10.0s |

- `vip_rebind_gap` p95 at 10s confirms the 10-second client timeout — service_pressure requests experienced degradation
- `demand_drop` worse than `activation_probe` — residual instability from node churn

## Per-LAN Latency

| LAN | Count | Mean | p50 | p95 | Pattern |
|-----|-------|------|-----|-----|---------|
| lan1 | 13,360 | 328ms | **7.6ms** | 185ms | Bimodal: fast failures + timeouts |
| lan2 | 16,616 | 216ms | 98ms | 197ms | Normal distribution |

LAN1 bimodal (median 7.6ms, mean 328ms, p99 10s) — many fast `status=0` failures mixed with fast successes. During `post_activation_use`, ALL LAN1 clients reported `last status=0` while LAN2 clients were healthy at `status=200`.

---

## Request-Lease Outcomes

| LAN | success_normal | success_after_rebind | failure_terminal |
|-----|----------------|---------------------|-----------------|
| lan1 | 17,832 | 1 | 292 |
| lan2 | 8,062 | 0 | 126 |

- 292 terminal failures on LAN1 vs 126 on LAN2 — LAN1 was the stressed side
- Only 1 recovery rebind (vs 8 in the control run) — the rebind gap may have suppressed normal recovery attempts
- 191 avoidance markers, 0 fallback markers

---

## MongoClient Lifecycle (edge_server_n1.log)

| Timestamp | Epoch | Mode | VIP | Context |
|-----------|-------|------|-----|---------|
| 09:50:59 | 1 | normal | `10.0.0.254` | Initial connection during baseline |
| **09:54:49** | **2** | **recovery** | **`10.0.0.252`** | **Fresh connection during vip_rebind_gap** |
| 09:55:25 | 3 | normal | `10.0.0.254` | Post-gap return to normal VIP |

The epoch=2 recovery-mode MongoClient at 09:54:49 is the direct evidence that the `vip_rebind_gap` forced a fresh connection. The edge server detected recovery distress, switched to the recovery VIP (`10.0.0.252`), and the controller routed that connection to the activated reserve (`10.0.0.7`).

---

## Reserve Lifecycle

| Timestamp | Event |
|-----------|-------|
| 09:50:59 | dyn1 prepared (ready by ~09:51:14) |
| 09:51:24 | **dyn1 ACTIVATED** (reason=load), IP=10.0.0.6 |
| 09:52:59 | VIP_DATA routed to dyn1 via normal VIP (10.0.0.254) |
| 09:53:57 | dyn2 prepared |
| 09:55:05 | **dyn2 ACTIVATED** (reason=load), IP=10.0.0.7 |
| 09:55:15 | VIP_DATA routed to dyn2 via **recovery** VIP (10.0.0.252, recovery=True) |
| 09:55:25 | Fresh MongoClient epoch=3 (normal mode) |

---

## Defects

### LAN1 collapse during post_activation_use
All 8 LAN1 clients reported `status=0` with 10s timeouts throughout `post_activation_use` and `demand_drop`. LAN2 clients remained healthy. The edge_server_n1 log shows epoch transitions but the request path to storage was broken. Likely causes:
- Normal VIP_DATA (`10.0.0.254`) DNAT rules may have expired or pointed to a removed node
- The controller's recovery routing went to the recovery VIP, but normal routing may not have been updated
- The reserve cycling (dyn1 activated → dyn2 prepared → dyn1 possibly removed) may have left the normal VIP_DATA pool inconsistent

### LAN1 vs LAN2 asymmetry
LAN2 had 5 dynamic storage nodes, LAN1 had fewer after dyn1 removal. The `hotspot_direction=lan2_to_lan1` means LAN2 clients queried LAN1 storage cross-region — when LAN1 storage degraded, LAN2 clients also experienced 503s.

### policy_state.csv import error
`reconstruct_policy_state.py` on remote cannot import `parse_policy_annotations` from `parse_elasticity_logs.py` — non-fatal but needs fixing.

---

## Comparison: Control vs Rebind

| Metric | Control | Rebind |
|--------|---------|--------|
| Reserve activations | 3 | 2 |
| VIP_DATA path | Normal (`10.0.0.254`) | **Recovery** (`10.0.0.252`) post-gap |
| Telemetry errors | 0 | 0 |
| LAN1 post-activation health | Degraded (248 failures) | **Collapsed** (all status=0) |
| Fresh MongoClient evidence | N/A (no rebind gap) | ✅ epoch=2 recovery mode |
| resource_stats.csv | Missing | ✅ Present |
| Cycling pattern | 3 cycles in 10min | 2 cycles observed |

---

## Next Actions

1. **Use-validation gate: PASSED** — `reserve-used` classification reached on both control and rebind runs
2. **Threshold sweep**: `t08` activates reliably but causes cycling and LAN1 instability — test `t12`–`t15` to find stable operating point
3. **Fix `reconstruct_policy_state.py`** import error on remote
4. **Investigate LAN1 collapse**: check normal VIP_DATA DNAT rule state during `post_activation_use` — controller may not have updated normal-path rules after reserve activation
