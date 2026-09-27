# RQ1 v3 — Post-Run Analysis (Campaign Capstone)

**Date**: 2026-08-09 · **Campaign**: Phase 2, 4 arms × n=7 = 28 runs, all exit 0
**Plan**: [`experiment_plan.md`](experiment_plan.md) · **Matrix**: [`run_matrix.md`](run_matrix.md) · **Summary + stats**: kept on `cloud-vm` (`analysis/rq1_campaign_summary.md` + dataset + stats) · **Graphs**: [`graphs/comparison/`](graphs/comparison/)
**Host**: `cloud-vm` · **Controller pin**: `d267099` · **Workload**: co-loaded 0.30/0.35/0.15/0.10/0.10 @ 180 s episode / rate 1.2

---

## 1. Objective

RQ1 asks whether the **observation interface** — how the edge platform's controller learns about edge-node state — has a measurable, replicated *user-visible* cost. The v2 campaign proved only the control-loop link (delivery mode → when the controller scales → usable-capacity timing: A 32 < B 57.5 < C ≈ D ~83 s) but found no user-visible service-quality difference. v3 exists to close the chain after two platform blockers were removed (a routing-layer flow-idle artifact and a 600 s plateau that amortized the ~50 s timing spread):

> delivery mode → what/when the controller sees → when it scales → **per-episode user-visible service quality (p95 / timeout / failure)**.

The independent variable is the **telemetry delivery mode** (4 arms). The hypothesis under test (H2, the new claim): arms that scale later show measurably worse per-episode quality — **A (fresh+complete) < B (delayed +30 s) < C (latest-state, ~1/3) ≈ D (sampled-push, ~1/3)**, tracking the usable-capacity ordering (H1: A < B < C ≈ D). H3 checks that non-surge phases stay clean in all arms (degradation confined to the episode).

## 2. Mechanism

- **Design**: 4 arms × n=7 = **28 runs**, seeds 3001–3007, new counterbalance (one run per arm per block, all four arms share the block seed → demand-matched). Arm envs: A `rq1_event_preserving.env`, B `rq1_delayed.env`, C `rq1_latest_state.env` + `POLL_INTERVAL_S=30`, D `rq1_sampled_push.env`. Open-loop driver, `CURL_MAX_TIME=300`, `INFLIGHT_WINDOW=1024`, `DRAIN_S=30`, `CLIENT_TCP_SYN_RETRIES=9` (Phase-0 fix).
- **Workload**: re-anchored in Phase 1 to a **180 s steep overload episode** (`compute_plateau`, rate 1.2, co-loaded mix with both compute- and storage-path load) so the ~50 s usable-capacity spread lands inside the stressed window. Tails (baseline / recovery_gap / demand_drop / idle_tail) unchanged.
- **Controller pin**: `d267099` (rq1-v3-p1), verified byte-identical on the VM at every pre-run gate; rq2 `925c43f` excluded.
- **Pre-registration (2026-08-08)**: H2 primary endpoint = **served-basis episode p95**; four primary MWU edges (delay A−B / D−C, loss A−D / B−C), no multiplicity correction, Cliff's δ + 95 % CI; ordering claim on the 28 replicates only; offered-basis ≥ 85 % hard gate for Arm A, reportable flag for B/C/D; differential cancellation reported per arm.
- **Analysis**: `rq1_delivery_per_run.py` per run (bundles in each run folder, retained on the VM), `rq1_delivery_comparison.py` cross-mode suite (25 graphs, archived to `graphs/comparison/`), campaign stats computed from the extracted dataset (kept on `cloud-vm`: `analysis/rq1_v3_campaign_dataset.csv`, `analysis/rq1_v3_campaign_stats.csv`).

## 3. Results

### Base-requirements verdict (28/28 runs)

All hard gates from `docs/operation/testing/testing_requirements.md` **met in every run** (verified from artifacts, not assumption): M1 (≥ 7 `,lan[12],add,`/run), M2 (served-basis completion ≥ 95.7 %, added nodes serve), V1 (co-loaded: edge + storage CPU loaded, `T_db` 100–500 ms in calibration), I1 (offered ≈ 5,180/LAN/episode ≥ 5,000), I2 (timeout / failure / canceled distinct classes, never merged), D1 (0× `NotPrimary`), D2 (0 restart/crash/OOM), D3 (provenance snapshots present), F1 (delivery per arm design: ep/delayed 1.0, ls/sp 0.325–0.336). Flags (reported, non-invalidating): `delayed_3` lan2 asymmetry 5.26× (> 3×, only run above the line), B-arm residual `http=000` completed class (2.22 %), storage-removal retry flags outside the episode (closed — §5.3), `sp_6` single-replicate cancellation spike.

### Per-hypothesis verdicts

