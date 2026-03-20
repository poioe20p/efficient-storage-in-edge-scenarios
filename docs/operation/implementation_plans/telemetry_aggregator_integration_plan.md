# Plan: Telemetry Aggregator Integration

## Goal

Wire up end-to-end ZeroMQ-based telemetry from the edge servers to the
aggregator container. This covers:

1. Adding `push_metric()` + `before_request`/`after_request` hooks to
   `app.py` (edge_server).
2. Creating `aggregator.py` inside `local_state_server/` and updating its
   `Dockerfile`.
3. Launching the aggregator container (one per network) inside
   `build_network_1.sh` and `build_network_2.sh`, including full network
   attachment.

---

## Context: docker_sampler is NOT needed

The architecture doc (`system_cross_network_state.md`) mentioned a
`docker_sampler` module that queries the Docker API from inside the aggregator
container to sample CPU/RAM of peer containers. This is **not the approach used
here**.

Instead, each `edge_server` container **includes its own CPU and RAM usage**
as fields in the ZMQ PUSH metric event it sends after each HTTP request. The
aggregator simply averages those values across the window — no Docker API
access needed, no extra volume mount, no `docker_sampler` module.

CPU and RAM fields sent by each edge server:

```json
{
  "server_id": "edge-server-net1-1",
  "ts": 1742126400.0,
  "T_total_ms": 85.2,
  "T_dados_ms": 47.1,
  "status_code": 200,
  "request_type": "read",
  "cpu_percent": 34.7,
  "ram_used_mb": 128.3
}
```

CPU/RAM are read via the standard `psutil` library inside the edge server
process (or via `/proc/stat` + `/proc/meminfo` if `psutil` is not installed).

---

## 1. `source/docker/edge_server/app.py`

The current `app.py` uses Flask. The metric push must be integrated as
`before_request`/`after_request` hooks using only the stdlib + `pyzmq` +
`psutil`.

### Changes

- Add env vars read at module level: `SERVER_ID`, `AGGREGATOR_PULL_ADDR`.
- Create one ZMQ PUSH socket at module level (lazy-connect on first use or at
  startup) connected to `AGGREGATOR_PULL_ADDR`.
- Add `push_metric(t_total_ms, t_dados_ms, status_code, request_type)` that
  builds the event dict (including `cpu_percent` and `ram_used_mb` via
  `psutil`) and calls `_sock.send_json(event, zmq.NOBLOCK)`.
- Add `@app.before_request` hook `_start_timer()` that sets
  `flask.g.t_start = time.monotonic()` and
  `flask.g.t_dados_elapsed = 0.0`.
- Add `@app.after_request` hook `_emit_metric(response)` that computes
  `t_total`, calls `push_metric(...)`, and returns `response`.

### Notes

- `zmq.NOBLOCK` ensures the hook never blocks the HTTP response even if the
  aggregator is temporarily unavailable (events are simply dropped).
- `t_dados_elapsed` will remain `0.0` until MongoDB queries are wired in; the
  field is included now so the event schema is stable.
- `SERVER_ID` defaults to `"unknown"` if the env var is absent.
- The ZMQ context and socket are created at module import time (same pattern as
  `telemetry_reporter.py` in the doc); `zmq.NOBLOCK` prevents import-time
  blocking.

---

## 2. `source/docker/local_state_server/aggregator.py` (new file)

The aggregator is a standalone Python script that:

- Binds a ZMQ PULL socket on `PULL_ADDR` (default `tcp://0.0.0.0:5555`).
- Binds a ZMQ PUB socket on `PUB_ADDR` (default `tcp://0.0.0.0:5556`).
- Collects events in a `_buffer` list (thread-safe via a `threading.Lock`).
- Every `WINDOW_S` seconds (default `10`), drains the buffer, computes a
  windowed summary keyed by `server_id`, and publishes it as JSON.

### Per-server fields in the published summary

Each server entry averages the fields the edge server already sends:

| Field               | Source                                                |
| ------------------- | ----------------------------------------------------- |
| `avg_T_total_ms`  | mean of `T_total_ms` in the window                  |
| `avg_T_dados_ms`  | mean of `T_dados_ms` in the window                  |
| `avg_T_proc_ms`   | mean of `T_total_ms - T_dados_ms`                   |
| `request_count`   | count of events in window                             |
| `error_rate`      | fraction of events with `status_code >= 500`        |
| `avg_cpu_percent` | mean of `cpu_percent` (from edge server via psutil) |
| `avg_ram_used_mb` | mean of `ram_used_mb` (from edge server via psutil) |

