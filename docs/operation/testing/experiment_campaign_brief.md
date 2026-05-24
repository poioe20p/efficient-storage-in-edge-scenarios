# Experiment Campaign Brief

## Completed One-Off Run - Hybrid Long-Cycle Observation Repeat Storage Check

- Status: completed.
- Objective: rerun the same long-cycle current-code observation workload used
  for `20260524_013746_hybrid_observation_current_code` so the previous
  “worked fine while storage stayed at 1” result can be tested for
  repeatability.
- Intended delta versus `20260524_013746_hybrid_observation_current_code`:
  - keep the same current runtime and controller code state.
  - keep the same standard long-cycle schedule from
    `source/scripts/testing/phases.json`.
  - keep the run observation-only: no `--fault-plan`.
  - change only the run label so the result is recorded as a separate repeat
    observation.
- Sync and rebuild policy:
  - no new sync is required before launch; local and remote SHA256 match for
    `source/scripts/Makefile`, `source/scripts/testing/phases.json`,
    `source/scripts/testing/run_experiment.sh`,
    `source/sdn_controller/vip_routing.py`, and
    `source/docker/edge_server/source/app.py`.
  - no image rebuild is required before launch; the checked baked
    `edge_server` runtime source also matches between local and `cloud-vm`.
- `sudo -n` preflight:
  - the required path is permitted: a dry-run of
    `sudo -n make -C source/scripts -n setup_network create_clients
    setup_test_data run_experiment
    RUN_LABEL=hybrid_observation_current_code_repeat_storage_check
    SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1` completed without prompting.
- Run label: `hybrid_observation_current_code_repeat_storage_check`.
- Primary comparisons:
  - compare directly against
    `20260524_013746_hybrid_observation_current_code` to test whether the same
    no-storage-scale shape repeats.
  - compare secondarily against `20260517_090203_two_regime_1680_full_recreate`
    only as the nearest kept long-cycle current-code baseline.
- Launch command:
  `ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios; sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment RUN_LABEL=hybrid_observation_current_code_repeat_storage_check SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1"`.
- Live checkpoint plan: passive monitoring only. Use read-only checks against
  `current_phase.txt`, `resource_stats.csv`, `per_node_stats.csv`,
  `container_events.csv`, controller logs, and `service_logs/`. Continue unless
  setup fails before useful traffic, the allowed `sudo -n make` path fails, or
  the run clearly stops progressing.
- Checkpoint question: when the same long-cycle workload is repeated on the
  same current-code state, does `storage_count` again stay fixed at 1, and if
  so does the previous stable latency and low-failure result reproduce?
- Agent authority: full autonomous authority within the experiment-runner
  contract for this run. The runner may launch, monitor passively, copy
  artifacts back locally, analyze the run, update this brief, and trim the
  cloud copy after verification.
- Result: completed as
  `20260524_091543_hybrid_observation_current_code_repeat_storage_check`.
- Completion evidence:
  - the remote run folder reached `current_phase.txt=idle`.
  - the main `sudo -n make -C source/scripts ... run_experiment` terminal
    exited with code 0.
  - the traffic generator completed all nine phases: `baseline`,
    `local_moderate`, `storage_stress`, `cross_region_hotspot`,
    `reverse_hotspot`, `compute_ramp`, `compute_spike`,
    `sustained_plateau`, and `demand_drop`.
  - the run emitted the expected artifact set including `client_requests.csv`,
    all per-phase `client_requests_*.csv` files, `resource_stats.csv`,
    `per_node_stats.csv`, `container_events.csv`, both controller logs,
    `service_logs/`, and `phases_snapshot.json`.
- Artifact status: the full run folder was copied back locally to
  `source/scripts/testing/metrics/20260524_091543_hybrid_observation_current_code_repeat_storage_check`.
  Local post-run analysis produced:
  - `analysis/recovery_validation_summary.md`
  - `analysis/recovery_validation_fault_windows.csv`
  - `analysis/recovery_validation_request_lease_outcomes.csv`
  - `run_summary.md`
  - `latency_summary.csv`
  - `resource_summary.csv`
  - `elasticity_events.csv`
  - `node_lifecycle_timings.csv`
- Remote retention status: the cloud copy was deleted after the verified local
  copy-back succeeded. The temporary remote tarball used to speed up transfer
  was also deleted, and `sudo -n make -C source/scripts cleanup_metrics`
  returned the remote metrics directory to `0` run folders.
- Interpretation:
  - the repeat run reproduced the earlier no-storage-scale shape. It finished
    with 19 non-200 responses out of 63,531 total requests, or 0.03% overall.
  - dynamic compute elasticity was slightly more active than in
    `20260524_013746_hybrid_observation_current_code`: container events
    recorded 12 dynamic compute additions and 12 removals, `server_count`
    again peaked at 3, and parsed controller timings placed compute ready times
    between 1.22 s and 2.51 s with cleanup timings between 0.45 s and 1.31 s.
  - `storage_count` again stayed fixed at 1, with no dynamic storage and no
    Tier 1 selective-sync activity.
  - recovery validation again remained entirely on `success_normal`
    (`lan1=43813`, `lan2=40243`) with `success_after_rebind=0`,
    `failure_terminal=0`, and controller avoidance/fallback markers still at 0.
  - compared directly against
    `20260524_013746_hybrid_observation_current_code`, the earlier “worked
    fine” result is therefore repeatable under the same no-storage-scale
    condition rather than being a one-off run. The remaining uncertainty is
    unchanged: this campaign still does not show whether that stable behavior
    depends on storage never scaling, because the workload again failed to move
    `storage_count` above 1.
- Next action: if the next campaign must determine whether no-storage-scale is
  the reason for the stable outcome, use a follow-up workload that reliably
  forces storage scale-out or a separately authorized storage-churn campaign.

## Campaign Outcome - Hybrid Observation Family

- Status: completed across all three planned runs.
- Completed runs:
  - `20260524_004416_hybrid_validation_n1`
  - `20260524_011256_hybrid_validation_n2`
  - `20260524_013746_hybrid_observation_current_code`
- Overall result:
  - all three observation-only runs completed and were copied back locally.
  - the current request-lease implementation did not show an obvious stability
    regression under either the targeted or long-cycle schedules.
  - none of the three runs naturally exercised the failed-backend-avoidance
    branch: all recovery-validation outputs remained entirely on
    `success_normal`, and controller avoidance/fallback markers stayed at 0.
  - the long-cycle run still exercised compute elasticity normally, with 11
    dynamic compute add/remove cycles, `server_count` peaking at 3, and
    `storage_count` fixed at 1.
- Remote retention status: the local copies remain under
  `source/scripts/testing/metrics/`, and the cloud copies were deleted after a
  dedicated `cleanup_metrics` target was added to the approved
  `sudo -n make -C source/scripts ...` path.
- Next recommended action: if the next campaign must prove the avoidance branch
  rather than confirm current-code stability, plan a stronger natural backend-
  churn workload or a separate explicitly authorized controlled-failure run.

## Completed One-Off Run - Hybrid Recovery Validation n2

- Status: completed.
- Objective: launch the mirrored short targeted hybrid observation run using
  the `n2` phase recipe so the current request-lease implementation and any
  naturally occurring controller recovery markers are observed under
  `lan1 -> lan2` pressure.
- Intended delta versus `20260524_004416_hybrid_validation_n1`:
  - keep the same synced runtime and harness code already used for `n1`.
  - switch only the phase profile to
    `source/scripts/testing/phases_experiment_hybrid_validation_n2.json`.
  - keep the run observation-only: no `--fault-plan`.
- Sync and rebuild policy:
  - no new runtime code sync is required before `n2`; the cloud VM already
    matches the local run-critical files from the completed `n1` launch.
  - no image rebuild is required before `n2`; `edge_server` was rebuilt from
    the synced request-lease runtime sources immediately before `n1`.
- `sudo -n` path: reuse the already verified non-interactive make path with
  `PHASES_CONFIG=testing/phases_experiment_hybrid_validation_n2.json` and the
  same combined prerequisite chain.
- Run label: `hybrid_validation_n2`.
- Primary comparisons:
  - compare directly against `20260524_004416_hybrid_validation_n1` to detect
    directional asymmetry between `lan2 -> lan1` and `lan1 -> lan2` targeted
    pressure.
  - compare both targeted runs against
    `20260517_090203_two_regime_1680_full_recreate` only as a broader
    architecture reference, not as the same workload family.
- Launch command:
  `ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios; sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment RUN_LABEL=hybrid_validation_n2 PHASES_CONFIG=testing/phases_experiment_hybrid_validation_n2.json SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1"`.
- Live checkpoint plan: passive monitoring only. Use read-only checks against
  `current_phase.txt`, `resource_stats.csv`, `container_events.csv`,
  controller logs, and `service_logs/`. Continue unless setup fails before
  useful traffic, the allowed `sudo -n make` path fails, or the run clearly
  stops progressing.
- Checkpoint question: does the mirrored `n2` workload show the same clean
  request-lease behavior as `n1`, or does the opposite hotspot direction expose
  different latency, failure, or controller-marker behavior?
- Agent authority: full autonomous authority within the experiment-runner
  contract for this run. The runner may launch, monitor passively, copy
  artifacts back locally, and update this brief after completion.
- Result: completed as `20260524_011256_hybrid_validation_n2`.
- Completion evidence:
  - the remote run folder reached `current_phase.txt=idle`.
  - the traffic generator completed all four phases: `warmup`,
    `storage_stress_n2`, `hotspot_n2`, and `cooldown`.
  - the run emitted the expected artifact set including `client_requests.csv`,
    `resource_stats.csv`, `per_node_stats.csv`, both controller logs,
    `container_events.csv`, `service_logs/`, and `phases_snapshot.json`.
- Artifact status: the full run folder was copied back locally to
  `source/scripts/testing/metrics/20260524_011256_hybrid_validation_n2`.
  Local post-run analysis produced:
  - `analysis/recovery_validation_summary.md`
  - `analysis/recovery_validation_fault_windows.csv`
  - `analysis/recovery_validation_request_lease_outcomes.csv`
- Remote retention status: the cloud copy was deleted after the dedicated
  `cleanup_metrics` target was added to the approved non-interactive make path.
- Interpretation:
  - no explicit fault events were recorded, as intended for this observation-
    only run.
  - request-lease outcomes were entirely `success_normal` in the generated
    recovery summary: `lan1=8903`, `lan2=12989`, with
    `success_after_rebind=0` and `failure_terminal=0` on both LANs.
  - controller recovery markers were absent again: `avoidance=0`,
    `fallback=0`.
  - the mirrored `n2` workload therefore matches the main `n1` conclusion:
    the targeted run completed, but it did not naturally force the
    failed-backend recovery branch strongly enough to exercise the avoidance
    logic.
- Next action: launch the standard long-cycle observation run on the same
  current-code state, then interpret it using the fact that neither targeted
  observation run naturally exercised the recovery branch.

