# Elasticity Documentation Split Plan

## Scope

Split the current elasticity overview into a short hub page plus dedicated
documents for orchestration, scale-up, and scale-down.

## Review Workflow

1. Execute one step at a time.
2. Stop after each review checkpoint.
3. Review the output of the current step before starting the next one.
4. Do not batch multiple steps into one implementation pass.

## Target Files

### Files To Create

1. `docs/operation/elasticy_manager/orchestration/elasticity_manager_orchestration.md`
2. `docs/operation/elasticy_manager/scale_up/compute_scale_up.md`
3. `docs/operation/elasticy_manager/scale_up/storage_scale_up.md`
4. `docs/operation/elasticy_manager/scale_down/compute_scale_down.md`
5. `docs/operation/elasticy_manager/scale_down/storage_scale_down.md`

### Files To Update

1. `docs/operation/elasticy_manager/elasticity_overview.md`
2. `docs/operation/testing/testing_overview.md`
3. `docs/operation/system_mechanisms.md`
4. `docs/operation/telemetry/telemetry_overview.md`
5. `docs/operation/selective_sync/selective_sync_overview.md`
6. `docs/operation/elasticy_manager/implementation/scale_down_instrumentation.md`
7. `docs/operation/elasticy_manager/implementation/compute_graceful_scale_down/README.md`
8. `docs/operation/elasticy_manager/implementation/storage_standby_first_scaleup/README.md`
9. `docs/operation/elasticy_manager/implementation/storage_standby_first_scaleup/phase_1_state_and_accounting.md`
10. `docs/operation/elasticy_manager/implementation/storage_standby_first_scaleup/phase_2_reserve_preparation.md`
11. `docs/operation/elasticy_manager/implementation/storage_standby_first_scaleup/phase_3_first_alert_activation.md`
12. `docs/operation/elasticy_manager/implementation/storage_standby_first_scaleup/phase_4_operational_visibility.md`

## Step 1 - Create the new document structure

Create these files with titles and section headings only. Do not move content
yet.

1. `docs/operation/elasticy_manager/orchestration/elasticity_manager_orchestration.md`
2. `docs/operation/elasticy_manager/scale_up/compute_scale_up.md`
3. `docs/operation/elasticy_manager/scale_up/storage_scale_up.md`
4. `docs/operation/elasticy_manager/scale_down/compute_scale_down.md`
5. `docs/operation/elasticy_manager/scale_down/storage_scale_down.md`

Use these section headings.

### `orchestration/elasticity_manager_orchestration.md`

1. Purpose
2. Thread Interaction
3. Alert Types
4. Alert Priority Order
5. Queue Dispatch
6. Busy and Pending Drain State
7. Cleanup Dispatch
8. Handoffs to Scaling Policy, Node Adders, and Topology
9. Tier 1 Reference

### `scale_up/compute_scale_up.md`

1. Purpose
2. Trigger Path
3. Compute Degradation Score
4. Adaptive Threshold and Peer Relief
5. Cooldown and Cap Rules
6. Provisioning Flow
7. VIP Admission
8. Environment Variables
9. Related Diagram
10. Related Plans

### `scale_up/storage_scale_up.md`

1. Purpose
2. Trigger Path
3. Storage Degradation Score
4. Diminishing Increment Threshold
5. Cooldown and Cap Rules
6. Provisioning Flow
7. Async Replica-Set Join
8. Deferred VIP_DATA Promotion
9. Standby First Scale-Up Reference
10. Environment Variables
11. Related Diagram
12. Related Plans

### `scale_down/compute_scale_down.md`

1. Purpose
2. Idle Detection
3. Candidate Selection
4. Phase A Drain
5. Phase B Cleanup
6. Drain Cancel
7. Busy and Pending Drain Interaction
8. Environment Variables
9. Instrumentation Reference
10. Related Diagram

### `scale_down/storage_scale_down.md`

1. Purpose
2. Idle Detection
3. VIP Isolation
4. Replica-Set Removal
5. Script Cleanup
6. Failure Timeout Handling
7. Environment Variables
8. Related Diagram

### Review checkpoint 1

Verify:

1. All five new files exist
2. File names are correct
3. Section headings are present
4. No content has been moved yet

## Step 2 - Rewrite the overview as a short hub page

Update `docs/operation/elasticy_manager/elasticity_overview.md`.

Keep only these parts:

1. Purpose and scope of the elasticity manager
2. Short summary of Thread 1, Thread 2, and Thread 3 interaction
3. A document map linking to:
   1. orchestration
   2. compute scale-up
   3. storage scale-up
   4. compute scale-down
   5. storage scale-down
4. A diagram map linking to the compute and storage scale-up and scale-down diagrams
5. A short Tier 1 note that points to `docs/operation/selective_sync/selective_sync_overview.md`
6. A short implementation-plan section linking to the relevant plan documents

