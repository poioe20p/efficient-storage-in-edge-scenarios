# Experiment Plan - Storage Reserve Threshold Sweep

## Intent

This experiment is a short post-usability threshold-tuning pass, not a validation ladder. It answers one operational question: now that [storage_reserve_use_validation/results.md](../storage_reserve_use_validation/results.md) has proved reserve can become request-visible capacity at `t08` and that `t20` never activates, which threshold in the unexplored range `t10`–`t18` is the least aggressive setting that still produces **stable** first-step reserve activation (activates once and does not cycle) under one fixed probe workload? The known boundaries are: `t08` activates reliably but cycles (3 full reserve cycles in 10 min on the control run); `t20` stays waiting-only. This sweep fills the gap. The plan is grounded in the storage trigger logic in [scaling_policy.py](../../../../../../source/sdn_controller/scaling_policy.py), the reserve activation path in [main_n1.py](../../../../../../source/sdn_controller/main_n1.py), [main_n2.py](../../../../../../source/sdn_controller/main_n2.py), and [node_registry.py](../../../../../../source/sdn_controller/node_registry.py), the reserve lifecycle docs in [README.md](../../../../elasticy_manager/implementation/storage_persistent_reserve/README.md) and [storage_scale_up.md](../../../../elasticy_manager/scale_up/storage_scale_up.md), and the real runner/artifact contract in [run_experiment.sh](../../../../../../source/scripts/testing/run_experiment.sh), [Makefile](../../../../../../source/scripts/Makefile), and [testing_overview.md](../../../testing_overview.md).

## Hypothesis / Expected Outcome

Under the shared activation-probe load, lower `SCALEUP_STORAGE_BASE_THRESHOLD` values should trigger reserve earlier and more reliably, while higher thresholds should delay activation or leave the reserve `READY_RESERVED` but unused. The `t08` control and rebind runs showed that activation alone is insufficient — the threshold must also avoid reserve cycling (activate → remove → re-activate within the same probe window). Because reserve use is already proved separately, the useful outcome here is a coarse operating choice, not a full boundary map: prefer the highest threshold among the candidates that reaches `[reserve] activated` within `activation_probe` **and does not cycle**.

## RQ Linkage

This plan still supports the reserved-standby branch of RQ3 in [system_to_thesis_map_rq_advanced.md](../../../../../../tese/miscelineous/system_to_thesis_map_rq_advanced.md), but now as a coarse tuning exercise after usability is already established. It helps choose a less aggressive trigger point without reopening the question of whether reserve can be used at all.

## Prerequisites

- ✅ **[storage_reserve_use_validation/results.md](../storage_reserve_use_validation/results.md) reached `reserve-used`** (2026-06-05). Both control and rebind runs at `t08` activated and served traffic through the reserve. The use-validation gate is passed — this sweep is now unlocked.
- Known boundaries from the use-validation campaign: `t08` activates but cycles (3 cycles on control, 2 on rebind); `t20` stayed waiting-only in a prior run. The candidate set below targets the unexplored range between them.
- Use the shared probe phase file [phases_experiment_storage_reserve_shared.json](../../../../../../source/scripts/testing/phases_experiment_storage_reserve_shared.json) unchanged for every run. This workload includes a `sustained_use` phase (180s @ 7 r/s, 80% cross-region) after the hotspot — the phase the old probe was missing, where the activated reserve must actually carry traffic.
- Use the per-run controller overrides under [controller_env_overrides](../../../../../../source/scripts/testing/controller_env_overrides/) so the matrix stays launch-ready without editing [osken-controller.env](../../../../../../source/scripts/osken-controller.env) in place.

## Independent Variable & Held-Constant Set

