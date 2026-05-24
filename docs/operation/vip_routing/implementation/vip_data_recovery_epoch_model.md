# VIP_DATA Recovery Epoch Model

**Status:** Implemented  
**Primary file:** [source/docker/edge_server/source/app.py](../../../../source/docker/edge_server/source/app.py)

Reference background:

- [vip_data_recovery_vip_arming_plan.md](../../archive/vip_routing/implementation/vip_data_recovery_vip_arming_plan.md)
- [edge_storage_connection_hard_failure_epoch_plan.md](../../other/edge_storage_connection_hard_failure_epoch_plan.md)
- [edge_storage_connection_epoch_visuals.md](../../other/edge_storage_connection_epoch_visuals.md)

## Objective

Keep the controller-side recovery VIP flow narrow, but move the edge-server
MongoDB lifecycle away from the older one-shot recovery-client model.

The implemented design treats **epoch** as the LAN-scoped unit of
request-visible storage state. An epoch owns:

- the bound VIP path (`VIP_DATA_*` or `VIP_DATA_RECOVERY_*`)
- the lazy `MongoClient`
- the recovery mode
- lease counts and retirement bookkeeping
- bounded recovery expiry once a recovery client is first materialized

This document supersedes the earlier Phase 3 description that reused one
recovered singleton client for a bounded session and suppressed `T_dados`
retirement only during that session.

## Implemented Model

### 1. Fixed Startup-Defined LAN Registry

[source/docker/edge_server/source/app.py](../../../../source/docker/edge_server/source/app.py)
seeds `_epoch_states` during module initialization, before telemetry startup
and before the housekeeping thread begins.

Startup requires matching LAN sets between normal and recovery VIP maps:

- every supported LAN must have a normal VIP mapping
- every supported LAN must have a recovery VIP mapping
- mismatched or missing LAN sets raise `StorageVipConfigurationError`

This makes the runtime LAN registry explicit and prevents lazy runtime creation
of missing LAN state.

### 2. Request-Owned Epoch Leasing

`timed_db(lan)` is now the boundary that binds one request-local lease per
owner LAN and points that lease at the current epoch.

Request flow:

1. Resolve the LAN against `_epoch_states`.
2. Look up an existing request-local lease for that LAN on the current Flask
   request.
3. If no lease exists yet, check the per-LAN circuit breaker and lease the
   current epoch once for that request-owned record.
4. Record `g.db_epoch_context` from the bound epoch immediately.
5. Lazily create that epoch's `MongoClient` if needed.
6. Yield the database handle. Repeated `timed_db(lan)` blocks in the same
   request reuse the same request lease and same epoch.
7. Release all held epoch leases once during request teardown, not on each
   `timed_db(...)` exit.

An OPEN shared breaker therefore blocks first acquisition of a new request
lease, but it does not by itself revoke reuse of a lease the current request
already holds.

The request keeps using the leased epoch even if a newer epoch becomes current
later. This is the key handoff guarantee for overlapping failures and
`/vip_data` updates.

### 3. Failure Rotation and VIP Update Cutover

`AutoReconnect` no longer arms a one-shot recovery client. Instead it performs
a compare-and-swap epoch rotation:

- if the failed epoch is still current, it becomes retiring
- a new current recovery epoch is created with the LAN's recovery VIP bound
- if another request already advanced the epoch, the rotation is skipped

`PUT /vip_data` follows the same epoch ownership model:

- the payload is validated up front
- malformed payloads return JSON `400`
- unknown LANs return JSON `400`
- a changed normal VIP replaces the LAN's current epoch under that LAN's lock

An already leased old epoch keeps its original VIP path; only newly admitted
requests move onto the replacement epoch.

### 4. Recovery Rollback and Housekeeping

Recovery rollback is now owned by a dedicated background housekeeping thread.

The housekeeping loop performs two jobs:

1. Roll a current recovery epoch back to a normal epoch when its bounded local
   recovery window expires.
2. Close retiring epochs only after their lease count reaches zero.

Important details:

- the recovery window starts when the recovery `MongoClient` is first
  materialized, which is the first locally observable recovery reconnect
  attempt for this process
- overdue drain deadlines produce warnings, not forced closure of epochs with
  active leases
- `StorageVipConfigurationError` is logged per affected LAN and does not stop
  housekeeping for other LANs
- unexpected housekeeping exceptions are logged and the loop continues

### 5. Circuit Breaker and `T_dados`

Each LAN now owns exactly one circuit breaker inside its `_LanEpochState`.
Concurrent requests for the same LAN therefore observe one shared OPEN,
HALF_OPEN, or CLOSED state.

`T_dados` remains request-scoped telemetry, but it is now observation-only:

- the after-request hook logs threshold breaches per LAN
- it does not rotate epochs
- it does not retire clients
- it does not suppress or extend recovery lifecycle

Recovery lifecycle is owned by epoch state and housekeeping, not by request-end
timing heuristics.

## Controller Interaction

The controller-side recovery behavior remains the same in principle:

- `VIP_DATA_RECOVERY_*` remains a separate VIP identity
- recovery PacketIn handling remains narrow to the MongoDB TCP connection
- the controller still selects the backend using its existing storage logic
- the controller now remembers the last normal `VIP_DATA` backend per `(edge_server_mac, domain)` as controller-local attribution only
- recovery `VIP_DATA_RECOVERY_*` selection excludes that remembered normal backend when another candidate exists, then falls back to the full pool if exclusion would empty it
- local storage removal clears remembered attribution entries that still point at the removed backend, while remembered peer backends remain safe through pool-membership fallback if they disappear from topology

What changed is the meaning of a recovery reconnect at the edge server. The
edge server now rotates onto a new local epoch and new local client object
instead of arming one special next client creation on a shared singleton.

This design still keeps controller scope narrow. The exclusion filter activates
only when the edge targets `VIP_DATA_RECOVERY_*`, and it does not add request
IDs, retry budgets, or repeated recovery-to-recovery hopping. A fresh normal
or recovery epoch still creates a fresh local connection attempt using its
bound VIP, and failure of the authoritative current recovery epoch remains
request-terminal at the edge.

## Rationale

Epoch started as a blast-radius reduction mechanism for the old shared-client
model, but the runtime only stays coherent if the same LAN-scoped abstraction
also owns:

- request attribution
- bound VIP-path snapshots
- bounded recovery lifecycle
- `/vip_data` validation and cutover
- breaker installation
- retirement and cleanup concurrency

That is why the final implementation treats epoch, not the raw `MongoClient`,
as the unit of storage state over time.

## File Map

- [source/docker/edge_server/source/app.py](../../../../source/docker/edge_server/source/app.py)
  owns LAN-scoped epoch state, breaker installation, request leasing,
  `/vip_data` validation, and housekeeping.
- [source/sdn_controller/vip_routing.py](../../../../source/sdn_controller/vip_routing.py)
  continues to own controller-side VIP handling, including narrow recovery VIP
  flow installation.
- [vip_routing_overview.md](../vip_routing_overview.md)
  explains the request-visible storage path boundary and the controller-facing
  recovery behavior.
- [system_mechanisms.md](../../system_mechanisms.md)
  explains the architectural assumptions and request lifecycle consequences.

## Verification Focus

Validate the implemented model with focused checks:

1. Overlapping `AutoReconnect` failures on the same old epoch create exactly
   one new current epoch.
2. Recovery mode requires a startup-resolved recovery VIP for every supported
   LAN.
3. `T_dados` threshold breaches are logged but do not force reconnection.
4. Request failure logs report the leased epoch even when a newer epoch is
   already current.
5. `PUT /vip_data` rejects malformed payloads and unknown LANs before state
   mutation.
6. An already leased old epoch keeps its original VIP after a normal VIP
   update, while newer requests use the replacement epoch.
7. Recovery rollback continues to run even if one LAN hits
   `StorageVipConfigurationError`.
8. Retiring epochs are closed only after their leases drain.
9. Concurrent requests for the same LAN share one installed circuit breaker.

## Related Notes

- [vip_data_recovery_vip_arming_plan.md](../../archive/vip_routing/implementation/vip_data_recovery_vip_arming_plan.md)
  remains useful background for the controller-facing recovery VIP identity and
  narrow-flow behavior.
- [implemented_02_mongodb_lease_request_state_machine_plan.md](./plans/implemented_02_mongodb_lease_request_state_machine_plan.md)
   and [implemented_02_mongodb_lease_request_state_machine/README.md](./plans/implemented_02_mongodb_lease_request_state_machine/README.md)
   retain the phased implementation record for the now-implemented request
   lease baseline; only the optional replay-safety refinement in Phase 4
   remains open.
- [implemented_03_mongodb_lease_failed_backend_avoidance_plan.md](./plans/implemented_03_mongodb_lease_failed_backend_avoidance_plan.md)
   and [implemented_03_mongodb_lease_failed_backend_avoidance/README.md](./plans/implemented_03_mongodb_lease_failed_backend_avoidance/README.md)
   retain the phased implementation record for the landed controller-side
   recovery-only avoidance behavior.
- [edge_storage_connection_epoch_visuals.md](../../other/edge_storage_connection_epoch_visuals.md)
  provides diagrams for the request lease, failure rotation, and housekeeping
  flows.

