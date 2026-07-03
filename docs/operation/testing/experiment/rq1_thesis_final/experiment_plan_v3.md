# Experiment Plan — RQ1 v3 (Measurement-Corrected Re-run)

**Status**: 📋 Planned · **Date**: 2026-07-03
**Parent plan**: [`experiment_plan.md`](experiment_plan.md) — v2final (executed 2026-07-02–03)
**Predecessor results**: [`results_v2final.md`](results_v2final.md) — v2final analysis

## Intent

Re-run the thesis-quality RQ1 dataset with two measurement-integrity fixes
identified during v2final analysis. The independent variable (telemetry mode),
workload, scale, and configuration are **unchanged** from v2final. The fixes
ensure fair mode comparison and correct per-phase metric attribution.

**What changed from v2final**:

| # | Change | Why |
|---|--------|-----|
| 1 | `sent_at` column replaces `timestamp` in `client_requests.csv`; `phase` captured at send-time | Per-phase failure rates reflect requests **initiated** in that phase, not requests that **completed** in it. Eliminates the completion-time bucketing artifact where instant-failures cluster in early buckets and slow successes spill into later ones. |
| 2 | `RANDOM_SEED=42` on all runs | Identical request sequence (types, targets, timing jitter) across all 12 runs. Without this, run A might randomly draw more writes than run B from the same `phases.json` mix — confounding mode comparison with workload variation. |
| 3 | `cleanup.sh -r` before each reboot | Removes all containers **and** MongoDB data volumes between runs. Ensures each run starts from an identical clean state — no residual containers, no stale replica-set data. |
| 4 | Comparison graphs deferred | Produced as a manual step after all 12 runs complete, not mid-campaign from partial data. |

**What did NOT change**: `phases.json` (same 7-phase workload), `current_state_integrated.env` (same overrides), scale (48 clients, 6000 devices, 100 nodes), `CURL_MAX_TIME=30`, `WAN_RTT_MS=200`, `VIP_HARD_TIMEOUT=60`.

## Hypothesis / Expected Outcome

Same as [v2final §Hypothesis](experiment_plan.md). The fixes do not change what
the system does — they ensure we **measure it correctly** and **compare modes
fairly**. Specifically:

1. **Reaction latency increases monotonically with polling interval.**
2. **Information staleness bounded by aggregation window**, not polling interval.
3. **Service quality degrades with polling interval** — distinguishable from within-mode variance.
4. **All four elasticity mechanisms exercise** in every run.
5. **curl=30s uncensors the latency distribution** — same expectation as v2final.

With `RANDOM_SEED=42`, within-mode variance should reflect **system
non-determinism** (container startup order, OVS flow installation timing,
elasticity decision timing), not workload differences. The corrected `sent_at`
bucketing removes the completion-time artifact that inflated early-bucket
failure rates in v2final degraded runs.

## RQ Linkage

Same as v2final. Supports thesis RQ1: *"How does telemetry delivery cadence
affect elasticity reaction latency, information staleness, and service quality
in an edge storage platform?"*

## Independent Variable & Held-Constant Set

| Parameter | Value | Notes |
|-----------|-------|-------|
| **Telemetry mode** | Push / Poll-5s / Poll-12s / Poll-30s | **Independent variable** |
| `RANDOM_SEED` | **42** | **New in v3** — fixed workload sequence |
| `WAN_RTT_MS` | 200 | |
| `VIP_HARD_TIMEOUT` | 60 | |
| `CURL_MAX_TIME` | 30 | |
| `CLIENTS` | 48 | |
| `DEVICES` | 6000 | |
| `NODES` | 100 | |
| `STORAGE_CPUS` | 0.10 | |
| `SS_ENABLED` | 1 | |
| `STORAGE_PERSISTENT_RESERVE_ENABLED` | 1 | |
| Workload | 7-phase mixed | Canonical `source/scripts/testing/phases.json` (unchanged from v2final) |
| Controller env | `current_state_integrated.env` | Unchanged from v2final |
| `cleanup.sh -r` between runs | Yes | **New in v3** — full container + volume reset |
| Reboot between runs | Yes | |
| Replicates per mode | 3 | |

### Phases File

Unchanged from v2final. Canonical: `source/scripts/testing/phases.json` — 7 phases, 1440s total.

> **Runner verification**:
> ```bash
> python3 -c "import json; d=json.load(open('source/scripts/testing/phases.json')); print(len(d['phases']), 'phases')"
> ```
> Expected: `7 phases`.

## Run Matrix

