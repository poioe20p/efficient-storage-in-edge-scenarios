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
|---|---|---|
| [`rq2/`](rq2/) | RQ2 bottleneck-aware scaling at the locked storage-bind config | **planned — NOT launched** (preflight pending) |
