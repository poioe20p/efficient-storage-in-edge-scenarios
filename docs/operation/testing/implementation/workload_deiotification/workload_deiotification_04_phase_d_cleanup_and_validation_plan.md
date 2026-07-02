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

### Legacy files

Remove only after all callers have migrated:

- `source/scripts/testing/sensor_reports.py`
- `source/scripts/testing/device_registry.py`

### Legacy names still to purge

Candidates for removal after all active callers and docs have moved:

- Old CLI flags such as `--seed-devices` and `--seed-nodes`
- Old Makefile variables such as `DEVICES` and `NODES`
- Any leftover route, request-type, or workload-surface names that survived earlier slices

## End-to-End Validation

The final end-to-end pass should cover:

1. `make -C source/scripts setup_test_data`
2. `traffic_generator.py --dry-run`
3. A real edge-server smoke test of the 5 workload endpoints
4. `make -C source/scripts run_experiment ...`
5. At least one analysis CLI run, including `cli_endpoint_breakdown.py` and `cli_simple_run.py`

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

### Active-doc audit

The active-doc set from Phase C should not expose:

- old collections
- old route examples
- old request-type names
- IoT framing
- old primary launch flags/variables

### Status-model audit

Confirm that the implementation keeps this distinction consistently:

- `payload.status`: stored 3-state content status
- `relevance`: computed 4-state classification

## Completion Criteria

Phase D is complete only when all of the following hold:

- The full experiment run succeeds with the renamed workload surface.
- The analysis CLIs still work with the new endpoint/request labels.
- Deprecated legacy files are removed.
- Any remaining legacy workload-facing names are removed from active surfaces.
- The final audit finds no stale active-surface workload terms.

## Out of Scope for Phase D

- Redesigning the workload shape itself
- Controller policy changes
- Historical archive cleanup beyond surfaces still in active use