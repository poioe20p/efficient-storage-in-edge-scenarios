# Results — RQ2 v3 Bottleneck-Aware Scaling (Storage-Bind Config)

**Date**: 2026-08-13 (updated for the sf_cb rerun) · **Experiment Plan**: [experiment_plan.md](experiment_plan.md) · **Runs**: 36 campaign + 6 sf_cb rerun @0.15/0.08 (2026-08-12/13) — labels `rq2_<cell>_1..6` for cells `cf_cb, sf_cb, ba_cb, cf_db, sf_db, ba_db`

## Run Timeline

| Run | Date | Status | Cumulative Analysis | Conclusions | Changes Made | Expectations for This Run |
|-----|------|--------|---------------------|-------------|--------------|--------------------------|
| v1 — 35 valid runs (36 − `ba_db_2` − `cf_db_5`) | 2026-08-08/09 | ✅ 34 / ❌ 2 (OOM incidents) | — (initial campaign) | B1 robust; B2 p95-leg CI includes 1.0 (sf_db, ba_db), CPU leg robust (sf_db); ba tail churn; 2 MEMCG OOM incidents | — (baseline, tag `rq2-v3-campaign-20260808`) | (from experiment_plan.md §6; B2 pre-registered n=5 seed-42 CI + seed-43 separate) |
| v2 — sf_cb rerun @0.15/0.08 (6 runs) | 2026-08-12/13 | ✅ 6/6 | v1 + rerun: the 0.30-vs-0.15 confound is resolved (originals @0.30 DF 0 % — never bound) | **sf_cb@0.15 shows NO user-visible wrong-action cost at the tested (sub-capacity) intensity**: 6/6 falsification-shaped (DF 8.7–9.1 %, p50 ~3.3 ms, timeout 0.22–0.53 %, served ≥99.5 %); resource-side cost = compute tier pinned ~61 % of cap in 93–97 % of windows with 0 adds + wasted storage activations; pilot outlier (DF 52 %, timeout 10.8 %) not reproducible | rerun launcher `CELLS["sf_cb"]` → 0.08/0.15 (VM + local, hash `d45cdb29…`); 6 originals quarantined `_superseded_sf_cb_030/`; DF/DT-p50 criteria added (§6.1a); dataset rebuilt (34 rows); graphs regenerated | (amended §6.1a/§6.4, 2026-08-13; sub-capacity load ⇒ no QoE cost, resource waste only) |

> **Replicate pool note (post-analysis)**: the campaign finished 36 runs; the analyzer excluded **2** as MEMCG OOM harness incidents (D2 hard-gate violation) — `ba_db_2` (run 7, 256 MB cap, incident file `ba_db_2_incident.md`) and `cf_db_5` (run 25, 512 MB cap, confirmed same mechanism). Valid pool = **34 runs**: `cf_cb` 6, `ba_cb` 6, `sf_cb` 6, `sf_db` 6, `ba_db` 5, `cf_db` 5. The `EDGE_MEMORY` split (runs 1–14 @ 256m, 15+ @ 512m) is platform hardening, not a treatment; it does not change the policy-comparison direction (cf_cb_4+ at 512m reproduce the B1 signature).

## Measurements — Per-Run

Measurements are presented without judgment. All latency values are completed-request percentiles (ms); `PRE`/`POST` windows are the plan's pinned windows (PRE = episode start → first storage add/activation; POST = ready+120 s → episode end). `p95 ratio` = POST/PRE p95 (B2, db cells); `p50 ratio` = POST/PRE p50 (B1, cb cells). B1/B2 thresholds: B1 p50 ratio < 0.5× (2× drop), B2 p95 < 0.8× OR peak storage-CPU < 0.75× per LAN.

### Compute-bound cells (B1 axis)

