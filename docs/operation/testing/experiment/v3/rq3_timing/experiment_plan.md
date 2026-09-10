# RQ3 Timing — Readiness-Loss Relief Contrast under Demand Escalation — Plan

**Family:** reframed RQ3, Family 4 (`rq3_timing`). Family 3
(`rq3_qoe`, quota ladder) is **STOPPED and superseded** (2026-09-08): its
plateau-saturation failure rate was structurally capped at ~1.5% (driver
patience `CURL_MAX_TIME=300 s` makes timeout share bimodal; arm differences
are transition-scoped but the P4 workload produced ~1 spawn/run). This family
keeps the three arms and both fault cells, fixes the quota at 0.12, and sweeps
the `compute_plateau` **rate** instead — so the old static tier is visibly
overloaded when solo, while hybrid/reconcile recover into a healthy plateau
tail after relief arrives. The contrast is **relief presence vs absence**,
measured on the slow-share axis.

**Status:** pre-registration drafted 2026-09-08, approved by user (all six
decision points). No run has launched.

## 1. Objective

Show that under total readiness-event loss (`loss_all`), the `event_only` arm
(no recovery path) degrades user service **visibly and boundedly** on the
slow-share axis, while `hybrid` (20 s fallback) and `reconcile` (10 s poll)
recover and stay healthy in the plateau tail — and certify that contrast at
n=6 blocks only after a **reproducible preflight signal** (3 independent
seeds, power margin).

## 2. Reasonableness boundaries (hard)

- No controller/application code changes; fault knobs and arm env deltas
  reused **byte-identical** (`rq3rob_event_only.env`, `rq3rob_loss_all.env`,
  `rq3sat_direct.env`, `rq3sat_discovery.env`).
- Quota fixed at `EDGE_CPUS=0.12` (attested in-band). Single swept axis:
  plateau rate `S ∈ {2.0, 2.5, 3.0}`.
- Workload: `compute_plateau` 600 s, pure-compute mix (`service_pressure`
  1.0) — no storage-tier confound.
- A collapsed regime (controls never recover, driver collapse, baseline
  errors) is **invalid** — never evidence, never chased by raising S further.

## 3. Arms and cells (unchanged)

| Arm | Configuration | Behavior under `loss_all` |
| --- | --- | --- |
| `event_only` | direct + fallback 130 s (inert) | events dropped → backends abandoned → **old tier solo forever** |
| `hybrid` | `rq3sat_direct.env` (fallback 20 s) | relief ≈ onset→decision→spawn→admit (~50–75 s), then pooled |
| `reconcile` | `rq3sat_discovery.env` (10 s poll) | relief ≈ ~10 s earlier than hybrid |

Cells: `none` (health floor) and `loss_all` (total event loss). `loss_alt` is
dropped — the dose is covered by `none` vs `loss_all` plus boundedness.

## 4. QoE measurement contract (family-defined)

- Window: `compute_plateau` bounds from the run's `phases_snapshot.json`
  (labeled-row `phase_bounds`), rows selected by `sent_at`.
- **Primary (gated): slow-share** `slow_rate = #(service rows with
  status=="timeout" OR latency_s > 1.0 s) / (completed + timeout)`, pooled;
  per-LAN descriptive. Timeouts slow unconditionally.
- Secondary (descriptive, never gated): `bad_rate`, `failure_rate`,
  `timeout_rate`, completed p50/p95/p99, `slow_5s`. **Timeout class is
  expected rare** — the per-phase driver drain (`DRAIN_S=30`) truncates
  long in-flight requests; timeouts can only come from requests dispatched in
  the first ~300 s of the plateau.
- **Relief-completion window (gated): plateau tail** = last 300 s of
  `compute_plateau`; controls healthy iff hybrid **and** reconcile pooled
  `slow_rate ≤2 pp` in the tail.
- Contrast `Δ_slow = slow_rate(event_only) − max(slow_rate(hybrid),
  slow_rate(reconcile))`, plateau pooled; lock bar ≥5 pp.
- **Onset-window contrast (co-primary, contract v2, amendment 2026-09-08,
  user-approved):** the readiness-loss contrast is onset-transient-dominated,
  so the acute demand-onset window is measured and gated alongside the
  full-plateau Δ_slow. `onset Δ_slow = slow_rate(event_only) −
  max(slow_rate(hybrid), slow_rate(reconcile))` over the first
  `TIMING_ONSET_S = 150 s` of `compute_plateau` (labeled-row onset).
  Screens, lock and E require BOTH the full-plateau and the onset-window
  Δ_slow ≥5 pp; the lock power margin (median ≥7 pp) applies to both.
- Boundedness: `event_only` pooled `slow_rate ≤25 %` (per screen and, at E,
  median + ≥4/6 blocks).
- Floors: ≥5,000 pooled / ≥1,000 per LAN plateau; baseline pooled ≥100 /
  per-LAN ≥50; driver-clean `cancel_rate <5 %`; baseline bad ≤1 % + http000=0.

