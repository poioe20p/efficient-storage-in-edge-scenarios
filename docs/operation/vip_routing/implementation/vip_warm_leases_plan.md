# VIP Warm Leases Plan

Reference: [vip_warm_start_and_vip_data_refresh_plan.md](./vip_warm_start_and_vip_data_refresh_plan.md)

## Objective

Add bounded warm-start preference for newly VIP-eligible compute and storage
backends without changing steady-state WSM routing or forcing live compute
connection cutover.

## Approved Decisions

- Use bounded warm leases with both a time limit and a selection budget.
- Keep warm-lease state in `VipRoutingMixin`, guarded by a small
  `threading.Lock`, because compute admission still comes from native Thread 3.
- Treat "not yet visible in the concrete VIP pool" as temporary
  non-claimability, not stale state.
- Create the compute warm lease as soon as a new compute backend is admitted to
  `VIP_SERVER`.
- Keep `VIP_SERVER` natural-move only in this phase, so the compute warm window
  must outlast the current `VIP_HARD_TIMEOUT`.

---

## Implementation Steps

### 1. Add warm-start configuration knobs

Modify [scaling_config.py](../../../../source/sdn_controller/scaling_config.py)
to hold four warm-start controls and one refresh fan-out limit.

Suggested knobs:

- `VIP_WARM_STORAGE_SECONDS`
- `VIP_WARM_STORAGE_SELECTIONS`
- `VIP_WARM_SERVER_SECONDS`
- `VIP_WARM_SERVER_SELECTIONS`
- `VIP_DATA_WARM_REFRESH_TARGETS`

Suggested defaults direction:

- Storage warm window: short, with a small selection budget.
- Compute warm window: longer than storage and above the current
  `VIP_HARD_TIMEOUT=120 s` because compute traffic movement stays passive.
- Refresh target count: a small bounded subset of local edge servers.

Example shape:

```python
VIP_WARM_STORAGE_SECONDS = float(os.environ.get("VIP_WARM_STORAGE_SECONDS", "15"))
VIP_WARM_STORAGE_SELECTIONS = int(os.environ.get("VIP_WARM_STORAGE_SELECTIONS", "4"))
VIP_WARM_SERVER_SECONDS = float(os.environ.get("VIP_WARM_SERVER_SECONDS", "150"))
VIP_WARM_SERVER_SELECTIONS = int(os.environ.get("VIP_WARM_SERVER_SELECTIONS", "8"))
VIP_DATA_WARM_REFRESH_TARGETS = int(os.environ.get("VIP_DATA_WARM_REFRESH_TARGETS", "1"))
```

What this achieves:

- bounds the warm period in time so a backend cannot stay preferred forever
- also bounds the preference by usage count under sustained traffic
- keeps compute eligible long enough to benefit from natural connection churn
- caps the refresh blast radius once the storage refresh subplan wires this
  knob into its controller-local round-robin target selector

### 2. Add synchronized bounded warm-lease state to VIP selection

Modify [vip_routing.py](../../../../source/sdn_controller/vip_routing.py).

Recommended state:

```python
self._warm_lock = threading.Lock()
self._warm_server_leases: dict[str, WarmLease] = {}
self._warm_storage_leases: dict[str, dict[str, WarmLease]] = {
    "n1": {},
    "n2": {},
}
```

Recommended data structure:

```python
@dataclass
class WarmLease:
    started_ts: float
    expires_ts: float
    remaining_selections: int
```

Recommended helper:

```python
def _claim_warm_backend(self, leases: dict[str, WarmLease], pool: dict[str, dict]) -> dict | None:
    now = time.monotonic()
    with self._warm_lock:
        stale = [
            mac
            for mac, lease in leases.items()
            if lease.expires_ts <= now or lease.remaining_selections <= 0
        ]
        for mac in stale:
            leases.pop(mac, None)

        candidates = [
            (mac, lease)
            for mac, lease in leases.items()
            if mac in pool and mac in self._mac_to_ip
        ]
        if not candidates:
            return None

        mac, lease = min(candidates, key=lambda item: item[1].started_ts)
        lease.remaining_selections -= 1
        if lease.remaining_selections <= 0:
            leases.pop(mac, None)
        return pool[mac]
```

Selection order becomes:

1. try a claimable warm lease
2. if none is claimable, run the current WSM selector unchanged

Key behavior:

- use `time.monotonic()` for expiry
- prune only expired or depleted leases as stale
- intersect the remaining leases with the concrete VIP pool and known IP map
- if nothing is claimable yet, fall back to WSM without deleting the lease

Recommended lease-creation helpers:

```python
def mark_server_backend_warm(self, mac: str) -> None:
    now = time.monotonic()
    with self._warm_lock:
        self._warm_server_leases[mac] = WarmLease(
            started_ts=now,
            expires_ts=now + VIP_WARM_SERVER_SECONDS,
            remaining_selections=VIP_WARM_SERVER_SELECTIONS,
        )


def mark_storage_backend_warm(self, mac: str, domain: str) -> None:
    now = time.monotonic()
    with self._warm_lock:
        self._warm_storage_leases[domain][mac] = WarmLease(
            started_ts=now,
            expires_ts=now + VIP_WARM_STORAGE_SECONDS,
            remaining_selections=VIP_WARM_STORAGE_SELECTIONS,
        )
```

What these helpers achieve:

- give both the compute admission path and the Thread 2 storage promotion path
  one concrete shared API for creating leases
- keep lease creation local to `VipRoutingMixin`, alongside lease claiming and
  pruning
- make repeated promotion/admission simple: marking the same MAC warm again
  just replaces the previous lease with a fresh bounded one

Why pool absence is not stale:

- `add_server_mac()` and `add_storage_mac()` update membership sets first
- concrete VIP pools can lag that update until the topology worker rebuilds
- absence from the concrete pool therefore means "not claimable yet", not
  "invalid forever"

### 3. Register warm compute backends when they enter VIP_SERVER

Modify [elasticity.py](../../../../source/sdn_controller/elasticity/elasticity.py)
and [vip_routing.py](../../../../source/sdn_controller/vip_routing.py).

Today Thread 3 adds the new compute MAC to the server pool and seeds its IP.
Replace that scattered sequence with one controller-side helper that performs
all three actions together.

Recommended helper:

```python
def register_new_server_backend(self, mac: str, ip: str) -> None:
    self.add_server_mac(mac)
    self.register_backend_ip(mac, ip)
    self.mark_server_backend_warm(mac)
```

What this achieves:

- turns compute backend registration into one controller-side operation instead
  of three loosely related calls
- keeps compute admission on the current Thread 3 path so the backend becomes
  VIP-eligible immediately
- creates the warm lease at the same moment the backend becomes usable through
  the shared `mark_server_backend_warm()` helper defined above

### 4. Keep VIP_SERVER strictly natural-move only in this phase

Modify [vip_routing.py](../../../../source/sdn_controller/vip_routing.py)
only to add the compute warm lease, not a new cutover mechanism.

Explicit non-actions for this phase:

- do not delete active VIP_SERVER affinities
- do not install more specific high-priority flow rules for new HTTP
  connections
- do not add soft-close or drain-like compute rebalance

Because compute movement is passive, the compute warm lease should be longer
than storage and at least longer than the current `VIP_HARD_TIMEOUT`, so the
new backend remains eligible for natural new connections and expired affinities
long enough to collect real traffic and telemetry.

---

## File Map

- [scaling_config.py](../../../../source/sdn_controller/scaling_config.py)
  Add storage/compute warm-start config knobs and the bounded refresh fan-out
  limit used by the storage refresh subplan.
- [vip_routing.py](../../../../source/sdn_controller/vip_routing.py)
  Add synchronized warm-lease state, helper methods, and warm-first selection
  that tolerates temporary pool-visibility lag.
- [elasticity.py](../../../../source/sdn_controller/elasticity/elasticity.py)
  Register the compute warm lease on the existing Thread 3 admission path when
  a dynamic compute backend becomes VIP-eligible.

---

## Dependencies

- No new external packages.
- This subplan provides the warm-lease helpers used by
  [vip_data_thread2_refresh_plan.md](./vip_data_thread2_refresh_plan.md).

---

## Verification

1. **Compute warm selection**
   Add a dynamic compute node and confirm the controller creates a compute warm
   lease immediately, existing HTTP connections remain pinned, and only natural
   new HTTP connections or natural VIP flow expiry can land on the warm
   backend.

2. **Storage warm selection**
   After the storage refresh subplan triggers a future `VIP_DATA` reconnect,
   confirm the next `VIP_DATA` packet-in can consume the warm storage lease
   before WSM-only routing resumes.

3. **Warm expiry**
   Confirm both `VIP_SERVER` and `VIP_DATA` warm leases expire cleanly by time
   or token budget and return to steady-state WSM behavior.

---

## Documentation Updates

- [vip_routing_overview.md](../vip_routing_overview.md)
  Add a warm-lease subsection and describe the compute/storage warm-selection
  behavior.
- [elasticity_overview.md](../../elasticy_manager/elasticity_overview.md)
  Note that compute admission into `VIP_SERVER` now creates a compute warm
  lease.
- [system_mechanisms.md](../../system_mechanisms.md)
  Document bounded warm preference and the synchronized warm-lease state.
