# Experiment Plan - Tier 1 Activation Stability

## Intent

This experiment evaluates the current Tier 1 selective-sync path as a required part of architecture readiness. It answers one operational question: when the workload is deliberately shaped to create a sustained hot cross-region read set, does Tier 1 reach `ACTIVE`, improve the consumer-LAN DB-latency signal, and drain cleanly without destabilizing the run? The plan is grounded in the selective-sync lifecycle in [selective_sync_overview.md](../../../selective_sync/selective_sync_overview.md), the Tier 1 hotspot workload described in [testing_overview.md](../../../testing_overview.md), the concrete phase file [phases_experiment_tier1_hotspot_bidirectional.json](../../../../../../source/scripts/testing/phases_experiment_tier1_hotspot_bidirectional.json), the current traffic-generator schema in [traffic_generator.py](../../../../../../source/scripts/testing/traffic_generator.py), the selective-sync thresholds in [scaling_config.py](../../../../../../source/sdn_controller/scaling_config.py), and the existing runner contract in [run_experiment.sh](../../../../../../source/scripts/testing/run_experiment.sh).

## Hypothesis / Expected Outcome

With `SS_ENABLED=1`, a Tier 1-targeting hotspot workload should emit `SelectiveSyncAlert`, move the coordinator state from `NONE` to `SPAWNING` to `ACTIVE`, broadcast a manifest to the consumer LAN, and produce a visible drop in consumer-side `T_db` p95 within about 1 to 2 telemetry windows after activation. The same workload with `SS_ENABLED=0` should not activate Tier 1 and should therefore preserve the higher cross-region DB-latency profile. In both cases, the run must finish without controller tracebacks, selective-storage crash loops, or residual `sel_sync_*` containers at final idle.

## Prerequisites

- Use [phases_experiment_tier1_hotspot_bidirectional.json](../../../../../../source/scripts/testing/phases_experiment_tier1_hotspot_bidirectional.json) unchanged for both runs.
- Current-capability approach: the current traffic generator randomly selects among devices in the target LAN, so this plan uses a deliberately small seeded working set (`DEVICES=30`) to make the hot set bounded without changing driver code. That keeps the run grounded in current capabilities instead of inventing a new schema.
- If this Tier 1 validation is being chained after storage-reserve work, first pass [storage_reserve_validation/experiment_plan.md](../storage_reserve_validation/experiment_plan.md). Do not continue to Tier 1 if the reserve-liveness gate fails.

## Independent Variable & Held-Constant Set

- Independent variable: Tier 1 lifecycle enabled versus disabled (`SS_ENABLED=1` vs `SS_ENABLED=0`).
- Held constant: same Tier 1 hotspot workload, same code and images, same WAN profile, same client/node/device counts, same runner path, and no `--fault-plan`.
- Held constant controller knobs besides the independent variable: use the fixed controller overrides [tier1_hotspot_control.env](../../../../../../source/scripts/testing/controller_env_overrides/tier1_hotspot_control.env) and [tier1_hotspot_enabled.env](../../../../../../source/scripts/testing/controller_env_overrides/tier1_hotspot_enabled.env). They pin `MAX_DYNAMIC_STORAGE=0`, `MAX_DYNAMIC_COMPUTE=0`, and `STORAGE_PERSISTENT_RESERVE_ENABLED=0` so Tier 1 is isolated from Tier 2 reserve and compute-elasticity churn without editing [osken-controller.env](../../../../../../source/scripts/osken-controller.env) in place.
- Held constant selective-sync thresholds: use the current defaults in [scaling_config.py](../../../../../../source/sdn_controller/scaling_config.py): `SS_MIN_READS_PER_WINDOW=14`, `SS_PROMOTION_CROSS_REGION_THRESHOLD=0.4`, `SS_BREACH_WINDOWS_M=2`, `SS_BREACH_WINDOWS_N=5`, `SS_SCALEDOWN_THRESHOLD=5`, and `SS_SCALEDOWN_WINDOW=8`.
- Held constant workload intent: read-only GET mix, hotspot concentrated on a bounded seeded device set (`DEVICES=30`), and both cross-region directions exercised within the same scenario file.

## Run Matrix

