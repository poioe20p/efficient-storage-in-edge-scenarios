# Experiment Plan v6 — Tier 1 WAN Curve + Storage Necessity Amplification

**Date**: 2026-06-29
**Status**: ✅ Approved (2026-06-29) — execution pending
**Depends on**: [v5 calibration plan](experiment_plan_v5_calibration.md) and [v5 results](results_v5.md)
**Purpose**: (1) Map Tier 1 benefit across WAN=200/230/260ms to find the crossover from inconclusive→dominant. (2) Push storage resource limits + load until single-MongoDB saturation proves storage elasticity necessary.

---

## v6-T1 — Tier 1 WAN-Dependence Curve

**Goal**: Find the WAN latency where Tier 1 transitions from within-noise-floor (v5, 160ms, ~4% throughput) to clearly beneficial (v4, 300ms, 18% throughput).

**Design**: At each WAN ∈ {200, 230, 260} ms, run Tier 1 ON vs OFF. All other mechanisms active. Single replicate unless 200ms shows ≤5% throughput difference → escalate to 2 replicates for that WAN (T1-B fallback).

**Fixed**: Storage `--cpus=0.15 --memory=512m`, Edge `--cpus=0.30 --memory=256m`, DEVICES=6000, CLIENTS=48, v4 6-phase workload.

### v6-T1 Run Matrix

| # | Label | WAN (ms) | SS_ENABLED | Env Override | Per-client cap |
|---|-------|----------|------------|-------------|----------------|
| T1 | `v6_t1_wan200_on` | 200 | 1 | `mechanism_necessity_all.env` | 5.0 req/s |
| T2 | `v6_t1_wan200_off` | 200 | 0 | `mechanism_necessity_notier1.env` | 5.0 req/s |
| T3 | `v6_t1_wan230_on` | 230 | 1 | `mechanism_necessity_all.env` | 4.3 req/s |
| T4 | `v6_t1_wan230_off` | 230 | 0 | `mechanism_necessity_notier1.env` | 4.3 req/s |
| T5 | `v6_t1_wan260_on` | 260 | 1 | `mechanism_necessity_all.env` | 3.8 req/s |
| T6 | `v6_t1_wan260_off` | 260 | 0 | `mechanism_necessity_notier1.env` | 3.8 req/s |

**Per-client cap logic**: Caps assume synchronous clients — maxPoolSize=1 means one in-flight request per client at a time. Each request takes ≥ WAN_RTT to complete, so max throughput = 1 / WAN_RTT. 200ms → 5.0 req/s, 230ms → 4.3 req/s, 260ms → 3.8 req/s. Actual throughput will be at or below these caps. The workload's peak rates (storage_storm=4 r/s, tier1_hotspot=5 r/s) are at or above the cap at 200+ms.

**Why higher WAN amplifies Tier 1 benefit (not masks it)**: Without Tier 1, a cross-region read takes `WAN_RTT + remote_DB_time` (e.g., 260 + 50 = 310ms → max 3.2 req/s). With Tier 1, it takes `LAN_RTT + local_cache_time` (e.g., 10 + 5 = 15ms → max 66 req/s, limited by client rate to 5 req/s). As WAN increases, the OFF throughput drops while ON throughput stays at the client target rate. The throughput ratio ON/OFF **increases monotonically with WAN** — 260ms should show the largest Δ.

### v6-T1 Success Criterion

| # | Metric | Target |
|---|--------|--------|
| 1 | Latency improvement with Tier 1 ON vs OFF | **≥2× faster** (median latency ON ≤ 50% of OFF) in cross-region phases (`tier1_hotspot`, `storage_storm`) |
| 2 | Throughput ON ≥ OFF | Direction correct (ON not worse) |
| 3 | No LAN outages, no controller tracebacks | System stability |

At 200–260ms WAN, Tier 1 eliminates the WAN round-trip for cached cross-region reads (260ms → ~10ms). The expected latency reduction is substantial — well above the 2× threshold.

