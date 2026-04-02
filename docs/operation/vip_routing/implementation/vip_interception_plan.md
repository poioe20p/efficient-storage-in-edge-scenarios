# VIP Interception Implementation Plan

## Overview

Add OpenFlow-based interception of **VIP_SERVER** (HTTP) and **VIP_DATA** (MongoDB) traffic to the existing OS-Ken SDN controller. A new `VipRoutingMixin` handles server selection (WSM cost formula), storage selection (fixed per domain), DNAT/SNAT flow rule installation, and proactive ARP virtualization.

## Architecture

This is **not a new thread**. The mixin adds methods to the same `KenLearnAndLog` class via inheritance (same pattern as `TopologyMixin`). Thread 1's `packet_in_handler` calls into VIP methods inline — same greenthread, same event loop.

---

```
KenLearnAndLog(VipRoutingMixin, TopologyMixin, OSKenApp)
       │
       ├── Thread 1 (event loop) ─── packet_in_handler()
       │       │
       │       ├─ Is VIP packet? ──Yes──► handle_vip_packet_in()
       │       │                              ├─ select_server() / select_storage()
       │       │                              ├─ install DNAT + SNAT rules (prio 200)
       │       │                              └─ Packet-Out first packet
       │       │
       │       └─ Not VIP ────────────► existing L2 learning logic
       │
       ├── Thread 2 (ZMQ subscriber) ── _on_telemetry_update()
       │       └─ updates _server_tproc dict (read by select_server)
       │
       └── Thread 3 (elasticity) ── unchanged
```

---

## Files to Change

| File                              | Action        | Purpose                                                        |
| --------------------------------- | ------------- | -------------------------------------------------------------- |
| `sdn_controller/vip_routing.py` | **NEW** | VIP routing mixin (all VIP logic)                              |
| `sdn_controller/main_n1.py`     | Modify        | Add mixin to MRO, VIP check in PacketIn, call ARP/punt install |
| `sdn_controller/main_n2.py`     | Modify        | Same changes as main_n1                                        |
| `scripts/osken-controller.env`  | Modify        | Add `WSM_THETA`, `VIP_IDLE_TIMEOUT`, `VIP_HARD_TIMEOUT`  |
| `docker/edge_server/source/app.py` | Modify     | Per-LAN VIP_DATA routing, singleton clients, LAN-aware queries |

---

## Step 1: Create `sdn_controller/vip_routing.py`

The full mixin module handling ARP snooping, server selection (WSM), storage selection, VIP packet interception, and OpenFlow rule installation.

