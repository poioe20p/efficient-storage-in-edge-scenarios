# RQ2 v3 — Experiment Setup Declaration

> **Canonical reference** for how RQ2 was tested. Values extracted from
> `experiment_plan_v3.md`, `phases_rq2.json`, `current_state_integrated.env`,
> `osken-controller.env`, and `scaling_config.py`.
> **Corresponding RQ doc**: [`rq2_v3.md`](rq2_v3.md)

---

## 1. Phases — `phases_rq2.json`

9 phases, 1740 s total (~29 min). **Two-cycle scale-up workout** with
all-local traffic (cross_region_ratio=0.0) to isolate routing mechanism
from cross-region effects. Each cycle: storage_storm → cooldown →
compute_spike → cooldown, followed by extended demand_drop.

| # | Phase | Duration | Rate/client | Cross-region | Client frac | Dominant mix |
|---|-------|----------|-------------|--------------|-------------|-------------|
| 1 | `baseline` | 60 s | 1.0 | 0% | 50% | 60% lookup, 25% ranking, 15% pressure |
| 2 | `storage_storm` | 240 s | 4.0 | 0% | 100% | 35% lookup, 30% update, 20% aggregate |
| 3 | `cooldown_1` | 180 s | 1.0 | 0% | 10% | baseline mix — drain before compute spike |
| 4 | `compute_spike` | 180 s | 4.0 | 0% | 100% | 100% service_pressure — pure compute stress |
| 5 | `cooldown_2` | 180 s | 1.0 | 0% | 10% | baseline mix — drain before second cycle |
| 6 | `storage_storm_2` | 240 s | 4.0 | 0% | 100% | Same as storage_storm — second storage cycle |
| 7 | `cooldown_3` | 180 s | 1.0 | 0% | 10% | baseline mix — drain before second compute spike |
| 8 | `compute_spike_2` | 180 s | 4.0 | 0% | 100% | 100% service_pressure — second compute cycle |
| 9 | `demand_drop` | 300 s | 1.0 | 0% | 10% | baseline mix — extended drain to observe full scale-down |

### Rationale for key design choices

| Choice | Why |
|--------|-----|
| All-local traffic (cross_region_ratio=0.0) | Isolates the routing mechanism from cross-region effects. WAN latency would confound per-request latency measurements. |
| 100% service_pressure in compute_spike | Isolates compute-bound stress — no storage component to confound. Guarantees CPU saturation and compute spawns even with corrected scoring (CPU_SPAN=40). |
| rate=4.0 for all stress phases | Consistent intensity across storage and compute stress — ensures spawns in both phase types. |
| 180 s cooldowns | Compute cooldown is 180 s; cooldowns match this to ensure nodes persist through the transition but drain before the next stress phase. |
| 300 s demand_drop | Extended final drain — allows observation of full scale-down sequence. |
| No tier1_hotspot or reverse_hotspot | These phases test Tier 1 selective sync (SS_ENABLED=1), which is disabled for RQ2. Irrelevant to the routing-plane coordination gap. |
| Two-cycle design | Each stress phase appears twice → doubles the number of spawn events per run. Increases statistical power for TTFT and initial share distributions. |
| 100% service_pressure in compute_spike | Isolates compute-bound stress — no storage component to confound. Guarantees CPU saturation and compute spawns even with corrected scoring (CPU_SPAN=40). |
| client_fraction=0.10 for baseline | Matches canonical — low enough to guarantee zero unintended spawns during the quiescent control phase. G5 (baseline p50) is the cleanest routing-quality signal; background load would dilute it. |

---

## 2. Resource Limits

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `CLIENTS` | 96 (48/LAN) | RQ1 v7 golden — doubled from v2's 32 to match v7 baseline |
| `MAX_DYNAMIC_COMPUTE` | 12 | RQ1 v7 golden — raised from v2's 6 |
| `MAX_DYNAMIC_STORAGE` | 8 | RQ1 v7 golden — raised from v2's 5 |
| `STORAGE_CPUS` | 0.08 | RQ1 v7 golden — tight enough to create CPU pressure |
| `STORAGE_MEMORY` | 512m | Default in `build_network_*.sh` |
| `EDGE_CPUS` | 0.30 | Default in `build_network_*.sh` |
| `EDGE_MEMORY` | 256m | Default in `build_network_*.sh` |
| `CURL_MAX_TIME` | 30 s | RQ1 v7 golden — hard timeout for client HTTP requests |
| `WAN_RTT_MS` | 185 ms | RQ1 v7 golden — one-way WAN delay (~92 ms per direction); with all-local traffic this primarily affects storage sync between LANs |

