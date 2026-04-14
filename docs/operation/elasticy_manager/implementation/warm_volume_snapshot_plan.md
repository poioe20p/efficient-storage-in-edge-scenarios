# Warm Volume Snapshot — Implementation Plan

> **Status:** Not Started
> **Date:** 2026-04-13
> **Depends on:** [Predictive Threshold & Async RS Join plan](predictive_threshold_and_async_rs_plan.md)
> (Phase 2 — async RS join via sidecar)
> **Motivation:** Even with the async RS join (predictive threshold plan),
> a fresh dynamic storage node must perform a **full initial sync** from the
> primary, which takes 20–30 s and pushes primary CPU to ~95 %.
> Pre-seeding the new node's `/data/db` with a recent snapshot eliminates
> the full sync — the node replays only the oplog delta (~1–3 s).

---

## TL;DR

Pre-populate dynamic storage node volumes with a recent WiredTiger snapshot
from the primary. Two components:

1. **Primary sidecar** (`mongo_telemetry.py`) — periodic background thread
   copies `/data/db` → `/warm` under `fsyncLock`.
2. **Controller** (`storage_node_manager.py`) — clones the warm volume into
   the new node's data volume inside `_docker_run_storage()`, after stale
   cleanup but before `docker run`.

Expected result: SECONDARY reaches `rs_secondary_ready` in **<15 s**
(was 34–45 s), primary CPU stays below 50 % during scale-up (was 94.9 %).

---

## Problem Summary

| Metric | Without warm vol | With warm vol |
|--------|------------------|---------------|
| Time to SECONDARY | 20–30 s (full initial sync) | ~1–3 s (oplog delta only) |
| Primary CPU during sync | ~95 % | < 50 % |
| Risk of RS join failure | High (primary overloaded) | Low |
| Network transfer | Full dataset | Oplog delta only |

The primary already has all the data locally. Snapshotting it periodically to
a warm volume is pure local I/O — zero network cost.

---

## Phase 1 — Primary Sidecar: Periodic Snapshot

### Concept

Add a **background daemon thread** to `mongo_telemetry.py` that runs on the
**primary** storage container only. Every `WARM_SNAPSHOT_INTERVAL_S` seconds
(default 300):

1. Check CPU — skip if above ceiling (default 70 %).
2. `db.fsyncLock()` — flushes all WiredTiger data and journal to disk,
   **blocks all write operations** until unlocked.
3. `cp -a /data/db/. /warm/` — copy the entire data directory.
4. Write `/warm/.snapshot_ts` with the current Unix timestamp — **written
   last** so its presence proves the copy is complete.
5. `db.fsyncUnlock()` — in a `finally` block; if the sidecar crashes,
   mongod auto-unlocks on next startup.

> **⚠ Write pause:** `fsyncLock` blocks client writes for the **entire
> duration of the copy** — typically **0.5–5 s** for 50–200 MB datasets
> (the typical edge storage size). This is NOT sub-second. The CPU ceiling
> check (70 %) ensures the snapshot only runs during relatively quiet periods.
> The 5-minute interval means this pause is rare.

### Crash safety

- If the sidecar dies mid-copy, mongod auto-unlocks `fsyncLock` on the
  next write or connection. Data files in `/data/db` are untouched.
- If the node restarts, the stale `/warm` directory may contain partial
  files. The controller checks `.snapshot_ts` freshness before cloning —
  a partial copy will either not have `.snapshot_ts` or will have a stale
  timestamp, triggering fallback to empty volume.

### Race condition: concurrent snapshot + clone

If the controller clones the warm volume while the sidecar starts a new
snapshot, the clone may contain a mix of old/new WiredTiger files.
Mitigations:

1. `.snapshot_ts` is written **last** — its presence + freshness proves the
   preceding copy was complete at that timestamp.
2. WiredTiger files are crash-consistent — journal replay handles mixed states.
3. The 5-minute interval makes overlap with a scale-up event unlikely.

Residual risk is acceptable; document in operational notes.

### Code — `mongo_telemetry.py`

#### New module-level imports and constants

