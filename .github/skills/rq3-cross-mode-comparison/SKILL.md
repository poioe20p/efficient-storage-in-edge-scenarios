---
name: rq3-cross-mode-comparison
description: 'Use when: generating RQ3 cross-mode comparison graphs after all runs of an RQ3 experiment campaign are analyzed. Triggers on: "rq3 analysis", "rq3 comparison graphs", "rq3 cross-mode graphs", "generate rq3 graphs", "compare rq3 runs", "rq3 graphs". Produces baseline FP spawns, FP score components, stress spawn count, TTFS, per-phase latency, baseline latency, latency by phase type, timeout rate, throughput, and score component decomposition graphs with per-replicate variance (scatter dots on bars, per-event dots on box plots).'
argument-hint: '<experiment_name> or auto-detect from available runs'
---

# RQ3 Cross-Mode Comparison Graphs

## Outcome

Generate the complete set of RQ3 cross-mode comparison graphs for an experiment
campaign and archive them to `<experiment_dir>/analysis/`. Every graph includes
per-replicate scatter dots (on grouped bars) and per-event scatter dots (on box
plots) to show variance — matching the quality standard of `rq3_v2.md` §5 and §6.

## When to Run

- After **all 9 runs** of an RQ3 experiment campaign have completed and run
  folders have been copied locally to `<experiment_dir>/metrics/`.
- This is **mandatory**, not optional.
- Re-run after any new runs are added to the campaign.

## Detection: Find RQ3 Runs and Group by Mode

### Step 1 — Scan for RQ3 runs

List the experiment metrics directory and filter for RQ3 naming patterns.
RQ3 v5 runs contain `rq3_v5_` in the folder name:

```powershell
# Local (after copy from cloud-vm)
Get-ChildItem docs/operation/testing/experiment/rq3_evaluation/v5/metrics -Directory |
  Where-Object { $_.Name -match 'rq3_v5_' }

# Cloud VM (if runs not yet copied)
ssh cloud-vm 'ls -d ~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/*rq3_v5_*'
```

### Step 2 — Group by mode

RQ3 v5 folder names follow the pattern:
`<timestamp>_rq3_v5_<mode>_<replicate>`

Mode detection keywords (match in folder name):

| Suffix | Mode |
|--------|------|
| `_ds_` | `degradation_score` |
| `_cpu_` | `cpu_only` |
| `_lat_` | `latency_only` |

### Step 3 — Map to experiment folder

| Prefix | Experiment folder |
|--------|-------------------|
| `rq3_v5` | `docs/operation/testing/experiment/rq3_evaluation/v5/` |

## Artifact Requirements Per Run

Before graph generation, every run folder under `<experiment_dir>/metrics/`
must contain these artifacts:

| # | Artifact | Purpose | Produced by |
|---|----------|---------|-------------|
| 1 | `elasticity_events.csv` | Detection metrics: FP spawns (M1), stress spawn count (M2), TTFS (M3), missed detections (M4) | `run_experiment.sh` post-processing |
| 2 | `client_requests.csv` | Service quality metrics: per-phase latency (M5), timeout rate (M6), throughput (M7) | `traffic_generator.py` |
| 3 | `policy_state.csv` | Score component decomposition for G8 diagnostic | `run_experiment.sh` post-processing |
| 4 | `per_node_stats.csv` | Pre→post improvement verification (C8), M4 missed detection criterion | `run_experiment.sh` post-processing |
| 5 | `controller_env_snapshot.env` | Confirm correct weights were applied per mode | `run_experiment.sh` post-processing |

> All artifacts are generated automatically by `run_experiment.sh`
> post-processing. No per-run extraction script is needed — unlike RQ1
> (which has per-run CLIs) or RQ2 (which requires `extract_spawn_metrics.py`).
> The RQ3 comparison script reads these CSVs directly.

## Graph Generation

### Analysis Script

The RQ3 comparison graph generator is at:

```
source/scripts/testing/analysis/rq3/campaign_analysis.py
```

It generates all 10 thesis graphs in one pass:

