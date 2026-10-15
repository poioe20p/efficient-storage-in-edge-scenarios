# Results — RQ3 Admission Modes (Readiness-Admission Completion Campaign)

**Date**: 2026-10-13 · **Plan**: [experiment_plan.md](experiment_plan.md) · **Matrix**: [run_matrix.md](run_matrix.md) · **Run log**: [campaign_log.md](campaign_log.md) · **Host**: `cloud-vm-rq3` · **Executed**: 38 runs, 2026-10-11 → 2026-10-13

Analysis-only record (no runs, no configuration changes). Screen inputs (final archived, `analysis/`): `completion_intact.json`, `completion_lost.json` (2026-10-12 02:47Z), `completion_premature_full.json` (2026-10-13 02:28Z), `completion_support.json` (2026-10-13 04:56Z); provenance `platform_identity.json`, `platform_identity_provision_check.json`, `canonical_hashes.json`, `family_profile_restore.json`. Every number below is quoted from these records; screen fractions are re-expressed in pp/% at 2 dp.

## 1. Scope & provenance

| Item | Record |
|---|---|
| Campaign | RQ3 Admission Modes — readiness-admission completion (Family 6, 7-block standardisation) |
| Dates | 2026-10-11 18:10:54Z (C1 first launch) → 2026-10-13 04:44:06Z (C3 end); family-profile restore 04:46:44Z; support screen 04:56Z |
| Host | `cloud-vm-rq3` |
| Timing execution tree | `~/rq3tim_frozen` @ `852a8a3` (tag `rq3tim-preflight-20260908`) — C1 + replacement re-runs |
| Soundness execution tree | `~/rq3snd_frozen2` @ `541fb22` (tag `rq3snd-preflight-20261003`) — C2 |
| Support/C3 execution tree | `~/efficient-storage-in-edge-scenarios` (campaign tree; the C3 launcher derives `REPO_ROOT` from its own location) |
| Operator tree | informational only (`platform_identity.json` item `operator_tree`, `required=false`; never causes DRIFT) |
| P0 gates | `c1_c2_gate` = MATCH (2026-10-11); `c3_gate` = UNDEFINED in that record (support-set snapshots not yet recorded — blocks C3 only) → resolved MATCH by `platform_identity_provision_check.json` (2026-10-12 08:01Z) |
| Waiver | timing image item **WAIVED** (non-blocking; timing-reference identity = recorded commit/worktree + admission-path hashes) |
| Canonical config (unmodified) | `phases.json` sha256 `57bccc12bebb98dfeb920c417d343e734763cd9a747f917b8177ee04977c7aa2`; `current_state_integrated.env` sha256 `000d6a3641bcc260c596ddb9c946e2344476c90731efbc8d547f1854b09634cf` (`canonical_hashes.json`) |
| Runs | C1 6 + 3 replacement re-runs (3 quarantined `*_void`) = 9; C2 24 (12 faulted + 12 matched partners); C3 5 — **38 executed** |
| Analysis inputs | 21 intact (`rq3tim_none_*`); 21 lost (`rq3tim_loss_all_*` + the same 21 no-fault runs for E-L4); 21 premature + 21 no-fault partners; 5 support replicates |

### Amendments chronology (plan §14 rows (b)–(l))

| Row | Date | Change |
|---|---|---|
| (b) | 2026-10-11 | seven-seed standardisation: +12 matched no-fault partners (35 new runs total); E-P4 retired |
| (c) | 2026-10-11 | review-round implementation fixes (frozen-tree label-check enforcement; analyzer exit codes; E-I4/E-L4 qualification reading 16/18) |
| (d) | 2026-10-11 | second review round (timing-image item → WAIVED; rule-axis re-derivation; duplicate-folder refusal) |
| (e) | 2026-10-11 | P0 scoping fix: the comparison is per group against that group's execution tree; the operator tree is informational |
| (f) | 2026-10-11 | third review round: C3 becomes an explicit execution group; P0 support-set resolution |
| (g) | 2026-10-11 | fourth review round: stage-scoped P0 verdict (`c1_c2_gate` / `c3_gate`) |
| (h) | 2026-10-12 | C1 stage-screen amendment: E-I1 re-scoped to spawn → first-success; ready→admission unmeasurable (note only); 3 block-7 runs quarantined `*_void` and replaced under their planned `_7` labels |
| (i) | 2026-10-12 | C3 prerequisite resolved: cell12 archived profile provisioned (`37bc546d…`); `c3_gate` MATCH |
| (j) | 2026-10-13 | C2 stage-screen fix: log-based E-P1 gates **not evaluable** when `controller_lan{1,2}.log` is absent (recorded era) — reported, never passed or failed |
| (k) | 2026-10-13 | `restore-family` made tree-agnostic (hash-verified byte copy instead of `git checkout`) |
| (l) | 2026-10-13 | C3 supporting-screen leg re-scope: E-S1 gate on spawn → first-success; E-S3 band check not assessable when its leg is degenerate |

