# Experiment Plan — RQ1 Tooling & Instrumentation Verification

**Status**: 🔵 Designed · **Date**: 2026-06-14
**Parent**: `docs/operation/testing/implementation/rq1_telemetry_freshness/rq1_analysis_tooling_plan.md`
**Current version**: v4 — tooling verification focus (post-implementation)

## Intent

The RQ1 analysis tooling has been fully implemented (all three CLIs,
`breach_detector.py`, `sample_controller_stats.py`, loader integration).
Before any RQ1 evaluation runs begin, we must verify that the **analysis
tooling works correctly** on real run data.

This experiment answers two questions:
1. **Tooling correctness**: Do all three RQ1 CLIs run without errors, produce
   well-formed output, and yield internally consistent results across CLIs?
2. **Instrumentation health**: Are the input artifacts the CLIs depend on
   (`consumed_at` in `resource_stats_debug.csv`, `controller_stats.csv`,
   `controller_env_snapshot.env`) being generated correctly?

This is a **pre-flight gate**, not an RQ1 evaluation. The RQ1 evaluation runs
must not start until this experiment passes.

## Hypothesis / Expected Outcome

### A. Instrumentation expectations (unchanged from v3)

1. **`consumed_at` is present and populated** in `resource_stats_debug.csv`.
2. **Staleness is cadence-appropriate** — differentiated across push/poll12/poll5/poll30.
3. **`controller_stats.csv` is generated** with all 6 columns for both controllers.
4. **Scaling events fire in both directions** in Runs A, B, C.
5. **`controller_env_snapshot.env` is captured** in the run folder.

### B. Tooling expectations (v4 focus)

6. **All three RQ1 CLIs complete without Python tracebacks** on every run.
7. **CLI outputs are non-empty and well-formed:**
   - `cli_rq1_timings` → 5 files: `rq1_staleness.{csv,png}`,
     `rq1_staleness_per_phase.csv`, `rq1_reaction_latency.{csv,png}`
   - `cli_rq1_overhead` → 3 files: `rq1_overhead_cpu.png`, `rq1_overhead_ram.png`, `rq1_overhead.csv`
   - `cli_rq1_decision_quality` → 2 files: `rq1_decision_quality.{csv,png}` (per-phase descriptive table)
8. **Breach detection is internally consistent across CLIs:**
   - `cli_rq1_timings` and `cli_rq1_decision_quality` detect the **same number
     of breaches** for the same run (they share `breach_detector.py`).
   - Every breach's `score` and `threshold` in the CSV output match what
     `breach_detector.detect_breaches()` computes.
9. **Reaction latency timeline is physically possible:**
   - `breach_window_end < spawn_start_ts < spawn_done.ts` for every event.
   - `breach_detection_s ≥ 0`, `provision_time_s ≥ 0`,
     `total_reaction_s ≈ breach_detection_s + provision_time_s` (± 0.001 s).
10. **Decision quality output is a descriptive per-phase table** with columns:
    `phase`, `phase_load`, `total_windows`, `breached_windows`,
    `peak_score`, `spawns_initiated`, `spawns_completed`. No classification
    labels — the gap between breached-windows and completed-spawns is the
    observable fact.
11. **`cli_rq1_overhead` handles `controller_stats.csv` correctly:**
    - Both `osken` and `osken_2` appear in the CPU and RAM time-series graphs.
    - Mean CPU% and RSS values are physically plausible (0–100% CPU, > 0 MB RSS).
12. **Edge cases handled gracefully:**
    - Run D (poll-30s) may have fewer/no breaches — CLIs must not crash,
      must produce empty CSVs or note "no events" in output.
    - If `controller_stats.csv` is missing, `cli_rq1_overhead` exits cleanly
      with a message, no traceback.
    - If `controller_env_snapshot.env` is missing, `load_thresholds()` falls
      back to defaults — breach detection may return 0 events (acceptable,
      but must not crash).