```python
import shutil
import subprocess
import threading

WARM_SNAPSHOT_ENABLED    = os.environ.get("WARM_SNAPSHOT_ENABLED", "false").lower() == "true"
WARM_SNAPSHOT_INTERVAL_S = float(os.environ.get("WARM_SNAPSHOT_INTERVAL_S", "300"))
WARM_SNAPSHOT_CPU_CEIL   = float(os.environ.get("WARM_SNAPSHOT_CPU_CEILING", "70"))
WARM_SNAPSHOT_DIR        = os.environ.get("WARM_SNAPSHOT_DIR", "/warm")
```

> **Note:** `subprocess` is added at module level (currently not imported in
> `mongo_telemetry.py`). It is used by `_copy_data_dir()` for `cp -a`.

#### `_warm_snapshot_loop()` — background thread target

```python
def _warm_snapshot_loop() -> None:
    """Periodically snapshot /data/db → /warm for pre-seeding new nodes."""
    logger.info("[warm-snapshot] thread started (interval=%ds, cpu_ceiling=%.0f%%)",
                WARM_SNAPSHOT_INTERVAL_S, WARM_SNAPSHOT_CPU_CEIL)

    while True:
        time.sleep(WARM_SNAPSHOT_INTERVAL_S)

        # CPU check — use interval=0.5 for a meaningful reading in this thread
        cpu = psutil.cpu_percent(interval=0.5)
        if cpu > WARM_SNAPSHOT_CPU_CEIL:
            logger.debug("[warm-snapshot] skipping — CPU %.1f%% > ceiling %.0f%%",
                         cpu, WARM_SNAPSHOT_CPU_CEIL)
            continue

        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
        try:
            t0 = time.perf_counter()
            # fsyncLock blocks ALL writes until unlock
            client.admin.command("fsync", lock=True)
            try:
                _copy_data_dir()
            finally:
                client.admin.command("fsyncUnlock")
            elapsed = time.perf_counter() - t0
            logger.info("[warm-snapshot] copy complete in %.1fs (cpu was %.1f%%)",
                        elapsed, cpu)
        except PyMongoError as exc:
            logger.warning("[warm-snapshot] failed: %s", exc)
        finally:
            client.close()


def _copy_data_dir() -> None:
    """Copy /data/db → WARM_SNAPSHOT_DIR, then write the timestamp marker."""
    src = "/data/db"
    dst = WARM_SNAPSHOT_DIR

    # Remove old snapshot contents but keep the mount point
    for entry in os.listdir(dst):
        path = os.path.join(dst, entry)
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)

    # Copy data files — cp -a preserves timestamps, permissions, symlinks
    subprocess.run(["cp", "-a", f"{src}/.", dst], check=True, timeout=60)

    # Timestamp marker LAST — proves the copy is complete
    ts_path = os.path.join(dst, ".snapshot_ts")
    with open(ts_path, "w") as f:
        f.write(str(time.time()))
```

#### Updated `main()` — start snapshot thread (primary only)

> **Prerequisite:** The snippet below shows `main()` in its **merged** state
> — i.e. *after* the predictive threshold plan's `_rs_self_join()` has been
> implemented. If this plan is implemented first, omit the `RS_ADD_SELF` block
> and use the current `main()` as the base.

```python
def main() -> None:
    global _sock

    logger.info("mongo_telemetry starting: mac=%s interval=%.1fs",
                _get_server_mac(), INTERVAL_S)

    # (From predictive threshold plan — not yet implemented)
    # Async RS self-join if configured
    if os.environ.get("RS_ADD_SELF") == "true":
        _rs_self_join()   # blocks until network ready + RS joined

    state_str = _wait_for_ready()

    # Now eth0 exists — create ZMQ socket
    _sock = _ctx.socket(zmq.PUSH)
    _sock.connect(AGGREGATOR_PULL_ADDR)
    logger.info("ZMQ PUSH socket connected to %s", AGGREGATOR_PULL_ADDR)

    # Warm snapshot thread — only on the PRIMARY
    if WARM_SNAPSHOT_ENABLED and state_str == "PRIMARY":
        t = threading.Thread(target=_warm_snapshot_loop,
                             name="warm-snapshot", daemon=True)
        t.start()
        logger.info("[warm-snapshot] enabled on PRIMARY")

    # (Remaining main() body unchanged — rs_secondary_ready, telemetry loop)
    ...
```

