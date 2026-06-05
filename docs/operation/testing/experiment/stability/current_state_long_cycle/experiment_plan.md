# Experiment Plan - Current State Integrated Baseline Cycle

## Intent

This experiment evaluates the current integrated system state with one single phased workload profile that must exercise the mechanisms already implemented in the platform inside the same run: Tier 2 storage scale-out, Tier 1 selective-sync activation, compute scale-out, and final cleanup. It answers one operational question: is the current code and controller snapshot in a stable enough state that all elasticity mechanisms can be exercised together, repeatedly, and cleanly before newer features are added? The plan is grounded in the testing contract in [testing_overview.md](../../../testing_overview.md), the current traffic-generator schema in [traffic_generator.md](../../../traffic_generator.md), the shared runner in [run_experiment.sh](../../../../../../source/scripts/testing/run_experiment.sh), the approved `make` entrypoint in [Makefile](../../../../../../source/scripts/Makefile), the controller knobs in [osken-controller.env](../../../../../../source/scripts/osken-controller.env) and [scaling_config.py](../../../../../../source/sdn_controller/scaling_config.py), the Tier 1 promotion gate in [promotion.py](../../../../../../source/sdn_controller/selective_sync/promotion.py) and [hotness.py](../../../../../../source/sdn_controller/selective_sync/hotness.py), the new integrated phase file [phases_experiment_integrated_baseline.json](../../../../../../source/scripts/testing/phases_experiment_integrated_baseline.json), and the historical combined-policy evidence recorded in [experiment_campaign_brief.md](../../../experiment_campaign_brief.md).

## Hypothesis / Expected Outcome

If the current system state is baseline-ready, two identical runs of the integrated profile should both complete all phases, raise `storage_count` above `1` during the storage-locality phases, emit `SelectiveSyncAlert` and reach `ACTIVE` during both hotspot directions, trigger dynamic compute during the dashboard-heavy tail, and return every dynamic compute, storage, and selective-sync container to baseline by final idle. If any mechanism remains unexercised in a run, or if one of the exercised mechanisms fails to drain cleanly, the baseline cycle is incomplete even if the rest of the run looks healthy.

## Independent Variable & Held-Constant Set

- Independent variable: run replicate only (`current_state_integrated_a` versus `current_state_integrated_b`).
- Held constant: current repository HEAD, current container images, the shared base env [osken-controller.env](../../../../../../source/scripts/osken-controller.env) plus the fixed override [current_state_integrated.env](../../../../../../source/scripts/testing/controller_env_overrides/current_state_integrated.env), the integrated phase file [phases_experiment_integrated_baseline.json](../../../../../../source/scripts/testing/phases_experiment_integrated_baseline.json), no `--fault-plan`, same operator host/VM, same WAN profile, same launch path, and no code, env, or image changes between the two runs.
- Held constant controller knobs: use [current_state_integrated.env](../../../../../../source/scripts/testing/controller_env_overrides/current_state_integrated.env) unchanged for both replicates so `SS_ENABLED=1`, `MAX_DYNAMIC_STORAGE=5`, and `MAX_DYNAMIC_COMPUTE=2` are fixed without editing the shared base env in place.
- Held constant workload sizing: `CLIENTS=3`, `DEVICES=600`, `NODES=100` for both runs. The seeded snapshot is large enough to create meaningful storage pressure, while Tier 1 remains compatible with this run shape because promotion is gated by collection-level read volume and cross-region ratio rather than by a per-document minimum-hit threshold.
- Abort rule: if any runtime-bearing file, controller env value, or image changes after `current_state_integrated_a`, discard the pair and restart from `current_state_integrated_a` under a new label family.

## Run Matrix

| Run label | What changes | Phase file |
| --- | --- | --- |
| `current_state_integrated_a` | First integrated baseline replicate | [phases_experiment_integrated_baseline.json](../../../../../../source/scripts/testing/phases_experiment_integrated_baseline.json) |
| `current_state_integrated_b` | Second integrated baseline replicate | [phases_experiment_integrated_baseline.json](../../../../../../source/scripts/testing/phases_experiment_integrated_baseline.json) |

Run order is fixed: `current_state_integrated_b` only starts after `current_state_integrated_a` artifacts are copied back and the operator confirms there were no code, env, or image changes in between.

## Run Configuration

