# Finding — Mean vs Median Latency Decision Signal (2026-08-03)

> **Status:** ⚙️ **Fix implemented (code + config) · Re-validation running** · **Date:** 2026-08-03
> **Scope:** All latency-based controller decision signals (scale-up + scale-down,
> compute + storage). Gated by `LATENCY_SIGNAL_MODE` (default `mean`).
> **Impacted config:** [`current_state_integrated.env`](../../../../source/scripts/testing/controller_env_overrides/current_state_integrated.env)
> (control-group scalable arm), `ablation_noscale.env`, RQ2 arm env files
> (`docs/operation/testing/experiment/v2/rq2/env/`). **RQ1 is deliberately
> excluded** (see §4).

---

## 1. The flaw (mechanism)

The controller's decision signals consumed the **mean** of the per-request
latency over each telemetry window (`avg_time_proc_ms`, `avg_time_db_ms`).

Latency is **right-skewed with unbounded outliers** (a single request can take
seconds, or time out entirely under `CURL_MAX_TIME=30`). In a **low-volume
window** — where the request count is small — **one slow request can dominate
the mean**, pushing it far above the latency the service actually experiences
most of the time. The sliding-window hit counter then records a "bad" window
even though the *typical* request was healthy.

The severity scales with **request volume**:

- **High-volume window:** one outlier is diluted (mean ≈ typical latency) →
  low distortion.
- **Low-volume window:** one outlier can move the mean by orders of magnitude →
  high distortion. The contamination is worst exactly where a scale decision
  should *not* fire (the service is idle, not degraded).

CPU signals (`average_cpu_percent`, `avg_storage_cpu_percent`) do **not** share
the exposure: CPU is **bounded 0–100%**, so a single sample cannot produce a
27-second-style outlier.

## 2. Evidence

### 2.1 RQ2 compute-bound episode (the trigger)

The RQ2 data-bound/compute-bound workload includes an episode where the
compute tier is saturated while **DB traffic is essentially zero**. In that
episode the DB latency mean (`avg_time_db_ms`) is computed over a handful of
requests; a single slow request inflated it to the tens-of-seconds range while
the DB was otherwise idle. A mean-based storage signal then recorded
storage-degraded windows that the median-based view does not — a false
"storage is the bottleneck" reading that can distort the bottleneck-aware
action selection and trigger unnecessary storage scale-up.

The episode is the **worst case** for mean-vs-median: zero-to-tiny DB traffic
means outliers dominate the mean with nothing to dilute them.

### 2.2 RQ1 exposure check (2026-08-03, `tools/rq1_storage_contamination.py`)

RQ1 used the **identical latency-only, mean-based storage signal** (controller
init log: `storage[τ_base=0.35 … w_cpu=0.0 w_lat=1.0 window=2/5]`, same as RQ2),
so it had the same theoretical exposure. The artifact check found:

1. **RQ1's workloads always touched the DB** — every phase (`storage_storm`,
   `tier1_hotspot`, …) includes DB reads/writes. RQ1 never had RQ2's worst case
   (a DB-free high-load episode). Contamination in RQ1 distorts *on top of* real
   pressure; it cannot cause false fires in a DB-idle scenario (which never
   occurred).
2. **RQ1's question is not about scaling precision** (delivery modes vs
   latency/staleness); storage scaling is a supporting mechanism, so
   mean-outlier over-scaling is peripheral to RQ1's headline results.
3. In the sampled RQ1 `push_1` run, recorded storage behavior does **not**
   cleanly match the contamination pattern (14 "triggered" windows showed
   `storage_latency_signal_ms ≈ 0`, `avg_time_db_ms ≈ 1.4–2.8 ms` — unpopulated
   signal, not obviously inflated).

**Conclusion on RQ1:** a claim that "RQ1 was distorted, must re-run" is **not
supported** by the artifacts. RQ1 is gated (see §4), not re-run.

## 3. Decision — median for all latency signals

| Signal | Before | After (`LATENCY_SIGNAL_MODE=median`) |
|---|---|---|
| Compute scale-up (`compute_latency_signal`) | mean | **median** (`median_time_proc_ms`, fallback mean) |
| Storage scale-up (`storage_latency_signal`) | mean | **median** (`median_time_db_ms`, fallback mean) |
| Compute scale-down (ceiling + `< TAU_PROC_DOWN_MS`) | mean | **median** (same signal as scale-up) |
| Storage scale-down (ceiling + `< TAU_DB_DOWN_MS`) | mean | **median** (same signal as scale-up) |
| CPU (compute / storage) | mean | **mean (unchanged)** — bounded 0–100%, no outlier exposure |

**Why all four latency signals:** they share the same right-skew/outlier
exposure; fixing only storage scale-up would leave the scale-down arms and
compute scale-up inconsistent with the corrected signal. Consistency also makes
the RQ2 **G2 bottleneck-validation median** (already median-based in the plan)
agree with the controller's own classification signal.

**Implementation (gated):** the aggregator already publishes
`median_time_proc_ms` / `median_time_db_ms` in every `domain_summary`
(`source/docker/local_state_server/aggregator.py`); the controller's
`DomainSummary` model now carries them (optional → fallback to mean for
pre-median aggregators), and `scaling_policy.py` selects the statistic from
`LATENCY_SIGNAL_MODE`. Default is **`mean`** → RQ1 byte-identical.

