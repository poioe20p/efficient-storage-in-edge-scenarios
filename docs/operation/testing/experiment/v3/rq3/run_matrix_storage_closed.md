# RQ3 v3 — Run Matrix (storage-replica benefit)

Part of [`experiment_plan.md`](experiment_plan.md). Per-run configuration for
the v3 RQ3 campaign (storage-replica benefit, tag
`rq3-stor-v3-campaign-20260807`).

> **Status: CLOSED (2026-08-08) — preflight done, storage campaign NOT RUN.**
> The probe phase (S-A..S-E) and the **4-run preflight** (P1/P2/P1-fix/P2-fix,
> §3) are complete. Preflight verdict: **storage-scale-up benefit NULL** at the
> locked campaign config → per the governance rule (plan §6, RQ3-storage-3),
> **no storage campaign**. RQ3 is evaluated on **compute only** (complete).

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
| S-A | `20260807_102732_rq3stor_probe_sa` | 3002 | SG-1/2/3 PASS, SG-4 FAIL (primary-pinned reads, no relief) → prefer_secondary fix |
| S-B | `20260807_112529_rq3stor_probe_sb` | 3002 | SG-2 collapse (31 % timeouts) → rate 0.6 |
| M1 | `20260807_121601_rq3stor_probe_m1` | 3002 | **SG-4 FAIL under honest window guards** (n=1 clean steady-state in the 300 s probe plateau; +44.7 % inflated by out-of-plateau/sparse windows) → **re-run at campaign 600 s phases**; ⚠ 153× NotPrimary burst — selection hardening §5.1 |
| M2 | `20260807_123710_rq3stor_probe_m2` | 3002 | **SG-4 PASS +14.8 %** (corrected; write cut 0.30→0.10 — weaker relief, supports mechanism) |
| M1b | `20260807_125756_rq3stor_probe_m1b` | 3005 | **SG-4 PASS +49.5 %** (corrected; reproducibility) |
| S-E | `20260807_131848_rq3stor_probe_se` | 3006 | **SG-4 PASS +42.3 %** (corrected; discovery arm; timing + consequence in plan §5.1/§5.3) |

## 3. Preflight (4 runs — closed, verdict: storage benefit NULL)

| # | Label | Arm | Seed | Result |
|---|---|---|---|---|
| P1 | `20260807_152020_rq3stor_preflight_direct` | direct | 3001 | SG-4 +38.2 % (⚠ **transient-spike artifact** — disproven); D1 31× NotPrimary burst; **FAIL** |
| P2 | `20260807_161136_rq3stor_preflight_disc` | disc | 3001 | SG-4 +3.6 %; D1 0; **FAIL** |
| P1-fix | `20260807_173547_rq3stor_preflight_direct_fix` | direct | 3001 | SG-4 +0.6 % (baseline 0.4); D1 0; **FAIL** |
| P2-fix | `20260807_234234_rq3stor_preflight_disc_fix` | disc | 3001 | SG-4 **−1.9 %** (baseline 0.4); D1 0; **FAIL** |

Full-length campaign phases (`phases_rq3_storage.json`, 600 s plateau @ rate
0.6). Launched on `cloud-vm-rq3` (launcher defaults EDGE_CPUS=0.75 /
STORAGE_CPUS=0.04):

```bash
ssh cloud-vm-rq3 "cd ~/efficient-storage-in-edge-scenarios && \
  bash source/scripts/testing/rq3stor_launch_run.sh rq3stor_direct.env rq3stor_preflight_direct 3001"
ssh cloud-vm-rq3 "cd ~/efficient-storage-in-edge-scenarios && \
  bash source/scripts/testing/rq3stor_launch_run.sh rq3stor_discovery.env rq3stor_preflight_disc 3001"
```

**Verdict (2026-08-08):** the 3 honest runs (P2 +3.6 %, P1-fix +0.6 %,
P2-fix −1.9 %) show **no sustained storage benefit**; P1's +38.2 % was an
early-plateau transient-spike artifact (pool p95 4.4–5.0 s in the first
~120 s, pre_p95 4236 ms), proven by the P1-vs-P1-fix investigation. Storage
CPU ~50–65 % in both arms across the plateau (no relief). R-stor-3 passes in
all 4 runs (reads offload) but offload never converts into user-visible
benefit. Per the pre-registered governance rule → **storage should not scale
up → no storage campaign**; RQ3 thesis claim = compute (complete).

