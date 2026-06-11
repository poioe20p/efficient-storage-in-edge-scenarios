# VIP Routing Interception and Flow Rules

## 1. Purpose

This document describes how the controller intercepts traffic destined for
virtual IP (VIP) addresses, generates ARP replies, installs punt rules, and
dispatches packets to DNAT/SNAT flow rule installation. It covers the
controller-side interception pipeline only -- backend selection logic and
edge-side epoch behaviour are documented separately.

## 2. Current Files

| File | Role |
| ---- | ---- |
| `source/sdn_controller/vip_routing.py` | Public `VipRoutingMixin` facade -- cooperative hooks and controller-facing API |
| `source/sdn_controller/_vip_routing/ingress.py` | ARP snooping, VIP intercept, ARP reply generation, VIP server and data handlers, punt rule management |
| `source/sdn_controller/_vip_routing/flows.py` | DNAT/SNAT rule installation and first-packet `PacketOut` |
| `source/sdn_controller/main_n1.py`, `source/sdn_controller/main_n2.py` | Controller entry points -- define `KenLearnAndLog(VipRoutingMixin, TopologyMixin, OSKenApp)` and `packet_in_handler()` |

## 3. Thread 1 Entry Path

All VIP interception runs inline in Thread 1's `packet_in_handler()`, which is
the OS-Ken event loop callback for OpenFlow `PacketIn` messages. The dispatch
order inside `packet_in_handler()` is:

1. Parse the Ethernet and IP headers from the raw `PacketIn` data.
2. Call `snoop_arp(pkt)` -- records sender IP↔MAC for every ARP packet that
   reaches the controller, regardless of whether it targets a VIP.
3. Call `handle_vip_packet_in(datapath, in_port, pkt, eth)`. If this returns
   `True`, the packet was handled by VIP logic and the handler returns
   immediately without running L2 learning or flooding.
4. If the packet is not VIP traffic, fall through to normal L2 MAC learning
   and forwarding.

The MRO requirement is that `VipRoutingMixin` sits **before** `TopologyMixin`:

```python
class KenLearnAndLog(VipRoutingMixin, TopologyMixin, OSKenApp):
    ...
```

This ensures `VipRoutingMixin._on_datapath_connected()` runs first after a
switch reconnect through the extension hook that `TopologyMixin` invokes after
it flushes stale flows and reinstalls the table-miss rule. The facade then
chains through `super()._on_datapath_connected(datapath)` to
`TopologyMixin`'s no-op hook before reinstalling VIP punt rules.

## 4. VIP Address Binding Set

`_iter_vip_bindings()` yields three `(vip_ip, vip_mac, domain)` tuples that
drive all punt rule installation, ARP matching, and packet dispatch:

| Binding | Domain |
| ------- | ------ |
| `VIP_SERVER` | `"server"` |
| `VIP_DATA_N1` | `"n1"` |
| `VIP_DATA_N2` | `"n2"` |

Recovery VIP bindings (`VIP_DATA_RECOVERY_N1`, `VIP_DATA_RECOVERY_N2`) were
removed in v5.x. They were a workaround for stale OVS flow rules on backend
unregister — now eliminated by conntrack-based flow rules (see § 10).

## 5. ARP Snooping and VIP ARP Replies

### ARP Snooping

`snoop_arp(pkt)` is called on **every** `PacketIn` before VIP dispatch. It
extracts the ARP protocol layer and records `src_ip → src_mac` and
`src_mac → src_ip` in the `_ip_to_mac` / `_mac_to_ip` dictionaries. Entries
with `src_ip == "0.0.0.0"` are skipped. ARP snooping is the authoritative
source for backend IP resolution and overwrites any statically seeded entries.

### VIP ARP Replies

When a client sends an ARP request for a VIP address, the controller does not
flood it -- it generates a crafted ARP reply. `handle_vip_packet_in()` detects
ARP requests (`opcode == ARP_REQUEST`) where `dst_ip` matches any VIP binding
and delegates to `_reply_vip_arp()`.

`_reply_vip_arp()` constructs an Ethernet + ARP reply packet with:

- `eth_src = VIP_MAC` (the virtual MAC)
- `arp_src_mac = VIP_MAC`, `arp_src_ip = VIP_IP`
- `eth_dst = requester MAC`, `arp_dst_mac = requester MAC`

The reply is sent via `OFPPacketOut` on the ingress port so the requester
associates the VIP IP with the virtual MAC. The real backend MAC is never
exposed to clients.

## 6. VIP ARP and IP Punt Rules

To ensure VIP-destined traffic always reaches the controller instead of being
flooded by lower-priority L2 rules, persistent punt rules are installed at
priority 100 on every switch reconnect.

