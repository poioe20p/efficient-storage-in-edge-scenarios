"""DNAT/SNAT flow-rule construction and PacketOut for VIP routing."""

from .config import (
    _VIP_IDLE_TIMEOUT, _VIP_HARD_TIMEOUT,
    _VIP_DATA_IDLE_TIMEOUT,
    _VIP_DATA_PER_CONNECTION,
    _ROUTER_OVS_PORT, _ROUTER_MAC,
    ClientVipBinding,
    logger,
)
from ..scaling_config import _VIP_FLOW_ISOLATION, _VIP_SERVER_PER_CONNECTION


# Flow cookies for VIP_DATA forward rules, keyed by domain.
# All per-client forward rules for a domain share the same cookie, allowing
# bulk OFPFC_DELETE on unregister_storage_backend without tracking
# individual clients.
_COOKIE_VIP_DATA_FWD = {
    "n1": 0x56494441,  # 'VIDA' in hex
    "n2": 0x56494442,  # 'VIDB' in hex
}

# Conntrack zone for each VIP_DATA domain.
# Reply rules match on the same zone so they can set the correct VIP MAC.
_CT_ZONE = {"n1": 1, "n2": 2}

# Backend subnet for each domain — used to differentiate n1/n2 reply rules.
# n1 backends are always on LAN1 (10.0.0.0/24), n2 on LAN2 (10.0.1.0/24).
# This is a fixed topology property; no other LANs are expected.
_BACKEND_SUBNET = {"n1": "10.0.0.0/24", "n2": "10.0.1.0/24"}


