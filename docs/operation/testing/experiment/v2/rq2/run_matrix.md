# RQ2 Bottleneck-Aware Scaling — Run Matrix

Part of [`experiment_plan.md`](experiment_plan.md). Detailed per-run
configuration for the RQ2 campaign.

## 1. Campaign structure

| Stage | Runs | Purpose |
|---|---|---|
| **Pre-flight** | 4 | One per representative cell (V3 spec); gates G1–G4 (§7) |
| **Main** | 18 | Full factorial 3 policies × 2 episodes × 3 replicates |

Run-label pattern: `rq2_<policy>_<episode>_<suffix>` with
`policy ∈ {cf, sf, ba}` (`cf`=fixed_compute_first, `sf`=fixed_storage_first,
`ba`=bottleneck_aware), `episode ∈ {cb, db}` (`cb`=compute-bound,
`db`=data-bound), `suffix ∈ {preflight, 1, 2, 3}`. Run folder becomes
`<timestamp>_rq2_<policy>_<episode>_<suffix>`.

## 2. Pre-flight matrix (4 runs)

| # | Label | Policy | Episode file | Why |
|---|---|---|---|---|
| P1 | `rq2_ba_cb_preflight` | `bottleneck_aware` | `phases_rq2_compute_bound.json` | classifier picks compute (T9.4) |
| P2 | `rq2_ba_db_preflight` | `bottleneck_aware` | `phases_rq2_data_bound.json` | classifier picks storage (T9.4) |
| P3 | `rq2_cf_db_preflight` | `fixed_compute_first` | `phases_rq2_data_bound.json` | suppressed-storage fire + fire-keyed scale-down protection (T9.8) |
| P4 | `rq2_sf_cb_preflight` | `fixed_storage_first` | `phases_rq2_compute_bound.json` | suppressed-compute fire + storage-submits (T9.3) |

## 3. Main matrix (18 runs)

| # | Label | Policy | Episode |
|---|---|---|---|
| 1–3 | `rq2_cf_cb_1..3` | `fixed_compute_first` | compute-bound |
| 4–6 | `rq2_cf_db_1..3` | `fixed_compute_first` | data-bound |
| 7–9 | `rq2_sf_cb_1..3` | `fixed_storage_first` | compute-bound |
| 10–12 | `rq2_sf_db_1..3` | `fixed_storage_first` | data-bound |
| 13–15 | `rq2_ba_cb_1..3` | `bottleneck_aware` | compute-bound |
| 16–18 | `rq2_ba_db_1..3` | `bottleneck_aware` | data-bound |

**Counterbalancing (thesis §8):** the 18 runs are executed in 3 blocks of 6
cells each, the 6 cells in each block in a different randomized order. The
runner generates each block order deterministically (e.g.
`python -c "import random; random.seed(<BLOCK_SEED>); print(random.sample(['cf_cb','cf_db','sf_cb','sf_db','ba_cb','ba_db'], 6))"`
with `BLOCK_SEED` = `1001`, `1002`, `1003` for blocks 1–3), **verifies the
three sampled orders are distinct** (re-sample a block's seed until distinct
if a collision occurs), records the final three orders as
`counterbalance_order.csv` in this experiment folder, and launches replicates
in that order. `RANDOM_SEED=42` is the **traffic** seed, not the ordering seed.
The analyst audits the order from the run-folder names;
`rq2_decision_analysis.py` reports each run's cell but does **not** check
block order — that is the runner's/analyst's responsibility.

## 4. Launch command

All runs in the cloud VM at `~/efficient-storage-in-edge-scenarios`:

```bash
ssh cloud-vm "cd ~/efficient-storage-in-edge-scenarios && \
  nohup sudo -n STORAGE_CPUS=0.08 EDGE_CPUS=0.15 WAN_RTT_MS=185 RANDOM_SEED=42 \
    make -C source/scripts setup_network create_clients setup_test_data run_experiment \
    OSKEN_ENV_OVERRIDE_FILE=../../docs/operation/testing/experiment/v2/rq2/env/<ENV_FILE> \
    RUN_LABEL=<LABEL> \
    PHASES_CONFIG=testing/phases_override/phases_rq2_<episode>.json \
    CLIENTS=24 CONTENT_ITEMS=3000 USERS=100 \
    DATA_SEED=42 CURL_MAX_TIME=30 \
    SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1 \
    > /tmp/<LABEL>.log 2>&1 &"
```

- `OSKEN_ENV_OVERRIDE_FILE` is resolved relative to `source/scripts` (make
  cwd); the `../../docs/...` path points at the per-arm env files in this
  `v2/rq2/env/` folder.
