# Plan — Warm Volume Snapshot + Controller-Assisted Primary Handoff for Tier 2

**Status:** Proposed
**Scope:** Tier 2 storage scale-up only
**Decision:** Keep current Tier 2 semantics and speed up the existing path with four concrete changes:

1. Let the static primary storage node maintain an optional warm snapshot volume.
2. Copy that snapshot into the new dynamic storage volume only when a dynamic node is actually being added.
3. Pass controller-known primary and node-identity information into the dynamic storage container: `RS_PRIMARY_HOST`, `OWN_IP`, `OWN_MAC`, and `IFACE=eth0`.
4. Keep the current network-ready wait and ready-notification path, but demote in-container identity discovery to fallback-only behavior.

This plan is intentionally narrower than the earlier Option 1 sketch. It does **not** include broad timing instrumentation, controller-performed `replSetReconfig`, any separate optimization of the `rs_secondary_ready` notification path, or any change to the rule that a Tier 2 node serves only after it reaches `SECONDARY`.

---

## 1. Problem Statement

The current Tier 2 add path already keeps serving semantics correct:

- Thread 3 starts the dynamic storage container in
  [storage_node_manager.py](../../../../source/sdn_controller/elasticity/storage_node_manager.py).
- The MongoDB sidecar inside the container performs async self-join in
  [mongo_telemetry.py](../../../../source/docker/edge_storage_server/mongo_telemetry.py).
- The controller adds the node to the VIP storage pool only after the sidecar emits
  `rs_secondary_ready`, as handled in
  [control_events.py](../../../../source/sdn_controller/control_events.py).

That correctness model should stay unchanged.

What is slow today is the path to that ready state:

1. A fresh dynamic node starts with an empty volume and usually performs a full initial sync.
2. The sidecar currently uses `RS_SEED_HOST` as a generic entry point, then runs `isMaster` to discover the current primary before it can `replSetReconfig` itself into the set.
3. The join path is robust, but it does more work than necessary when the controller already has enough information to narrow the first connection attempt.
4. The sidecar currently discovers its own IP and MAC inside the container, even though the controller already knows both values before `docker run`.

The approved optimization is therefore:

- remove the large data-copy cost with a warm snapshot,
- remove the avoidable primary-discovery step on the fast path, and
- remove avoidable identity discovery inside the dynamic storage container.

---

## 2. Explicit Non-Goals

The following are out of scope for this plan:

- broad Tier 2 timing instrumentation across every intermediate stage
- moving replica-set reconfiguration logic from the container sidecar into the controller
- introducing a new direct ready-notification channel that bypasses the current aggregator mini-summary fast path
- serving from a Tier 2 node before `SECONDARY`
- changing storage scale-up thresholds, windows, cooldowns, or caps
- introducing cross-LAN Tier 2 behavior
- changing Tier 1 behavior or the Tier 1 to Tier 2 supersede hook

Those topics can be revisited later, but they are not required to make the current Tier 2 path materially faster.

---

## 3. Approaches Considered

| # | Approach | Description | Pros | Cons | Effort | Risk |
| --- | --- | --- | --- | --- | --- | --- |
| **A** | **Warm snapshot + controller-assisted primary and identity handoff** | Pre-seed the volume from a warm snapshot and let the sidecar use controller-provided `RS_PRIMARY_HOST`, `OWN_IP`, and `OWN_MAC` directly first, with fallback to the current discovery path. | Attacks the dominant full-sync cost and removes avoidable join-path discovery work; preserves current readiness semantics; minimal architectural change. | Still leaves RS join ownership in the sidecar; requires warm-volume lifecycle management. | Medium | Medium |
| **B** | **Warm snapshot only** | Add the snapshot path but leave the current seed-first join flow untouched. | Largest single performance gain with the smallest behavior change. | Leaves avoidable discovery and retry overhead on the fast path. | Medium | Low |
| **C** | **Warm snapshot + controller-performed RS join** | Pre-seed the volume and move `replSetReconfig` into the controller after network attach. | Removes most join logic from the container. | Larger refactor; changes ownership boundaries between controller and sidecar; more failure-path complexity. | High | Medium to High |

**Recommended:** Approach A.

