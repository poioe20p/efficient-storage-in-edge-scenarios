# RQ2 Bottleneck-Aware Scaling — Run Matrix

Part of [`experiment_plan.md`](experiment_plan.md). Detailed per-run
configuration for the RQ2 campaign.

> **✅ Campaign complete (2026-08-04).** All 18 main runs (3 policies × 2
> episodes × 3 replicates) validated on the fixed data path: exit 0, correct
> env knobs, 0× `NotPrimaryOrSecondary`, no controller restart. Evaluation
> record: [`results.md`](results.md), [`post_run_analysis.md`](post_run_analysis.md),
> `analysis/campaign_dataset.csv`, `analysis/run_summaries/`, `graphs/comparison/`.
> Raw run folders are archived on `cloud-vm` only.

> **RQ2 v2 (final evidence):** [`experiment_plan.md`](experiment_plan.md) "RQ2 v2 (final
> evidence)" + **§10 below** define the 18-run v2 matrix (6 cells × 3 replicates,
> open-loop driver, effect-size statistics at n=3). The 18-run campaign in
> §1–§9 is the **v1/supporting record**. v2 block orders live in
> `counterbalance_order_v2.csv` (seeds 2001–2003); the v1
> `counterbalance_order.csv` is never overwritten.

> **⚠ Block-1 re-run (2026-08-03) — pre-fix data path superseded.** The first
> Block-1 set (`20260803_114003_rq2_cf_cb_1` … `20260803_141034_rq2_sf_db_1`,
> 11:40–14:10) ran on the **pre-fix data path**: the three fix knobs were
> absent from every `controller_env_snapshot.env` (verified), so static edges
> were `primary` / pool 1 / per-client flows and storage secondaries never
> served reads (`NotPrimaryOrSecondary`/13436) — its data-bound cells
> (`cf_db`, `sf_db`, `ba_db`) were confounded (storage scale-out produced
> ~zero usable read capacity). Those 6 runs were **deleted** (local + VM) and
> Block 1 is **re-run on the fixed path** (all three knobs SET on the shell
> **and** in the arm envs). See `read_preference_data_path_finding.md` §8–§10.

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

- **The three data-path vars are REQUIRED on the shell** (static
  `edge_server_n1/n2` read them at `setup_network`): without them the static
  edges silently revert to the pre-fix path — this is exactly what invalidated
  the first Block-1 set (see the note at the top of this file). They are also
  set in each arm env file (verified) so **dynamic** spawns inherit them via
  the controller env.
- `OSKEN_ENV_OVERRIDE_FILE` is resolved relative to `source/scripts` (make
  cwd). The command above is the **VM form**: the per-arm env files are synced
  to `~/efficient-storage-in-edge-scenarios/rq2_env/`, so the path is
  `../../rq2_env/<ENV_FILE>` (from `source/scripts` → repo root → `rq2_env/`).
  The docs-hosted originals live at
  `docs/operation/testing/experiment/v2/rq2/env/` and are **not** on the VM.
- `PHASES_CONFIG=testing/phases_override/phases_rq2_<episode>.json` selects the
  single-episode workload (repo-synced with `source/`, no staging).
- **VM sync (required — the env files live in `docs/`, which is not on the
  VM):** `env/rq2_compute_first.env`, `env/rq2_storage_first.env`,
  `env/rq2_bottleneck_aware.env` are synced to `~/rq2_env/` (verified
  2026-08-03 18:47, all three carry the data-path knobs). If an env file
  changes locally, re-scp it to the VM before the next run.

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

**Shell env (data-path fix + Approach B, 2026-08-03):** every RQ2 arm MUST
launch with all THREE vars on the shell (`sudo -n ... make setup_network ...`)
so the **static** `edge_server_n1/n2` containers enable the secondary-serving
read path AND the pooled fan-out:

- `EDGE_MONGO_READ_PREFERENCE=secondaryPreferred` (secondaries serve reads)
- `EDGE_MONGO_MAX_POOL_SIZE=6` (pooled edge client → fan-out per connection)
- `VIP_DATA_PER_CONNECTION_FLOWS=1` (controller per-connection flow matching;
  also in each arm env file)

The same vars are set in each arm env file so **dynamic** spawns inherit them
via the controller env. Without the shell vars the static edges revert to
`primary` + pool=1 and the fix silently returns (see
`read_preference_data_path_finding.md` §5). **This is what happened to the
first Block-1 set** (its env snapshots lack all three knobs); the re-run
launches carry them explicitly on the shell. Hardware sim vars
(`STORAGE_CPUS`, `EDGE_CPUS`, `WAN_RTT_MS`) and `RANDOM_SEED` are on the shell,
identical across all runs.

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
`SCALEUP_POLICY` line differs (verified by diff). All three set
**`LATENCY_SIGNAL_MODE=median`** and the **composite storage signal** (G0-v4;
median-era rebase 2026-08-03 — see the §6 calibration note and
`mean_vs_median_signal_finding.md`). The old
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

