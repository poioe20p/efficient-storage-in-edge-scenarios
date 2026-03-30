# Thread 3 — Runtime Node Addition Plan

## Overview

Thread 3 (the **Elasticity & Placement Manager**) is responsible for mutating the
infrastructure in response to latency breaches detected by Thread 2. This plan
covers the **add-only** half of that responsibility: spawning new `edge_server`
and `edge_storage_server` containers at runtime and wiring them into the
running network.

The mechanism is **atomic by idempotency**: each step checks current state
before acting, partial failures leave a clean slate the next time the operation
is retried, and every step is individually timed to produce a structured
execution record.

## Architecture: Three-Thread Interaction

---

```
Thread 2 (Observer)     Thread 3 (Elasticity Mgr)      Infrastructure
       |                        |
       |-- Alert(type, lan) --> |
       |                        |-- NodeAdder.add_edge_server()
       |                        |      ├─ docker run           (timed)
       |                        |      ├─ add_network_node.sh  (timed)
       |                        |      └─ returns NodeResult
       |                        |
       |                        |-- TopologyMixin.add_server_mac()
       |                        |      └─ Thread 1 auto-picks new server up
```

Thread 3 is a long-lived daemon thread that blocks on a `threading.Queue`.
Thread 2 posts typed `Alert` objects; Thread 3 pops and dispatches them.
Thread 1 never touches Thread 3 — it only reads the shared VIP pool that Thread
3 mutates through `TopologyMixin.add_server_mac()` / `add_storage_mac()`.

---

## Files

| File                                                   | Action           | Purpose                                                               |
| ------------------------------------------------------ | ---------------- | --------------------------------------------------------------------- |
| `source/sdn_controller/node_manager.py`              | **Create** | `NodeAdder` — per-step lifecycle with timing                       |
| `source/sdn_controller/elasticity.py`                | **Create** | `ElasticityManager` — Thread 3 queue/dispatch                      |
| `source/sdn_controller/main_n1.py`                   | **Modify** | Instantiate `ElasticityManager`, post alerts from Thread 2 callback |
| `source/scripts/network/add_network_node.sh`         | **Modify** | Emit `RESULT_IP=<ip>` on success for machine-readable parsing       |
| `source/scripts/network/add_network_storage_node.sh` | **Modify** | Same `RESULT_IP=<ip>` emission                                      |

---

## Phase 1 — `node_manager.py`

### `StepTimings` dataclass

Captures elapsed wall-clock time for each lifecycle phase, in seconds.
`total_s` is always the wall-clock elapsed from the very first step to the
last — not the sum of individual steps, so it includes inter-step overhead.

```python
from dataclasses import dataclass, field

@dataclass
class StepTimings:
    docker_run_s:       float = 0.0   # docker run --network none
    network_attach_s:   float = 0.0   # add_network_node.sh
    replica_set_join_s: float = 0.0   # add_network_storage_node.sh RS section (storage only)
    total_s:            float = 0.0
```

### `NodeOperationState` enum

Gives Thread 3 (and the thesis demo) a clear view of where each operation is.

```python
from enum import Enum, auto

class NodeOperationState(Enum):
    PENDING            = auto()   # queued, not started
    RUNNING_CONTAINER  = auto()   # docker run in progress
    ATTACHING_NETWORK  = auto()   # veth + OVS attachment in progress
    JOINING_RS         = auto()   # rs.add() in progress (storage only)
    DONE               = auto()   # fully operational
    FAILED             = auto()   # error; container cleaned up
```

### `NodeResult` dataclass

Returned by every `NodeAdder` method. Holds the operation outcome plus full
script output so the caller can log or forward it.

```python
@dataclass
class NodeResult:
    success:        bool
    container_name: str
    ip:             str | None       # None on failure
    timings:        StepTimings
    state:          NodeOperationState
    stdout:         str = ""
    stderr:         str = ""
```

### `NodeAdder` class

