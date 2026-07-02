# Workload De-IoT-ification Plan

> **Status**: Plan — approved, split into phase files · **Date**: 2026-07-02
> **Purpose**: Reframe the testing workload as a multi-region content discovery
> platform, remove IoT-specific terminology from active workload surfaces, and
> preserve the current scaling mechanics.

---

## Scenario

**Multi-Region Content Discovery Platform** — an edge-deployed content
syndication and discovery service where each LAN owns a regional content set,
users subscribe to topic tags, and demand shifts between storage-locality and
compute-analytics regimes.

---

## Locked Requirements

| # | Requirement |
|---|---|
| R1 | Zero IoT language in active workload code paths, active testing/operator docs, and primary help/examples |
| R2 | Collections rename to `content_items` and `user_profiles` |
| R3 | Primary endpoints rename to `/content/<id>`, `/feed/<user_id>`, `/content`, and `/content/aggregate` |
| R4 | Request types rename to `content_lookup`, `feed_ranking`, `content_update`, and `content_aggregate` |
| R5 | Controller and telemetry pipeline remain unchanged unless a workload-facing string is proven hardcoded |
| R6 | Stored workload signal remains under `payload` as `payload.engagement` |
| R7 | Stored `payload.status` is a 3-state item status (`quiet`, `trending`, `hot`) |
| R8 | Computed relevance remains a 4-state classification (`quiet`, `steady`, `trending`, `hot`) |
| R9 | Mechanical behavior is preserved: second MongoDB read, per-type weighting, deterministic SHA-256 jitter, per-user overrides |
| R10 | Active workload-facing CLI/env names are rewritten directly; deprecated compatibility aliases are not part of the plan |

---

## Core Mappings

### Endpoint Mapping

| Old | New |
|---|---|
| `/device/<id>/latest?node_id=` | `/content/<id>?requester=<user_id>` |
| `/dashboard/<node_id>?limit=N` | `/feed/<user_id>?limit=N` |
| `/service_pressure?...` | `/service_pressure?...` |
| `/device_update` | `/content` |
| `/device_aggregate` | `/content/aggregate` |

### Request Type Mapping

| Old | New |
|---|---|
| `device_status` | `content_lookup` |
| `dashboard` | `feed_ranking` |
| `service_pressure` | `service_pressure` |
| `device_update` | `content_update` |
| `device_aggregate` | `content_aggregate` |

### Function Mapping

| Old | New |
|---|---|
| `score_device_severity()` | `score_content_relevance()` |
| `score_dashboard_urgency()` | `score_feed_relevance()` |
| `compute_dashboard_summary()` | `compute_feed_summary()` |
| `verify_fleet_integrity()` | `verify_feed_integrity()` |

---

## Phase Files

Detailed implementation guidance is split into phase-specific files under
[`docs/operation/testing/implementation/workload_deiotification/`](implementation/workload_deiotification/).

| Phase | File | Scope |
|---|---|---|
| A | [`workload_deiotification_01_phase_a_data_model_and_seeding_plan.md`](implementation/workload_deiotification/workload_deiotification_01_phase_a_data_model_and_seeding_plan.md) | Canonical schema, seeders, snapshot export, indexes, Makefile, and runner seeding/help text |
| B | [`workload_deiotification_02_phase_b_request_path_and_local_state_plan.md`](implementation/workload_deiotification/workload_deiotification_02_phase_b_request_path_and_local_state_plan.md) | Edge-server routes, compute module, local request state, config naming, traffic generator, and request tracing |
| C | [`workload_deiotification_03_phase_c_phase_config_analysis_and_docs_plan.md`](implementation/workload_deiotification/workload_deiotification_03_phase_c_phase_config_analysis_and_docs_plan.md) | Phase JSONs, helper scripts, analysis labels, a full rewrite of `testing_workloads.md`, and targeted section rewrites in `testing_overview.md` plus the other active testing/operator docs |
| D | [`workload_deiotification_04_phase_d_cleanup_and_validation_plan.md`](implementation/workload_deiotification/workload_deiotification_04_phase_d_cleanup_and_validation_plan.md) | Legacy name cleanup, end-to-end validation, and final audit |

The phase files define implementation slices for the rewrite. They are not
meant to create intermediate repository states that are independently runnable
end to end under the new workload. A later phase may still be required before
the rewritten workflow is fully executable.

---

## Active Surface Scope

The mandatory zero-IoT audit applies to these active surfaces:

- Workload code paths under `source/docker/edge_server/source/` and `source/scripts/testing/`
- Primary operator scripts and examples, including `run_experiment.sh` and `trace_request.sh`
- Active testing/operator docs:
  - `testing_workloads.md`
  - `traffic_generator.md`
  - `testing_overview.md`
  - `trace_request.md`
  - `edge_server_compute_load.md`
  - `golden_config.md`
- `experiment_campaign_brief.md` only if it is still used as a live operator brief for current runs

Historical notes, archived experiments, and older campaign artifacts are not
part of the mandatory rename unless they are promoted back into active use.

---

## Phase Gates

These gates track completion of each implementation slice. They do not imply
that every earlier phase leaves the repository fully runnable under the new
workload before the remaining slices are applied.

| Phase | Validation Gate |
|---|---|
| A | `make setup_test_data` completes and exports `content_items.json` + `user_profiles.json` |
| B | `traffic_generator.py --dry-run` and `trace_request.sh` show only the new content/feed routes |
| C | Phase helper scripts regenerate mixes with the new request names, and active docs no longer describe the workload as IoT-based |
| D | One full experiment run succeeds, analysis still works, and the final audit finds no stale active-surface terms |

---

## Final Audit Policy

The final audit should check both wording and runnable behavior.

1. **Active docs and help text** must not expose old workload names such as
   `sensor_reports`, `device_registry`, `device_status`, `/device/...`,
   `dashboard`, `--seed-devices`, `--seed-nodes`, or `IoT`.
2. **Active workload code paths** must not use old collection names, route
   names, or request-type names.
3. **Stored item status vs computed relevance** must remain distinct:
   `payload.status` is the stored 3-state content signal, while `relevance`
   is the computed 4-state classification.

The detailed audit commands and removal criteria live in the Phase D file.

---

## Risks

| Risk | Mitigation |
|---|---|
| Hidden string dependencies in analysis or helper scripts | Audit phase helpers and analysis labels together in Phase C |
| Operator wrapper breakage from renamed flags/vars | Rewrite active wrappers, flags, and help text in the same phase as each interface change |
| Scope creep into historical notes | Treat archived or historical material as separate cleanup unless it is still operationally active |
| Inconsistent status vocabulary between stored payload and computed scoring | Keep the 3-state vs 4-state distinction explicit in Phase A and Phase B |
