# RQ3 v7 — Tighter Scaling Regime

**Status**: 🔵 Designed · **Date**: 2026-07-29 · **Extends**: [v6](../v6/experiment_plan_v6.md)
**Canonical RQ doc**: [`rq3_v6.md`](../../../../../../docs/research_questions/rq3/rq3_v6.md) (question unchanged from v6 — only scaling parameters change)

---

## 1. Objective & Hypothesis

Same core question as v6: **does trigger composition matter?** — but under a tighter scaling regime where scale-up requires stronger evidence (4/6 windows, 90s cooldown) and scale-down removes idle nodes aggressively (90s cooldown, 6/8 windows, 80s eval).

**Hypothesis**: The three-way separation (latency_only < degradation_score < cpu_only for spawn count) persists, but with degradation_score now using aggressive parameters:
- Fewer total spawns (4–8 vs 26.7 in v6): 7/10 windows + 0.30/0.50 base thresholds + 180/300s cooldowns
- ≤1–2 dynamic nodes per LAN after `demand_drop`: 3/5 windows + 30s cooldowns + reserve-floor decoupling enables back-to-back removal without per-node reserve-prep delays
- Clearer waste signal: cpu_only's extra spawns become even more visible vs the resource cost
- latency_only under-detection may worsen (longer cooldowns delay the few spawns it does trigger)

**Independent variable**: Four weight coefficients (same as v6). **NOTE: cpu_only and latency_only env files are NOT changed** — they keep the old v7 parameters (4/6 scale-up, 6/8 scale-down). Only degradation_score gets the aggressive treatment. This means the DS vs CO vs LO comparison now also measures the effect of the scaling regime.

---

## 2. Changes from v6

### Scale-up (tighter)

| Parameter | v6 | v7 (old DS1) | v7 (current) |
|-----------|:---:|:---:|:---:|
| `SCALEUP_WINDOW_SIZE` (compute) | 5 | 6 | **10** |
| `SCALEUP_REQUIRED` (compute) | 3/5 | 4/6 | **7/10** |
| `SCALEUP_COMPUTE_COOLDOWN_S` | 45 | 90 | **180** |
| `SCALEUP_STORAGE_WINDOW_SIZE` | 5 | 6 | **10** |
| `SCALEUP_STORAGE_REQUIRED` | 2/5 | 4/6 | **7/10** |
| `SCALEUP_STORAGE_COOLDOWN_S` | 120 | 180 | **300** |
| `SCALEUP_COMPUTE_BASE_THRESHOLD` | 0.20 | 0.18 | **0.30** |
| `SCALEUP_STORAGE_BASE_THRESHOLD` | 0.25 | 0.35 | **0.50** |

### Scale-down (easier)

| Parameter | v6 | v7 (old DS1) | v7 (current) |
|-----------|:---:|:---:|:---:|
| `SCALEDOWN_COMPUTE_COOLDOWN_S` | 180 | 90 | **30** |
| `SCALE_DOWN_COMPUTE_WINDOW_SIZE` | 12 | 8 | **5** |
| `SCALE_DOWN_COMPUTE_REQUIRED` | 9/12 | 6/8 | **3/5** |
| `SCALEDOWN_STORAGE_COOLDOWN_S` | 120 | 80 | **30** |
| `SCALE_DOWN_STORAGE_WINDOW_SIZE` | 12 | 8 | **5** |
| `SCALE_DOWN_STORAGE_REQUIRED` | 7/12 | 6/8 | **3/5** |
| `TAU_CPU_DOWN` | 15 | 15 | **25** |
| `TAU_PROC_DOWN_MS` | 20 | 20 | **50** |
| `TAU_DB_DOWN_MS` | 150 | 150 | **400** |
| `SCALE_DOWN_CANDIDATE_MAX_STALENESS_S` | 90 | 90 | **60** |

### Code Change — Reserve-Floor Decoupling

`node_registry.py::can_scale_down_storage` no longer requires a `READY_RESERVED` slot when the LAN has >2 dynamic storage nodes. This removes the bottleneck that limited v6 and the old v7 DS1 to removing at most one storage node per reserve-prep cycle (~120s). When ≥3 dynamic storage nodes exist on a LAN, scale-down proceeds without waiting for reserve preparation. The reserve floor still protects the last ≤2 nodes.

