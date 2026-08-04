# RQ3 v2 — Experiment Plan (final evidence)

**Date**: 2026-08-04 · **Plan**: `rq3_v2_rework_plan.md` · **Status**: 🔵 Plan — Phase 6 (campaign) pending on `cloud-vm-rq3`
**Execution VM**: `cloud-vm-rq3` (dedicated RQ3 VM; setup status to be verified before pre-flight)

## 1. Objective

Characterize how readiness propagation (event-driven `app_ready` push vs
periodic `/ready` discovery) affects when a ready backend becomes **usable
capacity**, measured as the service-level consequence of the admission gap and
the timing quantization.

## 2. Arms and hypotheses

| Arm | Propagation | Discovery interval | n |
|---|---|---|---|
| `direct` | event-driven `app_ready` push (no probe before admission) | — | 5 |
| `discovery` | periodic `/ready` scan | 10 s | 5 |
| `discovery_15` | periodic `/ready` scan (sensitivity) | 15 s | 3 |

| # | Hypothesis | Status |
|---|---|---|
| H1 | `direct` ≤ `discovery` on gap-window pool `timeout_rate` (headline) | primary |
| H2 | `direct` ≤ `discovery` on gap-window `failure_rate`, useful initial share (≥), scale-decision → usable-capacity | supporting (≥ 2-of-3) |
| H3 | Quantization `spawn_complete → admitted`: `direct` ≤ `discovery` | manipulation check |
| H4 | Quantization cost scales with `DISCOVERY_POLL_INTERVAL_S` (`discovery` ≤ `discovery_15`) | sensitivity, Cliff's delta only |
| H5 | `admitted → first_flow` arm-identical (selection function held fixed) | manipulation check |

## 3. Success criteria (C1–C9)

- C1: all runs exit 0; 0× `NotPrimaryOrSecondary`; no controller restart.
- C2: per-arm env verification — `READINESS_PROPAGATION`, cadence knobs
  (`READINESS_PROBE_RETRY_S`, `DISCOVERY_POLL_INTERVAL_S`), `VIP_FLOW_ISOLATION`
  from env snapshot; `EDGE_FLOW_ISOLATION`, `EDGE_APP_READY_EVENT`, `BIND_PORT=5000`
  from edge containers; driver knobs from the run-log config line.
- C3: min-admissions gate — ≥ 1 admitted backend per LAN per run.
- C4: flow-validation gate — Check A/B hard, C ≥ 0.9, D ≤ 1%.
- C5: gap-window measurability — ≥ 20 gap-window requests per LAN in both arms.
- C6: `direct` runs event-driven fraction ≥ 0.80 (`admit_source=event`).
- C7: readiness-criterion identity — post-admission confirming `/ready` probe.
- C8: headline + supporting stats on the pre-registered pairs with exclusions
  recorded; conclusion rule (≥ 2-of-3 consistency) applied.
- C9: honest null accepted — if no between-arm differential on consequence
  metrics, the claim narrows to the timing quantization (pre-registered).

## 4. Held fixed (identical across arms)

Readiness criterion (`app_ready` flag via `/ready` and the event), WSM routing
weights, `BACKEND_SELECTION_POLICY=topology_host`, `VIP_WARM_SERVER_SECONDS=0`
(no warm lease, no slow-start), telemetry `event_preserving` (RQ1 reference),
`SCALEUP_POLICY=dual` (RQ1 reference), compute-bound workload
(`phases_rq3_compute_episode.json`), Tier 1 / reserves / cross-region disabled.

## 5. Gates

`make driver_selftest` (shared) · `make rq3_analyzer_selftest` · `make
rq3_app_ready_selftest` · concurrency stress check · G2 calibration under
open-loop (`dropped` decision rule) · gap-window measurability gate ·
min-admissions arming · per-arm env verification · legacy `sync`-mode
regression smoke. Blocks do not start until all pass.

## 6. Artifacts / ack convention

`admission_log_lan1/lan2.csv` (required, both arms; `admit_source` column) ·
`client_requests.csv` (open-loop, status + phase) · `decision_log_*.csv` ·
`phases_snapshot.json` · per-run analyzer + flow-validation reports ·
`counterbalance_order_v2.csv`.

## 7. Relationship to other evidence

RQ3 is the third control-loop interface (routing admission); RQ1/RQ2 v2
campaigns are the other two. Superseded old-RQ3 (trigger-composition)
artifacts remain supporting calibration evidence only.
