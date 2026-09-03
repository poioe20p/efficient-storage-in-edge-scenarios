# research_q3 — Preflight Campaign (staged gates & checkpoints)

**Date**: 2026-09-03 · **Status**: 📋 Planned (merged design v2)

## Overarching goal

**Prove, before the ≈22 h full campaign, that every mechanism the campaign
will measure is live and behaves per its pre-registered contract — in each
return-timing cell the campaign will measure it in.** The preflight is a
mechanism-verification gate, not a results probe: each mechanism must be
observed firing end-to-end at least once, with the correct log shape,
tier, timing, and safety outcomes. Checkpoints run **mid-run** (passive,
read-only, at pre-registered windows) and **between runs** (a run's verdict
must be GO before the next launches), so a broken mechanism is caught
within one ≈40 min run instead of after the whole matrix.

What the campaign assumes true — and therefore what the preflight proves:

| # | Mechanism | Proof run |
| --- | --- | --- |
| 1 | stabilized **early**: storage retention fires (`quarantine_begin` tier=storage reason=retained, VIP_DATA unregister while still syncing); overload recall re-admits **both** tiers; recall **substitutes** the capacity add (decision log `recall`/`recalled_substitution`, not `DataAlert`); cycle-2 quarantine; safe finalization | P1 |
| 2 | stabilized **late**: both tiers **finalize before return** (storage M1); re-spawn at return | P5 |
| 3 | eager-safe (**drained**): begin/end pairs both tiers; evictions `ok`; ghosts 0; D1 clean | P2 |
| 4 | **immediate** ablation: end-only rows; no drain; D1 mechanism-exception attribution | P3 |
| 5 | control (**off**): no release log; no evict files; incumbent path untouched | P4 |
| 6 | timing-axis edit of the canonical `phases.json` (600→480→900) with snapshot provenance | P1, P5 |

## Run matrix (5 runs ≈ 4 h)

| # | Label | Arm | Timing | Proves |
| --- | --- | --- | --- | --- |
| P1 | `research_q3_s_pre_e1` | stabilized | early (hold=480) | #1 (riskiest — new code) |
| P2 | `research_q3_d_pre_e1` | drained | early | #3 |
| P3 | `research_q3_i_pre_e1` | immediate | early | #4 |
| P4 | `research_q3_o_pre_e1` | off | early | #5 |
| P5 | `research_q3_s_pre_l1` | stabilized | late (hold=900) | #2 |

- All runs seed 42, launched with
  `bash source/scripts/testing/research_q3_launch_run.sh arm_<x>.env <label> 42`
  (canonical + arm env merge; `OVERLOAD_MIN_REQUESTS=60`).
- Labels put the arm letter directly after `research_q3_` so
  `cli_release_compare.py` infers the arm (`research_q3_cal_*` always infers
  `stabilized-calibration`, so preflight labels avoid that prefix).
- **Drained/immediate LATE cells are not preflighted**: for those arms the
  timing axis changes only the `hold` duration (no retention logic), and the
  phase-edit mechanism itself is proven by P1(480)/P5(900) on the same
  canonical file. Pre-registered coverage rationale.
- **Between-run edit** (approved scope): canonical
  `source/scripts/testing/phases.json` `hold` 600→**480** before P1 and
  480→**900** before P5; each run folder captures `phases_snapshot.json` as
  provenance. After P5 the file is restored to **480** (campaign baseline
  for B1 early cells) — see Stage 6.

---

## Stage 0 — Local static gate (Windows host, ~2 min, no VM)

Purpose: fail fast on code/config breakage before touching the VM.

| # | Checkpoint | Command | Verdict |
| --- | --- | --- | --- |
| 0.1 | Release-gate selftest | `.venv\Scripts\python.exe source/scripts/testing/rq3rel_p1_01_release_gate_selftest.py` → `SELFTEST PASS` | GO/STOP |
| 0.2 | Compile + shell syntax | `python -m compileall -q source/sdn_controller source/scripts/testing/analysis`; `bash -n` the launcher + preflight scripts | GO/STOP |
| 0.3 | Config integrity | `phases.json` parses (5 phases; `hold=600` pre-edit baseline); canonical env contains `RELEASE_MECHANISM=off`; each `arm_*.env` contains its mechanism + pinned knobs (stabilized = `RELEASE_MECHANISM` + 11 knobs incl. `RELEASE_STABILIZE_S`/`RELEASE_RECALL_K`; others = `RELEASE_MECHANISM` + 9) | GO/STOP |
| 0.4 | CLI synthetic smoke | `tools/release_compare_selftest.py` + `tools/release_compare_selftest2.py` → `SELFTEST OK` (per-tier recall/qf columns render; cell-aware `recall_missed`; audit-row pairing) | GO/STOP |

