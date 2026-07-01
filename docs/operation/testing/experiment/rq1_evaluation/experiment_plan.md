# Experiment Plan — RQ1 Telemetry Delivery Cadence Evaluation

**Status**: 🔵 Designed · **Date**: 2026-06-21
**Parent**: [`system_to_thesis_map_rq_v2.md`](../../../../../tese/miscelineous/system_to_thesis_map_rq_v2.md) §RQ1

## Intent

Evaluate whether telemetry delivery cadence — aggregator-paced ZMQ push versus
controller-paced HTTP polling at three intervals — measurably delays the
controller's response to overload and degrades service quality during demand
shifts.

This is the **full RQ1 evaluation**. It supersedes the
[rq1_instrumentation_verification](../stability/rq1_instrumentation_verification/experiment_plan.md)
smoke test. The verification experiment confirmed the instrumentation pipeline
works; this experiment produces the data that answers the thesis question.

The single question: **does a blind spot between telemetry polls delay elasticity
actions, and at what polling interval does the delay become measurable as
degraded service quality?**

## Hypothesis / Expected Outcome

The aggregator's HTTP cache always holds the freshest completed summary.
When the controller polls at any interval, it retrieves that latest summary
— the data is always fresh at the moment of consumption. Evidence from the
[rq1_instrumentation_verification](../stability/rq1_instrumentation_verification/results.md)
§5 confirms: `consumed_at − window_end ≈ 0` for all modes, including poll-30s.
This is **correct behavior**, not a measurement failure.

The mechanism that actually delays the controller's response is not stale data
but **missed windows** — the controller simply does not see telemetry between
polls:

```text
Push mode:  controller sees every window (10 s cadence)
            ──[W10]──[W20]──[W30]──[W40]──
            ✅       ✅       ✅       ✅

Poll-30s:   controller sees 1 of every 3 windows
            ──[W10]──[W20]──[W30]──[W40]──
            ❌       ❌       ✅       ❌
            ↑──── blind spot ────↑
```

If overload first appears at W15, the controller in poll-30s does not learn
about it until it polls at t=30 — a 15-second window during which the system
is overloaded but no action is taken. The breach-detection segment of reaction
latency (`spawn_start_ts − breach_window_end`) captures exactly this penalty.

If this mechanism holds:

1. **Information age at consumption** (`consumed_at − window_end`) is ~0 for
   **all** modes. The HTTP cache serves the freshest summary — push and poll
   are indistinguishable by this metric. This confirms the delivery pipeline
   is healthy; it is not expected to differentiate between modes.
2. **Reaction latency increases** with polling interval — this is the
   *consequence* that matters for the thesis. The breach-detection segment
   (`breach_window_end → spawn_start`) grows because the controller cannot
   act on a breach window it hasn't seen yet. In push mode it sees the breach
   within milliseconds; in poll-30s the blind spot may be up to 30 s. The
   provisioning segment (`spawn_start → spawn_done`) is constant (container
   boot time). Evidence from the verification runs (§5): push detection
   9.9–19.8 s, poll-30s detection 9.3–40.0 s.
3. **Transient service quality degrades** when the blind spot prolongs
   overload. p95/p99 latency and failure rate are higher during demand-shift
   phases (`compute_spike`, `storage_stress`) in poll modes compared to push.
4. **Control-plane overhead** differs by mode. Push: near-zero polling
   traffic, persistent ZMQ subscriber greenthread. Poll: HTTP GET every
   `POLL_INTERVAL_S` seconds.
5. **Scaling outcomes diverge** under extreme blind spots. Poll-30s may spawn
   nodes after the demand spike has passed — the breach detector records
   overload but the controller's spawn arrives too late to help.

## RQ Linkage

RQ1 (Information Acquisition pillar) from
[`system_to_thesis_map_rq_v2.md`](../../../../../tese/miscelineous/system_to_thesis_map_rq_v2.md):

> How does telemetry delivery cadence affect controller decision staleness,
> reaction latency, and transient service quality during demand shifts in a
> stateful edge system?

