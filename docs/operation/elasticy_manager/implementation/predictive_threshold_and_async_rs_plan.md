# Predictive Threshold, Priority Queue & Async RS Join — Implementation Plan

> **Status:** Implemented  
> **Date:** 2026-04-13  
> **Motivation:** Analysis of the `20260413` test run. Storage scale-up takes
> 34–45 s and fails under load (RS join via shell script fails when primary
> is at 94.9 % CPU). The reactive threshold (τ=0.40) triggers too late, and
> FIFO queue serialisation delays storage behind compute by 17 s.

---

## TL;DR

Fix storage scale-up with four changes:

1. **Predictive adaptive threshold** — lower base threshold (0.25 vs 0.40) for
   early detection, increment per dynamic node to prevent pile-up.
2. **Priority queue** — storage-first dispatch when both alerts fire together.
3. **Async RS join via sidecar** — unblocks controller thread, adds retry logic
   to prevent cascading failures.
4. **Relaxed scale-down** — cooldown=120 s, window=9/15 to protect proactively
   added nodes.

Expected result: first storage detection drops from ~20 s to ~10 s, no more
cascading RS join failures, no unnecessary node pile-up, no premature removal.

---

## Problem Summary

### Timeline (abbreviated)

| Time | Event | Detail |
|------|-------|--------|
| 09:26:30 | Load begins | CPU 64–68 %, db_ms 15–19 ms |
| 09:26:50 | Scale-up triggered (2/5 window) | Both LANs fire ComputeAlert + DataAlert |
| 09:27:07 | lan2: compute node DONE (17.3 s) | Storage starts **now** (queued behind compute) |
| 09:27:36 | lan1: storage dyn1 DONE (45.2 s) | net_attach=40.59 s was the bottleneck |
| 09:28:19 | lan1: storage dyn3 **FAILED** | `Could not determine primary of 'rs_net1'` |
| 09:28:24 | lan2: storage dyn4 **FAILED** | same failure — primary at 94.9 % CPU |
| 09:28:31–09:29:51 | lan1 storage_count=0 for **80 s** | No storage serving requests |

### Root Causes

1. **Queue serialisation** — FIFO queue processes compute (17 s) before storage,
   adding 17 s delay to storage provisioning.
2. **RS join fails under load** — `find_primary_host()` in the shell script
   shells out to `mongosh ... isMaster` on the overloaded primary → empty
   response → script bails → wasted container.
3. **No retry with backoff** — on failure the container is cleaned up; the next
   attempt only fires when a new DataAlert arrives (10 s+ later).
4. **Reactive threshold too slow** — τ=0.40, 2/5 window means ~20 s from first
   degradation to trigger. Given 34–45 s provisioning time, the system is in
   crisis before the node is ready.
5. **Scale-down too aggressive** — 75 s cooldown + 7/12 window can remove
   proactively added nodes before a load wave arrives.

---

## Phase 0 — Predictive Adaptive Storage Threshold

### Concept

Instead of a fixed threshold, use an **adaptive threshold** that:
- **Starts lower** (base=0.25) to detect degradation ~10 s earlier than τ=0.40.
- **Increases per dynamic storage node** (+0.10 each) to prevent pile-up:
  the more nodes already provisioning/active, the harder it is to trigger
  another scale-up.
- **Caps at 0.65** so the system can always scale up under genuine saturation.

```
effective_threshold = min(base + dynamic_storage_count × increment, max_threshold)
```

Where `dynamic_storage_count` = pending + active dynamic storage nodes for
that LAN (count of entries in the **controller's** `self._active: dict[str, NodeInfo]`
in `main_n1.py`/`main_n2.py` where `node_type == "storage"`).

> **Note:** `ElasticityManager` in `elasticity.py` also has a `self._active`
> but it is a `list[dict]` used as an audit trail — **not** the same dict.
> To avoid confusion, Phase 1 renames that field to `_operation_log`.

**Compute scale-up is unchanged** — compute nodes start fast enough (~10 s)
that the current τ=0.40 with 2/5 window works well.

### Storage sliding window change

| Parameter | Current | New | Wall-clock at 10 s/window |
|-----------|---------|-----|--------------------------|
| Window size | 5 | **3** | 30 s |
| Required | 2 | **1** | First breach triggers |

With a lower base threshold (0.25) the false-positive risk is managed by the
per-node increment, not the window depth.

### Scale-down protection

| Parameter | Current | New | Reason |
|-----------|---------|-----|--------|
| Storage cooldown | 75 s | **120 s** | Proactively added nodes need time to prove usefulness |
| Storage window | 7/12 | **9/15** | More sustained signal required before removal |