## Completed One-Off Run - Hybrid Long-Cycle Observation Current Code

- Status: completed.
- Objective: after both targeted runs, execute the unchanged standard
  long-cycle workload on the same synced current-code state to observe broader
  architecture behavior with the new request-lease implementation in place.
- Intended delta versus `20260517_090203_two_regime_1680_full_recreate`:
  - keep the same current runtime and controller code state used for the
    targeted hybrid runs.
  - run the standard long-cycle schedule from
    `source/scripts/testing/phases.json`.
  - keep the run observation-only: no `--fault-plan`.
- Sync and rebuild policy:
  - `source/scripts/testing/phases.json` was synced to `cloud-vm` before
    launch, because it was not part of the targeted-run-only sync performed for
    `n1`.
  - no additional image rebuild was required before launch; the long-cycle run
    reused the same rebuilt `edge_server` image already validated by `n1` and
    `n2`.
- `sudo -n` path: reuse the verified non-interactive make path without a phase
  override.
- Run label: `hybrid_observation_current_code`.
- Primary comparisons:
  - compare against `20260517_090203_two_regime_1680_full_recreate` as the
    nearest kept long-cycle current-code reference.
  - compare interpretation against the completed targeted `n1` and `n2` runs
    to distinguish “feature not exercised” from broader architecture symptoms.
- Launch command:
  `ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios; sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment RUN_LABEL=hybrid_observation_current_code SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1"`.
- Live checkpoint plan: passive monitoring only. Use read-only checks against
  `current_phase.txt`, `resource_stats.csv`, `per_node_stats.csv`,
  `container_events.csv`, controller logs, and `service_logs/`. Continue unless
  setup fails before useful traffic, the allowed `sudo -n make` path fails, or
  the run clearly stops progressing.
- Checkpoint question: with the current request-lease code now deployed, does
  the long-cycle workload still produce the same storage and compute behavior
  seen in the latest kept long-cycle rerun, and do the targeted-run results
  change how that long-cycle behavior should be interpreted?
- Agent authority: full autonomous authority within the experiment-runner
  contract for this run. The runner may sync `phases.json`, launch, monitor
  passively, copy artifacts back locally, and update this brief after
  completion.
- Result: completed as `20260524_013746_hybrid_observation_current_code`.
- Completion evidence:
  - the remote run folder reached `current_phase.txt=idle`.
  - the traffic generator completed all nine phases: `baseline`,
    `local_moderate`, `storage_stress`, `cross_region_hotspot`,
    `reverse_hotspot`, `compute_ramp`, `compute_spike`,
    `sustained_plateau`, and `demand_drop`.
  - the run emitted the expected artifact set including `client_requests.csv`,
    all per-phase `client_requests_*.csv` files, `resource_stats.csv`,
    `per_node_stats.csv`, `container_events.csv`, both controller logs,
    `service_logs/`, and `phases_snapshot.json`.
- Artifact status: the full run folder was copied back locally to
  `source/scripts/testing/metrics/20260524_013746_hybrid_observation_current_code`.
  Local post-run analysis produced:
  - `analysis/recovery_validation_summary.md`
  - `analysis/recovery_validation_fault_windows.csv`
  - `analysis/recovery_validation_request_lease_outcomes.csv`
  - `run_summary.md`
  - `latency_summary.csv`
  - `resource_summary.csv`
  - `elasticity_events.csv`
  - `node_lifecycle_timings.csv`
- Remote retention status: the cloud copy was deleted after the dedicated
  `cleanup_metrics` target was added to the approved non-interactive make path.
- Interpretation:
  - the long-cycle request stream remained broadly stable: 21 non-200
    responses out of 63,431 total requests, or 0.03% overall. Non-200s first
    appeared in `cross_region_hotspot` and stayed low through the remaining
    phases.
  - dynamic compute scaling was active and cleaned up cleanly. Container events
    recorded 11 dynamic `edge_server` additions and 11 removals, parsed
    controller timings show compute nodes reaching ready in 1.15 s to 2.29 s
    and cleaning up in 0.45 s to 1.45 s, `server_count` peaked at 3, and
    `storage_count` stayed fixed at 1.
  - no dynamic storage or Tier 1 selective-sync activity was observed.
  - the heaviest request latency appeared in `compute_spike`
    (mean 69.18 ms, p95 158.81 ms) and `sustained_plateau`
    (mean 59.14 ms, p95 127.48 ms). `lan2` carried the heavier overall request
    latency profile, with mean 69.04 ms and p95 144.00 ms, versus `lan1` at
    27.96 ms mean and 72.50 ms p95, but failure rates remained negligible on
    both LANs.
  - recovery validation again showed only `success_normal` request-lease
    outcomes (`lan1=44082`, `lan2=40242`) with `success_after_rebind=0`,
    `failure_terminal=0`, and controller avoidance/fallback markers still at 0.
  - together with `n1` and `n2`, this indicates that the current-code
    architecture remains stable under both targeted and long-cycle
    observation-only traffic, but this campaign still does not validate the
    failed-backend-avoidance branch under natural workload conditions.
- Next action: if the next campaign must validate the avoidance branch rather
  than confirm no-regression behavior, run a follow-up workload with stronger
  natural backend churn or a separately authorized controlled-failure campaign.

## Completed One-Off Run - Hybrid Recovery Validation n1

- Status: completed.
- Objective: launch the first short targeted hybrid observation run for the
  current request-lease implementation, using the `n1` phase recipe to inspect
  request-lease outcomes, failure-rate behavior, and any naturally occurring
  controller recovery markers without synthetic fault injection.
- Intended delta versus the latest long-cycle current-code references:
  - use the short targeted profile in
    `source/scripts/testing/phases_experiment_hybrid_validation_n1.json`
    instead of the standard long-cycle `phases.json` schedule.
  - do not pass `--fault-plan`; this run is observation-only.
  - sync the current local runtime-bearing surfaces required by this run:
    `source/docker/edge_server/source/`,
    `source/scripts/Makefile`,
    `source/scripts/testing/run_experiment.sh`,
    `source/scripts/testing/traffic_generator.py`,
    `source/scripts/testing/device_registry.py`,
    `source/scripts/testing/create_indexes.py`,
    `source/scripts/testing/phases_experiment_hybrid_validation_n1.json`, and
    `source/sdn_controller/vip_routing.py`.
- Rebuild policy:
  - rebuild `edge_server` on `cloud-vm` before launch because the remote VM is
    missing the new request-lease runtime files under
    `source/docker/edge_server/source/`.
  - do not rebuild `osken-controller`; controller code remains bind-mounted.
  - do not rebuild `edge_storage_server`; this run does not require a baked
    storage-runtime change.
- `sudo -n` preflight:
  - generic `sudo -n true` is still blocked on `cloud-vm`.
  - the required path is permitted: a dry-run of
    `sudo -n make -C source/scripts -n setup_network create_clients
    setup_test_data run_experiment RUN_LABEL=hybrid_validation_n1
    PHASES_CONFIG=testing/phases_experiment_hybrid_validation_n1.json
    SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1` completed without prompting.
- Run label: `hybrid_validation_n1`.
- Primary comparisons:
  - compare against the forthcoming `hybrid_validation_n2` run to detect any
    directional asymmetry between `lan2 -> lan1` and `lan1 -> lan2` targeted
    pressure.
  - compare against
    `20260517_090203_two_regime_1680_full_recreate` as the nearest current-code
    long-cycle architecture reference, while treating the phase schedule as a
    different workload family.
- Launch command:
  `ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios; sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment RUN_LABEL=hybrid_validation_n1 PHASES_CONFIG=testing/phases_experiment_hybrid_validation_n1.json SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1"`.
- Live checkpoint plan: passive monitoring only. Use read-only checks against
  the active run folder, `current_phase.txt`, `resource_stats.csv`,
  `container_events.csv`, controller logs, and `service_logs/`. Continue unless
  setup fails before useful traffic, the allowed `sudo -n make` path fails, or
  the run clearly stops progressing.
- Checkpoint question: does the short `n1` targeted observation produce the
  expected request-lease outcome logging and any recovery-side controller
  markers under natural workload conditions, while keeping latency and failure
  behavior interpretable enough for comparison with the later `n2` run?
- Agent authority: full autonomous authority within the experiment-runner
  contract for this run. The runner may sync the listed surfaces, rebuild
  `edge_server`, launch with the verified `sudo -n make -C source/scripts`
  path, monitor passively, copy artifacts back locally, and update this brief
  after completion.
- Result: completed as `20260524_004416_hybrid_validation_n1`.
- Completion evidence:
  - the remote run folder reached `current_phase.txt=idle`.
  - the traffic generator completed all four phases: `warmup`,
    `storage_stress_n1`, `hotspot_n1`, and `cooldown`.
  - the run emitted the expected artifact set including `client_requests.csv`,
    `resource_stats.csv`, `per_node_stats.csv`, both controller logs,
    `container_events.csv`, `service_logs/`, and `phases_snapshot.json`.
- Artifact status: the full run folder was copied back locally to
  `source/scripts/testing/metrics/20260524_004416_hybrid_validation_n1`.
  Local post-run analysis produced:
  - `analysis/recovery_validation_summary.md`
  - `analysis/recovery_validation_fault_windows.csv`
  - `analysis/recovery_validation_request_lease_outcomes.csv`
- Remote retention status: the cloud copy was deleted after the dedicated
  `cleanup_metrics` target was added to the approved non-interactive make path.
- Interpretation:
  - no explicit fault events were recorded, as intended for this observation-
    only run.
  - request-lease outcomes were entirely `success_normal` in the generated
    recovery summary: `lan1=14041`, `lan2=8776`, with
    `success_after_rebind=0` and `failure_terminal=0` on both LANs.
  - controller recovery markers were absent: `avoidance=0`, `fallback=0`.
  - this means the targeted `n1` workload completed cleanly, but it did not
    naturally force a recovery path strongly enough to exercise the
    failed-backend-avoidance branch.
- Next action: run the mirrored `hybrid_validation_n2` observation with the
  same synced code and image state, then compare the two targeted runs before
  deciding whether the long-cycle observation rerun is still the right next
  step or whether a stronger non-synthetic recovery trigger is needed.

## Completed One-Off Run - Two-Regime Full Recreate Rerun

- Status: completed.
- Objective: rerun the long-cycle two-regime workload under the same current
  controller policy, but recreate clients and test data from scratch so the
  updated `device_registry.py` seeding logic is actually exercised.
