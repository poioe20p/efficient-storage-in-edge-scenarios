# Experiment Plan - Storage Reserve Use Validation

## Intent

This experiment answers one operational question: after a same-LAN storage trigger activates the ready reserve, can the promoted reserve actually carry `VIP_DATA` traffic instead of remaining only a control-plane activation marker? It is grounded in the reserve activation path in [main_n1.py](../../../../../../source/sdn_controller/main_n1.py), [main_n2.py](../../../../../../source/sdn_controller/main_n2.py), and [node_registry.py](../../../../../../source/sdn_controller/node_registry.py), the `VIP_DATA` selection path in [ingress.py](../../../../../../source/sdn_controller/_vip_routing/ingress.py), the edge-server epoch/runtime behavior in [vip_data_mongo_runtime.py](../../../../../../source/docker/edge_server/source/vip_data_mongo_runtime.py) and [vip_data_edge_epoch_and_recovery.md](../../../../vip_routing/vip_data_edge_epoch_and_recovery.md), the storage activity telemetry contract in [mongo_telemetry.py](../../../../../../source/docker/edge_storage_server/mongo_telemetry.py) and [aggregator.py](../../../../../../source/docker/local_state_server/aggregator.py), and the standard runner/artifact contract in [run_experiment.sh](../../../../../../source/scripts/testing/run_experiment.sh), [Makefile](../../../../../../source/scripts/Makefile), and [testing_overview.md](../../../testing_overview.md).

## Hypothesis / Expected Outcome

Activation alone may not be enough to prove use, because the edge server keeps one LAN-pinned direct `MongoClient` and the controller keeps broad `VIP_DATA` DNAT/SNAT rules until they idle out. Under the existing aggressive threshold profile, the control run may emit `[reserve] activated` but still leave traffic pinned to the pre-activation backend. The rebind run should emit `[reserve] activated`, then after a `service_pressure`-only gap longer than both `maxIdleTimeMS` and the `VIP_DATA` idle timeout, at least one fresh `vip_data(n1): ... -> real=<activated reserve IP>` selection and at least one post-gap `mongo_stats` event from the activated reserve. If activation occurs but those post-gap use markers never appear, the outcome is `activated but not used`.

## RQ Linkage

This is still part of the reserved-standby branch of RQ3 in [system_to_thesis_map_rq_advanced.md](../../../../../../tese/miscelineous/system_to_thesis_map_rq_advanced.md), but it is the usability gate for the reserve path. The threshold and load sweeps are follow-on tuning passes only after this plan has shown that activated reserve can become request-visible capacity on the data plane.

## Prerequisites

- Pass [storage_reserve_validation/experiment_plan.md](../storage_reserve_validation/experiment_plan.md) first. Do not run this plan if reserve liveness is still unstable.
- Current repository state: [../storage_reserve_validation/results.md](../storage_reserve_validation/results.md) already records a passed liveness gate, so this plan is now the next reserve-side experiment to run.
- Treat this plan as the gate before any threshold or load tuning. Only after it reaches `reserve-used` should [storage_reserve_threshold_sweep/experiment_plan.md](../storage_reserve_threshold_sweep/experiment_plan.md) or [storage_reserve_load_sweep/experiment_plan.md](../storage_reserve_load_sweep/experiment_plan.md) be considered.
- Concrete default for this plan: use the existing aggressive override [storage_reserve_threshold_t08.env](../../../../../../source/scripts/testing/controller_env_overrides/storage_reserve_threshold_t08.env). If the control run still stays waiting-only under that profile, stop and resolve the activation boundary first instead of reinterpreting the use-validation result.
- Both rows in this plan use the shared reserve workload family: [phases_experiment_storage_reserve_shared.json](../../../../../../source/scripts/testing/phases_experiment_storage_reserve_shared.json) for the control run and [phases_experiment_storage_reserve_shared_rebind.json](../../../../../../source/scripts/testing/phases_experiment_storage_reserve_shared_rebind.json) for the rebind run. These replace the previous `phases_experiment_storage_reserve_activation_probe.json` and `phases_experiment_storage_reserve_use_validation.json`, which lacked a sustained-use phase after activation.

