# VIP Routing Backend Selection and Warm Leases

## 1. Purpose

This document describes how `VipRoutingMixin` selects backend containers using
multi-dimensional WSM (Weighted Sum Model) cost functions, how warm leases
steer traffic toward newly admitted or promoted backends, and how the
controller-side lifecycle hooks keep VIP membership, backend IP seeding, and
warm-lease state synchronized across threads.

It covers the selector logic only -- DNAT/SNAT rule installation, ARP
interception, and edge-side epoch behaviour are documented separately.

## 2. Current Files

| File | Role |
|------|------|
| `source/sdn_controller/vip_routing.py` | Public `VipRoutingMixin` facade -- controller-facing selection and lifecycle API |
| `source/sdn_controller/_vip_routing/selection.py` | `select_server()`, `select_storage()`, warm-lease claim logic, recovery filtering, hop estimation |
| `source/sdn_controller/_vip_routing/state.py` | Mutable VIP-routing state, lifecycle hooks, and telemetry cache updates |
| `source/sdn_controller/_vip_routing/config.py` | WSM weights, logger, and shared lightweight types |
| `source/sdn_controller/main_n1.py`, `source/sdn_controller/main_n2.py` | `_on_telemetry_update()` callback calls `update_server_stats()` / `update_storage_stats()` |
| `source/sdn_controller/scaling_config.py` | Warm-lease TTL defaults (`_VIP_WARM_SERVER_SECONDS`, `_VIP_WARM_STORAGE_SECONDS`) |
| `source/sdn_controller/telemetry/models.py` | `ServerSummary` and `StorageServerSummary` data classes |

## 3. Topology Pools Consumed by VIP Routing

`VipRoutingMixin` depends on three topology-owned membership dictionaries
(defined as attributes on `TopologyMixin`):

| Pool | Purpose | Populated By |
|------|---------|-------------|
| `vip_server_pool` | Edge-server HTTP backends eligible for `VIP_SERVER` selection | Thread 3 (elasticity manager) via `add_server_mac()` / `remove_server_mac()` |
| `vip_storage_pool_n1` | MongoDB storage backends on LAN 1 eligible for `VIP_DATA_N1` selection | Thread 2 (telemetry) via `add_storage_mac()` / `remove_storage_mac()` |
| `vip_storage_pool_n2` | MongoDB storage backends on LAN 2 eligible for `VIP_DATA_N2` selection | Thread 2 (telemetry) via `add_storage_mac()` / `remove_storage_mac()` |

Each pool entry maps `mac → {"mac": ..., ...}`. Pool membership alone does not
guarantee selection -- the backend must also have a known IP in `_mac_to_ip`
before a warm lease can be claimed or WSM scoring can proceed.

## 4. Telemetry Inputs

Thread 2's `_on_telemetry_update()` callback (in `main_n*.py`) calls two
methods that refresh the per-backend snapshots consumed by the WSM cost
functions:

### `update_server_stats(servers: dict[str, ServerSummary])`

Stores per-server telemetry keyed by MAC. Each container discovers its own MAC
from `eth0` and includes it in telemetry events; the aggregator forwards it as
the dict key. Fields used by `select_server()`:

| Field | WSM Dimension | Source |
|-------|--------------|--------|
| `avg_cpu_percent` | CPU | Container-level CPU measurement |
| `avg_ram_used_mb` | RAM | Container-level RAM measurement |
| `request_count` | Requests | Request counter over the telemetry window |

### `update_storage_stats(storage_servers: dict[str, StorageServerSummary])`

Stores per-storage telemetry keyed by MAC. Fields used by `select_storage()`:

| Field | WSM Dimension | Source |
|-------|--------------|--------|
| `avg_cpu_percent` | CPU | Container-level CPU measurement |
| `avg_ram_used_mb` | RAM | Container-level RAM measurement |
| `avg_connections` | Connections | MongoDB connection count |
| `avg_repl_lag_s` | Replication Lag | `rs.status()` lag (may be `None`) |
| `member_state` | -- | Used by Thread 2 for promotion decisions, not by WSM directly |

## 5. Server Selection