- Intended delta versus `20260516_235859_two_regime_1680_seed_profiles`:
  - keep the synced testing inputs unchanged:
    - `source/scripts/testing/phases.json`
    - `source/scripts/testing/device_registry.py`
  - keep runtime container code and controller code unchanged.
  - keep the current controller env unchanged:
    `SS_ENABLED=1`, `MAX_DYNAMIC_STORAGE=5`, `MAX_DYNAMIC_COMPUTE=2`, and
    `SCALEUP_COMPUTE_BASE_THRESHOLD=0.25`.
  - override all skip defaults so the run recreates clients, reseeds test
    data, and regenerates the snapshot: `SKIP_CLIENTS=0`, `SKIP_SEED=0`, and
    `SKIP_SNAPSHOT=0`.
- Rebuild policy: do not rebuild images before this run. No runtime image
  sources changed since `20260516_235859_two_regime_1680_seed_profiles`, and
  the required images are already present on `cloud-vm`.
- Between-run harness fix: `source/scripts/testing/run_experiment.sh` was
  updated and synced to `cloud-vm` so `run_create_clients()` checks whether
  `network/clients/create_test_clients.sh` exists instead of incorrectly
  requiring the executable bit, which previously caused the first full-recreate
  attempt to fail even though the helper is invoked through `bash`.
- Pre-run sync validation:
  - local and remote SHA256 match for both `source/scripts/testing/phases.json`
    and `source/scripts/testing/device_registry.py`.
- `sudo -n` preflight:
  - generic `sudo -n true` is not permitted on `cloud-vm`.
  - the required command path is permitted: a dry-run of
    `sudo -n make -C source/scripts -n setup_network create_clients
    setup_test_data run_experiment RUN_LABEL=two_regime_1680_full_recreate
    SKIP_CLIENTS=0 SKIP_SEED=0 SKIP_SNAPSHOT=0` completed without prompting
    for a password.
- Workload/profile: reuse the same 1680-second 9-phase two-regime profile from
  `source/scripts/testing/phases.json`:
  `60/90/240/300/300/120/150/120/300` seconds for `baseline`,
  `local_moderate`, `storage_stress`, `cross_region_hotspot`,
  `reverse_hotspot`, `compute_ramp`, `compute_spike`,
  `sustained_plateau`, and `demand_drop`.
- Seeding/profile delta: reseed `device_registry` from scratch with the new
  `focused_local`, `regional_operator`, and `global_operator` node-profile
  families so the updated dashboard fan-out distribution is actually present in
  the run.
- Run label: `two_regime_1680_full_recreate`.
- Primary comparisons:
  - compare against `20260516_235859_two_regime_1680_seed_profiles` to isolate
    the effect of recreating clients and actually exercising the new seeded
    node-profile mix.
  - compare against `20260516_215213_regular_900_epoch_rotation_current_code_rerun`
    as the nearest current-code regular reference.
- Launch command: `ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios &&
  sudo -n make -C source/scripts setup_network create_clients
  setup_test_data run_experiment RUN_LABEL=two_regime_1680_full_recreate
  SKIP_CLIENTS=0 SKIP_SEED=0 SKIP_SNAPSHOT=0"`.
- Live checkpoint plan: passive monitoring only. Use read-only checks against
  `current_phase.txt`, `resource_stats.csv`, `per_node_stats.csv`,
  `container_events.csv`, controller logs, and `service_logs/` after the run
  folder appears. Continue unless the allowed `sudo -n make` path fails, setup
  fails before useful traffic, or the run clearly stops progressing.
- Checkpoint question: does the same two-regime profile, once clients and seed
  data are recreated from scratch, still produce storage elasticity and a
  dashboard-led compute pressure region, and does the new seeded profile mix
  alter the compute-elasticity outcome?
- Agent authority: full autonomous authority within the experiment-runner
  contract for this run. The runner may launch with the verified
  `sudo -n make -C source/scripts` path, monitor passively, summarize and trim
  the completed run folder when controller logs are no longer needed, copy
  artifacts back locally, and update this brief after completion.
- Result: completed as `20260517_090203_two_regime_1680_full_recreate`.
- Completion evidence:
  - the no-skip launch recreated both LAN client namespaces.
  - `sensor_reports.py`, `device_registry.py`, `create_indexes.py`, and
    `export_workload_snapshot.py` all ran during setup.
  - the run folder reached `current_phase.txt=idle` and no experiment process
    remained active after completion.
- Artifact status: the full run folder was copied back locally to
  `source/scripts/testing/metrics/20260517_090203_two_regime_1680_full_recreate`.
  The local copy includes `client_requests.csv`, `resource_stats.csv`, both
  controller logs, `phases_snapshot.json`, and `service_logs/`.
- Remote retention status: the cloud copy remains in place for now. Raw
  controller logs were retained because post-run analysis and trimming have not
  been executed yet.
- Interpretation: the requested full recreate rerun finished successfully and
  did exercise fresh client recreation, fresh seeding, and snapshot
  regeneration. Comparison against the prior skip-based two-regime run still
  remains to be analyzed.
- Checkpoint question: does the storage regime still produce the expected
  cross-region pressure and Tier 2 behavior, while the compute regime produces
  clearer dashboard-led edge-server CPU pressure and, potentially, natural
  compute lifecycle evidence under the unchanged controller env?
- Agent authority: full autonomous authority within the experiment-runner
  contract for this run. The runner may sync the listed testing surfaces,
  launch with the verified `sudo -n make -C source/scripts` path, monitor
  passively, summarize and trim the completed run folder when controller logs
  are no longer needed, copy artifacts back locally, and update this brief
  after completion.
- Result: completed as
  `20260516_235859_two_regime_1680_seed_profiles`.
- Artifact status: the run folder was copied back locally to
  `source/scripts/testing/metrics/20260516_235859_two_regime_1680_seed_profiles`.
  Local post-run analysis produced `run_summary.md`, `latency_summary.csv`,
  `resource_summary.csv`, `elasticity_events.csv`,
  `node_lifecycle_timings.csv`, and the `analysis/` plots. After the summary
  was written, the local folder was trimmed by deleting only the per-phase
  `client_requests_*.csv` files and raw controller logs.
- Remote retention status: the extra user-owned cloud copy used for local
  copy-back was deleted after verification. The original root-owned run folder
  under `~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/`
  remains on `cloud-vm` because autonomous deletion is still blocked outside
  the permitted `sudo -n make -C source/scripts ...` path.
- Interpretation: this run is a valid two-regime phase-profile result. It
  makes the storage-regime versus compute-regime distinction clearer than the
  earlier blended workload, and it exposes a large dashboard-led `503` region
  without any compute-node add event under the unchanged controller policy.
  However, because the launch still used `SKIP_SEED=1`, it is not yet the full
  validation run for the new seeded node-profile families.
- Next action: rerun the same long-cycle profile without `SKIP_SEED=1`, then
  compare the result against this run and against
  `20260516_215213_regular_900_epoch_rotation_current_code_rerun`.

## Timing Artifact Contract

- `node_lifecycle_timings.csv` should be interpreted as `add` (bootstrap),
  `ready` (service admission), and `remove` (scale-down completion).
- Historical timing folders created before the readiness-timing change only
  contain `add` and `remove`; for storage and Tier 1 those older `add` totals
  are bootstrap-completion timings, not ready-to-serve timings.

## Completed One-Off Run - Epoch Hard-Failure Validation Current-Code Rerun

- Status: completed.
- Objective: rerun one regular full-policy 900-second experiment after syncing
  the current modified experiment-code surfaces to `cloud-vm`, so the epoch-
  based hard-failure validation run reflects the latest local code rather than
  only the earlier `edge_server`-only sync.
- Evidence for rerun scope: after `20260516_212524_regular_900_epoch_rotation_rerun`
  completed, local source changes still existed under the following runtime-
  relevant areas:
  - `source/docker/edge_server/`
  - `source/docker/edge_storage_server/`
  - `source/scripts/`
  - `source/sdn_controller/`
- Remote sync scope before rebuild:
  - `source/docker/edge_server/`
  - `source/docker/edge_storage_server/`
  - `source/scripts/` code paths required by the harness, network setup, and
    controller startup, excluding generated `source/scripts/testing/metrics/`
    outputs.
  - `source/sdn_controller/`
- Pre-run image step: rebuilt the runtime-affected images on `cloud-vm` from
  `~/efficient-storage-in-edge-scenarios` with
  `bash source/scripts/build_images.sh edge_server edge_storage_server` after
  the sync completed.
- Workload/profile: keep the restored regular 900-second 9-phase profile used
  by `regular_900_full_scripts_sync_rerun`: `20/40/105/120/120/80/120/90/205`
  seconds for `baseline`, `local_moderate`, `storage_stress`,
  `cross_region_hotspot`, `reverse_hotspot`, `compute_ramp`,
  `compute_spike`, `sustained_plateau`, and `demand_drop`.
- Run label: `regular_900_epoch_rotation_current_code_rerun`.
- Primary comparisons:
  - compare against `20260516_212524_regular_900_epoch_rotation_rerun` to
    isolate the effect of widening the sync from `edge_server` only to the full
    current-code surface.
  - compare against `20260515_112952_regular_900_full_scripts_sync_rerun` as
    the nearest regular 900-second baseline that already includes kept
    controller and service logs.
- Launch command: `ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios &&
  sudo -n make -C source/scripts setup_network create_clients
  setup_test_data run_experiment
  RUN_LABEL=regular_900_epoch_rotation_current_code_rerun SKIP_CLIENTS=1
  SKIP_SEED=1 SKIP_SNAPSHOT=1"`.
- Live checkpoint plan: passive monitoring only. Use read-only checks against
  `current_phase.txt`, `resource_stats.csv`, `container_events.csv`,
  controller logs, and `service_logs/edge_server_*.log` to confirm the run is
  progressing and to capture any epoch-rotation or request-scoped DB failure
  evidence if storage-path failures occur naturally. Continue unless `sudo -n`
  fails, setup fails before useful traffic, or the run clearly stops
  progressing.
- Agent authority: full autonomous authority within the
  `experiment-runner-edge.agent.md` contract. The runner may sync the listed
  scope, rebuild images, launch with `sudo -n`, monitor passively, summarize
  and trim the run folder, copy artifacts back locally, and update this brief
  after completion without further approval.
- Pre-run sync validation: representative local-vs-remote SHA256 checks matched
  for `source/docker/edge_server/source/app.py`,
  `source/docker/edge_storage_server/entrypoint.sh`,
  `source/scripts/testing/run_experiment.sh`, and
  `source/sdn_controller/main_n1.py` after the broadened sync.
- Result: completed as
  `20260516_215213_regular_900_epoch_rotation_current_code_rerun`.
  The remote wrapper finished with `Experiment complete` and reported both kept
  controller logs and `service_logs/`.
- Artifact status: the full run folder was copied back locally to
  `source/scripts/testing/metrics/20260516_215213_regular_900_epoch_rotation_current_code_rerun`.
  Local verification confirmed `current_phase.txt=idle` and a populated
  `service_logs/` directory containing `edge_server_n1.log`,
  `edge_server_n2.log`, `edge_storage_server_n1.log`,
  `edge_storage_server_n2.log`, and dynamic node logs.
