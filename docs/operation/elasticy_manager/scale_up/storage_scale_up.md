# Storage Scale-Up

## 1. Purpose

Storage scale-up spawns additional `edge_storage_server` containers
(MongoDB secondaries) in response to sustained database latency (`T_db`) and
storage CPU pressure on the local LAN. The decision is made by Thread 2
(`ScalingPolicy`) using a diminishing-increment adaptive threshold and
executed by Thread 3 (`ElasticityManager` → `StorageNodeAdder`). RS join is
asynchronous via the container sidecar; VIP_DATA promotion is deferred until
the node reaches SECONDARY state.

Source: [`source/sdn_controller/scaling_policy.py`](../../../source/sdn_controller/scaling_policy.py),
[`source/sdn_controller/elasticity/storage_node_manager.py`](../../../source/sdn_controller/elasticity/storage_node_manager.py)

---

## 2. Trigger Path

```
TelemetrySummary (ZMQ)
    │
    ▼
_on_telemetry_update()                    [main_n*.py — Thread 2 mediator]
    ├─ evaluate scale-up                  [ScalingPolicy.evaluate_scale_up()]
    │   ├─ check storage scale-up cooldown
    │   ├─ check storage cap
    │   ├─ compute tail-aware latency signal
    │   ├─ compute storage degradation score
    │   ├─ compute diminishing-increment threshold
    │   ├─ append to sliding window
    │   └─ if window_hits >= REQUIRED → return DataAlert(lan, network_id, rs_name, primary_container)
    │
    ▼
self._elasticity.submit(DataAlert)         [Thread 2 → Thread 3 queue — priority 1]
    │
    ▼
_loop() pops alert → _handle_data()       [Thread 3]
    ├─ allocate IP/MAC
    ├─ StorageNodeAdder.add_storage_node()
    │   ├─ docker run edge_storage_server (with RS_SEED_HOST)
    │   └─ add_network_node.sh
    ├─ TopologyMixin.register_backend_ip() [IP→MAC seeded; VIP deferred]
    └─ [sidecar async] _rs_self_join() → _wait_for_ready() → emits rs_secondary_ready
```

A dormant Tier 2 supersede hook exists in the mediator: if `DataAlert` is
cross-LAN (`cross_lan_rs=True`), it drains any active Tier 1 for the same
direction before the Tier 2 spawn. Today all `DataAlert`s are same-LAN, so
this branch is inert. See
[`selective_sync_overview.md`](../../selective_sync/selective_sync_overview.md).

### 2.1 Persistent Reserve Model

When `STORAGE_PERSISTENT_RESERVE_ENABLED=1`, the first same-LAN storage
scale-up action changes from "spawn a new active storage node" to
"activate the ready reserve, then replenish". This removes the first-step
readiness gap from the critical path.

**Reserve lifecycle per LAN:**

1. Thread 2 maintains one `StorageReserveSlot` per LAN.
2. When the slot is `NONE` and a PRIMARY is visible, Thread 2 submits
   `PrepareStandbyStorageAlert` to Thread 3.
3. Thread 3 creates a real `SECONDARY` via the existing storage add path,
   with `standby_reserved=True` and heartbeat enabled. The node stays
   **outside** `VIP_DATA`.
4. When the sidecar reports `rs_secondary_ready`, the control-event
   dispatcher marks the slot `READY_RESERVED` instead of adding the node
   to VIP.
5. The first same-LAN `DataAlert` or recovery-distress signal activates
   the ready reserve immediately (adds to VIP, clears `standby_reserved`,
   resets cooldowns).
6. Replenishment starts immediately after activation or reserve loss.
7. Only one reserve preparation may be in flight per LAN at a time.
8. Ordinary storage scale-down is blocked unless a `READY_RESERVED` slot
   exists after the removal (reserve floor).

**Reserve slot states:**

| State | Meaning | Counts as active | Eligible for VIP |
|-------|---------|:---:|:---:|
| `NONE` | No reserve exists | No | No |
| `PREPARING` | Creation in flight | No | No |
| `READY_RESERVED` | Ready, heartbeating, outside VIP | No | No |

**Log markers (stable):**

