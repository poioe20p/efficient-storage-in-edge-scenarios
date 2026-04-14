# Plan: Node-Add Pipeline Optimization

## Problem

Storage node additions take **32–164 s** in production (test run `20260411_211928`).
The `net_attach` timing recorded by Thread 3 includes three hidden costs that
dominate the wall clock:

| Cost                                    | Typical range | Where                                            |
| --------------------------------------- | ------------- | ------------------------------------------------ |
| `collect_used_ips()` scan             | 5–20 s       | `add_network_storage_node.sh`, O(N) containers |
| `ensure_rs_secondary()` wait          | 10–30 s      | Same script, 10 retries × 3 s                   |
| `_cleanup_container()` on fresh names | 1.5–4 s      | `_BaseNodeAdder`, 3 docker commands            |

Because each add blocks Thread 3 for 60–80 s, the system is **still overloaded**
when the add finishes → Thread 2 triggers again → cascade of 10–15 nodes, later
ones failing from host resource exhaustion.

**Target:** reduce per-add wall clock to **5–10 s**, which naturally prevents
runaway scaling without needing hard node caps.

---

## Goal

1. **Pre-assign IP/MAC** from Python — eliminate the O(N) container scan.
2. **Conditional cleanup** — skip `docker stop/rm/volume rm` for names that don't exist yet.
3. **Remove SECONDARY wait** from the shell script — return after `rs.add()`.

   > **⚠ Superseded (2026-04-13):** This step is replaced by the more
   > comprehensive async RS join via the `mongo_telemetry.py` sidecar —
   > `rs.add()` is now performed entirely inside the container, not the
   > shell script at all. See
   > [`predictive_threshold_and_async_rs_plan.md`](predictive_threshold_and_async_rs_plan.md)
   > Phase 2.
4. **Sidecar SECONDARY event** — `mongo_telemetry.py` detects `stateStr == SECONDARY`
   and pushes a one-shot `rs_secondary_ready` ZMQ event.
5. **Aggregator fast-path** — treat `rs_secondary_ready` like `drain_complete`
   (immediate mini-summary, no 10 s window).
6. **Deferred VIP registration** — the controller adds the storage node to the
   VIP pool **only after** receiving `rs_secondary_ready`, preventing traffic to
   non-ready replicas.

---

## Phase A — Pre-assigned IP/MAC (eliminates O(N) scan)

### Current flow (slow)

The shell script scans every running container and named namespace:

```bash
# add_network_storage_node.sh — collect_used_ips() (simplified)
for cid in $(docker ps -q); do
    pid=$(docker inspect -f '{{.State.Pid}}' "$cid") || continue
    sudo nsenter -t "$pid" -n ip -4 -o addr show \
        | grep -oE "${subnet//./\.}\.[0-9]+"
done
while read -r ns _rest; do
    sudo ip -n "$ns" -4 -o addr show \
        | grep -oE "${subnet//./\.}\.[0-9]+"
done < <(ip netns list 2>/dev/null || true)
```

This degrades from ~5 s (few containers) to 20 s+ (many containers).

### Proposed flow

Python allocates the next IP from a per-LAN counter and passes `--ip` / `--mac`
to the script. The script skips auto-assignment when these are provided.

### `IpAllocator` class (`node_common.py`)

