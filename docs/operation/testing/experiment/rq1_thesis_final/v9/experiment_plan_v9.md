# RQ1 v9 — Phase-Duration-Tightened Telemetry Cadence Evaluation

**Status**: ❌ Pilot Failed · **Date**: 2026-07-24
**Predecessor**: [`../v8/experiment_plan_v8.md`](../v8/experiment_plan_v8.md)
**Results**: [`results.md`](results.md)
**Thesis RQ**: [`docs/research_questions/rq1/rq1_v2.md`](../../../research_questions/rq1/rq1_v2.md)

## Intent

v9 replicates v8's four-mode telemetry comparison (Push, Poll-5s, Poll-12s,
Poll-30s; n=3 per mode) with **one structural change**: stress-phase durations
are halved so that Poll-30s's typical detection window (~150 s) exceeds the
phase duration, removing the recovery time that allowed Poll-30s to partially
catch up in v8.

v8 demonstrated that the blind-spot mechanism is real (M6: 67.9% blind spot
rate for Poll-30s) and that the penalty concentrates at the tail (p95 latency
+69–91%). However, v8's stress phases (180–240 s) were long enough that even
Poll-30s — when it did detect overload — could spawn nodes with substantial
remaining phase time and serve requests. This produced a throughput signal
dominated by worst-case fragility (σ = 14K for Poll-30s vs σ = 2K for Push)
rather than consistent gap across all replicates.

**v9 makes the detection window dominate the phase.** Reducing stress phases
to 90–120 s means Poll-30s's typical ~150 s detection latency exceeds every
stress phase. Even the lucky case (poll alignment at ~80 s) leaves only
~10–26 s of dynamic-node service time. The result should be a **consistent**
throughput gap, timeout-rate elevation, and latency degradation across all
three Poll-30s replicates — no more T1 outliers.

## What Changed from v8 and Why

