# Experiment Plan v3 — Write Amplification + Load Scaling

**Status**: 📋 Planned — 2026-06-28
**Depends on**: [v2 experiment plan](experiment_plan_v2.md) and [v2 results](results_v2.md)
**Supersedes**: v2 — addresses the Tier 1 paradox (J healthier than I), insufficient storage CPU signal (<2%), and inter-hotspot cooldown asymmetry discovered in v2.

**v2 baseline run references** (for context — v3 comparisons are to Run L, not these):

- Run E (all on, WAN=50, v1 phases): `20260628_012320_mechanism_wan50` — WAN isolation proved 6.9× latency increase
- Run H (no storage, WAN=10, v2 phases): `20260628_023832_mechanism_storageheavy_nostorage` — best v2 performer (p95=242ms)
- Run J (no Tier 1, WAN=50, v2 phases): `20260628_092247_mechanism_v2_notier1` — Tier 1 OFF healthier than ON (paradox)

---

## Intent

v2 discovered two problems that v3 addresses:

1. **Tier 1 paradox**: At WAN=50 + dashboard mix, Tier 1 OFF (Run J) outperformed Tier 1 ON (Run I). Root cause: 60s `inter_hotspot_cooldown` was insufficient for Tier 1 container drain + MongoDB replica-set stabilization between hotspot directions. Tier 1 containers from the first direction hadn't drained when the reverse direction started.

2. **Storage CPU invisible**: MongoDB container CPU stayed at 1–2% even with 60% dashboard queries. Root cause: (a) all reads go to the PRIMARY via VIP — secondaries serve zero read traffic; (b) no write workload → no oplog replication traffic on secondaries. A single MongoDB at 1% CPU is not a bottleneck.

v3 introduces three independent changes:

1. **Write endpoint** (`POST /device_update`): A new endpoint on the edge server that writes directly to the MongoDB primary (bypassing the VIP-based read path). Writes generate oplog traffic that ALL replica-set members (including dynamic secondaries) must replicate — making storage CPU on secondaries measurable.

2. **Extended inter-hotspot cooldown** (60s → 300s at 1 req/s with 10% active clients): Gives the system 5 minutes to drain Tier 1 containers and stabilize replica sets between hotspot directions, eliminating the asymmetry observed in v2.

3. **Client count increase** (8 → 48): More clients at moderate per-client rates distributes load across all edge servers, engages more Tier 1 caches, and pushes total throughput toward the Flask ceiling where compute scale-up becomes visibly necessary.

---

## Hypothesis / Expected Outcome

1. **Storage scale-up (with writes)**: `storage_hotspot` with 15% `device_update` writes will show storage CPU ≥3% on the primary and measurable CPU increase on secondaries (oplog replication). Without storage reserve (1 node = primary only), the primary handles writes + all reads + oplog, producing higher per-node CPU than the distributed case.

2. **Tier 1 (with extended cooldown)**: The 300s cooldown eliminates the directional asymmetry. Both `tier1_hotspot_n1` and `tier1_hotspot_n2` should show comparable behavior. Tier 1 ON should reduce consumer-LAN `avg_time_db` vs Tier 1 OFF, and the owner-LAN MongoDB should be protected from cross-region read storms.

3. **Compute scale-up (with 48 clients)**: At 48 clients × 3–5 req/s in hotspot phases (144–240 req/s total), compute scale-up will trigger visibly. Without compute scale-up, edge server CPU should spike and failures increase.

---

## Independent Variables

| Variable | v2 value | v3 value | Rationale |
|----------|---------|---------|-----------|
| Write workload | None | `device_update` 15% in `storage_hotspot` | Oplog traffic stresses all replica-set members |
| `inter_hotspot_cooldown` duration | 60s | **300s** | Tier 1 drain + replica-set stabilization |
| `inter_hotspot_cooldown` client_fraction | 0.5 | **0.10** | ~5 active clients → scale-down arms within 45s |
| Client count | 8 | **48** | Load distribution across edge servers; higher total throughput |
| WAN RTT | 50ms | **100ms** | Doubles Tier 1 signal (100ms saved per cached cross-region read vs 50ms). At WAN=50 the network saving was only ~50ms of a ~70–250ms request; at WAN=100ms the saving is 100ms, making the Tier 1 effect unambiguous in total request latency. |

**Held constant**: all mechanism toggles, thresholds, cooldowns, host, code base (except the write endpoint), device count (600), node count (100).

---

## Code Changes (v2 → v3)

| File | Change | Purpose |
|------|--------|---------|
| `edge_server_config.py` | Added `mongo_primary_lan1`, `mongo_primary_lan2` fields | Primary IP passed as env var from controller |
| `vip_data_mongo_runtime.py` | Added `_write_clients` dict + `_get_write_client(lan)` | Direct-to-primary MongoClient for writes |
| `monitoring_workload_routes.py` | Added `POST /device_update` route | Write endpoint that updates device pressure via primary |
| `compute_node_manager.py` | Pass `EDGE_MONGO_PRIMARY_LAN1`/`_LAN2` on spawn | Controller tells edge server primary IP at startup |
| `traffic_generator.py` | Added `device_update` request type + POST body support | Test client sends write requests |
| `phases.json` | Updated rates, cooldown, mix | v3 workload profile |

