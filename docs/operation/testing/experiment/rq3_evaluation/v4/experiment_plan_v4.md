# Experiment Plan — RQ3 G0-v4 (CPU-Bound compute_spike + Storage Headroom)

**Date**: 2026-07-19 · **Status**: 📋 Designed · **Supersedes**: G0 v3 (20260718) · **Depends on**: [results_v3.md](./results_v3.md)

**Purpose**: Two fixes from v3: (1) `compute_spike` now uses `service_pressure` (a CPU-bound endpoint with NO MongoDB queries) so it actually stresses edge CPU rather than T_db, and (2) both `MAX_DYNAMIC_STORAGE` and `MAX_DYNAMIC_COMPUTE` increased from 5/6→20 to test whether the scoring mechanism self-regulates on both tiers (more nodes → lower load → lower score → scaling stops). Three runs with identical data (DATA_SEED=42) and traffic (RANDOM_SEED=42) to distinguish systematic issues from transient variance.

---

## 0. Prerequisites

| # | Check | How |
|---|-------|-----|
| P1 | compute_spike uses service_pressure | `grep 'service_pressure' source/scripts/testing/phases.json` returns the line |
| P2 | MAX_DYNAMIC_STORAGE=20 | `grep 'MAX_DYNAMIC_STORAGE=20' source/scripts/testing/controller_env_overrides/current_state_integrated.env` |
| P3 | Storage latency-only scoring | `grep 'SCALEUP_W_STORAGE_CPU=0' source/scripts/testing/controller_env_overrides/current_state_integrated.env` |
| P4 | Storage scale-down latency-only | `grep -n 'below = ds.avg_time_db_ms' source/sdn_controller/scaling_policy.py` — line 351 only |
| P5 | No orphan containers | `docker ps -a --format '{{.Names}}' | grep -qE 'edge_' && echo 'ORPHANS' || echo 'Clean'` |
| P6 | seed_content_items.py accepts --data-seed | `grep 'data-seed' source/scripts/testing/seed_content_items.py` — line 568 |
| P7 | seed_user_profiles.py accepts --data-seed | `grep 'data-seed' source/scripts/testing/seed_user_profiles.py` — line 189 |
| P8 | Makefile passes DATA_SEED through | `grep 'data-seed' source/scripts/Makefile` — lines 75, 84 |

---

## 1. Intent

