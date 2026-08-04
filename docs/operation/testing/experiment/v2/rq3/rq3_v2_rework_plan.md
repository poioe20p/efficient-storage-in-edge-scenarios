# RQ3 v2 Rework Plan — Readiness Propagation and Traffic Admission (final evidence)

**Date**: 2026-08-04 · **Status**: 🔵 Plan (approved, 2026-08-04) — implementing
**Review gate**: Reviewer (deepseek-v4-flash, to-be-implemented) — 2 rounds; all
🔴/🟡 resolved (see §8). Approach **A (event-driven direct)** user-approved.
**Supersedes as primary evidence**: nothing yet — the RQ3 mechanism is
implemented (`rq3_preparation.md` landed) but **no RQ3 campaign has ever run**;
the `docs/operation/testing/experiment/v2/rq3/` folder holds no experiment
package (only this plan). This plan is the first complete evaluation design
for RQ3.
**Thesis gates**: `thesis_overview.md` §5/§6/§8 and `thesis_structure.md` §5.4
(open-loop driver, Mann–Whitney U + Cliff's delta, run-level experimental unit,
per-arm knob verification).
**Execution VM**: `cloud-vm-rq3` (dedicated RQ3 VM — per user, 2026-08-04).

---

## 1. Why this rework exists

The RQ3 **mechanism** is fully implemented and validated (`readiness_gate.py`,
`/ready`, flow isolation, `admission_log.csv`, analyzers, arm env files,
`phases_rq3_compute_episode.json` — all landed per `rq3_preparation.md`).
What does **not** exist is the evaluation layer that RQ1 v2 / RQ2 v2 now define
as the thesis standard: no experiment plan, no run matrix, no statistics
contract, no calibration, no gates. The gaps:

| # | Gap | Evidence |
|---|---|---|
| G1 | **No experiment design package** — `docs/operation/testing/experiment/v2/rq3/` contains no `experiment_plan.md`, `run_matrix.md`, `analysis_focus.md`, `results.md` (only this plan after creation). No n, no cells, no counterbalancing, no hypothesis table. | verified folder listing |
| G2 | **No statistics layer** — `rq3_admission_analysis.py` is median/percentile descriptive only (`statistics.mean/median/stdev`); no MWU, no Cliff's delta, no effect sizes, no pre-registered pairs. Thesis §8 and RQ1 v2 §2.6 / RQ2 v2 §2.5 mandate effect sizes + uncertainty; the stats script must mirror `rq2v2_p2_03_stats.py` exactly (exact-enumeration MWU + Cliff's delta, **no CIs**). | analyzer source; `rq2v2_p2_03_stats.py` |
| G3 | **Analyzer not status-aware** — `transition_failure_rate` counts `http_status == 0 or >= 400` (legacy timeout-as-`0` conflation; the RQ2 v2 G2 / RQ1 v2 G2 lesson). The open-loop driver emits a `status` column (`completed`/`timeout`/`dropped`/`canceled`); failure must be **completed-only**, `timeout_rate` separate, `dropped`/`canceled` excluded from latency+failure, counted in offered, reported separately. `first_flow`/`first_success` likewise must exclude `dropped`/`canceled` rows. | analyzer source; RQ2 v2 Phase 1.5 row-value contract |
| G4 | **Written for the legacy sync driver** — `rq3_preparation.md` §T10 says "matching the existing per-request `ip netns exec curl` driver" and `curl -w '%{local_port}'`. The thesis driver is now the **open-loop** driver (`TRAFFIC_DRIVER_MODE=open_loop`, `CURL_MAX_TIME=300`, `INFLIGHT_WINDOW=1024`, `DRAIN_S=30`, per-worker merge, `force_close=True` per-request connections — which RQ3's flow isolation requires). The analyzer's column usage (`completed_at`, `http_status`, `latency_s`, `backend_id`, `source_port`, plus new `status`/`phase`) must be consumer-audited against the actual open-loop CSV. | `rq3_preparation.md`; RQ1/RQ2 v2 driver work |
| G5 | **Concurrency budget + phase rates not reconciled** — `phases_rq3_compute_episode.json` uses `rate_per_client: 5.0` in the spike. With `INFLIGHT_WINDOW=1024` and a 300 s cap, worst-case in-flight/client = 1500 > 1024 → **`dropped` is possible by design** (RQ1 v2 Phase-6 situation). No calibration, no pre-registered decision rule, no concurrency stress check. | phases file; RQ1 v2 Phase 6 |
| G6 | **Direct-arm conceptual purity** — `READINESS_PROPAGATION=direct` is wake-on-enqueue + 1 s re-probe **polling**, not a true event push; the true app-ready instant is unobservable between probes (`rq3_preparation` D3). Thesis wording — "direct lifecycle notification", "direct registration after a verified application-readiness event" (`thesis_overview.md` §6) — overclaims. Reviewer attack surface: *"this is fast polling vs slow polling, not event-driven vs periodic."* | `rq3_preparation.md` D3; `thesis_overview.md` §6 |
| G7 | **Discovery interval is a free knob** — `DISCOVERY_POLL_INTERVAL_S=10` is a config choice with no real-system grounding and no sensitivity point; the result risks reducing to *"you get the delay you configured."* | arm env files |
| G8 | **Consequence measurement mis-anchored** — the thesis payload is the **service-level consequence** of the admission gap, which lives in the **old-backend pool during `[spawn_started, admitted]`** (discovery leaves new capacity dark longer), not in the new backend's post-admission window (both arms look healthy there). No pre-registered gap-window primary metric and no measurability gate; a possible null must be a pre-registered outcome, not a blocker. | `thesis_overview.md` §6; analyzer metric placement |
| G9 | **No arming gates + no per-arm env verification** — no min-admissions gate (a spike that fails to trigger spawns yields no data), no scale-up arming, `rq3_flow_validation.py` not wired as a hard per-run gate, and no verification of the **edge-container** env knobs (`EDGE_FLOW_ISOLATION`, `BIND_PORT=5000`) that never appear in `controller_env_snapshot.env` (RQ1 v2 Phase-6 lesson). | `rq3_preparation.md` T9/T10; RQ1 v2 Phase 6 |
| G10 | **Within-run correlation unaddressed** — the primary metric is per-backend and only a few backends spawn per episode; app-startup variance ≈ effect size. Thesis §8: the experimental unit is the **independent run**. No pre-registered aggregation rule (run-level median) and no minimum-admissions contract. | analyzer `_cross_arm` pools per-backend; `thesis_overview.md` §8 |

**Decision basis (user-approved, 2026-08-04):** full v2 evaluation package —
2 primary arms (`direct`, `discovery`) × n=5, one sensitivity cell
(`discovery_15`, n=3) to convert knob-dependence into a robustness result;
pre-registered consequence metrics as the payload; the open-loop driver;
MWU + Cliff's delta mirroring `rq2v2_p2_03_stats.py`; and a **direct-arm
purity fix** (event-driven `app_ready` push, **approach A — approved**). All
runs on `cloud-vm-rq3` (new VM — setup status to be verified before Phase 6).

---

## 2. Locked requirements

1. **Driver**: run under the existing open-loop driver — `TRAFFIC_DRIVER_MODE=open_loop`,
   `CURL_MAX_TIME=300`, `INFLIGHT_WINDOW=1024`, `DRAIN_S=30`. Status-aware row
   contract (RQ2 v2 Phase 1.5): `timeout` → `http_status="000"`, `latency_s` =
   elapsed to timeout, `status="timeout"`; `dropped`/`canceled` →
   `http_status=""`, `latency_s=""`, `status=<class>`. Failure rate =
   **completed only**; timeout rate = `status=timeout` / (offered − canceled −
   dropped); offered = all rows; `dropped`/`canceled` counted in offered,
   excluded from latency + failure, reported separately.
2. **Direct arm = event-driven `app_ready` push** (fixes G6): the edge server
   emits an `app_ready` control event the moment the `app_ready` flag flips;
   the controller admits **on the event** in `direct` mode — admission ≈
   readiness + event-path latency, with **no probe before admission**. The
   readiness **criterion stays identical across arms**: `/ready` and the
   `app_ready` event both read the **same `app_ready` flag**, so the criterion
   is structurally identical; only the delivery semantics differ (event vs
   probe observation). The `/ready` probe is used in `direct` mode only for
   (a) a **post-admission identity confirmation** (verify `/ready` returns 200
   at the moment of event-driven admission — a non-200 is logged as an
   identity-check violation and reported, not a gate, since the flag was
   already true when the event fired), (b) an **event-absence safety net** (if
   no event within `READINESS_EVENT_FALLBACK_S` = 5 s after spawn-complete,
   fall back to `/ready` probing at `READINESS_PROBE_RETRY_S` so a single lost
   event cannot strand a ready backend), and (c) abandonment detection —
   `READINESS_PROBE_MAX_S` is a wall-clock timeout from spawn-complete in
   **both** modes (the modes differ in detection granularity, not mechanism).
   **Event-vs-fallback is measured, not assumed**: the admission log gains an
   `admit_source` column (`event` | `probe_fallback`), and a direct-mode run is
   **instrumentation-degraded** if < 80% of its admitted backends are
   event-driven (a fast-starting backend can legitimately be admitted by the
   safety net before its event lands; the fraction is reported and gated, so
   the "event-driven" claim is verified, not asserted). Fallback (recorded,
   not chosen): keep probe-based `direct` (wake + 1 s retry) and honestly
   reframe every document as "event-proximate vs periodic" — see §3.
3. **Discovery interval grounded + sensitivity**: `DISCOVERY_POLL_INTERVAL_S=10`
   pre-registered as "representative of registry/health-check-based discovery
   periods" with a citation; **plus** a secondary cell `discovery_15`
   (`DISCOVERY_POLL_INTERVAL_S=15`, n=3) so the quantization cost is shown to
   scale with the period (robustness, not knob-dependence).
4. **Pre-registered metrics** — the arm-differential consequence lives in the
   **admission gap**, not in the new backend's post-admission window (both
   arms look healthy there). Primary hierarchy:
   - **Headline (single pre-registered pair-metric):** pool-wide (old-backend)
     `timeout_rate` during the gap window `[spawn_started, admitted]` — direct
     vs discovery. This is where the quantization tail shows: discovery leaves
     the new capacity dark up to one poll period longer, so old backends carry
     the saturated load longer.
   - **Supporting (pre-registered consistency rule):** pool-wide `failure_rate`
     during the gap window (completed-only), useful initial request share
     (share of requests succeeding in `[spawn_started, admitted +
     TRANSITION_WINDOW_S]`, pool-wide), scale-decision → usable-capacity. The
     headline verdict must be supported by ≥ 2 of the 3 supporting metrics in
     the same direction (Cliff's delta sign); otherwise the conclusion is
     "mixed/ambiguous" — no post-hoc metric selection.
   - **Secondary / manipulation checks:** `spawn_complete → admitted`
     quantization (must show `direct` ≤ `discovery` — validates the
     mechanism), `admitted → first_flow` (should be arm-identical — confirms
     the selection function is held fixed), flow-isolation coverage (Check C),
     one-connection-per-request model (Check D), readiness-criterion identity
     (post-admission confirming `/ready` probe in `direct` mode; the
     `spawn_complete → app_ready_observed` overlap is **not** a cross-arm
     statistic because observation semantics differ — event vs probe — per
     §2.2).
   **Polarity convention (for the consistency rule):** "same direction toward
   the hypothesis" means, for the lower-is-better metrics (`timeout_rate`,
   `failure_rate`), `discovery` > `direct` supports the headline; for the
   higher-is-better metric (useful initial share), `direct` > `discovery`
   supports it. The rule is applied in this normalized polarity.
   Transition window: pre-registered `TRANSITION_WINDOW_S` (default 30 s),
   phase-aligned via the generator `phase` label; **truncation rule** — if a
   backend's admission lands within `TRANSITION_WINDOW_S` of the spike→cleanup
   phase boundary, the transition window is truncated at the boundary (requests
   in `cleanup_gap` are excluded). The **headline gap window is truncated the
   same way**: `[spawn_started, min(admitted, spike_end)]` — a backend admitted
   after the spike→cleanup boundary contributes no headline gap-window data
   (there is no saturation to measure), but still contributes the timing/
   quantization metrics (which carry no request-count requirement — the ≥ 20
   request rule applies to the share/failure/timeout metrics only, per §2.5).
