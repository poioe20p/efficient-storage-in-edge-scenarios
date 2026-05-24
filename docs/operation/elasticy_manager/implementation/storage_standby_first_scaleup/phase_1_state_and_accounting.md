# Phase 1 - State and Accounting

**Status:** Proposed  
**Primary outcome:** Add a controller-side standby state model that keeps
reserved standby storage separate from ordinary dynamic storage accounting.

This phase introduces the minimum controller state needed to represent a
reserved storage standby safely. It does not yet create standby containers and
does not change the live Tier 2 scale-up path.

---

## 1. Scope

In scope:

1. Add a launch-time master flag for the standby feature.
2. Extend controller-side node metadata so storage nodes can be marked as
   reserved standby.
3. Add a per-LAN standby slot model owned by Thread 2.
4. Exclude reserved standby storage from ordinary dynamic storage accounting:
   threshold counting, LIFO selection, and ordinary storage scale-down alert
   building.
5. Define how absence detection should treat reserved standby storage once it
   exists in later phases.
6. Keep all current Tier 2 scale-up behavior unchanged while the feature is
   still only state scaffolding.

Out of scope:

1. Creating standby containers.
2. Enabling heartbeat on standby containers.
3. Activating a standby on the first storage alert.
4. Discarding or replenishing a standby.

---

## 2. Why this phase must come first

The current storage elasticity path assumes every tracked dynamic storage node
is either active service capacity or a candidate for future scale-down. That is
not true for a reserved standby.

Today, the following controller behaviors would treat a reserve incorrectly if
it were introduced without new state:

1. `count_dynamic("storage")` in [source/sdn_controller/node_registry.py](../../../../../source/sdn_controller/node_registry.py)
   would make the reserve raise the adaptive threshold seen by
   [source/sdn_controller/main_n1.py](../../../../../source/sdn_controller/main_n1.py)
   and [source/sdn_controller/main_n2.py](../../../../../source/sdn_controller/main_n2.py).
2. `find_last_dynamic("storage")` would make the reserve the default storage
   scale-down candidate.
3. `build_scale_down_alert(...)` would route the reserve into the ordinary
   `ScaleDownDataAlert` path even while it had never served traffic.
4. The current absence path would interpret the reserve as a failed normal
   dynamic node rather than as a failed reserve slot.

Phase 1 exists to separate those meanings before any standby container is ever
created.

---

## 3. State model

Introduce a controller-local per-LAN standby slot with the following states:

| State | Meaning | Counted as dynamic storage | Eligible for storage scale-down | Eligible for VIP promotion |
| --- | --- | --- | --- | --- |
| `NONE` | No reserve exists yet | No | No | No |
| `PREPARING` | Standby creation submitted but not yet confirmed ready | No | No | No |
| `READY_RESERVED` | Standby is alive and `SECONDARY`, but still reserved | No | No | No |
| `ACTIVE_CONSUMED` | First scale-up activated the standby | Yes | Yes | Already active |
| `SPENT` | The first-alert opportunity is gone for this LAN | No | No | No |

This state should live in Thread 2 because Thread 2 already owns:

1. Registry bookkeeping.
2. Telemetry-driven readiness interpretation.
3. The decision point where `DataAlert` is submitted.

Thread 3 remains responsible for container lifecycle changes.

---

## 4. Step-by-step implementation

1. Add `STANDBY_STORAGE_ENABLED` in
   [source/sdn_controller/scaling_config.py](../../../../../source/sdn_controller/scaling_config.py)
   with default `0`.
2. Extend `NodeInfo` in
   [source/sdn_controller/elasticity/node_common.py](../../../../../source/sdn_controller/elasticity/node_common.py)
   with `standby_reserved: bool = False`.
3. In [source/sdn_controller/node_registry.py](../../../../../source/sdn_controller/node_registry.py),
   add a small `StorageStandbySlot` model keyed by LAN.
4. Add registry helpers for:
   `should_prepare_standby(lan)`, `mark_standby_prepare_submitted(lan)`,
   `mark_standby_ready(mac)`, `activate_ready_standby(lan)`, and
   `mark_first_storage_scaleup_missed(lan)`.
5. Change `count_dynamic("storage")` so it ignores `NodeInfo` records whose
   `standby_reserved` flag is still true.
6. Change `find_last_dynamic("storage")` to skip reserved standby storage.
7. Change `build_scale_down_alert(...)` to return `None` for reserved standby
   storage instead of producing `ScaleDownDataAlert`.
8. Change `detect_absent(...)` so when a reserved standby exceeds the normal
   absence threshold, the registry clears the standby slot and logs a standby
   failure rather than routing it into ordinary storage scale-down.