**Fallback (T1-B)**: If any WAN shows <2× latency improvement, add 1 replicate for that WAN pair. Maximum 10 runs (6 base + up to 4 extra).

---

## v6-ST — Storage Scaling Distribution Effect

**Goal**: Find a CPU limit + DEVICES combination where storage scale-out produces a **~20 percentage-point drop in average storage CPU across the cluster** (e.g., 40% pre-scale → 20% post-scale). The absolute CPU level is secondary — the distribution effect is what matters.

**Design**: Combined calibration matrix (ST-C) testing CPU × DEVICES simultaneously. Once a config shows a clear ~20pp drop within a single run (pre-scale vs post-scale in `storage_storm`), that run is the winner. No separate ablation needed — the evidence is the within-run scaling benefit.

**Fixed**: WAN=160ms, Edge `--cpus=0.30 --memory=256m`, CLIENTS=48, v4 6-phase workload, WiredTiger cache=0.25GB (minimum). All mechanisms ON (including storage elasticity).

### v6-ST Calibration Matrix (ST-C)

| # | Label | Storage CPUs | DEVICES | Expected StorCPU | Risk |
|---|-------|-------------|---------|------------------|------|
| S1 | `v6_st_cal_s1_cpu012` | 0.12 | 6000 | 21–28% | Low — small step from known 0.15→21% |
| S2 | `v6_st_cal_s2_cpu010` | 0.10 | 6000 | 26–34% | Medium — 0.10 was "unstable" at 256m in C3; now at 512m memory |
| S3 | `v6_st_cal_s3_cpu012` | 0.12 | 12000 | 28–38% | Low-Medium — 2× data ≈ 1.3× CPU (indexes fit in cache) |
| S4 | `v6_st_cal_s4_cpu010` | 0.10 | 12000 | 32–45% | Medium — tight CPU + larger dataset |
| S5 | `v6_st_cal_s5_cpu008` | 0.08 | 12000 | 38–55% | High — 0.08 may be below WiredTiger functional floor |
| S6 | `v6_st_cal_s6_cpu010` | 0.10 | 18000 | 35–50% | Medium-High — 3× data, watch memory: if avg_storage_memory_mb > 450, flag |

> **CPU extrapolation**: S1–S2 use linear scaling from v5 baseline (20.9% at 0.15 CPUs). S3–S6 use sub-linear DEVICES scaling — doubling data does not double CPU because indexes and working set fit in WiredTiger cache. S6 may hit the 512m memory ceiling before CPU saturates; monitor `avg_storage_memory_mb` in resource_stats.csv.

**Early termination**: Stop calibration when a run shows a **~20pp drop in average storage CPU** between pre-scale (first 60s of `storage_storm`) and post-scale (after scale-up stabilizes). The pre-scale average CPU should be ≥30% so the drop is clearly above noise. System must be stable (no OOM, success ≥85%).

**Measurement** (uses `avg_storage_cpu_percent` from `resource_stats.csv` — already the mean across all storage nodes in the cluster):
1. Pre-scale = mean of `avg_storage_cpu_percent` for rows where `phase=storage_storm AND relative_time ≤ 60s`
2. Post-scale CPU = mean `avg_storage_cpu_percent` for rows where `phase=storage_storm AND relative_time ≥ 150s` (after scale-up fully stabilized)
3. Drop = pre-scale − post-scale. Target: **≥20pp**.

> **Why 60s pre-scale / 150s post-scale**: `SCALEUP_STORAGE_COOLDOWN_S=60` prevents first alert before T+60s. With `REQUIRED=2` of `WINDOW_SIZE=5` (10s windows), earliest trigger is T+80s. Scale-up (docker run + RS join + data sync) takes 30–90s. The 150s+ window ensures the new node is serving reads. If a run shows a borderline drop (17–19pp), re-measure with a 180s+ window before rejecting.

