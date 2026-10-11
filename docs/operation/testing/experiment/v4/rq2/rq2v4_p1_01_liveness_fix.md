# RQ2 v4 — P1.1: Liveness/cull fix (diff draft)

> **Status:** 2026-10-11 · approved (author: "fix them") and **implemented**
> (P1.2); selftest green locally (all assertions incl. the live aggregator
> contract); implemented-diff review gate closed; VM verification P1.3–P1.4
> pending.
> **Companion:** [`rq2v4_plan.md`](rq2v4_plan.md) (master plan),
> [`preparation.md`](preparation.md) (autopsy findings, D1–D7).
> **Provenance:** both 2026-10-11 autopsies; every anchor below re-verified
> against the code at draft time (line numbers are the pre-patch state).

## 0. Goal

Under saturation the platform must stop culling live added units. The fix
makes presence honest (liveness is refreshed on every delivered window and by
container heartbeats) and makes absence/overload evidence honest (windows
without per-tier data are never consumed as evidence). Exit criterion: the
P1.4 battery gates (a)–(f) in `rq2v4_plan.md`.

## 1. Verified defect chain

1. **Presence freeze.** Presence (`_last_seen_mono`) is refreshed only inside
   `DynamicNodeRegistry.detect_absent()`, which the churn guard can skip for
   the whole overload episode (`main_n1.py:967–973`). Ages freeze, then a lull
   window opens the guard and expired ages cull in a batch
   (autopsy: Part C "not seen for 238–440 s", Part D cull ×7).
2. **No-evidence windows consumed as evidence.** The aggregator always
   publishes empty windows (`aggregator.py:349–366`) labeled
   `overload=False`; the controller appends that to the overload history
   (`main_n1.py:570–572`) and `detect_absent` ages every node missing from
   any summary — including empty and heartbeat-less blackout windows. During
   a per-request telemetry blackout (`zmq.NOBLOCK` drops,
   `telemetry.py:209–213`) this culls live nodes.
3. **No periodic liveness signal on dynamic nodes.** Dynamic containers
   inherit `HEARTBEAT_ENABLED=false` (compute: image default, preserved by
   the comment at `compute_node_manager.py:267–270`; storage: default
   `heartbeat_enabled=False`, `storage_node_manager.py:43–52`), so only the
   one-shot bootstrap heartbeat runs (`telemetry.py:289–293`). Static nodes
   already heartbeat (`build_network_1.sh:115,133`). Heartbeat-only entries
   synthesize **zero-latency** routing stats (`aggregator.py:494–506` →
   `update_server_stats`) that distort backend selection — the bootstrap
   heartbeat already injects one such entry per added node today.

## 2. Anchor table (verified 2026-10-11, pre-patch)

| Site | File:lines | Current behavior |
| --- | --- | --- |
| Append site | `main_n1.py:570–572` / `main_n2.py:552–554` | unconditional `_recent_overload.append(summary.overload)` |
| Recall feed | `main_n1.py:941–943` / `main_n2.py:923–925` | feeds `bool(s.overload)` into release gates |
| Churn guard | `main_n1.py:967` / `main_n2.py:949` | `s.overload or any(_recent_overload)` — **no edit needed** (see §5) |
| Absence | `node_registry.py:124–149` | ages any tracked node missing from the summary |
| Overload label | `aggregator.py:143–154` | `False` for domain_summary None or below `OVERLOAD_MIN_REQUESTS` |
| Publish | `aggregator.py:158–173`, empty call `349–366`, normal call `642` | always publishes, `overload` bool |
| Heartbeat merge | `aggregator.py:478–512` (synthesized `494–506`, existing-entry `507–512`) | synthesizes `servers[sid]` with zeroed latencies |
| Scale-down eval | `main_n1.py:1062–1068` / `main_n2.py:1044–1050` | consumes the zeroed domain_summary regardless of evidence |
| Housekeeping entry | `main_n1.py:931–933` / `main_n2.py:913–915` | re-runs on the same window; no delivery-freshness check |
| Routing merge | `_vip_routing/state.py:268–297` | stores every entry; heartbeats must not clobber measurements |
| Compute spawn | `elasticity/compute_node_manager.py:266–271` | no heartbeat env |
| Storage spawn | `elasticity/elasticity.py:726–735` (ordinary), `829–836` (reserve, already `True`) | ordinary add has no heartbeat |
| Model | `telemetry/models.py:108–121` (`TelemetrySummary`), `34–51` (`ServerSummary`) | no `request_evidence`, no `heartbeat_only` |
| Decode | `zmq_source.py:64`, `delayed_source.py:128`, `event_preserving_source.py:125`, `sampled_push_source.py:161`, `polling_source.py:99` | all `TelemetrySummary.model_validate(...)` — declared fields flow, defaults cover old payloads |

