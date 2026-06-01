# Storage Scale-Down

## 1. Purpose

Storage scale-down removes underutilised `edge_storage_server` containers
(MongoDB secondaries) using a synchronous removal flow. Unlike compute
scale-down, there is no drain concept for `mongod` — `rs.remove()` plus VIP
removal and script teardown suffice. The operation blocks Thread 3 (bounded,
~50 s worst case) and is triggered by sustained low CPU and DB latency.

Source: [`source/sdn_controller/scaling_policy.py`](../../../source/sdn_controller/scaling_policy.py),
[`source/sdn_controller/elasticity/storage_node_manager.py`](../../../source/sdn_controller/elasticity/storage_node_manager.py),
[`source/sdn_controller/elasticity/elasticity.py`](../../../source/sdn_controller/elasticity/elasticity.py)

---

## 2. Idle Detection

Storage scale-down uses an **AND-gate** sliding window — both storage CPU and
DB latency must be below their respective thresholds simultaneously for a
window to count as "idle".

### Thresholds

| Metric | Threshold | Meaning |
|--------|:---------:|---------|
| `avg_storage_cpu_percent` | `< TAU_STORAGE_CPU_DOWN` (15 %) | Storage CPU is low |
| `avg_time_db_ms` | `< TAU_DB_DOWN_MS` (150 ms) | DB latency is low |

Both conditions must hold for the window to count.

### Sliding Window

| Parameter | Default | Meaning |
|-----------|:-------:|---------|
| `SCALE_DOWN_STORAGE_WINDOW_SIZE` | 12 | Window size |
| `SCALE_DOWN_STORAGE_REQUIRED` | 7 | Idle windows needed to arm |

### Timeout Ceiling

If `avg_time_db_ms > SCALE_DOWN_DB_TIMEOUT_CEILING_MS` (default 5000 ms),
the window is treated as **indeterminate** and skipped — neither incrementing
nor resetting the idle count. This prevents RS elections or connectivity
timeouts from poisoning the signal.

### Instrumentation

Each evaluation emits a single DEBUG line:

```
[scale-down] storage eval: stCpu=5.2/15 db=80/150 below=True hits=5/7 armed=False
```

A one-shot INFO line fires on the rising edge of `armed`.

### Cross-Direction Reset

When storage scale-up triggers, the storage scale-down window is cleared (and
vice versa).

### Candidate Selection

Storage scale-down uses **LIFO** (newest dynamic storage node first). Only
dynamically added nodes are eligible — static servers and primary DB
containers are never removed. The assumption is that underutilisation means
no VIP_DATA flow rules are installed for the storage server.

---

## 3. VIP Isolation

The first step in `_handle_scale_down_data(alert)` is immediate VIP isolation:

```python
self._topo.unregister_storage_backend(alert.mac, domain=f"n{alert.lan}")
```

This single call:
1. Removes the MAC from the `VIP_DATA` pool for the given domain.
2. Clears the storage **warm lease** tied to that recyclable MAC/IP identity.

Thread 1 stops installing new DNAT/SNAT flows toward this node immediately.
Warm-lease invalidation matters because `IpAllocator` releases the IP on
successful removal and later reuses the lowest free suffix — MAC/IP identity
is recyclable, so warm state must be cleared at removal rather than relying
on later overwrite-on-add behavior.

---

## 4. Replica-Set Removal

`rs.remove()` is performed in Python (not in the shell script) with polling:

### Step 1 — Find Primary

```python
primary_host = self._find_rs_primary(primary_container, port)
```

Runs `db.adminCommand({isMaster: 1}).primary` via `mongosh` on the known
primary container. Returns `host:port` of the current RS primary, or `None`
if the primary is unreachable.

### Step 2 — rs.remove()

```python
ok = self._rs_remove_member(primary_container, primary_host, member_host)
```

Executes `rs.remove("ip:port")` via `mongosh` on the primary. Returns `True`
on `ok: 1`. On failure, a warning is logged but teardown proceeds anyway —
the node may already be absent from the RS configuration.

### Step 3 — Wait for Removal

```python
if ok_remove:
    self._wait_rs_member_removed(primary_container, primary_host, member_host)
```