13. **Existing CLIs still work** (`cli_simple_run`, `cli_overview`,
    `cli_phase_summary`).

## RQ Linkage

RQ1 (Information Acquisition pillar) — validates the measurement pipeline
that will be used to answer: *How does telemetry aggregation window size and
delivery cadence affect controller decision staleness?*

## Two-Tier Execution Strategy

The experiment is split into two tiers to minimize wasted runs:

| Tier | Runs | Duration | Purpose | Gate |
|---|---|---|---|---|
| **Tier 1 — Tooling Smoke Test** | Run A only (push) | ~10 min | Verify all CLIs run and produce correct output. Catches tooling bugs fast. | Must pass before Tier 2. |
| **Tier 2 — Full Verification** | Runs A, B, C, D | ~40 min | Verify instrumentation across all polling cadences + full CLI exercise. | Must pass before any RQ1 evaluation run. |

**Tier 1** uses the single push run because: (a) push mode has the simplest
staleness profile (sub-second), making expected values easy to validate;
(b) push mode generates scaling events (both directions) with the verification
env; (c) all CLIs can be tested against one run folder — tooling bugs are not
cadence-dependent.

**Tier 2** adds the three poll modes to verify: (a) staleness differentiation
across cadences (the v2 collector fix), (b) CLI behavior on runs with different
breach counts and staleness profiles, (c) edge cases like poll-30s where
breaches may be scarce.

## Independent Variable & Held-Constant Set

- **Independent variable**: `TELEMETRY_SOURCE` / `POLL_INTERVAL_S`
- **Held constant**: workload, window size, infrastructure

| Parameter | Value | Notes |
|---|---|---|
| Phase file | `phases_rq1_verify.json` | 6 phases, 480 s. Triggers compute scale-up (`compute_spike`) and scale-down (`demand_drop`). |
| `WINDOW_S` | 10 | Default aggregation window |
| `CLIENTS` | 8 | Standard |
| `DEVICES` | 600 | Standard |
| `NODES` | 100 | Standard |
| Controller env | `rq1_verify.env` | Golden config but `SCALEDOWN_COMPUTE_COOLDOWN_S=60` (vs 180) so scale-down fires within the run window |

## Run Matrix

| Run | `TELEMETRY_SOURCE` | `POLL_INTERVAL_S` | Staleness | Tier | Purpose |
|---|---|---|---|---|---|
| **A** (push) | `zmq` | — | Sub-second | 1 & 2 | Baseline: ZMQ push. Primary tooling verification target. |
| **B** (poll-12s) | `poll` | `12` | 0–12 s | 2 | Window + 2 s headroom; desync-safe. |
| **C** (poll-5s) | `poll` | `5` | 0–10 s | 2 | Faster than window; heavy dedup exercise. |
| **D** (poll-30s) | `poll` | `30` | 20–30 s | 2 | Stale-data stress test. Edge case: may have fewer breaches. |

> **Desync rationale:** The aggregator and controller are independent
> processes. At exactly 10 s polling, a poll could land just before the
> window boundary and the controller would read the old summary, then wait
> another full interval. Run B avoids this by polling at 12 s (window +
> headroom). Run C avoids it by polling fast enough (5 s) that every window
> is caught regardless of drift. Run D quantifies the additional cost of
> slow polling.

## Run Configuration

### Run A — Push baseline

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_verify_push \
  PHASES_CONFIG=testing/phases_override/phases_rq1_verify.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq1_verify.env \
  CLIENTS=8 DEVICES=600 NODES=100 \
  2>&1"
```

`TELEMETRY_SOURCE` defaults to `zmq`.

### Run B — Poll at 12 s (fair comparison, desync-safe)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_verify_poll12 \
  PHASES_CONFIG=testing/phases_override/phases_rq1_verify.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq1_verify.env \
  CLIENTS=8 DEVICES=600 NODES=100 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=12 \
  2>&1"
```

