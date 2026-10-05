# Post-Run Analysis — RQ3 Soundness (Readiness-Admission Fault Robustness)

## 1. Objective

Determine whether any existing admission rule (`event_only` push-trust, `hybrid`
fallback, `reconcile` periodic-poll; optional `wake_verify` probe) can deliver
sound usable-capacity realization across all three readiness-channel fault
families — and if not, where push-trust and pull-verification cross over,
quantified in one common damage currency. This is the soundness pillar of the
reframed RQ3 (readiness-admission coordination → usable-capacity realization;
see `tese/research_questions/rq3/rq3_reframing_recommendation.md`).

Independent variable: admission semantics (4 arms) × fault family — F2 timing
lies (`EDGE_READY_PREMATURE_S` lead N ∈ {2, 5, 10} s), F3 service lies
(semantic knob), F1 total event loss (`loss_all`) — with the pre-registered
verdicts H-S1…H-S3 (optional H-S4) fixed in the plan §6 before execution.

## 2. Mechanism

Four arms × fault cells over seeds 6301–6303 = 60 E-stage runs, preceded by a
3+1-run go/no-go P1 preflight (seeds 6351–6354); the `wake_verify` block ran as
a tail amendment contingent on a pre-tail gate scan (PASS, runs=51). Regime is
the Family-4 lock, unchanged: `compute_plateau` 600 s, `rate_per_client 2.0`,
pure-compute (`service_pressure 1.0`), `EDGE_CPUS=0.12`; both fault knobs are
default-off and byte-identical on the off-path; frozen worktree
`~/rq3snd_frozen2` (commit `541fb22`, tag `rq3snd-preflight-20261003`).

Damage is measured in the common currency D (§4.2) from I2-honest outcome
classes (§4.1, timeout-first) against same-seed `none` partners; this is a
pre-registered adversarial campaign — damage is the outcome, never a gate
failure. Three loss_all × event_only runs were accepted through a documented
audit path (nested v2 min-admissions gate false-fail on the expected
0-admissions mechanism; campaign gate independently valid; guard 3/3 —
`run_matrix.md` §Incident amendment). Every run passed its base gates before
counting (60/60 valid: driver-clean, no restart, provenance, quota, floors;
384 bind-verified spawns).

## 3. Results

| Criterion (plan §4.7/§6) | Verdict | Evidence |
|---|---|---|
| SC-5 · H-S1 — every existing rule fails a fault family (all components ≥ 2/3 seeds) | ✅ met | 5/5 components at 3/3 seeds: in-window `000` ≥ 10/LAN (event_only + hybrid, F2), D_s(semantic) ≥ 30 pp (event_only, reconcile), F1 defeat cited from Family 4; 4–6 `CHECK VIOLATION`/run in 18/18 F2 runs |
| SC-6 · H-S2 — veridicality ≠ verification (reconcile: D_s(F2) ≤ 2 pp ∧ D_s(F3) ≥ 30 pp ∧ zero violations, ≥ 2/3 seeds) | ✅ met | F2 ≤ 2 pp 3/3 (worst 0.12 pp); F3 ≥ 30 pp 3/3 (67.77–80.15 pp); gap median 69.12 pp ≥ 28; zero `CHECK VIOLATION` in F3 3/3; same-seed joint 3/3 |
| SC-7 · H-S3 — quantified crossover (growth gate met ∧ N\* band reported) | ❌ not met — pre-registered `growth_gate_failure` branch recorded; descriptive band reported | α(event_only) = +1.040 pp/s ≥ 0.5 but CI lower −0.515 ≤ 0.2 → gate not passed; max D̄ 12.57 pp ≥ 5 → branch per §4.4 #3; band `pull-dominates-immediately` (N\* = 2.0 at 3/3 seeds, zero censoring); hybrid α CI [0.915, 1.752] clears the same gate |
| SC-8 — base-requirement evidence for every assessed run | ✅ met | 60/60 valid; floors PASS; provenance + attestation present; no restart/crash; D1 clean |
| H-S4 (optional/secondary, excluded from primary verdicts) | ✅ met at 2/3 seeds | F2 ≤ 2 pp {—, −0.31, −3.36}; F3 ≥ 30 pp {—, 59.58, 69.70}; healthy-cell cost {+0.46, +0.16, +3.11 pp} (seed 6301 NA §4.5; 6303 over +2 pp) |

**Base requirements** (`testing_requirements.md`) — no hard-gate miss:
reproducibility (n = 3, direction consistent, fixed seeds); B1/B2 N/A
(pre-registered adversarial campaign); M1 mechanism exercised (per-run
attestations; F2 warning signature; exact loss_all accounting) · M2 not gated
by design — admission-without-usability *is* the phenomenon, reported per
arm · V1 under the Family-4 lock (P1-validated, E descriptive) · I1 floors ·
I2 honest classes · D1/D2/D3 clean in all 60. Flags: telemetry continuity
held; per-LAN counts symmetric (no ≤ 3× breach observed).

**Headline.** No tested rule is sound across all three families. Under timing
lies, damage grows with the lie lead for the trust-based arms (event_only
medians +4.1 → +8.1 → +12.6 pp at N = 2/5/10; hybrid +13.3 pp at N = 10) while
the waiting arm stays flat (reconcile −0.7 to −1.1 pp across the whole grid —
pairwise crossing already at N = 2 for 3/3 seeds); service lies damage **all**
arms severely (medians 64.6–79.1 pp) because every admission predicate —
including the probe — is satisfied by the lie; total event loss is exact:
event_only abandons all capacity (0 admitted / 32–33 spawns), while reconcile
recovers via its poll (5 probe admissions, F1 anchor 2.32 pp ≤ 10 pp).

## 4. Gaps & Next Steps

1. **H-S3 growth gate is a power limitation, not a missing effect.** The point
   estimate (event_only α = 1.04 pp/s) clears the 0.5 threshold and the hybrid
   arm's CI ([0.915, 1.752]) clears the same gate, but the event_only CI lower
   bound (−0.515) misses 0.2 with only 3 seeds × 3 grid points. The
   descriptive band (`pull-dominates-immediately`) is unanimous. Any escalation
   for CI power is a **new pre-registration** — the plan §4.5 allows no reruns
   beyond harness invalidity.
2. **Single-seed effects on the secondary arm.** wake_verify seed 6301's
   contrasts were NA'd by its none-partner breach (§4.5), and seed 6303's
   healthy-cell cost (+3.11 pp) exceeded the +2 pp descriptive bound — both
   recorded, neither chased; the arm certifies claim (c) for the channel
   faults at 2/3 seeds only.
3. **F1 hybrid cell not run** (plan scope): the F1 claims rest on the
   event_only defeat (Family-4 cited) and the reconcile anchor (2.32 pp).
4. **Next:** thesis rendering (damage-vs-N with per-seed dots; crossover band
   annotation) and the H-S3 wording per its branch; no further runs are
   planned under this plan.
