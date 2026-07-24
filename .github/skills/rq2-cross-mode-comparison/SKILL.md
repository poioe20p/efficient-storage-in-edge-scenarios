---
name: rq2-cross-mode-comparison
description: 'Use when: generating RQ2 cross-mode comparison graphs after all runs of an RQ2 experiment campaign are analyzed. Triggers on: "rq2 analysis", "rq2 comparison graphs", "rq2 cross-mode graphs", "generate rq2 graphs", "compare rq2 runs", "rq2 graphs". Produces TTFT, TFR, init time, initial share, per-phase p50, percentile, and phase-type graphs with per-replicate variance (scatter dots on bars, per-event dots on box plots).'
argument-hint: '<experiment_name> or auto-detect from available runs'
---

# RQ2 Cross-Mode Comparison Graphs

## Outcome

Generate the complete set of RQ2 cross-mode comparison graphs for an experiment
campaign and archive them to `<experiment_dir>/graphs/`. Every graph includes
per-replicate scatter dots (on grouped bars) and per-event scatter dots (on box
plots) to show variance — matching the quality standard of `rq2_v3.md` §5 and §6.

## When to Run

- After **all runs** of an RQ2 experiment campaign have completed per-run
  analysis (`extract_spawn_metrics.py` has been run on every run folder,
  producing `analysis/rq2_spawn_metrics.csv`).
- This is **mandatory**, not optional.
- Re-run after any new runs are added to the campaign.

## Detection: Find RQ2 Runs and Group by Mode

### Step 1 — Scan for RQ2 runs

List the metrics directory and filter for RQ2 naming patterns. RQ2 v3 runs
contain `rq2_v3_` in the folder name:

```powershell
# Local
Get-ChildItem source/scripts/testing/metrics -Directory |
  Where-Object { $_.Name -match 'rq2_v3_' }

# Cloud VM
ssh cloud-vm 'ls -d ~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/*rq2_v3_*'
```

### Step 2 — Group by mode

RQ2 folder names follow the pattern:
`<timestamp>_rq2_v3_<mode>_<replicate>`

Mode detection keywords (match in folder name):

| Suffix | Mode |
|--------|------|
| `_th_` | `topology_host` |
| `_ss_` | `topology_slowstart` |
| `_tl_` | `topology_lifecycle` |

### Step 3 — Map to experiment folder

Resolve the experiment folder at `docs/operation/testing/experiment/`. Match
the version prefix to the experiment subdirectory:

| Prefix | Experiment folder |
|--------|-------------------|
| `rq2_v3` | `docs/operation/testing/experiment/rq2_evaluation/v3/` |

## Graph Generation

### Primary Script

Use `campaign_analysis.py` which generates all 11 thesis graphs in one pass:

```bash
python3 -m source.scripts.testing.analysis.rq2.campaign_analysis \
    --run <label1>:<mode1>:<path1> \
    --run <label2>:<mode2>:<path2> \
    ... \
    --out-dir <experiment_dir>/graphs
```

Each `--run` argument has the format `label:mode:path`:
- `label`: human-readable identifier (e.g., `th_1`, `ss_2`)
- `mode`: one of `topology_host`, `topology_slowstart`, `topology_lifecycle`
- `path`: relative or absolute path to the run folder

### Prerequisite: Per-Run Extraction

Before running `campaign_analysis.py`, `extract_spawn_metrics.py` must have
been run on every run folder:

```bash
python3 -m source.scripts.testing.analysis.rq2.extract_spawn_metrics \
    <run_folder> --mode <topology_host|topology_slowstart|topology_lifecycle>
```

This produces `analysis/rq2_spawn_metrics.csv` per run, which is the input for
`campaign_analysis.py`.

## Graph Inventory

All 11 graphs are generated in a single `campaign_analysis.py` invocation
(matching `rq2_v3.md` §6):

### Spawn-to-Service Timing (box plots + per-event scatter dots)

| # | Graph | File | What it shows |
|---|-------|------|---------------|
| G1 | TTFT Distribution by Mode | `g1_ttft.png` | How quickly routing sends traffic to new backends |
| G2 | TFR Distribution by Mode | `g2_tfr.png` | How quickly backends serve their first response |
| G2b | TTFT vs TFR Scatter by Mode | `g2b_ttft_vs_tfr.png` | Speed vs readiness — diagonal = backend ready when traffic arrived |
| G3 | Backend Initialisation Time by Mode | `g3_init_time.png` | TFR − TTFT — isolates backend init from routing awareness |
| G4 | Initial Load Share by Mode | `g4_initial_share.png` | How aggressively each mode redirects traffic |
| G4b | TTFT vs Initial Share Scatter | `g4b_ttft_vs_share.png` | Speed vs magnitude joint distribution |

### Service Quality (grouped bars + per-replicate scatter dots)

| # | Graph | File | What it shows |
|---|-------|------|---------------|
| G5 | Baseline p50 Latency by Mode | `g5_baseline_p50.png` | Routing quality from quiescent state — cleanest signal |
| G5b | Non-Stress p50 Latency by Mode | `g5b_nonstress_p50.png` | Routing quality across all low-load phases |
| G6 | Per-Phase p50 Latency by Mode | `g6_per_phase_p50.png` | **Master graph** — when does routing matter? |
| G7 | Per-Mode Latency Percentiles | `g7_percentiles.png` | p50/p95/p99 per mode — median vs tail |
| G8 | Latency by Phase Type | `g8_phase_type_p95.png` | Convergence vs divergence per regime |