```python
import logging
import os

from os_ken.lib.packet import arp as arp_lib
from os_ken.lib.packet import ethernet, ether_types, ipv4, packet

logger = logging.getLogger("os_ken.vip_routing")

# Configurable via env
_WSM_THETA       = float(os.environ.get("WSM_THETA", "0.5"))
_VIP_IDLE_TIMEOUT = int(os.environ.get("VIP_IDLE_TIMEOUT", "30"))
_VIP_HARD_TIMEOUT = int(os.environ.get("VIP_HARD_TIMEOUT", "120"))


class VipRoutingMixin:
    """Mixin that intercepts traffic destined for VIP_SERVER or VIP_DATA
    and installs DNAT/SNAT rules pointing to a selected backend.

    Depends on TopologyMixin attributes:
        vip_server_ip, vip_data_ip, vip_server_mac, vip_data_mac,
        vip_server_pool, vip_storage_pool, hop_cache, _hop_cache_max,
        host_attachment, _datapath_by_id
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # IP ↔ MAC learned from ARP traffic flowing through the switch
        self._ip_to_mac: dict[str, str] = {}   # ip -> mac
        self._mac_to_ip: dict[str, str] = {}   # mac -> ip

        # Per-server T_proc (ms), updated by Thread 2 telemetry callback
        self._server_tproc: dict[str, float] = {}   # mac -> avg_time_proc_ms

        logger.info(
            "vip routing mixin init: theta=%.2f idle=%ds hard=%ds",
            _WSM_THETA, _VIP_IDLE_TIMEOUT, _VIP_HARD_TIMEOUT,
        )

    # ------------------------------------------------------------------
    # ARP snooping — learn IP ↔ MAC from ARP packets
    # ------------------------------------------------------------------

    def _snoop_arp(self, pkt) -> None:
        """Extract IP↔MAC from any ARP packet passing through."""
        arp_pkt = pkt.get_protocol(arp_lib.arp)
        if arp_pkt is None:
            return
        src_ip  = arp_pkt.src_ip
        src_mac = arp_pkt.src_mac
        if src_ip and src_mac and src_ip != "0.0.0.0":
            if self._ip_to_mac.get(src_ip) != src_mac:
                logger.info("arp learned: %s -> %s", src_ip, src_mac)
            self._ip_to_mac[src_ip]  = src_mac
            self._mac_to_ip[src_mac] = src_ip

    # ------------------------------------------------------------------
    # Server selection — WSM cost formula
    # ------------------------------------------------------------------

    def select_server(self, client_mac: str) -> dict | None:
        """Pick the server with the lowest WSM cost from vip_server_pool.

        Cost_j = θ · (T_proc_j / T_proc_max) + (1-θ) · (Hops_j / Hops_max)

        Falls back to hop-count only when no telemetry is available yet.
        Returns a pool entry dict {mac, dpid, port_no} or None.
        """
        pool = self.vip_server_pool
        if not pool:
            logger.warning("select_server: pool is empty")
            return None

        # Collect T_proc values for servers that have telemetry
        tproc_max = max(self._server_tproc.values()) if self._server_tproc else 0.0
        hops_max  = max(self._hop_cache_max, 1)

        best_entry = None
        best_cost  = float("inf")

        for mac, entry in pool.items():
            # Hop component
            hops = (self.hop_cache.get(client_mac) or {}).get(mac)
            if hops is None:
                hops = hops_max  # worst case if path unknown
            hop_norm = hops / hops_max

            # T_proc component
            tproc = self._server_tproc.get(mac)
            if tproc is not None and tproc_max > 0:
                proc_norm = tproc / tproc_max
            else:
                proc_norm = 0.0  # no telemetry yet — don't penalise

            cost = _WSM_THETA * proc_norm + (1 - _WSM_THETA) * hop_norm

            logger.debug(
                "select_server: mac=%s hops=%s proc=%.1fms cost=%.4f",
                mac, hops, tproc or 0, cost,
            )
            if cost < best_cost:
                best_cost  = cost
                best_entry = entry

        if best_entry:
            logger.info(
                "select_server: selected mac=%s cost=%.4f",
                best_entry["mac"], best_cost,
            )
        return best_entry

    # ------------------------------------------------------------------
    # Storage selection — fixed per domain (initial implementation)
    # ------------------------------------------------------------------

    def select_storage(self, src_mac: str) -> dict | None:
        """Pick the first available storage node from vip_storage_pool."""
        pool = self.vip_storage_pool
        if not pool:
            logger.warning("select_storage: pool is empty")
            return None
        entry = next(iter(pool.values()))
        logger.info("select_storage: selected mac=%s", entry["mac"])
        return entry

    # ------------------------------------------------------------------
    # VIP packet-in handler — called from Thread 1's packet_in_handler
    # ------------------------------------------------------------------

    def handle_vip_packet_in(self, datapath, in_port, pkt, eth) -> bool:
        """Intercept packets destined for VIP_SERVER or VIP_DATA.

        Returns True if the packet was VIP traffic (handled here),
        False if it should fall through to normal L2 learning.
        """
        # Always snoop ARP for IP learning, even if not VIP-targeted
        self._snoop_arp(pkt)

        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        if ip_pkt is None:
            # Check if this is an ARP request for a VIP — handle via proactive
            # rules (installed on switch connect). If the proactive rule is
            # missing for some reason, we could handle it reactively here,
            # but normally ARP for VIPs never reaches the controller.
            return False

        dst_ip = ip_pkt.dst
        src_ip = ip_pkt.src
        src_mac = eth.src

        if dst_ip == self.vip_server_ip:
            return self._handle_vip_server(datapath, in_port, pkt, eth, ip_pkt, src_mac, src_ip)
        elif dst_ip == self.vip_data_ip:
            return self._handle_vip_data(datapath, in_port, pkt, eth, ip_pkt, src_mac, src_ip)

        return False

    def _handle_vip_server(self, datapath, in_port, pkt, eth, ip_pkt, src_mac, src_ip) -> bool:
        """Select a web server and install DNAT/SNAT for VIP_SERVER."""
        server = self.select_server(src_mac)
        if server is None:
            logger.warning("vip_server: no server available, dropping")
            return True  # consumed but no action

        server_mac = server["mac"]
        server_ip  = self._mac_to_ip.get(server_mac)
        if server_ip is None:
            logger.warning("vip_server: IP unknown for server mac=%s, dropping", server_mac)
            return True

        logger.info(
            "vip_server: %s:%s -> server %s (%s)",
            src_ip, src_mac, server_ip, server_mac,
        )
        self._install_vip_dnat_snat(
            datapath, in_port, pkt,
            client_mac=src_mac,
            client_ip=src_ip,
            vip_ip=self.vip_server_ip,
            vip_mac=self.vip_server_mac,
            real_ip=server_ip,
            real_mac=server_mac,
            match_src_ip=False,  # VIP_SERVER: match on nw_dst only
        )
        return True

    def _handle_vip_data(self, datapath, in_port, pkt, eth, ip_pkt, src_mac, src_ip) -> bool:
        """Select a storage node and install DNAT/SNAT for VIP_DATA."""
        storage = self.select_storage(src_mac)
        if storage is None:
            logger.warning("vip_data: no storage available, dropping")
            return True

        storage_mac = storage["mac"]
        storage_ip  = self._mac_to_ip.get(storage_mac)
        if storage_ip is None:
            logger.warning("vip_data: IP unknown for storage mac=%s, dropping", storage_mac)
            return True

        logger.info(
            "vip_data: %s:%s -> storage %s (%s)",
            src_ip, src_mac, storage_ip, storage_mac,
        )
        self._install_vip_dnat_snat(
            datapath, in_port, pkt,
            client_mac=src_mac,
            client_ip=src_ip,
            vip_ip=self.vip_data_ip,
            vip_mac=self.vip_data_mac,
            real_ip=storage_ip,
            real_mac=storage_mac,
            match_src_ip=True,  # VIP_DATA: match includes nw_src (no src_port)
        )
        return True

    # ------------------------------------------------------------------
    # DNAT / SNAT rule installation
    # ------------------------------------------------------------------

    def _install_vip_dnat_snat(
        self, datapath, in_port, pkt, *,
        client_mac, client_ip, vip_ip, vip_mac,
        real_ip, real_mac, match_src_ip,
    ):
        """Install a DNAT + SNAT rule pair and Packet-Out the first packet.

        DNAT (forward):  nw_dst=VIP → set_field(real_ip, real_mac), output to backend port
        SNAT (return):   nw_src=real_ip → set_field(VIP_ip, VIP_mac), output to client port

        For VIP_DATA (match_src_ip=True): DNAT match also includes nw_src=client_ip
        (no src_port — per design doc — one rule covers all concurrent connections).
        """
        parser  = datapath.ofproto_parser
        ofproto = datapath.ofproto

        # Resolve output port for the backend
        backend_loc = self.host_attachment.get(real_mac)
        if backend_loc is None:
            logger.warning("dnat/snat: backend mac=%s not in host_attachment", real_mac)
            return
        _backend_dpid, backend_port = backend_loc

        # --- DNAT rule (client → VIP rewrites to client → real backend) ---
        dnat_match_fields = dict(eth_type=0x0800, ipv4_dst=vip_ip)
        if match_src_ip:
            dnat_match_fields["ipv4_src"] = client_ip

        dnat_match = parser.OFPMatch(**dnat_match_fields)
        dnat_actions = [
            parser.OFPActionSetField(eth_dst=real_mac),
            parser.OFPActionSetField(ipv4_dst=real_ip),
            parser.OFPActionOutput(backend_port),
        ]

        self._install_flow(
            datapath, priority=200,
            match=dnat_match, actions=dnat_actions,
            idle_timeout=_VIP_IDLE_TIMEOUT,
            hard_timeout=_VIP_HARD_TIMEOUT,
        )

        # --- SNAT rule (real backend → client rewrites to VIP → client) ---
        snat_match_fields = dict(eth_type=0x0800, ipv4_src=real_ip)
        if match_src_ip:
            snat_match_fields["ipv4_dst"] = client_ip

        snat_match = parser.OFPMatch(**snat_match_fields)
        snat_actions = [
            parser.OFPActionSetField(eth_src=vip_mac),
            parser.OFPActionSetField(ipv4_src=vip_ip),
            parser.OFPActionOutput(in_port),
        ]

        self._install_flow(
            datapath, priority=200,
            match=snat_match, actions=snat_actions,
            idle_timeout=_VIP_IDLE_TIMEOUT,
            hard_timeout=_VIP_HARD_TIMEOUT,
        )

        logger.info(
            "dnat/snat installed: vip=%s -> real=%s (idle=%ds hard=%ds)",
            vip_ip, real_ip, _VIP_IDLE_TIMEOUT, _VIP_HARD_TIMEOUT,
        )

        # --- Packet-Out the first packet with DNAT actions applied ---
        data = pkt.data if hasattr(pkt, "data") else None
        out_msg = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=ofproto.OFP_NO_BUFFER,
            in_port=in_port,
            actions=dnat_actions,
            data=data,
        )
        datapath.send_msg(out_msg)

    # ------------------------------------------------------------------
    # Proactive ARP reply rules — installed on switch connect
    # ------------------------------------------------------------------

    def install_vip_arp_rules(self, datapath) -> None:
        """Install proactive ARP reply rules for both VIPs.

        When a host sends ARP 'who-has <VIP>?', the switch answers directly
        with the VIP's virtual MAC — no controller involvement.
        """
        self._install_vip_arp_reply(datapath, self.vip_server_ip, self.vip_server_mac)
        self._install_vip_arp_reply(datapath, self.vip_data_ip,   self.vip_data_mac)
        logger.info(
            "vip arp rules installed: dpid=%s server=%s data=%s",
            datapath.id, self.vip_server_ip, self.vip_data_ip,
        )

    def _install_vip_arp_reply(self, datapath, vip_ip, vip_mac):
        """Install a single proactive ARP reply rule.

        match:   ARP request (op=1) with arp_tpa=<vip_ip>
        actions: rewrite ARP fields to form a reply, send back to IN_PORT
        """
        parser  = datapath.ofproto_parser
        ofproto = datapath.ofproto

        match = parser.OFPMatch(
            eth_type=0x0806,          # ARP
            arp_op=1,                 # ARP REQUEST
            arp_tpa=vip_ip,           # target protocol address = VIP
        )

        actions = [
            # Set ARP op to REPLY (2)
            parser.OFPActionSetField(arp_op=2),
            # Swap: move original sender → target
            # (the reply goes back to whoever asked)
            # Note: OVS evaluates actions left-to-right and reads the
            # *current* field value, so we must use NXActionRegMove or
            # set the target fields explicitly. Here we use set_field
            # which reads the original packet values before any action.
            #
            # We set the reply's SHA and SPA to the VIP's virtual identity,
            # and THA/TPA to the original requester (which OVS preserves
            # from the original SHA/SPA since set_field on arp_tha/arp_tpa
            # uses the packet's *original* values when evaluated).
            parser.OFPActionSetField(arp_sha=vip_mac),
            parser.OFPActionSetField(arp_spa=vip_ip),
            # Swap eth: dst ← original src, src ← VIP MAC
            parser.OFPActionSetField(eth_src=vip_mac),
            # Output back to the port the request came from
            parser.OFPActionOutput(ofproto.OFPP_IN_PORT),
        ]

        self._install_flow(datapath, priority=200, match=match, actions=actions)

    # ------------------------------------------------------------------
    # VIP punt rules — send VIP-destined IP traffic to controller
    # ------------------------------------------------------------------

    def install_vip_punt_rules(self, datapath) -> None:
        """Install punt rules that send VIP-destined IP packets to the controller.

        Priority 100 — higher than L2 proactive flows (prio 5) and reactive
        flows (prio 10), but lower than installed DNAT rules (prio 200).
        Once DNAT rules are installed, they take precedence and packets no
        longer reach the controller until the rules expire.
        """
        parser  = datapath.ofproto_parser
        ofproto = datapath.ofproto

        for vip_ip in (self.vip_server_ip, self.vip_data_ip):
            match   = parser.OFPMatch(eth_type=0x0800, ipv4_dst=vip_ip)
            actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                              ofproto.OFPCML_NO_BUFFER)]
            self._install_flow(datapath, priority=100, match=match, actions=actions)

        logger.info("vip punt rules installed: dpid=%s", datapath.id)

    # ------------------------------------------------------------------
    # Telemetry integration — called from _on_telemetry_update
    # ------------------------------------------------------------------

    def update_server_tproc(self, servers: dict) -> None:
        """Update per-server T_proc values from a telemetry summary.

        servers: dict of server_id -> ServerSummary (from TelemetrySummary.servers)
        """
        # server_id in telemetry is the container name (e.g. "edge_server_n1")
        # We need to map it to a MAC. For now, iterate the pool and match by
        # any known association. A more robust approach would include the MAC
        # in the telemetry event itself.
        for server_id, summary in servers.items():
            # Try to find this server's MAC in the pool
            # Convention: server_id contains the network suffix, and we can
            # match by checking ip_to_mac against known server IPs
            for mac in self._server_macs:
                ip = self._mac_to_ip.get(mac)
                if ip and server_id in self._server_tproc:
                    break
            # Just store by server_id for now — select_server resolves via pool MAC
            self._server_tproc[server_id] = summary.avg_time_proc_ms
            logger.debug(
                "tproc updated: %s = %.1fms", server_id, summary.avg_time_proc_ms,
            )
```

