# Elasticity Ablation Batch 4 Plan

## Purpose

Batch 4 is the post-fix follow-up to the Batch 3 comparison in
[`elasticity_ablation_batch3_results.md`](./elasticity_ablation_batch3_results.md).
Its purpose is to remove the Tier 1 selective-sync bring-up defect as a batch
confounder, keep compute elasticity disabled, and then test whether a higher
Tier 2 storage ceiling improves the stressed phases under the existing
long-cycle workload.

The batch therefore answers three questions in order:

1. Does Tier 1 promote and attach cleanly again?
2. Does raising `MAX_DYNAMIC_STORAGE` from the Batch 3 ablation value of `1`
   to `4` materially improve the hotspot phases?
3. Does the documented storage ceiling of `5` improve outcomes further, or
   mainly add more replica churn?

---

## Tier 1 Root Cause

Retained controller logs from
[`20260503_174814_cloud_snapshot_env`](../../../source/scripts/testing/metrics/20260503_174814_cloud_snapshot_env/)
show the failing attach boundary directly:

- the controller launches `add_selective_network_node.sh` through `/bin/bash`
- the Tier 1 wrapper then tries to `exec` the shared
  `add_network_node.sh` directly
- the target script is readable inside `/workspace`, but not executable in the
  affected run environment
- the wrapper therefore fails with `Permission denied` before the shared attach
  logic even runs

This differs from the working Tier 2 storage path, which already invokes the
same shared script through `/bin/bash` and therefore does not depend on the
target file's execute bit.

The fix is in
[`source/scripts/network/add_selective_network_node.sh`](../../../source/scripts/network/add_selective_network_node.sh):
the wrapper now delegates through `/bin/bash` instead of directly executing the
shared script.

### Deployment Note

The controller containers mount the repository into `/workspace` via
[`build_network_setup.sh`](../../../source/scripts/build_network_setup.sh), and
`NODE_SCRIPTS_DIR` already points at `/workspace/scripts/network`. That means
this shell-script fix is picked up by the next environment rebuild and does not
require rebuilding the OS-Ken image.

---

## Batch 4 Scope

- Keep the standard workload shape unchanged relative to the current long-cycle
  comparison workflow.
- Keep the WAN profile fixed for the whole batch.
- Keep `MAX_DYNAMIC_COMPUTE=0` for every Batch 4 run.
- Treat Tier 1 repair as a prerequisite, not as one more ablation knob.

Compute remains out of scope for Batch 4 because the current workload still
does not show evidence that compute elasticity is needed for the success path.

---

## Batch 4 Matrix

| Config ID | `SS_ENABLED` | `MAX_DYNAMIC_STORAGE` | `MAX_DYNAMIC_COMPUTE` | Purpose |
| --- | ---: | ---: | ---: | --- |
| `B4-C0` | `0` | `0` | `0` | Fresh no-scale control after the Tier 1 fix |
| `B4-C1` | `1` | `0` | `0` | Validate Tier 1 alone |
| `B4-C2s4` | `0` | `4` | `0` | Storage-only run at practical headroom |
| `B4-C3s4` | `1` | `4` | `0` | Main combined-policy candidate |
| `B4-C3s5` | `1` | `5` | `0` | Combined-policy ceiling check |

### Why `4` and `5`

Batch 3 used `MAX_DYNAMIC_STORAGE=1` as an ablation setting, not as the design
limit. The current controller and documentation already define the intended
Tier 2 ceiling as `5` dynamic storage nodes per LAN in
[`scaling_config.py`](../../../source/sdn_controller/scaling_config.py) and
[`elasticity_overview.md`](../elasticy_manager/elasticity_overview.md).

`4` is the main practical operating point for Batch 4 because it increases
storage headroom substantially without immediately pushing the Tier 2 path to
its documented ceiling. `5` is the follow-up ceiling check.

---

## Execution Sequence

### 1. Validate Tier 1 bring-up in isolation

