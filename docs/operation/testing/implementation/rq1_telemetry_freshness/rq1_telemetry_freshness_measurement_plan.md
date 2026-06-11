# RQ1 Telemetry Freshness Measurement — Implementation Plan

> **Status:** Approved · **Date:** 2026-06-11
> **Parent:** `tese/miscelineous/system_to_thesis_map_rq_v2.md` § RQ1
> **Mode:** Edge Planning Architect — plan only, no implementation until approved.

## Objective

Instrument the system so that RQ1's four primary measurements can be extracted
from every experiment run artifact and rendered as graphs/tables under
`<run_dir>/analysis/`.

| Measurement                  | Output                                                                         |
| ---------------------------- | ------------------------------------------------------------------------------ |
| Decision staleness           | Time-series plot + per-phase table                                             |
| Reaction latency             | Gantt-style breakdown + per-phase table                                        |
| Transient service quality    | Already covered by `cli_simple_run`, `cli_overview`, `cli_phase_summary` |
| Control-plane overhead       | Time-series plot of controller CPU/RAM                                         |
| False positive/negative rate | Per-phase classification table                                                 |

---

## Phase 1 — Timing Instrumentation (consumed_at)

**Goal:** Record when the controller consumes each telemetry summary so
staleness = `consumed_at_mono - window_end` can be computed post-hoc.

### Step 1.1 — Add `consumed_at_mono` to CoordinatorStatePublisher

**File:** `source/sdn_controller/selective_sync/state_publisher.py`

- Add required `consumed_at_mono: float` parameter to `publish()`.
- Always include it in the JSON payload.
- Update both callers (`main_n1.py`, `main_n2.py`) to pass it.

```python
# state_publisher.py — signature change
def publish(self, network_id: str, window_end: float,
            snapshot: dict[str, Tier1OwnerState],
            consumed_at_mono: float) -> None:
    ...
    payload = {
        "network_id": network_id,
        "window_end": window_end,
        "consumed_at_mono": consumed_at_mono,
        "owners": {k: asdict(v) for k, v in snapshot.items()},
    }
```

### Step 1.2 — Record consumed_at_mono in the mediator

**File:** `source/sdn_controller/main_n2.py` (and mirror in `main_n1.py`)

- At the top of `_on_telemetry_update`, record `time.monotonic()`.
- Pass it to `_coordinator_state_publisher.publish()`.

```python
# main_n2.py — in _on_telemetry_update, before the early-returns
def _on_telemetry_update(self, summary: TelemetrySummary) -> None:
    consumed_at_mono = time.monotonic()
  
    if summary.network_id != self._lan_id:
        ...
    ...
    # Existing publish call, add the new argument:
    self._coordinator_state_publisher.publish(
        summary.network_id,
        summary.window_end,
        self._selective_sync_coordinator.snapshot(),
        consumed_at_mono=consumed_at_mono,   # ← NEW
    )
```

- **Important:** Record `consumed_at_mono` BEFORE the `network_id` early-return
  guard, or the peer-LAN summaries won't get timestamps (and we want both).

### Step 1.3 — Merge consumed_at_mono into resource_stats_debug.csv

**File:** `source/scripts/testing/collect_resource_stats.py`

- In the debug CSV fieldnames, add `"consumed_at_mono"`.
- When a coordinator-state frame carries `consumed_at_mono`, include it in
  the debug row.

```python
# collect_resource_stats.py
DEBUG_FIELDNAMES = [
    ...
    "avg_time_db_cmd_count",
    "consumed_at_mono",          # ← NEW (last before Tier 1 columns)
] + TIER1_ALL_COLUMNS
```

- In the writer loop, extract from the coordinator frame:

```python
debug_row["consumed_at_mono"] = coord_frame.get("consumed_at_mono", "")
```

(The `.get` with default keeps the collector robust against old controllers
that haven't been updated yet, but after Phase 1 deployment the field is
always present.)

### Step 1.4 — Verify

- Run a short experiment, only with user permission.
- Confirm `resource_stats_debug.csv` has non-empty `consumed_at_mono` values.
- Confirm staleness = `consumed_at_mono - window_end` yields sane values
  (sub-second for push mode).

---

## Phase 2+3 — Polling Mechanism (Aggregator Cache + PollingTelemetrySource)

> **Documentation:** `docs/operation/telemetry/controller_side/controller_telemetry_consumer.md` § 4 & § 10;
> `docs/operation/telemetry/aggregation_publication/aggregator.md` § 13;
> `docs/operation/telemetry/telemetry_overview.md`