## Independent Variable & Held-Constant Set

- Independent variable: presence of a post-activation `VIP_DATA` rebind window in the phase profile.
- Held constant workload sizing: `CLIENTS=8`, `DEVICES=600`, `NODES=100`.
- Held constant controller behavior: [storage_reserve_threshold_t08.env](../../../../../../source/scripts/testing/controller_env_overrides/storage_reserve_threshold_t08.env), which fixes `STORAGE_PERSISTENT_RESERVE_ENABLED=1`, `SS_ENABLED=0`, `MAX_DYNAMIC_COMPUTE=0`, `SCALEUP_STORAGE_BASE_THRESHOLD=0.08`, and the same relaxed storage-trigger bundle used by the reserve-threshold sweep.
- Held constant hotspot direction: `lan2_to_lan1`, so LAN 1 is the stressed data plane and the expected reserve-under-use side.
- Held constant scope: same-LAN reserve activation plus first post-activation data-plane use only. Tier 1, compute elasticity, recovery-distress activation, and ordinary multi-step storage scale-out beyond the first reserve are out of scope.

## Run Matrix

| Run label | What changes | Phase file |
| --- | --- | --- |
| `reserve_use_control_t08` | Standard 5-phase workload: ramp → hotspot → **sustained_use** → drop. The `sustained_use` phase (180s @ 7 r/s, 80% cross-region) is where the activated reserve must carry real traffic. | [phases_experiment_storage_reserve_shared.json](../../../../../../source/scripts/testing/phases_experiment_storage_reserve_shared.json) |
| `reserve_use_rebind_t08` | Same as control but with a 45s `vip_rebind_gap` (service_pressure-only) inserted between `storage_hotspot` and `sustained_use`. The gap forces the edge server's MongoClient to expire (`maxIdleTimeMS=30000`), so fresh connections during `sustained_use` must route through the recovery VIP to the activated reserve. | [phases_experiment_storage_reserve_shared_rebind.json](../../../../../../source/scripts/testing/phases_experiment_storage_reserve_shared_rebind.json) |

Run order:

1. Run `reserve_use_control_t08` first.
2. If it stays waiting-only, stop. Do not proceed to the tuning sweeps until an activating candidate is found.
3. If it activates, run `reserve_use_rebind_t08` next.

## Run Configuration

- Launch path: verified non-interactive `make` workflow from [Makefile](../../../../../../source/scripts/Makefile).
- `--clients-per-lan`: `8` via `CLIENTS=8`.
- `--seed-devices`: `600` via `DEVICES=600`.
- `--seed-nodes`: `100` via `NODES=100`.
- Skip flags: `SKIP_CLIENTS=1`, `SKIP_SEED=1`, and `SKIP_SNAPSHOT=1` inside `run_experiment`.
- `--fault-plan`: omitted explicitly.
- Controller override: `OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/storage_reserve_threshold_t08.env`.
- Images: no rebuild required unless the deployed images no longer match the code under test.

Concrete control command:

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/storage_reserve_threshold_t08.env \
  RUN_LABEL=reserve_use_control_t08 \
  PHASES_CONFIG=testing/phases_experiment_storage_reserve_shared.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

Concrete rebind command:

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/storage_reserve_threshold_t08.env \
  RUN_LABEL=reserve_use_rebind_t08 \
  PHASES_CONFIG=testing/phases_experiment_storage_reserve_shared_rebind.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

Shared phase file used by `reserve_use_control_t08`: [phases_experiment_storage_reserve_shared.json](../../../../../../source/scripts/testing/phases_experiment_storage_reserve_shared.json)

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

Rebind variant: [phases_experiment_storage_reserve_shared_rebind.json](../../../../../../source/scripts/testing/phases_experiment_storage_reserve_shared_rebind.json) — same as above but inserts a 45s `vip_rebind_gap` (100% service_pressure, 3 r/s, 0% cross-region) between `storage_hotspot` and `sustained_use`.

