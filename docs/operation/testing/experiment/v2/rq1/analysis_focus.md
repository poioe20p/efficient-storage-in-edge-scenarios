# RQ1 Delivery Semantics — Measurement & Analysis Focus

Part of [`experiment_plan.md`](experiment_plan.md). Defines the measurement
contract, the graph inventory, and the analysis tooling contract for the RQ1
delivery-semantics campaign.

> **RQ1 v2 (final evidence):** this document's v2 contract (§0) supersedes the
> v1 framing for v2 runs. v1 folders remain the supporting record and keep the
> archived `results.md` numbers.

## 0. RQ1 v2 contract — full 2×2 factorial

Authoritative spec: [`rq1_v2_rework_plan.md`](rq1_v2_rework_plan.md).

### 0.1 Arms

| Arm | Source | Freshness | Completeness |
| --- | --- | --- | --- |
| A | `event_preserving` | sub-second | complete (frac ≈ 1.0) |
| B | `delayed_event_preserving` | +30 s | complete |
| C | `poll` (latest_state) | poll-30 (stale-lossy) | ≈ 1/3 |
| D | `sampled_push` (`SAMPLE_EVERY=3`) | sub-second | ≈ 1/3 |

### 0.2 Status-aware row contract (`client_requests.csv`)

- `status` column (14th): `completed | timeout | dropped | canceled`.
- `timeout` → `http_status="000"`, `latency_s` = elapsed to timeout.
- `dropped`/`canceled` → `http_status=""`, `latency_s=""`.
- **Failure = completed & `http_status != 200`** (only 200 is success for this
  edge service; 3xx/4xx under VIP misrouting are failures, not successes).
- `timeout_rate` = timeout / (offered − canceled − dropped); **canceled rows
  (phase-boundary drain artifacts) and dropped rows (client-side admission —
  they never reach the service and can never time out) are excluded from the
  denominator** and reported separately; `failure_rate` = failure / completed.
- Offered = all rows. Timeout/dropped/canceled NEVER enter latency percentiles
  or failure; they are reported separately (censoring flag at the cap).
- Delivery-log `mode` set includes `sampled_push` (Arm D).

### 0.3 Phase attribution (v2 rule)

- Client-side metrics: the generator `phase` label (authoritative).
- Decision/window-side boundaries: **derived from the generator labels**
  (min/max `sent_at` per phase). The open-loop supervisor shifts every later
  phase by the phase-boundary drains and workers progress independently, so
  contiguous anchoring is wrong; label-derived boundaries are correct.
- Validation: phases must start in schedule order (monotonic min `sent_at`) —
  violation hard-fails the run (`--skip-phase-validation` for legacy folders).
  A phase span beyond nominal + 2 drains + 2 windows is an informational
  warning (the open-loop supervisor is time-bounded per phase, so the v1
  plateau-overrun artifact is structurally impossible under open-loop).

### 0.4 Pre-registered statistics (n=5; effect-size, no alpha claim)