def install_vip_data_forward_rule(
    controller, datapath,
    vip_ip, vip_mac, domain,
    client_mac, client_ip,
    backend_ip, backend_mac, backend_port,
    is_cross_network=False,
    client_src_port=None,
):
    """Install/update a per-client or per-connection forward rule for VIP_DATA.

    Default (client_src_port is None, ``VIP_DATA_PER_CONNECTION_FLOWS=0``):
    the match is scoped to one client (eth_src / ipv4_src), preserving the
    per-client WSM load distribution from the current static-NAT design.

    Per-connection (client_src_port is not None, ``VIP_DATA_PER_CONNECTION_FLOWS=1``):
    the match also carries ``tcp_src`` so a pooled edge client
    (``EDGE_MONGO_MAX_POOL_SIZE>1``) fans its connections out to different
    storage backends.  These flows are installed on the connection SYN only
    and expire on ``_VIP_DATA_IDLE_TIMEOUT`` idle (hard_timeout=0), so an
    established connection is NEVER re-pinned mid-stream while it is active
    (re-pinning would DNAT an already-committed conntrack connection to a new
    backend port and break it).  They are cleaned by the domain-cookie bulk
    delete on unregister_storage_backend.

    Uses ct(commit, nat(dst=backend_ip)) so OVS tracks each connection
    independently.  Multiple per-client/per-connection forward rules share
    the same domain cookie — bulk-deleted on unregister_storage_backend.

    Cross-network: when the backend is on the peer LAN, eth_dst must be
    the router's MAC so the router accepts the frame for L3 forwarding.
    """
    parser = datapath.ofproto_parser
    ofproto = datapath.ofproto

    per_connection = _VIP_DATA_PER_CONNECTION and client_src_port is not None

    if per_connection:
        match = parser.OFPMatch(
            eth_type=0x0800,
            eth_src=client_mac,
            eth_dst=vip_mac,
            ipv4_src=client_ip,
            ipv4_dst=vip_ip,
            ip_proto=6,           # TCP
            tcp_src=client_src_port,   # MongoDB client ephemeral port
            tcp_dst=27018,        # MongoDB
        )
    else:
        # Per-client match — preserves per-client WSM load distribution
        match = parser.OFPMatch(
            eth_type=0x0800,
            eth_src=client_mac,
            eth_dst=vip_mac,
            ipv4_src=client_ip,
            ipv4_dst=vip_ip,
            ip_proto=6,           # TCP
            tcp_dst=27018,        # MongoDB
        )

    # Destination MAC: router MAC for cross-network, backend MAC for local
    dnat_eth_dst = (_ROUTER_MAC if is_cross_network and _ROUTER_MAC
                    else backend_mac)

    # ct(commit, nat(dst=backend_ip))
    # zone_src=None means immediate value (not read from a register);
    # zone_ofs_nbits stores the zone number directly.
    ct_action = parser.NXActionCT(
        flags=1,                    # NX_CT_F_COMMIT
        zone_src=None,              # immediate zone value
        zone_ofs_nbits=_CT_ZONE[domain],  # zone number 1 (n1) or 2 (n2)
        recirc_table=ofproto.OFPTT_ALL,
        alg=0,
        actions=[
            parser.NXActionNAT(
                flags=2,            # 2 = NX_NAT_F_DST (destination NAT)
                range_ipv4_min=backend_ip,
                range_ipv4_max=backend_ip,
            ),
        ],
    )

    actions = [
        ct_action,
        parser.OFPActionSetField(eth_dst=dnat_eth_dst),
        parser.OFPActionOutput(backend_port),
    ]

    if per_connection:
        # Per-connection flows idle-expire like per-client ones (so a closed
        # connection's flow clears and its port can be re-pinned correctly),
        # but NEVER hard-expire: an active established connection must not be
        # forcibly re-pinned mid-stream.  On idle expiry, the next packet
        # packet-ins and the controller re-installs to the SAME backend via
        # the binding map (see ingress._handle_vip_data) — never a fresh
        # select.  Cleanup also happens via the domain-cookie bulk delete on
        # unregister_storage_backend.  Idle is env-driven (_VIP_DATA_IDLE_
        # TIMEOUT, raised from 10 s 2026-08-07) so a connection waiting on a
        # slow/queued backend is not dropped mid-request.
        idle_timeout = _VIP_DATA_IDLE_TIMEOUT
        hard_timeout = 0
    else:
        # NOTE: No delete-before-install.  When this client re-selects (e.g.
        # after idle timeout or backend unregister), the new rule has the same
        # match (eth_src + ipv4_src + VIP fields) and OVS overwrites the old
        # one automatically via the same-priority/same-match rule.
        idle_timeout = _VIP_DATA_IDLE_TIMEOUT
        hard_timeout = 120                         # unchanged

    controller._install_flow(
        datapath,
        priority=200,
        match=match,
        actions=actions,
        idle_timeout=idle_timeout,
        hard_timeout=hard_timeout,
        cookie=_COOKIE_VIP_DATA_FWD[domain],
    )

    mode = "per-connection" if per_connection else "per-client"
    logger.info(
        "vip_data(%s): %s forward rule installed — client=%s:%s vip=%s "
        "backend=%s (idle=%ss hard=%ss cookie=0x%x)",
        domain, mode, client_ip,
        client_src_port if per_connection else "*",
        vip_ip, backend_ip, idle_timeout, hard_timeout,
        _COOKIE_VIP_DATA_FWD[domain],
    )