- Launch path: verified non-interactive `make` workflow from [Makefile](../../../../../../source/scripts/Makefile).
- `--phases-config`: `source/scripts/testing/phases_experiment_integrated_baseline.json` via `PHASES_CONFIG=testing/phases_experiment_integrated_baseline.json`.
- `--run-label`: `current_state_integrated_a` and `current_state_integrated_b`.
- `--batch-dir`: omitted in the default `make` path.
- `--clients-per-lan`: `3` via `CLIENTS=3`.
- `--seed-devices`: `600` via `DEVICES=600`.
- `--seed-nodes`: `100` via `NODES=100`.
- Skip flags: `SKIP_CLIENTS=1`, `SKIP_SEED=1`, and `SKIP_SNAPSHOT=1` inside `run_experiment`, because the same `make` call already runs `setup_network`, `create_clients`, and `setup_test_data` before `run_experiment`.
- `--fault-plan`: omitted explicitly.
- Controller override: `OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env` so both runs launch with the same integrated controller state.
- Code/config toggles: keep the shared base env [osken-controller.env](../../../../../../source/scripts/osken-controller.env) unchanged across both runs. Do not rebuild images or retune thresholds between the two replicates unless the operator intentionally starts a different experiment.

Concrete commands:

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
   OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=current_state_integrated_a \
  PHASES_CONFIG=testing/phases_experiment_integrated_baseline.json \
  CLIENTS=3 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
   OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=current_state_integrated_b \
  PHASES_CONFIG=testing/phases_experiment_integrated_baseline.json \
  CLIENTS=3 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

## Focus & Evidence

Primary focus: `resource_stats.csv`, `controller_lan1.log`, `controller_lan2.log`, `container_events.csv`, and `client_requests.csv`.

- `resource_stats.csv` is the lifecycle authority for `storage_count`, `server_count`, `coord_state_owner_lan`, `tier1_lifecycle_active_count`, `coord_hot_doc_total`, and per-phase DB-latency signals.
- `controller_lan1.log` and `controller_lan2.log` answer whether the control loop stayed healthy and whether `DataAlert`, `SelectiveSyncAlert`, `ACTIVE`, `ComputeAlert`, scale-down, and cleanup markers appeared in the intended phases.
- `container_events.csv` is the add/remove ground truth for dynamic compute, storage, and selective-sync containers and for final cleanup debt.
- `client_requests.csv` answers whether the heavier integrated run stayed serviceable, where non-200s appeared, and whether failures remained bounded to the intended hotspot windows.

Secondary focus: `per_node_stats.csv`, `policy_state.csv`, `elasticity_events.csv`, `phases_snapshot.json`, and `service_logs/`.

- `per_node_stats.csv` helps confirm which containers carried CPU and DB pressure during the storage-locality and compute-heavy phases.
- `policy_state.csv` and `elasticity_events.csv` are the tie-breakers when logs and CSVs disagree about why a mechanism did or did not trigger.
- `phases_snapshot.json` confirms the exact integrated profile that ran.
- `service_logs/` is only needed if controller or lifecycle evidence suggests a service-side crash, restart loop, or repeated timeout path.

## Metrics & Success Criteria

The current state is considered baseline-ready only if both integrated replicates satisfy all criteria below.

1. Run completion and artifact integrity.
   Both runs must reach `current_phase.txt=idle`, complete all ten phases from [phases_experiment_integrated_baseline.json](../../../../../../source/scripts/testing/phases_experiment_integrated_baseline.json), and emit the standard artifact contract from [testing_overview.md](../../../testing_overview.md).
2. Required Tier 2 storage exercise.
   Both runs must show `storage_count > 1` in `resource_stats.csv` and at least one dynamic storage add event in `container_events.csv` or `elasticity_events.csv` during `storage_stress`, `cross_region_hotspot`, or `reverse_hotspot`.
3. Required Tier 1 exercise.
   Both runs must show a real selective-sync path in both hotspot directions: `SelectiveSyncAlert` in controller logs, at least one `sel_sync_*` add event in `container_events.csv`, and `coord_state_owner_lan=ACTIVE` or `tier1_lifecycle_active_count=1` aligned to both `cross_region_hotspot` and `reverse_hotspot` windows.
4. Required compute exercise.
   Both runs must show `server_count > 1` in `resource_stats.csv` and at least one dynamic compute add event in `container_events.csv` or `elasticity_events.csv` during `compute_ramp`, `compute_spike`, or `sustained_plateau`.
5. Control-plane and runtime health.
   Neither controller log may contain an unhandled Python traceback, repeated fatal exception loop, or evidence that a controller stopped making forward progress during an active phase. No core `edge_server*`, `osken*`, or `local_state_*` container may enter a crash loop.
6. Cleanup correctness.
   By final idle of each run, no unexpected dynamic compute, storage, or selective-sync container should still be running. The run must show drain or cleanup markers for every mechanism that activated.
