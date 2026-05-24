# Operation Document Lifecycle

This index distinguishes current reference documents, active plans, and
historical implementation plans that have been archived after landing.

## Current Reference Documents

- `system_mechanisms.md`
- `vip_routing/vip_routing_overview.md`
- `testing/traffic_generator.md`
- `testing/edge_server_compute_load.md`
- `testing/trace_request.md`
- `testing/analysis_toolchain.md`
- `other/test_client_scripts.md`
- `other/edge_storage_connection_epoch_visuals.md`
- `vip_routing/implementation/vip_data_recovery_epoch_model.md`
- `elasticy_manager/implementation/compute_graceful_scale_down/README.md`

## Active Plans Kept In Place

- `other/micro_breaker_and_service_logs_plan.md`
- `other/edge_storage_connection_hard_failure_epoch_plan.md`
- `vip_routing/implementation/plans/01_mongodb_lease_warm_start_and_recovery_path_plan.md`
- `vip_routing/implementation/plans/implemented_02_mongodb_lease_request_state_machine/phase_4_optional_replay_safety_refinement.md`
- `elasticy_manager/implementation/storage_standby_first_scaleup/README.md`
- `elasticy_manager/implementation/plans/metric_drivers_investigation_plan.md`

## Implemented Phase Folders Kept In Place

- `vip_routing/implementation/plans/implemented_02_mongodb_lease_request_state_machine_plan.md`
- `vip_routing/implementation/plans/implemented_02_mongodb_lease_request_state_machine/README.md`
- `vip_routing/implementation/plans/implemented_03_mongodb_lease_failed_backend_avoidance_plan.md`
- `vip_routing/implementation/plans/implemented_03_mongodb_lease_failed_backend_avoidance/README.md`

## Historical Plans Archived After Landing

- `archive/other/heartbeat_dynamic_node_gate_plan.md`
- `archive/other/telemetry_refactor_plan.md`
- `archive/other/elasticity_ablation_matrix_plan.md`
- `archive/testing/elasticity_ablation_batch4_plan.md`
- `archive/testing/elasticity_ablation_batch5_plan.md`
- `archive/vip_routing/implementation/vip_warm_leases_plan.md`
- `archive/vip_routing/implementation/vip_data_recovery_vip_arming_plan.md`
- `archive/vip_routing/implementation/vip_warm_start_and_vip_data_refresh_plan.md`

## Notes

- Current reference documents should avoid `*_plan.md` filenames when they
  describe landed behavior or stable tooling.
- The 02/03 phased plan folders remain in place as implementation history and
  optional follow-on tracking, but the overview documents above are the
  canonical reference for the landed baseline.
- Historical plans stay in `archive/` when they still explain why the current
  mechanism behaves the way it does.
- Experiment result files and campaign briefs remain in the active tree because
  they are records, not pending work.
