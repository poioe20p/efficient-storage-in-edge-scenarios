# Elasticity Ablation Results - Batch 1

## Purpose

This document records the first completed five-run comparison batch for the
elasticity ablation matrix:

- `C0` no-scale control
- `C1` Tier 1 only
- `C2` Tier 2 only
- `C3` Tier 1 + Tier 2
- `C4` full current policy

It complements
[`../archive/other/elasticity_ablation_matrix_plan.md`](../archive/other/elasticity_ablation_matrix_plan.md)
by capturing what the batch actually showed. If a later rerun is produced,
keep this document as the stable Batch 1 reference and compare the rerun as a
new batch instead of rewriting the current conclusions in place.

---

## Batch Definition

| Config | Run ID | Controller knobs | Per-run summary |
| --- | --- | --- | --- |
| `C0` | `20260501_114427_c0` | `SS_ENABLED=0`, `MAX_DYNAMIC_STORAGE=0`, `MAX_DYNAMIC_COMPUTE=0` | [`run_summary.md`](../../../source/scripts/testing/metrics/20260501_114427_c0/run_summary.md) |
| `C1` | `20260501_120501_c1` | `SS_ENABLED=1`, `MAX_DYNAMIC_STORAGE=0`, `MAX_DYNAMIC_COMPUTE=0` | [`run_summary.md`](../../../source/scripts/testing/metrics/20260501_120501_c1/run_summary.md) |
| `C2` | `20260501_122539_c2` | `SS_ENABLED=0`, `MAX_DYNAMIC_STORAGE=1`, `MAX_DYNAMIC_COMPUTE=0` | [`run_summary.md`](../../../source/scripts/testing/metrics/20260501_122539_c2/run_summary.md) |
| `C3` | `20260501_124239_c3` | `SS_ENABLED=1`, `MAX_DYNAMIC_STORAGE=1`, `MAX_DYNAMIC_COMPUTE=0` | [`run_summary.md`](../../../source/scripts/testing/metrics/20260501_124239_c3/run_summary.md) |
| `C4` | `20260501_130119_c4` | `SS_ENABLED=1`, `MAX_DYNAMIC_STORAGE=1`, `MAX_DYNAMIC_COMPUTE=1` | [`run_summary.md`](../../../source/scripts/testing/metrics/20260501_130119_c4/run_summary.md) |

---

## Executive Conclusion

Batch 1 supports four main conclusions.

1. `C0` is a valid no-elasticity control: the system stayed serviceable without
   elasticity, but storage-heavy phases clearly raised latency and failure risk.
2. `C1` is the clearest isolated positive result: Tier 1 selective sync improved
   early storage-heavy behavior relative to `C0` and completed a clean lifecycle
   in both LANs.
3. `C2` shows that Tier 2 storage elasticity is too disruptive as a standalone
   first-response mechanism under the current workload timing: the batch paid
   the replica-set bootstrap cost before receiving the benefit.
4. `C4` is the healthiest elastic run and proves Tier 1 plus Tier 2 can coexist
   cleanly, but compute elasticity remained dormant. `C3` therefore should be
   treated as a defect-heavy outlier, not as clean negative evidence against the
   combined policy.

---

## Cross-Run Comparison

| Config | Tier 1 | Tier 2 | Compute | Run health | Main performance effect | Interpretation |
| --- | --- | --- | --- | --- | --- | --- |
| `C0` | Off | Off | Off | Healthy baseline | Stable service with clear storage-bound tail pressure; `storage_stress` had `21/1353` failures | Correct control reference for the standard workload |
| `C1` | Active | Off | Off | Mostly healthy | Two clean Tier 1 lifecycles; `storage_stress` failures fell to `2/1605`; late `demand_drop` defect remained | Strongest isolated positive signal for Tier 1 |
| `C2` | Off | Active | Off | Harmful early, healthier late | Tier 2 fired during `baseline`; first four phases showed near-timeout p95 values before later recovery | Tier 2 is too slow and disruptive as the only first response |
| `C3` | Active | Active | Off | Invalid / defect-heavy | Healthy until `reverse_hotspot`, then request-path collapse; `server_count=0` conflicted with still-running base edge servers | Diagnostic failure, not clean evidence against combined policy |
| `C4` | Active | Active | Enabled but unused | Best healthy run | Clean Tier 1 and Tier 2 lifecycle; low-hundreds-of-ms latency across the run; no compute alerts | Best positive reference for the current elastic stack |

