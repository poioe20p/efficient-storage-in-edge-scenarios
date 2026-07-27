# RQ1 v13 — Storage Cascade with Redesigned Phases (4 modes, n=3, S2 config, no CT5)

**Status**: 📋 Planned · **Date**: 2026-07-27
**Predecessor**: [`../v12/experiment_plan_v12.md`](../v12/experiment_plan_v12.md)
**Thesis RQ**: RQ1 — Telemetry Delivery Cadence and Control Quality

## Intent

v12 established that the S2+CT5 configuration (`EDGE=0.15`, `STORAGE=0.05`,
`--connect-timeout 5`) is unstable at n=3 (~30% catastrophic failure rate).
Root cause: the `compute_spike` phase (100% `service_pressure` with
`window_min=1`) produces extreme per-request variance, occasionally triggering
TCP accept-queue collapse or Poll-30s under-provisioning.

v13 makes three changes:

1. **Redesigned phases**: Shorter stress phases (150s vs 180-240s) make the
   30s blind spot 20% of each stress event (vs 12-17%). Two `storage_storm`
   events double-measure the cascade mechanism. `compute_spike` removed
   entirely — eliminates the `window_min=1` variance source.

2. **CT5 removed**: `--connect-timeout 5` is dropped from
   `traffic_generator.py`. Without `compute_spike`, the accept-queue collapse
   that CT5 exposed is no longer triggered. TCP-level failures that do occur
   are absorbed by OS TCP retransmission and show as high-latency completions
   or `CURL_MAX_TIME=30` timeouts. The throughput gap is the primary signal.

3. **Same S2 config**: `EDGE=0.15`, `STORAGE=0.05`, `CR=0.40`, controller env
   unchanged from v12. The only calibration point that produces separation.

## Hypothesis / Expected Outcome

1. **Throughput gap widens and is stable.** With 20% blind-spot fraction (vs
   12-17% in v12), P30 serves proportionally fewer requests per stress phase.
   Push/P30 throughput ranges do not overlap across n=3.

2. **Two storage events produce consistent gap.** Both `storage_storm` and
   `storage_storm_2` show the same Push vs P30 throughput gradient, confirming
   the cascade mechanism is replicable within a single run.

3. **Timeout separation is secondary.** Without CT5, TCP accept-queue failures
   appear as latency, not `http_status=0`. Timeout rates are lower overall and
   the gap is muted. The thesis narrative emphasizes throughput and tail
   latency as the primary RQ1 signals.

4. **Full dose-response curve is monotonic.** Push ≈ Poll-5s > Poll-12s >
   Poll-30s. Throughput and p95 latency follow the polling interval gradient.

5. **p95 latency inflates with polling interval.** P30 p95 ≥ Push p95. The tail
   inflation is consistent across replicates because it reflects blind-spot
   queuing, not random accept-queue collapse.

6. **G8 passes for all 12 runs.** 220s cleanup gaps exceed
   `SCALEDOWN_COMPUTE_COOLDOWN_S=180` and `SCALEUP_STORAGE_COOLDOWN_S=120`.

## RQ Linkage

**Thesis RQ1**: How does telemetry delivery cadence affect reaction latency
and transient service quality during demand shifts?

v13 tests this on workload phases designed around the storage cascade
mechanism — the only mechanism where the blind-spot penalty qualitatively
alters user experience (connections fail vs succeed). Shorter phases ensure
the blind spot occupies a meaningful fraction of each stress event. Two
storage storms per run double-measure the cascade, providing within-run
replication. The dose-response curve (4 modes) maps the penalty gradient:
near-zero blind spot (Push/Poll-5s), intermediate (Poll-12s), maximum
(Poll-30s).

## Independent Variable & Held-Constant Set

### Independent Variable

**Telemetry delivery mode**: Push (ZMQ at window close), Poll-5s (HTTP every
5 s), Poll-12s (HTTP every 12 s), Poll-30s (HTTP every 30 s).

### Held Constant

