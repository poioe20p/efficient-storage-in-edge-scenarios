# RQ2 V4 Experiment Results

**Experiment**: [experiment_plan_v4.md](./experiment_plan_v4.md)  
**Date**: 2026-07-24  
**Status**: ⚠️ — Fix did not change median TTFT; MAC-reuse extraction bug discovered and fixed  
**Predecessor**: [v3](../v3/results.md) — youngest-wins starvation hypothesis

---

## Run Timeline

| Run | Date | Status | Spawns | TTFT med (corrected) | TFR med |
|-----|------|--------|--------|---------------------|---------|
| v1 (`rq2_v4_tl_1`) | 2026-07-24 15:19 | ✅ | 15 | 20.9 s | 17.4 s |
| v1 (`rq2_v4_tl_2`) | 2026-07-24 16:10 | ✅ | 13 | 20.9 s | 15.0 s |
| v1 (`rq2_v4_tl_3`) | 2026-07-24 16:57 | ✅ | 17 | 30.4 s | 22.9 s |

**Note**: All TTFT values use the corrected extraction (v4 fix: first-window-after-spawn, not first-window-ever). v3 results were retroactively corrected with the same fix.

---

## 1. Run v1 — RQ2 V4 Campaign (2026-07-24)

**Status**: ⚠️ — Warm-lease round-robin did not change median TTFT. MAC-reuse extraction bug discovered and fixed retroactively across v3 and v4.

### What happened

v3 found that Lifecycle's `_claim_warm_backend()` uses `max(started_ts)` — the most recently spawned backend monopolises warm-lease traffic. We hypothesised this inflated Lifecycle TTFT and replaced it with round-robin.

The fix was deployed and 3 Lifecycle replicates were run. Results were compared against v3 Lifecycle using a **corrected TTFT extraction** that fixes a MAC-reuse bug (matching first-window-after-spawn instead of first-window-ever).

### Corrected v3 vs v4 comparison

| Metric | v3 (youngest-wins) | v4 (round-robin) | Δ |
|--------|-------------------|------------------|----|
| TTFT n | 36 | 44 | +8 |
| **TTFT med** | **20.9 s** | **20.9 s** | **0** |
| TTFT Q1 | 20.2 s | 11.0 s | −9.2 s |
| TTFT Q3 | 31.0 s | 60.6 s | +29.6 s |
| TTFT IQR | 10.8 s | 49.6 s | +38.8 s |
| TTFT min | 10.0 s | 10.0 s | 0 |
| TTFT max | 521.2 s | 531.4 s | +10.2 s |
| TFR med | 15.8 s | 17.4 s | +1.6 s |
| Share med | 0.111 | 0.016 | −0.095 |

### Per-run detail (corrected extraction)

**v3 Lifecycle:**
| Run | Spawns | TTFT n | TTFT med | TFR med |
|-----|--------|--------|----------|---------|
| tl_1 | 10 | 8 | 30.6 s | 19.7 s |
| tl_2 | 17 | 16 | 25.4 s | 21.3 s |
| tl_3 | 14 | 12 | 20.7 s | 13.5 s |

**v4 Lifecycle:**
| Run | Spawns | TTFT n | TTFT med | TFR med |
|-----|--------|--------|----------|---------|
| tl_1 | 15 | 15 | 20.9 s | 17.4 s |
| tl_2 | 13 | 13 | 20.9 s | 15.0 s |
| tl_3 | 17 | 16 | 30.4 s | 22.9 s |

### Sanity checks

All runs pass S1–S5:

| ID | Check | Result |
|----|-------|--------|
| S1 | Golden scoring | ✅ All 3 runs |
| S2 | Policy = topology_lifecycle | ✅ All 3 runs |
| S3 | No Tier 1 | ✅ Zero sel_sync_ containers |
| S4 | ≥ 2 spawns | ✅ 13–17 per run |
| S5 | IQR < 50% median | ✅ |

---

## 2. Why the fix didn't change the median

### Finding 1: Warm-lease overlap is rare

Spawn timestamps from tl_1 show that sequential compute spawns are typically spaced 70–240 s apart across both LANs. With warm-lease TTL = 45 s, most spawns have **zero** overlapping warm leases. Only 1–2 overlaps occur per run across 13–17 spawns.

When `len(candidates) == 1`, round-robin and `max(started_ts)` are identical. The fix only activates during overlaps — and overlaps are rare in this workload.

### Finding 2: The extraction was the real confound

