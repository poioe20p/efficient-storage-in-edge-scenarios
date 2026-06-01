# Elasticity Manager Orchestration

## 1. Purpose

The `ElasticityManager` (Thread 3) is the **sole orchestrator** of
infrastructure mutations in the controller. It owns a priority queue fed by
Thread 2's telemetry callback and dispatches typed alerts to the appropriate
handler — compute/storage scale-up, scale-down, drain cancel, and cleanup.
All container lifecycle changes flow through `NodeAdder`; the manager itself
never touches Docker or OVS directly.

Source: [`source/sdn_controller/elasticity/elasticity.py`](../../../source/sdn_controller/elasticity/elasticity.py)

---

## 2. Thread Interaction

```
Thread 2 (ScalingPolicy)          Thread 3 (ElasticityManager)         Thread 1 (SDN Controller)
       │                                    │                                    │
       │── submit(alert) ──────────────────►│                                    │
       │                                    │── _loop() pops from PriorityQueue  │
       │                                    │── _handle_<type>(alert)            │
       │                                    │   ├─ NodeAdder.add_*_node()       │
       │                                    │   └─ TopologyMixin.register_*() ──►│ reads VIP pool
       │                                    │                                    │
       │◄── consume_addition_completions() ─│                                    │
       │◄── consume_removal_completions() ──│                                    │
       │                                    │                                    │
       │◄── is_busy() / blocks_*_scale_up() │                                    │
```

- **Thread 2 → Thread 3:** `submit(alert)` enqueues a typed alert. Thread 2 is
  never blocked — the queue decouples detection from execution.
- **Thread 3 → Thread 1:** After a successful node add, the manager calls
  `TopologyMixin` methods (`register_new_server_backend`, `register_backend_ip`,
  `add_server_mac`, etc.) which mutate the shared VIP pool. Thread 1 reads
  this pool on the next controller loop iteration — no direct Thread 1/3
  coupling.
- **Thread 3 → Thread 2:** `consume_addition_completions()` and
  `consume_removal_completions()` return `NodeInfo` records and MAC sets so
  Thread 2 can track dynamic nodes for scale-down decisions.
- **Thread 2 ← Thread 3 (gates):** `is_busy()`, `blocks_compute_scale_up()`,
  and `blocks_storage_scale_up()` are read by Thread 2 before evaluating
  scale-up/down predicates.

---

## 3. Alert Types

All alert dataclasses are defined in `elasticity.py`. They are frozen
(immutable) and carry only the fields needed by their handler.

### Tier 2 — Compute & Storage

| Alert                       | Trigger (Thread 2)                                              | Handler (Thread 3)                                           |
| --------------------------- | --------------------------------------------------------------- | ------------------------------------------------------------ |
| `ComputeAlert`            | Adaptive compute threshold breached                             | `_handle_compute` → `ComputeNodeAdder.add_edge_server`  |
| `DataAlert`               | Storage degradation score above diminishing-increment threshold | `_handle_data` → `StorageNodeAdder.add_storage_node`    |
| `ScaleDownComputeAlert`   | Compute underutilization (7-of-12 windows) or telemetry timeout | `_handle_scale_down_compute` → Phase A drain              |
| `ScaleDownDataAlert`      | Storage underutilization (7-of-12 windows) or telemetry timeout | `_handle_scale_down_data` → `rs.remove()` + teardown    |
| `CleanupComputeAlert`     | `drain_complete` ZMQ event or telemetry timeout fallback      | `_handle_cleanup_compute` → Phase B OVS teardown          |
| `CancelComputeDrainAlert` | Compute scale-up fires while a compute drain is pending         | `_handle_cancel_compute_drain` → re-admit MAC to VIP pool |

### Tier 1 — Selective Sync

| Alert                             | Trigger                                  | Handler                                                                                       |
| --------------------------------- | ---------------------------------------- | --------------------------------------------------------------------------------------------- |
| `SelectiveSyncAlert`            | `PromotionCoordinator` predicate fires | `_handle_selective_sync` → `SelectiveStorageNodeAdder.add_selective_storage_node`        |
| `SelectiveSyncReconfigureAlert` | Live hot-doc set update                  | `_handle_selective_sync_reconfigure` → manifest broadcast + `POST /forwarder_config`     |
| `ScaleDownSelectiveAlert`       | Tier 1 underutilization                  | `_handle_scale_down_selective` → revoke manifest, `POST /drain`, record `PendingDrain` |
| `CleanupSelectiveAlert`         | `drain_complete` or timeout            | `_handle_cleanup_selective` → OVS teardown + `docker rm`                                 |