## Stage 1 — VM sync + harness gate (cloud VM, ~10 min)

Purpose: the controller container bind-mounts the repo workspace, so no
image rebuild is needed — but the VM workspace must contain the new code,
and it must be importable from inside the controller container.

| # | Checkpoint | Command (on VM) | Verdict |
| --- | --- | --- | --- |
| 1.1 | Repo synced + byte-identity | sync working tree → `~/efficient-storage-in-edge-scenarios`; MD5 byte-identity for `main_n1.py`, `main_n2.py`, `node_registry.py`, `release_gate.py`, `cli_release_compare.py` (local vs VM) | GO/STOP |
| 1.2 | Code current on VM | `grep -c RELEASE_MECHANISM source/sdn_controller/scaling_config.py` ≥ 1; `grep -c "_storage_release_gate" source/sdn_controller/main_n1.py` ≥ 2 | GO/STOP |
| 1.3 | Importability in container | `docker exec osken python -c "import sdn_controller.release_gate; print('ok')"` (both `osken` and `osken_2`) | GO/STOP |
| 1.4 | Sudo + docker | `sudo -n true`; `docker info` OK | GO/STOP |
| 1.5 | Controller starts clean | `docker logs osken` contains no `ImportError`/`Traceback`; gate logs `release_gate: mode=off` (canonical env) | GO/STOP |
| 1.6 | Phase-edit dry run | in-place JSON edit of `phases.json` `hold` 600→480 + re-parse OK (no actual edit yet — the runner performs the real edit before P1) | GO/STOP |

---

## Stage 2 — P1 stabilized early (hold=480, ~40 min)

Purpose: prove the NEW storage retention end-to-end (retention begin →
overload recall re-admit → recall-substitutes-add → cycle-2 → finalize),
alongside the proven compute quarantine, in the early-return cell.

**2.0 — Before launch**: edit canonical `phases.json` `hold` 600→480
(approved in-place edit); verify JSON re-parse. `rq3rel_p0_preflight.sh`
re-checks this edit before launching.

**Launch**: start the launcher detached and monitor in parallel:
`nohup bash source/scripts/testing/rq3rel_p0_preflight.sh > /tmp/p1_preflight.log 2>&1 &`,
then `tools/watch_run.py --run-label research_q3_s_pre_e1` plus a detached
checkpoint sampler (both controllers, ≤60 s cadence). The sampler cadence
is advisory: every checkpoint is verified **authoritatively from the
persisting logs** (release-log/decision-log rows carry timestamps), so a
signal that falls between samples is confirmed from the log file as soon as
it appears — live observation is for early abort only.

### In-run checkpoints (passive, read-only; times from run start — baseline 60 + storm 180 + hold 480 + return 180 + drop 900)

| # | Window | Check | Question answered |
| --- | --- | --- | --- |
| 2.1 | t ≈ 60–240 (`storm_mixed`) | compute + storage dynamic spawns; `scale_up` rows | M1/M2: both tiers accumulate surplus |
| 2.2 | t ≈ 330–440 (`hold`+90–200) | **storage** `quarantine_begin` row (tier=storage, trigger=scale_down, reason=retained); controller log `stabilized storage retention began`; VIP_DATA unregister. Window is a **projection** (v2 code has no measured onset yet) — firing outside it is a DIAGNOSE, not a STOP | storage retention fires (new code) |
| 2.3 | t ≈ 450–510 (`hold`+210–270) | compute `quarantine_begin` row (v4-measured 210–270) | compute quarantine armed |
| 2.4 | t ≈ 740–790 (`return`+20–70) | `recall` rows **both tiers** (storage reason=readmitted); **no** compute/storage teardown in `hold`; decision log shows `recall`/`recalled_substitution` (no `DataAlert` at that window) | recall fires on both tiers; recall substitutes the add |
| 2.5 | t ≈ 1030–1100 (`demand_drop`+130–200) | second storage + compute `quarantine_begin` rows | cycle-2 retention/quarantine |
| 2.6 | t ≈ 1500–1720 (`demand_drop`+600–820; nominal +620) | finalization rows both tiers (`scale_down` begin/end or end-only) | H-horizon safe finalize |
| 2.7 | any | both controllers alive; no `Traceback` in `docker logs` | D2 |

