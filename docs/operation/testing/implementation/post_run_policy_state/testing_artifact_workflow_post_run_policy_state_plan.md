# Testing Artifact Workflow Post-Run Policy State Plan

## Status

Implemented (2026-06-02).

## Objective

Redesign the default experiment artifact workflow so that:

1. the canonical request artifact remains `client_requests.csv`
2. no default workflow produces `client_requests_<phase>.csv`
3. the main per-window metrics artifact becomes a trimmed `resource_stats.csv`
4. the current broad `resource_stats.csv` shape is preserved as `resource_stats_debug.csv`
5. `policy_state.csv` is generated after the run from existing artifacts instead of being published live by the controller

This plan explicitly rejects any new controller-side per-window policy-state
publisher. The controller hot path must not gain extra publication work, extra
per-window serialization, or additional observability-only state tracking.

## Locked Requirements

1. Do not add any new controller-side policy-state publisher.
2. Do not add extra controller hot-path work just to support `policy_state.csv`.
3. Keep `client_requests.csv` as the only default client request CSV artifact.
4. Rename the current broad domain metrics view to `resource_stats_debug.csv`.
5. Make `resource_stats.csv` a trimmed per-window file focused on the values
   that actually drive scale-up and scale-down reasoning.
6. Keep `policy_state.csv` separate from `resource_stats.csv`.
7. Allow `policy_state.csv` to be reconstructed with controlled assumptions
   instead of requiring a perfect replay of every controller internal.
8. Prefer a stable 10-second windowed view over a maximal event dump.
9. Keep the solution grounded in the current run harness, current log capture,
   current controller env snapshot, and current post-run tooling.

## Implementation Direction

Implement `policy_state.csv` as a post-run, 10-second, per-LAN reconstruction
anchored to the trimmed `resource_stats.csv` timeline.

Generate `policy_state.csv` after the run by combining:

1. `resource_stats.csv` for the per-window timeline and raw scale inputs
2. `resource_stats_debug.csv` for any broader fields still needed for diagnosis
3. `controller_env_snapshot.env` for the exact thresholds, floors, spans,
   weights, cooldowns, and caps used in that run
4. `per_node_stats.csv` and `container_events.csv` to infer dynamic node counts
   and lifecycle boundaries
5. `controller_lan1.log` and `controller_lan2.log` to annotate controller-only
   outcomes such as busy skips, cooldown skips, trigger decisions, candidate
   selection, and no-candidate clears

The result is one row per LAN per telemetry window, not one row per log line.

## Reconstruction Assumptions

The reconstruction is allowed to make controlled assumptions, because the goal
is a useful and stable analysis artifact rather than a byte-for-byte replay of
controller internals.

1. `window_end` in `resource_stats.csv` is the canonical policy timeline.
2. One policy evaluation is assumed per `(network_id, window_end)` row.
3. If multiple relevant controller log lines fall inside the same window,
   the latest matching line for that state category wins.
4. Score fields should be derived from metrics plus the run-local controller env
   snapshot whenever the required inputs exist.
5. Dynamic compute and storage counts should be inferred from per-node rows
   first, then from container events as fallback.
6. If a field cannot be reconstructed confidently for a window, leave it blank
   and still emit the row.
7. The file is permitted to represent effective policy state, not every hidden
   intermediate branch the controller may have visited.

## Target Artifact Contract

After implementation, a standard run folder should contain:

1. `client_requests.csv`
2. `resource_stats.csv`
3. `resource_stats_debug.csv`
4. `policy_state.csv`
5. `per_node_stats.csv`
6. `container_events.csv`
7. `elasticity_events.csv`
8. `controller_lan1.log`
9. `controller_lan2.log`
10. existing snapshots and service logs

`client_requests_<phase>.csv` must not be part of the default contract.

## Trimmed resource_stats.csv Scope

The main `resource_stats.csv` should contain the raw inputs and derived helpers
that directly matter to elasticity reasoning. It should not carry broad debug
and runtime-helper columns that do not materially contribute to scale-up or
scale-down interpretation.

Planned main columns:

1. `timestamp`
2. `phase`
3. `network_id`
4. `window_end`
5. `total_requests`
6. `average_cpu_percent`
7. `avg_time_proc_ms`
8. `avg_storage_cpu_percent`
9. `avg_time_db_ms`
10. `p95_time_db_ms`
11. `storage_latency_signal_ms`
12. `server_count`
13. `storage_count`
14. `avg_repl_lag_ms`
15. any minimal derived score components needed for quick inspection

The current broad median-heavy and Tier 1 helper view should move to
`resource_stats_debug.csv`.

## policy_state.csv Scope

`policy_state.csv` should be a post-run, per-window, per-LAN derived file.

Planned columns:

