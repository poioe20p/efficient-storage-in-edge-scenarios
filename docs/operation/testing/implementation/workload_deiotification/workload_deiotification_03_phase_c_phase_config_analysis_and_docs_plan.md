# Workload De-IoT-ification — Phase C Phase Config, Analysis, and Docs Plan

> **Status**: Planned · **Date**: 2026-07-02
> **Parent**: [`../../workload_deiotification_plan.md`](../../workload_deiotification_plan.md)
> **Scope**: Rename phase mixes, helper scripts, analysis labels, and the
> active testing/operator docs that still describe the workload with the old
> device/dashboard framing.

## Objective

Phase C migrates the remaining configuration and operator surfaces after the
runtime path is already using the new names. At the end of this phase, helper
scripts regenerate the new request names and active workload docs no longer
describe the workload as IoT-based.

## Files and Required Changes

### 1. Phase JSONs and phase helpers

Files:

- `source/scripts/testing/phases.json`
- `source/scripts/testing/phases_override/phases_tier1_smoke.json`
- `source/scripts/testing/phases_override/phases_rq1_verify.json`
- `source/scripts/testing/phases_override/phases_mini.json`
- `source/scripts/testing/_fix_phases.py`
- `source/scripts/testing/setup/fix_phases.py`

Required changes:

- Rename all request-type keys inside `mix` dictionaries.
- Update helper-script prose so it no longer says mixed IoT workload, devices, or dashboards.
- Keep the phase names themselves unchanged unless a separate experiment-design change is approved.

### 2. Analysis labels

Files:

- `source/scripts/testing/analysis/cli_endpoint_breakdown.py`
- Any other analysis CLI with hardcoded request labels or response-key assumptions

Required changes:

- Rename endpoint labels from `device_status` and `dashboard` to `content_lookup` and `feed_ranking`.
- Update legends, titles, and help text.
- Verify whether any analysis code assumes old `/service_pressure` response keys.

### 3. Active testing/operator docs

Mandatory active-doc scope:

- `docs/operation/testing/testing_workloads.md`
- `docs/operation/testing/traffic_generator.md`
- `docs/operation/testing/testing_overview.md`
- `docs/operation/testing/trace_request.md`
- `docs/operation/testing/edge_server_compute_load.md`
- `docs/operation/testing/golden_config.md`

Conditional active-doc scope:

- `docs/operation/testing/experiment_campaign_brief.md` if it is still used as a live runbook for current campaigns

Required changes:

- Replace IoT/device/dashboard framing with content/feed framing.
- Replace old endpoint examples, collection names, and request labels.
- Update launch examples so the primary names are content/user terminology.
- Remove old workload-facing compatibility wording from the active docs instead of carrying it forward as a transitional note.

### 4. `docs/operation/testing/testing_workloads.md` — full rewrite

This file is not a light terminology pass. It should be rewritten as the new
canonical workload narrative.

Required changes:

- Replace the headline scenario "Multi-Region IoT Edge Monitoring Platform"
	with the approved content-discovery framing.
- Rewrite the collections section around `content_items`, `user_profiles`, and
	edge-local support state.
- Replace all request descriptions with the new content/feed routes and the
	new request-type names.
- Rewrite the data examples so they show content items and user profiles,
	not devices and monitoring nodes.
- Rewrite the compute-regime and storage-regime explanations so they describe
	content lookups and feed ranking instead of device status and dashboards.
- Rewrite the MongoDB justification using heterogeneous content records,
	topic-tag filtering, nested metadata, and read-locality pressure.
- Keep the workload claims, measurements, and experiment logic intact unless
	a separate experiment-design change is approved.

Sections that should be treated as rewrite targets, not spot edits:

- scenario overview
- core workload model
- request types
- phase-based demand shift
- MongoDB justification
- "keep it simple"
- what the experiments prove
- thesis-RQ mapping and baseline families

### 5. `docs/operation/testing/testing_overview.md` — targeted section rewrites

This file should stay an overview, but several sections need explicit updates.

Required section updates:

- **Architecture: Experiment Data Flow**
	- replace seeder names, snapshot file names, and workload labels in the
		diagram and surrounding prose.
- **Golden Configuration**
	- update launch examples so the primary exposed variables and examples use
		the new content/user terminology.
- **Client-Facing Workload Requests**
	- rewrite the request table and shorthand bullets around `content_lookup`,
		`feed_ranking`, and `service_pressure`.
- **Components**
	- update the summaries for `testing_workloads.md`, `traffic_generator.md`,
		`edge_server_compute_load.md`, and `trace_request.md` so they reflect the
		new content/feed framing.
- **Execution Order**
	- replace seeder commands, endpoint examples, and route examples with the
		new names.
- **What the Experiments Prove**
	- keep the claims intact, but rewrite the examples and mechanism references
		so they no longer rely on the old device/dashboard terminology.

The rest of the file can remain structurally the same if the wording no longer
describes the workload as IoT-based.

## Audit Rules for Phase C

The documentation audit should be stronger than a narrow IoT-word grep.

### Active-doc wording checks

Active docs and primary help text should not expose:

- `sensor_reports`
- `device_registry`
- `device_status`
- `/device/`
- `dashboard` when it still refers to the old route or workload role
- `DEVICES=` and `NODES=` when they are still presented as the primary
	workload-facing launch vocabulary in active operator docs
- `--seed-devices`
- `--seed-nodes`
- `IoT`

### Notes on generic terms

- `device` and `node` may still appear in unrelated platform or infrastructure contexts outside the active workload surface.
- The audit should focus on workload meaning, not every incidental infrastructure use of a generic noun.

## Validation Gate

Phase C is complete only when all of the following hold:

- Phase helper scripts regenerate mixes with the new request names.
- `cli_endpoint_breakdown.py` works with the renamed endpoint labels.
- `testing_workloads.md` is fully rewritten around the content-discovery
	workload rather than patched term-by-term.
- `testing_overview.md` has its data-flow, request-table, components, and
	execution-order sections updated to the new naming.
- The mandatory active-doc set no longer describes the workload as IoT-based.
- If `experiment_campaign_brief.md` remains active, it no longer points operators at the old seeding scripts or old workload names.

## Out of Scope for Phase C

- Runtime route implementation
- Seeder internals
- Deleting legacy source files
- Controller-side logic changes