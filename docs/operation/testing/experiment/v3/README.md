# Experiment v3 — Storage-Bind Rebased Campaigns

**v3** hosts experiment campaigns rebased on the **storage-bind locked
configuration** (2026-08-07, tag `rq2-v3-campaign-20260807`). It exists because
the v2 RQ2 campaign could not demonstrate a storage scale-up benefit: its
data-bound episode (rate 1.5, mixed ops) never made storage the bottleneck, and
the serving-path read-spread mechanism (pool 12, `wsm` selection) pinned reads
to the static primaries so replica scale-up produced no relief.

The probe series that solved this — and the resulting locked config — are
recorded in [`rq2/storage_bind_probe_record.md`](rq2/storage_bind_probe_record.md).
Historical v1/v2 records remain in [`../v2`](../v2) and are **not** modified by
v3.

| Subfolder | Campaign | Status |
| --- | --- | --- |
| [`rq2/`](rq2/) | RQ2 bottleneck-aware scaling at the locked storage-bind config | **planned — NOT launched** (preflight pending) |
| [`rq1/`](rq1/) | RQ1 telemetry delivery semantics on the fixed platform (flow-idle fix + re-anchored workload; Phases 0–1 required before the campaign) | **planned — NOT launched** |
| [`rq3/`](rq3/) | RQ3 **compute-saturation campaign** (direct vs discovery at config P4; 14 runs, n=7/arm, seeds 3001–3007) plus the storage-replica extension records | **compute campaign complete** (`results.md`, `post_run_analysis.md`, `analysis/`) — primary mechanism/relief evidence; storage extension **closed — SG-4 null, not carried** |
| [`rq3_low_headroom_DO_NOT_CITE/`](rq3_low_headroom_DO_NOT_CITE/) | RQ3 readiness-admission low-headroom consequence follow-up (superseded plan) | **superseded 2026-09-06 — archive only, do not cite** (never launched; bridge-stage artifacts retained) |
| [`rq3_robustness_DO_NOT_CITE/`](rq3_robustness_DO_NOT_CITE/) | RQ3 readiness-admission robustness (Family 2) — exploratory, superseded | **STOPPED after 19 valid runs — archive only, do not cite** (frozen regime 0.28–0.69 % failure); family line continued as Family 3, then Family 4 |
| [`rq3_qoe_DO_NOT_CITE/`](rq3_qoe_DO_NOT_CITE/) | RQ3 QoE-consequence discovery (Family 3) — superseded by Family 4 | **STOPPED and superseded 2026-09-08 — archive only, do not cite** (plateau failure rate structurally capped ~1.5 %; 7 runs retained) |
| [`rq3_timing/`](rq3_timing/) | RQ3 Timing — readiness-loss relief contrast (Family 4): 3 admission arms × 2 fault cells × 6 blocks (36 runs, seed-matched; rate 2.0, quota 0.12); slow-share headline with relief-completion tail gate | **completed 2026-09-09/10** — certified consequence evidence (overall pre-registered pass = false; H-T1 met; see `results.md`) |

**RQ3 evidence map (2026-09-26):** official evidence = [`../v2/rq3/`](../v2/rq3/) (original fixed-image campaign — definitive mechanism) + [`rq3/`](rq3/) (saturation campaign) + [`rq3_timing/`](rq3_timing/) (fault consequence). Stopped or superseded families — `rq3_robustness`, `rq3_qoe`, `rq3_low_headroom`, and the legacy `research_q3` under the parent folder — are suffix-renamed `_DO_NOT_CITE` (archive only; never cited as results).