```python
import subprocess, time, logging, shlex
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent.parent / "scripts" / "network"
logger = logging.getLogger("os_ken.node_manager")

class NodeAdder:
    """Stateless helper — each method is a self-contained, timed, idempotent lifecycle."""

    def add_edge_server(self, lan: int, name: str) -> NodeResult:
        """
        Full lifecycle for an edge_server container:
          1. docker run  --network none  edge_server
          2. add_network_node.sh --lan <lan> --name <name>
        """
        timings = StepTimings()
        t_total = time.perf_counter()

        # ── Step 1: docker run ────────────────────────────────────────────
        state = NodeOperationState.RUNNING_CONTAINER
        t0 = time.perf_counter()
        ok, stdout, stderr = self._docker_run_server(name)
        timings.docker_run_s = time.perf_counter() - t0

        if not ok:
            timings.total_s = time.perf_counter() - t_total
            return NodeResult(False, name, None, timings, NodeOperationState.FAILED,
                              stdout, stderr)

        # ── Step 2: network attachment ────────────────────────────────────
        state = NodeOperationState.ATTACHING_NETWORK
        t0 = time.perf_counter()
        ok, ip, stdout2, stderr2 = self._run_script(
            SCRIPTS_DIR / "add_network_node.sh",
            ["--lan", str(lan), "--name", name],
        )
        timings.network_attach_s = time.perf_counter() - t0
        timings.total_s = time.perf_counter() - t_total

        if not ok:
            self._cleanup_container(name)
            return NodeResult(False, name, None, timings, NodeOperationState.FAILED,
                              stdout + stdout2, stderr + stderr2)

        return NodeResult(True, name, ip, timings, NodeOperationState.DONE,
                          stdout + stdout2, stderr + stderr2)

    def add_storage_node(self, lan: int, name: str,
                         rs_name: str, primary_container: str,
                         port: int = 27018) -> NodeResult:
        """
        Full lifecycle for an edge_storage_server container:
          1. docker run  --network none  edge_storage_server  mongod  --replSet ...
          2. add_network_storage_node.sh  (handles veth + OVS + rs.add())
        """
        timings = StepTimings()
        t_total = time.perf_counter()

        # ── Step 1: docker run ────────────────────────────────────────────
        t0 = time.perf_counter()
        ok, stdout, stderr = self._docker_run_storage(name, rs_name, port)
        timings.docker_run_s = time.perf_counter() - t0

        if not ok:
            timings.total_s = time.perf_counter() - t_total
            return NodeResult(False, name, None, timings, NodeOperationState.FAILED,
                              stdout, stderr)

        # ── Step 2: network attach + RS join ─────────────────────────────
        t0 = time.perf_counter()
        ok, ip, stdout2, stderr2 = self._run_script(
            SCRIPTS_DIR / "add_network_storage_node.sh",
            ["--lan", str(lan), "--name", name,
             "--rs-name", rs_name, "--primary", primary_container,
             "--port", str(port)],
        )
        timings.network_attach_s = time.perf_counter() - t0
        # The storage script does both network attach AND rs.add() internally.
        # Split timing is available in the script's stdout via labelled sections
        # if needed for thesis instrumentation.
        timings.total_s = time.perf_counter() - t_total

        if not ok:
            self._cleanup_container(name)
            return NodeResult(False, name, None, timings, NodeOperationState.FAILED,
                              stdout + stdout2, stderr + stderr2)

        return NodeResult(True, name, ip, timings, NodeOperationState.DONE,
                          stdout + stdout2, stderr + stderr2)
```

### Idempotency checks in `_docker_run_*`

Before calling `docker run`, inspect the container state. Three cases:

| Existing state | Action                                                      |
| -------------- | ----------------------------------------------------------- |
| Not found      | Create normally                                             |
| Running        | Skip `docker run` (already created); proceed to next step |
| Stopped/exited | Remove and recreate                                         |

```python
def _docker_run_server(self, name: str) -> tuple[bool, str, str]:
    state = self._container_state(name)
    if state == "running":
        logger.info("container %s already running — skipping docker run", name)
        return True, "", ""
    if state is not None:
        self._cleanup_container(name)   # remove stopped remnant
    cmd = ["docker", "run", "-dit", "--network", "none", "--name", name, "edge_server"]
    return self._run_cmd(cmd)
```

### IP extraction from script stdout

The scripts emit a `RESULT_IP=<ip>` line at the very end (see Phase 4).
`_run_script` parses it:

```python
import re as _re
_RESULT_IP_RE = _re.compile(r'^RESULT_IP=(\S+)', _re.MULTILINE)

def _run_script(self, script: Path, args: list[str]) -> tuple[bool, str | None, str, str]:
    cmd = ["/bin/bash", str(script)] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    ip = None
    m = _RESULT_IP_RE.search(result.stdout)
    if m:
        ip = m.group(1)
    ok = result.returncode == 0
    return ok, ip, result.stdout, result.stderr
```

### Timing log on every operation

