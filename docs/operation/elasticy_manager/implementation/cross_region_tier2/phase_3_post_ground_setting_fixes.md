# Phase 3 — Post-Ground-Setting Fixes

**Status**: ✅ Implemented
**Depends on**: [Phase 2 — Cold-Start](./phase_2_cross_region_tier2_cold_start.md), [Ground-Setting Results](../../../testing/experiment/rq3/rq3_calibration/results.md)
**Feeds into**: [RQ3 Strategy Comparison](../../../testing/experiment/rq3/rq3_strategy_comparison/experiment_plan.md)

---

## Primary Outcome

Two fixes identified during ground-setting:

1. **Warm standby pre-spawn** fails because `resolve_peer_primary` returns `None` during controller `__init__` — peer topology not yet published.
2. **Cross-region scale-down oscillation**: same-LAN LIFO scale-down removes cross-region replicas; breach re-fires; spawn→remove cycle repeats. The root cause is using p95 as both activation and sustainment signal — the replica's presence suppresses the metric that justified it.

---

## Fix 1 — Warm Standby Pre-Spawn Deferral

### Problem

```python
# In __init__, called before peer ZMQ topology arrives:
self._prepare_cross_region_reserve_if_needed()
  → resolve_peer_primary("lan1") → None (peer hasn't published roles yet)
  → logs warning, returns
```

The slot stays in `NONE` forever because `_prepare_cross_region_reserve_if_needed` is only called once at startup.

### Fix

Move the pre-spawn call to the telemetry callback, mirroring how same-LAN reserve works (`_try_prepare_storage_reserve` is called every window). The slot init stays in `__init__`.

**`__init__`** (both `main_n1.py` and `main_n2.py`, lines 168–171):

```python
# Before:
if _CROSS_REGION_STORAGE_ENABLED and _CROSS_REGION_STORAGE_WARM:
    self._node_registry.init_cross_region_reserve_slot()
    self._prepare_cross_region_reserve_if_needed()

# After:
if _CROSS_REGION_STORAGE_ENABLED and _CROSS_REGION_STORAGE_WARM:
    self._node_registry.init_cross_region_reserve_slot()
    # Pre-spawn deferred to first telemetry callback — peer topology
    # must be available before resolve_peer_primary can succeed.
```

**`_on_telemetry_update`** (both files, after same-LAN reserve logic, before `_evaluate_cross_region_activation`):

```python
        # ── Cross-region warm standby: maintain reserve slot ────────
        # Deferred from __init__ — peer topology is now stable.
        # should_prepare_cross_region_reserve() guards on state=="NONE"
        # so the first successful resolve_peer_primary moves the slot
        # to PREPARING and subsequent windows are no-ops.
        self._prepare_cross_region_reserve_if_needed()

        # ── Cross-region warm standby: admit on pressure ────────────
        self._evaluate_cross_region_activation(summary)
```

### Why it works

- `should_prepare_cross_region_reserve()` → `state == "NONE"` — tries every window until success
- Window 1 (peer topology not ready): warns, returns. Window 2 (~10s later): topology stable, succeeds.
- `mark_cross_region_reserve_prepare_submitted()` sets state to `PREPARING` — prevents duplicate submissions
- Same pattern as same-LAN: `_try_prepare_storage_reserve` is called every window, guarded by `should_prepare_storage_reserve(lan)`

---

## Fix 2 — Cross-Region Scale-Down Lifecycle

### Problem

```
p95 > 1000ms → spawn cross-region replica → p95 drops to 50ms
→ same-LAN scale-down fires (domain underutilised)
→ removes replica → p95 > 1000ms again → spawn again → ...
```

The replica's presence suppresses the p95 signal. Using the same metric for activation and sustainment creates a control-loop paradox.

### Solution

Separate activation from sustainment:

| Decision | Signal | What it measures |
|---|---|---|
| **Activate** (spawn) | `t_db_p95_ms_per_lan > 1000` | Service quality degradation |
| **Sustain** (keep alive) | Cross-region read volume | Demand for remote data |
| **Deactivate** (scale down) | Read volume < floor for sustained windows | Demand subsided |

The activation signal tells us a replica is needed. The sustainment signal tells us it still is — regardless of what p95 looks like now that reads are local.

### Part A — Exclude Cross-Region from Same-LAN LIFO Scale-Down

**Where**: `main_n1.py` lines 576–592, same-LAN storage scale-down block.

**Current**:
```python
            if self._scaling_policy.evaluate_scale_down_storage(ds):
                node = self._node_registry.find_last_dynamic("storage")
                if node:
                    if not self._node_registry.can_scale_down_storage(node.mac, lan):
                        ...
                        self._scaling_policy.clear_scale_down_storage_window()
                    else:
                        ...
                        alert = self._node_registry.build_scale_down_alert(node.mac)
                        if alert:
                            self._elasticity.submit(alert)
                self._scaling_policy.clear_scale_down_storage_window()
```

**After**:
```python
            if self._scaling_policy.evaluate_scale_down_storage(ds):
                node = self._node_registry.find_last_dynamic("storage")
                if node:
                    # Cross-region nodes have their own demand-based
                    # lifecycle — same-LAN LIFO scale-down must skip them.
                    if node.owner_lan:
                        logger.debug(
                            "[scale-down] storage skip cross-region node %s (owner=%s)",
                            node.name, node.owner_lan,
                        )
                    elif not self._node_registry.can_scale_down_storage(node.mac, lan):
                        ...
                        self._scaling_policy.clear_scale_down_storage_window()
                    else:
                        ...
                        alert = self._node_registry.build_scale_down_alert(node.mac)
                        if alert:
                            self._elasticity.submit(alert)
                self._scaling_policy.clear_scale_down_storage_window()
```

Uses `elif` chain: cross-region check first, then existing reserve-floor check, then alert submission.

### Part B — Demand-Based Scale-Down Evaluator

**New env var** (`scaling_config.py`, after the cross-region policy vars):

```python
# Minimum cross-region read volume per telemetry window to sustain a
# cold-started cross-region replica.  When demand drops below this floor,
# the replica is eligible for scale-down.  Activation uses p95 > threshold;
# sustainment uses demand volume — two independent signals prevent the
# control-loop paradox where the replica's presence suppresses p95.
_CROSS_REGION_MIN_READS_TO_SUSTAIN = int(os.environ.get(
    "CROSS_REGION_MIN_READS_TO_SUSTAIN", "10"))
```

**New method** (`main_n1.py` and `main_n2.py`, in the cross-region methods section):

```python
def _evaluate_cross_region_scale_down(self, summary: TelemetrySummary) -> None:
    """Scale down cross-region replicas when demand subsides.

    Activation uses p95 DB time (service quality).  Sustainment uses
    cross-region read volume (demand).  These are independent so the
    replica's presence — which lowers p95 — does not suppress the
    sustainment measurement.

    Writes are excluded: they are not locality-sensitive and would
    inflate the demand signal without justifying a local replica.
    """
    _WRITE_OPS = frozenset({
        "insert_one", "insert_many",
        "update_one", "update_many", "replace_one",
        "delete_one", "delete_many", "bulk_write",
        "find_one_and_update", "find_one_and_replace", "find_one_and_delete",
    })

    for node in self._node_registry.list_dynamic("storage"):
        if not node.owner_lan or node.standby_reserved:
            continue

        # Count reads targeting the owner LAN's data this window
        # across all local edge servers.
        total_reads = 0
        for srv in summary.servers.values():
            for _coll, ops in srv.op_counters.get(node.owner_lan, {}).items():
                total_reads += sum(
                    count for op, count in ops.items()
                    if op not in _WRITE_OPS
                )

        if total_reads < _CROSS_REGION_MIN_READS_TO_SUSTAIN:
            logger.info(
                "[cross-region-scale-down] demand subsided for owner=%s "
                "node=%s reads=%d floor=%d — submitting scale-down",
                node.owner_lan, node.name, total_reads,
                _CROSS_REGION_MIN_READS_TO_SUSTAIN,
            )
            alert = self._node_registry.build_scale_down_alert(node.mac)
            if alert:
                self._elasticity.submit(alert)
```

