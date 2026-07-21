# RQ1 v8 — Experiment Setup Declaration

> **Canonical reference** for how RQ1 was tested. Values extracted from
> `experiment_plan_v8.md`, `phases_gap.json`, `current_state_integrated.env`,
> `osken-controller.env`, and `scaling_config.py`.
> **Corresponding RQ doc**: [`rq1_v2.md`](rq1_v2.md)

---

## 1. Phases — `phases_gap.json`

9 phases, 1920 s total (~32 min). **Cleanup gaps** (240 s, 5% load) between
high-load phases force all dynamic nodes to scale down, so each stress phase
starts from zero — isolating detection speed as the sole variable.

| # | Phase | Duration | Rate/client | Cross-region | Client frac | Dominant mix |
|---|-------|----------|-------------|--------------|-------------|-------------|
| 1 | `baseline` | 60 s | 1.0 | 0% | 10% | 60% lookup, 25% ranking, 15% pressure |
| 2 | `storage_storm` | 240 s | 4.0 | 90% | 100% | 35% lookup, 30% update, 20% aggregate |
| 3 | `cleanup_gap_1` | 240 s | 0.5 | 0% | 5% | baseline mix — drain nodes before next phase |
| 4 | `tier1_hotspot` | 180 s | 5.0 | 40% | 100% | 80% lookup — Tier 1 selective-sync stress |
| 5 | `inter_hotspot_cooldown` | 300 s | 1.0 | 0% | 10% | baseline mix — drain before reverse hotspot |
| 6 | `reverse_hotspot` | 180 s | 5.0 | 40% | 100% | 80% lookup — hotspot direction reversed |
| 7 | `cleanup_gap_2` | 240 s | 0.5 | 0% | 5% | baseline mix — drain before compute spike |
| 8 | `compute_spike` | 180 s | 2.0 | 0% | 100% | 100% `service_pressure` — pure compute stress |
| 9 | `demand_drop` | 300 s | 1.0 | 0% | 10% | baseline mix — measure recovery lag |

### Rationale for key design choices

| Choice | Why |
|--------|-----|
| 240 s cleanup gaps at 5% load | Compute cooldown is 180 s; 240 s ensures all dynamic nodes drain before next high-load phase. 5% load keeps telemetry flowing so the controller doesn't dead-node-detect the static backends. |
| 90% cross-region in `storage_storm` | Saturates WAN links, stresses storage tier cross-LAN routing. |
| 40% cross-region in hotspot phases | Enough to trigger Tier 1 selective sync without saturating WAN. |
| 100% `service_pressure` in `compute_spike` | Isolates compute-bound stress — no storage component to confound. |
| 300 s cooldown between hotspots | Longer than cleanup gaps because hotspot phases need more drain time (higher rate = more inflight requests). |
| `inter_hotspot_cooldown` (not cleanup gap) | Hotspot phases share the same routing pattern; a full gap reset would waste time. Cooldown is sufficient. |

---

## 2. Resource Limits

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `CLIENTS` | 96 (48/LAN) | Doubled from v4's 48 to remove headroom that masked the coordination gap |
| `MAX_DYNAMIC_COMPUTE` | 12 | Raised from 8 so Push can demonstrate its full spawning advantage |
| `MAX_DYNAMIC_STORAGE` | 8 | Unchanged from v5 calibration |
| `STORAGE_CPUS` | 0.08 | v5 Pilot B calibration — tight enough to create CPU pressure |
| `STORAGE_MEMORY` | 512m | v5 Pilot B calibration |
| `EDGE_CPUS` | 0.30 | Default in `build_network_*.sh` |
| `EDGE_MEMORY` | 256m | Default in `build_network_*.sh` |
| `CURL_MAX_TIME` | 30 s | Hard timeout for client HTTP requests |
| `WAN_RTT_MS` | 185 ms | One-way WAN delay (~92 ms per direction); from v5 calibration |

---

## 3. Controller Scoring — Compute Scale-Up

**Source**: `current_state_integrated.env` overrides (all others from `scaling_config.py` defaults).

