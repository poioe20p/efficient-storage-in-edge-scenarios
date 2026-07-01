# Results — v5 Resource-Constrained Mechanism Necessity

**Date**: 2026-06-29
**Experiment plan**: [experiment_plan_v5_calibration.md](./experiment_plan_v5_calibration.md)
**Depends on**: [v4 results](results_v4.md)
**Configuration**: WAN=160ms | Storage `--cpus=0.15 --memory=512m` | Edge `--cpus=0.30 --memory=256m` | WiredTiger cache=0.25GB

---

## Run Timeline

| Run | Date | Status | Total Req | Success | Key Finding |
|-----|------|--------|-----------|---------|-------------|
| v5 A (`mechanism_v5_all`) | 2026-06-29 12:02 | ✅ | 27,567 | 95.6% | All mechanisms active. Storage CPU 20.9%, Edge CPU 29.2%. |
| v5 B (`mechanism_v5_notier1`) | 2026-06-29 12:34 | ✅ | 26,482 | 96.3% | Tier 1 impact modest at WAN=160ms (−4% throughput). |
| v5 C (`mechanism_v5_nostorage`) | 2026-06-29 13:04 | ✅ | 27,166 | 95.8% | Single MongoDB handles load. Storage CPU 27.3% (vs 20.9% distributed). |
| v5 D (`mechanism_v5_nocompute`) | 2026-06-29 13:35 | ⚠️ | **18,331** | 94.9% | **Massive 34% throughput collapse**. Edge CPU 50.7%. |

---

## Cross-Run Summary

| Run | Total | OK% | StorCPU | EdgeCPU | Peak Srv | Peak Stor | BaseMed | StormMed | Tier1Med | SpikeMed |
|-----|-------|-----|---------|---------|----------|-----------|---------|----------|----------|----------|
| A (all on) | 27,567 | 95.6% | 20.9% | 29.2% | 5 | 7 | 24ms | 95ms | 2257ms | 2443ms |
| B (no Tier 1) | 26,482 | 96.3% | 18.4% | 29.3% | 4 | 7 | 23ms | **77ms** | 2326ms | **1590ms** |
| C (no storage) | 27,166 | 95.8% | **27.3%** | 30.9% | 4 | **2** | 19ms | **44ms** | **3084ms** | **1737ms** |
| D (no compute) | **18,331** | 94.9% | 15.3% | **50.7%** | **1** | 7 | 24ms | 47ms | **7915ms** | **8505ms** |

### Mechanism Impact (Δ vs Run A)

| Ablation | Throughput Δ | OK Δ | StorCPU Δ | EdgeCPU Δ | StormLat Δ | SpikeLat Δ | Tier1Lat Δ |
|----------|-------------|------|-----------|-----------|------------|------------|------------|
| No Tier 1 | −3.9% | +0.7pp | −2.5% | +0.1% | **−19%** | **−35%** | +3% |
| No storage | −1.5% | +0.2pp | **+6.4%** | +1.8% | **−54%** | **−29%** | **+37%** |
| **No compute** | **−33.5%** | −0.7pp | −5.6% | **+21.5%** | −51% | **+248%** | **+251%** |

---

## 1. Run A — `mechanism_v5_all` (Reference)

**Status**: ✅ — All 3 mechanisms exercised. 95.6% success. 73 node lifecycle events.

### Per-Phase Resources

| Phase | Storage CPU | Edge CPU | Servers | Storage Nodes |
|-------|------------|----------|---------|---------------|
| baseline | 10.6% | 33.4% | 1–2 | 5–7 |
| storage_storm | **20.9%** | 12.1% | 1–4 | 5–7 |
| tier1_hotspot | 8.9% | 7.3% | 0–5 | 5–7 |
| inter_hotspot_cooldown | 9.2% | 8.3% | 0–4 | 3–7 |
| compute_spike | 10.1% | **29.2%** | 1–4 | 4–7 |
| cooldown | 8.9% | 10.7% | 1–3 | 4–7 |

- **Storage CPU reached 20.9%** in `storage_storm` — 30× higher than v4's 0.7%. Target achieved.
- **Edge CPU reached 33.4%** in baseline — 11× higher than v4's 2.9%. Target achieved.
- **5 edge servers, 7 storage nodes** at peak. Elasticity actively distributing load.
- Per-node CPU drop on scale-out clearly visible: edge CPU 33%→12% (3 servers added).

