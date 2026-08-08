# RQ3 — Experiment Plan (v3): compute-only verdict, storage extension closed

**Status:** ✅ **DECIDED (2026-08-08) — storage extension CLOSED.** RQ3 is
evaluated on **compute only** (thesis RQ3, already complete 2026-08-06); the
storage-replica scale-up extension returned a **4-run preflight null** and is
**not carried forward**. No storage campaign runs.
**Scope:** (1) carry forward (amend) the **established compute scale-up benefit**
from the saturation probe (compute RQ3 complete); (2) evaluate the **storage
replica scale-up benefit** under a read-write mix where writes clog the primary
and reads offload to replicas — **evaluated, null, closed**; (3) the
pre-registered decision rule fired: **no benefit → storage should not scale up**
(RQ3-storage-3).
**Basis:** compute probe results in
[`rq3_saturation/experiment_plan.md`](../rq3_saturation/experiment_plan.md)
(2026-08-07, cells P-A′…P-B2) + the verified architecture: `/content` write
endpoint to the primary, `secondaryPreferred` reads, `rs_secondary_ready`
control event, and telemetry-based SECONDARY promotion fallback.
**Predecessor:** [`../rq3_saturation/experiment_plan.md`](../rq3_saturation/experiment_plan.md)
(compute saturation re-run, probe complete; campaign not started).
**Host:** `cloud-vm-rq3` (idle; fixed image `638e3efdcdc5` present).

---

## 1. Established — compute scale-up benefit (amended from the probe)

The saturation probe (7 cells, 2026-08-07) measured the **compute** side of the
readiness-propagation story at 48 clients. Result (window_log-authoritative):

| Dimension | Result | Evidence |
|---|---|---|
| **Relief (R1)** | Old-backend compute CPU **drops 9.3–9.7 pp** per admission | P-A′ −9.7 pp (74→65 %, n=9 steady-state); P-B −9.3 pp (68→59 %, n=12) |
| **T_proc (R2)** | −6 ms in P-A′ (51→45 ms) | supporting |
| **Timing (T1)** | direct ready→admit ≈ 0 s (event) vs probe quantization; start→admit 6.0 s (direct) vs 7.4 s (discovery) | P-B vs P-E/P-E2 |
| **Consequence** | **null** at achievable saturation | gap-window ≈ 0 in every cell; plateau-timeout metric = burst noise (P-B 11.4 % vs P-B2 27.7 % at same config+seed) |
| **Why bounded** | the RQ2-calibrated autoscaler fires at 70–88 % CPU (score is T_proc-dominated; CPU normalisation saturates ~9.5 %) → the compute tier cannot over-saturate | controller score log, P-B |

**This is the compute result the thesis carries forward:** readiness propagation
demonstrably **accelerates compute admission** (timing) and compute scale-up
**does relieve** the tier (≈ 10 pp CPU), but the admission-timing differential
does **not** translate into end-to-end harm because the compute tier cannot be
pressed past ~70–88 %. Locked config: rate 1.5 / EDGE_CPUS 0.25 /
`READINESS_EVENT_FALLBACK_S=20`.