### 3.1 Preflight pass criteria (vs `testing_requirements.md`)

Evaluated with `tools/rq3stor_probe_gate.py` (SG-1..SG-6 **+ R-stor-3
read-offload co-gate**) + `tools/rq3stor_req_check.py` (D1/D2/D3/F1/I1/I2/F2)
on `cloud-vm-rq3`; cross-run per mode via `tools/rq3stor_campaign_analysis.py`.

| Req | Gate | Pass criterion (per run) |
|---|---|---|
| **B2** | SG-4 | storage-scale-up benefit: pool p95 drops ≥ 10 % `[spawn−60, spawn]` vs `[admitted+10, admitted+70]` **AND the R-stor-3 co-gate passes** |
| **B2/mechanism** | R-stor-3 | PRIMARY connection share drops ≥ 20 % relative OR lands ≤ 60 % post-admission (per-run, window_log) |
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

Verdict: **preflight CLOSED — storage benefit NULL → no campaign.**
All base requirements (D1/D2/D3/F1/F2/I1/I2, SG-3, G5, G7) pass in every
run; the **SG-4/B2 benefit gate fails in 3 of 4** and the 4th (P1) is a
proven transient artifact. Per plan §6 / RQ3-storage-3, storage should not
scale up under this workload. The 12-run storage matrix (§4) is **NOT
launched**; RQ3's thesis claim rests on the compute campaign.

## 4. Main matrix (12 runs) — NOT RUN (storage benefit null)

Retained for reference only; **will not be launched**. Executed in
counterbalanced order from
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

**CLOSED (2026-08-08):** the storage campaign is not run; this record pins the
**verified code state** used by the 4-run preflight (P1/P2/P1-fix/P2-fix) on
`cloud-vm-rq3` — the same verified source the compute-only RQ3 verdict rests
on. Tag: `rq3-v3-compute-only-20260808` (new, Option A). The controller/edge
source was synced to `cloud-vm-rq3` with hash verification; the md5 below are
the **VM hashes** (what actually ran), verified 0 mismatches vs the scoped
commit:

```text
Synced to cloud-vm-rq3 2026-08-07/08 (md5 = VM hashes, verified against the rq3-v3-compute-only-20260808 commit):

46f9f9a81190000e7d30a21f01771e76  source/sdn_controller/scaling_config.py
b3fc3cabb30f95316ca2850805e04f50  source/sdn_controller/control_events.py
dc1b0b2900a5250c3e144cde11027f82  source/sdn_controller/main_n1.py
1766801d528cb771852555400a8e2aa6  source/sdn_controller/main_n2.py
56cce371014a514d87de5233d6a3db45  source/sdn_controller/vip_routing.py
dc0b804870a7770b91823d6425ac02b9  source/sdn_controller/_vip_routing/config.py
871f832f70985c3c3de90a8c2d878fe7  source/sdn_controller/_vip_routing/flows.py
9936e30735866d7ed07f99afd4d6506c  source/sdn_controller/_vip_routing/ingress.py
a7d08699223ed36ff9038c5ad24ffdd2  source/sdn_controller/_vip_routing/selection.py
723e15503ac44d7713f5db9f1ce1449a  source/sdn_controller/_vip_routing/state.py
b031fca280056836027dc19d24836e56  source/docker/edge_server/source/app.py
54414f70927fe9346645b5c540131f11  source/scripts/testing/run_experiment.sh
4d110ae010db7ef7a000d0ef8569e009  source/scripts/testing/rq3stor_launch_run.sh
bd140d4e6a255dabe4f7917887ec9613  source/scripts/testing/controller_env_overrides/rq3stor_direct.env
719b229070be9213b43f3c17512f9487  source/scripts/testing/controller_env_overrides/rq3stor_discovery.env
eeecb995ed3fb85225c997d37a38bc9c  source/scripts/testing/phases_override/phases_rq3_storage.json
faf381c71edb19e7080fb5b62ed27bd4  source/scripts/testing/phases_override/phases_rq3_storage_probe.json
cb5ae1bade4dbd31706413852f311a4c  docs/operation/testing/experiment/v3/rq3/counterbalance_order_v2.csv
```

Per-run launch records (source/env/phases md5 captured into the run folder by
the launcher) go here as the campaign executes.
```
