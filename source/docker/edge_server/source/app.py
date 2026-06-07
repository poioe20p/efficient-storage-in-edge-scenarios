import logging

from flask import Flask

from db_monitor import register as _register_db_monitor

# Register the pymongo CommandListener before any MongoClient is created.
_register_db_monitor()

from control_plane_routes import register_control_plane_routes
from edge_server_config import CONFIG
from edge_server_process_state import EdgeServerProcessState
from edge_request_lifecycle import (
    register_post_telemetry_request_hooks,
    register_pre_telemetry_request_hooks,
)
from monitoring_workload_routes import register_monitoring_workload_routes
from telemetry import init_telemetry
from vip_data_mongo_runtime import (
    snapshot_normal_vip_config,
    start_epoch_housekeeping,
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
    app.run(host=CONFIG.bind_host, port=CONFIG.bind_port, threaded=True)