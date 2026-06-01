# Phase 3 - First Alert Activation

**Status:** Proposed  
**Primary outcome:** Consume the standby on the first storage scale-up for a
LAN, or spend and discard it if the first alert arrives before the reserve is
ready.

This phase is where the reserve begins to affect user-facing Tier 2 behavior.
It keeps the existing `ScalingPolicy` intact and changes only how Thread 2
consumes the first `DataAlert` for a LAN.

---

## 1. Scope

In scope:

1. Intercept the first `DataAlert` for a LAN before it is submitted to Thread 3.
2. If the reserve is `READY_RESERVED`, activate it immediately without spawning
   a new storage container.
3. If the reserve is not ready yet, mark the reserve opportunity as spent and
   fall back to the current on-demand storage add path.
4. Discard any unconsumed reserve container after a miss.
5. Convert the activated standby into an ordinary active dynamic storage node.
6. Ensure later storage alerts use the current on-demand path.

Out of scope:

1. Replenishing the reserve after activation.
2. Any new standby-specific routing policy after activation.
3. Runtime re-enablement after a reserve has been spent.

---

## 2. Activation semantics

The controller-side rule for the first storage scale-up becomes:

1. `ScalingPolicy` still computes and emits the same `DataAlert` as today.
2. Thread 2 checks the standby slot for that LAN before calling
   `self._elasticity.submit(alert)`.
3. If the slot is `READY_RESERVED`, Thread 2 activates the reserve by adding
   the reserve MAC to the correct storage VIP pool and converting the standby
   slot to `ACTIVE_CONSUMED`.
4. If the slot is `PREPARING` or otherwise not ready yet, Thread 2 marks the
   reserve opportunity as `SPENT`, submits the original `DataAlert`, and
   schedules discard of the late reserve if one exists.
5. All later `DataAlert`s use the ordinary on-demand Tier 2 path because the
   reserve opportunity is already gone.

This keeps `ScalingPolicy` pure: it still owns the sliding-window clear and the
storage cooldown. The mediator simply chooses a different execution path for
the first alert when a ready reserve exists.

---

## 3. Why activation belongs in Thread 2

Activation does not require a new container lifecycle mutation when the standby
is already ready. The only action needed is the same action Thread 2 already
performs on `rs_secondary_ready`: add the storage MAC to the correct VIP pool.

That means the existing responsibility split still holds:

1. Thread 3 owns reserve creation and reserve discard.
2. Thread 2 owns the decision to expose a ready secondary to `VIP_DATA_N*`.

Keeping activation in Thread 2 avoids inventing a second promotion path in
Thread 3 for something that is fundamentally a VIP admission decision.

---

## 4. Step-by-step implementation

1. Add a small helper in [source/sdn_controller/main_n1.py](../../../../../source/sdn_controller/main_n1.py)
   and [source/sdn_controller/main_n2.py](../../../../../source/sdn_controller/main_n2.py)
   to intercept `DataAlert` when the standby feature is enabled.
2. If `activate_ready_standby(lan)` returns a `NodeInfo`, add its MAC to the
   correct storage VIP pool and do not submit the ordinary `DataAlert`.
3. Clear the `standby_reserved` bit on the activated `NodeInfo` so the former
   reserve now counts as ordinary active dynamic storage.
4. If the reserve is not ready when the first `DataAlert` arrives, call a
   registry helper that marks the slot `SPENT` and returns any existing late
   reserve `NodeInfo`.
5. Submit the original `DataAlert` unchanged so the current on-demand Tier 2
   path handles the real first scale-up.
6. Add `DiscardStandbyStorageAlert` in
   [source/sdn_controller/elasticity/elasticity.py](../../../../../source/sdn_controller/elasticity/elasticity.py)
   so Thread 3 can remove an unconsumed late reserve.
7. When the late reserve reaches `SECONDARY` after the reserve has already been
   spent, keep it out of VIP and route it into the discard path.
8. After activation or miss, all later storage scale-ups proceed through the
   current path because the slot is no longer eligible for reserve use.

---

## 5. Implementation code snippets

### 5.1 Thread 2 intercept

Add the intercept where `DataAlert` is currently submitted in
[source/sdn_controller/main_n1.py](../../../../../source/sdn_controller/main_n1.py)
and [source/sdn_controller/main_n2.py](../../../../../source/sdn_controller/main_n2.py):

