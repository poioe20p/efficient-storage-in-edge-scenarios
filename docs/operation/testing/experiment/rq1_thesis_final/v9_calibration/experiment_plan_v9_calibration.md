# RQ1 v9 Calibration — System Fragility Sweep

**Status**: 📋 Planned · **Date**: 2026-07-24
**Predecessor**: [`../v9/experiment_plan_v9.md`](../v9/experiment_plan_v9.md)
**Thesis RQ**: [`docs/research_questions/rq1/rq1_v2.md`](../../../research_questions/rq1/rq1_v2.md)

## Intent

v9's phase-duration reduction failed to produce a consistent throughput gap
because the system's static-node floor absorbs the coordination gap before it
cascades into user-visible failure — even with only 7 Poll-30s spawns vs 20
for Push.

v9 Calibration sweeps two parameters that directly attack this resilience:
**edge-server CPU allocation** and **per-client request rate**. Lower CPU
reduces the static nodes' capacity to absorb overload. Higher rate increases
the volume of requests that arrive during the blind spot. Either should force
the coordination gap to manifest as a measurable, consistent throughput and
timeout separation.

The calibration runs pairwise (Push + Poll-30s) across 5 configurations,
evaluating after each pair. The first configuration that passes a defined
separation gate becomes the winner. A full 12-run, 4-mode campaign is then
executed on the winning configuration.

## Hypothesis / Expected Outcome

1. **CPU reduction alone will produce a clear separation.** At EDGE_CPUS ≤ 0.15,
   the static nodes saturate under stress-phase load. Push detects and spawns;
   Poll-30s stays blind. The throughput gap should widen from v8's −19% mean
   to a consistent −30-50% across both replicates.

2. **Rate increase alone may work but risks saturation.** At 1.5× rate with
   v8 CPU, the system serves more requests but the static-to-dynamic ratio
   is unchanged. The gap may widen or may not — the blind spot's absolute
   request volume grows, but so does Push's service window.

3. **Combined CPU + rate (C5) is the most aggressive option.** If C1–C4 all
   fail, halved CPU with elevated rate should guarantee separation — but may
   also push Push into failure, eliminating the differentiation.

## What Changes and Why

| Parameter | v8 Value | Calibration Values | Rationale |
|-----------|----------|-------------------|-----------|
| `EDGE_CPUS` | 0.30 | **0.20, 0.15, 0.10** | Reduces static-node capacity. At 0.10, a single edge server can handle ~3× fewer concurrent requests before queuing. |
| Stress-phase rate | 1.0× | **1.5×** | Multiplies `rate_per_client` in `phases.json` for stress phases. Increases blind-spot request volume without changing phase duration. |
| `EDGE_MEMORY` | 256m | **Unchanged** | Edge workload is CPU-bound. Reducing to 128m risks OOM kills — noisy failure that doesn't differentiate modes. |
| Phases | v9 halved | **v8 durations** (restored) | v9 proved duration isn't the bottleneck. Longer phases give calibration more signal. |

| Config | EDGE_CPUS | Rate Multiplier | Stress-phase example rates |
|--------|-----------|-----------------|---------------------------|
| **C1** | 0.20 | 1.0× | storage_storm=4.0, hotspots=5.0, compute_spike=2.0 |
| **C2** | 0.15 | 1.0× | same |
| **C3** | 0.10 | 1.0× | same |
| **C4** | 0.15 | 1.5× | storage_storm=6.0, hotspots=7.5, compute_spike=3.0 |
| **C5** | 0.10 | 1.5× | same as C4 |

### Prerequisites

#### 1. Restore v8 Phase File

The current `phases.json` may have halved v9 durations or may lack the
`cleanup_gap_1`/`cleanup_gap_2` phases entirely. `phases_gap.json` on the
cloud VM has the correct 9-phase v8 cleanup-gap structure. Steps:

```bash
# On cloud-vm:
cd ~/efficient-storage-in-edge-scenarios/source/scripts/testing

# If phases_gap.json still exists (v9 plan didn't merge it):
cp phases_gap.json phases.json

# Verify durations are v8 values (not halved v9):
#   storage_storm: 240 s
#   tier1_hotspot: 180 s
#   reverse_hotspot: 180 s
#   compute_spike: 180 s
```

If `phases_gap.json` no longer exists, edit `phases.json` directly to ensure
it contains all 9 phases with v8 durations and the cleanup_gap structure.

#### 2. Verify Docker Images

```bash
ssh cloud-vm "docker images --format '{{.Repository}} {{.ID}}' | grep edge_server"
```

