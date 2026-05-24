# Phase 3 - Cleanup, Boundaries, and Reasonable Outcomes

**Goal:** keep the remembered normal-backend state aligned with local backend
lifecycle changes where the controller has an explicit removal hook, document
safe fallback behavior when a remembered peer backend disappears from the pool,
and make the controller boundary explicit so the 03 plan does not promise
outcomes the current request-lease model cannot support.

## 1. Why This Phase Exists

Phases 1 and 2 introduce a useful but intentionally narrow controller-local
behavior. Without explicit cleanup and boundary notes, the plan can easily drift
back into an unreasonable goal such as "the controller should keep finding new
backends for the same request after current recovery fails."

The current request-lease code in
[app.py](../../../../../../source/docker/edge_server/source/app.py) already
defines the real boundary:

- current normal can rotate to recovery once only while the request remains
    replay-safe
- stale failed epoch can adopt whatever epoch is already current
- authoritative current recovery failure is terminal for the request

This phase keeps the controller plan aligned with those semantics.

## 2. File Map

- [source/sdn_controller/vip_routing.py](../../../../../../source/sdn_controller/vip_routing.py)

## 3. Cleanup Hook

The controller already has a real lifecycle hook for local storage removal:
`unregister_storage_backend(...)` in
[vip_routing.py](../../../../../../source/sdn_controller/vip_routing.py).

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

Recommended integration:

```python
def unregister_storage_backend(self, mac: str, domain: str) -> None:
    self.remove_storage_mac(mac, domain)
    self.clear_storage_backend_warm(mac, domain)
    self._forget_normal_storage_choice(mac, domain)
```

Even without cleanup, filtering already falls back safely when the remembered
backend is not in the current pool. The cleanup hook is still valuable because
it keeps the controller-local attribution small and semantically current.

This cleanup hook should be described narrowly. It covers local removals that
already flow through `unregister_storage_backend(...)`. Peer-LAN disappearance
arrives through topology updates instead. That case is still selector-safe
because recovery filtering falls back when the remembered backend is no longer
in the current pool, but this phase should not claim an active forget path for
peer disappearance unless it adds one explicitly.

## 4. Reasonable Outcomes Table

| Scenario | Edge behavior from [app.py](../../../../../../source/docker/edge_server/source/app.py) | Controller responsibility | Outcome |
| --- | --- | --- | --- |
| Request fails on current normal epoch | If the request is still replay-safe, the edge can rotate to recovery once; otherwise the request becomes terminal | If the edge reaches recovery selection, avoid the remembered normal backend if another candidate exists | Replay-safe requests choose a different backend when possible; non-replay-safe requests do not trigger extra controller-side hopping |
| Request first binds while shared current epoch is already recovery | Request is already on recovery-mode state | Still consult the remembered normal backend if one exists | Recovery selection avoids the old normal backend when possible |
| Request fails on authoritative current recovery epoch | Request becomes terminal | None | No extra controller-side backend hopping |
| Failed epoch is stale and current already changed | Request adopts whatever epoch is already current | Answer whichever VIP the edge targets next | Selection follows current normal or current recovery state |
| Only one storage backend is in the pool | Edge may still target recovery VIP | Fall back to the full pool | No drop caused by the recovery filter |

## 5. Non-Goals

This plan does not attempt to solve any of the following:

- infer request history more precisely than the last normal backend choice
- remember per-request identities in the controller
- model request rebind budget in the controller
- create repeated recovery-to-recovery backend hopping after authoritative
  current recovery failure

If those behaviors are ever desired, they would require a new edge request-
lease design first, not just a controller-side selector tweak.

## 6. Verification

1. Removing a local storage backend through
    `unregister_storage_backend(...)` clears remembered normal-attribution
    entries that still point at it.
2. If a remembered peer backend disappears from the current pool, recovery
    filtering remains safe through pool-membership fallback even though this
    phase does not yet add an active forget path for peer disappearance.
3. Requests that start while current is already recovery still use the last
   remembered normal backend if available.
4. Failure on authoritative current recovery remains terminal and does not rely
   on extra controller behavior.
5. The written plan and verification scenarios stay aligned with the actual
   edge semantics in [app.py](../../../../../../source/docker/edge_server/source/app.py).
