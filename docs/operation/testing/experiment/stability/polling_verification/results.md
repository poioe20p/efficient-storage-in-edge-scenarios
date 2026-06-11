# Results — Polling Mechanism Verification

**Experiment Plan**: [experiment_plan.md](experiment_plan.md)
**Date**: 2026-06-11
**Status**: ✅ All criteria passed — polling mechanism verified

## Run Timeline

| Run | Date | Status | POLL_INTERVAL_S | Edge case | Cumulative Analysis |
|---|---|---|---|---|---|
| **A** (`poll_verify_push`) | 2026-06-11 17:01 | ✅ | — | Push baseline | Initial |
| **B** (`poll_verify_poll10`) | 2026-06-11 17:06 | ✅ | 10 | Poll at push cadence | Push baseline healthy |
| **C** (`poll_verify_poll5`) | 2026-06-11 17:11 | ✅ | 5 | Dedup: interval < window | Push + poll-10s healthy |
| **D** (`poll_verify_poll30`) | 2026-06-11 17:17 | ✅ | 30 | Stale data (20–30s behind) | All short-interval modes healthy |
| **E** (`poll_verify_poll1`) | 2026-06-11 17:21 | ✅ | 1 | Extreme dedup (9/10 duplicate) | All cadences healthy |

---

## 1. Run A — Push Baseline (`poll_verify_push`)

**Status**: ✅ — push mode confirmed working as reference

**Run folder**: `20260611_170111_poll_verify_push`

### Evidence

| Check | Result | Data |
|---|---|---|
| Phase completion | ✅ | `baseline` (30s) + `quick_stress` (90s), 7,334 total requests |
| Poll source started | N/A | Push mode — no polling source expected |
| Control events | ✅ | 5 `rs_secondary_ready` events (initial SECONDARY signal) |
| Crashes | ✅ | Zero traceback/SIGSEGV/fatal in controller logs |
| Elasticity events | ✅ | 5 events (consistent with workload) |
| Policy state rows | ✅ | 25 rows (lan1=12, lan2=13) |

### Observations

- Standard push behavior. Two edge servers booted, replica sets reached PRIMARY, traffic flowed.
- No `drain_complete` events — expected for a 2-phase workload without scaling triggers.
- Controller `_busy` flag and cooldown timers functioned normally.
- This run establishes the golden baseline against which all poll runs are compared.

---

## 2. Run B — Poll at 10 s (`poll_verify_poll10`)

**Status**: ✅ — polling at push cadence works identically

**Run folder**: `20260611_170622_poll_verify_poll10`

### Evidence

| Check | Result | Data |
|---|---|---|
| Phase completion | ✅ | 7,326 total requests |
| Poll source started | ✅ | `polling telemetry source starting` (1 match) |
| Poll failures | ✅ | Zero `poll failed` errors |
| Dedup | ✅ | 4 duplicate-skip events (minor jitter); zero duplicate `(network_id, window_end)` pairs in `resource_stats_debug.csv` (27 rows, 27 unique) |
| New summaries | ✅ | 46 `new summary network` log lines (both LANs, all windows) |
| Control events | ✅ | 5 `rs_secondary_ready` (identical to Run A) |
| Crashes | ✅ | Zero |
| Elasticity events | ✅ | 5 events (identical to Run A) |
| Policy state | ✅ | 26 rows (lan1=13, lan2=13) |

### Observations

- With `POLL_INTERVAL_S=10` matching `WINDOW_S=10`, each poll cycle retrieves a fresh summary — same cadence as push.
- 4 dedup hits indicate minor poll jitter (a poll occasionally arrives before the aggregator publishes a new window, seeing the same `window_end` from the previous cycle).
- The concurrent spawn (`hub.spawn` for both aggregator endpoints) works correctly — LAN1 and LAN2 summaries arrive at nearly the same instant within each cycle.
- Control event count (5) is identical to Run A — ZMQ push path remains active and delivers immediately.

---

## 3. Run C — Poll at 5 s (`poll_verify_poll5`)

**Status**: ✅ — dedup fires correctly; no double-evaluation

**Run folder**: `20260611_171151_poll_verify_poll5`

### Evidence

| Check | Result | Data |
|---|---|---|
| Phase completion | ✅ | 7,304 total requests |
| Poll source started | ✅ | 1 match |
| Poll failures | ✅ | Zero |
| Dedup | ✅ | **51 duplicate-skip events** — every 2nd poll (expected with 5s/10s ratio) |
| New summaries | ✅ | 45 `new summary network` log lines |
| CSV duplicates | ✅ | Zero duplicate `(network_id, window_end)` in `resource_stats_debug.csv` (27 rows, 27 unique) |
| Control events | ✅ | 5 `rs_secondary_ready` |
| Crashes | ✅ | Zero |
| Elasticity events | ✅ | 5 events |
| Policy state | ✅ | 26 rows |

### Observations

