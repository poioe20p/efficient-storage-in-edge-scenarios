# Storage Scale-Up Cooldown — Implementation Plan

> **Created:** 2026-04-13
> **Status:** Implemented

## Problem

Test run `20260413_183132` revealed runaway storage scaling:

- **LAN1:** 20 scale-up triggers → 8 active storage nodes
- **LAN2:** 16 storage nodes

**Root cause:** No scale-UP cooldown existed. Each new container increases host
CPU, which raises the degradation score, which triggers another scale-up within
the next telemetry window. The 1-of-3 sliding window fired instantly (one bad
window was enough), amplifying the feedback loop.

## Changes

### 1. Scale-up cooldown (`_SCALEUP_STORAGE_COOLDOWN_S`)

| Parameter | Default | Env var |
| --- | --- | --- |
| `_SCALEUP_STORAGE_COOLDOWN_S` | `120` s | `SCALEUP_STORAGE_COOLDOWN_S` |

After submitting a `DataAlert`, storage scale-up evaluation is suppressed for
120 seconds. This gives the new node time to join the replica set, begin
absorbing load, and let host CPU settle.

**Code change:** Extracted `_evaluate_storage_scale_up()` from the inline
storage block in `_evaluate_scale_up()`. The parent method now checks the
cooldown before delegating:

```python
scaleup_storage_cooldown_remaining = _SCALEUP_STORAGE_COOLDOWN_S - (now - self._last_storage_scale_up_ts)
if scaleup_storage_cooldown_remaining > 0:
    logger.debug("[scale-up] storage within %.0fs scale-up cooldown — skipping", ...)
else:
    self._evaluate_storage_scale_up(ds, lan, network_id)
```

### 2. Sliding window tightening

| Parameter | Old | New |
| --- | --- | --- |
| `SCALEUP_STORAGE_WINDOW_SIZE` | 3 | **5** |
| `SCALEUP_STORAGE_REQUIRED` | 1 | **2** |

Previously 1-of-3 (fires on a single bad window). Now 2-of-5 — requires two
degraded windows within five, filtering transient spikes.

### 3. Evaluation ordering

- **main_n1.py:** storage first → compute second (unchanged)
- **main_n2.py:** compute first → storage second (unchanged)

Both files now share the same `_evaluate_storage_scale_up()` extraction and
cooldown check pattern.

## Files Modified

| File | Change |
| --- | --- |
| `source/sdn_controller/main_n1.py` | Constants, cooldown, method extraction |
| `source/sdn_controller/main_n2.py` | Constants, cooldown, method extraction |
| `docs/operation/elasticy_manager/elasticity_overview.md` | Parameter table updated |