The v8 `edge_server` image must be present. If missing, rebuild.

### Restoring v8 Phase Durations

Before calibration, restore `phases.json` to v8 cleanup-gap durations:

| Phase | If v9 (current) | → v8 (restored) |
|-------|-----------------|-----------------|
| `storage_storm` | 120 s | **240 s** |
| `tier1_hotspot` | 90 s | **180 s** |
| `reverse_hotspot` | 90 s | **180 s** |
| `compute_spike` | 90 s | **180 s** |
| `cleanup_gap_1` | 240 s | **240 s** (unchanged) |
| `cleanup_gap_2` | 240 s | **240 s** (unchanged) |

All other parameters held constant from v8:
- `CLIENTS=96`, `DEVICES=6000`, `NODES=100`
- `WAN_RTT_MS=185`, `STORAGE_CPUS=0.08`, `STORAGE_MEMORY=512m`
- `CURL_MAX_TIME=30`, `RANDOM_SEED=42`, `DATA_SEED=42`
- Controller env: `current_state_integrated.env`
- Docker images: same as v8

## Calibration Run Matrix

### Sequential Gate Logic

Run each config pair (Push then Poll-30s). After both complete, evaluate:

| Criterion | Threshold |
|-----------|-----------|
| Throughput separation | Poll-30s ≤ 80% of Push throughput |
| Timeout rate separation | Poll-30s ≥ 2× Push timeout rate |
| Push sanity | Push timeout rate ≤ 10% (must not also be failing) |
| G8 | Both PASS |

**If all 4 pass → config wins. Stop calibration. Run full campaign.**
**If any fail → proceed to next config pair.**

### Config Pairs

Ordered by hypothesized likelihood of separation (CPU reduction first as the
primary driver, then CPU + rate combined):

| # | Label (Push / Poll-30s) | EDGE_CPUS | Rate × | Hypothesis |
|---|------------------------|-----------|--------|------------|
| C1 | `rq1_v9c_c1_push` / `_poll30` | 0.20 | 1.0× | Mild CPU reduction |
| C2 | `rq1_v9c_c2_push` / `_poll30` | 0.15 | 1.0× | Moderate CPU reduction |
| C3 | `rq1_v9c_c3_push` / `_poll30` | 0.10 | 1.0× | Heavy CPU reduction |
| C4 | `rq1_v9c_c4_push` / `_poll30` | 0.15 | 1.5× | Moderate CPU + rate |
| C5 | `rq1_v9c_c5_push` / `_poll30` | 0.10 | 1.5× | Heavy CPU + rate (most aggressive) |

**Maximum: 10 calibration runs.** Stop early if a config wins.
Each run: ~32 min (v8 phases). Per-pair wall-clock: ~90 min (includes
~5-10 min setup overhead per run).

**If no config passes after C5**: the sweep has failed. The system is
inherently too resilient for the coordination gap to manifest as a
consistent throughput/timeout separation under these parameter ranges.
Accept v8 as the definitive RQ1 campaign and report the calibration
results as a negative finding (bounding the conditions under which
telemetry cadence does *not* matter for user-visible metrics).

### Rate Multiplication

Rate × is applied by modifying `rate_per_client` in `phases.json` for
stress phases only (`storage_storm`, `tier1_hotspot`, `reverse_hotspot`,
`compute_spike`). Non-stress phases (baseline, cleanup gaps, cooldown,
demand_drop) use 1.0× rate regardless.

For C4/C5, `phases.json` stress-phase rates:

| Phase | Base rate | 1.5× |
|-------|-----------|------|
| `storage_storm` | 4.0 | **6.0** |
| `tier1_hotspot` | 5.0 | **7.5** |
| `reverse_hotspot` | 5.0 | **7.5** |
| `compute_spike` | 2.0 | **3.0** |

For C5 (EDGE_CPUS=0.15 + 1.5× rate), the combined stress is the most
aggressive configuration in the sweep.

## Run Configuration

### Common Parameters (all runs)

```
PHASES_CONFIG=testing/phases.json
OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env
WAN_RTT_MS=185 CLIENTS=96 STORAGE_CPUS=0.08 STORAGE_MEMORY=512m
CURL_MAX_TIME=30 RANDOM_SEED=42 DATA_SEED=42
```

### Push Runs (C1–C5)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients \
    setup_test_data run_experiment \
  RUN_LABEL=<LABEL> \
  EDGE_CPUS=<CONFIG_CPUS> \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=185 CLIENTS=96 STORAGE_CPUS=0.08 STORAGE_MEMORY=512m \
  CURL_MAX_TIME=30 RANDOM_SEED=42 DATA_SEED=42 \
  > /tmp/<LABEL>.log 2>&1 &"
