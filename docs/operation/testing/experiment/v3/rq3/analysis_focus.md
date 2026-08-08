# RQ3 v3 — Analysis Focus (CLOSED: compute-only verdict, storage benefit null)

Part of [`experiment_plan.md`](experiment_plan.md). **Status (2026-08-08):**
storage-replica scale-up evaluated via a 4-run preflight → **no measurable
benefit** → storage extension **closed, not carried forward**. RQ3's thesis
claim is evaluated on **compute only** (complete).

## 1. Headline claim — storage scale-up does NOT benefit (governance verdict)

- **RQ3-storage-3 / V-stor-1 (DECIDED)**: storage **should not scale** under
the locked read-write mix. The 4-run preflight showed **no sustained
benefit**: honest SG-4 medians P2 +3.6 %, P1-fix +0.6 %, P2-fix −1.9 %
(FAIL); P1's +38.2 % was a proven early-plateau transient-spike artifact.
Both arms' steady-state plateau p95 converge to ~1.1–1.2 s; storage primary
CPU stays ~50–65 % (no relief). R-stor-3 passes in all 4 runs (reads do
offload) but the offload never converts into user-visible latency/CPU
benefit.
- **No storage campaign** is run; the negative-benefit finding is the
deliverable (elastic capacity is wasted and only adds oplog load).
- **RQ3 thesis claim = compute only** (readiness propagation, complete): the
storage extension is closed and not carried forward.

## 2. Propagation claim — direct vs discovery timing (secondary)

- **T-stor-1**: `SECONDARY → promoted` delivery latency — direct **0.00 s**
  (event, measured 29/29) vs discovery **1.0–6.0 s** (telemetry window, avg
  ~3.9 s, measured 9/9). Campaign confirms the delivery-layer differential.
- **C-stor-1 (consequence)**: expected **null** — `spawn → promote` totals
  are dominated by the RS initial-sync catch-up (~35–41 s) in both arms, so
  no gap-window latency/timeout excess is measurable within the 600 s
  plateau. This is a mechanism-backed null (catch-up dominance), NOT
  under-saturation — mirroring the v2/rq3 conclusion.
- **No designed-cadence arm**: a slower discovery cadence would be a
  tautological knob-setting, not a system property.

## 3. Base-requirements gates (per `testing_requirements.md`)

- **D1** data path: controller + storage/server `NotPrimary` = 0 (⚠ M1 had a
  153-occurrence transient burst at RS-reconfig on `edge_server_n2` — did not
  reproduce; watch for recurrence and flag if it does).
- **D2** no restart/crash; **D3** provenance snapshots (phases + env) per run.
- **F1** telemetry continuity (plateau resource rows ≈ 45–50/2 LANs);
  **F2** LAN symmetry (offered lan1 ≈ lan2).
- **I1** demand ≈ 8.3–8.5 k completed plateau requests/run; **I2** outcome
  classes counted distinctly (completed/timeout/canceled).

## 4. Mechanism checks (supporting)

- **R-stor-3 is a HARD co-gate** (per-run + cross-run per mode): PRIMARY
  connection share (window_log) must drop ≥ 20 % relative OR land ≤ 60 %
  post-admission. SG-4 benefit counts only when it passes — latency relief
  without read offload is unexplained and does not count.
- **R-stor-2** primary CPU / write latency drop pre → post.
- **R-stor-4** replica RAM / member count sane growth.
- Pressure band (V1): plateau p95 is run-to-run noisy (1.2–11.2 s in probes);
  do not over-index on the band magnitude, rely on the pre/post relief delta.

## 5. Expected outputs (revised — storage campaign not run)

`run_matrix.md` §3 (preflight record + closed verdict), plan §5.4 (4-run
preflight verdict + artifact investigation), and this document replace the
storage campaign outputs (results.md / post_run_analysis.md / graphs for the
12-run storage matrix). The compute RQ3 campaign outputs already exist
(`tese/research_questions/rq3/rq3_evaluation_conclusions.md`).
