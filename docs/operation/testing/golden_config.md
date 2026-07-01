# Golden Configuration

The canonical sizing, mechanism toggles, and trigger thresholds for the
efficient-storage-in-edge-scenarios platform. Based on mechanism necessity
experiments (v5–v6, 2026-06-29/30) and stability experiments (2026-06-05/25).

All toggles and thresholds are encoded in
[`current_state_integrated.env`](../../../source/scripts/testing/controller_env_overrides/current_state_integrated.env).
Full results: [`experiment/stability/`](experiment/stability/).

---

## Workload Sizing

| Parameter | Value | Source |
|-----------|-------|--------|
| `WAN_RTT_MS` | **260** | v6 Tier 1 WAN curve — cross-region penalty visible; uncensored at `VIP_HARD_TIMEOUT=60` |
| `CLIENTS` | **48** | v6 — load volume for storage + Tier 1 stress |
| `DEVICES` | **6000** | v6 — dataset cardinality for realistic query cost |
| `NODES` | **100** | Held constant across all experiments |
| `STORAGE_CPUS` | **0.10** | v6 storage calibration — single node hits 46% without elasticity |
| `VIP_HARD_TIMEOUT` | **60s** | v6 — prevents timeout censorship at WAN ≥200ms (30s censors OFF-run data) |

### Phases File

The canonical workload is the 6-phase profile captured in
[`phases_snapshot.json`](../../../source/scripts/testing/metrics/20260629_235752_v6_t1_wan260_on_vip60/phases_snapshot.json)
(T9 run). For any experiment, review the phases to ensure they match the intent.

| Phase | Duration | Rate/Client | Cross-Region | Stresses |
|-------|----------|-------------|-------------|----------|
| `baseline` | 60s | 1 r/s | 0% | — |
| `storage_storm` | 240s | 4 r/s | 90% | Storage |
| `tier1_hotspot` | 180s | 5 r/s | 95% | Tier 1 |
| `inter_hotspot_cooldown` | 300s | 1 r/s | 0% | — |
| `compute_spike` | 180s | 4 r/s | 5% | Compute |
| `cooldown` | 120s | 1 r/s | 0% | — |

> To restore the original 10-phase RQ1 workload, copy `phases_snapshot.json` from any pre-v6 run folder.

## Mechanism Toggles

| Parameter                              | Value       | Purpose                                   |
| -------------------------------------- | ----------- | ----------------------------------------- |
| `STORAGE_PERSISTENT_RESERVE_ENABLED` | **1** | Tier 2 storage reserve enabled           |
| `SS_ENABLED`                         | **1** | Tier 1 selective-sync enabled            |
| `MAX_DYNAMIC_STORAGE`                | **5** | Up to 5 dynamic storage nodes per LAN     |
| `MAX_DYNAMIC_COMPUTE`                | **6** | Up to 6 dynamic compute nodes across LANs |

## Storage Trigger Bundle

The activation boundary is $0.12 < \tau \leq 0.15$.
**t12 (0.12)** is the highest threshold that still activates the reserve under
the probe workload used for calibration — avoids over-sensitivity while ensuring
the mechanism fires. Determined by
[`storage_reserve_threshold_sweep`](experiment/stability/storage_reserve_threshold_sweep/results.md):
t08 cycles, t12 stable, t20 never activates.

**✅ Fixed (2026-06-25):** A MAC-recycling collision previously blocked reserve
activation — when a Tier 1 node was removed and its MAC recycled for a new
reserve, a late cleanup completion for the old node removed the new reserve
from `_active`, causing `consume_ready_storage_reserve()` to return `None`.
Two-part fix applied and verified across the fix-verified pair:

- **Name-aware removal completions** — `sync()` now checks container name
  before removing from `_active`, preventing stale cleanups from clobbering
  nodes that reuse the same MAC.
- **Self-contained slot activation** — `consume_ready_storage_reserve()`
  constructs `NodeInfo` from slot data without depending on `_active` lookup.

**Fix verification**: 7 `[reserve] activated` events across the pair (vs 0
in all prior runs). The stale-removal guard triggered once — a late Tier 1
cleanup was correctly skipped because a compute node now occupied the MAC.
Zero "consume returned None" warnings. See
[`golden_config_stability/results.md`](experiment/stability/golden_config_stability/results.md) §6–§7.

