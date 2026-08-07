# RQ2 v3 — Run Matrix

Part of [`experiment_plan.md`](experiment_plan.md). Per-run configuration for
the v3 RQ2 campaign (storage-bind locked config, tag `rq2-v3-campaign-20260807`).

> **Status: PLANNED — NOT LAUNCHED.** Preflight (2 × `sf_db`, same seed) must
> pass before the 36-run campaign starts.

## 1. Per-cell configuration

| Cell | Env file (staged `~/rq2_env/`) | Phases file | EDGE_CPUS | STORAGE_CPUS | Verified by |
|---|---|---|---|---|---|
| `cf_cb` | `rq2_compute_first.env` | `phases_rq2_compute_bound.json` | 0.15 | 0.08 | cb_1/cb_2 (B1, v2 record) |
| `cf_db` | `rq2_compute_first.env` | `phases_rq2_data_bound.json` | **1.20** | **0.15** | F4a/F4b (B2, storage-bind record) |
| `sf_cb` | `rq2_storage_first.env` | `phases_rq2_compute_bound.json` | 0.30 | 0.15 | v2 Series-C |
| `sf_db` | `rq2_storage_first.env` | `phases_rq2_data_bound.json` | **1.20** | **0.15** | F4a/F4b + preflight |
| `ba_cb` | `rq2_bottleneck_aware.env` | `phases_rq2_compute_bound.json` | 0.15 | 0.08 | v2 Series-C |
| `ba_db` | `rq2_bottleneck_aware.env` | `phases_rq2_data_bound.json` | **1.20** | **0.15** | F4a/F4b (db config) |

Shared: `EDGE_MONGO_MAX_POOL_SIZE=48`, `EDGE_MONGO_READ_PREFERENCE=
secondaryPreferred`, `VIP_DATA_PER_CONNECTION_FLOWS=1`, `WAN_RTT_MS=185`,
`RANDOM_SEED=42`. Readiness gate (D9a) on in all three arm envs
(`READINESS_PROPAGATION=direct`, `EDGE_APP_READY_EVENT=1`).

## 2. Preflight (2 runs)

| # | Label | Cell | Seed | Purpose |
|---|---|---|---|---|
| P1 | `rq2_sf_db_preflight_1` | `sf_db` | 2001 | storage bind → relief at locked config |
| P2 | `rq2_sf_db_preflight_2` | `sf_db` | 2001 | same-seed reproducibility |

Pass = both runs satisfy experiment_plan §6 (B2, M1, M2, V1, I1, I2, D1–D3,
F2; timeout ≤ 5 %) with consistent direction and comparable magnitude.

## 3. Main matrix (36 runs)

Executed in counterbalanced order from
[`counterbalance_order_v2.csv`](counterbalance_order_v2.csv): 6 blocks × 6
cells, run labels `rq2_<cell>_1..6`. Block seeds 2001–2006.

## 4. Launch command

Run on `cloud-vm-rq2` (or via the orchestrator):

```bash
ssh cloud-vm-rq2 "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n STORAGE_CPUS=<SC> EDGE_CPUS=<EC> WAN_RTT_MS=185 RANDOM_SEED=42 \
    EDGE_MONGO_READ_PREFERENCE=secondaryPreferred EDGE_MONGO_MAX_POOL_SIZE=48 \
    VIP_DATA_PER_CONNECTION_FLOWS=1 \
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

The campaign runs the code pinned at tag `rq2-v3-campaign-20260807`. On
completion of the preflight, record the md5 of the synced orchestrator, arm
envs, and phase files in this matrix (replace this placeholder):

```
orchestrator:            <md5 of tools/run_rq2_campaign.py>
rq2_compute_first.env:   <md5>
rq2_storage_first.env:   <md5>
rq2_bottleneck_aware.env:<md5>
phases_rq2_data_bound.json:   <md5>
phases_rq2_compute_bound.json:<md5>
controller source:       <commit/hash synced at launch>
```
