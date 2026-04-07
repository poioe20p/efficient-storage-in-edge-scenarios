# Scale-Up Trigger — Implementation Plan

## Overview

Replace the current single-window, latency-only scale-up trigger with a
**dual-condition (CPU AND latency), 2-consecutive-window** guard. The change
is additive to `main_n1.py` — only the threshold evaluation block inside
`_on_telemetry_update()` and the module-level env var reads change.

This plan is a companion to `node_removal_plan.md`. Both live in
`_on_telemetry_update()` and share the same `is_busy()` guard and
cross-direction counter reset mechanism.

> **Note:** `node_removal_plan.md` references 3 consecutive windows for
> scale-up in its constraints narrative. The authoritative value is **2**
> (established here). `node_removal_plan.md` needs a minor update to its
> narrative to reflect this.

---

## Problem with the Current Approach

The current trigger fires on the **first single window** in which either
`avg_time_proc_ms > TAU_PROC_MS` or `avg_time_db_ms > TAU_DADOS_MS`.

Two problems:

1. **Latency alone is ambiguous.** `avg_time_db_ms` is measured at the edge
   server as the round-trip time of a pymongo operation. A single large result
   set takes longer regardless of storage node count — VIP routes the entire
   request to **one** node. The latency is data-bound, not capacity-bound.
   Adding nodes does not help. Same applies to `avg_time_proc_ms`: processing
   a large payload takes time on one server regardless of fleet size.
2. **A single window is not a sustained signal.** One delayed request or a
   brief GC pause can push the domain average over the threshold for a single
   window. Spawning a new container in response is wasteful and noisy.

---

## Dual-Condition Rationale

Requiring **both** CPU and latency to exceed their thresholds simultaneously
removes the ambiguity:

| CPU state | Latency state | Meaning                                      | Action                |
| --------- | ------------- | -------------------------------------------- | --------------------- |
| High      | High          | System saturated**and** users affected | **Scale up** ✓ |
| High      | Low           | Working hard but keeping up                  | Do nothing            |
| Low       | High          | Large query / data-bound, not a capacity gap | Do nothing            |
| Low       | Low           | System idle                                  | Scale-down territory  |

CPU captures capacity saturation; latency confirms user impact. Neither alone
is sufficient.

---

## Asymmetric Window Counts

| Direction  | Windows     | Wall-clock (WINDOW_S=10 s) | Rationale                                                                                                        |
| ---------- | ----------- | -------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Scale-up   | **2** | 20 s                       | Domain summary is already aggregated — a reliable signal; react fast to genuine saturation                      |
| Scale-down | **9** | 90 s                       | Must distinguish genuine idle from post-spike recovery; 4.5× asymmetry follows "scale up fast, scale down slow" |

This mirrors industry practice: K8s HPA uses a 5-minute stabilization window
for scale-down vs 0 s for scale-up; AWS defaults to 300 s cooldown for
scale-down vs 60 s for scale-up.

---

## No Explicit Cooldown

An explicit cooldown timer is **not needed**. Three interlocking mechanisms
provide equivalent protection without the added state:

| Mechanism                 | What it prevents                                                                         |
| ------------------------- | ---------------------------------------------------------------------------------------- |
| `is_busy()`             | Any evaluation while an add/remove operation is executing (30–180 s natural pause)      |
| 2-window scale-up guard   | Reacting to a single-window spike                                                        |
| 9-window scale-down guard | Removing a node after a temporary lull                                                   |
| Cross-direction reset     | Scale-down immediately after scale-up — counter resets to 0, needs 9 fresh idle windows |
| Dual-condition            | Re-triggering scale-up from residual latency without CPU pressure                        |

| Scenario                         | What happens without a cooldown                                                                                                                 |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| Scale-up → immediate scale-down | Scale-down counter was reset to 0 by the scale-up. Needs 9 fresh idle windows (90 s). Not a risk.                                               |
| Scale-down → immediate scale-up | Scale-up counter was reset to 0 by the scale-down. Needs 2 fresh saturated windows. If load is genuinely that high, scaling back up is correct. |
| Scale-up → another scale-up     | `is_busy()` blocks during the 30–60 s operation. Then needs 2 fresh windows. Only fires if load is genuinely still saturated.                |

