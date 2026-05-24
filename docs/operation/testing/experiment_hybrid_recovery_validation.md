# Hybrid Recovery Validation

## Purpose

This experiment family separates two questions that the standard workload
cannot answer cleanly on its own:

1. Do the recently implemented MongoDB request-lease and failed-backend
   avoidance features work under a deterministic backend failure?
2. How does the broader architecture behave now under the unchanged long-cycle
   workload?

The workflow is therefore hybrid:

1. run one short deterministic `n1` validation;
2. run one short deterministic `n2` validation;
3. only then run the standard long-cycle observation workload.

The targeted runs exist to validate the new correctness semantics without
mixing that answer with the broader VIP and client-model instability already
seen in kept long-cycle summaries.

## Run Family

### Targeted `n1` validation

- Phase file:
  [../../../source/scripts/testing/phases_experiment_hybrid_validation_n1.json](../../../source/scripts/testing/phases_experiment_hybrid_validation_n1.json)
- Fault plan:
  [../../../source/scripts/testing/fault_plan_experiment_hybrid_validation_n1.json](../../../source/scripts/testing/fault_plan_experiment_hybrid_validation_n1.json)
- Goal: drive `lan2 -> lan1` storage-locality pressure, wait for a stable
  normal VIP_DATA path, then hard-stop the last normal backend chosen by the
  controller that owns the hot client path.

### Targeted `n2` validation

- Phase file:
  [../../../source/scripts/testing/phases_experiment_hybrid_validation_n2.json](../../../source/scripts/testing/phases_experiment_hybrid_validation_n2.json)
- Fault plan:
  [../../../source/scripts/testing/fault_plan_experiment_hybrid_validation_n2.json](../../../source/scripts/testing/fault_plan_experiment_hybrid_validation_n2.json)
- Goal: mirror the same validation for `lan1 -> lan2` traffic.

### Long-cycle observation rerun

- Phase file:
  [../../../source/scripts/testing/phases.json](../../../source/scripts/testing/phases.json)
- Fault plan: none
- Goal: preserve the current architecture-observation baseline after the two
  deterministic correctness checks succeed.

## Artifact Contract

All runs keep the normal run-directory layout from
[testing_overview.md](testing_overview.md), with one addition for fault-aware
runs:

- `fault_plan_snapshot.json` — copy of the plan used for the run
- `experiment_fault_events.csv` — explicit record of injected actions,
  selected backend IP, selected container name, and execution status

The focused recovery-analysis pass writes under `analysis/`:

- `recovery_validation_summary.md`
- `recovery_validation_fault_windows.csv`
- `recovery_validation_request_lease_outcomes.csv`

## Launch Pattern

Targeted validation runs use the same runner with a phase override and fault
plan:

```bash
bash source/scripts/testing/run_experiment.sh \
  --phases-config source/scripts/testing/phases_experiment_hybrid_validation_n1.json \
  --fault-plan source/scripts/testing/fault_plan_experiment_hybrid_validation_n1.json \
  --run-label hybrid_validation_n1
```

The long-cycle observation rerun stays on the default phases file and omits
the fault plan:

```bash
bash source/scripts/testing/run_experiment.sh \
  --run-label hybrid_observation_current_code
```

These commands are documented here for operator reference only. They are not a
requirement to execute immediately when the code changes land.

## Interpretation Rules

### Request-lease outcomes

Use `recovery_validation_request_lease_outcomes.csv` and the summary counts to
separate the three expected cases:

- `success_normal` — the request never needed a recovery rebind
- `success_after_rebind` — the request completed after one bounded recovery
  rebind or stale-epoch catch-up
- `failure_terminal` — the request hit the terminal path after the recovery
  budget or current recovery epoch was exhausted

### Controller markers

The controller-side follow-up is working only if the targeted fault windows
show the recovery marker already implemented in
[../../../source/sdn_controller/vip_routing.py](../../../source/sdn_controller/vip_routing.py):

- `recovery avoiding last normal backend`

Fallback markers are expected in smaller pools and should be interpreted as a
safe degeneration, not as proof that the avoidance logic is absent:

- `recovery fallback to full pool after avoidance would empty candidates`

### Architecture observation

The long-cycle run is not itself the authoritative correctness check for the
new features. It becomes useful only after the targeted `n1` and `n2` runs
show that the request-lease and controller-avoidance mechanisms behave as
expected under deterministic failure.

## Image Rebuild Gate

This experiment family touches mostly host-side harness and analysis code.
That means the rebuild rule is narrow:

1. Changes under `source/scripts/`, `docs/`, and `source/sdn_controller/` do
   not require rebuilding the `osken-controller` image because the controller
   container bind-mounts the workspace at runtime.
2. Changes under `source/scripts/testing/analysis/` do not require any image
   rebuild because they are offline host-side tools.
3. The only image that must be considered for freshness is `edge_server`,
   because the request-lease implementation is baked into the runtime image.
4. If the execution host's `edge_server` image is stale or uncertain, rebuild
   it before running the targeted validation campaign.
5. `edge_storage_server` and `osken-controller` do not need rebuilds for this
   experiment family unless their Docker trees or baked runtime code change.

Recommended command when the remote `edge_server` image is stale:

```bash
bash source/scripts/build_images.sh edge_server
```

## Verification Sequence

1. Validate the shared runner support without executing a real campaign.
   Confirm that custom phases, fault-plan snapshots, and
   `experiment_fault_events.csv` all appear in a prepared run directory.
2. Run targeted `n1` validation and inspect the recovery-validation outputs.
3. Run targeted `n2` validation and inspect the recovery-validation outputs.
4. Run the unchanged long-cycle observation workload and compare it with the
   most recent kept architecture summaries.

If either targeted run fails to show the expected request-lease or
controller-avoidance signals, treat the long-cycle rerun as architecture-only
observation rather than as proof that the new features are correct.