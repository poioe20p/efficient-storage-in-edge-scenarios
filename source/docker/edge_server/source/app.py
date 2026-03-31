import logging
import os
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from flask import Flask, g, jsonify, request
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from telemetry import init_telemetry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_config_lock = threading.Lock()
_config: dict = {
    "db_url": os.environ.get("DB_URL", "mongodb://10.0.0.200:27018/"),
}

BIND_HOST: str = os.environ.get("BIND_HOST", "0.0.0.0")
BIND_PORT: int = int(os.environ.get("BIND_PORT", "5000"))
DB_NAME:   str = os.environ.get("DB_NAME", "edge_platform")
REGION:    str = os.environ.get("REGION", "lan1")
DATA_TIER: str = os.environ.get("DATA_TIER", "0")

vip_data_lock = threading.Lock()
vip_data_per_domain = {
    "lan1": "10.0.0.200",
    "lan2": "10.0.1.200",
}


def get_db_url() -> str:
    with _config_lock:
        return _config["db_url"]


def set_db_url(value: str) -> None:
    with _config_lock:
        _config["db_url"] = value
    # No persistent client to reset — each request opens its own connection.


# ---------------------------------------------------------------------------
# MongoDB client — one connection per HTTP request.
# Each request creates a fresh TCP SYN to VIP_Dados so the SDN controller
# can intercept and DNAT it to whichever storage tier is currently active.
# The client lives in Flask's per-request context (g) and is closed in
# teardown_request, guaranteeing the TCP socket is gone before the next
# request from the same client.
# ---------------------------------------------------------------------------

def _get_db():
    """Return the per-request MongoDB database handle, creating it on first use."""
    if not hasattr(g, "mongo_client"):
        g.mongo_client = MongoClient(get_db_url(), serverSelectionTimeoutMS=3000)
    return g.mongo_client[DB_NAME]


@app.teardown_request
def _close_mongo(_exc):
    client = g.pop("mongo_client", None)
    if client is not None:
        client.close()


@contextmanager
def timed_db():
    """Yields the per-request MongoDB database handle and accumulates elapsed
    time into ``g.time_db_elapsed`` so the telemetry layer can report
    T_dados correctly."""
    t0 = time.monotonic()
    try:
        yield _get_db()
    finally:
        g.time_db_elapsed = getattr(g, "time_db_elapsed", 0.0) + (time.monotonic() - t0)


# ---------------------------------------------------------------------------
# Control-plane routes (used by the SDN controller)
# ---------------------------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/config/db_url", methods=["PUT"])
def config_set_db_url():
    body = request.get_json(silent=True) or {}
    new_url = body.get("db_url")
    if not new_url or not isinstance(new_url, str):
        return jsonify({"error": "'db_url' string field required"}), 400
    old_url = get_db_url()
    set_db_url(new_url)
    log.info("PUT /config/db_url — changed from=%s to=%s", old_url, new_url)
    return jsonify({"db_url": new_url}), 200


@app.route("/vip_data", methods=["PUT"])
def set_vip_data():
    body = request.get_json(silent=True) or {}
    with vip_data_lock:
        vip_data_per_domain.update(body)
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

    try:
        with timed_db() as db:
            doc = db.sensor_reports.find_one({"_id": device_id})

        if doc is None:
            return jsonify({"error": "device not found", "device_id": device_id}), 404

        threshold_override = None
        if node_id != "unknown":
            with timed_db() as db:
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
            "region_served":   REGION,
            "timestamp":       datetime.now(timezone.utc),
            "latency_ms":      round(g.time_db_elapsed * 1000, 2),
            "served_from_tier": DATA_TIER,
        }
        try:
            with timed_db() as db:
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
      region  — region to filter query_events (default: REGION env var)
      window  — look-back window in hours (default: 1)
    """
    region   = request.args.get("region", REGION)
    window_h = float(request.args.get("window", "1"))
    since_dt = datetime.fromtimestamp(
        time.time() - window_h * 3600, tz=timezone.utc
    )

    try:
        with timed_db() as db:
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
        with timed_db() as db:
            status_map = {
                d["_id"]: d
                for d in db.sensor_reports.find(
                    {"_id": {"$in": device_ids}},
                    {"payload.status": 1, "payload.value": 1, "device_type": 1, "tags": 1},
                )
            }

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

    try:
        with timed_db() as db:
            registry = db.device_registry.find_one({"_id": node_id})

        if registry is None:
            return jsonify({"error": "node not found", "node_id": node_id}), 404

        subscribed_tags = registry.get("subscribed_tags", [])

        with timed_db() as db:
            devices = list(
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

init_telemetry(app)

if __name__ == "__main__":
    log.info(
        "Starting edge-server on %s:%d  db=%s/%s  region=%s",
        BIND_HOST, BIND_PORT, get_db_url(), DB_NAME, REGION,
    )

    # log.info(
    #     "Starting edge-server"
    # )
    app.run(host=BIND_HOST, port=BIND_PORT, threaded=True)