| Run | Seed | Timeout % | Served % | Compute adds | Storage activations | B1 p50 ratio lan1/lan2 | PRE p50 (ms) | POST p50 (ms) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| cf_cb_1 | 42 | 1.19 | 98.1 | 8 | 0 | 0.001 / 0.001 | 2962 / 2681 | 3.5 / 3.4 |
| cf_cb_2 | 42 | 0.65 | 99.0 | 8 | 0 | 0.001 / 0.001 | 2713 / 2589 | 3.3 / 3.2 |
| cf_cb_3 | 42 | 1.69 | 97.7 | 8 | 0 | 0.001 / 0.001 | 3021 / 2741 | 3.4 / 3.3 |
| cf_cb_4 | 42 | 1.54 | 97.8 | 8 | 0 | 0.003 / 0.002 | 2960 / 2680 | 3.5 / 3.3 |
| cf_cb_5 | 42 | 4.06 | 95.3 | 8 | 0 | 0.025 / 0.011 | 2281 / 2643 | 3.3 / 3.4 |
| cf_cb_6 | 43 | 1.70 | 97.7 | 8 | 0 | 0.001 / 0.001 | 2402 / 3080 | 3.3 / 3.5 |
| ba_cb_1 | 42 | 0.95 | 98.7 | 8 | 0 | 0.002 / 0.001 | 2163 / 2871 | 3.3 / 3.2 |
| ba_cb_2 | 42 | 0.69 | 99.0 | 8 | 1 (lan1, served) | 0.001 / 0.001 | 2493 / 2531 | 3.3 / 3.2 |
| ba_cb_3 | 42 | 0.49 | 99.2 | 8 | 0 | 0.002 / 0.001 | 2201 / 2520 | 3.3 / 3.2 |
| ba_cb_4 | 42 | 0.49 | 98.9 | 8 | 0 | 0.001 / 0.002 | 2301 / 2381 | 3.3 / 3.2 |
| ba_cb_5 | 42 | 0.69 | 99.0 | 8 | 0 | 0.001 / 0.001 | 2331 / 2421 | 3.3 / 3.2 |
| ba_cb_6 | 43 | 0.98 | 98.3 | 8 | 0 | 0.001 / 0.001 | 2425 / 2540 | 3.4 / 3.5 |
| sf_cb_1 | 42 | 1.62 | 98.4 | 0 | 2 (lan2, wasted) | — (no compute add) | 3.2 | — |
| sf_cb_2 | 42 | 0.00 | 100.0 | 0 | 1 (lan2, wasted) | — | 3.4 | — |
| sf_cb_3 | 42 | 0.00 | 100.0 | 0 | 1 (lan2, wasted) | — | 3.2 | — |
| sf_cb_4 | 42 | 0.00 | 100.0 | 0 | 2 (lan2, wasted) | — | 3.3 | — |
| sf_cb_5 | 42 | 0.00 | 100.0 | 0 | 2 (lan2, wasted) | — | 3.2 | — |
| sf_cb_6 | 43 | 0.00 | 100.0 | 0 | 2 (lan1+lan2, wasted) | — | 3.2 | — |

> **Superseded (2026-08-13)**: the six `sf_cb_1..6` rows above ran at the confounded **0.30/0.15** static-compute allocation and are superseded by the corrected-config rerun below (originals quarantined on the VM in `_superseded_sf_cb_030/`; full-campaign scan: their DF = 0 % — the tier never bound).

#### sf_cb rerun @ 0.15/0.08 (corrected config, 2026-08-12/13)

| Run | Seed | Timeout % | Served % | Compute adds | Storage activations | agg p50 (ms) | DF % (buckets ≥1 s) | DT-p50 (ms) | Edge CPU % of cap (p50/max) |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rq2_sf_cb_1 | 42 | 0.22 | 99.78 | 0 | 0 | 3.3 | 8.7 (2/23) | 346 | 61.2 / 83.7 |
| rq2_sf_cb_2 | 42 | 0.37 | 99.63 | 0 | 0 | 3.4 | 8.7 (2/23) | 365 | 61.6 / 86.1 |
| rq2_sf_cb_3 | 42 | 0.30 | 99.70 | 0 | 1/LAN (wasted) | 3.4 | 8.7 (2/23) | 339 | 61.7 / 85.5 |
| rq2_sf_cb_4 | 42 | 0.53 | 99.47 | 0 | 1/lan2 (wasted) | 3.4 | 9.1 (2/22) | 412 | 62.4 / 94.0 |
| rq2_sf_cb_5 | 42 | 0.25 | 99.75 | 0 | 2/lan2 (wasted) | 3.3 | 8.7 (2/23) | 329 | 60.7 / 92.2 |
| rq2_sf_cb_6 | 43 | 0.45 | 99.55 | 0 | 1/LAN (wasted) | 3.4 | 8.7 (2/23) | 384 | 62.4 / 86.5 |

