# Compute Graceful Scale-Down Plan

**Status:** Implemented  
**Scope:** Compute scale-down only  
**Implementation model:** Controller-selected, edge-driven, cancelable quiesce

This folder is the phased implementation plan for replacing the current
one-way compute drain with a slower but safer workflow where the controller
starts scale-down, the edge server stays responsible for declaring completion,
and pending drains can be canceled after new compute scale-up has already been
submitted.

The plan is intentionally split into phases so the system can gain the
availability benefit first and then tighten controller behavior in later,
smaller steps.

These documents are prescriptive implementation plans. Each phase defines the
intended implementation and justifies why it is structured that way. The plan
does not present multiple code-level options for later selection.

---

## 1. Goals

1. Planned compute scale-down must not create avoidable client-visible errors.
2. The controller must stop choosing the newest dynamic compute node by LIFO
   and instead choose the least disruptive recent candidate.
3. If load rises again while a compute node is draining, the controller submits
   the new compute scale-up first and then submits a lower-priority cancel for
   the pending drain.
4. A draining edge server must advertise its state in telemetry as
   `state: active | draining`.
5. Missing telemetry remains a failure-detection concern handled by the normal
   absence cleanup path, not by the graceful scale-down path.

---

## 2. Cross-phase decisions

The following decisions are fixed for all phases in this folder:

1. **Telemetry state field.** Use `state: active | draining`, not
   `drain_state` and not `normal`.
2. **No redrain cooldown.** A canceled node can immediately become eligible
   again if it is still the best candidate later.
3. **Scale up before canceling compute drain.** If a pending compute drain
   exists and load rises, the controller should submit fresh compute capacity
   first, then submit a lower-priority drain cancel. Pending compute drains are
   subtracted from the effective dynamic compute count used by scale-up
   threshold and max-cap evaluation, while registry lifecycle state remains
   unchanged.
4. **No forced cleanup while telemetry is healthy.** If a draining node keeps
   sending telemetry, the drain is considered alive. If telemetry stops, the
   existing absence cleanup path handles the node.
5. **Recent cached telemetry only for graceful candidate selection.** Phase 2
   reuses the controller's retained `_server_stats` snapshot and applies a
   staleness bound before a quiet node can remain eligible for graceful
   compute scale-down candidate ranking.

---

## 3. Phase map

| Phase | Focus | Outcome | Can land independently? |
| --- | --- | --- | --- |
| Phase 1 (implemented) | Edge-driven quiesce and telemetry state | Removes the immediate 503-style drain behavior and introduces the reversible drain protocol surface | Landed |
| Phase 2 (implemented) | Least-disruptive candidate ranking | Replaces LIFO compute removal with a telemetry-ranked candidate selector backed by retained `_server_stats` plus a staleness bound | Landed |
| Phase 3 (implemented) | Scale-up-before-cancel and pending-drain reevaluation | Keeps scale-up responsive while canceling stale compute drains as lower-priority recovery work | Landed |

All three phases are implemented.

---

## 4. Why this sequencing

The phases are ordered by user-facing risk reduction:

1. **Phase 1 first** because it directly addressed the worst current symptom:
   planned compute drain returning errors while the node still receives some
   overlap traffic.
2. **Phase 2 second** because once drain was safe, the next most important
   improvement was choosing the least disruptive dynamic node instead of the
   most recently added one.
3. **Phase 3 last** because cancelable drains required the controller to relax
   its pending-drain gate and add cancel-aware control logic.

This order leaves each intermediate state coherent and testable.

---

## 5. Global file map

The complete phased plan is expected to touch the following implementation
surfaces over time:

- [source/docker/edge_server/source/app.py](../../../../../source/docker/edge_server/source/app.py)
- [source/docker/edge_server/source/telemetry.py](../../../../../source/docker/edge_server/source/telemetry.py)
- [source/docker/local_state_server/aggregator.py](../../../../../source/docker/local_state_server/aggregator.py)
- [source/sdn_controller/telemetry/models.py](../../../../../source/sdn_controller/telemetry/models.py)
- [source/sdn_controller/main_n1.py](../../../../../source/sdn_controller/main_n1.py)
- [source/sdn_controller/main_n2.py](../../../../../source/sdn_controller/main_n2.py)
- [source/sdn_controller/node_registry.py](../../../../../source/sdn_controller/node_registry.py)
- [source/sdn_controller/scaling_config.py](../../../../../source/sdn_controller/scaling_config.py)
- [source/sdn_controller/scaling_policy.py](../../../../../source/sdn_controller/scaling_policy.py)
- [source/sdn_controller/elasticity/compute_node_manager.py](../../../../../source/sdn_controller/elasticity/compute_node_manager.py)
- [source/sdn_controller/elasticity/elasticity.py](../../../../../source/sdn_controller/elasticity/elasticity.py)

Cross-phase documentation updates are expected in:

- [../../elasticity_overview.md](../../elasticity_overview.md)
- [../../../system_mechanisms.md](../../../system_mechanisms.md)
- [../../../telemetry/telemetry_overview.md](../../../telemetry/telemetry_overview.md)

---

## 6. End-to-end acceptance criteria

Once all three phases land together, the system must satisfy the following:

1. A compute node placed into scale-down no longer rejects workload requests
   solely because it is in drain mode.
2. Per-server telemetry exposes `state: active | draining` and the latest
   summary preserves that state for controller-side decisions and analysis.
3. Compute scale-down chooses the least-loaded fresh dynamic node rather than
   the newest dynamic node.
4. If a compute drain is pending and the system becomes loaded again, the
   controller submits `ComputeAlert` first and then submits a lower-priority
   `CancelComputeDrainAlert`.
5. If a draining server stops emitting telemetry, the existing absence path
   still removes it without requiring a special drain-timeout cleanup path.
6. Experiment logs and CSV-derived analysis are sufficient to explain when a
   drain started, whether it was canceled, and whether it completed normally.

---

## 7. Out of scope

This plan does **not** include:

1. Storage scale-down changes.
2. Tier 1 selective-storage drain changes.
3. A redrain cooldown.
4. A new failure-only cleanup path for healthy draining nodes.
5. Threshold retuning beyond what is necessary to support the new compute
   behavior.
