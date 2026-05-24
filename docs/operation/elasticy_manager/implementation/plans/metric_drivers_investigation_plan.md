# Metric Drivers Investigation Plan

This is the **umbrella plan** for the investigation started after run
`20260420_184217`. It states the research question, scopes the threads, and
delegates the concrete implementation work to three subsystem-specific
sub-plans.

## Bottom-line research question

> **Does adding nodes actually reduce CPU / T_db / T_proc for compute and
> storage, and if not, what does drive them?**

Motivation from run `20260420_184217`:

- CPU on compute **and** storage stayed at 75-87 % across every phase from
  `local_moderate` onwards, including the `demand_drop` phase (1 req/s/client)
   - load does not explain this.
- `T_db` jumped to ~120 ms in `local_moderate` and never recovered, climbing
  to ~700 ms in `cross_region_hotspot`.
- Storage hit its dynamic cap (6) in every stressed phase; compute hit its cap
  (5) only in `demand_drop`.
- Scale-down never fired during the 10 min `demand_drop` - only cooldown-skip
  log lines appear in the controller log.

Working hypothesis: **adding nodes may not be relieving the metric it is
intended to relieve**. In particular, `storage_count` may positively correlate
with `T_db_write` because new replicas extend the write-concern quorum floor.
To prove or falsify that we need (i) per-node time series, (ii) scale-down
path introspection, and (iii) a `T_db` decomposition that isolates
read vs write.

## Scope & threads

Four chosen variants, each owned by a subsystem plan:

| Thread | Variant | Owner plan |
|---|---|---|
| c3-ii  T_db decomposition | pymongo `CommandListener` + aggregator/controller/CSV propagation | [`../../../telemetry/implementation/db_timing_decomposition.md`](../../../telemetry/implementation/db_timing_decomposition.md) |
| b2-i   scale-down audit   | DEBUG per eval + INFO on arm edge | [`../scale_down_instrumentation.md`](../scale_down_instrumentation.md) |
| a2-i   per-node time series | `per_node_stats.csv` emitted by the collector | [`../../../testing/analysis_toolchain.md`](../../../testing/analysis_toolchain.md) |
| A2     analysis package   | `source/scripts/testing/analysis/` + 4 CLIs | [`../../../testing/analysis_toolchain.md`](../../../testing/analysis_toolchain.md) |

**Out of scope:** changing scaling thresholds or caps. Findings from this
investigation will inform a follow-up tuning proposal (to be tracked in
`scaling_threshold_tuning_and_caps.md`).

## Global design decisions

1. **Backward compatibility** across all three sub-plans: the analysis package
   runs best against runs produced *after* these changes but degrades
   gracefully on the old run `20260420_184217` (missing per-node CSV / missing
   decomposition columns -> affected charts are skipped with warnings).
2. **No extra validation run** - the next regular experiment doubles as
   validation of the new schema and instrumentation.
3. **No behavioural change** to scaling, VIP routing, or traffic generation.
   All three sub-plans add observability and analysis surface only.

## Implementation order

Order is producer -> transport -> consumer so each step leaves a working system.

1. **Telemetry plan** - steps 1-3 (edge server listener, aggregator, pydantic
   models) + domain CSV columns.
2. **Elasticity plan** - scale-down log instrumentation.
3. **Testing plan** - step 1 (per-node CSV) then steps 2-7 (analysis package).

All three can be merged independently; the analysis CLIs produce warnings
instead of crashing when upstream pieces are missing.

## End-to-end acceptance criteria

Running the next regular experiment after all three sub-plans ship must
produce:

1. `resource_stats.csv` with `avg_repl_lag_ms`, `avg_time_db_read_ms`,
   `avg_time_db_write_ms`, `avg_time_db_cmd_count` populated (non-zero during
   any request-carrying phase).
2. `per_node_stats.csv` present, with row count ~= sum(active containers) x
   windows.
3. Controller log at `LOG_LEVEL=DEBUG` contains exactly one
   `[scale-down] compute eval: ...` and one `[scale-down] storage eval: ...` per
   telemetry window.
4. `python -m source.scripts.testing.analysis.cli_overview --run-dir <dir>`
   produces `<dir>/analysis/overview.png` without errors.
5. `cli_tdb_drivers` prints a regression line of the form
   `T_db_write ~= a + b*storage_count + c*cross_region_ratio  (R^2 = ...)`.

If (5) shows `b > 0` for `storage_count` with a meaningful R^2, the
investigation has answered the bottom-line question in the negative for
storage: **adding storage nodes makes writes slower**, and the scale-up policy
is worsening the very metric it targets.

## Consolidated risk register

| Risk | Owner plan | Mitigation |
|---|---|---|
| `CommandListener` fires outside Flask context -> `RuntimeError` | telemetry | `try/except RuntimeError` around `g` access |
| `time_db_read + time_db_write != time_db_ms` exactly | telemetry | Documented as expected; gap is diagnostic |
| pymongo major-version bump changes listener threading | telemetry | Step-1 acceptance catches it; switch to thread-local keyed by request id if needed |
| DEBUG log volume floods logs | elasticity | ~= 720 lines/hour/LAN; gated by `LOG_LEVEL` |
| Log grammar drift breaks `cli_scale_down` | elasticity / testing | Grammar contract owned by the elasticity plan; sync edit required |
| `per_node_stats.csv` grows large on long runs | testing | 3.6 k rows/hour; split per phase if > 50 MB |
| Mixed-version rolling upgrade of aggregator/controller | telemetry | `.get(...,0)` + pydantic defaults |
| CPU inflation baseline on dynamic containers (unresolved) | - | Follow-up: see `scaling_threshold_tuning_and_caps.md`; not addressed here |

## Follow-ups

After this investigation lands and one full run has been analysed:

- Revisit `TAU_PROC_DOWN_MS` and `TAU_DB_DOWN_MS` if the `unreachable_report`
  shows the AND predicate is chronically unsatisfiable.
- Investigate the CPU floor on dynamic containers independently.
- If `b_storage_count > 0` confirmed: consider write-concern tuning and a cap
  on storage scale-up that depends on replication lag rather than CPU/T_db.