---

## 2. Run B — `mechanism_v5_notier1` (Tier 1 Ablation)

**Status**: ✅ — Tier 1 impact is **within noise floor** at WAN=160ms. Signal too small to interpret reliably.

### Key Finding: Tier 1 Effect Undetectable at WAN=160ms

Without Tier 1:
- Throughput: 26,482 vs 27,567 (−3.9%) — a ~4% difference in a single-replicate experiment
- Success rate: 96.3% vs 95.6% (+0.7pp) — B is marginally better but within noise
- **tier1_hotspot latency**: B median=2326ms vs A=2257ms (+3%) — the target-phase benefit is only 69ms
- **storage_storm latency**: B median=77ms vs A=95ms (−19%)
- **compute_spike latency**: B median=1590ms vs A=2443ms (−35%)

**Why the non-tier1 latency differences are likely noise, not overhead**:

The Tier 1 `sel_sync_*` containers (`edge_selective_storage` image) are spawned **without `--cpus` or `--memory` Docker limits** (`source/sdn_controller/elasticity/selective_storage_manager.py` line ~265–290). Unlike `edge_server` (`--cpus=0.30`) and storage (`--cpus=0.15`), Tier 1 containers have access to the host's full CPU. They do NOT compete with edge_server for constrained CPU shares. The 19–35% latency differences in non-tier1 phases are therefore unlikely to be caused by Tier 1 resource competition.

More plausible explanations:
1. **Random variance**: Single-replicate experiment. Host CPU scheduling jitter, network variance, or slightly different container start times could produce these differences.
2. **Request mix differences**: B processed MORE requests in compute_spike (5,128 vs 4,686) — if the extra requests were faster (more `device_status` vs `dashboard`), the median shifts lower.
3. **Phase timing**: Slightly different phase start/end times relative to elasticity events could shift the request profile.

**The honest conclusion**: At WAN=160ms, Tier 1's effect (−3.9% throughput, +3% tier1_hotspot latency) is too small to distinguish from noise in a single-replicate experiment. This does NOT mean Tier 1 is useless — at WAN=300ms (v4) it produced an unambiguous 18% throughput gain and 45× median latency improvement. But at moderate WAN latency, the caching benefit shrinks toward the noise floor.

**Architectural note**: `sel_sync_*` containers have **no CPU/memory limits**, unlike the constrained edge_server and storage containers. This is a deliberate design choice (selective-sync is I/O-bound, not CPU-bound), but it means the v5 experiment cannot test whether Tier 1 would benefit from or be harmed by CPU limits.

---

## 3. Run C — `mechanism_v5_nostorage` (Storage Ablation)

**Status**: ✅ — Single MongoDB handles workload comfortably. Storage necessity remains unproven.

### Key Finding: Storage CPU Too Low to Demonstrate Necessity

With `MAX_DYNAMIC_STORAGE=0`:
- Storage nodes fixed at 1–2 (vs 5–7 in Run A)
- **Storage CPU reached 27.3%** in `storage_storm` — only +6.4pp above Run A's 20.9%
- **Target is 60%+** pre-scale storage CPU to show a dramatic benefit from scaling. At 27.3%, the single MongoDB is comfortable — not saturated.
- Throughput essentially unchanged (27,166 vs 27,567, −1.5%)

**Latency observations** (single-replicate — treat with caution):
- **storage_storm**: C median=44ms vs A=95ms (−54%) — directionally consistent with replication overhead (writes complete faster against a single primary without waiting for replica-set write concern)
- **tier1_hotspot**: C median=3084ms vs A=2257ms (+37%) — directionally consistent with missing local replicas (cross-region reads MUST go across WAN)
- **compute_spike**: C median=1737ms vs A=2443ms (−29%) — unclear cause, may be noise

**Why storage necessity remains unproven**: At `--cpus=0.15`, MongoDB operates at only 21–27% CPU. To reach the user's target of 60%+ (where scaling would produce a dramatic 30+pp per-node drop), storage CPUs would need to be ~0.05 — below what MongoDB/WiredTiger can function with (0.25GB cache minimum already establishe1d). The workload itself (DEVICES=6000, device_status writes + dashboard aggregations) is simply too light for modern MongoDB.