```text
[reserve] prepare_submitted lan=%d
[reserve] ready_reserved lan=%d name=%s ip=%s mac=%s
[reserve] activated lan=%d name=%s ip=%s mac=%s reason=%s
[reserve] waiting_ready lan=%d reason=%s
[reserve] lost lan=%d mac=%s
[reserve] replenish_submitted lan=%d
```

Source: [`source/sdn_controller/node_registry.py`](../../../source/sdn_controller/node_registry.py),
[`source/sdn_controller/elasticity/elasticity.py`](../../../source/sdn_controller/elasticity/elasticity.py),
[`source/sdn_controller/control_events.py`](../../../source/sdn_controller/control_events.py),
[`source/sdn_controller/main_n1.py`](../../../source/sdn_controller/main_n1.py),
[`source/sdn_controller/main_n2.py`](../../../source/sdn_controller/main_n2.py)

---

## 3. Storage Degradation Score

The weighted degradation score is per-LAN and CPU-dominant, because scaling
storage directly reduces CPU contention on the storage tier:

$$
\text{score} = 0.7 \cdot \text{cpu\_component} + 0.3 \cdot \text{lat\_component}
$$

Each component is normalised and clamped to $[0, 1]$:

$$
\text{component} = \min\!\left(1.0,\ \frac{\max(0,\ \text{value} - \text{floor})}{\text{span}}\right)
$$

| Component | Weight | Input metric                            | Floor |  Span  | Saturation |
| --------- | :----: | --------------------------------------- | :----: | :----: | :--------: |
| CPU       |  0.7  | `avg_storage_cpu_percent`             |  5 %  |   10   |    15 %    |
| Latency   |  0.3  | `max(avg_time_db_ms, p95_time_db_ms)` | 150 ms | 600 ms |   750 ms   |

### Tail-Aware Latency Signal

The latency input is **not** the simple domain average. Thread 2 scores
storage against `max(avg_time_db_ms, p95_time_db_ms)` — the tail-aware signal.
This means sustained p95 growth can trigger Tier 2 before the mean fully
rises, providing predictive scale-up for latency-sensitive workloads.

---

## 4. Diminishing Increment Threshold

Storage scale-up uses a **diminishing-increment adaptive threshold**. Each
successive dynamic storage node raises the effective threshold by an increment
that **halves with every node added**, floored at a minimum value. This
provides aggressive early resistance — the first few nodes face a rapidly
rising bar — while still allowing the system to react to genuine saturation at
higher node counts.

### Formula

$$
\tau_{\text{effective}} = \min\!\left(\text{BASE} + \sum_{i=0}^{n-1} \max(\text{INCREMENT} \cdot 0.5^{i},\ \text{MIN\_INCREMENT}),\ \text{MAX}\right)
$$

Where $n$ = number of active dynamic storage nodes in that LAN.

### Progression

|  $n$  | Per-node increment | Cumulative added | $\tau_{\text{effective}}$ |
| :-----: | :----------------: | :--------------: | :-------------------------: |
|    0    |         —         |      0.000      |       **0.25**       |
|    1    |       0.100       |      0.100      |       **0.35**       |
|    2    |       0.050       |      0.150      |       **0.40**       |
|    3    |    0.050 (min)    |      0.200      |       **0.45**       |
|    4    |       0.050       |      0.250      |       **0.50**       |
| 5 (cap) |       0.050       |      0.300      |       **0.55**       |

### Sliding Window

A score ≥ $\tau_{\text{effective}}$ counts as a "degraded" window. The trigger
fires with a lower bar than compute (2-of-5 vs 3-of-5), reflecting the higher
urgency of storage latency relief:

| Env var                         | Default | Meaning                            |
| ------------------------------- | :-----: | ---------------------------------- |
| `SCALEUP_STORAGE_WINDOW_SIZE` |    5    | Sliding window size                |
| `SCALEUP_STORAGE_REQUIRED`    |    2    | Degraded windows needed to trigger |

---

## 5. Cooldown and Cap Rules

### Scale-Up Cooldown

After a storage scale-up triggers, further storage scale-up evaluation is
suppressed:

| Env var                        | Default | Meaning                        |
| ------------------------------ | :-----: | ------------------------------ |
| `SCALEUP_STORAGE_COOLDOWN_S` |  120 s  | Post-scale-up storage cooldown |

### Scale-Down Cooldown

After any storage scale-up, storage **scale-down** evaluation is also
suppressed:

| Env var                          | Default | Meaning                                          |
| -------------------------------- | :-----: | ------------------------------------------------ |
| `SCALEDOWN_STORAGE_COOLDOWN_S` |  120 s  | Post-scale-up cooldown before storage scale-down |

### Hard Cap

| Env var                 | Default | Meaning                                                         |
| ----------------------- | :-----: | --------------------------------------------------------------- |
| `MAX_DYNAMIC_STORAGE` |    5    | Max dynamic storage nodes per LAN (MongoDB ≤ 7 voting members) |

### Cross-Direction Reset

When storage scale-up triggers, the storage **scale-down** sliding window is
cleared (and vice versa).

---

## 6. Provisioning Flow

Thread 3's `_handle_data(alert)` executes the provisioning lifecycle:

1. **Name generation:** `edge_storage_{network_id}_dyn{counter}` using a
   per-network monotonic sequence counter.
2. **IP/MAC allocation:** `IpAllocator` assigns the next free IP and
   deterministic MAC.
3. **Container spawn:** `docker run -d --network none --name <name> -v <name>-data:/data/db -e LAN_ID=lan<N> -e MONGO_REPLSET=<rs> -e MONGO_PORT=<port> -e IFACE=eth0 -e OWN_IP=<ip> -e OWN_MAC=<mac> -e RS_ADD_SELF=true -e RS_SEED_HOST=<primary_ip:port> edge_storage_server`
   — container starts with no network, sidecar configured with identity hints
   and seed host.
4. **Network attachment:** `add_network_node.sh --lan <N> --name <name> --ip <ip> --mac <mac>`
   — veth pair, OVS attach, IP/MAC/routes inside container namespace.
5. **IP→MAC seeding:** `TopologyMixin.register_backend_ip(mac, ip)` — Thread 1
   gets the mapping, but VIP is **not** registered yet (see § 8).

The controller returns after network attachment (~5–12 s) instead of waiting
for RS sync. The sidecar handles RS join asynchronously.

### Idempotency

Before `docker run`, the node manager inspects the container state:

| Existing state | Action                                         |
| -------------- | ---------------------------------------------- |
| Not found      | Create normally                                |
| Running        | Skip `docker run`, proceed to network attach |
| Stopped/exited | Remove container + volume, recreate            |

Stale volumes are always cleaned up before `docker run` to avoid replica-set
ID clashes from a previous failed attempt.

---

## 7. Async Replica-Set Join

RS join is performed **inside the container** by the `mongo_telemetry.py`
sidecar — not by the controller or a shell script.

### Sidecar Sequence

1. Wait for `eth0` + seed host reachability.
2. Connect directly to `RS_SEED_HOST` (the static `.4` storage node in the
   target LAN — no extra `isMaster` discovery round).
3. Perform a single `replSetReconfig` that both removes any stale member at
   the same `host:port` and adds the new member — eliminating the "Already
   present" errors that previously caused 86% spawn failure rates.
4. Retry with exponential backoff (5 attempts).
5. Wait for SECONDARY state (configurable timeout: `RS_READY_TIMEOUT_S`,
   default 300 s).
6. Emit `rs_secondary_ready` ZMQ event → triggers fast-path VIP promotion.

### Controller Non-Blocking

The sidecar creates its ZMQ socket **after** `_rs_self_join()` (which waits
for eth0 + seed connectivity) but **before** `_wait_for_ready()`. This ensures
telemetry flows even while the node is syncing, and prevents an infinite block
if RS join fails. The controller returns after network attach (~5–12 s)
instead of waiting for RS sync (~34–45 s), allowing Thread 3 to process other
alerts.

### Identity Hints

Thread 3 injects `OWN_IP`, `OWN_MAC`, and `IFACE=eth0` into the container at
`docker run` time. The sidecar validates these identity hints first and falls
back to in-container discovery when they are absent or malformed.

