"""Shared configuration, constants, and lightweight types for VIP routing.

Import-time environment-variable parsing happens here so every other module
in the _vip_routing package can import these values without touching os.environ.
"""

import logging
import os
from dataclasses import dataclass

logger = logging.getLogger("os_ken.vip_routing")


@dataclass(frozen=True)
class WarmLease:
    started_ts: float
    expires_ts: float


@dataclass(frozen=True)
class ClientVipBinding:
    """Recorded VIP_SERVER client→backend flow mapping (RQ3 flow isolation).

    Captured when ``install_vip_dnat_snat`` installs a VIP_SERVER DNAT/SNAT
    pair, so ``delete_vip_server_client_flows`` can delete the EXACT pair on
    the next request's ``request_complete`` control event. ``snat_eth_src`` is
    the exact ``eth_src`` used on the SNAT rule (backend MAC or router MAC).
    """
    client_mac: str
    client_ip: str
    backend_mac: str
    backend_ip: str
    vip_ip: str
    vip_mac: str
    snat_eth_src: str

# --- Backend-selection policy mode (RQ2) ---
_BACKEND_SELECTION_POLICY = os.environ.get(
    "BACKEND_SELECTION_POLICY", "topology_lifecycle"
)
# Valid: topology_host | topology_slowstart | topology_lifecycle

# --- Server (compute) WSM weights ---
_W_CPU      = float(os.environ.get("W_CPU",      "0.2"))
_W_RAM      = float(os.environ.get("W_RAM",      "0.2"))
_W_REQUESTS = float(os.environ.get("W_REQUESTS", "0.2"))
_W_HOPS     = float(os.environ.get("W_HOPS",     "0.28"))

# --- Storage WSM weights ---
_W_STORAGE_CPU         = float(os.environ.get("W_STORAGE_CPU",         "0.2"))
_W_STORAGE_RAM         = float(os.environ.get("W_STORAGE_RAM",         "0.2"))
_W_STORAGE_CONNECTIONS = float(os.environ.get("W_STORAGE_CONNECTIONS", "0.1"))
_W_STORAGE_LAG         = float(os.environ.get("W_STORAGE_LAG",         "0.2"))
_W_STORAGE_HOPS        = float(os.environ.get("W_STORAGE_HOPS",        "0.3"))

_VIP_IDLE_TIMEOUT = int(os.environ.get("VIP_IDLE_TIMEOUT", "30"))
_VIP_HARD_TIMEOUT = int(os.environ.get("VIP_HARD_TIMEOUT", "120"))

# Per-connection VIP_DATA flow matching (Approach B, 2026-08-03).
# 0 (default) = per-CLIENT forward rules (one backend per edge server; the
#   edge read client uses maxPoolSize=1, so every connection from an edge is
#   DNAT'd to the same storage backend). Preserves pre-fix/RQ1/RQ3 behavior.
# 1 = per-CONNECTION forward rules keyed on tcp_src: a pooled edge client
#   (EDGE_MONGO_MAX_POOL_SIZE>1) fans its connections out to different storage
#   backends, so storage serving capacity scales with edges x pool, not edges.
#   Only SYNs select a backend; established connections are never re-pinned
#   (their per-connection flow never expires), which avoids the
#   mid-connection DNAT break that a re-select would cause.
_VIP_DATA_PER_CONNECTION = int(
    os.environ.get("VIP_DATA_PER_CONNECTION_FLOWS", "0")
) > 0

# Cross-network routing: OVS port number connected to the inter-LAN router.
# 0 = disabled (local-only mode).  Set to the actual port (e.g. 3) to enable
# forwarding DNAT'd packets via the router toward peer-network backends.
_ROUTER_OVS_PORT  = int(os.environ.get("ROUTER_OVS_PORT",  "0"))

# MAC address of the router's interface on this controller's LAN.
# When a cross-network backend replies, the router performs L3 forwarding
# and substitutes its own MAC as eth_src.  The SNAT match must use this
# MAC instead of the real backend MAC for return-path rewriting.
_ROUTER_MAC = os.environ.get("ROUTER_MAC", "").strip().lower() or None
