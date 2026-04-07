# Graceful Node Removal — Implementation Plan

## Overview

Add graceful scale-down to the elasticity system. Symmetrical to Thread 3's
node addition, removal goes through the same orchestration layers:
`ElasticityManager` (policy + sequencing) → `NodeAdder` (lifecycle steps) →
shell scripts (low-level OVS/Docker operations).

The removal uses a **self-removal model**: the controller isolates the node from
the VIP pool, signals it to drain, and the container exits itself once idle.
The controller then cleans up OVS/veth/flows via the existing shell scripts.

**Compute removal is asynchronous (two-phase):** Thread 3 executes Phase A
(<1 s) — remove from VIP, discover veth via `nsenter`, send drain signal via
`docker exec curl /drain`, store a `PendingDrain` record — and returns
immediately. Phase B fires when the container sends a `drain_complete` ZMQ
event (or after a telemetry timeout fallback): Thread 3 runs the cleanup
script to remove OVS ports, flows, and the container. This avoids blocking
Thread 3 for the unbounded duration of in-flight request completion.

**Storage removal stays synchronous:** all storage operations are server-side
and bounded (~50 s worst case). There is no drain concept for mongod — only
`rs.remove()` via primary.

Two independent triggers can initiate removal:

- **Telemetry timeout** — dynamic node absent from 10 consecutive telemetry
  windows → assumed dead.
- **Underutilization** — CPU and latency metrics below scale-down thresholds for **9 consecutive windows** → healthy but idle.

Only **dynamically added** nodes are eligible — static servers and primary DB
containers are never removed.

---

## Removal Triggers

### Trigger A — Telemetry Timeout (Dead Node Detection)

**Where:** `source/sdn_controller/main_n1.py` — inside `_on_telemetry_update()`

```python
# In _on_telemetry_update():
for mac in self._dynamic_node_macs:
    if mac in summary.servers or mac in summary.storage_servers:
        self._absent_window_count[mac] = 0
    else:
        self._absent_window_count[mac] = self._absent_window_count.get(mac, 0) + 1
        if self._absent_window_count[mac] >= self._telemetry_timeout_windows:
            log.debug("Telemetry timeout for dynamic node %s (%d absent windows)",
                        mac, self._absent_window_count[mac])
            self._submit_scale_down_alert(mac)
```

Track per-MAC absent-window counters. Each time a `TelemetrySummary` arrives:

- Dynamic MACs **present** in the summary → reset counter to 0.
- Dynamic MACs **absent** → increment counter.
- Counter reaches `TELEMETRY_TIMEOUT_WINDOWS` → submit removal alert.

Using **window count** (not wall-clock seconds) adapts automatically if
`WINDOW_S` changes — semantically "10 consecutive windows without hearing from
this node" is more correct than a fixed duration.

| Env var                       | Default | Description                   |
| ----------------------------- | ------- | ----------------------------- |
| `TELEMETRY_TIMEOUT_WINDOWS` | `10`  | Absent windows before removal |

### Trigger B — Underutilization (Healthy Nodes)

**Where:** `source/sdn_controller/main_n1.py` — inside `_on_telemetry_update()`

Scale-down evaluates **two tiers independently**, each with its own
consecutive-window counter. A tier scales down only when **both** its CPU
and latency are below their respective thresholds — the AND condition
prevents false positives:

| CPU state | Latency state | Meaning                                          | Action               |
| --------- | ------------- | ------------------------------------------------ | -------------------- |
| High      | High          | System saturated, users affected                 | (scale-up territory) |
| High      | Low           | Working hard but keeping up                      | Do nothing           |
| Low       | High          | Large query / data-bound operation, not capacity | Do nothing           |
| Low       | Low           | System truly idle                                | Scale down candidate |

Latency alone is ambiguous because `avg_time_db_ms` is measured at the edge
server as the pymongo round-trip. A query returning a large result set takes
longer regardless of how many storage nodes exist — VIP routes the entire
request to **one** node. The latency is data-bound, not capacity-bound.
Same applies to `avg_time_proc_ms`. CPU removes this ambiguity: if latency
is high but CPU is low, the system has spare capacity and the latency is
inherent to the workload.

#### Compute scale-down

| Env var                            | Default | Description                                          |
| ---------------------------------- | ------- | ---------------------------------------------------- |
| `TAU_CPU_DOWN`                   | `20`  | Domain avg CPU % below → idle                       |
| `TAU_PROC_DOWN_MS`               | `100` | Domain avg processing latency below → idle          |
| `SCALE_DOWN_COMPUTE_CONSECUTIVE` | 9       | Consecutive windows below threshold (4.5× scale-up) |

```python
# Compute scale-down evaluation
if (summary.domain.average_cpu_percent < self._tau_cpu_down
        and summary.domain.avg_time_proc_ms < self._tau_proc_down_ms):
    self._scale_down_compute_consecutive += 1
else:
    self._scale_down_compute_consecutive = 0

if self._scale_down_compute_consecutive >= self._scale_down_compute_required:
    last = self._find_last_dynamic_compute_node()
    if last is not None:
        self._submit_scale_down_alert(last.mac)
        self._scale_down_compute_consecutive = 0
```

#### Storage scale-down

The aggregator computes the domain-average storage CPU from individual
`StorageServerSummary.avg_cpu_percent` entries and publishes it as
`DomainSummary.avg_storage_cpu_percent`. The controller reads the field
directly — no helper method needed.

| Env var                            | Default   | Description                                          |
| ---------------------------------- | --------- | ---------------------------------------------------- |
| `TAU_STORAGE_CPU_DOWN`           | `20`    | Domain avg storage CPU % below → idle               |
| `TAU_DB_DOWN_MS`                 | `50000` | Domain avg DB latency below → idle                  |
| `SCALE_DOWN_STORAGE_CONSECUTIVE` | 9         | Consecutive windows below threshold (4.5× scale-up) |

```python
# Storage scale-down evaluation
if (summary.domain.avg_storage_cpu_percent < self._tau_storage_cpu_down
        and summary.domain.avg_time_db_ms < self._tau_db_down_ms):
    self._scale_down_storage_consecutive += 1
else:
    self._scale_down_storage_consecutive = 0

if self._scale_down_storage_consecutive >= self._scale_down_storage_required:
    last = self._find_last_dynamic_storage_node()
    if last is not None:
        self._submit_scale_down_alert(last.mac)
        self._scale_down_storage_consecutive = 0
```

**Constraints:**

Production autoscalers (Kubernetes HPA, AWS Auto Scaling) follow a common
pattern: **scale up fast, scale down slow**. K8s HPA uses a 5-minute
stabilization window for scale-down vs 0 s for scale-up. AWS defaults to
300 s cooldown for scale-down vs 60 s for scale-up. The shared principles
are: serialization (one operation at a time), asymmetric timing, and
sustained signal (not momentary dips).

Our system achieves the same protection **without an explicit cooldown
timer**, relying instead on three interlocking mechanisms:

- **`is_busy()`** freezes all scaling evaluation for the entire duration of
  an add/remove operation (30–180 s). No alerts can stack.
- **Consecutive windows** force a sustained signal — 9 windows (90 s) for
  scale-down, 2 windows (20 s) for scale-up — starting from a *fresh*
  counter after any opposing event.
- **Cross-direction reset** zeroes the opposing tier’s counter, so after a
  scale-up the system needs 9 genuinely idle windows before scale-down can
  fire, and vice versa.

Together these make an explicit cooldown redundant:

| Scenario                         | What happens                                                                                                                           |
| -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Scale-up → immediate scale-down | Counter was reset to 0 by the scale-up. Needs 9 fresh idle windows (90 s). Not a risk.                                                 |
| Scale-down → immediate scale-up | Counter was reset to 0 by the scale-down. Needs 2 fresh saturated windows. If load is genuinely that high, scaling back up is correct. |
| Scale-up → another scale-up     | `is_busy()` blocks during the 30–60 s operation. Then needs 2 fresh windows. Only fires if load is genuinely still saturated.       |

The remaining constraints:

1. **Minimum node count** — never scale below the initial static nodes.
2. **Consecutive windows** — scale-up requires 2 consecutive windows above
   threshold before firing. Scale-down is always **4.5× the scale-up window**
   = 9 consecutive windows below threshold. Each tier tracks its own
   counter independently.
3. **Dual condition (CPU AND latency)** — both must be below threshold
   simultaneously. CPU captures capacity saturation; latency confirms user
   impact. Neither alone is sufficient (see truth table above).
4. **LIFO** — remove the most recently added dynamic node of the relevant
   tier (compute or storage).
5. **Operation serialization** — `ElasticityManager` exposes an `is_busy()`
   flag. Thread 2 skips **all** scaling evaluation (both up and down) while
   Thread 3 is executing an operation. This is the same pattern as AWS Auto
   Scaling, which blocks new scaling activities while one is in progress.
   No conflicting decisions can stack in the queue.
6. **Counter reset on opposing event or empty set** — when a scale-up alert
   is submitted for a tier, that tier's `_scale_down_*_consecutive` counter
   is reset to 0 (and vice versa). The system needs 9 *fresh* windows of
   genuinely low metrics after the new node is integrated before considering
   scale-down. Additionally, if the counter reaches the threshold but no
   eligible dynamic node exists, the counter is also reset to 0 — there is
   nothing to remove, so accumulated windows are discarded rather than
   carried forward.

### Scope Guards

```python
# Populated on add, cleared on remove
self._dynamic_node_macs: set[str] = set()

# Only dynamic MACs are eligible for removal
def _submit_scale_down_alert(self, mac: str) -> None:
    if mac not in self._dynamic_node_macs:
        return  # static/primary — never touch
    op = self._find_operation_by_mac(mac)
    if op is None:
        return
    # Build and submit the appropriate alert from the stored NodeResult
    ...
```

---

## Removal Workflow

Both triggers produce the same alert types and feed into the same workflow.

### Compute (`edge_server`) Removal — Async Two-Phase

```
Phase A — _handle_scale_down_compute(alert):         [Thread 3, <1 s]

1. remove_server_mac(mac)           ← immediate; Thread 1 stops routing to this node
2. discover veth via nsenter        (container still running, netns alive)
3. store PendingDrain(mac, veth, name, lan, ts)
4. docker exec curl -X POST /drain (drain signal)
   ├─ 200 → container will self-exit after in-flight complete
   └─ Fails → node is dead, submit CleanupComputeAlert immediately
5. RETURN                           ← Thread 3 is free for other operations
```

```
Phase B — _handle_cleanup_compute(alert):            [Thread 3, ~5–10 s]
   Triggered by: drain_complete ZMQ event  OR  telemetry timeout fallback

1. lookup PendingDrain by mac
2. docker stop --time 5 <name>      (safety net — should already be exited)
3. flush MAC flows                   (del-flows dl_src/dl_dst)
4. remove_network_node.sh --lan <N> --name <name>   (no --graceful)
   ├─ ovs-vsctl del-port + ip link del
   └─ docker rm
5. delete PendingDrain entry
```

```
Fallback — telemetry timeout:
   Container crashes / drain_complete never arrives
   → 10 absent windows (100 s) → timeout handler checks has_pending_drain(mac)
   → if pending: submit CleanupComputeAlert (skip Phase A)
   → if not pending: submit ScaleDownComputeAlert as normal
```

**Why two-phase async:** The synchronous approach blocks Thread 3 for the
unbounded duration of in-flight request completion. With `maxPoolSize=1` and
Flask `threaded=True`, a single slow request (large payload, network delay)
can hold Thread 3 for minutes. During that time, no other scaling operations
can execute. The async split keeps Phase A under 1 s and frees Thread 3
immediately.

**Why veth discovery happens in Phase A:** The script needs the container
**running** to discover the veth/MAC via `nsenter` into its network namespace.
If we waited for the container to exit first (via `os._exit(0)` after drain),
the netns would be gone and veth discovery would fail — OVS ports and veth
pairs would leak. By discovering in Phase A (container still alive) and
storing the result in `PendingDrain`, Phase B can clean up without `nsenter`.

**Why self-exit works:** with `maxPoolSize=1` per LAN and Flask `threaded=True`,
active requests complete naturally. The `/drain` endpoint:

- Sets `_draining = True`
- `before_request` returns 503 for new requests
- Drain monitor sends `drain_complete` ZMQ event + checks every 0.5 s
- Exits via `os._exit(0)` when `active_requests == 0`

**drain_complete signaling:** Before exit, the drain monitor sends a
`drain_complete` event through the existing ZMQ PUSH pipeline (same as
telemetry events). The aggregator passes it through as a `control_events`
entry in the published summary. The controller's SUB handler receives it and
submits a `CleanupComputeAlert` to Thread 3's queue.

### Storage (`edge_storage_server`) Removal

```
ElasticityManager._handle_scale_down_data(alert):

1. remove_storage_mac(mac, domain)  ← immediate; no new VIP DNAT flows installed
2. rs.remove(IP:PORT) via primary   ← member leaves RS, stops replicating  [Python]
   └─ Poll rs.status() until member gone (max 10 retries × 3s)
3. remove_network_storage_node.sh --lan <N> --name <name> --skip-rs          [script]
   └─ flush DNAT flows (dl_src/dl_dst) ← break any surviving connections
   └─ docker stop --time 15            ← SIGTERM + MongoDB quiesce (safety net)
   └─ OVS port + veth + docker rm + volume rm
```

**Why active flow flush instead of passive idle wait:**

The previous approach waited `MAX_IDLE_MS` (30 s) for edge-server connections
to close via `maxIdleTimeMS`. This **only works if the connection goes idle**.
Under sustained load, the edge server keeps querying through its existing
pymongo connection → packets keep flowing → the OVS DNAT flow's `idle_timeout`
never expires → `maxIdleTimeMS` never triggers → the connection stays alive
indefinitely. The storage node would never become safe to remove.

Flushing the DNAT flows **actively breaks the network path**. The edge
server's next pymongo operation gets a `ConnectionFailure` / `AutoReconnect`
→ pymongo reconnects to VIP → a new DNAT flow is installed pointing to a
different (healthy) storage node. The one in-flight query may fail, but the
edge server retries and the response is only slightly delayed.

With `directConnection=True` and `maxPoolSize=1`, only **one operation** can
be in-flight per LAN per edge server. The write either completed at MongoDB
before the flow was flushed, or it didn't — no partial state.

**Why the flush is a no-op in the normal underutilization path — but still
necessary for the telemetry timeout path:**

DNAT flows are installed with `VIP_IDLE_TIMEOUT = 30 s`. Scale-down via
underutilization requires **9 consecutive windows × 10 s = 90 s** of metrics
below threshold. By the time the removal fires, the DNAT flows to this node
have been expired by OVS for at least **60 s** — no edge server has had a
routable path to this mongod for over a minute, so no active connection can
exist. The flush step is structurally always executed but functionally a no-op.

The **telemetry timeout** path (dead node detection, 10 absent windows = 100 s)
is different: a node can die suddenly with in-flight traffic. Its DNAT flows
may not have expired cleanly (e.g., node crash mid-packet). The flush there
is genuinely defensive.

