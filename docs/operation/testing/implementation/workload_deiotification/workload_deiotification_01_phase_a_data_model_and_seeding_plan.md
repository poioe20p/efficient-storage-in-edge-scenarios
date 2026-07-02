# Workload De-IoT-ification — Phase A Data Model and Seeding Plan

> **Status**: Planned · **Date**: 2026-07-02
> **Parent**: [`../../workload_deiotification_plan.md`](../../workload_deiotification_plan.md)
> **Scope**: Finalize the canonical content schema and migrate all seeding,
> snapshot-export, indexing, and seeding-entrypoint surfaces to the new naming.

## Objective

Phase A establishes the new workload vocabulary at the data-model layer and
updates the seeding stack as one implementation slice. The phase gate is a
targeted seeding/snapshot check, not a claim that the full renamed workload is
already executable end to end before later slices land.

## Canonical Schema Decisions

### Collections

| Old | New |
|---|---|
| `sensor_reports` | `content_items` |
| `device_registry` | `user_profiles` |

### Shared content-item fields

| Field | Decision |
|---|---|
| `_id` | `lanX::content::NNN` |
| `region_origin` | Keep unchanged; it is already generic and is the canonical owner/origin LAN field for locality-sensitive routing, placement, and snapshot targeting |
| `content_type` | Replaces `device_type` |
| `payload.engagement` | Replaces `payload.value`; stays under `payload` to minimize route/compute churn |
| `payload.status` | Stored 3-state content signal: `quiet`, `trending`, `hot` |
| `metadata.relevance_baseline` | Replaces `metadata.alert_threshold` |
| `metadata.source` | Replaces `metadata.firmware` or other origin labels |
| `tags` | Topic categories, not infrastructure or industrial tags |
| `unit` | Keep as an explicit stored field; it names the engagement unit for the content type |
| `last_updated` | Keep unchanged; it is already generic and remains the canonical freshness field for feed candidate ordering and recency scoring |

These are canonical, not illustrative. `region_origin` and `last_updated`
must be treated as required stored fields because later phases depend on them
for locality-sensitive targeting, feed candidate ordering, and staleness-based
ranking.

Generic non-IoT fields that already fit the content workload should be carried
forward unchanged instead of being renamed only for the sake of renaming. In
Phase A, that explicitly applies to `region_origin`, `unit`, and
`last_updated`.

### Shared user-profile fields

| Field | Decision |
|---|---|
| `_id` | `lanX::user::NNN` |
| `home_region` | Keep as an explicit stored field; it remains the canonical owner/home-LAN marker for request targeting and profile seeding |
| `profile_kind` | `focused`, `broad`, `global` |
| `subscribed_tags` | Keep as a canonical stored field; it remains the primary fan-out input for feed-ranking requests |
| `followed_content` | Replaces `watched_devices` |
| `profile_config.email` | Replaces `alert_config.email`; canonical contact field retained in the renamed profile schema |
| `profile_config.relevance_override` | Replaces `alert_config.threshold_override` |

These are canonical, not illustrative. `home_region` and `subscribed_tags`
must be treated as required stored fields because later phases depend on them
for locality-sensitive targeting and feed candidate expansion.

### Canonical seeding interface names

Phase A should rewrite the active seeding interface to these exact names.

| Surface | Old | New |
|---|---|---|
| Makefile variable | `DEVICES` | `CONTENT_ITEMS` |
| Makefile variable | `NODES` | `USERS` |
| shell variable in `run_experiment.sh` | `SEED_DEVICES` | `SEED_CONTENT_ITEMS` |
| shell variable in `run_experiment.sh` | `SEED_NODES` | `SEED_USERS` |
| CLI flag in `run_experiment.sh` | `--seed-devices` | `--seed-content-items` |
| CLI flag in `run_experiment.sh` | `--seed-nodes` | `--seed-users` |

These names are canonical for the active workload surface. Phase A should not
leave these as "preferred" or "primary" alternatives.

### Content types

The seeded `content_items` collection should include these 9 types:

- `article`
- `video`
- `podcast`
- `image_gallery`
- `event`
- `tool`
- `review`
- `discussion`
- `curated_list`

Each type keeps the shared scoring fields above and adds type-specific payload
and metadata fields. The exact field set is fixed below and should be copied
into the seeder directly rather than invented during implementation.

### Shared scoring-field generation rules

These rules apply to every seeded `content_items` document, regardless of type.

#### Stored status distribution

Use this exact distribution when assigning `payload.status`:

| Stored status | Probability |
|---|---:|
| `quiet` | 0.55 |
| `trending` | 0.30 |
| `hot` | 0.15 |

#### Engagement generation from baseline

For every item, first sample `metadata.relevance_baseline` from the type-specific
 range in the table below. Then derive `payload.engagement` by multiplying that
 baseline by a factor chosen from the bucket for the selected stored status.

