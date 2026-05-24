# MongoDB Lease Failed-Backend Avoidance - Phased Implementation

**Status:** Implemented baseline retained for implementation history
**Scope:** Controller-local storage selection behavior for recovery VIP traffic
based on the last normal backend chosen for the same edge server and domain
**Implementation model:** keep request retry semantics entirely in the edge
request-lease model, and keep controller logic to one narrow job: avoid the
previous normal backend when selecting a recovery backend if another candidate
exists

This folder records the phased implementation plan for the controller-side
failed-backend-avoidance follow-up that is now implemented. It assumes the current warm-first storage
selection and recovery-VIP baseline already exist, and it also assumes the
request-lease model from the `02_` plan can already distinguish:

- current normal epoch that can rotate to recovery
- stale failed epoch that can adopt already-current state
- authoritative current recovery failure that is terminal for the request

The design goal is intentionally narrow: the controller remembers the most
recent backend it chose for normal `VIP_DATA` for a given
`(edge_server_mac, domain)`, then uses that memory only when the same edge
server later reaches `VIP_DATA_RECOVERY` for that domain.

Current baseline behavior is summarized in:

- [../../vip_routing_overview.md](../../vip_routing_overview.md)
- [../../../system_mechanisms.md](../../../system_mechanisms.md)
- [../vip_data_recovery_epoch_model.md](../vip_data_recovery_epoch_model.md)

Use those overview documents as the primary reference for landed behavior.
This folder is kept mainly as the phased implementation record for the landed
avoidance work.

---

## 1. Goals

1. Keep the behavior storage-specific and recovery-specific.
2. Bind controller memory to `(edge_server_mac, domain)`, not to request IDs.
3. Make recovery selection avoid the backend most recently chosen for normal
   `VIP_DATA` when another candidate exists.
4. Preserve warm-first then WSM selection order on the filtered candidate
   pool.
5. Fall back to the full candidate pool if filtering would otherwise drop all
   options.
6. Keep request budget, request terminality, and repeated recovery failure
   semantics in the edge request-lease model, not in the controller.

---

## 2. Cross-phase Decisions

1. **Key by `(edge_server_mac, domain)`.** The storage selector already uses
   the edge server MAC as `client_mac` for `VIP_DATA` decisions.
2. **Remember only the last normal backend.** Recovery selections should not
   overwrite that memory because recovery traffic must continue to know which
   prior normal backend to avoid.
3. **Apply only on recovery selection.** Normal steady-state selection should
   remain unchanged.
4. **Do not add controller-side request semantics.** No request budget,
   request IDs, retry counters, or controller-side recovery-hopping model are
   introduced here.
5. **Respect the existing selector stack.** Warm-lease claiming still runs
   first, but against the filtered pool when recovery selection is active.
6. **Stay controller-local.** This plan does not require a new edge-to-
   controller event path.

---

## 3. Phase Map

| Phase | Status | Focus | Outcome | Can land independently? |
| --- | --- | --- | --- | --- |
| [Phase 1](./phase_1_terminal_failure_event_contract.md) | Implemented | Controller-local last-normal attribution | The controller remembers the most recent normal backend per `(edge_server_mac, domain)` | Yes |
| [Phase 2](./phase_2_controller_avoidance_state_and_last_choice.md) | Implemented | Recovery-only different-backend selection | Recovery selection excludes the remembered normal backend when another candidate exists | No - depends on Phase 1 |
| [Phase 3](./phase_3_recovery_only_selector_filtering.md) | Implemented | Cleanup, boundaries, and reasonable outcomes | Local unregister cleanup is added, peer disappearance stays safe via pool fallback, and the non-goals are made explicit | Yes - after Phase 1 and Phase 2 exist |

Implemented baseline: Phases 1-3.

Remaining merge order: None.

---

## 4. Why This Sequencing

1. **Phase 1 first and now baseline** because the controller could not
   deliberately choose a different recovery backend until it remembered what
   it chose during normal routing.
2. **Phase 2 second and now baseline** because recovery filtering is the
   actual behavior change, and it depended on Phase 1's remembered normal
   attribution.
3. **Phase 3 third and now baseline** because cleanup and explicit boundary
   documentation complete the implemented controller-local behavior without
   widening the controller's request semantics.

---

## 5. Global File Map

The complete phased plan touched the following implementation surface:

- [source/sdn_controller/vip_routing.py](../../../../../../source/sdn_controller/vip_routing.py)

Cross-phase documentation updates are reflected in:

- [../../vip_routing_overview.md](../../vip_routing_overview.md)
- [../../../system_mechanisms.md](../../../system_mechanisms.md)
- [../vip_data_recovery_epoch_model.md](../vip_data_recovery_epoch_model.md)

---

## 6. End-to-End Acceptance Criteria

The implemented baseline now satisfies the following:

1. After normal `VIP_DATA` chooses backend `S2` for `(edge_server_mac, domain)`,
   the next `VIP_DATA_RECOVERY` selection for that same key avoids `S2` when
   another candidate exists.
2. Recovery selection still uses the existing warm-first then WSM order on the
   filtered pool.
3. Normal steady-state selection remains unchanged apart from refreshing the
   remembered normal backend.
4. Requests that first bind while the shared current epoch is already recovery
   still consult the remembered normal backend if one exists.
5. Failure on the authoritative current recovery epoch remains terminal for the
   request; the controller does not invent another backend hop for that same
   request.
6. Local `unregister_storage_backend(...)` cleanup clears remembered entries
   that still point at removed backends.
7. If a remembered peer backend disappears from the current pool, recovery
   filtering remains safe through the existing pool-membership fallback.
8. Single-backend pools still fall back safely to the full pool.
