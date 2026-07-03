# Results — Workload De-IoT-ification Golden Validation

**Date**: 2026-07-02
**Run folder**: `20260702_221431_workload_deiotification_golden_validation`
**Experiment plan**: [experiment_plan.md](experiment_plan.md)

## Verdict: ✅ PASS

All 10 success criteria met. The renamed workload surface is correct and the
system operates healthily at golden scale.

---

## Run Timeline

| Run | Date | Status | Cumulative Analysis |
|-----|------|--------|---------------------|
| v1 (`workload_deiotification_golden_validation`) | `20260702_221431` | ✅ | — (initial run, 6‑phase canonical) |
| v2 (`deiot_7phase_smoke`) | `20260702_232939` | ✅ | 6‑phase canonical passes all gates; 7‑phase profile adds `reverse_hotspot` + `demand_drop` for RQ1‑compatible stress |

---

## Configuration

| Parameter | Value |
|---|---|
| Phase file | `testing/phases.json` (6-phase canonical content-discovery) |
| Controller override | `current_state_integrated.env` |
| `WAN_RTT_MS` | 200 |
| `VIP_HARD_TIMEOUT` | 60 |
| `CURL_MAX_TIME` | 30 |
| `CLIENTS` | 48 |
| `CONTENT_ITEMS` | 6000 |
| `USERS` | 100 |
| `STORAGE_CPUS` | 0.10 |

---

## Results by Success Criterion

| # | Criterion | Result |
|---|---|---|
| 1 | Run completion | ✅ All 6 phases: baseline, storage_storm, tier1_hotspot, inter_hotspot_cooldown, compute_spike, cooldown |
| 2 | Overall failure rate | ✅ 355 / 23,097 = **1.5%** (< 20%) |
| 3 | Renamed request surface | ✅ content_lookup, feed_ranking, service_pressure, content_update, content_aggregate |
| 4 | Renamed snapshot surface | ✅ content_items.json + user_profiles.json only; no legacy filenames |
| 5 | Storage reserve activation | ✅ 10 activations (5 per LAN) |
| 6 | Storage scale-out | ✅ storage_count: 6→7 |
| 7 | Compute scale-up | ✅ server_count: 1→5 |
| 8 | Tier 1 selective sync | ✅ tier1_lifecycle_active_count=1, 101 windows active |
| 9 | Runtime envelope | ✅ VIP_HARD_TIMEOUT=60 confirmed in env snapshot |
| 10 | Control-plane health | ✅ 0 unhandled tracebacks |

---

## Per-Phase Breakdown

| Phase | Requests | Failures | Fail % | Avg Latency |
|---|---:|---:|---:|---:|
| baseline | 1,940 | 14 | 0.7% | 0.978s |
| storage_storm | 8,274 | 144 | 1.7% | 2.750s |
| tier1_hotspot | 4,459 | 97 | 2.2% | 3.916s |
| inter_hotspot_cooldown | 2,592 | 1 | 0.0% | 0.237s |
| compute_spike | 4,820 | 97 | 2.0% | 3.589s |
| cooldown | 1,012 | 2 | 0.2% | 0.257s |
| **Total** | **23,097** | **355** | **1.5%** | — |

---

## Mechanism Exercise

| Mechanism | Evidence |
|---|---|
| Storage reserve | 10 `[reserve] activated` events (5 lan1, 5 lan2) |
| Storage scale-out | storage_count rose from 6 to 7 during storage_storm |
| Compute scale-up | server_count rose from 1 to 5 during compute_spike |
| Tier 1 selective sync | tier1_lifecycle_active_count=1 in 101 telemetry windows |

---

## Failure Rate Context

The 1.5% overall failure rate is substantially lower than the ~7–12% expected
by the thesis RQ1 final plan. This is **not a configuration error** — the
identical thesis-final runtime envelope (WAN=200, VIP_HARD_TIMEOUT=60,
CURL_MAX_TIME=30, CLIENTS=48, CONTENT_ITEMS=6000, current_state_integrated.env)
was used. The difference is in the workload shape:

- The 6-phase canonical content-discovery profile has lower peak cross-region
  intensity than the old 7-phase thesis profile.
- Hotspot phases are bidirectional (both LANs emit cross-region), which spreads
  the cross-region load rather than concentrating it on one source LAN.