**Consistent finding across all 5 experiment generations**: Storage elasticity does not provide measurable throughput benefit at this workload scale. MongoDB is efficient enough that a single node handles the load. Storage distribution may matter at larger scales (DEVICES=60K+, complex `$lookup` aggregations) or under different failure modes (node loss), but at the current experiment scale it cannot be shown to be necessary.

---

## 4. Run D — `mechanism_v5_nocompute` (Compute Ablation)

**Status**: ⚠️ — **Massive 34% throughput collapse**. Single edge server saturated at 50.7% CPU.

### Key Finding: Compute is THE Dominant Mechanism at Constrained Resources

With `MAX_DYNAMIC_COMPUTE=0`:
- **Throughput collapsed to 18,331** (vs 27,567 in Run A) — **−33.5%**
- **Edge CPU hit 50.7%** in `compute_spike` (vs 29.2% in Run A) — **+21.5pp**
- **Edge CPU hit 43.1%** even in `baseline` (vs 33.4% in A)
- Single edge server per LAN cannot handle the load at `--cpus=0.30`
- Storage CPU dropped to 15.3% (vs 20.9% in A) — less work reaches MongoDB because edge servers are saturated

| Phase | Run A Edge CPU | Run D Edge CPU | Δ |
|-------|---------------|---------------|-----|
| baseline | 33.4% | **43.1%** | +9.7pp |
| storage_storm | 12.1% | **25.3%** | +13.2pp |
| compute_spike | 29.2% | **50.7%** | +21.5pp |

The compute_spike phase in D processed only 2,949 requests (vs 4,686 in A) — the edge server couldn't accept requests fast enough. This is the definitive compute necessity proof that v4 couldn't produce at WAN=300ms (where WAN was the bottleneck, not CPU).

---

## v5 Cross-Run Mechanism Verdict

| Mechanism | Ablation | Primary Evidence | v5 Verdict | v4 Verdict |
|-----------|----------|-----------------|------------|------------|
| **Compute** | D vs A | Throughput −34%, Edge CPU +22pp, SpikeLat +248% | ✅ **NECESSARY** | ⚠️ Marginal |
| **Tier 1** | B vs A | Throughput −4%, Tier1Lat +3% — within noise floor | ⚠️ **INCONCLUSIVE** | ✅ Dominant |
| **Storage** | C vs A | Throughput −1.5%, StorCPU +6pp — single node comfortable at 27% | ❌ **NOT PROVEN** | ❌ Not needed |

### Complete Reversal from v4

| Aspect | v4 (WAN=300ms) | v5 (WAN=160ms, constrained) |
|--------|----------------|---------------------------|
| Dominant constraint | WAN RTT at maxPoolSize=1 | **Edge CPU at --cpus=0.30** |
| Tier 1 benefit | 18% throughput, 45× median | **~4% throughput — within noise floor** |
| Storage CPU | 0.7% (invisible) | **21%** — improved but still below 60%+ target |
| Compute benefit | 2% throughput (marginal) | **34% throughput** (dominant), SpikeLat +248% |
| Failure rate | 43–51% | **4–5%** |
| Throughput vs expected | 12% | **~25%** |

**The resource constraints succeeded for compute**: Limiting edge_server to 0.30 CPUs shifted the bottleneck from WAN to compute CPU, demonstrating compute elasticity as necessary with a 34% throughput benefit.

**The resource constraints were insufficient for storage**: At 0.15 CPUs, MongoDB reaches only 21% CPU — far below the 60%+ target where scaling would show a dramatic per-node drop. The workload is simply too light for modern MongoDB at any CPU allocation that allows WiredTiger to function (0.25GB cache minimum).

**Tier 1 effect is WAN-dependent**: At 300ms (v4), Tier 1 provides an unambiguous 18% throughput gain. At 160ms (v5), the effect shrinks to ~4% — indistinguishable from noise in a single-replicate experiment. The `sel_sync_*` containers have NO CPU limits (unlike edge_server and storage), so they do not compete for constrained resources. This is a latency-dependent mechanism, not a CPU-dependent one.

---

## Per-Run Detailed Analysis

### Run A — Resource Utilization by Phase

| Phase | StorCPU | EdgeCPU | Srv | Stor | Requests |
|-------|---------|---------|-----|------|----------|
| baseline | 10.6% | 33.4% | 1–2 | 5–7 | 2,338 |
| storage_storm | 20.9% | 12.1% | 1–4 | 5–7 | 11,550 |
| tier1_hotspot | 8.9% | 7.3% | 0–5 | 5–7 | 5,597 |
| inter_hotspot_cooldown | 9.2% | 8.3% | 0–4 | 3–7 | 2,323 |
| compute_spike | 10.1% | 29.2% | 1–4 | 4–7 | 4,686 |
| cooldown | 8.9% | 10.7% | 1–3 | 4–7 | 1,073 |

