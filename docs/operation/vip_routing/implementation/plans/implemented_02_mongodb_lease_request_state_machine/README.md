# MongoDB Request Lease State Machine - Phased Implementation

**Status:** Implemented baseline; Phase 4 optional follow-on
**Scope:** Edge-server request-local storage-path ownership above the
implemented LAN-scoped epoch baseline
**Implementation model:** Keep epochs as the lower-level storage-path owner,
add request-local lease semantics above them

This folder records the phased implementation plan that introduced
request-scoped MongoDB storage leases. The existing LAN-scoped epoch model remains the owner
of the `MongoClient`, the bound VIP, the per-LAN breaker, and retirement and
rollback. The request-lease layer adds request-local semantics on top:

- when a request first binds to a storage path
- when later DB work in the same request must reuse that path
- when a hard connection failure may cut that request over once to recovery
- when the request must fail instead of silently rebinding

The shared concurrency-sensitive decisions for one LAN still belong to one
per-LAN authority state. Fresh admission, current-versus-stale failure
classification, and epoch-tagged breaker state should not be split across
independent check-then-act helpers.

Phases 1-3 are now implemented in
[source/docker/edge_server/source/app.py](../../../../../../source/docker/edge_server/source/app.py)
and
[source/docker/edge_server/source/telemetry.py](../../../../../../source/docker/edge_server/source/telemetry.py).
The remaining phase in this folder describes the optional replay refinement
above that baseline.

Current baseline behavior is summarized in:

- [../../vip_routing_overview.md](../../vip_routing_overview.md)
- [../../../system_mechanisms.md](../../../system_mechanisms.md)
- [../vip_data_recovery_epoch_model.md](../vip_data_recovery_epoch_model.md)
- [../../../other/edge_storage_connection_epoch_visuals.md](../../../other/edge_storage_connection_epoch_visuals.md)

Use those overview documents as the primary reference for landed behavior.
This folder is kept mainly as the phased implementation record for Phases 1-3
and as the home of the still-optional Phase 4 follow-on.

The plan is intentionally split into phases so the edge server can first gain
request-local lease ownership, then add bounded recovery semantics, then make
the new behavior visible in telemetry and docs, and only then refine replay
safety further if experiments actually need it.

The split is by scope and code surface, not by a requirement that each phase be
independently deployable or preserve full end-to-end behavior before the later
phases exist.

---

## 1. Goals

1. One HTTP request should hold at most one storage lease per owner LAN.
2. Repeated DB work in the same request and owner LAN should reuse the same
   request lease instead of looking like repeated independent checkouts.
3. The request lease should point to one LAN-scoped epoch rather than creating
   a new `MongoClient` per request.
4. Hard connection failure should allow at most one bounded failure-driven
   rebind per request and owner LAN.
5. Replay-unsafe requests should fail conservatively instead of silently
   rebinding to a different backend path.
6. The final request-lease design should still rest on the current epoch model,
   `/vip_data` behavior, and recovery-VIP baseline, even if intermediate
   phases temporarily reshape local mechanics while the full sequence lands.
7. The resulting request outcomes should be easy to trace in logs and, when
   useful, in telemetry.

---

## 2. Cross-phase Decisions

The following decisions are fixed for all phases in this folder:

1. **Epochs remain the lower-level owner.** The request lease points to an
   epoch; it does not replace epoch lifecycle.
2. **One request lease per owner LAN.** A single request may hold multiple
   leases only when it touches multiple owner LANs.
3. **No new controller selector logic here.** This folder changes edge-server
   request semantics only; controller-side failed-backend avoidance remains in
   the separate `03_` plan.
4. **No per-request direct backend steering.** Requests still reach storage via
   `VIP_DATA` or `VIP_DATA_RECOVERY`, not by dialing real backend IPs.
5. **One bounded rebind allowance.** First bind is free, and a request gets
   at most one failure-driven rebind for a given owner LAN. That rebind may
   either trigger authoritative current `normal -> recovery` cutover or catch
   the request up to the already-current epoch.
6. **One shared decision owner per LAN.** Admit-and-bind, current-versus-stale
   classification, and breaker state for one LAN must be linearized through
   the same LAN authority state.
7. **Conservative replay safety first.** Until a later optional refinement is
   proven correct, ambiguous or mutating operations are treated as replay
   unsafe.
