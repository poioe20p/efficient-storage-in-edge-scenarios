# Elasticity & Placement Manager — Overview

## Purpose

The Elasticity Manager (Thread 3) is responsible for mutating the infrastructure
in response to latency breaches and underutilisation signals detected by Thread 2.
It handles spawning **and gracefully removing** `edge_server` and
`edge_storage_server` containers at runtime and wiring/unwiring them from the
running network.

---

## Architecture: Three-Thread Interaction

```
Thread 2 (Observer/ZMQ)     Thread 3 (Elasticity Mgr)      Infrastructure
       │                              │
       │── Alert(type, lan) ────────►│
       │                              │── NodeAdder.add_edge_server()
       │                              │      ├─ docker run           (timed)
       │                              │      ├─ add_network_node.sh  (timed)
       │                              │      └─ returns NodeResult (ip, mac, timings)
       │                              │
       │                              │── TopologyMixin.add_server_mac()
       │                              │── TopologyMixin.register_backend_ip()
       │                              │      └─ Thread 1 picks up the new server via VIP pool
```

- **Thread 1** (SDN controller main loop) — handles OpenFlow events, reactive
  L2 learning, and VIP routing. Never touches Thread 3 directly; it reads the
  shared VIP pool that Thread 3 mutates through `TopologyMixin`.
- **Thread 2** (`ZmqTelemetrySource`) — subscribes to aggregator and peer
  topology ZMQ endpoints, receives `TelemetrySummary` updates, evaluates
  thresholds, and posts typed `Alert` objects to Thread 3's queue.
- **Thread 3** (`ElasticityManager`) — a long-lived daemon thread blocking on a
  `threading.Queue`. Pops alerts and dispatches them to the appropriate handler,
  which calls `NodeAdder` for the actual container lifecycle.

---

## File Layout

```
source/sdn_controller/
├── main_n1.py                    # Controller entry point — instantiates ElasticityManager,
│                                 #   posts alerts from Thread 2 callback
├── elasticity/
│   ├── __init__.py
│   ├── elasticity.py             # ElasticityManager — Thread 3 queue/dispatch
│   ├── node_common.py            # Shared types (NodeResult, RemovalResult, NodeInfo, …),
│   │                             #   constants (SCRIPTS_DIR), and _BaseNodeAdder helpers
│   ├── compute_node_manager.py   # ComputeNodeAdder — edge_server lifecycle + drain phases
│   └── storage_node_manager.py  # StorageNodeAdder — edge_storage_server lifecycle + rs.remove()
└── topology/
    └── topology.py               # TopologyMixin — VIP pool (add_server_mac, add_storage_mac, etc.)

source/scripts/network/
├── add_network_node.sh           # Attaches a running container to OVS LAN (veth + IP/MAC)
└── add_network_storage_node.sh   # Same + rs.add() to join the MongoDB replica set
```

---

## Alert Types

Produced by Thread 2's `_on_telemetry_update` callback in `main_n1.py`, consumed
by Thread 3.

| Alert                     | Trigger                                          | Fields                                                                        |
| ------------------------- | ------------------------------------------------ | ----------------------------------------------------------------------------- |
| `ComputeAlert`          | `avg_time_proc_ms > TAU_PROC_MS` (2 windows)   | `lan`, `network_id`                                                         |
| `DataAlert`             | `avg_time_db_ms > TAU_DADOS_MS` (2 windows)    | `lan`, `network_id`, `rs_name`, `primary_container`, `port`          |
| `ScaleDownComputeAlert` | Underutilisation (9 windows) or timeout         | `lan`, `network_id`, `container_name`, `mac`                          |
| `ScaleDownDataAlert`    | Underutilisation (9 windows) or timeout         | `lan`, `network_id`, `container_name`, `mac`, `ip`, `rs_name`, `primary_container`, `port` |
| `CleanupComputeAlert`   | `drain_complete` ZMQ event / telemetry timeout  | `mac`                                                                         |

Scale-up requires 2 consecutive windows above threshold. Scale-down requires 9
consecutive windows below threshold (asymmetric — scale down slow, scale up fast).

Thresholds are configured via environment variables:

