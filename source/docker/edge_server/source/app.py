import logging
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from flask import Flask, g, jsonify, request
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from telemetry import init_telemetry, ZmqMetricSender, _get_server_mac

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
TAU_DADOS_MS: float = float(os.environ.get("TAU_DADOS_MS", "5000"))

# ---------------------------------------------------------------------------
# Drain state — set by POST /drain, read by before_request and drain monitor
# ---------------------------------------------------------------------------

_draining = False
_active_requests = 0
_active_requests_lock = threading.Lock()
_SKIP_COUNTING = frozenset({"/health", "/drain"})

vip_data_lock = threading.Lock()
vip_data_per_domain = {
    "lan1": "10.0.0.200",
    "lan2": "10.0.1.200",
}


# ---------------------------------------------------------------------------
# MongoDB client — one singleton MongoClient per LAN.
# maxPoolSize=1 ensures exactly one DNAT selection per LAN per edge server.
# maxIdleTimeMS matches VIP_IDLE_TIMEOUT so the driver closes the socket
# at the same cadence as the SDN controller removes idle DNAT rules.
# ---------------------------------------------------------------------------

_clients_lock = threading.Lock()
_mongo_clients: dict[str, MongoClient] = {}


def _get_client(lan: str) -> MongoClient:
    with _clients_lock:
        client = _mongo_clients.get(lan)
        if client is None:
            with vip_data_lock:
                vip_ip = vip_data_per_domain[lan]
            url = f"mongodb://{vip_ip}:{DB_PORT}/"
            client = MongoClient(
                url, maxPoolSize=1, maxIdleTimeMS=MAX_IDLE_MS,
                serverSelectionTimeoutMS=3000,
                connectTimeoutMS=2000,
                socketTimeoutMS=5000,
                directConnection=True,
            )
            _mongo_clients[lan] = client
            log.info("Created MongoClient for %s → %s (maxIdleTimeMS=%d)", lan, url, MAX_IDLE_MS)
        return client


@contextmanager
def timed_db(lan: str):
    """Yields a MongoDB database handle for the given LAN and accumulates
    elapsed time into ``g.time_db_elapsed`` so the telemetry layer can
    report T_dados correctly."""
    t0 = time.monotonic()
    try:
        yield _get_client(lan)[DB_NAME]
    finally:
        g.time_db_elapsed = getattr(g, "time_db_elapsed", 0.0) + (time.monotonic() - t0)


# ---------------------------------------------------------------------------
# Drain guard — registered before init_telemetry so it has priority
# ---------------------------------------------------------------------------

@app.before_request
def _drain_guard():
    global _active_requests
    g.counted = False # g is the Flask request-global namespace; this flag tracks whether the current request was counted in _active_requests
    if request.path in _SKIP_COUNTING:
        return None  # control-plane routes bypass counting and drain check
    if _draining:
        return jsonify({"status": "draining"}), 503
    with _active_requests_lock:
        _active_requests += 1
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
    """Signal the server to stop accepting new requests and drain in-flight ones.

    The drain monitor thread watches ``_active_requests`` and fires a
    ``drain_complete`` ZMQ event once all in-flight requests finish, then
    terminates the process via ``os._exit(0)``.
    """
    global _draining, _drain_monitor_thread
    _draining = True
    if _drain_monitor_thread is None:
        _drain_monitor_thread = threading.Thread(
            target=_drain_monitor, daemon=True, name="drain-monitor"
        )
        _drain_monitor_thread.start()
    with _active_requests_lock:
        remaining = _active_requests
    log.info("Drain activated — rejecting new requests, %d in-flight", remaining)
    return jsonify({"status": "draining", "active_requests": remaining}), 200


