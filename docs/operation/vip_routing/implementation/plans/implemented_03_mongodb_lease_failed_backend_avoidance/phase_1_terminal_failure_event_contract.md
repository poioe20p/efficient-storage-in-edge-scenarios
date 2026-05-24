# Phase 1 - Controller-Local Last-Normal Attribution

**Goal:** give the controller enough local memory to know which backend it
most recently chose for normal `VIP_DATA` for a given edge server and domain.

This phase is about attribution only. It does not yet change selector
behavior.

## 1. Why This Phase Exists

If the controller is expected to choose a different backend on
`VIP_DATA_RECOVERY`, it first needs to remember what it chose during normal
`VIP_DATA` routing. That memory belongs in
[vip_routing.py](../../../../../../source/sdn_controller/vip_routing.py)
because that file already owns storage backend selection and already uses
`client_mac` plus `domain` as the routing identity.

This plan intentionally does not add a new event path. The controller only
needs one local fact for now: the last normal storage choice for a given
`(edge_server_mac, domain)`.

## 2. File Map

- [source/sdn_controller/vip_routing.py](../../../../../../source/sdn_controller/vip_routing.py)

## 3. Selector State

Recommended controller-local memory:

```python
self._last_normal_storage_choice: dict[tuple[str, str], str] = {}
```

Use the existing `_warm_lock` discipline because Thread 1 reads and updates
selector state while Thread 2 and Thread 3 may remove backends and clear stale
entries.

Put a comment in front of the code that explicitly declares what values are to be held in the variable.

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

## 4. Record Only Normal Selections

Recommended `select_storage(...)` shape for later phases:

```python
def select_storage(
    self,
    domain: str,
    client_mac: str,
    *,
    recovery: bool = False,
) -> dict | None:
    ...
```

Warm-claim integration:

```python
warm = self._claim_warm_backend(
    f"vip_data({domain})",
    self._warm_storage_leases.setdefault(domain, {}),
    pool,
)
if warm is not None:
    if not recovery:
        self._remember_normal_storage_choice(client_mac, domain, warm["mac"])
    return warm
```

WSM-selection integration:

```python
chosen = tied[rr_idx % len(tied)]
if not recovery:
    self._remember_normal_storage_choice(client_mac, domain, chosen["mac"])
return chosen
```

The `if not recovery` guard is the important boundary. Recovery choices must
not overwrite the remembered normal backend, because requests that enter while
the shared current epoch is already recovery still need the controller to know
which earlier normal backend should be avoided.

## 5. Why Recovery Choices Do Not Overwrite The Memory

The remembered value is not "last backend of any kind." It is specifically
"last backend chosen for normal `VIP_DATA` for this edge server and domain."

That distinction matters because the current edge request-lease model in
[app.py](../../../../../../source/docker/edge_server/source/app.py) allows:

- a request to move from current normal to recovery
- a stale failed epoch to adopt already-current state
- a request that first binds while the shared current epoch is already recovery

All of those cases still benefit from knowing the last normal backend. None of
them are improved by overwriting that memory with the most recent recovery
backend.

## 6. Verification

1. The controller records the most recent normal storage choice per
   `(edge_server_mac, domain)`.
2. A later normal choice for the same key overwrites the previous remembered
   value.
3. Recovery selections do not overwrite the remembered normal backend.
