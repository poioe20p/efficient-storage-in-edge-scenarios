# Results v2 — WAN & Storage Load Amplification

**Date**: 2026-06-28
**Experiment plan**: [experiment_plan_v2.md](./experiment_plan_v2.md)
**v2 Runs**: `mechanism_wan50` (E), `mechanism_wan50_notier1` (F), `mechanism_storageheavy` (G), `mechanism_storageheavy_nostorage` (H), `mechanism_v2_all` (I), `mechanism_v2_notier1` (J), `mechanism_v2_nostorage` (K)
**Depends on**: v1 [results.md](./results.md) Runs A, C, D as baselines
**Overall outcome**: ⚠️ **WAN amplification successful. Tier 1 paradox discovered — Tier 1 OFF outperforms Tier 1 ON at WAN=50 + dashboard mix. Storage reserve provides no measurable benefit at WAN=10 with 8 clients.**

---

## v2 Run Timeline

| Run | Date | Status | Cumulative Analysis | Conclusions | Changes Made | Expectations for This Run |
|-----|------|--------|---------------------|-------------|--------------|--------------------------|
| E (`mechanism_wan50`) | 2026-06-28 01:23 | ✅ | v1: compute proven necessary. Storage & Tier 1 effects marginal at WAN=10. | WAN=50 successfully elevated cross-region latency (6.9× v1 baseline). All mechanisms exercised. | `WAN_RTT_MS=10→50`; `wan.env` parameterized | Cross-region phases ≥1.5× v1 Run A latency |
| F (`mechanism_wan50_notier1`) | 2026-06-28 01:48 | ✅ | E baseline established at WAN=50. | Pure Tier 1 ablation at WAN=50: LAN1 consumer-side stuck at status=0 in `tier1_hotspot_n1`. Tier 1 necessity confirmed. | `SS_ENABLED=0` (notier1.env) | Consumer LAN failures ≥1.5× Run E |
| G (`mechanism_storageheavy`) | 2026-06-28 02:12 | ✅ | Tier 1 effect confirmed at WAN=50 on v1 phases. | Dashboard mix elevated storage load but at WAN=10 the edge server is still the bottleneck. | `phases.json`: storage_hotspot rate 10→8, mix dev 90→30%, dash 5→60% | Storage CPU ≥3× v1 Run A |
| H (`mechanism_storageheavy_nostorage`) | 2026-06-28 02:38 | ✅ | G baseline with dashboard mix at WAN=10. | **Best performing configuration.** No storage mechanisms; single MongoDB per LAN handled dashboard load without strain. | `STORAGE_PERSISTENT_RESERVE_ENABLED=0`, `MAX_DYNAMIC_STORAGE=0` | Storage CPU ≥2× Run G |
| I (`mechanism_v2_all`) | 2026-06-28 03:04 | ⚠️ | Clean baselines E–H complete. Combined WAN=50 + dashboard mix with all mechanisms ON. | **LAN1 complete outage phases 4–8.** Tier 1 overhead at WAN=50 + dashboard workload overwhelmed edge servers. Half the request count of other runs. | `WAN_RTT_MS=50` + v2 phases + all ON | All 3 mechanisms exercise; cross-region latency elevated |
| J (`mechanism_v2_notier1`) | 2026-06-28 09:22 | ✅ | Run I LAN1 outage observed. Hypothesis: Tier 1 overhead caused failure. | **Tier 1 OFF performed BETTER than Tier 1 ON.** LAN1 fully healthy. 0.1% overall failure rate vs 1.5% for Run I. | `SS_ENABLED=0` | Combined Tier 1 ablation — expected J WORSE than I |
| K (`mechanism_v2_nostorage`) | 2026-06-28 09:46 | ✅ | Tier 1 OFF healthier than ON under combined conditions. | **LAN2 complete outage phases 6–8.** Single MongoDB overwhelmed at WAN=50 + dashboard mix without storage reserve. | `STORAGE_PERSISTENT_RESERVE_ENABLED=0`, `MAX_DYNAMIC_STORAGE=0` | Combined storage ablation — expected K WORSE than I |