> **⚠ Known limitation — role changes:** The snapshot thread starts only if
> `_wait_for_ready()` returns `"PRIMARY"` at boot. If the primary steps down
> (election/failover), the thread continues running on a non-primary — the
> `fsyncLock` call will still succeed (it's a server-level command) but the
> snapshot may be stale by the time a scale-up occurs on the new primary.
> Conversely, a promoted SECONDARY will never start the thread. This is
> acceptable for single-primary edge deployments where role changes are rare.
> A future improvement could poll `rs.status()` periodically and start/stop
> the thread accordingly.

---

## Phase 2 — Controller: Consume Warm Volume on Scale-Up

### Concept

Before `docker run`, check if a fresh warm volume exists for this LAN.
If so, clone it into the new node's data volume. The new mongod starts with
pre-seeded WiredTiger files and only replays the oplog delta.

### `_acquire_warm_volume()` — new method on `StorageNodeAdder`

**File:** `source/sdn_controller/elasticity/storage_node_manager.py`
**Class:** `StorageNodeAdder` (alongside `_docker_run_storage`, `_find_rs_primary`, etc.)

```python
# Module-level constant (top of file, after existing imports)
import os   # NEW — not currently imported in storage_node_manager.py

_WARM_VOLUME_MAX_AGE_S = float(os.environ.get("WARM_VOLUME_MAX_AGE_S", "600"))


# Inside class StorageNodeAdder:
def _acquire_warm_volume(self, lan: int, target_vol: str) -> bool:
    """Clone the warm snapshot volume into *target_vol*.

    Returns True if the clone succeeded, False on any failure (the caller
    should proceed with an empty volume — current behaviour).
    """
    warm_vol = f"rs_net{lan}_warm"

    # 1. Read .snapshot_ts from the warm volume via a throwaway container.
    #    We use the edge_storage_server image (already available) to avoid
    #    pulling a new image like busybox.
    try:
        result = subprocess.run(
            ["docker", "run", "--rm",
             "-v", f"{warm_vol}:/src:ro",
             "edge_storage_server",
             "cat", "/src/.snapshot_ts"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            logger.info("[warm-vol] no .snapshot_ts in %s — fallback to empty volume",
                        warm_vol)
            return False
    except (subprocess.SubprocessError, OSError):
        logger.info("[warm-vol] could not read %s — fallback to empty volume", warm_vol)
        return False

    # 2. Check freshness
    try:
        snapshot_ts = float(result.stdout.strip())
    except ValueError:
        logger.warning("[warm-vol] invalid .snapshot_ts content: %r", result.stdout.strip())
        return False

    age = time.time() - snapshot_ts
    if age > _WARM_VOLUME_MAX_AGE_S:
        logger.info("[warm-vol] snapshot age %.0fs > max %.0fs — fallback to empty volume",
                    age, _WARM_VOLUME_MAX_AGE_S)
        return False

    # 3. Clone warm → target.  Mount warm as /src (read-only) and target as /dst.
    logger.info("[warm-vol] cloning %s → %s (age=%.0fs)", warm_vol, target_vol, age)
    t0 = time.perf_counter()
    try:
        result = subprocess.run(
            ["docker", "run", "--rm",
             "-v", f"{warm_vol}:/src:ro",
             "-v", f"{target_vol}:/dst",
             "edge_storage_server",
             "sh", "-c", "cp -a /src/. /dst/"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            logger.warning("[warm-vol] clone failed: %s", result.stderr.strip())
            return False
    except (subprocess.SubprocessError, OSError) as exc:
        logger.warning("[warm-vol] clone failed: %s", exc)
        return False

    elapsed = time.perf_counter() - t0
    logger.info("[warm-vol] clone complete in %.1fs", elapsed)
    return True
```

> **Image choice:** Uses `edge_storage_server` (Ubuntu-based, already built
> and available) instead of `busybox` to avoid introducing a new image
> dependency. The extra overhead (~0.2 s startup) is negligible compared to
> the 20–30 s saved by skipping initial sync.

### Updated `_docker_run_storage()` — warm clone between cleanup and run

> **⚠ Critical ordering:** The warm clone **cannot** be a separate "step 0"
> before `_docker_run_storage()`. The current code calls
> `_cleanup_container(name)` inside `_docker_run_storage()` if a stale
> container exists — that cleanup removes `{name}-data` via
> `docker volume rm`. If the warm clone happened *before* this call, the
> pre-seeded volume would be destroyed.
>
> **Solution:** Integrate the warm clone into `_docker_run_storage()` itself,
> **after** stale cleanup but **before** `docker run`.

```python
def _docker_run_storage(
    self, name: str, rs_name: str, port: int, lan: int,
) -> tuple[bool, str, str]:
    state = self._container_state(name)
    if state == "running":
        logger.info("[node_add] container %s already running — skipping docker run", name)
        return True, "", ""
    if state is not None:
        # Container exists in a non-running state — clean up stale remnants
        logger.info("[node_add] removing stale container %s (state=%s)", name, state)
        self._cleanup_container(name)   # removes {name}-data volume too
    # else: container doesn't exist — nothing to clean up

    # ── Warm-volume pre-seed (after stale cleanup, before docker run) ─
    vol = f"{name}-data"
    warm_ok = self._acquire_warm_volume(lan, vol)
    if warm_ok:
        logger.info("[node_add] step=warm_vol container=%s pre-seeded from warm snapshot", name)
    else:
        logger.info("[node_add] step=warm_vol container=%s using empty volume", name)

    cmd = [
        "docker", "run", "-dit",
        "--network", "none",
        "--name", name,
        "-v", f"{vol}:/data/db",
        "-e", f"LAN_ID=lan{lan}",
        "-e", f"MONGO_REPLSET={rs_name}",
        "-e", f"MONGO_PORT={port}",
        "-e", f"CONTAINER_NAME={name}",
        "edge_storage_server",
    ]
    return self._run_cmd(cmd)
```

`add_storage_node()` itself is **unchanged** — it calls
`_docker_run_storage()` which now handles warm cloning internally.

Docker auto-creates named volumes on first use. If `_acquire_warm_volume()`
succeeds, the volume already exists with pre-seeded data. `docker run -v
{name}-data:/data/db` mounts the existing volume. If it fails, Docker
creates a fresh empty volume as before.

---

## Phase 3 — Build Script Changes

### `build_network_1.sh` — add warm volume mount + env var

```bash
echo "Starting edge_storage_server_n1 container..."
docker run -dit --name edge_storage_server_n1 --network none \
  --no-healthcheck \
  -e LAN_ID=lan1 \
  -e AGGREGATOR_PULL_ADDR=tcp://10.0.0.5:5555 \
  -e MONGO_REPLSET=rs_net1 \
  -e MONGO_PORT=27018 \
  -e TELEMETRY_INTERVAL_S=10 \
  -e LOG_LEVEL=INFO \
  -e WARM_SNAPSHOT_ENABLED=true \
  -v edge_storage_server_n1-data:/data/db \
  -v rs_net1_warm:/warm \
  edge_storage_server
```

New lines: `-e WARM_SNAPSHOT_ENABLED=true` and `-v rs_net1_warm:/warm`.

### `build_network_2.sh` — same for n2

```bash
docker run -dit --name edge_storage_server_n2 --network none \
  --no-healthcheck \
  -e LAN_ID=lan2 \
  -e AGGREGATOR_PULL_ADDR=tcp://10.0.1.5:5555 \
  -e MONGO_REPLSET=rs_net2 \
  -e MONGO_PORT=27018 \
  -e TELEMETRY_INTERVAL_S=10 \
  -e LOG_LEVEL=INFO \
  -e WARM_SNAPSHOT_ENABLED=true \
  -v edge_storage_server_n2-data:/data/db \
  -v rs_net2_warm:/warm \
  edge_storage_server
```

### `cleanup.sh` — add warm volumes to cleanup

The existing `volumes_cleanup()` function **and** `reset_cleanup()` both
maintain independent volume lists. Warm volumes must be added to **both**:

#### `volumes_cleanup()` (line ~277)

```bash
# Base node volumes
local volumes=(
    edge_storage_server_n1-data
    edge_storage_server_n2-data
    rs_net1_warm
    rs_net2_warm
)
```

#### `reset_cleanup()` (line ~336)

```bash
# Base node volumes
local volumes=(
    edge_storage_server_n1-data
    edge_storage_server_n2-data
    rs_net1_warm
    rs_net2_warm
)
```

> **Why two lists?** `volumes_cleanup()` is called by `--volumes` flag for
> selective cleanup. `reset_cleanup()` is called by `--reset` for a full
> teardown. They share the same volume names but operate in different modes
> (the latter also removes all containers force-first).

---

## Phase 4 — Documentation

Update `elasticity_overview.md` with a "Warm Volume Snapshot" architecture
section.

---

## New Environment Variables

| Variable | Where | Default | Description |
|----------|-------|---------|-------------|
| `WARM_SNAPSHOT_ENABLED` | Primary sidecar | `false` | Enable periodic warm snapshot |
| `WARM_SNAPSHOT_INTERVAL_S` | Primary sidecar | `300` | Seconds between snapshots |
| `WARM_SNAPSHOT_CPU_CEILING` | Primary sidecar | `70` | Skip snapshot if CPU% exceeds |
| `WARM_SNAPSHOT_DIR` | Primary sidecar | `/warm` | Mount point for warm volume |
| `WARM_VOLUME_MAX_AGE_S` | Controller | `600` | Max snapshot age before fallback |

---

## Files Modified (Summary)

| File | Phase | Change |
|------|-------|--------|
| `source/docker/edge_storage_server/mongo_telemetry.py` | 1 | `_warm_snapshot_loop()`, `_copy_data_dir()`, thread start in `main()`, new env var reads |
| `source/sdn_controller/elasticity/storage_node_manager.py` | 2 | `_acquire_warm_volume()` method, warm clone in `_docker_run_storage()` |
| `source/scripts/network/build_network_1.sh` | 3 | `-e WARM_SNAPSHOT_ENABLED=true`, `-v rs_net1_warm:/warm` |
| `source/scripts/network/build_network_2.sh` | 3 | Same for n2 |
| `source/scripts/cleanup.sh` | 3 | Add `rs_net1_warm`, `rs_net2_warm` to volume list |
| `docs/operation/elasticy_manager/elasticity_overview.md` | 4 | New warm snapshot architecture section |

---

## Interaction with Other Plans

| Plan | Interaction |
|------|-------------|
| **Predictive threshold** (Phase 0) | Independent — earlier detection + warm vol = even faster response |
| **Async RS join** (Phase 2) | Complementary — warm vol reduces oplog replay from ~20 s to ~1–3 s; together, controller returns in ~5–12 s, SECONDARY ready in ~10–15 s |
| **Priority queue** (Phase 1) | Independent |

---

## Decisions

- Snapshot runs **in the primary sidecar** (`mongo_telemetry.py`), not the
  controller — data is local, zero network cost.
- Uses `fsyncLock`/`fsyncUnlock` + file copy (not `mongodump`) — produces raw
  WiredTiger files that mongod resumes replication from without full initial
  sync.
- One warm volume per LAN (`rs_net1_warm`, `rs_net2_warm`) — not a pool; a
  single snapshot suffices since concurrent scale-ups share the same snapshot
  baseline.
- Fallback is transparent — if the warm volume is missing, stale, or the clone
  fails, the system behaves exactly as today (full initial sync via oplog).
- Uses `edge_storage_server` image for volume cloning (already built) instead
  of `busybox` to avoid new image dependencies.
- `psutil.cpu_percent(interval=0.5)` used in the snapshot thread to get a
  meaningful CPU reading (not `interval=None` which returns 0.0 on first call
  in a new thread).
- **Dynamic nodes intentionally skip warm snapshot:** `_docker_run_storage()`
  does NOT pass `WARM_SNAPSHOT_ENABLED` or mount a warm volume for dynamic
  nodes. Only the primary (started by `build_network_*.sh`) runs the snapshot
  thread. Dynamic nodes are consumers, not producers, of warm snapshots.
- **Primary role detected once at startup:** The snapshot thread starts only
  if `_wait_for_ready()` returns `"PRIMARY"`. Role changes (step-down,
  promotion) are not tracked. Acceptable for single-primary edge deployments.

---

## Verification

1. Wait >5 min after start, check primary logs for
   `[warm-snapshot] copy complete in X.Xs`.
2. `docker volume inspect rs_net1_warm` — volume exists with data.
3. Trigger storage scale-up — controller logs
   `[warm-vol] cloned rs_net1_warm → {name}-data`.
4. New SECONDARY reaches `rs_secondary_ready` in <15 s (was 34–45 s).
5. Primary CPU stays <50 % during scale-up (was 94.9 %).
6. **Stale test:** set `WARM_VOLUME_MAX_AGE_S=1`, wait, scale-up →
   fallback to empty volume logged.
7. **CPU ceiling test:** load primary >70 %, verify snapshot skips with
   `[warm-snapshot] skipping — CPU X% > ceiling 70%`.
8. **Crash safety:** kill sidecar mid-copy, verify mongod auto-unlocks,
   next snapshot succeeds.
9. **Concurrent access:** trigger scale-up during snapshot — clone should
   still succeed (WiredTiger recovery handles mixed states).

---

## Review Notes

### Round 1 (2026-04-13 — agent review)

Issues found during initial plan review, with resolutions applied above:

| # | Severity | Issue | Resolution |
|---|----------|-------|------------|
| 1 | Medium | `fsyncLock` write pause understated as "sub-second" | Documented actual duration: 0.5–5 s for the copy under lock |
| 2 | Medium | Race condition: concurrent snapshot + clone | `.snapshot_ts` written last; WiredTiger handles crash-consistent states; documented residual risk |
| 3 | Low | `busybox` image not available in project | Use `edge_storage_server` image (already built) for volume cloning |
| 4 | Low | `psutil.cpu_percent(interval=None)` returns 0.0 on first call in new thread | Use `interval=0.5` for meaningful CPU reading |
| 5 | Low | Warm volume naming convention (`rs_net1_warm`) differs from data volumes (`-data` suffix) | Acceptable — warm volumes are an RS-level concept, not per-container |

### Round 2 (2026-04-13 — user codebase audit)

| # | Severity | Issue | Resolution |
|---|----------|-------|------------|
| 1 | **Critical** | `_cleanup_container()` in step 1 deletes the warm-cloned volume from step 0 — ordering was wrong | Moved warm clone into `_docker_run_storage()`, between stale cleanup and `docker run`. `add_storage_node()` unchanged. |
| 2 | **Critical** | `_rs_self_join()` referenced as "existing" but not yet implemented (it's in the predictive threshold plan) | Added prerequisite note; snippet now explicitly marked as **merged** state; standalone fallback documented |
| 3 | Medium | `reset_cleanup()` has a separate volume list not updated by plan | Added `reset_cleanup()` volume list update alongside `volumes_cleanup()`, with explanation of why two lists exist |
| 4 | Medium | Unused `import json` in Phase 2 code | Removed |
| 5 | Medium | Primary role detected once at startup — role changes unhandled | Documented as known limitation in `main()` section and Decisions; future improvement noted |
| 6 | Low | `_acquire_warm_volume()` class placement ambiguous | Heading and context updated to specify `StorageNodeAdder` class |
| 7 | Low | `subprocess` not in module-level imports for `mongo_telemetry.py` | Added to module-level imports block; removed inline `import subprocess` from `_copy_data_dir()` |
| 8 | Low | Type annotations missing from plan's `add_storage_node()` snippet | N/A — `add_storage_node()` is no longer shown as a modified snippet (warm clone moved into `_docker_run_storage()`) |
| 9 | Low | No explicit note that dynamic nodes intentionally skip warm snapshot | Added to Decisions section |
| 10 | Medium | Missing `import os` in `storage_node_manager.py` — `os.environ.get()` used for `_WARM_VOLUME_MAX_AGE_S` | Added `import os` to module-level snippet |