- `PHASES_CONFIG=testing/phases_override/phases_rq2_<episode>.json` selects the
  single-episode workload (repo-synced with `source/`, no staging).
- **VM sync (required — the env files live in `docs/`, which is not on the
  VM):** copy `env/rq2_compute_first.env`, `env/rq2_storage_first.env`,
  `env/rq2_bottleneck_aware.env` to the VM before the first run (scp to a
  known path, e.g. `~/rq2_env/`, and **rewrite the `../../docs/...` path in
  the command above to that VM-local path — the command as printed only
  resolves on the Windows host, not on the VM**).

| Run | `<ENV_FILE>` | `<LABEL>` | episode file |
|---|---|---|---|
| P1 | `rq2_bottleneck_aware.env` | `rq2_ba_cb_preflight` | `phases_rq2_compute_bound.json` |
| P2 | `rq2_bottleneck_aware.env` | `rq2_ba_db_preflight` | `phases_rq2_data_bound.json` |
| P3 | `rq2_compute_first.env` | `rq2_cf_db_preflight` | `phases_rq2_data_bound.json` |
| P4 | `rq2_storage_first.env` | `rq2_sf_cb_preflight` | `phases_rq2_compute_bound.json` |
| 1–3 | `rq2_compute_first.env` | `rq2_cf_cb_1..3` | `phases_rq2_compute_bound.json` |
| 4–6 | `rq2_compute_first.env` | `rq2_cf_db_1..3` | `phases_rq2_data_bound.json` |
| 7–9 | `rq2_storage_first.env` | `rq2_sf_cb_1..3` | `phases_rq2_compute_bound.json` |
| 10–12 | `rq2_storage_first.env` | `rq2_sf_db_1..3` | `phases_rq2_data_bound.json` |
| 13–15 | `rq2_bottleneck_aware.env` | `rq2_ba_cb_1..3` | `phases_rq2_compute_bound.json` |
| 16–18 | `rq2_bottleneck_aware.env` | `rq2_ba_db_1..3` | `phases_rq2_data_bound.json` |

**No extra shell env** is needed for any RQ2 arm (unlike RQ1 Arm C's
`POLL_INTERVAL_S`). Hardware sim vars (`STORAGE_CPUS`, `EDGE_CPUS`,
`WAN_RTT_MS`) and `RANDOM_SEED` are on the shell, identical across all runs.

**Calibrated-value carryover:** any value changed during G2 calibration
(episode phase mix/duration/rate, `CLIENTS`, `CONTENT_ITEMS`) MUST be carried
into the main 18 runs identically and recorded in the run log; if a phase
file is edited locally during calibration, **re-sync it to the VM** before the
main runs (the VM runs the file it has, not the repo copy). Otherwise the
main runs silently fall back to un-calibrated values, invalidating criteria
2/6/8.

## 5. Per-arm env files

This experiment folder's `env/` subfolder
(`docs/operation/testing/experiment/v2/rq2/env/`):

| File | `SCALEUP_POLICY` | Regime |
|---|---|---|
| `rq2_compute_first.env` | `fixed_compute_first` | scale compute only |
| `rq2_storage_first.env` | `fixed_storage_first` | scale storage only |
| `rq2_bottleneck_aware.env` | `bottleneck_aware` | classify → select the pressured tier |

The shared block (capacity 6/6 — strictly above the 4/tier budget so the
budget binds observably, scale-down 3-of-6 @ TAU 25/40 + storage 30s + 3-of-5,
disable flags, budget 4, margin 0.05, `CONTROL_TICK_S`, log paths) is
intentionally **identical** across the three files — **rebased from
`current_state_integrated.env`** (control-group retune 2026-08-01) plus the
thesis-§2 disable flags and the RQ2/Q6 scale-down calibration; only the
`SCALEUP_POLICY` line differs (verified by diff). The old
`source/scripts/testing/controller_env_overrides/rq2_{compute_first,storage_first,bottleneck_aware}.env`
files are **superseded** by these (RQ1 convention: the experiment folder's
`env/` is authoritative); they are kept for provenance only and must not be
used for runs.

## 6. Phase files (episode calibration)

Each is a **single-episode** run (D6): `baseline` → `<episode>` → `recovery_gap`
→ `demand_drop`, shaped like the control plateau (1200 s total). Starting
values below are the calibration baseline; **G2 (pre-flight) validates that
each episode actually induces its intended bottleneck** via
`rq2_bottleneck_validation.py` and the mix/duration/rate are adjusted in-place
if not.

