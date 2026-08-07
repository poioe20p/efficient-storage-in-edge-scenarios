# RQ3 v3 — Run Matrix (storage-replica benefit)

Part of [`experiment_plan.md`](experiment_plan.md). Per-run configuration for
the v3 RQ3 campaign (storage-replica benefit, tag
`rq3-stor-v3-campaign-20260807`).

> **Status: PLANNED — NOT LAUNCHED.** The probe phase is complete (S-A..S-E,
> SG-4 benefit proven 4/4). A **2-run preflight** (one per mode, same seed)
> must pass before the 12-run campaign starts.

## 1. Per-cell configuration

| Cell | Env file | Phases file | EDGE_CPUS | STORAGE_CPUS | Verified by |
|---|---|---|---|---|---|
| `direct` | `rq3stor_direct.env` | `phases_rq3_storage.json` | 0.75 | 0.04 | M1/M2/M1b (SG-4 PASS, +17.5…+44.7 %) |
| `disc` | `rq3stor_discovery.env` | `phases_rq3_storage.json` | 0.75 | 0.04 | S-E (SG-4 PASS +36.6 %, propagation switch verified) |

Shared locked config: rate 0.6 (plateau), mix `content_update 0.30 /
content_lookup 0.45 / feed_ranking 0.25`, `STORAGE_READ_POLICY=prefer_secondary`,
`EDGE_MONGO_READ_PREFERENCE=secondaryPreferred`, `EDGE_MONGO_MAX_POOL_SIZE=6`,
`VIP_FLOW_ISOLATION=1`, `WAN_RTT_MS=185`, `RANDOM_SEED=42`,
`CLIENTS=24 CONTENT_ITEMS=3000 USERS=100 DATA_SEED=42`. Readiness gate OFF
(`READINESS_PROPAGATION=off`) so only the storage promotion path carries the
treatment.

## 2. Phase 1 — probe history (complete)

| Cell | Label | Seed | Verdict |
|---|---|---|---|
| S-A | `20260807_121601_rq3stor_probe_m1` | 3002 | SG-1/2/3 PASS, SG-4 FAIL (primary-pinned reads, no relief) → prefer_secondary fix |
| S-B | (rate 1.2 write collapse) | — | SG-2 collapse (31 % timeouts) → rate 0.6 |
| M1 | `20260807_121601_rq3stor_probe_m1` | 3002 | **SG-4 PASS +44.7 %** (locked config established) |
| M2 | `20260807_123710_rq3stor_probe_m2` | 3002 | **SG-4 PASS +17.5 %** (write cut 0.30→0.10 — weaker relief, supports mechanism) |
| M1b | `20260807_125756_rq3stor_probe_m1b` | 3005 | **SG-4 PASS +27.5 %** (reproducibility) |
| S-E | `20260807_131848_rq3stor_probe_se` | 3006 | **SG-4 PASS +36.6 %** (discovery arm; timing + consequence recorded in plan §5.1/§5.3) |

## 3. Preflight (2 runs — per mode, same seed)

| # | Label | Arm | Seed | Purpose |
|---|---|---|---|---|
| P1 | `rq3stor_preflight_direct` | direct | 3001 | campaign config end-to-end at the locked config; benefit + base requirements |
| P2 | `rq3stor_preflight_disc` | disc | 3001 | same-seed discovery comparison; mode switch + base requirements |

Full-length campaign phases (`phases_rq3_storage.json`, 600 s plateau @ rate
0.6). ~30 min/run → ~1 h total. Launched on `cloud-vm-rq3` (launcher defaults
EDGE_CPUS=0.75 / STORAGE_CPUS=0.04):

```bash
ssh cloud-vm-rq3 "cd ~/efficient-storage-in-edge-scenarios && \
  bash source/scripts/testing/rq3stor_launch_run.sh rq3stor_direct.env rq3stor_preflight_direct 3001"
ssh cloud-vm-rq3 "cd ~/efficient-storage-in-edge-scenarios && \
  bash source/scripts/testing/rq3stor_launch_run.sh rq3stor_discovery.env rq3stor_preflight_disc 3001"
```

### 3.1 Preflight pass criteria (vs `testing_requirements.md`)

Evaluated with `tools/rq3stor_probe_gate.py` (SG-1..SG-6) + `tools/rq3stor_req_check.py`
(D1/D2/D3/F1/I1/I2/F2) on `cloud-vm-rq3`.

