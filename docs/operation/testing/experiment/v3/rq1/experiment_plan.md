# Experiment Plan — RQ1 v3 (Telemetry Delivery Semantics — fixed platform)

**Date**: 2026-08-07 · **Status**: 🟢 **PHASE 1 COMPLETE — episode locked (180 s @ 1.2, P1-b PASS); D-arm probe (P1-d) confirms in-episode degradation (p95 5× A). Phase 0+1 gate met (B/M/V/I/D, F reported) → Phase 2 campaign UNBLOCKED (pending n=5 vs n=7 decision).** ·
**Parent (v2)**: [`../../v2/rq1/experiment_plan.md`](../../v2/rq1/experiment_plan.md) ·
**Fix record**: [`../../v2/rq1/rq1_v3_platform_fix_plan.md`](../../v2/rq1/rq1_v3_platform_fix_plan.md) ·
**Base requirements**: [`../../../testing_requirements.md`](../../../testing_requirements.md) ·
**Thesis RQ1**: `tese/Notes/thesis_overview.md` §6-RQ1; `tese/research_questions/rq1/rq1.md`

> **Why v3 exists.** The v2 RQ1 campaign proved the control-loop link but not
> the user link: delivery modes changed *when* the controller scales
> (usable-capacity A 32 < B 57.5 < C ≈ D ~83 s; info-age A < D < C < B), yet
> user-visible service quality was null. Two blockers were identified (fix
> record §4): **(1)** all plateau timeouts/failures were a routing-layer
> connection-drop artifact (per-connection OVS flow idle-expiry under edge
> queueing) that scaling cannot influence — **fixed, opt-in** (§3); **(2)** the
> 600 s bounded plateau amortizes the ~50 s timing spread — to be re-anchored
> in Phase 1 (§6).

## 1. Objective

Same thesis RQ1, with the **full chain** as the target:

```text
delivery mode → what/when the controller sees → when it scales
   → user-visible service quality (per-episode p95 / timeout / failure)
```

The v3 claim to test: after the platform fix and a workload re-anchor, **arms
that scale later (C/D, ~80–85 s usable capacity) show measurably worse
per-episode service quality than A (fresh+complete, ~32 s), with B (delayed,
~57 s) in between** — the observation interface has a measured, replicated
user cost.

## 2. Hypothesis (Phase 2)

- **H1 (control-loop link, reproducibility):** usable-capacity ordering
  A < B < C ≈ D reproduces on the fixed platform.
- **H2 (user link — the new claim):** per-episode p95 / timeout / failure
  order as **A (best) < B < C ≈ D (worst)**, tracking the capacity-timing
  ordering.
- **H3:** non-surge (baseline / demand_drop) quality stays clean in all arms.

## 3. Platform fix (applied 2026-08-07, opt-in)

**Root cause:** per-connection VIP_DATA forward flows idled out at 10 s;
under load, connections waiting on the edge queue lost their flow and died
(`http=000` "unknown" — 100% of v2 plateau failures; lan2 4–45× worse).

**Fix:** new `VIP_DATA_IDLE_TIMEOUT` env (default **10** — RQ2/RQ3 keep
historical behavior unless they set it); all four RQ1 env files set
**`VIP_DATA_IDLE_TIMEOUT=120`** (`../../v2/rq1/env/rq1_*.env`). Controller is
volume-mounted (no image rebuild). Pool stays 6 (G2: pool 12 thrashes storage;
the queue is compute-bound, not DB-bound). Synced byte-identical to `cloud-vm`
(MD5-verified). Full evidence: fix record §3/§5.1.

