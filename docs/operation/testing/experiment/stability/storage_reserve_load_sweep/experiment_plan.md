# Experiment Plan - Storage Reserve Load Sweep

## Intent

This experiment is a short post-usability load-tuning pass, not a validation ladder. It answers one operational question: once reserve use has already been proved and a usable threshold profile has been chosen, what is the lightest offered-load setting among three candidate client counts that still reproduces same-LAN reserve activation under that fixed profile? The plan is grounded in the same reserve and trigger paths used by [storage_reserve_threshold_sweep/experiment_plan.md](../storage_reserve_threshold_sweep/experiment_plan.md), but the independent variable is now offered load rather than threshold.

## Hypothesis / Expected Outcome

At the lower client counts, the reserve may remain `READY_RESERVED` and heartbeating but unused. As offered load increases, the same fixed threshold bundle should eventually emit `[scale-up] storage triggered` and then `[reserve] activated`. Because reserve use is already proved separately, the useful outcome here is the lightest reproducible activation load among the three candidates rather than a full load boundary map.

## RQ Linkage

This is still part of the reserved-standby branch of RQ3 in [system_to_thesis_map_rq_advanced.md](../../../../../../tese/miscelineous/system_to_thesis_map_rq_advanced.md), but now as a coarse tuning exercise after usability is already established. It helps pick a lighter reproducible offered-load point for later campaigns.

## Prerequisites

- ✅ **[storage_reserve_use_validation/results.md](../storage_reserve_use_validation/results.md) reached `reserve-used`** (2026-06-05). The use-validation gate is passed — this sweep is unlocked.
- ✅ **[storage_reserve_threshold_sweep/results.md](../storage_reserve_threshold_sweep/results.md)** characterized the activation boundary (0.12 < τ ≤ 0.15) and showed that `t12` (0.12) is the highest threshold that still activates under the shared probe workload. The fixed threshold for this sweep is `t12`.
- Use the fixed threshold override [storage_reserve_threshold_t12.env](../../../../../../source/scripts/testing/controller_env_overrides/storage_reserve_threshold_t12.env) for every run — this is the chosen operating point from the threshold sweep.
- Use the shared probe phase file [phases_experiment_storage_reserve_shared.json](../../../../../../source/scripts/testing/phases_experiment_storage_reserve_shared.json) unchanged for every run. This workload includes a `sustained_use` phase (180s @ 7 r/s, 80% cross-region) — the phase the old probe was missing, where the activated reserve must actually carry traffic.
- Keep the chosen proven-usable controller override unchanged for every run so the only varied input is `CLIENTS`.

## Independent Variable & Held-Constant Set

- Independent variable: offered load via `CLIENTS` only.
- Held constant workload shape: `testing/phases_experiment_storage_reserve_shared.json`.
- Held constant seeding: `DEVICES=600`, `NODES=100`.
- Held constant controller behavior: `STORAGE_PERSISTENT_RESERVE_ENABLED=1`, `SS_ENABLED=0`, `MAX_DYNAMIC_COMPUTE=0`, no `--fault-plan`, same code/image state, and same WAN profile.
- Held constant storage trigger bundle: `SCALEUP_W_STORAGE_CPU=0.60`, `SCALEUP_W_T_DB=0.40`, `SCALEUP_STORAGE_CPU_FLOOR=1.5`, `SCALEUP_STORAGE_CPU_SPAN=5`, `SCALEUP_T_DB_FLOOR=60`, `SCALEUP_T_DB_SPAN=250`, `SCALEUP_STORAGE_BASE_THRESHOLD=0.12`, `SCALEUP_STORAGE_REQUIRED=2`, `SCALEUP_STORAGE_WINDOW_SIZE=5`, `SCALEUP_STORAGE_COOLDOWN_S=120`, and `MAX_DYNAMIC_STORAGE=5`.
- Held constant scope: same-LAN reserve activation only. Tier 1 and compute elasticity stay disabled or out of scope.

## Run Matrix

This experiment uses at most three runs. The detailed row-by-row matrix, recommended stop rule, exact client counts, and concrete commands are in [run_matrix.md](run_matrix.md).

## Run Configuration

- Launch path: verified non-interactive `make` workflow from [Makefile](../../../../../../source/scripts/Makefile).
- `--phases-config`: `testing/phases_experiment_storage_reserve_shared.json`.
- `--seed-devices`: `600` via `DEVICES=600`.
- `--seed-nodes`: `100` via `NODES=100`.
- Skip flags: `SKIP_CLIENTS=1`, `SKIP_SEED=1`, and `SKIP_SNAPSHOT=1` inside `run_experiment`.
- `--fault-plan`: omitted explicitly.
- Controller override: `OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/storage_reserve_threshold_t12.env` — the chosen operating point from the threshold sweep.
- Images: no rebuild required unless the deployed images no longer match the code under test.

Shared probe phase file used by this experiment: `testing/phases_experiment_storage_reserve_shared.json`

