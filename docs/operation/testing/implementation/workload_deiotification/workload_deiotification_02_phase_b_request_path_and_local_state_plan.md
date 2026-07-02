# Workload De-IoT-ification — Phase B Request Path and Local State Plan

> **Status**: Planned · **Date**: 2026-07-02
> **Parent**: [`../../workload_deiotification_plan.md`](../../workload_deiotification_plan.md)
> **Scope**: Rename the live request path, local request-state model, and
> workload-facing configuration so the edge server and traffic generator speak
> content/feed terminology end to end.

## Objective

Phase B migrates the active HTTP surfaces and the local request-activity model.
At the end of this phase, the edge server, traffic generator dry-run output,
and request trace examples must all use the new content/feed naming.

## Canonical Decisions

### Endpoints

| Old | New |
|---|---|
| `/device/<id>/latest?node_id=` | `/content/<id>?requester=<user_id>` |
| `/dashboard/<node_id>?limit=N` | `/feed/<user_id>?limit=N` |
| `/device_update` | `/content` |
| `/device_aggregate` | `/content/aggregate` |

### Request kinds

| Old | New |
|---|---|
| `device_status` | `content_lookup` |
| `dashboard` | `feed_ranking` |
| `service_pressure` | `service_pressure` |
| `device_update` | `content_update` |
| `device_aggregate` | `content_aggregate` |

`service_pressure` is intentionally unchanged. It remains the edge-local
introspection request kind and should not be renamed or removed during Phase B.

### Local request-state vocabulary

| Old | New |
|---|---|
| `device_id` | `content_id` |
| `node_id` | `user_id` |
| `severity` | `relevance` |

`request_kind` stays named `request_kind`, but its workload-facing values must
become `content_lookup`, `feed_ranking`, `service_pressure`,
`content_update`, and `content_aggregate`. `status` also stays named `status`.
Its exact meaning is request-kind dependent and is fixed by the canonical
local-buffer recording rules below.

Stored and computed labels are intentionally distinct:

- `payload.status`: stored 3-state content status (`quiet`, `trending`, `hot`)
- `relevance`: computed 4-state classification (`quiet`, `steady`, `trending`, `hot`)

### Canonical local-buffer recording rules

The old schema already used two different local-buffer record shapes depending
on request kind:

- `device_status` entries represented one concrete device lookup, so they
  carried a real `device_id`, a real `node_id`, a computed `severity`, and the
  device's stored `payload.status`.
- `dashboard` entries represented one aggregate request, not one concrete
  device, so they used `device_id = null`, `severity = "normal"`, and
  `status = "dashboard"` as a request-type marker.

Phase B should preserve that behavior explicitly under the new names rather
than inventing a new buffer contract.

| `request_kind` | Recorded in local buffer? | `content_id` | `user_id` | `relevance` | `status` | `tags` |
|---|---|---|---|---|---|---|
| `content_lookup` | yes | concrete content ID | requester user ID | computed 4-state relevance for that content item | stored 3-state `payload.status` for that content item | content item tags |
| `feed_ranking` | yes | `null` | requesting user ID | constant `quiet` (semantic equivalent of the old `normal`) | literal string `feed_ranking` (semantic equivalent of the old `dashboard`) | requesting profile's `subscribed_tags` |
| `service_pressure` | no | n/a | n/a | n/a | n/a | n/a |
| `content_update` | no | n/a | n/a | n/a | n/a | n/a |
| `content_aggregate` | no | n/a | n/a | n/a | n/a | n/a |

Implementation rule:

- Phase B should continue recording only lookup-style and feed-style client
  requests in local request activity. The helper routes `service_pressure`,
  `content_update`, and `content_aggregate` stay out of the local buffer in
  this phase so the service-pressure signal preserves its current semantics.

## Files and Required Changes

### 1. `source/docker/edge_server/source/monitoring_workload_routes.py`

Required changes:

- Rename all route decorators and handler names to the content/feed equivalents.
- Replace collection names with `content_items` and `user_profiles`.
- Replace request parameter names (`node_id` → `requester`, internal `user_id`).
- Rewrite the synthetic write path so `/content` accepts the canonical body
  fields `content_id`, `engagement`, `lan`, and optional `update_padding`.
  The handler should update `payload.engagement` and `last_updated` directly,
  and any extra oplog-padding field must use content terminology rather than
  the old `pressure_level` field.
  Preserve the old route's `update_one(..., upsert=True)` behavior exactly:
  Phase B does not add unknown-ID rejection or schema backfill logic for this
  helper route.
