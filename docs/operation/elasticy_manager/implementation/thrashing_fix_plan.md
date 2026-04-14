# Scale-Up / Scale-Down Thrashing Fix — Implementation Plan

> **Status:** Implemented (Fix A, Fix C). Fix B partially superseded — see below.  
> **Motivation:** Analysis of the `20260411_235936` test run (see
> [`testing_overview.md`](../../testing/testing_overview.md) for experiment
> results and [`todo.md`](../../todo.md) for the task backlog).
>
> **Partial supersession (2026-04-13):** Fix B's threshold values (τ=0.70,
> 2-of-5) were further refined. **Storage** now uses a separate predictive
> adaptive threshold (base=0.25, +0.10/node, max=0.65, 1-of-3 window);
> **compute** uses τ=0.40, 2-of-5. Fix A's storage cooldown is updated from
> 75 s to **120 s** and storage scale-down window from 7/12 to **9/15**.
> See [`predictive_threshold_and_async_rs_plan.md`](predictive_threshold_and_async_rs_plan.md).

---

## Overview

During the `compute_spike` phase of the 2026-04-11 test run the elasticity
manager entered a **thrashing loop**: it scaled up a new node, then immediately
decided the cluster was under-utilised (because the new node hadn't started
serving yet) and scaled it back down — before the node ever handled a single
request.

**Impact:** 5 415 HTTP 503 errors + 63 timeouts across ~4 minutes (72 % on
lan1).

This plan addresses **three independent root causes** that combined to produce
the loop. Each fix is self-contained and can be implemented and verified in
isolation.

