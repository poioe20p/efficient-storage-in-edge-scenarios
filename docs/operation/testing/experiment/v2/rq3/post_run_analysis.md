# RQ3 v2 — Post-Run Analysis (readiness-propagation: direct vs discovery)

**Date**: 2026-08-05 · **Plan**: `rq3_v2_rework_plan.md` · **Contract**: `measurement_contract.md`, `analysis_focus.md`
**Campaign**: 18 scheduled runs + 1 extra replicate on `cloud-vm-rq3` (2026-08-04 23:33 → 2026-08-05 05:05 UTC), all exit 0.
**Fixed-image validation campaign**: 12 runs (2026-08-06, n=6/arm, seeds 2310–2321), all exit 0 — see §6.
**Graphs**: `graphs/comparison/*.png` (14 figures, RQ1 comparison style) · **Per-run metrics**: `rq3_campaign_summary.csv`

---

## 1. Objective

RQ3 v2 asks whether the **readiness-propagation mechanism** determines the cost of
elastic scale-up: does a controller that learns backend readiness by **direct
event** (`app_ready`), versus one that **probes/polls** readiness on a fixed
period, change (a) how fast new capacity becomes usable, and (b) whether the
transition degrades service? The independent variable is `READINESS_PROPAGATION`
(`direct` vs `discovery`), with `discovery_15` (poll 15 s) as the sensitivity cell
showing the quantization cost scales with the poll period. The pre-registered
hypothesis (`analysis_focus.md` §1): the between-arm differential is carried by
**timing quantization** — discovery leaves new capacity dark up to one poll period
longer, so old backends carry the saturated load longer; a **null on consequence
metrics is a pre-registered acceptable outcome** (§2.7/§4.2).

## 2. Mechanism

- **Workload**: `phases_rq3_compute_episode.json` — baseline (60 s, 1.0 req/s),
  `compute_spike` (180 s, 3.0 req/s, 90 % service_pressure — fires compute scale-up),
  `cleanup_gap` (180 s, 0.5 req/s). 6 clients, open-loop, in-flight 1024, drain 30 s.
- **Design**: 6 counterbalanced blocks of 2 (seeds 2001–2006, each arm leads ≥ 2),
  + sensitivity `disc15` ×6 (seed 2007). n=6 per mode. Per-connection VIP flows
  (`VIP_SERVER_PER_CONNECTION_FLOWS=1`) so each request re-selects a backend;
  Check C gate ≥ 0.85 (amended 2026-08-05, see `run_matrix.md` void log).
- **Measured**: per-backend `spawn_complete→admitted` (the quantization),
  `scale-decision→first 2xx` (usable capacity), gap-window old-backend
  `timeout_rate`/`failure_rate` (headline consequence), `useful_initial_share`,
  `admitted→first_flow`, event fraction, Check C/D, per-phase latency/timeout.
  `rq3_admission_analysis.py` (per-run + cross-arm), `rq3_flow_validation.py`
  (per-run), `tools/gen_rq3_v2_comparison.py` (graphs + stats).

## 3. Results

### 3.1 Pre-registered verdicts

Aggregation: **run-level medians** (the pre-registered statistic, `analysis_focus.md` §4);
means shown where the graphs plot them. Exact two-sided MWU p (permutation-enumerated,
`tools/rq3_campaign_stats.py`); extra replicate excluded (n=6 per mode).

