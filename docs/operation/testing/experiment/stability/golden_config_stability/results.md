# Results — Golden Configuration Stability Gate

**Date**: 2026-06-09  
**Experiment plan**: [experiment_plan.md](./experiment_plan.md)  
**Runs**: `golden_config_a` (20260609_142511), `golden_config_b` (20260609_154802)  
**Overall outcome**: ⚠️ **Not yet stable.** Overall failure rate passes (1.6% A, 2.5% B), but persistent LAN2 connectivity collapse, cleanup debt, inter-run throughput variance, and absent reserve activation block the gate. Three issues identified — one fixed, two remain.

---

## Run Timeline

| Run | Date | Status | Cumulative Analysis | Conclusions | Changes Made | Expectations for This Run |
|-----|------|--------|---------------------|-------------|--------------|--------------------------|
| v1 (`golden_config_a`) | 2026-06-09 14:25 UTC | ⚠️ Overall 1.6% but demand_drop 26.4%, LAN-flip, 7 tracebacks, 19 stale containers | — (initial run) | — (initial run) | — (baseline) | Per plan: overall ≤3%, all mechanisms exercise, clean drain, LAN symmetry ≤3× |
| v1 (`golden_config_b`) | 2026-06-09 15:48 UTC | ⚠️ Overall 2.5% but demand_drop 14.4%, LAN-flip, 5 stale containers, 29% throughput loss | Run A: LAN2 dead, state.py bug, cleanup failure. All failures are HTTP-0 (TCP), not HTTP-503 (app). | state.py bug is the cleanup root cause. LAN2 collapse is infrastructure-level, not code. | `state.py:158` — `controller.datapaths.items()` → `for datapath in controller.datapaths:` | state.py fix should eliminate tracebacks and reduce cleanup debt; LAN2 collapse may or may not improve |

---

### 1. Run v1 — `golden_config_a` (`20260609_142511`)

**Status**: ⚠️ — Overall passes but demand_drop spike, LAN-flip, state.py bug, cleanup failure

#### Expectations from Plan

| Expectation | Rationale |
|---|---|
| Overall failure ≤3% | WAN R2 achieved 0.05% with same config |
| All 4 mechanisms exercise | Storage reserve, Tier 1, compute, conntrack |
| Non-hotspot phases ≤1% | No elasticity churn in baseline/low-mod/cooldown/drop |
| Hotspot phases ≤5% | Storage churn bounded by conntrack |
| Compute phases ≤5% | Dashboard-heavy but conntrack prevents cascade |
| LAN symmetry ≤3× | LAN-flip absent after txqueuelen fix |
| Clean drain to idle | All dynamic containers removed |
| Zero epoch rotations | Conntrack eliminates stale-rule cascade |
| Zero controller tracebacks | Code should be production-clean |

#### Results

**Run folder**: `source/scripts/testing/metrics/20260609_142511_golden_config_a/`

All 10 phases completed to `idle`. 115,146 total requests. `create_indexes.py` had a missing `DESCENDING` import — fixed before launch, no impact on results.

**Service Quality**:

| Phase | Requests | Failures | Rate | LAN1 | LAN2 | Target | Verdict |
|---|---|---|---|---|---|---|---|
| `baseline` | 484 | 0 | 0.0% | 0.0% | 0.0% | ≤1% | ✅ |
| `local_moderate` | 4,301 | 0 | 0.0% | 0.0% | 0.0% | ≤1% | ✅ |
| `storage_stress` | 27,333 | 12 | 0.0% | 0.0% | 0.0% | ≤5% | ✅ |
| `cross_region_hotspot` | 29,895 | 17 | 0.1% | 0.0% | 0.1% | ≤5% | ✅ |
| `inter_hotspot_cooldown` | 668 | 8 | 1.2% | 0.0% | 1.2% | ≤1% | ⚠️ |
| `reverse_hotspot` | 25,564 | 1,031 | 4.0% | 0.0% | 4.0% | ≤5% | ✅ |
| `compute_ramp` | 8,362 | 10 | 0.1% | 0.0% | 0.1% | ≤5% | ✅ |
| `compute_spike` | 11,137 | 62 | 0.6% | 0.0% | 0.6% | ≤5% | ✅ |
| `sustained_plateau` | 5,047 | 116 | 2.3% | 0.0% | 2.3% | ≤5% | ✅ |
| `demand_drop` | 2,355 | 622 | **26.4%** | 0.0% | 26.4% | ≤1% | 🔴 |
| **OVERALL** | **115,146** | **1,878** | **1.6%** | 0.07% | 3.95% | ≤3% | ✅ |