```python
class IpAllocator:
    """Per-LAN IP allocator for dynamic service nodes (.6–.29).

    Suffixes 1–5 are reserved for static infrastructure on each LAN:
        .1  router (default gateway)
        .2  edge_server (compute)
        .3  (reserved)
        .4  edge_storage_server (MongoDB primary)
        .5  local_state_server (aggregator)

    Dynamic nodes start at suffix 6 to avoid IP collisions.

    MAC addresses are derived deterministically:
        00:00:00:00:{lan:02x}:{suffix:02x}
    """

    _MIN_SUFFIX = 6
    _MAX_SUFFIX = 29

    def __init__(self, lan: int) -> None:
        self._lan = lan
        self._subnet_prefix = f"10.0.{lan - 1}"   # lan1 → 10.0.0, lan2 → 10.0.1
        # Pool of available suffixes (order gives predictable low-first allocation)
        self._free: list[int] = list(range(self._MIN_SUFFIX, self._MAX_SUFFIX + 1))
        self._in_use: set[int] = set()

    def allocate(self) -> tuple[str, str]:
        """Return (ip, mac) for the next available suffix. Raises if exhausted."""
        if not self._free:
            raise RuntimeError(f"IP pool exhausted for LAN {self._lan}")
        suffix = self._free.pop(0)
        self._in_use.add(suffix)
        ip  = f"{self._subnet_prefix}.{suffix}"
        mac = f"00:00:00:00:{self._lan:02x}:{suffix:02x}"
        return ip, mac

    def release(self, ip: str) -> None:
        """Return an IP to the free pool."""
        suffix = int(ip.rsplit(".", 1)[1])
        if suffix in self._in_use:
            self._in_use.discard(suffix)
            # Re-insert in sorted order for predictable allocation
            import bisect
            bisect.insort(self._free, suffix)

    def mark_used(self, ip: str) -> None:
        """Mark an IP as in-use (for static/pre-existing nodes)."""
        suffix = int(ip.rsplit(".", 1)[1])
        if suffix in self._free:
            self._free.remove(suffix)
        self._in_use.add(suffix)
```

### Instantiation in `ElasticityManager.__init__()` (`elasticity.py`)

The real signature is `__init__(self, topology_mixin: TopologyMixin)` — there is
no `network_id` parameter. LAN is determined per-alert from `alert.lan`. We use
a lazily-created per-LAN dict of allocators:

```python
from .node_common import IpAllocator

class ElasticityManager:
    def __init__(self, topology_mixin: TopologyMixin) -> None:
        # ... existing init ...
        self._ip_allocs: dict[int, IpAllocator] = {}   # keyed by LAN number

    def _get_allocator(self, lan: int) -> IpAllocator:
        """Lazy per-LAN allocator — created on first use."""
        if lan not in self._ip_allocs:
            self._ip_allocs[lan] = IpAllocator(lan)
        return self._ip_allocs[lan]
```

### Passing IP/MAC to scripts (`storage_node_manager.py`)

```python
# In add_storage_node(), before calling _run_script:
def add_storage_node(self, lan, name, rs_name, primary_container, port=27018,
                     ip=None, mac=None):
    # ... docker run step unchanged ...

    # ── Step 2: network attach + RS join ──────────────────────────────
    script_args = [
        "--lan", str(lan),
        "--name", name,
        "--rs-name", rs_name,
        "--primary", primary_container,
        "--port", str(port),
    ]
    if ip:
        script_args += ["--ip", ip]
    if mac:
        script_args += ["--mac", mac]

    ok, result_ip, result_mac, stdout2, stderr2 = self._run_script(
        SCRIPTS_DIR / "add_network_storage_node.sh",
        script_args,
    )
```

Same pattern for `compute_node_manager.py`:

```python
def add_edge_server(self, lan, name, ip=None, mac=None):
    # ... docker run step ...

    script_args = ["--lan", str(lan), "--name", name]
    if ip:
        script_args += ["--ip", ip]
    if mac:
        script_args += ["--mac", mac]

    ok, result_ip, result_mac, stdout2, stderr2 = self._run_script(
        SCRIPTS_DIR / "add_network_node.sh",
        script_args,
    )
```

### Caller in `ElasticityManager._handle_data()` (`elasticity.py`)

```python
def _handle_data(self, alert: DataAlert) -> None:
    name = self._next_name("edge_storage", alert.network_id)
    ip, mac = self._get_allocator(alert.lan).allocate()
    logger.info("[elasticity] data: spawning %s on LAN %d (ip=%s mac=%s)", name, alert.lan, ip, mac)

    result = self._storage_adder.add_storage_node(
        lan=alert.lan, name=name,
        rs_name=alert.rs_name,
        primary_container=alert.primary_container,
        port=alert.port,
        ip=ip, mac=mac,
    )
    # ... rest unchanged, but on failure release the IP: ...
    if not result.success:
        self._get_allocator(alert.lan).release(ip)
```

### Caller in `ElasticityManager._handle_compute()` (`elasticity.py`)

