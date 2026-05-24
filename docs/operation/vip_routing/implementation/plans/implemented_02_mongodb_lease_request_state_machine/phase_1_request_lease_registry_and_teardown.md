# Phase 1 - Request Lease Registry And Teardown

**Status:** Implemented in
[source/docker/edge_server/source/app.py](../../../../../../source/docker/edge_server/source/app.py)

**Goal:** replace per-`timed_db(...)` release with one request-owned storage
lease per owner LAN.

This phase is intentionally local to the edge server. It does not yet add the
bounded recovery cutover logic or the later single-authority first-bind
hardening. It only establishes request ownership.

## 1. Why This Phase Exists

Before Phase 1, [app.py](../../../../../../source/docker/edge_server/source/app.py)
leased the current epoch on every `timed_db(lan)` entry and released it again
in the `finally` block. That made repeated DB blocks inside one HTTP request
look like repeated independent storage checkouts even when the request was
conceptually still using the same storage path.

Phase 1 changes the ownership boundary from "per `timed_db(...)` block" to
"per request and owner LAN."

## 2. Target State

- the first DB access for `(request_id, owner_lan)` binds one request lease
- later DB accesses for the same owner LAN reuse that same bound epoch
- the request releases all held leases once, during request teardown
- the current route call sites can keep using `with timed_db(lan) as db:`
  during this phase

In this phase, the concrete request-local registry is keyed only by
`owner_lan`. The `request_id` part is implicit in the current Flask request
context. The bound path's `normal` versus `recovery` mode is derived from
`lease.epoch.mode`, and later phases may add request-lifecycle fields on that
same record without introducing a second registry key.

Phase 1 is therefore only the ownership baseline. It does not try to make the
first-bind admission path fully linearized under one LAN authority lock; that
hardening is deferred to Phase 2.

## 3. File Map

- [source/docker/edge_server/source/app.py](../../../../../../source/docker/edge_server/source/app.py)

## 4. Proposed Data Structures

Add a request-local lease record in [app.py](../../../../../../source/docker/edge_server/source/app.py):

```python
@dataclass
class RequestLease:
    lan: str
    epoch: _MongoEpoch
    first_bound_at: float
```

Request-local registry helper:

```python
def _get_request_lease_registry() -> dict[str, RequestLease]:
    registry = getattr(g, "db_request_leases", None)
    if registry is None:
        registry = {}
        g.db_request_leases = registry
    return registry
```

## 5. Binding Helper - Implemented Phase 1 Baseline

Phase 1 should add a helper that binds once per owner LAN per request:

```python
def _get_or_bind_request_lease(lan: str) -> RequestLease:
    registry = _get_request_lease_registry()
    lease = registry.get(lan)
    if lease is not None:
        return lease

    epoch = _lease_current_epoch(lan)
    lease = RequestLease(
        lan=lan,
        epoch=epoch,
        first_bound_at=time.monotonic(),
    )
    registry[lan] = lease
    return lease
```

This is the key semantic shift: `_lease_current_epoch(lan)` is now called once
per request lease, not once per DB block.

This helper is the implemented Phase 1 baseline, not the final first-bind
shape. It establishes one request-owned lease per LAN, but it does not yet
linearize breaker admission and current-epoch selection under the same LAN
lock. Phase 2 replaces that first-bind path with one atomic admit-and-bind
helper.

## 6. `timed_db(...)` Integration - Implemented Phase 1 Baseline

Recommended `timed_db(...)` shape after Phase 1:

```python
@contextmanager
def timed_db(lan: str):
    g.db_last_lan = lan
    registry = _get_request_lease_registry()
    lease = registry.get(lan)
    breaker = _get_or_create_breaker(lan)
    if lease is None and not breaker.check():
        raise CircuitOpenError(f"circuit open for {lan}")

    owner_token = _owner_lan.set(lan)
    t0 = time.monotonic()
    try:
        lease = lease or _get_or_bind_request_lease(lan)
        epoch = lease.epoch
        g.db_epoch_context = _snapshot_epoch(epoch)
        try:
            client = _get_or_create_epoch_client(lan, epoch)
            yield client[DB_NAME]
            breaker.record_success()
        except AutoReconnect:
            breaker.record_failure()
            next_vip_ip = _snapshot_vip_ip_for_epoch(lan, mode="recovery")
            _rotate_epoch_if_current(
                lan,
                expected_epoch_id=epoch.epoch_id,
                reason="auto_reconnect",
                next_mode="recovery",
                next_vip_ip=next_vip_ip,
            )
            log.warning(
                "timed_db: rotated epoch for %s after connection failure on epoch=%s",
                lan,
                epoch.epoch_id,
            )
            raise
    finally:
        _owner_lan.reset(owner_token)
        _accumulate_tdados(lan, time.monotonic() - t0)
```

