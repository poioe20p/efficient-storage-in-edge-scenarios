# RQ3 v2 — Results (template)

**Date**: 2026-08-04 · **Plan**: `rq3_v2_rework_plan.md` · **Status**: 🔵 template — awaiting the Phase 6 campaign on `cloud-vm-rq3`

## 1. Timeline

| Date | Event |
|---|---|
| 2026-08-04 | RQ3 v2 rework plan approved (approach A); Phases 1–3 + env regimes implemented; selftests passing |
| TBD | Phase 4 calibration + Phase 6 campaign on `cloud-vm-rq3` |
| TBD | Per-run analysis + stats + judgment |

## 2. Per-arm tables (fill from `rq3_admission_analysis.py --csv`)

| Arm | n (non-void) | gap_timeout median | gap_failure median | useful_share median | scale→1stok median (s) | start→admit median (s) | event_fraction |
|---|---|---|---|---|---|---|---|
| direct | | | | | | | |
| discovery | | | | | | | |
| discovery_15 | | | | | | | |

## 3. Primary pair — direct vs discovery

| Metric | med direct | med discovery | MWU p | Cliff's δ | supports headline |
|---|---|---|---|---|---|
| gap_timeout_rate | | | | | |
| gap_failure_rate | | | | | |
| useful_share | | | | | |
| scale→usable-capacity | | | | | |
| spawn→admitted (manip.) | | | | | |

**Consistency rule (≥ 2 of 3 supporting in the same direction):** □ met □ mixed/ambiguous

## 4. Sensitivity — discovery vs discovery_15 (Cliff's delta only)

| Metric | med disc10 | med disc15 | Cliff's δ |
|---|---|---|---|
| gap_timeout_rate | | | |
| spawn→admitted | | | |

## 5. Manipulation / validity

- Quantization `direct` ≤ `discovery`: □
- `admitted → first_flow` arm-identical: □
- Event-fraction ≥ 0.80 in direct runs: □ (instrumentation-degraded runs listed)
- Flow-validation gates (A/B/C/D) per run: □
- Readiness-criterion identity (post-admission probe): □

## 6. Judgment

(To be written after the campaign — timeline, per-arm tables, stats verdict,
null-acceptance, and limitations per `analysis_focus.md`.)