### Run B — Resource Utilization by Phase

| Phase | StorCPU | EdgeCPU | Srv | Stor | Requests |
|-------|---------|---------|-----|------|----------|
| baseline | 12.3% | 39.4% | 1–2 | 4–7 | 2,397 |
| storage_storm | 18.4% | 17.1% | 1–4 | 4–7 | 10,259 |
| tier1_hotspot | 8.8% | 10.0% | 1–4 | 5–7 | 5,048 |
| inter_hotspot_cooldown | 9.4% | 8.8% | 1–4 | 3–7 | 2,595 |
| compute_spike | 11.3% | 29.3% | 1–4 | 3–7 | 5,128 |
| cooldown | 8.6% | 11.1% | 1–3 | 4–7 | 1,055 |

### Run C — Resource Utilization by Phase

| Phase | StorCPU | EdgeCPU | Srv | Stor | Requests |
|-------|---------|---------|-----|------|----------|
| baseline | 22.6% | 43.2% | 1–2 | 1 | 2,380 |
| storage_storm | 27.3% | 10.8% | 1–4 | 1–2 | 10,705 |
| tier1_hotspot | 15.2% | 7.0% | 3–4 | 1 | 4,736 |
| inter_hotspot_cooldown | 12.4% | 12.4% | 1–4 | 1 | 2,649 |
| compute_spike | 32.9% | 30.9% | 1–4 | 1 | 5,635 |
| cooldown | 12.6% | 13.9% | 1–2 | 1 | 1,061 |

> **Note**: Storage CPU reached 32.9% in `compute_spike` — the single MongoDB primary is under real load. But throughput was not affected (5,635 requests vs 4,686 in Run A for compute_spike). MongoDB handles the load; the bottleneck is elsewhere.

### Run D — Resource Utilization by Phase

| Phase | StorCPU | EdgeCPU | Srv | Stor | Requests |
|-------|---------|---------|-----|------|----------|
| baseline | 10.4% | 43.1% | 1 | 5–7 | 2,317 |
| storage_storm | 15.3% | 25.3% | 1 | 5–7 | 6,728 |
| tier1_hotspot | 9.3% | 18.5% | 1 | 5–7 | 2,733 |
| inter_hotspot_cooldown | 9.6% | 24.7% | 1 | 4–7 | 2,613 |
| compute_spike | 10.3% | **50.7%** | 1 | 4–6 | **2,949** |
| cooldown | 9.3% | 22.6% | 1 | 4–6 | 991 |

> **Critical**: `compute_spike` processed only 2,949 requests in Run D vs 4,686 in Run A (−37%). The single edge server at `--cpus=0.30` was completely saturated at 50.7% CPU. This is the compute necessity proof.

---

## Node Lifecycle Activity

| Run | Node Timings | Elasticity Events | Dynamic Pattern |
|-----|-------------|-------------------|-----------------|
| A (all on) | 73 | 437 | Heavy compute + storage scaling |
| B (no Tier 1) | 82 | 466 | Even more scaling to compensate |
| C (no storage) | 32 | 316 | Compute-only scaling (no storage nodes) |
| D (no compute) | 39 | 46 | Storage-only scaling (no edge servers) |

- **82 node timings in Run B** is the highest — without Tier 1, the system compensates with more aggressive compute/storage scaling
- **32 node timings in Run C** — confirms no storage nodes were added (compute-only)
- **39 node timings in Run D** — storage nodes still scaled, but no edge servers added

---

## Comparison with v4

| Aspect | v4 (WAN=300ms, unlimited) | v5 (WAN=160ms, constrained) |
|--------|---------------------------|----------------------------|
| Storage CPU in storm | 0.7% | **20.9%** (30×) |
| Edge CPU in spike | 2.9% | **29.2%** (10×) |
| Compute benefit | 2% throughput | **34% throughput** |
| Tier 1 benefit | 18% throughput, 45× median | 4% throughput |
| Storage benefit | 0% | 1.5% throughput |
| Success rate | 57% | **96%** |
| Node timings | 35 | **73** (2.1×) |
| Dominant mechanism | Tier 1 | **Compute** |

