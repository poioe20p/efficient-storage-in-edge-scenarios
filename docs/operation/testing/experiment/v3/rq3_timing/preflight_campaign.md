# RQ3 Timing — Preflight Campaign

**Host:** `cloud-vm-rq3` · **Plan:** [`experiment_plan.md`](experiment_plan.md)
· **Matrix:** [`run_matrix.md`](run_matrix.md)

## Stage C0 — frozen runtime

1. Confirm no experiment process, network setup, watchdog, or launcher is
   active on the VM (`rq3_qoe` family STOPPED; run 8 retained as archive).
2. Create the tag `rq3tim-preflight-<date>` from commit `852a8a3` and a
   detached worktree `~/rq3tim_frozen`; verify `HEAD == 852a8a3`
   (mismatch = STOP).
3. Copy `rq3tim_p0_01/02/03` + `rq3tim_p1_01_launch_run.sh` + the amended
   analyzer (`readiness_robustness.py`) into the frozen tree; run
   `rq3tim_p0_01_prepare_tag.py --worktree <path> --tag <name>`.
4. Verify the shared frozen image guard (`rq3lh_image_state.json`) is
   acquired; the `852a8a3` lineage images are already verified — no rebuild.
5. Run `rq3tim_p0_03_preflight.sh`; all checks must pass.

## Preflight stage (P1 → P2 → lock)

For each rate rung in `{2.0, 2.5, 3.0}` (ascending only when under-saturated):

1. Edit the frozen `phases.json` `compute_plateau` `rate_per_client` to the
   rung value (in place, canonical file — the launcher asserts it).
2. P1: launch the 3 `loss_all` arms (seed 5301) with
   `rq3tim_p1_01_launch_run.sh <arm> loss_all rq3tim_loss_all_<arm>_<NN> 5301 <rung>`;
   one checkpoint row per run in [`preflight_log.md`](preflight_log.md).
3. Screen: `readiness_robustness.py timing-screen --stage p1 --rate <rung>
   --seed 5301 --run-dir <3 folders> --out <p1.json>`. `descend` → next rung;
   `stop_null` → STOP-NULL; `candidate` → P2.
4. P2: seeds 5302 and 5303, 4 runs each (3 arms `loss_all` + `event_only`×
   `none`); screen each with `--stage p2`. A `stop_null` seed → STOP-NULL.
5. Lock: `timing-screen --stage lock --screen-json <p1.json> <p2a.json>
   <p2b.json> --out <lock.json> --lock-out rq3tim_preflight_lock.json`.
   `lock` → proceed to E. `marginal` → one extra seed 5304, re-lock with all
   four screens. `descend` → next rung. All rungs exhausted → NULL report.

Checkpoints per preflight run:

- phases rate matches the rung (launcher assert) and the run folder captures
  `phases_snapshot.json`;
- quota_snapshot `requested_edge_cpus == 0.12` and all compute containers
  match (dynamic and static);
- mechanism per arm: event_only loss_all 0 admitted / ≥2 abandoned per LAN /
  zero `probe_fallback` / mode=all; hybrid all `probe_fallback` ≥1/LAN;
  reconcile all probe ≥1/LAN; no plateau scale-down;
- V1 on the **hybrid** run (amendment 2026-09-08): old-backend CPU median
  ≥60 % in the 30 s before first true-ready — no p95 upper cap (escalation
  design makes pre-ready p95 spikes expected);
- floors (≥5,000 pooled / ≥1,000 per LAN plateau; baseline pooled ≥100 /
  per-LAN ≥50), driver-clean cancel_rate <5 %, baseline bad ≤1 % + http000=0;
- **relief completion**: hybrid ∧ reconcile plateau-tail (last 300 s) slow
  ≤2 pp; none-cell (P2, contract-v2 amendment 2026-09-08) bad ≤1 % full
  plateau ∧ plateau-tail slow ≤2 pp; event_only bounded slow ≤25 %.
- **onset-window co-primary** (contract v2, amendment 2026-09-08): onset
  `Δ_slow` over the first 150 s of `compute_plateau` ≥5 pp alongside the
  full-plateau `Δ_slow` ≥5 pp (P1 candidate / P2 confirm); the lock applies
  the ≥7 pp median power margin to both the full and the onset Δ.

## Evidence stage (E) — locked rate only

Run the 36 E runs per the run matrix (blocks 1–6, seeds 5201–5206), one
checkpoint row per run. After block 6, the analyzer writes the H-T1…H-T3
verdicts via `readiness_robustness.py timing-campaign`; `results.md` and the
post-run analysis follow.
