# RQ1 Analysis Tooling — Complementary Implementation Plan

> **Status:** Implemented (with corrections) · **Date:** 2026-06-21
> **Parent:** `rq1_telemetry_freshness_measurement_plan.md` § Phase 4, 5, 6
> **Scope:** Build the three missing CLIs + one sampler script to close RQ1 measurement gaps.
> All tooling built and verified via `rq1_instrumentation_verification` experiment (v4).
> Two post-implementation bugs found and fixed (LAN mismatch, timezone shift).
> Staleness measurement reframed: `consumed_at − window_end` ≈ 0s in all modes
> because `/latest_summary` returns freshest window; real polling cost measured
> via reaction latency (Measurement #2).

## Objective

Three CLIs and one sampler script are needed to produce all five RQ1
measurements. Phase 1 (`consumed_at` timing) and Phases 2+3 (polling
mechanism) are already implemented. This plan covers the remaining
post-run analysis tooling.

| Measurement                 | What exists                                                                                                                                           | What's missing                                                                         |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| Decision staleness          | Source data:`consumed_at`, `window_end` in `resource_stats_debug.csv`. Note: `consumed_at − window_end` ≈ 0s in all modes (push and poll) because `/latest_summary` returns freshest window. See §Post-Implementation Corrections. | `cli/timings.py` — compute & plot (staleness is now an informational metric; real polling cost is measured via reaction latency) |
| Reaction latency            | Source data:`resource_stats_debug.csv` (domain metrics), `controller_env_snapshot.env` (thresholds), `elasticity_events.csv` (spawn timestamps) | `cli/timings.py` — breach detection from telemetry data using degradation_score |
| Transient service quality   | `cli_simple_run`, `cli_overview`, `cli_phase_summary`                                                                                           | Nothing — fully covered                                                               |
| Control-plane overhead      | Nothing                                                                                                                                               | `sample_controller_stats.py` → `controller_stats.csv` → `cli/overhead.py`  |
| Scaling outcome description | `elasticity_events.csv`, `phases_snapshot.json`                                                                                                   | `cli/decision_quality.py` — 2×2 descriptive labels                             |

---

## Implementation Order

```
Phase 5 (controller_stats.csv)
  └─→ Phase 4b (cli/overhead.py) — needs controller_stats.csv

Phase 4a (cli/timings.py) — independent; reads existing artifacts
Phase 6 (cli_rq1_decision_quality.py) — independent; reads existing artifacts
```

**Phase 5, 4a, and 6 can proceed in parallel.** Only 4b depends on 5.

---

## Phase 4a — `cli_rq1_timings.py` (Decision Staleness + Reaction Latency)

**File:** `source/scripts/testing/analysis/rq1/cli_rq1_timings.py` (new)

This CLI computes two of the five RQ1 measurements from artifacts that already
exist in every run folder.

### Inputs

| Artifact                     | Field                                                                            | Used for                                |
| ---------------------------- | -------------------------------------------------------------------------------- | --------------------------------------- |
| `resource_stats_debug.csv` | `window_end`, `consumed_at`, `network_id`                                  | Staleness =`consumed_at - window_end` |
| `elasticity_events.csv`    | `ts`, `kind` (`alert`, `spawn_start`, `spawn_done`), `tier`, `lan` | Reaction latency segments               |
| `phases_snapshot.json`     | Phase boundaries                                                                 | Phase shading and per-phase tables      |

All three are loaded by the existing `loader.py` → `Run` dataclass
(`debug_rows`, `events`, `phases`).

### Outputs (all under `<run_dir>/analysis/`)

| File                         | Content                                                                                                                                                     |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `rq1_staleness.png`        | Time-series: staleness (s) per LAN, phase-shaded background                                                                                                 |
| `rq1_staleness.csv`        | Per-phase: mean, p50, p95, max staleness; per-row: network_id, window_end, consumed_at, staleness_s                                                         |
| `rq1_reaction_latency.png` | Two panels: (a) stacked bar per scaling event: breach→spawn_start, spawn_start→spawn_done; (b) per-phase table of mean/p95 of each segment                |
| `rq1_reaction_latency.csv` | Per event: ts, lan, tier, breach_window_end, breach_detection_s (window_end → spawn_start), provision_time_s (spawn_start → spawn_done), total_reaction_s |

### Shared helper: `rq1/breach_detector.py`

Before either `cli_rq1_timings.py` or `cli_rq1_decision_quality.py` can
work, they need a shared module that replicates the controller's
degradation score computation. This ensures both CLIs detect breaches the
same way — and the same way the controller does.

```python
# source/scripts/testing/analysis/rq1/breach_detector.py
"""Shared breach detection: replicates the controller's degradation_score
and threshold logic from telemetry data.

Used by both cli_rq1_timings.py (reaction latency) and
cli_rq1_decision_quality.py (scaling outcome description).
"""


def degradation_score(cpu: float, latency: float,
                      w_cpu: float, w_lat: float,
                      cpu_floor: float, cpu_span: float,
                      lat_floor: float, lat_span: float) -> float:
    """Weighted degradation score in [0, w_cpu + w_lat].

    Exact replica of ScalingPolicy.degradation_score().
    Both components saturate at 1.0.
    """
    if cpu_span:
        cpu_component = min(1.0, max(0.0, cpu - cpu_floor) / cpu_span)
    else:
        cpu_component = 0.0
    if lat_span:
        lat_component = min(1.0, max(0.0, latency - lat_floor) / lat_span)
    else:
        lat_component = 0.0
    return w_cpu * cpu_component + w_lat * lat_component


def storage_latency_signal(avg_time_db_ms: float,
                           p95_time_db_ms: float) -> float:
    """Tail-aware DB latency signal. Replicates ScalingPolicy method."""
    return max(avg_time_db_ms, p95_time_db_ms)


def load_thresholds(env_snapshot: dict[str, str]) -> dict:
    """Extract scale-up thresholds from controller_env_snapshot.env.

    Returns a dict with keys matching scaling_config.py names.
    Falls back to scaling_config.py defaults (not the override file).
    """
    def _f(key: str, default: float) -> float:
        try:
            return float(env_snapshot.get(key, str(default)))
        except (ValueError, TypeError):
            return default

    return {
        # Compute weights — defaults from scaling_config.py
        "W_CPU":                          _f("SCALEUP_W_CPU", 0.40),
        "W_T_PROC":                       _f("SCALEUP_W_T_PROC", 0.60),
        "CPU_FLOOR":                      _f("SCALEUP_CPU_FLOOR", 5.0),
        "CPU_SPAN":                       _f("SCALEUP_CPU_SPAN", 10.0),
        "T_PROC_FLOOR":                   _f("SCALEUP_T_PROC_FLOOR", 20.0),
        "T_PROC_SPAN":                    _f("SCALEUP_T_PROC_SPAN", 80.0),
        "COMPUTE_BASE_THRESHOLD":         _f("SCALEUP_COMPUTE_BASE_THRESHOLD", 0.45),
        "COMPUTE_THRESHOLD_INCREMENT":    _f("SCALEUP_COMPUTE_THRESHOLD_INCREMENT", 0.10),
        "COMPUTE_MAX_THRESHOLD":          _f("SCALEUP_COMPUTE_MAX_THRESHOLD", 0.85),
        "COMPUTE_COOLDOWN_S":             _f("SCALEUP_COMPUTE_COOLDOWN_S", 45.0),
        "COMPUTE_PEER_RELIEF":            _f("SCALEUP_COMPUTE_PEER_RELIEF", 0.03),
        "COMPUTE_PEER_HEALTH_THRESHOLD":  _f("SCALEUP_COMPUTE_PEER_HEALTH_THRESHOLD", 0.35),
        # Storage weights — defaults from scaling_config.py
        "W_STORAGE_CPU":                  _f("SCALEUP_W_STORAGE_CPU", 0.70),
        "W_T_DB":                         _f("SCALEUP_W_T_DB", 0.30),
        "STORAGE_CPU_FLOOR":              _f("SCALEUP_STORAGE_CPU_FLOOR", 5.0),
        "STORAGE_CPU_SPAN":               _f("SCALEUP_STORAGE_CPU_SPAN", 10.0),
        "T_DB_FLOOR":                     _f("SCALEUP_T_DB_FLOOR", 150.0),
        "T_DB_SPAN":                      _f("SCALEUP_T_DB_SPAN", 600.0),
        "STORAGE_BASE_THRESHOLD":         _f("SCALEUP_STORAGE_BASE_THRESHOLD", 0.25),
        "STORAGE_THRESHOLD_INCREMENT":    _f("SCALEUP_STORAGE_THRESHOLD_INCREMENT", 0.10),
        "STORAGE_MIN_INCREMENT":          _f("SCALEUP_STORAGE_MIN_INCREMENT", 0.05),
        "STORAGE_MAX_THRESHOLD":          _f("SCALEUP_STORAGE_MAX_THRESHOLD", 0.55),
        "STORAGE_COOLDOWN_S":             _f("SCALEUP_STORAGE_COOLDOWN_S", 120.0),
    }


def _effective_compute_threshold(thresholds: dict, node_count: int,
                                  peer_score: float | None) -> float:
    """Compute effective threshold with dynamic count + peer relief."""
    base = thresholds["COMPUTE_BASE_THRESHOLD"]
    inc = thresholds["COMPUTE_THRESHOLD_INCREMENT"]
    cap = thresholds["COMPUTE_MAX_THRESHOLD"]
    dynamic_part = node_count * inc

    peer_relief = 0.0
    if (peer_score is not None
            and peer_score <= thresholds["COMPUTE_PEER_HEALTH_THRESHOLD"]):
        peer_relief = thresholds["COMPUTE_PEER_RELIEF"]

    return min(base + dynamic_part + peer_relief, cap)


def _effective_storage_threshold(thresholds: dict, node_count: int) -> float:
    """Compute effective storage threshold with diminishing increments.

    Replicates the controller's:
      cumulative = Σ max(increment × 0.5ⁱ, min_increment)
    """
    base = thresholds["STORAGE_BASE_THRESHOLD"]
    inc = thresholds["STORAGE_THRESHOLD_INCREMENT"]
    min_inc = thresholds["STORAGE_MIN_INCREMENT"]
    cap = thresholds["STORAGE_MAX_THRESHOLD"]

    cumulative = sum(
        max(inc * 0.5 ** i, min_inc)
        for i in range(node_count)
    )
    return min(base + cumulative, cap)


def _find_peer_row(window_end: float,
                   peer_rows: list[dict]) -> dict | None:
    """Return the peer-LAN debug row closest to (and ≤) window_end."""
    best = None
    for row in peer_rows:
        w = float(row.get("window_end", 0))
        if w <= window_end and (best is None
                                or w > float(best.get("window_end", 0))):
            best = row
    return best


def detect_breaches(
    debug_rows: list[dict],
    thresholds: dict,
) -> list[dict]:
    """Detect trigger events accounting for dynamic threshold, peer
    relief, and cooldown.

    Returns trigger events only — windows suppressed by cooldown or
    peer relief are excluded.  Each trigger:
      {network_id, window_end, tier, score, threshold,
       peer_relief, dynamic_count}
    """
    triggers = []
    sorted_rows = sorted(debug_rows,
                         key=lambda r: float(r.get("window_end", 0)))

    # Index peer rows by LAN for peer-relief lookups
    by_lan: dict[str, list[dict]] = {}
    for row in sorted_rows:
        by_lan.setdefault(row.get("network_id", ""), []).append(row)

    compute_count = 0
    storage_count = 0
    last_compute_trigger = -999999.0
    last_storage_trigger = -999999.0

    for row in sorted_rows:
        network_id = row.get("network_id", "")
        window_end = float(row.get("window_end", 0))
        peer_lan = "lan2" if network_id == "lan1" else "lan1"

        avg_cpu = float(row.get("average_cpu_percent", 0))
        avg_proc = float(row.get("avg_time_proc_ms", 0))
        avg_storage_cpu = float(row.get("avg_storage_cpu_percent", 0))
        avg_db = float(row.get("avg_time_db_ms", 0))
        p95_db = float(row.get("p95_time_db_ms", 0))

        # ── Compute breach ──────────────────────────────────────────
        compute_score = degradation_score(
            avg_cpu, avg_proc,
            thresholds["W_CPU"], thresholds["W_T_PROC"],
            thresholds["CPU_FLOOR"], thresholds["CPU_SPAN"],
            thresholds["T_PROC_FLOOR"], thresholds["T_PROC_SPAN"],
        )

        # Peer relief: evaluate peer LAN health at same window_end
        peer_score = None
        peer_row = _find_peer_row(window_end, by_lan.get(peer_lan, []))
        if peer_row:
            peer_score = degradation_score(
                float(peer_row.get("average_cpu_percent", 0)),
                float(peer_row.get("avg_time_proc_ms", 0)),
                thresholds["W_CPU"], thresholds["W_T_PROC"],
                thresholds["CPU_FLOOR"], thresholds["CPU_SPAN"],
                thresholds["T_PROC_FLOOR"], thresholds["T_PROC_SPAN"],
            )

        compute_threshold = _effective_compute_threshold(
            thresholds, compute_count, peer_score)

        cooldown_ok = (window_end - last_compute_trigger
                       >= thresholds["COMPUTE_COOLDOWN_S"])

        if compute_score >= compute_threshold and cooldown_ok:
            peer_relief = 0.0
            if (peer_score is not None
                    and peer_score <= thresholds["COMPUTE_PEER_HEALTH_THRESHOLD"]):
                peer_relief = thresholds["COMPUTE_PEER_RELIEF"]
            triggers.append({
                "network_id": network_id,
                "window_end": window_end,
                "tier": "compute",
                "score": round(compute_score, 4),
                "threshold": round(compute_threshold, 4),
                "peer_relief": peer_relief,
                "dynamic_count": compute_count,
            })
            compute_count += 1
            last_compute_trigger = window_end

        # ── Storage breach ─────────────────────────────────────────
        db_latency = storage_latency_signal(avg_db, p95_db)
        storage_score = degradation_score(
            avg_storage_cpu, db_latency,
            thresholds["W_STORAGE_CPU"], thresholds["W_T_DB"],
            thresholds["STORAGE_CPU_FLOOR"], thresholds["STORAGE_CPU_SPAN"],
            thresholds["T_DB_FLOOR"], thresholds["T_DB_SPAN"],
        )

        storage_threshold = _effective_storage_threshold(
            thresholds, storage_count)

        cooldown_ok = (window_end - last_storage_trigger
                       >= thresholds["STORAGE_COOLDOWN_S"])

        if storage_score >= storage_threshold and cooldown_ok:
            triggers.append({
                "network_id": network_id,
                "window_end": window_end,
                "tier": "storage",
                "score": round(storage_score, 4),
                "threshold": round(storage_threshold, 4),
                "peer_relief": 0.0,
                "dynamic_count": storage_count,
            })
            storage_count += 1
            last_storage_trigger = window_end

    return triggers
```

### Design notes (breach_detector)

- **Defaults match `scaling_config.py`**, not the override file. The
  override values are captured in `controller_env_snapshot.env` and take
  precedence at load time via `_f()`.
- **Storage threshold uses diminishing increments**: `Σ max(increment × 0.5ⁱ, min_increment)`. This exactly matches the controller.
- **Peer relief is compute-only**. Storage has no peer relief mechanism.
- **Cooldown is checked per-tier**. A trigger resets the cooldown clock
  for that tier only. Cooldown uses `window_end` deltas — equivalent to
  the controller's `time.monotonic()` deltas since both clocks advance
  at the same rate on the same host.
- **Not replicated by design**: busy flag, pending drain blocks, sliding
  window deque. These are controller-internal gating mechanisms, not the
  RQ1 variable under test (telemetry freshness).
- **Dual column-name support**: `_col(row, "average_cpu_percent", "median_cpu_percent")` handles both `domain_rows` and `debug_rows`
  naming conventions — domain CSV uses `average_*`/`avg_*` prefixes,
  debug CSV uses `median_*` prefixes and `t_db_p95_ms_owner_lan` for
  p95 DB latency. The breach detector accepts either row source.

### Computation: staleness

```python
def compute_staleness(debug_rows: list[dict], origin_ts: float) -> list[dict]:
    """For each debug row: staleness_s = consumed_at - window_end."""
    results = []
    for row in debug_rows:
        window_end = safe_float(row.get("window_end"))
        consumed_at = safe_float(row.get("consumed_at"))
        if window_end <= 0 or consumed_at <= 0:
            continue
        results.append({
            "network_id": row.get("network_id", ""),
            "window_end": window_end,
            "consumed_at": consumed_at,
            "staleness_s": max(0.0, consumed_at - window_end),
            "t_s": max(0.0, window_end - origin_ts),
        })
    return results
```

### Computation: reaction latency

The CLI independently detects when a breach occurs by applying the same
`degradation_score` formula and thresholds the controller used. It does
**not** rely on controller log alert events for breach detection. The
start timestamp is the `window_end` of the first telemetry window where
the score exceeds the threshold. The end timestamp is `spawn_done_ts`
from `elasticity_events.csv`.

```
For each (network_id, window_end) row, in time order:
  1. Load thresholds from controller_env_snapshot.env
  2. Compute compute_score = degradation_score(
       average_cpu_percent, avg_time_proc_ms, ...)
  3. Compute storage_score = degradation_score(
       avg_storage_cpu_percent, max(avg_time_db_ms, p95_time_db_ms), ...)
  4. If score ≥ threshold → this window_end is the breach start
  5. Find the earliest spawn_done event AFTER this window_end
     with matching (lan, tier) from elasticity_events.csv
  6. reaction_s = spawn_done_ts - breach_window_end
```

```python
def compute_reaction_latency(
    debug_rows: list[dict],
    events: list[ElasticityEvent],
    thresholds: dict,
) -> list[dict]:
    """Detect breaches from telemetry, match to spawn completions."""
    # Step 1: detect breaches from telemetry data
    breaches = detect_breaches(debug_rows, thresholds)

    # Step 2: for each breach, find the earliest spawn_done
    # with matching (lan, tier) that occurs after the breach window
    spawns_by_tier: dict[tuple[str, str], list[ElasticityEvent]] = {}
    for ev in events:
        if ev.kind == "spawn_done":
            # Map controller lan to network_id: "lan1" -> "lan1"
            key = (ev.lan, ev.tier)
            spawns_by_tier.setdefault(key, []).append(ev)

    results = []
    for breach in breaches:
        key = (breach["network_id"], breach["tier"])
        candidates = sorted(
            [e for e in spawns_by_tier.get(key, [])
             if e.ts > breach["window_end"]],
            key=lambda e: e.ts,
        )
        if not candidates:
            continue  # spawn never completed (breach unactioned)

        spawn_done = candidates[0]
        # Find spawn_start for the same chain (closest before spawn_done)
        spawn_start_ts = spawn_done.ts
        for ev in events:
            if (ev.kind == "spawn_start"
                    and ev.lan == breach["network_id"]
                    and ev.tier == breach["tier"]
                    and ev.ts < spawn_done.ts
                    and ev.ts > breach["window_end"]):
                spawn_start_ts = ev.ts
                break

        results.append({
            "breach_window_end": breach["window_end"],
            "lan": breach["network_id"],
            "tier": breach["tier"],
            "score": breach["score"],
            "threshold": breach["threshold"],
            "breach_detection_s": round(
                max(0.0, spawn_start_ts - breach["window_end"]), 3),
            "provision_time_s": round(
                max(0.0, spawn_done.ts - spawn_start_ts), 3),
            "total_reaction_s": round(
                max(0.0, spawn_done.ts - breach["window_end"]), 3),
        })
    return results
```

### Segments measured

| Segment                  | Formula                                | Meaning                                                     |
| ------------------------ | -------------------------------------- | ----------------------------------------------------------- |
| Breach detection         | `spawn_start_ts - breach_window_end` | Time from overload visible in telemetry to spawn initiation |
| Provisioning             | `spawn_done_ts - spawn_start_ts`     | Container boot + wiring time                                |
| **Total reaction** | `spawn_done_ts - breach_window_end`  | Full pipeline: overload visible → node operational         |

### Plot structure

```
rq1_staleness.png:  2 panels (lan1, lan2) stacked vertically
  X = t_s (window_end - origin_ts)
  Y = staleness_s
  Phase shading behind each panel
  Horizontal dashed line at 0

rq1_reaction_latency.png:  2 panels side by side
  Left:  stacked horizontal bar per scaling event
         [breach→spawn_start] [spawn_start→spawn_done]
         Y axis: event label (lan, tier, index)
         X axis: seconds
  Right: per-phase summary table
         Columns: phase, N, Det(p95), Prov(p95), Total(p95)
```

### Edge cases

- **No scaling events**: produce empty CSVs and a note "no scaling events in this run" instead of crashing.
- **Missing `consumed_at`** (old runs): skip staleness rows where `consumed_at <= 0`, produce a warning.
- **Push mode**: staleness should be sub-second. Any spike > 1s in push mode is a bug.
- **Poll mode**: staleness is expected to be ~0s regardless of `POLL_INTERVAL_S`, because the aggregator's `/latest_summary` endpoint always returns the most recent completed window. The operational impact of polling cadence is captured by reaction latency (Measurement #2), not by `consumed_at − window_end`.
- **Staleness CSV rows with empty `consumed_at`**: skipped during computation (windows the controller never processed — common in poll mode when the controller misses intermediate windows between poll cycles).

---

## Phase 5 — `sample_controller_stats.py` (Controller Overhead Sampler)

**File:** `source/scripts/testing/sample_controller_stats.py` (new)

A background process, modeled after `collect_resource_stats.py`, that
periodically samples controller container CPU and RAM via `docker stats`.

### Script structure

```python
#!/usr/bin/env python3
"""sample_controller_stats — periodic docker stats sampler for RQ1 overhead.

Run as a background process during experiments. Writes one row every
SAMPLE_INTERVAL_S seconds to <output>/controller_stats.csv.

Usage:
    python3 sample_controller_stats.py \
        --output /path/to/run/controller_stats.csv \
        --phase-file /path/to/current_phase.txt \
        [--interval 5]
"""

import argparse
import csv
import os
import signal
import subprocess
import sys
import time

# Container names to monitor (both controllers).
# Run with sudo so docker can be accessed.
_CONTROLLER_CONTAINERS = ["osken", "osken"]  # two instances, same image

FIELDNAMES = [
    "timestamp_iso", "phase", "container", "name",
    "cpu_percent", "mem_usage_mb",
]

_running = True


def _handle_sigterm(signum, frame):
    global _running
    _running = False


def _get_controller_ids() -> list[str]:
    """Return container IDs for the two os-ken controller containers."""
    try:
        out = subprocess.check_output(
            ["docker", "ps", "--filter", "ancestor=osken-controller",
             "--format", "{{.ID}} {{.Names}}"],
            text=True,
        )
    except subprocess.CalledProcessError:
        return []
    return [line.split()[0] for line in out.strip().split("\n") if line]


def _docker_stats(container_ids: list[str]) -> list[dict]:
    """Run docker stats --no-stream and parse output."""
    if not container_ids:
        return []
    # docker stats --no-stream can take multiple container IDs
    # Output: container_id,name,cpu%,mem_usage,...
    fmt = "{{.ID}},{{.Name}},{{.CPUPerc}},{{.MemUsage}}"
    try:
        out = subprocess.check_output(
            ["docker", "stats", "--no-stream", "--format", fmt]
            + container_ids,
            text=True,
        )
    except subprocess.CalledProcessError:
        return []
    results = []
    for line in out.strip().split("\n"):
        parts = line.split(",")
        if len(parts) < 4:
            continue
        cid, name, cpu, mem = parts[0], parts[1], parts[2], parts[3]
        # Parse mem_usage: "123.4MiB / 1.5GiB" → extract first number
        mem_mb = 0.0
        mem_str = mem.split("/")[0].strip() if "/" in mem else mem.strip()
        if mem_str.endswith("MiB"):
            mem_mb = float(mem_str[:-3])
        elif mem_str.endswith("GiB"):
            mem_mb = float(mem_str[:-3]) * 1024
        elif mem_str.endswith("KiB"):
            mem_mb = float(mem_str[:-3]) / 1024
        results.append({
            "container": cid,
            "name": name,
            "cpu_percent": cpu.strip("%"),
            "mem_usage_mb": f"{mem_mb:.1f}",
        })
    return results


def _read_phase(phase_file_path: str) -> str:
    """Read the current phase name from the phase file."""
    try:
        with open(phase_file_path, "r") as f:
            return f.readline().strip()
    except (OSError, IOError):
        return ""


def main():
    parser = argparse.ArgumentParser(description="Sample controller CPU/RAM")
    parser.add_argument("--output", required=True, help="CSV output path")
    parser.add_argument("--phase-file", required=True,
                        help="Path to current_phase.txt")
    parser.add_argument("--interval", type=int, default=5,
                        help="Sample interval in seconds (default: 5)")
    args = parser.parse_args()

    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)

    out_dir = os.path.dirname(args.output)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)

    with open(args.output, "w", newline="") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=FIELDNAMES)
        writer.writeheader()

        while _running:
            cids = _get_controller_ids()
            phase = _read_phase(args.phase_file)
            ts = time.time()
            ts_iso = time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))

            for stats in _docker_stats(cids):
                writer.writerow({
                    "timestamp_iso": ts_iso,
                    "phase": phase,
                    "container": stats["container"],
                    "name": stats["name"],
                    "cpu_percent": stats["cpu_percent"],
                    "mem_usage_mb": stats["mem_usage_mb"],
                })
            csvfile.flush()
            time.sleep(args.interval)


if __name__ == "__main__":
    main()
```

### Integration into `run_experiment.sh`

The script follows the same lifecycle as `collect_resource_stats.py`:

```bash
# In run_experiment.sh, after the controller is ready (after setup_network),
# before traffic starts:

# Start overhead sampler
OVERHEAD_SAMPLER_PID=""
if command -v python3 &>/dev/null; then
    python3 "${SCRIPTS_DIR}/testing/sample_controller_stats.py" \
        --output "${RUN_DIR}/controller_stats.csv" \
        --phase-file "${RUN_DIR}/current_phase.txt" \
        --interval 5 &
    OVERHEAD_SAMPLER_PID=$!
fi

# ... run traffic generator ...

# Kill overhead sampler (same moment as collector)
if [[ -n "$OVERHEAD_SAMPLER_PID" ]]; then
    kill "$OVERHEAD_SAMPLER_PID" 2>/dev/null || true
fi
```

The exact insertion point must be identified in `run_experiment.sh` by
locating the `collect_resource_stats` start/kill pattern and mirroring
it for the overhead sampler.

---

## Phase 4b — `cli_rq1_overhead.py` (Control-Plane Overhead Plots)

**File:** `source/scripts/testing/analysis/rq1/cli_rq1_overhead.py` (new)

Reads `controller_stats.csv` (produced by Phase 5) and generates CPU/RAM
time-series plots.

### Inputs

| Artifact                  | Field                                                           | Used for                           |
| ------------------------- | --------------------------------------------------------------- | ---------------------------------- |
| `controller_stats.csv`  | `timestamp_iso`, `phase`, `cpu_percent`, `mem_usage_mb` | CPU% and RSS(MB) time-series       |
| `phases_snapshot.json`  | Phase boundaries                                                | Phase shading                      |
| `elasticity_events.csv` | Event timestamps                                                | Vertical markers at scaling events |

### Outputs

| File                 | Content                                                                                                                    |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `rq1_overhead.png` | Two panels: (top) CPU% over time, (bottom) RSS(MB) over time; phase-shaded; scaling event markers as dashed vertical lines |
| `rq1_overhead.csv` | Per-phase: mean/p95 CPU%, mean/p95 RSS(MB)                                                                                 |

### Computation

```python
def compute_overhead(run) -> tuple[list[dict], dict[str, dict]]:
    """
    Returns:
      time_series: list of {t_s, cpu_pct, mem_mb}
      per_phase: {phase_name: {mean_cpu, p95_cpu, mean_mem, p95_mem}}
    """
    origin_ts = infer_origin_ts(run)
    rows = getattr(run, "controller_stats_rows", [])
  
    ts_data = []
    for row in rows:
        ts = parse_iso_ts(row.get("timestamp_iso"))
        if ts <= 0:
            continue
        ts_data.append({
            "t_s": max(0.0, ts - origin_ts),
            "phase": row.get("phase", ""),
            "cpu_pct": safe_float(row.get("cpu_percent")),
            "mem_mb": safe_float(row.get("mem_usage_mb")),
        })
  
    per_phase = {}
    for row in ts_data:
        p = per_phase.setdefault(row["phase"], {"cpu": [], "mem": []})
        p["cpu"].append(row["cpu_pct"])
        p["mem"].append(row["mem_mb"])
  
    summary = {}
    for phase, vals in per_phase.items():
        summary[phase] = {
            "mean_cpu_pct": sum(vals["cpu"]) / len(vals["cpu"]) if vals["cpu"] else 0,
            "p95_cpu_pct": percentile(vals["cpu"], 0.95),
            "mean_mem_mb": sum(vals["mem"]) / len(vals["mem"]) if vals["mem"] else 0,
            "p95_mem_mb": percentile(vals["mem"], 0.95),
        }
  
    return ts_data, summary
```

### Thesis alignment

Controller CPU% and RSS (MB) via `docker stats` on both `osken` and
`osken_2` containers. Polling traffic volume estimated from
`POLL_INTERVAL_S` and summary size (~2–10 KB per poll).

### Loader integration

The existing `loader.py` must be extended to optionally load
`controller_stats.csv`:

```python
# In loader.py load_run():
controller_stats_path = run_dir / "controller_stats.csv"
controller_rows = _read_csv(controller_stats_path, optional=True)
```

This is a single-line addition. The field `controller_stats_rows` must be
added to the `Run` dataclass with default `[]`.

---

## Phase 6 — `cli_rq1_decision_quality.py` (Scaling Outcome Description)

**File:** `source/scripts/testing/analysis/rq1/cli_rq1_decision_quality.py` (new)

Describes each breach outcome against the workload phase structure using
labels grounded in what the controller actually does — not subjective
"correctness" judgments. Uses the **same `breach_detector.py` module** as
`cli_rq1_timings.py` to detect breaches from telemetry data, ensuring
consistent breach detection across both CLIs.

### Phase load classification

```python
PHASE_LOAD_CLASSIFICATION = {
    "baseline":           "low",
    "quick_stress":       "high",
    "storage_stress":     "high",
    "cross_region_hotspot": "high",
    "compute_ramp":       "high",
    "compute_spike":      "high",
    "sustained_plateau":  "high",
    "demand_drop":        "low",
    "reverse_hotspot":    "high",
    "transition":         "transition",
}
```

### Classification logic

The CLI compares two independently observable facts to produce a 2×2
description table:

1. **Breach-detector finding**: did `degradation_score ≥ threshold` in
   this telemetry window (accounting for dynamic threshold, peer relief,
   and cooldown)?
2. **Controller action**: did a `spawn_done` event follow the breach?

Each breach is then mapped to the phase it fell in via
`PHASE_LOAD_CLASSIFICATION` and assigned a descriptive label:

| Breach phase load         | `spawn_done` exists | Label                | Meaning                                                                      |
| ------------------------- | --------------------- | -------------------- | ---------------------------------------------------------------------------- |
| `high`                  | yes                   | **actionable** | Real overload, controller acted                                              |
| `high`                  | no                    | **unactioned** | Real overload, but sliding window / cooldown / capacity cap prevented action |
| `low` or `transition` | yes                   | **over-eager** | Brief threshold crossing, controller spawned anyway                          |
| `low` or `transition` | no                    | **transient**  | Brief threshold crossing, controller correctly suppressed                    |

**Why there is no "delayed" label.** Reaction latency is measured
separately by `cli_rq1_timings.py` as `total_reaction_s = spawn_done_ts

- breach_window_end`. Conflating "was it correct?" with "was it fast?"
  into one label creates confusion — these are separate measurements.

**Why the sliding window is not replicated.** The controller requires
`REQUIRED/WINDOW_SIZE` consecutive hits to trigger; `breach_detector.py`
fires on the first individual window. The CLI therefore detects breaches
that the sliding window may suppress (→ `unactioned`), or may miss
breaches the controller caught after accumulating hits. The breach count
may differ from the controller's alert count — this is by design. The
CLI measures "when was overload visible in telemetry," not "when did the
controller decide to act."

### Outputs

| File                         | Content                                                                                                                                                                |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `rq1_decision_quality.csv` | Per breach: window_end, lan, tier, phase, phase_load, score, threshold, delay_s, classification (actionable/unactioned/over-eager/transient), justification            |
| `rq1_decision_quality.png` | Confusion-style heatmap: rows = phase names, columns = label, cell color = event count. Green = actionable, red = unactioned, orange = over-eager, yellow = transient. |

### Edge cases

- **Breach count differs from alert count**: `breach_detector.py` does
  not replicate the sliding window — it fires on the first window where
  `score ≥ threshold`. The controller may need more windows to fill the
  sliding window, or may be suppressed by cooldown/capacity cap. Expect
  the CLI's breach count to differ from `elasticity_events.csv` alert
  count. This is not a bug.
- **`controller_env_snapshot.env` must be present**: without it,
  `load_thresholds()` falls back to `scaling_config.py` defaults which
  may be too conservative for the workload — breach detection returns 0
  events. The run runner must verify this file is captured.
- **Multiple breaches per phase**: labelled independently. A second
  breach in the same high-load phase may be `actionable` (if another
  spawn follows) or `unactioned` (if capacity cap was reached).
- **Cross-LAN events**: spawn events on the peer LAN are excluded from
  matching (each controller only manages its own LAN). The
  `breach_detector` uses `network_id` from the debug rows which
  corresponds to the LAN where the breach was detected.

---

## File Map Summary

| Action | Path                                                                | Phase |
| ------ | ------------------------------------------------------------------- | ----- |
| New    | `source/scripts/testing/analysis/rq1/__init__.py`                 | 4     |
| New    | `source/scripts/testing/analysis/rq1/breach_detector.py`          | 4a,6  |
| New    | `source/scripts/testing/analysis/rq1/cli_rq1_timings.py`          | 4a    |
| New    | `source/scripts/testing/analysis/rq1/cli_rq1_overhead.py`         | 4b    |
| New    | `source/scripts/testing/sample_controller_stats.py`               | 5     |
| Edit   | `source/scripts/testing/run_experiment.sh`                        | 5     |
| Edit   | `source/scripts/testing/analysis/loader.py`                       | 4b    |
| New    | `source/scripts/testing/analysis/rq1/cli_rq1_decision_quality.py` | 6     |
| Edit   | `docs/operation/testing/analysis_toolchain.md`                    | 4,6   |
| Edit   | `source/scripts/testing/analysis/events.py`                      | —     |

---

## Post-Implementation Corrections (2026-06-21)

Two tooling bugs were discovered during the `rq1_instrumentation_verification`
experiment (v4) and fixed. See `results.md` §4 for full details.

### Bug A — LAN naming mismatch in `cli_rq1_timings.py`

`events.py` `parse_logs()` strips the ``"lan"`` prefix from filenames,
producing event LAN values ``"1"`` / ``"2"``.  The breach detector's
``network_id`` uses ``"lan1"`` / ``"lan2"``.  When
``compute_reaction_latency()`` built a spawn index keyed by
``(ev.lan, ev.tier)``, the keys never matched breach lookup keys.

**Fix**: Normalise `ev.lan` by prepending ``"lan"`` at both the spawn
index building site and the spawn_start matching site.

### Bug B — Timezone shift in `events.py` `_parse_ts()`

Controller logs use Python's ``%(asctime)s`` which produces
**comma-separated milliseconds in local time** (e.g.
``2026-06-14 00:38:25,822``).  Two sub-issues:

1. ``_RE_TIMESTAMP`` used ``(?:\.\d+)?`` — only matched dot before ms.
2. ``time.mktime()`` interpreted parsed time as local (Portugal = UTC+1
   in June), shifting all parsed timestamps by −3600 s vs
   ``time.time()`` (UTC epoch).

**Fix**:
1. Regex: ``(?:[.,]\d+)?`` to capture comma-separated ms.
2. ``ts_str.replace(",", ".")`` before parsing.
3. ``calendar.timegm()`` instead of ``time.mktime()`` for UTC→epoch.

### Staleness reframing

The experiment confirmed that `consumed_at − window_end` ≈ 0 s in all
four delivery modes (push, poll5, poll12, poll30).  This is correct
behavior: the aggregator's `/latest_summary` endpoint always returns
the most recent completed window, so the summary the controller reads
is always fresh regardless of polling cadence.  The controller misses
intermediate windows (2 out of 3 at 30 s polling), but the windows it
*does* consume are fresh.

The RQ1 question — *"does polling slower cause the controller to react
slower?"* — is therefore answered by reaction latency (Measurement #2),
not by staleness.  The `breach_detection_s` segment of reaction latency
captures the time from overload first visible in telemetry to spawn
initiation; this grows with polling interval because the controller
becomes aware of overload later, even though the data it reads is fresh.

**No architecture changes are needed.**  The existing tooling
correctly measures RQ1's primary dependent variable (reaction latency)
across all delivery modes.

---

## Dependencies

```
Phase 4a (cli_rq1_timings)          — independent; uses existing artifacts
Phase 5  (sample_controller_stats)   — independent; new runtime sampler
  └─→ Phase 4b (cli_rq1_overhead)  — needs controller_stats.csv
Phase 6  (cli_rq1_decision_quality)  — independent; uses existing artifacts
```

---

## What each tool produces vs. thesis definition

| Thesis Measurement          | Tool                                                     | How it's measured                                                                                                                                                                                                                     |
| --------------------------- | -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Decision staleness          | `cli_rq1_timings.py`                                   | `consumed_at - window_end` per debug row. Both `time.time()`, same host. Informational metric only — ≈ 0s in all modes (push and poll) because `/latest_summary` returns freshest window. The RQ1 thesis question ("does polling slower cause the controller to react slower?") is answered by reaction latency, not staleness. |
| Reaction latency            | `cli_rq1_timings.py` + `breach_detector.py`          | CLI independently computes `degradation_score` from telemetry data. Breach start = first `window_end` where score ≥ threshold. End = `spawn_done_ts`. Segments: breach_detection (→ spawn_start) + provision (→ spawn_done). **This is the primary RQ1 measurement** — captures the polling cost that staleness cannot. |
| Transient service quality   | Existing (`cli_simple_run` et al)                      | p95/p99 latency, failure rate, per-phase. Already correct.                                                                                                                                                                            |
| Control-plane overhead      | `sample_controller_stats.py` + `cli_rq1_overhead.py` | CPU% and RSS(MB) from `docker stats` every 5s. Polling traffic volume estimated from `POLL_INTERVAL_S` and summary size.                                                                                                          |
| Scaling outcome description | `cli_rq1_decision_quality.py` + `breach_detector.py` | Per-phase descriptive table: total telemetry windows, breached windows, peak degradation score, spawns initiated/completed. No classification labels — the gap between breached-windows and completed-spawns is the observable fact. See Phase 6 for rationale. |
