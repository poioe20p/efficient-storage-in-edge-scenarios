# RQ1 v2 — Post-Campaign Diagnostics & Platform-Fix Plan

**Date**: 2026-08-07 · **Status**: 🧭 **DIAGNOSIS COMPLETE — FIXES NOT STARTED, NO RUNS LAUNCHED** (hold point per user) ·
**Plan**: [`experiment_plan.md`](experiment_plan.md) · **Results**: [`results.md`](results.md) §v2 Final ·
**Related**: [`post_run_analysis.md`](post_run_analysis.md), `analysis_focus.md` §0.6, [`rq1_v2_rework_plan.md`](rq1_v2_rework_plan.md)

> This document records the **post-campaign investigations** (scaling-benefit,
> lan2 asymmetry, `http=000`/`unknown` mechanism, conntrack check, resource
> instrument finding) and the **fix plan** for the four identified issues,
> before any v3 re-run work begins. Run folders remain on `cloud-vm`; nothing
> here has been executed or launched.

---

## 1. Investigation 1 — Does scaling bring user benefit?

**Method (Part A, all 20 valid runs):** split each run's `compute_plateau`
requests into named-backend vs no-backend (`unknown`) populations; fleet growth
taken from `container_events` (dyn adds) and backend IDs, **not**
`resource_stats` (see §3.3); plateau latency pre/post usable-capacity as a
sanity trajectory (confounded by the load ramp — reported, not relied on).

**Findings:**

1. **Named backends (base + all dyn, up to dyn5–dyn8) serve at 0% timeout /
   0% failure in every run, on both LANs.** The edge tier never fails a
   request that reaches it (it is merely slow: p50 2–6 s vs 0.007 s baseline).
2. **100% of all plateau timeouts and 100% of all failures belong to the
   no-backend-assigned (`unknown`) population** — requests that stall 13–70 s
   then die with `http=000`, or time out at the 300 s client cap.
3. **Adding edge capacity does not relieve the bottleneck:** `ep_5` lan2 grew
   to 6 dynamic servers (dyn adds at ~121/193/261/501/571/641 s, up to `dyn8`)
   and its `unknown` population still timed out at ~73%.
4. The served population is always perfect (0% failure) regardless of fleet
   size, so **within this design, scaling produces no user-visible benefit**:
   the binding user constraint is the VIP→edge proxy path, which is invariant
   to edge count.

**Cross-RQ context (why the chain is achievable):**

- **RQ2** (`docs/operation/testing/experiment/v2/rq2/results.md`) proves the
  chain *is observable*: after re-calibration, the cross-over reproduced —
  mis-aligned `sf` in compute-bound is 1.6–40× worse on p50/p95; mis-aligned
  `cf_db` pins p99 at the 30 s timeout with failures 1.0–3.4%, while `ba_db`
  holds p99 ≤ 2.5 s / 0.39–0.79% failure. Key enabler: the scaled tier is the
  actual user bottleneck, and a wrong/missing action has visible cost.
- **RQ3** (`results.md`) shows the **same shape as RQ1** — strong timing/
  quantization effect (readiness→admission 0.17 vs 9.6 s; scale→first
  2.17 vs 6.01 s, d = −1.0) with **null user consequence** (gap timeout/failure
  0.000 at every load up to 88% old-backend CPU). So RQ3 is *not* the model for
  "scaling → user distinction"; RQ2's post-recalibration campaign is.

## 2. Investigation 2 — lan2 asymmetry (Part B, 5 ep runs)

**Method:** per-LAN plateau backend counts, per-backend timeout/failure, dyn
add timing (`container_events`).

**Findings:**

1. Offered load is equal per LAN (ratio 1.00) and telemetry delivery is
   symmetric (equal delivered windows) — telemetry is **not** the cause.
