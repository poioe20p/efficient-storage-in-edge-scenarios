# Results — RQ2 Extension (No-Op Arm, Varying-Demand Campaign, Provenance)

**Date**: 2026-09-28 · **Status**: ✅ **campaign COMPLETE — 30/30 runs executed and verified** (Stage A1 checkpoint 6/6; Stage 2 hard gates clean; two instrumentation items open, analysis-side); Part B execution closed; **Part C (`rq2pc`) CLOSED — probes + bounded diagnostic pair executed (2026-09-28); campaign NOT executed (user decision "stop + record"); closure record + findings below** ·
**Plan**: [experiment_plan.md](experiment_plan.md) ·
**Run matrix**: [run_matrix.md](run_matrix.md)

> **Campaign complete (2026-09-28).** All 30 runs executed and verified —
> Stage A1 cleared its §4.7 checkpoint; Stage 2 cleared the hard gates (see
> the timeline rows + [run_matrix.md](run_matrix.md)). Two instrumentation
> items remain open on the analysis side (G2 shift-window anchoring;
> M1/teardown per-phase consolidation). **Part C (`rq2pc` — genuine
> compute-bound) passed its review gate and was frozen at the FREEZE-3
> draft commit (`50b694c`; hash record in [run_matrix.md](run_matrix.md)
> §6); the probe ladder + bounded diagnostic pair @ 2.5 ran 2026-09-28 and
> the campaign was NOT executed — **Part C is CLOSED** ("stop + record",
> user decision; see the Part C record below).**

## Approval record

| Date | Approver | Decision |
| --- | --- | --- |
| 2026-09-26 | User (thesis author) | **APPROVED** — proceed with the canonical sequence; Part B allocation = **Alpha first, Beta fallback pre-registered** (plan §5.3); Stage-1 = **3 replicates/cell** ("3 first", §5.9); steps 1–2 instructed to proceed |

## Run Timeline