| Parameter                    | v8 Value            | v9 Value                                    | Rationale                                                                                                                                                                   |
| ---------------------------- | ------------------- | ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `storage_storm` duration   | 240 s               | **120 s**                             | v8: Poll-30s detects at ~150s → 90s remaining. v9: phase ends before Poll-30s detects. Even lucky alignment at ~80s → only ~26s of spawned-node service (vs Push's ~56s). |
| `tier1_hotspot` duration   | 180 s               | **90 s**                              | Same logic. Detection gap now consumes the entire phase for Poll-30s.                                                                                                       |
| `reverse_hotspot` duration | 180 s               | **90 s**                              | Same.                                                                                                                                                                       |
| `compute_spike` duration   | 180 s               | **90 s**                              | This phase has no cross-region traffic — the penalty is purely compute-spawning delay. Shortening it isolates the blind-spot effect on compute-bound workloads.            |
| Total run time               | ~32 min             | **~25.5 min**                         | Consequence of shorter phases.                                                                                                                                              |
| Phases file                  | `phases_gap.json` | **`phases.json`** (edited in place) | Per canonical-file convention: edit`phases.json` directly. v8's `phases_gap.json` is retired — cleanup-gap is now the standard RQ1 workload.                           |

### What is NOT changing

Every other parameter from v8 is held constant:

- **CLIENTS=96, DEVICES=6000, NODES=100** — identical workload infrastructure
- **WAN_RTT_MS=185, STORAGE_CPUS=0.08, STORAGE_MEMORY=512m** — resource limits
- **EDGE_CPUS=0.30, EDGE_MEMORY=256m, CURL_MAX_TIME=30** — edge & client config
- **Controller env** (`current_state_integrated.env`) — same scoring, cooldowns, thresholds
- **RANDOM_SEED=42, DATA_SEED=42** — deterministic across all runs
- **Aggregation window = 10 s** — unchanged
- **Docker images** — same as v8 (edge_server rebuilt without EDGE_MAX_CONCURRENT)
- **Cleanup gaps** — 240 s at 5% load, unchanged. G8 isolation is preserved.
- **`inter_hotspot_cooldown`** — 300 s, unchanged. Hotspot phases share routing patterns; shortening the cooldown would risk cross-phase carryover between the two 90 s hotspot phases.
- **`baseline` (60 s) and `demand_drop` (300 s)** — unchanged.

## Hypothesis / Expected Outcome

1. **Blind spot rate** (M6): Identical to v8 — Push 0%, Poll-5s 0%, Poll-12s ~25%, Poll-30s ~68%. The delivery mechanism hasn't changed; only the consequences have.
2. **Throughput gap becomes consistent**: v8 showed Poll-30s at −19% mean with T1 matching Push. v9 expects Poll-30s throughput **30–50% below Push across all three replicates**, with no outlier matching Push. The detection window exceeds every stress phase, so Poll-30s should serve few-to-zero requests with dynamic-node capacity.
3. **Timeout rate separates cleanly**: v8 showed overlapping distributions (Push 2.7–3.6%, Poll-30s 2.5–10.3%). v9 expects Push ~3% and Poll-30s **15–25% across all replicates**, with no overlap between Push and Poll-30s distributions.
4. **p95 latency gap widens**: v8 showed Poll-30s at 13.5 s vs ~7–8 s for others. v9 expects Poll-30s p95 **>20 s**, with the gap driven by requests that queue throughout the detection window with no dynamic capacity to relieve them.
5. **Controller overhead remains flat**: Unchanged from v8 — CPU and RAM should be similar across modes.
6. **G8 passes for all 12 runs**: Unchanged. Cleanup gaps are still 240 s (180 s cooldown + 60 s margin).

### How the Duration Change Affects Each Measurement

| Measurement                          | v8 Result                                           | v9 Expected Change                                               | Why                                                                                                                                  |
| ------------------------------------ | --------------------------------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| **M6 — Blind spot rate**      | Push 0%, Poll-5s 0%, Poll-12s 25.3%, Poll-30s 67.9% | **Identical**                                              | Delivery mechanism unchanged. Blind spots are a function of polling cadence, not phase length.                                       |
| **M4 — Throughput**           | Poll-30s −19% mean, T1=72,820 (matched Push)       | **Consistently −30-50% across all 3 Poll-30s replicates** | Poll-30s detection (~150 s) exceeds phase duration (90–120 s). Even lucky poll alignment leaves only ~10–26 s of dynamic capacity. |
| **M5 — Timeout rate**         | Push 2.7–3.6%, Poll-30s 2.5–10.3% (overlapping)   | **Push ~3%, Poll-30s 15–25% (non-overlapping)**           | Requests issued during the blind spot time out before dynamic nodes arrive. No recovery window to absorb the queue.                  |
| **M8 — p95 latency**          | Poll-30s 13.5 s vs Push 8.0 s (+69%)                | **Poll-30s >20 s (wider gap)**                             | Longer queueing during the detection window, less relief from late-arriving nodes.                                                   |
| **M1 — Spawn count**          | Poll-30s μ=8.3 vs Push μ=29.0 (−71%)             | **Similar or larger gap**                                  | Fewer spawn opportunities in shorter phases. Poll-30s may miss spawn windows entirely.                                               |
| **M2 — Missed opportunities** | Push 5/12, Poll-30s 9/12                            | **Poll-30s gap widens**                                    | Shorter phases = fewer spawns per phase = more phases below the <1 spawn/60s threshold.                                              |
| **S0 — Staleness**            | Push 0.03s, Poll-30s 9.9s                           | **Identical**                                              | Staleness = polling cadence, not phase duration.                                                                                     |
| **Controller CPU/RAM**         | Flat across modes                                   | **Identical**                                              | Delivery mechanism unchanged.                                                                                                        |
| **G8**                         | All 12 PASS                                         | **All 12 PASS**                                            | Cleanup gaps unchanged (240 s > 180 s cooldown).                                                                                     |

## RQ Linkage

**Thesis RQ1**: How does telemetry delivery cadence affect reaction latency
and transient service quality during demand shifts?

v9 is the tightened replication of v8. Where v8 established the mechanism
(M6: blind spots are real and cadence-dependent) and the tail-latency signal
(M8: p95 +69–91%), v9 removes the phase-duration buffer that allowed Poll-30s
to partially recover. It isolates the detection window as the dominant
determinant of service quality by making it exceed the stress period — the
architectural condition that real separated monitoring systems face during
short-duration demand spikes.

## Independent Variable & Held-Constant Set

### Independent Variable

**Telemetry delivery mode**: Push (ZMQ at window close), Poll-5s (HTTP every
5 s), Poll-12s (HTTP every 12 s), Poll-30s (HTTP every 30 s).

### Held Constant (identical to v8 except phase durations)

| Parameter           | Value                                               | Notes                         |
| ------------------- | --------------------------------------------------- | ----------------------------- |
| CLIENTS             | 96                                                  | Identical to v8               |
| DEVICES             | 6000                                                | Identical to v8               |
| NODES               | 100                                                 | Identical to v8               |
| MAX_DYNAMIC_COMPUTE | 12                                                  | Identical to v8               |
| STORAGE_CPUS        | 0.08                                                | Identical to v8               |
| STORAGE_MEMORY      | 512m                                                | Identical to v8               |
| EDGE_CPUS           | 0.30                                                | Identical to v8               |
| EDGE_MEMORY         | 256m                                                | Identical to v8               |
| CURL_MAX_TIME       | 30                                                  | Identical to v8               |
| CPU_SPAN            | 40                                                  | Identical to v8               |
| WAN_RTT_MS          | 185                                                 | Identical to v8               |
| RANDOM_SEED         | 42                                                  | Identical to v8               |
| DATA_SEED           | 42                                                  | Identical to v8               |
| Phases              | `phases.json` (edited in place with v9 durations) | v8`phases_gap.json` retired |
| Controller env      | `current_state_integrated.env`                    | Identical to v8               |
| Docker images       | Same as v8                                          | No rebuild needed             |
| Aggregation window  | 10 s                                                | Identical to v8               |

### v9 Phases (`phases.json`)

| # | Phase                      | Duration           | Rate/client | Cross-region | Client frac | Dominant mix                          |
| - | -------------------------- | ------------------ | ----------- | ------------ | ----------- | ------------------------------------- |
| 1 | `baseline`               | 60 s               | 1.0         | 0%           | 10%         | 60% lookup, 25% ranking, 15% pressure |
| 2 | `storage_storm`          | **120 s** ← | 4.0         | 90%          | 100%        | 35% lookup, 30% update, 20% aggregate |
| 3 | `cleanup_gap_1`          | 240 s              | 0.5         | 0%           | 5%          | baseline mix                          |
| 4 | `tier1_hotspot`          | **90 s** ←  | 5.0         | 40%          | 100%        | 80% lookup                            |
| 5 | `inter_hotspot_cooldown` | 300 s              | 1.0         | 0%           | 10%         | baseline mix                          |
| 6 | `reverse_hotspot`        | **90 s** ←  | 5.0         | 40%          | 100%        | 80% lookup                            |
| 7 | `cleanup_gap_2`          | 240 s              | 0.5         | 0%           | 5%          | baseline mix                          |
| 8 | `compute_spike`          | **90 s** ←  | 2.0         | 0%           | 100%        | 100% service_pressure                 |
| 9 | `demand_drop`            | 300 s              | 1.0         | 0%           | 10%         | baseline mix                          |

**Total**: 1530 s (~25.5 min). ← marks v8→v9 changes.

### Detection-Window vs Phase-Duration Math

Push and Poll-30s detection times are not single points — they vary with poll
alignment, breach severity, and cooldown state. The numbers below use v8-observed
ranges:

```
Push detection:     12–91 s (v8 observed, non-initial spawns; 5-window sliding + 45s cooldown)
Poll-30s detection: 76–670 s (v8 observed range; 5 polls × 30 s + blind-spot accumulation)
  Optimistic (poll aligned):  ~76 s (T2's 2 fast detections in v8)
  Typical (mid-cycle):       ~150 s
  Pessimistic (missed polls): ~500–670 s (T1 in v8; multi-cycle accumulation)

storage_storm (120 s):
  Push:     detects 12–91s → spawns 26–105s → 15–94s of dynamic capacity
  Poll-30s optimistic: detects ~76s → spawns ~90s → 30s (but only if poll aligns at ~20s into phase)
  Poll-30s typical:    detects ~150s → PHASE OVER → 0s
  Poll-30s pessimistic: detects 500–670s → phase long over → 0s

tier1_hotspot / reverse_hotspot / compute_spike (90 s):
  Push:     detects 12–91s → spawns 26–105s → 0–64s of dynamic capacity
  Poll-30s optimistic: detects ~76s → spawns ~90s → at phase boundary (0s margin)
  Poll-30s typical:    detects ~150s → PHASE OVER → 0s
  Poll-30s pessimistic: detects 500–670s → phase long over → 0s
```

**Key insight**: 90 s phases eliminate even the optimistic Poll-30s case
(76+14=90 s, at the phase boundary with zero margin for request service).
`storage_storm` at 120 s still allows an optimistic Poll-30s alignment (~30 s
of capacity), but the alignment window is narrow — the breach must occur within
~20 s of a poll that lands at ~t=60–76 s. This is approximately a 20/120 = 17%
probability per run, meaning 1 of 3 Poll-30s replicates may show partial recovery
in `storage_storm` but not in the 90 s phases.

## Run Matrix

v9 uses a **pilot-gated** execution model. The pilot (2 runs: Push + Poll-30s)
validates that the duration change produces the expected separation before
committing to the full 12-run campaign.

### Phase A — Pilot (2 runs)

| #  | Label                   | Mode     | Phases          | TELEMETRY_SOURCE | POLL_INTERVAL_S |
| -- | ----------------------- | -------- | --------------- | ---------------- | --------------- |
| P0 | `rq1_v9_push_pilot`   | Push     | `phases.json` | *(default)*    | —              |
| T0 | `rq1_v9_poll30_pilot` | Poll-30s | `phases.json` | `poll`         | 30              |

**Order**: P0 → T0. Each run: ~25.5 min. Pilot wall-clock: ~60 min.

### Pilot Gate — Go/No-Go Criteria

After both pilot runs complete, check against these criteria before proceeding
to Phase B:

| Criterion                         | Threshold                                      | Check                                                                                                       |
| --------------------------------- | ---------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| **Throughput separation**   | Poll-30s throughput ≤ 85% of Push throughput  | Must hold. If Poll-30s ≥ 85% of Push, the duration change is insufficient.                                 |
| **Timeout rate separation** | Poll-30s timeout rate ≥ 2× Push timeout rate | Must hold. Overlapping timeout rates = duration change didn't force the gap.                                |
| **M6 blind spot rate**      | Poll-30s blind spot rate ≥ 60%                | Sanity check — the mechanism should still be present. If <60%, something is wrong with the polling config. |
| **G8**                      | Both runs PASS (no spawns during cleanup gaps) | Must hold. G8 failure = phases file error or cooldown misconfiguration.                                     |

If all criteria pass → proceed to Phase B (full campaign).
If any criterion fails → **stop**. Do not run Phase B. The phase durations or
other parameters need adjustment. Report which criteria failed with the pilot
run data so the experiment designer can iterate.

### Phase B — Full Campaign (10 additional runs)

Only executed if the pilot gate passes. Adds Push and Poll-30s replicates
plus the intermediate modes.

| #  | Label               | Mode     | Phases          | TELEMETRY_SOURCE | POLL_INTERVAL_S |
| -- | ------------------- | -------- | --------------- | ---------------- | --------------- |
| P1 | `rq1_v9_push_2`   | Push     | `phases.json` | *(default)*    | —              |
| P2 | `rq1_v9_push_3`   | Push     | `phases.json` | *(default)*    | —              |
| F1 | `rq1_v9_poll5_1`  | Poll-5s  | `phases.json` | `poll`         | 5               |
| F2 | `rq1_v9_poll5_2`  | Poll-5s  | `phases.json` | `poll`         | 5               |
| F3 | `rq1_v9_poll5_3`  | Poll-5s  | `phases.json` | `poll`         | 5               |
| W1 | `rq1_v9_poll12_1` | Poll-12s | `phases.json` | `poll`         | 12              |
| W2 | `rq1_v9_poll12_2` | Poll-12s | `phases.json` | `poll`         | 12              |
| W3 | `rq1_v9_poll12_3` | Poll-12s | `phases.json` | `poll`         | 12              |
| T1 | `rq1_v9_poll30_2` | Poll-30s | `phases.json` | `poll`         | 30              |
| T2 | `rq1_v9_poll30_3` | Poll-30s | `phases.json` | `poll`         | 30              |

**Phase B order**: P1→P2→F1→F2→F3→W1→W2→W3→T1→T2.
Phase B wall-clock: ~5.3 h (255 min runtime + ~60 min overhead).

### Combined (if pilot passes)

**Total: 12 runs** (2 pilot + 10 Phase B). n=3 per mode (P0+P1+P2, F1+F2+F3,
W1+W2+W3, T0+T1+T2). Total wall-clock: ~6.3 h.

## Run Configuration

### Prerequisites

#### 1. Merge `phases_gap.json` into `phases.json` then delete `phases_gap.json`

`phases.json` (the canonical file) currently lacks the `cleanup_gap_1` and
`cleanup_gap_2` phases. `phases_gap.json` has the correct 9-phase gap structure
but v8 durations. Steps:

```bash
# On cloud-vm:
cd ~/efficient-storage-in-edge-scenarios/source/scripts/testing

# Copy gap structure into canonical file
cp phases_gap.json phases.json

# Edit stress-phase durations in phases.json:
#   storage_storm: 240 → 120
#   tier1_hotspot: 180 → 90
#   reverse_hotspot: 180 → 90
#   compute_spike: 180 → 90

# Remove the now-retired duplicate
rm phases_gap.json
```

After this, `phases.json` is the sole canonical phases file with the v9
durations. The run folder will capture `phases_snapshot.json`.

#### 2. Verify Docker images still exist

```bash
ssh cloud-vm "docker images --format '{{.Repository}} {{.ID}}' | grep edge_server"
```

The v8 `edge_server` image (ID `9f5721ed980e`, rebuilt without
EDGE_MAX_CONCURRENT) must be present. If missing, rebuild before the first run.

### Phase A — Pilot Runs

#### Push Pilot (P0)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients \
    setup_test_data run_experiment \
  RUN_LABEL=rq1_v9_push_pilot \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=185 CLIENTS=96 STORAGE_CPUS=0.08 STORAGE_MEMORY=512m \
  CURL_MAX_TIME=30 RANDOM_SEED=42 DATA_SEED=42 \
  > /tmp/rq1_v9_push_pilot.log 2>&1 &"
```

#### Poll-30s Pilot (T0)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients \
    setup_test_data run_experiment \
  RUN_LABEL=rq1_v9_poll30_pilot \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=30 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=185 CLIENTS=96 STORAGE_CPUS=0.08 STORAGE_MEMORY=512m \
  CURL_MAX_TIME=30 RANDOM_SEED=42 DATA_SEED=42 \
  > /tmp/rq1_v9_poll30_pilot.log 2>&1 &"
```

#### Pilot Gate Check (after both runs)

After both pilot runs complete and post-run workflow is executed for each,
evaluate the gate criteria from the Run Matrix section:

1. **Throughput**: `client_requests.csv` → total completions per run. T0 ≤ 0.85 × P0.
2. **Timeout rate**: `client_requests.csv` → http_status=0 count / total. T0 timeout rate ≥ 2× P0.
3. **M6**: `analysis/rq1/rq1_blind_spot_windows.csv` → blind_spot rate. T0 ≥ 60%.
4. **G8**: `node_lifecycle_timings.csv` → no spawns during cleanup_gap phases.

If all pass → proceed to Phase B.
If any fail → **stop and report**. Do not run Phase B.

### Phase B — Full Campaign

Only executed if the pilot gate passes. Same invocation pattern as pilot,
with labels adjusted:

#### Push (P1, P2)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients \
    setup_test_data run_experiment \
  RUN_LABEL=<LABEL> \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=185 CLIENTS=96 STORAGE_CPUS=0.08 STORAGE_MEMORY=512m \
  CURL_MAX_TIME=30 RANDOM_SEED=42 DATA_SEED=42 \
  > /tmp/<LABEL>.log 2>&1 &"
```

#### Poll-5s (F1–F3)

Same as Push, with:

```
TELEMETRY_SOURCE=poll POLL_INTERVAL_S=5
```

#### Poll-12s (W1–W3)

Same as Push, with:

```
TELEMETRY_SOURCE=poll POLL_INTERVAL_S=12
```

#### Poll-30s (T1, T2)

Same as Push, with:

```
TELEMETRY_SOURCE=poll POLL_INTERVAL_S=30
```

> **Note**: `PHASES_CONFIG=testing/phases.json` replaces v8's `testing/phases_gap.json`.
> The `phases_gap.json` file is retired. After v9, `phases.json` is the canonical
> RQ1 workload (cleanup-gap configuration with tightened stress phases).
> Docker images are unchanged from v8 — no rebuild needed.

## Focus & Evidence

### Primary Evidence (same structure as v8)

| Artifact                                     | What it shows                         | v9 Focus                                                                                                                                                 |
| -------------------------------------------- | ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `analysis/rq1_blind_spot_windows.csv` (M6) | Breached windows unseen by controller | **Expect identical to v8.** Confirms mechanism is stable.                                                                                          |
| `client_requests.csv`                      | Per-phase request count, http_status  | **Primary change expected.** Throughput gap should be consistent across all 3 Poll-30s replicates. Timeout rate should separate cleanly from Push. |
| `analysis/rq1_reaction_latency.csv`        | Breach detection + provision time     | Survivor bias still applies (see Validity Threats), but fewer detected events overall.                                                                   |
| `analysis/rq1_endpoint_latency.csv` (M8)   | Per-endpoint p50/p95/p99 per phase    | **Expect wider p95 gap.** Poll-30s >20 s vs Push ~8 s.                                                                                             |

### Secondary Evidence

| Artifact                                           | What it shows                                    |
| -------------------------------------------------- | ------------------------------------------------ |
| `analysis/rq1_staleness.csv`                     | Information age at consumption (identical to v8) |
| `analysis/rq1/rq1_overhead.csv`                  | Controller CPU%, RSS per mode (identical to v8)  |
| `analysis/rq1/rq1_decision_quality.csv`          | Breached windows vs spawns per phase             |
| `analysis/rq1/rq1_missed_opportunities.csv` (M2) | Phases with CPU pressure but no spawns           |
| `node_lifecycle_timings.csv`                     | Spawn timing relative to phase start (check G8)  |
| `container_events.csv`                           | Dynamic node lifecycle (spawn/stop)              |
| `analysis/rq1/rq1_timeout_root_cause.csv` (M7)   | Failure composition                              |

### Excluded from v9 Analysis

| Metric                           | Reason                                                                                                |
| -------------------------------- | ----------------------------------------------------------------------------------------------------- |
| **M3 — Time-to-capacity** | Non-discriminating in v8 (all runs "not_achieved"). Threshold too strict for this workload intensity. |
| **M9 — Recovery lag**     | Not differentiated by telemetry cadence in v8 (cooldown-gated, not information-gated).                |

## Metrics & Success Criteria

These are **measurements to report**, not pass/fail gates.

| Measurement                         | v9 Expectation                                                            | Evidence                               | v8 Baseline                                         |
| ----------------------------------- | ------------------------------------------------------------------------- | -------------------------------------- | --------------------------------------------------- |
| **Blind spot rate** (M6)      | Push 0%, Poll-5s 0%, Poll-12s ~25%, Poll-30s ~68%                         | `rq1_blind_spot_windows.csv`         | Push 0%, Poll-5s 0%, Poll-12s 25.3%, Poll-30s 67.9% |
| **Throughput** (M4)           | Poll-30s**−30-50% below Push, consistent across all 3 replicates** | `client_requests.csv` per-run totals | Poll-30s −19% mean, σ=14K (T1 matched Push)       |
| **Timeout rate** (M5)         | Push ~3%, Poll-30s**15–25% across all replicates**                 | `client_requests.csv` http_status=0  | Push 2.7–3.6%, Poll-30s 2.5–10.3% (overlapping)   |
| **p95 latency** (M8)          | Poll-30s**>20 s** vs Push ~8 s                                      | `rq1_endpoint_latency.csv`           | Poll-30s 13.5 s vs Push 8.0 s (+69%)                |
| **Reaction events detected**  | Push=15, Poll-5s=15, Poll-12s=15, Poll-30s**<8 (fewer than v8)**    | `rq1_reaction_latency.csv`           | Push=15, Poll-30s=8                                 |
| **Spawn count** (M1)          | Poll-30s <10 per run vs Push ~29                                          | `node_lifecycle_timings.csv`         | Poll-30s 8.3 vs Push 29.0                           |
| **Missed opportunities** (M2) | Poll-30s >9/12 (worse than v8)                                            | `rq1_missed_opportunities.csv`       | Push 5/12, Poll-30s 9/12                            |
| **Controller CPU/RAM**        | Flat across modes                                                         | `rq1_overhead.csv`                   | Push 10.4%/78MB, Poll-30s 7.2%/76MB                 |
| **Staleness** (S0)            | Push ~0s, Poll-30s ~10s (identical to v8)                                 | `rq1_staleness.csv`                  | Push 0.03s, Poll-30s 9.9s                           |
| **G8**                        | All 12 PASS                                                               | `node_lifecycle_timings.csv`         | All 12 PASS                                         |

### Success Gate (for the analyst)

The primary v8→v9 differentiation criterion: **Poll-30s throughput must be
consistently below Push across all three replicates, with no Poll-30s run
within 15% of Push's per-run minimum within v9.** This is a relative gate
(not anchored to v8 absolutes, since v9 total request volume is lower).

In v8, T1 (72,820) exceeded Push's mean (67,292) — a Poll-30s run outperformed
the average Push run. In v9, this must not happen. The minimum acceptable
separation: Push's lowest-throughput replicate must exceed Poll-30s's
highest-throughput replicate by at least 15%. If Push min = X and Poll-30s
max = Y, require X > 1.15Y.

Expected v9 Push range: approximately 40,000–48,000 (v8 scaled by ~60% to
account for halved stress-phase duration). Expected Poll-30s range:
approximately 20,000–32,000 (static-node floor plus modest recoveries in
`storage_storm` optimistic cases).

## Post-Run Workflow

Identical to v8. After each run:

1. Fix ownership: `sudo chown -R testop:testop <run_dir>`
2. Parse logs: `parse_elasticity_logs.py` → `elasticity_events.csv`, `node_lifecycle_timings.csv`
3. Statistics: `metrics_stats.py` with `--by-phase --by-lan --by-endpoint`
4. Generic graphs: `cli_overview`, `cli_simple_run`, `cli_phase_summary`, `cli_endpoint_breakdown`, `cli_scale_down`, `cli_lifecycle_gantt`, `cli_cpu_drivers`, `cli_tdb_drivers`
5. RQ1-specific CLIs: `missed_opportunities`, `time_to_capacity` (generated but not analyzed), `blind_spot_windows`, `timeout_root_cause`, `endpoint_latency`, `recovery_lag` (generated but not analyzed), `decision_quality`, `timings`, `overhead`
6. G8 check
7. Cross-mode comparison: `generate_comparison_graphs.py` after all 12 runs

## Validity Threats & Limitations

1. **Shorter phases reduce total request count.** v9 stress phases total 390 s
   (vs v8's 780 s). Per-mode request totals will be lower, reducing statistical
   power for per-phase breakdowns. The cross-mode comparison should aggregate
   across replicates for per-phase analysis.
2. **Survivor bias in reaction latency persists.** Poll-30s will detect even
   fewer events than v8 (phase ends before detection). Mean reaction latency
   is still not a valid cross-mode comparison. The thesis should use reaction
   events detected and blind spot rate instead.
3. **Static-node throughput floor.** Even with zero dynamic spawns, the 2
   static edge servers per LAN will complete some requests. Throughput will not
   drop to zero for any mode. The expected v9 Poll-30s floor is approximately
   v8 T2 scaled by the duration reduction (~38,000 × 0.5 ≈ 19,000–22,000),
   reflecting the static-node baseline under halved stress-phase duration.
4. **Stress-to-non-stress ratio.** v9 stress phases total 390 s out of 1530 s
   (25.5%), down from v8's 780/1920 (40.6%). Most requests occur outside stress
   phases where all modes behave identically, diluting the aggregate throughput
   signal. Per-phase breakdown of throughput and timeout rate is essential for
   the analyst — the mode separation emerges within stress phases, not in the
   run-level total. Cross-mode comparison graphs must include per-phase views.
5. **inter_hotspot_cooldown at 300 s between two 90 s phases** is proportionally
   long (3.3× the stress phase). This is intentional to prevent cross-hotspot
   carryover, but it means the hotspot phases are temporally sparse. The
   absolute throughput numbers in hotspot phases will be lower due to shorter
   duration, not just the coordination gap — compare per-mode ratios, not
   absolute counts.
6. **M3 and M9 are generated but excluded from analysis.** M3 (time-to-capacity)
   was non-discriminating in v8. M9 (recovery lag) was cooldown-gated. These
   CSVs are produced for completeness but should not be cited in v9 conclusions
   unless the v9 data shows unexpected differentiation.

## Artifact Contract

Standard run-folder layout from `docs/operation/testing/testing_overview.md`:

- `client_requests.csv`, `resource_stats.csv`, `per_node_stats.csv`
- `container_events.csv`, `node_lifecycle_timings.csv`, `elasticity_events.csv`
- `controller_lan1.log`, `controller_lan2.log`
- `phases_snapshot.json`, `controller_env_snapshot.env`
- `analysis/rq1/` with all RQ1 CSVs listed in Focus & Evidence
- 15 PNGs per run (generic + RQ1-specific)
- Cross-mode comparison: `graphs/comparison/` with 8+ PNGs + decision quality CSV
