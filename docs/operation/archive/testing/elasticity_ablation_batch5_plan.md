# Elasticity Ablation Batch 5 Plan

## Purpose

Batch 5 is the normal-workload validation batch for the elasticity changes that
landed after Batch 4. It keeps the standard long-cycle workload in
[`source/scripts/testing/phases.json`](../../../source/scripts/testing/phases.json)
unchanged and asks how the updated storage scale-up path, compute drain
behavior, and full policy behave under the same experiment shape used by the
previous ablation batches.

This batch deliberately avoids a custom compute-heavy workload. Compute
elasticity is enabled only in the final full-policy run with
`MAX_DYNAMIC_COMPUTE=2`; if the normal workload does not naturally trigger
compute scale-up or cancelable drain behavior, that is a valid result rather
than a failed run.

The batch answers four questions:

1. Does the post-change static normal run remain comparable to the Batch 4
   control?
2. Does Tier 2 storage scale-up become faster or cleaner under the normal
   workload when isolated from Tier 1 and compute elasticity?
3. Does Tier 1 still add value or lifecycle noise when combined with the
   updated Tier 2 storage path?
4. Does enabling compute elasticity with a cap of `2` produce any natural
   compute scale-up, scale-down, or drain-cancel evidence under the standard
   workload?

---

## Autonomous Runner Contract

This plan is written for the `#edge_experiment_runner` agent. The agent should
use this file as the run source of truth and update
[`experiment_campaign_brief.md`](./experiment_campaign_brief.md) before the
first launch so the durable campaign context matches Batch 5.

Required execution context:

1. Enter the cloud host with `ssh cloud-vm`.
2. Change to `~/efficient-storage-in-edge-scenarios`.
3. Run experiment commands on the cloud host only, not on the Windows host.
4. Use `sudo -n`; treat an interactive sudo prompt as a configuration failure.
5. If local changes are not present on the cloud host, explicitly copy or sync
   them before launching. Do not assume automatic synchronization.

Allowed between-run edits:

1. On the cloud host, edit only `source/scripts/osken-controller.env` between
   runs to apply the Batch 5 matrix values.
2. Local documentation may be updated after completed runs to record summaries
   and final results.
3. Do not edit `source/scripts/testing/phases.json` for this batch.
4. Do not edit active run artifacts while a run is in progress.
5. Do not make source-code changes during the batch.

Default active-run behavior:

1. After traffic generation starts, use passive monitoring.
2. Perform only read-only checks listed in the live checkpoint plan.
3. Do not send interrupts, cleanup commands, restarts, or container-control
   commands while a run is active unless the stop or restart policy below
   explicitly authorizes it.

---

## Batch 5 Matrix

| Config ID | Run label | `SS_ENABLED` | `MAX_DYNAMIC_STORAGE` | `MAX_DYNAMIC_COMPUTE` | Purpose |
| --- | --- | ---: | ---: | ---: | --- |
| `B5-C0` | `batch5_normal_static` | `0` | `0` | `0` | Standard no-elasticity reference after the staged controller changes |
| `B5-C1` | `batch5_normal_storage` | `0` | `5` | `0` | Isolate the updated Tier 2 storage scale-up path under the normal workload |
| `B5-C2` | `batch5_normal_combined` | `1` | `5` | `0` | Combine Tier 1 selective sync with the updated Tier 2 storage path |
| `B5-C3` | `batch5_normal_full_c2` | `1` | `5` | `2` | Full normal policy with compute elasticity enabled at cap `2` |

### Why compute cap `2`

Batch 4 intentionally disabled compute elasticity, and Batch 3 showed that the
standard workload did not reliably trigger compute scale-up at `MAX_DYNAMIC_COMPUTE=1`.
Batch 5 keeps the workload normal but raises the final full-policy compute cap
to `2` so the controller has enough headroom to show whether compute elasticity
activates naturally after the staged drain and scale-up gate changes.

Do not tune compute thresholds for this batch unless the user explicitly starts
a separate compute-focused investigation.

---

## Per-run Environment Values

Before each run, update `source/scripts/osken-controller.env` on `cloud-vm` so
the following keys match the intended row exactly:

| Run label | Required env values |
| --- | --- |
| `batch5_normal_static` | `SS_ENABLED=0`, `MAX_DYNAMIC_STORAGE=0`, `MAX_DYNAMIC_COMPUTE=0` |
| `batch5_normal_storage` | `SS_ENABLED=0`, `MAX_DYNAMIC_STORAGE=5`, `MAX_DYNAMIC_COMPUTE=0` |
| `batch5_normal_combined` | `SS_ENABLED=1`, `MAX_DYNAMIC_STORAGE=5`, `MAX_DYNAMIC_COMPUTE=0` |
| `batch5_normal_full_c2` | `SS_ENABLED=1`, `MAX_DYNAMIC_STORAGE=5`, `MAX_DYNAMIC_COMPUTE=2` |

After editing, verify the applied values with a read-only check such as:

```bash
grep -E '^(SS_ENABLED|MAX_DYNAMIC_STORAGE|MAX_DYNAMIC_COMPUTE)=' source/scripts/osken-controller.env
```

The run folder snapshot `controller_env_snapshot.env` is the authoritative
post-launch proof of the values actually used.

---

## Launch Command

Use the same standard command shape for every Batch 5 run, changing only the
`RUN_LABEL` after the env file is set:

```bash
sudo -n make setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=<run_label> SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

For example, the final full-policy run is:

```bash
sudo -n make setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=batch5_normal_full_c2 SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

The expected run folders are created under
`source/scripts/testing/metrics/` using the pattern
`<timestamp>_<run_label>`.

---

## Execution Sequence

Run the matrix in this order:

1. `batch5_normal_static`
2. `batch5_normal_storage`
3. `batch5_normal_combined`
4. `batch5_normal_full_c2`

This order keeps interpretation simple:

1. `B5-C0` establishes the current normal static baseline.
2. `B5-C1` isolates updated Tier 2 behavior without Tier 1 or compute.
3. `B5-C2` adds Tier 1 on top of the storage path.
4. `B5-C3` adds compute elasticity last, with `MAX_DYNAMIC_COMPUTE=2`.

Do not start the next run until the current run has completed, its run folder
has been identified, and the campaign brief has been updated with at least the
run ID and a short interim verdict.

---

## Live Checkpoint Plan

| Trigger | Question | Data sources | Continue if | Stop or restart if | Agent authority |
| --- | --- | --- | --- | --- | --- |
| Pre-run env check | Do the three controller knobs match the intended matrix row? | `source/scripts/osken-controller.env`, later `controller_env_snapshot.env` | Values match the row | Values do not match; fix env before launch | Agent may edit only `source/scripts/osken-controller.env` between runs |
| Launch | Did setup and traffic generation begin cleanly? | Terminal output, new metrics folder, `current_phase.txt` | New run folder exists and phase advances beyond setup | `sudo -n` fails, setup fails, or no run folder is created | Agent may stop before traffic starts and report |
| Storage activity window | For `B5-C1`, `B5-C2`, and `B5-C3`, does Tier 2 spawn and reach service when storage thresholds fire? | `controller_lan1.log`, `controller_lan2.log`, `container_events.csv`, `resource_stats.csv` | Run keeps producing requests, regardless of whether storage scale-up fires | Run is clearly dead before producing storage-sensitive evidence | Read-only observation only |
| Tier 1 activity window | For `B5-C2` and `B5-C3`, does Tier 1 reach `ACTIVE` without the old attach failure? | Controller logs, `resource_stats.csv`, `container_events.csv` | Tier 1 works or the run still produces useful evidence without it | Old `Permission denied` wrapper failure returns before useful evidence | Report evidence; do not interrupt active run unless it has already failed |
| Compute opportunity window | For `B5-C3`, does compute elasticity naturally trigger with cap `2`? | Controller logs, `container_events.csv`, `per_node_stats.csv`, `resource_stats.csv` | `ComputeAlert` appears, or no compute event appears but the run completes | Compute behavior crashes the run before useful evidence is produced | Read-only observation only |
| Demand drop and idle | Did scale-down, drain, cancel, and cleanup complete cleanly? | Controller logs, `container_events.csv`, final `resource_stats.csv` rows | Cleanup completes or residual debt is captured for analysis | No automatic stop after traffic has already completed | Agent may analyze after completion |

Compute-specific log markers to search in `B5-C3` if present:

- `ComputeAlert`
- `scale_down_compute`
- `compute candidate selected`
- `CancelComputeDrainAlert`
- `cancel_compute_drain`
- `canceled compute drain`
- `drain_complete`

Absence of these markers is not a failed run. It means the normal workload did
not naturally exercise that compute path.

---

## Stop And Restart Policy

Automatic stop is allowed only before useful traffic evidence exists, or after
the run has clearly failed and is no longer progressing.

Allowed restart cases:

1. `sudo -n` or setup fails before traffic starts.
2. No run folder is created.
3. The SSH-bound launch path dies before traffic starts.
4. The SSH-bound launch path dies during traffic and read-only checks show the
   run is no longer active and produced no useful partial evidence.

Restart rules:

1. Do not kill or clean up an active run just because the terminal detached.
   First use read-only checks to determine whether traffic is still running.
2. If a relaunch is needed for an infrastructure or transport failure, reuse
   the same run label only after the environment is cleanly rebuilt by the
   standard launch command.
3. If a partial run folder exists, record its run ID in the campaign brief and
   mark it as infrastructure-failure evidence, not as a performance result.
4. Do not restart for poor performance, failed scale-up, failed scale-down, or
   lifecycle churn. Those are behavioral results for this batch.

---

## Post-run Analysis

For each completed run, resolve the actual run folder path and run the standard
analysis commands after traffic has completed:

```bash
RUN_DIR="source/scripts/testing/metrics/<run_id>"

python source/scripts/tools/metrics_stats.py "$RUN_DIR" --by-phase --by-lan --by-endpoint
python source/scripts/tools/metrics_stats.py -r "$RUN_DIR/resource_stats.csv" --by-phase --by-network
python -m source.scripts.testing.analysis.cli_simple_run --run-dir "$RUN_DIR"
python -m source.scripts.testing.analysis.cli_overview --run-dir "$RUN_DIR"
python -m source.scripts.testing.analysis.cli_scale_down --run-dir "$RUN_DIR"
python -m source.scripts.testing.analysis.cli_cpu_drivers --run-dir "$RUN_DIR"
python -m source.scripts.testing.analysis.cli_tdb_drivers --run-dir "$RUN_DIR"
```

Then use the repository `metrics-run-summary` workflow for the run folder and
write `run_summary.md` before deleting transient request CSVs or controller
logs.

After all four runs complete, produce a simple cross-run comparison:

```bash
python -m source.scripts.testing.analysis.cli_simple_compare \
  --run-dir source/scripts/testing/metrics/<b5_c0_run_id> \
  --run-dir source/scripts/testing/metrics/<b5_c1_run_id> \
  --run-dir source/scripts/testing/metrics/<b5_c2_run_id> \
  --run-dir source/scripts/testing/metrics/<b5_c3_run_id> \
  --output-dir source/scripts/testing/metrics/batch5_normal_compare
```

If controller logs are still needed for interpretation, copy the full run
folder back before remote cleanup. If logs are no longer needed, summarize and
trim on the cloud host before copy-back. Delete the remote run folder only
after the local copy is verified. If the cloud host still rejects direct
`sudo -n rm`, keep the remote folder and report the retention caveat.

---

## Interpretation Criteria

### `B5-C0` static baseline

Use this run to verify that the normal workload still produces a comparable
baseline after the staged changes. It should have no dynamic compute, dynamic
storage, or Tier 1 selective-sync service activity.

Primary comparisons:

1. Failure rate and p95 latency by phase against Batch 4 `batch4_c0`.
2. Request volume against Batch 4 `batch4_c0`.
3. Any zero-count telemetry windows or serving-path anomalies.

### `B5-C1` storage-only run

Use this run to isolate the updated Tier 2 storage path.

Primary questions:

1. How long does it take from `DataAlert` submission to dynamic storage
   readiness or VIP admission?
2. Do dynamic storage nodes reach service more cleanly than in Batch 4?
3. Does the final idle snapshot show less Tier 2 cleanup debt?
4. Does `storage_count` rise without causing worse failure rate or throughput
   collapse?

Compare mainly against Batch 4 `batch4_c2s4` and `batch4_c3s5` storage
behavior, while keeping in mind that `B5-C1` has Tier 1 disabled.

### `B5-C2` combined storage plus Tier 1 run

Use this run to test whether the updated storage path changes the Batch 4
combined-policy reading.

Primary questions:

1. Does Tier 1 reach `ACTIVE` on both LAN directions when the normal workload
   creates cross-region pressure?
2. Does Tier 1 improve hotspot behavior over `B5-C1`, or mainly add lifecycle
   and reconfigure noise?
3. Does Tier 2 still scale and clean up when Tier 1 is active?

Compare mainly against `B5-C1` and Batch 4 `batch4_c3s5`.

### `B5-C3` full run with compute cap `2`

Use this run as the normal full-policy reference for the staged changes.

Primary questions:

1. Does compute elasticity naturally activate under the standard workload with
   `MAX_DYNAMIC_COMPUTE=2`?
2. If compute scale-down happens, does the controller choose a telemetry-ranked
   candidate rather than simply the newest dynamic node?
3. If load rises while a compute drain is pending, does `ComputeAlert` land
   before `CancelComputeDrainAlert` and does the drain cancel succeed?
4. If no compute activity appears, does the run still improve or regress due
   to storage and Tier 1 behavior?

Compare mainly against `B5-C2` and Batch 4 `batch4_c3s5`.

---

## Expected Output Artifacts

Batch 5 should produce:

1. Four run folders under `source/scripts/testing/metrics/`, one per Batch 5
   label.
2. A `controller_env_snapshot.env` in each run folder proving the matrix knobs.
3. A `run_summary.md` in each run folder.
4. Analysis outputs under each run's `analysis/` directory.
5. A comparison output directory at
   `source/scripts/testing/metrics/batch5_normal_compare/`.
6. A final synthesis document at
   [`elasticity_ablation_batch5_results.md`](./elasticity_ablation_batch5_results.md).

---

## Completion Checklist For The Runner Agent

Before marking the batch complete, confirm:

1. All four intended labels have either a completed run ID or a documented
   infrastructure-failure partial run ID.
2. Each completed run has a `run_summary.md`.
3. Each completed run has preserved enough evidence to answer its primary
   questions.
4. The full run uses `MAX_DYNAMIC_COMPUTE=2` in `controller_env_snapshot.env`.
5. The campaign brief lists the run IDs, verdicts, copy-back status, and next
   recommended action.
6. Remote deletion happened only after local copy verification, or the remote
   retention caveat is explicitly recorded.
