# Phase 1 — Cross-Region Tier 2 Warm Standby

**Status**: 📋 Planned
**Depends on**: [Phase 0 — Foundation](./phase_0_foundation_cross_region_spawn.md)

---

## Primary Outcome

A pre-spawned, pre-synced MongoDB secondary of the **remote** replica set, held
in `READY_RESERVED` on the consumer LAN, admitted to the local `VIP_DATA` pool
when cross-region DB pressure is detected. Zero sync tax on activation.

---

## Files Changed

| # | File | Change | Lines |
|---|---|---|---|
| 0 | `scaling_config.py` | Detection/policy env vars (deferred from Phase 0) | ~8 |
| 1 | `node_registry.py` | Cross-region reserve slot + helpers | ~40 |
| 2 | `elasticity.py` | `_handle_data` admits cross-region reserve to correct VIP domain | ~5 |
| 3 | `main_n1.py` + `main_n2.py` | Mediator: pre-spawn on startup, admit on pressure | ~50 |

---

## Step-by-Step

### Step 0 — Detection/policy env vars (`scaling_config.py`)

These were deferred from Phase 0 because they require the breach-ring and
evaluation code built in this phase. Add after the feature-flag constants
(added in Phase 0):

```python
# ── Cross-region Tier 2 detection/policy ──────────────────────────────
_CROSS_REGION_STORAGE_COOLDOWN_S = float(os.environ.get(
    "CROSS_REGION_STORAGE_COOLDOWN_S", "120"))
# M-of-N sliding window for cross-region DB pressure (mirrors Tier 1
# breach ring in selective_sync/promotion.py).
_CROSS_REGION_BREACH_WINDOWS_M = int(os.environ.get(
    "CROSS_REGION_BREACH_WINDOWS_M", "2"))
_CROSS_REGION_BREACH_WINDOWS_N = int(os.environ.get(
    "CROSS_REGION_BREACH_WINDOWS_N", "5"))
# p95 DB time (ms) threshold per remote LAN.
# Mirrors TAU_DADOS_MS in selective_sync/hotness.py.
_CROSS_REGION_DB_P95_THRESHOLD_MS = float(os.environ.get(
    "CROSS_REGION_DB_P95_THRESHOLD_MS", "65"))
```

**Verify**: Import in a Python shell — confirm all 4 read from env.

---

### Step 1 — Cross-region reserve slot (`node_registry.py`)

Add to `DynamicNodeRegistry` after the existing `StorageReserveSlot` and
`_reserve_slots` dict.  Owned by the registry (not module-level), mirroring
how `StorageReserveSlot` is owned.

**In `DynamicNodeRegistry.__init__`**:

```python
# Cross-region reserve — one slot for the peer LAN's RS secondary
# placed in this LAN.  None when disabled.
self._cross_region_reserve_slot: CrossRegionReserveSlot | None = None
```

**New dataclass** (before `DynamicNodeRegistry`):

```python
@dataclass
class CrossRegionReserveSlot:
    """One cross-region reserve per consumer LAN.
    
    Tracks a pre-spawned secondary of the PEER LAN's replica set, placed
    in THIS LAN to serve cross-region reads locally. Mirrors
    ``StorageReserveSlot`` but targets the remote RS instead of the local one.
    """
    state: str = "NONE"          # NONE | PREPARING | READY_RESERVED
    mac: str = ""
    ip: str = ""
    container_name: str = ""
    owner_lan: str = ""          # "lan1" or "lan2" — which RS this reserve belongs to
    rs_name: str = ""            # e.g. "rs_net1" (the REMOTE RS)
    pending_reason: str = ""
    prepare_submitted_ts: float = 0.0
    ready_ts: float = 0.0
```

**Methods on `DynamicNodeRegistry`** (mirroring same-LAN reserve helpers):

```python
def get_cross_region_reserve_slot(self) -> CrossRegionReserveSlot | None:
    """Return the cross-region reserve slot, or None if disabled."""
    return self._cross_region_reserve_slot

def init_cross_region_reserve_slot(self) -> CrossRegionReserveSlot:
    """Create and return a fresh slot (called once at startup if enabled)."""
    self._cross_region_reserve_slot = CrossRegionReserveSlot()
    return self._cross_region_reserve_slot

def should_prepare_cross_region_reserve(self) -> bool:
    slot = self._cross_region_reserve_slot
    return slot is not None and slot.state == "NONE"

def mark_cross_region_reserve_prepare_submitted(
    self, owner_lan: str, rs_name: str,
) -> None:
    slot = self._cross_region_reserve_slot
    assert slot is not None
    slot.state = "PREPARING"
    slot.owner_lan = owner_lan
    slot.rs_name = rs_name
    slot.prepare_submitted_ts = time.monotonic()

def mark_cross_region_reserve_ready(
    self, mac: str, ip: str, container_name: str,
) -> None:
    slot = self._cross_region_reserve_slot
    assert slot is not None
    slot.state = "READY_RESERVED"
    slot.mac = mac
    slot.ip = ip
    slot.container_name = container_name
    slot.ready_ts = time.monotonic()

def consume_cross_region_reserve(self) -> tuple[str, str, str]:
    """Activate: return (mac, ip, container_name) and reset slot to NONE."""
    slot = self._cross_region_reserve_slot
    assert slot is not None
    mac, ip, name = slot.mac, slot.ip, slot.container_name
    slot.state = "NONE"
    slot.mac = slot.ip = slot.container_name = ""
    return mac, ip, name
```