| Stored status | Engagement multiplier range |
|---|---|
| `quiet` | 0.35 – 0.84 × baseline |
| `trending` | 0.85 – 0.99 × baseline |
| `hot` | 1.00 – 1.35 × baseline |

This keeps the stored 3-state content signal distinct from the later 4-state
computed relevance classification.

#### Freshness generation from status

Use this exact `last_updated` policy:

| Stored status | `last_updated` age window |
|---|---|
| `hot` | now − 0 to 15 minutes |
| `trending` | now − 15 minutes to 6 hours |
| `quiet` (non-archived) | now − 6 hours to 7 days |
| `quiet` + `archived` tag | now − 30 to 180 days |

#### Tagging rules

- Tag assignment happens in two ordered steps:
	1. Sample 1 to 3 base tags without replacement from the type's preferred tag pool after excluding any status-conditioned tags (`trending`, `archived`).
	2. Optionally append status-conditioned tags according to the rules below if they are not already present.
- `trending` is a status-conditioned tag, not a base-pool requirement. It may be appended only when `payload.status` is `trending` or `hot`.
- `premium` is a base-pool tag. It should appear on exactly 15% of seeded items overall and should not be universal within any type.
- `archived` is a status-conditioned tag, not a base-pool requirement. It should be appended on exactly 10% of `quiet` items and on no non-`quiet` items, even for types whose preferred pool does not list `archived`.
- The final tag list must still contain no more than 3 tags total. If appending a status-conditioned tag would exceed the cap, replace one sampled base tag instead of exceeding the limit.
- In the type matrix below, the preferred tag pool must be interpreted as the base-pool source for step 1 only. Status-conditioned tags are never sampled during step 1 and are added only through step 2.
- No legacy infrastructure or IoT tags should survive Phase A seeding.

### Type-specific field matrix

Every `content_items` document keeps the shared fields above plus the
type-specific payload and metadata fields from exactly one row below.

