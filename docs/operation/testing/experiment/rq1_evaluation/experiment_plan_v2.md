Experiment Plan v2 — RQ1 Telemetry Delivery Cadence Evaluation

# Experiment Plan v2 — RQ1 Telemetry Delivery Cadence Evaluation

**Status**: ✅ Executed · **Date**: 2026-06-30 (plan), 2026-07-01 (executed)
**Results**: [`results_v2.md`](./results_v2.md)
**Prior work**: [`experiment_plan.md`](./experiment_plan.md) (v1, lightweight workload),
[`rq1_evaluation_final/experiment_plan.md`](../rq1_evaluation_final/experiment_plan.md) (final n=3, lightweight workload)
**Golden config**: [`golden_config.md`](../../golden_config.md)

This v2 plan is a **complementary experiment** at the golden-config workload
scale — it does not supersede the rq1_evaluation_final dataset, which remains
the definitive lightweight-workload RQ1 evidence. The two datasets together
characterize whether the blind-spot effect scales with workload intensity.

## Intent

Evaluate whether telemetry delivery cadence — aggregator-paced ZMQ push versus
controller-paced HTTP polling at three intervals — measurably delays the
controller's response to overload and degrades service quality during demand
shifts, **under the canonical golden-config workload**.

All prior RQ1 experiments (v1, v2, v2-replicates, final n=3) used a lightweight
workload: `CLIENTS=8`, `DEVICES=600`, `WAN_RTT_MS=10`. This experiment adopts
the golden config wholesale — `CLIENTS=48`, `DEVICES=6000`, `WAN_RTT_MS=260`,
`STORAGE_CPUS=0.10` — to stress the system at the calibrated operating point
where all four mechanisms (storage reserve, Tier 1 selective sync, compute
elasticity, conntrack routing) are proven to exercise. The heavier workload
produces more requests per phase (~200k–300k per run vs ~80k in prior
experiments), reducing the run-to-run variance that dominated prior service
quality measurements.

The single question: **does a blind spot between telemetry polls delay
elasticity actions, and at what polling interval does the delay become
measurable as degraded service quality?**

## Hypothesis / Expected Outcome

1. **Information age at consumption** (`consumed_at − window_end`) is ~0 for
   **all** modes. The HTTP cache serves the freshest completed summary —
   push and poll are indistinguishable by this metric. Robustly confirmed
   across 12/12 prior runs; not expected to change.
2. **Reaction latency increases with polling interval.** The breach-detection
   segment (`breach_window_end → spawn_start`) grows because the controller
   cannot act on a breach window it hasn't seen yet.

   **Mechanism-based expectation**: Push, Poll-5s, and Poll-12s all catch
   every window (~0 blind spot) — only Poll-30s has a genuine blind spot
   (~2 of 3 windows missed). The expected ordering from mechanism alone is:
   **Push ≤ Poll-5s ≈ Poll-12s < Poll-30s**.

   **Empirical complication**: Poll-12s was the worst case in all 3 prior
   iterations (329.6s, 160.4s, 370.4s) despite catching every window. A 2s
   per-window headroom accumulating over ~30 windows explains at most ~60s of
   additional latency, not the 160–370s observed. The mechanism is unclear —
   possibly the 12s polling cadence interacts with the sliding-window/cooldown
   evaluation logic in a way that amplifies small delays. v2 tests whether
   this pattern holds at golden-config scale or whether Poll-12s and Poll-5s
   converge to similar latency (as the mechanism predicts).

   **Known anomaly (rq1_evaluation_final Push_3):** Push mode may produce
   **0 reaction latency events** — the breach-detector registers no storage
   threshold breaches because the controller sees every window and prevents
   overload from developing into a detected breach. This is a valid mechanism
   effect (breach suppression via continuous visibility), not a measurement
   failure. If it recurs in v2, report the event count per mode and note that
   Push's 0 events prevents cross-mode latency comparison for that run — but
   the absence of breaches is itself evidence of superior control.
3. **Transient service quality degrades** as the blind spot prolongs overload.
   Under the heavier golden-config workload (48 clients, 260ms WAN, 6000
   devices), the stress is sufficient that missed telemetry windows should
   translate into measurably higher p95/p99 latency and failure rates during
   demand-shift phases. Expected ordering: **Push ≤ Poll-5s ≤ Poll-12s ≤
   Poll-30s** for overall failure rate.

   **Open question from rq1_evaluation_final:** Under the lightweight workload
   (CLIENTS=8, DEVICES=600, WAN=10ms), Push showed **higher** failure rates
   than all Poll modes (Push mean 0.54% vs Poll modes 0.08–0.13%). Two
   competing hypotheses for the golden-config scale:

   - **(a) Reversal**: At 48 clients, request-handling pressure dominates and
     ZMQ overhead becomes negligible → Push ≤ Poll ordering emerges.
   - **(b) Amplification**: ZMQ push-event overhead scales with request volume
     → Push > Poll gap widens.
     Both outcomes are thesis-relevant. A reversal validates the blind-spot
     hypothesis; an amplification reveals a previously uncharacterized
     controller-overhead trade-off in push-based telemetry.
