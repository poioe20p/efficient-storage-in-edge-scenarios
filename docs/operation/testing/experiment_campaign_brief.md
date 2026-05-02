# Experiment Campaign Brief

Use this file as the durable working context for successive experiment runs in this repository.

- Update it before launching a new run when the objective, run delta, or allowed edit scope changes.
- Update it after each completed run summary.
- Do not edit it during an active run unless you are recording a stop or restart decision after the run has already been halted.

## Campaign

- Name: Observe current full policy
- Status: completed
- Objective: Observe the current shared controller configuration as-is before any write-path or logging changes.
- Hypothesis: If the current full policy has a real request-path or storage-path defect, the instability will reappear in the storage-sensitive or hotspot phases of a zero-change rerun.
- Primary decision question: How does the current C4-style configuration behave end-to-end before any fixes are applied?

## Remote Execution Context

- VM entry: `ssh vm-tese`
- VM repo path: `/media/sf_shared/scripts`
- Default experiment entrypoint: `make setup_network create_clients setup_test_data run_experiment RUN_LABEL=observe_current_c4 SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1`
- Sync step required: no

## Metric Lens

- Primary metrics: per-phase failures and p95 latency from the generated request CSVs; storage_count and server_count trends in resource_stats.csv; controller warnings during Tier 1 and Tier 2 activity.
- Secondary metrics: container_events.csv lifecycle changes; per_node_stats.csv when present; current_phase.txt during live monitoring.
- Required reference runs: 20260502_001954_c4 as the previous full-policy rerun; 20260501_225337_c2 as the clean Tier 2 reference.
- Interpretation rule: treat this run as observation-only for the current full policy; do not claim the exact query_events write target from controller logs alone.

## Allowed Between-Run Edit Scope

- Allowed files or directories: none before this run.
- Forbidden areas: source/, docs/, scripts/, and active run artifacts while the run is in progress.
- Expected effect: zero-change rerun of the currently shared osken-controller.env configuration after local network setup, client creation, and test-data preparation.
- Validation before next run: none; this step is the baseline observation run.

## Live Checkpoint Plan

| Trigger | Question | Data Sources | Continue If | Stop Or Restart If | Notes |
| ------- | -------- | ------------ | ----------- | ------------------ | ----- |
| Pre-run prerequisites | Did local network setup, client creation, and test-data preparation finish cleanly? | Terminal output from the combined `make setup_network create_clients setup_test_data run_experiment ...` launch before traffic starts | The setup targets finish and the run proceeds into traffic generation | Any prerequisite stage fails before traffic starts | Do not start the observation run until prerequisites succeed |
| Run start | Did the harness create a new metrics folder and begin traffic generation cleanly? | Terminal output, active run folder | The run folder appears and traffic starts | The run fails before traffic starts | Infrastructure failure only |
| End of local_moderate | Is the current full policy already unstable before the main storage-sensitive windows? | current_phase.txt, resource_stats.csv, container_events.csv, controller logs | Requests are still flowing, even if degraded | The run collapses before storage_stress | Early instability is still useful evidence |
| First storage-sensitive window | Does Tier 2 visibly activate under the current policy? | resource_stats.csv, per_node_stats.csv, controller_lan1.log, controller_lan2.log | Storage elasticity signals appear or the run progresses into hotspot phases | The environment fails so badly that the run no longer produces useful evidence | Observation only; no tuning during the run |
| reverse_hotspot to demand_drop | Does the current full policy stabilize, degrade, or collapse under the integrated path? | Same sources plus terminal output | The run remains collectible to completion | The run is clearly dead and no more evidence will be produced | Stop only for obvious unrecoverable failure |

## Successive Runs

| Planned Label | Intended Delta | Command Or Config Change | Primary Metrics To Inspect | Result Run ID | Verdict | Next Action |
| ------------- | -------------- | ------------------------ | -------------------------- | ------------- | ------- | ----------- |
| observe_current_c4 | None; observe current shared configuration | Inside `ssh vm-tese` at `/media/sf_shared/scripts`: `make setup_network create_clients setup_test_data run_experiment RUN_LABEL=observe_current_c4 SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1` with the existing shared `osken-controller.env` | Failures by phase, p95 latency, storage_count, server_count, controller warnings | 20260502_131444_observe_current_c4 | Late collapse with late compute alerts; not a positive full-policy reference | Preserve this as the current-behavior baseline, then add edge-server log capture before the next write-path diagnostic run |

## Stop And Restart Policy

- Automatic stop allowed: no, except for a clearly unrecoverable infrastructure failure.
- Automatic restart allowed: no.
- Escalation threshold: stop only if the run dies before producing useful workload evidence.
- Recovery plan: record the failure reason, keep the partial artifacts, and reassess before any rerun.

## Cross-Run Notes

- Reference comparison: this completed rerun stayed healthy through `storage_stress` and then collapsed later, but it is still much worse than the clean `C2` Tier 2 reference and not healthier than the earlier completed `C4` rerun overall.
- Partial run note: `20260502_122953_observe_current_c4` stopped during baseline after a terminal-level interruption; keep its artifacts for debugging, but do not use it as evidence for policy behavior.
- Open defects: Tier 1 still shows post-cleanup `/forwarder_config` retries against a removed container; controller-only logging still cannot prove the exact `query_events` write target.
- Confidence level: high for the late integrated-path collapse, low for direct write-target attribution.

## Next Run Checklist

1. Confirm the intended delta.
2. Confirm the command to run inside the VM.
3. Confirm any allowed between-run edit scope.
4. Confirm the live checkpoint plan.
5. Confirm the stop or restart criteria.
6. Confirm the reference runs to compare after completion.