5. **Experimental unit**: the independent run. Primary comparisons use
   **run-level medians** of the per-backend gap-window values. Gates and void
   policy: a run requires ≥ 1 admitted compute backend **per LAN** (else the
   run is void); a void run is re-run with a fresh block seed, with at most 1
   void per cell recorded before the cell is reported under the missing-value
   rule. The re-run **takes the void run's position in the pre-recorded
   `counterbalance_order_v2.csv`** (no re-randomization); the matrix records
   the void (marked `void`) and the replacement (marked `replacement` + seed). The ≥ 20 attributed-requests rule applies to the **share/failure/
   timeout metrics** only (they need a request-count denominator); the timing
   metrics (quantization `spawn_complete → admitted`, `admitted → first_flow`,
   scale-decision → usable-capacity) are defined from the admission log and
   the first attributed request, with no request-count minimum. A backend-level
   metric is defined only if its own rule is met (else the backend is excluded
   from the run-level median; a run with no defined backends is a missing value
   for that metric). Per-backend distributions are reported descriptively
   (per-run scatter).
6. **Statistics**: mirror the statistical *methods* of `rq2v2_p2_03_stats.py`
   (two-sided Mann–Whitney U with exact enumeration when n_a + n_b ≤ 16 +
   Cliff's delta; no censored value enters MWU; latency percentiles
   descriptive-only with a censoring flag; missing-value exclusions with ≥ 3
   defined runs/cell; unified denominators; **no confidence intervals**)
   adapted to RQ3's pair structure (the RQ2 script hardcodes RQ2's cb/db ×
   cf/sf/ba design — RQ3's script uses the same methods on RQ3's pairs). At
   n=5 per primary arm the best-case two-sided MWU p is 2/C(10,5) ≈ 0.0079,
   but this bound assumes 5 defined, tie-free run-level values per arm; ties
   (discrete shares) and missing-value exclusions raise the achievable p, and
   per §1 G10 the expected separation is far from perfect — so conclusions
   rest on Cliff's delta (≥ 0.6 = large) + direction consistency across
   replicates, with the MWU p reported descriptively, exactly as RQ2 v2 scopes
   its n=3 claims.
7. **Gap-window measurability gate + between-arm differential** (fixes G8; no
   contradiction with a possible null): the pre-flight gate is on
   **measurability**, not direction — a calibration run passes only if ≥ 20
   requests are attributed to old backends within `[spawn_started, admitted]`
   per LAN (enough data to define the headline metric). The **conclusion is the
   between-arm differential**: pool-wide old-backend `timeout_rate` in the gap
   window, compared **direct vs discovery** via the primary stats pair. The
   within-arm gap-vs-baseline delta (vs the spike-phase baseline defined in
   §4.2) is a **context statistic only** — a ≥ 5 pp above-baseline delta flags
   a "degrading gap" for interpretation (constant pinned here: `GAP_DELTA_PP
   = 5`); it is not a gate and not a verdict, because the calibrated workload
   is chosen (§4.1) to produce it and it cannot discriminate the arms. If the
   between-arm differential shows no service cost, RQ3's honest conclusion is
   a null on the consequence metrics and the claim narrows to the timing
   quantization — pre-registered, not decided post-hoc, and the campaign runs
   to completion either way.
8. **Per-arm env/knob verification**: `READINESS_PROPAGATION`,
   `READINESS_PROBE_RETRY_S`, `DISCOVERY_POLL_INTERVAL_S`, `VIP_FLOW_ISOLATION`,
   `BACKEND_SELECTION_POLICY`, `VIP_WARM_SERVER_SECONDS` from the env snapshot;
   **`EDGE_FLOW_ISOLATION`, `EDGE_APP_READY_EVENT`, and `BIND_PORT=5000` from
   the edge containers** (`docker exec printenv` — never in
   `controller_env_snapshot.env`); driver knobs from the run log's printed
   config line. `rq3_flow_validation.py` gate policy: **Checks A and B hard**
   (any violation fails the run), **Check C hard at coverage ≥ 0.9** (below ⇒
   instrumentation-degraded run), **Check D** with a pre-registered allowance:
   ≤ 1% reused-source-port requests is tolerated and reported (the bounded
   async-delete caveat of `rq3_preparation.md` D5); **> 1% fails the run**
   (one-connection-per-request is a precondition for flow isolation).
9. **Seeds / blocking**: driver `RANDOM_SEED=42` base; block seeds 2001–2005
   for the 5 primary blocks of 2 (`direct`/`discovery`), seed 2006 for the
   `discovery_15` sensitivity block. With only 2 arms, "distinct order" per
   block is impossible by construction — the constraint is **counterbalance
   with recorded, reproducible randomization**: each block's within-block
   order is sampled from the block seed, the arm-leading distribution is
   verified (each arm leads ≥ 2 of 5 blocks, no systematic first-position
   bias) — if the sampled orders fail this, the block seeds are **resampled
   deterministically** (increment seed until the constraint holds) and the
   final seed set recorded in the plan; and the order matrix is written to a
   new
   `counterbalance_order_v2.csv` (never overwrite an existing file). The
   sensitivity block runs **consecutively after the primary blocks** in the
   same VM session (interleaving would counterbalance nothing — the treatment
   is the interval, not host state; per-run timestamps bound drift).
10. **Docs**: edit canonical files in place (no duplicates); per-arm env regime
    files live in `docs/operation/testing/experiment/v2/rq3/env/` (copies of the
    implemented `controller_env_overrides/rq3_*.env` canon, kept in sync — the
    RQ2 v2 `env/` convention), plus the new `rq3_discovery_15.env`.
11. **VM**: all RQ3 work runs on **`cloud-vm-rq3`** (dedicated RQ3 VM, per user
    2026-08-04); env files synced to `~/rq3_env/` on that VM before the
    campaign. RQ3 is fully **confined to `cloud-vm-rq3`** — image rebuilds and
    controller sync happen there independently of the RQ2 VM (no cross-VM
    sequencing constraint); the `app_ready` branch is inert unless
    `READINESS_PROPAGATION=direct` + `EDGE_APP_READY_EVENT=1`. RQ3 blocks do
    not start until the pre-flight gates pass on `cloud-vm-rq3`.

---

## 3. Approach comparison (recorded)

| | **A — Event-driven direct + 2×5 + sensitivity (chosen)** | B — Probe direct (honest reframe) |
|---|---|---|
| What | True `app_ready` event push for `direct`; n=5 primary arms + `discovery_15` n=3; full stats/calibration/gates | Keep probe-based `direct`; reframe docs as "event-proximate vs periodic"; n=5 + sensitivity |
| Removes G6 (fast-vs-slow polling)? | ✅ yes — `direct` is genuinely event-driven, matching `thesis_overview.md` §6 wording | ❌ only reframed (defensible but weaker) |
| Edge impact | edge_server + aggregator emit/whitelist one control event (reuses the proven `request_complete` path); 2 image rebuilds | none |
| Effort / Risk | Medium / Medium | Low / Low |