---

## 3. Controller Scoring — Compute Scale-Up

**Source**: `current_state_integrated.env` overrides (all others from `scaling_config.py` defaults).
Identical to RQ1 v7/v8 golden configuration.

| Parameter | v3 Value | Default | Rationale |
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

**Why CPU_SPAN=40 is critical**: The original RQ2 run used `CPU_SPAN=10` (default),
causing score saturation at moderate CPU — the controller spawned at every minor CPU
bump (222–301 events). `CPU_SPAN=40` makes the score linear across the observed CPU
range (0–50%), so spawns are meaningfully driven by real sustained overload. This
reduces event count but increases per-event signal quality for TTFT and initial share.

---

## 4. Controller Scoring — Storage Scale-Up

| Parameter | v3 Value | Default | Rationale |
|-----------|----------|---------|-----------|
| `SCALEUP_W_STORAGE_CPU` | 0 | 0.70 | **CPU excluded** — at 0.08 CPUs, storage CPU is I/O-wait, not a scaling signal |
| `SCALEUP_W_T_DB` | 1.0 | 0.30 | **Latency-only** — T_db is the only storage scaling signal |
| `SCALEUP_STORAGE_CPU_FLOOR` | 1.5 | 5 | Lowered to match tight CPU limits |
| `SCALEUP_STORAGE_CPU_SPAN` | 5 | 10 | Narrower span for constrained CPU range |
| `SCALEUP_T_DB_FLOOR` | 60 ms | 150 ms | Lowered: storage latency at 0.08 CPUs elevates earlier |
| `SCALEUP_T_DB_SPAN` | 250 ms | 600 ms | Narrower: tighter latency range at this CPU level |
| `SCALEUP_STORAGE_BASE_THRESHOLD` | 0.35 | 0.25 | Raised: latency-only scoring is more sensitive; RQ3-validated value |
| `SCALEUP_STORAGE_WINDOW_SIZE` | 5 | 5 | Default |
| `SCALEUP_STORAGE_REQUIRED` | 2 | 2 | Default — 2 of 5 windows must breach |
| `SCALEUP_STORAGE_COOLDOWN_S` | 120 s | 120 s | Default |

---

## 5. Scale-Down

| Parameter | v3 Value | Default | Rationale |
|-----------|----------|---------|-----------|
| `SCALEDOWN_COMPUTE_COOLDOWN_S` | 180 s | 40 s | **Raised** — keeps nodes alive through phase transitions; complements cooldown phases |
| `SCALE_DOWN_COMPUTE_REQUIRED` | 9 | 7 | Raised — requires stronger evidence of sustained low load |
| `SCALE_DOWN_COMPUTE_WINDOW_SIZE` | 12 | 12 | Default |
| `SCALEDOWN_STORAGE_COOLDOWN_S` | 120 s | 120 s | Default |
| `TELEMETRY_TIMEOUT_WINDOWS` | 18 | 18 | Default — 18 windows (~180 s) without telemetry → node marked dead |
| `NODE_BIRTH_GRACE_S` | 60 s | 60 s | Default — skip dead-node detection for first 60 s after spawn |

---

## 6. VIP Routing

### 6.1 Backend Selection Policy (Independent Variable)

| Parameter | v3 Value | Default | Rationale |
|-----------|----------|---------|-----------|
| `BACKEND_SELECTION_POLICY` | `topology_host` / `topology_slowstart` / `topology_lifecycle` | `topology_lifecycle` | **Independent variable** — set per-run via env override file |

**Mode behavior** (from `_vip_routing/selection.py`):

| Mode | Unknown stats default | Warm lease | Ramp | Encodes |
|---|---|---|---|---|
| `topology_host` | 0.0 (best-case) | Skipped | None — round-robin fair-share | No integration between provisioner and LB |
| `topology_slowstart` | 0.0 (neutral), penalty 1.0 | Skipped | Graduated: penalty 1.0→0.0 over 45 s after discovery | Separated LB with coordination delay |
| `topology_lifecycle` | 1.0 (worst-case, bypassed) | Created at spawn (WSM bypass) | Warm lease priority window (45 s) | Unified controller — zero coordination gap |

> **Code note:** Warm leases are created unconditionally for all backends
> at spawn time. Only `topology_lifecycle` consumes them via
> `_claim_warm_backend()`; the other modes ignore them.

### 6.2 WSM Weights (Server Selection)

