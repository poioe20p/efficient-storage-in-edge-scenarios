# RQ2 v3 — Bottleneck-Aware Scaling at the Storage-Bind Config

Status: **PLANNED — NOT LAUNCHED (2026-08-07).**
Code pinned at git tag **`rq2-v3-campaign-20260807`** (commit `5b3cefa`).

## 1. Context

The v2 RQ2 campaign was aborted at run 13 (`rq2_cf_cb_3`, 2026-08-06) because
the data-bound cells could not show a storage scale-up benefit: at the v2
episode (rate 1.5, mixed ops, edge 0.30 / storage 0.15, pool 12) storage never
bound, and reads stayed pinned to the static primaries so added replicas served
nothing. The probe series (`S2a`, `P0`, `F1a`, `F4a`, `F4b` — see
[`storage_bind_probe_record.md`](storage_bind_probe_record.md)) found a config
where storage binds, reads spread to replicas, and replica scale-up produces a
clear user-visible benefit, reproduced across two traffic seeds and passing all
`testing_requirements.md` hard gates.

**v3 rebases the RQ2 campaign on that locked config.** Compute-bound cells keep
the B1-validated v2 config; data-bound cells use the new locked config.

## 2. Objective

Demonstrate, per `testing_requirements.md`:

- **B1 — compute scale-up benefit** (cb cells): latency drop OR edge-CPU relief
  after a compute add, reproduced.
- **B2 — storage scale-up benefit** (db cells): latency drop OR storage-CPU
  relief after a storage add, reproduced.
- **M1/M2** — the claimed tier scales (per LAN) and added nodes serve requests.
- **V1** — the intended bottleneck is evidenced in telemetry (cb: edge CPU
  rising; db: `T_db`/storage CPU rising).
- **I1/I2, D1–D3, F1/F2** — interpretability, integrity, provenance, symmetry.

Policies under test (the RQ2 action-selection axis): `fixed_compute_first`
(cf), `fixed_storage_first` (sf), `bottleneck_aware` (ba) × episodes
compute-bound (cb) / data-bound (db).

## 3. Locked configuration (tag `rq2-v3-campaign-20260807`)

| Cell | Arm env | Phases file | EDGE_CPUS | STORAGE_CPUS | Pool |
|---|---|---|---|---|---|
| `cf_cb` | `rq2_compute_first.env` | `phases_rq2_compute_bound.json` | 0.15 | 0.08 | 48 |
| `cf_db` | `rq2_compute_first.env` | `phases_rq2_data_bound.json` | **1.20** | **0.15** | 48 |
| `sf_cb` | `rq2_storage_first.env` | `phases_rq2_compute_bound.json` | 0.30 | 0.15 | 48 |
| `sf_db` | `rq2_storage_first.env` | `phases_rq2_data_bound.json` | **1.20** | **0.15** | 48 |
| `ba_cb` | `rq2_bottleneck_aware.env` | `phases_rq2_compute_bound.json` | 0.15 | 0.08 | 48 |
| `ba_db` | `rq2_bottleneck_aware.env` | `phases_rq2_data_bound.json` | **1.20** | **0.15** | 48 |

`EDGE_MONGO_MAX_POOL_SIZE=48` is set in `tools/run_rq2_campaign.py` `BASE_ENV`
(static edges) **and** in all three arm envs (dynamic edges). Data-bound phase
episode: rate 5.0, mix `content_lookup 0.9 / feed_ranking 0.1`.

## 4. Design

- **6 cells × 6 replicates = 36 runs**, order per
  [`counterbalance_order_v2.csv`](counterbalance_order_v2.csv) (6 blocks of 6
  cells, randomized per block).
- Traffic seed `RANDOM_SEED=42` fixed; block seeds 2001–2006 (order recorded in
  the CSV).
- Open-loop driver, `CLIENTS=24`, `CURL_MAX_TIME=300`, `INFLIGHT_WINDOW=1024`,
  `DRAIN_S=30`, `CONTENT_ITEMS=3000`, `USERS=100`, `DATA_SEED=42`.
- Phase files (canonical, edited in place under `source/scripts/testing/
  phases_override/`):
  - **data-bound**: baseline 30 s → `data_bound_episode` 480 s (rate 5.0) →
    recovery_gap 60 s → demand_drop 240 s.
  - **compute-bound**: baseline 60 s → `compute_bound_episode` 600 s (rate 1.5,
    `service_pressure 1.0`) → recovery_gap 120 s → demand_drop 420 s.

## 5. Preflight (2 runs, before the 36)

Two `sf_db` runs at the **same** traffic seed (block seed 2001) to prove
same-seed reproducibility of the locked data-bound config before committing to
36 runs. Gates: both must pass the full `testing_requirements.md` check (B2,
M1, M2, V1, I1, I2, D1–D3, F2) and agree in direction/magnitude (both
timeout ≤ 5 %, both show storage bind → relief). Preflight run labels:
`rq2_sf_db_preflight_1`, `rq2_sf_db_preflight_2`.

## 6. Gates (pre-registered magnitudes)

- Health: timeout % ≤ 5 % per run (target ≈ 0 %).
- Benefit (B1/B2): ≥ 10 % drop in episode p50 or p95 latency after the first
  add in the claimed tier, OR clear tier-CPU relief (post-add CPU < 0.6 ×
  pre-add CPU); direction consistent across replicates.
- Mechanism (M1): ≥ 1 add in the claimed tier per LAN during the episode.
- Usability (M2): each added node serves ≥ 1 completed request.
- Validity (V1): storage fires show `cpu_s` rising (db) / edge CPU rising (cb).
- Demand (I1): ≥ 5 000 completed requests per LAN in the episode.
- Integrity: D1 0 × NotPrimary*, D2 no restart/crash, D3 snapshots present.

## 7. Provenance

- Campaign code pinned at tag `rq2-v3-campaign-20260807` (commit `5b3cefa`):
  `tools/run_rq2_campaign.py`, `docs/operation/testing/experiment/v3/rq2/env/*`
  (3 arm envs), `source/scripts/testing/phases_override/phases_rq2_data_bound
  .json`, `phases_rq2_compute_bound.json`.
- At launch the tagged files are synced to `cloud-vm-rq2` and md5-verified; the
  controller/edge source is synced and its hashes recorded in each run folder.