---

## Environment Variables

### New (scale-up thresholds)

| Env var                          | Default    | Description                                                                           |
| -------------------------------- | ---------- | ------------------------------------------------------------------------------------- |
| `TAU_CPU_UP`                   | `70`     | Compute domain avg CPU % above → saturation signal                                   |
| `TAU_PROC_UP_MS`               | `600`    | Compute domain avg processing latency above → user impact (replaces `TAU_PROC_MS`) |
| `TAU_STORAGE_CPU_UP`           | `70`     | Storage domain avg CPU % above → saturation signal                                   |
| `TAU_DB_UP_MS`                 | `150000` | Storage domain avg DB latency above → user impact (replaces `TAU_DADOS_MS`)        |
| `SCALE_UP_COMPUTE_CONSECUTIVE` | `2`      | Consecutive windows both above threshold before ComputeAlert fires                    |
| `SCALE_UP_STORAGE_CONSECUTIVE` | `2`      | Consecutive windows both above threshold before DataAlert fires                       |

### Changed (scale-down — for reference, already in `node_removal_plan.md`)

| Env var                            | Default | Description                                       |
| ---------------------------------- | ------- | ------------------------------------------------- |
| `SCALE_DOWN_COMPUTE_CONSECUTIVE` | 2       | Already split from old `SCALE_DOWN_CONSECUTIVE` |
| `SCALE_DOWN_STORAGE_CONSECUTIVE` | `9`   | Already split from old `SCALE_DOWN_CONSECUTIVE` |

### Removed

`TAU_PROC_MS` and `TAU_DADOS_MS` are replaced by `TAU_PROC_UP_MS` and
`TAU_DB_UP_MS` respectively. All `COOLDOWN_S` env vars are removed (no
explicit cooldown).

---

## Instance State

### Added to `__init__()`

```python
# Scale-up consecutive-window counters (Thread 2, guarded by is_busy())
self._scale_up_compute_consecutive: int = 0
self._scale_up_storage_consecutive: int = 0
```

### Removed

`_last_scale_event_ts` and any cooldown timestamp variables.

---

## Phase 1 — `main_n1.py` Changes

### 1a — Module-level env var reads

Replace:

```python
# Latency thresholds that trigger Thread 3 alerts — tunable via env vars.
_TAU_PROC_MS  = float(os.environ.get("TAU_PROC_MS",  "600"))
_TAU_DADOS_MS = float(os.environ.get("TAU_DADOS_MS", "150000"))
```

With:

```python
# Scale-up thresholds — both CPU and latency must breach simultaneously.
# CPU removes latency ambiguity: high latency from a large query looks the
# same as high latency from CPU saturation; CPU presence distinguishes them.
_TAU_CPU_UP             = float(os.environ.get("TAU_CPU_UP",             "70"))
_TAU_PROC_UP_MS         = float(os.environ.get("TAU_PROC_UP_MS",         "600"))
_TAU_STORAGE_CPU_UP     = float(os.environ.get("TAU_STORAGE_CPU_UP",     "70"))
_TAU_DB_UP_MS           = float(os.environ.get("TAU_DB_UP_MS",           "150000"))
_SCALE_UP_COMPUTE_CONSECUTIVE = int(os.environ.get("SCALE_UP_COMPUTE_CONSECUTIVE", "2"))
_SCALE_UP_STORAGE_CONSECUTIVE = int(os.environ.get("SCALE_UP_STORAGE_CONSECUTIVE", "2"))

# Scale-down thresholds (both CPU and latency must be below simultaneously).
_TAU_CPU_DOWN           = float(os.environ.get("TAU_CPU_DOWN",           "20"))
_TAU_PROC_DOWN_MS       = float(os.environ.get("TAU_PROC_DOWN_MS",       "100"))
_TAU_STORAGE_CPU_DOWN   = float(os.environ.get("TAU_STORAGE_CPU_DOWN",   "20"))
_TAU_DB_DOWN_MS         = float(os.environ.get("TAU_DB_DOWN_MS",         "50000"))
_SCALE_DOWN_COMPUTE_CONSECUTIVE = int(os.environ.get("SCALE_DOWN_COMPUTE_CONSECUTIVE", "9"))
_SCALE_DOWN_STORAGE_CONSECUTIVE = int(os.environ.get("SCALE_DOWN_STORAGE_CONSECUTIVE", "9"))
```

