# Selective-Sync Telemetry

## 1. Purpose

The selective-sync telemetry producer runs inside the `edge_selective_storage`
supervisor container. It pushes per-collection Change Stream metrics and
control events to the same per-network aggregator PUSH socket used by compute
and storage producers.

## 2. Current Files

- `source/docker/edge_selective_storage/telemetry.py` — `emit_telemetry()`,
  `emit_control_event()`, lazy ZMQ PUSH socket, and MAC discovery.

## 3. Shared Aggregator Contract

The supervisor reuses the same ZMQ PUSH socket contract as `mongo_telemetry.py`
and `telemetry.py`:

- Aggregator address resolved from `AGGREGATOR_PULL_ADDR` or derived from
  `LAN_ID` (e.g. `lan1` → `tcp://10.0.0.5:5555`).
- Socket is lazily connected on first use via `_get_telemetry_sock()`.
- All sends use `zmq.NOBLOCK` — frames are silently dropped under
  backpressure; the next event carries fresh values.

## 4. `selective_sync_per_collection` Payload

`emit_telemetry(collection, lag_s, token_age_s, hot_doc_count)` pushes one
frame per Change Stream event:

```json
{
  "server_mac":   "<MAC>",
  "member_state": "STANDALONE_CACHE",
  "selective_sync_per_collection": {
    "<collection>": {
      "lag_s":              0.8,
      "resume_token_age_s": 1.4,
      "hot_doc_count":      200
    }
  },
  "ts": 1742126400.0
}
```

| Field | Meaning |
| ----- | ------- |
| `lag_s` | Wall-clock seconds between the Change Stream event's `clusterTime` and now, computed by `compute_lag_s()`. Clamped to `>= 0.0`. |
| `resume_token_age_s` | Age of the resume token in seconds (provided by the caller). |
| `hot_doc_count` | Number of documents currently tracked as "hot" for that collection (provided by the caller). |

The frame carries a **single collection** per emission — the aggregator
handles merging across collections (see [aggregation_publication/aggregator.md](../aggregation_publication/aggregator.md)).

## 5. `control_events` Piggyback

`emit_control_event(event_type, **fields)` pushes a wrapped control frame on
the same ZMQ channel:

```json
{
  "server_mac":     "<MAC>",
  "member_state":   "STANDALONE_CACHE",
  "control_events": [
    {
      "event_type": "drain_complete",
      "server_id":  "<MAC>",
      "reason":     "scale_down_selective",
      "ts":         1742126400.0
    }
  ],
  "ts": 1742126400.0
}
```

This matches the wrapped control-event shape the aggregator already recognises
from compute/storage producers. The aggregator extracts and forwards these as
immediate mini-summaries without waiting for the next window close.

## 6. `STANDALONE_CACHE` Identity Marker

Every frame carries `"member_state": "STANDALONE_CACHE"`. This marks the frame
as originating from a Tier 1 selective-sync container rather than a replica-set
member. The topology layer uses this marker to exclude Tier 1 containers from
RS member advertisements and storage-role synchronisation.

## 7. Relationship to Aggregation and Controller Consumption

The aggregator routes selective-sync frames into a separate `ss_events` bucket
and applies last-writer-wins overwrites onto `StorageServerSummary`. The
controller consumes the resulting per-collection state for hotness evaluation
and coordinator-state publication.

These downstream stages are documented in:
- [aggregation_publication/aggregator.md](../aggregation_publication/aggregator.md) (§11 — Selective-Sync Folding)
- [controller_side/controller_telemetry_consumer.md](../controller_side/controller_telemetry_consumer.md)
