# Run Analysis Toolchain

## Objective

Build an offline analysis package that turns a run directory (the artifacts
emitted by `collect_resource_stats.py`, `traffic_generator.py`, and the SDN
controller logs) into phase-aligned plots and diagnostic tables. Today the only
way to interpret a run is to eyeball the CSVs; this document provides:

1. A shared **loader** that reads every artifact produced by a run, normalises
   timestamps, and parses controller logs into typed `ElasticityEvent`s.
2. A **per-node CSV** (`per_node_stats.csv`) so analysis can see whether new
   dynamic nodes actually absorb load.
3. Four **diagnostic CLIs** consuming the loader â€” overview dashboard,
    CPU-driver diagnostic, scale-down predicate audit, and T_db decomposition
    regression.
4. A simple **run-summary CLI** (`cli_simple_run`) for average latency,
    p95 latency, failure rate, and active-node plots.
5. A simple **comparison CLI** (`cli_simple_compare`) for cross-run overall and
    per-phase latency, failure rate, and node-count summaries.
6. A **recovery-validation CLI** (`cli_recovery_validation`) that summarizes
    request-lease outcomes, controller recovery markers, and request failures,
    with optional correlation against explicit fault events when a run has
    them.

Scope boundary: the toolchain is **read-only**. It does not change telemetry,
thresholds, scaling logic, or the traffic generator. Columns that depend on
telemetry changes (defined in
[`../telemetry/implementation/db_timing_decomposition.md`](../telemetry/implementation/db_timing_decomposition.md))
degrade gracefully when missing â€” the affected charts are skipped with a
warning.

## Impact on the testing mechanism

Reference: [`./testing_overview.md`](testing_overview.md).

| Stage | Current | After this plan |
|---|---|---|
| Collector `collect_resource_stats.py` | writes `resource_stats.csv` (trimmed) + `resource_stats_debug.csv` (broad) + `per_node_stats.csv` (one row per container per window) | N/A — already implemented |
| Post-run policy reconstruction | manual log inspection | `reconstruct_policy_state.py` generates `policy_state.csv` from existing artifacts; `parse_elasticity_logs.py` generates `elasticity_events.csv` |
| Fault injector `fault_injector.py` | not present | optionally writes `experiment_fault_events.csv` when `run_experiment.sh --fault-plan <file>` is used |
| Post-processing | ad-hoc — manual CSV inspection | `python -m source.scripts.testing.analysis.cli_<name> --run-dir <dir>` produces PNGs and a `summary.md` under `<dir>/analysis/`; `cli_simple_compare` writes a separate comparison output directory |
| Run directory layout | CSVs + controller logs | standard contract includes `client_requests.csv`, `resource_stats.csv`, `resource_stats_debug.csv`, `policy_state.csv`, `per_node_stats.csv`, `container_events.csv`, `elasticity_events.csv`, controller logs, `controller_env_snapshot.env`, `phases_snapshot.json`, a `service_logs/` directory, and an `analysis/` subdirectory populated on demand |

No change to experiment execution, workload definition, or the traffic
generator. `policy_state.csv` is reconstructed post-run and does not require
a new controller-side publisher.

---

## File map

| Action | Path | Purpose |
|---|---|---|
| Edit | `source/scripts/testing/collect_resource_stats.py` | emit `per_node_stats.csv` alongside the existing domain CSV |
| New | `source/scripts/testing/analysis/__init__.py` | package marker |
| New | `source/scripts/testing/analysis/loader.py` | `load_run(path) â†’ Run` |
| New | `source/scripts/testing/analysis/events.py` | controller-log regex parsers â†’ `list[ElasticityEvent]` |
| New | `source/scripts/testing/analysis/phase_window.py` | map window timestamps to phase boundaries via `phases_snapshot.json` |
| New | `source/scripts/testing/analysis/plots.py` | shared matplotlib helpers (phase shading, event overlays) |
| New | `source/scripts/testing/analysis/simple_metrics.py` | request bucketing, failure-rate summaries, and active-node reconstruction from `container_events.csv` |
| New | `source/scripts/testing/analysis/cli_overview.py` | one-page dashboard per run |
| New | `source/scripts/testing/analysis/cli_simple_run.py` | simple per-run latency, failure-rate, and active-node plots |
| New | `source/scripts/testing/analysis/cli_simple_compare.py` | simple multi-run comparison plots |
| New | `source/scripts/testing/analysis/cli_recovery_validation.py` | targeted recovery-validation summary around injected fault windows |
| New | `source/scripts/testing/analysis/cli_cpu_drivers.py` | per-node CPU vs request_count, old-vs-new load-balance table |
| New | `source/scripts/testing/analysis/cli_scale_down.py` | reconstruct scale-down predicate from CSV; compare to logs |
| New | `source/scripts/testing/analysis/cli_tdb_drivers.py` | T_db decomposition regression |
| New | `source/scripts/testing/analysis/requirements.txt` | `matplotlib` (no pandas / numpy) |

