# Experiment Plan — Golden Configuration Stability Gate

**Status**: ⚠️ Executed — gate not yet passed. See [results.md](results.md).
**Date**: 2026-06-09.
**Supersedes**: [current_state_long_cycle](../current_state_long_cycle/experiment_plan.md) v5.6 as the definitive integrated baseline.

## Intent

This is the final stability gate before new features or mechanisms are added. It evaluates the current system with **all fixes applied simultaneously** — conntrack VIP_DATA routing, cross-LAN veth TX queue fix, and recovery VIP removal — under the canonical integrated workload. It answers one question: **is the system, at the configuration values listed below, stable enough that all four elasticity mechanisms exercise together, repeatedly, and cleanly?** It also marks the exact configuration values that achieve this, so future campaigns have a pinned reference point.

The plan is grounded in evidence from nine prior stability experiments:

| Prior experiment | What it contributed to this gate |
|---|---|
| [conntrack_routing](../conntrack_routing/experiment_plan.md) | Stale-rule elimination. Compute 56–65% → 1.4%. Zero epoch rotations. Deployed in controller. |
| [wan_http0_root_cause](../wan_http0_root_cause/experiment_plan.md) | Cross-LAN veth TX queue fix (`txqueuelen=10000`). R2: 0.05% overall at CLIENTS=8, all mechanisms exercised. Deployed in `build_network_*.sh`. |
| [recovery_removal_validation](../recovery_removal_validation/experiment_plan.md) | Recovery VIP removal correct. All 8 criteria passed. Deployed in edge server image. |
| [storage_reserve_validation](../storage_reserve_validation/experiment_plan.md) | Reserve liveness confirmed (heartbeat stable, no cleanup loops). |
| [storage_reserve_use_validation](../storage_reserve_use_validation/experiment_plan.md) | Reserve carries VIP_DATA traffic (`reserve-used` gate passed at t08). |
| [storage_reserve_threshold_sweep](../storage_reserve_threshold_sweep/experiment_plan.md) | Activation boundary $0.12 < \tau \leq 0.15$. t12 = highest threshold that still activates. |
| [storage_reserve_load_sweep](../storage_reserve_load_sweep/experiment_plan.md) | c08 stable at t12 (no collapse); load boundary identified above 8 clients. |
| [tier1_activation](../tier1_activation/experiment_plan.md) | Tier 1 activates and drains cleanly both directions. DB-latency 84.5ms → 3.58ms. |
| [current_state_long_cycle](../current_state_long_cycle/experiment_plan.md) | Integrated baseline iterated v1→v5.6. v5.6 Run A: 2.2% (without WAN fix). |

## Hypothesis / Expected Outcome

If all fixes hold and the marked configuration is correct, a pair of identical runs should:

1. **Complete all 10 phases** of the canonical `phases.json` and drain to idle.
2. **Exercise all four mechanisms** in both runs: Tier 2 storage reserve scale-out, Tier 1 selective-sync activation in both hotspot directions, compute elasticity under dashboard-heavy phases, and conntrack VIP_DATA routing with visible entries.
3. **Stay within the service-quality envelope**: overall failure ≤3%, non-hotspot phases ≤1%, hotspot/compute phases ≤5%, no LAN-flip (LAN asymmetry ≤3×).
4. **Repeat cleanly**: per-phase p95 latency within 35% between replicates, same qualitative mechanism regime, same final baseline shape.
5. **Show zero epoch rotations** in edge-server logs during storage-churn phases, confirming conntrack eliminates the stale-rule cascade.

The WAN R2 diagnostic run already achieved 0.05% overall with all mechanisms exercised under the same workload and configuration. This pair confirms that result is repeatable and marks it as the definitive stability reference.

## RQ Linkage

This gate is a platform-stability prerequisite for all three thesis RQs in [system_to_thesis_map_rq_advanced.md](../../../../../../tese/miscelineous/system_to_thesis_map_rq_advanced.md):

- **RQ1** (push vs. polling telemetry): requires a stable control plane where telemetry acquisition is the only variable.
- **RQ2** (metadata-aware backend selection): requires a correct routing substrate where stale-rule failures don't confound selection quality.
- **RQ3** (locality/readiness strategy): requires elasticity mechanisms that exercise and drain cleanly before locality policies are compared.

If this gate fails, no RQ experiment can produce trustworthy results.

## Independent Variable & Held-Constant Set

- **Independent variable**: run replicate only (`golden_config_a` vs `golden_config_b`).
- **Held constant**: everything below — this is the golden configuration being marked.

