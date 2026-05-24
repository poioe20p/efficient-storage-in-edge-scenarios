from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Literal, TypeVar

from flask import g, request
from pymongo import MongoClient
from pymongo.command_cursor import CommandCursor
from pymongo.cursor import Cursor
from pymongo.errors import AutoReconnect, PyMongoError
from werkzeug.exceptions import BadRequest

from edge_server_config import CONFIG
from platform_cache import _owner_lan

log = logging.getLogger(__name__)

DB_NAME = CONFIG.db_name
DB_PORT = CONFIG.db_port
MAX_IDLE_MS = CONFIG.max_idle_ms
MONGO_CLIENT_RETIRE_GRACE_S = CONFIG.mongo_client_retire_grace_s
VIP_DATA_RECOVERY_SESSION_MAX_AGE_S = CONFIG.vip_data_recovery_session_max_age_s
CIRCUIT_COOLDOWN_S = CONFIG.circuit_cooldown_s


class StorageVipConfigurationError(RuntimeError):
    """Raised when the fixed startup VIP configuration is incomplete."""


@dataclass
class _MongoEpoch:
    """Global Mongo client generation scoped to a LAN and VIP selection.

    This runtime keeps the epoch object, its client, and all transition state
    together because they are guarded by the same per-LAN lifecycle lock.
    """

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


class RequestLeaseLifecycle(Enum):
    ACTIVE = auto()
    FAILED = auto()
    COMPLETED = auto()


@dataclass
class RequestLease:
    """Request-scoped binding between one Flask request and one Mongo epoch."""

    lan: str
    epoch: _MongoEpoch
    first_bound_at: float
    lifecycle: RequestLeaseLifecycle = RequestLeaseLifecycle.ACTIVE
    replay_safe: bool = True
    rebinds_used: int = 0
    terminal_reason: str | None = None


@dataclass
class _LanEpochState:
    lifecycle_lock: threading.Lock = field(default_factory=threading.Lock)
    normal_vip_ip: str | None = None
    recovery_vip_ip: str | None = None
    breaker: "_CircuitBreaker | None" = None
    current: _MongoEpoch | None = None
    retiring: list[_MongoEpoch] = field(default_factory=list)
    next_epoch_id: int = 1


vip_data_per_domain = {
    "lan1": "10.0.0.254",
    "lan2": "10.0.1.254",
}
vip_data_recovery_per_domain = {
    "lan1": os.environ.get("VIP_DATA_RECOVERY_N1_IP", "10.0.0.252"),
    "lan2": os.environ.get("VIP_DATA_RECOVERY_N2_IP", "10.0.1.252"),
}

_epoch_states_registry_lock = threading.Lock()
_epoch_states: dict[str, _LanEpochState] = {}
_epoch_housekeeping_start_lock = threading.Lock()
_epoch_housekeeping_started = False


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


def _get_lan_epoch_state(lan: str) -> _LanEpochState:
    with _epoch_states_registry_lock:
        state = _epoch_states.get(lan)
    if state is None:
        raise StorageVipConfigurationError(f"unknown configured LAN: {lan}")
    return state


def _snapshot_vip_ip_for_epoch(lan: str, mode: str) -> str:
    state = _get_lan_epoch_state(lan)
    with state.lifecycle_lock:
        if mode == "normal":
            vip_ip = state.normal_vip_ip
            if vip_ip is None:
                raise StorageVipConfigurationError(f"missing normal VIP mapping for {lan}")
            return vip_ip

        if mode == "recovery":
            vip_ip = state.recovery_vip_ip
            if vip_ip is None:
                raise StorageVipConfigurationError(
                    f"missing recovery VIP mapping for {lan}"
                )
            return vip_ip

    raise ValueError(f"unsupported epoch mode: {mode}")


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


def _mark_epoch_retiring_locked(state: _LanEpochState, epoch: _MongoEpoch) -> None:
    now = time.monotonic()
    epoch.retiring = True
    epoch.retire_requested_at = now
    epoch.drain_deadline = now + MONGO_CLIENT_RETIRE_GRACE_S
    state.retiring.append(epoch)