> **Median-era recalibration (2026-08-03, `mean_vs_median_signal_finding.md`):**
> the controller's decision signals are rebased from **mean** to **median**
> latency (`LATENCY_SIGNAL_MODE=median`; default stays `mean` → RQ1 untouched)
> and the storage scale-up signal becomes the validated **COMPOSITE**
> (control-group G0-v4): `SCALEUP_W_STORAGE_CPU=0.60`/`SCALEUP_W_T_DB=0.40`,
> storage-CPU floor 10/span 30, DB-latency floor 10/span 50 (crossing
> 27.5 ms), τ_base 0.35; storage scale-down is CPU-aware
> (`STORAGE_SCALE_DOWN_CPU_AWARE=1`, `TAU_STORAGE_CPU_DOWN=22`) with
> `TAU_DB_DOWN_MS` re-anchored 150 → 8. **Why:** the mean-based storage signal
> false-fired in the DB-free compute-bound episode — in low-request
> transition/tail windows a single slow request inflated the mean, so the
> Block-1 `ba` cells exhausted the storage budget in a DB-free episode
> (dual-firing). The controller's action-selection signal must agree with the
> plan's G2 median validator. **Implication:** the 6 Block-1 runs (2026-08-02)
> used the mean-era signal and are **superseded**; Block 1 is re-run on the
> median/composite config.

> **Option-2 storage-CPU floor tuning + calibration evidence (2026-08-03, `mean_vs_median_signal_finding.md` §6):**
> the composite storage signal (CPU floor 10) was validated on the control
> plateau but **still false-fired storage in RQ2's DB-free compute-bound
> episode** — in low-request transition/tail windows (4–9 reqs) the storage-CPU
> component (W 0.60) fired on lifecycle/spawn CPU transients (cpu_s 29–31 %,
> median T_db 9–13 ms), and those spawns then triggered replica-sync CPU spikes
> (54–85 %) inside the episode (a feedback loop). **Fix (Option 2, env-only):**
> raise `SCALEUP_STORAGE_CPU_FLOOR` 10 → **35** in the 3 RQ2 envs (comment
> added). Data-bound is unaffected — its storage signal is latency-dominated
> (median T_db 500+ ms → the latency component alone crosses τ 0.35), verified
> on the floor-10 data-bound calibration (storage 4/LAN, classifier 100 %).
>
> | Calibration run (floor) | episode | G2 | storage fires | storage budget used | in-episode storage CPU | classifier-vs-episode |
> |---|---|---|---|---|---|---|
> | `20260803_093421_rq2_ba_cb_cal` (10) | cb | PASS | 4 (lan1 3 / lan2 1) | lan1 3 / lan2 1 | 10–13 % | 47.1 % |
> | `20260803_100953_rq2_ba_db_cal` (10) | db | PASS | 8 (4/LAN) | 4/4 | 33–38 % | 100 % |
> | `20260803_104134_rq2_ba_cb_cal2` (35) | cb | PASS | **1** (lan1 0 / lan2 1) | lan1 0 / lan2 1 | **0.0 %** | 54.5 % |
> | `20260803_111022_rq2_ba_db_cal2` (35) | db | PASS | 8 (4/LAN) | 4/4 | 31–45 % | 71.4 % |
>
> **Result (floor 35):** compute-bound storage fires drop 4 → **1** (lan1 fully
> clean; the single lan2 fire is the accepted latency-driven tail residual —
> w=lan2:107, 4 reqs, median T_db 410 ms); **the in-episode feedback loop is
> broken** (episode storage CPU 0.00 % — no storage spawn → no replica-sync CPU
> spikes); compute 4/LAN, G2 PASS and T9.8 OK in every calibration run.
> Data-bound storage firing is fully preserved (4/LAN, budget exhausted). The
> residual latency-driven tail fires are accepted and documented — fewer nodes
> = leaner edge deployment, consistent with the thesis's edge-resource framing.
> **Decision: Option 2 accepted** (env-only, control group untouched); Option 3
> (DB-activity gate, code change) rejected — it yields the same residual for
> higher cost. Block 1 re-run (2026-08-03) uses the floor-35 envs.

