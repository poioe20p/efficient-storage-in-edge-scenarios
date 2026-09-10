# RQ3 Timing — Run Matrix

Parent plan: [`experiment_plan.md`](experiment_plan.md) · Host: `cloud-vm-rq3`
· Frozen base: commit `852a8a3`; tag `rq3tim-preflight-<date>` recorded in the
manifest at preparation time.

Launch: `rq3tim_p1_01_launch_run.sh <arm> <fault> <label> <seed> <rate>`.
The launcher **asserts** that the frozen `phases.json` `compute_plateau`
rate equals `<rate>` (mismatch = STOP). Quota is fixed at 0.12 inside the
launcher. Run folders: `metrics/<timestamp>_<label>`; labels globally unique.

## Label convention

- **Preflight** runs use block ordinals **50, 51, …** assigned sequentially
  (append-only in [`preflight_log.md`](preflight_log.md)):
  `rq3tim_<cell>_<arm>_<NN>`.
- **Evidence (E)** runs use blocks **1–6**: `rq3tim_<cell>_<arm>_<block>`.
  Preflight ordinals ≥50 never collide with E block numbers 1–6.

## Preflight stage (per rate rung, ladder 2.0 → 2.5 → 3.0)

One rung at a time; the first rung whose lock rule passes is locked — the
preflight signal is reproducible across 3 seeds with a ≥7 pp median margin
before any E run is launched. Rung recipes (ordinals continue across rungs):

| Stage | Seed | Runs | Labels (first rung 2.0; ordinals continue later) | Purpose |
| --- | ---: | --- | --- | --- |
| P1 | 5301 | 3 | `rq3tim_loss_all_event_only_50`, `rq3tim_loss_all_hybrid_51`, `rq3tim_loss_all_reconcile_52` | discovery screen + Δ_slow read |
| P2 | 5302 | 4 | `rq3tim_loss_all_event_only_53`, `rq3tim_loss_all_hybrid_54`, `rq3tim_loss_all_reconcile_55`, `rq3tim_none_event_only_56` | reproducibility seed A |
| P2 | 5303 | 4 | `rq3tim_loss_all_event_only_57`, `rq3tim_loss_all_hybrid_58`, `rq3tim_loss_all_reconcile_59`, `rq3tim_none_event_only_60` | reproducibility seed B |
| P2m | 5304 | 4 | ordinals 61–64 | marginal-only extra seed |

Screens: `readiness_robustness.py timing-screen --stage p1|p2 --rate <rung>
--seed <seed> --run-dir <folders> --out <json>`; lock:
`--stage lock --screen-json <p1.json> <p2a.json> <p2b.json> [<p2c.json>]
--out <lock.json> --lock-out rq3tim_preflight_lock.json`.
Verdict exit codes: `0` lock/candidate/confirm · `2` descend/marginal ·
`3` STOP-NULL. Lock writes `rq3tim_preflight_lock.json` and gates E.

Ladder discipline: ascend only when V1 under-saturated; never ascend past
driver-unclean or p95 >95 %; midpoint rate 2.25 only when 2.0 under-saturates
and 2.5 breaks driver-clean. No qualifying rung by 3.0 → NULL report.

## Evidence stage — E (36 runs, only after the lock file)

Cells `none`, `loss_all` × arms × 6 blocks at the **locked** rate. Block
seeds 5201–5206. Arm order rotates per block; within a block cells run
arm-major in order none → loss_all.

| Block | Seed | Order |
| ---: | ---: | --- |
| 1 | 5201 | event_only, hybrid, reconcile |
| 2 | 5202 | hybrid, reconcile, event_only |
| 3 | 5203 | reconcile, event_only, hybrid |
| 4 | 5204 | event_only, reconcile, hybrid |
| 5 | 5205 | hybrid, event_only, reconcile |
| 6 | 5206 | reconcile, hybrid, event_only |

Labels: `rq3tim_{cell}_{arm}_{block}`, e.g. `rq3tim_loss_all_hybrid_2`.
Analyze with `readiness_robustness.py timing-campaign` after block 6.
A failed pre-registered direction or boundedness component is reported,
never chased.