```bash
python3 -m source.scripts.testing.analysis.rq3.campaign_analysis \
    --run <label>:<mode>:<path> \
    --run <label>:<mode>:<path> \
    ... \
    --out-dir <experiment_dir>/analysis
```

Each `--run` argument has the format `label:mode:path`:
- `label`: human-readable identifier (e.g., `ds_1`, `cpu_2`)
- `mode`: one of `degradation_score`, `cpu_only`, `latency_only`
- `path`: relative or absolute path to the run folder

### Example Invocation (9-Run Campaign)

```bash
python3 -m source.scripts.testing.analysis.rq3.campaign_analysis \
    --run ds_1:degradation_score:docs/operation/testing/experiment/rq3_evaluation/v5/metrics/<ts>_rq3_v5_ds_1 \
    --run ds_2:degradation_score:docs/operation/testing/experiment/rq3_evaluation/v5/metrics/<ts>_rq3_v5_ds_2 \
    --run ds_3:degradation_score:docs/operation/testing/experiment/rq3_evaluation/v5/metrics/<ts>_rq3_v5_ds_3 \
    --run cpu_1:cpu_only:docs/operation/testing/experiment/rq3_evaluation/v5/metrics/<ts>_rq3_v5_cpu_1 \
    --run cpu_2:cpu_only:docs/operation/testing/experiment/rq3_evaluation/v5/metrics/<ts>_rq3_v5_cpu_2 \
    --run cpu_3:cpu_only:docs/operation/testing/experiment/rq3_evaluation/v5/metrics/<ts>_rq3_v5_cpu_3 \
    --run lat_1:latency_only:docs/operation/testing/experiment/rq3_evaluation/v5/metrics/<ts>_rq3_v5_lat_1 \
    --run lat_2:latency_only:docs/operation/testing/experiment/rq3_evaluation/v5/metrics/<ts>_rq3_v5_lat_2 \
    --run lat_3:latency_only:docs/operation/testing/experiment/rq3_evaluation/v5/metrics/<ts>_rq3_v5_lat_3 \
    --out-dir docs/operation/testing/experiment/rq3_evaluation/v5/analysis
```

### What the Script Does Per Graph

| Graph | Data source | Processing |
|-------|-------------|------------|
| G1 | `elasticity_events.csv` | Count score-triggered spawns during `baseline` phase rows. Exclude `standby_storage: spawning reserve`. Group by mode, compute mean + SEM across n=3 replicates, plot grouped bar with scatter dots. |
| G1b | `policy_state.csv` | For each FP spawn event in G1, look up the corresponding telemetry window's CPU score component and latency score component. Plot as 2D scatter (x=CPU, y=Latency), color by mode. |
| G2 | `elasticity_events.csv` | Count score-triggered spawns per stress phase (`storage_storm`, `tier1_hotspot`, `reverse_hotspot`, `compute_spike`) per tier (compute, storage). Grouped bar: 4 phase groups, 3 bars per group (DS/CPU/LAT). SEM + scatter dots. |
| G3 | `elasticity_events.csv` | Compute `first_spawn_ts − phase_start_ts` per stress phase. Box plot per mode per phase, individual spawn events as jittered scatter dots (aggregated across replicates). |
| G4 | `client_requests.csv` | Compute p50 latency per phase per mode. Grouped bar: 7 phase groups, 3 bars each. SEM + scatter dots. **Master service-quality graph.** |
| G5 | `client_requests.csv` | Compute p50 latency during `baseline` phase only. Grouped bar: 1 group, 3 bars. SEM + scatter dots. Cleanest measurement — no carryover backends. |
| G5b | `client_requests.csv` | Compute p50 latency aggregated by phase type (baseline, storage-stress, compute-stress, post-stress). Grouped bar: 4 groups, 3 bars each. SEM + scatter dots. |
| G6 | `client_requests.csv` | Compute per-phase timeout rate (latency ≥ 29.9s). Grouped bar: one group per phase, 3 bars each. SEM + scatter dots. |
| G7 | `client_requests.csv` | Completed requests per stress phase per mode. Grouped bar: one group per stress phase, 3 bars each. SEM + scatter dots. **Most RQ3-specific graph.** |
| G8 | `policy_state.csv` | Reconstruct CPU and latency score components from policy state rows. 3-panel line chart (one per mode, median replicate by total spawn count). X-axis: telemetry windows. Two lines: CPU component, latency component. Horizontal dashed line at threshold. Shaded regions for stress phases. |

