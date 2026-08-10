# RQ3 v2 — Run Matrix

**Date**: 2026-08-05 · **Plan**: `rq3_v2_rework_plan.md` §2.9/§4 Phase 5.1 · **Status**: ✅ **COMPLETE** — 18/18 runs green on `cloud-vm-rq3` (2026-08-04 23:33 – 2026-08-05 05:05 UTC)

> **2026-08-05 amendment (user-approved, 24 h budget):** replicates raised to
> **n=6 per mode** — `direct` × 6, `discovery` × 6, `discovery_15` × 6 =
> **18 runs** (was 13). Primary blocks 6 of 2 (seeds 2001–2006); sensitivity
> `disc15` × 6 (seed 2007). Counterbalance order generated deterministically
> by `tools/gen_rq3_counterbalance.py` and recorded in
> `counterbalance_order_v2.csv`. Runtime ≈ 6–7.5 h + ≤ 3 voids — comfortably
> within the 24 h window.

## 1. Campaign

- **Cells**: `direct` × 6, `discovery` × 6, `discovery_15` × 6 = **18 runs**.
- **Primary blocks**: 6 blocks of 2 (`direct`/`discovery`), block seeds
  2001–2006, within-block order sampled per block seed (generator:
  `tools/gen_rq3_counterbalance.py`).
- **Sensitivity block**: `discovery_15` × 6, seed 2007, run consecutively
  after the primary blocks in the same VM session.
- **Counterbalance verification**: each arm leads ≥ 2 of 6 blocks, no
  systematic first-position bias; if the sampled orders fail, the block seeds
  are **resampled deterministically** (increment seed until the constraint
  holds) and the final seed set recorded here. Generated order: **disc leads
  4 blocks, direct leads 2** (both ≥ 2 ✓).
- **Orders**: written to `counterbalance_order_v2.csv` (never overwrite an
  existing file). Void re-runs take the void's matrix position (marked
  `void`/`replacement` + seed); ≤ 1 void per cell.
- **Run suffixes**: `direct` / `disc` / `disc15`; labels `rq3_direct_N` /
  `rq3_disc_N` (N = block) / `rq3_disc15_N` (N = 1..6).

## 2. Launch contract

```text
TRAFFIC_DRIVER_MODE=open_loop CURL_MAX_TIME=300 INFLIGHT_WINDOW=1024 DRAIN_S=30
```

- Arm env: `env/rq3_direct.env` (with `EDGE_APP_READY_EVENT=1`,
  `READINESS_EVENT_FALLBACK_S=5.0`), `env/rq3_discovery.env`,
  `env/rq3_discovery_15.env` (`DISCOVERY_POLL_INTERVAL_S=15.0`).
- Env files synced to `cloud-vm-rq3:~/rq3_env/` before the campaign.

## 3. Matrix (generated order — `counterbalance_order_v2.csv`)

| Block | Seed | Run 1 | Run 2 | Result (Check C) | Notes |
|---|---|---|---|---|---|
| B1 | 2001 | `rq3_disc_1` ✅ | `rq3_direct_1` ✅ | 0.98 / 0.88 | disc leads; +repl 0.91 (extra) |
| B2 | 2002 | `rq3_disc_2` ✅ | `rq3_direct_2` ✅ | 1.00 / 0.96 | disc leads |
| B3 | 2003 | `rq3_disc_3` ✅ | `rq3_direct_3` ✅ | 0.98 / 0.92 | disc leads |
| B4 | 2004 | `rq3_disc_4` ✅ | `rq3_direct_4` ✅ | 0.97 / 0.89 | disc leads |
| B5 | 2005 | `rq3_direct_5` ✅ | `rq3_disc_5` ✅ | 0.93 / 0.98 | direct leads |
| B6 | 2006 | `rq3_direct_6` ✅ | `rq3_disc_6` ✅ | 0.88 / 1.00 | direct leads |
| B7 | 2007 | `rq3_disc15_1` ✅ | `rq3_disc15_2` ✅ | 1.00 / 1.00 | sensitivity |
| B7 | 2007 | `rq3_disc15_3` ✅ | `rq3_disc15_4` ✅ | 1.01 / 1.00 | sensitivity |
| B7 | 2007 | `rq3_disc15_5` ✅ | `rq3_disc15_6` ✅ | 1.00 / 0.99 | sensitivity |