Approach A is the smallest change set that addresses the concrete bottlenecks without changing who admits the node into service. Approach B is a useful fallback if the controller-assisted handoff proves not to matter enough. Approach C is not justified yet.

---

## 4. Current Code Path and Concrete Bottlenecks

The current storage scale-up path is split across the controller and the sidecar.

| Stage | Current owner | Current code | Current behavior | Candidate improvement |
| --- | --- | --- | --- | --- |
| Scale-up alert creation | Thread 2 controller | [scaling_policy.py](../../../../source/sdn_controller/scaling_policy.py) | Builds `DataAlert` with `rs_name` and `primary_container`, but not the current `primary_host`. | Enrich the alert later in `main_n*.py` using the current telemetry window. |
| Dynamic container spawn | Thread 3 controller | [storage_node_manager.py](../../../../source/sdn_controller/elasticity/storage_node_manager.py) | Starts with a fresh named volume every time. | Copy from a usable warm snapshot volume when a dynamic node is actually being added. |
| Network attach | Thread 3 + shell script | [add_network_node.sh](../../../../source/scripts/network/add_network_node.sh) | Works today; no semantic change needed. | No change in this plan. |
| Primary discovery | Sidecar | [mongo_telemetry.py](../../../../source/docker/edge_storage_server/mongo_telemetry.py) | Connects to `RS_SEED_HOST`, runs `isMaster`, then reconnects to the actual primary. | Try `RS_PRIMARY_HOST` directly first; keep the seed path as fallback. |
| Node identity discovery | Sidecar | [mongo_telemetry.py](../../../../source/docker/edge_storage_server/mongo_telemetry.py) | Discovers own IP and MAC from the container namespace. | Pass `OWN_IP`, `OWN_MAC`, and `IFACE=eth0` from the controller; keep discovery as fallback only. |
| RS join | Sidecar | [mongo_telemetry.py](../../../../source/docker/edge_storage_server/mongo_telemetry.py) | `replSetReconfig` appends this node as `priority: 0, votes: 0`. | Keep this logic in the sidecar. |
| Ready-state gating | Sidecar + Thread 2 controller | [mongo_telemetry.py](../../../../source/docker/edge_storage_server/mongo_telemetry.py), [control_events.py](../../../../source/sdn_controller/control_events.py) | Waits for `SECONDARY`, emits `rs_secondary_ready`, controller then promotes backend. | Keep unchanged; no separate notification optimization in this plan. |

The large cost is the empty-volume full sync. The other concrete waste visible in the current code is the sidecar's mandatory seed-to-primary discovery round plus avoidable identity discovery inside the dynamic container.

---

## 5. Approved Design

### 5.1 Keep the current serve-after-`SECONDARY` semantics

No part of this plan changes the admission rule:

- the storage node is still not placed in the VIP storage pool during `add_storage_node()`;
- the node is still promoted only after `rs_secondary_ready` or telemetry fallback detects `member_state == "SECONDARY"`;
- the dynamic node remains a real replica-set member, not a cache or pre-join stale reader.

That behavior is already documented in
[elasticity_overview.md](../elasticity_overview.md) and implemented in
[control_events.py](../../../../source/sdn_controller/control_events.py).

### 5.2 Add a direct-primary fast path, but keep the current seed fallback

The controller should pass the current primary host into the storage add path whenever it can resolve one from the current telemetry window and MAC-to-IP map. The sidecar should then try that host directly before falling back to the current seed-discovery flow.

This means:

- no behavior change when the direct host is stale or missing;
- no behavior change when an election occurs between alert creation and sidecar join;
- less unnecessary work when the controller's current primary view is correct.

### 5.3 Add warm snapshot pre-seeding, but treat age as advisory in phase 1

The primary storage container for each LAN should maintain an optional warm snapshot under a separate named volume. When a dynamic storage node is created, the controller should copy that snapshot into the new node's data volume if and only if the snapshot exists, is marked complete, and belongs to the expected replica set.

Snapshot age should still be inspected and logged, but in phase 1 it should be treated as **advisory**, not as a hard reject. A valid but stale snapshot is still likely to be better than an empty volume because it shrinks the remaining catch-up work.