| Date | Event | Status |
| --- | --- | --- |
| 2026-09-26 | Plan package drafted (`experiment_plan.md`, `run_matrix.md`, `results.md`) — awaiting approval | 📋 design, pending approval |
| 2026-09-26 | **Plan approved** (Alpha-with-Beta-fallback; Stage-1 = 3 replicates/cell) | ✅ approved |
| 2026-09-26 | **Step 1 executed (VM):** `rq2-v3-final` branched from `rq2-v3-campaign-20260808`; campaign-era edits committed (`5e3d29a`, 216 files); tag `rq2-v3-final-20260926`; clean tree verified | ✅ done |
| 2026-09-26 | **Step 2 executed (VM):** additive set applied on branch `rq2-extension`; VM test gate passed (unit check in the `osken` container; harness dry-parse of both varying files; analyzer regression smokes incl. 2 real v3 runs); committed + tagged `rq2-extension-draft-20260926` | ✅ done |
| 2026-09-26 | Smoke-driven fixes applied before the commit: storage-leg anchor = first **reserve activation** (decision-log) — the first elasticity `node_add` is a baseline bring-up node; M1 zero-action criterion = decision-log `scaleups_non_none` + `reserve_activates` (elasticity `adds_*` kept informational) | validation finding |
| 2026-09-26 | **Step 3 executed (VM):** tag-to-tag diff restricted to **exactly the 16 enumerated additive files** (no deletions; +2273/−64); three arm envs + base phase files **byte-identical**; `policy_gate` diff additive-only; draft-state md5s + tag anchors recorded in run_matrix §1 | ✅ done |
| 2026-09-26 | **Step 4 (FREEZE-1) executed (VM):** pre-probe hashes recorded in run_matrix §1 — launcher `036fb333…` (**provisional**), `rq2_none.env`, three arm envs (byte-identical ✓), `policy_gate`, base cb/db (= AS-RUN snapshot values), plan-package hashes; full 16-file additive set re-verified stable | 🧊 FROZEN — FREEZE-1 recorded (FREEZE-2 pending) |
| 2026-09-26 | **Stage-0 P1 sweep started:** P1-1 `rq2_ext_p1_r6` completed (exit 0); (a,c,d,e,f) pass, **(b) FAIL** (edge CPU 0 % of windows ≥ 75 % of cap) → in-place rate 6→9 applied; r9 next | 🔁 sweeping (1 / ≤4) |
| 2026-09-26 | **P1-2 `rq2_ext_p1_r9` completed (exit 0):** (a,c,d,e,f) pass; **(b) FAIL** (0 % ≥ 75 % of cap; median ~30–32 %); in-place rate 9→12 applied; r12 next | 🔁 sweeping (2 / ≤4) |
| 2026-09-26 | **P1-3 `rq2_ext_p1_r12` completed (exit 0):** (a,c,d,f) pass; **(b) FAIL** (≥75 % in ≤1.7 % of windows; med 37–39 %); first saturation signs (2.8 % timeouts, p95 ~10–13 s, mid-episode spiral then recovery); in-place edits: rate 12→15 [probe] + R1 600→1200 s [probe]; **P1-4 contingency launched** | 🔁 sweeping (3 / ≤4) |
| 2026-09-26 | **P1-4 `rq2_ext_p1_contingency` completed (exit 0):** (a,c,d,e,f) pass (0.627 % timeouts; 352 rps/LAN sustained 20 min); **(b) FAIL** (med 41.4/38.9 %, 0 % ≥ 75 %) → **Alpha verdict: INFEASIBLE → Beta switch** (pre-registered); Beta probe plan pending sign-off | ❌ Alpha closed → Beta |
| 2026-09-26 | **Beta switch APPROVED (user).** Allocation edge 0.6 / storage 0.15; **B-P1 `rq2_ext_b_r15` launched** (cbdb @ edge 0.6 / rate 15 [probe] / R1 600 s); sweep-evidence cleanup authorized (slim archive + delete at sweep close) | ▶ Beta probing (1 / ≤2+1) |
| 2026-09-27 | **B-P1 `rq2_ext_b_r15` completed (exit 0) — PASS** (pooled (b): 31.1 %; both readings recorded 27.1 / 35.0 %; caps provenance `docker inspect` ✓; timeouts 1.574 %). User order: **B-P1b (`rq2_ext_b_r16`)** improvement check; if no improvement → B-P1 rerun (reproducibility) | ✅ Beta bind achieved (pooled) → B-P1b running |
| 2026-09-27 | **B-P1b `rq2_ext_b_r16` completed (exit 0) — NO IMPROVEMENT** (pooled 27.7 % < 30 %; lanes flipped 33.3/22.0 %; p50 261.5 ms degraded; timeouts 2.19 %). Conditional fired: **B-P1 rerun `rq2_ext_b_r15_rep` (rate 15) launched** | 🔁 reproducibility check running |
| 2026-09-27 | **B-P1r `rq2_ext_b_r15_rep` completed (exit 0) — R1 REPRODUCED; (b) boundary** (episode: timeouts 1.621 % vs 1.574 %; completed 208 750 / 208 711 vs 208 696 / 208 897; CPU pooled 29.4 % vs 31.1 %, lanes swapped 31.7 / 27.1 — two-run pooled **30.25 %**). **New finding: B-P1 (not B-P1r) edge-fd incident (R2 lan1 blackout; containers never crashed; R1 unaffected)** — recorded; verdict + next-step call pending | ✅ reproducibility confirmed — ⚠ (b) boundary + platform incident recorded |
| 2026-09-27 | **User ratified (items 1–3):** Beta bind **accepted** (two-run pooled 30.25 %, both readings recorded); incident handling = fd scan added to the D-gates (plan §5.10 D4) + lessons entry; nofile raise / root-cause deferred; **B-P2 `rq2_ext_b_dbcb` launched** (dbcb @ edge 0.6, `sf` arm; R2 first rate 5, R1 rate 15; in-place rate edit md5 `3a06c924 → 46fd82af`) | ▶ B-P2 running |
| 2026-09-27 | **B-P2 `rq2_ext_b_dbcb` completed (exit 0)** — R2 ✓ (storage bind + activation; **P2: replenish 17.6 / 17.0 s → G = 120 s**); **R1 EMFILE meltdown** (×10 892 / ×11 101 fd errors; 149 k dropped/lane; recovered at demand_drop) | ⚠ B-P2 partial — R2/G usable, R1 incident |
| 2026-09-27 | **Two-episode post-hoc audit:** R2 re-read across all probe runs — contingency's R2 was a SEVERE meltdown (missed by the R1-scoped record); B-P1's R2 = lan1 wedge; fd-meltdown incidence now **3 / 8 runs**; battery upgraded to both-episodes; fd decision gates the campaign | ⚠ incident class widened |
| 2026-09-27 | **Fixes applied (user-approved):** edge containers `--ulimit nofile=65536:65536`; log-rotation fix synced to the RQ2 VM (local-only until now — `--log-opt` rotation + aggregator `INFO` default; the 8 prior probe runs ran unbounded); **verification rerun `rq2_ext_b_dbcb_rep` launched** (same dbcb/`sf` config) | ▶ fix verification running |
| 2026-09-27 | **B-P2r `rq2_ext_b_dbcb_rep` completed:** fd scan **0 / 0** (fix verified ✓) BUT **R1 collapsed via MEMCG OOM** — thread explosion (66 596 / 68 041); both edges kernel-killed 07:14:49/50 (`RestartCount=1`), no recovery (demand_drop 0/839 + 0/842); R2 ✓ + **P2 re-confirmed (G = 120 s)** — **dbcb R1 now 2 / 2 failed** | ⚠ overload spiral now terminates in OOM — campaign risk escalated |
| 2026-09-27 | **Root-cause fix applied (user-approved):** edge server bounded concurrency (`app.py` `_apply_request_concurrency_bound`; `EDGE_MAX_CONCURRENCY=1024` default; excess connections wait in the kernel accept backlog — no unbounded thread spawn); md5 `f9f7ad39…` → `3192e12d…`; image rebuilt (`aeaa8b6c7cd3` → `32642cda5693`; pip layer cache-reused — dependency parity ✓); gate confirmed live on both edges; **verification run `rq2_ext_b_dbcb_fix1` launched** (same dbcb/`sf` config) | ▶ fix1 verification running |
| 2026-09-27 | **fix1 result (`20260927_081734_rq2_ext_b_dbcb_fix1`):** concurrency gate **verified live** (engaged once per edge — n1 08:30:00 / n2 08:30:54); fd 0; no OOM / no restarts — **the spiral-death is eliminated** — **but R1 still collapsed**: edge CPU pinned ~92 %; completions ~22 rps/lane; 45 s client waits; `time_proc` 44 972 ms per window (healthy ≈ 0.14 ms); R1 paths 100 % `service_pressure`; **zero storage leases in R1** → **true root cause found: the per-request O(buffer) `/service_pressure` summary scan** (R2’s staged content events fill the 72 k buffer → each rate-15 query scans ~57 k events ≈ tens of ms CPU vs ~1 ms designed; dbcb-only — all 3 dbcb R1s collapsed, cbdb R1s always healthy on an empty buffer) | ⚠ diagnosed → fix2 |
| 2026-09-27 | **fix2 result (`20260927_090315_rq2_ext_b_dbcb_fix2`):** cache fix **PROVEN on the surviving lane** — lan2 compute episode ~300–325 rps (vs ~22 in the fix1 jam), per-request handling 0.2 ms (max 0.3 ms), refresh duty ≈ 1.5 %, fd scan 0/0, zero ERROR lines; **but n1 OOM-killed 09:10:28 during the data episode** — memcg `CONSTRAINT_MEMCG`; total-vm 8.6 GB = ~1024 live threads × 8 MB stacks (cap fully occupied; the request buffer is only ~50 MB); restart-in-place 09:10:29 then **failed to rejoin** (`app NOT ready: MongoDB ping failed within 180s`) → **lan1 dark for R2-tail + R1 + drain (23 min)**; lan2 R1 ~300–325 rps vs healthy 348 (timeouts 8.3 % vs ~1.6 % cbdb; p50 inflated by early R2-drain backlog + lan1-death contamination) — run **D2-tainted → not evidence** | ⚠ jam fixed; memory/concurrency next (fix3) |
| 2026-09-27 | **fix3 applied + verified build (final planned platform fix cycle, user 2026-09-27):** `app.py` memory hardening — `EDGE_MAX_CONCURRENCY` default **1024 → 256** + `EDGE_THREAD_STACK_SIZE_KB` **1024** (worker stacks 8 MB → 1 MB via `threading.stack_size`); md5 `3192e12d…` → `971dc2d5…`; image reconstructed **`FROM 83cf6d973afe` + `COPY source`** → **`30a2c88bc1ce`** (deps frozen ✓; in-image md5s `971dc2d5…` / `3d4c1538…`); **verification run `rq2_ext_b_dbcb_fix3` launched** — pre-stated pass (user-set, 2026-09-27): **no OOM/restart on either edge; both lanes' R1 ≥ ~330 rps; timeouts < 10 %** | ▶ fix3 verification running |
| 2026-09-27 | **Probe finalization + FREEZE-2 executed:** launcher Beta shift-cell caps finalized (six shift cells → `EDGE_CPUS=0.6`; `nn_*` + Part A untouched); probe-finalized commit `34cd78e` (11 files) + tag **`rq2-extension-final-20260927`**; FREEZE-2 launch-state hashes recorded in [run_matrix.md](run_matrix.md) §1 (launcher `db91c566…`; phases `a7db82c8…` / `46fd82af…`; order CSVs unchanged; platform fixes + `app.py` `971dc2d5…` + routes `3d4c1538…`; image `30a2c88bc1ce`); **sweep cleanup executed** — 4 P1 folders (3.4 GB) slim-archived (570 KB, 76 files, md5 `e96c7e77…`) + deleted | ✅ **FINALIZED — campaign launch state frozen** |
| 2026-09-27 | **Stage A1 executed (VM):** 6 × `nn_cb` runs (CSV-1, plan §6) completed — exit 0 ×6, ~22 min run clock each (11:16–14:01 UTC); no retries, no gate trips. Orchestration note: the host terminal hosting the launcher died once mid-stage → orchestrator resumed in adopt mode (in-flight run 4 adopted; no duplicate launches; runs unaffected — execution is VM-side). | ✅ done |
| 2026-09-27 | **Stage-A1 checkpoint PASSED — 6/6** (§4.7 gates D1/D2/D3 + I1 + M1 zero-action + V1): D1 0× NotPrimary; D2 no restart/crash/OOM (container events clean; dmesg OOMs only pre-campaign 07:15/09:11); D3 snapshots + v3 marker present; **I1 = 21 560–21 568 completed/LAN**; **M1 `scaleups_non_none = 0` + `reserve_activates = 0`** (recovery-gap reserve rotation excluded — platform maintenance; its sole record is the documented `scale_down/reserve_loss` recycle row — no activation/action/budget); **V1 = G2 PASS both LANs (official tool) + fires well above the ≥1 requirement (18–21 fired windows/LAN, audit recount)** (edge CPU median ~61 % of the 0.15 cap vs ~14–16 % baseline medians). Health flag: max episode timeout 0.005 %. Bind note: ≥75 %/≥30 % coverage reads 0/6 — that pair is the P1 **probe** criterion, not a §4.7 gate; 0.15-cap cells pin ~61 % (same as v3). | ✅ **PASS → Stage 2 cleared** |
| 2026-09-27 | **Analysis dry-run (checkpoint mitigation) PASSED:** extended analyzer (`rq2_bottleneck_aware_campaign.py`) runs end-to-end (exit 0) and builds the per-segment dataset (validated via a scratch alias on `rq2_ext_b_dbcb_fix3`: both episodes segmented; 16 graphs incl. `shift_recovery.png`). **Finding:** `RUN_RE` does not parse legacy `*_rq2_ext_*` labels (silently skipped) — probe-era re-analysis needs an alias/mapping. Pending (analyzer job): VM-side rollups + summary columns; flagged: `testing_requirements.md` absent from the `rq2-extension` branch. | ✅ done |
| 2026-09-27 | **Part A build-delta caveat recorded (plan §4.6):** extension runs use the probe-hardened edge build (concurrency gate + memory hardening; `/service_pressure` TTL cache ≤ 5 s staleness; image `30a2c88bc1ce`) vs the v3 comparator builds — carried as a labeled caveat on Part A cross-era comparisons (Q-A1..Q-A3). | ✅ recorded |
| 2026-09-27 | **Independent Stage-A1 gate audit (pre-Stage-2)** — all §4.7 gates re-verified from raw artifacts: G2 official tool re-run (PASS, all 6 runs); I1/timeout recount matches (21 560–21 568 completed/LAN; ~5 episode timeouts total; episode outcome classes = completed/timeout/canceled only); M1 recount (0 non-`none` scale_up actions; 0 `reserve_activate`; sole nonstandard row = `scale_down,reserve_loss` recycle record); D2/D3/D4 re-confirmed (1 service start per edge; 0 EMFILE; v3 marker present). Minor parsing note: aggregate `client_requests.csv` last field carries CRLF — parse robustly. | ✅ **all gates properly passed — audit closed** |
| 2026-09-28 | **Stage 2 executed (VM):** 24 runs (CSV-2) completed — exit 0 ×24 (~38 min two-episode / ~24 min single-episode wall); zero retries, zero gate trips; **campaign COMPLETE** 08:04. Orchestration note: two host-side terminal deaths mid-stage → launcher resumed in adopt mode both times (no duplicate launches; runs unaffected — execution is VM-side). | ✅ done |
| 2026-09-28 | **Stage-2 verification:** hard gates clean (0 restart/crash/OOM; 0 EMFILE; 0 NotPrimary; snapshots + markers ×24); I1 = 36/36 episode segments ≥ 5000/LAN (min ≈ 38.9 k, max ≈ 212 k); max episode timeout 22.4 % (no collapsed-run flags); arm signatures as designed (nn inert; cf compute-only; sf storage-only; ba both; both segments per shift run; storage adds served traffic). | ✅ verified |
| 2026-09-28 | **Open instrumentation items (analysis-side; do not affect run validity):** (i) G2 shift-window anchoring — official per-segment tool 60/84 vs as-run re-anchored 84/84 (tool fix pending); (ii) M1/teardown per-phase consolidation + `demand_drop` teardown-timing interpretation (pending). | ⚠ recorded |
| 2026-09-28 | **Closure + VM cleanup:** post-campaign teardown (containers 12→0; clients 48→0; netns 0; veths 63→0; transient dyn volumes removed; static seeds + images kept; all 30 run folders retained, 46 GB archive; 77 GB free). **Part B execution closed**; **Part C (`rq2pc` — genuine compute-bound) pre-registration in preparation** (analysis-side items carried forward). | ✅ closed |
| 2026-09-28 | **Part C review gate + FREEZE-3 draft committed** (`50b694c`, 9 files, no tag — the probe-finalized tag follows the ladder): all review 🔴/🟡 issues fixed; artifacts byte-identical local↔VM; `phases_rq2pc_cb.json` = byte copy of the base cb file (`d40f5f59…`); analyzer RUN_RE updated (`(?:pc)?` — rq2 + rq2pc match, probes excluded); restricted diff = exactly the enumerated paths; pre-run verification passed (clean-VM 0/0/0; 77 GB free); md5 record in [run_matrix.md](run_matrix.md) §6. | ✅ frozen (draft) |
| 2026-09-28 | **Part C probe ladder executed (VM):** P-0 `nn`@1.5 → no lock (slow-share 0.999 %, p50 3.3 ms); P-1 `nn`@3.0 → **LOCK** (99.0 %, p50 3.42 s) ⇒ **R* = 3.0** (P-2/P-3 skipped); P-4 `cf`@3.0 → lock re-check PASS but **signature FAIL** — 4 adds/LAN with **zero collapse** (PRE→POST p50 ratio 0.86 / 0.81; POST slow-share 99.2 / 96.7 %; completions ≈ the `nn` lock run) — log: [partc_probe_log.txt](partc_probe_log.txt) | ⚠ probes — 3.0 not treatable |
| 2026-09-28 | **Part C diagnostic pair @ 2.5 executed (user-approved, bounded):** `nn`@2.5 LOCK (97.0 %, p50 2.79 s); `cf`@2.5 first treatment signal — **lan2 PRE→POST ×21.4** (min 3–5 at 3–4 ms) — but **unstable**: lan1 ×0.76 (never collapsed), lan2 **relapse from min 6**, lan1's added nodes **torn down mid-episode** by the registry liveness cull (14:22:48–14:24:50) | ⚠ partial + contaminated |
| 2026-09-28 | **Part C CLOSED — "stop + record" (user decision):** focused analysis (registry liveness cull; near-capacity assignment concentration; no clean treatable window 1.5–3.0) → **campaign NOT executed**; closure record appended below; `phases_rq2pc_cb.json` restored to the frozen state; closure records committed (records-only; no `-final-` tag) | ⏹ closed (no campaign) |
| 2026-09-28 | **Part A/B pre-battery verification pass (read-only):** Part A headline numbers recomputed from raw artifacts — v3 `latency_summary` reproduced exactly; plan-convention recompute **Q-A1 0.680** / **Q-A2 0.487** (draft quotes ≈0.56–0.62 / ≈0.35 are convention-sensitive); Q-A3 + startup-transient (zero-add `sf_cb`: minute-0 3.9–4.4 s → 3 ms) confirmed; pin list + label caveats appended below | ⚠ recorded (pre-battery) |

