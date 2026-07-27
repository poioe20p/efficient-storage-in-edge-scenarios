# RQ1 v11 Calibration — Storage Cascade Sweep

**Status**: 📋 Planned · **Date**: 2026-07-25
**Predecessor**: [`../v10/experiment_plan_v10.md`](../v10/experiment_plan_v10.md)
**Thesis RQ**: [`docs/research_questions/rq1/rq1_v3.md`](../../../research_questions/rq1/rq1_v3.md)

## Intent

v10 established that at `EDGE_CPUS=0.15`, the Push vs Poll-30s coordination gap
exists directionally — throughput −14%, p95 +28%, and the `storage_storm` phase
shows the correct timeout direction (P30 7.7% vs Push 4.6%). But the gap doesn't
cascade into consistent, user-visible timeout separation because:

1. **The static edge nodes queue, they don't drop.** At `CURL_MAX_TIME=30`,
   queued requests complete before timing out — the timeout bucket absorbs
   the differentiation signal.

2. **The hotspot phases aren't storage-dependent enough.** At 0.40
   cross-region ratio, hotspots are compute-bound. The blind spot only
   produces a visible gap when storage is the cascade trigger.

3. **Storage at 0.08 CPUs is comfortable.** Tightening storage forces the
   cascade to start at the data layer, amplifying the 20s detection gap.

v11 Calibration sweeps the parameters that determine whether the 20s blind
spot produces visible failure: **storage CPU allocation**, **cross-region
request ratio**, and **client timeout**.

The calibration runs pairwise (Push + Poll-30s) across up to 6 configurations,
evaluating after each pair. The first configuration that passes the separation
gate becomes the winner for a full n=3 campaign.

## Hypothesis / Expected Outcome

1. **Storage tightening amplifies the cascade.** At `STORAGE_CPUS ≤ 0.06`, each
   cross-region storage operation takes longer. During stress phases, the
   storage tier saturates before the edge tier. Push detects storage saturation
   in ~10s and spawns storage nodes. Poll-30s stays blind for 30s — during
   which storage degrades further, edge servers queue waiting for storage, and
   the cascade propagates through TWO tiers instead of one.

2. **Cross-region ratio makes hotspots storage-dependent.** At 0.70
   cross-region in `tier1_hotspot` and `reverse_hotspot`, 70% of lookups cross
   the WAN to remote storage. The same storage cascade that already produces
   correct timeout direction in `storage_storm` (0.90 cross-region) now
   applies to hotspot phases too — fixing the inversion observed in v10.

3. **Tighter timeout exposes queuing.** At `CURL_MAX_TIME=20`, requests that
   queue for 20-30s time out instead of completing. Poll-30s, with 20s more
   blind-spot queuing, loses proportionally more requests — widening the
   timeout gap even without additional CPU constraint.

## Independent Variables

| Parameter | v10 Value | Calibration Values | Rationale |
|-----------|----------|--------------------|-----------|
| `STORAGE_CPUS` | 0.08 | **0.06, 0.05** | Storage becomes cascade bottleneck; each operation slower |
| Hotspot `cross_region_ratio` | 0.40 | **0.70** | Makes hotspots storage-dependent like `storage_storm` |
| `CURL_MAX_TIME` | 30 | **20** | Tighter timeout bucket exposes queuing as timeouts |

### Held Constant (from v10)

| Parameter | Value | Notes |
|-----------|-------|-------|
| `EDGE_CPUS` | **0.15** | v10 proved Push handles this (94%+ success) |
| `CLIENTS` | 96 | Same as v8/v10 |
| `WAN_RTT_MS` | 185 | Same as v8/v10 |
| `STORAGE_MEMORY` | 512m | Same as v8/v10 |
| `RANDOM_SEED` | 42 | |
| `DATA_SEED` | 42 | |
| Phases | `phases.json` (9-phase cleanup-gap) | Edited in place for cross-region configs |
| Controller env | `current_state_integrated.env` | Same as v8/v10 |

## Configuration at a Glance

### Make Variables (per-run)

