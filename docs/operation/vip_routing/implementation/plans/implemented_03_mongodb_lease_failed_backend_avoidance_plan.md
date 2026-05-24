# MongoDB Lease Failed-Backend Avoidance Plan

**Status:** Implemented baseline retained for implementation history

Reference:
[01_mongodb_lease_warm_start_and_recovery_path_plan.md](./01_mongodb_lease_warm_start_and_recovery_path_plan.md)

Depends on:

- [implemented_02_mongodb_lease_request_state_machine_plan.md](./implemented_02_mongodb_lease_request_state_machine_plan.md)
- [vip_data_recovery_epoch_model.md](../vip_data_recovery_epoch_model.md)

## Objective

Document the controller-local, recovery-only "avoid last normal backend"
behavior that landed as the controller-side follow-up to the request lease
state machine.

The controller state is intentionally keyed only by `(edge_server_mac, domain)`
because that is the selector boundary already used by
`select_storage(domain, client_mac)` in
[vip_routing.py](../../../../../source/sdn_controller/vip_routing.py).
The controller remembers which backend it most recently chose for normal
`VIP_DATA`, then uses that memory only when the same edge server later reaches
`VIP_DATA_RECOVERY` for the same domain.

This plan solves one reasonable case and explicitly avoids over-claiming:

- if traffic that previously used normal `VIP_DATA` later arrives on
  `VIP_DATA_RECOVERY`, the controller should purposefully avoid reselecting the
  backend it previously chose for normal routing when another candidate exists
- the controller does not model request budget, request identity, or repeated
  recovery-to-recovery retry semantics
- when the current recovery epoch itself fails, the outcome remains request
  terminality owned by the edge request-lease model in
  [app.py](../../../../../source/docker/edge_server/source/app.py)

This plan made sense because experiments showed repeated reselection of the
same backend after the request-lease model landed.

## Implemented Baseline

- [vip_routing.py](../../../../../source/sdn_controller/vip_routing.py)
  already has warm-first storage selection, a dedicated recovery-VIP path,
  controller-local last-normal attribution keyed by `(edge_server_mac,
  domain)`, recovery-only filtering that avoids the remembered normal backend
  when another candidate exists, local-unregister cleanup that forgets
  remembered entries pointing at removed backends, and the `_warm_lock` /
  `unregister_storage_backend(...)` hooks needed to keep selector state
  synchronized while peer disappearance stays safe through pool-membership
  fallback.
- [app.py](../../../../../source/docker/edge_server/source/app.py) already has
  the request-scoped lease model that distinguishes:
  normal-to-recovery transition, stale-epoch adoption of already-current
  state, and terminal failure when the authoritative current recovery epoch
  fails.
- The umbrella lease plan in
  [01_mongodb_lease_warm_start_and_recovery_path_plan.md](./01_mongodb_lease_warm_start_and_recovery_path_plan.md)
  already treats warm leases and recovery-VIP plumbing as implemented context.

This plan does not reopen those pieces. Phases 1-3 now form the current
controller baseline for the avoidance behavior described here.

Current baseline behavior is summarized in:

- [../../vip_routing_overview.md](../../vip_routing_overview.md)
- [../../../system_mechanisms.md](../../../system_mechanisms.md)
- [../vip_data_recovery_epoch_model.md](../vip_data_recovery_epoch_model.md)

Use those overview documents as the primary reference for landed behavior.
This plan file and the folder below are kept mainly as the phased
implementation record for the landed avoidance work.

## Detailed Phased Subplans

The phased implementation breakdown for this plan now lives in:

- [README.md](./implemented_03_mongodb_lease_failed_backend_avoidance/README.md)
- [Phase 1 - Controller-Local Last-Normal Attribution](./implemented_03_mongodb_lease_failed_backend_avoidance/phase_1_terminal_failure_event_contract.md)
- [Phase 2 - Recovery-Only Different-Backend Selection](./implemented_03_mongodb_lease_failed_backend_avoidance/phase_2_controller_avoidance_state_and_last_choice.md)
- [Phase 3 - Cleanup, Boundaries, and Reasonable Outcomes](./implemented_03_mongodb_lease_failed_backend_avoidance/phase_3_recovery_only_selector_filtering.md)

