# RQ2 v3 — Run Matrix

Part of [`experiment_plan.md`](experiment_plan.md). Per-run configuration for
the v3 RQ2 campaign (storage-bind locked config, tag `rq2-v3-campaign-20260808`).

> **Status: COMPLETED — all 36 runs finished (2026-08-09, 07:37 UTC).**
> Preflight complete (P1e/P2/P3/P3b/P4/P5; cb P6/P7 PASS). All 36 v3 campaign
> runs completed via the orchestrator (tag `rq2-v3-campaign-20260808`;
> blocks 1–6, per-run seeds 42/43). **Valid replicate pool: 34 runs**
> (36 − `ba_db_2` − `cf_db_5`). `ba_db_2` (run 7) excluded — harness incident
> (MEMCG OOM under the old 256 MB cap; see
> [`ba_db_2_incident.md`](ba_db_2_incident.md)). `cf_db_5` (run 25) excluded —
> **second MEMCG OOM incident (2 compute-node kills @ 512 MB cap, D2 hard-gate
> violation; same mechanism as `ba_db_2`; see `results.md` §Root Causes)**.
> `EDGE_MEMORY` 256m→512m for runs 15+; the ba_db reruns (3/4/5/6) are clean.
> Config split: runs 1–14 at 256m, 15–36 at 512m. Per-run analysis + cell-level
> B2/B1 synthesis + comparison graphs + `results.md` + `post_run_analysis.md`
> complete (analyzer, 2026-08-09). (Attempt 1 aborted — v2-label collision;
> fixed, relaunched.)
>
> **Amendment (2026-08-12) + rerun complete (2026-08-13):** the `sf_cb` cell was
> re-run at the binding compute config (`EDGE_CPUS 0.15 / STORAGE_CPUS 0.08`)
> to resolve the launch-allocation confound of the original cell (`0.30 / 0.15`).
> The 6-run rerun completed 2026-08-13 (seeds 42×5 + 43; all exit 0, D1/D2/D3
> clean); see [`sf_cb_rerun_plan.md`](sf_cb_rerun_plan.md) and `results.md`
> (v2 timeline row). P8 (`rq2_sf_cb_preflight_1`) resolved: Branch A (storage
> fires on cb, 2 on lan2), quarantined in `_superseded_pilot/`. Rerun verdict:
> no user-visible wrong-action cost at the tested intensity (DF 8.7–9.1 %);
> resource-waste + high-compute-utilization-without-relief framing.

## 1. Per-cell configuration

| Cell | Env file (launch source `{REPO}/rq2_env/`) | Phases file | EDGE_CPUS | STORAGE_CPUS | Pool | Verified by |
|---|---|---|---|---|---|---|
| `cf_cb` | `rq2_compute_first.env` | `phases_rq2_compute_bound.json` | 0.15 | 0.08 | 12 | cb_1/cb_2 (B1, v2 record) |
| `cf_db` | `rq2_compute_first.env` | `phases_rq2_data_bound.json` | **1.20** | **0.15** | **12** | F4a/F4b (B2) + preflight P4 |
| `sf_cb` | `rq2_storage_first.env` | `phases_rq2_compute_bound.json` | **0.15**¹ | **0.08**¹ | 12 | rerun complete 2026-08-13 ([sf_cb_rerun_plan.md](sf_cb_rerun_plan.md)) |
| `sf_db` | `rq2_storage_first.env` | `phases_rq2_data_bound.json` | **1.20** | **0.15** | **12** | F4a/F4b + preflight P1/P2/P3 |
| `ba_cb` | `rq2_bottleneck_aware.env` | `phases_rq2_compute_bound.json` | 0.15 | 0.08 | 12 | v2 Series-C |
| `ba_db` | `rq2_bottleneck_aware.env` | `phases_rq2_data_bound.json` | **1.20** | **0.15** | **12** | F4a/F4b (db config) + preflight P5 |

¹ 2026-08-12 amendment: the original `sf_cb` cell launched at `0.30 / 0.15`
   (a confound — compute provisioned above its binding point); the rerun uses
   `0.15 / 0.08` per [sf_cb_rerun_plan.md](sf_cb_rerun_plan.md). The launch
   env is `{REPO}/rq2_env/` (reserve=1); the `~/rq2_env/` copy is STALE
   (reserve=0) and must not be used (see `sf_cb_rerun_plan.md` §5).