2. **All named backends are 0% failed on both LANs.**
3. The asymmetry is entirely in the `unknown` population's **failure** rate
   (`http=000` completed rows): lan2 vs lan1 —
   `ep_1`: 3.54 vs 4.32 (lan1 worse, only exception) ·
   `ep_2`: 9.73 vs 3.10 · `ep_3`: **62.59 vs 2.68** (2468 vs 55 rows) ·
   `ep_4`: 12.15 vs 2.61 (846 vs 146) · `ep_5`: 12.68 vs 3.87 (487 vs 122).
4. ⇒ A lan2 **VIP/network path** fails a subset of connections under the same
   offered load — a data-plane defect, not a delivery-semantics or telemetry
   effect. It contaminates the failure metric and the reference arm (A).

**Status:** root cause narrowed to the lan2 VIP/network path; the exact layer
(edge HTTP concurrency vs VIP flow setup vs netem path) is pending the §5.1.1
read-only probe.

## 3. Investigation 3 — `http=000` / `unknown` mechanism

1. **`backend_id="unknown"` semantics** (`traffic_generator.py`): `backend_id`
   is the `X-Backend-ID` response header; `"unknown"` = **header absent =
   connection failure** (no valid proxied HTTP response from a backend).
2. **Conntrack is DISPROVED as the cause:** `conntrack_entries_n1/n2` peak at
   only 175–265 during the plateau (baseline 133–210) — no exhaustion.
3. **`resource_stats.server_count` UNDERCOUNTS the fleet:** it reports ~1.0–2.0
   during `compute_plateau` while `container_events`/backend IDs show the real
   fleet at dyn5–dyn8. Instrument limitation — fleet-size claims must use
   `container_events` + backend IDs.
