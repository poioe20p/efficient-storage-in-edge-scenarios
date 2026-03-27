# Graceful Node Removal — Implementation Plan

## Overview

Add graceful scale-down to the elasticity system. Symmetrical to Thread 3's node addition, removal goes through the same orchestration layers: `ElasticityManager` (policy + sequencing) → `NodeAdder` (lifecycle steps) → shell scripts (low-level OVS/Docker operations).

The removal design uses a **two-phase cooperative drain** to avoid cutting active connections mid-flight, while keeping complexity proportional to each node type.

---

## Architecture

### Two-Phase Cooperative Drain

**Phase A — Controller-side isolation (immediate):**
1. Remove MAC from VIP pool (`remove_server_mac` / `remove_storage_mac`) — no new VIP connections routed to this node
2. Storage only: `rs.remove(IP:PORT)` via the replica set primary — node leaves the RS before any shutdown

**Phase B — Node drain + controller cleanup:**
1. Signal node to stop accepting work (mechanism differs per type — see below)
2. Wait for active work to finish (or timeout)
3. `docker stop` if still running after timeout (force)
4. Flush OVS flows for the MAC, remove OVS port, delete veth pair
5. `docker rm` (and `docker volume rm` for storage)

### Drain Mechanism by Node Type

| | Compute (`edge_server`) | Storage (`edge_storage_server`) |
|---|---|---|
| **Has HTTP API?** | Yes (Flask on :5000) | No — `mongod` is the main process |
| **Drain signal** | `docker exec <name> curl -sS -X POST http://localhost:5000/drain` | Phase A is sufficient — `rs.remove()` + VIP removal stop all new work |
| **Idle detection** | Flask active-request counter hits 0 → container calls `os._exit(0)` | Controller reads telemetry pipeline: `connections_current ≤ 1` in next ZMQ window (~10 s) |
| **Who stops container?** | Container exits itself; controller detects via `docker inspect` poll | Controller calls `docker stop` once idle confirmed |
| **Timeout fallback** | Controller force-stops after 30 s | Controller force-stops after 15 s |

**Why `docker exec` for the drain signal:** after removing the MAC from the VIP pool, the OVS data path may still have stale DNAT flows. `docker exec` bypasses the network stack entirely and is reliable regardless of flow state.

**Why the telemetry pipeline for storage idle detection:** `mongo_telemetry.py` already pushes `connections_current` every `TELEMETRY_INTERVAL_S` (≈10 s) to the aggregator, which the controller already receives via `ZmqTelemetrySource`. Reusing this avoids any extra polling: zero additional overhead vs the alternative of spawning a `mongosh` process repeatedly.

---

## Files to Change

| File | Action | Purpose |
|------|--------|---------|
| `source/docker/edge_server/source/app.py` | Modify | Add `/drain` + `/drain/status` endpoints, active-request counter, drain monitor thread |
| `source/sdn_controller/node_manager.py` | Modify | Add `remove_edge_server()`, `remove_storage_node()`, removal helpers |
| `source/sdn_controller/elasticity.py` | Modify | Add `ScaleDownComputeAlert`, `ScaleDownDataAlert`, handlers in `_loop()` |
| `source/scripts/network/remove_network_node.sh` | Modify | Add `--graceful` + `--drain-timeout` flags |
| `source/scripts/network/remove_network_storage_node.sh` | Modify | Add `--graceful` + `--drain-timeout` flags |
| `source/sdn_controller/topology.py` | **No change** | `remove_server_mac()` and `remove_storage_mac()` already exist |

---

## Step 1 — Edge Server Drain Endpoint

**File:** `source/docker/edge_server/source/app.py`

The Flask app needs to know when it has zero active in-flight requests so it can safely exit.

### Changes

1. Add thread-safe active-request counter using a `threading.Lock` + integer.
   - `@app.before_request`: increment counter — skip for `/health` and `/drain*` paths
   - `@app.after_request`: always decrement counter (including on exception paths)

2. Add `_draining: bool = False` module-level flag.

3. Add `@app.before_request` guard: if `_draining` and route is not `/health` or `/drain*`, return `503 {"status": "draining"}` immediately. This stops new work from arriving while in-flight requests complete.

4. Add `POST /drain` endpoint:
   - Sets `_draining = True`
   - Returns `200 {"status": "draining", "active_requests": N}`

5. Add `GET /drain/status` endpoint:
   - Returns `{"draining": bool, "active_requests": int}`
   - Used passively by operators; the controller does not rely on polling this during removal

6. Add drain monitor background thread (started at app startup):
   - Sleeps 0.5 s between checks
   - When `_draining is True` and `active_requests == 0` → calls `os._exit(0)`
   - `os._exit` is used rather than `signal.raise(SIGTERM)` to guarantee immediate exit even if other background threads (e.g. ZMQ) are alive

---

## Step 2 — NodeAdder Removal Methods

**File:** `source/sdn_controller/node_manager.py`

Mirror the existing `add_edge_server` / `add_storage_node` pattern with removal counterparts.

### New Dataclasses

