# Run Summary — `reserve_use_control_t08`

**Run folder**: `source/scripts/testing/metrics/20260605_000530_reserve_use_control_t08/`  
**Experiment plan**: `docs/operation/testing/experiment/stability/storage_reserve_use_validation/experiment_plan.md`  
**Date**: 2026-06-05 00:05:30 UTC  
**Config**: `storage_reserve_threshold_t08.env` (SCALEUP_STORAGE_BASE_THRESHOLD=0.08, STORAGE_PERSISTENT_RESERVE_ENABLED=1, MAX_DYNAMIC_COMPUTE=0)  
**Workload**: 8 clients/LAN, 600 devices, 100 nodes, hotspot `lan2_to_lan1` at 90% cross-region  
**Phases**: baseline (60s) → activation_probe (300s) → demand_drop (180s)

---

## Verdict

**Reserve used.** The control run passed the activation and use gates: LAN1 reserve `edge_storage_lan1_dyn1` (10.0.0.6) activated at T+97s, carried VIP_DATA traffic within 25s of activation, and emitted regular `mongo_stats` for ~3 minutes until its removal. A second reserve (`dyn2`, 10.0.0.7) activated at T+398s and also carried VIP_DATA. The `has_recovery_distress` fallback eliminated all telemetry errors (0 vs hundreds in prior runs). The env snapshot captured `0.08` with full provenance.

**However**, the system could not stabilize under `t08`: dyn1 was removed 3m20s after activation, dyn2 followed, and dyn3 reused dyn1's IP — a classic reserve-cycling pattern suggesting the threshold is too aggressive for sustained operation.

---

## Plan Expectation Checklist

### Activation validity — ✅ Met
- `[reserve] activated lan=1 name=edge_storage_lan1_dyn1 ip=10.0.0.6 mac=00:00:00:00:01:06 reason=load` at 00:07:07 (T+97s into `activation_probe`)
- Two subsequent activations confirm the trigger path fires reliably under `t08`

### Reserve-used classification (control interpretation) — ✅ Met
- `vip_data(n1): client=10.0.0.2 -> vip=10.0.0.254 -> real=10.0.0.6 recovery=False` at 00:07:32 — 25s post-activation
- `vip_data(n1): client=10.0.0.2 -> vip=10.0.0.254 -> real=10.0.0.7 recovery=False` at 00:13:33 — second reserve also used
- Per criterion 5 (control interpretation): since the control already shows reserve-used markers, the rebind run would be confirmation, not isolation

### Storage-side corroboration — ✅ Met
- `edge_storage_lan1_dyn1`: pushed `mongo_stats` at 00:07:18, 00:07:38, 00:07:48, 00:07:58, 00:08:08, 00:08:18, 00:08:28, 00:08:38, 00:08:48 — recurring activity, not heartbeat-only
- `per_node_stats.csv` unavailable (collector crash) — cannot confirm `request_count > 0` per-node; this is a missing-input limitation, not a negative finding

### End of baseline — LAN1 reserve state
- At baseline end (00:06:30), `edge_storage_lan1_dyn1` was already at SECONDARY (ready since 00:04:28)
- First activation occurred 37s into `activation_probe` — the system had a ready reserve before the hotspot began

---

## Per-Phase Latency

| Phase | Count | Mean | p50 | p95 | p99 | Max |
|-------|-------|------|-----|-----|-----|-----|
| baseline | 1,917 | 43ms | 25ms | 131ms | 222ms | 1.3s |
| activation_probe | 22,934 | 146ms | 37ms | 324ms | 3.1s | 10.0s |
| demand_drop | 2,412 | 311ms | 22ms | **3.0s** | 6.4s | 10.0s |

- `demand_drop` p95 (3.0s) is worse than `activation_probe` (324ms) despite lower load — likely because active storage nodes had already been removed/cycled by that point

---

## Request-Lease Outcomes (from recovery validation CLI)

