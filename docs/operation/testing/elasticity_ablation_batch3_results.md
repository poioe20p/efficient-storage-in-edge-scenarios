# Elasticity Ablation Results - Batch 3

## Purpose

This document records the third completed `C0-C4` comparison batch. Unlike the
earlier batches, every launch in Batch 3 ran entirely on `cloud-vm`, so the
batch removes mixed execution location as a confounder and asks whether the
Batch 2 mechanism ordering still holds under a fully remote workflow.

It keeps
[`elasticity_ablation_batch2_results.md`](./elasticity_ablation_batch2_results.md)
as the direct long-cycle reference and captures what changed once the entire
batch was executed on the cloud host from start to finish.

---

## Batch Definition

| Config | Run ID | Controller knobs | Per-run summary |
| --- | --- | --- | --- |
| `C0` | `20260503_185809_batch3_c0` | `SS_ENABLED=0`, `MAX_DYNAMIC_STORAGE=0`, `MAX_DYNAMIC_COMPUTE=0` | [`run_summary.md`](../../../source/scripts/testing/metrics/20260503_185809_batch3_c0/run_summary.md) |
| `C1` | `20260503_192822_batch3_c1` | `SS_ENABLED=1`, `MAX_DYNAMIC_STORAGE=0`, `MAX_DYNAMIC_COMPUTE=0` | [`run_summary.md`](../../../source/scripts/testing/metrics/20260503_192822_batch3_c1/run_summary.md) |
| `C2` | `20260503_195831_batch3_c2` | `SS_ENABLED=0`, `MAX_DYNAMIC_STORAGE=1`, `MAX_DYNAMIC_COMPUTE=0` | [`run_summary.md`](../../../source/scripts/testing/metrics/20260503_195831_batch3_c2/run_summary.md) |
| `C3` | `20260503_202818_batch3_c3` | `SS_ENABLED=1`, `MAX_DYNAMIC_STORAGE=1`, `MAX_DYNAMIC_COMPUTE=0` | [`run_summary.md`](../../../source/scripts/testing/metrics/20260503_202818_batch3_c3/run_summary.md) |
| `C4` | `20260503_205814_batch3_c4` | `SS_ENABLED=1`, `MAX_DYNAMIC_STORAGE=1`, `MAX_DYNAMIC_COMPUTE=1` | [`run_summary.md`](../../../source/scripts/testing/metrics/20260503_205814_batch3_c4/run_summary.md) |

---

## Executive Conclusion

Batch 3 supports the same main reading as Batch 2, even after moving the entire
workflow onto `cloud-vm`.

1. `C2` remains the cleanest comparable elastic reference. Tier 2 still scales
   out, still avoids compute churn, and still beats the no-scale, Tier 1-only,
   and combined-path runs on the balance of failures versus request volume.
2. Tier 1 is still not a positive mechanism, and the controller logs show why.
   In `C1`, `C3`, and `C4`, promotions fire, but every logged `sel_sync_*`
   bring-up ends with `add_selective_network_node.sh` failing during network
   attach and `node_add ... state=FAILED`.
3. The combined Tier 1 plus Tier 2 path remains unstable. `C3` again acts as a
   failure case rather than a positive integrated reference, and Batch 3 shows
   that the integrated policy is being evaluated with a broken Tier 1 path.
4. `C4` looks better on raw fail rate, but not on a clean like-for-like basis.
   It completes far fewer requests than the other runs, records `108`
   zero-`server_count` windows, still never triggers compute elasticity, and
   does not have a working Tier 1 path.
5. Compute elasticity remains unproven. No `ComputeAlert` fired and no dynamic
   compute container appeared in any run.

---

## Cross-Run Comparison