- Remote retention status: the cloud copy could not be deleted autonomously
  after copy-back because non-interactive cleanup again failed under
  `sudo -n`.
- Interpretation: this run is the corrected epoch-validation reference for the
  latest local code surface. Unlike `20260516_212524_regular_900_epoch_rotation_rerun`,
  it includes the current host-side scripts, controller logic, and both runtime
  Docker code paths in addition to the rebuilt `edge_server` image.

## Completed One-Off Run - Epoch Hard-Failure Validation Edge-Server Sync Only

- Status: completed.
- Objective: run one regular full-policy 900-second experiment after syncing
  the updated `source/docker/edge_server/` tree to `cloud-vm` and rebuilding
  only the `edge_server` image, so the standard workload could validate the
  landed epoch-based hard-failure storage lifecycle against the latest kept-log
  regular baseline.
- Remote sync scope before rebuild:
  - `source/docker/edge_server/`
- Pre-run image step: rebuild only the `edge_server` image on `cloud-vm` from
  `~/efficient-storage-in-edge-scenarios` with
  `bash source/scripts/build_images.sh edge_server` after the sync completed.
- Workload/profile: reused the restored regular 900-second 9-phase profile:
  `20/40/105/120/120/80/120/90/205` seconds for `baseline`,
  `local_moderate`, `storage_stress`, `cross_region_hotspot`,
  `reverse_hotspot`, `compute_ramp`, `compute_spike`,
  `sustained_plateau`, and `demand_drop`.
- Run label: `regular_900_epoch_rotation_rerun`.
- Result: completed as `20260516_212524_regular_900_epoch_rotation_rerun`.
  The remote wrapper finished with `Experiment complete` and reported both kept
  controller logs and `service_logs/`.
- Artifact status: the full run folder was copied back locally to
  `source/scripts/testing/metrics/20260516_212524_regular_900_epoch_rotation_rerun`.
  Local verification confirmed `current_phase.txt=idle` and a populated
  `service_logs/` directory containing both `edge_server_*.log` and
  `edge_storage_server_*.log` outputs.
- Interpretation: this run is a valid intermediate reference for the
  `edge_server`-only sync path, but it is not the fully current-code run the
  user requested because local modified code still existed under
  `source/scripts/`, `source/sdn_controller/`, and
  `source/docker/edge_storage_server/` when it launched.

## Completed One-Off Run - Regular 900s Full Scripts Sync Rerun

- Status: completed.
- Objective: rerun one regular full-policy 900-second experiment after syncing
  the `source/scripts/` code-bearing tree and the full
  `source/sdn_controller/` tree to `cloud-vm`, because the previous rebuilt-
  image rerun still used a stale remote host-side experiment harness and
  therefore did not capture per-service edge/storage logs.
- Evidence for rerun scope:
  - local `source/scripts/testing/run_experiment.sh` now includes
    `run_capture_service_logs`, `SERVICE_LOG_DIR`, and the final `Service logs`
    summary line.
  - the copied run folder
    `source/scripts/testing/metrics/20260515_104530_regular_900_rebuild_rerun`
    contains controller logs but no `service_logs/` directory.
  - a direct local-vs-remote SHA256 check after the run showed the VM copy of
    `source/scripts/testing/run_experiment.sh` still differed from local, so
    the remote rerun used an older wrapper even though the images themselves
    had been rebuilt.
- Remote sync scope before rebuild:
  - `source/scripts/` code paths required by the harness and image build,
    excluding generated `source/scripts/testing/metrics/` outputs and the
    existing workload snapshot artifacts.
  - `source/sdn_controller/`
- Pre-rebuild validation:
  - verify remote SHA256 match for `source/scripts/testing/run_experiment.sh`
  - verify remote SHA256 match for
    `source/scripts/testing/capture_service_logs.py`
  - verify remote SHA256 match for at least one representative controller file
    under `source/sdn_controller/`
- Pre-run image step: rebuild the full image set on `cloud-vm` from
  `~/efficient-storage-in-edge-scenarios` with
  `bash source/scripts/build_images.sh` after the sync completes.
- Workload/profile: keep the restored regular 900-second 9-phase profile
  already used by `regular_900_confirm_after_vip_batch` and
  `regular_900_rebuild_rerun`: `20/40/105/120/120/80/120/90/205` seconds for
  `baseline`, `local_moderate`, `storage_stress`, `cross_region_hotspot`,
  `reverse_hotspot`, `compute_ramp`, `compute_spike`, `sustained_plateau`, and
  `demand_drop`.
- Run label: `regular_900_full_scripts_sync_rerun`.
- Primary comparisons:
  - compare against `20260515_104530_regular_900_rebuild_rerun` to isolate the
    effect of the full `scripts` plus `sdn_controller` sync on the same 900 s
    workload.
  - compare against `20260514_191105_regular_900_confirm_after_vip_batch` as
    the earlier regular 900-second post-VIP reference.
- Launch command: `ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios &&
  sudo -n make -C source/scripts setup_network create_clients setup_test_data
  run_experiment RUN_LABEL=regular_900_full_scripts_sync_rerun SKIP_CLIENTS=1
  SKIP_SEED=1 SKIP_SNAPSHOT=1"`.
- Live checkpoint plan: passive monitoring only. Use read-only checks against
  `current_phase.txt`, `client_requests.csv`, `resource_stats.csv`,
  `container_events.csv`, controller logs, and confirm the active run folder
  contains `service_logs/` before copy-back. Continue unless `sudo -n` fails,
  setup fails before useful traffic, or the run clearly stops progressing.
- Artifact handling: keep controller logs and copy the full run folder back
  locally after completion. The local copy is verified; the cloud copy is still
  retained because remote cleanup requires privileged removal and `sudo -n`
  returned `a password is required`.
- Result: completed as `20260515_112952_regular_900_full_scripts_sync_rerun`.
  The wrapper entered the service-log capture path and finished with
  `Experiment complete`.
- Artifact status: the full kept-log run folder was copied back locally to
  `source/scripts/testing/metrics/20260515_112952_regular_900_full_scripts_sync_rerun`.
  Local verification confirmed `current_phase.txt=idle`, both controller logs,
  and a populated `service_logs/` directory.
- Remote retention status: the cloud copy could not be deleted autonomously
  after copy-back because the run folder is root-owned on `cloud-vm` and
  non-interactive cleanup failed with `sudo: a password is required`.
- Restored service-log evidence: the copied `service_logs/` directory contains
  `edge_server_n1.log`, `edge_server_n2.log`, `edge_storage_server_n1.log`,
  `edge_storage_server_n2.log`, and dynamic storage-node logs, confirming that
  the host-side harness sync fixed the missing server/storage log capture.
- Interpretation: the operational objective of this rerun was achieved. The VM
  now ran the current experiment harness and produced the expected per-service
  logs alongside the controller logs. Detailed request-level outcome analysis is
  still pending.

## Completed One-Off Run - Regular 900s Rebuild Rerun

- Status: completed.
- Objective: rerun one regular full-policy 900-second experiment after a fresh
  sync and full image rebuild on `cloud-vm`, because a representative source
  check showed the VM had drifted from the local workspace again.
- Evidence for rerun scope: a local-vs-remote SHA256 spot check found
  `source/docker/edge_server/source/app.py` mismatched while the other sampled
  VIP-routing files still matched. To avoid rebuilding stale remote sources,
  sync the known VIP-routing-related subset again before the rebuild.
- Remote sync scope before rebuild:
  - `source/docker/edge_server/`
  - `source/sdn_controller/`
  - `source/scripts/network/`
  - `source/scripts/osken-controller.env`
- Pre-run image step: rebuild the full image set on `cloud-vm` from
  `~/efficient-storage-in-edge-scenarios` with
  `bash source/scripts/build_images.sh` after the sync completes.
- Workload/profile: keep the restored regular 900-second 9-phase profile
  already used by `regular_900_confirm_after_vip_batch`:
  `20/40/105/120/120/80/120/90/205` seconds for `baseline`,
  `local_moderate`, `storage_stress`, `cross_region_hotspot`,
  `reverse_hotspot`, `compute_ramp`, `compute_spike`,
  `sustained_plateau`, and `demand_drop`.
- Run label: `regular_900_rebuild_rerun`.
- Primary comparisons:
  - compare against `20260514_191105_regular_900_confirm_after_vip_batch` to
    see whether the fresh sync-plus-rebuild changes the failure-heavy regular
    profile outcome.
  - compare against `20260512_075751_short_fullpolicy_rebuild_mongo` as the
    earlier rebuilt-image 900-second reference.
- Launch command: `ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios &&
  sudo -n make -C source/scripts setup_network create_clients setup_test_data
  run_experiment RUN_LABEL=regular_900_rebuild_rerun SKIP_CLIENTS=1
  SKIP_SEED=1 SKIP_SNAPSHOT=1"`.
- Live checkpoint plan: passive monitoring only. Use read-only checks against
  `current_phase.txt`, `client_requests.csv`, `resource_stats.csv`,
  `container_events.csv`, and controller logs. Continue unless `sudo -n` fails,
  setup fails before useful traffic, or the run clearly stops progressing.
- Artifact handling: keep controller logs, copy the full run folder back
  locally after completion, and leave the cloud copy retained unless later
  cleanup is explicitly requested.
- Result: completed as `20260515_104530_regular_900_rebuild_rerun`. The remote
  wrapper reported `9 phases, 900s total, 6 clients` and finished with
  `Experiment complete`.
- Artifact status: the full kept-log run folder was copied back locally to
  `source/scripts/testing/metrics/20260515_104530_regular_900_rebuild_rerun`.
  Both controller logs were kept locally, and the cloud copy was left
  retained.
- Service log capture finding: the run folder did not include `service_logs/`.
  Post-run inspection showed the remote
  `source/scripts/testing/run_experiment.sh` did not match the local workspace,
  so this rerun still used a stale host-side harness that predates the service
  log capture path.
- Interpretation: the full image rebuild did use fresher image sources for the
  synced subset, but it did not refresh the entire remote testing harness.
  That host-side drift is the reason for the missing server/storage log files,
  and it motivates the next full `source/scripts/` plus
  `source/sdn_controller/` sync rerun.

## Completed One-Off Run - Regular 900s Confirmation After VIP Batch

- Status: completed.
- Objective: run one more regular full-policy confirmation after the VIP
  directional mini-batch, using the restored standard 900-second 9-phase
  workload instead of another short directional probe.
- Intended delta: no source or controller-policy changes relative to the lab
  state used for the completed VIP mini-batch. The only delta versus that batch
  is the workload shape: switch back from the 3-phase VIP-routing probes to the
  regular 9-phase profile already restored on `cloud-vm`.
- Rebuild policy: do not rebuild again before this run. The full image set was
  already rebuilt on `cloud-vm` from the synced current source before the VIP
  mini-batch, and no relevant source/config files changed afterward.
