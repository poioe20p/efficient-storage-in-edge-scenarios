# Sidecar ZMQ & Timeout Fix — Implementation Plan

> **Status:** Implemented (rev 2)  
> **Date:** 2026-04-13  
> **Motivation:** Post-implementation test run `20260413_154833` — after the
> predictive threshold + async RS join changes, dynamic storage nodes are
> provisioned fast (7–12 s) but **never join the VIP pool** because the
> sidecar blocks forever in `_wait_for_ready()`.
> 
> **Rev 2 (20260413_165850):** ZMQ + timeout fix deployed, but nodes still
> never reach SECONDARY. Two additional root causes discovered and fixed:
> 1. `_wait_for_network()` race condition — eth0 interface appears before
>    IPv4 is assigned, causing `_discover_own_ip()` to fail immediately.
> 2. MongoDB 7-voting-member limit — dynamic members were added with
>    `votes: 1` (default), hitting the ceiling after 7 members.

---

## TL;DR

After the async RS join was moved into the sidecar
([`predictive_threshold_and_async_rs_plan.md`](predictive_threshold_and_async_rs_plan.md)),
a follow-up test showed that dynamic storage nodes are created successfully
but never serve traffic. Fix with three changes to `mongo_telemetry.py`:

1. **Early ZMQ socket** — create before `_wait_for_ready()` so telemetry
   flows even while the node is still syncing.
2. **Timeout on `_wait_for_ready()`** — configurable via `RS_READY_TIMEOUT_S`
   (default 300 s); falls through to telemetry loop on timeout.
3. **Verbose logging in `_rs_self_join()`** — log primary discovery, RS config
   version, member list, and reconfig outcome for next-run diagnostics.

---

## Problem Summary

### What the test showed

| Metric | Expected | Actual |
|--------|----------|--------|
| Node creation time | 7–12 s | 7–12 s ✓ |
| `storage_count` | Grows from 1 | Stays at 1 ✗ |
| `vip_storage_pool` | Grows | Never changes ✗ |
| `rs_secondary_ready` events | ≥1 per dynamic node | 0 ✗ |
| `_promote_storage_from_telemetry()` | Fires as fallback | Never fires ✗ |

Dynamic storage containers (`edge_storage_lan1_dyn1`, `dyn2`, etc.) were
created and network-attached in 7–12 s — a major improvement from the
previous 34–45 s. However, **none of them ever joined the VIP pool**.

### Root cause chain

1. `_rs_self_join()` may succeed or silently fail after 5 retries.
2. `_wait_for_ready()` loops **forever** (`while True`) waiting for the node
   to reach SECONDARY or PRIMARY state.
3. If RS join failed → node never becomes SECONDARY → infinite loop.
4. **ZMQ socket was only created AFTER `_wait_for_ready()` returned** — so the
   node cannot emit *any* telemetry or events while stuck.
5. Controller never receives `rs_secondary_ready` → VIP never updated.
6. Fallback `_promote_storage_from_telemetry()` also never fires, because the
   fallback checks regular telemetry for `member_state=="SECONDARY"` — and
   no telemetry is arriving at all (no ZMQ socket).

### Evidence from controller logs

- All dynamic nodes show `"(VIP deferred until SECONDARY)"` — correct.
- Zero `rs_secondary_ready` events received.
- Zero `_promote_storage_from_telemetry()` calls.
- `storage_macs_n1` stays at `['00:00:00:00:00:04']` throughout.
- `server_macs` (compute) **does grow** — confirming compute nodes register
  fine (they use `add_server_mac()` immediately, no deferred path).

---

## Fix Details

### Phase A — Early ZMQ socket (critical)

**Before:**
```
_rs_self_join() → _wait_for_ready() → create ZMQ → emit events → telemetry loop
                  ↑ blocks forever if RS join failed — ZMQ never created
```

**After:**
```
_rs_self_join() → create ZMQ → _wait_for_ready(timeout) → emit events → telemetry loop
                               ↑ times out after 300s — falls through to loop
```

Key changes in `main()`:
- ZMQ socket created **after** `_rs_self_join()` (which ensures eth0 exists via
  `_wait_for_network()`) but **before** `_wait_for_ready()`.
- Even if the node never reaches SECONDARY, it will eventually enter the
  telemetry loop and send heartbeats, giving the controller visibility.

### Phase B — Timeout on `_wait_for_ready()`

- Signature: `_wait_for_ready(timeout: float = RS_READY_TIMEOUT_S) -> str | None`
- New env var: `RS_READY_TIMEOUT_S` (default `300` — 5 minutes)
- Returns `None` on timeout instead of blocking forever.
- Progress logging every 30 s while waiting.
- Caller handles `None`: logs a warning but still enters the telemetry loop.

### Phase C — Verbose logging in `_rs_self_join()`

Added `INFO`-level logs at:
- `isMaster` response: primary host and setName
- RS config fetch: version number and full member host list
- Reconfig success: new config version and member count

These enable diagnosing RS join failures from container logs without needing
to add additional debug instrumentation.

---

## New Environment Variable

| Variable | Default | Description |
|----------|---------|-------------|
| `RS_READY_TIMEOUT_S` | `300` | Max seconds `_wait_for_ready()` blocks before falling through |

---

## Files Modified

| File | Change |
|------|--------|
| `source/docker/edge_storage_server/mongo_telemetry.py` | Early ZMQ, timeout in `_wait_for_ready()`, verbose `_rs_self_join()` logging, `RS_READY_TIMEOUT_S` constant |

---

## Updated `main()` Flow

```python
def main() -> None:
    # 1. RS self-join (if RS_ADD_SELF=true) — blocks until network ready
    if os.environ.get("RS_ADD_SELF") == "true":
        _rs_self_join()

    # 2. Create ZMQ socket EARLY — eth0 exists after _rs_self_join()
    _sock = _ctx.socket(zmq.PUSH)
    _sock.connect(AGGREGATOR_PULL_ADDR)

    # 3. Wait for RS state WITH TIMEOUT — returns None on timeout
    state_str = _wait_for_ready()  # default 300s

    # 4. Emit rs_secondary_ready if applicable
    if state_str == "SECONDARY":
        _sock.send_json({"event_type": "rs_secondary_ready", ...})
    elif state_str is None:
        logger.warning("entering telemetry loop without confirmed RS state")

    # 5. Normal telemetry loop — always reached
    while True:
        _push_stats()
        time.sleep(INTERVAL_S)
```

---

## Verification

1. Re-run the test workload and check:
   - `rs_secondary_ready` events appear in controller logs
   - `storage_count` increases above 1
   - `vip_storage_pool` grows to include dynamic MACs
2. If RS join still fails, container logs will now show:
   - `isMaster → primary=...` (or `no primary in isMaster response`)
   - `RS config v..., N members: [...]`
   - Error details with full PyMongo exception messages
3. Even on RS join failure, the node enters the telemetry loop after 300 s
   timeout — controller will see heartbeats from the node.
4. Docker image must be rebuilt: `docker build -t edge_storage_server source/docker/edge_storage_server/`

---

## Relationship to Prior Plans

- **Extends:** [`predictive_threshold_and_async_rs_plan.md`](predictive_threshold_and_async_rs_plan.md)
  Phase 2b — same file (`mongo_telemetry.py`), same functions.
- **Supersedes:** The "deferred ZMQ socket" approach from
  [`storage_reliability_plan.md`](storage_reliability_plan.md) Fix C Part 1 —
  the socket is now created **before** `_wait_for_ready()`, not after.