---

## Execution order

### 1. Collector â€” emit `per_node_stats.csv`

One row per container per window. `role` is `"compute"` for rows from
`summary.servers` and `"storage"` for `summary.storage_servers`.

**Unit note â€” `avg_repl_lag_s` vs domain `avg_repl_lag_ms`.** The per-node CSV
writes `avg_repl_lag_s` in **seconds** (raw aggregator field), while the
domain CSV defined in
[`../telemetry/implementation/db_timing_decomposition.md`](../telemetry/implementation/db_timing_decomposition.md)
writes `avg_repl_lag_ms` in **milliseconds**. Analysis code joining the two
CSVs on the same axis must convert explicitly â€” the 1000Ã— mismatch is
otherwise silent and easy to miss.

```python
# source/scripts/testing/collect_resource_stats.py
PER_NODE_FIELDNAMES = [
    "timestamp", "phase", "network_id", "window_end",
    "server_id", "role", "request_count",
    "cpu_percent", "ram_used_mb",
    "avg_time_proc_ms", "avg_time_db_ms",
    "avg_time_db_read_ms", "avg_time_db_write_ms", "avg_time_db_cmd_count",
    "avg_repl_lag_s", "member_state", "last_report_ts",
]


def _emit_per_node_rows(writer, summary, phase, ts, network_id, window_end):
    for sid, s in summary.get("servers", {}).items():
        writer.writerow({
            "timestamp": ts, "phase": phase, "network_id": network_id,
            "window_end": window_end, "server_id": sid, "role": "compute",
            "request_count":         s.get("request_count", 0),
            "cpu_percent":           s.get("avg_cpu_percent", ""),
            "ram_used_mb":           s.get("avg_ram_used_mb", ""),
            "avg_time_proc_ms":      s.get("avg_time_proc_ms", ""),
            "avg_time_db_ms":        s.get("avg_time_db_ms", ""),
            "avg_time_db_read_ms":   s.get("avg_time_db_read_ms", ""),
            "avg_time_db_write_ms":  s.get("avg_time_db_write_ms", ""),
            "avg_time_db_cmd_count": s.get("avg_time_db_cmd_count", ""),
            "avg_repl_lag_s":        "", "member_state": "",
            "last_report_ts":        s.get("last_report_ts", ""),
        })
    for sid, s in summary.get("storage_servers", {}).items():
        writer.writerow({
            "timestamp": ts, "phase": phase, "network_id": network_id,
            "window_end": window_end, "server_id": sid, "role": "storage",
            "request_count":         s.get("sample_count", 0),
            "cpu_percent":           s.get("avg_cpu_percent", ""),
            "ram_used_mb":           s.get("avg_ram_used_mb", ""),
            "avg_time_proc_ms":      "", "avg_time_db_ms": "",
            "avg_time_db_read_ms":   "", "avg_time_db_write_ms": "",
            "avg_time_db_cmd_count": "",
            "avg_repl_lag_s":        s.get("avg_repl_lag_s", ""),
            "member_state":          s.get("member_state", "") or "",
            "last_report_ts":        s.get("last_report_ts", ""),
        })


# In main() â€” open a second CSV alongside the existing one:
per_node_path = os.path.join(output_dir or ".", "per_node_stats.csv")
per_node_file = open(per_node_path, "w", newline="")
per_node_writer = csv.DictWriter(per_node_file, fieldnames=PER_NODE_FIELDNAMES)
per_node_writer.writeheader()
per_node_file.flush()

# Inside the poll loop, after writing the domain row:
_emit_per_node_rows(
    per_node_writer, summary,
    phase=row["phase"], ts=row["timestamp"],
    network_id=row["network_id"], window_end=row["window_end"],
)
per_node_file.flush()
```

