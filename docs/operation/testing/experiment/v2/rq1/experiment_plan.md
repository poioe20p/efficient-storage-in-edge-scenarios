# Experiment Plan — RQ1 Telemetry Delivery Semantics

**Date**: 2026-07-31 · **Status**: 📋 Planned
**Parent (implementation plan)**: [`docs/research_questions/v2/rq1/rq1_prepation.md`](../../../../research_questions/v2/rq1/rq1_prepation.md) (Design B, **IMPLEMENTED** 2026-07-31)
**Thesis RQ1**: [`tese/Notes/thesis_overview.md`](../../../../../../tese/Notes/thesis_overview.md) §6 RQ1

> **RQ1 v2 (final evidence):** the 9-run v1 campaign below becomes the
> **v1 / supporting record** once the v2 campaign completes. v2 adds a fourth
> arm (D, sampled-push — the missing fresh+lossy cell), runs n=5 per arm under
> the open-loop driver (`TRAFFIC_DRIVER_MODE=open_loop`, `CURL_MAX_TIME=300`,
> `INFLIGHT_WINDOW=1024`, `DRAIN_S=30`), and pre-registers the statistics.
> Authoritative spec: [`rq1_v2_rework_plan.md`](rq1_v2_rework_plan.md); v2
> matrix in `run_matrix.md` §9; measurement contract in `analysis_focus.md` §0.

This is the **experiment plan** for the RQ1 delivery-semantics extension — the
"separate step" flagged in `rq1_prepation.md` §8. It turns the implemented
three-arm delivery machinery into a runnable, analyst-checkable campaign.

Split files in this folder:

| File | Purpose |
|---|---|
| `experiment_plan.md` | Intent, hypothesis, variable, success criteria, links (this file) |
| [`run_matrix.md`](run_matrix.md) | Detailed per-run configuration (labels, env, commands, cleanup) |
| [`analysis_focus.md`](analysis_focus.md) | Measurement contract, graph inventory, tooling contract |
| (control group) `phases_stress_plateau.json` | Workload phase file (1200 s control-group plateau — no per-RQ1 phase file) |

---

## 1. Objective

Answer the thesis RQ1: **How do verified event-preserving, delayed
event-preserving, and latest-state telemetry delivery semantics affect overload
observability, scaling response, and transient service quality in a stateful
edge service?**

The single question the campaign isolates: **is the controller harmed mainly by
delivery delay, by loss of intermediate demand evidence, or by both?** Three
delivery arms run an identical workload under a fixed policy; only the delivery
semantics vary.

## 2. Motivation & Hypothesis

**Change under test.** The RQ1 delivery-semantics extension is implemented
(`rq1_prepation.md` §3–§4): a durable sequence-numbered window log on the
aggregator (`aggregator.py`, always-publish, `window_seq`/`window_id`/`overload`
labels), three delivery sources (`event_preserving_source.py`,
`delayed_source.py`, `polling_source.py`), a shared delivery log + ack client
(`delivery_log.py`), a decision log, and the Design-B housekeeping split
(`main_n1.py`/`main_n2.py`, `node_registry.py`). This experiment evaluates that
machinery end-to-end.

**Hypothesis.** The three arms differ along two orthogonal axes — **completeness**
(how much of the window stream reaches the controller) and **info age** (how old
the evidence is when acted on):

- **H1 (delay penalty):** Arm B delivers the same complete stream as Arm A, but
  every decision lags ≈ `DELAY_S` → overload detection and scale-up reaction
  latency are ~`DELAY_S` higher, while overload observability (delivered windows)
  is preserved.
- **H2 (loss penalty):** Arm C has lower info age than B but drops intermediate
  windows → per-window overload observability and decision opportunities fall
  (missed overload windows), even though what it does see is fresher.
- **H3 (reference):** Arm A is the control — ≈100% delivery, sub-second delay.
  Both B (delay only) and C (loss only) are measured **relative to A**. If A shows
  meaningful missed windows, the run is a harness defect, not an arm effect.

