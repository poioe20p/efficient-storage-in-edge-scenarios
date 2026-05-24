# Phase 2 - Recovery-Only Different-Backend Selection

**Goal:** when a recovery-VIP selection happens for an edge server and domain,
avoid the most recently remembered normal `VIP_DATA` backend for that same
`(edge_server_mac, domain)` if another candidate exists.

This is the first phase that changes selector behavior.

## 1. Why This Phase Exists

Phase 1 only gave the controller the last normal backend. This phase turns that
memory into actual routing behavior.

Concrete controller boundary:

- the controller does not know request IDs or per-request backend history
- the controller only sees an edge server source MAC hitting either normal
  `VIP_DATA_*` or recovery `VIP_DATA_RECOVERY_*`
- the controller can therefore only help when the edge actually emits a
  recovery-VIP selection
- when that recovery selection happens, the only controller-local attribution
  available is the most recently remembered normal backend for that
  `(edge_server_mac, domain)`

The boundary stays narrow:

1. consult remembered state only for `VIP_DATA_RECOVERY`
2. avoid only the most recently remembered normal backend for that
   `(edge_server_mac, domain)`
3. do not add controller-side request semantics
4. do not try to solve repeated recovery-to-recovery hopping

## 2. File Map

- [source/sdn_controller/vip_routing.py](../../../../../../source/sdn_controller/vip_routing.py)

## 3. Selector Shape

Recommended signature change in
[vip_routing.py](../../../../../../source/sdn_controller/vip_routing.py):

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

Normal steady-state calls continue to use `recovery=False`.

## 4. Filter Helper

Recommended helper:

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

Concrete meaning of `previous_normal_mac` in this phase:

- it is the most recently remembered normal `VIP_DATA` choice for that edge
  server and domain
- it is not a proof of which backend the currently failing request last used
- this phase intentionally accepts that controller-local granularity because
  request-local retry semantics remain in `app.py`

This phase intentionally does **not** introduce:

- a dedicated avoidance-event path
- controller-side retry counters
- controller-side request budget
- separate remembered recovery-backend state

The current code in
[app.py](../../../../../../source/docker/edge_server/source/app.py) already
decides whether the request gets another attempt at all. The controller only
answers the next VIP selection that the edge actually produces.

## 5. Recovery-VIP Call Site

Recommended integration:

```python
storage = self.select_storage(domain, src_mac, recovery=recovery)
```

In the current controller baseline, that change belongs in `_handle_vip_data(...)`,
where recovery VIP traffic is already distinguished by the `recovery` boolean
before DNAT/SNAT installation. In concrete terms, `recovery=True` is the only
signal that this phase should activate. Normal `VIP_DATA_*` traffic must never
apply this filter.

Normal `VIP_DATA` selection stays unchanged:

```python
storage = self.select_storage(domain, src_mac)
```

## 6. Concrete Request Scenarios

In this plan, a request is only "asking for a different backend" in controller
terms when the edge emits a connection attempt toward `VIP_DATA_RECOVERY_*`.
That yields the following concrete cases:

1. **Current normal epoch fails and the edge rotates to recovery.**
   The next selection targets `VIP_DATA_RECOVERY_*`. The controller can help
   here by excluding the most recently remembered normal backend for that
   `(edge_server_mac, domain)` if another candidate exists.
2. **The request failed on a stale epoch, but the shared current epoch already
   changed.**
   The request adopts whatever epoch is already current in `app.py`. If that
   adopted epoch is recovery, the next selection still targets
   `VIP_DATA_RECOVERY_*`, so the controller can help in exactly the same
   recovery-only way.
3. **The request first binds while the shared current epoch is already
   recovery.**
   The request does not perform a normal-to-recovery transition itself, but it
   still targets `VIP_DATA_RECOVERY_*`. If the controller has a remembered
   normal backend for that `(edge_server_mac, domain)`, it can still avoid it.
4. **The authoritative current recovery epoch fails.**
   This is terminal in `app.py`. The controller cannot help because the edge
   should not keep asking the controller for further backend hopping on that
   request.
5. **The request stays on normal `VIP_DATA_*`.**
   The controller cannot help here because this phase does not change normal
   selection behavior. Normal traffic only refreshes the remembered normal
   backend.

So the practical boundary is explicit: the controller can help only on
recovery-VIP selections, and the main normal-to-recovery case is only one of
the recovery-entry paths that reach this logic.

## 7. Verification

1. After normal `VIP_DATA` chooses backend `S2`, the next recovery selection
   for the same `(edge_server_mac, domain)` avoids `S2` when another candidate
   exists.
2. Recovery filtering leaves normal steady-state `VIP_DATA` unchanged.
3. If excluding the remembered normal backend would empty the pool, the
   selector falls back safely to the full pool.