### 1b — `__init__()` state

Add after the existing instance variable initializations:

```python
# Scaling consecutive-window counters.
# Each type (compute / storage) tracks its own up and down counter
# independently. Counters are mutually exclusive within a type: a window
# that qualifies for scale-up resets the scale-down counter, and vice versa.
# No cooldown timestamps are used — is_busy() + these counters are sufficient.
self._scale_up_compute_consecutive:   int = 0
self._scale_up_storage_consecutive:   int = 0
self._scale_down_compute_consecutive: int = 0
self._scale_down_storage_consecutive: int = 0
```

### 1c — Aggregator: add `avg_storage_cpu_percent` to domain summary

**File:** `source/docker/local_state_server/aggregator.py`

The aggregator already has the fully-built `storage_servers` dict before it
constructs `domain_summary`. Add one field computed from it:

```python
        # ── Domain summary (HTTP only) ────────────────────────────────────────
        if http_events:
            avg_time_proc   = statistics.mean([e["time_total_ms"] - e["time_db_ms"] for e in http_events])
            avg_time_db     = statistics.mean([e["time_db_ms"] for e in http_events])
            avg_cpu_percent = statistics.mean([e["cpu_percent"] for e in http_events])
            peak_time_total = max(e["time_total_ms"] for e in http_events)
            total_requests  = len(http_events)
        else:
            avg_time_proc = avg_time_db = avg_cpu_percent = peak_time_total = 0.0
            total_requests = 0

        # Average CPU across all storage nodes (used by controller for scaling decisions).
        storage_cpus = [v["avg_cpu_percent"] for v in storage_servers.values()]
        avg_storage_cpu = sum(storage_cpus) / len(storage_cpus) if storage_cpus else 0.0

        summary = {
            ...
            "domain_summary": {
                "total_requests":         total_requests,
                "avg_time_proc_ms":       avg_time_proc,
                "avg_time_db_ms":         avg_time_db,
                "average_cpu_percent":    avg_cpu_percent,
                "peak_time_total_ms":     peak_time_total,
                "avg_storage_cpu_percent": avg_storage_cpu,   # ← NEW
            },
        }
```

### 1d — Pydantic model: add `avg_storage_cpu_percent` to `DomainSummary`

**File:** `source/sdn_controller/telemetry/models.py`

```python
class DomainSummary(BaseModel):
    total_requests: int
    avg_time_proc_ms: float
    avg_time_db_ms: float
    average_cpu_percent: float
    peak_time_total_ms: float
    avg_storage_cpu_percent: float = 0.0   # ← NEW; default 0.0 for backward compat
```

The `= 0.0` default keeps deserialization backward-compatible with aggregator
payloads from before this change.

### 1e — `_on_telemetry_update()` — threshold evaluation block

Replace the entire block after the `update_server_stats` / `update_storage_stats`
calls and the LAN parsing with:

```python
    # Skip all scaling evaluation while Thread 3 is executing an operation.
    # is_busy() returns True for the full duration of any add/remove (30–180 s).
    if self._elasticity.is_busy():
        logger.debug("elasticity busy — skipping scaling evaluation for %s", summary.network_id)
        return

    ds = summary.domain_summary
    storage_cpu = ds.avg_storage_cpu_percent  # aggregated by the aggregator

    # ── Evaluate conditions ──────────────────────────────────────────────────
    # Both CPU and latency must breach simultaneously. CPU removes the
    # latency ambiguity: a large query raises latency without saturating CPU.

    compute_up   = (ds.average_cpu_percent > _TAU_CPU_UP
                    and ds.avg_time_proc_ms > _TAU_PROC_UP_MS)
    compute_down = (ds.average_cpu_percent < _TAU_CPU_DOWN
                    and ds.avg_time_proc_ms < _TAU_PROC_DOWN_MS)

    data_up   = (storage_cpu > _TAU_STORAGE_CPU_UP
                 and ds.avg_time_db_ms > _TAU_DB_UP_MS)
    data_down = (storage_cpu < _TAU_STORAGE_CPU_DOWN
                 and ds.avg_time_db_ms < _TAU_DB_DOWN_MS)

    logger.debug(
        "[scaling] compute_up=%s compute_down=%s data_up=%s data_down=%s "
        "cpu=%.1f%% proc_ms=%.1f db_ms=%.1f storage_cpu=%.1f%%",
        compute_up, compute_down, data_up, data_down,
        ds.average_cpu_percent, ds.avg_time_proc_ms, ds.avg_time_db_ms, storage_cpu,
    )

    # ── Update counters (mutually exclusive within each type) ────────────────
    # A window that qualifies for scale-up resets the scale-down counter,
    # ensuring the scale-down needs N *fresh* below-threshold windows after
    # any scale-up, not windows accumulated before/during the operation.

    if compute_up:
        self._scale_up_compute_consecutive   += 1
        self._scale_down_compute_consecutive  = 0
    elif compute_down:
        self._scale_down_compute_consecutive += 1
        self._scale_up_compute_consecutive    = 0
    else:
        self._scale_up_compute_consecutive    = 0
        self._scale_down_compute_consecutive  = 0

    if data_up:
        self._scale_up_storage_consecutive   += 1
        self._scale_down_storage_consecutive  = 0
    elif data_down:
        self._scale_down_storage_consecutive += 1
        self._scale_up_storage_consecutive    = 0
    else:
        self._scale_up_storage_consecutive    = 0
        self._scale_down_storage_consecutive  = 0

    # ── Scale-up: compute ────────────────────────────────────────────────────
    if self._scale_up_compute_consecutive >= _SCALE_UP_COMPUTE_CONSECUTIVE:
        logger.info(
            "[scale-up] compute: cpu=%.1f%% > %.0f%% AND proc_ms=%.1f > %.0fms "
            "for %d consecutive windows — submitting ComputeAlert",
            ds.average_cpu_percent, _TAU_CPU_UP,
            ds.avg_time_proc_ms, _TAU_PROC_UP_MS,
            self._scale_up_compute_consecutive,
        )
        self._elasticity.submit_alert(
            ComputeAlert(lan=lan, network_id=summary.network_id)
        )
        # Reset opposing counter: need 9 fresh idle windows before scale-down.
        self._scale_down_compute_consecutive = 0

    # ── Scale-up: storage ────────────────────────────────────────────────────
    if self._scale_up_storage_consecutive >= _SCALE_UP_STORAGE_CONSECUTIVE:
        logger.info(
            "[scale-up] storage: storage_cpu=%.1f%% > %.0f%% AND db_ms=%.1f > %.0fms "
            "for %d consecutive windows — submitting DataAlert",
            storage_cpu, _TAU_STORAGE_CPU_UP,
            ds.avg_time_db_ms, _TAU_DB_UP_MS,
            self._scale_up_storage_consecutive,
        )
        self._elasticity.submit_alert(
            DataAlert(
                lan=lan,
                network_id=summary.network_id,
                rs_name=f"rs_net{lan}",
                primary_container=f"edge_storage_server_n{lan}",
            )
        )
        self._scale_down_storage_consecutive = 0

    # ── Scale-down: compute ──────────────────────────────────────────────────
    if self._scale_down_compute_consecutive >= _SCALE_DOWN_COMPUTE_CONSECUTIVE:
        logger.info(
            "[scale-down] compute: cpu=%.1f%% < %.0f%% AND proc_ms=%.1f < %.0fms "
            "for %d consecutive windows",
            ds.average_cpu_percent, _TAU_CPU_DOWN,
            ds.avg_time_proc_ms, _TAU_PROC_DOWN_MS,
            self._scale_down_compute_consecutive,
        )
        self._submit_scale_down_compute_alert(lan, summary)
        self._scale_up_compute_consecutive = 0

    # ── Scale-down: storage ──────────────────────────────────────────────────
    if self._scale_down_storage_consecutive >= _SCALE_DOWN_STORAGE_CONSECUTIVE:
        logger.info(
            "[scale-down] storage: storage_cpu=%.1f%% < %.0f%% AND db_ms=%.1f < %.0fms "
            "for %d consecutive windows",
            storage_cpu, _TAU_STORAGE_CPU_DOWN,
            ds.avg_time_db_ms, _TAU_DB_DOWN_MS,
            self._scale_down_storage_consecutive,
        )
        self._submit_scale_down_storage_alert(lan, summary)
        self._scale_up_storage_consecutive = 0
```

