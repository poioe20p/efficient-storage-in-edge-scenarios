# Implementation Plan - Hard-Failure-First Epoch Rotation

**Status:** Proposed
**Scope:** Edge-server MongoDB client lifecycle for LAN-scoped storage access

This plan assumes a fixed startup-defined LAN set. Every supported LAN must have both a normal VIP and a recovery VIP resolved by startup, whether those values come from fixed defaults or environment configuration. Runtime `PUT /vip_data` requests may update the normal VIP of an existing LAN, but they do not create new LANs or provision missing recovery VIP mappings.
**Primary files:**

- `source/docker/edge_server/source/vip_data_mongo_runtime.py`
- `source/docker/edge_server/source/app.py` (bootstrap and registration order only)

---

## 1. Replace the singleton client model with epoch state

Remove the old single-client and per-LAN recovery runtime structures:

- `_mongo_clients`
- `_retired_clients`
- `recovery_once_per_domain`
- `_arm_recovery_once(lan)`
- `client_mode_per_domain`
- `recovery_session_deadline_per_domain`
- `_snapshot_recovery_lans()`
- `_try_retire_expired_recovery_client(lan)`
- `_get_client_mode(lan)` and any failure logging helpers that still read per-LAN recovery state

Replace them with LAN-scoped epoch state.

Code sketch:

```python
from dataclasses import dataclass, field


class StorageVipConfigurationError(RuntimeError):
    pass


@dataclass
class _MongoEpoch:
    epoch_id: int
    mode: str
    vip_ip: str
    client: MongoClient | None = None
    client_created_at: float | None = None
    first_lease_at: float | None = None
    lease_count: int = 0
    retiring: bool = False
    retire_requested_at: float | None = None
    drain_deadline: float | None = None
    recovery_expires_at: float | None = None


@dataclass
class _LanEpochState:
    lifecycle_lock: threading.Lock = field(default_factory=threading.Lock)
    normal_vip_ip: str | None = None
    recovery_vip_ip: str | None = None
    breaker: "_CircuitBreaker | None" = None
    current: _MongoEpoch | None = None
    retiring: list[_MongoEpoch] = field(default_factory=list)
    next_epoch_id: int = 1


_epoch_states_registry_lock = threading.Lock()
_epoch_states: dict[str, _LanEpochState] = {}


def _seed_epoch_states_from_config() -> None:
    configured_lans = set(vip_data_per_domain)
    recovery_lans = set(vip_data_recovery_per_domain)
    if configured_lans != recovery_lans:
        raise StorageVipConfigurationError(
            "startup VIP configuration requires matching normal and recovery LAN sets"
        )

    seeded: dict[str, _LanEpochState] = {}
    for lan in sorted(configured_lans):
        seeded[lan] = _LanEpochState(
            normal_vip_ip=vip_data_per_domain[lan],
            recovery_vip_ip=vip_data_recovery_per_domain[lan],
        )

    with _epoch_states_registry_lock:
        _epoch_states.clear()
        _epoch_states.update(seeded)
```

Use `epoch.mode` as the only source of truth for recovery lifecycle and for selecting the initial VIP when a new epoch is created. After creation, `epoch.vip_ip` is the source of truth for that epoch's bound backend path. Runtime recovery state, recovery expiry, and the bound path all live only on the epoch object itself.

Call `_seed_epoch_states_from_config()` from the module-level startup path, immediately after the normal and recovery VIP maps are resolved and before starting `_epoch_housekeeping_loop`, before `init_telemetry(...)`, and before any imported app instance can begin background work. Do not defer seeding to `if __name__ == "__main__":`. That makes `_epoch_states` the complete runtime LAN registry for the fixed startup-defined LAN set, avoids lazy gaps for untouched LANs, and fails fast when startup VIP resolution is incomplete.

Use `_epoch_states_registry_lock` only to look up entries in `_epoch_states` after startup seeding. Use each `_LanEpochState.lifecycle_lock` to protect that LAN's epoch lifecycle and LAN-local VIP config: `normal_vip_ip`, `recovery_vip_ip`, `breaker`, `current`, `retiring`, `next_epoch_id`, lease counts, client materialization, recovery expiry, and drain bookkeeping. That keeps epoch transitions atomic without serializing unrelated LANs behind one process-wide lifecycle lock. The legacy shared `vip_data_per_domain` map becomes bootstrap and control-plane input only; runtime request paths, LAN enumeration, and response payloads should snapshot LAN-local VIP state instead of consulting that shared map.

