import dataclasses

@dataclasses
class Debit:
    switch_id: str
    port_n: int
    time_stamp: str
    mac_link: str
    total_