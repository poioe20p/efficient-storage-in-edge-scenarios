# RQ3 v3 — Experiment Plan: Compute Saturation Campaign (locked config)

**Status:** 🟢 **PLANNED — CAMPAIGN READY TO LAUNCH (2026-08-09).** Config locked
at **P4** (tuning matrix complete, `rq3_saturation/run_matrix.md`), relief
validated and reproduced at n=2 (P4 + repro4, 4 runs). Campaign: **n=7/arm →
14 runs**, seeds 3001–3007, counterbalanced. Code pin: tag
`rq3-sat-preflight-20260808` (controller == `d267099`, verified byte-identical
on `cloud-vm-rq3`).
**Scope:** Re-run the RQ3 readiness-propagation evaluation (direct vs
discovery) under a **saturation-capable configuration where compute scale-up
produces a measured relief** — the thesis-level claim RQ3 carries forward.
**Predecessor / basis:**
- [`rq3_saturation/experiment_plan.md`](../rq3_saturation/experiment_plan.md)
  + [`rq3_saturation/run_matrix.md`](../rq3_saturation/run_matrix.md) — the
  tuning matrix (P1–P4 + repro4) that locked the config and demonstrated
  relief.
- [`../v2/rq3/experiment_plan.md`](../v2/rq3/experiment_plan.md) and
  [`rq3_v2_rework_plan.md`](../v2/rq3/rq3_v2_rework_plan.md) — the 6-client v2
  campaign (complete): timing claim at d=−1.000.
- **Storage extension: CLOSED (2026-08-08)** — see
  [`experiment_plan_storage_closed.md`](experiment_plan_storage_closed.md).
  RQ3 is **compute-only**.
**Host:** `cloud-vm-rq3` (fixed image `638e3efdcdc5` present).

---

## 1. Objective

Same thesis RQ3: for newly created compute backends satisfying the same
application-readiness criterion, how does **direct lifecycle notification**
(`app_ready` event) versus **periodic discovery** (10 s poll) affect (a) the
time until a ready backend contributes usable capacity, (b) whether scale-up
**relieves** the compute tier (resource benefit), and (c) whether the
admission-timing differential converts into user-visible harm (consequence —
pre-registered null).

**The v3 addition:** the v2 campaign (6 clients, ~10 % CPU) could not press
the tier, so the **relief** dimension was unmeasurable. The saturation re-run
(48 clients) fixes this: at the locked config compute scale-up produces a
**measured old-backend CPU drop** (P4: direct −18.9 pp, discovery −32.5 pp;
repro: −10.3 / −26.7 pp — all ≥ 10 pp, reproduced at n=2/arm).

**The three-part thesis claim this campaign will carry:**
1. **Timing (T1/T2)** — direct admits new capacity ~7 s sooner (v2: d=−1.000);
   re-confirmed at the new config.
2. **Relief (R1/R2)** — compute adds drop old-backend CPU ≥ 10 pp (B1 CPU leg);
   the headline new claim, tested per-run at n=7/arm.
3. **Consequence (C1)** — gap-window user harm **null**, pre-registered and
   **autoscaler-bounded** (the tier cannot over-saturate past ~70–88 % CPU by
   design).

---

## 2. Locked configuration (P4 — from the tuning matrix)

| Parameter | Value | Evidence |
|---|---|---|
| plateau mix | **`service_pressure 1.0`** (compute-pure, 0 DB ops) | P2/P3/P4: DB ops make the DB the co-bottleneck (T_db 197 ms) and mask compute relief; pure compute isolates the compute tier |
| **EDGE_CPUS** | **0.15** | P1→P4 sweep (0.25→0.20→0.15): relief appears only at 0.15 (RQ2-cb-identical). At 0.25/0.20 the tier under-saturates (24–31 %) |
| rate_per_client | **1.5** (72 req/s aggregate) | driver-clean cap (PG-1: canceled 0.15–0.25 %) |
| CLIENTS | **24/LAN (48 total)** | RQ1/RQ2 golden; needed to press the tier |
| INFLIGHT_WINDOW | 1024 · DRAIN_S 30 · CURL_MAX_TIME 300 | unchanged |
| STORAGE_CPUS | 0.08 | unchanged |
| WAN_RTT_MS | 185 | unchanged |
| EDGE_MONGO_MAX_POOL_SIZE | 6 | unchanged |
| phases file | `source/scripts/testing/phases_override/phases_rq3_saturation.json` (baseline 60 s → compute_plateau 600 s → recovery_gap 120 s → demand_drop 420 s → idle_tail 420 s) | on VM, md5 `2ada9f3f` |
| arm envs | `rq3sat_direct.env` / `rq3sat_discovery.env` (READINESS_EVENT_FALLBACK_S=20 direct; MAX_DYNAMIC_COMPUTE=12; pool 6; per-connection VIP flows) | canonical + docs mirror |
| launcher | `source/scripts/testing/rq3sat_launch_run.sh <env> <label> <seed> 0.15` | EDGE_CPUS = arg 4 |
| code pin | tag `rq3-sat-preflight-20260808` (== `d267099` controller, 75/75 files) | verified byte-identical |

