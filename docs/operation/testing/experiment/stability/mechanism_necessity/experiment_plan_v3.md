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

1. **Tier 1 paradox**: At WAN=50 + dashboard mix, Tier 1 OFF (Run J) outperformed Tier 1 ON (Run I). Root cause (confirmed by controller-log analysis): Tier 1 **detection latency**, not cooldown timing. The cross-region read storm saturates the owner LAN's ``maxPoolSize=1`` MongoDB connection before the controller detects enough hot documents to trigger Tier 1. The ``sel_sync`` cache activates *after* the owner LAN has already degraded. The 300s inter-hotspot cooldown (between directions) addresses a different issue — directional drain between n1 and n2. The detection-latency problem is addressed by **(a)** higher cross-region throughput (84–108 req/s vs v2's ~30) so hot documents surface faster, **(b)** ``VIP_HARD_TIMEOUT=30`` so flows re-select onto Tier 1 caches sooner after activation, and **(c)** ``SCALEUP_COMPUTE_COOLDOWN_S=20`` so compute servers arrive before thread exhaustion.

2. **Storage CPU invisible**: MongoDB container CPU stayed at 1–2% even with 60% dashboard queries. Root cause: (a) ``cross_region_ratio`` in ``phases.json`` produced only 11% effective cross-region (not the expected 90%) because only ``device_status`` requests can cross regions and the mix allocated only 25% to that type; (b) no write workload → no oplog replication traffic on secondaries. A single MongoDB at 1% CPU is not a bottleneck.

v3 introduces these changes (original + investigation-driven):

1. **Write endpoint** (`POST /device_update`): A new endpoint on the edge server that writes directly to the MongoDB primary (bypassing the VIP-based read path). Writes generate oplog traffic that ALL replica-set members (including dynamic secondaries) must replicate — making storage CPU on secondaries measurable.

2. **Extended inter-hotspot cooldown** (60s → 300s at 1 req/s with 10% active clients): Gives the system 5 minutes to drain Tier 1 containers and stabilize replica sets between hotspot directions.

3. **Client count increase** (8 → 48): More clients at moderate per-client rates distributes load across all edge servers, engages more Tier 1 caches, and pushes total throughput toward the Flask ceiling where compute scale-up becomes visibly necessary.

4. **cross_region_ratio fix**: ``storage_hotspot`` mix changed from 25/50/10/15 to 65/10/10/15 (prioritizing ``device_status``, the only cross-region-capable type). Removed ``hotspot_direction`` so both LANs send cross-region reads. Effective cross-region: 11% → 58% (84 req/s).

5. **VIP_HARD_TIMEOUT=30** (down from 120s): OVS flow rules force backend re-selection every 30s instead of every 120s. Faster adaptation when new servers join the pool, Tier 1 caches become active, or backends become unhealthy. Also makes failure visibility more granular in ``client_requests.csv``.

6. **SCALEUP_COMPUTE_COOLDOWN_S=20** (down from 45s): Servers arrive 2.25× faster under load, preventing the thread-exhaustion cascade observed in the pre-v3 diagnostic run.

7. **SCALEUP_STORAGE_COOLDOWN_S=60** (down from 120s): Faster storage response under load.

8. **Write client double-checked locking**: Fixes TOCTOU race in ``_get_write_client`` lazy initialization.

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
| `inter_hotspot_cooldown` client_fraction | 0.5 | **0.10** | ~5 active clients at 1 req/s → all telemetry windows should be below
scale-down thresholds.  Scale-down requires 7 hits in a 12-window sliding
window at 10s telemetry intervals → **~70s minimum** to arm (not 45s as
stated in earlier plan drafts).  The 300s cooldown phase provides ample
margin (70s ≪ 300s). |
| Client count | 8 | **48** | Load distribution across edge servers; higher total throughput |
| WAN RTT | 50ms | **100ms** | Doubles Tier 1 signal (100ms saved per cached cross-region read vs 50ms). At WAN=50 the network saving was only ~50ms of a ~70–250ms request; at WAN=100ms the saving is 100ms, making the Tier 1 effect unambiguous in total request latency. |
| VIP hard timeout | 120s | **30s** | Flow rules force backend re-selection 4× faster. New servers, Tier 1 caches, and hung-backend avoidance all take effect within 30s instead of 120s. If PacketIn rate is too high, revert to 60s. |
| Compute scale-up cooldown | 45s | **20s** | Servers arrive 2.25× faster under load, preventing the thread-exhaustion cascade observed in the pre-v3 diagnostic run. |
| Storage scale-up cooldown | 120s | **60s** | Faster storage response under load. |

