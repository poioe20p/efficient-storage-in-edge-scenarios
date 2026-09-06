# RQ3 Low-Headroom Preflight Runbook

**Status:** preparation only. Do not execute this runbook during implementation.

**Host:** `cloud-vm-rq3`  
**Frozen tag:** `rq3-sat-preflight-20260808`  
**Experiment folder:** `docs/operation/testing/experiment/v3/rq3_low_headroom/`

## Stage 0 - Archive Inventory

Read-only checks before any image or worktree change:

1. Confirm the September release campaign is stopped and no run, Docker setup,
   watchdog, or launcher process is active.
2. Locate all 14 August `rq3sat_camp_direct_1..7` and
   `rq3sat_camp_disc_1..7` folders.
3. Require `client_requests.csv`, `admission_log_lan{1,2}.csv`,
   `service_logs/`, `phases_snapshot.json`, `controller_env_snapshot.env`,
   `run_status.json`, and the window logs in every folder.
4. Run the historical analyzer in lock mode. Require all seven pairs. Write
   `rq3lh_metric_lock.json`; otherwise STOP before runtime preparation.

## Stage 1 - Detached Frozen Worktree

1. Create a detached worktree at tag commit `55c22fbf...` outside the dirty main
   checkout.
2. Overlay only the approved `rq3lh_*` scripts, analyzer, delta env, and docs
   helper files.
3. Run `rq3lh_p0_01_prepare_frozen.py` in dry-run mode, then materialize the
   historical P4 profile into the detached worktree's canonical `phases.json`.
4. Record `.rq3lh_frozen_manifest.json` with tag/controller identities,
   protected-path hashes, phase hash, and arm-env hashes.
5. Verify that protected runtime paths are identical to the tag. A mismatch is
   STOP, not a repair opportunity.

## Stage 2 - Image Guard and Bridge

1. Record current `edge_server:latest` and `local_state_server:latest` image
   IDs in `rq3lh_image_state.json` and create backup tags.
2. Verify the exact `edge_server` image prefix `638e3efdcdc5`.
3. Build/tag `local_state_server:rq3lh-frozen` from the detached tag source.
4. Acquire the image guard without deleting any image. The launcher must refuse
   to run unless the guard is recorded as acquired.
5. Run the two bridge labels at quota 0.15 and seed 3001. The bridge is a
   compatibility gate only. STOP on any integrity, CPU, readiness-separation,
   or `abs(D_bridge) <= max(H,P)` failure. Evaluate it with the analyzer
   `bridge` subcommand, passing the two run folders and the metric lock.

## Stage 3 - Quota Screens

Run one at a time with the standard reset cycle and record a checkpoint after
each:

1. `rq3lh_screen_q12_1`, seed 3099, quota 0.12.
2. `rq3lh_screen_q10_1`, seed 3099, quota 0.10.
3. `rq3lh_screen_q10_2`, seed 3100, quota 0.10.
4. `rq3lh_screen_q12_2`, seed 3100, quota 0.12.

Use only the capacity-screen command. It must not emit readiness-window p95,
timeout/failure, or legacy gap outcomes. Both runs at a quota must pass before
that quota can qualify. Select 0.12 first if both q12 runs pass; otherwise
select 0.10 if both q10 runs pass. Write `rq3lh_quota_lock.json` and stop on
split/no qualifying result. Pass `--quota` to the screen command and treat a
non-zero exit as screen failure. Confirm `quota_snapshot.json` exists in each
screen run folder before invoking the screen.

## Stage 4 - Main and Event-Absence Preflight

Run the reversed blocks with a complete reset between every label:

```text
seed 3101: direct_1 -> discovery_1 -> event_absent_1
seed 3102: event_absent_2 -> discovery_2 -> direct_2
```

Apply per-run gates before the next label. Apply the paired primary GO rule
only after both direct/discovery runs for a seed are complete. Event-absence
rows are exempt from normal-direct event-fraction gates and use the separate
fallback contract. Analyze event absence with the `event-absence` subcommand
and pass the two same-seed normal direct folders as `--control-run`.

## Stage 5 - Sync and Restore

1. Copy run folders, snapshots, lock files, and analysis outputs to the local
   experiment folder.
2. Confirm every artifact is readable before cleanup.
3. Restore the original Docker image aliases from `rq3lh_image_state.json` and
   verify their IDs. Never delete images.
4. Keep the detached worktree until all analysis inputs are secured.
5. Write `results.md` and `post_run_analysis.md` only after the analyzer has
   produced the preflight and event-absence verdicts.

## Stop Boundary

The runner stops after Stage 5. The conditional n=6/arm campaign requires a
separate approval and a new run matrix; it is never launched by this runbook.
