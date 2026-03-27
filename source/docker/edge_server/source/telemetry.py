import os
import threading
import time
from abc import ABC, abstractmethod

import psutil
import zmq
from flask import Flask, g, request


def _discover_mac() -> str:
    """Return the MAC address of the first non-loopback interface found in sysfs.

    Prefers the interface named by the IFACE env var (default: eth0), but falls
    back to scanning all interfaces so that containers whose primary interface is
    named differently (e.g. eth1, ens3) still report a real MAC.
    """
    preferred = os.environ.get("IFACE", "eth0")
    candidates = [preferred]
    try:
        candidates += sorted(os.listdir("/sys/class/net"))
    except OSError:
        pass
    for iface in candidates:
        if iface == "lo":
            continue
        try:
            with open(f"/sys/class/net/{iface}/address") as f:
                mac = f.read().strip()
            if mac and mac != "00:00:00:00:00:00":
                return mac
        except OSError:
            continue
    return "unknown"


SERVER_MAC: str = _discover_mac()

HEARTBEAT_INTERVAL_S: float = float(os.environ.get("HEARTBEAT_INTERVAL_S", "60"))


def _get_server_mac() -> str:
    """Return the cached MAC, re-discovering if the interface wasn't available yet."""
    global SERVER_MAC
    if SERVER_MAC == "unknown":
        SERVER_MAC = _discover_mac()
    return SERVER_MAC


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


def _heartbeat_loop(sender: MetricSender, last_sent: list[float]) -> None:
    while True:
        time.sleep(1.0)
        if time.monotonic() - last_sent[0] >= HEARTBEAT_INTERVAL_S:
            last_sent[0] = time.monotonic()
            event = {
                "event_type":  "heartbeat",
                "server_id":   _get_server_mac(),
                "ts":          time.time(),
                "cpu_percent": psutil.cpu_percent(),
                "ram_used_mb": psutil.virtual_memory().used / 1_048_576,
            }
            sender.send(event)


def _build_event(time_total_ms: float, time_db_ms: float, status_code: int, request_type: str) -> dict:
    return {
        "server_id": _get_server_mac(),
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

    _last_sent: list[float] = [time.monotonic()]
    threading.Thread(target=_heartbeat_loop, args=(_sender, _last_sent), daemon=True).start()

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
        _last_sent[0] = time.monotonic()
        return response
