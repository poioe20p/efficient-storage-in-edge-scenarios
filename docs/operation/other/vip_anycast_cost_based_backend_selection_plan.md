# Concrete Implementation Plan: VIP Anycast + Cost-Based Backend Selection (Hop + Server Link Debit)

## Objective
Implement a **virtual service IP (VIP)** (e.g., `10.0.0.100`) so clients always target the VIP, while the controller selects the backend server (MongoDB host) **per new flow** based on:

- **Hop count** (link-hops) from client host → backend host, and
- **Server-facing link debit** (bps) from the statistics already produced/persisted by the port-stats controller.

This plan is the concrete “code-change” version of Milestone 5 in the VIP model described in [docs/operation/link_debit_stats_and_redirect_plan.md](docs/operation/link_debit_stats_and_redirect_plan.md).

---

## Key Design Decisions (important for correctness)

### 1) Where NAT rewrite must happen
Your proactive L2 path rules (in the topology apps) match on `eth_src` + `eth_dst`. Because of that:

- **DNAT (client → VIP → backend)** can happen at the **client’s edge switch** (the switch the client host is attached to). Intermediate switches will still see `eth_src=client_mac, eth_dst=backend_mac`, so existing L2 path flows keep working.

- **SNAT (backend → client; make reply appear from VIP)** must **also happen at the client’s edge switch (last hop)**.
  - If you rewrite `eth_src` to `VIP_MAC` at the backend side or mid-path, intermediate switches will no longer match their flows (they expect `eth_src=backend_mac`).
  - Rewriting at the client edge switch works because after rewrite the packet goes directly out the host-facing port (no more intermediate switches).

This single detail prevents “it works for one-switch topologies but breaks for multi-switch paths”.

### 2) Proactive ARP reply rule installation
The ARP reply rule you provided uses OVS/Nicira extensions (`move:NXM_*`). Installing that exact rule from OS-Ken is usually not portable.

Plan:
- Install the ARP reply rule via `ovs-ofctl` in the setup scripts (preferred).
- Add a controller ARP fallback (optional) so experiments still run even if the proactive rule is not installed.

### 3) Cache hop counts (topology is stable)
Hop counts are stable unless topology changes. Compute once per topology update and cache:

- `hop_cache[client_mac][server_mac] = hops`

### 4) Cache debit snapshots
Debit is sampled at ~5s in the stats apps. Cache the latest snapshot and refresh at the same cadence (or slightly slower) to avoid Mongo reads per packet.

---

## Scope (files to change)

### Controller (VIP + selection + flow install)
- [source/sdn_controller/osken_learn_and_log.py](source/sdn_controller/osken_learn_and_log.py)

### Topology graph and hop cache
- [source/sdn_controller/usecases/topology_n1.py](source/sdn_controller/usecases/topology_n1.py)
- [source/sdn_controller/usecases/topology_n2.py](source/sdn_controller/usecases/topology_n2.py)

### Debit stats read path
- [source/sdn_controller/library/repositories/debit.py](source/sdn_controller/library/repositories/debit.py) (already OK; reuse)
- [source/sdn_controller/calculate_stats_n1.py](source/sdn_controller/calculate_stats_n1.py) / `calculate_stats_n2.py` (already OK; reuse persistence)

### Setup scripts (recommended)
- [source/scripts/build_network_1.sh](source/scripts/build_network_1.sh)
- [source/scripts/build_network_2.sh](source/scripts/build_network_2.sh)

---

## Configuration (minimal)

Add these as env vars (or route through `config.py` if you prefer):

- `VIP_IP_LAN1=10.0.0.100`
- `VIP_IP_LAN2=10.0.1.100`
- `VIP_MAC=aa:bb:cc:dd:ee:ff`
- `VIP_SCORE_HOPS_WEIGHT=0.3`
- `VIP_SCORE_DEBIT_WEIGHT=0.7`
- `VIP_DEBIT_NORM_BPS=<bps>` (normalization constant; can reuse threshold)
- `VIP_DEBIT_REFRESH_SEC=5`
- `VIP_FLOW_IDLE_TIMEOUT_SEC=15` (keeps per-flow pinning short and adaptive)

Normalization is mandatory for the 30/70 weighting to be meaningful.

Recommended score:

$$score = 0.3\cdot\frac{hops}{max\_hops} + 0.7\cdot\min\left(1,\frac{debit\_bps}{VIP\_DEBIT\_NORM\_BPS}\right)$$