- Rewrite the aggregate path so `/content/aggregate` accepts `lan` and
  `engagement_threshold`, matches on `payload.engagement`, groups by
  `content_type`, and emits `avg_engagement` instead of the old
  `pressure_level`/`avg_pressure` vocabulary.
- Replace field paths:
  - `device_type` → `content_type`
  - `payload.value` → `payload.engagement`
  - `metadata.alert_threshold` → `metadata.relevance_baseline`
  - `alert_config.email` → `profile_config.email`
  - `alert_config.threshold_override` → `profile_config.relevance_override`
- Keep `region_origin` and `last_updated` unchanged; they already fit the content-oriented schema and remain the canonical ownership/freshness fields.
- Update feed candidate projections and sort keys so ownership/freshness lookups use `region_origin` and `last_updated`.
- Replace `request_kind` values staged into local request activity.
- Rewrite workload-facing success and error payload keys so `/content/<id>` and
  `/feed/<user_id>` responses no longer expose `device_id`, `node_id`,
  `devices`, or `severity` names anywhere in the JSON contract.

### 2. `source/docker/edge_server/source/compute.py`

Required changes:

- Rename the four workload-facing functions:
  - `score_device_severity()` → `score_content_relevance()`
  - `score_dashboard_urgency()` → `score_feed_relevance()`
  - `compute_dashboard_summary()` → `compute_feed_summary()`
  - `verify_fleet_integrity()` → `verify_feed_integrity()`
- Rename constants and comments away from IoT language.
- Replace threshold-proximity logic so content scoring uses
  `payload.engagement / metadata.relevance_baseline` while preserving the
  existing per-type exponent, SHA-256 jitter, and per-user override behavior.
- Emit computed `relevance` using this exact calibrated-ratio mapping:
  - `hot` when calibrated ratio ≥ `1.00`
  - `trending` when calibrated ratio ≥ `0.85` and < `1.00`
  - `steady` when calibrated ratio ≥ `0.70` and < `0.85`
  - `quiet` otherwise
- Rename the lookup scoring object fields explicitly:
  - `severity` → `relevance`
  - `anomaly_score` → `relevance_score`
  - `alert` → `above_baseline`
  - `calibration_hash` stays unchanged
- Replace tag vocabulary with the fixed topic-tag weight table below.
- Keep freshness-field access on `last_updated`; only the surrounding workload terminology changes.
- Replace all `device_*` and `severity_*` response keys in `/service_pressure` output.
- Replace remaining device/severity names in feed-oriented compute outputs,
  including `summary.device_count` → `summary.content_count` and
  `status_severity` → `status_weight` in the per-item breakdown payload.
- Keep the scoring mechanics unchanged.

### 3. `source/docker/edge_server/source/local_request_state.py`

Required changes:

- Rename the `LocalRequestEvent` fields from device/node/severity terminology.
- Rename storage helpers and accessors such as `recent_for_device()` and `_by_device`.
- Rename the constructor/window parameter from `per_device_window` to
  `per_content_window` so the internal API matches the renamed local-state
  vocabulary.
- Keep retention logic, truncation behavior, and return shapes intact except for renamed keys.

### 4. `source/docker/edge_server/source/edge_request_lifecycle.py`

Required changes:

- Rename staged local request event keys.
- Rename `stage_local_request_event()` parameters to content/user/relevance naming.
- Update the post-request builder call to pass renamed fields.

### 5. `source/docker/edge_server/source/edge_server_process_state.py`

Required changes:

- Rename `build_local_request_event()` parameters.
- Rename `LocalRequestState` construction arguments if the config names change.
- Keep drain behavior and telemetry sender behavior unchanged.

### 6. `source/docker/edge_server/source/edge_server_config.py`

Required changes:

- Rename workload-facing config properties to feed/content terminology:
  - `dashboard_candidate_limit` → `feed_candidate_limit`
  - `dashboard_integrity_work_factor` → `feed_integrity_work_factor`
  - `local_request_per_device_window` → `local_request_per_content_window`
- Rename the corresponding active env vars directly in the same phase:
  - `DASHBOARD_CANDIDATE_LIMIT` → `FEED_CANDIDATE_LIMIT`
  - `DASHBOARD_INTEGRITY_WORK_FACTOR` → `FEED_INTEGRITY_WORK_FACTOR`
  - `LOCAL_REQUEST_PER_DEVICE_WINDOW` → `LOCAL_REQUEST_PER_CONTENT_WINDOW`
- Rewrite the active env/property names directly so the configuration surface matches the renamed workload terminology.

### 7. `source/scripts/testing/traffic_generator.py`

Required changes:

- Load `content_items.json` and `user_profiles.json`.
- Rename internal targeting keys from device/node to content/user.
- Replace request-type branching with the canonical Phase B set:
  `content_lookup`, `feed_ranking`, `service_pressure`, `content_update`, and
  `content_aggregate`.
