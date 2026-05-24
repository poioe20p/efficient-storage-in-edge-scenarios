---
name: metrics-run-summary
description: 'Use when: analyzing an experiment metrics run folder, writing source/scripts/testing/metrics/<timestamp>/run_summary.md, using metrics_stats.py, running source/scripts/testing/analysis tools, interpreting elasticity, Tier 1 selective-sync, traffic latency, scale-up/down, and cleaning transient client request CSV/controller log files after the summary is produced.'
argument-hint: 'source/scripts/testing/metrics/<timestamp> or <timestamp>'
---

# Metrics Run Summary

## Outcome

Produce a concise, evidence-backed `run_summary.md` inside one metrics run
folder, normally `source/scripts/testing/metrics/<timestamp>/run_summary.md`.
The summary should explain how the run went in terms of elasticity, scale-up and
scale-down, Tier 1 selective-sync behavior, traffic handling, and any relevant
defects or caveats.

By default, use this skill once for each newly completed experiment run folder
under `source/scripts/testing/metrics/`, unless the user explicitly says to
defer the summary or keep the folder untouched.

After the summary is written and checked, clean the target run folder by deleting
only transient controller log files: `controller_lan[0-9].log`. Before deleting
controller logs, parse and retain `elasticity_events.csv` and
`node_lifecycle_timings.csv`. Leave every other file in the run folder intact.

When the run folder lives on `cloud-vm`, this skill is also the default remote
size-reduction step. Unless the user says controller logs still need to be kept
or the remote folder must remain in place, copy the reduced run folder back to
the local machine after cleanup, verify the copy succeeded, and then delete the
remote run folder to reclaim cloud disk space.

## Input Resolution

1. Accept either an absolute/relative run folder path or a bare timestamp such as
   `20260428_170152`.
2. If given a bare timestamp, resolve it to
   `source/scripts/testing/metrics/<timestamp>`.
3. Before any cleanup, confirm the resolved path is inside
   `source/scripts/testing/metrics/` and the folder name matches a timestamp-like
   pattern.
4. If the run folder is missing, stop and report the missing path.

## Evidence To Inspect

Read the run artifacts before writing conclusions:

- `resource_stats.csv` for domain-level CPU, RAM, latency decomposition,
  `server_count`, `storage_count`, `phase`, and `network_id`.
- `per_node_stats.csv` when present for per-node CPU/load-balance evidence.
- `container_events.csv` for dynamic compute, Tier 2 storage, and Tier 1
  selective-sync lifecycle anchors.
- `phases_snapshot.json` for phase order, duration, request mix, and
  cross-region ratios.
- `client_requests.csv` for per-phase latency, failures, endpoint, and LAN
  split via its `phase` column.
- `controller_lan1.log` and `controller_lan2.log` for alerts, spawn events,
  scale-down evaluations, cleanup failures, telemetry gaps, or exceptions.
  These are deleted only after the summary is complete.
- `elasticity_events.csv` and `node_lifecycle_timings.csv`, when present, for
  retained controller-log event and node add/remove timing evidence after raw
  controller logs are trimmed.
- Existing `run_summary.md`, if present, to understand whether this is a new
  summary, replacement, or update.

## Required Tooling

Use `metrics_stats.py` for descriptive statistics before making numerical
claims:

```powershell
python source/scripts/tools/metrics_stats.py "<run_dir>" --by-phase --by-lan --by-endpoint
python source/scripts/tools/metrics_stats.py -r "<run_dir>/resource_stats.csv" --by-phase --by-network
```

The first command processes `client_requests.csv`, prints latency statistics,
and appends `latency_summary.csv`. The second processes `resource_stats.csv`
and appends `resource_summary.csv`.

Use the analysis package when the needed input files exist:

```powershell
python -m source.scripts.testing.analysis.cli_overview --run-dir "<run_dir>"
python -m source.scripts.testing.analysis.cli_scale_down --run-dir "<run_dir>"
python -m source.scripts.testing.analysis.cli_cpu_drivers --run-dir "<run_dir>"
python -m source.scripts.testing.analysis.cli_tdb_drivers --run-dir "<run_dir>"
```

These commands create or append files under `<run_dir>/analysis/`, including
`overview.png`, `scale_down.png`, `cpu_drivers.png`, `tdb_drivers.png`, and
`analysis/summary.md` when their data dependencies are available.

If `matplotlib` is missing, install the analysis requirements before running the
plotting CLIs:

```powershell
python -m pip install -r source/scripts/testing/analysis/requirements.txt
```

When controller logs exist, parse them before cleanup and keep both CSV outputs:

```powershell
python source/scripts/tools/parse_elasticity_logs.py "<run_dir>/controller_lan1.log" "<run_dir>/controller_lan2.log" -o "<run_dir>/elasticity_events.csv" --timings-output "<run_dir>/node_lifecycle_timings.csv"
```

## Analysis Procedure

1. Identify the run and collect artifact availability.
   - Note missing optional files explicitly instead of inventing evidence.
   - Treat missing `per_node_stats.csv` as a limitation for load-balance claims.
   - Treat missing controller logs as a limitation for exact alert or cleanup
     diagnosis.

2. Generate statistics.
   - Run `metrics_stats.py` for latency and resource summaries.
  - Run `parse_elasticity_logs.py` when controller logs exist, producing
    `elasticity_events.csv` and `node_lifecycle_timings.csv` before any log
    cleanup.
   - Run the analysis CLIs that match the available artifacts.
   - Prefer generated summary CSVs and analysis outputs for quantitative claims,
     but cross-check surprising results against raw CSV/log snippets.