Where `max_hops` can be computed as the max hop value observed in the current hop cache (or a conservative constant).

---

## Step-by-step Code Changes

### Step A — Install the proactive ARP reply rule in scripts (recommended)

Edit [source/scripts/build_network_1.sh](source/scripts/build_network_1.sh) and [source/scripts/build_network_2.sh](source/scripts/build_network_2.sh) to add the VIP ARP reply rule on the **client-facing edge switch** (or on every switch if you want, but edge is enough).

Use the exact command from the design document (with VIP IP and VIP MAC).

Why scripts:
- preserves your exact `ovs-ofctl`/Nicira action semantics.
- avoids needing OS-Ken nicira action plumbing.

### Step B — Extend the base controller to parse ARP/IPv4/ICMP

Modify [source/sdn_controller/osken_learn_and_log.py](source/sdn_controller/osken_learn_and_log.py):

1) Imports:
- Add packet protocol parsing for:
  - `arp`
  - `ipv4`
  - `icmp`

2) Add VIP configuration fields in `__init__`:
- `self.vip_ip` (per LAN app; can be overridden by subclasses)
- `self.vip_mac`
- weights + normalization:
  - `self.vip_w_hops`, `self.vip_w_debit`, `self.vip_debit_norm_bps`
- caches:
  - `self._debit_cache = {"ts": 0, "by_server_mac": {}}`

3) In `switch_features_handler`, install a “punt VIP traffic” rule:

For ICMP ping to VIP (OpenFlow 1.3 match fields):
- match: `eth_type=0x0800, ipv4_dst=<VIP>, ip_proto=1, icmpv4_type=8`
- actions: `OUTPUT:CONTROLLER`
- priority: higher than your general learned/proactive forwarding, e.g. `priority=100`

This guarantees the *first packet* of each new VIP ping reaches the controller even if other forwarding rules exist.

4) Optional: controller ARP fallback
If you did not install the proactive ARP rule in scripts, handle ARP requests for VIP in `packet_in_handler`:
- If `arp_op==1` and `arp_tpa==VIP`, craft ARP reply `VIP is-at VIP_MAC` and `PacketOut` to `in_port`.

If scripts install proactive ARP, this handler can remain as a safety net.

### Step C — Add hop-cache + “edge switch” lookup in topology apps

Modify [source/sdn_controller/usecases/topology_n1.py](source/sdn_controller/usecases/topology_n1.py) and [source/sdn_controller/usecases/topology_n2.py](source/sdn_controller/usecases/topology_n2.py):

1) Track host attachment map on each topology refresh:
- `self.host_attachment[host_mac] = (switch_dpid, port_no)`

2) Compute hop cache only when topology changes:
- On any change to `hosts/links/sws`:
  - Build `servers_present = [mac for mac in self.servers_mac if mac in self.host_attachment]`
  - For each `host_mac` in `host_attachment` (excluding servers if you want):
    - For each `server_mac` in `servers_present`:
      - `hops = len(nx.shortest_path(self.net, host_mac, server_mac)) - 1`
      - store in `self.hop_cache[host_mac][server_mac]`

3) Expose a small helper API (used by VIP selection):
- `get_edge_switch(host_mac) -> (dpid, port_no) | None`
- `get_hops(host_mac, server_mac) -> int | None` (reads cache)

Rationale:
- This keeps hop computation close to where topology is already maintained.

### Step D — Read server debit from Mongo (reuse existing stats)

In the VIP selection logic (controller side), read debit snapshots using:

- `DebitRepository(MongodbRouter().get_simple_connection_string(add_app=True)).get_debit_by_lan_id(lan_id)`

Then build:
- `server_debit_bps_by_mac[peer_mac] = flow_rate`

Filtering exactly matches what you already print in the stats code:
- `neighbor_switch_id is None` (host-facing)
- `peer_mac in self.servers_mac`

Cache refresh policy:
- refresh from Mongo only if `now - last_refresh >= VIP_DEBIT_REFRESH_SEC`

### Step E — Backend selection and NAT flow installation (ICMP first)

Modify `packet_in_handler` in [source/sdn_controller/osken_learn_and_log.py](source/sdn_controller/osken_learn_and_log.py) (or, preferably, in the LAN-specific apps that inherit it):