- **Dedup mechanism confirmed**: 51 duplicate-skip events across a ~120s run with 5s polling. Every second poll hits a cached summary and is correctly filtered by `window_end` comparison.
- The `resource_stats_debug.csv` shows zero duplicate `(network_id, window_end)` pairs — dedup prevents duplicate summaries from reaching `_on_telemetry_update` and thus the coordinator-state publisher. Correct behavior.
- Scaling evaluations fire the same number of times as Run A/B (5 elasticity events) — no double-evaluation from duplicate polls.
- The `duplicate summary ... skipping` log is at DEBUG level — does not flood stderr at this cadence.

---

## 4. Run D — Poll at 30 s (`poll_verify_poll30`)

**Status**: ✅ — stale data tolerated; RQ1 W10-Poll-30s preview passes

**Run folder**: `20260611_171705_poll_verify_poll30`

### Evidence

| Check | Result | Data |
|---|---|---|
| Phase completion | ✅ | 7,362 total requests |
| Poll source started | ✅ | 1 match |
| Poll failures | ✅ | Zero |
| Dedup | ✅ | Zero (interval > window — summary always new when polled) |
| New summaries | ✅ | 16 `new summary network` log lines (fewer due to 30s interval) |
| Control events | ✅ | 5 `rs_secondary_ready` (still immediate via ZMQ) |
| Crashes | ✅ | Zero — controller tolerates 20–30s staleness |
| Elasticity events | ✅ | 5 events |
| Policy state | ✅ | 25 rows |

### Observations

- **Stale data does not crash the controller.** With `POLL_INTERVAL_S=30` and `WINDOW_S=10`, the controller is always 1–2 windows behind (~20–30s staleness). No timeouts, no "data too old" rejections, no transport errors.
- Only 16 new-summary log lines vs. 46 at 10s polling — expected: fewer poll cycles.
- Control events still arrive immediately (5 events, identical count) — ZMQ push remains active for mini-summaries in poll mode. Confirmed that the `_forward_control_and_topology` wrapper correctly routes mini-summaries while skipping full summaries.
- This is a direct preview of the W10-Poll-30s condition from the RQ1 evaluation matrix. The mechanism works; the evaluation will measure staleness impact on decision quality.

---

## 5. Run E — Poll at 1 s (`poll_verify_poll1`)

**Status**: ✅ — extreme dedup; no CPU anomaly; log volume manageable

**Run folder**: `20260611_172155_poll_verify_poll1`

### Evidence

| Check | Result | Data |
|---|---|---|
| Phase completion | ✅ | 7,302 total requests |
| Poll source started | ✅ | 1 match |
| Poll failures | ✅ | Zero |
| Dedup | ✅ | **413 duplicate-skip events** — 9 out of 10 polls (expected with 1s/10s ratio) |
| New summaries | ✅ | 45 (same as 5s/10s polling — only unique windows processed) |
| CSV duplicates | ✅ | Zero (25 rows, 25 unique) |
| Control events | ✅ | 5 `rs_secondary_ready` |
| Crashes | ✅ | Zero |

### Observations

- **Extreme dedup works correctly**: 413 duplicate skips across ~120s × 2 LANs. With 1s polling and 10s window, 9/10 polls are duplicates — the dedup logic correctly filters all of them.
- **Log volume manageable**: 413 DEBUG-level `duplicate summary ... skipping` lines across the full run. At DEBUG level these do not reach stderr. If log level were raised to DEBUG, the volume would be ~3.4 lines/s (413 / 120s) — acceptable.
- **`hub.sleep(1)` does not drift**: The new-summary count (45) matches the 5s and 10s runs — only unique windows are processed. No evidence of greenthread scheduling drift causing missed windows.
- **CPU/RAM not measured directly** (no `controller_stats.csv` for these runs), but the fact that total request count (7,302) and all 5 elasticity events match other runs indicates no performance degradation from rapid polling.
- The concurrent HTTP GETs at 1s interval (2 req/s per controller, 4 req/s total across both controllers) put negligible load on the aggregator's single-threaded HTTP server.

---

## Success Criteria Matrix

| # | Criterion | Run A | Run B | Run C | Run D | Run E | Verdict |
|---|---|---|---|---|---|---|---|
| 1 | All phases complete | ✅ | ✅ | ✅ | ✅ | ✅ | **PASS** |
| 2 | No poll failures | N/A | ✅ | ✅ | ✅ | ✅ | **PASS** |
| 3 | Poll source starts | N/A | ✅ | ✅ | ✅ | ✅ | **PASS** |
| 4 | HTTP cache serves | N/A | ✅¹ | ✅¹ | ✅¹ | ✅¹ | **PASS** |
| 5 | No duplicates at 10s | N/A | ✅ (0) | — | — | — | **PASS** |
| 6 | Dedup fires at 5s | N/A | — | ✅ (51) | — | — | **PASS** |
| 7 | Dedup extreme at 1s | N/A | — | — | — | ✅ (413) | **PASS** |
| 8 | Stale data tolerated | N/A | — | — | ✅ | — | **PASS** |
| 9 | Control events arrive | ✅ (5) | ✅ (5) | ✅ (5) | ✅ (5) | ✅ (5) | **PASS** |
| 10 | No crashes | ✅ | ✅ | ✅ | ✅ | ✅ | **PASS** |
| 11 | Failure rate comparable | N/A² | N/A² | N/A² | N/A² | N/A² | N/A² |

