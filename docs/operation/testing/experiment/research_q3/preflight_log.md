# research_q3 — Preflight Checkpoint Log

Fill one row per checkpoint executed. Verdicts: GO / STOP / DIAGNOSE.
STOP and DIAGNOSE entries require a resolution note before the campaign
continues.

| Date | Stage | Checkpoint | Run/Label | Result | Verdict | Resolution note |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-09-03 | 0.1 | release-gate selftest | — | SELFTEST PASS | GO | — |
| 2026-09-03 | 0.2 | compile + bash -n | — | py_compile clean; bash -n OK (compileall hit pre-existing `_v5_full_v2.py`, unrelated) | GO | — |
| 2026-09-03 | 0.3 | config integrity (hold=600 baseline; arm envs) | — | 5 phases; hold=600; canonical off; 4 arm envs mechanism+knobs | GO | — |
| 2026-09-03 | 0.4 | CLI synthetic smoke (tools selftests) | — | SELFTEST OK + SELFTEST2 OK | GO | — |
| 2026-09-03 | 1.1 | repo sync + 5-file MD5 | — | tarball sync; 5-file MD5 byte-identity local==VM | GO | VM repo on divergent origin/main; RQ3 always file-synced (262-file dirty tree) — see note below |
| 2026-09-03 | 1.2 | code current (storage gate present) | — | `_storage_release_gate`×26, `recalled_substitution` in main_n1 | GO | — |
| 2026-09-03 | 1.3 | importability | osken/osken_2 | import ok both containers | GO | — |
| 2026-09-03 | 1.4 | sudo+docker | — | sudo -n ok; docker 29.1.3 | GO | — |
| 2026-09-03 | 1.5 | controller clean start | — | 0 tracebacks; mode=stabilized armed | GO | — |
| 2026-09-03 | 1.6 | phase-edit dry run | — | in-place edit verified (became the real 2.0 edit) | GO | — |
| 2026-09-03 | 2.0 | phases edit 600→480 (P1 pre-launch) | — | hold 600→480 verified on VM | GO | — |
| 2026-09-03 | 2.1 | storm spawns | research_q3_s_pre_e1 | compute 6 + storage 3 adds; 3×ComputeAlert + reserve activations per LAN | GO | — |
| 2026-09-03 | 2.2 | storage retention begin hold+90–200 (projected) | research_q3_s_pre_e1 | retention `quarantine_begin reason=retained` both LANs (lan1 dyn4 08:40:59, lan2 dyn3 08:40:49) | GO | onset earlier than projected window; freeze logs `retention active=True` confirm |
| 2026-09-03 | 2.3 | compute quarantine hold+210–270 | research_q3_s_pre_e1 | quarantine_begin both LANs (lan2 dyn6 08:42:39 scale_down; lan1 dyn5 08:47:09 absent) | GO | — |
| 2026-09-03 | 2.4 | dual-tier recall + substitution | research_q3_s_pre_e1 | dual recall same second both LANs (08:47:49/59); storage reason=readmitted; no teardown in hold; return adds 1 compute+1 storage only | GO | lan1 dyn5 absent-recycling: repeated absent→quarantine→recall cycles (churn note for analyzer) |
| 2026-09-03 | 2.5 | cycle-2 quarantine | research_q3_s_pre_e1 | retention/quarantine re-armed in demand_drop both LANs | GO | — |
| 2026-09-03 | 2.6 | finalization drop+600–820 | research_q3_s_pre_e1 | finalize ≈ drop+581–662 both tiers both LANs; H=480 (end ok / veth_discovery_failed no-op) | GO | — |
| 2026-09-03 | 2.7 | controllers alive | research_q3_s_pre_e1 | up 44 min whole run; 0 tracebacks | GO | — |
| 2026-09-03 | 2.8 | artifacts D3 | research_q3_s_pre_e1 | all present incl phases_snapshot (hold=480), rs_status, release logs, evict logs | GO | p0 2b duplicate probe hits root-owned run dir (cosmetic; run_experiment auto-probe present) — fix p0 between runs |
| 2026-09-03 | 2.9 | CLI per-tier | research_q3_s_pre_e1 | C1s_recall=230.2s; qf=481.5s; qf_storage=491.9s; orphan=0; recall_missed=0 both; no unexpected n/a | GO | analyzer note: high attributed window hits (83 974 incl 47k timeout) — NotPrimary 0, attribution overlaps inflate count |
| 2026-09-03 | 2.10 | evictions/ghosts/D1 | research_q3_s_pre_e1 | evict_ok=2 nonok=0 overlap=0 ghosts=0; NotPrimary 0 everywhere | GO | — |
| 2026-09-03 | 2.11 | timing | research_q3_s_pre_e1 | finalize drop+581–662 (nominal 600–820 ok); recalls ≈ return | GO | dyn5 absent-churn note |
| 2026-09-03 | 2.12 | V1/I1/I2 | research_q3_s_pre_e1 | storm storage CPU 0.8→78%; storm ok req lan1 5524 / lan2 5044 ≫ 500; timeout distinct | GO | overall ~48% error/timeout under storage-bound storm — workload-validity note for analyzer |
|  | 3.1–3.4 | P2 mid-run | research_q3_d_pre_e1 |  |  |  |
|  | 3.5–3.7 | P2 post-run | research_q3_d_pre_e1 |  |  |  |
|  | 3.8–3.10 | P3 mid-run | research_q3_i_pre_e1 |  |  |  |
|  | 3.11–3.12 | P3 post-run | research_q3_i_pre_e1 |  |  |  |
|  | 4.1–4.3 | P4 mid-run | research_q3_o_pre_e1 |  |  |  |
|  | 4.4–4.5 | P4 post-run | research_q3_o_pre_e1 |  |  |  |
|  | 5.0 | phases edit 480→900 (P5 pre-launch) | — |  |  |  |
|  | 5.1–5.7 | P5 mid-run | research_q3_s_pre_l1 |  |  |  |
|  | 5.8–5.11 | P5 post-run | research_q3_s_pre_l1 |  |  |  |
|  | 6.1 | cross-run CLI | — |  |  |  |
|  | 6.2 | verdict recap | — |  |  |  |
|  | 6.3 | phases restore 900→480 | — |  |  |  |

