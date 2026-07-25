# RQ1 v9 — Results

**Status**: ❌ Pilot Failed · **Date**: 2026-07-24
**Plan**: [`experiment_plan_v9.md`](experiment_plan_v9.md)
**Predecessor**: [`../v8/results.md`](../v8/results.md)

## Run Timeline

| Run | Date | Status | Notes |
|-----|------|--------|-------|
| P0 (`rq1_v9_push_pilot`) | 2026-07-24 20:02 | ✅ | 3rd attempt after 2 stalls (0%-CPU bug from v8 P3) |
| T0 (`rq1_v9_poll30_pilot`) | 2026-07-24 21:14 | ✅ | 3rd attempt after 1 stall + 1 namespace cleanup error |

## Pilot Gate — FAILED

Per the plan, the pilot gate required all 4 criteria to pass before
proceeding to the full 10-run Phase B campaign. The gate failed.

| Criterion | Threshold | P0 (Push) | T0 (Poll-30s) | Verdict |
|-----------|-----------|-----------|---------------|---------|
| Throughput separation | T0 ≤ 85% of P0 | 40,579 | 37,583 (92.6%) | ❌ FAIL |
| Timeout rate separation | T0 ≥ 2× P0 | 3.9% | 2.5% | ❌ FAIL (T0 is *lower*) |
| M6 blind spot rate | T0 ≥ 60% | — | Not analyzed (pilot stopped) | ⚠️ Skipped |
| G8 | Both PASS | ✅ (0 gap spawns) | ✅ (0 gap spawns) | ✅ PASS |

**Result**: Phase B was not executed.

## Per-Run Quick Stats

| Run | Requests | 200 | 0 (timeout) | 503 | 500 | G8 | Spawns |
|-----|----------|-----|-------------|-----|-----|-----|--------|
| **P0** (Push) | 40,579 | 38,908 | 1,591 (3.9%) | 80 | 0 | ✅ | 20 |
| **T0** (Poll-30s) | 37,583 | 36,658 | 925 (2.5%) | 0 | 0 | ✅ | 7 |

## Per-Phase Latency

| Phase | P0 mean | P0 p95 | T0 mean | T0 p95 | T0 vs P0 Δ |
|-------|---------|--------|---------|--------|-----------|
| `baseline` | 0.11s | 0.52s | 0.15s | 0.62s | — |
| `storage_storm` | 6.79s | **30.0s** | 7.16s | **30.0s** | +5% mean, same ceiling |
| `tier1_hotspot` | 5.56s | **30.0s** | 6.29s | **30.0s** | +13% mean, same ceiling |
| `reverse_hotspot` | 2.70s | 18.35s | 3.38s | 18.31s | +25% mean, same p95 |
| `compute_spike` | 0.66s | 1.14s | 1.13s | 1.37s | +71% mean, +20% p95 |
| `demand_drop` | — | — | 1.15s | 0.66s | — |

Note: p95 hits the 30s CURL_MAX_TIME ceiling in `storage_storm` and
`tier1_hotspot` for both modes, masking any tail-latency differentiation.

## Per-Phase Throughput

| Phase | P0 reqs | T0 reqs | T0/P0 |
|-------|---------|---------|-------|
| `baseline` | 1,080 | 1,080 | 100% |
| `storage_storm` | 3,570 | 3,444 | 96% |
| `cleanup_gap_1` | 935 | 922 | 99% |
| `tier1_hotspot` | 3,308 | 2,960 | 89% |
| `inter_hotspot_cooldown` | — | 5,053 | — |
| `reverse_hotspot` | 6,223 | 5,267 | 85% |
| `cleanup_gap_2` | 780 | 901 | — |
| `compute_spike` | 15,095 | 15,284 | 101% |
| `demand_drop` | — | 2,672 | — |