| Variable | S1 | S2 | C1 | C2 | T1 | T2 |
|----------|----|----|----|----|----|----|
| `EDGE_CPUS` | **0.15** | **0.15** | **0.15** | **0.15** | **0.15** | **0.15** |
| `STORAGE_CPUS` | **0.06** | **0.05** | **0.06** | **0.05** | **0.06** | **0.05** |
| `CURL_MAX_TIME` | 30 | 30 | 30 | 30 | **20** | **20** |
| `CLIENTS` | 96 | 96 | 96 | 96 | 96 | 96 |
| `WAN_RTT_MS` | 185 | 185 | 185 | 185 | 185 | 185 |
| `STORAGE_MEMORY` | 512m | 512m | 512m | 512m | 512m | 512m |
| `RANDOM_SEED` | 42 | 42 | 42 | 42 | 42 | 42 |
| `DATA_SEED` | 42 | 42 | 42 | 42 | 42 | 42 |
| `PHASES_CONFIG` | `testing/phases.json` | same | same | same | same | same |
| `OSKEN_ENV_OVERRIDE_FILE` | `testing/controller_env_overrides/current_state_integrated.env` | same | same | same | same | same |
| `TELEMETRY_SOURCE` | (Push runs) | — | — | — | — | — |
| `TELEMETRY_SOURCE` / `POLL_INTERVAL_S` | (P30: `poll` / `30`) | same | same | same | same | same |

### Phases File

The canonical `source/scripts/testing/phases.json` has the 9-phase cleanup-gap
structure (total 1920 s). Two variants used:

| Variant | Configs | `tier1_hotspot.cross_region_ratio` | `reverse_hotspot.cross_region_ratio` |
|---------|---------|-----------------------------------|--------------------------------------|
| **Baseline (v10)** | S1, S2 | **0.40** | **0.40** |
| **High cross-region** | C1, C2, T1, T2 | **0.70** | **0.70** |

All other phases identical across variants. Edit `phases.json` in place
before the first run of C1; restore to 0.40 after T2 or when calibration
completes. Each run's `phases_snapshot.json` captures the active config.

Full phase list (unchanged across all configs except as noted above):

| # | Phase | Duration | Rate | Cross-Region | Client % | Key Mix |
|---|-------|----------|------|-------------|----------|---------|
| 1 | `baseline` | 60s | 1.0 | 0.00 | 10% | 60% lookup, 25% ranking |
| 2 | `storage_storm` | 240s | 4.0 | 0.90 | 100% | 35% lookup, 30% update, 20% aggregate |
| 3 | `cleanup_gap_1` | 240s | 0.5 | 0.00 | 5% | 60% lookup, 25% ranking |
| 4 | `tier1_hotspot` | 180s | 5.0 | **0.40 or 0.70** | 100% | 80% lookup |
| 5 | `inter_hotspot_cooldown` | 300s | 1.0 | 0.00 | 10% | 60% lookup, 25% ranking |
| 6 | `reverse_hotspot` | 180s | 5.0 | **0.40 or 0.70** | 100% | 80% lookup |
| 7 | `cleanup_gap_2` | 240s | 0.5 | 0.00 | 5% | 60% lookup, 25% ranking |
| 8 | `compute_spike` | 180s | 2.0 | 0.00 | 100% | 100% service_pressure |
| 9 | `demand_drop` | 300s | 1.0 | 0.00 | 10% | 60% lookup, 25% ranking |

### Controller Env Override

`source/scripts/testing/controller_env_overrides/current_state_integrated.env`
— **unchanged from v10 for ALL configs.** Key thresholds:

| Parameter | Value | Notes |
|-----------|-------|-------|
| `MAX_DYNAMIC_STORAGE` | 8 | Storage node cap |
| `MAX_DYNAMIC_COMPUTE` | 12 | Compute node cap |
| `SCALEUP_COMPUTE_BASE_THRESHOLD` | 0.18 | CPU fraction trigger |
| `SCALEUP_STORAGE_BASE_THRESHOLD` | 0.35 | Storage latency trigger |
| `SCALEDOWN_COMPUTE_COOLDOWN_S` | 180 | < cleanup_gap (240s) — ensures G8 |
| `SCALEUP_STORAGE_COOLDOWN_S` | 120 | Storage respawn cooldown |

### What Changes Between Configs (and Why)

