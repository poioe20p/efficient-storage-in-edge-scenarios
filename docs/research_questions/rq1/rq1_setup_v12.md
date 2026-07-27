# RQ1 v12 — Experiment Setup Declaration

> **Canonical reference** for how RQ1 v12 was tested. Values extracted from
> `experiment_plan_v12.md`, `phases.json`, `current_state_integrated.env`,
> `osken-controller.env`, and `scaling_config.py`.
> **Corresponding RQ doc**: [`rq1_v12.md`](rq1_v12.md)

---

## 1. Phases — `phases.json`

9 phases, 1920 s total (~32 min). **Cleanup gaps** (240 s, 5% load) between
high-load phases force all dynamic nodes to scale down, so each stress phase
starts from zero — isolating detection speed as the sole variable.

Identical to v8/v10's phase structure.

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

---

## 2. Resource Limits

| Parameter | v12 Value | v10 Value | Rationale |
|-----------|-----------|-----------|-----------|
| `CLIENTS` | 96 (48/LAN) | 96 | Same as v8/v10 |
| `MAX_DYNAMIC_COMPUTE` | 12 | 12 | Same as v8/v10 |
| `MAX_DYNAMIC_STORAGE` | 8 | 8 | Same as v8/v10 |
| `STORAGE_CPUS` | **0.05** | 0.08 | **−38% vs v10** — v11 calibration winner; storage cascade amplifier |
| `STORAGE_MEMORY` | 512m | 512m | Same as v8/v10 |
| `EDGE_CPUS` | **0.15** | 0.15 | Same as v10; Push handles this (≥94% success) |
| `EDGE_MEMORY` | 256m | 256m | Build script default |
| `CURL_MAX_TIME` | 30 s | 30 s | Same as v8/v10 |
| `--connect-timeout` | **5 s** | (absent) | **Added in v12** — catches TCP accept-queue failures during blind spot |
| `WAN_RTT_MS` | 185 ms | 185 ms | Same as v8/v10 |

### 2.1 Why STORAGE_CPUS = 0.05

At v10's `STORAGE_CPUS=0.08`, the storage tier had enough headroom that the
blind-spot penalty only produced a throughput gap (−14%) — timeout rates
converged because both modes eventually provisioned enough nodes. The gap
existed directionally but didn't cascade into user-visible timeout separation.

At 0.05 (−38% vs v10), each storage operation takes longer. Under stress-phase
load, the storage tier becomes the bottleneck FIRST — storage ops slow → edge
servers queue waiting for storage → the TCP accept queue fills → connections
fail. Push detects storage saturation and receives the telemetry within ~14 s
(window close + delivery + scoring) and provisions. Poll-30s may not detect
blind for 30s — during which the cascade propagates through the edge tier.

The v11 calibration confirmed this: S2 (STORAGE=0.05) produced a 5/6 gate
pass with massive p50 separation (4.7×), strong p95 gap (1.6×), and a 2.9×
timeout ratio (with `--connect-timeout 5`). At STORAGE=0.06 (S1), the cascade
was too weak — Poll-30s showed no degradation vs v10.

### 2.2 Why --connect-timeout 5

At `STORAGE_CPUS=0.05`, the edge server accept queue saturates during P30's
30s blind spot. Without `--connect-timeout`, these TCP-level failures were
absorbed by the OS TCP timeout (~20-30s) which overlapped with
`CURL_MAX_TIME=30`. Adding `--connect-timeout 5` catches connection failures
at 5s — 25s sooner — converting them into `http_status=0` events.

P30 sees more of these because its blind spot is 20s longer than Push's.
Without CT, the original S2 timeout ratio was 0.9× (inverted). With CT=5,
the ratio flipped to 2.9× (8.1% vs 2.8%).

This is a **permanent change** to `traffic_generator.py`. All v12 runs use it.

---

## 3. Controller Scoring — Compute Scale-Up

**Source**: `current_state_integrated.env` overrides. Identical to v8/v10.

| Parameter | v12 Value | Rationale |
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

Identical to v8/v10.

| Parameter | v12 Value | Rationale |
|-----------|----------|-----------|
| `SCALEUP_W_STORAGE_CPU` | 0 | CPU excluded — at tight limits, CPU is I/O-wait |
| `SCALEUP_W_T_DB` | 1.0 | Latency-only — T_db is the sole storage signal |
| `SCALEUP_STORAGE_BASE_THRESHOLD` | 0.35 | Storage latency trigger |
| `SCALEUP_STORAGE_WINDOW_SIZE` | 5 | 5 telemetry windows evaluated |
| `SCALEUP_STORAGE_REQUIRED` | 2 | 2 of 5 windows must breach |
| `SCALEUP_STORAGE_COOLDOWN_S` | 120 | Grace period after each storage spawn |

---

## 5. Controller Scoring — Scale-Down

Identical to v8/v10.

| Parameter | v12 Value | Rationale |
|-----------|----------|-----------|
| `SCALEDOWN_COMPUTE_COOLDOWN_S` | 180 | < cleanup gap (240s) — ensures G8 |
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
| Connect timeout | `--connect-timeout 5` **(added in v12)** |
| Rate pacing | `interval = 1.0 / phase.rate_per_client` with jitter |
| HTTP method | GET (POST for content_update/aggregate with body) |

## 11. Data Seeding

`setup_test_data` pre-populates each LAN's MongoDB with 6,000 content items
(12,000 total across LANs). `DATA_SEED=42` ensures deterministic generation.
`RANDOM_SEED=42` controls client request randomization.

## 12. Expected Delivered Requests (per run)

Based on v11 S2+CT5 pilot, per-phase expected throughput:

| Phase | Push (req) | Poll-30s (req) |
|-------|-----------|---------------|
| baseline (60s) | ~1,100 | ~1,100 |
| storage_storm (240s) | ~13,000 | ~11,000 |
| cleanup_gap_1 (240s) | ~850 | ~900 |
| tier1_hotspot (180s) | ~11,500 | ~9,500 |
| inter_hotspot_cooldown (300s) | ~5,000 | ~5,200 |
| reverse_hotspot (180s) | ~15,000 | ~11,500 |
| cleanup_gap_2 (240s) | ~900 | ~900 |
| compute_spike (180s) | ~21,500 | ~17,000 |
| demand_drop (300s) | ~5,000 | ~5,000 |
| **Total** | **~85,000** | **~60,000** |