## 4. RQ1 gate (reproducibility)

- RQ1 arm env files set **`LATENCY_SIGNAL_MODE=mean` explicitly** (a no-op at
  runtime — mean is the default — but it makes the captured
  `controller_env_snapshot.env` provenance unambiguous).
- RQ1's code path is therefore **byte-identical** to the archived runs; RQ1
  results remain valid and reproducible.
- The mean→median change is documented as an **RQ2+ / control-group
  signal-robustness calibration** — a legitimate, documented improvement
  between experiments, not a retroactive invalidation of RQ1.

## 5. Control-group reset (fork 1)

The control group (`current_state_integrated.env`, scalable arm) was **reset**
to the corrected signal: `LATENCY_SIGNAL_MODE=median` (header G0-v2 → G0-v3).
`ablation_noscale.env` (no-scale arm) sets the same flag so the ablation
isolates only the capacity knobs.

**Caveat:** the control-group tables in [`control_group.md`](control_group.md) §5
were produced on 2026-08-01 under **mean-driven** signals and are **not** a
description of the current control until re-validated. Re-validation pair:

- `cgr_scalable` (median scalable arm) and `cgr_noscale` (median no-scale arm),
  per the [control-group retune plan](control_group_retune/experiment_plan.md)
  run matrix (gates G1–G6).
- Median-era run folder: `source/scripts/testing/metrics/20260803_001705_cgr_scalable`
  (in progress; plateau + recovery captured).

## 6. Threshold retune (fork 2) — implemented 2026-08-03

**Retune intent:** re-anchor the storage latency normalization to the median
statistic's scale so the median-era control reproduces the mean-era operating
envelope (same mechanism exercise: storage adds ~4-5/LAN cap-bounded, reserve
activations, in-window reclaim) while staying robust to the tail outliers that
contaminated the mean.

**Evidence (median-era control run `20260803_001705_cgr_scalable`, resource_stats.csv):**

| Phase | median T_db p25 | p50 | p75 | p90 |
|---|---|---|---|---|
| compute_plateau | 4.8 | 15.4 | 206 | 3293 |
| recovery_gap | 0.0 | 2.6 | 610 | 12015 |
| demand_drop (early) | — | 82.6 | — | — |

- Plateau median T_db ≈ 15 ms vs mean-era ≈ 650 ms → the mean-era normalization
  (floor 60 / span 250; crossing 147.5 ms) under-fires storage under the median
  (storage reached 2-3/LAN vs the mean-era ~4-5 adds/LAN).
- demand_drop median ≈ 82 ms → `TAU_DB_DOWN_MS` must stay > 82 ms to reclaim
  in-window; **150 ms is retained** (same margin as mean-era).
- Compute is **unaffected**: the compute score is CPU-dominated (`W_CPU=0.60`);
  the proc-latency component sits below floor in both eras. Verified score≥τ
  fraction 0.983 mean vs 0.983 median.

**Decision (storage-only re-anchor):**

| Knob | Mean-era | Median-era (new) | Crossing |
|---|---|---|---|
| `SCALEUP_T_DB_FLOOR` | 60 | **10** ms | — |
| `SCALEUP_T_DB_SPAN` | 250 | **50** ms | 10 + 0.35×50 = **27.5 ms** |
| `TAU_DB_DOWN_MS` | 150 | **150** (retained) | demand_drop median ≈ 82 ms |
| τ_base storage | 0.35 | 0.35 (unchanged) | — |

Applied to `current_state_integrated.env`, `ablation_noscale.env`, and the RQ2
arm envs. RQ1 keeps mean-scale thresholds (60/250) with the mean signal.

**Verification:** the retuned config is validated by a re-run of the control
pair (`cgr_scalable`/`cgr_noscale`) with the new thresholds — expected: storage
reaches ~3 active + reserve (~4-5 adds/LAN), in-window reclaim in demand_drop,
compute 3-4/LAN, service metrics comparable to the mean-era §5 tables.

## 7. Out of scope (flagged, not changed)

- **WSM request routing** (`main_n1.py`/`main_n2.py` server selection uses
  `avg_time_proc_ms`/`avg_time_db_ms` as per-server cost). This is a
  **routing** decision (which backend gets the next request), not a capacity
  decision; a mis-route is self-correcting and low-stakes versus a scale
  action. Flagged here so it can be revisited if the thesis argues routing
  quality.
- **Reporting columns** `avg_time_proc_ms`/`avg_time_db_ms` in
  `resource_stats.csv` historically carry the aggregator's **median** (misnamed
  columns, kept for tooling compatibility). After this fix they mirror the
  decision signal in median mode; `storage_latency_signal_ms` was aligned to the
  decision signal (median, mean-of-nodes fallback).

## 8. References

- [`control_group.md`](control_group.md) — control-group reset + mean-era caveat
- [`control_group_retune/experiment_plan.md`](control_group_retune/experiment_plan.md) — re-validation run matrix + gates
- `source/sdn_controller/scaling_policy.py`, `scaling_config.py`, `telemetry/models.py`
- `source/scripts/testing/collect_resource_stats.py`
- `tools/rq1_storage_contamination.py` — RQ1 exposure check tool
