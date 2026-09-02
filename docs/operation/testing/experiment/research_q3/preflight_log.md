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