| Trigger                                  | Flows at removal time                  | Flush necessity  |
| ---------------------------------------- | -------------------------------------- | ---------------- |
| Underutilization (9 × 10 s = 90 s idle) | Already expired — idle_timeout = 30 s | Defensive no-op  |
| Telemetry timeout (dead node)            | May exist if node died suddenly        | Genuinely needed |

**Why `rs.remove()` is safe after flow flush:**

Once the DNAT flows are flushed, no edge server can reach this mongod through
the OVS data path. Any reconnection attempt goes through VIP and gets routed
elsewhere. So by the time `rs.remove()` executes, the node has no application
clients — only internal RS heartbeat connections (which `rs.remove()` handles
natively).

A `REMOVED` mongod **refuses writes** on the server side. If we `rs.remove()`
before flushing flows, edge servers with active connections would get write
errors. By flushing first, we guarantee no client is connected when the RS
membership changes.

**Why NOT `connections_current`:** unreliable — background connections from the
telemetry sidecar's periodic `serverStatus()` calls (every 2 s), internal RS
heartbeats, and mongosh sessions keep the count at 4–7 even when truly idle
from the application perspective:

```json
{"msg":"Connection accepted","attr":{"remote":"127.0.0.1:55940","connectionCount":6}}
{"msg":"Connection ended","attr":{"remote":"127.0.0.1:55940","connectionCount":5}}
{"msg":"Connection accepted","attr":{"remote":"10.0.0.4:53674","connectionCount":6}}
```

**Why `docker stop --time 15` is a safety net:**

MongoDB 5.0+ SIGTERM triggers a quiesce period: `mongod` finishes in-progress
operations, rejects new connections, then exits cleanly. The `--time 15` gives
MongoDB 15 s for this quiesce. After flow flush and `rs.remove()`, there are
no client connections and no RS obligations — so the quiesce completes almost
instantly.

> **Prerequisite — SIGTERM forwarding in `entrypoint.sh`:**
> The `edge_storage_server` container runs `bash` as PID 1, which launches
> `mongod &` in the background. Bash does **not** forward signals to children
> by default, so `docker stop` sends SIGTERM to bash, not to mongod. Without
> a fix, mongod never gets its quiesce — it gets SIGKILL after the timeout.
>
> The entrypoint must add a `trap` to forward SIGTERM:
>
> ```bash
> trap 'kill -TERM $MONGOD_PID; wait $MONGOD_PID' SIGTERM
> ```
>
> See Phase 0 below for the full change.

---

## Phase 0 — Fix SIGTERM Forwarding in Storage Entrypoint

**File:** `source/docker/edge_storage_server/entrypoint.sh`

**Problem:** `entrypoint.sh` (bash) is PID 1. It starts `mongod &` as a
background process. Bash does not forward signals to background children.
When `docker stop` sends SIGTERM, bash receives it but mongod never does.
After `--stop-timeout` expires, Docker sends SIGKILL — unclean shutdown,
journal recovery on restart.

**Fix:** Add a `trap` that forwards SIGTERM to `mongod` and waits for it to
exit cleanly.

### Current entrypoint (relevant section):

```bash
mongod $MONGOD_ARGS &
MONGOD_PID=$!

# ... wait for ready, start sidecar ...

wait $MONGOD_PID
```

### Fixed entrypoint:

```bash
# Forward SIGTERM to mongod so it gets a clean shutdown (quiesce).
# Without this, bash (PID 1) swallows the signal and mongod only
# receives SIGKILL after the container stop timeout expires.
trap 'kill -TERM $MONGOD_PID; wait $MONGOD_PID; exit $?' SIGTERM

mongod $MONGOD_ARGS &
MONGOD_PID=$!

# ... wait for ready, start sidecar ...

# Must use `wait` in a loop for the trap to fire — a single `wait` on
# a specific PID is interrupted by the signal, but bash only runs trap
# handlers between commands.
wait $MONGOD_PID
```

**Key details:**

- `trap` must be defined **before** `mongod &` so the handler is in place
  when the signal arrives.
- `wait $MONGOD_PID` at the end is needed: when SIGTERM arrives during
  `wait`, bash interrupts it, runs the trap handler (which sends TERM to
  mongod and waits for it), then exits with mongod's exit code.
- The sidecar (`mongo_telemetry.py`) runs as a background process and will
  be killed automatically when the container exits.

**This is a prerequisite for all other phases** — without it, `docker stop --time 15` in the storage removal workflow has no effect on mongod.

---

## Phase 1 — Edge Server Drain Endpoint

**File:** `source/docker/edge_server/source/app.py`

### Changes

1. **Module-level state:**

```python
_draining = False
_active_requests = 0
_active_requests_lock = threading.Lock()
```

2. **Request counting + drain guard:**

```python
_SKIP_COUNTING = frozenset({"/health", "/drain"})

@app.before_request
def _before_request():
    global _active_requests
    g.counted = False
    if request.path in _SKIP_COUNTING:
        return  # don't count control-plane routes
    if _draining:
        return jsonify({"status": "draining"}), 503
    with _active_requests_lock:
        _active_requests += 1
    g.counted = True   # mark only after successful increment

@app.after_request
def _after_request_count(response):
    global _active_requests
    # Use g.counted (set in before_request) — NOT _draining — to guard the
    # decrement. A request that incremented the counter before _draining was
    # set to True must still decrement when it completes, or _active_requests
    # never reaches 0 and the drain monitor never fires.
    if getattr(g, "counted", False):
        with _active_requests_lock:
            _active_requests -= 1
    return response
```

3. **Drain endpoint:**

```python
@app.route("/drain", methods=["POST"])
def drain():
    global _draining
    _draining = True
    log.info("Drain activated — rejecting new requests, waiting for %d in-flight",
             _active_requests)
    return jsonify({"status": "draining", "active_requests": _active_requests}), 200
```

4. **Drain monitor thread:**

```python
def _drain_monitor():
    """Background thread: sends drain_complete via ZMQ when all in-flight
    requests have finished, then exits the process."""
    while True:
        time.sleep(0.5)
        if _draining and _active_requests == 0:
            log.info("Drain complete — no active requests, sending drain_complete event")
            _metric_sender.send({
                "event_type":  "drain_complete",
                "server_id":   _server_mac,
                "ts":          time.time(),
            })
            time.sleep(0.1)  # flush ZMQ send buffer
            log.info("Exiting via os._exit(0)")
            os._exit(0)

threading.Thread(target=_drain_monitor, daemon=True, name="drain-monitor").start()
```

`os._exit(0)` is used instead of `sys.exit()` to guarantee immediate exit even
if ZMQ or other background threads hold event-loop references.

The `drain_complete` event is sent through the existing ZMQ PUSH socket
(`_metric_sender`) to the aggregator, which passes it through as a
`control_events` entry in the published summary. The controller receives it
via SUB and triggers Phase B cleanup.

**No `/drain/status`** — the controller doesn't need it. The container signals
completion via ZMQ and then exits itself. There's no useful action for the
controller to take between "drain started" and "drain_complete received".

---

## Phase 2 — NodeAdder Removal Methods

**File:** `source/sdn_controller/elasticity/node_manager.py`

### New Dataclasses