**Measurement notes (no judgment):** aggregate episode p50 excludes timed-out requests (latency_summary convention); DF = fraction of 30 s episode buckets with per-LAN-averaged bucket-p50 ≥ 1.0 s (§6.1a); DT-p50 = time-weighted mean of the bucket p50 series; Edge CPU = `average_cpu_percent` as % of the 0.15-container cap. D1 = 0, D2 = 0, D3 present on all 6.

### Data-bound cells (B2 axis)

| Run | Seed | Timeout % | Served % | First storage | B2 p95 ratio lan1/lan2 | B2 CPU ratio lan1/lan2 | Storage CPU PRE→POST (lan1 %) | Compute adds |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| sf_db_1 | 42 | 1.36 | 98.6 | reserve ×2 LANs | 0.579 / 0.579 | 0.583 / 0.573 | 70→44 | 0 |
| sf_db_2 | 42 | 0.04 | 99.9 | reserve ×2 LANs | 0.865 / 0.589 | 0.593 / 0.590 | 68→42 | 0 |
| sf_db_3 | 42 | 0.05 | 99.9 | reserve ×2 LANs | 0.593 / 0.554 | 0.653 / 0.633 | 66→43 | 0 |
| sf_db_4 | 42 | 1.34 | 98.6 | reserve ×2 LANs | 2.038 / 0.748 | 0.660 / 0.653 | 71→47 | 0 |
| sf_db_5 | 42 | 0.04 | 99.9 | reserve ×2 LANs | 1.147 / 0.954 | 0.627 / 0.626 | 66→45 | 0 |
| sf_db_6 | 43 | 0.03 | 99.9 | reserve ×2 LANs | 0.937 / 0.820 | 0.595 / 0.565 | 66→44 | 0 |
| ba_db_1 | 42 | 0.07 | 99.9 | reserve ×2 LANs | 0.763 / 1.205 | 0.706 / 0.618 | 66→45 | 6 |
| ba_db_3 | 42 | 2.65 | 96.4 | reserve ×2 LANs | 26.87 / 1.065 | 0.693 / 0.748 | 66→46 | 6 |
| ba_db_4 | 42 | 0.09 | 99.8 | reserve ×2 LANs | 0.907 / 1.456 | 0.654 / 0.735 | 67→47 | 6 |
| ba_db_5 | 42 | 0.06 | 99.9 | reserve ×2 LANs | 0.600 / 1.193 | 0.850 / 0.709 | 67→49 | 6 |
| ba_db_6 | 43 | 4.42 | 94.2 | reserve ×2 LANs | 35.505 / 8.893 | 1.061 / 0.734 | 69→73 (no relief lan1) | 6 |
| cf_db_1 | 42 | 0.08 | 99.8 | none (compute adds) | — | — | — | 6 |
| cf_db_2 | 42 | 0.11 | 99.8 | none | — | — | — | 6 |
| cf_db_3 | 42 | 0.07 | 99.8 | none | — | — | — | 6 |
| cf_db_4 | 42 | 0.10 | 99.8 | none | — | — | — | 6 |
| cf_db_5 | 42 | 9.31 | 90.4 | late lan1 (cold) | — | — | — | 6 |
| cf_db_6 | 43 | 0.08 | 99.8 | none | — | — | — | 6 |

**Excluded**: `ba_db_2` (run 7) and `cf_db_5` (run 25) — MEMCG OOM incidents, D2 hard-gate violation (see Root Causes).

