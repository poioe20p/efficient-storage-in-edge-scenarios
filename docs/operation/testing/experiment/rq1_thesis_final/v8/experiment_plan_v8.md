# RQ1 v8 — Definitive Telemetry Cadence Evaluation

**Status**: ✅ Complete · **Date**: 2026-07-23
**Predecessor**: [`../v7/experiment_plan_v7.md`](../v7/experiment_plan_v7.md)
**Thesis RQ**: [`docs/research_questions/rq1.md`](../../../research_questions/rq1.md)

## Intent

Evaluate the effect of telemetry delivery cadence on reaction latency and
transient service quality under a stress test that removes cross-phase node
carryover — the system's primary absorption buffer.

v7 Test A established that the cleanup-gap configuration isolates the
coordination gap: each high-load phase starts from zero dynamic nodes, forcing
both modes to detect overload and spawn from scratch. At n=2 per mode (Push vs
Poll-30s only), it showed a 33-51% throughput gap and a 0% vs 65% blind spot
rate.

**v8 is the definitive campaign**: all four telemetry modes (Push, Poll-5s,
Poll-12s, Poll-30s), n=3 replicates per mode, 12 runs total. It establishes
the full monotonic trend with statistical power and provides the thesis with
its primary RQ1 evidence.

## Hypothesis / Expected Outcome

1. **Reaction latency increases monotonically with polling interval**:
   Push < Poll-5s < Poll-12s < Poll-30s. The breach-detection segment accounts
   for the increase; provisioning time is constant (~14 s).

2. **Blind spot rate is zero for Push and Poll-5s**, rises at Poll-12s
   (~17%), and peaks at Poll-30s (~65%). The HTTP cache delivers fresh data
   at consumption time; the mechanism is missed windows, not stale data.

3. **Throughput gap widens with polling interval**: In cross-region phases
   (storage_storm, tier1_hotspot, reverse_hotspot), Poll-30s completes
   30-50% fewer requests than Push. Poll-5s and Poll-12s fall between.

4. **Service quality degrades monotonically**: Timeout rate and p95 latency
   increase with polling interval. Poll-30s shows the highest failure rate
   and widest variance (bimodality).

5. **Controller overhead is flat**: CPU and RAM do not increase meaningfully
   with faster polling — the delivery mechanism is not a resource concern.

6. **G8 passes for all 12 runs**: No dynamic nodes are added during cleanup
   gaps. Every high-load phase truly starts from zero.

## RQ Linkage

**Thesis RQ1**: How does telemetry delivery cadence affect reaction latency
and transient service quality during demand shifts?

v8 is the definitive answer. The cleanup-gap configuration removes the
temporal buffer (cross-phase carryover), making detection speed the sole
determinant of reaction quality. The four-mode design establishes the full
monotonic dose-response curve — from zero blind spot (Push) to major
blind spot (Poll-30s) — with n=3 per mode for statistical power.

## Independent Variable & Held-Constant Set

### Independent Variable

**Telemetry delivery mode**: Push (ZMQ at window close), Poll-5s (HTTP every
5 s), Poll-12s (HTTP every 12 s), Poll-30s (HTTP every 30 s).

### Held Constant

| Parameter | Value | Notes |
|-----------|-------|-------|
| CLIENTS | 96 | Identical to v7 Test A |
| DEVICES | 6000 | Identical to v7 Test A |
| NODES | 100 | Identical to v7 Test A |
| MAX_DYNAMIC_COMPUTE | 12 | From v5 Pilot B |
| STORAGE_CPUS | 0.08 | From v5 Pilot B |
| STORAGE_MEMORY | 512m | From v5 Pilot B |
| EDGE_CPUS | 0.30 | Default in build_network_*.sh |
| EDGE_MEMORY | 256m | Default in build_network_*.sh |
| CURL_MAX_TIME | 30 | From v7 Test A |
| CPU_SPAN | 40 | From v5 Pilot B |
| WAN_RTT_MS | 185 | From v5 Pilot B |
| RANDOM_SEED | 42 | Identical across all runs |
| DATA_SEED | 42 | Identical across all runs |
| Phases | `phases_gap.json` | Cleanup-gap config from v7 Test A |
| Controller env | `current_state_integrated.env` | From v5 Pilot B |
| Docker image | `edge_server` rebuilt without EDGE_MAX_CONCURRENT | Test B code reverted |
| Aggregation window | 10 s | Fixed; window-size variation is future work |

