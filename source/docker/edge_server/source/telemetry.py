import os
import time
from abc import ABC, abstractmethod

import psutil
import zmq
from flask import Flask, g, request

SERVER_ID: str = os.environ.get("SERVER_ID", "unknown")


class MetricSender(ABC):
    @abstractmethod
    def send(self, event: dict) -> None: ...


class ZmqMetricSender(MetricSender):
    def __init__(self) -> None:
        addr = os.environ.get("AGGREGATOR_PULL_ADDR", "")
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
