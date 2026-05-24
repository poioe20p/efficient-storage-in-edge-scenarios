# Elasticity Ablation Results - Batch 5

## Purpose

This document records the Batch 5 normal-workload cloud campaign from
[`elasticity_ablation_batch5_plan.md`](../archive/testing/elasticity_ablation_batch5_plan.md).
The batch reused the unchanged standard workload and compared four rows:
static, storage-only, storage plus Tier 1, and the full policy with compute cap
`2`.

The comparison artifacts are in
[`batch5_normal_compare`](../../../source/scripts/testing/metrics/batch5_normal_compare/summary.md).

## Batch Definition

| Config | Run ID | Controller knobs | Per-run summary |
| --- | --- | --- | --- |
| Static | `20260510_123544_batch5_normal_static` | `SS_ENABLED=0`, `MAX_DYNAMIC_STORAGE=0`, `MAX_DYNAMIC_COMPUTE=0` | [`run_summary.md`](../../../source/scripts/testing/metrics/20260510_123544_batch5_normal_static/run_summary.md) |
| Storage-only | `20260510_133219_batch5_normal_storage` | `SS_ENABLED=0`, `MAX_DYNAMIC_STORAGE=5`, `MAX_DYNAMIC_COMPUTE=0` | [`run_summary.md`](../../../source/scripts/testing/metrics/20260510_133219_batch5_normal_storage/run_summary.md) |
| Combined | `20260510_150147_batch5_normal_combined` | `SS_ENABLED=1`, `MAX_DYNAMIC_STORAGE=5`, `MAX_DYNAMIC_COMPUTE=0` | [`run_summary.md`](../../../source/scripts/testing/metrics/20260510_150147_batch5_normal_combined/run_summary.md) |
| Full C2 | `20260510_153808_batch5_normal_full_c2` | `SS_ENABLED=1`, `MAX_DYNAMIC_STORAGE=5`, `MAX_DYNAMIC_COMPUTE=2` | [`run_summary.md`](../../../source/scripts/testing/metrics/20260510_153808_batch5_normal_full_c2/run_summary.md) |

Excluded partial attempt: `20260510_142547_batch5_normal_combined` is retained
locally as transport-failure and Tier 1 reconfigure evidence, but is excluded
from the primary ranking. Its summary is at
[`run_summary.md`](../../../source/scripts/testing/metrics/20260510_142547_batch5_normal_combined/run_summary.md).

## Executive Conclusion

Batch 5 does not show a net service-quality improvement from the staged
elasticity mechanisms under the unchanged normal workload.

1. Static was the least bad completed row by both failure rate and p95 latency,
   despite a serious caveat: `edge_server_n1` exited `139` during
   `reverse_hotspot`.
2. Storage-only confirmed that Tier 2 can activate aggressively with cap `5`,
   reaching `storage_count=6`, but it worsened failures and latency versus
   static and left cleanup debt.
3. Combined mode confirmed Tier 1 can now reach `ACTIVE` in controller logs,
   unlike earlier broken bring-up evidence, but `tier1_active_count` stayed at
   `0.0`, reconfigure noise persisted, and p95 latency was the worst completed
   row.
4. Full C2 did not exercise compute elasticity. `ComputeAlert=0`, no compute
   dynamic containers appeared, and `server_count` stayed at `1.0` throughout.
5. The partial combined attempt reproduced transport/control cleanup risk and is
   useful evidence, but not a completed matrix result.

## Quantitative Anchors

| Config | Requests | Failures | Fail Rate | p95 Latency | Max Storage | Final Storage | Compute Alerts | Tier 1 Active Log Markers | Final Dynamic |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Static | 38,153 | 6,020 | 15.78% | 313.6 ms | 1.0 | 1.0 | 0 | 0 | 0 |
| Storage-only | 42,722 | 9,722 | 22.76% | 378.2 ms | 6.0 | 2.0 | 0 | 0 | 4 |
| Combined | 41,861 | 8,429 | 20.14% | 410.2 ms | 6.0 | 5.0 | 0 | 4 | 6 |
| Full C2 | 42,088 | 9,004 | 21.39% | 400.0 ms | 3.0 | 1.0 | 0 | 4 | 2 |