If the snapshot is absent, corrupt, incomplete, from the wrong replica set, or the copy fails, the system must fall back to the current empty-volume behavior automatically.

### 5.4 Pass controller-known node identity into the dynamic storage container

The controller already knows the IP and MAC assigned to a dynamic storage node before the container completes its join path. That information should be passed in at `docker run` time:

- `OWN_IP`
- `OWN_MAC`
- `IFACE=eth0`

The sidecar should use those values directly first and only fall back to `_discover_own_ip()` / `_discover_mac()` if the environment is missing or invalid.

This does **not** remove the need to wait for actual network readiness. The interface and route still need to exist before the node can join the replica set. It only removes unnecessary discovery work inside the container.

### 5.5 Keep the current ready-notification path unchanged

The current `rs_secondary_ready` path is already fast enough for this phase:

- the sidecar emits `rs_secondary_ready` immediately after `_wait_for_ready()` succeeds,
- the aggregator forwards control events immediately as a mini-summary,
- Thread 2 processes the mini-summary without waiting for a full telemetry window.

This plan therefore does **not** introduce a separate direct controller channel, controller-side readiness probing, or a dedicated notification optimization.

---

## 6. File-by-File Plan

### 6.1 [elasticity.py](../../../../source/sdn_controller/elasticity/elasticity.py)

Extend `DataAlert` with an optional `primary_host` field. The scaling policy can keep returning the same alert shape it returns today; the controller entry point will enrich it before submission.

```python
@dataclass(frozen=True)
class DataAlert:
    lan: int
    network_id: str
    rs_name: str
    primary_container: str
    primary_host: str | None = None
    port: int = 27018
    cross_lan_rs: bool = False
    owner_lan: str | None = None
```

This keeps `ScalingPolicy` pure and avoids leaking topology or telemetry concerns into the score-based decision engine.

---

### 6.2 [main_n1.py](../../../../source/sdn_controller/main_n1.py) and [main_n2.py](../../../../source/sdn_controller/main_n2.py)

Enrich `DataAlert` with the current local primary host before submission to the elasticity manager.

The controllers already have all required inputs in `_on_telemetry_update(...)`:

- the current `TelemetrySummary`, including `summary.storage_servers`
- the current MAC-to-IP map via `self._mac_to_ip`
- the LAN number and the MongoDB port

Concrete helper:

```python
def _resolve_local_primary_host(
    self,
    summary: TelemetrySummary,
    lan: int,
    port: int,
) -> str:
    for mac, stats in summary.storage_servers.items():
        if stats.member_state == "PRIMARY":
            ip = self._mac_to_ip.get(mac)
            if ip:
                return f"{ip}:{port}"

    return f"10.0.{lan - 1}.4:{port}"
```

Concrete enrichment point inside `_on_telemetry_update(...)`:

```python
for alert in self._scaling_policy.evaluate_scale_up(
    ds,
    lan,
    summary.network_id,
    dynamic_storage_count,
    dynamic_compute_count,
    peer_ds,
    allow_compute=not compute_blocked,
    allow_storage=not storage_blocked,
):
    if isinstance(alert, DataAlert):
        alert = DataAlert(
            lan=alert.lan,
            network_id=alert.network_id,
            rs_name=alert.rs_name,
            primary_container=alert.primary_container,
            primary_host=self._resolve_local_primary_host(summary, lan, alert.port),
            port=alert.port,
            cross_lan_rs=alert.cross_lan_rs,
            owner_lan=alert.owner_lan,
        )
    self._elasticity.submit(alert)
```

Why enrich here instead of in `scaling_policy.py`:

- `scaling_policy.py` currently depends only on `DomainSummary` and counters, not live topology state;
- `main_n*.py` already acts as the Thread 2 mediator for control-event processing and alert submission;
- the controller entry point sees the freshest local primary information available at submission time.

---

### 6.3 [storage_node_manager.py](../../../../source/sdn_controller/elasticity/storage_node_manager.py)

Use the enriched `primary_host` when spawning the dynamic storage container instead of always deriving `10.0.{lan-1}.4:{port}` locally.

Concrete signature change:

```python
def add_storage_node(
    self,
    lan: int,
    name: str,
    rs_name: str,
    port: int = 27018,
    primary_host: str | None = None,
    ip: str | None = None,
    mac: str | None = None,
) -> NodeResult:
```

