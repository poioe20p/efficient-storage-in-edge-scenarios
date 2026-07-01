# Experiment Plan v4 — Bidirectional WAN Stress + Read/Write/Aggregation Load

**Status**: 📋 Planned — 2026-06-29
**Depends on**: [v3 experiment plan](experiment_plan_v3.md) and [v3 results](results_v3.md)
**Supersedes**: v3 — addresses asymmetric tier1 LAN load, invisible storage CPU, and WAN penalty diluted by connection-pool queuing

---

## Intent

v3 proved all three mechanisms are necessary, but left three gaps that v4 addresses:

1. **Tier 1 phases were directional → asymmetric**: `tier1_hotspot_n1` had 94% LAN1 traffic, `tier1_hotspot_n2` had 74% LAN2. The asymmetry came from phase ordering (n1 on stressed system, n2 on scaled-up system with 3× better cross-region latency). v4 makes tier1 phases **bidirectional** — both LANs send cross-region reads simultaneously, producing balanced per-LAN request counts and testing Tier 1 activation on both sides at once.

2. **WAN=100ms penalty dominated by connection-pool queuing, not RTT**: Cross-region reads at 4,709ms were 181× local, but 99% of that was maxPoolSize=1 queuing, not the 100ms RTT. At **WAN=500ms**, the RTT floor alone is 500ms per cross-region request — making the network component unambiguously visible. Tier 1 benefit becomes crystalline: 500ms (cross-region) vs ~10ms (cache hit).

3. **Storage CPU stayed at 0.5% — invisible**: 22 write/s with 100-byte oplog entries is negligible. v4 introduces a **combined read+write+aggregation phase** with larger document payloads and a new aggregation endpoint to generate real MongoDB CPU load.

---

## Changes from v3

| # | Change | Rationale |
|---|--------|-----------|
| 1 | **Bidirectional tier1** — remove `hotspot_direction` from both tier1 phases | Both LANs send cross-region simultaneously. Tier 1 activates on both sides. Per-LAN request counts balanced. |
| 2 | **WAN=500ms** (up from 100ms) | RTT floor of 500ms per cross-region request. Tier 1 benefit unambiguous (500ms vs ~10ms). Network penalty visible in individual request latency, not just aggregate queuing. |
| 3 | **Read+write+aggregation phase** (`storage_storm`) replaces `storage_hotspot` | High-rate device_status reads (cross-region) + device_update writes (with large payload) + device_aggregate (MongoDB aggregation pipeline). Combined read/write load stresses all replica-set members. |
| 4 | **DEVICES=6000** (up from 600) | Larger dataset makes aggregation pipelines non-trivial. More documents → larger indexes → more MongoDB RAM/CPU pressure. |
| 5 | **`device_aggregate` endpoint** | New POST endpoint on edge server that runs a MongoDB `$match`+`$group`+`$sort` aggregation pipeline. Read-only, uses VIP read path. Generates real MongoDB CPU work (full-collection scan + grouping). |
| 6 | **Larger write payload** — `device_update` body includes a 1KB `extra` field | Each write's oplog entry grows from ~100 bytes to ~1KB. At 120 write/s, oplog bandwidth increases from 12 KB/s to 120 KB/s — 10× the replication traffic on secondaries. |
| 7 | **Write concern `w:1`** (default, unchanged) | `w:2` would add negligible CPU at 58 write/s — the fastest secondary (same-LAN) responds in ~1ms regardless of WAN. Write concern is not the right lever for storage stress; aggregation + larger write payload are. |
| 8 | **VIP=30s** (kept from v3) | Confirmed superior to VIP=60 in Run L vs T. Not changed. |

---

## Phase Profile (v4)

| # | Phase | Dur | Rate | Cross | Clients | Mix (dev/dsh/svc/upd/agg) | Purpose |
|---|-------|-----|------|-------|---------|---------------------------|---------|
| 1 | `baseline` | 60s | 1 | 0% | 50% | 60/25/15/0/0 | Warmup |
| 2 | **`storage_storm`** | 240s | **4** | 90% | 100% | **35/10/5/30/20** | Combined read (device_status, cross-region) + write (device_update, large payload) + aggregation (device_aggregate) |
| 3 | **`tier1_hotspot`** | 180s | **5** | 95% | 100% | 80/5/5/5/5 | Bidirectional: LAN1 clients cross-region read from LAN2's MongoDB AND LAN2 clients cross-region read from LAN1's MongoDB — both directions simultaneously. Tests Tier 1 activation on both LANs at once. |
| 4 | `inter_hotspot_cooldown` | 300s | 1 | 0% | 10% | 60/25/15/0/0 | System drain |
| 5 | `compute_spike` | 180s | **4** | 5% | 100% | 20/65/15/0/0 | Dashboard-heavy fleet audit |
| 6 | `cooldown` | 120s | 1 | 0% | 10% | 60/25/15/0/0 | Return to normal |