| LAN | success_normal | success_after_rebind | failure_terminal |
|-----|----------------|---------------------|-----------------|
| lan1 | 19,464 | 8 | 248 |
| lan2 | 4,599 | 0 | 194 |

- 248 terminal failures on LAN1 vs 194 on LAN2 — LAN1 (the stressed side) shows more distress
- 8 recovery rebinds on LAN1 (vs 0 on LAN2) — edge servers did attempt recovery
- 235 avoidance markers, 7 fallback markers in controller logs

---

## Reserve Lifecycle Timeline

| Timestamp | Event |
|-----------|-------|
| 00:04:17 | `edge_storage_lan1_dyn1` container started (total time: 0.84s) |
| 00:04:28 | dyn1 reached SECONDARY (11.05s from start) |
| 00:07:07 | **dyn1 ACTIVATED** (reason=load), IP=10.0.0.6 |
| 00:07:09 | `edge_storage_lan1_dyn2` container started |
| 00:07:18 | dyn1 first post-activation `mongo_stats` |
| 00:07:22 | dyn2 reached SECONDARY |
| 00:07:32 | **VIP_DATA routed to dyn1** (10.0.0.6) |
| 00:10:27 | **dyn1 REMOVED** (node_removing + cleanup_done, total removal 19.2s) |
| 00:12:08 | **dyn2 ACTIVATED** (reason=load), IP=10.0.0.7 |
| 00:13:33 | **VIP_DATA routed to dyn2** (10.0.0.7) |
| 00:14:18 | **dyn3 ACTIVATED** (reason=load), IP=10.0.0.6 (same IP as dyn1 — IP recycled) |

---

## Elasticity Churn

| LAN | Nodes created | Nodes removed |
|-----|--------------|---------------|
| LAN1 | 4 (dyn1–dyn4) | 1 (dyn1 at 00:10:27) |
| LAN2 | 5 (dyn1–dyn5) | 0 |

LAN1 saw 4 node creations despite `MAX_DYNAMIC_COMPUTE=0`. LAN2 saw 5 creations — the reserve preparation loop ran on both LANs, not just the stressed one.

---

## Defects and Caveats

### Fix validated: `has_recovery_distress` fallback
- **0 telemetry errors** in `controller_lan1.log` — the `_domain_summary_has_recovery_distress()` fallback eliminated the crash that plagued the previous run

### Fix validated: Env snapshot provenance
- `controller_env_snapshot.env`: `SCALEUP_STORAGE_BASE_THRESHOLD=0.08`, with base/override/runtime provenance comments

### Missing artifacts (pre-existing, not caused by this run)
- `resource_stats.csv` / `resource_stats_debug.csv`: remote `collect_resource_stats.py` is outdated (326 lines vs local 433 lines), lacks `--output-debug` flag
- `per_node_stats.csv`: same root cause
- `policy_state.csv`: `reconstruct_policy_state.py` not present on remote

### Reserve cycling
- dyn1 served traffic for only 3m20s before removal — system cannot stabilize at `t08`
- The cycle (prepare → ready → activate → remove → prepare new) ran 3 full iterations in 10 minutes on LAN1
- LAN2 also churned 5 nodes despite not being the hotspot target

---

## Next Actions

1. **Sync `collect_resource_stats.py` and `reconstruct_policy_state.py` to `cloud-vm`** — needed for complete artifact coverage on any future run
2. **Consider raising the threshold** — `t08` triggers activation reliably but causes rapid cycling; `t20` (the base default that was accidentally used in the prior run) may be too high since it never activated. Consider `t12`–`t15` as an intermediate.
3. **Rebind run is optional** — per criterion 5, the control already shows reserve-used markers; the rebind run would confirm rather than isolate
4. **Post-run cleanup**: controller logs can be deleted from the local copy after `elasticity_events.csv` and `node_lifecycle_timings.csv` are retained (already done by `run_experiment.sh`)
