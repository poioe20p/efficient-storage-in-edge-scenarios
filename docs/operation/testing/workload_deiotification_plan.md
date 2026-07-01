# Workload De-IoT-ification Plan

> **Status**: Plan — approved, not yet implemented · **Date**: 2026-06-30
> **Purpose**: Rename all IoT-specific workload concepts to a domain-agnostic
> "Multi-Region Content Discovery Platform" framing. Zero IoT language
> anywhere. All mechanical properties preserved.

---

## Scenario

**Multi-Region Content Discovery Platform** — an edge-deployed content
syndication and discovery service. Content items of diverse types are
ingested regionally and discovered globally through tag-based personalized
feeds. Read-heavy with periodic writes. Two operating regimes:
data-locality (content lookups dominate) and compute-analytics (feed
ranking dominates).

---

## Locked Requirements

| # | Requirement |
|---|---|
| R1 | Zero IoT language — no sensor, device, firmware, industrial, thermal, mechanical, fleet, etc. |
| R2 | Collection 1: `content_items` (replaces `sensor_reports`) |
| R3 | Collection 2: `user_profiles` (replaces `device_registry`) |
| R4 | 9 content types: `article`, `video`, `podcast`, `image_gallery`, `event`, `tool`, `review`, `discussion`, `curated_list` |
| R5 | Tags: `news`, `entertainment`, `sports`, `technology`, `finance`, `health`, `education`, `science`, `premium`, `trending`, `featured`, `archived` |
| R6 | 3 user profile tiers: `focused` (1-2 tags), `broad` (3-4 tags), `global` (5-6 tags) |
| R7 | ID patterns: `lan1::content::001`, `lan1::user::001` |
| R8 | Endpoints renamed, mechanics preserved (see Endpoint Mapping below) |
| R9 | Request types renamed (see Request Type Mapping below) |
| R10 | Compute functions renamed, formulas preserved (see Function Mapping below) |
| R11 | Field names in documents renamed (see Field Mapping below) |
| R12 | Seeder scripts renamed: `seed_content_items.py`, `seed_user_profiles.py` |
| R13 | Snapshot files renamed: `content_items.json`, `user_profiles.json` |
| R14 | Controller: zero changes (proven agnostic) |
| R15 | `edge_platform` DB name stays (already generic) |
| R16 | Phase names stay (already abstract) |
| R17 | All mechanical properties preserved: second MongoDB read for override, per-type exponential weighting, per-document SHA-256 jitter, per-user parameterization |

---

## Endpoint Mapping

| Old | New | Method | Role |
|---|---|---|---|
| `/device/<id>/latest?node_id=` | `/content/<id>?requester=<user_id>` | GET | Content lookup + enrichment (data-locality driver) |
| `/dashboard/<node_id>?limit=N` | `/feed/<user_id>?limit=N` | GET | Ranked personalized feed (compute driver) |
| `/service_pressure?window_min=&limit=` | `/service_pressure?window_min=&limit=` | GET | Unchanged (service introspection) |
| `/device_update` | `/content` | POST | Upsert content item (oplog stress) |
| `/device_aggregate` | `/content/aggregate` | POST | Aggregation pipeline (MongoDB CPU stress) |

---

## Request Type Mapping

Used in `phases.json` mix keys and `traffic_generator.py`:

| Old | New |
|---|---|
| `device_status` | `content_lookup` |
| `dashboard` | `feed_ranking` |
| `service_pressure` | `service_pressure` (unchanged) |
| `device_update` | `content_update` |
| `device_aggregate` | `content_aggregate` |

---

## Function Mapping (`compute.py`)

| Old | New | Change |
|---|---|---|
| `score_device_severity()` | `score_content_relevance()` | Rename + rename internal vars |
| `compute_trend()` | `compute_trend()` | Unchanged |
| `compute_service_pressure()` | `compute_service_pressure()` | Unchanged |
| `score_dashboard_urgency()` | `score_feed_relevance()` | Rename + rename internal vars |
| `compute_dashboard_summary()` | `compute_feed_summary()` | Rename |
| `verify_fleet_integrity()` | `verify_feed_integrity()` | Rename |

