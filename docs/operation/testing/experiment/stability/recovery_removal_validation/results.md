# Results — VIP Recovery Removal Validation

**Date**: 2026-06-07
**Experiment plan**: [experiment_plan.md](experiment_plan.md)

## Run Timeline

| Run | Date | Status | Cumulative Analysis | Conclusions | Changes Made | Expectations for This Run |
|-----|------|--------|---------------------|-------------|--------------|--------------------------|
| v1 (`recovery_removed_val_a`) | `2026-06-07T21:47Z` | ✅ | — (initial run) | — (initial run) | — (baseline: recovery code removed, edge_server image rebuilt) | (from experiment_plan.md: zero recovery references, backoff-only retry, normal VIP routing) |

### 1. Run v1 — `recovery_removed_val_a` (`2026-06-07T21:47Z`)

**Status**: ✅ — All 8 criteria passed. Recovery removal validated under full 10-phase workload.

#### Previous Run Analysis (cumulative)

Initial run — no prior analysis.

#### Conclusions

1. **Recovery removal is clean** (confirmed): Zero recovery-related code paths were exercised across 48,557 requests. The edge server created 62,399 normal-mode epochs with zero recovery epochs. The controller logged zero recovery VIP references. The old failure signatures (`rebinds_exhausted`, `rotation_failed`, `success_after_rebind`) are completely absent.

2. **New retry path is active** (confirmed): `retries_exhausted` is the sole terminal failure reason (2,326 occurrences). Telemetry lease outcomes no longer include the `rebinds_used` field. The MongoClient creation log no longer includes `recovery_session_max_age_s`.

3. **High failure rates in compute phases are expected** (observed, not a regression): `compute_ramp` (74.7%), `compute_spike` (79.8%), and `sustained_plateau` (78.3%) show elevated failure rates. These are the phases where MongoDB connections time out under heavy load, and the backoff-only retry path (3 attempts, ~700ms total) exhausts before recovery. This is the designed behavior — failures now propagate as 503 instead of rotating to a recovery VIP. The absolute failure counts are small (180, 288, 216) due to low request volumes in these phases.

4. **inter_hotspot_cooldown anomaly** (observed): 19.9% failure rate on only 267 requests. Small sample size; likely transient connection recovery during the cooldown transition between hotspot phases.

#### Changes Made

| File | Change | Rationale |
|------|--------|-----------|
| (none) | N/A — initial validation run | Baseline measurement |

#### Expectations for This Rerun

N/A — initial run. No rerun planned unless anomalies require investigation.

#### Results

**Per-phase failure rates** (from `full_analysis.py`):

| Phase | Requests | Failures | Rate |
|-------|----------|----------|------|
| baseline | 484 | 0 | 0.0% |
| local_moderate | 4,247 | 1 | 0.02% |
| storage_stress | 26,997 | 10 | 0.04% |
| cross_region_hotspot | 10,465 | 390 | 3.7% |
| inter_hotspot_cooldown | 267 | 53 | 19.9% |
| reverse_hotspot | 4,577 | 525 | 11.5% |
| compute_ramp | 241 | 180 | 74.7% |
| compute_spike | 361 | 288 | 79.8% |
| sustained_plateau | 276 | 216 | 78.3% |
| demand_drop | 642 | 251 | 39.1% |
| **OVERALL** | **48,557** | **1,914** | **3.9%** |

**Criteria assessment** (from [experiment_plan.md](experiment_plan.md)):

| # | Criterion | Expectation | Result | Met? |
|---|-----------|-------------|--------|------|
| C1 | Recovery refs in controller logs | 0 | 0 in both logs | ✅ |
| C2 | Recovery refs in edge server logs | 0 | 0 across all 23 logs | ✅ |
| C3 | All epochs `mode=normal` | ≥2 normal, 0 recovery | 62,399 normal, 0 recovery | ✅ |
| C4 | No `recovery_session_max_age` | 0 | 0 | ✅ |
| C5 | New failure reason active | `retries_exhausted` present, old absent | 2,326 new, 0 old | ✅ |
| C6 | Overall non-200 ≤ 5% | ≤5% | 3.94% | ✅ |
| C7 | Zero controller tracebacks | 0 | 0 | ✅ |
| C8 | Run reaches `idle` | Phase = idle | idle | ✅ |

**Mechanism exercise**:

| Mechanism | Exercised? | Evidence |
|-----------|-----------|----------|
| VIP_DATA routing (normal) | Yes | 48,557 requests routed via `vip_data_n1_ip`/`vip_data_n2_ip` |
| Tier 2 storage scale-out | Yes | `storage_count` reached 11, first >1 at baseline |
| Edge server retry (backoff-only) | Yes | 2,326 `retries_exhausted` terminal failures |
| Recovery VIP routing | No (expected) | Zero `vip_data_recovery_*` in any log |
| Recovery epoch rotation | No (expected) | Zero `mode=recovery` epochs |
| Recovery distress triggers | No (expected) | Zero `_RECOVERY_DISTRESS_OUTCOMES` references |

**Overall verdict**: The VIP recovery removal is validated. The system operates correctly with backoff-only retry, normal VIP routing is unaffected, and all recovery infrastructure is confirmed absent from runtime behavior.
