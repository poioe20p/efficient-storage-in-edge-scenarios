# Cross-Network VIP Routing Fix Plan

## Overview

VIP routing correctly selects cross-network backends (e.g., osken on LAN1 selects `edge_server_n2` on LAN2), but the DNAT'd packet is never forwarded to the remote LAN and the return-path SNAT rule never matches. Two configuration gaps and one protocol-level bug prevent cross-network VIP from working end-to-end.

---

## Root Causes

### RC-1: `ROUTER_OVS_PORT` not set (default `0` = disabled)

The `_install_vip_dnat_snat()` method already contains cross-network logic: when the selected backend is in `peer_hosts` and `_ROUTER_OVS_PORT > 0`, it outputs the DNAT'd packet to the router port. However, `ROUTER_OVS_PORT` was never set in `osken-controller.env` or the `docker run` commands, so it defaults to `0` (disabled). The backend is unreachable and the packet is dropped.

### RC-2: SNAT match uses backend MAC, but router rewrites it

When a cross-network backend responds, the packet traverses the inter-LAN router. Linux L3 forwarding rewrites **both** source and destination Ethernet MACs:

```
Backend (LAN2)                Router                     OVS-br0 (LAN1)
──────────────────────────    ──────────────────────    ──────────────────
Response packet:              eth2 receives:             Switch sees:
  eth_src = 00:00:00:00:00:05   routes via eth1            eth_src = 00:00:00:00:00:AA  ← router's LAN1 MAC
  eth_dst = 00:00:00:00:00:CC   rewrites MACs              eth_dst = <client_mac>
  ipv4_src = 10.0.1.2           ipv4 preserved             ipv4_src = 10.0.1.2
  ipv4_dst = 10.0.0.30                                     ipv4_dst = 10.0.0.30
```