| Parameter | Value | Notes |
|-----------|-------|-------|
| `EDGE_CPUS` | **0.15** | v10/v12 proven; Push handles this |
| `STORAGE_CPUS` | **0.05** | v11 calibration winner; cascade amplifier |
| `CURL_MAX_TIME` | 30 | Same as v8/v10/v12 |
| `--connect-timeout` | **removed** | Dropped from `traffic_generator.py` |
| `CLIENTS` | 96 | Same as v8/v10/v12 |
| `DEVICES` | 6000 | Same as v8/v10/v12 |
| `NODES` | 100 | Same as v8/v10/v12 |
| `MAX_DYNAMIC_COMPUTE` | 12 | Same as v8/v10/v12 |
| `MAX_DYNAMIC_STORAGE` | 8 | Same as v8/v10/v12 |
| `STORAGE_MEMORY` | 512m | Same as v8/v10/v12 |
| `EDGE_MEMORY` | 256m | Build script default |
| `CPU_SPAN` | 40 | Same as v8/v10/v12 |
| `WAN_RTT_MS` | 185 | Same as v8/v10/v12 |
| `RANDOM_SEED` | 42 | Same as v8/v10/v12 |
| `DATA_SEED` | 42 | Same as v8/v10/v12 |
| Phases | `phases.json` (v13 redesign) | 9-phase, 150s stress, 220s gaps, `storage_storm_2` |
| Controller env | `current_state_integrated.env` | Same as v8/v10/v12 |

## Prerequisites (Blockers — must be completed before first run)

| # | Change | File | Status | Rationale |
|---|--------|------|--------|-----------|
| P1 | Redesign phases | `source/scripts/testing/phases.json` | ⏳ Pending | 150s stress, 220s gaps, `storage_storm_2` replaces `compute_spike` (see §Phases Design) |
| P2 | Remove `--connect-timeout 5` | `source/scripts/testing/traffic_generator.py` | ⏳ Pending | Drop the `"--connect-timeout", "5"` line; keep `-D -` and `backend_id` |

No Docker image rebuild needed — `traffic_generator.py` runs from host. Both changes
are edits to the canonical files; no variant files created.

## Phases Design (v13)

9 phases, 1760 s total (~29 min). 220s cleanup gaps (above 180s
`SCALEDOWN_COMPUTE_COOLDOWN_S` and 120s `SCALEUP_STORAGE_COOLDOWN_S`) ensure
G8. 150s stress phases make the 30s blind spot 20% of each event.

| # | Phase | Duration | Rate/client | CR | Client % | Dominant Mix |
|---|-------|----------|-------------|-----|----------|-------------|
| 1 | `baseline` | 60s | 1.0 | 0.00 | 10% | 60% lookup, 25% ranking, 15% pressure |
| 2 | `storage_storm` | **150s** | 4.0 | 0.90 | 100% | 35% lookup, 30% update, 20% aggregate |
| 3 | `cleanup_gap_1` | **220s** | 0.5 | 0.00 | 5% | baseline mix |
| 4 | `tier1_hotspot` | **150s** | 5.0 | 0.40 | 100% | 80% lookup, 5% each ranking/pressure/update/aggregate |
| 5 | `cleanup_gap_2` | **220s** | 0.5 | 0.00 | 5% | baseline mix |
| 6 | `reverse_hotspot` | **150s** | 5.0 | 0.40 | 100% | 80% lookup (identical workload to tier1_hotspot — within-run hotspot replication) |
| 7 | `cleanup_gap_3` | **220s** | 0.5 | 0.00 | 5% | baseline mix |
| 8 | `storage_storm_2` | **150s** | 4.0 | 0.90 | 100% | Identical to phase 2 — second cascade measurement |
| 9 | `demand_drop` | 300s | 1.0 | 0.00 | 10% | baseline mix — measure recovery lag (time from phase start until p95 latency returns to ≤ baseline p95 + 1s) |

### What Changed from v10/v12 Phases

| Change | From | To | Rationale |
|--------|------|-----|-----------|
| `storage_storm` duration | 240s | 150s | Blind spot = 20% of phase (was 12.5%) |
| All cleanup gaps | 240s | 220s | 40s spawn window above 180s cooldown (was 60s) |
| `tier1_hotspot` duration | 180s | 150s | Blind spot = 20% (was 17%) |
| `inter_hotspot_cooldown` (300s) | Removed | → merged into `cleanup_gap_2` | 220s is sufficient for drain |
| `reverse_hotspot` duration | 180s | 150s | Same as tier1_hotspot |
| `compute_spike` (180s) | Removed | → `storage_storm_2` (150s) | Eliminates `window_min=1` variance; double-measures cascade |
| `demand_drop` | 300s | 300s | Unchanged — recovery measurement |
| **Total runtime** | **1920s** | **1760s** | 8% faster; more replicates/day |

