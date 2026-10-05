# Results — RQ3 Soundness (Readiness-Admission Fault Robustness, soundness half)

**Date**: 2026-10-05 · **Experiment Plan**: [experiment_plan.md](experiment_plan.md) · **Runs**: 60 E-stage runs `rq3snd_{fault}_{arm}_{1..3}` (seeds 6301–6303), 2026-10-03 10:35 → 2026-10-05 04:02 UTC on `cloud-vm-rq3` (`[seq] ALL DONE`); frozen worktree `~/rq3snd_frozen2` (commit `541fb22`, tag `rq3snd-preflight-20261003`, image `edge_server:latest` `207b1f9e8f64`)

**Verdict headline**: H-S1 ✅ · H-S2 ✅ · H-S3 ❌ not met — pre-registered `growth_gate_failure` branch recorded, descriptive band still reported (§4.4 #3) · H-S4 ✅ (secondary, excluded from primary verdicts)

**Evidence**: [`analysis/rq3snd_damage_all.json`](analysis/rq3snd_damage_all.json) (60 runs, 48 contrasts, 0 record errors, 16 median groups) + [`analysis/rq3snd_crossover_all.json`](analysis/rq3snd_crossover_all.json) (§4.4 fits + §6 verdicts), generated 2026-10-05 by `rq3.readiness_robustness soundness-damage | soundness-crossover`. Raw run folders remain on the VM.

## Run Timeline

| Run | Date | Status | Cumulative Analysis | Conclusions | Changes Made | Expectations for This Run |
|-----|------|--------|---------------------|-------------|--------------|--------------------------|
| v1 (E stage, 60 runs) | 2026-10-03/05 | ⚠️ | — (initial) | — (initial) | — (baseline; Family-4 lock regime; fault knobs per plan §7.1) | H-S1 ∧ H-S2 ∧ H-S3 (plan §6); H-S4 secondary |

## Measurements — Campaign

### Validity, floors, mechanism (all 60 runs)

- **60/60 runs valid** — `driver_clean ∧ no_restart ∧ provenance_ok ∧ quota_ok` true in every record; provenance snapshots + fault attestation present in all 60; floors PASS in all 60 (plateau ≥ 5,000 pooled / ≥ 1,000 per LAN; F2 window ≥ 15/LAN).
- 384 bind-verified spawns total; no spawn mismatches; no missing binds; driver cancel rates 0.3–0.6 % (< 5 % floor).
- **F2 false-claim mechanism attested**: nonzero `CHECK VIOLATION` warnings in **18/18** F2 runs (4–6 each); zero in all 12 F3 runs.
- **loss_all (F1) accounting**: `reconcile` admitted **5 / 5 / 5** backends via `probe` (3 seeds); `event_only` admitted **0** with **32–33 spawns abandoned** per run (3 seeds) — the exact F1 mechanism.
- Guarded acceptances: 3 runs (loss_all × event_only) accepted via the pre-registered audit path — the nested v2 min-admissions gate false-fails this cell (0 admissions is the expected mechanism); campaign gate re-run valid; guard accepted 3/3 guarded cells without interruption (`run_matrix.md` §Incident amendment; `preflight_log.md` 4.1/5.0).

### Damage medians — D̄ (pp) per arm × cell

D̄ = seed-median of D_s (§4.2; cell vs paired same-seed `none`); `n` = usable seeds; positive = damage.

| Arm | N=2 | N=5 | N=10 | semantic (F3) | loss_all (F1) |
|---|---:|---:|---:|---:|---:|
| `event_only` | +4.13 | +8.05 | +12.57 | +75.38 | +1.42 |
| `hybrid` | −0.82 | +8.62 | +13.33 | +79.10 | — (not run) |
| `reconcile` | −0.73 | −1.08 | −0.99 | +67.77 | +1.33 |
| `wake_verify` | — | — | −1.84 (n=2) | +64.64 (n=2) | — |

Contrasts: 46/48 `ok`; 2 `none_breach` exclusions (wake_verify seed 6301 — its none-partner tail_slow 3.95 % > 2 pp, §4.5 pre-registered exclusion; never chased).

### Per-seed damage D_s (pp) — seeds 6301 / 6302 / 6303

| Arm | N=2 | N=5 | N=10 | semantic (F3) |
|---|---|---|---|---|
| `event_only` | 11.35 / 1.40 / 4.13 | 0.12 / 8.05 / 9.42 | 5.74 / 16.18 / 12.57 | 75.23 / 82.64 / 75.38 |
| `hybrid` | −0.82 / −10.40 / 9.67 | 9.49 / −3.56 / 8.62 | 13.34 / 3.86 / 16.41 | 80.79 / 74.49 / 79.10 |
| `reconcile` | 0.12 / −0.73 / −4.45 | −0.43 / −1.08 / −8.21 | 0.12 / −0.99 / −4.68 | 67.77 / 80.15 / 64.44 |
| `wake_verify` | — | — | NA / −0.31 / −3.36 | NA / 59.58 / 69.70 |

loss_all: `event_only` −1.17 / 1.42 / 2.11; `reconcile` 0.15 / 1.33 / 2.93.

### H-S1…H-S4 — pre-registered checks (§6, as computed in the JSONs)

- **H-S1 components**: event_only F2 in-window `000` ≥ 10/LAN 3/3 · hybrid F2 same 3/3 · event_only D_s(semantic) ≥ 30 pp 3/3 · reconcile D_s(semantic) ≥ 30 pp 3/3 · F1 event_only defeat cited from Family 4 (no re-gating) — **pass**.
- **H-S2 components**: reconcile D_s(F2, N=10) ≤ 2 pp 3/3 ({0.12, −0.99, −4.68}) · D_s(F3) ≥ 30 pp 3/3 ({67.77, 80.15, 64.44}) · same-seed joint 3/3 · zero `CHECK VIOLATION` in F3 3/3 — gap median **69.12 pp** ≥ 28 — **pass**.
- **H-S3**: pairwise N\* per seed {2.0, 2.0, 2.0} (median 2.0); band `pull-dominates-immediately`; censored 0; lost seeds none. OLS fits (β, α pp/s, 95 % CI on α): event_only (2.357, **1.040**, [−0.515, 1.825]) · hybrid (−2.502, **1.685**, [0.915, 1.752]) · reconcile (−0.772, **−0.028**, [−0.028, 0.046]); n\*_fit −2.93 (extrapolated; descriptive only). Growth gate: point 1.040 ≥ 0.5 ✓ / CI lower −0.515 > 0.2 ✗ → gate not passed; max D̄(push) 12.57 pp ≥ 5 → branch **`growth_gate_failure`** — **not met (recorded; not a stop)**.
- **H-S4 (secondary)**: D_s(F2, N=10) ≤ 2 pp {NA, −0.31, −3.36} · D_s(F3) ≥ 30 pp {NA, 59.58, 69.70} · healthy-cell cost ≤ +2 pp {**+0.46, +0.16, +3.11**} — pass at 2/3 seeds (6301 NA §4.5; 6303 cost over) — **pass (secondary)**. Price (descriptive): none-cell admit→first median delta wv−eo = +0.49 / +0.35 / −0.09 s.
- **F1 anchor (descriptive, non-gated)**: |D̄(reconcile, loss_all) − D̄(reconcile, N=10)| = |1.330 − (−0.990)| = **2.32 pp ≤ 10** ✓.

## Judgment

**H-S1 — ✅ met (headline).** Every existing rule fails at least one fault family: `event_only` and `hybrid` both carry the F2 false-claim mechanism (nonzero `CHECK VIOLATION` warnings in 18/18 F2 runs; in-window `000` ≥ 10/LAN at every seed) and large semantic damage (75.4 / 79.1 pp medians); `reconcile` carries the semantic defeat (67.8 pp) despite being immune to F2; the F1 defeat of `event_only` is cited from Family 4 per the plan. Direction consistent across seeds — no component needed the reversed-direction exception.

**H-S2 — ✅ met, decisively.** `reconcile` stays at ≤ 2 pp damage across the entire F2 grid (per-seed worst |D_s| = 0.12 pp at N=10) while still showing ≥ 30 pp on F3 — gap median 69.12 pp against the 28 pp criterion, zero `CHECK VIOLATION` in the F3 runs, and the same-seed joint condition holds 3/3. This is the veridicality ≠ verification result: waiting for servability defeats timing lies, but the predicate itself is only as truthful as the service — the F3 lie satisfies every predicate, as it does for all four arms (64.6–79.1 pp across arms), so no admission mechanism survives service lies.

**H-S3 — ❌ not met — recorded per the §4.4 `growth_gate_failure` branch (descriptive band still reported; not a stop).** The point-estimate growth signal is present — `event_only` α = +1.04 pp/s ≥ 0.5, and `hybrid` α = +1.685 with CI [0.915, 1.752] clears the same gate comfortably — and the pairwise crossing is unanimous (N\* = 2 at all 3 seeds, band `pull-dominates-immediately`, zero censoring). The gate fails solely on the event_only CI lower bound (−0.515 vs required > 0.2): with 3 seeds × 3 grid points the seed-bootstrap CI is wide, and one seed (6302) carries a high N=2 anker value (16.18 pp at N=10 vs 1.40 at N=2 distorting the shape). Per pre-registration the branch is recorded as-is: no confirmed N\* crossover claim; the band is delivered descriptively only. Escalation would require a new pre-registration — §4.5 allows no reruns beyond harness invalidity, and none was warranted.

**H-S4 — ✅ (secondary; excluded from primary verdicts).** `wake_verify` probe-before-admission is bounded on F2 (≤ 2 pp at 2/3 seeds; seed 6301 NA via its none-partner breach) and still fails F3 (≥ 30 pp at the same 2/3 seeds), with a small healthy-cell price (+0.46 / +0.16 pp; seed 6303 +3.11 pp over the +2 pp bound) and a sub-half-second admission-latency delta. It mechanically supports H-S2's reading for the channel (timing) faults; it does not rescue the service (F3) family.

**F1 anchor and base requirements — met.** The descriptive F1 anchor holds (2.32 pp ≤ 10 pp). Base requirements (`testing_requirements.md`): all hard gates met — reproducibility (n=3, direction consistent ≥ 2/3); M1 mechanism exercised (384 bind-verified spawns; per-run attestation; F2 warnings; loss_all exact accounting); M2 not gated by design (§4.6 — admission-without-usability is the phenomenon; reported); V1 under the Family-4 lock (P1-validated, E descriptive); I1 floors; I2 honest outcome classes; D1/D2/D3 clean in all 60. Flags reported: telemetry continuity held; per-LAN in-window counts symmetric (no breach).

**Overall — ⚠️ partial.** The primary pass criterion H-S1 ∧ H-S2 ∧ H-S3 = **false**, gated solely on H-S3's pre-registered growth-gate branch — a CI-power limitation at n=3 seeds, not a missing effect (point estimate ≥ threshold; sibling arm's CI passes; band unanimous). The two headline claims are fully supported: (a) every existing admission rule fails at least one fault family, and (b) veridicality (zero fast-fails) is not verification — only wait-for-servability defeats timing lies, and nothing defeats service lies among the tested rules.

