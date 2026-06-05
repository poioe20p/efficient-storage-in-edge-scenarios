# Phase 3 - Storage Persistent Reserve Activation and Replenishment

## Status

Implemented.

## Primary Outcome

Make the reserve the first-step same-LAN storage scale-up action and start the
next reserve preparation immediately after activation.

## Scope

1. Intercept same-LAN storage load alerts before they become ordinary active
   storage spawn requests.
2. Activate the ready reserve immediately when a same-LAN storage alert fires.
3. Reclassify the activated reserve as ordinary active dynamic storage.
4. Start reserve replenishment immediately after activation.
5. If the reserve is still `PREPARING`, wait for it instead of spawning a
   second reserve.

## Behavioral Change

This phase changes the meaning of the first same-LAN Tier 2 storage scale-up.

Before this phase:

1. `DataAlert` means "spawn a new active storage node now"

After this phase:

1. `DataAlert` means "activate the ready reserve now"
2. if no ready reserve exists but a reserve is already preparing, do not spawn
   a second reserve and do not bypass the reserve model
3. once the reserve activates, prepare the next reserve immediately

This creates the intended stepwise growth behavior:

1. reserve activates into service
2. replenish begins right away
3. later growth can activate the next reserve once it becomes ready

## Step-By-Step Plan

1. Add a common helper in `main_n1.py` and `main_n2.py` to handle reserve-
   backed storage triggers.
2. When a same-LAN `DataAlert` is emitted by `ScalingPolicy`, route it through
   the reserve helper before calling `self._elasticity.submit(alert)`.
3. If the reserve slot is `READY_RESERVED`, consume it immediately:
   1. add the backend to the correct VIP pool
   2. clear `standby_reserved`
   3. treat the activation as a storage scale-up event for cooldown/reset
   4. start preparing the next reserve
4. If the reserve slot is `PREPARING`, latch `activation_pending=True` and
   wait for readiness instead of spawning a second reserve.
5. If the reserve slot is `NONE`, submit reserve preparation, latch pending
   activation, and wait.
6. When the preparing reserve later becomes ready, activate it on the next
   telemetry cycle if an activation is pending.

## Exact Edit Targets

Implement only these responsibilities in this phase.

1. In `source/sdn_controller/main_n1.py` and `source/sdn_controller/main_n2.py`,
   add one reserve-trigger helper and route same-LAN load-triggered `DataAlert`
   through it before normal Thread 3 submission.
2. In `source/sdn_controller/node_registry.py`, add the helper that consumes a
   ready reserve and clears pending activation state.
3. In `source/sdn_controller/scaling_policy.py`, add only the storage
   activation bookkeeping helper used after reserve activation.
4. Do not alter the cross-LAN `DataAlert` hook. Only same-LAN storage should be
   redirected through the reserve path.
5. Activation must add the backend to VIP using the normal storage admission
   path, then immediately submit preparation for the next reserve.

## Do Not Do In This Phase

1. Do not add recovery-distress telemetry yet.
2. Do not bypass the reserve model by spawning a normal active storage node
   when the reserve is merely `PREPARING`.
3. Do not prepare more than one reserve per LAN.
4. Do not leave an activated node marked `standby_reserved=True`.

## Code Sketches

### Reserve Trigger Helper

```python
def _handle_storage_reserve_trigger(self, summary: TelemetrySummary, lan: int, reason: str) -> bool:
    slot = self._node_registry.get_storage_reserve_slot(lan)

    if slot.state == "READY_RESERVED":
        info = self._node_registry.consume_ready_storage_reserve(lan)
        self.add_storage_mac(info.mac, f"n{lan}")
        info.standby_reserved = False
        self._scaling_policy.record_storage_activation()
        self._maybe_prepare_storage_reserve(summary, lan)
        return True

    self._node_registry.latch_storage_reserve_activation(lan, reason)
    self._maybe_prepare_storage_reserve(summary, lan)
    return True
```

### Mediator Hook

```python
for alert in self._scaling_policy.evaluate_scale_up(...):
    if isinstance(alert, DataAlert) and not alert.cross_lan_rs:
        if self._handle_storage_reserve_trigger(summary, alert.lan, "load"):
            continue
    self._elasticity.submit(alert)
```

### Scaling Policy Helper

```python
def record_storage_activation(self) -> None:
    self._last_storage_scale_up_ts = time.monotonic()
    self.clear_scale_down_storage_window()
```

## Verification Targets

1. The first same-LAN storage load alert activates a ready reserve instead of
   spawning a new active storage node.
2. A second reserve is not created while the current reserve is already
   `PREPARING`.
3. Activation immediately starts reserve replenishment.
4. Activated reserve nodes re-enter ordinary active dynamic accounting.

## Phase 3 Is Complete When

1. A same-LAN load alert consumes a ready reserve immediately.
2. A same-LAN load alert waits on a preparing reserve instead of spawning a
   second reserve.
3. Activation clears reserve status from the activated node.
4. Activation immediately starts preparation of the next reserve.
