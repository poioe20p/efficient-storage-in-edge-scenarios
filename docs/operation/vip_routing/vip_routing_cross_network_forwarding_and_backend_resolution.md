# VIP Routing Cross-Network Forwarding and Backend Resolution

## 1. Purpose

This document describes how the controller resolves backend IP and MAC
addresses, determines the output port for DNAT'd packets, and handles the
differences between local and cross-network (peer-LAN) forwarding paths. It
covers the packet-walkthrough details specific to forwarding and resolution --
backend selection logic and ARP interception are documented separately.

## 2. Current Files

| File | Role |
|------|------|
| `source/sdn_controller/vip_routing.py` | `VipRoutingMixin` -- `_install_vip_dnat_snat()`, `snoop_arp()`, `register_backend_ip()` |
| `source/sdn_controller/main_n1.py` | Entry point -- MRO and `packet_in_handler()` |
| `source/sdn_controller/topology/topology.py` | `TopologyMixin` -- `get_next_hop_port()`, `host_attachment`, `peer_hosts`, `on_topology_update()` |

## 3. Backend IP and MAC Resolution

For DNAT/SNAT rules the controller needs both the MAC and IP of the selected
backend. The `_mac_to_ip` / `_ip_to_mac` dictionaries are populated from three
sources in priority order (later sources overwrite earlier ones):

### 1. ARP Snooping (`snoop_arp()`) -- Authoritative

Every `PacketIn` calls `snoop_arp(pkt)` before VIP dispatch. It records
`src_ip → src_mac` and `src_mac → src_ip` from the ARP sender fields of any
ARP packet that reaches the controller. This is the authoritative source and
overwrites statically seeded entries if the container's IP ever changes.

### 2. Static Seed (`register_backend_ip()`) -- Bootstrap

`register_backend_ip(mac, ip)` directly writes entries into both dictionaries.
It is called in two contexts:

- **Thread 3 (elasticity):** `register_new_server_backend(mac, ip)` calls it
  immediately after adding a new MAC to `vip_server_pool`, so Thread 1 can
  route the very first packet to the new backend without waiting for ARP.
- **Peer topology seeding:** `TopologyMixin.on_topology_update()` calls it for
  every peer host that carries an `ip` field in its `TopologyHostEntry`. This
  ensures the controller can route to peer backends immediately without
  waiting for cross-network ARP traffic (which never reaches the local
  controller anyway).

### 3. Flush + Ping Bootstrap -- Startup

Instead of `arping` (which may not be installed in containers), the network
setup scripts use `ip neigh flush` + `ping` to force ARP resolution at
startup. The resulting ARP packets reach the controller and populate
`_mac_to_ip` via `snoop_arp()`.

### Resolution at Selection Time

Both `_handle_vip_server()` and `_handle_vip_data()` check `_mac_to_ip` for
the selected backend MAC before installing rules. If the IP is unknown, the
packet is dropped with a warning log -- the controller waits for the backend's
ARP to arrive rather than installing rules with incomplete information.

## 4. Output Port Resolution

`_install_vip_dnat_snat()` resolves the output port for the DNAT rule in a
strict fallback order:

### 1. `get_next_hop_port(dpid, client_mac, backend_mac)` -- Preferred

Computes the shortest path in the topology graph via NetworkX, then returns
the switch port on `dpid` that leads to the next hop toward `backend_mac`.
This is the preferred method for multi-switch topologies. Returns `None` if no
path exists.

### 2. `host_attachment[backend_mac]` -- Local Direct

Fallback for single-switch topologies where the backend is directly connected
to this controller's OVS bridge. Returns `(dpid, port_no)`. Populated by
`TopologyMixin` from OS-Ken's host tracker.

### 3. `ROUTER_OVS_PORT` -- Peer Backend via Router

Fallback when the backend MAC is found in `peer_hosts` and cross-network
routing is enabled (`ROUTER_OVS_PORT > 0`). The packet is forwarded to the
inter-LAN router for L3 delivery to the peer LAN.

### 4. Safe Drop

If none of the above resolve a port, the packet is dropped with a warning log:
`"mac=<mac> not reachable from dpid=<dpid>, skipping"`.

## 5. Local Backend Path

When the selected backend is directly attached to the local OVS switch
(backend MAC found in `host_attachment`), forwarding is straightforward:

1. **DNAT rule** outputs to the backend's OVS port. `eth_dst` is set to the
   real backend MAC.
2. The OVS switch delivers the rewritten frame directly to the backend
   container's veth interface.
3. **SNAT rule** matches on `eth_src=backend_mac` (the real MAC) and rewrites
   it to `VIP_MAC` on the return path.
4. The client sees the reply from the VIP address -- it never learns the real
   backend MAC or IP.

No router involvement is needed for local backends.

