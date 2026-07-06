# Compute Scale-Up

## 1. Purpose

Compute scale-up spawns additional `edge_server` containers in response to
sustained processing latency (`T_proc`) and CPU pressure on the local LAN.
The decision is made by Thread 2 (`ScalingPolicy`) and executed by Thread 3
(`ElasticityManager` → `ComputeNodeAdder`). A small peer-LAN health bias
lowers the threshold when the peer LAN can absorb spillover traffic.

Source: [`source/sdn_controller/scaling_policy.py`](../../../source/sdn_controller/scaling_policy.py),
[`source/sdn_controller/elasticity/compute_node_manager.py`](../../../source/sdn_controller/elasticity/compute_node_manager.py)

---

## 2. Trigger Path

```
TelemetrySummary (ZMQ)
    │
    ▼
_on_telemetry_update()                    [main_n*.py — Thread 2 mediator]
    ├─ sync node registry
    ├─ evaluate scale-up                  [ScalingPolicy.evaluate_scale_up()]
    │   ├─ check cooldown
    │   ├─ check cap
    │   ├─ compute degradation score
    │   ├─ compute adaptive threshold + peer relief
    │   ├─ append to sliding window
    │   └─ if window_hits >= REQUIRED → return ComputeAlert(lan, network_id)
    │
    ▼
self._elasticity.submit(ComputeAlert)     [Thread 2 → Thread 3 queue]
    │
    ▼
_loop() pops alert → _handle_compute()    [Thread 3]
    ├─ allocate IP/MAC
    ├─ ComputeNodeAdder.add_edge_server()
    │   ├─ docker run edge_server
    │   └─ add_network_node.sh
    └─ TopologyMixin.register_new_server_backend()
        └─ VIP web pool + warm lease (created unconditionally;
           consumed only when BACKEND_SELECTION_POLICY=topology_lifecycle)
```

The mediator (`main_n*.py`) also checks: if a `ComputeAlert` was submitted
and pending compute drains exist, a lower-priority `CancelComputeDrainAlert`
is enqueued so the drain can be reversed for fast rebound.

---

## 3. Compute Degradation Score

The weighted degradation score is per-LAN and computed from the `DomainSummary`:

$$\text{score} = W_{\text{CPU}} \cdot \text{cpu\_component} + W_{\text{T\_PROC}} \cdot \text{lat\_component}$$

Each component is normalised and clamped to $[0, 1]$:

$$\text{component} = \min\!\left(1.0,\ \frac{\max(0,\ \text{value} - \text{floor})}{\text{span}}\right)$$

| Component | Weight | Input metric | Floor | Span | Saturation |
|-----------|:------:|-------------|:-----:|:----:|:----------:|
| CPU | 0.40 | `average_cpu_percent` | 5 % | 10 | 15 % |
| Latency | 0.60 | `avg_time_proc_ms` | 20 ms | 80 | 100 ms |

The latency component dominates (0.60 vs 0.40) because processing latency is
the primary user-facing signal. Components saturate at 1.0 so a single extreme
window cannot dominate the sliding-window hit count — sustained badness is
expressed via the window-size/required ratio instead.

---

## 4. Adaptive Threshold and Peer Relief

### Adaptive Base Threshold

The base threshold rises linearly with each dynamic compute node already
present in the LAN:

$$\tau_{\text{base}} = \min(\text{BASE} + n_{\text{dynamic}} \cdot \text{INCREMENT},\ \text{MAX})$$

| Symbol | Env var | Default |
|--------|---------|:-------:|
| BASE | `SCALEUP_COMPUTE_BASE_THRESHOLD` | 0.45 |
| INCREMENT | `SCALEUP_COMPUTE_THRESHOLD_INCREMENT` | 0.10 |
| MAX | `SCALEUP_COMPUTE_MAX_THRESHOLD` | 0.85 |

Example progression ($n$ = dynamic compute count, excluding pending drains):

