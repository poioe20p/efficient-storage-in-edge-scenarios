# MongoDB Request Lease State Machine Plan

**Status:** Implemented baseline; Phase 4 optional follow-on
**Primary files:**

- [app.py](../../../../../source/docker/edge_server/source/app.py)
- [platform_cache.py](../../../../../source/docker/edge_server/source/platform_cache.py)

Reference background:

- [01_mongodb_lease_warm_start_and_recovery_path_plan.md](./01_mongodb_lease_warm_start_and_recovery_path_plan.md)
- [vip_data_recovery_epoch_model.md](../vip_data_recovery_epoch_model.md)
- [edge_storage_connection_hard_failure_epoch_plan.md](../../../other/edge_storage_connection_hard_failure_epoch_plan.md)

## Objective

Introduce a request-scoped storage-path lease model that separates three
different concerns that are currently too close together in the runtime:

1. initial storage-path and epoch selection for new work
2. stable epoch and storage-path reuse while an HTTP request is still in flight
3. one bounded failure-driven rebind after a real storage-path connection
   failure

The implemented LAN-scoped epoch model remains the lower-level storage-path
owner for the `MongoClient`, breaker, bound VIP, and retirement lifecycle.
This plan adds a request-scoped lease layer above that epoch model so a single
HTTP request can distinguish between normal placement, stable reuse, and
failure recovery without relying on legacy per-call lease behavior.

The request lease is not direct pinning to a specific MongoDB replica member.
It points to one LAN-scoped epoch, and that epoch remains the owner of the
actual bound VIP and client lifecycle.

Shared concurrency-sensitive decisions do not belong to the request lease
itself. They belong to one per-LAN authority state that owns the authoritative
current epoch, breaker admission, and retirement bookkeeping.

## Implemented Baseline

- [app.py](../../../../../source/docker/edge_server/source/app.py) already owns
  LAN-scoped epochs, the bound VIP snapshot, the per-LAN breaker, and epoch
  retirement and rollback.
- [app.py](../../../../../source/docker/edge_server/source/app.py) now also
   has the Phase 1 request-local lease registry keyed by LAN, request-owned
   `timed_db(...)` reuse, breaker-gated first acquisition, and request teardown
   release of held epochs once per LAN.
- [vip_routing.py](../../../../../source/sdn_controller/vip_routing.py)
  already owns steady-state `VIP_DATA` routing and narrow recovery-VIP flow
  installation.
- `/vip_data` configuration semantics, recovery-VIP plumbing, and warm-lease
  behavior are already part of the baseline described in
  [01_mongodb_lease_warm_start_and_recovery_path_plan.md](./01_mongodb_lease_warm_start_and_recovery_path_plan.md).

This plan does not reopen those implemented pieces. Phases 1-3 are now treated
as baseline. The remaining work is the optional replay-safety refinement above
that baseline, plus the separate controller-side avoidance baseline already
captured in the `03_` plan family.

Current baseline behavior is summarized in:

- [../../vip_routing_overview.md](../../vip_routing_overview.md)
- [../../../system_mechanisms.md](../../../system_mechanisms.md)
- [../vip_data_recovery_epoch_model.md](../vip_data_recovery_epoch_model.md)
- [../../../other/edge_storage_connection_epoch_visuals.md](../../../other/edge_storage_connection_epoch_visuals.md)

Use those overview documents as the primary reference for landed behavior.
This plan file and the folder below are kept mainly as the phased
implementation record for Phases 1-3 and as the home of the still-optional
Phase 4 follow-on.

## Detailed Phased Subplans

The phased implementation breakdown for this plan now lives in:

- [README.md](./implemented_02_mongodb_lease_request_state_machine/README.md)
- [Phase 1 - Request Lease Registry And Teardown](./implemented_02_mongodb_lease_request_state_machine/phase_1_request_lease_registry_and_teardown.md)
- [Phase 2 - Bounded Rebind And Replay Gate](./implemented_02_mongodb_lease_request_state_machine/phase_2_bounded_recovery_cutover_and_replay_gate.md)
- [Phase 3 - Request Lease Outcome Visibility](./implemented_02_mongodb_lease_request_state_machine/phase_3_request_lease_outcome_visibility.md)
- [Phase 4 - Optional Replay Safety Refinement](./implemented_02_mongodb_lease_request_state_machine/phase_4_optional_replay_safety_refinement.md)