Concrete host selection:

```python
join_host = primary_host or f"10.0.{lan - 1}.4:{port}"
logger.info("[node_add] join host for lan%d: %s", lan, join_host)
```

Concrete environment injection in `_docker_run_storage(...)`:

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
    "-e", f"OWN_IP={ip}",
    "-e", f"OWN_MAC={mac}",
    "-e", "IFACE=eth0",
    "-e", "RS_ADD_SELF=true",
    "-e", f"RS_PRIMARY_HOST={join_host}",
    "-e", f"RS_SEED_HOST={join_host}",
]
```

Passing both join variables keeps the existing `RS_SEED_HOST` contract valid while introducing a clearer direct-primary fast path. Passing `OWN_IP` and `OWN_MAC` lets the sidecar skip avoidable identity discovery in the common case.

The current shell-script contract does not need to change for this plan. [add_network_node.sh](../../../../source/scripts/network/add_network_node.sh) already uses `eth0` by default and only emits `RESULT_IP` / `RESULT_MAC`. No `RESULT_IFACE` output is required.

This file also owns warm snapshot acquisition before `docker run`.

Concrete pre-seed step:

```python
vol = f"{name}-data"
used_warm_snapshot = self._acquire_warm_volume(lan, rs_name, vol)

logger.info(
    "[node_add] storage volume prepared container=%s warm_snapshot=%s",
    name,
    used_warm_snapshot,
)
```

Concrete acquisition helper:

```python
def _acquire_warm_volume(self, lan: int, rs_name: str, target_volume: str) -> bool:
    source_volume = f"rs_net{lan}_warm"

    helper = textwrap.dedent(f"""
        import json, os, shutil, sys, time

        meta_path = "/warm/meta.json"
        data_dir = "/warm/data"

        if not os.path.exists(meta_path) or not os.path.isdir(data_dir):
            sys.exit(10)

        with open(meta_path, encoding="utf-8") as fh:
            meta = json.load(fh)

        if meta.get("complete") is not True:
            sys.exit(11)
        if meta.get("rs_name") != {rs_name!r}:
            sys.exit(12)

        age_s = time.time() - float(meta.get("created_ts", 0.0))
        stale = age_s > float({600.0!r})
        print(json.dumps({{"age_s": age_s, "stale": stale}}))

        shutil.copytree(data_dir, "/data/db", dirs_exist_ok=True)
    """).strip()

    ok, stdout, stderr = self._run_cmd([
        "docker", "run", "--rm",
        "--entrypoint", "python3",
        "-v", f"{source_volume}:/warm:ro",
        "-v", f"{target_volume}:/data/db",
        "edge_storage_server",
        "-c", helper,
    ])
    if ok and stdout.strip():
        logger.info("[node_add] warm snapshot metadata volume=%s %s", source_volume, stdout.strip())
    else:
        logger.info("[node_add] warm snapshot not used volume=%s stderr=%s", source_volume, stderr.strip())
    return ok
```

This collapses metadata inspection and the copy into one helper run. The important behavior is:

- missing, corrupt, incomplete, or wrong-RS snapshots are rejected,
- age is logged and classified as stale or not,
- valid stale snapshots are still copied in phase 1,
- any failure falls back to the current cold path.

---

### 6.4 [mongo_telemetry.py](../../../../source/docker/edge_storage_server/mongo_telemetry.py)

#### 6.4.1 Direct-primary join path with fallback

Today `_rs_self_join()` always starts from `RS_SEED_HOST`, waits for network reachability, runs `isMaster`, and then reconnects to the primary. The new flow should try `RS_PRIMARY_HOST` first and fall back to the current discovery path when needed.

Concrete shape:

```python
def _rs_self_join() -> None:
    primary_host = os.environ.get("RS_PRIMARY_HOST", "").strip()
    seed_host = os.environ.get("RS_SEED_HOST", "").strip()
    port = int(os.environ.get("MONGO_PORT", "27018"))

    target_host = primary_host or seed_host
    if not target_host:
        logger.warning("RS_ADD_SELF=true but no join host was provided")
        return

    target_ip, target_port = _split_host_port(target_host, port)
    if not _wait_for_network(target_ip, target_port):
        logger.error("Network never became available — cannot self-join RS")
        return

    own_ip = _discover_own_ip()
    if not own_ip:
        logger.error("Could not discover own IP — cannot self-join RS")
        return

    member_host = f"{own_ip}:{port}"

    if primary_host and _try_reconfig_against_primary(primary_host, member_host):
        return

    if seed_host and _discover_and_join_from_seed(seed_host, member_host):
        return

    logger.error("RS self-join failed through both direct and fallback paths")