**`reverse_hotspot` starting condition**: With 220s between `tier1_hotspot` end
and `reverse_hotspot` start, dynamic compute nodes from the first hotspot may
still be alive (scale-down requires 90s idle detection + 180s cooldown from
last spawn). `reverse_hotspot` therefore starts with potentially pre-warmed
capacity, while `tier1_hotspot` starts cold. This is consistent across all
modes — the cross-mode comparison for `reverse_hotspot` measures blind-spot
effect under a different initial condition (pre-warmed), not a within-run
replicate of `tier1_hotspot` (cold start).

### Why This Amplifies the Gap

v12's `results.md` initially proposed 120s stress phases and 200s gaps (1440s
total). v13 uses **150s stress phases and 220s gaps** (1760s total) as a
conservative compromise:

- **120s phases** gave 25% blind-spot fraction but only ~20s of spawn window
  in cleanup gaps (200s − 180s cooldown). Risked both modes struggling equally
  in the opening seconds of the next phase.
- **150s phases** give 20% blind-spot fraction with 40s of spawn window. Still
  a meaningful increase from v12's 12-17%, but with safe operational margins.

```
v12:  240s stress, 12.5% blind spot
  Push:  detects at ~14s → serves for 226s (94% of phase)
  P30:   detects at ~44s → serves for 196s (82% of phase)
  Gap:   Push serves 15% more of the phase

v13:  150s stress, 20% blind spot
  Push:  detects at ~14s → serves for 136s (91% of phase)
  P30:   detects at ~44s → serves for 106s (71% of phase)
  Gap:   Push serves 28% more of the phase per stress event
```

Note: this 28% is the per-phase provisioned-time ratio, not the total-run
throughput gap — which is diluted by baseline, cleanup, and demand_drop phases
where both modes are provisioned and the gap is near zero.

## Run Matrix

| # | Label | Mode | EDGE_CPUS | STORAGE_CPUS | CT | Purpose |
|---|-------|------|-----------|-------------|-----|---------|
| P1 | `rq1_v13_push_1` | Push | 0.15 | 0.05 | — | Baseline: zero blind spot |
| P2 | `rq1_v13_push_2` | Push | 0.15 | 0.05 | — | Replicate |
| P3 | `rq1_v13_push_3` | Push | 0.15 | 0.05 | — | Replicate |
| T1 | `rq1_v13_poll30_1` | Poll-30s | 0.15 | 0.05 | — | Maximum blind spot |
| T2 | `rq1_v13_poll30_2` | Poll-30s | 0.15 | 0.05 | — | Replicate |
| T3 | `rq1_v13_poll30_3` | Poll-30s | 0.15 | 0.05 | — | Replicate |
| ↳ | **Gate check** | | | | | Verify Push/P30 separation at n=3 |
| F1 | `rq1_v13_poll5_1` | Poll-5s | 0.15 | 0.05 | — | Near-zero blind spot: proves mechanism is missed windows |
| F2 | `rq1_v13_poll5_2` | Poll-5s | 0.15 | 0.05 | — | Replicate |
| F3 | `rq1_v13_poll5_3` | Poll-5s | 0.15 | 0.05 | — | Replicate |
| W1 | `rq1_v13_poll12_1` | Poll-12s | 0.15 | 0.05 | — | Intermediate: proves penalty is gradual |
| W2 | `rq1_v13_poll12_2` | Poll-12s | 0.15 | 0.05 | — | Replicate |
| W3 | `rq1_v13_poll12_3` | Poll-12s | 0.15 | 0.05 | — | Replicate |

**Total: 12 runs.** Run order: P1→P2→P3→T1→T2→T3 → **gate check** →
F1→F2→F3→W1→W2→W3.

Each run: ~29 min (1760 s phases). Total wall-clock: **9–12 h** (including
~3–5 launch attempts per run and namespace cleanup between runs).

### Sequential Gate (after T3)

After the first 6 runs (P1–P3, T1–T3), check:

| Gate | Check | Pass condition |
|------|-------|---------------|
| Throughput separation | Push range vs P30 range | No overlap between worst Push and best P30 |
| p95 latency separation | Push μ vs P30 μ | P30 p95 ≥ 1.15× Push p95 |
| Timeout direction | Push μ vs P30 μ | P30 timeout ≥ Push timeout (direction, not magnitude) |
| Within-mode variance | Max-min per mode | ≤ 15K req range within each mode (n=3) |
| G8 | All 6 runs | No spawns during cleanup gaps |

If all gates pass, proceed to F1–W3. If any gate fails, stop and diagnose.