- Workload/profile: reuse the restored regular 900-second profile:
  `20/40/105/120/120/80/120/90/205` seconds for `baseline`,
  `local_moderate`, `storage_stress`, `cross_region_hotspot`,
  `reverse_hotspot`, `compute_ramp`, `compute_spike`,
  `sustained_plateau`, and `demand_drop`.
- Run label: `regular_900_confirm_after_vip_batch`.
- Primary comparisons:
  - compare against `20260514_164917_vip_small_all_features` to see whether the
    current synced/rebuilt VIP-routing stack behaves more stably under a normal
    regular workload than under the targeted recovery probe.
  - compare against `20260512_075751_short_fullpolicy_rebuild_mongo` as the
    latest prior 900-second rebuilt-image reference run.
- Launch command: `ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios &&
  sudo -n make -C source/scripts setup_network create_clients setup_test_data
  run_experiment RUN_LABEL=regular_900_confirm_after_vip_batch SKIP_CLIENTS=1
  SKIP_SEED=1 SKIP_SNAPSHOT=1"`.
- Live checkpoint plan: passive monitoring only. Use read-only checks against
  `current_phase.txt`, `client_requests.csv`, `resource_stats.csv`,
  `container_events.csv`, and controller logs. Continue unless `sudo -n` fails,
  setup fails before useful traffic, or the run clearly stops progressing.
- Artifact handling: keep controller logs, copy the full run folder back
  locally after completion, and leave the cloud copy retained unless later
  cleanup is explicitly requested.
- Result: completed as
  `20260514_191105_regular_900_confirm_after_vip_batch` using the restored
  regular 900-second 9-phase workload and the already synced/rebuilt VIP-
  routing-capable lab images.
- Outcome summary: the run did not return to clean regular behavior. Overall
  outcomes were `200=17587`, `503=9429`, and `0=20` from
  `client_requests.csv`.
- Most failure-heavy phases:
  - `reverse_hotspot`: `200=1298`, `503=2465`, `0=2`
  - `compute_ramp`: `200=2354`, `503=1413`, `0=2`
  - `cross_region_hotspot`: `200=1864`, `503=1278`, `0=8`
- Recovery result: `demand_drop` did not recover cleanly. It ended with
  `200=205`, `503=806`, and `0=3`, so low-demand stabilization remained
  failure-heavy instead of returning to a mostly successful tail.
- Interpretation: the current synced/rebuilt VIP-routing stack can complete a
  regular 900-second run, but the instability seen in the VIP mini-batch is not
  confined to the short directional probe. Under the regular profile, the
  system remains substantially failure-prone in the hotspot and later phases,
  with especially poor recovery in `demand_drop`.
- Artifact status: the full kept-log run folder was copied back locally to
  `source/scripts/testing/metrics/20260514_191105_regular_900_confirm_after_vip_batch`.
  Both controller logs were kept locally, and the cloud copy was left retained.

## Completed Mini-Batch - VIP Routing Directional Recovery

- Status: completed.
- Objective: run a 3-run mini-batch that exercises the currently landed VIP
  routing rollout up to Phase 3 only: Phase 1 bounded warm-lease preference,
  Phase 2 one-shot recovery VIP arming, and Phase 3 bounded recovery-session
  lifetime. Do not include the optional failed-backend-avoidance follow-up.
- Approved edit scope: keep repository edits limited to this brief. Change only
  `source/scripts/testing/phases.json` on `cloud-vm` between runs.
- Remote sync prerequisite: the current `cloud-vm` checkout is behind the local
  VIP-routing rollout in the files that wire recovery behavior into the lab
  launch path. Before the batch starts, explicitly sync these local paths to
  `cloud-vm`, then rebuild all images again there:
  - `source/docker/edge_server/`
  - `source/sdn_controller/`
  - `source/scripts/network/`
  - `source/scripts/osken-controller.env`
- Pre-batch image step: before Run 1, rebuild the full image set on
  `cloud-vm` from `~/efficient-storage-in-edge-scenarios` with
  `bash source/scripts/build_images.sh` so the entire lab starts from freshly
  rebuilt images, not just the already-tested storage image.
- Controller policy: keep the active cloud controller/env configuration as-is;
  validate on `cloud-vm` before Run 1 that the current env still exposes the
  landed warm-lease and recovery VIP knobs.
- Primary comparisons:
  - `vip_small_hotspot_n2_to_n1` versus `vip_small_hotspot_n1_to_n2` for
    mirrored directional recovery behavior.
  - `vip_small_all_features` versus the two directional runs for the combined
    short-profile behavior with Phases 1-3 active together.
- Remote mutation rule: before each run, overwrite the VM copy of
  `source/scripts/testing/phases.json`, verify the remote file contents, then
  launch the run from a single remote one-liner. Do not edit repo files while a
  run is active.
- Launch form: `ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo
  -n make -C source/scripts setup_network create_clients setup_test_data
  run_experiment RUN_LABEL=<label> SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1"`.
- Batch start sequence:
  - sync the current local VIP-routing-related source/config files to
    `cloud-vm`
  - rebuild all images once on `cloud-vm`
  - validate the warm/recovery env knobs and back up the current remote
    `phases.json`
  - for each run: overwrite remote `phases.json`, verify it remotely, launch,
    passively monitor, keep logs, and copy the full run folder back locally
- Live checkpoint plan: passive monitoring only. Use read-only checks against
  the active run folder (`current_phase.txt`, `client_requests.csv`,
  `resource_stats.csv`, `container_events.csv`, and controller logs). Continue
  unless `sudo -n` fails, setup fails before useful traffic, or the run clearly
  stops progressing.
- Artifact handling: keep controller logs for all three runs. After each
  completion, copy the full run folder back locally before touching the next VM
  `phases.json` mutation, and leave the cloud copy retained unless the user
  later asks for cleanup.
- Run matrix:
  - `vip_small_hotspot_n2_to_n1`
    - Goal: directional validation of Phase 1 warm-lease preference plus
      Phase 2/3 recovery on the `lan2 -> lan1` hotspot path.
    - Remote `phases.json` profile:
      - `warm_lease_claim`: 45 s, 6.0 req/s/client, `cross_region_ratio=0.45`,
        `hotspot_direction=lan2_to_lan1`, mix `device_status=0.80`,
        `dashboard=0.10`, `service_pressure=0.10`.
      - `recovery_arm`: 90 s, 8.0 req/s/client, `cross_region_ratio=0.85`,
        `hotspot_direction=lan2_to_lan1`, mix `device_status=0.85`,
        `dashboard=0.10`, `service_pressure=0.05`.
      - `recovery_session_tail`: 60 s, 3.0 req/s/client,
        `cross_region_ratio=0.25`, `hotspot_direction=lan2_to_lan1`, mix
        `device_status=0.70`, `dashboard=0.20`, `service_pressure=0.10`.
  - `vip_small_hotspot_n1_to_n2`
    - Goal: mirrored directional validation of the same Phase 1/2/3 behavior
      on the `lan1 -> lan2` hotspot path.
    - Remote `phases.json` profile: same three phases and rates as the first
      run, but every directional phase uses
      `hotspot_direction=lan1_to_lan2`.
  - `vip_small_all_features`
    - Goal: short combined run with the currently landed VIP-routing features
      active together, limited to Phases 1-3.
    - Remote `phases.json` profile:
      - `phase1_warm_preference`: 45 s, 6.0 req/s/client,
        `cross_region_ratio=0.45`, `hotspot_direction=lan2_to_lan1`, mix
        `device_status=0.80`, `dashboard=0.10`, `service_pressure=0.10`.
      - `phase2_recovery_arm`: 75 s, 8.0 req/s/client,
        `cross_region_ratio=0.85`, `hotspot_direction=lan2_to_lan1`, mix
        `device_status=0.85`, `dashboard=0.10`, `service_pressure=0.05`.
      - `phase3_recovery_mirror`: 75 s, 8.0 req/s/client,
        `cross_region_ratio=0.85`, `hotspot_direction=lan1_to_lan2`, mix
        `device_status=0.85`, `dashboard=0.10`, `service_pressure=0.05`.
- Preparation outcome: the first VM rebuild exposed that `cloud-vm` was behind
  the local VIP-routing rollout. The required source/config subset was synced
  to `cloud-vm`, then the full image set was rebuilt again before Run 1. The
  original VM `phases.json` was backed up to
  `source/scripts/testing/phases.pre_vip_batch_latest.json` and restored after
  the batch completed.
- Completed runs:
  - `20260514_163624_vip_small_hotspot_n2_to_n1`: completed. The warm phase
    stayed clean at `200`, the `recovery_arm` phase produced repeated `503`
    responses mainly on the `lan2` clients while `lan1` stayed mostly healthy,
    and the tail phase partially recovered but still showed some late `503` and
    `0` statuses.
  - `20260514_164304_vip_small_hotspot_n1_to_n2`: completed. The mirrored run
    showed the same directional pattern in reverse: repeated `503` responses in
    `recovery_arm` mainly on the `lan1` clients, followed by stronger recovery
    toward mostly `200` responses in the tail phase.
  - `20260514_164917_vip_small_all_features`: completed. The combined
    Phase 2 segment became broadly `503`-heavy across both directions, while
    the mirrored Phase 3 segment recovered toward predominantly `200`
    responses by the second half of the phase.
- Artifact status: all three full run folders were copied back locally with
  controller logs kept, and the cloud copies were left retained. Local folders:
  `source/scripts/testing/metrics/20260514_163624_vip_small_hotspot_n2_to_n1`,
  `source/scripts/testing/metrics/20260514_164304_vip_small_hotspot_n1_to_n2`,
  and `source/scripts/testing/metrics/20260514_164917_vip_small_all_features`.

## Completed One-Off Run - MongoDB Image Rebuild Rerun

- Status: completed.
- Objective: rerun the active short full-policy experiment after rebuilding the
  `edge_storage_server` MongoDB image on `cloud-vm`, so the run definitely uses
  the latest storage-image code before comparison against the prior kept-log
  baseline.
- Intended delta: keep the same active cloud workload and controller policy as
  `20260511_225303_normal_keep_controller_logs`, but insert an explicit remote
  storage-image rebuild before `setup_network`.
- Workload/profile delta: no workload or controller-knob changes relative to
  `20260511_225303_normal_keep_controller_logs`; this rerun still uses the
  shortened 900-second `phases.json` profile and the controller snapshot with
  `SS_ENABLED=1`, `MAX_DYNAMIC_STORAGE=5`, `MAX_DYNAMIC_COMPUTE=2`, and
  `SCALEUP_COMPUTE_BASE_THRESHOLD=0.25`.
- Comparison target: compare mainly against
  `20260511_225303_normal_keep_controller_logs`, noting that both runs use the
  same shortened profile and threshold even though the earlier label says
  `normal`.
