# RQ2 Implementation Plan — Policy-Mode Gating

**Status**: ✅ Implemented · **Date**: 2026-07-05
**RQ doc**: [`docs/research_questions/rq2.md`](../../research_questions/rq2.md)
**Thesis map**: [`tese/miscelineous/system_to_thesis_map_rq_v2.md`](../../../tese/miscelineous/system_to_thesis_map_rq_v2.md)

---

## Intent

Implement three backend-selection policy modes controlled by a single env var
(`BACKEND_SELECTION_POLICY`). The modes differ only in **when the routing plane
becomes aware of a new backend** and **how traffic ramps onto it**.

| Mode | Pre-discovery (stats unknown) | Ramp-up |
|---|---|---|
| `topology_host` | Best-case (0.0) → instant cold-start herd | None |
| `topology_slowstart` | Neutral (0.0) + flat penalty (1.0) → effectively invisible until discovery | Graduated penalty 1.0→0.0 over WARM TTL, starting at discovery |
| `topology_lifecycle` | Warm lease at spawn (current behavior — unchanged) | Bounded priority window |

All other parameters (WSM weights, host-load dimensions, pool structure,
telemetry delivery) are identical across modes.

---

## File Map

```
source/sdn_controller/_vip_routing/
├── config.py          ← Add _BACKEND_SELECTION_POLICY
├── state.py           ← Add discovery tracking + cleanup
└── selection.py       ← Add policy gating, slowstart penalty, unknown-stats override

source/scripts/testing/controller_env_overrides/
├── rq2_topology_host.env      ← NEW
└── rq2_topology_slowstart.env ← NEW
```

---

## Step-by-Step Changes

### Step 1: `config.py` — Policy mode env var

**File**: `source/sdn_controller/_vip_routing/config.py`
**After the `WarmLease` dataclass**, before the WSM weight declarations:

```python
# --- Backend-selection policy mode (RQ2) ---
_BACKEND_SELECTION_POLICY = os.environ.get(
    "BACKEND_SELECTION_POLICY", "topology_lifecycle"
)
# Valid: topology_host | topology_slowstart | topology_lifecycle
```

Add `_BACKEND_SELECTION_POLICY` to the import in `selection.py` (see Step 4).

---

### Step 2: `state.py` — Discovery tracking

**File**: `source/sdn_controller/_vip_routing/state.py`

**2a. Add discovery dict in `init_vip_routing_state()`** — after the `_warm_storage_leases` dict closing `}`:

```python
    # Per-backend discovery timestamps for slow-start ramp (RQ2).
    # Keyed by MAC; populated when a backend first appears in telemetry.
    controller._backend_discovery_ts: dict[str, float] = {}  # mac -> first_telemetry_ts
```

**2b. Record discovery in `update_server_stats()`** — inside the `for mac, summary` loop, after the `controller._server_stats[mac] = summary` assignment:

```python
        if mac not in controller._backend_discovery_ts:
            controller._backend_discovery_ts[mac] = time.monotonic()
```

**2c. Record discovery in `update_storage_stats()`** — same pattern, inside the `for mac, summary` loop, after the `controller._storage_stats[mac] = summary` assignment:

```python
        if mac not in controller._backend_discovery_ts:
            controller._backend_discovery_ts[mac] = time.monotonic()
```

**2d. Cleanup in `unregister_server_backend()`** — after `clear_server_backend_warm(controller, mac)`:

```python
    controller._backend_discovery_ts.pop(mac, None)
```

**2e. Cleanup in `unregister_storage_backend()`** — after `clear_storage_backend_warm(controller, mac, domain)`:

```python
    controller._backend_discovery_ts.pop(mac, None)
```

---

### Step 3: `selection.py` — Import additions

**File**: `source/sdn_controller/_vip_routing/selection.py`

**Replace the existing import block** at the top of the file:

```python
from .config import (
    _W_CPU, _W_RAM, _W_REQUESTS, _W_HOPS,
    _W_STORAGE_CPU, _W_STORAGE_RAM, _W_STORAGE_CONNECTIONS,
    _W_STORAGE_LAG, _W_STORAGE_HOPS,
    _BACKEND_SELECTION_POLICY,
    logger,
)
from ..scaling_config import _VIP_WARM_SERVER_SECONDS, _VIP_WARM_STORAGE_SECONDS
```

---

### Step 4: `selection.py` — Helper functions

**After the import block**, before `_claim_warm_backend`:

```python
def _unknown_stats_default():
    """Return the unknown-stats normalised value for the current policy mode.

    topology_host:      0.0 (best-case  → cold-start herd)
    topology_slowstart: 0.0 (neutral    → penalty handles all deterrence)
    topology_lifecycle: 1.0 (worst-case → warm lease short-circuits WSM anyway;
                          also protects against preferring unmeasured peer backends)
    """
    if _BACKEND_SELECTION_POLICY == "topology_host":
        return 0.0
    if _BACKEND_SELECTION_POLICY == "topology_slowstart":
        return 0.0     # neutral — penalty owns all deterrence
    return 1.0          # topology_lifecycle (default)


def _slowstart_penalty(controller, mac: str, ttl_s: float) -> float:
    """Graduated cost penalty for discovery-time slow-start ramp (RQ2).

    Before discovery: returns 1.0 — the backend is worst-case, effectively
    invisible in practice (will only win traffic via round-robin tie-breaking
    if all other backends are equally penalised).

    After discovery: linear decay from 1.0 at discovery time to 0.0 at
    discovery_time + ttl_s.

    Returns 0.0 if the policy mode is not topology_slowstart, or if the
    ramp period has elapsed.

    Design note — penalty magnitude: the unweighted penalty (range 0–1)
    exceeds the maximum weighted WSM cost sum (0.88 for compute,
    0.90 for storage). This means the penalty is architecturally dominant —
    a backend under slowstart cannot win against any backend with real
    stats until the penalty has decayed substantially. This is intentional:
    the ramp IS the mechanism, not a subtle bias. In a separated system,
    the LB's slow-start weight dominates routing in the same way.
    """
    if _BACKEND_SELECTION_POLICY != "topology_slowstart":
        return 0.0
    discovered = controller._backend_discovery_ts.get(mac)
    if discovered is None:
        return 1.0          # undiscovered → maximum deterrence
    elapsed = time.monotonic() - discovered
    if elapsed >= ttl_s:
        return 0.0
    return 1.0 - (elapsed / ttl_s)
```

---

### Step 5: `selection.py` — Gate warm lease in `select_server`

**Replace the warm lease call and its early-return block**:

```python
    # Warm lease: only active in topology_lifecycle mode (RQ2).
    # topology_host and topology_slowstart skip it — the WSM cost
    # function handles new-backend selection via unknown-stats defaults.
    if _BACKEND_SELECTION_POLICY == "topology_lifecycle":
        warm = _claim_warm_backend(
            controller, "vip_server", controller._warm_server_leases, pool,
        )
        if warm is not None:
            return warm
```

---

### Step 6: `selection.py` — Override unknown-stats defaults in `select_server`

**Replace the three `... if stats else 1.0` normalisation lines** for `cpu_norm`, `ram_norm`, `req_norm`:

```python
        _default = _unknown_stats_default()
        cpu_norm = (stats.avg_cpu_percent / cpu_max) if stats else _default
        ram_norm = (stats.avg_ram_used_mb  / ram_max) if stats else _default
        req_norm = (stats.request_count    / req_max) if stats else _default
```

Note: `hop_norm` is NOT overridden — topology is always real.

---

### Step 7: `selection.py` — Add slowstart penalty in `select_server`

**After the `cost = (...)` line**, before `logger.debug`:

```python
        # Slow-start penalty (RQ2): topology_slowstart adds a graduated
        # cost penalty decaying 1.0→0.0 over WARM_SERVER TTL from discovery.
        # No-op for topology_host and topology_lifecycle.
        #
        # Design note — TTL reuse: the penalty decay period reuses
        # _VIP_WARM_SERVER_SECONDS (45 s) — the same TTL used for
        # warm-lease priority windows. These are semantically distinct
        # (warm-lease priority vs. discovery-time ramp), but using the
        # same TTL makes the comparison between topology_slowstart and
        # topology_lifecycle cleaner: both have a 45 s window, differing
        # only in when that window starts (discovery vs. spawn).
        cost += _slowstart_penalty(controller, mac, _VIP_WARM_SERVER_SECONDS)
```

---

### Step 8: `selection.py` — Gate warm lease in `select_storage`

**Replace the warm lease call and its early-return block** in `select_storage`:

```python
    if _BACKEND_SELECTION_POLICY == "topology_lifecycle":
        warm = _claim_warm_backend(
            controller,
            f"vip_data({domain})",
            controller._warm_storage_leases.setdefault(domain, {}),
            pool,
        )
        if warm is not None:
            return warm
```

---

### Step 9: `selection.py` — Override unknown-stats defaults in `select_storage`

