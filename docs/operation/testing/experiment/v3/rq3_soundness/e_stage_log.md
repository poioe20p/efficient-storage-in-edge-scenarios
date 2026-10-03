# RQ3 Soundness — E-Stage Execution Log

Full-campaign tracker (complete run set approved 2026-10-03; disk headroom secured
2026-10-03 — off-experiment VM archives cleaned (~27 GB), free ≈ 70 GB; docker pruned;
**order amended 2026-10-03: optional `wake_verify` runs deferred to the campaign tail,
contingent on the pre-tail gate scan**);
**E sequence RUNNING since 2026-10-03 10:35:45 UTC** — 60 runs, ETA ≈ 2026-10-05 early UTC). One row
per run; status updated as runs execute. Runs on
`~/rq3snd_frozen2`, fixed image `207b1f9e8f64`, launcher
`rq3snd_p1_01_launch_run.sh`, full reset between runs (launcher make chain).
Per-run logs on the VM: `/tmp/rq3snd_<label>.log` (R3b: `/tmp/rq3snd_93.log`).

Columns: **Status** = pending / running / done / invalid / failed; **Note** =
run_id + base-gate note when checked.

## P1 — optional R3b

| # | Block | Label | Cell | Arm | Seed | Status | Note |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 0 | P1 | `rq3snd_semantic_reconcile_93` | semantic | reconcile | 6354 | done | run `20261003_093133` exit 0; gates (a)–(d) all true; lock refreshed with all four runs — `r3b_informative` = true |

## Block 1 — seed 6301 (arm order: event_only → hybrid → reconcile)

| # | Block | Label | Cell | Arm | Seed | Status | Note |
| ---: | --- | --- | --- | --- | ---: | --- | --- |
| 1 | B1 | `rq3snd_none_event_only_1` | none | event_only | 6301 | done | run `20261003_104223` 10:35→11:17 UTC; launcher rc=0, sentinel ok; base gates **OK** (driver_clean/no_restart/provenance/quota); floors PASS (pooled 57,263; per-LAN 28.6k each; f2 ≥15 s); none_health no breach (tail_slow 0.86%, bad 0.68%); viol=0; 6 spawns bind-verified, no deferrals (none cell); cancel 0.49% |
| 2 | B1 | `rq3snd_premature2_event_only_1` | premature2 | event_only | 6301 | done | run `20261003_112420` 11:17→11:59 UTC; base gates **OK**; floors PASS; **5 spawns, deferral_s = 2.00 s each** (knob `EDGE_READY_PREMATURE_S=2` exact); viol=5 (recorded lie-window checks); cancel 0.47%; 000=45 |
| 3 | B1 | `rq3snd_premature5_event_only_1` | premature5 | event_only | 6301 | done | run `20261003_120616` 11:59→12:41 UTC; base gates **OK**; floors PASS; **5 spawns, deferral_s = 5.01 s** (knob=5 exact); **in-window 000 = 514** (vs 55 at N=2 — damage scales with lead); viol=5; cancel 0.45% |
| 4 | B1 | `rq3snd_premature10_event_only_1` | premature10 | event_only | 6301 | done | run `20261003_124808` 12:41→13:23 UTC; base gates **OK**; floors PASS; 6 spawns, deferral_s = 10.01 s (knob=10 exact); **in-window 000 = 985** (0→55→514→985 monotone with lead); viol=6; cancel 0.46% |
| 5 | B1 | `rq3snd_semantic_event_only_1` | semantic | event_only | 6301 | done | run `20261003_132958` 13:23→14:04 UTC; base gates **OK**; floors PASS; **F3 signature: 5xx = 45,617, 000 = 0 (channel up), viol = 0 (predicate satisfied while service fails)**; cancel 0.32% |
| 6 | B1 | `rq3snd_none_hybrid_1` | none | hybrid | 6301 | done | run `20261003_141130` 14:04→14:46 UTC; base gates **OK**; floors PASS; clean control (000=0, 5xx=0, viol=0); cancel 0.44% |
| 7 | B1 | `rq3snd_premature2_hybrid_1` | premature2 | hybrid | 6301 | done | run `20261003_145308` 14:46→15:28 UTC; base gates **OK**; floors PASS; deferral_s = 2.00; **in-window 000 = 96**; viol=5; cancel 0.40% |
| 8 | B1 | `rq3snd_premature5_hybrid_1` | premature5 | hybrid | 6301 | done | run `20261003_153437` 15:28→16:09 UTC; base gates **OK**; floors PASS; deferral_s = 5.01; **in-window 000 = 818**; viol=5; cancel 0.49% |
| 9 | B1 | `rq3snd_premature10_hybrid_1` | premature10 | hybrid | 6301 | done | run `20261003_161604` 16:09→16:51 UTC; base gates **OK**; floors PASS; deferral_s = 10.01; **in-window 000 = 1228**; viol=5; cancel 0.41% |
| 10 | B1 | `rq3snd_none_reconcile_1` | none | reconcile | 6301 | done | run `20261003_165802` 16:51→17:33 UTC; base gates **OK**; floors PASS (pooled 57,325; per-LAN 28.7k each); clean none control (000=0, 5xx=0, viol=0); cancel 0.38%; 5 spawns bind-verified, no deferrals (none cell) |
| 11 | B1 | `rq3snd_premature2_reconcile_1` | premature2 | reconcile | 6301 | done | run `20261003_173935` 17:33→18:14 UTC (**orphan-adopted by part-2 sequencer; run uninterrupted**); base gates **OK**; floors PASS; deferral_s = 2.01; **000=0, viol=0 (probe immunity)**; cancel 0.47% |
| 12 | B1 | `rq3snd_premature5_reconcile_1` | premature5 | reconcile | 6301 | done | run `20261003_182134` 18:14→18:56 UTC; base gates **OK**; floors PASS; deferral_s = 5.01; **000=0, viol=0 (probe immunity)**; cancel 0.49% |
| 13 | B1 | `rq3snd_premature10_reconcile_1` | premature10 | reconcile | 6301 | done | run `20261003_190310` 18:56→19:38 UTC; base gates **OK**; floors PASS; deferral_s = 10.01; **000=0, viol=0 (probe immunity — full F2 grid 0/0/0)**; cancel 0.47% |
| 14 | B1 | `rq3snd_semantic_reconcile_1` | semantic | reconcile | 6301 | done | run `20261003_194441` 19:38→20:19 UTC; base gates **OK**; floors PASS; **F3 signature: 5xx = 40,083, 000 = 0, viol = 0 (veridicality ≠ verification)**; cancel 0.37% |
| 15 | B1 | `rq3snd_loss_all_reconcile_1` | loss_all | reconcile | 6301 | running | started 20:19:40 UTC, folder `20261003_202612` |
| 16 | B1 | `rq3snd_semantic_hybrid_1` | semantic | hybrid | 6301 | pending | optional (descriptive) |
| 17 | B1 | `rq3snd_loss_all_event_only_1` | loss_all | event_only | 6301 | pending | optional (F1 push anchor) |
| 18 | B1 | `rq3snd_none_wake_verify_1` | none | wake_verify | 6301 | pending | optional — **tail block** (amendment 2026-10-03; contingent on pre-tail gate scan) |
| 19 | B1 | `rq3snd_premature10_wake_verify_1` | premature10 | wake_verify | 6301 | pending | optional — **tail block** (amendment 2026-10-03; contingent on pre-tail gate scan) |
| 20 | B1 | `rq3snd_semantic_wake_verify_1` | semantic | wake_verify | 6301 | pending | optional — **tail block** (amendment 2026-10-03; contingent on pre-tail gate scan) |

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
| 38 | B2 | `rq3snd_none_wake_verify_2` | none | wake_verify | 6302 | pending | optional — **tail block** (amendment 2026-10-03; contingent on pre-tail gate scan) |
| 39 | B2 | `rq3snd_premature10_wake_verify_2` | premature10 | wake_verify | 6302 | pending | optional — **tail block** (amendment 2026-10-03; contingent on pre-tail gate scan) |
| 40 | B2 | `rq3snd_semantic_wake_verify_2` | semantic | wake_verify | 6302 | pending | optional — **tail block** (amendment 2026-10-03; contingent on pre-tail gate scan) |

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
| 58 | B3 | `rq3snd_none_wake_verify_3` | none | wake_verify | 6303 | pending | optional — **tail block** (amendment 2026-10-03; contingent on pre-tail gate scan) |
| 59 | B3 | `rq3snd_premature10_wake_verify_3` | premature10 | wake_verify | 6303 | pending | optional — **tail block** (amendment 2026-10-03; contingent on pre-tail gate scan) |
| 60 | B3 | `rq3snd_semantic_wake_verify_3` | semantic | wake_verify | 6303 | pending | optional — **tail block** (amendment 2026-10-03; contingent on pre-tail gate scan) |