3. Analyze elasticity.
   - Count and time `ComputeAlert` and `DataAlert` events.
   - Identify dynamic compute containers such as `edge_server_*_dyn*`.
   - Identify dynamic Tier 2 storage containers such as
     `edge_storage_*_dyn*`.
   - Report scale-up anchors: alert, spawn start, online, first use if visible.
   - Report scale-down anchors: armed, drain, cleanup, container removal.
   - If no dynamic compute or Tier 2 storage appears, say so clearly and explain
     whether the run is a stable no-scale run or a failed-trigger run.

4. Analyze Tier 1 selective-sync.
   - Track selective containers such as `sel_sync_lan*_dyn*` from
     `container_events.csv` and controller logs.
   - Report promotion direction, online time, drain time, cleanup result, and
     any retry or missing-container defects.
   - State whether Tier 1 was used, whether it was drained, and whether cleanup
     or routing reconfiguration succeeded.

5. Analyze traffic handling.
   - Summarize request latency by phase: mean, p95, and failures.
   - Highlight late phases such as `compute_ramp`, `compute_spike`,
     `sustained_plateau`, and `demand_drop` when present.
   - Include per-LAN asymmetry when it changes interpretation.
   - Distinguish workload performance problems from post-workload cleanup
     defects.

6. Analyze resource shape.
   - Use `server_count` and `storage_count` to confirm scale-out/no-scale state.
   - Compare `median_time_proc_ms` and `median_time_db_ms` against expected
     compute/storage pressure.
   - Use `cli_scale_down` output to explain why scale-down did or did not arm
     when the run includes dynamic nodes.
   - Use `cli_cpu_drivers` to separate undersized tiers from routing or
     load-balancing failures.
   - Use `cli_tdb_drivers` when investigating storage-count/write-latency
     correlations.

7. Compare with reference runs when useful.
   - If the user names reference runs, compare the same phases and metrics.
   - If no reference is named, compare only when nearby run summaries or summary
     CSVs make the comparison obvious and relevant.

## `run_summary.md` Structure

Use this structure unless the run demands a narrower report:

```markdown
# Run Summary - <timestamp>

## Conclusion

<Short verdict: stable, scaled correctly, failed to scale, telemetry invalid,
cleanup defect, asymmetric failure, etc.>

## Main Points

- <Highest-signal findings.>

## Evidence

### Elasticity Events

<Alerts, dynamic containers, scale-up/down anchors, and controller errors.>

### Tier 1 Selective Sync

<Promotion, use, drain, cleanup, and reconfiguration behavior.>

### Resource Shape

<CPU/RAM/T_proc/T_db/server_count/storage_count by relevant phases.>

### Request Latency by Phase

| Phase | Mean (ms) | p95 (ms) | Failures |
| --- | ---: | ---: | ---: |

### Traffic Handling

<Per-LAN split, endpoint/phase behavior, and failure interpretation.>

## Practical Interpretation

<What this run means for the experiment campaign.>

## Follow-Up

<Only concrete follow-up that remains after the analysis. Omit if none.>
```

Keep the conclusion direct. Separate defects by subsystem: telemetry-plane,
elasticity decision, routing/load-balancing, Tier 1 cleanup, or workload/client
behavior. Do not treat cleanup errors after a healthy workload as performance
collapse unless the timing supports that claim.

## Cleanup Procedure

Cleanup is part of this skill, but only after `run_summary.md` has been written
and the summary is based on the data that will be removed.

1. List cleanup candidates inside the target run folder:
  - `controller_lan[0-9].log`
2. Verify every candidate path is directly under the resolved run folder.
3. Delete only those candidates.
4. Do not delete `client_requests.csv`, `resource_stats.csv`,
  `per_node_stats.csv`, `container_events.csv`, `phases_snapshot.json`,
  `latency_summary.csv`, `resource_summary.csv`, `elasticity_events.csv`,
  `node_lifecycle_timings.csv`, `run_summary.md`, or anything under
  `analysis/`.
5. Verify that no `controller_lan[0-9].log` files remain in that run folder.

## Cloud Copy-Back Procedure

Use this procedure when the analyzed run folder is on `cloud-vm`.

1. Confirm whether controller logs still need to be retained.
2. If controller logs are still needed, stop after the summary or copy the full
  folder first and do not delete the remote run folder.
3. If controller logs are no longer needed, run the cleanup procedure above.
4. Copy the remaining run folder back to the local machine with `scp`, `rsync`,
  or a similar transfer tool.
5. Verify the local copy exists and contains the expected summary and retained
  artifacts.
6. Unless the user asked to retain the remote copy, delete the remote run
  folder only after the local copy is verified.
7. If transfer verification fails, keep the remote run folder and report the
  failure instead of deleting it.

## Completion Checks

- `run_summary.md` exists in the target run folder.
- The summary has a clear conclusion and cites concrete phase metrics or event
  anchors.
- `latency_summary.csv` and `resource_summary.csv` exist when their source data
  was available.
- `elasticity_events.csv` and `node_lifecycle_timings.csv` exist when controller
  logs were available before cleanup.
- Analysis PNGs or `analysis/summary.md` exist when the corresponding analysis
  CLIs were runnable.
- The transient client request CSV and controller log files have been removed
  from the run folder after the summary was produced.
- If the cloud copy-back workflow was used, the verified local copy exists and
  the remote run folder was deleted only when the user did not request remote
  retention.
- No unrelated files were deleted.