```python
@dataclass
class PendingDrain:
    mac:            str
    veth:           str            # "unknown" only if veth discovery failed entirely
    container_name: str
    lan:            int
    initiated_ts:   float
    drain_signaled: bool = True    # False when drain HTTP call failed but veth is known

@dataclass
class RemovalTimings:
    drain_signal_s:    float = 0.0   # time to send drain signal
    drain_wait_s:      float = 0.0   # time waiting for container exit / idle timeout
    network_cleanup_s: float = 0.0   # shell script execution (flow flush + teardown)
    total_s:           float = 0.0   # wall-clock start to finish

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

### `initiate_drain(lan, name, mac) -> PendingDrain | None` — Phase A

```python
def initiate_drain(self, lan: int, name: str, mac: str) -> PendingDrain | None:
    """Phase A: discover veth (needs running container), send drain signal.
    Returns PendingDrain with drain_signaled=True if drain was acknowledged.
    Returns PendingDrain with drain_signaled=False if veth was found but the
    drain HTTP call failed (container dead — caller submits CleanupComputeAlert
    immediately without waiting for drain_complete event).
    Returns None only if veth discovery itself failed (container netns gone)."""

    # Discover veth via nsenter while container is still running
    veth = self._discover_veth(name)
    if veth is None:
        logger.warning("Cannot discover veth for %s — container netns is gone", name)
        return None

    # Send drain signal via docker exec (bypasses OVS data path).
    # Retry up to 3 times — a single transient failure should not abort drain.
    drain_ok = False
    for attempt in range(1, 4):
        ok, _, _, _ = self._run_cmd(
            ["docker", "exec", name, "curl", "-sS", "-X", "POST",
             "http://localhost:5000/drain"],
        )
        if ok:
            drain_ok = True
            break
        logger.warning("Drain attempt %d/3 failed for %s", attempt, name)
        if attempt < 3:
            time.sleep(1.0)

    if not drain_ok:
        logger.warning("All drain attempts failed for %s (veth=%s) — will cleanup immediately",
                       name, veth)
    else:
        logger.info("Drain initiated for %s (veth=%s)", name, veth)

    # Always return PendingDrain when veth is known. drain_signaled=False tells
    # the caller to submit CleanupComputeAlert immediately (no wait for ZMQ event).
    return PendingDrain(
        mac=mac, veth=veth, container_name=name,
        lan=lan, initiated_ts=time.time(),
        drain_signaled=drain_ok,
    )
```

### `cleanup_compute_node(pending: PendingDrain) -> RemovalResult` — Phase B

```python
def cleanup_compute_node(self, pending: PendingDrain) -> RemovalResult:
    """Phase B: stop container, flush flows, remove OVS port/veth, docker rm.
    Called after drain_complete ZMQ event or telemetry timeout fallback.

    The veth was discovered in Phase A (container was running then) and stored
    in PendingDrain. It is passed to the script via --veth so the script can
    skip nsenter discovery (netns is gone once the container has exited).
    The script handles: docker stop (safety net) + flow flush + del-port +
    veth deletion + docker rm — no duplication in Python."""
    timings = RemovalTimings()
    t_total = time.perf_counter()

    t0 = time.perf_counter()
    ok, _, stdout, stderr = self._run_script(
        SCRIPTS_DIR / "remove_network_node.sh",
        ["--lan", str(pending.lan), "--name", pending.container_name,
         "--veth", pending.veth, "--mac", pending.mac],
    )
    timings.network_cleanup_s = time.perf_counter() - t0
    timings.total_s = time.perf_counter() - t_total

    state = NodeOperationState.DONE if ok else NodeOperationState.FAILED
    return RemovalResult(ok, pending.container_name, pending.mac,
                         timings, state, stdout, stderr)
```

### `remove_storage_node(lan, name, mac, ip, rs_name, primary_container, port=27018, keep_volume=False)`

```python
def remove_storage_node(self, lan: int, name: str, mac: str,
                        ip: str, rs_name: str, primary_container: str,
                        port: int = 27018,
                        keep_volume: bool = False) -> RemovalResult:
    timings = RemovalTimings()
    t_total = time.perf_counter()

    # Step 1: RS removal via primary.
    # DNAT flows are already expired (90 s idle pre-condition > 30 s VIP_IDLE_TIMEOUT)
    # for the underutilization path. For the telemetry-timeout (dead node) path,
    # the script will flush flows as part of teardown. Either way, no active client
    # connections exist when rs.remove() executes.
    t0 = time.perf_counter()
    member_host = f"{ip}:{port}"
    primary_host = self._find_rs_primary(primary_container, port)
    rs_ok = self._rs_remove_member(primary_container, primary_host, member_host)
    if rs_ok:
        self._wait_rs_member_removed(primary_container, primary_host, member_host)
    timings.drain_wait_s = time.perf_counter() - t0

    # Step 2: Network teardown via shell script.
    # --skip-rs: script skips rs.remove() (already done above).
    # Script handles: docker stop --time 15, flow flush, del-port, veth del,
    # docker rm, volume rm — no duplication in Python.
    t0 = time.perf_counter()
    skip_rs_args = ["--skip-rs"] if rs_ok else []
    volume_args = ["--keep-volume"] if keep_volume else []
    ok, _, stdout, stderr = self._run_script(
        SCRIPTS_DIR / "remove_network_storage_node.sh",
        ["--lan", str(lan), "--name", name] + skip_rs_args + volume_args,
    )
    timings.network_cleanup_s = time.perf_counter() - t0
    timings.total_s = time.perf_counter() - t_total

    state = NodeOperationState.DONE if ok else NodeOperationState.FAILED
    return RemovalResult(ok, name, mac, timings, state, stdout, stderr)
```

### Private Helpers

| Helper                                                            | Description                                                                        |
| ----------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `_find_rs_primary(container, port)`                             | `docker exec <container> mongosh --eval "db.adminCommand({isMaster:1}).primary"` |
| `_rs_remove_member(container, primary_host, member_host)`       | `rs.remove('<member_host>')` via primary                                         |
| `_wait_rs_member_removed(container, primary_host, member_host)` | Poll `rs.status()` 10 × 3 s                                                     |

### Reuse of Existing Shell Scripts

The removal methods delegate infrastructure cleanup to the existing shell
scripts. The Python code adds only the logic that must precede the script:

- Compute (Phase A): VIP isolation, veth discovery, drain signal.
  Phase B calls the script with `--veth`/`--mac` for the full OVS teardown.
- Storage: RS removal via primary (must happen in Python before the script
  handles flow flush, container stop, and OVS teardown with `--skip-rs`).

This keeps OVS port removal, flow flush, and veth deletion in one place (the
scripts) and avoids duplication.

---

## Phase 3 — Shell Script Adjustments

### `remove_network_node.sh`

**Current problem:** `docker stop` immediately cuts active connections.

**Change:** add `--graceful`, `--drain-timeout`, `--veth`, and `--mac` flags.

- `--graceful` / `--drain-timeout` are for standalone CLI use only. The
  controller does **not** use `--graceful`.
- `--veth <veth>` and `--mac <mac>` allow Phase B to supply pre-discovered
  values so the script can skip `nsenter` discovery. This is necessary because
  the container is already exited in Phase B — its netns is gone, so `nsenter`
  would fail and OVS ports and veth pairs would leak.

```bash
# New argument parsing additions:
GRACEFUL=false
DRAIN_TIMEOUT=30
OVS_VETH=""     # pre-discovered veth (skips nsenter if provided)
CONTAINER_MAC="" # pre-discovered MAC (skips nsenter if provided)

--graceful)      GRACEFUL=true;       shift ;;
--drain-timeout) DRAIN_TIMEOUT="$2"; shift 2 ;;
--veth)          OVS_VETH="$2";      shift 2 ;;
--mac)           CONTAINER_MAC="$2"; shift 2 ;;
```

In `main()`, veth/MAC discovery is skipped when both are provided:

```bash
if [[ -n "$OVS_VETH" && -n "$CONTAINER_MAC" ]]; then
    echo "Using pre-discovered veth=${OVS_VETH} mac=${CONTAINER_MAC}"
    mac="$CONTAINER_MAC"
