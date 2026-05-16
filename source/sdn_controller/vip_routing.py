"""VIP routing mixin for the OS-Ken SDN controller.

Responsibilities:
  - ARP interception for VIP addresses (reactive, controller-generated replies)
  - IP packet interception for VIP_SERVER and VIP_DATA
  - DNAT/SNAT flow rule installation (priority 200, with timeouts)
  - Multi-dimensional WSM cost-based server selection (CPU, RAM, requests, hops)
  - Multi-dimensional WSM cost-based storage selection (CPU, RAM, connections,
    replication lag, hops)
  - Per-domain VIP_DATA: VIP_DATA_N1 routes to LAN1 storage,
    VIP_DATA_N2 routes to LAN2 storage

Cross-network support: when pools contain backends on the peer LAN (learned
via TopologyMixin.peer_hosts), select_server/select_storage can pick them.
DNAT'd packets are output to ROUTER_OVS_PORT so the inter-LAN router
forwards them to the remote switch, which delivers them via normal L2
forwarding (the packet is already rewritten — no second VIP PacketIn).

This is NOT a new thread.  All methods are called inline by Thread 1's
packet_in_handler.  State written by Thread 2 (_server_stats, _storage_stats)
is read here without additional locking because eventlet uses cooperative
switching and these dicts are only mutated between yield points. Warm-lease
state is the exception: native Thread 3 writes it too, so that slice is
guarded by a small threading.Lock.

Usage (class MRO in main_n*.py):
    class KenLearnAndLog(VipRoutingMixin, TopologyMixin, OSKenApp):
        ...
"""
import logging
import os
import threading
import time
from dataclasses import dataclass

from os_ken.lib.packet import arp as arp_lib
from os_ken.lib.packet import ethernet as eth_lib
from os_ken.lib.packet import ether_types, ipv4, packet
from os_ken.lib.packet import tcp as tcp_lib

from .scaling_config import _VIP_WARM_SERVER_SECONDS, _VIP_WARM_STORAGE_SECONDS
from .telemetry.models import ServerSummary, StorageServerSummary

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