> `_submit_scale_down_compute_alert()` and `_submit_scale_down_storage_alert()`
> are the methods defined in `node_removal_plan.md` Phase 5. They look up the
> last dynamic node of the relevant type and submit the appropriate
> `ScaleDownComputeAlert` / `ScaleDownDataAlert` to the elasticity queue.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `source/docker/local_state_server/aggregator.py` | Modify | Add `avg_storage_cpu_percent` to `domain_summary` dict |
| `source/sdn_controller/telemetry/models.py` | Modify | Add `avg_storage_cpu_percent: float = 0.0` to `DomainSummary` |
| `source/sdn_controller/main_n1.py` | Modify | Replace module-level env vars, add `__init__` state, rewrite threshold evaluation block (no helper needed) |
| `docs/operation/elasticy_manager/implementation/node_removal_plan.md` | Minor update | Correct "3 consecutive windows" to **2**; remove `_domain_storage_cpu()` helper (now provided by aggregator) |

---

## Verification

| # | Test                                                            | What to check                                                           |
| - | --------------------------------------------------------------- | ----------------------------------------------------------------------- |
| 1 | CPU high + latency high × 2 windows                            | Scale-up alert fires; scale-down counter reset to 0                     |
| 2 | CPU high + latency low                                          | No scale-up (data-bound, not saturation)                                |
| 3 | CPU low + latency high                                          | No scale-up (large query, spare capacity)                               |
| 4 | 1 window above → 1 window below → 1 window above              | Counter resets; no alert fires until 2 consecutive                      |
| 5 | Scale-up fires → load drops → 9 windows below both thresholds | Scale-down fires (needs all 9 because counter reset to 0 on scale-up)   |
| 6 | Scale-down fires → load spikes → 2 windows above thresholds   | Scale-up fires (counter reset to 0 on scale-down, then 2 fresh windows) |
| 7 | `is_busy()=True` during add/remove                            | No counter updates, no alerts at all                                    |
| 8 | Compute saturated, storage not                                  | ComputeAlert fires; storage counters unaffected                         |
| 9 | Storage saturated, compute not                                  | DataAlert fires; compute counters unaffected                            |

---

## Design Decisions

| Decision                                            | Rationale                                                                                                                                                                                                                                            |
| --------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CPU AND latency (not OR)                            | Latency alone is ambiguous: a large query raises latency without saturating CPU — adding nodes doesn't help because VIP routes the whole request to one node                                                                                        |
| 2 windows for scale-up                              | Domain summary is pre-aggregated across all edge servers — already a reliable signal; react fast to genuine saturation                                                                                                                              |
| 9 windows for scale-down                            | 4.5× asymmetry follows "scale up fast, scale down slow"; must distinguish genuine idle from post-spike recovery                                                                                                                                     |
| No cooldown timer                                   | `is_busy()` provides a natural pause (30–180 s per operation); cross-direction reset requires 9 fresh windows before opposing action; dual-condition blocks false re-triggers. An explicit timer adds state complexity without adding protection. |
| Storage CPU in `DomainSummary` | `DomainSummary.average_cpu_percent` covers only HTTP edge servers (computed from HTTP request events). Storage CPU is now aggregated by the aggregator into `avg_storage_cpu_percent` — the aggregator already has `storage_servers` fully built before constructing `domain_summary`, so no extra work is needed on the controller side. The controller-side `_domain_storage_cpu()` helper is **not needed**. |
| Counters reset on opposing event, not on alert fire | Alert may fire and trigger `is_busy()` immediately, but the counter reset happens before `is_busy()` returns True. Resetting on the event ensures the full window sequence is always fresh.                                                      |
| Replication lag rejected                            | Each secondary independently applies the full write stream; adding more secondaries doesn't reduce replication work on existing ones. If a secondary is CPU-saturated from reads (slowing oplog application), CPU already captures that directly.    |