| Run label | What changes | Phase file |
| --- | --- | --- |
| `tier1_hotspot_control` | Same hotspot workload with Tier 1 disabled (`SS_ENABLED=0`) | [phases_experiment_tier1_hotspot_bidirectional.json](../../../../../../source/scripts/testing/phases_experiment_tier1_hotspot_bidirectional.json) |
| `tier1_hotspot_enabled` | Same hotspot workload with Tier 1 enabled (`SS_ENABLED=1`) | [phases_experiment_tier1_hotspot_bidirectional.json](../../../../../../source/scripts/testing/phases_experiment_tier1_hotspot_bidirectional.json) |

Run order is fixed: run the control first, then the enabled run on the same code and image state.

## Run Configuration

- Launch path: verified non-interactive `make` workflow from [Makefile](../../../../../../source/scripts/Makefile).
- `--phases-config`: `testing/phases_experiment_tier1_hotspot_bidirectional.json`.
- `--run-label`: `tier1_hotspot_control` and `tier1_hotspot_enabled`.
- `--batch-dir`: omitted in the default `make` path.
- `--clients-per-lan`: `6` via `CLIENTS=6`.
- `--seed-devices`: `30` via `DEVICES=30` so the existing random device picker still concentrates cross-region demand on a bounded hot set.
- `--seed-nodes`: `40` via `NODES=40`.
- Skip flags: `SKIP_CLIENTS=1`, `SKIP_SEED=1`, and `SKIP_SNAPSHOT=1` inside `run_experiment`, because the same `make` call already runs `setup_network`, `create_clients`, and `setup_test_data` before `run_experiment`.
- `--fault-plan`: omitted explicitly.
- Controller override: `OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/tier1_hotspot_control.env` for the control run and `OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/tier1_hotspot_enabled.env` for the enabled run.

Phase profile used by this experiment:

- `warmup`: `45 s`, `rate_per_client=2.0`, `cross_region_ratio=0.0`, mix `device_status=0.70`, `dashboard=0.15`, `service_pressure=0.15`.
- `tier1_hotspot_n1`: `240 s`, `rate_per_client=8.0`, `cross_region_ratio=0.95`, `hotspot_direction=lan2_to_lan1`, mix `device_status=0.95`, `dashboard=0.03`, `service_pressure=0.02`.
- `cooldown_n1`: `120 s`, `rate_per_client=0.5`, `cross_region_ratio=0.0`, mix `device_status=0.70`, `dashboard=0.20`, `service_pressure=0.10`.
- `tier1_hotspot_n2`: `240 s`, `rate_per_client=8.0`, `cross_region_ratio=0.95`, `hotspot_direction=lan1_to_lan2`, mix `device_status=0.95`, `dashboard=0.03`, `service_pressure=0.02`.
- `cooldown_n2`: `120 s`, `rate_per_client=0.5`, `cross_region_ratio=0.0`, mix `device_status=0.70`, `dashboard=0.20`, `service_pressure=0.10`.

These timings are chosen against the current selective-sync thresholds: activation needs 2 breached windows inside a 5-window ring, while drain needs 8 consecutive cold windows. With the current 10-second telemetry windows, `240 s` hotspot phases and `120 s` cooldown phases leave margin for both activation and drain observation.

Concrete commands:

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
   OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/tier1_hotspot_control.env \
  RUN_LABEL=tier1_hotspot_control \
  PHASES_CONFIG=testing/phases_experiment_tier1_hotspot_bidirectional.json \
  CLIENTS=6 DEVICES=30 NODES=40 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
   OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/tier1_hotspot_enabled.env \
  RUN_LABEL=tier1_hotspot_enabled \
  PHASES_CONFIG=testing/phases_experiment_tier1_hotspot_bidirectional.json \
  CLIENTS=6 DEVICES=30 NODES=40 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

Do not edit [osken-controller.env](../../../../../../source/scripts/osken-controller.env) in place for this experiment. The only controller delta between the two runs is the override file named in each command above.

## Focus & Evidence

Primary focus: controller logs plus `resource_stats.csv`.

- `controller_lan1.log` and `controller_lan2.log` must show `SelectiveSyncAlert`, `node_add` completion for `sel_sync_*`, manifest broadcast, reconfigure activity if any, `ScaleDownSelectiveAlert`, and `CleanupSelectiveAlert` or equivalent drain markers.
- `resource_stats.csv` must show the Tier 1 observability columns moving as expected: `coord_state_owner_lan=ACTIVE` or `tier1_lifecycle_active_count=1`, meaningful `coord_hot_doc_total`, and consumer-side `t_db_p95_ms_peer_lan` improvement after activation.