> **Open-loop G2 recalibration evidence (2026-08-04, v2 open-loop driver):**
> the v2 open-loop driver preserves offered load (the v1 sync driver
> collapsed it), so the v1 episode rates (8.0/5.0) over-saturate. The rates
> were re-tuned in place and each candidate was validated on a `ba` G2
> calibration run before the campaign. **Calibration runs and verdicts:**
>
> | Run | episode | rate | driver | G2 (proc/db ms) | ep p50 | timeout% | canceled% | dropped | recovery | scale-up | verdict |
> |---|---|---|---|---|---|---|---|---|---|---|---|
> | `145827_rq2_g2_ba_cb_cal` | cb | 8.0 | open-loop | PASS | 84.8 s | 19.2 % | 18 % | 12.7 % | no | compute 4/LAN | **REJECT** — over-saturated (rate too hot) |
> | `153023_rq2_g2_ba_cb_cal2` | cb | 3.0 | open-loop | PASS (1.4/0) | 3.1 s | 14.9 % | 1.2 % | 0 | yes (→0 by ~360 s) | compute 4/LAN | **ACCEPT** |
> | `163351_rq2_g2_ba_db_cal` | db | 3.0 | **sync** | PASS (5/25) | 24 ms | 0 | 0 | 0 | n/a | storage 4/LAN | **INVALID** — launch omitted the open-loop env (13-col CSV, no `status`); sync driver load-collapse |
> | `181521_rq2_g2_ba_db_cal2` | db | 3.0 | open-loop | PASS (22/273) | 67 s | 21.4 % | 24.5 % | 0 | no (queue never clears) | storage 4/LAN | **REJECT** — over-saturated |
> | `190146_rq2_g2_ba_db_cal3` | db | 2.0 | open-loop | PASS (17/245) | 32 s | 15.6 % | 10.1 % | 0 | **yes** (timeouts 2648→0 by ep end) | storage 4/LAN | **PROVISIONAL** — mechanism works; retune to 1.5 for a shallower ramp |
> | `193959_rq2_g2_ba_db_cal4` | db | **1.5** | open-loop | PASS (12–24/177–230) | **2.0 s** | **10.1 %** (ramp-only) | **3.1 %** | 0 | **clean** (→0 by ~5 min; 0/9/2 in last 3 buckets) | storage 4/LAN | **ACCEPT** |
>
> **What worked at rate 1.5 (db, `193959_rq2_g2_ba_db_cal4`):**
> - Episode p50 **2.0 s**, p95 16 s, p99 28 s — real DB pressure (median `db_ms`
>   177–230 ≫ `proc_ms` 12–24), not collapse.
> - `timeout_rate` 10.1 % concentrated in the ramp (peak 1108 in the first
>   180 s), → ~0 in steady state after storage scale-up; `canceled` 3.1 %;
>   `dropped` 0.
> - Storage scale-up fires and the budget exhausts (4/LAN); G2 PASS both LANs;
>   the run completed exit=0 (the RQ3 gate skip fix).
>
> **Decision (2026-08-04, final):** the db episode is **ACCEPTED at rate 1.5**
> (window/rate = 1024/1.5 = 683 s > 300 s ✅). The cb episode is accepted at
> rate 3.0 (`153023_rq2_g2_ba_cb_cal2`). Both episode files are calibrated
> in place and synced to the VM. `ba` dual-fires in db (compute budget also
> exhausts, compute score pinned at 0.60) — documented, matches the v1
> baseline, reported honestly. **Pre-flight gate is green; the 18-run
> campaign may start.**

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

---

## 10. RQ2 v2 matrix (final evidence — 36 runs)

This section **supersedes §1–§9 as the primary RQ2 run configuration**; the
36-run v2 campaign is the final thesis evidence (n=6, 2026-08-04 scope
upgrade). The 18-run v1 campaign remains the supporting record. Spec:
`rq2_v2_rework_plan.md` (Phases 1–3 implemented; Phase 5 in execution).

### 10.1 Structure

| Stage | Runs | Purpose |
|---|---|---|
| **Pre-flight (Phase-5 gates, fail-fast)** | 3 + smoke | (a) `make driver_selftest` on the VM (host + inside a netns); (b) **concurrency stress check** — max in-flight at the intended rate and the 300 s cap must not exhaust container/conntrack connection limits (tune limits if it does; else lower window/rate and re-record the budget); (c) 2 G2 calibration runs (`ba_cb`, `ba_db`) under open-loop to re-tune episode rates (target ≤ 3 req/s/client so `window/rate > 300 s`); (d) legacy `sync`-mode
regression smoke. **Blocks do not start until all pass.** |
| **Main** | 36 | 6 cells × 6 replicates, 6 counterbalanced blocks |

