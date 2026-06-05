"""Controller-owned mutable VIP-routing state and lifecycle helpers.

All functions operate on ``controller`` (the VipRoutingMixin instance) and
read/write its instance attributes directly.  No state is moved off the
controller object.
"""

import logging
import time

from .config import WarmLease, logger
from ..scaling_config import _VIP_WARM_SERVER_SECONDS, _VIP_WARM_STORAGE_SECONDS

# Re-export for convenience (used by selection.py)
__all__ = [
    "init_vip_routing_state",
    "register_backend_ip",
    "mark_server_backend_warm",
    "mark_storage_backend_warm",
    "clear_server_backend_warm",
    "clear_storage_backend_warm",
    "register_new_server_backend",
    "unregister_server_backend",
    "unregister_storage_backend",
    "update_server_stats",
    "update_storage_stats",
]


def init_vip_routing_state(controller) -> None:
    """Initialise all mutable VIP-routing attributes on *controller*."""
    # IP ↔ MAC learned by snooping ARP packets that reach the controller.
    # Backends ARP for the VIPs at startup, which bootstraps this table.
    controller._ip_to_mac: dict[str, str] = {}   # ip  -> mac
    controller._mac_to_ip: dict[str, str] = {}   # mac -> ip

    # Per-server / per-storage telemetry stats, keyed by MAC.
    # Each container discovers its own MAC and includes it in telemetry
    # events — the aggregator forwards it as the dict key.
    # Updated by Thread 2 via update_server_stats() / update_storage_stats().
    # Read by Thread 1 cost functions (select_server / select_storage).
    controller._server_stats:  dict = {}  # mac -> ServerSummary
    controller._storage_stats: dict = {}  # mac -> StorageServerSummary

    # Round-robin counters for cold-start tie-breaking.
    # When multiple backends share the lowest WSM cost (common during cold
    # start when all resource dimensions are 0.0), the counter ensures
    # traffic is distributed instead of always hitting the first entry.
    controller._rr_server_idx: int = 0
    controller._rr_storage_idx: dict[str, int] = {}   # domain -> counter

    import threading
    controller._warm_lock = threading.Lock()
    controller._warm_server_leases: dict[str, WarmLease] = {}  # mac -> lease
    controller._warm_storage_leases: dict[str, dict[str, WarmLease]] = {
        "n1": {},
        "n2": {},
    }  # domain -> (mac -> lease)
    # (edge_server_mac, domain) -> backend_mac for the last normal
    # VIP_DATA choice. Recovery selections must not overwrite this state.
    controller._last_normal_storage_choice: dict[tuple[str, str], str] = {}

    from .config import (
        _W_CPU, _W_RAM, _W_REQUESTS, _W_HOPS,
        _VIP_IDLE_TIMEOUT, _VIP_HARD_TIMEOUT,
        _ROUTER_OVS_PORT,
    )
    logger.debug(
        "vip routing mixin: w_cpu=%.2f w_ram=%.2f w_req=%.2f w_hops=%.2f "
        "idle_timeout=%ds hard_timeout=%ds router_port=%d warm_storage=%.1fs warm_server=%.1fs",
        _W_CPU, _W_RAM, _W_REQUESTS, _W_HOPS,
        _VIP_IDLE_TIMEOUT, _VIP_HARD_TIMEOUT,
        _ROUTER_OVS_PORT,
        _VIP_WARM_STORAGE_SECONDS,
        _VIP_WARM_SERVER_SECONDS,
    )


def register_backend_ip(controller, mac: str, ip: str) -> None:
    """Seed _mac_to_ip/_ip_to_mac from a known IP returned by NodeAdder.

    Called by Thread 3 (ElasticityManager) immediately after adding a new
    MAC to the VIP pool, so Thread 1 can route the very first packet to
    the new backend without waiting for an ARP to arrive at the controller.
    snoop_arp() remains authoritative — it will overwrite this entry if
    the container's IP ever changes.
    """
    controller._ip_to_mac[ip]  = mac
    controller._mac_to_ip[mac] = ip
    logger.info("backend ip registered (static seed): %s -> %s", mac, ip)


# --- Warm-lease management (Thread 2 / Thread 3 facing) ---