---

## 2. Lease the current epoch and create its client lazily

Requests should lease the current epoch instead of directly fetching a shared `MongoClient`.

Code sketch:

```python
def _snapshot_vip_ip_for_epoch(lan: str, mode: str) -> str:
    state = _get_lan_epoch_state(lan)
    with state.lifecycle_lock:
        if mode == "normal":
            vip_ip = state.normal_vip_ip
            if vip_ip is None:
                raise StorageVipConfigurationError(
                    f"missing normal VIP mapping for {lan}"
                )
            return vip_ip

        if mode == "recovery":
            vip_ip = state.recovery_vip_ip
            if vip_ip is None:
                raise StorageVipConfigurationError(
                    f"missing recovery VIP mapping for {lan}"
                )
            return vip_ip

    raise ValueError(f"unsupported epoch mode: {mode}")


def _get_lan_epoch_state(lan: str) -> _LanEpochState:
    with _epoch_states_registry_lock:
        state = _epoch_states.get(lan)
    if state is None:
        raise StorageVipConfigurationError(f"unknown configured LAN: {lan}")
    return state


def _new_epoch_locked(
    state: _LanEpochState,
    mode: str,
    vip_ip: str,
) -> _MongoEpoch:
    epoch = _MongoEpoch(
        epoch_id=state.next_epoch_id,
        mode=mode,
        vip_ip=vip_ip,
    )
    state.next_epoch_id += 1
    return epoch


def _lease_current_epoch(lan: str) -> _MongoEpoch:
    state = _get_lan_epoch_state(lan)
    with state.lifecycle_lock:
        current = state.current
        if current is not None:
            current.lease_count += 1

            if current.first_lease_at is None:
                current.first_lease_at = time.monotonic()

            return current

    next_vip_ip = _snapshot_vip_ip_for_epoch(lan, mode="normal")

    with state.lifecycle_lock:
        if state.current is None:
            state.current = _new_epoch_locked(
                state,
                mode="normal",
                vip_ip=next_vip_ip,
            )
        epoch = state.current
        epoch.lease_count += 1

        if epoch.first_lease_at is None:
            epoch.first_lease_at = time.monotonic()

        return epoch


def _get_or_create_breaker(lan: str) -> _CircuitBreaker:
    state = _get_lan_epoch_state(lan)
    with state.lifecycle_lock:
        breaker = state.breaker
        if breaker is None:
            breaker = _CircuitBreaker()
            state.breaker = breaker
        return breaker


def _get_or_create_epoch_client(lan: str, epoch: _MongoEpoch) -> MongoClient:
    state = _get_lan_epoch_state(lan)
    with state.lifecycle_lock:
        if epoch.client is not None:
            return epoch.client

        epoch.client = MongoClient(
            f"mongodb://{epoch.vip_ip}:{DB_PORT}/",
            maxPoolSize=1,
            maxIdleTimeMS=MAX_IDLE_MS,
            serverSelectionTimeoutMS=3000,
            socketTimeoutMS=15000,
            directConnection=True,
        )
        epoch.client_created_at = time.monotonic()
        if epoch.mode == "recovery" and epoch.recovery_expires_at is None:
            epoch.recovery_expires_at = (
                epoch.client_created_at + VIP_DATA_RECOVERY_SESSION_MAX_AGE_S
            )
        return epoch.client


def _release_epoch(lan: str, epoch: _MongoEpoch) -> None:
    state = _get_lan_epoch_state(lan)
    with state.lifecycle_lock:
        if epoch.lease_count > 0:
            epoch.lease_count -= 1
```

The recovery expiry window is intentionally an edge-local timer that begins when the recovery `MongoClient` is first materialized, which is the earliest point this process can observe a recovery reconnect attempt. It is a bounded local recovery window, not a claim about the controller's exact TCP-level flow-install timing.

Important behavior:

- the new current epoch exists logically at rotation time
- the actual MongoDB client is created only when the first request leases that epoch
- a recovery epoch starts its bounded recovery window only after its client is first materialized
- VIP selection is LAN-local on `_LanEpochState`, so epoch creation and rotation do not wait on a global VIP lock
- the chosen VIP is bound into the epoch at creation time, so lazy client materialization cannot drift onto a newer global VIP mapping
- normal mode requires a normal VIP and recovery mode requires a recovery VIP; there is no silent fallback from recovery to the normal path
- missing VIP configuration fails as an explicit `StorageVipConfigurationError` instead of leaking a raw `KeyError` during checkout
- unrelated LANs do not serialize behind one global epoch lifecycle lock
- there is no per-LAN recovery hint left behind if a compare-and-swap rotation is skipped

---

## 3. Rotate epochs with compare-and-swap semantics

Rotation must be tied to the specific epoch that failed or was replaced. That prevents two concurrent failures on the same old epoch from creating multiple new current epochs.

The purpose of rotation in this plan is blast-radius reduction at the edge server. It separates newer requests from the old shared MongoDB client state, reduces how much future traffic remains tied to one damaged connection, and makes it easier to move future requests onto a newer connection after failure or VIP change. It is not intended to guarantee controller-side backend avoidance.

Code sketch:

```python
def _rotate_epoch_if_current(
    lan: str,
    expected_epoch_id: int,
    reason: str,
    next_mode: str,
    next_vip_ip: str,
) -> _MongoEpoch:
    state = _get_lan_epoch_state(lan)
    with state.lifecycle_lock:
        current = state.current

        if current is None:
            state.current = _new_epoch_locked(
                state,
                mode=next_mode,
                vip_ip=next_vip_ip,
            )
            log.info("Initialized epoch for %s via %s", lan, reason)
            return state.current

        if current.epoch_id != expected_epoch_id:
            log.info(
                "Skipped epoch rotation for %s via %s; current=%s expected=%s",
                lan,
                reason,
                current.epoch_id,
                expected_epoch_id,
            )
            return current

        now = time.monotonic()
        current.retiring = True
        current.retire_requested_at = now
        current.drain_deadline = now + MONGO_CLIENT_RETIRE_GRACE_S
        state.retiring.append(current)

        state.current = _new_epoch_locked(
            state,
            mode=next_mode,
            vip_ip=next_vip_ip,
        )
        log.info(
            "Rotated epoch for %s via %s: %s -> %s",
            lan,
            reason,
            current.epoch_id,
            state.current.epoch_id,
        )
        return state.current
```

Use this helper for:

- `AutoReconnect`
- recovery-to-normal rollover after a used recovery epoch expires

The important part is that `next_mode` is explicit on the new epoch. If a compare-and-swap rotation is skipped because another request already advanced the current epoch, there is no separate recovery hint left armed for a later unrelated epoch.

A new epoch guarantees a fresh local client object and a new connection attempt using that epoch's bound VIP. It does not guarantee a distinct backend IP. Backend choice remains owned by the controller's existing VIP selection rules, so selecting the same backend again remains possible. The intended benefit is smaller blast radius and cleaner handoff from old requests to newer requests, not forced backend reselection. Previous-backend exclusion, controller memory of failed server-to-storage connections, and flow-rule overrides to avoid a prior backend are out of scope for this plan.

---

## 4. Integrate epoch leasing into `timed_db(lan)`

`timed_db(lan)` must keep the current behavior around breaker checks, `_owner_lan`, and `T_dados` accounting while switching from shared-client lookup to epoch leasing.

Code sketch:

```python
def _snapshot_epoch(epoch: _MongoEpoch | None) -> dict[str, int | str | bool | None]:
    if epoch is None:
        return {
            "epoch_id": None,
            "mode": "unknown",
            "vip_ip": None,
            "retiring": None,
        }
    return {
        "epoch_id": epoch.epoch_id,
        "mode": epoch.mode,
        "vip_ip": epoch.vip_ip,
        "retiring": epoch.retiring,
    }


def _accumulate_tdados(lan: str, elapsed: float) -> None:
    g.time_db_elapsed = getattr(g, "time_db_elapsed", 0.0) + elapsed
    per_lan = getattr(g, "time_db_per_lan", None)
    if per_lan is None:
        per_lan = {}
        g.time_db_per_lan = per_lan
    per_lan[lan] = per_lan.get(lan, 0.0) + elapsed


@contextmanager
def timed_db(lan: str):
    g.db_last_lan = lan
    breaker = _get_or_create_breaker(lan)
    if not breaker.check():
        raise CircuitOpenError(f"circuit open for {lan}")

    owner_token = _owner_lan.set(lan)
    t0 = time.monotonic()
    epoch: _MongoEpoch | None = None

    try:
        epoch = _lease_current_epoch(lan)
        g.db_epoch_context = _snapshot_epoch(epoch)
        try:
            client = _get_or_create_epoch_client(lan, epoch)
            db = client[DB_NAME]
            yield db
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
            raise
    finally:
        if epoch is not None:
            _release_epoch(lan, epoch)
        _owner_lan.reset(owner_token)
        _accumulate_tdados(lan, time.monotonic() - t0)
```