| Config | Tier 1 | Tier 2 | Compute | Run health | Main performance effect | Interpretation |
| --- | --- | --- | --- | --- | --- | --- |
| `C0` | Off | Off | Off | Mixed | Full-volume no-scale run still collapses in `cross_region_hotspot`, `reverse_hotspot`, and `sustained_plateau` | Baseline reference only |
| `C1` | Promotion fires, spawn fails | Off | Off | Mixed / defect-prone | `reverse_hotspot` becomes worse than `C0`, and every logged selective spawn fails during network attach | Tier 1 trigger works; Tier 1 service does not |
| `C2` | Off | Active | Off | Mixed but cleanest elastic | Tier 2 scales storage up to `4.0` and beats `C0`, `C1`, and `C3` without `C4`'s severe request-volume collapse | Best comparable elastic reference |
| `C3` | Promotion fires, spawn fails | Active | Off | Defect-prone | Tier 2 scales, but Tier 1 bring-up fails and hotspot and plateau failures remain worst among the elastic runs | Combined path still unstable |
| `C4` | Promotion fires, spawn fails | Active | Enabled but unused | Mixed / throughput-suppressed | Lowest raw fail rate, but only `30,907` completed requests, `108` zero-server windows, broken Tier 1 bring-up, and `demand_drop` `p95≈10 s` | Not a clean positive reference |

### Quantitative Anchors

| Config | Total requests | Failures | Fail rate | Notable volume caveat |
| --- | ---: | ---: | ---: | --- |
| `C0` | `41,588` | `9,347` | `22.48%` | Full-volume control |
| `C1` | `41,288` | `8,776` | `21.26%` | Similar request volume to `C0`, but broken Tier 1 bring-up |
| `C2` | `37,275` | `7,475` | `20.05%` | Lower volume than `C0`/`C1`, but still the cleanest comparable elastic run |
| `C3` | `40,520` | `9,370` | `23.12%` | Near-control request volume with the worst elastic-run fail rate |
| `C4` | `30,907` | `2,513` | `8.13%` | Lowest raw fail rate, but also the largest request-volume collapse |

---

## Key Changes Relative to Batch 2

### Cloud-only execution confirms, rather than overturns, the Batch 2 ordering

Batch 2 already pointed to `C2` as the cleanest elastic reference and to the
combined path as an integration risk. Batch 3 keeps that same ordering even
though every run was launched entirely on `cloud-vm`.

### Batch 3 replaces the Batch 2 manifest symptom with a more direct Tier 1 bring-up failure

The Batch 2 rerun batch was notable for `manifest` timeout signatures in
Tier 1-enabled runs. Batch 3 does not reproduce that specific controller-log
symptom, but it does reveal a different defect: promotions fire and the
controller tries to spawn `sel_sync_*` containers, yet every logged selective
bring-up attempt ends with `add_selective_network_node.sh` failing and the
final `node_add` timing marked `state=FAILED`. The hotspot windows therefore do
not reflect a working Tier 1 path, and `tier1_active_count=0` is consistent
with the logs rather than just with missing telemetry.

### `C4` improves on raw failure rate, but not on clean comparability

Batch 3's full-policy run is much less failure-heavy than `C3` and much less
failure-heavy on raw rate than the other runs, especially in `reverse_hotspot`.
But it also completes far fewer total requests than the rest of the batch and
shows the worst zero-`server_count` telemetry distortion by far. That keeps it
from displacing `C2` as the clean reference.

### Compute elasticity is still dormant

This does not change. `MAX_DYNAMIC_COMPUTE=1` still produces no
`ComputeAlert` and no dynamic compute container under the current nine-phase
workload.

---

## Run-by-Run Findings

### `C0` - No-scale control

`C0` is still the correct no-elasticity baseline. It stays clean in
`baseline`, then degrades through the hotspot and late compute phases, with the
worst failure counts in `reverse_hotspot`, `cross_region_hotspot`, and
`sustained_plateau`. Because no dynamic container ever appears, its zero-count
windows in `resource_stats.csv` should be read as a telemetry or serving-path
defect rather than literal scale activity.

### `C1` - Tier 1 only

`C1` does not prove a healthy Tier 1 lifecycle under the remote workflow.
Promotion logic fires repeatedly, but every logged selective node bring-up ends
with network attach failure and `state=FAILED`. The run is slightly cleaner than
`C0` in some compute phases, but `reverse_hotspot` becomes worse and the
overall fail rate remains close to the control.

### `C2` - Tier 2 only

`C2` is again the cleanest elastic reference. Storage elasticity adds dynamic
storage containers throughout the stressed portion of the schedule, `storage_count`
reaches `4.0`, and the run posts the best balance of failure rate versus request
volume among the elastic configurations. It is still not pristine because both
hotspot phases remain expensive and two scale-down removals fail in the logs,
but it is the least confounded positive result.