Why this shape replaces the old probe:

- The old probe (`baseline → activation_probe → demand_drop`) had a fundamental flaw: the load cliff-dropped immediately after activation, so the activated reserve never served sustained traffic. The `demand_drop` at 180s exceeded the 120s scale-down cooldown, guaranteeing the reserve would be removed before the run ended.
- This shared workload adds a **gradual ramp** (`storage_ramp`, 120s) that builds load naturally instead of cliff-jumping from 2 to 10 req/s.
- **`sustained_use`** (180s @ 7 r/s, 80% cross-region) is the phase the old probe was missing — the activated reserve must carry real traffic here. Evidence comes from `vip_data(n1): ... -> real=<reserve IP>` selections and `mongo_stats` events during this phase.
- **`demand_drop` at 120s** matches `SCALEUP_STORAGE_COOLDOWN_S=120`, eliminating the post-cooldown window where scale-down could fire and create cycling.
- The rebind variant inserts a 45s `vip_rebind_gap` (100% service_pressure, 3 r/s, 0% cross-region) between `storage_hotspot` and `sustained_use` — the gap exceeds `maxIdleTimeMS=30000`, forcing the edge server to create a fresh MongoClient. Fresh connections during `sustained_use` then route through the recovery VIP (`10.0.0.252`) to prove the reserve is usable.
- Total duration: 780s (13 min) for the control workload, 825s (~14 min) for the rebind variant — both within the 10–15 minute target.

## Focus & Evidence

Primary focus: `controller_lan1.log`, `service_logs/edge_server_*.log`, `service_logs/edge_storage_lan1_dyn*.log`, and `per_node_stats.csv`.

- `controller_lan1.log` must show `[reserve] activated` for LAN 1 and record the activated reserve IP/MAC. During `post_activation_use`, it must then show at least one `select_storage(n1): selected=<reserve MAC>` or `vip_data(n1): client=<edge_server_ip> -> vip=<VIP_DATA_N1_IP> -> real=<activated reserve IP>` line.
- `service_logs/edge_server_*.log` must show a fresh `Created MongoClient for lan1 ...` line after `vip_rebind_gap` begins and before or during `sustained_use`. That is the evidence that the edge server opened a new `VIP_DATA` session rather than reusing the pre-activation socket.
- `service_logs/edge_storage_lan1_dyn*.log` must show at least one post-gap `Pushing mongo_stats event` from the activated reserve. A pure heartbeat-only pattern is not enough.
- `per_node_stats.csv` must show the activated reserve as `role=storage` with `request_count > 0` in at least one `sustained_use` window. Here `request_count` is the storage-side `sample_count`, so it is activity evidence rather than a query-count metric.

Secondary focus: `client_requests.csv`, `resource_stats.csv`, `elasticity_events.csv`, and `node_lifecycle_timings.csv`.

- `client_requests.csv` shows whether any post-gap recovery in failure rate or p95 latency appears once fresh routing can see the promoted reserve.
- `resource_stats.csv` confirms that `storage_count=2` remains visible after activation and into `sustained_use`.
- `elasticity_events.csv` and `node_lifecycle_timings.csv` are the timing references for reserve ready, trigger, activation, and replenish submission.

## Metrics & Success Criteria

1. Activation validity.
  `reserve_use_control_t08` is valid only if LAN 1 reaches `[reserve] activated` during `storage_hotspot` or `sustained_use`. If it stays waiting-only, stop and resolve the activation candidate first; do not reinterpret the use-validation result or proceed to tuning.
2. Fresh-session validity.
   `reserve_use_rebind_t08` is valid only if the first DB-bearing requests after `vip_rebind_gap` produce at least one fresh `Created MongoClient for lan1 ...` line in `service_logs/edge_server_*.log`.