| Phase | Dur | rate/cl | client frac | compute-bound mix | data-bound mix |
|---|---|---|---|---|---|
| `baseline` | 60 s | 1.0 | 0.1 | lookup 0.6 / feed 0.25 / pressure 0.15 | same |
| `compute_bound_episode` / `data_bound_episode` | 600 s | **8.0** / 5.0 | 1.0 | **pressure 1.0 (pure-compute, G2 recalibration 2026-08-02)** | **lookup 0.40 / update 0.30 / aggregate 0.25 / feed 0.05** |
| `recovery_gap` | 120 s | 0.5 | 0.05 | baseline mix | same |
| `demand_drop` | 420 s | 1.0 | 0.1 | baseline mix | same |

> **G2 recalibration (2026-08-02):** the initial compute-bound mix (pressure 0.50 /
> feed 0.35 / lookup 0.15 @ rate 5.0) drove ~50% DB-touching requests (`feed_ranking`
> + `content_lookup`), so the storage tier stayed hot and storage-scale-up replica-sync
> transients inflated the episode-mean `db_ms` (739–825 ms > `proc_ms`), failing the
> validator. Recalibrated to `service_pressure 0.85 / feed_ranking 0.15` @ rate 6.0 —
> DB-light; steady-state was clean (db_ms ≈ 0, cpu 40–90%) but residual `feed_ranking`
> DB reads + storage add/remove sync outliers (db_ms up to ~6500 ms) still corrupted
> transients. Final calibration: **`service_pressure 1.0`** — pure compute, zero
> MongoDB traffic, so storage never fires and the compute tier is the clean
> dominant bottleneck. The validator uses the **median** (robust to dynamic-server
> lifecycle/spawn transients). Rate raised **6.0 → 8.0** (2026-08-02) for a
> stronger compute bottleneck (CPU ~45–55% at 6.0; target higher saturation for
> clearer relief contrast). `phases_rq2_compute_bound.json` edited in place;
> data-bound episode unchanged (it passes).

The 600 s episode (like the control plateau) is long enough to exhaust the
4/tier budget even under the 120 s storage cooldown and to measure
time-to-recover in-window. Compute-bound endpoints: `service_pressure`,
`feed_ranking` (T_proc/CPU). Data-bound endpoints: `content_lookup`,
`content_update`, `content_aggregate` (T_db/storage CPU).

## 7. Pre-flight gate (must pass before the main 18 runs)

After the 4 pre-flight runs are analyzed:

- **G1 — tooling + decision-log contract:** all artifacts present for both
  LANs; the four analyzers run clean on the pre-flight folders; the decision
  log is the 20-column RQ2 format with the full header; the controller startup
  log shows `SCALEUP_POLICY`, `ACTION_BUDGET_PER_TIER`, `BOTTLENECK_CLASSIFY_MARGIN`
  (provenance). Criterion 1 holds.
- **G2 — episode induction (calibration):** `rq2_bottleneck_validation.py`
  confirms the intended bottleneck for both episode files **in the `ba`
  pre-flight runs** (compute-bound → `avg_time_proc_ms ≥ avg_time_db_ms`;
  data-bound → inverse). If not, adjust the episode mix/duration/rate (or
  scale), re-run the failing pre-flight, and carry the calibrated values into
  the main matrix (§4 carryover).
- **G3 — classifier + budget + suppression (T9.3/9.4/9.5/9.8):** `ba` runs show
  classifier agreement (criterion 4) and budget exhaustion reachable
  (criterion 5); `cf`/`sf` pre-flights show suppression (criterion 3) and the
  fire-keyed scale-down protection (criterion 7) via the `*_fired` columns.
- **G4 — flat-window inertness (T9.9):** nothing fires/commits on baseline
  windows; RQ1 artifacts unchanged (criterion 10); no controller restart
  mid-run (C2).

**Gate passes → the main 18-run campaign may start.**

## 8. Between-run procedure

1. Confirm run artifacts collected (C3).
2. Cleanup so the **aggregator and controller containers are recreated** —
   required for a fresh `window_log.jsonl` (seq restarts), delivery log and
   decision log. Reuse the repo's cleanup (e.g. `cleanup.sh` / the cleanup
   make target) before the next `setup_network`.
3. Verify checkpoint C1 (fresh state) before launching the next run.
4. No controller restart mid-run (C2). No VM reboot between replicates unless
   state contamination is observed.

## 9. Estimated wall-clock

~25–30 min per run (1200 s traffic + setup/teardown + artifact copy) →
pre-flight 4 runs ≈ 2 h; main 18 runs ≈ 9 h; total **≈ 11 h**, plus any
calibration re-runs.
