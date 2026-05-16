# VIP Warm Leases Plan

Reference: [vip_warm_start_and_vip_data_refresh_plan.md](./vip_warm_start_and_vip_data_refresh_plan.md)

## Objective

Add bounded warm-start preference for newly VIP-eligible compute and storage
backends without changing steady-state WSM routing or forcing live compute
connection cutover. For storage, the lease is consumed by the next eligible
fresh selection opportunity that occurs while the lease is still claimable.
Once the later recovery-VIP phases land, that is commonly the earliest
`VIP_DATA_RECOVERY_*` reconnect after a main-path connection failure, but this
subplan only needs to preserve a bounded controller-side preference window.

This is the controller-local Phase 1 subplan. It should stand on its own even
before the later recovery-VIP work exists, and later phases can consume any
remaining storage warm-lease window by creating additional fresh selection
opportunities.

## Approved Decisions

- Use bounded warm leases with monotonic time limits only; do not use a
  per-selection budget.
- Because dynamic backend identities are allocator-recycled, explicit backend
  removal must invalidate any warm lease for that identity. Later admission
  should still overwrite lease state as an idempotent safety net before the
  backend becomes claimable.
- Keep warm-lease state in `VipRoutingMixin`, guarded by a small
  `threading.Lock`, because compute admission still comes from native Thread 3.
- `scaling_config.py` is the source of truth for warm-start timing knobs.
  Once Phase 1 lands, `vip_routing.py` should import those constants instead
  of parsing duplicate warm-start env vars locally.
- Treat "not yet visible in the concrete VIP pool" as temporary
  non-claimability, not stale state.
- Create the compute warm lease as soon as a new compute backend is admitted to
  `VIP_SERVER`.
- Create the storage warm lease when a promoted storage backend becomes
  `SECONDARY` and is admitted into the storage membership set.
- Size the warm windows around the elasticity reaction horizon that produced
  the new node, not around `VIP_HARD_TIMEOUT` or the scale-down windows.
- This Phase 1 subplan does not depend on controller-driven `PUT /vip_data`
  refresh for correctness. Later recovery phases may create one or more fresh
  selection opportunities, and the storage warm lease should remain claimable
  across them until its monotonic expiry.
- Prefer the most recently admitted claimable warm backend first, so repeated
  scale-up under sustained load boosts the newest node rather than the oldest
  still-warm one.
- Keep `VIP_SERVER` natural-move only in this phase. The compute warm window
  should be short enough to return control to WSM once the new node starts
  contributing telemetry.

---

## Implementation Steps

### 1. Simplify the existing warm-start configuration to time-only knobs

Reuse [scaling_config.py](../../../../source/sdn_controller/scaling_config.py)
as the source of truth for warm-start controls, but collapse Phase 1 to two
time-only knobs. The existing per-selection budget knobs should be removed or
left unused once the time-only implementation lands.

This consolidation is specific to warm-start timing. `vip_routing.py` may keep
direct ownership of routing-local WSM weights and generic VIP rule timeout
knobs until a later cleanup phase, but it should stop being an independent
source of truth for warm-start timing once Phase 1 is implemented.

Target knobs:

- `VIP_WARM_STORAGE_SECONDS`
- `VIP_WARM_SERVER_SECONDS`
  Suggested defaults direction:
- Storage warm window: short, around one storage scale-up reaction horizon or
  promotion-availability interval, not around `VIP_HARD_TIMEOUT`.
- Compute warm window: short, around one compute scale-up reaction horizon, so
  a newly added backend picks up traffic quickly during sustained load without
  bypassing WSM for the full VIP flow lifetime.

Example shape:

```python
# With the current 10 s telemetry windows, start with one short control-loop
# reaction horizon rather than the 120 s VIP hard timeout.
VIP_WARM_STORAGE_SECONDS = float(os.environ.get("VIP_WARM_STORAGE_SECONDS", "30"))
VIP_WARM_SERVER_SECONDS = float(os.environ.get("VIP_WARM_SERVER_SECONDS", "45"))
```

What this achieves:

- bounds the warm period in time so a backend cannot stay preferred forever
- aligns warm preference with the elasticity control loop that just added the
  node
