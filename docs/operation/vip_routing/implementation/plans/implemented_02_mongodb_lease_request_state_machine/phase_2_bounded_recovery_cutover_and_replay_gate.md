# Phase 2 - Bounded Rebind And Replay Gate

**Goal:** add explicit request-lease lifecycle and one bounded
failure-driven rebind per owner LAN.

This phase is where the request lease stops being a pure accounting layer and
starts governing failure semantics.

Phase 1 is now implemented in
[app.py](../../../../../../source/docker/edge_server/source/app.py): the edge
server already has a request-local lease registry keyed by LAN, `timed_db(...)`
already reuses that request-owned lease, and request teardown already releases
held epochs once per LAN. This phase should therefore be read as a follow-on
that adds failure semantics on top of that baseline. It is also the point
where the app-facing MongoDB call boundary moves from `with timed_db(...)`
blocks to explicit `run_with_request_lease(...)` calls, not a redesign of the
Phase 1 ownership model itself.

## 1. Why This Phase Exists

With Phase 1 in place, the request already has a stable lease record and a
request-end release path. The remaining hard question is what happens when a
MongoDB operation fails after the request has already bound to a storage path?

The current `timed_db(...)` context manager can rotate the current LAN epoch on
`AutoReconnect`, but by itself it cannot safely replay an arbitrary collection
operation because the operation happens after the context manager yields the DB
handle.

The implemented `timed_db(...)` path also now owns request-visible context
setup that later code still depends on: `_owner_lan` for
`cached_collection(...)`, `g.db_epoch_context` for failure logging, breaker
success and failure accounting, and `T_dados` accumulation. Phase 2 should
therefore factor that seam into a reusable one-shot helper for retryable work
and then move route-level MongoDB call sites onto `run_with_request_lease(...)`
instead of bypassing it or preserving `timed_db(...)` as the main public
serving-path boundary.

That means this phase needs both:

- explicit request-lease lifecycle
- one explicit helper boundary for retryable DB work

## 2. Target State

- each request lease carries lifecycle, replay safety, and one request-local
  rebind allowance
- first bind is one linearized admit-and-bind decision for the authoritative
  current epoch, and it never spends the rebind allowance regardless of
  whether that current epoch is `normal` or `recovery`
- failure handling is linearized through one LAN authority state:
    current `normal` may cut over to `recovery`, stale epochs only catch up, and
    `recovery -> normal` remains housekeeping-driven
- replay-unsafe requests fail instead of silently rebinding
- retryable operations move onto `run_with_request_lease(...)` as the
  app-facing boundary instead of relying on the `timed_db(...)` context
  manager to magically resume work after `yield`
- that retry boundary preserves the lower-level responsibilities already owned
  by `timed_db(...)`: `_owner_lan`, breaker accounting, `g.db_epoch_context`,
  and `T_dados`
- fresh-request admission follows health of the current epoch path through one
  shared per-LAN breaker whose state is tagged to the authoritative current
  epoch id, not a raw LAN-wide memory of any recent failure on older epochs
- breaker success and failure accounting only applies to actual MongoDB I/O
  against the current epoch path; Tier 1 hits and stale-epoch outcomes do
  not reopen or reclose admission by themselves
- results returned from that explicit helper boundary are always fully
  materialized values, never a live `Cursor` or `CommandCursor`, so no
  MongoDB work escapes after the helper returns

## 3. File Map

- [source/docker/edge_server/source/app.py](../../../../../../source/docker/edge_server/source/app.py)
- [source/docker/edge_server/source/platform_cache.py](../../../../../../source/docker/edge_server/source/platform_cache.py)

## 4. Lease Model And Responsibility Split

Phase 2 needs to stop treating one enum as if it simultaneously described the
global LAN epoch, the request lifecycle, and the request's retry rights. Those
are different concerns:

- global LAN epoch lifecycle: one LAN has one authoritative `current` epoch,
    possibly several retiring epochs, request-triggered `normal -> recovery`
    cutover, and housekeeping-driven `recovery -> normal` rollback
- request lease lifecycle: for one `(request, owner_lan)`, the lease is either
    absent, `ACTIVE`, `FAILED`, or `COMPLETED`
- request-local rebind policy: after `AutoReconnect`, the request may consume
    at most one rebind to adopt a different epoch

