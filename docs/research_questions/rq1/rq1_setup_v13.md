# RQ1 v13 — Experiment Setup Declaration

> **Canonical reference** for how RQ1 v13 was tested. Values extracted from
> `experiment_plan_v13.md`, `phases.json` (v13 redesign), `current_state_integrated.env`,
> `osken-controller.env`, and `scaling_config.py`.
> **Corresponding RQ doc**: [`rq1_v13.md`](rq1_v13.md)

---

## 1. Phases — `phases.json`

9 phases, 1760 s total (~29 min). **Cleanup gaps** (220 s, 5% load) between
high-load phases exceed `SCALEDOWN_COMPUTE_COOLDOWN_S=180` and
`SCALEUP_STORAGE_COOLDOWN_S=120`, ensuring all dynamic nodes drain during
gaps (G8). Two `storage_storm` phases double-measure the cascade mechanism.
`compute_spike` removed — eliminates the `window_min=1` variance source
identified in v12.

Redesigned from v10/v12: stress phases shortened to amplify blind-spot
fraction (20% of each event vs 12-17%). Total runtime reduced 8% (1760s
vs 1920s).

| # | Phase | Duration | Rate/client | Cross-region | Client frac | Dominant mix |
|---|-------|----------|-------------|--------------|-------------|-------------|
| 1 | `baseline` | 60 s | 1.0 | 0% | 10% | 60% lookup, 25% ranking, 15% pressure |
| 2 | `storage_storm` | **150 s** | 4.0 | 90% | 100% | 35% lookup, 30% update, 20% aggregate |
| 3 | `cleanup_gap_1` | **220 s** | 0.5 | 0% | 5% | baseline mix — drain nodes before hotspot |
| 4 | `tier1_hotspot` | **150 s** | 5.0 | 40% | 100% | 80% lookup — Tier 1 selective-sync stress |
| 5 | `cleanup_gap_2` | **220 s** | 0.5 | 0% | 5% | baseline mix — drain before reverse hotspot |
| 6 | `reverse_hotspot` | **150 s** | 5.0 | 40% | 100% | 80% lookup — identical workload to tier1_hotspot |
| 7 | `cleanup_gap_3` | **220 s** | 0.5 | 0% | 5% | baseline mix — drain before second storage storm |
| 8 | `storage_storm_2` | **150 s** | 4.0 | 90% | 100% | Identical to phase 2 — second cascade measurement |
| 9 | `demand_drop` | 300 s | 1.0 | 0% | 10% | baseline mix — measure recovery lag |

**What changed from v10/v12**:

| Change | From | To | Rationale |
|--------|------|-----|-----------|
| Stress phases | 180–240 s | **150 s** | Blind spot = 20% of phase (was 12–17%) |
| Cleanup gaps | 240–300 s | **220 s** | Still > cooldowns, less recovery margin |
| `inter_hotspot_cooldown` (300 s) | Present | **Removed** | Merged into `cleanup_gap_2` (220 s) |
| `compute_spike` (180 s) | Present | **Removed** | Eliminates `window_min=1` variance source |
| `storage_storm_2` (150 s) | Absent | **Added** | Second measurement of the storage cascade |
| `cleanup_gap_3` (220 s) | Absent | **Added** | New gap before `storage_storm_2` |

**`reverse_hotspot` starting condition**: With 220s between `tier1_hotspot`
and `reverse_hotspot`, dynamic compute nodes from the first hotspot may still
be alive (scale-down requires 90s idle detection + 180s cooldown from last
spawn). `reverse_hotspot` starts with potentially pre-warmed capacity while
`tier1_hotspot` starts cold. Consistent across all modes.

---

## 2. Resource Limits

| Parameter | v13 Value | v12 Value | Rationale |
|-----------|-----------|-----------|-----------|
| `CLIENTS` | 96 (48/LAN) | 96 | Same as v8/v10/v12 |
| `MAX_DYNAMIC_COMPUTE` | 12 | 12 | Same as v8/v10/v12 |
| `MAX_DYNAMIC_STORAGE` | 8 | 8 | Same as v8/v10/v12 |
| `STORAGE_CPUS` | **0.05** | 0.05 | v11 calibration winner — unchanged |
| `STORAGE_MEMORY` | 512m | 512m | Same as v8/v10/v12 |
| `EDGE_CPUS` | **0.15** | 0.15 | v10/v12 proven; Push handles this |
| `EDGE_MEMORY` | 256m | 256m | Build script default |
| `CURL_MAX_TIME` | 30 s | 30 s | Same as v8/v10/v12 |
| `--connect-timeout` | **(removed)** | 5 s | **Dropped in v13** — `compute_spike` removed; accept-queue collapse risk eliminated |
| `WAN_RTT_MS` | 185 ms | 185 ms | Same as v8/v10/v12 |

