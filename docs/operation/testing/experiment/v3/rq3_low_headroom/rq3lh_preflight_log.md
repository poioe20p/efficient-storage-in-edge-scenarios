# RQ3 Low-Headroom Preflight Checkpoint Log

Fill one row for every checkpoint. Allowed verdicts are `GO`, `STOP`, and
`DIAGNOSE`. A `STOP` or `DIAGNOSE` requires a resolution note before any later
stage proceeds. This template is not evidence until run artifacts are attached.

| Date | Stage | Checkpoint | Label/Scope | Result | Verdict | Resolution note |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-09-06 | 0.1 | archive inventory | all August pairs | 14/14 folders complete; snapshots byte-identical (md5 2ada9f3f07); no active run/watchdog/launcher on VM | GO | |
| 2026-09-06 | 0.2 | historical metric lock | 14 runs | H=0.180 s, P=0.010 s, 7/7 pairs, seeds 3001-3007 verified from open_loop_schedule.json; amended plateau-eligible anchor (§3.1); per-LAN values + artifact/analyzer hashes in lock | GO | H is descriptive/exploratory only (D values inspected during endpoint development); lock synced locally |
| 2026-09-06 | 1.1 | detached worktree/tag identity | frozen tree | `~/rq3lh_frozen` detached at 55c22fbf; tag fetched to VM via bundle | GO | |
| 2026-09-06 | 1.2 | canonical P4 phases materialized | phases snapshot source | P4 profile (service_pressure=1.0) materialized from campaign-ready source; manifest phase hash recorded | GO | |
| 2026-09-06 | 1.3 | protected source hashes | controller/network/images | 70 protected files hashed; diff vs tag empty; static preflight checks PASS | GO | |
| | 2.1 | image state captured | Docker aliases | edge latest=638e3efdcdc5; local latest=de40e99c159d; backups edge/local_state:rq3lh-backup | GO | |
| | 2.2 | exact edge image verified | `638e3efdcdc5` | `edge_server:latest` already the frozen August image (unchanged by September) | GO | |
| | 2.3 | frozen local-state image | source/digest | built 60f3d8a34dc2 from tag source; smoke OK (pyzmq 27.2.0); `latest` switched to frozen; untracked runtime `osken-controller.env` (Jul-6, pre-August) overlaid with sha256 3ba06c1f recorded in manifest+state | GO | |
| | 2.4 | bridge compatibility | direct/discovery 0.15 | direct completed exit=0 (2 adds/LAN, event admits); discovery launched with mid-run quota capture | RUNNING | launcher quota-write fixed (sudo -n + no-overwrite) after direct's post-run PermissionError |
| | 3.1 | quota screen | `rq3lh_screen_q12_1` | | | |
| | 3.2 | quota screen | `rq3lh_screen_q10_1` | | | |
| | 3.3 | quota screen | `rq3lh_screen_q10_2` | | | |
| | 3.4 | quota screen | `rq3lh_screen_q12_2` | | | |
| | 3.5 | quota lock | selected quota | | | |
| | 4.1 | main/absence block | seed 3101 | | | |
| | 4.2 | main/absence block | seed 3102 | | | |
| | 4.3 | primary GO decision | both seeds | | | |
| | 5.1 | artifact sync | local copy | | | |
| | 5.2 | image alias restoration | original IDs | | | |
| | 5.3 | preflight verdict | final | | | |