---

## Run-by-Run Findings

### `C0` - No-scale control

`C0` stayed available with one compute node and one storage node per LAN. It
showed the expected storage-bound latency rise in `storage_stress`,
`cross_region_hotspot`, and `reverse_hotspot`, but it did not exhibit lifecycle
churn or a control-path defect. That makes it the correct baseline for this
matrix.

### `C1` - Tier 1 only

`C1` showed that Tier 1 selective sync can improve the standard workload on its
own. Compared with `C0`, it lowered baseline latency and sharply reduced
`storage_stress` failures, while both selective containers promoted, drained,
and cleaned up successfully. The late `demand_drop` timeout burst remains a real
defect, but the artifacts do not tie it to Tier 1 cleanup.

### `C2` - Tier 2 only

`C2` is the strongest negative signal in the batch. Tier 2 fired during
`baseline`, and the first four phases were dominated by severe latency and
timeout behavior while secondaries were being created and joined. Once the
storage tier stabilized at `storage_count=2`, the run recovered. The problem is
therefore not that Tier 2 can never help, but that the in-band bootstrap cost
arrived in the same window that the user-facing workload needed protection.

### `C3` - Tier 1 plus Tier 2

`C3` is not a valid steady-state comparison point. Both tiers activated, the run
looked healthy until `reverse_hotspot`, then the effective serving path failed.
The most important contradiction is that `resource_stats.csv` reported
`server_count=0` while `container_events.csv` still showed the base edge-server
containers running. Manifest PUT failures and a Tier 1 drain timeout strengthen
the case that this was a combined control/request-path defect, not evidence that
Tier 1 plus Tier 2 is fundamentally unsound.

### `C4` - Full current policy

`C4` is the healthiest elastic reference in Batch 1. Tier 1 and Tier 2 both ran
cleanly, request latency stayed in the low-hundreds of milliseconds, and the
run finished without the control-path defects seen in `C3`. Compute elasticity
never triggered, so this run supports the combined Tier 1 plus Tier 2 path, not
any claim about dynamic compute benefit.

---

## Mechanism-Level Interpretation

### Tier 1 selective sync

Batch 1 supports Tier 1 as the strongest positive mechanism under the standard
workload.

- `C1` improved the early storage-heavy phases relative to `C0`, especially in
  `storage_stress`, where failures fell from `21/1353` to `2/1605`.
- `C1` and `C4` show that the promotion, manifest, drain, and cleanup lifecycle
  can complete cleanly in both LANs.
- `C3` shows that the Tier 1 implementation still has integration risk in the
  combined path, but it does not overturn the positive signal from `C1` and
  `C4`.

The thesis-safe reading is that Tier 1 is the best supported benefit in this
batch.

### Tier 2 storage elasticity

Batch 1 does not support Tier 2 as the only first-response mechanism.

- `C2` shows severe early-phase degradation while the storage path is still
  joining and stabilizing.
- Later recovery in `C2` shows that extra storage capacity can still help after
  readiness is reached.
- `C4` shows that Tier 2 can coexist in a healthy run when the rest of the
  elastic stack is working cleanly.

The right conclusion is not that Tier 2 is useless. The right conclusion is
that the current in-band reactive form is too slow and too disruptive to stand
alone under the standard phase schedule.

### Compute elasticity

Compute elasticity remained unproven.

- No `ComputeAlert` fired in any Batch 1 run.
- No dynamic compute container appeared, including in `C4` where compute was
  enabled.
- The benefit seen in `C4` therefore belongs to a healthy Tier 1 plus Tier 2
  run, not to compute scale-out.

Any future compute claim needs a more compute-heavy workload, lower thresholds,
or both.

### Combined elasticity path

