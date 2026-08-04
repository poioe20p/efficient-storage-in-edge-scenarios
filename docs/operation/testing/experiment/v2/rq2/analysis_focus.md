# RQ2 Bottleneck-Aware Scaling — Measurement & Analysis Focus

Part of [`experiment_plan.md`](experiment_plan.md). Defines the measurement
contract, the graph inventory, and the analysis tooling contract for the RQ2
campaign.

## 1. Artifact contract (per run, per LAN)

Collected by `run_experiment.sh` → `collect_rq1_artifacts()` into the run folder
(the RQ1 artifact set is sufficient for RQ2):

| Artifact | Role | Key fields |
|---|---|---|
| `decision_log_lan{1,2}.csv` | **RQ2 decision universe** — one `scale_up` row per evaluated window (RQ2 arms, 20-col) | `ts, network_id, window_id, action_type, action, compute_score_norm, storage_score_norm, compute_threshold, storage_threshold, compute_fired, storage_fired, compute_eligible, storage_eligible, bottleneck_class, selected_action, rejected_action, compute_budget_used, storage_budget_used, budget_cap, reason` |
| `window_log_lan{1,2}.jsonl` | **Universe** — every published window | `network_id, window_seq, window_id, window_end, overload, servers, storage_servers, domain_summary, control_events` |
| `phases_snapshot.json` | **Episode ground truth** (post-hoc label, D5) | phase names/durations |
| `controller_env_snapshot.env` | Provenance | `SCALEUP_POLICY`, `ACTION_BUDGET_PER_TIER`, `BOTTLENECK_CLASSIFY_MARGIN`, caps, scale-down |
| existing | `client_requests.csv`, `per_node_stats.csv`, `resource_stats*.csv`, `controller_stats.csv`, `elasticity_events.csv`, `container_events.csv`, `controller_lan{1,2}.log` | latency/failures, per-node CPU, spawn/removal timing |

**Decision-log row conventions** (implemented in `_log_decision`; the analyzers
must honor them):

- RQ2 arms: exactly one `scale_up` row per evaluated window (a window with
  `domain_summary`, Thread 2 not busy), including `selected_action="none"`;
  empty (`domain_summary is None`) and busy windows produce **no** `scale_up`
  row — this defines the decision universe.
- Non-scale-up rows (scale-down, absent-node, reserve, cancel-drain) keep RQ1's
  `action_type`/`action` semantics within the 20-column format.
- `episode_label` is **not** a controller column; the analyzer attaches it from
  `phases_snapshot.json` (D5).

## 2. Derived metrics

| Metric | Definition | From | Meaning |
|---|---|---|---|
| Decision universe | `action_type="scale_up"` rows, dedup by `(window_id, action_type)` | decision log | one per evaluated window |
| Episode label | phase containing `window_end`, from `phases_snapshot.json` boundaries | decision log + phases snapshot | ground-truth bottleneck |
| Classifier-vs-episode agreement | fraction of episode windows where `bottleneck_class` == induced episode (denominator = episode windows with `window_end` in the episode phase **and both tiers eligible**, per the tool) | decision log + phases snapshot | D3 proxy check (H3) |
| Selected vs rejected action | `selected_action`, `rejected_action` columns | decision log | decision quality |
| Budget usage | `compute_budget_used`/`storage_budget_used`/`budget_cap`/`reason` | decision log | budget binds (per LAN) |
| Action counts | per-tier spawns = `scale_up` rows with `selected_action==tier` | decision log | number of scale actions |
| Time to recover bottleneck pressure | selected-action row ts → targeted tier's `score_norm` < its `*_threshold` | decision log (evidence series) | relief in the targeted tier |
| Time to usable capacity | action ts → first serving on the new node | `extract_spawn_metrics --tiers compute,storage --anchor decision` | capacity latency |
| Node-minutes | Σ(node count × lifetime), actual spawns only, LIFO pairing to removals | decision log | efficiency |
| Per-phase service quality | p50/p95/p99, failure rate, completed | `client_requests.csv` | transient quality |
| Resource health | per-node CPU, storage CPU, DB latency per phase | `resource_stats*`, `per_node_stats.csv` | tier pressure |

## 3. Thesis RQ2 measurement mapping