Internal constant renames:
- `SEVERITY_LEVELS` → `RELEVANCE_LEVELS` (critical/warning/elevated/normal → hot/trending/steady/quiet)
- `TAG_PRIORITY` → stays (generic enough)
- `TREND_WINDOW_SIZE` → stays
- `STALENESS_HALF_LIFE_S` → stays

---

## Field Mapping (Document Schema)

### `content_items` documents (was `sensor_reports`)

| Old field | New field | Notes |
|---|---|---|
| `_id` (e.g. `lan1::device::001`) | `_id` (e.g. `lan1::content::001`) | ID pattern change |
| `region_origin` | `region_origin` | Unchanged |
| `device_type` | `content_type` | |
| `tags` | `tags` | Values change (IoT tags → topic tags) |
| `unit` | `unit` | Unchanged (generic) |
| `payload.value` | `engagement` | The measured signal |
| `payload.status` | `payload.status` | Values: critical/warning/normal → hot/trending/steady/quiet |
| `payload.*` (type-specific) | `payload.*` | Type-specific fields renamed (below) |
| `metadata.firmware` | `metadata.source` | Content origin label |
| `metadata.location` / `machine_id` / etc. | `metadata.origin_label` | Generic origin descriptor |
| `metadata.alert_threshold` | `metadata.relevance_baseline` | |
| `metadata.*` (type-specific) | `metadata.*` | Type-specific fields renamed (below) |
| `last_updated` | `last_updated` | Unchanged |

### Content Type-Specific Fields

Each content type has structurally different payload and metadata fields.

#### `article`
- `payload.word_count` (int)
- `payload.reading_time_s` (int)
- `payload.author` (str)
- `payload.body_preview` (str)
- `metadata.source` (str): e.g. "editorial", "syndicated", "contributor"
- `metadata.origin_label` (str): e.g. "desk_3_section_B"

#### `video`
- `payload.duration_s` (int)
- `payload.resolution` (str): e.g. "1080p", "4K"
- `payload.codec` (str): e.g. "h264", "av1"
- `payload.thumbnail_url` (str)
- `metadata.source` (str): e.g. "studio_v1.0", "mobile_v2.1"
- `metadata.origin_label` (str): e.g. "studio_3"

#### `podcast`
- `payload.audio_length_s` (int)
- `payload.episode_num` (int)
- `payload.host` (str)
- `payload.transcript_url` (str)
- `metadata.source` (str): e.g. "recording_v1", "live_v2"
- `metadata.origin_label` (str): e.g. "booth_4"

#### `image_gallery`
- `payload.image_count` (int)
- `payload.max_dimensions` (str): e.g. "1920x1080"
- `payload.license` (str): e.g. "cc-by", "rights-managed"
- `payload.photographer` (str)
- `metadata.source` (str): e.g. "upload_v3", "agency_feed"
- `metadata.origin_label` (str): e.g. "gallery_section_A"

#### `event`
- `payload.start_time` (datetime)
- `payload.end_time` (datetime)
- `payload.venue` (str)
- `payload.capacity` (int)
- `payload.price_tier` (str): e.g. "free", "premium"
- `metadata.source` (str): e.g. "organizer_v1", "partner_api"
- `metadata.origin_label` (str): e.g. "venue_12"

#### `tool`
- `payload.tool_type` (str): e.g. "calculator", "visualizer", "converter"
- `payload.embed_url` (str)
- `payload.params_schema` (str): JSON schema string
- `payload.platform` (str): e.g. "web", "mobile"
- `metadata.source` (str): e.g. "sdk_v2.0", "custom_build"
- `metadata.origin_label` (str): e.g. "widget_gallery"

#### `review`
- `payload.rating` (float): 0.0–5.0
- `payload.reviewed_item` (str)
- `payload.pros` (list[str])
- `payload.cons` (list[str])
- `payload.verified` (bool)
- `metadata.source` (str): e.g. "user_submitted", "curator_pick"
- `metadata.origin_label` (str): e.g. "review_pool_1"

#### `discussion`
- `payload.reply_count` (int)
- `payload.participant_count` (int)
- `payload.is_pinned` (bool)
- `payload.is_locked` (bool)
- `metadata.source` (str): e.g. "forum_v3", "live_chat"
- `metadata.origin_label` (str): e.g. "thread_pool_A"

