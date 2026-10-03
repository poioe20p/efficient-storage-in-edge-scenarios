# RQ3 Soundness — E-Stage Execution Log

Full-campaign tracker (user-approved 2026-10-03: complete run set; VM storage
verified). One row per run; status updated as runs execute. Runs on
`~/rq3snd_frozen2`, fixed image `207b1f9e8f64`, launcher
`rq3snd_p1_01_launch_run.sh`, full reset between runs (launcher make chain).
Per-run logs on the VM: `/tmp/rq3snd_<label>.log` (R3b: `/tmp/rq3snd_93.log`).

Columns: **Status** = pending / running / done / invalid / failed; **Note** =
run_id + base-gate note when checked.

## P1 — optional R3b

| # | Block | Label | Cell | Arm | Seed | Status | Note |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 0 | P1 | `rq3snd_semantic_reconcile_93` | semantic | reconcile | 6354 | pending | dedicated F3×reconcile certification; updates lock `r3b_informative` |

## Block 1 — seed 6301 (arm order: event_only → hybrid → reconcile)

| # | Block | Label | Cell | Arm | Seed | Status | Note |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | B1 | `rq3snd_none_event_only_1` | none | event_only | 6301 | pending | |
| 2 | B1 | `rq3snd_premature2_event_only_1` | premature2 | event_only | 6301 | pending | |
| 3 | B1 | `rq3snd_premature5_event_only_1` | premature5 | event_only | 6301 | pending | |
| 4 | B1 | `rq3snd_premature10_event_only_1` | premature10 | event_only | 6301 | pending | |
| 5 | B1 | `rq3snd_semantic_event_only_1` | semantic | event_only | 6301 | pending | |
| 6 | B1 | `rq3snd_none_hybrid_1` | none | hybrid | 6301 | pending | |
| 7 | B1 | `rq3snd_premature2_hybrid_1` | premature2 | hybrid | 6301 | pending | |
| 8 | B1 | `rq3snd_premature5_hybrid_1` | premature5 | hybrid | 6301 | pending | |
| 9 | B1 | `rq3snd_premature10_hybrid_1` | premature10 | hybrid | 6301 | pending | |
| 10 | B1 | `rq3snd_none_reconcile_1` | none | reconcile | 6301 | pending | |
| 11 | B1 | `rq3snd_premature2_reconcile_1` | premature2 | reconcile | 6301 | pending | |
| 12 | B1 | `rq3snd_premature5_reconcile_1` | premature5 | reconcile | 6301 | pending | |
| 13 | B1 | `rq3snd_premature10_reconcile_1` | premature10 | reconcile | 6301 | pending | |
| 14 | B1 | `rq3snd_semantic_reconcile_1` | semantic | reconcile | 6301 | pending | |
| 15 | B1 | `rq3snd_loss_all_reconcile_1` | loss_all | reconcile | 6301 | pending | |
| 16 | B1 | `rq3snd_semantic_hybrid_1` | semantic | hybrid | 6301 | pending | optional (descriptive) |
| 17 | B1 | `rq3snd_loss_all_event_only_1` | loss_all | event_only | 6301 | pending | optional (F1 push anchor) |
| 18 | B1 | `rq3snd_none_wake_verify_1` | none | wake_verify | 6301 | pending | optional |
| 19 | B1 | `rq3snd_premature10_wake_verify_1` | premature10 | wake_verify | 6301 | pending | optional |
| 20 | B1 | `rq3snd_semantic_wake_verify_1` | semantic | wake_verify | 6301 | pending | optional |

## Block 2 — seed 6302 (arm order: hybrid → reconcile → event_only)