## Run Matrix

| # | Label | Mode | Phases |
|---|-------|------|--------|
| P1 | `rq1_v8_push_1` | Push | `phases_gap.json` |
| P2 | `rq1_v8_push_2` | Push | `phases_gap.json` |
| P3 | `rq1_v8_push_3` | Push | `phases_gap.json` |
| F1 | `rq1_v8_poll5_1` | Poll-5s | `phases_gap.json` |
| F2 | `rq1_v8_poll5_2` | Poll-5s | `phases_gap.json` |
| F3 | `rq1_v8_poll5_3` | Poll-5s | `phases_gap.json` |
| W1 | `rq1_v8_poll12_1` | Poll-12s | `phases_gap.json` |
| W2 | `rq1_v8_poll12_2` | Poll-12s | `phases_gap.json` |
| W3 | `rq1_v8_poll12_3` | Poll-12s | `phases_gap.json` |
| T1 | `rq1_v8_poll30_1` | Poll-30s | `phases_gap.json` |
| T2 | `rq1_v8_poll30_2` | Poll-30s | `phases_gap.json` |
| T3 | `rq1_v8_poll30_3` | Poll-30s | `phases_gap.json` |

**Total: 12 runs.** Run order: P1→P2→P3→F1→F2→F3→W1→W2→W3→T1→T2→T3.
Each run: ~32 min (1920 s phases). Total wall-clock: ~6.5 h (including setup
overhead between runs).

## Run Configuration

### Push Mode (P1–P3)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients \
    setup_test_data run_experiment \
  RUN_LABEL=<LABEL> \
  PHASES_CONFIG=testing/phases_gap.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=185 CLIENTS=96 STORAGE_CPUS=0.08 STORAGE_MEMORY=512m \
  CURL_MAX_TIME=30 RANDOM_SEED=42 DATA_SEED=42 \
  > /tmp/<LABEL>.log 2>&1 &"
