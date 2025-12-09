from dataclasses import dataclass
from typing import List, Any


@dataclass
class Host:
    mac: str
    switch_dpid: str
    port_no: int

@dataclass
class Switch:
    datapath: Any # object that represents the switch
    dpid: str # datapath ID of the switch which corresponding to the switch id

@dataclass
class Link:
    """
    Represents a link between two switches in the network topology.
    """
    src_dpid: str
    dst_dpid: str
    src_port_no: int
    dst_port_no: int

@dataclass
class Topology:
    switches: List[Switch]
    links: List[Link]
    hosts: List[Host]