**Acceptance:** after a â‰¥ 60 s collection, `per_node_stats.csv` exists with
row count â‰ˆ Î£(active containers) Ã— windows.

### 2. Loader

```python
# source/scripts/testing/analysis/loader.py
from dataclasses import dataclass
from pathlib import Path
import csv, json, re


@dataclass
class PhaseSpec:
    name: str
    duration_s: int
    rate_per_client: float
    cross_region_ratio: float
    mix: dict
    start_offset_s: float = 0.0   # filled in after load


@dataclass
class ElasticityEvent:
    ts: float
    lan: str
    kind: str     # alert | spawn_start | spawn_done | scale_down | busy | cooldown | armed | down_eval
    tier: str     # compute | storage
    container: str | None = None
    fields: dict | None = None    # extra regex captures (e.g. hits, below)


@dataclass
class Run:
    run_dir: Path
    phases: list[PhaseSpec]
    domain_rows: list[dict]
    node_rows: list[dict]                     # empty if per_node_stats.csv missing
    clients: dict[str, list[dict]]            # phase -> rows
    events: list[ElasticityEvent]
    t0: float                                 # earliest window_end, for time normalization


def load_run(run_dir: Path) -> Run:
    phases = _load_phases(run_dir / "phases_snapshot.json")
    domain_rows = _read_csv(run_dir / "resource_stats.csv")
    node_rows = _read_csv(run_dir / "per_node_stats.csv", optional=True)
    clients = {
        p.name: _read_csv(run_dir / f"client_requests_{p.name}.csv", optional=True)
        for p in phases
    }
    all_client_rows = _read_csv(run_dir / "client_requests.csv", optional=True)
    container_event_rows = _read_csv(run_dir / "container_events.csv", optional=True)
    fault_event_rows = _read_csv(run_dir / "experiment_fault_events.csv", optional=True)
    # Controller log filenames match the convention in run_experiment.sh.
    # If that naming changes, update this list.
    events = _parse_logs([run_dir / "controller_lan1.log",
                          run_dir / "controller_lan2.log"])
    t0 = min(float(r["window_end"]) for r in domain_rows) if domain_rows else 0.0
    return Run(
        run_dir,
        phases,
        domain_rows,
        node_rows,
        clients,
        all_client_rows,
        container_event_rows,
        fault_event_rows,
        events,
        t0,
    )
```

**Loader dependencies on upstream artifacts:**

- `phases_snapshot.json` must contain `cross_region_ratio` per phase â€” it is
  consumed by `cli_tdb_drivers`. If absent, the CLI warns and falls back to
  the nominal ratio from the workload definition (constants mirrored from
  `testing_workloads.md`).
- `resource_stats.csv` must have the `avg_time_db_*` columns populated for
  `cli_tdb_drivers` to run; absent columns are treated as the CLI skipping
  itself with a warning.
- Controller logs must be at `LOG_LEVEL=DEBUG` for `cli_scale_down` to see
  the per-window eval lines; at INFO the CLI falls back to showing only the
  `ARMED` rising edges.

### 3. Log event parser

Grammar is permissive â€” misses degrade gracefully. The scale-down grammar is
owned by the elasticity plan
([`../elasticy_manager/implementation/scale_down_instrumentation.md`](../elasticy_manager/implementation/scale_down_instrumentation.md)).

Retained lifecycle timing exports should preserve three operations in
`node_lifecycle_timings.csv`:

- `add` for bootstrap completion (`NodeResult` / `StepTimings`);
- `ready` for service admission (`vip_backend_registered`,
  `rs_secondary_ready`, telemetry fallback promotion, or Tier 1 `ACTIVE`);
- `remove` for scale-down cleanup completion.

For storage and Tier 1, analysis that cares about user-visible elasticity
latency should prefer `operation=ready` over `operation=add`.

