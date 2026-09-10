# RQ3 QoE-Consequence — Preflight Campaign

**Host:** `cloud-vm-rq3` · **Plan:** [`experiment_plan.md`](experiment_plan.md)
· **Matrix:** [`run_matrix.md`](run_matrix.md)

## Stage C0 — frozen runtime

1. Confirm no experiment process, network setup, watchdog, or launcher is
   active on the VM (robustness campaign is STOPPED; 19 valid runs retained).
2. Create the new tag from commit `852a8a3` and a detached worktree
   `~/rq3qoe_frozen`; verify `HEAD == 852a8a3` (mismatch = STOP).
3. Run `rq3qoe_p0_01_prepare_tag.py --worktree <path> --tag <name>` and verify
   the manifest (`.rq3qoe_frozen_manifest.json`).
4. Verify the shared frozen image guard (`rq3lh_image_state.json`) is acquired;
   the `852a8a3` lineage images are already verified — no rebuild expected.
5. Run `rq3qoe_p0_03_preflight.sh`; all checks must pass.

## Discovery stage (C1 → C2 → C3)

For each rung in `{0.13, 0.12, 0.11, 0.10, 0.09}` (descending), the runner:

1. Launches the 3 C1 `loss_all` runs (seed 5301) with
   `rq3qoe_p1_01_launch_run.sh <arm> loss_all rq3qoe_loss_all_<arm>_<NN> 5301 <rung>`
   and the standard per-run cycle (launch → snapshot verify → watchdog →
   gates), one checkpoint row per run in
   [`preflight_log.md`](preflight_log.md).
2. Runs `readiness_robustness.py qoe-screen --stage c1 --rung <rung> --seed
   5301 --run-dir <3 run folders> --out <...>`; all C1 gates must pass
   (integrity D1/D2/D3/quota/flow/driver, per-arm mechanism, pressure, controls
   `bad_rate ≤1 %` ∧ `slow_rate ≤2 pp` + baseline `bad_rate` ≤1 %).
   Ineligible → next rung.
3. Reads the C2 contrast from the same runs
   (`qoe-screen --stage c2 --c1-json <c1.json>`): lock iff eligible ∧ both
   axes bounded (event_only `bad ≤15 %` ∧ `slow ≤25 %`) ∧ (`Δ_timeout ≥5 pp`
   OR `Δ_slow ≥5 pp`); `lock_component` = slow when Δ_slow qualifies
   (slow-first precedence). Neither → next rung. Visible but unbounded →
   STOP-NULL (exit 3).
4. **On the first visible, bounded contrast: stop descending immediately**
   (user directive) and run C3 — 8 runs at 2 fresh seeds (5302, 5303) ×
   {3 arms `loss_all` + `event_only`×`none`}. C3 requires
   `--c1-json <c1.json>` and confirms the `lock_component` only: both seeds
   reproduce ≥5 pp on that axis + all C1 gates + both-axes boundedness +
   none-cell healthy (bad ≤1 % ∧ slow ≤2 pp). Monotone-gate failure
   (boundedness / none-cell health) → STOP-NULL (exit 3); contrast
   non-reproduction only → next rung.
5. On C3 lock: write `rq3qoe_quota_lock.json` and hand off to the E stage.

Checkpoints per discovery run:

- D3 snapshots, fault marker for loss rows, drop-log rows match mode
  (`mode=all` / `mode=alternate`) in controller logs;
- quota_snapshot `requested_edge_cpus == <rung>` and all compute containers
  match (dynamic and static);
- mechanism per arm: event_only loss_all 0 admitted / ≥2 abandoned per LAN /
  zero `probe_fallback`; hybrid loss_all all `probe_fallback`; reconcile all
  probe; ≥1 admit per LAN; no plateau scale-down;
- pressure: old-backend CPU median in [60, 85] %, p95 ≤95 % in the 30 s before
  first true-ready;
- pooled and per-LAN rate floors (≥5,000 pooled / ≥1,000 per LAN plateau;
  baseline pooled ≥100 / per-LAN ≥50 — amended 2026-09-07, artifact-sanity
  floor for the baseline ≤1 % read) and driver-clean cancel_rate <5 %;
- slow-share (amendment 2026-09-08): plateau pooled controls `slow_rate ≤2 pp`
  (threshold 1.0 s; timeouts slow unconditionally); none-cell `bad ≤1 %` ∧
  `slow ≤2 pp`; event_only boundedness `bad ≤15 %` ∧ `slow ≤25 %` at C2/C3;
  verdict exit codes `0` lock / `2` descend / `3` STOP-NULL; a legacy
  (pre-v2) `c1.json` fed to C2/C3 is a STOP (exit 3), never a fallback.

## Evidence stage (E) — locked rung only

If no rung qualifies: STOP with a NULL report (recorded, no E stage). On lock,
run the 54 E runs per the run matrix (blocks 1–6, seeds 5201–5206), one
checkpoint row per run, with direction checks at blocks 3 and 5 (per axis).
After block 6, the analyzer writes the H-Q1/H-Q1b/H-Q2/H-Q2b/H-Q3/H-Q4
verdicts via `readiness_robustness.py qoe-campaign` — overall pass =
`(H-Q1 ∧ H-Q2) ∨ (H-Q1b ∧ H-Q2b)` ∧ both boundedness ∧ H-Q3 ∧ H-Q4
(slow-share amendment 2026-09-08); `results.md` and the post-run analysis
follow.