| Parameter | v8 Value | Default | Rationale |
|-----------|----------|---------|-----------|
| `SCALEUP_W_CPU` | 0.60 | 0.40 | CPU-weighted — compute stress is CPU-bound |
| `SCALEUP_W_T_PROC` | 0.40 | 0.60 | Latency is secondary signal for compute |
| `SCALEUP_CPU_FLOOR` | 10 | 5 | Raised floor: only detect meaningful CPU elevation |
| `SCALEUP_CPU_SPAN` | 40 | 10 | Wider span: prevents score saturation at moderate CPU |
| `SCALEUP_T_PROC_FLOOR` | 25 ms | 20 ms | Slightly elevated; healthy edge latency is ~5–15 ms |
| `SCALEUP_COMPUTE_BASE_THRESHOLD` | 0.18 | 0.45 | Lowered: the wider span compresses scores; threshold compensates |
| `SCALEUP_COMPUTE_THRESHOLD_INCREMENT` | 0.10 | 0.10 | Default — adaptive escalation per existing dynamic node |
| `SCALEUP_COMPUTE_MAX_THRESHOLD` | 0.85 | 0.85 | Default — ceiling for adaptive threshold |
| `SCALEUP_WINDOW_SIZE` | 5 | 5 | Default — 5 telemetry windows evaluated |
| `SCALEUP_REQUIRED` | 3 | 3 | Default — 3 of 5 windows must breach threshold |
| `SCALEUP_COMPUTE_COOLDOWN_S` | 45 s | 45 s | Default — grace period after each spawn |
| `SCALEUP_COMPUTE_PEER_RELIEF` | 0.03 | 0.03 | Default — score reduction per peer node |
| `SCALEUP_COMPUTE_PEER_HEALTH_THRESHOLD` | 0.35 | 0.35 | Default — peer considered healthy below this |

**Why CPU_SPAN=40 is critical**: `CPU_SPAN=5` (v3) caused immediate score
saturation — the controller spawned at the slightest CPU bump.
`CPU_SPAN=40` (v4 onward) makes the score linear across the observed CPU
range (0–50%), so Poll-30s must genuinely accumulate sustained overload
before breaching. This is what makes the blind spot consequential.

---

## 4. Controller Scoring — Storage Scale-Up

| Parameter | v8 Value | Default | Rationale |
|-----------|----------|---------|-----------|
| `SCALEUP_W_STORAGE_CPU` | 0 | 0.70 | **CPU excluded** — at 0.08 CPUs, storage CPU is I/O-wait, not a scaling signal |
| `SCALEUP_W_T_DB` | 1.0 | 0.30 | **Latency-only** — T_db is the only storage scaling signal |
| `SCALEUP_STORAGE_CPU_FLOOR` | 1.5 | 5 | Lowered to match tight CPU limits |
| `SCALEUP_STORAGE_CPU_SPAN` | 5 | 10 | Narrower span for constrained CPU range |
| `SCALEUP_T_DB_FLOOR` | 60 ms | 150 ms | Lowered: storage latency at 0.08 CPUs elevates earlier |
| `SCALEUP_T_DB_SPAN` | 250 ms | 600 ms | Narrower: tighter latency range at this CPU level |
| `SCALEUP_STORAGE_BASE_THRESHOLD` | 0.35 | 0.25 | Raised: latency-only scoring is more sensitive |
| `SCALEUP_STORAGE_WINDOW_SIZE` | 5 | 5 | Default |
| `SCALEUP_STORAGE_REQUIRED` | 2 | 2 | Default — 2 of 5 windows must breach |
| `SCALEUP_STORAGE_COOLDOWN_S` | 120 s | 120 s | Default |

---

## 5. Scale-Down

| Parameter | v8 Value | Default | Rationale |
|-----------|----------|---------|-----------|
| `SCALEDOWN_COMPUTE_COOLDOWN_S` | 180 s | 40 s | **Raised** — keeps nodes alive through phase transitions; complements cleanup gaps |
| `SCALE_DOWN_COMPUTE_REQUIRED` | 9 | 7 | Raised — requires stronger evidence of sustained low load |
| `SCALE_DOWN_COMPUTE_WINDOW_SIZE` | 12 | 12 | Default |
| `SCALEDOWN_STORAGE_COOLDOWN_S` | 120 s | 120 s | Default |
| `TELEMETRY_TIMEOUT_WINDOWS` | 18 | 18 | Default — 18 windows (~180 s) without telemetry → node marked dead |
| `NODE_BIRTH_GRACE_S` | 60 s | 60 s | Default — skip dead-node detection for first 60 s after spawn |

---

## 6. VIP Routing

| Parameter | v8 Value | Default | Rationale |
|-----------|----------|---------|-----------|
| `VIP_IDLE_TIMEOUT` | 30 s | 30 s | Default — flow idle before eviction |
| `VIP_HARD_TIMEOUT` | 60 s | 120 s | **Halved** — forces flow re-evaluation sooner; makes routing staleness visible |
| `W_CPU` (server WSM) | 0.3 | 0.3 | Default |
| `W_RAM` | 0.1 | 0.1 | Default |
| `W_REQUESTS` | 0.2 | 0.2 | Default |
| `W_HOPS` | 0.28 | 0.28 | Default |
| `CROSS_NETWORK_HOP_PENALTY` | 3 | 3 | Default — additive penalty for cross-LAN backends |