### New environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SCALEUP_STORAGE_BASE_THRESHOLD` | `0.25` | Adaptive threshold: base value |
| `SCALEUP_STORAGE_THRESHOLD_INCREMENT` | `0.10` | Per-dynamic-node increment |
| `SCALEUP_STORAGE_MAX_THRESHOLD` | `0.65` | Adaptive threshold: cap |
| `SCALEUP_STORAGE_WINDOW_SIZE` | `3` | Storage scale-up sliding window size |
| `SCALEUP_STORAGE_REQUIRED` | `1` | Required above-threshold windows (storage) |

The existing `SCALEUP_SCORE_THRESHOLD`, `SCALEUP_WINDOW_SIZE`, and
`SCALEUP_REQUIRED` become **compute-only** — storage uses the new separate
variables.

Scale-down env vars updated (both `.env` **and** Python fallback defaults):

| Variable | Current default | New default | Python fallback also updated? |
|----------|-----------------|-------------|-------------------------------|
| `SCALEDOWN_STORAGE_COOLDOWN_S` | `75` | `120` | **Yes** — change `"75"` → `"120"` in `main_n1.py`/`main_n2.py` |
| `SCALE_DOWN_STORAGE_WINDOW_SIZE` | `12` | `15` | **Yes** — change `"12"` → `"15"` |
| `SCALE_DOWN_STORAGE_REQUIRED` | `7` | `9` | **Yes** — change `"7"` → `"9"` |

### Code — `main_n1.py` / `main_n2.py`

#### New module-level constants (alongside existing scale-up block)

```python
# Adaptive storage threshold (predictive — lower base, increment per node)
_SCALEUP_STORAGE_BASE_THRESHOLD      = float(os.environ.get("SCALEUP_STORAGE_BASE_THRESHOLD", "0.25"))
_SCALEUP_STORAGE_THRESHOLD_INCREMENT = float(os.environ.get("SCALEUP_STORAGE_THRESHOLD_INCREMENT", "0.10"))
_SCALEUP_STORAGE_MAX_THRESHOLD       = float(os.environ.get("SCALEUP_STORAGE_MAX_THRESHOLD", "0.65"))
_SCALEUP_STORAGE_WINDOW_SIZE         = int(os.environ.get("SCALEUP_STORAGE_WINDOW_SIZE", "3"))
_SCALEUP_STORAGE_REQUIRED            = int(os.environ.get("SCALEUP_STORAGE_REQUIRED", "1"))
```

#### `__init__` — separate storage window deque

```python
# Currently:
self._scale_up_storage_window: deque[bool] = deque(maxlen=_SCALE_UP_WINDOW_SIZE)

# Becomes:
self._scale_up_storage_window: deque[bool] = deque(maxlen=_SCALEUP_STORAGE_WINDOW_SIZE)
```

Similarly, the storage scale-down deque uses the new window size:

```python
# Currently:
self._scale_down_storage_window: deque[bool] = deque(maxlen=_SCALE_DOWN_STORAGE_WINDOW_SIZE)

# Becomes (with updated default 15):
self._scale_down_storage_window: deque[bool] = deque(maxlen=_SCALE_DOWN_STORAGE_WINDOW_SIZE)
```

#### `_count_dynamic_storage_nodes()` — new helper

```python
def _count_dynamic_storage_nodes(self) -> int:
    """Count pending + active dynamic storage nodes for adaptive threshold."""
    return sum(
        1 for info in self._active.values()
        if info.node_type == "storage"
    )
```

#### `_evaluate_scale_up()` — storage section changes

Replace the storage threshold comparison with the adaptive formula:

```python
def _evaluate_scale_up(self, ds: DomainSummary, lan: int, network_id: str) -> None:
    # ── Storage score ──
    storage_score = self._degradation_score(
        ds.avg_storage_cpu_percent, ds.avg_time_db_ms,
        _W_STORAGE_CPU, _W_T_DB,
        _STORAGE_CPU_FLOOR, _STORAGE_CPU_SPAN,
        _T_DB_FLOOR, _T_DB_SPAN,
    )

    # Adaptive threshold: increases with each dynamic storage node
    dynamic_count = self._count_dynamic_storage_nodes()
    effective_threshold = min(
        _SCALEUP_STORAGE_BASE_THRESHOLD + dynamic_count * _SCALEUP_STORAGE_THRESHOLD_INCREMENT,
        _SCALEUP_STORAGE_MAX_THRESHOLD,
    )

    above = storage_score >= effective_threshold
    self._scale_up_storage_window.append(above)
    logger.debug(
        "[scale-up] storage score=%.2f (τ_eff=%.2f, base=%.2f +%d×%.2f) "
        "cpu_s=%.1f%% T_db=%.1fms  window=%d/%d on %s",
        storage_score, effective_threshold,
        _SCALEUP_STORAGE_BASE_THRESHOLD, dynamic_count, _SCALEUP_STORAGE_THRESHOLD_INCREMENT,
        ds.avg_storage_cpu_percent, ds.avg_time_db_ms,
        sum(self._scale_up_storage_window), len(self._scale_up_storage_window),
        network_id,
    )
    if sum(self._scale_up_storage_window) >= _SCALEUP_STORAGE_REQUIRED:
        logger.info(
            "[scale-up] storage triggered: %d/%d windows ≥ %.2f "
            "(eff_τ=%.2f, dyn_nodes=%d, last score=%.2f, cpu_s=%.1f%%, T_db=%.1fms) on %s",
            sum(self._scale_up_storage_window),
            len(self._scale_up_storage_window),
            effective_threshold, effective_threshold, dynamic_count,
            storage_score, ds.avg_storage_cpu_percent, ds.avg_time_db_ms, network_id,
        )
        self._scale_up_storage_window.clear()
        self._scale_down_storage_window.clear()  # cross-direction reset
        self._elasticity.submit_alert(
            DataAlert(
                lan=lan,
                network_id=network_id,
                rs_name=f"rs_net{lan}",
                primary_container=f"edge_storage_server_n{lan}",
            )
        )
        self._last_storage_scale_up_ts = time.monotonic()

    # ── Compute score ── (unchanged — uses static _SCALE_UP_SCORE_THRESHOLD)
    ...
```