### Domain summary fields

```json
{
  "network_id": "net1",
  "window_end": 1742126410.5,
  "servers": { ... },
  "domain_summary": {
    "total_requests":  260,
    "avg_T_proc_ms":   38.7,
    "avg_T_dados_ms":  49.4,
    "peak_T_total_ms": 210.5
  }

```

---

## 3. `source/docker/local_state_server/Dockerfile`

### Changes

- Remove `flask` from `pip install`.
- Add `pyzmq` and `psutil` to `pip install`.
- `COPY aggregator.py /aggregator.py`
- `CMD ["python3", "/aggregator.py"]`
- Expose port `5555` (PULL) and `5556` (PUB).

---

## 4. `build_network_1.sh`

One aggregator container is launched for Network 1 using the `local_state_server`
image. It is wired into `ovs-br0` the same way other containers are.

### Network assignment

| Property                | Value                      |
| ----------------------- | -------------------------- |
| Container name          | `aggregator_n1`          |
| Image                   | `local_state_server`     |
| IP                      | `10.0.0.5/24`            |
| MAC                     | `00:00:00:00:00:05`      |
| Gateway                 | `10.0.0.1`               |
| veth pair (host → OVS) | `veth4` / `veth4-peer` |
| OVS bridge              | `ovs-br0`                |

### Steps added to the script (in order)

1. **Cleanup** — add `veth4 veth4-peer` to the existing cleanup loop.
2. **Create veth pair** — `sudo ip link add veth4 type veth peer name veth4-peer`.
3. **Move into OVS namespace** — `sudo ip link set veth4 netns ovs`.
4. **Add to OVS bridge** — `docker exec ovs ovs-vsctl add-port ovs-br0 veth4`.
5. **Bring up inside OVS** — `docker exec ovs ip link set veth4 up`.
6. **Launch container** —
   ```bash
   docker run -dit --name aggregator_n1 --network none \
     -e NETWORK_ID=net1 \
     -e PULL_ADDR=tcp://0.0.0.0:5555 \
     -e PUB_ADDR=tcp://0.0.0.0:5556 \
     -e WINDOW_S=10 \
     local_state_server
   ```
7. **Get PID** — `PID_AGG=$(docker inspect -f '{{.State.Pid}}' aggregator_n1)`.
8. **Move peer into container** — `sudo ip link set veth4-peer netns $PID_AGG`.
9. **Configure interface inside container** —
   ```bash
   sudo nsenter -t $PID_AGG -n ip link set veth4-peer name eth0
   sudo nsenter -t $PID_AGG -n ip link set eth0 address 00:00:00:00:00:05
   sudo nsenter -t $PID_AGG -n ip link set eth0 up
   sudo nsenter -t $PID_AGG -n ip addr add 10.0.0.5/24 dev eth0
   sudo nsenter -t $PID_AGG -n ip route add default via 10.0.0.1
   ```

---

## 5. `build_network_2.sh`

Mirror of Section 4 for Network 2.

### Network assignment

| Property                | Value                        |
| ----------------------- | ---------------------------- |
| Container name          | `aggregator_n2`            |
| Image                   | `local_state_server`       |
| IP                      | `10.0.1.5/24`              |
| MAC                     | `00:00:00:00:00:07`        |
| Gateway                 | `10.0.1.1`                 |
| veth pair (host → OVS) | `veth24` / `veth24-peer` |
| OVS bridge              | `ovs-br1`                  |

### Steps added to the script (in order)

1. **Cleanup** — add `veth24 veth24-peer` to the existing cleanup loop.
2. **Create veth pair** — `sudo ip link add veth24 type veth peer name veth24-peer`.
3. **Move into OVS namespace** — `sudo ip link set veth24 netns ovs`.
4. **Add to OVS bridge** — `docker exec ovs ovs-vsctl add-port ovs-br1 veth24`.
5. **Bring up inside OVS** — `docker exec ovs ip link set veth24 up`.
6. **Launch container** —
   ```bash
   docker run -dit --name aggregator_n2 --network none \
     -e NETWORK_ID=net2 \
     -e PULL_ADDR=tcp://0.0.0.0:5555 \
     -e PUB_ADDR=tcp://0.0.0.0:5556 \
     -e WINDOW_S=10 \
     local_state_server
   ```