## Probe Record — Stage 0

<!--
To be populated ONLY when probes run (plan §5.4; run_matrix.md §2).
Probes are not evidence — recorded here for the probe record and for
finalizing G / the Alpha–Beta decision. Rows mirror run_matrix.md §2
(P1-1..P1-4, P2, P3).

| Probe | Label | Config (shape / rate / caps) | Result | Verdict | Notes |
| --- | --- | --- | --- | --- | --- |
| P1-1 | rq2_ext_p1_r6  | cbdb · rate 6 · edge 1.20 / storage 0.15 · arm rq2_none.env · direct make chain | — | — | ALL-of acceptance: compute fires; edge ≥ 75 % cap in ≥ 30 % of episode windows; storage quiet; I1 ≥ 5000/LAN; timeout < 10 %; D-gates (thresholds plan-defined — plan §1.3) |
| P1-2 | rq2_ext_p1_r9  | cbdb · rate 9 · same config | — | — | as P1-1 |
| P1-3 | rq2_ext_p1_r12 | cbdb · rate 12 · same config | — | — | last Alpha point |
| P1-4 | rq2_ext_p1_contingency | highest feasible rate (plan-defined: highest sustained without client-side saturation — client drops < 10 % — recorded in the probe record) · R1 duration doubled to 1200 s [probe] | — | — | contingency (if 6/9/12 all fail); on pass the campaign R1 duration is 1200 s [probe]; still failing → Alpha infeasible → Beta switch recorded |
| P2 | rq2_ext_p2_reserve | reserve replenishment timing (v3 db records, else dedicated dbcb probe · sf arm) | — | — | sets G = max(120 s, replenish_p95 + 60 s) |
| P3 | rq2_ext_p3_boundary | carried-state verification across the phase boundary (6 items; strict-commit verified NOT engaged — excluded) | — | — | — |
-->

**P1 sweep CLOSED (2026-09-26) — Alpha INFEASIBLE → Beta switch** (plan §5.4); Beta probe plan **approved (user, 2026-09-26)** — B-P1 **PASS** (pooled, ratified 2026-09-27); B-P1b **no improvement** (pooled 27.7 %) → **B-P1 rerun (`rq2_ext_b_r15_rep`) launched.**