**All 18 runs exit 0, Checks A/B/D PASS, Check C ≥ 0.85 (amended gate).**
Per-mode Check C (scheduled cells):
- **direct (n=6):** 0.88 / 0.88 / 0.89 / 0.92 / 0.93 / 0.96 (+ extra 0.91)
- **discovery (n=6):** 0.98 / 1.00 / 0.98 / 0.97 / 0.98 / 1.00 — all ≥ 0.97
- **discovery_15 (n=6):** 0.99 / 1.00 / 1.00 / 1.00 / 1.00 / 1.01

> **Gate amendment (2026-08-05, user-approved option 1, pre-registered before
> continuing):** Check C hard threshold lowered **0.9 → 0.85** (`rq3_flow_validation.py`,
> plan §2.8, preflight G4, measurement contract G4). **Justification — corrected
> post-campaign (see `post_run_analysis.md` §3.3.8):** the direct-arm Check C
> shortfall tracks the http=000 failed-connect fraction almost exactly
> (per-run 4–12 % vs 4–12 %; discovery/disc15 shortfall only 0–3 % with zero
> 000s). Failed connects never emit `request_complete`, so they never produce a
> flow-delete yet are "completed" denominator rows — the low direct coverage is
> a denominator artifact of the treatment's own handover-window failed connects
> (which have no flow to delete), not the originally stated "~10–14 % orthogonal
> telemetry delivery loss" (the true residual delivery loss is ~2–3 %). The
> amended 0.85 gate stands: for established connections, delivered
> `request_complete` → delete is 1:1. Applies **retroactively**: B1-R2
> `rq3_direct_1` (0.88) and B4-R2 `rq3_direct_4` (0.89) are **valid** runs.

> **Replacement note** — `rq3_direct_1` replacement (fresh seed 2011, run
> `20260805_000344_rq3_direct_1`, Check C 0.91) was launched under the old 0.9
> gate; with the amendment the original B1-R2 run (0.88) is valid, so the
> replacement is recorded as an **extra direct replicate** (kept in the run
> artifacts; primary analysis uses the 6 scheduled direct cells B1–B6).
> Scheduled direct Check C distribution: **0.88 / 0.88 / 0.89 / 0.92 / 0.93 /
> 0.96** (+ extra 0.91) — all ≥ 0.85 valid. **Campaign complete 2026-08-05.**

*(Order sampled deterministically from each block seed by
`tools/gen_rq3_counterbalance.py`; arm-leading check: disc=4, direct=2 — both
≥ 2 ✓. Launch env per cell: `env/rq3_direct.env` for `direct`, `env/rq3_discovery.env`
for `disc`, `env/rq3_discovery_15.env` for `disc15`.)*

---

## 5. Post-hoc boundary probe — `rq3_probe` (2026-08-05, user-approved)

**Declared AFTER the 18-run campaign, explicitly post-hoc (non-pre-registered).**
Motivation: the campaign's gap-window consequence is null because the calibrated
spike (3.0 req/s/client → 18 req/s aggregate) leaves old backends at ~9–15 % CPU
(~10× headroom). The probe raises load toward real CPU saturation to locate
whether the quantization consequence materializes, and to quantify direct's
handover (http=000) cost at load. The pre-registered 18-run campaign and its
conclusions are **unchanged**; the probe is analyzed separately.

- **Objective:** locate the consequence boundary (gap-window old-backend
  `timeout_rate`/`failure_rate` > 0) under CPU saturation; measure direct
  http=000 fraction vs load. Boundary-locating → descriptive + Cliff's delta.
- **Arms:** `direct` + `discovery` (primary pair; `disc15` excluded).
- **Rate ladder (per client, 6 clients):** P1 8.0 (window 3072) → P2 12.0
  (window 4096) → P3 15.0 (window 6144). `INFLIGHT_WINDOW` raised per the
  pre-registered decision rule (`rate × 300 ≤ window`; RQ1 g2 rate15 precedent
  on the same VM: CPU p90 ≈ 73 %, max ≈ 96 %). 1 calibration run per arm per
  step. Escalate if old-backend CPU < 70 % AND no gap-window timeouts.
- **Stop rule:** stop when (a) gap-window `timeout_rate` > 0 in either arm
  (boundary found); or (b) `dropped` > 1 % despite the raised window (driver
  ceiling); or (c) rate 15 reached with no consequence (envelope ceiling).