## Root Causes

| # | Issue | Impact | Status |
|---|-------|--------|--------|
| 1 | H-S3 growth-gate CI lower bound missed (event_only α CI [−0.515, 1.825]; needs lower > 0.2) — 3-seed × 3-point bootstrap CI width, one seed's N=2 shape distortion | H-S3 not met; band reported descriptively only | Confirmed — pre-registered §4.4 #3 branch recorded; not a stop; no rerun (§4.5 limits reruns to harness invalidity) |
| 2 | `wake_verify` seed 6301 none-partner breach (tail_slow 3.95 % > 2 pp) | 2 wake_verify contrasts NA; H-S4 evaluated at 2/3 seeds | Pre-registered §4.5 exclusion applied; never chased |
| 3 | Nested v2 min-admissions gate false-fails loss_all × event_only (0 admissions = expected mechanism) | Run 17 initial sequencer STOP | Resolved — audit acceptance; guarded rule; 3/3 guarded cells accepted; `run_matrix.md` §Incident amendment |
| 4 | `hybrid` F2 low-N seed noise (6302: −10.4 pp at N=2, −3.6 pp at N=5; one negative seed at each low N) | None on medians; N=10 consistent 3/3 | Recorded — fallback-based arm variance at low N; no action |

## Next Actions

1. Thesis integration (RQ3 soundness section): render damage-vs-N (per-arm D̄(N) with per-seed dots) and crossover-band annotation from `analysis/rq3snd_crossover_all.json` per the thesis-figures pipeline when authoring `tese/`.
2. Wording discipline: report H-S3 as "growth gate not met — pre-registered branch; descriptive band `pull-dominates-immediately`"; never claim a confirmed N\* crossover. Note `hybrid`'s α CI clears the same gate — the push-family growth signal is present.
3. No further runs under this plan; any growth-gate power study is a new pre-registration (more seeds/blocks).
4. Retention: run folders remain on `cloud-vm-rq3` as the campaign archive (raw request data retained); controller logs removed post-analysis after parse-retention (see Changelog).

## Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-10-05 | Initial results.md — E stage complete (60/60 valid); H-S1 ✅, H-S2 ✅, H-S3 ❌ (`growth_gate_failure` branch), H-S4 ✅ secondary; campaign-wide damage + crossover JSONs archived under `analysis/` | First campaign analysis; verdicts computed by `rq3.readiness_robustness` per plan §4.4/§6 |
| 2026-10-05 | Post-analysis cleanup: controller logs removed from the 60 run folders after parse-retention verification (120 logs, ≈54 GiB reclaimed; run folders, retained CSVs, and raw request data intact) | `metrics-run-summary` retention policy; run folders remain on the VM as the campaign archive |
| 2026-10-05 | Thesis integration applied: §5 RQ3 extended with the claim-failure results (RQ3 statement + contribution widened, `tab:rq3_soundness` verdict table, `fig:rq3_soundness_damage`, synthesis row, rewritten summary); false-claim citations added (Flora et al. 2022; Pourreza and Narasimhan 2023); prose style pass (no dashes, minimal punctuation) | User-approved E1--E5 integration pass |
| 2026-10-05 | Thesis prose restructure: §5 RQ3 merged into one narrative (definition of readiness admission first, explanation before specifics, unified three-part expectation incl. the claim-failure families; 120 s abandonment window vs inert 130 s fallback timer clarified; "second campaign" framing removed; run sets recorded in `tab:rq3_design`) | Author style directive (whole-story requirement) |
| 2026-10-05 | Behaviour-first trim: §5 RQ3 reordered to one behaviour at a time across all rules (speed, lost, early, false), with the loss behaviour merged across both campaigns and the former F1 tie-back; dropped the poll-calibration result and the recovery-ordering figure (render archived in `tese/images/unused/`); compressed qualifiers, expectation part 3 and F2 count detail. Section 466 to 366 lines, 7 floats | Author trim directive (valuable-insight retention) |
| 2026-10-05 | House-pattern fix: results sections carry no citations, so the Flora/Pourreza `\parencite` calls were removed from §5 RQ3 and remain only in Chapter 2 (`sec:lit_sdn_lb`) | Author directive (citations belong to the literature review) |
| 2026-10-05 | Thesis scope retrenchment (author review): the false-claim (semantic) premise judged tautological and removed from the thesis — §5 F3 paragraph, bridge, expectation clause, veridicality verdict, false-claim table rows, two-panel figure (replaced by single-panel `rq3_soundness_damage_v2.png`, timing grid), In-sum and synthesis clauses, RQ3 statement and contribution clauses, and the Ch2 grounding passage. Flora/Pourreza fully removed on author review (bib entries, PDFs, extractions, README rows; corpus index restored to 37). This archive still records the full campaign, H-S1/H-S2/H-S4 included; the thesis reports the premature-claim grid and the loss anchor | Author directive (remove obvious/tautological premise) |
| 2026-10-05 | Thesis polish batch: RQ3 micro-wording ("lost or early", seed range spelled, premature-claim grid caption, "trusting rules"); Ch5 metrics bullet now three parts with the premature measure; testing and discussion carry the premature-claim comparison; Ch4 TODO gains the wake-verify sub-mode note; figure 5.6 replaced by the two-panel `rq3_admission_intervals_v2.png` (log-scale readiness-to-admission panel dropped, values stay in `tab:rq3_delays`) with the fast and slow binding classes defined in the caption; figure 5.8 caption defines damage (pp) and negative readings | Author review of section layout and figure readability |