> **PG-2 re-framing (pre-registered 2026-08-09).** The original PG-2 band
> (65–92 % sub-max CPU) was calibrated for the 0.6/0.2/0.2 DB-mixed workload.
> At the compute-pure P4 config the tier saturates to **~40–46 % mean / 62–67 %
> p95** (pooled sub-max ~40–42 %) — this is the **compute-pure ceiling**: the
> RQ2-calibrated autoscaler fires at 70–88 % CPU, so the tier cannot be pressed
> past that without the DB co-bottleneck that kills relief. **The saturation
> gate is re-anchored to: pooled sub-max CPU ≥ 30 % AND relief ≥ 10 pp**
> (relief is the mechanism gate; ~40 % is the documented achievable ceiling).
> This is the deliberate trade: DB ops give high CPU but null relief; pure
> compute gives relief at a lower absolute CPU.

---

## 3. Campaign design

- **Arms:** `direct` (rq3sat_direct.env) vs `discovery` (rq3sat_discovery.env).
- **n = 7/arm → 14 runs.** Rationale: with the expected full separation on
  timing (d=−1.000) the exact-MWU p-floor drops 0.0022 (n=6) → **0.0006
  (n=7)**; n=7 also gives the per-run relief MWU (n=7/arm) more power and
  robustness against run-to-run variance (RQ1 v3 precedent).
- **Counterbalance:** 7 blocks of 2, block seeds 3001–3007 (direct leads 4,
  discovery leads 3 — both ≥2), `v3/rq3/counterbalance_order.csv`.
- **Labels:** `rq3sat_camp_direct_{1..7}` / `rq3sat_camp_disc_{1..7}`.
- **Launch:** `rq3sat_launch_run.sh <arm_env> <label> <block_seed> 0.15`,
  one run at a time on `cloud-vm-rq3`, watchdog-monitored, per-run reset cycle.
- **Runtime:** ~40 min/run × 14 ≈ **9.3 h** + voids.
- **Void rule:** any run failing the per-run gates (§5) is void; replacement
  takes the void's matrix position (same block seed) — ≤1 void/arm.

---

## 4. Pre-registered metrics (within `compute_plateau` only)

All metrics computed within the `compute_plateau` phase (600 s). Steady-state
admissions only (spawn ≥ 120 s into the plateau — ramp guard).

| ID | Metric | Expectation | Gate |
|---|---|---|---|
| **T1** (timing, mechanism) | `ready → admitted` per backend | direct ≈ 0.001–3 s vs discovery ≈ 5–7 s; d near −1.000 | campaign G7 |
| **T2** (timing, end-to-end) | `spawn → first success` | direct faster; absolute differential ≥ v2 | supporting |
| **R1** (relief, primary) | old-backend compute CPU `[spawn−60, spawn]` vs `[admitted+10, admitted+70]`, steady-state | **drop ≥ 10 pp** (P4: −10.3…−32.5 pp) | **headline; B1 CPU leg** |
| R2 (supporting) | old-backend T_proc pre → post | drop | supporting |
| R3 (supporting) | pool latency p50/p95 pre → post | drop or stable (not worse) | B1 latency leg (secondary) |
| **C1** (consequence) | gap-window `[spawn_started, min(admitted, plateau_end)]` old-backend timeout_rate | **null** (0.000) — pre-registered | reported |
| C2 | gap-window failure_rate | null | reported |
| PG-1 | driver clean: canceled+dropped < 5 %, http000 ≈ 0 in baseline | pass | per run |
| PG-2 (re-anchored) | pooled sub-max CPU ≥ 30 % (documented ceiling ~40 %) | pass | per run |
| PG-3 | scale-up fires ≥ 1 add/LAN | pass | per run |
| PG-6 | no driver collapse (< 5 %) | pass | per run |