| Thesis primary measurement | Delivered by |
|---|---|
| Time to recover the bottleneck-specific pressure | relief tool (time-to-recover) |
| Time to usable capacity | `extract_spawn_metrics --anchor decision` |
| p50/p95/p99 latency, failures, completed offered demand | per-phase service quality |
| Compute and storage node-minutes | node-minutes tool |
| Number of scale actions | decision-analysis tool |
| Whether the selected action produces measurable relief in the targeted tier | relief tool |
| Cost of the action itself (replica-sync bandwidth / transient overload) | elasticity/container events + storage CPU during spawns (qualitative, reported) |

## 4. Analysis approach

- **Contrast structure (per episode type):** the correctly-aligned fixed arm is
  the reference. `bottleneck_aware` vs reference → does telemetry-driven
  selection match the right fixed arm? `bottleneck_aware` vs mis-aligned fixed
  arm → does it avoid the wrong action's cost (recovery, node-minutes)?
  Headline: **cross-over** — in `cb` episodes `cf`≈`ba` beat `sf`; in `db`
  episodes `sf`≈`ba` beat `cf`.
- **Episode validity:** `rq2_bottleneck_validation.py` is **independent** of the
  controller — raw `window_log.jsonl` `domain_summary` signals only; its
  primary verdict is **median** proc-vs-db dominance
  (`median(avg_time_proc_ms) ≥ median(avg_time_db_ms)` for compute-bound,
  inverse for data-bound) — the median is robust to dynamic-server
  lifecycle/spawn transients — with CPU/DB-latency elevation as a secondary
  diagnostic. A run whose induced bottleneck does not match its label
  (criterion 2) is flagged before any policy comparison.
- **Decision-signal statistic (median-era, 2026-08-03):** the decision-log
  evidence (`score_norm`, `bottleneck_class`, `*_fired`) is computed from
  **median** latency (`LATENCY_SIGNAL_MODE=median`) with the **composite
  storage signal** (storage CPU 0.60 + median DB latency 0.40, G0-v4) —
  consistent with the median-based validator. RQ2 adds the **Option-2 tuning**:
  `SCALEUP_STORAGE_CPU_FLOOR=35` (2026-08-03) so compute-bound lifecycle CPU
  transients (29–31 %) cannot trigger storage; residual compute-bound storage
  fires are latency-driven tail outliers (accepted). Calibration evidence:
  `20260803_*_cal{,2}` runs + `run_matrix.md` §6. Block-1 runs from 2026-08-02
  used the mean-era signal and are **superseded** (re-run on this config; see
  `mean_vs_median_signal_finding.md`).
- **Data-path / read preference (data-path fix 2026-08-03):** the first
  Block-1 set (`20260803_114003_rq2_cf_cb_1` … `20260803_141034_rq2_sf_db_1`)
  had `EDGE_MONGO_READ_PREFERENCE` unset (`primary`) — storage **secondaries
  never served reads** (rejected with `NotPrimaryOrSecondary`/13436), so
  storage scale-out produced ~zero usable read capacity and the data-bound
  cross-over was confounded. Those 6 runs were **deleted** and Block 1 is
  **re-run on the fixed path** — all re-run cells (and the control re-run) set
  `EDGE_MONGO_READ_PREFERENCE=secondaryPreferred` so secondaries serve reads;
  storage serving is now measurable. Storage per-node `request_count` is an
  **activity-window flag** (max ~1/poll), NOT a request volume — never divide
  it by compute `request_count`. See
  `read_preference_data_path_finding.md`.
- **Budget reporting:** budget is per LAN (D4); report per-LAN and the 2-LAN
  aggregate.
- **Grouping:** runs grouped by cell from the run-folder pattern
  `<timestamp>_rq2_<policy>_<episode>_<suffix>`; replicates aggregated with
  per-replicate scatter dots + error bars (same visual standard as RQ1).

## 5. Graph inventory

Cross-cell comparison suite, output to
`docs/operation/testing/experiment/v2/rq2/graphs/comparison/`. All graphs use
**grouped/bar charts with per-replicate scatter dots + error bars** (RQ1
standard). Group by cell (policy × episode) unless noted.

