import os
import statistics
import threading
import time
import logging

import zmq

WINDOW_S = float(os.environ.get("WINDOW_S", "10"))
NETWORK_ID = os.environ["NETWORK_ID"]
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")

logger = logging.getLogger("aggregator")

ctx = zmq.Context()

pull = ctx.socket(zmq.PULL)
_pull_addr = os.environ.get("PULL_ADDR", "tcp://0.0.0.0:5555")
pull.bind(_pull_addr)
logger.info("PULL socket bound to %s", _pull_addr)

pub = ctx.socket(zmq.PUB)
_pub_addr = os.environ.get("PUB_ADDR", "tcp://0.0.0.0:5556")
pub.bind(_pub_addr)
logger.info("PUB socket bound to %s", _pub_addr)

_buffer: list = []
_lock = threading.Lock()


def _receive_loop() -> None:
    logger.info("Receive loop started")
    while True:
        event = pull.recv_json()
        logger.debug("Received event from server_id=%s event_type=%s", event.get("server_id"), event.get("event_type"))
        etype = event.get("event_type")
        if etype in ("drain_complete", "rs_secondary_ready"):
            # Forward control events immediately as a mini-summary — do not
            # buffer into the aggregation window.  The controller needs these
            # signals as fast as possible.
            mini = {
                "network_id":     NETWORK_ID,
                "window_end":     time.time(),
                "servers":        {},
                "storage_servers": {},
                "control_events": [event],
            }
            logger.info("%s received for server_id=%s — publishing mini-summary", etype, event.get("server_id"))
            pub.send_json(mini)
            continue  # do not also buffer into the window
        with _lock:
            _buffer.append(event)


