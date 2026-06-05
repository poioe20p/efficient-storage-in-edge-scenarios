"""node_registry.py — Dynamic node lifecycle tracking (Registry pattern).

Tracks which dynamically added nodes exist, detects disappeared nodes,
and builds scale-down alerts. Does NOT submit alerts or access the
ElasticityManager beyond consuming completions.

Thread safety: all methods are called exclusively from Thread 2.
"""

import logging
import time
from dataclasses import dataclass

from .scaling_config import (
    _TELEMETRY_TIMEOUT_WINDOWS,
    _NODE_BIRTH_GRACE_S,
    _STORAGE_PERSISTENT_RESERVE_ENABLED,
    _STORAGE_RESERVE_PENDING_WINDOWS,
)
from .elasticity.elasticity import (
    ElasticityManager,
    ScaleDownComputeAlert,
    ScaleDownDataAlert,
    ScaleDownSelectiveAlert,
)
from .elasticity.node_common import NodeInfo
from .telemetry.models import TelemetrySummary

logger = logging.getLogger(__name__)


@dataclass
class StorageReserveSlot:
    """Controller-side state for one persistent same-LAN storage reserve.

    Owned by Thread 2. One slot per LAN.
    """
    lan: int
    state: str = "NONE"          # NONE | PREPARING | READY_RESERVED
    mac: str = ""
    ip: str = ""
    name: str = ""
    activation_pending: bool = False
    pending_reason: str = ""
    pending_windows_remaining: int = 0


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
        # Persistent reserve — one slot per LAN, keyed by LAN number.
        self._reserve_slots: dict[int, StorageReserveSlot] = {}

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
        """LIFO lookup for most recently added dynamic node of the given type.

        Reserved nodes (``standby_reserved=True``) are skipped — they are
        not eligible for ordinary LIFO scale-down.
        """
        for mac, info in reversed(list(self._active.items())):
            if info.node_type == node_type and mac in self._dynamic_node_macs and not info.standby_reserved:
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
        """Count dynamic nodes of the given type.

        Reserved storage nodes (``standby_reserved=True``) are excluded —
        they do not count toward active storage thresholds.
        """
        return sum(
            1 for info in self._active.values()
            if info.node_type == node_type and not info.standby_reserved
        )

    def node_age_s(self, mac: str, now: float | None = None) -> float:
        """Return monotonic age of a tracked node in seconds."""
        current = time.monotonic() if now is None else now
        return current - self._birth_ts.get(mac, current)

    def get_node_info(self, mac: str) -> NodeInfo | None:
        return self._active.get(mac)

    def is_tracked(self, mac: str) -> bool:
        return mac in self._dynamic_node_macs

    # ── Storage persistent reserve helpers ──────────────────────────────

    def _ensure_reserve_slot(self, lan: int) -> StorageReserveSlot:
        """Return (creating if necessary) the reserve slot for *lan*."""
        if lan not in self._reserve_slots:
            self._reserve_slots[lan] = StorageReserveSlot(lan=lan)
        return self._reserve_slots[lan]

    def get_storage_reserve_slot(self, lan: int) -> StorageReserveSlot:
        """Public read-only access to the reserve slot for *lan*."""
        return self._ensure_reserve_slot(lan)

    def should_prepare_storage_reserve(self, lan: int) -> bool:
        """True when the feature is on and *lan* needs a reserve preparation."""
        if not _STORAGE_PERSISTENT_RESERVE_ENABLED:
            return False
        slot = self._ensure_reserve_slot(lan)
        return slot.state == "NONE"

    def mark_storage_reserve_prepare_submitted(self, lan: int) -> None:
        """Record that a reserve preparation was submitted for *lan*."""
        slot = self._ensure_reserve_slot(lan)
        slot.state = "PREPARING"
        logger.info("[reserve] prepare_submitted lan=%d", lan)

    def mark_storage_reserve_ready(self, mac: str) -> None:
        """Move the reserve identified by *mac* to READY_RESERVED."""
        info = self.get_node_info(mac)
        if info is None or not info.standby_reserved:
            logger.warning("[reserve] mark_storage_reserve_ready for non-reserved mac=%s — ignoring", mac)
            return
        slot = self._ensure_reserve_slot(info.lan)
        slot.state = "READY_RESERVED"
        slot.mac = info.mac
        slot.ip = info.ip
        slot.name = info.name
        logger.info("[reserve] ready_reserved lan=%d name=%s ip=%s mac=%s",
                    info.lan, info.name, info.ip, info.mac)

    def latch_storage_reserve_activation(self, lan: int, reason: str, windows: int | None = None) -> None:
        """Mark that activation is pending, bounded by *windows* telemetry cycles.

        Re-latching (when already pending) refreshes the budget so a fresh
        trigger restarts the countdown.
        """
        if windows is None:
            windows = _STORAGE_RESERVE_PENDING_WINDOWS
        slot = self._ensure_reserve_slot(lan)
        slot.activation_pending = True
        slot.pending_reason = reason
        slot.pending_windows_remaining = windows
        logger.info("[reserve] waiting_ready lan=%d reason=%s windows=%d", lan, reason, windows)

    def tick_storage_reserve_pending_activation(self, lan: int) -> bool:
        """Decrement the pending-activation budget for *lan* by one window.

        Returns True when the budget has just reached zero (expired).
        Does nothing (returns False) when no activation is pending or the
        reserve has already been activated.
        """
        slot = self._ensure_reserve_slot(lan)
        if not slot.activation_pending:
            return False
        if slot.state == "READY_RESERVED":
            # Don't count down while ready — the next activation check will consume it.
            return False
        if slot.pending_windows_remaining <= 0:
            return True  # already expired — signal again so caller can clean up
        slot.pending_windows_remaining -= 1
        if slot.pending_windows_remaining <= 0:
            logger.info("[reserve] pending_expired lan=%d reason=%s", lan, slot.pending_reason)
            return True
        return False

    def clear_storage_reserve_pending_activation(self, lan: int) -> None:
        """Clear only the pending-activation fields; leave slot state alone."""
        slot = self._ensure_reserve_slot(lan)
        slot.activation_pending = False
        slot.pending_reason = ""
        slot.pending_windows_remaining = 0

    def mark_storage_reserve_prepare_failed(self, lan: int) -> None:
        """Clear a PREPARING slot back to NONE after a failed spawn.

        Pending activation is preserved so a waiting trigger can still be
        satisfied by a future replacement reserve.
        """
        slot = self._ensure_reserve_slot(lan)
        if slot.state != "PREPARING":
            return
        slot.state = "NONE"
        slot.mac = ""
        slot.ip = ""
        slot.name = ""
        logger.info("[reserve] prepare_failed lan=%d (pending=%s)", lan, slot.activation_pending)

    def unregister_reserved_node(self, mac: str) -> None:
        """Fully remove a reserved node from all registry tracking structures.

        This is a dedicated cleanup path — not ordinary scale-down.
        Idempotent: safe to call multiple times for the same MAC.
        """
        self._dynamic_node_macs.discard(mac)
        self._absent_window_count.pop(mac, None)
        self._active.pop(mac, None)
        self._birth_ts.pop(mac, None)
        logger.info("[reserve] unregistered mac=%s from tracking", mac)

    def consume_ready_storage_reserve(self, lan: int) -> NodeInfo | None:
        """Consume the ready reserve for *lan* and return its NodeInfo.

        Returns None if no ready reserve exists. Clears the slot back to NONE.
        """
        slot = self._ensure_reserve_slot(lan)
        if slot.state != "READY_RESERVED" or not slot.mac:
            return None
        info = self.get_node_info(slot.mac)
        # Capture identity before clearing the slot so the log line is accurate.
        activated_name = info.name if info else "?"
        activated_ip   = info.ip if info else "?"
        activated_mac  = slot.mac
        activated_reason = slot.pending_reason or "load"
        slot.state = "NONE"
        slot.mac = ""
        slot.ip = ""
        slot.name = ""
        slot.activation_pending = False
        slot.pending_reason = ""
        slot.pending_windows_remaining = 0
        logger.info("[reserve] activated lan=%d name=%s ip=%s mac=%s reason=%s",
                    lan, activated_name, activated_ip, activated_mac, activated_reason)
        return info

    def mark_storage_reserve_lost(self, mac: str) -> None:
        """Handle reserve loss — clear the slot identity so replenish can start.

        Preserves pending activation so a waiting trigger can carry forward
        to the replacement reserve.  Callers must call this **before**
        :meth:`unregister_reserved_node` so the node is still present in
        the registry when the slot is cleared.

        Includes a slot-scan fallback: if the node has already been removed
        from the registry (e.g. by an earlier unregister), scans all reserve
        slots for the matching MAC and clears the first match.
        """
        info = self.get_node_info(mac)
        if info is not None:
            lan = info.lan
            slot = self._ensure_reserve_slot(lan)
            if slot.mac == mac or slot.state == "PREPARING":
                slot.state = "NONE"
                slot.mac = ""
                slot.ip = ""
                slot.name = ""
                # Preserve pending activation for bounded carry-forward.
                logger.info("[reserve] lost lan=%d mac=%s (pending=%s windows_left=%d)",
                            lan, mac, slot.activation_pending, slot.pending_windows_remaining)
                return

        # Fallback: scan all slots for a matching MAC in case the node was
        # already unregistered before this call.
        for lan, slot in self._reserve_slots.items():
            if slot.mac == mac:
                slot.state = "NONE"
                slot.mac = ""
                slot.ip = ""
                slot.name = ""
                logger.info("[reserve] lost lan=%d mac=%s (fallback, pending=%s windows_left=%d)",
                            lan, mac, slot.activation_pending, slot.pending_windows_remaining)
                return

    def can_scale_down_storage(self, candidate_mac: str, lan: int) -> bool:
        """Return True only if removing *candidate_mac* leaves a ready reserve.

        Ordinary storage scale-down is blocked unless the LAN has a
        READY_RESERVED slot *after* the removal. A PREPARING reserve does
        not satisfy the floor.
        """
        slot = self._ensure_reserve_slot(lan)
        if slot.state != "READY_RESERVED":
            return False
        info = self.get_node_info(candidate_mac)
        return info is not None and not info.standby_reserved

    # ── Alert building ───────────────────────────────────────────────────

    def build_scale_down_alert(self, mac: str) -> ScaleDownComputeAlert | ScaleDownDataAlert | ScaleDownSelectiveAlert | None:
        """Build the appropriate scale-down alert from NodeInfo. Returns None if MAC not tracked.

        Reserved nodes (``standby_reserved=True``) do NOT produce ordinary
        scale-down alerts. Reserve loss is handled separately.
        """
        if mac not in self._dynamic_node_macs:
            logger.warning("[registry] mac=%s not in dynamic_node_macs — ignoring", mac)
            return None
        info = self._active.get(mac)
        if info is None:
            logger.warning("[registry] no NodeInfo for mac=%s — cannot build alert", mac)
            return None
        if info.standby_reserved:
            logger.info("[registry] mac=%s is standby_reserved — not building ordinary scale-down alert", mac)
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