## 3. Patch A — presence refresh at delivery

**A0. Init** — `main_n1.py:194` / `main_n2.py:188`, after the
`self._last_summary` declaration, add:

```python
        self._last_summary_mono: float = 0.0
```

**A1. `source/sdn_controller/node_registry.py`** — new method, inserted after
`detect_absent` (before the `# ── Queries ──` section):

```python
    def refresh_presence(self, summary: TelemetrySummary) -> None:
        """Refresh liveness for every tracked dynamic node in a delivered window.

        Called on delivery, outside the housekeeping churn guard, so
        suppression can no longer freeze presence ages. Heartbeat-only
        entries count as presence — liveness is their purpose.
        """
        now = time.monotonic()
        for mac in self._dynamic_node_macs:
            if mac in summary.servers or mac in summary.storage_servers:
                self._last_seen_mono[mac] = now
```

**A2. `main_n1.py:570–572`** (and identically `main_n2.py:552–554`, with its
two comment lines unchanged):

```python
# BEFORE
        if summary.window_seq is not None:
            self._last_summary = summary
            self._recent_overload.append(summary.overload)

# AFTER
        if summary.window_seq is not None:
            self._last_summary = summary
            self._last_summary_mono = time.monotonic()
            if summary.request_evidence:
                self._recent_overload.append(summary.overload)
            self._node_registry.refresh_presence(summary)
```

The `detect_absent` in-place refresh stays (idempotent; keeps that method
self-contained for its own callers).

## 4. Patch B — no absence or overload evidence without evidence

**B1. `source/docker/local_state_server/aggregator.py`**

`_publish_window` (L158) gains a keyword-only flag; the empty and normal call
sites pass request evidence:

```python
# BEFORE (L158–163)
def _publish_window(summary: dict) -> None:
    global _window_seq
    _window_seq += 1
    summary["window_seq"] = _window_seq
    summary["window_id"] = f"{NETWORK_ID}:{_window_seq}"
    summary["overload"] = _compute_overload(summary)

# AFTER
def _publish_window(summary: dict, *, request_evidence: bool = True) -> None:
    global _window_seq
    _window_seq += 1
    summary["window_seq"] = _window_seq
    summary["window_id"] = f"{NETWORK_ID}:{_window_seq}"
    # False = the window carried no HTTP request samples (empty window or
    # non-HTTP-only window). Consumers must not read it as a lull signal.
    summary["request_evidence"] = request_evidence
    summary["overload"] = _compute_overload(summary)
```

Log line (L165–173): append `evidence=%s` with `request_evidence` to the
argument list (diagnostics only).

```python
# BEFORE (L354, empty-window branch)
            _publish_window({

# AFTER
            _publish_window({
```
…and the closing call gains the flag:

```python
# BEFORE (L354–362)
            _publish_window({
                "network_id":      NETWORK_ID,
                "window_end":      time.time(),
                "servers":         {},
                "storage_servers": {},
                "domain_summary":  None,
                "control_events":  [],
            })

# AFTER
            _publish_window({
                "network_id":      NETWORK_ID,
                "window_end":      time.time(),
                "servers":         {},
                "storage_servers": {},
                "domain_summary":  None,
                "control_events":  [],
            }, request_evidence=False)
```

```python
# BEFORE (L642)
        _publish_window(summary)

# AFTER
        _publish_window(summary, request_evidence=bool(http_events))
```

`_compute_overload` is **unchanged**: the pre-registered `overload` label
(D3) keeps its meaning and the window-log contract is untouched; the new
flag distinguishes “not overloaded” from “not labelable”.

**B2. `source/sdn_controller/telemetry/models.py`** — `TelemetrySummary`,
after the `overload` field (L115):

```python
    overload: bool = False            # producer-side label (D3)
    # False when the window carried no HTTP request samples (empty or
    # non-HTTP-only window). Controller-side consumers must not treat such
    # windows as lull evidence. Producer:
    # source/docker/local_state_server/aggregator.py.
    request_evidence: bool = True
```

**B3. Append gate** — included in A2 above.

**B4. Recall feed gate.** `main_n1.py:941–943` (identical at
`main_n2.py:923–925`):

```python
# BEFORE
            if (self._release_gate.active
                    and s.window_seq != self._last_recall_feed_seq
                    and self._release_gate.mode == "stabilized"):

# AFTER
            if (self._release_gate.active
                    and s.window_seq != self._last_recall_feed_seq
                    and self._release_gate.mode == "stabilized"
                    and s.request_evidence):
```