This umbrella file stays as the design summary. The folder above carries the
retained phase-by-phase implementation notes.

## Approved Decisions

- Key the controller memory by `(edge_server_mac, domain)` because that is the
  routing identity already used for storage selection.
- Remember only the most recent normal `VIP_DATA` backend. Recovery selections
  must not overwrite that memory.
- Apply the filter only when handling `VIP_DATA_RECOVERY`, not during normal
  steady-state `VIP_DATA` selection.
- If excluding the remembered normal backend would empty the pool, fall back to
  the full pool instead of dropping traffic.
- Preserve the existing warm-first then WSM selector order; recovery filtering
  only changes the input pool.
- Do not introduce controller-side request budget, request IDs, event-driven
  failure attribution, retry counters, or separate recovery-backend memory.
- If a request first binds while the current shared epoch is already recovery,
  the controller may still avoid the remembered normal backend if it has one.
- If the authoritative current recovery epoch fails, the request remains
  terminal by the current edge semantics. This plan does not ask the
  controller to find a third backend for that same request.
- If a failed epoch is stale and the edge adopts whatever epoch is already
  current, the controller simply answers whichever VIP the edge targets next.
- Removed local storage backends should clear any remembered normal-attribution
  state that still points at them, while remembered peer backends remain safe
  through pool-membership fallback if they disappear from topology.
- This phase is storage-specific. Compute warm-start and compute routing remain
  unchanged.

## Implementation Steps

### 1. Record the most recent normal storage choice per edge server and domain

Modify [vip_routing.py](../../../../../source/sdn_controller/vip_routing.py).

Recommended controller-local memory:

```python
self._last_normal_storage_choice: dict[tuple[str, str], str] = {}
```

Recommended helper:

```python
def _remember_normal_storage_choice(
    self,
    client_mac: str,
    domain: str,
    backend_mac: str,
) -> None:
    with self._warm_lock:
        self._last_normal_storage_choice[(client_mac, domain)] = backend_mac
```

Recommended update points inside `select_storage(...)` for normal routing only:

```python
if warm is not None:
    if not recovery:
        self._remember_normal_storage_choice(client_mac, domain, warm["mac"])
    return warm
```

and:

```python
chosen = tied[rr_idx % len(tied)]
if not recovery:
    self._remember_normal_storage_choice(client_mac, domain, chosen["mac"])
return chosen
```

What this achieves:

- records which backend the controller most recently assigned for normal
  `VIP_DATA`
- keeps the selector key aligned to `(edge_server_mac, domain)`
- avoids corrupting the remembered normal backend with recovery-path choices

### 2. Filter recovery selection against the remembered normal backend

Modify [vip_routing.py](../../../../../source/sdn_controller/vip_routing.py).

Recommended selector shape:

```python
def select_storage(
    self,
    domain: str,
    client_mac: str,
    *,
    recovery: bool = False,
) -> dict | None:
    pool = self.vip_storage_pool_n1 if domain == "n1" else self.vip_storage_pool_n2
    if recovery:
        pool = self._filter_previous_normal_backend(domain, client_mac, pool)

    warm = self._claim_warm_backend(
        f"vip_data({domain})",
        self._warm_storage_leases.setdefault(domain, {}),
        pool,
    )
    ...
```

Recommended filter helper:

```python
def _filter_previous_normal_backend(
    self,
    domain: str,
    client_mac: str,
    pool: dict[str, dict],
) -> dict[str, dict]:
    key = (client_mac, domain)
    with self._warm_lock:
        previous_normal_mac = self._last_normal_storage_choice.get(key)

    if previous_normal_mac is None or previous_normal_mac not in pool:
        return pool

    filtered = {
        mac: entry
        for mac, entry in pool.items()
        if mac != previous_normal_mac
    }
    return filtered or pool
```

Call-site adjustment inside `_handle_vip_data(...)`:

```python
storage = self.select_storage(domain, src_mac, recovery=recovery)
```

