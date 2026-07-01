# Experiment Plan v5 — Resource Limit Calibration

**Date**: 2026-06-29
**Status**: 📋 Planned
**Depends on**: [v4 experiment plan](experiment_plan_v4.md) and [v4 results](results_v4.md)
**Purpose**: Find the Docker resource limits (`--cpus`, `--memory`) for edge_storage_server and edge_server that produce 10–20% per-node CPU/RAM reduction when elasticity scales out.

---

## Intent

v4 proved Tier 1 is the dominant mechanism at WAN=300ms, but storage and compute elasticity showed minimal benefit because:
1. **Storage CPU never exceeded 1%** — MongoDB is too efficient for this workload at full resources
2. **Edge CPU reached only 2.9%** in `compute_spike` — not enough load to justify scaling
3. **WAN=300ms bottlenecked throughput** to ~13K requests (vs ~108K expected)

v5 calibrates resource constraints to create **realistic load levels** where elasticity produces a visible 10–20% per-node improvement. The calibration itself is a structured experiment with 3 combinations.

---

## Design Principle

> *"On average, when storage or compute scales out, the per-node CPU usage should drop by 10–20% (relative). This means pre-scale CPU must be high enough (~30–60%) that distributing the load produces a statistically meaningful drop."*

**Target pre-scale CPU**:
- Storage (MongoDB primary): **30–50%** → post-scale: **20–35%** (10–20pp / 20–40% relative drop)
- Edge (Flask server): **30–50%** → post-scale: **20–35%**

**How we achieve this**: Artificially constrain Docker container resources so the same workload consumes a larger fraction of available CPU. This is valid because:
- Real edge devices have constrained hardware (Raspberry Pi, low-power x86)
- The workload itself is realistic; we're simulating a resource-constrained deployment
- The relative benefit of elasticity (10–20% per-node drop) is what matters, not absolute CPU%

---

## Fixed Parameters (all runs)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| WAN | **160ms** | 16× slower than local (~10ms). Per-client cap ~6.25 req/s. 48 clients → 300 req/s theoretical — leaves headroom above 192 req/s target. |
| DEVICES | 6000 | Kept from v4. Large enough for non-trivial aggregation. |
| CLIENTS | 48 | Same as v4. |
| VIP | 30s | Confirmed optimal in v3. |
| Phases | v4 6-phase profile | Unchanged workload. |
| WiredTiger cache | **0.1 GB** (all runs) | Forces disk I/O on MongoDB, amplifying CPU per query. Set via `--wiredTigerCacheSizeGB 0.1` in `entrypoint.sh`. |

---

## Calibration Matrix

| Run | Label | Storage `--cpus` | Storage `--memory` | Edge `--cpus` | Edge `--memory` | Expected Storage CPU | Expected Edge CPU |
|-----|-------|-----------------|--------------------|---------------|-----------------|---------------------|-------------------|
| **C0** | `calibrate_v5_unlimited` | unlimited | unlimited | unlimited | unlimited | ~8–15% (too low) | ~5–15% (too low) |
| **C1** | `calibrate_v5_moderate` | **0.5** | **256m** | **1.0** | **256m** | ~20–35% | ~15–25% |
| **C2** | `calibrate_v5_aggressive` | **0.35** | **256m** | **0.75** | **256m** | ~30–50% | ~20–35% |
| **C3** | `calibrate_v5_tight` | **0.25** | **256m** | **0.5** | **128m** | ~40–65% | ~30–50% |

**Selection logic**: C0 is the no-limits baseline at WAN=160ms. C1 is the best estimate from v4 data. C2 and C3 progressively tighten. The winning combination is the tightest one where the system remains stable (no OOM kills, <20% failure rate) AND scale-up produces a visible 10–20% per-node CPU drop.

---

## Code Changes (v4 → v5 calibration)

### 1. `source/docker/edge_storage_server/entrypoint.sh`