Same defect class as A2: a window without request evidence must not advance
release-gate/recall hysteresis.

**B5. Tier-evidence aging rule** — `node_registry.py:124–149`,
`detect_absent` body becomes:

```python
        now = time.monotonic()
        request_evidence = summary.request_evidence
        storage_evidence = bool(summary.storage_servers)
        timed_out: list[str] = []
        for mac in list(self._dynamic_node_macs):
            # Skip freshly spawned nodes still booting
            if now - self._birth_ts.get(mac, float('-inf')) < _NODE_BIRTH_GRACE_S:
                continue

            present = (mac in summary.servers) or (mac in summary.storage_servers)
            if present:
                self._last_seen_mono[mac] = now
                continue
            info = self._active.get(mac)
            if info is not None and info.node_type in ("storage", "selective_storage"):
                if not storage_evidence:
                    continue
            elif not request_evidence:
                continue
            if now - self._last_seen_mono.get(mac, now) > _TELEMETRY_TIMEOUT_S:
                logger.warning(
                    "[registry] mac=%s not seen for %.0fs — triggering removal",
                    mac, now - self._last_seen_mono.get(mac, now),
                )
                timed_out.append(mac)
        return timed_out
```

Docstring addition (same method):

```
        A node is only aged when the window carried evidence for its tier:
        HTTP request samples for compute nodes, storage summaries for
        storage nodes (liveness-only heartbeat entries included — they
        evidence the storage tier is alive). Windows without tier evidence —
        telemetry blackouts — must never produce absence.
```

**B6. Scale-down gate** — `main_n1.py:1062–1068` (identical at
`main_n2.py:1044–1050`). A no-HTTP window carries a **zeroed**
`domain_summary` (not `None`), which reads as underutilisation and arms a
graceful removal of live nodes. This gate also covers the new heartbeat-only
windows that Patch C introduces:

```python
# BEFORE
            # ── Scale-down evaluation — once per delivered window_seq ───
            if s.window_seq == self._last_scale_eval_seq:
                return
            self._last_scale_eval_seq = s.window_seq
            ds = s.domain_summary
            if ds is None:
                return

# AFTER
            # ── Scale-down evaluation — once per delivered window_seq ───
            if s.window_seq == self._last_scale_eval_seq:
                return
            self._last_scale_eval_seq = s.window_seq
            ds = s.domain_summary
            if ds is None or not s.request_evidence:
                # Zeroed domain summaries (no HTTP samples in this window)
                # must not read as underutilisation.
                return
```

B6 is a `return` from `_run_housekeeping`, so the remainder of the pass —
including the retention/quarantine expiry finalization branches that follow
— defers to the next request-evidenced window. The deferral only ever
postpones removals (the conservative direction; the canonical baseline runs
`RELEASE_MECHANISM=off`, but the structure stays mode-agnostic).

**B7. Delivery-freshness bound** — absence/scale-down judgments need a
recently delivered window; with no delivery the controller cannot
distinguish a dead node from a dead telemetry path. (The absent loop re-runs
every `CONTROL_TICK_S` against the same `_last_summary`; the scale-down
section is deduped per `window_seq`, the absent loop is not.)

`scaling_config.py`, after the churn-guard block (L160–161):

```python
# Housekeeping freshness bound: judgments need a window delivered recently
# (empty windows still refresh delivery). With no delivery for this long the
# controller cannot distinguish a dead node from a dead telemetry path, so
# it must not act. At least twice the longest delivery period past the last
# delivery — sampled push delivers every 3 x WINDOW_S — plus one tick of
# slack. Defaults (CONTROL_TICK_S=10, WINDOW_S=10): 70 s.
_HOUSEKEEPING_STALE_S = float(os.environ.get(
    "HOUSEKEEPING_STALE_S",
    str(max(6.0 * _CONTROL_TICK_S,
            6.0 * float(os.environ.get("WINDOW_S", "10"))) + _CONTROL_TICK_S)))
```

Import in both mains (after `_HOUSEKEEPING_OVERLOAD_LOOKBACK,` in the
`scaling_config` import block): add `_HOUSEKEEPING_STALE_S,`.

Housekeeping — `main_n1.py:931–933` / `main_n2.py:913–915`:

```python
# BEFORE
            s = self._last_summary
            if s is None or s.window_seq is None:
                return

# AFTER
            s = self._last_summary
            if s is None or s.window_seq is None:
                return
            if time.monotonic() - self._last_summary_mono > _HOUSEKEEPING_STALE_S:
                logger.debug(
                    "[housekeeping] no fresh window for %.0fs — skipping",
                    time.monotonic() - self._last_summary_mono,
                )
                return
```

The delivery stamp is the A2/A0 edit in §3.

