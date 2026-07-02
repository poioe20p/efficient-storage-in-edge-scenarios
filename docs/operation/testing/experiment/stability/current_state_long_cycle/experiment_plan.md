# Experiment Plan - Current State Integrated Baseline Cycle (v5.6 — Conntrack VIP_DATA)

**Status**: Conntrack VIP_DATA routing deployed (2026-06-08). The `ct_state` reply-rule bug
identified in the dedicated [conntrack_routing experiment](../conntrack_routing/experiment_plan.md)
is fixed. This v5.6 cycle is the first baseline pair with the fix in place.

## Intent

This experiment evaluates the current integrated system state with one single phased workload profile that must exercise the mechanisms already implemented in the platform inside the same run: Tier 2 storage scale-out, Tier 1 selective-sync activation, compute scale-out, conntrack VIP_DATA routing, and final cleanup. It answers one operational question: is the current code and controller snapshot in a stable enough state that all elasticity mechanisms can be exercised together, repeatedly, and cleanly before newer features are added? The plan is grounded in the testing contract in [testing_overview.md](../../../testing_overview.md), the current traffic-generator schema in [traffic_generator.md](../../../traffic_generator.md), the shared runner in [run_experiment.sh](../../../../../../source/scripts/testing/run_experiment.sh), the approved `make` entrypoint in [Makefile](../../../../../../source/scripts/Makefile), the controller knobs in [osken-controller.env](../../../../../../source/scripts/osken-controller.env) and [scaling_config.py](../../../../../../source/sdn_controller/scaling_config.py), the Tier 1 promotion gate in [promotion.py](../../../../../../source/sdn_controller/selective_sync/promotion.py) and [hotness.py](../../../../../../source/sdn_controller/selective_sync/hotness.py), the canonical phase file [phases.json](../../../../../../source/scripts/testing/phases.json), and the historical combined-policy evidence recorded in [experiment_campaign_brief.md](../../../experiment_campaign_brief.md).

## Hypothesis / Expected Outcome

If the current system state is baseline-ready, two identical runs of the integrated profile should both complete all phases, raise `storage_count` above `1` during the storage-locality phases, emit `SelectiveSyncAlert` and reach `ACTIVE` during the canonical `tier1_hotspot` window, trigger dynamic compute during the feed-ranking-heavy tail, and return every dynamic compute, storage, and selective-sync container to baseline by final idle. If any mechanism remains unexercised in a run, or if one of the exercised mechanisms fails to drain cleanly, the baseline cycle is incomplete even if the rest of the run looks healthy.

With conntrack VIP_DATA routing deployed, additional expectations apply:

- **Overall failure rate ≤3%** (vs v5.5 B at 6.7% with static NAT)
- **Compute phases ≤5%** (vs 56-65% with static NAT — stale-rule root cause eliminated)
- **Zero epoch rotations** during storage-churn phases (v5.5 had ≥10)
- **Conntrack entries >0** in `resource_stats.csv` (`conntrack_entries_n1`, `conntrack_entries_n2`)
- **Reply rules with `n_packets > 0`** in OVS flow dumps (evidence ct_state fix is active)

These expectations are derived from the [conntrack_routing experiment v1 results](../conntrack_routing/results.md).

## Independent Variable & Held-Constant Set

- Independent variable: run replicate only (`current_state_integrated_a` versus `current_state_integrated_b`).
- Held constant: current repository HEAD, current container images, the shared base env [osken-controller.env](../../../../../../source/scripts/osken-controller.env) plus the fixed override [current_state_integrated.env](../../../../../../source/scripts/testing/controller_env_overrides/current_state_integrated.env), the canonical phase file [phases.json](../../../../../../source/scripts/testing/phases.json), no `--fault-plan`, same operator host/VM, same WAN profile, same launch path, and no code, env, or image changes between the two runs.
- Held constant controller knobs: use [current_state_integrated.env](../../../../../../source/scripts/testing/controller_env_overrides/current_state_integrated.env) unchanged for both replicates. Storage: `SS_ENABLED=1`, `MAX_DYNAMIC_STORAGE=5`, `SCALEUP_STORAGE_BASE_THRESHOLD=0.12`. Compute: `MAX_DYNAMIC_COMPUTE=6`, `SCALEUP_COMPUTE_BASE_THRESHOLD=0.20`, `SCALEUP_CPU_FLOOR=3`, `SCALEUP_T_PROC_FLOOR=15`, `SCALEDOWN_COMPUTE_COOLDOWN_S=120`, `SCALE_DOWN_COMPUTE_REQUIRED=9` (see changelog for rationale).
- Held constant workload sizing: `CLIENTS=8`, `CONTENT_ITEMS=600`, `USERS=100` for both runs. The current canonical phase file uses `client_fraction` values from `0.1` to `1.0` so low-load windows remain observable without changing the launch surface between replicates. Tier 1 remains compatible because promotion is gated by collection-level read volume and cross-region ratio rather than by a per-document minimum-hit threshold.
- Held constant conntrack routing: VIP_DATA uses conntrack forward + reply rules (Phases 1-4 implementation + ct_state fix). The controller files `source/sdn_controller/_vip_routing/flows.py` and `ingress.py` are volume-mounted — no Docker image rebuild needed. These files MUST NOT change between the two replicates.
- Abort rule: if any runtime-bearing file, controller env value, or image changes after `current_state_integrated_a`, discard the pair and restart from `current_state_integrated_a` under a new label family.