def _publish_loop() -> None:
    logger.info("Publish loop started: network_id=%s window=%.1fs", NETWORK_ID, WINDOW_S)
    while True:
        time.sleep(WINDOW_S)
        with _lock:
            window, _buffer[:] = list(_buffer), []

        last_seen: dict[str, float] = {}
        for event in window:
            sid = event.get("server_id")
            ts  = event.get("ts", 0.0)
            if sid and ts > last_seen.get(sid, 0.0):
                last_seen[sid] = ts

        if not window:
            logger.debug("Window empty, skipping publish")
            continue

        http_events  = [e for e in window if e.get("event_type") not in ("mongo_stats", "heartbeat")]
        mongo_events = [e for e in window if e.get("event_type") == "mongo_stats"]

        # ── Per-server HTTP stats ─────────────────────────────────────────────
        by_server: dict = {}
        for event in http_events:
            by_server.setdefault(event["server_id"], []).append(event)

        servers = {}
        for server_id, events in by_server.items():
            time_totals = [event["time_total_ms"] for event in events]
            time_db     = [event["time_db_ms"] for event in events]
            time_procs  = [event["time_total_ms"] - event["time_db_ms"] for event in events]
            errors      = sum(1 for event in events if event["status_code"] >= 500)
            servers[server_id] = {
                "avg_time_total_ms": statistics.mean(time_totals),
                "avg_time_db_ms":    statistics.mean(time_db),
                "avg_time_proc_ms":  statistics.mean(time_procs),
                "request_count":     len(events),
                "error_rate":        errors / len(events),
                "avg_cpu_percent":   statistics.mean([event["cpu_percent"] for event in events]),
                "avg_ram_used_mb":   statistics.mean([event["ram_used_mb"] for event in events]),
                "last_report_ts":    last_seen.get(server_id, 0.0),
            }
            logger.debug(
                "server_id=%s requests=%d error_rate=%.2f avg_total_ms=%.1f avg_db_ms=%.1f",
                server_id, len(events), errors / len(events),
                statistics.mean(time_totals), statistics.mean(time_db),
            )

        # ── Per-server mongo stats ────────────────────────────────────────────
        by_storage: dict = {}
        for event in mongo_events:
            by_storage.setdefault(event["server_id"], []).append(event)

        storage_servers = {}
        for server_id, events in by_storage.items():
            lags = [e["repl_lag_s"] for e in events if e.get("repl_lag_s") is not None]
            storage_servers[server_id] = {
                "avg_repl_lag_s":  statistics.mean(lags) if lags else None,
                "avg_connections": statistics.mean([e["connections_current"] for e in events]),
                "avg_cpu_percent": statistics.mean([e["cpu_percent"] for e in events]),
                "avg_ram_used_mb": statistics.mean([e["ram_used_mb"] for e in events]),
                "sample_count":    len(events),
                "last_report_ts":  last_seen.get(server_id, 0.0),
                "member_state":    events[-1].get("member_state"),
            }

        # ── Heartbeat-only nodes (idle but alive) ─────────────────────────────
        heartbeats = [e for e in window if e.get("event_type") == "heartbeat"]
        for hb in heartbeats:
            sid = hb.get("server_id")
            if not sid:
                continue
            if "connections_current" in hb:          # storage sidecar heartbeat
                if sid not in storage_servers:
                    storage_servers[sid] = {
                        "avg_repl_lag_s":  hb.get("repl_lag_s"),
                        "avg_connections": float(hb.get("connections_current", 0)),
                        "avg_cpu_percent": hb.get("cpu_percent", 0.0),
                        "avg_ram_used_mb": hb.get("ram_used_mb", 0.0),
                        "sample_count":    0,
                        "last_report_ts":  last_seen[sid],
                        "member_state":    hb.get("member_state"),
                    }
            else:                                     # edge server heartbeat
                if sid not in servers:
                    servers[sid] = {
                        "avg_time_total_ms": 0.0,
                        "avg_time_db_ms":    0.0,
                        "avg_time_proc_ms":  0.0,
                        "request_count":     0,
                        "error_rate":        0.0,
                        "avg_cpu_percent":   hb.get("cpu_percent", 0.0),
                        "avg_ram_used_mb":   hb.get("ram_used_mb", 0.0),
                        "last_report_ts":    last_seen[sid],
                    }

        # ── Domain summary (HTTP only) ────────────────────────────────────────
        if http_events:
            time_procs_all  = [e["time_total_ms"] - e["time_db_ms"] for e in http_events]
            time_dbs_all    = [e["time_db_ms"] for e in http_events]
            cpus_all        = [e["cpu_percent"] for e in http_events]
            time_totals_all = [e["time_total_ms"] for e in http_events]
            rams_all        = [e["ram_used_mb"] for e in http_events]

            avg_time_proc   = statistics.mean(time_procs_all)
            avg_time_db     = statistics.mean(time_dbs_all)
            avg_cpu_percent = statistics.mean(cpus_all)
            peak_time_total = max(time_totals_all)
            total_requests  = len(http_events)

            median_time_proc   = statistics.median(time_procs_all)
            median_time_db     = statistics.median(time_dbs_all)
            median_cpu_percent = statistics.median(cpus_all)
            median_time_total  = statistics.median(time_totals_all)
            median_ram_used_mb = statistics.median(rams_all)
        else:
            avg_time_proc = avg_time_db = avg_cpu_percent = peak_time_total = 0.0
            median_time_proc = median_time_db = median_cpu_percent = 0.0
            median_time_total = median_ram_used_mb = 0.0
            total_requests = 0

        # ── Domain-average storage CPU (across all storage server entries) ────
        storage_cpu_values = [
            ss["avg_cpu_percent"]
            for ss in storage_servers.values()
            if ss.get("avg_cpu_percent") is not None
        ]
        avg_storage_cpu_percent = statistics.mean(storage_cpu_values) if storage_cpu_values else 0.0

        storage_ram_values = [
            ss["avg_ram_used_mb"]
            for ss in storage_servers.values()
            if ss.get("avg_ram_used_mb") is not None
        ]
        median_storage_cpu_percent = statistics.median(storage_cpu_values) if storage_cpu_values else 0.0
        median_storage_ram_used_mb = statistics.median(storage_ram_values) if storage_ram_values else 0.0

        summary = {
            "network_id":      NETWORK_ID,
            "window_end":      time.time(),
            "servers":         servers,
            "storage_servers": storage_servers,
            "control_events":  [],
            "domain_summary": {
                "total_requests":          total_requests,
                "avg_time_proc_ms":        avg_time_proc,
                "avg_time_db_ms":          avg_time_db,
                "average_cpu_percent":     avg_cpu_percent,
                "peak_time_total_ms":      peak_time_total,
                "avg_storage_cpu_percent": avg_storage_cpu_percent,
                "median_cpu_percent":          median_cpu_percent,
                "median_ram_used_mb":          median_ram_used_mb,
                "median_storage_cpu_percent":  median_storage_cpu_percent,
                "median_storage_ram_used_mb":  median_storage_ram_used_mb,
                "median_time_proc_ms":         median_time_proc,
                "median_time_db_ms":           median_time_db,
                "median_time_total_ms":        median_time_total,
            },
        }
        logger.info(
            "Publishing summary: network_id=%s total_requests=%d avg_cpu=%.1f%% peak_total_ms=%.1f",
            NETWORK_ID,
            summary["domain_summary"]["total_requests"],
            summary["domain_summary"]["average_cpu_percent"],
            summary["domain_summary"]["peak_time_total_ms"],
        )
        logger.debug("Full summary: %s", summary)
        pub.send_json(summary)


threading.Thread(target=_receive_loop, daemon=True).start()
_publish_loop()