def install_vip_data_reply_rule(
    controller, datapath,
    client_mac, client_ip, vip_mac, in_port, domain,
):
    """Install a reply rule for VIP_DATA traffic for one client+domain.

    The reply rule matches MongoDB reply packets (tcp_src=27018) addressed
    to the client and sends them through conntrack with ct(zone=N,nat) for
    automatic reverse NAT (backend IP → VIP IP).  After NAT, the source MAC
    is rewritten to the VIP MAC so the client sees the VIP as the source.

    The ipv4_src match on the backend subnet differentiates n1 (10.0.0.0/24)
    from n2 (10.0.1.0/24) so both reply rules can coexist for the same client
    without collision.  The ct(zone=N,nat) action then ensures the kernel looks
    up the connection in the correct conntrack zone.

    IMPORTANT: This rule does NOT match on ct_state because the reply packet
    has not been through ct() yet.  Instead, the ct(zone=N,nat) action in the
    pipeline processes the packet through conntrack, which applies reverse
    NAT and sets ct_state for the kernel's own state tracking.
    """
    parser = datapath.ofproto_parser
    ofproto = datapath.ofproto

    # Match MongoDB reply packets from this domain's backend subnet.
    # No ct_state match — the reply packet must go through ct() first,
    # and that is handled by the ct_action below.
    # ipv4_src on the backend subnet is the domain differentiator that
    # replaces the (broken) ct_zone match from the original design.
    match = parser.OFPMatch(
        eth_type=0x0800,
        eth_dst=client_mac,
        ipv4_src=_BACKEND_SUBNET[domain],  # domain differentiator (n1 vs n2)
        ipv4_dst=client_ip,
        ip_proto=6,
        tcp_src=27018,          # MongoDB reply packets
    )

    # ct(zone=N, nat) — triggers conntrack lookup and automatic reverse NAT.
    # flags=0 (no commit), no specific NAT direction (flags=0 on NXActionNAT
    # means "apply NAT from connection state").
    ct_action = parser.NXActionCT(
        flags=0,                    # no commit — connection already exists
        zone_src=None,              # immediate zone value
        zone_ofs_nbits=_CT_ZONE[domain],
        recirc_table=ofproto.OFPTT_ALL,  # continue with next action (no recirc)
        alg=0,
        actions=[
            parser.NXActionNAT(
                flags=0,            # automatic NAT (reverse of forward direction)
            ),
        ],
    )

    actions = [
        ct_action,
        parser.OFPActionSetField(eth_src=vip_mac),
        parser.OFPActionOutput(in_port),
    ]
    controller._install_flow(
        datapath,
        priority=200,
        match=match,
        actions=actions,
        idle_timeout=0,    # Never idle — conntrack manages lifecycle
        hard_timeout=0,    # Never expire
        cookie=0,          # No cookie needed — never deleted
    )


def _delete_flow_by_cookie(controller, datapath, cookie):
    """Delete all flows matching a specific cookie value."""
    parser = datapath.ofproto_parser
    ofproto = datapath.ofproto
    mod = parser.OFPFlowMod(
        datapath=datapath,
        cookie=cookie,
        cookie_mask=0xFFFFFFFFFFFFFFFF,
        table_id=ofproto.OFPTT_ALL,
        command=ofproto.OFPFC_DELETE,
        out_port=ofproto.OFPP_ANY,
        out_group=ofproto.OFPG_ANY,
        match=parser.OFPMatch(),  # wildcard — cookie is the filter
    )
    datapath.send_msg(mod)


def delete_vip_server_client_flows(controller, datapath, binding: ClientVipBinding):
    """Delete the exact VIP_SERVER DNAT+SNAT pair for one client+backend (RQ3).

    Uses the recorded binding for an EXACT match so it never matches the
    never-expiring ``VIP_DATA`` reply rule (``tcp_src=27018``) or another
    backend's ``VIP_SERVER`` SNAT rule. After deletion the priority-100 punt
    rule resumes → the next SYN triggers a fresh ``select_server()``.
    """
    parser = datapath.ofproto_parser
    ofproto = datapath.ofproto

    dnat_fields = {
        "eth_type": 0x0800,
        "eth_src": binding.client_mac,
        "eth_dst": binding.vip_mac,
        "ipv4_src": binding.client_ip,
        "ipv4_dst": binding.vip_ip,
        "ip_proto": 6,
    }
    snat_fields = {
        "eth_type": 0x0800,
        "eth_src": binding.snat_eth_src,
        "eth_dst": binding.client_mac,
        "ipv4_src": binding.backend_ip,
        "ipv4_dst": binding.client_ip,
        "ip_proto": 6,
    }
    # Per-connection binding (VIP_SERVER_PER_CONNECTION_FLOWS=1): delete the
    # exact connection pair (tcp_src on forward, tcp_dst on reply) so a
    # sibling connection's flow is never touched.
    if binding.client_port:
        dnat_fields["tcp_src"] = binding.client_port
        snat_fields["tcp_dst"] = binding.client_port
    dnat_match = parser.OFPMatch(**dnat_fields)
    snat_match = parser.OFPMatch(**snat_fields)
    for match in (dnat_match, snat_match):
        mod = parser.OFPFlowMod(
            datapath=datapath,
            table_id=ofproto.OFPTT_ALL,
            command=ofproto.OFPFC_DELETE,
            out_port=ofproto.OFPP_ANY,
            out_group=ofproto.OFPG_ANY,
            match=match,
        )
        datapath.send_msg(mod)
    logger.debug(
        "vip_server: flow delete issued — client=%s vip=%s backend=%s",
        binding.client_ip, binding.vip_ip, binding.backend_ip,
    )