### Phases (unchanged)

Scale-up cycle (DS): 180s cooldown + 100s eval (10 windows × 10s) = **280s per compute spawn**. Storage: 300s cooldown + 100s eval = **400s per storage spawn**.
Scale-down cycle (DS): 30s cooldown + 50s eval (5 windows × 10s) = **80s per removal** (both tiers). Reserve-floor decoupled when >2 dynamic storage nodes → back-to-back removal possible.

| Phase | v6 | v7 | Compute spawns (DS) | Storage spawns (DS) |
|-------|:---:|:---:|:---:|:---:|
| `storage_storm` | 240s | **300s** | ≤1 | 0 |
| `tier1_hotspot` | 180s | **240s** | 0 | 0 |
| `reverse_hotspot` | 180s | **240s** | 0 | 0 |
| `compute_spike` | 180s | **240s** | 0 | 0 |
| `inter_hotspot_cooldown` | 300s | **360s** | — (280s buffer for scale-down) | |
| `demand_drop` | 300s | **420s** | — (340s buffer for scale-down; ~4 removal cycles) | |
| **Total** | 1440s | **1860s (31 min)** | | |

> Telemetry interval: 10 s per window (held constant from v6). All cycle math assumes 10 s windows.

### Unchanged from v6

All floors (except raised TAU_DB_DOWN, TAU_CPU_DOWN, TAU_PROC_DOWN), spans, peer relief, telemetry delivery, routing policy, seeds, resource limits (0.08/0.25 CPUs, WAN=185ms, 96 clients), Tier 1 selective sync, persistent reserve, VIP routing, max dynamic nodes (8 storage, 12 compute), fault plan, weights, phases file.

**Changed from old v7**: `node_registry.py` reserve-floor decoupling (bypasses READY_RESERVED requirement when >2 dynamic storage nodes on LAN). Controller code is volume-mounted — no image rebuild needed.

---

## 3. Weights (Same as v6)

| Mode | W_CPU | W_T_PROC | W_STORAGE_CPU | W_T_DB |
|------|:---:|:---:|:---:|:---:|
| `degradation_score` | 0.40 | 0.60 | 0.20 | 0.80 |
| `cpu_only` | 1.00 | 0.00 | 1.00 | 0.00 |
| `latency_only` | 0.00 | 1.00 | 0.00 | 1.00 |

---

## 4. Run Matrix

3 modes × 3 replicates = 9 runs. Same run order as v6: DS1→DS3, then CO1→CO3, then LO1→LO3.

| # | Label | Mode | Env Override File | Phases File |
|---|-------|------|-------------------|-------------|
| DS1–DS3 | `rq3_v7_ds_1`–`_3` | degradation_score | `rq3_v7_degradation_score.env` | `phases_rq3_v7.json` |
| CO1–CO3 | `rq3_v7_cpu_1`–`_3` | cpu_only | `rq3_v7_cpu_only.env` | `phases_rq3_v7.json` |
| LO1–LO3 | `rq3_v7_lat_1`–`_3` | latency_only | `rq3_v7_latency_only.env` | `phases_rq3_v7.json` |

Between-run: full cleanup + VM reboot. **Estimated wall-clock**: 9 × (~31 min run + ~5 min reboot) ≈ **5.4 hours**.

---

## 5. Per-Run Launch Command

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n STORAGE_CPUS=0.08 EDGE_CPUS=0.25 WAN_RTT_MS=185 RANDOM_SEED=42 \
    make -C source/scripts setup_network create_clients setup_test_data run_experiment \
    OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/<ENV_FILE> \
    RUN_LABEL=<LABEL> \
    PHASES_CONFIG=testing/phases_override/phases_rq3_v7.json \
    CLIENTS=48 CONTENT_ITEMS=6000 USERS=100 \
    DATA_SEED=42 CURL_MAX_TIME=30 \
    SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1 \
    > /tmp/<LABEL>.log 2>&1 &"