## 2. Per-condition results

### 2.1 Intact — 7 blocks, 21 runs

**E-I1 — admission-chain contrast (gated; leg re-scoped per (h)).** Leg: spawn → first successful response, pooled per start-up class.

| Stratum | n A/B/C | median A | median B | median C | C − max(A,B) | MWU p A–C / B–C | Cliff's δ A–C / B–C |
|---|---|---|---|---|---|---|---|
| fast | 12 / 12 / 14 | 4.08 s | 3.08 s | 9.98 s | 5.90 s | 1.92e-4 / 1.75e-5 | −0.869 / −1.000 |
| slow | 22 / 22 / 19 | 13.69 s | 13.67 s | 19.78 s | 6.09 s | 5.01e-8 / 5.01e-8 | −1.000 / −1.000 |
| all (descriptive) | 34 / 34 / 33 | 13.19 s | 13.15 s | 15.50 s | 2.31 s | 0.0013 / 0.0006 | −0.458 / −0.488 |

Direction/band flags: `a_median_lt_c` true, `b_median_lt_c` true, `c_later_by_one_period` true (C later by ≤ one 10 s poll period in each gated stratum); primary strata 2/2 ok (secondary 2/2); B admit-source `event` fraction 1.0 (≥80 % check true); assessable blocks 1–7; **pass true**.
Recorded anchors on this leg: 11.27 s vs 17.70 s (exact MWU p = 0.0005); C1 stage screen read 13.19 / 13.15 / 15.36 s. Context legs: spawn → first routed 74.58 / 73.97 / 81.13 s; the earlier regime note d = −0.837 belongs to the adjacent admit → first-routed interval.
Ready→admit note: `app_ready_ts → admitted_ts` reads 0.000 s median for all three arms (status: unmeasurable in this build — instrument degeneracy; the service-log trace shows C's ≈2.9 s quantization) — note only, never gating.
Source: `completion_intact.json` `E-I1.leg`, `E-I1.strata.{fast,slow,all}`, `E-I1.level_flags`, `E-I1.primary_strata_ok`, `E-I1.b_event_fraction_ge_80pct`, `E-I1.assessable_blocks`, `E-I1.pass`, `E-I1.anchors`, `E-I1.ready_to_admit_leg`.

**E-I2 — handover quality (descriptive, no gate).** Admitted → first routed medians 0.774 / 0.703 / 0.662 s (A/B/C); initial-mix share 0.966 / 0.969 / 0.970; zero unattributed `000` in every arm. Descriptive finding recorded: initial-mix share below the recorded 1.000 anchor (reported, never chased).
Source: `completion_intact.json` `E-I2.modes.*`, `descriptive_findings`.

**E-I3 — redistribution onset (descriptive).** Spawn → first-routed medians A 74.58 / B 73.97 / C 78.36 s; redistributed share 0.6886 / 0.6864 / 0.6732 (n backends 34 / 34 / 33) — relief no-separation restated as recorded; descriptive only.
Source: `completion_intact.json` `E-I3.modes.*`, `E-I3.note`.

**E-I4 — health floor (gated conformance).** 19/21 intact runs clean under the recorded all-or-nothing floor (bad ≤1 % full plateau ∧ plateau tail slow ≤2 pp). The two non-clean runs are the recorded transients: block 3 hybrid bad 1.19 % (>1 %); block 5 reconcile tail 4.29 % (>2 pp). Recorded qualification restated: 16/18 recorded runs clean → `none_cell_healthy` = false; transient blocks [3, 5] stay recorded (never re-chased); block 7 clean; conforms = true; NA = false.
Source: `completion_intact.json` `E-I4.clean/denominator/provided`, `E-I4.recorded_floor`, `E-I4.recorded_qualification`, `E-I4.none_cell_healthy`.

### 2.2 Lost — 7 blocks, 21 `loss_all` + 21 no-fault runs

Pre-registered assessability: floors + driver-clean + controls (B ∧ C) plateau-tail ≤2 pp + Δ computable; block 4 (seed 5204) stays excluded as recorded; the added block 7 is assessed per block under the control-tail rule.

**E-L1 — headline (gated).** Δ_slow = slow(A) − max(slow(B), slow(C)):

| Block | seed | Δ slow (pp) | onset Δ (pp) | assessable | control tails B/C (%) | exclusion |
|---|---|---|---|---|---|---|
| 1 | 5201 | 7.00 | 28.01 | yes | 0.97 / 1.23 | — |
| 2 | 5202 | 10.87 | 25.17 | yes | 0.94 / 0.89 | — |
| 3 | 5203 | 6.21 | 25.11 | yes | 1.18 / 1.39 | — |
| 4 | 5204 | 4.97 | 25.95 | no | 1.23 / 4.08 | recorded exclusion (`recorded_exclusion_seed_5204`) |
| 5 | 5205 | 7.64 | 30.84 | yes | 1.24 / 1.16 | — |
| 6 | 5206 | 9.99 | 29.10 | yes | 1.41 / 1.23 | — |
| 7 | 5207 | 1.24 | 6.50 | no | 0.81 / 2.02 | report-only (`controls_tail_slow_gt_2pp`) |

Accept counts: 5/6 assessable blocks ≥5 pp (denominator [1–6]); **median 7.64 pp**; onset 5/6, **median 28.01 pp**; exact one-sample MWU p = 0.00397; Cliff's δ = 1.0; **pass true**.
Source: `completion_lost.json` `E-L1.*`, `block_rows.*.delta_slow/onset_delta_slow/control_tails/exclusion`.

**E-L2 — mechanism and relief (gated).** A: zero admissions / ≥2 abandoned candidates per LAN, zero new-backend successes — 5/5 assessable blocks; B: every admission via `probe_fallback`, ≥1 per LAN — 5/5; C: every admission via `probe`, ≥1 per LAN — 5/5; relief completion (B ∧ C tail ≤2 pp) — 5/5 (blocks 1, 2, 3, 5, 6); **pass true**; block 7 null for this component.
Source: `completion_lost.json` `E-L2.a_blocks/b_blocks/c_blocks/relief_blocks/per_block`.

**E-L3 — boundedness (gated).** event_only slow median **10.60 %** (values 10.60 / 14.39 / 8.34 / 10.10 / 13.66 % over the five assessable blocks); ≤25 % in 5/5; block-7 reading 3.03 % is report-only (outside the gated count); **pass true**.
Source: `completion_lost.json` `E-L3.event_only_slow`, `E-L3.median`, `E-L3.blocks_le_25pct`, `E-L3.block7`.

**E-L4 — health floor (gated conformance).** The intact runs under the same recorded run-level gate: 19/21 clean; recorded outcome reproduced (16/18; transients blocks 3 and 5); block 7 clean; conforms = true.
Source: `completion_lost.json` `E-L4.*`.

**Block-7 lost-pair qualifier.** The added block-7 pair does not count: reconcile control tail **2.015 %** > 2 pp → block unassessable; the recorded numbers (Δ 1.24 pp, onset 6.50 pp) are carried as report-only, not assessed.
Source: `completion_lost.json` `block_rows.7.control_tails.reconcile`, `block_rows.7.exclusion`, `E-L1.block7`.

### 2.3 Premature — 7 blocks, 21 faulted (10 s lead) + 21 matched no-fault runs

**E-P1 — mechanism attestation (gated).** Cells are assessable on ≥5/7 passing blocks:

| Cell | assessable blocks | passing | new runs passing | recorded blocks passing |
|---|---|---|---|---|
| A `event_only` | 7 | **7/7** | 4/4 | 3/3 |
| B `hybrid` | 7 | **7/7** | 4/4 | 3/3 |
| C `reconcile` | 6 | **6/7** | 4/4 | 2/3 |

All 12 new runs pass every gate (measured claim→bind deferral ∈ [9, 11] s, `EDGE_READY_PREMATURE_S=10` attestation, recorded bands, signature/immunity checks); **pass true**.
Recorded-era note ((j)): the 9 recorded runs (blocks 1–3) carry no `controller_lan{1,2}.log`, so their log-based gate (`check_violation_ge_1` for A/B, `zero_check_violations` for C) is **not evaluable** — listed in `not_evaluable_runs`, never passed or failed. One recorded run fails a non-log gate: `20261004_032511_rq3snd_premature10_reconcile_2` (b2) `zero_pre_bind_successes` = false — stays a reported failure (hence reconcile 6/7).
Source: `completion_premature_full.json` `E-P1.cells.*`, `E-P1.new_run_checks`, `E-P1.not_evaluable_runs`, `E-P1.recorded_run_checks`, `E-P1.pass`, `recorded_bands`.

**E-P2 — rule separation (gated, all 7 blocks).** A − C: **median 16.98 pp**, δ = 1.0, exact p = 0.000291, 7/7 blocks positive; B − C: **median 16.18 pp**, δ = 1.0, p = 0.000291, 7/7 positive. Per-block Δ_s (pp) — A−C: 13.52, 16.46, 6.35, 24.56, 17.98, 22.24, 16.98; B−C: 16.18, 16.71, 10.07, 14.86, 18.95, 14.27, 19.48. Both contrasts **pass true**.
Source: `completion_premature_full.json` `E-P2."A vs C".*`, `E-P2."B vs C".*`.

**E-P3 — absolute damage vs matched no-fault (gated, seven seed-matched pairs).**

| Rule | usable pairs | median D_s | positive pairs | pairs ≤2 pp | Cliff's δ | MWU p | dropped |
|---|---|---|---|---|---|---|---|
| A `event_only` | 6 | **+14.38 pp** | 6/6 | 0 | 1.000 | 0.00108 | 1 (b5) |
| B `hybrid` | 7 | **+11.66 pp** | 6/7 | 2 | 0.714 | 0.1512 | 0 |
| C `reconcile` | 7 | **−0.05 pp** | 3/7 | **7/7** | −0.143 | 0.8103 | 0 |

All three rules **pass true**. Dropped pair: b5 A — partner `20261012_153513_rq3snd_none_event_only_5` breached the no-fault floors (plateau tail-slow 8.93 %, bad 0.51 %) → per the recorded soundness §4.5 rule; one dropped seed < 2, so every rule stays assessable.

Pairs table (D_s in pp; U_cell / U_none in %):

| Block | seed | A: D_s / U_cell / U_none | B: D_s / U_cell / U_none | C: D_s / U_cell / U_none |
|---|---|---|---|---|
| 1 | 6301 | +5.74 / 16.20 / 10.47 | +13.33 / 18.87 / 5.53 | +0.12 / 2.69 / 2.57 |
| 2 | 6302 | +16.18 / 18.99 / 2.81 | +3.86 / 19.25 / 15.38 | −0.99 / 2.53 / 3.52 |
| 3 | 6303 | +12.57 / 15.07 / 2.50 | +16.41 / 18.79 / 2.38 | −4.68 / 8.72 / 13.40 |
| 4 | 6304 | +21.98 / 27.65 / 5.67 | +0.55 / 17.95 / 17.40 | +0.40 / 3.09 / 2.69 |
| 5 | 6305 | dropped (partner tail-slow 8.93 %) | −2.88 / 21.13 / 24.01 | −1.14 / 2.18 / 3.32 |
| 6 | 6306 | +22.53 / 25.59 / 3.06 | +14.55 / 17.62 / 3.07 | +0.45 / 3.35 / 2.91 |
| 7 | 6307 | +9.15 / 19.23 / 10.07 | +11.66 / 21.72 / 10.07 | −0.05 / 2.24 / 2.29 |

Component set: 21 faulted + 21 partners = 42 runs; `failures` = []; **pass true**.
Source: `completion_premature_full.json` `E-P3.rules.{event_only,hybrid,reconcile}.*` (incl. `pairs[]` `d_s/u_cell/u_none`, `none_breach_reason`), top-level `premature_runs`/`none_partners`/`runs`.

### 2.4 Supporting — 5 runs

**E-S1 — per-backend campaign (gated; leg re-scoped per (l)).** Leg: spawn → first successful response; direction direct before discovery in every backend (4/4): direct 1.888 / 1.970 / 2.539 / 1.598 s (median **1.93 s**) vs discovery 8.894 / 8.655 / 3.529 / 3.663 s (median **6.16 s**); direct event-sourced, discovery probe-sourced; initial-mix share 1.0 both arms, 0 `000`; handover against the set anchors (`useful_share` 1.0, 0× http=000 fast-fails); **pass true**.
Ready→admit degeneracy note: reads 0.000 s for every backend of both camp runs; the registered band readings are reported inside the note and never gate. Set anchors (not recomputable from one replicate): 1.93 vs 6.16 s, δ = −1.0; ready→admit 0.001 vs 6.984 s (set-level, 12 runs / 47 backends).
Source: `completion_support.json` `E-S1.*`, `anchors.camp`.

**E-S2 — higher-rate arm (gated).** Scale decision → usable capacity: direct **1.8729 s** vs discovery **8.9842 s**, direction 4/4, driver-clean, floors ok, gap-window null 0 bad, window 4096 (attested `4096 clients=3 edge_cpus=0.30 mongo_pool=1`); **pass true**. Set anchors: 2.17 vs 6.01 s (n = 6/arm, exact p = 0.0022, δ = −1.0, gap null 6×6 all-zero).
Source: `completion_support.json` `E-S2.*`, `anchors.cell12`.

**E-S3 — poll-interval sensitivity (descriptive).** The registered ready→admit leg reads 0.000 s for every backend (instrument degeneracy) → band check **not assessable**, reported as a note (quantization checks null; median 0.0 s); floors ok, driver-clean. Set precedent: 10 s arm 9.6 s → 15 s arm 15.2 s per position (disc15 anchor poll 15.0 s).
Source: `completion_support.json` `E-S3.*`, `anchors.disc15`, `descriptive_findings`.

Per-set runs (regimes: quota 0.30, clients 3, `EDGE_CPUS` 0.30, `mongo_pool` 1):

| Set run | Folder | base seed | window | cancel rate | completed baseline / compute_spike | backends |
|---|---|---|---|---|---|---|
| camp direct | `20261013_033743_rq3_camp_direct_7` | 2322 | 1024 | 0.71 % | 117 / 3214 | 4 |
| camp discovery | `20261013_035209_rq3_camp_disc_7` | 2323 | 1024 | 1.05 % | 116 / 3207 | 4 |
| cell12 direct | `20261013_040546_rq3_probe_cell12_direct_6` | 2226 | 4096 | 0.51 % | 117 / 12772 | 4 |
| cell12 discovery | `20261013_042031_rq3_probe_cell12_disc_6` | 2227 | 4096 | 0.59 % | 119 / 12745 | 4 |
| disc15 discovery | `20261013_043402_rq3_disc15_7` | 2007 | 1024 | 1.16 % | 118 / 3208 | 4 |

Sources: cancel/completed/backends `completion_support.json` `set_runs.*`, `runs` (folder map); seeds/windows/quota from the C3 rows of `campaign_log.md` (per-run `rq3adm_profile_attestation.txt`).

Restored-snapshot hashes: camp runs `702bc05196ae74c4e8ca4efa3ca150dcb3197391e55e1e17eb8a34580fbc4e8d`; cell12 runs `37bc546de326c6ea2e81597db616544e74dae4aa0efe3ec3f68ce096e6b771fa`; disc15 `702bc051…` (per-run `phases_snapshot.json`); family profile re-installed after the batch at `57bccc12bebb98dfeb920c417d343e734763cd9a747f917b8177ee04977c7aa2` (`family_profile_restore.json`).
Source: `campaign_log.md` C3 rows; `family_profile_restore.json` `installed_sha256`.

### 2.5 Wake-and-verify (D) — E-W screen (22 runs; C4)

Sources: `completion_intact_wake.json` (E-W1), `completion_lost_wake.json` (E-W2), `completion_premature_wake.json` (E-W3, E-P1 wake cell, E-P2 extension). Runs: `rq3snd_none_wake_verify_8..14` + `rq3snd_loss_all_wake_verify_8..14` (seeds 5201–5207; the intact runs double as the loss partners), `rq3snd_premature10_wake_verify_1..7` + partners `rq3snd_none_wake_verify_1..7` (seeds 6301–6307; ordinals 1–3 are the recorded pilots, reused). 22/22 runs valid (`campaign_log.md` C4).

**Author ruling applied (2026-10-14):** marginal 2–4 % variation is not by itself a reason to drop runs or pairs; affected pairs are retained and the deviation carried as a note. Applies below to the E-W2 partner tails (2.19 %, 3.64 %) and the E-W3 b1 partner tail (3.95 %). The recorded screens marked those pairs dropped, so their recorded medians and pass flags differ from the readouts here.

**E-W1 — intact direction (gated; recorded screen pass = false).** Fast class: D **4.01 s** (n = 41) vs A 4.08 s (near-tie, +0.07 s) vs C 9.98 s — D earlier than C by **5.97 s**, direction held. Slow class: **no D evidence** — the completion-era runs contain no bind stall at all (0 of 41 backends ≥ 5 s; max 0.089 s across the seven runs), while the A–C slow class comes from the September runs (10.0–10.4 s binds, universal in blocks 1–6). The gate reads "not reproduced in every primary stratum" because the slow stratum has no D backends; the substance holds in the fast class, which is also the era-matched one. No-fault: the pilot's small cost was not reproduced; two partner tails (b2 2.19 %, b5 3.64 %) are the only marginal readings.
Source: `completion_intact_wake.json` `E-W1.*`; bind distribution measured from the run edge logs.

**E-W2 — lost no-harm + mechanism (gated; recorded pass = false / NA; met 7/7 under the ruling).** Paired plateau slow-share delta (loss vs its own none partner), seven blocks: −0.32 / −1.51 / −0.65 / −0.01 / −0.71 / −0.37 / **+1.23** pp (median **−0.4 pp**; all within 2 pp). Mechanism exact: loss admissions all `probe_fallback` (44 rows), intact all `wake_verify_probe` (30 rows); recovery rides the same 20 s absence fallback (recorded hybrid anchor ≈21 s, descriptive). Admitted 6–7 per run, zero abandoned; loss plateau slow 0.7–3.5 %, plateau tail 0.7–3.7 %.
Sources: `completion_lost_wake.json` `E-W2.*`; b2/b5 deltas recomputed (the recorded screen dropped those pairs with `status: partner_breach`).

**E-W3 — premature immunity + paired damage (gated; recorded pass = true).** Paired damage over the seven pairs: −0.87 / −0.31 / −3.36 / −4.77 / **+3.13** / −6.04 / −0.73 pp (median **−0.9**; recorded 6-pair median −2.05) — within 2 pp in **6/7** (exception b5, +3.13 pp, whose partner tail was 3.64 %). Claim → first: 10.56–11.38 s per run, median **10.99 s** vs periodic **19.47 s** (admission at true servability). E-P2 extension: U(A) − U(D) **+16.86 pp**, 7/7 positive, MWU p = 0.00029, δ = 1.0 (gated, pass); U(D) − U(C) **−0.24 pp**, 3/7 positive (descriptive, near-tie). E-P1 wake cell: 5/7 pairs passing; the two not passing carry the recorded two-success pre-bind transient (b1 pilot, b4 new) — reported per run, the cell stays assessable.
Sources: `completion_premature_wake.json` `E-P3.rules.wake_verify`, `E-P1.*`, `E-P2."A vs D (wake vs A damage contrast)"`, `E-P2."D vs C (wake vs periodic, descriptive)"`; b1 pair damage recomputed under the ruling.

## 3. Thesis-facing consolidated tables

### T1 — Intact: the price of checking (working leg: spawn → first successful response, pooled per start-up class)

| Stratum | A `event_only` | B `hybrid` | C `reconcile` | C − max(A,B) | MWU p A–C / B–C | Cliff's δ A–C / B–C | Source |
|---|---|---|---|---|---|---|---|
| fast | 4.08 s (n=12) | 3.08 s (n=12) | 9.98 s (n=14) | 5.90 s | 1.92e-4 / 1.75e-5 | −0.869 / −1.000 | `completion_intact.json` `E-I1.strata.fast.median_event_only/hybrid/reconcile`, `c_delta_over_ab_s`, `primary_a_vs_c`, `secondary_b_vs_c` |
| slow | 13.69 s (n=22) | 13.67 s (n=22) | 19.78 s (n=19) | 6.09 s | 5.01e-8 / 5.01e-8 | −1.000 / −1.000 | `completion_intact.json` `E-I1.strata.slow.*` |
| pooled (descriptive) | 13.19 s (n=34) | 13.15 s (n=34) | 15.50 s (n=33) | 2.31 s | 0.0013 / 0.0006 | −0.458 / −0.488 | `completion_intact.json` `E-I1.strata.all.*` |

Direction/band: `E-I1.level_flags` (all three true; band = C later by ≤ one 10 s poll period). Negative δ = A/B earlier than C.
**E-W1 (D, wake_verify) — completion-era fast class:** D **4.01 s** (n = 41) vs A 4.08 s and C 9.98 s; near-tie with A (+0.07 s), C later than D by **5.97 s**. Slow class: no D evidence (the completion-era runs carry no bind stall; the A–C slow class is the September family). Recorded screen pass = false (slow stratum empty) — the substance holds in the fast class. Source: `completion_intact_wake.json` `E-W1.*`.

### T2 — Lost: separation and boundedness

| Quantity | Value | Source |
|---|---|---|
| Δ_slow median (5/6 assessable blocks; ≥5 pp in 5/6) | **7.64 pp** (δ = 1.0; exact p = 0.00397) | `completion_lost.json` `E-L1.median_pp`, `delta_ge_5pp_blocks`, `cliffs_delta`, `mwu_p` |
| onset Δ median (≥5 pp in 5/6) | **28.01 pp** | `completion_lost.json` `E-L1.onset_median_pp`, `onset_delta_ge_5pp_blocks` |
| event_only boundedness median (≤25 % in 5/5) | **10.60 %** | `completion_lost.json` `E-L3.median`, `blocks_le_25pct` |
| intact health floor (run-level) | 19/21 clean; recorded 16/18 reproduced; `none_cell_healthy` = false | `completion_lost.json` `E-L4.clean`/`denominator`, `recorded_qualification` |
| added block 7 | report-only (control tail 2.015 % > 2 pp) | `completion_lost.json` `block_rows.7.control_tails.reconcile`, `exclusion` |
| D (wake_verify) lost no-harm | **7/7 pairs ≤ 2 pp**, median −0.4 pp; admits 6–7/run, 0 abandoned; mechanism `probe_fallback` 44/44 | `completion_lost_wake.json` `E-W2.*` (b2/b5 partner tails 2.19 %/3.64 % re-included under the 2026-10-14 ruling) |

### T3 — Premature: damage matrix (seven seed-matched pairs)

| Rule | median D_s | positive pairs / usable | pairs ≤2 pp | Source |
|---|---|---|---|---|
| A `event_only` | **+14.38 pp** | 6/6 | 0 | `completion_premature_full.json` `E-P3.rules.event_only.median_d_pp`, `positive_pairs`, `usable_pairs`, `le_2pp_pairs` |
| B `hybrid` | **+11.66 pp** | 6/7 | 2 | `… E-P3.rules.hybrid.*` |
| C `reconcile` | **−0.05 pp** | 3/7 | **7/7** | `… E-P3.rules.reconcile.*` |
| rule separation (same-fault contrast) | A−C **+16.98 pp** (7/7 blocks positive) · B−C **+16.18 pp** (7/7) | — | — | `E-P2."A vs C".median_pp/positive_blocks`, `E-P2."B vs C".*` |
| D `wake_verify` | **−0.9 pp** | 1/7 | **6/7** | `completion_premature_wake.json` `E-P3.rules.wake_verify` (recorded 6-pair median −2.05 pp; b1 partner tail 3.95 % re-included under the ruling) |

E-P2 extension (D): U(A) − U(D) **+16.86 pp**, 7/7 positive, MWU p = 0.00029, δ = 1.0 (gated, pass); U(D) − U(C) **−0.24 pp** (descriptive, near-tie). Claim → first: D **10.99 s** vs C **19.47 s** (admission at true servability). Source: `completion_premature_wake.json` `E-P2.*`, `wake_claim_to_first.json`.

### T4 — Supporting: direction checks (the gated leg is E-S1's per-backend direction; the rest is consistent with the recorded set statistics)

| Check | Added replicate | Recorded set anchor | Source |
|---|---|---|---|
| E-S1 direct vs discovery (spawn → first success) | 1.93 vs 6.16 s; 4/4 backends | 1.93 vs 6.16 s (δ = −1.0; ready→admit 0.001 vs 6.984 s) | `completion_support.json` `E-S1.direct_median_s`, `discovery_median_s`, `ordering_pairs`; `anchors.camp` |
| E-S2 scale → usable | 1.873 vs 8.984 s; 4/4 | 2.17 vs 6.01 s (p = 0.0022; δ = −1.0; gap null 6×6 all-zero) | `completion_support.json` `E-S2.direct_median_s`, `discovery_median_s`, `gap_null_ok`; `anchors.cell12` |
| E-S3 15 s-poll quantisation | not assessable (leg degenerate) | 9.6 → 15.2 s per position | `completion_support.json` `E-S3.*`; `anchors.disc15` |

## 4. Dispositions & qualifiers

1. **Lost block 4 (seed 5204) exclusion** — pre-registered, applies unchanged (reconcile control tail 4.08 %); denominator stays the fixed six-block set, 5 assessable. (`completion_lost.json` `block_rows.4`, `denominator_blocks`.)
2. **Lost block 7 (seed 5207) report-only** — its pair does not count: reconcile control tail 2.015 % > 2 pp; Δ 1.24 pp / onset 6.50 pp carried as reported-only. (`block_rows.7`.)
3. **C1 quarantined `_void` attempts** — 3 runs quarantined and replaced under their planned `_7` labels: `rq3tim_none_reconcile_7` (intact C tail 3.84 %), `rq3tim_loss_all_reconcile_7` (control tail 6.50 %), `rq3tim_loss_all_event_only_7` (muted degradation 2.78 %). `_void` folders are excluded from set selection by the timing label regex and retained as the record of the attempt; one unused `_7b` launch attempt was rejected pre-platform by the launcher (`ERROR: invalid label`, no side effects). (`campaign_log.md` C1 re-runs; `completion_lost.json` note.)
4. **E-P1 recorded-era gates not evaluable** — the 9 recorded runs (blocks 1–3, seeds 6301–6303) predate the `controller_lan{1,2}.log` capture: `check_violation_ge_1` (A/B) and `zero_check_violations` (C) are reported not evaluable (amendment (j)) — never passed, never failed. (`E-P1.not_evaluable_runs`, `not_evaluable_logs_absent`.)
5. **E-P1 recorded b2 reconcile failure** — `zero_pre_bind_successes` = false on `20261004_032511_rq3snd_premature10_reconcile_2` (computed from archived client rows + service-log bind times, not controller logs): stays a reported failure; the reconcile cell reads 6/7 (still assessable). (`E-P1.recorded_run_checks.b2_reconcile`.)
6. **Degenerate ready→admit instrument ((h)/(l))** — reads 0.000 s in the intact set and in both C3 arms; reported as a note, never gating; E-S3's band check is consequently not assessable (descriptive only). (`E-I1.ready_to_admit_leg`, `E-S1.ready_to_admit_leg`, `E-S3.*`.)
7. **E-P3 dropped pair** — b5 A (event_only) dropped: the no-fault partner breached the recorded floors (plateau tail-slow 8.93 %, bad 0.51 %); one dropped seed < 2, so all three rules remain assessable. (`E-P3.rules.event_only.pairs[4].none_breach_reason`.)
8. **E-I2 descriptive finding** — initial-mix share below the recorded 1.000 anchor (0.966 / 0.969 / 0.970); reported, never chased (plan §7.1). (`completion_intact.json` `descriptive_findings`.)
9. **E-I4/E-L4 recorded qualification** — the recorded H-T3 outcome is restated exactly as recorded (16/18 clean, `none_cell_healthy` = false; blocks 3 and 5 transients never re-chased); the 21-run denominator adds 19/21 clean; conformance = reproduced + block-7 clean. (`E-I4`, `E-L4.recorded_qualification`.)
10. **`restore-family` incident (C3 batch end)** — the campaign tree's `git checkout` implementation failed and reverted the working-tree profile; recovered by verified byte copy (`57bccc12…`), assertion re-run PASS; the launcher was not modified in-stage and is flagged for review (amendment (k)). (`family_profile_restore.json`; `campaign_log.md` C3 incident.)
11. **P0 provenance qualifiers** — the 2026-10-11 identity record carries `c3_gate` UNDEFINED (support-set snapshots not yet recorded) blocking only C3; resolved MATCH on 2026-10-12. The timing image item is WAIVED, non-blocking. (`platform_identity.json`, `platform_identity_provision_check.json`.)
12. **No outstanding NA/failed components** — `na` = false with empty `na_components` (intact, lost); `failures` = [] (premature: 21 faulted + 21 partners = 42 runs; support: 5 runs). Nothing else is outstanding; the only remaining item of note is the descriptive E-S3 degeneracy note (item 6).

## 5. Component verdicts (final screens)

| Component | Gate | Verdict | Readout |
|---|---|---|---|
| E-I1 (intact A/B vs C, spawn → first-success) | gated | **met** | direction + band hold in both primary strata; 2/2 strata ok; pass true |
| E-I2 (handover quality) | descriptive | n/a (reported) | mix-share finding recorded |
| E-I3 (redistribution onset / relief) | descriptive | n/a (reported) | no separation, as expected |
| E-I4 (intact health-floor conformance) | gated | **met** | recorded outcome reproduced; 19/21 clean; block 7 clean |
| E-L1 (lost headline Δ_slow) | gated | **met** | median 7.64 pp / onset 28.01 pp; 5/6 blocks; δ = 1.0; p = 0.00397 |
| E-L2 (lost mechanism + relief) | gated | **met** | A 5/5, B 5/5, C 5/5, relief 5/5 |
| E-L3 (lost boundedness) | gated | **met** | median 10.60 %; 5/5 ≤ 25 % |
| E-L4 (lost health-floor conformance) | gated | **met** | recorded outcome reproduced; block 7 clean |
| E-P1 (premature attestation) | gated | **met** | cells 7/7, 7/7, 6/7 (≥5/7 each); 12/12 new runs pass; 9 recorded-gate exceptions reported |
| E-P2 (premature rule separation) | gated | **met** ×2 | A−C 16.98 pp 7/7; B−C 16.18 pp 7/7; δ = 1.0 both |
| E-P3 (absolute damage, paired) | gated ×3 | **met** | A 14.38 pp (6/6 positive); B 11.66 pp (6/7); C −0.05 pp (7/7 ≤ 2 pp) |
| E-S1 (supporting per-backend direction) | gated | **met** | 4/4 backends; 1.93 vs 6.16 s; sources correct |
| E-S2 (supporting higher-rate direction) | gated | **met** | 4/4 backends; 1.873 vs 8.984 s; null + floors ok |
| E-S3 (poll-interval sensitivity) | descriptive | n/a (band not assessable) | ready→admit leg degenerate; note recorded |

No component is NA-as-failed; the campaign's pre-registered component set is met as recorded above.