1) Detect VIP ICMP request:
- Parse `ipv4` and `icmp`
- If `ipv4.dst == VIP` and `icmp.type == 8`:
  - treat as a new VIP flow

2) Identify client MAC and its edge switch:
- `client_mac = eth.src`
- `client_edge = get_edge_switch(client_mac)` from topology (or from `self.hosts` list)
- Only install NAT rules on that `client_edge_dpid`.

3) Choose backend:
For each server MAC in `self.servers_mac`:
- `hops = hop_cache[client_mac][server_mac]`
- `debit_bps = server_debit_bps_by_mac.get(server_mac, 0)`
- `score = 0.3*(hops/max_hops) + 0.7*min(1,debit_bps/norm_bps)`
Pick min score.

4) Install DNAT rule on the client edge switch:
- match (ICMP echo request to VIP):
  - `eth_type=0x0800`
  - `eth_src=client_mac` (optional but recommended to keep it per-client)
  - `ipv4_dst=VIP`
  - `ip_proto=1`
  - `icmpv4_type=8`
- actions:
  - `set_field:backend_ip -> ipv4_dst`
  - `set_field:backend_mac -> eth_dst`
  - `OUTPUT: <next-hop-port>` (from topology path, i.e. the port on client edge switch toward the next node)
- `idle_timeout = VIP_FLOW_IDLE_TIMEOUT_SEC`

5) Install SNAT rule on the *same* client edge switch:
- match (ICMP echo reply coming back to client):
  - `eth_type=0x0800`
  - `eth_dst=client_mac`
  - `eth_src=backend_mac` (important: match before rewrite)
  - `ipv4_src=backend_ip`
  - `ip_proto=1`
  - `icmpv4_type=0`
- actions:
  - `set_field:VIP -> ipv4_src`
  - `set_field:VIP_MAC -> eth_src`
  - `OUTPUT: <client_port_no>` (host-facing port from attachment map)
- `idle_timeout = VIP_FLOW_IDLE_TIMEOUT_SEC`

6) PacketOut the first packet
After installing DNAT/SNAT rules, forward the triggering ICMP request immediately:
- Send `PacketOut` from the client edge switch with the DNAT actions and output to the next-hop port.

This avoids waiting for the host to retransmit.

### Step F — Extend to TCP SYN (later)
Once ICMP works:
- Match `ip_proto=6` (TCP)
- Use per-5tuple matching:
  - `ipv4_src`, `ipv4_dst=VIP`, `tcp_src`, `tcp_dst`, `ip_proto=6`
- DNAT to backend IP and (optionally) rewrite `eth_dst` to backend MAC.
- SNAT on replies to rewrite `ipv4_src` to VIP and `eth_src` to VIP_MAC.

Important:
- Keep the rewrite on the client edge switch for the same reason as ICMP.

---

## How this integrates with your existing proactive L2 flows

- You can keep your existing proactive host-to-host flows in the topology apps.
- VIP NAT rules are **higher priority** and only apply to VIP traffic.
- After DNAT, packets look like ordinary client→backend traffic and will match existing L2 path rules.
- Replies look like ordinary backend→client traffic until the last hop (client edge), where SNAT makes them appear from VIP.

---

## Observability (add logs)

Add a single greppable log line on each selection:

- `VIP_SELECT lan_id=lan_1 vip=10.0.0.100 client_mac=<...> backend_mac=<...> hops=<n> debit_bps=<x> score=<y>`

This is enough to correlate decisions with:
- hop cache,
- debit snapshots,
- observed traffic.

---

## Validation Checklist

1) ARP
- `arp -n` on a host shows `VIP -> VIP_MAC`.

2) ICMP
- `ping VIP` works.
- The controller prints `VIP_SELECT`.
- `ovs-ofctl dump-flows` shows DNAT + SNAT rules on the client edge switch.

3) Debit influence
- Generate traffic to increase one server’s port debit.
- Start a new VIP flow and verify selection flips (if hop difference is not dominant).

4) Multi-switch correctness
- Verify VIP works when client and backend are not on the same switch (ensures SNAT is at client edge, not mid-path).

---

## Implementation Order (recommended)

1) Script-level ARP reply rule for VIP (fast to validate).
2) ICMP VIP punt rule + controller DNAT/SNAT on client edge.
3) Hop cache computed in topology apps.
4) Debit cache read from Mongo.
5) Weighted score selection.
6) TCP SYN support.