## Run Matrix

| Run label | What changes | Phase file |
| --- | --- | --- |
| `current_state_integrated_a` | First integrated baseline replicate | [phases.json](../../../../../../source/scripts/testing/phases.json) |
| `current_state_integrated_b` | Second integrated baseline replicate | [phases.json](../../../../../../source/scripts/testing/phases.json) |

Run order is fixed: `current_state_integrated_b` only starts after `current_state_integrated_a` artifacts are copied back and the operator confirms there were no code, env, or image changes in between.

## Run Configuration

- Launch path: verified non-interactive `make` workflow from [Makefile](../../../../../../source/scripts/Makefile).
- `--phases-config`: `source/scripts/testing/phases.json` via `PHASES_CONFIG=testing/phases.json`.
- `--run-label`: `current_state_integrated_a` and `current_state_integrated_b`.
- `--batch-dir`: omitted in the default `make` path.
- `--clients-per-lan`: `8` via `CLIENTS=8`.
- `--seed-content-items`: `600` via `CONTENT_ITEMS=600`.
- `--seed-users`: `100` via `USERS=100`.
- Skip flags: `SKIP_CLIENTS=1`, `SKIP_SEED=1`, and `SKIP_SNAPSHOT=1` inside `run_experiment`, because the same `make` call already runs `setup_network`, `create_clients`, and `setup_test_data` before `run_experiment`.
- `--fault-plan`: omitted explicitly.
- Controller override: `OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env` so both runs launch with the same integrated controller state.
- Code/config toggles: keep the shared base env [osken-controller.env](../../../../../../source/scripts/osken-controller.env) unchanged across both runs. Do not rebuild images or retune thresholds between the two replicates unless the operator intentionally starts a different experiment.

Concrete commands:

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
   OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=current_state_integrated_a \
  PHASES_CONFIG=testing/phases.json \
   CLIENTS=8 CONTENT_ITEMS=600 USERS=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
   OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=current_state_integrated_b \
  PHASES_CONFIG=testing/phases.json \
   CLIENTS=8 CONTENT_ITEMS=600 USERS=100 \
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
   Both runs must reach `current_phase.txt=idle`, complete all six phases from [phases.json](../../../../../../source/scripts/testing/phases.json), and emit the standard artifact contract from [testing_overview.md](../../../testing_overview.md).
2. Required Tier 2 storage exercise.
   Both runs must show `storage_count > 1` in `resource_stats.csv` and at least one dynamic storage add event in `container_events.csv` or `elasticity_events.csv` during `storage_storm` or `tier1_hotspot`.
3. Required Tier 1 exercise.
   Both runs must show a real selective-sync path during the canonical hotspot window: `SelectiveSyncAlert` in controller logs, at least one `sel_sync_*` add event in `container_events.csv`, and `coord_state_owner_lan=ACTIVE` or `tier1_lifecycle_active_count=1` aligned to `tier1_hotspot`.
4. Required compute exercise.
   Both runs must show `server_count > 1` in `resource_stats.csv` and at least one dynamic compute add event in `container_events.csv` or `elasticity_events.csv` during `compute_spike`.
5. Control-plane and runtime health.
   Neither controller log may contain an unhandled Python traceback, repeated fatal exception loop, or evidence that a controller stopped making forward progress during an active phase. No core `edge_server*`, `osken*`, or `local_state_*` container may enter a crash loop.
