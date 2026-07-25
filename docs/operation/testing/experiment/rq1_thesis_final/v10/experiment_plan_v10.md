# RQ1 v10 — Calibrated Dose-Response (4 modes, n=3, EDGE_CPUS=0.15)

**Status**: 📋 Planned · **Date**: 2026-07-25
**Predecessor**: [`../v9_calibration/experiment_plan_v9_calibration.md`](../v9_calibration/experiment_plan_v9_calibration.md)
**Thesis RQ**: [`docs/research_questions/rq1/rq1_v3.md`](../../../research_questions/rq1/rq1_v3.md)

## Intent

v8 (n=3, four modes, `EDGE_CPUS=0.30`) showed the dose-response curve but the
Push vs Poll-30s throughput gap was only −19% mean with σ=14K — high variance,
one Poll-30s replicate matched Push.

v9 halved phase durations. Failed — the static-node floor absorbed the
coordination gap.

v9_calibration swept `EDGE_CPUS` downward. C2 (`EDGE_CPUS=0.15`) produced
clean, consistent separation in a single pilot pair:

| Metric | Push | Poll-30s | Δ |
|--------|------|----------|---|
| Total requests | 89,028 | 62,299 | −30% |
| Timeout rate | 2.0% | 4.5% | +2.3× |
| p50 latency | 8.4 ms | 43.6 ms | 5.2× |
| p95 latency | 9.2 s | 18.1 s | 2.0× |
| storage_storm throughput | 15,720 | 10,103 | −36% |
| compute_spike throughput | 37,854 | 15,954 | −58% |

**v10 is the definitive campaign on C2**: all four telemetry modes, n=3 per
mode, 12 runs total, with a **sequential gate**. The Push and Poll-30s
extremes run first (6 runs). If the C2 pilot separation does not replicate
across n=3, the campaign stops — no time is wasted on Poll-5s/Poll-12s.
If the separation holds, Poll-5s and Poll-12s complete the dose-response
curve.

The C2 pilot was executed on the cloud VM (2026-07-25):
Push run `20260725_052050_rq1_v9c_c2_push` and Poll-30s run
`20260725_081301_rq1_v9c_c2_poll30`. Both passed G8 and produced the
results shown above. The v9_calibration plan is superseded by this one.

## Hypothesis / Expected Outcome

1. **Push vs Poll-30s separation holds at n=3.** Push completes ≥85K
   requests per run with ≤3% timeout; Poll-30s completes ≤65K with ≥4%
   timeout. No overlap between the worst Push and best Poll-30s replicate.

2. **Full dose-response curve is monotonic.** Push ≈ Poll-5s (both near-zero
   blind spot) > Poll-12s (intermediate) > Poll-30s (major blind spot).
   Throughput, timeout rate, and latency percentiles follow the polling
   interval gradient.

3. **Latency percentiles separate at p50 and above.** Push p50 < 15 ms;
   Poll-30s p50 ≥ 30 ms; Poll-5s and Poll-12s fall between. p95 gap follows
   the same gradient.

4. **Blind spot windows follow polling interval.** Push ≈ Poll-5s ≈ 0%;
   Poll-12s intermediate; Poll-30s ≥ 50%.

5. **G8 passes for all 12 runs.** No dynamic nodes spawn during cleanup gaps.

## RQ Linkage

**Thesis RQ1**: How does telemetry delivery cadence affect reaction latency
and transient service quality during demand shifts?

v10 establishes the full dose-response curve — from zero blind spot (Push)
to major blind spot (Poll-30s), with Poll-5s and Poll-12s as intermediate
points — on a calibrated configuration where the coordination gap reliably
cascades into user-visible degradation. The v8 campaign established the
curve at `EDGE_CPUS=0.30` but with high variance in the Poll-30s endpoint.
v10 sharpens the endpoint separation and confirms the entire curve at the
calibrated CPU level.

## Independent Variable & Held-Constant Set

### Independent Variable

**Telemetry delivery mode**: Push (ZMQ at window close), Poll-5s (HTTP every
5 s), Poll-12s (HTTP every 12 s), Poll-30s (HTTP every 30 s).

### Held Constant

