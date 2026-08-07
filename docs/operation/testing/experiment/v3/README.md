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