@app.route("/vip_data", methods=["PUT"])
def set_vip_data():
    body = request.get_json(silent=True) or {}
    with vip_data_lock:
        vip_data_per_domain.update(body)
    with _clients_lock:
        for lan in body:
            _mongo_clients.pop(lan, None)
    return jsonify({"message": "VIP data updated", "vip_data": vip_data_per_domain}), 200


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
            doc = db.sensor_reports.find_one({"_id": device_id})

        if doc is None:
            return jsonify({"error": "device not found", "device_id": device_id}), 404

        threshold_override = None
        if node_id != "unknown":
            node_lan = node_id.split("::")[0]
            with timed_db(node_lan) as db:
                registry = db.device_registry.find_one(
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

        # Evaluate alert state against threshold
        value     = doc.get("payload", {}).get("value")
        threshold = threshold_override or doc.get("metadata", {}).get("alert_threshold")
        alert     = bool(threshold is not None and value is not None and value >= threshold)

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
                db.query_events.insert_one(query_event)
        except PyMongoError as exc:
            log.warning("query_events insert failed: %s", exc)

        doc["_id"]   = str(doc["_id"])
        doc["alert"] = alert
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
            hot_devices = list(db.query_events.aggregate(pipeline))

        device_ids = [d["_id"] for d in hot_devices]
        ids_by_lan: dict[str, list[str]] = {}
        for did in device_ids:
            ids_by_lan.setdefault(did.split("::")[0], []).append(did)

        status_map: dict[str, dict] = {}
        for lan, ids in ids_by_lan.items():
            with timed_db(lan) as db:
                for d in db.sensor_reports.find(
                    {"_id": {"$in": ids}},
                    {"payload.status": 1, "payload.value": 1, "device_type": 1, "tags": 1},
                ):
                    status_map[d["_id"]] = d

        for d in hot_devices:
            status = status_map.get(d["_id"], {})
            d["device_id"]   = d.pop("_id")
            d["status"]      = status.get("payload", {}).get("status", "unknown")
            d["value"]       = status.get("payload", {}).get("value")
            d["device_type"] = status.get("device_type")
            d["tags"]        = status.get("tags", [])

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
            registry = db.device_registry.find_one({"_id": node_id})

        if registry is None:
            return jsonify({"error": "node not found", "node_id": node_id}), 404

        subscribed_tags = registry.get("subscribed_tags", [])

        devices: list[dict] = []
        for lan in vip_data_per_domain:
            with timed_db(lan) as db:
                devices.extend(
                    db.sensor_reports.find(
                        {"tags": {"$in": subscribed_tags}},
                        {"_id": 1, "device_type": 1, "tags": 1,
                         "payload": 1, "metadata": 1, "region_origin": 1},
                    )
                )

        # Sort descending by urgency: value / alert_threshold
        def urgency(doc):
            value     = doc.get("payload", {}).get("value")
            threshold = doc.get("metadata", {}).get("alert_threshold")
            if value is None or not threshold:
                return 0.0
            return value / threshold

        devices.sort(key=urgency, reverse=True)
        devices = devices[:limit]

        for d in devices:
            d["_id"] = str(d["_id"])

        return jsonify({
            "node_id":        node_id,
            "subscribed_tags": subscribed_tags,
            "devices":         devices,
        }), 200

    except PyMongoError as exc:
        log.error("dashboard error: %s", exc)
        return jsonify({"error": "database error"}), 503


# ---------------------------------------------------------------------------

@app.after_request
def _check_tdados_threshold(response):
    time_db_ms = getattr(g, "time_db_elapsed", 0.0) * 1000
    if time_db_ms > TAU_DADOS_MS:
        with _clients_lock:
            evicted = list(_mongo_clients.keys())
            _mongo_clients.clear()
        log.debug(
            "T_dados=%.1fms > \u03c4=%.1fms \u2014 evicted clients %s to force reconnection",
            time_db_ms, TAU_DADOS_MS, evicted,
        )
    return response


# ---------------------------------------------------------------------------
# Drain monitor — background thread that fires drain_complete and self-exits
# ---------------------------------------------------------------------------

# Shared sender: reused by telemetry and drain monitor so both emit through
# the same ZMQ PUSH connection.
_metric_sender = ZmqMetricSender()


def _drain_monitor() -> None:
    """Background thread: started by POST /drain. Polls active_requests and,
    once all in-flight requests finish, sends a drain_complete ZMQ event then
    terminates the process via os._exit(0).
    """
    while True:
        time.sleep(0.5)
        with _active_requests_lock:
            remaining = _active_requests
        if remaining <= 0:
            log.info("Drain complete \u2014 all in-flight requests finished, sending drain_complete event")
            _metric_sender.send({
                "event_type": "drain_complete",
                "server_id":  _get_server_mac(),
                "ts":         time.time(),
            })
            time.sleep(0.1)  # small delay to let ZMQ flush the send buffer
            os._exit(0)  # noqa: SLF001 — intentional hard exit after drain

init_telemetry(app, sender=_metric_sender)

if __name__ == "__main__":
    log.info(
        "Starting edge-server on %s:%d  lan=%s  db_name=%s  vip_data=%s"
        "  maxIdleTimeMS=%d  tau_dados=%.0fms",
        BIND_HOST, BIND_PORT, LAN_ID, DB_NAME, vip_data_per_domain,
        MAX_IDLE_MS, TAU_DADOS_MS,
    )
    app.run(host=BIND_HOST, port=BIND_PORT, threaded=True)