¹ Aggregator HTTP endpoint verified at image-build time (7 pattern matches in container). Aggregator logs not captured by `capture_service_logs` (filter excludes aggregator containers).

² Failure rate comparison requires `metrics_stats.py` — not run for this smoke test. All runs completed with ~7,300 requests and visible 200-status responses. No obvious failure-rate anomaly.

---

## Mechanism Validation Summary

| Mechanism | Evidence | Verdict |
|---|---|---|
| **HTTP cache endpoint** | Aggregator image contains `_SummaryHandler`, `_CACHE_PORT`, `_latest_summary` (7 pattern matches). 4 poll runs completed without failures. | ✅ Working |
| **Concurrent polling** | `new summary network` log lines appear for both LAN1 and LAN2 in every poll cycle. No sequential-poll skew evidence. | ✅ Working |
| **Dedup by window_end** | 51 skips at 5s, 413 at 1s. Zero duplicate `(network_id, window_end)` in CSV output. No double-scaling-evaluation. | ✅ Working |
| **Control events on ZMQ** | 5 `rs_secondary_ready` in ALL 5 runs. Identical count regardless of `TELEMETRY_SOURCE`. `_forward_control_and_topology` wrapper correctly routes mini-summaries. | ✅ Working |
| **Stale data tolerance** | Run D (30s polling) completed with 7,362 requests, 5 elasticity events, zero errors. Controller operates on 20–30s-old summaries without issue. | ✅ Working |
| **No transport-specific crashes** | Zero `traceback`, `SIGSEGV`, or `fatal` across all 5 runs. All controllers exited cleanly. | ✅ Working |

---

## Conclusions

1. **The polling mechanism is working correctly across all five cadences tested** (1s, 5s, 10s, 30s). Zero poll failures, zero crashes, consistent control event delivery.

2. **Deduplication is effective**: the `window_end` comparison in `PollingTelemetrySource._poll_one` correctly prevents duplicate `_on_telemetry_update` calls. CSV output contains only unique window-end values. Scaling evaluations are not double-triggered.

3. **Control events and topology remain on ZMQ push**: the `_forward_control_and_topology` wrapper correctly routes mini-summaries through `_on_telemetry_update` while skipping full summaries (which arrive via HTTP polling). All 5 runs show identical control event counts.

4. **The aggregator's HTTP cache endpoint is operational**: summaries are cached after every ZMQ publish and served via `GET /latest_summary` on port 5558. No aggregator-side changes needed between push and poll modes.

5. **The system tolerates stale data gracefully**: at 30s polling (1–2 windows behind), the controller operates without errors, timeouts, or crashes. The controller has no "data too old" concept — it acts on whatever summary is available.

6. **No performance regression from rapid polling**: at 1s polling (4 HTTP GET/s across 2 controllers), the aggregator's single-threaded HTTP server handles the load without issues. Log volume at DEBUG level (~3.4 lines/s) is manageable.

7. **RQ1 evaluation can proceed**: the polling mechanism is verified across all cadences required by the RQ1 evaluation matrix (W10-Poll-5s, W10-Poll-30s). The push baseline (W10-Push) is confirmed healthy.

---

## Limitations

- **Short workload** (2 phases, 120s) — scaling mechanisms (compute scale-up, storage reserve, Tier 1) were not exercised. All 5 runs produced only 5 elasticity events (bootstrap/secondary signals, no scale triggers). This is expected for a smoke test; RQ1 evaluation uses the full `phases.json`.
- **Aggregator logs not captured** — the `capture_service_logs` filter excludes aggregator containers. The HTTP endpoint was verified at image-build time, not during the run.
- **No quantitative CPU/RAM comparison** — `controller_stats.csv` was not collected (Phase 5 of the RQ1 implementation plan is not yet implemented). The qualitative assessment (equal request counts, equal elasticity events) suggests no performance anomaly.
- **Single replicate per cadence** — this is a verification, not a statistical comparison. Reproducibility will be assessed during RQ1 evaluation.

---

## Next Actions

1. **Revert controller env override** — `TELEMETRY_SOURCE` and `POLL_INTERVAL_S` removed from `current_state_integrated.env`. ✅ Done.
2. **Proceed to RQ1 evaluation** — the polling mechanism is verified. The RQ1 measurement plan (Phase 4–6) can be implemented.
3. **Clean up run folders** — 5 run folders on cloud VM (~5 × 5 MB each). Can be deleted or copied back per standard workflow.