| Variable                          | Default    | Description                                        |
| --------------------------------- | ---------- | -------------------------------------------------- |
| `TAU_PROC_MS`                   | `600`    | Processing latency scale-up threshold (ms)         |
| `TAU_DADOS_MS`                  | `150000` | DB latency scale-up threshold (ms)                 |
| `TAU_CPU_DOWN`                  | `20`     | Domain avg CPU below → compute idle              |
| `TAU_PROC_DOWN_MS`              | `100`    | Domain avg proc latency below → compute idle     |
| `TAU_STORAGE_CPU_DOWN`          | `20`     | Domain avg storage CPU below → storage idle      |
| `TAU_DB_DOWN_MS`                | `50000`  | Domain avg DB latency below → storage idle       |
| `SCALE_DOWN_COMPUTE_CONSECUTIVE`| `9`      | Compute scale-down window count                    |
| `SCALE_DOWN_STORAGE_CONSECUTIVE`| `9`      | Storage scale-down window count                    |
| `TELEMETRY_TIMEOUT_WINDOWS`     | `10`     | Absent windows before dead-node removal            |

---

## Node Addition — Implemented

### Container Naming

Dynamic containers are named using a per-network sequence counter:
`{prefix}_{network_id}_dyn{counter}` — e.g. `edge_server_lan1_dyn1`,
`edge_storage_lan2_dyn3`.

### Lifecycle: `NodeAdder`

Each public method is a self-contained, timed, idempotent lifecycle. Every step
is individually timed with `time.perf_counter()`.

#### `add_edge_server(lan, name)`

| Step | Operation                                                                     | On failure                           |
| ---- | ----------------------------------------------------------------------------- | ------------------------------------ |
| 1    | `docker run -dit --network none --name <name> -e LAN_ID=lan<N> edge_server` | Return `FAILED`                    |
| 2    | `add_network_node.sh --lan <N> --name <name>`                               | Cleanup container, return `FAILED` |

#### `add_storage_node(lan, name, rs_name, primary_container, port)`

| Step | Operation                                                                                                                                                | On failure                                    |
| ---- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------- |
| 1    | `docker run -dit --network none --name <name> -v <name>-data:/data/db -e LAN_ID=lan<N> -e MONGO_REPLSET=<rs> -e MONGO_PORT=<port> edge_storage_server` | Return `FAILED`                             |
| 2    | `add_network_storage_node.sh --lan <N> --name <name> --rs-name <rs> --primary <primary> --port <port>`                                                 | Cleanup container + volume, return `FAILED` |

### Idempotency

Before calling `docker run`, `NodeAdder` inspects the container state:

| Existing state | Action                                              |
| -------------- | --------------------------------------------------- |
| Not found      | Create normally                                     |
| Running        | Skip `docker run`, proceed to next step           |
| Stopped/exited | Remove container (and volume for storage), recreate |

For storage nodes, stale volumes are always cleaned up before `docker run` to
avoid replica-set ID clashes from a previous failed attempt.

### Script Output Parsing

Both shell scripts emit machine-readable lines at the end of a successful run:

```
RESULT_IP=10.0.0.7
RESULT_MAC=00:00:00:00:01:07
```

`NodeAdder._run_script()` parses these via regex to populate `NodeResult.ip` and
`NodeResult.mac`.

### Post-Addition Registration (ElasticityManager)

On a successful `NodeResult`:

- **Compute:** `add_server_mac(mac)` + `register_backend_ip(mac, ip)` — the new
  server enters the VIP web pool and Thread 1 starts routing traffic to it.
- **Data:** `add_storage_mac(mac, domain=f"n{lan}")` + `register_backend_ip(mac, ip)`
  — the new storage node enters the VIP data pool for its domain.

If the script succeeds but MAC is not present in the output, a warning is logged
and VIP registration is skipped (the node is online but unreachable via VIP
until manually registered).

### Timing Model

Every `NodeResult` carries a `StepTimings` record:

| Field                  | What it measures                                                              | Typical range |
| ---------------------- | ----------------------------------------------------------------------------- | ------------- |
| `docker_run_s`       | `docker run` → container enters `running` state                          | 0.1 – 1 s    |
| `network_attach_s`   | veth creation → OVS port → IP config (+ rs.add for storage)                 | 1 – 10 s     |
| `replica_set_join_s` | Reserved for future split timing (currently absorbed in `network_attach_s`) | —            |
| `total_s`            | Wall clock from first step to last — includes inter-step overhead            | 1.5 – 15 s   |

Timings are emitted at `INFO` level by `log_timings()`.

### Audit Trail

Every operation (success or failure) is recorded in `ElasticityManager._active`,
a thread-safe list of dicts containing the alert, container name, and full
`NodeResult`. Accessible via `get_active_operations()` from any thread.

---

## Network Attachment Scripts

### `add_network_node.sh`

Attaches an already-running `--network none` Docker container to an OVS LAN.