### v6-ST Success Criterion

| # | Metric | Target |
|---|--------|--------|
| 1 | Average storage CPU drop (pre-scale − post-scale) | **≥20pp** within `storage_storm` phase |
| 2 | System stability | No OOM kills, success ≥85% |

No ablation run needed — the within-run scaling benefit is the evidence.

---

## Code Changes

### 1. `source/scripts/network/build_network_1.sh` — ✅ ALREADY APPLIED

Env-var defaults and debug echo are already in place. **Verify** before first run:
```bash
grep -n 'STORAGE_CPUS\|EDGE_CPUS\|\[v6\]' source/scripts/network/build_network_1.sh
```
Expected: `${STORAGE_CPUS:-0.15}`, `${EDGE_CPUS:-0.30}`, `[v6]` debug echo.

### 2. `source/scripts/network/build_network_2.sh` — ✅ ALREADY APPLIED

Same. Verify with the same grep. No edit needed.

### 3. `source/sdn_controller/elasticity/storage_node_manager.py` — ✅ ALREADY APPLIED

Hardcoded `"--cpus", "0.15"` replaced with `os.environ.get("STORAGE_CPUS", "0.15")`. Reads from `STORAGE_CPUS` env var — same value passed on the make command line. No per-run manual edit needed.

**Verify**:
```bash
grep -n 'STORAGE_CPUS' source/sdn_controller/elasticity/storage_node_manager.py
```
Expected: `storage_cpus = os.environ.get("STORAGE_CPUS", "0.15")`

### 4. `source/sdn_controller/elasticity/compute_node_manager.py` — ✅ ALREADY APPLIED

Hardcoded `"--cpus", "0.30"` replaced with `os.environ.get("EDGE_CPUS", "0.30")` for consistency. v6 does not vary edge CPU, but this prevents future fragility.

### 5. `source/scripts/build_network_setup.sh` — ✅ ALREADY APPLIED

Both osken container launches now include `-e STORAGE_CPUS="${STORAGE_CPUS:-0.15}"` and `-e EDGE_CPUS="${EDGE_CPUS:-0.30}"`. This bridges the Docker boundary — the Python managers inside the osken container can now read `os.environ.get("STORAGE_CPUS")`. Without this, dynamic nodes would always get the fallback 0.15 regardless of the make command line value.

**Propagation chain** (complete):
```
make STORAGE_CPUS=0.12
  → build_network_setup.sh (inherits env)
    → bash build_network_1.sh → ${STORAGE_CPUS:-0.15} → static node --cpus=0.12 ✅
    → docker run -e STORAGE_CPUS="${STORAGE_CPUS:-0.15}" osken-controller
      → Python os.environ.get("STORAGE_CPUS") → dynamic node --cpus=0.12 ✅
```

WiredTiger cache stays at `--wiredTigerCacheSizeGB 0.25` (minimum viable).

### 6. `source/scripts/testing/phases.json` — NO CHANGE

v4 6-phase workload unchanged for all v6 runs.

### 7. Controller env overrides — NO NEW FILES NEEDED

- `mechanism_necessity_all.env` — Tier 1 ON, storage ON (already exists)
- `mechanism_necessity_notier1.env` — Tier 1 OFF (already exists, `SS_ENABLED=0`)
- `mechanism_necessity_nostorage.env` — Storage OFF (already exists, `MAX_DYNAMIC_STORAGE=0`)
- `mechanism_necessity_all.env` used for all calibration runs S1–S6

---

## Launch Commands

> **Prerequisites**: Sync latest source to cloud VM. Verify env-var mechanism is deployed: `build_network_1.sh` shows `${STORAGE_CPUS:-0.15}`, `storage_node_manager.py` shows `os.environ.get("STORAGE_CPUS")`. The S1 debug echo will confirm runtime propagation.

### v6-T1 — Tier 1 WAN Curve (6 runs)