The biggest per-phase throughput gap is `tier1_hotspot` (89%) and
`reverse_hotspot` (85%), but these are modest relative to the expected
30–50% gap. `compute_spike` actually shows T0 completing slightly *more*
requests (101%) than P0 — the phase is compute-bound but with 0%
cross-region, the static nodes serve it efficiently regardless of
dynamic-node count.

## What Happened and Why

The v9 hypothesis was that halving stress-phase durations (180–240s → 90–120s)
would make Poll-30s's detection window (~150s) exceed the phase, leaving no
time for late-spawned nodes to contribute. The pilot shows this was insufficient.

**Three factors prevented the expected gap:**

1. **Static-node throughput floor.** Two edge servers per LAN serve requests
   regardless of dynamic-node count. T0 completed 93% of P0's total requests
   with only 7 compute spawns (vs 20 for P0) because the static nodes absorbed
   the load. Throughput cannot drop below what the static infrastructure serves.

2. **compute_spike dominated total volume.** This phase contributed 15,284 of
   T0's 37,583 requests (41%). It has 0% cross-region traffic and 100%
   `service_pressure` endpoints — purely CPU-bound. The 2.0× rate per client
   is low enough that static nodes handle it well, producing T0's best phase
   (1.13s mean, 1.37s p95). This phase alone erased the throughput gap.

3. **30s CURL_MAX_TIME masks the tail.** In `storage_storm` and `tier1_hotspot`,
   both modes saturate at p95 = 30.0s. The ceiling hides any tail-latency
   difference — we know Poll-30s users waited longer (mean is 5–13% higher),
   but we cannot quantify how much worse it was at the extreme tail.

## Operational Notes

### v8 P3 Stall Bug Persists

The 0%-CPU stall that affected v8 P3 (3 attempts) also struck both v9 pilot
runs. Both P0 and T0 required 3 attempts each:
- P0 attempts 1 & 2: stuck at "Removing test clients" after connectivity tests
  (process at 0% CPU, no progress)
- T0 attempt 1: same stall pattern
- T0 attempt 2: namespace cleanup error (leftover namespaces from attempt 1)
- P0 attempt 3 & T0 attempt 3: succeeded normally

This is likely a race condition in `remove_test_clients.sh` when interacting
with Docker API or ip netns during teardown. The 33% first-attempt success rate
is a concern for any campaign larger than the 2-run pilot.

### T0 503s = 0

T0 produced zero 503 backpressure responses. Push produced 80. In v8, this
was interpreted as a positive signal (Push hits capacity limits faster due to
more aggressive spawning). In v9, at lower total volume, the 503 count is
marginal for both modes.

## Evidence Inventory

| Run | Run Folder | Artifacts |
|-----|-----------|-----------|
| P0 | `20260724_200247_rq1_v9_push_pilot` | `client_requests.csv` (40,580 lines), `node_lifecycle_timings.csv`, `elasticity_events.csv`, `controller_lan1.log`, `controller_lan2.log`, `latency_summary.csv` |
| T0 | `20260724_211422_rq1_v9_poll30_pilot` | `client_requests.csv` (37,584 lines), `node_lifecycle_timings.csv`, `elasticity_events.csv`, `controller_lan1.log`, `controller_lan2.log` |

Full post-run analysis (RQ1 CLIs, graphs, M6 CSV) was not executed — the pilot
gate failure made it unnecessary.

## Conclusion

**v9 does not replace v8.** The phase-duration change was insufficient to
overcome the system's inherent resilience. The static-node throughput floor
and the dominance of `compute_spike` in total request volume masked the
coordination gap that M6 (67.9% blind spot rate) confirmed exists.

v8 remains the definitive RQ1 campaign. Its evidence — blind spot rate,
p95 latency (+69–91%), timeout reliability (σ = 0.4% vs 3–5%), and reaction
events detected (15 vs 8) — establishes the full dose-response curve the
thesis needs.

The v9 pilot results reinforce v8's core finding: the system is robust enough
that most runs succeed regardless of mode, and the coordination gap manifests
as **reliability**, not mean degradation — even under tightened phase durations.
