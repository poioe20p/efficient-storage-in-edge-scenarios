# RQ3 v2 — Analysis Focus (pre-registered)

**Date**: 2026-08-04 · **Plan**: `rq3_v2_rework_plan.md` · **Status**: pre-registered (before any run)

## 1. Pre-registered hierarchy

### Headline (single pre-registered pair-metric)
- **`gap_timeout_rate_median`** — pool-wide (old-backend) `timeout_rate` over
  `[spawn_started, min(admitted, spike_end)]`, **direct vs discovery**.
  Where the quantization tail shows: discovery leaves new capacity dark up to
  one poll period longer, so old backends carry the saturated load longer.

### Supporting (pre-registered consistency rule)
- `gap_failure_rate_median` (completed-only),
- `useful_share_median` (share succeeding over
  `[spawn_started, admitted + TRANSITION_WINDOW_S]`, pool-wide),
- `scale_to_first_success_median_s` (scale-decision → usable capacity).

The headline verdict must be supported by **≥ 2 of 3** supporting metrics in
the same direction (Cliff's delta sign); otherwise the conclusion is
"mixed/ambiguous". No post-hoc metric selection.

### Secondary / manipulation checks
- `spawn_to_admitted_median_s` (quantization; must show `direct` ≤ `discovery`),
- `admitted_to_first_flow` (should be arm-identical — selection function fixed),
- flow-isolation coverage (Check C ≥ 0.85 — amended 2026-08-05 from 0.9)
  and one-connection-per-request (Check D ≤ 1%),
- `admit_source` event-fraction ≥ 0.80 in `direct` runs (instrumentation gate),
- post-admission confirming `/ready` probe (readiness-criterion identity).

### Sensitivity (secondary, descriptive + Cliff's delta only, no MWU)
- `discovery` vs `discovery_15` on all metrics above — quantization cost
  scales with the discovery period (robustness, not knob-dependence).
- Minimum: **≥ 2 defined runs/cell** (n=3 stated; a single void does not drop
  the comparison; achieved n reported).

## 2. Metric definitions

| Metric | Definition | Window | Min n per backend |
|---|---|---|---|
| `gap_timeout_rate` | `timeout / (offered − dropped − canceled)` | `[spawn_started, admitted]`, spike-phase | 20 |
| `gap_failure_rate` | `(completed & http != 200) / completed` | same | 20 (completed) |
| baseline `timeout_rate` | as above | `[max(spawn_started − 60, spike_start), spawn_started]`, spike-phase | 20 |
| `gap_delta_pp` | `(gap − baseline) × 100` | — | — (context flag ≥ 5 pp) |
| `useful_initial_share` | successes / offered | `[spawn_started, admitted + 30 s]`, pool-wide, spike-phase | — |
| `spawn_complete → admitted` | quantization | admission log | — (timing; no request-count min) |
| `admitted → first_flow` | first attributed request | attribution via `backend_id` | — |
| `scale-decision → first_success` | decision-log `scale_up`/ComputeAlert → first 2xx | attribution via `backend_id` | — |

## 3. Status-aware contract (open-loop driver)

- Failure = `status=completed` & `http_status != 200`.
- `timeout_rate` = `status=timeout` / (offered − canceled − dropped).
- `dropped`/`canceled` counted in offered, excluded from latency + failure,
  reported separately.
- Latency percentiles descriptive-only with a censoring flag (cap
  `CURL_MAX_TIME=300` s).

## 4. Units / denominators

- Experimental unit = the independent run; primary comparisons use run-level
  medians of per-backend values (per-run scatter reported).
- Void policy: < 1 admitted backend per LAN ⇒ void; ≤ 1 void/cell then
  missing-value exclusion; re-run takes the matrix position (no
  re-randomization).
- `controller_env_snapshot.env` `READINESS_PROPAGATION` = arm ground truth;
  `DISCOVERY_POLL_INTERVAL_S` distinguishes `discovery`/`discovery_15`.

## 5. Censoring rule

No censored value enters MWU. `CURL_MAX_TIME=300` s; latency percentiles are
descriptive only (censoring flag where the cap binds). The per-run
`timeout_rate` is the primary degradation statistic and is defined for every
run.

## 6. Stats contract (mirrors `rq2v2_p2_03_stats.py`)

- Two-sided MWU (exact enumeration when n_a + n_b ≤ 16) + Cliff's delta.
- **No confidence intervals**.
- Primary pair: ≥ 3 defined runs/cell. Sensitivity: ≥ 2.
- Polarity normalized per metric (lower-is-better vs higher-is-better).
- Conclusions rest on Cliff's delta ≥ 0.6 + direction consistency; MWU p
  reported descriptively.

## 7. Calibration guard (Phase 4.1)

The direct arm's gap window (`[spawn_started, admitted]` ≈ app-startup + event
latency) can be short, so the ≥ 20 gap-request gate may be undefined for the
very arm it measures. The Phase-4.1 open-loop calibration criterion must verify
≥ 20 gap-window requests per LAN in a `direct` calibration run (spike rate
sufficient for a long enough gap window), and the chosen rate recorded.
