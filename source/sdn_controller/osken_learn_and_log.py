import eventlet
eventlet.monkey_patch()
import hashlib
import math
import os
import time
from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import (
    CONFIG_DISPATCHER,
    MAIN_DISPATCHER,
    set_ev_cls,
)
from os_ken.lib.packet import ethernet, ether_types, icmp, ipv4, packet, tcp, udp
from os_ken.ofproto import ofproto_v1_3

from sdn_controller.library.repositories.debit import DebitRepository
from sdn_controller.models.mongodb_host import MongodbRouter


class KenLearnAndLog(app_manager.OSKenApp):
    """Simple layer-2 learning switch with optional MongoDB logging."""
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(KenLearnAndLog, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.enable_reactive_learning = True
        self.datapaths = []
        self.servers_mac = [
            "00:00:00:00:00:04",
            "00:00:00:00:00:07",
            "00:00:00:00:00:09",
            "00:00:00:00:00:10",
        ]
        self.threashold_server_bps = 10000000  # 10 Mbps

        # Step D: debit snapshot cache (Mongo-backed).
        # Keep this lightweight and lazy so apps not using cost selection
        # don't pay connection overhead.
        self._vip_debit_refresh_sec = float(os.getenv("VIP_DEBIT_REFRESH_SEC", "5"))
        self._vip_debit_cache_ts = 0.0
        self._vip_debit_bps_by_server_mac = {}
        self._vip_debit_repo = None

        # VIP (Anycast service IP) configuration.
        # LAN-specific apps can override these, but defaults keep behavior explicit.
        self.vip_ip = os.getenv("VIP_IP", "10.0.0.100")
        self.vip_mac = os.getenv("VIP_MAC", "aa:bb:cc:dd:ee:ff")

        # Step E: selection weights + normalization.
        self.vip_w_hops = float(os.getenv("VIP_SCORE_HOPS_WEIGHT", "0.3"))
        self.vip_w_debit = float(os.getenv("VIP_SCORE_DEBIT_WEIGHT", "0.7"))
        self.vip_debit_norm_bps = float(
            os.getenv("VIP_DEBIT_NORM_BPS", str(self.threashold_server_bps))
        )
        # VIP flow key strategy for rendezvous hashing.
        # - pinned_dport: (client_ip, vip_ip, dport)
        #   Keeps TCP control + UDP data (iperf3 -u) on the same backend.
        #   Side-effect: all TCP connections from the same client to the same VIP port
        #   will stick to one backend (even with -P).
        # - five_tuple: (client_ip, vip_ip, proto, sport, dport)
        #   Distributes per-connection (TCP ephemeral source ports differ), but can
        #   break iperf3 UDP runs because TCP control and UDP data may pick different backends.
        # pinned_dport
        # five_tuple
        self.vip_flow_key_mode = str(os.getenv("VIP_FLOW_KEY_MODE", "five_tuple") or "five_tuple").strip().lower()
        self.vip_flow_idle_timeout_sec = int(os.getenv("VIP_FLOW_IDLE_TIMEOUT_SEC", "15"))

        # Step E: server MAC -> IP mapping (override with VIP_SERVER_MAC_IP_MAP).
        self.server_ip_by_mac = self._parse_server_mac_ip_map(
            os.getenv("VIP_SERVER_MAC_IP_MAP")
        )
        if not self.server_ip_by_mac:
            self.server_ip_by_mac = {
                "00:00:00:00:00:04": "10.0.0.4",
                "00:00:00:00:00:07": "10.0.1.4",
                "00:00:00:00:00:09": "10.0.0.6",
                "00:00:00:00:00:10": "10.0.1.5",
            }

    def _get_lan_id_for_debit(self) -> str:
        """Resolve LAN id used by DebitRepository snapshots.

        Convention in this repo is `_lan_id` on LAN-specific apps (e.g. "lan_1").
        Falls back to `LAN_ID` env var and finally "lan_1".
        """

        lan_id = getattr(self, "_lan_id", None)
        if isinstance(lan_id, str) and lan_id:
            return lan_id
        env_lan_id = os.getenv("LAN_ID")
        if isinstance(env_lan_id, str) and env_lan_id:
            return env_lan_id
        return "lan_1"

    def _get_vip_debit_repo(self) -> DebitRepository:
        if self._vip_debit_repo is None:
            mongo_uri = MongodbRouter().get_simple_connection_string(add_app=True)
            self._vip_debit_repo = DebitRepository(mongo_uri)
        return self._vip_debit_repo

    def _refresh_vip_debit_cache_if_needed(self) -> None:
        """Refresh cached per-server bps from MongoDB (latest debit snapshot).

        Cache stores only server-facing entries (peer_mac in `self.servers_mac`).
        Value is the max observed bps among ports that map to the same server MAC.
        """

        now = time.time()
        if (now - float(self._vip_debit_cache_ts or 0.0)) < self._vip_debit_refresh_sec:
            return

        lan_id = self._get_lan_id_for_debit()
        try:
            debit_stats = self._get_vip_debit_repo().get_debit_by_lan_id(lan_id)
        except Exception:
            # Keep previous cached values if Mongo is temporarily unavailable.
            self._vip_debit_cache_ts = now
            return

        bps_by_server_mac = {}
        for p in getattr(debit_stats, "port", []) or []:
            try:
                # Only use server-facing ports.
                peer_mac = str(getattr(p, "peer_mac", "") or "").lower()
                if not peer_mac or peer_mac not in getattr(self, "servers_mac", []):
                    continue

                # Ignore switch-link entries, keep host/server edges only.
                if getattr(p, "neighbor_switch_id", None) is not None:
                    continue

                flow_rate = float(getattr(p, "flow_rate", 0.0) or 0.0)
                prev = float(bps_by_server_mac.get(peer_mac, 0.0) or 0.0)
                if flow_rate > prev:
                    bps_by_server_mac[peer_mac] = flow_rate
            except Exception:
                continue

        self._vip_debit_bps_by_server_mac = bps_by_server_mac
        self._vip_debit_cache_ts = now

    def get_server_debit_bps_by_mac(self) -> dict:
        """Return cached debit map: server_mac -> bps (float)."""
        self._refresh_vip_debit_cache_if_needed()
        return dict(self._vip_debit_bps_by_server_mac or {})

    def get_server_debit_bps(self, server_mac: str) -> float:
        """Return cached debit for a specific server MAC, defaulting to 0.0."""
        if not server_mac:
            return 0.0
        self._refresh_vip_debit_cache_if_needed()
        return float((self._vip_debit_bps_by_server_mac or {}).get(str(server_mac).lower(), 0.0) or 0.0)

    def _parse_server_mac_ip_map(self, raw: str):
        """Parse VIP_SERVER_MAC_IP_MAP as mac=ip,mac=ip."""
        if not raw:
            return {}
        mapping = {}
        for item in raw.split(","):
            if not item.strip():
                continue
            if "=" not in item:
                continue
            mac, ip = item.split("=", 1)
            mac = mac.strip().lower()
            ip = ip.strip()
            if mac and ip:
                mapping[mac] = ip
        return mapping

    def _get_server_ip(self, server_mac: str):
        if not server_mac:
            return None
        return self.server_ip_by_mac.get(str(server_mac).lower())

    def _get_max_hops_cached(self) -> int:
        max_hops = getattr(self, "_hop_cache_max", None)
        if isinstance(max_hops, int) and max_hops > 0:
            return max_hops
        return 1

    def _get_hops_cached(self, host_mac: str, server_mac: str):
        if hasattr(self, "get_hops"):
            try:
                return self.get_hops(host_mac, server_mac)
            except Exception:
                return None
        return None

    def _compute_vip_cost(self, *, hops: int, debit_bps: float, max_hops: int) -> float:
        norm_hops = float(hops) / float(max(max_hops, 1))
        norm_bps = 0.0
        if self.vip_debit_norm_bps and self.vip_debit_norm_bps > 0:
            norm_bps = min(1.0, float(debit_bps) / float(self.vip_debit_norm_bps)) # The closer to the threshold the more costly the server is considered.
        return (self.vip_w_hops * norm_hops) + (self.vip_w_debit * norm_bps)

    def _select_backend_for_client(self, client_mac: str):
        """Select best backend server for a client based on hop + debit cost.

        Returns tuple (server_mac, server_ip, hops, debit_bps, score, max_hops) or None.
        """

        if not client_mac:
            return None

        max_hops = self._get_max_hops_cached()
        best = None

        for server_mac in getattr(self, "servers_mac", []) or []:
            hops = self._get_hops_cached(client_mac, server_mac)
            if hops is None:
                continue
            server_ip = self._get_server_ip(server_mac)
            if not server_ip:
                continue
            debit_bps = self.get_server_debit_bps(server_mac)
            score = self._compute_vip_cost(hops=hops, debit_bps=debit_bps, max_hops=max_hops)

            candidate = (server_mac, server_ip, hops, debit_bps, score, max_hops)
            if best is None or score < best[4]:
                best = candidate

        return best

    def _stable_hash_unit(self, text: str) -> float:
        """Return a stable pseudo-random float in (0, 1) for the given text."""
        if text is None:
            text = ""
        digest = hashlib.sha256(text.encode("utf-8", errors="ignore")).digest()
        value = int.from_bytes(digest[:8], byteorder="big", signed=False)
        return (value + 1) / float(2**64 + 1)

    def _select_backend_for_vip_flow(
        self,
        *,
        client_mac: str,
        client_ip: str,
        vip_ip: str,
        ip_proto: int,
        l4_sport: int | None,
        l4_dport: int | None,
    ):
        """Select backend for a VIP flow.

                Selection uses cost-aware rendezvous hashing, with a configurable flow key
                strategy via env var `VIP_FLOW_KEY_MODE`:

                - pinned_dport (default): per (client_ip, vip_ip, dport)
                    Keeps iperf3 UDP's TCP control and UDP data (same dport) on the same backend.
                - five_tuple: per (client_ip, vip_ip, proto, sport, dport)
                    Distributes per-connection, but may break iperf3 UDP tests.

                For ICMP (no ports), falls back to per-client selection.

        Returns tuple (server_mac, server_ip, hops, debit_bps, score, max_hops) or None.
        """

        if not client_mac:
            return None

        # ICMP or missing dport: keep stable per-client selection.
        # (For TCP/UDP we expect a destination port; source port may vary.)
        if ip_proto == 1 or not l4_dport:
            return self._select_backend_for_client(client_mac)

        max_hops = self._get_max_hops_cached()
        candidates = []
        for server_mac in getattr(self, "servers_mac", []) or []:
            hops = self._get_hops_cached(client_mac, server_mac)
            if hops is None:
                continue
            server_ip = self._get_server_ip(server_mac)
            if not server_ip:
                continue
            debit_bps = self.get_server_debit_bps(server_mac)
            cost = self._compute_vip_cost(hops=hops, debit_bps=debit_bps, max_hops=max_hops)
            candidates.append((server_mac, server_ip, hops, debit_bps, float(cost), max_hops))

        if not candidates:
            return None

        # Cost-aware rendezvous hashing: each flow key ranks servers differently,
        # but lower-cost servers are favored.
        mode = str(getattr(self, "vip_flow_key_mode", "pinned_dport") or "pinned_dport").strip().lower()
        if mode == "five_tuple":
            if l4_sport is None:
                # Without a source port, five-tuple can't distribute per-connection.
                # Fall back to the pinned_dport behavior.
                flow_key = f"{client_ip}|{vip_ip}|{int(l4_dport)}"
            else:
                flow_key = f"{client_ip}|{vip_ip}|{int(ip_proto)}|{int(l4_sport)}|{int(l4_dport)}"
        else:
            # pinned_dport (default)
            flow_key = f"{client_ip}|{vip_ip}|{int(l4_dport)}"
        best = None
        best_rank = None
        eps = 1e-6
        for server_mac, server_ip, hops, debit_bps, cost, max_hops in candidates:
            weight = 1.0 / max(cost + eps, eps) # The lower the cost, the higher the weight (with epsilon to avoid division by zero).
            u = self._stable_hash_unit(flow_key + "|" + str(server_mac).lower()) # Stable pseudo-random unit in (0, 1) for this flow-server pair. Always the same for the same inputs
            rank = weight / max(-math.log(u), eps) # 
            if best is None or rank > float(best_rank):
                best = (server_mac, server_ip, hops, debit_bps, cost, max_hops)
                best_rank = rank

        return best

    def _get_datapath_by_dpid(self, dpid):
        if hasattr(self, "_datapath_by_id"):
            dp_entry = getattr(self, "_datapath_by_id", {}).get(dpid)
            if dp_entry:
                return dp_entry[0]
        for dp in getattr(self, "datapaths", []) or []:
            if getattr(dp, "id", None) == dpid:
                return dp
        return None

    def _get_edge_switch(self, host_mac: str):
        if hasattr(self, "get_edge_switch"):
            try:
                return self.get_edge_switch(host_mac)
            except Exception:
                return None
        return None

    def _get_next_hop_port(self, edge_dpid: int, client_mac: str, server_mac: str):
        if hasattr(self, "get_next_hop_port"):
            try:
                return self.get_next_hop_port(edge_dpid, client_mac, server_mac)
            except Exception:
                return None
        return None

    def _install_flow(self, datapath, priority, match, actions, *,
                      idle_timeout=0, hard_timeout=0, cookie=0, flags=None):
        ofproto = datapath.ofproto
        if flags is None:
            flags = ofproto.OFPFF_SEND_FLOW_REM
                
        instructions = [
            datapath.ofproto_parser.OFPInstructionActions(
                ofproto.OFPIT_APPLY_ACTIONS,
                actions,
            )
        ]
        mod = datapath.ofproto_parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=instructions,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout,
            cookie=cookie,
            flags=flags,
            command=ofproto.OFPFC_ADD,
        )
        datapath.send_msg(mod)

    def add_flow(self, datapath, in_port, dst, src, actions):
        """Default reactive learning-switch rule installer."""
        parser = datapath.ofproto_parser
        match = parser.OFPMatch(
            in_port=in_port,
            eth_dst=dst,
            eth_src=src,
        )
        self._install_flow(
            datapath,
            priority=10,
            match=match,
            actions=actions,
            flags=datapath.ofproto.OFPFF_SEND_FLOW_REM,
        )


    # Event handler for switch features. This method is triggered when a switch connects to the controller.
    # @set_ev_cls decorator tells OS-Ken that the method "switch_features_handler" should be invoked when an EventOFPSwitchFeatures event is received.
    # CONFIG_DISPATCHER means this event is handled after the switch enters the configuration phase (after the initial handshake between switch and controller).
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, event):
        """Install the table-miss flow entry when the switch connects. 
        At first switch is configured to flood all packets in order to learn MAC addresses."""
    
        # Extract the datapath object, which represents in the controller enviroment the switch that is communicating with the controller.
        # The datapath contains information about the switch (datapath ID, methods to send messages, etc.)
        datapath = event.msg.datapath

        # ofproto represents the OpenFlow protocol, which includes constants (like action types and message types).
        ofproto = datapath.ofproto

        # The parser helps in creating OpenFlow messages such as matches, actions, flow mods, etc.
        parser = datapath.ofproto_parser
        
        self.datapaths.append(datapath)

        # Create a match object with no specific fields, meaning it will match all packets (wildcard match).
        # This is the default behavior of a hub, which forwards all traffic.
        match = parser.OFPMatch()
        
        # Create an action to output the packets to the controller and not buffer them.
        # This ensures that all packets that do not match any flow entries are sent to the controller
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        
        # Create a flow modification message to install the "table-miss" flow entry in the switch.
        instructions = [
            parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)
        ]
        mod = datapath.ofproto_parser.OFPFlowMod(
            datapath=datapath, # The switch this flow is being installed on.
            priority=0, # The lowest priority for the table-miss flow entry.
            match=match, # specifies the matching rule (matches all packets here because the match is empty and any traffic becomes selected).
            instructions=instructions, # Apply actions through the OpenFlow 1.3 instruction pipeline.
            flags=ofproto.OFPFF_SEND_FLOW_REM # flag that tells the switch to notify the controller when the flow is removed.
        )
        datapath.send_msg(mod)

        # Proactively punt VIP ICMP echo requests to the controller.
        # This guarantees the controller sees the first packet of a VIP “flow” even if
        # other proactive forwarding rules exist.
        try:
            vip_match = parser.OFPMatch(
                eth_type=ether_types.ETH_TYPE_IP,
                ipv4_dst=self.vip_ip,
                ip_proto=1,  # ICMP
                icmpv4_type=8,  # echo request
            )
            vip_actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
            self._install_flow(datapath, priority=100, match=vip_match, actions=vip_actions)
        except Exception:
            # Keep controller robust if the switch/parser doesn't support a field.
            pass


    # Packet In Handler
    # This method is triggered when a packet is received by the switch.
    # It learns MAC addresses and their associated ports, logs the event, and forwards the packet.
    # The next time a packet with the same source and destination MAC addresses is received, it will be forwarded directly without flooding or 
    # involving the controller again.
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, event):
        """Learn MAC-port mappings, log the event, and forward the packet."""

        msg = event.msg  # Extract the message from the event
        datapath = msg.datapath  # Get the switch (datapath) that sent the message
        ofproto = datapath.ofproto  # Get the OpenFlow protocol constants for this datapath
        parser = datapath.ofproto_parser  # Get the OpenFlow message parser for creating messages
        in_port = msg.match["in_port"]  # Get the input port from which the packet was received
        
        pkt = packet.Packet(msg.data) # Create a Packet object from the incoming packet data
        eth = pkt.get_protocol(ethernet.ethernet) # Extract the Ethernet header from the message
        dst = eth.dst # Get the destination MAC address from the Ethernet header frame
        src = eth.src # Get the source MAC address from the Ethernet header frame
        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        # Parse L3/L4 protocols used by the VIP service.
        # (Selection + DNAT/SNAT rules are added in later steps.)
        ipv4_hdr = pkt.get_protocol(ipv4.ipv4)
        icmp_hdr = pkt.get_protocol(icmp.icmp)
        tcp_hdr = pkt.get_protocol(tcp.tcp)
        udp_hdr = pkt.get_protocol(udp.udp)

        # Until VIP DNAT/SNAT is implemented, avoid flooding VIP frames (dst MAC is VIP_MAC)
        # which can create noisy broadcasts with no receiver.
        if ipv4_hdr is not None and str(getattr(ipv4_hdr, "dst", "")) == self.vip_ip:
            ip_proto = getattr(ipv4_hdr, "proto", None)
            # Only process ICMP, TCP, UDP for VIP selection; ignore other L4 protocols.
            if ip_proto not in (1, 6, 17):
                return

            # Implement per-(src_ip, dst_ip, ip_proto, src_port, dst_port) load balancing.
            # For ICMP there are no ports; we keep the existing ICMP type-based matching.
            fwd_l4_match = {}
            rev_l4_match = {}
            if ip_proto == 6:
                if tcp_hdr is None:
                    return
                tcp_src = int(getattr(tcp_hdr, "src_port", 0) or 0)
                tcp_dst = int(getattr(tcp_hdr, "dst_port", 0) or 0)
                if tcp_src <= 0 or tcp_dst <= 0:
                    return
                fwd_l4_match = {"tcp_src": tcp_src, "tcp_dst": tcp_dst}
                rev_l4_match = {"tcp_src": tcp_dst, "tcp_dst": tcp_src}

            if ip_proto == 17:
                if udp_hdr is None:
                    return
                udp_src = int(getattr(udp_hdr, "src_port", 0) or 0)
                udp_dst = int(getattr(udp_hdr, "dst_port", 0) or 0)
                if udp_src <= 0 or udp_dst <= 0:
                    return
                fwd_l4_match = {"udp_src": udp_src, "udp_dst": udp_dst}
                rev_l4_match = {"udp_src": udp_dst, "udp_dst": udp_src}

            client_ip = str(getattr(ipv4_hdr, "src", ""))
            l4_sport = None
            l4_dport = None
            if ip_proto == 6:
                l4_sport, l4_dport = tcp_src, tcp_dst
            elif ip_proto == 17:
                l4_sport, l4_dport = udp_src, udp_dst

            selection = self._select_backend_for_vip_flow(
                client_mac=src,
                client_ip=client_ip,
                vip_ip=self.vip_ip,
                ip_proto=int(ip_proto or 0),
                l4_sport=l4_sport,
                l4_dport=l4_dport,
            )
            if selection is None:
                return

            server_mac, server_ip, hops, debit_bps, score, max_hops = selection
            edge_info = self._get_edge_switch(src)
            if edge_info is None:
                return

            edge_dpid, client_port = edge_info
            edge_dp = self._get_datapath_by_dpid(edge_dpid)
            if edge_dp is None:
                return

            next_hop_port = self._get_next_hop_port(edge_dpid, src, server_mac)
            if next_hop_port is None:
                return

            lan_id = self._get_lan_id_for_debit()

            l4_sport = "-"
            l4_dport = "-"
            if ip_proto == 6:
                l4_sport = str(tcp_src)
                l4_dport = str(tcp_dst)
            elif ip_proto == 17:
                l4_sport = str(udp_src)
                l4_dport = str(udp_dst)

            print(
                "VIP_SELECT lan_id={} vip={} proto={} sport={} dport={} client_ip={} client_mac={} backend_ip={} backend_mac={} hops={} max_hops={} debit_bps={:.2f} score={:.4f}".format(
                    lan_id,
                    self.vip_ip,
                    ip_proto,
                    l4_sport,
                    l4_dport,
                    client_ip,
                    src,
                    server_ip,
                    server_mac,
                    hops,
                    max_hops,
                    float(debit_bps),
                    float(score),
                )
            )

            edge_parser = edge_dp.ofproto_parser
            edge_ofproto = edge_dp.ofproto

            dnat_match_kwargs = dict(
                eth_type=ether_types.ETH_TYPE_IP,
                eth_src=src,
                eth_dst=self.vip_mac,
                ipv4_src=client_ip,
                ipv4_dst=self.vip_ip,
                ip_proto=ip_proto,
                **fwd_l4_match,
            )
            snat_match_kwargs = dict(
                eth_type=ether_types.ETH_TYPE_IP,
                eth_src=server_mac,
                eth_dst=src,
                ipv4_src=server_ip,
                ipv4_dst=client_ip,
                ip_proto=ip_proto,
                **rev_l4_match,
            )

            if ip_proto == 1 and icmp_hdr is not None:
                dnat_match_kwargs["icmpv4_type"] = 8
                snat_match_kwargs["icmpv4_type"] = 0

            # DNAT: client -> VIP -> backend (installed on client edge switch)
            dnat_match = edge_parser.OFPMatch(**dnat_match_kwargs)
            dnat_actions = [
                edge_parser.OFPActionSetField(ipv4_dst=server_ip),
                edge_parser.OFPActionSetField(eth_dst=server_mac),
                edge_parser.OFPActionOutput(next_hop_port),
            ]
            self._install_flow(
                edge_dp,
                priority=200,
                match=dnat_match,
                actions=dnat_actions,
                idle_timeout=self.vip_flow_idle_timeout_sec,
            )

            # SNAT: backend -> client (rewrite source to VIP on last hop)
            snat_match = edge_parser.OFPMatch(**snat_match_kwargs)
            snat_actions = [
                edge_parser.OFPActionSetField(ipv4_src=self.vip_ip),
                edge_parser.OFPActionSetField(eth_src=self.vip_mac),
                edge_parser.OFPActionOutput(client_port),
            ]
            self._install_flow(
                edge_dp,
                priority=200,
                match=snat_match,
                actions=snat_actions,
                idle_timeout=self.vip_flow_idle_timeout_sec,
            )

            # PacketOut the first packet using DNAT actions.
            po_data = None
            buffer_id = msg.buffer_id
            if edge_dp.id != datapath.id or msg.buffer_id == edge_ofproto.OFP_NO_BUFFER:
                buffer_id = edge_ofproto.OFP_NO_BUFFER
                po_data = msg.data

            packet_out = edge_parser.OFPPacketOut(
                datapath=edge_dp,
                buffer_id=buffer_id,
                in_port=client_port,
                actions=dnat_actions,
                data=po_data,
            )
            edge_dp.send_msg(packet_out)
            return
        
        dpid_int = int(datapath.id)  # Datapath ID as integer for shard key routing
        self.mac_to_port.setdefault(dpid_int, {})  # Initialize mapping for this switch if absent
        
        # Learn a MAC address to avoid flooding next time
        if src not in self.mac_to_port[dpid_int]:  # If the source MAC is not already tracked for this switch
            self.mac_to_port[dpid_int][src] = in_port
            # print("mac_to_port[%s]: %s", dpid_int, self.mac_to_port[dpid_int])
        
        # Determine the output port for the destination MAC address    
        if dst in self.mac_to_port[dpid_int]:
            out_port = self.mac_to_port[dpid_int][dst]
        else:
            # Flood the packet if the destination MAC is unknown
            out_port = ofproto.OFPP_FLOOD

        # Create the action to forward the packet to the determined output port
        actions = [parser.OFPActionOutput(out_port)]

        # Install a flow entry to avoid future packet_in events for this flow
        if self.enable_reactive_learning and out_port != ofproto.OFPP_FLOOD:
            self.add_flow(datapath, in_port, dst, src, actions)
        
        data = None
        # If the packet is not buffered on the switch, include the packet data in the packet-out message
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        # Create a packet-out message to send the packet out of the switch
        out = datapath.ofproto_parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data,
        )
        
        # Send the packet-out message to the switch
        datapath.send_msg(out)