```python
def _log_timings(self, result: NodeResult) -> None:
    t = result.timings
    logger.info(
        "node_add timing  container=%s  docker_run=%.2fs  net_attach=%.2fs"
        "  rs_join=%.2fs  total=%.2fs  state=%s",
        result.container_name,
        t.docker_run_s, t.network_attach_s,
        t.replica_set_join_s, t.total_s,
        result.state.name,
    )
```

---

## Phase 2 — `elasticity.py`

### Alert types

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class ComputeAlert:
    lan: int           # target LAN (1 or 2)
    network_id: str    # e.g. "lan1"

@dataclass(frozen=True)
class DataAlert:
    lan: int
    network_id: str
    rs_name: str
    primary_container: str
    port: int = 27018
```

### `ElasticityManager`

```python
import threading
import queue
import logging
from .node_manager import NodeAdder, ComputeAlert, DataAlert

logger = logging.getLogger("os_ken.elasticity")

_COUNTER = {}   # network_id -> int, used to generate unique container names

class ElasticityManager:
    def __init__(self, topology_mixin) -> None:
        self._queue: queue.Queue = queue.Queue()
        self._adder = NodeAdder()
        self._topo  = topology_mixin            # TopologyMixin reference
        self._thread = threading.Thread(
            target=self._loop, name="elasticity", daemon=True
        )
        self._active: list[dict] = []           # audit trail for demo / observability

    def start(self) -> None:
        self._thread.start()
        logger.info("elasticity manager started")

    def submit_alert(self, alert) -> None:
        """Thread-safe. Called by Thread 2's on_update callback."""
        logger.info("alert submitted: %s", alert)
        self._queue.put(alert)

    def get_active_operations(self) -> list[dict]:
        return list(self._active)

    # ── private ──────────────────────────────────────────────────────────

    def _loop(self) -> None:
        while True:
            try:
                alert = self._queue.get()
                if isinstance(alert, ComputeAlert):
                    self._handle_compute(alert)
                elif isinstance(alert, DataAlert):
                    self._handle_data(alert)
                else:
                    logger.warning("unknown alert type: %s", type(alert))
            except Exception:  # noqa: BLE001
                logger.exception("elasticity loop error")

    def _handle_compute(self, alert: ComputeAlert) -> None:
        ctr = _COUNTER.get(alert.network_id, 0) + 1
        _COUNTER[alert.network_id] = ctr
        name = f"edge_server_{alert.network_id}_dyn{ctr}"
        logger.info("[compute] spawning %s on LAN %d", name, alert.lan)

        result = self._adder.add_edge_server(lan=alert.lan, name=name)
        self._adder._log_timings(result)
        self._active.append({"type": "compute", "name": name, "result": result})

        if result.success:
            mac = self._resolve_mac(name)
            if mac:
                self._topo.add_server_mac(mac)
                logger.info("[compute] %s online at %s (mac=%s)", name, result.ip, mac)

    def _handle_data(self, alert: DataAlert) -> None:
        ctr = _COUNTER.get(alert.network_id, 0) + 1
        _COUNTER[alert.network_id] = ctr
        name = f"edge_storage_{alert.network_id}_dyn{ctr}"
        logger.info("[data] spawning %s on LAN %d", name, alert.lan)

        result = self._adder.add_storage_node(
            lan=alert.lan, name=name,
            rs_name=alert.rs_name,
            primary_container=alert.primary_container,
            port=alert.port,
        )
        self._adder._log_timings(result)
        self._active.append({"type": "data", "name": name, "result": result})

        if result.success:
            mac = self._resolve_mac(name)
            if mac:
                self._topo.add_storage_mac(mac)
                logger.info("[data] %s online at %s (mac=%s)", name, result.ip, mac)

    def _resolve_mac(self, container_name: str) -> str | None:
        """Read the MAC address assigned by add_network_*.sh via docker inspect."""
        try:
            import subprocess, json
            raw = subprocess.check_output(
                ["docker", "inspect", "--format", "{{json .NetworkSettings.Networks}}", container_name],
                text=True,
            )
            # For --network none containers their networking is set up outside Docker.
            # Read from the container's eth0 directly instead.
            mac = subprocess.check_output(
                ["docker", "exec", container_name, "cat", "/sys/class/net/eth0/address"],
                text=True,
            ).strip()
            return mac
        except Exception:  # noqa: BLE001
            logger.warning("could not resolve MAC for %s", container_name)
            return None
