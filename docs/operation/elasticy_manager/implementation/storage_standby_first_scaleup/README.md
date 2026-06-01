# Storage Standby for First Scale-Up Plan

**Status:** Proposed  
**Scope:** Same-LAN Tier 2 storage scale-up only  
**Implementation model:** Launch-time feature-flagged hot standby per LAN

This folder is the phased implementation plan for introducing one reserved
dynamic storage standby per LAN. The standby is a real MongoDB secondary that
joins the local replica set ahead of demand, remains outside `VIP_DATA_N*`
while reserved, and is consumed only by the first storage scale-up in that LAN.

The plan is intentionally split into phases so the controller can gain the
state model first, then safely prepare the standby, then activate it on the
first alert, and finally tighten operational visibility and cleanup semantics.

These documents are prescriptive implementation plans. Each phase defines the
intended implementation and justifies why it is structured that way. The plan
does not present multiple code-level options for later selection.

---

## 1. Goals

1. When the feature is enabled, each LAN must maintain exactly one reserved
   storage standby.
2. The feature must be easy to enable or disable at launch time through the
   existing environment-backed controller config pattern.
3. The standby must be a real `SECONDARY`, not a stopped container, cache, or
   partially prepared volume.
4. The standby must heartbeat while reserved so it is intentionally visible to
   the controller even when idle.
5. The standby must stay out of `VIP_DATA_N*` until the first storage
   scale-up for that LAN consumes it.
6. The standby must not perturb the current adaptive storage threshold or the
   normal storage scale-down path while it is still reserved.
7. Later storage scale-ups must fall back to the current on-demand Tier 2 path
   after the reserve has been consumed or missed once.

---

## 2. Cross-phase decisions

The following decisions are fixed for all phases in this folder:

1. **One reserve per LAN.** Phase 1 targets exactly one same-LAN standby for
   `lan1` and one for `lan2`. No standby pool and no multiple-reserve support.
2. **Launch-time feature flag only.** The plan introduces a startup-time
   master switch, not live in-process toggling.
3. **Real secondary, not warm shell.** The reserve is a fully joined
   `SECONDARY` using the current storage sidecar join path.
4. **Heartbeat-enabled exception.** Reserved standby storage runs with
   `HEARTBEAT_ENABLED=true` even though ordinary dynamic storage keeps the
   default disabled behavior.
5. **Out of VIP while reserved.** `rs_secondary_ready` does not imply VIP
   promotion when the node is marked reserved standby.
6. **Excluded from adaptive counts.** Reserved standby storage does not count
   toward `count_dynamic("storage")`, does not raise the effective storage
   scale-up threshold, and is not eligible for ordinary storage scale-down.
7. **Consumed once.** The first storage scale-up for a LAN either activates the
   ready reserve or spends the reserve opportunity and falls back to the
   current cold path. No replenishment happens in this plan.
8. **Shared LAN IP allocator.** The reserve consumes a normal dynamic LAN IP
   and MAC from the existing shared `IpAllocator`; no separate address pool is
   introduced.
9. **Deterministic reserve name.** The reserved standby uses
   `edge_storage_lanX_dyn0`, leaving the current `_next_name(...)` sequence to
   continue with `dyn1`, `dyn2`, and so on for reactive adds.
10. **Heartbeat persists after activation.** Once the reserve is consumed, the
    running container remains heartbeat-enabled for the rest of its lifetime in
    phase 1. No midlife heartbeat reconfiguration is attempted.

---

## 3. Phase map

| Phase | Focus | Outcome | Can land independently? |
| --- | --- | --- | --- |
| [Phase 1](./phase_1_state_and_accounting.md) | Standby state model and safe accounting | Adds the controller-side standby slot model, feature flag, and exclusions from normal dynamic storage accounting | Yes |
| [Phase 2](./phase_2_reserve_preparation.md) | Reserve preparation and readiness gating | Bootstraps one heartbeating secondary per LAN and holds it outside the VIP pool while reserved | Yes |
| [Phase 3](./phase_3_first_alert_activation.md) | First-alert activation and miss semantics | Consumes the ready reserve on the first storage alert or spends and discards it when the first alert arrives too early | Yes |
| [Phase 4](./phase_4_operational_visibility.md) | Cleanup, logging, and experiment visibility | Makes reserve behavior easy to reset, trace, and interpret in run artifacts | Yes |

