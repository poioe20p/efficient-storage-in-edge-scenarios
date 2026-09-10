# RQ3 Readiness-Admission Robustness Campaign — Plan (approved draft)

> **Status cross-reference (2026-09-07):** this family launched on `cloud-vm-rq3`
> and was **STOPPED by user decision after 19 valid runs** (block 1 9/9, block 2
> 9/9, block 3 run 1). Rationale recorded in [`preflight_log.md`](preflight_log.md)
> (checkpoint 3.x): the frozen 0.15-quota regime lands in the 0.28–0.69%
> failure envelope, so n=6 cannot produce visible QoE degradation. The QoE
> consequence is now a separate Family-3 campaign (uniform-quota ladder, lock
> at the first rung with visible degradation): see
> [`../rq3_qoe/experiment_plan.md`](../rq3_qoe/experiment_plan.md). The 19 valid
> runs are retained as 0.15-family evidence.

**Family:** reframed RQ3, Family 2 (robustness). Family 1 (low-headroom
consequence) stays as implemented. Textual reframing is out of scope here.

## 1. Objective and treatments

Headline outcome: **admission preservation under fault** — what fraction of
ready compute backends still become usable capacity when readiness evidence
delivery fails, and how long ready capacity stays dark.

Arms (one per run, new tag):

| Arm | Configuration | Behavior |
| --- | --- | --- |
| `event_only` | direct propagation + `READINESS_EVENT_FALLBACK_S=130` (> probe max 120) | admit only on app_ready event; the abandon branch at probe_max=120 fires before the 130 s fallback can probe, so a lost event always yields `abandoned` (fallback provably inert — verified in Stage 0) |
| `hybrid` | existing `rq3sat_direct.env` (fallback 20 s) | event admit; fallback probe after 20 s |
| `reconcile` | existing `rq3sat_discovery.env` (10 s poll) | periodic discovery only |

Fault cells (one condition per run):

| Cell | Injection | Pre-registered contrast |
| --- | --- | --- |
| `none` | no fault | compatibility baseline; archived P4 numbers must reproduce |
| `loss_all` | every app_ready event dropped at the controller | event_only abandons all; hybrid recovers ~20 s; reconcile unaffected |
| `loss_alt` | every 2nd app_ready event per LAN dropped (controller arrival order, deterministic drop counter) | event_only loses ~half of backends (aggregate claim only); hybrid recovers; reconcile unaffected |
| `restart` | `docker restart osken` at locked phase offset | post-restart behavior of pending backends, per arm |

## 2. Stage 0 — preflight and characterization (no evidence claims)

New tag `rq3rob-preflight-<date>` created from `rq3-sat-preflight-20260808`
plus only: env-gated loss knob, fault-injector restart action, new arm/fault
env deltas, launcher/manifest/analyzer. Default-off knob keeps all other runs
byte-identical.

Runs (n=1 each, seed 4001-4009):

1. baseline none cell, all 3 arms -> hybrid and reconcile must reproduce archived
   P4 readiness/timing/CPU envelope. event_only has no archived baseline; its
   compatibility derivation is pre-registered as: identical no-fault behavior
   to hybrid (same gate code path until an event is lost), so it must reproduce
   hybrid's no-fault timing, event fraction 1.0, and CPU envelope.
2. `hybrid` + `loss_all`: all admissions `probe_fallback`; median
   admitted-spawn (spawn->admit) within [20, 26] s (fallback + probe retry
   + timeout cadence); true-ready->admit reported descriptively (~14.5 s,
   fallback anchored at pending registration); 0 abandoned.
3. `event_only` + `loss_all`: every backend abandoned at ~probe max; 0 admitted;
   outcome rows are `abandoned` with ZERO `probe_fallback` rows — this proves the
   130 s fallback never fires (abandon precedes fallback) and is what makes H1's
   0.0 preservation valid.
4. `event_only` + `loss_alt`: aggregate preservation fraction in [0.3, 0.7]
   (arrival-order drop makes per-backend claims non-reproducible; only the
   aggregate is pre-registered).
5. restart observation x3 (one per arm): restart at plateau+45 s; record actual
   outcomes of backends pending at restart.

Stage 0 deliverables:

- verify `docker logs -f` capture survives `docker restart osken`; else runner
  restarts capture or performs a post-run `docker logs` dump; record method.
- verify `ADMISSION_LOG_PATH=/tmp/admission_log.csv` survives `docker restart`
  (writable layer persists); if it does not, the campaign launcher must set
  `ADMISSION_LOG_PATH` to a host-persisted path. This artifact is the restart
  cell's core evidence.
- classify post-restart outcomes from artifacts: `recovered_admitted`,
  `orphaned_dark`, `removed_absent`, `still_pending`. Pre-register the NULL:
  because the gate registry, elasticity state, and late-event buffer are
  in-memory and the edge emits `app_ready` exactly once, NO arm is expected to
  re-admit a backend pending at restart; the restart cell's default finding is
  arm-independent orphaning, and an observed arm difference is the surprising
  result that would trigger Stage 2.
- lock restart offset: first candidate in {30,45,60} s after plateau start
  where >=1 backend is spawned-but-unadmitted at restart in 2 consecutive runs;
  document. Only after this observation are restart-cell expectations in the
  run matrix. No Stage 0 run is evidence.

## 3. Stage 1 — loss campaign (headline evidence)

Cells: `none`, `loss_all`, `loss_alt`; arms: 3; blocks: 6; runs: 54.
Block seeds 4101-4106. Arm order per block follows a 6-replicate rotation of
the 3-arm order (replicate r = rotation r), counterbalancing within-cell drift.
Workload: P4 phases (canonical phases in the frozen worktree), 24 clients/LAN,
rate 1.5, EDGE_CPUS 0.15.