Pool is per-cell (shell, `tools/run_rq2_campaign.py` `CELLS`): 12 for all
cells (db cells locked 2026-08-08 — P3/P3b evidence: stronger B2 p95 leg
0.42×/0.49× vs 0.63×/0.77× at pool 48, lower timeout 0.068–0.074 %). Arm
envs (dynamic edges) keep `EDGE_MONGO_MAX_POOL_SIZE=12`.
Shared: `EDGE_MONGO_READ_PREFERENCE=secondaryPreferred`,
`VIP_DATA_PER_CONNECTION_FLOWS=1`, `WAN_RTT_MS=185`, `OVERLOAD_CPU_PCT=30`,
`OVERLOAD_PEAK_LATENCY_MS=2000` (D3 overload-label re-anchor for RQ2, fix 8 —
see `experiment_plan.md` §3). `EDGE_MEMORY=512m` (2026-08-08, was 256m —
ba_db_2 MEMCG OOM; runs 1–14 at 256m, runs 15+ at 512m; see
`ba_db_2_incident.md`).
Readiness gate (D9a) on in all three arm envs (`READINESS_PROPAGATION=direct`,
`EDGE_APP_READY_EVENT=1`).

## 2. Preflight (P1–P8; P8 still 🔄 QUEUED)

(P1 was iterated through sub-labels during preflight, ending at P1e; P3 has
the sub-run P3b — the campaign banner's "P1e/P2/P3/P3b/P4/P5" refers to
those sub-labels. P8 was queued pre-campaign and remains QUEUED — see
[sf_cb_rerun_plan.md](sf_cb_rerun_plan.md) §6.2.)

| # | Label | Cell | Seed | Purpose |
|---|---|---|---|---|
| P1 | `rq2_sf_db_preflight_1` | `sf_db` | 2001 | storage bind → relief + **scale-down** at locked config |
| P2 | `rq2_sf_db_preflight_2` | `sf_db` | 2001 | same-seed reproducibility |
| P3 | `rq2_sf_db_preflight_pool12` | `sf_db` @ pool 12 | 2001 | pool-isolation diagnostic (is pool 48 required?) |
| P4 | `rq2_cf_db_preflight_1` | `cf_db` | 2001 | wrong-action sanity (suppressed storage, no collapse) |
| P5 | `rq2_ba_db_preflight_1` | `ba_db` | 2001 | classifier picks storage; benefit ≈ P1 |
| P6 | `rq2_ba_cb_preflight_1` | `ba_cb` | 2001 | v3 cb validation — B1 direction, compute scaling fires (PASS) |
| P7 | `rq2_cf_cb_preflight_1` | `cf_cb` | 2001 | v3 cb validation — B1 direction, compute scaling fires (PASS) |
| P8 | `rq2_sf_cb_preflight_1` | `sf_cb` | 2001 | does storage fire on service_pressure-1.0 cb (wasted-sync vs does-nothing); no collapse — **now a rerun-support probe at 0.15/0.08** (the 36-run campaign completed 2026-08-09 with P8 queued) | 🔄 QUEUED |

Pass = `experiment_plan.md` §5–§6 (P1/P2: full req-check + scale-down;
P4: timeout ≤ 10 %; P5: storage fires + benefit). P6/P7 (2026-08-08) validate
compute-bound arms under the v3 shell config (pool 12, OVERLOAD 30/2000,
reserve enabled, p5fix classifier) — both PASS B1 by a wide margin. P8
(2026-08-08) was queued to close the sf_cb gap (readiness review): on
`service_pressure 1.0` the storage signal may never fire — the probe tells
whether sf_cb is a "wasted-sync" or "does-nothing" cell. It was superseded as
a pre-campaign gate (the 36-run campaign completed 2026-08-09 with P8 queued)
and is now a rerun-support probe at 0.15/0.08 per `sf_cb_rerun_plan.md` §6.2.

## 3. Main matrix (36 runs)

Executed in counterbalanced order from
[`counterbalance_order_v2.csv`](counterbalance_order_v2.csv): 6 blocks × 6
cells, run labels `rq2_<cell>_1..6`. The CSV `block` column (1–6) is
counterbalance ordering only — `RANDOM_SEED` comes solely from `traffic_seed`
(stale v2-era "block seeds 2001–2006" wording removed 2026-08-08). Traffic
seed per run from the CSV `traffic_seed` column: `RANDOM_SEED=42` for `_1.._5`,
43 for `_6` (cross-seed arm). The orchestrator reads it and passes
`RANDOM_SEED=` per run.