`UNBOUND` therefore remains conceptual absence from the request-local registry.
Once the lease object exists, its lifecycle starts as `ACTIVE` regardless of
whether the current epoch is `normal` or `recovery`. The mode of the storage
path the request is currently using is derived from `lease.epoch.mode`; it does
not need a second request-lifecycle enum value.

In practice this means:

- first bind on a current `recovery` epoch is still just admission, not a
  consumed rebind
- the request only consumes its one rebind after an actual `AutoReconnect`
  and successful adoption of a different epoch
- if the request later rebinds from stale `recovery` to already-current
  `normal`, that is a request-local catch-up, not a global rollback

Extend the lease record in [app.py](../../../../../../source/docker/edge_server/source/app.py):

```python
class RequestLeaseLifecycle(Enum):
    ACTIVE = auto()
    FAILED = auto()
    COMPLETED = auto()


@dataclass
class RequestLease:
    lan: str
    epoch: _MongoEpoch
    first_bound_at: float
    lifecycle: RequestLeaseLifecycle = RequestLeaseLifecycle.ACTIVE
    replay_safe: bool = True
    rebinds_used: int = 0
    terminal_reason: str | None = None
```

Phase 2 should update the Phase 1 request-binding helper to construct the
lease inline at first bind. The initial lease record is mode-agnostic except
for the epoch reference it holds, so a dedicated constructor helper is not
required unless later phases add real initialization logic that must stay
centralized.

## 5. Replay-Safety Source Of Truth

Phase 2 should keep a single source of truth for replay safety on the
request-owned lease itself. It should not introduce a second request-local
`g.db_replay_unsafe_lans` structure in parallel with `lease.replay_safe`.

Recommended lease update pattern:

```python
lease = _get_or_bind_request_lease(lan)
lease.replay_safe = lease.replay_safe and replay_safe
```

This flag is sticky for the life of the request-owned lease. Once one
operation marks the lease replay-unsafe, later operations in the same request
do not restore retry eligibility.

The `replay_safe` input should come from the explicit operation boundary used
by `run_with_request_lease(...)`. `platform_cache.py` can continue to own
operation counting and Tier 1 read short-circuiting, but it should not become
a second owner of request-failure state in this phase.

Replay safety answers only one question: may this request safely retry after a
later `AutoReconnect`? It does not describe LAN health. The currently exercised
serving workload is read-only, so the normal `sensor_reports` and
`device_registry` reads can enter `run_with_request_lease(...)` as
`replay_safe=True`. The conservative failure branch stays in the plan for
future owner-LAN writes or ambiguous control-path operations. Tier 1
selective-sync still only short-circuits point reads, and local support-state
writes remain outside this lease model.

Recommended route-level usage:

```python
run_with_request_lease(
    device_lan,
    op_name="sensor_reports.find_one",
    replay_safe=True,
    fn=lambda db: cached_collection(db, "sensor_reports").find_one({"_id": device_id}),
)
```

Read-only operations remain replay-safe by default unless a later phase adds a
stricter policy for a specific call boundary.

## 6. Single-Authority Bind And Rebind Decisions

The earlier Phase 2 draft still split first bind and rebind into separate
steps. That is the race this revision removes. For one LAN,
`_LanEpochState` is the shared authority for:

- authoritative current epoch selection
- fresh-request admission for that current epoch
- current-versus-stale classification after `AutoReconnect`
- request adoption of the replacement epoch
- epoch-tagged breaker state that gates fresh admission

So the Phase 1 helper should stop doing "check admission first, bind later"
and instead do one atomic admit-and-bind step.

That helper should preserve the current cold-start behavior from Phase 1: if a
LAN has not leased any epoch yet, first bind should lazily initialize the first
authoritative `normal` epoch while the LAN lock is already held rather than
failing just because `state.current` was still empty.

Recommended helper update in [app.py](../../../../../../source/docker/edge_server/source/app.py):