| # | Graph | Metric | Type |
|---|---|---|---|
| 1 | `bottleneck_validation.png` | per-run induced-tier signals (compute CPU/proc vs storage CPU/T_db during episode) | grouped bar + dots |
| 2 | `classifier_agreement.png` | classifier-vs-episode agreement per `ba` cell | bar + dots |
| 3 | `selected_action.png` | per-cell selected-action distribution (compute/storage/none) | stacked bar |
| 4 | `action_counts.png` | per-tier spawn counts per cell | grouped bar + dots |
| 5 | `budget_usage.png` | `*_budget_used` vs `budget_cap` per tier per cell; `reason` distribution | bar + dots |
| 6 | `time_to_recover.png` | time-to-recover bottleneck pressure per cell | bar + dots |
| 7 | `time_to_usable_capacity.png` | action ts → first serving per cell (compute + storage) | bar + dots |
| 8 | `latency_p50.png` | episode-phase p50 per cell | grouped bar + dots |
| 9 | `latency_p95.png` | episode-phase p95 per cell | grouped bar + dots |
| 10 | `latency_p99.png` | episode-phase p99 per cell | grouped bar + dots |
| 11 | `failure_rate.png` | episode-phase failure % per cell | bar + dots |
| 12 | `node_minutes.png` | compute + storage node-minutes per cell (per unit of completed demand) | grouped bar + dots |
| 13 | `relief_targeted_tier.png` | post-action targeted-tier `score_norm` vs threshold (relief evidence) per cell | bar + dots |
| 14 | `cross_over.png` | headline: per-episode mean time-to-recover + p95 across the 3 policies | grouped bar + dots (the key figure) |
| 15 | `counterbalance.png` | per-run cell (policy × episode × replicate) from run-folder names; block order recorded by the runner | table/scatter |

## 6. Tooling contract

The RQ2 analyzers are implementation deliverables and live canonically at
`docs/research_questions/v2/rq2/` (referenced here, **not duplicated** —
deviating from RQ1's copy-in-experiment-folder pattern to keep a single source
of truth; the user can override if copies are preferred). Run them locally on
copied-back run folders. All four first confirm the run is an RQ2 run by
reading `controller_env_snapshot.env` (`SCALEUP_POLICY` ∈ the three RQ2 arms;
`dual`/RQ1 runs are skipped).

- **`rq2_bottleneck_validation.py`** (CLI: `<run_dir> [--lan 1|2] [--csv OUT]`)
  — independent of the controller; from `window_log.jsonl` raw signals, its
  verdict is the **median** proc-vs-db dominance during the episode
  (`median(avg_time_proc_ms) ≥ median(avg_time_db_ms)` compute-bound; inverse
  data-bound) — the median is robust to dynamic-server lifecycle/spawn
  transients; CPU / DB-latency elevation is a secondary diagnostic, not part
  of the pass verdict. Emits a per-run validation table.

- **T9.8 cooldown note:** the fire-keyed scale-down check reads
  `SCALEDOWN_*_COOLDOWN_S` from `controller_env_snapshot.env` (compute 180,
  storage 30 in these RQ2 envs). The snapshot must contain those keys for the
  check to be valid; verify before analysis.
- **`rq2_decision_analysis.py`** (CLI: `<run_dir> [--csv OUT]`) — filters
  `scale_up` rows, joins `window_id` ↔ `window_log.jsonl`, attaches
  `episode_label` from `phases_snapshot.json`; emits the per-run decision table,
  per-tier action counts, per-window classifier-vs-episode agreement, budget
usage (per LAN), and the per-run counterbalance cell (policy × episode ×
replicate; the cross-run matrix is assembled by the analyst from the run-folder
names).
- **`rq2_relief_analysis.py`** (CLI: `<run_dir> [--csv OUT]`) — per selected
  action, from the decision-log evidence series: when the targeted tier's
  `score_norm` falls back under its `*_threshold` → time-to-recovery; whether
  relief is in the targeted tier.
- **`rq2_node_minutes.py`** (CLI: `<run_dir> [--csv OUT]`) — per tier per run:
  actual spawns only (`scale_up` rows with `selected_action==tier`), dedup by
  `(window_id, action_type)`, LIFO pairing to removals; Σ(node count ×
  lifetime), normalised per unit of completed demand.
