# Experiment Plan — RQ2 Bottleneck-Aware Scaling Action

**Date**: 2026-08-02 · **Status**: ✅ **Completed** — 18/18 main runs validated on the fixed data path (2026-08-04); full evaluation in [`results.md`](results.md) and [`post_run_analysis.md`](post_run_analysis.md)
**Parent (implementation plan)**: [`docs/research_questions/v2/rq2/rq2_preparation.md`](../../../../research_questions/v2/rq2/rq2_preparation.md) (approved; code **IMPLEMENTED** — `PolicyGate`, `ScaleUpVerdict`, `commit_*`, 20-column decision log)
**Thesis RQ2**: [`tese/Notes/thesis_overview.md`](../../../../../../tese/Notes/thesis_overview.md) §6 RQ2
**Control group**: [`v2/control_group.md`](../control_group.md) (validated 2026-08-01) — the scale-vs-no-scale reference; RQ2 rebases its platform onto the control config (Option B) and varies `SCALEUP_POLICY`.

This is the **experiment plan** for the RQ2 required extension (policy gate +
bottleneck-aware action selection). It turns the implemented three-policy
machinery into a runnable, analyst-checkable campaign, mirroring the RQ1
campaign at [`v2/rq1/`](../rq1/).

Split files in this folder:

| File | Purpose |
|---|---|
| `experiment_plan.md` | Intent, hypothesis, variable, success criteria, links (this file) |
| [`run_matrix.md`](run_matrix.md) | Detailed per-run configuration (labels, env, commands, cleanup, gates) |
| [`analysis_focus.md`](analysis_focus.md) | Measurement contract, graph inventory, tooling contract |
| `env/` | 4 per-arm env files (`rq2_compute_first.env`, `rq2_storage_first.env`, `rq2_bottleneck_aware.env`, `rq2_bottleneck_aware_strict.env`) |
| (episode phase files) | `source/scripts/testing/phases_override/phases_rq2_compute_bound.json`, `phases_rq2_data_bound.json` |

---

## RQ2 v2 (final evidence)

> **This section is the final RQ2 evidence.** The 18-run campaign below
> (§1–§6, [`results.md`](results.md)) remains as the **v1 / supporting
> record** (characterization + reproduction); it is **not** final thesis
> evidence. Authoritative rework spec:
> [`rq2_v2_rework_plan.md`](rq2_v2_rework_plan.md) (Phases 1–3 implemented;
> this Phase 4 doc pass).

The v2 campaign is the **full compliance rework** — it removes the five v1
structural gaps (G1–G5, `rq2_v2_rework_plan.md` §1):