`POLL_INTERVAL_S=12` = `WINDOW_S=10` + 2 s headroom. The controller polls
slightly slower than the window cadence to ensure a new summary has been
published before each poll. Clock drift between the aggregator and controller
cannot cause systematic boundary misses.

### Run C — Poll at 5 s (faster than window, RQ1 extended set)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_verify_poll5 \
  PHASES_CONFIG=testing/phases_override/phases_rq1_verify.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq1_verify.env \
  CLIENTS=8 DEVICES=600 NODES=100 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=5 \
  2>&1"
```

`POLL_INTERVAL_S=5` < `WINDOW_S=10` — catches every window regardless of
clock drift. Approximately every other poll is a duplicate; dedup filters
them. Heavy dedup exercise (expect ~50 duplicate-skip events per ~120 s,
consistent with the polling verification smoke test). Maps to the RQ1
extended set condition W10-Poll-5s.

### Run D — Poll at 30 s (stale-data stress)

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=rq1_verify_poll30 \
  PHASES_CONFIG=testing/phases_override/phases_rq1_verify.json \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/rq1_verify.env \
  CLIENTS=8 DEVICES=600 NODES=100 \
  TELEMETRY_SOURCE=poll POLL_INTERVAL_S=30 \
  2>&1"
```

With `POLL_INTERVAL_S=30` and `WINDOW_S=10`, the controller is always
1–2 windows behind. Scaling decisions may be delayed. This is the
W10-Poll-30s evaluation condition — this run previews it with full
instrumentation.

## Focus & Evidence

### Tier 1 — Tooling Smoke Test (Run A only)

**Primary — CLI execution & output correctness:**

| Check | How to verify |
|---|---|
| All 3 RQ1 CLIs run without tracebacks | Run each CLI via `python -m`; check exit code = 0 |
| All expected output files exist | `ls analysis/rq1/` — expect up to 10 files: 5 from timings, 3 from overhead (cpu.png, ram.png, csv), 2 from decision_quality. Reaction latency files absent when 0 spawn-matched breaches. |
| CSV files are non-empty | `wc -l analysis/rq1/*.csv` — header + ≥ 1 data row |
| Breach count consistent between CLIs | Both share `breach_detector.py`. `rq1_decision_quality.csv` is per-phase (N rows = N phases); `rq1_reaction_latency.csv` is per-breach. Counts differ by design. Verify both CLIs use same `detect_breaches()` output. |
| Decision quality CSV has descriptive columns | `head -1 analysis/rq1/rq1_decision_quality.csv` — columns: `phase,phase_load,total_windows,breached_windows,peak_score,spawns_initiated,spawns_completed` |
| Controller overhead produces CPU + RAM graphs | `cli_rq1_overhead` writes `rq1_overhead_cpu.png`, `rq1_overhead_ram.png`, and `rq1_overhead.csv` with both controllers |
| Existing CLIs still work | `cli_simple_run`, `cli_overview`, `cli_phase_summary` all exit 0 |

**Secondary — quick sanity on values:**

| Check | How to verify |
|---|---|
| Push staleness is sub-second | `csvcut -c staleness_s analysis/rq1/staleness.csv \| tail -n +2 \| sort -n` — p95 < 2 s |
| Breach scores are in [0, 1] range | Check `score` column in `rq1_reaction_latency.csv` — all values in [0, 1] |
| Reaction latency segments are ≥ 0 | `breach_detection_s`, `provision_time_s`, `total_reaction_s` all ≥ 0 |
| Controller CPU% is 0–100 | Spot-check `rq1_overhead.csv` — mean_cpu in [0, 100], visually verify time-series graphs |

### Tier 2 — Full Verification (Runs A–D)

Same checks as Tier 1 applied to all four runs, plus:

| Check | How to verify |
|---|---|
| Staleness differentiates across modes | Compare `mean_s` from `rq1_staleness_per_phase.csv` across A/B/C/D |
| Poll-12s mean staleness 0–12 s | Run B: `mean_s` between 0–12 s |
| Poll-5s mean staleness 0–10 s | Run C: `mean_s` between 0–10 s |
| Poll-30s mean staleness 15–35 s | Run D: `mean_s` between 15–35 s |
| `controller_env_snapshot.env` captured in all runs | File present, contains `SCALEUP_CPU_FLOOR=3` |
| CLI handles sparse-breach runs (D) | `cli_rq1_timings` and `cli_rq1_decision_quality` exit 0 even if 0 breaches |

### Primary — timing artifact (`resource_stats_debug.csv`)

| Check | How to verify |
|---|---|
| `consumed_at` column exists | `head -1 resource_stats_debug.csv` — column present |
| All rows have `consumed_at` | `csvcut -c consumed_at resource_stats_debug.csv \| grep -c '^$'` — zero empty |
| Staleness computable | `consumed_at - window_end` per row. Both fields use `time.time()` on same host — directly comparable. |

**Per-run staleness expectations:**

| Run | Mean staleness | Why |
|---|---|---|
| A (push) | < 1 s | ZMQ delivery on same Docker host |
| B (poll-12s) | 0–12 s, mean ~6 s | Window + 2 s headroom; always polls after window close |
| C (poll-5s) | 0–10 s, mean ~5 s | Faster than window; dedup filters ~50% of polls |
| D (poll-30s) | 15–35 s | Controller is 1–2 windows behind |

### Primary — overhead artifact (`controller_stats.csv`)

| Check | How to verify |
|---|---|
| File exists | `test -s controller_stats.csv` |
| All 6 columns present | `head -1 controller_stats.csv` — `timestamp_iso,timestamp,phase,container,cpu_percent,mem_usage_mb` |
| Both controllers sampled | `csvcut -c container controller_stats.csv \| sort \| uniq` — `osken` and `osken_2` |
| Sampling cadence ~5 s | Timestamp deltas between consecutive rows ≈ 5 s |
| `phase` column non-empty | `csvcut -c phase controller_stats.csv \| grep -c '^$'` < 10% of rows |

### Secondary — scaling events (both directions)

| Artifact | What to check |
|---|---|
| `container_events.csv` | `spawn_start` / `spawn_done` in `compute_spike`; `stop` / `destroy` in `demand_drop` |
| `elasticity_events.csv` | `compute_scale_up` and `compute_scale_down` events |
| Controller logs | `[scale-up] compute` during `compute_spike`; `[scale-down] compute` during `demand_drop` |

Verification env uses `SCALEDOWN_COMPUTE_COOLDOWN_S=60` so scale-down
fires within the 120 s `demand_drop` phase in push and poll-10s modes.
In poll-30s mode, stale data may delay detection — scale-down may fire
late or not at all. That is a staleness observation, not a failure.

## Tier 1 — Tooling Smoke Test Procedure

Run these commands on Run A's folder **before** launching Tier 2:

```bash
RUN_DIR=<path/to/run_A_folder>

# 1. Run all three RQ1 CLIs
python3 -m source.scripts.testing.analysis.rq1.cli_rq1_timings --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.rq1.cli_rq1_overhead --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.rq1.cli_rq1_decision_quality --run-dir "$RUN_DIR"

# 2. Verify all expected output files exist
ls "$RUN_DIR/analysis/rq1/"*.csv "$RUN_DIR/analysis/rq1/"*.png
# Expected: rq1_staleness.csv, rq1_staleness.png, rq1_staleness_per_phase.csv,
#           rq1_reaction_latency.csv (absent if 0 events), rq1_reaction_latency.png,
#           rq1_overhead_cpu.png, rq1_overhead_ram.png, rq1_overhead.csv,
#           rq1_decision_quality.csv, rq1_decision_quality.png

# 3. Verify decision_quality CSV has expected descriptive columns
head -1 "$RUN_DIR/analysis/rq1/rq1_decision_quality.csv"
# Expected: phase,phase_load,total_windows,breached_windows,peak_score,spawns_initiated,spawns_completed

# 4. Verify per-phase summary content
python3 -c "
import csv
with open('$RUN_DIR/analysis/rq1/rq1_decision_quality.csv') as f:
    for row in csv.DictReader(f):
        tw = int(row['total_windows'])
        bw = int(row['breached_windows'])
        sp = int(row['spawns_completed'])
        flag = ' <-- breached' if bw > 0 else ''
        print(f\"{row['phase']:<25s} windows={tw:>2d}  breached={bw:>2d}  spawns_done={sp:>2d}{flag}\")
"

# 5. Verify reaction latency timeline consistency
python3 -c "
import csv
with open('$RUN_DIR/analysis/rq1/rq1_reaction_latency.csv') as f:
    for row in csv.DictReader(f):
        det = float(row['breach_detection_s'])
        prov = float(row['provision_time_s'])
        total = float(row['total_reaction_s'])
        assert det >= 0, f'negative detection: {det}'
        assert prov >= 0, f'negative provision: {prov}'
        assert abs(total - (det + prov)) < 0.01, \
            f'total {total} != det+prov {det+prov}'
print('All reaction latency rows consistent')
"

# 6. Verify push staleness is sub-second
python3 -c "
import csv
with open('$RUN_DIR/analysis/rq1/rq1_staleness.csv') as f:
    vals = [float(r['staleness_s']) for r in csv.DictReader(f)]
p95 = sorted(vals)[int(len(vals)*0.95)]
print(f'Staleness: mean={sum(vals)/len(vals):.4f}s, p95={p95:.4f}s')
assert p95 < 2.0, f'Push staleness p95={p95}s exceeds 2s threshold'
print('Push staleness OK')
"

# 7. Verify existing CLIs
python3 -m source.scripts.testing.analysis.cli_simple_run --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.cli_overview --run-dir "$RUN_DIR"
python3 -m source.scripts.testing.analysis.cli_phase_summary --run-dir "$RUN_DIR"
```

If all 7 checks pass, Tier 2 is cleared to proceed. If any check fails,
**stop** — fix the tooling before running more experiments.

## Tier 2 — Full CLI Verification

Run all three RQ1 CLIs against each of the four run folders (A, B, C, D):

```bash
for label in rq1_verify_push rq1_verify_poll12 rq1_verify_poll5 rq1_verify_poll30; do
    RUN_DIR="<path/to/$label>"
    echo "=== $label ==="
    python3 -m source.scripts.testing.analysis.rq1.cli_rq1_timings --run-dir "$RUN_DIR"
    python3 -m source.scripts.testing.analysis.rq1.cli_rq1_overhead --run-dir "$RUN_DIR"
    python3 -m source.scripts.testing.analysis.rq1.cli_rq1_decision_quality --run-dir "$RUN_DIR"
done
```

Then run the Tier 1 checks (3–7) against each run folder and additionally:

```bash
# 8. Verify staleness differentiates across modes
for label in rq1_verify_push rq1_verify_poll12 rq1_verify_poll5 rq1_verify_poll30; do
    echo -n "$label: "
    python3 -c "
import csv
with open('<path/to/$label>/analysis/rq1/rq1_staleness.csv') as f:
    vals = [float(r['staleness_s']) for r in csv.DictReader(f)]
print(f'mean={sum(vals)/len(vals):.4f}s  p95={sorted(vals)[int(len(vals)*0.95)]:.4f}s')
"
done
# Expected: push < poll5 ≈ poll12 < poll30 (strictly increasing mean)

# 9. Verify controller_env_snapshot.env exists in each run folder
for label in rq1_verify_push rq1_verify_poll12 rq1_verify_poll5 rq1_verify_poll30; do
    grep -l "SCALEUP_CPU_FLOOR=3" "<path/to/$label>/controller_env_snapshot.env" || \
        echo "MISSING: $label"
done
```