**Total duration**: 60+240+180+300+180+120 = **1080s (18 min)**.

### Throughput Math (48 clients, WAN=500ms)

| Phase | Rate/client | Total req/s | Cross-region (effective) | Write req/s | Agg req/s |
|-------|------------|-------------|--------------------------|-------------|-----------|
| baseline | 1 × 50% | 24 | 0 | 0 | 0 |
| storage_storm | 4 × 100% | 192 | **60** (0.35×1.0×0.90=31.5%) | 58 | 38 |
| tier1_hotspot | 5 × 100% | 240 | **182** (0.80×1.0×0.95=76%, both directions simultaneously) | 12 | 12 |
| inter_hotspot_cooldown | 1 × 10% | ~5 | 0 | 0 | 0 |
| compute_spike | 4 × 100% | 192 | **2** (0.20×1.0×0.05=1%) | 0 | 0 |
| cooldown | 1 × 10% | ~5 | 0 | 0 | 0 |

Expected request count per run: **~108,000**.

---

## Run Matrix (v4)

| Run | Label | WAN | Mechanisms | Compares to | Answers |
|-----|-------|-----|-----------|-------------|---------|
| **A** | `mechanism_v4_all` | **500ms** | All on, VIP=30 | — (reference) | Storage CPU ≥5%? Tier 1 bidirectional? WAN penalty clear? |
| **B** | `mechanism_v4_notier1` | **500ms** | No Tier 1 | A | Consumer latency clearly degraded without Tier 1 at 500ms? |
| **C** | `mechanism_v4_nostorage` | **500ms** | No storage | A | Single-primary handles 58 write/s + aggregation? |
| **D** | `mechanism_v4_nocompute` | **500ms** | No compute | A | Single edge server handles 192 req/s? Gate as v3. |

**Gate for Run D**: Same as v3 — only if Run A's `compute_spike` adds ≥1 server AND edge CPU increase <2×.

---

## Code Changes (v3 → v4)

| File | Change | Purpose |
|------|--------|---------|
| `phases.json` | v4 phase profile: bidirectional tier1, storage_storm with aggregation mix, WAN-adjusted rates | v4 workload |
| `monitoring_workload_routes.py` | Add `POST /device_aggregate` endpoint | Aggregation pipeline on MongoDB |
| `traffic_generator.py` | Add `device_aggregate` request type | Test client sends aggregation requests |
| `vip_data_mongo_runtime.py` | **No changes needed** | Existing `run_with_request_lease(fn=lambda db: ...)` callback contract already supports aggregation — the `lambda` provides the `db` handle |
| `edge_server_config.py` | **No mandatory changes** | Aggregation pipeline threshold is passed per-request in the JSON body, not hardcoded in config |
| `mechanism_necessity_*.env` ×4 | No changes needed (VIP=30 already set, cooldowns already correct) | — |
| `device_update` body | Add 1KB `extra` payload field | Larger oplog entries for replication stress |
| Test data seed | Increase DEVICES from 600 to 6000 | Larger dataset for aggregation scans |

---

## Success Criteria

| # | Mechanism | Metric | Target | Phase |
|---|-----------|--------|--------|-------|
| 1 | Storage | Storage CPU on primary | **≥5%** | `storage_storm` |
| 2 | Storage | Storage CPU on secondaries | ≥1% (measurable oplog replication) | `storage_storm` |
| 3 | Storage | C vs A: per-node storage CPU | ≥2× | `storage_storm` |
| 4 | Tier 1 | Bidirectional activation | Tier 1 ACTIVE on both LANs simultaneously | `tier1_hotspot` |
| 5 | Tier 1 | Consumer LAN total latency (B vs A) | **≥5×** (500ms vs ~10ms cache hit) | `tier1_hotspot` |
| 6 | Tier 1 | Per-LAN balanced request count | ≤20% difference between LANs | `tier1_hotspot` |
| 7 | Compute | Scale-up triggers | ≥1 server added | `compute_spike` |
| 8 | Compute | D vs A: per-node edge CPU | ≥2× | `compute_spike` |
| 9 | WAN | Cross-region latency floor visible | Cross-region p25 ≥ 450ms (WAN RTT floor) | `storage_storm`, `tier1_hotspot` |
| 10 | Control-plane | 0 tracebacks | — | All phases |

