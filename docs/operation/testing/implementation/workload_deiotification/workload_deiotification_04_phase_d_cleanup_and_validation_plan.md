# Workload De-IoT-ification — Phase D Legacy Name Cleanup and Validation Plan

> **Status**: Planned · **Date**: 2026-07-02
> **Parent**: [`../../workload_deiotification_plan.md`](../../workload_deiotification_plan.md)
> **Scope**: Remove legacy workload names after migration and run
> the final end-to-end validation plus audit.

## Objective

Phase D removes obsolete filenames and any remaining legacy workload names only after the new
content/feed workflow is already stable. It also defines the final validation
and audit criteria for declaring the rename complete.

## Cleanup Targets

### Legacy source entrypoints

By the time Phase D begins, the legacy seeder source files are expected to be
gone already. Phase D should verify absence rather than plan their deletion.

- `source/scripts/testing/sensor_reports.py`
- `source/scripts/testing/device_registry.py`

Implementation rule:

- If either legacy seeder file still exists at Phase D start, treat that as
	migration debt left behind by earlier phases and remove it before the final
	validation pass.

### Live snapshot artifacts

The active generator workflow treats `source/scripts/testing/data/workload_snapshot/`
as a live input surface rather than a historical cache. Phase D must audit and
clean that directory together with the runtime rename.

- `source/scripts/testing/data/workload_snapshot/sensor_devices.json`
- `source/scripts/testing/data/workload_snapshot/device_registry.json`

Implementation rule:

- Regenerate the canonical snapshot with `export_workload_snapshot.py` and
	remove any leftover legacy snapshot filenames before the final validation
	pass. The target end state is that the live snapshot directory exposes only
	`content_items.json` and `user_profiles.json`.

### Legacy names still to purge

Candidates for removal after all active callers and docs have moved:

- Old CLI flags such as `--seed-devices` and `--seed-nodes`
- Old Makefile variables such as `DEVICES` and `NODES`
- Any leftover route, request-type, or workload-surface names that survived earlier slices

## End-to-End Validation

The final end-to-end pass should execute these checks in order. Treat these as
the canonical Phase D validation commands unless a later approved plan changes
the active operator workflow.

Environment preconditions for the standalone checks in steps 4 and 5:

- The network is already deployed.
- The named client namespaces used below already exist on both LANs. The
	examples assume `lan1_client_1..3` and `lan2_client_1..3` are available.
- The active controller override remains
	`source/scripts/testing/controller_env_overrides/current_state_integrated.env`.
- The validation run uses the canonical phase file
	`source/scripts/testing/phases.json`.

1. Confirm the canonical phase profile before any runtime validation if there
	 is any doubt that `phases.json` was edited during earlier slices:

	 ```bash
	 python source/scripts/testing/setup/fix_phases.py --dry-run
	 ```

2. Regenerate the canonical seeded data and the live snapshot directory:

	 ```bash
	 make -C source/scripts setup_test_data CONTENT_ITEMS=6000 USERS=100
	 ```

3. Reconcile the live snapshot directory with the canonical exported filenames.
	 `setup_test_data` regenerates `content_items.json` and `user_profiles.json`,
	 but it does not itself prove that stale legacy snapshot files are gone. If
	 legacy snapshot files still exist after step 2, remove them and then prove
	 the final directory state explicitly:

	 ```bash
	 rm -f source/scripts/testing/data/workload_snapshot/sensor_devices.json \
	   source/scripts/testing/data/workload_snapshot/device_registry.json

	 test -f source/scripts/testing/data/workload_snapshot/content_items.json
	 test -f source/scripts/testing/data/workload_snapshot/user_profiles.json
	 test ! -e source/scripts/testing/data/workload_snapshot/sensor_devices.json
	 test ! -e source/scripts/testing/data/workload_snapshot/device_registry.json
	 ```

4. Confirm the standalone generator can emit only the renamed request surface
	 under the canonical profile:

	 ```bash
	 sudo python3 source/scripts/testing/traffic_generator.py \
		 --config source/scripts/testing/phases.json \
		 --clients-lan1 lan1_client_1,lan1_client_2,lan1_client_3 \
		 --clients-lan2 lan2_client_1,lan2_client_2,lan2_client_3 \
		 --snapshot-dir source/scripts/testing/data/workload_snapshot \
		 --output source/scripts/testing/metrics/client_requests_phase_d_dry_run.csv \
		 --vip 10.0.0.253:5000 \
		 --dry-run
	 ```