---

## v3 Phase Profile

| # | Phase | Dur | Rate | Cross | Clients | Mix (dev/dsh/svc/upd) | Purpose |
|---|-------|-----|------|-------|---------|------------------------|---------|
| 1 | `baseline` | 60s | 1 | 0% | 50% | 60/25/15/0 | Normal operations — warmup |
| 2 | **`storage_hotspot`** | 240s | **3** | 90% | 100% | **25/50/10/15** | Regional incident — cross-region reads + writes |
| 3 | `tier1_hotspot_n1` | 180s | **5** | 95% | 100% | 95/3/2/0 | Hot device focus (lan2→lan1) |
| 4 | **`inter_hotspot_cooldown`** | **300s** | **1** | 0% | **10%** | 60/25/15/0 | Incident resolved — system drain |
| 5 | `tier1_hotspot_n2` | 180s | **5** | 95% | 100% | 95/3/2/0 | Hot device focus (lan1→lan2) |
| 6 | `compute_spike` | 180s | **4** | 5% | 100% | 20/65/15/0 | Fleet audit — dashboard-heavy |
| 7 | `cooldown` | 120s | 1 | 0% | **10%** | 60/25/15/0 | Return to normal — drain |

**Throughput math** (48 clients at 100% fraction, unless noted, 7 phases):

| Phase | Rate/client | Total req/s | Cross-region | Write req/s |
|-------|------------|-------------|-------------|-------------|
| storage_hotspot | 3 | 144 | 130 | 22 |
| tier1_hotspot_n1 | 5 | 240 | 228 | 0 |
| inter_hotspot_cooldown | 1 × 10% | ~5 | 0 | 0 |
| tier1_hotspot_n2 | 5 | 240 | 228 | 0 |
| compute_spike | 4 | 192 | 10 | 0 |

---

## Run Matrix (v3)

Lean 4-run matrix. Runs O–R from the initial draft are dropped — v2 already proved
WAN isolation (E vs A), pure single-variable ablations at WAN=10 (G vs H),
and that storage doesn’t matter without writes. The v3 phase profile (writes + 300s
cooldown + 48 clients) is the new baseline used by all runs.

| Run | Label | WAN | Mechanisms | Compares to | Answers |
|-----|-------|-----|-----------|-------------|---------|
| **L** | `mechanism_v3_all` | **100ms** | All on | — (v3 reference) | Compute triggers? Tier 1 symmetric n1↔n2? Storage CPU ≥3% with writes? |
| **M** | `mechanism_v3_notier1` | **100ms** | No Tier 1 | L | Does Tier 1 improve consumer latency at WAN=100ms + 300s cooldown? Did the v2 J-vs-I paradox resolve? |
| **N** | `mechanism_v3_nostorage` | **100ms** | No storage | L | Does single-primary handle writes + reads at 48-client scale? Is per-node storage CPU ≥2× L? |
| **S** | `mechanism_v3_nocompute` | **100ms** | No compute | L | Reconfirm compute necessity at 48-client scale (optional — run only if v2’s 5.4× latency proof is considered insufficient at higher load). |

Run order: **L → M → N** [→ S if needed]. L first — if the v3 reference does not exercise all three mechanisms, diagnose before proceeding (see Mechanism Exercise Gate below).

---

## Launch Command

```bash
# Run L — v3 combined reference
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_all.env \
  RUN_LABEL=mechanism_v3_all \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=100 \
  CLIENTS=48 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# Run M — v3 Tier 1 ablation
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_notier1.env \
  RUN_LABEL=mechanism_v3_notier1 \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=100 \
  CLIENTS=48 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# Run N — v3 storage ablation
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_nostorage.env \
  RUN_LABEL=mechanism_v3_nostorage \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=100 \
  CLIENTS=48 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# Run S — v3 compute ablation (optional)
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_nocompute.env \
  RUN_LABEL=mechanism_v3_nocompute \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=100 \
  CLIENTS=48 DEVICES=600 NODES=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

Images must be rebuilt before first run: `make -C source/scripts build_images`

---

## Write Endpoint Architecture

```
POST /device_update
    │
    ▼
Edge Server (_get_write_client)
    │
    │  directConnection=True
    │  URI = mongodb://<primary_ip>:27018/
    │  (bypasses VIP, no OVS flow rule)
    ▼
PRIMARY MongoDB (edge_storage_server_n1/n2)
    │
    │  oplog entry generated
    ▼
ALL SECONDARIES (dyn1, dyn2, ...)
    └── pull oplog, apply entry → CPU work