```

---

## Phase 3 — Script Adaptations

Both scripts need a **single extra line** at the very end of `main()` that emits
the machine-readable IP so `NodeAdder._run_script()` can parse it:

> **Location in both scripts:** at the end of the success banner (after the last
> `echo "==="` line).

```bash
# add_network_node.sh  AND  add_network_storage_node.sh  — same addition
# ← last line in main() currently:
echo "============================================================================"

# ← add after it:
echo "RESULT_IP=${IP}"    # machine-readable; parsed by NodeAdder
```

No other structural changes are required. The scripts already exit non-zero on
any failure due to `set -euo pipefail`, so `subprocess.run` return-code checking
is reliable.

---

## Phase 4 — Wiring into `main_n1.py`

```python
# In KenLearnAndLog.__init__(), after self._telemetry.start():

from .elasticity import ElasticityManager, ComputeAlert, DataAlert

self._elasticity = ElasticityManager(topology_mixin=self)
self._elasticity.start()
```

Thread 2's callback (`_print_summary`) becomes the threshold evaluator:

```python
_TAU_PROC_MS  = float(os.environ.get("TAU_PROC_MS",  "200"))
_TAU_DADOS_MS = float(os.environ.get("TAU_DADOS_MS", "150"))

def _make_on_update(app):
    def _on_update(summary: TelemetrySummary) -> None:
        ds = summary.domain_summary
        lan = int(summary.network_id.replace("lan", ""))  # "lan1" -> 1

        if ds.avg_time_proc_ms > _TAU_PROC_MS:
            app._elasticity.submit_alert(ComputeAlert(lan=lan, network_id=summary.network_id))

        if ds.avg_time_db_ms > _TAU_DADOS_MS:
            app._elasticity.submit_alert(DataAlert(
                lan=lan,
                network_id=summary.network_id,
                rs_name=f"rs_net{lan}",
                primary_container=f"edge_storage_server_n{lan}",
            ))
    return _on_update
```

---

## Timing Model

Every `NodeResult` carries a `StepTimings` record. The table below shows which
steps contribute to each field and what to expect in a healthy run:

| Field                  | What it measures                                                                        | Typical range |
| ---------------------- | --------------------------------------------------------------------------------------- | ------------- |
| `docker_run_s`       | `docker run` → container enters `running` state                                    | 0.1 – 1 s    |
| `network_attach_s`   | veth creation → OVS port → IP config (+ rs.add for storage)                           | 1 – 10 s     |
| `replica_set_join_s` | Not used directly (absorbed in `network_attach_s`); read from script stdout if needed | —            |
| `total_s`            | Wall clock from first step to last — includes inter-step overhead                      | 1.5 – 15 s   |

These timings are emitted at `INFO` level by `_log_timings()` and can be fed
into a Prometheus counter or written to the shared MongoDB later.

---

## Idempotency State Machine

```
Trigger
  │
  ▼
_container_state(name)?
  ├─ None    → docker run           RUNNING_CONTAINER
  ├─ running → skip                 → ATTACHING_NETWORK
  └─ stopped → cleanup → docker run RUNNING_CONTAINER
                │
                ▼
          Script check: is eth0 already configured?
          ├─ No  → run script       ATTACHING_NETWORK
          └─ Yes → skip             → (JOINING_RS / DONE)
                    │
                    ▼ (storage only)
              rs.status(): member present?
              ├─ No  → rs.add()     JOINING_RS
              └─ Yes → skip         → DONE