## 5. Stages — preflight signal first, E only after lock

**P1 — discovery screen (seed 5301, rate S, 3 `loss_all` arms).** Gates:
V1 **anchored on the hybrid run**: old-tier pool CPU pre-first-ready median
≥60 % (amendment 2026-09-08 — the demand-escalation design makes pre-ready
p95 spikes expected, so there is no p95 upper cap; regime reasonableness is
enforced by relief completion + boundedness + driver-clean); floors;
driver-clean; baseline health; quota 0.12; no plateau scale-down; mechanism
per arm (event_only 0 admitted / ≥2 abandoned per LAN / mode=all; hybrid all
`probe_fallback` ≥1/LAN; reconcile all probe ≥1/LAN); **relief completion**
(controls plateau-tail slow ≤2 pp). Verdict: `candidate` iff eligible ∧
full-plateau Δ_slow ≥5 pp ∧ onset-window Δ_slow ≥5 pp ∧ event_only bounded;
visible-but-unbounded → `stop_null`.

**P2 — reproducibility (seeds 5302, 5303, ×4 runs = 3 arms `loss_all` +
`event_only`×`none`).** Per-seed gates: all P1 gates + none-cell healthy
(bad ≤1 % full plateau ∧ **plateau-tail** slow ≤2 pp — contract-v2 none-cell
amendment 2026-09-08: a no-fault run pays the same universal demand-onset
transient as every arm, so the none-cell slow health floor is the plateau
TAIL, consistent with the loss_all controls) + boundedness. Verdict `confirm`
per seed.

**Lock rule (the preflight signal):** every screen Δ_slow ≥5 pp **and** onset
Δ_slow ≥5 pp (co-primary) and screen median Δ_slow ≥7 pp **and** onset Δ_slow
median ≥7 pp (power margin on both) and every screen
eligible/bounded/relief-complete. **Marginal** (all ≥5 pp on both, either
median <7 pp): one extra seed 5304. **Lock interpretation (amended
2026-09-08, user-approved):** with an extra seed run, the lock is the
**≥3-of-≥4 independent-seed reproducible majority** (≥5 pp full AND onset per
locked seed, medians ≥7 pp) — a single genuine stochastic outlier seed (weak
event_only draw and/or a reconcile tail transient, still onset-passing) does
not block the lock; it is recorded with its diagnosis. Monotone failures
(boundedness, none-cell health, relief never completes, driver-unclean) →
`stop_null` (STOP-NULL report). On lock: `rq3tim_preflight_lock.json` (rate,
quota, screens, deltas, onset deltas).

**S-ladder discipline:** ascend only when under-saturated (V1 median <60 %);
never ascend past driver-unclean or p95 >95 %; midpoint screen at 2.25 only
if 2.0 under-saturates while 2.5 breaks driver-clean. No qualifying rung by
3.0 → NULL report.

**E — evidence (only after the lock file):** 3 arms × 2 cells × 6 blocks =
36 runs, seeds 5201–5206, arm rotation per block, full reset between runs.

## 6. E-stage hypotheses (locked rate, all pre-registered)

- **H-T1 (headline):** per-block full-plateau `Δ_slow` ≥5 pp in ≥4/6
  assessable blocks ∧ full median ≥5 pp **AND** per-block onset-window
  `Δ_slow` ≥5 pp in ≥4/6 assessable blocks ∧ onset median ≥5 pp
  (contract v2 co-primary; amendment 2026-09-08); one-sample MWU + Cliff's δ
  on the Δ list vs zeros. Block assessable iff floors + driver-clean +
  controls plateau-tail slow ≤2 pp + Δ computable; ≥3/6 excluded ⇒ not
  assessable. Boundedness: event_only slow median ≤25 % ∧ ≥4/6 ≤25 %.
- **H-T2 (relief completion):** hybrid ∧ reconcile tail-slow ≤2 pp in ≥5/6
  blocks; time-to-relief (plateau onset from labeled rows → first 200 served
  by a new backend via `backend_id`) finite ∧ ≤120 s in ≥5/6 blocks, hybrid
  median > reconcile median; event_only zero new-backend successes in ≥5/6
  blocks.
- **H-T3 (health floor):** none-cell all arms bad ≤1 % (full plateau) ∧
  **plateau-tail** slow ≤2 pp (contract-v2 none-cell amendment 2026-09-08).
- Pass = H-T1 ∧ H-T2 ∧ H-T3. Failed directions reported, never chased.

## 7. Implementation surface

1. `source/scripts/testing/rq3tim_p1_01_launch_run.sh` (mirror qoe launcher;
   fixed quota 0.12; **rate arg asserted against the frozen phases.json**;
   labels `rq3tim_<cell>_<arm>_<ordinal|block>`).
2. `source/scripts/testing/rq3tim_p0_01_prepare_tag.py` (manifest; protected
   surface + arm envs identical to rq3qoe minus `loss_alt`).