- **`extract_spawn_metrics.py`** (CLI: `<run_dir> --tiers compute,storage
  --anchor decision [--out ...]`, at `source/scripts/testing/analysis/rq2/`) —
  time-to-usable-capacity: compute spawns from `compute:` lines +
  `client_requests.csv` `backend_id` (TFR); storage spawns from `data:` lines
  (TTFT from `per_node_stats.csv` first serving window, `rs_secondary_ready`
  as readiness diagnostic).

**Run location:** where the data lives (cloud VM), then `scp` the run folders
back locally for analysis — same convention as RQ1.

---

## 7. RQ2 v2 measurement contract (final evidence)

This section **supersedes §1–§6 as the measurement contract for the final RQ2
evidence** (the v1 contract above remains the supporting record). Spec:
`rq2_v2_rework_plan.md` §2. Implemented v2 analyzers live at
`docs/research_questions/v2/rq2/` (referenced, not duplicated):

| Analyzer | Purpose | Output |
|---|---|---|
| `rq2v2_p2_01_sync_cost.py` | replica-sync action cost per added storage member | `sync_cost.csv` |
| `rq2v2_p2_02_relief_flatten.py` | secondary relief-flatten signal (score plateau after action) | `relief_flatten.csv` |
| `rq2v2_p2_03_stats.py` | pre-registered statistics on `campaign_dataset.csv` | `stats_summary.csv` |

### 7.1 `status`-aware metrics (row-value contract)

`client_requests.csv` gains a **14th/last column `status`** with classes
`completed | timeout | dropped | canceled` (all consumers audited in the
Phase-1 pass). Definitions with **unified denominators**:

| Metric | Definition | Denominator |
|---|---|---|
| **Offered** | all rows (every dispatched request) | — |
| **Completed** | `status=completed` | offered |
| **Timeout rate** — the **primary degradation statistic**, defined for every run | `status=timeout` / offered | offered |
| **Failure rate** | `status=completed` **and** `http_status` not in (`"200"`, `""`) | completed |
| **Dropped / canceled** | `status=dropped` / `status=canceled` | reported separately; **excluded from latency and failure** |

Row-value contract (implemented in the driver): `timeout` →
`http_status="000"`, `latency_s` = elapsed to timeout; `dropped`/`canceled` →
`http_status=""`, `latency_s=""`. Never compute failure from a timeout row;
never let a stale consumer reintroduce the cap artifact into p99.

### 7.2 Sync-cost metric

`rq2v2_p2_01_sync_cost.py` (CLI: `<run_dir> [--output FILE]`) — measures the
MongoDB **initial-sync cost** paid when a storage member is added: from
`service_logs/edge_storage_*.log` (STARTUP2 → SECONDARY transitions +
`initial sync done` `bytesToCopy`; `rs_secondary_ready` as fallback),
`container_events.csv`, and `resource_stats*.csv`/`per_node_stats.csv`.
`sync_cost.csv` columns: `member_id, add_ts, first_secondary_ts,
sync_duration_s, bytes_applied, storage_cpu_during_sync_pct, source`.
`bytes_applied` is `null` when unobtainable (sync duration + storage CPU are
the primary metrics). A cell that adds no storage produces a header-only file
(reported as counts + medians, not tested). **Not inferred from existing
artifacts.**

### 7.3 Relief-flatten metric (secondary relief signal)

`rq2v2_p2_02_relief_flatten.py` (CLI: `<run_dir> [--output FILE]
[--flatten-window-s 120]`) — per spawned scale-up action, whether the targeted
tier's `score_norm` **stops rising / plateaus** within
`RELIEF_FLATTEN_WINDOW_S` after the action (`plateau_within_window`), in
addition to the existing below-threshold recovery
(`recovered_below_threshold`); `relief_signal` = either. Output:
`relief_flatten.csv` (columns `window_id, action_ts, selected_action,
targeted_tier, score_norm_at_action, score_norm_peak_after,
plateau_within_window, recovered_below_threshold, relief_signal`).

### 7.4 Statistics contract (pre-registered, significance-capable at n=6)

`rq2v2_p2_03_stats.py` (CLI: `--dataset campaign_dataset.csv
[--output stats_summary.csv]`):