Batch 1 gives one healthy combined reference and one defective combined
reference.

- `C4` shows that Tier 1 plus Tier 2 can coexist and remain healthy.
- `C3` shows that the combined path still has defect risk around manifest
  handling, cleanup, telemetry, or request routing.

That makes `C4` the positive reference and `C3` the diagnostic failure case.
`C3` should not be presented as proof that the combined policy is inherently
bad.

---

## Question-by-Question Interpretation

### Is Tier 1 the main reason the healthier runs stayed stable?

Mostly yes. The clearest comparison is `C0` versus `C1`: Tier 1 improved the
storage-heavy phases without needing Tier 2 or compute elasticity. `C4`
reinforces that reading because Tier 1 remained clean inside the healthiest
elastic run.

### Does Tier 2 help on its own?

Not as a standalone first response under the current timing. `C2` shows that the
user-facing phases can be overwhelmed by bootstrap cost before the new storage
nodes become beneficial.

### Does Tier 2 add value beyond Tier 1?

Possibly, but Batch 1 is not strong enough to make a clean causal claim yet.
`C4` is healthier than `C1`, which is consistent with Tier 2 adding value when
the system remains healthy. But `C3` is too defect-heavy to serve as a clean
intermediate comparison point.

### Does compute elasticity matter under the standard workload?

Batch 1 provides no evidence that it does. The workload never triggered dynamic
compute, so compute elasticity cannot be credited for any observed improvement.

---

## Timing Interpretation

The current phase timing matters for how this batch should be read.

- The aggregator publishes one telemetry summary every `10 s`; see
  [`../system_mechanisms.md`](../system_mechanisms.md).
- Tier 1 promotion uses a `2-of-5` breach window and therefore can often show a
  visible effect within a storage-sensitive phase.
- Tier 2 storage scale-up also uses a `2-of-5` trigger, but it still pays the
  asynchronous replica-set join and `SECONDARY` readiness cost before the new
  node can help.
- Compute scale-up uses a `3-of-5` trigger, but Batch 1 suggests that the lack
  of compute scale-out is mostly a signal-strength problem, not only a timing
  problem.

The current `phases_snapshot.json` uses `45-120 s` phases, with the
storage-sensitive hotspot phases lasting `75 s`. That is long enough for Tier 1
to show value, but it is a poor fit for evaluating Tier 2 as a same-phase
reactive mechanism. The older traffic-generator design planned much longer
`300-600 s` phases, which is more compatible with storage bootstrap and steady
state observation.

---

## What Batch 1 Supports

- Tier 1 selective sync improves the standard workload and is the strongest
  positive signal in the batch.
- Tier 2 should not be used as the sole first-response mechanism under the
  current workload timing and bootstrap path.
- Tier 1 plus Tier 2 can work together in a healthy run.
- Compute elasticity is not demonstrated under the standard nine-phase workload.
- `C3` exposed a real integration defect that deserves separate debugging.

## What Batch 1 Does Not Support

- A claim that compute elasticity improved performance in this batch.
- A claim that Tier 2 is inherently harmful in every context.
- A claim that Tier 1 plus Tier 2 is inherently unstable.
- A direct quantitative claim about change-stream overhead on the owner primary.
- A direct claim about warm-volume, snapshot-backed, or dormant Tier 2
  improvements, because those variants were not implemented in Batch 1.

---

## Recommended Next Steps

1. Preserve this document as the Batch 1 reference and compare any rerun as a
   new batch instead of replacing these conclusions.
2. If rerunning `C0-C4`, keep the same controller semantics but lengthen the
   storage-sensitive phases first, especially `storage_stress`,
   `cross_region_hotspot`, and `reverse_hotspot`.
3. Treat Tier 2 follow-up as either a longer-phase experiment or a pre-warmed
   variant study (snapshot-backed, dormant, or similar), not as another
   short-phase Tier 2-only run.
4. Investigate the `C3` control/request-path defect before using it as evidence
   in an architecture-level argument.
5. If compute elasticity still matters to the thesis, design a separate
  compute-heavier batch or retune the compute trigger thresholds.