else
    # Existing nsenter discovery (container must be running)
    ...
fi
```

With `--graceful`, after veth/MAC discovery:

```bash
if [[ "$GRACEFUL" == "true" ]]; then
    echo "Sending drain signal to '${CONTAINER_NAME}'..."
    docker exec "$CONTAINER_NAME" curl -sS -X POST http://localhost:5000/drain \
        || echo "  ⚠️  Drain signal failed (container may be dead)." >&2

    echo "Waiting up to ${DRAIN_TIMEOUT}s for container to exit..."
    local waited=0
    while [[ "$waited" -lt "$DRAIN_TIMEOUT" ]]; do
        local status
        status=$(docker inspect -f '{{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null) || break
        [[ "$status" != "running" ]] && break
        sleep 1
        waited=$((waited + 1))
    done
fi
```

Without `--graceful`: current immediate behavior (for when the controller
already handled drain, or for force-removal).

### `remove_network_storage_node.sh`

**Changes:**

1. Add `--skip-rs` flag: skip `rs.remove()` step entirely (controller already
   did it in Python before calling the script).
2. Reorder operations when `--skip-rs` is set: flush DNAT flows **before**
   `docker stop --time 15` (flow flush is already a no-op for the
   underutilization path but is genuinely needed for dead-node removal).

```bash
SKIP_RS=false

--skip-rs) SKIP_RS=true; shift ;;
```

```bash
# RS removal section:
if [[ "$SKIP_RS" == "false" ]]; then
    # ... existing rs.remove() logic ...
fi

# Always use docker stop --time 15 to give mongod its SIGTERM quiesce.
# mongod has no RS obligations (already removed) and no client connections,
# so the quiesce period completes almost instantly.
docker stop --time 15 "$CONTAINER_NAME" >/dev/null
```

---

## Phase 4 — ElasticityManager Scale-Down Handlers

**File:** `source/sdn_controller/elasticity/elasticity.py`

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

@dataclass(frozen=True)
class CleanupComputeAlert:
    """Phase B trigger — submitted when drain_complete ZMQ event arrives
    or when telemetry timeout fires for a MAC with a pending drain."""
    mac: str
```

`ip` and `mac` are passed from the caller (from the original `NodeResult`
stored in the `_active` audit trail) to avoid re-discovery race conditions.

### New State

```python
import threading

# Pending drain records — populated in Phase A, consumed in Phase B
self._pending_drains: dict[str, PendingDrain] = {}   # key: MAC address

# Completed-removal notifications for Thread 2.
# Written by Thread 3 (handlers) after cleanup; read+cleared by Thread 2
# (_on_telemetry_update) to purge _dynamic_node_macs / _absent_window_count.
self._removal_complete_lock = threading.Lock()
self._removal_complete_macs: set[str] = set()

def has_pending_drain(self, mac: str) -> bool:
    """Check if a MAC has an in-progress drain. Used by telemetry timeout
    handler to decide whether to submit CleanupComputeAlert (pending)
    or ScaleDownComputeAlert (not pending — node died without drain)."""
    return mac in self._pending_drains

def consume_removal_completions(self) -> set[str]:
    """Called by Thread 2 to collect MACs of fully removed nodes.
    Clears the internal set and returns a snapshot. Thread 2 uses the
    result to remove MACs from _dynamic_node_macs and _absent_window_count."""
    with self._removal_complete_lock:
        macs = set(self._removal_complete_macs)
        self._removal_complete_macs.clear()
        return macs
```

### New Handlers

```python
def _handle_scale_down_compute(self, alert: ScaleDownComputeAlert) -> None:
    """Phase A: isolate from VIP, discover veth, send drain signal, return."""
    logger.info("Scale-down compute Phase A: %s (mac=%s)", alert.container_name, alert.mac)
    self._topo.remove_server_mac(alert.mac)

    pending = self._adder.initiate_drain(
        lan=alert.lan, name=alert.container_name, mac=alert.mac,
    )

    if pending is None:
        # Veth discovery failed — container netns already gone (hard crash).
        # Use veth="unknown"; the script will skip OVS port/veth removal
        # (nsenter unavailable) and log a warning about the potential port leak.
        logger.warning("Veth discovery failed for %s — falling back to unknown veth", alert.mac)
        self._pending_drains[alert.mac] = PendingDrain(
            mac=alert.mac, veth="unknown", container_name=alert.container_name,
            lan=alert.lan, initiated_ts=time.time(),
            drain_signaled=False,
        )
        self._queue.put(CleanupComputeAlert(mac=alert.mac))
        return

    self._pending_drains[alert.mac] = pending

    if not pending.drain_signaled:
        # Veth is known but drain HTTP call failed — container is likely dead.
        # No drain_complete event will arrive; skip the wait, go to Phase B.
        logger.warning("Drain signal failed for %s (veth=%s) — submitting immediate cleanup",
                       alert.mac, pending.veth)
        self._queue.put(CleanupComputeAlert(mac=alert.mac))
        return

    logger.info("Phase A complete — waiting for drain_complete from %s", alert.mac)
    # Thread 3 returns here — _busy becomes False, new operations can proceed.

def _handle_cleanup_compute(self, alert: CleanupComputeAlert) -> None:
    """Phase B: clean up OVS/veth/flows/container after drain_complete."""
    pending = self._pending_drains.pop(alert.mac, None)
    if pending is None:
        logger.warning("No pending drain for %s — ignoring cleanup alert", alert.mac)
        return

    logger.info("Scale-down compute Phase B: cleaning up %s", pending.container_name)
    result = self._adder.cleanup_compute_node(pending)
    self._adder.log_timings(result)
    self._record({
        "type": "scale_down_compute", "alert": alert,
        "name": pending.container_name, "result": result,
    })
    # Notify Thread 2 to remove this MAC from _dynamic_node_macs and
    # _absent_window_count. Done regardless of result.success so stale
    # tracking state is always cleared even after a partial cleanup failure.
    with self._removal_complete_lock:
        self._removal_complete_macs.add(alert.mac)

def _handle_scale_down_data(self, alert: ScaleDownDataAlert) -> None:
    logger.info("Scale-down data: removing %s (mac=%s)", alert.container_name, alert.mac)
    self._topo.remove_storage_mac(alert.mac, domain=f"n{alert.lan}")

    result = self._adder.remove_storage_node(
        lan=alert.lan, name=alert.container_name, mac=alert.mac,
        ip=alert.ip, rs_name=alert.rs_name,
        primary_container=alert.primary_container, port=alert.port,
    )
    self._adder.log_timings(result)
    self._record({
        "type": "scale_down_data", "alert": alert,
        "name": alert.container_name, "result": result,
    })
    # Notify Thread 2 to remove this MAC from _dynamic_node_macs and
    # _absent_window_count. Done regardless of result.success.
    with self._removal_complete_lock:
        self._removal_complete_macs.add(alert.mac)
```

### Loop Extension

