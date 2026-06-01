# Compute Scale-Down

## 1. Purpose

Compute scale-down gracefully removes underutilised `edge_server` containers
using an async two-phase drain model. The controller isolates the node from
the VIP pool, signals it to drain in-flight requests, and returns immediately.
The container self-exits once idle; the controller then cleans up the network
attachment. Pending drains can be cancelled if load rebounds (scale-up wins
over scale-down).

Source: [`source/sdn_controller/scaling_policy.py`](../../../source/sdn_controller/scaling_policy.py),
[`source/sdn_controller/elasticity/compute_node_manager.py`](../../../source/sdn_controller/elasticity/compute_node_manager.py),
[`source/sdn_controller/elasticity/elasticity.py`](../../../source/sdn_controller/elasticity/elasticity.py)

---

## 2. Idle Detection

Compute scale-down uses an **AND-gate** sliding window — both CPU and latency
must be below their respective thresholds simultaneously for a window to count
as "idle". This prevents false positives from data-bound latency spikes.

### Thresholds

| Metric                  |           Threshold           | Meaning                   |
| ----------------------- | :----------------------------: | ------------------------- |
| `average_cpu_percent` |   `< TAU_CPU_DOWN` (15 %)   | Domain compute CPU is low |
| `avg_time_proc_ms`    | `< TAU_PROC_DOWN_MS` (20 ms) | Processing latency is low |

Both conditions must hold for the window to count.

### Sliding Window

| Parameter                          | Default | Meaning                    |
| ---------------------------------- | :-----: | -------------------------- |
| `SCALE_DOWN_COMPUTE_WINDOW_SIZE` |   12   | Window size                |
| `SCALE_DOWN_COMPUTE_REQUIRED`    |    7    | Idle windows needed to arm |

### Timeout Ceiling

If `avg_time_proc_ms > SCALE_DOWN_PROC_TIMEOUT_CEILING_MS` (default 5000 ms),
the window is treated as **indeterminate** and skipped — neither incrementing
nor resetting the idle count. This prevents RS election stalls or connectivity
timeouts from poisoning the signal.

### Instrumentation

Each evaluation emits a single DEBUG line carrying all predicate inputs:

```
[scale-down] compute eval: cpu=8.2/15 proc=12.5/20 below=True hits=5/7 armed=False
```

A one-shot INFO line is emitted on the rising edge (`False → True`) of
`armed`. See §9 for the instrumentation plan reference.

### Cross-Direction Reset

When compute scale-up triggers, the compute scale-down window is cleared (and
vice versa).

---

## 3. Candidate Selection

When the scale-down predicate is armed, the mediator
(`_pick_compute_scale_down_candidate`) selects the least disruptive eligible
node.

### Eligibility Filters

| Filter           | Rule                                                                              |
| ---------------- | --------------------------------------------------------------------------------- |
| Pending drain    | Node must not already have a `PendingDrain`                                     |
| Cached telemetry | Must have a retained `ServerSummary` in `_server_stats`                       |
| Staleness        | `last_report_ts` must be within `SCALE_DOWN_CANDIDATE_MAX_STALENESS_S` (90 s) |
| State            | `server.state == "active"` (not draining)                                       |
| Birth grace      | Node age ≥`NODE_BIRTH_GRACE_S` (60 s)                                          |

Only **dynamic** compute nodes are eligible — static servers and primary DB
containers are never removed.

### Ranking

Eligible candidates are sorted ascending by:

1. `request_count` (fewest active requests first — least disruption)
2. `avg_cpu_percent` (lowest CPU first)
3. `avg_time_proc_ms` (lowest latency first)
4. `-last_report_ts` (oldest report last — tiebreaker)

The candidate with the lowest `request_count` is selected.

---

## 4. Phase A Drain

`_handle_scale_down_compute(alert)` — Thread 3, < 1 second:

1. **VIP isolation:** `unregister_server_backend(mac)` — immediately removes
   the backend from the VIP web pool and clears the compute warm lease.
   Thread 1 stops creating new DNAT/SNAT flows toward this node.
2. **Veth discovery:** `nsenter` into the container's network namespace to
   discover the OVS-side veth name (needed for Phase B when the netns is gone).
3. **Store `PendingDrain`:** `PendingDrain(mac, veth, container_name, lan, ts, ip)`.
4. **Drain signal:** `docker exec curl -X POST http://localhost:5000/drain`
   (3-attempt retry).
   - **200 OK** → container will self-exit after in-flight requests complete.
     Thread 3 returns; `_busy` is reset.
   - **All attempts fail** → container is dead; submit
     `CleanupComputeAlert` immediately — no waiting for `drain_complete`.
5. **Veth discovery fails** → container netns already gone; release IP,
   notify Thread 2, return immediately.

Thread 3 spends < 1 second in Phase A and is free for other operations during
the unbounded drain period.

---

## 5. Phase B Cleanup

`_handle_cleanup_compute(alert)` — Thread 3, ~5–10 seconds:

Triggered by:

- `drain_complete` ZMQ event from the container supervisor.
- Telemetry timeout fallback (node absent for 18 windows).