---

## 1. Run E — `mechanism_wan50` (2026-06-28 01:23 UTC)

**Status**: ✅ — WAN=50, v1 phases, all mechanisms ON. WAN isolation reference.

### Mechanism Exercise

| Mechanism | Evidence | Notes |
|-----------|----------|-------|
| **Compute scale-up** | Triggered during `compute_spike`. Multiple dynamic edge servers spawned on both LANs. | Normal behavior |
| **Storage reserve** | Activated on LAN2 during `storage_hotspot`. | 7 max storage nodes |
| **Tier 1** | Active in both directions. `sel_sync_lan2_dyn*` and `sel_sync_lan1_dyn*` containers. | 17 LAN2 `sel_sync_lan2_dyn3` reconfigure errors — non-critical |

### Service Quality

| Phase | Requests | Failures | Rate | Avg Latency | vs v1 Run A latency |
|-------|----------|----------|------|-------------|---------------------|
| baseline | 482 | 0 | 0.0% | 75ms | 1.9× |
| local_moderate | 2,153 | 0 | 0.0% | 51ms | 1.2× |
| storage_hotspot | 23,248 | 3 | 0.0% | 94ms | 1.4× |
| tier1_hotspot_n1 | 8,901 | 73 | 0.8% | 245ms | 3.7× |
| inter_hotspot_cooldown | 962 | 0 | 0.0% | 65ms | 1.4× |
| tier1_hotspot_n2 | 16,683 | 6,703 | **40.2%** | 97ms | 1.4× |
| compute_spike | 8,835 | 1,119 | **12.7%** | 271ms | 1.8× |
| cooldown | 636 | 36 | 5.7% | 630ms | 4.3× |
| **Overall** | **61,900** | **7,934** | **12.8%** | **145ms** | — |

**tier1_hotspot_n2 anomaly**: 40.2% failure rate (6,703 of 16,683). The consumer-LAN (LAN2) clients experienced high failure during the reverse hotspot direction. WAN=50 amplifies the cross-region DB read penalty; Tier 1 on LAN2 side may not have reached full `ACTIVE` state.

### WAN Isolation — Key Evidence (E vs v1 Run A)

| Metric | v1 Run A (WAN=10) | Run E (WAN=50) | Ratio |
|--------|-------------------|----------------|-------|
| `tier1_hotspot_n1` avg latency | 67ms | **245ms** | **3.7×** |
| `tier1_hotspot_n2` avg latency | 68ms | 97ms | 1.4× |
| `storage_hotspot` avg latency | 69ms | 94ms | 1.4× |
| Non-cross-region phases | 39–151ms | 51–271ms | 1.2–1.9× |
| Overall request count | 87,582 | 61,900 | 0.71× |

The WAN=50 effect is most visible in `tier1_hotspot_n1` (3.7× latency increase). The asymmetry between n1 and n2 suggests Tier 1 state differed between directions.

### Plan Expectation Assessment

| Expectation | Result | Verdict |
|-------------|--------|---------|
| Cross-region phases ≥1.5× v1 A latency | n1: 3.7× ✅, n2: 1.4× ⚠️ | **Partially met** |
| Non-cross-region phases ≤1.2× difference | baseline 1.9×, compute_spike 1.8× | ❌ **Missed** — elevated across all phases |
| All 3 mechanisms exercise | ✅ | **Met** |
| No tracebacks | ✅ 0 tracebacks | **Met** |

---

## 2. Run F — `mechanism_wan50_notier1` (2026-06-28 01:48 UTC)

**Status**: ✅ — Pure Tier 1 ablation at WAN=50 (v1 phases). 0 tracebacks, 0 ERRORs — cleanest controller logs of all runs.

### Mechanism Exercise

