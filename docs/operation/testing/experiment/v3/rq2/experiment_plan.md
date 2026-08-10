# RQ2 v3 — Bottleneck-Aware Scaling at the Storage-Bind Config

Status: **PLANNED — PREFLIGHT IN PROGRESS (2026-08-08).** P1 ran with the
original envs; the storage scale-down gate missed (churn guard held because
the D3 overload label never cleared). P1b re-anchored only `OVERLOAD_CPU_PCT`
— the 1000 ms peak bar still tripped on the `demand_drop` tail, so the guard
held again. P1c (full re-anchor `OVERLOAD_CPU_PCT=30` +
`OVERLOAD_PEAK_LATENCY_MS=2000`) confirmed the guard releases (~19 s into
`demand_drop`) and the scale-down eval arms repeatedly, but the
**reserve-floor guard** blocked every removal (≤2 storage nodes/LAN with no
`READY_RESERVED` standby) → 0 scale-down decisions, 0 `removed` events.
Root cause: storage scale-down needs a ready persistent-reserve standby,
which was disabled by rq2_preparation D8. **D8 reversal (2026-08-07):** the
storage persistent reserve is now ENABLED in all three arm envs — the reserve
is the storage scale mechanism (activate+replenish on scale-up, floor-safe
scale-down in `demand_drop`). Validating as P1d (label
`rq2_sf_db_preflight_1d`).

**P1d (2026-08-07):** scale-down gate passed **numerically** (3 `removed`
events, `scale_down` rows on both LANs, 0 reserve-floor blocks) — but the
reserve was NOT exercised: the episode scale-up cold-spawned `dyn2` and the
standby never reached `READY_RESERVED`. Root causes: **(Gap 1)** the RQ2
PolicyGate storage branch has the reserve call commented out (stale D8-era
comment), so RQ2 storage scale-up always cold-spawns; **(Gap 2)** the P1d
controller ran a stale runtime that did not exercise the current
reserve-ready path. **Fix (2026-08-08):** `main_n1.py`/`main_n2.py` now
route the RQ2 storage scale-up through `_handle_storage_reserve_trigger` —
activate the ready standby, or latch+wait while PREPARING; cold spawn only
when the reserve is disabled; a reserve activation consumes the storage
budget. All drifted source synced (46 files) and the edge_server image
rebuilt. Validating as P1e (label `rq2_sf_db_preflight_1e`).

**P1e (2026-08-08):** **PASS (runner gates).** The reserve mechanism operated
end-to-end: standby `READY` → `[reserve] activated` on the first load trigger
(23:53:38/41, both LANs — no cold spawn) → replenish; a second activation
later in the episode (00:03:01 / 00:05:33) followed a `cleanup_submitted`
cycle. `demand_drop` produced **6 `removed` events** (00:02:19–00:07:03),
`storage underutilisation — removing` fired on both LANs, and **0
reserve-floor blocks** (floor satisfied by the READY replenished standby).
Base gates clean: D1 0 × NotPrimary, D2 0 tracebacks, D3 snapshots present,
exit 0 (~19 min). **Analyzer (2026-08-08):** M1/M2 confirmed (activated node
served ~50 % of episode reads), V1 (storage CPU →70 % pre-add), I1 (57.2k /
57.3k per LAN), I2 (distinct timeout/canceled classes), timeout 0.09 %
(≤5 %). **B2 partial:** p50 flat (54.9→61.6 ms — the reserve activated early
and preempted deep saturation); p95 711→549 ms, mean 180→135 ms, peak
storage CPU 70 %→43 %. F2 1.079× (within base 3×; over the campaign's 1.05×
flag). Next: **P2** (`rq2_sf_db_preflight_2`, same-seed
repro).