def mark_server_backend_warm(controller, mac: str) -> None:
    now = time.monotonic()
    with controller._warm_lock:
        controller._warm_server_leases[mac] = WarmLease(
            started_ts=now,
            expires_ts=now + _VIP_WARM_SERVER_SECONDS,
        )
    logger.info(
        "vip_server warm lease created: mac=%s ttl=%.1fs",
        mac,
        _VIP_WARM_SERVER_SECONDS,
    )


def mark_storage_backend_warm(controller, mac: str, domain: str) -> None:
    now = time.monotonic()
    with controller._warm_lock:
        domain_leases = controller._warm_storage_leases.setdefault(domain, {})
        domain_leases[mac] = WarmLease(
            started_ts=now,
            expires_ts=now + _VIP_WARM_STORAGE_SECONDS,
        )
    logger.info(
        "vip_data(%s) warm lease created: mac=%s ttl=%.1fs",
        domain,
        mac,
        _VIP_WARM_STORAGE_SECONDS,
    )


def clear_server_backend_warm(controller, mac: str) -> None:
    with controller._warm_lock:
        cleared = controller._warm_server_leases.pop(mac, None) is not None
    if cleared:
        logger.info("vip_server warm lease cleared: mac=%s", mac)


def clear_storage_backend_warm(controller, mac: str, domain: str) -> None:
    with controller._warm_lock:
        domain_leases = controller._warm_storage_leases.setdefault(domain, {})
        cleared = domain_leases.pop(mac, None) is not None
    if cleared:
        logger.info("vip_data(%s) warm lease cleared: mac=%s", domain, mac)


# --- Backend lifecycle hooks (public API, called by elasticity manager) ---

def register_new_server_backend(controller, mac: str, ip: str) -> None:
    controller.add_server_mac(mac)
    register_backend_ip(controller, mac, ip)
    mark_server_backend_warm(controller, mac)


def unregister_server_backend(controller, mac: str) -> None:
    controller.remove_server_mac(mac)
    clear_server_backend_warm(controller, mac)


def unregister_storage_backend(controller, mac: str, domain: str) -> None:
    controller.remove_storage_mac(mac, domain)
    clear_storage_backend_warm(controller, mac, domain)
    _forget_normal_storage_choice(controller, mac, domain)


# --- Telemetry cache updates (Thread 2 facing) ---

def update_server_stats(controller, servers: dict) -> None:
    """Store per-server telemetry stats, keyed by MAC.

    ``servers`` is keyed by the container's MAC address (each container
    discovers its own MAC from eth0 and includes it in telemetry events).
    Thread 1 reads _server_stats in select_server() for the WSM cost
    function.
    """
    for mac, summary in servers.items():
        controller._server_stats[mac] = summary
        logger.debug(
            "server stats updated: mac=%s cpu=%.1f%% ram=%.1fMB req=%d",
            mac, summary.avg_cpu_percent,
            summary.avg_ram_used_mb, summary.request_count,
        )


def update_storage_stats(controller, storage_servers: dict) -> None:
    """Store per-storage telemetry stats, keyed by MAC.

    ``storage_servers`` is keyed by the container's MAC address.
    Thread 1 reads _storage_stats in select_storage() for the storage
    WSM cost function.
    """
    for mac, summary in storage_servers.items():
        controller._storage_stats[mac] = summary
        logger.debug(
            "storage stats updated: mac=%s cpu=%.1f%% ram=%.1fMB conn=%.1f lag=%s",
            mac, summary.avg_cpu_percent,
            summary.avg_ram_used_mb, summary.avg_connections,
            summary.avg_repl_lag_s,
        )


# --- Internal helpers (also used by selection.py) ---

def _remember_normal_storage_choice(controller, client_mac: str, domain: str, backend_mac: str) -> None:
    with controller._warm_lock:
        controller._last_normal_storage_choice[(client_mac, domain)] = backend_mac


def _forget_normal_storage_choice(controller, backend_mac: str, domain: str) -> None:
    with controller._warm_lock:
        stale_keys = [
            key
            for key, remembered_mac in controller._last_normal_storage_choice.items()
            if key[1] == domain and remembered_mac == backend_mac
        ]
        for key in stale_keys:
            controller._last_normal_storage_choice.pop(key, None)

    if stale_keys:
        logger.info(
            "vip_data(%s): forgot %d remembered normal choices for removed backend mac=%s",
            domain,
            len(stale_keys),
            backend_mac,
        )