**Verify**: Unit-test the slot state machine — NONE → PREPARING → READY_RESERVED → (consume) → NONE.

---

### Step 2 — Pre-spawn on startup (`main_n1.py` + `main_n2.py`)

In the mediator's startup sequence (after `ElasticityManager.start()` and topology is stable), submit a cross-region `PrepareStandbyStorageAlert` **if** `CROSS_REGION_STORAGE_ENABLED=1` and `CROSS_REGION_STORAGE_WARM=1`.

The existing same-LAN reserve pre-spawn logic lives in `_handle_storage_reserve_trigger`. Add a parallel method `_prepare_cross_region_reserve_if_needed`:

```python
def _prepare_cross_region_reserve_if_needed(self) -> None:
    """Pre-spawn one cross-region warm standby on startup (if enabled)."""
    if not _CROSS_REGION_STORAGE_ENABLED or not _CROSS_REGION_STORAGE_WARM:
        return

    slot = self._node_registry.get_cross_region_reserve_slot()
    if slot is None:
        return
    if not self._node_registry.should_prepare_cross_region_reserve():
        logger.debug("[cross-region-reserve] slot already %s — skipping", slot.state)
        return

    # Determine peer LAN and its RS details.
    peer_lan = "lan2" if self._lan_id == "lan1" else "lan1"
    peer_lan_num = 2 if self._lan_id == "lan1" else 1
    peer_rs_name = f"rs_net{peer_lan_num}"

    # Resolve peer primary: returns (rs_name, "ip:27018") or None.
    result = self.resolve_peer_primary(peer_lan)
    if result is None:
        logger.warning(
            "[cross-region-reserve] cannot resolve peer primary for %s — deferring",
            peer_lan,
        )
        return
    _peer_rs_name, peer_primary_host = result  # ("rs_net1", "10.0.0.4:27018")

    self._node_registry.mark_cross_region_reserve_prepare_submitted(
        peer_lan, peer_rs_name,
    )

    # Primary container name is a fixed convention per LAN.
    primary_container = f"edge_storage_server_n{peer_lan_num}"

    alert = PrepareStandbyStorageAlert(
        lan=self._lan_num,                  # spawn in THIS (consumer) LAN
        network_id=self._lan_id,
        rs_name=peer_rs_name,               # join the REMOTE RS
        primary_container=primary_container,
        owner_primary=peer_primary_host,     # already-resolved "10.0.0.4:27018"
    )
    self._elasticity.submit(alert)
    logger.info(
        "[cross-region-reserve] prepare submitted: target_lan=%d rs=%s primary=%s",
        self._lan_num, peer_rs_name, peer_primary_host,
    )
```

Call this after the same-LAN reserve pre-spawn, during the startup sequence where `_handle_storage_reserve_trigger` is first invoked.

**Key detail**: The `PrepareStandbyStorageAlert` handler calls
`add_storage_node(lan=alert.lan, ...)`. Following the Tier 1
`SelectiveSyncAlert` pattern, add `owner_primary: str = ""` to
`PrepareStandbyStorageAlert` and pass the already-resolved remote primary
directly — no derivation from LAN numbers or RS names.

```python
@dataclass(frozen=True)
class PrepareStandbyStorageAlert:
    lan: int
    network_id: str
    rs_name: str
    primary_container: str
    port: int = 27018
    owner_primary: str = ""   # NEW — "10.0.0.4:27018" for cross-region
```

In `_handle_prepare_standby_storage`, use `owner_primary` directly as the seed host:

```python
def _handle_prepare_standby(self, alert: PrepareStandbyStorageAlert) -> None:
    # Cross-region: owner_primary is the already-resolved remote primary.
    rs_seed = alert.owner_primary or None

    result = self._storage_adder.add_storage_node(
        lan=alert.lan,
        name=name,
        rs_name=alert.rs_name,
        port=alert.port,
        ip=ip, mac=mac,
        heartbeat_enabled=True,
        rs_seed_host_override=rs_seed,
    )
    # ... rest unchanged ...
```

**Verify**: After controller startup, check that a cross-region standby container exists (`docker ps | grep edge_storage`), is a SECONDARY of the remote RS (`docker exec <name> mongosh --eval "rs.status().members.find(...).stateStr"`), and is NOT in the VIP pool (no `add_storage_mac` log for this MAC).

---

### Step 3 — Admit on demand (`main_n1.py` + `main_n2.py`)

In the telemetry callback (where `_handle_storage_reserve_trigger` and `PromotionCoordinator.evaluate` are called), add cross-region activation logic:

```python
def _evaluate_cross_region_activation(self, summary: TelemetrySummary) -> None:
    """Admit the cross-region warm standby if cross-region DB pressure detected."""
    if not _CROSS_REGION_STORAGE_ENABLED or not _CROSS_REGION_STORAGE_WARM:
        return

    slot = self._node_registry.get_cross_region_reserve_slot()
    if slot is None or slot.state != "READY_RESERVED":
        return  # Nothing to admit

    # Determine peer LAN
    peer_lan = "lan2" if self._lan_id == "lan1" else "lan1"

    # Reuse the same breach signal Tier 1 uses:
    # t_db_p95_ms_per_lan[peer_lan] > threshold
    if not self._cross_region_db_breach_this_window(summary, peer_lan):
        return

    # M-of-N debounce
    if not self._cross_region_breach_ring_ready(peer_lan):
        return

    # Cooldown check
    if self._cross_region_cooldown_active():
        return

    # Admit the reserve
    mac, ip, name = self._node_registry.consume_cross_region_reserve()

    # Register in the consumer LAN's VIP_DATA pool
    vip_domain = f"n{self._lan_num}"
    self.add_storage_mac(mac, vip_domain)
    self.mark_storage_backend_warm(mac, vip_domain)

    # Record activation for cooldown
    self._cross_region_last_activation_ts = time.monotonic()

    logger.info(
        "[cross-region-reserve] ACTIVATED: mac=%s ip=%s vip=%s owner=%s",
        mac, ip, vip_domain, slot.owner_lan,
    )

    # Trigger replenishment
    self._prepare_cross_region_reserve_if_needed()
```

**Breach detection helper** (`_cross_region_db_breach_this_window`):

```python
def _cross_region_db_breach_this_window(self, summary: TelemetrySummary,
                                         peer_lan: str) -> bool:
    """True if any local edge server has p95 DB time > threshold for peer LAN."""
    threshold = _CROSS_REGION_DB_P95_THRESHOLD_MS
    return any(
        srv.t_db_p95_ms_per_lan.get(peer_lan, 0.0) > threshold
        for srv in summary.servers.values()
    )
```

This is the same logic as `selective_sync/hotness.py:breach_this_window` — intentionally identical so Tier 1 and Tier 2 share the same activation signal.

**M-of-N debounce** (simple sliding window in the mediator):

```python
# In __init__:
self._cross_region_breach_ring: dict[str, deque] = {}  # peer_lan -> deque(bool)

def _cross_region_breach_ring_ready(self, peer_lan: str) -> bool:
    ring = self._cross_region_breach_ring.setdefault(
        peer_lan, deque(maxlen=_CROSS_REGION_BREACH_WINDOWS_N)
    )
    breached = self._cross_region_db_breach_this_window(
        self._last_summary, peer_lan
    )
    ring.append(breached)
    return sum(ring) >= _CROSS_REGION_BREACH_WINDOWS_M
```

**Cooldown**:

```python
def _cross_region_cooldown_active(self) -> bool:
    elapsed = time.monotonic() - self._cross_region_last_activation_ts
    return elapsed < _CROSS_REGION_STORAGE_COOLDOWN_S
```

**Verify**: Run a workload with cross-region hotspot phases. Verify that:
1. The standby is pre-spawned and READY before the hotspot phase
2. When the hotspot hits, the standby is admitted to `VIP_DATA_N{consumer}`
3. Consumer reads are served locally (verify via `client_requests.csv` DB time)
4. After the hotspot subsides, the standby is NOT scaled down (reserve is consumed; new reserve is prepared)
5. A new standby is prepared after activation (replenishment)

---

### Step 4 — Env overrides for RQ3

Create `source/scripts/testing/controller_env_overrides/rq3_tier2_warm.env`:

```bash
# RQ3 — Tier 2 Warm Standby (cross-region)
CROSS_REGION_STORAGE_ENABLED=1
CROSS_REGION_STORAGE_WARM=1
SS_ENABLED=0
```

And `testing/controller_env_overrides/rq3_remote.env` (baseline):

```bash
# RQ3 — Remote Only
CROSS_REGION_STORAGE_ENABLED=0
CROSS_REGION_STORAGE_WARM=0
SS_ENABLED=0
```

---

## Phase 1 Verification Checklist

- [ ] Cross-region standby pre-spawns on controller startup
- [ ] Standby joins remote RS and reaches SECONDARY
- [ ] Standby receives oplog from remote primary (verify `replLag` in telemetry)
- [ ] Standby is NOT in VIP pool while READY_RESERVED
- [ ] Cross-region DB pressure detected (breach signal fires)
- [ ] M-of-N debounce prevents spurious activation
- [ ] Standby admitted to `VIP_DATA_N{consumer}` on sustained pressure
- [ ] Consumers read from local cross-region replica (DB time drops)
- [ ] Replenishment: new standby prepared after activation
- [ ] Cooldown prevents rapid re-activation
- [ ] Same-LAN reserve path is not broken (regression)

---

## Phase 1 Gate

Before proceeding to Phase 2, confirm:
1. A full RQ3 warm-standby run completes: standby pre-spawns → pressure detected → admitted → consumers served locally → new standby replenished
2. The readiness gap (time from breach_window_end to admitted) is measurable and < 5 seconds
3. No new tracebacks or error log entries related to cross-region path