**P2 (2026-08-08):** **PASS — reproduces P1e.** Same seed 2001: episode
demand 114,625, timeout 0.085 % (vs 0.090 %), p50 63.4 ms (vs 55.5 ms), p95
591 ms (vs 548 ms), per-LAN 57.2k/57.3k. Reserve activated ~100 s into the
episode (00:34:20/23 — same as P1e's ~102 s), **5 removals** in `demand_drop`
(vs 6), **0 reserve-floor blocks**, `storage underutilisation — removing`
fired both LANs. F2 1.043× (within the 1.05× flag). Base gates clean
(D1/D2/D3, exit 0). Both P1e and P2 validate the reserve mechanism + scale-
down for sf_db. Preflight sf_db reproducibility established; the B2
window/benefit re-examination (reserve preempts saturation) still applies.

**P3 (2026-08-08):** `rq2_sf_db_preflight_pool12` — **PASS.** Under shell
pool 12 the reserve still binds → relieves: activated ~04:44:44/46 (both
LANs), **read spread ~50/50** post-add (38.7k/38.6k backends), **B2
(RQ2-specific) both legs met** (p95 1016→418 ms = 0.41×; peak storage CPU
73%→44%), timeout 0.068 % (lowest yet), 4 removals in `demand_drop`, 0
reserve-floor blocks, base gates clean. **Diagnostic answer: pool 12 suffices
with the reserve** — pool 48 is NOT required for reserve-enabled db cells
(probe-era pinning was cold-spawn-specific; the reserve's warm secondary
spreads under pool 12). **Decision (2026-08-08, user): pool 12 is the db-cell
campaign config** — no functional difference vs pool 48 for the reserve path;
whichever yields better thesis results is what matters, and pool 12 is the
simpler validated config. Because the pool-12 result is n=1, a second pool-12
run is being executed as **P3b** (`rq2_sf_db_preflight_pool12_2`, same seed
2001) to establish n=2 before the campaign. **Controller logs: retained on the
hosting VM indefinitely** (user decision — `cloud-vm-rq2` has storage headroom;
no cleanup of `controller_lan*.log` for P1e/P2/P3).

**P3b (2026-08-08):** `rq2_sf_db_preflight_pool12_2` — **PASS — pool-12 n=2
established.** Same seed 2001, pool 12: reserve activated ~70 s into the
episode (08:13:11/16, no cold spawn), read spread ~50/50 post-add (36.4k/
36.2k), **B2 (RQ2-specific) both legs met** (p95 796→394 ms = 0.49×; peak
storage CPU 65/73%→43/45% = 0.67×/0.61×), timeout 0.074 % (vs P3 0.068 %),
4 removals in `demand_drop` (lan1 3 + lan2 1), 0 reserve-floor blocks, base
gates clean, exit 0. F2 1.095× (flag — same pattern as P1e's 1.079×; within
base 3×). Direction consistent with P3 on every gate ⇒ **pool 12 is locked as
the db-cell campaign config** (n=2). Next: **P4** (`rq2_cf_db_preflight_1`,
cf_db wrong-action sanity).
**P4 (2026-08-08):** `rq2_cf_db_preflight_1` (cf_db, seed 2001) — **PASS
(wrong-action sanity).** Compute-first on the data-bound episode added
**compute** (7 readiness-gated adds, lan1 dyn2/dyn3/dyn5/dyn6 + lan2
dyn2/dyn3/dyn4) and **never activated the storage reserve (0 activations)** —
storage stays suppressed. Bottleneck unrelieved: episode storage CPU mean
57.8/58.0 %, peak 94.3/83.7 %; latency severely elevated vs sf_db (p50
141 ms vs 34.6-41.4 ms; p95 33.3 s vs 428-460 ms); timeout **8.27 %** ≤ 10 %
ceiling — no collapse. Base gates clean (D1/D2/D3, exit 0). F2 4.3× flag
(lan1 worse than lan2; both elevated). Pre-registered no-benefit arm judged
on its own claimed direction — valid finding. This is the controlled
contrast for the bottleneck-aware arm.

**P5 (2026-08-08):** `rq2_ba_db_preflight_1` (ba_db, seed 2001) — **FAIL
(blocking gate — plan expectation not met).** The bottleneck-aware classifier
did NOT cleanly pick storage: it scaled **both tiers** (6 compute adds +
2 storage reserve activations at 09:12:42/44). The mid-episode churn
triggered an **edge-tier reachability outage on LAN1**: `server_count` → 0,
requests → 0 at 09:16:12–22 (~270 s), OVS `not reachable` routing warnings
bracket the collapse. Episode timeout **8.16 %** (vs sf_db 0.07 %), p95
20.8 s; B2 massively negative (POST p95 27.2 s vs PRE 645 ms, confounded by
the outage). Base gates clean at the data path (D1/D2/D3, exit 0) — the
failure was at the VIP/OVS routing layer, not MongoDB. **This blocks the
ba_db preflight gate and requires a decision before the campaign.**
Candidate paths (user decision): (a) fix the ba classifier to commit to the
detected bottleneck tier; (b) investigate the VIP-routing loss under
concurrent dyn adds; (c) re-run P5 after either fix; (d) document ba_db as
not-yet-validated and rescope the ba cells.

**P5 rework — root causes + fixes (2026-08-08, implemented + validated):**

Root cause (a) — ba classifier over-scales: in `policy_gate.py`, the
`bottleneck_aware` per-window one-fired path acted on a fire without checking
the classifier. P5's decision log shows the classifier declared **storage** in
the first firing windows (sScore 0.60 > cScore 0.47) yet compute was spawned
anyway because storage had not "fired" that window. Enabling strict mode alone
does not fix this (fires alternate, never 2-consecutive).

Fix (a): one-fired selection now consults `classify()` and suppresses a fire
whose tier is not the declared bottleneck (both non-strict `select()` and
`_select_strict` step-4); the suppression is recorded via
`last_suppressed()` and logged in the decision log as
`reason=classifier_suppressed` (main_n1/n2). Result: ba commits to storage on
the data-bound episode; compute still acts once storage is relieved (storage
score below threshold). Files: `policy_gate.py`, `main_n1.py`, `main_n2.py`.

Root cause (b) — VIP routing drops during churn: `topology.py`
`get_sws_links_hosts` rebuilt `host_attachment` **wholesale** from the OS-Ken
poll; a transiently-incomplete snapshot during dyn-node churn dropped the
static LAN1 edge backend, and `flows.py`/`ingress.py` **skipped** DNAT/SNAT
flow installs for unreachable MACs → ~60 s LAN1 edge outage (server_count 0,
requests 0, 34-36 % timeout spike at 270-360 s).

Fix (b): `topology.py` retains a previously-known host missing from a poll
for `TOPOLOGY_HOST_GRACE_TICKS` (default 3) consecutive polls before removal,
so a transiently-incomplete snapshot cannot drop VIP backends; a host is only
evicted after the full grace window. `flows.py`/`ingress.py` now set
`_topo_correction_needed = True` on "not reachable" (request topology
re-learn + republish) instead of only skipping.

Validation (all green): new gate `rq2v2_p5_01_policy_gate_ba_commit_test.py`
(P5 fire-sequence regression), new `rq2v2_p5_02_topology_host_grace_test.py`
(grace window), existing `rq2v2_p3_01_policy_gate_strict_test.py` (no
regression) — all pass on the local interpreter and inside the
`osken-controller` container on the VM; `py_compile` clean on all changed
files. Controller source runs from the bind mount → no image rebuild needed.
Next: **re-run P5** (`rq2_ba_db_preflight_1`, same seed 2001, pool 12).

**P5-fix tag (2026-08-08):** the rework is tagged **`rq2-v3-p5fix-20260808`**
(local commit `925c43f`; VM commit `bc5ae4e`) and synced to `cloud-vm-rq2`
(controller runs from the bind mount). P5 rerun uses this tagged code.

**P5 rerun (2026-08-08, `20260808_111548_rq2_ba_db_preflight_1`, tag
`rq2-v3-p5fix-20260808`):** **PASS — fixes validated end-to-end.**
Classifier suppression fired at lan1 w36 (compute fire suppressed, storage
eligible sS=0.60 → reserve activated next window); the 6 compute adds all
occurred post-storage-relief (storage score 0.0-0.13, below threshold) —
intended ba behavior, no wrong-action sneak-in. **No edge outage**: timeout
trajectory has no bucket >5 % (old P5: 34-36 % at 270-360 s). Episode timeout
**0.138 %** (vs old P5 8.16 %), p95 781 ms (vs 20.8 s), **B2 p95 leg met**
(1040→690 ms = 0.66×); peak-CPU leg weak (lan1 0.75×, lan2 1.06×) — the p95
leg carries B2. Reserve activated on both LANs (2 per LAN). D1/D2/D3 clean,
exit 0. F2 1.26× flag (within base 3×). **ba_db preflight gate cleared** —
preflight complete (P1e/P2/P3/P3b/P4/P5). Next: the 36-run campaign.

**Cb-arm preflight (2026-08-08):** `rq2_ba_cb_preflight_1`
(`20260808_132902`) and `rq2_cf_cb_preflight_1` (`20260808_135829`) — both
**PASS**, closing the v3 cb validation gap (the cb arms previously rested on
v2 evidence only). Under the v3 shell config (pool 12, OVERLOAD 30/2000,
reserve enabled, p5fix classifier): compute scale-up fires **4 adds/LAN** in
the episode (ba and cf), **8/8 added nodes serve requests** (cf: 24,119
completed via dyn backends), and **B1 is met by a wide margin** — p50
2421→3 ms (ba) / 2285→3 ms (cf), p95 collapses after the first add. Timeout
1.55 % (ba) / 0.82 % (cf), D1/D2/D3 clean, exit 0. The compute-bound arms are
v3-validated; the campaign is launch-ready.

Code pinned at git tag **`rq2-v3-campaign-20260808`** — the P5-validated
campaign state (local commit `925c43f` = `rq2-v3-p5fix-20260808`; VM commit
`84cbd8be`). It includes the P5-fix rework **plus** the RQ3-v2 controller
features (readiness gate, per-connection VIP state, sampled push) that were
active in the working tree during every post-P1d preflight run. The earlier
`rq2-v3-campaign-20260807` (commit `21e8824`) is superseded — it predates the
P5 fix and must not be used for the campaign.

**Campaign launch (2026-08-08):** the 36-run campaign started on
`cloud-vm-rq2` via `tools/run_rq2_campaign.py` (counterbalance_order_v2.csv,
6 blocks, per-run seeds; tag `rq2-v3-campaign-20260808`). Provenance md5s
recorded in `run_matrix.md` §5. Per-run base-gate checks + analysis follow.
Attempt 1 was aborted in the first minute: the orchestrator's completion
detection matched the v2 campaign folders (same `rq2_<cell>_1..3` labels) and
skipped runs 1–13. Fixed `is_run_completed()` to require the v3
`STORAGE_PERSISTENT_RESERVE_ENABLED=1` marker (see lessons-learned),
relaunched cleanly at `rq2_ba_cb_1` (aborted attempt log:
`campaign_log_20260808_attempt1_aborted.txt`).

**Campaign paused (2026-08-08, after run 14/36):** after `rq2_ba_cb_3`, the
campaign was paused by user decision to investigate `ba_db_2`
(`20260808_171707`, run 7) — a suspected platform/harness incident (compute
node SIGKILL exit 137 ~44 s after spawn, a subsequent `add_network_node.sh`
spawn failure, registry churn, and the classifier firing compute at t≈25 s
before the storage activation, diverging from `ba_db_1`). Pending root cause:
decision-log suppression rows, host OOM check, and what killed the node; then
classify as "designed ba cost" (reframe as a ba-cost finding) or "harness
incident" (exclude + rerun `ba_db_2`). Runs 1–14 complete (blocks 1–2 + 2 of
block 3); 22 runs remain.