```python
# source/scripts/testing/analysis/events.py
_RE_ALERT       = re.compile(r"alert submitted .*?(ComputeAlert|DataAlert)\(lan=(\d)")
_RE_SPAWN_START = re.compile(r"\[elasticity\] (compute|data): spawning (\S+) on LAN (\d)")
_RE_SPAWN_DONE  = re.compile(r"\[elasticity\] (compute|data): (\S+) online")
_RE_COOLDOWN    = re.compile(r"\[scale-down\] (compute|storage) within (\d+)s cooldown")
_RE_BUSY        = re.compile(r"\[scale-down\] elasticity manager is busy")
_RE_ARMED       = re.compile(r"\[scale-down\] (compute|storage) ARMED: hits=(\d+)/(\d+)")
_RE_DOWN_EVAL   = re.compile(
    r"\[scale-down\] (compute|storage) eval: "
    r"(?:cpu|stCpu)=([\d.]+)/[\d.]+ "
    r"(?:proc|db)=([\d.]+)/[\d.]+ "
    r"below=(\w+) hits=(\d+)/(\d+) armed=(\w+)"
)
```

### 4. `cli_overview`

One figure per run with N rows per LAN stacked:

### 4a. `cli_recovery_validation`

Focused summary for runs that care about request-local recovery semantics.
The CLI is intentionally narrow: it does not replace the overview dashboard,
and it does not require explicit fault events to run.

Artifacts written under `<run_dir>/analysis/`:

- `recovery_validation_summary.md`
- `recovery_validation_fault_windows.csv`
- `recovery_validation_request_lease_outcomes.csv`

Primary inputs:

- `experiment_fault_events.csv` when present
- `service_logs/edge_server_*.log`
- `controller_lan1.log`, `controller_lan2.log`
- `client_requests.csv`

Questions answered:

1. How many `success_normal`, `success_after_rebind`, and
    `failure_terminal` request-lease outcomes were observed?
2. Did the controller emit `recovery avoiding last normal backend` markers?
3. Did recovery fall back to the full pool because avoidance would empty the
    candidate set?
4. What was the request failure rate around the observed recovery activity?
5. If `experiment_fault_events.csv` exists, did the planned injected fault
    actually execute and what happened around that window?

- request rate (from `client_requests.csv`, grouped by `phase`)
- compute CPU (domain median + per-node thin grey lines)
- storage CPU (domain median + per-node thin grey lines)
- `T_proc`
- `T_db` with `T_db_read` / `T_db_write` stacked
- node counts (compute, storage)

All axes share a time x-axis with phase background shading and vertical lines
at spawn/remove events from the event stream.

### 4b. `cli_simple_run`

Simple service-facing run summary. Uses `client_requests.csv` for latency and
failure-rate plots and `container_events.csv` for active-node plots. Produces a
single figure with:

- average latency over time
- p95 latency over time
- failure rate over time
- total active nodes over time
- active nodes by type (`compute`, `storage`, `selective`)

This is intended to be the first interpretation surface for a run before the
more diagnostic dashboards are consulted.

### 4c. `cli_simple_compare`

Simple multi-run comparison output. Produces:

- `simple_compare_overall.png` for overall average latency, failure rate, mean
    total nodes, and max total nodes by run
- `simple_compare_phase.png` for per-phase average latency and failure rate by
    run

Unlike the single-run CLIs, this command writes to a caller-provided output
directory or a default comparison directory because it spans multiple run
folders.

### 5. `cli_cpu_drivers`

Load-balance diagnostic: median CPU of the *oldest* node versus *newer* nodes
per phase and role. If newer nodes sit near 0 while the oldest is saturated,
the symptom is a routing / load-balancing failure, not an undersized tier.

```python
# source/scripts/testing/analysis/cli_cpu_drivers.py
def load_balance_table(run: Run) -> list[dict]:
    out = []
    for phase in run.phases:
        for role in ("compute", "storage"):
            rows = [r for r in run.node_rows
                    if r["phase"] == phase.name and r["role"] == role
                    and r["cpu_percent"] not in ("", None)]
            if not rows:
                continue
            first_seen = {}
            for r in rows:
                sid = r["server_id"]
                we = float(r["window_end"])
                first_seen[sid] = min(first_seen.get(sid, we), we)
            oldest = min(first_seen.values())
            old_nodes = {sid for sid, t in first_seen.items() if t == oldest}
            old_cpu = _median(float(r["cpu_percent"]) for r in rows
                              if r["server_id"] in old_nodes)
            new_cpu = _median(float(r["cpu_percent"]) for r in rows
                              if r["server_id"] not in old_nodes)
            out.append({"phase": phase.name, "role": role,
                        "old_cpu_median": old_cpu, "new_cpu_median": new_cpu,
                        "nodes": len(first_seen)})
    return out
```