4. **All four mechanisms exercise** in all modes — bidirectional Tier 1,
   storage reserve activation, compute elasticity, conntrack routing. All
   three code fixes (MAC-recycling, topology resolution, name-aware removal)
   are deployed and verified.
5. **Control-plane overhead** differs modestly by mode. Push: persistent ZMQ
   subscriber greenthread. Poll: HTTP GET every `POLL_INTERVAL_S` seconds.
   Prior experiments showed indistinguishable CPU/RAM between modes; the
   heavier workload may widen the gap.

## RQ Linkage

RQ1 (Information Acquisition pillar) from
[`system_to_thesis_map_rq_v2.md`](../../../../../tese/miscelineous/system_to_thesis_map_rq_v2.md):

> How does telemetry delivery cadence affect controller decision staleness,
> reaction latency, and transient service quality during demand shifts in a
> stateful edge system?

This experiment is the **primary evidence** for the RQ1 evaluation chapter
(thesis Chapter 5). The four conditions map to the thesis narrative:

| Condition          | Thesis narrative                                                                                                                                  |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Push**     | Baseline: no coordination gap. SDN controller receives telemetry at window close.                                                                 |
| **Poll-5s**  | Fast polling: polls faster than the window cadence. Tests whether over-polling wastes resources.                                                  |
| **Poll-12s** | Fair comparison: polls just after window close with headroom for clock desync.                                                                    |
| **Poll-30s** | Blind monitoring: encodes the property of separated architectures (Prometheus scrape interval). Controller sees 1 of every 3 telemetry snapshots. |

## Independent Variable & Held-Constant Set

- **Independent variable**: `TELEMETRY_SOURCE` / `POLL_INTERVAL_S`
- **Held constant**: everything else — workload, thresholds, infrastructure,
  window size, routing policy, container images

| Parameter                              | Value                            | Source                                                    |
| -------------------------------------- | -------------------------------- | --------------------------------------------------------- |
| Phase file                             | `testing/phases.json`          | Mixed 7-phase workload (see §Phases Design)              |
| `WINDOW_S`                           | 10                               | Default aggregation window                                |
| Controller env                         | `current_state_integrated.env` | Golden config. Add`VIP_HARD_TIMEOUT=60`                 |
| `WAN_RTT_MS`                         | **260**                    | Golden config — cross-region penalty visible             |
| `CLIENTS`                            | **48**                     | Golden config — load volume for storage + Tier 1 stress |
| `DEVICES`                            | **6000**                   | Golden config — dataset cardinality                      |
| `NODES`                              | **100**                    | Held constant across all experiments                      |
| `STORAGE_CPUS`                       | **0.10**                   | Golden config — single node hits 46% without elasticity  |
| Images                                 | Current HEAD                     | Must include all three code fixes                         |
| `SS_ENABLED`                         | 1                                | Tier 1 selective-sync enabled                            |
| `STORAGE_PERSISTENT_RESERVE_ENABLED` | 1                                | Tier 2 storage reserve enabled                           |

### Code Fixes (All Verified, Deployed)

| Fix                                         | File                                                | Verification                                      |
| ------------------------------------------- | --------------------------------------------------- | ------------------------------------------------- |
| MAC-recycling collision (reserve)           | `node_registry.py` B1+B2, `elasticity.py` B1    | 7`[reserve] activated` in fix-verification      |
| Topology resolution (Tier 1 bidirectional) | `topology.py` `resolve_peer_primary()` two-step | 0 "no primary known" across all v2-replicate runs |
| Name-aware removal guard                    | `node_registry.py` `sync()`                     | 1 stale-removal guard trigger in fix-verification |

### Phases Design — Mixed 7-Phase Workload

The golden config's 6-phase workload lacks `reverse_hotspot` (bidirectional
Tier 1 needed — was a bug vector in prior experiments) and `demand_drop`
(scale-down observation — critical for RQ1 blind-spot measurement). The
original RQ1 10-phase workload has phases that don't add distinct stress
(`local_moderate`, `compute_ramp`, `sustained_plateau`).

**Mixed 7-phase workload** — golden config rates/durations/mixes for shared
phases, plus `reverse_hotspot` and `demand_drop`:

| # | Phase                      | Dur  | Rate/Client | Cross-Reg | Client Frac | Mix (DS/D/SP/DU/DA) | Stresses          |
| - | -------------------------- | ---- | ----------- | --------- | ----------- | ------------------- | ----------------- |
| 1 | `baseline`               | 60s  | 1.0         | 0%        | 0.5         | .60/.25/.15/0/0     | —                |
| 2 | `storage_storm`          | 240s | 4.0         | 90%       | 1.0         | .35/.10/.05/.30/.20 | Storage           |
| 3 | `tier1_hotspot`          | 180s | 5.0         | 95%       | 1.0         | .80/.05/.05/.05/.05 | Tier 1 (dir 1)   |
| 4 | `inter_hotspot_cooldown` | 300s | 1.0         | 0%        | 0.1         | .60/.25/.15/0/0     | Scale-down window |
| 5 | `reverse_hotspot`        | 180s | 5.0         | 95%       | 1.0         | .80/.05/.05/.05/.05 | Tier 1 (dir 2)   |
| 6 | `compute_spike`          | 180s | 4.0         | 5%        | 1.0         | .20/.65/.15/0/0     | Compute           |
| 7 | `demand_drop`            | 300s | 1.0         | 0%        | 0.10        | .60/.25/.15/0/0     | Scale-down        |