---

## Step 2: Modify `main_n1.py` (and `main_n2.py` identically)

### 2a. Add import

```python
# existing imports...
from .topology import TopologyMixin
from .vip_routing import VipRoutingMixin  # ← ADD
```

### 2b. Add mixin to class MRO

```python
# BEFORE:
class KenLearnAndLog(TopologyMixin, app_manager.OSKenApp):

# AFTER:
class KenLearnAndLog(VipRoutingMixin, TopologyMixin, app_manager.OSKenApp):
```

### 2c. Add VIP check in `packet_in_handler` (before L2 learning)

Insert after LLDP check, before `dpid_int = int(datapath.id)`:

```python
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, event):
        msg = event.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        dst = eth.dst
        src = eth.src
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        # ────────── VIP interception (before L2 learning) ──────────
        if self.handle_vip_packet_in(datapath, in_port, pkt, eth):
            return
        # ───────────────────────────────────────────────────────────

        dpid_int = int(datapath.id)
        # ... rest of existing L2 learning logic unchanged ...
```

### 2d. Install ARP + punt rules on switch connect

In `_state_change_handler`, after reinstalling table-miss in the `MAIN_DISPATCHER` branch:

```python
    @set_ev_cls(ofp_event.EventOFPStateChange, [MAIN_DISPATCHER, DEAD_DISPATCHER])
    def _state_change_handler(self, ev):
        datapath = ev.datapath
        if ev.state == MAIN_DISPATCHER:
            # ... existing flow flush + table-miss reinstall ...

            # ─── Install VIP rules ───
            self.install_vip_arp_rules(datapath)
            self.install_vip_punt_rules(datapath)
            # ─────────────────────────

            entry = (datapath, datapath.id)
            # ... rest unchanged ...
```