```python
def _handle_compute(self, alert: ComputeAlert) -> None:
    name = self._next_name("edge_server", alert.network_id)
    ip, mac = self._get_allocator(alert.lan).allocate()
    logger.info("[elasticity] compute: spawning %s on LAN %d (ip=%s mac=%s)", name, alert.lan, ip, mac)

    result = self._compute_adder.add_edge_server(
        lan=alert.lan, name=name,
        ip=ip, mac=mac,
    )
    # ... rest unchanged, but on failure release the IP: ...
    if not result.success:
        self._get_allocator(alert.lan).release(ip)
```

### Shell script changes (`add_network_storage_node.sh`, `add_network_node.sh`)

Both scripts already accept `--ip` and `--mac` in the CLI interface (see
`build_network_add_node_plan.md`), but currently still run `collect_used_ips()`
even when they are provided. The change skips the scan:

```bash
# In main(), after argument parsing:
if [[ -n "$IP" && -n "$MAC" ]]; then
    log "Using pre-assigned IP=$IP MAC=$MAC — skipping auto-assignment"
else
    log "Auto-assigning IP and MAC..."
    IP=$(auto_assign_ip)
    MAC=$(auto_generate_mac "$IP")
fi
```

> **Tradeoff:** when `--ip`/`--mac` are provided, this also skips
> `validate_ip_not_taken()` (which internally calls `collect_used_ips()`).
> We accept this because the Python `IpAllocator` is the single source of
> truth for dynamic IPs — collisions are impossible unless someone manually
> assigns IPs outside the allocator. This should be explicitly documented
> as a pre-condition in the script's `--ip` argument help text.

### IP release on node removal (`elasticity.py`)

```python
def _handle_scale_down_data(self, alert: ScaleDownDataAlert) -> None:
    # ... existing rs.remove + script teardown ...
    if result.success:
        self._get_allocator(alert.lan).release(alert.ip)
```

### IP release for compute nodes (`elasticity.py`)

`ScaleDownComputeAlert` currently has no `ip` field. To support compute IP
release, either:

1. **Add `ip` to `ScaleDownComputeAlert`** (Thread 2 already knows the IP from
   its tracking `_active` dict and can populate it when creating the alert), or
2. **Look up the IP from `_pending_drains`** inside `_handle_cleanup_compute()`
   (if `PendingDrain` carries the IP).

Option 1 is cleaner — add the field:

```python
@dataclass(frozen=True)
class ScaleDownComputeAlert:
    lan:            int
    network_id:     str
    container_name: str
    mac:            str
    ip:             str          # ← NEW: needed for IP release
```

The IP must **not** be released in `_handle_scale_down_compute()` (Phase A)
because the container still holds the IP in its network namespace until
`_handle_cleanup_compute()` (Phase B) performs the actual teardown. Releasing
early would allow a scale-up to allocate the same IP while it's still in use.

Instead, carry the IP through `PendingDrain` and release in Phase B:

```python
# Add ip field to PendingDrain:
@dataclass
class PendingDrain:
    lan:            int
    container_name: str
    mac:            str
    ip:             str          # ← NEW: carried from ScaleDownComputeAlert
    veth_host:      str
    drain_signaled: bool
```

```python
def _handle_cleanup_compute(self, alert: CleanupComputeAlert) -> None:
    pending = self._pending_drains.get(alert.mac)
    if pending is None:
        return
    # ... existing cleanup logic ...
    result = self._compute_adder.cleanup_compute_node(pending)
    del self._pending_drains[alert.mac]
    # Release IP only after container is fully torn down
    self._get_allocator(pending.lan).release(pending.ip)
```

---

## Phase B — Conditional Cleanup (skip for fresh containers)

### Current flow (wasteful)

`_docker_run_storage()` **always** calls `_cleanup_container()` before
`docker run`, even for container names that have never existed:

```python
# storage_node_manager.py — current
def _docker_run_storage(self, name, rs_name, port, lan):
    state = self._container_state(name)
    if state == "running":
        return True, "", ""
    # Always clean up — even if the container doesn't exist
    self._cleanup_container(name)   # 3 docker commands: stop + rm + volume rm
    cmd = ["docker", "run", ...]
    return self._run_cmd(cmd)
```