**Total: 1440s (24 min).** Mix keys: DS=`device_status`, D=`dashboard`,
SP=`service_pressure`, DU=`device_update`, DA=`device_aggregate`.

`hotspot_direction` is `""` (empty/automatic) for all phases — the traffic
generator derives direction from the phase name.

`demand_drop` uses `client_fraction: 0.10` (not 0.5). Rationale: at 48
clients, 0.10 = 4.8 req/s — consistent with the golden config's
`inter_hotspot_cooldown` convention. At 0.5 (24 req/s), load never truly
"drops" below threshold and scale-down may not fire within the 300s window.
Scale-down timeline: `compute_spike` ends at t=960, `demand_drop` starts.
`SCALEDOWN_COMPUTE_COOLDOWN_S=180` gates when scale-down *can* fire (t=1140
earliest). `SCALE_DOWN_COMPUTE_REQUIRED=9` consecutive below-threshold windows
(`WINDOW_S=10`) gates whether it *does* fire (90s of sustained low load). With
`demand_drop` lasting 300s (t=960→1260), there are 120s of eligible time
(t=1140→1260) — enough for 12 windows, well above the 9 required. At 0.10
client fraction (4.8 req/s), load should stay below threshold throughout.

> **Prerequisite**: Edit `source/scripts/testing/phases.json` to this 7-phase
> spec before launching any run. The current file contains the golden config
> 6-phase workload. The run folder will capture a `phases_snapshot.json` copy.

## Run Matrix

| Mode               | `TELEMETRY_SOURCE` | `POLL_INTERVAL_S` | Blind spot                                          | Runs | Labels                        |
| ------------------ | -------------------- | ------------------- | --------------------------------------------------- | ---- | ----------------------------- |
| **Push**     | `zmq`              | —                  | None — sees every window                           | 3    | `rq1_v2_push_1` … `_3`   |
| **Poll-5s**  | `poll`             | `5`               | None — catches every window (dedup filters ~50%)   | 3    | `rq1_v2_poll5_1` … `_3`  |
| **Poll-12s** | `poll`             | `12`              | ~0 (headroom absorbs drift — catches every window) | 3    | `rq1_v2_poll12_1` … `_3` |
| **Poll-30s** | `poll`             | `30`              | ~2 of 3 windows missed                              | 3    | `rq1_v2_poll30_1` … `_3` |

**Total: 12 runs. Run order**: Push_1 → Push_2 → Push_3 → Poll-5s_1 →
Poll-5s_2 → Poll-5s_3 → Poll-12s_1 → Poll-12s_2 → Poll-12s_3 → Poll-30s_1 →
Poll-30s_2 → Poll-30s_3. Push runs first (cleanest host state, works against
the thesis claim that Push should be best). If any run fails to complete
(controller crash, phase freeze, >50% overall failure), investigate and re-run
that single run before proceeding.

**Campaign duration**: ~6 hours minimum (12 runs × ~30 min each: 24 min run +
5 min settle + ~1 min post-run). With degradation escape hatch reboots, ~8
hours. Allocate a full-day window.

## Host-State Protocol

**No reboots (with degradation escape hatch).** Between every run:

```bash
# Full teardown
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && make -C source/scripts cleanup 2>&1"
# Wait 5 min for kernel/OVS/Docker state to settle
sleep 300
```

Between modes, the same protocol applies (no special handling).

**Degradation escape hatch**: The rq1_evaluation_final experiment demonstrated
that host-state accumulation is real and measurable — Push_1 (5th consecutive
run without reboot) failed at 5.04% vs Push_2 (1st run after reboot) at 0.33%,
a 15× degradation. If any run shows anomalous degradation relative to its mode
siblings (e.g., >3× the failure rate of the cleanest run in that mode),
immediately reboot the cloud VM before the next run:

```bash
ssh cloud-vm "sudo reboot"; sleep 60  # wait for SSH to come back
```

Also reboot if the operator observes any of: (a) `make cleanup` leaving
residual containers/bridges, (b) >10% `make cleanup` commands taking >30s,
(c) kernel logs showing OVS or conntrack errors between runs.

**Rationale for no-reboot default**: Rebooting takes 30–60s plus SSH
reconnection. A 5-minute settle after full `make cleanup` is expected to
be sufficient. The golden config's heavier workload may also produce
different accumulation patterns than the lightweight workload. The escape
hatch ensures we don't lose data to host-state degradation as happened
with Push_1 in rq1_evaluation_final.

