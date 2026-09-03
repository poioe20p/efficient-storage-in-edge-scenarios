# research_q3 — Preflight Checkpoint Log

Fill one row per checkpoint executed. Verdicts: GO / STOP / DIAGNOSE.
STOP and DIAGNOSE entries require a resolution note before the campaign
continues.

| Date | Stage | Checkpoint | Run/Label | Result | Verdict | Resolution note |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-09-02 | 0.1 | release-gate selftest | — | SELFTEST PASS (26 ok) | GO | — |
| 2026-09-02 | 0.2 | compile + shell syntax | — | compileall + py_compile + bash -n all clean | GO | — |
| 2026-09-02 | 0.3 | config integrity | — | phases.json 5 phases; canonical env pins off; 4 arm envs with mechanism + 9 knobs | GO | arm_*.env normalized CRLF→LF |
| 2026-09-02 | 0.4 | CLI synthetic smoke | temp synthetic | table+safety CSVs render; expected n/a present; exit 0 | GO | fixed `end_reason` UnboundLocalError in cli_release_compare.py (_release_events); re-ran clean |
| 2026-09-02 | 1.1 | VM repo synced + new files | — | release_gate.py/release_log.py + arm envs present on VM | GO | scp/tar sync; 64/64 files MD5 byte-identical |
| 2026-09-02 | 1.2 | code current on VM | — | scaling_config RELEASE_MECHANISM ×6; phases.json 5 phases; arm_stabilized.env present | GO | — |
| 2026-09-02 | 1.3 | importability in container | osken/osken_2 | `osken import ok`, `osken_2 import ok` | GO | bind-mounted workspace live without rebuild |
| 2026-09-02 | 1.4 | sudo + docker | — | sudo -n ok; docker 29.1.3 | GO | — |
| 2026-09-02 | 1.5 | controller starts clean | — | 0 ImportError/Traceback in both controllers; `release_gate: mode=off` at DEBUG (canonical env) | GO | Stage-1 script's SSH session was reset mid-setup; 1.3/1.5 re-verified with fresh checks |
| 2026-09-02 | 2.1 | both tiers spawn in storm | research_q3_cal_s1 | storage spawns only (reserve standby dyn1-7); compute never spawned — policy `compute cap reached (0/0)` every window | STOP | launcher passed only arm env; canonical override (MAX_DYNAMIC_COMPUTE=3) never applied — base env pins 0 |
| 2026-09-02 | 2.2 | quarantine_begin in hold | research_q3_cal_s1 | none — release_log has no compute rows (mechanism never armed) | STOP | same root cause (compute scale-down never became eligible) |
| 2026-09-02 | 2.3 | recall at return onset | research_q3_cal_s1 | 0 recall rows | STOP | no quarantine → no recall |
| 2026-09-02 | 2.4 | cycle-2 finalization | research_q3_cal_s1 | none | STOP | mechanism never exercised |
| 2026-09-02 | 2.5 | controllers alive throughout | research_q3_cal_s1 | osken + osken_2 up entire run; 0 tracebacks (sampler, every ~2 min) | GO | — |
| 2026-09-02 | 2.6 | artifacts present | research_q3_cal_s1 | release logs, rs_evict_logs_lan1/2 (5 files each), rs_status_research_q3_cal_s1.json, phases_snapshot, controller_env_snapshot all present | GO | — |
| 2026-09-02 | 2.7 | CLI parse + recall_missed=0 | research_q3_cal_s1 |  |  | deferred to rerun (mechanism absent) |
| 2026-09-02 | 2.8 | eviction non-ok=0, ghosts=0, D1 | research_q3_cal_s1 | storage releases only pre/post-run, all `ok` | GO | — |
| 2026-09-02 | 2.9 | timing vs pre-registered | research_q3_cal_s1 |  |  | deferred to rerun |
|  | 3.1 | off: no release log/evict files | research_q3_o1 |  |  |  |
|  | 3.2 | immediate: end-only + eviction logs | research_q3_i1 |  |  |  |
|  | 3.3 | drained: begin/end pairs | research_q3_d1 |  |  |  |
|  | 3.4 | per-run gates (3 runs) | o1/i1/d1 |  |  |  |
|  | 3.5 | cross-run CLI sanity | cal+o1+i1+d1 |  |  |  |
|  | 4 | per-run gate after each of 28 | research_q3_* |  |  |  |
|  | 4 | early direction (run 3/arm) | research_q3_* |  |  |  |
|  | 4 | arm consistency (run 6/arm) | research_q3_* |  |  |  |
|  | 4 | cross-seed sensitivity | x1 runs |  |  |  |
|  | 4 | final campaign verdict | all |  |  |  |

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
