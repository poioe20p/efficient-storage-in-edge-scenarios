# Results — RQ2 Bottleneck-Aware Scaling

**Date**: 2026-08-05 · **Experiment Plan**: [experiment_plan.md](experiment_plan.md)

> **RQ2 v2 (final evidence):** the **36-run v2 campaign** — open-loop driver,
> 6 cells × 6 replicates, `CURL_MAX_TIME=300`/`INFLIGHT_WINDOW=1024`/
> `DRAIN_S=30`, significance-capable statistics at n=6 (exact MWU, Cliff's
> delta, 6/6 direction), sync-cost + relief-flatten — **completed mechanically
> (36/36 exit 0) but is CONFOUNDED by a load-calibration failure**: the
> open-loop offered load exceeded the platform's sustainable capacity in both
> episodes, so **no cell operated in a healthy baseline regime**. The
> pre-registered SC1–SC6 evaluation below is therefore **not a clean
> validation**; the campaign must be re-calibrated (load / concurrency) and
> re-run before any thesis conclusion is drawn from it (spec:
> [`rq2_v2_rework_plan.md`](rq2_v2_rework_plan.md) Phase 5; `results.md` §v2
> Judgment, Root Causes).
>
> **v1 / supporting record:** the 18-run campaign (2026-08-04) is retained in
> the **Appendix** with its caveats (latency-coupled driver, 30 s censoring,
> n=3) — characterization and reproduction evidence, not final thesis evidence.

## RQ2 v2 (final evidence)

**Status:** ⚠️ **Completed (36/36 exit 0, all gates passed) but confounded** —
see the v2 Judgment: the open-loop load exceeded platform capacity in both
episodes, inverting the data-bound cross-over and leaving no healthy baseline.
Analysis date 2026-08-05 on `cloud-vm-rq2` (run folders archived there; only
analysis outputs are retained locally).