- lets new nodes absorb traffic quickly during sustained load
- returns selection to steady-state WSM soon enough to avoid prolonged
  hotspotting on a just-added backend

### 2. Add synchronized bounded warm-lease state to VIP selection

Modify [vip_routing.py](../../../../source/sdn_controller/vip_routing.py).

Expected starting point for this step:

- [main_n1.py](../../../../source/sdn_controller/main_n1.py) and
  [main_n2.py](../../../../source/sdn_controller/main_n2.py) already call
  `mark_storage_backend_warm(mac, domain)` from the promotion path.
- [scaling_config.py](../../../../source/sdn_controller/scaling_config.py)
  already exposes warm-start env knobs; Phase 1 should retain only the
  time-based controls.
- The missing work is the controller-side warm-lease implementation inside
  `VipRoutingMixin`.

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
```

Recommended helper:

```python
def _claim_warm_backend(self, leases: dict[str, WarmLease], pool: dict[str, dict]) -> dict | None:
    now = time.monotonic()
    with self._warm_lock:
        stale = [
            mac
            for mac, lease in leases.items()
      if lease.expires_ts <= now
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

        mac, _ = max(candidates, key=lambda item: item[1].started_ts)
        return pool[mac]
```

Selection order becomes:

1. try a claimable warm lease
2. if none is claimable, run the current WSM selector unchanged

Key behavior:

- use `time.monotonic()` for expiry
- prune only expired leases as stale
- intersect the remaining leases with the concrete VIP pool and known IP map
- if nothing is claimable yet, fall back to WSM without deleting the lease
- while the lease remains claimable, warm-first selection wins deterministically
  over steady-state WSM; once the lease expires, WSM resumes
- if multiple warm leases are simultaneously claimable, prefer the newest one
  first so a later scale-up under sustained load boosts the most recently added
  backend

Recommended lease-creation helpers:

```python
def mark_server_backend_warm(self, mac: str) -> None:
    now = time.monotonic()
    with self._warm_lock:
        self._warm_server_leases[mac] = WarmLease(
            started_ts=now,
            expires_ts=now + VIP_WARM_SERVER_SECONDS,
        )


def mark_storage_backend_warm(self, mac: str, domain: str) -> None:
    now = time.monotonic()
    with self._warm_lock:
        self._warm_storage_leases[domain][mac] = WarmLease(
            started_ts=now,
            expires_ts=now + VIP_WARM_STORAGE_SECONDS,
        )
```

Recommended lease-invalidation helpers:

```python
def clear_server_backend_warm(self, mac: str) -> None:
    with self._warm_lock:
        self._warm_server_leases.pop(mac, None)


def clear_storage_backend_warm(self, mac: str, domain: str) -> None:
    with self._warm_lock:
        self._warm_storage_leases[domain].pop(mac, None)
```

What these helpers achieve:

- give both the compute admission path and the Thread 2 storage promotion path
  one concrete shared API for creating leases
- keep lease creation local to `VipRoutingMixin`, alongside lease claiming and
  pruning
- make repeated promotion/admission simple: marking the same MAC warm again
  just replaces the previous lease with a fresh short-lived time window
- keep explicit scale-down and cleanup paths from leaving a stale warm lease on
  a MAC/IP identity that the allocator may later recycle

Why pool absence is not stale:

- `add_server_mac()` and `add_storage_mac()` update membership sets first
- concrete VIP pools can lag that update until the topology worker rebuilds
- absence from the concrete pool therefore means "not claimable yet", not
  "invalid forever"

### 3. Complete warm compute registration when new backends enter VIP_SERVER

Modify [vip_routing.py](../../../../source/sdn_controller/vip_routing.py).

Thread 3 in
[elasticity.py](../../../../source/sdn_controller/elasticity/elasticity.py)
already probes for a controller-side `register_new_server_backend()` helper
and falls back to the older add-and-seed sequence if it is absent. Phase 1
only needs to provide that helper in `VipRoutingMixin` so compute admission
automatically gets warm-lease registration through the existing hook.

Recommended helper:

```python
def register_new_server_backend(self, mac: str, ip: str) -> None:
    self.add_server_mac(mac)
    self.register_backend_ip(mac, ip)
    self.mark_server_backend_warm(mac)
```

What this achieves:

- turns compute backend registration into one controller-side operation instead
  of leaving Thread 3 on the fallback path
- keeps compute admission on the current Thread 3 path so the backend becomes
  VIP-eligible immediately
- creates the warm lease at the same moment the backend becomes usable through
  the shared `mark_server_backend_warm()` helper defined above

### 4. Invalidate warm leases on explicit backend removal

Modify [vip_routing.py](../../../../source/sdn_controller/vip_routing.py)
and [elasticity.py](../../../../source/sdn_controller/elasticity/elasticity.py).

Recommended removal hooks:

```python
def unregister_server_backend(self, mac: str) -> None:
    self.remove_server_mac(mac)
    self.clear_server_backend_warm(mac)


def unregister_storage_backend(self, mac: str, domain: str) -> None:
    self.remove_storage_mac(mac, domain)
    self.clear_storage_backend_warm(mac, domain)
```

Recommended call sites:

- compute scale-down should clear any warm lease when the backend is removed
  from `VIP_SERVER`
- storage scale-down should clear any warm lease when the backend is removed
  from the per-domain `VIP_DATA` pool

Why this matters:

- the allocator releases addresses on successful removal and then reuses the
  lowest free suffix on the next add
- MAC/IP identity is therefore recyclable even if the old warm window has not
  expired yet
- explicit invalidation keeps MAC-only warm-lease keys safe without relying
  solely on later overwrite-on-add behavior

### 5. Keep VIP_SERVER strictly natural-move only in this phase

Modify [vip_routing.py](../../../../source/sdn_controller/vip_routing.py)
only to add the compute warm lease, not a new cutover mechanism.

Explicit non-actions for this phase:

- do not delete active VIP_SERVER affinities
- do not install more specific high-priority flow rules for new HTTP
  connections
- do not add soft-close or drain-like compute rebalance

Because compute movement is passive, the compute warm lease should be longer
than storage only by a small margin and should stay close to one compute
scale-up reaction horizon, not the full `VIP_HARD_TIMEOUT`. The goal is to let
the new backend attract traffic quickly during the post-scale-up period, then
return to WSM once the node has fresh telemetry and can compete normally.

---

## File Map

- [scaling_config.py](../../../../source/sdn_controller/scaling_config.py)
  Collapse warm-start config to `VIP_WARM_STORAGE_SECONDS` and
  `VIP_WARM_SERVER_SECONDS`; retire the per-selection budget knobs and keep
  warm-start timing ownership centralized here.
- [vip_routing.py](../../../../source/sdn_controller/vip_routing.py)
  Add synchronized time-only warm-lease state, helper methods, explicit
  invalidation on removal, and newest-first warm selection that tolerates
  temporary pool-visibility lag.
- [elasticity.py](../../../../source/sdn_controller/elasticity/elasticity.py)
  Already contains the optional `register_new_server_backend()` admission hook
  used by this subplan and should call the new warm-lease invalidation helpers
  on explicit compute and storage removal.

## Focused Checks

1. **Compute warm selection**
   Add a dynamic compute node and confirm the controller creates a compute warm
   lease immediately, existing HTTP connections remain pinned, and only natural
   new HTTP connections or natural VIP flow expiry can land on the warm
   backend.

2. **Lease recycle safety**
   Scale down a backend, confirm its warm lease is cleared when VIP membership
   is removed, then re-add a node that reuses the same allocator identity and
   confirm only the new admission can create a fresh lease for that MAC.

3. **Storage warm selection**
   After the recovery-VIP phase creates a fresh post-failure storage selection
   opportunity, confirm the next eligible packet-in can consume the warm
   storage lease before WSM-only routing resumes.

---

## Dependencies

- No new external packages.
- This subplan provides the warm-lease helpers used by the recovery-VIP phase
  in [vip_warm_start_and_vip_data_refresh_plan.md](./vip_warm_start_and_vip_data_refresh_plan.md).

---

## Verification

Validate this phase experimentally: confirm the controller logs show warm-lease
creation, claim, and expiry for both `VIP_SERVER` and `VIP_DATA`, and confirm
that once the short bounded lease window ends the selector returns to
steady-state WSM behavior. Under repeated scale-up during sustained load, the
most recently admitted warm backend should be the one briefly preferred.

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
