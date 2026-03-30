# MAC→IP Seeding Fix Plan

## Overview

After the full network build, VIP routing fails with `"IP unknown for mac=XX — awaiting ARP from backend"` for all backend servers. The controller's `_mac_to_ip` dict is empty because ARP snooping never fires for any host. This plan identifies the three root causes and their fixes.

**Prerequisite:** Step 8.2 in `build_network_setup.sh` (static OVS VIP ARP reply flows at priority=200) was already removed — those flows overrode the controller's punt rules at priority=100, preventing ARP packets from ever reaching the controller.

---

## Root Causes

### RC-1: `arping` not installed in containers

The ARP bootstrap in `test_conectivity.sh` used `arping -c 1 -w 2 -I eth0 <target>` to force ARP requests from each container. However, the Dockerfiles for `edge_server`, `edge_storage_server`, and `local_state_server` only install `iputils-ping` — **not** `iputils-arping`. The command silently fails (stderr suppressed by `2>/dev/null`), so no ARP is ever sent.

### RC-2: Warm ARP caches suppress fresh ARPs

Containers communicate before the controller connects (e.g., connecting to MongoDB on startup). This warms the ARP caches. Even if `arping` were available, a subsequent `ping` to the same host would not generate a new ARP request — the cached entry is used instead. The controller never sees ARP traffic and can't snoop MAC→IP.

### RC-3: Peer hosts have no IP in topology sharing

`TopologyHostEntry` only carried `mac`, `dpid`, `port_no` — no IP field. When the LAN1 controller receives topology from LAN2, it learns *where* peer hosts are attached (MAC + switch port), but **not** their IP addresses. Since ARP snooping only captures local ARP traffic, `_mac_to_ip` can never be populated for cross-network hosts. VIP routing always fails when selecting a peer server.

---

## Fixes

### Fix 1: Replace `arping` with ARP flush + ping (RC-1 + RC-2)

**File:** `source/scripts/test_conectivity.sh`

Renamed `arping_from_container()` → `arp_ping_from_container()` with the following logic:

1. `docker exec "$source" ip neigh flush to "$target"` — flush the ARP cache entry for the target IP (both `ip` and `ping` are available in all containers)
2. `docker exec "$source" ping -c 1 -W 2 "$target"` — send a single ping, which forces a fresh ARP request on the wire

The SDN controller's table-miss rule (priority=0) punts the ARP to the controller, where `snoop_arp()` records the sender's MAC→IP mapping.

This fixes both RC-1 (no dependency on `arping`) and RC-2 (flush guarantees a fresh ARP regardless of cache state).

### Fix 2: Add IP field to topology model (RC-3)

**File:** `source/sdn_controller/models.py`

Added `ip: str | None = None` to `TopologyHostEntry`. The field is optional and defaults to `None` so existing topology messages without IP remain backward-compatible.

```python
class TopologyHostEntry(BaseModel):
    mac: str
    dpid: int
    port_no: int
    ip: str | None = None
```

### Fix 3: Include IP in published topology snapshots (RC-3)

**File:** `source/sdn_controller/topology.py` — `_publish_topology()`

When building the local network section, each `TopologyHostEntry` now includes `ip=self._mac_to_ip.get(mac)`. This means that once the local controller has snooped a host's MAC→IP (via Fix 1's bootstrap), that IP is included in outgoing topology snapshots to the peer controller.

```python
TopologyHostEntry(mac=mac, dpid=dpid, port_no=port_no, ip=self._mac_to_ip.get(mac))
```

### Fix 4: Seed peer IPs on topology update (RC-3)

**File:** `source/sdn_controller/topology.py` — `on_topology_update()`

After receiving and storing peer hosts, the method now iterates over all peer host entries and calls `self.register_backend_ip(mac, ip)` for each host that carries an IP. This seeds `_mac_to_ip` on the receiving controller so VIP routing can immediately resolve peer server/storage MACs to their IPs.

```python
for h in self.peer_hosts.values():
    ip = h.get("ip")
    if ip:
        self.register_backend_ip(h["mac"], ip)
```

---

## Data Flow After Fix

```
1. Controllers start, connect to OVS switches
2. build_network_setup.sh step 9 runs: test_conectivity.sh all
3. test_conectivity.sh runs ARP bootstrap:
   └─ For each container × VIP combination:
      ├─ ip neigh flush to <VIP>     (clear stale ARP cache)
      └─ ping -c 1 <VIP>            (triggers ARP request on wire)
         └─ OVS table-miss → PacketIn → controller
            └─ snoop_arp(): _mac_to_ip[sender_mac] = sender_ip

4. Controller's _mac_to_ip now populated for all LOCAL hosts
5. Next _publish_topology() includes IP in TopologyHostEntry
   └─ ZMQ PUB → peer controller receives snapshot
      └─ on_topology_update():
         ├─ peer_hosts stored with IP
         └─ register_backend_ip(mac, ip) for each peer host
            └─ _mac_to_ip now populated for PEER hosts too

6. VIP routing resolves both local and peer server MACs to IPs ✅
```

---

## Files Changed

| File | Change |
|------|--------|
| `source/scripts/test_conectivity.sh` | Replaced `arping_from_container()` → `arp_ping_from_container()` using flush + ping |
| `source/sdn_controller/models.py` | Added `ip: str \| None = None` to `TopologyHostEntry` |
| `source/sdn_controller/topology.py` | `_publish_topology()`: include IP from `_mac_to_ip` in host entries |
| `source/sdn_controller/topology.py` | `on_topology_update()`: call `register_backend_ip()` for peer hosts with IP |

---

## Timing Dependency

The ARP bootstrap **must** run after the controller is connected to OVS and has installed its table-miss rule. The existing `build_network_setup.sh` sequence already ensures this:

1. Step 8: Start controllers
2. Step 8.1: Point OVS to controllers
3. `wait_for_controller_connected` + `sleep 5`
4. Step 9: `test_conectivity.sh all` (runs ARP bootstrap first)

However, the first topology publish may occur before the ARP bootstrap completes. Peer IP seeding will happen on the **next** topology publish cycle (within `TOPOLOGY_INTERVAL` seconds, default 1s) after the bootstrap finishes. This is acceptable — VIP routing naturally retries on the next packet-in.