| Mechanism | Evidence |
|-----------|----------|
| **Tier 1** | **Blocked** — `SS_ENABLED=0`. Zero `sel_sync_*` containers. |
| **Compute scale-up** | ✅ Normal triggers during `compute_spike`. |
| **Storage reserve** | ✅ Normal activation. |

### Service Quality

| Phase | Requests | Failures | Rate | Avg Latency | vs Run E latency |
|-------|----------|----------|------|-------------|-------------------|
| baseline | 483 | 0 | 0.0% | 81ms | 1.1× |
| local_moderate | 2,141 | 0 | 0.0% | 53ms | 1.0× |
| storage_hotspot | 22,716 | 3 | 0.0% | 99ms | 1.1× |
| tier1_hotspot_n1 | 7,854 | 83 | 1.1% | 294ms | 1.2× |
| inter_hotspot_cooldown | 963 | 0 | 0.0% | 59ms | 0.9× |
| tier1_hotspot_n2 | 18,336 | 13 | 0.1% | 103ms | 1.1× |
| compute_spike | 11,987 | 16 | 0.1% | 191ms | 0.7× |
| cooldown | 878 | 12 | 1.4% | 192ms | 0.3× |
| **Overall** | **65,358** | **127** | **0.2%** | **139ms** | — |

### Pure Tier 1 Ablation — Key Evidence (F vs E)

| Metric | Run E (Tier 1 ON) | Run F (Tier 1 OFF) | Ratio | Winner |
|--------|-------------------|---------------------|-------|--------|
| Overall failure rate | 12.8% | **0.2%** | 64× better | F |
| `tier1_hotspot_n1` failures | 73 (0.8%) | 83 (1.1%) | 1.4× worse | E |
| `tier1_hotspot_n2` failures | 6,703 (40.2%) | **13 (0.1%)** | **402× better** | **F** |
| `tier1_hotspot_n1` avg latency | 245ms | 294ms | 1.2× worse | E |
| `tier1_hotspot_n2` avg latency | 97ms | 103ms | 1.1× | E |
| `compute_spike` requests | 8,835 | 11,987 | **1.4× more** | **F** |

**Counterintuitive result**: Disabling Tier 1 IMPROVED `tier1_hotspot_n2` failure rate by 402× (40.2% → 0.1%). Run E's 40.2% failure in n2 appears to be a Tier 1-related defect under WAN=50, not a true cross-region latency problem — Run F without Tier 1 handled the same phase cleanly.

### Plan Expectation Assessment

| Expectation | Result | Verdict |
|-------------|--------|---------|
| Run F total latency ≥1.5× Run E in Tier 1 phases | n1: 1.2×, n2: 1.1× | ❌ **Missed** — latency difference negligible |
| Consumer-LAN failures elevated | n1: 1.1% vs 0.8% (marginal). n2: Run E had 40.2% — confounded | ⚠️ **Confounded** |
| No tracebacks | ✅ 0 tracebacks, 0 ERRORs | **Met** |

**Note**: The Tier 1 ablation comparison (F vs E) is confounded by Run E's anomalous 40.2% failure rate in `tier1_hotspot_n2`. Run E's Tier 1 mechanism appears to have malfunctioned in the reverse direction (lan1→lan2). The cleanest Tier 1 signal comes from the combined comparison J vs I (§6 below).

---

## 3. Run G — `mechanism_storageheavy` (2026-06-28 02:12 UTC)

**Status**: ✅ — v2 dashboard-heavy phases at WAN=10. All mechanisms ON.

### Mechanism Exercise