This umbrella file stays as the design summary. The folder above carries the
retained phase-by-phase implementation notes and the remaining optional follow-
on.

## Problem Statement

The current epoch model already prevents immediate reuse of a failed shared
client object, and Phase 1 now makes request ownership explicit: multiple
`timed_db(...)` blocks inside one HTTP request reuse one request-owned lease
per owner LAN. The remaining gap is that failure semantics above that lease
are still implicit, while the controller's steady-state `VIP_DATA` flow
remains broader than one TCP connection.

That creates a conceptual gap:

- request-local ownership now exists, but bounded rebind policy, replay safety,
  and one clear shared decision owner are not yet first-class parts of the
  design
- request-terminal failure outcome is not explicit enough for later optional
   controller follow-up
- request failure outcome is not explicit enough for later optional controller
  follow-up

The thesis-facing model should instead treat each HTTP request as moving
through a small state machine per owner domain.

## Design Principles

1. Fresh-request admission and epoch binding for one LAN must be one linearized
   admit-and-bind decision for one authoritative current epoch id.
2. Stable epoch reuse is preserved inside an existing request lease.
3. One HTTP request may hold separate leases for separate owner domains.
4. Background pool changes affect future leases, not already bound ones.
5. Shared concurrency-sensitive decisions for one LAN are made by one per-LAN
   authority state, not by separate check-then-act helpers.
6. Slow is not automatically broken; soft degradation does not force rebind.
7. Hard connection failure is handled by one bounded request-local rebind;
   that rebind may either trigger `normal -> recovery` cutover for the
   authoritative current epoch or catch the request up to an already-current
   epoch.
8. Replay-unsafe requests fail instead of silently rebinding.
9. Controller-side failed-backend avoidance remains a separate optional
   follow-up in
   [implemented_03_mongodb_lease_failed_backend_avoidance_plan.md](./implemented_03_mongodb_lease_failed_backend_avoidance_plan.md).
10. No legacy compatibility path is kept once Phase 2 lands; app-facing
    retryable MongoDB work moves to `run_with_request_lease(...)` instead of
    preserving `timed_db(...)` as the public serving-path surface.
11. Fresh-request admission is controlled by one shared per-LAN breaker whose
    state is tagged to the authoritative current epoch id; it blocks new
    leases for that epoch without revoking a lease already held by the current
    request.

## Scope

### In scope

- explicit request-lease lifecycle, bounded failure-driven rebind, terminal
   failure, and completion
- conservative replay-safety gating for bounded rebind
- current-epoch-aware fresh-request admission and breaker accounting
- one explicit per-LAN shared authority for admit-and-bind, rebind
   classification, and epoch-tagged breaker state
- request-terminal lease outcomes needed by later observability or optional
  controller follow-up
- documentation updates that explain the ownership split between request lease
  and LAN epoch

### Out of scope

- controller-side failed-backend avoidance itself
- warm-lease rollout or recovery-VIP rollout work that is already implemented
- `/vip_data` refresh behavior, startup LAN registry seeding, or epoch
  housekeeping baseline
- compute routing or compute elasticity changes

## Request Lease Model

### Lease Identity

The new logical lease key is:

```text
(request_id, owner_domain)
```

This tuple is the logical state-machine identity, not the concrete in-memory
registry key used by Phase 1. The Phase 1 registry is keyed only by
`owner_domain` inside the current Flask request. The bound epoch mode remains
derived from `lease.epoch.mode`, while lifecycle and rebind accounting live on
that same request-owned lease record instead of creating a second registry
entry.

Each request-scoped lease points to one LAN-scoped epoch. The epoch still owns
the actual `MongoClient` and storage-path lifecycle, while the request lease
owns the decision about whether this request is still allowed to keep using
that epoch. It does not own direct pinning to a specific MongoDB backend
member.

### Scope Separation