### 2.1 Why STORAGE_CPUS = 0.05

At v10's `STORAGE_CPUS=0.08`, the storage tier had enough headroom that the
blind-spot penalty only produced a throughput gap (−14%) — timeout rates
converged because both modes eventually provisioned enough nodes.

At 0.05 (−38% vs v10), each storage operation takes longer. Under stress-phase
load, the storage tier becomes the bottleneck FIRST — storage ops slow → edge
servers queue waiting for storage → throughput degrades. Push detects storage
saturation and receives the telemetry within ~14 s (window close + delivery +
scoring) and provisions. Poll-30s may not detect for up to 30 s — during
which the cascade propagates through the edge tier.

The v11 calibration confirmed S2 (STORAGE=0.05) as the only configuration
producing Push vs Poll-30s separation. v12 confirmed the separation at n=3 in
stable runs (15% throughput gap, 1.44× p95 gap) but revealed instability from
the `compute_spike` phase.

### 2.2 Why Redesigned Phases

v12's 240s and 180s stress phases diluted the 30s blind spot to 12-17% of
each event. Both modes spent most of each phase provisioned, muting the gap.
v13's 150s phases make the blind spot 20% of each stress event — amplifying
the throughput penalty. Two `storage_storm` phases double-measure the cascade
mechanism where the gap is most visible.

### 2.3 Why `--connect-timeout` Removed

v12 used `--connect-timeout 5` to catch TCP accept-queue failures during P30's
blind spot as `http_status=0` events. This produced a 2.9× timeout ratio in
the v11 pilot but amplified the `compute_spike` variance at n=3 (P2 had 95%
of timeouts at <5s latency). With `compute_spike` removed in v13, the
accept-queue collapse risk is eliminated. TCP-level failures that do occur
appear as high-latency completions or `CURL_MAX_TIME=30` timeouts. The
timeout gap is muted by design — throughput and tail latency carry the
evidence.

---

## 3. Controller Scoring — Compute Scale-Up

**Source**: `current_state_integrated.env` overrides. Identical to v8/v10/v12.

| Parameter | v13 Value | Rationale |
|-----------|----------|-----------|
| `SCALEUP_W_CPU` | 0.60 | CPU-weighted — compute stress is CPU-bound |
| `SCALEUP_W_T_PROC` | 0.40 | Latency is secondary signal for compute |
| `SCALEUP_CPU_FLOOR` | 10 | Raised floor: only detect meaningful CPU elevation |
| `SCALEUP_CPU_SPAN` | 40 | Wider span: prevents score saturation at moderate CPU |
| `SCALEUP_T_PROC_FLOOR` | 25 ms | Slightly elevated; healthy edge latency is ~5-15 ms |
| `SCALEUP_COMPUTE_BASE_THRESHOLD` | 0.18 | Lowered: wider span compresses scores |
| `SCALEUP_COMPUTE_COOLDOWN_S` | 45 s | Grace period after each spawn |
| `SCALEUP_REQUIRED` | 3 | 3 of 5 windows must breach threshold |

---

## 4. Controller Scoring — Storage Scale-Up

Identical to v8/v10/v12.

| Parameter | v13 Value | Rationale |
|-----------|----------|-----------|
| `SCALEUP_W_STORAGE_CPU` | 0 | CPU excluded — at tight limits, CPU is I/O-wait |
| `SCALEUP_W_T_DB` | 1.0 | Latency-only — T_db is the sole storage signal |
| `SCALEUP_STORAGE_BASE_THRESHOLD` | 0.35 | Storage latency trigger |
| `SCALEUP_STORAGE_WINDOW_SIZE` | 5 | 5 telemetry windows evaluated |
| `SCALEUP_STORAGE_REQUIRED` | 2 | 2 of 5 windows must breach |
| `SCALEUP_STORAGE_COOLDOWN_S` | 120 | Grace period after each storage spawn |