```

The primary IP is fixed (`10.0.0.4` for LAN1, `10.0.1.4` for LAN2) and passed as environment variable when the controller spawns edge-server containers.

---

## Success Criteria

| Mechanism | Metric | Target | Phase |
|-----------|--------|--------|-------|
| Storage | Storage CPU on primary | ≥3% | `storage_hotspot` |
| Storage | Storage CPU on secondaries | ≥1% (oplog work) | `storage_hotspot` |
| Storage | N vs L: per-node storage CPU | ≥2× | `storage_hotspot` |
| Tier 1 | Symmetry n1 vs n2 | ≤20% difference | Both Tier 1 phases |
| Tier 1 | Consumer-LAN avg_time_db (M vs L) | ≥3× | `tier1_hotspot_n1`, `n2` |
| Tier 1 | Consumer-LAN total latency (M vs L) | ≥1.5× | `tier1_hotspot_n1`, `n2` |
| Compute | scale-up triggers | ≥1 server added | `compute_spike` |
| Control-plane | Tracebacks, epoch rotations | 0 | All phases |

---

## Mechanism Exercise Gate (Run L)

Same as v2 Run A / Run I: all three mechanisms must exercise in the reference run.
If any mechanism fails to activate, diagnose before proceeding to M/N/S.

| Mechanism missing | Check | Likely cause | Fix |
|-------------------|-------|-------------|-----|
| Compute: no `server_count > 1` in `compute_spike` | Controller logs for `[scale-up] compute` | Threshold too high at 48-client scale | Lower `SCALEUP_COMPUTE_BASE_THRESHOLD`; re-run L only |
| Storage: no `[reserve] activated` | Controller logs for `[scale-up] storage triggered` | Writes may change degradation score profile | Lower `SCALEUP_STORAGE_BASE_THRESHOLD` from 0.10 → 0.08; re-run L only |
| Tier 1: no `SelectiveSyncAlert` | Controller logs for `SelectiveSync`; `coord_hot_doc_total` | Hot set not concentrated enough at 48 clients | Verify `cross_region_ratio` in tier1 phases is 0.95 |

---

## Checkpoints

| Trigger | Question | Evidence |
|---------|----------|----------|
| End of `baseline` | Storage reserve `READY_RESERVED` on both LANs? | Controller logs |
| Mid `storage_hotspot` (~180s) | `[reserve] activated`? Compute scaled up? Storage CPU elevated? | Controller logs, `resource_stats.csv` |
| Mid `tier1_hotspot_n1` (~540s) | Tier 1 `ACTIVE`? Consumer latency at WAN=100ms? | Controller logs, `client_requests.csv` |
| Mid `tier1_hotspot_n2` (~1020s) | Tier 1 `ACTIVE` for reverse? Symmetry with n1? | Controller logs |
| Mid `compute_spike` (~1200s) | Compute elasticity added servers? | `resource_stats.csv` |
| End of `cooldown` | Clean drain? | `container_events.csv` |

---

## Validity Threats & Limitations

- **WAN=100ms may saturate connection pools**: With `maxPoolSize=1` per VIP connection and 100ms RTT, a single connection handles ~10 req/s max. At 240 cross-region req/s, requests will queue if Tier 1 doesn't absorb them. This is the intended mechanism effect, but it means throughput (not just latency) becomes the primary metric.
- **48 clients may overwhelm the test host**: 48 network namespaces × curl processes = higher host CPU. Monitor host load during runs; reduce `rate_per_client` if the host becomes the bottleneck.
- **Single replicate**: each condition runs once. The v2 baselines provide comparison context but use different WAN/phases.
- **Write endpoint is new**: The `POST /device_update` path has not been tested in a full experiment. Verify writes succeed in `baseline` before relying on `storage_hotspot` storage CPU measurements.
- **`mechanism_necessity_nocompute.env`**: Exists from v1 but was not used in v2. Verify `MAX_DYNAMIC_COMPUTE=0` is the only change from the all.env baseline.

---

## Artifact Contract

Same as v2. Each run folder under `source/scripts/testing/metrics/<timestamp>_mechanism_v3_<label>/` must contain:

- `client_requests.csv`, `resource_stats.csv`, `resource_stats_debug.csv`
- `per_node_stats.csv`, `container_events.csv`
- `controller_lan1.log`, `controller_lan2.log`
- `elasticity_events.csv`, `node_lifecycle_timings.csv`, `policy_state.csv`
- `phases_snapshot.json`, `controller_env_snapshot.env`
- `service_logs/` directory

Expected later analysis outputs: per-run `cli_simple_run` summaries, cross-run `cli_mechanism_compare` (L vs M vs N), and `results_v3.md`.

---

## Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-06-28 | Initial v3 plan. Added write endpoint, extended cooldown, 48 clients. | Addresses v2 findings: Tier 1 paradox (cooldown too short), storage CPU invisible (no writes → no oplog), edge server load below ceiling (too few clients). |
| 2026-06-28 | WAN_RTT_MS 50→100. Lean 4-run matrix replacing 7-run structure. | 100ms doubles Tier 1 signal. Runs O–R dropped — v2 already proved WAN isolation, storage at WAN=10, and pure single-variable ablations. |
