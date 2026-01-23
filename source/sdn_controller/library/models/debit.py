from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional


def _utc_now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


@dataclass
class DebitStats:
    @dataclass
    class SwitchPortStats:
        switch_id: str
        port_no: int
        flow_rate: float
        peer_mac: str
        neighbor_switch_id: Optional[str] = None
        ttl: int = 60 * 60  # 1 hour

    lan_id: str
    time_stamp: int = field(default_factory=_utc_now_ts)
    port: List[SwitchPortStats] = field(default_factory=list)