| Config | What Changes | Why |
|--------|-------------|-----|
| **v10 → S1** | `STORAGE_CPUS`: 0.08 → **0.06** | Storage ops ~25% slower. Cascade starts at data layer — Push detects storage saturation in ~10s, P30 blind for 30s. |
| **S1 → S2** | `STORAGE_CPUS`: 0.06 → **0.05** | Storage ops ~38% slower than v10. If S1's −25% doesn't produce enough separation. |
| **S2 → C1** | Phases: hotspot CR 0.40 → **0.70**; `STORAGE_CPUS` back to 0.06 | 70% of hotspot lookups now cross WAN to remote storage. Fixes v10's hotspot timeout inversion. |
| **C1 → C2** | `STORAGE_CPUS`: 0.06 → **0.05** | If C1 direction correct but magnitude too small for gate. |
| **C2 → T1** | `CURL_MAX_TIME`: 30 → **20**; `STORAGE_CPUS` back to 0.06 | Requests queued 20-30s now time out instead of completing. P30 loses more (20s extra blind-spot queuing). |
| **T1 → T2** | `STORAGE_CPUS`: 0.06 → **0.05** | Maximum amplification — all three levers at strongest. |

### Why Poll-30s First, Then Push Only If Promising

v10 proved that single-pilot calibration is unreliable: the C2 pilot (n=1)
showed clean Push vs Poll-30s separation that did not replicate at n=3.
But running Push blindly for every config wastes time — if Poll-30s doesn't
show degradation, the config is dead regardless of Push.

**Run order for every config:**
1. **Poll-30s #1** → evaluate against v10 Poll-30s baseline
2. **Poll-30s #2** → only if #1 was promising
3. **Push #1 and #2** → only after both Poll-30s runs confirm degradation

**Poll-30s promising threshold** (vs v10 Poll-30s ranges):

| Signal | Threshold | v10 P30 Range | Rationale |
|--------|-----------|---------------|-----------|
| Timeout ≥ 5% | Above all v10 P30 | 2.9–4.7% | Storage cascade amplifies timeouts |
| Throughput ≤ 60K | Below all v10 P30 | 61.8–65.7K | Storage cascade reduces throughput |
| p50 latency ≥ 80ms | Above all v10 P30 | 16.5–83.2ms | Blind-spot queuing inflates median |
| p95 latency ≥ 18s | Above all v10 P30 | 16.4–17.8s | Blind-spot queuing inflates tail |
| Latency stddev ↑ | Higher than v10 P30 | ~5.7–7.2s est. | Blind spot increases variance |

**Any ONE of the five** triggers "promising" → run Poll-30s #2 to confirm.

If Poll-30s #1 hits either threshold → run #2 to confirm.
If Poll-30s #1 misses both → config is dead; skip to next config (saves 90+ min).
If both Poll-30s runs confirm degradation → run Push #1 and #2 to measure the gap.

**Winner condition**: Both Push runs pass sanity (≤10% timeout) AND gate:
P30 μ ≤ 80% of Push μ, P30 μ timeout ≥ 2× Push μ timeout, G8 all 4 runs.

### Run Order & Config Rationale

Each config amplifies a specific part of the blind-spot cascade, ordered
from simplest change to most aggressive:

| # | Config | STORAGE | CR | CT | Runs | Why This Config |
|---|--------|---------|-----|-----|------|-----------------|
| **S1** | Storage cascade | **0.06** | 0.40 | 30 | 4 | v10 proved the gap exists in `storage_storm` (correct timeout direction) but not hotspots. Tightening storage from 0.08→0.06 makes every storage operation ~25% slower. The cascade starts at the data layer — Push detects in ~10s and spawns storage nodes, P30 stays blind for 30s while storage degrades further. This should widen the gap in `storage_storm` AND start propagating it to `tier1_hotspot` and `reverse_hotspot` (which still have 0.40 cross-region — less storage-dependent, but now storage is slower). |
| **S2** | Aggressive storage | **0.05** | 0.40 | 30 | 4 | If S1's −25% storage slowdown doesn't amplify enough, S1's −38% should. Higher risk of both modes failing (Push timeout >10%). |
| **C1** | Storage + cross-region | **0.06** | **0.70** | 30 | 4 | If S1 produces a gap but doesn't fix the hotspot timeout inversion, C1 makes hotspots explicitly storage-dependent: 70% of hotspot lookups now cross the WAN to remote storage. Combined with STORAGE=0.06, hotspots now face the same storage cascade that `storage_storm` already proves produces correct timeout direction. |
| **C2** | Aggressive storage + cross-region | **0.05** | **0.70** | 30 | 4 | If C1 produces separation but the magnitude is too small for the gate (e.g., P30 timeout only 1.5× Push instead of ≥2×), C2's more aggressive storage amplifies further. |
| **T1** | Storage + cross-region + timeout | **0.06** | **0.70** | **20** | 4 | If C1/C2 produce the correct direction but the timeout gap is absorbed by the 30s CURL_MAX_TIME bucket (requests queue but still complete), T1 tightens the bucket to 20s. Queued requests that would have completed at 20-30s now time out. P30, with 20s more blind-spot queuing, loses proportionally more. |
| **T2** | Maximum amplification | **0.05** | **0.70** | **20** | 4 | All three amplifiers at their strongest. If nothing else works — this is the last resort before declaring the sweep failed. |