### Post-run gates (before P2)

| # | Check | Verdict |
| --- | --- | --- |
| 2.8 | Artifacts: `release_log_lan{1,2}.csv`, `rs_evict_logs_lan{1,2}/`, `rs_status_*.json`, `phases_snapshot.json` (hold=480), `controller_env_snapshot.env` | GO/STOP (D3) |
| 2.9 | `cli_release_compare.py` on the run dir: `C1_stabilized_recall_p50` AND `C1_stabilized_recall_storage_p50` populated (cycle-1 recalls); `C1_stabilized_qf_p50` AND `C1_stabilized_qf_storage_p50` populated (cycle-2 finalizations in `demand_drop`); `C4_recall_missed=0` and `C4_recall_missed_storage=0`; no unexpected n/a | GO/DIAGNOSE |
| 2.10 | Evictions all `ok` (`C2_evict_nonok=0`); `C2_ghosts=0`; D1 clean outside attribution windows (D1 violations = Hard STOP per the rules below; eviction/ghost findings = DIAGNOSE) | GO/STOP · DIAGNOSE |
| 2.11 | Timing vs pre-registered windows (§5 of `experiment_plan.md`); jitter beyond one tick + is_busy deferral → investigate | GO/DIAGNOSE |
| 2.12 | V1/I1: storage CPU rises in `storm_mixed` (resource stats); ≥500 completed requests per LAN in `storm_mixed` (`client_requests.csv`); I2 outcome classes distinct | GO/DIAGNOSE |

## Stage 3 — P2 drained + P3 immediate (eager-safe + ablation, ~1.5 h)

Purpose: prove the eager-safe release shape (begin/end pairs, clean RS) and
the safety-boundary ablation shape (end-only, fire-and-forget) before the
campaign measures them.

**P2 launch**: `research_q3_launch_run.sh arm_drained.env research_q3_d_pre_e1 42`
(hold still 480). **P3 launch** (after P2 gates GO):
`research_q3_launch_run.sh arm_immediate.env research_q3_i_pre_e1 42`.

### P2 — drained (eager-safe) mid-run checkpoints

| # | Window | Check |
| --- | --- | --- |
| 3.1 | t ≈ 60–240 | both tiers spawn |
| 3.2 | `hold` | storage begin/end pair ≈ `hold`+121 (v4-measured onset); compute begin/end pair ≈ last-scale-up+330; **no** `quarantine_begin` rows |
| 3.3 | `return` | no recall rows; ordinary `DataAlert`/`ComputeAlert` rows if demand re-crosses |
| 3.4 | `demand_drop` | cycle-2 releases |

Post-run: 3.5 artifacts (D3) · 3.6 CLI — C1 compute/storage p50 from pairs,
recall/qf columns n/a, `orphan_begin=0` · 3.7 evictions `ok`, ghosts 0, D1
clean · V1/I1/I2 as in 2.12. **Verdict recorded in `preflight_log.md`
before P3 launches.**

### P3 — immediate (safety-boundary ablation) mid-run checkpoints

| # | Window | Check |
| --- | --- | --- |
| 3.8 | t ≈ 60–240 | both tiers spawn |
| 3.9 | `hold` | `end`-only rows both tiers (no `begin`); `fire_and_forget` lines in `rs_evict_logs_lan{1,2}/`; no drain POST in controller logs |
| 3.10 | `hold`/`drop` | D1 rows attributed inside `[end−30 s, end+90 s]` windows; rows outside windows 0× |

Post-run: 3.11 artifacts (D3) · 3.12 CLI — end-only accounting,
`orphan_begin=0`, ghosts informative (the immediate arm's storage-side
cost), no unexpected n/a · V1/I1/I2 as in 2.12. **Verdict before P4.**

## Stage 4 — P4 off control smoke (~40 min)

**Launch**: `research_q3_launch_run.sh arm_off.env research_q3_o_pre_e1 42`.

| # | Window | Check |
| --- | --- | --- |
| 4.1 | t ≈ 60–240 | both tiers spawn (incumbent path) |
| 4.2 | `hold` | incumbent scale-down via container removals; **no** release rows; **no** `/tmp/rs_evict` files |
| 4.3 | any | controllers alive (D2) |

Post-run: 4.4 CLI — arm=off, release-derived metrics n/a (not 0) ·
4.5 artifacts present; decision log shows incumbent rows only; **D1 direct**:
0 `NotPrimary` rows in `client_requests.csv` (the off arm has no release
rows, so no attribution windows exist — check the raw file); V1/I1/I2 as
in 2.12.