## Run Configuration

### Pre-run Checklist (Once Per Experiment)

- [ ] Cloud VM reachable: `ssh cloud-vm`
- [ ] All three code fixes present on cloud VM
- [ ] `phases.json` edited to 7-phase mixed workload
- [ ] `current_state_integrated.env` includes `VIP_HARD_TIMEOUT=60` (see §Env Override)
- [ ] `sudo -n` working (no password prompt)
- [ ] Container images rebuilt if any code changed since last build

### Env Override — Add `VIP_HARD_TIMEOUT=60`

The golden config specifies `VIP_HARD_TIMEOUT=60` for WAN ≥200ms. The default
is 120s (from `osken-controller.env`). `current_state_integrated.env` does not
currently set this value. **Add the following line** before launching:

```
VIP_HARD_TIMEOUT=60
```

> Rationale: The golden config was calibrated with VIP_HARD_TIMEOUT=60 for v6
> experiments. At WAN_RTT_MS=260, 60s prevents timeout censorship while keeping
> the hard-timeout safety net. The default 120s is also safe but diverges from
> the calibrated golden config.

### Run A1–A3 — Push Baseline

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_v2_push_1 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=260 CLIENTS=48 DEVICES=6000 NODES=100 STORAGE_CPUS=0.10 \
  2>&1" | tee run_rq1_v2_push_1.log
```

`TELEMETRY_SOURCE` defaults to `zmq`. No `POLL_INTERVAL_S` needed.
Repeat for `_2` and `_3` with appropriate labels.

### Run B1–B3 — Poll at 5s (Faster Than Window)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_v2_poll5_1 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=260 CLIENTS=48 DEVICES=6000 NODES=100 STORAGE_CPUS=0.10 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=5 \
  2>&1" | tee run_rq1_v2_poll5_1.log
```

`POLL_INTERVAL_S=5` < `WINDOW_S=10`. Every window is caught; approximately
every other poll is a duplicate (dedup filters them).

### Run C1–C3 — Poll at 12s (Fair Comparison, Desync-Safe)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_v2_poll12_1 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=260 CLIENTS=48 DEVICES=6000 NODES=100 STORAGE_CPUS=0.10 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=12 \
  2>&1" | tee run_rq1_v2_poll12_1.log
```

`POLL_INTERVAL_S=12` = `WINDOW_S=10` + 2s headroom. The 2s headroom means
every poll catches the just-closed window: poll at t=12 catches W10, t=24
catches W20, t=36 catches W30 — **zero windows missed**. Avoids boundary
races from clock drift between aggregator and controller processes. Prior
evidence (3/3 iterations) shows Poll-12s is consistently the worst case for
reaction latency despite catching every window — the 2s headroom introduces
a minor delay that accumulates across the sliding-window evaluation.

### Run D1–D3 — Poll at 30s (Blind Monitoring Stress Test)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_v2_poll30_1 \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=260 CLIENTS=48 DEVICES=6000 NODES=100 STORAGE_CPUS=0.10 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=30 \
  2>&1" | tee run_rq1_v2_poll30_1.log
```

Controller sees 1 of every 3 telemetry windows — the strongest test of
whether the blind spot measurably degrades control.

### Post-Run Workflow (Per Run)

Controller logs at DEBUG level from a ~24 min run with 48 clients are large
(100–400 MB each). Do not copy them back — run all parsing and analysis on
the cloud VM, then copy back only the reduced folder.

```bash
# === On cloud-vm, after the run completes ===

RUN_DIR="source/scripts/testing/metrics/$(ls -t source/scripts/testing/metrics/ | head -1)"

# 1. Parse controller logs → small event CSVs
python3 source/scripts/tools/parse_elasticity_logs.py \
  "$RUN_DIR/controller_lan1.log" \
  "$RUN_DIR/controller_lan2.log" \
  -o "$RUN_DIR/elasticity_events.csv" \
  --timings-output "$RUN_DIR/node_lifecycle_timings.csv"

# 2. Make env snapshot readable (may be root-owned)
sudo chown $(whoami) "$RUN_DIR/controller_env_snapshot.env"

# 2b. Verify env snapshot is readable before CLIs consume it
python3 -c "import os; d='$RUN_DIR/controller_env_snapshot.env'; assert os.access(d, os.R_OK), f'Cannot read {d}'; print('OK:', d)"

# 3. Run all analysis CLIs on the cloud VM
python3 -m source.scripts.testing.analysis.rq1.cli.timings         --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.rq1.cli.overhead        --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.rq1.cli.decision_quality --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.cli_simple_run              --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.cli_overview                --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.cli_phase_summary           --run-dir "$RUN_DIR"

# 4. Delete controller logs (parsed, no longer needed)
rm "$RUN_DIR/controller_lan1.log" "$RUN_DIR/controller_lan2.log"

# 5. Delete service logs (large, not needed for RQ1 analysis)
rm -rf "$RUN_DIR/service_logs/"

# === Copy back to local machine ===
# scp -r cloud-vm:~/efficient-storage-in-edge-scenarios/"$RUN_DIR" ./source/scripts/testing/metrics/
# Verify the local copy has all expected artifacts
```

