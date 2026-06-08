"""DNAT/SNAT flow-rule construction and PacketOut for VIP routing."""

from .config import (
    _VIP_IDLE_TIMEOUT, _VIP_HARD_TIMEOUT,
    _ROUTER_OVS_PORT, _ROUTER_MAC,
    logger,
)


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


def install_vip_data_forward_rule(
    controller, datapath,
    vip_ip, vip_mac, domain,
    client_mac, client_ip,
    backend_ip, backend_mac, backend_port,
    is_cross_network=False,
):
    """Install/update a per-client forward rule for a VIP_DATA domain.

    The match is scoped to one client (eth_src / ipv4_src), preserving the
    per-client WSM load distribution from the current static-NAT design.

    Uses ct(commit, nat(dst=backend_ip)) so OVS tracks each connection
    independently.  Multiple per-client forward rules share the same
    domain cookie — they can be bulk-deleted on unregister_storage_backend.

    Cross-network: when the backend is on the peer LAN, eth_dst must be
    the router's MAC so the router accepts the frame for L3 forwarding.
    """
    parser = datapath.ofproto_parser
    ofproto = datapath.ofproto

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
                flags=0,            # 0 = DNAT
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

    # NOTE: No delete-before-install.  When this client re-selects (e.g.
    # after idle timeout or backend unregister), the new rule has the same
    # match (eth_src + ipv4_src + VIP fields) and OVS overwrites the old
    # one automatically via the same-priority/same-match rule.
    controller._install_flow(
        datapath,
        priority=200,
        match=match,
        actions=actions,
        idle_timeout=10,                          # 10s (down from 30s)
        hard_timeout=120,                         # unchanged
        cookie=_COOKIE_VIP_DATA_FWD[domain],
    )

    logger.info(
        "vip_data(%s): per-client forward rule installed — client=%s vip=%s "
        "backend=%s (idle=10s hard=120s cookie=0x%x)",
        domain, client_ip, vip_ip, backend_ip, _COOKIE_VIP_DATA_FWD[domain],
    )


def install_vip_data_reply_rule(
    controller, datapath,
    client_mac, client_ip, vip_mac, in_port, domain,
):
    """Install a reply rule for VIP_DATA traffic for one client+domain.

    The reply rule matches packets belonging to established connections
    (already in conntrack) and rewrites their source to the domain's VIP MAC.
    The IP NAT reversal is handled automatically by conntrack's ct(nat).

    ct_zone scoping ensures n1 and n2 reply rules have different matches
    and can coexist for the same client without collision.
    """
    parser = datapath.ofproto_parser
    ofproto = datapath.ofproto

    # Match established+tracked connections in the domain's conntrack zone.
    # ct_state=(3, 3) => bits 0 (tracked) and 1 (established) both set.
    match = parser.OFPMatch(
        ct_state=(3, 3),
        ct_zone=_CT_ZONE[domain],
        eth_type=0x0800,
        eth_dst=client_mac,
        ipv4_dst=client_ip,
        ip_proto=6,
    )
    actions = [
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
    idle_timeout=None, hard_timeout=None,
) -> None:
    """Install a DNAT + SNAT flow rule pair and Packet-Out the first packet.

    DNAT (forward):
        match(eth_dst=VIP_MAC, ipv4_src=client, ipv4_dst=VIP, ip_proto)
        → set_field(eth_dst=real_mac, ipv4_dst=real_ip), output toward backend

    SNAT (return):
        match(eth_src=backend_mac, eth_dst=client_mac,
              ipv4_src=backend, ipv4_dst=client, ip_proto)
        → set_field(eth_src=VIP_mac, ipv4_src=VIP_ip), output to client port

    Transport ports are excluded so one steady-state VIP_DATA
    rule can cover concurrent connections from the same web server without
    tier-transition inconsistency.
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
                "dnat/snat: mac=%s not reachable from dpid=%s, skipping",
                real_backend_mac, datapath.id,
            )
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