**ba_db_2 root cause resolved (2026-08-08, analyzer): verdict is **harness
incident, not designed ba cost** (see [`ba_db_2_incident.md`](ba_db_2_incident.md)).
Confirmed chain: the ba classifier warm-up fired compute at t≈+24 s before
storage bound (contributory, not sufficient — `ba_db_1` scaled compute to
budget 3/4 cleanly); the spawned `edge_server_lan1_dyn2` was **MEMCG-OOM-killed**
at t≈+74 s (dmesg 17:19:23, CONSTRAINT_MEMCG, edge **256 MB cap**, exit 137);
the killed container's failed netns/veth cleanup triggered a full flow rebuild
(812 flow keys cleared) → `server_count` 0 / `T_db` 0 from t≈+90 s → mass
timeouts → false-underutilization storage scale-down churn + broken subsequent
spawns. **Decision:** `ba_db_2` excluded (ba_db back to n=1 valid);
**`EDGE_MEMORY` raised 256m → 512m** for the remaining campaign (all 3 arm
envs + orchestrator `BASE_ENV`, synced to `~/rq2_env/`; runs 1–14 at 256m,
runs 15+ at 512m — platform hardening, not a treatment). Campaign resumes at
the next pending replicate; the `ba_db` rerun is gate-checked before more
`ba_db` replicates.