| Probe | Label | Run folder | Result | Verdict |
| --- | --- | --- | --- | --- |
| P1-1 | `rq2_ext_p1_r6` | `20260926_194930_rq2_ext_p1_r6` (exit 0, ~32 min) | (a) ✓ compute fired (7–8 windows/LAN); **(b) FAIL — edge CPU max 54.2 % of cap, median ~25 %, 0/119 windows ≥ 75 %**; (c) ✓ zero storage fires in R1 (median storage CPU 6 %); (d) ✓ I1 = 85 813 / 85 795 completed per LAN; (e) ✓ timeout 0.006 %; (f) ✓ D-gates (0 NotPrimary; exit 0; no OOM/kill markers; snapshots present) | ❌ **FAIL** → sweep to r9 |
| P1-2 | `rq2_ext_p1_r9` | `20260926_203048_rq2_ext_p1_r9` (exit 0, ~32 min) | (a) ✓ compute fired (8–9 windows/LAN); **(b) FAIL — edge CPU max 53.0 / 47.0 %, median ~30–32 %, 0/120 windows ≥ 75 %**; (c) ✓ zero storage fires in R1; (d) ✓ I1 = 128 270 / 128 212 completed per LAN; (e) ✓ timeout 0.006 %; (f) ✓ D-gates | ❌ **FAIL (b)** → sweep to r12 |
| P1-3 | `rq2_ext_p1_r12` | `20260926_210850_rq2_ext_p1_r12` (exit 0, ~32 min) | (a) ✓ (5–7 fires/LAN); **(b) FAIL — edge CPU med 37.2 / 38.6 %, max 71.6 / 77.5 %, ≥75 % in 0 / 1.7 % of windows**; (c) ✓ zero storage fires; (d) ✓ 165 665 / 165 471 completed (~276 rps/LAN delivered); **(e) ⚠ 2.835 % timeouts (within limit) but the service hit a transient saturation spiral — p95 10.6 / 13.1 s, p99 ~26–28 s, timeouts concentrated in minutes 5–8 of R1, then recovered**; (f) ✓ D-gates | ❌ **FAIL (b)** — service-capacity wall ≈ 276 rps/LAN at only ~38 % of the edge cap; rate is not the binding lever |
| P1-4 | `rq2_ext_p1_contingency` | `20260926_214756_rq2_ext_p1_contingency` (exit 0, ~47 min) | (a) ✓ 27 fires/LAN; **(b) FAIL — edge CPU med 41.4 / 38.9 %, max 65.6 / 59.1 %, 0 % ≥ 75 %**; (c) ✓ zero storage fires; (d) ✓ 421 762 / 422 295 completed per LAN (**352 rps/LAN sustained for 20 min**); (e) ✓ 0.627 % timeouts (bounded transient at min 5–6, then clean; p50 16.9 ms); (f) ✓ D-gates ⚠ **R2 post-hoc (2026-09-27): SEVERE meltdown — p50 33 / 74 s, timeouts 14 / 22 %, fd ×12 232 (R1 unaffected; original battery was R1-scoped)** | ❌ **FAIL (b)** — rate 15 [probe] + 1200 s [probe]: bind band still unreachable → **Alpha infeasible** |
| B-P1 | `rq2_ext_b_r15` | `20260926_223952_rq2_ext_b_r15` (exit 0, ~37 min) | (a) ✓ 8–9 fires/LAN; **(b) PASS — pooled reading 31.1 % ≥ 30 %** (edge CPU med 68.3 / 70.2 % of the 0.6 cap; ≥ 75 % in 27.1 % lan1 / 35.0 % lan2 — lan1 borderline under the strict per-LAN reading; both recorded); (c) ✓ zero storage fires in R1; (d) ✓ 208 696 / 208 897 completed per LAN; (e) ✓ 1.574 % timeouts (p50 25.5 ms); (f) ✓ D-gates ⚠ — **post-run forensic (2026-09-27): lan1 fd-exhaustion outage in R2→run end** (R1/episode unaffected; see incident note below); **caps provenance: edge NanoCpus 0.6 / storage 0.15 (`docker inspect`)** | ✅ **PASS** (pooled convention, ratified 2026-09-27; incident noted) |
| B-P1b | `rq2_ext_b_r16` | `20260926_232452_rq2_ext_b_r16` (exit 0, ~35 min) | (a) ✓ 9/9 fires; **(b) NO IMPROVEMENT — pooled 27.7 % < 30 %** (lan1 33.3 % ↑ / lan2 22.0 % ↓ — lanes flipped; strict reading mixed); rate 16 also **degraded service** (p50 **261.5 ms** vs 25.5 ms at r15; timeouts 2.19 %); (c) ✓ zero storage fires; (d) ✓ 220 902 / 221 244 completed per LAN; (e) ✓ within limits but degraded; (f) ✓ D-gates | ❌ **no improvement** → conditional fired: B-P1 rerun (rate 15) |
| B-P1r | `rq2_ext_b_r15_rep` | `20260927_000357_rq2_ext_b_r15_rep` (exit 0, ~31 min) | (a) ✓ compute fires present (R1 fire-rows 18/18); **(b) 29.4 % pooled < 30 %** (edge CPU med 65.2 / 67.5 % of the 0.6 cap; ≥ 75 % in 31.7 % lan1 / 27.1 % lan2 — lanes swapped vs B-P1; two-run pooled **30.25 %** — the cut sits inside jitter); (c) ✓ zero storage fires in R1; (d) ✓ 208 750 / 208 711 episode completed; (e) ✓ episode timeout 1.621 % (p50 32.4 / 31.2 ms; p95 8.2 / 8.3 s); (f) ✓ D-gates (fd scan clean; container events normal; snapshots present); **caps provenance ✓ (`docker inspect`)** | 🔁 **R1 reproduced — (b) boundary** (31.1 / 29.4 across the two rate-15 runs) |
| B-P2 | `rq2_ext_b_dbcb` | `20260927_052152_rq2_ext_b_dbcb` (exit 0, ~32 min) | **(R2 first) storage bind + activation ✓** — storage CPU med 41.0 / 41.9 % of cap (activated node shares load; none-arm peers 76–78 %); reserve activated 1×/LAN (05:24:06 / 05:24:11; storage budget 1); edge CPU med **75.5 / 76.4 %** — **R2 “compute-quiet” NOT met** (regime finding: absolute edge load ≈ 0.45–0.48 cores, same as Alpha’s R2 read against 1.20); R2: completed 54 082 / 55 219, timeouts 3 167 / 2 078, p50 1.58 / 1.27 s; **(P2) replenish = activation→next READY = 17.6 / 17.0 s → G = max(120, 77.6) = 120 s** (settle checks 22 s / 42 s < G); **(R1) EMFILE meltdown** — fd errors ×10 892 / ×11 101 (all in R1), dropped 149 447 / 149 012, ~10.2 k / 212.7 k completed, p50 ~204–213 s; recovered at demand_drop; (P3) boundary observations partial | ⚠ **P2 ✓ (G = 120 s) + R2 ✓; R1 meltdown — B-P2 partial** |
| B-P2r | `rq2_ext_b_dbcb_rep` | `20260927_065605_rq2_ext_b_dbcb_rep` (exit 0, ~32 min) | **fd fix verified — 0 EMFILE** (vs ×10 892 / ×11 101); **(R2 first) ✓ again** — storage med 41.7 / 41.8 %; activations ×2 lan1 / ×1 lan2 (06:57:58 / 07:00:30 / 06:58:23), replenish 17.1 / 16.2 / 17.5 s → **P2 re-confirmed (G = 120 s)**; R2 completed 55 382 / 55 955 (96–97 %), timeouts 1 849 / 1 328, p50 1.26 / 1.19 s; **(R1) collapsed — MEMCG OOM** — thread explosion (66 596 / 68 041), kernel `CONSTRAINT_MEMCG` kills of both edges 07:14:49/50 (total-vm 43 GB; `RestartCount=1`); no recovery (demand_drop 0/839 + 0/842); R1 completed 19.3 k / 27.9 k of ~212 k; p50 67 / 56 s | ❌ **fd fix works; R1 OOM meltdown — dbcb R1 2/2 failed** |