### ARP Punt Rules (`install_vip_arp_punt_rules()`)

For each VIP binding, installs:

```text
priority=100, eth_type=0x0806, arp_tpa=<VIP_IP> → output=CONTROLLER
```

This overrides the topology layer's ARP flood rule (priority 1). The
controller replies with the crafted ARP reply described in Section 5.

### IP Punt Rules (`install_vip_punt_rules()`)

For each VIP binding, installs:

```text
priority=100, eth_type=0x0800, ipv4_dst=<VIP_IP> → output=CONTROLLER
```

Once DNAT rules (priority 200) are installed they take precedence and
subsequent packets bypass the controller entirely. When the DNAT rule expires
(idle or hard timeout) the priority-100 punt rule resumes and triggers fresh
backend selection on the next packet.

## 7. VIP Packet Dispatch

`handle_vip_packet_in()` dispatches based on the destination IP:

| Destination IP | Handler | Notes |
| -------------- | ------- | ----- |
| `VIP_SERVER` | `_handle_vip_server()` | Selects edge server, installs DNAT/SNAT |
| `VIP_DATA_N1` | `_handle_vip_data(domain="n1")` | Selects LAN 1 storage |
| `VIP_DATA_N2` | `_handle_vip_data(domain="n2")` | Selects LAN 2 storage |
| `VIP_DATA_RECOVERY_N1` | `_handle_vip_data(domain="n1", recovery=True)` | Narrow-flow recovery |
| `VIP_DATA_RECOVERY_N2` | `_handle_vip_data(domain="n2", recovery=True)` | Narrow-flow recovery |

Only ICMP (1), TCP (6), and UDP (17) are handled as valid `ip_proto` match
values. Other protocols (ESP, GRE, etc.) pass through to normal L2 processing
-- they are not valid OpenFlow `ip_proto` match values for the rule set and
would produce a controller error if passed to `OFPMatch`.

Both `_handle_vip_server()` and `_handle_vip_data()` follow the same pattern:

1. Call the selector (`select_server()` or `select_storage()`).
2. If the pool is empty, log a warning and drop the packet (return `True`).
3. Resolve the backend IP from `_mac_to_ip`. If unknown, log a warning and
   wait for ARP from the backend (return `True`).
4. Call `_install_vip_dnat_snat()` with the chosen backend.

## 8. DNAT and SNAT Rule Installation

`_install_vip_dnat_snat()` installs a flow rule pair at priority 200 and
Packet-Outs the first packet so it reaches the backend while the rules
propagate through the OVS pipeline.

### DNAT Rule (Forward Path)

```text
priority=200
match: eth_type=0x0800, eth_src=<client_mac>, eth_dst=<VIP_MAC>,
       ipv4_src=<client_ip>, ipv4_dst=<VIP_IP>, ip_proto=<proto>
actions: set_field(eth_dst=<backend_mac>), set_field(ipv4_dst=<backend_ip>),
         output=<backend_port>
```

### SNAT Rule (Return Path)

```text
priority=200
match: eth_type=0x0800, eth_src=<backend_mac>, eth_dst=<client_mac>,
       ipv4_src=<backend_ip>, ipv4_dst=<client_ip>, ip_proto=<proto>
actions: set_field(eth_src=<VIP_MAC>), set_field(ipv4_src=<VIP_IP>),
         output=<client_port>
```

### Key Design Decisions

**Source port exclusion.** TCP/UDP source port is intentionally omitted from
the match in normal (non-recovery) flows. For `VIP_DATA`, one rule per
`(web_server_ip, domain_VIP)` pair covers all concurrent MongoDB connections
from that server, preventing tier-transition read inconsistency. For
`VIP_SERVER`, it ensures per-client server affinity across parallel HTTP
sub-connections.

**Default timeouts.** Normal flows use `VIP_IDLE_TIMEOUT` (30 s) and
`VIP_HARD_TIMEOUT` (120 s). Recovery flows use narrower timeouts (see Section
9).

**Output port resolution order:**

1. `get_next_hop_port(dpid, client_mac, backend_mac)` -- preferred for
   multi-switch topologies.