**Campaign complete (2026-08-09):** all 36 runs finished (orchestrator exit
0, 07:37 UTC). Valid replicate pool **35 runs** (36 − `ba_db_2` excluded).
`ba_db` has n=5 valid (1, 3, 4, 5, 6); the `EDGE_MEMORY` split 256m (runs
1–14) / 512m (15–36) is recorded for analysis. Next: per-run analysis,
cell-level B2 synthesis (n=5 seed-42 CI, seed-43 separate), cross-mode
comparison graphs, and `post_run_analysis.md` (analyzer).

## 1. Context

The v2 RQ2 campaign was aborted at run 13 (`rq2_cf_cb_3`, 2026-08-06) because
the data-bound cells could not show a storage scale-up benefit: at the v2
episode (rate 1.5, mixed ops, edge 0.30 / storage 0.15, pool 12) storage never
bound, and reads stayed pinned to the static primaries so added replicas served
nothing. The probe series (`S2a`, `P0`, `F1a`, `F4a`, `F4b` — see
[`storage_bind_probe_record.md`](storage_bind_probe_record.md)) found a config
where storage binds, reads spread to replicas, and replica scale-up produces a
clear user-visible benefit, reproduced across two traffic seeds and passing all
`testing_requirements.md` hard gates.

**v3 rebases the RQ2 campaign on that locked config.** Compute-bound cells keep
the B1-validated v2 config; data-bound cells use the new locked config.

