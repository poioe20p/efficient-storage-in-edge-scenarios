"""VIP routing mixin for the OS-Ken SDN controller.

Responsibilities:
  - ARP interception for VIP addresses (reactive, controller-generated replies)
  - IP packet interception for VIP_SERVER and VIP_DATA
  - DNAT/SNAT flow rule installation (priority 200, with timeouts)
  - WSM cost-based server selection using T_proc + hop count
  - Fixed-per-domain storage selection (MDVBP tier 0 baseline)
  - Per-domain VIP_DATA: VIP_DATA_N1 routes to LAN1 storage,
    VIP_DATA_N2 routes to LAN2 storage

Cross-network support: when pools contain backends on the peer LAN (learned
via TopologyMixin.peer_hosts), select_server/select_storage can pick them.
DNAT'd packets are output to ROUTER_OVS_PORT so the inter-LAN router
forwards them to the remote switch, which delivers them via normal L2
forwarding (the packet is already rewritten — no second VIP PacketIn).

This is NOT a new thread.  All methods are called inline by Thread 1's
packet_in_handler.  State written by Thread 2 (_server_tproc) is read
here — no locks are needed because eventlet uses cooperative switching and
these dicts are only mutated between yield points.

Usage (class MRO in main_n*.py):
    class KenLearnAndLog(VipRoutingMixin, TopologyMixin, OSKenApp):
        ...
"""
import logging
import os

from os_ken.lib.packet import arp as arp_lib
from os_ken.lib.packet import ethernet as eth_lib
from os_ken.lib.packet import ether_types, ipv4, packet

logger = logging.getLogger("os_ken.vip_routing")

_WSM_THETA        = float(os.environ.get("WSM_THETA",        "0.5"))
_VIP_IDLE_TIMEOUT = int(os.environ.get("VIP_IDLE_TIMEOUT", "30"))
_VIP_HARD_TIMEOUT = int(os.environ.get("VIP_HARD_TIMEOUT", "120"))

# Cross-network routing: OVS port number connected to the inter-LAN router.
# 0 = disabled (local-only mode).  Set to the actual port (e.g. 3) to enable
# forwarding DNAT'd packets via the router toward peer-network backends.
_ROUTER_OVS_PORT  = int(os.environ.get("ROUTER_OVS_PORT",  "0"))

# Constant hop penalty assigned to backends on the peer network.
# Used instead of hop_cache (which is local-only) when the selected backend
# lives across the router.  Must be > 0.
_CROSS_NETWORK_HOP_PENALTY = int(os.environ.get("CROSS_NETWORK_HOP_PENALTY", "3"))


