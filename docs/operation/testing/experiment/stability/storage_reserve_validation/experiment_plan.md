# Experiment Plan - Storage Reserve Validation

## Intent

This experiment is now the reserve-liveness gate for the stability family. It answers one operational question: after the heartbeat contract fix, can each LAN prepare one standby full replica, reach `READY_RESERVED`, keep that reserve heartbeating outside VIP, and avoid the old cleanup loop long enough to survive the smoke workload? It is grounded in the reserve lifecycle described in [README.md](../../../../elasticy_manager/implementation/storage_persistent_reserve/README.md), the activation semantics in [storage_scale_up.md](../../../../elasticy_manager/scale_up/storage_scale_up.md), the mediator path in [main_n1.py](../../../../../../source/sdn_controller/main_n1.py), [main_n2.py](../../../../../../source/sdn_controller/main_n2.py), and [node_registry.py](../../../../../../source/sdn_controller/node_registry.py), and the real runner contract in [run_experiment.sh](../../../../../../source/scripts/testing/run_experiment.sh), [Makefile](../../../../../../source/scripts/Makefile), and [testing_overview.md](../../../testing_overview.md).

## Hypothesis / Expected Outcome

If the reserve path is healthy enough to study activation, the smoke run should show one clean reserve lifecycle per LAN: `[reserve] prepare_submitted`, `[reserve] ready_reserved`, repeated heartbeat events from the standby storage sidecar, no `[reserve] cleanup_submitted`, and reserve visibility in late telemetry windows including `demand_drop`. Activation is not required in this gate. If the run reaches `READY_RESERVED` and remains clean but never emits `[scale-up] storage triggered`, that is a trigger-gap outcome, not a reserve-liveness failure.

## RQ Linkage

This is still part of the reserved-standby branch of RQ3 in [system_to_thesis_map_rq_advanced.md](../../../../../../tese/miscelineous/system_to_thesis_map_rq_advanced.md), but only as a prerequisite gate. It confirms that a warm reserve can stay ready long enough to make activation experiments meaningful. It does not by itself answer the first-step activation question.

## Independent Variable & Held-Constant Set

- No workload sweep inside this gate. This is one fixed smoke-liveness run.
- Held constant workload sizing: `CLIENTS=8`, `DEVICES=600`, `NODES=100`.
- Held constant controller behavior: the shared base env [osken-controller.env](../../../../../../source/scripts/osken-controller.env) plus [storage_reserve_common.env](../../../../../../source/scripts/testing/controller_env_overrides/storage_reserve_common.env), which fixes `STORAGE_PERSISTENT_RESERVE_ENABLED=1`, `SS_ENABLED=0`, `MAX_DYNAMIC_COMPUTE=0`, and the relaxed storage-trigger bundle for the run; no `--fault-plan`, same code and images, same WAN profile, and same launch path.
- Held constant storage trigger bundle: `SCALEUP_W_STORAGE_CPU=0.60`, `SCALEUP_W_T_DB=0.40`, `SCALEUP_STORAGE_CPU_FLOOR=1.5`, `SCALEUP_STORAGE_CPU_SPAN=5`, `SCALEUP_T_DB_FLOOR=60`, `SCALEUP_T_DB_SPAN=250`, `SCALEUP_STORAGE_BASE_THRESHOLD=0.20`, `SCALEUP_STORAGE_REQUIRED=2`, `SCALEUP_STORAGE_WINDOW_SIZE=5`, and `SCALEUP_STORAGE_COOLDOWN_S=120`.
- Held constant scope: same-LAN Tier 2 reserve readiness and liveness only. Activation mapping is delegated to the companion threshold and load sweeps.

## Run Matrix

| Run label | What changes | Phase file |
| --- | --- | --- |
| `storage_reserve_smoke` | No variation. Single liveness gate run. | [phases_experiment_storage_reserve_smoke.json](../../../../../../source/scripts/testing/phases_experiment_storage_reserve_smoke.json) |

## Run Configuration

- Launch path: verified non-interactive `make` workflow from [Makefile](../../../../../../source/scripts/Makefile).
- `--phases-config`: `testing/phases_experiment_storage_reserve_smoke.json`.
- `--run-label`: `storage_reserve_smoke`.
- `--clients-per-lan`: `8` via `CLIENTS=8`.
- `--seed-devices`: `600` via `DEVICES=600`.
- `--seed-nodes`: `100` via `NODES=100`.
- Skip flags: `SKIP_CLIENTS=1`, `SKIP_SEED=1`, and `SKIP_SNAPSHOT=1` inside `run_experiment`, because the same `make` call already runs `setup_network`, `create_clients`, and `setup_test_data` before `run_experiment`.
- `--fault-plan`: omitted explicitly.
- Controller override: `OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/storage_reserve_common.env`.
- Images: no rebuild required unless the deployed images do not already contain the reserve-heartbeat fix.

