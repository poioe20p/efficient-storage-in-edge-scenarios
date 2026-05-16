# VIP_DATA Failed-Backend Avoidance Plan

Reference: [vip_warm_start_and_vip_data_refresh_plan.md](./vip_warm_start_and_vip_data_refresh_plan.md)
Depends on:

- [vip_warm_leases_plan.md](./vip_warm_leases_plan.md)
- [vip_data_recovery_vip_arming_plan.md](./vip_data_recovery_vip_arming_plan.md)
- [vip_data_recovery_flow_session_plan.md](./vip_data_recovery_flow_session_plan.md)

## Objective

Add a short-lived controller-side “avoid last failed backend” memory only if
Phase 1 through Phase 3 still show repeated reselection of the same unhealthy
storage backend after a recovery attempt.

This is the optional Phase 4 subplan. It is intentionally deferred until
experiments prove that bounded warm leases plus bounded recovery reselection are
still not enough.

It assumes Phase 1 already clears warm leases on explicit backend removal, so
this phase only has to reason about currently valid candidate identities that
remain in the storage pool.

## Approved Decisions

- Key the avoidance memory by `(edge_server_mac, domain)` because
  `select_storage(domain, client_mac)` already uses the edge server MAC as the
  client identifier for `VIP_DATA` routing.
- Use a short time limit and a small retry budget, not a permanent blacklist.
- Arm the avoidance entry when a recovery-path selection happens, because that
  recovery attempt is the first controller-visible evidence that the previously
  chosen backend likely failed for that edge server and domain.
- If excluding the avoided backend would empty the candidate pool, fall back to
  the full pool instead of dropping traffic.
- Warm-lease selection should run on the filtered candidate pool, so a newly
  promoted dynamic backend can still win if it is healthy and claimable.
- This phase is storage-specific. Compute warm-start and compute routing remain
  unchanged.
- Removed backends should already have no surviving warm lease state; this
  phase layers avoidance on top of the remaining valid pool, not on top of
  stale recycled identities.

---

## Implementation Steps

### 1. Track the most recent storage choice per edge server and domain

Modify [vip_routing.py](../../../../source/sdn_controller/vip_routing.py).

Recommended state:

```python
self._last_storage_choice: dict[tuple[str, str], str] = {}
```

Recommended update point inside `select_storage(...)`:

```python
chosen = tied[rr_idx % len(tied)]
self._last_storage_choice[(client_mac, domain)] = chosen["mac"]
return chosen
```

What this achieves:

- records which backend the controller most recently assigned to a given edge
  server and owner domain
- gives later recovery selections a concrete backend to avoid briefly

### 2. Add short-lived avoidance leases

Modify [vip_routing.py](../../../../source/sdn_controller/vip_routing.py)
and [osken-controller.env](../../../../source/scripts/osken-controller.env).

Recommended data structure:

```python
@dataclass
class AvoidLease:
    mac: str
    expires_ts: float
    remaining_attempts: int
```

Recommended state and knobs:

```python
self._avoid_failed_storage: dict[tuple[str, str], AvoidLease] = {}

_VIP_DATA_AVOID_FAILED_SECONDS = float(os.environ.get("VIP_DATA_AVOID_FAILED_SECONDS", "20"))
_VIP_DATA_AVOID_FAILED_ATTEMPTS = int(os.environ.get("VIP_DATA_AVOID_FAILED_ATTEMPTS", "2"))
```

Recommended env additions:

```dotenv
VIP_DATA_AVOID_FAILED_SECONDS=20
VIP_DATA_AVOID_FAILED_ATTEMPTS=2
```

What this achieves:

- keeps the avoidance memory small, bounded, and easy to expire
- avoids turning one failure into a long-lived routing bias

### 3. Arm avoidance on the recovery path

Modify [vip_routing.py](../../../../source/sdn_controller/vip_routing.py).

Recommended arming helper:

```python
def _arm_failed_backend_avoidance(self, client_mac: str, domain: str) -> None:
    key = (client_mac, domain)
    failed_mac = self._last_storage_choice.get(key)
    if failed_mac is None:
        return
    now = time.monotonic()
    self._avoid_failed_storage[key] = AvoidLease(
        mac=failed_mac,
        expires_ts=now + _VIP_DATA_AVOID_FAILED_SECONDS,
        remaining_attempts=_VIP_DATA_AVOID_FAILED_ATTEMPTS,
    )
```

Recommended recovery hook:

```python
if recovery:
    self._arm_failed_backend_avoidance(src_mac, domain)
storage = self.select_storage(domain, src_mac)
```

Why this specific timing:

- the recovery PacketIn is the first controller-visible event that tells us the
  previous path likely failed for that edge server and domain
- arming here avoids inventing a separate failure-reporting side channel

### 4. Filter the candidate pool before warm and WSM selection

Modify [vip_routing.py](../../../../source/sdn_controller/vip_routing.py).

Recommended filter helper:

```python
def _filter_avoided_storage_pool(self, domain: str, client_mac: str, pool: dict[str, dict]) -> dict[str, dict]:
    key = (client_mac, domain)
    lease = self._avoid_failed_storage.get(key)
    if lease is None:
        return pool

    now = time.monotonic()
    if lease.expires_ts <= now or lease.remaining_attempts <= 0:
        self._avoid_failed_storage.pop(key, None)
        return pool

    filtered = {mac: entry for mac, entry in pool.items() if mac != lease.mac}
    if not filtered:
        return pool

    lease.remaining_attempts -= 1
    if lease.remaining_attempts <= 0:
        self._avoid_failed_storage.pop(key, None)
    return filtered
```

Recommended selector order:

```python
pool = self.vip_storage_pool_n1 if domain == "n1" else self.vip_storage_pool_n2
pool = self._filter_avoided_storage_pool(domain, client_mac, pool)
warm = self._claim_warm_backend(self._warm_storage_leases[domain], pool)
if warm is not None:
    self._last_storage_choice[(client_mac, domain)] = warm["mac"]
    return warm
```

What this achieves:

- avoids immediate reselection of the same backend when a short-lived recovery
  attempt clearly failed
- still preserves the existing warm-first then WSM selection ordering on the
  filtered pool
- falls back safely to the full pool when the avoided backend is the only
  candidate left
- keeps avoidance focused on current healthy candidates after Phase 1 has
  already removed any stale warm state during explicit backend removal

---

## File Map

- [vip_routing.py](../../../../source/sdn_controller/vip_routing.py)
  Track last storage choice, arm avoidance on recovery PacketIn, and filter the
  candidate pool before warm and WSM selection.
- [osken-controller.env](../../../../source/scripts/osken-controller.env)
  Define optional avoidance-window knobs.

---

## Dependencies

- Phases 1 through 3 should already exist so experiments can prove whether this
  follow-up is actually needed.
- Phase 1 removal-time warm-lease invalidation should already exist so MAC-only
  warm-lease keys are safe before this phase adds a second short-lived filter.
- No new external packages.

---

## Verification

Validate this phase experimentally only if repeated reselection still appears:
after a recovery-triggered failure for a given edge server and domain, the next
bounded recovery selection should avoid the previously chosen backend whenever
an alternative candidate exists, then expire back to normal behavior.

---

## Documentation Updates

- [system_mechanisms.md](../../system_mechanisms.md)
  Document the optional avoid-last-failed behavior only if this phase is
  actually implemented.