- **Probe cell:** n = 3 per arm at the final rate, alternating, labels
  `rq3_probe_direct_N` / `rq3_probe_disc_N`, run consecutively on
  `cloud-vm-rq3`. Same env (`rq3_direct.env`/`rq3_discovery.env`), same
  workload phases (spike `rate_per_client` = probe rate), same analyzer.
- **Deliverables (separated):** `_rq3_probe_summary.csv`, probe graphs
  (`gap_timeout_vs_rate`, `http000_vs_rate`), `post_run_analysis.md` §5,
  thesis conclusion update. `phases_rq3_compute_episode.json` restored to 3.0
  after the probe.

Probe run log (calibration ladder → probe cell):

| Step | rate/client | window | arm | run id | result |
|---|---|---|---|---|---|
| P1 | 8.0 | 3072 | direct | `20260805_181641_rq3_probe_p1_direct` | null (gap_to 0.000, useful 1.000, 0×000, CPU ~25 %) |
| P1 | 8.0 | 3072 | discovery | `20260805_183014_rq3_probe_p1_disc` | null (gap_to 0.000, useful 1.000, 0×000, CPU ~24 %) |
| P2 | 12.0 | 4096 | direct | `20260805_184258_rq3_probe_p2_direct` | null (gap_to 0.000, useful 1.000, 0×000, CPU ~36 %) |
| P2 | 12.0 | 4096 | discovery | `20260805_190300_rq3_probe_p2_disc` | null (gap_to 0.000, useful 1.000, 0×000, CPU ~35 %) |
| ~~P3~~ | ~~15.0~~ | — | — | **bypassed** | user decision (2026-08-05): jump straight to the saturation extreme |
| ~~P4~~ | ~~20.0~~ | — | — | **bypassed** | user decision: jump straight to the saturation extreme |
| P5 | 25.0 | 10240 | direct | `20260805_191557_rq3_probe_p5_direct` | null (gap_to 0.000, useful 1.000, 0×000); CPU 44.9/61.7 %; **driver delivery caps at ~100-120 req/s (~65-80 % of nominal 150)**; canceled 4 % (drain); latency p99 1.2-2.9 s — the system limit is the driver, not the compute |
| P5 | 25.0 | 10240 | discovery | `20260805_193013_rq3_probe_p5_disc` | **null at CPU saturation** (gap_to 0.000, gap_fr 0.000, useful 1.000, 0×000); **CPU 61.6/79.1/88.1 %** (discovery later admission → old backends carry the ceiling load → ~30 pp higher CPU than direct); scale→1st 5.19 s vs direct 2.91 s; canceled 10.7 % (drain); **no gap-window consequence even at true old-backend saturation** |
| ~~cell~~ | ~~25.0~~ | ~~10240~~ | ~~direct ×2~~ | `rq3_probe_cell_direct_1/2` (seeds 2207/2209) | **ABANDONED** after the rate-25 discovery voids (see note below); `cell_direct_1` (seed 2207) PASSED: null (gap 0.000, useful 1.000, 0×000), CPU ~72-75 %, canceled 20.6 % (drain) — retained as envelope-boundary observation |
| ~~cell~~ | ~~25.0~~ | ~~10240~~ | ~~discovery ×2~~ | `rq3_probe_cell_disc_1/2r` (seeds 2208/2211) | **ABANDONED** — `cell_disc_1` and replacement `cell_disc_1r` both **VOID**: flow-validation Check D DEGRADED (>50 % unknown source ports), caused by the **driver drain-cancel collapse (~50 % canceled)** at rate 25, not genuine flow-isolation violations (0 reuse) — retained as envelope-boundary evidence |
| ~~cell~~ | ~~16.0~~ | ~~6144~~ | ~~direct ×2~~ | `rq3_probe_cell16_direct_1` (seed 2212) | **ABANDONED** — `cell16_direct_1` **VOID**: Check D DEGRADED (62.5 % unknown ports), **canceled 43.7 %** — the driver drain-cancel collapse onset is between rate 12 and 16 (not only at 25); 0 dropped / 0 http=000 / null consequence retained as beyond-envelope evidence |
| cell | 12.0 | 4096 | direct (×6 total) | `P2` + `cell12_direct_1..5` (seeds 2203/2216/2218/2220/2222/2224) | **all 6 ✅ null, clean** — gap_to 0.000, useful 1.000, 0×000, CPU 31.6–37.4 %, canceled ≤ 0.39 %; scale→1st 1.85–2.30 s (med 2.17) |
| cell | 12.0 | 4096 | discovery (×6 total) | `P2` + `cell12_disc_1..5` (seeds 2204/2217/2219/2221/2223/2225) | **all 6 ✅ null, clean** — gap_to 0.000, useful 1.000, CPU 32.5–38.0 %, canceled ≤ 0.46 %; scale→1st 4.72–7.67 s (med 6.01); `cell12_disc_4` has 2×http=000 = slow `cleanup_gap` rows (not the fast-fail artifact) |

