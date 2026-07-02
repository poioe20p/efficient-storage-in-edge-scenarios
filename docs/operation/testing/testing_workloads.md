# Testing Workloads

The testing workload exists to demonstrate four things under one coherent
application shape:

1. Elastic resource adaptation across compute and storage.
2. Lower latency after the platform reacts to shifting demand.
3. Balanced request distribution across edge servers.
4. A MongoDB fit that depends on document-shape flexibility and locality
   pressure, not only on replica-set support.

The current runtime implements a content-discovery application with two
operating regimes inside one workload family:

- Storage-locality regime: `content_lookup` dominates and cross-region reads
  pressure `VIP_DATA`.
- Compute-analytics regime: `feed_ranking` dominates and edge-server CPU work
  becomes the main signal.

The canonical active phase profile for this workload is
`source/scripts/testing/phases.json`. Shorter validation and diagnostic
profiles live under `source/scripts/testing/phases_override/`.

---

## Scenario Overview

The workload models a multi-region content-discovery platform.

- Each LAN owns a catalog of `content_items`.
- Each LAN also owns `user_profiles` whose interests drive cross-region read
  demand.
- Edge servers answer content lookups and ranked feed requests locally, while
  reading through `VIP_DATA` when the requested data lives elsewhere.
- Demand shifts by changing the request mix and cross-region ratio between
  phases instead of switching to a different application.

This keeps the narrative simple while still creating measurable data-gravity,
compute-scaling, and routing effects.

---

## Core Workload Model

### 1. `content_items`

One document per content item, stored in the owning LAN and updated in place.

```json
{
  "_id": "lan1::content::482",
  "region_origin": "lan1",
  "content_type": "short_video",
  "tags": ["trending", "sports", "premium"],
  "payload": {
    "engagement": 74.3,
    "status": "hot",
    "media_duration_s": 42
  },
  "metadata": {
    "relevance_baseline": 65.0,
    "creator_tier": "partner",
    "language": "en"
  },
  "last_updated": 1716030123.12
}
```

Why this helps MongoDB:

- Content types can carry different nested payload structures without schema
  migrations.
- Tag arrays enable multi-valued interest matching.
- Nested metadata supports application-side enrichment with locality-sensitive
  reads.
- In-place updates create oplog traffic when storage-heavy phases include
  write amplification.

### 2. `user_profiles`

One document per user profile. It defines the requester's home LAN, interest
tags, and optional per-content-type relevance overrides.

```json
{
  "_id": "lan2::user::005",
  "home_region": "lan2",
  "subscribed_tags": ["trending", "finance", "technology"],
  "watched_content": ["lan1::content::482", "lan2::content::017"],
  "profile_config": {
    "relevance_override": {
      "short_video": 70.0,
      "news_article": 55.0
    }
  }
}
```

Why this helps MongoDB:

- Users do not share a rigid profile shape.
- Interest tags create array-intersection queries for ranked feeds.
- Nested override maps let the edge server customize scoring without a join
  table.

### 3. `local_request_activity`

Bounded in-memory support state maintained by each edge server for the recent
requests it has served.

```json
{
  "request_kind": "content_lookup",
  "user_id": "lan2::user::005",
  "content_id": "lan1::content::482",
  "timestamp": 1716030123.12,
  "latency_ms": 84,
  "served_from_tier": 1,
  "tier1_hit_ratio": 1.0,
  "tier1_eligible_reads": 1,
  "relevance": "hot",
  "status": "hot",
  "tags": ["trending", "sports"]
}
```

This support state enables:

- local temporal trend estimation for `content_lookup`
- local pressure summaries for `service_pressure`
- bounded retention with explicit truncation signaling when the edge-local
  buffer cap is reached

`local_request_activity` is intentionally support state, not the primary
storage-pressure path. Cross-region pressure still comes from `content_items`
and `user_profiles` reads.

---

## Request Types

The workload uses three core read paths and two supplemental storage
amplifiers.