Primary attribution pairs (factorial edges — Mann–Whitney U exact/normal +
Cliff's delta):

- **delay:** A–B (`ep` vs `delayed`), D–C (`sp` vs `ls`)
- **loss:** A–D (`ep` vs `sp`), B–C (`delayed` vs `ls`)

Headline tradeoff (Cliff's delta only, no significance claim): B–D (`delayed`
vs `sp`), A–C (`ep` vs `ls`).

Metrics: usable-capacity latency, `timeout_rate`, `failure_rate`
(completed-only), time-to-recover (scale-down from `recovery_gap` start),
info-age at decision. ≥ 3 defined runs/cell to test; no censored value enters
MWU; latency percentiles descriptive-only with a censoring flag. Implemented
in `docs/research_questions/v2/rq1/rq1v2_p3_01_stats.py`.

### 0.5 Reporting rules

- Offered vs completed recorded separately (per phase).
- Scale-down claims reported from `decision_log` **and** `container_events`
  jointly (bounded claim; no controller change). `rq1v2_p3_01_stats.py`
  reports `scale_down_latency_s` (decision-log, pre-registered primary)
  alongside `removal_latency_s` (container_events first dynamic-compute
  removal) as the joint cross-check.
- C8: cross-arm comparison on non-surge `timeout_rate` + `failure_rate` under
  equal offered load (may honestly be a null).
- **Arm C lan2 asymmetry:** `rq1v2_p4_01_lan2_asymmetry.py` (per-run per-LAN
  plateau rates, load distribution, per-backend counts, per-LAN delivery
  counts). Pre-flight: run against the open-loop calibration runs to check
  whether the v1 asymmetry reproduces before blocks start. Full root-cause:
  after the campaign. No Arm C quality claim until resolved or bounded.

## 1. Artifact contract (per run, per LAN)

Collected by `run_experiment.sh` → `collect_rq1_artifacts()` into the run folder:

| Artifact | Role | Key fields |
|---|---|---|
| `window_log_lan{1,2}.jsonl` | **Universe** — every published window | `network_id, window_seq, window_id, window_end, overload, servers, storage_servers, domain_summary, control_events` |
| `telemetry_delivery_log_lan{1,2}.csv` | **Delivered** — every window the controller consumed | `network_id, window_seq, window_id, window_end, delivery_ts, delay_s, mode, release_ts` |
| `decision_log_lan{1,2}.csv` | **Actions** — controller decisions | `ts, network_id, window_id, action_type, action` |
| `ack_log_lan{1,2}.jsonl` | Producer-side acks (audit/cross-check) | `window_id, window_seq, delivered_at` |
| `controller_env_snapshot.env`, `aggregator_env_snapshot.env` | Provenance | base + override values actually used |

**Delivery-log row conventions** (implemented in `delivery_log.py`; the analyzer
must honor them):

- row with non-empty `window_id` = a real delivered window (dedup by `window_id`);
- `window_id=None` row is **not** a delivered window; `mode` distinguishes
  `gap_recovery` (aged out / never delivered) from `processing_error` (delivered
  from the log but `on_update` raised before consuming).

## 2. Derived metrics

| Metric | Definition | From | Meaning |
|---|---|---|---|
| Delivery delay | `delay_s = delivery_ts − window_end` | delivery log | how old the window is when the controller consumes it |
| Info age at decision | `decision_ts − window_end` (join via `window_id`) | decision log + delivery log | effective staleness of the evidence behind each action |
| Delivered fraction | delivered windows ÷ universe windows | delivery log vs window log | completeness |
| Missed overload windows | (universe ∩ overload) − delivered, **excluding** `in-delay-at-run-end` | window log vs delivery log | loss of overload evidence |
| In-delay-at-run-end | delivered count 0, `window_end + DELAY_S > universe_last_window_end` | window log | Arm B residual, not "missed" |
| Overload detection delay | `window_end` → first decision referencing the window | window log + decision log | observability latency |
| Demand-shift → decision | phase transition ts → first decision ts | phases_snapshot + decision log | reaction latency |
| Demand-shift → usable capacity | phase transition ts → spawn ready | phases_snapshot + container_events | capacity latency |
| Per-phase service quality | p50/p95/p99, failure rate, completed | client_requests | transient quality |
| Overhead | controller CPU% / RSS; per-window counts + bytes | controller_stats, logs | cost of delivery |

## 2b. Analysis rules (must be implemented in the per-run analyzer)

- **Universe bounds:** `window_log.jsonl` also contains pre-run (setup) and
  post-run (teardown) empty windows. The universe is bounded to the **active
  traffic window** = `[first_request_ts_floor, last_request_ts_ceil]`, where
  `first/last_request_ts` come from `client_requests.csv` and are rounded to the
  `WINDOW_S` boundary. Windows outside this range are excluded from
  delivered-fraction and missed-overload computations.
- **Phase transitions:** `phases_snapshot.json` gives durations only. **v1
  rule:** boundaries anchored to the traffic window start (`phase_i_start =
  traffic_start + sum(durations before i)`). **v2 rule (§0.3):** boundaries are
  derived from the generator `phase` label (min `sent_at` per phase) because
  the open-loop supervisor shifts later phases by the phase-boundary drains
  and workers progress independently; contiguous anchoring is wrong under
  open-loop. Reaction-latency metrics use the derived boundaries; the order
  validation (§0.3) hard-fails corrupt runs.
- **Overload episode (per-episode visibility, arm C):** consecutive overload
  windows with at most one intervening non-overload window form one episode. An
  episode is "visible" if any delivered window inside it (or within one
  `WINDOW_S` of it) produced a controller decision.

## 3. Thesis RQ1 measurement mapping

| Thesis primary measurement | Delivered by |
|---|---|
| Completed and missed overload windows | delivered fraction, missed overload windows |
| Information age and delivery delay | delivery delay, info age at decision |
| Time from demand shift to scaling decision | demand-shift → decision |
| Time from demand shift to usable capacity | demand-shift → usable capacity |
| Offered and completed requests | per-phase completed from client_requests |
| Latency distributions and failure rate | per-phase p50/p95/p99, failure rate |
| Controller and telemetry overhead | overhead metrics |

## 4. Analysis approach

- **Contrast structure:** A is the control. **A vs B** isolates the delay
  penalty (same completeness, higher info age). **A vs C** isolates the
  loss-of-intermediate-evidence penalty (lower info age, lower completeness).
  Headline: **completeness-vs-info-age tradeoff** per arm.
- **Overload semantics:** missed overload windows computed by the analyzer only.
  Report **per-window** (missed count) and **per-episode** visibility for Arm C:
  an episode may still be observed via a later delivered overload window even
  though intermediate windows were dropped; the analyst must state both.
- **Arm A as a harness check:** any `gap_recovery`/`processing_error` in Arm A
  indicates a defect, not an arm effect.
- **Grouping:** runs grouped by arm from the run-folder pattern
  `<timestamp>_rq1_delivery_<arm>_<suffix>`; replicates aggregated with
  per-replicate scatter dots and error bars (same visual standard as the old
  `rq1-cross-mode-comparison` graphs).

## 5. Graph inventory

Cross-mode comparison suite, output to
`docs/operation/testing/experiment/v2/rq1/graphs/comparison/`. All graphs use
**grouped/bar charts with per-replicate scatter dots + error bars** (the old
`rq1-cross-mode-comparison` visual standard) — box plots are deliberately not
used (unreadable with per-event dots). The latency/throughput/timeout/degraded
graphs read `client_requests.csv` directly and attribute phases by the
generator's `phase` column (the analyzer's anchored phase bucketing is
misaligned — plateau overrun; see `results.md` deep-verification note).

