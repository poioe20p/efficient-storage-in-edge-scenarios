from __future__ import annotations

from pydantic import BaseModel


class TopologyHostEntry(BaseModel):
    mac: str
    dpid: int
    port_no: int
    ip: str | None = None


class TopologyLinkEntry(BaseModel):
    src_dpid: int
    src_port_no: int
    dst_dpid: int


class TopologyNetworkSection(BaseModel):
    hosts: list[TopologyHostEntry] = []
    links: list[TopologyLinkEntry] = []
    switches: list[int] = []


class TopologySnapshot(BaseModel):
    type: str = "topology"
    network_id: str
    networks: dict[str, TopologyNetworkSection] = {}
    hosts: list[TopologyHostEntry] = []
    links: list[TopologyLinkEntry] = []
    switches: list[int] = []
    hops: dict = {}
    ts: float = 0.0
    avg_hop_count: float = 0.0
    # MAC role sets — advertised by sender so peer can merge them into its own pools
    server_macs:     list[str] = []
    storage_macs_n1: list[str] = []
    storage_macs_n2: list[str] = []
    # MAC → RS role ("primary" / "secondary" / "") for the publishing LAN's
    # own storage nodes. Consumed by ``resolve_peer_primary`` on the receiver
    # so a consumer controller can look up the peer LAN's primary IP for
    # Tier 1 Change Stream cursors (see Stage 2 in
    # ``docs/operation/elasticy_manager/implementation/tier1_selective_sync/``).
    # Selective-sync containers carry ``member_state="STANDALONE_CACHE"`` on
    # the telemetry side and are mapped to ``""`` here — they must never be
    # advertised as RS members.
    storage_roles:   dict[str, str] = {}
