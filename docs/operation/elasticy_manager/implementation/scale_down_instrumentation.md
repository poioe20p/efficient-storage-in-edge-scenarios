# Scale-Down Instrumentation

## Objective

Make the scale-down decision path observable. Today, `scaling_policy.py` only
logs when an eval is skipped (busy manager, within cooldown); it is silent
about whether the predicate itself was satisfied, how many consecutive windows
have been "below threshold", and when the sliding window becomes armed. This
makes it impossible to tell — from logs alone — whether scale-down never fired
because CPU/T_proc/T_db never dropped below the thresholds, or because the
arm-count was reset by intermittent spikes, or because cooldown/busy always
pre-empted the eval.

Goal: one DEBUG line per eval carrying every predicate input, plus a one-shot
INFO line on the rising edge of `armed`. **No behavioural change** to the
predicate.

## Impact on the elasticity mechanism

Reference: [`../elasticity_overview.md`](../elasticity_overview.md).

- Thread 2 decision engine (`scaling_policy.evaluate_scale_down_compute` /
  `evaluate_scale_down_storage`) gains instrumentation; return value, sliding
  window, and cooldown logic are unchanged.
- Thread 3 dispatcher is not touched.
- Observability surface: new DEBUG lines become the primary artifact consumed
  by the scale-down audit CLI defined in the testing plan
  ([`analysis_toolchain_plan.md`](../../testing/analysis_toolchain_plan.md)'s
  `cli_scale_down`). The CLI reconstructs the same predicate from CSV and
  cross-checks it against these log lines.
- Existing `busy` / within-cooldown log lines are retained; this plan adds to
  them, not replaces them.

---

## File map

| Action | Path |
|---|---|
| Edit | `source/sdn_controller/scaling_policy.py` |

---

## Execution

Add a `prev_armed` flag per tier to detect the `False → True` edge transition.

```python
# source/sdn_controller/scaling_policy.py
def __init__(self, ...):
    # ... existing init ...
    self._prev_scale_down_compute_armed = False
    self._prev_scale_down_storage_armed = False


def evaluate_scale_down_compute(self, ds: DomainSummary) -> bool:
    if ds.avg_time_proc_ms > _SCALE_DOWN_PROC_TIMEOUT_CEILING_MS:
        logger.debug(
            "[scale-down] compute eval: proc=%.1f exceeds ceiling (%.0f) — window skipped",
            ds.avg_time_proc_ms, _SCALE_DOWN_PROC_TIMEOUT_CEILING_MS,
        )
        return False

    below = (ds.average_cpu_percent < _TAU_CPU_DOWN
             and ds.avg_time_proc_ms < _TAU_PROC_DOWN_MS)
    self._scale_down_compute_window.append(below)
    hits = sum(self._scale_down_compute_window)
    armed = hits >= _SCALE_DOWN_COMPUTE_REQUIRED

    logger.debug(
        "[scale-down] compute eval: cpu=%.1f/%.0f proc=%.1f/%.1f below=%s hits=%d/%d armed=%s",
        ds.average_cpu_percent, _TAU_CPU_DOWN,
        ds.avg_time_proc_ms, _TAU_PROC_DOWN_MS,
        below, hits, _SCALE_DOWN_COMPUTE_REQUIRED, armed,
    )
    if armed and not self._prev_scale_down_compute_armed:
        logger.info(
            "[scale-down] compute ARMED: hits=%d/%d cpu=%.1f proc=%.1f",
            hits, _SCALE_DOWN_COMPUTE_REQUIRED,
            ds.average_cpu_percent, ds.avg_time_proc_ms,
        )
    self._prev_scale_down_compute_armed = armed
    return armed


def evaluate_scale_down_storage(self, ds: DomainSummary) -> bool:
    if ds.avg_time_db_ms > _SCALE_DOWN_DB_TIMEOUT_CEILING_MS:
        logger.debug(
            "[scale-down] storage eval: db=%.1f exceeds ceiling (%.0f) — window skipped",
            ds.avg_time_db_ms, _SCALE_DOWN_DB_TIMEOUT_CEILING_MS,
        )
        return False

    below = (ds.avg_storage_cpu_percent < _TAU_STORAGE_CPU_DOWN
             and ds.avg_time_db_ms < _TAU_DB_DOWN_MS)
    self._scale_down_storage_window.append(below)
    hits = sum(self._scale_down_storage_window)
    armed = hits >= _SCALE_DOWN_STORAGE_REQUIRED

    logger.debug(
        "[scale-down] storage eval: stCpu=%.1f/%.0f db=%.1f/%.0f below=%s hits=%d/%d armed=%s",
        ds.avg_storage_cpu_percent, _TAU_STORAGE_CPU_DOWN,
        ds.avg_time_db_ms, _TAU_DB_DOWN_MS,
        below, hits, _SCALE_DOWN_STORAGE_REQUIRED, armed,
    )
    if armed and not self._prev_scale_down_storage_armed:
        logger.info(
            "[scale-down] storage ARMED: hits=%d/%d stCpu=%.1f db=%.1f",
            hits, _SCALE_DOWN_STORAGE_REQUIRED,
            ds.avg_storage_cpu_percent, ds.avg_time_db_ms,
        )
    self._prev_scale_down_storage_armed = armed
    return armed
```