**The gap left open (and this plan's reason to exist):** the probe deliberately
moved the workload *away* from storage (fixing the P-A collapse) and never
exercised the **storage tier as the bottleneck**. Storage replicas scaled (up to
4 members, 17 spawns in P-B) but relieved nothing because the workload had
~0 DB ops. Storage replica benefit is **untested** — that is what this plan
adds.

---

## 2. Why storage replicas — the untested relief mechanism

The architecture already implements the storage twin of the compute readiness
gate (verified in source):

| Piece | Mechanism | Location |
|---|---|---|
| **Writes to primary** | `POST /content` writes engagement updates to the replica-set primary via a dedicated `directConnection` write client — docstring: *"Writes generate oplog traffic that stresses all replica-set members, making storage scale-up measurable."* | `source/docker/edge_server/source/monitoring_workload_routes.py`, `vip_data_mongo_runtime.py` |
| **Reads to replicas** | `EDGE_MONGO_READ_PREFERENCE=secondaryPreferred` (default in `build_network_*.sh`) → reads offload to secondaries when present | network build scripts |
| **Replica readiness** | a new replica must reach **SECONDARY** (catch up) before it can serve reads | mongo replica-set semantics |
| **Direct notification** | `rs_secondary_ready` control event → promote the replica into the VIP read pool the instant it reaches SECONDARY | `control_events.process_secondary_events` |
| **Periodic discovery** | telemetry-based `member_state == SECONDARY` detection → promote as a **fallback** (periodic, up to telemetry cadence) | `control_events.promote_storage_from_telemetry` |

**Hypothesis (the relief pathway):** under a **read-write mix**, writes clog the
primary (primary-only write path + oplog fan-out) while reads offload to
replicas. Adding a replica increases read capacity → the primary's residual read
work and its **piled queue drain** → request latency drops → **storage scale-up
benefit is measurable**. Replica catch-up (→SECONDARY) is the readiness
condition; **direct** (event) promotes the instant it catches up, **discovery**
(telemetry poll) promotes up to one cadence later — so during the catch-up gap
the primary stays clogged, and the timing differential becomes consequential.

**Pre-registered caution (not fixated):** if the read share is too small, adding
replicas only adds oplog fan-out (primary gets *more* work, not less) and there
is **no benefit**. That is exactly what the benefit gate (§6) decides.

---

## 3. Research questions

- **RQ3-storage-1 (benefit):** Under a read-write mix, does adding a storage
  replica (scale-up) produce measurable relief of the primary's write/read
  queue (request latency / primary CPU) — i.e. **is storage scale-up
  beneficial**?
- **RQ3-storage-2 (propagation):** When a replica becomes ready (SECONDARY),
  does direct lifecycle notification (`rs_secondary_ready`) vs periodic
  discovery (telemetry) change when the relief arrives — and does that
  differential become **consequential** while the primary is clogged?
- **RQ3-storage-3 (governance):** If RQ3-storage-1 shows **no benefit**, the
  verdict is that **storage should not scale up** under this workload (elastic
  capacity is wasted and only adds oplog load). This is a pre-registered
  outcome, not a failure.

Shared common ground with RQ1/RQ2/RQ3-compute: the same readiness-propagation
mechanism (event vs discovery) and the same elasticity framework — each RQ tunes
its own variant of the workload/config.

---

## 4. Configuration (draft — mix to calibrate in Phase 1)

### 4.1 Launch parameters (per run, `cloud-vm-rq3`)

```text
TRAFFIC_DRIVER_MODE=open_loop  CURL_MAX_TIME=300  INFLIGHT_WINDOW=1024  DRAIN_S=30
CLIENTS=24                     # 48 total (RQ1/RQ2 golden)
EDGE_CPUS=0.25                 # compute side unchanged (carried from probe)
STORAGE_CPUS=0.08              # storage compute quota (calibrate if needed)
WAN_RTT_MS=185
EDGE_MONGO_MAX_POOL_SIZE=6
EDGE_MONGO_READ_PREFERENCE=secondaryPreferred
```

### 4.2 Workload — the read-write mix (new phases file)

`source/scripts/testing/phases_override/phases_rq3_storage.json` (new; the
traffic generator already supports `content_update` → POST `/content` and
`content_aggregate`). Baseline read-write mix to calibrate in Phase 1:

| Request type | Path | Target | Initial weight |
|---|---|---|---|
| `content_update` (write) | POST `/content` | **primary** (dedicated write client) | 0.30 |
| `content_lookup` (read) | GET `/content/<id>` | replicas (secondaryPreferred) | 0.45 |
| `feed_ranking` (read+compute) | GET `/feed` | replicas | 0.25 |

- Phase skeleton mirrors the saturation shape: `baseline` → **`storage_plateau`
  (600 s, full client_fraction)** → `recovery_gap` → `demand_drop` → `idle_tail`.
- **Calibration objective:** enough writes that the primary's write latency /
  queue rises (primary becomes the bottleneck) **and** enough reads that
  replica offload is the relief — but **not** so write-heavy that the primary
  collapses (that would be a driver/storage failure, not a treatment regime).

### 4.3 Storage propagation mode (implementation prerequisite)

The compute ReadinessGate has `READINESS_PROPAGATION=direct|discovery`. The
storage promotion path currently runs **event + telemetry fallback together**.
This plan requires a **storage propagation mode switch** (mirroring the compute
gate):

- `STORAGE_PROPAGATION=direct` → promote **only** on `rs_secondary_ready`
  (event-driven; no telemetry promotion).
- `STORAGE_PROPAGATION=discovery` → promote **only** on telemetry-detected
  SECONDARY at a poll cadence (the quantization = the treatment).

Carried in `controller_env_overrides/rq3stor_{direct,discovery}.env` (canonical
env rule) + mirrored in `env/`. **This is the one platform extension this plan
requires** (analogous to the compute ReadinessGate — acceptable per the
per-RQ-variant principle).

### 4.4 Arm envs

`rq3stor_direct.env` (STORAGE_PROPAGATION=direct, EDGE_APP…/storage-ready event
enabled) and `rq3stor_discovery.env` (STORAGE_PROPAGATION=discovery, storage
telemetry SECONDARY promotion only).

---

## 5. Phase 1 — probe (calibrate + benefit gate)

Cells **S-A..S-D** (direct arm) iterate until a config passes the gates; then a
single **S-E** (discovery at the locked config) verifies the propagation
differential.

### 5.1 Probe gates (all must pass to lock)

**S-A (2026-08-07, direct, mix 0.30/0.45/0.25, rate 1.2, EDGE_CPUS 0.25,
STORAGE_CPUS 0.08) — verdict: SG-1/2/3 PASS, SG-4 FAIL.** The primary
clogged hard (plateau p95 16.1 s vs baseline 1.1 s; SG-2 PASS) and storage
scaled (17 promotions, all `rs_secondary_ready` → direct mode switch verified;
SG-3 PASS), but **no relief**: median p95 drop 0 % (3 of 4 measured promotions
worse). Root cause (read-distribution, window_log): the primary still carries
~2× the connections (59 vs ~28 per replica) — reads only partially offload and
the primary-pinned share queues for seconds (db_ms ~10 ms, storage CPU 40–46 %
→ the seconds are queueing, not DB work). Adding replicas cannot drain a
primary-pinned share. **Response (Path 1 + Path 2):** (1) new
`STORAGE_READ_POLICY=prefer_secondary` (skip the PRIMARY for read selection
when any secondary exists — writes stay on the primary via the dedicated write
client); (2) resource shaping so the storage tier is the only constrained
resource: EDGE_CPUS 0.75 (compute never the bottleneck), STORAGE_CPUS 0.04,
Mongo cache already 0.25 GB (env-gated to shrink further if needed).

**M2 (2026-08-07, direct, rate 0.6, mix 0.10/0.55/0.35 — write reduction only)
— verdict: SG-1/2/3/4 PASS, median p95 relief +17.5 %.** Counterintuitive but
decisive: cutting writes WEAKENED the relief (M1 +44.7 % vs M2 +17.5 %) because
fewer writes = less primary pressure = less room for the replica read-offload
to relieve. This supports the original mechanism (writes create the primary
bottleneck; replica offload relieves it). **M1b (2026-08-07, seed 3005,
reproducibility) — SG-4 PASS +27.5 % (SG-2 pressure-band miss: plateau p95
1.2 s did not rise vs baseline).** The benefit reproduces across M1/M1b/M2
(relief +17.5…+44.7 %); the plateau-pressure magnitude is run-to-run noisy
(p95 1.2–11.2 s) but does not remove the effect. **Locked probe config: rate
0.6 / mix 0.30/0.45/0.25 / prefer_secondary / EDGE_CPUS 0.75 / STORAGE_CPUS
0.04** — locked for the campaign.

**S-E (2026-08-07, discovery at the locked config, seed 3006) — SG-4 PASS
+36.6 %, propagation mode switch verified** (all 10 promotions
`telemetry_secondary`, none `rs_secondary_ready`). End-to-end delivery timing
measured from the storage sidecar logs (sidecar `SECONDARY` reached →
controller promote): **direct 0.00 s (29/29 promotions across M1/M2/M1b) vs
discovery 1.0–6.0 s (avg ~3.9 s, 9/9 in S-E)** — the `rs_secondary_ready`
event path is already immediate (control mini-summary →
`process_secondary_events`, step 2, outside the telemetry cadence), so no
event-path change was needed. **Consequence (C-stor-1): null.** Both arms'
`spawn → promote` totals are dominated by the replica-set initial-sync
catch-up (~35–41 s); discovery's ≤10 s window quantization is masked by
run-to-run catch-up variance (direct fast cluster 35.3–40.6 s vs discovery
39.7–40.2 s), so the propagation mode cannot change when relief arrives
within the 300 s plateau. Per the v2/rq3 C9 precedent, the honest null is
accepted and the claim narrows to the delivery-layer timing differential.

**Probe-number corrections (honest SG-4 window guards, 2026-08-07):** all probe
benefit numbers above are the ORIGINAL unguarded estimates. Under the SG-4
guards (post window `[w+10, w+70]` inside the plateau; `n_pre`/`n_post` ≥ 50),
the corrected per-run medians are **M2 +14.8 %, M1b +49.5 %, S-E +42.3 %
(PASS)** and **M1 n=1 clean steady-state (FAIL)** — M1's +44.7 % was inflated
by promotions whose windows fell outside the 300 s probe plateau (e.g.
`lan2_dyn7` promoted 12:23:19, after plateau end 12:22:10). M1 is therefore
**re-run at the campaign 600 s phases**; the preflight/campaign numbers are the
evidence. The benefit direction is stable across the three usable probes
(+14.8…+49.5 %), consistent with the R-stor-3 mechanism (primary connection
share post ≈ 34–44 %, offload +1…+25 % per promotion).

| Gate | Criterion | Purpose |
|---|---|---|
| **SG-1** Driver clean | canceled+dropped < 5 % of offered; http=000 ≈ 0 in `baseline` (plateau timeouts = treatment regime, RQ3-sat calibration) | 48-client driver envelope |
| **SG-2** Primary under pressure | primary write/read latency p95 **rises** across the plateau (primary is the bottleneck); no storage collapse (timeout rate < ~10 % whole-plateau) | the clog exists and is safe |
| **SG-3** Storage scale-up fires | ≥ 1 storage replica admitted per LAN during `storage_plateau` | the mechanism is exercised |
| **SG-4** **Benefit** | after replica admission: pool latency p50/p95 **drops ≥ 10 %** over `[spawn−60, spawn]` vs `[admitted+10, admitted+70]` — steady-state admissions only (ramp guard: promotion ≥ 120 s into the plateau, **post window `[w+10, w+70]` must stay inside the plateau, `n_pre`/`n_post` ≥ 50**) | **the benefit gate — counts only when the R-stor-3 read-offload co-gate also passes** |
| **SG-5** Quantization intact | evaluated on **S-E**: direct `SECONDARY → promoted` ≲ 1 s (measured **0.00 s**); discovery 1–6 s (avg ~3.9 s — below the ≥ 5 s expectation because the storage bootstrap telemetry lands inside the 10 s window) | propagation treatment |
| SG-6 | whole-run canceled/dropped < 5 %; driver cleanliness only | same as SG-1 |

**Hardening (pre-campaign, 2026-08-07):** the M1 probe's 153×
`NotPrimaryOrSecondary` burst (12:17:32–12:18:01, reads on `edge_server_n2`)
is the `prefer_secondary` selection routing reads to a RECOVERING (non-SECONDARY)
member during a replica-set reconfig. Fixed in `_vip_routing/selection.py`:
reads now offload to **SECONDARY-only** members.
`tools/rq3stor_window_burst_check.py` verifies whether any burst touches an
SG-4 window before M1's +44.7 % is carried forward. Residual risk (documented):
`member_state` is telemetry (~1 window old), so an in-flight connection to a
member demoted mid-reconfig can still fail once; new connections re-select per
flow (`VIP_DATA_PER_CONNECTION_FLOWS=1`).

### 5.2 Escalation / de-escalation / stop

- **Primary not clogged (SG-2 fail):** raise the write share (`content_update`
  0.30 → 0.45, rebalance reads) or raise rate; never exceed the driver-clean
  cap (rate ≤ 1.5 / 72 req/s envelope — RQ3-sat precedent).
- **Collapse (SG-2: timeouts > ~10 %):** lower the write share / rate.
- **No benefit (SG-4 fail after the mix is genuinely primary-clogging):**
  **stop** — the verdict is **storage should not scale up** under this
  workload (§3 RQ3-storage-3). Record the finding; do not force more load.
- Lock on SG-1..SG-4 (direct cells); S-E then verifies SG-5 + the consequence
  direction (§5.3).

### 5.3 Consequence direction (S-E decision rule)

S-E (discovery at the locked config) must show: **discovery's relief arrives
later** than direct's (promotion timing), and during the catch-up gap the
primary stays clogged — measured as gap-window latency p95 / timeout excess
**> direct's**. If the direction is absent, diagnose (primary not clogged
enough? catch-up too fast?) and re-probe; the absence is recorded.