| Parameter | Value | Notes |
|-----------|-------|-------|
| `EDGE_CPUS` | **0.15** | C2 winner from v9_calibration — half of v8's 0.30 |
| `CLIENTS` | 96 | Same as v8 |
| `DEVICES` | 6000 | Same as v8 |
| `NODES` | 100 | Same as v8 |
| `MAX_DYNAMIC_COMPUTE` | 12 | Same as v8 |
| `STORAGE_CPUS` | 0.08 | Same as v8 |
| `STORAGE_MEMORY` | 512m | Same as v8 |
| `EDGE_MEMORY` | 256m | Build script default — not passed explicitly |
| `CURL_MAX_TIME` | 30 | Same as v8 |
| `CPU_SPAN` | 40 | Same as v8 |
| `WAN_RTT_MS` | 185 | Same as v8 |
| `RANDOM_SEED` | 42 | Same as v8 |
| `DATA_SEED` | 42 | Same as v8 |
| Phases | `phases.json` (v8 cleanup-gap) | 9 phases, 240/180 s stress durations |
| Controller env | `current_state_integrated.env` | Same as v8 |

### Why EDGE_CPUS = 0.15

At v8's 0.30 CPUs, the static edge nodes had enough capacity to absorb the
Poll-30s blind spot — requests queued rather than timed out, and the
throughput gap was noisy (−19% mean, σ=14K).

Halving to 0.15 reduces each edge server's concurrent request capacity.
Under stress-phase load, the static nodes saturate. Push detects overload
within one window (~10 s) and spawns dynamic nodes in ~14 s. Poll-30s
remains blind for up to 30 s before detecting — and once detected, another
~14 s to provision. The saturated static nodes cannot absorb that 30–44 s gap,
so requests time out and throughput drops.

At 0.10 (C3), even Push may not provision fast enough, risking both modes
failing and losing mode differentiation.

The 240 s cleanup gaps exceed the controller's `SCALEDOWN_COMPUTE_COOLDOWN_S=180`
(configured in `current_state_integrated.env`). This ensures all dynamic nodes
time out during the gap — each high-load phase truly starts from zero (G8).

## Run Matrix

| # | Label | Mode | EDGE_CPUS |
|---|-------|------|-----------|
| P1 | `rq1_v10_push_1` | Push | 0.15 |
| P2 | `rq1_v10_push_2` | Push | 0.15 |
| P3 | `rq1_v10_push_3` | Push | 0.15 |
| T1 | `rq1_v10_poll30_1` | Poll-30s | 0.15 |
| T2 | `rq1_v10_poll30_2` | Poll-30s | 0.15 |
| T3 | `rq1_v10_poll30_3` | Poll-30s | 0.15 |
| F1 | `rq1_v10_poll5_1` | Poll-5s | 0.15 |
| F2 | `rq1_v10_poll5_2` | Poll-5s | 0.15 |
| F3 | `rq1_v10_poll5_3` | Poll-5s | 0.15 |
| W1 | `rq1_v10_poll12_1` | Poll-12s | 0.15 |
| W2 | `rq1_v10_poll12_2` | Poll-12s | 0.15 |
| W3 | `rq1_v10_poll12_3` | Poll-12s | 0.15 |

**Total: 12 runs.** Run order: P1→P2→P3→T1→T2→T3 → **gate check** →
F1→F2→F3→W1→W2→W3. The gate after T3 verifies the Push vs Poll-30s
separation before committing to the intermediate modes.

Each run: ~32 min (1920 s phases). Total wall-clock: **10–14 h** (including
~3–5 launch attempts per run due to the known stall bug — see Validity
Threats §5 — and namespace cleanup between runs).

### Sequential Gate (after T3)

After the first 6 runs (P1–P3, T1–T3), check:

| Gate | Check | Pass condition |
|------|-------|---------------|
| Throughput separation | Push mean vs Poll-30s mean | Push ≥ 85K, Poll-30s ≤ 65K, no overlap |
| Timeout separation | Push mean vs Poll-30s mean | Push ≤ 3%, Poll-30s ≥ 4% |
| G8 | All 6 runs | No spawns during cleanup gaps |

If all three gates pass, proceed to F1–W3. If any gate fails, stop and
diagnose — the C2 pilot did not replicate.

Quick gate check from the cloud VM (after P1–P3, T1–T3 complete):

```bash
# Throughput (total rows per run)
for d in 202*_rq1_v10_push_* 202*_rq1_v10_poll30_*; do
  echo "$d: $(wc -l < $d/client_requests.csv) requests"
done

# Timeout rate (http_status=0 rows / total)
for d in 202*_rq1_v10_push_* 202*_rq1_v10_poll30_*; do
  total=$(wc -l < $d/client_requests.csv)
  timeouts=$(grep -c ',0$' $d/client_requests.csv || echo 0)
  echo "$d: $(python3 -c \"print(f'{$timeouts/$total*100:.1f}%')\")"
done
```

If the gate fails due to a single outlier (e.g., one Push run at 80K while
two are at 90K), evaluate whether the outlier is anomalous (C4 screening:
http_status=0 > 50% or LAN imbalance > 10:1). If the outlier is anomalous,
exclude it and re-check the gate with the remaining replicates. If two runs
are anomalous, abort the campaign.