> **Cell n raised to n=6/arm (user-approved 2026-08-06):** the rate-12 clean
> high-load cell is extended to **n=6/arm** (8 additional runs) so that (a) the
> timing-under-load claim (direct scale→first ~2.2 s vs discovery ~6.7-9.5 s,
> full separation) can be tested with an exact MWU at n=6/arm — expected
> p=0.0022 if separation holds — matching the campaign's n=6 convention, and
> (b) the consequence null rests on 6×6 all-zero runs. Alternating order;
> seeds 2218-2225. Phases restored to 3.0 after the cell.

**Probe COMPLETE (2026-08-05):** n=2/arm at rate 12 (the highest consistently-clean rate), all gates pass, consequence null on every probe run at every rate (8/12/25). Rates 16-25 are beyond the driver's clean-delivery envelope (drain-cancel collapse → flow-validation void), documented as the platform's measured limit. Deliverables: `rq3_probe_summary.csv`, `graphs/probe/*.png` (9 figures: 8 vs-rate + rate-12 cell, added 2026-08-06), `post_run_analysis.md` §5.

**Cell COMPLETE (2026-08-06):** the rate-12 cell is now **n=6/arm** — 8 additional runs (seeds 2218–2225, all exit 0, all gates pass; run IDs `20260806_022046..034852_rq3_probe_cell12_{direct,disc}_{2..5}`). Timing-under-load is now **statistically significant**: scale→first med **2.17 s direct vs 6.01 s discovery**, **exact MWU p = 0.0022, Cliff's d = −1.000** (full separation); consequence null rests on 6×6 all-zero runs (p = 1.000). `rq3_probe_summary.csv` regenerated (17 runs), 8 probe graphs re-plotted + new `rate12_cell_timing.png` cell figure, phases restored to 3.0, launcher/temp scripts cleaned.

> **Cell-rate adjustment 2 (user-approved 2026-08-05):** the rate-16 cell was
> **abandoned** after `cell16_direct_1` voided with the same driver drain-cancel
> collapse (canceled 43.7 %, Check D >50 % unknown) — the collapse onset is
> between rate 12 and 16. The formal cell moves to **rate 12** (window 4096,
> the highest consistently-clean rate: 0.4 % canceled, all gates pass at
> n=1/arm in the P2 ladder). Cell = 1 more run per arm (n=2/arm total at rate
> 12). Rates 16/25 are retained as labeled **beyond-envelope boundary
> observations** (driver delivery collapse = the platform's practical limit;
> consequence remains null up to and at the edge of that collapse).

> **Ladder adjustment (user-approved 2026-08-05):** after P2 (rate 12) showed a
> clean null (0 dropped / 0 http=000, CPU ~35 %) with linear CPU scaling, the
> user directed a **direct jump to P5 (rate 25)** to find the limit fast;
> P3 (15) and P4 (20) are **bypassed** (recorded, not run). Rate 25 exceeds
> the RQ1-g2-demonstrated envelope (15) — a genuine limit probe (dropped or
> conntrack ceiling is itself an answer).

> **Ladder extension (user-approved 2026-08-05, post-hoc):** P1 measured CPU
> ~24–25 % at rate 8 (RQ3 workload reaches CPU far slower than RQ1 g2's
> rate15 precedent). Per the approved escalation rule (CPU < 70 % and no gap
> timeouts → escalate), the ladder is extended beyond P3 to P4 (rate 20,
> window 8192) and P5 (rate 25, window 10240) to reach actual CPU saturation
> (~70–90 %), where the consequence boundary can materialize. Conntrack:
> 6 × 10240 ≈ 61k < 65536 (feasible).

## 4. Runtime estimate

~20–25 min/run (60+180+180 = 420 s workload + 4 × 30 s drains + spawn/setup/
teardown). 18 runs ≈ 6–7.5 h + up to 3 void re-runs (≈ +1–1.5 h). Calibration
and pre-flight are complete (2026-08-04/05). **Well under the 24 h window**
available for the campaign.