```

Concrete direct-primary helper:

```python
def _try_reconfig_against_primary(primary_host: str, member_host: str) -> bool:
    try:
        client = MongoClient(
            f"mongodb://{primary_host}/",
            serverSelectionTimeoutMS=3000,
            directConnection=True,
        )
        try:
            config = client.admin.command("replSetGetConfig")["config"]
            config["members"] = [
                m for m in config["members"]
                if m.get("host") != member_host
            ]
            max_id = max(m["_id"] for m in config["members"])
            config["version"] += 1
            config["members"].append({
                "_id": max_id + 1,
                "host": member_host,
                "priority": 0,
                "votes": 0,
            })
            client.admin.command("replSetReconfig", config)
            logger.info("RS join succeeded via direct primary %s", primary_host)
            return True
        finally:
            client.close()
    except PyMongoError as exc:
        logger.warning("Direct primary join failed via %s: %s", primary_host, exc)
        return False
```

Concrete fallback split:

```python
def _discover_and_join_from_seed(seed_host: str, member_host: str) -> bool:
    # Keep the current isMaster -> primary_host -> replSetReconfig flow here.
    ...
```

This keeps the current robust behavior intact while removing unnecessary primary discovery when the controller has already supplied the correct host.

The same file should use controller-provided identity values first:

```python
SERVER_MAC = os.environ.get("OWN_MAC", "").strip() or _discover_mac()
IFACE = os.environ.get("IFACE", "eth0").strip() or "eth0"

def _discover_own_ip() -> str:
    configured_ip = os.environ.get("OWN_IP", "").strip()
    if configured_ip:
        return configured_ip

    try:
        result = subprocess.run(
            ["ip", "-4", "-o", "addr", "show", IFACE],
            capture_output=True, text=True, timeout=5,
        )
        for part in result.stdout.split():
            if "/" in part and "." in part:
                return part.split("/")[0]
    except Exception:
        pass
    return ""
```

This keeps the current network wait but removes unnecessary identity discovery in the common case.

#### 6.4.2 Warm snapshot producer loop

The static primary storage containers should optionally maintain the warm snapshot from the same sidecar process. This is a storage-side periodic task, not a controller thread.

Concrete configuration surface:

```python
WARM_SNAPSHOT_ENABLED = (
    os.environ.get("WARM_SNAPSHOT_ENABLED", "false").strip().lower() == "true"
)
WARM_SNAPSHOT_INTERVAL_S = float(os.environ.get("WARM_SNAPSHOT_INTERVAL_S", "300"))
WARM_SNAPSHOT_CPU_CEILING = float(os.environ.get("WARM_SNAPSHOT_CPU_CEILING", "70"))
WARM_SNAPSHOT_DIR = os.environ.get("WARM_SNAPSHOT_DIR", "/warm")
```

Concrete loop shape:

```python
def _warm_snapshot_loop() -> None:
    while True:
        time.sleep(WARM_SNAPSHOT_INTERVAL_S)
        if not WARM_SNAPSHOT_ENABLED:
            continue
        if container_cpu_percent() > WARM_SNAPSHOT_CPU_CEILING:
            continue
        if _current_member_state() != "PRIMARY":
            continue
        _create_warm_snapshot(WARM_SNAPSHOT_DIR)
```

Concrete snapshot creation shape:

```python
def _create_warm_snapshot(snapshot_dir: str) -> bool:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
    try:
        client.admin.command({"fsync": 1, "lock": True})
        try:
            subprocess.run(
                [
                    "sh", "-c",
                    f"rm -rf {snapshot_dir}/data && mkdir -p {snapshot_dir}/data && cp -a /data/db/. {snapshot_dir}/data/",
                ],
                check=True,
            )
            _write_warm_snapshot_meta(snapshot_dir)
            return True
        finally:
            client.admin.command({"fsyncUnlock": 1})
    except Exception:
        logger.exception("Warm snapshot creation failed")
        return False
    finally:
        client.close()