**S-E outcome: direction ABSENT — consequence null, pre-registered-acceptable
(C9, v2/rq3 precedent).** The mechanism differential exists at the delivery
layer (0.00 s vs 1–6 s) but is swamped by the RS initial-sync catch-up
(~35–41 s) in the `spawn → promote` totals, so no gap-window latency/timeout
excess is measurable within the 300 s plateau. No re-probe needed: the null
is mechanism-backed (catch-up dominance), not under-saturation. The campaign
(§7) therefore reports the delivery-layer timing differential (T-stor-1) as
the propagation claim and the benefit (R-stor-1/SG-4) as the headline; no
designed-cadence arm is added (a slower discovery cadence would be a
tautological knob-setting, not a system property).

### 5.4 Preflight verdict — storage benefit NULL at the locked campaign config

The 2-run preflight planned in `run_matrix.md` §3 was expanded to **4 runs**
(2026-08-07/08, `cloud-vm-rq3`, full-length 600 s plateau @ rate 0.6) to
resolve run-to-run noise and the SG-2 config artifact (baseline rate 1.0 → 0.4
fix). Full gates on every run:

| Run | Arm / baseline | SG-4 (benefit) | SG-2 (V1) | D1 (NotPrimary) | Verdict |
|---|---|---|---|---|---|
| P1 `20260807_152020_rq3stor_preflight_direct` | direct / 1.0 | +38.2 % (⚠ transient artifact) | FAIL | ⚠ 31× (burst, demand_drop) | ❌ artifact |
| P2 `20260807_161136_rq3stor_preflight_disc` | disc / 1.0 | +3.6 % | FAIL | ✅ 0 | ❌ FAIL |
| P1-fix `20260807_173547_rq3stor_preflight_direct_fix` | direct / 0.4 | +0.6 % | FAIL | ✅ 0 | ❌ FAIL |
| P2-fix `20260807_234234_rq3stor_preflight_disc_fix` | disc / 0.4 | **−1.9 %** | FAIL | ✅ 0 | ❌ FAIL |