```

*(The per-step idempotency checks inside the scripts are handled by the scripts
themselves via `validate_requirements` and the existing OVS/Docker state
inspection. The Python layer adds a pre-flight `docker inspect` to avoid
re-running `docker run` when a container already exists from a prior partial
attempt.)*

---

## Verification Checklist

- [ ] Manually `queue.put(ComputeAlert(lan=1, network_id="lan1"))` and verify a
  new container appears on LAN 1 with correct IP/MAC and is reachable from the
  switch.
- [ ] Verify `NodeResult.timings.total_s` is logged at INFO level.
- [ ] Kill the script mid-execution (e.g. via SIGKILL on the bash process) and
  verify the Docker container is cleaned up and `state == FAILED`.
- [ ] Re-submit the same alert and verify the operation succeeds cleanly
  (idempotency — no duplicate container error).
- [ ] After a successful `add_edge_server`, confirm
  `TopologyMixin.vip_server_pool` contains the new MAC and Thread 1 starts
  routing VIP_Web traffic to it.

---

---

# Addendum — Dynamic Node Telemetry Fix

## Problem Statement

Dynamically spawned nodes do **not** publish telemetry to their respective
aggregator. Two independent root causes:

| Node type               | Root cause                                                                                                             | Effect                                                                                                   |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `edge_server`         | `_docker_run_server` passes no `-e` flags → `AGGREGATOR_PULL_ADDR` defaults to `""` → ZMQ socket is `None` | `ZmqMetricSender.send()` silently no-ops every event                                                   |
| `edge_storage_server` | `_docker_run_storage` passes `mongod ...` as CMD, overriding `CMD ["/entrypoint.sh"]` from the Dockerfile        | `entrypoint.sh` never executes → `python3 /mongo_telemetry.py` (the telemetry sidecar) never starts |

**Note:** The CMD-override issue also affects the *static* storage nodes
launched in `build_network_1.sh` and `build_network_2.sh` — their sidecar is
equally not running.

---

## Design Decision: `LAN_ID` Env Var

Instead of requiring `node_manager.py` to know every aggregator address, each
Docker image owns a built-in `LAN → subnet` mapping. The controller only needs
to pass a single `LAN_ID` env var and the container derives the correct
`AGGREGATOR_PULL_ADDR` internally.

**Precedence (both images):** explicit `AGGREGATOR_PULL_ADDR` env var >
`LAN_ID`-derived address > disabled (no telemetry).

The LAN-to-subnet mapping is:

| `LAN_ID` | Subnet          | Aggregator address      |
| ---------- | --------------- | ----------------------- |
| `1`      | `10.0.0.0/24` | `tcp://10.0.0.5:5555` |
| `2`      | `10.0.1.0/24` | `tcp://10.0.1.5:5555` |

This is baked into each image's Python code (the helper function
`_aggregator_addr_from_lan()`).

---

## Files

| File                                                     | Action           | Purpose                                                                           |
| -------------------------------------------------------- | ---------------- | --------------------------------------------------------------------------------- |
| `source/docker/edge_server/source/telemetry.py`        | **Modify** | Add `LAN_ID` → aggregator derivation in `ZmqMetricSender.__init__`           |
| `source/docker/edge_storage_server/mongo_telemetry.py` | **Modify** | Same `LAN_ID` derivation for `AGGREGATOR_PULL_ADDR`                           |
| `source/docker/edge_storage_server/entrypoint.sh`      | **Modify** | Add `MONGO_PORT` env var support; derive `MONGO_URI` from port                |
| `source/docker/edge_storage_server/Dockerfile`         | **Modify** | Add `MONGO_PORT` to ENV block; clear `AGGREGATOR_PULL_ADDR` default           |
| `source/sdn_controller/node_manager.py`                | **Modify** | Pass `LAN_ID` + `SERVER_ID` to both node types; stop CMD override for storage |
| `source/scripts/network/build_network_1.sh`            | **Modify** | Storage: replace CMD override with env vars                                       |
| `source/scripts/network/build_network_2.sh`            | **Modify** | Same as above for LAN 2                                                           |

---

## Phase A — Docker Image Changes (all steps parallel)

### Step A.1 — `edge_server/source/telemetry.py`

Add `LAN_ID` → aggregator address derivation inside `ZmqMetricSender.__init__`.

**Current code:**

```python
class ZmqMetricSender(MetricSender):
    def __init__(self) -> None:
        addr = os.environ.get("AGGREGATOR_PULL_ADDR", "")
        self._sock: zmq.Socket | None = None
        if addr:
            ctx = zmq.Context.instance()
            self._sock = ctx.socket(zmq.PUSH)
            self._sock.connect(addr)
```

**New code:**

```python
def _aggregator_addr_from_lan() -> str:
    """Derive the aggregator ZMQ PULL address from the LAN_ID env var."""
    lan_id = os.environ.get("LAN_ID", "")
    if not lan_id:
        return ""
    subnet_third_octet = int(lan_id) - 1       # LAN 1 → 10.0.0.x, LAN 2 → 10.0.1.x
    return f"tcp://10.0.{subnet_third_octet}.5:5555"


class ZmqMetricSender(MetricSender):
    def __init__(self) -> None:
        addr = os.environ.get("AGGREGATOR_PULL_ADDR", "") or _aggregator_addr_from_lan()
        self._sock: zmq.Socket | None = None
        if addr:
            ctx = zmq.Context.instance()
            self._sock = ctx.socket(zmq.PUSH)
            self._sock.connect(addr)
```

### Step A.2 — `edge_storage_server/mongo_telemetry.py`

Same derivation for the storage sidecar.