---

## Launch Commands

```bash
# Run A — v4 combined reference (WAN=500ms, all mechs, VIP=30)
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_all.env \
  RUN_LABEL=mechanism_v4_all \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=500 \
  CLIENTS=48 DEVICES=6000 NODES=100

# Run B — v4 Tier 1 ablation
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_notier1.env \
  RUN_LABEL=mechanism_v4_notier1 \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=500 \
  CLIENTS=48 DEVICES=6000 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# Run C — v4 storage ablation
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_nostorage.env \
  RUN_LABEL=mechanism_v4_nostorage \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=500 \
  CLIENTS=48 DEVICES=6000 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# Run D — v4 compute ablation (gated)
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_nocompute.env \
  RUN_LABEL=mechanism_v4_nocompute \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=500 \
  CLIENTS=48 DEVICES=6000 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

Images to rebuild: `edge_server` (aggregation endpoint + large write payload).

---

## Validity Threats

- **WAN=500ms may saturate beyond recovery**: At 500ms RTT with maxPoolSize=1, a single connection handles ~2 req/s. With 91 cross-region req/s in `tier1_hotspot`, 45+ connections would be needed — impossible with maxPoolSize=1. The system WILL collapse without Tier 1. This is the intended effect, but Run A may show >50% failure rate. If so, reduce WAN to 300ms for subsequent runs.
- **DEVICES=6000 may slow test data seeding**: 10× more documents = 10× seeding time. First run will be slower.
- **Aggregation on 6000 documents may still be fast**: MongoDB can aggregate 6000 documents in <100ms. The aggregation CPU benefit may be marginal. If aggregation doesn't move MongoDB CPU, increase DEVICES further or add `$lookup` across collections.
- **Aggregation doesn't stress WAN**: `device_aggregate` always targets the client's own LAN (collection-level operation), so its 38 req/s in `storage_storm` contribute zero cross-region traffic. This is by design — aggregation is for MongoDB CPU stress, not WAN saturation. The cross-region load comes from `device_status` reads only.
- **Oplog amplification depends on extra field being stored**: The 1KB `extra` field must be persisted by the `device_update` route for the 10× oplog bandwidth increase to materialize. If the route doesn't store it, writes remain at ~100 bytes.
- **`time_db` false positive for storage scale-up**: Aggregation queries inherently take longer than simple point reads. With `SCALEUP_T_DB_FLOOR=60ms` and `SCALEUP_W_T_DB=0.40`, a 500ms aggregation query saturates the latency component to 1.0, contributing 0.40 to the degradation score — above the 0.10 threshold even with zero storage CPU. Storage may scale up due to query complexity rather than storage overload. Mitigated by: (a) the M-of-N sliding window requires 2/5 consecutive breaches, (b) the latency component is capped at 1.0 so a single extreme window cannot dominate, (c) in practice, maxPoolSize=1 queuing means time_db reflects genuine capacity pressure, not just query cost. Flagged for thesis discussion.

---

## Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-06-29 | Initial v4 plan. Bidirectional tier1, WAN=500ms, read+write+aggregation phase, DEVICES=6000, larger write payload. | Addresses v3 gaps: asymmetric LAN load, WAN penalty diluted by queuing, invisible storage CPU. |
| 2026-06-29 | Dropped `w:2` write concern — negligible CPU impact at 58 write/s. Added `time_db` false-positive validity threat note. Clarified bidirectional tier1 mechanics (both LANs cross-region simultaneously). | Write concern is not the right lever; aggregation + larger payload are. time_db false positive is real but bounded by M-of-N windowing + component saturation cap. |
| 2026-06-29 | Created [implementation_plan_v4.md](implementation_plan_v4.md) — file-by-file code change spec. | Ready for implementation agent. |
| 2026-06-29 | Executed all 4 runs at WAN=300ms (reduced from 500ms per validity threat). Tier 1 45× median latency benefit confirmed. Storage CPU 0.7% (missed ≥5% target). Compute marginal. Full analysis in [results_v4.md](results_v4.md). | WAN=500ms produced 51% failure rate; 300ms is the correct setting. Storage and compute are secondary to WAN bottleneck at maxPoolSize=1. |