This preserves the existing request-scoped accounting while changing only the client lifecycle model.

The important details are that `AutoReconnect` handling covers both first client materialization and later use of the DB handle for the leased epoch, request-scoped logging can keep the leased epoch snapshot for correct attribution, and cleanup still runs even if checkout fails before a client is materialized.

Breaker semantics still gate admission before any epoch is leased. A newer current epoch can already exist after a VIP update or failure-driven rotation, but only newly admitted requests use it. If the breaker is OPEN, new requests remain blocked until cooldown even though the next current epoch is already prepared.

Implementation note:

- `_get_or_create_breaker(lan)` creates at most one breaker per LAN under that LAN's lifecycle lock, so every request for that LAN observes the same breaker state
- `breaker.check()` remains the admission gate so the plan stays grounded in the current `_CircuitBreaker` API from `app.py`; if the codebase later prefers `allow_request()`, that should be a separate mechanical rename or compatibility wrapper

Breaker state transitions remain owned by the breaker object's own internal lock; `_LanEpochState.lifecycle_lock` is only the installation boundary that prevents duplicate breaker instances for the same LAN.

Add an explicit Flask handler for configuration faults so they stay visible in logs and do not silently collapse into the existing `PyMongoError` → `503` path:

```python
@app.errorhandler(BadRequest)
def _handle_bad_request(exc):
    return jsonify({"error": exc.description}), 400


@app.errorhandler(StorageVipConfigurationError)
def _handle_storage_vip_configuration_error(exc):
    route_name = request.endpoint or request.path or "unknown"
    _log_db_failure(
        route_name,
        exc,
        lan=getattr(g, "db_last_lan", None),
    )
    return jsonify({"error": "storage VIP configuration error"}), 500
```

The `BadRequest` handler keeps `PUT /vip_data` validation failures on the same JSON `400` contract already used by the current control-plane routes instead of falling back to Flask's default HTML error page. The `StorageVipConfigurationError` handler only covers request-context runtime failures. It should reuse the same structured `_log_db_failure(...)` path as other DB faults so request id, LAN, breaker state, timing, and `g.db_epoch_context` remain visible for configuration errors too. Background housekeeping must catch `StorageVipConfigurationError` itself so one LAN's missing VIP mapping does not terminate recovery rollback or drained-epoch cleanup for every LAN.

---

## 5. Disable `T_dados` as a forced reconnection trigger

The current `@app.after_request` hook should stop calling `_retire_client(lan)` or any future epoch-rotation helper. Keep it as observation-only.

Replace the current reconnect-forcing branch with this:

```python
@app.after_request
def _check_tdados_threshold(response):
    per_lan = getattr(g, "time_db_per_lan", None)
    if not per_lan:
        return response

    for lan, elapsed in per_lan.items():
        time_ms = elapsed * 1000
        if time_ms > TAU_DADOS_MS:
            log.debug(
                "T_dados[%s]=%.1fms > tau=%.1fms -- observed only, no forced reconnection",
                lan,
                time_ms,
                TAU_DADOS_MS,
            )
    return response
```

Implementation note:

- remove the current `in_recovery` branch from this hook
- remove the current `_retire_client(lan)` call from this hook
- keep `g.time_db_per_lan` because telemetry and higher-level elasticity logic still need it

---

## 6. Update `VIP_DATA` handling and recovery rollback

When the controller changes the VIP for a LAN, replace whichever epoch is current at that moment under the same lock. Use compare-and-swap only for failure-driven rotation and recovery rollback.

Code sketch:

```python
def _collect_expired_recovery_epochs() -> list[tuple[str, int]]:
    expired: list[tuple[str, int]] = []
    now = time.monotonic()

    with _epoch_states_registry_lock:
        items = list(_epoch_states.items())

    for lan, state in items:
        with state.lifecycle_lock:
            current = state.current
            if current is None or current.mode != "recovery":
                continue
            if current.first_lease_at is None or current.recovery_expires_at is None:
                continue
            if now >= current.recovery_expires_at:
                expired.append((lan, current.epoch_id))

    return expired


def _roll_expired_recovery_epochs() -> None:
    for lan, expected_epoch_id in _collect_expired_recovery_epochs():
        try:
            next_vip_ip = _snapshot_vip_ip_for_epoch(lan, mode="normal")
        except StorageVipConfigurationError as exc:
            log.error(
                "storage_vip_configuration_error during recovery rollback for %s: %s",
                lan,
                exc,
            )
            continue
        _rotate_epoch_if_current(
            lan,
            expected_epoch_id=expected_epoch_id,
            reason="recovery_expired",
            next_mode="normal",
            next_vip_ip=next_vip_ip,
        )


def _rotate_current_epoch_locked(
    lan: str,
    state: _LanEpochState,
    reason: str,
    next_mode: str,
    next_vip_ip: str,
) -> _MongoEpoch:
    current = state.current

    if current is not None:
        now = time.monotonic()
        current.retiring = True
        current.retire_requested_at = now
        current.drain_deadline = now + MONGO_CLIENT_RETIRE_GRACE_S
        state.retiring.append(current)

    state.current = _new_epoch_locked(
        state,
        mode=next_mode,
        vip_ip=next_vip_ip,
    )
    log.info(
        "Replaced current epoch for %s via %s: %s -> %s",
        lan,
        reason,
        getattr(current, "epoch_id", None),
        state.current.epoch_id,
    )
    return state.current


def _rotate_current_epoch(
    lan: str,
    reason: str,
    next_mode: str,
    next_vip_ip: str,
) -> _MongoEpoch:
    state = _get_lan_epoch_state(lan)
    with state.lifecycle_lock:
        return _rotate_current_epoch_locked(
            lan,
            state,
            reason,
            next_mode,
            next_vip_ip,
        )


def _snapshot_normal_vip_config() -> dict[str, str]:
    snapshot: dict[str, str] = {}

    with _epoch_states_registry_lock:
        items = list(_epoch_states.items())

    for lan, state in items:
        with state.lifecycle_lock:
            if state.normal_vip_ip is not None:
                snapshot[lan] = state.normal_vip_ip

    return snapshot


def _parse_vip_update_payload(body: object) -> dict[str, str]:
    if not isinstance(body, dict):
        raise BadRequest("vip_data payload must be a JSON object")

    normalized: dict[str, str] = {}
    for lan, raw_vip_ip in body.items():
        if not isinstance(lan, str) or not lan:
            raise BadRequest("vip_data payload contains an invalid LAN key")
        if not isinstance(raw_vip_ip, str):
            raise BadRequest(f"vip_data value for {lan} must be a string")

        vip_ip = raw_vip_ip.strip()
        if not vip_ip:
            raise BadRequest(f"vip_data value for {lan} must be a non-empty string")

        normalized[lan] = vip_ip

    return normalized


@app.route("/vip_data", methods=["PUT"])
def set_vip_data():
    body = _parse_vip_update_payload(request.get_json(silent=True))

    with _epoch_states_registry_lock:
        unknown_lans = sorted(lan for lan in body if lan not in _epoch_states)
    if unknown_lans:
        return jsonify({
            "error": "unknown LANs in vip_data update",
            "unknown_lans": unknown_lans,
        }), 400

    changed_lans: list[str] = []
    for lan, vip_ip in body.items():
        state = _get_lan_epoch_state(lan)
        with state.lifecycle_lock:
            if state.normal_vip_ip == vip_ip:
                continue
            state.normal_vip_ip = vip_ip
            _rotate_current_epoch_locked(
                lan,
                state,
                reason="vip_update",
                next_mode="normal",
                next_vip_ip=vip_ip,
            )
            changed_lans.append(lan)

    return jsonify({
        "message": "VIP data updated",
        "vip_data": _snapshot_normal_vip_config(),
        "changed_lans": changed_lans,
    }), 200
```