```python
@dataclass
class RemovalTimings:
    drain_signal_s:    float = 0.0
    drain_wait_s:      float = 0.0
    network_cleanup_s: float = 0.0
    total_s:           float = 0.0

@dataclass
class RemovalResult:
    success:        bool
    container_name: str
    mac:            str | None
    timings:        RemovalTimings
    state:          NodeOperationState
    stdout:         str = ""
    stderr:         str = ""
```

### `remove_edge_server(lan, name, mac, drain_timeout=30)`

Steps (each individually timed):

1. **Discover OVS veth** — call `_discover_ovs_veth(name)` while the container is still running; records the veth name for later cleanup
2. **Signal drain** — `docker exec <name> curl -sS -X POST http://localhost:5000/drain`
3. **Wait for container exit** — poll `docker inspect` every 1 s until status is not "running" or `drain_timeout` expires
4. **Force-stop if needed** — `docker stop <name>` if still running after timeout
5. **Flush OVS flows** — `_flush_mac_flows(bridge, mac)` — removes `dl_src` and `dl_dst` entries
6. **Remove OVS port** — `_remove_ovs_port(bridge, veth)`
7. **Delete veth pair** — `_delete_veth(veth)` via `nsenter` into OVS netns
8. **Remove container** — `docker rm <name>`

Returns `RemovalResult`.

### `remove_storage_node(lan, name, mac, ip, rs_name, primary_container, port=27018, drain_timeout=15, keep_volume=False)`

Steps:

1. **Discover OVS veth** — same as compute
2. **Find RS primary** — `docker exec <primary> mongosh --quiet --port <port> --eval "db.adminCommand({isMaster:1}).primary"`
3. **rs.remove** — `docker exec <primary> mongosh ... --eval "rs.remove('<ip>:<port>')"`
4. **Wait for RS removal** — poll `rs.status()` until the member no longer appears (max 10 retries, 3 s each)
5. **Wait for idle** — `_poll_mongo_connections(name, port, drain_timeout)`: read `connections_current` from the telemetry data already in `ElasticityManager`; if not available yet, fall back to a single `docker exec mongosh db.serverStatus().connections.current` check at timeout boundary
6. **Stop container** — `docker stop <name>`
7. **Flush OVS flows** — `_flush_mac_flows(bridge, mac)`
8. **Remove OVS port** — `_remove_ovs_port(bridge, veth)`
9. **Delete veth pair** — `_delete_veth(veth)`
10. **Remove container** — `docker rm <name>`
11. **Remove volume** — `docker volume rm <name>-data` unless `keep_volume=True`

Returns `RemovalResult`.

### New Private Helpers

| Helper | Description |
|--------|-------------|
| `_discover_ovs_veth(name, iface="eth0")` | Read peer ifindex from container netns via `nsenter`; find matching link in OVS netns |
| `_flush_mac_flows(bridge, mac)` | `docker exec ovs ovs-ofctl del-flows <bridge> dl_src=<mac>` and `dl_dst=<mac>` |
| `_remove_ovs_port(bridge, veth)` | `docker exec ovs ovs-vsctl del-port <bridge> <veth>` |
| `_delete_veth(veth)` | `sudo nsenter --net=/var/run/netns/ovs ip link del <veth>` |
| `_wait_container_stopped(name, timeout)` | Poll `docker inspect` every 1 s until not "running" or timeout; returns `True` if stopped, `False` if timed out |
| `_poll_mongo_connections(name, port, timeout)` | See note above — uses telemetry data where available |

---

## Step 3 — Shell Scripts: Graceful Flag

**Files:** `source/scripts/network/remove_network_node.sh` and `remove_network_storage_node.sh`

Add `--graceful` and `--drain-timeout <seconds>` flags to each script. Without `--graceful` the scripts retain their current immediate-removal behaviour (backward compatible).

### `remove_network_node.sh --graceful`

After the existing veth/MAC discovery:

1. Send drain signal: `docker exec "$CONTAINER_NAME" curl -sS -X POST http://localhost:5000/drain`
2. Poll `docker inspect` for container exit every 1 s up to `DRAIN_TIMEOUT` (default 30 s)
3. If still running: `docker stop "$CONTAINER_NAME"`
4. Continue with existing network teardown (flush flows, del-port, veth deletion, docker rm)

```
Usage change:
  remove_network_node.sh --lan 1 --name edge_server_n1_dyn1 --graceful
  remove_network_node.sh --lan 1 --name edge_server_n1_dyn1 --graceful --drain-timeout 60
```

### `remove_network_storage_node.sh --graceful`

After existing RS removal and the veth/MAC/IP discovery:

1. After `rs.remove()` succeeds, print "Waiting for connections to drain..."
2. Poll `docker exec "$CONTAINER_NAME" mongosh --quiet --port "$PORT" --eval "db.serverStatus().connections.current"` every 2 s up to `DRAIN_TIMEOUT` (default 15 s)
3. If connections ≤ 1 before timeout: proceed immediately
4. `docker stop "$CONTAINER_NAME"`
5. Continue with existing network + volume teardown

```
Usage change:
  remove_network_storage_node.sh --lan 1 --name edge_storage_n1_dyn1 --graceful
  remove_network_storage_node.sh --lan 1 --name edge_storage_n1_dyn1 --graceful --drain-timeout 30
```