**Why A:** the thesis's co-location claim ("direct notification is only possible
when the lifecycle owner and the routing plane share an event path") is only
airtight if `direct` is actually event-driven; the `request_complete` control
event already proves the path end-to-end, so the addition is small and
low-risk. B remains the documented fallback if the user prefers no edge change —
the rest of the plan (stats, calibration, matrix, gates, docs) is unchanged.

---

## 4. Phased task breakdown

File naming: new files `<scope>_p<phase>_<nn>_<name>.<ext>`, scope = `rq3v2`;
canonical files edited in place (never duplicated).

### Phase 1 — RQ3 analyzer rework + selftest · scope `rq3v2`

**Goal**: make the RQ3 analyzers contract-correct under the open-loop driver,
status-aware, and run-level.

| # | File | Action | Task |
|---|---|---|---|
| 1.1 | `docs/research_questions/v2/rq3/rq3_admission_analysis.py` | Edit in place | (a) status-aware service quality per §2.1 (replace `http_status == 0 or >= 400` with completed-only failure + separate `timeout_rate`; `dropped`/`canceled` excluded from latency+failure, counted in offered, reported separately); (b) consumer-audit the CSV columns (`completed_at`, `http_status`, `latency_s`, `backend_id`, `source_port`, `status`, `phase`) against the actual open-loop driver header and fix names; (c) **gap-window primary metrics** — pool-wide (old-backend) `timeout_rate`/`failure_rate` over `[spawn_started, admitted]` vs the baseline phase, plus useful initial request share and scale-decision → usable-capacity per §2.4; (d) **run-level aggregation**: per-run median of per-backend values for the primary metrics + per-backend descriptive table (per-run scatter), with the ≥ 20-request per-backend definition rule and void handling per §2.5; (e) gap-window + transition-window truncation at the spike→cleanup boundary via the generator `phase` label (RQ1 v2 G6 lesson), with slow-backends-after-boundary handling per §2.4; (f) recognize `direct`/`discovery`/`discovery_15` arm labels from `controller_env_snapshot.env` (+ `DISCOVERY_POLL_INTERVAL_S` column when distinct); (g) `first_flow`/`first_success` exclude `dropped`/`canceled`; (h) readiness-criterion identity via the post-admission confirming `/ready` probe + the `admit_source` distribution (event-driven fraction ≥ 80% gate in `direct` runs; not the cross-arm `app_ready_observed` overlap — §2.2). |
| 1.2 | `docs/research_questions/v2/rq3/rq3_flow_validation.py` | Edit in place | Gate policy per §2.8: **A/B hard** (any pre-admission or post-removal traffic fails the run), **C hard at coverage ≥ 0.9** (instrumentation-degraded run below), **D ≤ 1% tolerated and reported, > 1% fails the run** (the D5 async-delete caveat is within the 1% allowance); status-aware request filtering; per-run report emitted into the run folder. |
| 1.3 | `source/scripts/testing/rq3v2_p1_01_analyzer_selftest.py` | **Create** | Synthetic open-loop CSV + admission log: status attribution (timeout/dropped/canceled), run-level aggregation, quantization estimation, arm labels, `admit_source` event-fraction gate, Check A–D gates. Gate = new Makefile target `rq3_analyzer_selftest`. |

**Phase-1 gate:** `make rq3_analyzer_selftest` passes (host + inside a netns);
no stale consumer reintroduces the cap artifact.

### Phase 2 — Direct arm: event-driven `app_ready` push · scope `rq3v2`

**Goal**: fix G6 — `direct` admits on a true readiness event, not 1 s polling.

| # | File | Action | Task |
|---|---|---|---|
| 2.1 | `source/docker/edge_server/source/app.py` | Edit in place | When `EDGE_APP_READY_EVENT=1` (default 0), emit an `app_ready` control event (same sender as `request_complete`, serialized by the existing ZMQ lock) the moment `process_state.app_ready` flips true — before any request is served. Non-RQ3 runs emit nothing (byte-identical). |
| 2.2 | `source/docker/local_state_server/aggregator.py` | Edit in place | Whitelist `app_ready` in `_CONTROL_EVENT_TYPES` (same path as `request_complete`). |
| 2.3 | `source/sdn_controller/readiness_gate.py` + `control_events.py` + `main_n1.py`/`main_n2.py` + `source/sdn_controller/scaling_config.py` + `source/sdn_controller/elasticity/compute_node_manager.py` | Edit in place | In `direct` mode, admit on the `app_ready` event (`process_app_ready_events` → `readiness_gate.admit_on_event(pb)`), recording `admit_source=event`; with a pre-registered **event-absence safety net** (`READINESS_EVENT_FALLBACK_S` = 5 s after spawn-complete → fall back to `/ready` probing at `READINESS_PROBE_RETRY_S`, recording `admit_source=probe_fallback`); post-admission confirming `/ready` probe (identity check); `READINESS_PROBE_MAX_S` wall-clock abandonment in both modes; `discovery` mode unchanged (10 s `/ready` scan). **Config:** add `_READINESS_EVENT_FALLBACK_S` to `scaling_config.py` (all readiness knobs live there per `rq3_preparation` T1). **Env pass-through:** add `EDGE_APP_READY_EVENT` to `compute_node_manager.py` `_docker_run_server` (the readiness-gated **dynamic** spawn path, same mechanism as `EDGE_FLOW_ISOLATION` — static `edge_server_n1/n2` are **not** readiness-gated and boot before the run, so they need no event). `app_ready_ts` logged as the event observation time. |
| 2.4 | `source/scripts/testing/rq3v2_p2_01_app_ready_selftest.py` | **Create** | Synthetic: event arrives → admission within ~1 s of the readiness flip with `admit_source=event`; **event lost → safety-net probing admits on `/ready` within `READINESS_EVENT_FALLBACK_S` + retry with `admit_source=probe_fallback`**; no readiness within `READINESS_PROBE_MAX_S` → abandoned; post-admission confirming probe returns 200; `READINESS_PROPAGATION=off`/`discovery` emit nothing and behave unchanged (regression). Gate = `make rq3_app_ready_selftest`. |
| 2.5 | Env | Edit in place | `controller_env_overrides/rq3_direct.env`: add `EDGE_APP_READY_EVENT=1` and `READINESS_EVENT_FALLBACK_S=5.0`; `rq3_discovery.env` unchanged. Sync the copies in `docs/operation/testing/experiment/v2/rq3/env/`. |