| Aspect | v2 setting |
|---|---|
| **Driver** | **open-loop** (`traffic_generator.py --driver-mode open_loop`): the arrival process is independent of completions, per-request synchronous response timing preserved. Rationale — Schroeder, Wierman & Harchol-Balter, *Open Versus Closed: A Cautionary Tale* (NSDI 2006): closed-loop models mask overload; a latency-coupled driver makes the offered load differ per arm, which is exactly the v1 confound (G1). |
| **Replicates** | n = 3 per cell (min achievable MWU p = 0.10 — **no α claims**; conclusions by effect size + 3/3 direction consistency, scoped to what n=3 supports) |
| **Cells** | 6 cells × 3 = **18 runs** — `cf_cb, cf_db, sf_cb, sf_db, ba_cb, ba_db` |
| **`ba-strict`** | implemented (knob `BOTTLENECK_STRICT_SINGLE=1`, env `rq2_bottleneck_aware_strict.env`, gate unit-tested) but **not run** in this 18-run campaign — kept as a documented option for a follow-up capacity-vs-classification test. |
| **Timeouts** | `CURL_MAX_TIME=300` s; `timeout` is a **distinct outcome class**, never merged into `failure`; the per-run `timeout_rate` is the primary degradation statistic (defined for every run). |
| **Concurrency / drain** | `INFLIGHT_WINDOW=1024` (window/rate > cap → `dropped` unreachable in production by design), `DRAIN_S=30` at each phase boundary (`canceled` class, sequential drain→dispatch). |
| **Process model** | supervisor keeps the phase timeline + active mask (dedicated seeded RNG); **one worker process per netns** (`--client-ns`, seeded `random.seed(base + ns_index)`, fresh TCP connection per request). |
| **Statistics** | **effect-size hierarchy** (no α claims at n=3): per episode, aligned vs mis-aligned (headline), `ba` vs mis-aligned, `ba` vs aligned (equivalence ≤ 1.5×) — Cliff's delta ≥ 0.6 + 3/3 direction consistency on `timeout_rate`, `failure_rate`, `node-minutes`, `time-to-recover`; MWU reported descriptively (n=3 min p=0.10); **no censored value enters MWU**; ≥3 defined values rule. |
| **Action cost** | replica-sync cost per added storage member — **new collector** `rq2v2_p2_01_sync_cost.py` → `sync_cost.csv` (initial-sync duration, bytes applied, storage CPU during sync). |
| **Relief** | secondary **relief-flatten** signal — `rq2v2_p2_02_relief_flatten.py` → `relief_flatten.csv` (target-tier `score_norm` stops rising / plateaus within `RELIEF_FLATTEN_WINDOW_S` after the action). |
| **Reporting** | `status`-aware metrics: offered vs completed vs timeout vs dropped/canceled; unified denominators; classifier asymmetry reported honestly (cb ≈ chance, db strong). |
| **New gates** | **per-run driver self-test** (enforced inside `run_traffic()` in `run_experiment.sh` — fail-fast on every run, stronger than a one-off pre-flight check), pre-flight concurrency stress check, stats gate (effect-size comparisons with missing-value exclusions recorded). |

**v2 success criteria (scoped to n=3 — effect-size, no α claims):**

- **SC1 Cross-over (headline):** per episode, aligned beats mis-aligned on
  episode p95 and `timeout_rate` with **3/3 direction consistency** and
  Cliff's delta ≥ 0.6.
- **SC2 Value-of-information:** `ba` beats mis-aligned (3/3 + Cliff's delta
  ≥ 0.6) and is within **1.5×** of the aligned median (equivalence).
- **SC3 Wrong-action cost:** mis-aligned shows no targeted-tier relief,
  exhausts its wrong-tier budget, and node-minutes/1000 ≥ aligned and ≥ `ba`.
- **SC4 Classification:** `ba` agreement > 50 % in db (reported; ≈ chance in
  cb, honest).
- **SC5 Mechanics:** budget binds at 4/tier/LAN; G2 induction pass; 0×
  NotPrimary; no controller restart; per-run driver gate.
- **SC6 Efficiency:** `ba` node-minutes/1000 ≤ mis-aligned.

**Run-label pattern (v2):** `rq2_<policy>_<episode>_<replicate>` with
`policy ∈ {cf, sf, ba}`, `episode ∈ {cb, db}`, `replicate ∈ {1..3}` (e.g. `rq2_ba_cb_1`). Block orders live in
[`counterbalance_order_v2.csv`](counterbalance_order_v2.csv) (seeds
2001–2003, distinct-order verified; the v1 `counterbalance_order.csv` is
never overwritten). Full v2 matrix: [`run_matrix.md`](run_matrix.md) §10;
v2 measurement contract: [`analysis_focus.md`](analysis_focus.md) §7.

---

## 1. Objective

Answer the thesis RQ2: **under compute-bound and data-access-bound demand, does
a bottleneck-aware controller — choosing the scale-out action (compute or
storage) from tier telemetry — recover service quality and use resources more
efficiently than the fixed compute-only or storage-only policies an operator
would otherwise configure?**

The single question the campaign isolates: **does telemetry determine *which
capacity action* is taken, and what does a wrong action cost?** Three policy
arms run the same workload under the same episode; only the action-selection
policy varies.