**Current code (module-level, lines 10–11):**

```python
SERVER_ID            = os.environ.get("SERVER_ID", "mongo-unknown")
AGGREGATOR_PULL_ADDR = os.environ.get("AGGREGATOR_PULL_ADDR", "tcp://10.0.0.5:5555")
```

**New code:**

```python
def _aggregator_addr_from_lan() -> str:
    """Derive the aggregator ZMQ PULL address from the LAN_ID env var."""
    lan_id = os.environ.get("LAN_ID", "")
    if not lan_id:
        return ""
    subnet_third_octet = int(lan_id) - 1
    return f"tcp://10.0.{subnet_third_octet}.5:5555"


SERVER_ID            = os.environ.get("SERVER_ID", "mongo-unknown")
AGGREGATOR_PULL_ADDR = os.environ.get("AGGREGATOR_PULL_ADDR", "") or _aggregator_addr_from_lan()
```

When the static build scripts pass `-e AGGREGATOR_PULL_ADDR=tcp://...` the
explicit value wins. When `node_manager.py` passes only `-e LAN_ID=1`, the
helper derives the correct address.

### Step A.3 — `edge_storage_server/entrypoint.sh`

Add `MONGO_PORT` env var support so the entrypoint can replace the CMD override
that `node_manager.py` and the build scripts were using.

**Current code:**

```bash
#!/usr/bin/env bash
set -euo pipefail

MONGOD_ARGS="--bind_ip_all"
if [ -n "${MONGO_REPLSET:-}" ]; then
    MONGOD_ARGS="$MONGOD_ARGS --replSet $MONGO_REPLSET"
fi

mongod $MONGOD_ARGS &
MONGOD_PID=$!

until mongosh --quiet --eval "db.runCommand({ping:1})" >/dev/null 2>&1; do
    sleep 1
done

python3 /mongo_telemetry.py &

wait $MONGOD_PID
```

**New code:**

```bash
#!/usr/bin/env bash
set -euo pipefail

# Build mongod arguments from env vars.
MONGOD_ARGS="--bind_ip_all"
if [ -n "${MONGO_REPLSET:-}" ]; then
    MONGOD_ARGS="$MONGOD_ARGS --replSet $MONGO_REPLSET"
fi
if [ -n "${MONGO_PORT:-}" ]; then
    MONGOD_ARGS="$MONGOD_ARGS --port $MONGO_PORT"
fi

# Derive MONGO_URI from MONGO_PORT so the sidecar connects to the right port.
export MONGO_URI="${MONGO_URI:-mongodb://localhost:${MONGO_PORT:-27017}/}"

# Start mongod in the background.
# shellcheck disable=SC2086
mongod $MONGOD_ARGS &
MONGOD_PID=$!

# Wait until mongod accepts connections before starting the sidecar.
until mongosh --port "${MONGO_PORT:-27017}" --quiet --eval "db.runCommand({ping:1})" >/dev/null 2>&1; do
    sleep 1
done

# Start the telemetry sidecar in the background.
python3 /mongo_telemetry.py &

# The container lives as long as mongod does.
wait $MONGOD_PID
```

### Step A.4 — `edge_storage_server/Dockerfile`

Update the ENV block to add `MONGO_PORT` and clear `AGGREGATOR_PULL_ADDR`
(so `LAN_ID` derivation is the default path).

**Current ENV block:**

```dockerfile
ENV DEBIAN_FRONTEND=noninteractive \
    MONGO_VERSION=7.0 \
    SERVER_ID=mongo-unknown \
    AGGREGATOR_PULL_ADDR=tcp://10.0.0.5:5555 \
    MONGO_URI=mongodb://localhost:27017/ \
    TELEMETRY_INTERVAL_S=10 \
    MONGO_REPLSET=
```

**New ENV block:**

```dockerfile
ENV DEBIAN_FRONTEND=noninteractive \
    MONGO_VERSION=7.0 \
    SERVER_ID=mongo-unknown \
    AGGREGATOR_PULL_ADDR= \
    LAN_ID= \
    MONGO_URI= \
    MONGO_PORT=27017 \
    TELEMETRY_INTERVAL_S=10 \
    MONGO_REPLSET=
```

`AGGREGATOR_PULL_ADDR` and `MONGO_URI` are now empty by default. The
entrypoint derives `MONGO_URI` from `MONGO_PORT`, and `mongo_telemetry.py`
derives `AGGREGATOR_PULL_ADDR` from `LAN_ID`.

---

## Phase B — `node_manager.py` (depends on Phase A)