Note: v13 gates are relaxed from v12's (no ≥6% timeout requirement, no ≥80K
absolute threshold, wider within-mode variance tolerance, lower p95 ratio)
because CT5 is removed — timeout separation is no longer the primary signal.
The throughput gap and p95 gap carry the evidence.

Quick gate check from the cloud VM (after P1–P3, T1–T3 complete):

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics

# Throughput ranges
echo '=== Push throughput ==='
for d in 202*_rq1_v13_push_*; do
  echo \"\$d: \$(tail -n +2 \$d/client_requests.csv | wc -l)\"
done

echo '=== P30 throughput ==='
for d in 202*_rq1_v13_poll30_*; do
  echo \"\$d: \$(tail -n +2 \$d/client_requests.csv | wc -l)\"
done

# G8 check (grep returns non-zero if no matches; || true handles that)
echo '=== G8 ==='
for d in 202*_rq1_v13_push_* 202*_rq1_v13_poll30_*; do
  spawns=\$(grep -c 'cleanup_gap' \$d/node_lifecycle_timings.csv 2>/dev/null || echo 0)
  echo \"\$d: \$spawns\"
done\"

## Run Configuration

### Common Parameters (all runs)

```
EDGE_CPUS=0.15 STORAGE_CPUS=0.05
PHASES_CONFIG=testing/phases.json
OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env
WAN_RTT_MS=185 CLIENTS=96 STORAGE_MEMORY=512m
CURL_MAX_TIME=30 RANDOM_SEED=42 DATA_SEED=42
```

### Push Mode (P1–P3)

`TELEMETRY_SOURCE` defaults to `zmq` (push) in `build_network_setup.sh`. Explicitly
set for symmetry with poll-mode commands:

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n TELEMETRY_SOURCE=zmq make -C source/scripts setup_network \
    create_clients setup_test_data run_experiment \
  RUN_LABEL=<LABEL> \
  EDGE_CPUS=0.15 STORAGE_CPUS=0.05 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=185 CLIENTS=96 STORAGE_MEMORY=512m \
  CURL_MAX_TIME=30 RANDOM_SEED=42 DATA_SEED=42 \
  > /tmp/<LABEL>.log 2>&1 &"
```

**Important**: `TELEMETRY_SOURCE` and `POLL_INTERVAL_S` are shell environment
variables passed BEFORE `make` (via `sudo -n`), not Makefile arguments. They are
consumed by `build_network_setup.sh` which passes them to the controller via
`sudo -E`. Placing them after `make` (as Make vars) will be silently ignored and
the run will use the default Push mode.

### Poll-30s Mode (T1–T3)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n TELEMETRY_SOURCE=poll POLL_INTERVAL_S=30 make -C source/scripts \
    setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=<LABEL> \
  EDGE_CPUS=0.15 STORAGE_CPUS=0.05 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=185 CLIENTS=96 STORAGE_MEMORY=512m \
  CURL_MAX_TIME=30 RANDOM_SEED=42 DATA_SEED=42 \
  > /tmp/<LABEL>.log 2>&1 &"
```

### Poll-5s Mode (F1–F3)

Same as Poll-30s, replacing `POLL_INTERVAL_S=30` with `POLL_INTERVAL_S=5`.

### Poll-12s Mode (W1–W3)

Same as Poll-30s, replacing `POLL_INTERVAL_S=30` with `POLL_INTERVAL_S=12`.

### Per-Run Cleanup

```bash
ssh cloud-vm "sudo python3 /tmp/clean_ns.py && \
  sudo -n bash ~/efficient-storage-in-edge-scenarios/source/scripts/cleanup.sh"
```

### Post-Campaign Retrieval

After all runs complete, copy run folders back to the local machine for
analysis (as documented in `docs/operation/testing/testing_overview.md`):

```bash
scp -r cloud-vm:~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/202*_rq1_v13_* \
  source/scripts/testing/metrics/
```

### Run Monitoring

```bash
# Check if run is alive
ssh cloud-vm "pgrep -af 'run_experiment'"

# Tail the log
ssh cloud-vm "tail -20 /tmp/<LABEL>.log"

# Launch watchdog
python tools/watch_run.py --host cloud-vm --run-label <LABEL> \
  --poll-interval 15 --timeout 4200
```

Watchdog timeout: 4200s (70 min) — ample for ~29 min runs.

## Focus & Evidence

### Primary Evidence

| Artifact | What it shows |
|----------|--------------|
| `client_requests.csv` | Throughput, timeout rate, latency (p50/p95/p99/stddev) per phase/mode |
| Per-phase breakdown | Which phases carry the gap (expect storage-dependent phases) |

