# Phase 0 — Foundation: Cross-Region Spawn Plumbing

**Status**: 📋 Planned
**Depends on**: [README.md](./README.md)

---

## Primary Outcome

Enable `add_storage_node` to spawn a container that joins a **remote** replica
set. Today the RS seed host is derived from the spawn LAN — a node spawned on
LAN2 always joins `rs_net2`. After this phase, the caller can override the
seed host to join `rs_net1` from a LAN2 container.

Also add the env-var knobs and cross-region dispatch logic in `_handle_data`
so that a `DataAlert` with `cross_lan_rs=True` produces a correctly-placed,
correctly-registered cross-region replica.

---

## Files Changed

| # | File                        | Change                                                  | Lines |
| - | --------------------------- | ------------------------------------------------------- | ----- |
| 1 | `scaling_config.py`       | New feature-flag env vars for cross-region storage      | ~4    |
| 2 | `storage_node_manager.py` | Accept explicit`rs_seed_host` in `add_storage_node` | ~5    |
| 3 | `elasticity.py`           | `DataAlert.owner_primary` field                | ~2    |
| 4 | `elasticity.py`           | Cross-region dispatch in`_handle_data`                | ~25   |

> **Note**: Detection/policy parameters (breach windows, cooldown, DB threshold)
> belong to Phase 1 where the scaling_policy.py cross-region evaluation is built.
> Phase 0 only adds the feature-flag plumbing needed to gate cross-region storage.

---

## Step-by-Step

### Step 1 — Env vars (`scaling_config.py`)

Add after the existing `_SS_*` block (or with the other feature-flag constants):

```python
# ── Cross-region Tier 2 storage (feature flags) ───────────────────────
_CROSS_REGION_STORAGE_ENABLED = int(os.environ.get(
    "CROSS_REGION_STORAGE_ENABLED", "0"))
_CROSS_REGION_STORAGE_WARM = int(os.environ.get(
    "CROSS_REGION_STORAGE_WARM", "0"))
_MAX_CROSS_REGION_STORAGE = int(os.environ.get(
    "MAX_CROSS_REGION_STORAGE", "1"))
```

> **Deferred to Phase 1**: `_CROSS_REGION_STORAGE_COOLDOWN_S`,
> `_CROSS_REGION_BREACH_WINDOWS_M`, `_CROSS_REGION_BREACH_WINDOWS_N`,
> `_CROSS_REGION_DB_P95_THRESHOLD_MS`. These are detection/policy parameters
> that require the breach-ring and evaluation code built in Phase 1.
> Phase 0 only plumbs the dispatch path; alerts are constructed manually for
> verification.

**Verify**: Import one of these in a Python shell — `from sdn_controller.scaling_config import _CROSS_REGION_STORAGE_ENABLED` — confirm it reads from env.

---

### Step 2 — Seed host override (`storage_node_manager.py`)

**Current code** (lines 57–60 of `add_storage_node`):

```python
primary_ip = f"10.0.{lan - 1}.4"
rs_seed_host = f"{primary_ip}:{port}"
logger.info("[node_add] RS seed host for lan%d: %s", lan, rs_seed_host)
```

**Replace with**:

```python
if rs_seed_host_override is not None:
    rs_seed_host = rs_seed_host_override
    logger.info("[node_add] RS seed host (override): %s", rs_seed_host)
else:
    primary_ip = f"10.0.{lan - 1}.4"
    rs_seed_host = f"{primary_ip}:{port}"
    logger.info("[node_add] RS seed host for lan%d: %s", lan, rs_seed_host)
```

**Method signature change** (line 35):

```python
# Current:
def add_storage_node(
    self, lan: int, name: str, rs_name: str,
    port: int = 27018, ip: str | None = None, mac: str | None = None,
    heartbeat_enabled: bool = False,
) -> NodeResult:

# After:
def add_storage_node(
    self, lan: int, name: str, rs_name: str,
    port: int = 27018, ip: str | None = None, mac: str | None = None,
    heartbeat_enabled: bool = False,
    rs_seed_host_override: str | None = None,
) -> NodeResult:
```

**Verify**: Call `add_storage_node(lan=2, rs_name="rs_net1", rs_seed_host_override="10.0.0.4:27018", ...)` — the spawned container should join `rs_net1` (verify via `docker exec <name> mongosh --eval "rs.status().set"`).

---

### Step 3 — `DataAlert.owner_primary` field (`elasticity.py`)

Following the `SelectiveSyncAlert` pattern, add an explicit `owner_primary`
field to `DataAlert` so the remote primary address is **passed through**
rather than derived from LAN numbers:

```python
@dataclass(frozen=True)
class DataAlert:
    lan:               int
    network_id:        str
    rs_name:           str
    primary_container: str
    port:              int = 27018
    cross_lan_rs:      bool = False
    owner_lan:         str | None = None
    owner_primary:     str = ""     # NEW — "10.0.0.4:27018" for cross-region
```

### Step 4 — Cross-region dispatch (`elasticity.py` — `_handle_data`)