```

> `CLIENTS=48` means 48 per LAN (96 total). `SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1` skips the per-run phases of `run_experiment.sh`; the Makefile targets `create_clients` and `setup_test_data` re-seed on every run (non-trivial: 6000 items + 100 users). The 5.4h estimate accounts for this.

| Run | `<ENV_FILE>` | `<LABEL>` |
|---|---|---|
| DS1–DS3 | `rq3_v7_degradation_score.env` | `rq3_v7_ds_1`–`_3` |
| CO1–CO3 | `rq3_v7_cpu_only.env` | `rq3_v7_cpu_1`–`_3` |
| LO1–LO3 | `rq3_v7_latency_only.env` | `rq3_v7_lat_1`–`_3` |

---

## 6. Success Criteria

Same as v6 (C1–C11 from experiment_plan_v6.md §8), with one addition:

| # | Criterion | Pass condition |
|---|-----------|----------------|
| C12 | Scale-down efficiency | ≤2 dynamic nodes per LAN at end of `demand_drop` in DS1–DS3 (enabled by reserve-floor decoupling + 3/5 windows + 30s cooldowns) |

---

## 7. Expected Outcomes

| Mode | v6 spawns (mean) | v7 expected | Rationale |
|------|:---:|:---:|------|
| degradation_score | 26.7 | **4–8** | 7/10 windows + 0.30/0.50 base thresholds + 180/300s cooldowns; reserve-floor decoupled for rapid scale-down |
| cpu_only | 36.7 | **10–16** | Still highest, but 4/6 gate + peer relief curtails chaining (unchanged from old v7 params — only DS changed) |
| latency_only | 19.0 | **3–6** | Storage-only T_db spawns, 4/6 + 180s cooldown severely limits (unchanged from old v7 params) |

> Ranges are non-overlapping: latency_only (3–6) < degradation_score (4–8) < cpu_only (10–16).

> Ranges are non-overlapping: latency_only (3–6) < degradation_score (6–10) < cpu_only (10–16). Storage spawns dominate all modes (v6 finding). Compute spawns limited to 1–2 per run given phase duration constraints (§2).

**Scale-down**: v6 left 76–84% of nodes unremoved; old v7 DS1 left 15/19 dynamic nodes. With the reserve-floor decoupling + 3/5 windows + 30s cooldowns + raised underutilization ceilings (TAU_DB_DOWN=400ms), scale-down can remove storage nodes back-to-back until hitting the ≤2 floor. demand_drop should end at ≤1–2 dynamic nodes per LAN.

**Service quality**: latencies may increase slightly vs v6 (fewer spawns = less capacity), but the three-way ordering should hold. CURL_MAX_TIME=30s is protected by the default 5000ms timeout ceiling (windows where T_proc/T_db > 5000ms are skipped, not counted against scale-down).

---

## 8. References

- [RQ3 v6 experiment plan](../v6/experiment_plan_v6.md) — baseline for scaling parameter comparison
- [RQ3 v6 results](../v6/results.md) — baseline for spawn/latency comparison
- [RQ3 v7 env — degradation_score](../../../../../../source/scripts/testing/controller_env_overrides/rq3_v7_degradation_score.env)
- [RQ3 v7 env — cpu_only](../../../../../../source/scripts/testing/controller_env_overrides/rq3_v7_cpu_only.env)
- [RQ3 v7 env — latency_only](../../../../../../source/scripts/testing/controller_env_overrides/rq3_v7_latency_only.env)
- [Phases v7](../../../../../../source/scripts/testing/phases_override/phases_rq3_v7.json)
- [RQ3 v6 measurement framework](../../../../../../docs/research_questions/rq3/rq3_v6.md)

---

## 9. Pre-Flight Verification

No separate smoke test — v7 reuses the v6 verification baseline (same resource config, same mean-only signal, same Docker images). Before launch:

- [ ] Cloud VM reachable, `sudo -n` working
- [ ] `node_registry.py` reserve-floor decoupling deployed (volume mount — no rebuild needed; verify with `grep "dyn_on_lan" source/sdn_controller/node_registry.py`)
- [ ] v7 env files synced to cloud VM (`rq3_v7_*.env`)
- [ ] `phases_rq3_v7.json` synced to cloud VM
- [ ] `scaling_policy.py` mean-only signal still deployed (unchanged from v6)
- [ ] Docker images up-to-date (unchanged from v6 — controller code is volume-mounted, env params only)

> The `node_registry.py` change takes effect on container restart (which happens during `setup_network`). No image rebuild needed: controller code is mounted via `-v "$PWD":/workspace`.