```python
def __init__(self, topology_mixin: TopologyMixin) -> None:
    # ... existing init ...
    self._busy = False  # read by Thread 2, written by Thread 3

def is_busy(self) -> bool:
    """Thread-safe check: is an operation currently in progress?
    Called by Thread 2 to skip scaling evaluation during operations.
    Also returns True while any drain is pending (Phase A complete, Phase B
    not yet triggered) so a duplicate ScaleDownComputeAlert cannot be
    submitted for the same MAC while it is still draining."""
    return self._busy or bool(self._pending_drains)

def _loop(self) -> None:
    while True:
        alert = self._queue.get()
        self._busy = True
        try:
            if isinstance(alert, ComputeAlert):
                self._handle_compute(alert)
            elif isinstance(alert, DataAlert):
                self._handle_data(alert)
            elif isinstance(alert, ScaleDownComputeAlert):
                self._handle_scale_down_compute(alert)
            elif isinstance(alert, ScaleDownDataAlert):
                self._handle_scale_down_data(alert)
            elif isinstance(alert, CleanupComputeAlert):
                self._handle_cleanup_compute(alert)
            else:
                logger.warning("Unknown alert type: %s", type(alert).__name__)
        except Exception:
            logger.exception("Error handling alert %s", alert)
        finally:
            self._busy = False
```

Note: `CleanupComputeAlert` (Phase B) also sets `_busy = True` during
cleanup. This is correct: Phase B performs docker stop, flow flush, and
OVS teardown — no other scaling operations should run concurrently.

`_busy` is a simple `bool` — safe without a lock because it's written only
by Thread 3 and read by Thread 2. Python's GIL guarantees atomic reads/writes
of `bool`. Thread 2 checks `is_busy()` and skips evaluation; Thread 3 sets
`True` before handling and `False` in `finally`.

```

---

## Phase 5 — Telemetry Timeout + Underutilization Triggers

**File:** `source/sdn_controller/main_n1.py`

### State

```python
# Dynamic node tracking (populated on add, cleared on remove)
self._dynamic_node_macs: set[str] = set()

# Telemetry timeout: absent-window counters
self._absent_window_count: dict[str, int] = {}

# Underutilization: separate per-tier counters (no explicit cooldown)
self._scale_down_compute_consecutive: int = 0
self._scale_down_storage_consecutive: int = 0
# Scale-up: per-tier consecutive counters (requires 2 windows above threshold)
self._scale_up_compute_consecutive:   int = 0
self._scale_up_storage_consecutive:   int = 0
```

`_scaling_in_progress` is no longer needed as local state — Thread 2 calls
`self._em.is_busy()` directly on the `ElasticityManager` instance.

### Scale-Up Thresholds

Scale-up requires **both** CPU AND latency to exceed their thresholds simultaneously. Latency alone is ambiguous — a cold-start or large payload causes high latency regardless of fleet size. CPU confirms the system has genuinely exhausted capacity.

| Env var               | Default  | Description                                        |
| --------------------- | -------- | -------------------------------------------------- |
| `TAU_PROC_MS`       | `600`  | Domain avg processing latency → compute scale-up  |
| `TAU_DADOS_MS`      | `150000` | Domain avg DB latency → storage scale-up         |
| `TAU_CPU_UP`        | `70`   | Domain avg CPU % for compute scale-up AND gate    |
| `TAU_STORAGE_CPU_UP` | `70`  | Domain avg storage CPU % for storage scale-up AND gate |

Scale-up also fires only after **2 consecutive windows** above threshold — this prevents a single transient spike from triggering an add. When scale-up fires for a tier, that tier's scale-down consecutive counter is reset to 0 (cross-direction reset).

### Timeout Detection

Added to `_on_telemetry_update()`:

```python
# Consume completed-removal notifications from Thread 3 first, so stale
# MACs are purged before the timeout and underutilization loops run.
for mac in self._em.consume_removal_completions():
    self._dynamic_node_macs.discard(mac)
    self._absent_window_count.pop(mac, None)
    self._active.pop(mac, None)
    logger.info("[scale-down] removed MAC %s from dynamic tracking after cleanup", mac)

# Check each dynamic MAC for telemetry timeout
for mac in list(self._dynamic_node_macs):
    present = (mac in summary.servers) or (mac in summary.storage_servers)
    if present:
        self._absent_window_count[mac] = 0
    else:
        count = self._absent_window_count.get(mac, 0) + 1
        self._absent_window_count[mac] = count
        if count >= self._telemetry_timeout_windows:
            log.debug("Telemetry timeout for %s (%d absent windows)", mac, count)
            if self._em.has_pending_drain(mac):
                # Phase A already ran — container was draining but
                # drain_complete never arrived (crash, OOM, network).
                # Skip Phase A, go straight to Phase B cleanup.
                self._em.submit_cleanup_compute(mac)
            else:
                # Node died without a drain — normal timeout removal.
                self._submit_scale_down_alert(mac)
```

### Drain Complete Handling

Added to `_on_telemetry_update()` — process `control_events` from the
aggregator summary:

```python
# Process drain_complete events from the ZMQ pipeline
for event in summary.control_events:
    if event.get("event_type") == "drain_complete":
        mac = event.get("server_id")
        if mac and self._elasticity.has_pending_drain(mac):
            logger.info("[scale-down] drain_complete received for mac=%s — submitting Phase B cleanup", mac)
            self._elasticity.submit_cleanup_compute(mac)
```

> **Guard:** `has_pending_drain(mac)` is checked before submitting cleanup. This prevents spurious `drain_complete` events (e.g., a replayed ZMQ message or a stale event after cleanup already completed) from triggering a second Phase B.

The `drain_complete` event flows through the existing ZMQ pipeline:

1. Edge server drain monitor sends `{"event_type": "drain_complete", "server_id": MAC, "ts": ...}` via `_metric_sender.send()` (ZMQ PUSH)
2. Aggregator receives it on PULL, passes it through as `control_events` in the published summary (not buffered/aggregated — forwarded immediately)
3. Controller receives it on SUB, calls `self._em.submit_cleanup_compute(mac)` which puts a `CleanupComputeAlert` in Thread 3's queue

**Aggregator change** (`source/docker/local_state_server/aggregator.py`):
The aggregator's `_receive_loop()` must recognize `drain_complete` events and
forward them as `control_events` **immediately** — not buffered until the next
aggregation window.

**Mechanism:** when a `drain_complete` message arrives on the PULL socket the
aggregator publishes a mini-summary immediately via the PUB socket. This
mini-summary contains only the `control_events` list; metric fields are empty
or `None`. The aggregator does not modify or delay the event — it is a single
ZMQ hop (~1 ms).

```python
# In _receive_loop(), upon receiving any message:
if event.get("event_type") == "drain_complete":
    # Publish immediately — do not wait for the next window boundary.
    # Omit domain_summary entirely: Pydantic uses its default (all zeros).
    # The controller returns early before reading domain_summary for
    # mini-summaries (guard: if not summary.servers and not summary.storage_servers: return).
    mini = {
        "network_id":      NETWORK_ID,
        "window_end":      time.time(),
        "servers":         {},
        "storage_servers": {},
        "control_events":  [event],
    }
    pub.send_json(mini)
    continue  # do not also buffer into the window
```

The controller's `_on_telemetry_update` must accept summaries with `domain=None`
and process `control_events` regardless. Regular window-boundary summaries
continue to carry `"control_events": []`.

### Underutilization Detection

Added after existing scale-up checks:

```python
# Skip ALL scaling evaluation while an operation is in progress.
# Same pattern as AWS Auto Scaling — no new scaling activity while one runs.
# Thread 2 must not stack conflicting decisions in the queue.
if self._em.is_busy():
    return

# --- Cross-direction resets (scale-up path, shown here for reference) --------
# When a scale-up fires for a tier, that tier's scale-down consecutive counter
# is immediately zeroed. The system then needs 9 fresh windows of genuinely
# idle metrics before scale-down can fire again. This reset is placed inline
# with the existing scale-up branches (not duplicated here) as:
#   self._scale_down_compute_consecutive = 0   # inside compute scale-up branch
#   self._scale_down_storage_consecutive = 0   # inside storage scale-up branch
# Symmetrically, scale-down firing zeroes the scale-up counter (already shown
# in the underutilization code below via self._scale_up_*_consecutive = 0).
# -----------------------------------------------------------------------------

