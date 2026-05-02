# Elasticity Ablation Results - Batch 2

## Purpose

This document records the second completed `C0-C4` comparison batch, produced
after the workload was extended to the long-cycle nine-phase schedule. It keeps
[`elasticity_ablation_batch1_results.md`](./elasticity_ablation_batch1_results.md)
as the stable short-phase reference and captures what changed once Tier 2 had
time to bootstrap and the rerun batch exposed longer-lived control-path
defects.

---

## Batch Definition

| Config | Run ID | Controller knobs | Per-run summary |
| --- | --- | --- | --- |
| `C0` | `20260501_212305_c0` | `SS_ENABLED=0`, `MAX_DYNAMIC_STORAGE=0`, `MAX_DYNAMIC_COMPUTE=0` | [`run_summary.md`](../../../source/scripts/testing/metrics/20260501_212305_c0/run_summary.md) |
| `C1` | `20260501_221039_c1` | `SS_ENABLED=1`, `MAX_DYNAMIC_STORAGE=0`, `MAX_DYNAMIC_COMPUTE=0` | [`run_summary.md`](../../../source/scripts/testing/metrics/20260501_221039_c1/run_summary.md) |
| `C2` | `20260501_225337_c2` | `SS_ENABLED=0`, `MAX_DYNAMIC_STORAGE=1`, `MAX_DYNAMIC_COMPUTE=0` | [`run_summary.md`](../../../source/scripts/testing/metrics/20260501_225337_c2/run_summary.md) |
| `C3` | `20260501_234659_c3` | `SS_ENABLED=1`, `MAX_DYNAMIC_STORAGE=1`, `MAX_DYNAMIC_COMPUTE=0` | [`run_summary.md`](../../../source/scripts/testing/metrics/20260501_234659_c3/run_summary.md) |
| `C4` | `20260502_001954_c4` | `SS_ENABLED=1`, `MAX_DYNAMIC_STORAGE=1`, `MAX_DYNAMIC_COMPUTE=1` | [`run_summary.md`](../../../source/scripts/testing/metrics/20260502_001954_c4/run_summary.md) |

---

## Executive Conclusion

Batch 2 changes the mechanism-level reading from Batch 1 in four important ways.

1. `C2` becomes the strongest positive result. Under the long-cycle workload,
   Tier 2 storage elasticity has enough time to come online and stabilize the
   storage-heavy phases.
2. `C1` no longer provides a clean Tier 1 win. Tier 1 still promotes and cleans
   up, but the rerun is dominated by request-path and telemetry defects rather
   than by clear end-to-end benefit.
3. The combined Tier 1 plus Tier 2 path remains unstable. `C3` collapses during
   the hotspot phases, and `C4` suffers severe early instability before later
   recovery.
4. Compute elasticity remains unproven. Even with `MAX_DYNAMIC_COMPUTE=1`, no
   `ComputeAlert` or dynamic compute container appeared.

---

## Cross-Run Comparison

| Config | Tier 1 | Tier 2 | Compute | Run health | Main performance effect | Interpretation |
| --- | --- | --- | --- | --- | --- | --- |
| `C0` | Off | Off | Off | Mixed | Early and mid phases are usable, then `sustained_plateau` degrades and `demand_drop` collapses completely | Partial no-scale reference only; late defect is unrelated to elasticity |
| `C1` | Active | Off | Off | Mixed / defect-heavy | Two Tier 1 lifecycles complete, but failures persist from `storage_stress` through `demand_drop` | Tier 1 lifecycle works, but the rerun does not support a strong Tier 1 benefit claim |
| `C2` | Off | Active | Off | Healthy | Storage scales out in both LANs and keeps failure counts low across all demand phases | Best healthy run in Batch 2; strongest positive signal for the long-cycle workload |
| `C3` | Active | Active | Off | Invalid during hotspot window | Full request collapse in `cross_region_hotspot` and `reverse_hotspot`, then later recovery | Combined path remains defect-prone; use as a failure case, not a positive reference |
| `C4` | Active | Active | Enabled but unused | Mixed | Severe early instability, later recovery, still failure-heavy in `reverse_hotspot` | Full policy still weaker than `C2`; compute remains dormant |

---

## Key Changes Relative to Batch 1

### Tier 2 reverses from weakest standalone mechanism to strongest one

Batch 1 suggested that standalone Tier 2 was too disruptive because the
bootstrap cost landed inside the short workload phases. Batch 2 reverses that
result. With `240-300 s` storage-sensitive phases, `C2` stabilizes the run and
keeps failures low while holding `storage_mean` near `2.0` for most of the
campaign.

### Tier 1 loses its clear positive lead

Batch 1's cleanest isolated benefit came from `C1`. In Batch 2, Tier 1 still
promotes and drains, but the Tier 1 enabled runs (`C1`, `C3`, and `C4`) all
show controller-side manifest timeouts or broader request-path instability. The
rerun batch therefore supports Tier 1 lifecycle viability more than Tier 1
performance benefit.

### `C4` is no longer the best reference run