| `content_type` | Unit | Baseline range | Required payload fields | Payload generation rules | Required metadata fields | Metadata generation rules | Preferred tag pool |
|---|---|---|---|---|---|---|---|
| `article` | `views/h` | 120 – 500 | `headline`, `author`, `word_count`, `reading_time_s`, `body_preview` | `headline="{region} article {index}"`; `author` from `author_1..author_20`; `word_count` 400–2200; `reading_time_s=round(word_count / U(3.2,4.2))`; `body_preview` as a deterministic summary string 90–140 chars long | `section`, `language`, `publisher_tier` | `section` from `local, world, business, science, culture`; `language` from `en, pt`; `publisher_tier` from `local, partner, flagship`; `source` from `editorial, syndicated, contributor` | `news`, `technology`, `science`, `finance`, `education` |
| `video` | `streams/h` | 180 – 700 | `title`, `duration_s`, `resolution`, `creator`, `captioned` | `title="{region} video {index}"`; `duration_s` 60–3600; `resolution` from `720p, 1080p, 1440p, 4k`; `creator` from `creator_1..creator_30`; `captioned=true` with probability 0.50 | `channel`, `language`, `distribution_tier` | `channel` from `channel_1..channel_20`; `language` from `en, pt`; `distribution_tier` from `local, partner, featured`; `source` from `studio, mobile, partner_feed` | `entertainment`, `featured`, `technology`, `sports` |
| `podcast` | `listens/h` | 80 – 260 | `title`, `duration_s`, `host`, `episode_number`, `transcript_available` | `title="{region} podcast {index}"`; `duration_s` 300–5400; `host` from `host_1..host_15`; `episode_number` 1–300; `transcript_available=true` with probability 0.50 | `series`, `language`, `release_cadence` | `series` from `series_1..series_20`; `language` from `en, pt`; `release_cadence` from `daily, weekly, biweekly`; `source` from `recording, live, partner_audio` | `education`, `news`, `technology`, `health`, `finance` |
| `image_gallery` | `views/h` | 100 – 420 | `title`, `image_count`, `cover_caption`, `dominant_format` | `title="{region} gallery {index}"`; `image_count` 4–24; `cover_caption` template string; `dominant_format` from `photo, illustration, mixed` | `collection`, `license`, `photographer_credit` | `collection` from `collection_1..collection_15`; `license` from `standard, cc-by, editorial`; `photographer_credit` from `photographer_1..photographer_25`; `source` from `upload, agency_feed, editorial` | `featured`, `entertainment`, `news`, `sports`, `science` |
| `event` | `rsvps/h` | 15 – 90 | `title`, `start_time`, `end_time`, `venue`, `capacity` | `title="{region} event {index}"`; `start_time` 1–30 days in the future; `end_time` = `start_time` + 1–6 hours; `venue` from `venue_1..venue_30`; `capacity` 30–1500 | `organizer_type`, `access_tier`, `venue_region` | `organizer_type` from `community, commercial, institutional`; `access_tier` from `free, ticketed, invite`; `venue_region` from `region_zone_1..region_zone_8`; `source` from `organizer, partner_api` | `featured`, `entertainment`, `education`, `sports`, `premium` |
| `tool` | `sessions/h` | 40 – 180 | `title`, `tool_type`, `platform`, `interaction_mode`, `estimated_runtime_ms` | `title="{region} tool {index}"`; `tool_type` from `calculator, visualizer, converter, planner`; `platform` from `web, mobile, desktop`; `interaction_mode` from `form, canvas, chat`; `estimated_runtime_ms` 50–1500 | `provider`, `supported_audiences`, `stability_tier` | `provider` from `provider_1..provider_15`; `supported_audiences` from `consumer, student, analyst, operator`; `stability_tier` from `beta, stable, featured`; `source` from `sdk, custom_build, partner_tool` | `technology`, `finance`, `education`, `featured`, `premium` |
| `review` | `interactions/h` | 30 – 140 | `title`, `rating`, `reviewed_item`, `pros`, `cons` | `title="{region} review {index}"`; `rating` 2.0–5.0 with 0.1 precision; `reviewed_item` from `item_1..item_200`; `pros` list of 1–3 short strings; `cons` list of 0–2 short strings | `reviewer_kind`, `reviewed_category`, `spoiler_level` | `reviewer_kind` from `staff, verified_user, guest`; `reviewed_category` from `video, tool, event, article, podcast`; `spoiler_level` from `none, light, heavy`; `source` from `user_submitted, curator_pick` | `premium`, `technology`, `entertainment`, `health`, `featured` |
| `discussion` | `replies/h` | 60 – 240 | `title`, `reply_count`, `participant_count`, `is_pinned`, `is_locked` | `title="{region} discussion {index}"`; `reply_count` 0–400; `participant_count` 2–120; `is_pinned` true with 10% probability; `is_locked` true with 5% probability | `forum`, `moderation_state`, `language` | `forum` from `general, support, strategy, fan`; `moderation_state` from `open, reviewed, restricted`; `language` from `en, pt`; `source` from `forum, live_chat, partner_board` | `news`, `entertainment`, `sports`, `technology` |
| `curated_list` | `saves/h` | 25 – 110 | `title`, `item_count`, `curator`, `theme`, `update_frequency` | `title="{region} list {index}"`; `item_count` 3–40; `curator` from `curator_1..curator_20`; `theme` from `starter_pack, weekly_digest, local_highlights, expert_picks`; `update_frequency` from `daily, weekly, monthly` | `curator_kind`, `list_scope`, `freshness_policy` | `curator_kind` from `editorial, community, algorithmic`; `list_scope` from `local, cross-region, global`; `freshness_policy` from `rolling, manual, seasonal`; `source` from `editorial, automated, community` | `featured`, `premium`, `education`, `entertainment` |

### Canonical topic-tag vocabulary

Allowed topic tags for Phase A seeding are exactly:

- `news`
- `technology`
- `science`
- `finance`
- `sports`
- `entertainment`
- `health`
- `education`
- `featured`
- `trending`
- `premium`
- `archived`

### Canonical user-profile generation rules

The renamed user-profile seeder should preserve the current behavioral shape
exactly, using the following canonical parameters.

| `profile_kind` | Weight | `subscribed_tags` count | `followed_content` count | follow-mode weights | mixed-mode foreign share |
|---|---:|---:|---:|---|---:|
| `focused` | 0.55 | 1–2 | 3–6 | `local=0.80`, `mixed=0.20`, `foreign=0.00` | 0.25 |
| `broad` | 0.30 | 3–4 | 4–8 | `local=0.45`, `mixed=0.45`, `foreign=0.10` | 0.50 |
| `global` | 0.15 | 4–6 | 6–12 | `local=0.20`, `mixed=0.55`, `foreign=0.25` | 0.70 |

Additional rules:

- `subscribed_tags` are sampled without replacement from the canonical topic-tag vocabulary.
- `followed_content` is built from content IDs in the home LAN and peer LAN according to the table above.
- Mixed-mode `followed_content` lists must contain at least one local item and at least one foreign item whenever the target count is greater than 1.
- `profile_config.email` should use the stable pattern `ops-{home_region}@example.com` so every seeded profile in the same home LAN keeps the current region-scoped contact convention.

### Canonical relevance-override ranges

Every seeded `user_profiles` document should include explicit
`profile_config.relevance_override` entries for all 9 content types using the
following ranges.