| Hypothesis | Verdict | Key evidence |
| --- | --- | --- |
| **H1** usable-capacity A < B < C ≈ D | ✅ **CONFIRMED** | Medians A 28.5 < B 59.6 < C 79.6 ≈ D 83.2 s; A<B in 7/7, B<C in 7/7 blocks; C vs D 5/7 with D marginally later (n.s. separation) |
| **H2** per-episode p95 A < B < C ≈ D | ⚠️ **PARTIALLY CONFIRMED** | **Loss arms confirmed**: A−D δ = −1.000, p = 0.0006, 7/7 perfect separation, C/D ~9× A (31–40 s vs 3–5 s). **Delay A−B confirmed in aggregate** (p = 0.0012, δ = −0.959, 7/7) but **B bimodal** (65 s at seeds 3001/3007, 5–13 s elsewhere) → **B−C n.s.** (p = 0.209). **C ≈ D** (D−C p = 0.456; point estimate C marginally worse — "D strictly worst" not supported) |
| **H3** non-surge phases clean | ✅ **CONFIRMED** | Baseline/recovery/demand-drop p95 ~1.05–1.08 s in all arms; only 300 s-cap tail timeouts in demand_drop (0.07–0.12 %) and two single-window recovery blips in C/D |

### The replicated finding