**Held constant**: all mechanism toggles, host, code base (except the write endpoint + lock fix), device count (600), node count (100).

---

## Code Changes (v2 → v3)

| File | Change | Purpose |
|------|--------|---------|
| `edge_server_config.py` | Added `mongo_primary_lan1`, `mongo_primary_lan2` fields | Primary IP passed as env var from controller |
| ``vip_data_mongo_runtime.py`` | Added ``_write_clients`` dict + ``_get_write_client(lan)`` with double-checked locking | Direct-to-primary MongoClient for writes, thread-safe lazy init |
| `monitoring_workload_routes.py` | Added `POST /device_update` route | Write endpoint that updates device pressure via primary |
| `compute_node_manager.py` | Pass `EDGE_MONGO_PRIMARY_LAN1`/`_LAN2` on spawn | Controller tells edge server primary IP at startup |
| `traffic_generator.py` | Added `device_update` request type + POST body support | Test client sends write requests |
| `phases.json` | Updated rates, cooldown, mix; ``storage_hotspot``: removed ``hotspot_direction``, mix 25/50/10/15→65/10/10/15 | v3 workload profile with corrected cross-region throughput |
| `mechanism_necessity_*.env` ×4 | ``SCALEUP_COMPUTE_COOLDOWN_S=20``, ``SCALEUP_STORAGE_COOLDOWN_S=60``, ``VIP_HARD_TIMEOUT=30`` | Faster scale-up response, faster flow adaptation |

---

## v3 Phase Profile

| # | Phase | Dur | Rate | Cross | Clients | Mix (dev/dsh/svc/upd) | Purpose |
|---|-------|-----|------|-------|---------|------------------------|---------|
| 1 | `baseline` | 60s | 1 | 0% | 50% | 60/25/15/0 | Normal operations — warmup |
| 2 | **`storage_hotspot`** | 240s | **3** | 90% | 100% | **65/10/10/15** | Regional incident — cross-region reads + writes (bidirectional, no hotspot_direction) |
| 3 | `tier1_hotspot_n1` | 180s | **5** | 95% | 100% | 95/3/2/0 | Hot device focus (lan2→lan1) |
| 4 | **`inter_hotspot_cooldown`** | **300s** | **1** | 0% | **10%** | 60/25/15/0 | Incident resolved — system drain |
| 5 | `tier1_hotspot_n2` | 180s | **5** | 95% | 100% | 95/3/2/0 | Hot device focus (lan1→lan2) |
| 6 | `compute_spike` | 180s | **4** | 5% | 100% | 20/65/15/0 | Fleet audit — dashboard-heavy |
| 7 | `cooldown` | 120s | 1 | 0% | **10%** | 60/25/15/0 | Return to normal — drain |

### How `cross_region_ratio` actually works

Only `device_status` requests can cross regions — `dashboard`, `service_pressure`, and
`device_update` are architecturally local (dashboard queries local node data,
service_pressure is a local endpoint, writes target the local primary).

When a `hotspot_direction` is set to a directional value (e.g. `lan2_to_lan1`),
clients on the **destination** LAN are blocked from sending cross-region
requests — they always stay local. This creates the directional hot-device
concentration needed for Tier 1 testing. When `hotspot_direction` is set to
the empty string ``""`` (as in `storage_hotspot`), neither direction matches
and clients on **both** LANs can send cross-region requests.

**Important**: If the `hotspot_direction` key is absent from the phase config,
the traffic generator defaults to ``"lan2_to_lan1"`` (see
``PhaseConfig.from_dict`` in ``traffic_generator.py:89``). The empty string
must be set **explicitly** to get bidirectional behaviour.

The **effective cross-region rate** for a phase is:

```
effective = device_status_mix × eligible_client_fraction × cross_region_ratio

Where eligible_client_fraction = 1.0 (no hotspot_direction) or 0.5 (directional).
```

**Throughput math** (48 clients at 100% fraction, unless noted):