The SNAT rule on osken (LAN1) matched `eth_src=00:00:00:00:00:05` (the real backend MAC), but the packet arrives with `eth_src=00:00:00:00:00:AA` (the router's eth1 MAC). The SNAT rule never fires and the client sees the raw backend IP instead of the VIP.

### RC-3: `ROUTER_MAC` not configured

Each controller needs to know its local router interface MAC to use in the SNAT match. This was not a defined env var.

### RC-4: DNAT action sets `eth_dst` to the final backend MAC, not the router MAC

The DNAT action rewrote `eth_dst` to the real backend's MAC (e.g. `00:00:00:00:00:05` on LAN2) and
outputted the packet to the router port. However, ethernet frames are hop-by-hop: the router only
accepts frames addressed to one of its own interface MACs. A frame with `eth_dst=00:00:00:00:00:05`
arrives at the router's `eth1`, is not destined for the router, and is silently discarded by the
kernel before any L3 forwarding occurs.

The fix: set `eth_dst=ROUTER_MAC` (the router's LAN-side interface MAC) so the router accepts the
frame, then forwards it based on `ipv4_dst` to the correct remote backend.

---

## Fixes

### Fix 1: Set `ROUTER_OVS_PORT=3` in shared env

**File:** `source/scripts/osken-controller.env`

The router connects as the 3rd port on both bridges (veth3 → ovs-br0 port 3, veth23 → ovs-br1 port 3). Added:

```env
ROUTER_OVS_PORT=3
```

### Fix 2: Add `ROUTER_MAC` per controller

**File:** `source/scripts/build_network_setup.sh`

Each controller receives its local router interface MAC via `-e ROUTER_MAC=`:

| Controller | Bridge | Router interface | MAC |
|-----------|--------|-----------------|-----|
| osken | ovs-br0 | eth1 | `00:00:00:00:00:AA` |
| osken_2 | ovs-br1 | eth2 | `00:00:00:00:00:CC` |

**File:** `source/scripts/osken-controller.env`

Added `ROUTER_MAC=` (empty default, overridden per-container).

### Fix 3: Use `ROUTER_MAC` in SNAT match for cross-network backends

**File:** `source/sdn_controller/vip_routing.py`

Added `_ROUTER_MAC` module-level variable read from env. In `_install_vip_dnat_snat()`:

1. Track `is_cross_network = True` when backend is in `peer_hosts` and routed via `_ROUTER_OVS_PORT`
2. When `is_cross_network and _ROUTER_MAC`, the SNAT match uses `eth_src=_ROUTER_MAC` instead of `eth_src=real_backend_mac`
3. All other SNAT match fields (`eth_dst=client_mac`, `ipv4_src=real_backend_ip`, `ipv4_dst=client_ip`) remain unchanged — the router preserves L3 headers

### Fix 4: Use `ROUTER_MAC` in DNAT action `eth_dst` for cross-network backends

**File:** `source/sdn_controller/vip_routing.py`

For cross-network backends the DNAT action must address the frame to the router's LAN-side
interface MAC, not the final backend MAC.  Standard L3 hop-by-hop forwarding requires
`eth_dst = next-hop MAC` at every segment boundary.

```python
# Before (bug — router discards frame, eth_dst not one of its own MACs):
dnat_actions = [
    OFPActionSetField(eth_dst=real_backend_mac),
    OFPActionSetField(ipv4_dst=real_backend_ip),
    OFPActionOutput(ROUTER_OVS_PORT),
]

# After (fix — router accepts frame and L3-forwards based on ipv4_dst):
dnat_eth_dst = ROUTER_MAC if is_cross_network else real_backend_mac
dnat_actions = [
    OFPActionSetField(eth_dst=dnat_eth_dst),
    OFPActionSetField(ipv4_dst=real_backend_ip),
    OFPActionOutput(ROUTER_OVS_PORT),
]
```

---

## Packet Flow After Fix

### Forward path (client → VIP → cross-network backend)

```
1. Client (10.0.0.30) sends to VIP_SERVER (10.0.0.100, VIP MAC aa:bb:cc:dd:ee:01)
2. OVS-br0 punt rule → controller PacketIn
3. select_server() picks edge_server_n2 (00:00:00:00:00:05, 10.0.1.2, in peer_hosts)
4. _install_vip_dnat_snat():
     is_cross_network = True, backend_port = ROUTER_OVS_PORT (3)
     DNAT rule: match(eth_dst=VIP_MAC, ipv4_dst=VIP_IP)
                → set eth_dst=00:00:00:00:00:AA (ROUTER_MAC, Fix 4)
                   set ipv4_dst=10.0.1.2
                   output port 3
     SNAT rule: match(eth_src=00:00:00:00:00:AA, ipv4_src=10.0.1.2, ipv4_dst=10.0.0.30)
                → set eth_src=aa:bb:cc:dd:ee:01 (VIP MAC)
                   set ipv4_src=10.0.0.100 (VIP IP)
                   output client port
5. Packet-Out exits OVS-br0 port 3 with:
     eth_dst = 00:00:00:00:00:AA  ← router's eth1 MAC (next-hop)
     ipv4_dst = 10.0.1.2          ← real backend IP preserved
6. Router eth1 receives frame: eth_dst matches own MAC → accepted by kernel
7. Kernel IP forwarding: ipv4_dst=10.0.1.2 → route 10.0.1.0/24 via eth2
     Router ARPs for 10.0.1.2 on eth2 → resolves to 00:00:00:00:00:05
     Router rewrites MACs:
       eth_src = 00:00:00:00:00:CC  (router eth2 MAC)
       eth_dst = 00:00:00:00:00:05  (backend MAC, ARP-resolved)
8. Packet enters OVS-br1 via veth23 → normal L2 forwarding → edge_server_n2
     ipv4_dst = 10.0.1.2 (real IP, not a VIP) → osken_2 does not intercept
```

### Return path (backend response → client)

```
1. edge_server_n2 (10.0.1.2) replies to client (10.0.0.30)
2. ovs-br1 normal forwarding → router port (no VIP involvement on LAN2)
3. Router receives on eth2, routes to 10.0.0.30 via eth1
4. Router rewrites MACs: eth_src=00:00:00:00:00:AA, eth_dst=<client_mac>
5. Packet enters ovs-br0 port 3
6. SNAT rule matches:
   eth_src=00:00:00:00:00:AA ✓ (router MAC, not backend MAC)
   ipv4_src=10.0.1.2 ✓
   ipv4_dst=10.0.0.30 ✓
7. Actions: eth_src→aa:bb:cc:dd:ee:01 (VIP MAC), ipv4_src→10.0.0.100 (VIP)
8. Output to client port → client sees response from VIP ✅
```

---

## Files Changed

| File | Change |
|------|--------|
| `source/scripts/osken-controller.env` | Added `ROUTER_OVS_PORT=3` and `ROUTER_MAC=` |
| `source/scripts/build_network_setup.sh` | Added `-e ROUTER_MAC="00:00:00:00:00:AA"` (osken) and `-e ROUTER_MAC="00:00:00:00:00:CC"` (osken_2) |
| `source/sdn_controller/vip_routing.py` | Added `_ROUTER_MAC` env var; SNAT match uses router MAC (Fix 3); DNAT `eth_dst` uses router MAC for cross-network (Fix 4) |

---

## Assumptions

- The router is always port 3 on both bridges (3rd `add-port` in `build_network_1.sh` / `build_network_2.sh`)
- The router does **not** NAT/MASQUERADE inter-LAN traffic (only Internet-bound traffic) — `ipv4_src` is preserved through the router
- Each bridge has exactly one router port (no multi-path)
