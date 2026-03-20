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
        with _lock:
            _buffer.append(event)


def _publish_loop() -> None:
    logger.info("Publish loop started: network_id=%s window=%.1fs", NETWORK_ID, WINDOW_S)
    while True:
        time.sleep(WINDOW_S)
        with _lock:
            window, _buffer[:] = list(_buffer), []

        if not window:
            logger.debug("Window empty, skipping publish")
            continue

        by_server: dict = {}
        for event in window:
            by_server.setdefault(event["server_id"], []).append(event)

        servers = {}
        for server_id, events in by_server.items():
            time_totals = [event["time_total_ms"] for event in events]
            time_db = [event["time_db_ms"] for event in events]
            time_procs = [event["time_total_ms"] - event["time_db_ms"] for event in events]
            errors = sum(1 for event in events if event["status_code"] >= 500)
            servers[server_id] = {
                "avg_time_total_ms": statistics.mean(time_totals),
                "avg_time_db_ms": statistics.mean(time_db),
                "avg_time_proc_ms": statistics.mean(time_procs),
                "request_count": len(events),
                "error_rate": errors / len(events),
                "avg_cpu_percent": statistics.mean([event["cpu_percent"] for event in events]),
                "avg_ram_used_mb": statistics.mean([event["ram_used_mb"] for event in events]),
            }
            logger.debug(
                "server_id=%s requests=%d error_rate=%.2f avg_total_ms=%.1f avg_db_ms=%.1f",
                server_id, len(events), errors / len(events),
                statistics.mean(time_totals), statistics.mean(time_db),
            )

        avg_time_proc = statistics.mean([event["time_total_ms"] - event["time_db_ms"] for event in window])
        avg_time_db = statistics.mean([event["time_db_ms"] for event in window])
        avg_cpu_percent = statistics.mean([event["cpu_percent"] for event in window])
        summary = {
            "network_id": NETWORK_ID,
            "window_end": time.time(),
            "servers": servers,
            "domain_summary": {
                "total_requests": len(window),
                "avg_time_proc_ms": avg_time_proc,
                "avg_time_db_ms": avg_time_db,
                "average_cpu_percent": avg_cpu_percent,
                "peak_time_total_ms": max(event["time_total_ms"] for event in window),
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