`select_server(client_mac)` picks the edge-server backend with the lowest WSM
cost from `vip_server_pool`.

### Cost Function

$$
Cost_j = w_{cpu} \cdot \frac{CPU_j}{CPU_{max}} + w_{ram} \cdot \frac{RAM_j}{RAM_{max}} + w_{req} \cdot \frac{Req_j}{Req_{max}} + w_{hops} \cdot \frac{Hops_j}{Hops_{max}}
$$

### Current Default Weights

| Weight | Env Var | Default |
|--------|---------|---------|
| $w_{cpu}$ | `W_CPU` | `0.2` |
| $w_{ram}$ | `W_RAM` | `0.2` |
| $w_{req}$ | `W_REQUESTS` | `0.2` |
| $w_{hops}$ | `W_HOPS` | `0.28` |

### Normalization

- $CPU_{max}$, $RAM_{max}$, $Req_{max}$ are computed as the maximum value
  **among backends that have telemetry** in the pool. If no backends have
  stats, each max defaults to `1.0` to avoid division by zero.
- $Hops_{max}$ is `max(hop_cache_max, 1)`.

### Selection Order

1. **Warm lease claim.** If a valid warm lease exists for a backend that is
   still in the pool and has a known IP, that backend is selected immediately
   (see Section 8).
2. **WSM scoring.** If no warm lease is claimable, all backends in the pool are
   scored and the lowest-cost candidate is chosen.
3. **Round-robin tie-breaking.** When multiple backends share the lowest cost,
   a global `_rr_server_idx` counter distributes traffic evenly.

## 6. Storage Selection

`select_storage(domain, client_mac)` picks the storage
backend with the lowest WSM cost from the domain's pool
(`vip_storage_pool_n1` or `vip_storage_pool_n2`).

### Cost Function

$$
Cost_j = w_{cpu} \cdot \frac{CPU_j}{CPU_{max}} + w_{ram} \cdot \frac{RAM_j}{RAM_{max}} + w_{conn} \cdot \frac{Conn_j}{Conn_{max}} + w_{lag} \cdot \frac{Lag_j}{Lag_{max}} + w_{hops} \cdot \frac{Hops_j}{Hops_{max}}
$$

### Current Default Weights

| Weight | Env Var | Default |
|--------|---------|---------|
| $w_{cpu}$ | `W_STORAGE_CPU` | `0.2` |
| $w_{ram}$ | `W_STORAGE_RAM` | `0.2` |
| $w_{conn}$ | `W_STORAGE_CONNECTIONS` | `0.1` |
| $w_{lag}$ | `W_STORAGE_LAG` | `0.2` |
| $w_{hops}$ | `W_STORAGE_HOPS` | `0.3` |

### Normalization

Same pattern as server selection: max values are computed from pool members
with telemetry, defaulting to `1.0` when no stats exist. Replication lag
(`avg_repl_lag_s`) may be `None`, in which case it is treated as `0` in the
max computation and normalization.

### Recovery Filtering

When `recovery=True`, the pool is first filtered through
`_filter_previous_normal_backend()` (see Section 9) before warm-lease claiming
or WSM scoring. This excludes the remembered last-normal backend when another
candidate exists.

### Selection Order

1. **Recovery pool filtering** (if `recovery=True`).
2. **Warm lease claim** (see Section 8).
3. **WSM scoring** across all pool members.
4. **Round-robin tie-breaking** using a per-domain counter
   (`_rr_storage_idx[domain]`).
5. **Remember normal choice.** If not a recovery selection, the chosen backend
   is recorded via `_remember_normal_storage_choice()`.

## 7. Unknown Telemetry and Tie-Breaking

### Unknown Telemetry -- Policy-Dependent Assignment

Backends without telemetry stats (e.g., peer backends not yet measured, newly
added nodes) are assigned a default normalized score that depends on the active
backend-selection policy mode (`BACKEND_SELECTION_POLICY`):