| B-P2f | `rq2_ext_b_dbcb_fix1` | `20260927_081734_rq2_ext_b_dbcb_fix1` (exit 0, ~32 min) | **gate verified live** — engaged once per edge (n1 08:30:00 / n2 08:30:54); fd scan **0 / 0**; no OOM, no restarts — **spiral-death eliminated** ✓; **(R1) still collapsed — second mechanism:** edge CPU pinned ~92 %, ~22 rps/lane served, 45 s waits, `time_proc` 44 972 ms/window (healthy ≈ 0.14 ms), R1 paths 100 % `service_pressure`, zero storage leases in R1; the acceptance jam signature (HTTP 200, `time_db ≈ 0`, 45 s `time_proc`) | ⚠ **death fixed; R1 jam persists — root cause = per-request O(buffer) summary scan (dbcb-only) → fix2 launched** |
| B-P2g | `rq2_ext_b_dbcb_fix2` | `20260927_090315_rq2_ext_b_dbcb_fix2` (exit 0, ~30 min) | **jam fix verified on the surviving lane** — lan2 compute episode ~300–325 rps steady (vs ~22 in fix1), per-request handling 0.2 ms (max 0.3 ms), refresh duty ≈ 1.5 % (119 requests > 50 ms ≈ exact cadence), fd scan 0/0, zero ERROR lines; **BUT n1 OOM-killed 09:10:28 during the data episode** (~1024 live threads × 8 MB stacks = total-vm 8.6 GB; cap fully occupied) and after restart **failed to rejoin** (`app NOT ready: MongoDB ping failed within 180s`) → lan1 dark 23 min; lan2 R1 timeouts 8.3 %, p50 inflated by early R2-drain backlog + lan1-death contamination | ⚠ **cache fix PROVEN; run D2-tainted (n1 OOM+rejoin) → not evidence → B-P2h** |
| B-P2h | `rq2_ext_b_dbcb_fix3` | `20260927_100227_rq2_ext_b_dbcb_fix3` (exit 0, ~30 min) | **C1 ✓** no OOM/restart (RestartCount 0/0; zero memcg kills; gate never blocked — 256 sufficed; live memory ≤ ~86 MiB of 512; fix2 died at 473 MiB); **C3 ✓** compute-episode timeouts **6.0 % / 5.2 %** (< 10 %); **C4 ✓** fd 0/0; **C2 ◐** episode avg **307 / 312 rps** (< ~330) — **bimodal**: constrained head 10:14–10:18 (~170–210 rps delivered; edge CPU 37–55 %, handlers 0.1–0.4 ms — a *delivery-side* constraint) coinciding with the **storage reserve release/reconfig burst at the data→compute boundary** (10:13:31–10:14:19: dyn-node removals + re-add, replicaset reconfig — `node_lifecycle_timings.csv`), then **full healthy absorption from 10:19** (354 rps server-side; final minutes zero drops/timeouts); symmetric across lanes | ✅ **C1/C3/C4 PASS; C2 steady-state healthy (head = boundary churn, documented)** |

**Probe notes (P1-1):** probes are not evidence. Platform note: the storage
**standby reserve** recycled during the run via `reserve_loss` maintenance
(remove + respawn every ~4–8 min; brief storage-CPU spikes at the recycle
moments) — policy-independent (zero selected actions; `fixed_none` selection
inert ✓) and also present in v3 records (e.g. `cf_cb_1`). Rate point r6 sits
below the bind band: edge CPU scales with offered load (no saturation jump),
so the sweep continues (r9, r12). r9 rose to a median ~30–32 % of cap
(sub-linear in rate) — still far from the 75 % bind band; r12 next.
**Sweep conclusion (r6/r9/r12):** edge CPU is sub-linear in rate (med 25 →
31 → 38 %) while the *service* hits a capacity wall between r9 (p95 30 ms,
15 timeouts) and r12 (2.8 % timeouts, p95 10–13 s, mid-episode spiral then
recovery) at ~276 rps/LAN — i.e. the wall is **not** edge-CPU-bound, and no
rate inside the sustained envelope approaches 75 % of the 1.20 cap.
P1-4 (one confirmatory attempt at the highest feasible rate, R1 = 1200 s)
tests this ceiling directly. **P1-4 rate = 15 [probe]:** one step beyond the
wall (≈1.25× the last sweep point); client-side drops stayed ≈0 through r12
(the harness was not the limiter), so the single attempt probes the
post-wall regime for the record.

**Alpha verdict (pre-registered, plan §5.4): INFEASIBLE → BETA switch.**
All four rate points fail (b) and the gap is **structural**: edge CPU grows
sub-linearly with rate (~25 → 31 → 38 → 41 % of the 1.20 cap), so no rate
inside the sustained envelope approaches 75 % of cap; pushing rate only buys
a bounded saturation transient (r12: 2.8 % timeouts; r15: 0.63 % in 20 min).
Alpha comparability limits (restated at the switch, plan §5.3): Alpha's R1 is
**not** the v3 cb episode (rate 1.5 @ edge 0.15); the Beta switch **re-anchors
both phases** and loses the exact-v3 R2 anchor — to be restated in this probe
record at Beta finalization. **Beta allocation:** edge ≈ **0.6** / storage
0.15 (mid). Measured basis: the same R1 episode at edge 0.6 puts the observed
~0.48–0.50 cores at ~80 % of cap (bind achievable, evidence-backed); R2 keeps
the v3 storage-bind config at 0.15 (storage CPU med 31–46 % of cap, spikes
~87 % in the probes) with compute-quietness to be verified at the lower edge
cap. **Beta probe plan (pending sign-off):** B-P1 `cbdb` @ edge 0.6 / rate 15
(check (b), (e), fires, storage quiet); B-P2 `dbcb` @ edge 0.6 with the `sf`
arm (storage bind + compute quiet in R2; also serves **P2** reserve-replenish
→ `G` derivation and **P3** boundary observations). ≤ 2 runs + 1 contingency.

**Beta probes — APPROVED (user, 2026-09-26) and running.** Allocation: edge
**0.6** / storage 0.15. B-P1 `rq2_ext_b_r15` (cbdb @ edge 0.6 / rate 15
[probe] / R1 600 s / `rq2_none` arm) launched 2026-09-26; B-P2
`rq2_ext_b_dbcb` (dbcb @ edge 0.6, `sf` arm, R2 exact-v3 first) follows if
B-P1 passes. **Sweep-evidence cleanup (user-authorized, 2026-09-26):** at
sweep close the four P1 probe run folders are deleted after a slim provenance
archive (key CSVs only) is extracted — an explicit exception to the
never-delete policy; all conclusions remain in this probe record.

**B-P1 verdict + follow-up (user-ratified 2026-09-27).** Leg (b) aggregation
was not pinned in the plan text; the **pooled** reading (all episode windows,
both LANs) is ratified: **B-P1 PASSES (31.1 % ≥ 30 %)** — with both readings
recorded (lan1 27.1 % under the strict per-LAN reading, flagged borderline).
Cap provenance verified on the live containers (`docker inspect`: edge
NanoCpus = 0.6, storage = 0.15). **User instruction:** run **B-P1b
(`rq2_ext_b_r16`, rate 16)** to test improvement; **if it does not improve,
re-run B-P1 (`rq2_ext_b_r15_rep`, rate 15) as a one-off reproducibility
check** (explicit budget extension beyond Beta ≤ 2 + 1).

**B-P1b outcome (2026-09-27): NO IMPROVEMENT** — pooled 27.7 % < 30 %
(lan1 33.3 % ↑ / lan2 22.0 % ↓; the lanes flipped) and service degraded
(p50 261.5 ms vs 25.5 ms at rate 15; timeouts 2.19 %). **Conditional fired:
B-P1 re-run `rq2_ext_b_r15_rep` (rate 15) launched for the reproducibility
check.** Read so far: the bind is strong in all three Beta runs (median
~67–72 % of the 0.6 cap) but the ≥ 75 %-coverage cut sits in the run/lane
jitter band (~22–35 %).

**B-P1r outcome (2026-09-27): R1 REPRODUCED — the (b) cut is a boundary.**
Episode-scoped, both rate-15 runs: timeouts 1.621 % (vs 1.574 %); completed
208 750 / 208 711 (vs 208 696 / 208 897); per-lane p50 32.4 / 31.2 ms
(vs 26.7 / 24.5); p95 8.2 s (vs 9.3–10.2 s); CPU pooled 29.4 % (vs 31.1 %)
with the lanes swapped (31.7 / 27.1 vs 27.1 / 35.0) — a 2-window difference
out of 238 windows, i.e. **two-run pooled 30.25 %**. Reading: the episode
bind and service profile reproduce; the pre-registered ≥ 30 % cut sits
inside run/lane jitter; **(b) ACCEPTED by the user (2026-09-27)** — the
Beta bind is accepted on the two-run pooled 30.25 %; both readings recorded
(strict-per-LAN and pooled) per the ratified convention.

