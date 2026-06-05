# Run Summary - 20260604_182338_storage_reserve_smoke

## Conclusion

Reserve liveness passed. Both LANs prepared one standby storage replica, both replicas reached ready state in about 12.4 seconds, both kept heartbeating through `demand_drop`, and no cleanup regression appeared. The run did not emit a storage activation trigger, so this run should be classified exactly as the plan states: liveness passed, activation untested.

## Main Points

- LAN1 reserve `edge_storage_lan1_dyn1` reached ready in 12.47 s; LAN2 reserve `edge_storage_lan2_dyn1` reached ready in 12.36 s.
- Demand stayed stable while the reserve remained live: only 4 non-200 responses occurred in `reserve_trigger_lan1` and none occurred in `baseline` or `demand_drop`.
- `storage_count` reached 2 during the run and the reserve MACs remained visible in `per_node_stats.csv` during late `demand_drop` windows.
- No cleanup markers, reserve removals, or absent-node cleanup loops appeared.
- No `[scale-up] storage triggered` event appeared, so activation still needs a threshold or load sweep.

## Evidence

### Elasticity Events

- `elasticity_events.csv` shows one reserve add and one reserve ready event per LAN.
- `node_lifecycle_timings.csv` records:
  - LAN1 add `edge_storage_lan1_dyn1`: 0.92 s total; ready in 12.47 s.
  - LAN2 add `edge_storage_lan2_dyn1`: 0.81 s total; ready in 12.36 s.
- No reserve cleanup event was parsed after readiness.

### Tier 1 Selective Sync

Tier 1 was not part of this run and no selective-sync container appeared.

### Resource Shape

- `server_count` stayed fixed at 1.0 for the whole run.
- `storage_count` averaged 1.16 overall, with a p95 of 2.0, which matches one standby reserve appearing without full storage activation.
- During `reserve_trigger_lan1`, median `time_db` rose sharply on the cross-region side of the workload, but late `demand_drop` medians dropped back toward the low single-digit range while the reserve remained visible.

### Request Latency by Phase

| Phase | Mean (ms) | p95 (ms) | Failures |
| --- | ---: | ---: | ---: |
| `baseline` | 45.87 | 140.59 | 0 / 1,918 |
| `reserve_trigger_lan1` | 120.30 | 326.31 | 4 / 20,339 |
| `demand_drop` | 59.22 | 180.16 | 0 / 2,883 |

### Traffic Handling

- Overall request success was 25,136 / 25,140 = 99.98%.
- All four failures occurred inside `reserve_trigger_lan1`, so the late window remained clean.
- LAN asymmetry remained visible in latency, with LAN2 carrying the higher cross-region DB cost during the trigger phase, but that did not turn into a cleanup or routing collapse.

## Practical Interpretation

This run is sufficient as the reserve-liveness gate for the stability family. It proves the heartbeat fix kept both standby replicas alive long enough to support later activation experiments. It does not prove the storage trigger thresholds are low enough to activate the reserve under this workload.

## Follow-Up

Proceed to the storage-reserve threshold or load sweeps if the next question is activation, or treat this run as the passed prerequisite before Tier 1 work.
