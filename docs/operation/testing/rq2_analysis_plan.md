# RQ2 Analysis Plan — CLI Tools and Graphs

**Status**: ✅ Implemented · **Date**: 2026-07-05
**RQ doc**: [`docs/research_questions/rq2.md`](../../research_questions/rq2.md)
**Implementation plan**: [`docs/operation/vip_routing/rq2_implementation_plan.md`](../vip_routing/rq2_implementation_plan.md)

---

## Intent

Extend the analysis toolchain to measure load redistribution time, produce the
per-mode redistribution profile, and generate the five graphs needed to
evaluate RQ2.

---

## Required Graphs

### Graph 1 — Redistribution Profile (Core Visual Evidence)

**What**: Request share (y-axis, 0→1) vs time since spawn (x-axis, 0→~60s).
One line per mode overlaid on the same axes.

```
Request share
  1.0 ┤      ╱╲
      ┤     ╱  ╲___              ← topology_host (cold-start herd)
  0.5 ┤    ╱       ╲___
      ┤   ╱            ╲____     ← topology_lifecycle (warm lease)
  0.0 ┤──                   ╱
      └─────────────────────╱──   ← topology_slowstart (invisible → ramp)
      0                   30   60s
```

**Data**: `per_node_stats.csv` filtered to new backend MAC, joined with controller log events (`run.events`, loaded by the existing `loader.py`) for `spawn_done` timestamps.

**Production**: New CLI command `cli_rq2_redistribution` (produces all Graph data).

**Requirements**:

- Detect scale-up events from `run.events` (`ElasticityEvent` with `kind="spawn_done"`). Filter by role using the local `_container_role()` helper (same logic as `simple_metrics.container_role`) to separate compute and storage spawns.
- For each spawn event, extract `spawn_ts = ev.ts` and container name.
- **MAC resolution** (there is no direct container→MAC join): use role-aware temporal proximity. For a spawn at time T with role R, find server_ids of role R in `per_node_stats.csv` that (a) did not appear in any window before T, and (b) appear in a window within [T, T+15s]. The server_id column IS the MAC. Role disambiguation (matching only same-role backends) prevents cross-type misidentification; the scale-up cooldown guarantees at most one new backend per role in any 15 s window, so the match is unambiguous.\n- **Spawn isolation filter — ±45s window**: only measure redistribution for spawns where no other spawn of the same role occurred within ±45s (the warm-lease TTL for compute). If a second spawn arrives before the first has finished redistributing, the pool size changes mid-measurement and the equilibrium threshold shifts — contaminating the redistribution time. Cross-LAN spawns (lan1 vs. lan2) operate on separate VIP pools and do NOT contaminate each other — the isolation check is **per-role, per-LAN** (using the `network_id` column in `per_node_stats.csv`). Spawns that fail the isolation check are skipped. From the existing push-run artifacts, per-LAN per-role spawns are spaced 70–120s apart — comfortably exceeding the 45s window — so most spawns will pass this filter.
- From `per_node_stats.csv`, filter rows matching the resolved MAC after spawn time.
- **Compute vs. storage handling**: for compute backends, use `request_count` as the load metric; for storage backends, use `avg_connections`. Compute `share = this_node_metric / total_metric_in_window`.
- **Storage — PRIMARY exclusion**: the PRIMARY handles write traffic that no secondary receives. Its connection count is structurally higher and a new secondary can never match it. For storage share calculations and equilibrium detection, **filter to SECONDARY nodes only** (`member_state == "SECONDARY"` in `per_node_stats.csv`). Exclude the PRIMARY from both the metric total and the backend count N. Compute backends are unaffected — all edge servers are equivalent.
- **Data granularity**: both `request_count` and `avg_connections` are per-10s-window cumulative values — this gives approximate share at 10 s granularity, acceptable for redistribution profiling.
- Compute `time_since_spawn = per_node_stats.timestamp - spawn_ts`.
- Align all scale-up events by `time_since_spawn` (x-axis).
- Aggregate: mean share per time bucket (1-second bins) across all events in a run, separately for compute and storage roles.
- Output: CSV with columns `mode, role, time_since_spawn_s, mean_share, std_share`

---

### Graph 2 — Redistribution Time (Core Quantitative Evidence)

**What**: Box plot or bar chart. One bar per mode. Y-axis: seconds from `spawn_done` to equilibrium.

```
Redistribution time (s)
  50 ┤ ┌─────┐
     ┤ │     │  ┌─────┐
  25 ┤ │  █  │  │  █  │  ┌─────┐
     ┤ │     │  │     │  │  █  │
   0 ┤ └─────┘  └─────┘  └─────┘
       R2-TH     R2-SS     R2-TL
```

**Data**: Derived from Graph 1 data.

**Production**: Same CLI command produces both the profile CSV and a summary CSV.

**Requirements**:

- For each scale-up event, find first timestamp where `|share - expected_share| ≤ 0.10` for 3 consecutive samples.
  - **Compute**: `expected_share = 1 / N` where N = all compute backends in the pool at that window.
  - **Storage**: `expected_share = 1 / N` where N = all **SECONDARY** storage backends in the pool at that window (PRIMARY excluded — see below).
- `redistribution_time_s = equilibrium_ts - spawn_done_ts`
- Per-mode aggregate: `n`, `mean`, `median`, `p95`, `min`, `max`
- Output: CSV with columns `mode, n_events, mean_s, median_s, p95_s, min_s, max_s`

---

### Graph 3 — Transition-Window Service Quality

**What**: Side-by-side bar charts. p95 latency (ms) and failure rate (%) during `compute_spike` phase, one bar per mode.

**Data**: `client_requests.csv` filtered to `phase=compute_spike`.

**Production**: Computed directly in `cli_rq2_redistribution` (no modification to `cli_phase_summary` needed).

**Requirements**:

- Load `client_requests.csv` for each run folder
- Filter to `phase == "compute_spike"`
- Compute p95 latency and failure rate per run
- Map each run to its mode via `BACKEND_SELECTION_POLICY` from `controller_env_snapshot.env`
- Output: CSV `rq2_transition_quality.csv` with columns `mode, p95_latency_ms, failure_rate_pct`

---

### Graph 4 — Cumulative Requests to New Backend

**What**: Cumulative request count (y-axis) vs time since spawn (x-axis), one line per mode.

```
Cumulative requests to new backend
  1000 ┤        ╱
       ┤      ╱                 ← topology_host: fastest accumulation
   500 ┤    ╱                   ← topology_lifecycle: close behind
       ┤  ╱
     0 ┤──╱                     ← topology_slowstart: flat during gap
       └──────────────────
       0         30      60s
```

**Data**: Same as Graph 1, but cumulative sum instead of share.

**Production**: Same CLI as Graph 1 — just a different aggregation of the same data.

**Requirements**:

- For each scale-up event, compute cumulative request count to the new backend
- Aggregate: mean cumulative count per time bucket across all events in a run
- Output: CSV with columns `mode, time_since_spawn_s, mean_cumulative_requests`

---

### Graph 5 — Coordination-Gap Penalty (annotation on Graph 2)

**What**: The difference between `topology_slowstart` and `topology_lifecycle` mean redistribution times — the coordination-gap penalty in routing. This is the RQ2 equivalent of RQ1's breach-detection penalty.

Rather than a standalone chart, this is displayed as an **annotation on Graph 2**: a line connecting the SS and TL bars with a label: "Δ = Xs coordination-gap penalty." The value is computed as `mean_redistribution_s(SS) − mean_redistribution_s(TL)` from Graph 2's aggregate data.

---

## New CLI Command: `cli_rq2_redistribution`

**Location**: `source/scripts/testing/analysis/rq2/cli_rq2_redistribution.py`

**Usage**:

```
python cli_rq2_redistribution.py <run_folder> [<run_folder> ...]
```

**Inputs per run folder**:

- `run.events` — controller log events loaded by `loader.py` (`ElasticityEvent` with `kind="spawn_done"`)
- `per_node_stats.csv` — per-backend load metrics over time (10 s windows)
- `client_requests.csv` — per-request latency/failure data (for Graph 3 only)
- `controller_env_snapshot.env` — mode detection (`BACKEND_SELECTION_POLICY` key)
- `phases_snapshot.json` — phase boundaries (used only for Graph 3: filtering `client_requests.csv` to `compute_spike` phase)

**Mode detection**: Read `BACKEND_SELECTION_POLICY` from `controller_env_snapshot.env`. If absent, default to `topology_lifecycle`. This file is already captured by `post_run.sh` and verified in RQ1 experiments.

**Outputs** (written to `<run_folder>/analysis/`):

- `rq2_redistribution_profile.csv` — per-second load share over time, per role (Graph 1 data)
- `rq2_redistribution_summary.csv` — per-event redistribution times + per-mode aggregates (Graph 2 data)
- `rq2_cumulative_load.csv` — cumulative load to new backend over time, per role (Graph 4 data)
- `rq2_transition_quality.csv` — per-mode p95 latency and failure rate in `compute_spike` (Graph 3 data)

**Logic**:

```
for each run_folder:
    mode = detect_mode(run_folder)  # from controller_env_snapshot.env
    events = run.events where kind == "spawn_done"
    stats  = load per_node_stats.csv
    role_fn = container_role from simple_metrics.py
  
    spawns_by_role = {}   # role -> list of (spawn_ts, container, network_id)
    for each spawn in events:
        spawn_role = role_fn(spawn.container)
        # Resolve network_id from per_node_stats (the new backend's first window)
        # or from the container name suffix (lan1/lan2).
        lan = extract_lan(spawn.container)  # "n1" or "n2" from name or stats
        spawns_by_role.setdefault(spawn_role, []).append(
            (spawn.ts, spawn.container, lan)
        )
    
    for role, spawns in spawns_by_role.items():
        for (spawn_ts, container, lan) in spawns:
            # ±45s isolation check: skip if another same-role, same-LAN
            # spawn occurred within 45s of this one.
            conflicts = [s for s in spawns
                         if s[2] == lan                           # same LAN
                         and s[0] != spawn_ts                     # not itself
                         and abs(s[0] - spawn_ts) <= 45.0]
            if conflicts:
                skip  # pool was still redistributing
            \n        # Role-aware temporal proximity MAC resolution
        before = set of server_ids with this role in stats
                 where window_end < spawn_ts
        after  = set of server_ids with this role in stats
                 where spawn_ts <= window_end <= spawn_ts + 15
        new_macs = after - before
      
        if len(new_macs) != 1:
            skip   # no unambiguous match (cooldown guarantees at most 1)
        mac = new_macs.pop()
      
        # Filter per_node_stats for this MAC, after spawn
        node_rows = stats[(stats.server_id == mac)
                          and (stats.window_end >= spawn_ts)]
        if node_rows is empty: skip
      
        # Select metric based on role
        metric_col = "request_count" if spawn_role == "compute" \
                     else "avg_connections"
      
        for each window w in node_rows:
            # Sum metric across eligible same-role backends at this window.
            # For storage: exclude PRIMARY (its write traffic makes it
            # structurally incomparable to secondaries).
            if spawn_role == "storage":
                peers = stats[(stats.role == spawn_role)
                              and (stats.window_end == w.window_end)
                              and (stats.member_state == "SECONDARY")]
            else:
                peers = stats[(stats.role == spawn_role)
                              and (stats.window_end == w.window_end)]
            total = sum(peers[metric_col])
            share = w[metric_col] / total
            time_since_spawn = w.timestamp - spawn_ts
            append (time_since_spawn, share) to profile[spawn_role]
        
        # Find equilibrium using dynamic N per window
        for each window w in node_rows (sliding window of 3):
            if spawn_role == "storage":
                peers_at_w = stats[(stats.role == spawn_role)
                                   and (stats.window_end == w.window_end)
                                   and (stats.member_state == "SECONDARY")]
            else:
                peers_at_w = stats[(stats.role == spawn_role)
                                   and (stats.window_end == w.window_end)]
            N = len(distinct server_ids in peers_at_w)
          
            shares_in_window = [s for (t, s) in profile_slice
                                where t in window]
            if all |s - expected_share| <= 0.10 for s in shares_in_window:
                equilibrium_ts = window[0].timestamp
                redistribution_s = equilibrium_ts - spawn_ts
                break
  
    # Aggregate profile across all spawns in this run, per role
    for role in ("compute", "storage"):
        group by time_since_spawn (1s bins)
        compute mean and std of share per bin
  
    # Write outputs per role
```

---

## Integration with Existing Toolchain

| Existing Tool                              | What it does for RQ2                                                                                |
| ------------------------------------------ | --------------------------------------------------------------------------------------------------- |
| `loader.py` (`run.events`)             | Provides`ElasticityEvent` list with `spawn_done` timestamps — consumed as input                |
| `simple_metrics.py` (`container_role`) | Maps container name prefix to role (`compute`/`storage`) — consumed as helper                  |
| `per_node_stats.csv`                     | Per-backend load metrics at 10 s window granularity — primary data source for Graphs 1, 2, 4       |
| `client_requests.csv`                    | Per-request latency/failure — data source for Graph 3                                              |
| `controller_env_snapshot.env`            | Mode detection — already captured by`post_run.sh`                                                |
| `cli_mechanism_compare`                  | Cross-run comparison — reusable as-is for RQ2                                                      |
| **NEW** `cli_rq2_redistribution`   | All RQ2-specific analysis — redistribution profiling, equilibrium detection, cross-mode comparison |

---

## Verification Checklist

- [ ] `cli_rq2_redistribution` runs without errors on a golden config run folder
- [ ] Detects scale-up events correctly (≥1 spawn in `compute_spike` phase)
- [ ] `request_share` values are in [0, 1] range
- [ ] `redistribution_time_s` is non-negative and plausible (< 120 s at this scale)
- [ ] Per-mode aggregates differ between modes (if they don't, the experiment may need more clients)
- [ ] Output CSVs have correct column schemas
- [ ] Graph scripts can consume output CSVs and produce the five specified graphs

---

## Summary

| Artifact                      | New or existing                                 | Lines                |
| ----------------------------- | ----------------------------------------------- | -------------------- |
| `cli_rq2_redistribution.py` | **New** (handles all Graphs 1–5)         | ~120                 |
| Graph generation scripts      | **New** (can reuse RQ1 plotting patterns) | ~50                  |
| **Total**               |                                                 | **~170 lines** |

No modifications to existing tools (`cli_simple_run`, `cli_phase_summary`, `cli_mechanism_compare`, `loader.py`) are required — the new CLI is self-contained and consumes the same run folder artifacts as existing tools.