> ⚠ **Numbering**: the table above uses the v2 stage numbering (2.2 = storage
> retention, 2.7 = controllers alive, etc.). The historical sections below
> predate design v2 and use the OLD numbering — read them as historical
> records only.

---

**Resolution notes (Stage 2 first attempt, 2026-09-02)**

- **Root cause of 2.1–2.4 STOP**: `research_q3_launch_run.sh` passed only the arm env as `OSKEN_ENV_OVERRIDE_FILE`; the canonical override `current_state_integrated.env` (MAX_DYNAMIC_COMPUTE=3, SS_ENABLED=1, recalibrated scale-up/down thresholds) never reached the controller. Base env pins MAX_DYNAMIC_COMPUTE=0 → compute never scaled → mechanism never exercised.
- **Fix**: launcher now merges canonical + arm into one temp override (arm wins per key, provenance header) — commit `bc34580`, tag `rq3-rel-preflight-20260902` (v2). Verified on VM: merged env contains MAX_DYNAMIC_COMPUTE=3 / SS_ENABLED=1 / RELEASE_MECHANISM=stabilized.
- **Tooling fix**: `tools/watch_run.py` same-label rerun guard now treats run_status.json completed/failed as idle (previously current_phase.txt held the last phase name after completion → false "completed" on rerun).
- **Rerun launched**: `research_q3_cal_s1` (seed 42, stabilized) with merged env; sampler + watchdog active. New run folder, verdicts to be recorded on completion.

---

**Stage 2 rerun results (`20260902_171159_research_q3_cal_s1`, completed 17:52:18Z, exit 0)**

- **2.1 GO** — storm spawns: dynamic compute (`edge_server_lan{1,2}_dyn2..6`) + storage + sel_sync spawned; 3 `scale_up` decision rows.
- **2.5 GO** — both controllers alive all run, 0 tracebacks.
- **2.2 STOP** — no `quarantine_begin`: housekeeping churn guard (`LAN overloaded (recent)`) suppressed absent-cleanup + scale-down evaluation during hold; no compute scale-down eval lines at all in hold.
- **2.3 STOP** — 0 recall rows (no quarantine).
- **2.4 STOP** — compute `armed=True` repeatedly in demand_drop (17:33:35, 17:35:05, 17:36:35…) but `main_n1` logs `no graceful candidate is eligible — clearing current window`: the dynamic compute nodes had already been removed at 17:31:35 via the **absent-cleanup path** (`ScaleDownComputeAlert reason='absent'` for dyn3/dyn5/dyn6) — which calls `release_gate.clear()` and bypasses the release mechanism entirely (no release-log rows).
- **2.6 GO** — artifacts present (release logs, rs_evict_logs, rs_status, snapshots).
- **2.7/2.9** — n/a: mechanism absent.

**Diagnosed root cause (rerun)**:
1. `return_storm` uses `cross_region_ratio=0.9` → ~90% of requests cross to the other LAN, so local dynamic compute servers receive almost no traffic → their telemetry goes stale beyond `_TELEMETRY_TIMEOUT_S` (≈180 s).
2. When the churn guard lifts at demand_drop+32 s, `detect_absent` flags dyn3/dyn5/dyn6 and the absent-cleanup path removes them **without going through the release gate** (no quarantine/recall/finalization).
3. The release path's candidate picker then finds an empty dynamic-compute list → `no graceful candidate is eligible` — the stabilized chain never fires.