```

### Poll-5s Mode (F1–F3)

Same as Push, with:
```
TELEMETRY_SOURCE=poll POLL_INTERVAL_S=5
```

### Poll-12s Mode (W1–W3)

Same as Push, with:
```
TELEMETRY_SOURCE=poll POLL_INTERVAL_S=12
```

### Poll-30s Mode (T1–T3)

Same as Push, with:
```
TELEMETRY_SOURCE=poll POLL_INTERVAL_S=30
```

> **`phases_gap.json` exception**: The project convention requires editing
> `phases.json` in place. v7 Test A established `phases_gap.json` as the
> exception — Test A and Test B required different phase configs simultaneously.
> v8 uses this file exclusively. The run folder captures `phases_snapshot.json`.
> After the v8 campaign, `phases_gap.json` should be reconciled back into
> `phases.json` as the canonical phases file (cleanup-gap config is now the
> standard RQ1 workload).
> files (app.py, build_network_1.sh, build_network_2.sh, compute_node_manager.py).
> The Docker image must be rebuilt before the first v8 run.

## Focus & Evidence

### Primary Evidence

| Artifact | What it shows | Measurement |
|----------|--------------|-------------|
| `analysis/rq1_blind_spot_windows.csv` (M6) | Breached windows unseen by controller | Blind spot rate per mode |
| `analysis/rq1_reaction_latency.csv` | Breach detection + provision time | Reaction latency decomposition |
| `client_requests.csv` | Per-phase request count, http_status | Throughput gap, timeout rate, 503 count |
| `analysis/rq1_timeout_root_cause.csv` (M7) | storage_bound vs transient_spike vs 503s | Failure composition |

### Secondary Evidence

| Artifact | What it shows |
|----------|--------------|
| `analysis/rq1_staleness.csv` | Information age at consumption (expect ~0 s all modes) |
| `analysis/rq1/rq1_overhead.csv` | Controller CPU%, RSS per mode |
| `analysis/rq1/rq1_decision_quality.csv` | Breached windows vs spawns per phase |
| `analysis/rq1/rq1_missed_opportunities.csv` (M2) | Phases with CPU pressure but no spawns |
| `analysis/rq1/rq1_time_to_capacity.csv` (M3) | Time from phase start to sufficient capacity |
| `analysis/rq1/rq1_endpoint_latency.csv` (M8) | Per-endpoint p50/p95/p99 per phase |
| `analysis/rq1/rq1_recovery_lag.csv` (M9) | Recovery time from demand_drop |
| `node_lifecycle_timings.csv` | Spawn timing relative to phase start (check G8) |
| `container_events.csv` | Dynamic node lifecycle (spawn/stop) |

### Cross-Mode Comparison (after all 12 runs)

Use `generate_comparison_graphs.py` (all four `--run-dirs-*` arguments now
optional) to produce:

| Graph | Measurement |
|-------|-------------|
| Reaction latency mean + max + combined | §5.2 — Core evidence |
| Controller CPU% + RSS | §5.4 — Overhead cost |
| Max staleness | §5.1 — Confirmation |
| Timeout rate overall + per-phase | §5.3 — Service quality |
| Decision quality table | §5.5 — Behavioral divergence |

All graphs include per-replicate scatter dots and error bars showing variance
(n=3 per mode).

## Metrics & Success Criteria

These are **measurements to report**, not pass/fail gates. The thesis
interprets the dose-response curve.

| Measurement | Expected trend | Evidence |
|-------------|---------------|----------|
| **Blind spot rate** (M6) | Push = Poll-5s = 0%; Poll-12s < Poll-30s | `rq1_blind_spot_windows.csv` |
| **Reaction latency** | Push < Poll-5s < Poll-12s < Poll-30s (monotonic) | `rq1_reaction_latency.csv` |
| **Breach detection segment** | Increases with polling interval | `rq1_reaction_latency.csv` (breach_detection_s) |
| **Provision time** | ~14 s constant across all modes | `rq1_reaction_latency.csv` (provision_time_s) |
| **Throughput in cross-region phases** | Push ≥ Poll-5s ≥ Poll-12s > Poll-30s | `client_requests.csv` per-phase counts |
| **Timeout rate** | Push < Poll-5s < Poll-12s < Poll-30s | `client_requests.csv` http_status=0 |
| **Timeout root cause** (M7) | storage_bound dominant in slower modes | `rq1_timeout_root_cause.csv` |
| **p95 latency** (cross-region phases) | Increases with polling interval | `rq1_endpoint_latency.csv` |
| **Controller CPU%** | Flat across modes (~11-14%) | `rq1_overhead.csv` |
| **Controller RSS** | Flat across modes (~85-95 MB) | `rq1_overhead.csv` |
| **Staleness at consumption** | ~0 s for all modes | `rq1_staleness.csv` |
| **G8 (no spawns during gaps)** | PASS all 12 runs | `node_lifecycle_timings.csv` |
| **Recovery lag** (M9) | Similar across modes (~30-35 s) | `rq1_recovery_lag.csv` |
| **Missed opportunities** (M2) | Higher in slower polling modes | `rq1_missed_opportunities.csv` |

Report per-mode means with ±σ (standard deviation across n=3 replicates).
Flag any anomalous runs (>50% http_status=0, or LAN-specific failures)
for exclusion with justification.

## Post-Run Workflow (per run)

After each run completes:

### Step 1 — Fix ownership & parse logs

```bash
sudo chown -R testop:testop <run_dir>
python3 source/scripts/tools/parse_elasticity_logs.py \
  <run_dir>/controller_lan1.log <run_dir>/controller_lan2.log \
  -o <run_dir>/elasticity_events.csv \
  --timings-output <run_dir>/node_lifecycle_timings.csv
