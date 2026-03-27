import logging
import os
import threading
import time

from flask import Flask, jsonify, request
from telemetry import init_telemetry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

app = Flask(__name__)

_config_lock = threading.Lock()
_config: dict = {
    "db_url": os.environ.get("DB_URL", "mongodb://10.0.0.4:27017/test"),
}

BIND_HOST: str = os.environ.get("BIND_HOST", "0.0.0.0")
BIND_PORT: int = int(os.environ.get("BIND_PORT", "5000"))

# TO-DO: THIS NEEDS TO BE THREAD-SAFE
vip_data_lock = threading.Lock()
vip_data_per_domain = {
    "lan_1": "10.0.0.200",
    "lan_2": "10.0.1.200"
}

def get_db_url() -> str:
    with _config_lock:
        return _config["db_url"]


def set_db_url(value: str) -> None:
    with _config_lock:
        _config["db_url"] = value


@app.route("/health", methods=["GET"])
def health():
    log.info("health check")
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


@app.route("/data", methods=["GET"])
def get_data():
    db_url = get_db_url()
    log.info("GET /data — db_url=%s", db_url)
    # TODO: query MongoDB via db_url and return results
    return jsonify({"message": "not implemented", "db_url": db_url}), 501


@app.route("/data", methods=["POST"])
def post_data():
    db_url = get_db_url()
    body = request.get_json(silent=True) or {}
    log.info("POST /data — db_url=%s body=%s", db_url, body)
    # TODO: insert body into MongoDB via db_url
    return jsonify({"message": "not implemented", "db_url": db_url}), 501

@app.route("/vip_data", methods=["PUT"])
def set_vip_data():
    body = request.get_json(silent=True) or {}
    # it should perform a python dict update with the body
    with vip_data_lock:
        vip_data_per_domain.update(body)
    return jsonify({"message": "VIP data updated", "vip_data": vip_data_per_domain}), 200


@app.route("/wait_time", methods=["POST"])
def post_wait_time():
    body = request.get_json(silent=True) or {}
    wait_time_ms = body.get("wait_time_ms")
    if not isinstance(wait_time_ms, (int, float)):
        return jsonify({"error": "'wait_time_ms' field must be a number"}), 400
    log.info("POST /wait_time — simulating wait of %d ms", wait_time_ms)
    time.sleep(wait_time_ms / 1000.0)
    return jsonify({"message": f"Simulating wait of {wait_time_ms} ms"}), 200

init_telemetry(app)


if __name__ == "__main__":
    log.info("Starting edge-server API on %s:%d (threaded=True, db_url=%s)", BIND_HOST, BIND_PORT, get_db_url())
    app.run(host=BIND_HOST, port=BIND_PORT, threaded=True)
