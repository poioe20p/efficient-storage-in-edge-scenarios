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
- Run folders: `source/scripts/testing/metrics/20260803_*_cgr_*` (pending).

## 6. Threshold retune (fork 2)

Median < mean under right-skew, so flipping the signal **systematically lowers**
the observed latency signal. Thresholds calibrated on the mean — storage
scale-up `τ_base=0.35` + `T_DB floor 60/span 250`, compute `τ_base=0.18` +
`T_proc floor 25/span 50`, scale-down `TAU_PROC_DOWN_MS=40` /
`TAU_DB_DOWN_MS=150` — may shift the operating point (expected: fewer
mean-inflated scale-ups, faster reclaims).

**Protocol (evidence-driven):**
1. Run the median-era control pair (§5) with the current thresholds.
2. From `resource_stats.csv` / `window_log.jsonl`, extract the median-era
   signal distributions (by phase: plateau / recovery_gap / demand_drop).
3. Retune floors/spans/τ so the median signal crosses the same operating
   points the mean did (or the retuned points the evidence supports).
4. Update `current_state_integrated.env`, RQ2 arm envs, and this doc with the
   new values + the evidence table.

**Status:** pending the §5 runs.

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