### Cross-Run Comparison

After all 12 runs are analyzed individually, produce a cross-run summary per
mode (3 runs each) and an all-modes comparison:

```bash
# Per-mode comparison (3 runs each)
python -m source.scripts.testing.analysis.cli_simple_compare \
  --run-dirs metrics/<push_1> metrics/<push_2> metrics/<push_3> \
  --output-dir metrics/rq1_v2_push_comparison \
  --labels Push_1 Push_2 Push_3

# ... repeat for poll5, poll12, poll30 ...

# All-modes comparison (use run _2 from each mode as representative)
python -m source.scripts.testing.analysis.cli_simple_compare \
  --run-dirs \
    metrics/<push_2> \
    metrics/<poll5_2> \
    metrics/<poll12_2> \
    metrics/<poll30_2> \
  --output-dir metrics/rq1_v2_comparison \
  --labels Push Poll-5s Poll-12s Poll-30s
```

## Focus & Evidence

### Primary Focus

| # | Role                            | Measurement                                                          | Artifact                                                 | CLI                                             | Output                                                     |
| - | ------------------------------- | -------------------------------------------------------------------- | -------------------------------------------------------- | ----------------------------------------------- | ---------------------------------------------------------- |
| 1 | **Confirmation**          | Information age at consumption (`consumed_at − window_end`)       | `resource_stats_debug.csv`                             | `cli/timings.py`                            | `rq1_staleness.png`, `rq1_staleness.csv`               |
| 2 | **Core evidence**         | Reaction latency (`spawn_done_ts − breach_window_end`), segmented | `resource_stats_debug.csv` + `elasticity_events.csv` | `cli/timings.py`                            | `rq1_reaction_latency.png`, `rq1_reaction_latency.csv` |
| 3 | **User-visible impact**   | Transient service quality (p95/p99 latency, failure rate per phase)  | `client_requests.csv`                                  | `cli_simple_run.py`, `cli_phase_summary.py` | `simple_run.png`, `phase_summary.png`                  |
| 4 | **Cost**                  | Control-plane overhead (CPU%, RSS MB per controller)                 | `controller_stats.csv`                                 | `cli/overhead.py`                           | `rq1_overhead_cpu.png`, `rq1_overhead_ram.png`         |
| 5 | **Behavioral divergence** | Scaling outcome (breached windows vs spawns per phase)               | `resource_stats_debug.csv` + `container_events.csv`  | `cli/decision_quality.py`                   | `rq1_decision_quality.png`                               |

**Measurement 2 is the core thesis evidence.** The breach-detection segment
(`spawn_start_ts − breach_window_end`) captures the blind-spot penalty: the
controller cannot act on a breach window it hasn't received yet. In push mode
this is dominated by evaluation logic (~10–20s). In poll-30s the blind spot
adds up to 30s on top.

**Measurement 3 is the secondary thesis evidence.** Under the golden config's
heavier workload (48 clients, 260ms WAN), each run produces ~200k–300k requests
(vs ~80k in prior experiments). The larger sample size per phase should reduce
the run-to-run variance that dominated prior service quality measurements,
enabling the first meaningful cross-mode comparison of failure rates.

### Secondary Evidence

| Artifact                               | What to check                                                                                         |
| -------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| `resource_stats.csv`                 | `server_count`, `storage_count`, `coord_state_owner_lan` — confirms all 4 mechanisms exercised |
| `container_events.csv`               | `spawn_start`/`spawn_done` in `compute_spike`; `stop`/`destroy` in `demand_drop`          |
| `elasticity_events.csv`              | `compute_scale_up`/`compute_scale_down` events; `node_spawning`/`node_online`                 |
| `controller_lan1.log` / `lan2.log` | Check before deletion: no tracebacks, no SIGSEGV, no abnormal termination                             |
| `phases_snapshot.json`               | Confirms phase order and durations                                                                    |
| `controller_env_snapshot.env`        | Confirms thresholds match golden config;`VIP_HARD_TIMEOUT=60` present                               |

## Metrics & Success Criteria

These are **evaluation criteria** — they determine whether the experiment
produced interpretable results. They are not pass/fail gates for the system.