```

### Step 2 — Statistics

```bash
python3 source/scripts/tools/metrics_stats.py <run_dir> --by-phase --by-lan --by-endpoint
python3 source/scripts/tools/metrics_stats.py -r <run_dir>/resource_stats.csv --by-phase --by-network
```

### Step 3 — Generic analysis graphs

```bash
for cli in cli_overview cli_simple_run cli_phase_summary cli_endpoint_breakdown \
           cli_scale_down cli_lifecycle_gantt cli_cpu_drivers cli_tdb_drivers; do
  python3 -m source.scripts.testing.analysis.$cli --run-dir <run_dir>
done
```

### Step 4 — RQ1-specific CLIs

```bash
for cli in missed_opportunities time_to_capacity blind_spot_windows \
           timeout_root_cause endpoint_latency recovery_lag \
           decision_quality timings overhead; do
  python3 -m source.scripts.testing.analysis.rq1.cli.$cli --run-dir <run_dir>
done
```

### Step 5 — G8 check

```bash
python3 -c "
import csv, json
from pathlib import Path
run_dir = Path('<run_dir>')
with open(run_dir / 'phases_snapshot.json') as f:
    phases = json.load(f)['phases']
t = 0
gap_windows = []
for p in phases:
    if 'cleanup_gap' in p['name']:
        gap_windows.append((p['name'], t, t + p['duration_s']))
    t += p['duration_s']
with open(run_dir / 'node_lifecycle_timings.csv') as f:
    for row in csv.DictReader(f):
        add_ts = float(row.get('add_time', 0))
        for name, start, end in gap_windows:
            if start < add_ts <= end:
                print(f'G8 FAIL: {row.get(\"node_type\")} added during {name} at t={add_ts:.0f}s')
print('G8 check complete')
"
```

### Step 6 — Cleanup & copy back

```bash
rm -f <run_dir>/controller_lan1.log <run_dir>/controller_lan2.log
rm -rf <run_dir>/service_logs
# scp run folder locally, verify, then delete remote
```

### Step 7 — Cross-mode comparison (after final run)

```bash
python -m source.scripts.testing.analysis.rq1.scripts.generate_comparison_graphs \
    --title-prefix "RQ1 v8" \
    --run-dirs-push <P1_dir> <P2_dir> <P3_dir> \
    --run-dirs-poll5 <F1_dir> <F2_dir> <F3_dir> \
    --run-dirs-poll12 <W1_dir> <W2_dir> <W3_dir> \
    --run-dirs-poll30 <T1_dir> <T2_dir> <T3_dir> \
    --output-dir docs/operation/testing/experiment/rq1_thesis_final/v8/graphs/comparison/