9. Keep the ordinary `DataAlert` path unchanged in this phase.

---

## 5. Implementation code snippets

### 5.1 Config flag

Add the standby master switch beside the existing elasticity toggles in
[source/sdn_controller/scaling_config.py](../../../../../source/sdn_controller/scaling_config.py):

```python
_STANDBY_STORAGE_ENABLED = int(os.environ.get("STANDBY_STORAGE_ENABLED", "0"))
```

This phase does not add any additional standby count or heartbeat knobs. One
reserve per LAN is fixed by design in phase 1.

### 5.2 Node metadata

Extend `NodeInfo` in
[source/sdn_controller/elasticity/node_common.py](../../../../../source/sdn_controller/elasticity/node_common.py):

```python
@dataclass
class NodeInfo:
    mac: str
    lan: int
    network_id: str
    name: str
    ip: str
    node_type: str
    rs_name: str = ""
    primary_container: str = ""
    port: int = 27018
    owner_lan: str = ""
    standby_reserved: bool = False
```

Reserved standby uses the same `node_type == "storage"` bucket as ordinary
Tier 2 nodes. The separate `standby_reserved` bit is what prevents the reserve
from being counted or removed like an ordinary active secondary.

### 5.3 Registry slot model

Add a controller-local slot model in
[source/sdn_controller/node_registry.py](../../../../../source/sdn_controller/node_registry.py):

```python
@dataclass
class StorageStandbySlot:
    lan: int
    state: str = "NONE"
    mac: str = ""
    ip: str = ""
    name: str = ""
```

Thread 2 owns two slots:

```python
self._storage_standby: dict[int, StorageStandbySlot] = {
    1: StorageStandbySlot(lan=1),
    2: StorageStandbySlot(lan=2),
}
```

### 5.4 Dynamic-count exclusion

Change `count_dynamic(...)` in
[source/sdn_controller/node_registry.py](../../../../../source/sdn_controller/node_registry.py):

```python
def count_dynamic(self, node_type: str) -> int:
    return sum(
        1
        for info in self._active.values()
        if info.node_type == node_type and not info.standby_reserved
    )
```

This keeps the reserved standby out of the adaptive storage threshold used by
[source/sdn_controller/scaling_policy.py](../../../../../source/sdn_controller/scaling_policy.py).

### 5.5 Absence handling contract

Once later phases start creating standby containers, absence handling should
distinguish a failed reserve from a failed active node:

```python
if info.standby_reserved:
    logger.warning(
        "[standby] reserved standby mac=%s absent for %d windows -- clearing slot",
        mac,
        count,
    )
    self._clear_standby_slot(info.lan, mac)
    continue
```

Phase 1 only defines this contract. The later phases are what make the branch
reachable.

---

## 6. File map

### Code

- [source/sdn_controller/scaling_config.py](../../../../../source/sdn_controller/scaling_config.py)
- [source/sdn_controller/elasticity/node_common.py](../../../../../source/sdn_controller/elasticity/node_common.py)
- [source/sdn_controller/node_registry.py](../../../../../source/sdn_controller/node_registry.py)
- [source/sdn_controller/main_n1.py](../../../../../source/sdn_controller/main_n1.py)
- [source/sdn_controller/main_n2.py](../../../../../source/sdn_controller/main_n2.py)

### Docs

- [../../elasticity_overview.md](../../elasticity_overview.md)
- [../../../archive/other/heartbeat_dynamic_node_gate_plan.md](../../../archive/other/heartbeat_dynamic_node_gate_plan.md)

---

## 7. Verification

1. With `STANDBY_STORAGE_ENABLED=0`, confirm no standby-specific behavior or
   logging appears.
2. Add a synthetic `NodeInfo(..., standby_reserved=True)` in tests or a local
   controller harness and confirm `count_dynamic("storage")` ignores it.
3. Confirm `find_last_dynamic("storage")` does not return a reserved standby.
4. Confirm `build_scale_down_alert(...)` returns `None` for reserved standby.
5. Confirm the standby slot transitions are controller-local only and do not
   change current `DataAlert` handling yet.

---

## 8. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Reserve state leaks into ordinary dynamic storage behavior | Centralize the distinction in `NodeInfo.standby_reserved` and registry helpers instead of scattering ad hoc checks in multiple controller call sites |
| Standby slot and `_active` map drift apart | Keep all standby-slot mutations in `DynamicNodeRegistry` rather than duplicating state in `main_n1.py` / `main_n2.py` |
| Future phases bypass the accounting exclusions | Treat Phase 1 as a hard prerequisite for any standby container preparation |