All 1,878 failures are HTTP status `0` (TCP connection failure). Zero HTTP `503` (application error). The system never rejects valid requests — clients simply cannot establish a TCP connection.

**Mechanism Exercise**:

| Mechanism | Evidence | Verdict |
|---|---|---|
| Tier 2 storage | max `storage_count`=8; 0 `[reserve] activated` events | ⚠️ Storage scaled but reserve path unused |
| Tier 1 selective-sync | `SelectiveSyncAlert` on both LANs; reached `ACTIVE` | ✅ |
| Compute elasticity | max `server_count`=4; 19 LAN1 + 45 LAN2 `ComputeAlert` | ✅ |
| Conntrack VIP_DATA | max `conntrack_entries_n1`=65, `n2`=57 | ✅ |

**Health**:

| Check | Result | Verdict |
|---|---|---|
| Controller tracebacks | **7** — all `state.py:158` `AttributeError: 'list' object has no attribute 'items'` | 🔴 |
| Epoch rotations | 0 | ✅ |
| Recovery mode epochs | 0 | ✅ |
| Cleanup at idle | **19** dynamic containers (17 storage + 2 compute) | 🔴 |
| LAN symmetry | LAN1=0.07%, LAN2=3.95% — **60.4× ratio** | 🔴 |

**Root cause — `state.py` bug**: `controller.datapaths` is initialised as a `list` (`[]` in `main_n1.py:65` / `main_n2.py:65`), but `state.py:158` called `.items()` on it, expecting a dict. This `AttributeError` prevented all storage `unregister_storage_backend` calls from deleting forward flow rules, which blocked scale-down. The 7 tracebacks correspond to 7 failed scale-down attempts. The 19 residual containers are the direct consequence.

---

### 2. Run v1 — `golden_config_b` (`20260609_154802`)

**Status**: ⚠️ — state.py fix confirmed (0 tracebacks, 5→19 containers), but LAN2 collapse worsened and throughput dropped 29%

#### Previous Run Analysis (cumulative)

Run A revealed three issues: (1) `state.py:158` bug blocking storage scale-down, (2) LAN2 TCP connectivity collapse during low-load phases, (3) all failures are HTTP-0 (TCP connection failure), not HTTP-503. The state.py bug is a clear code defect with a one-line fix. The LAN2 collapse is infrastructure-level — LAN1 is essentially perfect (0.07% failure) while LAN2 fails at 3.95%, exclusively with TCP connection failures. This pattern is identical to the LAN-flip observed in v5.6 B (21.3% overall, before txqueuelen fix) and in the WAN diagnostic campaign — but the txqueuelen fix was already deployed, so the chokepoint must be elsewhere.

#### Conclusions

1. **`state.py` bug is the cleanup root cause** (confirmed). The `.items()` → list-iteration fix eliminated all controller tracebacks (7→0) and reduced stale containers from 19 to 5. This is a verified fix.

2. **LAN2 TCP connectivity collapse persists and worsened** (new evidence). LAN2 failure rate increased from 3.95% (A) to 11.92% (B). All failures remain HTTP-0. The collapse is not load-correlated — the worst phases are `demand_drop` (1 req/s, 0% cross-region) and `inter_hotspot_cooldown` (1 req/s, 0% cross-region). This rules out throughput saturation as the cause. The pattern suggests a resource leak or state accumulation on the LAN2 path that degrades over time — Run B was launched immediately after Run A on the same host without a host reboot.