**Platform incident recorded — edge EMFILE burst (B-P1; forensics
2026-09-27).** `edge_server_n1` logged `OSError: [Errno 24] Too many open
files` ×1 170 (22:55:20–22:55:44) and went silent; **lan1 stopped serving
from ~22:56 to run end** (`demand_drop` lan1 = 840/840 timeouts; edge
process never restarted; container exit 0 at teardown). `edge_server_n2`
logged ×2 918 in the same R2-onset window but kept serving; **R1/episode
metrics uncontaminated** (fd errors start after R1). Same signature, smaller
and non-fatal, in `rq2_ext_p1_contingency` (×12 232 at its R2 onset) — fd
pressure at the high-rate regime is recurring (2/7 probe runs), occasionally
fatal (1/7); the other five runs (r6, r9, r12, B-P1b, B-P1r) are clean.
Edge container nofile limit = 1024 (no `--ulimit` at launch; no artifact
records fd counts — the log signature is the detector). **Accepted (user,
2026-09-27):** per-run fd scan added to the D-gate set (plan §5.10 D4) +
lessons-log entry; nofile raise and root-cause deferred (comparability vs v3).

**Two-episode post-hoc audit (2026-09-27).** Earlier batteries were
episode-1-scoped; a full-run re-read after B-P2 shows second-episode (R2)
behaviour diverges materially and two meltdowns had been under-observed.
R2 per run (completed l1 / l2 · timeouts · p50 · fd errors · verdict):

| Run | R2 completed (l1 / l2) | R2 timeouts | R2 p50 | fd errors | R2 verdict |
| --- | --- | --- | --- | --- | --- |
| r6 | 57 263 / 57 315 | 15 / 24 | 151 / 183 ms | 0 | clean |
| r9 | 56 829 / 57 041 | 419 / 214 | ~1.0 s | 0 | mild |
| r12 | 57 302 / 57 218 | 32 / 40 | 280 / 369 ms | 0 | clean |
| contingency | 44 198 / 44 633 | 8 140 / 12 439 | 33 / 74 s | ×12 232 | **SEVERE meltdown (R1-scoped record missed it)** |
| B-P1 | 11 780 / 24 881 | 24 715 / 13 959 | 14 / 17 s | ×4 088 | **meltdown (lan1 wedge)** |
| B-P1b | 56 284 / 56 922 | 958 / 261 | 1.19 / 0.99 s | 0 | clean |
| B-P1r | 54 606 / 54 894 | 2 584 / 2 324 | 1.38 / 1.36 s | 0 | mild |
| B-P2 | 54 082 / 55 219 | 3 167 / 2 078 | 1.58 / 1.27 s | 0 in R2 (22 k in R1) | usable |

Consequences: the P1-4 row above is annotated; the post-run battery now
covers **both episodes** (D4 fd scan + per-phase per-lane service health);
fd-meltdown incidence is **3 / 8 probe runs**. At Beta caps, R2 is
edge-hot (~75–80 % of the 0.6 cap) by default — the “compute-quiet”
expectation only holds at the Alpha 1.20 cap (absolute edge load ≈ 0.45–0.5
cores in all runs). B-P2 net: **P2 ✓ (G = 120 s), R2 ✓ (usable), R1 ✗
(meltdown)** — the fd root-cause / nofile decision now gates the campaign
(user call).

When P1 concludes, the passing rate point (or the Alpha→Beta switch) and the
finalized `G` from P2 will be recorded here; P3's verified carried-state
table (6 items) will reference back to
[experiment_plan.md](experiment_plan.md) §5.4.

## Freeze Artifacts (pre-FREEZE-1)

| Artifact | Status |
| --- | --- |
| Dual-bind scan capture (v3 decision-log scan) — **recorded block below** (original 2026-09-26: **23 / 10,044** scale-up windows, `ba` = 3; regenerated 2026-09-28: **27 / 12,207** over 44 v3-marker folders, `ba` = 2 — wider population; 0.22 % both times) ([experiment_plan.md](experiment_plan.md) §8 item 5; [run_matrix.md](run_matrix.md) §5) | ✅ recorded (2026-09-28) |

**Dual-bind scan — recorded block (closed 2026-09-28).** Scan definition: decision-log rows with `action_type=scale_up`; "both tiers fired" = `compute_fired=1 AND storage_fired=1` in the same window. Original 2026-09-26 scan: **23 / 10,044** windows (0.23 %), `ba` = 3. Regeneration 2026-09-28 over all v3-marker `cf/sf/ba × cb/db` folders (44 runs; includes reruns/exclusions): **27 / 12,207** windows (0.22 %), `ba`-family = 2. Rarity conclusion unchanged; simultaneous dual-bind stays out of scope (plan §2.1).

## Campaign Runs

**Executed — 30 run folders** (Stage A1: `nn_cb` × 6; Stage 2: `nn_db` × 6 + 18 shift runs). Cells, order CSVs and the checklist: [run_matrix.md](run_matrix.md). Verification + closure: timeline rows above; two instrumentation items remain open on the analysis side; a **pre-battery verification pass** (read-only recompute + pin list) is recorded immediately below.

## Part A/B — Pre-Battery Verification Note (2026-09-28)

**Status: ⚠ PRE-BATTERY reference — NOT frozen.** Independent read-only
recomputation of the Part A headline numbers from raw run artifacts, ahead
of the **final battery** (the two open analysis-side items — G2 shift-window
fix; M1/teardown consolidation — remain pending; extension numbers freeze
only after it). Purpose: reconcile the draft RQ2 fact base (2026-09-28)
against what the files actually support. Method: per-run
`client_requests.csv` → episode-phase rows, completed-only latency, **both
lanes pooled per replicate**, median-of-replicates / available-pool
conventions (plan §4.6, seed-42). Scripts (read-only, kept for the battery):
`temp/qa_verify.py`, `temp/qa_sfcb.py` (VM copies in `/tmp/`).

### Recomputed values (plan convention)

| Quantity | Recomputed |
| --- | --- |
| `cf_db` episode p95 — available seed-42 (`_1.._4`), s | 0.706 · 0.763 · 0.923 · 1.135 → **median 0.923** |
| `nn_db` episode p95 — seed-42 (`_1.._5`), s | 1.357 · 1.130 · 49.059 · 1.820 · 0.970 → **median 1.357** |
| **Q-A1 ratio / support** | **0.680** / **0/4** replicates above the `nn_db` median |
| `sf_db` episode p95 — seed-42 (`_1.._5`), s | 0.502 · 0.502 · 0.661 · 0.756 · 0.737 → **median 0.661** |
| **Q-A2 ratio / support** | **0.487** / **5/5** replicates below the `nn_db` median |
| Q-A3 episode p50 | `nn_cb` **3.20 ms** (all six) · `cf_cb` **3.3–4.8 ms** (median 3.50 ms; ratio 1.094) |
| Startup-transient check (per-minute p50) | v3 `cf_cb`: slow in **minute 0 only** (0.4–2.2 s) → minute 1+ ≈ 3 ms; **zero-compute-add** `sf_cb` reruns: minute 0 **3.9–4.4 s** → minute 1+ ≈ 3 ms; extension `nn_cb`: flat 3.2–3.4 ms (no slow phase) |

Convention sensitivity (same data, alternative cuts): Q-A1 ≈ 0.57–0.74
(lane ratios 0.690 / 0.870); Q-A2 ≈ 0.37–0.54 (lane ratios 0.546 / 0.477);
exploratory 512m-subset cut for `sf_db` (`_5` only): 0.543.

### Cross-checks (read-only; no contradictions)

- The v3-era `latency_summary.csv` reproduces **exactly** under this
  pipeline (`cf_db_1` 0.7059 vs archived 0.705865; `cf_db_2` 0.7627 vs
  0.762670; `sf_db_1` 0.5023 vs 0.502275) — differences below are convention
  choices, not pipeline error.
