# Tier 1 Activation Smoke Test — Results

**Experiment plan**: [`experiment_plan.md`](./experiment_plan.md)  
**Date**: 2026-06-26  
**Status**: ✅ Gate passed — bidirectional Tier 1 restored

## Run Timeline

| Run | Date | Status | Gate Result | Changes Made |
|-----|------|--------|-------------|--------------|
| v1 | 2026-06-26 11:55 UTC | ✅ Pass | **5/5 criteria** | `topology.py`: `resolve_peer_primary()` two-step resolution |

---

## 1. Run v1 — Results

**Run folder**: `source/scripts/testing/metrics/20260626_115523_tier1_smoke/`

### Criteria Assessment

| # | Criterion | Result | Evidence |
|---|-----------|--------|----------|
| 1 | `sel_sync_lan1_dyn*` ACTIVE | ✅ **PASS** | `sel_sync_lan1_dyn3`: add 12:03:42, ready(ACTIVE) 12:03:52. **First lan2→lan1 activation since 2026-06-09.** |
| 2 | `sel_sync_lan2_dyn*` ACTIVE | ✅ **PASS** | `sel_sync_lan2_dyn2`: add 11:56:38, ready(ACTIVE) 11:56:48, remove 12:00:38. Positive control confirmed. |
| 3 | `no primary known` warnings | ✅ **PASS** | **0** warnings in `controller_lan1.log`. The 16 warnings from pre-fix runs are eliminated. |
| 4 | No tracebacks | ✅ **PASS** | 0 in both `controller_lan1.log` and `controller_lan2.log`. |
| 5 | Run completes | ✅ **PASS** | `idle` — all 5 phases completed. |

### Tier 1 Lifecycle Details

```
Direction: lan1→lan2 (positive control — always worked)
  sel_sync_lan2_dyn2  add 11:56:38  ready(ACTIVE) 11:56:48  remove 12:00:38
                      ↑ activated during hotspot_lan2_to_lan1 phase
                      (lan2 clients accessing lan1 data → lan2 controller
                       spawns sync container to pull lan1 data locally)

Direction: lan2→lan1 (the fix — previously blocked by "no primary known")
  sel_sync_lan1_dyn3  add 12:03:42  ready(ACTIVE) 12:03:52
                      ↑ activated during hotspot_lan1_to_lan2 phase
                      (lan1 clients accessing lan2 data → lan1 controller
                       spawns sync container to pull lan2 data locally)
```

**One-direction-per-phase**: Each 180s hotspot phase activated Tier 1 in exactly
one direction — the direction opposite to the hotspot (lan2→lan1 hotspot triggers
lan1→lan2 Tier 1 sync; lan1→lan2 hotspot triggers lan2→lan1 Tier 1 sync). This
is correct behavior: the controller experiencing the inbound cross-region load
spawns the sync container on its own LAN.

**No `remove` event for `sel_sync_lan1_dyn3`**: The 60s `idle` phase at the end
of the run may not be long enough for the Tier 1 cooldown + scale-down to fire
(180s scale-down cooldown). This is expected — the container was still active at
run end. Not a concern for the gate.

### Mechanism Exercise (secondary)

| Mechanism | Evidence |
|-----------|----------|
| Tier 1 (selective sync) | ✅ Bidirectional: 1 spawn per direction |
| Reserve (Tier 2) | ⚠️ 0 activations — short workload with no storage_stress phase |
| Compute (Tier 3) | ⚠️ Not exercised — workload designed for Tier 1 only |

The absence of reserve and compute activation is **intentional** — the smoke test
workload isolates Tier 1. This is not a defect.

---

## Gate Decision

**✅ PASS — proceed to RQ1 v2-replicate rerun.**

The topology fix restores bidirectional Tier 1 selective-sync activation.
The lan2→lan1 direction, which had been blocked since 2026-06-09 by the
real-MAC/virtual-MAC key mismatch in `resolve_peer_primary()`, now activates
correctly. Zero `no primary known` warnings confirm the fix eliminates the
failed lookup entirely.

### Next Steps

1. **RQ1 v2-replicate rerun** — the variance condition was met (0.15pp ≤ 2pp)
   and the topology fix is now verified. Run 4 additional replicates (one per
   cadence: Push, Poll-5s, Poll-12s, Poll-30s) with the topology fix in place.
   These will serve dual purpose: verify the fix under the full integrated
   workload AND provide the statistical replicates the plan calls for.

2. **Expectation for replicates**: Tier 1 should now activate in BOTH directions
   (not just lan1→lan2) in Push, Poll-5s, and Poll-12s. Poll-30s may still
   suppress Tier 1 entirely due to the blind-spot effect. Reserve activation
   should follow the v2 pattern (6–7 in fast modes, degraded in slow modes).
   Service quality should show the monotonic degradation seen in v2.

### Artifacts

| Artifact | Location |
|----------|----------|
| Run folder | `source/scripts/testing/metrics/20260626_115523_tier1_smoke/` |
| Phases file | `source/scripts/testing/phases_override/phases_tier1_smoke.json` |
| This report | `docs/operation/testing/experiment/tier1_activation_smoke_test/results.md` |
| Experiment plan | [`experiment_plan.md`](./experiment_plan.md) |

---

## Results

⏳ Pending — run not yet executed.