The compute section remains identical — still uses `_SCALE_UP_SCORE_THRESHOLD`
(0.40), `_SCALE_UP_WINDOW_SIZE` (5), and `_SCALE_UP_REQUIRED` (2).

> **`main_n2.py` note:** In `main_n2.py`, `_evaluate_scale_up()` evaluates
> **compute first, then storage** (reversed order from `main_n1.py`). The
> adaptive threshold change only applies to the **storage score** section in
> both files — find the `# ── Storage score ──` block regardless of its
> position relative to the compute block.

### Worked Example

With 0 dynamic storage nodes and the 2026-04-13 telemetry:

```
09:26:30  score=0.48  effective_τ=0.25  above ✓  window 1/3 → TRIGGERED!
```

vs the current behaviour (τ=0.40, 2/5 window):

```
09:26:30  score=0.48  τ=0.40  above ✓  window 1/5
09:26:40  score=0.87  τ=0.40  above ✓  window 2/5 → TRIGGERED
```

**Saves ~10 s** on the first scale-up.

With 1 dynamic storage node already provisioning:

```
effective_τ = 0.25 + 1×0.10 = 0.35
```

A second scale-up only triggers if score ≥ 0.35 (still low enough for genuine
stress, but filtering transient spikes).

With 4 dynamic storage nodes:

```
effective_τ = min(0.25 + 4×0.10, 0.65) = 0.65
```

The system needs very strong degradation (score ≥ 0.65) to add a 5th node.

### `osken-controller.env` changes

```bash
# Existing (becomes compute-only):
SCALEUP_SCORE_THRESHOLD=0.40
SCALEUP_REQUIRED=2

# New — Adaptive storage scale-up threshold
SCALEUP_STORAGE_BASE_THRESHOLD=0.25
SCALEUP_STORAGE_THRESHOLD_INCREMENT=0.10
SCALEUP_STORAGE_MAX_THRESHOLD=0.65
SCALEUP_STORAGE_WINDOW_SIZE=3
SCALEUP_STORAGE_REQUIRED=1

# Updated scale-down defaults
SCALEDOWN_STORAGE_COOLDOWN_S=120
SCALE_DOWN_STORAGE_WINDOW_SIZE=15
SCALE_DOWN_STORAGE_REQUIRED=9
```

---

## Phase 1 — Priority Queue (Storage-First)

### Concept

Replace `queue.Queue` (FIFO) with `queue.PriorityQueue` in `ElasticityManager`.
When both a `DataAlert` and `ComputeAlert` arrive simultaneously, storage goes
first because it takes longer to provision.

### Priority Order

| Priority | Alert type | Rationale |
|----------|-----------|-----------|
| 1 | `DataAlert` | Storage scale-up — slowest to provision, most critical |
| 2 | `ComputeAlert` | Compute scale-up — fast, but still urgent |
| 3 | `CleanupComputeAlert` | Phase B drain cleanup — time-bounded |
| 4 | `ScaleDownDataAlert` | Storage removal — never urgent |
| 5 | `ScaleDownComputeAlert` | Compute removal — lowest priority |

### Code — `elasticity.py`

#### Priority constants and sequence counter

```python
import itertools

# Alert dispatch priorities (lower number = higher priority).
_PRIORITY_DATA_ALERT           = 1
_PRIORITY_COMPUTE_ALERT        = 2
_PRIORITY_CLEANUP_COMPUTE      = 3
_PRIORITY_SCALEDOWN_DATA       = 4
_PRIORITY_SCALEDOWN_COMPUTE    = 5

# Tie-breaker: monotonically increasing sequence so alerts with the same
# priority are processed in FIFO order.  PriorityQueue compares tuples
# element-by-element; without a sequence, uncomparable dataclasses would
# raise TypeError.
_alert_seq = itertools.count()
```

#### Queue type change

