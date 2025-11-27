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
    type: EventType
    dpid: float
    src: str
    dst: str
    in_port: int
    createdAt: float
    ttl: int