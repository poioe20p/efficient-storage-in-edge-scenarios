# RQ2 — Storage-Bind Probe Record (basis for v3)

The probe series that produced the locked storage-bind config now used by the
v3 RQ2 campaign. Runs: `S2a`, `P0`, `F1a`, `F4a`, `F4b` (2026-08-07,
`cloud-vm-rq2`). Historical D/W/S probes are recorded in the v2
`series_d_storage_bind_probe_plan.md`.

## 1. Problem

In the v2 campaign, storage scale-up produced no user-visible benefit. Root
cause (confirmed in code + data): the serving-path read path pinned edge
connections to the storage primaries (`directConnection=True` + data-VIP
per-connection pinning + small edge pool), so added replicas served ~nothing.

## 2. Probe progression (one variable at a time)

| Cell | Change | Result |
|---|---|---|
| `S2a` | anchor (pool 12, stor 0.10, rate 7.0) | storage binds (prims 100 %) but 0 spread → 18.0 % TO, p50 43 s |
| `P0` | pool 12 → 48 | **spread fixed** (3+ backends); db_ms −82 %; still 15.8 % TO |
| `F1a` | storage 0.10 → 0.15 | DB healthy (13.6 ms, 50/50 spread) but rate-7 pre-spawn backlog → 18.3 % TO |
| `F4a` | rate 7.0 → 5.0 | ✅ **PASS 1.84 % TO** — bind→relief signature |
| `F4b` | repro (seed 43) | ✅ **PASS 0.04 % TO** — reproduced |

## 3. Locked config (F4a/F4b)

`edge 1.20 / storage 0.15 / rate 5.0 / EDGE_MONGO_MAX_POOL_SIZE=48 /
content_lookup 0.9 + feed_ranking 0.1 / sf_db arm / pool-48 read spread`.

Bind→relief signature (both seeds): pre-add p50 ~0.6–1.9 s + timeouts; after the
replica joins, p50 drops to ~0.05–0.6 s and timeouts → 0; storage CPU at fire
66–74 % → ~7 % post-relief.

## 4. Requirements verdict (testing_requirements.md)

Both `F4a` and `F4b` pass every hard gate: **B2** (latency drop + storage-CPU
relief, reproduced), **M1** (1 storage add/LAN), **M2** (added secondary serves
~50 % of reads), **V1** (T_db/storage CPU rising), **I1** (~39 k offered/LAN),
**I2** (distinct outcome classes), **D1** (0 × NotPrimary*), **D2** (exit 0, no
restart), **D3** (snapshots present). Flags: F1 continuous telemetry, F2 LAN
symmetry ≤ 1.05×. Compute benefit (**B1**) was separately verified on the v2
`cb_1`/`cb_2` runs (static-edge CPU 66–81 % → 47–62 %, timeouts → 0).

## 5. Findings

1. **Read spread requires the pool to keep opening connections to new
   replicas** — pool 48 + WSM selection achieves it at the locked rate; pool 12
   saturates and pins to the initial backends.
2. **Rate must sit in the pressure band, not overload**: rate 7.0 builds a
   pre-spawn backlog that never drains in the episode; rate 5.0 (~92 % of
   single-node capacity) gives a small deficit that drains in seconds after the
   replica joins.
3. **Storage 0.15 is the per-op-fast binding point**: 0.10 keeps the DB slow
   all episode; 0.08 starves per-op (unrelievable). At 0.15, one node binds
   (~66–74 %) and two nodes fully relieve.