### Step B.1 — `_docker_run_server`

Add `lan` parameter. Inject `-e LAN_ID` and `-e SERVER_ID`.

**Current code:**

```python
def _docker_run_server(self, name: str) -> tuple[bool, str, str]:
    state = self._container_state(name)
    if state == "running":
        logger.info("[node_add] container %s already running — skipping docker run", name)
        return True, "", ""
    if state is not None:
        logger.info("[node_add] removing stale container %s (state=%s)", name, state)
        self._cleanup_container(name)
    cmd = ["docker", "run", "-dit", "--network", "none", "--name", name, "edge_server"]
    return self._run_cmd(cmd)
```

**New code:**

```python
def _docker_run_server(self, name: str, lan: int) -> tuple[bool, str, str]:
    state = self._container_state(name)
    if state == "running":
        logger.info("[node_add] container %s already running — skipping docker run", name)
        return True, "", ""
    if state is not None:
        logger.info("[node_add] removing stale container %s (state=%s)", name, state)
        self._cleanup_container(name)
    cmd = [
        "docker", "run", "-dit",
        "--network", "none",
        "--name", name,
        "-e", f"LAN_ID={lan}",
        "-e", f"SERVER_ID={name}",
        "edge_server",
    ]
    return self._run_cmd(cmd)
```

### Step B.2 — `_docker_run_storage`

Add `lan` parameter. Remove CMD override, pass configuration through env vars
so `entrypoint.sh` starts both `mongod` and the telemetry sidecar.

**Current code:**

```python
def _docker_run_storage(self, name: str, rs_name: str, port: int) -> tuple[bool, str, str]:
    state = self._container_state(name)
    if state == "running":
        logger.info("[node_add] container %s already running — skipping docker run", name)
        return True, "", ""
    self._cleanup_container(name)
    vol = f"{name}-data"
    cmd = [
        "docker", "run", "-dit",
        "--network", "none",
        "--name", name,
        "-v", f"{vol}:/data/db",
        "edge_storage_server",
        "mongod", "--replSet", rs_name, "--bind_ip_all", "--port", str(port),
    ]
    return self._run_cmd(cmd)
```

**New code:**

```python
def _docker_run_storage(self, name: str, rs_name: str, port: int, lan: int) -> tuple[bool, str, str]:
    state = self._container_state(name)
    if state == "running":
        logger.info("[node_add] container %s already running — skipping docker run", name)
        return True, "", ""
    self._cleanup_container(name)
    vol = f"{name}-data"
    cmd = [
        "docker", "run", "-dit",
        "--network", "none",
        "--name", name,
        "-v", f"{vol}:/data/db",
        "-e", f"LAN_ID={lan}",
        "-e", f"SERVER_ID={name}",
        "-e", f"MONGO_REPLSET={rs_name}",
        "-e", f"MONGO_PORT={port}",
        "edge_storage_server",
    ]
    return self._run_cmd(cmd)
```

No trailing `mongod ...` — the Dockerfile's `CMD ["/entrypoint.sh"]` takes
over. The entrypoint reads `MONGO_REPLSET` and `MONGO_PORT` from the env,
starts mongod, waits for readiness, then launches the telemetry sidecar.

### Step B.3 — Update callers

```python
# In add_edge_server():
ok, stdout, stderr = self._docker_run_server(name, lan)
#                                                  ^^^ new arg

# In add_storage_node():
ok, stdout, stderr = self._docker_run_storage(name, rs_name, port, lan)
#                                                                  ^^^ new arg
```

---

## Phase C — Build Network Scripts (parallel with Phase B, depends on Phase A)

### Step C.1 — `build_network_1.sh`

Replace the storage node CMD override with env vars. Add `LAN_ID=1` to both
edge_server and edge_storage_server for consistency.

#### edge_server_n1

**Current docker run:**

```bash
docker run -dit --name edge_server_n1 --network none \
  -e SERVER_ID=edge_server_n1 \
  -e AGGREGATOR_PULL_ADDR=tcp://10.0.0.5:5555 \
  -e LOG_LEVEL=INFO \
  edge_server
```

**New docker run:**

```bash
docker run -dit --name edge_server_n1 --network none \
  -e LAN_ID=1 \
  -e SERVER_ID=edge_server_n1 \
  -e AGGREGATOR_PULL_ADDR=tcp://10.0.0.5:5555 \
  -e LOG_LEVEL=INFO \
  edge_server
```

#### edge_storage_server_n1