- Independent variable: `SCALEUP_STORAGE_BASE_THRESHOLD` only.
- Held constant workload: one shared probe file, `testing/phases_experiment_storage_reserve_shared.json`.
- Held constant workload sizing: `CLIENTS=8`, `DEVICES=600`, `NODES=100`.
- Held constant controller behavior: `STORAGE_PERSISTENT_RESERVE_ENABLED=1`, `SS_ENABLED=0`, `MAX_DYNAMIC_COMPUTE=0`, no `--fault-plan`, same code/image state, and same WAN profile.
- Held constant storage trigger bundle besides the independent variable: `SCALEUP_W_STORAGE_CPU=0.60`, `SCALEUP_W_T_DB=0.40`, `SCALEUP_STORAGE_CPU_FLOOR=1.5`, `SCALEUP_STORAGE_CPU_SPAN=5`, `SCALEUP_T_DB_FLOOR=60`, `SCALEUP_T_DB_SPAN=250`, `SCALEUP_STORAGE_REQUIRED=2`, `SCALEUP_STORAGE_WINDOW_SIZE=5`, `SCALEUP_STORAGE_COOLDOWN_S=120`, and `MAX_DYNAMIC_STORAGE=5`.
- Held constant scope: same-LAN reserve activation only. Cross-LAN full-replica placement, Tier 1, and compute elasticity stay disabled or out of scope.

## Run Matrix

This experiment uses at most three runs. The detailed row-by-row matrix, recommended stop rule, exact threshold values, and concrete commands are in [run_matrix.md](run_matrix.md).

## Run Configuration

- Launch path: verified non-interactive `make` workflow from [Makefile](../../../../../../source/scripts/Makefile).
- `--phases-config`: `testing/phases_experiment_storage_reserve_shared.json`.
- `--clients-per-lan`: `8` via `CLIENTS=8`.
- `--seed-devices`: `600` via `DEVICES=600`.
- `--seed-nodes`: `100` via `NODES=100`.
- Skip flags: `SKIP_CLIENTS=1`, `SKIP_SEED=1`, and `SKIP_SNAPSHOT=1` inside `run_experiment`.
- `--fault-plan`: omitted explicitly.
- Controller overrides: each row in [run_matrix.md](run_matrix.md) uses its own `OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/storage_reserve_threshold_tXX.env` so `SCALEUP_STORAGE_BASE_THRESHOLD` is the only per-run controller delta.
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

Why this probe shape replaces the old one:

- The old probe (`baseline → activation_probe → demand_drop`) only verified whether the reserve activates — the load cliff-dropped immediately after activation, giving no phase where the reserve serves sustained traffic. The 180s `demand_drop` exceeded the 120s scale-down cooldown, guaranteeing the reserve would be removed and re-activated (cycling).
- **`storage_ramp`** (120s) builds load gradually instead of cliff-jumping from 2 to 10 req/s.
- **`storage_hotspot`** (300s) provides the peak stress that triggers activation.
- **`sustained_use`** (180s @ 7 r/s, 80% cross-region) is the missing phase — the activated reserve must carry real traffic here. Stability is judged by whether the reserve persists through this entire phase without cycling.
- **`demand_drop` at 120s** matches `SCALEUP_STORAGE_COOLDOWN_S=120`, eliminating the post-cooldown window that caused cycling in the old probe.
- Total duration: 780s (13 min).

## Focus & Evidence

Primary focus: `controller_lan1.log`, `controller_lan2.log`, `elasticity_events.csv`, and `node_lifecycle_timings.csv`.

- The decisive markers are `[reserve] ready_reserved`, `[scale-up] storage triggered`, `[reserve] waiting_ready`, `[reserve] activated`, and the next `[reserve] prepare_submitted` for replenish.
- `elasticity_events.csv` and `node_lifecycle_timings.csv` confirm whether reserve activation was the first extra-capacity step or whether the run stayed in a waiting-only regime.

Secondary focus: `client_requests.csv`, `resource_stats.csv`, `per_node_stats.csv`, and `service_logs/`.

- `client_requests.csv` answers whether the less aggressive threshold delayed activation enough to noticeably widen the failure window relative to the other candidates.
- `resource_stats.csv` and `per_node_stats.csv` show whether the reserve remained visible and whether `storage_count` briefly reached `2` after activation.
- `service_logs/` is only for disambiguation when reserve readiness or liveness looks inconsistent with the controller logs. Reserve use itself is not re-proved here; that is the job of [storage_reserve_use_validation/experiment_plan.md](../storage_reserve_use_validation/experiment_plan.md).

## Metrics & Success Criteria

1. Run validity.
   Each run is valid only if the stressed LAN reaches `READY_RESERVED` before or during `storage_hotspot` and does not re-enter the cleanup loop.