The important removal is the old per-call `_release_epoch(lan, epoch)` in the
`finally` block. Release moves to request teardown.

This is intentionally still a split first-bind path: `breaker.check()` runs
before `_get_or_bind_request_lease(lan)`. That is sufficient for the Phase 1
ownership change, but it is not the final concurrency-safe design. Phase 2
replaces this with one LAN-authority decision that performs admission, current
epoch selection, and lease creation together.

This split path also leaves one logging caveat in the implemented Phase 1
baseline: `g.db_last_lan` moves to the requested LAN before breaker admission,
but `g.db_epoch_context` is only refreshed after a lease is actually bound.
So if one request has already bound `lan1` and later hits a pre-bind failure on
`lan2` (for example an OPEN breaker before `lan2` ever acquires a lease), the
failure log can name `lan2` as the failing LAN while still showing the last
successfully bound request epoch from `lan1`. This document treats that as a
known Phase 1 limitation rather than claiming precise pre-bind cross-LAN epoch
metadata. The current Phase 2 draft does not yet define a dedicated fix for
that logging-context gap.

Phase 1 still keeps the existing breaker-failure recording and current-epoch
rotation on `AutoReconnect`. What changes here is request ownership and final
release timing, not the lower-level epoch-rotation baseline.

The breaker rule is also explicit here: an OPEN shared breaker blocks creation
of a new request lease, but does not by itself revoke reuse of a lease the
current request already holds. If that reused epoch is actually broken, later
phases handle the failure and recovery transition explicitly.

## 7. What Phase 2 Keeps And Replaces

Phase 2 keeps these Phase 1 outcomes:

- one request-local lease registry keyed by LAN
- repeated same-LAN lease reuse inside one request, even after the route-level
    serving boundary moves away from `timed_db(...)`
- one final release at request teardown

Phase 2 replaces these first-bind details:

- separate `breaker.check()` before lease creation
- the direct bind path inside `_get_or_bind_request_lease(...)` as the final
    first-bind shape
- raw breaker admission semantics that are not yet tagged to the authoritative
    current epoch

So this document should be read as the implemented ownership baseline, not as
the final concurrency-hardened design for fresh admission.

## 8. Request Teardown Release

Use request teardown rather than `after_request` so release still happens on
error paths:

```python
@app.teardown_request
def _release_request_leases(_exc: BaseException | None) -> None:
    registry = getattr(g, "db_request_leases", None)
    if not registry:
        return

    for lease in registry.values():
        _release_epoch(lease.lan, lease.epoch)
    registry.clear()
```

This preserves the current epoch bookkeeping while moving the release boundary
to the end of the request.

## 9. Call-Site Consequence

Current route structure can stay unchanged in this phase:

```python
with timed_db(device_lan) as db:
    doc = cached_collection(db, "sensor_reports").find_one({"_id": device_id})

with timed_db(device_lan) as db:
    peer_doc = cached_collection(db, "sensor_reports").find_one(
        {"_id": peer_device_id},
        {"payload": 1, "metadata.alert_threshold": 1},
    )
```

The difference after Phase 1 is not the route syntax. The difference is that
both blocks now reuse one request-owned epoch lease for `device_lan` instead of
leasing and releasing it twice.

Local support-state writes committed to the serving edge buffer are outside
this Mongo lease boundary and do not participate in `timed_db(...)` ownership.

## 10. Verification

1. A request that enters `timed_db(lan1)` multiple times binds one request
    lease and triggers one final `_release_epoch(lan1, epoch)` at teardown on
    the normal path.
2. A request that acquires a lease and then exits through an error path still
    triggers one final `_release_epoch(lan1, epoch)` at teardown.
3. A request that touches `lan1` and `lan2` holds two distinct request leases.
4. A request that never touches MongoDB creates no request lease registry.
5. With no existing lease for `lan1`, an OPEN breaker blocks first acquisition.
6. After a request already holds a lease for `lan1`, later `timed_db(lan1)`
    reuse in that same request is still allowed even if the breaker opens after
    the first bind.
7. If request A has already leased epoch `N0` for `lan1` and request B later
    triggers `AutoReconnect`-driven rotation to new current epoch `R1`, request
    A keeps using its already leased epoch `N0` until teardown, while new
    admissions move to `R1`.
8. In that split state, teardown for request A releases the epoch it actually
    held (`N0`), not the newer current epoch (`R1`).
9. Existing route code keeps working without a large call-site rewrite in this
    phase.