```python
def _bind_new_request_lease(lan: str) -> RequestLease:
    registry = _get_request_lease_registry()
    state = _get_lan_epoch_state(lan)
    breaker = _get_or_create_breaker(lan)

    with state.lifecycle_lock:
        current = state.current
        if current is None:
            vip_ip = state.normal_vip_ip
            if vip_ip is None:
                raise StorageVipConfigurationError(
                    f"missing normal VIP mapping for {lan}"
                )
            current = _new_epoch_locked(
                state,
                mode="normal",
                vip_ip=vip_ip,
            )
            state.current = current
        if not breaker.check_locked(current.epoch_id):
            raise CircuitOpenError(
                f"circuit open for {lan} epoch={current.epoch_id}"
            )

        now = time.monotonic()
        current.lease_count += 1
        if current.first_lease_at is None:
            current.first_lease_at = now
        lease = RequestLease(
            lan=lan,
            epoch=current,
            first_bound_at=now,
        )
        registry[lan] = lease
        return lease


def _get_or_bind_request_lease(lan: str) -> RequestLease:
    registry = _get_request_lease_registry()
    lease = registry.get(lan)
    if lease is not None:
        return lease
    return _bind_new_request_lease(lan)
```

The important property is that breaker admission, current-epoch selection,
lease-count increment, and lease creation all refer to the same authoritative
current epoch while one LAN lock is held.

Recommended helper in [app.py](../../../../../../source/docker/edge_server/source/app.py):

```python
def _rebind_request_lease_after_autoreconnect(lease: RequestLease) -> _MongoEpoch:
    if lease.rebinds_used >= 1 or not lease.replay_safe:
        lease.lifecycle = RequestLeaseLifecycle.FAILED
        lease.terminal_reason = "rebind_not_allowed"
        raise AutoReconnect("request lease cannot rebind again")

    state = _get_lan_epoch_state(lease.lan)
    failed_epoch = lease.epoch
    with state.lifecycle_lock:
        current_epoch = state.current
        if current_epoch is None:
            raise RuntimeError(f"no current epoch for {lease.lan}")

        if current_epoch.epoch_id == failed_epoch.epoch_id:
            if failed_epoch.mode != "normal":
                lease.lifecycle = RequestLeaseLifecycle.FAILED
                lease.terminal_reason = "current_recovery_epoch_failed"
                raise AutoReconnect("current recovery epoch cannot rebind again")

            next_vip_ip = _snapshot_vip_ip_for_epoch(lease.lan, mode="recovery")
            adopted_epoch = _rotate_epoch_if_current_locked(
                state,
                expected_epoch_id=failed_epoch.epoch_id,
                reason="request_lease_auto_reconnect",
                next_mode="recovery",
                next_vip_ip=next_vip_ip,
            )
        else:
            adopted_epoch = current_epoch

        if adopted_epoch.epoch_id == failed_epoch.epoch_id:
            raise RuntimeError("rebind helper must adopt a different epoch")

        adopted_epoch.lease_count += 1
        if adopted_epoch.first_lease_at is None:
            adopted_epoch.first_lease_at = time.monotonic()
        lease.epoch = adopted_epoch
        lease.rebinds_used += 1

    _release_epoch(lease.lan, failed_epoch)
    return adopted_epoch
```

The key rule is that `_rotate_epoch_if_current(...)` should not run after a
separate unlocked current-epoch snapshot. Phase 2 should either add
`_rotate_epoch_if_current_locked(...)` or factor the compare-and-swap body so
the LAN-authority helper both classifies the failure and, when allowed,
mutates the authoritative current epoch before returning the adopted epoch.

If the request failed on a stale epoch, it must not mutate global LAN state at
all. It should only adopt the already-current epoch and release its stale one.
That stale-epoch catch-up can land on either `normal` or `recovery`, depending
on what the LAN has already decided is authoritative.

So the helper has only three cases:

- failed epoch is current `normal`: request may trigger the shared
  `normal -> recovery` cutover and then adopt the new current epoch
- failed epoch is stale: request may adopt the already-current epoch without
  mutating LAN state
- failed epoch is current `recovery`: request is terminal, because
  `recovery -> normal` remains housekeeping-driven and Phase 2 does not allow
  a second request-triggered cutover from recovery

The rebind allowance is request-local and bounded. First bind does not consume
it, regardless of initial epoch mode. Only a successful adoption of a
different epoch after `AutoReconnect` increments `rebinds_used`.

The sketch deliberately reuses `_get_lan_epoch_state(...)` and
`state.lifecycle_lock` instead of introducing another current-epoch accessor.

