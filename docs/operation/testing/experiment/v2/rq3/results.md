# RQ3 v2 — Results

**Date**: 2026-08-05 (updated 2026-08-06) · **Plan**: `rq3_v2_rework_plan.md` · **Status**: ✅ **campaign complete** — 18 scheduled runs + 1 extra on `cloud-vm-rq3`, plus a **12-run fixed-image validation campaign** (2026-08-06, §8)

## 1. Timeline

| Date | Event |
|---|---|
| 2026-08-04 | RQ3 v2 rework plan approved (approach A); Phases 1–3 + env regimes implemented; selftests passing |
| 2026-08-04/05 | Calibration (direct/discovery) + G1–G4 arming gates green |
| 2026-08-05 | **Check C gate amended 0.9 → 0.85** (user-approved, pre-registered; justification later corrected — see `post_run_analysis.md` §3.3.8) |
| 2026-08-04 23:33 – 08-05 05:05 | **18-run campaign** (direct ×6, discovery ×6, discovery_15 ×6) + 1 extra direct replicate; all exit 0 |
| 2026-08-05 | Per-run analysis (`rq3_admission_analysis.py`, `rq3_flow_validation.py`), 14 comparison graphs, stats (`tools/rq3_campaign_stats.py`), post-run analysis written + reviewed |

## 2. Per-arm tables (run-level medians, `rq3_admission_analysis.py --csv`, extra replicate excluded)

| Arm | n (non-void) | gap_timeout median | gap_failure median | useful_share median | scale→1stok median (s) | start→admit median (s) | event_fraction |
|---|---|---|---|---|---|---|---|
| direct | 6 (5 for gap) | 0.000 | 0.000 | 0.739 | 10.963 | 0.170 | 1.000 |
| discovery | 6 | 0.000 | 0.000 | 1.000 | 11.454 | 9.619 | 0.0 |
| discovery_15 | 6 | 0.000 | 0.000 | 1.000 | 16.969 | 15.222 | 0.0 |

## 3. Primary pair — direct vs discovery

| Metric | med direct | med discovery | MWU p (exact) | Cliff's δ | supports headline |
|---|---|---|---|---|---|
| gap_timeout_rate | 0.000 | 0.000 | 1.000 | +0.000 | neutral (null) |
| gap_failure_rate | 0.000 | 0.000 | 1.000 | +0.000 | neutral (null) |
| useful_share | 0.739 | 1.000 | 0.0022 | −1.000 | direct **worse** |
| scale→usable-capacity | 10.963 | 11.454 | 0.132 | −0.556 | direct better (NS, <0.6) |
| spawn→admitted (manip.) | 0.170 | 9.619 | 0.0022 | −1.000 | quantization **met** |

**Consistency rule (≥ 2 of 3 supporting in the same direction):** ☐ met ☑ **mixed/ambiguous**
(neutral null / direct-worse / direct-better → 1–1–1; headline consequence null is pre-registered-acceptable)

## 4. Sensitivity — discovery vs discovery_15 (Cliff's delta only, descriptive)

| Metric | med disc10 | med disc15 | Cliff's δ |
|---|---|---|---|
| gap_timeout_rate | 0.000 | 0.000 | +0.000 |
| spawn→admitted | 9.619 | 15.222 | −0.444 |
| scale→usable-capacity | 11.454 | 16.969 | −0.444 |

Quantization cost scales with the poll period (descriptive; p = 0.24).

## 5. Manipulation / validity

- Quantization `direct` ≤ `discovery`: ☑ **met** (0.170 ≤ 9.619, full separation, p = 0.0022)
- `admitted → first_flow` arm-identical: ☐ **NOT met** — direct 10.044 s vs discovery 0.826 s (p = 0.0022); unanticipated, see `post_run_analysis.md` §3.3.5
- Event-fraction ≥ 0.80 in direct runs: ☑ **met** (1.000 in all 6 direct runs; no instrumentation-degraded runs)
- Flow-validation gates (A/B/C/D) per run: ☑ **all 18 pass** (A/B/D hard; C ≥ 0.88 ≥ 0.85 amended gate)
- Readiness-criterion identity (post-admission probe): ☑ (per `measurement_contract.md` §0; unchanged readiness criterion across arms)
- Unanticipated direct-only artifact: http=000/`backend_id=unknown` fast-fails 162–428/run (4.6–12 % of offered), zero in discovery/disc15 — drives Check C shortfall and useful_share gap (`post_run_analysis.md` §3.3.6–8)

## 6. Judgment