Run `_roll_expired_recovery_epochs()` from a background epoch-housekeeping loop so recovery rollback stays bounded by monotonic time even when unrelated LANs are the only ones receiving traffic. Recovery rollback must log and continue on `StorageVipConfigurationError` so housekeeping stays alive for other LANs and drained-epoch cleanup still runs.

Malformed `PUT /vip_data` input is a client error, not a runtime storage-configuration fault. The route should therefore reject invalid payload shapes, non-string or empty VIP values, and unknown LAN names with JSON `400` responses before mutating any LAN-local state. `StorageVipConfigurationError` remains the explicit contract for internal runtime configuration gaps after request validation has already passed.

The important detail is that VIP ownership is LAN-local inside `_LanEpochState`, and current-epoch replacement happens under that LAN's lifecycle lock. That guarantees an already-leased old epoch keeps its original path while the new current epoch becomes the target for future admitted requests through the updated VIP, without forcing unrelated LANs to wait on a shared VIP lock. The plan only claims connection handoff onto a newer local client object and its bound VIP; it does not claim that the controller will necessarily choose a different backend IP.

Validation for this section is about network behavior, not assumed controller changes. The implementation should confirm that simultaneous normal-VIP and recovery-VIP traffic from the same edge server behaves as intended under the existing DNAT/SNAT rules, that old requests continue on the leased old epoch while new requests use the newer epoch, and that reconnecting to the same backend remains acceptable when the controller's existing selection rules choose it again. Any runtime path that needs current LAN enumeration or current normal VIP config should use `_snapshot_normal_vip_config()` or direct LAN-local state rather than `vip_data_per_domain`. Because the LAN set is fixed at startup, `_snapshot_normal_vip_config()` should reflect every configured LAN even before that LAN has served traffic, and `PUT /vip_data` should reject unknown LANs rather than treating them as dynamic additions. Controller-side tracking of previously failed backends, targeted flow invalidation, or forced exclusion of a prior backend is out of scope for this plan.

---

## 7. Update diagnostics helpers to read request-owned and epoch-owned state

Current-epoch snapshots are still useful for global inspection, but request failure attribution must use the epoch that the request actually leased.

Code sketch:

```python
def _snapshot_epoch(epoch: _MongoEpoch | None) -> dict[str, int | str | bool | None]:
    if epoch is None:
        return {
            "epoch_id": None,
            "mode": "unknown",
            "vip_ip": None,
            "retiring": None,
        }
    return {
        "epoch_id": epoch.epoch_id,
        "mode": epoch.mode,
        "vip_ip": epoch.vip_ip,
        "retiring": epoch.retiring,
    }


def _get_current_epoch_snapshot(lan: str) -> dict[str, int | str | None]:
    with _epoch_states_registry_lock:
        state = _epoch_states.get(lan)
    if state is None:
        return {"epoch_id": None, "mode": "unknown"}

    with state.lifecycle_lock:
        current = state.current if state is not None else None
        if current is None:
            return {"epoch_id": None, "mode": "unknown"}
        return {
            "epoch_id": current.epoch_id,
            "mode": current.mode,
        }
```

Set `g.db_epoch_context = _snapshot_epoch(epoch)` immediately after `_lease_current_epoch(lan)` succeeds. Use that request-scoped snapshot in structured DB failure logging paths, including the request-context `StorageVipConfigurationError` handler. Keep `_get_current_epoch_snapshot(lan)` for global status and inspection endpoints instead of `client_mode_per_domain` and `_get_client_mode(lan)`. Any route or response payload that needs the current normal VIP config should use `_snapshot_normal_vip_config()` instead of reading `vip_data_per_domain`.

---

## 8. Replace the retired-client sweeper with epoch housekeeping

Epoch housekeeping should both roll back expired recovery epochs and remove retired epochs only after their leases have drained. A passed drain deadline should trigger logging or diagnostics, not forced closure of an epoch that still has active leases.

Code sketch:

```python
def _close_drained_epochs() -> None:
    ready: list[MongoClient] = []
    overdue: list[tuple[str, int, int]] = []
    now = time.monotonic()

    with _epoch_states_registry_lock:
        items = list(_epoch_states.items())

    for lan, state in items:
        with state.lifecycle_lock:
            still_retiring: list[_MongoEpoch] = []
            for epoch in state.retiring:
                deadline_passed = (
                    epoch.drain_deadline is not None and now >= epoch.drain_deadline
                )
                if epoch.lease_count == 0:
                    if epoch.client is not None:
                        ready.append(epoch.client)
                    continue
                if deadline_passed:
                    overdue.append((lan, epoch.epoch_id, epoch.lease_count))
                still_retiring.append(epoch)
            state.retiring = still_retiring

    for lan, epoch_id, lease_count in overdue:
        log.warning(
            "retiring epoch %s for %s still has %s active leases after drain deadline",
            epoch_id,
            lan,
            lease_count,
        )

    for client in ready:
        try:
            client.close()
        except Exception as exc:  # pragma: no cover - defensive close path
            log.warning("drained epoch close failed: %s", exc)


def _epoch_housekeeping_loop() -> None:
    sweep_interval = max(1.0, min(MONGO_CLIENT_RETIRE_GRACE_S / 2.0, 5.0))
    while True:
        time.sleep(sweep_interval)
        try:
            _roll_expired_recovery_epochs()
            _close_drained_epochs()
        except Exception:
            log.exception("epoch housekeeping sweep failed")
```

Replace the current retired-client sweeper thread and per-response global recovery-expiry scan with the background epoch-housekeeping thread. `_roll_expired_recovery_epochs()` should still catch `StorageVipConfigurationError` per affected LAN, and the outer housekeeping loop must log unexpected exceptions and continue so one sweeper bug does not permanently stop recovery rollback or drained-epoch cleanup.

---

## 9. Edit sequence

Apply the implementation in this order:

1. Remove the old shared-client globals, per-LAN recovery runtime state, and the one-shot recovery flag mechanism.
2. Add the epoch dataclasses, move `StorageVipConfigurationError` ahead of module-level initialization, include a bound VIP field, LAN-local VIP config fields, a registry lock for `_epoch_states`, one lifecycle lock inside each `_LanEpochState`, and the `_seed_epoch_states_from_config()` helper.
3. Seed `_epoch_states` from the resolved startup VIP maps at module initialization before the epoch-housekeeping thread starts, before telemetry initialization runs, and before the app begins background work.
4. Add `_snapshot_vip_ip_for_epoch`, `_get_lan_epoch_state`, `_new_epoch_locked`, `_lease_current_epoch`, `_get_or_create_breaker`, `_get_or_create_epoch_client`, and `_release_epoch`.
5. Make `_new_epoch_locked(...)` pure and require every epoch-mutating path to pass an explicit `vip_ip` snapshot.
6. Replace `_retire_client(lan)` and `_arm_recovery_once(lan)` with epoch rotation helpers that set the next epoch mode explicitly.
7. Update `timed_db(lan)` so `AutoReconnect` handling covers both first client materialization and later DB-handle use, keep the existing breaker `check()` admission API unless a dedicated compatibility rename is added, make it explicit that breaker admission still gates cutover onto the new current epoch, and add explicit JSON handlers for `BadRequest` and `StorageVipConfigurationError`.
8. Replace `_check_tdados_threshold(response)` so `T_dados` is observation-only and no longer forces reconnection.
9. Update `PUT /vip_data` so the entire payload is validated up front, malformed or unknown-LAN updates fail with JSON `400` responses before any state mutation, each LAN's VIP config and new current epoch creation are updated under that LAN's lifecycle lock, and the response returns LAN-local VIP snapshots instead of mirroring runtime truth back into `vip_data_per_domain`.
10. Update diagnostics helpers so request failure logging captures the leased epoch snapshot, request-context `StorageVipConfigurationError` handling reuses structured DB failure logging, and global inspection still reads the current epoch state.
11. Replace the retired-client sweeper and per-response recovery-expiry scan with background epoch housekeeping that logs and continues on `StorageVipConfigurationError` during recovery rollback and has a loop-level exception boundary so unexpected housekeeping bugs do not kill the thread.
12. Add focused validation for overlapping `AutoReconnect` failures, observation-only `T_dados`, monotonic recovery expiry, request-scoped epoch attribution, VIP update cutover, explicit configuration-failure handling, breaker singleton behavior, and housekeeping survivability.

---

## 10. Verification

Validate the implementation with focused checks:

1. Overlapping `AutoReconnect` failures on the same old epoch create exactly one new current epoch.
2. `T_dados` threshold breaches are logged but do not rotate epochs or force reconnection.
3. A recovery epoch starts its edge-local expiry window when its recovery client is first materialized, which is the first locally observable recovery reconnect attempt for this process, and recovery rollback stays bounded by monotonic time without waiting for unrelated request traffic.
4. Recovery mode requires a recovery VIP that is resolved by startup for every supported LAN, startup seeding fails fast if the resolved LAN sets do not match between normal and recovery VIP maps, and missing normal or recovery VIP mappings raise `StorageVipConfigurationError` instead of silently falling back to another path.
5. Request-scoped DB failure logs report the leased epoch context even when a newer epoch is already current.
6. An old leased epoch keeps using its bound VIP after a `VIP_DATA` update, while the new current epoch is created with the updated VIP and becomes the target for newly admitted requests once breaker state allows them.
7. Runtime LAN enumeration and current normal VIP reads use `_snapshot_normal_vip_config()` or direct LAN-local state rather than `vip_data_per_domain`, and the snapshot includes every startup-configured LAN even before first traffic.
8. Simultaneous normal-VIP and recovery-VIP traffic from the same edge server behaves as intended under the existing controller match rules.
9. Old requests continue on the leased old epoch while newer requests use the newer epoch, reducing the blast radius of a damaged shared connection.
10. Epoch rotation creates a fresh local client object and a new connection attempt, but validation does not assume a distinct backend IP unless the bound VIP changed.
11. Overdue-drain warnings include enough context to distinguish the LAN and epoch involved.
12. `timed_db(lan)` always resets the owner token and releases any epoch that was successfully leased, even when later client creation or DB use fails.
13. Request-context `StorageVipConfigurationError` handling uses structured DB failure logging with the same request-scoped epoch context as other DB faults and returns `500` instead of being folded into the runtime `PyMongoError` → `503` path.
14. Background epoch housekeeping logs `StorageVipConfigurationError` per affected LAN and continues running so other LANs still receive recovery rollback and drained-epoch cleanup, and an unexpected sweeper exception is logged without terminating future sweeps.
15. A rotation, recovery-expiry rollback, or VIP update on one LAN does not require holding the lifecycle lock or VIP snapshot path for a different LAN.
16. `PUT /vip_data` rejects unknown LANs instead of auto-creating runtime state, keeping the fixed startup-defined LAN contract explicit.
17. Malformed `PUT /vip_data` payloads, including null, non-string, empty, or unknown-LAN values, return JSON `400` responses with the existing `error` field before mutating any LAN-local state.
18. Concurrent requests for the same LAN share one installed circuit breaker object, so OPEN and HALF_OPEN admission state does not diverge across requests.

---

## 11. Documentation updates after implementation

After the code change is implemented and validated, update the operational documentation so it reflects why the epoch design grew beyond a simple shared-client replacement.

Required follow-up:

1. Update `docs/operation/vip_routing/vip_routing_overview.md` to explain that epoch now defines the request-owned storage path boundary: client object, bound VIP, recovery mode, and handoff between old and new requests.
2. Update `docs/operation/system_mechanisms.md` to clarify the edge-server assumptions that the plan now depends on: fixed startup-defined LAN set, normal and recovery VIP mappings for every LAN resolved by startup, and the fact that epoch rotation changes the local client object and bound VIP without claiming backend exclusion.
3. Update `docs/operation/vip_routing/implementation/vip_data_recovery_epoch_model.md` so it no longer describes the older one-shot recovery-client model and instead matches the approved epoch lifecycle, bounded recovery rollback, and housekeeping behavior.
4. Create `docs/operation/other/edge_storage_connection_epoch_visuals.md` if a dedicated visuals note is still wanted, and create or update the associated diagrams so the visuals show that epoch ownership now includes request leasing, LAN-local VIP state, breaker singleton ownership, and background cleanup of retiring epochs.
5. Add a short rationale section in the final implementation-facing docs stating that epoch started as a shared-client blast-radius reduction mechanism but had to absorb request attribution, VIP-path binding, recovery lifecycle, control-plane validation, and concurrency ownership so the runtime behavior stayed coherent under overlapping failures and VIP updates.

The documentation update is not optional polish. It is part of landing this plan safely, because the implementation no longer means only "rotate the MongoClient"; it means "treat epoch as the LAN-scoped unit of request-visible storage state over time."
