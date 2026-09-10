# RQ3 Robustness — Run Matrix

Parent plan: [`experiment_plan.md`](experiment_plan.md) · Host: `cloud-vm-rq3`
· New tag created from `rq3-sat-preflight-20260808` (tag name recorded in the
manifest at preparation time).

## Stage 0 — preflight (9 runs, calibration only)

| # | Label | Arm | Fault | Seed | Purpose |
| ---: | --- | --- | --- | ---: | --- |
| 1 | `rq3rob_none_hybrid_0` | hybrid | none | 4001 | archived P4 compatibility |
| 2 | `rq3rob_none_reconcile_0` | reconcile | none | 4002 | archived P4 compatibility |
| 3 | `rq3rob_none_event_only_0` | event_only | none | 4003 | hybrid-equivalence derivation |
| 4 | `rq3rob_loss_all_hybrid_0` | hybrid | loss_all | 4004 | fallback recovery smoke |
| 5 | `rq3rob_loss_all_event_only_0` | event_only | loss_all | 4005 | fallback-inertness proof |
| 6 | `rq3rob_loss_alt_event_only_0` | event_only | loss_alt | 4006 | aggregate preservation smoke |
| 7 | `rq3rob_restart_event_only_0` | event_only | restart | 4007 | restart observation |
| 8 | `rq3rob_restart_hybrid_0` | hybrid | restart | 4008 | restart observation |
| 9 | `rq3rob_restart_reconcile_0` | reconcile | restart | 4009 | restart observation |

Stage 0 verdicts: compatibility (1-3), fallback proof (4-6), and restart
observation (7-9, restart offset sweep 30/45/60 if needed). No Stage 0 run is
evidence.

## Stage 1 — loss campaign (54 runs, headline evidence)

Cells `none`, `loss_all`, `loss_alt` × arms × 6 blocks. Block seeds 4101-4106.
Arm order rotates per block (replicate r = rotation r):

| Block | Seed | Order |
| ---: | ---: | --- |
| 1 | 4101 | event_only, hybrid, reconcile |
| 2 | 4102 | hybrid, reconcile, event_only |
| 3 | 4103 | reconcile, event_only, hybrid |
| 4 | 4104 | event_only, reconcile, hybrid |
| 5 | 4105 | hybrid, event_only, reconcile |
| 6 | 4106 | reconcile, hybrid, event_only |

Labels: `rq3rob_{cell}_{arm}_{block}`, e.g. `rq3rob_loss_all_hybrid_2`.
Launch: `rq3rob_p1_01_launch_run.sh <arm> <fault> <label> <seed>`.
Per-run gates and the H1/H2/H3 decision rules are in the plan §3; direction
checks at blocks 3 (2-of-3) and 5 (3-of-5) with the diagnosed-cause rule.
A failed pre-registered direction is reported, never chased.

## Stage 2 — restart campaign (conditional, 18 runs)

Only if Stage 0 restart observations show a reproducible arm difference.
Arms × 6 blocks, seeds 4201-4206, restart at the locked offset. Launch:
`rq3rob_p1_01_launch_run.sh <arm> restart rq3rob_restart_<arm>_<block> <seed> <offset>`.