| # | Block | Label | Cell | Arm | Seed | Status | Note |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 21 | B2 | `rq3snd_none_hybrid_2` | none | hybrid | 6302 | pending | |
| 22 | B2 | `rq3snd_premature2_hybrid_2` | premature2 | hybrid | 6302 | pending | |
| 23 | B2 | `rq3snd_premature5_hybrid_2` | premature5 | hybrid | 6302 | pending | |
| 24 | B2 | `rq3snd_premature10_hybrid_2` | premature10 | hybrid | 6302 | pending | |
| 25 | B2 | `rq3snd_none_reconcile_2` | none | reconcile | 6302 | pending | |
| 26 | B2 | `rq3snd_premature2_reconcile_2` | premature2 | reconcile | 6302 | pending | |
| 27 | B2 | `rq3snd_premature5_reconcile_2` | premature5 | reconcile | 6302 | pending | |
| 28 | B2 | `rq3snd_premature10_reconcile_2` | premature10 | reconcile | 6302 | pending | |
| 29 | B2 | `rq3snd_semantic_reconcile_2` | semantic | reconcile | 6302 | pending | |
| 30 | B2 | `rq3snd_loss_all_reconcile_2` | loss_all | reconcile | 6302 | pending | |
| 31 | B2 | `rq3snd_none_event_only_2` | none | event_only | 6302 | pending | |
| 32 | B2 | `rq3snd_premature2_event_only_2` | premature2 | event_only | 6302 | pending | |
| 33 | B2 | `rq3snd_premature5_event_only_2` | premature5 | event_only | 6302 | pending | |
| 34 | B2 | `rq3snd_premature10_event_only_2` | premature10 | event_only | 6302 | pending | |
| 35 | B2 | `rq3snd_semantic_event_only_2` | semantic | event_only | 6302 | pending | |
| 36 | B2 | `rq3snd_semantic_hybrid_2` | semantic | hybrid | 6302 | pending | optional (descriptive) |
| 37 | B2 | `rq3snd_loss_all_event_only_2` | loss_all | event_only | 6302 | pending | optional (F1 push anchor) |
| 38 | B2 | `rq3snd_none_wake_verify_2` | none | wake_verify | 6302 | pending | optional |
| 39 | B2 | `rq3snd_premature10_wake_verify_2` | premature10 | wake_verify | 6302 | pending | optional |
| 40 | B2 | `rq3snd_semantic_wake_verify_2` | semantic | wake_verify | 6302 | pending | optional |

## Block 3 — seed 6303 (arm order: reconcile → event_only → hybrid)

| # | Block | Label | Cell | Arm | Seed | Status | Note |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 41 | B3 | `rq3snd_none_reconcile_3` | none | reconcile | 6303 | pending | |
| 42 | B3 | `rq3snd_premature2_reconcile_3` | premature2 | reconcile | 6303 | pending | |
| 43 | B3 | `rq3snd_premature5_reconcile_3` | premature5 | reconcile | 6303 | pending | |
| 44 | B3 | `rq3snd_premature10_reconcile_3` | premature10 | reconcile | 6303 | pending | |
| 45 | B3 | `rq3snd_semantic_reconcile_3` | semantic | reconcile | 6303 | pending | |
| 46 | B3 | `rq3snd_loss_all_reconcile_3` | loss_all | reconcile | 6303 | pending | |
| 47 | B3 | `rq3snd_none_event_only_3` | none | event_only | 6303 | pending | |
| 48 | B3 | `rq3snd_premature2_event_only_3` | premature2 | event_only | 6303 | pending | |
| 49 | B3 | `rq3snd_premature5_event_only_3` | premature5 | event_only | 6303 | pending | |
| 50 | B3 | `rq3snd_premature10_event_only_3` | premature10 | event_only | 6303 | pending | |
| 51 | B3 | `rq3snd_semantic_event_only_3` | semantic | event_only | 6303 | pending | |
| 52 | B3 | `rq3snd_none_hybrid_3` | none | hybrid | 6303 | pending | |
| 53 | B3 | `rq3snd_premature2_hybrid_3` | premature2 | hybrid | 6303 | pending | |
| 54 | B3 | `rq3snd_premature5_hybrid_3` | premature5 | hybrid | 6303 | pending | |
| 55 | B3 | `rq3snd_premature10_hybrid_3` | premature10 | hybrid | 6303 | pending | |
| 56 | B3 | `rq3snd_semantic_hybrid_3` | semantic | hybrid | 6303 | pending | optional (descriptive) |
| 57 | B3 | `rq3snd_loss_all_event_only_3` | loss_all | event_only | 6303 | pending | optional (F1 push anchor) |
| 58 | B3 | `rq3snd_none_wake_verify_3` | none | wake_verify | 6303 | pending | optional |
| 59 | B3 | `rq3snd_premature10_wake_verify_3` | premature10 | wake_verify | 6303 | pending | optional |
| 60 | B3 | `rq3snd_semantic_wake_verify_3` | semantic | wake_verify | 6303 | pending | optional |

## Post-run analysis (after all runs)

- A2 damage tables: `readiness_robustness.py soundness-damage --run-dir <all>`
- A3 crossover: `readiness_robustness.py soundness-crossover`
- A4 hypothesis verdicts H-S1…H-S4 + base-requirements table
- `results.md` + `post_run_analysis.md` (only after the campaign)