## 5. Deliberately NOT changed

- **Churn guard read (`main_n1.py:967` / `main_n2.py:949`)** — no edit. With
  B3, `_recent_overload` holds only evidenced labels, so `any(...)` carries
  the hysteresis correctly across blackouts. A window without request
  evidence can no longer drive the compute-side chain (B4/B5/B6 gate the
  recall feed, absence and scale-down; B7 blocks stale windows); absence
  itself remains tier-scoped by B5. **Semantic change (intended):** the
  lookback deque now spans the last N *evidenced* windows, so suppression
  extends in wall-clock time across blackouts — exactly the
  capacity-protection the guard exists for.
- **`update_storage_stats` / storage heartbeat branch** — the heartbeat
  payload carries real instantaneous measurements (connections, CPU, RAM,
  lag). For a primary, `_repl_lag_and_state` returns `0.0` in the real
  `mongo_stats` path as well (`mongo_telemetry.py:292–294`), so no new
  falsification exists; there is no zero-latency field on the storage side.
  The entry flows normally and also stamps backend discovery. The slight
  loss of window averaging on idle heartbeats is accepted and pre-exists for
  static nodes.
- **Existing-entry heartbeat merge branch (`aggregator.py:507–512`)** —
  refreshes only `last_report_ts`/`state`; no poisoning path.
- **`_compute_overload` return type and `OVERLOAD_MIN_REQUESTS` semantics** —
  unchanged (B1 rationale above; plan P1.1's "fix `_compute_overload`"
  wording is refined by this draft — recorded in `rq2v4_plan.md`).
- **`detect_absent` in-place refresh** — kept (idempotent).
- **B5/B6 asymmetry (intentional)** — absence is judged per tier, while
  scale-down requires request evidence for both tiers: HTTP-free windows
  carry a zeroed DB-latency context, which the storage underutilisation
  gate would misread. Deferring to the next request-evidenced window is the
  conservative direction.
- **Promotion / role-sync paths** (`sync_storage_roles`,
  `process_secondary_events`, reserve preparation) — they consume the *state*
  fields of heartbeat entries (`member_state`, connections), which are fresh
  real observations from a live query; that is by design and unchanged. This
  fix scopes "evidence" consumption to the overload, absence and scale-down
  signals.
- **Container images** — `edge_server`/`edge_storage_server` heartbeat code
  already exists (`telemetry.py:289`, `mongo_telemetry.py:339`); the fix
  enables it via docker-run env only. **P1.3 rebuilds only the
  `local_state_server` image** (its Dockerfile bakes `aggregator.py`); the
  controller runs from the bind-mounted VM checkout
  (`build_network_setup.sh` mounts `$PWD` into the controller container), so
  its fixes deploy by syncing that checkout to the fix commit (plan P1.3
  wording refined). Edge images are unchanged. The two edge telemetry
  comments still reference the pre-archive docs path
  (`docs/operation/other/…`) — cosmetic only, corrected when those images
  are next rebuilt in P2.

## 6. Patch C — heartbeats on dynamic nodes, no routing poisoning

**C1. `elasticity/compute_node_manager.py`** — `_docker_run_server`, replace
the comment block at L267–270:

```python
# BEFORE
            "-e", f"EDGE_MONGO_MAX_POOL_SIZE={os.environ.get('EDGE_MONGO_MAX_POOL_SIZE', '1')}",
            # Dynamic nodes inherit HEARTBEAT_ENABLED=false (the image default).
            # Lifecycle is handled by scale-down (graceful) + telemetry-window
            # absence timeout (failure). See
            # docs/operation/other/heartbeat_dynamic_node_gate_plan.md.
            "edge_server",

# AFTER
            "-e", f"EDGE_MONGO_MAX_POOL_SIZE={os.environ.get('EDGE_MONGO_MAX_POOL_SIZE', '1')}",
            # Dynamic nodes heartbeat too (liveness only): presence must
            # survive telemetry blackouts under saturation. Supersedes the
            # 2026-08 heartbeat gate plan — see
            # docs/operation/archive/other/heartbeat_dynamic_node_gate_plan.md
            # and docs/operation/testing/experiment/v4/rq2/rq2v4_p1_01_liveness_fix.md.
            "-e", "HEARTBEAT_ENABLED=true",
            "edge_server",
```

**C2. `elasticity/elasticity.py`** — `_handle_data` storage spawn (L726):

