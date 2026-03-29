# Dynamic Cross-Network Hop Penalty Plan

## Overview

The VIP routing selection (WSM cost function) uses `_CROSS_NETWORK_HOP_PENALTY` — a
static integer (default 3) — as the hop cost for cross-network backends. This causes
a selection inversion: when a new client has no entry in `hop_cache` yet, local
backends fall back to `hops_max` (worst case), while cross-network backends get the
fixed constant 3. If `_hop_cache_max > 3` from prior observations, the cross-network
backend incorrectly wins.

The fix replaces the static constant with a topology-derived dynamic value:
`avg_local_hops + avg_peer_hops`. The local average is computed from `hop_cache` after
each rebuild; the peer average is transmitted in `TopologySnapshot` and stored on
receipt. The same `avg_local_hops` is used as the fallback for locally-attached
backends whose specific path is not yet in `hop_cache`.

---

## Root Cause

In `select_server()` / `select_storage()` in `vip_routing.py`:

```python
hops = (self.hop_cache.get(client_mac) or {}).get(mac)
if hops is None:
    if mac in self.peer_hosts:
        hops = _CROSS_NETWORK_HOP_PENALTY   # fixed = 3
    else:
        hops = hops_max                     # ← BUG: also hits local backends
                                            #   with no hop entry yet
```

When a client is new (not in `hop_cache`):

- Local backend with no hop entry → `hops = hops_max`
- Cross-network backend → `hops = 3`
- If `hops_max > 3`, cross-network wins despite higher real cost.

---

## Fixes

### Fix 1 — Add `avg_hop_count` to `TopologySnapshot` model

**File:** `source/sdn_controller/models.py`

Add one field to `TopologySnapshot`:

```python
avg_hop_count: float = 0.0
```

Default `0.0` ensures backward compatibility with peers that don't send it yet.

---

### Fix 2 — Compute `_avg_hop_count` after each hop cache rebuild

**File:** `source/sdn_controller/topology.py`

**2a.** In `TopologyMixin.__init__()`, initialise:

```python
self._avg_hop_count: float = 0.0
self._peer_avg_hop_count: float = 0.0
```

**2b.** At the end of `_rebuild_hop_cache()`, after the existing `resolved` log line:

```python
all_hops = [
    v for per_host in self.hop_cache.values()
    for v in per_host.values()
    if v is not None
]
self._avg_hop_count = sum(all_hops) / len(all_hops) if all_hops else 0.0
logger.debug("hop cache avg hops: %.2f (from %d resolved paths)", self._avg_hop_count, len(all_hops))
```

---

### Fix 3 — Publish `avg_hop_count` in topology snapshot

**File:** `source/sdn_controller/topology.py`

In `_publish_topology()`, add `avg_hop_count=self._avg_hop_count` when constructing
`TopologySnapshot`:

```python
snapshot = TopologySnapshot(
    ...
    avg_hop_count=self._avg_hop_count,
    ...
)
```

---

### Fix 4 — Store peer's `avg_hop_count` on receipt

**File:** `source/sdn_controller/topology.py`

In `on_topology_update()`, after validating the incoming snapshot:

```python
self._peer_avg_hop_count = snapshot.avg_hop_count
logger.debug("peer avg hop count updated: %.2f", self._peer_avg_hop_count)
```

---

### Fix 5 — Replace static fallback with dynamic three-way branch

**File:** `source/sdn_controller/vip_routing.py`

Apply the same change in **both** `select_server()` and `select_storage()`.

Replace:

```python
if hops is None:
    if mac in self.peer_hosts:
        hops = _CROSS_NETWORK_HOP_PENALTY
    else:
        hops = hops_max
```

With:

```python
if hops is None:
    if mac in self.peer_hosts:
        local_avg = max(self._avg_hop_count, 1.0)
        peer_avg  = max(self._peer_avg_hop_count, 1.0)
        hops = local_avg + peer_avg
    elif mac in self.host_attachment:
        hops = max(self._avg_hop_count, 1.0)
    else:
        hops = hops_max   # truly unknown MAC — safety net
```

The `max(..., 1.0)` guards against cold-start (both averages still 0.0 before the
first topology tick), guaranteeing cross-network ≥ 2.0 and local-unknown ≥ 1.0.

---

### Fix 6 — Remove `_CROSS_NETWORK_HOP_PENALTY`

**File:** `source/sdn_controller/vip_routing.py`

Remove the module-level constant and its `logger.debug` reference in `__init__`:

```python
# DELETE these lines:
_CROSS_NETWORK_HOP_PENALTY = int(os.environ.get("CROSS_NETWORK_HOP_PENALTY", "3"))
```

```python
# DELETE from logger.debug in __init__:
"... cross_hop_penalty=%d",
..., _CROSS_NETWORK_HOP_PENALTY,
```

Also remove `CROSS_NETWORK_HOP_PENALTY` from `source/scripts/osken-controller.env` if
it is set there.

---

## Invariants After Fix

| Condition             | Backend type               | Hops assigned                     | Guaranteed ordering    |
| --------------------- | -------------------------- | --------------------------------- | ---------------------- |
| Path in `hop_cache` | any                        | real path length                  | exact                  |
| No path yet, local    | `mac in host_attachment` | `avg_local` (≥ 1.0)            | local ≤ cross-network |
| No path yet, remote   | `mac in peer_hosts`      | `avg_local + avg_peer` (≥ 2.0) | cross-network > local  |
| Truly unknown MAC     | neither                    | `hops_max`                      | worst case             |

---

## Verification

1. **Cold-start regression:** restart all containers with no prior traffic; send a
   request from a new client immediately — confirm a local backend is selected, not
   cross-network.
2. **After topology tick:** `_avg_hop_count` appears in DEBUG logs with a sane value
   (1.0 for single-switch LAN); `_peer_avg_hop_count` updates after ZMQ exchange.
3. **Cross-network selection still works:** when ALL local backends are removed from
   the pool, a cross-network backend is still selected and DNAT/SNAT rules are
   installed correctly (existing cross-network routing plan behaviour is unaffected).
4. **Symmetry check:** both osken and osken_2 log matching `avg_hop_count` values
   (both single-switch LANs → 1.0 each; cross-network penalty = 2.0).
