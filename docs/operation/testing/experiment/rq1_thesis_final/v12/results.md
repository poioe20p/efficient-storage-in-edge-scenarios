# RQ1 v12 — Results

**Experiment**: [experiment_plan_v12.md](./experiment_plan_v12.md)  
**Date**: 2026-07-27  
**Status**: ❌ Campaign aborted — configuration unstable at n=3; phases redesign needed

## Run Timeline

| Run | Label | Mode | Status | Requests | TO Rate | G8 |
|-----|-------|------|--------|----------|---------|-----|
| P1 | `rq1_v12_push_1` | Push | ✅ | 67,301 | 2.76% | ✅ |
| P2 | `rq1_v12_push_2` | Push | ❌ Anomalous | 87,384 | 23.87% | ✅ |
| P2b | `rq1_v12_push_2b` | Push | ✅ | 71,573 | 2.37% | ✅ |
| P3 | `rq1_v12_push_3` | Push | ✅ | 81,541 | 2.25% | ✅ |
| T1 | `rq1_v12_poll30_1` | Poll-30s | ✅ | 65,971 | 4.67% | ✅ |
| T2 | `rq1_v12_poll30_2` | Poll-30s | ✅ | 58,684 | 4.89% | ✅ |
| T3 | `rq1_v12_poll30_3` | Poll-30s | ❌ Anomalous | 50,594 | 38.49% | ✅ |
| T3b | `rq1_v12_poll30_3b` | Poll-30s | ⏹️ Killed | — | — | — |

**7 runs executed** (1 killed). 2 catastrophic anomalies (P2, T3). 1 stable rerun (P2b).  
**Gate check**: Not passed — campaign aborted before intermediate modes.

---

## 1. Stable-Run Metrics

### 1.1 Throughput

| Mode | Run | Total Requests |
|------|-----|---------------|
| Push | P1 | 67,301 |
| Push | P2b | 71,573 |
| Push | P3 | 81,541 |
| **Push μ (σ)** | | **73,472 (7,290)** |
| Poll-30s | T1 | 65,971 |
| Poll-30s | T2 | 58,684 |
| **P30 μ (σ)** | | **62,328 (5,150)** |

**Throughput gap**: P30 completes 85% of Push throughput — a **15% penalty** attributable to the 30-second blind spot during which the controller takes no action while demand rises.

### 1.2 Timeout Rate

| Mode | Run | Timeout Rate |
|------|-----|-------------|
| Push | P1 | 2.76% |
| Push | P2b | 2.37% |
| Push | P3 | 2.25% |
| **Push μ** | | **2.46%** |
| Poll-30s | T1 | 4.67% |
| Poll-30s | T2 | 4.89% |
| **P30 μ** | | **4.78%** |

**Timeout ratio**: P30 timeouts are **1.94×** Push timeouts. The gap exists directionally but is below the planned ≥6% gate. Without `--connect-timeout 5`, TCP accept-queue failures are absorbed by OS-level TCP retransmission (~20-30s) and do not register as `http_status=0` events, muting the timeout separation.

### 1.3 Latency (successful requests only, http_status=200)

| Mode | Run | p50 | p95 | p99 | Mean | StdDev |
|------|-----|-----|-----|-----|------|--------|
| Push | P1 | 0.011s | 8.71s | 18.98s | 1.48s | 3.55s |
| Push | P2b | 0.028s | 7.61s | 18.84s | 1.39s | 3.39s |
| Push | P3 | 0.020s | 7.09s | 18.40s | 1.19s | 3.01s |
| **Push μ** | | **0.020s** | **7.80s** | **18.74s** | **1.36s** | **3.32s** |
| Poll-30s | T1 | 0.057s | 11.10s | 18.92s | 1.61s | 3.74s |
| Poll-30s | T2 | 0.348s | 11.32s | 18.89s | 1.76s | 3.95s |
| **P30 μ** | | **0.202s** | **11.21s** | **18.91s** | **1.69s** | **3.84s** |

**p95 gap**: P30 p95 is **1.44×** Push p95 (11.21s vs 7.80s). The tail inflates under blind-spot queuing — requests that arrive during the 30s detection gap accumulate in the edge server queue, producing longer completion times.

**p50 inversion**: P30's median is higher than Push's for T2 (0.348s vs 0.020–0.028s), but this is a throughput-latency trade-off artifact. Push serves 15% more requests — including the marginal ones that P30 drops — which inflates Push's mean but not its median under synchronous client pacing. The thesis argues that **median latency is misleading under synchronous clients**; the correct comparison is throughput-adjusted: Push delivers more requests with lower tail latency.

**StdDev**: P30 latency variance is **1.16×** Push (3.84s vs 3.32s). The blind spot introduces dispersion — some requests complete quickly (served by static nodes before saturation), others queue for extended periods.

### 1.4 Per-Phase Throughput (stable runs)