| # | Label | `TELEMETRY_SOURCE` | `POLL_INTERVAL_S` | `RANDOM_SEED` |
|---|-------|-------------------|--------------------|----------------|
| 1 | `rq1_v3_push_1` | `zmq` | — | 42 |
| 2 | `rq1_v3_push_2` | `zmq` | — | 42 |
| 3 | `rq1_v3_push_3` | `zmq` | — | 42 |
| 4 | `rq1_v3_poll5_1` | `poll` | 5 | 42 |
| 5 | `rq1_v3_poll5_2` | `poll` | 5 | 42 |
| 6 | `rq1_v3_poll5_3` | `poll` | 5 | 42 |
| 7 | `rq1_v3_poll12_1` | `poll` | 12 | 42 |
| 8 | `rq1_v3_poll12_2` | `poll` | 12 | 42 |
| 9 | `rq1_v3_poll12_3` | `poll` | 12 | 42 |
| 10 | `rq1_v3_poll30_1` | `poll` | 30 | 42 |
| 11 | `rq1_v3_poll30_2` | `poll` | 30 | 42 |
| 12 | `rq1_v3_poll30_3` | `poll` | 30 | 42 |

**Total: 12 runs.** Run order: Push_1→2→3, Poll-5s_1→2→3, Poll-12s_1→2→3, Poll-30s_1→2→3.
**Campaign duration**: ~6 hours (12 × ~28 min + cleanup/reboot overhead).

## Run Configuration

### Per-Run Protocol

For each of the 12 runs, execute in this order:

```bash
# 1. Launch the experiment
ssh -o ServerAliveInterval=60 cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=<LABEL> \
  PHASES_CONFIG=testing/phases.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  WAN_RTT_MS=200 CLIENTS=48 DEVICES=6000 NODES=100 STORAGE_CPUS=0.10 \
  CURL_MAX_TIME=30 RANDOM_SEED=42 \
  > /tmp/<LABEL>.log 2>&1 &"

# 2. Wait for completion (experiment ~28 min)
#    Monitor: ssh cloud-vm "tail -f /tmp/<LABEL>.log"

# 3. Post-run analysis (see below)

# 4. Cleanup + reboot before next run:
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo bash source/scripts/cleanup.sh -r"
ssh cloud-vm "sudo reboot"
# Wait ~90s for VM to come back:
Start-Sleep -Seconds 90
ssh -o ConnectTimeout=10 -o ConnectionAttempts=10 cloud-vm "echo 'VM ready'"
```

### Mode-Specific Flags

| Mode | Extra `make` flags |
|------|--------------------|
| Push | *(none — zmq is default)* |
| Poll-5s | `TELEMETRY_SOURCE=poll POLL_INTERVAL_S=5` |
| Poll-12s | `TELEMETRY_SOURCE=poll POLL_INTERVAL_S=12` |
| Poll-30s | `TELEMETRY_SOURCE=poll POLL_INTERVAL_S=30` |

### Post-Run Workflow (per run)

```bash
RUN_DIR="source/scripts/testing/metrics/<timestamp>_<label>"

# Fix ownership
sudo chown -R testop:testop "$RUN_DIR"

# Parse controller logs → elasticity events
python3 source/scripts/tools/parse_elasticity_logs.py \
  "$RUN_DIR/controller_lan1.log" "$RUN_DIR/controller_lan2.log" \
  -o "$RUN_DIR/elasticity_events.csv" \
  --timings-output "$RUN_DIR/node_lifecycle_timings.csv"

# RQ1 analysis CLIs (produce CSVs for comparison graphs)
python3 -m source.scripts.testing.analysis.rq1.cli_rq1_timings         --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.rq1.cli_rq1_overhead        --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.rq1.cli_rq1_decision_quality --run-dir "$RUN_DIR"

# Per-run graphs are NOT generated — only comparison graphs after all runs complete

# Cleanup large artifacts
rm "$RUN_DIR/controller_lan1.log" "$RUN_DIR/controller_lan2.log"
rm -rf "$RUN_DIR/service_logs/"
```

### CSV Schema Change (v3)

The `client_requests.csv` header is now:

```
sent_at, phase, client_ns, client_lan, endpoint, content_id, user_id,
target_region, http_status, latency_s, completed_at
```

- **`sent_at`**: ISO 8601 timestamp captured **before** `curl` execution — request send-time.
- **`phase`**: Phase name at send-time (was completion-time in v2final).
- **`completed_at`**: ISO 8601 timestamp captured **after** `curl` returns — for latency validation.

Analysis tools use the `phase` column for per-phase bucketing (via `loader.py`).
The `simple_metrics.py` `infer_origin_ts` / `infer_end_ts` functions use `sent_at`.
No other tool changes were needed.

## Focus & Evidence