4. **ROOT CAUSE (confirmed, code-grounded, 2026-08-07):** the `unknown`
   population is **per-connection OVS data-flow idle-expiry under edge
   queueing.** Driver semantics: `status=completed, http=000, latency 13–70 s`
   = an aiohttp **connection exception** (`except Exception` path in
   `traffic_generator.py` — the connection died mid-request, not a client
   timeout). Edge: Werkzeug `make_server(threaded=True)` with **backlog 128**
   (empirically confirmed `ThreadedWSGIServer.request_queue_size = 128` — the
   backlog=5 hypothesis is DISPROVED) and **Mongo pool 6/edge** → requests
   queue seconds-to-tens-of-seconds (served p50 2–6 s). VIP: per-connection
   data forward flow **`idle_timeout = 10 s, hard_timeout = 0`**
   (`_vip_routing/flows.py`) — an in-flight connection idle >10 s (waiting on
   the edge's DB queue) loses its flow; the response can no longer be
   forwarded → connection dies (13–70 s) or client-timeouts at 300 s. This
   explains: 100% of failures in `unknown` (only stalled connections die);
   named backends 0% (served within the flow window complete); load-dependence
   (RQ3 at low load = 0 http=000); lan2 worse (longer queues); and why edge
   scaling does not help (new edges have the same pool-6 queueing; the flow
   timeout is per-connection, fleet-independent).

## 4. Reality verdicts (the four issues)

| # | Issue | Real? | Evidence | Fix owner |
| --- | --- | --- | --- | --- |
| 1 | Routing-layer connection failures (`unknown` population) | ✅ **YES** | 100% of timeouts/failures; named backends 0%; conntrack not it; invariant to fleet size | edge HTTP concurrency + VIP path (§5.1) |
| 2 | lan2 asymmetry | ✅ **YES** | `unknown`-failure 4–45× worse on lan2 in 4/5 ep runs; telemetry/offered symmetric | rides on #1; else lan2 path (§5.2) |
| 3 | Scale-down measurement (G8) | ✅ **YES** | decision-log real removals A 7/10, B 3/10, **C 0/10, D 0/10**; C/D removals only in `idle_tail` (guard) | deferred controller logging (§5.3) |
| 4 | Designed-null plateau | ✅ **YES** | 600 s bounded plateau amortizes the ~50 s capacity-timing spread; C8 null | workload re-anchor (§5.4) |

## 5. Fix plan

### 5.1 Issue 1 — Routing-layer connection failures (blocking)

1. **1.1 Root-cause — COMPLETE (2026-08-07, read-only):** mechanism =
   **per-connection OVS data-flow idle-expiry (10 s) under edge queueing**
   (Mongo pool 6/edge, served p50 2–6 s). See §3 item 4. Backlog=5 disproved
   (128 confirmed empirically); conntrack disproved; controller logs show no
   data-plane error (expected — OVS data plane).
2. **1.2 Fix — APPLIED (2026-08-07) and synced to `cloud-vm` (byte-identical, MD5-verified):**
   - **(a) Data-plane flow idle_timeout is now env-driven.** Added
     `VIP_DATA_IDLE_TIMEOUT` (default 30) in `_vip_routing/config.py` and used
     it in both VIP_DATA forward branches (`_vip_routing/flows.py`;
     per-connection `hard_timeout=0`, per-client `hard_timeout=120` unchanged).
     All four RQ1 env files set **`VIP_DATA_IDLE_TIMEOUT=120`** (covers the
     observed 13–70 s queue waits). Per-connection binding keyed by client src
     port is preserved — RQ3 flow-isolation Check D semantics unchanged, only
     expiry latency grows. Default is a conservative 30 for the other RQs;
     only RQ1 overrides to 120.
   - **(b) Pool bump DROPPED.** `EDGE_MONGO_MAX_POOL_SIZE` stays 6: the G2
     record shows pool 12 at this config thrashes storage
     (4 edges × 12 = 48 concurrent Mongo ops at `STORAGE_CPUS=0.08`), and the
     queue is compute-bound (edge CPU), not DB-bound — the pool is not the
     lever. If validation shows residual deaths, revisit (bounded raise +
     rate check).
   - ⚠️ Shared controller with RQ2/RQ3 — sync was sequenced (no active RQ1
     run); no image rebuild (volume-mounted controller).
3. **1.3 Validate — ✅ PASSED (2026-08-07, `20260807_143811_rq1_delivery_ep_fixval`, exit 0).**
   - Fix target (connection deaths, `http=000` completed): **0.39 % of plateau
     offered** (133 total) vs v2's 194–2523 per run — artifact effectively
     fixed. Named backends 30,488 completed / **0 non-200**; named p50
     1.52/1.55 s (better than v2's ~2.1 s). lan2−lan1 failure **+0.48 pp**
     (v2 A was +2.64 pp) — asymmetry resolved.
   - testing_requirements: M1 ✅ (3 dyn/LAN), M2 ✅ (usable 24.6 s both LANs),
     V1 ✅ (edge CPU 56–61 % med / 88–90 % max — compute-bound, capacity is
     now the lever), I1 ✅, I2 ✅, D1 ✅ (0 NotPrimary), D2 ✅ (no restart),
     D3 ✅, F1 ✅, F2 ✅.
   - **Open item — RESOLVED (root-caused 2026-08-07, driver fix applied):** the
     ~30 s timeout floor (~1,800/run, hard wall, 100 % inside `compute_plateau`,
     uniform across endpoints, `backend=unknown`, edge logs clean) is a
     **client-side measurement artifact**: aiohttp's `DEFAULT_TIMEOUT` is
     `ClientTimeout(total=300, sock_connect=30)`, and the driver created
     `ClientSession` with **no explicit timeout**, so a stalled TCP handshake
     aborted at exactly 30 s (verified in installed aiohttp 3.14.3 source;
     mechanism = handshake stall under plateau load — backlog/flow-setup
     pressure, not a system property). It is **NOT arm-invariant**: it swings
     701 → 12,823 across the 20 v2 runs (18×, run-dependent), so it added
     chaotic variance to per-run timeout/failure and inflated C/D failure
     counts via a handshake cap rather than genuine behavior.
   - **Fix (2026-08-07):** opt-in `AIOHTTP_SOCK_CONNECT_TIMEOUT` in
     `source/scripts/testing/traffic_generator.py` (`ClientTimeout(total=
     CURL_MAX_TIME, sock_connect=<env or 30>)`); `rq1_launch_run.sh` passes
     `AIOHTTP_SOCK_CONNECT_TIMEOUT=300` for all RQ1 runs. Unset keeps the
     historical aiohttp default (RQ2/RQ3 unchanged). Effect: handshake stalls
     become slow-latency (real signal) or genuine failures at the 300 s cap
     instead of 30 s phantoms. Synced LF-normalized + MD5-verified;
     `edge_server` image rebuilt (`5a4db541fda5`) for the `app.py` bind-timing
     diagnostic (behavior-neutral). Re-run **P0-2 `rq1_delivery_ep_fix2`**
     validates the wall collapses and Arm A can be healthy in-episode.
4. **1.4 P0-2 result + idle-timeout re-fix (2026-08-08):** P0-2
   (`20260807_163608_rq1_delivery_ep_fix2`, exit 0) **validated the sock_connect
   fix** (30 s wall 1,802 → 0) but **exposed the 120 s flow-expiry cliff**:
   `completed/000` = 2,406, of which **1,964 (82 %) die at 120–140 s** (all in
   plateau) — connections queued >120 s at the edge lose their per-connection
   flow (`VIP_DATA_IDLE_TIMEOUT=120`); the 30 s phantom had masked them. The
   flow fix had moved the cliff **10 s → 120 s**; this plateau's queue depth
   exceeds 120 s for ~5 % of requests. **Re-fix (2026-08-08):**
   `VIP_DATA_IDLE_TIMEOUT` raised **120 → 600** (= 2× the 300 s client cap) in
   all four RQ1 env files — byte-identical, LF, MD5-verified on `cloud-vm`;
   controller volume-mounted, no rebuild. Rationale: with idle ≥ 2× cap no
   in-flight connection can outlive its flow, so the artifact class merges
   into the genuine 300 s client-cap timeout. **P0-3 `rq1_delivery_ep_fix3`
   launched 2026-08-08** to validate `completed/000` artifact class → ≈ 0.
- Verify lan1 ≈ lan2 after the #1 fix; if lan2 remains worse, isolate the lan2
  path (per-LAN VIP state, netem on the inter-LAN router, per-LAN edge fleet).
- Gate: lan2−lan1 failure delta < 2 pp on the validation run.

### 5.3 Issue 3 — Scale-down logging (defer the code change)

- The controller is shared, volume-mounted, and RQ2/RQ3 are actively running —
  a controller change now is the one risky edit.
- **Keep the existing bounded claim** (decision_log + container_events joint;
  guard-conditioned for C/D, per `analysis_focus.md` §0.6) and add
  real-removal logging only in a maintenance window after the active campaigns.
- This is a documentation decision, not a campaign blocker.

### 5.4 Issue 4 — Workload re-anchor (make the timing visible)

1. **New demand shape:** replace the 600 s bounded plateau with a **short, steep
   episode (~150–200 s)** where A's ~30 s usable capacity covers the peak and
   C/D's ~80–85 s lands after it — so the timing spread is visible
   per-episode (RQ2 granularity). Edit `phases_rq1_stress_plateau.json` in
   place.
2. **G2 recalibration, RQ2-style:** target a **healthy aligned baseline**
   (Arm A: low p95, ~0% timeout in-episode) with C/D visibly degraded in the
   episode window. Calibrate the rate so the aligned arm is healthy but the
   episode is not a free ride.
3. Re-run 4 arms × n (n = 5 or 7; the n decision matters again for the
   per-episode metrics). Measure per-episode p95 / timeout / failure.

### 5.5 Sequencing & dependencies

```text
#1 fix ──► #2 verify ──► #4 workload re-anchor ──► campaign re-run ──► analysis
   │                          ▲
   └── must precede #4 (the new shape would otherwise re-measure the
       connection-failure population)
#3 deferred to a maintenance window (shared controller, RQ2/RQ3 live)
```

- `cloud-vm` (RQ1 host) is free — diagnosis + validation run can start without
  touching the RQ2/RQ3 VMs.
- Code risk is limited to the shared controller (`_vip_routing/flows.py`, live
  on the other VMs) — the fix must be sequenced/synced, never mid-run; the
  `edge_server` image is unchanged (no image rebuild needed).

### 5.6 Run matrix (planned — NOT started)

The v3 campaign lives in [`../v3/rq1/`](../v3/rq1/) (per user directive: new
campaign + evaluations live under `docs/operation/testing/experiment/v3/rq1/`):
plan [`experiment_plan.md`](../v3/rq1/experiment_plan.md), matrix
[`run_matrix.md`](../v3/rq1/run_matrix.md). Sequence and gates:

| Phase | Runs | Arms | Seeds | Workload | Gate / decision |
| --- | --- | --- | --- | --- | --- |
| **0 — Fix validation** | 1 | A (`ep`) | 2001 | current `phases_rq1_stress_plateau.json` | §5.1.3: `unknown` ≤ 0.5 % of plateau offered; named p50 in v2 range; lan2−lan1 failure < 2 pp → proceed; else revisit |
| **1 — G2 re-anchor (§5.4)** | 2–4 (calibration) | A (`ep`) + 1× C/D probe | 2001–2003 | new short steep episode (~150–200 s) | Arm A healthy in-episode (low p95, ~0 % timeout); overload fires (≥ 30 % windows); C/D visibly degraded in-episode; no collapse |
| **Gate** | — | — | — | — | **validate Phases 0–1 against `testing_requirements.md` (B/M/V/I/D, F flags) — campaign blocked until this passes** |
| **2 — Campaign** | **20 (n=5)** or 28 (n=7) | A, B, C, D | 2001–2005 (reuse v2 counterbalance) or 3001–3007 (new) | new short steep episode | per-run gates + per-episode p95 / timeout / failure stats (MWU + Cliff's delta on factorial edges) |

- Phase 0 is the immediate next step (pending approval) — it isolates the fix
  on the current workload before any workload re-anchor.
- n decision (Phase 2) after Phase 0/1: n=5 if the timing effect is clearly
  separated; n=7 if borderline (per-episode metrics benefit from more runs).

## 6. Status / hold point

- **Per user directive: DO NOT start the run yet; nothing launched.**
- **§5.1.1 root-cause: COMPLETE** (2026-08-07) — mechanism identified:
  per-connection OVS data-flow idle-expiry (10 s) under edge DB-pool queueing.
- **§5.1.2 fix: APPLIED + synced to `cloud-vm`** (2026-08-07, byte-identical;
  flow idle env-driven, RQ1 `VIP_DATA_IDLE_TIMEOUT=120`; pool bump dropped).
- Next action (pending approval): **Phase 0 — §5.1.3 fix validation** (1 arm ×
  1 seed on the current workload); then §5.4 workload re-anchor + Phase 2
  campaign per §5.6.

## 7. Cross-references

- `results.md` §v2 Final (campaign record), `post_run_analysis.md` (capstone),
  `analysis_focus.md` §0.6 (guard-interaction scale-down rule),
  `experiment_plan.md` §F + changelog, `rq1_v2_rework_plan.md`.
- RQ2: `docs/operation/testing/experiment/v2/rq2/results.md` (cross-over
  headline; the chain is observable after re-calibration).
- RQ3: `docs/operation/testing/experiment/v2/rq3/results.md` (null consequence;
  bind-delay `http=000` root cause and fix in `edge_server/source/app.py`).
