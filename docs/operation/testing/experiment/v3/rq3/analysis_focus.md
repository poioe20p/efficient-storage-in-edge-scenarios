# RQ3 v3 — Analysis Focus: Compute Saturation Campaign (pre-registered)

Part of [`experiment_plan.md`](experiment_plan.md). **Status (2026-08-09):**
compute saturation campaign **PLANNED — ready to launch** (n=7/arm, 14 runs,
config P4). Pre-registered analysis contract for the campaign — decided
**before** results are known. Storage extension **CLOSED** (see Appendix A).

## 1. Headline claim (campaign) — scale-up relieves the compute tier

- **R1 (primary, B1 CPU leg)**: old-backend compute CPU drops **≥ 10 pp**
  `[spawn−60, spawn]` → `[admitted+10, admitted+70]` (steady-state, plateau).
  Preflight already showed this at n=2/arm: **direct −18.9/−10.3 pp,
  discovery −32.5/−26.7 pp**. Campaign decides the headline at n=7/arm.
- **R2**: old-backend T_proc drop (supporting).
- **R3**: pool latency p50/p95 drop or stable-not-worse (secondary; latency
  is NOT the required leg — CPU is).
- **Statistical contract (pre-registered)**:
  - Unit = RUN; per-run medians over that run's steady-state admissions.
  - Cross-arm (n=7 vs 7): **exact MWU (permutation) + Cliff's δ** on per-run
    relief values.
  - Within-run: **paired sign test** on per-admission (pre, post) relief.
  - Paired by block: **paired exact permutation** (direct_N vs disc_N share
    block seed N, `counterbalance_order.csv`).
  - Success: majority of admissions relieved per run, and cross-arm relief
    positive with p < 0.05.
- **PG-2 re-framing (pre-registered)**: saturation gate re-anchored to
  **pooled sub-max CPU ≥ 30 % AND relief ≥ 10 pp**. ~40 % is the documented
  compute-pure ceiling (autoscaler fires at 70–88 %, so the tier cannot be
  pressed further without the DB co-bottleneck that nullifies relief).

## 2. Timing claim — direct vs discovery readiness propagation (re-confirm)

- **T1**: `ready → admitted` — direct ≈ 0.001–3 s (event) vs discovery
  ≈ 5–7 s (10 s poll + fallback 20 s). Expected d ≈ −1.000 (v2: d=−1.000,
  n=6). Campaign re-confirms at the saturation config.
- **T2**: `spawn → first success` — direct faster; absolute differential ≥ v2.
- **C1 (consequence, pre-registered NULL + autoscaler-bounded)**: gap-window
  `[spawn_started, min(admitted, plateau_end)]` timeout_rate = **0.000** in
  both arms. The tier is admission-gated and the autoscaler caps the ceiling
  (fires at 70–88 %), so a timing differential cannot convert into sustained
  user-visible harm. Reported, not a gate.
- **C2**: gap-window failure_rate = null.

## 3. Base-requirements gates (per `testing_requirements.md`, per run)

- **G1** ≥ 20 gap requests/LAN · **G2** ≥ 1 admitted backend/LAN ·
  **G3** direct event fraction ≥ 0.80 · **G4** flow checks A/B/D hard, C ≥ 0.85
- **G5** driver clean (canceled < 5 %, http000 ≈ 0 baseline) · **G8** no
  plateau scale-down churn
- **D1** `NotPrimary` = 0 · **D2** no restart/crash · **D3** provenance
  snapshots (phases + env) per run
- **M1** scale-up fires per LAN · **M2** added nodes serve ≥ 1 request
- **V1** compute CPU rises in plateau (bottleneck evidenced)
- **I1** ≥ 5 000 completed plateau/LAN · **I2** outcome classes distinct
- **PG-1** driver clean · **PG-2** re-anchored sub-max CPU ≥ 30 % ·
  **PG-3** ≥ 1 add/LAN · **PG-6** no collapse

## 4. Mechanism checks (supporting)

- Relief is **window_log-authoritative** (`rq3sat_relief_windowlog.py`),
  cross-checked with `rq3_camp_prepost_resources.py --steady-s 120`
  (resource_stats).
- Autoscaler interaction: relief must come from scale-up, not from load
  drop — confirmed by steady-state plateau (rate held 72 req/s across the
  admission window) and G8 (no scale-down churn mid-plateau).
- Do not over-index on absolute CPU band; rely on the pre/post relief delta
  (run-to-run absolute CPU is noisy).

## 5. Expected outputs

Per-run analyzer (`rq3_admission_analysis.py`, phase=`compute_plateau`) →
T1/T2/C1/C2 per run; relief tools → R1/R2/R3; gates via `rq3sat_probe_gate.py`.
Campaign deliverables: `results.md`, `post_run_analysis.md`, graphs
(`relief_cpu_prepost.png`, `timing_campaign.png`, saturation family), then
thesis update in `tese/research_questions/rq3/*`.

---

## Appendix A — Storage analysis focus (CLOSED, 2026-08-08)

The storage-replica scale-up extension was closed after a 4-run preflight
showed **no sustained benefit** (honest SG-4 medians P2 +3.6 %, P1-fix
+0.6 %, P2-fix −1.9 %; P1's +38.2 % was a proven early-plateau transient
artifact). R-stor-3 (read offload) passed all 4 runs but never converted
into user-visible benefit; storage primary CPU stayed ~50–65 % (no relief).
Per governance rule RQ3-storage-3 → **storage should not scale → no storage
campaign**. Full storage analysis contract (T-stor-1 delivery differential,
C-stor-1 catch-up-dominated null, R-stor gates, D1 watch on the M1
153-occurrence reconfig burst) is retained in git history of this file and in
[`experiment_plan_storage_closed.md`](experiment_plan_storage_closed.md).