#### `curated_list`
- `payload.item_count` (int)
- `payload.curator` (str)
- `payload.theme` (str)
- `payload.update_frequency` (str): e.g. "daily", "weekly"
- `metadata.source` (str): e.g. "editorial_v1", "automated_v2"
- `metadata.origin_label` (str): e.g. "list_section_5"

### `user_profiles` documents (was `device_registry`)

| Old field | New field | Notes |
|---|---|---|
| `_id` (e.g. `lan1::node::001`) | `_id` (e.g. `lan1::user::001`) | ID pattern change |
| `home_region` | `home_region` | Unchanged |
| `profile_kind` | `profile_kind` | Values: focused_local→focused, regional_operator→broad, global_operator→global |
| `subscribed_tags` | `subscribed_tags` | Values change (IoT tags → topic tags) |
| `watched_devices` | `followed_content` | List of content IDs |
| `alert_config.email` | `profile_config.email` | |
| `alert_config.threshold_override` | `profile_config.relevance_override` | Per-content-type overrides |

### `local_request_activity` events (was `LocalRequestEvent`)

| Old field | New field | Notes |
|---|---|---|
| `device_id` | `content_id` | Nullable (null for feed_ranking events) |
| `node_id` | `user_id` | |
| `severity` | `relevance` | Values: critical→hot, warning→trending, elevated→steady, normal→quiet |
| `status` | `status` | Values: critical→hot, warning→trending, normal→steady |
| All other fields | Unchanged | `request_kind` values change per Request Type Mapping |

---

## Scoring Translation

### `score_content_relevance()` (was `score_device_severity()`)

| Old concept | New concept | Detail |
|---|---|---|
| `value` | `engagement` | Measured traction signal |
| `threshold` | `relevance_baseline` | Expected engagement for this content type |
| `raw_ratio = value / threshold` | `raw_ratio = engagement / baseline` | How much is this outperforming? |
| `calibration_hash` (device_id) | `content_signature` (content_id) | Per-item deterministic jitter |
| `calibrated_ratio` | Same | SHA-256 jitter applied |
| Exponential by `device_type` | Exponential by `content_type` | Different types, different sensitivity |
| `anomaly_score` | `relevance_score` | |
| Classification: critical/warning/elevated/normal | Classification: hot/trending/steady/quiet | Cutoffs at 1.0/0.85/0.70 |
| `alert` boolean | `is_trending` boolean | True when ratio ≥ 1.0 |

### `score_feed_relevance()` (was `score_dashboard_urgency()`)

| Old factor | New factor | Weight |
|---|---|---|
| Threshold proximity (value/alert_threshold)³ | Baseline ratio (engagement/baseline)³ | 40% |
| Tag priority (IoT tags) | Topic relevance (topic tags) | 25% |
| Status severity (critical/warning/normal) | Payload status (hot/trending/steady) | 20% |
| Staleness decay from `last_updated` | Same | 15% |

### `compute_feed_summary()` (was `compute_dashboard_summary()`)

Returns aggregate statistics (mean/std/max relevance scores, status distribution) — mechanics unchanged.

### `verify_feed_integrity()` (was `verify_fleet_integrity()`)

Iterated SHA-256 over each item's payload — CPU-bound work preserved exactly.

---

## Tag Mapping

| Old IoT tag | New topic tag |
|---|---|
| `industrial` | `news` |
| `high-priority` | `premium` |
| `thermal` | `technology` |
| `mechanical` | `sports` |
| `logistics` | `finance` |
| `environmental` | `science` |
| `predictive-maintenance` | `featured` |
| `fleet` | `entertainment` |
| `mobile` | `health` |
| `outdoor` | `education` |
| `compliance` | `archived` |
| *(no equivalent)* | `trending` |

Tag priority weights (used in `score_feed_relevance`):

| Tag | Weight |
|---|---|
| `premium` | 2.0 |
| `trending` | 1.8 |
| `news` | 1.3 |
| `sports` | 1.2 |
| `technology` | 1.1 |
| `finance` | 1.1 |
| `health` | 1.0 |
| `education` | 1.0 |
| `science` | 1.0 |
| `entertainment` | 0.9 |
| `featured` | 0.8 |
| `archived` | 0.5 |