This experiment is the **primary evidence** for the RQ1 evaluation chapter
(thesis Chapter 5). The four conditions map directly to the thesis narrative:

| Condition          | Thesis narrative                                                                                                                                                            |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Push**     | Baseline: no coordination gap. SDN controller receives telemetry at window close — same-process routing sees new backends immediately.                                     |
| **Poll-5s**  | Fast polling: controller polls faster than the window cadence. Tests whether over-polling wastes resources without benefit.                                                 |
| **Poll-12s** | Fair comparison: polls just after window close with headroom for clock desync. The practical alternative to push — cleaner than raw 10 s polling.                          |
| **Poll-30s** | Blind monitoring: encodes the property of separated architectures (Prometheus scrape interval, CloudWatch metric period). Controller sees 1 of every 3 telemetry snapshots. |

## Independent Variable & Held-Constant Set

- **Independent variable**: `TELEMETRY_SOURCE` / `POLL_INTERVAL_S`
- **Held constant**: everything else — workload, thresholds, infrastructure,
  window size, routing policy, container images

| Parameter      | Value                            | Source                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| -------------- | -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Phase file     | `testing/phases.json`          | 10-phase integrated workload (~25 min):`baseline` → `local_moderate` → `storage_stress` → `cross_region_hotspot` → `inter_hotspot_cooldown` → `reverse_hotspot` → `compute_ramp` → `compute_spike` → `sustained_plateau` → `demand_drop`. Exercises storage, Tier 1, and compute sequentially. Both hotspot directions present (`lan2_to_lan1` and `lan1_to_lan2`) so breaches occur on both LANs. `demand_drop` (300 s) exceeds the 180 s cooldown — scale-down fires within the run window. |
| `WINDOW_S`   | 10                               | Default aggregation window. Held constant for all RQ1 conditions.                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| Controller env | `current_state_integrated.env` | [Golden config](../../golden_config.md). Proven stable across the variance_reduction experiment (0.23% overall, compute phases 0.04–0.63%). Uses `SCALEDOWN_COMPUTE_COOLDOWN_S=180` (not 60) — scale-down fires during `demand_drop` (300 s > 180 s cooldown) without the premature node removal that 60 s caused in the verification runs.                                                                                                                                                                                     |
| `CLIENTS`    | 8                                | Standard                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `DEVICES`    | 600                              | Standard                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| `NODES`      | 100                              | Standard                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| Images         | Current HEAD                     | Must include: fixed collector (`_coord_by_window` pairing), polling source, HTTP summary cache, overhead sampler, conntrack routing, WAN TX queue fix. Rebuild if any component is stale.                                                                                                                                                                                                                                                                                                                                          |
| WAN profile    | `metro` (`WAN_RTT_MS=10`)    | Default — required for Tier 1 breach gate to fire                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |

### Why Not `rq1_verify.env`

The verification env uses `SCALEDOWN_COMPUTE_COOLDOWN_S=60` to force scale-down
within the short 480 s run. The
[variance_reduction](../../stability/variance_reduction/results.md) experiment
proved that 60 s cooldown causes premature node removal during peak load
(47–88% failure in compute phases). For the RQ1 evaluation, cooldown behavior
must be held constant at the proven-stable value (180 s) — otherwise compute
phase failures from premature scale-down would confound the reaction latency
measurement. The `demand_drop` phase (300 s) exceeds the 180 s cooldown,
giving 120 s of below-threshold windows for scale-down to fire.

## Run Matrix

| Run                    | `TELEMETRY_SOURCE` | `POLL_INTERVAL_S` | Blind spot                                                 | Purpose                                              |
| ---------------------- | -------------------- | ------------------- | ---------------------------------------------------------- | ---------------------------------------------------- |
| **A** (push)     | `zmq`              | —                  | None — sees every window                                  | Baseline: no coordination gap                        |
| **B** (poll-5s)  | `poll`             | `5`               | None — catches every window (dedup filters ~50% of polls) | Faster than window: exercises dedup, no blind spot   |
| **C** (poll-12s) | `poll`             | `12`              | ~1 of 6 windows missed (desync headroom)                   | Fair comparison: window + headroom, minor blind spot |
| **D** (poll-30s) | `poll`             | `30`              | ~2 of 3 windows missed                                     | Blind monitoring stress test                         |