The resource constraints achieved exactly what they were designed for: shifting the bottleneck from WAN to compute CPU, making compute elasticity the dominant and necessary mechanism.

---

## Limitations

1. **Tier 1 effect within noise floor at WAN=160ms**: The `sel_sync_*` containers have NO Docker resource limits (unlike edge_server `--cpus=0.30` and storage `--cpus=0.15`). They do NOT compete for constrained CPU. The latency differences between B and A in non-tier1 phases (StormLat −19%, SpikeLat −35%) are most likely random variance from a single-replicate experiment, not Tier 1 overhead. Tier 1's effect at WAN=160ms is too small to distinguish from noise — unlike v4 at WAN=300ms where it produced an unambiguous 18% throughput gain and 45× median latency improvement.
2. **Storage CPU (20–27%) too low to prove necessity**: The user's target is 60%+ pre-scale storage CPU to show a dramatic scaling benefit. At 0.15 CPUs, MongoDB operates at only 21% CPU under storage_storm — the 6.4pp concentration effect when storage is ablated is real but small. A single MongoDB handles the workload comfortably. Storage necessity remains unproven at this scale, consistent with v1–v4 findings.
3. **Single replicate per condition**: Each ablation ran once. The 34% compute throughput drop is large enough to be significant, but the 4% Tier 1 throughput drop and 3% Tier1Lat difference may have stochastic components.
3. **Storage replication overhead not isolated**: The 54% write latency improvement without replication (C vs A) may be partly an artifact of replica-set churn during the experiment. A controlled test with fixed replica-set topology would isolate the pure replication overhead.
4. **WAN bottleneck still present**: At maxPoolSize=1 with 160ms RTT, per-client throughput is capped at ~6.25 req/s. This still limits total system throughput, but compute now saturates before WAN does.
5. **`p95_time_db_ms` unavailable**: The telemetry collector does not populate this column in v5 runs. All DB-time analysis uses `avg_time_db_ms` from resource_stats.csv where available, but this was not collected in the simplified v5 CSVs.
6. **Tier 1 container resource model**: `sel_sync_*` containers (`edge_selective_storage` image) are spawned WITHOUT `--cpus` or `--memory` Docker limits, unlike edge_server (`--cpus=0.30`) and storage (`--cpus=0.15`). This asymmetry means Tier 1 containers have access to the host's full CPU — a deliberate design choice since selective-sync is I/O-bound (oplog tailing). However, it also means v5 cannot test whether Tier 1 would benefit from or be harmed by CPU limits. The v2 Tier 1 paradox (ON worse than OFF at WAN=50) may have a different root cause than CPU competition.

---

## Recommendations

1. **For thesis**: The v4+v5 results together tell a complete story — mechanism necessity is **context-dependent**. Tier 1 dominates at high WAN latency (v4: 300ms); its effect shrinks into the noise floor at moderate WAN (v5: 160ms). Compute dominates under CPU constraints regardless of WAN. Storage necessity cannot be demonstrated at this workload scale with any viable CPU limit — MongoDB is too efficient. This multi-generational, multi-configuration evidence is a stronger thesis contribution than claiming any single mechanism is always necessary.

2. **Storage at higher scale or abandon**: To reach 60%+ storage CPU, either increase DEVICES to 60K+ with `$lookup` aggregations, or accept that storage elasticity's value is capacity headroom and fault tolerance — not latency/throughput improvement at current scale. v1–v5 consistently show storage is not a bottleneck.

3. **Tier 1 WAN-dependence curve**: Characterize the Tier 1 benefit curve across WAN latencies (10ms, 50ms, 100ms, 160ms, 300ms). v4 (300ms) and v5 (160ms) are two points. The full curve would identify the crossover point where Tier 1 transitions from dominant to negligible — this is the key deployment guidance.

4. **maxPoolSize × WAN interaction**: The interaction between WAN latency, connection pool size, and mechanism necessity is the key insight. A follow-up experiment varying maxPoolSize (1, 5, 10) at different WAN latencies would characterize this interaction space.

5. **Apply CPU limits to sel_sync containers**: For a fair resource-constrained comparison, `sel_sync_*` containers should get the same `--cpus`/`--memory` limits as storage containers. Currently they run unlimited while edge_server and storage are constrained — an asymmetry that confounds the resource competition analysis.