Add `--wiredTigerCacheSizeGB 0.1` to mongod arguments. This forces MongoDB to use at most 100MB for its internal cache, causing more disk reads and amplifying CPU per query.

```bash
# Before (line ~5-8):
MONGOD_ARGS="--bind_ip_all"
if [ -n "${MONGO_REPLSET:-}" ]; then
    MONGOD_ARGS="$MONGOD_ARGS --replSet $MONGO_REPLSET"
fi

# After:
MONGOD_ARGS="--bind_ip_all --wiredTigerCacheSizeGB 0.1"
if [ -n "${MONGO_REPLSET:-}" ]; then
    MONGOD_ARGS="$MONGOD_ARGS --replSet $MONGO_REPLSET"
fi
```

### 2. `source/scripts/network/build_network_1.sh` (line ~111)

Add `--cpus` and `--memory` to `edge_storage_server_n1`:

```bash
docker run -dit --name edge_storage_server_n1 --network none \
  --cpus=${STORAGE_CPUS:-0.5} --memory=${STORAGE_MEMORY:-256m} \
  --no-healthcheck \
  ...
```

And to `edge_server_n1` (line ~100):

```bash
docker run -dit --name edge_server_n1 --network none --restart=on-failure \
  --cpus=${EDGE_CPUS:-1.0} --memory=${EDGE_MEMORY:-256m} \
  ...
```

### 3. `source/scripts/network/build_network_2.sh`

Same changes — `edge_storage_server_n2` and `edge_server_n2`.

### 4. `source/sdn_controller/elasticity/storage_node_manager.py` (line ~237)

Add resource flags to the `cmd` list for dynamic storage nodes:

```python
cmd = [
    "docker", "run", "-dit",
    "--cpus", "0.5",      # ← ADD (hardcoded to match static nodes)
    "--memory", "256m",   # ← ADD
    "--network", "none",
    "--name", name,
    ...
]
```

### 5. `source/sdn_controller/elasticity/compute_node_manager.py` (line ~214)

Same for dynamic edge servers:

```python
cmd = [
    "docker", "run", "-dit",
    "--cpus", "1.0",      # ← ADD
    "--memory", "256m",   # ← ADD
    "--network", "none",
    "--name", name,
    ...
]
```

> **Note**: The static nodes (build scripts) use environment variable defaults (`${STORAGE_CPUS:-0.5}`) for easy override. The dynamic nodes (Python managers) use hardcoded values. After calibration identifies the winning limits, both will be set to the same values.

### 6. Image Rebuild

`edge_storage_server` image must be rebuilt (entrypoint.sh changed). `edge_server` image does NOT need rebuild (no source changes — only docker run flags).

```bash
sudo bash source/scripts/build_images.sh edge_storage_server
```

---

## Launch Commands

```bash
# C0 — baseline (no limits, WAN=160ms)
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_all.env \
  RUN_LABEL=calibrate_v5_unlimited \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=160 \
  CLIENTS=48 DEVICES=6000 NODES=100 \
  STORAGE_CPUS=0 EDGE_CPUS=0 STORAGE_MEMORY=0 EDGE_MEMORY=0

# C1 — moderate (storage=0.5, edge=1.0)
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_all.env \
  RUN_LABEL=calibrate_v5_moderate \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=160 \
  CLIENTS=48 DEVICES=6000 NODES=100 \
  STORAGE_CPUS=0.5 EDGE_CPUS=1.0 STORAGE_MEMORY=256m EDGE_MEMORY=256m

# C2 — aggressive (storage=0.35, edge=0.75)
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_all.env \
  RUN_LABEL=calibrate_v5_aggressive \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=160 \
  CLIENTS=48 DEVICES=6000 NODES=100 \
  STORAGE_CPUS=0.35 EDGE_CPUS=0.75 STORAGE_MEMORY=256m EDGE_MEMORY=256m

# C3 — tight (storage=0.25, edge=0.5)
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/mechanism_necessity_all.env \
  RUN_LABEL=calibrate_v5_tight \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=160 \
  CLIENTS=48 DEVICES=6000 NODES=100 \
  STORAGE_CPUS=0.25 EDGE_CPUS=0.5 STORAGE_MEMORY=256m EDGE_MEMORY=128m
```