| #  | Criterion                                        | How checked                                                          | Expectation                                                                                                                                                                                                                                                                                                                                                          |
| -- | ------------------------------------------------ | -------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1  | All 12 runs complete all phases                  | `current_phase.txt` = `idle`; 7 phases in `resource_stats.csv` | 12/12                                                                                                                                                                                                                                                                                                                                                                |
| 2  | Information age ~0 for all modes                 | `rq1_staleness.csv` per-phase max                                  | < 0.05s for all modes. Confirms HTTP cache works.                                                                                                                                                                                                                                                                                                                    |
| 3  | Reaction latency increases with polling interval | `rq1_reaction_latency.csv` breach-detection segment                | Mechanism-based:**Push ≤ Poll-5s ≈ Poll-12s < Poll-30s**. Prior data (3/3) showed Poll-12s > Poll-30s — v2 tests whether this empirical anomaly persists at golden-config scale. **If Push produces 0 events** (breach suppression — see Hypothesis §2), report event count per mode; 0 events in Push is a valid finding, not a criterion failure. |
| 4  | All 4 mechanisms exercise in all runs            | `resource_stats.csv` + controller logs                             | Reserve (≥1`[reserve] activated`), Tier 1 bidirectional (`coord_state_owner_lan=ACTIVE` on both LANs), compute spawns, conntrack entries                                                                                                                                                                                                                       |
| 5  | Service quality degrades with polling interval   | Per-mode mean failure rate (n=3)                                     | Push ≤ Poll-5s ≤ Poll-12s ≤ Poll-30s. Compute mean and range per mode from 3 replicates.                                                                                                                                                                                                                                                                          |
| 6  | `controller_env_snapshot.env` present          | File exists, non-empty                                               | All 12 runs                                                                                                                                                                                                                                                                                                                                                          |
| 7  | `elasticity_events.csv` present                | File exists, ≥10 events                                             | All 12 runs                                                                                                                                                                                                                                                                                                                                                          |
| 8  | No controller crashes or tracebacks              | Controller logs (check before deletion)                              | 0 across all runs                                                                                                                                                                                                                                                                                                                                                    |
| 9  | All RQ1 CLIs produce output                      | CLI exit codes + output files                                        | All measurement outputs per run                                                                                                                                                                                                                                                                                                                                      |
| 10 | Cross-run comparison produces output             | `cli_simple_compare` exit code + PNGs                              | Per-mode and all-modes comparison PNGs                                                                                                                                                                                                                                                                                                                               |

**Interpretation notes:**

- **Criterion 2** should pass trivially — the HTTP cache guarantees fresh data.
  If it fails, the delivery pipeline is broken.
- **Criterion 3 is the thesis finding.** If reaction latency does NOT increase
  with polling interval at the golden-config workload scale, that is a valid
  result — it bounds the blind-spot problem.
- **Criterion 5 is the secondary thesis finding.** With n=3 per mode and
  ~200k–300k requests per run, the failure rate means should be stable enough
  for cross-mode comparison. Report per-mode means with ranges (min–max), not
  confidence intervals (n=3 is insufficient for formal CIs).
- **Criterion 4** — if Tier 1 fires in only one direction, the topology
  resolution fix has regressed. Stop and investigate before proceeding.

## Checkpoints

The operator may observe these in-run triggers. No action is required unless
a checkpoint answer indicates a blocked experiment.

| #  | Trigger                         | Question                                                              | Action if missed                                           |
| -- | ------------------------------- | --------------------------------------------------------------------- | ---------------------------------------------------------- |
| C1 | Phase`storage_storm` + 120s   | `storage_count > 1` in at least one LAN?                            | Storage mechanism not firing — check thresholds           |
| C2 | Phase`tier1_hotspot` + 120s   | `coord_state_owner_lan = ACTIVE` for at least one LAN?              | Tier 1 not activating — check WAN emulation, SS_ENABLED  |
| C3 | Phase`reverse_hotspot` + 120s | `coord_state_owner_lan = ACTIVE` for the OTHER LAN?                 | Bidirectional Tier 1 failing — check topology resolution |
| C4 | Phase`compute_spike` + 60s    | `server_count > 1` in at least one LAN?                             | Compute not scaling — check thresholds                    |
| C5 | Phase`demand_drop` + 240s     | `server_count` and `storage_count` declining?                     | Scale-down not firing — check cooldown timing             |
| C6 | Run end                         | All dynamic containers removed? (`container_events.csv`)            | Cleanup debt — check controller logs                      |
| C7 | Any run                         | `controller_stats.csv` has rows for both `osken` and `osken_2`? | Overhead sampler failed                                    |

## Validity Threats & Limitations

1. **n=3 per mode.** Means are estimable but n=3 is insufficient for formal
   confidence intervals. Report means with min–max ranges. The ~200k–300k
   requests per run provide stable per-run rates; cross-run variance within
   a mode reflects genuine host-state/system variance, not sampling error.
2. **No reboot between modes.** Host state may accumulate across the 12-run
   campaign (~5–6 hours total). The 5-minute settle after `make cleanup` is
   expected to be sufficient, but the rq1_evaluation_final experiment
   demonstrated that accumulation is real (Push_1 at 5.04% after 4 prior runs
   vs Push_2 at 0.33% after reboot). The degradation escape hatch (§Host-State
   Protocol) mitigates this — if any run shows >3× the failure rate of its
   cleanest mode sibling, reboot before the next run.