```python
class ElasticityManager:
    def __init__(self, topology_mixin: TopologyMixin) -> None:
        # Currently:
        # self._queue: queue.Queue = queue.Queue()
        # Becomes:
        self._queue: queue.PriorityQueue = queue.PriorityQueue()

        # Rename audit trail to avoid confusion with controller's _active (dict[str, NodeInfo]):
        # Currently:
        # self._active: list[dict] = []           # audit trail (operation history)
        # Becomes:
        self._operation_log: list[dict] = []       # audit trail (operation history)
        ...
```

> **Rename `_active`:** Also update `get_active_operations()` and `_record()`
> in `elasticity.py` to use `self._operation_log` instead of `self._active`.

#### Submit methods — unified type→priority dispatch

> **⚠ Changed from original plan:** The original plan had separate
> `submit_alert()` and `submit()` methods where `submit()` could
> mis-prioritise a `DataAlert` as compute. All three methods are now
> consolidated into a single `submit()` using a type→priority dict.

```python
# Type → priority lookup (covers all alert types)
_ALERT_PRIORITY: dict[type, int] = {
    DataAlert:             _PRIORITY_DATA_ALERT,
    ComputeAlert:          _PRIORITY_COMPUTE_ALERT,
    CleanupComputeAlert:   _PRIORITY_CLEANUP_COMPUTE,
    ScaleDownDataAlert:    _PRIORITY_SCALEDOWN_DATA,
    ScaleDownComputeAlert: _PRIORITY_SCALEDOWN_COMPUTE,
}

def submit(self, alert) -> None:
    """Unified thread-safe enqueue for any alert type."""
    priority = _ALERT_PRIORITY.get(type(alert))
    if priority is None:
        logger.warning("[elasticity] unknown alert type %s — using lowest priority", type(alert).__name__)
        priority = _PRIORITY_SCALEDOWN_COMPUTE
    logger.info("[elasticity] alert submitted (priority=%d): %s", priority, alert)
    self._queue.put((priority, next(_alert_seq), alert))

def submit_cleanup_compute(self, mac: str) -> None:
    """Convenience: enqueue a CleanupComputeAlert by MAC."""
    self.submit(CleanupComputeAlert(mac=mac))
```

`submit_alert()` is **removed** — all callers use `submit()` directly.
Update call-sites in `main_n1.py`/`main_n2.py`:
`self._elasticity.submit_alert(DataAlert(...))` → `self._elasticity.submit(DataAlert(...))`
`self._elasticity.submit_alert(ComputeAlert(...))` → `self._elasticity.submit(ComputeAlert(...))`

#### `_loop()` — unpack the tuple

```python
def _loop(self) -> None:
    while True:
        try:
            _priority, _seq, alert = self._queue.get()     # ← unpack tuple
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
                    logger.warning("[elasticity] unknown alert type: %s", type(alert))
            finally:
                self._busy = False
        except Exception:
            logger.exception("[elasticity] unhandled error in loop")
```

---

## Phase 2 — Async RS Join via Sidecar

### Concept

Move the `rs.add()` operation from `add_network_storage_node.sh` into the
container's `mongo_telemetry.py` sidecar. The sidecar already waits for RS
readiness (`_wait_for_ready()`), so this is a natural extension.

**Benefits:**
- **Retry with backoff** — the sidecar retries `rs.add()` inside the container
  rather than bailing the whole script and cleaning up the container.
- **Unblock controller** — Thread 3 returns after network attach (~5-12 s)
  instead of waiting for RS sync (~34-45 s).
- **Resilience** — independent of primary CPU load on the host; pymongo has
  better timeout/retry handling than `mongosh` in a shell script.

### New Flow (Before vs After)

**Before:**
```
Controller         Shell script                              Container sidecar
    │─ docker run ──────────────────────────────────────────→ starts mongod
    │─ add_network_storage_node.sh ──→ veth+OVS attach
    │                                  rs.add() on primary   
    │                                  wait SECONDARY         ← blocks 20-30s
    │                                  ← returns ────────────│
    │← NodeResult (34-45s total)                              _wait_for_ready()
    │                                                         ← already SECONDARY
    │                                                         emit rs_secondary_ready
```

**After:**
```
Controller         Shell script                  Container sidecar
    │─ docker run ────────────────────────────→ starts mongod
    │   (with RS_ADD_SELF=true,
    │    RS_SEED_HOST=10.0.0.4:27018)
    │                                            _wait_for_network() ← blocks (no eth0)
    │─ add_network_node.sh ──→ veth+OVS attach
    │← NodeResult (5-12s total)                  _wait_for_network() returns (eth0 OK)
    │                                            _rs_self_join() ← retry/backoff
    │                                              rs.add() on primary
    │                                            _wait_for_ready()
    │                                              wait SECONDARY (20-30s)
    │                                            emit rs_secondary_ready
```