## Cross-Run Comparison

| Cell | Aligned? | Episode | B1/B2 leg | Cell median p95 ratio (95% CI, n=5 seed-42) | seed-43 | CPU-relief leg | Timeout range % | Served % |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: |
| cf_cb | ✅ aligned | compute | **B1 p50 0.001–0.025×** (≫2× drop) | — | 0.001 | — | 0.65–4.06 | 95.3–99.0 |
| ba_cb | ✅ aligned | compute | **B1 p50 0.001–0.002×** | — | 0.001 | — | 0.49–0.98 | 98.3–99.2 |
| sf_cb | ❌ wrong-action | compute | rerun @0.15: no compute add; DF 8.7–9.1 %, p50 ~3.3 ms, timeout 0.22–0.53 % → **no user-visible wrong-action cost at tested intensity**; compute tier ~61 % of cap in 93–97 % windows, 0 adds (resource cost); storage wasted | — | — | — | 0.22–0.53 (rerun) | 99.5–99.8 (rerun) |
| sf_db | ✅ aligned | data | B2 p95 0.574–1.393 **CI includes 1.0** | 0.879 | CPU 0.57–0.66 **all <0.75** | 0.03–1.36 | 98.6–99.9 |
| ba_db | ✅ classifier | data | B2 p95 0.897–13.968 **CI includes 1.0** (n=4) | 22.199 | CPU 0.62–0.85 lan1 / 0.62–0.75 lan2 (1 fail) | 0.07–4.42 | 94.2–99.9 |
| cf_db | ❌ wrong-action | data | no storage scale-up | — | — | — | 0.07–0.31 (excl. incident) | 99.8 |

## Judgment

### B1 — compute scale-up benefit (cb cells): ✅ MET and robust

All 12 aligned compute replicates (cf_cb, ba_cb) show the pre-add compute saturation (PRE p50 ~2.2–3.0 s) collapsing to ~3.3 ms after the first compute add — p50 ratio 0.001–0.025, far beyond the pre-registered ≥2× threshold. Direction consistent across all 12 replicates (both seeds). G2 (edge-CPU binding), M1 (8 adds to budget, 4/LAN), M2 (added nodes served), I1, D1–D3, F2 all clean. **B1 is thesis evidence for the compute axis.**

### B2 — storage scale-up benefit (db cells): ⚠️ MECHANISM confirmed, p95-leg cell-level gate NOT met

- **Mechanism (M1/M2/V1) confirmed and reproduced**: in all 11 valid db replicates where storage was the claimed tier (sf_db 6, ba_db 5), the storage persistent reserve activated on both LANs (`[reserve] activated`, no cold spawn), storage CPU bound pre-add (V1: 66–71 % → post 42–49 %) and relieved in 10/11 (peak-CPU ratio < 0.75× on 19/22 LANs; all sf_db 12/12 LANs pass). The activated reserve served reads (M2).
- **p95-leg cell-level CI does NOT exclude 1.0** for either aligned db cell (pre-registered criterion):
  - sf_db: median 0.727, 95 % CI **[0.574, 1.393]** (includes 1.0); 3/5 seed-42 replicates pass <0.8× on the mean-of-LANs ratio.
  - ba_db: median 1.083, 95 % CI **[0.897, 13.968]** (n=4, includes 1.0); 2/4 seed-42 replicates have ratios >1.
