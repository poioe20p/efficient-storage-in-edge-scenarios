# RQ1 Delivery Semantics — Measurement & Analysis Focus

Part of [`experiment_plan.md`](experiment_plan.md). Defines the measurement
contract, the graph inventory, and the analysis tooling contract for the RQ1
delivery-semantics campaign.

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
- **Phase transitions:** `phases_snapshot.json` gives durations only. Phase
  boundaries are anchored to the traffic window start: `phase_i_start =
  traffic_start + sum(durations of phases before i)`, where `traffic_start` is
  the rounded-down first client request ts. Reaction-latency metrics use these
  derived boundaries.
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
`docs/operation/testing/experiment/v2/rq1_experiment/graphs/comparison/`:

| # | Graph | Metric | Type |
|---|---|---|---|
| 1 | `delivery_completeness.png` | delivered % of universe; delivered % of overload windows | grouped bar + per-replicate dots |
| 2 | `delivery_delay_box.png` | `delay_s` per arm | box + per-event dots |
| 3 | `info_age_at_decision_box.png` | `decision_ts − window_end` per arm | box + per-decision dots |
| 4 | `missed_overload.png` | universe / delivered / missed overload windows per arm | grouped bar + dots |
| 5 | `overload_detection_delay.png` | `window_end` → first decision (per overload window) | bar + dots |
| 6 | `scale_reaction_latency.png` | surge → first scale-up decision; → usable capacity | 2-panel bar + dots |
| 7 | `scale_down_latency.png` | drop → first scale-down decision | bar + dots |
| 8 | `phase_latency.png` | p50/p95/p99 per phase per arm | grouped bar + error bars |
| 9 | `overhead.png` | controller CPU% + RSS per arm | bar + dots |
| 10 | `completeness_vs_infoage.png` | delivered fraction vs info-age-at-decision per arm | scatter (arm-colored) |

## 6. Tooling contract (**implemented**)

Implemented at this experiment folder's `analysis/` subfolder
(`docs/operation/testing/experiment/v2/rq1_experiment/analysis/`), per the
user-directed v2/rq1 placement. Smoke-tested on synthetic runs (2026-07-31).

- **`rq1_delivery_per_run.py`** (CLI: `<run_folder>`)
  - Inputs: the four RQ1 artifacts + `client_requests.csv`, `container_events.csv`,
    `controller_stats.csv`, `phases_snapshot.json`, env snapshots.
  - Implements the analysis rules in §2b (universe bounds, phase anchoring,
    episode definition).
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
    - `phase_service_quality.csv` — per phase per LAN: p50/p95/p99, failure,
      completed;
    - `overhead.csv` — per controller container: mean CPU%, mean RSS;
    - `run_meta.csv` — arm, window_s, delay_s, bounds, phase names.
  - Failure behavior: exits cleanly with a message if a required artifact
    (`window_log`, delivery/decision log, `client_requests.csv`,
    `phases_snapshot.json`, `controller_env_snapshot.env`) is missing;
    optional artifacts (`ack_log`, `container_events.csv`,
    `controller_stats.csv`) degrade gracefully.
- **`rq1_delivery_comparison.py`** (CLI:
  `--run-dirs-ep/--run-dirs-delayed/--run-dirs-ls`, `--output-dir`)
  - Groups runs by arm, aggregates the per-run CSVs, renders the §5 graph suite
    with per-replicate variance.
- **Run location:** where the data lives (cloud VM), then `scp` the
  `graphs/comparison/` folder back locally — same convention as the old
  `rq1-cross-mode-comparison` skill.