## Run Configuration

### Prerequisites

Before the first run, verify the phases file on the cloud VM has the v8
cleanup-gap structure (9 phases):

```bash
ssh cloud-vm "cat ~/efficient-storage-in-edge-scenarios/source/scripts/testing/phases.json | python3 -c \"
import sys,json; p=json.load(sys.stdin)
for ph in p['phases']:
    print(f\\\"{ph['name']:30s} {ph['duration_s']}s\\\")
\""
```

Expected durations:

| Phase | Duration |
|-------|----------|
| `baseline` | 60 s |
| `storage_storm` | 240 s |
| `cleanup_gap_1` | 240 s |
| `tier1_hotspot` | 180 s |
| `inter_hotspot_cooldown` | 300 s |
| `reverse_hotspot` | 180 s |
| `cleanup_gap_2` | 240 s |
| `compute_spike` | 180 s |
| `demand_drop` | 300 s |

If the phases file is missing cleanup-gap phases or has different durations,
copy from a known-good snapshot (e.g. the C2 pilot run's `phases_snapshot.json`).
As of 2026-07-25, the cloud VM's `phases.json` already has the correct 9-phase
cleanup-gap structure (verified by the C2 pilot runs).

The controller env override (`current_state_integrated.env`) must match the
v8/v9_calibration baseline — no threshold or cooldown changes.

No Docker image rebuild is needed. The C2 configuration uses the same images
as v8/v9_calibration.

### Per-Run Cleanup

Between every run, clean leftover network namespaces to avoid
`setup_network: Error 1`:

```bash
ssh cloud-vm "sudo python3 /tmp/clean_ns.py && sudo -n bash ~/efficient-storage-in-edge-scenarios/source/scripts/cleanup.sh"
```

The `clean_ns.py` script must be created on the cloud VM before the first
run. Copy it from the repo host:

```bash
scp tools/clean_ns.py cloud-vm:/tmp/
```

The script deletes leftover network namespaces from `ip netns list` that match
client/edge patterns. This prevents `setup_network` from failing when it
encounters namespaces from a prior run that `cleanup.sh` missed.

### Push Mode (P1–P3)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients \
    setup_test_data run_experiment \
  RUN_LABEL=<LABEL> \
  EDGE_CPUS=0.15 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=185 CLIENTS=96 STORAGE_CPUS=0.08 STORAGE_MEMORY=512m \
  CURL_MAX_TIME=30 RANDOM_SEED=42 DATA_SEED=42 \
  > /tmp/<LABEL>.log 2>&1 &"
```

### Poll-30s Mode (T1–T3)

Same as Push, with:

```
TELEMETRY_SOURCE=poll POLL_INTERVAL_S=30
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

### Run Monitoring

Monitor progress from the host:

```bash
# Check if run is still alive
ssh cloud-vm "pgrep -af 'run_experiment'"

# Tail the log
ssh cloud-vm "tail -20 /tmp/<LABEL>.log"

# Check current phase
ssh cloud-vm "grep -i 'phase\|=== Phase' /tmp/<LABEL>.log | tail -3"
```

After each run completes, verify the run folder exists and has expected
artifacts:

```bash
ssh cloud-vm "ls ~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/<LABEL>/"
```

## Focus & Evidence

### Primary Evidence

| Artifact | What it shows | Measurement |
|----------|--------------|-------------|
| `client_requests.csv` | Per-phase request count, http_status | Throughput gap, timeout rate |
| `latency_summary.csv` | Per-phase/LAN/endpoint percentiles | p50, p90, p95, p99 latency |
| `node_lifecycle_timings.csv` | Spawn timing, node type | Spawn count, G8 validation |
| `per_node_stats.csv` | Per-node CPU per window | Missed opportunities (M2) |

### Secondary Evidence

| Artifact | What it shows |
|----------|--------------|
| `elasticity_events.csv` | Scale decisions, breach detection |
| `container_events.csv` | Dynamic node lifecycle (spawn/stop) |
| `resource_stats.csv` | Controller CPU/RAM overhead |
| `controller_lan1.log` / `controller_lan2.log` | Alerts, exceptions, recovery |
| `phases_snapshot.json` | Phase order, durations, request mix |

### Analysis Outputs (post-campaign)

Run the analysis CLI tools on each run folder, then cross-mode comparison.
All paths are relative to the repo root on the cloud VM
(`~/efficient-storage-in-edge-scenarios/`). CLI tools use `python -m`
module invocation because they have package-relative imports.

| Output | Command |
|--------|---------|
| Latency percentiles | `python source/scripts/tools/metrics_stats.py <run-dir>` (produces `latency_summary.csv`) |
| Blind spot windows (M6) | `python -m source.scripts.testing.analysis.rq1.cli.blind_spot_windows --run-dir <run-dir>` |
| Missed opportunities (M2) | `python -m source.scripts.testing.analysis.rq1.cli.missed_opportunities --run-dir <run-dir>` |
| Cross-mode comparison graphs | `python source/scripts/testing/analysis/rq1/scripts/generate_comparison_graphs.py --run-dirs-push <d1> <d2> <d3> --run-dirs-poll5 <d1> <d2> <d3> --run-dirs-poll12 <d1> <d2> <d3> --run-dirs-poll30 <d1> <d2> <d3> --output-dir docs/operation/testing/experiment/rq1_thesis_final/v10/analysis/` |

### Primary Focus

**Throughput and timeout rate** are the primary success gates — they directly
measure whether the coordination gap cascades into user-visible degradation.
**Latency percentiles** (p50, p95) are the secondary focus — they reveal the
shape of the degradation (median shift vs tail inflation).
**Blind spot windows** (M6) provide the mechanism-level confirmation.

## Metrics & Success Criteria

These are **measurements to report**, not pass/fail gates. The thesis
interprets the separation between modes.

| Measurement | Expected | Evidence |
|-------------|----------|----------|
| **Throughput** | Push ≥ 85K; Poll-30s ≤ 65K; no overlap between worst Push and best Poll-30s | `client_requests.csv` total row count |
| **Timeout rate** | Push ≤ 3%; Poll-30s ≥ 4% in every replicate | `client_requests.csv` http_status=0 |
| **storage_storm throughput** | Push ≥ 14K; Poll-30s ≤ 11K | `client_requests.csv` per-phase |
| **compute_spike throughput** | Push ≥ 30K; Poll-30s ≤ 20K | `client_requests.csv` per-phase |
| **p50 latency** | Push < 15 ms; Poll-30s ≥ 30 ms | `latency_summary.csv` OVERALL row |
| **p95 latency** | Push < 12 s; Poll-30s ≥ 16 s | `latency_summary.csv` OVERALL row |
| **Spawn count** | Push > Poll-30s by ≥2× | `node_lifecycle_timings.csv` compute-typed rows |
| **Blind spot rate (M6)** | Push ≈ 0%; Poll-30s ≥ 50% | Blind spot analysis output |
| **G8** | PASS all 12 runs | `node_lifecycle_timings.csv` no spawns in cleanup_gap phases |
| **Controller overhead** | Flat across modes | `resource_stats.csv` |

Report per-mode means with ±σ (standard deviation across n=3 replicates).
Flag any anomalous runs with timeout rate >15% or LAN-specific failures.

## Validity Threats & Limitations

1. **Single CPU configuration.** C2 (0.15) was chosen because the C2 pilot
   separated Push and Poll-30s cleanly. The entire dose-response curve is
   contingent on this CPU level. A different CPU allocation might produce
   different separation magnitudes.

3. **Single workload shape.** The 9-phase cleanup-gap workload is one specific
   demand pattern. Different phase durations, rates, or compositions may
   produce different results.

4. **No fault injection.** All runs use normal operation. Network partitions,
   controller restarts, and storage-node failures are out of scope.

5. **Known stall bug.** The `create_clients` → `teardown_clients` transition
   experiences a ~33% first-attempt success rate due to a 0%-CPU stall.
   Expect 3–5 launch attempts per run. Recovery procedure on failure:
   1. `sudo -n make -C source/scripts teardown_clients`
   2. `sudo -n bash ~/efficient-storage-in-edge-scenarios/source/scripts/cleanup.sh`
   3. Namespace cleanup: `sudo python3 /tmp/clean_ns.py`
   4. Retry from `setup_network` (full Make target chain)
   Failed attempts do not produce metric files — only a successful
   `run_experiment` completion writes to the metrics folder.

## Artifact Contract

Standard run-folder layout per `docs/operation/testing/testing_overview.md`:

```
source/scripts/testing/metrics/<LABEL>/
├── client_requests.csv
├── latency_summary.csv
├── resource_stats.csv
├── per_node_stats.csv
├── node_lifecycle_timings.csv
├── elasticity_events.csv
├── container_events.csv
├── controller_lan1.log
├── controller_lan2.log
├── phases_snapshot.json
├── controller_env_snapshot.env
└── analysis/                         (post-analysis)
    ├── rq1_blind_spot_windows.csv
    ├── rq1_missed_opportunities.csv
    └── ...
```

After the campaign, cross-mode comparison graphs go to:
`docs/operation/testing/experiment/rq1_thesis_final/v10/analysis/`.