- Run label: `short_fullpolicy_rebuild_mongo`.
- Remote build step: `sudo -n bash source/scripts/build_images.sh
  edge_storage_server` was not permitted on `cloud-vm` because that extra sudo
  path still prompts for a password. The fallback non-sudo build command
  `bash source/scripts/build_images.sh edge_storage_server` succeeded because
  the remote user already had Docker access.
- Launch command: from `cloud-vm`, run `cd ~/efficient-storage-in-edge-scenarios`
  then `sudo -n make -C source/scripts setup_network create_clients
  setup_test_data run_experiment RUN_LABEL=short_fullpolicy_rebuild_mongo
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1`.
- Live checkpoint outcome: passive monitoring only. The active run folder was
  `source/scripts/testing/metrics/20260512_075751_short_fullpolicy_rebuild_mongo`.
  Read-only checks confirmed phase progression through all 9 phases and final
  completion with `current_phase.txt=idle`.
- Result: the rebuild completed successfully, the experiment completed cleanly,
  and the run produced the full request CSV set plus `resource_stats.csv`,
  `per_node_stats.csv`, `container_events.csv`, and both controller logs.
- Key evidence: Docker rebuilt `edge_storage_server:latest` on `cloud-vm`, the
  experiment wrapper printed all phases through `demand_drop`, and the run
  ended with the standard `Experiment complete` summary for the rebuilt-image
  folder.
- Artifact status: the full run folder was copied back locally to
  `source/scripts/testing/metrics/20260512_075751_short_fullpolicy_rebuild_mongo`
  without trimming. Controller logs were explicitly kept: local sizes are about
  50 MB for `controller_lan1.log` and 180 MB for `controller_lan2.log`. The
  cloud copy also remains retained, untrimmed, at about 227 MB because the
  controller logs are still needed.
- Next recommended action: compare rebuilt-image behavior against
  `20260511_225303_normal_keep_controller_logs`, focusing on storage readiness,
  phase-level failure concentration, and any lifecycle or elasticity deltas now
  that the storage image was rebuilt immediately before launch.

## Completed One-Off Run - Short Readiness Timing Validation

- Status: completed.
- Objective: run one short full-policy timing experiment to collect fresh
  `ready` rows from the readiness-timing instrumentation, because the earlier
  timing CSVs were produced before the readiness boundary existed.
- Workload delta: `source/scripts/testing/phases.json` keeps the same phase
  order, rates, mixes, and hotspot directions, but phase durations are shortened
  to 20/40/105/120/120/80/120/90/205 seconds for a 900-second traffic window,
  about 15 minutes before setup and teardown overhead.
- Controller knobs: keep the current timing-calibration policy:
  `SS_ENABLED=1`, `MAX_DYNAMIC_STORAGE=5`, `MAX_DYNAMIC_COMPUTE=2`, and
  `SCALEUP_COMPUTE_BASE_THRESHOLD=0.25`.
- Run label: `short_ready_timing_s5`.
- Primary question: do the updated controller logs produce real storage,
  Tier 1, and any compute `operation=ready` rows in `node_lifecycle_timings.csv`
  under a roughly 15-minute full-policy run?
- Timing artifacts: keep controller logs until `elasticity_events.csv` and
  `node_lifecycle_timings.csv` are generated with the updated parser, then
  retain those CSVs when raw logs are trimmed.
- Launch command: from `cloud-vm`, run `cd ~/efficient-storage-in-edge-scenarios`
  then `sudo -n make -C source/scripts setup_network create_clients
  setup_test_data run_experiment RUN_LABEL=short_ready_timing_s5
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1`.
- Live checkpoint: passive monitoring only after launch. Continue unless setup
  fails before useful traffic, `sudo -n` fails, or the run clearly stops
  progressing with no useful timing evidence. After completion, analyze through
  a writable `/tmp` snapshot if the original run folder is root-owned.
- Result: completed as `20260510_231710_short_ready_timing_s5` and analyzed
  through a writable snapshot copied locally to
  `source/scripts/testing/metrics/20260510_231710_short_ready_timing_s5_analysis`.
  The run used the intended 900-second phase profile and reached `idle`.
- Timing evidence: the updated parser retained 22 timing rows. Tier 1 produced
  3 `operation=ready` rows with `ready_source=tier1_active`, total 1.28-2.21 s
  and median 1.44 s. Storage produced bootstrap add/remove rows but 0
  `operation=ready` rows. Compute produced no lifecycle rows.
- Storage readiness interpretation: all 7 dynamic storage containers reached
  the controller's online/deferred point with "VIP deferred until SECONDARY",
  but the logs contained no `rs_secondary_ready` or `telemetry_secondary`
  readiness signal. Per-node telemetry for those dynamic storage MACs reported
  `member_state=PRIMARY`, so the current readiness boundary never admitted
  storage as ready-to-serve.
- Traffic/resource result: storage scaled to 3 observed backends, `server_count`
  stayed 1.0, and no `ComputeAlert` appeared. Stress phases had substantial
  503 failures, while `demand_drop` returned to 0 failures.
- Next recommended action: inspect whether dynamic storage should be considered
  ready on `PRIMARY` telemetry in this topology, or whether the replica-set join
  path should produce SECONDARY members. After fixing or clarifying that
  boundary, run another short readiness-timing validation if storage
  ready-to-serve timing is still required.
- Artifact status: raw controller logs and per-phase request CSVs were trimmed
  from the copied analyzed folder after generating `elasticity_events.csv` and
  `node_lifecycle_timings.csv`. The temporary `/tmp` analysis snapshot was
  deleted after local verification. The original cloud run folder remains
  retained because it is root-owned.

## Completed One-Off Run - Compute Timing Threshold Calibration

- Status: completed.
- Objective: run one timing-only full-policy calibration to force compute
  elasticity far enough to capture compute add/remove rows in
  `node_lifecycle_timings.csv`, while retaining dynamic storage and Tier 1
  timing evidence for comparison.
- Workload delta: keep the longer timing workload already in
  `source/scripts/testing/phases.json`: durations
  30/60/180/210/210/150/240/180/300 seconds, with compute-phase rates
  `compute_ramp=14`, `compute_spike=24`, and `sustained_plateau=16` requests
  per client.
- Controller knobs: `SS_ENABLED=1`, `MAX_DYNAMIC_STORAGE=5`,
  `MAX_DYNAMIC_COMPUTE=2`, and timing-only
  `SCALEUP_COMPUTE_BASE_THRESHOLD=0.25` instead of the normal 0.38.
- Run label: `fast_full_timing_s5_compute_threshold25`.
- Primary question: does lowering only the compute scale-up threshold produce
  dynamic compute add/remove timing rows, and how do those timings compare with
  the already observed storage and Tier 1 timings?
- Timing artifacts: keep controller logs until `elasticity_events.csv` and
  `node_lifecycle_timings.csv` are generated; retain those CSVs when raw logs
  are trimmed.
- Launch command: from `cloud-vm`, run `cd ~/efficient-storage-in-edge-scenarios`
  then `sudo -n make -C source/scripts setup_network create_clients
  setup_test_data run_experiment RUN_LABEL=fast_full_timing_s5_compute_threshold25
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1`.
- Live checkpoint: passive monitoring only after launch, using
  `current_phase.txt`, `container_events.csv`, `resource_stats.csv`,
  `per_node_stats.csv`, and controller logs. Continue unless setup fails before
  useful traffic, `sudo -n` fails, or the run clearly stops progressing with no
  useful timing evidence. If the SSH wrapper disconnects but all scale-up
  phases exist, analyze a writable snapshot as in the prior timing runs.
- Result: completed as `20260510_205533_fast_full_timing_s5_compute_threshold25`
  and analyzed through a writable snapshot copied to
  `source/scripts/testing/metrics/20260510_205533_fast_full_timing_s5_compute_threshold25_analysis`.
  The run reached `idle`, generated all phase request CSVs, and retained
  `elasticity_events.csv` plus `node_lifecycle_timings.csv` before raw
  controller logs were trimmed from the copied snapshot.
- Timing evidence: dynamic storage add total was 1.30-3.62 s across 11 rows,
  storage remove total was 2.79-19.72 s across 9 rows, Tier 1 add total was
  2.39-2.42 s across 2 rows, and Tier 1 remove total was 1.01-1.17 s across
  2 rows. No compute timing rows were produced.
- Compute interpretation: the calibration used
  `SCALEUP_COMPUTE_BASE_THRESHOLD=0.25`, `SCALEUP_REQUIRED=3`, and
  `MAX_DYNAMIC_COMPUTE=2`. Offline score reconstruction found 2
  above-threshold windows in `compute_ramp` and 6 in `compute_spike`, with max
  score about 0.302, but controller logs had no `ComputeAlert` or compute-scale
  marker and `server_count` stayed 1.0. Another guard, consecutive-window
  mismatch, decision-path issue, or logging gap is likely preventing compute
  alerts.
- Next recommended action: inspect the compute scale-up decision path and add
  targeted logging around score calculation, consecutive-window qualification,
  cooldowns, and max-node guards before running another compute timing
  calibration. If the goal is purely timing capture, explicitly discuss lowering
  the threshold further or relaxing `SCALEUP_REQUIRED` for one documented
  calibration run.
- Artifact status: the reduced analyzed copy is local. The original cloud run
  folder remains root-owned; the temporary writable `/tmp` snapshot should be
  removed after local verification if it has not already been deleted.

## Completed One-Off Run - Longer Full-Policy Node Timing

- Status: completed with wrapper-disconnect caveat.
- Objective: rerun the full-policy timing experiment with longer scale-up
  windows and stronger compute-phase load so dynamic storage, Tier 1
  selective-sync, and compute add/remove timings can all be captured in
  `node_lifecycle_timings.csv`.
- Workload delta: `source/scripts/testing/phases.json` keeps the standard phase
  order and non-compute request mixes, but durations are lengthened to
  30/60/180/210/210/150/240/180/300 seconds. Compute-sensitive rates are raised
  to `compute_ramp=14`, `compute_spike=24`, and `sustained_plateau=16` requests
  per client to push the compute score above the full-policy threshold.
- Controller knobs: `SS_ENABLED=1`, `MAX_DYNAMIC_STORAGE=5`,
  `MAX_DYNAMIC_COMPUTE=2`.
- Run label: `fast_full_timing_s5_long_compute`.
- Primary question: do dynamic storage, Tier 1, and compute all produce exact
  add/remove timing rows when the workload gives each scale-up path enough time
  and stronger compute pressure?
- Timing artifacts: keep controller logs until `elasticity_events.csv` and
  `node_lifecycle_timings.csv` are generated; retain those CSVs when raw logs
  are trimmed.