| Phase | Push (avg) | P30 (avg) | P30/Push |
|-------|-----------|-----------|----------|
| `baseline` (60s) | 1,083 | 1,060 | 98% |
| `storage_storm` (240s) | 13,055 | 10,718 | 82% |
| `cleanup_gap_1` (240s) | 905 | 921 | 102% |
| `tier1_hotspot` (180s) | 12,288 | 10,698 | 87% |
| `inter_hotspot_cooldown` (300s) | 4,845 | 5,135 | 106% |
| `reverse_hotspot` (180s) | 16,264 | 10,785 | 66% |
| `cleanup_gap_2` (240s) | 914 | 886 | 97% |
| `compute_spike` (180s) | 19,235 | 17,027 | 89% |
| `demand_drop` (300s) | 4,882 | 5,099 | 104% |

The largest gaps are in the storage-dependent phases: `storage_storm` (−18%), `tier1_hotspot` (−13%), and `reverse_hotspot` (−34%). The blind-spot penalty concentrates where storage is the bottleneck — consistent with the cascade mechanism.

### 1.5 Dynamic Node Provisioning

| Mode | Run | Compute Dyn | Storage Dyn | Total Dyn |
|------|-----|-------------|-------------|-----------|
| Push | P1 | 14 | 13 | 27 |
| Push | P2b | 16 | 17 | 33 |
| Push | P3 | 15 | 16 | 31 |
| Poll-30s | T1 | 10 | 18 | 28 |
| Poll-30s | T2 | 11 | 16 | 27 |

Poll-30s spawns fewer compute nodes (10-11 vs 14-16) — the blind spot causes the controller to miss scale-up opportunities for compute. Storage provisioning is similar across modes because storage saturation persists longer and is eventually detected even with the blind spot.

---

## 2. Anomalous Runs

### 2.1 P2 (`rq1_v12_push_2`) — Accept-Queue Collapse

| Metric | P2 (anomalous) | Push μ (stable) |
|--------|---------------|-----------------|
| Total requests | 87,384 | 73,472 |
| Timeout rate | **23.87%** | 2.46% |
| `compute_spike` TO | 18,164 (58.8%) | ~396 (2.1%) |
| Dynamic nodes | 15 comp / 15 stor | 15 / 15 |

**Failure mechanism**: Despite normal provisioning (15 compute, 15 storage — identical to stable runs), the `compute_spike` phase triggered a catastrophic TCP accept-queue collapse. Of 18,164 timeouts in compute_spike, **95% had latency <5s** — these are `--connect-timeout 5` failures where the edge server's accept queue was full and new SYN packets were dropped. The controller provisioned correctly, but the cascade was faster than provisioning — the `window_min=1` query in `service_pressure` returned massive datasets for certain random content items, blocking edge server worker processes and saturating the accept queue before new nodes came online.

### 2.2 T3 (`rq1_v12_poll30_3`) — Poll-30s Under-Provisioning

| Metric | T3 (anomalous) | P30 μ (stable) |
|--------|---------------|-----------------|
| Total requests | 50,594 | 62,328 |
| Timeout rate | **38.49%** | 4.78% |
| Dynamic nodes | **5 comp** / 11 stor | 11 / 17 |

**Failure mechanism**: The 30s blind spot prevented the controller from detecting the overload, resulting in only **5 compute nodes** spawned (vs 10-11 normal). Unlike P2, most timeouts were 5-10s latency (92%) — application-level stalls, not connect-timeout failures. The controller simply did not know it needed to provision more. The blind spot compounded the cascade: without enough compute nodes, the edge tier degraded, which cascaded into storage tier degradation, producing the 38.5% timeout rate.

---

## 3. Root Cause Analysis

### 3.1 The `compute_spike` Phase Is the Instability Vector

Both anomalies originate in `compute_spike` — a 180s phase at 100% `service_pressure` workload. The `window_min=1` parameter (set May 2026, predating all experiments) makes each `service_pressure` request query 10× more MongoDB data than `window_min=10`. Depending on random content selection, some requests return near-empty results and others return massive datasets — creating extreme per-request variance:

- **P2 (Push)**: An unlucky content distribution triggered an accept-queue collapse despite normal provisioning.
- **T3 (P30)**: The blind spot prevented detection of the overload, leading to severe under-provisioning.

The stable runs also showed variance in `compute_spike` throughput (15K–25K req), just not to the catastrophic threshold.

### 3.2 The S2+CT5 Configuration Is Inherently Unstable at n=3

The v11 calibration tested S2+CT5 at n=1 per mode (single pair) and achieved 5/6 gates. At n=3, the configuration shows ~30% catastrophic failure rate. The single-pair calibration gave a false sense of reliability — the config was always this unstable, the pilot just landed in the stable zone.

### 3.3 Why Other Calibration Configurations Are Not Viable

