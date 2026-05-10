# Phase 2 - Reserve Preparation

**Status:** Proposed  
**Primary outcome:** Prepare one heartbeating storage standby per LAN and hold
it outside the VIP storage pool while it remains reserved.

This phase creates the reserve. It does not yet consume the reserve on the
first storage alert.

---

## 1. Scope

In scope:

1. Add a Thread 3 alert for standby preparation.
2. Bootstrap one storage standby per LAN when the feature is enabled and the
   local primary is healthy.
3. Reuse the current storage-add lifecycle for the reserve instead of creating
   a parallel bootstrap mechanism.
4. Enable heartbeat explicitly for the standby container.
5. Hold the standby out of `VIP_DATA_N*` after it reaches `SECONDARY`.
6. Register the standby's IP and MAC in controller caches so Thread 1 can
   resolve it later when it is activated.

Out of scope:

1. Activating the standby on the first storage alert.
2. Spending the reserve opportunity when the first alert arrives too early.
3. Replenishing or discarding the reserve.

---

## 2. Preparation model

Phase 2 uses the current same-LAN Tier 2 path as-is wherever possible:

1. Thread 2 detects that the standby should exist.
2. Thread 2 submits a background `PrepareStandbyStorageAlert`.
3. Thread 3 allocates a normal LAN IP and MAC from the shared `IpAllocator`.
4. Thread 3 starts `edge_storage_lanX_dyn0` through the existing
   `StorageNodeAdder.add_storage_node(...)` path, but with
   `HEARTBEAT_ENABLED=true`.
5. The container joins the local replica set through the current
   `mongo_telemetry.py` sidecar path.
6. When `rs_secondary_ready` arrives, Thread 2 marks the standby slot as
   `READY_RESERVED` and explicitly does not add the node to the VIP pool.

This keeps reserve preparation aligned with the current controller-owned
storage lifecycle instead of introducing a special shell-script-only path.

---

## 3. Why the reserve must use the existing storage add path

The current Tier 2 storage workflow already has the invariants this feature
needs:

1. `StorageNodeAdder` owns `docker run`, IP and MAC hints, and network attach.
2. The sidecar already owns RS self-join and ready-state detection in
   [source/docker/edge_storage_server/mongo_telemetry.py](../../../../../source/docker/edge_storage_server/mongo_telemetry.py).
3. Thread 2 already owns the `rs_secondary_ready` promotion gate in
   [source/sdn_controller/control_events.py](../../../../../source/sdn_controller/control_events.py).

The reserve therefore differs from ordinary Tier 2 only in two ways:

1. Heartbeat is enabled while the node is reserved.
2. Ready-state does not imply VIP admission while the node is still reserved.

---

## 4. Step-by-step implementation

1. Add `PrepareStandbyStorageAlert` in
   [source/sdn_controller/elasticity/elasticity.py](../../../../../source/sdn_controller/elasticity/elasticity.py).
2. Add a helper in [source/sdn_controller/main_n1.py](../../../../../source/sdn_controller/main_n1.py)
   and [source/sdn_controller/main_n2.py](../../../../../source/sdn_controller/main_n2.py)
   to submit the standby preparation alert once per LAN when the feature is
   enabled and the local primary is visible in telemetry.
3. Add a deterministic reserve name helper in Thread 3:
   `edge_storage_lan1_dyn0` / `edge_storage_lan2_dyn0`.
4. Extend
   [source/sdn_controller/elasticity/storage_node_manager.py](../../../../../source/sdn_controller/elasticity/storage_node_manager.py)
   so `add_storage_node(...)` can pass `HEARTBEAT_ENABLED=true` for the
   standby path.
5. When Thread 3 records standby preparation success, append a `NodeInfo` with
   `standby_reserved=True` so Thread 2 can track the reserve.
6. Update [source/sdn_controller/control_events.py](../../../../../source/sdn_controller/control_events.py)
   so `rs_secondary_ready` marks standby as `READY_RESERVED` and skips VIP
   admission.
7. Apply the same reserved-standby gate to the telemetry fallback path that
   currently promotes `member_state == "SECONDARY"`.
8. Keep `count_dynamic("storage")` unchanged from Phase 1, so the reserve does
   not influence later adaptive threshold calculations.

---

## 5. Implementation code snippets

### 5.1 Standby alert and handler

Add the alert in
[source/sdn_controller/elasticity/elasticity.py](../../../../../source/sdn_controller/elasticity/elasticity.py):

```python
@dataclass(frozen=True)
class PrepareStandbyStorageAlert:
    lan: int
    network_id: str
    rs_name: str
    primary_container: str
    port: int = 27018
```

The handler should be separate from ordinary `_handle_data(...)` because it
must use a deterministic `dyn0` name and must record the resulting `NodeInfo`
as reserved standby rather than ordinary active storage.

### 5.2 Thread 2 bootstrap hook

