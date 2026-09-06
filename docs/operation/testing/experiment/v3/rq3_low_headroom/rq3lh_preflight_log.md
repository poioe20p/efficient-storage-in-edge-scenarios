# RQ3 Low-Headroom Preflight Checkpoint Log

Fill one row for every checkpoint. Allowed verdicts are `GO`, `STOP`, and
`DIAGNOSE`. A `STOP` or `DIAGNOSE` requires a resolution note before any later
stage proceeds. This template is not evidence until run artifacts are attached.

| Date | Stage | Checkpoint | Label/Scope | Result | Verdict | Resolution note |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-09-06 | 0.1 | archive inventory | all August pairs | 14/14 folders complete; snapshots byte-identical (md5 2ada9f3f07); no active run/watchdog/launcher on VM | GO | |
| | 0.2 | historical metric lock | 14 runs | | | |
| | 1.1 | detached worktree/tag identity | frozen tree | | | |
| | 1.2 | canonical P4 phases materialized | phases snapshot source | | | |
| | 1.3 | protected source hashes | controller/network/images | | | |
| | 2.1 | image state captured | Docker aliases | | | |
| | 2.2 | exact edge image verified | `638e3efdcdc5` | | | |
| | 2.3 | frozen local-state image | source/digest | | | |
| | 2.4 | bridge compatibility | direct/discovery 0.15 | | | |
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