The headline claim of RQ1 v3 — *arms that scale later show measurably worse per-episode service quality* — is **confirmed and replicated for the loss arms (C/D)** with the strongest possible separation (Cliff's δ = −1.000, exact p = 0.0006, every one of 7 replicates). The delayed arm B is significantly worse than A in aggregate but trajectory-dependent (bimodal). The **full monotone ordering A < B < C ≈ D is not reproduced** (B−C n.s., D not strictly worst). Timeouts are 0 in the episode in all 28 runs (ordering carried by p95, as pre-registered); no arm shows harness collapse (served-basis ≥ 95.7 %); non-surge quality is clean everywhere → the between-arm p95 contrast is a **genuine, artifact-free service-quality cost of late or lossy delivery**, not a platform artifact.

## 4. Gaps & Next Steps

- **B's bimodality — resolved as a margin effect (see §5.1).** B's usable capacity is tight (55.1–61.5 s) yet its episode p95 spans 5.0–65.3 s. The post-campaign mechanism check shows the control loop is identical across all B runs; the spread is a *margin effect* — B's ~60 s exposure window makes its outcome conditional on the platform's transient service rate (5/7 runs near-A, 2/7 collapse to loss-arm levels). B−C still cannot separate at n=7, but the reason is now understood, not unexplained. The delay-axis aggregate claim (A<B) holds.
- **"D strictly worst" not supported at campaign scale.** The sampled-push arm was expected to react latest (can miss the surge-onset window), but at n=7 C (poll-30 latest-state) is if anything marginally worse. Robust statement: **C ≈ D**, both ~9× A.
- **Differential-cancellation expectation did not reproduce.** The probe-derived monotone pattern (cancellation rising with degradation) did not survive replication — campaign canceled shares are flat ~5–7 % (one `sp_6` outlier at 21.2 %). The served/offered gap is zero (plateau timeouts = 0), so no correction is needed, but the probe pattern should not be cited.
- **Single-run caveats**: `delayed_3` lan asymmetry, `sp_6` cancellation spike, B's residual `http=000` class (2.22 %) — all reported, none gate-breaking.
- **Regime-relative magnitudes**: all H1/H2 magnitudes are on the co-loaded 180 s/1.2 regime; they are regime-relative per the base-requirements relative-criteria rule.
- **What the thesis can state**: the observation interface has a measured, replicated user cost on the fixed platform — lossy delivery (latest-state or sampled, ~1/3 completeness) costs ~9× episode p95 with perfect separation; +30 s delay is significant in aggregate but trajectory-dependent; non-surge quality and data-path integrity stay clean in every arm.

---

## 5. Post-campaign verification checks (2026-09-26)

### 5.1 Arm B bimodality — resolved: a margin effect

The delayed arm's run-to-run spread (episode p95 5.0–65.3 s) was investigated directly from the run artifacts:

- **Not a delivery/decision-layer effect.** Across all 7 delayed runs the control loop behaved identically: decision evidence age = 30 s in every run, first scale-up decision 52.0–60.4 s (per-run max over LANs; isolated earlier per-LAN decisions follow the documented stale-pre-plateau-window artifact) and usable capacity 52.6–63.6 s — yet user-visible p95 ranged 5.0–65.3 s.
- **The degraded runs show a deep queue drained by capacity arrival.** `delayed_1` / `delayed_7`: episode p50 = 5.3 s (equal to the lossy arms' ~5.6–5.8 s), 13–15 % of requests > 30 s, p99 capped at ~68–71 s ≈ the capacity-usable time; per-bucket p95 shows transients at 60–90 s and 120–150 s.
- **The trigger is platform service-rate variance, present in all arms.** Episode median compute processing time varies ~6× across runs of identical configuration: B degraded runs 83.1–93.6 ms vs B healthy runs 16.1–51.4 ms; the reference arm shows the same spread (10.3–71.6 ms) — the identical-config variance documented in Phase 0 (P0-4 vs P0-4R).
- **Mechanism — margin effect.** Each arm's exposure window (episode start → usable capacity) sets its margin over that variance: **A ~29 s** (immune; worst bucket p95 7.5 s even in the slowest platform state) · **B ~55–62 s** (conditional; 5/7 runs near-A, 2/7 collapse to loss-arm levels) · **C/D ~78–83 s** (always deep; variance irrelevant). The delivery mode sets the margin; the platform state decides the outcome.
- **Consequences.** One mechanism now explains: A−B significance in aggregate (exposure doubled), B−C non-separation (typical B ≈ A-like, collapsed B ≈ C/D), the tight C ≈ D result, and stable control-loop timing with unstable user quality. It also retro-justifies the n=7 variance rationale.
- **Thesis framing**: the delay arm's user-visible cost is *conditional* — the closer an arm operates to the capacity limit, the more observation delay costs (a transferable design insight, not just a number).

### 5.2 Aggregation-masking check (per-bucket DF)

Motivated by the RQ2 aggregate-masking finding, the campaign was re-checked at per-bucket granularity (30 s buckets, served-basis) for hidden degradation. **Result: no masking** — degraded-time fraction (share of episode buckets with bucket-p95 ≥ 10 s): **A 0.0 % · B 28.0 % · C 63.6 % · D 64.6 %** (per-run values in the CSV). The episode-p95 ordering reproduces at bucket granularity, with A never exceeding 7.5 s in any bucket (its non-zero DF50 share, 29.8 %, is the onset ramp before scale-up lands — a finite transient, not hidden degradation). Artifacts: [`graphs/comparison/df95_masking_check.png`](graphs/comparison/df95_masking_check.png), [`graphs/comparison/df95_masking_per_run.csv`](graphs/comparison/df95_masking_per_run.csv).

### 5.3 Scale-down integrity check (campaign-wide sweep)

A read-only sweep of all 28 campaign runs (docker truth `container_events.csv`; controller truth `elasticity_events.csv`; `decision_log_lan{1,2}.csv`; `reaction_timeline.csv`) closes the storage scale-down retry flag and certifies run isolation. Artifacts: [`scale_down/`](scale_down/) — per-run sweep table, FAILED-event detail, raw report.

- **No cross-run contamination — verified, not assumed.** Every run's start-of-run snapshot is the identical 7-container baseline fleet with no dynamic container (28/28). The between-arm contrast rests on a verified common starting state; no run inherited leftovers from a previous run.
- **Scale-down executes in every run.** Docker-level removals of dynamic containers occurred in all 28 runs — storage removals in every run (A 27 · B 29 · C 19 · D 13; 88 total) and compute removals in 19/28 runs (A 36 · B 18 · C 3 · D 6; 63 total). Executed removals concentrate in `idle_tail` (21/28 runs idle_tail-only; 7 runs also show removals in `demand_drop`/`recovery_gap`).
- **The storage `FAILED`-retry class is closed.** 218 FAILED `node_remove_timing` events campaign-wide (A 46 · B 68 · C 59 · D 45; per-run mean 6.4–9.7, reproducing the original watch-item record), all on storage containers (lan2 125 · lan1 93). Every event's container had already been successfully removed: 0 events without a prior `DONE` for the same container (strict ordering), docker removal evidence for 218/218, **0 unresolved**. Retries fire 28.8–306.4 s after the successful removal (median 112.7 s; per-attempt durations 26.8–34.7 s, avg 30.7; up to 8 repeats on one container). A post-removal retry loop — no removal failure, no D2 impact.
- **No restarts/crashes in any run.** No restart signature in any container state sequence (28/28); the base fleet ran continuously — D2 holds through the tails, not only the episode.
- **Observation (post-hoc; not a claim).** In-run removal progression differs across arms — removals A 63 (c36/s27) · B 47 (c18/s29) · C 22 (c3/s19) · D 19 (c6/s13) — tracking each arm's add counts (A/B add 85–93; C/D 59–68) and leaving more dynamic containers at the run-end snapshot in late arms (leftovers A 30 · B 38 · C 46 · D 40); all leftovers are cleared before the next run (first bullet). Directionally consistent with the delivery-mode timing chain, but the readout is post-hoc and confounded (cycle counts, ~31 s retry occupancy) — it affects neither measured user quality (H3) nor run isolation.
- **Limitation — scale-down latency remains not evaluable.** `scale_down_latency_s` populated in only 9/28 runs (A 6 · B 2 · C 0 · D 1), non-comparable phase alignment → not claimed.

---

*Capstone synthesized from the 28 run folders and the campaign analysis (both retained on `cloud-vm`), and `graphs/comparison/`. Probes (P-B/P-C/D-recheck) are calibration only per pre-registration and are not evidence for ordering claims.*
