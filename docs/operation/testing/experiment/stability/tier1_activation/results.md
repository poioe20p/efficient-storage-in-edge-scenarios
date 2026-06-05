# Results - Tier 1 Activation Stability

**Date:** 2026-06-04  
**Status:**  PASSED — Tier 1 path validated  

## Authoritative Runs

| Run | Label | SS_ENABLED | Tier 2 | Phases | Requests | Success | SS Events |
| --- | --- | --- | --- | --- | ---: | ---: | ---: |
| `20260604_204334` | `tier1_hotspot_control` | 0 | Off | 5/5 | 14,268 | 99.99% | **0** |
| `20260604_205108` | `tier1_hotspot_enabled` | 1 | Off | 5/5 | 27,857 | 99.14% | **160** (69+91) |

Both runs were executed with the controller env verified via `docker exec osken env` before launch:

| Variable | Control | Enabled |
| --- | --- | --- |
| `SS_ENABLED` | 0 | 1 |
| `STORAGE_PERSISTENT_RESERVE_ENABLED` | 0 | 0 |
| `MAX_DYNAMIC_STORAGE` | 0 | 0 |
| `MAX_DYNAMIC_COMPUTE` | 0 | 0 |

Earlier runs (`20260604_190206`, `190750`, `192313`) are excluded because the cloud VM was missing required phase and override files. The prior enabled run (`20260604_194228`) is superseded by `20260604_205108` which has confirmed container env verification.

## Expectation Check

| Plan expectation | Status | Evidence |
| --- | --- | --- |
| Workload creates a bounded cross-region hot set in both directions | **Met** | Reconfigure alerts enumerate 30 hot devices per direction; `sel_sync_lan1_dyn1` and `sel_sync_lan2_dyn1` both reached `ACTIVE` |
| Enabled run promotes Tier 1 and reaches `ACTIVE` in both directions | **Met** | `container_events.csv` shows both containers added, running, and removed; 160 `SelectiveSync` markers across both controller logs |
| Control run does not activate Tier 1 | **Met** | Zero `SelectiveSync` / `sel_sync` events in either controller log |
| Service quality improves after activation | **Met** | Control `tier1_hotspot_n1` LAN2 median `time_db` = 84.5 ms vs enabled 3.58 ms. Tier 1 effectively eliminated the cross-region DB penalty in the first direction. |
| Activation stays stable (failures < 1.0%) | **Met** | Enabled: `tier1_hotspot_n1` 0.05% failures, `tier1_hotspot_n2` 0.02% failures. Control: 0.14% and 0.06%. |
| Teardown completes with no residual `sel_sync_*` containers | **Met** | `container_events.csv` shows both containers removed; no residual containers after `cooldown_n2` |

## Overall Verdict

**Tier 1 selective sync is validated as a functioning mechanism.** With Tier 2 fully isolated, the enabled run activated selective-sync in both hotspot directions, kept request failures well below 1%, and removed all selective containers by run end. The control run confirmed zero false activation. The first-direction DB-latency comparison shows Tier 1 eliminating the cross-region penalty that dominates the control run.

## Key Numbers

### Control (`20260604_204334_tier1_hotspot_control`)

- 14,268 requests, 99.99% success (2 `http_status=0`)
- 0 Tier 1 events
- `tier1_hotspot_n1` LAN2: median `time_db` = 84.5 ms, median `time_total` = 86.6 ms

### Enabled (`20260604_205108_tier1_hotspot_enabled`)

- 27,857 requests, 99.14% success (239 `http_status=0`, no non-200 HTTP errors)
- 160 Tier 1 events (69 LAN1 + 91 LAN2)
- `sel_sync_lan2_dyn1` added at `tier1_hotspot_n1`, removed at `tier1_hotspot_n1`
- `sel_sync_lan1_dyn1` added at `tier1_hotspot_n1`, removed at `tier1_hotspot_n1`
- `tier1_hotspot_n1` LAN2: median `time_db` = 3.58 ms, median `time_total` = 5.25 ms

### Latency Comparison (First Hotspot Direction)

| Metric | Control | Enabled |
| --- | ---: | ---: |
| LAN2 median `time_db` | 84.5 ms | 3.58 ms |
| LAN2 median `time_total` | 86.6 ms | 5.25 ms |

## Known Limitations

- The `OSKEN_ENV_OVERRIDE_FILE` mechanism does not propagate into Docker containers on this cloud VM. The base `osken-controller.env` was edited directly as a reliable workaround (restored after runs).
- Test client network namespaces are torn down mid-run during cooldown phases, causing `http_status=0` failures that are unrelated to Tier 1 behavior.
- The control run's `resource_stats.csv` only covers `warmup`, `transition`, and `tier1_hotspot_n1`, so the second-direction latency comparison is one-sided.

## Artifact Map

| Run folder | Role |
| --- | --- |
| `source/scripts/testing/metrics/20260604_204334_tier1_hotspot_control/` | Authoritative control (SS_ENABLED=0, Tier 2 off) |
| `source/scripts/testing/metrics/20260604_205108_tier1_hotspot_enabled/` | Authoritative enabled (SS_ENABLED=1, Tier 2 off) |
