# research_q3 — Preflight Campaign (staged gates & checkpoints)

**Date**: 2026-09-02 · **Status**: 📋 Planned

> ⚠ **Revision pending (merged design v2, 2026-09-03)**: the stages below
> specify the pre-merged design (o1/i1/d1 arm smoke runs, hold=600-derived
> windows, n=6 + x1 labels). A revision covering the merged cells
> (eager-safe / stabilized retention per tier, immediate ablation,
> early/late timing) is the next design step. Until then
> `experiment_plan.md` (v2) is authoritative for arm semantics and the run
> matrix; stage numbering and checkpoint expectations below will be revised
> in place.

The preflight is a **staged campaign**: nothing proceeds to the next stage
until the current stage's checkpoints pass. Every checkpoint has a verdict
(**GO** / **STOP** / **DIAGNOSE**) recorded in
[`preflight_log.md`](preflight_log.md). Stages 0–2 are automated by
`source/scripts/testing/rq3rel_p0_preflight.sh` where noted; Stages 3–4 are
runner-driven with the checkpoints below.

**Naming**: campaign = `research_q3`. Run labels: `research_q3_{o,i,d,s}1..6`
(seed 42), `research_q3_{o,i,d,s}x1` (seed 43, sensitivity), calibration
`research_q3_cal_s1`. Arms: o=off, i=immediate, d=drained, s=stabilized.

---

## Stage 0 — Local static gate (Windows host, ~2 min, no VM)

Purpose: fail fast on code/config breakage before touching the VM.

| # | Checkpoint | Command | Verdict |
| --- | --- | --- | --- |
| 0.1 | Release-gate selftest | `.venv\Scripts\python.exe source/scripts/testing/rq3rel_p1_01_release_gate_selftest.py` → `SELFTEST PASS` | GO/STOP |
| 0.2 | Compile + shell syntax | `python -m compileall -q source/sdn_controller`; `py_compile` the two new testing scripts; `bash -n` (Git Bash) the three shell scripts | GO/STOP |
| 0.3 | Config integrity | `phases.json` parses (5 phases); archive `phases_before_rq3rel.json` parses; canonical env contains `RELEASE_MECHANISM=off`; each `arm_*.env` contains its mechanism + the 9 pinned knobs | GO/STOP |
| 0.4 | CLI synthetic smoke | Build a synthetic run folder in `temp/` (fabricated `release_log_lan1.csv`, `client_requests.csv`, `rs_status_x.json`, `rs_evict_logs_lan1/` lines, `container_events.csv`, `phases_snapshot.json`), run `cli_release_compare.py --run-dir temp/...`, verify the table + safety CSVs render and expected `n/a` fields are `n/a`; **delete the temp folder afterwards** | GO/STOP |

## Stage 1 — VM sync + harness gate (cloud VM, ~10 min)

Purpose: the controller container bind-mounts the repo workspace
(`-v "$PWD":/workspace`, `PYTHONPATH=/workspace`), so **no image rebuild is
needed** — but the VM workspace must contain the new code, and it must be
importable from inside the controller container.