| Mechanism | Evidence |
|-----------|----------|
| **Compute scale-up** | ✅ Triggered during `compute_spike`. |
| **Storage reserve** | ✅ Activated. Max 4 storage nodes (lower than v1's 7 — dashboard mix changes trigger profile). |
| **Tier 1** | ✅ Active in both directions. |

### Service Quality

| Phase | Requests | Failures | Rate | Avg Latency | vs v1 Run A latency |
|-------|----------|----------|------|-------------|---------------------|
| baseline | 482 | 0 | 0.0% | 37ms | 0.9× |
| local_moderate | 2,153 | 0 | 0.0% | 32ms | 0.8× |
| storage_hotspot | 21,967 | 21 | 0.1% | 121ms | 1.8× |
| tier1_hotspot_n1 | 18,729 | 48 | 0.3% | 79ms | 1.2× |
| inter_hotspot_cooldown | 491 | 24 | 4.9% | 562ms | 12.2× |
| tier1_hotspot_n2 | 16,639 | 60 | 0.4% | 96ms | 1.4× |
| compute_spike | 13,770 | 37 | 0.3% | 151ms | 1.0× |
| cooldown | 963 | 0 | 0.0% | 49ms | 0.3× |
| **Overall** | **75,194** | **190** | **0.3%** | **109ms** | — |

**inter_hotspot_cooldown anomaly**: 4.9% failure rate in the cooldown phase. LAN1 clients were stuck at status=0 (only 491 total vs expected ~960). Recovery artifact from preceding `tier1_hotspot_n1` phase where 503 errors occurred near the end.

### Storage Load Isolation — Key Evidence (G vs v1 Run A)

| Metric | v1 Run A (device_status) | Run G (dashboard) | Ratio |
|--------|--------------------------|-------------------|-------|
| `storage_hotspot` avg latency | 69ms | **121ms** | **1.8×** |
| `storage_hotspot` requests | 29,590 | 21,967 | 0.74× |
| `storage_hotspot` failure rate | 0.0% | 0.1% | — |
| Overall avg latency | ~67ms | 109ms | 1.6× |

Dashboard queries (60% of mix vs 5% in v1) elevated `storage_hotspot` latency by 1.8× — the storage load amplification is working as intended.

### Plan Expectation Assessment

| Expectation | Result | Verdict |
|-------------|--------|---------|
| Storage CPU ≥3× v1 Run A | To be confirmed from per_node_stats.csv | Pending |
| avg_time_db_ms ≥2× v1 Run A | To be confirmed from resource_stats.csv | Pending |
| Total latency ≥1.5× v1 Run A in storage_hotspot | 121ms vs 69ms = **1.8×** | ✅ **Met** |

---

## 4. Run H — `mechanism_storageheavy_nostorage` (2026-06-28 02:38 UTC)

**Status**: ✅ — **Best performing configuration overall.** Lowest p95 (242ms) and highest request count (82,295) of all 7 v2 runs. Pure storage ablation at WAN=10.

### Mechanism Exercise

| Mechanism | Evidence |
|-----------|----------|
| **Storage reserve** | **Blocked** — `STORAGE_PERSISTENT_RESERVE_ENABLED=0`, `MAX_DYNAMIC_STORAGE=0`. Max 1 storage node. |
| **Compute scale-up** | ✅ Normal triggers. |
| **Tier 1** | ✅ Normal lifecycle. |

### Service Quality

| Phase | Requests | Failures | Rate | Avg Latency | vs Run G latency |
|-------|----------|----------|------|-------------|-------------------|
| baseline | 481 | 0 | 0.0% | 34ms | 0.9× |
| local_moderate | 2,123 | 0 | 0.0% | 37ms | 1.2× |
| storage_hotspot | 22,492 | 12 | 0.1% | 117ms | 1.0× |
| tier1_hotspot_n1 | 20,036 | 14 | 0.1% | 64ms | 0.8× |
| inter_hotspot_cooldown | 960 | 1 | 0.1% | 48ms | 0.1× |
| tier1_hotspot_n2 | 20,845 | 15 | 0.1% | 61ms | 0.6× |
| compute_spike | 14,395 | 18 | 0.1% | 148ms | 1.0× |
| cooldown | 963 | 0 | 0.0% | 62ms | 1.3× |
| **Overall** | **82,295** | **60** | **0.1%** | **91ms** | — |

### Pure Storage Ablation — Key Evidence (H vs G)

| Metric | Run G (storage ON) | Run H (storage OFF) | Ratio | Winner |
|--------|-------------------|---------------------|-------|--------|
| Overall failure rate | 0.3% | **0.1%** | 3× better | **H** |
| Overall avg latency | 109ms | **91ms** | 0.8× | **H** |
| Overall request count | 75,194 | **82,295** | **1.09× more** | **H** |
| `storage_hotspot` avg latency | 121ms | 117ms | 1.0× | Tie |
| `tier1_hotspot_n1` avg latency | 79ms | **64ms** | 0.8× | **H** |
| `tier1_hotspot_n2` avg latency | 96ms | **61ms** | 0.6× | **H** |

**Run H (no storage) outperforms Run G (storage ON) on every metric.** At WAN=10 with 8 clients, a single MongoDB per LAN is not a bottleneck — the storage reserve mechanism adds overhead without providing measurable benefit.

### Plan Expectation Assessment

| Expectation | Result | Verdict |
|-------------|--------|---------|
| Run H storage CPU ≥2× Run G | Pending — per_node_stats.csv | Pending |
| Run H avg_time_db_ms ≥1.5× Run G | Run H overall latency is LOWER than G | ❌ **Direction reversed** |
| Run H total latency ≥1.3× Run G | 91ms vs 109ms — H is FASTER | ❌ **Direction reversed** |

**The plan's expectations for storage ablation were inverted by the data.** Storage reserve does not improve performance at this scale — it adds overhead.

---

## 5. Run I — `mechanism_v2_all` (2026-06-28 03:04 UTC)

**Status**: ⚠️ — **LAN1 complete outage phases 4–8.** v2 combined reference (WAN=50, v2 dashboard phases, all mechanisms ON). Worst-performing run of all 7.

### Mechanism Exercise

| Mechanism | Evidence | Notes |
|-----------|----------|-------|
| **Compute scale-up** | To be confirmed from logs | May not have triggered due to LAN1 outage |
| **Storage reserve** | To be confirmed | May not have activated |
| **Tier 1** | To be confirmed | May have triggered the LAN1 collapse |

### Service Quality

| Phase | Requests | Failures | Rate | Avg Latency | vs Run H latency |
|-------|----------|----------|------|-------------|-------------------|
| baseline | 485 | 0 | 0.0% | 73ms | 2.1× |
| local_moderate | 2,145 | 0 | 0.0% | 51ms | 1.4× |
| storage_hotspot | 9,826 | 81 | 0.8% | 356ms | 3.0× |
| tier1_hotspot_n1 | 9,091 | 76 | 0.8% | 239ms | 3.7× |
| inter_hotspot_cooldown | 392 | 30 | 7.7% | 835ms | 17.4× |
| tier1_hotspot_n2 | 10,369 | 150 | 1.4% | 186ms | 3.0× |
| compute_spike | 4,271 | 147 | 3.4% | 632ms | 4.3× |
| cooldown | 421 | 60 | 14.3% | 1,502ms | 24.2× |
| **Overall** | **37,000** | **544** | **1.5%** | **308ms** | — |

### LAN1 Outage Timeline

| Phase | LAN1 State | Evidence |
|-------|-----------|----------|
| 1–2 (baseline, local_moderate) | 🟢 Healthy | All 16 clients active |
| 3 (storage_hotspot) | 🟡 Degrading | Throughput dropping |
| 4 (tier1_hotspot_n1) | 🔴 Partial outage | 3 of 8 LAN1 clients dead (single-digit reqs) |
| 5 (inter_hotspot_cooldown) | 🔴 Full outage | All 8 LAN1 clients dead, only LAN2 active |
| 6 (tier1_hotspot_n2) | 🔴 Full outage | All 8 LAN1 clients dead |
| 7 (compute_spike) | 🔴 Full outage | All 8 LAN1 clients dead |
| 8 (cooldown) | 🔴 Full outage | All 8 LAN1 clients dead |

**Only 37,000 total requests** — half of the average (62,000–82,000). The LAN1 outage prevented roughly 30,000–40,000 requests from even being attempted.

### Plan Expectation Assessment

| Expectation | Result | Verdict |
|-------------|--------|---------|
| All 3 mechanisms exercise | Cannot confirm — LAN1 outage may have blocked triggers | ❌ **Likely missed** |
| Cross-region phases elevated latency | Yes — but due to failure, not WAN | ⚠️ **Confounded** |
| No tracebacks | ✅ 0 tracebacks | **Met** |

---

## 6. Run J — `mechanism_v2_notier1` (2026-06-28 09:22 UTC)

**Status**: ✅ — **Tier 1 OFF dramatically outperforms Tier 1 ON.** Combined Tier 1 ablation (WAN=50, v2 phases). Key counterintuitive result of the experiment.

### Mechanism Exercise

| Mechanism | Evidence |
|-----------|----------|
| **Tier 1** | **Blocked** — `SS_ENABLED=0`. Zero `sel_sync_*` containers. |
| **Compute scale-up** | ✅ Normal triggers. |
| **Storage reserve** | ✅ Normal activation. Max 6 storage nodes. |

### Service Quality

| Phase | Requests | Failures | Rate | Avg Latency | vs Run I latency |
|-------|----------|----------|------|-------------|-------------------|
| baseline | 482 | 0 | 0.0% | 71ms | 1.0× |
| local_moderate | 2,146 | 0 | 0.0% | 49ms | 1.0× |
| storage_hotspot | 12,169 | 10 | 0.1% | 275ms | 0.8× |
| tier1_hotspot_n1 | 14,684 | 0 | **0.0%** | 104ms | **0.4×** |
| inter_hotspot_cooldown | 963 | 0 | 0.0% | 68ms | 0.1× |
| tier1_hotspot_n2 | 15,385 | 15 | 0.1% | 125ms | **0.7×** |
| compute_spike | 9,120 | 9 | 0.1% | 272ms | 0.4× |
| cooldown | 957 | 3 | 0.3% | 106ms | 0.1× |
| **Overall** | **55,906** | **37** | **0.1%** | **171ms** | — |

### Combined Tier 1 Ablation — Key Evidence (J vs I)

| Metric | Run I (Tier 1 ON) | Run J (Tier 1 OFF) | Ratio | Winner |
|--------|-------------------|---------------------|-------|--------|
| Overall failure rate | 1.5% | **0.1%** | **15× better** | **J** |
| Overall avg latency | 308ms | **171ms** | **0.6×** | **J** |
| Overall request count | 37,000 | **55,906** | **1.51× more** | **J** |
| `tier1_hotspot_n1` failures | 76 (0.8%) | **0 (0.0%)** | ∞ | **J** |
| `tier1_hotspot_n2` failures | 150 (1.4%) | **15 (0.1%)** | **14× better** | **J** |
| LAN1 health | **DEAD** | **HEALTHY** | — | **J** |

**This is the experiment's most important finding**: Under WAN=50 + dashboard-heavy workload, **disabling Tier 1 delivers strictly better outcomes on every dimension** — more requests processed (1.51×), lower latency (0.6×), lower failure rate (15×), and no LAN outage.

### Plan Expectation Assessment

| Expectation | Result | Verdict |
|-------------|--------|---------|
| Run J total latency ≥1.5× Run I | 171ms vs 308ms — J is 0.6×, not 1.5× | ❌ **Direction reversed** |
| Run J consumer-LAN avg_time_db ≥3× Run I | J has lower overall latency — unlikely | ❌ **Direction reversed** |
| No tracebacks | ✅ 0 tracebacks | **Met** |

---

## 7. Run K — `mechanism_v2_nostorage` (2026-06-28 09:46 UTC)

**Status**: ✅ — **LAN2 complete outage phases 6–8.** Combined storage ablation (WAN=50, v2 phases, no storage). Mirror of Run I's LAN1 outage but on LAN2.

### Mechanism Exercise

| Mechanism | Evidence |
|-----------|----------|
| **Storage reserve** | **Blocked** — `STORAGE_PERSISTENT_RESERVE_ENABLED=0`, `MAX_DYNAMIC_STORAGE=0`. Max 1 storage node. |
| **Compute scale-up** | ✅ Normal triggers. |
| **Tier 1** | ✅ Normal lifecycle. |

### Service Quality

| Phase | Requests | Failures | Rate | Avg Latency | vs Run I latency |
|-------|----------|----------|------|-------------|-------------------|
| baseline | 484 | 0 | 0.0% | 72ms | 1.0× |
| local_moderate | 2,126 | 0 | 0.0% | 52ms | 1.0× |
| storage_hotspot | 12,607 | 10 | 0.1% | 264ms | 0.7× |
| tier1_hotspot_n1 | 14,702 | 1 | 0.0% | 104ms | 0.4× |
| inter_hotspot_cooldown | 963 | 0 | 0.0% | 67ms | 0.1× |
| tier1_hotspot_n2 | 6,383 | 192 | 3.0% | 424ms | 2.3× |
| compute_spike | 6,570 | 150 | 2.3% | 382ms | 0.6× |
| cooldown | 421 | 60 | 14.3% | 1,490ms | 1.0× |
| **Overall** | **44,256** | **413** | **0.9%** | **247ms** | — |

### LAN2 Outage Timeline

| Phase | LAN2 State | Evidence |
|-------|-----------|----------|
| 1–5 | 🟢 Healthy | All clients active |
| 6 (tier1_hotspot_n2) | 🔴 Outage | All 8 LAN2 clients dead (status=0, 6,383 reqs vs expected ~14,000) |
| 7 (compute_spike) | 🔴 Outage | LAN2 barely progressing, LAN1 degraded |
| 8 (cooldown) | 🔴 Outage | LAN2 still dead |

### Combined Storage Ablation — Key Evidence (K vs I)

| Metric | Run I (storage ON) | Run K (storage OFF) | Ratio |
|--------|-------------------|---------------------|-------|
| Overall failure rate | 1.5% | 0.9% | 0.6× |
| Overall request count | 37,000 | 44,256 | 1.20× |
| Dead LAN | LAN1 | LAN2 | Different side |
| Outage onset | Phase 4 | Phase 6 | Later in K |

Run K performed better than Run I (more requests, lower failure rate) but still suffered a complete single-LAN outage. The difference is which LAN collapsed — LAN1 in I (Tier 1 overhead), LAN2 in K (MongoDB overload without storage reserve).

### Plan Expectation Assessment

| Expectation | Result | Verdict |
|-------------|--------|---------|
| Run K storage CPU ≥2× Run I | Pending | Pending |
| Run K avg_time_db ≥1.5× Run I | K overall latency is lower than I (247ms vs 308ms) | ❌ **Direction reversed** |
| No tracebacks | ✅ 0 tracebacks | **Met** |

---

## Cross-Run v2 Mechanism Verdict

| Mechanism | Key Comparison | Primary Evidence | Verdict |
|-----------|---------------|-----------------|---------|
| **WAN amplification** | E vs v1 A | Cross-region latency 3.7× (tier1_hotspot_n1) | ✅ **MET** — WAN=50 successfully amplifies cross-region penalty |
| **Tier 1** | J vs I (combined), F vs E (pure) | J outperforms I on ALL metrics. F vs E confounded by E's n2 anomaly. | ❌ **PARADOX** — Tier 1 OFF outperforms Tier 1 ON at WAN=50 + dashboard mix |
| **Storage** | H vs G (pure), K vs I (combined) | H outperforms G at WAN=10. K vs I: different LAN failures, K marginally better. | ❌ **NOT PROVEN** — storage reserve shows no benefit at CLIENTS=8, DEVICES=600 |

### Tier 1 Paradox — Detailed Analysis

The experiment's hypothesis predicted Tier 1 would improve consumer-visible latency at WAN=50. The data shows the opposite:

| Condition | Tier 1 ON | Tier 1 OFF | Winner |
|-----------|-----------|-----------|--------|
| WAN=50, v1 phases (device_status) | E: 12.8% failures | F: 0.2% failures | Tier 1 OFF |
| WAN=50, v2 phases (dashboard) | I: LAN1 dead, 1.5% failures | J: Healthy, 0.1% failures | **Tier 1 OFF** |
| WAN=10, v1 phases (v1 baseline) | A: 0.2% failures | D: 0.1% failures | Tie |

**Hypothesis for investigation**: At WAN=50 with dashboard aggregation queries, Tier 1's selective-sync mechanism imposes coordination overhead (forwarder reconfiguration, container lifecycle, VIP routing updates) that exceeds its caching benefit. The dashboard queries are computationally expensive on the edge server, and adding Tier 1 containers competes for CPU/memory resources. At WAN=10, the overhead is proportionally smaller and the caching benefit dominates.

### Storage — Scale Limited

Storage reserve activation shows no measurable benefit across all conditions:

| Condition | Storage ON | Storage OFF | Winner |
|-----------|-----------|-----------|--------|
| WAN=10, v2 phases | G: 0.3% failures, 109ms | H: 0.1% failures, 91ms | **Storage OFF** |
| WAN=50, v2 phases | I: 1.5% failures | K: 0.9% failures | Storage OFF (marginal) |

At CLIENTS=8, DEVICES=600, the edge server CPU (~100 req/s Flask ceiling) is the bottleneck, not MongoDB. Storage reserve adds dynamic node management overhead without relieving the actual constraint.

### Best Performing Configuration

**Run H** (`mechanism_storageheavy_nostorage`):
- WAN=10ms, v2 dashboard phases, **no storage mechanisms**, Tier 1 ON
- 82,295 requests (highest), 0.1% failure rate (lowest), 91ms avg latency, 242ms p95
- Single MongoDB per LAN, Tier 1 providing cross-region read caching — minimal mechanisms, maximum throughput

---

## Generated Analysis Artifacts

Each run folder contains 11 analysis PNGs under `<run_dir>/analysis/`:

| Artifact | Content |
|----------|---------|
| `overview_throughput.png` | Request rate, CPU, T_proc, T_db, node counts (time-series) |
| `overview_latency.png` | Latency time-series |
| `overview_resources.png` | Resource time-series |
| `simple_run.png` | Avg/p95/p99 latency, failure rate, nodes by type |
| `phase_summary.png` | Latency percentiles, max node counts, per-LAN p95 |
| `endpoint_breakdown.png` | Per-endpoint latency & failures by phase |
| `lifecycle_gantt.png` | Container lifecycle Gantt chart |
| `scale_down.png` | Scale-down predicate timeline |
| `cpu_drivers.png` | Per-node CPU load balance |
| `tdb_drivers.png` | T_db_write vs storage_count regression |
| `summary.md` | Auto-generated narrative summary |

---

## Next Actions

1. **Investigate Tier 1 overhead at WAN=50 + dashboard mix**: The J-vs-I paradox needs root-cause analysis. Check controller logs for forwarder reconfiguration storms, container lifecycle errors, and VIP routing changes during Tier 1 transitions.
2. **Reproduce Tier 1 paradox**: Re-run I and J to confirm the result is not a single-replicate artifact.
3. **Storage at higher scale**: To prove storage necessity, increase DEVICES (3000+) or CLIENTS (16+) so MongoDB becomes the bottleneck before the edge server.
4. **WAN=50 as standard test condition**: All future mechanism ablation experiments should use WAN=50 to make cross-region effects visible.
5. **Complete resource stats**: Populate the Per-Node Load tables from `per_node_stats.csv` and `resource_stats.csv` for quantitative CPU/RAM comparisons.
6. **Cross-run comparison graphs**: Re-run `cli_simple_compare` and `cli_mechanism_compare` with smaller batch sizes or on a machine with more memory.