### Core read paths

| Request type | Endpoint | Role |
| --- | --- | --- |
| `content_lookup` | `/content/<content_id>?requester=<user_id>` | Primary storage-locality request |
| `feed_ranking` | `/feed/<user_id>?limit=<N>` | Primary compute-heavy request |
| `service_pressure` | `/service_pressure?window_min=<minutes>&limit=<N>` | Local support-state introspection |

### Supplemental storage amplifiers

| Request type | Endpoint | Role |
| --- | --- | --- |
| `content_update` | `POST /content` | Storage write amplification and oplog traffic |
| `content_aggregate` | `POST /content/aggregate` | Full-collection aggregation work through `VIP_DATA` |

The active user-facing narrative stays centered on `content_lookup`,
`feed_ranking`, and `service_pressure`. The two POST routes are generator-driven
auxiliary operations used by the canonical storage-heavy phases to make
MongoDB-side work visible.

### 1. `content_lookup`

`GET /content/<content_id>?requester=<user_id>`

The edge server:

- reads the `content_items` document for the target content
- reads the requester's `user_profiles` document for relevance overrides
- computes relevance via `score_content_relevance()`
- computes a short trend over recent local request history via `compute_trend()`
- stages a local request-activity event with request-scoped latency and Tier 1
  hit information

This is the main storage-locality driver because it creates the most direct
cross-region point-read pressure.

### 2. `feed_ranking`

`GET /feed/<user_id>?limit=<N>`

The edge server:

- reads the user's `user_profiles` document to get `subscribed_tags`
- queries `content_items` across all LANs for matching tags
- scores results with `score_feed_relevance()`
- computes response summaries with `compute_feed_summary()`
- runs `verify_feed_integrity()` to create deterministic CPU-bound work
- stages a local request-activity event so `service_pressure` sees feed-heavy
  demand

This is the primary compute-regime path: it stays read-heavy while shifting the
dominant cost toward edge-server scoring, summarization, and verification.

### 3. `service_pressure`

`GET /service_pressure?window_min=<minutes>&limit=<N>`

The edge server summarizes its own recent `local_request_activity` buffer:

- request count and request rate
- mean and p95 latency
- request-kind counts
- top content concentration
- top tags
- Tier 1 hit ratio over eligible reads
- a derived pressure score and label

This is a local analytics path. It does not create synchronous MongoDB load.

### 4. `content_update`

`POST /content`

The generator sends engagement updates to the owning LAN primary. These
updates are not the main user-facing story, but they amplify storage behavior
by generating real write load and oplog traffic.

### 5. `content_aggregate`

`POST /content/aggregate`

The generator runs an aggregation pipeline against `content_items` through the
normal VIP path. This creates collection-level CPU work on the storage side and
helps differentiate phases where point reads alone would under-stress MongoDB.

---

## Why This Workload Fits The Thesis

| Mechanism | Trigger in the current workload |
| --- | --- |
| Compute scaling | `feed_ranking` scoring, summary work, and integrity verification |
| Storage scaling | cross-region `content_lookup` reads plus storage-heavy write and aggregation mixes |
| Routing balance | simultaneous edge demand across multiple namespaces and phases |
| MongoDB justification | heterogeneous content records, nested profile overrides, tag-array filtering, and locality-sensitive reads |

---

## Phase-Based Demand Shift

The canonical active profile is the 6-phase schedule in
`source/scripts/testing/phases.json`.

`cross_region_ratio` applies only to `content_lookup`. The canonical storage
phases also include `content_update` and `content_aggregate` so storage-side
CPU, write load, and oplog effects are measurable without changing the
application family.

