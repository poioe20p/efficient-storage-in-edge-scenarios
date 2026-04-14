# Storage Node Addition Reliability Fix — Plan

> **Status:** Implemented  
> **Date:** 2026-04-13  
> **Motivation:** Analysis of `20260412_204044` test run. 30 storage spawns
> attempted, 5 succeeded at `rs.add()`, zero reached VIP pool. Two root causes:
> stale RS members causing "Already present" errors (86% spawn failure) and
> `rs_secondary_ready` ZMQ event lost before socket was connected.

---

## Root Cause Analysis

### 1. Stale RS members → `rs.add()` "Already present" (86% failure rate)

When a storage node spawn fails *after* `rs.add()` succeeds (or the container
is removed without `rs.remove()`), a phantom RS member persists at the
allocated `IP:PORT`. The `IpAllocator` cycles through a small range (suffixes
2-29), so the next spawn to the same IP hits:

```
ERROR: MongoServerError: Reconfig attempted to add a member that is already present.
```

The phantom members have `priority: 0` (non-voting), so they cause no election
or write-concern issues — only wasted primary replication retry attempts to
dead endpoints.

### 2. `rs_secondary_ready` event lost → nodes never join VIP

The sidecar (`mongo_telemetry.py`) created its ZMQ PUSH socket at **module
import time**, before `eth0` existed (container starts with `--network none`).
The `_wait_for_ready()` function polls `localhost:27018` and detects SECONDARY
state, then emits `rs_secondary_ready` via `_sock.send_json(event, NOBLOCK)`.
But the TCP connection to the aggregator was never established (no network
interface), so the message was silently lost.

Evidence from `dyn6` docker logs:
- Sidecar *was* running past `_wait_for_ready()` (pushing `mongo_stats` events)
- MAC `00:00:00:00:02:03` appeared in telemetry with correct RS topology
- Controller never received `rs_secondary_ready` for any dynamic storage node
- Storage VIP pool never grew beyond the 1 static member

---

## Fixes

### Fix A — Stale RS member cleanup before `rs.add()`

**File:** `source/scripts/network/add_network_storage_node.sh`

Added `rs_cleanup_stale_member()` function called at the top of
`rs_add_member()`. Queries `rs.status().members` for an existing entry matching
the target `host:port`. If found, calls `rs.remove()` + 2 s wait, then
proceeds with `rs.add()`. No-op when clean. Errors are warnings, not fatal.

### Fix B — DROPPED

Originally proposed as RS cleanup in the Python failure path
(`elasticity.py`). Dropped because:
- Fix A handles stale RS cleanup on the next spawn to the same IP
- Phantom members are harmless (priority 0, non-voting, no write-concern impact)
- Only minor primary replication timeout noise until Fix A clears them

### Fix C — Reliable SECONDARY detection

#### Part 1 — Deferred ZMQ socket (`mongo_telemetry.py`)

Moved ZMQ socket creation from module-level into `main()`, *after*
`_wait_for_ready()` returns. At that point `eth0` must exist (reaching
SECONDARY requires network connectivity to the primary for rs.add + initial
sync). The `rs_secondary_ready` event is now sent on a properly connected
socket — this is the **fast path** for VIP promotion.

`_wait_for_ready()` was refactored to return the state string (`"SECONDARY"` or
`"PRIMARY"`) rather than sending the event itself.

#### Part 2 — `member_state` in telemetry events (`mongo_telemetry.py`)

Refactored `_repl_lag_s()` → `_repl_lag_and_state()` to return a tuple
`(lag_seconds, member_state_str)`. The `stateStr` was already read from
`replSetGetStatus` — now it's exposed in every `mongo_stats` and `heartbeat`
event as `"member_state"`.

#### Part 3 — Aggregator propagation (`aggregator.py`)

In the storage aggregation block, the latest `member_state` from the window is
picked via `events[-1].get("member_state")` and included in the summary dict.
Both active (mongo_stats) and heartbeat-only (idle) storage entries carry it.

#### Part 4 — Model field (`models.py`)

Added `member_state: str | None = None` to `StorageServerSummary`.

#### Part 5 — Telemetry-based VIP promotion (`main_n1.py`, `main_n2.py`)

New method `_promote_storage_from_telemetry()` called in `_on_telemetry_update()`
after `_log_and_update_stats()`. For each MAC in `storage_servers`:
- If `member_state == "SECONDARY"` AND MAC in `_active` AND MAC NOT in
  `_local_storage_macs_nX` → call `add_storage_mac(mac, domain)`.

Same operation as `_process_secondary_events()` — different trigger (regular
telemetry window vs one-shot control event). Fires ~2-4 s after the fast path.

---

## Files Modified

| File | Change |
| ---- | ------ |
| `source/scripts/network/add_network_storage_node.sh` | `rs_cleanup_stale_member()` before `rs_add_member()` |
| `source/docker/edge_storage_server/mongo_telemetry.py` | Deferred ZMQ socket; `_repl_lag_and_state()`; `member_state` in events |
| `source/docker/local_state_server/aggregator.py` | `member_state` propagated in storage summaries |
| `source/sdn_controller/telemetry/models.py` | `member_state` field on `StorageServerSummary` |
| `source/sdn_controller/main_n1.py` | `_promote_storage_from_telemetry()` fallback |
| `source/sdn_controller/main_n2.py` | `_promote_storage_from_telemetry()` fallback |
| `docs/operation/elasticy_manager/elasticity_overview.md` | New "Storage Node Reliability" section |

---

## Verification Checklist

1. Rebuild Docker images: `edge_storage_server`, `os-ken`, `local_state_server`
2. Run experiment with τ=0.40 phases
3. Shell script logs: no "Already present" `rs.add()` errors → Fix A working
4. Sidecar logs: `member_state` field present in pushed events
5. Controller logs: `rs_secondary_ready` events received → Fix C fast path
6. Controller logs: "promoting storage mac=… via telemetry fallback" → Fix C fallback
7. Dynamic storage MACs appear in VIP storage pool; traffic load-balanced to them
8. DataAlert storm stops after VIP promotion

---

## Design Decisions

- **Fix B dropped:** Fix A covers stale RS cleanup on next spawn; phantoms are
  harmless at priority 0.
- **Controller-side periodic timer dropped:** Replaced by `member_state` in the
  existing telemetry pipeline — no new thread or timer needed.
- **Dual VIP promotion path:** `rs_secondary_ready` control event is the fast
  path (~immediate); telemetry-based `member_state` detection is the fallback
  (~2-4 s delay on next aggregation window).