```python
# BEFORE
        result = self._storage_adder.add_storage_node(
            lan=alert.lan,
            name=name,
            rs_name=alert.rs_name,
            # primary_container=alert.primary_container,
            port=alert.port,
            ip=ip, mac=mac,
            rs_seed_host_override=rs_seed_override,
        )

# AFTER
        result = self._storage_adder.add_storage_node(
            lan=alert.lan,
            name=name,
            rs_name=alert.rs_name,
            # primary_container=alert.primary_container,
            port=alert.port,
            ip=ip, mac=mac,
            # Everyday dynamic storage nodes heartbeat too (liveness only).
            heartbeat_enabled=True,
            rs_seed_host_override=rs_seed_override,
        )
```

Standby reserves already pass `heartbeat_enabled=True` (L829–836); the
signature defaults stay `False` (explicit intent per call site).

**C3. `aggregator.py`** — edge heartbeat branch (L494–506):

```python
# BEFORE
            else:                                     # edge server heartbeat
                if sid not in servers:
                    servers[sid] = {
                        "avg_time_total_ms": 0.0,
                        "avg_time_db_ms":    0.0,
                        "avg_time_proc_ms":  0.0,
                        "request_count":     0,
                        "error_rate":        0.0,
                        "avg_cpu_percent":   hb.get("cpu_percent", 0.0),
                        "avg_ram_used_mb":   hb.get("ram_used_mb", 0.0),
                        "last_report_ts":    last_seen.get(sid, hb.get("ts", 0.0)),
                        "state":             hb.get("state", "active"),
                    }

# AFTER
            else:                                     # edge server heartbeat
                if sid not in servers:
                    # Liveness-only entry (zeroed latency fields). Flagged so
                    # the routing stats never absorb it as a zero-latency
                    # sample — presence consumers may still see it.
                    servers[sid] = {
                        "heartbeat_only":    True,
                        "avg_time_total_ms": 0.0,
                        "avg_time_db_ms":    0.0,
                        "avg_time_proc_ms":  0.0,
                        "request_count":     0,
                        "error_rate":        0.0,
                        "avg_cpu_percent":   hb.get("cpu_percent", 0.0),
                        "avg_ram_used_mb":   hb.get("ram_used_mb", 0.0),
                        "last_report_ts":    last_seen.get(sid, hb.get("ts", 0.0)),
                        "state":             hb.get("state", "active"),
                    }
```

**C4. `telemetry/models.py`** — `ServerSummary`, after
`state: Literal[...] = "active"`:

```python
    # True for liveness-only heartbeat entries (zeroed latency fields) —
    # excluded from the routing stats cache. Producer: aggregator heartbeat
    # merge.
    heartbeat_only: bool = False
```

**C5. `_vip_routing/state.py`** — `update_server_stats` (L268–283):

```python
# BEFORE
    for mac, summary in servers.items():
        controller._server_stats[mac] = summary
        if mac not in controller._backend_discovery_ts:
            controller._backend_discovery_ts[mac] = time.monotonic()

# AFTER
    for mac, summary in servers.items():
        if mac not in controller._backend_discovery_ts:
            # Stamp discovery for every node the controller hears from —
            # including liveness-only heartbeats — so the slow-start ramp
            # clock starts at spawn, not at first assignment.
            controller._backend_discovery_ts[mac] = time.monotonic()
        if summary.heartbeat_only:
            # Liveness-only sample: zeroed latency fields must never
            # overwrite real routing stats. Refresh the freshness stamp and
            # drain state on an existing entry; a node with no entry yet
            # keeps a flagged placeholder (as the pre-patch bootstrap
            # heartbeat did) so it stays a graceful scale-down candidate.
            entry = controller._server_stats.get(mac)
            if entry is None:
                controller._server_stats[mac] = summary
            elif summary.last_report_ts > entry.last_report_ts:
                entry.last_report_ts = summary.last_report_ts
                entry.state = summary.state
            continue
        controller._server_stats[mac] = summary
```

## 7. Post-fix semantics (walkthrough)

- **Delivery**: every real window refreshes presence (§3) and the delivery
  timestamp; ages advance only while a node is silent in *delivered*
  windows — the churn guard no longer freezes them.
- **Blackout under overload**: empty/storage-only/heartbeat-only windows are
  never appended (B3), never fed to release gates (B4), only age a tier that
  itself has evidence (B5), and never drive scale-down (B6). Periodic
  heartbeats (C) keep dynamic nodes present; the pinned timeout (600 s, §11)
  tolerates 10 consecutive heartbeat-interval losses.
- **No delivery at all** (past 2 × the longest delivery period + one tick —
  70 s at defaults): housekeeping stands down (B7) — a dead telemetry path
  must not read as a dead fleet.
- **Genuine absence**: heartbeats stop, peers keep reporting → tier
  evidence present → ages accumulate → removed at `_TELEMETRY_TIMEOUT_S` as
  before (regression-safe).
