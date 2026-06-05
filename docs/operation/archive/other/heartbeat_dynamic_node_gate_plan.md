# Plan — Disable Heartbeats on Dynamic Nodes (`HEARTBEAT_ENABLED` Gate)

**Status:** Implemented
**Scope:** Telemetry subsystem + dynamic node spawners
**Approach:** Env-var gate (`HEARTBEAT_ENABLED`) — see §2 for alternatives considered

Implementation landed in:
- [source/docker/edge_server/source/telemetry.py](../../../source/docker/edge_server/source/telemetry.py) — `HEARTBEAT_ENABLED` flag gating the heartbeat thread.
- [source/docker/edge_storage_server/mongo_telemetry.py](../../../source/docker/edge_storage_server/mongo_telemetry.py) — `HEARTBEAT_ENABLED` flag gating the heartbeat branch of `_push_stats`.
- [source/sdn_controller/elasticity/compute_node_manager.py](../../../source/sdn_controller/elasticity/compute_node_manager.py) — leaves dynamic compute on the image default `HEARTBEAT_ENABLED=false`.
- [source/sdn_controller/elasticity/storage_node_manager.py](../../../source/sdn_controller/elasticity/storage_node_manager.py) — passes literal `HEARTBEAT_ENABLED=true|false` in `_docker_run_storage`.
- Docs updated: [telemetry_overview.md](../telemetry/telemetry_overview.md), [elasticity_overview.md](../elasticy_manager/elasticity_overview.md), [system_mechanisms.md](../system_mechanisms.md).

---

## 1. Motivation

Under the system's operating assumptions, for **dynamic** nodes:

- Receiving requests → keep.
- Not receiving requests → remove (graceful scale-down, or hard timeout — both converge on removal).
- Not receiving requests but consuming CPU → degenerate state; timeout path is acceptable.

There is no legitimate "idle but keep alive" state for dynamic nodes. Therefore heartbeats on dynamic nodes are redundant and slightly counterproductive: when scale-down hasn't fired yet (cooldown, windows warming up), a heartbeat-driven liveness signal pushes eviction from the graceful path to the 180 s timeout ceiling — for a node we already intend to remove.

**Static** nodes (`edge_server_n{1,2}`, `edge_storage_server_n{1,2}` — the primary DB containers) are explicitly excluded from scale-down (see [elasticity_overview.md §Node Removal](../elasticy_manager/elasticity_overview.md)). Heartbeats remain their only liveness signal during quiet periods and must continue to fire.

**Conclusion.** Heartbeats should be emitted by **static nodes only**. Dynamic nodes should rely on data events for liveness and on the 180 s timeout as a failure detector.

---

## 2. Approaches considered

| # | Approach | Pros | Cons | Effort | Risk |
|---|---|---|---|---|---|
| **A** | **Env-var gate (`HEARTBEAT_ENABLED`)**. Only the literal value `true` enables periodic heartbeats. Dynamic nodes keep the disabled default; static containers set `HEARTBEAT_ENABLED=true`. | Minimal, surgical; fully reversible; no protocol change; aggregator/controller unchanged | One more env var to remember; split behavior by configuration rather than by explicit role | **Low** | Very low |
| **B** | **Explicit `role` field in telemetry events**. Aggregator/elasticity manager branches on `role=static\|dynamic`. | Semantically cleanest; opens door to other role-conditional behavior | Touches event schema, Pydantic model, elasticity liveness logic, tests | Medium | Medium |
| **C** | **Remove heartbeats entirely**. Rely on scale-down + timeout everywhere. | Simplest code | Breaks liveness for static nodes during genuine quiet periods | Low | **High — unsafe** |
| **D** | **Document only, no code change**. | Zero risk | Leaves the redundancy in place | Very Low | None |

