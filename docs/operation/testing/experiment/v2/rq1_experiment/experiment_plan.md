# Experiment Plan — RQ1 Telemetry Delivery Semantics

**Date**: 2026-07-31 · **Status**: 📋 Planned
**Parent (implementation plan)**: [`docs/research_questions/v2/rq1/rq1_prepation.md`](../../../../research_questions/v2/rq1/rq1_prepation.md) (Design B, **IMPLEMENTED** 2026-07-31)
**Thesis RQ1**: [`tese/Notes/thesis_overview.md`](../../../../../../tese/Notes/thesis_overview.md) §6 RQ1

This is the **experiment plan** for the RQ1 delivery-semantics extension — the
"separate step" flagged in `rq1_prepation.md` §8. It turns the implemented
three-arm delivery machinery into a runnable, analyst-checkable campaign.

Split files in this folder:

| File | Purpose |
|---|---|
| `experiment_plan.md` | Intent, hypothesis, variable, success criteria, links (this file) |
| [`run_matrix.md`](run_matrix.md) | Detailed per-run configuration (labels, env, commands, cleanup) |
| [`analysis_focus.md`](analysis_focus.md) | Measurement contract, graph inventory, tooling contract |
| `phases_rq1_delivery.json` | Workload phase file (480 s, surge + drain + drop + tail) |

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
scaling policy (golden `osken-controller.env` thresholds; capacity caps and
`SCALEDOWN_COMPUTE_COOLDOWN_S=60` set in the per-arm env, identical across
arms), routing policy, workload (`phases_rq1_delivery.json`), topology,
resource limits (`STORAGE_CPUS=0.08 EDGE_CPUS=0.25 WAN_RTT_MS=185`),
clients/devices/nodes, `OVERLOAD_*` thresholds, and Tier 1 / persistent
reserves / cross-region storage **disabled**.

## 3. Run Matrix

Full detail in [`run_matrix.md`](run_matrix.md). Structure:

| Stage | Runs | Arms |
|---|---|---|
| Pre-flight (tooling + calibration gate) | 3 | one per arm |
| Main campaign | 9 (3 per arm) | A `event_preserving`, B `delayed_event_preserving`, C `poll` |

Env override files (one per named regime, in the `env/` subfolder of this
experiment folder): `env/rq1_event_preserving.env`, `env/rq1_delayed.env`,
`env/rq1_latest_state.env`. Phase file: `phases_rq1_delivery.json` (this
folder). These three files **supersede** `rq1_delivery_semantics.env` (which
lacked the capacity overrides needed for scale-up to fire). The env files are
deliberately placed under this v2/rq1 folder (not
`source/scripts/testing/controller_env_overrides/`); the harness resolves them
via `OSKEN_ENV_OVERRIDE_FILE` with a relative path (see §4).

The per-arm files share a small identical block (capacity, cooldown, disable
flags, `CONTROL_TICK_S`, log paths) — a deliberate, documented duplication so
each arm file is self-contained. The shared settings are **not** merged into
`current_state_integrated.env` because that file is the RQ2/RQ3 baseline (Tier 1
and reserves enabled) and the RQ1 disable flags must not alter it. Per-run
provenance is still captured by `controller_env_snapshot.env` and
`aggregator_env_snapshot.env`.

## 4. Run Configuration

Canonical per-run launch (all runs in the cloud VM at
`~/efficient-storage-in-edge-scenarios`; full per-arm table in `run_matrix.md`):

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n STORAGE_CPUS=0.08 EDGE_CPUS=0.25 WAN_RTT_MS=185 RANDOM_SEED=42 \
    make -C source/scripts setup_network create_clients setup_test_data run_experiment \
    OSKEN_ENV_OVERRIDE_FILE=../../docs/operation/testing/experiment/v2/rq1_experiment/env/<ENV_FILE> \
    RUN_LABEL=<LABEL> \
    PHASES_CONFIG=../../docs/operation/testing/experiment/v2/rq1_experiment/phases_rq1_delivery.json \
    CLIENTS=<N> CONTENT_ITEMS=<N> USERS=100 \
    DATA_SEED=42 CURL_MAX_TIME=30 \
    SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1 \
    > /tmp/<LABEL>.log 2>&1 &"