5. Run a real VIP-routed edge-server smoke test for all 5 workload endpoints.
	 The smoke test is not complete unless each request goes through
	 `VIP_SERVER` and reaches the implemented renamed route:

	 ```bash
	 sudo bash source/scripts/testing/trace_request.sh --ns lan1_client_1 \
		 -- curl -s "http://10.0.0.253:5000/content/lan1::content::001?requester=lan1::user::001"

	 sudo bash source/scripts/testing/trace_request.sh --ns lan1_client_1 \
		 -- curl -s "http://10.0.0.253:5000/feed/lan1::user::001?limit=10"

	 sudo bash source/scripts/testing/trace_request.sh --ns lan1_client_1 \
		 -- curl -s "http://10.0.0.253:5000/service_pressure?window_min=10&limit=10"

	 sudo bash source/scripts/testing/trace_request.sh --ns lan1_client_1 \
		 -- curl -s -X POST http://10.0.0.253:5000/content \
				-H "Content-Type: application/json" \
				-d '{"content_id":"lan1::content::001","engagement":42,"lan":"lan1"}'

	 sudo bash source/scripts/testing/trace_request.sh --ns lan1_client_1 \
		 -- curl -s -X POST http://10.0.0.253:5000/content/aggregate \
				-H "Content-Type: application/json" \
				-d '{"lan":"lan1","engagement_threshold":10}'
	 ```

6. Run one full canonical experiment with the exact documented operator-facing
	 launch template and record the resulting run directory under
	 `source/scripts/testing/metrics/`. This step is intentionally a cold-start
	 end-to-end validation: it re-runs `setup_network`, `create_clients`, and
	 `setup_test_data` from the top-level launch surface to confirm that the
	 canonical integrated launch still works after the Phase D cleanup.

	 ```bash
	 sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
		 OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
		 RUN_LABEL=phase_d_validation \
		 PHASES_CONFIG=testing/phases.json \
		 WAN_RTT_MS=260 CLIENTS=48 CONTENT_ITEMS=6000 USERS=100 STORAGE_CPUS=0.10 \
		 SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
	 ```

7. Run the minimum analysis CLI validation against that completed run folder:

	 ```bash
	 python -m source.scripts.testing.analysis.cli_endpoint_breakdown --run-dir source/scripts/testing/metrics/<run_dir>
	 python -m source.scripts.testing.analysis.cli_simple_run --run-dir source/scripts/testing/metrics/<run_dir>
	 ```

### Canonical final validation profile

Unless a separate approval explicitly chooses a different validation profile,
Phase D should validate against the canonical active workload profile:

- use `source/scripts/testing/phases.json`
- do not pass a `phases_override/*.json` file
- if needed, run `source/scripts/testing/setup/fix_phases.py --dry-run` first
	to confirm that `phases.json` already matches the canonical content-discovery
	profile before launching the final experiment

## Final Audit Criteria

### Active workload code-path audit

Active workload code paths should no longer rely on:

- `sensor_reports`
- `device_registry`
- `device_status`
- `/device/`
- old seeder filenames as primary entrypoints

No deprecated compatibility layer is part of the target state. Any leftover
legacy names found here should be treated as migration debt to remove, not as
supported aliases to keep.

Include in this audit:

- `source/docker/edge_server/source/**`
- `source/scripts/testing/**`
- `source/scripts/testing/data/workload_snapshot/**`
- `source/scripts/Makefile`

Exclude from this audit unless a separate cleanup task promotes them into
scope:

- `source/scripts/testing/metrics/**`
- archived or historical findings under `source/scripts/testing/analysis/**/findings/**`
- historical controller and service logs

### Active-doc audit

The active-doc set from Phase C should not expose:

- old collections
- old route examples
- old request-type names
- IoT framing
- old primary launch flags/variables

Include in this audit exactly:

- `docs/operation/testing/testing_workloads.md`
- `docs/operation/testing/traffic_generator.md`
- `docs/operation/testing/testing_overview.md`
- `docs/operation/testing/trace_request.md`
- `docs/operation/testing/edge_server_compute_load.md`
- `docs/operation/testing/golden_config.md`
- `docs/operation/testing/experiment_campaign_brief.md`

`experiment_campaign_brief.md` remains mandatory in Phase D because
`testing_overview.md` still points operators at it as part of the active
workflow.

Exclude from this audit unless separately promoted into active scope:

- `docs/operation/testing/analysis_toolchain.md`
- historical experiment result notes
- archived testing plans and archived run notes

### Status-model audit

Confirm that the implementation keeps this distinction consistently:

- `payload.status`: stored 3-state content status
- `relevance`: computed 4-state classification

## Completion Criteria

Phase D is complete only when all of the following hold:

- The full experiment run succeeds with the renamed workload surface.
- The analysis CLIs still work with the new endpoint/request labels.
- Legacy seeder source entrypoints are confirmed absent.
- The live workload snapshot directory contains only `content_items.json` and
	`user_profiles.json` as the active exported snapshot artifacts, and the
	legacy snapshot filenames are confirmed absent.
- Any remaining legacy workload-facing names are removed from active surfaces.
- The final audit finds no stale active-surface workload terms.

## Out of Scope for Phase D

- Redesigning the workload shape itself
- Controller policy changes
- Historical archive cleanup beyond surfaces still in active use