**Cells (6):** `cf_cb, cf_db, sf_cb, sf_db, ba_cb, ba_db` (the
`ba-strict` arm is implemented but **not run** in this campaign — kept as a
documented option for a follow-up capacity-vs-classification test).

**Run-label pattern (v2):** `rq2_<policy>_<episode>_<replicate>` with
`policy ∈ {cf, sf, ba}`, `episode ∈ {cb, db}`,
`replicate = block number ∈ {1..6}` (e.g. `rq2_ba_cb_1`). Run folder:
`<timestamp>_rq2_<policy>_<episode>_<replicate>`.

### 10.2 Counterbalancing (6 blocks, seeds 2001–2006)

The 36 runs execute in **6 blocks of 6 cells**, each block a different
randomized order. Each block order is generated deterministically with
`python -c "import random; random.seed(<BLOCK_SEED>); print(random.sample([...6 cells...], 6))"`
with `BLOCK_SEED = 2001..2006` for blocks 1–6. **Distinct-order verification
is kept** — the six sampled orders must all be distinct (re-sample a block's
seed on collision until distinct). The verified final orders are recorded in
**`counterbalance_order_v2.csv`** in this experiment folder (a **new** file —
the v1 `counterbalance_order.csv` is **never overwritten**). `RANDOM_SEED=42`
remains the traffic seed **base**; in open-loop mode each per-netns worker
seeds `random.seed(base + ns_index)` (per-client request-type sequences stay
distinct). The analyst audits order from run-folder names;
`rq2_decision_analysis.py` reports each run's cell but does **not** check
block order — that is the runner's/analyst's responsibility.

### 10.3 Per-run launch (v2 additions)

The v1 launch (§4) plus the following **per-run additions** (all on the shell
alongside the existing data-path knobs; `run_experiment.sh` passes them
through to the supervisor/workers):

- `TRAFFIC_DRIVER_MODE=open_loop` — supervisor + **one worker per netns**
  (`--client-ns`, `--vip`, `--schedule-file`, `--phase-state-file`);
  per-worker seed `random.seed(base + ns_index)`; fresh TCP connection per
  request (`TCPConnector(force_close=True)`).
- `CURL_MAX_TIME=300` — replaces the v1 `CURL_MAX_TIME=30`; `timeout` is a
  distinct `status` class, never merged into `failure`.
- `INFLIGHT_WINDOW=1024` — per-client in-flight cap; with episode rate ≤ 3
  req/s/client, `window/rate > 300 s` so **`dropped` is unreachable in
  production by design** (offered load fully preserved).
- `DRAIN_S=30` — per-phase-boundary drain (< the 60 s shortest phase);
  in-flight awaited up to `DRAIN_S`, then `canceled` (counted in offered,
  excluded from latency/failure); sequential drain→dispatch.
- Env file per cell (`OSKEN_ENV_OVERRIDE_FILE`): the 3 v1 arm envs **plus**
  `rq2_bottleneck_aware_strict.env` for the two `ba-strict` cells.
- **Sync-cost collection:** `rq2v2_p2_01_sync_cost.py` → `sync_cost.csv`
  per run (initial-sync duration, bytes applied, storage CPU during sync).
- **Per-run driver self-test gate:** `run_experiment.sh run_traffic()` runs
  `openloop_p1_01_driver_selftest.py` whenever `TRAFFIC_DRIVER_MODE=open_loop`
  and **fails fast** (exit 1) if it does not pass. Implemented **per run**,
  not only once pre-flight — a stronger gate than the plan's one-off
  pre-flight check; every run's env snapshot must show the open-loop knobs.

Env mapping (all four files synced to `~/rq2_env/`):

| Cell(s) | `<ENV_FILE>` |
|---|---|
| `cf_cb`, `cf_db` | `rq2_compute_first.env` |
| `sf_cb`, `sf_db` | `rq2_storage_first.env` |
| `ba_cb`, `ba_db` | `rq2_bottleneck_aware.env` |

### 10.4 Between-run procedure and wall-clock

Same as §8 (fresh aggregator/controller per run; checkpoints C1–C3; no
controller restart mid-run). The per-run self-test adds only seconds per run.
**VM:** all v2 runs execute on **`cloud-vm-rq2`** (`ssh cloud-vm-rq2`, repo at
`~/efficient-storage-in-edge-scenarios`); raw v2 run folders are archived on
that VM (the v1 runs remain archived on `cloud-vm`).
Estimate: 18 runs × ~30–35 min (incl. 4 drains of 30 s + setup) ≈
**9–11 h** ≈ **1 VM-day of blocks**, plus any calibration re-runs.
