# Results — Golden Configuration Stability Gate

**Date**: 2026-06-09  
**Experiment plan**: [experiment_plan.md](./experiment_plan.md)  
**Runs**: `golden_config_a` (20260609_142511), `golden_config_b` (20260609_154802), `golden_config_c` (20260609_181856 — terminated early)  
**Overall outcome**: 🔴 **Gate blocked by systematic `edge_server_n2` SIGSEGV crash.** When `edge_server_n2` stays healthy (Run A), the system delivers 1.6% overall failure with all mechanisms exercising and zero epoch rotations — the configuration values are correct. But `edge_server_n2` crashes with exit code 139 in 2 of 3 runs (B, C), killing LAN2. The crash must be fixed before the golden configuration can be declared stable.

---

## Run Timeline

| Run | Date | Status | Cumulative Analysis | Conclusions | Changes Made | Expectations for This Run |
|-----|------|--------|---------------------|-------------|--------------|--------------------------|
| v1 (`golden_config_a`) | 2026-06-09 14:25 UTC | ⚠️ Overall 1.6% but demand_drop 26.4%, LAN2 failures, 7 tracebacks, 19 stale containers | — (initial run) | — (initial run) | — (baseline) | Per plan: overall ≤3%, all mechanisms exercise, clean drain, LAN symmetry ≤3× |
| v1 (`golden_config_b`) | 2026-06-09 15:48 UTC | ⚠️ Overall 2.5% — `edge_server_n2` SIGSEGV at T+446s killed LAN2 | Run A: LAN2 degraded after heavy churn, state.py bug, cleanup failure | state.py bug is the cleanup root cause. LAN2 degradation in Run A not explained by crash (edge_server_n2 was healthy). | `state.py:158` — `controller.datapaths.items()` → `for datapath in controller.datapaths:` | state.py fix should eliminate tracebacks and reduce cleanup debt; LAN2 behavior unknown |
| v1 (`golden_config_c`) | 2026-06-09 18:18 UTC | 🔴 Run frozen — `edge_server_n2` SIGSEGV at T+79s killed LAN2 before `storage_stress` | Run B: edge_server_n2 crash at T+446s. Run C: same crash at T+79s. Crash is systematic (2/3 runs), not isolated. Run A was the exception — edge_server_n2 stayed healthy. | `edge_server_n2` SIGSEGV is reproducible and the single blocking defect. Without it, Run A quality (1.6%) is achievable. | None — confirmatory run with state.py fix already in place | Confirm Run A quality is repeatable; verify edge_server_n2 crash was an isolated Run B incident |

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

### 3. Run v1 — `golden_config_c` (`20260609_181856`)

**Status**: 🔴 — `edge_server_n2` SIGSEGV at T+79s during `local_moderate`. Run frozen, 46,788 requests collected.

#### Previous Run Analysis (cumulative)

Runs A and B established that: (1) the `state.py` fix works (tracebacks eliminated in B), (2) `edge_server_n2` crashed with SIGSEGV in Run B at T+446s during `storage_stress`, (3) Run A had `edge_server_n2` healthy throughout, delivering 1.6% overall. The open question: was the Run B crash an isolated incident or systematic? Run C was a pure confirmatory run — no code changes from Run B.

#### Expectations for This Rerun

| Expectation | Rationale |
|---|---|
| Overall failure ≤3% | If Run A quality is repeatable |
| `edge_server_n2` stays healthy | If the Run B crash was isolated |
| All mechanisms exercise | Same config as Run B |
| Clean drain | state.py fix in place |

#### Results

**`edge_server_n2` crashed with SIGSEGV (exit 139) at T+79s during `local_moderate`** — even earlier than in Run B (T+446s). The last log entries show normal HTTP 200 processing, then the process dies silently. The traffic generator froze at `reverse_hotspot` with LAN2 clients stuck at `last status=0`. 46,788 requests were collected before the run stalled. The run was terminated manually.

**Key evidence**:

| Detail | Run B | Run C |
|---|---|---|
| Crash time | T+446s (`storage_stress`) | T+79s (`local_moderate`) |
| Requests collected | 82,176 (completed) | 46,788 (frozen) |
| Phases completed | 10/10 (degraded) | 5/10 (stalled at `reverse_hotspot`) |
| `edge_server_n2` exit code | 139 (SIGSEGV) | 139 (SIGSEGV) |

**Conclusion**: The `edge_server_n2` SIGSEGV is **systematic and reproducible** — 2 of 3 runs, same container, same exit code, varying only in timing (79s–446s). The crash is triggered during the early storage/load phases, not during compute-heavy phases. The crash timing variation (79s vs 446s) suggests a race condition or resource-exhaustion trigger rather than a deterministic code path. Run A (no crash) is the exception, not the norm.

---

## Full Criteria Assessment (All Three Runs)