| Phase | Rate/client | Total req/s | Cross-region (effective) | Write req/s |
|-------|------------|-------------|--------------------------|-------------|
| storage_hotspot | 3 | 144 | **84** (0.65×1.0×0.90=58%) | 22 |
| tier1_hotspot_n1 | 5 | 240 | **108** (0.95×0.5×0.95=45%) | 0 |
| inter_hotspot_cooldown | 1 × 10% | ~5 | 0 | 0 |
| tier1_hotspot_n2 | 5 | 240 | **108** (0.95×0.5×0.95=45%) | 0 |
| compute_spike | 4 | 192 | **2** (0.20×1.0×0.05=1.0%) | 0 |

**Total experiment duration**: 60+240+180+300+180+180+120 = **1260s (21 min)**.

Expected request count per run (48 clients × Σ(phase_duration × rate × client_fraction), zero failures): **~159,000**.

### Phase boundary timeline

| Phase | Start | End | Mid |
|-------|-------|-----|-----|
| baseline | 0s | 60s | — |
| storage_hotspot | 60s | 300s | **180s** |
| tier1_hotspot_n1 | 300s | 480s | **390s** |
| inter_hotspot_cooldown | 480s | 780s | — |
| tier1_hotspot_n2 | 780s | 960s | **870s** |
| compute_spike | 960s | 1140s | **1050s** |
| cooldown | 1140s | 1260s | — |

---

## Focus & Evidence

**Primary focus**: Controller logs + latency files. The experiment's core question
is whether mechanisms activate and improve outcomes under load. Controller logs
show *when* and *why* (scale-up triggers, Tier 1 alerts, VIP rule changes).
``client_requests.csv`` shows *effect* (latency, failure rate per phase/per LAN).

**Secondary focus**: Resource files (``resource_stats.csv``, ``per_node_stats.csv``)
quantify the *magnitude* of mechanism effects — storage CPU increase, per-node
load balance, ``server_count``/``storage_count`` evolution.

**Tertiary**: Container lifecycle (``container_events.csv``) confirms spawn/stop
timing; ``elasticity_events.csv`` provides structured event trace for debugging.

### Per-artifact evidence map

| Artifact | Shows | Primary for |
|----------|-------|-------------|
| ``client_requests.csv`` | Per-phase/LAN p95/p99 latency, failure rate, request mix | Tier 1 effect (consumer latency), compute necessity (failure rate under load) |
| ``controller_lan1.log``, ``controller_lan2.log`` | Scale decisions, Tier 1 alerts, VIP rule changes, errors | All mechanisms — activation timing and correctness |
| ``resource_stats.csv`` | ``server_count``, ``storage_count``, ``avg_storage_cpu_percent``, ``avg_time_db_ms``, ``tier1_lifecycle_active_count`` | Storage CPU, Tier 1 active count, compute server count |
| ``per_node_stats.csv`` | Per-container CPU/RAM breakdown | Storage CPU per node (primary vs secondary), compute load balance |
| ``elasticity_events.csv`` | Structured scale-up/down events, node lifecycle timings | Mechanism exercise verification |
| ``container_events.csv`` | Spawn/stop/state-change events with timestamps | Tier 1 container lifecycle, compute server churn |
| ``policy_state.csv`` | Reconstructed per-window policy decisions | Cross-referencing controller decisions with outcomes |

---

## Run Matrix (v3)

Lean 5-run matrix. Runs O–R from the initial draft are dropped — v2 already proved
WAN isolation (E vs A), pure single-variable ablations at WAN=10 (G vs H),
and that storage doesn’t matter without writes. The v3 phase profile (writes + 300s
cooldown + 48 clients) is the new baseline used by all runs.

| Run | Label | WAN | Mechanisms | Env File | Compares to | Answers |
|-----|-------|-----|-----------|----------|-------------|---------|
| **L** | `mechanism_v3_all` | **100ms** | All on, VIP=30 | `mechanism_necessity_all.env` | — (reference) | Compute triggers? Tier 1 symmetric? Storage CPU >=3%? |
| **T** | `mechanism_v3_all_vip60` | **100ms** | All on, VIP=60 | `mechanism_necessity_all_vip60.env` | L | Is VIP=30 better than VIP=60? |
| **M** | `mechanism_v3_notier1` | **100ms** | No Tier 1 | `mechanism_necessity_notier1.env` | L | Does Tier 1 reduce consumer latency? |
| **N** | `mechanism_v3_nostorage` | **100ms** | No storage | `mechanism_necessity_nostorage.env` | L | Does single-primary handle writes + reads? |
| **S** | `mechanism_v3_nocompute` | **100ms** | No compute | `mechanism_necessity_nocompute.env` | L | Reconfirm compute necessity (gated) |