### `C3` - Tier 1 plus Tier 2

`C3` remains the combined-path failure case. Tier 2 activates, but the Tier 1
path does not complete a successful bring-up, and `cross_region_hotspot`,
`reverse_hotspot`, and `sustained_plateau` still absorb the worst failure load
among the elastic runs. The integrated path remains the main architecture-level
risk area.

### `C4` - Full current policy

`C4` is mixed. It is clearly better than `C3` on raw failure rate and notably
better than the rest of the batch in `reverse_hotspot`, but it completes only
`30,907` total requests, never uses compute elasticity, and records `108`
zero-`server_count` windows. The very low `demand_drop` volume, `p95≈10 s`, and
failed Tier 1 bring-up attempts make it too confounded to treat as the best
overall reference.

---

## Mechanism-Level Interpretation

### Tier 1 selective sync

Batch 3 does not support Tier 1 as a working mechanism yet.

- Promotions fire in `C1`, `C3`, and `C4`, and `container_events.csv` records
   short-lived `sel_sync_*` activity.
- Every logged selective `node_add` timing in those runs ends `state=FAILED`
   after `add_selective_network_node.sh` fails during attach.
- `tier1_active_count` remains `0` in every run, and Batch 3 log evidence is
   consistent with that because no selective node reaches a stable active state.

### Tier 2 storage elasticity

Batch 3 again supports Tier 2 as the cleanest positive mechanism under the
current workload.

- `C2` scales storage to `4.0` and remains the best comparable elastic run.
- `C3` and `C4` also scale storage, but the integrated path adds other defects.
- Storage scale-down cleanup is not perfect, but it completes often enough to
   leave Tier 2 as the only elastic mechanism that repeatedly works end to end.
- The cloud-only rerun therefore strengthens, rather than weakens, the Batch 2
  Tier 2 conclusion.

### Compute elasticity

Compute elasticity remains unproven.

- No `ComputeAlert` fired.
- No dynamic compute container appeared.
- `MAX_DYNAMIC_COMPUTE=1` still changes nothing measurable in Batch 3.

### Combined elasticity path

Batch 3 still does not support a clean positive claim for the combined policy.

- `C3` remains outright failure-prone.
- `C4` is more recoverable than `C3`, but still too confounded by throughput
   suppression, telemetry collapse, and broken Tier 1 bring-up to be the main
   positive reference.
- The combined policy is therefore being evaluated with one working elastic
   subsystem and one failing one.

---

## Control-Plane Caveat

The zero-count caveat persists in Batch 3. `resource_stats.csv` still reports
zero `server_count` or `storage_count` windows in runs where the base containers
remain present in `container_events.csv`. This caveat is most severe in `C4`,
which reports `108` zero-`server_count` windows and also completes far fewer
requests than the other runs. These windows should be read as serving-path,
collector, or control-plane disappearance rather than literal base-container
loss.

---

## What Batch 3 Supports

- Running the full matrix entirely on `cloud-vm` does not overturn the Batch 2
  mechanism ordering.
- `C2` remains the cleanest comparable elastic reference for the current
  long-cycle workload.
- Tier 1 promotion logic still fires under the cloud-only workflow.
- The combined Tier 1 plus Tier 2 path still carries real integration risk.
- Compute elasticity is still dormant under the current workload.

## What Batch 3 Does Not Support

- A claim that mixed execution location was the main reason Batch 2 favored
  `C2`.
- A claim that Tier 1 selective sync now works cleanly under the cloud-only
   workflow.
- A claim that the full `C4` policy is now the best clean overall configuration.
- Any claim that compute elasticity improved performance in this batch.
- A literal reading that zero-count windows in `resource_stats.csv` mean the
  base compute or storage containers actually disappeared.

---

## Recommended Next Steps

1. Use `C2` as the Batch 3 positive reference when the argument needs a
   cloud-only elastic run.
2. Debug the selective network-attach failure in `add_selective_network_node.sh`
   before using `C1`, `C3`, or `C4` as Tier 1 evidence.
3. Re-evaluate why `C4` reduces raw failures while also losing request volume,
   reporting `108` zero-`server_count` windows, and never triggering compute.
4. If compute elasticity matters to the thesis, build a separate compute-heavy
   batch instead of relying on the current workload.
