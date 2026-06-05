# Results - Storage Reserve Validation

Checked run path: [../../../../../../source/scripts/testing/metrics/20260604_182338_storage_reserve_smoke](../../../../../../source/scripts/testing/metrics/20260604_182338_storage_reserve_smoke)

Supporting run summary: [../../../../../../source/scripts/testing/metrics/20260604_182338_storage_reserve_smoke/run_summary.md](../../../../../../source/scripts/testing/metrics/20260604_182338_storage_reserve_smoke/run_summary.md)

Checked against: [experiment_plan.md](./experiment_plan.md)

## Expectation Check

| Plan expectation | Status | Key evidence |
| --- | --- | --- |
| Both LANs prepare one standby full replica and reach the ready state | Met | `node_lifecycle_timings.csv` shows `edge_storage_lan1_dyn1` ready in 12.47 s and `edge_storage_lan2_dyn1` ready in 12.36 s. |
| Heartbeat persistence continues through the trigger and into `demand_drop` | Met | Standby service logs continue to emit heartbeat events through late `demand_drop`; reserve MACs remain visible in late `per_node_stats.csv` rows. |
| No cleanup regression appears | Met | No reserve cleanup events were parsed, no reserve removal appears in `container_events.csv`, and the controller logs did not show the old absent-node cleanup loop. |
| Telemetry still sees the reserve late in the run | Met | `per_node_stats.csv` still contains both reserve MACs in `demand_drop`, and `storage_count` reaches 2 without ever escalating into a full storage activation. |
| Missing storage activation is classified as `liveness passed, activation untested` | Met | The run produced no `[scale-up] storage triggered` marker, but it still met all four liveness conditions. |

## Overall Verdict

`storage_reserve_smoke` matched the plan and passed the reserve-liveness gate. The reserve stayed ready, visible, and heartbeating long enough to make later activation experiments meaningful. The run does not prove anything about activation thresholds, only that the persistent-reserve path is healthy enough for follow-on activation work.

## Caveats

- The plan still names `[reserve] prepare_submitted` and `[reserve] ready_reserved`, but the current controller logs express the same lifecycle through `[elasticity] standby_storage` plus the parsed `node_ready_timing` events.
- This run is intentionally not an activation proof. It should not be used to claim that the storage trigger thresholds are already correct.

## Next Action

Treat this result as the passed prerequisite for [../storage_reserve_use_validation/experiment_plan.md](../storage_reserve_use_validation/experiment_plan.md). The next reserve-side experiment is now the storage-reserve use-validation run, and the threshold/load sweeps should remain optional tuning work only after that plan reaches `reserve-used`.
