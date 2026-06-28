# Experiment Plan v2 — Mechanism Necessity (WAN + Storage Load Amplification)

**Status**: ✅ Completed — 2026-06-28
**Depends on**: [v1 experiment plan](experiment_plan.md) and [v1 results](results.md) — inherits v1 structure, env files, and v1 results as baseline comparisons.
**Supersedes**: v1 for Tier 1 and storage ablations. Compute ablation is not repeated (v1 proved it decisively: 5.4× latency, 3.1× CPU, 4.2× throughput collapse).

**v2 Results**: See [results.md §5–§11](results.md) for full per-run analysis and cross-run synthesis.

**Changelog**:

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-06-28 | All 7 runs executed (E–K). Full per-run analysis produced (11 PNGs each). Results.md updated with v2 timeline. | Experiment v2 completed. Key finding: Tier 1 OFF outperforms Tier 1 ON at WAN=50 + dashboard mix (J vs I). Storage reserve provides no measurable benefit at WAN=10 (H vs G). |

**v1 baseline run references**:

- Run A (all on, WAN=10, v1 phases): `20260627_194010_mechanism_all`
- Run D (no Tier 1, WAN=10, v1 phases): `20260627_210523_mechanism_notier1`
- Run C (no storage, WAN=10, v1 phases): `20260627_202722_mechanism_nostorage`

**WAN prerequisite**: Before any WAN=50 run, edit `wan.env` line 24 from `WAN_RTT_MS=10` to `WAN_RTT_MS=${WAN_RTT_MS:-10}` to allow make command-line override. Verify with `wan_set.sh` (no args) that the current setting reads back before starting.

**phases.json edit**: Between Runs F and G, edit `storage_hotspot` in `phases.json`: `rate_per_client` 10→8, `mix` `{"device_status":0.90,...}` → `{"device_status":0.30,"dashboard":0.60,"service_pressure":0.10}`. `phases_snapshot.json` in each run folder captures the profile that actually ran.

## Intent

v1 proved compute scale-up is causally necessary. Tier 1 showed a 1,279× owner-LAN `time_db` effect but modest consumer-side improvement (1.3–1.4×) because `WAN_RTT_MS=10` (5 ms one-way) makes the cross-region network penalty negligible relative to total request time. Storage showed no meaningful degradation because `device_status` lookups consume <1% MongoDB CPU.

v2 addresses both limitations with two independent changes, each tested in isolation before being combined:

1. **WAN latency amplification** (`WAN_RTT_MS=10` → `50`): increases the cross-region network penalty from ~10 ms to ~50 ms RTT. This should make Tier 1's consumer-side latency benefit visible in overall request latency, not just `time_db`. All cross-region phases (`storage_hotspot`, `tier1_hotspot_n1`, `tier1_hotspot_n2`) will show elevated baseline latency.
2. **Storage load amplification** (`storage_hotspot` mix from 90% device_status → 60% dashboard): dashboard aggregation queries are CPU/memory-intensive on MongoDB, replacing the near-free indexed lookups that left MongoDB at <1% CPU in v1. This should make storage scale-up's per-node CPU distribution benefit clearly measurable.

Each change is tested in isolation (Runs E, G) against v1 baselines, then combined with mechanism ablations (Runs F, H for pure single-variable; J, K for both changes) and the v2 combined reference (I) to prove Tier 1 and storage necessity under amplified conditions.

## Hypothesis / Expected Outcome