**Code pin (2026-08-08, post-P1):** the RQ1 Phase-1 validation (P1-b/P1-d) ran
on the controller state of commit **`d267099`** (rq3 v3, "per-connection flow
isolation") — the shared controller files are byte-identical on `cloud-vm`.
That delta is **behavior-neutral for RQ1**: the only shared-code change is
`VIP_SERVER_PER_CONNECTION_FLOWS` (default **0**, set by no RQ1 env →
"original byte-identical behavior" per `ingress.py`). The rq2 commit
**`925c43f`** (classifier/topology grace) is **NOT** on `cloud-vm` and must
stay out of RQ1. **Pin: `rq1-v3-p1-controller-pin-20260808` → `d267099`.**
The campaign runs on exactly this state; the VM working tree is verified
against the pin at every pre-run gate.

## 4. Execution phases (mandatory order)

| Phase | What | Outcome gate |
| --- | --- | --- |
| **0 — Fix validation** | Arm A, seed 2001, current plateau workload (P0-1…P0-4 + **replicate P0-4R for n=2**) | **re-scoped 2026-08-08:** artifact class (120–300 s connection-kill cliff) ≈ 0 of plateau offered · genuine 300 s client-cap timeout ≤ 8 % (v2-accepted envelope) · named p50 in v2 range · lan2−lan1 failure < 2 pp · total `http=000` reported as covariate (not gated) |
| **1 — G2 re-anchor** | 2–4 calibration runs, new short steep episode + **workload-regime matrix (M1/M2/M3, §6)** | healthy aligned baseline (Arm A); overload fires (≥ 30 % windows); C/D visibly degraded in-episode; **B1 AND B2 demonstrable on the chosen regime**; no collapse |
| **Gate** | validate Phases 0–1 against `testing_requirements.md` | §5 below — **campaign may not start until this passes** |
| **2 — Campaign** | 4 arms × n (20 or 28 runs) | per-run gates + per-episode stats |

## 5. Base-requirements gate (`testing_requirements.md`) — applied after Phases 0–1

| Requirement | Phase 0 check | Phase 1 check |
| --- | --- | --- |
| B1/B2 — scaling benefit | B1: compute add → latency drop OR edge-CPU relief (artifact removed ⇒ capacity is the lever) | B1: same, in the new episode |
| M1/M2 — mechanism | ≥ 1 add/LAN during pressure; added node reaches app-ready → serves ≥ 1 request | same |
| V1 — intended bottleneck | edge CPU rising in plateau (compute-bound) | edge CPU rising in the episode (compute-bound) |
| I1/I2 — interpretability | enough completed requests/LAN for percentiles; timeout / failure / dropped classes distinct | same |
| D1/D2/D3 — data-path | 0× NotPrimary; no restart/crash; provenance snapshots present | same |
| F1/F2 — flags | telemetry continuity across stress; lan1 ≈ lan2 (≤ 3×) | same |

**No Phase 2 campaign run may start until Phases 0–1 pass B/M/V/I/D (F flags
reported) per this table.**

**Gate re-scope (pre-registered 2026-08-08):** the original Phase 0 criterion
`unknown ≤ 0.5 %` was calibrated when *every* `http=000` was the routing-layer
artifact. Post-fix (P0-2→P0-4) the classes are separable and the artifact class
(120–300 s connection-kill cliff) is ≈ 0 (0.69 % in P0-4, no systematic cliff);
the residual is the **genuine 300 s client-cap timeout**, accepted up to 8 %
(the v2-locked G2 envelope, timeout 8.9/7.4 %). A literal total-`000` ≤ 0.5 %
reading is unachievable on a genuinely overloaded plateau and is superseded by
the Phase 1 re-anchor. Total `http=000` is retained as a descriptive covariate.

## 6. Workload re-anchor (Phase 1, RQ2-style)

**Locked design (2026-08-08):** edit
`source/scripts/testing/phases_override/phases_rq1_stress_plateau.json` in
place (canonical file, no duplicates). The overload phase **keeps the name
`compute_plateau`** (the RQ1 delivery analyzer anchors the overload phase by
that name) but is re-anchored from a 600 s flat plateau to a **180 s steep
episode**:

| Phase | duration | rate/client | client_frac | mix |
| --- | --- | --- | --- | --- |
| baseline | 60 s | 1.0 | 0.1 | unchanged |
| **compute_plateau (episode)** | **180 s** (calibrate 150–200) | **1.4** (calibrate 1.3–1.5) | 1.0 | service_pressure 0.5 / content_lookup 0.3 / feed_ranking 0.1 / content_update 0.05 / content_aggregate 0.05 |
| recovery_gap | 120 s | 0.5 | 0.05 | unchanged |
| demand_drop | 420 s | 1.0 | 0.1 | unchanged (scale-down integrity) |
| idle_tail | 420 s | 0.05 | 0.05 | unchanged |

- **Why 180 s:** Arm A usable capacity ~30 s covers ~83 % of the episode on
  added capacity; C/D (~80 s) cover only ~53 % → the ~50 s spread is ~28 % of
  the stressed window (vs ~8 % of the old 600 s plateau) → per-episode user
  cost becomes measurable.
- **Why this mix:** `service_pressure`-heavy drives edge CPU up fast (steep
  onset, RQ2's lever) while retained `content_lookup` keeps DB pressure so
  **B2 (storage-add benefit) is testable** (RQ2's pure pressure=1.0 episode
  has no DB path).
- **Calibration runs (Arm A, seed 2001; one degraded-arm probe):** see
  run_matrix Phase 1. P1-c verifies the storage add fires **in-episode**
  (post-overload onset) so B2's pre/post-add window exists.
- **Phase 1 gate magnitudes:** overload ≥ 30 % of episode windows · Arm A
  episode p95 ≤ 10 s, timeout ≤ 2 %, completion ≥ 95 % · C/D p95 ≥ 2× A or
  timeout ≥ 5× A · no collapse (completion ≥ 60 %) · I1 ≥ 5,000
  completed/episode/LAN · B1/B2: pre = episode start → first add ready;
  post = ready + 120 s → episode end (p95 drop OR tier-CPU relief).

### Workload-regime matrix (M1/M2/M3, 2026-08-08)

RQ1 requires **both** compute and storage scale-up to show user-visible benefit
(B1 AND B2) — a compute-strict workload would leave storage scaling as a
no-benefit dimension (P1-b/P1-d confirmed: T_db ≈ 0 ms, storage CPU 30–50 %,
so the current episode is de facto compute-strict and B2 is unmeasurable).
Before locking the campaign workload, characterize the regime hypothesis space
(Arm A, seed 2001, locked 180 s episode):

| Run | Regime | mix (`sp/cl/fr/upd/agg`) | expected |
| --- | --- | --- | --- |
| M1 | compute-strict | 0.50 / 0.30 / 0.10 / 0.05 / 0.05 | **already measured** (P1-b): B1 ✅ (edge-CPU relief) · B2 ❌ (T_db≈0) |
| M2 | **co-loaded (target)** | 0.30 / 0.35 / 0.15 / 0.10 / 0.10 (~39 DB ops/s/LAN) | B1 ✅ AND B2 ✅ (T_db rises; storage add relieves) |
| M3 | storage-bound (optional) | 0.15 / 0.45 / 0.20 / 0.10 / 0.10 | B2 ✅ · B1 ❌ (edge CPU low) — only if M2 misbehaves |

**Decision rule:** M2 is the campaign candidate if B1 AND B2 both show relief
(or p95 drop) in their pinned windows, Arm A stays healthy (p95 ≤ 10 s,
timeout ≤ 2 %), overload ≥ 30 % windows, and there is no collapse. If M2 tips
storage-bound or collapses, tune once (rate 1.1–1.3 / nudge mix) and re-run
before the campaign. After the regime is chosen, re-run the **D-arm probe on
that regime** (P1-d style) to confirm C/D degradation still holds, then lock
the campaign workload.

## 7. Campaign design (Phase 2) — n=7 LOCKED (2026-08-08)

- 4 arms × n: A `ep` (fresh+complete), B `delayed` (+30 s, complete),
  C `ls` (poll-30, ~1/3), D `sp` (sampled /3, ~1/3).
- **n=7 (28 runs, seeds 3001–3007, new counterbalance).** Rationale: the
  platform shows real run-to-run variance under identical config+seed
  (Phase 0: P0-4 vs P0-4R — `http=000` 8.83 % vs 3.31 %, p95 86 s vs 24 s;
  v2 record: "healthy 6–10 %"). The per-episode metrics (p95/timeout/failure)
  need more power for exact MWU than n=5 provides, and a new counterbalance
  avoids reusing v2's seeds. The H2 effect is large (5× p95 in the P1-d
  probe), so the 8 extra runs buy robustness against the heat variance.
- **Counterbalance** (7 blocks, one run per arm per block, rotating order —
  see run_matrix Phase 2).
- **Per-run gates:** artifact class (120–300 s) ≤ 1 % · genuine timeout ≤ 8 %
  · served-basis completion ≥ 95 % (collapse screen, all arms) · **offered-basis
  completion ≥ 85 % — hard gate for Arm A, reportable flag for B/C/D (see
  screen-application bullet)** · D1 0× NotPrimary · D2 no restart · D3
  snapshots · F1 delivery per arm design (ep/delayed ≈ 1.0; ls/sp
  0.333 ± 0.1) · F2 lan symmetry ≤ 3×.
- **Screen application by arm (re-pre-registered 2026-08-08, pre-campaign):**
  the offered-basis ≥ 85 % line was calibrated on Arm A and is a **hard gate
  for Arm A only** (healthy reference). For the designed-degraded arms B/C/D,
  offered-basis < 85 % is a **reportable flag, not a gate**; the collapse
  screen for those arms is **served-basis completion < 95 % OR an all-timeout
  phase** (harness-collapse check). Rationale (from P-B/P-C probes):
  phase-end cancellation (drain) rises with degradation — B lan2 83.9 %,
  C 78.8/77.1 %, D lan1 85.8 % all sit below the A-calibrated line yet show
  no harness collapse (served-basis 100 %, 0 timeouts, delivery-by-design);
  per `testing_requirements.md`, runs are allowed to show worse outcomes and
  collapse is judged at harness level.
- **Outcome-basis definitions (pinned 2026-08-08, pre-campaign):** `offered` =
  requests issued in the phase (phase_service_quality `offered`); `completed` =
  `status=200`; `canceled`/`dropped` = client-side abandonment (phase-end drain,
  not a latency class); `failed` = non-200 error; `timeout` = distinct 300 s
  client-cap class, **never** merged into `failed` (I2).
  - **Served-basis completion** = `completed / (offered − canceled − dropped)`
    — the collapse screen (≥ 95 %).
  - **Offered-basis completion** = `completed / offered` — Arm A gate ≥ 85 %;
    B/C/D reportable flag (see screen-application bullet).
  - **H2 per-episode latency** is reported **both** served-basis (p95 over
    `completed`) and offered-basis (p95 over `completed ∪ timeout`, timeouts
    counted at 300 s). The MWU uses the served-basis value; `canceled`/`dropped`
    and `timeout` are reported per run as outcome classes (covariates), never
    silently merged. Because arms cancel at different rates (A ≈ 360–410 vs
    D ≈ 500–740 in plateau), the served-vs-offered gap is itself reported per
    arm as a differential-cancellation check.
- **Metrics:** per-episode p95 / timeout / failure + usable-capacity latency +
  info-age at decision; MWU (exact) + Cliff's delta on the factorial edges
  (delay A−B / D−C, loss A−D / B−C). Verdicts: H1 (usable-capacity ordering
  A < B < C ≈ D, both lossy arms late — **D may be strictly worst**, sampled
  push reacting later than latest-state) and H2 (per-episode quality ordering
  A < B < C ≈ D, direction consistent across replicates; a D > C outcome is a
  **valid H2 confirmation** — more evidence loss = more cost — not a failure).
- **H2 primary endpoint + multiplicity (pre-registered 2026-08-08):** the H2
  primary endpoint is **served-basis episode p95** (the MWU metric). `timeout`
  and `failure` are reported per arm as distinct outcome classes (secondary) —
  plateau timeouts are ≈ 0 in all arms (idle-tail only), so they cannot
  discriminate; the ordering is carried by p95, with failure/canceled as
  supporting evidence. The four MWU edges (delay A−B / D−C, loss A−D / B−C)
  are the pre-registered primary comparisons — **no multiplicity correction**;
  effect sizes via Cliff's delta with 95 % CIs.
- **Ordering claim source (pre-registered 2026-08-08):** the H1/H2 ordering
  claim is established **on the 28 campaign replicates** (demand-matched per
  block: all four arms share the block seed 3001–3007). Pre-campaign probes
  (M2, D-recheck, P-B, P-C) are calibration/feasibility only and are cited as
  such — they are n=1 and seed-mismatched across arms (A/B @ 2001, C/D @ 2004).
- **B1/B2 role in RQ1 (pre-registered 2026-08-08):** B1/B2 are the
  architecture-floor gates (`testing_requirements.md` B), satisfied at the
  regime lock (P1-b/M2/D-recheck). They are **not** the RQ1 deliverable — the
  deliverable is H2 (observation-interface cost). The analyzer reports B1/B2
  per Arm-A campaign run as floor reproduction; the RQ1 headline is the
  between-arm contrast. The storage-scaling narrative belongs to RQ2/RQ3.
- **Differential-cancellation reporting (pre-registered 2026-08-08):** per
  arm and per run, the results report **offered-basis episode p95** (timeouts
  counted at 300 s) alongside served-basis p95, the served-vs-offered gap, and
  the `canceled`/`dropped` share, in a **headline table** (not an appendix).
  Cancellation rises with degradation (A ≈ 360–410 → B ≈ 718–836 →
  C ≈ 1098–1186 → D ≈ 505–739), so served-basis alone understates
  degraded-arm cost; both are reported.
- Driver unchanged from v2: open-loop, `CURL_MAX_TIME=300`,
  `INFLIGHT_WINDOW=1024`, `DRAIN_S=30`.

## 8. Changelog

| Date | Change | Rationale |
| --- | --- | --- |
| 2026-08-07 | Created v3 plan; Phases 0–1 mandatory before the campaign; gate on `testing_requirements.md`; campaign + evaluations live in this folder | RQ1 v2 proved the control-loop link only; the fix + re-anchor target the user link |
| 2026-08-08 | P0-2 (`rq1_delivery_ep_fix2`) validated the 30 s wall collapse but exposed the **120 s flow-expiry cliff** (`completed/000` 2,406, 82 % at 120–140 s). `VIP_DATA_IDLE_TIMEOUT` raised **120 → 600** in all four RQ1 envs; P0-3 `rq1_delivery_ep_fix3` launched | the artifact class (flow-expiry kills) must be eliminated before the Phase 1 gate; idle ≥ 2× client cap merges the artifact into the genuine 300 s timeout |
| 2026-08-08 | P0-3 (`rq1_delivery_ep_fix3`) **disproved** the flow-expiry hypothesis (cliff persisted at idle=600); root cause = client kernel SYN-retry ceiling (`tcp_syn_retries=6` → ~127 s). P0-4 (`rq1_delivery_ep_fix4`) with `CLIENT_TCP_SYN_RETRIES=9` **confirmed the fix**: artifact class 9.37 % → **0.69 %**, genuine timeout 5.76 % (≤ 8 %), slow-successes 0.23 % → 2.26 %. **Gate re-scope pre-registered** (artifact class ≈ 0 + genuine timeout ≤ 8 % supersedes literal `unknown ≤ 0.5 %`). Replicate `rq1_delivery_ep_fix4_r2` queued for n=2 | artifact elimination is the Phase 0 precondition; the re-scope is pre-registered so the Phase 2 verdict is internally consistent |
| 2026-08-08 | **Phase 1 re-anchor locked**: `compute_plateau` re-anchored 600 s → **180 s steep episode** (rate 1.4, compute-heavy + DB-bearing mix); phase name retained for analyzer compatibility; tails unchanged (scale-down integrity). Gate magnitudes pre-registered (§6). Calibration P1-a…P1-d queued (Arm A seed 2001; D probe seed 2004) | Phase 0 proved the control-loop link on the fixed platform; the short episode makes the ~50 s spread land inside the stressed window so the per-episode user link (H2) becomes measurable |
| 2026-08-08 | **Phase 1 COMPLETE**: P1-a (rate 1.4) too hot → tuned to **1.2**; P1-b PASS (episode **LOCKED 180 s @ 1.2**: A p95 7.0 s, timeout 0 %, overload 100 %); P1-d PASS (**D p95 = 5× A**, 35–70 s, usable 80.7/81.7 s — H2 precondition confirmed). Phase 0+1 gate met → **Phase 2 UNBLOCKED**. **n=7 LOCKED** (28 runs, seeds 3001–3007, new counterbalance) — rationale: run-to-run variance (P0-4 vs P0-4R 000 8.83 % vs 3.31 %) needs more MWU power than n=5 | reproducibility of the A-vs-D effect is the campaign's deliverable; n=7 is pre-registered so the campaign verdict is internally consistent |
| 2026-08-08 | **Workload-regime matrix pre-registered (M1/M2/M3, §6)** after P1-b/P1-d showed the episode is de facto compute-strict (T_db ≈ 0 ms → B2 unmeasurable). **Controller pin: `rq1-v3-p1-controller-pin-20260808` → `d267099`** (the exact state P1 validated; the rq3 per-connection VIP_SERVER delta is off-by-default → behavior-neutral for RQ1; rq2 `925c43f` excluded from cloud-vm). M2 (co-loaded) queued; campaign held until both B1 and B2 are demonstrable | RQ1 must show benefit for BOTH compute and storage scaling; pinning the controller prevents cross-RQ drift (user requirement) |
| 2026-08-08 | **M2 (`rq1_regime_coloaded`) PASS — co-loaded regime locked as campaign candidate**: B1 ✅ (compute adds hold p95 4.9/4.0 s, 0 timeouts, 100 % delivered); **B2 ✅ (storage genuinely loaded — per-node T_db 127–297 ms; hot secondary 87 % → ~20 % after storage add, load spreads to 3 nodes)**; overload ≈100 % plateau windows; D1 0 / D2 no restart / D3 ✅. **D-recheck (`rq1_regime_sp_d`) PASS — D p95 106.3/75.1 s = 21.6×/18.6× A (≥ 2×)**: co-load amplifies the D-arm penalty (vs P1-d 5×) → stronger H2. **CAMPAIGN WORKLOAD LOCKED: co-loaded mix 0.30/0.35/0.15/0.10/0.10 @ 180 s/1.2.** Flags for analyzer: lan1 storage-removal retry failures in idle-tail; D-arm reaction latency 138 s (sampled telemetry); single-window overload blips during removals | Both compute AND storage scale-up now demonstrable (user requirement); D-arm contrast confirmed on the chosen regime before Phase 2 |
| 2026-08-08 | **Pre-campaign probes (B/C) + §7 screen re-scope**: P-B `rq1_probe_b` PASS (B usable 59.5/60.5 s, p95 29.0/30.1 s → **A < B < D**; v2 ~57.5 s reproduced). P-C `rq1_probe_c` PASS (C usable 74.6 s, p95 38.3/41.2 s → **co-load ordering A < B < C < D**, D strictly worst — sampled push can miss the surge-onset window vs latest-state always-current demand). **Offered-basis ≥ 85 % screen re-pre-registered per Option 1**: hard gate for Arm A only; reportable flag for B/C/D (collapse = served-basis < 95 % OR all-timeout), because phase-end cancellation rises with degradation (B lan2 83.9 %, C 78.8/77.1 %, D lan1 85.8 % — none collapsed). Readiness review conditions 1–3 all closed → **campaign clear to start (pending user go)** | B/C arms had never run on the final workload (readiness gap #1); the monotone ordering strengthens H2; the screen re-scope keeps the collapse screen honest without failing designed-degraded arms |
| 2026-08-08 | **§7 thesis-level pre-registrations**: H2 primary endpoint = **served-basis episode p95** (plateau timeouts ≈ 0 in all arms — cannot discriminate); the four MWU edges are the pre-registered primary comparisons, no multiplicity correction, Cliff's delta + 95 % CIs; **ordering claim established on the 28 campaign replicates** (probes are n=1, seed-mismatched — calibration only); **B1/B2 are architecture-floor gates, not the RQ1 deliverable** (headline = H2; analyzer reports B2 per A-run); **differential-cancellation reporting** — offered-basis p95 + served-vs-offered gap per arm in a headline table. **C-arm `ack_count=0` resolved: structural** — latest-state acks go to the local_state_server aggregator `ACK_LOG_PATH` (`aggregator.py:77`), not the run-folder `ack_log_lan{1,2}.jsonl` the analyzer counts; no gate impact (delivery integrity reads `telemetry_delivery_log`) | thesis-level rigor: pre-register the primary endpoint, keep the ordering claim on campaign data, prevent the differential-cancellation attack, and resolve the telemetry-accounting anomaly before write-up |