**Headline (timing quantization): CONFIRMED.** Event-driven admission (`direct`)
admits new capacity at 0.17 s vs 9.62 s (discovery) and 15.22 s (disc15) —
~57×/90× faster, exact MWU p = 0.0022, Cliff's d = −1.0 (full separation over
6 independent seeds). The quantization tail scales with the poll period
(descriptive, d = −0.44), confirming the mechanism is the poll, not the host.

**Consequence (gap-window service quality): NULL, pre-registered-acceptable.**
gap `timeout_rate` and `failure_rate` are 0.000 on every defined run of every
arm (p = 1.0). Old backends absorb the gap at the calibrated 3.0 req/s spike;
there is no between-arm service differential in the gap window. The supporting
set is **mixed/ambiguous** (1–1–1): useful_share significantly favors discovery
(0.74 vs 1.0, driven by a direct-only fast-fail artifact, not old-backend
timeouts), scale→usable-capacity directionally favors direct (0.49 s median,
p = 0.13), gap_failure is null.

**Unanticipated but robust finding (direct-only handover cost):** direct's
ultra-early admission (event-driven, ~0.1 s) outruns the data path — 17/24
direct backends wait ~10 s for their first attributed request (refresh-phase
dependent), during which 4.6–12 % of offered requests fail fast
(http=000, `backend_id=unknown`, sub-10 ms mostly), in every direct run and
zero in discovery/disc15. This artifact also explains the direct Check C
shortfall (failed connects emit no `request_complete`), correcting the gate
amendment's original "orthogonal delivery loss" justification (true residual
delivery loss ~2–3 %).

**Bottom line for the thesis:** readiness-propagation determines elastic
scale-up **timing** (strong, significant); it does not determine gap-window
**service quality** at the calibrated load (null), but event-driven admission
carries a small transient handover-window availability cost that polling-based
discovery avoids. Detailed evidence: `post_run_analysis.md`, `graphs/comparison/*.png`.

## 7. Post-hoc boundary probe (2026-08-05, declared post-hoc)

To address the under-saturation objection (the campaign null was measured at
3 req/s/client, ~10 % old-backend CPU), a declared boundary probe re-ran the
same comparison at rates **8 / 12 / 25** req/s/client (windows 3072 / 4096 /
10240), then a clean high-load cell at **rate 12**, extended to **n=6/arm**
(2026-08-06, 8 additional runs, seeds 2218–2225). Result:
**consequence null at every load** — gap `timeout_rate`/`failure_rate` 0.000
and useful_share 1.000 on all **17 valid probe runs**; the discovery arm reached
**88 % max old-backend CPU** with zero gap-window timeouts. The practical limit
is the **open-loop driver's delivery ceiling** (~100-120 req/s aggregate): at
rate 16 canceled jumps to 43.7 %, at rate 25 to 4-50 % (run-dependent),
tripping the flow-isolation gate (Check D voids `cell_disc_1/1r`,
`cell16_direct_1`). Timing persists at every load, and at the **n=6/arm
rate-12 cell it is statistically significant**: scale→first median **2.17 s
(direct) vs 6.01 s (discovery)**, full separation, **exact two-sided MWU
p = 0.0022, Cliff's d = −1.000**; the consequence null at rate 12 rests on
6×6 all-zero runs (p = 1.000). No http=000 in any probe run except 2 slow
`cleanup_gap` rows in `cell12_disc_4` (the benign pattern, not the campaign
fast-fail artifact). **Root cause (2026-08-06):** the campaign's direct-arm
http=000 / ~10 s handover is the edge app's intermittent Werkzeug dev-server
bind delay — the `app_ready` event fires on a MongoDB-ping predicate up to
~10 s before the HTTP server binds — a harness artifact, not a propagation
cost (the probe backends happened to bind instantly). The same delay
intermittently contaminates RQ1/RQ2 runs (no readiness gate). Fix applied in
`edge_server/source/app.py` (bind before readiness; image rebuilt and
smoke-verified). Full analysis:
`post_run_analysis.md` §5; evidence: `rq3_probe_summary.csv`, `graphs/probe/*.png`.
**Refined 2026-08-06:** instrumented fixed-image campaign evidence (§8.2,
`post_run_analysis.md` §4/§6) shows the ~10 s stall is in the **raw socket
`bind()`/`listen()`** path (persists with `make_server`; not the dev server),
a shared infra cost controlled statistically in §8.

**Updated thesis verdict:** readiness-propagation determines elastic scale-up
timing (strong, significant, persistent under load); the service consequence is
null **up to the platform's measured practical limit** (~100-120 req/s
aggregate, ~88 % old-backend CPU), beyond which the open-loop driver's own
delivery collapses — the null is no longer dismissible as under-saturation.

## 8. Fixed-image validation campaign (2026-08-06, post-fix)

