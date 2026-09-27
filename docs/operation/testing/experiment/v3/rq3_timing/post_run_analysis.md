# Post-Run Analysis — RQ3 Timing (Readiness-Loss Relief Contrast under Demand Escalation)

## 1. Objective

Determine whether, under total readiness-event loss (`loss_all`) with constrained headroom (quota 0.12) and demand escalation (rate 2.0), an event-only admission arm degrades user service *visibly and boundedly* on the slow-share axis, while fallback-probing (`hybrid`) and periodic-polling (`reconcile`) arms recover into a healthy plateau tail — and certify that contrast at n = 6 blocks behind a reproducible 3-of-4-seed preflight. This is the consequence/robustness pillar of the reframed RQ3 (readiness-admission coordination → usable-capacity realization; `tese/research_questions/rq3/rq3_reframing_recommendation.md`).

Independent variable: readiness-admission coordination semantics (`event_only` with inert 130 s fallback vs `hybrid` 20 s fallback vs `reconcile` 10 s poll), crossed with fault cell (`none`, `loss_all`). Primary metric: slow-share `#(timeout ∨ latency > 1 s)/service` over `compute_plateau`; onset window (first 150 s) as co-primary; plateau tail (last 300 s) as relief-completion gate.

## 2. Mechanism

Three arms × two cells × six blocks = 36 runs, seeds 5201–5206, arm order rotated per block, full reset between runs. Workload `compute_plateau` 600 s, pure-compute (`service_pressure` 1.0), quota fixed at `EDGE_CPUS=0.12`, rate swept and **locked at 2.0** via a 3-of-4-seed preflight (5301/5302/5304; 5303 recorded as a diagnosed stochastic outlier). Controller/application code frozen; fault knobs and arm env deltas byte-identical to the robustness family. Every run base-gated (mechanism exactness, quota, floors, driver-clean, baseline, no scale-down, no restart) before the campaign verdict.

## 3. Results

| Criterion (plan §6) | Verdict | Evidence |
|---|---|---|
| H-T1 full Δ ≥ 5 pp in ≥ 4/6 assessable + median ≥ 5 pp | ✅ met | 5/5 assessable (7.00 / 10.87 / 6.21 / 7.64 / 9.99), median 7.64 pp, MWU p = 0.00397, δ = 1.0 |
| H-T1 onset Δ ≥ 5 pp (co-primary) | ✅ met | 5/5 blocks (25.11–30.84 pp), median 28.01 pp |
| H-T1 boundedness (event_only ≤ 25 %) | ✅ met | median 10.6 %, 5/5 ≤ 25 % |
| H-T2 relief completion (hybrid ∧ reconcile tail ≤ 2 pp, ≥ 5/6) | ✅ met | 5/6 relief blocks (b4 excluded) |
| H-T2 time-to-relief ordering (hybrid median > reconcile) | ✅ met (re-anchored, analysis-only 2026-09-26) | as-run TTR (0.95 vs 1.30 s) was an onset-anchor artifact; spawn-anchored: hybrid 21.38 > reconcile 17.07 s (spawn→admit, 6/6); spawn→first serve 22.12 vs 17.76 s (5/6 + tie) — see `analysis/timing_campaign_reanchored.json` |
| H-T2 event_only zero new-backend successes | ✅ met | 6/6 blocks |
| H-T3 none-cell health (bad ≤ 1 %, tail ≤ 2 pp, all arms) | ⚠️ mostly clean | 16/18 clean; b3 none-hybrid bad 1.19 %; b5 none-reconcile tail 4.29 % (single-window) |

**Base requirements (`testing_requirements.md`)** — all hard gates met: reproducibility (n = 6, direction consistent, fixed seeds); M1 mechanism exercised; M2 capacity usable; D1 baseline clean; D2 no restart/crash; D3 provenance present. No hard-gate miss; the H-T3 floor read is an RQ-specific gate, not evidence-invalidating (the H-T2-ordering miss was resolved by the 2026-09-26 re-anchoring).

**Headline result.** Under `loss_all` at quota 0.12 / rate 2.0, `event_only` degrades to 8.3–14.4 % slow-share (onset 29.7–39.0 % slow, t0/t30 75–98 %) while `hybrid`/`reconcile` recover to a healthy tail (≤ 2 pp in 5/6 blocks), a contrast of ~6.2–10.9 pp (median 7.64 pp) full-plateau and ~25–31 pp (median 28 pp) onset. The degradation is bounded (≤ 25 %) and onset-transient-dominated.

## 4. Gaps & Next Steps

1. **H-T2 TTR — resolved by analysis-only re-anchoring (2026-09-26).** The as-run metric anchored at plateau onset while the first backend spawns **27–35 s before** onset (during baseline) in every control run, so its 0–8 s values measured the phase boundary, not the relief interval. Re-anchored at the first relief backend's spawn (`analysis/timing_campaign_reanchored.json`; admission logs + client rows, any phase): **reconcile is faster than hybrid** — spawn→admit medians 17.07 vs 21.38 s (earlier in 6/6 blocks) and spawn→first serve medians 17.76 vs 22.12 s (5/6 plus a sub-second tie in block 3) — consistent with the plan's ≤10 s poll-quantum direction (observed median gap ≈4.3 s). The slow-rate relief-completion *timing* remains non-separating (five window variants; direction splits); the campaign tail gate (5/6) is unchanged. Overall campaign pass remains false, now gated on H-T3 alone. The re-anchored definition is now the analyzer's `timing_relief_metrics` (adopted 2026-09-26; onset value kept as a diagnostic).
2. **H-T3 is mostly clean, not a substantive failure.** 16/18 no-fault runs meet both floors; the two breaches (bad 1.19 % — 0.19 pp over; tail 4.29 % — one 30-s spike) are marginal single-window stochastic humps. They do not touch the H-T1 contrast, and they are consistent with the thin-headroom premise (the static tier is near saturation at rate 2.0 even without fault).
3. **Scope of the consequence claim.** Demonstrated only for total event loss + constrained headroom + demand escalation; not selective loss, restart, or healthy-event regimes. The none-cell spikes (4.08/4.29 %) show the static tier is near saturation at rate 2.0 independent of the fault — the Δ metric controls for this, and the claim must be stated as a contrast within a stressed regime.
4. **The directional result is construction-expected** (event_only's fallback is provably inert); the thesis contribution is the *quantified, bounded, conditional* trade-off (the ~7 s latency benefit priced against a ~6–11 pp bounded robustness cost), not a discovery that fallback helps.