| $n$ | $\tau_{\text{base}}$ |
|:---:|:--------------------:|
| 0 | 0.45 |
| 1 | 0.55 |
| 2 | 0.65 |
| 3 | 0.75 |
| 4 (cap) | 0.85 |

### Peer Relief

The peer LAN's health is evaluated using the **same** degradation score
formula. If the peer's compute score is ≤ `PEER_HEALTH_THRESHOLD` (default
0.35), a small relief term is added to the local threshold:

$$\tau_{\text{effective}} = \min(\tau_{\text{base}} + \text{peer\_relief},\ \text{MAX})$$

| Env var | Default | Meaning |
|---------|:-------:|---------|
| `SCALEUP_COMPUTE_PEER_RELIEF` | 0.03 | Extra threshold when peer is healthy |
| `SCALEUP_COMPUTE_PEER_HEALTH_THRESHOLD` | 0.35 | Peer score must be ≤ this to qualify |

If the peer `DomainSummary` is unavailable (e.g., peer controller not yet
connected), `peer_relief = 0` and the decision falls back to purely local
adaptive scaling.

This policy is **per LAN** — LAN1 spawns in LAN1, LAN2 spawns in LAN2. The
peer is used only as a small threshold bias when it is healthy enough to act
as a real spillover path. It is paired with a VIP_SERVER routing recalibration
in Thread 1: `W_HOPS` is reduced to 0.28 so cross-LAN server selection is more
willing when the local server is clearly more loaded.

### Sliding Window

A score ≥ $\tau_{\text{effective}}$ counts as a "degraded" window. The
trigger fires when the required number of degraded windows is reached:

| Env var | Default | Meaning |
|---------|:-------:|---------|
| `SCALEUP_WINDOW_SIZE` | 5 | Sliding window size |
| `SCALEUP_REQUIRED` | 3 | Degraded windows needed to trigger |

---

## 5. Cooldown and Cap Rules

### Scale-Up Cooldown

After a compute scale-up triggers, further compute scale-up evaluation is
suppressed for the cooldown period:

| Env var | Default | Meaning |
|---------|:-------:|---------|
| `SCALEUP_COMPUTE_COOLDOWN_S` | 45 s | Post-scale-up compute cooldown |

### Scale-Down Cooldown

After any compute scale-up, compute **scale-down** evaluation is also
suppressed:

| Env var | Default | Meaning |
|---------|:-------:|---------|
| `SCALEDOWN_COMPUTE_COOLDOWN_S` | 40 s | Post-scale-up cooldown before scale-down |

### Hard Cap

| Env var | Default | Meaning |
|---------|:-------:|---------|
| `MAX_DYNAMIC_COMPUTE` | 4 | Max dynamic compute nodes per LAN |

Pending compute drains are **subtracted** from the effective dynamic compute
count during scale-up evaluation. This means a short-lived extra live compute
node may exist until later scale-down convergence, but the cap on scale-up
decisions is enforced correctly. The live compute count may briefly be $n+1$
when a drain is pending and a new node is spawned.

### Cross-Direction Reset

When compute scale-up triggers, the compute **scale-down** sliding window is
cleared (and vice versa). This prevents stale "idle" windows from the
pre-scale-up period from triggering an immediate scale-down.

---

## 6. Provisioning Flow

Thread 3's `_handle_compute(alert)` executes the full provisioning lifecycle:

1. **Name generation:** `edge_server_{network_id}_dyn{counter}` using a
   per-network monotonic sequence counter.
2. **IP/MAC allocation:** `IpAllocator` assigns the next free IP in
   `10.0.{lan-1}.6–55` and a deterministic MAC (`00:00:00:00:{lan:02x}:{suffix:02x}`).
3. **Container spawn:** `docker run -d --network none --name <name> -e LAN_ID=lan<N> -e CONTAINER_NAME=<name> edge_server`
   — container starts with no network, so the controller fully controls when
   it becomes reachable.