| # | Graph | Metric | Type |
|---|---|---|---|
| 1 | `delivery_completeness.png` | delivered % of universe; delivered % of overload windows | grouped bar + per-replicate dots |
| 2 | `delivery_delay.png` | `delay_s` per-run mean per arm (+ `DELAY_S` line) | bar + per-replicate dots + error bars |
| 3 | `info_age.png` | info-age at scale-up and at decision per arm | 2-panel bar + dots |
| 4 | `missed_overload.png` | universe / delivered / missed overload windows per arm | grouped bar + dots |
| 5 | `overload_detection_delay.png` | `window_end` → first decision (per overload window) | bar + dots |
| 6 | `scale_reaction_latency.png` | plateau → first scale-up decision; → usable capacity | 2-panel bar + dots |
| 7 | `scale_down_latency.png` | plateau end → first scale-down decision (`recovery_gap` row) | bar + dots |
| 8 | `phase_latency.png` | p50/p95/p99 per phase per arm (raw phase labels) | grouped bar + per-replicate dots |
| 9 | `overhead.png` | controller CPU% + RSS per arm | bar + dots |
| 10 | `completeness_vs_infoage.png` | delivered fraction vs info-age-at-decision per arm | scatter (arm-colored) |
| 11 | `per_phase_latency_p50.png` | per-phase latency p50 per arm | grouped bar + per-replicate dots |
| 12 | `per_phase_latency_p95.png` | per-phase latency p95 per arm | grouped bar + per-replicate dots |
| 13 | `per_phase_latency_p99.png` | per-phase latency p99 per arm | grouped bar + per-replicate dots |
| 14 | `throughput.png` | total requests served per arm | bar + dots |
| 15 | `throughput_per_phase.png` | per-phase requests per arm | grouped bar + dots |
| 16 | `timeout_comparison.png` | `http_status=0` rate per arm | bar + dots |
| 17 | `per_phase_timeout.png` | per-phase `http_status=0` rate per arm | grouped bar + dots |
| 18 | `degraded_5s.png` | % requests with latency > 5 s per arm | bar + dots |
| 19 | `degraded_10s.png` | % requests with latency > 10 s per arm | bar + dots |
| 20 | `degraded_20s.png` | % requests with latency > 20 s per arm | bar + dots |
| 21 | `endpoint_latency_p50.png` | overall endpoint p50 per arm | bar + dots |
| 22 | `endpoint_latency_p95.png` | overall endpoint p95 per arm | bar + dots |
| 23 | `reaction_latency_max.png` | plateau → first scale-up decision, max over LANs | bar + dots |
| 24 | `compute_cpu.png` | avg compute node CPU% during `compute_plateau` | bar + per-replicate dots |
| 25 | `storage_cpu.png` | avg storage node CPU% during `compute_plateau` | bar + per-replicate dots |

## 6. Tooling contract (**implemented**)