| Check | Metric (run-level median) | direct | discovery | discovery_15 | MWU p (d vs disc) | Verdict |
|---|---|---|---|---|---|---|
| **Quantization (secondary: must show direct ≤ discovery)** | `spawn→admitted` (s) | **0.170** (0.13–0.31) | 9.619 (4.98–17.46) | 15.222 (7.54–19.86) | **0.0022** | ✅ **met** — d = −1.000, full separation, ~57× faster |
| **Headline consequence** | gap-window `timeout_rate` | 0.000 (n=5) | 0.000 | 0.000 | 1.000 | ✅ pre-registered **null** |
| Supporting 1 | gap-window `failure_rate` | 0.000 (n=5) | 0.000 | 0.000 | 1.000 | neutral (null) |
| Supporting 2 | `useful_initial_share` | **0.739** (0.68–0.86) | 1.000 | 1.000 | **0.0022** | direct **worse** (d = −1.000) |
| Supporting 3 | `scale→first 2xx` (s) | 10.963 (6.33–11.07) | 11.454 (6.95–19.52) | 16.969 (9.41–21.79) | 0.132 (NS) | directional direct **better** (d = −0.556, < 0.6 pre-reg threshold; vs disc15 p=0.026) |
| Manipulation (expected arm-identical) | `admitted→first_flow` (s) | **10.044** (5.30–10.11) | 0.826 (0.77–0.85) | 0.870 (0.79–0.93) | **0.0022** | ❌ **NOT met** — unanticipated divergence |
| Instrumentation | event fraction | 1.00 (all runs) | 0.0 (by design) | 0.0 | — | ✅ (direct gate ≥ 0.80) |
| Instrumentation | Check C | 0.88–0.96 | 0.97–1.00 | 0.99–1.01 | — | ✅ all ≥ 0.85 gate; D ≤ 1 % (see §3.3.8 for the gate-justification correction) |
| Sensitivity (descriptive, Cliff only) | quantization vs poll period | — | 9.619 | 15.222 | 0.240 (NS, descriptive) | ✅ cost scales with poll period (d = −0.444) |

**Supporting-consistency rule (≥ 2 of 3 same direction):** supporting set =
`gap_failure` (neutral), `useful_share` (direct worse), `scale→1st` (direct
better, NS) → **1–1–1, i.e. "mixed/ambiguous"** for the service-consequence
dimension. The timing claim is **unambiguous** (significant); the consequence
claim is **null-to-mixed** (headline null + split supporting set).

### 3.2 Confirmed findings