# --- Compute scale-down (domain avg CPU AND domain avg processing latency) ---
if (summary.domain.average_cpu_percent < self._tau_cpu_down
        and summary.domain.avg_time_proc_ms < self._tau_proc_down_ms):
    self._scale_down_compute_consecutive += 1
else:
    self._scale_down_compute_consecutive = 0

if self._scale_down_compute_consecutive >= self._scale_down_compute_required:
    last = self._find_last_dynamic_compute_node()
    if last is not None:
        self._submit_scale_down_alert(last.mac)
        self._scale_down_compute_consecutive = 0
    else:
        # No eligible node — reset so the counter doesn't accumulate
        # meaninglessly. The cross-direction reset already handles the
        # normal case (scale-up zeroes this counter), so this only matters
        # if dynamic nodes were removed outside the normal scale-down path.
        self._scale_down_compute_consecutive = 0

# --- Storage scale-down (domain avg storage CPU AND domain avg DB latency) ---
if (summary.domain.avg_storage_cpu_percent < self._tau_storage_cpu_down
        and summary.domain.avg_time_db_ms < self._tau_db_down_ms):
    self._scale_down_storage_consecutive += 1
else:
    self._scale_down_storage_consecutive = 0

if self._scale_down_storage_consecutive >= self._scale_down_storage_required:
    last = self._find_last_dynamic_storage_node()
    if last is not None:
        self._submit_scale_down_alert(last.mac)
        self._scale_down_storage_consecutive = 0
    else:
        self._scale_down_storage_consecutive = 0  # same rationale as compute
```

### Helper Methods

**`_find_last_dynamic_compute_node()` and `_find_last_dynamic_storage_node()`**

LIFO selection requires ordered tracking. `_active: dict[str, NodeInfo]` is a
regular Python dict (insertion order = addition order). The most recently added
node is at the end — iterating in reverse gives LIFO.

```python
@dataclass
class NodeInfo:
    """Stored in _active audit trail on node addition. Supplies all fields
    needed to build ScaleDownComputeAlert / ScaleDownDataAlert."""
    mac:               str
    node_type:         str          # "compute" or "storage"
    lan:               int
    network_id:        str
    name:              str          # container name
    ip:                str
    rs_name:           str = ""     # storage only
    primary_container: str = ""     # storage only
    port:              int = 27018  # storage only

# Populated on add, consumed on remove:
self._active: dict[str, NodeInfo] = {}   # key: MAC, insertion order = LIFO

def _find_last_dynamic_compute_node(self) -> NodeInfo | None:
    for mac, info in reversed(list(self._active.items())):
        if mac in self._dynamic_node_macs and info.node_type == "compute":
            return info
    return None

def _find_last_dynamic_storage_node(self) -> NodeInfo | None:
    for mac, info in reversed(list(self._active.items())):
        if mac in self._dynamic_node_macs and info.node_type == "storage":
            return info
    return None
```

**`_submit_scale_down_alert(mac)`**

Looks up `_active[mac]` to retrieve all alert fields, then builds and submits
the appropriate alert to Thread 3. Called from both the telemetry timeout
handler (with just a MAC) and the underutilization path (via the LIFO helpers
above).

```python
def _submit_scale_down_alert(self, mac: str) -> None:
    if mac not in self._dynamic_node_macs:
        log.warning("MAC %s is not a dynamic node — skipping scale-down", mac)
        return
    info = self._active.get(mac)
    if info is None:
        log.warning("No NodeInfo for MAC %s — cannot build scale-down alert", mac)
        return
    if info.node_type == "compute":
        alert = ScaleDownComputeAlert(
            lan=info.lan, network_id=info.network_id,
            container_name=info.name, ip=info.ip, mac=mac,
        )
    else:
        alert = ScaleDownDataAlert(
            lan=info.lan, network_id=info.network_id,
            container_name=info.name, ip=info.ip, mac=mac,
            rs_name=info.rs_name, primary_container=info.primary_container,
            port=info.port,
        )
    self._em.submit(alert)
```

---

## Files to Change

| File                                                      | Action              | Purpose                                                                                  |
| --------------------------------------------------------- | ------------------- | ---------------------------------------------------------------------------------------- |
| `source/docker/edge_storage_server/entrypoint.sh`       | Modify              | Add SIGTERM trap to forward signal to `mongod` (Phase 0)                               |
| `source/docker/edge_server/source/app.py`               | Modify              | Add `/drain` endpoint, active-request counter, drain monitor with ZMQ event            |
| `source/docker/local_state_server/aggregator.py`        | Modify              | Pass through `drain_complete` events as `control_events` in published summary        |
| `source/sdn_controller/elasticity/node_manager.py`      | Modify              | Add `initiate_drain()`, `cleanup_compute_node()`, `remove_storage_node()`, helpers (no `remove_edge_server`) |
| `source/sdn_controller/elasticity/elasticity.py`        | Modify              | Add `CleanupComputeAlert`, `PendingDrain` state, Phase A/B handlers, loop dispatch   |
| `source/sdn_controller/main_n1.py`                      | Modify              | Add drain_complete handling, telemetry timeout integration, underutilization trigger     |
| `source/scripts/network/remove_network_node.sh`         | Modify              | Add `--graceful` + `--drain-timeout` flags (CLI use only)                            |
| `source/scripts/network/remove_network_storage_node.sh` | Modify              | Add `--skip-rs`, `--graceful`, `--drain-timeout` flags                             |
| `source/sdn_controller/topology/topology.py`            | **No change** | `remove_server_mac()` and `remove_storage_mac()` already exist                       |

---

## Implementation Order

```
Phase 0 (entrypoint.sh)                 ─┐
Phase 1 (drain endpoint + ZMQ event)    ─┤
Phase 1a (aggregator pass-through)      ─┤
                                          ├──► Phase 2 (NodeAdder) ──► Phase 4 (Elasticity) ──► Phase 5 (triggers)
