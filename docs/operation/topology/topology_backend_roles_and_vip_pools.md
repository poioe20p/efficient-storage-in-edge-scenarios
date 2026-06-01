# Topology Backend Roles and VIP Pools

## 1. Purpose

This document describes how the SDN controller manages VIP addresses, classifies
backend containers into MAC-based role sets (server, storage LAN 1, storage
LAN 2), dynamically registers new containers, rebuilds VIP forwarding pools
from reachable backends, and tracks storage replica-set roles. It also documents
the `resolve_peer_primary()` contract used by the Tier 1 selective-sync
subsystem.

## 2. Current Files

- `source/sdn_controller/topology/topology.py` — `TopologyMixin` class containing
  all VIP address configuration, MAC role set management, dynamic registration
  methods, VIP pool rebuild logic, storage role tracking, and the
  `resolve_peer_primary()` lookup.

## 3. VIP Address Set

The topology mixin defines five virtual IP addresses, configured via environment
variables with hardcoded defaults:

| VIP | Env Vars (IP / MAC) | Default IP | Default MAC | Purpose |
|---|---|---|---|---|
| **VIP_SERVER** | `VIP_SERVER_IP`, `VIP_SERVER_MAC` | `10.0.0.253` | `aa:bb:cc:dd:ee:01` | HTTP edge servers (shared across domains) |
| **VIP_DATA_N1** | `VIP_DATA_N1_IP`, `VIP_DATA_N1_MAC` | `10.0.0.254` | `aa:bb:cc:dd:ee:02` | MongoDB storage on LAN 1 |
| **VIP_DATA_N2** | `VIP_DATA_N2_IP`, `VIP_DATA_N2_MAC` | `10.0.1.254` | `aa:bb:cc:dd:ee:03` | MongoDB storage on LAN 2 |
| **VIP_DATA_RECOVERY_N1** | `VIP_DATA_RECOVERY_N1_IP`, `VIP_DATA_RECOVERY_N1_MAC` | `10.0.0.252` | `aa:bb:cc:dd:ee:12` | Recovery MongoDB storage on LAN 1 |
| **VIP_DATA_RECOVERY_N2** | `VIP_DATA_RECOVERY_N2_IP`, `VIP_DATA_RECOVERY_N2_MAC` | `10.0.1.252` | `aa:bb:cc:dd:ee:13` | Recovery MongoDB storage on LAN 2 |

VIP_DATA is per-domain: edge servers on LAN 1 connect to `VIP_DATA_N1` to reach
LAN 1's MongoDB replica set, and to `VIP_DATA_N2` to reach LAN 2's. The recovery
VIPs provide dedicated endpoints for recovery-mode storage access.

## 4. Local and Peer MAC Role Sets

Backends are classified into roles by MAC address. Each role is maintained as a
pair of sets — local (seeded from env vars or registered dynamically) and peer
(replaced wholesale from incoming topology snapshots):

| Property | Local set | Peer set | Purpose |
|---|---|---|---|
| `_server_macs` | `_local_server_macs` | `_peer_server_macs` | HTTP edge server containers |
| `_storage_macs_n1` | `_local_storage_macs_n1` | `_peer_storage_macs_n1` | MongoDB storage containers (LAN 1) |
| `_storage_macs_n2` | `_local_storage_macs_n2` | `_peer_storage_macs_n2` | MongoDB storage containers (LAN 2) |

### Seeding

Local MAC sets are seeded at startup from environment variables:

- `SERVER_MACS` — comma-separated MACs for HTTP backends.
- `STORAGE_MACS_N1` — comma-separated MACs for LAN 1 storage.
- `STORAGE_MACS_N2` — comma-separated MACs for LAN 2 storage.

### Union Properties

Each role exposes a `@property` that returns the union of the local and peer
sets:

```python
@property
def _server_macs(self) -> set[str]:
    return self._local_server_macs | self._peer_server_macs

@property
def _storage_macs_n1(self) -> set[str]:
    return self._local_storage_macs_n1 | self._peer_storage_macs_n1

@property
def _storage_macs_n2(self) -> set[str]:
    return self._local_storage_macs_n2 | self._peer_storage_macs_n2
```

These union properties are used by `_rebuild_vip_pools()` and
`_rebuild_hop_cache()` to consider all known backends regardless of origin.

### Peer MAC Merge

When `on_topology_update()` receives a `TopologySnapshot` from the peer
controller, it performs a **wholesale replacement** of the peer MAC sets:

```python
self._peer_server_macs     = set(snapshot.server_macs)
self._peer_storage_macs_n1 = set(snapshot.storage_macs_n1)
self._peer_storage_macs_n2 = set(snapshot.storage_macs_n2)
```

This ensures that removals (e.g. a container scaled down on the peer) are
correctly reflected — incremental add/remove would leak stale entries.

## 5. Dynamic Backend Registration

The elasticity manager (running in a separate thread) calls the following
methods after spawning or removing containers:

| Method | Signature | Description |
|---|---|---|
| `add_server_mac(mac)` | `(str) -> None` | Registers a new HTTP server MAC in the local set and triggers `_rebuild_hop_cache()`. |
| `remove_server_mac(mac)` | `(str) -> None` | Removes an HTTP server MAC from the local set and triggers `_rebuild_hop_cache()`. |
| `add_storage_mac(mac, domain="n1")` | `(str, str) -> None` | Registers a storage MAC in the appropriate LAN set (default `n1`, use `"n2"` for LAN 2) and triggers `_rebuild_hop_cache()`. |
| `remove_storage_mac(mac, domain="n1")` | `(str, str) -> None` | Removes a storage MAC from the appropriate LAN set and triggers `_rebuild_hop_cache()`. |