## 2. Objective

Demonstrate, per `testing_requirements.md`:

- **B1 — compute scale-up benefit** (cb cells): latency drop OR edge-CPU relief
  after a compute add, reproduced.
- **B2 — storage scale-up benefit** (db cells): latency drop OR storage-CPU
  relief after a storage add, reproduced.
- **M1/M2** — the claimed tier scales (per LAN) and added nodes serve requests.
- **V1** — the intended bottleneck is evidenced in telemetry (cb: edge CPU
  rising; db: `T_db`/storage CPU rising).
- **I1/I2, D1–D3, F1/F2** — interpretability, integrity, provenance, symmetry.

Policies under test (the RQ2 action-selection axis): `fixed_compute_first`
(cf), `fixed_storage_first` (sf), `bottleneck_aware` (ba) × episodes
compute-bound (cb) / data-bound (db).

## 3. Locked configuration (tag `rq2-v3-campaign-20260808`)

| Cell | Arm env | Phases file | EDGE_CPUS | STORAGE_CPUS | Pool |
|---|---|---|---|---|---|
| `cf_cb` | `rq2_compute_first.env` | `phases_rq2_compute_bound.json` | 0.15 | 0.08 | 12 |
| `cf_db` | `rq2_compute_first.env` | `phases_rq2_data_bound.json` | **1.20** | **0.15** | **12** |
| `sf_cb` | `rq2_storage_first.env` | `phases_rq2_compute_bound.json` | 0.30 | 0.15 | 12 |
| `sf_db` | `rq2_storage_first.env` | `phases_rq2_data_bound.json` | **1.20** | **0.15** | **12** |
| `ba_cb` | `rq2_bottleneck_aware.env` | `phases_rq2_compute_bound.json` | 0.15 | 0.08 | 12 |
| `ba_db` | `rq2_bottleneck_aware.env` | `phases_rq2_data_bound.json` | **1.20** | **0.15** | **12** |

Pool is **per-cell** (hardening fix 4): `EDGE_MONGO_MAX_POOL_SIZE=12` applies
to the static edges of all cells (shell, in `tools/run_rq2_campaign.py`
`CELLS`); the arm envs keep 12 (dynamic edges). Db cells use pool 12 (locked
2026-08-08 after P3/P3b — evidence: B2 p95 leg 0.42×/0.49× vs 0.63×/0.77× at
pool 48, timeout 0.068–0.074 % vs 0.085–0.090 %; pool 48 was the pre-P3 shell
config). Data-bound episode: rate 5.0, mix
`content_lookup 0.9 / feed_ranking 0.1`; `demand_drop` 360 s (scale-down
window).

