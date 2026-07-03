# Experiment Plan v2‑Lite — De‑IoT‑ified 7‑Phase Smoke Test

**Status**: 🔵 Designed · **Date**: 2026-07-03
**Parent**: [experiment_plan.md](experiment_plan.md) — golden validation (6‑phase canonical)
**Predecessor**: [../../rq1_evaluation/experiment_plan_v2_lite.md](../../rq1_evaluation/experiment_plan_v2_lite.md) — v2‑lite WAN=200ms + curl=30s validation
**Phase file**: `testing/phases_override/phases_rq1_7phase.json`

## Intent

Validate that the renamed content‑discovery workload surface works end‑to‑end
under the RQ1 v2 7‑phase mixed profile — the same profile that produced clear
Tier 1 benefit and ~7% baseline failure at WAN=200ms. This is the **smoke‑test
gate** before committing the full 12‑run RQ1 thesis‑final campaign.

The single question: **does the renamed workload run end‑to‑end with the RQ1
7‑phase profile, the thesis‑final runtime envelope, all four mechanisms
exercised, and overall failure below 20 percent?**

## Hypothesis / Expected Outcome

If the 7‑phase profile exercises the renamed workload surface correctly:

- all 7 phases complete (`reverse_hotspot` and `demand_drop` appear)
- overall failure rate is in the ~7% range (consistent with v2‑lite at
  WAN=200ms with curl=30s), well below the 20% gate
- `reverse_hotspot` produces cross‑region pressure on the opposite direction
  from `tier1_hotspot`
- `demand_drop` provides a 300 s scale‑down observation window
- Tier 1 activates in both hotspot directions
- storage and compute mechanisms exercise as in the 6‑phase validation

## Independent Variable & Held‑Constant Set

- **Independent variable**: none — single‑run smoke test
- **Held constant set**: identical to the golden validation run, except the
  phase file

| Parameter | Value |
| --- | --- |
| Phase file | `testing/phases_override/phases_rq1_7phase.json` |
| Controller override | `testing/controller_env_overrides/current_state_integrated.env` |
| `WAN_RTT_MS` | `200` |
| `VIP_HARD_TIMEOUT` | `60` |
| `CURL_MAX_TIME` | `30` |
| `CLIENTS` | `48` |
| `CONTENT_ITEMS` | `6000` |
| `USERS` | `100` |
| `STORAGE_CPUS` | `0.10` |
| Fault plan | omitted |

## 7‑Phase Profile

| # | Phase | Dur | Rate/client | Cross-reg | Clients | Mix (CL/FR/SP/CU/CA) |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| 1 | `baseline` | 60s | 1.0 | 0% | 50% | .60/.25/.15/0/0 |
| 2 | `storage_storm` | 240s | 4.0 | 90% | 100% | .35/.10/.05/.30/.20 |
| 3 | `tier1_hotspot` | 180s | 5.0 | 95% | 100% | .80/.05/.05/.05/.05 |
| 4 | `inter_hotspot_cooldown` | 300s | 1.0 | 0% | 10% | .60/.25/.15/0/0 |
| 5 | `reverse_hotspot` | 180s | 5.0 | 95% | 100% | .80/.05/.05/.05/.05 |
| 6 | `compute_spike` | 180s | 4.0 | 5% | 100% | .20/.65/.15/0/0 |
| 7 | `demand_drop` | 300s | 1.0 | 0% | 10% | .60/.25/.15/0/0 |

**Total**: 1440 s (24 min).
Mix keys: CL=`content_lookup`, FR=`feed_ranking`, SP=`service_pressure`,
CU=`content_update`, CA=`content_aggregate`.

Differences from the 6‑phase canonical:

- Added `reverse_hotspot` (180 s, 5 r/s, 95% cross) for bidirectional Tier 1
  hotspot exercise.
- Replaced 120 s `cooldown` with 300 s `demand_drop` for sustained scale‑down
  observation.
- Shared phases keep identical rates, durations, and mixes.

## Run Matrix

| Run | Label | Phase file |
| --- | --- | --- |
| A | `deiot_7phase_smoke` | `testing/phases_override/phases_rq1_7phase.json` |

Single run only. If the launch fails before the first stress phase, one
identical rerun is allowed.

## Run Configuration

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=deiot_7phase_smoke \
  PHASES_CONFIG=testing/phases_override/phases_rq1_7phase.json \
  WAN_RTT_MS=200 CLIENTS=48 CONTENT_ITEMS=6000 USERS=100 STORAGE_CPUS=0.10 \
  CURL_MAX_TIME=30 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

## Metrics & Success Criteria

| # | Criterion | Pass condition |
| --- | --- | --- |
| 1 | Run completion | Rows exist for all 7 phases: baseline, storage_storm, tier1_hotspot, inter_hotspot_cooldown, reverse_hotspot, compute_spike, demand_drop |
| 2 | Overall failure rate | < 20% (expected ~7% based on v2‑lite at WAN=200ms with curl=30s) |
| 3 | Renamed request surface | Labels subset of content_lookup, feed_ranking, service_pressure, content_update, content_aggregate |
| 4 | Tier 1 bidirectional | tier1_lifecycle_active_count ≥ 1 in both tier1_hotspot and reverse_hotspot windows |
| 5 | Storage reserve activation | ≥ 1 `[reserve] activated` in controller logs |
| 6 | Storage scale‑out | storage_count rises above baseline during storage_storm |
| 7 | Compute scale‑up | server_count rises above baseline during compute_spike |
| 8 | Runtime envelope | VIP_HARD_TIMEOUT=60 in controller_env_snapshot.env |
| 9 | Control‑plane health | 0 unhandled tracebacks |

## Checkpoints

| Trigger | Question | Runner action |
| --- | --- | --- |
| Mid `tier1_hotspot` | Tier 1 active in first direction? | Report only |
| Mid `reverse_hotspot` | Tier 1 active in reverse direction? | Report only |
| End of `demand_drop` | Run complete with acceptable failures? | Report only |

## Validity Threats

1. **Single‑run gate** — validates the 7‑phase profile works with the renamed
   surface, not reproducibility.
2. **Failure rate may differ from v2‑lite** — the v2‑lite profile used the
   old IoT request names; structural equivalence is expected but not proven
   until this run completes.

## Artifact Contract

Standard run‑folder layout per `testing_overview.md`. Primary evidence:
`client_requests.csv`, `resource_stats.csv`, `controller_lan1.log`,
`controller_lan2.log`, `phases_snapshot.json`, `controller_env_snapshot.env`.

If this smoke test passes, proceed to the full 12‑run
[`rq1_thesis_final`](../../rq1_thesis_final/experiment_plan.md) campaign.