**Current docker run:**

```bash
docker run -dit --name edge_storage_server_n1 --network none \
  -e SERVER_ID=edge_storage_server_n1 \
  -e MONGO_URI=mongodb://localhost:27018/ \
  -e INTERVAL_S=10 \
  -e AGGREGATOR_PULL_ADDR=tcp://10.0.0.5:5555 \
  -e LOG_LEVEL=INFO \
  --no-healthcheck \
  -v edge_storage_server_n1-data:/data/db edge_storage_server mongod \
  --replSet rs_net1 --bind_ip_all --port 27018
```

**New docker run:**

```bash
docker run -dit --name edge_storage_server_n1 --network none \
  -e LAN_ID=1 \
  -e SERVER_ID=edge_storage_server_n1 \
  -e AGGREGATOR_PULL_ADDR=tcp://10.0.0.5:5555 \
  -e MONGO_REPLSET=rs_net1 \
  -e MONGO_PORT=27018 \
  -e TELEMETRY_INTERVAL_S=10 \
  -e LOG_LEVEL=INFO \
  --no-healthcheck \
  -v edge_storage_server_n1-data:/data/db edge_storage_server
```

No trailing `mongod ...`. The entrypoint derives `MONGO_URI` from
`MONGO_PORT`, the explicit `AGGREGATOR_PULL_ADDR` takes precedence over
`LAN_ID` derivation.

### Step C.2 — `build_network_2.sh`

Same changes for LAN 2. Add `LAN_ID=2` to both containers.

#### edge_server_n2

**Current docker run:**

```bash
docker run -dit --name edge_server_n2 --network none \
  -e SERVER_ID=edge_server_n2 \
  -e AGGREGATOR_PULL_ADDR=tcp://10.0.1.5:5555 \
  -e LOG_LEVEL=INFO \
  edge_server
```

**New docker run:**

```bash
docker run -dit --name edge_server_n2 --network none \
  -e LAN_ID=2 \
  -e SERVER_ID=edge_server_n2 \
  -e AGGREGATOR_PULL_ADDR=tcp://10.0.1.5:5555 \
  -e LOG_LEVEL=INFO \
  edge_server
```

#### edge_storage_server_n2

**Current docker run:**

```bash
docker run -dit --name edge_storage_server_n2 --network none \
  --no-healthcheck \
  -e SERVER_ID=edge_storage_server_n2 \
  -e MONGO_URI=mongodb://localhost:27018/ \
  -e INTERVAL_S=10 \
  -e AGGREGATOR_PULL_ADDR=tcp://10.0.1.5:5555 \
  -e LOG_LEVEL=INFO \
  -v edge_storage_server_n2-data:/data/db edge_storage_server mongod \
  --replSet rs_net2 --bind_ip_all --port 27018
```

**New docker run:**

```bash
docker run -dit --name edge_storage_server_n2 --network none \
  --no-healthcheck \
  -e LAN_ID=2 \
  -e SERVER_ID=edge_storage_server_n2 \
  -e AGGREGATOR_PULL_ADDR=tcp://10.0.1.5:5555 \
  -e MONGO_REPLSET=rs_net2 \
  -e MONGO_PORT=27018 \
  -e TELEMETRY_INTERVAL_S=10 \
  -e LOG_LEVEL=INFO \
  -v edge_storage_server_n2-data:/data/db edge_storage_server
```

---

## Verification Checklist

- [ ] Rebuild both Docker images (`edge_server`, `edge_storage_server`).
- [ ] **Static test** — run `build_network_1.sh`, then:
  - `docker exec edge_storage_server_n1 pgrep -f mongo_telemetry` — sidecar
    PID exists.
  - `docker logs aggregator_n1 | grep mongo_stats` — storage telemetry events
    arrive.
- [ ] **Dynamic edge_server** — trigger
  `add_edge_server(lan=1, name="edge_server_test")`, then:
  - `docker exec edge_server_test env | grep LAN_ID` → `LAN_ID=1`.
  - Send HTTP request, check `docker logs aggregator_n1` for an event with
    `server_id=edge_server_test`.
- [ ] **Dynamic storage** — trigger `add_storage_node(lan=1, ...)`, then:
  - `docker exec <name> pgrep -f mongo_telemetry` — sidecar running.
  - `docker logs aggregator_n1 | grep <name>` — events arriving.
- [ ] **LAN 2 cross-check** — repeat dynamic tests with `lan=2` and verify
  events arrive at `aggregator_n2`, not `aggregator_n1`.