```json
{
  "phases": [
    {
      "name": "baseline",
      "duration_s": 60,
      "rate_per_client": 2.0,
      "cross_region_ratio": 0.0,
      "mix": { "device_status": 0.60, "dashboard": 0.25, "service_pressure": 0.15 }
    },
    {
      "name": "storage_ramp",
      "duration_s": 120,
      "rate_per_client": 6.0,
      "cross_region_ratio": 0.70,
      "hotspot_direction": "lan2_to_lan1",
      "mix": { "device_status": 0.80, "dashboard": 0.10, "service_pressure": 0.10 }
    },
    {
      "name": "storage_hotspot",
      "duration_s": 300,
      "rate_per_client": 10.0,
      "cross_region_ratio": 0.90,
      "hotspot_direction": "lan2_to_lan1",
      "mix": { "device_status": 0.90, "dashboard": 0.05, "service_pressure": 0.05 }
    },
    {
      "name": "sustained_use",
      "duration_s": 180,
      "rate_per_client": 7.0,
      "cross_region_ratio": 0.80,
      "hotspot_direction": "lan2_to_lan1",
      "mix": { "device_status": 0.85, "dashboard": 0.08, "service_pressure": 0.07 }
    },
    {
      "name": "demand_drop",
      "duration_s": 120,
      "rate_per_client": 2.0,
      "cross_region_ratio": 0.10,
      "mix": { "device_status": 0.60, "dashboard": 0.25, "service_pressure": 0.15 }
    }
  ]
}
```

Why `CLIENTS` is the chosen load variable:

- it is a real `run_experiment.sh` knob and therefore easy to hold constant everywhere else
- it keeps the phase file unchanged across all candidate runs
- it gives a clean single-variable sweep even though the current generator cannot express source-only rate changes

## Focus & Evidence

Primary focus: `controller_lan1.log`, `controller_lan2.log`, `elasticity_events.csv`, `node_lifecycle_timings.csv`, and `client_requests.csv`.

- The decisive markers remain `[reserve] ready_reserved`, `[scale-up] storage triggered`, `[reserve] waiting_ready`, `[reserve] activated`, and replenish submission.
- `client_requests.csv` matters more here than in the threshold sweep because the user-visible failure window is part of deciding whether a lighter-load candidate is still useful operationally.

Secondary focus: `resource_stats.csv`, `per_node_stats.csv`, and `service_logs/`.

- `resource_stats.csv` and `per_node_stats.csv` show whether the reserve remained visible while the offered load increased and whether `storage_count` reached `2` in late windows.
- `service_logs/` is only for disambiguation if reserve liveness looks inconsistent. Reserve use itself is not re-proved here; that is the job of [storage_reserve_use_validation/experiment_plan.md](../storage_reserve_use_validation/experiment_plan.md).

## Metrics & Success Criteria

1. Run validity.
   Each run is valid only if the stressed LAN reaches `READY_RESERVED` before or during `storage_hotspot` and does not re-enter the cleanup loop.
2. Stable activating candidate.
   A candidate is acceptable only if: (a) the first same-LAN storage trigger is followed by `[reserve] activated` by the end of `storage_hotspot` or early `sustained_use`; (b) a fresh `[reserve] prepare_submitted` for replenish follows; and (c) the activated reserve is not removed and re-activated within `sustained_use` (no cycling).
3. Waiting-only candidate.
  A candidate is `waiting-only` if reserve stays `READY_RESERVED` and heartbeating but no `[scale-up] storage triggered` appears by the end of `storage_hotspot`.
4. Tuning success condition.
  The experiment succeeds when at least one of the three candidates is acceptable (stable activating). The preferred operating point is the lowest client count among the acceptable candidates.
5. Stop rule.
  Start from the anchor load in [run_matrix.md](run_matrix.md). Use the third run only if the first two results still leave the lightest acceptable load ambiguous.
6. Escalation rule.
  If none of the three candidates activate, extend load upward before changing thresholds. If all three activate comfortably, try a lower trio only in a later pass.

## Checkpoints

| Trigger | Question | Evidence | Runner action |
| --- | --- | --- | --- |
| End of `baseline` | Is the reserve already `READY_RESERVED` before the load probe starts? | Controller logs, `elasticity_events.csv` | Report only |
| First `[scale-up] storage triggered` | Did the fixed threshold bundle finally reach activation at this client count? | Controller logs, `node_lifecycle_timings.csv` | Report only |
| End of `sustained_use` | Did the reserve cycle (activate → remove → re-activate) within `sustained_use`? Count distinct `[reserve] activated` events. | Controller logs, `elasticity_events.csv` | Report only — cycling disqualifies the candidate |

## Validity Threats & Limitations

- Changing `CLIENTS` raises both local and cross-region load on both LANs because the current generator uses symmetric client pools. This is still the cleanest current single-variable load knob, but it is not a pure source-only load sweep.
- This sweep keeps one proven-usable threshold bundle fixed. If the real activation behavior depends more on threshold choice than on offered load, use [storage_reserve_threshold_sweep/experiment_plan.md](../storage_reserve_threshold_sweep/experiment_plan.md) first.
- This is intentionally a coarse 2-3 run tuning pass, not an exhaustive load boundary map.
- No `--fault-plan` is used, so recovery-distress activation is out of scope.

## Artifact Contract

Each run folder under `source/scripts/testing/metrics/<timestamp>_<run_label>/` must contain the standard artifacts described in [testing_overview.md](../../../testing_overview.md): `client_requests.csv`, `resource_stats.csv`, `resource_stats_debug.csv`, `policy_state.csv`, `per_node_stats.csv`, `container_events.csv`, `elasticity_events.csv`, `controller_lan1.log`, `controller_lan2.log`, `controller_env_snapshot.env`, `phases_snapshot.json`, and `service_logs/`.

Expected later analysis outputs:

- The normal run summaries from the existing analysis toolchain.
- A load-tuning note that records, for each candidate client count, reserve ready time, first trigger time, activation time if any, replenish submission time if any, first LAN1 failure timestamp, last LAN1 `200` timestamp, and the chosen operating point.