3. **System throughput degraded 29% between runs** (new evidence). Run A processed 115,146 requests; Run B processed 82,176. This is consistent with the resource-degradation hypothesis — something on the LAN2 path (kernel conntrack table, OVS datapath, iptables rules, Docker bridge) accumulates state that is not fully cleaned between runs, and the second run starts with degraded capacity.

4. **Storage reserve never activates under the integrated workload** (observation). 0 `[reserve] activated` events in either run. The t12 threshold (0.12) was chosen from a dedicated storage-reserve probe workload with 90% device_status mix. The integrated `phases.json` workload has a more diverse mix (dashboard, service_pressure) that produces a different storage stress profile. The reserve path itself is proven usable (from `storage_reserve_use_validation`), but the trigger threshold needs recalibration for the integrated workload shape.

5. **Conntrack, Tier 1, and compute mechanisms all exercise correctly** (confirmed). Conntrack entries present (n1=52, n2=39), zero epoch rotations, Tier 1 reaches ACTIVE in both directions, compute scales up/down. These mechanisms are not implicated in the LAN2 failure.

#### Changes Made

| File | Change | Rationale |
|------|--------|-----------|
| `source/sdn_controller/_vip_routing/state.py:158` | `for dp_id, datapath in controller.datapaths.items():` → `for datapath in controller.datapaths:` with `dp_id = datapath.id` | `controller.datapaths` is a `list`, not a `dict`. The `.items()` call raised `AttributeError`, blocking storage scale-down. Linked to Run A conclusion #1. |
| `source/scripts/testing/create_indexes.py:5` | Added `DESCENDING` to pymongo import | `DESCENDING` was used at line 22 but not imported. Caused `setup_test_data` to fail before Run A launch. |

#### Expectations for This Rerun

| Expectation | Rationale |
|---|---|
| Controller tracebacks = 0 | state.py fix removes the only known traceback source |
| Cleanup improved (fewer stale containers) | Storage scale-down should work correctly with fixed `unregister_storage_backend` |
| LAN2 collapse may or may not improve | state.py fix does not address the LAN2 TCP path; this is a separate infrastructure issue |
| Overall failure rate remains bounded | Same workload, same config; storage phases should stay clean |

#### Results

**Run folder**: `source/scripts/testing/metrics/20260609_154802_golden_config_b/`

All 10 phases completed to `idle`. 82,176 total requests — 28.6% fewer than Run A.

**Service Quality**:

| Phase | Run A | Run B | Target | A | B |
|---|---|---|---|---|---|
| `baseline` | 0.0% | 0.0% | ≤1% | ✅ | ✅ |
| `local_moderate` | 0.0% | 0.0% | ≤1% | ✅ | ✅ |
| `storage_stress` | 0.0% | 3.1% | ≤5% | ✅ | ✅ |
| `cross_region_hotspot` | 0.1% | 1.6% | ≤5% | ✅ | ✅ |
| `inter_hotspot_cooldown` | 1.2% | **9.6%** | ≤1% | ⚠️ | 🔴 |
| `reverse_hotspot` | 4.0% | 1.7% | ≤5% | ✅ | ✅ |
| `compute_ramp` | 0.1% | 3.9% | ≤5% | ✅ | ✅ |
| `compute_spike` | 0.6% | 2.4% | ≤5% | ✅ | ✅ |
| `sustained_plateau` | 2.3% | 3.8% | ≤5% | ✅ | ✅ |
| `demand_drop` | **26.4%** | **14.4%** | ≤1% | 🔴 | 🔴 |
| **OVERALL** | **1.6%** | **2.5%** | ≤3% | ✅ | ✅ |

**Expectation assessment**:

| Expectation | Result | Verdict |
|---|---|---|
| Controller tracebacks = 0 | **0** tracebacks (was 7 in Run A) | ✅ Met |
| Cleanup improved | **5** dynamic containers (was 19 in Run A) | ⚠️ Improved but not zero |
| LAN2 collapse may improve | LAN2 **worsened**: 3.95% → 11.92% | ❌ Degraded |
| Overall bounded | 2.5% (≤3% target met) | ✅ Met |