Remove these parts from the overview:

1. Full alert tables
2. Full threshold tables
3. Full node-addition description
4. Full node-removal description
5. Full queue-priority explanation
6. Full network-script description
7. Full Tier 1 lifecycle description
8. Any run-specific issue or retrospective section that depends on old anchors

### Review checkpoint 2

Verify:

1. The overview is short
2. The overview acts as a hub page
3. The overview links to all new documents
4. Tier 1 is only referenced, not duplicated

## Step 3 - Fill the orchestration document

Update `docs/operation/elasticy_manager/orchestration/elasticity_manager_orchestration.md`.

Move or rewrite only elasticity-manager-specific coordination content into this file.

Include:

1. Thread 2 callback flow in `main_n*.py`: registry sync, control-event dispatch, scale-up evaluation, scale-down evaluation, and alert submission
2. Alert types currently handled by `ElasticityManager`:
   1. `ComputeAlert`
   2. `DataAlert`
   3. `ScaleDownComputeAlert`
   4. `ScaleDownDataAlert`
   5. `CleanupComputeAlert`
   6. `CancelComputeDrainAlert`
   7. `SelectiveSyncAlert`
   8. `SelectiveSyncReconfigureAlert`
   9. `ScaleDownSelectiveAlert`
   10. `CleanupSelectiveAlert`
3. Current alert priority ordering from `_ALERT_PRIORITY`
4. Queue dispatch behavior using `PriorityQueue` plus FIFO tie-breaker from `_alert_seq`
5. Busy and pending-drain behavior through `has_active_operation()`, `is_busy()`, `blocks_compute_scale_up()`, `blocks_storage_scale_up()`, `has_pending_drain()`, and `pending_compute_drain_count()`
6. Cleanup dispatch behavior through `submit_cleanup()`, including routing by `PendingDrain.node_type`
7. Manager-owned handoff points between scaling policy, node adders, and topology, including `register_new_server_backend()`, `register_backend_ip()`, `unregister_server_backend()`, and `unregister_storage_backend()`
8. Current Tier 1 wiring through `attach_selective_sync_coordinator()` and `attach_tier1_broadcaster()`
9. A short Tier 1 integration note with a reference to the selective-sync overview
10. The dormant Tier 2 supersede hook for cross-LAN `DataAlert`

Do not include:

1. General platform mechanisms
2. Full Tier 1 subsystem explanation
3. Full scale-up threshold tuning details
4. Full scale-down lifecycle details

### Review checkpoint 3

Verify:

1. The file only contains elasticity-manager orchestration content
2. Queue and cleanup behavior are covered
3. Current selective alert handling is included
4. Tier 1 is still only referenced

## Step 4 - Fill the compute scale-up document

Update `docs/operation/elasticy_manager/scale_up/compute_scale_up.md`.

Include:

1. Compute trigger path from `_on_telemetry_update()` through `ScalingPolicy.evaluate_scale_up()` and `_evaluate_compute_scale_up()` to `ComputeAlert`
2. Compute degradation score inputs: `average_cpu_percent` and `avg_time_proc_ms`
3. Effective compute-node count for scale-up: dynamic compute count minus `pending_compute_drain_count()`
4. Adaptive threshold behavior
5. Peer-relief behavior
6. Compute cooldown and cap behavior
7. The current rebound path: submit `ComputeAlert` first, then `submit_cancel_compute_drain()` when a compute drain is pending
8. Current blocking rule for compute scale-up through `blocks_compute_scale_up()`
9. Compute provisioning path in Thread 3 through `_handle_compute()` and `ComputeNodeAdder.add_edge_server()`
10. Compute VIP admission behavior through `register_new_server_backend()`
11. Compute-related environment variables
12. Link to the compute scale-up diagram
13. Link to relevant implementation plans

### Review checkpoint 4

Verify:

1. The file is compute-only
2. The trigger, threshold, provisioning, and VIP sections are present
3. The effective-count and rebound path are present
4. Environment variables are compute-only

## Step 5 - Fill the storage scale-up document

Update `docs/operation/elasticy_manager/scale_up/storage_scale_up.md`.

Include:

1. Storage trigger path from `_on_telemetry_update()` through `ScalingPolicy.evaluate_scale_up()` and `_evaluate_storage_scale_up()` to `DataAlert`
2. Storage degradation score inputs: `avg_storage_cpu_percent` and the tail-aware latency signal `max(avg_time_db_ms, p95_time_db_ms)`
3. Diminishing-increment threshold behavior
4. Current `DataAlert` construction for same-LAN scale-up: `rs_name=f"rs_net{lan}"` and `primary_container=f"edge_storage_server_n{lan}"`
5. Storage cooldown and cap behavior
6. Current blocking rule for storage scale-up through `blocks_storage_scale_up()`
7. Storage provisioning path in Thread 3 through `_handle_data()` and `StorageNodeAdder.add_storage_node()`
8. Pre-seeding of backend IP mapping through `register_backend_ip()`
9. Async replica-set join path
10. Deferred VIP_DATA promotion path
11. Standby-first scale-up references
12. Storage-related environment variables
13. Link to the storage scale-up diagram
14. Link to relevant implementation plans