Thread 3 is free after 5-12 s. The RS join happens asynchronously inside the
container. The VIP promotion still waits for `rs_secondary_ready`.

### Step 2a — Add env vars to `_docker_run_storage()`

**File:** `source/sdn_controller/elasticity/storage_node_manager.py`

The `_docker_run_storage()` method gets two new env vars passed to the
container:

```python
def _docker_run_storage(self, name: str, rs_name: str, port: int, lan: int,
                        rs_seed_host: str | None = None) -> tuple[bool, str, str]:
    ...
    cmd = [
        "docker", "run", "-dit",
        "--network", "none",
        "--name", name,
        "-v", f"{vol}:/data/db",
        "-e", f"LAN_ID=lan{lan}",
        "-e", f"MONGO_REPLSET={rs_name}",
        "-e", f"MONGO_PORT={port}",
        "-e", f"CONTAINER_NAME={name}",
    ]
    # If rs_seed_host is provided, the sidecar will self-join the RS
    if rs_seed_host:
        cmd += ["-e", "RS_ADD_SELF=true", "-e", f"RS_SEED_HOST={rs_seed_host}"]
    cmd.append("edge_storage_server")
    return self._run_cmd(cmd)
```

The `rs_seed_host` is the `host:port` of the known RS primary (or seed).

### Step 2a (cont.) — Derive primary IP from LAN topology

**File:** `source/sdn_controller/elasticity/storage_node_manager.py`

> **⚠ Changed from original plan:** The original plan used
> `_resolve_container_ip()` with `docker inspect`, but the OS-Ken controller
> runs **inside a container** without the Docker socket mounted, so
> `docker inspect` would fail.
>
> Primary storage containers have **deterministic IPs** assigned by the
> network setup scripts: `10.0.<lan−1>.4` (e.g., lan1 → `10.0.0.4`,
> lan2 → `10.0.1.4`). We derive the seed host directly from the LAN number.

Called from `add_storage_node()`:

```python
def add_storage_node(self, lan, name, rs_name, primary_container, port=27018,
                     ip=None, mac=None):
    # Derive primary IP from LAN topology convention:
    #   lan1 → 10.0.0.4, lan2 → 10.0.1.4
    primary_ip = f"10.0.{lan - 1}.4"
    rs_seed_host = f"{primary_ip}:{port}"
    logger.info("[node_add] RS seed host for lan%d: %s", lan, rs_seed_host)

    # Step 1: docker run
    ok, stdout, stderr = self._docker_run_storage(name, rs_name, port, lan,
                                                  rs_seed_host=rs_seed_host)
    ...
```

`_resolve_container_ip()` is **not needed** and should **not** be added.

### Step 2b — `_rs_self_join()` in sidecar

**File:** `source/docker/edge_storage_server/mongo_telemetry.py`

New function added before `_wait_for_ready()`:

```python
import socket

_RS_MAX_ATTEMPTS    = 5
_RS_INITIAL_BACKOFF = 3.0    # seconds
_RS_BACKOFF_FACTOR  = 2.0
_NETWORK_WAIT_TIMEOUT = 120.0  # seconds to wait for eth0 + seed connectivity


def _wait_for_network(seed_host: str, seed_port: int, timeout: float = _NETWORK_WAIT_TIMEOUT) -> bool:
    """Block until eth0 exists AND the seed host is TCP-reachable.

    The container starts with ``--network none``.  ``add_network_node.sh``
    creates the veth pair and attaches eth0 *after* ``docker run``.
    This function must complete before ``_rs_self_join()`` can connect
    to the RS primary.

    Returns True when connectivity is confirmed, False on timeout.
    """
    deadline = time.monotonic() + timeout
    logger.info("Waiting for network (eth0 + TCP %s:%d) ...", seed_host, seed_port)
    while time.monotonic() < deadline:
        # 1. Does the network interface exist yet?
        if not os.path.exists("/sys/class/net/eth0"):
            time.sleep(1)
            continue
        # 2. Can we TCP-connect to the seed host?
        try:
            with socket.create_connection((seed_host, seed_port), timeout=3):
                logger.info("Network ready — seed %s:%d reachable", seed_host, seed_port)
                return True
        except OSError:
            time.sleep(1)
    logger.error("Network wait timed out after %.0fs", timeout)
    return False


def _discover_own_ip() -> str:
    """Discover this container's IP from eth0 (or first non-loopback interface)."""
    preferred = os.environ.get("IFACE", "eth0")
    try:
        import subprocess
        result = subprocess.run(
            ["ip", "-4", "-o", "addr", "show", preferred],
            capture_output=True, text=True, timeout=5,
        )
        # Output: "2: eth0    inet 10.0.0.7/24 brd 10.0.0.255 scope global eth0"
        for part in result.stdout.split():
            if "/" in part and "." in part:
                return part.split("/")[0]
    except Exception:
        pass
    return ""


def _rs_self_join() -> None:
    """Join this node to the replica set by connecting to the seed host.

    Steps:
      1. Connect to RS_SEED_HOST, query isMaster to find the current primary.
      2. Discover own IP from eth0.
      3. Clean stale member at own host:port if present.
      4. rs.add({host: own_ip:port, priority: 0}) with retry/backoff.

    Environment:
      RS_SEED_HOST  — host:port of a known RS member (seed)
      MONGO_PORT    — port this mongod listens on
      MONGO_REPLSET — replica set name (for validation)
    """
    seed_host = os.environ.get("RS_SEED_HOST", "")
    port      = int(os.environ.get("MONGO_PORT", "27018"))

    if not seed_host:
        logger.warning("RS_ADD_SELF=true but RS_SEED_HOST not set — skipping self-join")
        return

    # Parse host:port for the network wait
    seed_parts = seed_host.rsplit(":", 1)
    seed_ip    = seed_parts[0]
    seed_port_int = int(seed_parts[1]) if len(seed_parts) > 1 else port

    # ── Wait for eth0 + seed connectivity (blocks until add_network_node.sh runs) ──
    if not _wait_for_network(seed_ip, seed_port_int):
        logger.error("Network never became available — cannot self-join RS")
        return

    own_ip = _discover_own_ip()
    if not own_ip:
        logger.error("Could not discover own IP — cannot self-join RS")
        return
    member_host = f"{own_ip}:{port}"
    logger.info("RS self-join: seed=%s own=%s", seed_host, member_host)

    backoff = _RS_INITIAL_BACKOFF
    for attempt in range(1, _RS_MAX_ATTEMPTS + 1):
        try:
            # Connect to seed to discover the current primary
            client = MongoClient(f"mongodb://{seed_host}/",
                                 serverSelectionTimeoutMS=5000,
                                 directConnection=True)
            try:
                is_master = client.admin.command("isMaster")
                primary_host = is_master.get("primary")
                logger.info("Attempt %d/%d: isMaster → primary=%s, setName=%s",
                            attempt, _RS_MAX_ATTEMPTS, primary_host,
                            is_master.get("setName", "?"))
            finally:
                client.close()

            if not primary_host:
                logger.warning("Attempt %d/%d: no primary in isMaster response — retrying in %.0fs",
                               attempt, _RS_MAX_ATTEMPTS, backoff)
                time.sleep(backoff)
                backoff *= _RS_BACKOFF_FACTOR
                continue

            # Connect to the actual primary
            primary_client = MongoClient(f"mongodb://{primary_host}/",
                                        serverSelectionTimeoutMS=5000,
                                        directConnection=True)
            try:
                # Single config fetch: remove stale member (if any) AND add
                # ourselves in one replSetReconfig to avoid version drift.
                config = primary_client.admin.command("replSetGetConfig")["config"]
                logger.info("Attempt %d/%d: RS config v%d, %d members: %s",
                            attempt, _RS_MAX_ATTEMPTS, config["version"],
                            len(config["members"]),
                            [m["host"] for m in config["members"]])

                # Clean stale member at our host:port if present
                original_len = len(config["members"])
                config["members"] = [
                    m for m in config["members"] if m.get("host") != member_host
                ]
                if len(config["members"]) < original_len:
                    logger.info("Removing stale RS member at %s from config", member_host)

                # rs.add() — append ourselves
                max_id = max(m["_id"] for m in config["members"])
                config["version"] += 1
                config["members"].append({
                    "_id": max_id + 1,
                    "host": member_host,
                    "priority": 0,
                })
                primary_client.admin.command("replSetReconfig", config)
                logger.info("RS self-join succeeded: added %s to RS (attempt %d, new config v%d, %d members)",
                            member_host, attempt, config["version"], len(config["members"]))
                return
            finally:
                primary_client.close()

        except PyMongoError as exc:
            logger.warning("Attempt %d/%d: RS self-join failed: %s — retrying in %.0fs",
                           attempt, _RS_MAX_ATTEMPTS, exc, backoff)
            time.sleep(backoff)
            backoff *= _RS_BACKOFF_FACTOR

    logger.error("RS self-join FAILED after %d attempts — node will not join RS", _RS_MAX_ATTEMPTS)
```

> **⚠ Changed from original plan:** `_remove_member_from_config()` is
> **removed**. The stale-member cleanup and `rs.add()` now happen in a
> **single `replSetReconfig`** call (one config fetch, one version bump)
> to eliminate the version-drift risk from two consecutive reconfigs.

#### Updated `main()` in `mongo_telemetry.py`

> **⚠ Updated 2026-04-13 (run `154833` follow-up):** The original flow created
> the ZMQ socket *after* `_wait_for_ready()`. A follow-up test showed this
> blocks forever when RS join fails — no telemetry, no events. The socket is
> now created **before** `_wait_for_ready()`, and `_wait_for_ready()` has a
> configurable timeout (`RS_READY_TIMEOUT_S`, default 300 s). See
> [`sidecar_zmq_timeout_fix.md`](sidecar_zmq_timeout_fix.md).

