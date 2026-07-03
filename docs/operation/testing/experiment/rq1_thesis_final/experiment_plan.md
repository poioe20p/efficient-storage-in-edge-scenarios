# Experiment Plan — RQ1 Thesis Final

**Status**: ✅ Executed · **Date**: 2026-07-02 – 2026-07-03
**Parent plan**: [`../rq1_evaluation/experiment_plan_v2.md`](../rq1_evaluation/experiment_plan_v2.md) — structural reference
**Predecessors**: [`../rq1_evaluation/experiment_plan_v2_lite.md`](../rq1_evaluation/experiment_plan_v2_lite.md) — WAN=200ms calibration + curl=30s validation

## Intent

Produce the **thesis-quality RQ1 dataset**: 3 replicates per telemetry mode
at golden-config scale with `curl --max-time 30s` to avoid artificial
latency censorship at 10s. The independent variable is telemetry delivery
cadence (Push vs Poll-5s vs Poll-12s vs Poll-30s). All other parameters
held at the v2-lite validated values (WAN=200ms, VIP_HARD_TIMEOUT=60s,
curl=30s). A cloud-VM reboot between runs eliminates host-state confounds.

This is the **definitive RQ1 experiment** — its graphs go in the thesis.

## Hypothesis / Expected Outcome

Same as v2 §Hypothesis, validated at WAN=200ms with uncensored latency:

1. **Reaction latency increases monotonically with polling interval.**
   Push < Poll-5s < Poll-12s < Poll-30s, with the blind-spot contribution
   measurable across all phases.
2. **Information staleness is bounded by the aggregation window**, not the
   polling interval. Push ~0s; Poll modes ~window size.
3. **Service quality degrades with polling interval** above the reduced
   noise floor (~7–12% baseline at WAN=200ms). The blind-spot contribution
   to failure rate should be distinguishable from within-mode variance.
4. **All four elasticity mechanisms exercise** in every run (storage
   scale-out, compute scale-up, Tier 1 selective sync, reserve activation).
5. **curl=30s uncensors the latency distribution** — latency percentiles
   (p95, p99) reflect true cross-region response times, not an artificial
   10s cap. The Poll-30s+curl=30s combination reveals the pathological
   storage_storm saturation regime identified in v2-lite.

## Independent Variable & Held-Constant Set

| Parameter | Value | Notes |
|-----------|-------|-------|
| **Telemetry mode** | Push / Poll-5s / Poll-12s / Poll-30s | **Independent variable** |
| `WAN_RTT_MS` | 200 | Validated in v2-lite; ~7–12% baseline failure |
| `VIP_HARD_TIMEOUT` | 60 | v6 gold standard; 2× headroom above curl=30s |
| `curl --max-time` | 30 | Uncensored latency; CURL_MAX_TIME fix applied |
| `CLIENTS` | 48 | Golden config |
| `DEVICES` | 6000 | Golden config |
| `NODES` | 100 | Golden config |
| `STORAGE_CPUS` | 0.10 | Golden config |
| `SS_ENABLED` | 1 | Selective sync enabled |
| `STORAGE_PERSISTENT_RESERVE_ENABLED` | 1 | Reserve activation |
| Workload | 7-phase mixed | Canonical `source/scripts/testing/phases.json` (see §Phases File below) — 7 phases, request types: content_lookup/feed_ranking/content_update/content_aggregate/service_pressure |
| Reboot between runs | Yes | Eliminate memory accumulation |
| Replicates per mode | 3 | Thesis-quality variance estimation |

## Run Matrix

| # | Label | `TELEMETRY_SOURCE` | `POLL_INTERVAL_S` | `WAN_RTT_MS` | `CURL_MAX_TIME` |
|---|-------|-------------------|--------------------|--------------|-----------------|
| 1 | `rq1_v2final_push_1` | `zmq` (default) | — | 200 | 30 |
| 2 | `rq1_v2final_push_2` | `zmq` (default) | — | 200 | 30 |
| 3 | `rq1_v2final_push_3` | `zmq` (default) | — | 200 | 30 |
| 4 | `rq1_v2final_poll5_1` | `poll` | 5 | 200 | 30 |
| 5 | `rq1_v2final_poll5_2` | `poll` | 5 | 200 | 30 |
| 6 | `rq1_v2final_poll5_3` | `poll` | 5 | 200 | 30 |
| 7 | `rq1_v2final_poll12_1` | `poll` | 12 | 200 | 30 |
| 8 | `rq1_v2final_poll12_2` | `poll` | 12 | 200 | 30 |
| 9 | `rq1_v2final_poll12_3` | `poll` | 12 | 200 | 30 |
| 10 | `rq1_v2final_poll30_1` | `poll` | 30 | 200 | 30 |
| 11 | `rq1_v2final_poll30_2` | `poll` | 30 | 200 | 30 |
| 12 | `rq1_v2final_poll30_3` | `poll` | 30 | 200 | 30 |