- **Per the pre-registered rule, sf_db and ba_db do NOT pass the cell-level B2 p95 gate** (a p95-leg CI including 1.0 fails B2 even when the CPU leg passes). The CPU leg is reported as the carrying leg where it holds (sf_db: all; ba_db: lan2 all, lan1 except ba_db_6).
- **Why the p95 leg fails — two contributing, evidence-backed causes:**
  1. **Sparse completed-request tail (all db cells)**: ~0.8 % of completed requests take >10 s (p99 up to ~84 s in a 30 s bucket) with storage CPU only ~40 %. The PRE window (30–60 s, ~3–5 k requests) rarely contains a tail event; the POST window (300+ s, ~35–38 k requests) always does → a **window-length asymmetry** inflates POST p95 independent of the add. This is a measurement-contract property, not a mechanism failure.
  2. **ba post-relief compute churn (ba_db only)**: ba_db adds compute after storage relief (6 adds, storage score below threshold); each compute add coincides with a 30 s-bucket p95 spike (e.g. ba_db_3: spikes at t≈120/180/270 s matching dyn adds at 121/211/351 s; p95 up to 69 s) and elevated timeout (ba_db_3 2.65 %, ba_db_6 4.42 % vs sf_db 0.03–1.36 %). The **ba cost** — second-tier churn during a data-bound episode — is real and reproducible (2 of 5 ba_db replicates).

### Wrong-action arms (pre-registered no-benefit): ✅ judged on their claimed direction

- **cf_db** (compute-first on data-bound): compute scaled (6 adds), storage suppressed (no reserve activation in 5/5 valid), service degraded vs the aligned sf_db (episode p50 ~36–78 ms and p95 ~706–1135 ms vs sf_db p50 ~40–70 ms / p95 ~502–756 ms; cf_db compute adds gave no p50 benefit, p50 ratio 0.13–1.52×). Pre-registered no-benefit direction observed; evidence valid.
- **sf_cb** (storage-first on compute-bound): **confound resolved by the 2026-08-12/13 rerun at 0.15/0.08** (the original 0.30/0.15 allocation never bound — DF 0 % in all 6 originals — so the original service comparison was unclean). At the corrected binding config, the rerun (6/6, seeds 42×5 + 43) shows **no user-visible wrong-action cost at the tested (sub-capacity) intensity**: aggregate p50 ~3.3 ms, timeout 0.22–0.53 %, served 99.5–99.8 %, DF 8.7–9.1 % (only the first ~60 s of each episode degrades, then self-resolves). The wrong-action cost is therefore **resource-side**: the compute tier is pinned at ~61 % of the 0.15 cap in 93–97 % of episode windows with 0 compute adds (high utilization without relief), and the storage activations (0–2/run) are consistently **wasted** (no relief needed). Falsification-shaped 6/6 under §6.4 (aggregate p50 < 0.5 s, timeout < 0.65 %, DF < 15 %); the pilot outlier (DF 52 %, timeout 10.8 %) shows a binding-moment degradation is possible but not reproducible at this intensity. The pre-registered "or" (wastes resources **or** degrades service) is satisfied via resource waste; the user-service-quality leg is **not** demonstrated on the cb axis at this load.

### Base-requirements verdict per arm

| Gate | cf_cb | ba_cb | sf_cb | sf_db | ba_db | cf_db |
| --- | --- | --- | --- | --- | --- | --- |
| B (benefit) | ✅ B1 | ✅ B1 | n/a (no-benefit) | ⚠️ B2 p95 CI⊃1; CPU leg ✅ | ⚠️ B2 p95 CI⊃1; CPU leg mostly | n/a (no-benefit) |
| M1/M2 | ✅ | ✅ | n/a | ✅ | ✅ | ✅ (compute) |
| V1 | ✅ | ✅ | ✅ | ✅ | ✅ (1 LAN fail in ba_db_6) | ✅ |
| I1 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| D1/D2/D3 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ (excl. cf_db_5) |
| F2 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Verdict | ✅ evidence | ✅ evidence | ✅ evidence (no-benefit) | ✅ evidence (B2 p95-leg nuance) | ✅ evidence (B2 p95-leg nuance + ba cost) | ✅ evidence (no-benefit; excl. cf_db_5) |

## Root Causes