### Review checkpoint 5

Verify:

1. The file is storage-only
2. The tail-aware latency signal is present
3. The async join and deferred VIP promotion sections are present
4. The standby-first reference is present

## Step 6 - Fill the compute scale-down document

Update `docs/operation/elasticy_manager/scale_down/compute_scale_down.md`.

Include:

1. Compute idle detection path from `_on_telemetry_update()` through `evaluate_scale_down_compute()`
2. Current compute candidate selection rules:
   1. skip nodes already in pending drain
   2. require cached `ServerSummary`
   3. reject stale summaries older than `_SCALE_DOWN_CANDIDATE_MAX_STALENESS_S`
   4. require `server.state == "active"`
   5. require `node_age_s >= _NODE_BIRTH_GRACE_S`
   6. sort by `request_count`, `avg_cpu_percent`, `avg_time_proc_ms`, and newest `last_report_ts`
3. Current post-trigger behavior: when compute underutilisation fires, the compute scale-down window is cleared after that handling cycle; if no candidate is eligible, the same clear still happens
4. Async two-phase drain flow through `_handle_scale_down_compute()`
5. Cleanup flow through `_handle_cleanup_compute()`
6. Drain-cancel flow through `CancelComputeDrainAlert`, `cancel_drain()`, and `add_server_mac()`
7. Busy and pending-drain interaction relevant to compute
8. Compute scale-down environment variables
9. Link to the scale-down instrumentation plan
10. Link to the compute scale-down diagram

### Review checkpoint 6

Verify:

1. The file is compute-only
2. The ranked candidate-selection rules are present
3. Phase A, Phase B, and cancel behavior are present
4. Instrumentation reference is present

## Step 7 - Fill the storage scale-down document

Update `docs/operation/elasticy_manager/scale_down/storage_scale_down.md`.

Include:

1. Storage idle detection path from `_on_telemetry_update()` through `evaluate_scale_down_storage()`
2. Current storage candidate-selection rule: use `_node_registry.find_last_dynamic("storage")`
3. Synchronous storage removal flow through `_handle_scale_down_data()`
4. VIP isolation behavior through `unregister_storage_backend(domain=f"n{lan}")`
5. Replica-set removal flow through `StorageNodeAdder.remove_storage_node()`
6. Script cleanup flow
7. Timeout-ceiling skip behavior in storage idle detection when `avg_time_db_ms` exceeds `_SCALE_DOWN_DB_TIMEOUT_CEILING_MS`
8. Current post-trigger behavior: when storage underutilisation fires, the storage scale-down window is cleared after that handling cycle
9. Separate failure-detection path: absent-node detection is handled outside the storage underutilisation path
10. Storage scale-down environment variables
11. Link to the storage scale-down diagram

### Review checkpoint 7

Verify:

1. The file is storage-only
2. The current LIFO-style storage candidate selection is present
3. The synchronous removal path is clear
4. VIP isolation, `rs.remove()`, and cleanup are present

## Step 8 - Update elasticity implementation-plan references

Update these files so they point to the new split documentation instead of the
old monolithic overview sections:

1. `docs/operation/elasticy_manager/implementation/scale_down_instrumentation.md`
2. `docs/operation/elasticy_manager/implementation/compute_graceful_scale_down/README.md`
3. `docs/operation/elasticy_manager/implementation/storage_standby_first_scaleup/README.md`
4. `docs/operation/elasticy_manager/implementation/storage_standby_first_scaleup/phase_1_state_and_accounting.md`
5. `docs/operation/elasticy_manager/implementation/storage_standby_first_scaleup/phase_2_reserve_preparation.md`
6. `docs/operation/elasticy_manager/implementation/storage_standby_first_scaleup/phase_3_first_alert_activation.md`
7. `docs/operation/elasticy_manager/implementation/storage_standby_first_scaleup/phase_4_operational_visibility.md`

Use these target mappings where possible:

1. `scale_down_instrumentation.md` -> `scale_down/compute_scale_down.md` and `scale_down/storage_scale_down.md`
2. `compute_graceful_scale_down/README.md` -> `scale_down/compute_scale_down.md`
3. `storage_standby_first_scaleup/*` -> `scale_up/storage_scale_up.md`

### Review checkpoint 8

Verify:

1. These files still reference elasticity documentation
2. Their references now point to the new split files where needed
3. They do not depend on removed overview anchors