## 7. Explicit Retry Boundary Extracted From The `timed_db(...)` Seam

Because `timed_db(...)` yields the DB handle before the actual collection call,
bounded recovery needs a helper that owns one retry boundary explicitly.

That helper should reuse the lower-level seam that `timed_db(...)` already
implements today. Phase 2 should not leave two copies of owner-LAN setup,
epoch-context snapshotting, breaker accounting, and `T_dados` accumulation in
the codebase. In practice: factor the current `timed_db(...)` body into one
reusable helper, migrate route-level MongoDB work to
`run_with_request_lease(...)`, and demote `timed_db(...)` from the main
app-facing surface.

The first-bind admission rule also needs to become current-epoch aware. Phase 2
should not preserve a separate "check breaker first, then bind later" step
because that blocks new requests even after the LAN has already cut over to a
shared recovery epoch and also reintroduces an avoidable race. Instead:

- fresh requests should be admitted to the current recovery epoch even if the
    previous current normal epoch opened admission for that LAN
- only failures observed on the current epoch path should open admission for
    future first binds
- only actual MongoDB I/O against the current epoch path should close
    admission again; Tier 1 hits and stale-epoch successes should not do it

Phase 2 should therefore adopt Option B explicitly, with one extra rule: the
breaker is not a second coordination authority. It stays shared per LAN, its
state is tagged to the epoch id it evaluates, and the admission checks that
matter for fresh binding should run while the LAN lock is already held. That
way an `OPEN` state only blocks fresh requests for the same authoritative
current epoch id, and `HALF_OPEN` really means one probe for that epoch.

Recommended breaker contract in [app.py](../../../../../../source/docker/edge_server/source/app.py):

```python
class _CircuitBreaker:
    def __init__(self):
        self.state = _CircuitState.CLOSED
        self._epoch_id: int | None = None
        self._opened_at: float = 0.0
        self._half_open_probe_inflight = False

    def _adopt_epoch_locked(self, epoch_id: int) -> None:
        if self._epoch_id == epoch_id:
            return
        self._epoch_id = epoch_id
        self.state = _CircuitState.CLOSED
        self._opened_at = 0.0
        self._half_open_probe_inflight = False

    def check_locked(self, epoch_id: int) -> bool:
        self._adopt_epoch_locked(epoch_id)
        if self.state is _CircuitState.CLOSED:
            return True
        if self.state is _CircuitState.OPEN:
            if time.monotonic() - self._opened_at < CIRCUIT_COOLDOWN_S:
                return False
            self.state = _CircuitState.HALF_OPEN
        if self.state is _CircuitState.HALF_OPEN:
            if self._half_open_probe_inflight:
                return False
            self._half_open_probe_inflight = True
            return True
        return False

    def record_success_locked(self, epoch_id: int) -> None:
        self._adopt_epoch_locked(epoch_id)
        self.state = _CircuitState.CLOSED
        self._half_open_probe_inflight = False

    def record_failure_locked(self, epoch_id: int) -> None:
        self._adopt_epoch_locked(epoch_id)
        self.state = _CircuitState.OPEN
        self._opened_at = time.monotonic()
        self._half_open_probe_inflight = False
```

This keeps one shared breaker object per LAN, but changes what it means.
Failures on stale epoch `N0` do not block fresh admission to new current epoch
`R1`. Failures on authoritative current `R1` do. Requests that already hold a
lease keep that lease; the breaker still gates only fresh admission.

Recommended helper shape, including current-epoch-aware breaker accounting and
cursor-result enforcement:

```python
from pymongo.command_cursor import CommandCursor
from pymongo.cursor import Cursor


T = TypeVar("T")


def _ensure_materialized_result(op_name: str, result: T) -> T:
    if isinstance(result, (Cursor, CommandCursor)):
        raise TypeError(
            f"{op_name} returned a live cursor; materialize it inside run_with_request_lease(...)"
        )
    return result


def _record_breaker_outcome_if_authoritative(
    lan: str,
    epoch: _MongoEpoch,
    *,
    outcome: Literal["success", "failure"],
    used_epoch_client: bool = True,
) -> None:
    if outcome == "success" and not used_epoch_client:
        return

    state = _get_lan_epoch_state(lan)
    breaker = _get_or_create_breaker(lan)
    with state.lifecycle_lock:
        current = state.current
        if current is None or current.epoch_id != epoch.epoch_id:
            return
        if outcome == "success":
            breaker.record_success_locked(epoch.epoch_id)
        else:
            breaker.record_failure_locked(epoch.epoch_id)


def _run_db_op_once(
    lan: str,
    lease: RequestLease,
    op_name: str,
    fn: Callable[[Any], T],
) -> T:
    g.db_last_lan = lan
    owner_token = _owner_lan.set(lan)
    t0 = time.monotonic()
    try:
        epoch = lease.epoch
        g.db_epoch_context = _snapshot_epoch(epoch)
        g.db_used_epoch_client = False
        client = _get_or_create_epoch_client(lan, epoch)
        result = fn(client[DB_NAME])
        result = _ensure_materialized_result(op_name, result)
        _record_breaker_outcome_if_authoritative(
            lan,
            epoch,
            outcome="success",
            used_epoch_client=getattr(g, "db_used_epoch_client", False),
        )
        return result
    except AutoReconnect:
        _record_breaker_outcome_if_authoritative(lan, epoch, outcome="failure")
        raise
    finally:
        _owner_lan.reset(owner_token)
        _accumulate_tdados(lan, time.monotonic() - t0)


def run_with_request_lease(
    lan: str,
    *,
    op_name: str,
    replay_safe: bool,
    fn: Callable[[Any], T],
) -> T:
    registry = _get_request_lease_registry()
    lease = registry.get(lan)
    if lease is not None and lease.lifecycle == RequestLeaseLifecycle.FAILED:
        raise PyMongoError(f"request lease already failed for {lan}")
    if lease is not None and lease.lifecycle == RequestLeaseLifecycle.COMPLETED:
        raise PyMongoError(f"request lease already completed for {lan}")

    lease = lease or _get_or_bind_request_lease(lan)
    lease.replay_safe = lease.replay_safe and replay_safe

    attempts = 0
    while True:
        attempts += 1
        try:
            return _run_db_op_once(lan, lease, op_name, fn)
        except AutoReconnect:
            if attempts > 1 or lease.rebinds_used >= 1 or not lease.replay_safe:
                lease.lifecycle = RequestLeaseLifecycle.FAILED
                lease.terminal_reason = f"{op_name}:terminal_recovery_failure"
                raise
            _rebind_request_lease_after_autoreconnect(lease)
```

Because `platform_cache.py` currently returns live cursors from `find(...)`
and `aggregate(...)`, Phase 2 should enforce materialization at the helper
boundary instead of leaving it to caller discipline. `platform_cache.py` should
also mark when the request actually used the bound epoch client: Tier 1 hits
leave `g.db_used_epoch_client=False`, while fall-through calls to the VIP-backed
collection set it to `True` before I/O.

That marker is part of the retry-boundary contract, not just a convenience for
`platform_cache.py`. Serving-path callbacks should either go through
`cached_collection(...)` or set `g.db_used_epoch_client=True` before any raw
VIP-backed `db[...]` or `db.command(...)` I/O. Otherwise a successful
authoritative `HALF_OPEN` probe could perform real MongoDB work without closing
admission for that epoch.

Recommended `platform_cache.py` pattern:

```python
def _mark_epoch_client_used() -> None:
    try:
        g.db_used_epoch_client = True
    except RuntimeError:
        pass


def find_one(self, filter=None, *args, **kwargs):
    self._record_op("find_one")
    doc_id = _extract_doc_id(filter)
    self._record_access(doc_id)
    hit = self._try_tier1(filter)
    self._record_tier1_attempt(...)
    if hit is not None:
        return hit
    _mark_epoch_client_used()
    return self._coll.find_one(filter, *args, **kwargs)


def find(self, filter=None, *args, **kwargs):
    self._record_op("find")
    _mark_epoch_client_used()
    return self._coll.find(filter, *args, **kwargs)


def aggregate(self, pipeline, *args, **kwargs):
    self._record_op("aggregate")
    _mark_epoch_client_used()
    return self._coll.aggregate(pipeline, *args, **kwargs)
```

