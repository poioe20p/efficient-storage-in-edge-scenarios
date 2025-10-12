# Virtual topology overview

Derived from `network_layout.drawio`.

## Logical components

- `ovs-br0`: Open vSwitch bridge acting as the Layer‑2 core for the LAN segment.
- `container1`: Ubuntu host attached to `ovs-br0` via `veth1` (`eth0` inside the container) using IP `10.0.0.2/24`.
- `container2`: Ubuntu host attached to `ovs-br0` via `veth2` (`eth0` inside the container) using IP `10.0.0.3/24`.
- `mongodb`: Database container attached to `ovs-br0` via `veth5` (`eth0`) using IP `10.0.0.4/24`.
- `nat-router`: Router container with two interfaces:
  - LAN side `eth1` (`veth3-peer`) connected to `ovs-br0`, IP `10.0.0.1/24`.
  - WAN side `eth0` (`veth4-peer`) connected to the host, IP `192.168.100.2/24`.
- Host system: Provides the other end of `veth4` with IP `192.168.100.1/24` and performs NAT to the outside network.
- `ryu` controller: Runs on the host network (reachable at `127.0.0.1:6633`) and manages flow rules on `ovs-br0`.
- Internet uplink: Represents external connectivity beyond the NAT router.

## Interface and addressing summary

| Node          | Interface(s)                                 | IP / Notes               |
| ------------- | --------------------------------------------- | ------------------------ |
| `ovs-br0`     | Ports: `veth1`, `veth2`, `veth3`, `veth5`     | Central Open vSwitch     |
| `container1`  | `eth0` (`veth1-peer`)                         | `10.0.0.2/24`            |
| `container2`  | `eth0` (`veth2-peer`)                         | `10.0.0.3/24`            |
| `mongodb`     | `eth0` (`veth5-peer`)                         | `10.0.0.4/24`            |
| `nat-router`  | `eth1` (`veth3-peer`), `eth0` (`veth4-peer`)  | `10.0.0.1/24`, `192.168.100.2/24` |
| Host          | `veth4`                                       | `192.168.100.1/24`; runs NAT |
| `ryu`         | Host network                                  | Listens on `127.0.0.1:6633` |

## Link relationships

- `container1` ⇄ `ovs-br0` via the `veth1`/`veth1-peer` pair.
- `container2` ⇄ `ovs-br0` via the `veth2`/`veth2-peer` pair.
- `mongodb` ⇄ `ovs-br0` via the `veth5`/`veth5-peer` pair.
- `nat-router` LAN (`eth1`) ⇄ `ovs-br0` via `veth3`/`veth3-peer` (default gateway `10.0.0.1`).
- `nat-router` WAN (`eth0`) ⇄ host via `veth4`/`veth4-peer`, bridging to `192.168.100.0/24`.
- Host performs IP forwarding/NAT to reach the Internet, while the `ryu` controller programs `ovs-br0` over TCP `127.0.0.1:6633`.