## Step 9 - Update cross-subsystem references

Update these files:

1. `docs/operation/testing/testing_overview.md`
2. `docs/operation/system_mechanisms.md`
3. `docs/operation/telemetry/telemetry_overview.md`
4. `docs/operation/selective_sync/selective_sync_overview.md`

Apply these rules:

1. Replace deep links to removed `elasticity_overview.md` anchors
2. Point general references to the trimmed overview hub page
3. Point scale-up references to the new scale-up files
4. Point scale-down references to the new scale-down files
5. Keep Tier 1 ownership in the selective-sync overview
6. Replace old references to generic node-removal text with the specific compute or storage scale-down document

Use these concrete target mappings.

### `docs/operation/testing/testing_overview.md`

1. Replace the `Known Issues` anchor link with plain text or a local note in `testing_overview.md`.
2. Do not retarget the `Known Issues` link to the trimmed overview hub page.
3. Replace the `Telemetry vs VIP Pool Discrepancy` anchor link with `orchestration/elasticity_manager_orchestration.md`.

### `docs/operation/system_mechanisms.md`

1. Keep generic subsystem-pointer references to elasticity pointing at `elasticity_overview.md` when the surrounding sentence is only a general navigation hint.
2. Replace the configuration bullet for elasticity thresholds, windows, and cooldowns with grouped links to:
   1. `scale_up/compute_scale_up.md`
   2. `scale_up/storage_scale_up.md`
   3. `scale_down/compute_scale_down.md`
   4. `scale_down/storage_scale_down.md`
3. Replace the edge-server drain endpoint reference to generic node-removal details with `scale_down/compute_scale_down.md`.
4. Replace the add/remove node lifecycle reference in the network-infrastructure section with grouped links to:
   1. `scale_up/compute_scale_up.md`
   2. `scale_up/storage_scale_up.md`
   3. `scale_down/compute_scale_down.md`
   4. `scale_down/storage_scale_down.md`

### `docs/operation/telemetry/telemetry_overview.md`

1. Replace the single elasticity link in the weighted-degradation-score paragraph with grouped links to:
   1. `scale_up/compute_scale_up.md`
   2. `scale_up/storage_scale_up.md`
   3. `scale_down/compute_scale_down.md`
   4. `scale_down/storage_scale_down.md`

### `docs/operation/selective_sync/selective_sync_overview.md`

1. Keep the general `Elasticity Manager overview` see-also reference pointing at the trimmed `elasticity_overview.md` hub page.
2. Add or prefer `orchestration/elasticity_manager_orchestration.md` only when the surrounding reference is specifically about queue priority, cleanup dispatch, or elasticity-manager integration.

### Review checkpoint 9

Verify:

1. No remaining links depend on removed overview anchors
2. Cross-subsystem references still resolve
3. The new split is visible from related subsystem docs
4. `testing_overview.md` no longer points run-specific notes at removed overview anchors
5. `system_mechanisms.md` uses specific split docs for thresholds and lifecycle paths
6. `telemetry_overview.md` points scale-threshold references to the split scale-up and scale-down docs

## Step 10 - Text cleanup and consistency pass

Run a final pass on all touched elasticity-manager documents.

Fix:

1. Corrupted text
2. Broken characters
3. Duplicated rows
4. Duplicated paragraphs
5. Field names that do not match current code terminology

Check consistency for:

1. `network_id`
2. `primary_container`
3. `ComputeAlert`
4. `DataAlert`
5. `ScaleDownComputeAlert`
6. `ScaleDownDataAlert`
7. `CleanupComputeAlert`
8. `CancelComputeDrainAlert`
9. `SelectiveSyncAlert`
10. `SelectiveSyncReconfigureAlert`
11. `ScaleDownSelectiveAlert`
12. `CleanupSelectiveAlert`
13. `submit_cleanup()`
14. `blocks_compute_scale_up()`
15. `blocks_storage_scale_up()`
16. `pending_compute_drain_count()`
17. `register_new_server_backend()`
18. `register_backend_ip()`

### Review checkpoint 10

Verify:

1. Touched elasticity-manager files read cleanly
2. Terminology matches the current codebase
3. No corrupted text remains

## Final Validation

1. Run markdown diagnostics on all touched files
2. Check that new files have valid internal links
3. Check that overview links resolve
4. Check that cross-subsystem references resolve

## Done Conditions

1. `docs/operation/elasticy_manager/elasticity_overview.md` is a short hub page
2. Compute and storage are documented separately for scale-up and scale-down
3. `docs/operation/elasticy_manager/orchestration/` exists and contains only elasticity-manager-specific coordination content
4. Tier 1 selective sync is referenced instead of duplicated
5. Old references to removed overview anchors are updated
6. Touched elasticity-manager documents no longer contain corrupted text