---

## 5. Controller Scoring — Scale-Down

Identical to v8/v10/v12.

| Parameter | v13 Value | Rationale |
|-----------|----------|-----------|
| `SCALEDOWN_COMPUTE_COOLDOWN_S` | 180 | < cleanup gap (220s) — ensures G8 |
| `SCALE_DOWN_COMPUTE_REQUIRED` | 9 | Sustained low load before scale-down |

---

## 6. Telemetry Delivery

| Mode | How | Latency | Blind-spot window |
|------|-----|---------|-------------------|
| Push | Aggregator pushes via ZMQ at window close | ~14 s (window + fan-out + scoring) | ~0 s |
| Poll-5s | Controller polls HTTP cache every 5 s | ~5 s + ~14 s processing | ~5 s |
| Poll-12s | Controller polls HTTP cache every 12 s | ~12 s + ~14 s processing | ~12 s |
| Poll-30s | Controller polls HTTP cache every 30 s | ~30 s + ~14 s processing | ~30 s |

---

## 7. Network Topology

Two LANs, symmetric. 8 static containers (edge_server ×2, edge_storage_server
×2, aggregator ×2 + NAT router + OVS). 96 client namespaces (48/LAN).

| Parameter | Value |
|-----------|-------|
| `WAN_RTT_MS` | 185 ms |
| VIP routing | Double-VIP model (VIP_SERVER, VIP_DATA per LAN) |
| Cross-LAN routing | Via NAT router (WAN bridge) |

---

## 8. Infrastructure (Cloud VM)

Dell PowerEdge R620, Proxmox VM. `ip_forward=1`, no swap. Docker bridge +
OVS (Open vSwitch). OS-Ken SDN controller with custom Ryu modules.

## 9. Docker Images

| Image | CPU | Memory | Notes |
|-------|-----|--------|-------|
| `edge_server` | 0.15 | 256m | Process-based: content_lookup, feed_ranking, service_pressure |
| `edge_storage_server` | 0.05 | 512m | MongoDB single-node replica set per LAN |
| `aggregator` | (default) | (default) | Telemetry aggregation + ZMQ push |
| `ovs` | (default) | (default) | Open vSwitch (OVS) |
| `nat-router` | (default) | (default) | WAN bridge |
| `client` | (default) | (default) | 96 network namespaces with curl |

## 10. Traffic Generator

`source/scripts/testing/traffic_generator.py` — synchronous per-client loop.
Each client waits for curl to finish before sending the next request. Latency
directly throttles throughput — measuring real user-experienced throughput,
not an artificial firehose.

| Parameter | Value |
|-----------|-------|
| Curl timeout | `--max-time 30` |
| Connect timeout | **(removed in v13)** |
| Rate pacing | `interval = 1.0 / phase.rate_per_client` with jitter |
| HTTP method | GET (POST for content_update/aggregate with body) |

## 11. Data Seeding

`setup_test_data` pre-populates each LAN's MongoDB with 6,000 content items
(12,000 total across LANs). `DATA_SEED=42` ensures deterministic generation.
`RANDOM_SEED=42` controls client request randomization.

## 12. Expected Delivered Requests (per run)

Based on v12 stable-run per-phase throughput scaled to 150s stress phases.
Values are estimates pending v13 execution.

| Phase | Push (req) | Poll-30s (req) |
|-------|-----------|---------------|
| baseline (60s) | ~1,100 | ~1,100 |
| storage_storm (150s) | ~8,100 | ~6,700 |
| cleanup_gap_1 (220s) | ~830 | ~850 |
| tier1_hotspot (150s) | ~10,200 | ~8,900 |
| cleanup_gap_2 (220s) | ~830 | ~850 |
| reverse_hotspot (150s) | ~13,500 | ~9,000 |
| cleanup_gap_3 (220s) | ~830 | ~850 |
| storage_storm_2 (150s) | ~8,100 | ~6,700 |
| demand_drop (300s) | ~5,000 | ~5,000 |
| **Total** | **~48,500** | **~40,000** |

Expected Push/P30 throughput gap: ~15-20% total, concentrated in the four
stress phases (storage_storm, tier1_hotspot, reverse_hotspot, storage_storm_2).
