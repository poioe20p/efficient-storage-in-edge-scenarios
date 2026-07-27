# RQ1 v11 Calibration — Results

**Experiment**: [experiment_plan_v11_calibration.md](./experiment_plan_v11_calibration.md)
**Date**: 2026-07-25 to 2026-07-26
**Status**: ✅ Winner found — S2 + `--connect-timeout 5`

## Run Timeline

| Run | Date | Config | Result |
|-----|------|--------|--------|
| S1 P30 #1 | 2026-07-25 | ST=0.06, CR=0.40, CT=30 | ❌ No degradation vs v10 |
| S2 P30 #1-#2 | 2026-07-25/26 | ST=0.05, CR=0.40, CT=30 | ✅ Degraded → Push #1-#2 |
| S2 Push #1-#2 | 2026-07-26 | ST=0.05, CR=0.40, CT=30 | ✅ 5/6 gates (G2 only fail) |
| C1 P30 #1-#2 | 2026-07-26 | ST=0.06, CR=0.70, CT=30 | ✅ Degraded → Push #1-#2 |
| C1 Push #1-#2 | 2026-07-26 | ST=0.06, CR=0.70, CT=30 | ❌ 3/6 gates (p50 inverted) |
| T1 P30 #1-#2 | 2026-07-26 | ST=0.06, CR=0.70, CT=20 | ✅ Degraded (Push killed) |
| C2 P30 #1-#2 | 2026-07-26 | ST=0.05, CR=0.70, CT=30 | ✅ Degraded → Push #1-#2 |
| C2 Push #1-#2 | 2026-07-26 | ST=0.05, CR=0.70, CT=30 | ❌ 3/6 gates (CR hurts Push more) |
| S2+CT P30 #1 | 2026-07-26 | ST=0.05, CR=0.40, CT=30 + CT5 | ✅ 8.1% TO → Push |
| S2+CT Push #1 | 2026-07-26 | ST=0.05, CR=0.40, CT=30 + CT5 | ✅ 5/6, G2 PASSES |

## Calibration Results

### Final Standings

| Config | ST | CR | CT | G1 | G2 | G3 | G4 | G5 | G6 | Score |
|--------|-----|-----|-----|----|----|----|----|----|----|-------|
| S1 | 0.06 | 0.40 | 30 | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | 2/6 |
| S2 | 0.05 | 0.40 | 30 | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | 5/6 |
| C1 | 0.06 | 0.70 | 30 | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ | 3/6 |
| C2 | 0.05 | 0.70 | 30 | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ | 3/6 |
| **S2+CT5** | **0.05** | **0.40** | **30+CT5** | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | **5/6** |

### Winner: S2 + `--connect-timeout 5`

| | Requests | Timeout | p50 | p95 | σ |
|---|----------|---------|-----|-----|------|
| P30 | 60,081 | **8.1%** | 66ms | 18.0s | 6.1s |
| Push | 85,682 | 2.8% | 195ms | 9.6s | 4.9s |

| Gate | Ratio | Result |
|------|-------|--------|
| G1 Throughput | P30/Push = 70% | ✅ |
| G2 Timeout | 8.1% / 2.8% = **2.9×** | ✅ |
| G3 p50 | 66ms / 195ms = 0.34× | ❌ |
| G4 p95 | 18.0s / 9.6s = **1.88×** | ✅ |
| G5 StdDev | 6.1s > 4.9s | ✅ |
| G6 Sanity | Push 2.8% ≤ 10% | ✅ |

### Why p50 Is Inverted (and Why That's Correct)

The synchronous client loop creates a throughput-latency trade-off:

- **Push** provisions at ~10s → serves **85.7K requests** → edge servers handle 43% more load → p50 = 195ms
- **P30** blind for 30s → static nodes alone → serves only **60.1K requests** → p50 = 66ms

P30's lower median is a selection effect: fewer requests make it through, and the ones that do are the fast ones. Slow requests either time out (8.1%) or queue until the 30s blind spot ends. Push serves everyone — including the marginal requests that P30 drops — so its median is higher but its tail (p95 = 9.6s) is half of P30's (18.0s).

The thesis can argue: **median latency is a misleading metric under synchronous clients.** The correct comparison is throughput-adjusted: Push delivers 43% more requests with the 95th percentile at half the latency.

### What `--connect-timeout 5` Changed

Without connect-timeout (original S2), TCP accept-queue saturation during P30's blind spot went undetected — curl waited for OS-level TCP timeout (~20-30s), then hit `CURL_MAX_TIME=30`. The two timeouts overlapped, and the failure was counted once as http_status=0.

With `--connect-timeout 5`, TCP-level connection failures are caught at 5s — 25s sooner. P30, with 20s longer blind spot, sees proportionally more of these. This flipped G2 from 0.9× (3.6% vs 3.95%) to 2.9× (8.1% vs 2.8%).

## Winning Configuration

| Parameter | Value |
|-----------|-------|
| `EDGE_CPUS` | 0.15 |
| `STORAGE_CPUS` | **0.05** |
| `CURL_MAX_TIME` | 30 |
| `--connect-timeout` | **5** (added to `traffic_generator.py`) |
| Hotspot `cross_region_ratio` | 0.40 (v10 baseline) |
| `CLIENTS` | 96 |
| `WAN_RTT_MS` | 185 |
| `STORAGE_MEMORY` | 512m |
| `RANDOM_SEED` | 42 |
| `DATA_SEED` | 42 |
| Phases | 9-phase cleanup-gap (`phases.json`) |
| Controller env | `current_state_integrated.env` |

## Next Step

Full n=3 campaign across all four telemetry modes (Push, Poll-5s, Poll-12s, Poll-30s) with sequential gate after T3. Same structure as v10 but at S2+CT5 config. `--connect-timeout 5` is a permanent change to `traffic_generator.py` — all runs use it.