1. **Lookup `PendingDrain`** by MAC.
2. **Run `remove_network_node.sh`:** `--lan <N> --name <name> --veth <veth> --mac <mac>`
   - Script handles: `docker stop` (safety net) → flow flush → OVS del-port →
     veth deletion → `docker rm`.
   - The `--veth` flag was discovered in Phase A so the script can skip
     `nsenter` discovery (the container's netns is gone once it has exited).
3. **Release IP** back to `IpAllocator`.
4. **Delete `PendingDrain`** entry.
5. **Notify Thread 2** via `consume_removal_completions()`.

A `RemovalResult` carrying `RemovalTimings` (`network_cleanup_s`, `total_s`)
is recorded in the audit trail.

---

## 6. Drain Cancel

`_handle_cancel_compute_drain(alert)` — Thread 3:

Triggered when compute scale-up fires while a compute drain is pending. The
mediator submits `ComputeAlert` first (priority 4), then
`CancelComputeDrainAlert` (priority 7).

1. **Select pending drain:** `_select_pending_compute_drain(mac)` — if `mac`
   is `None`, picks any pending compute drain.
2. **Cancel signal:** `docker exec curl -X POST http://localhost:5000/drain -d '{"command":"cancel"}'`
   (2-attempt retry).
3. **On success:**
   - `add_server_mac(mac)` — re-admit MAC to VIP web pool. Thread 1 resumes
     routing to this node.
   - Delete `PendingDrain` entry.
   - Node is immediately eligible for future scale-down again (no re-drain
     cooldown).
4. **On failure:** Submit `CleanupComputeAlert` — the node is unresponsive
   and should be torn down.

---

## 7. Busy and Pending Drain Interaction

### Gate Methods (Thread 2 reads these)

| Method                            | Returns `True` when…                                        |
| --------------------------------- | -------------------------------------------------------------- |
| `is_busy()`                     | A handler is executing**OR** any `PendingDrain` exists |
| `blocks_compute_scale_up()`     | A handler is executing (`_busy` only)                        |
| `has_pending_compute_drain()`   | Any compute-type `PendingDrain` exists                       |
| `pending_compute_drain_count()` | Returns count of pending compute drains                        |

### Key Asymmetry

**Pending compute drains do NOT block compute scale-up.** This is the
intentional rebound path:

1. Thread 2 subtracts pending compute drains from the effective dynamic
   compute count: `effective = registry_count - pending_drain_count`.
2. If the scale-up predicate fires, Thread 2 submits `ComputeAlert` **first**
   (priority 4).
3. Then submits `CancelComputeDrainAlert` (priority 7).
4. The cancel either re-admits the draining node or cleans it up.

This may temporarily leave one extra live compute node until later scale-down
convergence. The steady-state cap (`MAX_DYNAMIC_COMPUTE=4`) applies to the
effective count, not the live count.

**Pending compute drains DO block `is_busy()`**, which gates scale-down
evaluation globally. No new scale-down is considered while any drain is in
flight.

---

## 8. Environment Variables

### Idle Detection

| Variable                               | Default | Description                                        |
| -------------------------------------- | :-----: | -------------------------------------------------- |
| `TAU_CPU_DOWN`                       |   15   | Domain avg CPU % below which compute is idle       |
| `TAU_PROC_DOWN_MS`                   |   20   | Domain avg T_proc (ms) below which compute is idle |
| `SCALE_DOWN_COMPUTE_WINDOW_SIZE`     |   12   | Sliding window size                                |
| `SCALE_DOWN_COMPUTE_REQUIRED`        |    7    | Idle windows required to arm                       |
| `SCALE_DOWN_PROC_TIMEOUT_CEILING_MS` |  5000  | T_proc above which window is skipped               |

### Candidate Selection

| Variable                                 | Default | Description                                               |
| ---------------------------------------- | :-----: | --------------------------------------------------------- |
| `SCALE_DOWN_CANDIDATE_MAX_STALENESS_S` |   90   | Max age of cached `ServerSummary` for candidate ranking |
| `NODE_BIRTH_GRACE_S`                   |   60   | Skip absent-node detection during bootstrap (s)           |

### Cooldown & Timeout

| Variable                         | Default | Description                                          |
| -------------------------------- | :-----: | ---------------------------------------------------- |
| `SCALEDOWN_COMPUTE_COOLDOWN_S` |   40   | Post-scale-up cooldown before compute scale-down (s) |
| `TELEMETRY_TIMEOUT_WINDOWS`    |   18   | Absent windows before dead-node removal (180 s)      |

---

## 9. Instrumentation Reference

The scale-down decision path is instrumented per the plan in
[`implementation/scale_down_instrumentation.md`](../implementation/scale_down_instrumentation.md).

Each evaluation emits a single DEBUG line with all predicate inputs
(`cpu`, `proc`, `below`, `hits/required`, `armed`). A one-shot INFO line
fires on the rising edge of `armed`. The log grammar is a stable contract
consumed by the analysis toolchain (`cli_scale_down`).

---

## 10. Related Diagram

- [Compute scale-down sequence diagram](../diagrams/compute_scale_down.drawio)

Related implementation plan:

- [Compute graceful scale-down](../implementation/compute_graceful_scale_down/README.md) — phased plan for async two-phase drain with cancel support.