**Recommended: Approach A.** Smallest footprint, keeps the telemetry protocol unchanged (aggregator and controller continue to treat `heartbeat` events as before — they just won't arrive from dynamic nodes), reversible by flipping one env var at spawn time.

---

## 3. Code changes

### 3.1 [source/docker/edge_server/source/telemetry.py](../../../source/docker/edge_server/source/telemetry.py)

Add a module-level flag and gate the heartbeat thread start:

```python
HEARTBEAT_INTERVAL_S: float = float(os.environ.get("HEARTBEAT_INTERVAL_S", "60"))
HEARTBEAT_ENABLED: bool = (
    os.environ.get("HEARTBEAT_ENABLED", "false").strip().lower() == "true"
)
```

In `init_telemetry`:

```python
def init_telemetry(app: Flask, sender: MetricSender | None = None) -> None:
    _sender = sender or ZmqMetricSender()

    if HEARTBEAT_ENABLED:
        _last_sent: list[float] = [time.monotonic()]
        threading.Thread(
            target=_heartbeat_loop, args=(_sender, _last_sent), daemon=True
        ).start()
    # ... rest unchanged
```

The `_last_sent` countdown reset in the request hook is harmless when the thread isn't running; no need to gate it.

### 3.2 [source/docker/edge_storage_server/mongo_telemetry.py](../../../source/docker/edge_storage_server/mongo_telemetry.py)

Same flag, gate the heartbeat branch of `_push_stats`:

```python
HEARTBEAT_INTERVAL_S = float(os.environ.get("HEARTBEAT_INTERVAL_S", "60"))
HEARTBEAT_ENABLED = (
    os.environ.get("HEARTBEAT_ENABLED", "false").strip().lower() == "true"
)
```

```python
if activity:
    event_type = "mongo_stats"
elif HEARTBEAT_ENABLED and now - _last_send_ts >= HEARTBEAT_INTERVAL_S:
    event_type = "heartbeat"
else:
    logger.debug("No client activity — skipping telemetry push")
    return
```

### 3.3 [source/sdn_controller/elasticity/compute_node_manager.py](../../../source/sdn_controller/elasticity/compute_node_manager.py) — `_docker_run_server`

Dynamic compute nodes keep the image default `HEARTBEAT_ENABLED=false`; no explicit injection is required:

```python
cmd = [
    "docker", "run", "-dit",
    "--network", "none",
    "--name", name,
    "-e", f"LAN_ID=lan{lan}",
    "-e", f"CONTAINER_NAME={name}",
    "edge_server",
]
```

### 3.4 [source/sdn_controller/elasticity/storage_node_manager.py](../../../source/sdn_controller/elasticity/storage_node_manager.py) — `_docker_run_storage`

Dynamic storage spawns pass the strict boolean contract expected by the sidecar. Ordinary dynamic secondaries use `false`; standby reserves use `true`:

```python
cmd = [
    "docker", "run", "-dit",
    "--network", "none",
    "--name", name,
    "-v", f"{vol}:/data/db",
    "-e", f"LAN_ID=lan{lan}",
    "-e", f"MONGO_REPLSET={rs_name}",
    "-e", f"MONGO_PORT={port}",
    "-e", f"CONTAINER_NAME={name}",
    "-e", f"HEARTBEAT_ENABLED={'true' if heartbeat_enabled else 'false'}",
]
```

### 3.5 [source/sdn_controller/elasticity/selective_storage_manager.py](../../../source/sdn_controller/elasticity/selective_storage_manager.py) — `_docker_run_selective`

Inspect before finalising. The selective-storage image's telemetry module
([source/docker/edge_selective_storage/telemetry.py](../../../source/docker/edge_selective_storage/telemetry.py))
currently has no heartbeat emitter, so **likely no change** is required. If a
heartbeat emitter is added in the future, keep its dynamic default at
`HEARTBEAT_ENABLED=false` and only opt in with `true` where static or
standby liveness is required.

### 3.6 Static container specs — no change required

[source/scripts/network/build_network_1.sh](../../../source/scripts/network/build_network_1.sh)
and its n2 counterpart now set `-e HEARTBEAT_ENABLED=true` explicitly on the
static containers so the launch scripts match the strict boolean contract.

### 3.7 Controller / aggregator — no change

The heartbeat event type, aggregator handling
([local_state_server/aggregator.py line 208](../../../source/docker/local_state_server/aggregator.py)),
and the "absent windows" counter all continue to work. Dynamic nodes simply
stop producing `heartbeat` events; presence of **any** event (request-driven,
`mongo_stats`, or heartbeat from a static peer) still resets the per-MAC
absence counter.

---

## 4. Behavioral consequences

| Scenario | Before | After |
|---|---|---|
| Dynamic compute spawns → idle → scale-down path active | Removed by scale-down | Removed by scale-down (unchanged) |
| Dynamic compute spawns → idle → scale-down blocked (cooldown, windows warming) | Heartbeats hold node alive indefinitely | **New:** timeout reclaims at 180 s as a safety net |
| Dynamic compute under load → goes quiet | Scale-down reclaims | Scale-down reclaims (unchanged) |
| Dynamic compute crashes/hangs | Timeout at 180 s | Timeout at 180 s (unchanged) |
| Static edge server / primary DB quiet period | Heartbeats keep flowing | Heartbeats keep flowing (unchanged) |

---

## 5. Config surface

| Variable | Scope | Default | Effect |
|---|---|---|---|
| `HEARTBEAT_ENABLED` | `edge_server`, `edge_storage_server` | `false` | When `true`, enables the heartbeat emitter for that container. Set explicitly on static containers via [build_network_1.sh](../../../source/scripts/network/build_network_1.sh) / [build_network_2.sh](../../../source/scripts/network/build_network_2.sh). Dynamic nodes keep the default disabled. |

`HEARTBEAT_INTERVAL_S`, `WINDOW_S`, and `TELEMETRY_TIMEOUT_WINDOWS` are unaffected.

---

## 6. Verification

1. **Build & smoke test.** Rebuild both images; run
   [source/scripts/build_network_setup.sh](../../../source/scripts/build_network_setup.sh);
   confirm static nodes still produce heartbeats on idle (aggregator logs).
2. **Dynamic idle path.** Force a scale-up, let load drop. Confirm via
   dynamic container logs that no `heartbeat` events are emitted. Confirm
   scale-down reclaims the node normally.
3. **Dynamic failure path.** Force a scale-up, then `docker kill` the
   dynamic node before scale-down fires. Confirm timeout-based cleanup at
   ~180 s.
4. **Static quiet period.** Stop traffic for >60 s. Confirm static nodes
   continue to appear in aggregator summaries with `request_count=0`.
5. **Unit tests** (if any exist for `init_telemetry` / `_push_stats`):
    add a test toggling `HEARTBEAT_ENABLED=false` and asserting no heartbeat
   events are produced. Leave existing tests unchanged.

---

## 7. Documentation updates

| File | Change |
|---|---|
| [docs/operation/telemetry/telemetry_overview.md](../telemetry/telemetry_overview.md) | In "Heartbeat Events", note that periodic heartbeats are disabled by default and enabled only via `HEARTBEAT_ENABLED=true` on static nodes. Add rationale. Add `HEARTBEAT_ENABLED` to the config table. |
| [docs/operation/elasticy_manager/elasticity_overview.md](../elasticy_manager/elasticity_overview.md) | In §Node Removal, clarify that on dynamic nodes the timeout is a *failure detector*, not an idleness detector — graceful removal is handled by the underutilisation scale-down path. Update the "~3 × `HEARTBEAT_INTERVAL_S`" annotation to note that dynamic nodes don't heartbeat; the 180 s window is the raw absence tolerance. |
| [docs/operation/system_mechanisms.md](../system_mechanisms.md) | Update the "Heartbeat events" paragraph (line ~238) and the "Idle" bullet (line ~636) to reflect static-only emission. Add a short "Liveness model" subsection summarising the static/dynamic asymmetry. |

---

## 8. Out of scope

- No change to `HEARTBEAT_INTERVAL_S`, `TELEMETRY_TIMEOUT_WINDOWS`, or `WINDOW_S` defaults.
- No changes to the aggregator event schema or Pydantic validators.
- No introduction of a `role` field in events (Approach B — rejected).
- No changes to the selective-storage image unless §3.5 inspection reveals a heartbeat emitter.