3. Reserve-used classification.
   `reserve_use_rebind_t08` proves actual use only if, after the fresh MongoClient line, `controller_lan1.log` shows at least one `select_storage(n1): selected=<reserve MAC>` or `vip_data(n1): ... -> real=<activated reserve IP>` line during `sustained_use`.
4. Storage-side corroboration.
   The activated reserve must emit at least one post-gap `Pushing mongo_stats event`, and `per_node_stats.csv` must show `request_count > 0` for that reserve in at least one `sustained_use` window.
5. Control interpretation.
   If the control run activates but never shows reserve-used markers, classify it as `activated but pinned`. If it already shows reserve-used markers, treat the rebind run as confirmation rather than isolation.
6. Overall success.
   The experiment succeeds when `reserve_use_rebind_t08` reaches `reserve-used` classification. If it reaches `activated but pinned` again, the reserve path is not yet request-visible under the current data-plane lifecycle.
7. Follow-on rule.
  Threshold and load tuning are allowed only after this plan reaches `reserve-used`.

## Checkpoints

| Trigger | Question | Evidence | Runner action |
| --- | --- | --- | --- |
| End of `baseline` | Is LAN 1 already `READY_RESERVED` before the activation hotspot begins? | Controller logs, `elasticity_events.csv` | Report only |
| First `[reserve] activated` | Which MAC/IP became the promoted reserve? | `controller_lan1.log`, `node_lifecycle_timings.csv` | Report only |
| End of `vip_rebind_gap` | Has the run completed more than 30 s with no `VIP_DATA` work? | Current phase, edge-server logs, controller logs | Report only |
| First 30 s of `post_activation_use` | Did the edge server create a fresh MongoClient and did the controller select the promoted reserve? | `service_logs/edge_server_*.log`, `controller_lan1.log` | Report only |
| Mid `post_activation_use` | Is the promoted reserve now emitting `mongo_stats` activity instead of only heartbeat? | `service_logs/edge_storage_lan1_dyn*.log`, `per_node_stats.csv` | Report only |

## Validity Threats & Limitations

- This repository does not yet contain an analyzed activating reserve run. The plan uses [storage_reserve_threshold_t08.env](../../../../../../source/scripts/testing/controller_env_overrides/storage_reserve_threshold_t08.env) as the concrete default because it is the lowest existing threshold candidate, but activation is still empirical, not assumed.
- `VIP_DATA` selection is per fresh connection, not per request. Even after the rebind gap, the controller may legitimately reselect the primary again. This plan proves whether the promoted reserve can carry traffic when given a fresh routing opportunity; it does not prove that the WSM will prefer reserve under every load regime.
- `controller_lan1.log` only shows new `vip_data(...)` selections when no matching broad flow already exists. The `vip_rebind_gap` is deliberately longer than the documented `VIP_DATA` idle timeout so the post-gap phase has a fresh selection opportunity.
- `per_node_stats.csv` storage `request_count` is activity-frame count (`sample_count`), not actual query count. Use it only together with controller and service-log evidence.
- No `--fault-plan` is used, so recovery-distress activation and recovery-VIP behavior remain out of scope.

## Artifact Contract

Each run folder under `source/scripts/testing/metrics/<timestamp>_<run_label>/` must contain the standard artifacts described in [testing_overview.md](../../../testing_overview.md): `client_requests.csv`, `resource_stats.csv`, `resource_stats_debug.csv`, `policy_state.csv`, `per_node_stats.csv`, `container_events.csv`, `elasticity_events.csv`, `controller_lan1.log`, `controller_lan2.log`, `controller_env_snapshot.env`, `phases_snapshot.json`, and `service_logs/`.

Expected later analysis outputs:

- The normal run summaries from the existing analysis toolchain.
- A short use-validation note that records reserve ready time, activation time, the activated reserve MAC/IP, the first post-gap `Created MongoClient` timestamp, the first `vip_data(... -> real=<reserve IP>)` timestamp if any, the first post-gap reserve `mongo_stats` timestamp if any, and whether the outcome was `reserve-used`, `activated but pinned`, or `waiting-only`.