## Graph Inventory

10 graphs total, matching `rq3_v2.md` §6:

### Detection Quality (G1–G3) — grouped bars + box plots

| # | Graph | File | Domain | Variance | What it shows |
|---|-------|------|--------|----------|---------------|
| G1 | Baseline FP Spawns by Mode | `g1_baseline_fp_spawns.png` | Detection | SEM + scatter dots | Which modes fire unnecessarily during quiescent state. Primary SQ3a graph. |
| G1b | FP Spawn Score Components at Trigger | `g1b_fp_score_components.png` | Detection | 2D position | What signal combination triggered each FP. Reveals pure-CPU noise vs borderline. |
| G2 | Stress Spawn Count by Mode & Phase | `g2_stress_spawn_count.png` | Detection | SEM + scatter dots | Detection sensitivity across all stress phases. Mode consistency across storage vs compute stress. |
| G3 | TTFS Distribution by Mode & Phase | `g3_ttfs_distribution.png` | Detection | Box/IQR + per-event dots | How quickly each mode responds to stress onset. Wide IQR = inconsistent timing. |

### Service Quality (G4–G7) — grouped bars

| # | Graph | File | Domain | Variance | What it shows |
|---|-------|------|--------|----------|---------------|
| G4 | Per-Phase p50 Latency by Mode | `g4_per_phase_p50.png` | Service Quality | SEM + scatter dots | **Master graph.** Full timeline — when does trigger composition affect user experience? |
| G5 | Baseline p50 Latency by Mode | `g5_baseline_p50.png` | Service Quality | SEM + scatter dots | Cleanest measurement: no carryover backends, no residual load. |
| G5b | Latency by Phase Type | `g5b_phase_type_p50.png` | Service Quality | SEM + scatter dots | Tests phase-dependent regime model: convergence under I/O, divergence under CPU. |
| G6 | Timeout Rate by Mode & Phase | `g6_timeout_rate.png` | Service Quality | SEM + scatter dots | User-visible harm. Complements G7 (throughput). |
| G7 | Throughput by Mode & Stress Phase | `g7_throughput.png` | Service Quality | SEM + scatter dots | **Most RQ3-specific.** Extra spawns = more work (under-detection) or same work (waste)? |

### Diagnostic (G8)

| # | Graph | File | Domain | Variance | What it shows |
|---|-------|------|--------|----------|---------------|
| G8 | Score Component Decomposition | `g8_score_components.png` | Diagnostic | N/A (illustrative) | **Why** modes behaved differently. 3 panels, median replicate each. CPU + latency component lines, threshold line, stress phase shading. |

## Styling Convention

All graphs follow the thesis styling (matching RQ1 v8 and RQ2 v3 conventions):

- **Colors**:
  - `degradation_score` = `#4CAF50` (green — system default, cross-signal confirmation)
  - `cpu_only` = `#F44336` (red — industry default, CPU alone)
  - `latency_only` = `#2196F3` (blue — user-experience dimension, latency alone)
- **Box plots**: Face color matching mode, black median line, per-event jittered scatter dots (alpha=0.55)
- **Grouped bars**: Solid fill with 0.78 alpha, black edge (0.8 linewidth), per-replicate jittered scatter dots (alpha=0.55)
- **G8 line chart**: Solid lines per component (CPU=2.0 linewidth, latency=2.0 linewidth, dashed threshold), shaded phase regions (alpha=0.12)
- **G1b scatter**: Filled circles, size 28, alpha=0.65 per mode, thin black edge
- **Axes**: Top/right spines hidden, dashed y-grid at 0.22 alpha
- **Figure sizes**: Single bar = (8,5), Box plot = (10,6), Multi-phase grouped bar = (14,6), Master G4 = (18,7), G8 diagnostic = (20,8)
- **Font sizes**: Title 13pt bold, Labels 12pt, Ticks 10pt, Annotations 9pt