**Phase-2 gate:** selftest passes (host + netns); `off`/`discovery` regression
byte-identical; the misconfiguration guard (no `request_complete`/`app_ready`
events within `FLOW_ISOLATION_WARMUP_S`) still fires.

**Deployment sequencing:** the branch is additive and inert unless
`READINESS_PROPAGATION=direct` + `EDGE_APP_READY_EVENT=1`. Implement + selftest
**locally first**; image rebuild + VM sync on **`cloud-vm-rq3` only** (RQ3 is
confined to its dedicated VM — no RQ2 VM impact); smoke-run before any RQ3 v2
block.

### Phase 3 — Pre-registered metrics & stats · scope `rq3v2`

**Goal**: pre-register the primary hierarchy and add the RQ3 statistics layer
before any run.

| # | File | Action | Task |
|---|---|---|---|
| 3.1 | `docs/operation/testing/experiment/v2/rq3/analysis_focus.md` | **Create** | Pre-registered hierarchy per §2.4–§2.6: **headline** = gap-window pool `timeout_rate` (direct vs discovery); **supporting** = gap-window `failure_rate`, useful initial request share, scale-decision → usable-capacity, with the ≥ 2-of-3 same-direction consistency rule and the polarity convention (§2.4); **secondary/manipulation** = `spawn_complete → admitted` quantization, `admitted → first_flow`, flow-isolation coverage, `admit_source` event-fraction (≥ 80% in `direct`), post-admission criterion identity; **sensitivity** = `discovery` vs `discovery_15` (Cliff's delta only, no MWU; **≥ 2 defined runs/cell** — n=3 stated, a single void does not drop the comparison, achieved n reported). Denominators, censoring rule, run-level aggregation + ≥ 20-request rule (share/failure/timeout metrics only), min-admissions + void policy, gap/transition-window truncation rule. |
| 3.2 | `docs/research_questions/v2/rq3/rq3v2_p3_01_stats.py` | **Create** | Mirror the statistical methods of `rq2v2_p2_03_stats.py`: two-sided MWU (exact enumeration when n_a + n_b ≤ 16) + Cliff's delta per pre-registered pair; no censored value enters MWU; ≥ 3 defined runs/cell for the primary pair, **≥ 2 for the sensitivity pair** (secondary, Cliff's delta only); unified denominators; `stats_summary.csv` + console table. |
| 3.3 | `docs/operation/testing/experiment/v2/rq3/experiment_plan.md` | **Create** | Hypothesis table (headline: direct ≤ discovery on gap-window pool `timeout_rate`; supporting: gap-window `failure_rate`, useful initial share, scale-decision → usable-capacity; mechanism: quantization `direct` ≤ `discovery`; sensitivity: quantization scales with `DISCOVERY_POLL_INTERVAL_S`), success criteria C1–C9, gates, ack convention (`admission_log` required for both arms; `app_ready` event required for `direct`), v1 = none (first campaign). |

**Phase-3 gate:** stats script smoke-tests on synthetic n=5 data.

### Phase 4 — Calibration, episode validation, env regimes · scope `rq3v2`

**Goal**: fix G5/G8/G9 — calibrate under open-loop, wire the gap-window
measurability gate + arming gates, add the sensitivity env regime.

| # | File | Action | Task |
|---|---|---|---|
| 4.1 | `source/scripts/testing/phases_override/phases_rq3_compute_episode.json` | Edit in place | Re-calibrate spike `rate_per_client` under open-loop (target ≤ 3 req/s/client so `window/rate > 300 s`; if a higher rate is needed, apply the RQ1 v2 Phase-6 decision rule: `dropped` possible by design, > 1% → raise `INFLIGHT_WINDOW` up to the concurrency limit, recorded). The chosen rate must **simultaneously** fit the concurrency budget and saturate the old backends — the calibration run criterion is: spike rate ≤ min(3 req/s/client, the rate at which a calibration run shows gap-window old-backend `timeout_rate` ≥ 5 pp above baseline), recorded with the actual client count and aggregate load. Mix stays compute-bound (service_pressure + feed_ranking dominate; low DB). |
| 4.2 | `docs/operation/testing/experiment/v2/rq3/rq3v2_p4_01_episode_validation.py` | **Create** | Gap-window measurability + context tool: per run, pool-wide old-backend `timeout_rate`/`failure_rate` during `[spawn_started, min(admitted, spike_end)]` vs the **spike-phase baseline** `[max(spawn_started − 60, spike_start), spawn_started]` (constrained to the spike phase so an early scale-up cannot inflate the delta with low-load `baseline`-phase traffic); measurability = ≥ 20 gap-window requests per LAN; context flag = `GAP_DELTA_PP = 5` (≥ 5 pp above baseline ⇒ "degrading gap", for interpretation only — §2.7). Constants pinned here (not deferred): `MIN_GAP_REQUESTS=20`, `GAP_DELTA_PP=5`, `BASELINE_S=60`. Pre-flight on calibration runs (measurability is a gate; the between-arm differential is the conclusion — §2.7); full report per campaign run. |
| 4.3 | `source/scripts/testing/run_experiment.sh` | Edit in place | `collect_rq3_artifacts()` extended: admission logs (already), edge-container `printenv` verification (`EDGE_FLOW_ISOLATION`, `EDGE_APP_READY_EVENT`, `BIND_PORT`), run-log config line for driver knobs; hard-gate wiring: min-admissions check, scale-up arming, `rq3_flow_validation.py` non-zero exit — **ordered before the run-folder cleanup step** (the gates read the copied admission logs and `controller_lan*.log` before those artifacts are deleted). |
| 4.4 | `docs/operation/testing/experiment/v2/rq3/env/rq3_direct.env`, `rq3_discovery.env`, `rq3_discovery_15.env` | **Create** | Copies of the canonical `controller_env_overrides/rq3_direct.env` / `rq3_discovery.env` (kept in sync, provenance note); new `rq3_discovery_15.env` = discovery regime + `DISCOVERY_POLL_INTERVAL_S=15` (distinct named regime — allowed by the canonical-env rule). |