Polls `rs.status()` until the member is gone from the RS configuration
(max 10 retries × 3 s = 30 s timeout). This ensures the RS has acknowledged
the topology change before the container is destroyed.

### Worst-Case Timing

| Phase | Duration |
|-------|:--------:|
| Find primary | ~1 s |
| rs.remove() | ~2 s |
| Wait for removal | ≤ 30 s |
| Script teardown | ~10–15 s |
| **Total** | **~50 s** |

---

## 5. Script Cleanup

After `rs.remove()`, the shell script handles physical teardown:

```
remove_network_storage_node.sh --lan <N> --name <name> --skip-rs [--keep-volume]
```

The `--skip-rs` flag tells the script that `rs.remove()` was already performed
in Python. The script executes:

1. **DNAT flow flush:** Removes any remaining OpenFlow DNAT rules targeting
   this storage node's MAC.
2. **`docker stop --time 15`:** Graceful shutdown with 15-second timeout for
   `mongod` to flush writes.
3. **OVS port/veth deletion:** Removes the OVS port and destroys the veth pair.
4. **`docker rm`:** Removes the stopped container.
5. **`docker volume rm`:** Removes the named data volume (`<name>-data`),
   unless `--keep-volume` is passed.

After successful removal, the IP is released back to `IpAllocator` and
Thread 2 is notified via `consume_removal_completions()`.

---

## 6. Failure Timeout Handling

Two independent triggers can initiate storage removal:

### Graceful — Underutilisation

CPU and latency metrics below scale-down thresholds for a sustained period
(sliding window). This is the **graceful** path for idle dynamic nodes.
Only dynamically added nodes are eligible.

### Failure Detector — Telemetry Timeout

A dynamic storage node absent from 18 consecutive telemetry windows (180 s
raw absence tolerance) is assumed dead and removed. This is a **failure
detector**, not an idleness detector:

- Dynamic storage nodes do **not** emit periodic heartbeats
  (`HEARTBEAT_ENABLED=false` is the image default; only static containers set
  `HEARTBEAT_ENABLED=true`).
- Any idle-but-alive node is removed by the underutilisation path well before
  the 180 s timeout fires.
- The 180 s is the raw absence tolerance for crashed or network-partitioned
  nodes.

When the timeout fires:
1. `DynamicNodeRegistry.detect_absent(summary)` returns the MAC.
2. If a `PendingDrain` exists for the MAC, `submit_cleanup(mac)` is called
   (Phase B). Storage doesn't use pending drains, so this path is unlikely.
3. Otherwise, `build_scale_down_alert(mac)` constructs a
   `ScaleDownDataAlert` and submits it to the queue.

### Birth Grace

Newly added nodes skip absent-node detection for `NODE_BIRTH_GRACE_S` (60 s)
during bootstrap, preventing premature removal before the sidecar completes
RS join and telemetry begins flowing.

---

## 7. Environment Variables

### Idle Detection

| Variable | Default | Description |
|----------|:-------:|-------------|
| `TAU_STORAGE_CPU_DOWN` | 15 | Domain avg storage CPU % below which storage is idle |
| `TAU_DB_DOWN_MS` | 150 | Domain avg T_db (ms) below which storage is idle |
| `SCALE_DOWN_STORAGE_WINDOW_SIZE` | 12 | Sliding window size |
| `SCALE_DOWN_STORAGE_REQUIRED` | 7 | Idle windows required to arm |
| `SCALE_DOWN_DB_TIMEOUT_CEILING_MS` | 5000 | T_db above which window is skipped |

### Cooldown & Timeout

| Variable | Default | Description |
|----------|:-------:|-------------|
| `SCALEDOWN_STORAGE_COOLDOWN_S` | 120 | Post-scale-up cooldown before storage scale-down (s) |
| `TELEMETRY_TIMEOUT_WINDOWS` | 18 | Absent windows before dead-node removal (180 s) |
| `NODE_BIRTH_GRACE_S` | 60 | Skip absent-node detection during bootstrap (s) |

### Candidate Staleness (compute-only, not used by storage)

Storage scale-down uses LIFO selection and does not use the
`SCALE_DOWN_CANDIDATE_MAX_STALENESS_S` variable (that is compute-only).

---

## 8. Related Diagram

- [Storage scale-down sequence diagram](../diagrams/storage_scale_down.drawio)