def delete_vip_data_forward_rule(controller, datapath, domain):
    """Delete the forward rule for a VIP_DATA domain.

    After deletion, new SYNs to the VIP will be punted to the controller
    (priority-100 punt rule), triggering fresh select_storage().
    Established connections survive in conntrack state.

    Called from unregister_storage_backend via state.py.
    """
    _delete_flow_by_cookie(controller, datapath, _COOKIE_VIP_DATA_FWD[domain])
    logger.info(
        "vip_data(%s): forward rule deleted (cookie=0x%x)",
        domain, _COOKIE_VIP_DATA_FWD[domain],
    )


# ====================================================================
# Existing static DNAT+SNAT — kept for VIP_SERVER and backward compat
# ====================================================================


def install_vip_dnat_snat(
    controller, datapath, in_port, pkt, *,
    client_mac, client_ip, ip_proto, vip_ip, vip_mac,
    real_backend_ip, real_backend_mac,
    client_port=None, idle_timeout=None, hard_timeout=None,
) -> None:
    """Install a DNAT + SNAT flow rule pair and Packet-Out the first packet.

    DNAT (forward):
        match(eth_dst=VIP_MAC, ipv4_src=client, ipv4_dst=VIP, ip_proto)
        → set_field(eth_dst=real_mac, ipv4_dst=real_ip), output toward backend

    SNAT (return):
        match(eth_src=backend_mac, eth_dst=client_mac,
              ipv4_src=backend, ipv4_dst=client, ip_proto)
        → set_field(eth_src=VIP_mac, ipv4_src=VIP_ip), output to client port

    Transport ports are excluded in per-client mode so one steady-state
    rule can cover concurrent connections from the same client. When
    ``client_port`` is set (VIP_SERVER per-connection mode,
    ``VIP_SERVER_PER_CONNECTION_FLOWS=1``), the DNAT/SNAT pair is scoped to
    the client's ephemeral source port so each fresh request connection gets
    its own exact flow pair.
    """
    parser  = datapath.ofproto_parser
    ofproto = datapath.ofproto

    # Prefer get_next_hop_port for multi-switch topologies; fall back to
    # host_attachment for single-switch (backend directly connected here).
    is_cross_network = False
    backend_port = controller.get_next_hop_port(datapath.id, client_mac, real_backend_mac)
    if backend_port is None:
        backend_loc = controller.host_attachment.get(real_backend_mac)
        if backend_loc is not None:
            _, backend_port = backend_loc
        elif real_backend_mac in controller.peer_hosts and _ROUTER_OVS_PORT > 0:
            backend_port = _ROUTER_OVS_PORT
            is_cross_network = True
            logger.info(
                "dnat/snat: cross-network mac=%s -> router port %d",
                real_backend_mac, _ROUTER_OVS_PORT,
            )
        else:
            logger.warning(
                "dnat/snat: mac=%s not reachable from dpid=%s, skipping — "
                "requesting topology re-learn",
                real_backend_mac, datapath.id,
            )
            controller._topo_correction_needed = True
            return

    # --- DNAT rule ---
    # eth_dst=vip_mac: the client sends to VIP_MAC (from our ARP reply).
    # ipv4_src=client_ip: scopes the rule to this specific client so
    #   multiple simultaneous clients each select their own backend.
    dnat_fields = {
        "eth_type": 0x0800,
        "eth_src": client_mac,
        "eth_dst": vip_mac,
        "ipv4_src": client_ip,
        "ipv4_dst": vip_ip,
        "ip_proto": ip_proto,
    }
    # Per-connection mode: scope the DNAT to the client's ephemeral source
    # port so each fresh request connection gets its own flow pair (the
    # request_complete delete then targets exactly that connection, never a
    # sibling's flow).
    if _VIP_SERVER_PER_CONNECTION and client_port:
        dnat_fields["tcp_src"] = client_port
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
    controller._install_flow(
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
    # Per-connection mode: scope the SNAT (backend→client reply) to this
    # connection's client port (the reply's TCP dst).
    if _VIP_SERVER_PER_CONNECTION and client_port:
        snat_fields["tcp_dst"] = client_port
    snat_match = parser.OFPMatch(**snat_fields)
    snat_actions = [
        parser.OFPActionSetField(eth_src=vip_mac),
        parser.OFPActionSetField(ipv4_src=vip_ip),
        parser.OFPActionOutput(in_port),
    ]
    controller._install_flow(
        datapath, priority=200,
        match=snat_match, actions=snat_actions,
        idle_timeout=idle_timeout if idle_timeout is not None else _VIP_IDLE_TIMEOUT,
        hard_timeout=hard_timeout if hard_timeout is not None else _VIP_HARD_TIMEOUT,
    )

    # ── RQ3 flow isolation: record the client→backend binding ──
    # Active ONLY when VIP_FLOW_ISOLATION=1 (RQ3 arms). When off (default) this
    # block is skipped entirely → canonical/RQ1/RQ2 runs are byte-identical
    # (no _vip_server_client_map writes, no re-selection flow deletes).
    # On re-selection for a client that already has a binding, first delete the
    # old exact DNAT+SNAT pair (on every datapath) so the previous backend's
    # SNAT rule does not linger with a different match.
    if _VIP_FLOW_ISOLATION:
        # Per-connection mode keys the map by (client_mac, client_port) so
        # concurrent requests from one client are independent; per-client mode
        # keys by client_mac (the newest selection wins), preserving D5's
        # original design for runs without VIP_SERVER_PER_CONNECTION_FLOWS=1.
        _key = ((client_mac, client_port)
                if (_VIP_SERVER_PER_CONNECTION and client_port) else client_mac)
        with controller._warm_lock:
            old = controller._vip_server_client_map.get(_key)
            if old is not None and (old.backend_mac != real_backend_mac
                                    or old.vip_ip != vip_ip):
                try:
                    for _dp in controller.datapaths:
                        delete_vip_server_client_flows(controller, _dp, old)
                except Exception:
                    logger.exception(
                        "vip_server: failed to delete old binding for client=%s",
                        client_mac,
                    )
            controller._vip_server_client_map[_key] = ClientVipBinding(
                client_mac=client_mac,
                client_ip=client_ip,
                backend_mac=real_backend_mac,
                backend_ip=real_backend_ip,
                vip_ip=vip_ip,
                vip_mac=vip_mac,
                snat_eth_src=snat_eth_src,
                client_port=client_port or 0,
            )

    logger.info(
        "dnat/snat installed: vip=%s -> real=%s (idle=%ds hard=%ds)",
        vip_ip,
        real_backend_ip,
        idle_timeout if idle_timeout is not None else _VIP_IDLE_TIMEOUT,
        hard_timeout if hard_timeout is not None else _VIP_HARD_TIMEOUT,
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