**Phase-4 gate:** calibration runs meet the **gap-window measurability gate**
(≥ 20 gap-window requests per LAN in both arms — the verdict is an outcome,
not a gate, per §2.7); min-admissions arming passes on calibration runs;
flow-validation gate passes.

### Phase 5 — Experiment plan + thesis docs · scope `rq3v2`

| # | File | Action | Task |
|---|---|---|---|
| 5.1 | `docs/operation/testing/experiment/v2/rq3/run_matrix.md` | **Create** | v2 matrix: `direct` × 5, `discovery` × 5, `discovery_15` × 3 = 13 runs; 5 primary blocks of 2 (seeds 2001–2005, within-block order randomized per block seed, arm-leading verified ≥ 2 blocks each — §2.9) + 1 sensitivity block (seed 2006) run consecutively after the primary blocks; new `counterbalance_order_v2.csv`. Launch: `TRAFFIC_DRIVER_MODE=open_loop CURL_MAX_TIME=300 INFLIGHT_WINDOW=1024 DRAIN_S=30`; run suffixes `direct`/`disc`/`disc15`. |
| 5.2 | `docs/operation/testing/experiment/v2/rq3/results.md` | **Create** | v2 template: timeline + per-arm tables + judgment; per-replicate scatter + medians + IQR. |
| 5.3 | `docs/operation/testing/experiment/v2/rq3/post_run_analysis.md` | **Create** | Placeholder per the standard post-run workflow. |
| 5.4 | `tese/Notes/thesis_overview.md` | Edit in place | §5: RQ3 final protocol implemented; §6 RQ3: 2-arm + sensitivity design, event-driven `direct`, consequence metrics pre-registered. |
| 5.5 | `thesis_structure.md` | Edit in place | §5.4: open-loop driver implemented for RQ3; §7.3 limitations (n=5 primary, run-level unit, driver fixed, direct-arm event push). |
| 5.6 | `docs/research_questions/v2/rq3/rq3_preparation.md` | Edit in place | Sync the parent implementation plan: (a) open-loop driver premise + `EDGE_APP_READY_EVENT` + `READINESS_EVENT_FALLBACK_S` + `admit_source` column; (b) **flag the D3 invariant break explicitly** — under event-driven `direct`, `app_ready_ts` is an event observation time, not a probe observation, so the "app_ready_observed → admitted ≈ 0 in both arms" invariant applies to `discovery` only; (c) **supersede T12.4** (the cross-arm `spawn_complete → app_ready_observed` overlap check is dropped as a statistic — replaced by the post-admission confirming probe + `admit_source`); (d) **update the §5 measurement contract**: headline = gap-window pool `timeout_rate` differential, useful share pool-wide over `[spawn_started, admitted + TRANSITION_WINDOW_S]` (not new-backend post-admission only). |
| 5.7 | `tese/references.bib` | Edit in place | Add the discovery-interval grounding citation (registry/health-check default, e.g. Consul) if the chosen citation is not already present. |

### Phase 6 — Campaign execution (`cloud-vm-rq3`)

1. **Pre-flight (hard gates, fail-fast):** (a) `make driver_selftest` (host +
   netns) — already passing; (b) `make rq3_analyzer_selftest`; (c) `make
   rq3_app_ready_selftest`; (d) **concurrency stress check** — aggregate
   in-flight at the calibrated spike rate × clients × 300 s cap must not
   exhaust container/conntrack limits (tune if it does); (e) **G2 calibration
   under open-loop** — re-tune spike rate, apply the `dropped` decision rule,
   record the choice; (f) **gap-window measurability gate** (§4.2) on
   calibration runs — ≥ 20 gap-window requests per LAN in both arms (the
   verdict itself is an outcome, not a gate — §2.7); (g) **min-admissions
   arming** — ≥ 1 admitted backend/LAN in both arms; (h) **per-arm env
   verification** — incl. edge-container `EDGE_FLOW_ISOLATION`/`BIND_PORT` and
   the run-log driver config line; (h2) **event-driven fraction check** on a
   `direct` calibration run — ≥ 80% `admit_source=event` (instrumentation
   sanity for the G6 fix); (i) legacy `sync`-mode regression smoke.
   **Blocks do not start until all pass.**
2. **Main campaign:** 13 runs (5 primary blocks of 2 + 1 sensitivity block of
   3). Workload is 60 + 180 + 180 = 420 s of phases + 4 drains of 30 s + spawn/
   setup/teardown, so ~20–25 min/run → 13 runs ≈ 4.5–5.5 h ≈ **under 1 VM-day**,
   plus up to 3 void re-runs (≤ 1 per cell, §2.5) ≈ +1–1.5 h worst case, plus
   pre-flight/calibration (~4–6 runs ≈ 2 h). All on `cloud-vm-rq3`.
3. **Per-run analysis:** admission timing segments, consequence metrics
   (status-aware), flow-isolation validity (hard gate), episode-validation
   verdict, arm env verification, per-run scatter.