```
add_network_node.sh --lan <1|2> --name <container> [--ip <x.x.x.x>] [--mac <XX:..>]
```

Steps:

1. Resolve OVS bridge, subnet, and gateway from `--lan`.
2. Auto-assign IP (scan running containers + named namespaces) if `--ip` omitted.
3. Auto-generate MAC from LAN index and host octet if `--mac` omitted.
4. Pick next free veth index (range `10–19` for LAN 1, `30–49` for LAN 2).
5. Create veth pair, move one end into OVS namespace, attach to bridge.
6. Move peer end into the container namespace, configure IP/MAC/routes.
7. Print summary and emit `RESULT_IP` / `RESULT_MAC`.

### `add_network_storage_node.sh`

Same as above, plus:

- Runs `rs.add("IP:PORT")` against the replica-set primary.
- Waits for the new member to reach `SECONDARY` state before completing.

### Per-LAN Constants

| Property           | LAN 1                                                | LAN 2           |
| ------------------ | ---------------------------------------------------- | --------------- |
| OVS bridge         | `ovs-br0`                                          | `ovs-br1`     |
| Subnet             | `10.0.0.0/24`                                      | `10.0.1.0/24` |
| Gateway IP         | `10.0.0.1`                                         | `10.0.1.1`    |
| Dynamic veth range | `10–19`                                           | `30–49`      |
| Reserved IPs       | `.1` (gw), `.100` (VIP_Web), `.200` (VIP_Data) | same            |

---

## Node Removal — Planned

Graceful scale-down will be added symmetrically to node addition. The design
uses a two-phase cooperative drain to avoid cutting active connections.

### Two-Phase Cooperative Drain

**Phase A — Controller-side isolation (immediate):**

1. Remove MAC from VIP pool (`remove_server_mac` / `remove_storage_mac`).
2. Storage only: `rs.remove(IP:PORT)` via the replica set primary.

**Phase B — Node drain + cleanup:**

1. Signal node to stop accepting work.
2. Wait for active work to finish (or timeout).
3. `docker stop` if still running after timeout.
4. Flush OVS flows for the MAC, remove OVS port, delete veth pair.
5. `docker rm` (and `docker volume rm` for storage).

### Drain by Node Type

|                      | Compute (`edge_server`)                                              | Storage (`edge_storage_server`)                                          |
| -------------------- | ---------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Drain signal         | `docker exec <name> curl -sS -X POST http://localhost:5000/drain`    | Phase A is sufficient —`rs.remove()` + VIP removal stop all new work    |
| Idle detection       | Flask active-request counter hits 0 → container calls `os._exit(0)` | Telemetry pipeline:`connections_current ≤ 1` in next ZMQ window (~10 s) |
| Who stops container? | Container exits itself; controller detects via `docker inspect` poll | Controller calls `docker stop` once idle confirmed                       |
| Timeout fallback     | Force-stop after 30 s                                                  | Force-stop after 15 s                                                      |

### New Alert Types (planned)

| Alert                     | Fields                                                                                                     |
| ------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `ScaleDownComputeAlert` | `lan`, `network_id`, `container_name`, `ip`, `mac`                                               |
| `ScaleDownDataAlert`    | `lan`, `network_id`, `container_name`, `ip`, `mac`, `rs_name`, `primary_container`, `port` |

`ip` and `mac` are passed from the caller (available from the original
`NodeResult` at addition time) to avoid re-discovery race conditions.

### New `NodeAdder` Methods (planned)

- `remove_edge_server(lan, name, mac, drain_timeout=30)` — drain signal →
  wait for exit → force-stop → flush OVS flows → remove port/veth → `docker rm`.
- `remove_storage_node(lan, name, mac, ip, rs_name, primary_container, port, drain_timeout=15)` — rs.remove → wait for idle → stop → flush → cleanup → volume rm.

### New Shell Scripts (planned)

- `remove_network_node.sh --graceful` — drain + network teardown for compute.
- `remove_network_storage_node.sh --graceful` — RS removal + drain + network
  teardown for storage.

Both scripts will add `--graceful` and `--drain-timeout` flags; without
`--graceful` they retain immediate-removal behaviour for backward compatibility.

### Scale-Down Detection (deferred)

The policy for *when* to remove a node (scale-down thresholds) is a separate
concern. The removal mechanism will be implemented and tested before the
detection logic is layered on top. Once ready, Thread 2 will submit
`ScaleDownComputeAlert` / `ScaleDownDataAlert` to the queue via
`submit_alert()`.