| Artifact | What it shows | Priority |
|----------|--------------|----------|
| `analysis/rq1_reaction_latency.csv` | Breach-to-spawn latency per mode | **Primary** |
| `analysis/rq1_staleness.csv` | Information age per mode | **Primary** |
| `client_requests.csv` | Per-phase failure rate (send-time bucketed), latency percentiles | **Primary** |
| `elasticity_events.csv` | Scaling events, Tier 1 activations | Secondary |
| `resource_stats.csv` | Storage/server count, CPU/RAM per phase | Secondary |
| `phases_snapshot.json` | Phase order, durations, request mix | Reference |
| `controller_env_snapshot.env` | Confirms config held constant | Reference |

**Primary focus**: `client_requests.csv` (send-time bucketed) + RQ1 reaction latency/staleness CSVs.
The key improvement over v2final is that per-phase failure rates now correctly attribute
each request to the phase it was **sent** in.

## Metrics & Success Criteria

Same criteria as [v2final §Metrics](experiment_plan.md), restated for v3:

| # | Criterion | Expectation |
|---|-----------|-------------|
| C1 | All 12 runs complete | 12/12 → idle, zero controller tracebacks |
| C2 | Information age step-function | Push ~0s; Poll-5s ~5s; Poll-12s/Poll-30s ~10s (window-gated) |
| C3 | Reaction latency monotonic | Push < Poll-5s < Poll-12s < Poll-30s (per-mode μ, n=3) |
| C4 | Mechanisms exercise | All four mechanisms in all runs (storage scale-out, compute scale-up, Tier 1 selective sync, reserve activation) |
| C5 | Service quality degrades with polling interval | Push ≤ Poll-5s ≤ Poll-12s ≤ Poll-30s (failure rate), with n=3 error bars |
| C6 | Latency uncensored | p95 ok_latency reflects true cross-region response times, not artificial cap |
| C7 | Within-mode variance estimable | n=3 allows μ ± σ for all metrics; `RANDOM_SEED=42` isolates system variance from workload variance |

## Post-Completion: Comparison Graphs (Manual Step)

After all 12 runs have completed post-run analysis, the **analysis agent** should run:

```bash
python3 -m source.scripts.testing.analysis.rq1.scripts.generate_comparison_graphs \
  --run-dirs <all 12 run dirs> \
  --output docs/operation/testing/experiment/rq1_thesis_final/graphs/comparison/
```

This produces the cross-mode bar charts (failure rate by mode, reaction latency
by mode, staleness by mode, per-phase timeout rate, controller CPU/RAM). It
must run only after ALL 12 runs are present — not incrementally.

No per-run individual graphs are produced or copied — only the comparison
graphs are needed for the thesis.

## Graph Organization

Only comparison graphs are produced. No per-run individual images.

```
docs/operation/testing/experiment/rq1_thesis_final/graphs/
└── comparison/
    ├── failure_rate_by_mode.png
    ├── reaction_latency_by_mode.png
    ├── staleness_by_mode.png
    ├── per_phase_timeout_rate.png
    └── controller_overhead_by_mode.png
```

## Artifact Contract

Standard run-folder layout per [`testing_overview.md`](../../testing_overview.md) plus:

| File | Notes |
|------|-------|
| `client_requests.csv` | **v3 schema**: `sent_at`, `phase` (send-time), …, `completed_at` |
| `controller_env_snapshot.env` | Base + override provenance comments |
| `phases_snapshot.json` | Copy of canonical `phases.json` |
| `elasticity_events.csv` | Parsed from controller logs |
| `node_lifecycle_timings.csv` | Container spawn/stop timings |
| `analysis/rq1/` | RQ1 CLI outputs (timings, overhead, decision_quality) — feed comparison graphs |
| `analysis/rq1/rq1_decision_quality.csv` | Per-phase breach/spawn summary |
| `analysis/rq1/rq1_overhead.csv` | Controller CPU/RAM per window |
| `analysis/rq1/rq1_reaction_latency.csv` | Breach-to-spawn latency |
| `analysis/rq1/rq1_staleness.csv` | Information age |

## Validity Threats & Limitations

| Threat | Mitigation |
|--------|-----------|
| Bimodal variance (v2final: 5/12 runs degraded) | `cleanup.sh -r` ensures identical clean state; `RANDOM_SEED=42` removes workload variation. If bimodality persists, it is genuine system non-determinism. |
| Completion-time bucketing artifact (v2final) | `sent_at` fix — per-phase metrics now correctly attributed to send-time. |
| Workload differences between modes (v2final) | `RANDOM_SEED=42` — identical request sequence across all 12 runs. |
| Residual container state between runs (v2final) | `cleanup.sh -r` removes all containers + volumes before reboot. |
| `cleanup.sh -r` removes seeded data | `setup_test_data` re-seeds fresh each run. No net effect. |

## Changelog

| Date | Change |
|------|--------|
| 2026-07-03 | Plan created. Changes from v2final: `sent_at` column, `RANDOM_SEED=42`, `cleanup.sh -r` between runs, per-run graphs removed (only comparison graphs produced), comparison graphs deferred to post-completion manual step. |