## 2. Motivation & Hypothesis

**Change under test.** The RQ2 required extension is implemented
(`rq2_preparation.md` §2–§3): pure per-tier evaluation returns a
`ScaleUpVerdict`; a `PolicyGate` selects the action (`fixed_compute_first`,
`fixed_storage_first`, `bottleneck_aware`) and enforces the per-tier action
budget (`ACTION_BUDGET_PER_TIER=4`); the decision log records evidence
(`compute_score_norm`/`storage_score_norm`), `*_fired`/`*_eligible`, selected
and rejected action, and budget usage on **every** evaluated window. This
experiment evaluates that machinery end-to-end.

**Hypothesis (value-of-information).** The comparison is crossed over the two
episode types:

| | **compute-bound episode** | **data-bound episode** |
|---|---|---|
| `fixed_compute_first` | ✓ adds compute → relief | ✗ no signal path to storage → **stays degraded** |
| `fixed_storage_first` | ✗ wastes budget on storage → no relief | ✓ adds storage → relief |
| `bottleneck_aware` | ✓ classifies → adds compute | ✓ classifies → adds storage |

- **H1 (right action):** in each episode, `bottleneck_aware` selects the
  pressured tier and achieves relief comparable to the correctly-aligned fixed
  arm.
- **H2 (wrong action cost):** the mis-aligned fixed arm (storage-first under
  compute-bound, compute-first under data-bound) does **not** relieve its
  targeted tier, wastes its action budget on the wrong tier, and leaves the
  service degraded longer — evidenced by time-to-recover, latency/failures, and
  node-minutes.
- **H3 (decision quality):** the classifier-vs-episode agreement (fraction of
  episode windows where `bottleneck_class` matches the induced episode) is
  meaningfully above chance; misclassifications (finite margin) are reported,
  not hidden.

**Independent variable (2 crossed factors):**

- policy arm: `SCALEUP_POLICY ∈ {fixed_compute_first, fixed_storage_first,
  bottleneck_aware}`;
- episode type: compute-bound | data-bound (single episode per run — D6).

**Held constant (per thesis §2 + `rq2_preparation.md` D8/D9):**
`TELEMETRY_SOURCE=event_preserving` (RQ1 reference), Tier 1 / persistent
reserve / cross-region **disabled**, per-tier caps **6/6** (Option B — strictly
above the action budget), action budget **4/tier/LAN** (the binding ceiling),
cooldowns, decision-signal statistic **median** (`LATENCY_SIGNAL_MODE=median`,
median-era rebase 2026-08-03) with the **composite storage signal** (G0-v4;
`mean_vs_median_signal_finding.md` §6) at **storage-CPU floor 35** (RQ2
Option-2 tuning 2026-08-03 — calibration evidence in `run_matrix.md` §6),
WSM routing policy, workload shape
(plateau + demand drop), topology, resource limits
(`STORAGE_CPUS=0.08 EDGE_CPUS=0.15 WAN_RTT_MS=185`), clients/devices/nodes,
backend admission = existing VIP (RQ3 out of scope).

## 3. Run Matrix (summary)

Full detail in [`run_matrix.md`](run_matrix.md).

| Stage | Runs | Cells |
|---|---|---|
| Pre-flight (tooling + calibration + gate) | 4 | `ba×cb`, `ba×db`, `cf×db`, `sf×cb` (V3 spec) |
| Main campaign | 18 (3 per cell) | 6 cells × 3 replicates |

Run-label pattern: `rq2_<policy>_<episode>_<suffix>` with
`policy ∈ {cf, sf, ba}`, `episode ∈ {cb, db}`, `suffix ∈ {preflight, 1..3}`.

> **⚠ Block-1 re-run (2026-08-03):** the first Block-1 set
> (`20260803_114003_rq2_cf_cb_1` … `20260803_141034_rq2_sf_db_1`) ran on the
> **pre-fix data path** (env snapshots verified to lack the three data-path
> knobs) and was **deleted**; Block 1 is re-run on the fixed path
> (`secondaryPreferred` + pool 6 + per-connection flows, on the shell **and**
> in the arm envs). Details in `run_matrix.md` and
> `read_preference_data_path_finding.md` §8–§10.