## 6. Peer Backend Path

When the selected backend resides on the peer LAN (backend MAC found in
`peer_hosts`), the packet must traverse the inter-LAN router:

### Forward Path (Client → VIP → Cross-Network Backend)

1. **DNAT rule** outputs to `ROUTER_OVS_PORT` (the OVS port connected to the
   router), not the backend's own OVS port.
2. **`eth_dst` is set to `ROUTER_MAC`** (the router's LAN-side interface
   MAC), not the real backend MAC. This is critical: if `eth_dst` were set to
   the backend MAC, the router's kernel would silently drop the frame because
   it is not destined for any of the router's own interfaces. By addressing
   the frame to `ROUTER_MAC`, the router's kernel IP stack accepts it for L3
   forwarding.
3. **`ipv4_dst` remains the real backend IP.** The router performs standard L3
   forwarding based on the destination IP: it looks up the route, rewrites
   `eth_src` to its own egress interface MAC, rewrites `eth_dst` to the
   backend MAC (from its ARP table on the peer LAN), and decrements TTL.
4. The packet arrives at the peer LAN's OVS as a normal L2 frame addressed to
   the backend MAC. No second VIP interception occurs because `ipv4_dst` is
   the real backend IP, not a VIP address.

### Return Path (Backend → Client)

1. The backend responds normally. The peer LAN's OVS forwards the frame toward
   the router (or directly if the client is on the same LAN).
2. The router performs L3 forwarding: it rewrites `eth_src` to its own LAN MAC
   (on the originating controller's LAN) and `eth_dst` to the client MAC.
3. The frame arrives at the originating controller's OVS with
   **`eth_src=ROUTER_MAC`**, not the real backend MAC.
4. **SNAT rule matches on `eth_src=ROUTER_MAC`** and rewrites
   `eth_src → VIP_MAC`, `ipv4_src → VIP_IP`.
5. The client sees the response from the VIP address -- it never learns that
   the backend is on a different LAN.

## 7. Router MAC Return Path

The SNAT match for cross-network traffic uses `ROUTER_MAC` instead of the real
backend MAC because the router rewrites `eth_src` during L3 forwarding. The
key differences from local-backend SNAT:

| Aspect | Local Backend | Cross-Network Backend |
|--------|--------------|----------------------|
| SNAT `eth_src` match | Real backend MAC | `ROUTER_MAC` |
| Reason | Backend is L2-adjacent | Router rewrites `eth_src` during L3 forwarding |

Each controller receives its own `ROUTER_MAC` via the `ROUTER_MAC` environment
variable in the `docker run` command within `build_network_setup.sh`. If
`ROUTER_MAC` is not set or is empty, cross-network forwarding is effectively
disabled even if `ROUTER_OVS_PORT > 0`, because the DNAT rule cannot construct
a valid `eth_dst` for the router and the SNAT rule cannot match return traffic.

## 8. Failure Cases and Safe Drops

The controller handles several forwarding failure cases gracefully:

| Failure | Behaviour |
|---------|-----------|
| Backend IP unknown (`_mac_to_ip` miss) | Packet dropped; controller waits for ARP from backend |
| No route via `get_next_hop_port()` | Falls through to `host_attachment` and `ROUTER_OVS_PORT` checks |
| Backend not in `host_attachment` or `peer_hosts` | Packet dropped with warning: `"mac=<mac> not reachable"` |
| `ROUTER_OVS_PORT == 0` and backend is peer | Packet dropped (cross-network routing disabled) |
| `ROUTER_MAC` not set and backend is peer | DNAT `eth_dst` falls back to real backend MAC; frame silently dropped by router |

In all drop cases, no flow rules are installed and the packet is not forwarded.
The client experiences a timeout and may retry; on retry the controller gets
another `PacketIn` and attempts fresh backend selection with updated state.

## 9. First-Packet Packet-Out

After installing the DNAT and SNAT flow rules, `_install_vip_dnat_snat()`
sends an `OFPPacketOut` message with the DNAT actions applied to the original
buffered packet data. This ensures the first packet reaches the backend
immediately while the new flow rules propagate through the OVS pipeline.

The `PacketOut` uses the same DNAT actions that were installed in the flow
rule, including the cross-network `eth_dst=ROUTER_MAC` rewrite when
applicable. This means the first packet follows the exact same path as
subsequent packets that hit the cached flow rule.

## 10. Related Diagrams

| Diagram | File |
|---------|------|
| VIP_SERVER routing (client to edge server, including cross-network path) | [`diagram/vip_server_routing.drawio`](diagram/vip_server_routing.drawio) |
| VIP_DATA routing (edge server to storage, including cross-network path) | [`diagram/vip_data_routing.drawio`](diagram/vip_data_routing.drawio) |