- **New backends**: the warm lease is granted at admission
  (`register_new_server_backend` → `state.py:167–170`; 45 s via
  `_VIP_WARM_SERVER_SECONDS`), so under `topology_lifecycle` a new backend
  short-circuits the WSM cost while it warms; under `topology_slowstart` the
  ramp clock starts at the discovery stamp (C5) — matching the pre-patch
  bootstrap-heartbeat timing — and the unknown-stats default is neutral
  (0.0). Heartbeats never clobber measurements (C5): an existing entry
  keeps its real stats and receives only the freshness stamp and drain
  state, so an idle-but-alive node stays a valid graceful scale-down
  candidate.
- **Selection**: heartbeat-only entries stay in presence. A never-served
  node keeps a flagged zeroed placeholder in the stats cache (pre-patch
  bootstrap semantics, without the repeated overwrite), which briefly reads
  as cheapest in the WSM cost until its first real window arrives.
- **Removed nodes**: the VIP unregister helpers drop the cached summary;
  the reserve-loss, selective-cleanup and readiness-abandon paths drop it
  via `drop_backend_caches` — a recycled MAC can never present a removed
  container's measurements as fresh.

**Documented residuals:** per-node sample loss inside an otherwise-evidenced
tier (one node's HTTP samples all dropped while peers report) is covered by
heartbeats (10 intervals per pinned timeout), not by per-node drop detection
— `zmq.NOBLOCK` drops are silent and not counted. A backend with no stats at
all (e.g. before its first heartbeat) competes at the unknown-stats default.
The P1.4 battery measures both paths; drop counters are out of scope for P1.

## 8. P1.2 tests — implemented and green (2026-10-11, host Python)

`source/scripts/testing/rq2v4_p1_02_liveness_selftest.py` (repo-style
selftest; ran green on the host):

1. Registry evidence gating — no-evidence window + aged mac → no absence;
   request-evidenced window: below timeout kept, past timeout removed;
   storage node not aged without storage evidence, removed with it;
   `selective_storage` follows the storage branch; heartbeat-only presence
   counts and refreshes.
2. `refresh_presence` resets ages without any housekeeping pass; silent
   nodes untouched.
3. Model/decode compatibility — legacy payload (no new fields) defaults to
   `request_evidence=True` / `heartbeat_only=False`; explicit values flow;
   `_HOUSEKEEPING_STALE_S == max(6 × TICK, 6 × WINDOW_S) + TICK`.
4. `update_server_stats` — a never-served node's heartbeat keeps a flagged
   placeholder and stamps discovery; a later heartbeat refreshes only the
   freshness stamp and drain state of an existing entry (real measurements
   intact; older stamps never regress; the refreshed stamp keeps the node
   inside the 90 s scale-down candidate gate). `unregister_*` and
   `drop_backend_caches` drop the cached summary — a recycled MAC never
   inherits foreign stats.
5. Aggregator window contract — **subprocess** run (the module is a script
   whose tail binds the cache server and calls `_publish_loop()` at import —
   `aggregator.py:733–734`, `738`; the parent needs `pyzmq`, present on the
   host and in the `local_state_server` image). Bind-then-close ephemeral
   ports picked by the parent; PUSH the heartbeat twice (duplicate-tolerant;
   guards a drop) → poll `/windows` (not `/latest_summary`, which every window
   overwrites) → `request_evidence=False`, `heartbeat_only=True`; PUSH one
   HTTP event → `request_evidence=True`, entry not flagged.

## 9. Docs updated (applied 2026-10-11)

- `docs/operation/archive/other/heartbeat_dynamic_node_gate_plan.md` ✅ —
  supersession banner: dynamic nodes now heartbeat (liveness only).
- `docs/operation/telemetry/telemetry_overview.md` ✅ — window contract
  (`request_evidence`), heartbeat-only semantics (placeholder + removed-node
  drop), presence/absence rules; `sampled_push` added to the mode list.
- This artifact + `rq2v4_plan.md` ✅ — anchor refinements (guard read and
  `_compute_overload` untouched; P1.3 image scope; extra gates B6/B7;
  review-fix log: candidate-staleness refresh, recycled-MAC pops incl.
  reserve/selective cleanup, B7 formula).

## 10. Change inventory

**Code & scripts (10 files)**

| # | File | Patches |
| --- | --- | --- |
| 1 | `source/sdn_controller/node_registry.py` | A1, B5 |
| 2 | `source/sdn_controller/main_n1.py` | A0/A2, B4, B6, B7, import |
| 3 | `source/sdn_controller/main_n2.py` | A0/A2, B4, B6, B7, import |
| 4 | `source/docker/local_state_server/aggregator.py` | B1, C3 |
| 5 | `source/sdn_controller/telemetry/models.py` | B2, C4 |
| 6 | `source/sdn_controller/_vip_routing/state.py` | C5 |
| 7 | `source/sdn_controller/elasticity/compute_node_manager.py` | C1 |
| 8 | `source/sdn_controller/elasticity/elasticity.py` | C2 |
| 9 | `source/sdn_controller/scaling_config.py` | B7 (constant) |
| 10 | `source/scripts/testing/rq2v4_launch_run.sh` | launcher, merge shim (new) |

**Config — mode deltas (4 new files in
`source/scripts/testing/controller_env_overrides/`)**

A delta alone must never be passed as the override: the launcher merges
canonical + delta (delta wins) into a temp file and passes that as
`OSKEN_ENV_OVERRIDE_FILE` (precedent: the research_q3 merge shim, whose
`build_network_setup.sh`/`run_experiment.sh` accept a single file). The P1.4
battery and the P5 campaign use these files:

| File | Content (delta over `current_state_integrated.env`) |
| --- | --- |
| `rq2v4_mode_both.env` | `MAX_DYNAMIC_COMPUTE=6` · `MAX_DYNAMIC_STORAGE=6` · `SS_ENABLED=0` |
| `rq2v4_mode_comp.env` | `MAX_DYNAMIC_COMPUTE=6` · `MAX_DYNAMIC_STORAGE=0` · `STORAGE_PERSISTENT_RESERVE_ENABLED=0` · `SS_ENABLED=0` |
| `rq2v4_mode_stor.env` | `MAX_DYNAMIC_COMPUTE=0` · `MAX_DYNAMIC_STORAGE=6` · `SS_ENABLED=0` |
| `rq2v4_mode_none.env` | `MAX_DYNAMIC_COMPUTE=0` · `MAX_DYNAMIC_STORAGE=0` · `STORAGE_PERSISTENT_RESERVE_ENABLED=0` · `SS_ENABLED=0` |

- Caps pin the operating point (6/6 per domain; the canonical carries 3/3).
  `none` is the no-action comparator; `comp`/`stor` disable the other tier
  per D1 (comp also disables the storage reserve).
- `SS_ENABLED=0` in **all four** modes: Tier-1 promotion can spawn
  `edge_selective_storage` containers (`elasticity.py:1333` →
  `selective_storage_manager.py`; gated at `promotion.py:108`), and v4 RQ2
  evaluates none of the Tier-1 surface. Holding it off uniformly keeps
  `none` a true no-action comparator and the 3×3 a single-axis contrast.
  **Verify at P1.2** (check v3 RQ2 episodes for Tier-1 activity; if any
  engaged, flag back before freezing the choice).
- Cross-region storage is already off (`CROSS_REGION_STORAGE_ENABLED`
  defaults to 0 and the canonical does not set it) — no delta needed.
- Spawn-gate closure: scale-up caps, the reserve flag, the SS flag and the
  cross-region default are the only controller-side container-spawn
  switches; all are pinned or defaulted above.

The four **transport deltas** `rq2v4_transport_{ep,delayed,poll,sampled}.env`
carry only the RQ1 transport keys (copied from
`docs/operation/testing/experiment/v2/rq1/env/`) and exist for the P1.4
RQ1-mode smoke set (§12.1).

**Launcher (new)** — `source/scripts/testing/rq2v4_launch_run.sh`:
`<mode> <label> <seed> [extra_env_file ...]`, merges canonical + mode delta
+ optional transport deltas (later files win), shapes resources, runs the
make targets. Used by P1.3 (smoke), P1.4 (battery + RQ1-mode smoke set) and
the P5 campaign.

**Tests (1 new)** — `source/scripts/testing/rq2v4_p1_02_liveness_selftest.py`
(§8).

**Docs (3 updated + plan)** — §9.

All edits revert cleanly via git. No `phases.json` change (the battery edits
it in place per rung, as planned). No other config changes:
`TELEMETRY_TIMEOUT_S=600` and the churn-guard knobs stay as pinned.

## 11. Gate pins, build & verification

**Battery gate pins (pre-registered here, inherited by P4.1):**

- Gate (c) relief — treatment window (add+30 s … add+180 s) vs pre-add
  window (add−180 s … add); primary signal per tier: compute lanes → mean
  window `avg_cpu_percent` of the lane's edge servers; storage lanes → mean
  window CPU of the lane's storage members. Relief ratio = post/pre means;
  **threshold ≤ 0.75 on both lanes** (v3 db anchor observed 0.565–0.66).
- Gate (d) unlock — lock present: per-lane client p95 ≥ 1 s in ≥ 80 % of
  pre-add windows; cleared: per-lane client p95 < 1 s in ≥ 80 % of treatment
  windows.
- Gates (a)/(b)/(e)/(f) as written in `rq2v4_plan.md` P1.4.

**Deployment precondition (lockstep):** the VM checkout commit and the
`local_state_server` image are updated together — the controller runs from
the bind-mounted checkout (so the fix reaches it by sync, not rebuild),
while the aggregator is baked into its image; the new fields default to
pre-fix behaviour when absent (fail-open), so a mixed pair would silently
disable the guards.

**Steps (after approval):**

1. P1.2 ✅ (2026-10-11): patches applied; mode + transport deltas and the
   launcher added; §8 selftests green locally (all assertions; host run;
   the `_pick_compute_scale_down_candidate` wiring is exercised end to end
   by P1.4).
2. P1.3: sync the `cloud-vm-rq2` checkout to the fix commit; rebuild the
   `local_state_server` image and record its id; deploy. **Assert the
   lockstep:** `docker inspect` the deployed aggregator image id equals the
   recorded build; the controller container's `sdn_controller/` on the
   mounted workspace contains `request_evidence` (grep via `docker exec`);
   a probe window in the window log carries the top-level
   `request_evidence` key and, when a heartbeat lands in it,
   `servers[<mac>].heartbeat_only`. Low-rate smoke (telemetry continuous,
   no startup regressions).
3. P1.4: 13-run battery per `rq2v4_plan.md` — 9 gate runs launched through
   the merge shim (`rq2v4_mode_*` deltas over the canonical override) plus
   the 4-run RQ1-mode smoke set (one per `rq2v4_transport_*` delta) — full
   retention, 1 Hz host sampler; artifact `rq2v4_p1_05_verification.md`.

## 12. Delivery-mode compatibility and RQ1 impact (2026-10-11)

### 12.1 Mode producibility (transports unchanged)

The fix touches no delivery source. All five decode paths
(`event_preserving`, `delayed_event_preserving`, `poll`, `sampled_push`,
`zmq`) validate the same model, and the new fields are additive with
pre-fix defaults, so both RQ1's four modes and RQ2's three scaling modes
remain producible. The mode transports are re-proven on the fixed build by
the P1.4 RQ1-mode smoke set (4 runs, `rq2v4_transport_*.env`): each asserts
its delivery signature (ep: contiguous; delayed: every window, late; poll:
cadence = POLL_INTERVAL_S; sampled: every SAMPLE_EVERY-th window) plus
continuous presence and zero cull rows.

### 12.2 What changes for the modes (the point of the fix)

Pre-fix, absence/lull was inferred from delivery content: a window with no
per-node telemetry aged every node, and a zeroed window read as
underutilisation. That made lifecycle semantics a function of delivery
completeness/lateness — i.e., a function of the RQ1 treatment itself.
Post-fix, liveness comes from container-owned heartbeats (mode-independent)
and absence needs tier evidence; the modes keep varying only what RQ1
intends (lateness and completeness of the delivered stream).

**Replay note:** the evidence gates are unconditional — this is a repair,
not a mode, and no env default changed. Byte-identical replay of the
pre-fix platform (RQ1/RQ3 archives) means checking out the pre-fix commit,
not setting a flag.

### 12.3 RQ1 archive audit (read-only, 12 runs)

All 12 locally archived RQ1 delivery runs
(`source/scripts/testing/metrics/2026080*_rq1_delivery_*`) were audited for
the defect signature:

- Scale-down decisions while demand was above 10 % of the run's peak
  window: **zero in every run**. All removal rows per run (33–215) sit at
  zero/low-demand windows, i.e. the post-drop reclaim phase.
- Those removals are almost entirely absence-driven (`absent` rows ≈
  scale-down rows; e.g. ep_1 70/70, delayed_1 81/83, sp_1 125/125,
  ls_2 215/215) — the pre-fix reclaim path, not the graceful
  underutilisation path.

Interpretation: RQ1's *load-rise* measurements (scale-up response,
delivered share, information age — the episode the RQ answers) were not
affected by the defect; the churn guard held during the rise and no live
unit was removed mid-episode. RQ1's *teardown*, however, ran through the
absence path (mode-dependent by construction), which the fix replaces with
heartbeat-backed liveness; on the fixed platform teardown would run through
the policy's graceful scale-down instead.

### 12.4 Decision (D9)

The archived RQ1 results stand as the record of the pre-fix platform; the
v4 record documents this behaviour change; the RQ1-mode smoke set (P1.4)
re-proves mode producibility on the fixed build. Teardown replication under
the fixed semantics (a 4-arm RQ1 re-run) is parked, not planned — revisit
only on author request.