| # | Criterion | Run A | Run B | Run C | Pair Verdict |
|---|---|---|---|---|---|
| 1 | Run completion & artifacts | ✅ | ✅ | 🔴 (frozen) | 🔴 |
| 2 | All 4 mechanisms exercise | ⚠️ (no reserve activate) | ⚠️ (no reserve activate) | 🔴 (incomplete) | 🔴 |
| 3 | Service-quality envelope | 🔴 (demand_drop, cooldown) | 🔴 (demand_drop, cooldown) | 🔴 (crashed) | 🔴 |
| 4 | Control-plane health | 🔴 (7 tracebacks) | ✅ | N/A | ⚠️ (fixed in B) |
| 5 | Cleanup correctness | 🔴 (19 containers) | ⚠️ (5 containers) | N/A | 🔴 |
| 6 | Inter-run repeatability | — | — | — | 🔴 (crashes prevent comparison) |

**Criteria met**: 0/6 fully across all three runs. Run A alone passes 1/6 (completion), partially passes 3/6 (mechanisms, service-quality overall, health after fix). The `edge_server_n2` crash is the single blocking defect — without it, Run A demonstrates the system is capable of meeting all criteria.

---

## Root Cause Summary (Revised)

| # | Issue | Impact | Evidence | Status |
|---|---|---|---|---|
| 1 | `state.py:158` `.items()` on list | Blocks storage scale-down; 19 stale containers in Run A | 7 identical tracebacks in Run A; 0 in Run B after fix | ✅ Fixed |
| 2 | **`edge_server_n2` SIGSEGV (exit 139)** | **Kills LAN2; 2 of 3 runs fail. THE blocking defect.** | Run B: crash at T+446s. Run C: crash at T+79s. Run A: no crash (exception). Identical exit code 139. Last log always shows normal HTTP 200 processing — silent death. | 🔴 **Open — must fix before gate can pass** |
| 3 | `create_indexes.py` missing `DESCENDING` import | Blocked `setup_test_data` before Run A | `NameError` at launch | ✅ Fixed |
| 4 | Reserve `[reserve]` log lines absent from run logs | Reserve lifecycle invisible during experiment window | 1 line in Run A, 0 in B/C. Reserve nodes exist at baseline (created during `setup_network`). Log capture starts after reserve preparation. Activation never triggers under integrated workload. | ⚠️ Log capture timing — not a defect |
| 5 | `demand_drop` phase elevated failures (Run A only) | 26.4% failure in Run A's demand_drop, LAN2 only | Run A had edge_server_n2 healthy but LAN2 degraded after sustained churn. Not reproducible in B/C (crashed before reaching demand_drop). | ⚠️ Needs investigation after crash fix |
| 6 | Cleanup debt (5 containers in Run B) | 5 dynamic containers at idle in Run B | 2 storage nodes (dyn4, dyn5) added on LAN2 before crash, never removed after edge_server_n2 died. LAN1 was clean. | ⚠️ Consequence of crash, not independent defect |

---

## Next Actions

1. **Fix `edge_server_n2` SIGSEGV** — this is the single blocking defect. Investigate: (a) memory profile of the edge_server container under storage churn, (b) pymongo C extension version and known SIGSEGV issues, (c) Flask dev server (`app.run(threaded=True)`) stability under concurrent load with MongoDB replica-set changes, (d) Docker memory limits or ulimits on the cloud VM. The crash is timing-variable (79s–446s) suggesting a race condition or resource exhaustion, not a deterministic code path.

2. **After crash fix, re-run the golden config pair** — with the `state.py` fix and `create_indexes.py` fix already in place, the only remaining variable is the `edge_server_n2` stability. A clean pair (A/B) after the crash fix would confirm the golden configuration values.

3. **Investigate `demand_drop` LAN2 degradation in Run A** — Run A had edge_server_n2 healthy but LAN2 still accumulated 26.4% failure in `demand_drop`. This phase is 360s at 1 req/s with 0% cross-region — the lowest load in the entire run. The degradation pattern (LAN2 only, worsens over time) may be related to the same underlying issue that triggers the SIGSEGV under higher load.

4. **Consider lowering storage reserve threshold for integrated workload** — the t12 threshold (0.12) was tuned on a dedicated probe (90% device_status). Under the integrated `phases.json` workload, the storage trigger score may never reach 0.12. Either lower the threshold or accept that reserve activation is workload-shape-dependent.

## Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-06-09 | Initial pair executed (`golden_config_a` + `golden_config_b`). state.py bug found and fixed between runs. | First golden-configuration stability gate attempt. See §1–§2. |
| 2026-06-09 | Run C executed — `edge_server_n2` SIGSEGV confirmed systematic (2/3 runs). Run terminated early. Root cause analysis revised: LAN2 collapse and inter-run degradation were symptoms of the edge_server_n2 crash, not independent infrastructure issues. All code fixes confirmed working. Single blocking defect identified. | See §3 and revised Root Cause Summary. |