> The 4–6 run pre-flight/calibration estimate does **not** include Stage-5
> fallback-chain re-runs (R1/R2 re-tuning) — budget up to +2–3 runs if the
> first calibration rate is not feasible (see `rq3_preflight.md` §8).

---

## 6. Fixed-image validation campaign — `rq3_camp` (2026-08-06, post-fix)

**Declared AFTER the servability fix** (`edge_server/source/app.py` now binds
via `make_server` *before* firing `app_ready`, so readiness = servability).
Purpose: re-run the primary pair under a corrected harness to confirm the RQ3
claims without the direct-arm http=000 handover artifact, and to quantify the
residual container-bind stall (measured per backend) so it can be controlled
statistically. Same canonical config as the 18-run campaign — **rate 3.0
req/s/client, `INFLIGHT_WINDOW=1024`, `DRAIN_S=30`, n=6/arm = 12 runs**,
seeds **2310–2321**, fixed+instrumented image `638e3efdcdc5`, default
`EDGE_CPUS=0.30`, same 4-step per-run reset launcher.

| # | label | seed | arm | run id | result |
|---|---|---|---|---|---|
| 1 | `rq3_camp_direct_1` | 2310 | direct | `20260806_105929` | ✅ scale→1st 11.146 s (bind-dominated) |
| 2 | `rq3_camp_direct_2` | 2311 | direct | `20260806_111204` | ✅ 2.130 s (all fast-bind) |
| 3 | `rq3_camp_direct_3` | 2312 | direct | `20260806_112415` | ✅ 11.173 s |
| 4 | `rq3_camp_direct_4` | 2313 | direct | `20260806_113633` | ✅ 7.202 s (mixed bind) |
| 5 | `rq3_camp_direct_5` | 2314 | direct | `20260806_114830` | ✅ 11.660 s |
| 6 | `rq3_camp_direct_6` | 2315 | direct | `20260806_120030` | ✅ 11.339 s |
| 7 | `rq3_camp_disc_1` | 2316 | discovery | `20260806_121237` | ✅ 19.564 s |
| 8 | `rq3_camp_disc_2` | 2317 | discovery | `20260806_122433` | ✅ 18.373 s |
| 9 | `rq3_camp_disc_3` | 2318 | discovery | `20260806_123629` | ✅ 17.115 s |
| 10 | `rq3_camp_disc_4` | 2319 | discovery | `20260806_124902` | ✅ 18.153 s |
| 11 | `rq3_camp_disc_5` | 2320 | discovery | `20260806_130131` | ✅ 13.274 s |
| 12 | `rq3_camp_disc_6` | 2321 | discovery | `20260806_131400` | ✅ 17.367 s |

**All 12 runs exit 0, non-void, 0×http=000, `useful_share=1.000`,
flow-validation A/B/C/D pass** (47 backends). Analysis:
`tools/rq3_stratified_analysis.py` (per-backend bind + readiness→admission +
spawn→first, bind-stratified), graphs `graphs/campaign_fixed/`, per-backend
CSV `graphs/campaign_fixed/campaign_stratified_per_backend.csv`. Results:
`results.md` §8, `post_run_analysis.md` §6. Note: `EDGE_CPUS=1.0` was tried
in one diagnostic run (`rq3_binddiag_disc_1`, seed 2303) and **rejected** —
it suppresses compute scale-up entirely (void), so the default 0.30 is
retained.

**Supporting validation/diagnostic runs (2026-08-06, pre-campaign):**

| label | seed | purpose | outcome |
|---|---|---|---|
| `rq3_fixval_direct_1` | 2301 | fix validation pair (direct) | ✅ 0×000, useful_share 1.000; 3/4 backends slow-bind |
| `rq3_fixval_disc_1` | 2302 | fix validation pair (discovery) | ✅ 0×000, useful_share 1.000; 4/6 slow-bind |
| `rq3_binddiag_disc_1` | 2303 | `EDGE_CPUS=1.0` knob test | ❌ **void** (0 compute backends — knob suppresses scale-up) |
| `rq3_binddiag2_disc_1` | 2304 | instrumented bind-timing diagnostic | ✅ 2/4 slow-bind, `bind-timing` evidence captured |

These are diagnostic/validation runs, not campaign cells; the fixval pair is
the pre-campaign proof that the servability fix eliminated http=000, and the
binddiag runs produced the `bind-timing` instrumentation evidence used by
the stratified analysis.