---

## 4. Alert Priority Order

The manager uses a `queue.PriorityQueue` with a `(priority, sequence, alert)`
tuple. Lower priority numbers win. A monotonically increasing sequence counter
provides FIFO ordering within the same priority level.

| Priority | Alert                             | Rationale                                                                           |
| :------: | --------------------------------- | ----------------------------------------------------------------------------------- |
|    1    | `DataAlert`                     | Storage scale-up supersedes all — fastest path to latency relief                   |
|    2    | `SelectiveSyncAlert`            | Tier 1 promotion sits just below storage                                            |
|    3    | `SelectiveSyncReconfigureAlert` | Live Tier 1 updates                                                                 |
|    4    | `ComputeAlert`                  | Compute scale-up                                                                    |
|    5    | `CleanupComputeAlert`           | Phase B compute cleanup — paired near its scale-down                               |
|    6    | `CleanupSelectiveAlert`         | Phase B Tier 1 cleanup                                                              |
|    7    | `CancelComputeDrainAlert`       | Cancel a pending compute drain (lower priority than the scale-up that triggered it) |
|    8    | `ScaleDownDataAlert`            | Storage scale-down                                                                  |
|    9    | `ScaleDownSelectiveAlert`       | Tier 1 scale-down Phase A                                                           |
|    10    | `ScaleDownComputeAlert`         | Compute scale-down — lowest priority                                               |

Unknown alert types fall back to priority 10 with a warning.

---

## 5. Queue Dispatch

The `_loop()` method runs in a dedicated daemon thread (`"elasticity-mgr"`):

```python
def _loop(self) -> None:
    while True:
        _priority, _seq, alert = self._queue.get()
        self._busy = True
        try:
            if isinstance(alert, ComputeAlert):         self._handle_compute(alert)
            elif isinstance(alert, DataAlert):           self._handle_data(alert)
            elif isinstance(alert, ScaleDownComputeAlert): self._handle_scale_down_compute(alert)
            # ... remaining alert types ...
        finally:
            self._busy = False
```

Key properties:

- **Blocking pop:** `_queue.get()` blocks until an alert arrives — no polling.
- **Sequential execution:** One alert at a time. While a handler runs, `_busy`
  is `True` and Thread 2 gates scale-up/down evaluation accordingly.
- **Exception safety:** `_busy` is reset in `finally`, so a handler crash
  cannot permanently wedge the manager.
- **No priority inversion:** Cleanup alerts (Phase B) have higher priority
  than their corresponding scale-down alerts (Phase A), so a pending Phase B
  wins over a fresh scale-down submission of the same tier.

---

## 6. Busy and Pending Drain State

The manager exposes four gating methods consumed by Thread 2's scaling policy:

| Method                        | Returns `True` when…                                                                         |
| ----------------------------- | ----------------------------------------------------------------------------------------------- |
| `has_active_operation()`    | A handler is actively executing (`_busy`)                                                     |
| `is_busy()`                 | A handler is executing**OR** any Phase A drain is pending                                 |
| `blocks_compute_scale_up()` | A handler is executing (`_busy` only — pending compute drains do NOT block compute scale-up) |
| `blocks_storage_scale_up()` | A handler is executing **OR** any storage-type `PendingDrain` exists                   |

The asymmetry is intentional:

- **Pending compute drains** do not block compute scale-up. Thread 2 subtracts
  them from the effective dynamic compute count and submits `ComputeAlert`
  first, followed by a lower-priority `CancelComputeDrainAlert`. This favors
  fast rebound.
- **Pending storage drains** do block storage scale-up, because storage
  removal is synchronous (`rs.remove()` blocks Thread 3).
- **Pending Tier 1 selective drains** block neither compute nor storage
  scale-up.

`_busy` is a plain `bool` written only by Thread 3 and read by Thread 2;
Python's GIL guarantees atomic reads/writes.

---

## 7. Cleanup Dispatch

Cleanup (Phase B) is triggered externally — the manager does not poll for
drain completion. The entry point is `submit_cleanup(mac)`:

```python
def submit_cleanup(self, mac: str) -> None:
    pending = self._get_pending_drain(mac)
    if pending is None:
        # Fallback: unknown MAC → CleanupComputeAlert
        self.submit(CleanupComputeAlert(mac=mac))
        return
    if pending.node_type == "selective_storage":
        self.submit(CleanupSelectiveAlert(mac=mac))
    else:
        self.submit(CleanupComputeAlert(mac=mac))
```

Callers:

- **`ControlEventDispatcher.process_drain_events`** — subscribes to the
  `drain_complete` ZMQ event from the edge server supervisor and calls
  `elasticity.submit_cleanup(mac)`.
- **Telemetry timeout fallback** — Thread 2 detects a dynamic node absent for
  18 consecutive windows (180 s) and submits a scale-down alert; if a
  `PendingDrain` already exists, the timeout path can also trigger cleanup.

The dispatcher routes by `PendingDrain.node_type` (`"compute"` or
`"selective_storage"`), so a single `submit_cleanup` entry point handles both
compute and Tier 1 Phase B without the caller knowing the node type.

---

## 8. Handoffs to Scaling Policy, Node Adders, and Topology

The manager is the **sole integration point** between these subsystems:

### Scaling Policy → Manager

- `submit(alert)` — the only way alerts enter the queue.
- `submit_cleanup(mac)` — Phase B entry for external drain-complete events.
- `submit_cancel_compute_drain(mac)` — cancel a pending compute drain.

### Manager → Node Adders

- `ComputeNodeAdder.add_edge_server(lan, name, ip, mac)` — spawn + network
  attach, returns `NodeResult`.
- `StorageNodeAdder.add_storage_node(lan, name, rs_name, port, ip, mac)` —
  spawn + network attach; RS join is async via sidecar, returns `NodeResult`.
- `SelectiveStorageNodeAdder.add_selective_storage_node(...)` — Tier 1 spawn.
- Removal methods on the same adder instances handle teardown.

### Manager → Topology (VIP Pool)

Via the `ElasticityController` protocol (implemented by the composed
controller from `main_n*.py`):

| Method                                      | Called by                      | Purpose                                                     |
| ------------------------------------------- | ------------------------------ | ----------------------------------------------------------- |
| `register_new_server_backend(mac, ip)`    | `_handle_compute`            | Add compute backend to VIP web pool + warm lease            |
| `register_backend_ip(mac, ip)`            | `_handle_data`               | Pre-seed IP→MAC for storage (VIP deferred until SECONDARY) |
| `unregister_server_backend(mac)`          | `_handle_scale_down_compute` | Remove compute from VIP, clear warm lease                   |
| `unregister_storage_backend(mac, domain)` | `_handle_scale_down_data`    | Remove storage from VIP, clear warm lease                   |
| `add_server_mac(mac)`                     | Cancel drain                   | Re-admit MAC after drain cancel                             |

### Manager → Thread 2 (Completion Notification)

- `consume_addition_completions()` → `list[NodeInfo]` — new nodes to track.
- `consume_removal_completions()` → `set[str]` — MACs of fully removed nodes.

### Late Wiring (Two-Phase Construction)

The Tier 1 `PromotionCoordinator` needs a reference to the manager (for
`submit`), and the manager needs the coordinator (for `on_spawned`/`drain`
hooks). This circular dependency is resolved via setters called from
`main_n*.py` after both objects exist:

- `attach_selective_sync_coordinator(coordinator)`
- `attach_tier1_broadcaster(broadcast_fn)`

---

## 9. Tier 1 Reference

Tier 1 selective sync shares the same priority queue and cleanup dispatch
(`submit_cleanup`) as Tier 2 compute/storage. The manager handles Tier 1
alerts via the same `_loop` dispatch pattern, reusing the compute drain
model (Phase A drain → Phase B cleanup via `PendingDrain`).

The full Tier 1 subsystem — promotion predicate, state machine, manifest
protocol, coordinator lifecycle, and config knobs — lives in
[`selective_sync/selective_sync_overview.md`](../../selective_sync/selective_sync_overview.md).

The manager's Tier 1 integration is limited to:

- Dispatching `SelectiveSyncAlert` / `SelectiveSyncReconfigureAlert` /
  `ScaleDownSelectiveAlert` / `CleanupSelectiveAlert` via `isinstance` in
  `_loop()`.
- Routing Phase B cleanup by `PendingDrain.node_type == "selective_storage"`.
- Providing the `attach_selective_sync_coordinator` and
  `attach_tier1_broadcaster` late-wiring setters.