```bash
# T1 — WAN=200ms, Tier 1 ON
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_all.env \
  RUN_LABEL=v6_t1_wan200_on \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=200 \
  CLIENTS=48 DEVICES=6000 NODES=100

# T2 — WAN=200ms, Tier 1 OFF
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_notier1.env \
  RUN_LABEL=v6_t1_wan200_off \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=200 \
  CLIENTS=48 DEVICES=6000 NODES=100

# T3 — WAN=230ms, Tier 1 ON
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_all.env \
  RUN_LABEL=v6_t1_wan230_on \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=230 \
  CLIENTS=48 DEVICES=6000 NODES=100

# T4 — WAN=230ms, Tier 1 OFF
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_notier1.env \
  RUN_LABEL=v6_t1_wan230_off \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=230 \
  CLIENTS=48 DEVICES=6000 NODES=100

# T5 — WAN=260ms, Tier 1 ON
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_all.env \
  RUN_LABEL=v6_t1_wan260_on \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=260 \
  CLIENTS=48 DEVICES=6000 NODES=100

# T6 — WAN=260ms, Tier 1 OFF
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_notier1.env \
  RUN_LABEL=v6_t1_wan260_off \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=260 \
  CLIENTS=48 DEVICES=6000 NODES=100
```

> **Note**: v6-T1 uses default CPU values (0.15 storage, 0.30 edge). No CPU env vars needed on command line — defaults are correct.

### v6-ST — Storage Calibration + Ablation

**Pre-run workflow for each S-run**:
1. Verify `storage_node_manager.py` reads from env var: `grep 'STORAGE_CPUS' source/sdn_controller/elasticity/storage_node_manager.py`
2. Launch the make command below — `STORAGE_CPUS=0.12` propagates automatically via env var

```bash
# S1 — CPUs=0.12, DEVICES=6000
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_all.env \
  RUN_LABEL=v6_st_cal_s1_cpu012 \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=160 \
  CLIENTS=48 DEVICES=6000 NODES=100 \
  STORAGE_CPUS=0.12

# S2 — CPUs=0.10, DEVICES=6000
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_all.env \
  RUN_LABEL=v6_st_cal_s2_cpu010 \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=160 \
  CLIENTS=48 DEVICES=6000 NODES=100 \
  STORAGE_CPUS=0.10

# S3 — CPUs=0.12, DEVICES=12000
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_all.env \
  RUN_LABEL=v6_st_cal_s3_cpu012 \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=160 \
  CLIENTS=48 DEVICES=12000 NODES=100 \
  STORAGE_CPUS=0.12

# S4 — CPUs=0.10, DEVICES=12000
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_all.env \
  RUN_LABEL=v6_st_cal_s4_cpu010 \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=160 \
  CLIENTS=48 DEVICES=12000 NODES=100 \
  STORAGE_CPUS=0.10

# S5 — CPUs=0.08, DEVICES=12000
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_all.env \
  RUN_LABEL=v6_st_cal_s5_cpu008 \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=160 \
  CLIENTS=48 DEVICES=12000 NODES=100 \
  STORAGE_CPUS=0.08

# S6 — CPUs=0.10, DEVICES=18000
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_all.env \
  RUN_LABEL=v6_st_cal_s6_cpu010 \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=160 \
  CLIENTS=48 DEVICES=18000 NODES=100 \
  STORAGE_CPUS=0.10
```

No ablation runs needed. The calibration winner IS the result — it demonstrates the ~20pp storage CPU drop from scaling within a single run.

---

## Execution Order

```
Phase 1 — Code changes (once, before any runs):
  1. Edit build_network_1.sh: env-var defaults for CPU/memory
  2. Edit build_network_2.sh: same
  3. Sync to cloud VM

Phase 2 — v6-T1 (6 runs, ~120 min):
  T1 → T2 → T3 → T4 → T5 → T6
  Analyze after each WAN pair. If 200ms inconclusive, queue T1-B replicates.

Phase 3 — v6-ST Calibration (2–6 runs, ~40–120 min):
  S1 → S2 → (check ~20pp drop) → S3 → S4 → (check drop) → S5 or S6
  Stop when a run shows ~20pp per-node storage CPU drop with stability.

Total: 8–12 runs, ~160–240 min (~3–4 hours)
```