---

## 7. Telemetry Aggregation

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Aggregation window (`WINDOW_S`) | 10 s | Default — 10 s summaries; fixed across all modes |
| Delivery modes | Push (ZMQ), Poll-5s, Poll-12s, Poll-30s (HTTP) | Independent variable |
| Aggregator cache | HTTP `/telemetry/latest` — always holds freshest completed window | Ensures data is fresh at consumption; mechanism is missed windows, not stale data |

---

## 8. Topology & Seeds

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `RANDOM_SEED` | 42 | Fixed across all runs — deterministic client behavior |
| `DATA_SEED` | 42 | Fixed across all runs — deterministic test data |
| `DEVICES` | 6000 | Synthetic device pool for content generation |
| `NODES` | 100 | Synthetic content nodes |
| Topology | 2 LANs, 1 NAT router, OVS bridges | Static throughout all runs |
| Static backends/LAN | 1 edge_server, 1 edge_storage_server, 1 aggregator | Fixed |
| SDN controller | OS-Ken/Ryu, 2 instances (LAN1 + LAN2), shared topology | Fixed |
| Tier 1 selective sync | Enabled (`SS_ENABLED=1`) | Fixed — on for all runs |
| Persistent reserve | Enabled (`STORAGE_PERSISTENT_RESERVE_ENABLED=1`) | Fixed |

---

## 9. Docker Images

| Image | Tag / ID | Notes |
|-------|----------|-------|
| `edge_server` | `9f5721ed980e` | Rebuilt 2026-07-21 — EDGE_MAX_CONCURRENT semaphore removed |
| `edge_storage_server` | `0cc001492d0a` | Unchanged |
| `edge_selective_storage` | `8a0eedd11f06` | Unchanged |
| `osken-controller` | `9bbdab221f14` | Unchanged |
| `local_state_server` | `341a3d114bdd` | Unchanged |
| `ovs-container` | `009d269e762f` | Unchanged |
| `ubuntu-nat-router` | `ea95499b2b3c` | Unchanged |

---

## 10. Run Matrix

4 modes × 3 replicates = 12 runs. Order: Push → Poll-5s → Poll-12s → Poll-30s.

| # | Label | Mode | TELEMETRY_SOURCE | POLL_INTERVAL_S |
|---|-------|------|------------------|-----------------|
| P1–P3 | `rq1_v8_push_{1,2,3}` | Push | *(default — ZMQ)* | — |
| F1–F3 | `rq1_v8_poll5_{1,2,3}` | Poll-5s | `poll` | 5 |
| W1–W3 | `rq1_v8_poll12_{1,2,3}` | Poll-12s | `poll` | 12 |
| T1–T3 | `rq1_v8_poll30_{1,2,3}` | Poll-30s | `poll` | 30 |

All other parameters (`CLIENTS=96`, `WAN_RTT_MS=185`, `STORAGE_CPUS=0.08`,
`CURL_MAX_TIME=30`, `RANDOM_SEED=42`, `DATA_SEED=42`, `PHASES_CONFIG=testing/phases_gap.json`,
`OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env`)
identical across all 12 runs.

---

## 11. Measurements (M1–M9)

See [`rq1_v2.md` §5](rq1_v2.md#5-how-it-is-measured) for full metric definitions.

| M | Metric | Primary artifact |
|---|--------|-----------------|
| M1 | Spawn count | `node_lifecycle_timings.csv` |
| M2 | Missed opportunities | `rq1_missed_opportunities.csv` |
| M3 | Time-to-capacity | `rq1_time_to_capacity.csv` |
| M4 | Throughput | `client_requests.csv` |
| M5 | Timeout rate | `client_requests.csv` |
| M6 | Blind spot windows | `rq1_blind_spot_windows.csv` |
| M7 | Timeout root cause | `rq1_timeout_root_cause.csv` |
| M8 | Latency by endpoint | `rq1_endpoint_latency.csv` |
| M9 | Recovery lag | `rq1_recovery_lag.csv` |

---

## 12. Validity Gates

| Gate | Check | Source |
|------|-------|--------|
| G8 | Zero dynamic nodes added during cleanup gaps | `node_lifecycle_timings.csv` vs `phases_snapshot.json` |
| C4 | Anomaly screening: http_status=0 > 50% or LAN imbalance > 10:1 → flag for exclusion | `client_requests.csv` |
| Staleness | Information age at consumption ~0 s for all modes | `rq1_staleness.csv` |
| Overhead | Controller CPU flat across modes (~11–14%) | `rq1_overhead.csv` |
