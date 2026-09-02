# research_q3 — Preflight Checkpoint Log

Fill one row per checkpoint executed. Verdicts: GO / STOP / DIAGNOSE.
STOP and DIAGNOSE entries require a resolution note before the campaign
continues.

| Date | Stage | Checkpoint | Run/Label | Result | Verdict | Resolution note |
| --- | --- | --- | --- | --- | --- | --- |
|  | 0.1 | release-gate selftest | — |  |  |  |
|  | 0.2 | compile + shell syntax | — |  |  |  |
|  | 0.3 | config integrity | — |  |  |  |
|  | 0.4 | CLI synthetic smoke | temp synthetic |  |  |  |
|  | 1.1 | VM repo synced + new files | — |  |  |  |
|  | 1.2 | code current on VM | — |  |  |  |
|  | 1.3 | importability in container | osken/osken_2 |  |  |  |
|  | 1.4 | sudo + docker | — |  |  |  |
|  | 1.5 | controller starts clean | — |  |  |  |
|  | 2.1 | both tiers spawn in storm | research_q3_cal_s1 |  |  |  |
|  | 2.2 | quarantine_begin in hold | research_q3_cal_s1 |  |  |  |
|  | 2.3 | recall at return onset | research_q3_cal_s1 |  |  |  |
|  | 2.4 | cycle-2 finalization | research_q3_cal_s1 |  |  |  |
|  | 2.5 | controllers alive throughout | research_q3_cal_s1 |  |  |  |
|  | 2.6 | artifacts present | research_q3_cal_s1 |  |  |  |
|  | 2.7 | CLI parse + recall_missed=0 | research_q3_cal_s1 |  |  |  |
|  | 2.8 | eviction non-ok=0, ghosts=0, D1 | research_q3_cal_s1 |  |  |  |
|  | 2.9 | timing vs pre-registered | research_q3_cal_s1 |  |  |  |
|  | 3.1 | off: no release log/evict files | research_q3_o1 |  |  |  |
|  | 3.2 | immediate: end-only + eviction logs | research_q3_i1 |  |  |  |
|  | 3.3 | drained: begin/end pairs | research_q3_d1 |  |  |  |
|  | 3.4 | per-run gates (3 runs) | o1/i1/d1 |  |  |  |
|  | 3.5 | cross-run CLI sanity | cal+o1+i1+d1 |  |  |  |
|  | 4 | per-run gate after each of 28 | research_q3_* |  |  |  |
|  | 4 | early direction (run 3/arm) | research_q3_* |  |  |  |
|  | 4 | arm consistency (run 6/arm) | research_q3_* |  |  |  |
|  | 4 | cross-seed sensitivity | x1 runs |  |  |  |
|  | 4 | final campaign verdict | all |  |  |  |