Run order: **L → T → M → N** [→ S if gated]. L and T back-to-back
minimises host-state drift for the VIP timeout comparison.

### Mechanism Toggles

| Run | MAX_DYNAMIC_COMPUTE | STORAGE_PERSISTENT_RESERVE_ENABLED | SS_ENABLED | MAX_DYNAMIC_STORAGE | VIP_HARD_TIMEOUT |
|-----|----------------------|-----------------------------------|-----------|----------------------|------------------|
| **L** | 6 | 1 | 1 | 5 | **30** |
| **T** | 6 | 1 | 1 | 5 | **60** |
| **M** | 6 | 1 | **0** | 5 | 30 |
| **N** | 6 | **0** | 1 | **0** | 30 |
| **S** | **0** | 1 | 1 | 5 | 30 |

**Run S gate**: Run S only if BOTH conditions are true after Run L:
1. Run L's `compute_spike` phase added ≥1 edge server (compute scale-up triggered), AND
2. Run L's `compute_spike` per-node edge CPU increase vs `baseline` is <2×.

If condition 1 is false (compute never triggered), the threshold is too high
and S would be a tautology. If condition 2 is false (CPU already ≥2× without
compute scale-up), then compute necessity is already proven and S adds nothing.
S is only useful when compute scale-up *did* trigger but its *benefit* is
marginal — the ablation run proves whether the benefit is real.

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

# Run T — v3 VIP timeout comparison (VIP_HARD_TIMEOUT=60)
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_all_vip60.env \
  RUN_LABEL=mechanism_v3_all_vip60 \
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

Images must be rebuilt before first run (``edge_server`` image only — the write
endpoint and lock fix are the only container-side changes):
``sudo bash source/scripts/build_images.sh edge_server``

**WAN verification**: After ``setup_network``, verify WAN emulation is active:
``docker exec nat-router tc qdisc show dev eth1`` should show a latency qdisc
with delay matching half of ``WAN_RTT_MS`` (50ms at WAN=100ms).

**First-run vs re-run**: The commands below include ``SKIP_CLIENTS=1 SKIP_SEED=1
SKIP_SNAPSHOT=1`` — these are for re-runs where clients, data, and snapshots
already exist from a previous run. For a **first run** on a fresh network,
omit all three skip flags (clients, seeding, and snapshot export will run).

**v2→v3 comparability**: v3 changes 8 variables simultaneously from v2 (WAN RTT,
client count, write workload, 3 cooldowns, VIP timeout, cross_region_ratio mix).
v3 is a **new baseline** — its results are NOT directly comparable to v2 results.
Within-v3 comparisons (M vs L, N vs L, S vs L) isolate single mechanism
differences under the v3 baseline.

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
| Storage | Storage CPU on secondaries | Any measurable increase vs baseline (oplog work). Note: below controller's ``SCALEUP_STORAGE_CPU_FLOOR=1.5`` — measurement-only, does not gate mechanism decisions. | `storage_hotspot` |
| Storage | N vs L: per-node storage CPU | ≥2× | `storage_hotspot` |
| Tier 1 | Symmetry n1 vs n2 | ≤20% difference | Both Tier 1 phases |
| Tier 1 | Consumer-LAN avg_time_db (M vs L) | ≥3× | `tier1_hotspot_n1`, `n2` |
| Tier 1 | Consumer-LAN total latency (M vs L) | ≥1.5× | `tier1_hotspot_n1`, `n2` |
| Compute | scale-up triggers | ≥1 server added | `compute_spike` |
| Compute | S vs L: per-node edge CPU | ≥2× (if S run) | `compute_spike` |
| VIP timeout | L vs T: overall failure rate, latency p95 | L ≤ T (30s does not harm) | All phases |
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

### Abort Criterion — WAN=100ms Overshoot

WAN=100ms with 48 clients at 84–108 cross-region req/s may saturate the
``maxPoolSize=1`` connection beyond what the mitigations (VIP_HARD_TIMEOUT=30,
SCALEUP_COMPUTE_COOLDOWN_S=20) can handle. If Run L shows **any** of the
following, abort, reduce WAN to 50ms, and re-run:

- Overall failure rate >50%
- Total requests significantly below the expected ~159,000 (phase math:
  48 clients × Σ(phase_duration × rate × client_fraction)). A threshold
  of <40,000 (~25% of capacity) indicates systemic collapse.
- Any single-LAN complete outage lasting >1 phase (same symptom as v2 Runs I/K)

