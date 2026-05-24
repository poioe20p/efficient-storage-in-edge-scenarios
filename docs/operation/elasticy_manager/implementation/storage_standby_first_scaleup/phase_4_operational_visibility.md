# Phase 4 - Operational Visibility

**Status:** Proposed  
**Primary outcome:** Make reserve behavior easy to reset, trace, and interpret
in logs and experiment artifacts.

This phase does not add new reserve semantics. It makes the earlier phases
operationally safe to run and easy to analyse.

---

## 1. Scope

In scope:

1. Ensure cleanup and reset flows remove standby containers and volumes.
2. Add stable controller log markers for standby lifecycle transitions.
3. Document how experiment artifacts should interpret reserve creation versus
   reserve activation.
4. Clarify the heartbeat exception for reserved standby storage in the
   operational docs.
5. Keep the plan friendly to the current `container_events.csv` and summary
   workflow.

Out of scope:

1. A new analysis CLI dedicated to standby behavior.
2. Runtime standby dashboards.
3. Automatic reserve replenishment after analysis detects the slot was spent.

---

## 2. Cleanup and reset expectations

The reserve naming rule from earlier phases is chosen to minimize extra cleanup
work:

1. The current dynamic-storage cleanup regex in
   [source/scripts/cleanup.sh](../../../../../source/scripts/cleanup.sh) already
   matches `edge_storage_lanX_dyn0-data` because it accepts any numeric `dynN`.
2. The reserve should therefore use `dyn0` consistently and avoid introducing a
   second cleanup naming convention.
3. Even if no functional cleanup change is required, the cleanup script should
   document that `dyn0` is the reserved-standby storage name.

Phase 4 should add an explicit comment or log line in cleanup docs so reserve
containers are not mistaken for stale experimental leftovers.

---

## 3. Log grammar

The controller should emit stable INFO log markers for the reserve lifecycle so
experiment summaries can separate background reserve preparation from the first
user-visible storage activation.

Recommended markers:

1. `[standby] prepare_submitted lan=%d`
2. `[standby] preparing lan=%d name=%s ip=%s mac=%s`
3. `[standby] ready_reserved lan=%d name=%s ip=%s mac=%s`
4. `[standby] activated lan=%d name=%s ip=%s mac=%s`
5. `[standby] first_alert_missed lan=%d`
6. `[standby] discard_submitted lan=%d name=%s`
7. `[standby] discarded lan=%d name=%s`

These markers should be added in the controller paths introduced by Phases 2
and 3, not synthesized later by external analysis.

---

## 4. Experiment interpretation rules

The reserve changes how experiment artifacts should be read:

1. `container_events.csv` will show `edge_storage_lanX_dyn0` appearing near the
   start of the run or shortly after controller startup. That is reserve
   preparation, not a reactive storage scale-up.
2. The first user-visible scale-up moment is the controller log line
   `[standby] activated ...`, not the `dyn0` container creation timestamp.
3. If the first storage alert misses the reserve, the controller log line
   `[standby] first_alert_missed ...` marks the moment the standby opportunity
   was lost for that LAN.
4. The first true cold-path storage scale-up after a miss remains the ordinary
   `data: spawning edge_storage_lanX_dyn1`-style event.

The docs in [docs/operation/testing/testing_overview.md](../../../testing/testing_overview.md)
should explicitly capture these rules so future run summaries do not credit the
reserve bootstrap time as the first storage scale-up time.

---

## 5. Step-by-step implementation

1. Update [source/scripts/cleanup.sh](../../../../../source/scripts/cleanup.sh)
   comments or volume-cleanup notes to document that `dyn0` is a valid standby
   storage container and volume name.
2. Add the standby lifecycle log markers listed above in the controller paths
   created by Phases 2 and 3.
3. Update [docs/operation/elasticy_manager/elasticity_overview.md](../../elasticity_overview.md)
   to explain the reserve lifecycle at a high level.
4. Update [docs/operation/system_mechanisms.md](../../../system_mechanisms.md)
   so the liveness and VIP-admission model explicitly mentions reserved
   standby storage.
5. Update [docs/operation/testing/testing_overview.md](../../../testing/testing_overview.md)
   with the experiment-interpretation rules above.
6. Update [docs/operation/archive/other/heartbeat_dynamic_node_gate_plan.md](../../../archive/other/heartbeat_dynamic_node_gate_plan.md)
   to document reserved standby storage as the explicit exception to the
   no-heartbeat dynamic-storage rule.

---

## 6. Verification

1. Run a reset and confirm `dyn0` standby containers and their volumes are
   removed along with other dynamic storage nodes.
2. Confirm the controller logs contain the stable standby markers in the
   expected order for prepare, ready, activate, miss, and discard paths.
3. Confirm `container_events.csv` can distinguish reserve preparation from
   reactive storage activation when paired with controller logs.
4. Confirm the updated testing docs explain how to measure first-alert
   activation correctly.
5. Confirm the heartbeat plan docs clearly identify reserved standby storage as
   a deliberate exception.

---

## 7. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Future run summaries misclassify reserve bootstrap as reactive scale-up | Define activation and miss log markers as the authoritative timing anchors |
| Operators manually remove the reserve because it looks like an orphaned dynamic node | Document `dyn0` naming explicitly in cleanup and elasticity docs |
| The heartbeat exception is forgotten and later refactors remove standby liveness | Update the heartbeat plan docs and the elasticity overview to keep the exception explicit |
