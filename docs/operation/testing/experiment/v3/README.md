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
| [`rq3/`](rq3/) | RQ3 **storage-replica benefit** at the locked config (rate 0.6, read-write mix, prefer_secondary): SG-4 benefit proven in probes (+17.5…+44.7 %, 4/4); propagation timing differential measured (direct 0 s vs discovery 1–6 s); consequence null per the v2/rq3 C9 precedent | **planned — NOT launched** (probes complete; tag `rq3-stor-v3-campaign-20260807`) |
| [`rq3_low_headroom/`](rq3_low_headroom/) | RQ3 readiness-admission low-headroom consequence follow-up: quota screens, fixed-window transient QoE, and separate event-source-absence robustness | **superseded 2026-09-06** — RQ3 reframed (readiness-admission coordination); bridge-stage artifacts retained |
| [`rq3_robustness/`](rq3_robustness/) | RQ3 readiness-admission robustness (reframed RQ3, Family 2): event-only vs hybrid vs reconciliation under controlled event loss and controller restart | **launched 2026-09-06…07; STOPPED by user decision after 19 valid runs** (frozen regime 0.28–0.69% failure — n=6 cannot show visible QoE degradation); restart findings characterized; QoE consequence moved to [`rq3_qoe/`](rq3_qoe/) |
| [`rq3_qoe/`](rq3_qoe/) | RQ3 QoE-consequence configuration discovery (reframed RQ3, Family 3): uniform-quota ladder down to a locked low-headroom config where readiness-event loss produces visible, bounded degradation in event_only while hybrid/reconcile stay healthy; certify at n=6/arm | **pre-registered 2026-09-07 (Approach A); slow-share axis added 2026-09-08; STOPPED and superseded 2026-09-08** — plateau failure rate structurally capped ~1.5 %; 7 runs retained as archive |
| [`rq3_timing/`](rq3_timing/) | RQ3 Timing — readiness-loss relief contrast (reframed RQ3, Family 4): arms unchanged, quota fixed 0.12, `compute_plateau` rate ladder {2.0, 2.5, 3.0}; slow-share headline with relief-completion tail gate; reproducible preflight signal (3 seeds, ≥7 pp median margin) gates the 36-run E stage | **pre-registered 2026-09-08 (user-approved); tooling implemented and validated locally; C0 tag pending** |