### Marked Configuration Values

These are the values this experiment confirms as the stable operating point. They are encoded in the controller override file [`current_state_integrated.env`](../../../../../../source/scripts/testing/controller_env_overrides/current_state_integrated.env) and the network build scripts. All values below are held constant across both runs.

**Workload sizing**:
- `CLIENTS=8`, `DEVICES=600`, `NODES=100`
- Phase file: `testing/phases.json` (canonical 10-phase integrated workload, unchanged)

**Mechanism toggles**:
- `STORAGE_PERSISTENT_RESERVE_ENABLED=1` — Tier 2 storage reserve enabled
- `SS_ENABLED=1` — Tier 1 selective-sync enabled
- `MAX_DYNAMIC_STORAGE=5` — up to 5 dynamic storage nodes per LAN
- `MAX_DYNAMIC_COMPUTE=6` — up to 6 dynamic compute nodes across LANs

**Storage trigger bundle** (from threshold sweep — t12 is the highest that still activates):
- `SCALEUP_STORAGE_BASE_THRESHOLD=0.12`
- `SCALEUP_W_STORAGE_CPU=0.60`, `SCALEUP_W_T_DB=0.40`
- `SCALEUP_STORAGE_CPU_FLOOR=1.5`, `SCALEUP_STORAGE_CPU_SPAN=5`
- `SCALEUP_T_DB_FLOOR=60`, `SCALEUP_T_DB_SPAN=250`
- `SCALEUP_STORAGE_REQUIRED=2`, `SCALEUP_STORAGE_WINDOW_SIZE=5`
- `SCALEUP_STORAGE_COOLDOWN_S=120`

**Compute trigger bundle** (from v5.4 campaign tuning):
- `SCALEUP_COMPUTE_BASE_THRESHOLD=0.20`
- `SCALEUP_CPU_FLOOR=3`, `SCALEUP_T_PROC_FLOOR=15`
- `SCALEDOWN_COMPUTE_COOLDOWN_S=120`, `SCALE_DOWN_COMPUTE_REQUIRED=9`

**Infrastructure fixes** (already deployed, must NOT change between runs):
- Conntrack VIP_DATA routing: `source/sdn_controller/_vip_routing/flows.py` (reply rules use `ct(zone=N,nat)` + `ipv4_src=backend_subnet` match)
- Cross-LAN veth TX queue: `txqueuelen 10000` on veth3/eth1 + veth23/eth2 in `build_network_1.sh` and `build_network_2.sh`
- Recovery VIP removal: edge server image has no `_CircuitBreaker`, no recovery VIP code paths
- No `--fault-plan`, same WAN profile, same host/VM, same launch path

**Abort rule**: if any runtime-bearing file, controller env value, or image changes after `golden_config_a`, discard the pair and restart from `golden_config_a`.

## Run Matrix

| Run label | What changes | Phase file |
|---|---|---|
| `golden_config_a` | First golden-config replicate | `testing/phases.json` |
| `golden_config_b` | Second golden-config replicate | `testing/phases.json` |

Run order is fixed: `golden_config_b` only starts after `golden_config_a` artifacts are saved and the operator confirms no code, env, or image changes occurred.

## Run Configuration