**Key principle** (from Tier 1's `SelectiveSyncAlert`): `alert.lan` is the
consumer LAN (spawn target). `alert.owner_lan` is the data source.
`alert.owner_primary` is the already-resolved remote primary `ip:port` —
no derivation needed.

The only change in `_handle_data`: if `owner_primary` is set, pass it as
the seed host override. Otherwise, derive from `alert.lan` as before.

```python
def _handle_data(self, alert: DataAlert) -> None:
    # Seed host: if owner_primary is set (cross-region), use it directly.
    # Otherwise derive from alert.lan (same-LAN, existing behaviour).
    if alert.owner_primary:
        rs_seed_override = alert.owner_primary
        logger.info(
            "[elasticity] data: CROSS-REGION spawn lan=%d rs=%s seed=%s owner=%s",
            alert.lan, alert.rs_name, rs_seed_override, alert.owner_lan,
        )
    else:
        rs_seed_override = None  # derived from alert.lan

    name = self._next_name("edge_storage", alert.network_id)
    ip, mac = self._get_allocator(alert.lan).allocate()
    spawn_started_monotonic_s = time.monotonic()
    logger.info(
        "[elasticity] data: spawning %s on LAN %d (ip=%s mac=%s)",
        name, alert.lan, ip, mac,
    )

    result = self._storage_adder.add_storage_node(
        lan=alert.lan,
        name=name,
        rs_name=alert.rs_name,
        port=alert.port,
        ip=ip, mac=mac,
        rs_seed_host_override=rs_seed_override,   # ← NEW kwarg
    )
    self._storage_adder.log_timings(result)
    self._record({"type": "data", "alert": alert, "name": name, "result": result})

    if result.success and result.ip:
        effective_mac = result.mac or mac
        effective_ip  = result.ip or ip
        if effective_mac:
            self._topo.register_backend_ip(effective_mac, effective_ip)
            logger.info(
                "[elasticity] data: %s online  ip=%s  mac=%s  (VIP deferred until SECONDARY)",
                name, effective_ip, effective_mac,
            )
            info = NodeInfo(
                mac=effective_mac, lan=alert.lan, network_id=alert.network_id,
                name=name, ip=effective_ip, node_type="storage",
                rs_name=alert.rs_name,
                primary_container=alert.primary_container,
                port=alert.port,
                spawn_started_monotonic_s=spawn_started_monotonic_s,
                owner_lan=alert.owner_lan or "",       # ← NEW: track cross-region provenance
            )
            with self._addition_complete_lock:
                self._addition_complete_infos.append(info)
    else:
        self._get_allocator(alert.lan).release(ip)
        logger.error("[elasticity] data: failed to spawn %s", name)
```

> **Design note — feature-flag gate**: The `_CROSS_REGION_STORAGE_ENABLED`
> gate is enforced at **alert-generation time** (Phase 1/2 in
> `scaling_policy.py`), not at dispatch time. In Phase 0, the dispatch path
> is always-on when `owner_primary` is set, since only manual verification
> constructs these alerts. Phase 1/2 will add a separate
> `_evaluate_cross_region_scale_up` method in `scaling_policy.py` that reads
> `t_db_p95_ms_per_lan` and produces `DataAlert(owner_primary=..., cross_lan_rs=True)`.

> **Deferred to Phase 1**: The `_handle_prepare_standby` handler also calls
> `add_storage_node` and will need the same `rs_seed_host_override` treatment
> for cross-region warm reserves. Phase 1 adds `owner_primary` to
> `PrepareStandbyStorageAlert` and passes it through identically.

**Verify**: From controller N2, submit:
```python
DataAlert(
    lan=2, network_id="lan2", rs_name="rs_net1",
    primary_container="edge_storage_server_n1",
    cross_lan_rs=True, owner_lan="lan1",
    owner_primary="10.0.0.4:27018",
)
```
The spawned container should run on LAN2, join `rs_net1`, register in `VIP_DATA_N2`.

---

## Phase 0 Verification Checklist

- [ ] `_CROSS_REGION_STORAGE_ENABLED` reads from env, defaults to 0
- [ ] `add_storage_node(lan=2, rs_name="rs_net1", rs_seed_host_override="10.0.0.4:27018", ...)` spawns on LAN2, joins `rs_net1`
- [ ] Manual `DataAlert(lan=2, rs_name="rs_net1", cross_lan_rs=True, owner_primary="10.0.0.4:27018", ...)` → spawns on LAN2
- [ ] Same manual alert → registers in `VIP_DATA_N2`
- [ ] Same-LAN `DataAlert(...)` without `owner_primary` → behaviour unchanged (regression)
- [ ] `NodeInfo.owner_lan` populated from `alert.owner_lan` for cross-region nodes
- [ ] Cross-region container can reach remote primary (`ping 10.0.0.4` from LAN2 container)
- [ ] Oplog replication works across WAN (remote primary → cross-region secondary)

---

## Phase 0 Gate

Before proceeding to Phase 1, confirm:

1. A manual cross-region spawn succeeds (RS join + VIP registration)
2. The cross-region secondary receives oplog entries from the remote primary
3. Reads served through the cross-region secondary return correct data
4. Same-LAN spawn path is not broken
