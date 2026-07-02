# Edge Server Compute Load

This document describes the implemented edge-server paths that make the current
content-discovery workload produce meaningful CPU work. The goal is to keep
`T_proc = T_total - T_dados` non-trivial so compute elasticity can react to a
real application signal instead of to synthetic delay.

The main compute-oriented routes are implemented in
`source/docker/edge_server/source/monitoring_workload_routes.py`, and the pure
compute helpers live in `source/docker/edge_server/source/compute.py`.

---

## Design Principles

1. No fake work: no `sleep()` calls, no random delay injection.
2. CPU-visible work: scoring, statistics, hashing, and list processing that
   show up in `psutil.cpu_percent()`.
3. Scale with request volume: higher request rate means more cumulative
   `T_proc` inside each telemetry window.
4. No extra synchronous DB round-trips for the compute signal: the added work
   operates on data already fetched by the route.

---

## Endpoint Summary

| Route | Main compute path | Expected `T_proc` impact |
| --- | --- | --- |
| `/content/<content_id>?requester=<user_id>` | `score_content_relevance()` + `compute_trend()` | about 5-15 ms/request |
| `/service_pressure` | `compute_service_pressure()` over local request activity | about 3-10 ms/request |
| `/feed/<user_id>?limit=<N>` | `score_feed_relevance()` + `compute_feed_summary()` + `verify_feed_integrity()` | about 80-120 ms/request |

Two additional routes exist in the canonical storage-heavy phase mix:

| Route | Role |
| --- | --- |
| `POST /content` | storage write amplification and oplog traffic |
| `POST /content/aggregate` | collection-level aggregation work through the normal VIP read path |

These two POST routes are real runtime paths, but they are storage-side
amplifiers. They are not the primary `T_proc` signal used to justify compute
scale-out.

---

## Compute Module Functions

### `score_content_relevance()`

Used by `content_lookup`.

- reads the current engagement and relevance baseline
- applies a content-specific calibration hash
- applies a per-content-type sensitivity curve
- returns a multi-level relevance result: `hot`, `trending`, `steady`, or
  `quiet`

### `compute_trend()`

Also used by `content_lookup`.

- looks at recent local request latency samples for the same content item
- computes a regression slope
- classifies the trend as `rising`, `falling`, `stable`, or
  `insufficient_data`

### `compute_service_pressure()`

Used by `service_pressure`.

- scans the local in-memory request buffer
- computes request rate, latency summary, Tier 1 hit ratio, and concentration
  metrics
- returns `request_kind_counts`, `top_content`, `top_tags`, and a derived
  pressure score/label

### `score_feed_relevance()`

Used by `feed_ranking`.

- scores each candidate content item using baseline proximity, tag priority,
  payload status, and staleness decay
- sorts the candidate pool by urgency score

### `compute_feed_summary()`

Also used by `feed_ranking`.

- computes urgency mean, max, and distribution summaries over the returned feed

### `verify_feed_integrity()`

Also used by `feed_ranking`.

- runs deterministic iterative hashing over the returned content list
- converts feed ranking into CPU-visible work without changing the DB path

---

## Runtime Knobs

The current content-discovery compute path is controlled by these env vars in
`edge_server_config.py`:

| Variable | Default | Effect |
| --- | --- | --- |
| `SERVICE_PRESSURE_DEFAULT_WINDOW_MIN` | `10` | Default look-back window for `service_pressure` |
| `SERVICE_PRESSURE_DEFAULT_LIMIT` | `10` | Default response limit for ranked local summaries |
| `LOCAL_REQUEST_BUFFER_MAX_EVENTS` | derived | Cap for the edge-local request buffer |
| `FEED_CANDIDATE_LIMIT` | `500` | Maximum candidate pool fetched before ranking |
| `FEED_INTEGRITY_WORK_FACTOR` | `200` | Hash iterations used by `verify_feed_integrity()` |

`FEED_CANDIDATE_LIMIT` and `FEED_INTEGRITY_WORK_FACTOR` are the most direct
controls over how much CPU the `feed_ranking` route consumes per request.

---

## Why The Signal Matters

The canonical phase profile uses `compute_spike` as the main compute-focused
window. In that phase, `feed_ranking` dominates the mix while
`cross_region_ratio` stays low. That separation matters:

- storage-side pressure remains visible in the earlier storage phases
- edge-server CPU becomes the dominant signal in the compute phase
- the controller can react to a real application-side `T_proc` increase instead
  of to synthetic or DB-only load

In other words, the current content-discovery workload produces a compute
signal that is both realistic and attributable.