This wastes 1.5–4 s per fresh add (three docker commands that return "not found").

### Proposed flow

Only call `_cleanup_container()` when the container actually exists:

```python
# storage_node_manager.py — proposed
def _docker_run_storage(self, name, rs_name, port, lan):
    state = self._container_state(name)
    if state == "running":
        logger.info("[node_add] container %s already running — skipping docker run", name)
        return True, "", ""
    if state is not None:
        # Container exists in a non-running state — clean up stale remnants
        logger.info("[node_add] removing stale container %s (state=%s)", name, state)
        self._cleanup_container(name)
    # else: container doesn't exist — nothing to clean up
    cmd = [
        "docker", "run", "-dit",
        "--network", "none",
        "--name", name,
        "-v", f"{name}-data:/data/db",
        "-e", f"LAN_ID=lan{lan}",
        "-e", f"MONGO_REPLSET={rs_name}",
        "-e", f"MONGO_PORT={port}",
        "-e", f"CONTAINER_NAME={name}",
        "edge_storage_server",
    ]
    return self._run_cmd(cmd)
```

> **Note:** `compute_node_manager.py` (`_docker_run_server`) already implements
> this pattern — it only calls `_cleanup_container()` when `state is not None`.
> The fix is storage-only.

---

## Phase C — Split Storage Script (remove SECONDARY wait)

### Current flow

`add_network_storage_node.sh` calls `ensure_rs_secondary()` after `rs.add()`,
which polls up to 10 × 3 s = 30 s:

```bash
# add_network_storage_node.sh — ensure_rs_secondary() (current)
ensure_rs_secondary() {
    local host="$1" port="$2" retries=10 delay=3
    for ((i=1; i<=retries; i++)); do
        state=$(docker exec "$PRIMARY" mongosh --quiet --port="$port" --eval \
            "var m=rs.status().members.find(m=>m.name==='$host:$port'); print(m?m.stateStr:'UNKNOWN')")
        if [[ "$state" == "SECONDARY" ]]; then
            log "Member $host:$port reached SECONDARY after $i check(s)"
            return 0
        fi
        log "Waiting for $host:$port to become SECONDARY (attempt $i/$retries, state=$state)"
        sleep "$delay"
    done
    log "WARNING: $host:$port did not reach SECONDARY after $retries retries"
    return 1
}
```

### Proposed flow

Remove the `ensure_rs_secondary` call from `main()`. After `rs.add()` succeeds,
the script returns immediately. The sidecar inside the container will notify the
controller when SECONDARY is reached (Phase D).

```bash
# add_network_storage_node.sh — main() change (before → after)

# BEFORE:
rs_add_member "$IP" "$PORT" "$PRIMARY" "$PRIMARY_PORT"
ensure_rs_secondary "$IP" "$PORT"   # ← blocks 10-30s

# AFTER:
rs_add_member "$IP" "$PORT" "$PRIMARY" "$PRIMARY_PORT"
log "rs.add() complete — SECONDARY detection deferred to sidecar"
# ensure_rs_secondary removed — sidecar will emit rs_secondary_ready event
```

The `ensure_rs_secondary()` function definition is kept in the script for
manual/debugging use but is no longer called from `main()`.

**Impact:** `net_attach` drops from 32–164 s to ~3–5 s (veth + OVS + rs.add).

---

## Phase D — Sidecar SECONDARY Event

### Context

The storage sidecar (`mongo_telemetry.py`) already polls `replSetGetStatus()`
every 2 s via `_repl_lag_s()` and knows the node's `stateStr`. It has a ZMQ
PUSH socket connected to the aggregator.

### Why a blocking startup loop

Until the replica reaches `SECONDARY`, it **cannot serve reads** — any MongoDB
call from an edge server routed to it would fail. The sidecar also cannot
produce meaningful telemetry (opcounters, replication lag) while the node is
in `STARTUP2` or `RECOVERING`. Therefore the sidecar must **block on startup**
until the node reaches either `SECONDARY` or `PRIMARY`, and only then enter
the normal telemetry loop. The `rs_secondary_ready` event is emitted **only**
for `SECONDARY` nodes — the PRIMARY is already in the VIP pool via static
topology setup.