| Parameter                          | Value          | Notes                                  |
| ---------------------------------- | -------------- | -------------------------------------- |
| `SCALEUP_STORAGE_BASE_THRESHOLD` | **0.12** | Highest threshold that still activates |
| `SCALEUP_W_STORAGE_CPU`          | 0.60           | Default                                |
| `SCALEUP_W_T_DB`                 | 0.40           | Default                                |
| `SCALEUP_STORAGE_CPU_FLOOR`      | 1.5            | Default                                |
| `SCALEUP_STORAGE_CPU_SPAN`       | 5              | Default                                |
| `SCALEUP_T_DB_FLOOR`             | 60             | Default                                |
| `SCALEUP_T_DB_SPAN`              | 250            | Default                                |
| `SCALEUP_STORAGE_REQUIRED`       | 2              | Consecutive windows for trigger        |
| `SCALEUP_STORAGE_WINDOW_SIZE`    | 5              | Sliding window                         |
| `SCALEUP_STORAGE_COOLDOWN_S`     | **120**  | Default                                |

## Compute Trigger Bundle

The **cooldown is the load-bearing value**. Determined by
[`variance_reduction`](experiment/stability/variance_reduction/results.md):
at 120 s, scale-down removes nodes during peak load (47–88 % failure in
compute phases). At **180 s**, nodes survive the storage → compute phase
transition — compute phases drop to 0.04–0.63 %, overall 0.23 %.

| Parameter                          | Value          | Why Not Default                                                                                           |
| ---------------------------------- | -------------- | --------------------------------------------------------------------------------------------------------- |
| `SCALEUP_COMPUTE_BASE_THRESHOLD` | **0.20** | Lowered from 0.45 — needed for integrated workload where compute load is dashboard-heavy but distributed |
| `SCALEUP_CPU_FLOOR`              | **3**    | Lowered from 5                                                                                            |
| `SCALEUP_T_PROC_FLOOR`           | **15**   | Lowered from 20                                                                                           |
| `SCALEDOWN_COMPUTE_COOLDOWN_S`   | **180**  | ⬆ Raised from 120.**The single most important value.**                                             |
| `SCALE_DOWN_COMPUTE_REQUIRED`    | **9**    | Consecutive below-threshold windows                                                                       |

## Infrastructure Fixes (Deployed, Not Tuneable)

These are code-level fixes confirmed by dedicated experiments — they are part of
the standard deployment, not configuration knobs:

| Fix                                               | Experiment                                                                                   | Effect                                                                                                                                                                                                |
| ------------------------------------------------- | -------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Conntrack VIP_DATA routing                        | [`conntrack_routing`](experiment/stability/conntrack_routing/results.md)                      | Eliminates stale-rule → AutoReconnect cascade. Compute: 56–65 % → 1.4 %. Zero epoch rotations.                                                                                                   |
| Cross-LAN veth TX queue (`txqueuelen=10000`)    | [`wan_http0_root_cause`](experiment/stability/wan_http0_root_cause/results.md)                | Eliminates TCP collapse on LAN2. 426× improvement. R2: 0.05 % overall.                                                                                                                              |
| MAC-recycling collision in`node_registry.py`    | [`golden_config_stability`](experiment/stability/golden_config_stability/results.md) §6–§7 | Reserve activation: 0 → 7`[reserve] activated`. Name-aware removal (B1) + self-contained slot activation (B2). Fixed 2026-06-25.                                                                   |
| Virtual-MAC mismatch in`resolve_peer_primary()` | [`rq1_evaluation`](experiment/rq1_evaluation/results.md) §8                                  | Tier 1 bidirectional activation: unidirectional → bidirectional.`_peer_storage_roles` uses real Docker MACs but `resolve_peer_primary()` was looking them up by virtual MACs. Fixed 2026-06-26. |

## Canonical Launch Command

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=<label> \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=260 CLIENTS=48 DEVICES=6000 NODES=100 STORAGE_CPUS=0.10
```

> For Tier 1 ablation (ON vs OFF), also set `VIP_HARD_TIMEOUT=60` in the env override
> and use `mechanism_necessity_all_vip60.env` / `mechanism_necessity_notier1_vip60.env`.
> For storage ablation, use `mechanism_necessity_all.env` / `mechanism_necessity_nostorage.env`.
> For compute ablation at constrained CPUs, use `current_state_integrated.env` /
> `mechanism_necessity_nocompute.env` with `CLIENTS=8 DEVICES=600 EDGE_CPUS=0.30`.
> Full ablation configs: [v5](experiment/stability/mechanism_necessity/results_v5.md),
> [v6](experiment/stability/mechanism_necessity/results_v6.md).
