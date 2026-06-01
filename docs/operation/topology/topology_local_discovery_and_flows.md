# Topology Local Discovery and Proactive Flows

## 1. Purpose

This document describes how the SDN controller discovers the local OpenFlow
network topology (switches, hosts, links), builds a hop-cache and graph model,
and installs proactive L2 forwarding flows for locally discovered hosts. It
covers the poll-loop mechanics, router filtering, switch reconnect handling,
and the boundary between proactive and reactive learning.

## 2. Current Files

- `source/sdn_controller/topology/topology.py` — `TopologyMixin` class containing
  the OS-Ken greenthread worker, discovery, hop-cache rebuild, and proactive
  flow installation logic.
- `source/sdn_controller/main_n1.py` (and `main_n2.py`) — entry-point applications
  that compose `TopologyMixin` with `VipRoutingMixin`. Also defines the shared
  `_install_flow()` helper and the reactive learning `packet_in_handler`.

## 3. OS-Ken Topology Service Dependency

The topology mixin requires the `os_ken.topology.switches` OS-Ken application:

- `TopologyMixin.REQUIRED_APP = ['os_ken.topology.switches']` declares the
  dependency at the class level.
- `main_n1.py` also declares `_REQUIRED_APP = ['os_ken.topology.switches']`
  at module scope because the OS-Ken app manager resolves dependencies from
  `sys.modules[cls.__module__]`, so it must be declared on the entry-point
  module explicitly.
- The lazy lookup is performed by `_get_topology_api_app()`, which calls
  `app_manager.lookup_service_brick('switches')`. If the service is not yet
  available it returns `None` (no error logged repeatedly after the first
  warning).

## 4. Local Discovery Poll Loop

The `_topology_worker()` greenthread runs every `_topology_interval` seconds
(default 1, from `TOPOLOGY_INTERVAL` env var). Each tick:

1. **`get_sws_links_hosts()`** — queries the OS-Ken topology API for the
   current set of switches, hosts, and links.
2. **`_rebuild_hop_cache()`** — recomputes shortest-path hop counts between
   all known hosts and configured backends.
3. **`_rebuild_vip_pools()`** — merges local and peer host maps and filters by
   MAC role sets (detailed in the *Backend Roles and VIP Pools* document).
4. **Change detection** — compares current `sws`, `links`, and `hosts` against
   the previous snapshot (`_sws_prev`, `_links_prev`, `_hosts_prev`).
5. **First-valid or changed** — if the topology has changed (or this is the
   first valid poll), calls `_install_local_topology_flows()` and records
   `_topology_initialized = True`.
6. **Publish decision** — if `first_valid`, `changed`, `_topo_correction_needed`,
   or heartbeat tick, calls `_publish_topology()` (detailed in the *Peer
   Exchange and Models* document).

## 5. Router Filtering

Hosts whose MAC address belongs to the built-in `_router_mac_blocklist` set
are excluded from local discovery. The blocklist is hardcoded in
`TopologyMixin.__init__`:

```python
self._router_mac_blocklist = {
    "00:00:00:00:00:aa", "00:00:00:00:00:bb",
    "00:00:00:00:00:cc", "00:00:00:00:00:dd",
    "00:00:00:00:00:AA", "00:00:00:00:00:BB",
    "00:00:00:00:00:CC", "00:00:00:00:00:DD",
}
```

The filtering is applied in `get_sws_links_hosts()`:

```python
self.hosts = [
    (host.mac, host.port.dpid, host.port.port_no)
    for host in host_list
    if getattr(host, "port", None) is not None
    and host.mac not in self._router_mac_blocklist
]
```

This prevents router MACs from appearing in host-attachment maps, VIP pools,
or hop-cache computations.

## 6. Host Attachment and Graph Build

After filtering, `get_sws_links_hosts()` builds two data structures:

- **`host_attachment`** — a `dict[str, (int, int)]` mapping each host MAC to
  its `(dpid, port_no)` tuple. This is the primary lookup for the edge switch
  and port of any discovered host.
- **NetworkX `DiGraph` (`self.net`)** — constructed with edges for host–switch
  and switch–switch connections:
  - Host → switch edges: `(host_mac, dpid)` with `port=1` (host side) and
    `(dpid, host_mac)` with `port=host.port.port_no` (switch side).
  - Switch → switch edges: `(src_dpid, dst_dpid)` with `port=link.src.port_no`
    (from `get_all_link()`).

The graph is cleared and rebuilt on every poll cycle.

## 7. Hop Cache and Average Hop Count

`_rebuild_hop_cache()` runs after every topology poll:

1. Computes the union of configured backend MACs
   (`_server_macs | _storage_macs_n1 | _storage_macs_n2`) intersected with
   locally attached hosts.