**Run order**: A → B → C → D. Each run starts after the previous run's
artifacts are copied back and verified. If any run fails to complete
(controller crash, phase freeze, >50% overall failure), investigate and
re-run that single condition before proceeding.

**Replicates**: one run per condition initially. If the push and poll-5s
runs show ≤2 pp difference in overall failure rate (suggesting variance
dominates the signal), add a second replicate per condition. The plan
treats this as a conditional extension, not a requirement.

## Run Configuration

All runs use the same launch shape — only `TELEMETRY_SOURCE` and
`POLL_INTERVAL_S` vary.

### Pre-run Checklist (All Runs)

- [ ] Cloud VM host rebooted (clears accumulated kernel/OVS/Docker state)
- [ ] Container images rebuilt if any code changed since last build
- [ ] `phases.json` has both hotspot directions and `demand_drop` ≥ 300 s
- [ ] `current_state_integrated.env` is the golden config (180 s cooldown)
- [ ] `controller_env_snapshot.env` will be `chown`-ed before copy-back so it survives

### Run A — Push Baseline

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_eval_push \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  CLIENTS=8 DEVICES=600 NODES=100 \
  2>&1"
```

`TELEMETRY_SOURCE` defaults to `zmq`. No `POLL_INTERVAL_S` needed.

### Run B — Poll at 5 s (Faster Than Window)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_eval_poll5 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  CLIENTS=8 DEVICES=600 NODES=100 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=5 \
  2>&1"
```

`POLL_INTERVAL_S=5` < `WINDOW_S=10`. Every window is caught; approximately
every other poll is a duplicate (dedup filters them).

### Run C — Poll at 12 s (Fair Comparison, Desync-Safe)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_eval_poll12 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  CLIENTS=8 DEVICES=600 NODES=100 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=12 \
  2>&1"
```

`POLL_INTERVAL_S=12` = `WINDOW_S=10` + 2 s headroom. The controller polls
just after a new summary is available, avoiding boundary races from clock
drift between the aggregator and controller processes.

### Run D — Poll at 30 s (Stale Monitoring Stress Test)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_eval_poll30 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  CLIENTS=8 DEVICES=600 NODES=100 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=30 \
  2>&1"
```

With `POLL_INTERVAL_S=30` and `WINDOW_S=10`, the controller sees 1 of
every 3 telemetry windows. This is the strongest test of whether the
blind spot measurably degrades control.

### Post-Run Workflow (All Runs)

Controller logs at DEBUG level from a ~25 min run are large (50–200 MB each).
Do not copy them back — run all parsing and analysis on the cloud VM, then
copy back only the reduced folder.

```bash
# === On cloud-vm, after the run completes ===

# 1. Parse controller logs → small event CSVs
python3 source/scripts/tools/parse_elasticity_logs.py \
  metrics/<ts>/controller_lan1.log \
  metrics/<ts>/controller_lan2.log \
  -o metrics/<ts>/elasticity_events.csv \
  --timings-output metrics/<ts>/node_lifecycle_timings.csv

# 2. Make env snapshot readable
sudo chown $(whoami) metrics/<ts>/controller_env_snapshot.env

# 3. Run all analysis CLIs on the cloud VM
python3 -m source.scripts.testing.analysis.rq1.cli.timings         --run-dir metrics/<ts>
python3 -m source.scripts.testing.analysis.rq1.cli.overhead        --run-dir metrics/<ts>
python3 -m source.scripts.testing.analysis.rq1.cli.decision_quality --run-dir metrics/<ts>
python3 -m source.scripts.testing.analysis.cli_simple_run              --run-dir metrics/<ts>
python3 -m source.scripts.testing.analysis.cli_overview                --run-dir metrics/<ts>
python3 -m source.scripts.testing.analysis.cli_phase_summary           --run-dir metrics/<ts>

# 4. Delete controller logs (they've been parsed, no longer needed)
rm metrics/<ts>/controller_lan1.log
rm metrics/<ts>/controller_lan2.log

# === Copy back to local machine ===
# scp -r cloud-vm:~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/<ts> .
# Verify the local copy has all expected artifacts, then optionally:
# ssh cloud-vm "rm -rf ~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/<ts>"
```