4. **Network attachment:** `add_network_node.sh --lan <N> --name <name> --ip <ip> --mac <mac>`
   — creates veth pair, attaches to OVS bridge, configures IP/MAC/routes
   inside the container namespace.
5. **VIP registration:** See §7.

Every step is individually timed with `time.perf_counter()`. The `NodeResult`
carries a `StepTimings` record (`docker_run_s`, `network_attach_s`, `total_s`).
On failure at any step, allocated resources are cleaned up and the IP is
returned to the allocator pool.

---

## 7. VIP Admission

On successful spawn + network attach, the manager calls:

```python
self._topo.register_new_server_backend(mac, ip)
```

This single call:
1. Adds the MAC to the VIP web pool (`_local_server_macs`).
2. Seeds the backend IP in `_mac_to_ip`.
3. Creates a short compute **warm lease** — the new backend gets a brief
   preference in Thread 1's VIP_SERVER selection, ensuring traffic reaches
   it quickly for validation.

Thread 1 picks up the new backend on its next controller loop iteration —
no explicit notification is needed. The warm lease expires after a short
period, after which the backend competes on equal footing with other
backends via the standard weighted cost function.

Thread 2 is also notified via `consume_addition_completions()` so it can
track the new MAC for future scale-down decisions.

A `[node_ready]` log marker is emitted at this point, distinguishing the
end-to-end readiness boundary from the `[node_add]` bootstrap-completion
marker.

---

## 8. Environment Variables

### Degradation Score

| Variable | Default | Description |
|----------|:-------:|-------------|
| `SCALEUP_W_CPU` | 0.40 | CPU weight in compute degradation score |
| `SCALEUP_W_T_PROC` | 0.60 | T_proc weight in compute degradation score |
| `SCALEUP_CPU_FLOOR` | 5 | CPU % below which contribution is 0 |
| `SCALEUP_CPU_SPAN` | 10 | CPU normalisation range (5 + 10 = 15 % saturation) |
| `SCALEUP_T_PROC_FLOOR` | 20 | T_proc (ms) below which contribution is 0 |
| `SCALEUP_T_PROC_SPAN` | 80 | T_proc normalisation range (20 + 80 = 100 ms saturation) |

### Adaptive Threshold & Peer Relief

| Variable | Default | Description |
|----------|:-------:|-------------|
| `SCALEUP_COMPUTE_BASE_THRESHOLD` | 0.45 | Adaptive compute base threshold |
| `SCALEUP_COMPUTE_THRESHOLD_INCREMENT` | 0.10 | Per-dynamic-compute-node threshold increment |
| `SCALEUP_COMPUTE_MAX_THRESHOLD` | 0.85 | Adaptive compute threshold cap |
| `SCALEUP_COMPUTE_PEER_RELIEF` | 0.03 | Extra threshold when peer LAN is healthy |
| `SCALEUP_COMPUTE_PEER_HEALTH_THRESHOLD` | 0.35 | Peer compute score ≤ this enables peer_relief |

### Window & Cooldown

| Variable | Default | Description |
|----------|:-------:|-------------|
| `SCALEUP_WINDOW_SIZE` | 5 | Sliding window size (compute) |
| `SCALEUP_REQUIRED` | 3 | Degraded windows required to trigger |
| `SCALEUP_COMPUTE_COOLDOWN_S` | 45 | Post-scale-up compute cooldown (s) |
| `SCALEDOWN_COMPUTE_COOLDOWN_S` | 40 | Post-scale-up cooldown before compute scale-down (s) |
| `MAX_DYNAMIC_COMPUTE` | 4 | Hard cap: max dynamic compute nodes per LAN |

---

## 9. Related Diagram

- [Compute scale-up sequence diagram](../diagrams/compute_scale_up.drawio)

---

## 10. Related Plans

- [Scaling threshold tuning and caps](implementation/plans/metric_drivers_investigation_plan.md) — investigation into CPU/T_proc drivers.
- [Orchestration overview](../orchestration/elasticity_manager_orchestration.md) — queue dispatch and handoffs.