## Log grammar (stable contract for log consumers)

```
[scale-down] <tier> eval: cpu=<f>/<f> proc=<f>/<f> below=<bool> hits=<n>/<N> armed=<bool>
[scale-down] <tier> eval: stCpu=<f>/<f> db=<f>/<f> below=<bool> hits=<n>/<N> armed=<bool>
[scale-down] <tier> eval: <metric>=<f> exceeds ceiling (<f>) — window skipped
[scale-down] <tier> ARMED: hits=<n>/<N> <metric>=<f> <metric>=<f>
```

**Ceiling-skip semantics.** When `T_proc` or `T_db` exceeds the configured
timeout ceiling (`_SCALE_DOWN_*_TIMEOUT_CEILING_MS`), the predicate returns
`False` **without appending to the sliding deque** — the window is
indeterminate (likely an RS election or network blip) and must not reset the
arm counter. Consumers reconstructing the predicate from CSV must exclude
ceiling-skipped windows from the hit count, otherwise their reconstructed
`hits=n/N` will drift from the controller's.

This format **replaces** the pre-existing ceiling-skip lines in
`scaling_policy.py` (`[scale-down] compute: avg_time_proc_ms=X.Y exceeds
timeout ceiling (Z) — skipping window`). Any external log consumer that
matched the old format must be updated.

Regex used by `cli_scale_down`:

```python
_RE_DOWN_EVAL = re.compile(
    r"\[scale-down\] (compute|storage) eval: "
    r"(?:cpu|stCpu)=([\d.]+)/[\d.]+ "
    r"(?:proc|db)=([\d.]+)/[\d.]+ "
    r"below=(\w+) hits=(\d+)/(\d+) armed=(\w+)"
)
_RE_DOWN_CEILING = re.compile(
    r"\[scale-down\] (compute|storage) eval: "
    r"(proc|db)=([\d.]+) exceeds ceiling \(([\d.]+)\) — window skipped"
)
_RE_ARMED = re.compile(r"\[scale-down\] (compute|storage) ARMED: hits=(\d+)/(\d+)")
```

## Acceptance

1. Running a controller at `LOG_LEVEL=DEBUG` produces exactly one `[scale-down]
   <tier> eval:` line per tier per telemetry window — no more, no less.
2. During a sustained low-load phase, the `hits=n/N` counter increments
   monotonically until `armed=True`, at which point one `ARMED` INFO line is
   emitted and no further `ARMED` lines are emitted unless `armed` drops back
   to `False` and rises again.
3. Scale-down behaviour (whether it fires) is bit-identical to the previous
   version on a replayed telemetry stream.

## Risks

| Risk | Mitigation |
|---|---|
| DEBUG volume floods logs | ~1 line per tier per 10 s window per LAN ≈ 720 lines/hour/LAN. Acceptable; gated by `LOG_LEVEL`. |
| `prev_armed` flag not thread-safe | `scaling_policy` state is accessed only from Thread 2's single callback path; no locking required. |
| Log grammar drift breaks consumers | Regex contract documented above; any change requires a sync edit of `cli_scale_down`. |

## Overview file changes — `elasticity_overview.md`

The following edits to [`../elasticity_overview.md`](../elasticity_overview.md)
are required so the overview reflects the new observability surface.

### 1. Scale-Down Sliding Window — add an instrumentation paragraph

Append to the **"Scale-Down Sliding Window"** subsection:

> **Instrumentation (from `implementation/scale_down_instrumentation.md`).**
> Each evaluation emits a single DEBUG line carrying all predicate inputs
> (`cpu`, `proc`/`db`, `below`, `hits/required`, `armed`); a one-shot INFO
> line is emitted on the rising edge of `armed`. Behaviour of the predicate
> is unchanged. Log grammar is defined as a stable contract consumed by the
> analysis toolchain (`cli_scale_down`).

### 2. Anti-Thrashing Mechanisms — no change to the table

The existing table is unaffected. Add a footnote under the table:

> Scale-down evaluation transitions are observable via the DEBUG/INFO log
> lines specified in [`implementation/scale_down_instrumentation.md`](implementation/scale_down_instrumentation.md).

### 3. New section — "Implementation Plans"

Add a new top-level section near the end of the overview (before or next to
**"Node Addition"**):

```markdown
## Implementation Plans

- [`implementation/metric_drivers_investigation_plan.md`](implementation/metric_drivers_investigation_plan.md)
  — umbrella investigation into what actually drives CPU / T_db / T_proc.
- [`implementation/scale_down_instrumentation.md`](implementation/scale_down_instrumentation.md)
  — DEBUG/INFO observability for the scale-down decision path.
- [`implementation/scaling_threshold_tuning_and_caps.md`](implementation/scaling_threshold_tuning_and_caps.md)
  — threshold tuning and hard-cap rationale (existing).
```

## Cross-references

- Umbrella investigation: [`./metric_drivers_investigation_plan.md`](./metric_drivers_investigation_plan.md)
- Log consumer: [`../../testing/analysis_toolchain_plan.md`](../../testing/analysis_toolchain_plan.md) (`cli_scale_down`)