| Parameter | Value | Default | Rationale |
|-----------|-------|---------|-----------|
| `W_CPU` (server WSM) | 0.3 | 0.2 | From `osken-controller.env` — CPU-weighted routing |
| `W_RAM` | 0.1 | 0.2 | From `osken-controller.env` |
| `W_REQUESTS` | 0.2 | 0.2 | Default |
| `W_HOPS` | 0.28 | 0.28 | Default |
| `CROSS_NETWORK_HOP_PENALTY` | 3 | 3 | From `osken-controller.env` — additive penalty for cross-LAN backends |

### 6.3 Flow Timeouts

| Parameter | v3 Value | Default | Rationale |
|-----------|----------|---------|-----------|
| `VIP_IDLE_TIMEOUT` | 30 s | 30 s | Default — flow idle before eviction |
| `VIP_HARD_TIMEOUT` | 60 s | 120 s | **Halved** — from `current_state_integrated.env`; forces flow re-evaluation sooner |

---

## 7. Telemetry Aggregation

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Aggregation window (`WINDOW_S`) | 10 s | Default — 10 s summaries; fixed |
| Delivery mode | **Push** (ZMQ, window-close) | Held constant — RQ1's optimal delivery; isolates routing mechanism from telemetry cadence |
| Aggregator cache | HTTP `/telemetry/latest` — always holds freshest completed window | Not used for push mode; available for verification |

---

## 8. Topology & Seeds

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `RANDOM_SEED` | 42 | Fixed across all runs — deterministic client behavior |
| `CONTENT_ITEMS` | 6000 | Synthetic content pool for test data |
| Topology | 2 LANs, 1 NAT router, OVS bridges | Static throughout all runs |
| Static backends/LAN | 1 edge_server, 1 edge_storage_server, 1 aggregator | Fixed |
| SDN controller | OS-Ken/Ryu, 2 instances (LAN1 + LAN2), shared topology | Fixed |
| Tier 1 selective sync | **Disabled** (`SS_ENABLED=0`) | **RQ2-specific** — excludes Tier 1 pool to isolate routing mechanism from selective-sync contamination |
| Persistent reserve | Enabled (`STORAGE_PERSISTENT_RESERVE_ENABLED=1`) | Fixed |
| Warm-lease TTLs | Server 45 s, Storage 30 s | `scaling_config.py` defaults |
| cross_region_ratio | 0.0 (all phases) | All-local — isolates routing from WAN effects |

---

## 9. Docker Images

| Image | Notes |
|-------|-------|
| `edge_server` | No rebuild needed — `EDGE_MAX_CONCURRENT` semaphore NOT enabled for RQ2 |
| `edge_storage_server` | Unchanged |
| `edge_selective_storage` | Not used (SS_ENABLED=0) |
| `osken-controller` | Unchanged |
| `local_state_server` | Unchanged |
| `ovs-container` | Unchanged |
| `ubuntu-nat-router` | Unchanged |

---

## 10. Run Matrix

3 modes × 3 replicates = 9 runs. Order: topology_host → topology_slowstart → topology_lifecycle.

| # | Label | BACKEND_SELECTION_POLICY | Env Override File |
|---|-------|--------------------------|-------------------|
| TH1–TH3 | `rq2_v3_th_{1,2,3}` | `topology_host` | `rq2_v3_topology_host.env` |
| SS1–SS3 | `rq2_v3_ss_{1,2,3}` | `topology_slowstart` | `rq2_v3_topology_slowstart.env` |
| TL1–TL3 | `rq2_v3_tl_{1,2,3}` | `topology_lifecycle` | `rq2_v3_topology_lifecycle.env` |

All other parameters (`CLIENTS=96`, `WAN_RTT_MS=185`, `STORAGE_CPUS=0.08`,
`EDGE_CPUS=0.30`, `CURL_MAX_TIME=30`, `RANDOM_SEED=42`, `CONTENT_ITEMS=6000`,
`PHASES_CONFIG=testing/phases_override/phases_rq2.json`) identical across all 9 runs.

**Between every run**: cleanup + VM reboot (see experiment plan §8).

**Total wall-clock estimate**: 9 × (29 min run + 5 min cleanup/reboot) ≈ **5.1 hours**.

---

## 11. Measurements (G1–G8 + G2b, G4b, G5b)