class VipRoutingMixin:
    """Mixin that intercepts traffic for VIP_SERVER (HTTP) and VIP_DATA (MongoDB).

    Must sit *before* TopologyMixin in the class MRO so that the
    _on_datapath_connected hook is called in the correct cooperative order.

    Depends on TopologyMixin attributes (set at __init__ time):
        vip_server_ip, vip_server_mac,
        vip_data_n1_ip, vip_data_n1_mac, vip_data_n2_ip, vip_data_n2_mac,
        vip_data_recovery_n1_ip, vip_data_recovery_n1_mac,
        vip_data_recovery_n2_ip, vip_data_recovery_n2_mac,
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

        # Per-server / per-storage telemetry stats, keyed by MAC.
        # Each container discovers its own MAC and includes it in telemetry
        # events — the aggregator forwards it as the dict key.
        # Updated by Thread 2 via update_server_stats() / update_storage_stats().
        # Read by Thread 1 cost functions (select_server / select_storage).
        self._server_stats:  dict[str, ServerSummary]        = {} # mac -> ServerSummary
        self._storage_stats: dict[str, StorageServerSummary] = {} # mac -> StorageServerSummary

        # Round-robin counters for cold-start tie-breaking.
        # When multiple backends share the lowest WSM cost (common during cold
        # start when all resource dimensions are 0.0), the counter ensures
        # traffic is distributed instead of always hitting the first entry.
        self._rr_server_idx: int = 0
        self._rr_storage_idx: dict[str, int] = {}   # domain -> counter

        self._warm_lock = threading.Lock()
        self._warm_server_leases: dict[str, WarmLease] = {} # mac -> lease
        self._warm_storage_leases: dict[str, dict[str, WarmLease]] = {
            "n1": {},
            "n2": {},
        } # domain -> (mac -> lease)

        logger.debug(
            "vip routing mixin: w_cpu=%.2f w_ram=%.2f w_req=%.2f w_hops=%.2f "
            "idle_timeout=%ds hard_timeout=%ds router_port=%d warm_storage=%.1fs warm_server=%.1fs",
            _W_CPU, _W_RAM, _W_REQUESTS, _W_HOPS,
            _VIP_IDLE_TIMEOUT, _VIP_HARD_TIMEOUT,
            _ROUTER_OVS_PORT,
            _VIP_WARM_STORAGE_SECONDS,
            _VIP_WARM_SERVER_SECONDS,
        )

    def _iter_vip_bindings(self):
        yield (self.vip_server_ip, self.vip_server_mac, "server", False)
        yield (self.vip_data_n1_ip, self.vip_data_n1_mac, "n1", False)
        yield (self.vip_data_n2_ip, self.vip_data_n2_mac, "n2", False)
        yield (self.vip_data_recovery_n1_ip, self.vip_data_recovery_n1_mac, "n1", True)
        yield (self.vip_data_recovery_n2_ip, self.vip_data_recovery_n2_mac, "n2", True)

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

    def _claim_warm_backend(
        self,
        vip_name: str,
        leases: dict[str, WarmLease],
        pool: dict[str, dict],
    ) -> dict | None:
        """Check for and claim any warm lease for a backend in the pool."""
        now = time.monotonic()
        
        with self._warm_lock:
            
            expired = [
                mac
                for mac, lease in leases.items()
                if lease.expires_ts <= now
            ]
            for mac in expired:
                leases.pop(mac, None)

            candidates = [
                (mac, lease)
                for mac, lease in leases.items()
                if mac in pool and mac in self._mac_to_ip
            ]
            if not candidates:
                for mac in expired:
                    logger.info("%s warm lease expired: mac=%s", vip_name, mac)
                return None

            mac, lease = max(candidates, key=lambda item: item[1].started_ts)
            chosen = pool[mac]

        for expired_mac in expired:
            logger.info("%s warm lease expired: mac=%s", vip_name, expired_mac)

        logger.info(
            "%s warm lease claimed: mac=%s remaining=%.1fs",
            vip_name,
            mac,
            max(lease.expires_ts - now, 0.0),
        )
        return chosen

    # Controller-side lifecycle hooks used by Thread 2 and Thread 3 to keep
    # VIP membership, backend IP seeding, and warm-lease state synchronized
    # when dynamic backends are promoted, admitted, removed, or retracted.

    def mark_server_backend_warm(self, mac: str) -> None:
        now = time.monotonic()
        with self._warm_lock:
            self._warm_server_leases[mac] = WarmLease(
                started_ts=now,
                expires_ts=now + _VIP_WARM_SERVER_SECONDS,
            )
        logger.info(
            "vip_server warm lease created: mac=%s ttl=%.1fs",
            mac,
            _VIP_WARM_SERVER_SECONDS,
        )

    def mark_storage_backend_warm(self, mac: str, domain: str) -> None:
        now = time.monotonic()
        with self._warm_lock:
            domain_leases = self._warm_storage_leases.setdefault(domain, {})
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

    def clear_server_backend_warm(self, mac: str) -> None:
        with self._warm_lock:
            cleared = self._warm_server_leases.pop(mac, None) is not None
        if cleared:
            logger.info("vip_server warm lease cleared: mac=%s", mac)

    def clear_storage_backend_warm(self, mac: str, domain: str) -> None:
        with self._warm_lock:
            domain_leases = self._warm_storage_leases.setdefault(domain, {})
            cleared = domain_leases.pop(mac, None) is not None
        if cleared:
            logger.info("vip_data(%s) warm lease cleared: mac=%s", domain, mac)

    def register_new_server_backend(self, mac: str, ip: str) -> None:
        self.add_server_mac(mac)
        self.register_backend_ip(mac, ip)
        self.mark_server_backend_warm(mac)

    def unregister_server_backend(self, mac: str) -> None:
        self.remove_server_mac(mac)
        self.clear_server_backend_warm(mac)

    def unregister_storage_backend(self, mac: str, domain: str) -> None:
        self.remove_storage_mac(mac, domain)
        self.clear_storage_backend_warm(mac, domain)

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
                and any(arp_pkt.dst_ip == vip_ip for vip_ip, _, _, _ in self._iter_vip_bindings())
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
        if dst_ip == self.vip_data_recovery_n1_ip:
            logger.debug("vip data recovery n1 packet-in: dpid=%s in_port=%s ip=%s", datapath.id, in_port, ip_pkt)
            return self._handle_vip_data(
                datapath, in_port, pkt, src_mac, src_ip, ip_proto, domain="n1", recovery=True
            )
        if dst_ip == self.vip_data_recovery_n2_ip:
            logger.debug("vip data recovery n2 packet-in: dpid=%s in_port=%s ip=%s", datapath.id, in_port, ip_pkt)
            return self._handle_vip_data(
                datapath, in_port, pkt, src_mac, src_ip, ip_proto, domain="n2", recovery=True
            )

        return False

    # ------------------------------------------------------------------
    # ARP reply generation
    # ------------------------------------------------------------------

    def _reply_vip_arp(self, datapath, in_port, arp_req) -> bool:
        """Craft and send an ARP reply for a VIP address request."""
        vip_ip = None
        vip_mac = None
        for candidate_ip, candidate_mac, _, _ in self._iter_vip_bindings():
            if arp_req.dst_ip == candidate_ip:
                vip_ip = candidate_ip
                vip_mac = candidate_mac
                break
        if vip_ip is None or vip_mac is None:
            return False

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
        logger.debug("vip_server: _mac_to_ip=%s", self._mac_to_ip)
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

    def _handle_vip_data(self, datapath, in_port, pkt, src_mac, src_ip, ip_proto, *, domain, recovery=False) -> bool: # * allows passing domain as a keyword-only argument for clarity
        storage = self.select_storage(domain, src_mac)
        if storage is None:
            logger.warning("vip_data(%s): pool empty, packet dropped", domain)
            return True

        storage_mac = storage["mac"]
        logger.debug("vip_data(%s): _mac_to_ip=%s", domain, self._mac_to_ip)
        storage_ip  = self._mac_to_ip.get(storage_mac)
        if storage_ip is None:
            logger.warning(
                "vip_data(%s): IP unknown for mac=%s — awaiting ARP from backend",
                domain, storage_mac,
            )
            return True

        if recovery and domain == "n1":
            vip_ip, vip_mac = self.vip_data_recovery_n1_ip, self.vip_data_recovery_n1_mac
        elif recovery and domain == "n2":
            vip_ip, vip_mac = self.vip_data_recovery_n2_ip, self.vip_data_recovery_n2_mac
        elif domain == "n1":
            vip_ip, vip_mac = self.vip_data_n1_ip, self.vip_data_n1_mac
        else:
            vip_ip, vip_mac = self.vip_data_n2_ip, self.vip_data_n2_mac

        tcp_src_port = None
        tcp_dst_port = None
        if recovery:
            tcp_pkt = pkt.get_protocol(tcp_lib.tcp)
            if ip_proto != 6 or tcp_pkt is None or tcp_pkt.dst_port != 27018:
                logger.warning(
                    "vip_data(%s) recovery: non-Mongo recovery packet dropped proto=%s dst_port=%s",
                    domain,
                    ip_proto,
                    getattr(tcp_pkt, "dst_port", None),
                )
                return True
            tcp_src_port = tcp_pkt.src_port
            tcp_dst_port = tcp_pkt.dst_port

        self._install_vip_dnat_snat(
            datapath, in_port, pkt,
            client_mac=src_mac,
            client_ip=src_ip,
            ip_proto=ip_proto,
            vip_ip=vip_ip,
            vip_mac=vip_mac,
            real_backend_ip=storage_ip,
            real_backend_mac=storage_mac,
            tcp_src_port=tcp_src_port,
            tcp_dst_port=tcp_dst_port,
            idle_timeout=_VIP_DATA_RECOVERY_IDLE_TIMEOUT if recovery else None,
            hard_timeout=_VIP_DATA_RECOVERY_HARD_TIMEOUT if recovery else None,
        )
        
        logger.info(
            "vip_data(%s): client=%s -> vip=%s -> real=%s recovery=%s",
            domain, src_ip, vip_ip, storage_ip, recovery,
        )
        
        return True

    # ------------------------------------------------------------------
    # Server selection — multi-dimensional WSM cost function
    # ------------------------------------------------------------------

    def select_server(self, client_mac: str) -> dict | None:
        """Pick the web server with the lowest WSM cost from vip_server_pool.

        Cost_j = w_cpu·(CPU_j/CPU_max) + w_ram·(RAM_j/RAM_max)
               + w_req·(Req_j/Req_max) + w_hops·(Hops_j/Hops_max)

        When multiple candidates share the lowest cost (typical during cold
        start when all resource dimensions are 0.0), round-robin across them
        to distribute traffic evenly.
        """
        pool = self.vip_server_pool
        if not pool:
            logger.warning("select_server: pool empty")
            return None

        warm = self._claim_warm_backend("vip_server", self._warm_server_leases, pool)
        if warm is not None:
            return warm

        # Compute max values for normalization (only from servers in the pool)
        pool_stats = [self._server_stats[m] for m in pool if m in self._server_stats]
        cpu_max = max((s.avg_cpu_percent for s in pool_stats), default=0.0) or 1.0
        ram_max = max((s.avg_ram_used_mb  for s in pool_stats), default=0.0) or 1.0
        req_max = max((s.request_count    for s in pool_stats), default=0)   or 1
        hops_max = max(self._hop_cache_max, 1)

        best_cost = float("inf") # initialized to infinity so any real cost will be lower, ensuring at least one candidate is selected
        tied: list[dict] = []

        for mac, entry in pool.items():
            stats = self._server_stats.get(mac)

            # Unknown stats → treat as worst-case (1.0) so backends without
            # telemetry yet (e.g. peer backends, newly added nodes) are not
            # accidentally preferred over measured local backends.
            cpu_norm = (stats.avg_cpu_percent / cpu_max) if stats else 1.0
            ram_norm = (stats.avg_ram_used_mb  / ram_max) if stats else 1.0
            req_norm = (stats.request_count    / req_max) if stats else 1.0

            hops = (self.hop_cache.get(client_mac) or {}).get(mac)
            if hops is None:
                if mac in self.peer_hosts:
                    local_avg = max(self._avg_hop_count, 1.0)
                    peer_avg  = max(self._peer_avg_hop_count, 1.0)
                    hops = local_avg + peer_avg
                elif mac in self.host_attachment:
                    hops = max(self._avg_hop_count, 1.0)   # local unknown: avg local cost
                else:
                    hops = hops_max   # truly unknown MAC — safety net
            hop_norm = hops / hops_max

            cost = (_W_CPU * cpu_norm + _W_RAM * ram_norm
                    + _W_REQUESTS * req_norm + _W_HOPS * hop_norm)
            logger.debug(
                "select_server: mac=%s cpu=%.1f ram=%.1f req=%s hops=%s cost=%.4f",
                mac,
                stats.avg_cpu_percent if stats else 0.0,
                stats.avg_ram_used_mb if stats else 0.0,
                stats.request_count if stats else 0,
                hops, cost,
            )
            if cost < best_cost:
                best_cost = cost
                tied = [entry]
            elif cost == best_cost:
                tied.append(entry)

        if not tied:
            return None

        chosen = tied[self._rr_server_idx % len(tied)] # select from tied candidates using round-robin index
        self._rr_server_idx += 1
        logger.info(
            "select_server: selected=%s cost=%.4f (tied=%d rr_idx=%d)",
            chosen["mac"], best_cost, len(tied), self._rr_server_idx - 1,
        )
        return chosen

    # ------------------------------------------------------------------
    # Storage selection — multi-dimensional WSM cost function
    # ------------------------------------------------------------------

    def select_storage(self, domain: str, client_mac: str) -> dict | None:
        """Pick the storage node with the lowest WSM cost from the domain's pool.

        Cost_j = w_cpu·(CPU_j/CPU_max) + w_ram·(RAM_j/RAM_max)
               + w_conn·(Conn_j/Conn_max) + w_lag·(Lag_j/Lag_max)
               + w_hops·(Hops_j/Hops_max)

        When multiple candidates share the lowest cost (typical during cold
        start when all resource dimensions are 0.0), round-robin across them
        to distribute traffic evenly.  Each domain has its own counter.
        """
        pool = self.vip_storage_pool_n1 if domain == "n1" else self.vip_storage_pool_n2
        if not pool:
            logger.warning("select_storage(%s): pool empty", domain)
            return None

        warm = self._claim_warm_backend(
            f"vip_data({domain})",
            self._warm_storage_leases.setdefault(domain, {}),
            pool,
        )
        if warm is not None:
            return warm

        pool_stats = [self._storage_stats[m] for m in pool if m in self._storage_stats]
        cpu_max  = max((s.avg_cpu_percent        for s in pool_stats), default=0.0) or 1.0
        ram_max  = max((s.avg_ram_used_mb         for s in pool_stats), default=0.0) or 1.0
        conn_max = max((s.avg_connections          for s in pool_stats), default=0.0) or 1.0
        lag_max  = max((s.avg_repl_lag_s or 0      for s in pool_stats), default=0.0) or 1.0
        hops_max = max(self._hop_cache_max, 1)

        best_cost = float("inf") # initialized to infinity so any real cost will be lower, ensuring at least one candidate is selected
        tied: list[dict] = []

        for mac, entry in pool.items():
            stats = self._storage_stats.get(mac)

            # Unknown stats → treat as worst-case (1.0) so backends without
            # telemetry yet (e.g. peer backends, newly added nodes) are not
            # accidentally preferred over measured local backends.
            cpu_norm  = (stats.avg_cpu_percent        / cpu_max)  if stats else 1.0
            ram_norm  = (stats.avg_ram_used_mb         / ram_max)  if stats else 1.0
            conn_norm = (stats.avg_connections          / conn_max) if stats else 1.0
            lag_norm  = ((stats.avg_repl_lag_s or 0)   / lag_max)  if stats else 1.0

            hops = (self.hop_cache.get(client_mac) or {}).get(mac)
            if hops is None:
                if mac in self.peer_hosts:
                    local_avg = max(self._avg_hop_count, 1.0)
                    peer_avg  = max(self._peer_avg_hop_count, 1.0)
                    hops = local_avg + peer_avg
                elif mac in self.host_attachment:
                    hops = max(self._avg_hop_count, 1.0)   # local unknown: avg local cost
                else:
                    hops = hops_max   # truly unknown MAC — safety net
            hop_norm = hops / hops_max

            cost = (_W_STORAGE_CPU * cpu_norm + _W_STORAGE_RAM * ram_norm
                    + _W_STORAGE_CONNECTIONS * conn_norm
                    + _W_STORAGE_LAG * lag_norm + _W_STORAGE_HOPS * hop_norm)
            logger.debug(
                "select_storage(%s): mac=%s cpu=%.1f ram=%.1f conn=%.1f lag=%.2f hops=%s cost=%.4f",
                domain, mac,
                stats.avg_cpu_percent if stats else 0.0,
                stats.avg_ram_used_mb if stats else 0.0,
                stats.avg_connections if stats else 0.0,
                (stats.avg_repl_lag_s or 0) if stats else 0.0,
                hops, cost,
            )
            if cost < best_cost:
                best_cost = cost
                tied = [entry]
            elif cost == best_cost:
                tied.append(entry)

        if not tied:
            return None

        rr_idx = self._rr_storage_idx.get(domain, 0)
        chosen = tied[rr_idx % len(tied)] # select from tied candidates using round-robin index
        self._rr_storage_idx[domain] = rr_idx + 1
        logger.info(
            "select_storage(%s): selected=%s cost=%.4f (tied=%d rr_idx=%d)",
            domain, chosen["mac"], best_cost, len(tied), rr_idx,
        )
        return chosen

    # ------------------------------------------------------------------
    # DNAT / SNAT rule installation
    # ------------------------------------------------------------------

    def _install_vip_dnat_snat(
        self, datapath, in_port, pkt, *,
        client_mac, client_ip, ip_proto, vip_ip, vip_mac, real_backend_ip, real_backend_mac,
        tcp_src_port=None, tcp_dst_port=None,
        idle_timeout=None, hard_timeout=None,
    ):
        """Install a DNAT + SNAT flow rule pair and Packet-Out the first packet.

        DNAT (forward):
            match(eth_dst=VIP_MAC, ipv4_src=client, ipv4_dst=VIP, ip_proto)
            → set_field(eth_dst=real_mac, ipv4_dst=real_ip), output toward backend

        SNAT (return):
            match(eth_src=backend_mac, eth_dst=client_mac,
                  ipv4_src=backend, ipv4_dst=client, ip_proto)
            → set_field(eth_src=VIP_mac, ipv4_src=VIP_ip), output to client port

        By default, transport ports are excluded so one steady-state VIP_DATA
        rule can cover concurrent connections from the same web server without
        tier-transition inconsistency. The recovery VIP path can optionally
        narrow both DNAT and SNAT rules to one TCP connection by passing
        tcp_src_port/tcp_dst_port and custom timeouts.
        """
        parser  = datapath.ofproto_parser
        ofproto = datapath.ofproto

        # Prefer get_next_hop_port for multi-switch topologies; fall back to
        # host_attachment for single-switch (backend directly connected here).
        is_cross_network = False
        backend_port = self.get_next_hop_port(datapath.id, client_mac, real_backend_mac)
        if backend_port is None:
            backend_loc = self.host_attachment.get(real_backend_mac)
            if backend_loc is not None:
                _, backend_port = backend_loc
            elif real_backend_mac in self.peer_hosts and _ROUTER_OVS_PORT > 0:
                backend_port = _ROUTER_OVS_PORT
                is_cross_network = True
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
        has_tcp_ports = (
            ip_proto == 6
            and tcp_src_port is not None
            and tcp_dst_port is not None
        )
        dnat_fields = {
            "eth_type": 0x0800,
            "eth_src": client_mac,
            "eth_dst": vip_mac,
            "ipv4_src": client_ip,
            "ipv4_dst": vip_ip,
            "ip_proto": ip_proto,
        }
        if has_tcp_ports:
            dnat_fields["tcp_src"] = tcp_src_port
            dnat_fields["tcp_dst"] = tcp_dst_port
        dnat_match = parser.OFPMatch(**dnat_fields)
        # Cross-network: the frame must be addressed to the router's LAN MAC so
        # the router's kernel IP stack accepts it for L3 forwarding.  Sending
        # eth_dst=real_backend_mac causes the router to silently drop the frame
        # (not destined for any of its own interfaces).
        dnat_eth_dst = (_ROUTER_MAC if is_cross_network and _ROUTER_MAC
                        else real_backend_mac)
        dnat_actions = [
            parser.OFPActionSetField(eth_dst=dnat_eth_dst),
            parser.OFPActionSetField(ipv4_dst=real_backend_ip),
            parser.OFPActionOutput(backend_port),
        ]
        self._install_flow(
            datapath, priority=200,
            match=dnat_match, actions=dnat_actions,
            idle_timeout=idle_timeout if idle_timeout is not None else _VIP_IDLE_TIMEOUT,
            hard_timeout=hard_timeout if hard_timeout is not None else _VIP_HARD_TIMEOUT,
        )

        # --- SNAT rule ---
        # eth_dst=client_mac + ipv4_dst=client_ip are critical: without them ALL
        # outgoing traffic from the backend (to any host) would get its source
        # rewritten to VIP_IP, breaking the backend's non-VIP connections.
        #
        # Cross-network: the router does L3 forwarding between LANs, which
        # rewrites eth_src to the router's own LAN MAC.  The return packet
        # arrives at this switch with eth_src=ROUTER_MAC, not the real backend
        # MAC.  We must match on the router MAC to intercept return traffic.
        if is_cross_network and _ROUTER_MAC:
            snat_eth_src = _ROUTER_MAC
            logger.debug(
                "snat: cross-network, matching router mac=%s instead of backend mac=%s",
                _ROUTER_MAC, real_backend_mac,
            )
        else:
            snat_eth_src = real_backend_mac
        snat_fields = {
            "eth_type": 0x0800,
            "eth_src": snat_eth_src,
            "eth_dst": client_mac,
            "ipv4_src": real_backend_ip,
            "ipv4_dst": client_ip,
            "ip_proto": ip_proto,
        }
        if has_tcp_ports:
            snat_fields["tcp_src"] = tcp_dst_port
            snat_fields["tcp_dst"] = tcp_src_port
        snat_match = parser.OFPMatch(**snat_fields)
        snat_actions = [
            parser.OFPActionSetField(eth_src=vip_mac),
            parser.OFPActionSetField(ipv4_src=vip_ip),
            parser.OFPActionOutput(in_port),
        ]
        self._install_flow(
            datapath, priority=200,
            match=snat_match, actions=snat_actions,
            idle_timeout=idle_timeout if idle_timeout is not None else _VIP_IDLE_TIMEOUT,
            hard_timeout=hard_timeout if hard_timeout is not None else _VIP_HARD_TIMEOUT,
        )

        logger.info(
            "dnat/snat installed: vip=%s -> real=%s (idle=%ds hard=%ds recovery_ports=%s)",
            vip_ip,
            real_backend_ip,
            idle_timeout if idle_timeout is not None else _VIP_IDLE_TIMEOUT,
            hard_timeout if hard_timeout is not None else _VIP_HARD_TIMEOUT,
            has_tcp_ports,
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

        for vip_ip, _, _, _ in self._iter_vip_bindings():
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

        for vip_ip, _, _, _ in self._iter_vip_bindings():
            match   = parser.OFPMatch(eth_type=0x0800, ipv4_dst=vip_ip)
            actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                              ofproto.OFPCML_NO_BUFFER)]
            self._install_flow(datapath, priority=100, match=match, actions=actions)

        logger.info("vip ip punt rules installed: dpid=%s", datapath.id)

    # ------------------------------------------------------------------
    # Telemetry integration — called from _on_telemetry_update (Thread 2)
    # ------------------------------------------------------------------

    def update_server_stats(self, servers: dict[str, ServerSummary]) -> None:
        """Store per-server telemetry stats, keyed by MAC.

        ``servers`` is keyed by the container's MAC address (each container
        discovers its own MAC from eth0 and includes it in telemetry events).
        Thread 1 reads _server_stats in select_server() for the WSM cost
        function.
        """
        for mac, summary in servers.items():
            self._server_stats[mac] = summary
            logger.debug(
                "server stats updated: mac=%s cpu=%.1f%% ram=%.1fMB req=%d",
                mac, summary.avg_cpu_percent,
                summary.avg_ram_used_mb, summary.request_count,
            )

    def update_storage_stats(self, storage_servers: dict[str, StorageServerSummary]) -> None:
        """Store per-storage telemetry stats, keyed by MAC.

        ``storage_servers`` is keyed by the container's MAC address.
        Thread 1 reads _storage_stats in select_storage() for the storage
        WSM cost function.
        """
        for mac, summary in storage_servers.items():
            self._storage_stats[mac] = summary
            logger.debug(
                "storage stats updated: mac=%s cpu=%.1f%% ram=%.1fMB conn=%.1f lag=%s",
                mac, summary.avg_cpu_percent,
                summary.avg_ram_used_mb, summary.avg_connections,
                summary.avg_repl_lag_s,
            )