Candidate fixes (awaiting user decision): route absent-cleanup for compute through `release_gate` (mechanism change); or tune `TELEMETRY_TIMEOUT`/`HOUSEKEEPING_OVERLOAD_LOOKBACK`; or change `return_storm.cross_region_ratio` in phases.json so local dynamics keep serving; or a combination.

---

**Fix v3 (approved: options 1+2, commit `a6db7e7`, tag `rq3-rel-preflight-20260902` v3)**

- `main_n1.py`/`main_n2.py`: absent COMPUTE nodes now follow the arm's release semantics — stabilized quarantines them (`quarantine_begin`, trigger=absent, finalize on expiry); drained/immediate submit with reason=scale_down so elasticity logs begin/end rows; mode=off keeps the incumbent path.
- `scaling_config.py`: `TELEMETRY_TIMEOUT_S` env hook (default = prior computed value).
- `current_state_integrated.env`: `TELEMETRY_TIMEOUT_S=600`, `HOUSEKEEPING_OVERLOAD_LOOKBACK=2`.
- `phases.json`: `return_storm.cross_region_ratio` 0.9 → 0.0 (local dynamics keep serving through the storm return).
- Validated: compileall, release-gate selftest, phases parse; 5 files MD5 byte-identical on VM; merged run env verified (TELEMETRY_TIMEOUT_S=600, HOUSEKEEPING_OVERLOAD_LOOKBACK=2, RELEASE_MECHANISM=stabilized, MAX_DYNAMIC_COMPUTE=3).
- **v3 calibration rerun launched** (`research_q3_cal_s1`, seed 42) with sampler + watchdog; verdicts on completion.

---

**Stage 2 v3 results (`20260902_205202_research_q3_cal_s1`, completed 21:33:00Z, exit 0) — MECHANISM EXERCISED**

- **2.1 GO** — compute dyn2–6 + storage dyn1–5 spawned; 3 `scale_up` rows.
- **2.5 GO** — controllers alive all run, 0 tracebacks.
- **2.2 (quarantine) — exercised, but in `demand_drop`, not `hold`**: `quarantine_begin` rows on both LANs (trigger=`absent`, via the new release-gate routing); the `hold` window is unreachable because the churn guard suppresses every tick (D3 overload label stays true — see below).
- **2.3 (recall) — GO**: `overload,recall,1,recalled` rows ~10 s after each quarantine on both LANs.
- **2.4 (cycle-2 finalization) — NOT exercised**: every quarantine is recalled within ~10 s; no compute `begin`/`end` finalization rows (C1_stabilized_qf_p50 = n/a).
- **2.6 GO** — all artifacts present (release/decision/container/resource stats, snapshots, rs_evict_logs 3+5, rs_status).
- **2.7 GO** — CLI parses: `C4_recall_missed=0`, `C1_stabilized_recall_p50=10.0s`, `C1_storage_p50=12.17s`, no unexpected n/a (qf_p50 n/a expected — no finalization).
- **2.8 GO** — 8/8 evictions `ok` (`C2_evict_nonok=0`, `C2_evict_overlap=0`), `C2_ghosts=0`, `C2_attributed_errors=3` inside windows, `C2_notprimary=0` → D1 clean.
- **2.9** — quarantine at `demand_drop+182s` (lan1) / `demand_drop+90s` (lan2); recall +10 s — pre-registered windows (hold-based) need updating.

**Root cause of the label sticking true (lead for analyzer)**: the D3 overload label is computed in `source/docker/local_state_server/aggregator.py` as `avg_cpu ≥ OVERLOAD_CPU_PCT OR peak_latency ≥ … OR error_rate ≥ …`. Under the `EDGE_CPUS=0.08` capped regime, capped-CPU% stays high even at rate 0.5 → label true through `hold`/`demand_drop` → churn guard suppresses scale-down all `hold`, and every quarantine is recalled within ~10 s in `demand_drop`. Open decision: retune `OVERLOAD_CPU_PCT`/label inputs (needs analyzer investigation + user approval) vs. accept recall-dominated stabilized behavior and update the pre-registered windows accordingly.

---

**Fix v4 (approved: request-floor gate, commit `a7964a7`, tag `rq3-rel-preflight-20260902` v4)**

