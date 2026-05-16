import logging
import os
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from uuid import uuid4

from flask import Flask, g, jsonify, request
from pymongo import MongoClient
from pymongo.errors import AutoReconnect, PyMongoError
from werkzeug.exceptions import BadRequest
from db_monitor import register as _register_db_monitor
from platform_cache import _owner_lan, cached_collection, set_tier1_manifest
from telemetry import init_telemetry, ZmqMetricSender, _get_server_mac

# Register the pymongo CommandListener before any MongoClient is created.
_register_db_monitor()
from compute import (
    score_device_severity,
    compute_trend,
    score_anomaly_results,
    score_dashboard_urgency,
    compute_dashboard_summary,
    TREND_WINDOW_SIZE,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BIND_HOST:   str = os.environ.get("BIND_HOST", "0.0.0.0")
BIND_PORT:   int = int(os.environ.get("BIND_PORT", "5000"))
DB_NAME:     str = os.environ.get("DB_NAME", "edge_platform")
LAN_ID:      str = os.environ.get("LAN_ID", "lan1")
DATA_TIER:   str = os.environ.get("DATA_TIER", "0")
DB_PORT:      int   = int(os.environ.get("DB_PORT", "27018"))
MAX_IDLE_MS:  int   = int(os.environ.get("MAX_IDLE_MS",
                          str(int(os.environ.get("VIP_IDLE_TIMEOUT", "30")) * 1000)))
TAU_DADOS_MS: float = float(os.environ.get("TAU_DADOS_MS", "65"))
CIRCUIT_COOLDOWN_S: float = float(os.environ.get("CIRCUIT_COOLDOWN_S", "5"))
DRAIN_POLL_INTERVAL_S: float = float(os.environ.get("DRAIN_POLL_INTERVAL_S", "0.5"))
DRAIN_QUIET_PERIOD_S: float = float(os.environ.get("DRAIN_QUIET_PERIOD_S", "1.0"))
MONGO_CLIENT_RETIRE_GRACE_S: float = float(
    os.environ.get("MONGO_CLIENT_RETIRE_GRACE_S", "30")
)
VIP_DATA_RECOVERY_SESSION_MAX_AGE_S: float = float(
    os.environ.get("VIP_DATA_RECOVERY_SESSION_MAX_AGE_S", "35")
)

# ---------------------------------------------------------------------------
# Drain state — set by POST /drain, read by before_request and drain monitor
# ---------------------------------------------------------------------------

_draining = False
_active_requests = 0
_last_user_request_ts = time.monotonic()
_active_requests_lock = threading.Lock()
_SKIP_COUNTING = frozenset({"/health", "/drain"})


class StorageVipConfigurationError(RuntimeError):
    """Raised when the fixed startup VIP configuration is incomplete."""


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


# ---------------------------------------------------------------------------
# MongoDB client epochs — one current epoch plus draining retired epochs per LAN.
# maxPoolSize=1 still ensures exactly one DNAT selection per LAN per edge server.
# maxIdleTimeMS matches VIP_IDLE_TIMEOUT so the driver closes the socket at the
# same cadence as the SDN controller removes idle DNAT rules.
# ---------------------------------------------------------------------------


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


def _accumulate_tdados(lan: str, elapsed: float) -> None:
    g.time_db_elapsed = getattr(g, "time_db_elapsed", 0.0) + elapsed
    per_lan = getattr(g, "time_db_per_lan", None)
    if per_lan is None:
        per_lan = {}
        g.time_db_per_lan = per_lan
    per_lan[lan] = per_lan.get(lan, 0.0) + elapsed


_seed_epoch_states_from_config()


class _CircuitState(Enum):
    CLOSED    = auto()
    OPEN      = auto()
    HALF_OPEN = auto()


class _CircuitBreaker:
    """Per-LAN circuit breaker for MongoDB connections."""

    def __init__(self):
        self.state = _CircuitState.CLOSED
        self._opened_at: float = 0.0
        self._lock = threading.Lock()

    def check(self) -> bool:
        """Return True if a request may proceed, False if circuit is OPEN."""
        with self._lock:
            if self.state is _CircuitState.CLOSED:
                return True
            if self.state is _CircuitState.OPEN:
                if time.monotonic() - self._opened_at >= CIRCUIT_COOLDOWN_S:
                    self.state = _CircuitState.HALF_OPEN
                    log.info("Circuit \u2192 HALF_OPEN (cooldown elapsed)")
                    return True  # allow one probe
                return False
            # HALF_OPEN \u2014 allow one probe, re-arm to block others
            self.state = _CircuitState.OPEN
            return True

    def record_success(self):
        with self._lock:
            if self.state is _CircuitState.HALF_OPEN:
                log.info("Circuit \u2192 CLOSED (probe succeeded)")
            self.state = _CircuitState.CLOSED

    def record_failure(self):
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
    pass


def _get_or_create_breaker(lan: str) -> _CircuitBreaker:
    state = _get_lan_epoch_state(lan)
    with state.lifecycle_lock:
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
    return breaker.snapshot()


def _log_db_failure(route_name: str, exc: Exception, lan: str | None = None) -> None:
    failure_lan = lan or getattr(g, "db_last_lan", None) or "unknown"
    breaker_snapshot = _get_breaker_snapshot(None if failure_lan == "unknown" else failure_lan)
    request_epoch = getattr(g, "db_epoch_context", None) or _snapshot_epoch(None)
    current_epoch = (
        _get_current_epoch_snapshot(failure_lan)
        if failure_lan != "unknown" else
        _snapshot_epoch(None)
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


@contextmanager
def timed_db(lan: str):
    """Yields a MongoDB database handle for the given LAN and accumulates
    elapsed time into ``g.time_db_elapsed`` so the telemetry layer can
    report T_dados correctly.

    Requests lease the current LAN epoch, lazily materialize that epoch's
    MongoClient, and keep their request-visible storage path bound to the
    leased epoch even if a newer epoch becomes current later.

    A per-LAN circuit breaker prevents threads from blocking on a known-dead
    server: if the circuit is OPEN, a ``CircuitOpenError`` is raised immediately
    instead of waiting for the 3 s server-selection timeout.
    """
    g.db_last_lan = lan
    breaker = _get_or_create_breaker(lan)
    if not breaker.check():
        raise CircuitOpenError(f"circuit open for {lan}")
    # Tag every wrapped cached_collection() access made inside this block
    # with the owning LAN. Token is returned by set() and restored in finally
    # so nested timed_db() calls unwind correctly.
    owner_token = _owner_lan.set(lan)
    t0 = time.monotonic()
    epoch: _MongoEpoch | None = None
    try:
        epoch = _lease_current_epoch(lan)
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
        if epoch is not None:
            _release_epoch(lan, epoch)
        _owner_lan.reset(owner_token)
        _accumulate_tdados(lan, time.monotonic() - t0)


# ---------------------------------------------------------------------------
# Drain guard — registered before init_telemetry so it has priority
# ---------------------------------------------------------------------------

def get_drain_state() -> str:
    return "draining" if _draining else "active"

@app.before_request
def _drain_guard():
    global _active_requests, _last_user_request_ts
    g.request_id = uuid4().hex[:12]
    g.db_last_lan = None
    g.db_epoch_context = None
    g.db_last_command = None
    g.db_last_command_db = None
    g.db_last_command_target = None
    g.db_last_command_failed = None
    g.db_last_command_duration_s = None
    g.counted = False # g is the Flask request-global namespace; this flag tracks whether the current request was counted in _active_requests
    if request.path in _SKIP_COUNTING:
        return None  # control-plane routes bypass request counting
    with _active_requests_lock:
        _active_requests += 1
        _last_user_request_ts = time.monotonic()
    g.counted = True  # only set after successful increment
    return None


@app.after_request
def _drain_counter(response):
    global _active_requests
    # Guard with g.counted (set in _drain_guard) — NOT _draining — so that
    # requests which were counted before draining was set still decrement.
    if getattr(g, "counted", False):
        with _active_requests_lock:
            _active_requests -= 1
    return response


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


# ---------------------------------------------------------------------------
# Control-plane routes (used by the SDN controller)
# ---------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


_drain_monitor_thread: threading.Thread | None = None


@app.route("/drain", methods=["POST"])
def drain():
    """Change the local drain state.

    Supported commands:
      - start  (default when omitted)
      - cancel

    ``start`` moves the server into quiesce mode without rejecting workload
    requests. Repeated ``start`` refreshes the quiet-period timer.
    """
    global _draining, _drain_monitor_thread, _last_user_request_ts
    body = request.get_json(silent=True) or {}
    command = body.get("command", "start")

    if command not in ("start", "cancel"):
        return jsonify({"error": "invalid command"}), 400

    if command == "cancel":
        _draining = False
        with _active_requests_lock:
            remaining = _active_requests
        log.info("Drain canceled — server returned to active state with %d in-flight", remaining)
        return jsonify({"state": "active", "active_requests": remaining}), 200

    with _active_requests_lock:
        _draining = True
        _last_user_request_ts = time.monotonic()
        remaining = _active_requests

    if _drain_monitor_thread is None or not _drain_monitor_thread.is_alive():
        _drain_monitor_thread = threading.Thread(
            target=_drain_monitor, daemon=True, name="drain-monitor"
        )
        _drain_monitor_thread.start()
    log.info("Drain activated — quiescing with %d in-flight", remaining)
    return jsonify({"state": "draining", "active_requests": remaining}), 200


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


@app.route("/tier1_manifest", methods=["PUT"])
def tier1_manifest():
    """Install / replace / revoke the Tier 1 manifest for an ``owner_lan``.

    Body shape:
        {
          "owner_lan":   "lan1",
          "host":        "10.0.1.10:27018"  | null,
          "collections": {"sensor_reports": ["lan1::dev-7", ...], ...} | {}
        }
    ``host=null`` or empty ``collections`` revokes the manifest.
    """
    body = request.get_json(force=True) or {}
    owner_lan = body.get("owner_lan")
    if not owner_lan:
        return jsonify({"error": "'owner_lan' is required"}), 400
    set_tier1_manifest(
        owner_lan=owner_lan,
        host=body.get("host"),
        collections=body.get("collections"),
    )
    return jsonify({"ok": True}), 200


@app.route("/wait_time", methods=["POST"])
def post_wait_time():
    body = request.get_json(silent=True) or {}
    wait_time_ms = body.get("wait_time_ms")
    if not isinstance(wait_time_ms, (int, float)):
        return jsonify({"error": "'wait_time_ms' field must be a number"}), 400
    time.sleep(wait_time_ms / 1000.0)
    return jsonify({"message": f"Simulating wait of {wait_time_ms} ms"}), 200


# ---------------------------------------------------------------------------
# Workload routes
# ---------------------------------------------------------------------------

@app.route("/device/<path:device_id>/latest", methods=["GET"])
def device_latest(device_id: str):
    """Return the latest sensor report for a device.

    Query params:
      node_id  — optional monitoring-node identifier; when supplied the node's
                 alert threshold overrides are applied from device_registry.

    Two VIP_Dados reads (sensor_reports + device_registry) create the
    T_dados amplification effect described in the workload model.
    """
    node_id = request.args.get("node_id", "unknown")
    device_lan = device_id.split("::")[0]

    try:
        with timed_db(device_lan) as db:
            doc = cached_collection(db, "sensor_reports").find_one({"_id": device_id})

        if doc is None:
            return jsonify({"error": "device not found", "device_id": device_id}), 404

        threshold_override = None
        if node_id != "unknown":
            node_lan = node_id.split("::")[0]
            with timed_db(node_lan) as db:
                registry = cached_collection(db, "device_registry").find_one(
                    {"_id": node_id},
                    {"alert_config.threshold_override": 1},
                )
            if registry:
                dev_type = doc.get("device_type", "")
                threshold_override = (
                    registry.get("alert_config", {})
                    .get("threshold_override", {})
                    .get(dev_type)
                )

        # --- Compute: severity scoring ---
        value     = doc.get("payload", {}).get("value")
        threshold = threshold_override or doc.get("metadata", {}).get("alert_threshold")
        severity_result = score_device_severity(
            value, threshold, doc.get("device_type", ""), device_id,
        )
        alert = severity_result["alert"]

        # Append query event — capture read latency before this write
        query_event = {
            "node_id":         node_id,
            "device_id":       device_id,
            "region_served":   LAN_ID,
            "timestamp":       datetime.now(timezone.utc),
            "latency_ms":      round(g.time_db_elapsed * 1000, 2),
            "served_from_tier": DATA_TIER,
        }
        try:
            with timed_db(LAN_ID) as db:
                cached_collection(db, "query_events").insert_one(query_event)
        except PyMongoError as exc:
            log.warning("query_events insert failed: %s", exc)

        # --- Compute: trend analysis from recent query_events ---
        try:
            with timed_db(LAN_ID) as db:
                recent_events = list(
                    cached_collection(db, "query_events").find(
                        {"device_id": device_id},
                        {"latency_ms": 1, "timestamp": 1, "_id": 0},
                    )
                    .sort("timestamp", -1)
                    .limit(TREND_WINDOW_SIZE)
                )
        except PyMongoError:
            recent_events = []

        trend_result = compute_trend(recent_events)

        doc["_id"]       = str(doc["_id"])
        doc["alert"]     = alert
        doc["severity"]  = severity_result
        doc["trend"]     = trend_result
        return jsonify(doc), 200

    except PyMongoError as exc:
        _log_db_failure("device_latest", exc)
        return jsonify({"error": "database error"}), 503


@app.route("/anomalies", methods=["GET"])
def anomalies():
    """Return the top-10 most-queried devices in a region + time window,
    enriched with their current sensor status.

    Query params:
      region  — region to filter query_events (default: LAN_ID env var)
      window  — look-back window in hours (default: 1)
    """
    region   = request.args.get("region", LAN_ID)
    window_h = float(request.args.get("window", "1"))
    since_dt = datetime.fromtimestamp(
        time.time() - window_h * 3600, tz=timezone.utc
    )

    try:
        with timed_db(LAN_ID) as db:
            pipeline = [
                {"$match": {
                    "region_served": region,
                    "timestamp":     {"$gte": since_dt},
                }},
                {"$group": {
                    "_id":            "$device_id",
                    "query_count":    {"$sum": 1},
                    "avg_latency_ms": {"$avg": "$latency_ms"},
                }},
                {"$sort":  {"query_count": -1}},
                {"$limit": 10},
            ]
            hot_devices = list(cached_collection(db, "query_events").aggregate(pipeline))

        device_ids = [d["_id"] for d in hot_devices]
        ids_by_lan: dict[str, list[str]] = {}
        for did in device_ids:
            ids_by_lan.setdefault(did.split("::")[0], []).append(did)

        status_map: dict[str, dict] = {}
        for lan, ids in ids_by_lan.items():
            with timed_db(lan) as db:
                for d in cached_collection(db, "sensor_reports").find(
                    {"_id": {"$in": ids}},
                    {"payload.status": 1, "payload.value": 1, "device_type": 1, "tags": 1,
                     "metadata.alert_threshold": 1},
                ):
                    status_map[d["_id"]] = d

        for d in hot_devices:
            status = status_map.get(d["_id"], {})
            d["device_id"]   = d.pop("_id")
            d["status"]      = status.get("payload", {}).get("status", "unknown")
            d["value"]       = status.get("payload", {}).get("value")
            d["device_type"] = status.get("device_type")
            d["tags"]        = status.get("tags", [])
            d["threshold"]   = status.get("metadata", {}).get("alert_threshold")

        # --- Compute: composite risk scoring ---
        hot_devices = score_anomaly_results(hot_devices)

        return jsonify({"region": region, "window_hours": window_h, "results": hot_devices}), 200

    except PyMongoError as exc:
        _log_db_failure("anomalies", exc)
        return jsonify({"error": "database error"}), 503


@app.route("/dashboard/<node_id>", methods=["GET"])
def dashboard(node_id: str):
    """Return the most urgent devices for a monitoring node based on its
    subscribed tags, sorted by proximity of the current value to its alert
    threshold.

    Query params:
      limit  — max devices to return (default: 10)
    """
    limit = int(request.args.get("limit", "10"))
    node_lan = node_id.split("::")[0]

    try:
        with timed_db(node_lan) as db:
            registry = cached_collection(db, "device_registry").find_one({"_id": node_id})

        if registry is None:
            return jsonify({"error": "node not found", "node_id": node_id}), 404

        subscribed_tags = registry.get("subscribed_tags", [])

        devices: list[dict] = []
        for lan in _snapshot_normal_vip_config():
            with timed_db(lan) as db:
                devices.extend(
                    cached_collection(db, "sensor_reports").find(
                        {"tags": {"$in": subscribed_tags}},
                        {"_id": 1, "device_type": 1, "tags": 1,
                         "payload": 1, "metadata": 1, "region_origin": 1,
                         "last_updated": 1},
                    )
                )

        # --- Compute: multi-factor urgency scoring ---
        devices = score_dashboard_urgency(devices)
        devices = devices[:limit]

        # --- Compute: fleet summary statistics ---
        summary = compute_dashboard_summary(devices)

        for d in devices:
            d["_id"] = str(d["_id"])

        return jsonify({
            "node_id":         node_id,
            "subscribed_tags": subscribed_tags,
            "devices":         devices,
            "summary":         summary,
        }), 200

    except PyMongoError as exc:
        _log_db_failure("dashboard", exc)
        return jsonify({"error": "database error"}), 503


# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Drain monitor — background thread that fires drain_complete and self-exits
# ---------------------------------------------------------------------------

# Shared sender: reused by telemetry and drain monitor so both emit through
# the same ZMQ PUSH connection.
_metric_sender = ZmqMetricSender()
threading.Thread(
    target=_epoch_housekeeping_loop,
    daemon=True,
    name="mongo-epoch-housekeeping",
).start()


def _drain_monitor() -> None:
    """Background thread started by POST /drain.

    The server keeps serving workload traffic while draining. Once request
    activity reaches zero and remains quiet for a short period, emit
    ``drain_complete`` and terminate the process. If drain is canceled, exit
    the thread silently.
    """
    while True:
        time.sleep(DRAIN_POLL_INTERVAL_S)
        with _active_requests_lock:
            remaining = _active_requests
            quiet_for = time.monotonic() - _last_user_request_ts
        if not _draining:
            return
        if remaining <= 0 and quiet_for >= DRAIN_QUIET_PERIOD_S:
            log.info("Drain complete \u2014 all in-flight requests finished, sending drain_complete event")
            _metric_sender.send({
                "event_type": "drain_complete",
                "server_id":  _get_server_mac(),
                "ts":         time.time(),
            })
            time.sleep(0.1)  # small delay to let ZMQ flush the send buffer
            os._exit(0)  # noqa: SLF001 — intentional hard exit after drain

init_telemetry(app, sender=_metric_sender, get_drain_state=get_drain_state)

if __name__ == "__main__":
    log.info(
        "Starting edge-server on %s:%d  lan=%s  db_name=%s  vip_data=%s"
        "  vip_data_recovery=%s"
        "  maxIdleTimeMS=%d  tau_dados=%.0fms  recovery_session_max_age_s=%.1f",
        BIND_HOST, BIND_PORT, LAN_ID, DB_NAME, _snapshot_normal_vip_config(),
        vip_data_recovery_per_domain,
        MAX_IDLE_MS, TAU_DADOS_MS, VIP_DATA_RECOVERY_SESSION_MAX_AGE_S,
    )
    app.run(host=BIND_HOST, port=BIND_PORT, threaded=True)