To re-evaluate RQ3 under a corrected harness (the `app_ready` event can no
longer precede servability — the edge now binds before firing readiness), the
primary pair was re-run at the canonical rate **3.0 req/s/client, n=6/arm**
(**12 runs**, seeds 2310–2321, `20260806_10*/11*/12*/13*_rq3_camp_{direct,disc}_{1..6}`,
fixed+instrumented image `638e3efdcdc5`, default `EDGE_CPUS=0.30`). All 12 runs
exit 0, non-void, **0×http=000 fast-fails**, `useful_share=1.000`,
flow-validation A/B/C/D pass (47 backends across both arms).

### 8.1 Run-level medians

| Run (seed) | arm | start→admit (s) | scale→1stok (s) | gap_to/gap_fr | useful_share |
|---|---|---|---|---|---|
| `camp_direct_1` (2310) | direct | 10.056 | 11.146 | 0.000/0.000 | 1.000 |
| `camp_direct_2` (2311) | direct | 0.489 | 2.130 | 0.000/0.000 | 1.000 |
| `camp_direct_3` (2312) | direct | 10.100 | 11.173 | 0.000/0.000 | 1.000 |
| `camp_direct_4` (2313) | direct | 5.226 | 7.202 | 0.000/0.000 | 1.000 |
| `camp_direct_5` (2314) | direct | 10.075 | 11.660 | 0.000/0.000 | 1.000 |
| `camp_direct_6` (2315) | direct | 10.123 | 11.339 | 0.000/0.000 | 1.000 |
| `camp_disc_1` (2316) | discovery | 18.000 | 19.564 | 0.000/0.000 | 1.000 |
| `camp_disc_2` (2317) | discovery | 16.952 | 18.373 | 0.000/0.000 | 1.000 |
| `camp_disc_3` (2318) | discovery | 15.472 | 17.115 | 0.000/0.000 | 1.000 |
| `camp_disc_4` (2319) | discovery | 16.660 | 18.153 | 0.000/0.000 | 1.000 |
| `camp_disc_5` (2320) | discovery | 11.799 | 13.274 | 0.000/0.000 | 1.000 |
| `camp_disc_6` (2321) | discovery | 15.809 | 17.367 | 0.000/0.000 | 1.000 |

### 8.2 Bind-stratified analysis (`tools/rq3_stratified_analysis.py`)

The edge's raw `socket.bind()`/`listen()` intermittently stalls ~10 s under
active-run network-namespace churn (final root cause, `post_run_analysis.md`
§6) — a shared infra cost, random per backend, hitting both arms
(fast-bind <1 s vs slow-bind ≥5 s strata). Because the stall is **measured per
backend** (instrumented `bind-timing` log line), the arms are compared
**within bind strata** — controlling for the measured confounder:

**PRIMARY — readiness→admission (mechanism, bind-independent):**

| stratum | direct (n) | discovery (n) | MWU p | Cliff's d |
|---|---|---|---|---|
| all | 0.001 s (23) | 6.984 s (24) | <0.0001 | −1.000 |
| fast-bind | 0.001 s (7) | 7.305 s (7) | 0.0006 | −1.000 |
| slow-bind | 0.000 s (16) | 6.768 s (17) | <0.0001 | −1.000 |

**END-TO-END — spawn→first success (bind-controlled):**

| stratum | direct (n) | discovery (n) | MWU p | Cliff's d |
|---|---|---|---|---|
| all | 11.272 s (23) | 17.698 s (24) | 0.0005 | −0.594 |
| fast-bind | 1.687 s (7) | 9.164 s (7) | 0.0006 | −1.000 |
| slow-bind | 11.461 s (16) | 18.282 s (17) | <0.0001 | −1.000 |

### 8.3 Judgment (fixed-image campaign)

- **The direct-arm http=000 / handover artifact is GONE** — 0 fast-fails in
  47 backends; `useful_share=1.000` in every run (the pre-fix direct `0.739`
  share gap was the artifact, not the mechanism).
- **Mechanism claim re-confirmed cleanly**: event-driven admission is
  ≈7000× faster than polling on readiness→admission (median 0.001 vs 6.98 s,
  d = −1.000 in every stratum).
- **End-to-end claim now holds**: spawn→first is significantly faster for
  direct even pooled (p = 0.0005, d = −0.594), and d = −1.000 within both
  bind strata — on fast-bind backends direct serves a client **1.69 s vs
  9.16 s** after spawn; on slow-bind **11.46 vs 18.28 s**. The residual
  ~10 s bind stall is a **shared, documented infra cost** that no longer
  masks the differential once controlled for.
- Evidence: `graphs/campaign_fixed/*.png`,
  `graphs/campaign_fixed/campaign_stratified_per_backend.csv`.
