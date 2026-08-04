# RQ1 v2 Rework Plan — Telemetry Delivery Semantics (final evidence)

**Date**: 2026-08-04 · **Status**: ✅ **Phases 1–5 implemented** (2026-08-04) · 🚧 **Phase 6 (campaign execution) in progress — G2 open-loop calibration BLOCKED** (two problems; see below) — no campaign blocks may start until resolved

**Phase 6 execution record (2026-08-04):**
- **🚨 G2 calibration re-run (Arm A, TRUE open-loop) — `20260804_165925_rq1_delivery_ep_calib2`, exit 0, BLOCKED.** The launch fix worked (open_loop_schedule.json present, workers `--driver-mode open_loop --in-flight-window 1024 --drain-s 30.0`, 14-col CSV with `status`). But the run revealed two blocking problems:
  1. **Catastrophic overload collapse (both LANs)**: open-loop preserves offered load → plateau ≈ 120 req/s/LAN (71.6k offered each) vs the sync-driver run's ~82 req/s total. lan1 timeout_rate 87.7%, completed 8.1%, p50 21.9 s; lan2 timeout_rate 68.2%, completed 17.1%, p50 236 ms. `dropped` = 3.13% / 15.51% — both > 1% → **G2 rule triggers raising `INFLIGHT_WINDOW`** (or re-tuning offered rate).
  2. **lan1 overload-detection/scaling asymmetry**: lan1 window_log flagged 14/173 overload vs lan2 123/167, lan1 made 2 scale-ups (lan2: 6), scaled to dyn2 only, `server_count` collapsed back to 1 mid-plateau — yet lan1 was the worse-performing LAN. Inverse of v1's Arm C lan2 asymmetry.
  **Blocked pending: root-cause of the lan1 detection asymmetry + G2 calibration retune. See `results.md` §v2 for full numbers.**
- **⚠️ First two calibration runs INVALIDATED (launch-env bug, 2026-08-04):** `20260804_153342_rq1_delivery_ep_calib`, `20260804_162043_rq1_delivery_sp_calib` (exit 0) ran the **legacy sync driver**: `export`ed knobs were stripped by sudo `env_reset` before `make` (no `open_loop_schedule.json`, no "Driver mode" log line, legacy 13-col CSV, default CPU caps). **Fix applied + verified**: `_rq1_launch.sh` now passes all knobs as make command-line variables (which survive sudo). Retained as sync-driver reference only.
- Gates (a)/(b)/(c) (driver/analyzer/sampled-push selftests) already passing; (d) concurrency stress implicit in the calibration plateau (82 req/s × 300 s cap without conntrack exhaustion); (i) sync regression pending.

**Implementation record (2026-08-04):**
- P1 analyzer rework: implemented + selftest passing (`source/scripts/testing/rq1v2_p1_01_analyzer_selftest.py`, `make rq1_analyzer_selftest`).
- P2 sampled-push source: implemented + selftest passing (`source/sdn_controller/telemetry/sampled_push_source.py`, `source/scripts/testing/rq1v2_p2_01_sampled_push_selftest.py`, `make rq1_sampled_push_selftest`); wired in `main_n1.py`/`main_n2.py`; `env/rq1_sampled_push.env`.
- P3 stats: implemented (`docs/research_questions/v2/rq1/rq1v2_p3_01_stats.py`), smoke-tested; C8 verdict + non-surge metrics included.
- P4 lan2 asymmetry: implemented (`docs/operation/testing/experiment/v2/rq1/rq1v2_p4_01_lan2_asymmetry.py`), smoke-tested.
- P5 docs: `experiment_plan.md`, `run_matrix.md` §9, `analysis_focus.md` §0, `results.md` v2 template, `thesis_overview.md`, `thesis_structure.md`, `tese/references.bib` (Schroeder 2006) all updated.

