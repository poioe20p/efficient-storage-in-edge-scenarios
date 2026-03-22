"""
elasticity.py — Thread 3: Elasticity & Placement Manager.

Owns a threading.Queue fed by Thread 2's on_update callback. Dispatches
typed alerts to the appropriate handler. All infrastructure mutations flow
through NodeAdder — this module is the sole orchestrator of container
lifecycle changes.
"""

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .node_manager import NodeAdder

if TYPE_CHECKING:
    from .topology import TopologyMixin

logger = logging.getLogger("os_ken.elasticity")

# Per-network sequence counter used to generate unique dynamic container names.
_COUNTER: dict[str, int] = {}


# ------------------------------------------------------------------
# Alert types — produced by Thread 2, consumed by Thread 3
# ------------------------------------------------------------------

@dataclass(frozen=True)
class ComputeAlert:
    """Raised by Thread 2 when avg T_proc > τ_proc for a network domain."""
    lan: int          # target LAN number (1 or 2)
    network_id: str   # e.g. "lan1"


@dataclass(frozen=True)
class DataAlert:
    """Raised by Thread 2 when avg T_dados > τ_dados for a network domain."""
    lan:               int
    network_id:        str
    rs_name:           str   # e.g. "rs_net1"
    primary_container: str   # container to run rs.add() against
    port:              int = 27018


# ------------------------------------------------------------------
# ElasticityManager
# ------------------------------------------------------------------

class ElasticityManager:
    """Thread 3: the sole actor for infrastructure mutations.

    Thread 2 calls ``submit_alert()``; this manager pops alerts off its queue
    and runs the appropriate NodeAdder lifecycle in a dedicated daemon thread.
    The calling thread is never blocked — the queue decouples detection from
    execution.
    """

    def __init__(self, topology_mixin: TopologyMixin) -> None:
        self._queue:  queue.Queue = queue.Queue()
        self._adder   = NodeAdder()
        self._topo    = topology_mixin          # TopologyMixin reference
        self._active: list[dict] = []           # audit trail (operation history)
        self._lock    = threading.Lock()
        self._thread  = threading.Thread(
            target=self._loop, name="elasticity-mgr", daemon=True,
        )

    def start(self) -> None:
        self._thread.start()
        logger.info("[elasticity] manager started")

    def submit_alert(self, alert: ComputeAlert | DataAlert) -> None:
        """Thread-safe enqueue. Called by Thread 2's on_update callback."""
        logger.info("[elasticity] alert submitted: %s", alert)
        self._queue.put(alert)

    def get_active_operations(self) -> list[dict]:
        """Return a snapshot of the operation audit trail (safe to call from any thread)."""
        with self._lock:
            return list(self._active)

    # ------------------------------------------------------------------
    # Private — runs exclusively in the elasticity daemon thread
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        while True:
            try:
                alert = self._queue.get()
                if isinstance(alert, ComputeAlert):
                    self._handle_compute(alert)
                elif isinstance(alert, DataAlert):
                    self._handle_data(alert)
                else:
                    logger.warning("[elasticity] unknown alert type: %s", type(alert))
            except Exception:  # noqa: BLE001
                logger.exception("[elasticity] unhandled error in loop")

    def _handle_compute(self, alert: ComputeAlert) -> None:
        name = self._next_name("edge_server", alert.network_id)
        logger.info("[elasticity] compute: spawning %s on LAN %d", name, alert.lan)

        result = self._adder.add_edge_server(lan=alert.lan, name=name)
        self._adder.log_timings(result)
        self._record({"type": "compute", "alert": alert, "name": name, "result": result})

        logger.debug("[elasticity] compute result: success=%s ip=%s mac=%s", result.success, result.ip, result.mac)

        if result.success and result.ip:
            if result.mac:
                self._topo.add_server_mac(result.mac)
                logger.info(
                    "[elasticity] compute: %s online  ip=%s  mac=%s",
                    name, result.ip, result.mac,
                )
            else:
                logger.warning(
                    "[elasticity] compute: %s online at %s but MAC not available in script output",
                    name, result.ip,
                )
        else:
            logger.error("[elasticity] compute: failed to spawn %s", name)

    def _handle_data(self, alert: DataAlert) -> None:
        name = self._next_name("edge_storage", alert.network_id)
        logger.info("[elasticity] data: spawning %s on LAN %d", name, alert.lan)

        result = self._adder.add_storage_node(
            lan=alert.lan,
            name=name,
            rs_name=alert.rs_name,
            primary_container=alert.primary_container,
            port=alert.port,
        )
        self._adder.log_timings(result)
        self._record({"type": "data", "alert": alert, "name": name, "result": result})

        logger.debug("[elasticity] data result: success=%s ip=%s mac=%s", result.success, result.ip, result.mac)

        if result.success and result.ip:
            if result.mac:
                self._topo.add_storage_mac(result.mac)
                logger.info(
                    "[elasticity] data: %s online  ip=%s  mac=%s",
                    name, result.ip, result.mac,
                )
            else:
                logger.warning(
                    "[elasticity] data: %s online at %s but MAC not available in script output",
                    name, result.ip,
                )
        else:
            logger.error("[elasticity] data: failed to spawn %s", name)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _next_name(self, prefix: str, network_id: str) -> str:
        _COUNTER[network_id] = _COUNTER.get(network_id, 0) + 1
        name = f"{prefix}_{network_id}_dyn{_COUNTER[network_id]}"
        logger.debug("[elasticity] generated container name: %s", name)
        return name

    def _record(self, entry: dict) -> None:
        # threading.Lock used as a context manager: acquired on enter, released on exit.
        with self._lock:
            self._active.append(entry)
        logger.debug("[elasticity] recorded operation: type=%s name=%s", entry.get("type"), entry.get("name"))