### Proposed change

Replace the current `main()` entry point with a two-phase startup:

1. **`_wait_for_ready()`** — blocking loop that polls `replSetGetStatus()`
   every `INTERVAL_S` seconds. When `stateStr` is `SECONDARY` or `PRIMARY`
   for the local member, it emits the event (SECONDARY only) and returns.
2. **Normal telemetry loop** — the existing `_push_stats()` cycle, unchanged.

> **Why PRIMARY must also pass:** The `edge_storage_server` image runs
> `mongo_telemetry.py` in **every** storage container, including the PRIMARY
> (`edge_storage_server_n1`, `edge_storage_server_n2`). If we only wait for
> `SECONDARY`, the PRIMARY sidecar would loop forever and never emit telemetry.

```python
# mongo_telemetry.py — new blocking startup function

_READY_STATES = frozenset({"SECONDARY", "PRIMARY"})

def _wait_for_ready() -> None:
    """Block until this node reaches SECONDARY or PRIMARY state.

    Called once at sidecar startup, before the normal telemetry loop.
    Until the node is ready, telemetry is meaningless.
    Only SECONDARY nodes emit the rs_secondary_ready event (PRIMARY is
    already in the VIP pool via static topology).
    """
    container_name = os.environ.get("CONTAINER_NAME", "unknown")
    logger.info("Waiting for a ready replica-set state before starting telemetry...")
    while True:
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
            try:
                status = client.admin.command("replSetGetStatus")
            finally:
                client.close()

            for member in status.get("members", []):
                if member.get("self") and member.get("stateStr") in _READY_STATES:
                    state_str = member["stateStr"]
                    if state_str == "SECONDARY":
                        event = {
                            "event_type": "rs_secondary_ready",
                            "server_id":  _get_server_mac(),
                            "container":  container_name,
                            "ts":         time.time(),
                        }
                        logger.info(
                            "SECONDARY reached — emitting rs_secondary_ready (mac=%s)",
                            _get_server_mac(),
                        )
                        _sock.send_json(event, zmq.NOBLOCK)
                    else:
                        logger.info("PRIMARY detected — skipping rs_secondary_ready event")
                    return
        except Exception as exc:
            logger.debug("Not ready yet: %s", exc)

        time.sleep(INTERVAL_S)
```

Updated `main()`:

```python
def main() -> None:
    logger.info("mongo_telemetry starting: mac=%s interval=%.1fs",
                _get_server_mac(), INTERVAL_S)
    _wait_for_ready()           # blocks until SECONDARY or PRIMARY
    logger.info("Replica ready — entering normal telemetry loop")
    while True:
        try:
            _push_stats()
        except Exception as exc:
            logger.info("Unexpected error in _push_stats: %s", exc)
        time.sleep(INTERVAL_S)
```

> **Key difference from an in-loop approach:** `_push_stats()` is never called
> while the node is in `STARTUP2`/`RECOVERING`. No spurious heartbeats or
> `mongo_stats` events reach the aggregator before the node is ready to serve.
> The `_secondary_announced` flag and `_check_secondary_ready()` helper from
> the earlier design are no longer needed — the blocking startup handles both
> detection and emission before the normal loop ever starts.
>
> **Note on HOSTNAME:** Docker sets `HOSTNAME` to the truncated container ID,
> not the `--name`. We pass the container name explicitly via
> `-e CONTAINER_NAME={name}` in the `docker run` command (see Phase A changes
> to `storage_node_manager.py` / `compute_node_manager.py`).

### Event schema

```json
{
    "event_type": "rs_secondary_ready",
    "server_id":  "00:00:00:00:01:05",
    "container":  "edge_storage_lan1_dyn1",   // from CONTAINER_NAME env var
    "ts":         1744400000.123
}
```

### Behaviour for pre-existing (static) storage nodes

Static storage nodes are already `PRIMARY` when the sidecar starts.
`_wait_for_ready()` will detect this on the first poll (~2 s) and emit
`rs_secondary_ready` immediately. Since these nodes are already in the VIP pool
via the static topology setup, the event is harmless — `_process_secondary_events`
will log a warning ("unknown mac") and ignore it, because the MAC is not in
`_active` (only dynamic nodes are tracked there).