Phase 3 (shell scripts)                 ─┘
```

Phase 0, Phase 1 (including 1a — aggregator), and Phase 3 have no dependencies
and can be implemented in parallel. Phase 1 and 1a are closely related (send
event + forward event) and should be implemented together. Phase 2 depends on
all three. Phase 4 depends on Phase 2. Phase 5 depends on Phase 4.

---

## Verification

| #  | Test                          | What to check                                                                                                                                                                          |
| -- | ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1  | Drain smoke test              | `curl -X POST :5000/drain` → 200; `POST /data` → 503; drain_complete ZMQ event sent; idle container exits                                                                        |
| 2  | Compute removal under load    | Traffic generator → trigger removal → Phase A (<1 s): VIP removed, veth discovered, drain sent, Thread 3 returns → Phase B: drain_complete received, OVS cleaned, container removed |
| 2a | Drain fallback (no ZMQ event) | Kill container during drain (no drain_complete sent) → telemetry timeout (10 absent windows) → has_pending_drain = true → CleanupComputeAlert → Phase B cleanup proceeds           |
| 3  | Storage removal               | VIP isolation → flow flush → edge server retries on healthy node →`rs.remove()` → `docker stop --time 15` → RS clean, data accessible                                         |
| 3a | SIGTERM forwarding            | `docker stop --time 15` → mongod logs `Shutting down exitCode:0`, no journal recovery on restart                                                                                  |
| 4  | Telemetry timeout (no drain)  | Kill dynamic node (no pending drain) → after 10 absent windows → ScaleDownComputeAlert fires → Phase A + Phase B                                                                    |
| 5  | Dead node drain failure       | Phase A:`/drain` fails (node dead) → immediate CleanupComputeAlert → Phase B cleanup                                                                                               |
| 6  | Compute underutilization      | Lower load → domain CPU AND proc latency below threshold for 9 windows → compute scale-down fires                                                                                    |
| 6a | Storage underutilization      | Lower load → domain storage CPU AND DB latency below threshold for 9 windows → storage scale-down fires independently                                                                |
| 6b | High latency, low CPU         | Large query causes high `avg_time_db_ms` but storage CPU is low → no scale-down/scale-up triggered (data-bound, not capacity)                                                       |
| 7  | Scope                         | Verify static/primary nodes are never eligible for removal                                                                                                                             |
| 8  | Shell standalone              | `remove_network_node.sh --lan 1 --name <name>` from CLI; or pre-drain the endpoint manually then pass `--veth`/`--mac` for cleanup-only mode                                        |
| 9  | Aggregator pass-through       | Send drain_complete ZMQ event → verify aggregator includes it in `control_events` → controller receives it                                                                         |

---

## Design Decisions

| Decision                                      | Rationale                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| --------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| No `/drain/status`                          | Controller doesn't poll it; container signals completion via `drain_complete` ZMQ event and then exits itself. No useful action between "drain started" and "drain_complete received".                                                                                                                                                                                                                                                                                      |
| Drop `connections_current` for storage      | Background connections (telemetry sidecar `serverStatus()` every 2 s, RS heartbeats, mongosh) keep count at 4–7 even when application-idle.                                                                                                                                                                                                                                                                                                                                |
| Active flow flush BEFORE `rs.remove()`      | A REMOVED mongod refuses writes. Passive `sleep(MAX_IDLE_MS)` fails under sustained load (connection never goes idle). Flushing DNAT flows actively breaks the network path; edge server retries via VIP to a healthy node. One query delayed, no data loss. For the underutilization path the flush is a structural no-op: 90 s idle > 30 s `VIP_IDLE_TIMEOUT`, so flows have already expired. For the telemetry timeout (dead node) path the flush is genuinely needed. |
| `docker stop --time 15` for storage         | MongoDB 5.0+ SIGTERM quiesce; safety net only — no clients after flow flush, no RS obligations after `rs.remove()`, so quiesce completes instantly.                                                                                                                                                                                                                                                                                                                        |
| Compute removal delegated to script           | `remove_network_node.sh --graceful` retained for standalone CLI use. The controller does **not** use `--graceful` — it handles drain in Python (Phase A: `initiate_drain()`) and calls the script without `--graceful` for cleanup only (Phase B: `cleanup_compute_node()`).                                                                                                                                                                                 |
| Async two-phase compute removal               | Synchronous removal blocks Thread 3 for unbounded duration (in-flight request completion). Phase A (<1 s) discovers veth + sends drain signal + returns. Phase B fires on `drain_complete` ZMQ event. Thread 3 is free between phases for other operations.                                                                                                                                                                                                                 |
| `drain_complete` via ZMQ pipeline           | Reuses existing ZMQ PUSH→PULL→PUB→SUB infrastructure. Aggregator passes through `drain_complete` as `control_events` (not buffered). Controller receives it in Thread 2 and submits `CleanupComputeAlert` to Thread 3.                                                                                                                                                                                                                                               |
| Fallback via telemetry timeout                | If container crashes and never sends `drain_complete`, telemetry timeout (10 absent windows = 100 s) fires. `has_pending_drain(mac)` checks if Phase A already ran — if so, skips to Phase B cleanup directly.                                                                                                                                                                                                                                                           |
| SIGTERM trap in `entrypoint.sh`             | Bash (PID 1) does not forward signals to background `mongod`. Without the trap, `docker stop` never triggers quiesce — mongod gets SIGKILL after timeout.                                                                                                                                                                                                                                                                                                                |
| Self-removal via `/drain` + `os._exit(0)` | Container completes in-flight requests, sends `drain_complete` ZMQ event, then exits itself. Controller triggers Phase B cleanup on event receipt.                                                                                                                                                                                                                                                                                                                          |
| `docker exec curl` for drain signal         | `docker exec` bypasses OVS data path entirely — reliable even after VIP removal. ZMQ is one-way push (container→aggregator); cannot send commands *to* the container via ZMQ. The `drain_complete` event goes back *from* the container via the same ZMQ pipeline.                                                                                                                                                                                                  |
| Telemetry timeout: 10 absent windows          | Adapts to `WINDOW_S` changes. Catches crashes, OOM-kills, network partitions. If `/drain` fails → node is already dead.                                                                                                                                                                                                                                                                                                                                                  |
| LIFO removal order                            | Most recently added dynamic node of the relevant tier is least likely to hold long-lived state.                                                                                                                                                                                                                                                                                                                                                                               |
| Only dynamic nodes eligible                   | Static servers and primary DB are infrastructure constants — never removed.                                                                                                                                                                                                                                                                                                                                                                                                  |
| Shell scripts retain immediate mode           | `--graceful` is opt-in. `--skip-rs` avoids double RS removal when controller handles it. Backward compatible.                                                                                                                                                                                                                                                                                                                                                             |
| Reuse shell scripts for teardown              | Flow flush, OVS port removal, veth deletion already implemented in scripts. Python adds only drain/RS logic, delegates infra cleanup to existing scripts.                                                                                                                                                                                                                                                                                                                     |
| No scale-down while scaling in progress       | Same as AWS Auto Scaling: block new scaling activities while one runs. Thread 2 checks `em.is_busy()` and skips all scaling evaluation. Prevents conflicting operations from stacking. Prefers over-provisioning — better to have more resources than less.                                                                                                                                                                                                                |
| Counter reset on scale-up                     | A scale-up resets the matching tier's `_scale_down_*_consecutive` counter to 0. Prevents the race where metrics dip while a node is being added but not yet integrated. Requires 9 fresh windows from a settled state.                                                                                                                                                                                                                                                      |
| Dual condition (CPU AND latency)              | Latency alone is ambiguous — a large query is slow regardless of fleet size (data-bound, not capacity-bound). CPU alone misses user impact (high CPU but low latency = keeping up). Both together confirm: the system is saturated*and* users are affected.                                                                                                                                                                                                                |
| Dual condition for scale-up | Latency alone is insufficient for scale-up: a cold-start or large query causes high latency regardless of fleet size (data-bound, not capacity-bound). CPU confirms capacity is genuinely exhausted. Requiring CPU AND latency above threshold prevents false positives from transient workload spikes. Symmetric with the scale-down dual condition rationale. |
| Separate per-tier counters                    | Compute and storage scale independently, matching how scale-up works. Storage can scale down while compute stays; and vice versa.`is_busy()` + consecutive windows + cross-direction resets prevent rapid successive removals without needing an explicit cooldown.                                                                                                                                                                                                         |
| Domain-average CPU, not per-node              | Individual node spikes are normal (transient load imbalance via VIP). Domain average smooths these out — if the*fleet* average CPU is low, the fleet has excess capacity.                                                                                                                                                                                                                                                                                                  |
| Drop `avg_repl_lag_s` as scaling signal     | Every secondary independently applies the full write stream; adding more secondaries doesn’t reduce replication work on existing ones. If reads cause CPU contention that slows oplog application, CPU already captures that directly. Kept as monitoring/logging metric only.                                                                                                                                                                                               |
