# Experiment Plan — Mechanism Necessity Ablation

**Status**: 📋 Planned — 2026-06-27
**Depends on**: [golden_config_stability](../golden_config_stability/experiment_plan.md), [variance_reduction](../variance_reduction/experiment_plan.md), [tier1_activation](../tier1_activation/experiment_plan.md)

## Intent

This experiment answers one compound question: **does each elasticity mechanism — compute scale-up, storage reserve activation, and Tier 1 selective-sync — produce a measurable, causally-attributable improvement under its respective load regime when all other mechanisms and thresholds are held fixed?**

Prior stability experiments proved that each mechanism *activates correctly*. None proved that the system performs *worse* when a mechanism is disabled. This experiment fills that gap via a 4-run ablation: one all-enabled baseline and three runs each disabling exactly one mechanism. The same phases file and threshold bundle are used for all runs. The independent variable is which mechanism is absent.

## Hypothesis / Expected Outcome

If each mechanism is causally necessary for performance under its target load regime:

1. **Compute**: `compute_spike` (dashboard-heavy, 7 r/s/client) with `MAX_DYNAMIC_COMPUTE=0` should produce elevated failure rate, elevated p95 latency, and **higher per-server CPU and RAM** (load concentrated on fixed nodes) relative to the all-enabled run where dashboard processing distributes across 2–6 edge servers.
2. **Storage**: `storage_hotspot` (device_status-heavy, 10 r/s/client, 90 % cross-region) with both `STORAGE_PERSISTENT_RESERVE_ENABLED=0` and `MAX_DYNAMIC_STORAGE=0` should produce higher p95 latency and **higher per-storage-node CPU and RAM** (all cross-region reads hit a single fixed MongoDB — no dynamic storage nodes can be added via any path) relative to the all-enabled run, where the activated reserve distributes read load across 2+ storage nodes.
3. **Tier 1**: `tier1_hotspot_n1` and `tier1_hotspot_n2` (95 % cross-region read hotspot in each direction) with `SS_ENABLED=0` should preserve the high cross-region DB-latency profile (~80–100 ms `time_db`), while the all-enabled run should drop to ~3–5 ms after Tier 1 reaches `ACTIVE`.

**Load distribution is the unifying principle**: adding compute or storage nodes should reduce per-node CPU and RAM because the same total load is served by more instances. This is as important as latency and failure rate — it proves the mechanisms achieve their architectural purpose of horizontal scale-out.

## RQ Linkage

- **RQ1** (delivery cadence): requires a stable control plane — the ablation confirms that compute elasticity prevents cascading failures that would otherwise confound telemetry-mode comparisons.
- **RQ2** (metadata-aware backend selection): requires a correct routing substrate — the ablation confirms that storage reserve activation provides additional read capacity, which backend selection policies can exploit.
- **RQ3** (locality/readiness strategy): the Tier 1 ablation directly demonstrates that local caching eliminates the cross-region DB penalty, which is the core premise of locality-aware strategies.

## Independent Variable & Held-Constant Set

- **Independent variable**: which single mechanism is disabled (compute, storage, or Tier 1). The all-enabled run is the reference.
- **Held constant**: workload shape (same `phases.json`), sizing (`CLIENTS=8`, `DEVICES=600`, `NODES=100`), all threshold/cooldown values, WAN profile, host, code, images, launch path. No `--fault-plan`.

### Mechanism Toggles Per Run

| Run | `MAX_DYNAMIC_COMPUTE` | `STORAGE_PERSISTENT_RESERVE_ENABLED` | `SS_ENABLED` | `MAX_DYNAMIC_STORAGE` |
|-----|----------------------|-------------------------------------|-------------|----------------------|
| A (all) | 6 | 1 | 1 | 5 |
| B (no compute) | **0** | 1 | 1 | 5 |
| C (no storage) | 6 | **0** | 1 | **0** |
| D (no tier1) | 6 | 1 | **0** | 5 |

