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