| Fix | Root Cause | Section |
|-----|-----------|---------|
| A — Scale-down cooldown timer | No grace period after scale-up | [§ Fix A](#fix-a--scale-down-cooldown-after-scale-up) |
| B — Threshold tuning | τ=0.85 / 3-of-5 too high and slow | [§ Fix B](#fix-b--scale-up-threshold-tuning) |
| C — Birth-grace for absent-node detection | Boot time counted as "absent" | [§ Fix C](#fix-c--birth-grace-for-absent-node-detection) |

---

## Observed Timeline (abbreviated)

| Time      | LAN  | Event |
|-----------|------|-------|
| 23:12:48  | lan1 | Storage score 0.48, compute 0.46 — visible degradation |
| 23:13:18  | lan1 | First window above τ (score 1.62, T_db 156 ms) — window 1/5 |
| 23:13:36  | lan2 | Scale-up triggered (3/5) |
| 23:13:38  | lan1 | Scale-up triggered (3/5), spawns `edge_storage_lan1_dyn1` |
| 23:13:49  | both | **First client errors appear** (503 + timeouts) |
| 23:14:08  | lan1 | Spawns `edge_server_lan1_dyn2` (30 s after storage) |
| **23:15:18** | lan1 | `edge_server_lan1_dyn2` **scaled DOWN** — 7/8 windows idle (never served traffic) |
| **23:15:26** | lan2 | `edge_server_lan2_dyn1` **scaled DOWN** — 7/9 windows idle |
| **23:15:48** | lan1 | `edge_storage_lan1_dyn1` **scaled DOWN** — removal FAILED |
| 23:17:49  | —    | Last client error; system slowly stabilises |

---

## Fix A — Scale-Down Cooldown After Scale-Up

### Problem

When `_evaluate_scale_up` triggers, it clears both the scale-up **and**
scale-down sliding windows:

```python
# main_n1.py  _evaluate_scale_up  (current — around line 283-299)
# (logger.info() call between the if-check and clear() omitted for brevity)
if sum(self._scale_up_storage_window) >= _SCALE_UP_REQUIRED:
    logger.info(...)                                # full log call in source
    self._scale_up_storage_window.clear()
    self._scale_down_storage_window.clear()     # cross-direction reset
    self._elasticity.submit_alert(
        DataAlert(
            lan=lan,
            network_id=network_id,
            rs_name=f"rs_net{lan}",
            primary_container=f"edge_storage_server_n{lan}",
        )
    )
```

The clear resets the scale-down window to zero — but it doesn't **pause** it.
As soon as the next telemetry window arrives (10 s), `_evaluate_scale_down_*`
starts appending again. If the load spike that triggered the scale-up has
subsided — or the new node's capacity is still pending — the existing nodes
appear underutilised and below-threshold windows accumulate normally. After
just 7 below-threshold windows (70 s), the scale-down fires and removes the
node that was just spawned.

### Proposed Change

Add **per-tier cooldown timestamps** — one for storage, one for compute —
set on their respective scale-up events. Skip the corresponding scale-down
evaluation until the tier-specific cooldown has elapsed.

Storage nodes take significantly longer to become ready than compute nodes
(RS initialisation + data sync ≈ 30 s vs container start ≈ 10–15 s), so the
cooldown periods are sized accordingly.

#### New Environment Variables

| Variable | Default | Unit | Purpose |
|----------|---------|------|---------|
| `SCALEDOWN_STORAGE_COOLDOWN_S` | `75` | seconds | Time after a **storage** scale-up during which storage scale-down is suppressed. Accounts for RS join (~30 s) + VIP propagation (~10 s) + initial traffic ramp + safety margin. |
| `SCALEDOWN_COMPUTE_COOLDOWN_S` | `40` | seconds | Time after a **compute** scale-up during which compute scale-down is suppressed. Accounts for container boot (~10–15 s) + VIP registration + safety margin. |

#### Code — module-level constants (after existing scale-down env vars)

```python
# main_n1.py — new constants, after the scale-down sliding-window block
_SCALEDOWN_STORAGE_COOLDOWN_S = float(os.environ.get("SCALEDOWN_STORAGE_COOLDOWN_S", "75"))
_SCALEDOWN_COMPUTE_COOLDOWN_S = float(os.environ.get("SCALEDOWN_COMPUTE_COOLDOWN_S", "40"))
```

#### Code — `__init__` (new instance attributes)

Add after the scale-down sliding-window deques:

```python
# Per-tier cooldowns: suppress scale-down for a grace period after scale-up.
# Initialised to -inf so the cooldown condition is never true at startup
# (time.monotonic() starts from an arbitrary reference, often system boot).
self._last_storage_scale_up_ts: float = float('-inf')
self._last_compute_scale_up_ts: float = float('-inf')
```

#### Code — `_evaluate_scale_up` (record per-tier timestamp on trigger)

In the storage trigger block, **after the `submit_alert` call**, record the
storage timestamp. Same for compute:

```python
# Storage trigger (line ~283 area)
if sum(self._scale_up_storage_window) >= _SCALE_UP_REQUIRED:
    ...
    self._elasticity.submit_alert(DataAlert(...))
    self._last_storage_scale_up_ts = time.monotonic()    # ← NEW

# Compute trigger (line ~318 area)
if sum(self._scale_up_compute_window) >= _SCALE_UP_REQUIRED:
    ...
    self._elasticity.submit_alert(ComputeAlert(...))
    self._last_compute_scale_up_ts = time.monotonic()    # ← NEW
```

#### Code — `_on_telemetry_update` (per-tier guards before scale-down evaluation)

Replace the current late section:

```python
# Current code (around line 175):
self._evaluate_scale_up(ds, lan, summary.network_id)
self._evaluate_scale_down_compute(ds)
self._evaluate_scale_down_storage(ds)
```

With:

```python
self._evaluate_scale_up(ds, lan, summary.network_id)

now = time.monotonic()

compute_cooldown_remaining = _SCALEDOWN_COMPUTE_COOLDOWN_S - (now - self._last_compute_scale_up_ts)
if compute_cooldown_remaining > 0:
    logger.debug(
        "[scale-down] compute within %.0fs cooldown — skipping",
        compute_cooldown_remaining,
    )
else:
    self._evaluate_scale_down_compute(ds)

storage_cooldown_remaining = _SCALEDOWN_STORAGE_COOLDOWN_S - (now - self._last_storage_scale_up_ts)
if storage_cooldown_remaining > 0:
    logger.debug(
        "[scale-down] storage within %.0fs cooldown — skipping",
        storage_cooldown_remaining,
    )
else:
    self._evaluate_scale_down_storage(ds)
```

> **Note:** Add `import time` at the top of the file — it is not currently
> imported in either `main_n1.py` or `main_n2.py`.

### Worked Example

With `SCALEDOWN_STORAGE_COOLDOWN_S=75`, `SCALEDOWN_COMPUTE_COOLDOWN_S=40`,
and the 2026-04-11 timeline:

| Time     | Event | Storage cooldown | Compute cooldown |
|----------|-------|------------------|------------------|
| 23:13:38 | Storage scale-up triggered → `_last_storage_scale_up_ts` set | 75 s | — |
| 23:14:08 | Compute scale-up triggered → `_last_compute_scale_up_ts` set | 45 s | 40 s |
| 23:14:18 | Telemetry arrives — both scale-downs **skipped** | 35 s | 30 s |
| 23:14:48 | Compute cooldown expires → compute scale-down **resumes** | 5 s | — |
| 23:14:53 | Storage cooldown expires → storage scale-down **resumes** | — | — |
| 23:15:18 | Would have been removed under old logic — now node **is serving traffic** | — | — |

Compute nodes (faster boot) resume scale-down evaluation 35 s sooner than
storage nodes, matching their shorter time-to-ready.

> **Additional protection from window accumulation:** Because the cooldown
> skips `_evaluate_scale_down_*()` entirely, the sliding-window deque receives
> no entries during the cooldown period. Combined with the `clear()` in
> `_evaluate_scale_up`, the scale-down evaluator must re-accumulate 7
> below-threshold windows (≥ 70 s) *after* the cooldown expires before it can
> fire. Effective total protection: **storage ≥ 145 s** (75 + 70), **compute
> ≥ 110 s** (40 + 70). This is not a bug — it's a desirable second layer of
> defence.

---

## Fix B — Scale-Up Threshold Tuning

### Problem

The current threshold (τ=0.85 with 3-of-5 windows) means the system must reach
roughly CPU > 85 % **and** T_db > 78 ms simultaneously for 3 windows (~30 s)
before the trigger fires. By the time this condition is met, the server is
already in severe distress.

Observed in the 2026-04-11 run:

```
23:12:08  score=0.35 (cpu_s=78.4%, T_db=24ms)    — degrading but below τ
23:12:48  score=0.48 (cpu_s=81.3%, T_db=33ms)    — still below τ
23:13:08  score=0.65 (cpu_s=88.9%, T_db=49ms)    — still below τ
23:13:18  score=1.62 (cpu_s=85.8%, T_db=156ms)   — finally above τ! window 1/5
23:13:28  score=1.56                               — window 2/5
23:13:38  score=1.69                               — window 3/5 → TRIGGERED
```

That is **90 seconds** between first visible degradation and the actual scale-up.

### Proposed Change

Lower the threshold and reduce the required window count:

| Parameter | Current | Proposed | Effect |
|-----------|---------|----------|--------|
| `SCALEUP_SCORE_THRESHOLD` | 0.85 | **0.70** | Reacts earlier, when there's moderate degradation |
| `SCALEUP_REQUIRED` | 3 | **2** | 2-of-5 instead of 3-of-5, saves ~10 s reaction time |

#### Code — env var defaults only (no structural change)

```python
# main_n1.py — change the default values:
_SCALE_UP_SCORE_THRESHOLD  = float(os.environ.get("SCALEUP_SCORE_THRESHOLD", "0.70"))   # was "0.85"
_SCALE_UP_REQUIRED         = int(os.environ.get("SCALEUP_REQUIRED",         "2"))        # was "3"
```

No other code is affected — the scoring formula, sliding window, and alert
dispatch remain identical.

### Worked Example — When Would It Fire?

With the proposed values applied to the same telemetry from the 2026-04-11 run:

```
23:12:08  score=0.35 — below 0.70         window 0/5
23:12:48  score=0.48 — below 0.70         window 0/5
23:13:08  score=0.65 — below 0.70         window 0/5
23:13:18  score=1.62 — above 0.70 ✓       window 1/5
23:13:28  score=1.56 — above 0.70 ✓       window 2/5 → TRIGGERED
```

Scale-up fires at **23:13:28** instead of **23:13:38** — 10 s earlier.

If the `SCALEUP_T_DB_FLOOR` is also adjusted:

| Parameter | Current | Proposed | Reasoning |
|-----------|---------|----------|-----------|
| `SCALEUP_T_DB_FLOOR` | 15 ms | **20 ms** | Slightly raise floor to avoid false positives under normal load |

That adjustment is optional and independent from the threshold change. If
applied, the false-positive threshold in the analysis below shifts from
T_db ≈ 67 ms to T_db ≈ 72 ms (slightly safer).

### False-Positive Risk

Lowering τ from 0.85 to 0.70 means a score of 0.70 now triggers. What does
that look like in practice?

```
score = 0.3 × max(0, cpu − 50) / 35  +  0.7 × max(0, T_db − 15) / 75
```

To reach 0.70 with CPU at 75% (moderate):

```
cpu_component = (75 − 50) / 35 = 0.714
score = 0.3 × 0.714 + 0.7 × latency_component = 0.214 + 0.7 × lat
→ need lat component ≥ (0.70 − 0.214) / 0.7 = 0.694
→ T_db ≥ 15 + 0.694 × 75 = 67 ms
```

So the trigger fires at CPU ≈ 75 % **and** T_db ≈ 67 ms — still a meaningful
degradation point, not a false alarm.

---

## Fix C — Birth-Grace for Absent-Node Detection

### Problem

`_detect_absent_nodes` starts counting absent windows immediately after a
new node appears in `_dynamic_node_macs`. A freshly spawned storage node that
takes 30 s for RS join will accumulate 3 "absent" windows before it can ever
emit a telemetry heartbeat:

```python
# main_n1.py — _detect_absent_nodes (current — around line 240)
def _detect_absent_nodes(self, summary: TelemetrySummary) -> None:
    for mac in list(self._dynamic_node_macs):
        present = (mac in summary.servers) or (mac in summary.storage_servers)
        if present:
            self._absent_window_count[mac] = 0
        else:
            self._absent_window_count[mac] = self._absent_window_count.get(mac, 0) + 1
            count = self._absent_window_count[mac]
            logger.debug("[scale-down] mac=%s absent for %d windows", mac, count)
            if count >= _TELEMETRY_TIMEOUT_WINDOWS:
                logger.warning(
                    "[scale-down] mac=%s absent for %d windows — triggering removal",
                    mac, count,
                )
                self._absent_window_count[mac] = 0
                if self._elasticity.has_pending_drain(mac):
                    self._elasticity.submit_cleanup_compute(mac)
                else:
                    self._submit_scale_down_alert(mac)
```

While the timeout (`TELEMETRY_TIMEOUT_WINDOWS = 10`) is large enough that a
30 s boot won't trigger timeout removal by itself, the absent windows create
two side effects:

1. **Log noise** — every 10 s a debug line is emitted for a node that is simply
   booting, cluttering the controller log during the critical post-scale-up
   period.
2. **Premature timeout accumulation** — if a node's boot time is unexpectedly
   long (e.g. slow RS sync), it could silently accumulate towards the 10-window
   timeout threshold before it ever has a chance to report.

> **Note:** A node that hasn't started reporting telemetry does **not** appear
> in `summary.servers` / `summary.storage_servers`, so the aggregator's domain
> averages are computed from reporting nodes only — the absent node does not
> drag the average down.

### Proposed Change

Record a "birth timestamp" when a dynamic node is first tracked. Skip
absent-window counting for that MAC until a configurable grace period elapses.

#### New Environment Variable

| Variable | Default | Unit | Purpose |
|----------|---------|------|---------|
| `NODE_BIRTH_GRACE_S` | `60` | seconds | Skip absent-node detection for this long after node creation |

#### Code — module-level constant

```python
# main_n1.py — new constant, near _TELEMETRY_TIMEOUT_WINDOWS
_NODE_BIRTH_GRACE_S = float(os.environ.get("NODE_BIRTH_GRACE_S", "60"))
```

#### Code — `__init__` (new instance attribute)

Add after `self._absent_window_count`:

```python
self._birth_ts: dict[str, float] = {}   # mac -> monotonic timestamp of first tracking
```

#### Code — `_sync_node_tracking` (record birth timestamp)

In the addition-completions loop, add the timestamp:

```python
for info in self._elasticity.consume_addition_completions():
    self._dynamic_node_macs.add(info.mac)
    self._active[info.mac] = info
    self._birth_ts[info.mac] = time.monotonic()    # ← NEW
    logger.info(
        "[scale-down] tracking new dynamic %s node mac=%s name=%s",
        info.node_type, info.mac, info.name,
    )
```

And in the removal-completions loop, clean up the entry:

```python
for mac in self._elasticity.consume_removal_completions():
    self._dynamic_node_macs.discard(mac)
    self._absent_window_count.pop(mac, None)
    self._active.pop(mac, None)
    self._birth_ts.pop(mac, None)                  # ← NEW
    logger.info("[scale-down] removed MAC %s from dynamic tracking after cleanup", mac)
```

#### Code — `_detect_absent_nodes` (skip during grace period)

Add an early-continue at the top of the loop:

```python
def _detect_absent_nodes(self, summary: TelemetrySummary) -> None:
    now = time.monotonic()
    for mac in list(self._dynamic_node_macs):
        # Skip freshly spawned nodes that are still booting
        if now - self._birth_ts.get(mac, float('-inf')) < _NODE_BIRTH_GRACE_S:
            continue                                # ← NEW

        present = (mac in summary.servers) or (mac in summary.storage_servers)
        if present:
            self._absent_window_count[mac] = 0
        else:
            self._absent_window_count[mac] = self._absent_window_count.get(mac, 0) + 1
            ...   # rest unchanged
```

### Worked Example

Storage node `edge_storage_lan1_dyn1` spawns at 23:13:38 (boot takes ~30 s):

| Window | Time     | Absent? | Grace? | Count |
|--------|----------|---------|--------|-------|
| 1      | 23:13:48 | yes     | **yes** (elapsed 10 s < 60 s) | skipped |
| 2      | 23:13:58 | yes     | **yes** (20 s < 60 s)          | skipped |
| 3      | 23:14:08 | yes     | **yes** (30 s < 60 s)          | skipped |
| 4      | 23:14:18 | **no** (node joins RS, sends heartbeat) | **yes** (40 s < 60 s) | skipped (grace `continue` fires before presence check) |
| …      | …        | no      | yes | skipped |
| 7      | 23:14:48 | no      | expired  | 0 — presence branch now executes, resets count |

Without the grace, absent count would have reached 3 by window 3, silently
accumulating toward the 10-window timeout threshold before the node has a
chance to report.

---

## Verification Scenarios

| # | Scenario | Expected behaviour |
|---|----------|--------------------|
| 1 | Storage scale-up fires, node boots in 30 s | Storage scale-down skipped for 75 s (Fix A). Absent-node detection skipped for 60 s (Fix C). Node joins RS and starts serving; system stabilises. |
| 1b | Compute scale-up fires, node boots in 15 s | Compute scale-down skipped for 40 s (Fix A). Node registers in VIP pool and starts serving within cooldown. |
| 2 | Scale-up fires, new node **fails** to boot (hangs) | After 60 s birth grace, absent detection resumes. After 10 absent windows (100 s) the timeout path triggers removal. Total: 160 s worst case for both tiers (`NODE_BIRTH_GRACE_S` + 10 × 10 s). |
| 3 | Moderate degradation (score ~0.72) sustained for 2 windows | Scale-up fires at 20 s instead of 30 s (Fix B). |
| 4 | Two scale-ups in rapid succession (same tier) | Second `submit_alert` refreshes that tier's timestamp, extending its cooldown from that point. |
| 4b | Storage + compute scale-ups in rapid succession | Each tier's cooldown is tracked independently — compute resumes evaluation sooner than storage. |
| 5 | Scale-down fires while cooldown is active due to concurrent busy=True check | The `is_busy()` guard already returns True while Thread 3 is processing an alert. The cooldown adds a second layer in case `is_busy` clears before the node is ready. |
| 6 | Low-load steady state (score < 0.70, all nodes healthy) | No change — scale-up never fires, scale-down proceeds normally after cooldown (cooldown only activates when a scale-up occurs). |

---

## Design Decisions

| Decision | Rationale | Alternative considered |
|----------|-----------|----------------------|
| Per-tier cooldown timers | Storage nodes need significantly longer to become ready (RS join + data sync ≈ 30 s) compared to compute (container start ≈ 10–15 s). A single timer either over-protects compute or under-protects storage. | Single global cooldown — simpler but mismatches real boot times |
| Cooldown refreshes on every scale-up (per tier) | Prevents cascading thrashing when multiple scale-ups of the same tier fire in quick succession | Fixed-duration cooldown from first event — risks stale protection |
| Birth grace based on wall-clock, not window count | Monotonic time is independent of telemetry delivery jitter | Count-based grace (e.g. skip first N windows) — fragile under ZMQ delays |
| Storage cooldown 75 s, compute cooldown 40 s | Storage: RS join (~30 s) + VIP propagation (~10 s) + traffic ramp (~15 s) + margin. Compute: container start (~15 s) + VIP registration (~5 s) + margin. Sized to just cover observed boot times without over-delaying scale-down. | Single 90 s cooldown — over-protects compute nodes that are ready in 15 s |
| Birth grace 60 s | 60 s is the observed maximum boot time (storage RS join). Prevents absent-window accumulation during bootstrap. | Shorter grace (30 s) — too tight for storage; longer (90 s) — delays legitimate dead-node detection |
| Threshold lowered to 0.70 (not lower) | Below 0.70 the false-positive risk increases at moderate loads (see worked example in Fix B) | 0.60 — could cause premature scale-ups under normal variance |

---

## Files to Modify

| File | Changes |
|------|---------|
| `source/sdn_controller/main_n1.py` | Add `import time`, per-tier cooldown constants + timestamps, birth-grace dict, per-tier guards in `_on_telemetry_update` |
| `source/sdn_controller/main_n2.py` | Apply the same changes verbatim — `main_n2.py` is structurally identical to `main_n1.py` (same env vars, same class, same methods; only `_lan_id` and endpoint defaults differ) |
| `source/scripts/osken-controller.env` | Add new env vars with defaults for documentation |
| `docs/operation/elasticy_manager/elasticity_overview.md` | Update parameter tables to reflect new defaults |