**Integration** (`_on_telemetry_update`, after `_evaluate_cross_region_activation`):

```python
        # ── Cross-region warm standby: admit on pressure ────────────
        self._evaluate_cross_region_activation(summary)

        # ── Cross-region scale-down: remove when demand subsides ────
        self._evaluate_cross_region_scale_down(summary)
```

**New import** (both `main_n1.py` and `main_n2.py`):

```python
from .scaling_config import (
    ...
    _CROSS_REGION_MIN_READS_TO_SUSTAIN,   # ← add
)
```

---

## Files Changed

| # | File | Change | Lines |
|---|---|---|---|
| 1 | `scaling_config.py` | New env vars `_CROSS_REGION_MIN_READS_TO_SUSTAIN`, `_CROSS_REGION_SUSTAIN_WINDOWS_M`, `_CROSS_REGION_SUSTAIN_WINDOWS_N` | ~12 |
| 2 | `main_n1.py` | Defer pre-spawn + LIFO exclusion + demand-based scale-down with sliding-window debounce + import | ~55 |
| 3 | `main_n2.py` | Same changes (mirror) | ~55 |

---

## Verification

Re-run the cold-start validation with `rq3_tier2_cold.env` and `phases_rq3_calibration.json`:

- [ ] Cross-region node survives through `sustained_pressure` phase (reads ≥ 20, debounce ring stays below M-of-N → no scale-down)
- [ ] Cross-region node scales down during `cooldown` phase (reads < 20 for M-of-N consecutive windows → debounce arms → scale-down fires)
- [ ] Single-window dips do NOT trigger scale-down (debounce: 2-of-3 means 1 window below floor is insufficient)
- [ ] Same-LAN storage scale-down still works (regression — cross-region exclusion only affects `owner_lan` nodes)
- [ ] Warm standby pre-spawns successfully (peer topology available at first telemetry window)
- [ ] No tracebacks

---

## Design Rationale

**Why a sliding-window debounce (2-of-3)?** The initial implementation fired
scale-down on the first window below threshold — no debounce.  V1 validation
revealed a single-window dip (reads=19 at threshold=20) triggered an
unnecessary scale-down→re-spawn of dyn7→dyn8 during pressure.  The same-LAN
scale-down evaluator (`ScalingPolicy.evaluate_scale_down_storage`) already
uses M-of-N debounce (7-of-12); cross-region sustainment needed the same
pattern.  The window is shorter (2-of-3, 20–30s) because demand drops faster
than CPU/utilization — cooldown reads stay at 0–15 for many consecutive
windows, so 2-of-3 adds at most 20s of latency to a correct scale-down while
filtering out single-window noise.

**Per-node rings with cleanup.** Each cross-region node gets its own
`deque[bool]` ring keyed by MAC.  When a node is removed from the registry
(scaled down or absent), its ring is cleaned up at the end of the evaluation
window — no unbounded memory growth.

**Why count reads only?** Writes (insert, update, delete) are not
locality-sensitive — they must go to the primary regardless of where the
replica lives. Counting writes would inflate the demand signal without
justifying a local replica. The Tier 1 hotness module already uses this
same distinction (`_WRITE_OPS` in `selective_sync/hotness.py`).

**Why not make this part of Phase 2?** Phase 2 is implemented and tested.
These fixes address issues discovered during ground-setting that were not
foreseeable during Phase 2 planning. They are logically Phase 3 — post-
validation hardening — and do not change the Phase 2 design, only its
scale-down behavior.