3. **Run order confound.** Push always runs first (cleanest host state).
   If Push consistently shows the lowest failure rates, host-state advantage
   is a confound. Mitigation: Push being best actually supports the thesis
   claim. If Push shows HIGHER failure than Poll modes despite running first,
   the finding is strengthened (works against confound).
4. **Push 0 reaction events (known from rq1_evaluation_final).** Push_3
   produced 0 breach-detector events — the controller's continuous visibility
   prevented any breach window from opening. If this recurs, cross-mode
   reaction latency comparison is incomplete for that run. Mitigation:
   report event counts per mode; treat 0 events as a valid mechanism effect
   (breach suppression), not missing data. The service quality comparison
   (criterion 5) remains valid regardless.
5. **Same-host aggregator and controller.** HTTP polling latency is
   sub-millisecond (same Docker host). In a real deployment, network RTT
   would increase polling latency but not the blind spot — the controller
   would still miss windows between polls. The measured blind-spot penalty
   is a lower bound.
6. **Poll-12s may not generalize.** The 12s interval (window + 2s) is tuned
   to the 10s window. If window size changes, headroom must be retuned.
7. **`controller_env_snapshot.env` may be root-owned.** The post-run `chown`
   step must execute before copy-back. The readability assertion (post-run
   step 2b) catches this — if the assertion fails, the CLIs will not run on
   stale defaults. If the assertion is skipped, the breach detector falls
   back to `scaling_config.py` defaults (e.g., compute base threshold 0.45
   vs golden 0.20).
8. **Single workload shape.** The 7-phase workload exercises storage, Tier 1,
   and compute sequentially. Results may not generalize to different workload
   compositions (e.g., simultaneous storage + compute stress).
9. **`time.time()` wall clock for information age.** NTP adjustment during a
   ~24-minute run could add ≤1s error. Negligible for a ~0s measurement.
10. **Cross-workload comparability.** Results from this experiment (golden
    config: 48 clients, WAN 260ms) are not directly comparable to the
    rq1_evaluation_final dataset (8 clients, WAN 10ms). The two datasets
    answer different questions: the lightweight dataset characterizes blind-spot
    effects under low stress; this dataset characterizes them under calibrated
    high stress. The thesis should present both and discuss scaling behavior.

## Artifact Contract

Standard run-folder layout per [`testing_overview.md`](../../testing_overview.md)
plus RQ1 analysis outputs. Each run folder must contain:

| Artifact                        | Required | Notes                                                  |
| ------------------------------- | -------- | ------------------------------------------------------ |
| `client_requests.csv`         | ✅       | Aggregate per-request latency CSV with`phase` column |
| `resource_stats.csv`          | ✅       | Trimmed per-window domain metrics                      |
| `resource_stats_debug.csv`    | ✅       | Broad per-window metrics for deep diagnosis            |
| `policy_state.csv`            | ✅       | Reconstructed per-window policy state                  |
| `per_node_stats.csv`          | ✅       | Per-container per-window metrics                       |
| `container_events.csv`        | ✅       | Docker container lifecycle events                      |
| `elasticity_events.csv`       | ✅       | Parsed controller log events (post-run)                |
| `node_lifecycle_timings.csv`  | ✅       | Per-node timing breakdown (post-run)                   |
| `controller_stats.csv`        | ✅       | Controller CPU/RAM overhead samples                    |
| `controller_env_snapshot.env` | ✅       | Exact thresholds at runtime with provenance comments   |
| `phases_snapshot.json`        | ✅       | Phase configuration used for the run                   |
| `current_phase.txt`           | ✅       | Final phase reached (`idle` on success)              |
| `analysis/`                   | ✅       | RQ1 CLI outputs (PNGs + CSVs)                          |
| `controller_lan*.log`         | ❌       | Deleted after parsing (post-run step 4)                |
| `service_logs/`               | ❌       | Deleted after parsing (post-run step 5)                |

After all 12 runs, comparison outputs at:

- `source/scripts/testing/metrics/rq1_v2_push_comparison/`
- `source/scripts/testing/metrics/rq1_v2_poll5_comparison/`
- `source/scripts/testing/metrics/rq1_v2_poll12_comparison/`
- `source/scripts/testing/metrics/rq1_v2_poll30_comparison/`
- `source/scripts/testing/metrics/rq1_v2_comparison/` (all-modes)

---

## Prerequisites Summary

Before launching the first run, these changes must be made on the cloud VM:

1. **Edit `phases.json`** — replace the 6-phase golden config with the 7-phase
   mixed workload (see §Phases Design).
2. **Edit `current_state_integrated.env`** — add `VIP_HARD_TIMEOUT=60`.
3. **Edit `build_network_setup.sh`** — add `TELEMETRY_SOURCE` and
   `POLL_INTERVAL_S` passthrough to both `osken` and `osken_2` docker run
   commands (see §Telemetry Variable Passthrough below).
4. **Verify code fixes** — all three fixes present in `source/sdn_controller/`.
5. **Rebuild images** if any code has changed since last build:
   ```bash
   ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && make -C source/scripts build_images 2>&1"
   ```