After all four runs are complete and copied back, run the cross-run comparison
locally (see [Cross-Run Comparison](#cross-run-comparison) below).

## Focus & Evidence

Five measurement questions answer the thesis RQ1. Measurement 2 (reaction
latency) is the **core evidence** — it captures the blind-spot penalty that
polling introduces. Measurement 1 confirms the HTTP cache works correctly.

### Primary Focus

| # | Role                            | Measurement                                                          | Artifact                                                 | CLI                                             | Output                                                                   |
| - | ------------------------------- | -------------------------------------------------------------------- | -------------------------------------------------------- | ----------------------------------------------- | ------------------------------------------------------------------------ |
| 1 | **Confirmation**          | Information age at consumption (`consumed_at − window_end`)       | `resource_stats_debug.csv`                             | `cli/timings.py`                            | `rq1_staleness.png`, `rq1_staleness.csv`                             |
| 2 | **Core evidence**         | Reaction latency (`spawn_done_ts − breach_window_end`), segmented | `resource_stats_debug.csv` + `elasticity_events.csv` | `cli/timings.py`                            | `rq1_reaction_latency.png`, `rq1_reaction_latency.csv`               |
| 3 | **User-visible impact**   | Transient service quality (p95/p99 latency, failure rate per phase)  | `client_requests.csv`                                  | `cli_simple_run.py`, `cli_phase_summary.py` | `simple_run.png`, `phase_summary.png`                                |
| 4 | **Cost**                  | Control-plane overhead (CPU%, RSS MB per controller)                 | `controller_stats.csv`                                 | `cli/overhead.py`                           | `rq1_overhead_cpu.png`, `rq1_overhead_ram.png`, `rq1_overhead.csv` |
| 5 | **Behavioral divergence** | Scaling outcome description (breached windows vs. spawns per phase)  | `resource_stats_debug.csv` + `container_events.csv`  | `cli/decision_quality.py`                   | `rq1_decision_quality.png`, `rq1_decision_quality.csv`               |

**How measurements 1 and 2 connect to the thesis argument**:

The aggregator's HTTP cache always holds the freshest completed summary.
When the controller polls, it retrieves that latest summary — the data is
fresh at the moment of consumption. **Measurement 1 confirms this**:
`consumed_at − window_end ≈ 0` for all modes, including poll-30s. If
this were NOT the case (e.g., staleness > 5s in push mode), something
is broken in the delivery pipeline.

The real mechanism is **missed windows** — the controller does not see
telemetry between polls. **Measurement 2 captures the consequence**: the
breach-detection segment of reaction latency lengthens because the
controller cannot act on a breach window it has not yet received. The
independent breach detector identifies the first window where overload
is visible; the controller only learns about it at its next poll.
The gap — `spawn_start_ts − breach_window_end` — is the blind-spot
penalty. In push mode this is dominated by the controller's evaluation
logic (sliding window, cooldown, ~10–20s). In poll-30s the blind spot
adds up to 30s on top.

All outputs are written to `<run_dir>/analysis/`. For cross-run comparison,
run `cli_simple_compare.py` across all four run folders.

### Secondary Evidence

| Artifact                               | What to check                                                                                         |
| -------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `resource_stats.csv`                 | `server_count`, `storage_count`, `coord_state_owner_lan` — confirms all 4 mechanisms exercised |
| `container_events.csv`               | `spawn_start`/`spawn_done` in `compute_spike`; `stop`/`destroy` in `demand_drop`          |
| `elasticity_events.csv`              | `compute_scale_up` and `compute_scale_down` events; `node_spawning`/`node_online`             |
| `controller_lan1.log` / `lan2.log` | No tracebacks, no SIGSEGV, no abnormal termination                                                    |
| `phases_snapshot.json`               | Confirms phase order and durations                                                                    |
| `controller_env_snapshot.env`        | Confirms thresholds match golden config                                                               |

### Cross-Run Comparison

After all four runs are analyzed individually, produce a cross-run summary:

```bash
python -m source.scripts.testing.analysis.cli_simple_compare \
  --run-dirs \
    metrics/<ts_push> \
    metrics/<ts_poll5> \
    metrics/<ts_poll12> \
    metrics/<ts_poll30> \
  --output-dir metrics/rq1_eval_comparison \
  --labels Push Poll-5s Poll-12s Poll-30s
```

This produces `simple_compare_overall.png` and `simple_compare_phase.png`
with all four conditions on the same axes.

## Metrics & Success Criteria

These are **evaluation criteria** — they determine whether the experiment
produced interpretable results. They are not pass/fail gates for the system.

| # | Criterion                                           | How checked                                                  | Expectation                                                                                                                                                     |
| - | --------------------------------------------------- | ------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | All 4 runs complete all phases                      | `resource_stats.csv` phase column                          | All 10 phases present (baseline through demand_drop)                                                                                                            |
| 2 | Information age ~0 for all modes                    | `rq1_staleness.csv` per-phase means                        | Push, Poll-5s, Poll-12s, Poll-30s all < 1 s. Confirms the HTTP cache works correctly — the controller always retrieves the freshest summary.                   |
| 3 | Reaction latency increases with polling interval    | `rq1_reaction_latency.csv` breach-detection segment        | Push ≤ Poll-5s ≈ Poll-12s < Poll-30s. This is the**core thesis evidence** — the blind spot between polls delays the controller's response to overload. |
| 4 | All 4 mechanisms exercise in push mode              | `resource_stats.csv` + controller logs                     | Tier 2, Tier 1, compute, conntrack all fire                                                                                                                     |
| 5 | `controller_env_snapshot.env` present in all runs | File exists in run folder                                    | Non-empty, contains threshold values                                                                                                                            |
| 6 | `elasticity_events.csv` present in all runs       | File exists in run folder                                    | ≥ 10 events per run                                                                                                                                            |
| 7 | No controller crashes or tracebacks                 | Controller logs (check before deletion in post-run workflow) | Zero`Traceback`, `SIGSEGV`, or `FATAL`                                                                                                                    |
| 8 | All RQ1 CLIs produce output without error           | CLI exit codes + output files                                | All measurement outputs generated per run                                                                                                                       |
| 9 | Cross-run comparison produces output                | `cli_simple_compare` exit code + PNGs                      | Both comparison PNGs generated                                                                                                                                  |

**Interpretation note**: Criterion 2 should pass trivially — the HTTP cache
design guarantees fresh data at every poll. If it fails, the delivery
pipeline is broken. **Criterion 3 is the thesis finding.** If reaction
latency does NOT increase with polling interval, that is a valid and
publishable result — it means the blind spot between polls does not
translate into measurably slower reactions at these cadences. If criterion 3
holds, the thesis can quantify the relationship: a polling interval of *X*
seconds adds up to *Y* seconds to breach detection time.

## Checkpoints

The operator may observe these in-run triggers. No action is required unless
a checkpoint answer indicates a blocked experiment.

| #  | Trigger                               | Question                                                              | Action if missed                                                                   |
| -- | ------------------------------------- | --------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| C1 | Phase`storage_stress` + 120 s       | `storage_count > 1` in at least one LAN?                            | Storage mechanism not firing — check thresholds in`controller_env_snapshot.env` |
| C2 | Phase`cross_region_hotspot` + 120 s | `coord_state_owner_lan = ACTIVE` for at least one LAN?              | Tier 1 not activating — check WAN latency emulation                               |
| C3 | Phase`compute_spike` + 60 s         | `server_count > 1` in at least one LAN?                             | Compute not scaling — check`SCALEUP_COMPUTE_BASE_THRESHOLD`                     |
| C4 | Phase`demand_drop` + 240 s          | `server_count` and `storage_count` declining?                     | Scale-down not firing — check cooldown timing                                     |
| C5 | Run end                               | All dynamic containers removed? (`container_events.csv`)            | Cleanup debt — check controller logs for scale-down blockers                      |
| C6 | Any run                               | `controller_stats.csv` has rows for both `osken` and `osken_2`? | Overhead sampler failed — check`sample_controller_stats.py` process             |

## Validity Threats & Limitations

1. **Single run per condition**. Statistical power is limited. If push and
   poll-5s show ≤2 pp difference in overall failure rate, variance may
   dominate the signal. The plan allows adding a second replicate per
   condition (see Run Matrix).
2. **`time.time()` wall clock for information age**. Both `window_end` and
   `consumed_at` use `time.time()`. NTP adjustment during a ~25-minute run
   could add ≤1 s error. Negligible — the measurement is ~0 for all modes
   and is only a confirmation check, not a differentiating metric.
3. **Same-host aggregator and controller**. The HTTP polling latency is
   sub-millisecond (same Docker host). In a real deployment, network RTT
   would increase the polling latency but not the blind spot — the controller
   would still miss windows between polls. The measured blind-spot penalty
   is therefore a *lower bound*.
4. **Poll-12s may not generalize**. The 12 s interval (window + 2 s) is
   tuned to the 10 s window. If the window size changes, the headroom must
   be retuned. This condition is a proof-of-concept for desync-safe
   polling, not a universal recommendation.
5. **Scaling outcome description is descriptive, not causal**. The per-phase
   table shows correlation (windows with overload vs. spawns completed) but
   does not prove that the blind spot *caused* a delayed spawn. The thesis
   must interpret this alongside the reaction latency data.
6. **`controller_env_snapshot.env` may be root-owned on cloud VM**. The
   post-run `chown` step must execute before copy-back. If forgotten, the
   breach detector falls back to `scaling_config.py` defaults — which differ
   from the golden config and would produce incorrect threshold comparisons.
7. **Host state accumulation across runs**. Four consecutive ~25-minute runs
   on the same host may accumulate kernel/OVS/Docker state (conntrack table
   entries, OVS datapath flows, Docker network state). The pre-run host
   reboot mitigates this but cannot be enforced by tooling.

## Artifact Contract

Standard run-folder layout per [`testing_overview.md`](../../testing_overview.md)
plus the RQ1 analysis outputs. Each run folder must contain:

| Artifact                               | Required | Notes                                                                          |
| -------------------------------------- | -------- | ------------------------------------------------------------------------------ |
| `client_requests.csv`                | ✅       | Aggregate request log with`phase` column                                     |
| `resource_stats.csv`                 | ✅       | Trimmed domain metrics                                                         |
| `resource_stats_debug.csv`           | ✅       | Broad domain metrics with`consumed_at`                                       |
| `per_node_stats.csv`                 | ✅       | Per-container per-window metrics                                               |
| `container_events.csv`               | ✅       | Docker lifecycle events                                                        |
| `elasticity_events.csv`              | ✅       | Parsed controller events (must be generated before log deletion)               |
| `controller_lan1.log` / `lan2.log` | ✅       | Raw controller logs (may be deleted after`elasticity_events.csv` generation) |
| `controller_env_snapshot.env`        | ✅       | Must survive copy-back (post-run`chown`)                                     |
| `phases_snapshot.json`               | ✅       | Phase configuration snapshot                                                   |
| `controller_stats.csv`               | ✅       | Controller CPU/RAM samples                                                     |
| `service_logs/`                      | ✅       | Edge/storage container logs                                                    |

After running the full analysis pipeline, each run folder adds under `analysis/`:

| Analysis Output                                                          | CLI                          |
| ------------------------------------------------------------------------ | ---------------------------- |
| `rq1_staleness.png`, `rq1_staleness.csv`                             | `cli/timings`            |
| `rq1_reaction_latency.png`, `rq1_reaction_latency.csv`               | `cli/timings`            |
| `rq1_overhead_cpu.png`, `rq1_overhead_ram.png`, `rq1_overhead.csv` | `cli/overhead`           |
| `rq1_decision_quality.png`, `rq1_decision_quality.csv`               | `cli/decision_quality`   |
| `simple_run.png`                                                       | `cli_simple_run`           |
| `overview.png`                                                         | `cli_overview`             |
| `phase_summary.png`                                                    | `cli_phase_summary`        |

Cross-run comparison outputs go to a separate directory (not inside any
single run folder):

| Comparison Output              | CLI                    |
| ------------------------------ | ---------------------- |
| `simple_compare_overall.png` | `cli_simple_compare` |
| `simple_compare_phase.png`   | `cli_simple_compare` |

---

## Changelog

| Date       | Change                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          | Rationale                                       |
| ---------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- |
| 2026-06-21 | Initial plan — full RQ1 evaluation with canonical phases.json + golden config                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | Supersedes rq1_instrumentation_verification     |
| 2026-06-22 | All 4 runs (A–D) completed and analyzed. Key findings: information age ~0 for all modes (criterion 2 ✅); reaction latency increases with blind spot but not monotonic (criterion 3 ⚠️); Tier 1 only fired in Poll-12s (criterion 4 ⚠️); overhead indistinguishable (criterion 4 ✅).                                                                                                                                                                                                                                                                     | Initial v1 analysis; see`results.md` §1–§6 |
| 2026-06-25 | **Rerun approved.** MAC-recycling bug in `node_registry.py` fixed (B1: name-aware removal, B2: self-contained slot activation). Verified with 7 `[reserve] activated` events across golden_config pair, 1 stale-removal guard trigger, 0 "consume returned None." Earlier "Push preempted Tier 1" theory withdrawn — Tier 1 regression from golden_config_stability is a separate, unresolved issue. Fix alone justifies rerun: reaction latency baseline stronger with reserve fast path working.                                                 | See`results.md` §7–§8                      |
| 2026-06-26 | **v2 complete.** All 4 runs (A–D) executed with fixed code. Reserve activation confirmed (6–7 in fast modes, degrades to 1–3 in slow polling). Tier 1 fires in lan1→lan2 direction (34→30→32→0 ACTIVE); reverse direction blocked by virtual-MAC mismatch in `resolve_peer_primary()` — **fixed 2026-06-26**. Service quality degrades monotonically: 0.14%→0.29%→1.20%→1.70% (12× from Push to Poll-30s). Variance condition met (0.15pp ≤ 2pp) — replicates recommended. v2 cross-run comparison at `rq1_eval_v2_comparison/`. | See`results.md` §8                           |
| 2026-06-26 | **Virtual-MAC mismatch in `resolve_peer_primary()` fixed.** `_peer_storage_roles` uses real Docker MACs but the method looked them up by virtual MACs from `STORAGE_MACS_N*`. Fix: two-step resolution — confirm primary via `_peer_storage_roles` (real MACs), resolve IP via `_peer_storage_macs_n*` → `peer_hosts` (virtual MACs). Smoke test passed (bidirectional Tier 1 in tier1_smoke). Replicates confirm: 0 "no primary known" across all 4 runs.                                                                                 | See`tier1_activation_smoke_test/results.md`   |
| 2026-06-26 | **v2-replicates complete.** All 4 runs (A′–D′) with topology fix. Bidirectional Tier 1 restored — first time since June 9. Zero "no primary known." Reserve 5–8 per run. BUT — extreme variance: Push replicate 5.04% vs v2 Push 0.14% (35×). v2 monotonic degradation NOT replicated. Poll-12s consistently worst-case (370.4s). Service quality and mechanism suppression claims from v2 withdrawn. n=2 insufficient.                                                                                                                           | See`results.md` §9                           |