| Req | Gate | Pass criterion (per run) |
|---|---|---|
| **B2** | SG-4 | storage-scale-up benefit: pool p95 drops ≥ 10 % `[spawn−60, spawn]` vs `[admitted+10, admitted+70]` |
| **M1** | SG-3 | ≥ 1 storage replica admitted per LAN during `storage_plateau` |
| **M2** | SG-3 | each admitted replica serves ≥ 1 successful request (usable, not just spawned) |
| **V1** | SG-2 | primary write/read latency p95 rises across the plateau (primary clogged); storage CPU rises |
| **I1** | SG-1/SG-6 | ≥ 2000 completed plateau requests per LAN (probe evidence ~4.2 k/LAN) |
| **I2** | SG-6 | timeout distinct from failure; denominators consistent (offered/completed/timeout/canceled) |
| **D1** | req_check | 0× `NotPrimary`/`NotPrimaryOrSecondary` (controller + storage/server logs) — ⚠ M1 probe had a 153× reconfig transient; must be 0× or flagged with justification |
| **D2** | req_check | 0 controller restart / 0 edge/storage container crash |
| **D3** | req_check | `phases_snapshot.json` + `controller_env_snapshot.env` present in the run folder |
| F1 | req_check | resource_stats rows across the plateau (no telemetry blackout) |
| F2 | req_check | offered lan1 ≈ lan2 (≤ 3× asymmetry) |
| G5 | probe gate | direct: all promotions `rs_secondary_ready`; disc: all `telemetry_secondary` (mode switch intact) |
| G7 | probe gate | whole-plateau timeout rate < ~10 % (no storage collapse) |

Verdict: **P1+P2 both pass all hard gates → launch the 12-run campaign**
(`counterbalance_order_v2.csv`, seeds 3001–3006). A hard-gate failure in
**both** runs → diagnose + re-probe before the campaign. A flag (e.g., a D1
burst like the M1 probe) → report with justification; if it recurs in both
runs → re-diagnose. Campaign n may be increased beyond n=6/arm if the
preflight suggests more statistical power is needed.

## 4. Main matrix (12 runs)

Executed in counterbalanced order from
[`counterbalance_order_v2.csv`](counterbalance_order_v2.csv): 6 blocks × 2
arms, run labels `rq3stor_direct_1..6` / `rq3stor_disc_1..6`. Block seeds
3001–3006.

## 5. Launch command

Run on `cloud-vm-rq3` via the launcher. The env argument is the **filename
only** — the launcher resolves it against `docs/.../v3/rq3/env/`:

```bash
ssh cloud-vm-rq3 "cd ~/efficient-storage-in-edge-scenarios && \
  bash source/scripts/testing/rq3stor_launch_run.sh \
    rq3stor_direct.env rq3stor_direct_<n> <seed>"
ssh cloud-vm-rq3 "cd ~/efficient-storage-in-edge-scenarios && \
  bash source/scripts/testing/rq3stor_launch_run.sh \
    rq3stor_discovery.env rq3stor_disc_<n> <seed>"
```

Launcher defaults: EDGE_CPUS=0.75, STORAGE_CPUS=0.04, and the campaign
`phases_rq3_storage.json` is hardcoded (pass a later `PHASES_CONFIG=` in the
extra-make-vars slot to override, e.g. for a probe harness). Each run ~30 min
(60 s baseline + 600 s plateau + 120 s recovery + 420 s demand_drop + 420 s
idle_tail).

## 6. Provenance / hash record

The campaign runs the code pinned at tag `rq3-stor-v3-campaign-20260807`. On
each launch, the controller/edge source is synced to `cloud-vm-rq3` with hash
verification and the md5 of the synced source files, arm envs, and phases are
recorded here (replace this placeholder with the launch record):

```text
Synced to cloud-vm-rq3 2026-08-07 (md5, verified 0/29 mismatches):

46f9f9a81190000e7d30a21f01771e76  source/sdn_controller/scaling_config.py
b3fc3cabb30f95316ca2850805e04f50  source/sdn_controller/control_events.py
dc1b0b2900a5250c3e144cde11027f82  source/sdn_controller/main_n1.py
1766801d528cb771852555400a8e2aa6  source/sdn_controller/main_n2.py
56cce371014a514d87de5233d6a3db45  source/sdn_controller/vip_routing.py
dc0b804870a7770b91823d6425ac02b9  source/sdn_controller/_vip_routing/config.py
871f832f70985c3c3de90a8c2d878fe7  source/sdn_controller/_vip_routing/flows.py
9936e30735866d7ed07f99afd4d6506c  source/sdn_controller/_vip_routing/ingress.py
672ad5c42390a5cf78bc954a1de2bd6f  source/sdn_controller/_vip_routing/selection.py
723e15503ac44d7713f5db9f1ce1449a  source/sdn_controller/_vip_routing/state.py
b031fca280056836027dc19d24836e56  source/docker/edge_server/source/app.py
54414f70927fe9346645b5c540131f11  source/scripts/testing/run_experiment.sh
4d110ae010db7ef7a000d0ef8569e009  source/scripts/testing/rq3stor_launch_run.sh
bd140d4e6a255dabe4f7917887ec9613  source/scripts/testing/controller_env_overrides/rq3stor_direct.env
719b229070be9213b43f3c17512f9487  source/scripts/testing/controller_env_overrides/rq3stor_discovery.env
2a2669e49f4cf73793adb8c2fdc2ea16  source/scripts/testing/phases_override/phases_rq3_storage.json
faf381c71edb19e7080fb5b62ed27bd4  source/scripts/testing/phases_override/phases_rq3_storage_probe.json
cb5ae1bade4dbd31706413852f311a4c  docs/operation/testing/experiment/v3/rq3/counterbalance_order_v2.csv
```

Per-run launch records (source/env/phases md5 captured into the run folder by
the launcher) go here as the campaign executes.
```
