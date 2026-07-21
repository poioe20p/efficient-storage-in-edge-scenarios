---
name: rq1-cross-mode-comparison
description: 'Use when: generating RQ1 cross-mode comparison graphs after all runs of an RQ1 experiment campaign are analyzed. Triggers on: "rq1 analysis", "rq1 comparison graphs", "cross-mode graphs", "generate comparison graphs", "compare rq1 runs", "rq1 graphs". Produces reaction latency, controller overhead, staleness, timeout rate, per-phase timeout, and decision quality graphs with per-replicate variance (scatter dots, error bars).'
argument-hint: '<experiment_name> or auto-detect from available runs'
---

# RQ1 Cross-Mode Comparison Graphs

## Outcome

Generate the complete set of RQ1 cross-mode comparison graphs for an experiment
campaign and archive them to `<experiment_dir>/graphs/comparison/`. Every graph
includes per-replicate scatter dots and error bars to show variance — matching
the quality standard of `rq1.md` §5 and §6.

## When to Run

- After **all runs** of an RQ1 experiment campaign have completed per-run
  analysis (all single-run CLIs: `decision_quality`, `timings`,
  `blind_spot_windows`, `timeout_root_cause`, `endpoint_latency`,
  `recovery_lag`, `missed_opportunities`, `time_to_capacity`, `overhead`).
- This is **mandatory**, not optional — per the RQ1 scope rule in the Edge
  Experiment Analyzer mode instructions.
- Re-run after any new runs are added to the campaign.

## Detection: Find RQ1 Runs and Group by Mode

### Step 1 — Scan for RQ1 runs

List `source/scripts/testing/metrics/` and filter for folders matching the
RQ1 naming pattern. RQ1 runs contain `rq1_` in the folder name:

```powershell
# Local
Get-ChildItem source/scripts/testing/metrics -Directory |
  Where-Object { $_.Name -match 'rq1_' }

# Cloud VM
ssh cloud-vm 'ls -d ~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/*rq1_*'
```

### Step 2 — Group by experiment family

RQ1 folder names follow the pattern:
`<timestamp>_rq1_<version>_<variant>_<mode>_<replicate>`

Group runs by their **family prefix** — everything after the timestamp up to
the mode suffix. The mode is the last segment before the replicate number.

Examples:

| Folder | Family | Mode |
|--------|--------|------|
| `*_rq1_v3_push_1` | `rq1_v3` | push |
| `*_rq1_v5_pilotB_push_2` | `rq1_v5_pilotB` | push |
| `*_rq1_v7_gap_poll30_1` | `rq1_v7_gap` | poll30 |

Mode detection keywords (case-insensitive match in folder name):
- **Push**: `_push_` but NOT `_push_` inside `_gap_push_` (handle carefully)
- **Poll-5s**: `_poll5_`
- **Poll-12s**: `_poll12_`
- **Poll-30s**: `_poll30_`

### Step 3 — Map to experiment folder

Resolve the experiment folder at `docs/operation/testing/experiment/`. Match
the family prefix to the experiment subdirectory:

| Family examples | Experiment folder |
|-----------------|-------------------|
| `rq1_v3` | `docs/operation/testing/experiment/rq1_thesis_final/` |
| `rq1_v5_pilotB` | `docs/operation/testing/experiment/rq1_thesis_final/v5/` |
| `rq1_v7_gap` (or `rq1_v7_slot`) | `docs/operation/testing/experiment/rq1_thesis_final/v7/` |

When the family contains multiple sub-experiments (e.g., `v7_gap` and
`v7_slot`), generate separate comparison graphs for each sub-experiment.

## Script Selection

### 4-mode experiments (Push, Poll-5s, Poll-12s, Poll-30s)

Use the canonical script:

```bash
python -m source.scripts.testing.analysis.rq1.scripts.generate_comparison_graphs \
    --run-dirs-push <push_dir1> <push_dir2> ... \
    --run-dirs-poll5 <poll5_dir1> <poll5_dir2> ... \
    --run-dirs-poll12 <poll12_dir1> <poll12_dir2> ... \
    --run-dirs-poll30 <poll30_dir1> <poll30_dir2> ... \
    --output-dir <experiment_dir>/graphs/comparison/
```

**Note**: The canonical script requires all 4 `--run-dirs-*` arguments. For
missing modes, pass the argument with a non-existent placeholder path (e.g.,
`--run-dirs-poll5 /nonexistent`). The `collect_mode_data` function handles
empty CSVs gracefully (returns zeros).

### 2-mode experiments (Push + Poll-30s only)

Use the v7-specific script (adapts the canonical logic for 2 modes):