| Scope | Owns | Lifetime | Identity |
| --- | --- | --- | --- |
| Request lease | request-local permission to keep using one LAN-scoped epoch and storage path for one HTTP request in one owner domain | one HTTP request | logical identity `(request_id, owner_domain)` |
| LAN authority state | authoritative current epoch id, epoch-tagged breaker state, and retiring-epoch bookkeeping for one LAN | process lifetime | `(lan)` |
| LAN epoch | one concrete epoch object that owns one `MongoClient`, one bound VIP, and one retirement lifecycle | until replaced and drained | `(lan, epoch_id)` |
| Steady-state controller flow | DNAT/SNAT selection for an edge-server storage path | until timeout | `(edge_server_mac, domain_vip)` |
| Recovery controller flow | bounded recovery reconnect path | one recovery TCP connection | `(edge_server_mac, recovery_vip, tcp_src, tcp_dst)` |

The deliberate asymmetry is important: request leases are finer-grained than
controller flow rules. The app preserves request-local storage semantics,
while the controller still operates at the edge-server flow level.

The other important asymmetry is inside the edge server itself: request leases
are request-local references, but the LAN authority state is the only shared
decision owner. If breaker admission is checked on one epoch id and binding is
done on another, the design is wrong even if the request lease structure looks
clean afterward.

## Request State Machine

### States

`UNBOUND` is the conceptual state where the current request has not yet created
any lease record for that owner domain. In the concrete request-local registry,
that means there is no `RequestLease` object yet for that LAN. Materialized
lease records therefore start in `ACTIVE` once the first bind occurs.

These are request lifecycle states only. They do not encode whether the bound
epoch is `normal` or `recovery`; current epoch mode is derived from
`lease.epoch.mode`.

| State | Meaning |
| --- | --- |
| `UNBOUND` | request has not yet created a lease for this owner domain |
| `ACTIVE` | request holds one lease for this owner domain and may keep using or rebind it according to replay and rebind policy |
| `FAILED` | request cannot continue safely on this owner domain |
| `COMPLETED` | request ended and the lease was released |

### Core Transitions

| Transition | Trigger | Decision |
| --- | --- | --- |
| `UNBOUND -> ACTIVE` | first DB access for a domain | acquire one request-owned epoch and storage path |
| `ACTIVE -> ACTIVE` | later DB work in same domain | keep the current request-owned epoch |
| `ACTIVE -> ACTIVE` | hard connection failure before replay becomes unsafe | rebind once, either by triggering current `normal -> recovery` cutover or by catching up to the already-current epoch |
| `ACTIVE -> FAILED` | current `recovery` fails, replay becomes unsafe, or rebind is already exhausted | fail request |
| `ACTIVE -> COMPLETED` | request ends | release lease |

### Storage-Path Situations

1. **Request start, no storage path yet.**
   Decision: perform one linearized admit-and-bind decision for the
   authoritative current epoch and create one request-owned lease.
2. **Request still running, same lease healthy.**
   Decision: keep the same epoch and storage path for later DB work in that
   domain.
3. **Request still running, different owner domain needed.**
   Decision: create a second lease, but only for that other domain.
4. **Backend pool changes in the background.**
   Decision: keep the existing request lease unchanged.
5. **Soft degradation only.**
   Decision: keep the lease unless request-level timeout policy says otherwise.
6. **Hard connection failure on the authoritative current normal epoch before replay becomes unsafe.**
   Decision: use one linearized classify-and-rebind decision to trigger the
   shared `normal -> recovery` cutover once and rebind the same request-owned
   lease to the new current epoch.
7. **Hard connection failure on a stale epoch.**
   Decision: use that same linearized classify-and-rebind decision to catch
   the request-owned lease up to the already-current epoch without mutating
   global LAN state.
8. **Failure after an unsafe replay point or on the authoritative current recovery epoch.**
   Decision: fail the request instead of rebinding.
9. **Request end.**
   Decision: release every domain lease held by the request.

## Phases

### Phase 1 - Implemented Request-Scoped Lease Layer

**Status:** Implemented in
[app.py](../../../../../source/docker/edge_server/source/app.py).

**Goal:** replace per-`timed_db(...)` lease and release with one request-scoped
lease per owner domain.

**Scope:** edge-server app only.

**Changes:**

