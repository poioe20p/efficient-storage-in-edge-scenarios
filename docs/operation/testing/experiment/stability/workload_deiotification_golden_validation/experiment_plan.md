# Experiment Plan — Workload De-IoT-ification Golden Validation

**Status**: 🔵 Designed · **Date**: 2026-07-02
**Parent**: [../../../workload_deiotification_plan.md](../../../workload_deiotification_plan.md)
**Configuration references**: [../../../golden_config.md](../../../golden_config.md), [../../rq1_thesis_final/experiment_plan.md](../../rq1_thesis_final/experiment_plan.md)

## Intent

Validate that the implemented workload rewrite from device/dashboard terminology
to the content/feed workload surface is correct under the current golden
configuration and that the system still functions operationally at the active
production-like scale.

This experiment answers one binary gate question:

**Can the renamed workload run end to end with the canonical golden phase file,
the RQ1-thesis-final runtime envelope (`WAN_RTT_MS=200`, `VIP_HARD_TIMEOUT=60`,
`curl --max-time 30`), all four elasticity mechanisms exercised, and overall
request failure below 20 percent?**

This is a validation gate for the de-IoT-ification implementation, not a new
performance comparison study.

## Hypothesis / Expected Outcome

If the implementation is correct and the current system remains healthy:

- the run completes all canonical phases from `testing/phases.json`
- the active snapshot surface exposes only `content_items.json` and
  `user_profiles.json`
- `client_requests.csv` contains only the renamed request kinds
  (`content_lookup`, `feed_ranking`, `service_pressure`, `content_update`,
  `content_aggregate`)
- storage reserve activation, storage scale-out, compute scale-up, and Tier 1
  selective sync all exercise during the run
- overall request failure remains below 20 percent
- controller logs contain no unhandled Python traceback

The analyst should be able to mark the run `pass`, `miss`, or `inconclusive`
from the artifacts alone.

## RQ Linkage

This is not an RQ measurement experiment. It reuses the runtime envelope from
the thesis-final RQ1 campaign so that workload-surface validation happens under
the same operational conditions already accepted for golden-scale runs.

Independent variable: none. This is a single-run binary validation of the
current implementation state.

## Independent Variable & Held-Constant Set

- **Independent variable**: none — single-run validation gate
- **Held constant set**:

| Parameter            | Value                                                             | Why held constant                                                                              |
| -------------------- | ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Phase file           | `testing/phases.json`                                           | Canonical active content-discovery workload profile                                            |
| Controller override  | `testing/controller_env_overrides/current_state_integrated.env` | Current golden mechanism bundle                                                                |
| `WAN_RTT_MS`       | `200`                                                           | Matches the thesis-final validated WAN setting                                                 |
| `VIP_HARD_TIMEOUT` | `60`                                                            | Must be inherited from the controller override and confirmed in`controller_env_snapshot.env` |
| `CURL_MAX_TIME`    | `30`                                                            | Matches the thesis-final uncensored client timeout                                             |
| `CLIENTS`          | `48`                                                            | Golden config active client load                                                               |
| `CONTENT_ITEMS`    | `6000`                                                          | Golden config dataset cardinality                                                              |
| `USERS`            | `100`                                                           | Golden config profile count                                                                    |
| `STORAGE_CPUS`     | `0.10`                                                          | Golden config storage CPU budget                                                               |
| Fault plan           | omitted                                                           | No synthetic failures in this validation                                                       |
| Images / code        | current implemented workload rewrite                              | The experiment validates the already-implemented state; it does not test an alternate build    |

Prerequisite:

- If the deployed `edge_server` container image predates the workload rewrite,
  rebuild it with `make -C source/docker build-edge-server` and redeploy before
  launch. That is a launch prerequisite, not an experiment variable.

## Run Matrix

| Run | Label                                         | What changes                                                                                         | Phase file              |
| --- | --------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ----------------------- |
| A   | `workload_deiotification_golden_validation` | No comparison axis; validates the current renamed workload surface under the golden runtime envelope | `testing/phases.json` |