| # | Checkpoint | Command (on VM) | Verdict |
| --- | --- | --- | --- |
| 1.1 | Repo synced | `cd ~/efficient-storage-in-edge-scenarios && git pull` (or the runner's sync step); `test -f source/sdn_controller/release_gate.py && test -f source/sdn_controller/release_log.py` | GO/STOP |
| 1.2 | Code current on VM | `grep -c RELEASE_MECHANISM source/sdn_controller/scaling_config.py` ≥ 1; `phases.json` has 5 phases; `test -f docs/operation/testing/experiment/research_q3/env/arm_stabilized.env` | GO/STOP |
| 1.3 | Importability inside container | After one `make setup_network` pass (fresh containers from the synced workspace): `docker exec osken python -c "import sdn_controller.release_gate, sdn_controller.release_log; print('ok')"` (both `osken` and `osken_2`) | GO/STOP |
| 1.4 | Sudo + docker | `sudo -n true`; `docker info` OK | GO/STOP |
| 1.5 | Controller starts clean | `docker logs osken` contains no `ImportError`/`Traceback`; gate logs `release_gate: mode=off` at most at debug (canonical env) | GO/STOP |

## Stage 2 — Calibration run (stabilized arm, full length, ~35 min)

Purpose: prove the riskiest timeline (quarantine → recall → cycle-2
finalization) works end-to-end before any campaign run.

**Launch**: `bash source/scripts/testing/research_q3_launch_run.sh arm_stabilized.env research_q3_cal_s1 42`

### In-run checkpoints (runner passive monitoring, read-only; times from run start)

| # | Window | Check | Question answered |
| --- | --- | --- | --- |
| 2.1 | t ≈ 60–240 s (`storm_mixed`) | compute + storage dynamic spawns; `decision_log` scale_up rows | M1/V1: both tiers accumulate surplus |
| 2.2 | t ≈ 450–510 s (`hold` +210–270) | `docker exec osken tail /tmp/release_log.csv` shows a `quarantine_begin` row | quarantine armed, evaluation frozen |
| 2.3 | t ≈ 860–880 s (`return_storm` +20–30) | a `recall` row appears; **no** compute `scale_down` teardown in `hold` | recall fires, zero churn |
| 2.4 | t ≈ 1160–1300 s (`demand_drop` +140…620) | second `quarantine_begin`, then `begin`/`end` finalization rows | cycle-2 finalization executes |
| 2.5 | any | `docker ps` shows both controllers alive; no `Traceback` in `docker logs` | D2 |

### Post-run gates (before Stage 3)

| # | Check | Verdict |
| --- | --- | --- |
| 2.6 | All artifacts present: `release_log_lan{1,2}.csv`, `rs_evict_logs_lan{1,2}/`, `rs_status_cal_s1.json`, `phases_snapshot.json`, `controller_env_snapshot.env` (D3) | GO/STOP |
| 2.7 | `cli_release_compare.py` on the run dir: recall rows parsed, `recall_missed=0`, `C1_stabilized_qf_p50` ≈ 480–620 s, no unexpected `n/a` | GO/DIAGNOSE |
| 2.8 | Eviction outcomes all `ok` (`C2_evict_nonok=0`); `C2_ghosts=0`; D1 clean outside attribution windows | GO/DIAGNOSE |
| 2.9 | Timing vs pre-registered windows (§5 of `experiment_plan.md`); jitter beyond one tick + 30 s → investigate | GO/DIAGNOSE |

## Stage 3 — Arm smoke runs (one per remaining arm, ~1.5 h)

Purpose: prove each arm's release actually fires and produces the expected
log shape before spending the full matrix.

**Launches**: `research_q3_o1` (`arm_off.env`), `research_q3_i1`
(`arm_immediate.env`), `research_q3_d1` (`arm_drained.env`), all seed 42.

| # | Checkpoint | Verdict |
| --- | --- | --- |
| 3.1 | `off`: collector reports no release log (WARNING fallback); storage evictions leave no `/tmp/rs_evict` files | GO/STOP |
| 3.2 | `immediate`: release `end`-only rows in `hold` for both tiers; `rs_evict_logs_lan{1,2}` contain `fire_and_forget` lines; no drain POST in controller logs | GO/STOP |
| 3.3 | `drained`: `begin`+`end` pairs; storage eviction outcomes `ok`; drain POST present | GO/STOP |
| 3.4 | All three: M1 releases in `hold` (per arm), M2, V1, I1, D2, D3 | GO/STOP |
| 3.5 | Cross-run: `cli_release_compare.py` over the 4 runs (cal + o1 + i1 + d1) — table renders; compute C1 ordering `immediate < drained`; `C2_evict_nonok=0`; no unexpected `n/a` | GO/DIAGNOSE |

## Stage 4 — Full campaign (28 runs + interleaved checkpoints)

**Matrix**: 4 arms × n=6 (seed 42) + n=1 (seed 43, sensitivity) = 28 runs.
Counterbalanced blocks:

| Block | Runs (order) |
| --- | --- |
| B1 | `o1 i1 d1 s1 o2 i2 d2` |
| B2 | `s2 o3 i3 d3 s3 o4 i4` |
| B3 | `d4 s4 o5 i5 d5 s5 o6` |
| B4 | `i6 d6 s6 ox1 ix1 dx1 sx1` |

Note: `o1/i1/d1/s1` in B1 are the Stage-3 smoke runs and count toward n —
they are NOT re-run.

### Checkpoints between runs

| When | Checkpoint | Verdict |
| --- | --- | --- |
| After **every** run | Per-run gate: artifacts present, D2/D3, mechanism rows present (M1), harness active in env snapshot, `cli_release_compare.py` produces a table row without unexpected `n/a` | GO/STOP |
| After run 3 of each arm | Early direction check: 2-of-3 consistency on C1/C2 direction; `recall_missed` in ≤1 of 3 for stabilized | GO/DIAGNOSE |
| After run 6 of each arm | Arm-consistency check: direction stable across 6; C2_evict_nonok=0 across all runs | GO/DIAGNOSE |
| After all 28 | Cross-seed sensitivity: compare seed-42 n=6 vs seed-43 n=1 per arm (report-only; a large deviation flags seed dependence, not failure) | report |
| After all 28 | Full C1–C5 analysis + every base-requirement gate (M1/M2/V1/I1/D1/D2/D3, F1/F2) → campaign verdict per arm | verdict |

## Stop/go rules

| Category | Condition | Action |
| --- | --- | --- |
| **Hard STOP** | controller crash/restart (D2), missing `phases_snapshot.json`/`controller_env_snapshot.env` (D3), mechanism not exercised (M1), harness flags absent from env snapshot, `cli_release_compare` crash on a real run folder | fix root cause, rerun the run |
| **DIAGNOSE** | direction inconsistent across replicates, `recall_missed`, eviction non-ok, D1 attributed rows, timing beyond pre-registered windows, unexpected `n/a` | investigate + document in `preflight_log.md` before continuing; n is not a cost — extend the matrix only after a diagnosed cause, never as a blind fix |
| **Report-only** | F1 telemetry gaps, F2 LAN asymmetry, seed-43 deviations, `eviction_overlap` counts | record, do not block |

## Wall time

29 full-length runs × ≈35 min (1920 s phases + setup/teardown) ≈ **17 h**
of VM time, plus Stage 0–1 overhead. Schedule as 4 blocks with a checkpoint
review between blocks.