---

## File Map — Every File Touched

### Edge Server (`source/docker/edge_server/source/`)

| File | Action | Scope |
|---|---|---|
| `monitoring_workload_routes.py` | Edit | Rename endpoints, collection names, field refs, request_kind strings. Replace all `sensor_reports`→`content_items`, `device_registry`→`user_profiles` |
| `compute.py` | Edit | Rename all 4 functions, rename constants, rename severity→relevance labels, replace tag vocabulary, replace device_type→content_type |
| `local_request_state.py` | Edit | Rename dataclass fields: `device_id`→`content_id`, `node_id`→`user_id`, `severity`→`relevance` |
| `edge_server_config.py` | No change | Config keys already generic |
| `platform_cache.py` | No change | Collection names passed as strings, not hardcoded |
| `vip_data_mongo_runtime.py` | No change | Not workload-specific |
| `edge_request_lifecycle.py` | Verify | May reference `request_kind` strings — check and update if so |
| `app.py` | No change | Routes registered by name, unchanged |
| `control_plane_routes.py` | No change | Control plane, not workload-specific |

### Testing Scripts (`source/scripts/testing/`)

| File | Action | Scope |
|---|---|---|
| `sensor_reports.py` | **Rename** → `seed_content_items.py` | Full rewrite: 9 content types, new fields, new tags, new ID patterns |
| `device_registry.py` | **Rename** → `seed_user_profiles.py` | Full rewrite: user profiles, topic tags, followed_content, relevance_override |
| `traffic_generator.py` | Edit | Rename request types (5), endpoint URL builders, field refs, snapshot file names, CSV column headers |
| `export_workload_snapshot.py` | Edit | Rename collection names, output file names (`sensor_devices.json`→`content_items.json`, `device_registry.json`→`user_profiles.json`) |
| `create_indexes.py` | Edit | Rename collection names and index fields |
| `_fix_phases.py` | Edit | Rename request type strings in mix dicts |
| `tier1_stats.py` | Edit | Update collection name reference in docstring |
| `phases.json` | Edit | Rename request type keys in all phase `mix` dicts |
| `phases_override/phases_tier1_smoke.json` | Edit | Same as phases.json |
| `phases_override/phases_rq1_verify.json` | Edit | Same as phases.json |
| `phases_override/phases_mini.json` | Edit | Same as phases.json |
| `run_experiment.sh` | Verify | Check for `DEVICES`/`NODES` var names — may need `CONTENT_ITEMS`/`USERS` or keep for backward compat |
| `capture_reverse_hotspot_probe.sh` | No change | Not workload-specific |
| `trace_request.sh` | No change | Not workload-specific |

### Analysis Scripts (`source/scripts/testing/analysis/`)

| File | Action | Scope |
|---|---|---|
| `cli_endpoint_breakdown.py` | Edit | Rename endpoint labels and colors: `device_status`→`content_lookup`, `dashboard`→`feed_ranking` |
| `cli_overview.py` | Verify | Check for endpoint name references in docstring only |
| All other analysis CLIs | Verify | Most reference CSVs by column name, not endpoint names. Check for any hardcoded request type strings. |

### Build System

| File | Action | Scope |
|---|---|---|
| `source/scripts/Makefile` | Edit | Update target names (`seed_sensor_reports`→`seed_content_items`, `seed_device_registry`→`seed_user_profiles`), update `DEVICES`→`CONTENT_ITEMS` variable, update script name references |

### Documentation

| File | Action | Scope |
|---|---|---|
| `docs/operation/testing/testing_workloads.md` | **Rewrite** | Complete rewrite with content platform framing, no IoT language |
| `docs/operation/testing/traffic_generator.md` | Edit | Update endpoint/request type references, scenario description |
| `docs/operation/testing/testing_overview.md` | Edit | Update data flow diagram labels, script name references |

### NOT Changed (Verified Agnostic)

