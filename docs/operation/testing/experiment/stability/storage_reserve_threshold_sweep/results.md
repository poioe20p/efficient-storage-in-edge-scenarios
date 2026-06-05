# Results — Storage Reserve Threshold Sweep

**Date**: 2026-06-05  
**Experiment plan**: [experiment_plan.md](./experiment_plan.md)  
**Runs**: `reserve_threshold_t15` (20260605_103643), `reserve_threshold_t12` (20260605_105036), `reserve_threshold_t10` (20260605_110405)  
**Overall outcome**: ❌ **No stable-activating candidate found. All activating thresholds cycle.**  
**Key conclusion**: **Activation boundary is $0.12 < \tau \leq 0.15$.** Cycling is structural — caused by the old phase file's 180s `demand_drop` exceeding the 120s scale-down cooldown, not by threshold choice.  

> **⚠️  Post-analysis update (2026-06-05):** The phase file has been replaced. These runs used `phases_experiment_storage_reserve_activation_probe.json` (baseline → activation_probe → demand_drop), which lacked a `sustained_use` phase. The new shared workload at `phases_experiment_storage_reserve_shared.json` adds a 180s `sustained_use` phase and shortens `demand_drop` to 120s to match the scale-down cooldown. The criteria assessment below reflects the old phase file; re-running with the new workload may produce different (stable) outcomes.

---

## Run Matrix Results

| Run | Threshold | Activations | 1st activation | Phase of 1st | LAN1 nodes | LAN2 nodes | Classification |
|-----|-----------|-------------|----------------|-------------|------------|------------|----------------|
| 1 | **t15** (0.15) | 2 (dyn1→dyn2) | 10:43:21 | demand_drop (+38s) | 3 | 5 | ❌ Cycles |
| 2 | **t12** (0.12) | 2 (dyn1→dyn2) | 10:57:04 | demand_drop (+28s) | 3 | 5 | ❌ Cycles |
| 3 | **t10** (0.10) | 3 (dyn1→dyn2→dyn3) | 11:08:43 | activation_probe (T+218s) | 4 | 5 | ❌ Cycles |

Combined with prior evidence (`t08` = 3+ cycles, `t20` = waiting-only):

| τ | 0.08 | 0.10 | 0.12 | 0.15 | 0.20 |
|---|------|------|------|------|------|
| Activates | ✅ | ✅ | ✅ | ✅ | ❌ |
| 1st in probe | ✅ (T+37s) | ✅ (T+218s) | ❌ (+28s after) | ❌ (+38s after) | — |
| Cycles? | 3 | 3 | 2 | 2 | — |

---

## Criteria Assessment

### 1. Run validity — ✅ Met (all runs)

All three runs reached `READY_RESERVED` before `activation_probe` started. In every run, `edge_storage_lan1_dyn1` was ready during the setup phase (before baseline):

| Run | Reserve ready time | Experiment start | Ready before probe? |
|-----|-------------------|-----------------|---------------------|
| t15 | 10:35:43 | 10:36:43 | ✅ |
| t12 | 10:49:35 | 10:50:36 | ✅ |
| t10 | 11:03:04 | 11:04:05 | ✅ |

No cleanup-loop re-entry observed in any run.

### 2. Stable activating candidate — ❌ Missed (all runs)

Criterion 2 requires: (a) activation within `activation_probe`, (b) fresh replenish follows, (c) **no cycling**.

| Sub-criterion | t15 | t12 | t10 |
|--------------|-----|-----|-----|
| (a) Activated in probe? | ❌ (both after) | ❌ (both after) | ✅ (1st at T+218s) |
| (b) Replenish follows? | ✅ (<1s) | ✅ (<1s) | ✅ (<1s) |
| (c) No cycling? | ❌ (2 activations) | ❌ (2 activations) | ❌ (3 activations) |

**No run meets all three sub-criteria.** t10 comes closest with an in-probe activation, but still cycles.

### 3. Waiting-only candidate — ❌ Not applicable

No run was waiting-only. Even t15 (the most conservative) activated twice. The prior `t20` result (waiting-only) is the only data point in that category.

### 4. Cycling candidate — ✅ Confirmed (t10, t12, t15 all cycle)

The cycling pattern is consistent across all activating thresholds:

```
dyn1 activated → dyn2 prepared (<1s later) → dyn1 removed → dyn2 activated → dyn3 prepared (<1s later) → ...
```

Scale-down cooldown (120s) does not prevent cycling — it only delays it. After cooldown expires, the activated reserve is removed, creating a gap that the next reserve fills. This creates a sawtooth pattern of activation → removal → re-activation.

### 5. Tuning success condition — ❌ Missed

No candidate is acceptable (stable-activating). The experiment does not find a preferred operating point.

### 6. Stop rule — Executed correctly

`t15` → missed (activated but cycled) → `t12` → missed (cycled) → `t10` → missed (cycled). All three primary candidates exhausted.

### 7. Escalation rule — Triggered

> "If none of t15, t12, t10 yield a stable activation, widen the threshold range or revisit the workload shape before changing load."

---

## Checkpoint Answers