1. Add a request-local lease registry on `flask.g`.
2. Rewrite `timed_db(lan)` so the first call for a domain acquires the current
   epoch and stores it on the request.
3. Reuse that lease for later `timed_db(lan)` calls in the same request.
4. Gate only first acquisition on the shared breaker; reuse of an already-held
   request lease continues even if the breaker opened after the lease was
   created.
5. Release all held leases during request teardown.
6. Remove the legacy per-call lease and release path instead of keeping a
   compatibility branch.

**Verification:**

1. A request that touches `lan1` multiple times produces one epoch checkout and
   one release.
2. Separate concurrent requests still keep separate request-local lease state.
3. `T_dados` accumulation remains per DB block.

Phase 1 is now baseline for the remaining phases.

### Phase 2 - Request State Machine and Replay-Safety Gate

**Goal:** add explicit request-lease lifecycle, one bounded failure-driven
rebind, and one clear per-LAN authority for shared decisions.

**Scope:** edge-server app and request-local operation tracking.

**Assumptions:**

1. First bind is free; a request may consume at most one failure-driven
   rebind for a given owner LAN.
2. Fresh-request admission is controlled by one shared per-LAN breaker whose
   state is tagged to the authoritative current epoch id.
3. Conservative replay-safety default: once a non-idempotent write has been
   executed or may have become ambiguous, later storage failure for that
   request is terminal.
4. The currently exercised serving workload is read-only; broader VIP-backed
   write instrumentation is optional follow-up unless serving routes add such
   writes later.

**Changes:**

1. Add `ACTIVE`, `FAILED`, and `COMPLETED` lifecycle tracking on materialized
   request leases, with `UNBOUND` represented by the absence of a lease record
   before first bind.
2. Replace split breaker-check then bind behavior with one linearized
   admit-and-bind helper so the breaker decision and leased epoch always refer
   to the same authoritative current epoch id.
3. Replace unlocked current-versus-stale classification with one linearized
   classify-and-rebind helper so failure classification and adopted epoch come
   from the same decision point.
4. Extract the current `timed_db(...)` responsibilities into a reusable
   one-shot helper, make `run_with_request_lease(...)` the app-facing
   boundary, and convert route-level owner-LAN MongoDB work to that helper.
5. Mark requests replay-unsafe after mutating storage operations unless a later
   phase introduces narrower per-call replay annotations.
6. On `AutoReconnect`, either trigger authoritative current `normal -> recovery`
   cutover or catch the request up to the already-current epoch, but only if
   the request is still replay-safe and has not already used its one rebind.
7. Treat failure on the authoritative current `recovery` epoch as terminal in
   Phase 2; stale `recovery` -> current catch-up remains allowed when current
   has already advanced.
8. Use Option B breaker semantics: one shared per-LAN breaker object whose
   admission state is tagged to the authoritative current epoch id, so stale
   failures and Tier 1 hits do not poison or heal the new current epoch. That
   breaker must also use a true single-probe `HALF_OPEN` window under
   concurrency.
9. Materialize cursor-producing operations fully inside
   `run_with_request_lease(...)` so no MongoDB work escapes the retry
   boundary after the helper returns.
10. Keep the terminal `ACTIVE -> FAILED` outcome explicit so later optional
   controller follow-up has a clean trigger boundary.

**Verification:**

1. First-bind admission and leased epoch selection always refer to the same
   authoritative current epoch id.
2. A read-only request can trigger one authoritative `normal -> recovery`
   cutover or stale-epoch catch-up and continue.
3. Rebind classification cannot terminal-fail a request as authoritative
   current `recovery` if the authoritative current epoch has already advanced
   elsewhere before the classify-and-rebind decision point.
4. Fresh requests can be admitted to new current epoch `R1` even if the shared
   breaker had been opened for old current epoch `N0`.
5. Exactly one fresh request is admitted as the `HALF_OPEN` probe for one
   epoch id; concurrent fresh requests for that same epoch remain blocked.
6. A request that already executed an unsafe write, fails on authoritative
   current `recovery`, or has already used its one rebind ends in `FAILED`.
7. Tier 1 hits and stale-epoch outcomes do not by themselves heal or poison
   fresh admission for the authoritative current epoch.