```python
if isinstance(alert, DataAlert) and _STANDBY_STORAGE_ENABLED:
    standby = self._node_registry.activate_ready_standby(alert.lan)
    if standby is not None:
        self.add_storage_mac(standby.mac, f"n{standby.lan}")
        logger.info(
            "[standby] activated lan=%d name=%s mac=%s ip=%s",
            standby.lan,
            standby.name,
            standby.mac,
            standby.ip,
        )
        continue

    late_reserve = self._node_registry.mark_first_storage_scaleup_missed(alert.lan)
    if late_reserve is not None:
        self._elasticity.submit(
            DiscardStandbyStorageAlert(
                lan=late_reserve.lan,
                network_id=late_reserve.network_id,
                container_name=late_reserve.name,
                mac=late_reserve.mac,
                ip=late_reserve.ip,
                rs_name=late_reserve.rs_name,
                primary_container=late_reserve.primary_container,
                port=late_reserve.port,
            )
        )

self._elasticity.submit(alert)
```

This preserves the current `ScalingPolicy` cooldown and window semantics
because the alert was already computed in the same way as today.

### 5.2 Registry activation contract

The registry helper should convert a ready reserve into an ordinary active
dynamic node atomically:

```python
def activate_ready_standby(self, lan: int) -> NodeInfo | None:
    slot = self._storage_standby[lan]
    if slot.state != "READY_RESERVED":
        return None

    info = self._active.get(slot.mac)
    if info is None:
        slot.state = "SPENT"
        return None

    info.standby_reserved = False
    slot.state = "ACTIVE_CONSUMED"
    return info
```

Once the flag is cleared, ordinary `count_dynamic("storage")` and storage
scale-down logic can include the node again.

### 5.3 Discard alert

Add a dedicated discard alert in
[source/sdn_controller/elasticity/elasticity.py](../../../../../source/sdn_controller/elasticity/elasticity.py):

```python
@dataclass(frozen=True)
class DiscardStandbyStorageAlert:
    lan: int
    network_id: str
    container_name: str
    mac: str
    ip: str
    rs_name: str
    primary_container: str
    port: int = 27018
```

The handler should reuse the current storage removal path, but it must skip VIP
removal because a reserved standby was never added to `VIP_DATA_N*`.

### 5.4 Late-ready standby after miss

If the slot is already `SPENT` when `rs_secondary_ready` arrives for the
reserve, the control-event path should log and schedule discard rather than
promote or re-reserve it:

```python
if info.standby_reserved and registry.standby_state(info.lan) == "SPENT":
    logger.info(
        "[standby] reserve became ready after miss lan=%d mac=%s -- scheduling discard",
        info.lan,
        mac,
    )
    elasticity.submit_cleanup_standby(...)
    continue
```

The exact helper name can vary, but the semantics should remain fixed.

---

## 6. File map

### Code

- [source/sdn_controller/main_n1.py](../../../../../source/sdn_controller/main_n1.py)
- [source/sdn_controller/main_n2.py](../../../../../source/sdn_controller/main_n2.py)
- [source/sdn_controller/node_registry.py](../../../../../source/sdn_controller/node_registry.py)
- [source/sdn_controller/control_events.py](../../../../../source/sdn_controller/control_events.py)
- [source/sdn_controller/elasticity/elasticity.py](../../../../../source/sdn_controller/elasticity/elasticity.py)
- [source/sdn_controller/elasticity/storage_node_manager.py](../../../../../source/sdn_controller/elasticity/storage_node_manager.py)

### Docs

- [../../scale_up/storage_scale_up.md](../../scale_up/storage_scale_up.md)
- [../../../system_mechanisms.md](../../../system_mechanisms.md)

---

## 7. Verification

1. Enable the feature and let the standby reach `READY_RESERVED` before any
   storage alert; confirm the first storage alert activates `dyn0` without a
   new storage `docker run`.
2. Confirm the activated node now appears in the VIP storage pool and ordinary
   active dynamic storage accounting.
3. Force the first storage alert to arrive while the reserve is still
   `PREPARING`; confirm the controller falls back to the current on-demand
   `DataAlert` path.
4. Confirm the reserve opportunity is then marked spent and later storage
   alerts no longer attempt reserve activation.
5. Confirm a late-ready reserve after a miss is discarded rather than promoted
   or held forever.
6. Confirm a consumed reserve can later be removed by the ordinary storage
   scale-down path.

---

## 8. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Activation bypasses the existing storage cooldown semantics | Do not change `ScalingPolicy`; intercept only after the `DataAlert` already exists |
| Reserve is counted twice after activation | Clear `standby_reserved` in the registry before reusing the node as ordinary active storage |
| Late reserve survives forever after the first alert already used the cold path | Add the explicit `SPENT` state and discard path for post-miss readiness |