| Layer | Why |
|---|---|
| `source/sdn_controller/` (all) | Zero hardcoded collection/field names. Works with generic `(owner_lan, collection)` tuples. |
| `source/docker/local_state_server/aggregator.py` | Collection names passed through as strings. |
| `source/docker/edge_selective_storage/` | Works with generic collection strings. |
| `source/docker/OVS/`, `source/docker/ubuntu-nat-router/` | Network infrastructure. |
| `source/scripts/network/` | Network setup. |
| `source/scripts/build_images.sh`, `build_network_setup.sh`, `cleanup.sh` | Infrastructure scripts. |
| `tese/` (all) | Thesis documents reference abstract descriptions. |

---

## Implementation Order

### Phase 1 — Seeder Scripts (no dependencies)

1. Create `seed_content_items.py` from scratch (replaces `sensor_reports.py`)
   - 9 content type specs with `engagement` and type-specific payload/metadata fields
   - Topic tag pool with per-type tag assignment
   - ID pattern: `{region}::content::{index:03d}`
   - Upsert via `UpdateOne` with `upsert=True`
2. Create `seed_user_profiles.py` from scratch (replaces `device_registry.py`)
   - 3 profile families: focused/broad/global with tag ranges 1-2/3-4/5-6
   - `followed_content` pointing to seeded content IDs (local/mixed/foreign mix)
   - `profile_config.relevance_override` per content type
   - ID pattern: `{region}::user::{index:03d}`

### Phase 2 — Edge Server Routes (depends on nothing)

3. Edit `compute.py` — rename functions, constants, severity→relevance labels, tag vocabulary
4. Edit `monitoring_workload_routes.py` — rename endpoints, collection name strings, field references, request_kind strings
5. Edit `local_request_state.py` — rename dataclass fields

### Phase 3 — Traffic Generator & Config (depends on Phase 1, 2 for consistency)

6. Edit `traffic_generator.py` — request types, URLs, field refs, snapshot file names
7. Edit `export_workload_snapshot.py` — collection names, output file names
8. Edit `create_indexes.py` — collection names, index fields
9. Edit `phases.json` — request type keys in all mix dicts
10. Edit `phases_override/*.json` — same
11. Edit `_fix_phases.py` — request type strings

### Phase 4 — Build System & Docs (depends on all above)

12. Edit `Makefile` — target names, variable names
13. Edit `cli_endpoint_breakdown.py` — endpoint labels
14. Verify all other analysis scripts for hardcoded strings
15. Rewrite `testing_workloads.md`
16. Update `traffic_generator.md`
17. Update `testing_overview.md`

### Phase 5 — Cleanup

18. Delete old `sensor_reports.py` and `device_registry.py` (after confirming new seeders work)
19. Run a full experiment to validate end-to-end

---

## Validation Checklist

After all changes, the following must hold:

- [ ] `make setup_test_data` completes without errors using new seeders
- [ ] `export_workload_snapshot.py` produces `content_items.json` + `user_profiles.json`
- [ ] `traffic_generator.py --dry-run` prints correct new URLs
- [ ] All 5 endpoints return 200 on a running edge server
- [ ] A full experiment run (`make run_experiment`) completes with valid `client_requests.csv`
- [ ] `cli_endpoint_breakdown.py` produces correct per-endpoint charts
- [ ] `cli_simple_run.py` produces valid latency/failure plots
- [ ] Controller logs show no errors related to collection/field name changes
- [ ] `grep -ri "sensor\|device_type\|firmware\|industrial\|thermal\|mechanical\|fleet\|IoT" source/docker/edge_server/ source/scripts/testing/` returns zero matches (excluding this plan doc and old files pending delete)
- [ ] `testing_workloads.md` contains zero IoT references

---

## Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Missed a hardcoded string in analysis scripts | Phase 4 step 14: grep all analysis scripts for old strings |
| Makefile variable rename breaks existing experiment runner scripts | Keep backward-compat aliases (e.g. `DEVICES` as alias for `CONTENT_ITEMS`) or update `run_experiment.sh` |
| Old run folders have CSVs with old column names | Analysis CLIs should handle both old and new column names, or we accept that old runs need re-analysis before the rename. The rename is a clean break. |
| Phase override JSONs drift from canonical phases.json | Apply same edits to all phase files in one batch |
| `edge_request_lifecycle.py` has hardcoded request_kind strings | Verify in Phase 2 |