Run order: single run only.

If the launch fails before the run reaches the first stress phase, one identical
rerun is allowed. That rerun is recovery from an invalid launch, not a second
experimental condition.

## Run Configuration

Launch with the current top-level operator surface so the validation covers the
same workflow operators actually use.

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=workload_deiotification_golden_validation \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=200 CLIENTS=48 CONTENT_ITEMS=6000 USERS=100 STORAGE_CPUS=0.10 \
  CURL_MAX_TIME=30 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

Configuration notes:

- `CURL_MAX_TIME=30` is passed explicitly even though the traffic generator now
  defaults to 30, so the run folder documents the intended envelope.
- `VIP_HARD_TIMEOUT=60` is not passed as a top-level make variable; it must
  come from `current_state_integrated.env` and be confirmed in the run-folder
  env snapshot.
- `--fault-plan` is intentionally omitted.
- `setup_test_data` is part of the same top-level launch because the validation
  should cover the renamed seeding and snapshot-export workflow too.

## Focus & Evidence

**Primary focus**: `client_requests.csv` + `resource_stats.csv` + controller logs.

| Artifact                                         | What it answers                                                                                                       |
| ------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------- |
| `client_requests.csv`                          | Whether the request surface stayed on the renamed workload labels and whether overall failure stays below the gate    |
| `resource_stats.csv`                           | Whether`storage_count`, `server_count`, and `tier1_lifecycle_active_count` show the expected mechanism exercise |
| `controller_lan1.log`, `controller_lan2.log` | Whether reserve activation and scale decisions fired and whether any traceback occurred                               |

**Secondary focus**: snapshot directory + `container_events.csv` + run snapshots.

| Artifact                                           | What it answers                                                                                 |
| -------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| `source/scripts/testing/data/workload_snapshot/` | Whether the live snapshot surface exposes only`content_items.json` and `user_profiles.json` |
| `container_events.csv`                           | Whether dynamic storage, dynamic compute, and`sel_sync_*` containers appeared and drained     |
| `phases_snapshot.json`                           | Whether the run used the canonical active phase file                                            |
| `controller_env_snapshot.env`                    | Whether the run actually used`VIP_HARD_TIMEOUT=60`                                            |

State the analysis emphasis explicitly:

- **Primary**: controller logs + `resource_stats.csv` + `client_requests.csv`
- **Secondary**: `container_events.csv` + snapshot-directory state + run snapshots

## Metrics & Success Criteria

The run passes only if every criterion below is met.

| #  | Criterion                       | How it is checked                                                                               | Pass condition                                                                                                               |
| -- | ------------------------------- | ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| 1  | Run completion                  | Compare`client_requests.csv` / `resource_stats.csv` phases against `phases_snapshot.json` | Rows exist for all canonical phases in`testing/phases.json`                                                                |
| 2  | Overall failure rate            | `client_requests.csv`                                                                         | Total failed requests < 20% of all requests                                                                                  |
| 3  | Renamed request surface only    | Unique request labels in`client_requests.csv`                                                 | Labels are a subset of`content_lookup`, `feed_ranking`, `service_pressure`, `content_update`, `content_aggregate`  |
| 4  | Renamed snapshot surface only   | Live snapshot directory after`setup_test_data`                                                | `content_items.json` and `user_profiles.json` exist; legacy snapshot filenames are absent                                |
| 5  | Storage reserve activation      | Controller logs                                                                                 | At least one reserve-activation marker such as`[reserve] activated` appears                                                |
| 6  | Storage scale-out exercised     | `resource_stats.csv`                                                                          | `storage_count` rises above the baseline fixed-node level during `storage_storm` or `tier1_hotspot`                    |
| 7  | Compute scale-up exercised      | `resource_stats.csv`                                                                          | `server_count` rises above the baseline fixed-node level during `compute_spike`                                          |
| 8  | Tier 1 selective sync exercised | `resource_stats.csv` or `container_events.csv`                                              | `tier1_lifecycle_active_count >= 1` in at least one telemetry window, or a `sel_sync_*` container reaches active service |
| 9  | Runtime envelope respected      | `controller_env_snapshot.env` and run configuration                                           | `VIP_HARD_TIMEOUT=60`, `WAN_RTT_MS=200`, `CURL_MAX_TIME=30`                                                            |
| 10 | Control-plane health            | `controller_lan1.log`, `controller_lan2.log`                                                | No unhandled Python traceback                                                                                                |