**Config:** open-loop driver (`TRAFFIC_DRIVER_MODE=open_loop`, `CURL_MAX_TIME=300`,
`INFLIGHT_WINDOW=1024`, `DRAIN_S=30`); **n = 6 per cell; 6 cells × 6 replicates
= 36 runs**; 6 counterbalanced blocks (seeds 2001–2006, orders in
[`counterbalance_order_v2.csv`](counterbalance_order_v2.csv)); episode rate
3.0 req/s/client (cb) / 1.5 req/s/client (db), 48 active clients; **per-run
driver self-test gate** (fail-fast on every run); significance-capable
statistics at n=6 (exact MWU, min p = 0.0022; Cliff's delta; 6/6 direction);
`sync_cost.csv` + `relief_flatten.csv` per run.

### v2 Run Timeline

| Run | Date | Status | Cumulative Analysis | Conclusions | Changes Made | Expectations for This Run |
|-----|------|--------|---------------------|-------------|--------------|--------------------------|
| Pre-flight gates: driver selftest, concurrency stress, G2 calibration (`ba_cb`, `ba_db`), sync regression | 2026-08-04 | ⚠️ | — | Gates passed; **calibration runs already show the overload that later dominates the campaign** (`ba_cb_cal2` ep p50 ≈ 3.1 s / 15 % timeout; `ba_db_cal2` ep p50 ≈ 67 s / 22 % timeout) | — (baseline of the 36-run v2 campaign) | All gates pass; rates tuned to ≤ 3 req/s/client so `window/rate > 300 s` |
| Block 1 — 6 runs (seed 2001) | 2026-08-04 22:07 – 08-05 01:39 | ⚠️ | Calibration overload signal | All runs exit 0; every cell overloaded (ep timeout 8–50 %); data-bound storage path at 3–11 s db latency | — | Replicate the calibration's health |
| Block 2 — 6 runs (seed 2002) | 2026-08-05 02:08–04:32 | ⚠️ | Block 1: universal overload, not cell-specific | Overload reproducible; `ba_db` consistently the least-degraded cell | — | Replicate consistency |
| Block 3 — 6 runs (seed 2003) | 2026-08-05 05:02–07:24 | ⚠️ | Blocks 1–2: aligned arms are not healthy references | Cross-over not reproduced; `sf_db` (aligned) timeout 43–53 % | — | Replicate-3 confirmation |
| Block 4 — 6 runs (seed 2004) | 2026-08-05 07:54–10:17 | ⚠️ | 3 blocks: `ba_db` robust, fixed arms inverted in db | 6/6 `ba_db` lowest timeout in db | — | Replicate consistency |
| Block 5 — 6 runs (seed 2005) | 2026-08-05 10:45–13:08 | ⚠️ | 4 blocks: overload stable across seeds | `sf_db` 43–53 % vs `cf_db` 16–22 % timeout (inverted) | — | Replicate consistency |
| Block 6 — 6 runs (seed 2006) | 2026-08-05 13:35–15:58 | ⚠️ | 5 blocks: full-campaign overload picture | 36/36 exit 0; campaign confounded; re-run required | — | Final replicate confirmation |

Status legend: ✅ = run valid and passed its gates · ⚠️ = run valid but the
cell is **not** a clean health reference (overload regime) · ❌ = invalid.

### v2 Measurements — Per-Cell

Measurements are presented without judgment (all judgment is in **v2
Judgment**). All values are episode-phase medians over the 6 replicates unless
noted. **Unified denominators:** offered = all rows; timeout rate =
`status=timeout`/offered (the **primary degradation statistic**, defined for
every run); failure rate = completed & `http_status` not in (`"200"`, `""`)
/ completed; dropped/canceled reported separately and **excluded from latency
and failure**. **Latency is reported in seconds** (the v2 dataset stores
seconds in the `ep_pXX_ms` columns, v1 convention; the `CURL_MAX_TIME=300` s
cap is the censoring bound, not 30 s). Latency percentiles are descriptive
only; no censored value enters MWU. Full per-run rows:
`analysis/campaign_dataset.csv` (v2, 36 rows) + `stats_summary.csv`
(`rq2v2_p2_03_stats.py`). Graphs: `graphs/20260805/`.

| Cell | actions (c/s) | budget used (c/s, per LAN max) | classifier-vs-episode agree % | relief (recovered/actions) | median recovery (s) | node-min/1000 (c + s) | episode offered | timeout % | failure % | ep p50 (s) | ep p95 (s) | ep p99 (s) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `cf_cb` | 8 / 0 | 4 / 0 | 50.9 | 5 / 8 | 65.2 | 1.579 + 0.000 | 86 112 | 19.1 | 1.52 | 3.0 | 18.3 | 45.6 |
| `cf_db` | 8 / 0 | 4 / 0 | 78.6 | 6 / 8 | 85.0 | 2.841 + 0.000 | 43 114 | 19.7 | 4.98 | 108.1 | 207.4 | 254.4 |
| `sf_cb` | 0 / 1 | 0 / 0 | 63.6 | 0 / 1 | — | 0.000 + 0.088 | 86 113 | 23.0 | 0.53 | 3.3 | 18.9 | 60.7 |
| `sf_db` | 0 / 6 | 0 / 4 | 77.6 | 4 / 6 | 75.0 | 0.000 + 2.404 | 43 125 | 49.8 | 10.97 | 19.9 | 95.0 | 151.8 |
| `ba_cb` | 8 / 1 | 4 / 1 | 50.8 | 6 / 9 | 35.1 | 1.545 + 0.104 | 86 113 | 18.8 | 1.64 | 2.9 | 18.1 | 49.9 |
| `ba_db` | 8 / 8 | 4 / 4 | 77.9 | 6 / 16 | 39.8 | 3.269 + 2.543 | 43 126 | 10.3 | 1.25 | 2.6 | 16.1 | 27.7 |

Per-run episode timeout % (all 6 replicates) — the primary degradation statistic:

| Cell | r1 | r2 | r3 | r4 | r5 | r6 |
|---|---:|---:|---:|---:|---:|---:|
| `cf_cb` | 7.24 | 14.12 | 15.38 | 22.80 | 23.25 | 28.04 |
| `cf_db` | 15.61 | 16.86 | 19.17 | 20.29 | 22.20 | 22.35 |
| `sf_cb` | 14.01 | 17.98 | 19.08 | 26.85 | 34.88 | 37.98 |
| `sf_db` | 43.20 | 45.29 | 48.66 | 50.95 | 51.08 | 53.26 |
| `ba_cb` | 6.90 | 15.10 | 16.41 | 21.29 | 21.95 | 24.88 |
| `ba_db` | 8.65 | 9.14 | 9.55 | 11.11 | 12.74 | 12.86 |

Per-run episode failure % (completed-only):

| Cell | r1 | r2 | r3 | r4 | r5 | r6 |
|---|---:|---:|---:|---:|---:|---:|
| `cf_cb` | 0.37 | 0.59 | 1.15 | 1.90 | 3.49 | 3.56 |
| `cf_db` | 0.07 | 0.41 | 1.56 | 8.40 | 13.28 | 17.62 |
| `sf_cb` | 0.09 | 0.15 | 0.15 | 0.90 | 1.74 | 2.47 |
| `sf_db` | 6.94 | 7.33 | 10.77 | 11.18 | 11.75 | 12.35 |
| `ba_cb` | 0.50 | 0.93 | 1.51 | 1.77 | 1.85 | 2.26 |
| `ba_db` | 0.07 | 1.13 | 1.24 | 1.27 | 1.54 | 1.66 |

v2-only metrics (medians over runs that produced the artifact):

| Cell | sync members (n) | sync duration (s) | storage CPU during sync (%) | relief-flatten actions | plateau within window | recovered below threshold | relief signal |
|---|---:|---:|---:|---:|---:|---:|---:|
| `ba_db` | 10 | 9.9–10.2 | 62–68 | 16 | 9–11 | 4–11 | 10–11 |
| `sf_db` | 7–9 | 9.8–10.4 | 54–70 | 5–7 | 2–4 | 2–4 | 3–4 |
| `ba_cb` | 3–4 | 2.9–9.5 | 13–20 | 9–10 | 5–7 | 3–7 | 5–7 |
| `cf_cb` / `cf_db` | 2 | 3.6–7.7 | — | 7–8 | 5–8 | 3–8 | 5–8 |
| `sf_cb` | 2–3 | 4.9–9.7 | 13–21 | 0–1 | 0 | 0 | 0 |

### v2 Judgment

**Headline: the 36-run campaign is CONFOUNDED by a load-calibration failure,
not a clean evaluation.** Every conclusion below is framed as agreement or
divergence from the plan's expectations (`experiment_plan.md` §5, SC1–SC6).

**The overload (evidence):**
- Offered episode rate = 48 clients × 3.0 (cb) / 1.5 (db) req/s = **144 / 72
  req/s**. Sustained service rate during the episode: `cf_cb` ≈ 119 req/s
  (86 112 offered / 600 s, 15–28 % timeouts), `sf_db` ≈ 34 req/s, `cf_db` ≈
  36 req/s, `ba_db` ≈ 62 req/s. Offered **exceeds** capacity in both episodes.
- The platform is **healthy at the lower rates of the same run**: baseline /
  `demand_drop` (1.0 req/s/client = 48 req/s) show p50 ≈ 7 ms, while the
  episode (144 req/s) shows p50 ≈ 2.8 s in the same run (`cf_cb_1`). This is
  queue-overload, not a permanent regression.
- The **G2 calibration runs themselves already showed the overload**
  (`ba_cb_cal2` ep p50 ≈ 3.1 s / 15 % timeout; `ba_db_cal2` ep p50 ≈ 67 s /
  22 % timeout) and were accepted — the calibration validated the
  client-side `window/rate > 300 s` (drop-avoidance) condition but **not the
  platform's ability to serve the offered load**.
- Data-bound storage path: median `avg_time_db_ms` = **3 s (`ba_db`) to 11 s
  (`sf_db`)** during the episode (v1's data-bound episode was ~100–250 ms) —
  MongoDB saturated under the open-loop driver's concurrency (up to
  `INFLIGHT_WINDOW=1024` per client vs the sync driver's 1 in-flight/client).
- **0× `NotPrimaryOrSecondary`** across all 36 runs (the data-path fix holds)
  and no controller restart — so the saturation is genuine capacity, not a
  read-preference defect.

**Criterion-by-criterion (per plan §5):**

1. **Artifact + decision-log contract — ✅ met (36/36).** All artifacts present
   and non-empty per LAN; full 20-column `scale_up` rows; open-loop knobs in
   every env snapshot; one `scale_up` row per evaluated window.
2. **Episode induction valid (G2) — ✅ met (36/36).** Median proc-vs-db
   dominance matches every episode label (independent `window_log` validator).
3. **Fixed-arm suppression — ✅ met.** `cf` never selects storage (cf_cb/cf_db
   storage = 0), `sf` never selects compute (sf_cb/sf_db compute = 0);
   suppressed fires still logged with `*_fired`/`rejected_action`.
4. **Bottleneck-aware selects the pressured tier (SC4) — ✅ met (as
   reported).** Classifier-vs-episode agreement: `ba_db` 77.9 % (6/6 above
   chance), `ba_cb` 50.8 % ≈ chance — the honest cb/db asymmetry
   pre-registered in the plan. `ba` selects compute in cb (8/LAN) and both
   tiers in db (8+8/LAN).
5. **Budget binds (SC5 mechanics) — ✅ met.** 4/tier/LAN exhausted in every
   scaled cell (cf 4/0, sf 0/4 in db, ba 4/4 in db, ba 4/1 in cb); caps 6/6
   above the budget; `reason="budget_exhausted"` reachable; T9.8 fire-keyed
   scale-down protection OK in all runs.
6. **Relief in the targeted tier — ⚠️ inconclusive under overload.** In-tier
   recovery 5–6/8 (cf cells), 4/6 (`sf_db`), 6/16 (`ba_db`); relief-flatten
   `relief_signal` 63–69 % of actions in `ba_db`/`sf_db` and 56–70 % in
   `ba_cb`/`cf_cb`; `sf_cb` shows none (0–1 actions). Because every cell is
   overloaded, "relief" (score below threshold / plateau) does not translate
   into service health (episode p50 ≥ 2.6 s even in the best cell).
7. **Scale-down + fire-keyed protection (T9.8) — ✅ met.** Scale-down present
   where the allowed tier scaled; no cooldown-gated violation in any run.
8. **Cross-over + open-loop contrast (SC1) — ❌ NOT reproduced.** The
   pre-registered headline ("aligned beats mis-aligned on p95 + timeout_rate,
   6/6, Cliff's δ ≥ 0.6") fails:
   - **cb**: `cf` (19.1 %) vs `sf` (23.0 %) timeout — direction correct but
     small (MWU p = 0.394, δ = −0.33; not 6/6).
   - **db**: **INVERTED** — aligned `sf_db` 49.8 % vs mis-aligned `cf_db`
     19.7 % timeout, 6/6 in the **wrong** direction (MWU p = 0.0022, δ = 1.0).
     The aligned storage-first arm is the worst cell; `cf_db`'s compute
     scale-out keeps requests in-flight (completing slowly, p50 = 108 s)
     instead of timing out. The v1 cross-over direction does **not** survive
     the open-loop overload.
   - `offered ≈ completed + timeout` across arms confirms the open-loop
     driver preserved the offered load (no latency-coupled divergence) — the
     G1 confound is genuinely removed, which is exactly why the overload is
     now visible.
9. **Efficiency / node-minutes (SC6) — ❌ as written → pre-registered
   dual-budget finding applies.** `ba_db` node-minutes/1000 = 5.812 vs aligned
   `sf_db` 2.404 and mis-aligned `cf_db` 2.841 — `ba` spends **both** budgets
   (8 compute + 8 storage in db), matching the pre-campaign evidence and the
   plan §7.7 pre-registered rule. Per that rule this is reported **as a
   finding, not a shortfall**: `ba_db` is the only cell that keeps timeout ≤
   12.9 % in db (aligned `sf_db` ≥ 43 %) and p50 ≤ 2.6 s, so `ba` delivers
   quality **without knowing the episode**, at a **budget-bounded** resource
   cost (4/tier/LAN — the same ceiling each fixed arm hits on its own tier).
   The efficiency narrative reframes to "avoids the mis-configured outcome at
   a bounded, budget-capped cost", exactly as pre-registered.
10. **Stats — ⚠️ reported, but interpretability limited.** Exact MWU at n=6
    reached significance on several pairs (min p = 0.0022), but the headline
    pairs are either not significant (cb timeout, p = 0.394) or significant in
    the **anti-hypothesis** direction (db aligned-vs-misaligned, p = 0.0022,
    inverted). Significance without a healthy baseline cannot support the
    plan's claims. `sync_cost` measured: storage initial-sync ≈ 10 s at 54–70 %
    storage CPU in data-bound cells — a real, quantified action cost.

**Confirmed (multi-run) vs hypothesis (single-run):**
- **Confirmed (36/36):** open-loop driver preserves offered load; episode
  induction valid; budget binds; T9.8 intact; 0× NotPrimary; no restart;
  data-bound storage path saturates under open-loop concurrency (3–11 s db
  latency).
- **Confirmed (6/6 each):** `ba_db` is the least-degraded data-bound cell on
  timeout (8.7–12.9 %) and failure (≤ 1.66 %); `sf_db` (aligned) is the worst
  (43–53 % timeout) — a robust inversion of the plan's SC1 expectation.
- **Hypothesis:** the exact mechanism of the ~120 req/s compute-bound ceiling
  (CPU 43 % at 0.4 ms service time — a non-CPU bottleneck, likely WAN/network
  emulation or aggregator serialization) and the storage saturation driver
  need targeted investigation before re-running.

### v2 Root Causes

| # | Issue | Impact | Status |
|---|-------|--------|--------|
| 1 | **Open-loop load calibration failure** — episode rates 3.0/1.5 req/s/client (144/72 req/s) exceed platform capacity (~119 cb, ~35–62 db req/s); calibration validated only the drop-free window, not service capacity | All cells overloaded (ep timeout 7–53 %); no healthy baseline; SC1/SC2/SC6 uninterpretable as pre-registered | Confirmed (36/36 + calibration runs) — **must be fixed before re-run** |
| 2 | **Storage tier saturated under open-loop concurrency** — db latency 3–11 s vs v1's ~100–250 ms; `STORAGE_CPUS=0.08` + pool 6 cannot serve the open-loop in-flight concurrency | Data-bound episode collapses; aligned `sf_db` 49.8 % timeout; storage scale-out provides little relief | Confirmed (db cells, 6/6) — candidate fix: lower episode rate, raise storage CPU/pool, or bound concurrency |
| 3 | **Non-CPU compute-bound ceiling (~120 req/s at 43 % CPU / 0.4 ms service)** — mechanism unidentified | Compute-bound overload even with headroom | Hypothesis — needs targeted capacity probe |
| 4 | **2/6 `sf_cb` runs spawn zero nodes** (storage signal never fires in cb under open-loop) | `sf_cb` relief absent in 2 runs; mis-aligned arm cannot even act | Expected H2 variant — documented |

### v2 Next Actions

1. **Do not treat this campaign as final RQ2 evidence.** Re-calibrate the
   load: lower episode rates (target a healthy aligned-arm baseline, e.g.
   ≤ 1.0 req/s/client cb) **and** validate service capacity in the G2 gate
   (not just the drop-free window); consider bounding open-loop concurrency
   or raising `STORAGE_CPUS`/pool for the data-bound episode.
2. **Investigate the ~120 req/s compute-bound ceiling** (WAN emulation,
   aggregator, VIP flow pinning) before re-running — a capacity probe at
   0.5/1.0/2.0/3.0 req/s/client on `cf_cb`.
3. **Re-run the 36-run campaign** on the re-calibrated load; only then
   evaluate SC1–SC6 as pre-registered (incl. the SC6 dual-budget rule).
4. Keep this dataset as the **overload-characterization record**: it proves
   the open-loop driver's confound-removal and bounds the platform's capacity
   envelope.
5. Update `post_run_analysis.md` after the re-run.

### v2 Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-08-05 | 36-run campaign analyzed on `cloud-vm-rq2`; dataset + stats + graphs produced; results recorded | Campaign mechanically complete but confounded by load calibration — full SC1–SC6 evaluation with the overload finding |

---

## Appendix — v1 18-run campaign (2026-08-04, supporting record)

> **Retained as the v1 / supporting record.** The v2 campaign above is the
> final evidence; v1 stays for characterization and reproduction. **Caveats**
> that keep v1 from being final evidence (`rq2_v2_rework_plan.md` §1):
> **(G1)** latency-coupled sync driver — offered load differed per arm
> (`cf_db`/`sf_db` issued ~60 % less, `ba_db` ~29 % more than intended);
> **(G2)** p99 censored at the 30 s cap (`CURL_MAX_TIME=30`) — `p99=30000` is
> the cap, not a measurement, and timeouts were conflated with failures;
> **(G3)** n=3 — Mann–Whitney U significance impossible (min p = 0.10), effect
> sizes only; **(G4)** `ba_db` scaled both tiers (8 compute + 8 storage) — no
> sticky commitment, so its edge over `sf_db` may be capacity, not
> classification; **(G5)** replica-sync action cost not measured.

### v1 Run Timeline

| Run | Date | Status | Cumulative Analysis | Conclusions | Changes Made | Expectations for This Run |
|-----|------|--------|---------------------|-------------|--------------|--------------------------|
| Block 1 — 6 runs (`cf_cb_1`…`sf_db_1`) | 2026-08-03 23:21–2026-08-04 01:50 | ✅ | — (first block on fixed data path) | All 6 G2-PASS, correct knobs, 0× NotPrimary, no restarts | — (baseline of the fixed-path campaign; the pre-fix Block-1 set was deleted — see `run_matrix.md` note) | From plan §5: G2 valid induction, suppression (cf/sf), budget binds, T9.8 OK |
| Block 2 — 6 runs (`ba_cb_2`…`cf_db_2`) | 2026-08-04 02:21–04:42 | ✅ | Block 1: induction valid in all 6 cells; cf/sf suppression clean; ba cells classify above chance | Confirmed Block-1 behavior; no drift across blocks | — (same config; counterbalanced order) | Same as Block 1 + replicate consistency |
| Block 3 — 6 runs (`sf_db_3`…`ba_db_3`) | 2026-08-04 05:11–07:31 | ✅ | Blocks 1–2: all 12 runs G2-PASS, budget binds at 4/tier/LAN, T9.8 OK, cross-over direction reproduced | 18/18 consistent: cf≈ba beat sf in cb; sf/ba beat cf in db; cf_db shows 30 s p99 timeout tail (H2) | — (same config) | Replicate-3 confirmation of the cross-over |

Status legend: ✅ = run valid and passed its gates; all 18 runs exit 0, correct env knobs, 0× `NotPrimaryOrSecondary`, no controller restart, fresh window seq (checkpoints C1–C3). In the per-run sections, ⚠️ marks the plan-expected **mis-aligned arms** (`cf_db`, `sf_cb` — H2 degradation is the treatment effect, not a run-validity issue); every run is ✅ on validity/gates.

### v1 Measurements — Per-Run

Measurements are presented without judgment (all judgment is in the **Judgment** section). All values are episode-phase medians/rates unless noted; latency in ms; failures = `http_status != 200`. Full per-run rows: [`analysis/campaign_dataset.csv`](analysis/campaign_dataset.csv). Per-run narrative: [`analysis/run_summaries/`](analysis/run_summaries/).

### Run 1–3: `cf_cb` (fixed_compute_first × compute-bound) — `..._cf_cb_1..3`

**Status**: ✅ — G2 PASS both LANs; compute 8 spawns, storage 0.

| Metric | r1 | r2 | r3 |
|---|--:|--:|--:|
| G2 (proc_ms / db_ms, LAN1) | 0.47 / 0.00 | 0.40 / 0.00 | 0.24 / 0.00 |
| G2 (storage CPU %) | 0.0 | 0.0 | 0.0 |
| scale_up rows (deduped) | 263 | 266 | 265 |
| action counts (compute / storage) | 8 / 0 | 8 / 0 | 8 / 0 |
| budget used (c/s per LAN) | 4/0 · 4/0 | 4/0 · 4/0 | 4/0 · 4/0 |
| classifier-vs-episode agree | 24/49 (49.0%) | 29/55 (52.7%) | 25/50 (50.0%) |
| T9.8 fire-keyed scale-down | OK | OK | OK |
| relief recovered (in-tier) | 0/8 | 3/8 | 4/8 |
| relief median recovery (s) | — | 60.0 | 90.0 |
| episode p50 / p95 / p99 (ms) | 6.8 / 254 / 503 | 2.4 / 175 / 754 | 2.7 / 234 / 475 |
| episode failure % | 0.44 | 0.25 | 0.53 |
| node-min/1000 req (comp / stor) | 0.855 / 0 | 0.849 / 0 | 0.849 / 0 |
| TTFT comp median (s) | 39.5 | 39.6 | 29.5 |

### Run 4–6: `cf_db` (fixed_compute_first × data-bound) — `..._cf_db_1..3`

**Status**: ⚠️ (valid run; **mis-aligned arm — expected degraded**, H2). G2 PASS; compute 8 spawns, storage 0.

| Metric | r1 | r2 | r3 |
|---|--:|--:|--:|
| G2 (proc_ms / db_ms, LAN1) | 36.7 / 306.8 | 15.4 / 276.3 | 58.4 / 307.1 |
| G2 (storage CPU %) | 34.1 | 28.4 | 35.9 |
| scale_up rows (deduped) | 261 | 273 | 263 |
| action counts (compute / storage) | 8 / 0 | 8 / 0 | 8 / 0 |
| budget used (c/s per LAN) | 4/0 · 4/0 | 4/0 · 4/0 | 4/0 · 4/0 |
| classifier-vs-episode agree | 35/50 (70.0%) | 38/53 (71.7%) | 31/49 (63.3%) |
| T9.8 | OK | OK | OK |
| relief recovered (in-tier) | 4/8 | 5/8 | 4/8 |
| relief median recovery (s) | 49.3 | 39.5 | 50.2 |
| episode p50 / p95 / p99 (ms) | 485 / 2076 / 30000 | 482 / 1979 / 30000 | 495 / 1990 / 30000 |
| episode failure % | 1.04 | 2.10 | 3.38 |
| node-min/1000 req (comp / stor) | 4.593 / 0 | 4.730 / 0 | 4.187 / 0 |
| TTFT comp median (s) | 59.6 | 29.4 | 39.3 |

### Run 7–9: `sf_cb` (fixed_storage_first × compute-bound) — `..._sf_cb_1..3`

**Status**: ⚠️ (valid run; **mis-aligned arm — expected no relief**, H2). G2 PASS; compute 0 spawns, storage 1.

| Metric | r1 | r2 | r3 |
|---|--:|--:|--:|
| G2 (proc_ms / db_ms, LAN1) | 0.69 / 0.00 | 0.72 / 0.00 | 0.74 / 0.00 |
| G2 (storage CPU %) | 8.2 | 0.0 | 0.0 |
| scale_up rows (deduped) | 264 | 259 | 264 |
| action counts (compute / storage) | 0 / 1 | 0 / 1 | 0 / 1 |
| budget used (c/s per LAN) | 0/0 · 0/1 | 0/0 · 0/1 | 0/1 · 0/0 |
| classifier-vs-episode agree | 44/71 (62.0%) | 51/72 (70.8%) | 54/78 (69.2%) |
| T9.8 | OK | OK | OK |
| relief recovered (in-tier) | 0/1 | 0/1 | 0/1 |
| relief median recovery (s) | — | — | — |
| episode p50 / p95 / p99 (ms) | 163 / 370 / 664 | 167 / 383 / 873 | 160 / 376 / 876 |
| episode failure % | 0.26 | 0.29 | 0.24 |
| node-min/1000 req (comp / stor) | 0 / 0.078 | 0 / 0.037 | 0 / 0.079 |
| TTFT stor median (s) | 39.4 | 39.1 | 39.1 |

### Run 10–12: `sf_db` (fixed_storage_first × data-bound) — `..._sf_db_1..3`

**Status**: ✅ — G2 PASS; compute 0 spawns, storage 8.

| Metric | r1 | r2 | r3 |
|---|--:|--:|--:|
| G2 (proc_ms / db_ms, LAN1) | 10.8 / 103.1 | 22.0 / 244.6 | 19.3 / 245.8 |
| G2 (storage CPU %) | 27.7 | 32.4 | 35.3 |
| scale_up rows (deduped) | 259 | 212 | 230 |
| action counts (compute / storage) | 0 / 8 | 0 / 8 | 0 / 8 |
| budget used (c/s per LAN) | 0/4 · 0/4 | 0/4 · 0/4 | 0/4 · 0/4 |
| classifier-vs-episode agree | 26/32 (81.3%) | 31/43 (72.1%) | 26/37 (70.3%) |
| T9.8 | OK | OK | OK |
| relief recovered (in-tier) | 4/8 | 4/8 | 4/8 |
| relief median recovery (s) | 20.2 | 20.2 | 19.4 |
| episode p50 / p95 / p99 (ms) | 395 / 1369 / 2774 | 588 / 1972 / 30000 | 501 / 1865 / 30000 |
| episode failure % | 0.78 | 1.19 | 1.05 |
| node-min/1000 req (comp / stor) | 0 / 2.584 | 0 / 3.649 | 0 / 3.396 |
| TTFT stor median (s) | 34.7 | 29.4 | 39.3 |

### Run 13–15: `ba_cb` (bottleneck_aware × compute-bound) — `..._ba_cb_1..3`

**Status**: ✅ — G2 PASS; compute 8 spawns, storage 0/2/1.

| Metric | r1 | r2 | r3 |
|---|--:|--:|--:|
| G2 (proc_ms / db_ms, LAN1) | 0.32 / 0.00 | 0.44 / 0.00 | 0.41 / 0.00 |
| G2 (storage CPU %) | 0.0 | 7.7 | 0.0 |
| scale_up rows (deduped) | 261 | 262 | 261 |
| action counts (compute / storage) | 8 / 0 | 8 / 2 | 8 / 1 |
| budget used (c/s per LAN) | 4/0 · 4/0 | 4/1 · 4/1 | 4/0 · 4/1 |
| classifier-vs-episode agree | 26/48 (54.2%) | 31/49 (63.3%) | 30/51 (58.8%) |
| T9.8 | OK | OK | OK |
| relief recovered (in-tier) | 1/8 | 2/10 | 0/9 |
| relief median recovery (s) | 10.0 | 40.9 | — |
| episode p50 / p95 / p99 (ms) | 2.9 / 222 / 757 | 3.7 / 244 / 483 | 3.4 / 237 / 694 |
| episode failure % | 0.66 | 0.64 | 0.15 |
| node-min/1000 req (comp / stor) | 0.831 / 0 | 0.851 / 0.099 | 0.831 / 0.052 |
| TTFT comp median (s) | 29.1 | 29.3 | 34.4 |

### Run 16–18: `ba_db` (bottleneck_aware × data-bound) — `..._ba_db_1..3`

**Status**: ✅ — G2 PASS; compute 8 spawns, storage 8.

| Metric | r1 | r2 | r3 |
|---|--:|--:|--:|
| G2 (proc_ms / db_ms, LAN1) | 15.4 / 217.1 | 14.7 / 189.4 | 16.2 / 217.0 |
| G2 (storage CPU %) | 37.2 | 31.6 | 39.7 |
| scale_up rows (deduped) | 257 | 264 | 262 |
| action counts (compute / storage) | 8 / 8 | 8 / 8 | 8 / 8 |
| budget used (c/s per LAN) | 4/4 · 4/4 | 4/4 · 4/4 | 4/4 · 4/4 |
| classifier-vs-episode agree | 24/31 (77.4%) | 26/35 (74.3%) | 24/34 (70.6%) |
| T9.8 | OK | OK | OK |
| relief recovered (in-tier) | 7/16 | 7/16 | 8/16 |
| relief median recovery (s) | 30.2 | 40.2 | 50.5 |
| episode p50 / p95 / p99 (ms) | 127 / 1165 / 2187 | 247 / 1313 / 2519 | 92 / 1181 / 2201 |
| episode failure % | 0.39 | 0.55 | 0.79 |
| node-min/1000 req (comp / stor) | 2.385 / 1.766 | 2.817 / 2.044 | 2.207 / 1.655 |
| TTFT comp / stor median (s) | 39.8 / 29.7 | 39.1 / 39.3 | 49.6 / 29.4 |

### v1 Cross-Run Comparison

### Per-episode policy comparison (mean over 3 replicates)

| Episode | Policy | actions (c/s) | agree % | ep p50 (ms) | ep p95 (ms) | ep p99 (ms) | failure % | node-min/1000 (c+s) |
|---|---|---|---|--:|--:|--:|--:|--:|
| compute-bound | cf | 8 / 0 | 50.6 | 4 | 221 | 577 | 0.41 | 0.85 + 0 |
| compute-bound | sf | 0 / 1 | 67.3 | 163 | 376 | 804 | 0.26 | 0 + 0.06 |
| compute-bound | ba | 8 / 1 | 58.8 | 3 | 234 | 645 | 0.48 | 0.84 + 0.05 |
| data-bound | cf | 8 / 0 | 68.3 | 487 | 2015 | **30000** | 2.17 | 4.50 + 0 |
| data-bound | sf | 0 / 8 | 74.6 | 495 | 1735 | 20925 | 1.01 | 0 + 3.21 |
| data-bound | ba | 8 / 8 | 74.1 | 155 | 1220 | 2302 | 0.58 | 2.47 + 1.82 |

### Time-to-usable-capacity (per-run median TTFT, s)

| Cell | compute TTFT | storage TTFT |
|---|---|:--:|
| cf_cb | 29–40 | — |
| cf_db | 29–60 | — |
| sf_cb | — | 39 |
| sf_db | — | 29–39 |
| ba_cb | 29–34 | 39–40 |
| ba_db | 39–50 | 29–39 |

### Counterbalance order (from run-folder names)

| Block | Run order |
|---|---|
| 1 | cf_cb, cf_db, ba_db, sf_cb, ba_cb, sf_db |
| 2 | ba_cb, ba_db, sf_db, cf_cb, sf_cb, cf_db |
| 3 | sf_db, ba_cb, sf_cb, cf_cb, cf_db, ba_db |

Three distinct orders (seeds 1001/1002/1003), each cell once per block — see [`counterbalance_order.csv`](counterbalance_order.csv).

### v1 Judgment

All 18 runs: exit 0, `SCALEUP_POLICY` matches arm, budget 4, `LATENCY_SIGNAL_MODE=median`, storage-CPU floor 35, `secondaryPreferred`/pool 6/per-connection flows confirmed in every `controller_env_snapshot.env`; **0× `NotPrimaryOrSecondary`** across all `service_logs/`; no controller restart; fresh window seq per run (C1–C3).

### Criterion-by-criterion

1. **Artifact + decision-log contract — ✅ met (18/18).** All artifacts present/non-empty per LAN; every `scale_up` row has the full 20-column header with evidence/`*_fired`/`*_eligible`/`*_budget_used` populated; dedup by `(window_id, action_type)` is a no-op.
2. **Episode induction (G2) — ✅ met (18/18).** Median proc-vs-db dominance matches the label in every run: compute-bound `proc_ms` 0.2–0.8 ≫ `db_ms` 0.00; data-bound `db_ms` 103–307 ≫ `proc_ms` 11–97, with storage CPU 27–55 %. Independent validator (raw `window_log` signals), robust to spawn transients.
3. **Fixed-arm suppression — ✅ met.** `cf` never emits `selected_action=storage` (18 runs: cf_cb/cf_db all storage=0); `sf` never emits `selected_action=compute` (sf_cb/sf_db all compute=0). Suppressed-tier fires still logged (`*_fired`), `selected/rejected` record the counterfactual.
4. **Bottleneck-aware selects pressured tier — ✅ met.** In cb, `ba` selects compute (8/LAN); in db, `ba` selects storage (8/LAN, plus compute — see note). Per-window classifier-vs-episode agreement 54–77 % across `ba` cells, all above chance (50 %).
5. **Budget binds — ✅ met.** Every scaled cell exhausts the 4/tier/LAN budget (usage == cap in cf_cb, cf_db, sf_db, ba_cb, ba_db). Caps 6/6 sit above the budget, so exhaustion is budget-driven, not cap-ineligibility; `reason="budget_exhausted"` is rare only because no cell fires a 5th time (the budget binds by reaching the cap, exactly the Option-B design).
6. **Relief in the targeted tier — ⚠️ partially met / reported.** Aligned arms recover in-tier for ~50 % of actions (sf_db 4/8, ba_db 7–8/16, median recovery 20–51 s); compute-bound cells show lower in-tier recovery (cf_cb 0/8, 3/8, 4/8; ba_cb 1/8, 2/10, 0/9) because the pure-compute episode keeps the compute score near its threshold even after scale-out. Mis-aligned `cf_db` recovers compute (4–5/8) yet the service stays degraded (p99 = 30 s) — recovery in the *wrong* tier is visible and does not relieve the data path. `sf_cb` shows no relief (0/1).
7. **Scale-down + fire-keyed protection — ✅ met.** Scale-down decisions present per LAN in every cell where the allowed tier scaled (cf_cb, sf_db, ba_cb, ba_db); absent where nothing scaled (sf_cb, cf_db storage) as expected. No cooldown-gated `scale_down` within `SCALEDOWN_*_COOLDOWN_S` of a `*_fired=1` window — T9.8 OK in all 18.
8. **Cross-over service-quality contrast — ✅ reproduced (the headline).** Compute-bound: `cf` ≈ `ba` beat `sf` (p50 4/3 vs 163 ms; p95 221/234 vs 376 ms) — the mis-aligned storage-first arm is ~1.6–40× worse on latency. Data-bound: `ba` ≥ `sf` ≫ `cf` — `cf_db` p99 pins at the 30 s timeout in all 3 replicates with failures 1.0–3.4 %; `ba_db` holds p99 ≤ 2.5 s with failures 0.39–0.79 % and no timeout tail, while the aligned reference arm `sf_db` still shows a 30 s p99 tail in 2 of 3 replicates (failures 0.78–1.19 %). The direction reproduces across all 3 replicates.
9. **Efficiency / node-minutes — ✅ met with an important nuance.** Wasted actions are visible: `cf_db` spends 4.2–4.7 compute node-min/1000 req on a data-bound episode and still degrades (H2); `sf_cb` spends storage actions that relieve nothing. `ba_db` spends 2.5 compute + 1.8 storage node-min/1000 — it scales both tiers and delivers the best data-bound failure rate (0.58 %) and no 30 s tail. The bottleneck-aware arm is not the *cheapest* (that is the correctly-aligned fixed arm, which exploits the known regime) but it is the most robust: it matches the aligned arm's quality and avoids the mis-aligned arm's cost.
10. **RQ1 artifacts unchanged / no restart — ✅ met.** Window-log/delivery-log semantics preserved in the 20-column format; no controller restart in any run.

### Confirmed findings (multi-run) vs hypotheses (single-run)

- **Confirmed (18/18):** data-path fix holds throughout — storage secondaries serve reads in every data-bound run (0× NotPrimary), so storage scale-out yields usable read capacity; episode induction valid in all cells; budget binds at 4/tier/LAN; T9.8 protection intact.
- **Confirmed (3× each):** the cross-over direction (criterion 8) reproduces in all three replicates; `ba` agreement is above chance in all 6 `ba` runs (54–77 %); mis-aligned `cf_db` shows the 30 s timeout tail in all 3 replicates.
- **Hypothesis / needs care:** the classifier agreement in `cf_cb`/`sf_cb` (≈50–70 %) is inflated by non-decision windows and is best read from the `ba` cells; `sf_db` shows a 30 s p99 tail in 2 of 3 replicates despite being the aligned arm — a residual tail that `ba_db` does not show (worth one paragraph in the thesis, not a harness defect).

### v1 Root Causes (if issues found)

| # | Issue | Impact | Status |
|---|-------|--------|--------|
| 1 | `cf_db` p99 = 30 s (CURL_MAX_TIME) — mis-aligned arm has no signal path to storage | Confounds a fair comparison unless the mis-aligned arm is read as the H2 control (it is) | Expected (H2) — not a defect |
| 2 | Negative `init_time_s` (TTFT−TFR) in spawn metrics | Time-to-usable-capacity is anchored on per_node_stats window granularity, which lags HTTP first-response; init_time is a tooling artifact | Documented in run_summaries; TTFT/TFR reported separately |
| 3 | `ba_cb` storage fires (0–2/LAN) in a DB-free episode | Residual latency-driven tail fires (accepted in the floor-35 calibration; see `run_matrix.md` §6) | Accepted, documented |
| 4 | `sf_db` 30 s p99 tail in 2/3 replicates | Aligned storage-first arm still shows tail timeouts during storage scale-out transients | Reported for thesis nuance |

### v1 Next Actions

1. **Thesis RQ2 chapter**: cite this `results.md` + `graphs/comparison/cross_over.png` as the headline evidence; write the cross-over paragraph and the `sf_db` tail caveat.
2. **Post-run analysis**: [`post_run_analysis.md`](post_run_analysis.md) — objective → mechanism → results → gaps capstone.
3. **Archive**: raw run folders remain on `cloud-vm` (25 folders incl. calibration/probes); local copies intentionally removed (graphs + this analysis are the retained record).
4. **Optional**: regenerate the 15 comparison graphs locally from the retained record (no run folders needed):
   `python -m source.scripts.testing.analysis.rq2.rq2_bottleneck_aware_campaign --from-dataset docs/operation/testing/experiment/v2/rq2/analysis/campaign_dataset.csv --graphs-dir docs/operation/testing/experiment/v2/rq2/graphs/comparison`.
   A full dataset rebuild from raw run folders requires the archive on `cloud-vm`; the VM lacks `latency_summary.csv`/`resource_summary.csv` (metrics_stats outputs), so run `metrics_stats.py` there first for the latency/resource fields.

### v1 Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-08-04 | Campaign completion: 18/18 runs validated on the fixed data path; per-run summaries, campaign dataset, and 15 comparison graphs produced | Final RQ2 evidence record; see `experiment_plan.md` changelog |
| 2026-08-04 | Local run folders removed; VM holds the archive | Keep the workspace lean; graphs + evaluation analysis are the retained record |