def _lease_current_epoch(lan: str) -> _MongoEpoch:
    state = _get_lan_epoch_state(lan)
    with state.lifecycle_lock:
        current = state.current
        if current is None:
            vip_ip = state.normal_vip_ip
            if vip_ip is None:
                raise StorageVipConfigurationError(f"missing normal VIP mapping for {lan}")
            current = _new_epoch_locked(
                state,
                mode="normal",
                vip_ip=vip_ip,
            )
            state.current = current

        current.lease_count += 1
        if current.first_lease_at is None:
            current.first_lease_at = time.monotonic()
        return current


def _get_or_create_epoch_client(lan: str, epoch: _MongoEpoch) -> MongoClient:
    state = _get_lan_epoch_state(lan)
    with state.lifecycle_lock:
        if epoch.client is not None:
            return epoch.client

        url = f"mongodb://{epoch.vip_ip}:{DB_PORT}/"
        epoch.client = MongoClient(
            url,
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
        log.info(
            "Created MongoClient for %s epoch=%s mode=%s via %s "
            "(maxIdleTimeMS=%d recovery_session_max_age_s=%.1f)",
            lan,
            epoch.epoch_id,
            epoch.mode,
            url,
            MAX_IDLE_MS,
            VIP_DATA_RECOVERY_SESSION_MAX_AGE_S,
        )
        return epoch.client


def _release_epoch(lan: str, epoch: _MongoEpoch) -> None:
    state = _get_lan_epoch_state(lan)
    with state.lifecycle_lock:
        if epoch.lease_count > 0:
            epoch.lease_count -= 1


def _get_request_lease_registry() -> dict[str, RequestLease]:
    registry = getattr(g, "db_request_leases", None)
    if registry is None:
        registry = {}
        g.db_request_leases = registry
    return registry


def _bind_new_request_lease(lan: str) -> RequestLease:
    registry = _get_request_lease_registry()
    state = _get_lan_epoch_state(lan)

    with state.lifecycle_lock:
        current = state.current
        if current is None:
            vip_ip = state.normal_vip_ip
            if vip_ip is None:
                raise StorageVipConfigurationError(f"missing normal VIP mapping for {lan}")
            current = _new_epoch_locked(
                state,
                mode="normal",
                vip_ip=vip_ip,
            )
            state.current = current

        breaker = _get_or_create_breaker_locked(state)
        if not breaker.check():
            raise CircuitOpenError(f"circuit open for {lan} epoch={current.epoch_id}")

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

            next_vip_ip = state.recovery_vip_ip
            if next_vip_ip is None:
                raise StorageVipConfigurationError(
                    f"missing recovery VIP mapping for {lease.lan}"
                )
            adopted_epoch = _rotate_epoch_if_current_locked(
                lease.lan,
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

        now = time.monotonic()
        adopted_epoch.lease_count += 1
        if adopted_epoch.first_lease_at is None:
            adopted_epoch.first_lease_at = now
        lease.epoch = adopted_epoch
        lease.rebinds_used += 1

    _release_epoch(lease.lan, failed_epoch)
    return adopted_epoch


def _rotate_epoch_if_current_locked(
    lan: str,
    state: _LanEpochState,
    expected_epoch_id: int,
    reason: str,
    next_mode: str,
    next_vip_ip: str,
) -> _MongoEpoch:
    current = state.current

    if current is None:
        state.current = _new_epoch_locked(
            state,
            mode=next_mode,
            vip_ip=next_vip_ip,
        )
        log.info(
            "Initialized epoch for %s via %s: epoch=%s mode=%s vip=%s",
            lan,
            reason,
            state.current.epoch_id,
            state.current.mode,
            state.current.vip_ip,
        )
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

    _mark_epoch_retiring_locked(state, current)
    state.current = _new_epoch_locked(
        state,
        mode=next_mode,
        vip_ip=next_vip_ip,
    )
    log.info(
        "Rotated epoch for %s via %s: %s -> %s (mode=%s vip=%s)",
        lan,
        reason,
        current.epoch_id,
        state.current.epoch_id,
        state.current.mode,
        state.current.vip_ip,
    )
    return state.current


def _rotate_epoch_if_current(
    lan: str,
    expected_epoch_id: int,
    reason: str,
    next_mode: str,
    next_vip_ip: str,
) -> _MongoEpoch:
    state = _get_lan_epoch_state(lan)
    with state.lifecycle_lock:
        return _rotate_epoch_if_current_locked(
            lan,
            state,
            expected_epoch_id,
            reason,
            next_mode,
            next_vip_ip,
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
        _mark_epoch_retiring_locked(state, current)

    state.current = _new_epoch_locked(
        state,
        mode=next_mode,
        vip_ip=next_vip_ip,
    )
    log.info(
        "Replaced current epoch for %s via %s: %s -> %s (mode=%s vip=%s)",
        lan,
        reason,
        getattr(current, "epoch_id", None),
        state.current.epoch_id,
        state.current.mode,
        state.current.vip_ip,
    )
    return state.current


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


def _close_drained_epochs() -> None:
    ready: list[tuple[str, int, MongoClient]] = []
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
                        ready.append((lan, epoch.epoch_id, epoch.client))
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

    for lan, epoch_id, client in ready:
        try:
            client.close()
        except Exception as exc:  # pragma: no cover - defensive close path
            log.warning("drained epoch close failed for %s epoch=%s: %s", lan, epoch_id, exc)


def _epoch_housekeeping_loop() -> None:
    sweep_interval = max(1.0, min(MONGO_CLIENT_RETIRE_GRACE_S / 2.0, 5.0))
    while True:
        time.sleep(sweep_interval)
        try:
            _roll_expired_recovery_epochs()
            _close_drained_epochs()
        except Exception:
            log.exception("epoch housekeeping sweep failed")


def start_epoch_housekeeping() -> None:
    global _epoch_housekeeping_started

    # This thread must be single-start because it operates on one shared epoch
    # registry for the process. Starting more than one would create duplicate
    # close/rollback sweeps against the same state.
    with _epoch_housekeeping_start_lock:
        if _epoch_housekeeping_started:
            return
        threading.Thread(
            target=_epoch_housekeeping_loop,
            daemon=True,
            name="mongo-epoch-housekeeping",
        ).start()
        _epoch_housekeeping_started = True


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


def _get_current_epoch_snapshot(lan: str) -> dict[str, int | str | bool | None]:
    with _epoch_states_registry_lock:
        state = _epoch_states.get(lan)
    if state is None:
        return _snapshot_epoch(None)

    with state.lifecycle_lock:
        return _snapshot_epoch(state.current)


def snapshot_normal_vip_config() -> dict[str, str]:
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


def prepare_vip_update_payload(body: object) -> dict[str, str]:
    return _parse_vip_update_payload(body)


def find_unknown_vip_update_lans(payload: dict[str, str]) -> list[str]:
    with _epoch_states_registry_lock:
        return sorted(lan for lan in payload if lan not in _epoch_states)


def apply_vip_update(payload: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    changed_lans: list[str] = []
    for lan, vip_ip in payload.items():
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

    return snapshot_normal_vip_config(), changed_lans


def _accumulate_tdados(lan: str, elapsed: float) -> None:
    g.time_db_elapsed = getattr(g, "time_db_elapsed", 0.0) + elapsed
    per_lan = getattr(g, "time_db_per_lan", None)
    if per_lan is None:
        per_lan = {}
        g.time_db_per_lan = per_lan
    per_lan[lan] = per_lan.get(lan, 0.0) + elapsed


class _CircuitState(Enum):
    CLOSED = auto()
    OPEN = auto()
    HALF_OPEN = auto()


class _CircuitBreaker:
    """Per-LAN circuit breaker for MongoDB connections."""

    def __init__(self):
        self.state = _CircuitState.CLOSED
        self._opened_at: float = 0.0
        self._lock = threading.Lock()

    def check(self) -> bool:
        with self._lock:
            if self.state is _CircuitState.CLOSED:
                return True
            if self.state is _CircuitState.OPEN:
                if time.monotonic() - self._opened_at >= CIRCUIT_COOLDOWN_S:
                    self.state = _CircuitState.HALF_OPEN
                    log.info("Circuit -> HALF_OPEN (cooldown elapsed)")
                    return True
                return False
            self.state = _CircuitState.OPEN
            return True

    def record_success(self) -> None:
        with self._lock:
            if self.state is _CircuitState.HALF_OPEN:
                log.info("Circuit -> CLOSED (probe succeeded)")
            self.state = _CircuitState.CLOSED

    def record_failure(self) -> None:
        with self._lock:
            self.state = _CircuitState.OPEN
            self._opened_at = time.monotonic()

    def snapshot(self) -> dict[str, float | str]:
        with self._lock:
            cooldown_remaining_s = 0.0
            if self.state is _CircuitState.OPEN:
                cooldown_remaining_s = max(
                    0.0,
                    CIRCUIT_COOLDOWN_S - (time.monotonic() - self._opened_at),
                )
            return {
                "state": self.state.name,
                "cooldown_remaining_s": round(cooldown_remaining_s, 3),
            }


class CircuitOpenError(PyMongoError):
    """Raised when the circuit breaker for a LAN is open."""


def _get_or_create_breaker_locked(state: _LanEpochState) -> _CircuitBreaker:
    breaker = state.breaker
    if breaker is None:
        breaker = _CircuitBreaker()
        state.breaker = breaker
    return breaker


def _get_breaker_snapshot(lan: str | None) -> dict[str, float | str]:
    if not lan:
        return {"state": "UNKNOWN", "cooldown_remaining_s": 0.0}

    with _epoch_states_registry_lock:
        state = _epoch_states.get(lan)
    if state is None:
        return {"state": "UNKNOWN", "cooldown_remaining_s": 0.0}

    with state.lifecycle_lock:
        breaker = state.breaker
        if breaker is None:
            return {"state": "UNINITIALIZED", "cooldown_remaining_s": 0.0}
        snapshot = breaker.snapshot()
    return {
        "state": str(snapshot["state"]),
        "cooldown_remaining_s": float(snapshot["cooldown_remaining_s"]),
    }


def log_db_failure(route_name: str, exc: Exception, lan: str | None = None) -> None:
    failure_lan = lan or getattr(g, "db_last_lan", None) or "unknown"
    breaker_snapshot = _get_breaker_snapshot(None if failure_lan == "unknown" else failure_lan)
    request_epoch = getattr(g, "db_epoch_context", None) or _snapshot_epoch(None)
    current_epoch = (
        _get_current_epoch_snapshot(failure_lan)
        if failure_lan != "unknown"
        else _snapshot_epoch(None)
    )
    log.error(
        "db_failure route=%s request_id=%s method=%s path=%s lan=%s "
        "request_epoch_id=%s request_epoch_mode=%s request_epoch_vip=%s request_epoch_retiring=%s "
        "current_epoch_id=%s current_epoch_mode=%s current_epoch_vip=%s current_epoch_retiring=%s "
        "breaker_state=%s breaker_cooldown_remaining_s=%.3f "
        "exc_type=%s exc=%s last_cmd=%s last_cmd_db=%s last_cmd_target=%s "
        "last_cmd_failed=%s last_cmd_s=%s tdados_s=%.6f tdb_read_s=%.6f "
        "tdb_write_s=%.6f tdb_cmd_count=%d",
        route_name,
        getattr(g, "request_id", "unknown"),
        request.method,
        request.path,
        failure_lan,
        request_epoch["epoch_id"],
        request_epoch["mode"],
        request_epoch["vip_ip"],
        request_epoch["retiring"],
        current_epoch["epoch_id"],
        current_epoch["mode"],
        current_epoch["vip_ip"],
        current_epoch["retiring"],
        breaker_snapshot["state"],
        float(breaker_snapshot["cooldown_remaining_s"]),
        type(exc).__name__,
        exc,
        getattr(g, "db_last_command", None),
        getattr(g, "db_last_command_db", None),
        getattr(g, "db_last_command_target", None),
        getattr(g, "db_last_command_failed", None),
        getattr(g, "db_last_command_duration_s", None),
        getattr(g, "time_db_elapsed", 0.0),
        getattr(g, "time_db_read_s", 0.0),
        getattr(g, "time_db_write_s", 0.0),
        getattr(g, "time_db_cmd_count", 0),
    )


def _project_request_lease_outcome(lease: RequestLease) -> dict[str, Any]:
    projected_lifecycle = (
        RequestLeaseLifecycle.FAILED
        if lease.lifecycle == RequestLeaseLifecycle.FAILED
        else RequestLeaseLifecycle.COMPLETED
    )

    if projected_lifecycle == RequestLeaseLifecycle.FAILED:
        outcome = "failure_terminal"
    elif lease.rebinds_used > 0:
        outcome = "success_after_rebind"
    else:
        outcome = "success_normal"

    return {
        "lan": lease.lan,
        "epoch_id": lease.epoch.epoch_id,
        "epoch_mode": lease.epoch.mode,
        "lifecycle": projected_lifecycle.name,
        "outcome": outcome,
        "rebinds_used": lease.rebinds_used,
        "replay_safe": lease.replay_safe,
        "terminal_reason": lease.terminal_reason,
    }


def collect_request_lease_outcomes() -> list[dict[str, Any]]:
    registry = getattr(g, "db_request_leases", None) or {}
    return [
        _project_request_lease_outcome(lease)
        for _lan, lease in sorted(registry.items())
    ]


def log_request_lease_outcome(entry: dict[str, Any]) -> None:
    log.info(
        "request lease outcome request_id=%s lan=%s lifecycle=%s outcome=%s "
        "epoch_id=%s epoch_mode=%s rebinds_used=%s replay_safe=%s "
        "terminal_reason=%s",
        getattr(g, "request_id", "unknown"),
        entry["lan"],
        entry["lifecycle"],
        entry["outcome"],
        entry["epoch_id"],
        entry["epoch_mode"],
        entry["rebinds_used"],
        entry["replay_safe"],
        entry["terminal_reason"],
    )


def release_request_leases() -> None:
    registry = getattr(g, "db_request_leases", None)
    if not registry:
        return

    for lease in registry.values():
        if lease.lifecycle != RequestLeaseLifecycle.FAILED:
            lease.lifecycle = RequestLeaseLifecycle.COMPLETED
        _release_epoch(lease.lan, lease.epoch)
    registry.clear()


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
    with state.lifecycle_lock:
        current = state.current
        if current is None or current.epoch_id != epoch.epoch_id:
            return
        breaker = _get_or_create_breaker_locked(state)
        if outcome == "success":
            breaker.record_success()
        else:
            breaker.record_failure()


def _run_db_op_once(
    lan: str,
    lease: RequestLease,
    op_name: str,
    fn: Callable[[Any], T],
) -> T:
    g.db_last_lan = lan
    owner_token = _owner_lan.set(lan)
    t0 = time.monotonic()
    epoch = lease.epoch
    try:
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


@contextmanager
def timed_db(lan: str):
    """Compatibility context manager for low-level DB access.

    Serving-path MongoDB work should use run_with_request_lease(...) so replay
    safety and bounded rebind stay attached to the explicit operation boundary
    instead of a yielded DB handle.
    """

    g.db_last_lan = lan
    registry = _get_request_lease_registry()
    lease = registry.get(lan)
    if lease is not None and lease.lifecycle == RequestLeaseLifecycle.FAILED:
        raise PyMongoError(f"request lease already failed for {lan}")
    if lease is not None and lease.lifecycle == RequestLeaseLifecycle.COMPLETED:
        raise PyMongoError(f"request lease already completed for {lan}")

    lease = lease or _get_or_bind_request_lease(lan)
    lease.replay_safe = False
    owner_token = _owner_lan.set(lan)
    t0 = time.monotonic()
    try:
        epoch = lease.epoch
        g.db_epoch_context = _snapshot_epoch(epoch)
        g.db_used_epoch_client = True
        client = _get_or_create_epoch_client(lan, epoch)
        yield client[DB_NAME]
    except AutoReconnect:
        _record_breaker_outcome_if_authoritative(lan, lease.epoch, outcome="failure")
        raise
    else:
        _record_breaker_outcome_if_authoritative(
            lan,
            lease.epoch,
            outcome="success",
            used_epoch_client=True,
        )
    finally:
        _owner_lan.reset(owner_token)
        _accumulate_tdados(lan, time.monotonic() - t0)


_seed_epoch_states_from_config()