Batch 1 treated `C4` as the healthiest elastic configuration. In Batch 2,
`C4` recovers after a severe early disturbance, but it is still less clean than
`C2` and still offers no compute elasticity evidence.

### Compute elasticity is still dormant

This did not change between batches. The longer phases were enough to change the
Tier 2 story but still did not trigger any dynamic compute scale-out.

---

## Run-by-Run Findings

### `C0` - No-scale control

`C0` is useful as the no-elasticity reference only for the early and mid phases.
It shows the expected storage-bound latency growth through
`reverse_hotspot`, but the run becomes unreliable in `sustained_plateau` and
fully collapses in `demand_drop`. Because the base containers never disappear in
`container_events.csv`, that late collapse should be treated as a request-path
or telemetry failure, not as a capacity-only result.

### `C1` - Tier 1 only

`C1` proves that Tier 1 can still promote, drain, and clean up, but it does not
prove that Tier 1 alone makes the long-cycle workload healthy. The run shows
persistent failures from `storage_stress` onward, manifest PUT timeouts on both
controllers, and reported `server_mean=0.5` even though the base edge
containers remain alive.

### `C2` - Tier 2 only

`C2` is the clean Batch 2 positive reference. Storage elasticity activates in
both LANs, the storage tier stays expanded through the heavy phases, and all
high-demand phases remain bounded with only low-single-digit failures. This is
the strongest evidence that long phases are required to evaluate Tier 2 fairly.

### `C3` - Tier 1 plus Tier 2

`C3` remains a combined-path failure case. Both tiers activate, but the run
fully collapses through `cross_region_hotspot` and `reverse_hotspot` before
recovering later. The recovery matters because it shows the run is not simply
under-provisioned; instead, something in the combined control or request path
fails specifically in the hotspot interval.

### `C4` - Full current policy

`C4` shows that the full policy can eventually settle into a reasonable late-run
shape, but it still suffers severe early failures and never exercises compute
elasticity. The result is therefore mixed: better than `C3` overall, but not
better than `C2` and still not evidence for compute scale-out.

---

## Mechanism-Level Interpretation

### Tier 1 selective sync

Batch 2 supports Tier 1 as a working lifecycle mechanism, not as the strongest
performance win.

- Tier 1 promotions, drains, and cleanups are all visible in the artifacts.
- Tier 1 enabled runs also show manifest PUT timeouts and broader request-path
  instability.
- The rerun batch therefore does not support a thesis-level claim that Tier 1 is
  the main reason the long-cycle workload stays healthy.

### Tier 2 storage elasticity

Batch 2 supports Tier 2 as the main positive mechanism under the long-cycle
schedule.

- `C2` is the healthiest elastic run.
- The storage tier expands early enough to help the storage-heavy phases.
- This is the exact reversal Batch 1 could not show because the original phases
  were too short.

### Compute elasticity

Compute elasticity remains unproven.

- No `ComputeAlert` fired.
- No dynamic compute container appeared.
- Any late-run benefit in `C4` belongs to Tier 1 plus Tier 2 only.

### Combined elasticity path

Batch 2 still does not support a clean positive claim for the combined policy.

- `C3` fails catastrophically during the hotspot window.
- `C4` is more recoverable, but still unstable in the early phases and still
  worse than `C2`.
- The combined path should therefore be treated as an integration risk area, not
  as a stable reference design.

---

## Control-Plane Caveat

One cross-run caveat matters for reading Batch 2 correctly. In `C0`, `C1`,
`C3`, and `C4`, `resource_stats.csv` sometimes reports reduced or zero
`server_count` and `storage_count` even though `container_events.csv` shows the
base compute and storage containers still running. Those windows should not be
read as literal container loss. They are evidence of a control-plane,
telemetry-plane, or request-path defect that makes the serving path effectively
disappear from the collectors.

---

## What Batch 2 Supports

- Long storage-sensitive phases are necessary if the experiment is meant to
  measure Tier 2 fairly.
- Tier 2 storage elasticity can be the healthiest standalone mechanism once the
  workload gives it time to settle.
- Compute elasticity is still not exercised by the current nine-phase workload.
- The combined Tier 1 plus Tier 2 path still carries real integration risk.

## What Batch 2 Does Not Support

- A strong positive claim for Tier 1 as the main benefit in the long-cycle
  rerun.
- A claim that the full `C4` policy is the best overall configuration.
- Any claim that compute elasticity improved performance in this batch.
- A literal reading that the base compute or storage containers actually died in
  the zero-count windows.

---

## Recommended Next Steps

1. Use `C2` as the Batch 2 positive reference when discussing long-cycle
   storage elasticity.
2. Debug why the serving path can disappear from `resource_stats.csv` while the
   base containers remain alive in `container_events.csv`.
3. Isolate the Tier 1 manifest and request-path defects before using `C1`,
   `C3`, or `C4` as architecture-level evidence.
4. If compute elasticity matters to the thesis, design a separate compute-heavy
   batch instead of relying on the current workload.