## Monitoring (per run + every 5 min)

- **Per run (sequencer):** launcher exit code + `.run_completed` sentinel,
  then `soundness-damage` on the finished run → base gates (`valid`: driver
  clean / no restart / provenance / quota). The chain **stops** on any failure
  or free disk < 6 GB. Per-run gate JSON: `/tmp/rq3snd_gate_<label>.json`.
- **Pulse monitor (every 5 min, since 2026-10-03):** `/tmp/rq3snd_e_pulse.py`
  → `/tmp/rq3snd_e_pulse.txt`: per-run detailed line (valid, floors, cancel,
  class counts, violations, median deferral, spawns), live heartbeat (current
  phase), aggregate every 10 runs, alert on any invalid run.
- **Local watcher:** tails ledger + pulse; notifies on ALL DONE / STOP.
- **Disk (2026-10-03):** on user approval, off-experiment main-tree metrics
  cleaned — 73 probe/preflight/diagnostic run folders (~27.4 GB freed; free
  43 → 70 GB). Kept: official `rq3sat_camp_*` runs, all summary CSVs;
  `rq3tim_*` / `rq3snd_*` archives untouched. Docker: dangling prune only;
  rollback images retained. Cleanup script: `temp/rq3snd_cleanup_20261003.sh`.
- **Order amendment (2026-10-03, user-approved):** optional `wake_verify`
  runs (9) deferred to the campaign tail, contingent on a pre-tail gate scan
  (`/tmp/rq3snd_wv_prescan.py`: validity + floors + none-health + mechanism
  attestation across every preceding run; block skipped if the scan fails).
  Part-2 sequencer `/tmp/rq3snd_e_sequence2.sh` — adopted the in-flight
  run 11 without interrupting it; ledger/gate/pulse conventions unchanged.
- Reminder: damage magnitude is *the measurement* — it never fails a gate;
  only integrity/harness failures stop the chain (§2, §4.5 policy).

## Post-run analysis (after all runs)

- A2 damage tables: `readiness_robustness.py soundness-damage --run-dir <all>`
- A3 crossover: `readiness_robustness.py soundness-crossover`
- A4 hypothesis verdicts H-S1…H-S4 + base-requirements table
- `results.md` + `post_run_analysis.md` (only after the campaign)
