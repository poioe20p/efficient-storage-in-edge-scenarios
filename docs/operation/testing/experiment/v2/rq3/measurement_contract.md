# RQ3 v2 — Measurement contract (post-calibration)

**Status:** calibrated ✅ — both arms validated (direct 20260804_224518, discovery 20260804_225812); all preflight gates and calibration arming gates green.
**Scope:** defines exactly what RQ3 v2 measures, from which artifacts, with which caveats — the pre-registered contract in `docs/research_questions/v2/rq3/rq3_preparation.md` §5, made concrete with the calibration numbers below. All campaign runs must satisfy the checks/gates here or be marked void per `rq3_v2_rework_plan.md` §2.5/§2.6.

---

## 0. Calibration baseline (2026-08-04, cloud-vm-rq3)

| Quantity | direct | discovery |
|---|---|---|
| run | `20260804_224518_rq3_calib_direct` | `20260804_225812_rq3_calib_discovery` |
| exit | 0 (all gates green) | 0 (all gates green) |
| admissions | 4 (lan1=2, lan2=2), `admit_source=event` ×4 | 4 (lan1=2, lan2=2), `admit_source=probe` ×4 |
| flow validation | C=0.91, A/B/D PASS | C=0.99, A/B/D PASS |
| gap requests (≥20/LAN gate) | lan1=769, lan2=285 | lan1=406, lan2=369 |
| event fraction (≥0.80 gate, direct) | **1.0** | 0.0 (by design) |

Run-level medians (from `rq3_admission_analysis.py`):

| Metric | direct | discovery |
|---|---|---|
| spawn→admitted (s) | **0.209** | **6.850** |
| scale-decision→1st success (s) | 11.029 | 8.466 |
| gap-window `timeout_rate` | 0.000 | 0.000 |
| gap-window `failure_rate` | 0.000 | 0.000 |
| useful initial share | 0.684 | 1.000 |
| transition latency p50/p95/p99 (s) | 0.015–0.026 / 0.036–0.063 / 0.074–0.139 | 0.017–0.018 / 0.036–0.062 / 0.091–0.380 |

**Reading:** the between-arm differential is carried by the **timing quantization** (event admission ≈ 33× faster to admit, 0.2 s vs 6.9 s), while the **service-consequence metrics are null** (0.000 gap timeouts/failures on both arms — pre-registered as a possible conclusion, not a post-hoc finding). The campaign's headline is the between-arm gap-window `timeout_rate` differential (see §3).

---

## 1. Latency

- **Definition:** per-request `latency_s` from `client_requests.csv`, restricted to `status=completed` (driver row-value contract: `timeout`→`http_status="000"`, `dropped`/`canceled` carry `latency_s=""` and are **excluded** from latency and failure, counted in offered only — `rq3_v2_rework_plan.md` G2/§1).
- **Reported windows:**
  - **Transition window** `[admitted, admitted + TRANSITION_WINDOW_S]` (default 60 s) — p50/p95/p99 + `gap_n`.
  - **Gap window** `[spawn_started, min(admitted, spike_end)]` — p50/p95/p99, `gap_to`/`gap_fr`, `gap_delta_pp`.
  - **Spike baseline** `[max(spawn_started − 60, spike_start), spawn_started]` — context only.
- **Censoring:** `CURL_MAX_TIME=300` s; any censored value is flagged `censored` and **never enters the MWU** (analysis_focus.md). Latency percentiles are descriptive with the censoring flag.
- **Calibration values:** transition p50/p95/p99 are sub-100 ms on both arms (0.015–0.026 / 0.036–0.063 / 0.074–0.380 s) — the edge tier is not the latency bottleneck; the differential RQ3 cares about is **timing**, not per-request latency.

## 2. Scale-up (readiness propagation timing)

- **Chain:** `decision ts` (ComputeAlert in `decision_log_*.csv`, nearest `ts` before `spawn_started_ts`) → `spawn_started` → `spawn_complete` → `admitted` → `first_flow` → `first_success`.
- **Primary outcome (D3):** `spawn_complete → admitted`. Reported as **raw per-run distributions** (never a fabricated `app_ready → admitted`).
- **Quantization caveats (pre-registered):** discovery `spawn_complete → admitted` is quantized to `[0, DISCOVERY_POLL_INTERVAL_S]` (10 s campaign); direct pays `~READINESS_PROBE_RETRY_S`; true app-ready is only observable at probe times (D3).
- **Calibration:** direct median 0.209 s vs discovery 6.850 s — a clean, measurable ~33× separation that survives any post-hoc join; `scale→1st success` 11.0 s vs 8.5 s (usable-capacity proxy).