- Storage block (11/11 activations = sf 6 + ba 5; CPU relief 0.57–0.66× in
  12/12 LANs; B2 median 0.727 [0.574, 1.393]; floor-safe scale-down),
  cf-on-data band (706–1135 ms vs aligned 502–756 ms), classifier 88–93 %,
  36/34 pools and the `ba_db_2`/`cf_db_5` exclusions: consistent with the
  frozen v3 record ([rq2_conclusions.md](../../../../../tese/research_questions/rq2/rq2_conclusions.md) §§2–3); `cf_db` rep-5 folder absent ✓.
- Part C values: verified in the closure audit (§ Part C above) — not restated here.

### Flags for the final battery (pin before freezing)

1. **Ratio conventions.** The draft fact-base quotes (Q-A1 ≈0.56–0.62;
   Q-A2 ≈0.35) do not reproduce under the plan convention (**0.680** /
   **0.487**; bands above). The battery must pin the convention (seed-42 /
   available pool; lane pooling) and restate. Conclusions unaffected —
   Q-A1 ≪ 1.2 with support 0/4; Q-A2 ≤ 0.85 with support 5/5.
2. **"≈3× at p95"** follows the Q-A2 ratio → ≈2× at 0.487 (≈2–2.8× across
   variants). Quote with the frozen ratio.
3. **Point values.** Use medians/ranges — cf_db **0.92** (0.71–1.13);
   sf_db **0.66** (0.50–0.76); nn_db **1.36** (0.97–1.82; one degraded run
   at 49.1) — rather than band-interior figures (0.84 / 0.5).
4. **L4 collapse counts** (cf 0/6; ba ≈1/5): hold for the battery. The
   anchored collapse definition must classify the final-minute fast tails
   observed in `cf_shdbcb_1/2` and `ba_shdbcb_1/3` and state the ba
   denominator. Context: shift compute episodes run at rate 15; several runs
   never bind (`cf_shdbcb_3`, `ba_shcbdb_1`), others jam to p50 16–126 s —
   "recovery almost nowhere to measure" is qualitatively supported.
5. **Labels.** Apply the **build-delta** caveat (extension = probe-hardened
   edge build; v3 comparators predate it) to **all** Part A comparisons; the
   cross-era label applies to **all** Part A comparisons (Q-A1 included),
   not only the storage pair; state the 256/512 cap split per replicate
   where a pool spans caps (plan §4.6).
6. **`nn_db_3` handling.** Degraded run (p95 49.06 s; ≈19 % non-completed vs
   ≈0.1–1.6 % peers; I1 still passed). Keep-with-documentation; its
   inclusion shifts the exact Q-A1 ratio (**0.680** incl / ≈0.74 excl) —
   decide and document in the battery.
7. **Wording.** The zero-add controls are the **extension-era** `nn_cb`
   runs (testing a v3-era claim) — "within-era" is misleading.

**Nothing in this note is frozen.** The final battery supersedes it and
writes the frozen numbers; until then the extension numbers are provisional.

## Part C — Record (rq2pc)

**Pre-registration:** [partc_addendum.md](partc_addendum.md) (frozen by
FREEZE-3, `50b694c`; hash record [run_matrix.md](run_matrix.md) §6).
**Part C is CLOSED — the campaign was NOT executed** (user decision
"stop + record", 2026-09-28). Probes are not evidence: the ladder and the
diagnostic pair below close the probe question (is there a rate regime
where compute adds demonstrably relieve the compute-bound meltdown?).
Full execution log: [partc_probe_log.txt](partc_probe_log.txt).

### Measurements — probe ladder (P-0 → P-4, 2026-09-28)

5 probe runs total (≤ 7-run cap; the 2-run diagnostic pair as the
user-approved extension; no relaunches). Blended `compute_bound_episode`
numbers (per-client CSVs; lower-median p50):

| Probe | Label (run folder) | Config | completed · timeouts · canceled · slow-share · p50 | Verdict |
| --- | --- | --- | --- | --- |
| P-0 | `rq2pc_p0_nn_015` (`20260928_111224…`) | `nn` · rate 1.5 | 43 131 · 2 · 0 · 0.999 % · 3.3 ms | **NO LOCK** — ascending |
| P-1 | `rq2pc_p1_nn_030` (`20260928_114122…`) | `nn` · rate 3.0 | 61 957 · 24 017 · 132 · 99.0 % · 3.42 s | **LOCK** ⇒ **R\* = 3.0** (P-2/P-3 skipped) |
| P-4 | `rq2pc_p4_cf_030` (`20260928_121013…`) | `cf` · rate 3.0 | 62 426 · 22 445 · 1 233 · 97.7 % · 3.23 s | lock re-check PASS; **signature FAIL** |

P-4 signature pass (window defs, addendum §7: PRE = episode start → first
compute `node_add`; POST = first compute `node_ready` + 120 s → episode
end): **4 compute adds fired per LAN** (budget cap), nodes admitted and
served — yet PRE→POST p50 ratio **0.86** (lan1) / **0.81** (lan2) — **no
collapse (slightly worse)**; POST slow-share **99.2 / 96.7 %**; blended
completions ≈ the `nn` lock run (62 426 vs 61 957). **At 3.0 the meltdown
is not capacity-bound: added servers do not relieve it.**

### Measurements — diagnostic pair @ 2.5 (user-approved bounded extension)

| Run | Label (run folder) | completed · timeouts · canceled · slow-share · p50 | Verdict |
| --- | --- | --- | --- |
| 1/2 | `rq2pc_pd_nn_025` (`20260928_134455…`) | 63 188 · 8 405 · 217 · 97.0 % · 2.79 s | **LOCK** (reference) |
| 2/2 | `rq2pc_pd_cf_025` (`20260928_141410…`) | 60 773 · 10 077 · 955 · 74.3 % · 2.07 s (lan2: 57.9 % · 1.13 s) | treatment signal — **unstable** |

`cf`@2.5 window + per-minute observations (client CSVs + `per_node_stats.csv`):

- **lan2 collapse is real:** PRE p50 ≈ 1.87 s → POST ≈ 0.087 s (≈ **×21.4**);
  minutes 3–5 run at 3–4 ms with 0–71 timeouts/min.
- **Neither lane sustains it:** lan2 **relapses from minute 6** (p50 back
  to 2.3–3.9 s; 1.1–1.4 k timeouts/min in minutes 6 / 8 / 9); **lan1 never
  collapses** (PRE→POST ratio 0.76; p50 ≥ 1.8 s in every minute) and its
  worst minutes (6 / 8 / 9; 1.5–1.7 k timeouts, p50 5.0–9.1 s) follow the
  mid-episode teardown below.
- **Per-minute concentration:** in the healthy minutes each lane's
  ≈ 3.0–3.7 k req/min (the full demand) land on **one compute node at a
  time**, rotating across the fixed server and the added nodes (e.g., lan1:
  main → dyn2 → dyn3 → dyn4 → main → dyn5); lan2's ms-scale minutes are the
  only minutes where **two added nodes share** the lane's load. `nn`@2.5
  reference: steady 2.4–3.8 s p50 every minute, both lanes.
- **Mid-episode teardown (lan1):** the `controller_lan1.log` node-registry
  liveness cull (`[registry] mac=… not seen for N s — triggering removal`,
  N = 238–440 s) fired 14:22:48 for macs …01:06 (storage) / …01:07 / …01:08
  / …01:09 and 14:24:48 for …01:0a; removals executed 14:23:31–14:24:50 —
  **inside the episode**. The "seen" timestamps do not track served traffic
  (…01:07 served 3 201 requests in its first minute yet its last "seen" ≈
  its admission instant). lan2's cull batch fired only at 14:26:48+ (≈ 1 min
  after episode end). The same cull pattern appears post-episode in
  `nn`@2.5 (storage node, 13:57:30) and in P-4@3.0 (batches 12:14:52 /
  12:19:52 / 12:21:52) — **systematic platform behavior, not a one-off.**

### Judgment

1. **Probe question answered (ladder):** no clean treatable window exists
   in the tested range **1.5 → 3.0** at the Series-C allocation. 1.5 =
   cruise (no lock); **3.0 = locked but not capacity-bound** (P-4: adds
   with zero benefit — the constraint is elsewhere); 2.5 = treatable *in
   principle* (lan2 ×21.4) but the effect is **assignment-dependent and
   unstable** (lane asymmetry, minute-6 relapse, mid-episode cull
   contamination).
