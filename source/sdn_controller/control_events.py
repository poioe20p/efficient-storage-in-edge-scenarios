"""control_events.py — ZMQ control event dispatcher.

Dispatches drain_complete, rs_secondary_ready, and telemetry-based
VIP promotions. Fully stateless — all dependencies passed as arguments.

Thread safety: all methods are called exclusively from Thread 2.
"""

import logging
from typing import Callable

from .elasticity.elasticity import ElasticityManager
from .node_registry import DynamicNodeRegistry
from .telemetry.models import TelemetrySummary

logger = logging.getLogger(__name__)


class ControlEventDispatcher:
    """Dispatches ZMQ control events and telemetry-based VIP promotions.

    Stateless — all state is read from the node registry and topology mixin.
    """

    def process_drain_events(self, summary: TelemetrySummary,
                             elasticity: ElasticityManager) -> None:
        """Handle drain_complete control events forwarded by the aggregator."""
        for event in summary.control_events:
            if event.get("event_type") == "drain_complete":
                mac = event.get("server_id")
                if mac and elasticity.has_pending_drain(mac):
                    logger.info("[control] drain_complete received for mac=%s — submitting Phase B cleanup", mac)
                    elasticity.submit_cleanup_compute(mac)

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
                add_storage_mac_fn(mac, f"n{info.lan}")
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
            domain = f"n{info.lan}"
            already_in = (
                mac in local_storage_macs_n1 if domain == "n1"
                else mac in local_storage_macs_n2
            )
            if already_in:
                continue
            add_storage_mac_fn(mac, domain)
            logger.info(
                "[control] promoting storage mac=%s via telemetry fallback "
                "(member_state=SECONDARY, ip=%s, name=%s)",
                mac, info.ip, info.name,
            )
