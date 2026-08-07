# RQ3 v3 — Analysis Focus (storage-replica benefit)

Part of [`experiment_plan.md`](experiment_plan.md). What the campaign must
establish, and the pre-registered claims it will support. Follows the
v2/rq3 `C9` honest-null precedent: a null consequence is acceptable if the
mechanism is explained; the claim then narrows to the timing/benefit layer.

## 1. Headline claim — storage scale-up benefits (the governance verdict)

- **RQ3-storage-3 / V-stor-1**: storage **should scale** under the locked
  read-write mix because replica admission measurably relieves the primary
  (probe evidence: SG-4 PASS 4/4, p95 relief +17.5…+44.7 %).
- Campaign must confirm: **SG-4 benefit reproduces at n=6/arm** (median
  relief ≥ 10 %, direction consistent across seeds 3001–3006).
- Anti-claim (the thesis's governance rule): if relief disappears at campaign
  scale → storage should **not** scale (oplog load without relief) — the
  negative-benefit finding is the deliverable.

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

- **R-stor-2** primary CPU / write latency drop pre → post.
- **R-stor-3** read offload: replica request share rises after admission.
- **R-stor-4** replica RAM / member count sane growth.
- Pressure band (V1): plateau p95 is run-to-run noisy (1.2–11.2 s in probes);
  do not over-index on the band magnitude, rely on the pre/post relief delta.

## 5. Expected campaign outputs

`results.md` (pre-registered metric table + gates G1–G8), `post_run_analysis.md`
(trace objective → mechanism → result), graphs under `graphs/` (latency by
arm, relief per run, timing differential, read distribution).