### Telemetry Variable Passthrough (Critical)

`build_network_setup.sh` currently passes `STORAGE_CPUS` and `EDGE_CPUS` to
the OS-Ken containers via `-e` flags, but does **not** forward `TELEMETRY_SOURCE`
or `POLL_INTERVAL_S`. Without this fix, `main_n1.py` silently defaults to
`TELEMETRY_SOURCE=zmq` — all poll-mode runs would actually be push runs with
no indication of failure.

**Add the following two lines** to both the `osken` (after line 475) and
`osken_2` (after line 492) `docker run` commands in `build_network_setup.sh`:

```bash
    -e TELEMETRY_SOURCE="${TELEMETRY_SOURCE:-zmq}" \
    -e POLL_INTERVAL_S="${POLL_INTERVAL_S:-10}" \
```

**Verification**: After `make setup_network`, confirm the variables reach
the container:

```bash
ssh cloud-vm "docker exec osken env | grep -E 'TELEMETRY_SOURCE|POLL_INTERVAL_S'"
# Expected when running a poll mode:
# TELEMETRY_SOURCE=poll
# POLL_INTERVAL_S=5  (or 12, or 30)
```

If the variables are absent, stop — all subsequent runs would be misconfigured.

---

## Lessons from rq1_evaluation_final (Lightweight Workload)

The prior experiment ([`rq1_evaluation_final`](../rq1_evaluation_final/experiment_plan.md))
tested the same four telemetry modes under a lightweight workload
(`CLIENTS=8`, `DEVICES=600`, `WAN_RTT_MS=10`, 10-phase). Key findings that
inform this v2 design:

| Finding                                                                        | How v2 addresses it                                                                                                                                                                                   |
| ------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Push had higher failure rates than Poll** (0.54% vs 0.08–0.13%)       | Golden config's 48-client load tests whether this reverses (hypothesis §3a) or amplifies (§3b).                                                                                                     |
| **Push_3 had 0 reaction latency events**                                 | Hypothesis §2 now acknowledges breach suppression as a valid mechanism effect. Criterion 3 adjusted to treat 0 events as a finding, not a failure.                                                   |
| **Host-state accumulation is real** (Push_1 at 5.04% after 4 prior runs) | Degradation escape hatch added: reboot if any run shows >3× failure vs cleanest sibling.                                                                                                             |
| **Poll-12s NOT consistently worst for service quality**                  | Criterion 5 (service quality) now framed as "expected ordering" without requiring Poll-12s to be the worst. Poll-12s mechanism vs empirical ordering tension explicitly documented in Hypothesis §2. |
| **n=3 attempted but Push_1 excluded → effective n=2**                   | All 12 v2 runs are new (no reuse of prior data). Degradation escape hatch prevents exclusions.                                                                                                        |
| **Reboot-between-mode-pairs protocol was effective**                     | v2 defaults to no-reboot for efficiency, but the escape hatch replicates the reboot protocol if degradation appears.                                                                                  |
| **All mechanisms exercised in all modes**                                | Golden config sizing is proven to exercise all mechanisms. Criterion 4 retained unchanged.                                                                                                            |

---

## Changelog

| Date       | Change                                                                                                                                                                                                                                                            | Rationale                                                                                                                                                              |
| ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2026-06-30 | Initial v2 plan — golden config sizing, 7-phase mixed workload, n=3 per mode, no-reboot protocol                                                                                                                                                                 | Complete redesign from v1. Adopts canonical golden config parameters for thesis-grade service quality measurements.                                                    |
| 2026-06-30 | Adjusted based on rq1_evaluation_final findings — Push 0-events anomaly, host-state escape hatch, service quality hypothesis revision, cross-workload comparability threat                                                                                       | Incorporates lessons from the definitive lightweight-workload RQ1 experiment.                                                                                          |
| 2026-06-30 | Architectural review fixes — TELEMETRY_SOURCE/POLL_INTERVAL_S passthrough prerequisite, demand_drop client_fraction 0.5→0.10, env snapshot readability assertion, Poll-12s blind-spot math correction, campaign duration estimate                               | Critical: without the passthrough fix, all poll-mode runs silently become push runs.                                                                                   |
| 2026-06-30 | Re-review fixes — Poll-12s mechanism vs empirical ordering tension resolved (Hypothesis §2 and Criterion 3 now separate mechanism-based and empirical expectations), demand_drop scale-down math clarified (cooldown gates when, required windows gate whether) | Resolves inconsistency introduced by Poll-12s blind-spot correction: the plan no longer presents the empirical anomaly as if it follows from the blind-spot mechanism. |
| 2026-07-01 | Campaign executed — 12 runs completed (Push×3, Poll-5s×3, Poll-12s×3, Poll-30s×3). All criteria assessed. Results in `results_v2.md`. | Full analysis: blind-spot confirmed in reaction latency (24.6s→68.6s), Poll-12s anomaly absent at golden-config scale, service quality dominated by baseline overload at WAN=260ms. |