G0-v3 validated storage latency-only scoring (baseline 0.056 vs v2's 0.600) but revealed two problems:

1. **`compute_spike` misnamed**: At 80% feed_ranking + 20% content_lookup, the bottleneck was T_db (3,310ms), not edge CPU (18%). The phase tested MongoDB read throughput, not edge compute scaling. `service_pressure` is a CPU-burn endpoint that operates on an in-memory event buffer — no MongoDB queries at all. This makes it a pure edge-CPU stress test, which is exactly what `compute_spike` should be. At 2 r/s it should properly saturate edge CPU.

2. **LAN2 T_db variance unresolved**: Deep investigation of v3 found LAN2 T_db = 4,664ms vs LAN1's 1,956ms during compute_spike (per-LAN breakdown from `resource_stats.csv`). v2 showed both LANs balanced (1,437ms / 1,525ms). The v3 LAN2 spike could be a transient MongoDB issue (data distribution, replication lag) or run-to-run variance. Three identical runs (same traffic seed, same data seed) will show whether it's reproducible.

---

## 2. Changes from v3

| Parameter | v3 | v4 | Rationale |
|-----------|----|----|-----------|
| compute_spike mix | 80% feed_ranking + 20% content_lookup | **100% service_pressure** | service_pressure is CPU-bound — actually stresses edge CPU |
| compute_spike rate | 0.5 r/s | **2.0 r/s** | CPU-bound endpoint can handle much higher throughput without MongoDB bottleneck |
| MAX_DYNAMIC_STORAGE | 5 | **20** | Headroom for storage scaling; tests self-regulation |
| MAX_DYNAMIC_COMPUTE | 6 | **20** | Headroom for compute scaling; tests self-regulation (same logic as storage) |
| service_pressure window | `window_min=10` | **`window_min=1`** | Steady-state buffer at t=60s → clean pre/post comparison |
| Traffic seed | 42 (single) | **42** (three runs, same seed) | Same traffic patterns across runs |
| Data seed | Uncontrolled (random each run) | **42** (new `--data-seed` arg, same across runs) | Identical content items across runs — data varies per experiment, not per run |
| Storage scoring | Latency-only (W_STORAGE_CPU=0) | Same as v3 | Already validated |
| All other params | WAN=185ms, 0.08/0.25 CPUs | Same as v3 | Proven config |

### Why service_pressure?

| Endpoint | MongoDB queries | CPU work | Bottleneck |
|----------|----------------|----------|------------|
| `feed_ranking` | Heavy (indexed tag queries + ranking over results) | Heavy (ranking algorithm) | **T_db** |
| `content_lookup` | Light (single document fetch) | Light | Neither |
| `service_pressure` | **None** (in-memory event buffer only) | **Heavy (CPU burn on buffer processing)** | **Edge CPU** |

`service_pressure` calls `/service_pressure?window_min=1&limit=10` — it processes an in-memory event buffer with zero MongoDB calls. At 2 r/s × 48 clients = 96 req/s, this should push edge CPU well above the 18% seen with feed_ranking.

**Buffer steady state**: With `window_min=1`, the endpoint looks at the last 60 seconds of requests. At ~48 req/s per edge server, the 1-minute window reaches steady state at t=60s with **2,880 events** — constant for the rest of the phase. This eliminates the buffer-growth confound that would otherwise inflate per-call CPU over time. Pre-scale (seconds 60–90) and post-scale (seconds 150–180) both have the same 2,880 events per call, so H2 measures pure scaling benefit: same work, more servers. If CPU at 2 r/s is too low (<40%), the rate can be increased — 2,880 events at higher throughput still gives steady-state comparison.

### Why MAX_DYNAMIC_STORAGE=20?

v3 showed storage scaling reached 5.7 nodes (near the 5-node cap). With the cap at 20, the system has room to scale further. The scoring mechanism should **self-regulate**:

```
score = sat((T_db − 60) / 250)

T_db = 505ms → score = 1.00  (spawn more)
T_db = 200ms → score = 0.56  (spawn more, but slowing)
T_db = 120ms → score = 0.24  (approaching threshold)
T_db =  80ms → score = 0.08  (below threshold — stop)
```

If more replicas reduce T_db (more read capacity from secondaries), the score drops and scaling stops naturally — **well before the 20 cap**. This is the expected behavior.

If T_db does NOT decrease with more replicas (MongoDB read throughput doesn't scale with replica count for this workload), the score stays at 1.0 and the system spawns to the cap. **This is not a plan failure — it's a finding** about MongoDB read scalability in this architecture.

**⚠️ Resource monitoring**: The 8GB cloud VM can sustain ~14 storage containers (512MB each) before OOM. The 20 cap is a safety ceiling. Monitor `free -h` during storage_storm. If free RAM drops below 512MB, kill the run and reduce the cap to 12. But the expectation is that T_db will drop and scaling will self-limit before reaching 14 nodes.

---

## 3. Hypotheses

| # | Hypothesis | Expected |
|---|-----------|----------|
| H1 | `service_pressure` at 2 r/s pushes edge CPU ≥40% during compute_spike | v3 compute_spike (feed_ranking) hit 18% CPU — service_pressure does zero MongoDB I/O, so CPU should be 2×+ higher at the same rate |
| H2 | Edge CPU drops ≥15pp within compute_spike after compute scale-up | More servers = distributed CPU work = lower per-server CPU. Buffer steady state at t=60s ensures comparable pre/post work per call. |
| H3 | Storage latency-only scoring continues to work (baseline ~0.00, stress ~1.00) | No storage-side changes from v3 |
| H4 | LAN2 T_db variance is run-to-run, not systematic | If all three runs show similar T_db, it's systematic. If variable, it's transient. |
| H5 | Storage scoring self-regulates: T_db drops as replicas increase, score falls below threshold before hitting the cap | Storage node count plateaus at some N < 14 (not hitting OOM limit), with T_db declining as N grows. |
| H6 | Compute scoring self-regulates: edge CPU drops as servers increase, score falls below threshold before hitting the cap | Compute node count plateaus at some N < 20, with per-server CPU declining as N grows. Clean test since service_pressure has no MongoDB dependency. |

---

## 4. Run Matrix

Three identical runs. Same traffic seed + same data seed = identical traffic patterns AND identical content items. `seed_content_items.py` and `seed_user_profiles.py` now accept `--data-seed` (see code changes below). Data varies per experiment, not per run.

| # | Label | Traffic Seed | Data Seed | Purpose |
|---|-------|-------------|-----------|---------|
| v4-r1 | `rq3_g0_v4_r1` | 42 | 42 | First run — direct comparison with v3 |
| v4-r2 | `rq3_g0_v4_r2` | 42 | 42 | Reproducibility — is v3's LAN2 spike repeatable? |
| v4-r3 | `rq3_g0_v4_r3` | 42 | 42 | Confirm pattern — systematic or transient? |

**Order**: r1 first. If r1's compute_spike edge CPU ≥ 40%, proceed to r2. If ≥ 25% but < 40%, increase service_pressure rate to 4 r/s for r2–r3. If < 25%, service_pressure may not be CPU-intensive enough — investigate endpoint before continuing.

---

## 5. Launch Commands

### Code Changes (prerequisite — apply once before r1)

Add `--data-seed` to both seed scripts and wire through the Makefile:

1. **`source/scripts/testing/seed_content_items.py`**: add `random.seed(args.data_seed)` after `args = parser.parse_args()`
2. **`source/scripts/testing/seed_user_profiles.py`**: same change
3. **`source/scripts/Makefile`**: add `--data-seed $(DATA_SEED)` to both `seed_content_items` and `seed_user_profiles` targets

### Run Commands

All runs use the same command, differing only in RUN_LABEL:

```bash
# v4-r1
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=rq3_g0_v4_r1 \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=185 CLIENTS=48 CONTENT_ITEMS=6000 USERS=100 \
  STORAGE_CPUS=0.08 EDGE_CPUS=0.25 \
  STORAGE_MEMORY=512m EDGE_MEMORY=256m \
  RANDOM_SEED=42 DATA_SEED=42 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# v4-r2 (RUN_LABEL=rq3_g0_v4_r2) — same otherwise
# v4-r3 (RUN_LABEL=rq3_g0_v4_r3) — same otherwise
```

**Cleanup between runs** — remove containers, networks, and volumes. Re-seeding with DATA_SEED=42 reproduces identical content:
```bash
sudo -n bash source/scripts/cleanup.sh -v   # -v flag removes edge_storage volumes
# Verify no data carryover:
docker volume ls | grep -q edge_storage && echo 'WARNING: volumes remain' || echo 'Clean'
```

---

## 6. Focus & Evidence

### Primary

| Artifact | What It Shows |
|----------|--------------|
| `resource_stats.csv` | Edge CPU during compute_spike — is it ≥40%? Per-LAN T_db to check LAN2 variance. |
| `policy_state.csv` | Storage score behavior with MAX_DYNAMIC_STORAGE=20 — does scaling go beyond 5 nodes? |
| `client_requests.csv` | compute_spike latency — should be much lower than v3's 3,489ms since no MongoDB bottleneck. |

### Within-Phase Pre/Post

Same method as v2/v3, but with `window_min=1` the buffer reaches steady state at t=60s. Compare seconds 60–90 (pre-scale, 6 windows) vs seconds 150–180 (post-scale, 6 windows). Both have identical 2,880 events per call — pure scaling comparison. Primary focus on edge CPU drop in compute_spike (H2).

### Cross-Run Comparison (r1 vs r2 vs r3) — Composite Stability

| Metric | What to compare |
|--------|----------------|
| compute_spike edge CPU | Mean and pre/post drop — consistent across runs? |
| LAN2 T_db | Mean and p50 — is the v3 4,664ms anomaly reproducible? |
| Storage nodes spawned | Does MAX_DYNAMIC_STORAGE=20 enable more scaling? |
| compute_spike latency | Median and p95 — should be low and consistent |

---

## 7. Success Criteria

| # | Criterion | Target | Measurement |
|---|-----------|--------|-------------|
| S1 | compute_spike edge CPU (full phase) | ≥40% | Mean of `average_cpu_percent` |
| S2 | Within-phase edge CPU drop (compute_spike) | ≥15pp | Pre vs post 6-window means at steady state (seconds 60–90 vs 150–180). Same work per call, different server count. |
| S3 | compute_spike median latency | ≤500ms | CPU-bound, no MongoDB bottleneck expected |
| S4 | System stability | Success ≥90% in EACH individual phase | Phase-by-phase check — a single phase < 90% fails |
| S5 | Storage score baseline < 0.10 | <0.10 | Mean of `storage_score` in baseline phase |
| S6 | Storage scaling self-regulates | Peak `dynamic_storage_count` reaches some N > 5 then plateaus (growth rate < 0.5 nodes/window for last 6 windows of stress phase), with T_db declining as N grows | Evidence of the scoring feedback loop — more nodes → lower T_db → lower score |
| S7 | Compute scaling self-regulates | Peak `dynamic_compute_count` reaches some N > 2 then plateaus (growth rate < 0.5 nodes/window for last 6 windows of compute_spike), with per-server CPU declining as N grows | Same feedback loop on the compute side — more servers → lower CPU → lower score |

---

## 8. Decision Tree

### Per-Run (applied to r1 first)

| Condition | Action |
|-----------|--------|
| S1 ≥ 40%, S2 ≥ 15pp, S3 ≤ 500ms | ✅ compute_spike fixed. Continue to next run. |
| S1 ≥ 40% but S2 < 15pp | ⚠️ CPU level OK but drop insufficient — scaling may be too slow or ineffective. H2 is not a hard gate. Continue to next run but note in analysis. |
| S1 ≥ 25% but < 40% | ⚠️ Marginal CPU. Increase service_pressure rate to 4 r/s for remaining runs. |
| S1 < 25% | ❌ service_pressure not CPU-intensive enough. Investigate endpoint before continuing. |

### Cross-Run (after all 3 complete)

| Condition | Action |
|-----------|--------|
| Storage node count plateaus at N < 14 with declining T_db | ✅ Storage scoring self-regulates (H5). Confirmed. |
| Storage node count reaches cap (20) without OOM, T_db stays high | Finding: MongoDB read throughput doesn't scale with replica count for this workload. |
| Compute node count plateaus at N < 20 with declining per-server CPU | ✅ Compute scoring self-regulates (H6). Confirmed. |
| Compute node count reaches cap (20), per-server CPU stays high | Finding: compute scaling doesn't reduce per-server CPU for this workload. |
| LAN2 T_db consistent across all 3 runs (within ±20%) | Flag as systematic — investigate MongoDB data distribution or infrastructure. |
| LAN2 T_db varies widely across runs (>50% range) | Confirmed transient — v3's LAN2 spike was a one-off. Proceed to RQ3 with v4 config. |
| At least 1 run OOMs or hits >16 storage nodes with free RAM < 512MB | Reduce MAX_DYNAMIC_STORAGE to 12, rerun that run. |

---

## 9. Validity Threats

| Threat | Severity | Mitigation |
|--------|----------|------------|
| `service_pressure` with `window_min=1` may produce lower absolute CPU than `window_min=10` (2,880 events vs 8,900). May not reach the 40% H1 target at 2 r/s. | ⚠️ Low | Decision tree handles this: if CPU < 40% but ≥ 25%, increase rate to 4 r/s. At 4 r/s, steady-state window = 5,760 events — close to original workload. |
| MAX_DYNAMIC_STORAGE=20: if T_db is insensitive to replica count, system spawns to cap. At 512MB/node, ~14 nodes exhaust 8GB VM RAM. | ⚠️ Medium | This is the experiment's key question (H5). Monitor `free -h` during storage_storm. If free RAM < 512MB, kill run and reduce cap to 12. If system reaches 20 without OOM, that itself is a finding. |
| 3 runs × ~20 min = ~1h, VM stability over time | Low | Run back-to-back, verify no orphan containers between runs. |
| WAN RTT 185ms fixed (not swept) | Low | Matches v2/v3 — keeps baseline comparable. |
| feed_ranking is described as "heavy" in the comparison table but uses indexed queries (not full collection scans) | Low | Description corrected to "indexed tag queries + ranking over results." |

---

## 10. Artifact Contract

Standard layout plus cross-run comparison:

```
source/scripts/testing/metrics/<timestamp>_rq3_g0_v4_r1/
source/scripts/testing/metrics/<timestamp>_rq3_g0_v4_r2/
source/scripts/testing/metrics/<timestamp>_rq3_g0_v4_r3/
```

Post-run: `results_v4.md` with within-phase pre/post analysis for each run, plus cross-run LAN2 T_db comparison table.