2. Stable activating candidate.
   A candidate is acceptable only if: (a) the first same-LAN storage trigger is followed by `[reserve] activated` by the end of `storage_hotspot` or early `sustained_use`; (b) a fresh `[reserve] prepare_submitted` for replenish follows; and (c) the activated reserve is **not** removed and re-activated within `sustained_use` (no cycling). A single activation that persists through `sustained_use` and into `demand_drop` is the goal.
3. Waiting-only candidate.
   A candidate is `waiting-only` if reserve stays `READY_RESERVED` and heartbeating but no `[scale-up] storage triggered` appears by the end of `storage_hotspot`.
4. Cycling candidate.
   A candidate `cycles` if it activates but the reserve is subsequently removed (scale-down) and then re-activated within `sustained_use`. The `t08` control run exhibited 3 such cycles — one during the hotspot, two during what should have been sustained use. Cycling candidates are unacceptable for operational use even though they prove the threshold can activate.
5. Tuning success condition.
   The experiment succeeds when at least one candidate is acceptable (stable activating). The preferred operating point is the highest threshold among the acceptable candidates.
6. Stop rule.
   Start at `t15`. If it is stable-activating, optionally try `t18` to stretch higher; otherwise stop at `t15`. If `t15` misses activation, fall back to `t12`. If `t12` cycles, fall back to `t10`. Stop once a stable-activating threshold is found or all primary candidates are exhausted.
7. Escalation rule.
   If none of `t15`, `t12`, `t10` yield a stable activation, widen the threshold range or revisit the workload shape before changing load.

## Checkpoints

| Trigger | Question | Evidence | Runner action |
| --- | --- | --- | --- |
| End of `baseline` | Is the reserve already `READY_RESERVED` before the probe starts? | Controller logs, `elasticity_events.csv` | Report only |
| First `[scale-up] storage triggered` | Did the controller activate reserve immediately or only latch waiting? | Controller logs, `node_lifecycle_timings.csv` | Report only |
| About one telemetry window after activation | Did a new reserve preparation begin immediately after activation? | Controller logs, `elasticity_events.csv` | Report only |
| End of `sustained_use` | Did the reserve cycle (activate → remove → re-activate) within `sustained_use`? Count distinct `[reserve] activated` events. | Controller logs, `elasticity_events.csv` | Report only — cycling disqualifies the candidate |

## Validity Threats & Limitations

- The current traffic generator cannot create a truly source-only hotspot. `hotspot_direction` only gates who may issue cross-region reads; both LANs still keep their local traffic at the same phase rate.
- This sweep varies only `SCALEUP_STORAGE_BASE_THRESHOLD`. If the real activation behavior is dominated by the CPU or DB floor values instead, this plan tunes only within the current relaxed floor bundle.
- This is intentionally a coarse 2-3 run tuning pass, not an exhaustive boundary map. The `t08` cycling evidence (3 cycles in 10 min) is specific to this probe workload; a different workload shape may shift the stability boundary.
- No `--fault-plan` is used, so recovery-distress activation is not exercised here.
- The adaptive threshold increment (`SCALEUP_STORAGE_THRESHOLD_INCREMENT=0.10`) means the effective threshold rises to `base + 0.10` after the first activation. The `demand_drop` phase at 120s matches `SCALEUP_STORAGE_COOLDOWN_S=120`, so scale-down cannot fire during the drop — the cooldown and the drop end simultaneously. This eliminates the cycling window that existed with the old 180s `demand_drop`.

## Artifact Contract

Each run folder under `source/scripts/testing/metrics/<timestamp>_<run_label>/` must contain the standard artifacts described in [testing_overview.md](../../../testing_overview.md): `client_requests.csv`, `resource_stats.csv`, `resource_stats_debug.csv`, `policy_state.csv`, `per_node_stats.csv`, `container_events.csv`, `elasticity_events.csv`, `controller_lan1.log`, `controller_lan2.log`, `controller_env_snapshot.env`, `phases_snapshot.json`, and `service_logs/`.

Expected later analysis outputs:

- The normal run summaries from the existing analysis toolchain.
- A threshold-tuning note that records, for each candidate threshold, reserve ready time, first trigger time, activation time if any, replenish submission time if any, hotspot failure rate, and the chosen operating point.
