import os
import time
from abc import ABC, abstractmethod

import psutil
import zmq
from flask import Flask, g, request

SERVER_ID: str = os.environ.get("SERVER_ID", "unknown")


def _aggregator_addr_from_lan() -> str:
    """Derive the aggregator ZMQ PULL address from the LAN_ID env var (e.g. "lan1")."""
    lan_id = os.environ.get("LAN_ID", "")
    if not lan_id.startswith("lan"):
        return ""
    subnet_third_octet = int(lan_id[3:]) - 1  # lan1 → 10.0.0.x, lan2 → 10.0.1.x
    return f"tcp://10.0.{subnet_third_octet}.5:5555"


class MetricSender(ABC):
    @abstractmethod
    def send(self, event: dict) -> None: ...


class ZmqMetricSender(MetricSender):
    def __init__(self) -> None:
        addr = os.environ.get("AGGREGATOR_PULL_ADDR", "") or _aggregator_addr_from_lan()
        self._sock: zmq.Socket | None = None
        if addr:
            ctx = zmq.Context.instance()
            self._sock = ctx.socket(zmq.PUSH)
            self._sock.connect(addr)

    def send(self, event: dict) -> None:
        if self._sock is None:
            return
        try:
            self._sock.send_json(event, zmq.NOBLOCK)
        except zmq.Again:
            pass


def _build_event(time_total_ms: float, time_db_ms: float, status_code: int, request_type: str) -> dict:
    return {
        "server_id": SERVER_ID,
        "ts": time.time(),
        "time_total_ms": time_total_ms,
        "time_db_ms": time_db_ms,
        "status_code": status_code,
        "request_type": request_type,
        "cpu_percent": psutil.cpu_percent(),
        "ram_used_mb": psutil.virtual_memory().used / (1024 * 1024),
    }


def init_telemetry(app: Flask, sender: MetricSender | None = None) -> None:
    _sender = sender or ZmqMetricSender()

    @app.before_request
    def _start_timer() -> None:
        g.time_start = time.monotonic()
        g.time_db_elapsed = 0.0

    @app.after_request
    def _emit_metric(response):
        time_total = (time.monotonic() - g.time_start) * 1000
        event = _build_event(
            time_total_ms=time_total,
            time_db_ms=g.time_db_elapsed * 1000,
            status_code=response.status_code,
            request_type="write" if request.method in ("POST", "PUT", "PATCH", "DELETE") else "read",
        )
        print(f"Sending telemetry event: {event}")
        _sender.send(event)
        return response