### 2e. Wire telemetry into WSM cost model

In `_on_telemetry_update`, after the existing domain summary processing, add:

```python
    def _on_telemetry_update(self, summary: TelemetrySummary) -> None:
        if summary.network_id != self._lan_id:
            return
        ds = summary.domain_summary
        print(f"[telemetry] network={summary.network_id} ...")

        # ─── Update per-server T_proc for WSM selection ───
        self.update_server_tproc(summary.servers)
        # ──────────────────────────────────────────────────

        # ... rest of threshold logic unchanged ...
```

---

## Step 3: Update `osken-controller.env`

Add these lines at the end:

```bash
# VIP routing — WSM weight and flow timeouts
WSM_THETA=0.5
VIP_IDLE_TIMEOUT=30
VIP_HARD_TIMEOUT=120
```

---

## OpenFlow Rule Summary

After deployment, the switch will have these rules (inspectable via `ovs-ofctl dump-flows`):

| Priority      | Match                                        | Actions                       | Installed By                       |
| ------------- | -------------------------------------------- | ----------------------------- | ---------------------------------- |
| **0**   | `*` (wildcard)                             | `output:CONTROLLER`         | table-miss (switch connect)        |
| **1**   | `eth_type=0x0806` (ARP)                    | `FLOOD`                     | proactive topology flows           |
| **5**   | `in_port, eth_src, eth_dst`                | `output:next_hop`           | proactive topology flows           |
| **10**  | `in_port, eth_src, eth_dst`                | `output:learned_port`       | reactive L2 learning               |
| **100** | `eth_type=0x0800, nw_dst=VIP_SERVER_IP`    | `output:CONTROLLER`         | **VIP punt (new)**           |
| **100** | `eth_type=0x0800, nw_dst=VIP_DATA_IP`      | `output:CONTROLLER`         | **VIP punt (new)**           |
| **200** | `arp, arp_op=1, arp_tpa=VIP_SERVER_IP`     | ARP reply with VIP_SERVER_MAC | **VIP ARP (new)**            |
| **200** | `arp, arp_op=1, arp_tpa=VIP_DATA_IP`       | ARP reply with VIP_DATA_MAC   | **VIP ARP (new)**            |
| **200** | `nw_dst=VIP_SERVER_IP`                     | DNAT →`real_server_ip/mac` | **VIP DNAT (new, per-flow)** |
| **200** | `nw_src=real_server_ip`                    | SNAT →`VIP_SERVER_ip/mac`  | **VIP SNAT (new, per-flow)** |
| **200** | `nw_src=web_server_ip, nw_dst=VIP_DATA_IP` | DNAT →`storage_ip/mac`     | **VIP DNAT (new, per-flow)** |
| **200** | `nw_src=storage_ip, nw_dst=web_server_ip`  | SNAT →`VIP_DATA_ip/mac`    | **VIP SNAT (new, per-flow)** |

