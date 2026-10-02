import logging
import os
import threading
import time

from flask import Flask, request

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

# RQ3 soundness (default off): while time.time() < this value, every workload
# request fails with a deterministic HTTP 503 (set below when
# EDGE_READY_SEMANTIC_LIE_S > 0; 0.0 = inert).
_RQ3_SEMANTIC_LIE_UNTIL = 0.0

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
            # WSGI REMOTE_PORT is the client's ephemeral source port (DNAT
            # only rewrites the destination), so the controller can scope the
            # flow delete to this exact connection when
            # VIP_SERVER_PER_CONNECTION_FLOWS=1. 0 = unavailable (ignored).
            client_port = int(request.environ.get("REMOTE_PORT") or 0)
            server_mac = _get_server_mac()
            threading.Thread(
                target=_emit_request_complete,
                args=(process_state, client_ip, client_port, server_mac),
                daemon=True,
            ).start()
    return response


@app.before_request
def _rq3_semantic_lie_gate():
    """RQ3 soundness (default off): deterministic false-claim window.

    While ``EDGE_READY_SEMANTIC_LIE_S`` > 0 and within the window set at
    bind, every workload request — all paths except the probe paths in
    ``SKIP_COUNTING_PATHS`` — fails with a well-formed HTTP 503 while /ready
    keeps answering 200: the readiness predicate itself lies. Registered
    after the telemetry hooks so request accounting still runs; the normal
    ``after_request`` path still stamps ``X-Backend-ID``.
    """
    if _RQ3_SEMANTIC_LIE_UNTIL and time.time() < _RQ3_SEMANTIC_LIE_UNTIL:
        if request.path not in SKIP_COUNTING_PATHS:
            return "rq3_semantic_lie", 503