7. **Get PID** — `PID_AGG=$(docker inspect -f '{{.State.Pid}}' aggregator_n2)`.
8. **Move peer into container** — `sudo ip link set veth24-peer netns $PID_AGG`.
9. **Configure interface inside container** —
   ```bash
   sudo nsenter -t $PID_AGG -n ip link set veth24-peer name eth0
   sudo nsenter -t $PID_AGG -n ip link set eth0 address 00:00:00:00:00:07
   sudo nsenter -t $PID_AGG -n ip link set eth0 up
   sudo nsenter -t $PID_AGG -n ip addr add 10.0.1.5/24 dev eth0
   sudo nsenter -t $PID_AGG -n ip route add default via 10.0.1.1
   ```

---

## 6. `system_cross_network_state.md`

### 6.1 Fix Section 2 — Node Self-Registration

The current text describes containers "self-registering" by sending an ARP or
hello packet into the local OVS switch after startup. This is inaccurate.

Network attachment for all containers (edge servers, storage nodes, and the
aggregator) is performed **externally** by the admin scripts
(`build_network_[1|2].sh`, `add_network_node.sh`,
`add_network_storage_node.sh`). The scripts create the veth pair, move it into
OVS, configure the container's IP/MAC via `nsenter`, and set the default
gateway — the container never needs to "self-register".

The corrected section should describe:

1. Admin scripts (`build_network_*.sh` or `add_network_node.sh`) perform the
   veth + OVS + IP/MAC configuration entirely from the host.
2. Controller B learns the new node's MAC/port on the first actual data-plane
   packet (PacketIn), as normal L2 learning.
3. Controller B writes the topology change to the Shared MongoDB on that
   PacketIn.

---

## 7. `source/docker/edge_storage_server/` — MongoDB Telemetry Sidecar

The `edge_storage_server` runs a bare `mongod` with no application layer.
A lightweight Python sidecar (`mongo_telemetry.py`) runs alongside `mongod`
and pushes periodic snapshots to the same aggregator PULL socket used by edge
servers.

### Event type distinction

The aggregator routes events by the presence of `event_type`:

| `event_type` value | Source | Aggregator handling |
|---|---|---|
| *(absent)* | `edge_server` (per HTTP request) | Averaged in `_buffer` over the window |
| `"mongo_stats"` | `edge_storage_server` (periodic) | Latest snapshot per `server_id` in a separate `_mongo_buffer` |

Edge server events have no `event_type` field — no changes needed to `app.py`
for the aggregator to distinguish the two kinds.

### Metrics pushed by `mongo_telemetry.py`

```json
{
  "event_type":          "mongo_stats",
  "server_id":           "mongo-net1",
  "ts":                  1742126400.0,
  "repl_lag_s":          1.2,
  "connections_current": 4,
  "cpu_percent":         12.3,
  "ram_used_mb":         256.7
}
```

| Field | Source | Meaning |
|---|---|---|
| `repl_lag_s` | `replSetGetStatus` | Seconds behind primary. `0.0` if this IS the primary; `null` if standalone. |
| `connections_current` | `serverStatus.connections.current` | Active mongod connections — indicates load from edge servers and Change Stream consumers. |
| `cpu_percent` | `psutil` | Container CPU (same field name as edge_server events). |
| `ram_used_mb` | `psutil` | Container RAM used in MB (same field name as edge_server events). |

### New files

| File | Purpose |
|---|---|
| `source/docker/edge_storage_server/mongo_telemetry.py` | Sidecar: collects metrics, pushes ZMQ PUSH event every `TELEMETRY_INTERVAL_S` seconds |
| `source/docker/edge_storage_server/entrypoint.sh` | Starts `mongod`, waits for readiness ping, then starts sidecar in background |

### Aggregator summary delta

The aggregator's published summary gains a `"storage_nodes"` section:

```json
"storage_nodes": {
  "mongo-net1": {
    "repl_lag_s":          1.2,
    "connections_current": 4,
    "cpu_percent":         12.3,
    "ram_used_mb":         256.7
  }
}
```

Since `mongo_stats` events are periodic snapshots (not per-request), the
aggregator keeps the **latest** event per `server_id` rather than windowed
averaging.

### `edge_storage_server` Dockerfile changes

- Add `python3 python3-pip` to apt-get.
- Add `RUN pip3 install --no-cache-dir pyzmq psutil pymongo`.
- `COPY mongo_telemetry.py /mongo_telemetry.py`
- `COPY entrypoint.sh /entrypoint.sh` + `RUN chmod +x /entrypoint.sh`
- `CMD ["/entrypoint.sh"]`
- New env vars: `SERVER_ID`, `AGGREGATOR_PULL_ADDR`, `MONGO_URI`,
  `TELEMETRY_INTERVAL_S`, `MONGO_REPLSET` (empty = standalone mode).
