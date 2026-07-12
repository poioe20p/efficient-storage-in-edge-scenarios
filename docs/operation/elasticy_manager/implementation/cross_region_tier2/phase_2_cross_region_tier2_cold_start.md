# Phase 2 — Cross-Region Tier 2 Cold-Start

**Status**: 📋 Planned
**Depends on**: [Phase 1 — Warm Standby](./phase_1_cross_region_tier2_warm_standby.md)

---

## Primary Outcome

On-demand cross-region replica spawn — no pre-spawned standby. When cross-region
DB pressure is detected, the consumer LAN's controller spawns a new MongoDB
secondary of the remote replica set, waits for full initial sync, then admits
it to the local `VIP_DATA` pool. The sync duration is the **readiness gap** —
RQ3's core measurement.

---

## Difference from Phase 1 (Warm)

|                              | Warm (Phase 1)                            | Cold (Phase 2)                             |
| ---------------------------- | ----------------------------------------- | ------------------------------------------ |
| When does the replica exist? | Pre-spawned at baseline                   | Spawned on first pressure detection        |
| Readiness gap                | Admission only (~instant)                 | Full initial sync (minutes)                |
| Idle cost                    | Ongoing replication + container resources | Zero                                       |
| Activation trigger           | Same breach signal                        | Same breach signal                         |
| Replenishment                | Yes (new standby after activation)        | No (replica stays active until scale-down) |

---

## Files Changed

| # | File                            | Change                                                                                                    | Lines    |
| - | ------------------------------- | --------------------------------------------------------------------------------------------------------- | -------- |
| 1 | `main_n1.py` + `main_n2.py` | Branch `_evaluate_cross_region_activation` for cold-start path; add `_MAX_CROSS_REGION_STORAGE` import | ~25      |
| 2 | Env override                    | `rq3_tier2_cold.env`                                                                                    | new file |

---

## Design Decision: Warm Lease on Cold-Start?

When a cold-start cross-region replica finishes initial sync and is admitted
to the VIP pool, should it receive a warm lease?

**Decision: NO — follow the same-LAN Tier 2 path.**  Warm leases are an
RQ2 property (routing-plane awareness timing).  RQ3 holds routing constant
across all strategies.  The warm path (Phase 1) uses `_promote_storage_backend`
which calls both `add_storage_mac` and `mark_storage_backend_warm` — the warm
lease is a by-product of the reserve activation mechanism, not a deliberate
RQ3 variable.  The cold path uses the standard `control_events.py`
`add_storage_mac_fn` (VIP pool only, no warm lease) — the same path used by
same-LAN Tier 2 scale-up.

**This is consistent within RQ3**: warm standby gets warm leases (faster
load redistribution after admission), cold-start does not (same as same-LAN
Tier 2).  Both strategies hold the RQ2 policy constant at `topology_lifecycle`
(the existing default).  If we added warm leases to the cold path, we'd be
varying RQ2 and RQ3 simultaneously.

---

## Step-by-Step

### Step 1 — Branch `_evaluate_cross_region_activation` for cold-start

Phase 1's `_evaluate_cross_region_activation` already handles the breach
detection pipeline. Instead of adding a separate method that duplicates
this logic, add an `else` branch for the cold-start path. The breach
detection, M-of-N debounce, and cooldown are **shared** — only the response
differs.

```python
def _evaluate_cross_region_activation(self, summary: TelemetrySummary) -> None:
    """Admit warm standby or spawn cold replica on cross-region pressure."""
    if not _CROSS_REGION_STORAGE_ENABLED:
        return

    peer_lan = "lan2" if self._lan_id == "lan1" else "lan1"

    # ── Shared breach detection ─────────────────────────────────────
    if not self._cross_region_db_breach_this_window(summary, peer_lan):
        return
    if not self._cross_region_breach_ring_ready(peer_lan, summary):
        return
    if self._cross_region_cooldown_active():
        return

    if _CROSS_REGION_STORAGE_WARM:
        # ── Phase 1: admit standby ──────────────────────────────────
        slot = self._node_registry.get_cross_region_reserve_slot()
        if slot is None or slot.state != "READY_RESERVED":
            return
        mac, ip, name = self._node_registry.consume_cross_region_reserve()
        vip_domain = f"n{self._lan_num}"
        self._promote_storage_backend(mac, vip_domain)
        self._cross_region_last_activation_ts = time.monotonic()
        logger.info(
            "[cross-region-reserve] ACTIVATED: mac=%s ip=%s name=%s vip=%s owner=%s",
            mac, ip, name, vip_domain, slot.owner_lan,
        )
        self._prepare_cross_region_reserve_if_needed()

    else:
        # ── Phase 2: cold-start spawn via DataAlert ──────────────────
        current = self._count_cross_region_active()
        if current >= _MAX_CROSS_REGION_STORAGE:
            return

        peer_lan_num = 2 if self._lan_id == "lan1" else 1

        # Resolve peer primary.  Returns (rs_name, "ip:27018") or None.
        result = self.resolve_peer_primary(peer_lan)
        if result is None:
            logger.warning(
                "[cross-region-cold] cannot resolve peer primary for %s — deferring",
                peer_lan,
            )
            return
        peer_rs_name, peer_primary_host = result

        primary_container = f"edge_storage_server_n{peer_lan_num}"

        alert = DataAlert(
            lan=self._lan_num,
            network_id=self._lan_id,
            rs_name=peer_rs_name,
            primary_container=primary_container,
            port=27018,
            cross_lan_rs=True,
            owner_lan=peer_lan,
            owner_primary=peer_primary_host,
        )
        self._elasticity.submit(alert)
        self._cross_region_last_activation_ts = time.monotonic()
        logger.info(
            "[cross-region-cold] SPAWN submitted: consumer_lan=%d owner=%s rs=%s",
            self._lan_num, peer_lan, peer_rs_name,
        )
```

