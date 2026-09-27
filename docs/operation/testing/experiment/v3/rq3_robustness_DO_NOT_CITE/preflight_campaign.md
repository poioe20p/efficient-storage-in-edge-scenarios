# RQ3 Robustness — Preflight Campaign

**Host:** `cloud-vm-rq3` · **Plan:** [`experiment_plan.md`](experiment_plan.md)
· **Matrix:** [`run_matrix.md`](run_matrix.md)

## Stage 0.1 — frozen runtime

1. Confirm no experiment process, network setup, watchdog, or launcher is
   active on the VM.
2. Create the new tag from the approved source state and a detached worktree.
3. Run `rq3rob_p0_01_prepare_tag.py --worktree <path> --tag <name>` and verify
   the manifest.
4. Acquire the shared frozen image guard (`rq3lh_image_state.json`), exact edge
   image `638e3efdcdc5`, and the frozen `local_state_server` image.
5. Run `rq3rob_p0_03_preflight.sh`; all checks must pass.

## Stage 0.2 — compatibility and loss smoke

Run Stage 0 rows 1-6 in order with the standard reset cycle between labels.
Checkpoints per run:

- D3 snapshots, fault marker for loss rows, drop-log rows match mode
  (`mode=all` / `mode=alternate` in controller logs);
- hybrid loss_all: all admissions `probe_fallback`, dark median in [20,26] s;
- event_only loss_all: all rows `abandoned`, zero `probe_fallback` rows;
- event_only loss_alt: aggregate preservation in [0.3,0.7];
- compatibility rows reproduce the archived P4 timing/CPU envelope.

## Stage 0.3 — restart observation

Run Stage 0 rows 7-9. Verify:

- `docker logs -f` capture survives `docker restart osken`, else restart the
  capture or use a post-run `docker logs` dump and record the method;
- `admission_log_lan1.csv` survives the restart (writable layer); otherwise the
  campaign launcher must point `ADMISSION_LOG_PATH` at a host-persisted path;
- at least one backend is spawned-but-unadmitted at restart; else sweep the
  offset 30/45/60;
- classify outcomes with `readiness_robustness.py restart-observation`.

Pre-register the restart expectations from these observations before any
Stage 2 decision; no Stage 0 run is evidence.

## Stage 1 handoff

If all Stage 0 gates pass, the runner proceeds to the Stage 1 blocks per the
run matrix, writing one checkpoint row per run in
[`rq3rob_preflight_log.md`](rq3rob_preflight_log.md) and syncing artifacts
after each block.