- Launch command: from `cloud-vm`, run `cd ~/efficient-storage-in-edge-scenarios`
  then `sudo -n make -C source/scripts setup_network create_clients
  setup_test_data run_experiment RUN_LABEL=fast_full_timing_s5_long_compute
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1`.
- Live checkpoint: passive monitoring only after launch, using
  `current_phase.txt`, `container_events.csv`, `resource_stats.csv`,
  `per_node_stats.csv`, and controller logs. Continue unless setup fails before
  useful traffic, `sudo -n` fails, or the run clearly stops progressing with no
  useful timing evidence.
- Result: launched as `20260510_191740_fast_full_timing_s5_long_compute` and
  analyzed through a writable snapshot copied to
  `source/scripts/testing/metrics/20260510_191740_fast_full_timing_s5_long_compute_analysis`.
  The SSH-bound experiment wrapper disconnected after the run had entered
  `demand_drop`; all scale-up phases produced request CSVs, but final
  demand-drop cleanup convergence is caveated.
- Timing evidence: dynamic storage add total was 1.09-3.45 s across 9 rows,
  storage remove total was 6.76-26.93 s across 6 rows, Tier 1 add total was
  1.33-2.52 s across 3 rows, and Tier 1 remove total was 1.31-2.39 s across
  3 rows. No compute timing rows were produced.
- Compute interpretation: stronger compute phases increased the estimated
  compute score to about 0.325 in `compute_spike`, but the score remained below
  the 0.38 threshold for all windows. To collect compute add/remove timings,
  the next run should be a timing-only calibration that relaxes compute scale-up
  sensitivity, for example `SCALEUP_COMPUTE_BASE_THRESHOLD=0.25`, while keeping
  `MAX_DYNAMIC_COMPUTE=2`.
- Cleanup caveat: the temporary writable analysis snapshot under `/tmp` was
  deleted after local copy-back. The original cloud run folder remains
  root-owned, and orphan `collect_resource_stats.py` / `poll_container_events.py`
  processes tied to this run could not be stopped by the non-root user
  (`Operation not permitted`); treat them as stale idle collectors, not as an
  active traffic generator.

## Completed One-Off Run - Fast Full-Policy Node Timing

- Status: completed.
- Objective: run one shortened full-policy cloud experiment to collect precise
  node add/remove timing evidence under higher dynamic storage pressure.
- Workload delta: `source/scripts/testing/phases.json` keeps the standard phase
  order and request mixes, but durations are shortened to 20/30/75/90/90/45/60/45/240
  seconds so the run completes in about 12 minutes while retaining a long
  demand-drop window for scale-down.
- Controller knobs: `SS_ENABLED=1`, `MAX_DYNAMIC_STORAGE=5`,
  `MAX_DYNAMIC_COMPUTE=2`.
- Run label: `fast_full_timing_s5`.
- Primary question: how long do dynamic Tier 2 storage, Tier 1 selective-sync,
  and any compute nodes take to add and remove, and do timings differ under the
  full policy with more storage headroom?
- Timing artifacts: controller logs are kept until
  `elasticity_events.csv` and `node_lifecycle_timings.csv` are generated from
  `parse_elasticity_logs.py`; those CSVs must be retained when
  `metrics-run-summary` trims raw logs.
- Launch command: from `cloud-vm`, run `cd ~/efficient-storage-in-edge-scenarios`
  then `sudo -n make -C source/scripts setup_network create_clients setup_test_data
  run_experiment RUN_LABEL=fast_full_timing_s5 SKIP_CLIENTS=1 SKIP_SEED=1
  SKIP_SNAPSHOT=1`.
- Live checkpoint: after launch, monitor read-only progress through
  `current_phase.txt`, `container_events.csv`, `resource_stats.csv`, and
  controller logs. Continue unless setup fails before useful traffic, `sudo -n`
  fails, or the run clearly stops progressing with no useful timing evidence.
- Result: completed as `20260510_182921_fast_full_timing_s5`. The retained
  timing CSV captured dynamic storage and Tier 1 selective-sync timing, but no
  compute timing because no dynamic compute lifecycle occurred. Storage add
  total was 1.97-2.78 s, storage remove total was 3.52-20.74 s, Tier 1 add
  total was 1.61-2.33 s, and Tier 1 remove total was 1.56-1.98 s.
- Compute interpretation: the compute cap was enabled, but the estimated
  compute scale-up score peaked at about 0.231 in `compute_spike`, below the
  0.38 threshold for all windows. A second timing run needs longer scale-up
  phases and likely stronger compute load or a deliberate timing-only compute
  threshold relaxation if compute add/remove timings are required.
- Artifact status: analyzed through a writable cloud snapshot because the
  original cloud run folder is root-owned and arbitrary `sudo -n chown` is not
  permitted. The reduced analyzed folder was copied locally to
  `source/scripts/testing/metrics/20260510_182921_fast_full_timing_s5_analysis`;
  the original root-owned cloud run remains retained as a cleanup caveat.

Use this file as the durable working context for successive experiment runs in
this repository.

- Update it before launching a new run when the objective, run delta, or
  allowed edit scope changes.
- Update it after each completed run summary.
- Do not edit it during an active run unless you are recording a stop or
  restart decision after the run has already been halted.
- Unless requested otherwise, after every completed cloud run use the
  `metrics-run-summary` skill for the created metrics folder, summarize
  remotely when controller logs are no longer needed, then copy the remaining
  run folder back to the local host.

## Campaign

- Name: Elasticity ablation batch 5 normal-workload cloud run
- Status: completed
- Objective: Run the Batch 5 matrix from
  `docs/operation/archive/testing/elasticity_ablation_batch5_plan.md` on `cloud-vm`
  using the unchanged standard workload in `source/scripts/testing/phases.json`
  to validate the post-Batch-4 storage scale-up path, Tier 1 interaction, and
  natural compute elasticity opportunity under `MAX_DYNAMIC_COMPUTE=2`.
- Hypothesis: The post-change static run should remain comparable to the
  Batch 4 control; the updated Tier 2 path should scale faster or more cleanly
  than the Batch 4 storage-enabled runs; Tier 1 may still reduce hotspot pain
  but can add lifecycle and reconfigure noise; and the normal workload may or
  may not naturally trigger compute elasticity even with a cap of `2`.
- Primary decision question: Under the unchanged normal workload, do the staged
  storage, Tier 1, and compute-drain changes improve service quality or cleanup
  convergence relative to the Batch 4 references, and does compute elasticity
  activate naturally at cap `2`?

## Remote Execution Context

- VM entry: `ssh cloud-vm`
- VM repo path: `~/efficient-storage-in-edge-scenarios`
- Default experiment entrypoint: `sudo -n make -C source/scripts setup_network
  create_clients setup_test_data run_experiment RUN_LABEL=<batch5_label>
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1`
- Sudo mode: `sudo -n` is required for autonomous experiment execution; treat
  any interactive password prompt as a cloud-host configuration failure.
- Image-build prerequisite: completed on `cloud-vm` before the first Batch 5
  relaunch with `cd ~/efficient-storage-in-edge-scenarios/source/scripts; bash
  build_images.sh`. Direct Docker access was available; wrapping the build
  script with `sudo -n` was rejected, but the experiment launch path still uses
  `sudo -n`.
- Per-run config application: update only `source/scripts/osken-controller.env`
  on the VM between runs to set `SS_ENABLED`, `MAX_DYNAMIC_STORAGE`, and
  `MAX_DYNAMIC_COMPUTE`.
- Planned run labels: `batch5_normal_static`, `batch5_normal_storage`,
  `batch5_normal_combined`, `batch5_normal_full_c2`.
- Validation before each launch: verify the three remote env values with
  `grep -E '^(SS_ENABLED|MAX_DYNAMIC_STORAGE|MAX_DYNAMIC_COMPUTE)='
  source/scripts/osken-controller.env`; after launch, treat
  `controller_env_snapshot.env` as authoritative proof.
- Artifact policy: after each completed run, summarize and trim the run folder
  on the VM when controller logs are no longer needed, copy the remaining
  artifacts back locally, verify the copy, and then remove the remote folder if
  the cloud host allows non-interactive deletion. If direct `sudo -n rm` is
  still rejected, keep the remote folder and record the caveat.

## Metric Lens

- Primary metrics: per-phase failures and p95 latency from generated request
  CSVs; `storage_count`, `server_count`, `tier1_lifecycle_active_count`, and
  `tier1_active_count` trends from `resource_stats.csv`; container lifecycle
  anchors from `container_events.csv`; controller log evidence around
  `DataAlert`, storage spawn/readiness/VIP admission, `SelectiveSyncAlert`,
  Tier 1 `ACTIVE`, `ComputeAlert`, compute drain/cancel markers, scale-down,
  cleanup failures, and post-cleanup reconfigure noise.
- Secondary metrics: `per_node_stats.csv` for load-balance and compute-driver
  evidence when present, `current_phase.txt` during live monitoring, and the
  generated analysis outputs under each run's `analysis/` directory.
- Required reference runs: Batch 4 `20260504_150216_batch4_c0` as the fresh
  post-fix static control, `20260504_155204_batch4_c2s4` as the storage-only
  ceiling-4 reference, and `20260505_151638_batch4_c3s5` as the best
  storage-enabled combined reference. Use `20260504_114144_batch4_c1` as the
  Tier 1-only reference when interpreting selective-sync value.
- Interpretation rule: absence of compute markers in `batch5_normal_full_c2`
  is not a failed run. It means the normal workload did not naturally exercise
  the compute path.

## Allowed Between-Run Edit Scope

- Allowed during this campaign: only `source/scripts/osken-controller.env` on
  the VM between runs, plus local documentation updates for this campaign
  brief and the Batch 5 result notes after runs complete.
- Forbidden during this campaign: source-code changes, edits to
  `source/scripts/testing/phases.json`, edits outside the controller env file
  on the VM, and edits to active run artifacts while a run is in progress.
- Validation used before each run: confirm the three knob values in the remote
  controller env before launch and in `controller_env_snapshot.env` after the
  run folder is created.

## Live Checkpoint Plan

- Monitoring control rule: after traffic generation starts, use passive
  monitoring. Perform only read-only checks against terminal output, process
  state, `current_phase.txt`, `resource_stats.csv`, `per_node_stats.csv`,
  `container_events.csv`, and controller logs.
- Agent authority: the runner may edit only `source/scripts/osken-controller.env`
  between runs; it may stop before traffic starts for failed prerequisites; it
  may analyze after completion; it must not interrupt active traffic unless the
  run has clearly failed and is no longer progressing.