| Policy Mode | Unknown-Stats Default | Rationale |
|---|---|---|
| `topology_host` | **0.0** (best-case) | Cold-start thundering herd — new backends win every WSM competition immediately, encoding HAProxy leastconn with no slow-start. |
| `topology_slowstart` | **0.0** (neutral) | The slowstart penalty (Section 11) handles all deterrence; unknown stats are neutral so the penalty is the sole gate. |
| `topology_lifecycle` | **1.0** (worst-case) | Default/current behavior — prevents unmeasured peers from being preferred over measured local backends. Warm leases short-circuit the WSM for new backends, so unknown stats only affect existing unmeasured backends. |

In all modes, `hop_norm` is never overridden — topology is always computed from
real hop-cache data or the fallback estimation table below.

### Hop Fallback Estimation

When a hop count is not in `hop_cache` for a given `(client_mac, backend_mac)`
pair, it is estimated in priority order:

| Condition | Hops Assigned |
|-----------|--------------|
| Path in `hop_cache` | Real shortest-path length |
| Local, no path yet | `max(_avg_hop_count, 1.0)` |
| Cross-network (peer) | `max(_avg_hop_count, 1.0) + max(_peer_avg_hop_count, 1.0)` |
| Truly unknown MAC | `hops_max` (worst case) |

The `max(..., 1.0)` guard prevents cold-start zero values from making
cross-network backends appear cost-free. `_avg_hop_count` is computed by
`TopologyMixin._rebuild_hop_cache()` and `_peer_avg_hop_count` is received via
topology updates.

### Round-Robin Tie-Breaking

When multiple backends share the identical lowest WSM cost (common during cold
start when all resource dimensions are 0.0), a round-robin counter distributes
traffic evenly:

- Server selection uses a single global counter `_rr_server_idx`.
- Storage selection uses per-domain counters `_rr_storage_idx["n1"]` and
  `_rr_storage_idx["n2"]`.

## 8. Warm Lease Claim Path

Newly admitted compute backends and newly promoted storage secondaries receive
bounded warm leases. A warm lease is a monotonic expiry timestamp only -- it
carries no additional state.

**Policy-mode gating (RQ2)**: Warm leases are always **created** by the
elasticity manager (Thread 3) and telemetry pipeline (Thread 2) regardless of
policy mode — the creation path is unchanged. However, warm leases are only
**consumed** by the WSM selection functions when
`BACKEND_SELECTION_POLICY=topology_lifecycle`. In `topology_host` and
`topology_slowstart` modes, `_claim_warm_backend()` is gated off — unclaimed
leases expire after their TTL with an info-level log line. This is harmless and
keeps the code change minimal (no modification to `main_n*.py` or
`elasticity/`).

### Lease Data Structure

```python
@dataclass(frozen=True)
class WarmLease:
    started_ts: float   # time.monotonic() when lease was created
    expires_ts: float   # time.monotonic() when lease expires
```

### Claim Path (`_claim_warm_backend()`)

1. **Acquire `_warm_lock`** -- the only thread-synchronized section in
   `VipRoutingMixin`, needed because Thread 3 (native thread) writes warm
   leases while Thread 1 (eventlet greenthread) reads and claims them.
2. **Expire stale leases.** Any lease with `expires_ts <= now` is removed from
   the dict.
3. **Filter claimable candidates.** A lease is claimable only when:
   - Its MAC is present in the concrete VIP pool.
   - Its MAC has a known backend IP in `_mac_to_ip`.
4. **Newest wins.** If multiple leases are claimable, the one with the highest
   `started_ts` wins. This keeps the brief post-scale-up preference aligned
   with the latest admitted backend under sustained load.
5. **Return the chosen pool entry.** The caller uses it directly; the lease
   remains in the dict until it expires naturally -- it is not consumed on
   claim.

### Lease Creation

| Backend Type | Created By | Method | TTL Default |
|-------------|-----------|--------|-------------|
| Compute (server) | Thread 3 | `register_new_server_backend(mac, ip)` → `mark_server_backend_warm(mac)` | `VIP_WARM_SERVER_SECONDS` (45 s) |
| Storage | Thread 2 | `_promote_storage_backend()` → `mark_storage_backend_warm(mac, domain)` | `VIP_WARM_STORAGE_SECONDS` (30 s) |

### Lease Invalidation

