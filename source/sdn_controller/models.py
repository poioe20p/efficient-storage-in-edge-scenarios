from __future__ import annotations

from pydantic import BaseModel


class TopologyHostEntry(BaseModel):
    mac: str
    dpid: int
    port_no: int


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