- Update URL builders to the new endpoints.
- Update POST bodies to these exact shapes:
  - `content_update`: `{"content_id": "...", "engagement": <integer 0-100>, "lan": "lanX", "update_padding": "..."}`
  - `content_aggregate`: `{"lan": "lanX", "engagement_threshold": <integer 30-70>}`
- Preserve the current traffic-generator numeric semantics exactly:
  - `content_update.engagement` uses `random.randint(0, 100)`
  - `content_aggregate.engagement_threshold` uses `random.randint(30, 70)`
- Rename CSV column headers if they still expose device/node naming.
- Rename CSV headers explicitly from `device_id` → `content_id` and `node_id`
  → `user_id`.

### 8. `source/scripts/testing/trace_request.sh`

Required changes:

- Replace endpoint examples with `/content/...` and `/feed/...`.
- Replace example IDs with `lanX::content::...` and `lanX::user::...`.
- Replace user-facing comments that still describe the request as a device lookup.

## Response-Contract Changes

The `/service_pressure` output should be renamed in the same phase so the
public response contract does not lag behind the route rename.

### `/content/<id>` response contract

| Old key | New key |
|---|---|
| `device_id` | `content_id` |
| `severity` | `relevance` |
| `alert` | `above_baseline` |

Implementation rules:

- The not-found payload must return `content_id`, not `device_id`.
- The computed lookup object returned by `score_content_relevance()` must be
  attached under `relevance`, not `severity`.
- Preserve the old structural pattern exactly under the renamed keys: the
  response body is still the fetched content document plus a top-level
  `above_baseline` boolean, a nested computed object under `relevance`, and the
  existing `trend` object. Do not flatten the computed relevance fields into
  the top-level document beyond the single duplicated `above_baseline` flag.

### `/feed/<user_id>` response contract

| Old key | New key |
|---|---|
| `node_id` | `user_id` |
| `devices` | `content_items` |
| `summary.device_count` | `summary.content_count` |
| `status_severity` | `status_weight` |

Implementation rules:

- No feed response payload should expose `node_id` or `devices` after Phase B.
- The summary object returned by `compute_feed_summary()` must use
  `content_count` as its collection-size key.
- The per-item feed breakdown field `status_weight` remains derived from the
  stored 3-state `payload.status` signal. It does not represent the computed
  4-state `relevance` classification.

### `/service_pressure` response contract

| Old key | New key |
|---|---|
| `unique_device_count` | `unique_content_count` |
| `top_device_share` | `top_content_share` |
| `top_devices` | `top_content` |
| `device_id` | `content_id` |
| `last_severity` | `last_relevance` |
| `top_tags[].unique_device_count` | `top_tags[].unique_content_count` |

## Canonical Topic-Tag Weights

`score_feed_relevance()` should use the canonical topic-tag weights below.
The tag vocabulary should match the Phase A seeding vocabulary exactly.

| Tag | Weight |
|---|---|
| `premium` | `2.0` |
| `trending` | `1.8` |
| `news` | `1.3` |
| `sports` | `1.2` |
| `technology` | `1.1` |
| `finance` | `1.1` |
| `health` | `1.0` |
| `education` | `1.0` |
| `science` | `1.0` |
| `entertainment` | `0.9` |
| `featured` | `0.8` |
| `archived` | `0.5` |

Implementation rule:

- No new topic tags should be invented during Phase B.
- If an unknown tag still appears at runtime, keep the current generic fallback weight of `0.5` rather than adding ad-hoc special handling.

## Validation Gate

Phase B is complete only when all of the following hold:

- `traffic_generator.py --dry-run` emits only the new content/feed routes when
  run against a Phase B validation config that already uses the renamed
  request-kind keys, or after Phase C updates the canonical phase files.
- `trace_request.sh` help text and examples use the new route and ID patterns.
- The edge server serves the 5 workload endpoints with the new names.
- `/content/<id>` no longer exposes `device_id`, `severity`, or other stale
  device/node keys in success or error payloads.
- `/feed/<user_id>` no longer exposes `node_id`, `devices`, or
  `summary.device_count`.
- `/service_pressure` no longer exposes stale device-specific response keys,
  including `top_tags[].unique_device_count`.
- The synthetic write/aggregate routes accept only the canonical Phase B body
  fields (`content_id`, `engagement`, `engagement_threshold`, `lan`, and
  optional `update_padding`).

## Out of Scope for Phase B

- Seeder rewrite details
- Phase JSON request-type renames
- Testing/operator docs beyond `trace_request.sh`
- Final end-to-end validation