---

## 8. Deferred VIP_DATA Promotion

Storage VIP admission is **deferred** until the node is confirmed SECONDARY.
This prevents routing traffic to a node that hasn't finished its initial sync.

### Fast Path — `rs_secondary_ready` Control Event

1. Sidecar emits a one-shot `rs_secondary_ready` ZMQ event when the node
   reaches `SECONDARY`.
2. `ControlEventDispatcher.process_secondary_events()` receives it.
3. Calls the `_promote_storage_backend(mac, domain)` helper:
   - `add_storage_mac(mac, domain)` — admit to `VIP_DATA` pool.
   - `mark_storage_backend_warm(mac, domain)` — short warm lease so the
     promoted node gets a brief preference on the next eligible selection.
4. `[node_ready]` log marker emitted.

### Fallback — Telemetry-Based `member_state` Detection

1. The sidecar includes `stateStr` in every `mongo_stats` and `heartbeat`
   event.
2. The aggregator propagates it via `StorageServerSummary.member_state`.
3. `_promote_storage_from_telemetry()` checks each storage node in the summary
   and promotes it if `member_state == "SECONDARY"` and not already
   registered (~2–4 s delay vs fast path).

### Warm Lease

At promotion time, a short storage warm lease is marked. This prevents routing
traffic to a node that hasn't finished its initial sync while still giving the
promoted node a brief preference on the next fresh eligible selection.

---

---

## 10. Environment Variables

### Degradation Score

| Variable                      | Default | Description                                                |
| ----------------------------- | :-----: | ---------------------------------------------------------- |
| `SCALEUP_W_STORAGE_CPU`     |   0.7   | CPU weight (dominant — scaling fixes CPU contention)      |
| `SCALEUP_W_T_DB`            |   0.3   | T_db weight (secondary contention indicator)               |
| `SCALEUP_STORAGE_CPU_FLOOR` |    5    | Storage CPU % below which contribution is 0                |
| `SCALEUP_STORAGE_CPU_SPAN`  |   10   | Storage CPU normalisation range (5 + 10 = 15 % saturation) |
| `SCALEUP_T_DB_FLOOR`        |   150   | T_db (ms) below which contribution is 0                    |
| `SCALEUP_T_DB_SPAN`         |   600   | T_db normalisation range (150 + 600 = 750 ms saturation)   |

### Diminishing-Increment Threshold

| Variable                                | Default | Description                                    |
| --------------------------------------- | :-----: | ---------------------------------------------- |
| `SCALEUP_STORAGE_BASE_THRESHOLD`      |  0.25  | Adaptive base threshold                        |
| `SCALEUP_STORAGE_THRESHOLD_INCREMENT` |  0.10  | Starting per-node increment (halves each node) |
| `SCALEUP_STORAGE_MIN_INCREMENT`       |  0.05  | Floor for per-node increment                   |
| `SCALEUP_STORAGE_MAX_THRESHOLD`       |  0.55  | Adaptive threshold cap                         |

### Window & Cooldown

| Variable                         | Default | Description                                          |
| -------------------------------- | :-----: | ---------------------------------------------------- |
| `SCALEUP_STORAGE_WINDOW_SIZE`  |    5    | Sliding window size                                  |
| `SCALEUP_STORAGE_REQUIRED`     |    2    | Degraded windows required to trigger                 |
| `SCALEUP_STORAGE_COOLDOWN_S`   |   120   | Post-scale-up storage cooldown (s)                   |
| `SCALEDOWN_STORAGE_COOLDOWN_S` |   120   | Post-scale-up cooldown before storage scale-down (s) |
| `MAX_DYNAMIC_STORAGE`          |    5    | Hard cap: max dynamic storage nodes per LAN          |

---

## 11. Related Diagram

- [Storage scale-up sequence diagram](../diagrams/storage_scale_up.drawio)

---

## 12. Related Plans

- [Storage standby-first scale-up](../implementation/storage_standby_first_scaleup/README.md) — phased plan for pre-warmed Tier 2 standbys.
- [Orchestration overview](../orchestration/elasticity_manager_orchestration.md) — queue dispatch, alert priority, and handoffs.