Before the full batch starts, run a narrow Tier 1-only validation equivalent to
`B4-C1` and confirm:

1. `SelectiveSyncAlert` is submitted.
2. `node_add` completes with `state=DONE` for the `sel_sync_*` node.
3. The coordinator transitions to `ACTIVE`.
4. The manifest is broadcast to the consumer LAN.
5. For collectors that include the observability fix, `tier1_lifecycle_active_count` becomes `1` in `resource_stats.csv`; for legacy Batch 4 artifacts collected before that fix, use `coord_state_owner_lan=ACTIVE` instead because `tier1_reporting_count` is only supply-side telemetry and may stay `0` in quiet windows.
6. Drain and cleanup complete without residual selective containers.

Do not start the rest of Batch 4 until this validation passes.

### 2. Run the Batch 4 matrix

For each configuration:

1. Update
   [`source/scripts/osken-controller.env`](../../../source/scripts/osken-controller.env)
   with the Batch 4 knobs.
2. Rebuild the environment with
   [`build_network_setup.sh`](../../../source/scripts/build_network_setup.sh).
3. Launch the standard experiment with
   [`run_experiment.sh`](../../../source/scripts/testing/run_experiment.sh).
4. Preserve controller logs until the run analysis is complete.

### 3. Analyze each run with the existing toolchain

Use the same metrics workflow that was used for Batch 3:

- [`metrics_stats.py`](../../../source/scripts/tools/metrics_stats.py)
- [`cli_overview.py`](../../../source/scripts/testing/analysis/cli_overview.py)
- [`cli_scale_down.py`](../../../source/scripts/testing/analysis/cli_scale_down.py)
- [`cli_cpu_drivers.py`](../../../source/scripts/testing/analysis/cli_cpu_drivers.py)
- [`cli_tdb_drivers.py`](../../../source/scripts/testing/analysis/cli_tdb_drivers.py)

As in Batch 3, the final interpretation must be based on both metrics outputs
and raw controller-log evidence rather than on `container_events.csv` alone.

---

## Validation Criteria

### Tier 1 repair criteria

The Tier 1 fix is considered valid only if the old failure signature disappears:

- no `Permission denied` on `add_network_node.sh`
- no immediate `node_add ... state=FAILED` caused by the wrapper boundary
- at least one selective node reaches a stable active state

### Batch-level criteria

Batch 4 should answer the following comparisons:

1. `B4-C1` versus `B4-C0`
   Does a functioning Tier 1 path reduce cross-region failures or latency?
2. `B4-C2s4` versus `B4-C0`
   Does higher Tier 2 headroom alone improve hotspot behavior?
3. `B4-C3s4` versus `B4-C1`
   Does Tier 2 add value once Tier 1 is actually working?
4. `B4-C3s5` versus `B4-C3s4`
   Does pushing to the documented ceiling improve service quality or mainly add
   lifecycle churn?

---

## Expected Outcomes

The main expected outcome is that Batch 4 becomes interpretable in a way Batch
3 was not.

- If `B4-C1` stays weak even after the bring-up fix, then Tier 1 is not useful
  enough under the current workload and should not be credited for previous
  healthy runs.
- If `B4-C2s4` clearly improves the hotspot phases over `B4-C0`, then Batch 3's
  remaining pain was at least partly a storage-headroom issue rather than just
  a Tier 1 confounder.
- If `B4-C3s4` becomes the best balanced run, then the intended combined policy
  starts to make sense once Tier 1 is actually alive.
- If `B4-C3s5` adds churn without improving outcomes over `B4-C3s4`, then the
  practical recommendation should remain below the architectural ceiling.

---

## Output Artifacts

Batch 4 should produce:

1. One run folder per Batch 4 configuration under
   [`source/scripts/testing/metrics/`](../../../source/scripts/testing/metrics/).
2. A per-run `run_summary.md` in each folder.
3. A batch synthesis document at
   [`elasticity_ablation_batch4_results.md`](./elasticity_ablation_batch4_results.md).