7. Service-quality envelope.
   Each run must keep overall non-200 responses at or below `5.0%`. Non-hotspot phases `baseline`, `local_moderate`, `inter_hotspot_cooldown`, `compute_ramp`, `compute_spike`, `sustained_plateau`, and `demand_drop` must each stay at or below `1.0%` failures. Hotspot phases `storage_stress`, `cross_region_hotspot`, and `reverse_hotspot` must each stay at or below `10.0%` failures.
8. Inter-run repeatability.
   The pair must stay in the same qualitative regime across both runs: all three mechanisms trigger, total request volume differs by no more than `10%`, per-phase p95 latency differs by no more than `35%` in the storage-locality phases and no more than `30%` in the compute phases, and cleanup converges to the same final baseline shape.

## Checkpoints

| Trigger | Question | Evidence | Runner action |
| --- | --- | --- | --- |
| End of `storage_stress` | Has Tier 2 begun to scale out, or is `storage_count` still pinned at `1`? | `resource_stats.csv`, `container_events.csv`, controller logs | Report only |
| Mid `cross_region_hotspot` | Did the first directional hotspot emit `SelectiveSyncAlert` and reach `ACTIVE`? | `resource_stats.csv`, `container_events.csv`, controller logs | Report only |
| Mid `reverse_hotspot` | Did the reverse direction also emit `SelectiveSyncAlert` and reach `ACTIVE`? | `resource_stats.csv`, `container_events.csv`, controller logs | Report only |
| Mid `compute_spike` | Has compute elasticity actually added a dynamic edge server under the dashboard-heavy tail? | `resource_stats.csv`, `container_events.csv`, controller logs, `per_node_stats.csv` | Report only |
| End of `demand_drop` | Did every activated mechanism drain back to baseline before idle? | `container_events.csv`, `resource_stats.csv`, `service_logs/`, controller logs | Report only |

## Validity Threats & Limitations

- This integrated baseline is stronger than the old standard long-cycle repeatability check. It is a readiness gate for exercising mechanisms together, not a like-for-like continuation of the previous low-pressure baseline.
- The seeded device and node counts define one run-wide workload snapshot, but the mechanisms are exercised by the phase-local range of rate, mix, cross-region ratio, and hotspot direction within the profile. That is the current supported way to vary workload shape inside one run.
- The controller's Tier 1 promotion gate is collection-level, not dependent on a per-document minimum-hit threshold. A larger seeded working set therefore does not by itself block Tier 1 promotion, while the manifest remains bounded by `SS_HOT_DOC_LIMIT`.
- No `--fault-plan` is used here, so this experiment does not validate failed-backend avoidance, explicit hard-failure recovery, or other synthetic-fault paths.
- If one mechanism fails to trigger while the others behave as expected, use the isolated companion workloads [phases_experiment_storage_trigger.json](../../../../../../source/scripts/testing/phases_experiment_storage_trigger.json) and [phases_experiment_tier1_hotspot_bidirectional.json](../../../../../../source/scripts/testing/phases_experiment_tier1_hotspot_bidirectional.json) as diagnostic follow-up, not as the baseline gate itself.
- Host-level noise, WAN-profile drift, or accidental env edits between runs can create false differences. That is why the plan fixes the launch path and forbids code, env, or image changes between the two replicates.

## Artifact Contract

Each run folder under `source/scripts/testing/metrics/<timestamp>_<run_label>/` must contain the standard run artifacts described in [testing_overview.md](../../../testing_overview.md): `client_requests.csv`, `resource_stats.csv`, `resource_stats_debug.csv`, `policy_state.csv`, `per_node_stats.csv`, `container_events.csv`, `elasticity_events.csv`, `controller_lan1.log`, `controller_lan2.log`, `controller_env_snapshot.env`, `phases_snapshot.json`, and `service_logs/`.

Expected later analysis outputs:

- Root run summaries such as `run_summary.md`, `latency_summary.csv`, `resource_summary.csv`, `elasticity_events.csv`, and `node_lifecycle_timings.csv`.
- A direct comparison output for `current_state_integrated_a` and `current_state_integrated_b`, preferably using the existing analysis CLIs documented in [analysis_toolchain.md](../../../analysis_toolchain.md).
- A focused integrated-mechanisms note that records first storage add, first Tier 1 `ACTIVE` window per direction, first compute add, the cleanup sequence, and any residual debt or phase-local failure spikes.
No additional experiment-specific outputs are required beyond the artifacts and summaries listed above.
<!-- end -->