Metric interpretation rules:

- Treat `http_status` values that the current analysis CLIs classify as
  failures as failures here too.
- The baseline fixed-node level for `storage_count` and `server_count` should
  be taken from the initial low-load phase of the same run, not from a separate
  historical reference run.
- Criteria 5 and 6 are intentionally separate: reserve activation proves the
  standby path engaged, while `storage_count` growth proves additional storage
  capacity actually served the run.

## Checkpoints

| Trigger                  | Question                                                     | Evidence                                                          | Runner action |
| ------------------------ | ------------------------------------------------------------ | ----------------------------------------------------------------- | ------------- |
| After`setup_test_data` | Is the renamed snapshot surface clean?                       | Snapshot directory contents                                       | Report only   |
| Mid`storage_storm`     | Did reserve activation fire and did`storage_count` rise?   | Controller logs,`resource_stats.csv`                            | Report only   |
| Mid`tier1_hotspot`     | Did Tier 1 reach active state?                               | `resource_stats.csv`, `container_events.csv`, controller logs | Report only   |
| Mid`compute_spike`     | Did compute scale-up raise`server_count` above baseline?   | `resource_stats.csv`                                            | Report only   |
| End of`cooldown`       | Did the run finish cleanly with acceptable overall failures? | `client_requests.csv`, controller logs                          | Report only   |

## Validity Threats & Limitations

1. **Single-run gate** — this plan validates correctness and operational health,
   not reproducibility or within-mode variance.
2. **Mechanism timing sensitivity** — a single missed activation does not by
   itself prove the workload rewrite is broken. If the run is otherwise healthy
   but one mechanism gate misses narrowly, repeat the identical run once before
   attributing failure to the rewrite.
3. **Overall failure threshold only** — `< 20%` validates operational
   acceptability, but it does not replace deeper per-phase performance analysis.
4. **Canonical-profile dependency** — if one mechanism does not exercise in this
   validation run, the next diagnostic step is the current canonical workload
   profile and mechanism thresholds, not immediate redesign of the rewrite.

## Artifact Contract

The run must produce the standard run-folder layout described in
`testing_overview.md`, including at least:

- `client_requests.csv`
- `resource_stats.csv`
- `resource_stats_debug.csv`
- `per_node_stats.csv`
- `container_events.csv`
- `elasticity_events.csv` (post-run reconstructed artifact — see below)
- `controller_lan1.log`
- `controller_lan2.log`
- `controller_env_snapshot.env`
- `phases_snapshot.json`
- `service_logs/`

`elasticity_events.csv` is not produced automatically by the run; after the run
completes, generate it with:

```bash
python3 source/scripts/tools/parse_elasticity_logs.py \
  <run_dir>/controller_lan1.log <run_dir>/controller_lan2.log \
  -o <run_dir>/elasticity_events.csv
```

Additional validation-specific expectations:

- `controller_env_snapshot.env` records `VIP_HARD_TIMEOUT=60`
- `phases_snapshot.json` matches the canonical active content-discovery profile
- the live snapshot directory exposes only `content_items.json` and
  `user_profiles.json`

Expected later `analysis/` outputs after the runner finishes:

- `cli_endpoint_breakdown`
- `cli_simple_run`

Those analysis outputs are not the primary pass/fail signal, but they should
still be runnable on the completed validation run.