```

## Checkpoints

| # | Checkpoint | Phase/Trigger | Question | Action |
|---|-----------|---------------|----------|--------|
| C1 | Run folder created | After each launch | Did the run start? | Verify log and process |
| C2 | Phase transition past cleanup_gap_1 | t ≈ 550 s | Did the controller survive? | Check current_phase.txt |
| C3 | G8 | Post-run | Any spawns during cleanup gaps? | Report PASS/FAIL |
| C4 | Anomaly screening | Post-run | http_status=0 > 50%? LAN imbalance > 10:1? | Flag for exclusion |
| C5 | n=3 completeness | After each mode's 3rd run | All replicates healthy? | If <2 healthy runs remain, schedule replacement |

## Prerequisites

| # | Item | Status |
|---|------|--------|
| P1 | `phases_gap.json` exists with cleanup gaps | ✅ From v7 |
| P2 | `current_state_integrated.env` configured (CPU_SPAN=40, MAX_DYNAMIC_COMPUTE=12) | ✅ From v7 |
| P3 | Remove EDGE_MAX_CONCURRENT from app.py, build_network_*.sh, compute_node_manager.py | ✅ Done |
| P4 | Rebuild `edge_server` Docker image (no semaphore) | ⬜ TODO |
| P5 | Verify canonical `phases.json` exists (not needed for v8 but must not be corrupted) | ⬜ TODO |
| P6 | RQ1 analysis CLIs operational | ✅ From v7 |
| P7 | `generate_comparison_graphs.py` accepts optional mode arguments | ✅ Fixed |
| P8 | VM capacity: 52 GB disk, 6.9 GB RAM available | ✅ Verified |

### P4 Detail — Docker Rebuild

```bash
# On cloud-vm
cd ~/efficient-storage-in-edge-scenarios
sudo docker build -t edge_server:latest source/docker/edge_server
```

Verify the semaphore code is absent:
```bash
sudo docker run --rm edge_server:latest grep -c "EDGE_MAX_CONCURRENT" /source/app.py
# Expected: 0
```

## Validity Threats & Limitations

| Threat | Mitigation |
|--------|------------|
| **n=3 per mode** | Adequate for dose-response trend detection. Report ±σ for all metrics. |
| **Run order not randomized** | Modes run in order of increasing interval. VM performance drift across 6.5 h is accepted. If a clear time trend appears (e.g., later runs systematically worse), flag in results. |
| **Cleanup gaps force artificial reset** | This is intentional — it isolates the independent variable. The thesis frames it as a stress test, not a realistic workload. |
| **Controller crash risk** | v7 had 1 crash in 6 runs (A2 original). With 12 runs, expect 1-2 failures. Schedule replacements. |
| **Bimodality in Poll-30s** | Known from v3-v7. n=3 captures both regimes. Report per-replicate values, not just means. |
| **Gap duration (240 s) may be tight for Poll-30s** | Poll-30s detection of load drop takes up to 30 s, leaving 30 s margin for compute cooldown (180 s). G8 verifies gaps work. |
| **Docker image rebuild** | Must rebuild without EDGE_MAX_CONCURRENT before first run. Verify with grep. |

## Artifact Contract

Standard run-folder layout per `docs/operation/testing/testing_overview.md`:

```
<run_dir>/
  client_requests.csv
  resource_stats.csv
  resource_stats_debug.csv
  per_node_stats.csv
  container_events.csv
  controller_stats.csv
  policy_state.csv
  elasticity_events.csv
  node_lifecycle_timings.csv
  phases_snapshot.json
  controller_env_snapshot.env
  current_phase.txt
  latency_summary.csv
  resource_summary.csv
  analysis/
    overview_latency.png / overview_resources.png / overview_throughput.png
    simple_run.png
    phase_summary.png
    endpoint_breakdown.png
    scale_down.png
    lifecycle_gantt.png
    cpu_drivers.png
    tdb_drivers.png
    rq1_staleness.png / rq1_staleness.csv / rq1_staleness_per_phase.csv
    rq1_reaction_latency.png / rq1_reaction_latency.csv
    rq1/
      rq1_blind_spot_windows.csv
      rq1_timeout_root_cause.csv
      rq1_missed_opportunities.csv
      rq1_time_to_capacity.csv
      rq1_endpoint_latency.csv
      rq1_recovery_lag.csv
      rq1_decision_quality.csv / rq1_decision_quality.png
      rq1_overhead.csv / rq1_overhead_cpu.png / rq1_overhead_ram.png
```

After all 12 runs, cross-mode comparison outputs at:
```
docs/operation/testing/experiment/rq1_thesis_final/v8/graphs/comparison/
```

## Changelog

| Date | Change |
|------|--------|
| 2026-07-21 | v8 plan created. Definitive RQ1 campaign: 4 modes × 3 replicates = 12 runs using cleanup-gap configuration from v7 Test A. All Test B concurrency-limit code reverted. Full post-run measurement specification included. |