Secondary focus: `container_events.csv`, `service_logs/`, and `client_requests.csv`.

- `container_events.csv` is the lifecycle ground truth for `sel_sync_*` container add/remove events and residual cleanup debt.
- `service_logs/` helps confirm forwarder start, drain, and `drain_complete` behavior when controller logs alone are insufficient.
- `client_requests.csv` confirms that request failures stay bounded while Tier 1 is active and during teardown.

Tertiary focus: `phases_snapshot.json`, `policy_state.csv`, and coordinator-state observability fields.

- `phases_snapshot.json` anchors phase boundaries for pre/post activation comparisons.
- `policy_state.csv` is secondary only; the decisive Tier 1 truth signals are the controller logs, `coord_state_owner_lan`, and `tier1_lifecycle_active_count`.

## Metrics & Success Criteria

The Tier 1 path passes only if the enabled run and the control run together satisfy all criteria below.

1. Workload exercise.
   The phase file plus bounded seeded device set must produce a concentrated cross-region hot set in both directions. If hot-set concentration cannot be confirmed from `coord_hot_doc_total`, `top_hot_doc_hits`, and controller evidence, the run is invalid rather than failed.
2. Promotion path activation.
   In the enabled run, each hotspot direction must emit `SelectiveSyncAlert`, create a `sel_sync_*` node, and reach `ACTIVE` as seen in controller logs and in `resource_stats.csv` via `tier1_lifecycle_active_count=1` or `coord_state_owner_lan=ACTIVE`.
3. Service-quality effect.
   In the enabled run, `t_db_p95_ms_peer_lan` or the equivalent consumer-side DB-latency signal must improve within about 1 to 2 telemetry windows after `ACTIVE` compared with the immediately preceding hotspot window and compared with the control run for the same direction.
4. Stability during activation.
   Tier 1 activation must not introduce controller tracebacks, repeated selective-storage restart loops, or phase-local failure spikes above `1.0%` in `client_requests.csv`.
5. Teardown correctness.
   After each cooldown phase, the enabled run must show manifest revocation, `ScaleDownSelectiveAlert`, and final cleanup with no residual `sel_sync_*` containers by final idle.
6. Control comparison.
   The control run must complete without Tier 1 activation. If `SS_ENABLED=0` still appears to activate Tier 1, treat that as a correctness failure rather than a stability issue.

## Checkpoints

| Trigger | Question | Evidence | Runner action |
| --- | --- | --- | --- |
| Mid `tier1_hotspot_n1` | Did the first direction submit `SelectiveSyncAlert` and start the selective container? | Controller logs, `container_events.csv` | Report only |
| First window after `ACTIVE` | Did consumer-side `T_db` p95 begin to drop once Tier 1 reached service? | `resource_stats.csv`, controller logs | Report only |
| End `cooldown_n1` / `cooldown_n2` | Did manifest revoke and did selective cleanup complete? | Controller logs, `container_events.csv`, `service_logs/` | Report only |

## Validity Threats & Limitations

- The current driver does not pin exact hot-device IDs. Using `DEVICES=30` is an operational approximation that stays within current tooling, but it is still weaker than a future explicit pinned-subset phase schema.
- The plan intentionally uses no injected failures, so it does not validate hard-failure recovery or failed-backend avoidance.
- If the same hotspot profile also triggers Tier 2 strongly, interpretation becomes harder. The Tier 1 hotspot must therefore stay focused on selective-sync activation rather than full-replica forcing.

## Artifact Contract

Each run folder under `source/scripts/testing/metrics/<timestamp>_<run_label>/` must contain the standard run artifacts from [testing_overview.md](../../../testing_overview.md): `client_requests.csv`, `resource_stats.csv`, `resource_stats_debug.csv`, `policy_state.csv`, `per_node_stats.csv`, `container_events.csv`, `elasticity_events.csv`, `controller_lan1.log`, `controller_lan2.log`, `controller_env_snapshot.env`, `phases_snapshot.json`, and `service_logs/`.

Expected later analysis outputs:

- The usual run-summary outputs from the existing analysis toolchain in [analysis_toolchain.md](../../../analysis_toolchain.md).
- A focused Tier 1 comparison note that aligns activation timestamps, `T_db` p95 before and after `ACTIVE`, and teardown completion for both hotspot directions.