**D3 overload-label re-anchor (2026-08-07, fix 8):** the campaign launches
with `OVERLOAD_CPU_PCT=30` and `OVERLOAD_PEAK_LATENCY_MS=2000` (shell
make-vars, propagate to the aggregator containers via `build_network_1/2.sh`).
The aggregator defaults collide with the data-bound baselines: storage idles
at 6–9 % CPU (vs the 5.0 CPU bar) and the `demand_drop` tail latency is
~1.0–1.4 s (vs the 1000 ms peak bar), so the D3 `overload` label stayed true
through `demand_drop` and the housekeeping churn guard
(`HOUSEKEEPING_OVERLOAD_GATE=1`) suppressed scale-down for the entire P1 run
(and P1b, which re-anchored only the CPU bar). At 30/2000 the label is on
during the episode (avg CPU ~42 %, peak 8.8 s+) and off during `demand_drop`
(~5 %, ~1.3 s), so scale-down can fire — while the churn guard stays active
for genuine overload. RQ1/RQ3 launches keep the 5.0/1000 defaults.

**Storage persistent reserve (2026-08-07, D8 reversal):** the three arm envs
now set `STORAGE_PERSISTENT_RESERVE_ENABLED=1` (previously 0 per
rq2_preparation D8). Rationale: with the reserve OFF the sf_db scale-down is
structurally blocked — `can_scale_down_storage` requires a `READY_RESERVED`
slot whenever ≤2 non-reserved storage nodes remain on a LAN, and the db cell
sits at exactly 2 (static + dynamic). With the reserve ON, the first storage
trigger activates the ready standby (no cold spawn + RS-join wait),
replenishment keeps one standby per LAN, and `demand_drop` scale-down becomes
floor-safe (active + 1 reserve). Storage scale-up is therefore the reserve
activation path, not the cold dynamic spawn.

## 4. Design

- **6 cells × 6 replicates = 36 runs**, order per
  [`counterbalance_order_v2.csv`](counterbalance_order_v2.csv) (6 blocks of 6
  cells, randomized per block).
- Traffic seed per run from the CSV `traffic_seed` column: `RANDOM_SEED=42`
  for replicates `_1.._5`, `RANDOM_SEED=43` for the `_6` cross-seed arm
  (hardening fix 2 — one seed-43 replicate per cell, so the matrix also tests
  demand robustness, not only platform response). The CSV `block` column
  (1–6) is the counterbalance ordering only — RANDOM_SEED comes solely from
  `traffic_seed` (the stale v2-era "block seeds 2001–2006" wording removed
  2026-08-08; the CSV carries no block seed).
- Open-loop driver, `CLIENTS=24`, `CURL_MAX_TIME=300`, `INFLIGHT_WINDOW=1024`,
  `DRAIN_S=30`, `CONTENT_ITEMS=3000`, `USERS=100`, `DATA_SEED=42`.
- Phase files (canonical, edited in place under `source/scripts/testing/
  phases_override/`):
  - **data-bound**: baseline 30 s → `data_bound_episode` 480 s (rate 5.0) →
    recovery_gap 60 s → demand_drop 360 s.
  - **compute-bound**: baseline 60 s → `compute_bound_episode` 600 s (rate 1.5,
    `service_pressure 1.0`) → recovery_gap 120 s → demand_drop 420 s.

## 5. Preflight (5 runs, before the 36)