**Summary of what changes:**

| Component | Change |
|---|---|
| Aggregator | In-memory `_latest_summary` dict + stdlib HTTP server on port `5558` (daemon thread). Always publishes via ZMQ AND caches for HTTP — identical behavior across push/poll conditions. |
| Controller | New `PollingTelemetrySource` (implements `TelemetryEventSource` ABC). Deduplicates by `window_end` so `_on_telemetry_update` is only called when a genuinely new summary arrives. |
| Controller wiring | `TELEMETRY_SOURCE=zmq\|poll` env var + `POLL_INTERVAL_S` env var. ZMQ `tcp://` endpoints are converted to `http://` URLs (port `5556` → `5558`). |

**Key design decisions (see sub-plan for full rationale):**
1. Aggregator remains the **sole source** — no intermediate DB (avoids confounding write latency).
2. **HTTP** (stdlib) is the polling transport — simplest, no new dependencies, same hop count as push.
3. **Dedup by `window_end`** — prevents re-triggering controller logic on duplicate reads when poll interval < window size.
4. **ZMQ PUB always runs** — aggregator behavior is identical across conditions; only the controller-side source changes.

---

## Phase 4 — RQ1 Analysis CLIs

**Goal:** Produce graphs and tables from run artifacts that answer RQ1.

### Step 4.1 — New CLI: `cli_rq1_timings`

**File:** `source/scripts/testing/analysis/cli_rq1_timings.py` (new)

**Inputs:**

- `resource_stats_debug.csv` (has `window_end`, `consumed_at_mono`)
- Controller logs via `events.py` (has `alert`, `spawn_start`, `spawn_done`)
- `phases_snapshot.json` (phase boundaries)

**Outputs** (all in `<run_dir>/analysis/`):

| File                         | Content                                                                                                                                                |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `rq1_staleness.png`        | Time-series: staleness (s) over experiment time, one line per LAN, phase-shaded background                                                             |
| `rq1_staleness.csv`        | Per-phase: mean, p50, p95, max staleness                                                                                                               |
| `rq1_reaction_latency.png` | Two panels: (a) stacked bar per scaling event showing breach→alert→spawn_start→spawn_done segments; (b) per-phase table of mean/p95 of each segment |
| `rq1_reaction_latency.csv` | One row per scaling event: event_ts, lan, tier, staleness_at_event_s, queue_delay_s, provision_time_s, total_reaction_s                                |

**Computation:**

- Staleness: `consumed_at_mono - window_end` for each debug row. Plot against
  `window_end` aligned to t0.
- Reaction latency segments:
  - `breach_to_alert_s`: `alert_ts - window_end_of_triggering_summary` (join
    alert events to the most recent debug row before the alert)
  - `queue_delay_s`: `spawn_start_ts - alert_ts`
  - `provision_time_s`: `spawn_done_ts - spawn_start_ts`
  - `total_reaction_s`: `spawn_done_ts - window_end_of_triggering_summary`

### Step 4.2 — New CLI: `cli_rq1_overhead`

**File:** `source/scripts/testing/analysis/cli_rq1_overhead.py` (new)

**Inputs:** `controller_stats.csv` (produced by Phase 5 sampler)

**Outputs:**

| File                 | Content                                                                                      |
| -------------------- | -------------------------------------------------------------------------------------------- |
| `rq1_overhead.png` | Two panels: controller CPU% and RSS (MB) over time, phase-shaded, with scaling event markers |
| `rq1_overhead.csv` | Per-phase: mean/p95 CPU%, mean/p95 RSS MB                                                    |

### Step 4.3 — Register CLIs in loader/package

- Add imports in `analysis/__init__.py` if needed (currently just a marker).
- Document usage in `analysis_toolchain.md`.

---

## Phase 5 — Controller Overhead Sampler

**Goal:** Periodically sample controller container CPU/RAM during experiments.

### Step 5.1 — New script: `sample_controller_stats.py`

**File:** `source/scripts/testing/sample_controller_stats.py` (new)

- Runs as a background process alongside `collect_resource_stats.py`.
- Every `SAMPLE_INTERVAL_S` (default 5s), runs:
  ```
  docker stats --no-stream --format "{{.Name}},{{.CPUPerc}},{{.MemUsage}}" <controller_container>
  ```
- Parses output, writes to `<output_dir>/controller_stats.csv`.
- Handles SIGTERM for graceful shutdown (same pattern as
  `collect_resource_stats.py`).

**CSV columns:**

```
timestamp, container, cpu_percent, mem_usage_mb
```