Concrete command:

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
   OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/storage_reserve_common.env \
  RUN_LABEL=storage_reserve_smoke \
  PHASES_CONFIG=testing/phases_experiment_storage_reserve_smoke.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

## Focus & Evidence

Primary focus: `controller_lan1.log`, `controller_lan2.log`, `service_logs/`, `per_node_stats.csv`, and `resource_stats.csv`.

- `controller_lan1.log` and `controller_lan2.log` must show `[reserve] prepare_submitted` and `[reserve] ready_reserved`, with no `[reserve] cleanup_submitted` or `[registry] ... absent for` cleanup markers.
- `service_logs/edge_storage_lan1_dyn*.log` and `service_logs/edge_storage_lan2_dyn*.log` are the heartbeat evidence. They must show one initial `Pushing mongo_stats event` followed by repeated `Pushing heartbeat event` lines.
- `per_node_stats.csv` and `resource_stats.csv` confirm that the reserve remains visible into late windows, including `demand_drop`, and that `storage_count` occasionally reaches `2` while the standby is alive.

Secondary focus: `elasticity_events.csv`, `node_lifecycle_timings.csv`, and `container_events.csv`.

- Use `elasticity_events.csv` and `node_lifecycle_timings.csv` to confirm that the reserve became ready only once per LAN.
- Use `container_events.csv` to check for duplicate reserve churn or late cleanup debt.

## Metrics & Success Criteria

1. Reserve readiness.
   Both LANs must show `[reserve] prepare_submitted` followed by `[reserve] ready_reserved` during `baseline` or early `reserve_trigger_lan1`.
2. Heartbeat persistence.
   Each standby storage service log must show repeated heartbeat events at roughly the heartbeat interval through the trigger window and into `demand_drop`.
3. No cleanup regression.
   Neither controller log may contain `[reserve] cleanup_submitted` or `[registry] ... absent for 18 windows` for the reserved MACs.
4. Telemetry visibility.
   At least one reserve MAC must still appear in `per_node_stats.csv` during `demand_drop`, and `resource_stats.csv` should still show `storage_count=2` in at least one late window.
5. Escalation rule.
   If the run satisfies items 1 through 4 but does not emit `[scale-up] storage triggered`, classify the outcome as `liveness passed, activation untested` and continue with [storage_reserve_use_validation/experiment_plan.md](../storage_reserve_use_validation/experiment_plan.md). Do not start the threshold or load tuning sweeps until reserve has reached `reserve-used` there.

## Checkpoints

| Trigger | Question | Evidence | Runner action |
| --- | --- | --- | --- |
| End of `baseline` | Has each LAN already reached `READY_RESERVED`? | Controller logs, `elasticity_events.csv` | Report only |
| About 60 seconds after first readiness | Are heartbeat events now visible from each standby reserve? | `service_logs/` | Report only |
| Mid `demand_drop` | Does the reserve still appear in telemetry without cleanup markers? | `per_node_stats.csv`, `resource_stats.csv`, controller logs | Report only |

## Validity Threats & Limitations

- This run is intentionally a liveness gate, not an activation proof. In the completed June 4 smoke campaign, reserve liveness passed while the storage trigger score still stayed below the current threshold, so no activation occurred.
- The current traffic generator cannot create a truly one-sided source-only hotspot. `hotspot_direction` gates cross-region reads, but both LANs still generate local traffic at the same phase rate.
- No `--fault-plan` is used, so recovery-distress activation remains out of scope here.

## Artifact Contract

The run folder under `source/scripts/testing/metrics/<timestamp>_storage_reserve_smoke/` must retain the standard artifacts from [testing_overview.md](../../../testing_overview.md): `client_requests.csv`, `resource_stats.csv`, `resource_stats_debug.csv`, `policy_state.csv`, `per_node_stats.csv`, `container_events.csv`, `controller_lan1.log`, `controller_lan2.log`, `controller_env_snapshot.env`, `phases_snapshot.json`, and `service_logs/`. This gate also expects `elasticity_events.csv` and `node_lifecycle_timings.csv` for reserve-lifecycle timing.

Expected later analysis outputs:

- The normal latency/resource summaries from the existing testing toolchain.
- A short reserve-liveness note that records reserve prepare time, ready time, first heartbeat time, late-window reserve visibility, and whether activation remained untested.

The next stability experiment in this reserve sequence is [storage_reserve_use_validation/experiment_plan.md](../storage_reserve_use_validation/experiment_plan.md). The threshold and load sweeps become optional follow-on tuning passes only after reserve use is proved there.