**Storage ablation note**: `MAX_DYNAMIC_STORAGE=0` blocks ALL dynamic storage paths — both the reserve pre-preparation path (`STORAGE_PERSISTENT_RESERVE_ENABLED=0` disables the fast-activation standby) and the direct `DataAlert` spawn path (`scaling_policy.py:248` returns `None` when `dynamic_storage_count >= _MAX_DYNAMIC_STORAGE`, i.e., `0 >= 0`). Setting only `STORAGE_PERSISTENT_RESERVE_ENABLED=0` would still allow storage nodes via the normal `DataAlert` → `self._elasticity.submit(alert)` fallthrough at `main_n1.py:503`. Both must be zero for a clean ablation.

### Fixed Threshold Bundle (all 4 runs)

| Parameter | Value | Origin |
|---|---|---|
| `SCALEUP_STORAGE_BASE_THRESHOLD` | **0.10** | t10 — highest threshold that activates at CLIENTS=8 (load_sweep: t12 does not) |
| `SCALEUP_COMPUTE_BASE_THRESHOLD` | 0.20 | Golden config |
| `SCALEDOWN_COMPUTE_COOLDOWN_S` | 180 | Golden config (variance_reduction fix) |
| `SCALEUP_STORAGE_COOLDOWN_S` | 120 | Golden config |
| `SCALEDOWN_STORAGE_COOLDOWN_S` | **300** | Extended — prevents reserve cycling during 240s `storage_hotspot` (300 > 240, scale-down never fires mid-phase). Golden config default is 120s. |
| `SCALEUP_CPU_FLOOR` | 3 | Golden config |
| `SCALEUP_T_PROC_FLOOR` | 15 | Golden config |
| `SCALE_DOWN_COMPUTE_REQUIRED` | 9 | Golden config |
| `SCALEUP_W_STORAGE_CPU` | 0.60 | Golden config |
| `SCALEUP_W_T_DB` | 0.40 | Golden config |
| `SCALEUP_STORAGE_CPU_FLOOR` | 1.5 | Golden config |
| `SCALEUP_STORAGE_CPU_SPAN` | 5 | Golden config |
| `SCALEUP_T_DB_FLOOR` | 60 | Golden config |
| `SCALEUP_T_DB_SPAN` | 250 | Golden config |
| `SCALEUP_STORAGE_REQUIRED` | 2 | Golden config |
| `SCALEUP_STORAGE_WINDOW_SIZE` | 5 | Golden config |

Tier 1 thresholds use controller defaults (`SS_MIN_READS_PER_WINDOW=14`, `SS_PROMOTION_CROSS_REGION_THRESHOLD=0.4`, `SS_BREACH_WINDOWS_M=2`, `SS_BREACH_WINDOWS_N=5`, `SS_SCALEDOWN_THRESHOLD=5`, `SS_SCALEDOWN_WINDOW=8`).

**Base env parameters** (from `osken-controller.env`, held constant across all 4 runs): `SCALEUP_COMPUTE_COOLDOWN_S=45`, `SCALEUP_CPU_SPAN=5`, `SCALEUP_T_PROC_SPAN=50`, `SCALEUP_REQUIRED=3`, `SCALEUP_COMPUTE_THRESHOLD_INCREMENT=0.10`, `SCALE_DOWN_COMPUTE_WINDOW_SIZE=12`, `SCALE_DOWN_STORAGE_WINDOW_SIZE=15`, `SCALE_DOWN_STORAGE_REQUIRED=9`, and all other parameters not listed in the Fixed Threshold Bundle above. The env override mechanism (`run_experiment.sh:193-218`) merges overrides on top of the base — unmentioned keys are preserved unchanged.