---

## Success Criteria Summary

### v6-T1 — Tier 1 WAN Curve

| # | Metric | Target |
|---|--------|--------|
| 1 | Latency improvement ON vs OFF | **≥2× faster** (median ON ≤ 50% of OFF) in `tier1_hotspot` and `storage_storm` |
| 2 | Throughput ON ≥ OFF | Direction correct |
| 3 | No LAN outages, no tracebacks | Stability |

### v6-ST — Storage Scaling Distribution

| # | Metric | Target |
|---|--------|--------|
| 1 | Average storage CPU drop (pre-scale − post-scale) | **≥20pp** within `storage_storm` |
| 2 | No OOM kills, success ≥85% | Stability |

---

## Expected Outcomes

| Scenario | Implication |
|----------|------------|
| Tier 1 ≥2× faster at 200ms | Crossover is ≤200ms. Tier 1 beneficial for moderate-WAN deployments. |
| Tier 1 ≥2× faster only at 260ms | Crossover is 230–260ms. Tier 1 only justified for high-latency deployments. |
| Tier 1 <2× faster at all WAN values | Tier 1's v4 result (300ms) may need re-examination. WAN latency alone doesn't guarantee benefit. |
| Storage ~20pp drop at S2 (0.10/6K) | 0.10 CPUs is sufficient. DEVICES=6000 is enough load for visible distribution effect. |
| Storage ~20pp drop only at S4+ (0.10/12K) | Both tighter CPU AND higher load needed for measurable distribution benefit. |
| Storage unstable at 0.08 CPUs (S5) | WiredTiger floor is ~0.10 CPUs at 0.25GB cache. Accept best stable config. |
| No config reaches ~20pp drop | Storage distribution effect is real but too small to measure at this workload scale. Accept as a scale limitation finding. |

---

## Documentation Updates

- `docs/operation/testing/experiment/stability/mechanism_necessity/experiment_plan_v6.md` — this file (new)
- `docs/operation/testing/experiment/stability/mechanism_necessity/results_v6.md` — results (new, after execution)
- `docs/operation/testing/experiment/stability/mechanism_necessity/results.md` — append v6 timeline (after execution)
- `docs/operation/todo.md` — update with v6 status

---

## Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-06-29 | Initial v6 plan. Two sub-experiments: Tier 1 WAN curve (6 runs, 200/230/260ms) + Storage calibration/ablation (ST-C matrix, 6–8 runs). | v5 showed Tier 1 inconclusive at 160ms, storage not proven at 0.15 CPUs. v6 maps the Tier 1 crossover and pushes storage to saturation. |
| 2026-06-29 | Codebase review fixes applied: (1) CPU ranges revised to sub-linear for DEVICES scaling, (2) fallback paragraph corrected — CPU% does not concentrate, (3) pre-scale measurement window tightened to 60s, (4) run labels encode CPU value, (5) prerequisite block added, (6) debug echo for env propagation, (7) manual pre-run verification gate, (8) WAN amplification explanation, (9) S6 memory watch note. | Review against actual build scripts and storage_node_manager.py identified propagation gaps, incorrect concentration assumption, and fragility risks. |
| 2026-06-29 | Success criteria simplified per user: storage = ~20pp per-node CPU drop when scaling (within-run, no ablation); Tier 1 = noticeable latency improvement (qualitative). Removed ablation runs (S-A/S-B), reduced total from 11–14 to 8–12 runs. | User clarified that proving the mechanism's benefit (distribution effect, latency improvement) is the goal, not proving necessity through degradation. |