**Deviations from the plan (recorded):**
- Phase boundaries are **derived from the generator `phase` label** (not schedule-anchored then validated): the open-loop supervisor shifts later phases by the phase-boundary drains and workers progress independently, so contiguous anchoring is wrong; the validation is phase-order (monotonic min `sent_at`) with a non-fatal span warning.
- `timeout_rate` denominator is `offered − canceled − dropped` (canceled = phase-boundary drain artifacts; dropped = client-side admission, never reached the service).
- `tese/references.bib` `Schroeder2006OpenVersusClosed` added here (also closes the RQ2 v2 Phase 4.7 gap).
**Review gate**: 1 round of Reviewer (deepseek-v4-flash, to-be-implemented) —
2 🔴 / 10 🟡 / 13 🔵; all 🔴/🟡 resolved, useful 🔵 incorporated (see §8).
**Supersedes as primary evidence**: the 2026-08-02 9-run campaign
(`results.md`) becomes **supporting/characterization evidence**.
**Thesis gates**: `thesis_overview.md` §5/§6/§8 and `thesis_structure.md` §5.4
(open-loop driver, Mann–Whitney U + Cliff's delta, 4-arm 2×2 factorial).

---

## 1. Why this rework exists

The 9-run RQ1 campaign (2026-08-02, 3 arms × 3 replicates) is directionally
correct — the completeness-vs-info-age tradeoff reproduces, and usable-capacity
latency orders A < B < C — but it is **not** final thesis evidence. The rework
completes the experimental design and removes the confounds:

| # | Gap | Evidence |
|---|---|---|
| G1 | **Latency-coupled sync driver** — plateau request counts differed per arm (A ~10.6–11.5 k, B ~5.1–6.2 k, C ~7.0–7.3 k); arms faced different demand | `results.md` caveats; `traffic_generator.py` legacy `client_loop()` (1 in-flight/client) |
| G2 | **p99 censored at 30 s** (`CURL_MAX_TIME=30`); timeout conflated with failure (`http_status != 200`) | `results.md`; legacy analyzers check `http_status == "0"` |
| G3 | **No statistics** — n=3 cannot reach MWU significance; no effect sizes | `results.md`; thesis §5.4 mandates MWU + Cliff's delta |
| G4 | **Delay-vs-loss not isolated**: Arm C (poll-30) has both loss *and* up-to-30 s delay — the completeness×info-age 2×2 is missing the fresh+lossy cell | `polling_source.py` (interval couples loss+delay); C info-age-at-decision 16.8/11.1 s |
| G5 | **Post-hoc C9 metric rescue** — first-decision latency invalid for Arm B (stale-boundary artifact); criterion re-anchored onto usable-capacity latency after data | `results.md` main-campaign caveat |
| G6 | **Analyzer phase-bucketing artifact** — anchored boundaries misaligned with the generator's plateau overrun (~52–57 s), inflating `recovery_gap` counts 5–20× and producing a fake "10.96% spike" | `results.md` deep-verification note; `rq1_delivery_per_run.py` `_phase_of` / anchored `phase_times` |
| G7 | **Arm C lan2 plateau failure asymmetry** — 11–12% lan2 vs 2–4% lan1, run-invariant, unexplained, unique to Arm C | `results.md` finding 3 |
| G8 | **Scale-down decision log incomplete** — `container_events` shows 1.5–3× more removals than logged scale-down decisions (replacement/churn not logged) | `results.md` C7 caveat |
| G9 | **C8 transient-quality null** — non-surge rates 2–4% across arms, not arm-discriminative; Arm A itself violates | `results.md` C8 verdict |

**Decision basis (user-approved, 2026-08-04):** 4-arm full 2×2 factorial,
n=5, 20 runs, 5 counterbalanced blocks. Add the missing cell (Arm D =
fresh+lossy, **sampled-push** source) so the delay-vs-loss attribution is
clean. The shared open-loop driver (RQ2 v2 Phase 1, self-test passing) removes
G1/G2; RQ1-specific work removes G3–G9.

---

## 2. Locked requirements

1. **Driver**: re-run under the existing open-loop driver —
   `TRAFFIC_DRIVER_MODE=open_loop`, `CURL_MAX_TIME=300`, `INFLIGHT_WINDOW=1024`,
   `DRAIN_S=30`. Offered/completed separated; `timeout` recorded as a distinct
   outcome class (never merged into `failure`).
2. **Pre-registered reaction metric**: primary = **usable-capacity latency**
   (demand-shift → spawn ready) for **all arms**. First-decision latency is
   delivery-timing-confounded (stale-boundary for B, poll-timing for C,
   first-window miss possible for D) → reported **descriptively only**, for
   every arm, never as a primary metric or a gate.
3. **RQ1 analyzers**: status-aware (failure = completed & `http_status != 200`;
   `timeout_rate` = `status=timeout` / (offered − canceled − dropped);
   `dropped`/`canceled` excluded from latency + failure and from the
   timeout-rate denominator, counted in offered, reported separately);
   client-side phase attribution via the **generator `phase` label**;
   decision/window-side boundaries **derived from the generator labels**
   (the open-loop supervisor shifts later phases by the phase-boundary drains
   and workers progress independently, so contiguous anchoring is wrong; the
   validation is phase-order with a non-fatal span warning);
   `sampled_push` added to the recognized delivery modes.
4. **Arm C lan2 asymmetry**: pre-flight diagnostic on the open-loop calibration
   runs; full root-cause during/after the campaign; no Arm C quality claim until
   resolved or bounded.
5. **Scale-down claim**: reported from `decision_log` **and** `container_events`
   jointly (bounded claim). **No controller change** (RQ2 campaign is imminent
   and the controller is volume-mounted).
6. **Statistics**: mirror `rq2v2_p2_03_stats.py` exactly — two-sided
   Mann–Whitney U (exact enumeration for small n) + Cliff's delta; no censored
   value enters MWU; missing-value exclusions (≥ 3 defined runs/cell); latency
   percentiles descriptive-only with a censoring flag. **No confidence
   intervals claimed** (the RQ2 script computes none).
7. **C8**: cross-arm comparison on non-surge `timeout_rate` + `failure_rate`
   under equal offered load, per generator `phase` label, `canceled` rows
   excluded (the phase-boundary drain bounds plateau spillover by
   construction). May honestly be a null result.
8. **Docs**: edit canonical files in place (no duplicates); `tese/references.bib`
   gains `Schroeder2006OpenVersusClosed` (manual DBLP entry — also closes the
   RQ2 v2 Phase 4.7 gap).

---

## 3. Approach comparison (recorded)

| | **A — 4-arm full 2×2 (chosen)** | B — 3-arm mechanism comparison |
|---|---|---|
| What | Add fresh+lossy sampled-push arm (D); n=5, 20 runs | Keep A/B/C; n=5, 15 runs; reframe RQ as mechanism comparison |
| Answers "delay, loss, or both"? | ✅ clean factorial | ❌ C's loss stays delay-contaminated |
| New telemetry source? | ✅ yes (consumer-side filter, ~1 module) | ❌ none |
| Effort / Risk | Medium / Medium | Low / Low |
| Edge impact | delivery path gains one source; controller logic otherwise untouched | none |

**Why A:** RQ1's thesis question *is* the delay-vs-loss attribution; the 3-arm
design is a 2×2 minus one cell and cannot answer it. The added source is a
subclass of the existing event-preserving source — no controller logic change.

---

## 4. Phased task breakdown

File naming: new files `<scope>_p<phase>_<nn>_<name>.<ext>`, scope = `rq1v2`;
canonical files are edited in place (never duplicated).

### Phase 1 — RQ1 analyzer rework · scope `rq1v2`

**Goal**: make the RQ1 analyzers contract-correct under the new driver, remove
the phase-bucketing artifact, and add Arm D support.

| # | File | Action | Task |
|---|---|---|---|
| 1.1 | `docs/operation/testing/experiment/v2/rq1/analysis/rq1_delivery_per_run.py` | Edit in place | (a) status-aware service quality per §2.3 (replace `is_failed()` `http_status=="0"` logic); (b) client-side phases from the generator `phase` label; decision/window-side from schedule-anchored boundaries validated against labels (tolerance 1 window → run fail); (c) add `sampled_push` mode to recognized delivery-log modes; (d) offered vs completed per phase; (e) per-arm run-suffix support `sp`. |
| 1.2 | `docs/operation/testing/experiment/v2/rq1/analysis/rq1_delivery_comparison.py` | Edit in place | Status-aware timeout graph (`timeout_rate`, not `http_status=="0"`); add 4th arm D (`sp`); per-replicate scatter + medians + IQR; stats-overlay hooks. |
| 1.3 | `docs/operation/testing/experiment/v2/rq1/rq1v2_p1_01_analyzer_selftest.py` | **Create** | Synthetic-status CSV: timeout/dropped/canceled attribution correct; phase-label vs anchored mismatch detected (run fail); `sampled_push` parsed. Gate = new Makefile target `rq1_analyzer_selftest`. |

**Phase-1 gate:** analyzer selftest passes; no stale consumer reintroduces the
cap artifact (shared consumers already audited in RQ2 v2 Phase 1.5; the RQ1
analyzers were the remaining gap).

### Phase 2 — Sampled-push source (Arm D) · scope `rq1v2`

**Goal**: implement the missing fresh+lossy cell — delivers every Nth window
immediately (sub-second), drops the rest.

| # | File | Action | Task |
|---|---|---|---|
| 2.1 | `source/sdn_controller/telemetry/sampled_push_source.py` | **Create** | `SampledPushTelemetrySource(EventPreservingTelemetrySource)`: in-order pull from the durable window log; per-URL counter; **deliver every `SAMPLE_EVERY`-th window** (cache + `delivery_log` mode `sampled_push` + ack + `on_update`); advance `last_seq` for every window so it never falls behind; sub-second delivery (`EVENT_POLL_INTERVAL_S=0.5`); dropped windows are not delivered — the analyzer computes misses from the universe (same semantics as the poll arm); never blocks, no replay; empty windows passed to `on_update`, cached only if non-empty (mirrors event-preserving). **Limitation documented:** deterministic every-3rd sampling; the workload is constant-rate so periodicity-aliasing risk is low. |
| 2.2 | `source/sdn_controller/main_n1.py`, `main_n2.py` | Edit in place | Add `TELEMETRY_SOURCE=sampled_push` branch → `SampledPushTelemetrySource(endpoints, sample_every=int(os.environ.get("SAMPLE_EVERY", "3")), poll_interval_s=float(os.environ.get("EVENT_POLL_INTERVAL_S", "0.5")), on_update=...)`. |
| 2.3 | `docs/operation/testing/experiment/v2/rq1/env/rq1_sampled_push.env` | **Create** | Copy of `rq1_event_preserving.env` + `TELEMETRY_SOURCE=sampled_push` + `SAMPLE_EVERY=3`. (Distinct named regime — allowed by the canonical-env rule; RQ1 arms use per-arm env files by design.) |
| 2.4 | `source/scripts/testing/rq1v2_p2_01_sampled_push_selftest.py` | **Create** | Synthetic window log: delivered fraction ∈ [0.30, 0.36]; delivery delay p50 < 2 s; in-order; gap handling unchanged; `SAMPLE_EVERY=1` ≡ event-preserving (regression). Gate = `make rq1_sampled_push_selftest`. |

**Phase-2 gate:** selftest passes (host + inside a netns); dry-run delivered
fraction ≈ 1/3; info-age at scale-up p50 < 2 s.

**Deployment sequencing (RQ2 safety):** the branch is additive and inert unless
`TELEMETRY_SOURCE=sampled_push`. Implement + selftest **locally first**; sync to
the VM **between RQ2 runs/blocks, never mid-run**; smoke-run before any RQ1 v2
block. The RQ2 v2 campaign (18-run, 6 cells × 3) keeps priority on the VM.

### Phase 3 — Pre-registered metrics & stats · scope `rq1v2`

**Goal**: pre-register the primary hierarchy and add the RQ1 statistics layer
before any run.

| # | File | Action | Task |
|---|---|---|---|
| 3.1 | `docs/operation/testing/experiment/v2/rq1/analysis_focus.md` | Edit in place | Pre-registered hierarchy. **Primary attribution pairs (factorial edges, each axis at both levels):** delay — **A–B** (fresh+complete vs stale+complete) and **D–C** (fresh+lossy vs stale+lossy); loss — **A–D** (complete+fresh vs lossy+fresh) and **B–C** (complete+stale vs lossy+stale). **Headline tradeoff (descriptive + Cliff's delta only, not axis-attribution):** **B–D** (stale+complete vs fresh+lossy) and A–C. Metrics: usable-capacity latency, `timeout_rate`, `failure_rate` (completed-only), time-to-recover (scale-down from `recovery_gap` start), info-age at decision. Delivered fraction + info-age at scale-up = manipulation checks (no stats needed). Latency percentiles descriptive-only. |
| 3.2 | `docs/research_questions/v2/rq1/rq1v2_p3_01_stats.py` | **Create** | Mirror `rq2v2_p2_03_stats.py` exactly: two-sided MWU (exact enumeration when n_a + n_b ≤ 16) + Cliff's delta, per pre-registered pair; no censored value enters MWU; ≥ 3 defined runs/cell minimum; unified denominators; `stats_summary.csv` + console table. |
| 3.3 | `docs/operation/testing/experiment/v2/rq1/experiment_plan.md` | Edit in place | C8 claim decision pre-registered (§2.7). New success criteria C1–C9 for v2 (ack convention: `ack_log` required for A/B, **partial for D** (delivered windows only), absent by design for C). |

**Phase-3 gate:** stats script smoke-tests on synthetic n=5 data.

### Phase 4 — Arm C lan2 asymmetry + scale-down claim bounding · scope `rq1v2`

**Goal**: resolve or bound the two data-integrity threats before any Arm C
quality claim.

| # | File | Action | Task |
|---|---|---|---|
| 4.1 | `docs/operation/testing/experiment/v2/rq1/rq1v2_p4_01_lan2_asymmetry.py` | **Create** | Per-run per-LAN plateau failure/timeout for all arms under open-loop; load-distribution check (VIP routing, per-backend request counts, poll delivery per LAN); verdict: cause identified or bounded. **Pre-flight version runs a diagnostic on the open-loop calibration runs** (data-availability gate); full root-cause after the campaign. |
| 4.2 | `analysis_focus.md` + `results.md` v2 section | Edit in place | Scale-down claims reported from `decision_log` **and** `container_events` jointly (bounded claim; no controller change). |

### Phase 5 — Experiment plan + thesis docs · scope `rq1v2` (edit in place)

| # | File | Task |
|---|---|---|
| 5.1 | `experiment_plan.md` | v2 section: 4 arms, n=5, 20 runs, open-loop knobs, pre-registered pairs/metrics, new gates (driver/analyzer/sampled-push selftests, stats, censoring, bucketing, scale-down arming), updated hypothesis table + D row, ack convention, v1 marked supporting. |
| 5.2 | `run_matrix.md` | v2 matrix: 4 arms × 5 = 20 runs, 5 counterbalanced blocks of 4 (seeds 2001–2005 = driver `RANDOM_SEED` base, distinct-order verification, new `counterbalance_order_v2.csv` — never overwrite v1). Launch: `TRAFFIC_DRIVER_MODE=open_loop CURL_MAX_TIME=300 INFLIGHT_WINDOW=1024 DRAIN_S=30`. **Arm C: `POLL_INTERVAL_S=30` on the shell (Docker `-e` override trap — restated from v1; must not be dropped).** Arm D: `rq1_sampled_push.env`. Run suffixes: `ep`/`delayed`/`ls`/`sp`; checkpoint C4 arm set updated. |
| 5.3 | `analysis_focus.md` | Status-aware metrics, `sampled_push` mode, pre-registered hierarchy, stats contract, censoring rule, unified denominators, phase-label bucketing rule, RQ1 concurrency budget (§4 Phase 6). |
| 5.4 | `results.md` | Restructure as the v2 template (timeline + per-arm tables + judgment); v1 retained as appendix/supporting record with caveats. |
| 5.5 | `tese/Notes/thesis_overview.md` | §5: RQ1 final protocol implemented; §6 RQ1: 4-arm 2×2 + D arm; §8 note. |
| 5.6 | `thesis_structure.md` | §5.4: open-loop driver implemented for RQ1; §7.3 limitations (n=5, driver fixed, factorial). |
| 5.7 | `tese/references.bib` | Add `Schroeder2006OpenVersusClosed` (manual DBLP entry; NSDI 2006, no reliably resolvable DOI). |

### Phase 6 — Campaign execution (cloud VM, via Edge Experiment Runner)

1. **Pre-flight (hard gates, fail-fast):** (a) `make driver_selftest` (host +
   netns) — already passing; (b) `make rq1_analyzer_selftest`; (c) `make
   rq1_sampled_push_selftest`; (d) **concurrency stress check** — aggregate
   in-flight at plateau rate 5.0 × 24 clients × 300 s cap must not exhaust
   container/conntrack connection limits (tune limits if it does); (e) **G2
   calibration under open-loop** — the plateau rate 5.0 with
   `INFLIGHT_WINDOW=1024` means worst-case in-flight/client = 1500 > window →
   **`dropped` is possible by design** and is a designed, reported outcome
   (counted in offered, excluded from latency/failure; accounting validated by
   the driver Scenario-B self-test). Decision rule: if calibration `dropped` >
   1% of offered, raise `INFLIGHT_WINDOW` up to the concurrency limit, else
   keep 1024 — recorded in the plan; (f) **per-arm scale-down arming check**
   (esp. Arm D — its ~30 s delivery cadence stretches the 3-of-6 below-window
   accumulation; must fire ≥ 1 scale-down decision/LAN before blocks start —
   the v1 P3 failure mode); (g) Arm D dry-run (fraction ∈ [0.30, 0.36],
   info-age < 2 s); (h) lan2 asymmetry diagnostic on calibration runs; (i)
   legacy `sync`-mode regression smoke. **Blocks do not start until all pass.**
2. **Main campaign:** 4 arms × 5 = 20 runs, 5 counterbalanced blocks (seeds
   2001–2005). ~20 runs × ~30–35 min (incl. 3 phase-boundary drains + run-end
   drain of 30 s each + setup) ≈ 11–12 h ≈ 1.5–2 VM-days, **plus** pre-flight /
   calibration (~4–6 runs ≈ 3 h).
3. **Per-run analysis:** delivery integrity, info-age, reaction
   (capacity-anchored), scale-down (decision_log + container_events jointly),
   service quality (status-aware), overhead.
4. **Cross-arm:** updated comparison graphs (per-replicate scatter, medians,
   IQR, Cliff's delta, MWU p on pre-registered pairs); stats summary.
5. **Post-run:** `post_run_analysis.md` + `results.md` v2 judgment; archive raw
   run folders.

**Phase-6 gates:** all runs exit 0; **per-arm env verification** — A/B:
`TELEMETRY_SOURCE`; C: `TELEMETRY_SOURCE=poll` **and shell `POLL_INTERVAL_S=30`**;
D: `TELEMETRY_SOURCE=sampled_push` and `SAMPLE_EVERY=3` (from env snapshot);
driver-mode/window/drain verified from the **run log's printed config line**
(`run_experiment.sh` echoes "Driver mode: open_loop (window=…, drain=…)" — these
shell-only knobs never appear in `controller_env_snapshot.env`); 0×
`NotPrimaryOrSecondary`; no controller restart; stats on all pre-registered
pairs meeting the ≥ 3-defined-runs cell minimum, exclusions recorded.

---

## 5. Dependencies

- Phase 1 before 3–6 (analyzer selftest must pass). Phase 2 before 5–6
  (sampled-push selftest must pass). Controller code is volume-mounted → no
  image rebuild. `aiohttp` on the VM (already installed).
- **RQ2 v2 campaign has VM priority** (18-run, 6 cells × 3); RQ1 v2 controller sync is sequenced
  between RQ2 runs/blocks (the sampled-push branch is inert unless
  `TELEMETRY_SOURCE=sampled_push`). RQ1 v2 campaign runs after RQ2 (or
  interleaved per user).
- Env files (incl. `rq1_sampled_push.env`) synced to the VM before Phase 6.
- Phase 5 docs edits can proceed in parallel with Phases 1–4 but must be
  complete before Phase 6.

## 6. Documentation updates (summary)

`experiment_plan.md`, `run_matrix.md`, `analysis_focus.md`, `results.md`
(all in `docs/operation/testing/experiment/v2/rq1/`), `thesis_overview.md`,
`thesis_structure.md`, `tese/references.bib`, plus this plan doc
(`docs/operation/testing/experiment/v2/rq1/rq1_v2_rework_plan.md`).

## 7. Out of scope (explicit)

- No controller change for scale-down logging (bounded claim only).
- No changes to the RQ2 campaign or its `ba-strict` work.
- Tier 1 selective sync / persistent reserves / cross-region placement remain
  disabled (thesis §2).
- No per-RQ1 phase file — RQ1 keeps the control-group
  `phases_stress_plateau.json` (rate 5.0 unchanged); the concurrency budget is
  handled via `INFLIGHT_WINDOW` / `dropped` semantics, not a workload edit.
- RQ3 remains separate.

## 8. Review changelog (2026-08-04)

**Round 1** (Reviewer, deepseek-v4-flash, `--to-be-implemented`): 2 🔴 / 10 🟡 /
13 🔵. Resolutions applied in this revision:

- 🔴 `sample_every` spec fixed — `int(os.environ.get("SAMPLE_EVERY", "3"))`,
  not `int(SAMPLE_EVERY, 3)` (the latter was a startup crash).
- 🔴 Arm C `POLL_INTERVAL_S=30` **shell** requirement restored in §5.2 launch
  spec + the Phase-6 knob gate (the draft had silently dropped it → C would run
  at poll-10, destroying the factorial).
- 🟡 RQ1 concurrency budget rewritten honestly: rate 5.0 + window 1024 →
  `dropped` possible by design (a reported outcome), calibrated in G2 with a
  recorded decision rule; removed the false `≤ 3 req/s/client` arithmetic.
- 🟡 "exact CIs" claim removed — the RQ1 stats script mirrors
  `rq2v2_p2_03_stats.py` exactly (exact-enumeration MWU + Cliff's delta; that
  script computes no confidence intervals).
- 🟡 Pre-registered pairs restructured to the factorial edges (delay: A–B,
  D–C; loss: A–D, B–C); diagonals B–D/A–C demoted to headline-tradeoff,
  descriptive + Cliff's delta only.
- 🟡 Phase attribution: generator `phase` label for client-side metrics;
  schedule-anchored boundaries for decision/window-side metrics with an
  explicit 1-window tolerance + run hard-fail.
- 🟡 Phase 4.1 vs Phase-6 pre-flight timing reconciled (pre-flight diagnostic on
  calibration runs; full root-cause post-campaign).
- 🟡 Per-arm scale-down arming gate added (esp. Arm D — the v1 P3 failure
  mode).
- 🟡 Knob gate made per-arm (`SAMPLE_EVERY`/`POLL_INTERVAL_S`/`TELEMETRY_SOURCE`)
  + driver knobs verified from the run log's printed config line (shell-only
  knobs never appear in env snapshots).
- 🟡 C8 spillover bounded by a pre-registered rule (generator phase label +
  `canceled` exclusion; the phase-boundary drain bounds spillover by
  construction).
- 🟡 Phase 2.2 vs RQ2 deployment sequenced (additive/inert branch; local
  selftest first; VM sync between RQ2 runs/blocks).
- 🔵 Arm D run suffix `sp` + checkpoint C4 arm set updated; selftests placed per
  repo convention (`source/scripts/testing/`); ack convention extended to D
  (partial); "results template" → `results.md` v2 section; sampling-aliasing
  documented as a limitation; first-decision latency declared descriptive-only
  for **all** arms; stats placement/seeds clarified (driver `RANDOM_SEED`, seeds
  2001–2005); stats-gate wording made satisfiable with missing-value
  exclusions; wall-clock estimate includes pre-flight; tolerances defined
  (fraction ∈ [0.30, 0.36], info-age p50 < 2 s).
