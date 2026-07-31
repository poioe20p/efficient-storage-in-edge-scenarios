# RQ3 v7 — Results

**Date**: 2026-07-29 · **Status**: ✅ Complete · **Runs**: 3 (DS1, CO1, LO1)

---

## 1. Parameter Regime

### degradation_score (DS1) — Tuned

| Parameter | v6 | v7 DS |
|-----------|:---:|:---:|
| `SCALEUP_COMPUTE_WINDOW_SIZE` | 5 | 10 |
| `SCALEUP_COMPUTE_REQUIRED` | 3 | 7 |
| `SCALEUP_COMPUTE_COOLDOWN_S` | 45 | 180 |
| `SCALEUP_COMPUTE_BASE_THRESHOLD` | 0.20 | 0.30 |
| `SCALEUP_STORAGE_WINDOW_SIZE` | 5 | 7 |
| `SCALEUP_STORAGE_REQUIRED` | 2 | 4 |
| `SCALEUP_STORAGE_COOLDOWN_S` | 120 | 180 |
| `SCALEUP_STORAGE_BASE_THRESHOLD` | 0.25 | 0.35 |
| `SCALE_DOWN_COMPUTE_WINDOW_SIZE` | 12 | 5 |
| `SCALE_DOWN_COMPUTE_REQUIRED` | 9 | 3 |
| `SCALEDOWN_COMPUTE_COOLDOWN_S` | 180 | 30 |
| `TAU_CPU_DOWN` | 15 | 25 |
| `TAU_PROC_DOWN_MS` | 20 | 50 |
| `SCALE_DOWN_STORAGE_WINDOW_SIZE` | 12 | 6 |
| `SCALE_DOWN_STORAGE_REQUIRED` | 7 | 4 |
| `SCALEDOWN_STORAGE_COOLDOWN_S` | 120 | 60 |
| `TAU_DB_DOWN_MS` | 150 | 400 |

### cpu_only (CO1) & latency_only (LO1) — Old v7

| Parameter | Value |
|-----------|:---:|
| `SCALEUP_WINDOW_SIZE` | 6 |
| `SCALEUP_REQUIRED` | 4 |
| `SCALEUP_COMPUTE_COOLDOWN_S` | 90 |
| `SCALEUP_STORAGE_COOLDOWN_S` | 180 |
| `SCALE_DOWN_COMPUTE_WINDOW_SIZE` | 8 |
| `SCALE_DOWN_COMPUTE_REQUIRED` | 6 |
| `SCALEDOWN_COMPUTE_COOLDOWN_S` | 90 |
| `SCALE_DOWN_STORAGE_WINDOW_SIZE` | 8 |
| `SCALE_DOWN_STORAGE_REQUIRED` | 6 |
| `SCALEDOWN_STORAGE_COOLDOWN_S` | 80 |

> Weights, phases, caps (MAX_DYNAMIC_STORAGE=8, MAX_DYNAMIC_COMPUTE=12), resource limits, and WAN RTT unchanged from v6.

### Code Change — Reserve-Floor Decoupling

`node_registry.py::can_scale_down_storage` bypasses the `READY_RESERVED` requirement when >2 dynamic storage nodes exist on the LAN. This removes the ~120s per-node bottleneck that limited v6 storage scale-down.

---

## 2. Three-Mode Comparison

| Metric | DS1 (eased) | CO1 | LO1 |
|--------|:---:|:---:|:---:|
| **Dynamic nodes (demand_drop)** | **12** | **13** | **10** |
| LAN1 dyn (storage) | 5 (4s) | 9 (7s) | 4 (4s) |
| LAN2 dyn (storage) | 7 (6s) | 4 (4s) | 6 (6s) |
| **Total requests** | 27,090 | **103,633** | 23,112 |
| **p50 latency** | 454 ms | 0.2 ms | 476 ms |
| **Mean latency** | 3,846 ms | 835 ms | 4,524 ms |
| **CPU mean** | 27.1% | 23.4% | 25.6% |

### v6 Baseline (for reference)

| Metric | DS1 | CO1 | LO1 |
|--------|:---:|:---:|:---:|
| Dynamic nodes | 19 | — | — |
| Total requests | 27,212 | 27,307 | 18,396 |
| p50 latency | 219 ms | 16 ms | 19 ms |
| Mean latency | 2,909 ms | — | — |
| CPU mean | 23.3% | — | — |

---

## 3. Iteration History

| Iteration | Storage SD | Storage SU | DYN final | p50 |
|-----------|:---:|:---:|:---:|:---:|
| Tight | 3/5, 30s | 7/10, 300s | 5 | 504 ms |
| Eased | 4/6, 60s | 4/7, 180s | 7 (first run), 12 (re-run) | 6.6 ms / 454 ms |
| 3/4 | 3/4, 60s | 4/7, 180s | 8 | 398 ms |

> The first eased run (7 dyn, 6.6 ms p50) showed significant run-to-run variance. The re-run (12 dyn, 454 ms p50) is more representative.

---

## 4. Conclusions

1. **Three-way separation holds but is weaker than v6.** CO1 dominates throughput (104k vs 23-27k) but spawns the most nodes. DS and LO converge in both node count and latency.

2. **Reserve-floor decoupling worked but scale-down is still bounded.** Despite the code change removing the per-node bottleneck, 10-13 dynamic nodes remain after demand_drop. The spawn rate during stress phases outpaces the scale-down rate.

3. **Run-to-run variance is high.** The first eased DS1 had 7 dyn and 6.6 ms p50; the re-run had 12 dyn and 454 ms p50. Single-replicate conclusions should be treated cautiously.

4. **Demand_drop duration (420s) is insufficient** to fully drain the node pool given current spawn rates. Either longer drain phase or harder scale-up gates are needed to reach the ≤4 dynamic node target.

5. **CO1's 104k throughput with 0.2 ms p50** suggests cpu_only under old v7 params is genuinely over-provisioning — consistent with v6 findings.

---

## 5. Run IDs

| Run | ID |
|-----|-----|
| DS1 | `20260729_154358_rq3_v7_ds_1` |
| CO1 | `20260729_170431_rq3_v7_cpu_1` |
| LO1 | `20260729_175155_rq3_v7_lat_1` |