**Replace the four `... if stats else 1.0` normalisation lines** for `cpu_norm`, `ram_norm`, `conn_norm`, `lag_norm`:

```python
        _default = _unknown_stats_default()
        cpu_norm  = (stats.avg_cpu_percent        / cpu_max)  if stats else _default
        ram_norm  = (stats.avg_ram_used_mb         / ram_max)  if stats else _default
        conn_norm = (stats.avg_connections          / conn_max) if stats else _default
        lag_norm  = ((stats.avg_repl_lag_s or 0)   / lag_max)  if stats else _default
```

---

### Step 10: `selection.py` — Add slowstart penalty in `select_storage`

**After the `cost = (...)` line**, before `logger.debug`:

```python
        # Slow-start penalty (RQ2): same design as select_server.
        # Reuses _VIP_WARM_STORAGE_SECONDS (30 s) for the ramp period —
        # same TTL as storage warm leases, differing only in start time.
        cost += _slowstart_penalty(controller, mac, _VIP_WARM_STORAGE_SECONDS)
```

---

### Step 11: Env override files

**File**: `source/scripts/testing/controller_env_overrides/rq2_topology_host.env`
```
# RQ2 — topology_host: unknown stats → best-case (0.0), no warm lease, no ramp.
# Encodes HAProxy leastconn without slow-start (cold-start thundering herd).
BACKEND_SELECTION_POLICY=topology_host
```

**File**: `source/scripts/testing/controller_env_overrides/rq2_topology_slowstart.env`
```
# RQ2 — topology_slowstart: unknown stats → neutral, penalty 1.0 until discovery,
# then graduated decay 1.0→0.0 over warm-lease TTL. Encodes separated LB slow-start
# with coordination delay (HAProxy/NGINX slow-start starting at first health check).
BACKEND_SELECTION_POLICY=topology_slowstart
```

No file needed for `topology_lifecycle` — it's the default.

---

## What Does NOT Change

| Component | Reason |
|---|---|
| `main_n1.py` / `main_n2.py` | Warm leases still created by `register_new_server_backend()` — the policy mode only gates whether `select_server`/`select_storage` consume them. See note below on log noise. |
| `elasticity/` | Scale-up/down logic unchanged |
| `telemetry/` | Telemetry pipeline unchanged |
| `topology/` | Hop cache unchanged |
| `_vip_routing/flows.py` | Flow rule installation unchanged |
| `_vip_routing/ingress.py` | Packet dispatch unchanged — calls `selection.select_server()` / `selection.select_storage()` |

**Warm-lease log noise in non-lifecycle modes**: `register_new_server_backend()` (called by the elasticity manager in `main_n*.py`) unconditionally calls `mark_server_backend_warm()`, which creates a `WarmLease` and logs it. In `topology_host` and `topology_slowstart` modes, `_claim_warm_backend()` is gated off so these leases are never claimed — they expire after their TTL with an info-level log line. This is harmless (a few log lines per scale-up event) and keeps the change minimal (no modification to `main_n*.py` or `elasticity/`).

---

## Verification Checklist

- [ ] `config.py`: `_BACKEND_SELECTION_POLICY` resolves correctly for all three values
- [ ] `state.py`: `_backend_discovery_ts` populated on first telemetry, cleaned up on unregister
- [ ] `selection.py`: Warm lease only claimed in `topology_lifecycle` mode
- [ ] `selection.py`: Unknown stats → 0.0 in `topology_host` and `topology_slowstart`, 1.0 in `topology_lifecycle`
- [ ] `selection.py`: Slowstart penalty decays linearly in `topology_slowstart`, zero in other modes
- [ ] Env overrides: Files created and parseable by the Makefile
- [ ] Controller boots without errors in all three modes
- [ ] Existing golden-config behavior unchanged (default is `topology_lifecycle`)
- [ ] No import errors, no new dependencies

---

## Summary

| File | Lines changed | New lines |
|---|---|---|
| `config.py` | 0 | 6 |
| `state.py` | 0 | 6 (init: 2, update_server: 1, update_storage: 1, unregister_server: 1, unregister_storage: 1) |
| `selection.py` | 14 (modified: gates, overrides, imports) | 38 (helpers: 32, penalty calls: 4, imports: 2) |
| Env overrides | — | 2 files × 3 lines (comment + blank + value) |
| **Total** | ~14 modified lines | ~55 new lines |

All changes confined to `_vip_routing/`. No impact on `main_n*.py`, `elasticity/`, `telemetry/`, or `topology/`.