See [`rq2_v3.md` §5](rq2_v3.md#5-how-it-is-measured) for full metric definitions
and the causal measurement chain.

### 11.1 Spawn-to-Service Timing — Core Evidence

All metrics computed per **compute** spawn event only. Storage spawns excluded.

| ID | Metric | Graph | Primary artifact | Operational definition |
|----|--------|-------|-----------------|----------------------|
| M1 | **TTFT** (Time-to-First-Traffic) | G1 — Box plot per mode + scatter dots | `cli_rq2_redistribution.py` | `t(first_request) − spawn_done_ts`, per spawn event. ~10 s window resolution. |
| M2 | **TFR** (Time-to-First-Response) | G2 — Box plot per mode + scatter dots | Requires per-backend response tracking instrumentation | `t(first_response) − spawn_done_ts`, per spawn event |
| M3 | **TTFT × TFR Scatter** | G2b — 2D scatter, color=mode | Derived from M1 + M2 | Joint distribution of speed vs readiness |
| M4 | **Backend Initialisation Time** | G3 — Box plot per mode + scatter dots | Derived from M1 + M2 | `tfr − ttft`, per spawn event |
| M5 | **Initial Load Share** | G4 — Box plot per mode + scatter dots | `cli_rq2_redistribution.py` | `new_backend_requests / total_VIP_requests` in first visible window |
| M6 | **TTFT × Initial Share Scatter** | G4b — 2D scatter, color=mode | Derived from M1 + M5 | Joint distribution of speed vs magnitude |

### 11.2 Service Quality — User-Visible Impact

| ID | Metric | Graph | Primary artifact | Operational definition |
|----|--------|-------|-----------------|----------------------|
| M7 | **Baseline p50 Latency** | G5 — Grouped bar, baseline phase only | `client_requests.csv` via `metrics_stats.py` | Per-mode p50 for baseline — the only phase guaranteed quiescent |
| M8 | **Non-Stress p50 Latency** | G5b — Grouped bar per low-load phase | `client_requests.csv` via `metrics_stats.py` | Per-mode p50 for baseline + cooldowns + demand_drop |
| M9 | **Per-Phase p50 Latency** | G6 — Grouped bar, all 9 phases | `client_requests.csv` via `metrics_stats.py` | Per-mode p50 per phase — the master service-quality graph |
| M10 | **Per-Mode Latency Percentiles** | G7 — Grouped bar (p50/p95/p99) per mode | `client_requests.csv` via `metrics_stats.py` | Aggregate percentiles per mode across all phases |
| M11 | **Latency by Phase Type** | G8 — Grouped bar, 4 groups (baseline / post-stress / storage / compute) | `client_requests.csv` via `metrics_stats.py` | Per-mode p95 pooled by phase type |

### 11.3 Safety

| ID | Metric | Artifact | Expected |
|----|--------|----------|----------|
| M12 | **Failure Rate** | `client_requests.csv` | HTTP status ≠ 200 ≤ 0.1% across all modes |

### 11.5 Sanity Checks

| ID | Check | Artifact | Expectation |
|----|-------|----------|-------------|
| S1 | Golden scoring applied | `controller_env_snapshot.env` | `SCALEUP_CPU_SPAN=40`, `SCALEUP_CPU_FLOOR=10`, `SCALEUP_STORAGE_BASE_THRESHOLD=0.35`, `MAX_DYNAMIC_COMPUTE=12` |
| S2 | Policy applied | `controller_env_snapshot.env` | `BACKEND_SELECTION_POLICY` matches label |
| S3 | No Tier 1 | `container_events.csv` | Zero `sel_sync_` containers |
| S4 | Scale-ups occurred | `elasticity_events.csv` | ≥ 2 unique `spawn_done` events per run |
| S5 | Spawn count consistent | `elasticity_events.csv` | IQR of spawn count within mode < 50% of mode median |

---

## 12. Validity Gates

| Gate | Trigger | Check | Source |
|------|---------|-------|--------|
| **CP-1** | Before ANY run | All three RQ2 v3 env override files match golden + RQ2 overrides (§5.2 verification command) | `rq2_v3_topology_*.env` |
| **CP0** | After `rq2_v3_th_1` | ≥ 2 unique spawn_done events? `SCALEUP_CPU_SPAN=40` confirmed in snapshot? | `elasticity_events.csv`, `controller_env_snapshot.env` |
| **CP1** | After first mode's 3 reps | TTFT and initial share consistent across replicates? (IQR < 50% of median for both) | `rq2_redistribution_summary.csv` |
| **CP2** | After second mode's 3 reps | Do TTFT and initial share differ visibly between modes? | Qualitative — full dataset needed for conclusion |
| **CP3** | End of campaign | Golden scoring + policy confirmed for all 9 `controller_env_snapshot.env` files | Cross-check all 9 snapshots |
| **S4** | Per run | Scale-ups occurred (≥ 2 per run) | `elasticity_events.csv` |
| **S5** | Per mode | Spawn count IQR < 50% of median within mode | `elasticity_events.csv` |