8. No serving-path route still depends on `with timed_db(...) as db:` as the
   normal app-facing contract.

### Phase 3 - Observability and Documentation

**Status:** Implemented in
[app.py](../../../../../source/docker/edge_server/source/app.py)
and
[telemetry.py](../../../../../source/docker/edge_server/source/telemetry.py).

**Goal:** make the request lease state machine visible in logs, telemetry, and
docs without expanding scope into controller-side avoidance.

**Changes:**

1. Finalize one projected request-lease outcome record per owner LAN near
   response end.
2. Ship those projected records on the existing edge-server per-request
   telemetry frame and emit one final structured log line per lease.
3. Keep those request-level outcomes on the raw edge-server telemetry path;
   aggregated summaries and CSV collectors remain separate follow-on work if
   experiments later need them.
4. Keep
   [implemented_03_mongodb_lease_failed_backend_avoidance_plan.md](./implemented_03_mongodb_lease_failed_backend_avoidance_plan.md)
   as an optional follow-on rather than part of this core plan; controller
   triggers continue to use the separate control-event path.

**Verification:**

1. Fault-injection runs can distinguish healthy completion, one-rebind
   recovery or catch-up completion, and terminal failure from edge-server logs
   and per-request telemetry.
2. The thesis diagrams can map directly to the request-level outcome contract.

### Phase 4 - Optional Replay-Safety Refinement

**Goal:** recover more safely replayable requests without weakening
correctness.

**Scope:** app-side operation wrappers and selected call sites.

**Changes:**

1. Add explicit replay-safety annotations to selected DB operations.
2. Replace the conservative request-wide write gate only where correctness is
   provable.
3. Keep the default behavior fail-safe for unannotated or ambiguous writes.

**Verification:**

1. Replay-safe operations can use the one bounded failure-driven rebind.
2. Unannotated writes still fail conservatively.

## File Map

- [app.py](../../../../../source/docker/edge_server/source/app.py)
   request-lease lifecycle, teardown, linearized admit-and-bind and
   classify-and-rebind decisions, current-epoch-aware breaker admission, and
   terminal outcome tracking.
- [platform_cache.py](../../../../../source/docker/edge_server/source/platform_cache.py)
  request-level mutating-operation tracking and any later replay-safety
  annotations.
- [vip_routing_overview.md](../../vip_routing_overview.md)
  future documentation update once the implementation lands.
- [system_mechanisms.md](../../../system_mechanisms.md)
  future documentation update once the implementation lands.
- [vip_data_recovery_epoch_model.md](../vip_data_recovery_epoch_model.md)
  future documentation update to describe the request-lease layer above the
  implemented epoch baseline.

## Dependencies

1. The implemented LAN-scoped epoch model in
   [vip_data_recovery_epoch_model.md](../vip_data_recovery_epoch_model.md)
   remains the base storage-path lifecycle.
2. The implemented warm/recovery baseline described in
   [01_mongodb_lease_warm_start_and_recovery_path_plan.md](./01_mongodb_lease_warm_start_and_recovery_path_plan.md)
   remains unchanged by this plan.
3. The optional controller-side avoidance follow-up in
   [implemented_03_mongodb_lease_failed_backend_avoidance_plan.md](./implemented_03_mongodb_lease_failed_backend_avoidance_plan.md)
   depends on Phase 1 and Phase 2 of this plan rather than being part of this
   plan.

## Documentation Updates

Once implementation begins, update:

1. [vip_routing_overview.md](../../vip_routing_overview.md)
2. [system_mechanisms.md](../../../system_mechanisms.md)
3. [vip_data_recovery_epoch_model.md](../vip_data_recovery_epoch_model.md)
4. [edge_storage_connection_epoch_visuals.md](../../../other/edge_storage_connection_epoch_visuals.md)

## Rationale

The thesis-friendly claim is not that every MongoDB call re-selects a backend.
It is that storage-path selection happens at lease creation, storage-path
stability is preserved inside the lease, and one LAN-scoped shared authority
owns the concurrent decisions about current epoch changes, breaker admission,
and failure-driven rebinding.

That is the smallest model that matches both MongoDB connection semantics and
the controller's role in storage selection.