Add a one-shot bootstrap helper in
[source/sdn_controller/main_n1.py](../../../../../source/sdn_controller/main_n1.py)
and [source/sdn_controller/main_n2.py](../../../../../source/sdn_controller/main_n2.py):

```python
def _maybe_prepare_storage_standby(
    self,
    summary: TelemetrySummary,
    lan: int,
) -> None:
    if not _STANDBY_STORAGE_ENABLED:
        return
    if not self._node_registry.should_prepare_standby(lan):
        return
    if not any(ss.member_state == "PRIMARY" for ss in summary.storage_servers.values()):
        return

    self._elasticity.submit(
        PrepareStandbyStorageAlert(
            lan=lan,
            network_id=summary.network_id,
            rs_name=f"rs_net{lan}",
            primary_container=f"edge_storage_server_n{lan}",
        )
    )
    self._node_registry.mark_standby_prepare_submitted(lan)
```

This hook should run before ordinary scale-up evaluation so the reserve can be
prepared in the background as early as possible.

### 5.3 Deterministic standby name

Reserve naming should bypass `_next_name(...)` in
[source/sdn_controller/elasticity/elasticity.py](../../../../../source/sdn_controller/elasticity/elasticity.py):

```python
def _standby_name(self, lan: int) -> str:
    return f"edge_storage_lan{lan}_dyn0"
```

Using `dyn0` keeps the reserve outside the normal reactive naming sequence and
matches the existing dynamic-storage cleanup regex in
[source/scripts/cleanup.sh](../../../../../source/scripts/cleanup.sh).

### 5.4 Heartbeat override for reserve spawns

Extend the storage spawner in
[source/sdn_controller/elasticity/storage_node_manager.py](../../../../../source/sdn_controller/elasticity/storage_node_manager.py):

```python
def add_storage_node(
    self,
    lan: int,
    name: str,
    rs_name: str,
    port: int = 27018,
    ip: str | None = None,
    mac: str | None = None,
    heartbeat_enabled: bool = False,
) -> NodeResult:
    ...
```

and:

```python
cmd += ["-e", f"HEARTBEAT_ENABLED={'true' if heartbeat_enabled else 'false'}"]
```

Ordinary dynamic storage keeps the current default path. Only standby
preparation sets `heartbeat_enabled=True`.

### 5.5 Ready-state gating in control events

Update [source/sdn_controller/control_events.py](../../../../../source/sdn_controller/control_events.py):

```python
if info.standby_reserved:
    registry.mark_standby_ready(mac)
    logger.info(
        "[standby] ready_reserved mac=%s ip=%s name=%s -- VIP deferred",
        mac,
        info.ip,
        info.name,
    )
    continue
```

The telemetry fallback branch should apply the same rule so a reserved standby
seen as `SECONDARY` through ordinary `mongo_stats` still remains outside the
VIP pool.

---

## 6. File map

### Code

- [source/sdn_controller/main_n1.py](../../../../../source/sdn_controller/main_n1.py)
- [source/sdn_controller/main_n2.py](../../../../../source/sdn_controller/main_n2.py)
- [source/sdn_controller/control_events.py](../../../../../source/sdn_controller/control_events.py)
- [source/sdn_controller/elasticity/elasticity.py](../../../../../source/sdn_controller/elasticity/elasticity.py)
- [source/sdn_controller/elasticity/storage_node_manager.py](../../../../../source/sdn_controller/elasticity/storage_node_manager.py)
- [source/docker/edge_storage_server/mongo_telemetry.py](../../../../../source/docker/edge_storage_server/mongo_telemetry.py)

### Docs

- [../../elasticity_overview.md](../../elasticity_overview.md)
- [../../../system_mechanisms.md](../../../system_mechanisms.md)

---

## 7. Verification

1. Start with `STANDBY_STORAGE_ENABLED=1` and confirm each controller prepares
   exactly one `edge_storage_lanX_dyn0` for its LAN.
2. Confirm the reserve reaches `SECONDARY` through the current sidecar join
   path.
3. Confirm the reserve emits idle heartbeat telemetry while reserved.
4. Confirm `rs_secondary_ready` for `dyn0` does not add the reserve to
   `vip_storage_pool_n1` or `vip_storage_pool_n2`.
5. Confirm `count_dynamic("storage")` still reports zero reserved nodes before
   the first real storage activation.
6. Confirm the reserve occupies a real LAN IP and MAC from the shared
   allocator and that later dynamic nodes use the next free LAN slot.

---

## 8. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Reserve creation accidentally promotes the standby into service immediately | Gate both `rs_secondary_ready` and telemetry fallback on `standby_reserved` before any `add_storage_mac(...)` call |
| Reserve bootstrap fails repeatedly and floods the controller with retries | Keep retry state in the standby slot and apply a simple controller-local retry backoff when preparation fails |
| Reserve preparation consumes LAN address space earlier than expected | Treat this as intentional capacity reservation and document that the standby uses the shared `IpAllocator` like any other dynamic node |