- **n = 6 per cell → α-capable.** Mann–Whitney U at n=6 has minimum p = 0.0022
  (exact enumeration); α=0.05 significance claims are possible (~22 distinct
  p-values ≤ 0.05 reachable). Conclusions rest on **significance (where
  reached) + Cliff's delta magnitude** (≥ 0.6 = large) and **direction
  consistency across all 6 replicates**; where p > 0.05, claims are scoped to
  effect size + direction only (no significance language).
- **Pre-registered comparison hierarchy** (per episode):
  - *headline*: **aligned vs mis-aligned** (`cf` vs `sf` in cb; `sf` vs `cf`
    in db) — the cross-over proof;
  - *primary*: **`ba` vs mis-aligned** (value-of-information) and **`ba` vs
    aligned** (equivalence — within 1.5× of the aligned median);
  - *exploratory*: `cf` vs `sf` efficiency — Cliff's delta only, no claim.
  Metrics: `timeout_rate`, `failure_rate`, `node-minutes`, `time-to-recover`.
- **No censored value enters MWU** — latency percentiles are descriptive only
  (median-of-replicates + per-run scatter + IQR) with a **censoring flag**
  where the 300 s cap binds.
- **≥6 defined values rule:** a comparison is evaluated only where all 6 runs
  per cell have a defined value; cells with undefined values (e.g.
  `cf_cb`/`sf_cb` time-to-recover, cells that add no storage for sync-cost)
  are excluded and reported as counts + medians (Cliff's delta only).
- Output: `stats_summary.csv` (rows `episode, pair, metric, n_a, n_b,
  median_a, median_b, mwu_p, clifffs_delta, evaluated, note`).

### 7.5 Censoring rule (latency percentiles)

With `CURL_MAX_TIME=300`, any latency percentile that reaches the 300 s cap is
the **cap, not a measurement** — flagged (censoring flag) and reported
descriptively; the **per-run `timeout_rate` is the primary degradation
statistic** (defined for every run, independent of the cap).

### 7.6 New gates

- **Per-run driver self-test** — enforced inside `run_traffic()` in
  `run_experiment.sh` (fail-fast, exit 1) whenever `TRAFFIC_DRIVER_MODE=open_loop`;
  a stronger gate than a one-off pre-flight check.
- **Concurrency stress check** (pre-flight, Phase 5 step 1b): max in-flight at
  the intended rate and the 300 s cap must not exhaust container/conntrack
  connection limits.
- **Stats gate** — MWU computed on all pre-registered primary pairs with
  missing-value exclusions recorded.

### 7.7 Efficiency (SC6) — pre-registered interpretation nuance

**Background (pre-campaign evidence, 2026-08-04):** calibration/validation runs
(`rq2_g2_ba_db_cal4`, `rq2_g2_ba_db_hard_cal`, `rq2_g2_ba_strict_db_cal`)
show that `ba` in the **db** episode spends **both** action budgets
(compute=4 **and** storage=4 per LAN): the classifier commits to storage on
most windows, but single-tier compute fires recur (~1/3 of episode windows), so
compute actions also bind. The aligned `sf` arm spends storage only (4);
mis-aligned `cf` spends compute only (4). If node lifetimes are comparable,
`ba` node-minutes in db may approach **2× the aligned arm**.

**Pre-registered decision rule (SC6)** — committed before the campaign
completes, so the db-cell outcome cannot reinterpret the criterion after the
fact:

1. `SC6` (`ba` node-minutes ≤ mis-aligned) is evaluated **as written**.
2. If it holds → the efficiency claim stands unchanged.
3. If it does **not** hold (`ba` spends both budgets; node-minutes > aligned or
   > mis-aligned), it is reported as a **finding, not a shortfall**:
   - `ba` recovers service quality to the aligned arm's level **without
     knowing the episode** (SC2 value-of-information on quality), and its
     node-minutes are **bounded by the action budget** (4/tier/LAN — the same
     ceiling each fixed arm hits on its own tier).
   - The efficiency narrative reframes from *"uses fewer nodes"* to
     *"avoids the mis-configured outcome at a bounded, budget-capped resource
     cost"* — the price of not knowing the episode.
   - Node-minutes are reported **per unit of completed demand**
     (node-minutes ÷ completed requests) alongside the raw figure, so the
     comparison is not distorted by differing completed-load denominators.
4. The same rule applies to the **cb** episode if classifier noise causes `ba`
   to spend storage budget there (cb classifier ≈ chance).
