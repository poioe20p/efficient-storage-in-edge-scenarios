# Peer MAC Role Sharing Implementation Plan

## Overview

Each SDN controller currently knows only its own server and storage MACs (set via environment variables at startup). As a result, `vip_server_pool` only ever contains the local controller's server — it never includes servers from the peer network, even though the peer topology (host locations) is already shared via ZMQ.

This plan:

1. Fixes an env-var format bug (`container_name:MAC` → plain `MAC`) that prevents any VIP pools from populating.
2. Adds `server_macs`, `storage_macs_n1`, `storage_macs_n2` to the `TopologySnapshot` model so each controller can advertise which MACs it has registered as backends.
3. Merges incoming peer MAC roles into the local controller's effective sets so `vip_server_pool` spans both networks.
4. Ensures dynamically-added nodes (via `add_server_mac` / `add_storage_mac` from `elasticity.py`) are propagated to the peer on the next topology publish cycle.

---

## Architecture (after change)

```
osken (LAN1)                             osken_2 (LAN2)
─────────────────────────────────────    ─────────────────────────────────────
_local_server_macs = {00:00:00:00:00:02} _local_server_macs = {00:00:00:00:00:05}
_peer_server_macs  = {}                  _peer_server_macs  = {}
                    ↕ ZMQ topology exchange
After first exchange:
_peer_server_macs  = {00:00:00:00:00:05} _peer_server_macs  = {00:00:00:00:00:02}

_server_macs (property) = _local | _peer  (both servers visible to each controller)

_rebuild_vip_pools() uses _server_macs → vip_server_pool contains both servers
```

Dynamic node addition:

```
elasticity.py calls add_server_mac(new_mac)
  → added to _local_server_macs
  → next _publish_topology() includes new_mac in snapshot.server_macs
  → peer receives snapshot → replaces _peer_server_macs → now includes new_mac
  → peer's vip_server_pool updated on next tick
```

---

## Files to Change

| File                                      | Action | Purpose                                                                                      |
| ----------------------------------------- | ------ | -------------------------------------------------------------------------------------------- |
| `source/sdn_controller/models.py`       | Modify | Add `server_macs`, `storage_macs_n1`, `storage_macs_n2` fields to `TopologySnapshot` |
| `source/sdn_controller/topology.py`     | Modify | Split MAC sets into local/peer, publish roles, merge on reception                            |
| `source/scripts/osken-controller.env`   | Verify | Env vars must use plain MAC format (no `container_name:` prefix)                           |
| `source/scripts/build_network_setup.sh` | Verify | `-e SERVER_MACS=` must be plain MAC only                                                   |

---

## Step 1: Fix env-var format (prerequisite)

**Bug:** The env vars were modified to use `container_name:MAC` format (e.g. `edge_server_n1:00:00:00:00:00:02`), but the parsing code does a simple comma-split and stores the entire string. OS-Ken discovers MAC addresses as plain hex (`00:00:00:00:00:02`), so no hosts ever match, and all VIP pools remain empty.

**Fix:** Revert `SERVER_MACS`, `STORAGE_MACS_N1`, `STORAGE_MACS_N2` to plain comma-separated MACs.

`source/scripts/osken-controller.env`:

```bash
SERVER_MACS=                          # default empty; overridden per container
STORAGE_MACS_N1=00:00:00:00:00:04
STORAGE_MACS_N2=00:00:00:00:00:06
```

`source/scripts/build_network_setup.sh`:

```bash
-e SERVER_MACS="00:00:00:00:00:02"    # osken  (LAN1)
...
-e SERVER_MACS="00:00:00:00:00:05"    # osken_2 (LAN2)
```

No code changes — this is a configuration fix only.

---

## Step 2: Add MAC role fields to `TopologySnapshot`

**File:** `source/sdn_controller/models.py`

Add three optional fields (default `[]` for backward compatibility with old controller versions):

```python
class TopologySnapshot(BaseModel):
    type: str = "topology"
    network_id: str
    networks: dict[str, TopologyNetworkSection] = {}
    hosts: list[TopologyHostEntry] = []
    links: list[TopologyLinkEntry] = []
    switches: list[int] = []
    hops: dict = {}
    ts: float = 0.0
    # MAC role sets — advertised by sender so peer can merge them into its own pools
    server_macs:     list[str] = []
    storage_macs_n1: list[str] = []
    storage_macs_n2: list[str] = []
```

---

## Step 3: Split MAC sets into local vs peer in `TopologyMixin.__init__`

**File:** `source/sdn_controller/topology.py` — `__init__()`, around L40-L47

Replace the three `set[str]` attributes with a local/peer pair each, plus a property that exposes the union:

```python
# Local MAC sets — populated from env vars at startup, updated dynamically
self._local_server_macs:     set[str] = {
    m.strip() for m in os.environ.get("SERVER_MACS", "").split(",") if m.strip()
}
self._local_storage_macs_n1: set[str] = {
    m.strip() for m in os.environ.get("STORAGE_MACS_N1", "").split(",") if m.strip()
}
self._local_storage_macs_n2: set[str] = {
    m.strip() for m in os.environ.get("STORAGE_MACS_N2", "").split(",") if m.strip()
}

# Peer MAC sets — replaced wholesale on each topology update from the peer
self._peer_server_macs:     set[str] = set()
self._peer_storage_macs_n1: set[str] = set()
self._peer_storage_macs_n2: set[str] = set()
```

Add properties (or a helper method) so downstream code continues using `_server_macs` etc. unchanged:

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

The `logger.info(...)` init log and all downstream code (`_rebuild_vip_pools`, `_rebuild_hop_cache`) already use `self._server_macs` etc., so they work without change.

---

## Step 4: Update `add_server_mac` / `remove_server_mac` / `add_storage_mac` / `remove_storage_mac`

**File:** `source/sdn_controller/topology.py` — L106-L127

These must target `_local_*` sets (not the property, which is read-only):

```python
def add_server_mac(self, mac: str) -> None:
    self._local_server_macs.add(mac)
    self._rebuild_hop_cache()

def remove_server_mac(self, mac: str) -> None:
    self._local_server_macs.discard(mac)
    self._rebuild_hop_cache()

def add_storage_mac(self, mac: str, domain: str = "n1") -> None:
    if domain == "n2":
        self._local_storage_macs_n2.add(mac)
    else:
        self._local_storage_macs_n1.add(mac)
    self._rebuild_hop_cache()

def remove_storage_mac(self, mac: str, domain: str = "n1") -> None:
    if domain == "n2":
        self._local_storage_macs_n2.discard(mac)
    else:
        self._local_storage_macs_n1.discard(mac)
```

---

## Step 5: Publish local MAC roles in `_publish_topology`

**File:** `source/sdn_controller/topology.py` — `_publish_topology()`, L427-L465

Add the three new fields when constructing `TopologySnapshot`:

```python
snapshot = TopologySnapshot(
    network_id=self._network_id,
    networks=networks,
    hosts=local_section.hosts,
    links=local_section.links,
    switches=local_section.switches,
    hops=self.hop_cache,
    ts=time.time(),
    # Advertise this controller's registered backend MACs
    server_macs=list(self._local_server_macs),
    storage_macs_n1=list(self._local_storage_macs_n1),
    storage_macs_n2=list(self._local_storage_macs_n2),
)
```

Only local sets are published — the peer's own peer-sets are not re-echoed back, avoiding cycles.

---

## Step 6: Merge peer MAC roles in `on_topology_update`

**File:** `source/sdn_controller/topology.py` — `on_topology_update()`, L150-L184

After the existing peer host/link/switch extraction, add:

```python
# Replace peer MAC role sets wholesale so removals propagate correctly
self._peer_server_macs     = set(snapshot.server_macs)
self._peer_storage_macs_n1 = set(snapshot.storage_macs_n1)
self._peer_storage_macs_n2 = set(snapshot.storage_macs_n2)
logger.debug(
    "peer MAC roles updated from %s: server=%s storage_n1=%s storage_n2=%s",
    peer_nid,
    list(self._peer_server_macs),
    list(self._peer_storage_macs_n1),
    list(self._peer_storage_macs_n2),
)
```

Full replacement (not `|=`) ensures that if the peer removes a MAC (e.g. node removed), the next snapshot will no longer include it and the local view is corrected.

---

## Design Decisions

| Decision                                 | Rationale                                                                                                                                                                                                     |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Separate `_local_*` / `_peer_*` sets | Full replacement of peer sets on each update so removals propagate. A single merged set would accumulate stale MACs.                                                                                          |
| Only local MACs published                | Each controller advertises only what it registered — avoids reflecting peer data back to the peer, which would cause stale MACs to persist indefinitely.                                                     |
|                                          |                                                                                                                                                                                                               |
| No explicit locking                      | Python set operations are atomic enough in CPython with cooperative greenthread scheduling. Eventlet yields at I/O, not mid-set-operation.                                                                    |
| Readiness already guaranteed             | `add_server_mac` / `add_storage_mac` are called by `elasticity.py` only after the node is fully configured (veth attached; for storage: `rs.add` + SECONDARY confirmed). No additional gating needed. |

---

## Verification Checklist

- [ ] Startup logs show plain MACs: `server_macs=['00:00:00:00:00:02']`, not `container_name:MAC`
- [ ] After topology exchange, `vip_server_pool` log contains MACs from **both** networks
- [ ] `vip_storage_pool_n1` and `vip_storage_pool_n2` populated once hosts are discovered
- [ ] Dynamic add: add server on LAN1 → appears in LAN2's `vip_server_pool` on next tick
- [ ] Dynamic remove: remove server MAC on LAN1 → disappears from LAN2's pool on next tick
- [ ] Old-format topology message (no `server_macs` field) → peer MAC sets become empty, not error