1. `timestamp`
2. `phase`
3. `network_id`
4. `window_end`
5. `dynamic_compute_count`
6. `dynamic_storage_count`
7. `compute_score`
8. `compute_base_threshold`
9. `compute_effective_threshold`
10. `compute_above_threshold`
11. `compute_window_hits`
12. `compute_window_size`
13. `compute_scaleup_cooldown_remaining_s`
14. `compute_scaledown_below_threshold`
15. `compute_scaledown_hits`
16. `compute_scaledown_armed`
17. `compute_scaledown_cooldown_remaining_s`
18. `storage_score`
19. `storage_base_threshold`
20. `storage_effective_threshold`
21. `storage_above_threshold`
22. `storage_window_hits`
23. `storage_window_size`
24. `storage_latency_signal_ms`
25. `storage_scaleup_cooldown_remaining_s`
26. `storage_scaledown_below_threshold`
27. `storage_scaledown_hits`
28. `storage_scaledown_armed`
29. `storage_scaledown_cooldown_remaining_s`
30. `elasticity_busy`
31. `compute_blocked`
32. `storage_blocked`
33. `compute_triggered`
34. `storage_triggered`
35. `compute_candidate_selected`
36. `storage_candidate_selected`
37. `notes`

Not every column needs to be available in every window. The reconstruction may
leave values blank when the signal is not recoverable without inventing state.

## Code Sketches

### Post-Run Reconstruction Entry Point

```python
def reconstruct_policy_state(
    resource_rows: list[dict],
    debug_rows: list[dict],
    node_rows: list[dict],
    container_event_rows: list[dict],
    controller_logs: dict[str, Path],
    controller_env: dict[str, str],
) -> list[dict]:
    """Build one policy-state row per LAN per telemetry window."""
```

### Window-First Reconstruction Model

```python
@dataclass
class PolicyWindow:
    network_id: str
    window_end: float
    phase: str
    dynamic_compute_count: int | None = None
    dynamic_storage_count: int | None = None
    compute_score: float | None = None
    storage_score: float | None = None
    elasticity_busy: bool | None = None
    notes: list[str] = field(default_factory=list)
```

### Harness Integration Shape

```bash
python3 "${SCRIPTS_DIR}/tools/reconstruct_policy_state.py" \
    --resource-stats "${RESOURCE_STATS_OUTPUT}" \
    --resource-stats-debug "${RESOURCE_STATS_DEBUG_OUTPUT}" \
    --per-node-stats "${PER_NODE_STATS_OUTPUT}" \
    --container-events "${CONTAINER_EVENTS_OUTPUT}" \
    --controller-env "${CONTROLLER_ENV_SNAPSHOT_OUTPUT}" \
    --controller-log-lan1 "${CONTROLLER_LOG_LAN1}" \
    --controller-log-lan2 "${CONTROLLER_LOG_LAN2}" \
    --output "${POLICY_STATE_OUTPUT}"
```

## Step-By-Step Plan

### Step 1 - Freeze the new artifact contract

Update the testing workflow documentation and harness expectations so the
default artifact contract becomes:

1. `client_requests.csv`
2. `resource_stats.csv`
3. `resource_stats_debug.csv`
4. `policy_state.csv`
5. `per_node_stats.csv`
6. existing logs and snapshots

Explicitly remove any default expectation of `client_requests_<phase>.csv`.

### Step 2 - Split main and debug resource stats outputs

Refactor `source/scripts/testing/collect_resource_stats.py`
to write two domain-level CSVs:

1. a trimmed `resource_stats.csv`
2. a broad `resource_stats_debug.csv`

The debug file should preserve the current broad schema as closely as possible.
The main file should carry the actual elasticity inputs and small derived
helpers only.

### Step 3 - Keep request metrics aggregate-only

Confirm that `source/scripts/testing/traffic_generator.py`
and `source/scripts/testing/run_experiment.sh`
only produce `client_requests.csv` by default.

Then update analysis and documentation that still mention
`client_requests_<phase>.csv`.

### Step 4 - Add a post-run policy reconstruction tool

Add a new script: `source/scripts/tools/reconstruct_policy_state.py`

Responsibilities:

1. load the canonical window grid from `resource_stats.csv`
2. load exact run configuration from `controller_env_snapshot.env`
3. derive score fields directly from metrics and config
4. infer dynamic node counts from `per_node_stats.csv`
5. use `container_events.csv` as fallback around spawn and drain boundaries
6. parse controller logs only for controller-only outcomes and annotations
7. emit `policy_state.csv`

### Step 5 - Reuse and extend existing log parsing

Refactor `source/scripts/tools/parse_elasticity_logs.py`
so it exposes reusable log-line parsing helpers that are imported directly by
`source/scripts/tools/reconstruct_policy_state.py`.

### Step 6 - Anchor to the 10-second metrics cadence

The reconstruction must treat the per-window rows from `resource_stats.csv` as
authoritative time buckets.

### Step 7 - Prefer per-node evidence for dynamic counts

Use `source/scripts/testing/collect_resource_stats.py`'s
`per_node_stats.csv` output as the primary source for dynamic node counts.
