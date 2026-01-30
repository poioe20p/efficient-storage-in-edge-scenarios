from dataclasses import dataclass
from typing import Any, Dict, List, Optional
# from pydantic import BaseModel

@dataclass    
class Host:
    mac: str
    switch_dpid: str
    port_no: int

@dataclass
class Link:
    src_dpid: str
    src_port_no: int
    dst_dpid: str

@dataclass
class Topology:
    id: str
    hosts: List[Host]
    links: List[Link]
    switchs: List[Any]
    ttl: float
    timestamp: str
    controller_name: str = None
    # hop_map[host_mac][server_mac] = hop_count (int) or None
    hops: Optional[Dict[str, Dict[str, Optional[int]]]] = None