---

## Packet Flow

### VIP_SERVER (HTTP)

```
1. Client sends TCP SYN to 10.0.0.100 (VIP_SERVER)
2. ARP for 10.0.0.100 → answered by switch (prio 200 ARP rule) → VIP_SERVER_MAC
3. IP packet to VIP_SERVER_IP hits punt rule (prio 100) → PacketIn
4. packet_in_handler → handle_vip_packet_in → select_server (WSM)
5. DNAT rule installed (prio 200): nw_dst=VIP → real_server
6. SNAT rule installed (prio 200): nw_src=real_server → VIP
7. Packet-Out first packet with DNAT actions
8. Subsequent packets: switch-only (prio 200 > prio 100)
9. After idle_timeout/hard_timeout: rules expire → next packet triggers fresh selection
```

### VIP_DATA (MongoDB)

```
1. Web server opens TCP connection to 10.0.0.200:27018 (VIP_DATA)
2. ARP for 10.0.0.200 → answered by switch → VIP_DATA_MAC
3. IP packet to VIP_DATA_IP hits punt rule → PacketIn
4. packet_in_handler → handle_vip_packet_in → select_storage
5. DNAT rule (prio 200): nw_src=web_server, nw_dst=VIP → storage (no src_port)
6. SNAT rule (prio 200): nw_src=storage, nw_dst=web_server → VIP
7. Packet-Out first packet
8. All MongoDB connections from this web server use same storage node
9. On timeout expiry: next connection can be routed to a different tier
```

---

## WSM Cost Formula

$$
Cost_j^{web} = \theta \cdot \frac{T_{proc,j}}{T_{proc,max}} + (1-\theta) \cdot \frac{Hops_j}{Hops_{max}}
$$

Where:

- $\theta$ = `WSM_THETA` (default 0.5) — weight between processing time and network distance
- $T_{proc,j}$ = average processing time of server $j$ (from Thread 2 telemetry)
- $Hops_j$ = shortest-path hop count from requesting client to server $j$ (from topology)
- Cold start (no telemetry): $T_{proc}$ penalty is 0, selection based on hop count only

---

## Design Decisions

1. **No `src_port` in VIP_DATA match** — one rule covers all concurrent connections from a web server to a domain VIP, preventing tier-transition inconsistency across parallel connections
2. **ARP handled proactively** — prio 200 rules in the switch answer ARP for VIPs without involving the controller (zero added latency for ARP resolution)
3. **Punt at prio 100, DNAT at prio 200** — once DNAT rules are installed they override the punt rule; when they expire the punt rule resumes and triggers fresh selection
4. **`idle_timeout` + `hard_timeout`** — idle_timeout handles bursty traffic (rule stays alive while connections flow), hard_timeout guarantees tier transitions propagate even under sustained load
5. **Mixin pattern** — follows existing `TopologyMixin` convention; no new thread, no new event loop

---