```

Concrete metadata shape:

```python
def _write_warm_snapshot_meta(snapshot_dir: str) -> None:
    meta = {
        "created_ts": time.time(),
        "rs_name": os.environ.get("MONGO_REPLSET"),
        "source_container": os.environ.get("CONTAINER_NAME"),
        "complete": True,
    }
    with open(os.path.join(snapshot_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f)
```

The exact shell used for the copy can vary, but the contract should stay fixed:

- snapshots run only on primaries,
- snapshots are skipped under high CPU,
- snapshot data lives under `/warm/data` and metadata lives in `/warm/meta.json`,
- `meta.json` is written only on success,
- any failure leaves the cold path available.

---

### 6.5 [build_network_1.sh](../../../../source/scripts/network/build_network_1.sh) and [build_network_2.sh](../../../../source/scripts/network/build_network_2.sh)

Mount a warm volume for each static primary and enable the snapshot loop on those static containers only.

Concrete shape for LAN 1:

```bash
docker run -dit --name edge_storage_server_n1 --network none \
  -e LAN_ID=lan1 \
  -e MONGO_REPLSET=rs_net1 \
  -e MONGO_PORT=27018 \
  -e HEARTBEAT_ENABLED=true \
  -e WARM_SNAPSHOT_ENABLED=true \
  -e WARM_SNAPSHOT_INTERVAL_S=300 \
  -e WARM_SNAPSHOT_CPU_CEILING=70 \
  -e WARM_SNAPSHOT_DIR=/warm \
  -v edge_storage_server_n1-data:/data/db \
  -v rs_net1_warm:/warm \
  edge_storage_server
```

LAN 2 should mirror the same pattern with `rs_net2_warm`.

No change is required in
[entrypoint.sh](../../../../source/docker/edge_storage_server/entrypoint.sh):
the sidecar already starts only after `mongod` accepts connections, which is compatible with both the direct-primary join path and the warm-snapshot loop.

---

### 6.6 [cleanup.sh](../../../../source/scripts/cleanup.sh)

Include the warm snapshot volumes in full-reset and volume-removal paths.

Concrete shape:

```bash
local volumes=(
  edge_storage_server_n1-data
  edge_storage_server_n2-data
  rs_net1_warm
  rs_net2_warm
)
```

Without this change, the experiment environment can retain stale warm snapshots across resets and make Tier 2 bootstrap results harder to interpret.

---

## 7. Files That Should Not Change

To keep the implementation consistent with the current architecture, the following files should remain behaviorally unchanged:

- [scaling_policy.py](../../../../source/sdn_controller/scaling_policy.py) — still computes when to scale, not how to discover the primary
- [control_events.py](../../../../source/sdn_controller/control_events.py) — still promotes storage only on `rs_secondary_ready` or telemetry fallback
- [aggregator.py](../../../../source/docker/local_state_server/aggregator.py) — no change; control-event mini-summaries are already forwarded immediately
- [zmq_source.py](../../../../source/sdn_controller/telemetry/zmq_source.py) — no change; the current mini-summary receive path is already sufficient
- [node_registry.py](../../../../source/sdn_controller/node_registry.py) — no change needed for direct-primary handoff or warm snapshot support
- [entrypoint.sh](../../../../source/docker/edge_storage_server/entrypoint.sh) — current sidecar startup order is already compatible

---

## 8. Config Surface

| Variable | Where | Default | Purpose |
| --- | --- | --- | --- |
| `RS_PRIMARY_HOST` | Dynamic storage container | unset | Controller-supplied direct primary target for the join fast path |
| `RS_SEED_HOST` | Dynamic storage container | existing | Fallback seed host for current discovery behavior |
| `OWN_IP` | Dynamic storage container | unset | Controller-supplied IP for the new dynamic storage node |
| `OWN_MAC` | Dynamic storage container | unset | Controller-supplied MAC for the new dynamic storage node |
| `IFACE` | Dynamic storage container | `eth0` | Interface name used for network-ready and fallback IP discovery |
| `WARM_SNAPSHOT_ENABLED` | Static primary storage containers | `false` | Enable periodic warm snapshot creation |
| `WARM_SNAPSHOT_INTERVAL_S` | Static primary storage containers | `300` | Seconds between warm snapshot attempts |
| `WARM_SNAPSHOT_CPU_CEILING` | Static primary storage containers | `70` | Skip snapshot creation when storage CPU is above this value |
| `WARM_SNAPSHOT_DIR` | Static primary storage containers | `/warm` | Path of the mounted warm snapshot volume |
| `WARM_VOLUME_MAX_AGE_S` | Controller / storage adder | `600` | Soft staleness threshold used for logging and classification in phase 1; not a hard reject |

---

## 9. Verification

The verification should focus on behavior, not broad timing instrumentation.

### 9.1 Direct-primary handoff

Expected outcome:

- the controller logs the resolved `primary_host` when submitting a `DataAlert`;
- the dynamic storage container logs a direct join attempt via `RS_PRIMARY_HOST`;
- when the host is correct, the sidecar joins without the initial `isMaster` discovery round.

### 9.2 Fallback behavior

Expected outcome:

- if `RS_PRIMARY_HOST` is stale because an election occurred, the direct attempt fails quickly;
- the sidecar falls back to the current seed-based discovery path;
- the node still reaches `SECONDARY` eventually.

### 9.3 Warm snapshot use

Expected outcome:

- static primaries write a warm snapshot only when they are `PRIMARY` and below the CPU ceiling;
- dynamic storage add logs whether the warm snapshot was used or the cold path was used;
- missing, corrupt, incomplete, or wrong-RS snapshot metadata forces a safe cold-path fallback;
- valid but stale snapshots are still copied in phase 1 and logged as stale.

### 9.4 Readiness and admission

Expected outcome:

- the node is still admitted to the VIP storage pool only after `rs_secondary_ready` or telemetry fallback confirms `member_state == "SECONDARY"`;
- no request is routed to the dynamic storage node before that point.

### 9.5 End-to-end comparison using the existing experiment pipeline

The existing testing and metrics workflow is sufficient for comparison:

- [run_experiment.sh](../../../../source/scripts/testing/run_experiment.sh)
- [metrics_stats.py](../../../../source/scripts/tools/metrics_stats.py)
- [testing_overview.md](../../testing/testing_overview.md)

The key metric to compare across baseline and optimized runs is the time between:

1. storage scale-up alert submission, and
2. `rs_secondary_ready`.

No extra timing-instrumentation project is required for the first validation pass.

---

## 10. Documentation Updates Required After Implementation

After the code lands, update the following docs so the behavior described there matches the implementation exactly:

| File | Required update |
| --- | --- |
| [elasticity_overview.md](../elasticity_overview.md) | Mark this plan as implemented, document `RS_PRIMARY_HOST`, and document warm-volume lifecycle and fallback behavior. |
| [system_mechanisms.md](../../system_mechanisms.md) | Clarify that Tier 2 now uses an optional direct-primary join fast path and an optional warm snapshot pre-seed path, while admission remains gated on `SECONDARY`. |
| [testing_overview.md](../../testing/testing_overview.md) | Add the new config knobs and note that Tier 2 comparison runs may use warm snapshots. |

---

## 11. Bottom Line

This plan keeps the current Tier 2 semantics and narrows the optimization to the concrete, code-backed changes that are consistent with the existing architecture:

1. **Warm snapshot** removes the largest avoidable cost: full cold initial sync on an empty volume.
2. **Controller-assisted primary handoff** removes the smaller but unnecessary seed-to-primary discovery round on the fast path.
3. **Controller-assisted node identity handoff** removes avoidable IP and MAC discovery work inside the dynamic container.

Everything else stays the same:

- the sidecar still owns replica-set join,
- the controller still owns VIP admission,
- the current `rs_secondary_ready` mini-summary path stays unchanged,
- the node still serves only after `SECONDARY`.

That makes this the smallest coherent Tier 2 speed-up plan that remains aligned with the current codebase.