2. For every host MAC, computes `nx.shortest_path(self.net, host_mac, backend_mac)`
   for each backend in the intersected set. The hop count is
   `max(len(path) - 1, 0)`.
3. Stores results in `self.hop_cache[src_mac][dst_mac]` (or `None` for
   unreachable pairs).
4. Tracks the global maximum hop count in `_hop_cache_max` (used for WSM
   hop-count normalization).
5. Computes `_avg_hop_count` as the arithmetic mean of all resolved hop
   distances. This value is published in topology snapshots so the peer
   controller can use it as `_peer_avg_hop_count` for its cross-network
   hop penalty estimate.

## 8. Switch Reconnect Handling

When a switch connects or disconnects, `_state_change_handler(ev)` is triggered
via the OS-Ken event framework (`@set_ev_cls(EventOFPStateChange, ...)`):

### On `MAIN_DISPATCHER` (reconnect):

1. **Flush all stale flows** — sends an `OFPFC_DELETE` with a wildcard match,
   removing every flow entry on the switch. This prevents stale rules from a
   previous controller run from suppressing `PacketIn` events needed for host
   re-discovery.
2. **Reinstall table-miss** — installs a priority-0 flow that sends unmatched
   packets to the controller (`OFPP_CONTROLLER, 65535`).
3. **Notify mixins** — calls `_on_datapath_connected(datapath)`, which is a
   hook that higher-order mixins (e.g. `VipRoutingMixin`) override to reinstall
   their own rules (e.g. VIP DNAT rules at priority 100/200).
4. **Update switch list** — appends `(datapath, datapath.id)` to `self.sws`
   and `self._datapath_by_id` if not already present.

### On `DEAD_DISPATCHER` (disconnect):

Removes the switch from `self.sws` and `self._datapath_by_id`.

The default `_on_datapath_connected()` in `TopologyMixin` is a no-op — it is
the subclass's responsibility to override it for custom rule installation.

## 9. Proactive Flow Installation

Proactive flows are installed when the topology changes (or on first valid
poll) via `_install_local_topology_flows()`, which clears the deduplication
set and calls `send_all_flow_rules_proactively()`.

### Scope — Local Hosts Only

Proactive flows are installed **only for local host pairs** discovered in
`self.hosts`. Peer-discovered hosts (from `peer_hosts`) are not included.
This is because the local controller does not have topological certainty about
the peer network's internal paths.

### Installation Path

1. **`send_all_flow_rules_proactively()`** — iterates over all unique pairs of
   local hosts. For each pair, calls `nx.shortest_path(self.net, host1[0], host2[0])`
   to compute the path through the network graph.
2. **`_install_path_flows(path)`** — for each node in the path, looks up the
   datapath in `_datapath_by_id` and calls `proactive_flow_rule_install()`.
3. **`proactive_flow_rule_install(sw, path)`** — installs a bidirectional
   pair of flows:
   - Forward: match `in_port, eth_dst=dst_mac, eth_src=src_mac` → output
     `out_port` (priority 5).
   - Reverse: match `in_port=out_port, eth_dst=src_mac, eth_src=dst_mac` →
     output `in_port` (priority 5).
4. **ARP flood rule** — on each switch, a single priority-1 rule is installed
   to flood ARP packets (`eth_type=0x0806` → `OFPP_FLOOD`). This is done once
   per switch (tracked by `_arp_rules_installed`).
5. **Deduplication** — `_installed_flow_keys` set stores `(dpid, src_mac, dst_mac)`
   tuples to prevent reinstalling identical rules on repeated topology ticks.

### Flow Priority Summary

| Priority | Rule | Installed by |
|---|---|---|
| 0 | Table-miss → controller | `_state_change_handler` |
| 1 | ARP flood | `proactive_flow_rule_install` |
| 5 | Proactive L2 forwarding | `proactive_flow_rule_install` |
| 10 | Reactive L2 learning | `main_n*.py` (`packet_in_handler`) |

Higher-priority rules (100, 200) are installed by `VipRoutingMixin` for VIP
DNAT and load balancing.

## 10. Reactive Learning Boundary

When a packet arrives at the controller that was not handled by a proactive
flow (e.g. a new flow not yet installed, or traffic involving an unknown
destination), the `packet_in_handler` in `main_n*.py` provides reactive L2
learning:

1. Learns the source MAC → port mapping in `mac_to_port[dpid]`.
2. If the destination MAC is known, installs a priority-10 flow
   (`in_port, eth_dst, eth_src`) with `OFPFF_SEND_FLOW_REM` flag.
3. If the destination is unknown, floods the packet.

Reactive learning is **disabled** when `self.enable_reactive_learning = False`
(used in some experiment configurations). VIP-destined packets are intercepted
before the L2 learning path via `self.handle_vip_packet_in()` — if handled,
the method returns `True` and the reactive path is skipped for that packet.