## Metrics & Success Criteria

### Gate A — Tier 1 Tooling Smoke Test (Run A only)

Must pass before Tier 2. **Blocking**: any failure stops the campaign.

| # | Criterion | Pass threshold |
|---|---|---|
| T1 | All 3 RQ1 CLIs exit 0 | No Python tracebacks |
| T2 | Output files exist under `analysis/rq1/` | Up to 10 files: 5 timings + 3 overhead + 2 decision_quality. Reaction latency absent when 0 spawn-matched breaches. |
| T3 | Breach detection consistent between CLIs | Both CLIs share `breach_detector.py` → same underlying breach count. Output formats differ (per-phase summary vs per-breach latency). |
| T4 | Classification labels use v4 set only | N/A — labels removed. Per-phase table has no classification column. |
| T5 | No legacy labels in classification | N/A — labels removed. Verify CSV has `phase`, `phase_load`, `total_windows`, `breached_windows`, `peak_score`, `spawns_initiated`, `spawns_completed` columns. |
| T6 | Reaction latency segments sum correctly | `total_reaction_s ≈ breach_detection_s + provision_time_s` (± 0.01 s) for all rows |
| T7 | `breach_detection_s ≥ 0`, `provision_time_s ≥ 0` | No negative values |
| T8 | Push staleness p95 < 2 s | `p95_s` in `rq1_staleness_per_phase.csv` < 2.0 |
| T9 | Breach scores in [0, 1] | `score` column in `rq1_reaction_latency.csv` — all values ∈ [0, 1] |
| T10 | `cli_rq1_overhead` reads both controllers | Per-phase CSV has rows for both `osken` and `osken_2` |
| T11 | Controller CPU% physically plausible | `mean_cpu` in [0, 100] in `rq1_overhead.csv` |
| T12 | Existing CLIs all exit 0 | `cli_simple_run`, `cli_overview`, `cli_phase_summary` no tracebacks |

### Gate B — Tier 2 Full Verification (Runs A–D)

Must pass before any RQ1 evaluation run.

**Instrumentation criteria:**

| # | Criterion | Pass threshold |
|---|---|---|
| I1 | All 4 runs complete all 6 phases | All 6 phases present in `client_requests.csv` for each run |
| I2 | `consumed_at` present and non-empty | ≥ 90% of `resource_stats_debug.csv` rows populated |
| I3 | Push staleness sub-second (Run A) | Mean < 1.0 s, p95 < 2.0 s |
| I4 | Poll-12s staleness 0–12 s (Run B) | Mean between 0–12 s |
| I5 | Poll-5s staleness 0–10 s (Run C) | Mean between 0–10 s |
| I6 | Poll-30s staleness 15–35 s (Run D) | Mean between 15–35 s |
| I7 | `controller_stats.csv` all 6 columns | `timestamp_iso`, `timestamp`, `phase`, `container`, `cpu_percent`, `mem_usage_mb` present. `phase` column non-empty in ≥ 50% of rows. |
| I8 | Compute scale-up fires (Runs A, B, C) | ≥ 1 `spawn_start` during `compute_spike` |
| I9 | Compute scale-down fires (Runs A, B, C) | ≥ 1 `stop` during `demand_drop` |
| I10 | `controller_env_snapshot.env` captured | File exists in all 4 run folders, contains `SCALEUP_CPU_FLOOR=3` |

**Tooling criteria (applied to all 4 runs):**