```python
def main() -> None:
    global _sock

    logger.info("mongo_telemetry starting: mac=%s interval=%.1fs", _get_server_mac(), INTERVAL_S)

    # If RS_ADD_SELF is set, self-join the RS first (with retry/backoff).
    # _rs_self_join() calls _wait_for_network() internally, ensuring eth0
    # is available when it returns (even if the join itself fails).
    if os.environ.get("RS_ADD_SELF") == "true":
        _rs_self_join()

    # Create ZMQ socket EARLY — before _wait_for_ready() — so that even
    # if the RS join failed or the node is stuck in STARTUP2, diagnostic
    # heartbeats can still reach the controller.
    _sock = _ctx.socket(zmq.PUSH)
    _sock.connect(AGGREGATOR_PULL_ADDR)
    logger.info("ZMQ PUSH socket connected to %s", AGGREGATOR_PULL_ADDR)

    # Wait for RS state with timeout — returns None if timeout expires.
    state_str = _wait_for_ready()

    # Emit rs_secondary_ready if applicable (fast path for VIP promotion).
    if state_str == "SECONDARY":
        ...  # (unchanged)
    elif state_str is None:
        logger.warning("entering telemetry loop without confirmed RS state")

    logger.info("Entering normal telemetry loop")
    while True:
        ...  # (unchanged)
```

> **Important sequencing note:** `_rs_self_join()` runs **before**
> `_wait_for_ready()`. Inside `_rs_self_join()`, `_wait_for_network()` blocks
> until `add_network_node.sh` has attached eth0 and the seed host is
> TCP-reachable. Only then does it attempt `rs.add()`. The ZMQ socket is
> created **after** `_rs_self_join()` (eth0 guaranteed) but **before**
> `_wait_for_ready()`, so telemetry can flow while the node syncs.
> `_wait_for_ready()` blocks until the node reaches SECONDARY state (with a
> configurable timeout: `RS_READY_TIMEOUT_S`, default 300 s).
>
> **Timeline:**
> ```
> entrypoint.sh: mongod starts → sidecar starts
> sidecar:       _wait_for_network() blocks (no eth0 yet)
>   ── meanwhile: controller runs add_network_node.sh → attaches eth0 ──
> sidecar:       _wait_for_network() returns (eth0 + TCP OK)
> sidecar:       _rs_self_join() → rs.add() with retry/backoff
> sidecar:       _wait_for_ready() → blocks until SECONDARY
> sidecar:       emit rs_secondary_ready
> ```

### Step 2c — Switch to `add_network_node.sh`

**File:** `source/sdn_controller/elasticity/storage_node_manager.py`

Replace Step 2 (network attach + RS join) with network-only attach:

```python
def add_storage_node(self, lan, name, rs_name, primary_container, port=27018,
                     ip=None, mac=None):
    ...
    # Step 2: network attach only (RS join handled by sidecar)
    script_args = ["--lan", str(lan), "--name", name]
    if ip:
        script_args += ["--ip", ip]
    if mac:
        script_args += ["--mac", mac]
    ok, result_ip, result_mac, stdout2, stderr2 = self._run_script(
        SCRIPTS_DIR / "add_network_node.sh",       # ← was add_network_storage_node.sh
        script_args,
    )
    ...
```

The `--rs-name`, `--primary`, and `--port` args are no longer passed (not
needed by `add_network_node.sh`).

### Step 2d — No change in `_handle_data()`

The existing comment in `elasticity.py` already says:

```python
# Do NOT call add_storage_mac() here — the node is not SECONDARY yet.
# VIP registration is deferred until rs_secondary_ready arrives.
```

This is correct — the VIP promotion path (via `_process_secondary_events()` /
`_promote_storage_from_telemetry()`) remains unchanged.

---

## Phase 3 — ~~Simplify~~ Delete `add_network_storage_node.sh`

> **Status:** Superseded by Phase 2.

**File:** `source/scripts/network/add_network_storage_node.sh`

With RS join moved to the sidecar (Phase 2), this script is functionally
identical to `add_network_node.sh` — both do veth+OVS attachment only.
**Delete** the script to avoid maintaining two copies. All callers switch to
`add_network_node.sh`.

The `remove_network_storage_node.sh` script is **not affected** — it handles
teardown (flush flows, docker stop, OVS cleanup, volume rm) and does not
perform `rs.add()`.

The `rs_cleanup_stale_member()` function from Fix A (storage reliability plan)
is **superseded** by the sidecar's `_rs_self_join()` which performs the same
stale cleanup before `rs.add()`.

---

## Phase 4 — Documentation

### Files to update

