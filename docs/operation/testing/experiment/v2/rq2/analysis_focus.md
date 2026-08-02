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