| # | Criterion | Pass threshold |
|---|---|---|
| T13 | All 3 RQ1 CLIs exit 0 on all 4 runs | No Python tracebacks on any run |
| T14 | Output files exist for all 4 runs | Up to 10 files under each `analysis/rq1/` (reaction latency absent when 0 spawn-matched breaches) |
| T15 | Breach detection consistent on all runs | Both CLIs share `breach_detector.py`. Output row counts differ (per-phase vs per-breach) — verify underlying breach count identical. |
| T16 | Classification labels are v4-only on all runs | N/A — labels removed. Per-phase table format verified across all runs. |
| T17 | Reaction latency consistent on all runs | All rows: `breach_detection_s ≥ 0`, `provision_time_s ≥ 0`, segments sum correctly |
| T18 | `cli_rq1_overhead` produces per-phase table for all runs | Non-empty CSV with `osken` and `osken_2` rows |
| T19 | Edge case: CLIs handle Run D gracefully | If Run D has 0 breaches, CLIs exit 0 with "no events" message, not traceback |
| T20 | Existing CLIs work on all runs | `cli_simple_run`, `cli_overview`, `cli_phase_summary` exit 0 |

### Consistency cross-checks

| # | Criterion | Pass threshold |
|---|---|---|
| C1 | Breach count matches between `cli_rq1_timings` and `cli_rq1_decision_quality` | Same number of breach events in both CLIs' outputs for the same run |
| C2 | Breach scores match manual computation | `degradation_score()` on a sample debug row matches the `score` column in `rq1_reaction_latency.csv` |
| C3 | Staleness strictly increases with polling interval | Mean staleness: push < poll5 ≈ poll12 < poll30 |

## Validity Threats & Limitations

- **`time.time()` wall clock** — both `window_end` and `consumed_at` use
  `time.time()`. NTP adjustment during a 10-minute run could add ≤ 1 s
  error. Acceptable for verification. RQ1 evaluation should consider
  `time.monotonic()` for precision.
- **Single run per condition** — sufficient for tooling/instrumentation
  verification. RQ1 evaluation will need multiple runs per condition for
  statistical power.
- **Desync between aggregator and controller clocks** — poll-12s (Run B)
  and poll-5s (Run C) represent two strategies for handling clock drift
  between independent processes. Run B adds headroom; Run C polls fast
  enough to catch every window.
- **Scale-down in poll-30s** — with 30 s polling staleness, the controller
  may not detect the demand drop soon enough to trigger scale-down within
  the 120 s phase. If Run D has no scale-down events, that is a staleness
  observation (not a failure). `cli_rq1_decision_quality` handles empty
  input gracefully.
- **Controller env divergence** — `rq1_verify.env` differs from the golden
  config only in `SCALEDOWN_COMPUTE_COOLDOWN_S=60` (vs 180). This is
  acceptable for verification; the golden config is restored for RQ1
  evaluation.
- **`controller_env_snapshot.env` prerequisite** — breach detection
  requires the env snapshot to use the same thresholds the controller used.
  If the snapshot is missing (root-owned on cloud VM, not copied back),
  `load_thresholds()` falls back to `scaling_config.py` defaults
  (`CPU_FLOOR=5.0`) which are too conservative for this workload —
  criteria T13–T16 will produce 0 breach events. The runner must verify
  this file exists before running analysis.
- **Not replicating the sliding window** — `breach_detector.py` uses
  the first individual window where `score ≥ threshold`, not the
  controller's sliding-window mechanism. The CLI's breach count may differ
  from the controller's alert count. This is by design — the CLI measures
  "when was overload visible in telemetry," not "when did the controller
  decide to act."


## Artifact Contract

Standard run-folder layout per `testing_overview.md` plus:

| Artifact | Source | Expected |
|---|---|---|
| `resource_stats_debug.csv` | Collector | `consumed_at` column populated |
| `controller_stats.csv` | Phase 5 sampler | 6 columns, both `osken` and `osken_2`, ~5 s cadence |
| `controller_env_snapshot.env` | `run_experiment.sh` | Must record `rq1_verify.env` provenance |
| `container_events.csv` | Collector | Scale-up + scale-down events (Runs A, B, C) |
| `elasticity_events.csv` | Log parser | Alert lifecycle |
| `client_requests.csv` | Traffic generator | All 6 phases |
| `analysis/rq1/rq1_staleness.{csv,png}` | `cli_rq1_timings` | Staleness time-series + per-phase table |
| `analysis/rq1/rq1_staleness_per_phase.csv` | `cli_rq1_timings` | Per-phase aggregate staleness |
| `analysis/rq1/rq1_reaction_latency.{csv,png}` | `cli_rq1_timings` | Reaction latency breakdown |
| `analysis/rq1/rq1_overhead.{csv,png}` | `cli_rq1_overhead` | Controller CPU/RAM over time |
| `analysis/rq1/rq1_decision_quality.{csv,png}` | `cli_rq1_decision_quality` | Per-phase descriptive table (windows, breached, peak score, spawns) |

## Changelog

| Date | Change | Rationale |
|---|---|---|
| 2026-06-14 | **v4.1**: Synced plan to tooling changes. Overhead split into `rq1_overhead_cpu.png` + `rq1_overhead_ram.png`. Decision quality replaced 2x2 labels with per-phase descriptive table (windows, breached, peak score, spawns). Removed stale `_plot_confusion_matrix` validity threat. | Post-analysis tooling improvements from Tier 1+2 findings. |
| 2026-06-14 | **v4**: Refocused experiment on tooling verification (post-implementation). Added two-tier execution strategy (Tier 1 smoke test on Run A → gate → Tier 2 full verification). Reorganized criteria into instrumentation (I1–I10) and tooling (T1–T20) sets. Added concrete CLI invocation procedures. Added criterion T5 to catch legacy classification labels in output. Added known limitation about plot color-coding mismatch. | `rq1_analysis_tooling_plan.md` fully implemented — need to verify CLIs work before RQ1 evaluation runs. |
| 2026-06-14 | **T3 criterion refined**: Changed from "CSV row counts must be equal" to "decision_quality.csv row count ≥ reaction_latency.csv row count, difference explained by unactioned/transient labels." | Tier 1 analysis found T3 failing due to different filtering (timings requires spawn_done match, decision_quality doesn't). Both CLIs share `breach_detector.py` — underlying breach count is identical. |
| 2026-06-21 | **Bug fixes**: (a) LAN naming mismatch in `cli_rq1_timings.py` — normalised `ev.lan` ("1"/"2") to match `breach["network_id"]` ("lan1"/"lan2"). (b) Timezone shift in `events.py` `_parse_ts()` — replaced `time.mktime()` with `calendar.timegm()` for UTC→epoch conversion, fixed regex to capture comma-separated ms from controller `%(asctime)s` log format. | Both bugs caused 0 reaction latency events across all 4 runs. See `results.md` §4. |
| 2026-06-12 | v3: Added breach-detector verification criteria (11–13, 19–20). Added `controller_env_snapshot.env` prerequisite (10). Updated `controller_stats.csv` to require v3 fields (`timestamp_iso`, `phase`). Updated hypothesis with internal consistency checks for reaction latency timeline and decision quality phase mapping. | `rq1_analysis_tooling_plan.md` implementation — `breach_detector.py`, reworked `cli_rq1_timings.py` and `cli_rq1_decision_quality.py` |
| 2026-06-12 | v2: Applied collector fix — same-LAN `consumed_at` by `(network_id, window_end)` + row buffering. Updated `_compute_staleness` to same-row subtraction. | `results.md` §Root Cause → §Fix Applied |
| 2026-06-12 | v1: Initial analysis of all 4 verification runs (push, poll12, poll5, poll30). Criteria 4–6 (poll staleness) missed due to `peer_lan` cross-pairing in `collect_resource_stats.py`. See `results.md` §1 for root cause analysis. | `results.md` §1 |