```bash
python3 source/scripts/testing/analysis/rq1/scripts/v7_comparison_full.py \
    --push-dirs <push_dir1> <push_dir2> ... \
    --poll30-dirs <poll30_dir1> <poll30_dir2> ... \
    --output-dir <experiment_dir>/graphs/comparison/
```

This script is at `source/scripts/testing/analysis/rq1/scripts/v7_comparison_full.py`
and accepts `--push-dirs` and `--poll30-dirs` with variable numbers of
replicates. All graphs include per-replicate scatter dots and error bars.

## Graph Inventory

The comparison generates these outputs (matching `rq1.md` §5 measurements):

| # | Graph | Measurement (§) | Variance |
|---|-------|-----------------|----------|
| 1 | `*_latency_mean.png` | 5.2 — Mean reaction latency | Per-event scatter dots |
| 2 | `*_latency_max.png` | 5.2 — Max reaction latency | Per-event scatter dots |
| 3 | `*_reaction_latency_combined.png` | 5.2 — Mean+max grouped | Value labels |
| 4 | `*_overhead_comparison.png` | 5.4 — Controller CPU% + RSS | Per-replicate scatter dots |
| 5 | `*_staleness_comparison.png` | 5.1 — Max information age | Per-replicate scatter dots |
| 6 | `*_timeout_comparison.png` | 5.3 — Timeout rate overall | Scatter dots + stddev |
| 7 | `*_per_phase_timeout.png` | 5.3 — Per-phase timeout rate | Error bars + scatter dots |
| 8 | `*_decision_quality.png` | 5.5 — Breached windows & spawns | N/A (descriptive table) |
| 9 | `*_decision_quality.csv` | 5.5 — Raw decision quality | N/A |

The prefix varies by script: `rq1_v2_` for the canonical 4-mode script,
`v7_` for the 2-mode script. All outputs go to `graphs/comparison/`.

## Pre-Flight Checklist

Before generating comparison graphs, verify:

1. **All per-run CLIs have been run** on every run in the campaign:
   - `decision_quality` → `analysis/rq1/rq1_decision_quality.csv`
   - `timings` → `analysis/rq1_reaction_latency.csv`, `analysis/rq1_staleness.csv`
   - `overhead` → `analysis/rq1/rq1_overhead.csv`
   - `blind_spot_windows` → `analysis/rq1/rq1_blind_spot_windows.csv`
   - `timeout_root_cause` → `analysis/rq1/rq1_timeout_root_cause.csv`

2. **`controller_stats.csv`** exists in every run folder (needed for overhead graph).

3. **`client_requests.csv`** exists in every run folder (needed for timeout rate).

4. **Anomalous runs are identified and excluded** — runs with >50% http_status=0
   or other clear defects should be omitted from comparison. Document exclusions
   in the graph footnotes or a README in the comparison folder.

## Run Location

The comparison script runs where the data resides:
- If run folders are on `cloud-vm`, run the script via SSH on `cloud-vm`,
  then `scp` the `graphs/comparison/` folder back locally.
- If run folders have been copied locally, run locally using the workspace
  Python environment (`.venv`).

## Post-Generation

1. **Sync locally**: If run on cloud-vm, copy `graphs/comparison/` back:
   ```powershell
   scp -r cloud-vm:<experiment_dir>/graphs/comparison <local_experiment_dir>/graphs/
   ```

2. **Verify**: List the comparison folder and confirm all expected PNGs and
   CSVs are present.

3. **Document**: Note any excluded runs, mode count, and replicate count in a
   brief comment or update the experiment's `results.md`.

## Full Workflow (Example)

For a v7-style 2-mode experiment with Push and Poll-30s:

```bash
# 1. Detect runs
ssh cloud-vm 'ls -d ~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/*rq1_v7_gap_*'

# 2. Group by mode
# Push:  *rq1_v7_gap_push_1  (exclude *push_2 if anomalous)
# Poll:  *rq1_v7_gap_poll30_1  *rq1_v7_gap_poll30_2

# 3. Run comparison on cloud-vm
ssh cloud-vm 'cd ~/efficient-storage-in-edge-scenarios && python3 \
  source/scripts/testing/analysis/rq1/scripts/v7_comparison_full.py \
  --push-dirs source/scripts/testing/metrics/20260721_051833_rq1_v7_gap_push_1 \
  --poll30-dirs \
    source/scripts/testing/metrics/20260721_064626_rq1_v7_gap_poll30_1 \
    source/scripts/testing/metrics/20260721_073750_rq1_v7_gap_poll30_2 \
  --output-dir docs/operation/testing/experiment/rq1_thesis_final/v7/graphs/comparison'

# 4. Sync locally
scp -r cloud-vm:~/efficient-storage-in-edge-scenarios/docs/operation/testing/experiment/rq1_thesis_final/v7/graphs/comparison \
  docs/operation/testing/experiment/rq1_thesis_final/v7/graphs/
```