```bash
# Run A
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=golden_config_a \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# Run B
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=golden_config_b \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

- `--phases-config`: `testing/phases.json` — canonical 10-phase integrated workload (2,220 s total).
- `--clients-per-lan`: `8`, `--seed-devices`: `600`, `--seed-nodes`: `100`.
- `--fault-plan`: **omitted** — no synthetic failure injection.
- Controller override: `current_state_integrated.env` unchanged for both runs.
- Images: no rebuild required. The txqueuelen fix is applied by `setup_network`; conntrack and recovery-removal changes are already in the deployed images/volume-mounted controller code.

## Focus & Evidence

**Primary focus**: `client_requests.csv` + controller logs (`controller_lan1.log`, `controller_lan2.log`).

- `client_requests.csv` is the service-quality authority — per-phase, per-LAN, per-endpoint failure rates and p95/p99 latency via `phase_stats.py`.
- Controller logs answer whether each mechanism fired in the intended phases: `[reserve] activated`, `SelectiveSyncAlert` → `ACTIVE`, `ComputeAlert`, scale-down/cleanup markers, and "forward rule deleted" on storage unregister.

**Secondary focus**: `resource_stats.csv`, `container_events.csv`, `elasticity_events.csv`, `service_logs/`.

| Artifact | Shows |
|---|---|
| `client_requests.csv` | Per-phase, per-LAN, per-endpoint HTTP status and latency. **THE** pass/fail signal. |
| `controller_lan1.log`, `controller_lan2.log` | Mechanism lifecycle markers: reserve ready/activated, Tier 1 alert→ACTIVE→drain, compute scale-up/down, conntrack rule install/delete, any Python tracebacks. |
| `resource_stats.csv` | `storage_count`, `server_count`, `tier1_lifecycle_active_count`, `conntrack_entries_n1`/`n2`, per-phase DB-latency signals. |
| `container_events.csv` | Add/remove ground truth for dynamic compute, storage, and `sel_sync_*` containers. Final cleanup debt. |
| `elasticity_events.csv` | Scale-up/down timing reference for cross-referencing with controller logs. |
| `service_logs/edge_server_*.log` | Epoch rotation count (`current_recovery_epoch_failed`), `AutoReconnect` frequency, `Created MongoClient` mode (must be `normal` — no recovery mode). |
| `phases_snapshot.json` | Confirms the exact 10-phase profile that ran. |
| `per_node_stats.csv` | Which containers carried CPU/DB pressure during each phase. |

**Tertiary**: `policy_state.csv` — only needed if controller logs and CSVs disagree about why a mechanism did or did not trigger.

## Metrics & Success Criteria

The golden configuration is confirmed stable only if **both runs satisfy all criteria below**.

### 1. Run completion & artifact integrity
Both runs must reach `current_phase.txt=idle`, complete all 10 phases, and emit the standard artifact contract.

### 2. All four mechanisms exercise

| Mechanism | Required evidence (per run) | Primary artifact |
|---|---|---|
| Tier 2 storage reserve | `storage_count > 1`, ≥1 `[reserve] activated`, ≥1 dynamic storage add event | `resource_stats.csv`, controller logs, `container_events.csv` |
| Tier 1 selective-sync | `SelectiveSyncAlert` → `ACTIVE` in BOTH hotspot directions, `sel_sync_*` add/remove events, drain to idle | Controller logs, `container_events.csv`, `resource_stats.csv` |
| Compute elasticity | `server_count > 1`, ≥1 `ComputeAlert` per LAN, ≥1 dynamic compute add event | `resource_stats.csv`, controller logs, `container_events.csv` |
| Conntrack VIP_DATA | `conntrack_entries_n1 > 0`, `conntrack_entries_n2 > 0`, ≥1 "forward rule deleted" on storage unregister | `resource_stats.csv`, controller logs |

### 3. Service-quality envelope

| Scope | Criterion | Rationale |
|---|---|---|
| Overall | ≤3.0% failure | Conntrack target. WAN R2: 0.05%. |
| Non-hotspot phases (`baseline`, `local_moderate`, `inter_hotspot_cooldown`, `demand_drop`) | ≤1.0% failure each | These phases have no elasticity churn. |
| Hotspot phases (`storage_stress`, `cross_region_hotspot`, `reverse_hotspot`) | ≤5.0% failure each | Storage churn may cause transient failures; conntrack keeps them bounded. |
| Compute phases (`compute_ramp`, `compute_spike`, `sustained_plateau`) | ≤5.0% failure each | Dashboard-heavy; DB query latency may still cause isolated timeouts. |
| LAN symmetry | LAN1/LAN2 failure rate ratio ≤ 3× overall | The LAN-flip pattern (one LAN dead, other perfect) must be absent. WAN R2: 1.0×. |

### 4. Control-plane & runtime health
- No unhandled Python traceback in either controller log.
- No core container (`edge_server*`, `osken*`, `local_state_*`) enters a crash loop.
- Zero `mode=recovery` epoch creations in edge-server service logs (recovery VIPs removed).
- Zero epoch rotations (`current_recovery_epoch_failed`) during storage-churn phases.

### 5. Cleanup correctness
By final idle, no unexpected dynamic compute, storage, or `sel_sync_*` containers remain. Every mechanism that activated must show drain or cleanup markers.

### 6. Inter-run repeatability
- All four mechanisms exercise in both runs (same qualitative regime).
- Total request volume differs by ≤10% between runs.
- Per-phase p95 latency differs by ≤35% in hotspot/compute phases between runs.
- Both runs converge to the same final baseline shape.

### 7. Escalation rule
If either run fails criteria 1–5, do **not** proceed to new feature development. Investigate the failure against the specific mechanism that misbehaved. If both runs pass but criterion 6 (repeatability) fails, run a third replicate (`golden_config_c`) before deciding.

## Checkpoints

| Trigger | Question | Evidence | Runner action |
|---|---|---|---|
| End of `storage_stress` (~540s) | Has Tier 2 storage begun to scale out? Is `storage_count > 1`? | `resource_stats.csv`, controller logs | Report only |
| Mid `cross_region_hotspot` (~720s) | Did the first directional hotspot emit `SelectiveSyncAlert` and reach `ACTIVE`? | Controller logs, `resource_stats.csv` | Report only |
| Mid `reverse_hotspot` (~1170s) | Did the reverse direction also reach `ACTIVE`? | Controller logs, `resource_stats.csv` | Report only |
| Mid `compute_spike` (~1500s) | Has compute elasticity added dynamic edge servers? | `resource_stats.csv`, controller logs | Report only |
| End of `demand_drop` (~2220s) | Did every activated mechanism drain back to baseline? | `container_events.csv`, `resource_stats.csv`, controller logs | Report only |
| Run end | Are `conntrack_entries_n1` and `conntrack_entries_n2` >0 in the final telemetry window? | `resource_stats.csv` | Report only |

## Validity Threats & Limitations

- **Single host/VM**: both runs share the same physical environment. Host-level noise, Docker daemon contention, or WAN-profile drift between runs can create false differences. The abort rule mitigates code/env drift but not infrastructure noise.
- **Two-run pair, not statistical**: two replicates is the minimum for repeatability. If results are borderline (e.g., one run at 2.8%, the other at 4.1%), a third replicate is warranted before declaring pass or fail.
- **WAN non-determinism**: v5.4 showed a 4× spread (2.0% vs 8.1%) with identical code due to WAN conditions alone. The txqueuelen fix eliminates the dominant bottleneck, but WAN variance in `reverse_hotspot` may still produce LAN-specific elevation that is not a code defect.
- **Storage reserve may not activate at t12 under the integrated workload**: the threshold sweep used a dedicated storage-reserve probe workload. Under `phases.json`, the storage stress profile differs — more dashboard mix, less pure device_status. If t12 stays waiting-only here while the WAN R2 run activated at the same threshold, the workload shape (not the threshold) is the variable. This is acceptable — the gate confirms the integrated config works; individual mechanism tuning is already done.
- **Tier 1 at DEVICES=600**: the Tier 1 activation experiment used DEVICES=30 to concentrate the hot set. At DEVICES=600 with random device selection, the hot set may be more diffuse. The promotion gate is collection-level (not per-document), so a larger seeded set does not block activation as long as cross-region read volume meets `SS_MIN_READS_PER_WINDOW=14`. If Tier 1 fails to activate here, that is a workload-concentration finding, not a stability failure — the mechanism itself is already validated.
- **No `--fault-plan`**: synthetic failure paths (hard-failure recovery, failed-backend avoidance) are out of scope. This gate validates normal-operation stability only.

## Artifact Contract

Standard run-folder layout per [`testing_overview.md`](../../../testing_overview.md):

```
source/scripts/testing/metrics/<timestamp>_golden_config_a/
  client_requests.csv
  resource_stats.csv
  resource_stats_debug.csv
  policy_state.csv
  per_node_stats.csv
  container_events.csv
  elasticity_events.csv
  node_lifecycle_timings.csv
  phases_snapshot.json
  current_phase.txt
  controller_lan1.log
  controller_lan2.log
  controller_env_snapshot.env
  service_logs/
    edge_server_n1.log  (or edge_server_*/)
    edge_server_n2.log
    edge_storage_lan1_dyn*/
    edge_storage_lan2_dyn*/
```

Same layout for `golden_config_b`. No experiment-specific additional files expected.

Expected later analysis outputs:
- Standard run summaries from the existing analysis toolchain (`phase_stats.py`, `full_analysis.py`).
- A direct A/B comparison using `simple_compare_overall.png` and `simple_compare_phase.png`.
- A golden-configuration note that records, for each run: first storage trigger time, first Tier 1 ACTIVE time per direction, first ComputeAlert time, conntrack entry peak, cleanup completion, overall failure rate, and per-phase breakdown. This note becomes the pinned reference for all future campaigns.

## Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-06-09 | Initial pair executed (`golden_config_a` + `golden_config_b`). `create_indexes.py` missing `DESCENDING` import fixed before launch. `state.py:158` `.items()` on list bug found and fixed between runs. Gate not yet passed — LAN2 TCP connectivity collapse, cleanup debt, and absent reserve activation remain open. | [results.md](results.md) §1–§2 — full analysis and root cause investigation. |
<!-- end -->