### 6. `cli_scale_down`

Reconstruct the scale-down predicate from the CSV and overlay controller log
events to show where/why the predicate was or wasn't armed.

The reconstruction must model the ceiling-skip path exactly as
`scaling_policy.py` does (see
[`../elasticy_manager/implementation/scale_down_instrumentation.md`](../elasticy_manager/implementation/scale_down_instrumentation.md)):
when `T_proc`/`T_db` exceeds the timeout ceiling the deque is **not**
updated, so a ceiling-skipped window must be excluded from hit counts â€”
otherwise the reconstructed `hits=n/N` drifts from the controller's.

```python
# source/scripts/testing/analysis/cli_scale_down.py
TAU_CPU_DOWN, TAU_PROC_DOWN_MS = 65.0, 5.0           # mirror scaling_config defaults
TAU_STORAGE_CPU_DOWN, TAU_DB_DOWN_MS = 65.0, 100.0
SCALE_DOWN_PROC_TIMEOUT_CEILING_MS = 5000.0          # mirror scaling_config
SCALE_DOWN_DB_TIMEOUT_CEILING_MS   = 5000.0


def predicate_timeline(run: Run) -> list[dict]:
    rows = []
    for r in run.domain_rows:
        cpu   = float(r["median_cpu_percent"] or 0)
        proc  = float(r["median_time_proc_ms"] or 0)
        stcpu = float(r["median_storage_cpu_percent"] or 0)
        tdb   = float(r["median_time_db_ms"] or 0)
        ceiling_skip_compute = proc > SCALE_DOWN_PROC_TIMEOUT_CEILING_MS
        ceiling_skip_storage = tdb  > SCALE_DOWN_DB_TIMEOUT_CEILING_MS
        rows.append({
            "phase": r["phase"], "network_id": r["network_id"],
            "t": float(r["window_end"]) - run.t0,
            "ceiling_skip_compute": ceiling_skip_compute,
            "ceiling_skip_storage": ceiling_skip_storage,
            "compute_cpu_below":  cpu  < TAU_CPU_DOWN,
            "compute_proc_below": proc < TAU_PROC_DOWN_MS,
            "compute_below":      cpu  < TAU_CPU_DOWN  and proc < TAU_PROC_DOWN_MS,
            "storage_cpu_below":  stcpu < TAU_STORAGE_CPU_DOWN,
            "storage_db_below":   tdb   < TAU_DB_DOWN_MS,
            "storage_below":      stcpu < TAU_STORAGE_CPU_DOWN and tdb < TAU_DB_DOWN_MS,
        })
    return rows


def unreachable_report(timeline: list[dict]) -> dict:
    """Per phase, count windows where each half of the AND failed.

    Ceiling-skipped windows are excluded from the per-tier counts and
    reported under a separate ``*_ceiling_skip`` key.
    """
    from collections import defaultdict
    by_phase = defaultdict(lambda: defaultdict(int))
    for r in timeline:
        by_phase[r["phase"]]["n"] += 1
        if r["ceiling_skip_compute"]:
            by_phase[r["phase"]]["compute_ceiling_skip"] += 1
        else:
            for k in ("compute_cpu_below", "compute_proc_below"):
                if r[k]:
                    by_phase[r["phase"]][k] += 1
        if r["ceiling_skip_storage"]:
            by_phase[r["phase"]]["storage_ceiling_skip"] += 1
        else:
            for k in ("storage_cpu_below", "storage_db_below"):
                if r[k]:
                    by_phase[r["phase"]][k] += 1
    return dict(by_phase)
```

### 7. `cli_tdb_drivers`

Closed-form OLS regression (no numpy) of
`T_db_write ~ a + bÂ·storage_count + cÂ·cross_region_ratio`.

