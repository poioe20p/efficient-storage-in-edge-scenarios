# RQ2 v5 - Read-path renewal fix + storage spread band + recalibrated battery

> **Status:** authorised by author directive 2026-10-16 (hard goals H1/H2; scope =
> 56 runs, `mx`+`db`; naming `rq2v5`).
> **Parent:** v4/rq2 (diagnosis record).
> **Precedence:** for v5 this plan wins where it conflicts with any v4/rq2
> artifact; v4 artifacts remain authoritative for the v4 record. **Explicit v5
> overrides of v4 registrations:** (a) `stor`@mx storage relief is a **hard**
> goal for v5 (v4's G3 "measured, not assumed" note applies to v4 only;
> annotate `v4/rq2/experiment_plan.md` S5.2 G3 row + `rq2v4_p5_03_mx_regime_report.md`
> S2.3 in W4); (b) MC1(db) witness statistic/threshold redefined for the v5
> seat; (c) **D21b**: `select_storage` gains an env-gated epsilon-band spread
> (default OFF; v5 pins ON) - the distribution mechanism H1/H2 require.
> **Companion:** [`../../v4/rq2/rq2v4_p5_02_read_path_pinning.md`](../../v4/rq2/rq2v4_p5_02_read_path_pinning.md)
> (D18), [`../../v4/rq2/rq2v4_p5_04_db_regime_report.md`](../../v4/rq2/rq2v4_p5_04_db_regime_report.md) (S9 carries the D21 pointer).
> **Naming:** step artifacts use `rq2v5`, order `NN` (e.g.
> `rq2v5_p1_01_pool_renew_selftest.py`); run labels `rq2v5_<mode>_<regime>_<seed>`.
> **D23 (registered):** the four mode-delta files remain
> `controller_env_overrides/rq2v4_mode_*.env` (campaign-agnostic capability
> deltas; reuse documented, not a naming violation); the `rq2v5` rule covers
> run labels, new scripts, pins, and campaign artifacts only.
> **Workstreams (not v4's F1/F2 floor labels):** W1 = fix design + implementation
> (+ evidence deposit); W2 = seat calibration + pilot; W3 = 56-run battery;
> W4 = analysis + close-out.
> **Review:** auto-review round 1 (35 findings) and round 2 (24 findings) triaged;
> this is version 3 (adds the storage spread band D21b; worker/scheduler
> atomicity; single-source knobs; census arithmetic; floor re-derivation policy).

## 0. Author directive (verbatim scope)

1. **H1 (hard):** `stor` (storage-only scale-up) must **lower `t_db`**
   (`avg_time_db_ms`) in the db regime vs `none`. Client-side benefit is **not**
   required.
2. **H2 (hard):** **same-tier relief** - the storage tier must relieve its own
   press under storage-only scale-up (D14 protocol), in db **and** mx.
3. Everything else (client completion/latency/timeouts) is **soft** - measured,
   reported, never gating.
4. Scope: **56 runs = mx (28) + db (28)**. `cb` excluded (no in-episode storage
   admissions; default-off flags keep it mechanically unaffected - S7.7).
5. New naming: **`rq2v5`** (scope per D23 above).

## 1. Diagnosis recap (what v4 established, not re-litigated)

- **D18 - read-path pinning:** edge->member connections are pinned at birth
  (`select_storage` ran only 42x in an entire db run); with a fixed edge set,
  mid-press connection births ~ 0, so members admitted mid-press receive **no
  reads** -> `stor`@db relief **0/7**, `stor`@mx relief **0/7**. Flow-expiry
  re-installs reuse the recorded pin (`_vip_data_conn_map`) - never re-select.
- **Selection is one-hot for storage:** `select_storage` returns the strict
  argmin of the WSM cost (round-robin only on exact ties); there is no
  epsilon-band/floor for storage (unlike `select_server`, P2.6/P2.8). New
  connections therefore concentrate on one member even when several have
  capacity.
- **Path-binding (analyzer measurement 2026-10-16; being deposited as
  `rq2v5_w1_01_path_binding_evidence.md` in W1; method: window_log_lanX
  extraction over the 7 valid seeds of each db arm; episode-window means):**

  | quantity (db, episode) | `none` | `comp` | reading |
  | --- | --- | --- | --- |
  | edge units per lane (mean over windows) | 1.0 | 1.9 (1 static + 1 spawned) | the only intervention that changed delivery |
  | edge-delivered requests/window (of ~1200 offered) | ~1083-1103 (~90 %) | ~1186 (~99 %) | delivery recovers when the edge set doubles |
  | single-member CPU, win-max mean | 68.5/70.0 % | 72.4/73.0 % | same single member absorbed FULL delivery at ~72-73 % -> >= 27 pp headroom |
  | `t_db` (domain `avg_time_db_ms`) | ~62-63 ms | ~60-64 ms | member service leg flat - no t_db headroom existed at `sc=0.15` |
  | client completion / p50 | 92/93 % @ 1.9/1.7 s | 99.8 % @ 27/49 ms | the deficit was the client-facing path, not the member |

- **Consequence:** three changes are required - **(A) delivery** (renewal so
  storage scale-up can reach the data plane), **(B) distribution** (a storage
  epsilon-band so renewed/new connections spread across near-best members
  rather than one-hot), and **(C) seat** (a member that is the first-binding
  resource, so `t_db` has headroom to fall).
- **P6.1 band** (~60 s VIP re-arm artifact) remains an interpretive constraint,
  handled as in v4 (report as-is + artifact-excluded sensitivity as diagnostic).

## 2. Hard goals, acceptance and gate battery (pre-registered; frozen unless the author amends)

**Metric conventions (frozen):** episode windows only; phantom row =
`http_status 000` or `latency_s >= 300` excluded from percentile legs;
completion = share of episode rows with HTTP 200. **`t_db` primary =
per-window `avg_time_db_ms`** from `window_log_lanX.jsonl` ->
`domain_summary.avg_time_db_ms` (secondary `avg_time_db_read_ms`; both
reported). Seed-level t_db = median of the seed's episode window values
(l1/l2 separate).

**Evaluability (carries v4 S5.3 reduced-n rule):** a *seed pair* (H1) or *seed*
(H2) is evaluable iff all contributing runs are `valid` under v5 screening.
Cell verdict on evaluable units: n=7 -> >= 6/7; n=6 -> >= 5/6; n <= 5 ->
evidence-limited + author escalation.

| ID | Cell(s) | Criterion | Verdict rule |
| --- | --- | --- | --- |
| **H1-db** | `stor`@db vs paired `none`@db | per seed (paired): `median(t_db|stor)` <= **0.80 x** `median(t_db|none)`, **both lanes** | >= 6/7 evaluable pairs |
| **H2-db** | `stor`@db | v4 D14 protocol (full definition below), literal **and** win-max | >= 6/7 evaluable seeds |
| **H2-mx** | `stor`@mx | same D14 protocol | >= 6/7 evaluable seeds |
| H1-mx | `stor`@mx vs paired `none`@mx | same t_db rule as H1-db | **secondary.** Feasibility definition (frozen): the mx seat is NOT recalibrated in v5; H1-mx is promoted to hard in D22 iff the mx pilot pair (seed 45, same frozen seat) shows `median(t_db|stor pilot)` <= 0.80 x `median(t_db|none pilot)` on both lanes with the renewal census complete; otherwise it is reported with the pilot evidence and flagged to the author - never silently softened |
| Soft | all `stor` cells | completion / p50 / p95x / timeouts vs `none` (pooled-lane t_db ratio reported, descriptive) | reported only |

**D14 protocol (full definition, carried verbatim from v4 P5.04 S1):**
activation = earliest in-episode (>= ep0-5 s) of the `reserve_activate,storage_lanN`
decision row or the `[reserve] activated` line; **post-ready window = activation
+ 120 s -> episode end** (min 10 windows; fewer -> judge on available windows
and flag). **Literal variant:** busiest pre-add member (highest pre-add mean;
tie-break peak then MAC) own per-window CPU < 0.75 x its own pre-add peak.
**Win-max variant:** per-window max CPU across all members < 0.75 x pre-add
win-max peak. Shares descriptive; time-to-relief = first post-ready window
meeting the criterion. Thin pre-add baselines (3-5 windows in db) carry the v4
caveat.

**MC battery (carried from v4, EXCEPT MC1-db):** MC1(db) **redefined for the v5
seat** (explicit change): **member win-max mean over episode windows >= 90 %**;
MC1(mx) unchanged (member mean >= 33 % + `storage_above_threshold` >= 40 % of
episode rows); MC2 engagement; MC3 specificity; MC4 margin; MC5 liveness; G4
ceilings with the v4 scoped note.

**Base-requirements floor:** carry the **complete v4 S5.4 table verbatim** (all
IDs/magnitudes as registered in `v4/rq2/experiment_plan.md` S5.4; read it, do
not restate from memory), **amended by the seat change as follows:** rows whose
magnitudes are seat-calibrated are re-derived in W2 and re-registered in D22:
specifically V1 db (v4 "member >= 50 %" is superseded by MC1-db >= 90 %) and
db I1 (>= 5000 completed requests/LAN). If a carried magnitude is unreachable
at the frozen db seat, the pilot records the achieved value and D22 re-registers
the row **with author sign-off** - never silently waived. All other rows apply
as registered.

**Renewal evidence (census - corrected arithmetic):** per run record:
(i) controller broadcasts: `now` + `deferred` (worker retry) = 1 per storage
admission (failures logged and counted); (ii) edge fires: `wave=1` and `wave=2`
log lines; (iii) exceptions: `debounced`, `superseded` (a newer admission
replaced a pending schedule), `failed`. Requirements: fires == broadcasts x
waves - exceptions (recorded per class); every admission has a broadcast of
class now|deferred; any wave gap > 2 x configured gap is flagged.

## 3. W1 - Platform fix

### 3.1 Mechanism truths this design is built on (verified in code 2026-10-16)

1. **Warm lease = 30 s TTL window** (`_VIP_WARM_STORAGE_SECONDS=30`): created per
   promotion (`mark_storage_backend_warm`), evicted on expiry OR by
   `clear_storage_backend_warm` (called from `unregister_storage_backend` on
   scale-down); `_claim_warm_backend` returns a live-lease member for **every**
   connection born during the window (round-robin when several leases are
   live). One admission therefore *relocates* the connections born inside its
   window onto the newly promoted member.
2. `select_storage` = strict WSM argmin (round-robin only on exact ties); **no
   spread band** for storage (unlike `select_server`); unknown-stats default =
   1.0 (worst) for members without telemetry; warm claims short-circuit scoring
   entirely.
3. Flow-expiry re-installs reuse the recorded pin; only **new** connections
   re-run selection.
4. Therefore the design has three parts: **wave A** (immediate rotation; the
   warm window relocates reads off the pre-add member -> H2), **wave B** (a
   rotation after the warm TTL, when the epsilon-band is active -> reads
   distribute across near-best members -> H1), and the **band** itself (D21b;
   without it wave B re-concentrates - the round-2 finding).

### 3.2 Design

**a. Two waves per admission.** On each storage admission the controller
notifies edges once; each edge schedules per LAN: wave A immediately, wave B at
+`WAVE_GAP_S` (default 45 s > 30 s TTL). A new admission **supersedes** a
pending schedule (atomic; the pending wave B is cancelled and counted
`superseded`; each admission's wave A fires immediately regardless). Wave B's
spread premise holds when no promotion occurred within the preceding 30 s; the
census flags wave-B fire times falling inside a warm window.

**b. Storage epsilon-band spread (D21b) in `select_storage`.** Env-gated,
default OFF; v5 pins ON. Mechanics mirror `select_server`'s P2.6/P2.8 band
(`source/sdn_controller/_vip_routing/selection.py`, band block ~L231-284):
after the post-filter WSM costs are computed, the band = candidates with
`cost <= min_cost + EPS`; if the band would be smaller than `MIN_BAND` when a
candidate is a strict argmin by more than EPS, include the next-best
candidate(s) until the floor is met (same semantics as compute - re-read the
compute implementation and mirror it, do not improvise); round-robin within
the band (reuse/extend the domain's `rr_idx`); log with a distinct marker
`select_storage(%s): spread band=%d eps=%.3f floor=%d warm=%s chosen=...`.
Knobs: `STORAGE_SELECTION_SPREAD_EPS` (default 0.0 = OFF),
`STORAGE_SELECTION_SPREAD_MIN_BAND` (default 0). **v5 pins EPS=0.03,
MIN_BAND=2** (D22 may re-pin within 0.02-0.05 / 2-3 with pilot evidence).
The band must respect the existing `prefer_secondary` filter (band over the
post-filter candidate set only) and must not fire when a warm claim already
returned.

**c. Levers classification.** Timing/policy levers (waves, `WAVE_GAP_S`,
debounce, EPS, MIN_BAND) may be re-pinned via D22. **Any other selection-math
change requires a new decision ID** before use.

### 3.3 Invariants (reviewer check-list)

1. Never re-pin a live stream: each wave creates a new epoch; the old epoch is
   retired and closed by the existing lease-drain/housekeeping machinery - do
   not bypass it.
2. Same-VIP rotation is intentional: use `_rotate_current_epoch_locked`
   directly (`next_vip_ip = state.normal_vip_ip`); `apply_vip_update`'s
   VIP-change guard stays untouched.
3. Debounce applies to wave A only (per LAN); wave B is edge-scheduled and not
   debounced.
4. Double-gated: controller `STORAGE_POOL_RENEW_ENABLED` (default 0) and edge
   `EDGE_POOL_RENEW_ENABLED` (default 0). Either unset => v4 behaviour.
   Band double-gated too: default 0.0/0 => exact v4 `select_storage`.
5. No selection-math changes beyond the D21b band (see 3.2c).

### 3.4 Edge changes (image `edge_server`)

**a. `edge_server_config.py`** - add and wire in `from_env()` (follow the
`mongo_client_retire_grace_s` pattern):

```python
pool_renew_enabled=(os.environ.get("EDGE_POOL_RENEW_ENABLED", "0").strip() == "1"),
pool_renew_min_interval_s=float(os.environ.get("EDGE_POOL_RENEW_MIN_INTERVAL_S", "15")),
pool_renew_waves=int(os.environ.get("EDGE_POOL_RENEW_WAVES", "2")),
pool_renew_wave_gap_s=float(os.environ.get("EDGE_POOL_RENEW_WAVE_GAP_S", "45")),
```

**b. `vip_data_mongo_runtime.py`** - module state + atomic scheduler. Lock order
(documented): `_pool_renew_lock` may be held while taking `state.lifecycle_lock`
(the reverse never happens; `_get_lan_epoch_state` is called before any lock).

```python
_pool_renew_lock = threading.Lock()
_pool_renew_last_at: dict[str, float] = {}
_pool_renew_timers: dict[str, list[threading.Timer]] = {}

def _rotate_renewed_epoch(lan: str, reason: str, wave: int) -> dict:
    state = _get_lan_epoch_state(lan)
    with state.lifecycle_lock:
        if state.normal_vip_ip is None:
            raise StorageVipConfigurationError(f"missing normal VIP mapping for {lan}")
        new_epoch = _rotate_current_epoch_locked(
            lan, state, reason=f"pool_renew:{reason}:w{wave}",
            next_mode="normal", next_vip_ip=state.normal_vip_ip)
        epoch_id = new_epoch.epoch_id
    log.info("pool_renew: lan=%s reason=%s wave=%d new_epoch=%s", lan, reason, wave, epoch_id)
    return {"rotated": True, "reason": reason, "lane": lan, "wave": wave, "epoch_id": epoch_id}

def renew_current_epoch(lan: str, reason: str) -> dict:
    """Wave A now + wave B after the warm-lease TTL (admission-time renewal)."""
    if not CONFIG.pool_renew_enabled:
        return {"rotated": False, "reason": "disabled", "lane": lan, "wave": 0, "epoch_id": None}
    state = _get_lan_epoch_state(lan)
    superseded = 0
    with _pool_renew_lock:                      # atomic cancel + debounce + store
        now = time.monotonic()
        if now - _pool_renew_last_at.get(lan, 0.0) < CONFIG.pool_renew_min_interval_s:
            with state.lifecycle_lock:
                current_id = state.current.epoch_id if state.current else None
            return {"rotated": False, "reason": "debounced", "lane": lan, "wave": 0,
                    "epoch_id": current_id}
        _pool_renew_last_at[lan] = now
        superseded = len(_pool_renew_timers.get(lan, []))
        for t in _pool_renew_timers.pop(lan, []):
            t.cancel()
        if superseded:
            log.info("pool_renew: lan=%s superseded=%d pending wave(s)", lan, superseded)
        result = _rotate_renewed_epoch(lan, reason, wave=1)   # wave A
        timers: list[threading.Timer] = []
        for wave in range(2, CONFIG.pool_renew_waves + 1):    # v5 ships 2; increases are D22 levers
            t = threading.Timer(
                CONFIG.pool_renew_wave_gap_s * (wave - 1),
                _rotate_renewed_epoch, args=(lan, reason, wave))
            t.daemon = True
            timers.append(t)
        _pool_renew_timers[lan] = timers
        for t in timers:
            t.start()
    return result
```

(All cancel/store/start happen under one `_pool_renew_lock` acquisition - no
gap for a racing admission; superseded timers are counted and logged.)

**c. `control_plane_routes.py`** - new POST route; **imports must be extended**
(add `renew_current_epoch`, `snapshot_normal_vip_config` to the
`vip_data_mongo_runtime` import list; use the in-scope `process_state` for the
edge's own LAN (`process_state.config.lan_id`) - do NOT import CONFIG newly):

```python
@app.route("/pool_renew", methods=["POST"])
def pool_renew():
    body = request.get_json(silent=True) or {}
    lan = body.get("lan")
    known = set(snapshot_normal_vip_config().keys())
    if not isinstance(lan, str) or lan not in known or lan != process_state.config.lan_id:
        return jsonify({"error": "unknown or mismatched lan", "lan": lan}), 400
    result = renew_current_epoch(lan, reason=str(body.get("reason", "unspecified")))
    return jsonify(result), 200
```

**d. `edge_server_process_state.py`** - add `"/pool_renew"` to
`SKIP_COUNTING_PATHS` so the new control route is excluded from workload
counters. (Scope note: `/vip_data`, `/tier1_manifest`, `/wait_time` are not in
the set today - their treatment is unchanged, out of v5 scope.)

### 3.5 Controller changes (mirror edits `main_n1.py` AND `main_n2.py`)

**a. `scaling_config.py`:**

```python
_STORAGE_POOL_RENEW_ENABLED = os.environ.get("STORAGE_POOL_RENEW_ENABLED", "0").strip() == "1"
_STORAGE_SELECTION_SPREAD_EPS = float(os.environ.get("STORAGE_SELECTION_SPREAD_EPS", "0.0"))
_STORAGE_SELECTION_SPREAD_MIN_BAND = int(os.environ.get("STORAGE_SELECTION_SPREAD_MIN_BAND", "0"))
```

Add `_STORAGE_POOL_RENEW_ENABLED` to each main file's
`from scaling_config import (...)` list (they import constants explicitly). The
selection module imports the two band constants from `..scaling_config`
(matching its existing import block).

**b. Non-blocking, lossless broadcast.** Worker thread + lock-guarded
in-flight flag + one pending retry (a deferred admission is retried when the
current fan-out completes - never dropped). Under os-ken's monkey-patched
threading this worker is cooperative; it is still bounded by
`nodes x timeout(1.5 s)` and reads node maps by value:

```python
def _broadcast_pool_renew(self, domain: str) -> None:
    """POST /pool_renew on every edge server of this LAN after a storage admission."""
    if not _STORAGE_POOL_RENEW_ENABLED:
        return
    with self._pool_renew_lock:
        if self._pool_renew_inflight:
            self._pool_renew_pending = True
            logger.info("[pool_renew] broadcast deferred domain=%s", domain)
            return
        self._pool_renew_inflight = True
    threading.Thread(target=self._pool_renew_worker, args=(domain,),
                     daemon=True, name="pool-renew-fanout").start()

def _pool_renew_worker(self, domain: str) -> None:
    pending = True
    while pending:
        with self._pool_renew_lock:
            self._pool_renew_pending = False
        sent = 0
        for mac in list(self._local_server_macs):
            ip = self._mac_to_ip.get(mac)
            if not ip:
                continue
            url = f"http://{ip}:5000/pool_renew"
            try:
                requests.post(url, json={"lan": self._lan_id,
                                         "reason": "storage_admission"}, timeout=1.5)
                sent += 1
            except requests.RequestException as exc:
                logger.warning("[pool_renew] POST %s failed: %s", url, exc)
        logger.info("[pool_renew] broadcast domain=%s nodes=%d", domain, sent)
        with self._pool_renew_lock:
            pending = self._pool_renew_pending
            if not pending:
                self._pool_renew_inflight = False
```

(init `self._pool_renew_lock = threading.Lock()`,
`self._pool_renew_inflight = False`, `self._pool_renew_pending = False` with
the controller's other state. Census classes: `broadcast` now/deferred;
`failed` logged.)

**c. Call site - the single choke point:**

```python
def _promote_storage_backend(self, mac: str, domain: str) -> None:
    self.add_storage_mac(mac, domain)
    self.mark_storage_backend_warm(mac, domain)
    self._broadcast_pool_renew(domain)      # NEW - admission-time renewal
    logger.info("[vip_data] promoted storage mac=%s domain=%s", mac, domain)
```

Coverage (corrected): ALL admission paths funnel through
`self._promote_storage_backend` - reserve activation, stabilized recall,
cross-region warm admission, AND the telemetry-driven consumers
(`promote_storage_from_telemetry` / `process_secondary_events` receive it as
their `add_storage_mac_fn` from `_on_telemetry_update`). Ordering: promote ->
broadcast (member selectable before wave A).

### 3.6 Plumbing and provenance

1. **Static edges:** `source/scripts/network/build_network_1.sh` +
   `build_network_2.sh` - in the `edge_server` `docker run` env block, insert
   the four `-e EDGE_POOL_RENEW_*` lines **before the final `edge_server` image
   token** (the block currently ends `-e EDGE_MONGO_MAX_POOL_SIZE=... \` then
   `edge_server`):

```bash
  -e EDGE_POOL_RENEW_ENABLED=${EDGE_POOL_RENEW_ENABLED:-0} \
  -e EDGE_POOL_RENEW_MIN_INTERVAL_S=${EDGE_POOL_RENEW_MIN_INTERVAL_S:-15} \
  -e EDGE_POOL_RENEW_WAVES=${EDGE_POOL_RENEW_WAVES:-2} \
  -e EDGE_POOL_RENEW_WAVE_GAP_S=${EDGE_POOL_RENEW_WAVE_GAP_S:-45} \
```

2. **Dynamic edges (mandatory):** `source/sdn_controller/elasticity/compute_node_manager.py`
   `_docker_run_server` (env list ~L265-270) - add the same four
   `"-e", f"EDGE_POOL_RENEW_...={os.environ.get('EDGE_POOL_RENEW_...', '<default>')}"`
   entries (matching the file's existing pattern). The controller process env
   is the single source (see 3.6.4), so dynamic edges inherit the pinned values.

3. **Launcher:** copy `source/scripts/testing/rq2v4_launch_run.sh` ->
   `source/scripts/testing/rq2v5_launch_run.sh`. Changes: (a) usage/echo tokens
   `rq2v4` -> `rq2v5`; (b) **`MODE_ENV` path stays
   `source/scripts/testing/controller_env_overrides/rq2v4_mode_${MODE}.env`**
   (D23 reuse; no rename, no duplicates); (c) single-source lift: after
   building `MERGED_ENV`, lift each of the four `EDGE_POOL_RENEW_*` values from
   the merged env into the make-var block exactly like the existing
   `MERGED_HASH` pattern (one `sed`-lift per var; make-var defaults only when
   unset); (d) do NOT export the values independently of the pins file
   (single source of truth).

4. **Pins file (single source; no canonical edit):** create
   `source/scripts/testing/controller_env_overrides/rq2v5_pins.env` carrying:
   `STORAGE_POOL_RENEW_ENABLED=1`,
   `STORAGE_SELECTION_SPREAD_EPS=0.03`,
   `STORAGE_SELECTION_SPREAD_MIN_BAND=2`,
   `EDGE_POOL_RENEW_ENABLED=1`,
   `EDGE_POOL_RENEW_MIN_INTERVAL_S=15`,
   `EDGE_POOL_RENEW_WAVES=2`,
   `EDGE_POOL_RENEW_WAVE_GAP_S=45`.
   The v5 launcher merges it as an extra env file on every run (v4
   `rq2v4_p4_pins.env` precedent) => (i) captured verbatim in the run's
   `controller_env_snapshot.env` (provenance); (ii) controller process env =>
   dynamic spawns; (iii) launcher lift => static edge `-e`.
   **`current_state_integrated.env` stays untouched.**

5. **Seat + flag provenance in artifacts:** `rq2v5_run_status.csv` carries
   `edge_cpus`, `storage_cpus`, `pool_renew_enabled`, `pool_renew_wave_gap_s`,
   `spread_eps`, `spread_min_band` columns. W2/W3 preflight witnesses: static
   edge via `docker exec edge_server_n1 printenv EDGE_POOL_RENEW_ENABLED
   EDGE_POOL_RENEW_WAVE_GAP_S`; **dynamic edge**: after the first `both` run of
   each regime, the same witness on a live dynamic unit; both recorded in the
   pilot/battery evidence. `phases_snapshot.json` D3 check as v4.

6. **Images:** rebuild `edge_server` on the VM; record image id + content hash
   in the W2 pilot evidence. Unset flags => v4 behaviour (compat).

7. **`phases.json` (canonical workload file) - edit in place per regime, no
   variants.** W2 copies two reference shapes INTO this folder for repo
   visibility: `rq2v5_ref_phases_mx.json` (from the v4 mx run
   `20261013_161442_rq2v4_none_mx_45` `phases_snapshot.json`) and
   `rq2v5_ref_phases_db.json` (from the v4 db run
   `20261014_113032_rq2v4_none_db_43`), plus a byte-copy of the canonical
   file's pre-campaign content as `rq2v5_ref_phases_restore.json`. Edit
   `phases.json` in place before each regime block (regime-major), verify via
   the D3 check on the first run of each regime, and at campaign close restore
   the canonical file byte-exactly from `rq2v5_ref_phases_restore.json`.

### 3.7 Tests (W1 exit evidence)

1. New selftest `source/scripts/testing/rq2v5_p1_01_pool_renew_selftest.py`
   (standalone, house style; runs on the VM where `pymongo` is importable; env
   read at import time => the test spawns itself as subprocesses with different
   env):
   a. flag off -> `disabled`; no epoch change;
   b. flag on -> wave A: `epoch_id` increments (via
      `_get_current_epoch_snapshot`), previous epoch marked retiring;
   c. immediate second POST -> `debounced`;
   d. lane mismatch -> 400; unknown LAN -> 400; malformed body -> 400;
   e. **wave B**: with `EDGE_POOL_RENEW_WAVE_GAP_S=1`, a second rotation
      appears within ~2 s AND not before ~1 s (wave-B timing bound);
   f. **supersession**: two POSTs spaced > debounce and < gap -> the first
      wave B is cancelled, counted `superseded`, exactly one wave B remains;
   g. **retire/close**: after rotation the previous epoch's client is closed by
      the housekeeping sweep once leases drain (assert via the epoch snapshot /
      close log).
2. `python -m py_compile` clean on every touched `.py`.
3. A storage-band selftest case in the same script family: with two synthetic
   member costs `[0.80, 0.82]`, EPS=0.03/floor=2 -> both in the band and
   selection round-robins (assert alternating picks); with EPS=0 -> strict
   argmin restored. (Drive `select_storage` with a stub controller; no network.)
4. W2 pilot census: broadcasts == admissions; fires == broadcasts x waves -
   recorded exceptions.

## 4. W2 - Seat calibration and pilot (runner)

**Seat delta (explicit, both quotas):** db runs pin **`STORAGE_CPUS` in
0.07-0.11 (start 0.09)** AND **`EDGE_CPUS=1.20`** (v4 db seat - the launcher
default 0.15 must NOT be used for db). mx keeps the v4 seat (`sc=0.05`,
`ec=0.15`). Nothing else changes (rates, mix, phases shape from 3.6.7).

Rationale: at `sc=0.15` the member sat ~69 % with flat ~62 ms `t_db` - no
headroom for H1; a saturated member is required so added storage capacity
lowers `t_db`.

**Pilot runs** (labels `rq2v5_p2_pilot_*`, seed **45** for the pair, standard db
schedule ~24 min, budget <= 5 runs ~2 h):

1. `none`@db at `sc=0.09` - **P-A:** member win-max mean >= 90 %; delivery
   deficit >= 8 pp vs offered; `t_db` median >= 120 ms (~2x v4 floor); edge CPU
   moderate (< 70 %).
2. `stor`@db at `sc=0.09` (fix + band on) - **P-B:** (i) renewal census
   complete (S2); (ii) **distribution**: >= 2 members carrying reads post-ready
   and busiest pre-add member CPU dropping (H2 direction); (iii) `t_db` median
   <= 0.80 x the none pilot's (H1 direction); (iv) band marker present in
   controller logs (`select_storage ... spread band=`).
3. P-A fail -> retry at `sc=0.07`. P-B fail WITH census present -> **stop and
   escalate to the author**; allowed escalation levers: wave/gap/debounce and
   EPS/MIN_BAND re-pinning (D22, within 0.02-0.05 / 2-3) - any further
   selection-math change needs a new decision ID first.
4. One confirmation repeat of the `stor` pilot at the frozen value.
5. Floor re-derivation (S2): record achieved db I1 and the seat-conditional
   rows; prepare D22's re-registration text for author sign-off if needed.

**Freeze (D22):** final `sc`, pilot numbers, H1-mx promote/report decision,
floor-row re-registrations, and the created **`experiment_plan.md`** (battery
contract: matrix S5, gates S2, seat D22). W3 cannot start before D22.

## 5. W3 - Battery (56 runs)

| Block | Cells | Seeds | Runs | ec / sc / band | Order discipline |
| --- | --- | --- | --- | --- | --- |
| mx | `both` / `comp` / `stor` / `none` | 42-48 | 28 | 0.15 / 0.05 / pins | v4 per-regime seed rotation, regime-major blocks, identical mode order to v4 for pairing |
| db | `both` / `comp` / `stor` / `none` | 42-48 | 28 | 1.20 / D22-frozen / pins | same |

- Labels `rq2v5_<mode>_<regime>_<seed>`; standard run-folder layout; VM dir
  `~/rq2v5_battery/` (adapted from the v4 battery).
- `phases.json` edited in place per regime (3.6.7); D3 check on each block's
  first run; env snapshot shows the pins values.
- **Replacement/top-up rules - carry v4's registered rules verbatim** (read
  `v4/rq2/experiment_plan.md` S5.5 + D20: incident-class replacements only,
  spares <= 14 with sign-off, > 4 replacements per regime => stop + escalate,
  per-cell cap as registered; all rows in `rq2v5_run_status.csv`).
- Pacing ~30 h + deploy overhead; v4 F2 (floor) quiescence + stop triggers
  carried.
- Preflight per regime: seat + flag witness (static + dynamic, 3.6.5);
  controller env snapshot contains the pins values.

## 6. W4 - Analysis and close-out

- Adapt the v4 pipeline: per-run metrics (p5mx-style), D14 tooling
  (g1lock-style) for H2, `t_db` extraction (window_log `avg_time_db_ms` +
  per-server `avg_time_db_read_ms`), renewal census (S2), band-marker census.
  Outputs: `rq2v5_cell_stats.csv`, `rq2v5_run_status.csv`.
- Verdicts: **H1-db, H2-db, H2-mx** (+H1-mx per D22) + carried battery (S2) +
  base floor (v4 S5.4 as amended by D22).
- Deliverables: `results.md`, `post_run_analysis.md`, cross-mode comparison
  graphs, VM retention (slim-archive after analysis).
- **Documentation updates:**
  - `docs/operation/vip_routing/vip_data_edge_epoch_and_recovery.md` - add the
    admission-time renewal trigger (endpoint, flags, wave semantics, invariants).
  - `docs/operation/vip_routing/vip_routing_backend_selection_and_warm_leases.md` -
    document the renewal/wave/warm-lease interaction and the storage
    epsilon-band (D21b) alongside the compute band precedent.
  - **Annotate the v4 registrations this plan overrides** (precedence (a)):
    `v4/rq2/experiment_plan.md` S5.2 G3 row (`stor`@mx) and
    `rq2v4_p5_03_mx_regime_report.md` S2.3 - one-line "v5 override (hard goal
    for rq2v5)" pointer each.
  - v4 records D21 row + P5.04 S9 pointer: already landed 2026-10-16 (verify
    wording; D21's registration authority is this plan; D21b/D22/D23 live here).
  - Known stale doc bits (`edge_storage_connection_epoch_visuals.md`
    recovery_vip_ip/breaker) - OUT of scope; flagged to the author.

## 7. Risks and mitigations

| # | Risk | Mitigation |
| --- | --- | --- |
| 7.1 | Renewal relocates rather than spreads | D21b band + wave B after the 30 s TTL; pilot P-B(ii)/(iv) verifies; census flags wave-B fires inside warm windows |
| 7.2 | Band parameters mis-tuned (over-spread hurts t_db via weakest member) | EPS/floor are pins; D22 re-pins within 0.02-0.05 / 2-3 with pilot evidence; H1 gates the outcome |
| 7.3 | Unknown-stats cost (1.0) biases fresh members | Wave B runs with live stats (~10 s cadence); band floor keeps fresh members eligible; pilot observes |
| 7.4 | Rotation churn vs the P6.1 band | 2 waves per admission (2-6/lane/episode); band census per run vs v4; material worsening => finding |
| 7.5 | Controller worker blocked/cooperative under eventlet | worker is bounded (nodes x 1.5 s), reads maps by value, lossless deferred retry (3.5b) |
| 7.6 | OOM class (db edge memory) persists | v4 replacement/top-up rules carried (S5) |
| 7.7 | Comparability | v5 = new platform segment; never pool with v4; cb unaffected (no in-episode admissions + default-off flags) |
| 7.8 | `t_db` mixes write ops | Primary `avg_time_db_ms` (the author's metric); secondary `avg_time_db_read_ms` |

## 8. Deliverables and file map

**Created:** `source/scripts/testing/rq2v5_launch_run.sh`;
`source/scripts/testing/rq2v5_p1_01_pool_renew_selftest.py`;
`source/scripts/testing/controller_env_overrides/rq2v5_pins.env`;
`rq2v5_w1_01_path_binding_evidence.md`, `rq2v5_ref_phases_mx.json`,
`rq2v5_ref_phases_db.json`, `rq2v5_ref_phases_restore.json`, (W2)
`experiment_plan.md`, (W4) `rq2v5_cell_stats.csv`, `rq2v5_run_status.csv`,
`results.md`, `post_run_analysis.md` (all in this folder); VM `~/rq2v5_battery/`.
**Modified (code):** edge: `edge_server_config.py`, `vip_data_mongo_runtime.py`,
`control_plane_routes.py` (incl. extended import list),
`edge_server_process_state.py`; controller: `scaling_config.py`,
`_vip_routing/selection.py` (D21b band + band-constant imports), `main_n1.py`,
`main_n2.py` (flag import + broadcast worker), `elasticity/compute_node_manager.py`;
network: `build_network_1.sh`, `build_network_2.sh`.
**Modified (records/workload):** `source/scripts/testing/phases.json` (in place
per regime; restored byte-exactly at close);
`docs/operation/vip_routing/*` (two docs, S6); v4 `experiment_plan.md` S5.2 +
`rq2v4_p5_03_mx_regime_report.md` S2.3 (override annotations) + `rq2v4_p5_04`
(S9 landed).
**Reused unchanged (D23):** `rq2v4_mode_*.env`; `current_state_integrated.env`.

## Changelog

| Date | Change | Rationale |
| --- | --- | --- |
| 2026-10-16 | Authored plan (v1); **D21** registered: admission-time epoch-renewal fix + recalibrated db seat; hard goals H1/H2; scope 56 runs (mx+db) | Author directive (2026-10-16) |
| 2026-10-16 | **v2 after review round 1** (3 critical / 19 warning / 13 observation): two-wave renewal; dynamic-edge env; non-blocking fan-out; pins-file provenance; per-regime phases procedure; full D14 + reduced-n + base-floor carries; MC1-db explicit; census/pointers corrected | auto-review round 1 |
| 2026-10-16 | **v3 after review round 2** (2 critical / 8 warning / 14 observation): **D21b storage epsilon-band added** (renewal alone relocates; argmin is one-hot - the band is the H1/H2 distribution mechanism, env-gated, mirroring the compute P2.6/P2.8 precedent); lossless broadcast worker; atomic edge scheduler (superseded counted); single-source knobs (pins -> merged env -> lifts); route imports corrected; explicit band/floor/wave D22 ranges; floor re-derivation policy; v4 override annotations; D23 registered (mode-env reuse); W1 path-binding evidence deposit; H1-mx feasibility definition; selftest coverage expanded | auto-review round 2 |
| - | **D22** (pending W2): frozen db seat `sc=...`; pilot numbers; H1-mx decision; floor re-registrations; `experiment_plan.md` created | W2 calibration |