**Independent variable:** telemetry delivery semantics — 3 levels,
`TELEMETRY_SOURCE ∈ {event_preserving, delayed_event_preserving, poll}`.

**Held constant (per thesis §2):** `WINDOW_S=10`, `CONTROL_TICK_S=10`,
scaling policy (**rebased from the control group, 2026-08-01**: caps 3/3,
compute scale-down 180 s/9, storage scale-down 30 s + 3/5 — set in the per-arm
env, identical across arms), routing policy, workload
(`phases_stress_plateau.json` — the control group's validated plateau),
topology, resource limits (`STORAGE_CPUS=0.08 EDGE_CPUS=0.15 WAN_RTT_MS=185`),
clients/devices/nodes, `OVERLOAD_*` thresholds, and Tier 1 / persistent
reserves / cross-region storage **disabled** (thesis §2 — a deviation from the
control's scalable arm, which runs SS/reserve on; verified at pre-flight G1).

## 3. Run Matrix

Full detail in [`run_matrix.md`](run_matrix.md). Structure:

| Stage | Runs | Arms |
|---|---|---|
| Pre-flight (tooling + calibration gate) | 3 | one per arm |
| Main campaign | 9 (3 per arm) | A `event_preserving`, B `delayed_event_preserving`, C `poll` |

Env override files (one per named regime, in the `env/` subfolder of this
experiment folder): `env/rq1_event_preserving.env`, `env/rq1_delayed.env`,
`env/rq1_latest_state.env`. **Workload:** the control group's
`phases_stress_plateau.json` (no per-RQ1 phase file). The env files are
**rebased from `current_state_integrated.env`** (control-group retune
2026-08-01) plus the thesis-§2 disable flags and delivery vars; they
**supersede** `rq1_delivery_semantics.env`. The env files are deliberately
placed under this v2/rq1 folder (not
`source/scripts/testing/controller_env_overrides/`); the harness resolves them
via `OSKEN_ENV_OVERRIDE_FILE` with a relative path (see §4).

The per-arm files share an identical platform block (capacity, scale-down,
disable flags, `CONTROL_TICK_S`, log paths) — copied from
`current_state_integrated.env` (2026-08-01 retune) so each arm file is
self-contained and reproduces the control's effective thresholds.
`current_state_integrated.env` itself stays the RQ2/RQ3 baseline and is not
edited. Per-run provenance is still captured by `controller_env_snapshot.env`
and `aggregator_env_snapshot.env`.

## 4. Run Configuration

Canonical per-run launch (all runs in the cloud VM at
`~/efficient-storage-in-edge-scenarios`; full per-arm table in `run_matrix.md`):

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup bash source/scripts/testing/rq1_launch_run.sh \
    <ENV_FILE> <LABEL> <SEED> [POLL_INTERVAL_S=30 for Arm C] \
    > /tmp/<LABEL>.log 2>&1 &"
```

- The launcher `source/scripts/testing/rq1_launch_run.sh` encodes the canonical
  make chain: open-loop driver (`TRAFFIC_DRIVER_MODE=open_loop`,
  `CURL_MAX_TIME=300`, `INFLIGHT_WINDOW=1024`, `DRAIN_S=30`),
  `PHASES_CONFIG=testing/phases_override/phases_rq1_stress_plateau.json`
  (rate 3.0), and the Mongo data-path block
  (`EDGE_MONGO_READ_PREFERENCE=secondaryPreferred`, `EDGE_MONGO_MAX_POOL_SIZE=12`,
  `VIP_DATA_PER_CONNECTION_FLOWS=1`). All knobs are make command-line variables
  so they survive sudo `env_reset`. Arm C additionally passes `POLL_INTERVAL_S=30`
  as the optional extra-args slot.
- **Arm C poll interval (critical):** `build_network_setup.sh` passes
  `-e POLL_INTERVAL_S="${POLL_INTERVAL_S:-10}"` and Docker `-e` overrides the
  env file — so the `POLL_INTERVAL_S=30` in `rq1_latest_state.env` alone is
  **not enough**. Arm C runs must also set `POLL_INTERVAL_S=30` on the shell in
  the launch prefix (see `run_matrix.md` §4). Recommended hardening (follow-up):
  give `POLL_INTERVAL_S` the same pass-through treatment `TELEMETRY_SOURCE` got.
- Images: `local_state_server` was already rebuilt on the VM (2026-07-31) with
  the RQ1 aggregator; the `osken-controller` image needs **no** rebuild
  (controller code is volume-mounted). No further image work required.
- Between runs: cleanup recreates the aggregator and controller containers →
  fresh `window_log.jsonl`/delivery/decision logs per run (checkpoint C1).

## 5. Measurements & Success Criteria

Primary evidence (per run, per LAN) — collected by `run_experiment.sh`
`collect_rq1_artifacts()` into the run folder:

- `window_log_lan{1,2}.jsonl` — **universe** (every published window, `overload` label)
- `telemetry_delivery_log_lan{1,2}.csv` — **delivered** (+ `gap_recovery`/`processing_error` rows)
- `decision_log_lan{1,2}.csv` — **controller actions** (join to windows via `window_id`)
- `ack_log_lan{1,2}.jsonl` — producer-side acks (audit/cross-check)
- existing: `client_requests.csv`, `resource_stats.csv`, `controller_stats.csv`,
  `container_events.csv`, `controller_lan{1,2}.log`, `phases_snapshot.json`,
  `controller_env_snapshot.env`, `aggregator_env_snapshot.env`

Derived-metric definitions and the thesis-RQ1 mapping are in
[`analysis_focus.md`](analysis_focus.md) §2–§3.

Numbered success criteria (each objectively checkable by the analyst; per LAN):

1. **Artifact completeness:** `window_log`, `telemetry_delivery_log` and
   `decision_log` are present and non-empty in every run folder, for both LANs.
   `ack_log` is required for arms A and B and **absent by design** for arm C (the
   polling source does not ack) — its absence for C is not a defect.
2. **Arm A is a clean reference:** delivered fraction ≥ 0.98 of universe windows,
   **zero** `gap_recovery` and `processing_error` rows (else harness defect).
3. **Arm B completeness + delay:** delivered fraction **excluding
   `in-delay-at-run-end`** ≥ 0.98. The final ≈ `DELAY_S/WINDOW_S`+1 windows are
   always in the hold queue at artifact-copy time (expected residue ≈ 3–4 windows
   per LAN — not a defect). p50 `delay_s` of surge-phase windows ∈
   [`DELAY_S`, `DELAY_S`+`WINDOW_S`] (i.e. 30–40 s; the upper bound allows the
   documented un-masked backlog excess; if a mid-run stall pushed p50 above 40,
   report and inspect rather than auto-fail); `in-delay-at-run-end` reported
   separately.
4. **Arm C loss is measurable:** delivered fraction < 0.70 (intermediate windows
   actually dropped) **and** p50 info-age-at-decision ≥ 10 s lower than Arm B's
   (the delay-vs-loss contrast is real, not degenerate).
5. **Overload is exercised:** during `compute_plateau`, ≥ 30% of plateau
   windows are labeled `overload` in the universe in **all** arms (else the
   plateau did not trip `OVERLOAD_*` → calibration failure, see pre-flight gate
   G2). Plateau rate 5.0 stays **locked** (control-group decision); G2 adjusts
   `OVERLOAD_*`/`CLIENTS`, not the rate.
6. **Scale-up response:** ≥ 1 scale-up decision per LAN in every arm during
   `compute_plateau`, and usable capacity reached (`container_events.csv` spawn
   ready) — required so "demand shift → decision → capacity" is measurable.
7. **Scale-down response:** ≥ 1 scale-down decision per LAN **after
   `compute_plateau`** in **every arm**. A/B's first removal is expected in
   `recovery_gap` (premised on the rebased `SCALEDOWN_COMPUTE_COOLDOWN_S=180`
   from the last scale-up); C's lands later (in `recovery_gap`/`demand_drop`),
   driven by its sparser delivery. **RQ1 scale-down calibration (2026-08-02):**
   compute `SCALE_DOWN_COMPUTE_WINDOW_SIZE=6`, `SCALE_DOWN_COMPUTE_REQUIRED=3`
   (3-of-6 = 50%), with the below-criterion relaxed to `TAU_CPU_DOWN=25` /
   `TAU_PROC_DOWN_MS=40` — identical in all three arm env files. Pre-flight
   showed the fixed 9-of-12 threshold made even a complete lossy arm unable to
   accumulate below windows: the drop's residual CPU (~17–24%) exceeds
   `TAU_CPU_DOWN=15`, so almost no delivered window was `below` — the criterion,
   not the count/window, was the blocker. Storage scale-down is **not**
   calibrated: it arms for C (3/3) and is instead capped by the reserve-floor
   guard at ≤2 dynamic nodes (reserves disabled) — a platform floor affecting
   all arms equally, documented as a non-delivery constraint. The analyst
   reports each arm's delivered below-threshold window count in
   `recovery_gap`+`demand_drop` alongside the outcome; an arm that does not fire
   while its delivered count ≥ the required count is flagged for inspection
   (not auto-passed, not auto-failed).
8. **Transient service quality:** per-phase failure rate ≤ 2% in **all
   non-surge phases** (baseline, `recovery_gap`, `demand_drop`);
   plateau-phase degradation is expected — the comparison is **relative across
   arms** (see C9), not absolute. Per-phase request counts are reported alongside
   the rate (only `recovery_gap` is a low-volume f0.05 phase; `baseline` and
   `demand_drop` are f0.1 — `demand_drop` is high-volume at 420 s — so no
   blanket "≤1 failure" claim applies).

   **v2 re-framing (pre-registered, 2026-08-04):** under the open-loop driver
   the arms finally face equal offered load, so C8 is **re-cast as a cross-arm
   comparison** on non-surge `timeout_rate` + `failure_rate` (per generator
   `phase` label, `canceled` rows excluded from the denominator) rather than an
   absolute ≤ 2% bound. The pre-registered expectation is that any
   arm-discriminative non-surge degradation is a **delay penalty** (Arm B); a
   null result is an acceptable, reported outcome. The absolute ≤ 2% bound
   from v1 is dropped for v2 (v1 showed it was spike-driven and
   non-discriminative).

   **C8 decision rule (implemented in `rq1v2_p3_01_stats.py`):** the non-surge
   comparison is one of three outcomes from Cliff's delta on non-surge
   `timeout_rate`/`failure_rate` across the factorial edges — **DELAY PENALTY**
   (delay edges A→B, D→C degrade while loss edges are ≈ 0; pass),
   **NULL** (all |delta| ≤ 0.2; reported as a null), or **UNANTICIPATED** (any
   loss edge clearly degrades, or any edge shows a **direction reversal** —
   |delta| > 0.2 with the wrong sign; triggers re-inspection).
9. **Delay-vs-loss ordering:** mean reaction latency (plateau start → first
   scale-up decision) and info-age-at-decision order as B ≥ C > A, while
   delivered fraction orders as A ≈ B > C. If this ordering is violated, the
   run/arm is flagged for re-inspection before conclusions.

   **v2 re-framing (2026-08-04):** the v1 first-decision ordering formulation is
   superseded for v2 — first-decision latency is descriptive-only (delivery
   timing confounds it in every arm), and the v2 ordering claim is the
   pre-registered **factorial-edge comparison** (delay edges A−B, D−C; loss
   edges A−D, B−C) on usable-capacity latency, `timeout_rate`, `failure_rate`,
   time-to-recover, and info-age at decision (`analysis_focus.md` §0.4;
   implemented in `rq1v2_p3_01_stats.py`).

## 6. Analysis Approach

Full detail in [`analysis_focus.md`](analysis_focus.md) §4–§6. Summary:

- **Contrast structure:** A is the control. **A vs B** isolates the delay penalty;
  **A vs C** isolates the loss-of-intermediate-evidence penalty. The headline is a
  **completeness-vs-info-age tradeoff** (delivered fraction vs info age at
  decision) per arm.
- **Per-run analysis** (`analysis/rq1_delivery_per_run.py`, **implemented**):
  run folder → per-run metrics CSVs (`delivery_integrity.csv`,
  `delivery_delay.csv`, `info_age.csv`, `overload_observability.csv`,
  `overload_episodes.csv`, `reaction_timeline.csv`,
  `phase_service_quality.csv`, `overhead.csv`, `run_meta.csv`).
- **Cross-mode graphs** (`analysis/rq1_delivery_comparison.py`, **implemented**):
  group runs by arm → graph suite (delivery completeness, delivery-delay and
  info-age boxes, missed overload, overload detection delay, scale reaction,
  scale-down, per-phase latency, overhead, completeness-vs-info-age) with
  per-replicate variance, archived to `<experiment>/graphs/comparison/`.
- **Overload semantics:** missed overload windows computed by the analyzer only
  (universe ∩ overload − delivered, excluding `in-delay-at-run-end`); report
  per-window **and** per-episode visibility for Arm C (an episode may still be
  seen via a later delivered overload window even if intermediate windows are
  dropped).

## Appendix

### A. Prerequisites (before any run)

- [x] Implementation deployed + validated (`rq1_prepation.md` §9)
- [x] `local_state_server` image rebuilt on VM (2026-07-31)
- [x] RQ1 env override files created (`env/rq1_event_preserving.env`, `env/rq1_delayed.env`, `env/rq1_latest_state.env`)
- [x] Workload = control group's `phases_stress_plateau.json` (no per-RQ1 phase
      file)
- [x] Launch-path prerequisites understood: Arm C sets `POLL_INTERVAL_S=30` on the
      shell (`build_network_setup.sh` `-e` default is 10); `OVERLOAD_*` thresholds
      are set on the shell for `build_network_1/2.sh`, not in the controller env
      file
- [x] **Analysis tooling implemented** — `analysis/rq1_delivery_per_run.py` +
      `analysis/rq1_delivery_comparison.py` (see [`analysis_focus.md`](analysis_focus.md) §6),
      smoke-tested on synthetic runs.
- [ ] Files synced to cloud VM (`ssh cloud-vm`, repo at `~/efficient-storage-in-edge-scenarios`)

  > **Placement (rebase 2026-08-01):** the workload is the control group's
  > `source/scripts/testing/phases_override/phases_stress_plateau.json` (the
  > canonical control-group regime), so the old placement deviation for a
  > per-RQ1 phase file is **resolved** (no per-RQ1 phase file). The per-arm env
  > files stay under this v2/rq1 folder (`env/`); the harness consumes them via
  > `OSKEN_ENV_OVERRIDE_FILE` with a relative path, and each run still records the
  > merged result in `controller_env_snapshot.env`.

### B. Checkpoints

- **C1 (per run):** fresh aggregator/controller state — `window_log` `window_seq`
  starts near 1, delivery/decision logs contain only the current run's header/rows.
- **C2 (per run):** no controller restart mid-run (restart invalidates the run).
  Verification: `container_events.csv` shows the `osken`/`osken_2` container
  start time before the run start, and each controller log carries exactly one
  startup banner.
- **C3 (per run):** all four RQ1 artifacts copied before external cleanup
  (`collect_rq1_artifacts` ordering).
- **C4 (campaign):** run folders follow `<timestamp>_rq1_delivery_<arm>_<suffix>`
  (arm ∈ `ep` | `delayed` | `ls` | `sp` — the `sp` suffix was added for v2).
  Replicate aggregation includes **only numeric suffixes** (`_1`..`_5` for v2,
  `_1`..`_3` for v1); pre-flight (`_preflight`) runs are excluded from the
  replicate scatter.
- **C5 (environment):** the VM shell must not have `TELEMETRY_SOURCE` exported —
  `build_network_setup.sh` passes it through only when set, and the per-arm env
  file is authoritative for it. (Arm C deliberately sets `POLL_INTERVAL_S` on the
  shell; `TELEMETRY_SOURCE` must not be set on the shell.)

### C. Validity threats

- **Controller restart mid-run** re-pulls the window log and re-delivers →
  duplicate decisions; run invalid (thesis §8). Checked by C2.
- **In-delay-at-run-end:** Arm B windows still in the hold queue at run end are
  not "missed" — the trailing `recovery_gap`/`demand_drop` phases (≥
  `DELAY_S + WINDOW_S` = 540 s) are sized to drain them; the analyzer still
  reports the residual separately.
- **Wall-clock assumption:** delivery delay / info age rely on same-host clocks
  (true in this deployment); a clock skew would corrupt `delay_s`.
- **Overload-label proxies:** `OVERLOAD_*` are pre-registered proxies, not the
  internal `degradation_score`; the plan treats them as the observability signal
  by definition (D3), identical across arms.
- **Arm C episode visibility:** per-window loss may coexist with per-episode
  visibility; both are reported (C9 handles the ordering, not a bare count).

### D. References

- Implementation plan: `docs/research_questions/v2/rq1/rq1_prepation.md`
- Thesis RQ1: `tese/Notes/thesis_overview.md` §6
- Code: `source/sdn_controller/telemetry/{models,delivery_log,event_preserving_source,delayed_source,polling_source}.py`,
  `source/sdn_controller/{main_n1,main_n2,node_registry,scaling_config}.py`,
  `source/docker/local_state_server/aggregator.py`
- Harness: `source/scripts/testing/run_experiment.sh` (`collect_rq1_artifacts`),
  this folder's `env/rq1_{event_preserving,delayed,latest_state}.env`,
  control group's `source/scripts/testing/phases_override/phases_stress_plateau.json`,
  this folder's `analysis/rq1_delivery_{per_run,comparison}.py`

## F. RQ1 v2 — final evidence

Authoritative spec: [`rq1_v2_rework_plan.md`](rq1_v2_rework_plan.md); matrix
`run_matrix.md` §9; measurement contract `analysis_focus.md` §0.

- **Design:** 4-arm full 2×2 factorial — adds Arm D `sampled_push`
  (fresh+lossy, `SAMPLE_EVERY=3`, sub-second delivery, ~1/3 delivered). n=5 per
  arm, 20 runs, 5 counterbalanced blocks (seeds 2001–2005).
- **Hypothesis additions:** the delay-vs-loss attribution is clean only with
  the missing cell — **delay** = A−B and D−C edges (fresh- and lossy-level);
  **loss** = A−D and B−C edges (complete- and stale-level); diagonals B−D /
  A−C are the headline tradeoff (descriptive + Cliff's delta only).
- **Driver:** `TRAFFIC_DRIVER_MODE=open_loop`, `CURL_MAX_TIME=300`,
  `INFLIGHT_WINDOW=1024`, `DRAIN_S=30`; offered/completed separated; `timeout`
  a distinct outcome class; `dropped` possible by design (counted in offered,
  excluded from latency/failure, reported separately).
- **Metrics:** pre-registered primary = **usable-capacity latency**;
  first-decision latency is descriptive-only for ALL arms (delivery-timing
  confounded). Stats: MWU (exact/normal) + Cliff's delta on the factorial
  edges; ≥ 3 defined runs/cell; no censored value enters MWU; latency
  percentiles descriptive-only with a censoring flag. Implemented in
  `docs/research_questions/v2/rq1/rq1v2_p3_01_stats.py`.
- **Gates:** driver/analyzer/sampled-push selftests, concurrency stress, G2
  calibration under open-loop, per-arm scale-down arming (esp. Arm D), Arm D
  dry-run, lan2 asymmetry diagnostic, sync-mode regression.
- **v1 status:** the v1 9-run campaign above is the **supporting record** once
  the v2 campaign completes.

## E. Changelog

| Date | Change | Rationale |
|---|---|---|
| 2026-07-31 | Created plan (480 s surge profile, EDGE_CPUS=0.25, caps 8/12, compute cooldown 60 s) | Turn the implemented three-arm delivery machinery into a runnable campaign |
| 2026-08-01 | **Rebased onto the validated control group** (`v2/control_group.md`): workload = `phases_stress_plateau.json`, `EDGE_CPUS=0.15`, caps 3/3, storage scale-down 30 s+3/5, compute scale-down 180 s/9; phase names `overload_surge`/`drain_1`/`tail` → `compute_plateau`/`recovery_gap`/`demand_drop`; scale-down anchored to the post-plateau region; criterion 8 per-phase counts; G1 verifies scale-up SS-off | Reuse the validated control calibration so RQ1 reports deltas relative to the control; the SS-off/reserve-off config (thesis §2) is not control-validated and is verified at pre-flight, not assumed |
| 2026-08-01 | **RQ1 scale-down calibration:** `SCALE_DOWN_COMPUTE_REQUIRED=9 → 6` in the 3 arm env files (control stays 9); criterion 7 updated | Pre-flight P3 showed a lossy latest-state arm cannot reach 9-of-12 compute scale-down (drop yields ~55% below vs 75% required); 6-of-12 lets C fire while staying identical across arms (RQ1 isolation) |
| 2026-08-02 | **Scale-down calibration v2:** compute → 3-of-6 (`SCALE_DOWN_COMPUTE_WINDOW_SIZE=6`, `SCALE_DOWN_COMPUTE_REQUIRED=3`) + relaxed below-criterion (`TAU_CPU_DOWN=25`, `TAU_PROC_DOWN_MS=40`) in the 3 arm env files | P3 re-run at 6/12 still did not arm C: the drop's residual CPU (~17–24%) exceeds `TAU_CPU_DOWN=15`, so almost no delivered window is `below` — the criterion, not the count/window, was the blocker |
| 2026-08-02 | **Main campaign (9 runs) executed + analyzed** — `ep_1..3`, `delayed_1..3`, `ls_1..3` on the calib-v2 env (Arm C with `POLL_INTERVAL_S=30` on the shell); results in `results.md` §Main Campaign | n=3 closes RQ1: C1–C6 ✅; C7 ✅ (≥1 decision/LAN — `ls_3` lan1 decision-log gap flagged for inspection); C8 ❌ (A and B, corrected on raw phase labels); C9 ✅ (capacity-anchored reaction; C > B capacity ordering is a finding refining H1/H2); C lan2 plateau asymmetry |
| 2026-08-02 | **Deep-verification correction:** per-phase C8 recomputed on generator `phase` labels — the analyzer's anchored bucketing was misaligned (plateau overrun ~52–57 s), making the earlier "B-only" C8 reading an artifact. C8 is assessed **⚠️ borderline** (non-surge rates uniformly low 2–4% across arms); the delayed_3 recovery_gap 10.96% spike was an artifact (raw 1.85%); C7 adds a container_events churn caveat for `ls_3` lan1 | Independently re-derived every claim from raw VM artifacts; all C1–C6, reaction, capacity-ordering, and delivery claims verified exact |
| 2026-08-04 | **G2 calib6 negative → workload re-anchor.** Pool 12 did not fix the collapse; real root cause = churn-driven (absent-cleanup/scale-down removing live nodes during overload → RS reconfig → DB stalls, self-amplifying). Control/RQ2 “proven-stable” rates were sync-driver (closed-loop); open-loop was never rate-calibrated. Added `_HOUSEKEEPING_OVERLOAD_GATE` (default ON, all RQs): suppress absent-cleanup + scale-down while overloaded. Planned open-loop rate sweep 2.0/2.5/3.0 (Arm A, seed 2001, pool 12) to re-anchor the plateau | Re-anchor RQ1 so delivery arms differentiate on decision quality under bounded overload instead of a self-inflicted data-plane collapse |