```python
# source/scripts/testing/analysis/cli_tdb_drivers.py
def ols(X: list[list[float]], y: list[float]) -> tuple[list[float], float]:
    """Returns (coefficients, R^2). X includes the constant-1 column."""
    n, k = len(X), len(X[0])
    XtX = [[sum(X[i][a]*X[i][b] for i in range(n)) for b in range(k)] for a in range(k)]
    Xty = [sum(X[i][a]*y[i] for i in range(n)) for a in range(k)]
    beta = _solve(XtX, Xty)  # Gaussian elimination
    y_hat = [sum(beta[a]*X[i][a] for a in range(k)) for i in range(n)]
    ss_res = sum((y[i]-y_hat[i])**2 for i in range(n))
    ybar = sum(y) / n
    ss_tot = sum((yi - ybar)**2 for yi in y) or 1.0
    return beta, 1.0 - ss_res / ss_tot


def fit_tdb_write_model(run: Run) -> dict:
    phase_by_name = {p.name: p for p in run.phases}
    X, y = [], []
    for r in run.domain_rows:
        p = phase_by_name.get(r["phase"])
        if not p or not r.get("avg_time_db_write_ms"):
            continue
        X.append([1.0, float(r["storage_count"]), p.cross_region_ratio])
        y.append(float(r["avg_time_db_write_ms"]))
    beta, r2 = ols(X, y)
    return {"intercept": beta[0], "b_storage_count": beta[1],
            "b_cross_region": beta[2], "r2": r2, "n": len(y)}
```

If `b_storage_count > 0` with meaningful RÂ², **adding storage nodes makes
writes slower** â€” this is the primary falsifiable claim of the parent
investigation.

---

## CLI UX

```
python -m source.scripts.testing.analysis.cli_overview      --run-dir <dir>
python -m source.scripts.testing.analysis.cli_cpu_drivers   --run-dir <dir>
python -m source.scripts.testing.analysis.cli_scale_down    --run-dir <dir>
python -m source.scripts.testing.analysis.cli_tdb_drivers   --run-dir <dir>
```

Each writes under `<run-dir>/analysis/`:

- `overview.png`, `cpu_drivers.png`, `scale_down.png`, `tdb_drivers.png`
- `summary.md` (appended by every CLI â€” one section per tool)

## Acceptance

1. Fresh run produces `per_node_stats.csv` with row count â‰ˆ Î£(containers) Ã— windows.
2. `cli_overview` on that run produces `<dir>/analysis/overview.png` without
   errors.
3. `cli_scale_down` `unreachable_report` prints, per phase, which half of the
   AND predicate was never satisfied (explains silent scale-down).
4. `cli_tdb_drivers` prints a table like
   `T_db_write â‰ˆ 12.4 + 38.1Â·storage_count + 95.2Â·cross_region_ratio  (RÂ²=0.71)`.
5. Running any CLI against the old run `20260420_184217` (no per-node CSV, no
   `avg_time_db_*` columns) prints warnings and skips the affected subplots
   instead of crashing.

## Risks

| Risk | Mitigation |
|---|---|
| `per_node_stats.csv` grows large on long runs | 10 nodes Ã— 360 windows Ã— 10 s window â‰ˆ 3600 rows/run â€” trivial. Split per phase later if > 50 MB. |
| Log grammar drift | Regex contract owned by [`../elasticy_manager/implementation/scale_down_instrumentation.md`](../elasticy_manager/implementation/scale_down_instrumentation.md); any change requires a sync edit here. |
| Missing columns on old runs | All field accesses use `.get(...)` with defaults; subplot functions check for presence and `warnings.warn()` when skipping. |
| Thresholds hard-coded in `cli_scale_down` | Mirrors `scaling_config.py` defaults; if scaling thresholds are retuned, update the constants in one place (documented at top of file). |

## Overview file changes â€” `testing_overview.md`

The following edits to [`./testing_overview.md`](testing_overview.md) are
required so the overview reflects the new artifact set and analysis surface.

### 1. Architecture diagram â€” add analysis branch

Extend the experiment data-flow diagram with a parallel branch showing the
new outputs:

```
  traffic_generator.py              ...
         â”‚
         â–¼
    metrics/client_requests.csv
  metrics/resource_stats.csv          â†â”€â”€ domain windowed stats (existing + new columns)
  metrics/per_node_stats.csv          â†â”€â”€ per-container windowed stats (NEW)
  metrics/controller_lan{1,2}.log     â†â”€â”€ includes scale-down DEBUG lines
         â”‚
         â–¼
  python -m source.scripts.testing.analysis.cli_<name> --run-dir <dir>
         â”‚
         â–¼
  <run-dir>/analysis/
    â”œâ”€â”€ overview.png
    â”œâ”€â”€ cpu_drivers.png
    â”œâ”€â”€ scale_down.png
    â”œâ”€â”€ tdb_drivers.png
    â””â”€â”€ summary.md
```

### 2. New Components section â€” "5. Run Analysis Toolchain"

Append a subsection after **"4. Request Trace"**:

```markdown
### 5. Run Analysis Toolchain â€” [`analysis_toolchain.md`](analysis_toolchain.md)

Offline package that ingests a run directory and emits phase-aligned plots and
diagnostic tables. Read-only â€” does not modify telemetry, scaling, or the
traffic generator.

| CLI | Purpose |
|---|---|
| `cli_overview` | One-page dashboard: request rate, CPU, T_proc, T_db (read/write stacked), node counts with phase shading and elasticity-event overlays |
| `cli_cpu_drivers` | Per-node CPU vs request-count; old-vs-new node CPU table to detect load-balance failures |
| `cli_scale_down` | Reconstructs the scale-down predicate from CSV and cross-checks against controller log lines |
| `cli_tdb_drivers` | OLS regression `T_db_write ~ a + bÂ·storage_count + cÂ·cross_region_ratio` to falsify the "more storage = slower writes" hypothesis |

Consumes `resource_stats.csv` (domain), `per_node_stats.csv` (per-container),
`client_requests.csv`, `phases_snapshot.json`, and the controller log files.
Phase-scoped request analysis is derived from the aggregate CSV via its
`phase` column. Missing fields on older runs degrade gracefully with warnings.
```

### 3. Execution Order â€” add a post-run step

Add a step 5 under the existing command block:

```bash
# 5. Generate analysis artifacts from the run directory
python -m source.scripts.testing.analysis.cli_overview    --run-dir metrics/<ts>
python -m source.scripts.testing.analysis.cli_cpu_drivers --run-dir metrics/<ts>
python -m source.scripts.testing.analysis.cli_scale_down  --run-dir metrics/<ts>
python -m source.scripts.testing.analysis.cli_tdb_drivers --run-dir metrics/<ts>
```

### 4. File Layout â€” add the analysis package and new CSV

Replace the `docs/operation/testing/` file layout block with the addition of
this plan, and append a new block for the source-level layout:

```
source/scripts/testing/
â”œâ”€â”€ collect_resource_stats.py    â† now also writes per_node_stats.csv
â””â”€â”€ analysis/                    â† NEW â€” offline analysis package
    â”œâ”€â”€ __init__.py
    â”œâ”€â”€ loader.py
    â”œâ”€â”€ events.py
    â”œâ”€â”€ phase_window.py
    â”œâ”€â”€ plots.py
    â”œâ”€â”€ cli_overview.py
    â”œâ”€â”€ cli_cpu_drivers.py
    â”œâ”€â”€ cli_scale_down.py
    â”œâ”€â”€ cli_tdb_drivers.py
    â””â”€â”€ requirements.txt
```

Under `docs/operation/testing/` add the new reference entry:

```
â”œâ”€â”€ analysis_toolchain.md            â† this document
```

## Cross-references

- Umbrella investigation: [`../elasticy_manager/implementation/plans/metric_drivers_investigation_plan.md`](../elasticy_manager/implementation/plans/metric_drivers_investigation_plan.md)
- Produces new fields consumed here: [`../telemetry/implementation/db_timing_decomposition.md`](../telemetry/implementation/db_timing_decomposition.md)
- Produces log lines consumed here: [`../elasticy_manager/implementation/scale_down_instrumentation.md`](../elasticy_manager/implementation/scale_down_instrumentation.md)