| Phase | Duration | Rate/client | `cross_region_ratio` | Mix | Role |
| --- | ---: | ---: | ---: | --- | --- |
| `baseline` | 60 s | 1.0 | 0.00 | `content_lookup=0.60`, `feed_ranking=0.25`, `service_pressure=0.15` | Tier 0 control |
| `storage_storm` | 240 s | 4.0 | 0.90 | `content_lookup=0.35`, `feed_ranking=0.10`, `service_pressure=0.05`, `content_update=0.30`, `content_aggregate=0.20` | Storage-heavy buildup |
| `tier1_hotspot` | 180 s | 5.0 | 0.95 | `content_lookup=0.80`, `feed_ranking=0.05`, `service_pressure=0.05`, `content_update=0.05`, `content_aggregate=0.05` | Tier 1 and locality hotspot |
| `inter_hotspot_cooldown` | 300 s | 1.0 | 0.00 | `content_lookup=0.60`, `feed_ranking=0.25`, `service_pressure=0.15` | Recovery and drain observation |
| `compute_spike` | 180 s | 4.0 | 0.05 | `content_lookup=0.20`, `feed_ranking=0.65`, `service_pressure=0.15` | Peak compute pressure |
| `cooldown` | 120 s | 1.0 | 0.00 | `content_lookup=0.60`, `feed_ranking=0.25`, `service_pressure=0.15` | Cooldown-gated scale-in observation |

Interpretation by regime:

- Storage-locality regime: `storage_storm` and `tier1_hotspot` create the main
  cross-region and storage-side pressure.
- Compute-analytics regime: `compute_spike` keeps cross-region demand low while
  making `feed_ranking` dominant.

### Validation and diagnostic overrides

The repository keeps three non-canonical override profiles:

- `source/scripts/testing/phases_override/phases_tier1_smoke.json`
  Focused bidirectional Tier 1 hotspot validation.
- `source/scripts/testing/phases_override/phases_rq1_verify.json`
  Shorter verification profile that still exercises storage and compute shifts.
- `source/scripts/testing/phases_override/phases_mini.json`
  Minimal smoke profile for quick end-to-end checks.

---

## MongoDB Justification Beyond Replica Sets

This workload justifies MongoDB on multiple fronts:

1. Flexible schema: `content_items` vary by `content_type` and nested payload.
2. Metadata-rich filtering: `feed_ranking` depends on array intersection over
   `tags` plus nested profile configuration.
3. Read locality pressure: `content_lookup` makes cross-region point reads easy
   to measure and reason about.
4. Storage-side mixed pressure: `content_update` and `content_aggregate` create
   write and aggregation load without leaving the current workload family.

That is a stronger thesis defense than "we used MongoDB because it replicates".

---

## Keep It Simple

The current implementation is intentionally small:

- 2 MongoDB collections: `content_items` and `user_profiles`
- 1 bounded edge-local support-state buffer: `local_request_activity`
- 3 core read endpoints and 2 supplemental storage-amplification routes
- 1 traffic generator with tunable phase mixes and cross-region ratios

That is enough to generate:

- storage elasticity pressure
- compute elasticity pressure
- routing-balance evidence
- latency deltas before and after adaptation

---

## What The Experiments Prove

The current workload is designed to show that:

1. Storage expands only when locality pressure and storage-side work justify it.
2. Tier 1 selective sync reacts to concentrated hotspots without redefining the
   whole workload.
3. Compute scaling reacts to feed-ranking pressure independently of peak
   cross-region storage load.
4. WSM-based routing still distributes requests across available edge servers.
5. Cooldown phases reclaim resources after the pressure subsides.

---

## Thesis/RQ Mapping And Baseline Families

Use the workload families like this:

- Canonical active baseline: `source/scripts/testing/phases.json`
- Focused Tier 1 companion: `source/scripts/testing/phases_override/phases_tier1_smoke.json`
- Short verification profile: `source/scripts/testing/phases_override/phases_rq1_verify.json`
- Minimal smoke profile: `source/scripts/testing/phases_override/phases_mini.json`

For thesis and RQ analysis, compare runs by holding the application family
constant and varying only the mechanism set, WAN profile, or workload profile
within these defined phase files.