| Checkpoint | t15 | t12 | t10 |
|-----------|-----|-----|-----|
| Reserve READY before probe? | ✅ dyn1 at 10:35:43 | ✅ dyn1 at 10:49:35 | ✅ dyn1 at 11:03:04 |
| First activation time | 10:43:21 (demand_drop) | 10:57:04 (demand_drop) | 11:08:43 (activation_probe) |
| Replenish after 1st activation? | dyn2 at 10:43:22 (<1s) | dyn2 at 10:57:05 (<1s) | dyn2 at 11:08:44 (<1s) |
| Cycling count within probe? | 0 (both after probe) | 0 (both after probe) | 1 (dyn1 in probe, dyn2/dyn3 after) |
| Total LAN1 nodes created | 3 | 3 | 4 |
| Total LAN2 nodes created | 5 | 5 | 5 |

---

## Latency & Failure Comparison

| Phase | Metric | t15 | t12 | t10 |
|-------|--------|-----|-----|-----|
| baseline | count | 1,913 | 1,910 | 1,905 |
| | avg | 47ms | 45ms | 42ms |
| | p95 | 135ms | 135ms | 118ms |
| | fail % | 0.0% | 0.0% | 0.0% |
| activation_probe | count | 23,552 | 23,809 | 23,354 |
| | avg | 151ms | 151ms | 151ms |
| | p95 | 360ms | 358ms | 340ms |
| | fail % | 1.7% | 1.8% | **8.6%** |
| demand_drop | count | 2,476 | 2,509 | 2,330 |
| | avg | 262ms | 254ms | 342ms |
| | p95 | 3,009ms | 1,742ms | 3,016ms |
| | fail % | 18.6% | 18.7% | 20.3% |

**Key observations:**

- `activation_probe` average latency is identical across all thresholds (151ms) — the fixed storage node absorbs the steady load regardless of threshold.
- `t10` has a **significantly higher failure rate during activation_probe** (8.6% vs ~1.7%) — the earlier activation (T+218s) coincides with a spike in `status=0` (timeout) and `status=503` responses. The activation event itself may cause a brief service disruption.
- `demand_drop` p95 latency saturates at ~3s for t10 and t15, reflecting client timeouts during the phase transition. t12 has lower p95 (1,742ms) — possibly because its activations happen earlier in demand_drop, giving time for recovery.

---

## LAN2 Behavior (Cross-Talk)

All three runs show LAN2 creating exactly 5 dynamic storage nodes despite not being the hotspot target. This is the persistent reserve mechanism maintaining a standby reserve on LAN2 independently of the hotspot. LAN2 nodes are never activated — they remain SECONDARY throughout.

This cross-talk is consistent with the use-validation runs (t08 control and rebind also had 5 LAN2 nodes). It is not a threshold-specific effect.

---

## Activation Boundary

The sweep combined with prior evidence maps the activation boundary:

```
t20 (0.20):   waiting-only
t15 (0.15):   activates (late, cycles)
t12 (0.12):   activates (late, cycles)
t10 (0.10):   activates (earlier, cycles more)
t08 (0.08):   activates (earliest, cycles most)
```

The boundary for any activation lies between 0.15 and 0.20. The boundary for in-probe activation lies between 0.10 and 0.12. However, **no threshold produces a single stable activation** — all activating thresholds cycle.

---

## Why Does Every Activating Threshold Cycle?

The cycling mechanism is independent of the base threshold value:

1. **Activation** triggers the adaptive threshold increment (`base + 0.10`). The effective threshold jumps to `base + 0.10` (e.g., 0.25 at t15, 0.22 at t12, 0.20 at t10).
2. **Scale-down cooldown** (120s) starts at activation. After it expires, scale-down evaluates the activated node.
3. **Scale-down removes** the activated reserve (the demand_drop phase has low load → low degradation score → scale-down fires).
4. **Removal drops** the dynamic node count → effective threshold drops back to base.
5. **Load still present** (or residual) → triggers re-activation → cycle repeats.

The cycle is structural: it depends on scale-down removing the activated node faster than the workload can stabilize. The 120s cooldown is shorter than the 180s demand_drop phase, so there's always time for at least one removal + re-activation cycle.

---

## Follow-On Recommendations

1. **Extend scale-down cooldown** (`SCALEDOWN_STORAGE_COOLDOWN_S`): increasing from 120s to 300s would prevent removal within a single demand_drop phase, likely breaking the cycle.
2. **Increase scale-down window size** (`SCALE_DOWN_STORAGE_WINDOW_SIZE` and `SCALE_DOWN_STORAGE_REQUIRED`): requiring more healthy windows before removal would make scale-down less trigger-happy.
3. **Tune the threshold increment** (`SCALEUP_STORAGE_THRESHOLD_INCREMENT`): reducing from 0.10 to 0.05 would make the post-activation effective threshold lower, but this alone won't stop cycling — it just shifts when it happens.
4. **Separate workload tuning** (`storage_reserve_load_sweep`): characterize whether a lighter or differently-shaped probe workload can produce stable activation at a given threshold.
5. **Investigate the LAN1 collapse pattern** seen in the rebind run of the use-validation experiment — normal VIP_DATA path may have routing consistency issues that compound during cycling.

---

## Generated Analysis Artifacts

- `analysis/simple_run.png` — per-run latency, failure, and node count plots (in each run folder)
- `threshold_sweep_compare/simple_compare_overall.png` — cross-run latency and node comparison
- `threshold_sweep_compare/simple_compare_phase.png` — per-phase cross-run comparison