## Stage 5 — P5 stabilized late (hold=900, ~45 min)

Purpose: prove the timing-axis flip — with a long valley both tiers
**finalize before return** (storage M1) and re-spawn at return.

**5.0 — Before launch**: edit canonical `phases.json` `hold` 480→900; verify
JSON re-parse.

**Launch**: `research_q3_launch_run.sh arm_stabilized.env research_q3_s_pre_l1 42`
(detached; watchdog + ≤60 s sampler as in Stage 2).

| # | Window | Check |
| --- | --- | --- |
| 5.1 | t ≈ 60–240 | both tiers spawn |
| 5.2 | `hold`+90–200 | storage `quarantine_begin` (reason=retained) — projected window, DIAGNOSE if outside |
| 5.3 | `hold`+210–270 | compute `quarantine_begin` |
| 5.4 | `hold`+560–720 (nominal expiry +601, onset +90–200 + H) | **storage** finalization rows — before return at `hold`+900 (storage M1) |
| 5.5 | `hold`+680–820 (onset +210–270 + 480–520 + tick/is_busy slack) | **compute** finalization rows — before return |
| 5.6 | `return`+0–180 | re-spawns: `added` rows both tiers in `container_events`; `scale_up` decision rows |
| 5.7 | any | controllers alive (D2) |

Post-run: 5.8 artifacts (phases_snapshot hold=900) · 5.9 CLI —
`C1_stabilized_qf_p50` AND `C1_stabilized_qf_storage_p50` populated; recall
columns n/a; `C4_recall_missed`/`C4_recall_missed_storage` **n/a** (late
cell — verifies the analyzer's cell detection) · 5.10 evictions `ok`,
ghosts 0, D1 clean · 5.11 timing vs pre-registered · V1/I1/I2 as in 2.12.

## Stage 6 — Closing cross-run gate

| # | Check | Verdict |
| --- | --- | --- |
| 6.1 | `cli_release_compare.py` over all 5 preflight runs: table renders; arms inferred from labels; per-tier columns populated where expected; no unexpected n/a | GO/DIAGNOSE |
| 6.2 | Verdict recap: every stage GO → campaign go; any open DIAGNOSE → resolved + documented in `preflight_log.md` first | verdict |
| 6.3 | Restore canonical `phases.json` `hold` 900→480 (campaign baseline for B1 early cells); re-parse OK | GO/STOP |

## Stop/go rules

| Category | Condition | Action |
| --- | --- | --- |
| **Hard STOP** | controller crash/restart (D2), missing `phases_snapshot.json`/`controller_env_snapshot.env` (D3), mechanism not exercised (M1 — the arm's expected rows absent), substitution rows absent at 2.4, harness flags absent from env snapshot, `cli_release_compare` crash on a real run folder, D1 rows outside attribution windows | fix root cause, rerun the run |
| **DIAGNOSE** | timing beyond pre-registered windows, `recall_missed=1`, eviction non-ok, unexpected `n/a` | investigate + document in `preflight_log.md` before continuing; never proceed on a blind rerun |
| **Report-only** | F1 telemetry gaps, F2 LAN asymmetry, `eviction_overlap` counts, ghosts for the immediate arm | record, do not block |

## Base-requirements floor (per `testing_requirements.md`)

The preflight checks the mechanism + integrity floor, not benefit:
**M1** (the arm's release fires per tier/LAN) · **M2** (spawned nodes usable;
activated reserves serve ≥1 request) · **V1** (storage-bound bottleneck
evidenced in storm) · **I1** (N=500 completed requests per LAN in
`storm_mixed`, plan-defined) · **I2** (timeout is a distinct outcome class;
denominators consistent) · **D1** (0× non-attributed; the immediate arm's
errors attributed in `[end−30 s, end+90 s]`) · **D2** · **D3**. V1/I1/I2
evidence is collected per run at the 2.12-style post-run gate (storage CPU
in storm; `client_requests.csv` counts and outcome classes).
Benefit gates (B1/B2) and direction comparisons are campaign scope.

## Wall time

5 runs ≈ 3.5–4 h of VM time + Stage 0/1 (≈10 min) + between-run gates
(≈0.5 h) ≈ **4.5 h** total. Schedule strictly in order — P1 → gates → P2 →
gates → P3 → gates → P4 → gates → P5 → gates → Stage 6 closing gate.