2. **First confirmed mechanism — node-registry liveness cull (systematic;
   all probe runs).** Added nodes are torn down `N` s after their last
   "seen" event (N ≈ 209–690 s observed), and "seen" does not renew on
   served traffic. Consequence: a treatment's added capacity can be
   dismantled mid-measurement by the platform (lan1 minutes 8–9), and
   POST-window audits must treat registry culls as a teardown source, not a
   policy action. Feeds the open **M1/teardown consolidation** item.
3. **Second confirmed mechanism — near-capacity assignment concentration.**
   At 2.5 the lane demand ≈ one node's capacity and per-minute load sits on
   a single node; relief appears only when the assignment splits load across
   two added nodes. This makes the "≥ 2× collapse on both LANs" acceptance a
   function of the routing regime, not of the add count — exactly what the
   diagnostic showed (one lane ×21.4, the other ×0.76 on the same arm, same
   adds).
4. **Campaign decision ("stop + record", user 2026-09-28).** The 24-run
   campaign is **not executed**: at 3.0 the treatment cannot express, at 2.5
   its expression is (a) a routing lottery and (b) intersected by the
   liveness cull — a 24-run dataset would be dominated by these two
   platform behaviors rather than by the treatment. **Part C contributes no
   evidence runs** (probes are not evidence); its output is this diagnostic
   record + the two mechanisms above.
5. **Open platform questions (registered, not probed):** (i) node-registry
   liveness semantics — what refreshes "seen", and why added nodes expire
   mid-load; (ii) compute assignment/concentration at near-capacity rates —
   what drives which node receives each minute's load. Any future
   compute-bound campaign should start from these.

**Closure state:** `phases_rq2pc_cb.json` restored to the frozen state
(`d40f5f59…`; transient in-place rate edits 1.5→3.0→2.5 documented in
[partc_probe_log.txt](partc_probe_log.txt)); closure commit `7817edf`
(records-only on `rq2-extension`) — **no `-final-` tag** (the planned tag
implied campaign readiness that the stop decision obviates).

## Changelog

| Date | Change | Rationale |
| --- | --- | --- |
| 2026-09-26 | Stub created with the plan package | Pre-registration record; no results exist |
| 2026-09-26 | Reviewer resolution pass applied to the package (34 items; C1–C3/W1–W25/O1–O6) — probe template aligned to run_matrix P1-1..P1-4; approval record + freeze-artifact sections added | Review gate (pre-approval) |
| 2026-09-26 | Second review-resolution pass applied to the package (CR1, W1′–W11′, O1–O9) — probe template updated (P1-4 definition, plan-defined thresholds, 6-item carried-state) | Review gate (pre-approval) |
| 2026-09-26 | Final corrections pass applied to the package (threshold list completed; no env archive mirror; FREEZE-2 re-hash rule; `demand_drop` = 420 s) — results content unaffected (no runs) | Pre-approval corrections |
| 2026-09-26 | Plan approved; approval record + execution timeline added (step 1 done; step 2 in progress) | Execution record |
| 2026-09-26 | Step 2 executed on the VM; draft tag `rq2-extension-draft-20260926`; smoke findings (reserve-activation anchor; decision-log M1 criterion) applied before the commit | Execution record |
| 2026-09-26 | Step 3 verification record added to run_matrix §1 (restricted-diff adjudge + draft-state md5s + tag anchors) | Execution record |
| 2026-09-26 | FREEZE-1 record added (§1): pre-probe hashes + plan-package hashes; FREEZE-2 slots remain open | Execution record |
| 2026-09-26 | Probe record started: P1-1 result recorded (FAIL on b); r6→r9 in-place rate edit applied (uncommitted until probe finalization) | Probe execution |
| 2026-09-26 | P1-2 result recorded (FAIL on b; rate 9→12 in-place); probe budget used: 2 / ≤4 | Probe execution |
| 2026-09-26 | P1-3 result recorded (FAIL on b; service-capacity wall documented; rate 12→15 + R1 duration 600→1200 s in-place); P1-4 contingency launched; budget used: 3 / ≤4 | Probe execution |
| 2026-09-26 | P1-4 result recorded (FAIL on b at rate 15 / 1200 s); **Alpha declared INFEASIBLE → Beta switch** (plan §5.3/§5.4); Beta probe plan drafted (B-P1/B-P2, ≤2 + 1) — pending sign-off | Probe execution |
| 2026-09-26 | Beta switch approved (user); B-P1 launched; probe-evidence cleanup authorized (slim archive + delete at sweep close; recorded exception) | Probe execution |
| 2026-09-27 | B-P1 recorded PASS (pooled convention ratified + both readings noted); B-P1b (`rq2_ext_b_r16`) launched; conditional B-P1 rerun authorized | Probe execution |
| 2026-09-27 | B-P1b recorded (no improvement; service degraded at r16); B-P1r (`rq2_ext_b_r15_rep`) launched (conditional reproducibility check) | Probe execution |
| 2026-09-27 | B-P1r recorded (R1 reproduced; episode metrics match; (b) 29.4 % vs 31.1 % — two-run pooled 30.25 %); B-P1 edge-fd incident forensics recorded (R2 lan1 blackout; not reproduced in B-P1r) | Probe execution |
| 2026-09-27 | User ratified items 1–3: Beta bind accepted (two-run pooled 30.25 %); fd-scan incident handling accepted (plan §5.10 D4 + lessons entry); B-P2 approved | User decision |
| 2026-09-27 | B-P2 recorded (R2 ✓: activation + **G = 120 s**; R1 fd meltdown — partial); two-episode audit recorded (contingency R2 meltdown correction; battery now both-episodes); fd incidence 3/8 — decision gates the campaign | Probe execution |
| 2026-09-27 | Platform fixes applied (`--ulimit nofile=65536` on edge containers; log-rotation fix synced — `build_network_{1,2}.sh`, md5 `da479154` / `6bb54940`); verification rerun `rq2_ext_b_dbcb_rep` launched | User decision (items 1–3) |
| 2026-09-27 | B-P2r recorded: fd fix verified (0 EMFILE); **R1 MEMCG OOM incident** (thread explosion; both edges restarted; no recovery); P2 re-confirmed (G = 120 s); **dbcb R1 2/2 failed** — root-cause decision re-opened | Probe execution |
| 2026-09-27 | Edge-server concurrency bound implemented (root-cause fix — unbounded thread-per-connection → gated accept); image rebuilt + smoked (dependency parity via layer cache); verification run `rq2_ext_b_dbcb_fix1` launched | User decision (root-cause path) |
| 2026-09-28 | Campaign executed + verified (Stage A1 + Stage 2, 30/30); Stage-2 verification + open instrumentation items + closure sweep recorded | Execution record |
| 2026-09-28 | Part C addendum + artifacts drafted (`rq2pc` pre-registration) — awaiting review + FREEZE-3 | Part C pre-registration |
| 2026-09-28 | Part C review gate passed + FREEZE-3 draft committed (`50b694c`); hash record + statuses updated | Execution record |
| 2026-09-28 | Part C probe ladder executed (P-0 no lock; P-1 lock @ 3.0 → R* = 3.0; P-4 `cf`@3.0 lock PASS, signature FAIL — zero benefit); bounded diagnostic pair @ 2.5 executed (`nn` LOCK; `cf`: lan2 ×21.4, lan1 ×0.76, lan2 relapse min 6, lan1 mid-episode registry cull) | Probe execution |
| 2026-09-28 | **Part C CLOSED — "stop + record" (user decision):** campaign NOT executed (no clean treatable window 1.5–3.0; cull + assignment concentration dominate); Part C record + findings appended; `phases_rq2pc_cb.json` restored to the frozen state; closure records committed (records-only; no `-final-` tag) | User decision (post-diagnostic) |
| 2026-09-28 | Part A/B pre-battery verification note appended — recomputed values (Q-A1 0.680 / Q-A2 0.487), convention bands, cross-checks (v3 summaries reproduced exactly), pin list (ratio conventions, ≈3×, L4 counts, build-delta/cap labels, `nn_db_3`) | Verification pass (read-only; ahead of the final battery) |