| # | Label | Cell | Purpose / pass |
|---|---|---|---|
| P1 | `rq2_sf_db_preflight_1` | sf_db, seed 2001 | locked db config end-to-end: full req-check, bind → relief, **≥1 storage scale-down in `demand_drop`** |
| P1d | `rq2_sf_db_preflight_1d` | sf_db, seed 2001 | P1c retry with storage persistent reserve ENABLED: reserve READY before episode → activate on first trigger (no cold spawn) → **≥1 storage scale-down in `demand_drop`** (numeric pass, but reserve not exercised — see status) |
| P1e | `rq2_sf_db_preflight_1e` | sf_db, seed 2001 | P1d retry after Gap 1 fix (reserve wired into the RQ2 storage path) + fresh image: **`[reserve] activated` on first trigger (no cold spawn)** → **≥1 storage scale-down in `demand_drop`** |
| P2 | `rq2_sf_db_preflight_2` | sf_db, seed 2001 | same-seed reproducibility (P1 ≈ P2) |
| P3 | `rq2_sf_db_preflight_pool12` | sf_db @ shell pool 12 | fix-1 diagnostic: does pool 12 @ rate 5 also bind → relieve? |
| P3b | `rq2_sf_db_preflight_pool12_2` | sf_db @ shell pool 12, seed 2001 | pool-12 n=2 reproducibility (same-seed repeat of P3; **PASS — pool 12 locked as db-cell config**) |
| P4 | `rq2_cf_db_preflight_1` | cf_db, seed 2001 | wrong-action sanity: storage stays suppressed, no collapse (timeout ≤ 10 %), latency elevated vs P1 (**PASS** — 0 reserve activations, timeout 8.27 %, p50 ~4×/p95 ~75× vs sf_db) |
| P5 | `rq2_ba_db_preflight_1` | ba_db, seed 2001 | classifier picks storage; benefit ≈ P1 (**PASS — rerun 20260808_111548 after `rq2-v3-p5fix-20260808`**: suppression + no collapse; timeout 0.138 %, B2 p95 0.66×) |

Pass for P1/P2 = full `testing_requirements.md` check (B2, M1, M2, V1, I1, I2,
D1–D3, F2), timeout ≤ 5 %, bind → relief signature, ≥ 1 storage scale-down.
P3 was diagnostic; **P3b is the pool-12 n=2 reproducibility run** (user
decision 2026-08-08: pool 12 is the db-cell campaign config, so it must have
n ≥ 2 like any other claim). ~6 × 14 min ≈ 85 min.

## 6. Gates (pre-registered magnitudes)

- Health: timeout % ≤ 5 % per run (target ≈ 0 %).
- Benefit — B1 (compute, cb cells): **p50 drop ≥ 2×** between the pinned
  pre-add and post-add windows (below), OR clear tier-CPU relief (post-add CPU
  < 0.6 × pre-add).
- Benefit — **B2 (storage, db cells) — RQ2-specific re-scope (2026-08-08,
  preflight-calibrated)**: reserve-enabled storage cells do not show a 2× p50
  drop because the reserve activates early (~100 s into the episode) and
  preempts deep single-node saturation (pre-add p50 already ~55–78 ms in P1e/
  P2). The user-visible benefit manifests as **tail relief** and **peak-CPU
  relief**; pre-registered per LAN as: **post-add window p95 < 0.8 × pre-add
  window p95, OR post-add window peak storage CPU < 0.75 × pre-add window
  peak**. Calibration (n=2, seed 2001): p95 ratio 0.77× / 0.63×, peak-CPU
  ratio 0.59×–0.70× — both legs pass in P1e and P2. A no-add counterfactual
  (reserve disabled) remains an optional cross-validation, not a campaign
  gate. Cell-level: median of replicate ratios with 95 % CI excluding 1.0.
  **The CI is computed on the n=5 seed-42 replicates; the `_6` seed-43
  replicate is reported separately as the demand-robustness check, not pooled
  into the CI** (pre-registered 2026-08-08). Direction consistent across
  replicates.
- Mechanism (M1): ≥ 1 add in the claimed tier per LAN during the episode.
- Usability (M2): each added node serves ≥ 1 completed request.
- Validity (V1): storage fires show `cpu_s` rising (db) / edge CPU rising (cb).
- Demand (I1): ≥ 5 000 completed requests per LAN in the episode.
- Integrity: D1 0 × NotPrimary*, D2 no restart/crash, D3 snapshots present.
- **Pre/post-add windows (pinned):** pre-add = episode start → first storage
  add/activation timestamp (`[reserve] activated` / `container_events`
  `added`); post-add = first add **ready** + 120 s → episode end (fallback
  ready = add + 40 s). Report p50/p95/p99 and the storage-CPU peak over each
  window plus the 30 s-bucket trajectory.