## Styling Convention

All graphs follow the RQ1 v8 thesis styling:

- **Colors**: Host = `#F44336` (red), Slowstart = `#FF9800` (orange), Lifecycle = `#4CAF50` (green)
- **Box plots**: Face color matching mode, black median line, per-event jittered scatter dots (alpha=0.55)
- **Grouped bars**: Solid fill with 0.78 alpha, black edge, per-replicate jittered scatter dots (alpha=0.55)
- **Axes**: Top/right spines hidden, dashed y-grid at 0.22 alpha
- **Figure sizes**: Single = (10,6), Wide = (14,6), Master (G6) = (18,7)
- **Font sizes**: Title 13pt bold, Labels 12pt, Ticks 11pt, Annotations 10pt

## Pre-Flight Checklist

Before generating comparison graphs, verify:

1. **`extract_spawn_metrics.py` has been run** on every run folder → `analysis/rq2_spawn_metrics.csv` exists per run.

2. **`client_requests.csv`** exists in every run folder (needed for per-phase latency).

3. **`controller_env_snapshot.env`** confirms correct `BACKEND_SELECTION_POLICY` per run:
   ```bash
   for d in metrics/*rq2_v3_*; do echo "$d: $(sudo grep BACKEND_SELECTION $d/controller_env_snapshot.env)"; done
   ```

4. **All 9 runs present** — 3 per mode. Flag if any mode has fewer than 3 replicates.

## Run Location

- If run folders are on `cloud-vm`, sync analysis code, run extraction + generation via SSH, then `scp` the `graphs/` folder back locally.
- If run folders have been copied locally, run locally using the workspace Python environment (`.venv`).

## Post-Generation

1. **Sync locally**: If run on cloud-vm, copy the graphs folder back:
   ```powershell
   $dest = "docs/operation/testing/experiment/rq2_evaluation/v3/graphs"
   New-Item -ItemType Directory -Force -Path $dest | Out-Null
   scp cloud-vm:/tmp/rq2_v3_graphs/*.png "$dest/"
   ```

2. **Verify**: List the graphs folder and confirm all 11 PNGs are present:
   ```powershell
   Get-ChildItem docs/operation/testing/experiment/rq2_evaluation/v3/graphs/ | Select-Object Name
   ```

3. **Document**: Note any excluded runs, mode count, and replicate count. Update
   the experiment's `results.md` with graph references.

## Full Workflow (Example)

For a 9-run v3 campaign on cloud-vm:

```bash
# 1. Sync analysis code
scp source/scripts/testing/analysis/rq2/extract_spawn_metrics.py cloud-vm:~/efficient-storage-in-edge-scenarios/source/scripts/testing/analysis/rq2/
scp source/scripts/testing/analysis/rq2/campaign_analysis.py cloud-vm:~/efficient-storage-in-edge-scenarios/source/scripts/testing/analysis/rq2/

# 2. Fix ownership (runs created with sudo)
ssh cloud-vm 'sudo chown -R testop:testop ~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/*rq2_v3_*'

# 3. Run per-run extraction
ssh cloud-vm 'cd ~/efficient-storage-in-edge-scenarios && \
  for pair in \
    source/scripts/testing/metrics/20260723_121444_rq2_v3_th_1:topology_host \
    ...; do
    d="${pair%%:*}"; m="${pair##*:}";
    python3 source/scripts/testing/analysis/rq2/extract_spawn_metrics.py "$d" --mode "$m";
  done'

# 4. Generate comparison graphs
ssh cloud-vm 'cd ~/efficient-storage-in-edge-scenarios && \
  python3 source/scripts/testing/analysis/rq2/campaign_analysis.py \
    --run th_1:topology_host:source/scripts/testing/metrics/20260723_121444_rq2_v3_th_1 \
    --run th_2:topology_host:source/scripts/testing/metrics/20260723_131920_rq2_v3_th_2 \
    --run th_3:topology_host:source/scripts/testing/metrics/20260723_141518_rq2_v3_th_3 \
    --run ss_1:topology_slowstart:source/scripts/testing/metrics/20260723_151453_rq2_v3_ss_1 \
    --run ss_2:topology_slowstart:source/scripts/testing/metrics/20260723_161744_rq2_v3_ss_2 \
    --run ss_3:topology_slowstart:source/scripts/testing/metrics/20260723_171539_rq2_v3_ss_3 \
    --run tl_1:topology_lifecycle:source/scripts/testing/metrics/20260723_191641_rq2_v3_tl_1 \
    --run tl_2:topology_lifecycle:source/scripts/testing/metrics/20260723_201650_rq2_v3_tl_2 \
    --run tl_3:topology_lifecycle:source/scripts/testing/metrics/20260723_211342_rq2_v3_tl_3 \
    --out-dir /tmp/rq2_v3_graphs'

# 5. Copy graphs locally
scp cloud-vm:/tmp/rq2_v3_graphs/*.png docs/operation/testing/experiment/rq2_evaluation/v3/graphs/
```