---

## Phase E — Aggregator Fast-Path

### Context

The aggregator already has a fast-path for `drain_complete` — it publishes an
immediate mini-summary with `control_events=[event]`, bypassing the 10 s
aggregation window:

```python
# aggregator.py — current fast-path
def _receive_loop():
    while True:
        event = pull.recv_json()
        if event.get("event_type") == "drain_complete":
            mini = {
                "network_id":      NETWORK_ID,
                "window_end":      time.time(),
                "servers":         {},
                "storage_servers": {},
                "control_events":  [event],
            }
            pub.send_json(mini)
            continue
        with _lock:
            _buffer.append(event)
```

### Proposed change

Extend the condition to include `rs_secondary_ready`:

```python
# aggregator.py — proposed
def _receive_loop():
    while True:
        event = pull.recv_json()
        etype = event.get("event_type")

        if etype in ("drain_complete", "rs_secondary_ready"):
            mini = {
                "network_id":      NETWORK_ID,
                "window_end":      time.time(),
                "servers":         {},
                "storage_servers": {},
                "control_events":  [event],
            }
            logger.info("%s received for server_id=%s — publishing mini-summary",
                        etype, event.get("server_id"))
            pub.send_json(mini)
            continue

        with _lock:
            _buffer.append(event)
```

No changes to the `TelemetrySummary` model — `control_events: list[dict]`
already accepts arbitrary event dicts.

---

## Phase F — Deferred VIP Registration

### Current flow

Thread 3 registers the storage node in the VIP pool **immediately** after
`add_storage_node()` returns:

```python
# elasticity.py — _handle_data() (current)
if result.success and result.ip:
    if result.mac:
        self._topo.add_storage_mac(result.mac, domain=f"n{alert.lan}")    # ← VIP pool
        self._topo.register_backend_ip(result.mac, result.ip)              # ← IP↔MAC table
        # ... NodeInfo push to _addition_complete_infos ...
```

With Phase C (SECONDARY wait removed), the node is **not yet SECONDARY** when
`add_storage_node()` returns. Routing traffic to it now would hit a
`STARTUP2`/`RECOVERING` member that cannot serve reads.

### Proposed flow — Thread 3 side

Remove `add_storage_mac()` from `_handle_data()`. Keep `register_backend_ip()`
(harmless pre-seeding of the IP↔MAC lookup table):

```python
# elasticity.py — _handle_data() (proposed)
if result.success and result.ip:
    if result.mac:
        # Pre-seed IP↔MAC table so Thread 1 has the mapping ready
        # when the node eventually enters the VIP pool.
        self._topo.register_backend_ip(result.mac, result.ip)

        # Do NOT call add_storage_mac() here — the node is not SECONDARY yet.
        # VIP registration is deferred until rs_secondary_ready arrives (Phase F).
        logger.info(
            "[elasticity] data: %s online  ip=%s  mac=%s  (VIP deferred until SECONDARY)",
            name, result.ip, result.mac,
        )

        info = NodeInfo(
            mac=result.mac, lan=alert.lan, network_id=alert.network_id,
            name=name, ip=result.ip, node_type="storage",
            rs_name=alert.rs_name,
            primary_container=alert.primary_container,
            port=alert.port,
        )
        with self._addition_complete_lock:
            self._addition_complete_infos.append(info)
```

### Proposed flow — Thread 2 side (controller)

New method in `main_n1.py` and `main_n2.py`, called from `_on_telemetry_update()`
right after `_process_drain_events()`:

```python
def _process_secondary_events(self, summary: TelemetrySummary) -> None:
    """Handle rs_secondary_ready control events — add storage node to VIP pool."""
    for event in summary.control_events:
        if event.get("event_type") == "rs_secondary_ready":
            mac = event.get("server_id")
            if not mac:
                continue
            info = self._active.get(mac)
            if info is None:
                logger.warning(
                    "[scale-up] rs_secondary_ready for unknown mac=%s — ignoring", mac)
                continue
            if info.node_type != "storage":
                logger.warning(
                    "[scale-up] rs_secondary_ready for non-storage mac=%s — ignoring", mac)
                continue

            # NOW add to VIP storage pool — node is confirmed SECONDARY
            self.add_storage_mac(mac, domain=f"n{info.lan}")
            logger.info(
                "[scale-up] rs_secondary_ready received for mac=%s — "
                "added to VIP storage pool (ip=%s, name=%s)",
                mac, info.ip, info.name,
            )
```