## Pre-Flight Checklist

Before generating comparison graphs, verify:

1. **All 9 runs present** in `<experiment_dir>/metrics/`:
   ```powershell
   Get-ChildItem docs/operation/testing/experiment/rq3_evaluation/v5/metrics -Directory |
     Where-Object { $_.Name -match 'rq3_v5_' } |
     Measure-Object | Select-Object -ExpandProperty Count
   # Expected: 9
   ```

2. **All 5 required artifacts present per run**:
   ```powershell
   $required = @('elasticity_events.csv','client_requests.csv','policy_state.csv','per_node_stats.csv','controller_env_snapshot.env')
   Get-ChildItem docs/operation/testing/experiment/rq3_evaluation/v5/metrics/*rq3_v5_* -Directory |
     ForEach-Object {
       $missing = $required | Where-Object { -not (Test-Path (Join-Path $_.FullName $_)) }
       if ($missing) { "$($_.Name): MISSING $missing" }
     }
   ```

3. **Controller env confirms correct weights per mode**:
   ```powershell
   Get-ChildItem docs/operation/testing/experiment/rq3_evaluation/v5/metrics/*rq3_v5_*/controller_env_snapshot.env |
     ForEach-Object {
       $w = Select-String -Path $_.FullName -Pattern 'SCALEUP_W_CPU=|SCALEUP_W_T_PROC=|SCALEUP_W_STORAGE_CPU=|SCALEUP_W_T_DB='
       "$($_.Directory.Name): $($w -join ', ')"
     }
   ```
   Expected ranges per mode table in experiment plan §4.1.

4. **No runs with >50% http_status=0** — flag any run where timeouts dominate.

5. **All runs reached `idle`** — check `current_phase.txt` contains `idle`.

## Run Location

- If run folders are on `cloud-vm`, copy them locally first (per `experiment_plan_v5.md` §6.4), then run the analysis script locally using the workspace Python environment (`.venv`).
- If running on cloud-vm, sync the analysis script first, then `scp` the `analysis/` folder back.

## Post-Generation

1. **Verify**: List the analysis folder and confirm all 10 PNGs are present:
   ```powershell
   Get-ChildItem docs/operation/testing/experiment/rq3_evaluation/v5/analysis/*.png |
     Select-Object Name
   # Expected: g1_baseline_fp_spawns.png, g1b_fp_score_components.png,
   #   g2_stress_spawn_count.png, g3_ttfs_distribution.png,
   #   g4_per_phase_p50.png, g5_baseline_p50.png, g5b_phase_type_p50.png,
   #   g6_timeout_rate.png, g7_throughput.png, g8_score_components.png
   ```

2. **Document**: Write `rq3_eval_v5_findings.md` in the analysis folder, structured against C1–C8 from the experiment plan, with per-mode summaries and thesis narrative alignment. Reference the 10 graphs.

3. **Cross-RQ comparison notes**: Capture M2 (stress spawn count), M5 (per-phase latency), and M7 (throughput) baseline values for the detection→delivery→action chain narrative spanning RQ3→RQ1→RQ2.

## Implementation Notes

The `campaign_analysis.py` script does NOT exist yet. This skill defines its
expected interface and behavior. When implementing, follow these conventions:

1. **Input**: `--run label:mode:path` triples (flexible count), `--out-dir`
2. **Data loading**: Read CSVs directly from run folders (no intermediate extraction)
3. **Mode grouping**: Aggregate by mode for per-replicate statistics
4. **Phase mapping**: Use `phases_snapshot.json` from the first run folder for phase names and durations
5. **FP spawn exclusion**: Filter out `standby_storage: spawning reserve` events from M1 counts
6. **G8 replicate selection**: Use the median replicate per mode by total spawn count
7. **Error handling**: Skip runs with missing CSVs, warn about n<3 per mode, produce partial graphs when possible
8. **Output**: PNG files at 150 DPI, named as specified in the inventory above