## 4. Launch command

Run on `cloud-vm-rq2` (or via the orchestrator):

```bash
ssh cloud-vm-rq2 "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n STORAGE_CPUS=<SC> EDGE_CPUS=<EC> WAN_RTT_MS=185 RANDOM_SEED=42 \
    EDGE_MONGO_READ_PREFERENCE=secondaryPreferred EDGE_MONGO_MAX_POOL_SIZE=12 \
    VIP_DATA_PER_CONNECTION_FLOWS=1 OVERLOAD_CPU_PCT=30 OVERLOAD_PEAK_LATENCY_MS=2000 \
    make -C source/scripts setup_network create_clients setup_test_data run_experiment \
    OSKEN_ENV_OVERRIDE_FILE=../../rq2_env/<ENV_FILE> \
    RUN_LABEL=<LABEL> \
    PHASES_CONFIG=testing/phases_override/<PHASES_FILE> \
    CLIENTS=24 CONTENT_ITEMS=3000 USERS=100 DATA_SEED=42 \
    CURL_MAX_TIME=300 TRAFFIC_DRIVER_MODE=open_loop INFLIGHT_WINDOW=1024 DRAIN_S=30 \
    SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1 \
    > /tmp/<LABEL>.log 2>&1 &"
```

Orchestrator: `python3 tools/run_rq2_campaign.py --host cloud-vm-rq2 \
--order docs/operation/testing/experiment/v3/rq2/counterbalance_order_v2.csv \
--start-at <label> [--log ...]`.

## 5. Provenance / hash record

The campaign runs the code pinned at tag `rq2-v3-campaign-20260808` (the
P5-validated state — local commit `925c43f` / VM commit `84cbd8be`), which
supersedes the pre-fix `rq2-v3-campaign-20260807`. Recorded at launch
(2026-08-08) on `cloud-vm-rq2`:

```
orchestrator:            268b57998cb3fa7d34f017934a951be7   (campaign launch 2026-08-08)
orchestrator (sf_cb rerun amendment 2026-08-12): d45cdb2939d7a010c548fb410d9261b5
rq2_compute_first.env:   2735f36a069d6a48ebf15cc8d894fa72
rq2_storage_first.env (campaign launch, tagged): 3e18ffcadc4ab21d5352f4950877bbeb
rq2_storage_first.env ({REPO}/rq2_env, current 2026-08-12): c41bd38ef309cc1dd6822757c89dbb52
rq2_storage_first.env (~/rq2_env, STALE reserve=0): e8a5e9e24d47b0483094118d2bfb3ddf
rq2_bottleneck_aware.env:4eb3ac058adcb181c8c325cbbd359869
phases_rq2_data_bound.json:   06a880c5dbfceb78c4ae5639870b5cd5
phases_rq2_compute_bound.json: d40f5f592375360c76a1d55f4c168200
controller source:       tag rq2-v3-campaign-20260808 (VM commit 84cbd8be)
```

sf_cb rerun 1-row order CSV hashes (created 2026-08-12, deleted after the rerun):
```
sf_cb_preflight_1.csv: b41313d28c55228ff3c1b9b0fd32dd90
sf_cb_run_1.csv:       884da160602dbce88d547d0576dcb2b5
sf_cb_run_2.csv:       b502c8118c7d6a484a76bede066626c7
sf_cb_run_3.csv:       1120ca8041c1c9bdd6671898878afb04
sf_cb_run_4.csv:       567813048d43459dcdfd575e0a38e54a
sf_cb_run_5.csv:       e86aea806ac08ed8acc1e14f2867acf9
sf_cb_run_6.csv:       14fc0b63f9a9fed4fbd473a8d8d61f06
```

**P8 resolution (2026-08-12):** `rq2_sf_cb_preflight_1` (seed 2001, 0.15/0.08)
— Branch A (storage fires on cb; 2 on lan2); DF 9.5 %, agg p50 3.4 ms, timeout
0.50 %; folder quarantined in `{METRICS}/_superseded_pilot/`. Pilot
`rq2_sf_cb_pilot` (seed 42, 0.15/0.08): DF 52 %, timeout 10.77 % — the single
outlier among 8 sf_cb@0.15 runs; quarantined likewise.