Metrics per backend: outcome class (event / probe_fallback / probe /
abandoned / orphaned_dark / removed_without_admission); true-ready->admit;
spawn->first-success. Preservation denominator is the PRE-CHURN cohort:
only backends spawned before the first abandonment in the run, so loss-induced
respawn churn cannot dilute the ratio; churn count is reported separately.
Per run/LAN: preservation rate = admitted / pre-churn spawned; dark duration
medians. Cell contrasts: H1/H2 as scoped below; dark duration via exact MWU +
Cliff's delta, paired by block seed.

Pre-registered Stage 1 hypotheses (statistical scope explicit per metric):

- H1 loss_all preservation (ABSOLUTE expectations, no significance test —
  deterministic): hybrid = 1.0, reconcile = 1.0, event_only = 0.0 (all
  abandoned).
- H2 loss_alt preservation (per block x LAN units, n=12): hybrid and reconcile
  = 1.0 per unit (absolute); event_only per-run aggregate in [0.3, 0.7].
- H3 dark penalty (continuous, inferential: exact MWU + Cliff's delta on
  per-run median spawn->admit, hybrid loss_all vs hybrid none, n=6/arm):
  hybrid loss_all median within
  [20, 26] s (fallback + probe retry + timeout cadence, not discovery poll)
  and greater than hybrid none-cell (~0 s). True-ready->admit dark is
  reported descriptively (Stage 0 anatomy: ~14.5 s, fallback anchored at
  pending registration).
- H4 QoE secondary (hybrid and reconcile loss cells ONLY): fixed-window
  timeout/failure <= 1% (no collapse). For event_only loss cells, QoE collapse
  is a measured consequence of H1, reported descriptively, never a gate and
  never a rescue of the primary.

Gates per run: D1/D2/D3, M1/M2, V1, I1/I2, driver clean, flow A/B/D hard and
C>=0.85 (restart cells: A/B/D only), no NotPrimary, drop-log rows match
requested mode, fault marker CSV present, quota_snapshot matches, no plateau
scale-down (restart cells: scale-down before restart_ts only). Void rule: <=1
replacement per arm after diagnosed cause, same seat/seed.

## 4. Stage 2 — restart campaign (conditional escalation)

Stage 2 runs only if Stage 0 observations show a reproducible ARM DIFFERENCE
in pending-backend outcomes (the null is arm-independent orphaning). Then
3 arms x 6 blocks (18 runs, seeds 4201-4206), restart at the locked offset,
expectations pre-registered from Stage 0 observations. Otherwise publish Stage 0
observations as characterized behavior with no inferential claim. Never
retrofit expectations from campaign data.

Restart cell gates: pre-register that scaling cooldowns, decision counters, and
telemetry cadence re-anchor at restart (part of the treatment), so all post-
restart metrics are windowed relative to restart_ts, never to plateau start.
Flow-validation Check C may degrade after restart (flows re-install); A/B/D
remain hard. The restart marker CSV (fault injector) is a D3-level artifact.
The exactly-once edge event emission is the SUBJECT of the robustness question,
not a confound; claims are phrased accordingly (recovery capacity of each
coordination design, not a re-emission assumption).

## 5. Implementation surface (new tag only)

1. `source/sdn_controller/control_events.py`: env `READINESS_EVENT_DROP_MODE`
   (off | all | alternate), default off; drop happens before `admit_on_event`;
   log every dropped event with MAC/mode. No effect on discovery arm.
2. `source/scripts/testing/fault_injector.py`: new action type
   `docker_restart` (container name `osken`), phase/after_s trigger, writes
   `experiment_fault_events.csv` restart rows with epoch timestamp.
3. New env deltas under `controller_env_overrides/`:
   `rq3rob_event_only.env` (direct bundle + FALLBACK_S=130),
   `rq3rob_loss_all.env`, `rq3rob_loss_alt.env` (drop-mode only).
4. `source/scripts/testing/analysis/rq3/readiness_robustness.py`: outcome
   classification, preservation, dark duration, restart-window detection,
   cell statistics; reuses the rq3lh request/QoE helpers where applicable.
5. `rq3rob_p0_01_prepare_tag.py` (manifest), `rq3rob_p0_02_analyzer_selftest.py`,
   `rq3rob_p0_03_preflight.sh`, `rq3rob_p1_01_launch_run.sh`
   (arm env + fault env + label + seed + optional restart offset).
6. Docs: `docs/operation/testing/experiment/v3/rq3_robustness/`
   {experiment_plan.md, run_matrix.md, preflight_campaign.md, preflight_log.md};
   update `testing_overview.md`, `v3/README.md`.

Non-goals: no change to readiness_gate semantics; no selective edge-side loss;
no controller-state persistence changes; thesis text unchanged until evidence.

## 6. Budget and stop rules

Stage 0 ~9 runs; Stage 1 54 runs (~40 min/run + reset, ~36+ h wall).
Stage 2 18 runs only on GO. Between-block direction checks (2-of-3 by block 3,
3-of-5 by block 5) with diagnosed-cause rule; a failed pre-registered direction
is reported, not chased. Campaign runs after the low-headroom campaign finishes
on cloud-vm-rq3; no overlap.

## 7. Validation before VM

py_compile + analyzer selftest (synthetic fixtures for drop modes and restart
classification); bash -n/shellcheck; env-merge proof (event_only=direct+130,
loss deltas single-key); manifest/tag identity; launcher negative tests; dry
run of make vars. No experiment executes during implementation.