**Unit of analysis = RUN.** Per-run medians over that run's steady-state
admissions (not per-admission pooling). Cross-arm: **exact MWU** (permutation)
+ **Cliff's δ** on per-run values (n=7/arm). Relief additionally:
**paired sign test** on per-admission (pre, post) within each run + **paired
exact permutation** on per-block (direct_N vs disc_N share block seed N, per
counterbalance_order.csv).

---

## 5. Per-run gates (base requirements `testing_requirements.md` + saturation)

| Gate | Criterion | Stage |
|---|---|---|
| G1 measurability | ≥ 20 gap requests / LAN | per run |
| G2 min-admissions | ≥ 1 admitted backend / LAN | per run |
| G3 event fraction (direct) | ≥ 0.80 event-driven | per run |
| G4 flow validation | Check A/B/D hard, C ≥ 0.85 | per run |
| G5 driver clean | canceled < 5 %; 0×http=000 in baseline | per run |
| G6 relief (campaign) | R1 ≥ 10 pp drop on majority of admissions, per arm | campaign |
| G7 quantization | T1 separation ≥ 5 s | campaign |
| G8 no plateau scale-down churn | no removals mid-plateau confounding relief | per run |
| D1 / D2 / D3 | 0×NotPrimary / no restart-crash / snapshots present | per run |
| M1 / M2 | scale-up fires per LAN / added nodes serve ≥ 1 request | per run |
| V1 | compute CPU rises in plateau (bottleneck evidenced) | per run |
| I1 / I2 | ≥ 5 000 completed plateau/LAN / outcome classes distinct | per run |

---

## 6. Analysis & deliverables

- **Per-run analyzer:** `docs/research_questions/v2/rq3/rq3_admission_analysis.py`
  (phase-parameterized to `compute_plateau`) → T1/T2/C1/C2.
- **Relief:** `tools/rq3_camp_prepost_resources.py --steady-s 120` (R1/R2) +
  `tools/rq3sat_relief_latency.py` (R3) + `tools/rq3sat_relief_windowlog.py`
  (window_log-authoritative).
- **Gates:** `tools/rq3sat_probe_gate.py` (PG-1/2/3/6).
- **Stats:** exact MWU + Cliff's δ, per-run medians, paired block test.
- **Graphs:** the saturation family + `relief_cpu_prepost.png`,
  `timing_campaign.png`.
- **Docs after results:** `results.md`, `post_run_analysis.md`,
  `graphs/`; update `tese/research_questions/rq3/*` with the campaign result.

---

## 7. Timeline

| Step | Action |
|---|---|
| Done | Tuning matrix P1–P4 + repro4 → config locked, docs in `rq3_saturation/` |
| 0 | Sync config to VM (verified: phases md5 `2ada9f3f`, envs, launcher) |
| 1 | Launch 14-run campaign (n=7/arm, counterbalance_order.csv) |
| 2 | Per-run gates + watchdog; voids take matrix positions |
| 3 | Analysis + stats + graphs |
| 4 | `results.md` / `post_run_analysis.md`; thesis doc update |

---

## Appendix A — Saturation tuning matrix summary (P1–P4 + repro4)

Full detail: [`../rq3_saturation/run_matrix.md`](../rq3_saturation/run_matrix.md).

| Cell | Mix | EDGE_CPUS | Plateau CPU | Relief (old-CPU pre→post) | Verdict |
|---|---|---|---|---|---|
| P1 | 0.6/0.2/0.2 | 0.25 | 65–78 % | null (DB co-bottleneck) | ❌ |
| P2 | 1.0 | 0.25 | 24 % | n/a (under-saturated) | ❌ |
| P3 | 1.0 | 0.20 | 31 % | n/a | ❌ |
| **P4** | **1.0** | **0.15** | **~42–46 %** | **−18.9 / −32.5 pp** | ✅ |
| repro4 | 1.0 | 0.15 | ~40 % | −10.3 / −26.7 pp | ✅ reproduced |

---

## Appendix B — Storage extension (CLOSED)

The storage-replica scale-up extension was closed 2026-08-08 after a 4-run
preflight showed no sustained benefit. **RQ3 is compute-only.** Full record:
[`experiment_plan_storage_closed.md`](experiment_plan_storage_closed.md) +
[`run_matrix_storage_closed.md`](run_matrix_storage_closed.md) (storage log) +
[`analysis_focus.md`](analysis_focus.md) Appendix A.
