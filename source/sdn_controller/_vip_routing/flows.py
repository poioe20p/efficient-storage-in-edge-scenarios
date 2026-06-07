"""DNAT/SNAT flow-rule construction and PacketOut for VIP routing."""

from .config import (
    _VIP_IDLE_TIMEOUT, _VIP_HARD_TIMEOUT,
    _ROUTER_OVS_PORT, _ROUTER_MAC,
    logger,
)


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