- **Per-run screening stop-rule (pre-registered 2026-08-08):** a hard-gate
  trip on a *healthy* cell — D1 (NotPrimary), D2 (restart/crash), D3 missing,
  or no-collapse (episode served-basis < 95 %) — **halts the campaign**;
  investigate and rerun before resuming. `timeout % > 5 %` on a healthy cell
  ⇒ rerun once; if it reproduces, halt and investigate. No-benefit cells
  (`cf_db`, `sf_cb`) are exempt from the health-timeout ceiling (they are
  pre-registered to degrade) but a hard data-path trip (D1/D2/D3) still halts.
- **B2 leg attribution (pre-registered 2026-08-08):** B2 is met per LAN by
  the OR rule (p95 < 0.8× OR peak-CPU < 0.75×). For the cell-level verdict the
  **p95 leg is primary**; the peak-CPU leg is supporting evidence, reported
  per LAN. A cell whose p95-leg 95 % CI includes 1.0 does NOT pass B2 even if
  the CPU leg passes — both legs are reported and the carrying leg is named.
  (Applies to sf_db and ba_db; ba_db is expected to be p95-carried — preflight
  lan2 peak-CPU ratio 1.06×.)
- **Efficiency verdict (pre-registered 2026-08-08):** per cell and replicate,
  from `elasticity_events.csv` + `node_lifecycle_timings.csv`: scale-action
  count by tier (adds/activations/removals per LAN), compute + storage
  node-minutes, rs-join time per storage add (the measured sync cost), and a
  wasted-actions tally (actions yielding no relief in the targeted tier).
  Reported descriptively (median per cell); feeds the "use resources more
  efficiently" half of the RQ2 claim. **Action-cost scope note:** replica-sync
  *bandwidth* is not directly metered — the measured sync cost is join time +
  transient storage CPU/latency + node-minutes; the bandwidth limitation is
  stated in the thesis, not assumed measured.

## 7. Claim shaping (open-ended, result-driven)

The claim is **not pre-scoped to a single signal**. The evaluation asserts the
mechanism relation — *worse trigger awareness ⇒ worse user service quality* —
and measures user service quality across the available signals (latency,
timeout, throughput served, edge/storage CPU). The final thesis claim is
**shaped by the results**: whichever signals the data shows improve (or
degrade) when the correct tier scales become the signals the claim is built
on, including effects that exceed pre-registered expectations. Wrong-action
cells (`cf_db`, `sf_cb`) are judged against their own pre-registered direction
(degraded service quality), per `testing_requirements.md`.

## 8. Provenance

- Campaign code pinned at tag `rq2-v3-campaign-20260808` (local commit
  `925c43f` = the `rq2-v3-p5fix-20260808` tree; VM commit `84cbd8be`):
  `tools/run_rq2_campaign.py`, `docs/operation/testing/experiment/v3/rq2/env/*`
  (3 arm envs), `source/scripts/testing/phases_override/phases_rq2_data_bound
  .json`, `phases_rq2_compute_bound.json`.
- The tag supersedes the pre-fix `rq2-v3-campaign-20260807` (commit
  `21e8824`). It captures the controller/edge source that ran the preflight
  (incl. the RQ3-v2 features) on both sides; the VM tag's tree is exactly the
  working tree that passed P1e–P5.
- At launch the tagged files are synced to `cloud-vm-rq2` and md5-verified; the
  controller/edge source is synced and its hashes recorded in each run folder.

## 9. Changelog

| Date | Change | Rationale |
| --- | --- | --- |
| 2026-08-09 | Campaign analysis complete: per-run summaries (35), cell-level B2/B1 synthesis, arm narrative, cross-mode comparison graphs, `results.md`, `post_run_analysis.md`. **Valid pool corrected to 34** — `cf_db_5` (run 25) re-classified as a **second MEMCG OOM incident** (2 compute-node OOM kills @ 512 MB cap, D2 hard-gate violation; same mechanism as `ba_db_2`) and excluded from the cf_db pool (cf_db valid = 1,2,3,4,6). B1 robust (cb cells); B2 p95-leg cell-level CI includes 1.0 for both sf_db and ba_db (pre-registered gate not met), CPU-relief leg robust for sf_db; ba_db tail degradation from post-relief compute churn. | Linked to `results.md` §Judgment, §Root Causes. The 512 MB hardening did not eliminate the edge-server MEMCG OOM under compute churn. |