Warm leases are explicitly cleared on backend removal via
`clear_server_backend_warm(mac)` and `clear_storage_backend_warm(mac, domain)`
because dynamic MAC/IP identities are allocator-recycled. Later admission still
overwrites any prior lease before the backend becomes claimable, providing a
secondary safety net.

## 9. Recovery Avoidance via Last Normal Choice

Normal (non-recovery) `VIP_DATA` selections remember the chosen backend per
`(edge_server_mac, domain)` inside `_last_normal_storage_choice`. Recovery
selections use this state to avoid reconnecting to the same backend that may
have caused the failure.

### Remembering (`_remember_normal_storage_choice()`)

Called at the end of every normal (non-recovery) `select_storage()` call. The
warm-lease fast path also calls it when a warm backend is claimed outside
recovery. Protected by `_warm_lock`.

### Filtering (`_filter_previous_normal_backend()`)

Called at the start of recovery `select_storage()`:

1. Look up the remembered normal backend for `(client_mac, domain)`.
2. If the remembered MAC is still in the pool, return a filtered pool that
   excludes it.
3. If the filtered pool would be empty, fall back to the full pool -- it is
   better to try the same backend than to have no candidates.
4. If the remembered MAC is no longer in the pool (peer disappeared, local
   unregistered), return the full pool unchanged.

### Forgetting (`_forget_normal_storage_choice()`)

Called by `unregister_storage_backend(mac, domain)` to clear any remembered
entries that still point at the removed backend. Scans all keys matching the
given domain and removes those whose remembered MAC equals the removed backend.

### Key Constraints

- Recovery selections **never** overwrite `_last_normal_storage_choice`. Only
  normal selections update it.
- The recovery filter is a soft preference, not a hard guarantee -- if the
  only candidate is the same backend, it will still be used.
- Peer disappearance is safe because `_filter_previous_normal_backend()` falls
  back when the remembered backend is absent from the pool.

## 10. Backend-Selection Policy Modes (RQ2)

The controller supports three backend-selection policy modes, controlled by the
`BACKEND_SELECTION_POLICY` env var (default: `topology_lifecycle`).

### Policy Mode Table

| Mode | Warm Lease | Unknown Stats | Slowstart Penalty | Encodes |
|---|---|---|---|---|
| `topology_host` | Not consumed | 0.0 (best-case) | None | HAProxy leastconn, no slow-start — cold-start thundering herd |
| `topology_slowstart` | Not consumed | 0.0 (neutral) | 1.0→0.0 over TTL from discovery | Separated LB slow-start — coordination gap between spawn and discovery |
| `topology_lifecycle` | Consumed (default) | 1.0 (worst-case) | None | Unified controller — spawn-time warm lease, zero discovery gap |

All other parameters (WSM weights, host-load dimensions, pool structure,
telemetry delivery) are identical across modes.

### Design Rationale

The three modes form a spectrum of routing-plane awareness timing relative to
backend spawn, directly parallel to RQ1's telemetry-delivery cadence
comparison (push vs. poll). RQ1 tests the coordination gap in monitoring;
RQ2 tests the same phenomenon in routing.

## 11. Slowstart Penalty Ramp (topology_slowstart)

When `BACKEND_SELECTION_POLICY=topology_slowstart`, the WSM cost function adds
a graduated penalty to each backend's cost after it is first discovered in
telemetry. The penalty simulates a separated LB's slow-start mechanism
(HAProxy slow-start, NGINX initial weight).

### Mechanism

- **Before discovery**: penalty = 1.0 (flat). The backend is effectively
  invisible — it will only win traffic via round-robin tie-breaking if all
  other backends are equally penalised.
- **At discovery** (first telemetry window containing the backend): penalty
  begins decaying linearly from 1.0 to 0.0 over the warm-lease TTL period
  (`VIP_WARM_SERVER_SECONDS` = 45 s for compute, `VIP_WARM_STORAGE_SECONDS`
  = 30 s for storage).
- **After ramp**: penalty = 0.0 — backend competes on real WSM cost only.

### Discovery Tracking