2. `host_attachment[backend_mac]` -- fallback for single-switch (backend
   directly connected to this controller's OVS).
3. `ROUTER_OVS_PORT` -- fallback when the backend is in `peer_hosts` and
   cross-network routing is enabled (`ROUTER_OVS_PORT > 0`).
4. If no route is found, the packet is dropped with a warning log.

**Cross-network DNAT.** When the backend is on the peer LAN, `eth_dst` in the
DNAT rule is set to `ROUTER_MAC` (not the real backend MAC) so the router's
kernel IP stack accepts the frame for L3 forwarding.

**Cross-network SNAT.** When the backend is on the peer LAN, the SNAT match
uses `eth_src=ROUTER_MAC` (not the real backend MAC) because the router
rewrites `eth_src` to its own LAN MAC during L3 forwarding.

**First-packet Packet-Out.** After installing the flow rules,
`_install_vip_dnat_snat()` sends an `OFPPacketOut` with the DNAT actions
applied to the buffered packet data so the first packet reaches the backend
immediately.

## 9. Recovery-VIP Narrow Flow Behavior (Deprecated — Removed in v5.x)

> **Deprecated.** The recovery VIP mechanism was removed as part of the
> conntrack-based VIP_DATA routing changes. The stale-flow-rule problem it
> worked around is now solved at the source: conntrack enables safe deletion
> of forward rules on `unregister_storage_backend` without breaking
> established connections. See § 10 for the replacement architecture.

The section below is preserved for historical reference only.

## 9. Recovery-VIP Narrow Flow Behavior (Historical)

When `_handle_vip_data()` is called with `recovery=True` (destination IP
matches `VIP_DATA_RECOVERY_N1` or `VIP_DATA_RECOVERY_N2`), three differences
apply:

### Protocol and Port Validation

Only TCP packets destined for port 27018 (MongoDB) are accepted. Non-TCP
packets or TCP packets with a different destination port are dropped with a
warning log. This prevents the recovery VIP from accidentally intercepting
non-MongoDB traffic.

### TCP Port Scoping

The recovery DNAT and SNAT rules include `tcp_src` and `tcp_dst` in the match,
narrowing each rule pair to a single TCP connection. In the DNAT rule
`tcp_src=<client_port>, tcp_dst=27018` is matched; in the SNAT rule the ports
are swapped (`tcp_src=27018, tcp_dst=<client_port>`).

This contrasts with normal `VIP_DATA` rules, which omit transport ports to
allow one rule pair to cover all concurrent connections from a given edge
server.

### Narrower Timeouts

Recovery flows use:

| Timeout | Default | Purpose |
| ------- | ------- | ------- |
| `VIP_DATA_RECOVERY_IDLE_TIMEOUT` | 40 s | Bounds idle recovery connections |
| `VIP_DATA_RECOVERY_HARD_TIMEOUT` | 45 s | Hard limit on recovery flow lifetime |

These are intentionally shorter than the normal-flow timeouts (30 s / 120 s)
to bound recovery-path state. The hard timeout is only 5 s longer than the
idle timeout, meaning recovery flows are torn down quickly once the connection
goes idle.

### Recovery Backend Selection

The same `select_storage()` function is called, but with `recovery=True`. This
causes the selector to exclude the remembered last-normal backend when another
candidate exists (see the Backend Selection document). Recovery selections do
not overwrite the remembered normal choice.

## 10. Reconnect Reinstallation and Flow Priorities

### Switch Reconnect

`_on_datapath_connected(datapath)` is called by `TopologyMixin`'s state-change
handler after a switch reconnects and stale flows are flushed. It calls:

1. `super()._on_datapath_connected(datapath)` -- chains to `TopologyMixin`.
2. `install_vip_arp_punt_rules(datapath)` -- reinstalls ARP punt rules.
3. `install_vip_punt_rules(datapath)` -- reinstalls IP punt rules.

DNAT/SNAT rules (priority 200) are not reinstalled -- they were ephemeral
(installed with idle/hard timeouts) and will be recreated on the next
`PacketIn` that hits the priority-100 punt rules.

The MRO ordering (`VipRoutingMixin` before `TopologyMixin`) is critical here:
it ensures the facade's `_on_datapath_connected()` implementation is the hook
invoked by `TopologyMixin._state_change_handler()` after the stale-flow flush.
The facade then chains through `TopologyMixin`'s no-op extension hook via
`super()` before reinstalling VIP punt rules.

### Flow Priority Summary

| Priority | Rule | Installed By | Trigger |
| -------- | ---- | ------------ | ------- |
| 100 | VIP ARP punt → controller | `install_vip_arp_punt_rules()` | Switch connect |
| 100 | VIP IP punt → controller | `install_vip_punt_rules()` | Switch connect |
| 200 | DNAT/SNAT (per-flow, timed) | `_install_vip_dnat_snat()` | First VIP `PacketIn` |
| 200 | Forward rule (conntrack, per-client) | `install_vip_data_forward_rule()` | First VIP_DATA `PacketIn` |
| 200 | Reply rule (conntrack, per-client) | `install_vip_data_reply_rule()` | First VIP_DATA `PacketIn` |

## 11. Conntrack-Based VIP_DATA Routing

> **Added v5.x.** The conntrack architecture replaces static DNAT/SNAT for
> VIP_DATA with OVS connection-tracking-based rules. Design rationale is
> documented in [conntrack_vip_routing_design.md](implementation/plans/conntrack_vip_routing/conntrack_vip_routing_design.md);
> implementation steps in [conntrack_vip_routing_plan.md](implementation/plans/conntrack_vip_routing/conntrack_vip_routing_plan.md).

### Why Conntrack?

The v5.x experiment campaign identified stale OVS flow rules as the root cause
of 55–65% failure rates in compute phases. When a storage backend is removed
from the VIP_DATA pool, the existing static DNAT+SNAT rule pair was NOT
deleted. The stale rule continued to DNAT new TCP connections to the dead
backend for up to 120 s (hard timeout).

OVS conntrack separates **connection establishment** (flow rules) from
**connection state** (conntrack table). Once a connection is established, its
NAT mapping lives in the kernel conntrack table independently of the flow rule
that created it. The forward rule can be safely deleted — established
connections survive in conntrack, and new connections trigger a fresh
`select_storage` via the priority-100 punt rule.

### Rule Structure

Two rule types replace the old DNAT+SNAT pair:

**Forward rule** (per-client, per-domain):

```
Match: eth_src=client_mac, eth_dst=vip_mac, ipv4_src=client_ip, ipv4_dst=vip_ip, tcp_dst=27018
Action: ct(commit, zone=N, nat(dst=backend_ip)), set_field(eth_dst=backend_mac), output:port
Idle: 10 s | Hard: 120 s | Priority: 200 | Cookie: per-domain
```

**Reply rule** (per-client, per-domain):

```
Match: ct_state=+est+trk, ct_zone=N, eth_dst=client_mac, ipv4_dst=client_ip
Action: set_field(eth_src=vip_mac), output:in_port
Idle: 0 | Hard: 0 | Priority: 200 | Cookie: 0
```

### Key Design Points

| Concept | Detail |
| ------- | ------ |
| **Per-client match** | `eth_src` and `ipv4_src` scope the forward rule to one edge server — preserves per-client WSM load distribution |
| **No `tcp_src`** | All TCP connections from the same client route to the same backend; pymongo connection pools are handled correctly |
| **ct_zone differentiation** | Zone 1 for n1, zone 2 for n2 — prevents reply rule collision for the same client across domains |
| **Bulk deletion by cookie** | All forward rules for a domain share one cookie — `unregister_storage_backend` deletes them in one `OFPFC_DELETE` |
| **Reply rules never expire** | Conntrack manages the connection lifecycle; the reply rule just gates established traffic |
| **Idle timeout 10 s** | Reduced from 30 s — the 10 s fallback ensures stale rules don't persist if proactive deletion fails |
| **Safe deletion** | Deleting the forward rule cannot affect in-flight connections — their NAT state lives in kernel conntrack, not in OVS |

### Connection Lifecycle

```
NEW CONNECTION:
  SYN → matches forward rule → ct(commit) creates conntrack entry
  → DNAT to backend → reply packets match reply rule via ct_state=+est+trk

ESTABLISHED CONNECTION:
  All subsequent packets match the reply rule → ct(nat) reverses NAT
  → Forward rule never consulted again for this connection

AFTER FORWARD RULE DELETED (unregister_storage_backend):
  Established connections: reply rules + conntrack still handle them ✅
  New SYNs: no matching forward rule → punt rule → controller → fresh select_storage() ✅
```

### Comparison: Static NAT vs Conntrack

| Aspect | Static NAT | Conntrack |
| ------ | ---------- | --------- |
| Forward mechanism | `SetField(ipv4_dst, eth_dst)` | `ct(commit, nat(dst=...))` |
| Reply mechanism | `SetField(ipv4_src, eth_src)` with backend match | `ct_state=+est+trk` match with `SetField(eth_src)` |
| Connection state | In the flow rule itself | In kernel conntrack table |
| Safe to delete rule? | ❌ Breaks in-flight connections | ✅ Conntrack entries survive |
| Stale rule window | 30–120 s (idle/hard timeout) | 0 s (proactive deletion on unregister) |
| Rule count | 2 per client per domain (DNAT + SNAT) | 2 per client per domain (forward + reply) |

Lower-priority rules (0--10) are installed by `TopologyMixin` (ARP flood at
priority 1, L2 forwarding at lower priorities).

## 11. Related Diagrams

| Diagram | File |
| ------- | ---- |
| VIP_SERVER routing (client to edge server) | [`diagram/vip_server_routing.drawio`](diagram/vip_server_routing.drawio) |
| VIP_DATA routing (edge server to storage) | [`diagram/vip_data_routing.drawio`](diagram/vip_data_routing.drawio) |