**Total: 12 runs.** Run order: Push_1→2→3, Poll-5s_1→2→3, Poll-12s_1→2→3, Poll-30s_1→2→3.
**Campaign duration**: ~5.5 hours (12 × ~28 min each with reboot).

## Prerequisites

All v2-lite prerequisites already applied and verified:

- ✅ `source/scripts/testing/phases.json` — canonical 7-phase file (see §Phases File)
- ✅ `VIP_HARD_TIMEOUT=60` in `current_state_integrated.env`
- ✅ TELEMETRY passthrough in `build_network_setup.sh`
- ✅ `CURL_MAX_TIME` passthrough in `source/scripts/Makefile`
- ✅ `traffic_generator.py` default `--max-time` = 30s
- ✅ `sudo -n` working

**No new prerequisites.** If the cloud VM was rebooted since v2-lite, verify
`sudo -n echo OK` before launching.

### Phases File

**Canonical file**: `source/scripts/testing/phases.json`

This experiment uses a **7-phase mixed workload** (1440 s total):

| # | Phase | Duration | Key characteristic |
|---|-------|----------|--------------------|
| 1 | `baseline` | 60s | Low-rate, local-only, content_lookup heavy |
| 2 | `storage_storm` | 240s | High-rate, 90% cross-region, write-heavy (content_update + content_aggregate) |
| 3 | `tier1_hotspot` | 180s | Max-rate, 95% cross-region, lookup-heavy (triggers Tier 1 selective sync) |
| 4 | `inter_hotspot_cooldown` | 300s | Low-rate, local-only, cooldown/recovery window |
| 5 | `reverse_hotspot` | 180s | Max-rate, 95% cross-region, lookup-heavy (second wave — tests cumulative effect) |
| 6 | `compute_spike` | 180s | High-rate, 5% cross-region, feed_ranking heavy (triggers compute scale-up) |
| 7 | `demand_drop` | 300s | Low-rate, local-only, long scale-down observation window |

**Request types**: `content_lookup`, `feed_ranking`, `content_update`, `content_aggregate`, `service_pressure`.

> **Runner note**: Always verify the canonical file has 7 phases before launching:
> ```bash
> python3 -c "import json; d=json.load(open('source/scripts/testing/phases.json')); print(len(d['phases']), 'phases')"
> ```
> Expected output: `7 phases`.

## Run Configuration

All runs use the same base command with mode-specific `TELEMETRY_SOURCE` and
`POLL_INTERVAL_S`. `CURL_MAX_TIME=30` is passed explicitly (belt-and-suspenders
with the traffic_generator.py default).

### Push (Runs 1–3)

```bash
ssh -o ServerAliveInterval=60 cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_v2final_push_N \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=200 CLIENTS=48 DEVICES=6000 NODES=100 STORAGE_CPUS=0.10 \
  CURL_MAX_TIME=30 \
  > /tmp/rq1_v2final_push_N.log 2>&1 &"
```
Replace `N` with 1, 2, 3.

### Poll-5s (Runs 4–6)

Same as Push, plus `TELEMETRY_SOURCE=poll POLL_INTERVAL_S=5`.
Label: `rq1_v2final_poll5_N`, log: `/tmp/rq1_v2final_poll5_N.log`.

### Poll-12s (Runs 7–9)

Same as Push, plus `TELEMETRY_SOURCE=poll POLL_INTERVAL_S=12`.
Label: `rq1_v2final_poll12_N`, log: `/tmp/rq1_v2final_poll12_N.log`.

### Poll-30s (Runs 10–12)

Same as Push, plus `TELEMETRY_SOURCE=poll POLL_INTERVAL_S=30`.
Label: `rq1_v2final_poll30_N`, log: `/tmp/rq1_v2final_poll30_N.log`.

### Between-Run Reboot Protocol

After each run's post-run analysis:

```bash
ssh cloud-vm "sudo reboot"
Start-Sleep -Seconds 90
ssh -o ConnectTimeout=10 -o ConnectionAttempts=10 cloud-vm "echo 'VM ready'"
```