The helper may still return any already-materialized shape the route needs,
such as one document, a list, or another eager value. The only forbidden
return shapes are lazy cursor objects whose database work would continue after
the helper has already reset request context and closed the retry boundary.

`FAILED` is therefore a real terminal lifecycle in Phase 2: once a
request-owned lease reaches it, later work for the same owner LAN in the same
request fails immediately instead of silently trying again.

`COMPLETED` is entered during request teardown when the request releases its
held epochs.

Recommended teardown-state finalization:

```python
@app.teardown_request
def _release_request_leases(_exc: BaseException | None) -> None:
    registry = getattr(g, "db_request_leases", None)
    if not registry:
        return

    for lease in registry.values():
        if lease.lifecycle != RequestLeaseLifecycle.FAILED:
            lease.lifecycle = RequestLeaseLifecycle.COMPLETED
        _release_epoch(lease.lan, lease.epoch)
    registry.clear()
```

Once this phase lands, `run_with_request_lease(...)` becomes the normal
serving-path contract for owner-LAN MongoDB work.

## 8. Route-Level Example

Read-only point lookup:

```python
doc = run_with_request_lease(
    device_lan,
    op_name="sensor_reports.find_one",
    replay_safe=True,
    fn=lambda db: cached_collection(db, "sensor_reports").find_one({"_id": device_id}),
)
```

Second owner-LAN read in the same request:

```python
registry = run_with_request_lease(
    node_lan,
    op_name="device_registry.find_one",
    replay_safe=True,
    fn=lambda db: cached_collection(db, "device_registry").find_one(
        {"_id": node_id},
        {"alert_config.threshold_override": 1},
    ),
)
```

Cursor-producing work must also stay inside the helper boundary. The helper
should reject a callback that returns a live cursor, so cursor-producing call
sites need to materialize to a concrete result before returning:

```python
devices = run_with_request_lease(
    lan,
    op_name="sensor_reports.find.dashboard",
    replay_safe=True,
    fn=lambda db: list(
        cached_collection(db, "sensor_reports").find(
            {"tags": {"$in": subscribed_tags}},
            {
                "_id": 1,
                "device_type": 1,
                "tags": 1,
                "payload": 1,
                "metadata": 1,
                "region_origin": 1,
                "last_updated": 1,
            },
        )
    ),
)
```

Local support-state writes committed after the response do not use
`run_with_request_lease(...)` at all because they do not traverse the owner-LAN
Mongo storage path.

This is more explicit than the current `with timed_db(...)` path because the
retry and rebind boundary becomes app-facing instead of staying implicit inside
a context manager that already yielded the DB handle.

## 9. Verification

1. A request first admitted while the current LAN epoch is already `recovery`
    starts as `ACTIVE` with `rebinds_used=0`, and that admission and lease bind
    refer to the same authoritative current epoch id.
2. A read-only request that fails on the current `normal` epoch can trigger one
    shared `normal -> recovery` cutover, adopt the new current epoch, and
    complete.
3. A request that fails on a stale epoch catches up to the already-current
    epoch without mutating global LAN state, including stale `recovery` ->
    current `normal` catch-up after housekeeping rollback.
4. A request that fails on the authoritative current `recovery` epoch is
    terminal in Phase 2.
5. A write or otherwise replay-unsafe request fails after `AutoReconnect`, and
    replay safety stays sticky for the rest of that request-owned lease.
6. `FAILED` leases cannot be reused later in the same request, and non-failed
    leases are finalized as `COMPLETED` during teardown.
7. When authoritative current changes from failed `normal` epoch `N0` to new
    `recovery` epoch `R1`, fresh requests are admitted against `R1` even if the
    breaker had previously opened for `N0`.
8. When authoritative current `R1` later fails, the breaker opens for `R1`
    itself, and after cooldown exactly one fresh request becomes the
    `HALF_OPEN` probe for that epoch.
9. Tier 1 hits, stale-epoch successes, and stale-epoch failures do not by
    themselves heal or poison fresh-request admission for the authoritative
    current epoch.
10. The retry path preserves `_owner_lan`, current-epoch-aware breaker
     accounting, `g.db_epoch_context`, and `T_dados`, rejects live cursor
     leakage, and replaces `with timed_db(...) as db:` as the normal serving-path
     contract for owner-LAN MongoDB work.