**Maximum: 24 calibration runs (6 configs × 4 runs).** Stop early when a
config wins (both replicates pass all 4 gates). Each run: ~32 min (1920 s
phases) + ~15 min setup. Per-config wall-clock: ~3.5 hours. Total worst-case:
~21 hours.

### Sequential Gate Logic

For each config, run all 4 runs (2 Push, 2 Poll-30s). After all 4 complete:

| Criterion | Threshold | Applies To | Rationale |
|-----------|-----------|------------|-----------|
| Throughput separation | P30 μ ≤ 80% of Push μ | Mean across replicates | Blind-spot throughput penalty |
| Timeout rate separation | P30 μ ≥ 2× Push μ | Mean across replicates | Blind-spot timeout penalty |
| p50 latency separation | P30 μ p50 ≥ 2× Push μ p50 | Mean across replicates | Median shifts under blind-spot queuing |
| p95 latency separation | P30 μ p95 ≥ 1.5× Push μ p95 | Mean across replicates | Tail inflates under blind-spot queuing |
| Latency variance | P30 σ > Push σ | Per-mode stddev | Blind spot increases latency dispersion |
| Push sanity | Each Push run ≤ 10% timeout | Per-replicate | Config must not break Push |
| G8 | All 4 runs PASS | Per-replicate | No spawns in cleanup gaps |

**Winner condition: ALL 7 gates pass.** If any gate fails, proceed to next
config. If a single Push run exceeds 10% timeout, the config is too
aggressive — skip to the next config.

**If no config passes after T2**: the sweep has failed. Document v10 as the
definitive finding — the throughput gap exists (−14%) but the timeout
signal requires constraints outside the tested space. Accept as a bounded
negative result and return to v8 as the thesis campaign.

### Cross-Region Modification

For C1/C2/T1/T2, edit `phases.json` in place. Change only `cross_region_ratio`
in `tier1_hotspot` and `reverse_hotspot`:

| Phase | v10 value | Calibration value |
|-------|-----------|-------------------|
| `tier1_hotspot` | 0.40 | **0.70** |
| `reverse_hotspot` | 0.40 | **0.70** |

All other phases unchanged. Restore to 0.40 after cross-region configs complete
(if moving to S1/S2 or after calibration ends).

### CURL_MAX_TIME Override

For T1/T2, pass `CURL_MAX_TIME=20` in the Make invocation. No file edits needed.

## Run Configuration

### Pre-Run Cleanup (between every run)

```bash
ssh cloud-vm "sudo python3 /tmp/clean_ns.py && \
  sudo -n bash ~/efficient-storage-in-edge-scenarios/source/scripts/cleanup.sh"
```

### Common Parameters (all runs)

```
EDGE_CPUS=0.15
PHASES_CONFIG=testing/phases.json
OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env
WAN_RTT_MS=185 CLIENTS=96 STORAGE_MEMORY=512m
RANDOM_SEED=42 DATA_SEED=42
```

### S1 — Storage Cascade (STORAGE_CPUS=0.06) — 4 runs

```bash
# S1 Push (2 replicates)
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients \
    setup_test_data run_experiment \
  RUN_LABEL=rq1_v11c_s1_push_1 \
  STORAGE_CPUS=0.06 CURL_MAX_TIME=30 \
  > /tmp/rq1_v11c_s1_push_1.log 2>&1 &"

ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients \
    setup_test_data run_experiment \
  RUN_LABEL=rq1_v11c_s1_push_2 \
  STORAGE_CPUS=0.06 CURL_MAX_TIME=30 \
  > /tmp/rq1_v11c_s1_push_2.log 2>&1 &"

# S1 Poll-30s (2 replicates)
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients \
    setup_test_data run_experiment \
  RUN_LABEL=rq1_v11c_s1_poll30_1 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=30 \
  STORAGE_CPUS=0.06 CURL_MAX_TIME=30 \
  > /tmp/rq1_v11c_s1_poll30_1.log 2>&1 &"

ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients \
    setup_test_data run_experiment \
  RUN_LABEL=rq1_v11c_s1_poll30_2 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=30 \
  STORAGE_CPUS=0.06 CURL_MAX_TIME=30 \
  > /tmp/rq1_v11c_s1_poll30_2.log 2>&1 &"
```