> C0 uses `0` as sentinel for "unlimited" — the build scripts must handle this (skip `--cpus`/`--memory` flags when value is 0 or empty). C1–C3 use explicit values.

---

## Success Criteria (per calibration run)

| # | Metric | Target | Phase |
|---|--------|--------|-------|
| 1 | Storage CPU pre-scale | **30–60%** | `storage_storm` (first 120s) |
| 2 | Storage CPU post-scale | **10–20% drop** from pre-scale | `storage_storm` (after first scale-up) |
| 3 | Edge CPU pre-scale | **30–60%** | `compute_spike` (first 90s) |
| 4 | Edge CPU post-scale | **10–20% drop** from pre-scale | `compute_spike` (after first scale-up) |
| 5 | System stability | No OOM kills, <25% failure rate | All phases |
| 6 | Scale-up triggers | ≥1 storage and ≥1 compute | `storage_storm` + `compute_spike` |

**Winning combination**: The run that meets all criteria with the tightest (lowest) resource limits.

---

## Calibration Workflow

```
Edit 7 files → sync to cloud VM → rebuild edge_storage_server image
  → Run C0 (baseline, ~20 min)
  → Run C1 (moderate, ~20 min)
  → If C1 doesn't reach 30% CPU: skip to C2
  → Run C2 (aggressive, ~20 min)
  → If C2 meets criteria: STOP (C2 is winner)
  → Else Run C3 (tight, ~20 min)
  → Analyze all runs → select winner
  → Apply winner limits to all files permanently
  → Proceed to v5 mechanism ablation experiment
```

**Total calibration time**: ~60–80 min (3–4 runs × 20 min each).

---

## Expected Outcomes

| If… | Then… |
|-----|-------|
| C1 (0.5 CPUs) already reaches 30–50% CPU | Storage is more resource-sensitive than estimated. C1 is the winner. Use for v5. |
| C2 (0.35 CPUs) reaches 30–50% CPU | This is the sweet spot. Apply C2 limits to v5. |
| C3 (0.25 CPUs) still below 30% CPU | MongoDB is incredibly efficient. Consider workload amplification (more DEVICES, `$lookup`) instead of further CPU limiting. |
| Any run has OOM kills | Increase `--memory` for that run's successor. |
| C1 fails (high failure rate) | Limits too aggressive at WAN=160ms. Reduce WAN to 120ms or loosen limits. |

---

## Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-06-29 | Initial v5 calibration plan. 4-run matrix (C0–C3), WAN=160ms, Docker resource limits + WiredTiger cache. | v4 showed storage/compute CPU invisible; need constrained resources to make elasticity benefit measurable. |
| 2026-06-29 | C0 (unlimited) and C1 (0.5 CPUs) calibration runs completed. C1 storage CPU only 6.1% — too low to show elasticity benefit. Proceeded to C3 (0.10 CPUs) which reached 28.6% storage CPU but caused instability. Settled on storage=0.15 CPUs, edge=0.30 CPUs, storage memory 512m (WiredTiger 0.25GB minimum), WAN=160ms. | Calibration showed MongoDB needs 0.25GB WiredTiger minimum (0.1GB caused error), 256MB memory caused OOM. v5 launched at 0.15 CPUs storage, 0.30 CPUs edge. |
| 2026-06-29 | v5 mechanism ablation completed: 4 runs (A: all on, B: no Tier 1, C: no storage, D: no compute) at WAN=160ms with resource limits. | Full results in [results_v5.md](results_v5.md). Compute emerged as DOMINANT mechanism (−34% throughput when ablated), reversing v4 where Tier 1 dominated. Resource constraints successfully shifted bottleneck from WAN to compute CPU. |