In the current controller baseline, that recovery-path call-site change belongs
in `_handle_vip_data(...)`, where recovery VIP traffic is already distinguished
by the `recovery` boolean before DNAT/SNAT rule installation.

What this achieves:

- makes the controller deliberately choose a different backend when traffic
  moves from normal `VIP_DATA` to `VIP_DATA_RECOVERY` and another candidate
  exists
- lets requests that first bind while the shared current epoch is already
  recovery still avoid the previous normal backend when that memory exists
- keeps normal steady-state placement unchanged

### 3. Clear stale attribution and document the explicit controller boundary

Modify [vip_routing.py](../../../../../source/sdn_controller/vip_routing.py).

Recommended cleanup helper:

```python
def _forget_normal_storage_choice(self, backend_mac: str, domain: str) -> None:
    with self._warm_lock:
        stale_keys = [
            key
            for key, remembered_mac in self._last_normal_storage_choice.items()
            if key[1] == domain and remembered_mac == backend_mac
        ]
        for key in stale_keys:
            self._last_normal_storage_choice.pop(key, None)
```

Recommended backend-unregister integration:

```python
def unregister_storage_backend(self, mac: str, domain: str) -> None:
    self.remove_storage_mac(mac, domain)
    self.clear_storage_backend_warm(mac, domain)
    self._forget_normal_storage_choice(mac, domain)
```

This phase also makes the non-goals explicit in the implementation notes and
verification plan:

- current recovery failure remains request-terminal and is not a controller
  retry problem
- the controller does not infer request history beyond the last normal backend
- if the edge adopts a different already-current epoch after a stale failure,
  the controller simply handles the next targeted VIP

What this achieves:

- keeps controller-local attribution aligned with backend lifecycle changes
- prevents the 03 plan from over-promising outcomes that the current request
  model in [app.py](../../../../../source/docker/edge_server/source/app.py)
  does not support

## File Map

- [vip_routing.py](../../../../../source/sdn_controller/vip_routing.py)
  remember the last normal storage choice, filter recovery selection against
  it, and clear stale remembered entries when storage backends are removed.

## Dependencies

- Phase 1 and Phase 2 of
  [implemented_02_mongodb_lease_request_state_machine_plan.md](./implemented_02_mongodb_lease_request_state_machine_plan.md)
  should already exist so the runtime can distinguish normal placement from
  bounded request-level rebinding and terminal request-owned lease failure.
- The implemented warm/recovery baseline described in
  [01_mongodb_lease_warm_start_and_recovery_path_plan.md](./01_mongodb_lease_warm_start_and_recovery_path_plan.md)
  should remain unchanged while this phase layers a recovery-only filter on top
  of the existing storage selector.
- No new external packages.

## Verification

Validate this phase experimentally only if repeated reselection still appears.
After normal `VIP_DATA` for a given `(edge_server_mac, domain)` selects backend
`S2`, the next `VIP_DATA_RECOVERY` selection for that same key should avoid
`S2` whenever an alternative candidate exists.

Also confirm that:

- normal steady-state `VIP_DATA` selection still records and updates the last
  normal backend without otherwise changing behavior
- requests that first bind while the shared current epoch is already recovery
  still consult the remembered normal backend if one exists
- failure on the authoritative current recovery epoch remains terminal and does
  not require extra controller-side failover behavior
- stale failed epochs that adopt already-current state simply follow whichever
  VIP the edge targets next
- single-backend pools still fall back safely instead of dropping traffic

## Documentation Updates

- [system_mechanisms.md](../../../system_mechanisms.md)
  document the optional recovery-only avoid-last-normal behavior only if this
  phase is actually implemented.
- [vip_routing_overview.md](../../vip_routing_overview.md)
  document that avoidance, when enabled, is a controller-local recovery-only
  filter keyed by `(edge_server_mac, domain)`.
- [vip_data_recovery_epoch_model.md](../vip_data_recovery_epoch_model.md)
  clarify that controller-side avoidance does not change the request-owned
  terminal behavior of the current recovery epoch.