4. **Cross-arm:** updated comparison graphs (per-replicate scatter, medians,
   IQR, Cliff's delta on the primary pair + sensitivity, MWU p on the primary
   pair only — sensitivity is Cliff's delta only per §3.1); stats summary.
5. **Post-run:** `post_run_analysis.md` + `results.md` v2 judgment; archive raw
   run folders on the VM; retain graphs + analysis locally.

**Phase-6 gates:** all runs exit 0; per-arm env verification (arm label +
cadence knobs from env snapshot; edge-container flags from `docker exec
printenv`; driver knobs from the run-log config line); 0×
`NotPrimaryOrSecondary`; no controller restart; min-admissions met per run;
flow-validation checks pass per run; stats on all pre-registered pairs meeting
the ≥ 3-defined-runs cell minimum, exclusions recorded.

---

## 5. Dependencies

- **RQ1 + RQ2 v2 implemented** (done): open-loop driver, `rq2v2_p2_03_stats.py`
  as the stats template, per-arm env-verification convention, generator `phase`
  label. The RQ3 mechanism (`rq3_preparation.md`) is already landed.
- **Two image rebuilds for Phase 2** (`edge_server`, `local_state_server`) —
  only if approach A is kept; build on `cloud-vm-rq3` (RQ3 is confined to its
  dedicated VM — no RQ2 VM impact), smoke-run before any RQ3 block.
- **aiohttp** on the VM (already installed). `requests` already a controller
  dependency.
- Env files (`env/rq3_*.env`) synced to `cloud-vm-rq3:~/rq3_env/` before
  Phase 6.
- Phase 5 docs edits can proceed in parallel with Phases 1–4 but must be
  complete before Phase 6.

## 6. Documentation updates (summary)

`experiment_plan.md`, `run_matrix.md`, `analysis_focus.md`, `results.md`,
`post_run_analysis.md` (all new, `docs/operation/testing/experiment/v2/rq3/`),
`thesis_overview.md`, `thesis_structure.md`, `tese/references.bib`,
`docs/research_questions/v2/rq3/rq3_preparation.md`, plus this plan doc.

## 7. Out of scope (explicit)

- Storage-backend readiness propagation (`rs_secondary_ready`) — distinct
  readiness event, held constant (D8).
- Cross-network `VIP_SERVER` flow isolation — same-LAN RQ3 workload only.
- Tier 1 selective sync / persistent reserves / cross-region placement stay
  disabled (thesis §2).
- No controller change to scale-down logging or backend-selection policy.
- The superseded old-RQ3 (trigger-composition) artifacts remain supporting
  calibration evidence only; not touched.
- RQ1 v2 / RQ2 v2 campaigns: separate efforts on their own VMs.

## 8. Review changelog (2026-08-04)

**Round 1** (Reviewer, deepseek-v4-flash, `--to-be-implemented`): 2 🔴 / 12 🟡 /
8 🔵. Resolutions applied in this revision:

- 🔴 **Calibration gate vs null contradiction** — resolved by splitting
  measurability (gate: ≥ 20 gap-window requests per LAN in calibration runs)
  from verdict (pre-registered outcome: hurt / not-hurt, campaign runs to
  completion either way) — §2.7, §4.2, Phase 6 (f).
- 🔴 **Phase-2 edge-env pass-through omitted** — added
  `compute_node_manager.py` (`_docker_run_server`) **and**
  `build_network_1.sh`/`build_network_2.sh` (static edge servers) to the
  Phase 2.3 file list; without these the `EDGE_APP_READY_EVENT` knob never
  reaches the container and no event is emitted.
- 🟡 Direct-arm identity-check mechanism made precise: admission is
  event-triggered only (no pre-admission probe); the criterion is identical
  because `/ready` and the event read the same `app_ready` flag; the probe is
  used post-admission (identity confirmation) and as an event-absence fallback
  (`READINESS_EVENT_FALLBACK_S` = 5 s) — §2.2, Phase 2.3/2.4.
- 🟡 D3 invariant break flagged: `app_ready_ts` semantics differ between arms
  (event vs probe observation); the cross-arm `app_ready_observed` overlap
  check was **dropped as a statistic** and replaced by the post-admission
  confirming probe; `rq3_preparation.md` updated to record the invariant
  break — §2.2, §2.4, Phase 5.6.
- 🟡 Calibration verdict operationalized with fixed pre-registered constants
  (≥ 20 gap-window requests; ≥ 5 pp old-backend `timeout_rate` above baseline)
  — §4.2.
- 🟡 **Primary metrics re-anchored to the gap window**: headline = pool-wide
  old-backend `timeout_rate` over `[spawn_started, admitted]`; supporting =
  gap-window `failure_rate`, useful initial share (pool-wide gap+transition),
  scale-decision → usable-capacity; the new backend's post-admission window is
  secondary — §2.4, Phase 1.1, Phase 3.1.
- 🟡 Multiplicity: single pre-registered headline pair-metric + ≥ 2-of-3
  same-direction consistency rule for the supporting set; no post-hoc metric
  selection — §2.4, Phase 3.1.
- 🟡 Void policy + minimum requests: ≤ 1 void per cell (re-run with fresh
  block seed) then missing-value; ≥ 20 attributed requests per backend for a
  defined metric; MWU p bound qualified (ties/voids raise achievable p) —
  §2.5, §2.6.
- 🟡 Counterbalance fixed for 2 arms: recorded reproducible per-block
  randomization + arm-leading ≥ 2 of 5 verification (global distinct-order is
  impossible for 5 blocks of 2) — §2.9, Phase 5.1.
- 🟡 Sensitivity MWU contradiction resolved: sensitivity = Cliff's delta only —
  §3.1, Phase 6 step 4.
- 🟡 Flow-validation gate policy per check: A/B hard, C hard at coverage
  ≥ 0.9, D soft with ≤ 1% allowance (D5 async-delete caveat tolerated) —
  §2.8, Phase 1.2.
- 🟡 Dedicated-VM premise: RQ3 confined to `cloud-vm-rq3`; cross-VM
  sequencing constraint removed — §2.11, Phase 2, §5.
- 🟡 Sensitivity block placed consecutively after the primary blocks (the
  treatment is the interval, not host state; per-run timestamps bound drift) —
  §2.9, Phase 5.1.
- 🔵 G1 "empty folder" wording corrected; run-time estimate corrected to
  ~20–25 min/run (420 s workload); §2.2 abandonment wording fixed (wall-clock
  in both modes); transition-window truncation rule added for boundary-crossing
  backends; "mirror exactly" → "mirror the statistical methods"; power caveat
  added; Phase 4.3 gate ordering before cleanup; §4.1 concurrency-vs-saturation
  joint calibration criterion added.

**Round 2** (re-review of changed portions): 1 🔴 / 9 🟡 / 7 🔵; all resolved:

- 🔴 `build_network_*.sh` do not exist under `source/scripts/testing/` — and the
  static `edge_server_n1/n2` are **not** readiness-gated (the gate handles only
  `_handle_compute` dynamic spawns, which boot before the run), so they need no
  `EDGE_APP_READY_EVENT`; removed from Phase 2.3, keeping only
  `compute_node_manager.py` (verified: `_docker_run_server` is the
  `EDGE_FLOW_ISOLATION` pass-through site).
- 🟡 Event-absence safety net no longer undermines the event-driven claim: the
  admission log gains `admit_source` (`event` | `probe_fallback`), and a
  `direct` run is instrumentation-degraded if < 80% of admissions are
  event-driven — the claim is measured, not asserted — §2.2, Phase 2.3/2.4,
  Phase 6 (h2).
- 🟡 Gap-window truncation added (headline window = `[spawn_started, min(admitted,
  spike_end)]`; slow backends admitted after the boundary contribute timing
  metrics only) — §2.4, Phase 1.1(e).
- 🟡 Sensitivity stats slack: ≥ 2 defined runs/cell for the secondary
  sensitivity pair (Cliff's delta only) — Phase 3.1/3.2.
- 🟡 Verdict conflation removed: conclusion = between-arm differential; the
  within-arm gap-vs-baseline delta is a context flag with `GAP_DELTA_PP=5`
  pinned in the plan; no gate, no verdict — §2.7, §4.2.
- 🟡 Arm-leading failure action: deterministic block-seed resampling until the
  constraint holds, final seeds recorded — §2.9.
- 🟡 `rq3_preparation.md` sync expanded (T12.4 superseded, §5 measurement
  contract updated, admission-log columns `admit_source` + `app_ready_ts`
  semantics) — Phase 5.6.
- 🟡 Header "folder is empty" corrected; baseline window constrained to the
  spike phase (`[max(spawn_started − 60, spike_start), spawn_started]`) —
  header, §4.2.
- 🟡 `READINESS_EVENT_FALLBACK_S` config path added (`scaling_config.py` in
  Phase 2.3).
- 🔵 Polarity convention for the consistency rule; ≥ 20-request rule scoped to
  share/failure/timeout metrics (timing metrics exempt); confirming-probe
  non-200 handling (logged + reported, not a gate); void re-run takes the
  matrix position (no re-randomization); estimate includes ≤ 3 void re-runs;
  Check D > 1% fails the run.

**Round 3 (implemented-code review, 2026-08-04)**: 1 🔴 / 10 🟡 / 10 🔵; all
🔴/🟡 resolved:

- 🔴 **`discovery_15` arm label never produced in real runs** — the sensitivity
  env is a `discovery` regime with `DISCOVERY_POLL_INTERVAL_S=15` only, so the
  analyzer now **derives the arm label from the interval** (re-labels
  `discovery` + interval 15 → `discovery_15`); `rq3_flow_validation.py`
  accepts `discovery_15`; the selftest exercises the real env shape.
- 🟡 Check C `measured` = **completed only** (timeout/dropped/canceled never
  emit `request_complete`); exit-code contract 0/1/2 (hard A/B/D → 1,
  instrumentation-degraded C → 2); selftest covers both.
- 🟡 ≥ 20-request rule extended to `useful_initial_share` + transition metrics
  and counted on **attributed** (completed+timeout) requests.
- 🟡 `PendingBackend.abandoned` flag — a late `app_ready` cannot double-admit a
  backend whose teardown was enqueued (no abandoned+admitted double row).
- 🟡 Late-event buffer — an `app_ready` arriving before Thread 3's `enqueue` is
  buffered and replayed on enqueue (no spurious `probe_fallback` degradation).
- 🟡 `admit_on_event` gated to `direct` mode (a misconfigured `discovery` run
  cannot be admitted on the event, bypassing the cadence).
- 🟡 `run_experiment.sh` `verify_rq3_run()` gate wired after
  `collect_rq3_artifacts` and before cleanup: min-admissions per LAN,
  flow-validation exit-code gate, controller + dynamic-edge env verification.
- 🟡 Lock-ordering surface documented (`_on_admit` is non-blocking in-memory
  registration; all gate mutations serialize on `_wake`).
- 🔵 `gap_delta_pp` CLI arg now used (`degrading_gap` run flag emitted);
  `_percentile` returns None for empty input; analyzer docstring identity
  claim corrected; stats `supports_headline` computed from Cliff's-delta sign
  (primary only) and sensitivity reports `scales_with_interval`; app_ready
  selftest gains late-event replay, post-abandonment guard, and
  discovery-guard assertions.
- 🔵 Recorded as remaining: Phase-4.2 `rq3v2_p4_01_episode_validation.py`
  (created during Phase 4 with calibration); stats-script automated selftest
  (validated manually on synthetic n=5); edge-side `EDGE_APP_READY_EVENT=0`
  regression (edge module not unit-tested); gap window uses completion-time
  attribution (documented).

**Pre-flight review (2026-08-04)** — `rq3_preflight.md` +
`rq3v2_p6_01_preflight.sh` + the analyzer's per-LAN gap counts. Round 1: 5 🔴 /
14 🟡 / 7 🔵; Round 2: 1 🔴 / 9 🟡 / 6 🔵; all 🔴/🟡 resolved:

- 🔴 Empty-VM seeding → Stage 4.6 + `SKIP_CLIENTS=0 SKIP_SEED=0 SKIP_SNAPSHOT=0`
  and the **per-run reset cycle** (teardown_clients → setup_network → run);
  seeding is an upsert, so only a teardown resets data (thesis §8).
- 🔴 Unimplementable sync gate → canonical `controller_env_overrides` must
  byte-match `~/rq3_env` (FAIL-hard); docs env copies checked per-knob
  (provenance header differs by design).
- 🔴 Static-edge `EDGE_FLOW_ISOLATION` default 0 → `EDGE_FLOW_ISOLATION=1 make
  setup_network` + static-edge `printenv` verification.
- 🔴 `stage_calib` vacuous pass on empty data → header-only CSV fails; G4
  flow-validation gated per folder; arm cross-check; **both** calibration
  folders required.
- 🔴 Aggregate vs per-LAN measurability → analyzer now emits distinct
  `gap_requests_lan1/lan2` (union window per LAN, no double-counting).
- 🟡 `set -e` G4 abort (Round 2) → flow-validation calls guarded with `if`.
- 🟡 Baseline enforced (nproc ≥ 4, Ubuntu 22.04, 0 containers, make/git/ovs/pip3).
- 🟡 Full env knob matrix asserted (all arms + docs copies) via
  `assert_matrix`; `EDGE_APP_READY_EVENT` negative on both discovery regimes;
  `bind_port` default == 5000.
- 🟡 Concurrency: per-client `rate × 300 ≤ window` and aggregate
  `rate × 6 × 300 ≤ nf_conntrack_max`; feasible-rate interval resolves the
  R1/R2 contradiction; calibration starts at rate 3.0 with an explicit
  fallback chain; distinct calibration seeds (2101/2102, outside 2001–2006).
- 🔵 Calibration summary persisted (`--calib-summary`); exit 2 = INCOMPLETE
  (calibration skipped); report() no longer uses tee; Stage-7 log string is
  the driver's actual banner; Stage-1.6 ordering noted; run-matrix calibration
  budget note added.