## 3. Pre/post scale-up effect (the headline)

- **Headline metric:** pool-wide old-backend `timeout_rate` in the gap window `[spawn_started, min(admitted, spike_end)]` per LAN, **between-arm differential** (direct vs discovery) via the primary stats pair (Cliff's delta + MWU where defined).
- **Supporting set (≥2-of-3 same-direction consistency rule):** gap-window `failure_rate`, useful initial share (pool-wide gap+transition), scale-decision→usable-capacity.
- **Baseline for context:** spike-phase baseline `[max(spawn_started − 60, spike_start), spawn_started]`; `GAP_DELTA_PP=5` is a **context flag only** (degrading gap), not a gate and not a verdict.
- **Null is pre-registered:** the calibration already shows 0.000/0.000 gap timeouts/failures on both arms. If the campaign reproduces this, the honest conclusion is a **null on consequence metrics** and the claim narrows to the timing quantization — pre-registered in §2.7/§4.2, runs to completion either way.
- **Measurability gate (G1):** ≥ 20 attributed (completed+timeout) requests in the gap window per LAN per run (calibration: 285–769 ✓).

## 4. Throughput

- **Offered vs completed per phase:** from `client_requests.csv` (`status` column): `completed`, `timeout`, `dropped`, `canceled`.
  - `timeout_rate = timeout / offered` (the headline's failure dimension).
  - `dropped`/`canceled` counted in offered, **excluded** from latency+failure, reported separately.
- **Saturation sanity:** `resource_stats.csv` spike-phase compute CPU vs the `SCALEUP_CPU_FLOOR` (4.5%) — calibration spike averaged well above floor and fired scale-up; campaign runs must show the same (min-admissions gate + scale-up arming).
- **Calibration:** 3516/3510 offered with 0 reuse and C 0.91/0.99 — the driver, flow isolation, and load model are stable.

## 5. Load distribution

- **Per-backend request counts:** `backend_id` from `client_requests.csv`, **attributed rows only** (`backend_id != "unknown"`; parse-failed rows excluded from `first_flow`/`first_success` per preparation.md §5).
- **Pool-wide old vs new backend share:** useful initial share = fraction of gap+transition requests served by the newly admitted backend(s); direct 0.684 vs discovery 1.000 in calibration (discovery's longer gap means the old pool dominates until admit, then full handover).
- **Per-LAN distribution:** gap/transition counts emitted per LAN (`gap_requests_lan1/lan2`, no double-counting) — calibration 769/285 and 406/369.
- **Flow-isolation validity (Check D):** one fresh TCP connection per request (`source_port` freshness, ≤1% reuse) — a precondition for clean per-backend attribution; calibration 0 reuse.

---

## 6. Gates every campaign run must pass (else void per §2.6)

| Gate | Criterion | Calibration |
|---|---|---|
| G1 measurability | ≥ 20 gap requests/LAN both arms | ✓ |
| G2 min-admissions | ≥ 1 admitted backend per LAN | ✓ (2/LAN) |
| G3 event fraction (direct) | ≥ 0.80 event-driven | ✓ (1.0) |
| G4 flow validation | Check A/B/D hard, C ≥ 0.85 (amended 2026-08-05 from 0.9) | ✓ (0.91/0.99) |
| Env verification | controller + dynamic-edge `EDGE_APP_READY_EVENT`/`EDGE_FLOW_ISOLATION` | ✓ |
| Preflight | baseline 12/12, code 7/7, env 99/99 | ✓ |

---

## 7. Artifact → analyzer map

| Artifact | Contents | Consumer |
|---|---|---|
| `admission_log_lan{1,2}.csv` | one row per spawned compute backend: `spawn_started/completed`, `admitted_ts`, `admit_source`, `app_ready_ts` | `rq3_admission_analysis.py` |
| `decision_log_lan{1,2}.csv` | `scale_up` ComputeAlert rows | trigger join (nearest ts) |
| `client_requests.csv` | per-request `status/latency_s/backend_id/source_port/phase` | analyzer + `rq3_flow_validation.py` |
| `controller_lan{1,2}.log` | `request_complete: client flows deleted` (Check C) | `rq3_flow_validation.py` |
| `controller_env_snapshot.env` | arm ground truth (`READINESS_PROPAGATION`) + knobs | analyzer arm label, preflight |
| `phases_snapshot.json` | episode context (post-hoc join) | analyzer |
| `container_events.csv` | spawn/removal events (Check B) | `rq3_flow_validation.py` |
| `resource_stats.csv` | per-window CPU/requests (saturation sanity) | preflight/policy reconstruction |
