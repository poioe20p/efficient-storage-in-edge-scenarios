"""control_events.py — ZMQ control event dispatcher.

Dispatches drain_complete, rs_secondary_ready, and telemetry-based
VIP promotions. Fully stateless — all dependencies passed as arguments.

Thread safety: all methods are called exclusively from Thread 2.
"""

import logging
import time
from typing import Callable

from .elasticity.elasticity import ElasticityManager
from .elasticity.node_common import log_ready_timing
from .node_registry import DynamicNodeRegistry
from .telemetry.models import TelemetrySummary

logger = logging.getLogger(__name__)


class ControlEventDispatcher:
    """Dispatches ZMQ control events and telemetry-based VIP promotions.

    Stateless — all state is read from the node registry and topology mixin.
    """

    def _log_storage_ready(self, info, source: str) -> None:
        if info.ready_logged or info.spawn_started_monotonic_s <= 0:
            return
        log_ready_timing(
            info.name,
            "storage",
            source,
            time.monotonic() - info.spawn_started_monotonic_s,
        )
        info.ready_logged = True

    def process_drain_events(self, summary: TelemetrySummary,
                             elasticity: ElasticityManager) -> None:
        """Handle drain_complete control events forwarded by the aggregator.

        Routes on ``PendingDrain.node_type`` via
        :meth:`ElasticityManager.submit_cleanup` so compute and Tier 1
        selective-sync drains share the same dispatch path.
        """
        for event in summary.control_events:
            if event.get("event_type") == "drain_complete":
                mac = event.get("server_id")
                if mac and elasticity.has_pending_drain(mac):
                    logger.info("[control] drain_complete received for mac=%s — submitting Phase B cleanup", mac)
                    elasticity.submit_cleanup(mac)
                elif mac:
                    logger.info("[control] drain_complete for unknown mac=%s — ignoring", mac)
                else:
                    logger.warning("[control] drain_complete missing server_id — ignoring")

    def process_secondary_events(
        self,
        summary: TelemetrySummary,
        registry: DynamicNodeRegistry,
        add_storage_mac_fn: Callable[[str, str], None],
    ) -> None:
        """Handle rs_secondary_ready control events — add storage node to VIP pool."""
        for event in summary.control_events:
            if event.get("event_type") == "rs_secondary_ready":
                mac = event.get("server_id")
                if not mac:
                    continue
                info = registry.get_node_info(mac)
                if info is None:
                    logger.warning("[control] rs_secondary_ready for unknown mac=%s — ignoring", mac)
                    continue
                if info.node_type != "storage":
                    logger.warning("[control] rs_secondary_ready for non-storage mac=%s — ignoring", mac)
                    continue
                if info.ready_logged:
                    logger.debug("[control] rs_secondary_ready for mac=%s already processed — ignoring", mac)
                    continue
                add_storage_mac_fn(mac, f"n{info.lan}")
                self._log_storage_ready(info, "rs_secondary_ready")
                logger.info(
                    "[control] rs_secondary_ready received for mac=%s — "
                    "added to VIP storage pool (ip=%s, name=%s)",
                    mac, info.ip, info.name,
                )

    def promote_storage_from_telemetry(
        self,
        summary: TelemetrySummary,
        registry: DynamicNodeRegistry,
        local_storage_macs_n1: set[str],
        local_storage_macs_n2: set[str],
        add_storage_mac_fn: Callable[[str, str], None],
    ) -> None:
        """Fallback VIP promotion: detect SECONDARY from regular telemetry.

        If a storage node reports member_state=="SECONDARY" in its aggregated
        telemetry but has not been added to the VIP pool yet, promote it now.
        """
        for mac, ss in summary.storage_servers.items():
            if ss.member_state != "SECONDARY":
                continue
            info = registry.get_node_info(mac)
            if info is None or info.node_type != "storage":
                continue
            if info.ready_logged:
                continue
            domain = f"n{info.lan}"
            already_in = (
                mac in local_storage_macs_n1 if domain == "n1"
                else mac in local_storage_macs_n2
            )
            if already_in:
                continue
            add_storage_mac_fn(mac, domain)
            self._log_storage_ready(info, "telemetry_secondary")
            logger.info(
                "[control] promoting storage mac=%s via telemetry fallback "
                "(member_state=SECONDARY, ip=%s, name=%s)",
                mac, info.ip, info.name,
            )