1. **WAN isolation (E vs v1 Run A)**: All cross-region phases should show elevated total request latency at WAN=50 vs WAN=10. Consumer-LAN `avg_time_db` should increase proportionally. Non-cross-region phases (`baseline`, `local_moderate`, `compute_spike`) should be unaffected.
2. **Storage load isolation (G vs v1 Run A)**: `storage_hotspot` should show elevated per-node storage CPU (target ≥3× v1's 0.7%) and elevated `avg_time_db` due to dashboard aggregation cost. Total request latency should increase because dashboard queries are slower than device_status lookups.
3. **Tier 1 ablation at WAN=50 (F vs E for pure; J vs I for combined)**: With the amplified cross-region penalty, Tier 1 should produce a **consumer-visible** latency improvement (target ≥1.5× in `tier1_hotspot_n1`/`n2` total request latency, not just `time_db`). The owner-LAN protection effect seen in v1 (1,279×) should persist or strengthen.
4. **Storage ablation with heavy queries (H vs G for pure; K vs I for combined)**: With dashboard-heavy `storage_hotspot`, the single fixed MongoDB should show substantially higher per-node CPU (target ≥2×) and higher `avg_time_db` than the distributed 2+ nodes.
5. **Combined reference (I)**: All three mechanisms should exercise. Cross-region phases should show elevated baseline latency (WAN=50 effect). `storage_hotspot` should show meaningful storage CPU (dashboard effect). `compute_spike` should behave as in v1 (compute scale-up handles it).

## RQ Linkage

Same as v1: RQ1 (stable control plane), RQ2 (backend selection requires correct routing), RQ3 (locality strategy — Tier 1 eliminates cross-region penalty, storage reserve provides read capacity).

## Independent Variables & Held-Constant Set

Two independent variables, tested separately then together:

| Variable                | v1 value          | v2 value                | Isolated in |
| ----------------------- | ----------------- | ----------------------- | ----------- |
| WAN RTT                 | 10 ms            | **50 ms**        | Run E       |
| `storage_hotspot` mix | 90% device_status | **60% dashboard** | Run G       |

**Held constant**: all mechanism toggles (except where ablated), all thresholds, cooldowns, sizing (`CLIENTS=8`, `DEVICES=600`, `NODES=100`), WAN profile (except RTT), host, code, images. No `--fault-plan`. Same env override files as v1.

### Mechanism Toggles Per Run

| Run                         | `MAX_DYNAMIC_COMPUTE` | `STORAGE_PERSISTENT_RESERVE_ENABLED` | `SS_ENABLED` | `MAX_DYNAMIC_STORAGE` |
| --------------------------- | ----------------------- | -------------------------------------- | -------------- | ----------------------- |
| E (wan50)                   | 6                       | 1                                      | 1              | 5                       |
| F (wan50 no tier1)          | 6                       | 1                                      | **0**    | 5                       |
| G (storageheavy)            | 6                       | 1                                      | 1              | 5                       |
| H (storageheavy no storage) | 6                       | **0**                            | 1              | **0**             |
| I (v2 all)                  | 6                       | 1                                      | 1              | 5                       |
| J (v2 no tier1)             | 6                       | 1                                      | **0**    | 5                       |
| K (v2 no storage)           | 6                       | **0**                            | 1              | **0**             |

### Fixed Threshold Bundle

Identical to v1 (see [v1 plan](experiment_plan.md#fixed-threshold-bundle-all-4-runs)):

- `SCALEUP_STORAGE_BASE_THRESHOLD=0.10` (t10)
- `SCALEDOWN_STORAGE_COOLDOWN_S=300`
- `SCALEDOWN_COMPUTE_COOLDOWN_S=180`
- `SCALEUP_COMPUTE_BASE_THRESHOLD=0.20`
- All other values from v1 env files.

## Run Matrix

| Run         | Label                                | WAN            | Phases                                       | Mechanisms | Env override                          | Compares to                                            |
| ----------- | ------------------------------------ | -------------- | -------------------------------------------- | ---------- | ------------------------------------- | ------------------------------------------------------ |
| **E** | `mechanism_wan50`                  | **50ms** | v1 (device_status`storage_hotspot`)        | All on     | `mechanism_necessity_all.env`       | v1 Run A (WAN=10)                                      |
| **F** | `mechanism_wan50_notier1`          | **50ms** | v1                                           | No Tier 1 | `mechanism_necessity_notier1.env`   | E (**pure Tier 1 ablation at WAN=50**)          |
| **G** | `mechanism_storageheavy`           | 10ms           | **v2** (dashboard `storage_hotspot`) | All on     | `mechanism_necessity_all.env`       | v1 Run A (device_status mix)                           |
| **H** | `mechanism_storageheavy_nostorage` | 10ms           | **v2**                                 | No storage | `mechanism_necessity_nostorage.env` | G (**pure storage ablation with heavy queries**) |
| **I** | `mechanism_v2_all`                 | **50ms** | **v2**                                 | All on     | `mechanism_necessity_all.env`       | — (v2 combined reference)                             |
| **J** | `mechanism_v2_notier1`             | **50ms** | **v2**                                 | No Tier 1 | `mechanism_necessity_notier1.env`   | I (Tier 1 ablation, both changes)                     |
| **K** | `mechanism_v2_nostorage`           | **50ms** | **v2**                                 | No storage | `mechanism_necessity_nostorage.env` | I (storage ablation, both changes)                     |

Run order: **E → F** (v1 phases, WAN=50) → **[edit phases.json to v2]** → **G → H** (v2 phases, WAN=10) → **I → J → K** (v2 phases, WAN=50).

Only **one phase edit** required: after E/F, before G. Runs G, H, I, J, K all use the same v2 phases.

**Clean (single-variable) ablations:**

- **F vs E**: WAN=50 with/without Tier 1, v1 phases — isolates Tier 1 effect from storage mix change
- **H vs G**: heavy queries with/without storage, WAN=10 — isolates storage effect from WAN change

**Combined ablations** (J vs I, K vs I) show mechanism effects under both amplified conditions simultaneously.

**Cross-phase comparison warning**: Run E (v1 `storage_hotspot` mix) and Runs G–K (v2 `storage_hotspot` mix) have different `storage_hotspot` profiles. Do not compare E's `storage_hotspot` metrics to G's — the comparison is confounded by both WAN (50 vs 10) and mix (device_status vs dashboard). Use E only for Tier 1 phase comparisons and WAN isolation.

## Run Configuration

All runs use identical launch shape except `RUN_LABEL`, `WAN_RTT_MS`, and `OSKEN_ENV_OVERRIDE_FILE`. Runs G, H, I, J, K share the same edited `phases.json`.

```bash
# Run E — WAN isolation (WAN=50, v1 phases, all on)
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_all.env \
  RUN_LABEL=mechanism_wan50 \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=50 \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# Run F — Pure Tier 1 ablation at WAN=50 (WAN=50, v1 phases, no Tier 1)
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_notier1.env \
  RUN_LABEL=mechanism_wan50_notier1 \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=50 \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# Run G — Storage load isolation (WAN=10, v2 phases, all on)
# [EDIT phases.json to v2 profile before this run]
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_all.env \
  RUN_LABEL=mechanism_storageheavy \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# Run H — Pure storage ablation with heavy queries (WAN=10, v2 phases, no storage)
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_nostorage.env \
  RUN_LABEL=mechanism_storageheavy_nostorage \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# Run I — v2 combined reference (WAN=50, v2 phases, all on)
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_all.env \
  RUN_LABEL=mechanism_v2_all \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=50 \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# Run J — v2 Tier 1 ablation (WAN=50, v2 phases, no Tier 1)
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_notier1.env \
  RUN_LABEL=mechanism_v2_notier1 \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=50 \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# Run K — v2 storage ablation (WAN=50, v2 phases, no storage)
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_nostorage.env \
  RUN_LABEL=mechanism_v2_nostorage \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=50 \
  CLIENTS=8 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

- `--phases-config`: `testing/phases.json`. For Runs E and F: v1 8-phase profile (device_status-heavy `storage_hotspot`). For Runs G–K: v2 8-phase profile (dashboard-heavy `storage_hotspot`). Edit `phases.json` between F and G.
- `WAN_RTT_MS=50`: sets symmetric round-trip WAN latency to 50 ms (25 ms one-way on each router egress). Omitted for Runs G and H (default to 10 ms from `wan.env`).
- `--clients-per-lan`: `8`, `--seed-devices`: `600`, `--seed-nodes`: `100`.
- `--fault-plan`: **omitted**.
- Images: no rebuild required.

### v2 Phase Profile (Runs G, H, I, J, K)

Only `storage_hotspot` changes from v1:

| # | Phase                         | Dur  | Rate        | Cross | Clients | Mix (dev/dsh/svc)  | Hotspot    |
| - | ----------------------------- | ---- | ----------- | ----- | ------- | ------------------ | ---------- |
| 1 | `baseline`                  | 60s  | 1           | 0%    | 50%     | 60/25/15           | —         |
| 2 | `local_moderate`            | 60s  | 3           | 0%    | 75%     | 55/30/15           | —         |
| 3 | **`storage_hotspot`** | 240s | **8** | 90%   | 100%    | **30/60/10** | lan2→lan1 |
| 4 | `tier1_hotspot_n1`          | 180s | 8           | 95%   | 100%    | 95/3/2             | lan2→lan1 |
| 5 | `inter_hotspot_cooldown`    | 60s  | 2           | 0%    | 50%     | 60/25/15           | —         |
| 6 | `tier1_hotspot_n2`          | 180s | 8           | 95%   | 100%    | 95/3/2             | lan1→lan2 |
| 7 | `compute_spike`             | 180s | 7           | 5%    | 100%    | 20/65/15           | —         |
| 8 | `cooldown`                  | 120s | 1           | 0%    | 50%     | 60/25/15           | —         |

**Changes from v1 `storage_hotspot`:**

| Parameter             | v1     | v2                 | Rationale                                                                                                                      |
| --------------------- | ------ | ------------------ | ------------------------------------------------------------------------------------------------------------------------------ |
| `rate_per_client`   | 10     | **8**        | Dashboard queries stress edge server CPU; 8 r/s × 8 clients = 64 total req/s (safe margin below ~100 req/s ceiling)          |
| `mix` (dev/dsh/svc) | 90/5/5 | **30/60/10** | 60% dashboard aggregation queries are CPU/memory-intensive on MongoDB (v1's 90% device_status lookups left MongoDB at <1% CPU) |

Tier 1 and compute phases are unchanged from v1. `storage_hotspot` duration stays at 240s. Runs G, H, I, J, K all use this v2 profile.

### WAN Latency Effect Scope

`WAN_RTT_MS=50` (25 ms one-way on each router egress) affects ALL cross-region traffic:

| Phase                      | Cross-region ratio | Expected latency increase                                           |
| -------------------------- | ------------------ | ------------------------------------------------------------------- |
| `baseline`               | 0%                 | None                                                                |
| `local_moderate`         | 0%                 | None                                                                |
| `storage_hotspot`        | 90%                | **Significant** — 72 cross-region req/s at +40 ms RTT       |
| `tier1_hotspot_n1`       | 95%                | **Significant** — consumer-LAN `time_db` baseline elevated |
| `inter_hotspot_cooldown` | 0%                 | None                                                                |
| `tier1_hotspot_n2`       | 95%                | **Significant** — consumer-LAN `time_db` baseline elevated |
| `compute_spike`          | 5%                 | Negligible                                                          |
| `cooldown`               | 0%                 | None                                                                |

This means Runs E, F, I, J, K will show elevated total request latency in all three hotspot phases compared to v1 equivalents — not just `time_db` but also the client-visible HTTP response time. This is intentional: it amplifies the Tier 1 consumer-side signal and makes the cross-region penalty observable in `client_requests.csv` latency, not just `resource_stats.csv` `time_db`.

## Focus & Evidence

**Primary focus**: same as v1 — `client_requests.csv` + `resource_stats.csv` + controller logs. The WAN=50 runs will additionally require tracking total request latency in cross-region phases as a consumer-visible Tier 1 metric.

**New evidence for v2:**

| Evidence                                     | Source                                                | Used for                                                                |
| -------------------------------------------- | ----------------------------------------------------- | ----------------------------------------------------------------------- |
| Total request latency in cross-region phases | `client_requests.csv` via `cli_mechanism_compare` | WAN isolation (E vs v1 A), Tier 1 ablation (F vs E)                    |
| Consumer-LAN`avg_time_db_ms`               | `resource_stats.csv`                                | Tier 1 ablation — now expected visible in total latency too           |
| Per-node storage CPU% in`storage_hotspot`  | `per_node_stats.csv`                                | Storage load isolation (G vs v1 A), storage ablation (H vs G, K vs I)   |
| `avg_time_db_ms` in `storage_hotspot`    | `resource_stats.csv`                                | Storage ablation — dashboard queries should produce meaningful DB time |

## Metrics & Success Criteria

All `time_db` references use `avg_time_db_ms` from `resource_stats.csv`. `p95_time_db_ms` is not populated by the current telemetry collector (uniformly zero in v1 results).

### 1. WAN Isolation (E vs v1 Run A)

| Metric                               | Target             | Phases                                              |
| ------------------------------------ | ------------------ | --------------------------------------------------- |
| Run E total request latency          | ≥1.5× v1 Run A   | `tier1_hotspot_n1`, `tier1_hotspot_n2`          |
| Run E consumer-LAN`avg_time_db_ms` | ≥1.5× v1 Run A   | `tier1_hotspot_n1`, `tier1_hotspot_n2`          |
| Non-cross-region phases (E vs A)     | ≤1.2× difference | `baseline`, `local_moderate`, `compute_spike` |

Targets are conservative: v1 consumer-LAN `avg_time_db_ms` was ~74ms at WAN=10. At WAN=50 (+40ms RTT), linear expectation is ~114ms (1.5×). Non-linear effects (connection pooling, queuing) could amplify this. The directional effect (E > A in cross-region phases, E ≈ A in local phases) is the primary criterion.

### 2. Pure Tier 1 Ablation at WAN=50 (F vs E)

| Metric                                  | Target        | Phases                                     |
| --------------------------------------- | ------------- | ------------------------------------------ |
| Run F total request latency             | ≥1.5× Run E | `tier1_hotspot_n1`, `tier1_hotspot_n2` |
| Run F consumer-LAN`avg_time_db_ms`    | ≥3× Run E   | `tier1_hotspot_n1`, `tier1_hotspot_n2` |
| Owner-LAN`avg_time_db_ms` degradation | ≥10×        | `tier1_hotspot_n2`                       |

This is the **cleanest Tier 1 ablation** — WAN=50 amplifies the cross-region penalty while v1 phases isolate the effect from the storage mix change. Total latency targets are softer (≥1.5×) because fixed costs (Flask processing, local network) dilute the DB-time improvement. `avg_time_db_ms` targets are ≥3× because DB time scales with WAN RTT.

### 3. Storage Load Isolation (G vs v1 Run A)

| Metric                         | Target                                          | Phase               |
| ------------------------------ | ----------------------------------------------- | ------------------- |
| Run G avg storage CPU per node | ≥3× v1 Run A (≥~2.1%)                        | `storage_hotspot` |
| Run G`avg_time_db_ms`        | ≥2× v1 Run A                                  | `storage_hotspot` |
| Run G total request latency    | ≥1.5× v1 Run A (dashboard queries are slower) | `storage_hotspot` |

### 4. Pure Storage Ablation with Heavy Queries (H vs G)

| Metric                         | Target        | Phase               |
| ------------------------------ | ------------- | ------------------- |
| Run H avg storage CPU per node | ≥2× Run G   | `storage_hotspot` |
| Run H`avg_time_db_ms`        | ≥1.5× Run G | `storage_hotspot` |
| Run H total request latency    | ≥1.3× Run G | `storage_hotspot` |

This is the **cleanest storage ablation** — dashboard-heavy queries stress MongoDB while WAN=10 isolates the effect from the WAN latency change.

**Compute-parity checkpoint**: dashboard queries stress both edge server CPU and MongoDB CPU. Compute scale-up may trigger during `storage_hotspot` in both Run G and Run H. After both runs complete, verify that compute scale-up behavior (timing, `server_count` peak) is comparable between G and H. If they differ by >1 server, flag the storage comparison as potentially confounded.

### 5. Combined Tier 1 Ablation (J vs I)

| Metric                                  | Target        | Phases                                     |
| --------------------------------------- | ------------- | ------------------------------------------ |
| Run J total request latency             | ≥1.5× Run I | `tier1_hotspot_n1`, `tier1_hotspot_n2` |
| Run J consumer-LAN`avg_time_db_ms`    | ≥3× Run I   | `tier1_hotspot_n1`, `tier1_hotspot_n2` |
| Owner-LAN`avg_time_db_ms` degradation | ≥10×        | `tier1_hotspot_n2`                       |

### 6. Combined Storage Ablation (K vs I)

| Metric                         | Target        | Phase               |
| ------------------------------ | ------------- | ------------------- |
| Run K avg storage CPU per node | ≥2× Run I   | `storage_hotspot` |
| Run K`avg_time_db_ms`        | ≥1.5× Run I | `storage_hotspot` |
| Run K total request latency    | ≥1.3× Run I | `storage_hotspot` |

### 7. Mechanism Exercise Gate (Run I)

Same as v1 Run A: all three mechanisms must exercise (≥1 compute trigger, ≥1 `[reserve] activated`, Tier 1 `ACTIVE` in both directions). If storage fails to activate, continue — the ablation still compares per-node load.

**Diagnostic decision tree — Run I mechanism gate failure:**

| Mechanism missing                                    | Check                                                         | Likely cause                                                                     | Fix                                                                      |
| ---------------------------------------------------- | ------------------------------------------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------ |
| Compute: no`server_count > 1` in `compute_spike` | Controller logs for`[scale-up] compute`                     | Threshold too high or dashboard mix in`storage_hotspot` pre-triggered cooldown | Lower`SCALEUP_COMPUTE_BASE_THRESHOLD` or extend cooldown               |
| Storage: no`[reserve] activated`                   | Controller logs for`[scale-up] storage triggered`           | Dashboard queries changed the degradation score profile vs v1                    | Lower`SCALEUP_STORAGE_BASE_THRESHOLD` from 0.10 → 0.08; re-run I only |
| Tier 1: no`SelectiveSyncAlert`                    | Controller logs for`SelectiveSync`; `coord_hot_doc_total` | Hot set not concentrated enough with dashboard mix                               | Verify`cross_region_ratio` in tier1 phases is 0.95                     |

### 8. Control-Plane Health (all runs)

Same as v1: no tracebacks, no crash loops, zero epoch rotations, clean drain.

## Checkpoints

| Trigger                         | Question                                                              | Evidence                                | Runner action |
| ------------------------------- | --------------------------------------------------------------------- | --------------------------------------- | ------------- |
| End of`baseline`              | Is storage reserve`READY_RESERVED` on both LANs?                    | Controller logs                         | Report only   |
| Mid`storage_hotspot` (~180s)  | Has`[reserve] activated`? Has compute scaled up (dashboard stress)? | Controller logs,`resource_stats.csv`  | Report only   |
| Mid`tier1_hotspot_n1` (~480s) | Has Tier 1 reached`ACTIVE`? Consumer latency elevated at WAN=50?   | Controller logs,`client_requests.csv` | Report only   |
| Mid`tier1_hotspot_n2` (~720s) | Has Tier 1 reached`ACTIVE` for reverse?                            | Controller logs                         | Report only   |
| Mid`compute_spike` (~900s)    | Has compute elasticity added servers?                                 | `resource_stats.csv`                  | Report only   |
| End of`cooldown`              | Clean drain?                                                          | `container_events.csv`                | Report only   |

## Validity Threats & Limitations

- **WAN=50 affects all cross-region phases**: the increased latency is not Tier 1-specific — `storage_hotspot` also sees elevated latency. This is intentional (real-world WAN links have latency) but means cross-phase comparisons must account for the WAN baseline shift.
- **Dashboard mix conflates compute and storage stress**: 60% dashboard in `storage_hotspot` stresses both edge server CPU and MongoDB CPU. Compute scale-up may trigger during the storage phase. The compute-parity checkpoint (§4) mitigates this — verify comparable compute behavior between paired runs.
- **Single replicate**: each condition runs once. Replication would be ideal but the v1 baselines provide comparison points.
- **Phase edit between F and G**: `phases.json` must be edited between runs. The plan documents the exact v1 and v2 profiles. `phases_snapshot.json` in each run folder captures the profile that actually ran.
- **v1 phases for Runs E/F**: Runs E and F use v1 phases to isolate the WAN effect. The `storage_hotspot` mix difference between E/F and G–K means `storage_hotspot` comparisons across those run groups are confounded by phase differences — use E/F for WAN and Tier 1 comparisons only.
- **`p95_time_db_ms` unavailable**: the telemetry collector does not populate this column. All `time_db` targets use `avg_time_db_ms`.

## Artifact Contract

Same as v1. Each run folder under `source/scripts/testing/metrics/<timestamp>_mechanism_<label>/` must contain the standard artifacts plus `controller_env_snapshot.env` (with `WAN_RTT_MS` provenance from the environment) and `phases_snapshot.json`.

Expected later analysis outputs:

- Per-run `cli_simple_run` summaries
- Cross-run `cli_mechanism_compare` (v2 runs + v1 Run A for WAN isolation comparison)
- Cross-run `cli_simple_compare` (v2 runs only)
- Comparison tables:
  - WAN isolation: E vs v1 Run A (`20260627_194010_mechanism_all`)
  - Pure Tier 1 ablation at WAN=50: F vs E
  - Storage load isolation: G vs v1 Run A
  - Pure storage ablation with heavy queries: H vs G
  - Combined Tier 1 ablation: J vs I
  - Combined storage ablation: K vs I