### S2–T2 Labels

Same pattern as S1. Each config has 4 run labels: `<config>_push_1`,
`<config>_push_2`, `<config>_poll30_1`, `<config>_poll30_2`.

| Config | STORAGE | CR | CT | Push labels | Poll-30s labels |
|--------|---------|-----|-----|-------------|-----------------|
| S2 | 0.05 | 0.40 | 30 | `rq1_v11c_s2_push_{1,2}` | `rq1_v11c_s2_poll30_{1,2}` |
| C1 | 0.06 | 0.70 | 30 | `rq1_v11c_c1_push_{1,2}` | `rq1_v11c_c1_poll30_{1,2}` |
| C2 | 0.05 | 0.70 | 30 | `rq1_v11c_c2_push_{1,2}` | `rq1_v11c_c2_poll30_{1,2}` |
| T1 | 0.06 | 0.70 | 20 | `rq1_v11c_t1_push_{1,2}` | `rq1_v11c_t1_poll30_{1,2}` |
| T2 | 0.05 | 0.70 | 20 | `rq1_v11c_t2_push_{1,2}` | `rq1_v11c_t2_poll30_{1,2}` |

Commands identical to S1 template, substituting the config-specific
`STORAGE_CPUS`, `CURL_MAX_TIME`, and `RUN_LABEL`. For C1/C2/T1/T2,
edit `phases.json` hotspot `cross_region_ratio` to 0.70 before the first
run of the config.

### Run Monitoring

```bash
# Check if run is alive
ssh cloud-vm "pgrep -af 'run_experiment'"

# Tail the log
ssh cloud-vm "tail -20 /tmp/<LABEL>.log"

# Launch watchdog
python tools/watch_run.py --host cloud-vm --run-label <LABEL> --poll-interval 15 --timeout 5400
```

## Post-Calibration (Winner Found)

If a config passes all 4 gates, execute a full n=3 campaign on the winning
configuration across all four telemetry modes, following v10's structure:

| # | Label | Mode | STORAGE | CR | CT |
|---|-------|------|---------|-----|-----|
| P1–P3 | `rq1_v11_push_{1..3}` | Push | (winner) | (winner) | (winner) |
| T1–T3 | `rq1_v11_poll30_{1..3}` | Poll-30s | (winner) | (winner) | (winner) |
| F1–F3 | `rq1_v11_poll5_{1..3}` | Poll-5s | (winner) | (winner) | (winner) |
| W1–W3 | `rq1_v11_poll12_{1..3}` | Poll-12s | (winner) | (winner) | (winner) |

Sequential gate after T3: Push μ ≥ 85K, P30 μ ≤ 65K, Push TO ≤ 3%, P30 TO ≥ 4%,
G8 all 6. Same run commands as v10 with winning STORAGE_CPUS and CURL_MAX_TIME.

## Metrics & Success Criteria (Post-Calibration Campaign)

Same as v10 §Metrics & Success Criteria, adapted to winning configuration.

## Validity Threats

1. **Single EDGE_CPUS level.** v11 holds EDGE_CPUS=0.15 constant. If no
   config passes, it's possible a different edge CPU level (e.g., 0.18)
   would produce separation with the same storage cascade.

2. **Phase file edits are destructive.** Cross-region changes modify the
   canonical `phases.json` in place. Each run's `phases_snapshot.json`
   captures the active config. Restore to v10 values after calibration.

3. **Known stall bug.** Same as v10 — expect 3–5 launch attempts per run.
   Recovery: teardown_clients → cleanup.sh → clean_ns.py → retry.

## Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-07-26 | **Calibration complete. Winner: S2 + `--connect-timeout 5`.** See [results.md](./results.md). | G3 (p50) fails: Push serves 43% more requests, median higher — throughput artifact. |
| 2026-07-26 | Added `--connect-timeout 5` to `traffic_generator.py`. G2 flipped from 0.9× → 2.9×. | Catches TCP accept-queue failures during blind spot. |
| 2026-07-26 | Reversed run order: Poll-30s first. 5-signal evaluation, 7-gate criteria. | Running Push blindly wastes time; latency+stddev capture blind-spot mechanism. |
| 2026-07-25 | Plan authored. n=2 per config. | v10 showed gap exists directionally but timeout signal absent. |