The analyzer + comparison scripts live at this experiment folder's
`analysis/` subfolder (`docs/operation/testing/experiment/v2/rq1/analysis/`),
per the user-directed v2/rq1 placement; the pre-registered statistics script
lives at `docs/research_questions/v2/rq1/` (canonical per-RQ location).
Analyzer + comparison smoke-tested on synthetic runs (2026-07-31); stats
script smoke-tested on synthetic runs (2026-08-04).

- **`rq1_delivery_per_run.py`** (CLI: `<run_folder>`; `--skip-phase-validation`
  for legacy v1 folders with the known plateau overrun)
  - Inputs: the four RQ1 artifacts + `client_requests.csv`, `container_events.csv`,
    `controller_stats.csv`, `phases_snapshot.json`, env snapshots,
    `open_loop_schedule.json` (drain provenance, optional).
  - Implements the analysis rules in §2b + the v2 rules in §0.2–§0.3
    (status-aware service quality, generator-label phase derivation +
    validation).
  - Outputs per run (into `<run_folder>/analysis/rq1_delivery/`):
    - `delivery_integrity.csv` — per LAN: arm, universe, delivered, delivered_frac,
      overload_total, overload_delivered, overload_missed, in_delay_at_end,
      gap_recovery, processing_error, ack_count;
    - `delivery_delay.csv` — per delivered window: `window_id, window_end,
      delivery_ts, delay_s, release_ts, mode, phase`;
    - `info_age.csv` — per decision: `ts, window_id, window_end, info_age_s,
      action_type, action`;
    - `overload_observability.csv` — per overload window: `window_id, window_end,
      delivered, episode_id, first_decision_ts, detection_delay_s, acted`;
    - `overload_episodes.csv` — per episode: `episode_id, n_windows, window_ids,
      delivered_any, visible, first_decision_ts`;
    - `reaction_timeline.csv` — per phase per LAN: `phase, network_id,
      phase_start, scale_up_first_ts, scale_down_first_ts, usable_capacity_ts,
      decision_latency_s, capacity_latency_s, scale_down_latency_s`;
      `scale_down_latency_s` is carried **only on the `recovery_gap` row** and
      measured from `recovery_gap` start (the generator-derived first
      `recovery_gap` request under the v2 label-derived boundaries — note it
      is NOT generally the same timestamp as `compute_plateau` end under
      open-loop drains/worker stagger), using the first cooldown-gated
      scale-down after the plateau (A/B land in `recovery_gap`, C in
      `demand_drop`);
    - `phase_service_quality.csv` — per phase per LAN (v2 columns): `offered`,
      `completed`, p50/p95/p99 (completed+ok only), `failure_count`,
      `failure_rate` (completed-only), `timeout_count`, `timeout_rate`
      (timeout/(offered−canceled−dropped)), `dropped_count`, `canceled_count`
      (status columns blank for legacy runs, which keep the v1 failure-rate
      denominator of all rows);
    - `overhead.csv` — per controller container: mean CPU%, mean RSS;
    - `run_meta.csv` — arm, window_s, delay_s, bounds, phase names.
  - Failure behavior: exits cleanly with a message if a required artifact
    (`window_log`, delivery/decision log, `client_requests.csv`,
    `phases_snapshot.json`, `controller_env_snapshot.env`) is missing;
    optional artifacts (`ack_log`, `container_events.csv`,
    `controller_stats.csv`) degrade gracefully.
- **`rq1_delivery_comparison.py`** (CLI:
  `--run-dirs-ep/--run-dirs-delayed/--run-dirs-ls/--run-dirs-sp`, `--output-dir`)
  - Groups runs by arm, aggregates the per-run CSVs, renders the §5 graph suite
    with per-replicate variance. Timeout graphs are status-aware
    (`status=timeout`); latency/throughput graphs read `client_requests.csv`
    but exclude timeout/dropped/canceled rows (latency percentiles over
    completed+ok only; throughput = completed).
- **`rq1v2_p3_01_stats.py`** (CLI: per-arm `--run-dirs-*`, `--output`)
  — pre-registered statistics (§0.4); canonical location
  `docs/research_questions/v2/rq1/`.
- **Gates:** `make rq1_analyzer_selftest` and the sampled-push selftest (see
  `run_matrix.md` §9 pre-flight gate (c) — on the VM host, run the sampled-push
  selftest inside the `osken-controller` image because host python3 lacks
  pydantic; the selftest injects an os_ken hub stub). Both must pass before
  v2 blocks.
- **Run location:** where the data lives (cloud VM), then `scp` the
  `graphs/comparison/` folder back locally — same convention as the old
  `rq1-cross-mode-comparison` skill.
