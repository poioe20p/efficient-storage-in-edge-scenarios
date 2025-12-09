from dataclasses import dataclass
from enum import Enum

class EventType(Enum):
    NODE_ADDED = "node_added"
    NODE_REMOVED = "node_removed"
    LINK_ADDED = "link_added"
    LINK_REMOVED = "link_removed"
    PACKET_IN = "packet_in"


@dataclass
class Event:
    dpid: float
    src: str
    dst: str
    in_port: int
    out_port: int
    created_ts: float
    ttl: float
    type: str
    datapath_id: str | None = None
    shard_zone: str | None = None