## Verification

```bash
# 1. Check flow rules
docker exec ovs ovs-ofctl dump-flows ovs-br0

# 2. ARP test (should get VIP MAC without controller log)
docker exec edge_server_n1 arping -c 1 10.0.0.100

# 3. HTTP through VIP
docker exec edge_server_n1 curl http://10.0.0.100:5000/health

# 4. MongoDB through VIP
docker exec edge_server_n1 mongosh mongodb://10.0.0.200:27018 --eval "db.runCommand({ping:1})"

# 5. Controller logs
docker logs osken 2>&1 | grep -iE "vip|dnat|snat|select_server|select_storage"

# 6. Verify timeout expiry triggers new PacketIn
# Wait idle_timeout seconds with no traffic, then re-curl
```

---

## Open Items

1. **Port rewrite**: Design doc says VIP_Web is `:80` but Flask runs on `:5000`. Currently matching on `nw_dst` only (no port match). Add `tp_dst` rewrite if port translation is needed.
2. ~~**Per-domain VIP_DATA**: Currently a single `VIP_DATA_IP=10.0.0.200`. Extend to per-domain VIPs (e.g., `10.0.0.200`, `10.0.1.200`) when multi-domain routing is implemented.~~ → Addressed in the *Per-LAN VIP_DATA Routing* addendum above.
3. **Telemetry → MAC mapping**: `TelemetrySummary.servers` keys are container names (e.g., `edge_server_n1`), not MACs. The `update_server_tproc` method needs a name→MAC mapping (via an env var or telemetry enrichment) for WSM to work with per-MAC granularity.
4. **ARP reply field swap**: The proactive ARP reply rule uses `set_field` to write SHA/SPA but relies on OVS preserving the original ARP sender fields in THA/TPA. This needs testing — if OVS overwrites THA/TPA prematurely, we may need `NXActionRegMove` to properly swap the fields.

---

## Addendum — Elasticity Backend IP Bootstrap Fix

### Problem

When Thread 3 (`ElasticityManager`) spawns a new backend via `NodeAdder`, the MAC is
added to the VIP pool immediately via `add_server_mac()` / `add_storage_mac()`. However,
`_mac_to_ip` is populated **only** by `snoop_arp()`, which requires an ARP packet from
the new container to actually arrive at the controller first.

This creates a window where Thread 1's `_handle_vip_server` / `_handle_vip_data` picks
the new backend from the pool, then fails the IP lookup and drops every packet:

```
WARNING vip_server: IP unknown for mac=00:00:00:00:01:06 — awaiting ARP from backend
```

The packet-drop loop continues until the container ARPs (which may take many seconds
or require a forwarded probe to trigger it).

The IP is already validated and available in `NodeResult.ip` at the exact moment the
MAC is registered — it just was never propagated to `_mac_to_ip`.

### Fix

Add `register_backend_ip(mac, ip)` to `VipRoutingMixin` and call it from
`ElasticityManager` right after `add_server_mac()` / `add_storage_mac()`.

`snoop_arp()` remains the authoritative path — any real ARP from the backend will
overwrite the seeded entry, which is correct (e.g., container restart with same MAC
but new IP).

### Files Changed

| File                              | Change                                                                                                                                                                                     |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `sdn_controller/vip_routing.py` | New `register_backend_ip(mac, ip)` method on `VipRoutingMixin`, placed alongside `snoop_arp()`                                                                                       |
| `sdn_controller/elasticity.py`  | Call `self._topo.register_backend_ip(result.mac, result.ip)` in both `_handle_compute` and `_handle_data`, inside the existing `result.success and result.ip and result.mac` guard |

### `register_backend_ip` implementation

```python
def register_backend_ip(self, mac: str, ip: str) -> None:
    """Seed _mac_to_ip/_ip_to_mac from a known IP returned by NodeAdder.

    Called by Thread 3 (ElasticityManager) immediately after adding a new
    MAC to the VIP pool, so Thread 1 can route the very first packet to
    the new backend without waiting for an ARP to arrive at the controller.
    snoop_arp() remains authoritative — it will overwrite this entry if
    the container's IP ever changes.
    """
    self._ip_to_mac[ip]  = mac
    self._mac_to_ip[mac] = ip
    logger.info("backend ip registered (static seed): %s -> %s", mac, ip)
```

### Thread-safety rationale

`_mac_to_ip` / `_ip_to_mac` are plain `dict` objects. Thread 3 writes via
`register_backend_ip()`; Thread 1 reads via `_handle_vip_server` / `_handle_vip_data`.
Python's GIL makes individual dict key assignments atomic. The controller uses
eventlet's cooperative scheduling, so there are no true concurrent accesses at yield
points — the same rationale already documented in the `vip_routing.py` module docstring
for `_server_tproc`. No additional locking is needed.

### Verification

```bash
# Trigger an elasticity compute alert, then watch for the static seed log line:
docker logs osken 2>&1 | grep "backend ip registered"

# Confirm no "IP unknown" warnings appear for the new backend:
docker logs osken 2>&1 | grep "IP unknown"

# Confirm the first packet to the new server is routed immediately (no drop delay):
docker logs osken 2>&1 | grep "vip_server:"
```