| `content_type` | Override range |
|---|---|
| `article` | 100 – 550 |
| `video` | 150 – 750 |
| `podcast` | 60 – 300 |
| `image_gallery` | 80 – 450 |
| `event` | 15 – 100 |
| `tool` | 30 – 220 |
| `review` | 20 – 170 |
| `discussion` | 40 – 260 |
| `curated_list` | 20 – 130 |

## Files and Required Changes

### 1. `source/scripts/testing/sensor_reports.py` → `seed_content_items.py`

Required changes:

- Rename the file and primary script identity.
- Replace the IoT device-type catalog with the 9 content types.
- Replace all IoT-specific payload and metadata fields.
- Keep `region_origin` unchanged and preserve it as an explicit stored field on every record.
- Generate `payload.engagement`, `payload.status`, `metadata.relevance_baseline`, `unit`, and `last_updated` for every record according to the canonical rules above.
- Implement the type-specific payload and metadata fields exactly as defined in the Phase A field matrix above.
- Change IDs from `lanX::device::NNN` to `lanX::content::NNN`.
- Change the target collection from `sensor_reports` to `content_items`.
- Replace IoT tag pools with the canonical topic-tag vocabulary and per-type preferred tag pools defined above.

### 2. `source/scripts/testing/device_registry.py` → `seed_user_profiles.py`

Required changes:

- Rename the file and primary script identity.
- Change IDs from `lanX::node::NNN` to `lanX::user::NNN`.
- Preserve `home_region` as an explicit stored field.
- Preserve `subscribed_tags` as an explicit stored field.
- Change `watched_devices` to `followed_content`.
- Rename `alert_config.email` to `profile_config.email` and preserve it as an explicit stored field.
- Implement the 3-tier profile distribution and local/mixed/foreign behavior exactly as defined in the canonical user-profile generation table above.
- Replace IoT threshold overrides with explicit `profile_config.relevance_override` entries for all 9 content types using the canonical ranges above.
- Change the target collection from `device_registry` to `user_profiles`.

### 3. `source/scripts/testing/export_workload_snapshot.py`

Required changes:

- Export `content_items` instead of `sensor_reports`.
- Export `user_profiles` instead of `device_registry`.
- Rename output files to `content_items.json` and `user_profiles.json`.
- For `content_items`, project `_id` plus `region_origin` so the traffic-generator snapshot still preserves regional ownership.
- For `user_profiles`, project `_id`, `home_region`, `subscribed_tags`, `followed_content`, and `profile_config`.
- Update printed labels so operator output no longer says devices or nodes.

### 4. `source/scripts/testing/create_indexes.py`

Required changes:

- Point indexes at `content_items` and `user_profiles`.
- Keep the existing `region_origin` index name and field path.
- Keep the existing content recency compound index on `tags + last_updated`.
- Rename `device_type` index to `content_type`.
- Keep the `payload.status` index path if the stored status remains under `payload`.
- Keep the `subscribed_tags` index for user-profile fan-out.

### 5. `source/scripts/Makefile`

Required changes:

- Rename seeding targets to `seed_content_items` and `seed_user_profiles`.
- Change `setup_test_data` dependencies accordingly.
- Make content/user terminology primary in comments and examples.
- Rename `DEVICES` to `CONTENT_ITEMS`.
- Rename `NODES` to `USERS`.
- Update all examples and invocations so they use `CONTENT_ITEMS` and `USERS` exactly.
- Update the `run_experiment` target invocation so it passes `--seed-content-items` and `--seed-users` instead of the legacy seeding flags.

### 6. `source/scripts/testing/run_experiment.sh`

Phase A scope in this file is limited to seeding and snapshot help/output:

- Replace `sensor_reports` and `device_registry` references in step descriptions.
- Replace `devices/region`, `nodes/region`, and similar wording in operator output.
- Rename `SEED_DEVICES` to `SEED_CONTENT_ITEMS`.
- Rename `SEED_NODES` to `SEED_USERS`.
- Rename `--seed-devices` to `--seed-content-items`.
- Rename `--seed-nodes` to `--seed-users`.
- Update help text, examples, validation, and step output so they use the renamed variables and flags exactly.

## Validation Gate

Phase A is complete only when all of the following hold:

- `make -C source/scripts setup_test_data` succeeds.
- The snapshot directory contains `content_items.json` and `user_profiles.json`.
- The exported IDs use `content` and `user` patterns.
- `Makefile` examples and variables use `CONTENT_ITEMS` and `USERS` exactly.
- `run_experiment.sh` help text and step output use `--seed-content-items`, `--seed-users`, `SEED_CONTENT_ITEMS`, and `SEED_USERS` exactly.

## Out of Scope for Phase A

- Edge-server route renames
- Traffic-generator route changes
- Phase JSON request-type renames
- Analysis label updates
- Final cleanup of old route/request labels outside the seeding stack