The intended merge order is Phase 1 -> Phase 2 -> Phase 3 -> Phase 4.

---

## 4. Why this sequencing

The phases are ordered by correctness boundaries rather than by raw speedup:

1. **Phase 1 first** because the system needs a separate controller state for
   reserved standby storage before any container exists. Without that state,
   the reserve would be miscounted as ordinary dynamic storage and immediately
   conflict with the current scale-down and threshold logic.
2. **Phase 2 second** because once the controller can represent a reserve
   safely, the standby container can be prepared using the current Tier 2 join
   path without changing first-alert behavior yet.
3. **Phase 3 third** because activation is the first phase that changes how a
   real `DataAlert` is consumed. By then the reserve already exists and has a
   well-defined reserved state.
4. **Phase 4 last** because observability and cleanup should follow the final
   lifecycle semantics, not precede them.

This order leaves each intermediate state coherent and testable.

---

## 5. Global file map

The complete phased plan is expected to touch the following implementation
surfaces over time:

- [source/sdn_controller/scaling_config.py](../../../../../source/sdn_controller/scaling_config.py)
- [source/sdn_controller/main_n1.py](../../../../../source/sdn_controller/main_n1.py)
- [source/sdn_controller/main_n2.py](../../../../../source/sdn_controller/main_n2.py)
- [source/sdn_controller/node_registry.py](../../../../../source/sdn_controller/node_registry.py)
- [source/sdn_controller/control_events.py](../../../../../source/sdn_controller/control_events.py)
- [source/sdn_controller/elasticity/elasticity.py](../../../../../source/sdn_controller/elasticity/elasticity.py)
- [source/sdn_controller/elasticity/node_common.py](../../../../../source/sdn_controller/elasticity/node_common.py)
- [source/sdn_controller/elasticity/storage_node_manager.py](../../../../../source/sdn_controller/elasticity/storage_node_manager.py)
- [source/docker/edge_storage_server/mongo_telemetry.py](../../../../../source/docker/edge_storage_server/mongo_telemetry.py)
- [source/scripts/cleanup.sh](../../../../../source/scripts/cleanup.sh)

Cross-phase documentation updates are expected in:

- [../../scale_up/storage_scale_up.md](../../scale_up/storage_scale_up.md)
- [../../../system_mechanisms.md](../../../system_mechanisms.md)
- [../../../testing/testing_overview.md](../../../testing/testing_overview.md)
- [../../../archive/other/heartbeat_dynamic_node_gate_plan.md](../../../archive/other/heartbeat_dynamic_node_gate_plan.md)

---

## 6. End-to-end acceptance criteria

Once all phases land together, the system must satisfy the following:

1. With `STANDBY_STORAGE_ENABLED=0`, no standby storage node is prepared and
   the current Tier 2 storage scale-up path is unchanged.
2. With `STANDBY_STORAGE_ENABLED=1`, exactly one standby storage node per LAN
   is prepared, reaches `SECONDARY`, and remains outside the VIP storage pool.
3. Reserved standby storage emits heartbeats while idle and is therefore
   intentionally visible to the controller during the reserved period.
4. Reserved standby storage does not contribute to the adaptive storage
   threshold and is not selected by the ordinary storage scale-down path.
5. If the first storage scale-up for a LAN occurs after the standby is ready,
   the controller activates that standby without spawning a new storage
   container for that first alert.
6. If the first storage scale-up for a LAN occurs before the standby is ready,
   the controller falls back to the current on-demand storage add path and the
   standby opportunity is spent for that LAN.
7. After the reserve is consumed or missed once, later storage scale-ups use
   the current on-demand Tier 2 path.
8. A consumed standby becomes an ordinary active dynamic storage node and can
   later be removed by the normal storage scale-down path.

---

## 7. Out of scope

This plan does **not** include:

1. Live runtime toggling after the controllers are already running.
2. A standby pool larger than one node per LAN.
3. Automatic standby replenishment after activation or removal.
4. Cross-LAN standby replicas.
5. Serving from a reserve before it reaches `SECONDARY`.
6. A separate standby-specific routing policy once the reserve is active.
7. Compute standby or Tier 1 selective-sync standby behavior.