> **Note on storage drain in the shell script:** the shell script uses the `mongosh` polling approach since it has no access to the controller's telemetry pipeline. This is only used when the script is called standalone (manually by an operator). When called through `NodeAdder`, the controller uses the telemetry pipeline instead.

---

## Step 4 — ElasticityManager Scale-Down

**File:** `source/sdn_controller/elasticity.py`

### New Alert Types

```python
@dataclass(frozen=True)
class ScaleDownComputeAlert:
    lan:            int
    network_id:     str
    container_name: str
    ip:             str
    mac:            str

@dataclass(frozen=True)
class ScaleDownDataAlert:
    lan:               int
    network_id:        str
    container_name:    str
    ip:                str
    mac:               str
    rs_name:           str
    primary_container: str
    port:              int = 27018
```

The `ip` and `mac` fields are passed in from the caller (the controller already has these from the original `NodeResult` produced at addition time). Passing them avoids re-discovery race conditions.

### New Handlers

`_handle_scale_down_compute(alert: ScaleDownComputeAlert)`:
1. Call `self._topo.remove_server_mac(alert.mac)` — immediate, stops new VIP routing to this node
2. Call `self._adder.remove_edge_server(lan=alert.lan, name=alert.container_name, mac=alert.mac, ...)`
3. `self._adder.log_timings(result)` (reuse existing method; adapt for `RemovalResult`)
4. `self._record({"type": "scale_down_compute", "alert": alert, "result": result})`
5. Log success or failure

`_handle_scale_down_data(alert: ScaleDownDataAlert)`:
1. Call `self._topo.remove_storage_mac(alert.mac)`
2. Call `self._adder.remove_storage_node(lan=alert.lan, name=alert.container_name, mac=alert.mac, ip=alert.ip, rs_name=alert.rs_name, primary_container=alert.primary_container, port=alert.port)`
3. Record and log

### Loop Extension

Extend `_loop()` to dispatch `ScaleDownComputeAlert` and `ScaleDownDataAlert`:

```python
elif isinstance(alert, ScaleDownComputeAlert):
    self._handle_scale_down_compute(alert)
elif isinstance(alert, ScaleDownDataAlert):
    self._handle_scale_down_data(alert)
```

---

## Step 5 — Thread 2 Scale-Down Detection (Deferred)

Deciding *when* to remove a node (scale-down policy thresholds) is a separate concern and is intentionally excluded from this plan. The removal *mechanism* (this plan) must be solid and tested before the detection logic is layered on top.

When implemented, Thread 2 will submit `ScaleDownComputeAlert` / `ScaleDownDataAlert` to the `ElasticityManager` queue via `submit_alert()`, exactly mirroring how `ComputeAlert` / `DataAlert` are submitted today.

---

## Verification

| Scenario | What to check |
|----------|---------------|
| Drain endpoint smoke test | `curl -X POST localhost:5000/drain` → 200; subsequent POST to `/data` → 503; idle container exits |
| Compute removal integration | `add_edge_server` → send requests → `remove_edge_server` → OVS port gone, veth deleted, container removed |
| Storage removal integration | `add_storage_node` → `remove_storage_node` → member gone from `rs.status()`, container stopped, volume removed |
| Script standalone (compute) | `remove_network_node.sh --graceful --lan 1 --name <c>` works from CLI |
| Script standalone (storage) | `remove_network_storage_node.sh --graceful --lan 1 --name <c>` works from CLI |
| Timeout path | Drain busy server with `drain_timeout=5` → container force-stopped after 5 s |
| Idempotency | Call removal twice → second call handles "container not found" without error |
| Crash during drain | Container crashes mid-drain → controller detects "exited" state and proceeds to cleanup |

---

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| `docker exec curl` for drain signal | Bypasses OVS network stack; works even after flows are flushed |
| `os._exit(0)` in drain monitor | Guarantees container exit even if ZMQ/background threads hold event loop references |
| `/drain` endpoint over SIGTERM | SIGTERM stops the server from accepting new connections but does not let it return 503 to clients; the endpoint provides an explicit drain window |
| Telemetry pipeline for storage idle detection | `connections_current` already arrives every ~10 s at zero extra cost; `mongosh` polling would spawn a Node.js process on each check |
| mongosh polling in shell scripts | Scripts have no access to the telemetry pipeline; `mongosh` polling is acceptable for manual operator use |
| Drain timeouts: 30 s compute / 15 s storage | HTTP clients may have long outstanding requests; MongoDB connections are shorter-lived due to RS membership change |
| MAC + IP as parameters to removal methods | Controller has these from the original `NodeResult`; avoids re-discovery race conditions if the container is partially torn down |
| `--graceful` flag on shell scripts | Backward-compatible; operators can still perform immediate removal if needed |
| Removal recorded in same `_active` audit trail | Keeps a unified operation history with `type="scale_down_compute"` / `type="scale_down_data"` tags |
| Thread 2 detection deferred | Policy (when to scale down) is separate from mechanism (how); test mechanism first |