### Step 5.2 — Integrate into run_experiment.sh

**File:** `source/scripts/testing/run_experiment.sh`

- Start `sample_controller_stats.py` after the controller is ready, before
  traffic starts.
- Kill it (SIGTERM) after traffic generator finishes, same as
  `collect_resource_stats.py`.

---

## Phase 6 — False Positive/Negative Classification

**Goal:** Classify each scaling decision as correct, premature, delayed, or
missed by correlating against the workload phase structure.

### Step 6.1 — Extend `cli_scale_down.py` or new CLI

**File:** Either extend `source/scripts/testing/analysis/cli_scale_down.py`
or create `cli_rq1_decision_quality.py` (new).

**Logic:**

- A scale-up during a high-load phase is **correct**.
- A scale-up during a low-load phase or transition is **premature** (noise).
- A scale-up that happens >N seconds after load increase is **delayed** (stale).
- No scale-up during a sustained high-load phase is **missed**.

**Outputs:**

| File                         | Content                                                                |
| ---------------------------- | ---------------------------------------------------------------------- |
| `rq1_decision_quality.csv` | Per scaling event: ts, lan, tier, phase, classification, justification |
| `rq1_decision_quality.png` | Confusion-style matrix: rows=phases, cols=classification, cell=count   |

**Phase load classification:** derive from `phases.json` phase names (e.g.,
`high_load_n1` → high; `baseline` → low; `transition` → transition).

### Step 6.2 — Document classification rules

- Add a section to `analysis_toolchain.md` defining the classification
  heuristics so they're reproducible.

---

## File Map Summary

| Action   | Path                                                                                              | Phase |
| -------- | ------------------------------------------------------------------------------------------------- | ----- |
| Edit     | `source/sdn_controller/selective_sync/state_publisher.py`                                       | 1     |
| Edit     | `source/sdn_controller/main_n2.py`                                                              | 1     |
| Edit     | `source/sdn_controller/main_n1.py`                                                              | 1     |
| Edit     | `source/scripts/testing/collect_resource_stats.py`                                              | 1     |
| —        | **Phase 2+3 files — see telemetry docs**                                                         | 2,3   |
| New      | `source/scripts/testing/analysis/cli_rq1_timings.py`                                            | 4     |
| New      | `source/scripts/testing/analysis/cli_rq1_overhead.py`                                           | 4     |
| New      | `source/scripts/testing/sample_controller_stats.py`                                             | 5     |
| Edit     | `source/scripts/testing/run_experiment.sh`                                                      | 5     |
| New/Edit | `source/scripts/testing/analysis/cli_rq1_decision_quality.py` (or extend `cli_scale_down.py`) | 6     |
| Edit     | `docs/operation/testing/analysis_toolchain.md`                                                  | 4,6   |

---

## Dependencies Between Phases

```
Phase 1 (timing instrumentation)
  └─→ Phase 4 (analysis CLIs consume consumed_at_mono)

Phase 2+3 (polling mechanism — see telemetry docs)
  ├─→ Phase 2 (aggregator HTTP endpoint) ──→ Phase 3 (polling source)
  └─→ Enables evaluation conditions W*-Poll-*

Phase 5 (overhead sampler) — independent, can run anytime

Phase 6 (decision quality) — depends on Phase 1 + existing events.py
```

**Phases 1 and 2 can run in parallel.** Phase 5 is fully independent.
Phases 3, 4, 6 depend on earlier infrastructure.

---

## Edge-Specific Considerations

- **Staleness vs monotonic clocks:** `window_end` uses `time.time()` (wall
  clock), `consumed_at_mono` uses `time.monotonic()`. These are NOT
  comparable across the network. The aggregator and controller run on the
  same Docker host in our topology, so clock skew is negligible. Document
  this assumption.
- **Polling mechanism edge considerations:** See
  `docs/operation/telemetry/aggregation_publication/aggregator.md` § 13 for HTTP
  server threading, polling overhead, cache-miss-on-startup, and aggregator
  restart behavior.

---

## Documentation Updates

| File                                               | Update                                                                                                                                |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `docs/operation/testing/analysis_toolchain.md`   | Add entries for `cli_rq1_timings`, `cli_rq1_overhead`, `cli_rq1_decision_quality`; add `consumed_at_mono` to debug CSV schema |
| `docs/operation/telemetry/telemetry_overview.md` | Document polling source and aggregator HTTP cache endpoint |
| `docs/operation/testing/testing_overview.md`     | Add `controller_stats.csv` artifact and `sample_controller_stats.py`                                                              |