### Integration in `_on_telemetry_update()`

```python
def _on_telemetry_update(self, summary: TelemetrySummary) -> None:
    if summary.network_id != self._lan_id:
        return

    self._sync_node_tracking()           # Thread 3 → Thread 2 NodeInfo transfer
    self._process_drain_events(summary)   # existing: drain_complete → CleanupComputeAlert
    self._process_secondary_events(summary)  # NEW: rs_secondary_ready → add_storage_mac

    if not summary.servers and not summary.storage_servers:
        return

    # ... rest unchanged (log stats, detect absent, evaluate scale) ...
```

### Timing safety

`_sync_node_tracking()` runs **before** `_process_secondary_events()`. Since
`add_storage_node()` now completes in ~5 s and SECONDARY transition takes 5–30 s,
the `NodeInfo` will be in `self._active` long before `rs_secondary_ready` arrives.

---

## Files Changed

| File                                                         | Phase | Change                                                                                                                                                                                               |
| ------------------------------------------------------------ | ----- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `source/sdn_controller/elasticity/node_common.py`          | A     | Add `IpAllocator` class                                                                                                                                                                            |
| `source/sdn_controller/elasticity/elasticity.py`           | A, F  | Add `_ip_allocs` dict + `_get_allocator()`; use in `_handle_data` and `_handle_compute`; release on removal (data + compute); remove `add_storage_mac` from `_handle_data`               |
| `source/sdn_controller/elasticity/storage_node_manager.py` | A, B  | Accept `ip`/`mac` params → pass `--ip`/`--mac` to script; add `-e CONTAINER_NAME={name}` to docker run; conditional cleanup                                                               |
| `source/sdn_controller/elasticity/compute_node_manager.py` | A     | Accept `ip`/`mac` params → pass `--ip`/`--mac` to script; add `-e CONTAINER_NAME={name}` to docker run; add `ip` field to `PendingDrain`; release IP in `_handle_cleanup_compute()` |
| `source/scripts/network/add_network_storage_node.sh`       | A, C  | Skip `collect_used_ips` when `--ip`/`--mac` provided; remove `ensure_rs_secondary` call from `main()`                                                                                      |
| `source/scripts/network/add_network_node.sh`               | A     | Skip `collect_used_ips` when `--ip`/`--mac` provided                                                                                                                                           |
| `source/docker/edge_storage_server/mongo_telemetry.py`     | D     | Add `_wait_for_ready()` blocking startup (PRIMARY + SECONDARY); one-shot `rs_secondary_ready` event for SECONDARY only                                                                           |
| `source/docker/local_state_server/aggregator.py`           | E     | Extend fast-path to include `rs_secondary_ready`                                                                                                                                                   |
| `source/sdn_controller/main_n1.py`                         | F     | Add `_process_secondary_events()`; call from `_on_telemetry_update()`                                                                                                                            |
| `source/sdn_controller/main_n2.py`                         | F     | Same as `main_n1.py`                                                                                                                                                                               |

**Reference only (no changes):**

| File                                              | Reason                                                                     |
| ------------------------------------------------- | -------------------------------------------------------------------------- |
| `source/sdn_controller/telemetry/models.py`     | `TelemetrySummary.control_events` already supports arbitrary event dicts |
| `source/sdn_controller/telemetry/zmq_source.py` | Mini-summary handling already works (triggers `on_update` callback)      |
| `source/sdn_controller/vip_routing.py`          | `register_backend_ip()` API unchanged                                    |
| `source/sdn_controller/topology/topology.py`    | `add_storage_mac()` / `_rebuild_vip_pools()` API unchanged             |

---

## Execution Order

```
Phase A (IP alloc)          ─┐
Phase B (cond. cleanup)     ─┤  all independent / parallel
Phase D (sidecar event)     ─┘
                              │
Phase C (rm SECONDARY wait) ─── depends on D (sidecar must detect SECONDARY)
Phase E (aggregator)        ─── depends on D (event format defined)
                              │
Phase F (deferred VIP)      ─── depends on C + D + E (fast return + event flow)
```