```

- `PHASES_CONFIG` and `OSKEN_ENV_OVERRIDE_FILE` are resolved relative to
  `source/scripts` (make cwd), hence the `../../docs/...` paths to the phases
  and per-arm env files in this folder.
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
5. **Overload is exercised:** during `overload_surge`, ≥ 30% of surge windows are
   labeled `overload` in the universe in **all** arms (else the surge did not trip
   `OVERLOAD_*` → calibration failure, see pre-flight gate G2).
6. **Scale-up response:** ≥ 1 scale-up decision per LAN in every arm during
   `overload_surge`, and usable capacity reached (`container_events.csv` spawn
   ready) — required so "demand shift → decision → capacity" is measurable.
7. **Scale-down response:** ≥ 1 scale-down decision per LAN in
   `demand_drop`/`tail` in **every arm**. A fires ≈ at cooldown expiry; B's
   decision lands ≈ `DELAY_S` later (delay-shifted); C fires when its delivered
   below-threshold windows in drop+tail reach the scale-down required count —
   with poll-30 that is ≈ 7 delivered windows ≈ the required 7, so C is
   **borderline, not exempt**. The analyst reports each arm's delivered-window
   count in drop+tail alongside the scale-down outcome; an arm that does not fire
   while its delivered count ≥ the required count is flagged for inspection (not
   auto-passed, not auto-failed).
8. **Transient service quality:** per-phase failure rate ≤ 2% in **all non-surge
   phases** (baseline, drain_1, demand_drop, tail); surge-phase degradation is
   expected — the comparison is **relative across arms** (see C9), not absolute.
   At the low volume of the 0.05-fraction phases (~30–45 requests per LAN) this
   means **at most 1 failure**; the analyst reports the request count alongside
   the rate.
9. **Delay-vs-loss ordering:** mean reaction latency (surge start → first scale-up
   decision) and info-age-at-decision order as B ≥ C > A, while delivered fraction
   orders as A ≈ B > C. If this ordering is violated, the run/arm is flagged for
   re-inspection before conclusions.

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
- [x] `phases_rq1_delivery.json` created (this folder)
- [x] Launch-path prerequisites understood: Arm C sets `POLL_INTERVAL_S=30` on the
      shell (`build_network_setup.sh` `-e` default is 10); `OVERLOAD_*` thresholds
      are set on the shell for `build_network_1/2.sh`, not in the controller env
      file
- [x] **Analysis tooling implemented** — `analysis/rq1_delivery_per_run.py` +
      `analysis/rq1_delivery_comparison.py` (see [`analysis_focus.md`](analysis_focus.md) §6),
      smoke-tested on synthetic runs.
- [ ] Files synced to cloud VM (`ssh cloud-vm`, repo at `~/efficient-storage-in-edge-scenarios`)

  > **Placement deviation (documented):** `phases_rq1_delivery.json` lives in this
  > experiment folder (not `testing/phases_override/`) per the v2 campaign
  > convention directed by the user; the single-canonical-`phases.json` rule is
  > deliberately deviated from for this named campaign. Each run still snapshots
  > `phases_snapshot.json`, so the analyzer's provenance is unaffected. The runner
  > passes an explicit `PHASES_CONFIG` path (no glob over `phases_override/`), so
  > the placement does not affect resolution. The per-arm env files are likewise
  > placed under this v2/rq1 folder (`env/`) rather than
  > `controller_env_overrides/`, per the same user-directed convention; the
  > harness consumes them via `OSKEN_ENV_OVERRIDE_FILE` with a relative path, and
  > each run still records the merged result in `controller_env_snapshot.env`.

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
  (arm ∈ `ep` | `delayed` | `ls`). Replicate aggregation includes **only numeric
  suffixes** (`_1`..`_3`); pre-flight (`_preflight`) runs are excluded from the
  replicate scatter.
- **C5 (environment):** the VM shell must not have `TELEMETRY_SOURCE` exported —
  `build_network_setup.sh` passes it through only when set, and the per-arm env
  file is authoritative for it. (Arm C deliberately sets `POLL_INTERVAL_S` on the
  shell; `TELEMETRY_SOURCE` must not be set on the shell.)

### C. Validity threats

- **Controller restart mid-run** re-pulls the window log and re-delivers →
  duplicate decisions; run invalid (thesis §8). Checked by C2.
- **In-delay-at-run-end:** Arm B windows still in the hold queue at run end are
  not "missed" — the trailing `drain_1`/`tail` phases (≥ `DELAY_S + WINDOW_S`)
  are sized to drain them; the analyzer still reports the residual separately.
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
  this folder's `phases_rq1_delivery.json`,
  this folder's `analysis/rq1_delivery_{per_run,comparison}.py`