**Investigation (why P1 "passed"):** P1's +38.2 % was driven by an
early-plateau transient latency spike (pool p95 4.4–5.0 s in the first ~120 s;
pre_p95 4236 ms in the evaluated pre-windows) that subsided regardless of
replica admission. Both runs converge to the same steady-state plateau p95
(~1.1–1.2 s). Storage primary CPU stays ~50–65 % across the plateau in **both**
arms — adding replicas relieves neither latency nor CPU. R-stor-3 (read
offload) passes in all 4 runs (replicas do offload reads), but the offload
never converts into user-visible benefit. **No sustained storage-scale-up
benefit at the locked config — the honest, cross-arm, cross-baseline verdict
is NULL.**

**Governance outcome (RQ3-storage-3, pre-registered):** storage scale-up is
**not beneficial** under this workload → **storage should not scale up**.
Elastic capacity is wasted and only adds oplog load. No storage campaign is
run; RQ3's thesis claim is carried by the compute campaign (complete).

---

## 6. The governance rule — storage should not scale if it doesn't benefit

**Pre-registered verdict rule (the experiment's headline output):**

- If **SG-4 / R-stor-1** shows no measurable relief (latency/queue drop below
  threshold) at a genuinely primary-clogging mix → **storage scale-up is not
  beneficial** → the elasticity policy **should not scale storage** under this
  workload (elastic capacity adds oplog load without relief). The campaign
  then reports the *negative* benefit as the finding, with the resource-cost
  argument (wasted capacity + oplog fan-out).
- If benefit **is** shown → the campaign proceeds to the propagation question
  (direct vs discovery relief timing) and the consequence.

This gate is what makes the experiment about **whether to scale**, not just
**how fast to scale** — addressing the thesis requirement that scale-up must
demonstrably matter.

---

## 7. Phase 2 — campaign (NOT RUN: SG-4 benefit null at campaign config)

> **Decision (2026-08-08): no storage campaign.** The 4-run preflight
> (P1/P2/P1-fix/P2-fix, §5.4) showed **no measurable storage benefit** at the
> locked campaign config: SG-4 median p95 drop −1.9…+3.6 % across the three
> honest runs (P1's +38.2 % was a proven early-plateau transient-spike
> artifact; both arms, both baseline settings). Per the governance rule (§6)
> and RQ3-storage-3, **storage should not scale up under this workload** — the
> negative-benefit finding is the deliverable. RQ3's thesis claim rests on the
> compute campaign (already complete). The planned 12-run storage matrix below
> is retained for reference only and will NOT be launched.

- **Arms:** `direct` (`rq3stor_direct.env`) vs `discovery`
  (`rq3stor_discovery.env`), n = 6/arm → 12 runs, counterbalanced blocks
  (seeds 3001–3006, `tools/gen_rq3_counterbalance.py` — v2/sat convention).
- **Labels:** `rq3stor_direct_{1..6}` / `rq3stor_disc_{1..6}`.
- **Order:** `v3/rq3/counterbalance_order_v2.csv` (seeds 3001–3006, direct=3 /
  disc=3 leads, no designed-cadence arm).
- **Code pinned:** tag `rq3-stor-v3-campaign-20260807` (launch code force-added
  so the tag contains the campaign config; controller/edge source synced at
  launch with hash verification, hashes recorded in `v3/rq3/run_matrix.md`).
- **Preflight gate:** 2 runs (P1 direct + P2 disc, seed 3001) must pass
  `testing_requirements.md` B2/M1/M2/V1/I1/I2/D1/D2/D3 (plus F1/F2 and
  campaign gates G5/G7) before the campaign launches — `run_matrix.md` §3.
  Campaign n may be raised above n=6/arm if the preflight indicates more
  statistical power is needed.
- **Runtime:** ~30 min/run × 12 ≈ 6 h + voids.
- **If SG-4 shows no benefit → no campaign; the negative-benefit finding is
  the deliverable** (run a small confirmation set, n=3/arm, then stop).

---

## 8. Pre-registered metrics

All within `storage_plateau`; steady-state admissions (spawn ≥ 120 s into the
plateau, ramp guard).

| ID | Metric | Expectation |
|---|---|---|
| **R-stor-1** (primary benefit) | Pool-wide request latency p50/p95, `[spawn−60, spawn]` vs `[admitted+10, admitted+70]` (replica admission) | **drop ≥ 10 %** (primary queue relief) |
| R-stor-2 (supporting) | Primary CPU / write-latency pre → post | drop |
| **R-stor-3** (hard co-gate) | Read offload: PRIMARY connection share pre → post (window_log) | **drops ≥ 20 % relative OR lands ≤ 60 % post-admission** — per-run + cross-run per mode; SG-4 counts only when this passes |
| R-stor-4 (context) | Replica RAM / member count | sane growth |
| **C-stor-1** (consequence) | Gap-window latency p95 / timeout rate `[spawn, min(promoted, plateau_end)]` | **discovery > direct** (primary stays clogged during the catch-up gap) |
| C-stor-2 | Gap-window failure rate | same direction |
| **T-stor-1** (timing) | `SECONDARY → promoted` (delivery layer) | direct ≈ 0 s (measured **0.00 s**, 29/29) vs discovery 1–6 s (avg ~3.9 s) |
| T-stor-2 | `spawn → first read served by replica` | direct faster |
| **V-stor-1** (governance) | SG-4 benefit met / not met | **verdict: storage scales (or does not) by measured benefit** |

**Unit of analysis = RUN** (per-run median over that run's steady-state
promotions — not per-promotion pooling). **Headline = latency** (R-stor-1 p95
drop ≥ 10 %); the timeout branch is secondary (reported, not gated).
Cross-run per mode: median + direction consistency (≥ 2 of 6 consistent,
reproducibility principle) + bootstrap CI. **Paired per seed** (direct_N ↔
disc_N share block seed N): exact permutation test on the paired deltas +
Cliff's δ (v2/rq3 stats convention). Evaluated by
`tools/rq3stor_campaign_analysis.py` (per-run + cross-run per mode).

---

## 9. Campaign gates (G1–G8, mirror RQ3-sat conventions)

G1 driver clean; G2 primary pressure band (SG-2); G3 scale-up fires ≥ 1/LAN;
G4 relief (R-stor-1, ≥ 10 %, **with the R-stor-3 read-offload co-gate**);
G5 quantization (T-stor-1); G6 consequence direction (C-stor-1); G7 no storage
collapse; G8 no cross-RQ gate contamination (key on the storage-specific env,
per lessons-learned).

---

## 10. File map

| File | Purpose | State |
|---|---|---|
| `source/scripts/testing/phases_override/phases_rq3_storage.json` | read-write mix phases, full-length 600 s plateau at the **locked rate 0.6** (edited in place from 1.2 — the S-B collapse lesson) | done |
| `source/scripts/testing/phases_override/phases_rq3_storage_probe.json` | fast probe harness (rate 0.6) | done |
| `source/scripts/testing/controller_env_overrides/rq3stor_{direct,discovery}.env` | storage propagation mode | done |
| `docs/operation/testing/experiment/v3/rq3/env/*` | mirrored envs (launcher path) | done (probes) |
| `source/sdn_controller/control_events.py`, `scaling_config.py`, `main_n1.py`, `main_n2.py`, `_vip_routing/selection.py` | `STORAGE_PROPAGATION` + `STORAGE_READ_POLICY` mode switches (**+ SECONDARY-only read-offload hardening**, §5.1) | **done** (probe-verified + hardened) |
| `source/scripts/testing/rq3stor_launch_run.sh` | launcher (RQ3-sat precedent) | done |
| `tools/rq3stor_probe_gate.py`, `rq3stor_relief.py`, `rq3stor_read_dist.py`, `rq3stor_lat_by_endpoint.py`, `rq3stor_req_check.py` | SG gates + R-stor-1 relief + read distribution + endpoint latency + base-requirements check | done |
| `tools/rq3stor_window_burst_check.py`, `rq3stor_campaign_analysis.py` | SG-4 window-burst verification + per-run/cross-run campaign analysis (R-stor-3 co-gate, paired per seed) | done |

---

## 11. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Adding replicas only adds oplog load (no read offload because read share too small) | SG-2 pressure + SG-4 benefit gate; rebalance mix; this **is** a legitimate outcome (V-stor-1) |
| Primary collapse under writes | SG-2 timeout band; lower write share; stop/escalate per §5.2 |
| Storage promotion mode switch is new platform code | Mirror the verified compute ReadinessGate; isolated to the storage promotion path; selftest before runs |
| Run-to-run burst noise (RQ3-sat C6 lesson) | Consequence measured on gap-window + steady-state windows, not plateau aggregates; n=6/arm |
| Read-preference not actually offloading | Verify replica request share in probe (SG-3/R-stor-3) before locking |

---

## 12. Timeline

| When | Action | Status |
|---|---|---|
| Now (draft) | Review this plan; approve direction | done |
| Step 1 | Implement `STORAGE_PROPAGATION` mode switch + selftest | done |
| Step 2 | Phase-1 probe cells S-A..S-E (calibrate mix; SG-1..SG-6; S-E direction) | **done** (S-A..S-E; SG-4 PASS 4/4; timing + consequence recorded §5.1/§5.3) |
| Step 3 | **SG-4 verdict** — benefit shown → campaign; no benefit → negative-benefit finding + stop | **done: benefit shown → campaign** |
| Step 3a | **Hardening**: SECONDARY-only `prefer_secondary` fix + M1 window-burst verification + R-stor-3 co-gate + per-run/cross-run tools | done (fix + tools; M1 verification runs before the number is used) |
| Step 3b | **4-run preflight** (P1/P2/P1-fix/P2-fix, seeds 3001) vs `testing_requirements.md` (B2/M1/M2/V1/I1/I2/D1/D2/D3 + F1/F2 + G5/G7 + R-stor-3 co-gate) | **done** (2026-08-07/08) — D1/D2/D3/F/I pass; SG-4 benefit NULL → verdict (§5.4) |
| Step 4 | Phase-2 storage campaign (12 runs) | **NOT RUN — SG-4 null ⇒ no storage campaign** (compute RQ3 already complete) |
| Step 5 | Thesis doc updates (rq3.md, conclusions, thesis_overview) | pending |