**Why t10**: The canonical golden threshold `t12` does not activate the storage reserve at 8 clients under any workload tested (`storage_reserve_load_sweep` — c08 waiting-only, c10 overloads edge server). t10 is the next step down that activates at 8 clients (proven in `storage_reserve_threshold_sweep`). All 4 runs use t10 so the comparison is fair.

## Run Matrix

| Run | Label | Compute | Storage Reserve | Tier 1 | Phase file | Env override |
|-----|-------|---------|----------------|--------|-----------|--------------|
| A | `mechanism_all` | ✅ (6) | ✅ (1) | ✅ (1) | `testing/phases.json` | `mechanism_necessity_all.env` |
| B | `mechanism_nocompute` | ❌ (0) | ✅ (1) | ✅ (1) | `testing/phases.json` | `mechanism_necessity_nocompute.env` |
| C | `mechanism_nostorage` | ✅ (6) | ❌ (0) | ✅ (1) | `testing/phases.json` | `mechanism_necessity_nostorage.env` |
| D | `mechanism_notier1` | ✅ (6) | ✅ (1) | ❌ (0) | `testing/phases.json` | `mechanism_necessity_notier1.env` |

Run order: A → B → C → D (all-enabled reference first, then ablations in any order). If Run A does not exercise all three mechanisms, stop and diagnose before proceeding — see §1 diagnostic tree below.

**SKIP_SEED clarification**: `SKIP_SEED=1` tells `run_experiment.sh` not to re-seed data because `setup_test_data` in the same `make` invocation already seeded it. It is an operational efficiency flag, not a determinism control. Device/node selection and request ordering are non-deterministic across runs (no `RANDOM_SEED` set).

**Host reboot**: not mandated between runs. The compute ablation's expected effect (≥10pp failure gap) survives any host-state drift. For the storage ablation, if results are borderline, re-run C vs A with a host reboot between them to control accumulated kernel/Docker/network state (as `variance_reduction` demonstrated matters).

## Run Configuration

All runs use identical launch shape except `RUN_LABEL` and `OSKEN_ENV_OVERRIDE_FILE`:

```bash
# Run A — all mechanisms enabled
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_all.env \
  RUN_LABEL=mechanism_all \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# Run B — compute scale-up disabled
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_nocompute.env \
  RUN_LABEL=mechanism_nocompute \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# Run C — storage reserve disabled
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_nostorage.env \
  RUN_LABEL=mechanism_nostorage \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# Run D — Tier 1 disabled
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_notier1.env \
  RUN_LABEL=mechanism_notier1 \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

- `--phases-config`: `testing/phases.json` — simplified 8-phase mechanism-stress workload (see Phase Profile below).
- `--clients-per-lan`: `8`, `--seed-devices`: `600`, `--seed-nodes`: `100`.
- `--fault-plan`: **omitted** — no synthetic failure injection.
- Images: no rebuild required. All mechanism code is already deployed.

### Phase Profile

Simplified from the original 10-phase canonical workload. Phases target specific mechanism domains with increased duration and intensity:

| # | Phase | Dur | Rate | Cross | Clients | Mix (dev/dsh/svc) | Hotspot |
|---|-------|-----|------|-------|---------|---------------------|---------|
| 1 | `baseline` | 60s | 1 | 0% | 50% | 60/25/15 | — |
| 2 | `local_moderate` | 60s | 3 | 0% | 75% | 55/30/15 | — |
| 3 | `storage_hotspot` | 240s | 10 | 90% | 100% | 90/5/5 | lan2→lan1 |
| 4 | `tier1_hotspot_n1` | 180s | 8 | 95% | 100% | 95/3/2 | lan2→lan1 |
| 5 | `inter_hotspot_cooldown` | 60s | 2 | 0% | 50% | 60/25/15 | — |
| 6 | `tier1_hotspot_n2` | 180s | 8 | 95% | 100% | 95/3/2 | lan1→lan2 |
| 7 | `compute_spike` | 180s | 7 | 5% | 100% | 20/65/15 | — |
| 8 | `cooldown` | 120s | 1 | 0% | 50% | 60/25/15 | — |

**Total**: 1080 s (18 min).

**Note**: `phases.json` has already been edited to the 8-phase profile below. No further file changes are needed.

**Changes from the original 10-phase `phases.json`** (historical context):
- Removed: `cross_region_hotspot` (redundant with `tier1_hotspot_n1`), `compute_ramp` + `sustained_plateau` (replaced by single longer `compute_spike`), `reverse_hotspot` (replaced by `tier1_hotspot_n2`), `demand_drop` (shortened to `cooldown`).
- Shortened: `local_moderate` (90→60 s), `cooldown` (300→120 s).
- Lengthened: `storage_hotspot` (180→240 s), `compute_spike` (150→180 s) — more time for mechanisms to activate and show measurable effect.
- Increased rate: `storage_hotspot` (5→10 r/s) — matches the intensity that produced visible storage stress in `storage_reserve_load_sweep`.

## Focus & Evidence

**Primary focus**: `client_requests.csv` + `resource_stats.csv` + controller logs.

| Artifact | Shows |
|---|---|
| `client_requests.csv` | Per-phase, per-LAN failure rate and p95/p99 latency. **THE** pass/fail signal for compute ablation. |
| `resource_stats.csv` | `storage_count`, `server_count`, `tier1_lifecycle_active_count`, per-node CPU%, `time_db` p95 signals. Core evidence for storage and Tier 1 ablations. |
| `controller_lan1.log`, `controller_lan2.log` | Mechanism lifecycle: `[reserve] activated`, `SelectiveSyncAlert` → `ACTIVE`, `ComputeAlert`, scale-down/cleanup markers. |

**Secondary focus**: `per_node_stats.csv`, `container_events.csv`, `elasticity_events.csv`, `service_logs/`.

| Artifact | Shows |
|---|---|
| `per_node_stats.csv` | Per-container CPU%, memory, `time_db`, `request_count` — primary evidence for per-node load distribution (compute and storage ablations). |
| `container_events.csv` | Add/remove ground truth for dynamic compute, storage, and `sel_sync_*` containers. |
| `elasticity_events.csv` | Scale-up/down timing reference. |
| `service_logs/edge_server_*.log` | Epoch rotations, `AutoReconnect`, recovery mode — control-plane health across all runs. |
| `phases_snapshot.json` | Confirms the exact 8-phase profile that ran. |

### Evidence Map Per Mechanism

| Mechanism | Primary comparison | Key metric | Artifacts |
|-----------|-------------------|------------|-----------|
| **Compute** | Run B vs A/C/D in `compute_spike` | Failure rate, p95 latency, per-server CPU%, per-server RAM | `client_requests.csv`, `resource_stats.csv`, `per_node_stats.csv` |
| **Storage** | Run C vs A/B/D in `storage_hotspot` | p95 latency, per-storage CPU%, per-storage RAM | `client_requests.csv`, `resource_stats.csv`, `per_node_stats.csv` |
| **Tier 1** | Run D vs A/B/C in `tier1_hotspot_n1`/`n2` | Consumer-LAN `time_db` p95 | `resource_stats.csv` |

## Metrics & Success Criteria

The experiment succeeds when each ablation run shows a **directional degradation** relative to the all-enabled run in its target phase, and the all-enabled run exercises all three mechanisms cleanly.

### 1. All-Enabled Run (A) — Mechanism Exercise Gate

| Mechanism | Required evidence |
|---|---|
| Compute scale-up | `server_count > 1` during `compute_spike`, ≥1 `ComputeAlert` per LAN |
| Storage reserve | `storage_count > 1`, ≥1 `[reserve] activated` during `storage_hotspot` |
| Tier 1 | `SelectiveSyncAlert` → `ACTIVE` in BOTH hotspot directions, `tier1_lifecycle_active_count=1` |

If Run A does not exercise all three mechanisms, diagnose before proceeding. If only storage fails to activate at t10, continue — the storage ablation (C vs A/B/D) can still compare latency and per-node load even without activation in Run A.

**Diagnostic decision tree — Run A mechanism gate failure:**

| Mechanism missing | Check | Likely cause | Fix |
|---|---|---|---|
| Compute: no `server_count > 1` in `compute_spike` | Controller logs for `[scale-up] compute`; `SCALEUP_COMPUTE_BASE_THRESHOLD` in env snapshot | Threshold too high for this workload | Lower `SCALEUP_COMPUTE_BASE_THRESHOLD` from 0.20 → 0.15 |
| Storage: no `[reserve] activated` | Controller logs for `[scale-up] storage triggered`; `degradation_score` in debug CSV | t10 still too high at 8 clients under new phases | Lower `SCALEUP_STORAGE_BASE_THRESHOLD` from 0.10 → 0.08; re-run A only |
| Tier 1: no `SelectiveSyncAlert` | Controller logs for `SelectiveSync`; `coord_hot_doc_total` in `resource_stats.csv` | Hot set not concentrated enough | Increase `DEVICES` or verify `cross_region_ratio` in `tier1_hotspot_n1`/`n2` is 0.95 |
| Any: missing `per_node_stats.csv` | Run folder artifacts | Collector crash (outdated binary) | Sync latest collector to host; re-run |

### 2. Compute Ablation (B vs A/C/D) — Failure Rate & Per-Node Load

| Metric | Target | Phase |
|---|---|---|
| Run B failure rate | ≥10 percentage points above max(A,C,D) | `compute_spike` |
| Run B p95 latency | ≥2× max(A,C,D) | `compute_spike` |
| Run A/C/D failure rate | ≤5% each | `compute_spike` |
| Run B avg edge-server CPU% | ≥1.5× max(A,C,D) avg edge-server CPU% | `compute_spike` |
| Run B avg edge-server RAM | ≥1.3× max(A,C,D) avg edge-server RAM | `compute_spike` |

Rationale: `variance_reduction` Run B (net-0 scale-up) hit 87.9 % in `compute_spike` vs Run C (net-+5) at 0.16 %. A clean `MAX_DYNAMIC_COMPUTE=0` should produce a similarly clear gap. **Per-node load distribution** is the direct mechanism: when compute scales up (Runs A/C/D), dashboard processing is distributed across 2–6 edge servers, so each server carries a fraction of the CPU and RAM load. Without scale-up (Run B), the fixed servers absorb the full load alone — per-node CPU and RAM must be visibly higher. This is measured from `per_node_stats.csv` per-container CPU% and memory columns, averaged across all edge servers active during `compute_spike`.

### 3. Storage Ablation (C vs A/B/D) — Latency & Per-Node Load

| Metric | Target | Phase |
|---|---|---|
| Run C avg storage CPU per node | ≥1.5× max(A,B,D) avg storage CPU per node | `storage_hotspot` |
| Run C avg storage RAM per node | ≥1.3× max(A,B,D) avg storage RAM per node | `storage_hotspot` |
| Run C p95 latency | ≥1.3× max(A,B,D) | `storage_hotspot` |
| Runs A/B/D `storage_count` | ≥2 for at least one telemetry window | `storage_hotspot` |

Rationale: a single MongoDB serving all cross-region reads concentrates CPU, RAM, and I/O on one node. When the reserve activates (Runs A/B/D), reads distribute across 2+ storage nodes — each node handles a fraction of the query volume, so per-node CPU and RAM must drop. This is the same load-distribution principle as compute scale-out. Per-node CPU% and memory are measured from `per_node_stats.csv` for all `edge_storage_*` containers active during `storage_hotspot`. With `MAX_DYNAMIC_STORAGE=0` (Run C), zero dynamic storage nodes can be added via any path (reserve or direct `DataAlert`), so the single fixed MongoDB handles the full cross-region read load alone. If the latency difference is small at DEVICES=600, the per-node CPU and RAM distribution metrics are the fallback — they directly prove that adding storage capacity spreads load.

### 4. Tier 1 Ablation (D vs A/B/C) — Cross-Region Latency

| Metric | Target | Phase |
|---|---|---|
| Run D consumer-LAN `time_db` p95 | ≥10× max(A,B,C) consumer-LAN `time_db` p95 | `tier1_hotspot_n1`, `tier1_hotspot_n2` |
| Runs A/B/C `tier1_lifecycle_active_count` | =1 during each hotspot direction | `tier1_hotspot_n1`, `tier1_hotspot_n2` |

Rationale: `tier1_activation` showed 84.5 ms → 3.58 ms (23.6×). The same workload shape produces the same expectation.

### 5. Control-Plane Health (all runs)

- No unhandled Python traceback in either controller log.
- No core container (`edge_server*`, `osken*`, `local_state_*`) enters a crash loop.
- Zero epoch rotations during storage-churn phases.
- All dynamic containers drained by final `cooldown`.

### 6. Escalation

- If Run B does not show elevated failures in `compute_spike`, increase `rate_per_client` in that phase.
- If Run C does not show a latency/CPU difference, escalate: (1) re-run C vs A with a host reboot between them to control state accumulation, (2) increase `DEVICES` to 3000 to make DB queries costlier, (3) verify `SCALEDOWN_STORAGE_COOLDOWN_S=300` is in the env snapshot.
- If Run D does not show the Tier 1 latency gap, verify that `tier1_hotspot_n1`/`n2` produce sufficient cross-region read volume.

## Checkpoints

| Trigger | Question | Evidence | Runner action |
|---|---|---|---|
| End of `baseline` | Is storage reserve `READY_RESERVED` on both LANs? | Controller logs, `elasticity_events.csv` | Report only |
| Mid `storage_hotspot` (~180s) | Has `[reserve] activated` fired on LAN1? | Controller logs | Report only |
| Mid `tier1_hotspot_n1` (~480s) | Has Tier 1 reached `ACTIVE` for first direction? | Controller logs, `resource_stats.csv` | Report only |
| Mid `tier1_hotspot_n2` (~720s) | Has Tier 1 reached `ACTIVE` for reverse direction? | Controller logs, `resource_stats.csv` | Report only |
| Mid `compute_spike` (~900s) | Has compute elasticity added dynamic edge servers? In Run B, are failures climbing? | `resource_stats.csv`, `client_requests.csv` | Report only |
| End of `cooldown` | Have all dynamic containers drained? | `container_events.csv`, controller logs | Report only |

## Validity Threats & Limitations

- **Storage ablation blocks both paths**: `MAX_DYNAMIC_STORAGE=0` blocks the direct `DataAlert` spawn path (`scaling_policy.py:248`), and `STORAGE_PERSISTENT_RESERVE_ENABLED=0` blocks the reserve fast-path (`main_n1.py:204,231`). Verified against controller source 2026-06-27. Without both set to 0, the normal `DataAlert` fallthrough at `main_n1.py:503` would still allow dynamic storage nodes, making the ablation ineffective.
- **Storage necessity is latency/load, not failure**: the Flask edge server (~100 req/s ceiling) saturates before MongoDB does at current scales. The storage ablation proves load distribution and latency improvement, not failure prevention. A production WSGI server would shift the bottleneck, but this experiment uses the current Flask deployment.
- **Storage activation at t10 is not guaranteed**: `storage_reserve_load_sweep` showed c08 at t12 was waiting-only. t10 at 8 clients activated under the old probe (threshold sweep) but has not been tested with the new 8-phase workload. Activation is expected but not certain.
- **Reserve cycling prevented by extended cooldown**: `SCALEDOWN_STORAGE_COOLDOWN_S=300` exceeds the 240s `storage_hotspot` duration, so scale-down cannot fire during the stress phase. The reserve, once activated, persists through the entire phase. This eliminates the cycling window that plagued earlier threshold/load sweeps where the 120s cooldown was shorter than the phase.
- **Single-replicate per run**: each ablation condition runs once. Inter-run variance (host state, WAN conditions) could confound small differences. The compute ablation's expected effect is large enough to survive single-replicate noise; storage and Tier 1 effects are smaller and may need replication.
- **No fixed seed**: device/node selection is non-deterministic. Request ordering varies. This adds noise but does not bias the directional hypothesis.
- **WAN variability**: the `tc netem` emulation may produce timing variance that affects cross-region latency. All runs share the same WAN profile, so this is held constant.
- **Storage→Tier 1 cross-contamination**: `storage_hotspot` (phase 3) runs before `tier1_hotspot_n1` (phase 4). If the storage reserve activates in phase 3 and the 300s cooldown keeps it alive, extra MongoDB nodes could still serve reads during Tier 1 phases — independently reducing consumer-LAN `time_db` even without Tier 1 active. This would **shrink** the Tier 1 ablation effect size. The expected Tier 1 effect (84→3ms, 23.6×) is large enough to survive this confound, but if Run D's `time_db` is anomalously low during Tier 1 phases, check whether `storage_count > 1` in `resource_stats.csv` for those phases.

## Artifact Contract

Each run folder under `source/scripts/testing/metrics/<timestamp>_mechanism_<label>/` must contain the standard artifacts: `client_requests.csv`, `resource_stats.csv`, `resource_stats_debug.csv`, `policy_state.csv`, `per_node_stats.csv`, `container_events.csv`, `elasticity_events.csv`, `controller_lan1.log`, `controller_lan2.log`, `controller_env_snapshot.env`, `phases_snapshot.json`, and `service_logs/`.

Expected later analysis outputs:

- **Per-run**: standard `cli_simple_run` summaries (`simple_run.png` — latency, failure rate, node counts over time).
- **Per-run**: `cli_cpu_drivers` load-balance diagnostics (`cpu_drivers.png` — old-vs-new node CPU per phase per role).
- **Per-run**: `cli_phase_summary` per-phase latency percentiles and node-type breakdowns (`phase_summary.png`).
- **Cross-run**: `cli_mechanism_compare` — the primary comparison output for this experiment. Produces `mechanism_compare.png` with 8 panels (4 rows × 2 columns):

| Row | Left | Right | Data source |
|-----|------|-------|-------------|
| 1 | Avg latency by phase | Failure rate by phase | `client_requests.csv` |
| 2 | Avg compute CPU% by phase | Avg storage CPU% by phase | `per_node_stats.csv` |
| 3 | Avg compute RAM (MB) by phase | Avg storage RAM (MB) by phase | `per_node_stats.csv` |
| 4 | Owner-LAN avg_time_db_ms | Consumer-LAN avg_time_db_ms | `resource_stats.csv` |

Owner/consumer LAN assignment follows `hotspot_direction` from `phases_snapshot.json`: `lan2_to_lan1` → owner=lan1, consumer=lan2. Non-hotspot phases average both LANs.

**Usage**:
```bash
python -m source.scripts.testing.analysis.cli_mechanism_compare \
  --run-dir <path/to/mechanism_all> \
  --run-dir <path/to/mechanism_nocompute> \
  --run-dir <path/to/mechanism_nostorage> \
  --run-dir <path/to/mechanism_notier1> \
  --output-dir <path/to/comparison_output>
```

- **Cross-run**: `cli_simple_compare` for overall latency/failure/node-count comparison (`simple_compare_overall.png`, `simple_compare_phase.png`).
- A mechanism-necessity verdict per factor: **met** (clear degradation when disabled), **marginal** (degradation present but small), or **missed** (no visible degradation).
