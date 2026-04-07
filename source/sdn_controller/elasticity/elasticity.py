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

from .node_common import NodeInfo
from .compute_node_manager import ComputeNodeAdder, PendingDrain
from .storage_node_manager import StorageNodeAdder

if TYPE_CHECKING:
    from ..topology.topology import TopologyMixin

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


@dataclass(frozen=True)
class ScaleDownComputeAlert:
    """Scale-down: remove the most recently added dynamic compute node."""
    lan:            int
    network_id:     str
    container_name: str
    mac:            str


@dataclass(frozen=True)
class ScaleDownDataAlert:
    """Scale-down: remove the most recently added dynamic storage node."""
    lan:               int
    network_id:        str
    container_name:    str
    mac:               str
    ip:                str
    rs_name:           str
    primary_container: str
    port:              int = 27018


@dataclass(frozen=True)
class CleanupComputeAlert:
    """Phase B trigger: submitted when drain_complete ZMQ event arrives (or
    telemetry timeout fallback).  Causes Thread 3 to run OVS teardown."""
    mac: str


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
        self._compute_adder = ComputeNodeAdder()
        self._storage_adder = StorageNodeAdder()
        self._topo    = topology_mixin          # TopologyMixin reference
        self._active: list[dict] = []           # audit trail (operation history)
        self._lock    = threading.Lock()

        # Scale-down state — written by Thread 3, read by Thread 2
        self._busy: bool = False                # True while an operation is in progress
        self._pending_drains: dict[str, PendingDrain] = {}  # key: MAC

        # Add/removal completion notifications for Thread 2
        self._addition_complete_lock  = threading.Lock()
        self._addition_complete_infos: list[NodeInfo] = []
        self._removal_complete_lock   = threading.Lock()
        self._removal_complete_macs:  set[str] = set()

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

    def submit(self, alert) -> None:
        """Generic submit for any alert type (scale-up or scale-down)."""
        logger.info("[elasticity] alert submitted: %s", alert)
        self._queue.put(alert)

    def submit_cleanup_compute(self, mac: str) -> None:
        """Thread-safe enqueue of a Phase B cleanup alert (drain_complete event)."""
        logger.info("[elasticity] CleanupComputeAlert submitted for mac=%s", mac)
        self._queue.put(CleanupComputeAlert(mac=mac))

    def is_busy(self) -> bool:
        """Thread-safe check: is an operation currently in progress?

        Returns True while Thread 3 is executing any add/remove handler, or
        while a Phase A drain is pending (compute cleanup not yet completed).
        Thread 2 skips ALL scaling evaluation when this returns True.
        ``_busy`` is a plain bool written only by Thread 3 and read by Thread 2;
        Python's GIL guarantees atomic reads/writes of bool.
        """
        return self._busy or bool(self._pending_drains)

    def has_pending_drain(self, mac: str) -> bool:
        """Check if a MAC has an in-progress drain (Phase A done, Phase B pending)."""
        return mac in self._pending_drains

    def consume_addition_completions(self) -> list[NodeInfo]:
        """Called by Thread 2 to collect NodeInfo records for newly added nodes."""
        with self._addition_complete_lock:
            result, self._addition_complete_infos = list(self._addition_complete_infos), []
        return result

    def consume_removal_completions(self) -> set[str]:
        """Called by Thread 2 to collect MACs of fully removed nodes."""
        with self._removal_complete_lock:
            result, self._removal_complete_macs = set(self._removal_complete_macs), set()
        return result

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
                self._busy = True
                try:
                    if isinstance(alert, ComputeAlert):
                        self._handle_compute(alert)
                    elif isinstance(alert, DataAlert):
                        self._handle_data(alert)
                    elif isinstance(alert, ScaleDownComputeAlert):
                        self._handle_scale_down_compute(alert)
                    elif isinstance(alert, ScaleDownDataAlert):
                        self._handle_scale_down_data(alert)
                    elif isinstance(alert, CleanupComputeAlert):
                        self._handle_cleanup_compute(alert)
                    else:
                        logger.warning("[elasticity] unknown alert type: %s", type(alert))
                finally:
                    # CleanupComputeAlert is Phase B — keep _busy False only
                    # after it finishes (pending_drains already cleared inside handler).
                    self._busy = False
            except Exception:  # noqa: BLE001
                logger.exception("[elasticity] unhandled error in loop")

    def _handle_compute(self, alert: ComputeAlert) -> None:
        name = self._next_name("edge_server", alert.network_id)
        logger.info("[elasticity] compute: spawning %s on LAN %d", name, alert.lan)

        result = self._compute_adder.add_edge_server(lan=alert.lan, name=name)
        self._compute_adder.log_timings(result)
        self._record({"type": "compute", "alert": alert, "name": name, "result": result})

        logger.debug("[elasticity] compute result: success=%s ip=%s mac=%s", result.success, result.ip, result.mac)

        if result.success and result.ip:
            if result.mac:
                self._topo.add_server_mac(result.mac)
                self._topo.register_backend_ip(result.mac, result.ip)
                logger.info(
                    "[elasticity] compute: %s online  ip=%s  mac=%s",
                    name, result.ip, result.mac,
                )
                # Notify Thread 2 so it can track this MAC for scale-down
                info = NodeInfo(
                    mac=result.mac, lan=alert.lan, network_id=alert.network_id,
                    name=name, ip=result.ip, node_type="compute",
                )
                with self._addition_complete_lock:
                    self._addition_complete_infos.append(info)
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

        result = self._storage_adder.add_storage_node(
            lan=alert.lan,
            name=name,
            rs_name=alert.rs_name,
            primary_container=alert.primary_container,
            port=alert.port,
        )
        self._storage_adder.log_timings(result)
        self._record({"type": "data", "alert": alert, "name": name, "result": result})

        logger.debug("[elasticity] data result: success=%s ip=%s mac=%s", result.success, result.ip, result.mac)

        if result.success and result.ip:
            if result.mac:
                self._topo.add_storage_mac(result.mac, domain=f"n{alert.lan}")
                self._topo.register_backend_ip(result.mac, result.ip)
                logger.info(
                    "[elasticity] data: %s online  ip=%s  mac=%s",
                    name, result.ip, result.mac,
                )
                # Notify Thread 2 so it can track this MAC for scale-down
                info = NodeInfo(
                    mac=result.mac, lan=alert.lan, network_id=alert.network_id,
                    name=name, ip=result.ip, node_type="storage",
                    rs_name=alert.rs_name,
                    primary_container=alert.primary_container,
                    port=alert.port,
                )
                with self._addition_complete_lock:
                    self._addition_complete_infos.append(info)
            else:
                logger.warning(
                    "[elasticity] data: %s online at %s but MAC not available in script output",
                    name, result.ip,
                )
        else:
            logger.error("[elasticity] data: failed to spawn %s", name)

    def _handle_scale_down_compute(self, alert: ScaleDownComputeAlert) -> None:
        """Phase A: isolate from VIP, discover veth, send drain signal, return.

        Thread 3 returns immediately after Phase A.  Phase B is triggered by
        the drain_complete ZMQ event (or telemetry timeout fallback) which
        submits a CleanupComputeAlert.
        """
        logger.info("[elasticity] scale_down_compute: removing %s (mac=%s)", alert.container_name, alert.mac)

        # Immediately remove from VIP pool so no new DNAT flows are installed.
        self._topo.remove_server_mac(alert.mac)

        pending = self._compute_adder.initiate_drain(alert.lan, alert.container_name, alert.mac)
        if pending is None:
            # Veth discovery failed — container netns already gone.
            # Treat as immediate cleanup with best-effort teardown.
            logger.warning("[elasticity] veth discovery failed for %s — attempting cleanup without veth", alert.container_name)
            with self._removal_complete_lock:
                self._removal_complete_macs.add(alert.mac)
            return

        self._pending_drains[alert.mac] = pending
        self._record({"type": "scale_down_compute_phase_a", "alert": alert, "pending": pending})

        if not pending.drain_signaled:
            # Drain HTTP call failed — container is dead.  Submit Phase B immediately.
            logger.info("[elasticity] drain failed for %s — submitting immediate CleanupComputeAlert", alert.container_name)
            self._queue.put(CleanupComputeAlert(mac=alert.mac))
        else:
            logger.info("[elasticity] drain initiated for %s — waiting for drain_complete event", alert.container_name)
        # Thread 3 returns here; _busy is reset in _loop's finally block.

    def _handle_cleanup_compute(self, alert: CleanupComputeAlert) -> None:
        """Phase B: stop container, flush flows, remove OVS port/veth, docker rm.

        Triggered by drain_complete ZMQ event or telemetry timeout fallback.
        """
        pending = self._pending_drains.get(alert.mac)
        if pending is None:
            logger.warning("[elasticity] CleanupComputeAlert for unknown mac=%s — ignoring", alert.mac)
            return

        logger.info("[elasticity] cleanup_compute: container=%s mac=%s", pending.container_name, alert.mac)
        result = self._compute_adder.cleanup_compute_node(pending)
        self._compute_adder.log_removal_timings(result)
        self._record({"type": "scale_down_compute_phase_b", "alert": alert, "result": result})

        del self._pending_drains[alert.mac]

        # Notify Thread 2 that this MAC has been fully cleaned up.
        with self._removal_complete_lock:
            self._removal_complete_macs.add(alert.mac)

        if result.success:
            logger.info("[elasticity] cleanup_compute done: container=%s", pending.container_name)
        else:
            logger.error("[elasticity] cleanup_compute FAILED: container=%s", pending.container_name)

    def _handle_scale_down_data(self, alert: ScaleDownDataAlert) -> None:
        """Storage removal: VIP isolation → rs.remove() → script teardown."""
        logger.info("[elasticity] scale_down_data: removing %s (mac=%s)", alert.container_name, alert.mac)

        # Immediately remove from VIP pool so no new DNAT flows are installed.
        self._topo.remove_storage_mac(alert.mac, domain=f"n{alert.lan}")

        result = self._storage_adder.remove_storage_node(
            lan=alert.lan,
            name=alert.container_name,
            mac=alert.mac,
            ip=alert.ip,
            rs_name=alert.rs_name,
            primary_container=alert.primary_container,
            port=alert.port,
        )
        self._storage_adder.log_removal_timings(result)
        self._record({"type": "scale_down_data", "alert": alert, "result": result})

        # Notify Thread 2 regardless of success so stale tracking is cleared.
        with self._removal_complete_lock:
            self._removal_complete_macs.add(alert.mac)

        if result.success:
            logger.info("[elasticity] scale_down_data done: container=%s", alert.container_name)
        else:
            logger.error("[elasticity] scale_down_data FAILED: container=%s", alert.container_name)

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