## Run-by-Run Findings

### Static

The static row stayed inert as intended: no `DataAlert`, `ComputeAlert`,
`SelectiveSyncAlert`, or dynamic container events appeared. It remains the
primary Batch 5 control, but not a pristine one. The `edge_server_n1` exit `139`
during `reverse_hotspot` likely inflated late LAN1 failures.

### Storage-only

Storage-only validated Tier 2 activation, with 11 storage spawns and a maximum
`storage_count` of `6.0`. It did not improve service quality: failures rose to
22.76% and p95 rose to 378.2 ms. Cleanup remained incomplete, with four dynamic
storage containers still running at final collection.

### Combined

Combined mode is the most important mechanism result in Batch 5. Tier 1 reached
`ACTIVE` in logs on both LANs, so the path progressed beyond the earlier
network-attach failure pattern. However, `tier1_active_count` remained `0.0` in
resource telemetry and selective-sync reconfigure failures continued. Compared
with storage-only, combined mode reduced failures from 22.76% to 20.14%, but p95
rose from 378.2 ms to 410.2 ms and cleanup debt increased.

### Full C2

Full C2 confirms that the normal workload still does not naturally trigger
compute elasticity, even with `MAX_DYNAMIC_COMPUTE=2`. The row is therefore not
evidence for compute scaling benefit. Its lower maximum storage count and lower
final cleanup debt are useful, but the service result remains worse than static.

## Batch 4 Comparison

Batch 5 improves one important mechanism detail relative to the Batch 4 context:
Tier 1 can now reach `ACTIVE` in logs. That is materially better than the older
attach-failure symptom.

However, Batch 5 does not reproduce the stronger service-quality story from the
best Batch 4 storage-enabled combined reference. The completed Batch 5 elastic
rows all remained worse than the Batch 5 static control on failure rate and p95.
Tier 2 cleanup debt also persisted, and Tier 1 telemetry still disagreed with
lifecycle logs.

## Mechanism-Level Interpretation

### Tier 2 Storage

Tier 2 is active, but not a net win in this batch. It responds repeatedly and can
reach the higher cap, yet the extra churn correlates with worse failure and
latency behavior under this normal workload. Cleanup convergence remains a core
issue.

### Tier 1 Selective Sync

Tier 1 is no longer simply failing to attach. It reaches `ACTIVE` in the
completed combined and full rows. The mechanism is still too noisy for a clean
positive claim because telemetry reports `tier1_active_count=0.0`, reconfigure
failures continue after activation, and the combined rows do not beat static.

### Compute Elasticity

Compute elasticity remains unproven. The cap `2` row produced no `ComputeAlert`,
no compute dynamic containers, and no increase in `server_count`. A separate
compute-heavy workload is still required if the thesis needs compute elasticity
evidence.

## Artifact And Retention Status

All completed Batch 5 rows were summarized on a user-owned VM snapshot, trimmed,
copied back locally, and verified. The original cloud run folders are retained
because direct non-interactive cleanup of root-owned metrics folders is blocked.

The remote comparison folder also had to be generated under `/tmp` and copied
back locally because the remote metrics directory is not user-writable outside
the whitelisted experiment path.

## Recommended Next Steps

1. Treat Batch 5 static as the local control, but explicitly cite the
   `edge_server_n1` crash caveat.
2. Do not claim a Batch 5 service-quality win for storage, combined, or full C2
   under the unchanged normal workload.
3. Investigate Tier 1 telemetry publication and selective-sync reconfigure
   failures before using Tier 1 as positive production evidence.
4. Investigate Tier 2 cleanup convergence and final dynamic storage debt.
5. Use a separate compute-heavy campaign if compute elasticity evidence is
   required.