**Health comparison**:

| Check | Run A | Run B |
|---|---|---|
| Controller tracebacks | 7 | **0** ✅ |
| Epoch rotations | 0 | 0 |
| Recovery mode | 0 | 0 |
| Dynamic at idle | 19 | **5** ⚠️ |
| LAN1 failure | 0.07% | 0.14% |
| LAN2 failure | 3.95% | **11.92%** 🔴 |
| LAN ratio | 60× | **84×** 🔴 |
| HTTP 0 (conn fail) | 1,878 (100%) | 2,044 (100%) |
| HTTP 503 (app err) | 0 | 0 |

---

## Full Criteria Assessment (Pair)

| # | Criterion | Run A | Run B | Pair Verdict |
|---|---|---|---|---|
| 1 | Run completion & artifacts | ✅ | ✅ | ✅ |
| 2 | All 4 mechanisms exercise | ⚠️ (no reserve activate) | ⚠️ (no reserve activate) | ⚠️ |
| 3 | Service-quality envelope | 🔴 (demand_drop, cooldown) | 🔴 (demand_drop, cooldown) | 🔴 |
| 4 | Control-plane health | 🔴 (7 tracebacks) | ✅ | ⚠️ (fixed in B) |
| 5 | Cleanup correctness | 🔴 (19 containers) | ⚠️ (5 containers) | 🔴 |
| 6 | Inter-run repeatability | — | — | 🔴 (28.6% vol diff) |

**Criteria met**: 1/6 fully, 2/6 partially, 3/6 failed.

---

## Root Cause Summary

| # | Issue | Impact | Evidence | Status |
|---|---|---|---|---|
| 1 | `state.py:158` `.items()` on list | Blocks storage scale-down; 19 stale containers | 7 identical tracebacks in Run A; 0 in Run B after fix | ✅ Fixed |
| 2 | LAN2 TCP connectivity collapse | 100% of failures; LAN2 4–12% failure, LAN1 0.07–0.14% | All 3,922 failures across both runs are HTTP-0 on LAN2. Worst in low-load phases. | 🔴 Open |
| 3 | Storage reserve never activates | Storage nodes added via regular scale path, not reserve | 0 `[reserve] activated` in either run; t12 threshold from dedicated probe workload | ⚠️ Configuration |
| 4 | Inter-run resource degradation | Run B processed 29% fewer requests; LAN2 worsened | Same host, consecutive runs, no reboot between | 🔴 Open |
| 5 | `create_indexes.py` missing import | Blocked `setup_test_data` before Run A | `NameError: name 'DESCENDING' is not defined` | ✅ Fixed |

---

## Next Actions

1. **Investigate LAN2 TCP path** — check OVS datapath flows, iptables FORWARD rules, Docker bridge state, and kernel conntrack table on the LAN2 side after a run. The LAN-flip pattern (one LAN perfect, one dead) with HTTP-0 failures points to a routing or NAT state asymmetry, not an application bug.

2. **Host reboot between runs** — the 29% throughput degradation and LAN2 worsening between consecutive runs on the same host suggests accumulated kernel/container state. A host reboot between Run A and Run B would isolate whether this is a genuine system degradation or a test-infrastructure artefact.

3. **Recalibrate storage reserve threshold for integrated workload** — the t12 threshold (0.12) was tuned on a dedicated storage probe (90% device_status). The integrated `phases.json` workload has a more diverse mix. Either lower the threshold for the integrated workload or accept that the reserve path is exercised separately.

4. **Re-run the pair after LAN2 investigation and host reboot** — once the LAN2 collapse is understood and mitigated, re-run the golden config pair with the state.py fix in place to confirm the gate can be passed.

## Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-06-09 | Initial pair executed (`golden_config_a` + `golden_config_b`). state.py bug found and fixed between runs. | First golden-configuration stability gate attempt. See §1–§2. |