def _emit_request_complete(process_state, client_ip: str, client_port: int,
                           server_mac: str) -> None:
    """Emit a request_complete control event (RQ3 flow isolation).

    Runs in a background thread after the response is flushed; never touches
    the (torn-down) request context. ``client_port`` is the connection's
    source port (per-connection flow delete); 0 if unavailable.
    """
    try:
        process_state.metric_sender.send({
            "event_type": "request_complete",
            "server_id": server_mac,
            "client_ip": client_ip,
            "client_port": client_port,
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


def _apply_request_concurrency_bound(server) -> None:
    """Bound the number of concurrent request threads (2026-09-27).

    werkzeug's threaded server spawns one handler thread per connection with
    NO cap. Under an overload/retry-storm episode (extension rate-15 runs)
    live threads grew into the thousands -> 43 GB virtual / memcg OOM at the
    512 MB cap (B-P2r, 2026-09-27: both edges killed, service lost).

    The gate acquires a slot in the ACCEPT loop before a handler thread is
    spawned, so excess connections wait in the kernel accept backlog instead
    of consuming thread/memory. Replaces ThreadingMixIn.process_request with
    a bounded, faithful reimplementation. ``EDGE_MAX_CONCURRENCY`` (default
    256; 0 disables).

    Fix 3 (2026-09-27): the 1024 cap still allowed ~1024 live threads with
    8 MB stacks (~300 MB resident) to fill the 512 MB memcg during
    rq2_ext_b_dbcb_fix2 (n1 OOM-killed 09:10:28; total-vm 8.6 GB; buffer
    only ~50 MB). Default lowered to 256 and worker stacks shrunk via
    ``EDGE_THREAD_STACK_SIZE_KB`` (default 1024; 0 = leave process default).
    """
    limit = int(os.environ.get("EDGE_MAX_CONCURRENCY", "256"))
    stack_kb = int(os.environ.get("EDGE_THREAD_STACK_SIZE_KB", "1024"))
    if stack_kb > 0:
        try:
            threading.stack_size(stack_kb * 1024)
            log.info("request-thread stack size set to %d KB", stack_kb)
        except (ValueError, RuntimeError) as exc:
            log.warning("request-thread stack size %d KB rejected: %s", stack_kb, exc)
    if limit <= 0:
        log.info("request-concurrency bound disabled (EDGE_MAX_CONCURRENCY=%d)", limit)
        return
    gate = threading.BoundedSemaphore(limit)
    state = {"blocked": 0, "logged": False}
    worker = server.process_request_thread

    def process_request(request, client_address):
        if not gate.acquire(blocking=False):
            state["blocked"] += 1
            if not state["logged"]:
                state["logged"] = True
                log.warning(
                    "request-concurrency gate engaged: waiting for a free request slot (limit=%d)",
                    limit,
                )
            gate.acquire()
        try:
            t = threading.Thread(
                target=process_request_thread,
                args=(request, client_address),
                daemon=getattr(server, "daemon_threads", True),
            )
            t.start()
        except BaseException:
            gate.release()
            try:
                server.shutdown_request(request)
            except Exception:
                pass
            raise

    def process_request_thread(request, client_address):
        try:
            worker(request, client_address)
        finally:
            gate.release()

    server.process_request = process_request
    server.process_request_thread = process_request_thread
    log.info("request-concurrency bound active: EDGE_MAX_CONCURRENCY=%d", limit)


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
    # ── RQ3 readiness/servability fix (2026-08-06) ────────────────────────
    # Bind the HTTP server synchronously with werkzeug.serving.make_server
    # (instead of the opaque app.run()), then start the accept loop in a
    # background thread, and only THEN start the app_ready probe. This makes
    # the readiness predicate mean actual servability: the app_ready event and
    # /ready 200 can only fire once the socket is bound and the server is
    # accepting connections. Previously app.run()'s dev-server reloader path
    # intermittently took ~10 s to bind after "Serving Flask app", so the
    # event (fired on the MongoDB-ping predicate) preceded servability by up
    # to ~10 s — the RQ3 direct-arm handover artifact (http=000 fast-fails,
    # identity-check violations, admitted→first-flow lag), which also
    # contaminated RQ1/RQ2 runs (no readiness gate). Fix verified: bind delay
    # ~0 and event strictly after bind.
    from werkzeug.serving import make_server
    # ── RQ3 soundness knob: premature readiness claim (default off) ───────
    # EDGE_READY_PREMATURE_S=N > 0 deterministically re-introduces the
    # pre-2026-08-06 ordering: the readiness claim (flag set + app_ready
    # event, fired on the Mongo-ping predicate) precedes servability by
    # exactly N s; the socket bind is deferred. N=0 keeps the bind-before-
    # claim fix unchanged.
    _premature_s = 0
    try:
        _premature_s = max(
            0, int(os.environ.get("EDGE_READY_PREMATURE_S", "0") or 0)
        )
    except ValueError:
        log.warning("EDGE_READY_PREMATURE_S is not an int — treating as 0")
    if _premature_s > 0:
        log.info(
            "RQ3 premature claim: EDGE_READY_PREMATURE_S=%d (claim precedes bind)",
            _premature_s,
        )
        # Probe starts BEFORE bind so the claim can outrun servability.
        threading.Thread(
            target=_run_app_ready_probe, args=(process_state, CONFIG),
            daemon=True,
        ).start()
        try:
            _claim_max_s = float(os.environ.get("READINESS_APP_MAX_S", "180"))
        except ValueError:
            _claim_max_s = 180.0
            log.warning("READINESS_APP_MAX_S is not a float — using 180 s")
        _claim_deadline = time.monotonic() + _claim_max_s
        while not process_state.app_ready and time.monotonic() < _claim_deadline:
            time.sleep(0.05)
        _t_claim = time.time()
        if not process_state.app_ready:
            log.warning(
                "RQ3 premature claim: no claim within %.0fs (Mongo ping did not "
                "succeed) — binding without a premature claim",
                _claim_max_s,
            )
        log.info(
            "READINESS_CLAIM lan=%s premature_s=%d claimed=%d ts=%.3f",
            CONFIG.lan_id, _premature_s, int(process_state.app_ready), _t_claim,
        )
        time.sleep(_premature_s)
    # ── bind-delay diagnostic (temp, 2026-08-06) ──────────────────────────
    # Times the make_server sub-steps so a residual ~10 s intermittent bind
    # stall (seen during active runs) can be attributed: getaddrinfo (DNS) vs
    # importlib.metadata (disk) vs socket bind+listen. Behavior-neutral.
    import socket as _socket
    _t0 = time.perf_counter()
    _ai = _socket.getaddrinfo(
        CONFIG.bind_host, CONFIG.bind_port, _socket.AF_INET,
        _socket.SOCK_STREAM, _socket.IPPROTO_TCP,
    )
    _t1 = time.perf_counter()
    import importlib.metadata as _im
    _im.version("werkzeug")
    _t2 = time.perf_counter()
    server = make_server(
        CONFIG.bind_host, CONFIG.bind_port, app, threaded=True,
    )
    _t_bind = time.time()
    _t3 = time.perf_counter()
    log.info(
        "bind-timing getaddrinfo=%.3fs importlib.metadata=%.3fs make_server(bind+listen)=%.3fs total=%.3fs",
        _t1 - _t0, _t2 - _t1, _t3 - _t2, _t3 - _t0,
    )
    _apply_request_concurrency_bound(server)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    log.info("edge-server listening: http://%s:%d", CONFIG.bind_host, CONFIG.bind_port)
    if _premature_s > 0:
        log.info(
            "READINESS_BIND lan=%s premature_s=%d bind_ts=%.3f deferral_s=%.3f",
            CONFIG.lan_id, _premature_s, _t_bind, _t_bind - _t_claim,
        )
    # ── RQ3 soundness knob: semantic lie window (default off) ─────────────
    # EDGE_READY_SEMANTIC_LIE_S=S > 0 makes every workload request fail
    # deterministically (HTTP 503) for S s counted from bind while /ready
    # keeps answering normally — the readiness predicate itself lies.
    _lie_s = 0
    try:
        _lie_s = max(0, int(os.environ.get("EDGE_READY_SEMANTIC_LIE_S", "0") or 0))
    except ValueError:
        log.warning("EDGE_READY_SEMANTIC_LIE_S is not an int — treating as 0")
    if _lie_s > 0:
        _RQ3_SEMANTIC_LIE_UNTIL = _t_bind + _lie_s
        log.info(
            "RQ3 semantic lie active: EDGE_READY_SEMANTIC_LIE_S=%d until=%.3f",
            _lie_s, _RQ3_SEMANTIC_LIE_UNTIL,
        )
    if _premature_s <= 0:
        # RQ3 readiness probe — background thread marks app_ready after a real
        # MongoDB round-trip so the controller's /ready gate can admit this
        # node. Started only after the socket is bound so the event cannot
        # precede servability (the default, fixed ordering).
        threading.Thread(
            target=_run_app_ready_probe, args=(process_state, CONFIG),
            daemon=True,
        ).start()
    # Keep the main thread alive; serve_forever runs in its own daemon thread.
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.shutdown()