| File | Change |
|------|--------|
| `elasticity_overview.md` | Deprecate: shared threshold, shared window, `add_network_storage_node.sh`, "No Explicit Cooldown" claim |
| `elasticity_overview.md` | Add: adaptive threshold formula, priority queue, async RS join via sidecar |
| `scale_up_trigger_plan.md` | Add deprecation note: storage now uses separate adaptive threshold |
| `storage_reliability_plan.md` | Add note: Fix A (`rs_cleanup_stale_member` in shell) superseded by sidecar `_rs_self_join()` |
| `node_add_optimization_plan.md` | Add note: Phase C (remove SECONDARY wait) superseded by async RS join |

### Future improvements to document

| Improvement | Description | Expected benefit |
|-------------|-------------|-----------------|
| Pre-create containers | `docker create` ahead of time, `docker start` on demand | Save ~1-3 s docker run overhead |
| I/O thread pool | `concurrent.futures.ThreadPoolExecutor` for parallel subprocess calls in Thread 3 | Parallel network attach for compute+storage |

---

## Files Modified (Summary)

| File | Phase | Change |
|------|-------|--------|
| `source/sdn_controller/main_n1.py` | 0 | Adaptive threshold, `_count_dynamic_storage_nodes()`, separate storage window/required, new env var reads, updated scale-down defaults |
| `source/sdn_controller/main_n2.py` | 0 | Same as main_n1 (**note: `_evaluate_scale_up()` has compute-first, storage-second order — reversed from n1**) |
| `source/scripts/osken-controller.env` | 0 | New env vars for adaptive threshold + updated scale-down defaults |
| `source/sdn_controller/elasticity/elasticity.py` | 1 | `PriorityQueue`, priority constants, `_alert_seq`, unified `submit()` with type→priority dict, rename `_active` → `_operation_log` |
| `source/sdn_controller/elasticity/storage_node_manager.py` | 2a,2c | `rs_seed_host` env var (deterministic IP from LAN), switch to `add_network_node.sh` |
| `source/docker/edge_storage_server/mongo_telemetry.py` | 2b | `_wait_for_network()`, `_rs_self_join()`, `_discover_own_ip()`, updated `main()` |
| `source/scripts/network/add_network_storage_node.sh` | 3 | **DELETE** |
| `docs/operation/elasticy_manager/elasticity_overview.md` | 4 | Deprecation notes + new sections |

---

## Verification

1. Run same `phases.json` test, verify storage triggers at ~10 s (was ~20 s)
   — check log line `[scale-up] storage triggered ... eff_τ=0.25`.
2. Verify second storage node only triggers if effective threshold (0.35)
   is breached — no pile-up.
3. `storage_count` never drops to 0 during `local_moderate` phase.
4. `rs_secondary_ready` arrives even under high CPU — check for `RS self-join
   succeeded` in container logs.
5. Priority queue: when both alerts fire simultaneously, DataAlert is
   processed before ComputeAlert — check log ordering.
6. Scale-down doesn't remove proactively added nodes prematurely (120 s cooldown,
   9/15 window) — check log line `[scale-down] storage within Xfs cooldown`.
7. `add_network_storage_node.sh` is not called anywhere — grep to confirm.

---

## Review Errata (2026-04-13)

Issues found during plan review, with resolutions applied above:

| # | Severity | Issue | Resolution |
|---|----------|-------|------------|
| 15 | **Critical** | `_rs_self_join()` runs before network attach — no eth0, cannot reach primary | Added `_wait_for_network()` that polls for eth0 + TCP connectivity before `_rs_self_join()` |
| 5 | **High** | `_resolve_container_ip()` uses `docker inspect` inside containerised controller | Replaced with deterministic IP from LAN topology (`10.0.<lan−1>.4`); removed `_resolve_container_ip()` |
| 10 | **Medium** | Double config fetch in stale cleanup + rs.add — version drift risk | Merged into single `replSetGetConfig` → filter stale + append new → single `replSetReconfig`; removed `_remove_member_from_config()` |
| 6 | **Medium** | `submit()` doesn’t distinguish `DataAlert` from `ComputeAlert` for priority | Unified all submit methods into single `submit()` with `_ALERT_PRIORITY` type→priority dict; removed `submit_alert()` |
| 1 | **Low** | Ambiguous `_active` — two different dicts in `elasticity.py` vs `main_n*.py` | Renamed `elasticity.py`’s `_active` → `_operation_log`; clarified which `_active` is used in `_count_dynamic_storage_nodes()` |
| 3 | **Low** | Python fallback defaults not updated alongside `.env` changes | Explicitly noted that `main_n1.py`/`main_n2.py` fallback strings must change (cooldown `"75"→"120"`, window `"12"→"15"`, required `"7"→"9"`) |
| 9 | **Low** | Dead `import netifaces` comment in `_rs_self_join()` code | Removed; `_discover_own_ip()` uses `subprocess` + `ip` command (iproute2 present in image) |
| 13 | **Low** | `main_n2.py` structural differences not accounted for | Added explicit note: `main_n2.py` evaluates compute-first then storage (reversed from n1) |