- The `inter_hotspot_cooldown` phase is 300s at client_fraction=0.10, which
  adds many clean requests that pull the overall average down.
- Peak failure per phase is only 2.2% (tier1_hotspot), consistent with a
  well-provisioned system at WAN=200 with Tier 1 active.

If a future validation needs failure rates closer to the thesis baseline, use
the old 7-phase profile (or a new stress-oriented override) with directional
hotspot phases and higher peak rates.

---

## Analysis Graphs

Graphs archived at `graphs/20260702_221431/`:

- `endpoint_breakdown.png` — latency and failures by endpoint per phase
- `simple_run.png` — timeline of node counts, CPU, and request rates
- `overview_latency.png` — latency distributions over the run
- `overview_resources.png` — resource utilisation over the run
- `overview_throughput.png` — request throughput over the run
- `phase_summary.png` — per-phase aggregated metrics

---

## Caveats

1. **Controller env snapshot not copied locally** — `controller_env_snapshot.env`
   remains root-owned on the cloud VM. Verified via `sudo grep` that
   `VIP_HARD_TIMEOUT=60` is present.

2. **Single-run gate** — this run validates correctness under one workload
   shape. Reproducibility and variance are not characterised.

3. **Canonical profile only** — only the 6-phase `phases.json` was exercised.
   The `phases_override/` profiles were not part of this validation.

---

### 2. Run v2 — `deiot_7phase_smoke` (`20260702_232939`)

**Status**: ✅ PASS — 7‑phase profile smoke test gate

**Experiment plan**: [experiment_plan_v2_lite.md](experiment_plan_v2_lite.md)

#### Results by Success Criterion

| # | Criterion | Result |
|---|---|---|
| 1 | Run completion | ✅ All 7 phases: baseline, storage_storm, tier1_hotspot, inter_hotspot_cooldown, reverse_hotspot, compute_spike, demand_drop |
| 2 | Overall failure rate | ✅ 3,908 / 31,260 = **12.5%** (< 20%) |
| 3 | Renamed request surface | ✅ content_lookup, feed_ranking, service_pressure, content_update, content_aggregate |
| 4 | Tier 1 bidirectional | ✅ tier1_lifecycle_active_count ≥ 1 in both hotspot phases |
| 5 | Storage reserve activation | ✅ reserve activations in controller logs |
| 6 | Storage scale‑out | ✅ storage_count rose above baseline |
| 7 | Compute scale‑up | ✅ server_count rose above baseline |
| 8 | Runtime envelope | ✅ VIP_HARD_TIMEOUT=60 in env snapshot |
| 9 | Control‑plane health | ✅ 0 tracebacks |

#### Per-Phase Breakdown

| Phase | Requests | Failures | Fail % |
|---|---:|---:|---:|
| baseline | 2,048 | 11 | 0.5% |
| storage_storm | 11,014 | 3,577 | 32.5% |
| tier1_hotspot | 4,711 | 96 | 2.0% |
| inter_hotspot_cooldown | 2,498 | 25 | 1.0% |
| reverse_hotspot | 3,896 | 97 | 2.5% |
| compute_spike | 4,518 | 98 | 2.2% |
| demand_drop | 2,575 | 4 | 0.2% |
| **Total** | **31,260** | **3,908** | **12.5%** |

#### Analysis

The 7‑phase profile produces substantially higher stress than the 6‑phase
canonical (12.5% vs 1.5% overall). The `storage_storm` phase is the primary
stress driver at 32.5% failures — the combination of 90% cross‑region reads
plus `content_update` and `content_aggregate` write pressure at 4 r/s/client
with 48 clients creates real storage‑side contention.

The `reverse_hotspot` phase exercised Tier 1 in the opposite direction at 2.5%
failures, comparable to `tier1_hotspot` at 2.0% — confirming the bidirectional
hotspot stress is balanced.

The 300 s `demand_drop` at client_fraction=0.10 provided a clean scale‑down
window with only 0.2% failures.

This result clears the 7‑phase profile for use in the RQ1 thesis‑final
12‑run campaign.

#### Graphs

Archived at `graphs/20260702_232939/`:

- `endpoint_breakdown.png`, `simple_run.png`, `overview_latency.png`,
  `overview_resources.png`, `overview_throughput.png`, `phase_summary.png`