1. **Event-driven admission eliminates the poll quantization.** direct admits
   new capacity in 0.170 s (median) vs 9.619 s (discovery) and 15.222 s (disc15)
   — ~57×/90× faster, full separation (Cliff's d = −1.0, exact MWU p = 0.0022),
   stable across all 6 seeds (0.13–0.31 s). The quantization tail scales with
   the poll period (10 → 15 s adds ~5.6 s of median; descriptive, p = 0.24),
   confirming the mechanism is the poll, not the host.
   → `quantization_spawn_to_admitted.png`
2. **Usable capacity is reached somewhat sooner in direct (directional, not
   conclusive).** `scale-decision→first 2xx` medians 10.96 s (direct) vs
   11.45 s (discovery) — a **0.49 s** median gap, **not significant**
   (p = 0.132) and below the pre-registered d ≥ 0.6 threshold (d = −0.56);
   vs disc15 (16.97 s) it is significant (p = 0.026). The monotone trend with
   poll period is supportive but the direct-vs-discovery usable-capacity
   advantage is a directional supporting vote, not a confirmed headline.
   → `scale_to_first_success.png`
3. **Headline consequence is null on every arm.** gap-window old-backend
   `timeout_rate` and `failure_rate` = 0.000 on all defined runs (1 of the 6
   scheduled direct runs undefined — per-backend attributed gap requests
   < 20; the excluded extra replicate is the other undefined row). Old
   backends never time out during the gap in any mode at the calibrated spike
   (3.0 req/s). The pre-registered null is reproduced. → `gap_timeout_rate.png`,
   `gap_failure_rate.png`
4. **Per-request latency is not the bottleneck** on any arm: transition/phase
   p50 ≈ 0.015–0.020 s, p95 ≈ 0.04–0.06 s, p99 ≈ 0.07–0.46 s (sub-100 ms tier);
   no per-phase timeout differentiation. The RQ3 differential is timing, not
   per-request latency. → `per_phase_latency.png`, `per_phase_timeout.png`

### 3.3 Unanticipated findings (plan did not anticipate)

5. **`admitted→first_flow` is NOT arm-identical (manipulation check failed).**
   In direct runs, 17 of 24 admitted backends receive their first attributed
   request **~9.9–10.3 s after admission**, while discovery/disc15 backends get
   traffic in ~0.8 s (exact MWU p = 0.0022, d = +1.000). The lag is
   **per-backend and equals the edge app's intermittent HTTP-bind delay
   (root-caused 2026-08-06, see §4)**: the edge's Werkzeug dev server
   intermittently took ~10 s to bind ("Serving Flask app" → "Running on
   http://"), while the `app_ready` event fires on the MongoDB-ping predicate
   ~0.03 s after start — up to ~10 s before the server can serve. Direct
   admits on that early event; discovery's poll cannot return 200 until the
   server actually serves `/ready`, so it structurally waits out the gap.
   Per-backend correlation (direct_1): bind delay 10.0–10.4 s ⟺ first-success
   +10.0–10.4 s; bind delay 0.0 s ⟺ first-success +0.68 s. The earlier
   "route/ARP-refresh reusing `DISCOVERY_POLL_INTERVAL_S=10.0`" hypothesis is
   **contradicted** by the controller logs (flow installs to the new backend
   succeed at +0.7 s — the data path is ready; the app is not). →
   `admitted_to_first_flow.png`
   *(Attribution refined 2026-08-06 by the instrumented fixed-image campaign
   §6: the ~10 s is in the raw socket `bind()`/`listen()` path and persists
   with `make_server`; the app fix eliminated the premature-admission
   artifact, not the stall — see §4/§6.)*
6. **A direct-only fast-fail footprint: http=000 / backend=unknown.** Each
   lagging admission creates a ~10 s window of **completed requests with
   `http_status=000` and `backend_id=unknown`** — fast connection-setup
   failures (mostly < 10 ms, tail up to ~1 s), confined to `compute_spike`.
   Across all windows per run (2 windows in 4 of 6 direct runs; total span
   10–100 s of the spike), direct records 162–428 such rows (4.6–12 % of
   offered): direct_1 348, direct_2 162, direct_3 287, direct_4 385,
   direct_5 189, direct_6 428. **Zero** fast-fail 000 rows in all 6 discovery
   runs; disc15 has 0,0,0,0,0,0 fast-fail 000s (disc15_4 has 2 *different*
   rows: ~15 s latency, `cleanup_gap` phase — not this artifact). This is the
   empirical price of event-driven ultra-early admission combined with an
   **app-side servability gap**: the backend's HTTP server is not yet bound
   (intermittent ~10 s Werkzeug bind delay), so connections are refused
   during the window. It is a harness artifact, not a routing/flow-layer lag
   (flow installs to the backend succeed at +0.7 s). → `unattributed_http000.png`
7. **Consequence on the supporting set:** `useful_initial_share` direct = 0.739
   vs 1.000 discovery (p = 0.0022) — the 000-unknown rows are counted as
   non-successes pool-wide (they sit after the gap window, so the headline
   stays null). Direct's timing win carries a transient handover cost that
   polling avoids — but root-caused (2026-08-06) to the app bind delay (a
   harness artifact), not to event-driven admission per se (see finding 5).
8. **The Check C shortfall in direct runs IS the http=000 artifact — the gate
   amendment's original justification was wrong.** Per-run, Check C shortfall
   (1 − coverage) tracks the http=000 fraction almost exactly: direct_2 4.4 %
   vs 4.6 %, direct_3 8.1 % vs 8.1 %, direct_6 12.0 % vs 12.1 %, direct_1
   12.0 % vs 9.9 % (residual ~2 %), direct_4 11.5 % vs 10.9 % (residual
   ~0.6 %), direct_5 6.9 % vs 5.3 % (residual ~1.6 %); discovery/disc15
   shortfalls are only 0–3 % with zero 000s. Failed connects never emit
   `request_complete`, so they never produce a flow-delete — yet they are
   "completed" rows in the coverage denominator. Hence the low Check C in
   direct is a **denominator artifact of the treatment's own failed connects**
   (which have no flow to delete), NOT the "~10–14 % orthogonal telemetry
   delivery loss" stated in the 2026-08-05 gate amendment. The true residual
   delivery loss is only ~2–3 % (the discovery/disc15 residual). The amended
   0.85 gate remains **defensible but for a corrected reason**: for
   established connections, delivered `request_complete` → delete is 1:1
   (verified earlier), and the low coverage rows never had a flow.
   → `check_c_coverage.png`, `unattributed_http000.png`

### 3.4 Overall verdict

**The timing/mechanism claim is CONFIRMED (significant); the service-consequence
claim is null-to-mixed (pre-registered as acceptable).** Event-driven readiness
propagation admits new capacity ~57× faster (0.17 s vs 9.6 s, p = 0.0022) and
the quantization cost scales with the poll period as predicted. There is **no
service degradation from the gap** (null timeouts on all arms), and usable
capacity is reached directionally sooner (0.49 s median, NS). However, the
supporting set is split: direct reaches usable capacity marginally sooner yet
also exhibits a **reproducible, direct-only transient handover artifact** —
4.6–12 % of offered requests fail fast (http=000, unattributed) during the
   ~10 s-per-admission windows when ultra-early admission outruns the app's HTTP
   bind — a harness artifact (edge Werkzeug bind delay, root-caused and fixed
   2026-08-06, §4) — which discovery avoids entirely and which also explains the
   direct Check C
shortfall (correcting the gate amendment's original justification). The honest
thesis claim: **readiness-propagation determines elastic scale-up timing; it
does not, at the calibrated load, determine gap-window service quality — but
event-driven admission carries a small, transient, handover-window availability
cost that polling-based discovery does not.**

## 4. Gaps & Next Steps

- **Why exactly ~10 s? — RESOLVED (2026-08-06).** The lag is the edge app's
  intermittent **Werkzeug dev-server bind delay**: bind inside `app.run()`
  intermittently took ~10 s ("Serving Flask app" → "Running on http://"),
  while the `app_ready` event fires on the MongoDB-ping predicate ~10 s
  earlier. Per-backend correlation in `direct_1`: bind delay 10.0–10.4 s ⟺
  first-success +10.0–10.4 s; bind delay 0.0 s ⟺ first-success +0.68 s. The
  probe rate-12 runs were clean (0×000) precisely because no dynamic backend
  hit the delay there (all ~0 s). **The same app-side delay contaminates RQ1
  and RQ2** (no readiness gate — backends admitted at spawn): RQ1 shows
  18–428 slow 000s/run with ~half of dynamic backends delayed; RQ2
  (cloud-vm-rq2) shows ~10.3 s on *every* backend with 253 fast 000s + ~380
  timeouts per run — and RQ2's TTFT/initial-share metrics are exactly what a
  ~10 s unservable window corrupts, with a between-arm interaction risk
  (policies that route to new backends immediately are penalized;
  warm-lease/slow-start hold traffic off). Storage servers are unaffected
  (different readiness path). **Fix applied (2026-08-06)**:
  `edge_server/source/app.py` now binds via `werkzeug.serving.make_server`
  *before* starting the readiness probe, so `app_ready`/the event can only
  fire once the server is accepting connections (readiness = servability).
  Image rebuilt on `cloud-vm-rq3` (`edge_server:latest`), smoke-verified:
  bind ~3 ms, `/ready` responds immediately, event structurally after bind.
  `cloud-vm-rq2` needs the same rebuild before its next campaign.
  **Refined 2026-08-06 (instrumented fixed-image campaign, §6):** the ~10 s is
  NOT the Werkzeug dev server per se — it persists inside `make_server`'s raw
  socket `bind()`/`listen()` (instrumented `bind-timing` logs show
  `getaddrinfo=0.000s`, `importlib.metadata=0.001s`,
  `make_server(bind+listen)=10.03–10.04 s`), only manifests during active runs
  at spawn time (kernel-level stall under network-namespace churn), and is
  intermittent (~50-75 % of spawns), random across backends (statics too),
  equally in both arms. The app fix remains correct and necessary (readiness
  can no longer precede servability → 0×000), but it does not eliminate the
  bind stall; no cheap harness knob does (`EDGE_CPUS=1.0` was tried and
  rejected: it suppresses compute scale-up, voiding the run). The stall is
  now **controlled statistically** via bind-stratified analysis in the
  fixed-image campaign (§6).
- **http=000 semantics**: the driver records these as `completed` with
  `http_status=000`; whether they are connection resets or aborted connects is
  not distinguishable in the current CSV. A follow-up could capture TCP-level
  outcomes (RST vs timeout) in the driver.
- **Load ceiling**: at the calibrated 3.0 req/s the spike leaves headroom —
  gap timeouts are null because old backends absorb the gap. A higher-rate
  sensitivity cell (e.g., 5.0–6.0 req/s, if the in-flight budget allows) would
  test whether the quantization cost materializes as timeouts under true
  saturation — the one regime where the headline could turn non-null.
- **`useful_share` direction is confounded** by the http=000 artifact: the
  direct-vs-discovery share gap (0.74 vs 1.0) is driven by attribution
  failures, not by old-backend timeout — reported as measured, mechanism
  hypothesis in §3.3.
- **Check C gate amendment re-justified** (see §3.3.8): the 0.9 → 0.85
  loosening stands, but for the corrected reason (failed connects have no
  flow to delete; true flow-delete coverage is 1:1 for established
  connections), not the original "orthogonal ~10–14 % delivery loss"
  justification. `run_matrix.md` amendment note updated accordingly.
- **Extra replicate**: `20260805_000344_rq3_direct_1` (seed 2011, Check C 0.91)
  is excluded from the primary n=6 but retained in artifacts; it does not
  change any conclusion (its metrics sit within the direct distributions).

---

## 5. Post-hoc boundary probe (declared 2026-08-05, user-approved)

**Status: post-hoc (non-pre-registered) extension.** Purpose: the campaign's
consequence null was measured at 3 req/s/client (~10 % old-backend CPU) — a load
where degradation was *impossible*, so the null could be dismissed as
under-saturation. This probe re-tests the same comparison at progressively
higher load to locate where/if the readiness-quantization consequence
materializes, and to quantify the system's practical limit. **It does not
replace or alter the pre-registered 18-run campaign** (that remains the primary
RQ3 evaluation); it is a labeled boundary sub-analysis. Plan/run log:
`run_matrix.md` §5; evidence: `rq3_probe_summary.csv`, `graphs/probe/*.png` (8).

**Design.** Same arms, envs, metrics, and analyzer as the campaign; only the
spike `rate_per_client` differs. Ladder: rate 8 (window 3072) → 12 (4096) → 25
(10240), then a clean high-load cell at **rate 12**, extended to **n=6/arm**
(8 additional runs, user-approved 2026-08-06, seeds 2218–2225) — the highest
consistently-clean rate, matching the campaign's n=6 convention so the
timing-under-load claim can be tested with an exact MWU. `INFLIGHT_WINDOW`
raised per the pre-registered `rate × 300 ≤ window` rule. All runs on
`cloud-vm-rq3`, 4-step per-run reset (`rq3_preflight.md` §8). Seeds 2201–2225
(outside the campaign range).

**Results (run-level medians; n per arm per rate):**

| rate/client | arm | n | gap_to / gap_fr | useful_share | scale→1st (s) | CPU p50 (max) | canceled % | http=000 |
|---|---|---|---|---|---|---|---|---|
| 8 (48/s) | direct | 1 | 0.000 / 0.000 | 1.000 | 2.17 | 24.5 (29.6) | 0.27 | 0 |
| 8 | discovery | 1 | 0.000 / 0.000 | 1.000 | 9.50 | 24.3 (35.2) | 0.26 | 0 |
| 12 (72/s) | direct | 6 | 0.000 / 0.000 (all) | 1.000 (all) | 1.85–2.30 (med 2.17) | 31.6–37.4 (42.5) | 0.24–0.39 | 0 |
| 12 | discovery | 6 | 0.000 / 0.000 (all) | 1.000 (all) | 4.72–7.67 (med 6.01) | 32.5–38.0 (65.3) | 0.27–0.46 | 2* |
| 25 (150/s) | direct | 2 | 0.000 / 0.000 | 1.000 / 1.000 | 2.91 / 3.08 | 44.9 / 71.8 (75.3) | 3.97 / 20.58 | 0 |
| 25 | discovery | 1 | 0.000 / 0.000 | 1.000 | 5.19 | 61.6 (88.1) | 10.68 | 0 |

* `cell12_disc_4` (rate 12): 2×http=000 rows in `cleanup_gap` (1.0–3.0 s latency, backend unknown) — the benign cleanup-phase pattern, not the direct fast-fail artifact.

**Findings.**

1. **The consequence is null at every load, including true old-backend CPU
   saturation.** gap-window `timeout_rate` and `failure_rate` = 0.000 on all 17
   valid probe runs; useful_share = 1.000 everywhere; zero dropped and zero
   http=000 in the entire probe (the only 000 rows are 2 slow `cleanup_gap`
   rows in `cell12_disc_4` — the benign pattern, not the fast-fail artifact).
   The discovery arm drove old backends to
   **88 % max CPU** at rate 25 with zero gap-window timeouts/failures — the
   strongest possible null (the campaign's under-saturation objection is
   neutralized: consequence does not materialize even when old backends are
   genuinely saturated). → `gap_timeout_vs_rate.png`, `gap_failure_vs_rate.png`.
2. **The quantization persists and matters under load.** spawn→admitted 0.15–0.30 s
   (direct) vs 2.8–5.3 s (discovery) at every rate, and **scale→first-success
   direct 1.85–3.08 s vs discovery 4.72–9.50 s** — direct reaches usable capacity
   4–7 s sooner end-to-end at every rate (no handover lag in any probe run, so
   the timing win is no longer erased); at the n=6/arm rate-12 cell this
   separation is significant (MWU p = 0.0022, see finding 5). →
   `spawn_admit_vs_rate.png`, `scale_first_vs_rate.png`.
3. **The system limit is the driver, not the compute backends.** CPU rises
   ~linearly to rate 12 (~35 %), then the **open-loop driver's delivery
   collapses**: at rate 16 (window 6144) canceled jumps to 43.7 % and at rate
   25 to 4–50 % (run-dependent), requests drain-cancel with no source-port
   record, and the flow-isolation gate (Check D >50 % unknown) voids those
   runs (`cell_disc_1`, `cell_disc_1r`, `cell16_direct_1`). The compute
   backends never exceed ~88 % CPU; the practical delivered ceiling is
   **~100–120 req/s aggregate**. → `cpu_vs_rate.png`, `canceled_vs_rate.png`.
4. **No http=000 in any probe run.** The campaign's direct-only handover
   artifact (162–428 fast-fails) did not appear in the probe's 17 runs —
   root-caused 2026-08-06 to the **edge app's intermittent ~10 s Werkzeug
   bind delay**, which no probe backend hit (all dynamic backends bound in
   ~0 s). The probe's cleanliness is therefore not a load effect and not
   admission-phase luck — it is the absence of the harness bug; a single
   slow-bind direct backend would reproduce the campaign's fast-fails and
   erase the timing win (cf. campaign `direct_1` scale→first 10.96 s). The
   fix in `edge_server/source/app.py` (bind before readiness) removes the
   artifact at the source. (Refined 2026-08-06: the stall itself persists in
   the raw socket bind path — see §4/§6.) (`cell12_disc_4`'s 2×http=000 are
   slow `cleanup_gap` rows, backend unknown — the known benign pattern, not
   the fast-fail artifact.) → `http000_vs_rate.png`.
5. **The timing-under-load claim is now statistically significant (n=6/arm).**
   At the rate-12 cell (the highest consistently-clean rate), direct reaches
   usable capacity in 1.85–2.30 s (median 2.17 s) vs discovery 4.72–7.67 s
   (median 6.01 s) — **full separation, exact two-sided MWU p = 0.0022,
   Cliff's d = −1.000** (campaign convention). The consequence null now rests
   on **6×6 all-zero** rate-12 runs (gap_to/gap_fr 0.000, useful 1.000;
   p = 1.000). This closes the probe's n=2 statistical limitation.
   → `scale_first_vs_rate.png`, `spawn_admit_vs_rate.png`,
   `rate12_cell_timing.png` (dedicated cell figure, added 2026-08-06).

**Verdict (probe).** The RQ3 consequence claim upgrades from *"null at 3 req/s
(under-saturated)"* to *"**no readiness-quantization service consequence up to
and including the platform's measured practical limit** — ~100–120 req/s
aggregate / ~88 % old-backend CPU — where the open-loop driver's own delivery
collapses before the compute backends saturate."* Timing remains confirmed at
every load, and at the **n=6/arm rate-12 cell it is now statistically
significant**: scale→first median 2.17 s (direct) vs 6.01 s (discovery),
**exact two-sided MWU p = 0.0022, Cliff's d = −1.000** (full separation).
Caveats: the probe is
post-hoc; rate 16/25 runs are partially instrumentation-void (Check D) due to
the drain-cancel collapse; no probe run reproduced the campaign's http=000
handover artifact (phase-dependence). The thesis presents this as a clearly
labeled boundary sub-analysis of the RQ3 evaluation.

---

## 6. Fixed-image validation campaign (2026-08-06)

**Status: the definitive post-fix evaluation.** After the servability fix
(`edge_server/source/app.py`: bind via `make_server` *before* the readiness
probe, so `app_ready` cannot precede servability), the primary pair was
re-run at the canonical rate **3.0 req/s/client, n=6/arm — 12 runs**
(seeds 2310–2321, `rq3_camp_{direct,disc}_{1..6}`, fixed+instrumented image
`638e3efdcdc5`, default `EDGE_CPUS=0.30`). All runs non-void, exit 0,
**0×http=000**, `useful_share=1.000`, flow-validation A/B/C/D pass (47
backends). The direct-arm handover artifact of §3.3.6–8 is **eliminated at
the source** — the pre-fix direct `useful_share=0.739` gap was the artifact,
not the mechanism.

**Bind-stall final root cause (instrumented).** The edge app now logs a
`bind-timing getaddrinfo=… importlib.metadata=… make_server(bind+listen)=…`
line before serving. Across the campaign, slow backends show
`getaddrinfo=0.000s`, `importlib.metadata=0.001s`, and
**`make_server(bind+listen)=10.03–10.04 s`** — the stall is in the **raw
`socket.bind()`/`listen()`** path inside `make_server`. Ruled out: DNS
(getaddrinfo 0.000 s even in slow cases), disk (importlib.metadata 1 ms),
CPU cgroup (VM CPU 1–13 %; `EDGE_CPUS=1.0` was tried and rejected — it
suppresses compute scale-up, voiding the run), the veth attach (completes
before the app logs `Starting edge-server` in the slow cases), and the
Werkzeug dev server (persists with `make_server`). It manifests **only
during active runs at spawn time** (kernel-level stall under network-namespace
churn: veth attach + OVS/controller flow churn), intermittently
(~50-75 % of spawns), randomly across backends (statics too — n1 had 11 s in
the discovery fixval run), and **equally in both arms**. It is therefore a
**shared, unavoidable infra cost** on absolute `spawn→first` timing; it
cancels in the between-arm difference.

**Stratified analysis.** Because the stall is **measured per backend**, the
arms are compared within bind strata (fast <1 s, slow ≥5 s) — controlling for
the measured confounder rather than discarding slow-bind cases
(`tools/rq3_stratified_analysis.py`, `tools/gen_rq3_stratified_graphs.py`):

**PRIMARY — readiness→admission (bind-independent):**

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

**Verdict.** The mechanism claim is decisive everywhere (readiness→admission
0.001 vs ~7 s, d = −1.000 in all strata), and the **end-to-end claim now
holds**: `spawn→first` significantly favors direct even pooled (p = 0.0005,
d = −0.594) and is perfect within both bind strata (d = −1.000; fast-bind
1.69 vs 9.16 s, slow-bind 11.46 vs 18.28 s). With the artifact controlled,
the fixed-image campaign confirms **both** the timing claim and a
user-visible consequence — the strongest RQ3 evidence to date. Evidence:
`graphs/campaign_fixed/*.png`,
`graphs/campaign_fixed/campaign_stratified_per_backend.csv`.

---

*Evidence: 19 campaign run folders + 17 valid probe run folders under
`source/scripts/testing/metrics/` (verified local copy),
`rq3_campaign_summary.csv`, `rq3_probe_summary.csv`, 14 campaign graphs under
`graphs/comparison/`, 9 probe graphs under `graphs/probe/` (8 vs-rate + the
rate-12 cell figure), `run_matrix.md`
(complete, incl. probe log). Analyzer: `rq3_admission_analysis.py`,
`rq3_flow_validation.py`; campaign graphs: `tools/gen_rq3_v2_comparison.py`;
probe graphs: `tools/gen_rq3_probe_graphs.py`; stats:
`tools/rq3_campaign_stats.py`.*