All changes propagate automatically via the next topology publish cycle.

## 6. VIP Pool Rebuild Rules

`_rebuild_vip_pools()` is called on every topology tick, after the hop cache
has been rebuilt. It constructs the forwarding pools used by `VipRoutingMixin`:

```python
def _rebuild_vip_pools(self) -> None:
    combined: dict[str, dict] = {
        mac: {"mac": mac, "dpid": dpid, "port_no": port_no}
        for mac, (dpid, port_no) in self.host_attachment.items()
    }
    combined |= self.peer_hosts   # dict union — local wins on overlap

    self.vip_server_pool     = {mac: combined[mac] for mac in self._server_macs     if mac in combined}
    self.vip_storage_pool_n1 = {mac: combined[mac] for mac in self._storage_macs_n1 if mac in combined}
    self.vip_storage_pool_n2 = {mac: combined[mac] for mac in self._storage_macs_n2 if mac in combined}
```

### Rules

1. **Local-first merge** — `host_attachment` (locally discovered hosts) is the
   base; `peer_hosts` (from the peer controller's snapshot) are merged in via
   `|=` dict union. Local entries take precedence if the same MAC appears in
   both.
2. **MAC role filter** — only backends whose MAC appears in the corresponding
   role set (`_server_macs`, `_storage_macs_n1`, `_storage_macs_n2`) are
   included.
3. **Reachability gate** — only hosts that are **both** configured (via MAC
   role) **and** topologically reachable (present in the merged host map)
   appear in the pool.
4. **Each pool entry** contains `{"mac": ..., "dpid": ..., "port_no": ...}`,
   used by VIP routing to build DNAT actions.

## 7. Storage Role Tracking

`TopologySnapshot` carries a `storage_roles: dict[str, str]` map from MAC to
replica-set role — one of `"primary"`, `"secondary"`, or `""` (unknown or not
an RS member). This is used by the Tier 1 selective-sync subsystem to discover
the peer RS primary endpoint.

### Population — Local Side

Each controller calls `sync_storage_roles(summary.storage_servers)` from
`_on_telemetry_update` after every telemetry window. It rebuilds the local
roles dict fresh from `TelemetrySummary.storage_servers[*].member_state`:

| `member_state` | `storage_roles` value |
|---|---|
| `"PRIMARY"` | `"primary"` |
| `"SECONDARY"` | `"secondary"` |
| anything else (including `"STANDALONE_CACHE"`) | `""` |

Key design points:

- **Fresh rebuild each window** — RS re-elections mean the primary MAC can
  change between windows. Merging would keep a stale `"primary"` entry alive.
  Fresh rebuilds cost `O(members_in_lan)` and correctly reflect the latest
  telemetry snapshot.
- **Selective-sync containers** — carry `member_state="STANDALONE_CACHE"` on
  the telemetry side and are mapped to `""`. They must **never** be advertised
  as RS members.
- **Stale entry cleanup** — `sync_storage_roles` clears the entire
  `_local_storage_roles` dict before repopulating, so any MAC that disappeared
  from telemetry (scale-down, container removal) is automatically forgotten.

### Population — Peer Side

`on_topology_update()` copies the peer snapshot's `storage_roles` into
`self._peer_storage_roles` wholesale (same replacement rule as MAC sets).

### Individual Methods

| Method | Description |
|---|---|
| `update_storage_role(mac, member_state)` | Maps a single telemetry `member_state` to a role string and stores it in `_local_storage_roles`. |
| `sync_storage_roles(storage_servers)` | Rebuilds `_local_storage_roles` from a `TelemetrySummary.storage_servers` dict. Clears stale entries, then calls `update_storage_role` for each live entry. |
| `forget_storage_role(mac)` | Removes a single MAC from `_local_storage_roles` (called on node removal). |

## 8. Peer Primary Resolution Contract

```python
def resolve_peer_primary(self, peer_network_id: str) -> tuple[str, str] | None
```

Returns `(rs_name, "ip:27018")` for the peer LAN's current replica-set primary,
or `None` if no primary is known.

### Lookup Logic

1. Extracts the LAN number `n` from `peer_network_id` (e.g. `"lan1"` → `"1"`).
2. Selects the peer storage MAC set for that LAN
   (`_peer_storage_macs_n1` if `n == "1"`, else `_peer_storage_macs_n2`).
3. Iterates the MAC set looking for a MAC whose `_peer_storage_roles` value is
   `"primary"`.
4. Resolves the MAC to an IP via `self.peer_hosts` (which was seeded during
   `on_topology_update`).
5. Returns `(f"rs_net{n}", f"{ip}:27018")` if found, otherwise `None`.

### Contract Notes

- The port is **`27018`** (the `mongod` shard-port default in the testbed),
  not the standard `27017`. The coordinator uses this value directly when
  building the remote Change Stream URI.
- The caller (`PromotionCoordinator` in Tier 1 selective sync) handles `None`
  by deferring promotion for one telemetry window.

## 9. Short Tier 1 Reference

The `storage_roles` map and `resolve_peer_primary()` together form the contract
that the Tier 1 selective-sync subsystem consumes to discover the peer LAN's
RS primary endpoint. The `PromotionCoordinator` calls
`resolve_peer_primary(owner_lan)` through a thin wrapper in `main_n*.py` to
build the remote Change Stream URI before spawning an `edge_selective_storage`
container.

For the full selective-sync lifecycle, policy triggers, and `PromotionCoordinator`
design, see the [Selective Sync Overview](../selective_sync/selective_sync_overview.md).