8. **No legacy app-facing compatibility after Phase 2.** Once the explicit
   retry boundary lands, serving-path MongoDB work moves to
   `run_with_request_lease(...)`; `timed_db(...)` may remain only as an
   extracted internal seam or be removed.
9. **Request teardown releases leases.** Per-call `timed_db(...)` exit should
   no longer be the final release boundary once Phase 1 lands.
10. **Breaker gating is current-epoch aware and does not force mid-request invalidation.**
   One shared breaker object still exists per LAN, but its admission state is
   tagged to the authoritative current epoch id. It can block first
   acquisition for that epoch without revoking reuse of a lease already held by
   the current request.
11. **Visibility follows semantics.** Telemetry and docs should reflect the
   final request-lease model, not a temporary intermediate shape.

---

## 3. Phase Map

| Phase | Status | Focus | Outcome | Primary code surface |
| --- | --- | --- | --- | --- |
| [Phase 1](./phase_1_request_lease_registry_and_teardown.md) | Implemented | Request-local registry and teardown | One request-owned lease per owner LAN, reused across repeated DB blocks | `app.py` |
| [Phase 2](./phase_2_bounded_recovery_cutover_and_replay_gate.md) | Implemented | Bounded rebind and replay gate | One explicit request-level rebind allowance with conservative failure semantics, stale-epoch catch-up, Option B epoch-tagged breaker admission, and one clear per-LAN authority for admit-and-bind and classify-and-rebind decisions | `app.py`, `platform_cache.py` |
| [Phase 3](./phase_3_request_lease_outcome_visibility.md) | Implemented | Outcome visibility | Request lease outcomes become visible in edge-server logs and per-request telemetry, while controller-trigger wiring remains separate | `app.py`, `telemetry.py` |
| [Phase 4](./phase_4_optional_replay_safety_refinement.md) | Optional follow-on | Finer replay safety | Safer recovery for provably replay-safe operations only | `app.py`, `platform_cache.py` |

Implemented baseline: Phases 1-3.

Remaining merge order: Phase 4.

---

## 4. Why This Sequencing

1. **Phase 1 first and now baseline** because request ownership had to exist
   before recovery and replay semantics could be attached to it.
2. **Phase 2 second** because bounded cutover only makes sense once the system
   can say which request lease is being cut over.
3. **Phase 3 third** because visibility should describe the final request
   semantics, not a partial intermediate model.
4. **Phase 4 last** because replay-safety refinement should sit on top of the
   conservative model, not replace it before the base behavior is validated.

---

## 5. Global File Map

The complete phased plan touched or may still touch the following implementation
surfaces over time:

- [source/docker/edge_server/source/app.py](../../../../../../source/docker/edge_server/source/app.py)
- [source/docker/edge_server/source/platform_cache.py](../../../../../../source/docker/edge_server/source/platform_cache.py)
- [source/docker/edge_server/source/telemetry.py](../../../../../../source/docker/edge_server/source/telemetry.py)

Cross-phase documentation updates are expected in:

- [../../vip_routing_overview.md](../../vip_routing_overview.md)
- [../../../system_mechanisms.md](../../../system_mechanisms.md)
- [../vip_data_recovery_epoch_model.md](../vip_data_recovery_epoch_model.md)
- [../../../other/edge_storage_connection_epoch_visuals.md](../../../other/edge_storage_connection_epoch_visuals.md)

---

## 6. End-to-End Acceptance Criteria

Once all non-optional phases land together, the system must satisfy the
following:

1. A request that performs multiple DB operations against the same owner LAN
   binds once and reuses that binding.
2. A request that touches multiple owner LANs can hold separate leases without
   confusing their epochs or VIP paths.
3. A read-only request can use one bounded failure-driven rebind after a real
   connection failure.
4. Fresh admission, leased epoch selection, and breaker state for one LAN all
   refer to the same authoritative current epoch id.
5. Current-versus-stale failure classification and adopted epoch come from one
   decision point rather than from separate unlocked snapshots.
6. A replay-unsafe request fails instead of silently rebinding to a new
   storage path.
7. Request teardown releases all remaining leases, even on error paths.
8. Lease outcome visibility is sufficient to distinguish healthy completion,
   one-rebind recovery or catch-up completion, and terminal failure.