Env files (authoritative, in this folder's `env/`):
`rq2_compute_first.env` / `rq2_storage_first.env` / `rq2_bottleneck_aware.env` —
identical except the `SCALEUP_POLICY` line (verified by diff; the old
`source/scripts/testing/controller_env_overrides/rq2_*.env` copies are
**superseded** by these, matching RQ1's convention).

Episode phase files (calibrated in-place under `phases_override/`):
`phases_rq2_compute_bound.json` / `phases_rq2_data_bound.json`.

## 4. Run Configuration

Canonical per-run launch (all runs in the cloud VM at
`~/efficient-storage-in-edge-scenarios`; full per-run table in `run_matrix.md`):

```bash
ssh cloud-vm-rq2 "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n STORAGE_CPUS=0.08 EDGE_CPUS=0.15 WAN_RTT_MS=185 RANDOM_SEED=42 \
    EDGE_MONGO_READ_PREFERENCE=secondaryPreferred \
    EDGE_MONGO_MAX_POOL_SIZE=6 \
    VIP_DATA_PER_CONNECTION_FLOWS=1 \
    make -C source/scripts setup_network create_clients setup_test_data run_experiment \
    OSKEN_ENV_OVERRIDE_FILE=../../rq2_env/<ENV_FILE> \
    RUN_LABEL=<LABEL> \
    PHASES_CONFIG=testing/phases_override/phases_rq2_<episode>.json \
    CLIENTS=24 CONTENT_ITEMS=3000 USERS=100 \
    DATA_SEED=42 CURL_MAX_TIME=30 \
    SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1 \
    > /tmp/<LABEL>.log 2>&1 &"
```

- `OSKEN_ENV_OVERRIDE_FILE` is resolved relative to `source/scripts` (make
  cwd). The command above is the **VM form**: the per-arm env files are synced
  to `~/efficient-storage-in-edge-scenarios/rq2_env/`, so the path is
  `../../rq2_env/<ENV_FILE>`. The docs-hosted originals live at
  `docs/operation/testing/experiment/v2/rq2/env/` and are not on the VM.
- **VM sync (required):** the env files live under `docs/`, which is not on
  the VM — `env/*.env` are synced to `~/rq2_env/` (verified 2026-08-03; see
  `run_matrix.md` §4). The phase files live under `source/scripts/` and are
  repo-synced (no staging).
- **Shell env (data-path fix + Approach B, 2026-08-03):** every RQ2 arm MUST
  launch with `EDGE_MONGO_READ_PREFERENCE=secondaryPreferred`,
  `EDGE_MONGO_MAX_POOL_SIZE=6` and `VIP_DATA_PER_CONNECTION_FLOWS=1` on the
  shell (static `edge_server_n1/n2` read them at `setup_network`); the same
  vars are in each arm env file so dynamic spawns inherit them via the
  controller env. See `read_preference_data_path_finding.md` §5/§7. Since
  2026-08-03 `secondaryPreferred` is the code/shell **default** (the go-to),
  so an unset `EDGE_MONGO_READ_PREFERENCE` no longer reverts to `primary`;
  the explicit pre-fix opt-out (`EDGE_MONGO_READ_PREFERENCE=primary`) is used
  only by the G3 negative control.
- Images: **the `edge_server` image must be rebuilt on the VM** after the
  2026-08-03 data-path fix (read preference), because the edge code is baked,
  not volume-mounted: `sudo bash source/scripts/build_images.sh edge_server`
  (see `read_preference_data_path_finding.md`). Controller code is
  volume-mounted; the RQ1 aggregator image is already on the VM.
- Between runs: cleanup recreates the aggregator + controller containers →
  fresh `window_log.jsonl` / delivery / decision logs per run (checkpoint C1).

## 5. Measurements & Success Criteria

Primary evidence (per run, per LAN) — collected by `run_experiment.sh`
`collect_rq1_artifacts()` into the run folder (the RQ1 artifact set is
sufficient; RQ2 needs no new collectors):

- `decision_log_lan{1,2}.csv` — **the RQ2 universe**: one `scale_up` row per
  evaluated window in RQ2 arms, 20-column format (evidence, `*_fired`,
  `*_eligible`, `bottleneck_class`, `selected_action`, `rejected_action`,
  `*_budget_used`, `budget_cap`, `reason`)
- `window_log_lan{1,2}.jsonl` — universe (join via `window_id`)
- `phases_snapshot.json` — **episode ground-truth label** (post-hoc join, D5)
- `controller_env_snapshot.env` — provenance (arm, budget, margin, caps)
- existing: `client_requests.csv`, `per_node_stats.csv`, `resource_stats*.csv`,
  `controller_stats.csv`, `elasticity_events.csv`, `container_events.csv`,
  `controller_lan{1,2}.log`

Derived-metric definitions and the thesis-RQ2 mapping are in
[`analysis_focus.md`](analysis_focus.md) §2–§3.

Numbered success criteria (each objectively checkable by the analyst; per LAN
unless noted):

1. **Artifact + decision-log contract:** all artifacts above present and
   non-empty for both LANs; every RQ2-arm `scale_up` row has the full 20-column
   header and all evidence/`*_fired`/`*_eligible`/`*_budget_used` cells filled
   (never empty); exactly one `scale_up` row per evaluated window (dedup by
   `(window_id, action_type)` is a no-op on a clean run).
2. **Episode induction valid (bottleneck validation):**
   `rq2_bottleneck_validation.py` (raw `window_log.jsonl` signals, independent
   of the controller) confirms the induced episode dominated the intended
   tier using the **median** (robust to dynamic-server lifecycle/spawn
   transients, which can reach hundreds of ms and would dominate a mean):
   compute-bound runs show `median(avg_time_proc_ms) ≥
   median(avg_time_db_ms)` during the episode, data-bound runs the inverse.
   Evaluated on the `ba` pre-flight runs (the G2 gate). Fixed arms may carry
   policy-contaminated signals (their own wrong actions inject pressure) and
   are reported, not auto-failed. CPU / DB-latency elevation is a secondary
   diagnostic.
3. **Fixed-arm suppression:** `fixed_compute_first` never emits
   `selected_action="storage"`; `fixed_storage_first` never emits
   `selected_action="compute"`. The suppressed tier's window still advances
   and its fire is still logged (`*_fired=1`); `selected_action`/
   `rejected_action` record the outcome — `selected="none"` when the
   suppressed tier fires alone, `selected=<allowed>` / `rejected=<suppressed>`
   when both fire in the same window — so the counterfactual is analyzable.
4. **Bottleneck-aware selects the pressured tier:** in compute-bound episodes,
   `ba` selects compute; in data-bound episodes, `ba` selects storage. The
   per-window classifier-vs-episode agreement is reported (over episode
   windows in which **both** tiers were eligible — the tool's denominator);
   disagreement is flagged for inspection, not auto-failed (H3; the finite
   margin is pre-registered in D3).
5. **Budget binds (Option B):** each tier's spawns are capped at
   `ACTION_BUDGET_PER_TIER` (4) per LAN; caps (6/6) sit strictly above the
   budget so a budget-blocked fire is distinguishable from cap-ineligibility:
   after exhaustion, a fired tier yields no submission and
   `reason="budget_exhausted"` is logged; `*_budget_used`/`budget_cap` are
   consistent. Verified reachable in the pre-flight (T9.5) and reported per
   cell in the main campaign.
6. **Relief in the targeted tier:** for each selected action, the targeted
   tier's `score_norm` falls back under its `*_threshold` within the episode or
   recovery (time-to-recover measurable via `rq2_relief_analysis.py`); a
   mis-aligned fixed arm shows **no** targeted-tier relief (service stays
   degraded) — H2.
7. **Scale-down active + fire-keyed protection (T9.8):** ≥ 1 scale-down
   decision per LAN after the episode in every cell **where the allowed tier
   actually scaled up** (cf×cb, sf×db, ba×cb, ba×db) — compute 3-of-6 @ TAU
   25/40 reclaims in `recovery_gap`/`demand_drop`; storage 30s + 3-of-5
   reclaims in `demand_drop`. In mis-aligned cells (cf×db, sf×cb) the allowed
   tier may add zero nodes, so the **absence** of a scale-down is expected and
   reported, not failed. In all cells, no cooldown-gated `scale_down` row
   appears within `SCALEDOWN_*_COOLDOWN_S` of a window where that tier's
   `*_fired=1` (including policy-suppressed fires), verified from the `*_fired`
   columns.
8. **Cross-over service-quality contrast (the headline):** in compute-bound
   episodes, `cf` ≈ `ba` beat `sf` on p50/p95/p99, failure rate, and
   time-to-recover; in data-bound episodes, `sf` ≈ `ba` beat `cf` (which stays
   degraded). If the cross-over does not reproduce, the cell is flagged for
   re-inspection before conclusions.
9. **Efficiency / node-minutes:** compute+storage node-minutes per run
   (`rq2_node_minutes.py`, actual spawns only); the mis-aligned fixed arm shows
   higher resource use per unit of completed demand (wasted actions).
10. **RQ1 artifacts unchanged:** `window_log`/delivery-log behavior and the
    non-scale-up decision rows keep RQ1 semantics within the 20-column format;
    no controller restart mid-run (checkpoint C2).

## 6. Analysis Approach

Full detail in [`analysis_focus.md`](analysis_focus.md) §4–§6. Summary:

- **Contrast structure:** per episode type, the correctly-aligned fixed arm is
  the reference; `bottleneck_aware` is compared to it and to the
  mis-aligned fixed arm. Headline: **does selecting the action from telemetry
  match the right fixed arm and beat the wrong one** (recovery, efficiency).
- **Per-run analysis** (`rq2_bottleneck_validation.py`,
  `rq2_decision_analysis.py`, `rq2_relief_analysis.py`, `rq2_node_minutes.py`;
  canonical location `docs/research_questions/v2/rq2/` — referenced, not
  duplicated): run folder → per-run CSVs (bottleneck validation, decision
  table + counterbalance + classifier-vs-episode agreement, relief/time-to-
  recover, node-minutes).
- **Time-to-usable-capacity:** `source/scripts/testing/analysis/rq2/extract_spawn_metrics.py`
  with `--tiers compute,storage --anchor decision`.
- **Cross-cell graphs:** per-cell and per-replicate variance (see
  `analysis_focus.md` §5).

## Appendix

### A. Prerequisites (before any run)

- [x] Implementation deployed + validated (T9 static/unit checks; V3 pre-flight
      is this plan's own stage 1 — see `run_matrix.md` §7)
- [x] RQ2 arm env files created (`env/rq2_compute_first.env`,
      `env/rq2_storage_first.env`, `env/rq2_bottleneck_aware.env` — identical
      except `SCALEUP_POLICY`)
- [x] Episode phase files calibrated in-place
      (`phases_override/phases_rq2_compute_bound.json`,
      `phases_rq2_data_bound.json`)
- [x] Analysis tooling exists (`docs/research_questions/v2/rq2/rq2_*.py`,
      `source/scripts/testing/analysis/rq2/extract_spawn_metrics.py`)
- [x] `env/*.env` synced to the cloud VM (repo at `~/efficient-storage-in-edge-scenarios`) — verified 2026-08-03; all three carry the data-path knobs
- [x] Leftover dual-episode `phases_override/phases_rq2.json` **removed**
      (2026-08-02; violated D6 single-episode-per-run — superseded by the two
      single-episode files)

### B. Checkpoints

- **C1 (per run):** fresh aggregator/controller state — `window_log` `window_seq`
  starts near 1; decision log contains only this run's rows.
- **C2 (per run):** no controller restart mid-run (restart invalidates the run).
- **C3 (per run):** artifacts copied before external cleanup.
- **C4 (campaign):** run folders follow `<timestamp>_rq2_<policy>_<episode>_<suffix>`;
  replicate aggregation includes only numeric suffixes; pre-flight runs are
  excluded from the replicate scatter.
- **C5 (episode label):** the episode label comes from `phases_snapshot.json`
  (post-hoc join), never from an injected env (D5).

### C. Validity threats

- **Controller restart mid-run** re-pulls and re-delivers the window log →
  duplicate decisions; run invalid (thesis §8). Checked by C2.
- **Budget/cap interplay (Option B):** caps 6/6 sit strictly above the 4/tier
  budget, so a budget-blocked fire (tier still under cap) is logged as
  `reason="budget_exhausted"` and is distinguishable from cap-ineligibility.
  Reported per LAN (budget is per LAN, D4).
- **Classifier proxy:** the D3 `score_norm`-based classifier is a documented
  proxy; its correctness is validated empirically by the induced-episode
  check (criterion 2), not assumed.
- **Fixed-arm budget exhaustion:** a mis-aligned fixed arm may exhaust its
  budget on the wrong tier and stop acting — an expected treatment effect, not
  a harness defect (documented; visible via `*_budget_used`).
- **Wall-clock / clocks:** decision timing relies on same-host clocks (true in
  this deployment).
- **Node-minutes approximation:** node-minutes uses decision-row timing (D4
  caveat); reported as an approximation.

### D. References

- Implementation plan: `docs/research_questions/v2/rq2/rq2_preparation.md`
- Thesis RQ2: `tese/Notes/thesis_overview.md` §6; `tese/research_questions/rq2.md`
- Control group: `docs/operation/testing/experiment/v2/control_group.md`
- Code: `source/sdn_controller/{policy_gate,scaling_policy,scaling_config,main_n1,main_n2}.py`
- Analyzers: `docs/research_questions/v2/rq2/rq2_{bottleneck_validation,decision_analysis,relief_analysis,node_minutes}.py`
- Spawn metrics: `source/scripts/testing/analysis/rq2/extract_spawn_metrics.py`

## Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-08-04 | Campaign complete: 18/18 main runs validated on the fixed data path (3 policies × 2 episodes × 3 replicates); per-run summaries, `campaign_dataset.csv`, and 15 cross-cell graphs produced; `results.md` timeline + `post_run_analysis.md` written | Final RQ2 evidence record — see `results.md` Judgment and `post_run_analysis.md` §3 |
| 2026-08-04 | Local run folders removed; VM holds the 25-folder archive; graphs + evaluation analysis retained in this folder | Keep the workspace lean; the evaluation-level record is the retained deliverable |
| 2026-08-04 | RQ2 v2 rework documented (Phase 4): open-loop driver, n=5, 8 cells incl. `ba-strict`, `CURL_MAX_TIME=300`/`INFLIGHT_WINDOW=1024`/`DRAIN_S=30`, MWU + Cliff's delta, sync-cost + relief-flatten, `status`-aware reporting; the 18-run campaign is re-framed as the v1/supporting record | Authoritative spec `rq2_v2_rework_plan.md`; v2 matrix `run_matrix.md` §10; orders `counterbalance_order_v2.csv` |
| 2026-08-04 | **Scope decision:** RQ2 v2 campaign reduced to **18 runs** (6 cells × 3 replicates, 3 blocks, seeds 2001–2003); statistics are **effect-size at n=3** (no α claims; MWU descriptive; SC1–SC6); `ba-strict` implemented but **not run** (follow-up option); matrix, docs, and stats tool updated to match | User time-budget constraint; conclusions scoped to what n=3 supports |
