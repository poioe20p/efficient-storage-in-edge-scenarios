import logging
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum, auto

from flask import Flask, g, jsonify, request
from pymongo import MongoClient
from pymongo.errors import AutoReconnect, PyMongoError
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

# ---------------------------------------------------------------------------
# Drain state — set by POST /drain, read by before_request and drain monitor
# ---------------------------------------------------------------------------

_draining = False
_active_requests = 0
_last_user_request_ts = time.monotonic()
_active_requests_lock = threading.Lock()
_SKIP_COUNTING = frozenset({"/health", "/drain"})

vip_data_lock = threading.Lock()
vip_data_per_domain = {
    "lan1": "10.0.0.254",
    "lan2": "10.0.1.254",
}


# ---------------------------------------------------------------------------
# MongoDB client — one singleton MongoClient per LAN.
# maxPoolSize=1 ensures exactly one DNAT selection per LAN per edge server.
# maxIdleTimeMS matches VIP_IDLE_TIMEOUT so the driver closes the socket
# at the same cadence as the SDN controller removes idle DNAT rules.
# ---------------------------------------------------------------------------

_clients_lock = threading.Lock()
_mongo_clients: dict[str, MongoClient] = {}
_retired_clients: list[tuple[float, str, MongoClient]] = [] # [retired_ts, lan, client]


def _close_retired_clients() -> None:
    cutoff = time.monotonic() - MONGO_CLIENT_RETIRE_GRACE_S
    ready: list[tuple[str, MongoClient]] = []
    with _clients_lock:
        still_retired: list[tuple[float, str, MongoClient]] = []
        for retired_ts, lan, client in _retired_clients:
            if retired_ts <= cutoff:
                ready.append((lan, client))
            else:
                still_retired.append((retired_ts, lan, client))
        _retired_clients[:] = still_retired

    for lan, client in ready:
        try:
            client.close()
        except Exception as exc:  # pragma: no cover - defensive close path
            log.warning("retired MongoClient close failed for %s: %s", lan, exc)


def _retire_client(lan: str) -> None:
    retired = False
    with _clients_lock:
        old = _mongo_clients.pop(lan, None)
        if old is not None:
            _retired_clients.append((time.monotonic(), lan, old))
            retired = True

    if retired:
        log.info(
            "Retired MongoClient for %s; future requests will reconnect after %.0fs grace",
            lan,
            MONGO_CLIENT_RETIRE_GRACE_S,
        )
    _close_retired_clients()


def _retired_client_sweeper() -> None:
    sweep_interval = max(1.0, min(MONGO_CLIENT_RETIRE_GRACE_S / 2.0, 5.0))
    while True:
        time.sleep(sweep_interval)
        _close_retired_clients()


def _get_client(lan: str) -> MongoClient:
    _close_retired_clients()
    with _clients_lock:
        client = _mongo_clients.get(lan)
        if client is None:
            with vip_data_lock:
                vip_ip = vip_data_per_domain[lan]
            url = f"mongodb://{vip_ip}:{DB_PORT}/"
            client = MongoClient(
                url, maxPoolSize=1, maxIdleTimeMS=MAX_IDLE_MS,
                serverSelectionTimeoutMS=3000,
                socketTimeoutMS=15000,
                directConnection=True,
            )
            _mongo_clients[lan] = client
            log.info("Created MongoClient for %s → %s (maxIdleTimeMS=%d)", lan, url, MAX_IDLE_MS)
        return client


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


class CircuitOpenError(PyMongoError):
    """Raised when the circuit breaker for a LAN is open."""
    pass


_circuit_breakers: dict[str, _CircuitBreaker] = {}


def _get_breaker(lan: str) -> _CircuitBreaker:
    with _clients_lock:
        breaker = _circuit_breakers.get(lan)
        if breaker is None:
            breaker = _CircuitBreaker()
            _circuit_breakers[lan] = breaker
        return breaker


@contextmanager
def timed_db(lan: str):
    """Yields a MongoDB database handle for the given LAN and accumulates
    elapsed time into ``g.time_db_elapsed`` so the telemetry layer can
    report T_dados correctly.

    On a connection-level failure (e.g. RST after a DNAT rule change) the
    stale client is evicted so the next request creates a fresh connection
    to the VIP rather than retrying on the dead socket.

    A per-LAN circuit breaker prevents threads from blocking on a known-dead
    server: if the circuit is OPEN, a ``CircuitOpenError`` is raised immediately
    instead of waiting for the 3 s server-selection timeout.
    """
    breaker = _get_breaker(lan)
    if not breaker.check():
        raise CircuitOpenError(f"circuit open for {lan}")
    # Tag every wrapped cached_collection() access made inside this block
    # with the owning LAN. Token is returned by set() and restored in finally
    # so nested timed_db() calls unwind correctly.
    owner_token = _owner_lan.set(lan)
    t0 = time.monotonic()
    try:
        try:
            yield _get_client(lan)[DB_NAME]
            breaker.record_success()
        except AutoReconnect:
            breaker.record_failure()
            _retire_client(lan)
            log.warning("timed_db: retired stale MongoClient for %s after connection failure", lan)
            raise
    finally:
        _owner_lan.reset(owner_token)
        elapsed = time.monotonic() - t0
        g.time_db_elapsed = getattr(g, "time_db_elapsed", 0.0) + elapsed
        per_lan = getattr(g, "time_db_per_lan", None)
        if per_lan is None:
            per_lan = {}
            g.time_db_per_lan = per_lan
        per_lan[lan] = per_lan.get(lan, 0.0) + elapsed


# ---------------------------------------------------------------------------
# Drain guard — registered before init_telemetry so it has priority
# ---------------------------------------------------------------------------

def get_drain_state() -> str:
    return "draining" if _draining else "active"

@app.before_request
def _drain_guard():
    global _active_requests, _last_user_request_ts
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
    body = request.get_json(silent=True) or {}
    with vip_data_lock:
        vip_data_per_domain.update(body)
    for lan in body:
        _retire_client(lan)
    return jsonify({"message": "VIP data updated", "vip_data": vip_data_per_domain}), 200


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
        log.error("device_latest error: %s", exc)
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
        log.error("anomalies error: %s", exc)
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
        for lan in vip_data_per_domain:
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
        log.error("dashboard error: %s", exc)
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
            _retire_client(lan)
            log.debug(
                "T_dados[%s]=%.1fms > \u03c4=%.1fms \u2014 retired client to force reconnection",
                lan, time_ms, TAU_DADOS_MS,
            )
    return response


# ---------------------------------------------------------------------------
# Drain monitor — background thread that fires drain_complete and self-exits
# ---------------------------------------------------------------------------

# Shared sender: reused by telemetry and drain monitor so both emit through
# the same ZMQ PUSH connection.
_metric_sender = ZmqMetricSender()
threading.Thread(
    target=_retired_client_sweeper,
    daemon=True,
    name="mongo-client-sweeper",
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
        "  maxIdleTimeMS=%d  tau_dados=%.0fms",
        BIND_HOST, BIND_PORT, LAN_ID, DB_NAME, vip_data_per_domain,
        MAX_IDLE_MS, TAU_DADOS_MS,
    )
    app.run(host=BIND_HOST, port=BIND_PORT, threaded=True)