| Trigger | Question | Data Sources | Continue If | Stop Or Restart If |
| ------- | -------- | ------------ | ----------- | ------------------ |
| Pre-run env check | Do the three controller knobs match the intended matrix row? | Remote `osken-controller.env`, later `controller_env_snapshot.env` | Values match the row | Values do not match; fix env before launch |
| Launch | Did setup and traffic generation begin cleanly? | Terminal output, new metrics folder, `current_phase.txt` | New run folder exists and phase advances beyond setup | `sudo -n` fails, setup fails, or no run folder is created |
| Storage activity window | For `B5-C1`, `B5-C2`, and `B5-C3`, does Tier 2 spawn and reach service when thresholds fire? | Controller logs, `container_events.csv`, `resource_stats.csv` | Requests continue, regardless of whether storage scale-up fires | Run is clearly dead before producing storage-sensitive evidence |
| Tier 1 activity window | For `B5-C2` and `B5-C3`, does Tier 1 reach `ACTIVE` without the old attach failure? | Controller logs, `resource_stats.csv`, `container_events.csv` | Tier 1 works, or the run still produces useful evidence without it | Old `Permission denied` wrapper failure returns before useful evidence |
| Compute opportunity window | For `B5-C3`, does compute elasticity naturally trigger with cap `2`? | Controller logs, `container_events.csv`, `per_node_stats.csv`, `resource_stats.csv` | `ComputeAlert` appears, or no compute event appears but the run completes | Compute behavior crashes the run before useful evidence is produced |
| Demand drop and idle | Did scale-down, drain, cancel, and cleanup complete cleanly? | Controller logs, `container_events.csv`, final `resource_stats.csv` rows | Cleanup completes or residual debt is captured for analysis | No automatic stop after traffic has already completed |

Compute-specific markers for `batch5_normal_full_c2`: `ComputeAlert`,
`scale_down_compute`, `compute candidate selected`, `CancelComputeDrainAlert`,
`cancel_compute_drain`, `canceled compute drain`, and `drain_complete`.

## Successive Runs

| Planned Label | Intended Delta | Command Or Config Change | Primary Metrics To Inspect | Result Run ID | Verdict | Next Action |
| ------------- | -------------- | ------------------------ | -------------------------- | ------------- | ------- | ----------- |
| batch5_normal_static | `SS_ENABLED=0`, `MAX_DYNAMIC_STORAGE=0`, `MAX_DYNAMIC_COMPUTE=0` | Update remote `osken-controller.env`, then launch with `RUN_LABEL=batch5_normal_static` | Static baseline failures, p95 latency, request volume, no dynamic activity, comparison to Batch 4 `batch4_c0` | `20260510_123544_batch5_normal_static` | Completed static baseline with no elasticity activity, but caveated by `edge_server_n1` exiting `139` during `reverse_hotspot`; 38,153 requests, 15.78% failures, p95 313.6 ms. Summary and trimmed artifacts copied locally to `source/scripts/testing/metrics/20260510_123544_batch5_normal_static`; original root-owned cloud run retained because direct non-interactive deletion is blocked. | Launch `batch5_normal_storage` after setting and verifying storage-only env values |
| batch5_normal_storage | `SS_ENABLED=0`, `MAX_DYNAMIC_STORAGE=5`, `MAX_DYNAMIC_COMPUTE=0` | Update remote `osken-controller.env`, then launch with `RUN_LABEL=batch5_normal_storage` | `DataAlert` to storage readiness or VIP admission, `storage_count`, failures, latency, Tier 2 cleanup debt | `20260510_133219_batch5_normal_storage` | Completed storage-only row; Tier 2 activated (`DataAlert=22`, storage spawns `11`, max `storage_count=6.0`) but service quality regressed versus static with 42,722 requests, 22.76% failures, p95 378.2 ms, and four dynamic storage containers still running at final collection. Summary and trimmed artifacts copied locally to `source/scripts/testing/metrics/20260510_133219_batch5_normal_storage`; original root-owned cloud run retained. | Launch `batch5_normal_combined` after setting and verifying selective-sync plus storage env values |
| batch5_normal_combined | `SS_ENABLED=1`, `MAX_DYNAMIC_STORAGE=5`, `MAX_DYNAMIC_COMPUTE=0` | Update remote `osken-controller.env`, then launch with `RUN_LABEL=batch5_normal_combined` | Tier 1 `ACTIVE`, Tier 1 reconfigure noise, storage interaction, failures and latency versus storage-only | `20260510_150147_batch5_normal_combined` plus partial attempt `20260510_142547_batch5_normal_combined` | Completed retry; combined mode triggered storage and Tier 1 (`DataAlert=21`, `SelectiveSyncAlert=2`, storage spawns `11`, Tier 1 `ACTIVE` log markers on both LANs). It reduced failures versus storage-only but worsened p95: 41,861 requests, 20.14% failures, p95 410.2 ms, max `storage_count=6.0`, final `storage_count=5.0`, telemetry `tier1_active_count=0.0`, and five dynamic storage containers still running at final collection. Summary and trimmed artifacts copied locally to `source/scripts/testing/metrics/20260510_150147_batch5_normal_combined`; original root-owned cloud run retained. | Launch `batch5_normal_full_c2` after setting and verifying compute cap `2` |
| batch5_normal_full_c2 | `SS_ENABLED=1`, `MAX_DYNAMIC_STORAGE=5`, `MAX_DYNAMIC_COMPUTE=2` | Update remote `osken-controller.env`, then launch with `RUN_LABEL=batch5_normal_full_c2` | Natural compute trigger evidence, drain/cancel markers, full-policy performance, storage and Tier 1 behavior | `20260510_153808_batch5_normal_full_c2` | Completed full row; compute cap was enabled but no natural compute elasticity occurred (`ComputeAlert=0`, compute dynamic events `0`, `server_count=1.0`). Storage and Tier 1 activated (`DataAlert=20`, `SelectiveSyncAlert=2`, max `storage_count=3.0`, Tier 1 `ACTIVE` log markers), with 42,088 requests, 21.39% failures, p95 400.0 ms, and two dynamic storage containers still running at final collection. Summary and trimmed artifacts copied locally to `source/scripts/testing/metrics/20260510_153808_batch5_normal_full_c2`; original root-owned cloud run retained. | Generate Batch 5 compare and final results synthesis |

## Stop And Restart Policy

- Automatic stop allowed during this campaign: only before useful traffic
  evidence exists, or after the run has clearly failed, is no longer
  progressing, and continuing would not produce useful evidence.
- Allowed restart cases: `sudo -n` or setup fails before traffic starts; no run
  folder is created; the SSH-bound launch path dies before traffic starts; or
  the SSH-bound launch path dies during traffic and read-only checks show the
  run is no longer active and produced no useful partial evidence.
- Do not restart for poor performance, failed scale-up, failed scale-down, or
  lifecycle churn. Those are behavioral results for Batch 5.
- Recovery plan: preserve partial artifacts, record the failure mode and run ID
  in this brief, and relaunch only for infrastructure or shell-level failure.

## Cross-Run Notes

- Batch 5 deliberately keeps the standard long-cycle workload unchanged; do not
  tune compute thresholds or edit `phases.json` in this campaign.
- The first Batch 5 static launch attempt from the repo root failed before any
  traffic or run folder creation because the remote root has no `setup_network`
  target. The actual orchestration Makefile on `cloud-vm` is
  `source/scripts/Makefile`, so Batch 5 launches use `make -C source/scripts`
  from the repo root.
- Batch 4 `batch4_c0` completed as the post-fix no-scale control with no Tier
  1, no Tier 2, and no compute elasticity activity.
- Batch 4 `batch4_c2s4` confirmed dynamic Tier 2 storage activation, but it was
  not a net improvement overall and ended with incomplete cleanup debt.
- Batch 4 `batch4_c3s5` was the best storage-enabled Batch 4 result: it reached
  `storage_count=5`, exercised Tier 1 on both LANs, improved on the no-scale
  control, and still carried Tier 1 telemetry and Tier 2 cleanup caveats.
- The Batch 4 partial `20260505_114215_batch4_c3s5` remains transport-failure
  evidence only and should be excluded from performance comparisons.
- Batch 5 `20260510_123544_batch5_normal_static` completed as the static
  baseline and stayed inert (`DataAlert=0`, `ComputeAlert=0`,
  `SelectiveSyncAlert=0`, no dynamic container events). Its performance result
  is caveated by `edge_server_n1` exiting `139` during `reverse_hotspot`, which
  contributed to late LAN1 failures.
- Batch 5 `20260510_133219_batch5_normal_storage` completed the storage-only
  row and confirmed Tier 2 activation on both LANs, reaching `storage_count=6`.
  It was not a service-quality improvement over static in this run: overall
  failures rose to 22.76%, p95 rose to 378.2 ms, and cleanup left four dynamic
  storage containers running at final collection.
- Batch 5 `20260510_142547_batch5_normal_combined` is a partial combined-row
  attempt only. The SSH launch disconnected during `sustained_plateau`; traffic
  later stopped, while root-owned collectors remained orphaned and could not be
  killed with direct `sudo -n kill`. A stable summarized snapshot was copied
  locally, then the `/tmp` snapshot was removed. Use it as transport-failure and
  Tier 1 reconfigure evidence, not as the definitive combined result.
- Batch 5 `20260510_150147_batch5_normal_combined` completed the combined row.
  Tier 1 reached `ACTIVE` in controller logs on both LANs, but
  `tier1_active_count` stayed at 0.0 in resource telemetry. Compared with
  storage-only, failures improved from 22.76% to 20.14%, but p95 latency rose
  from 378.2 ms to 410.2 ms and cleanup still left dynamic storage debt.
- Batch 5 `20260510_153808_batch5_normal_full_c2` completed the full row with
  compute cap `2`, but compute elasticity did not activate naturally
  (`ComputeAlert=0`, no compute dynamic containers, `server_count=1.0`). It
  retained Tier 1 log activation and storage activity, with 21.39% failures and
  p95 400.0 ms.
- Final Batch 5 comparison artifacts were generated on `cloud-vm` under `/tmp`
  because the remote metrics directory is not user-writable, then copied back to
  `source/scripts/testing/metrics/batch5_normal_compare`. Final results were
  written to `docs/operation/testing/elasticity_ablation_batch5_results.md`.
- Persistent caveats entering Batch 5: Tier 1 supply telemetry can disagree with
  lifecycle truth, post-cleanup Tier 1 reconfigure attempts can continue after
  removal, and Tier 2 cleanup convergence was incomplete in several Batch 4
  storage-enabled runs.
- Current remote retention caveat from Batch 4: the cloud host allowed the
  `sudo -n make ... run_experiment` path but rejected direct `sudo -n rm`; if
  this still holds after Batch 5 copy-back, keep the remote folders and record
  the retention status.

## Next Run Checklist

1. Completed: generated `source/scripts/testing/metrics/batch5_normal_compare`
  from the completed Batch 5 rows and documented the retained partial combined
  attempt as excluded failure evidence.
2. Completed: wrote `docs/operation/testing/elasticity_ablation_batch5_results.md`
  with the final Batch 5 verdict, comparisons, and caveats.
3. Completed: recorded that original root-owned cloud run folders were retained
  because non-interactive deletion was blocked.
4. No further Batch 5 runs are queued from this campaign brief.
