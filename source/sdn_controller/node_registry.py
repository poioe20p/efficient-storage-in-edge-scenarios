"""node_registry.py — Dynamic node lifecycle tracking (Registry pattern).

Tracks which dynamically added nodes exist, detects disappeared nodes,
and builds scale-down alerts. Does NOT submit alerts or access the
ElasticityManager beyond consuming completions.

Thread safety: all methods are called exclusively from Thread 2.
"""

import logging
import time

from .scaling_config import _TELEMETRY_TIMEOUT_WINDOWS, _NODE_BIRTH_GRACE_S
from .elasticity.elasticity import (
    ElasticityManager,
    ScaleDownComputeAlert,
    ScaleDownDataAlert,
    ScaleDownSelectiveAlert,
)
from .elasticity.node_common import NodeInfo
from .telemetry.models import TelemetrySummary

logger = logging.getLogger(__name__)


class DynamicNodeRegistry:
    """Tracks dynamically added nodes for scale-down and absence detection.

    Owns: MAC tracking sets, active node map, absence counters, birth timestamps.
    Answers queries — does NOT submit alerts or touch the elasticity manager.
    """

    def __init__(self) -> None:
        self._dynamic_node_macs: set[str] = set()
        self._active: dict[str, NodeInfo] = {}     # mac → NodeInfo, insertion order = LIFO
        self._absent_window_count: dict[str, int] = {}
        self._birth_ts: dict[str, float] = {}

    # ── Thread 3 → Thread 2 sync ────────────────────────────────────────

    def sync(self, elasticity: ElasticityManager) -> None:
        """Consume removal and addition completions from Thread 3."""
        for mac in elasticity.consume_removal_completions():
            self._dynamic_node_macs.discard(mac)
            self._absent_window_count.pop(mac, None)
            self._active.pop(mac, None)
            self._birth_ts.pop(mac, None)
            logger.info("[registry] removed MAC %s from tracking after cleanup", mac)

        for info in elasticity.consume_addition_completions():
            self._dynamic_node_macs.add(info.mac)
            self._active[info.mac] = info
            self._birth_ts[info.mac] = time.monotonic()
            logger.info("[registry] tracking new dynamic %s node mac=%s name=%s",
                        info.node_type, info.mac, info.name)

    # ── Absence detection ────────────────────────────────────────────────

    def detect_absent(self, summary: TelemetrySummary) -> list[str]:
        """Return MACs that exceeded TELEMETRY_TIMEOUT_WINDOWS consecutive absent windows."""
        now = time.monotonic()
        timed_out: list[str] = []
        for mac in list(self._dynamic_node_macs):
            # Skip freshly spawned nodes still booting
            if now - self._birth_ts.get(mac, float('-inf')) < _NODE_BIRTH_GRACE_S:
                continue

            present = (mac in summary.servers) or (mac in summary.storage_servers)
            if present:
                self._absent_window_count[mac] = 0
            else:
                self._absent_window_count[mac] = self._absent_window_count.get(mac, 0) + 1
                count = self._absent_window_count[mac]
                logger.debug("[registry] mac=%s absent for %d windows", mac, count)
                if count >= _TELEMETRY_TIMEOUT_WINDOWS:
                    logger.warning("[registry] mac=%s absent for %d windows — triggering removal", mac, count)
                    self._absent_window_count[mac] = 0
                    timed_out.append(mac)
        return timed_out

    # ── Queries ──────────────────────────────────────────────────────────

    def find_last_dynamic(self, node_type: str) -> NodeInfo | None:
        """LIFO lookup for most recently added dynamic node of the given type."""
        for mac, info in reversed(list(self._active.items())):
            if info.node_type == node_type and mac in self._dynamic_node_macs:
                return info
        return None

    def list_dynamic(self, node_type: str) -> list[NodeInfo]:
        """Return tracked dynamic nodes of the given type in insertion order."""
        return [
            info
            for mac, info in self._active.items()
            if info.node_type == node_type and mac in self._dynamic_node_macs
        ]

    def count_dynamic(self, node_type: str) -> int:
        """Count dynamic nodes of the given type."""
        return sum(
            1 for info in self._active.values()
            if info.node_type == node_type
        )

    def node_age_s(self, mac: str, now: float | None = None) -> float:
        """Return monotonic age of a tracked node in seconds."""
        current = time.monotonic() if now is None else now
        return current - self._birth_ts.get(mac, current)

    def get_node_info(self, mac: str) -> NodeInfo | None:
        return self._active.get(mac)

    def is_tracked(self, mac: str) -> bool:
        return mac in self._dynamic_node_macs

    # ── Alert building ───────────────────────────────────────────────────

    def build_scale_down_alert(self, mac: str) -> ScaleDownComputeAlert | ScaleDownDataAlert | ScaleDownSelectiveAlert | None:
        """Build the appropriate scale-down alert from NodeInfo. Returns None if MAC not tracked."""
        if mac not in self._dynamic_node_macs:
            logger.warning("[registry] mac=%s not in dynamic_node_macs — ignoring", mac)
            return None
        info = self._active.get(mac)
        if info is None:
            logger.warning("[registry] no NodeInfo for mac=%s — cannot build alert", mac)
            return None

        if info.node_type == "compute":
            return ScaleDownComputeAlert(
                lan=info.lan,
                network_id=info.network_id,
                container_name=info.name,
                mac=mac,
                ip=info.ip,
            )
        elif info.node_type == "selective_storage":
            return ScaleDownSelectiveAlert(
                lan=info.lan,
                network_id=info.network_id,
                owner_lan=info.owner_lan,
                container_name=info.name,
                mac=mac,
                ip=info.ip,
            )
        else:
            return ScaleDownDataAlert(
                lan=info.lan,
                network_id=info.network_id,
                container_name=info.name,
                mac=mac,
                ip=info.ip,
                rs_name=info.rs_name,
                primary_container=info.primary_container,
                port=info.port,
            )