### Post-Run Workflow (per run)

Same as v2 §Post-Run Workflow:

```bash
RUN_DIR="source/scripts/testing/metrics/<timestamp>_<label>"
sudo chown -R testop:testop "$RUN_DIR"
python3 source/scripts/tools/parse_elasticity_logs.py \
  "$RUN_DIR/controller_lan1.log" "$RUN_DIR/controller_lan2.log" \
  -o "$RUN_DIR/elasticity_events.csv" --timings-output "$RUN_DIR/node_lifecycle_timings.csv"
python3 -m source.scripts.testing.analysis.rq1.cli_rq1_timings         --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.rq1.cli_rq1_overhead        --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.rq1.cli_rq1_decision_quality --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.cli_simple_run              --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.cli_overview                --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.cli_phase_summary           --run-dir "$RUN_DIR"
rm "$RUN_DIR/controller_lan1.log" "$RUN_DIR/controller_lan2.log"
rm -rf "$RUN_DIR/service_logs/"
```

## Focus & Evidence

| Artifact | What it shows | Priority |
|----------|--------------|----------|
| `analysis/rq1_reaction_latency.csv` | Breach-to-spawn latency per mode | **Primary** |
| `analysis/rq1_staleness.csv` | Information age per mode | **Primary** |
| `client_requests.csv` | Per-phase failure rate, latency percentiles (p50/p95/p99), cross-region request outcomes | **Primary** |
| `elasticity_events.csv` | Scaling events, Tier 1 activations | Secondary |
| `resource_stats.csv` | Storage/server count, CPU/RAM per phase | Secondary |
| `phases_snapshot.json` | Phase order, durations, request mix | Reference |
| `controller_env_snapshot.env` | Confirms config held constant | Reference |

## Metrics & Success Criteria

| # | Criterion | Expectation |
|---|-----------|-------------|
| 1 | All 12 runs complete | 12/12 → idle |
| 2 | Information age ~0 | Push ~0.05s; Poll-5s ~5s; Poll-12s/Poll-30s ~10s (window-gated) |
| 3 | Reaction latency monotonic | Push < Poll-5s < Poll-12s < Poll-30s across all replicates |
| 4 | Mechanisms exercise | Storage ≥7, compute ≥4, all 7 phases in all runs |
| 5 | Service quality degrades | Push ≤ Poll-5s ≤ Poll-12s ≤ Poll-30s (failure rate), per-mode μ with error bars |
| 6 | Latency uncensored | p95 ok_latency > 10s for Poll-30s (true tail visible; cf. v2-lite poll30_t30 p95=10.55s) |
| 7 | Within-mode variance estimable | n=3 allows μ ± σ reporting for all metrics |

## Validity Threats

1. **Run order confound** — Push always first. Mitigated by reboot between every run and mode grouping consistent with v2.
2. **Single workload shape** — results bound to the 7-phase mixed workload.
3. **WAN=200ms only** — does not characterise the WAN-latency axis; v2 covers WAN=260ms.
4. **n=3 per mode** — sufficient for μ ± σ reporting; formal confidence intervals would require more replicates.
5. **Reboot between runs** — adds ~2 min per run but eliminates memory-accumulation confound identified in v2.

## Artifact Contract

Run folders at:
- `source/scripts/testing/metrics/<timestamp>_rq1_v2final_push_1/` … `_3/`
- `source/scripts/testing/metrics/<timestamp>_rq1_v2final_poll5_1/` … `_3/`
- `source/scripts/testing/metrics/<timestamp>_rq1_v2final_poll12_1/` … `_3/`
- `source/scripts/testing/metrics/<timestamp>_rq1_v2final_poll30_1/` … `_3/`

Results will be documented in `results_v2final.md` in this folder.

## Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-07-02 | Plan created | Thesis-final RQ1 dataset: n=3, curl=30s, WAN=200ms, reboot between runs |
| 2026-07-03 | Added §Phases File specification; updated request type names (device_status→content_lookup, dashboard→feed_ranking, device_update→content_update, device_aggregate→content_aggregate) | Workload schema renamed request types; canonical file was 6-phase, restored to 7-phase from `phases_override/phases_rq1_7phase.json` |
| 2026-07-03 | Campaign executed — 12/12 runs, 0 tracebacks; `results_v2final.md` written | See `results_v2final.md` for full per-criterion assessment. Key finding: extreme within-mode failure variance (bimodal healthy/degraded regimes) obscures between-mode trend; latency still censored at ~10.5s despite curl=30s |
