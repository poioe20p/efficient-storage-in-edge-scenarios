# v2 Campaign — Experiment Plans

> The thesis-framing evaluation campaign (current `thesis_overview.md` framing).
> Contains the validated **control group** and the per-RQ evaluation campaigns.
> Parent index: [`../README.md`](../README.md).

## Layout

| Entry | Contents |
|---|---|
| [`control_group.md`](control_group.md) | Generic **scale-vs-no-scale control** (validated 2026-08-01). Referenced by RQ1/RQ2/RQ3 as the "does the platform work / what does scaling buy" reference. |
| [`control_group_retune/`](control_group_retune/) | Retune plan + results that produced the validated control config (caps 3/3, storage scale-down 30 s + 3/5 windows, `demand_drop` 420 s, plateau rate 5.0 locked). |
| [`post_implementation_verification/`](post_implementation_verification/) | V0–V4 pre-flight gates for the combined RQ1/RQ2/RQ3 implementation before each evaluation campaign. |
| [`rq1/`](rq1/) | **RQ1 — telemetry delivery semantics** campaign: experiment plan, run matrix, analysis focus, per-arm env files, analysis tooling. |
| [`rq2/`](rq2/) | **RQ2 — bottleneck-aware scaling action** campaign: experiment plan, run matrix, analysis focus, per-arm env files (3 policies), episode phase calibration, analysis tooling. |
| [`rq3/`](rq3/) | RQ3 — readiness propagation campaign (placeholder). |

## RQ1 note (rebase onto the control group)

RQ1 reuses the control group's workload and platform, varying only
`TELEMETRY_SOURCE`:

- **Workload:** `source/scripts/testing/phases_override/phases_stress_plateau.json`
  (1200 s: baseline → 600 s `compute_plateau` rate 5.0 → `recovery_gap` →
  420 s `demand_drop`). No per-RQ1 phase file.
- **Platform (from `current_state_integrated.env`, the control's scalable arm):**
  `EDGE_CPUS=0.15`, `STORAGE_CPUS=0.08`, caps 3/3, storage scale-down 30 s + 3/5,
  compute scale-down 180 s / 9 windows.
- **RQ1-only deviation (thesis §2):** Tier 1 selective sync, persistent reserves
  and cross-region storage are **disabled** — a config no control arm validates;
  RQ1 pre-flight G1 verifies scale-up still fires SS-off.
- **Arms:** A `event_preserving` · B `delayed_event_preserving` (`DELAY_S=30`) ·
  C `poll` (`POLL_INTERVAL_S=30`).