**Helper — `_count_cross_region_active`**:

```python
def _count_cross_region_active(self) -> int:
    """Count active cross-region storage nodes.

    Cross-region nodes have ``owner_lan`` populated (Phase 0).
    Same-LAN nodes leave it empty.
    """
    return sum(
        1 for info in self._node_registry.list_dynamic("storage")
        if info.owner_lan and not info.standby_reserved
    )
```

**Key changes from Phase 1**:

- Warm path: `_CROSS_REGION_STORAGE_WARM` branch unchanged
- Cold path: same breach detection → `DataAlert(cross_lan_rs=True)` instead
  of admitting a standby
- `resolve_peer_primary` returns `(rs_name, host)` tuple — use `peer_rs_name`
  and `peer_primary_host` directly
- `primary_container` derived from LAN number convention (no non-existent
  `resolve_container_for_host` call)
- `_count_cross_region_active` uses `owner_lan` (populated by Phase 0)
  instead of comparing `rs_name` strings
- No ring reset on non-breach — the sliding window naturally decays false
  windows (no `self._cross_region_breach_ring.pop(peer_lan, None)`)

**New import required** (both `main_n1.py` and `main_n2.py`):

```python
from .scaling_config import (
    ...
    _MAX_CROSS_REGION_STORAGE,   # ← add
)
```

---

### Step 2 — Readiness gap measurement

No code changes needed.  `control_events.py:_log_storage_ready` already logs
the readiness gap for every storage node that reaches SECONDARY:

```
[node_ready] timing container=<name> node_type=storage source=rs_secondary_ready total=<X>s state=READY
```

`total=<X>s` is `time.monotonic() − spawn_started_monotonic_s` — exactly
the provisioning-to-readiness gap RQ3 needs.  For offline analysis, grep
controller logs for `[node_ready]` and filter by `owner_lan` (cross-region)
vs empty (same-LAN).

---

### Step 3 — Scale-down limitation

Existing LIFO scale-down (`find_last_dynamic("storage")`) works for the
single-cross-region-node test scenario — the most recently added storage
node is the cross-region replica.  However, candidate selection does not
distinguish cross-region from same-LAN nodes by `owner_lan`.  Cross-region-
aware scale-down (remote `rs.remove()` against the data-owner primary,
per-`owner_lan` underutilisation tracking) is **future work**.  For RQ3,
the single-node case is sufficient; the limitation is acknowledged.

---

### Step 4 — Env override for RQ3 cold-start

Create `source/scripts/testing/controller_env_overrides/rq3_tier2_cold.env`:

```bash
# RQ3 — Tier 2 Cold-Start (cross-region)
CROSS_REGION_STORAGE_ENABLED=1
CROSS_REGION_STORAGE_WARM=0
SS_ENABLED=0
MAX_CROSS_REGION_STORAGE=1
CROSS_REGION_STORAGE_COOLDOWN_S=120
```

---

## Phase 2 Verification Checklist

- [ ] `CROSS_REGION_STORAGE_WARM=0` — no standby pre-spawned at startup
- [ ] Cross-region DB pressure detected → `DataAlert(cross_lan_rs=True)` submitted
- [ ] Container spawns on consumer LAN, joins remote RS
- [ ] During initial sync, container is NOT in VIP pool (deferred until SECONDARY)
- [ ] `rs_secondary_ready` → `add_storage_mac` → admitted to VIP pool (no warm lease)
- [ ] Readiness gap logged via `[node_ready]` in controller logs (`total=<X>s`)
- [ ] Consumers read from local cross-region replica after admission
- [ ] Cooldown prevents rapid successive spawns
- [ ] `_MAX_CROSS_REGION_STORAGE` cap enforced
- [ ] Scale-down: replica removed cleanly (rs.remove + teardown) when pressure subsides

---

## Phase 2 Gate

Before considering the implementation complete, confirm:

1. A full RQ3 cold-start run completes: no pre-spawn → pressure detected → spawn → sync → admitted → consumers served → eventual scale-down
2. Readiness gap is measurable (logged in controller output)
3. Readiness gap is significantly longer than warm standby's admission-only gap (Phase 1 result) — this is the RQ3 comparison
4. Zero idle cost before spawn (no container, no replication traffic during baseline)