6. Cleanup correctness.
   By final idle of each run, no unexpected dynamic compute, storage, or selective-sync container should still be running. The run must show drain or cleanup markers for every mechanism that activated.
7. Service-quality envelope (v5.6 — conntrack routing).
   Each run must keep overall non-200 responses at or below `5.0%`. Low-load phases `baseline`, `inter_hotspot_cooldown`, and `cooldown` must each stay at or below `1.0%` failures. Pressure phases `storage_storm`, `tier1_hotspot`, and `compute_spike` must each stay at or below `10.0%` failures.
8. Inter-run repeatability.
   The pair must stay in the same qualitative regime across both runs: all three mechanisms trigger, total request volume differs by no more than `10%`, per-phase p95 latency differs by no more than `35%` in the storage-locality phases and no more than `30%` in the compute phases, and cleanup converges to the same final baseline shape.

## Checkpoints

| Trigger | Question | Evidence | Runner action |
| --- | --- | --- | --- |
| End of `storage_storm` | Has Tier 2 begun to scale out, or is `storage_count` still pinned at `1`? | `resource_stats.csv`, `container_events.csv`, controller logs | Report only |
| Mid `tier1_hotspot` | Did the canonical hotspot emit `SelectiveSyncAlert` and reach `ACTIVE`? | `resource_stats.csv`, `container_events.csv`, controller logs | Report only |
| Mid `compute_spike` | Has compute elasticity actually added a dynamic edge server under the feed-ranking-heavy tail? | `resource_stats.csv`, `container_events.csv`, controller logs, `per_node_stats.csv` | Report only |
| End of `cooldown` | Did every activated mechanism drain back to baseline before idle? | `container_events.csv`, `resource_stats.csv`, `service_logs/`, controller logs | Report only |

## Validity Threats & Limitations

- This integrated baseline is stronger than the old standard long-cycle repeatability check. It is a readiness gate for exercising mechanisms together, not a like-for-like continuation of the previous low-pressure baseline.
- The seeded device and node counts define one run-wide workload snapshot, but the mechanisms are exercised by the phase-local range of rate, mix, cross-region ratio, and hotspot direction within the profile. That is the current supported way to vary workload shape inside one run.
- The controller's Tier 1 promotion gate is collection-level, not dependent on a per-document minimum-hit threshold. A larger seeded working set therefore does not by itself block Tier 1 promotion, while the manifest remains bounded by `SS_HOT_DOC_LIMIT`.
- No `--fault-plan` is used here, so this experiment does not validate failed-backend avoidance, explicit hard-failure recovery, or other synthetic-fault paths.
- If one mechanism fails to trigger while the others behave as expected, use the shorter verification override [phases_rq1_verify.json](../../../../../../source/scripts/testing/phases_override/phases_rq1_verify.json) and the focused Tier 1 smoke profile [phases_tier1_smoke.json](../../../../../../source/scripts/testing/phases_override/phases_tier1_smoke.json) as diagnostic follow-up, not as the baseline gate itself.
- Host-level noise, WAN-profile drift, or accidental env edits between runs can create false differences. That is why the plan fixes the launch path and forbids code, env, or image changes between the two replicates.

## Artifact Contract

Each run folder under `source/scripts/testing/metrics/<timestamp>_<run_label>/` must contain the standard run artifacts described in [testing_overview.md](../../../testing_overview.md): `client_requests.csv`, `resource_stats.csv`, `resource_stats_debug.csv`, `policy_state.csv`, `per_node_stats.csv`, `container_events.csv`, `elasticity_events.csv`, `controller_lan1.log`, `controller_lan2.log`, `controller_env_snapshot.env`, `phases_snapshot.json`, and `service_logs/`.

Expected later analysis outputs:

- Root run summaries such as `run_summary.md`, `latency_summary.csv`, `resource_summary.csv`, `elasticity_events.csv`, and `node_lifecycle_timings.csv`.
- A direct comparison output for `current_state_integrated_a` and `current_state_integrated_b`, preferably using the existing analysis CLIs documented in [analysis_toolchain.md](../../../analysis_toolchain.md).
- A focused integrated-mechanisms note that records first storage add, first Tier 1 `ACTIVE` window per direction, first compute add, the cleanup sequence, and any residual debt or phase-local failure spikes.
No additional experiment-specific outputs are required beyond the artifacts and summaries listed above.

## Changelog

