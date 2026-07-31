import logging
import os
import threading
import time

from flask import Flask, g, abort, request

from db_monitor import register as _register_db_monitor

# Register the pymongo CommandListener before any MongoClient is created.
_register_db_monitor()

from control_plane_routes import register_control_plane_routes
from edge_server_config import CONFIG
from edge_server_process_state import EdgeServerProcessState, SKIP_COUNTING_PATHS
from edge_request_lifecycle import (
    register_post_telemetry_request_hooks,
    register_pre_telemetry_request_hooks,
)
from monitoring_workload_routes import register_monitoring_workload_routes
from telemetry import init_telemetry, _get_server_mac
from vip_data_mongo_runtime import (
    snapshot_normal_vip_config,
    start_epoch_housekeeping,
    _get_write_client,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(threadName)s] %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)

app = Flask(__name__)
process_state = EdgeServerProcessState(CONFIG)

# Request hooks are split into pre/post telemetry phases on purpose. Flask runs
# after_request hooks in reverse registration order, so the post-telemetry
# hooks below execute before telemetry emission and can finalize request-local
# lease metadata without changing the existing serving semantics.
register_pre_telemetry_request_hooks(app, CONFIG, process_state)
register_control_plane_routes(app, process_state)
register_monitoring_workload_routes(app, CONFIG, process_state)
start_epoch_housekeeping()
init_telemetry(
    app,
    sender=process_state.metric_sender,
    get_drain_state=process_state.get_drain_state,
)
register_post_telemetry_request_hooks(app, process_state)


@app.after_request
def _add_backend_identity(response):
    """Stamp every response with the container identity so the traffic
    generator can log which backend served each request.

    Uses the Docker container hostname (e.g. edge_server_lan1_dyn2) as the
    stable identifier.  The controller also knows container names from spawn
    events, enabling cross-referencing for TFR (Time-to-First-Response)
    computation.

    RQ3 flow isolation: when EDGE_FLOW_ISOLATION=1 and the request is a real
    workload request (not /health, /drain, /ready), emit a ``request_complete``
    control event from a background thread (after the response is flushed) so
    the controller deletes this client's VIP_SERVER flow → one fresh
    backend-selection event per request. client_ip is captured in-context; the
    thread only calls metric_sender.send()."""
    backend_id = os.environ.get("CONTAINER_NAME", os.environ.get("HOSTNAME", "unknown"))
    response.headers["X-Backend-ID"] = backend_id
    if os.environ.get("EDGE_FLOW_ISOLATION", "0") == "1":
        if request.path not in SKIP_COUNTING_PATHS:
            client_ip = request.remote_addr
            server_mac = _get_server_mac()
            threading.Thread(
                target=_emit_request_complete,
                args=(process_state, client_ip, server_mac),
                daemon=True,
            ).start()
    return response


def _emit_request_complete(process_state, client_ip: str, server_mac: str) -> None:
    """Emit a request_complete control event (RQ3 flow isolation).

    Runs in a background thread after the response is flushed; never touches
    the (torn-down) request context.
    """
    try:
        process_state.metric_sender.send({
            "event_type": "request_complete",
            "server_id": server_mac,
            "client_ip": client_ip,
            "ts": time.time(),
        })
    except Exception:
        log.exception("[flow-isolation] request_complete emission failed")


def _run_app_ready_probe(process_state, config) -> None:
    """RQ3 readiness: mark the app ready after a real MongoDB round-trip.

    The single, testable readiness predicate (D2): /ready returns 200 iff
    ``process_state.app_ready`` is True, set here after a successful
    ``ping`` against the primary within ``READINESS_APP_MAX_S``.
    """
    # > controller READINESS_PROBE_MAX_S (120) so the edge never gives up
    # before the controller would abandon the backend.
    max_wait_s = float(os.environ.get("READINESS_APP_MAX_S", "180"))
    deadline = time.monotonic() + max_wait_s
    while time.monotonic() < deadline:
        try:
            _get_write_client(config.lan_id).admin.command("ping")
            process_state.mark_app_ready()
            log.info("app ready: MongoDB ping OK (lan=%s)", config.lan_id)
            return
        except Exception:
            time.sleep(1.0)
    log.error("app NOT ready: MongoDB ping failed within %.0fs", max_wait_s)


if __name__ == "__main__":
    log.info(
        "Starting edge-server on %s:%d  lan=%s  db_name=%s  vip_data=%s"
        "  maxIdleTimeMS=%d  tau_dados=%.0fms",
        CONFIG.bind_host,
        CONFIG.bind_port,
        CONFIG.lan_id,
        CONFIG.db_name,
        snapshot_normal_vip_config(),
        CONFIG.max_idle_ms,
        CONFIG.tau_dados_ms,
    )
    # RQ3 readiness probe — background thread marks app_ready after a real
    # MongoDB round-trip so the controller's /ready gate can admit this node.
    threading.Thread(
        target=_run_app_ready_probe, args=(process_state, CONFIG), daemon=True,
    ).start()
    app.run(host=CONFIG.bind_host, port=CONFIG.bind_port, threaded=True)