class VipRoutingMixin:
    """Mixin that intercepts traffic for VIP_SERVER (HTTP) and VIP_DATA (MongoDB).

    Must sit *before* TopologyMixin in the class MRO so that the
    _on_datapath_connected hook is called in the correct cooperative order.

    Depends on TopologyMixin attributes (set at __init__ time):
        vip_server_ip, vip_server_mac,
        vip_data_n1_ip, vip_data_n1_mac, vip_data_n2_ip, vip_data_n2_mac,
        vip_server_pool, vip_storage_pool_n1, vip_storage_pool_n2,
        hop_cache, _hop_cache_max, host_attachment

    Depends on the concrete class (_install_flow defined in main_n*.py):
        _install_flow(dp, priority, match, actions, *, idle_timeout, hard_timeout)
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # IP ↔ MAC learned by snooping ARP packets that reach the controller.
        # Backends ARP for the VIPs at startup, which bootstraps this table.
        self._ip_to_mac: dict[str, str] = {}   # ip  -> mac
        self._mac_to_ip: dict[str, str] = {}   # mac -> ip

        # Per-server T_proc (ms) updated by Thread 2 telemetry callback.
        # Keyed by server_id as reported in TelemetrySummary.servers.
        self._server_tproc: dict[str, float] = {}

        logger.info(
            "vip routing mixin: theta=%.2f idle_timeout=%ds hard_timeout=%ds "
            "router_port=%d cross_hop_penalty=%d",
            _WSM_THETA, _VIP_IDLE_TIMEOUT, _VIP_HARD_TIMEOUT,
            _ROUTER_OVS_PORT, _CROSS_NETWORK_HOP_PENALTY,
        )

    # ------------------------------------------------------------------
    # Datapath connection hook
    # Called by TopologyMixin._state_change_handler after stale flow flush
    # ------------------------------------------------------------------

    def _on_datapath_connected(self, datapath) -> None:
        """Install VIP rules after the switch reconnects and stale flows are flushed."""
        super()._on_datapath_connected(datapath)
        self.install_vip_arp_punt_rules(datapath)
        self.install_vip_punt_rules(datapath)

    # ------------------------------------------------------------------
    # ARP snooping — learn IP ↔ MAC from ARP packets
    # ------------------------------------------------------------------

    def snoop_arp(self, pkt) -> None:
        """Record sender IP ↔ MAC from any ARP packet that reaches the controller."""
        arp_pkt = pkt.get_protocol(arp_lib.arp)
        if arp_pkt is None:
            return
        src_ip, src_mac = arp_pkt.src_ip, arp_pkt.src_mac
        if src_ip and src_mac and src_ip != "0.0.0.0":
            if self._ip_to_mac.get(src_ip) != src_mac:
                logger.info("arp learned: %s -> %s", src_ip, src_mac)
            self._ip_to_mac[src_ip] = src_mac
            self._mac_to_ip[src_mac] = src_ip

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

    # ------------------------------------------------------------------
    # VIP packet-in entry point — called from Thread 1's packet_in_handler
    # ------------------------------------------------------------------

    def handle_vip_packet_in(self, datapath, in_port, pkt, eth) -> bool:
        """Intercept ARP and IP packets destined for VIP addresses.

        Returns True if the packet was handled here — caller should return
        immediately without running L2 learning.
        Returns False to let normal packet processing continue.
        """
        
        # ARP for a VIP: generate a controller-crafted reply
        if eth.ethertype == ether_types.ETH_TYPE_ARP:
            arp_pkt = pkt.get_protocol(arp_lib.arp)
            if (
                arp_pkt is not None
                and arp_pkt.opcode == arp_lib.ARP_REQUEST
                and arp_pkt.dst_ip in (self.vip_server_ip, self.vip_data_n1_ip, self.vip_data_n2_ip)
            ):
                logger.debug("vip ARP request: dpid=%s in_port=%s arp=%s", datapath.id, in_port, arp_pkt)
                return self._reply_vip_arp(datapath, in_port, arp_pkt)
            return False

        # IPv4 to a VIP: select backend, install DNAT/SNAT, Packet-Out
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        if ip_pkt is None:
            return False

        dst_ip   = ip_pkt.dst
        src_ip   = ip_pkt.src
        src_mac  = eth.src
        ip_proto = ip_pkt.proto

        # Only handle ICMP (1), TCP (6), UDP (17).  Other protocols (ESP, GRE,
        # etc.) are not valid OFP ip_proto match values for our rule set and
        # would produce a controller error if passed to OFPMatch.
        if ip_proto not in (1, 6, 17):
            return False

        if dst_ip == self.vip_server_ip:
            logger.debug("vip server packet-in: dpid=%s in_port=%s ip=%s", datapath.id, in_port, ip_pkt)
            return self._handle_vip_server(datapath, in_port, pkt, src_mac, src_ip, ip_proto)
        if dst_ip == self.vip_data_n1_ip:
            logger.debug("vip data n1 packet-in: dpid=%s in_port=%s ip=%s", datapath.id, in_port, ip_pkt)
            return self._handle_vip_data(datapath, in_port, pkt, src_mac, src_ip, ip_proto, domain="n1")
        if dst_ip == self.vip_data_n2_ip:
            logger.debug("vip data n2 packet-in: dpid=%s in_port=%s ip=%s", datapath.id, in_port, ip_pkt)
            return self._handle_vip_data(datapath, in_port, pkt, src_mac, src_ip, ip_proto, domain="n2")

        return False

    # ------------------------------------------------------------------
    # ARP reply generation
    # ------------------------------------------------------------------

    def _reply_vip_arp(self, datapath, in_port, arp_req) -> bool:
        """Craft and send an ARP reply for a VIP address request."""
        if arp_req.dst_ip == self.vip_server_ip:
            vip_mac = self.vip_server_mac
            vip_ip  = self.vip_server_ip
        elif arp_req.dst_ip == self.vip_data_n1_ip:
            vip_mac = self.vip_data_n1_mac
            vip_ip  = self.vip_data_n1_ip
        else:
            vip_mac = self.vip_data_n2_mac
            vip_ip  = self.vip_data_n2_ip

        reply_pkt = packet.Packet()
        reply_pkt.add_protocol(eth_lib.ethernet(
            dst=arp_req.src_mac,
            src=vip_mac,
            ethertype=0x0806,
        ))
        reply_pkt.add_protocol(arp_lib.arp(
            opcode=arp_lib.ARP_REPLY,
            src_mac=vip_mac,
            src_ip=vip_ip,
            dst_mac=arp_req.src_mac,
            dst_ip=arp_req.src_ip,
        ))
        reply_pkt.serialize()

        ofproto = datapath.ofproto
        parser  = datapath.ofproto_parser
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=ofproto.OFP_NO_BUFFER,
            in_port=ofproto.OFPP_CONTROLLER,
            actions=[parser.OFPActionOutput(in_port)],
            data=reply_pkt.data,
        )
        datapath.send_msg(out)
        logger.info(
            "vip arp reply: %s is-at %s  (requester ip=%s mac=%s)",
            vip_ip, vip_mac, arp_req.src_ip, arp_req.src_mac,
        )
        return True

    # ------------------------------------------------------------------
    # VIP_SERVER (HTTP) — select web server via WSM cost formula
    # ------------------------------------------------------------------

    def _handle_vip_server(self, datapath, in_port, pkt, src_mac, src_ip, ip_proto) -> bool:
        server = self.select_server(src_mac)
        if server is None:
            logger.warning("vip_server: pool empty, packet dropped")
            return True

        server_mac = server["mac"]
        server_ip  = self._mac_to_ip.get(server_mac)
        if server_ip is None:
            logger.warning(
                "vip_server: IP unknown for mac=%s — awaiting ARP from backend",
                server_mac,
            )
            return True

        self._install_vip_dnat_snat(
            datapath, in_port, pkt,
            client_mac=src_mac,
            client_ip=src_ip,
            ip_proto=ip_proto,
            vip_ip=self.vip_server_ip,
            vip_mac=self.vip_server_mac,
            real_backend_ip=server_ip,
            real_backend_mac=server_mac,
        )
        
        logger.info(
            "vip_server: client=%s -> vip=%s -> real=%s",
            src_ip, self.vip_server_ip, server_ip,
        )
        
        return True

    # ------------------------------------------------------------------
    # VIP_DATA (MongoDB) — fixed storage node per domain
    # ------------------------------------------------------------------

    def _handle_vip_data(self, datapath, in_port, pkt, src_mac, src_ip, ip_proto, *, domain) -> bool: # * allows passing domain as a keyword-only argument for clarity
        storage = self.select_storage(domain)
        if storage is None:
            logger.warning("vip_data(%s): pool empty, packet dropped", domain)
            return True

        storage_mac = storage["mac"]
        storage_ip  = self._mac_to_ip.get(storage_mac)
        if storage_ip is None:
            logger.warning(
                "vip_data(%s): IP unknown for mac=%s — awaiting ARP from backend",
                domain, storage_mac,
            )
            return True

        if domain == "n1":
            vip_ip, vip_mac = self.vip_data_n1_ip, self.vip_data_n1_mac
        else:
            vip_ip, vip_mac = self.vip_data_n2_ip, self.vip_data_n2_mac

        self._install_vip_dnat_snat(
            datapath, in_port, pkt,
            client_mac=src_mac,
            client_ip=src_ip,
            ip_proto=ip_proto,
            vip_ip=vip_ip,
            vip_mac=vip_mac,
            real_backend_ip=storage_ip,
            real_backend_mac=storage_mac,
        )
        
        logger.info(
            "vip_data(%s): client=%s -> vip=%s -> real=%s",
            domain, src_ip, vip_ip, storage_ip,
        )
        
        return True

    # ------------------------------------------------------------------
    # Server selection — WSM cost formula
    # ------------------------------------------------------------------

    def select_server(self, client_mac: str) -> dict | None:
        """Pick the web server with the lowest WSM cost from vip_server_pool.

        Cost_j = θ · (T_proc_j / T_proc_max) + (1-θ) · (Hops_j / Hops_max)

        Falls back to hop-count-only when no telemetry data is available yet
        (cold start): the T_proc penalty term is treated as 0.
        """
        pool = self.vip_server_pool
        if not pool:
            logger.warning("select_server: pool empty")
            return None

        tproc_max = max(self._server_tproc.values()) if self._server_tproc else 0.0
        hops_max  = max(self._hop_cache_max, 1)

        best_entry, best_cost = None, float("inf")

        for mac, entry in pool.items():
            hops = (self.hop_cache.get(client_mac) or {}).get(mac)
            if hops is None:
                if mac in self.peer_hosts:
                    hops = _CROSS_NETWORK_HOP_PENALTY
                else:
                    hops = hops_max   # penalise unknown path as worst case
            hop_norm  = hops / hops_max

            tproc     = self._server_tproc.get(mac)
            proc_norm = (tproc / tproc_max) if (tproc is not None and tproc_max > 0) else 0.0

            cost = _WSM_THETA * proc_norm + (1 - _WSM_THETA) * hop_norm
            logger.debug(
                "select_server: mac=%s hops=%s tproc=%s cost=%.4f",
                mac, hops, tproc, cost,
            )
            if cost < best_cost:
                best_cost, best_entry = cost, entry

        if best_entry:
            logger.info("select_server: selected=%s cost=%.4f", best_entry["mac"], best_cost)
        return best_entry

    # ------------------------------------------------------------------
    # Storage selection — fixed per domain (MDVBP tier 0 baseline)
    # ------------------------------------------------------------------

    def select_storage(self, domain: str) -> dict | None:
        """Return the storage node for the given domain from its dedicated pool."""
        pool = self.vip_storage_pool_n1 if domain == "n1" else self.vip_storage_pool_n2
        if not pool:
            logger.warning("select_storage(%s): pool empty", domain)
            return None
        entry = next(iter(pool.values()))
        logger.info("select_storage(%s): selected=%s", domain, entry["mac"])
        return entry

    # ------------------------------------------------------------------
    # DNAT / SNAT rule installation
    # ------------------------------------------------------------------

    def _install_vip_dnat_snat(
        self, datapath, in_port, pkt, *,
        client_mac, client_ip, ip_proto, vip_ip, vip_mac, real_backend_ip, real_backend_mac,
    ):
        """Install a DNAT + SNAT flow rule pair and Packet-Out the first packet.

        DNAT (forward):
            match(eth_dst=VIP_MAC, ipv4_src=client, ipv4_dst=VIP, ip_proto)
            → set_field(eth_dst=real_mac, ipv4_dst=real_ip), output toward backend

        SNAT (return):
            match(eth_src=backend_mac, eth_dst=client_mac,
                  ipv4_src=backend, ipv4_dst=client, ip_proto)
            → set_field(eth_src=VIP_mac, ipv4_src=VIP_ip), output to client port

        src_port (TCP/UDP) is intentionally excluded.  For VIP_DATA one rule per
        (web_server_ip, domain_VIP) pair covers all concurrent connections from
        that web server, preventing tier-transition read inconsistency.
        For VIP_SERVER the same rule covers all parallel browser sub-connections,
        ensuring per-client server affinity.
        """
        parser  = datapath.ofproto_parser
        ofproto = datapath.ofproto

        # Prefer get_next_hop_port for multi-switch topologies; fall back to
        # host_attachment for single-switch (backend directly connected here).
        backend_port = self.get_next_hop_port(datapath.id, client_mac, real_backend_mac)
        if backend_port is None:
            backend_loc = self.host_attachment.get(real_backend_mac)
            if backend_loc is not None:
                _, backend_port = backend_loc
            elif real_backend_mac in self.peer_hosts and _ROUTER_OVS_PORT > 0:
                backend_port = _ROUTER_OVS_PORT
                logger.info(
                    "dnat/snat: cross-network mac=%s -> router port %d",
                    real_backend_mac, _ROUTER_OVS_PORT,
                )
            else:
                logger.warning(
                    "dnat/snat: mac=%s not reachable from dpid=%s, skipping",
                    real_backend_mac, datapath.id,
                )
                return

        # --- DNAT rule ---
        # eth_dst=vip_mac: the client sends to VIP_MAC (from our ARP reply).
        # ipv4_src=client_ip: scopes the rule to this specific client so
        #   multiple simultaneous clients each select their own backend.
        dnat_match = parser.OFPMatch(
            eth_type=0x0800,
            eth_src=client_mac,    # scope to this exact client (ref: eth_src=src)
            eth_dst=vip_mac,
            ipv4_src=client_ip,
            ipv4_dst=vip_ip,
            ip_proto=ip_proto,
        )
        dnat_actions = [
            parser.OFPActionSetField(eth_dst=real_backend_mac),
            parser.OFPActionSetField(ipv4_dst=real_backend_ip),
            parser.OFPActionOutput(backend_port),
        ]
        self._install_flow(
            datapath, priority=200,
            match=dnat_match, actions=dnat_actions,
            idle_timeout=_VIP_IDLE_TIMEOUT,
            hard_timeout=_VIP_HARD_TIMEOUT,
        )

        # --- SNAT rule ---
        # eth_dst=client_mac + ipv4_dst=client_ip are critical: without them ALL
        # outgoing traffic from the backend (to any host) would get its source
        # rewritten to VIP_IP, breaking the backend's non-VIP connections.
        snat_match = parser.OFPMatch(
            eth_type=0x0800,
            eth_src=real_backend_mac,
            eth_dst=client_mac,
            ipv4_src=real_backend_ip,
            ipv4_dst=client_ip,
            ip_proto=ip_proto,
        )
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
            vip_ip, real_backend_ip, _VIP_IDLE_TIMEOUT, _VIP_HARD_TIMEOUT,
        )

        # Packet-Out the first packet with DNAT actions so it reaches the backend
        # while the new flow rules propagate through the pipeline.
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=ofproto.OFP_NO_BUFFER,
            in_port=in_port,
            actions=dnat_actions,
            data=pkt.data,
        )
        datapath.send_msg(out)

    # ------------------------------------------------------------------
    # VIP ARP punt rules — send ARP-for-VIP to the controller
    # ------------------------------------------------------------------

    def install_vip_arp_punt_rules(self, datapath) -> None:
        """Punt ARP requests for VIP IPs to the controller (priority 100).

        Overrides the ARP flood rule (priority 1) installed by the topology
        mixin.  The controller replies with a crafted ARP reply packet
        (see _reply_vip_arp).  Pure OFP 1.3 is used throughout — no Nicira
        extensions required.
        """
        parser  = datapath.ofproto_parser
        ofproto = datapath.ofproto

        for vip_ip in (self.vip_server_ip, self.vip_data_n1_ip, self.vip_data_n2_ip):
            match   = parser.OFPMatch(eth_type=0x0806, arp_tpa=vip_ip)
            actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                              ofproto.OFPCML_NO_BUFFER)]
            self._install_flow(datapath, priority=100, match=match, actions=actions)

        logger.info("vip arp punt rules installed: dpid=%s", datapath.id)

    # ------------------------------------------------------------------
    # VIP IP punt rules — send VIP-destined IP packets to the controller
    # ------------------------------------------------------------------

    def install_vip_punt_rules(self, datapath) -> None:
        """Punt IPv4 packets destined for VIP addresses to the controller (priority 100).

        Once DNAT rules (priority 200) are installed they take precedence and
        subsequent packets bypass the controller entirely.  When the DNAT rule
        expires (idle_timeout or hard_timeout) the punt rule resumes and
        triggers fresh backend selection.
        """
        parser  = datapath.ofproto_parser
        ofproto = datapath.ofproto

        for vip_ip in (self.vip_server_ip, self.vip_data_n1_ip, self.vip_data_n2_ip):
            match   = parser.OFPMatch(eth_type=0x0800, ipv4_dst=vip_ip)
            actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                              ofproto.OFPCML_NO_BUFFER)]
            self._install_flow(datapath, priority=100, match=match, actions=actions)

        logger.info("vip ip punt rules installed: dpid=%s", datapath.id)

    # ------------------------------------------------------------------
    # Telemetry integration — called from _on_telemetry_update (Thread 2)
    # ------------------------------------------------------------------

    def update_server_tproc(self, servers: dict) -> None:
        """Update per-server T_proc values from a TelemetrySummary.servers dict.

        servers: dict[server_id, ServerSummary] as received from Thread 2.

        The server_id keys are container names (e.g. 'edge_server_n1').
        select_server currently queries the pool by MAC address, so this dict
        is a best-effort approximation until an explicit server_id → MAC
        mapping is wired up (e.g. via SERVER_IDS env or telemetry enrichment).
        """
        for server_id, summary in servers.items():
            self._server_tproc[server_id] = summary.avg_time_proc_ms
            logger.debug("tproc updated: %s = %.1fms", server_id, summary.avg_time_proc_ms)