**Recommended:** A + B + D in parallel → C + E in parallel → F.

---

## Verification

| Test     | What to check                                                                                                                                               |
| -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Phase A  | Add a storage node → script receives `--ip`/`--mac`, no `collect_used_ips` output, completes in <5 s                                                 |
| Phase B  | Fresh container name → no "Stopping container" / "Removing container" in logs; existing name → cleanup happens                                            |
| Phase C  | Storage add returns after `rs.add()` without SECONDARY wait; total ~3–5 s                                                                                |
| Phase D  | Sidecar logs (`docker logs <storage>`) show `rs_secondary_ready` emitted once when `stateStr` becomes `SECONDARY`                                   |
| Phase E  | Aggregator logs show immediate forwarding (not buffered for 10 s)                                                                                           |
| Phase F  | Controller logs:`[scale-up] rs_secondary_ready received for mac=X — added to VIP storage pool`; node receives traffic **only after** this log line |
| Full run | `net_attach` ~3–5 s (down from 32–164 s); fewer total dynamic nodes spawned; no 503s from non-ready replicas                                            |

---

## Decisions

| Decision                                      | Rationale                                                                                                       |
| --------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| No node caps                                  | Fast adds naturally prevent runaway scaling; caps can be trivially added later in `_evaluate_scale_up()`      |
| IP range `.2–.29` (28 slots/LAN)           | Matches existing convention in `create_test_clients.sh` (`.30+` for test clients)                           |
| No IP persistence                             | Controller restart invalidates experiment; one-time startup scan can be added later                             |
| MAC derived from IP                           | Pure function `00:00:00:00:{lan:02x}:{suffix:02x}` — no separate allocation needed                           |
| `register_backend_ip()` still from Thread 3 | Harmless pre-seeding; ensures IP↔MAC ready when VIP membership is granted                                      |
| `ensure_rs_secondary()` kept as function    | Available for manual debugging / standalone script usage                                                        |
| 3 Docker images need rebuild                  | `edge_storage_server` (D), `local_state_server` (E), `os-ken` (A+F — used by both n1 and n2 controllers) |

---

## Data Flow — Before vs. After

### Before (current)

```
Thread 3                          Shell script                    Sidecar
   │                                   │                            │
   ├─ docker run ─────────────── 2-4s  │                            │
   ├─ add_network_storage_node.sh ────►│                            │
   │                                   ├─ collect_used_ips ── 5-20s │
   │                                   ├─ veth + OVS ──────── 2-3s  │
   │                                   ├─ rs.add() ────────── 1-2s  │
   │                                   ├─ ensure_rs_secondary 10-30s│
   │                              ◄────┤                            │
   ├─ add_storage_mac() ──── VIP pool  │                            │
   ├─ register_backend_ip()            │                            │
   │                                   │                            │
   │  ═══ 32–164s total ═══           │                            │
```

### After (proposed)

```
Thread 3               Shell script          Sidecar              Aggregator   Thread 2
   │                        │                   │                     │            │
   ├─ ip_alloc.allocate()   │                   │                     │            │
   ├─ docker run ───── 2-4s │                   │                     │            │
   ├─ script --ip --mac ───►│                   │                     │            │
   │                        ├─ veth+OVS ── 2-3s │                     │            │
   │                        ├─ rs.add() ── 1-2s │                     │            │
   │                   ◄────┤                   │                     │            │
   ├─ register_backend_ip() │                   │                     │            │
   ├─ push NodeInfo         │                   │                     │            │
   │                        │                   │                     │            │
   │  ═══ 5-8s total ═══   │                   │                     │            │
   │                        │                   │                     │            │
   │                        │            (5-30s later)                │            │
   │                        │                   ├─ stateStr=SECONDARY │            │
   │                        │                   ├─ rs_secondary_ready─►            │
   │                        │                   │                     ├─ mini-sum──►│
   │                        │                   │                     │            ├─ add_storage_mac()
   │                        │                   │                     │            │  VIP pool ✓
```