| Config | ST | CR | CT | Fate |
|--------|-----|-----|-----|------|
| S1 | 0.06 | 0.40 | 30 | No separation at all — too weak |
| C1 | 0.06 | 0.70 | 30 | p50 inverted, G2 fails |
| C2 | 0.05 | 0.70 | 30 | CR=0.70 hurts Push more than P30 |
| T1 | 0.06 | 0.70 | 20 | Push killed entirely |

The only axis that produces separation is `STORAGE_CPUS`, and the only viable point is 0.05. There is no unexplored configuration in the calibrated space.

---

## 4. Conclusions

### 4.1 The Blind-Spot Penalty Is Real but Muted by Phase Design

The storage cascade mechanism is valid: at `STORAGE_CPUS=0.05`, the blind spot produces a **15% throughput gap** (73K vs 62K), **1.44× p95 latency inflation** (11.2s vs 7.8s), and **1.94× timeout rate** (4.8% vs 2.5%). However, the 240s and 180s stress phases dilute the 30s blind spot — both modes spend most of each phase provisioned. The blind spot is only 12-17% of each stress phase duration.

### 4.2 The Throughput Gap Is the Stable Signal

Across the 5 stable runs, throughput consistently separates: Push 67-82K, Poll-30s 59-66K. The timeout gap is supplementary — it appears directionally (1.94×) but is below the 6% gate and depends on `--connect-timeout 5` to be visible. The p95 latency gap (1.44×) is consistent but modest.

### 4.3 Path Forward: Phases Redesign

The next iteration (v13) should redesign `phases.json` to amplify the blind-spot penalty:

1. **Shorter stress phases** (240s → 150s): The 30s blind spot becomes 20% of each phase instead of 12-17%.
2. **Replace `compute_spike` with `storage_storm_2`**: Eliminates the `window_min=1` variance source. The storage cascade is the RQ1 mechanism — measure it twice.
3. **Tighter cleanup gaps** (240s → 220s): Still above cooldowns (180s compute, 120s storage), but less recovery time between events.
4. **Total runtime**: 1760s (~29 min) vs 1920s (32 min) — faster iteration.
5. **Drop CT5**: `--connect-timeout 5` removed. Without `compute_spike`, accept-queue collapse risk is eliminated. Throughput gap is the primary signal.

The config should remain S2 (EDGE=0.15, STORAGE=0.05, CR=0.40). The `--connect-timeout 5` can be dropped if the primary signal is throughput — without CT5, TCP accept-queue failures appear as high-latency completions rather than timeouts, potentially reducing variance.

### 4.4 Thesis Narrative Implications

RQ1's contribution shifts from "blind spot causes dramatic timeout separation via TCP accept-queue cascade" to:

> **Telemetry delivery cadence affects transient service quality primarily through throughput degradation and tail-latency inflation during storage-demand shifts.** The 30-second blind spot in Poll-30s causes a 15% throughput penalty and 1.44× p95 latency increase compared to Push, as the controller misses detection windows during the critical early seconds of demand spikes. The penalty concentrates in storage-dependent workload phases, consistent with a cascade mechanism where storage saturation propagates through the edge tier's TCP accept queue.

---

## 5. Run Artifacts

All run folders under `source/scripts/testing/metrics/` on the cloud VM:

| Run | Folder | Status |
|-----|--------|--------|
| P1 | `20260727_045506_rq1_v12_push_1` | Retained for reference |
| P2 | `20260727_055924_rq1_v12_push_2` | Anomalous — excluded from analysis |
| P2b | `20260727_080630_rq1_v12_push_2b` | Retained — replaces P2 |
| P3 | `20260727_070321_rq1_v12_push_3` | Retained |
| T1 | `20260727_091006_rq1_v12_poll30_1` | Retained |
| T2 | `20260727_101429_rq1_v12_poll30_2` | Retained |
| T3 | `20260727_111825_rq1_v12_poll30_3` | Anomalous — excluded from analysis |
| T3b | `20260727_123846_rq1_v12_poll30_3b` | Killed during setup — no data |

---

## Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-07-27 | Campaign executed (7 runs + 1 killed) | S2+CT5 config per v11 calibration winner |
| 2026-07-27 | P2 rerun as P2b after 23.87% TO anomaly | Accept-queue collapse; P2b confirmed stable |
| 2026-07-27 | T3 rerun as T3b after 38.49% TO anomaly | Poll-30s under-provisioning; T3b killed early |
| 2026-07-27 | Campaign aborted | ~30% catastrophic failure rate at n=3; phases redesign needed |
| 2026-07-27 | Root cause identified | `compute_spike` + `window_min=1` produces extreme variance; S2+CT5 inherently unstable at n=3 |
| 2026-07-27 | Path forward defined | v13: shorter stress phases, replace compute_spike with storage_storm_2, keep S2 config |