| Date | Change | Rationale |
| --- | --- | --- |
| 2026-06-05 | Edge server circuit breaker removed (Approach B) | Breaker caused 46.9% false failure rate during normal storage churn. Removed `_CircuitBreaker`, `CircuitOpenError`, replaced with 500ms lightweight failure gate on `_MongoEpoch.last_failure_at`. See [results.md](./results.md) §2–§4 for full investigation and decision record. |
| 2026-06-05 | CLIENTS=3 → CLIENTS=8; added `client_fraction` to phase file and traffic generator | Individual client stalls at 3 clients dominated aggregate failure stats. 8 clients with per-phase subset selection provides more realistic workload model while keeping total load comparable. |
| 2026-06-05 | `getMore` cursor failure investigation | Service log analysis revealed 3,257 `getMore` failures (53% of all errors) — pymongo cannot retry cursor continuation. Root cause: VIP routing changes sever in-flight TCP connections between cursor batches. Fix: `batch_size=200` on dashboard `find()` reduces `getMore` calls from ~6 to ≤2. See [results.md](./results.md) §6–§7. |
| 2026-06-05 | Option B: increased rebind limit for replay-safe reads | `max_rebinds=2` (was 1) for `replay_safe=True` operations. Defense-in-depth alongside `batch_size` fix. |
| 2026-06-06 | Phase file consolidated to canonical `phases.json` | Removed redundant `phases_experiment_integrated_baseline.json`. The run auto-snapshots the phases config into the run folder as `phases_snapshot.json`. All experiments use the single source of truth. |
| 2026-06-06 | Compute elasticity thresholds lowered | `MAX_DYNAMIC_COMPUTE` 2→6 (room for both LANs). `SCALEUP_COMPUTE_BASE_THRESHOLD` 0.45→0.20 (was never tuned unlike storage's 0.12). `SCALEUP_CPU_FLOOR` 5→3, `SCALEUP_T_PROC_FLOOR` 20→15 (lower baseline). `SCALEDOWN_COMPUTE_COOLDOWN_S` 40→120 (nodes not removed immediately after spawning). `SCALE_DOWN_COMPUTE_REQUIRED` 7→9 (stricter: 9 of 12 windows must be healthy before removal). See [results.md](./results.md) §10 for full analysis. |
| 2026-06-06 | 500ms gate removed from edge server | The lightweight failure gate on `_MongoEpoch.last_failure_at` was removed. Evidence from two completed runs showed it caused 3–15% false failures in baseline phases by blocking all requests for 500ms after any `AutoReconnect` during normal storage replica-set churn. `serverSelectionTimeoutMS=3000` + `retryReads=True` already handle transient reconnects. See [results.md](./results.md) §11. |
| 2026-06-06 | v4 pair executed (`current_state_integrated_a`=`20260606_130104`, `b`=`20260606_135350`) with all fixes applied (500ms gate removed, Tier 1 spawn hardening, compute thresholds tuned, canonical `phases.json`). Image `74f5e1165238`. | Both runs complete but Tier 1 never reaches ACTIVE. Baseline/storage phases pristine (0.0%). See [results.md](./results.md) §15. |
| 2026-06-06 | Dashboard rework: bounded candidate fetch (`DASHBOARD_CANDIDATE_LIMIT=500`) + fleet integrity verification (`verify_fleet_integrity()`, `DASHBOARD_INTEGRITY_WORK_FACTOR=200`). Tier 1 lifecycle columns added to main `resource_stats.csv`. | Fixes compute-phase 55–71% failure caused by unbounded DB fetch (3.5s latency per dashboard query) and negligible CPU work (0.5% container CPU). Enables compute scaling to trigger. |
| 2026-06-08 | v5.6 — Conntrack VIP_DATA routing deployed. `ct_state` reply-rule bug fixed in `flows.py` `install_vip_data_reply_rule()`. Reply rules now use `ct(zone=N,nat)` action + `ipv4_src=backend_subnet` match instead of broken `ct_state=+est+trk` match. | Conntrack eliminates stale-rule → AutoReconnect → epoch-rotation cascade. v1 conntrack run: compute 1.4% (vs 56-65%), storage-churn 0.04%, zero epoch rotations. See [conntrack_routing results](../conntrack_routing/results.md) and [design doc §3k](../../../vip_routing/implementation/plans/conntrack_vip_routing/conntrack_vip_routing_design.md). |

## Historical Context

The changelog above is preserved as historical context for the original v5.6 campaign.