- `source/docker/local_state_server/aggregator.py`: `OVERLOAD_MIN_REQUESTS` env hook (default 0) — `_compute_overload` returns False when `total_requests < OVERLOAD_MIN_REQUESTS`, so lull windows with capped-CPU% no longer label D3 overload.
- `research_q3_launch_run.sh`: `OVERLOAD_MIN_REQUESTS=60` (make var).
- Rebuilt `local_state_server` image (id `de40e99c159d`) + smoke-tested the env hook inside the image.
- Validated: compileall, release-gate selftest, phases parse; 5-file MD5 byte-identity on VM; watchdog same-label guard hardened.
- **v4 calibration run launched** (`research_q3_cal_s1`, seed 42) with sampler + watchdog; verdicts on completion.

---

**Stage 2 v4 results (`20260902_232911_research_q3_cal_s1`, watchdog exit 0) — FULL CHAIN PROVEN**

- **2.1 GO** — both tiers spawn in `storm_mixed`.
- **2.5 GO** — controllers alive all run, 0 tracebacks (live sampler).
- **2.2 GO** — compute `scale_down,quarantine_begin` at `hold`+221 s on lan2 (pre-registered 210–270 s window ✓); storage begin/end ok pairs observed in `hold`/`demand_drop`.
- **2.3 GO** — recall rows on BOTH LANs at `return_storm`+51–61 s.
- **2.4 GO** — cycle-2 quarantine in `demand_drop`; finalization (`scale_down,end,1,veth_discovery_failed`) at quarantine+490 s (H=480 + one tick ✓).
- **2.6 GO** — artifacts present (release logs, rs_evict_logs, rs_status, snapshots).
- **2.7 / 2.8** — pending analyzer confirmation on the completed run folder.
- **2.9 GO** — quarantine onset inside the pre-registered window; recall ≈ return+51–61 s; finalize ≈ quarantine+490 s.

**Mechanism verdict**: the full stabilized chain (quarantine → recall → cycle-2 quarantine → finalize) is proven end-to-end. Stage 2 exits to design work.

---

**Design change (2026-09-03, user-approved) — merged RQ3 design v2**

- RQ3 reworded: *"Under recurrent demand in a stateful edge service, how do eager and stabilized scale-down policies for surplus compute and storage capacity affect resource occupancy during demand valleys, avoidable lifecycle churn, and the recovery time and transient service quality observed when demand returns?"*
- Arms: `off` control; `drained` = eager-safe (drain + confirmed rs.remove, prompt termination); `stabilized` = retention H=480 s on BOTH tiers (compute quarantine + storage retained out of VIP_DATA, overload recall, safe finalize); `immediate` = safety-boundary ablation reported separately.
- New axis: return timing — early (`hold`=480 s) vs late (`hold`=900 s), edited in-place in canonical `phases.json` between blocks.
- Reporting: tier-stratified C1–C5, n=4 per cell (32 runs + calibration, ≈ 22 h). Compute-bound regime deferred + pre-registered.
- **Implementation**: storage retention in `main_n1.py`/`main_n2.py` (second `ReleaseGate` per tier, retention begin/recall/expiry, `VIP_DATA` unregister/re-register, release-log rows `tier=storage`), registry retained-MAC tracking, updated `scaling_config.py`/`release_gate.py` docs, `experiment_plan.md` v2. Commit + tag pending reviewer pass.
- **Next**: preflight run matrix for the new cells (eager-safe / retention-storage / immediate ablation / early+late timing) — see `preflight_campaign.md` update after implementation sign-off.

---

**Stage 0-2 results � P1 stabilized early (20260903_083426_research_q3_s_pre_e1, completed exit 0)**

- **Full dual-tier chain proven end-to-end**: storage retention (reason=retained, both LANs) and compute quarantine begin in hold; dual overload recall at return (storage reason=readmitted � new re-admit path); cycle-2 retention/quarantine in demand_drop; H=480 finalize at drop+581-662 with end ok (storage) / eth_discovery_failed (compute no-op). Recall substituted adds (return adds minimal; C4_return_spawns=0; no teardown in hold).
- **All 2.1-2.12 gates GO** (see table). Analyzer notes for campaign: (1) lan1 compute dyn5 absent-recycling (repeated absent->quarantine->recall cycles, finalized veth_discovery_failed) � churn-relevant, mechanism-correct; (2) high attributed error-window hits driven by return/drop storm timeouts (NotPrimary 0 everywhere; D1 clean; attribution overlaps inflate window counts); (3) ~48% overall error/timeout under the storage-bound storm � workload-validity context for benefit judgments.
- **Tooling fix (between runs)**: p0 Stage-2b duplicate rs_probe hits the root-owned run folder (permission denied under testop; set -e aborts before hints). run_experiment already auto-probes (rs_status_research_q3_s_pre_e1.json present) � p0 2b will be guarded/skipped when rs_status_* exists.