Discovery time is recorded when a backend first appears in telemetry
(`_backend_discovery_ts[mac]`), set by `update_server_stats()` and
`update_storage_stats()` in `state.py`. The discovery timestamp is cleaned up
on `unregister_server_backend()` and `unregister_storage_backend()`.

### Design Note — Penalty Magnitude

The unweighted penalty (range 0–1) exceeds the maximum weighted WSM cost sum
(0.88 for compute, 0.90 for storage). This means the penalty is architecturally
dominant — a backend under slowstart cannot win against any backend with real
stats until the penalty has decayed substantially. This is intentional: the
ramp IS the mechanism, not a subtle bias.

### Design Note — TTL Reuse

The penalty decay period reuses `_VIP_WARM_SERVER_SECONDS` and
`_VIP_WARM_STORAGE_SECONDS` — the same TTLs used for warm-lease priority
windows. These are semantically distinct (warm-lease priority vs.
discovery-time ramp), but using the same TTL makes the comparison between
`topology_slowstart` and `topology_lifecycle` cleaner: both have the same
duration, differing only in when that window starts (discovery vs. spawn).

## 12. Controller Lifecycle Hooks

These methods are the public API that Thread 2 (telemetry) and Thread 3
(elasticity) call to keep VIP state synchronized when backends are promoted,
admitted, removed, or retracted.

### Thread 3 (Elasticity) Hooks

| Method | Effect |
|--------|--------|
| `register_new_server_backend(mac, ip)` | Adds MAC to `vip_server_pool`, seeds `_mac_to_ip`, creates server warm lease |
| `unregister_server_backend(mac)` | Removes MAC from `vip_server_pool`, clears server warm lease |

### Thread 2 (Telemetry/Promotion) Hooks

| Method | Effect |
|--------|--------|
| `mark_server_backend_warm(mac)` | Creates/renews a server warm lease for an existing pool member |
| `mark_storage_backend_warm(mac, domain)` | Creates/renews a storage warm lease for an existing pool member |
| `clear_server_backend_warm(mac)` | Removes a server warm lease |
| `clear_storage_backend_warm(mac, domain)` | Removes a storage warm lease |
| `unregister_storage_backend(mac, domain)` | Removes MAC from the domain's storage pool, clears storage warm lease, forgets normal choice |

All warm-lease mutations are protected by `_warm_lock` (a `threading.Lock`)
because Thread 3 is a native thread while Thread 1 is an eventlet greenthread.

## 13. Current Weight and Lease Knobs

### WSM Weights (set via environment variables)

| Env Var | Default | Applies To |
|---------|---------|------------|
| `W_CPU` | `0.2` | Server selection |
| `W_RAM` | `0.2` | Server selection |
| `W_REQUESTS` | `0.2` | Server selection |
| `W_HOPS` | `0.28` | Server selection |
| `W_STORAGE_CPU` | `0.2` | Storage selection |
| `W_STORAGE_RAM` | `0.2` | Storage selection |
| `W_STORAGE_CONNECTIONS` | `0.1` | Storage selection |
| `W_STORAGE_LAG` | `0.2` | Storage selection |
| `W_STORAGE_HOPS` | `0.3` | Storage selection |

### Warm Lease TTLs

| Env Var | Default | Applies To |
|---------|---------|------------|
| `VIP_WARM_SERVER_SECONDS` | `45` | Compute warm lease TTL |
| `VIP_WARM_STORAGE_SECONDS` | `30` | Storage warm lease TTL |

### Flow Timeouts (relevant to selection lifecycle)

| Env Var | Default | Effect on Selection |
|---------|---------|---------------------|
| `VIP_IDLE_TIMEOUT` | `30` | After this idle period the DNAT rule expires and the next packet triggers fresh selection |
| `VIP_HARD_TIMEOUT` | `120` | Hard limit on DNAT rule lifetime; forces fresh selection |
| `VIP_DATA_RECOVERY_IDLE_TIMEOUT` | `40` | ❌ Removed — recovery VIPs no longer exist |
| `VIP_DATA_RECOVERY_HARD_TIMEOUT` | `45` | ❌ Removed — recovery VIPs no longer exist |