---

## Addendum — Per-LAN VIP_DATA Routing from Edge Server

### Problem

Edge servers (`app.py`) use a single `DB_URL` for all MongoDB operations
regardless of which LAN the requested data lives in. Since device documents are
partitioned by LAN — each seeded only into its origin LAN's replica set — and
VIP_DATA addresses are per-domain (`VIP_DATA_N1` on LAN 1, `VIP_DATA_N2` on
LAN 2), the edge server must route each query to the correct VIP_DATA address
based on the `lan1`/`lan2` prefix in the document `_id`.

Additionally, the current implementation creates a fresh `MongoClient` per HTTP
request, paying the TCP handshake + MongoDB hello cost each time. This cost is
unnecessary during traffic bursts where the same DNAT rule is active (rules live
for `VIP_IDLE_TIMEOUT=30s`).

A third issue: the docker run commands in `build_network_1.sh` /
`build_network_2.sh` pass `LAN_ID` (not `REGION`), so `REGION` always falls
back to the default `"lan1"`.

### Connection Model: Singleton with Dual Recycling

A module-level `MongoClient` per LAN (`maxPoolSize=1`) with two complementary
recycling mechanisms that ensure DNAT re-evaluation happens in both quiet and
busy periods:

1. **`maxIdleTimeMS`** (quiet periods) — matches `VIP_IDLE_TIMEOUT × 1000`.
   The PyMongo driver closes the socket after this idle window, so the next
   request forces a fresh TCP SYN → `packet_in` → controller re-runs WSM.

2. **`TAU_DADOS_MS` threshold** (busy periods) — an `after_request` hook
   checks the request's accumulated `T_dados` (`g.time_db_elapsed × 1000`).
   When it exceeds the same threshold the SDN controller uses for elasticity
   alerts (`TAU_DADOS_MS`), all per-LAN singleton clients are evicted from the
   pool. The next request on any LAN creates a fresh `MongoClient` → fresh TCP
   SYN → `packet_in` → controller re-evaluates WSM with current conditions.

Without the threshold check, under sustained load the socket never goes idle,
`maxIdleTimeMS` never fires, and the DNAT rule stays pinned to the same backend
indefinitely — even if the controller has since spawned a better-suited backend.

```
Request A arrives
  → pool empty → TCP SYN → packet_in → controller selects B1 → DNAT installed
  → queries run on reused socket

Request B arrives (within maxIdleTimeMS)
  → socket reused → hits B1 (same DNAT rule)
  → T_dados within threshold → no action

Request C arrives (load spike on B1)
  → socket reused → T_dados exceeds TAU_DADOS_MS
  → after_request evicts all clients from pool
  → next request forces new TCP SYN → fresh packet_in
  → controller re-evaluates WSM, may select B2

... idle > maxIdleTimeMS (quiet period) ...
  → driver closes socket; VIP_IDLE_TIMEOUT also expires → DNAT removed

Request D arrives
  → new TCP SYN → fresh packet_in → controller re-evaluates WSM
```

Both `VIP_IDLE_TIMEOUT` and `maxIdleTimeMS` are idle timeouts — they only fire
when no traffic is flowing. Setting them to the same value keeps them coherent.
`maxPoolSize=1` ensures exactly one DNAT selection is active per LAN per edge
server. Making it easier to manage the lifecycle of connections and allowing for more frequent and pourposefully packet in.

#### Concurrency Safety: Pop-Without-Close

When evicting clients (both in the threshold hook and `/vip_data` PUT), entries
are **popped from the dict but never `.close()`d**. An explicit `.close()` would
race against in-flight operations on other Flask threads that still hold a
reference to the old `MongoClient`:

```
Thread A: _get_client("lan1") → gets client ref → releases lock → starts query
Thread B: after_request → acquires lock → pops "lan1" → releases lock
Thread A: query completes on old client (still valid — not closed)
Thread C: _get_client("lan1") → no entry → creates fresh client → new TCP SYN
```

CPython's reference-counting GC destroys the orphaned `MongoClient` (and closes
its socket) as soon as the last `timed_db` context holding a reference exits.
With `maxPoolSize=1`, at most one orphaned socket per LAN can exist briefly.

### Document ID Convention

IDs follow `{lan}::{type}::{number}` — the LAN is `id.split("::")[0]`:

| Entity          | Example ID            | LAN extracted |
|-----------------|-----------------------|---------------|
| Sensor device   | `lan1::device::042`   | `lan1`        |
| Monitoring node | `lan2::node::007`     | `lan2`        |

### Fixes

**Fix 1 — Rename `REGION` → `LAN_ID`**

Replace `REGION: str = os.environ.get("REGION", "lan1")` with
`LAN_ID: str = os.environ.get("LAN_ID", "lan1")` and update all references.

**Fix 2 — Replace single `db_url` with per-LAN singleton clients**

Remove `_config_lock`, `_config`, `get_db_url()`, `set_db_url()`, `_get_db()`,
and `@app.teardown_request _close_mongo()`. Add:

```python
DB_PORT: int = int(os.environ.get("DB_PORT", "27018"))
MAX_IDLE_MS: int = int(os.environ.get("MAX_IDLE_MS",
                       str(int(os.environ.get("VIP_IDLE_TIMEOUT", "30")) * 1000)))

_clients_lock = threading.Lock()
_mongo_clients: dict[str, MongoClient] = {}

def _get_client(lan: str) -> MongoClient:
    with _clients_lock:
        client = _mongo_clients.get(lan)
        if client is None:
            with vip_data_lock:
                vip_ip = vip_data_per_domain[lan]
            url = f"mongodb://{vip_ip}:{DB_PORT}/"
            client = MongoClient(
                url, maxPoolSize=1, maxIdleTimeMS=MAX_IDLE_MS,
                serverSelectionTimeoutMS=3000,
            )
            _mongo_clients[lan] = client
            log.info("Created MongoClient for %s → %s (maxIdleTimeMS=%d)", lan, url, MAX_IDLE_MS)
        return client
```

**Fix 3 — `timed_db(lan)` context manager**

```python
@contextmanager
def timed_db(lan: str):
    t0 = time.monotonic()
    try:
        yield _get_client(lan)[DB_NAME]
    finally:
        g.time_db_elapsed = getattr(g, "time_db_elapsed", 0.0) + (time.monotonic() - t0)
```

**Fix 4 — Remove `/config/db_url` route**

Delete the `config_set_db_url()` route. VIP_DATA addresses are managed via
`/vip_data` PUT.

**Fix 5 — `/vip_data` PUT resets affected clients**

After updating `vip_data_per_domain`, evict stale singleton clients (pop-without-close
for concurrency safety — see *Concurrency Safety* above):

```python
with _clients_lock:
    for lan in body:
        _mongo_clients.pop(lan, None)
```

**Fix 6 — `device_latest`: LAN-aware queries**

Parse `device_lan = device_id.split("::")[0]`. Use `timed_db(device_lan)` for
`sensor_reports`, `timed_db(node_lan)` for `device_registry`, and
`timed_db(LAN_ID)` for `query_events` (local activity log).

**Fix 7 — `anomalies`: LAN-aware enrichment**

`query_events` uses `timed_db(LAN_ID)`. Enrichment groups `device_ids` by LAN
prefix and issues one `sensor_reports.find()` per LAN.

**Fix 8 — `dashboard`: both LANs for sensor data**

`device_registry` uses node's LAN. `sensor_reports` queries **both LANs** (tags
can match devices on either) and merges before urgency sort.

**Fix 9 — Startup log**

Update to reflect `LAN_ID`, `vip_data_per_domain`, `MAX_IDLE_MS`, and `TAU_DADOS_MS`.

**Fix 10 — T_dados adaptive reconnection**

Add `TAU_DADOS_MS` env var (same name and default as the SDN controller) and an
`after_request` hook that evicts all per-LAN singleton clients when the request's
accumulated `T_dados` exceeds the threshold. This forces the next request to
create a fresh TCP connection, triggering a `packet_in` → WSM re-evaluation:

```python
TAU_DADOS_MS: float = float(os.environ.get("TAU_DADOS_MS", "150000"))

@app.after_request
def _check_tdados_threshold(response):
    time_db_ms = getattr(g, "time_db_elapsed", 0.0) * 1000
    if time_db_ms > TAU_DADOS_MS:
        with _clients_lock:
            evicted = list(_mongo_clients.keys())
            _mongo_clients.clear()
        log.warning(
            "T_dados=%.1fms > τ=%.1fms — evicted clients %s to force reconnection",
            time_db_ms, TAU_DADOS_MS, evicted,
        )
    return response
```

The hook is registered **before** `init_telemetry(app)`. Flask executes
`after_request` hooks in reverse registration order, so the telemetry hook
(registered by `init_telemetry`) runs first — the metric is captured before the
client eviction happens.

### Per-LAN Routing Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `LAN_ID` | `lan1` | Edge server's home LAN (replaces `REGION`) |
| `DB_PORT` | `27018` | MongoDB port for VIP_DATA addresses |
| `MAX_IDLE_MS` | `VIP_IDLE_TIMEOUT × 1000` (30000) | PyMongo `maxIdleTimeMS` — socket recycling window (quiet periods) |
| `TAU_DADOS_MS` | `150000` | T_dados threshold — evict all clients when exceeded (busy periods) |

### Per-LAN Routing Invariants

1. A query for `lan1::device::*` connects via `vip_data_per_domain["lan1"]` (VIP_DATA_N1)
2. A query for `lan2::device::*` connects via `vip_data_per_domain["lan2"]` (VIP_DATA_N2)
3. `query_events` always goes to `LAN_ID` — the local edge server's activity log
4. At most one TCP socket per LAN is active at any time (`maxPoolSize=1`)
5. Socket recycling aligns with DNAT rule lifetime (`maxIdleTimeMS ≈ VIP_IDLE_TIMEOUT`)
6. `/vip_data` PUT invalidates the affected singleton client
7. When T_dados exceeds `TAU_DADOS_MS`, **all** LAN clients are evicted — next request forces fresh `packet_in` → WSM re-evaluation
8. Client eviction uses pop-without-close — never `.close()` a client that may be in use by another thread
