# Experiment Plan v2-Lite — RQ1 at Reduced WAN Latency

**Status**: 🔵 Designed · **Date**: 2026-07-01
**Parent plan**: [`experiment_plan_v2.md`](./experiment_plan_v2.md) — all structural details there
**Motivation**: [`results_v2.md`](./results_v2.md) §2, Criterion 5

## Intent

Re-run each telemetry mode **at WAN=200ms** in two passes: Pass 1 runs all
four modes once (Push → Poll-5s → Poll-12s → Poll-30s). If Pass 1 confirms
that (a) the v2 blind-spot patterns hold, (b) failure rates are lower
(~7–12% vs ~25–37%), and (c) service-quality variance between modes is
detectable, then Pass 2 repeats the full sequence for a second replicate.

This is a **complementary confirmation**, not a full experiment. It inherits
the v2 plan's hypothesis, RQ linkage, phases, and success criteria unchanged
— only the WAN latency, replicate count, and run order differ. A cloud-VM
reboot between runs eliminates memory-accumulation confounds.

## Hypothesis / Expected Outcome

Same as v2 §Hypothesis, with one refinement for service quality:

5. **Service quality degrades with polling interval, now measurable above
   a lower noise floor.** At WAN=200ms, the v6 calibration experiment
   measured ~7% baseline failure rate (vs ~29% at WAN=260ms). The blind-spot
   contribution (+3–5pp) should be distinguishable from run-to-run variance
   at this baseline.

## Independent Variable & Held-Constant Set

| Parameter | v2 Value | v2-Lite Value | Reason |
|-----------|---------|---------------|--------|
| `WAN_RTT_MS` | 260 | **200** | Reduce baseline failure rate per v6 calibration |
| Replicates per mode | 3 | **2** | Confirm v2 patterns with lower noise floor |
| Reboot between runs | No | **Yes** | Eliminate memory-accumulation confound |
| Everything else | — | Same as v2 | Phases, CLIENTS=48, DEVICES=6000, NODES=100, STORAGE_CPUS=0.10, VIP_HARD_TIMEOUT=60, SS_ENABLED=1, etc. |

## Run Matrix

| # | Pass | Label | `TELEMETRY_SOURCE` | `POLL_INTERVAL_S` | `WAN_RTT_MS` |
|---|------|-------|-------------------|--------------------|--------------|
| 1 | 1 | `rq1_v2lite_push_1` | `zmq` (default) | — | 200 |
| 2 | 1 | `rq1_v2lite_poll5_1` | `poll` | 5 | 200 |
| 3 | 1 | `rq1_v2lite_poll12_1` | `poll` | 12 | 200 |
| 4 | 1 | `rq1_v2lite_poll30_1` | `poll` | 30 | 200 |
| — | — | **Gate check** | — | — | — |
| 5 | 2 | `rq1_v2lite_push_2` | `zmq` (default) | — | 200 |
| 6 | 2 | `rq1_v2lite_poll5_2` | `poll` | 5 | 200 |
| 7 | 2 | `rq1_v2lite_poll12_2` | `poll` | 12 | 200 |
| 8 | 2 | `rq1_v2lite_poll30_2` | `poll` | 30 | 200 |

**Total: 4–8 runs** (Pass 2 is conditional on the gate check).
**Run order**: Push → Poll-5s → Poll-12s → Poll-30s, then repeat if gate passes.
**Campaign duration**: ~2 h for Pass 1 alone; ~4 h if Pass 2 executes
(each run ~28 min with reboot).

## Run Configuration

All prerequisites from v2 §Prerequisites Summary remain in effect
(7-phase `phases.json`, `VIP_HARD_TIMEOUT=60`, TELEMETRY passthrough in
`build_network_setup.sh`). No new prerequisites.

### Pass 1 — First Replicate (always executes)

#### Run 1 — Push

```bash
ssh -o ServerAliveInterval=60 cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_v2lite_push_1 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=200 CLIENTS=48 DEVICES=6000 NODES=100 STORAGE_CPUS=0.10 \
  > /tmp/rq1_v2lite_push_1.log 2>&1 &"
```

#### Run 2 — Poll-5s

```bash
ssh -o ServerAliveInterval=60 cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_v2lite_poll5_1 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=200 CLIENTS=48 DEVICES=6000 NODES=100 STORAGE_CPUS=0.10 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=5 \
  > /tmp/rq1_v2lite_poll5_1.log 2>&1 &"
```

#### Run 3 — Poll-12s

```bash
ssh -o ServerAliveInterval=60 cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_v2lite_poll12_1 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=200 CLIENTS=48 DEVICES=6000 NODES=100 STORAGE_CPUS=0.10 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=12 \
  > /tmp/rq1_v2lite_poll12_1.log 2>&1 &"
```

#### Run 4 — Poll-30s

```bash
ssh -o ServerAliveInterval=60 cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_v2lite_poll30_1 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=200 CLIENTS=48 DEVICES=6000 NODES=100 STORAGE_CPUS=0.10 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=30 \
  > /tmp/rq1_v2lite_poll30_1.log 2>&1 &"
```

### Gate Check — Pass 1 → Pass 2 Decision

After Pass 1 post-run analysis is complete for all four modes, evaluate:

| Condition | What to check | Threshold |
|-----------|---------------|-----------|
| **A. v2 patterns hold** | Reaction latency monotonic: Push < Poll-5s < Poll-12s < Poll-30s | Same rank order as v2 §3.1 |
| **B. Failure rate lower** | Per-mode failure rate (mean across the 4 Pass 1 runs) | ≤ 15% (vs v2's 25–37%) |
| **C. Service-quality spread** | Failure-rate range across the 4 modes | ≥ 3 pp (blind-spot signal detectable above noise) |

- **All three met** → proceed to Pass 2 (second replicate of all four modes).
- **Any condition fails** → stop. Pass 1 alone answers the question; a second
  replicate under degraded conditions adds noise, not signal.

The runner reports the gate outcome and the analyst confirms it before Pass 2
is launched.

### Pass 2 — Second Replicate (conditional on gate)

Same commands as Pass 1, with labels `_2` instead of `_1`:

#### Run 5 — Push (replicate 2)

Same command as Run 1, with label `rq1_v2lite_push_2` and log `/tmp/rq1_v2lite_push_2.log`.

#### Run 6 — Poll-5s (replicate 2)

Same command as Run 2, with label `rq1_v2lite_poll5_2` and log `/tmp/rq1_v2lite_poll5_2.log`.

#### Run 7 — Poll-12s (replicate 2)

Same command as Run 3, with label `rq1_v2lite_poll12_2` and log `/tmp/rq1_v2lite_poll12_2.log`.

#### Run 8 — Poll-30s (replicate 2)

Same command as Run 4, with label `rq1_v2lite_poll30_2` and log `/tmp/rq1_v2lite_poll30_2.log`.

### Between-Run Reboot Protocol

After each run's post-run analysis (chown, parse, 6 CLIs, delete logs):

```bash
# 1. Reboot the cloud VM to clear accumulated memory
ssh cloud-vm "sudo reboot"

# 2. Wait for VM to shut down and come back (~90s typical)
Start-Sleep -Seconds 90

# 3. Confirm SSH is responsive
ssh -o ConnectTimeout=10 -o ConnectionAttempts=10 cloud-vm "echo 'VM ready'"
```

**Rationale**: The v2 12-run campaign revealed progressive memory accumulation
on the cloud VM over extended uptime. A cold reboot between runs eliminates this
confound and ensures each run starts from a clean host state.

### Post-Run Workflow (per run)

Same as v2 §Post-Run Workflow (chown, parse, 6 CLIs, delete controller/service logs).
After analysis, execute the reboot protocol above before launching the next run.

## Focus & Evidence

Same as v2 §Focus & Evidence. Primary focus: reaction latency (Criterion 3).
Secondary: service quality with reduced noise floor (Criterion 5).

## Metrics & Success Criteria

Same 10 criteria as v2 §Metrics & Success Criteria, with adjusted expectations:

| # | Criterion | v2-Lite Expectation |
|---|-----------|-------------------|
| 1 | All runs complete | Pass 1: 4/4 → idle; Pass 2 (if gate): 4/4 → idle |
| 2 | Information age ~0 | Push ~0.05s; Poll ~5–10s (poll-interval gated) |
| 3 | Reaction latency ↑ with poll interval | Push < Poll-5s < Poll-12s < Poll-30s (same pattern as v2) |
| 4 | Mechanisms exercise | All 4 mechanisms in all runs |
| 5 | Service quality degrades | Push ≤ Poll-5s ≤ Poll-12s ≤ Poll-30s, with failure rates ~7–12% (vs v2's 25–37%) |

## Validity Threats

1. **n=1 per mode if gate fails, n=2 if gate passes** — Pass 1 alone provides pattern confirmation; the second replicate adds cross-replicate sanity but formal confidence intervals still require more data.
2. **Run order confound** — Push always first within each pass (cleanest post-reboot host). Mitigated by reboot between every run (all runs start cold) and same mode ordering as v2.
3. **Gate condition C (≥ 3 pp spread) is arbitrary** — it guards against launching Pass 2 when the blind-spot signal is buried in noise. If the spread is < 3 pp, the practical impact of telemetry cadence on service quality is negligible regardless of statistical significance.
4. **Cross-WAN comparability** — Results at WAN=200ms are not directly comparable to v2 WAN=260ms. The two datasets characterise the blind-spot effect at different operating points.
5. **Reboot adds ~2 min per run** — acceptable; host-state consistency is the higher priority.
6. All other v2 validity threats (§Validity Threats) apply unchanged.

## Artifact Contract

Same as v2 §Artifact Contract. Run folders at:
- `source/scripts/testing/metrics/<timestamp>_rq1_v2lite_push_1/`
- `source/scripts/testing/metrics/<timestamp>_rq1_v2lite_push_2/`
- `source/scripts/testing/metrics/<timestamp>_rq1_v2lite_poll5_1/`
- `source/scripts/testing/metrics/<timestamp>_rq1_v2lite_poll5_2/`
- `source/scripts/testing/metrics/<timestamp>_rq1_v2lite_poll12_1/`
- `source/scripts/testing/metrics/<timestamp>_rq1_v2lite_poll12_2/`
- `source/scripts/testing/metrics/<timestamp>_rq1_v2lite_poll30_1/`
- `source/scripts/testing/metrics/<timestamp>_rq1_v2lite_poll30_2/`

Results will be documented in `results_v2_lite.md` in this folder.