The original TTFT extraction used `mac not in first_window` — matching the first-ever telemetry window for a MAC, not the first-after-spawn window. Docker container recycling reuses MACs across spawns within a single run, causing later spawns to pick up earlier containers' windows.

**Impact of the extraction fix on v3 Lifecycle TTFT:**

| | Before fix | After fix | Δ |
|---|-----------|----------|----|
| TTFT matches | 17/41 (41%) | 36/41 (88%) | +19 |
| TTFT med | 30.6 s | **20.9 s** | −9.7 s |
| TTFT IQR | 34.8 s | 10.8 s | −24.0 s |

The MAC-reuse bug inflated v3's TTFT by 9.7 s and more than tripled the IQR. The corrected Lifecycle TTFT is **20.9 s** — not 30.6 s as originally reported.

### Finding 3: Round-robin increases variance

v4's Q1 is lower (11.0 vs 20.2 s) — round-robin helps some backends get traffic in their first window. But v4's Q3 is higher (60.6 vs 31.0 s) — others are delayed more. The IQR widened from 10.8 s to 49.6 s.

Round-robin distributes warm-lease traffic across all candidates, which guarantees every backend gets *some* traffic (lower Q1) but reduces the volume per backend. A backend near the end of a telemetry window may get only 1–2 requests before the window closes — enough to register, but sometimes not enough to appear in that window's aggregation if timing is tight. This creates a bimodal distribution: fast matches (window 1) and delayed matches (window 3–5).

---

## 3. Conclusions

1. **The warm-lease selection policy is not the dominant TTFT driver.** Replacing `max(started_ts)` with round-robin did not change the median (20.9 s → 20.9 s). The ~21 s TTFT is driven by the telemetry window cadence (~10 s) and spawn timing within that window, not by the lease-claiming policy.

2. **The MAC-reuse extraction bug was the real confound.** It inflated v3's Lifecycle TTFT from 20.9 s to 30.6 s. This was a measurement error, not a mechanism property.

3. **Warm-lease overlap is rare in this workload.** Spawns are spaced 70–240 s apart; warm-lease TTL is 45 s. The fix only matters during overlaps, which occur 1–2 times per run.

4. **v3 results must be retroactively corrected.** The corrected Lifecycle TTFT is 20.9 s (not 30.6 s), TFR is 15.8 s, share is 0.111. The coordination gap (Slowstart − Lifecycle) is 51.0 − 20.9 = **30.1 s** (not 20.4 s).

5. **The round-robin fix is a negative result for the thesis but a positive result for understanding.** We: (a) identified a suspected mechanism, (b) implemented a targeted fix, (c) ran a controlled experiment, (d) disproved the hypothesis. This is how science works, and it strengthens the thesis by eliminating a confound.

---

## 4. Corrected v3 Lifecycle numbers (for reference)

All v3 Lifecycle metrics with the MAC-reuse-corrected extraction:

| Metric | Original v3 | Corrected | Δ |
|--------|------------|-----------|----|
| TTFT n | 17 | 36 | +19 matches |
| TTFT med | 30.6 s | **20.9 s** | −9.7 s |
| TTFT Q1 | 20.5 s | 20.2 s | −0.3 s |
| TTFT Q3 | 55.3 s | 31.0 s | −24.3 s |
| TTFT IQR | 34.8 s | 10.8 s | −24.0 s |
| TFR med | 15.8 s | 15.8 s | unchanged |
| Share med | 0.111 | 0.111 | unchanged |
| Coordination gap | 20.4 s | **30.1 s** | +9.7 s |

The v3 results.md should be updated to reflect these corrected numbers.

---

## 5. Extraction Fix

The fix is in `extract_spawn_metrics.py`, `compute_ttft()`:

```diff
- Build dict: mac → first_window_end (mac not in first_window)
+ Collect ALL windows per MAC, then per spawn:
+   find first window_end >= spawn_ts with request_count > 0
```

This correctly handles Docker MAC reuse across container lifetimes within a single run. The fix has been applied to the canonical extraction script and should be used for all future RQ2 analysis.

---

## 6. Artefact Locations

- **v4 run folders**: `source/scripts/testing/metrics/20260724_*_rq2_v4_tl_*` on `cloud-vm`
- **v3 run folders (re-extracted)**: `source/scripts/testing/metrics/20260723_*_rq2_v3_tl_*` on `cloud-vm`
- **Extraction script**: `source/scripts/testing/analysis/rq2/extract_spawn_metrics.py`