WAN=50ms is the fallback — v2 proved it amplifies cross-region latency 3.7×,
which is sufficient to show Tier 1 and storage effects.

---

## Checkpoints

| Trigger | Question | Evidence |
|---------|----------|----------|
| End of `baseline` (60s) | Storage reserve `READY_RESERVED` on both LANs? | Controller logs |
| Mid `storage_hotspot` (**~180s**) | `[reserve] activated`? Compute scaled up? Storage CPU elevated? | Controller logs, `resource_stats.csv` |
| Mid `tier1_hotspot_n1` (**~390s**) | Tier 1 `ACTIVE`? Consumer latency at WAN=100ms? | Controller logs, `client_requests.csv` |
| Mid `tier1_hotspot_n2` (**~870s**) | Tier 1 `ACTIVE` for reverse? Symmetry with n1? | Controller logs |
| Mid `compute_spike` (**~1050s**) | Compute elasticity added servers? | `resource_stats.csv` |
| End of `cooldown` (1260s) | Clean drain? | `container_events.csv` |

---

## Validity Threats & Limitations

- **WAN=100ms may saturate connection pools**: With `maxPoolSize=1` per VIP connection and 100ms RTT, a single connection handles ~10 req/s max. At 240 cross-region req/s, requests will queue if Tier 1 doesn't absorb them. This is the intended mechanism effect, but it means throughput (not just latency) becomes the primary metric.
- **48 clients may overwhelm the test host**: 48 network namespaces × curl processes = higher host CPU. Monitor host load during runs; reduce `rate_per_client` if the host becomes the bottleneck.
- **Single replicate**: each condition runs once. The v2 baselines provide comparison context but use different WAN/phases.
- **Write endpoint is new**: The ``POST /device_update`` path has not been tested in a full experiment. Verify writes succeed in ``baseline`` before relying on ``storage_hotspot`` storage CPU measurements. At 22 write req/s, oplog bandwidth is ~11 KB/s — secondary CPU increase may be <0.5% (below the controller's ``SCALEUP_STORAGE_CPU_FLOOR=1.5``, so this is a measurement-only target that cannot gate mechanism decisions). The primary CPU criterion (≥3%) is the gating metric.
- **``SCALEDOWN_STORAGE_COOLDOWN_S=300`` may block storage drain during cooldown phases**: If storage reserve activated late in ``tier1_hotspot_n1``, the 300s cooldown may still be active through the entire ``inter_hotspot_cooldown``, preventing storage scale-down evaluation. Storage nodes from ``storage_hotspot`` may persist through both Tier 1 phases into ``compute_spike``. This is acceptable for the experiment (storage count reflects peak demand) but the analyst should check ``elasticity_events.csv`` for scale-down timing relative to phase boundaries.
- **Read/write ``maxPoolSize`` asymmetry**: The read client uses ``maxPoolSize=1`` (architecturally required for controller routing control). The write client uses ``maxPoolSize=2`` (direct-to-primary, bypasses VIP). This asymmetry is harmless — writes are infrequent (15% mix in one phase) and the write pool size only helps under concurrent write bursts. Both were confirmed safe in pre-v3 diagnostic testing.
- **``mechanism_necessity_nocompute.env``**: Exists from v1 but was not used in v2. Verify ``MAX_DYNAMIC_COMPUTE=0`` is the only change from the all.env baseline.
- **VIP_HARD_TIMEOUT=30 may increase PacketIn rate**: Shorter flow-rule lifetime means OVS punts traffic to the controller more frequently. At 48 clients this is manageable, but if controller CPU spikes, revert to 60s.

---

## Artifact Contract

Same as v2. Each run folder under ``source/scripts/testing/metrics/<timestamp>_<label>/``
(e.g. ``20260628_133016_mechanism_v3_all``) must contain:

- `client_requests.csv`, `resource_stats.csv`, `resource_stats_debug.csv`
- `per_node_stats.csv`, `container_events.csv`
- `controller_lan1.log`, `controller_lan2.log`
- `elasticity_events.csv`, `node_lifecycle_timings.csv`, `policy_state.csv`
- `phases_snapshot.json`, `controller_env_snapshot.env`
- `service_logs/` directory

Expected later analysis outputs: per-run `cli_simple_run` summaries, cross-run `cli_mechanism_compare` (L vs M vs N), and `results_v3.md`.

Run folder pattern: ``source/scripts/testing/metrics/<timestamp>_<label>/``
(e.g. ``20260628_133016_mechanism_v3_all`` — note the label already contains
``mechanism_v3_``, so the folder is ``<ts>_mechanism_v3_all``, not
``<ts>_mechanism_v3_mechanism_v3_all``).

---

## RQ Linkage *(Thesis)*

This experiment supports **RQ2 (Backend Selection)** and **RQ3 (Data Locality)**
from the thesis research-question map (``tese/miscelineous/system_to_thesis_map_rq_v2.md``).

| RQ | Independent Variable (experiment) | Dependent Variable | How Measured |
|----|----------------------------------|-------------------|-------------|
| RQ2 — Does adaptive backend selection maintain service quality under WAN? | Storage reserve ON vs OFF (L vs N) | ``avg_time_db_ms``, storage CPU per node | ``resource_stats.csv``, ``per_node_stats.csv`` |
| RQ2 — Does compute elasticity prevent edge-server saturation? | Compute ON vs OFF (L vs S) | Edge server CPU, failure rate, ``server_count`` | ``resource_stats.csv``, ``client_requests.csv`` |
| RQ3 — Does Tier 1 selective sync reduce cross-region read penalty? | Tier 1 ON vs OFF (L vs M) | Consumer-LAN ``avg_time_db_ms``, total request latency | ``client_requests.csv`` per-phase per-LAN breakdown |
| RQ3 — Does Tier 1 activation cost exceed benefit at WAN=100ms? | L vs M (direction of latency difference) | Consumer-LAN latency delta | ``client_requests.csv`` — positive delta = benefit, negative = cost dominates |

---

---

## Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-06-28 | Initial v3 plan. Added write endpoint, extended cooldown, 48 clients. | Addresses v2 findings: Tier 1 paradox, storage CPU invisible, edge server load below ceiling. |
| 2026-06-28 | WAN_RTT_MS 50→100. Lean 4-run matrix replacing 7-run structure. | 100ms doubles Tier 1 signal. Runs O–R dropped — v2 already proved WAN isolation, storage at WAN=10, and pure single-variable ablations. |
| 2026-06-28 | Pre-v3 diagnostic run: diagnosed Tier 1 paradox root cause, ``cross_region_ratio`` mechanics, cascade failure chain. | Controller-log analysis of **v2 Run I** proved Tier 1 detection latency (not cooldown) causes owner-LAN degradation. ``cross_region_ratio`` only applies to ``device_status`` requests; effective rate = mix × eligible_clients × ratio. |
| 2026-06-28 | ``storage_hotspot`` mix 25/50/10/15 → 65/10/10/15, removed ``hotspot_direction``. | Old 25% mix gave 11% effective cross-region instead of expected 90%. New mix gives 58% (84 req/s). Removed directional block so both LANs stress MongoDB. |
| 2026-06-28 | ``SCALEUP_COMPUTE_COOLDOWN_S`` 45→20, ``SCALEUP_STORAGE_COOLDOWN_S`` 120→60 across all mechanism env files. | Pre-v3 diagnostic: cooldown was 10s too slow to prevent thread exhaustion cascade at 48-client scale. Faster scale-up keeps servers ahead of degradation. |
| 2026-06-28 | Write client: added double-checked locking (``_write_clients_lock``). | Fixes TOCTOU race when multiple Flask threads first enter the write path simultaneously during ``storage_hotspot``. |
| 2026-06-28 | ``VIP_HARD_TIMEOUT=30`` (down from 120s) across all mechanism env files. | OVS flow rules force backend re-selection 4× faster. When Tier 1 caches activate or servers join the pool, traffic redistributes within 30s instead of 120s. Natural circuit breaker for hung backends. |
| 2026-06-28 | Added Run T (``mechanism_v3_all_vip60``) — VIP timeout comparison. | 5-run matrix isolates VIP=30 vs VIP=60 under identical conditions. Answers whether 30s is too aggressive (PacketIn overhead) or 60s is too slow. |
| 2026-06-28 | **Experiment executed** — 5 runs (L, T, M, N, S). Full analysis in [results_v3.md](results_v3.md). | VIP=30 confirmed superior. Compute necessity reconfirmed (S vs L: edge CPU 2.8×). Storage necessity proven (N vs L: LAN2 collapse). Tier 1 effect measurable in avg_time_db (n2: 3.24×) but diluted in total latency by WAN=100ms. Storage CPU target (≥3%) not met — write volume insufficient. |
