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
_VIP_DATA_RECOVERY_IDLE_TIMEOUT = int(os.environ.get("VIP_DATA_RECOVERY_IDLE_TIMEOUT", "40"))
_VIP_DATA_RECOVERY_HARD_TIMEOUT = int(os.environ.get("VIP_DATA_RECOVERY_HARD_TIMEOUT", "45"))

# Cross-network routing: OVS port number connected to the inter-LAN router.
# 0 = disabled (local-only mode).  Set to the actual port (e.g. 3) to enable
# forwarding DNAT'd packets via the router toward peer-network backends.
_ROUTER_OVS_PORT  = int(os.environ.get("ROUTER_OVS_PORT",  "0"))

# MAC address of the router's interface on this controller's LAN.
# When a cross-network backend replies, the router performs L3 forwarding
# and substitutes its own MAC as eth_src.  The SNAT match must use this
# MAC instead of the real backend MAC for return-path rewriting.
_ROUTER_MAC = os.environ.get("ROUTER_MAC", "").strip().lower() or None