| # | Issue | Impact | Status |
| --- | --- | --- | --- |
| 1 | **MEMCG OOM of edge compute nodes** — `ba_db_2` (256 MB cap, 1 kill) and `cf_db_5` (512 MB cap, 2 kills: dyn3@338 s, dyn5@532 s; anon-RSS ~462–463 MB at kill). Cascade: failed netns/veth cleanup → data-plane disruption → mass timeouts (cf_db_5 47.7 % in one 30 s bucket) → false-underutilization churn. | 2 runs excluded (D2 hard gate); ~7.7 GB transients freed. The 512 MB raise reduced but did **not** eliminate the OOM. | Confirmed (dmesg CONSTRAINT_MEMCG in both). Platform follow-up: raise cap / fix memory accounting. |
| 2 | **Sparse completed-request tail (~0.8 % >10 s)** in data-bound episodes (all db cells, storage CPU ~40 %). Inflates long-window POST p95; source not yet isolated (driver stall / Mongo read path / WAN). | Distorts the B2 p95 leg (PRE vs POST window-length asymmetry). | Hypothesis-level; needs a targeted probe run. |
| 3 | **ba post-relief compute churn** injects tail spikes + elevated timeouts on db (ba_db_3, ba_db_6). | The ba arm's p95 benefit is not robust; ba_db timeout 4.42 % worst-case. | Confirmed (compute-add timing vs spike buckets). Designed ba cost, not an incident. |

## Next Actions

1. **Reframe the B2 claim** for the thesis: the storage reserve **mechanism** (activation, CPU relief, no cold spawn) is reproduced (n=11), but the pre-registered cell-level p95-benefit gate is **not** met — the claim must rest on the CPU-relief leg + tail behavior, or the p95 window contract must be re-examined (tail contamination).
2. **Platform hardening**: raise/verify the edge `EDGE_MEMORY` cap (or fix memory accounting) — 2 OOM incidents bracket the phenomenon at 256 MB and 512 MB.
3. **Tail investigation**: isolate the ~0.8 % >10 s completed-request source (probe with storage-CPU-capped windows).
4. **sf_cb confound → resolved (2026-08-13)**: the 0.30→0.15 rerun at the corrected config confirms the **resource-waste-only** framing — no user-visible wrong-action cost at the tested sub-capacity intensity (DF 8.7–9.1 %; compute tier ~61 % of cap without relief). If the thesis requires the strongest wrong-action form (user QoE collapse on the cb axis), a capacity-exceeding probe (heavier `service_pressure` limit / lower `EDGE_CPUS`) is the pre-registered next step — not required for the claim as stated (the "or" is satisfied via resource waste; cf_db already carries the service-degradation leg on the db axis).
5. Cross-mode comparison graphs archived (`graphs/comparison/`, 19 PNGs); per-run graphs archived (`graphs/<run_timestamp>/`, 350 PNGs); campaign dataset + synthesis CSVs in `analysis/`.

## Changelog

| Date | Change | Rationale |
| --- | --- | --- |
| 2026-08-09 | Initial results.md for the v3 campaign (36 runs; 34 valid after 2 OOM exclusions). | Per-run analysis, cell-level B2/B1 synthesis, arm narrative. |
| 2026-08-09 | `cf_db_5` re-classified as MEMCG OOM incident (2 kills @512 MB) and excluded from the cf_db pool. | D2 hard-gate violation; same mechanism as `ba_db_2`. |
| 2026-08-13 | sf_cb rerun @0.15/0.08 incorporated (6 runs), DF/DT-p50 criteria added (§6.1a), dataset rebuilt (34 rows), comparison graphs regenerated; original sf_cb@0.30 rows marked superseded. | Resolve the 0.30 confound; the rerun shows no user-visible wrong-action cost at the tested intensity — resource-waste + high-utilization-without-relief framing. |
| 2026-08-13 | Recreated the lost B1/B2 ratio-figure generator as `tools/rq2_v3_ratio_graphs.py` and regenerated `b1_p50_ratio`, `b2_cpu_ratio`, `b2_p95_ratio`, `b2_pre_post_p95` from the rebuilt 34-run dataset. | The ad-hoc 08-09 generator was never saved; recreated for provenance consistency — sf_cb@0.15 has B1 N/A (no compute add) and the db cells are unchanged, so content is unchanged but provenance now matches the rebuilt dataset. |