### Secondary Evidence

| Artifact | What it shows |
|----------|--------------|
| `node_lifecycle_timings.csv` | Dynamic node spawn counts per mode; P30 should spawn fewer compute nodes |
| `container_events.csv` | Container spawn/stop timing |
| Controller logs (`controller_lan1.log`, `controller_lan2.log`) | Scale decisions, timing, anomalies |
| `phases_snapshot.json` | Confirms correct phases were active |

### Analysis Focus

1. **Throughput**: Primary metric. Push vs P30 per-phase breakdown. Check that
   `storage_storm` and `storage_storm_2` show consistent within-run gradient.
2. **p95 latency**: Secondary metric. P30 tail inflation vs Push.
3. **Timeout rate**: Supplementary. Direction only — P30 ≥ Push; magnitude
   not gated.
4. **Dose-response**: Poll-5s ≈ Push, Poll-12s intermediate, Poll-30s worst.
5. **Within-mode variance**: ≤ 10K req range per mode across n=3.

## Metrics & Success Criteria

| Measurement | Expected | Evidence |
|-------------|----------|----------|
| **Throughput gap** | Push and P30 ranges do not overlap | `client_requests.csv` total row count |
| **Within-mode variance** | Range ≤ 15K req per mode (n=3) | `client_requests.csv` per-mode range |
| **p95 latency gap** | P30 p95 ≥ 1.15× Push p95 | `client_requests.csv` latency_s |
| **Timeout direction** | P30 ≥ Push timeout rate (any margin) | `client_requests.csv` http_status=0 |
| **Dose-response** | Throughput and p95 monotonic with polling interval | Cross-mode comparison |
| **Within-mode variance** | Range ≤ 10K req per mode (n=3) | `client_requests.csv` per-mode range |
| **storage_storm_2 replication** | Gap in `storage_storm_2` ≈ gap in `storage_storm` | Per-phase throughput comparison |
| **G8** | PASS all 12 runs | No spawns in cleanup_gap phases |
| **Controller overhead** | Flat across modes | `resource_stats.csv` |

## Validity Threats & Limitations

1. **Single STORAGE level.** Only tested at 0.05. The cascade threshold may
   be sensitive to this value; other levels may not separate.

2. **Single workload shape.** The 9-phase storage-heavy design is one demand
   pattern, redesigned based on v12's mechanism diagnosis. Not independently
   validated with a different workload.

3. **CT5 removal changes timeout visibility.** TCP accept-queue failures that
   CT5 exposed as `http_status=0` now appear as high-latency completions or
   `CURL_MAX_TIME=30` timeouts. The timeout gap is muted by design; throughput
   and p95 carry the evidence.

4. **Shorter phases = fewer requests = higher per-metric variance.** 1760s vs
   1920s means ~8% fewer requests per run. Per-replicate p95 and stddev have
   wider confidence intervals. Within-run replication only covers
   `storage_storm`/`storage_storm_2` — `tier1_hotspot`/`reverse_hotspot` have
   no within-run replicates and are 150s each (vs 180s in v12).

5. **`reverse_hotspot` starts pre-warmed.** The 220s cleanup gap between
   hotspots may not fully drain dynamic compute nodes. `reverse_hotspot` and
   `tier1_hotspot` are not comparable as within-run replicates — they measure
   blind-spot effect under different initial conditions.

6. **Known stall bug.** Expect ~3–5 launch attempts per run. Recovery:
   `teardown_clients` → `cleanup.sh` → `clean_ns.py` → retry.

## Artifact Contract

Standard run-folder layout as documented in `docs/operation/testing/testing_overview.md`:

```
source/scripts/testing/metrics/<timestamp>_<run_label>/
  client_requests.csv
  resource_stats.csv
  per_node_stats.csv
  container_events.csv
  node_lifecycle_timings.csv
  elasticity_events.csv
  controller_lan1.log
  controller_lan2.log
  phases_snapshot.json
  controller_env_snapshot.env
  service_logs/
```

Analysis outputs (produced by Edge Experiment Analyzer):
```
docs/operation/testing/experiment/rq1_thesis_final/v13/
  run_summary.md
  results.md
```

## Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-07-27 | Plan authored | v12 diagnosed: `compute_spike` + `window_min=1` unstable at n=3. v13: redesigned phases (150s stress, 220s gaps, storage_storm_2), CT5 removed, same S2 config. |