3. `source/scripts/testing/rq3tim_p0_02_analyzer_selftest.py` (runs the
   shared selftest harness; timing fixtures included).
4. `source/scripts/testing/rq3tim_p0_03_preflight.sh` (static checks).
5. Analyzer `readiness_robustness.py` — `timing-screen` (p1/p2/lock) and
   `timing-campaign` (H-T1…T3) subcommands; reuses `_qoe_status` slow-share
   math; `timing_tail_slow` (last-300-s tail), `timing_onset_slow`
   (first-150-s onset, contract-v2 co-primary) and `timing_relief_metrics`
   (time-to-relief via `backend_id`).
6. `source/scripts/testing/phases.json` — edited in place per rung during P1
   (frozen copy runs the campaign; the repo canonical is set to the locked
   rate at lock time).
7. Docs: `docs/operation/testing/experiment/v3/rq3_timing/` {this file,
   `run_matrix.md`, `preflight_campaign.md`, `preflight_log.md`}; STOP note in
   `rq3_qoe/preflight_log.md`; cross-references updated.

Non-goals: no controller/application changes, no new images, no new env
files, thesis text unchanged until evidence.

## 8. Cost and stop rules

P1 ≤9 runs + P2 8 (+4 marginal) + E 36 = ≤57 runs ≈ 43 h worst case; typical
lock at S=2.0: ≈31 h. E runs only after `rq3tim_preflight_lock.json` exists.
Every preflight run gets a checkpoint row in `preflight_log.md` with
GO/STOP/DIAGNOSE verdicts.

## 9. Validation before VM

Shared selftest (qoe + timing paths, 29 checks) · pyflakes/py_compile ·
bash -n · rate-assert launcher negatives (wrong rate, mismatched phases.json,
bad label) · env-merge proof · manifest/tag identity. No experiment executes
during implementation.

## 10. Changelog

- 2026-09-08 — pre-registration approved by user. Preflight signal defined
  as P1 + P2 across 3 seeds with a ≥7 pp median power margin (marginal →
  one extra seed, bounded). Supersedes `rq3_qoe` (STOP recorded there).
- 2026-09-08 (amendment, user-approved) — rq3tim V1 pressure gate amended:
  V1 = hybrid old-tier pre-first-ready median ≥60 % only; dropped the reused
  qoe p95 ≤95 % cap and upper median bound (the escalation design makes
  pre-ready p95 spikes expected; reasonableness is enforced by relief
  completion, boundedness and driver-clean).
- 2026-09-08 (contract v2 amendment, user-approved — **Option A**) —
  onset-window co-primary added: a single 600 s plateau yields only one onset
  transient and the ~85 % quiet tail dilutes the full-plateau mean contrast
  (P1 full Δ 9.08 pp vs onset Δ 41.71 pp at seed 5301). The first-150-s
  onset-window `Δ_slow` becomes a **co-primary** beside the full-plateau
  `Δ_slow`: screens/lock/E gate both ≥5 pp and the lock median power margin
  (≥7 pp) applies to both. Analyzer `timing_onset_slow` + gating; standalone
  selftest 13/13. Applies identically to already-run and future runs (no
  reruns, no invalidation).
- **Option B (documented fallback if Option A fails to deliver):** if, after
  P1/P2 lock and a first look at E, the onset (or full) contrast still looks
  too thin or insufficiently separated for the thesis, switch to a
  **multi-block demand profile** (several ≥300 s high-rate blocks separated
  by short dips) so the onset transient repeats inside each run and the
  contrast dominates the pooled read. This CHANGES `phases.json` for all
  future runs, invalidates the single-block P1/P2 evidence, and requires a
  per-block-window analyzer rework + a fresh preflight — it is a deliberate
  second act, not a mid-preflight tweak.
- 2026-09-08 (contract v2 none-cell amendment, user-approved) — the
  none-cell health floor slow is judged on the **plateau tail** (relief
  completion), not the full plateau. Rationale: even a no-fault run carries
  the universal demand-onset transient (no dynamic backend is ready for the
  first ~40–60 s), so a full-plateau ≤2 pp slow ceiling is structurally
  unreachable at rate S; P2 seed 5302 flagged `stop_null` on a none-cell
  full-plateau slow of 2.34 % (tail 1.26 %). bad stays ≤1 % on the full
  plateau. Aligns P2 and H-T3 with the loss_all-control tail standard.
- 2026-09-08 (lock, user-approved) — **rate 2.0 locked** on the 3-of-4
  reproducible majority (seeds 5301/5302/5304): full Δ median 9.08 pp
  (9.08/9.61/7.59), onset Δ median 31.33 pp (41.71/30.9/31.33); seed 5303
  recorded as a genuine stochastic outlier (weak event_only draw 8.77 % and
  one reconcile late-tail transient — diagnosed, onset Δ 24.2 pp still
  passed). `rq3tim_preflight_lock.json` written. Lock interpretation amended:
  ≥3-of-≥4 independent seeds ≥5 pp (full AND onset) with medians ≥7 pp.
