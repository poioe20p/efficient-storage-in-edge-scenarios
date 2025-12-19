from dataclasses import dataclass
from typing import List, Any

@dataclass    
class Host:
    mac: str
    switch_dpid: str
    port_no: int

@dataclass
class Topology:
    id: str
    hosts: List[Host]
    links: List[Any]
    switchs: List[Any]
    ttl: float
    timestamp: str
    controller_name: str = None