```

### Poll-30s Runs (C1–C5)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients \
    setup_test_data run_experiment \
  RUN_LABEL=<LABEL> \
  EDGE_CPUS=<CONFIG_CPUS> \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=30 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=185 CLIENTS=96 STORAGE_CPUS=0.08 STORAGE_MEMORY=512m \
  CURL_MAX_TIME=30 RANDOM_SEED=42 DATA_SEED=42 \
  > /tmp/<LABEL>.log 2>&1 &"
```

### Per-Config Settings

| Config | EDGE_CPUS | Phases rate | Phase edit between groups |
|--------|-----------|-------------|--------------------------|
| C1 | `0.20` | 1.0× | None (use v8 rates) |
| C2 | `0.15` | 1.0× | None |
| C3 | `0.10` | 1.0× | None |
| C4 | `0.15` | 1.5× | **Edit phases.json**: set stress-phase rates to 1.5× |
| C5 | `0.10` | 1.5× | None (keep 1.5× from C4, change EDGE_CPUS only) |

> **Note**: Between C3 and C4, edit `rate_per_client` in `phases.json` for
> `storage_storm` (4.0→6.0), `tier1_hotspot` (5.0→7.5), `reverse_hotspot`
> (5.0→7.5), `compute_spike` (2.0→3.0). Non-stress phases stay at 1.0×.
> Only EDGE_CPUS changes between C4 and C5 (rate stays at 1.5×).

## Full Campaign (on Winning Config)

If a calibration config passes the gate, execute the full 12-run campaign
on that configuration with the v8 run matrix pattern:

4 modes × 3 replicates = 12 runs. Push, Poll-5s, Poll-12s, Poll-30s.
Labels: `rq1_v9c_<mode>_{1,2,3}`.

The full campaign follows the v8 experiment plan's run configuration
(substituting `PHASES_CONFIG=testing/phases.json` for v8's
`testing/phases_gap.json`, and adding `EDGE_CPUS=<winner>`),
metrics, focus, and post-run workflow. Omitted here for brevity — the
calibration's purpose is to find the config; the v8 plan provides the
campaign template.

## Calibration Gate Criteria Per Pair

After each Push + Poll-30s pair:

| # | Criterion | Threshold | Measurement |
|---|-----------|-----------|-------------|
| G1 | Throughput separation | Poll-30s ≤ 80% of Push | `client_requests.csv` row counts per run |
| G2 | Timeout rate separation | Poll-30s timeout rate ≥ 2× Push | `client_requests.csv` http_status=0 |
| G3 | Push sanity | Push timeout rate ≤ 10% | `client_requests.csv` |
| G4 | G8 | Both PASS (0 spawns during cleanup gaps) | `node_lifecycle_timings.csv` |

All 4 must pass for the config to win. If G3 fails (Push also failing),
the config is too aggressive — all modes fail equally, no differentiation.

**G3 caveat**: For C3/C5 (EDGE_CPUS=0.10), Push may approach 8–9% timeout
rate — technically passing G3 but indicating the system is near collapse. If
a config wins at 8–9% Push timeout, the full campaign's n=3 replicates may
push some Push runs above 10%. Consider running the Push replicate first in
the full campaign to validate G3 at n=3 before committing to all 12 runs.

## Validity Threats

1. **Calibration uses n=1 per mode per config.** A single lucky Poll-30s
   alignment could produce a false negative (appears to pass, but wouldn't
   replicate). The full 12-run campaign with n=3 is the validation. Calibration
   only selects the config — it doesn't produce thesis evidence.

2. **CPU reduction changes the relationship between overload and telemetry.**
   At 0.10 CPU, the edge servers saturate at lower request volumes, which means
   the scoring function's CPU_FLOOR=10 and CPU_SPAN=40 parameters may need
   recalibration. If Push spawns excessively at C3 (high timeout despite many
   spawns), the scoring thresholds are misaligned with the CPU range.

3. **Rate multiplication may saturate the WAN link.** At 1.5× rate with 90%
   cross-region in storage_storm, the WAN bandwidth may become the bottleneck
   rather than CPU. This would make all modes converge regardless of telemetry
   — a different kind of failure than intended.

4. **Restoring v8 phase durations reintroduces the recovery buffer.** v8 phases
   (180-240s) give Poll-30s time to partially recover if it detects overload.
   This is intentional — the calibration is testing whether CPU/rate changes
   can overcome the recovery buffer, not whether the buffer exists.
