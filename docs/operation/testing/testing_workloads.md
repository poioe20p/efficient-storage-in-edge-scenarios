Good. That goal narrows things properly.

You want to demonstrate:

1. Elastic resource adaptation (compute + storage)
2. Lower latency under shifting demand
3. Balanced load distribution
4. That MongoDB is a good fit beyond just replica sets

So your workload must:

- Be read-heavy (to create data gravity)
- Include aggregation (to justify MongoDB)
- Include heterogeneous documents (to justify document model)
- Create regional skew that shifts over time
- Allow controlled phase transitions

Let’s design something that checks all boxes.

---

# The Best Fit: Multi-Region IoT Edge Monitoring Platform

> A distributed edge platform where each region produces IoT sensor data, but edge nodes from other regions consume it dynamically, and dashboards are assembled at request time from live device state.

Think of it as an industrial or smart-city monitoring system where:

- Devices are scattered across regions
- Edge nodes serve queries for local and remote device data
- Demand patterns shift as different regions become "hot" (e.g., a sensor cluster enters alarm state)

This combines:

- Cross-region data gravity (the core thesis claim)
- Aggregation workloads (anomaly detection, fleet summaries)
- Metadata richness (heterogeneous device types, no schema migrations)
- Realistic IoT read patterns (poll-heavy, append-only event logs)

---

# Core Workload Model

## Data Types

Use 3 collections:

### 1. `sensor_reports`

Latest readings from IoT devices. One document per device, updated in-place (upsert) on each report, preserving the full current state.

```json
{
  "_id": "lan1::device::482",
  "region_origin": "lan1",
  "device_type": "temperature_sensor",
  "tags": ["industrial", "high-priority"],
  "unit": "celsius",
  "payload": {
    "value": 74.3,
    "status": "warning",
    "calibration_offset": -0.5
  },
  "metadata": {
    "firmware": "v2.1.4",
    "location": "floor_3_zone_B",
    "alert_threshold": 80.0
  },
  "last_updated": ISODate(...)
}
```

Why this helps MongoDB:

- Flexible metadata: different device types carry entirely different payload fields — no schema migrations required
- Tag arrays: multi-dimensional device classification (zone, priority, type)
- Nested structures: payload schema varies per `device_type` without breaking reads on other documents
- Upsert pattern: `replaceOne` with `upsert: true` keeps one current-state document per device

---

### 2. `device_registry`

One document per registered edge node or application client. Describes which device streams it is subscribed to and its home region.

```json
{
  "_id": "node_891",
  "home_region": "lan2",
  "subscribed_tags": ["industrial", "high-priority"],
  "watched_devices": ["lan1::device::482", "lan1::device::501"],
  "alert_config": {
    "email": "ops@example.com",
    "threshold_override": {"temperature_sensor": 75.0}
  }
}
```

Heterogeneous fields per node type.
Subscription-driven data access pattern.
Nested alert config — evolves per deployment without migrations.
Good for document DB: no two node configurations are identical.

---

### 3. `query_events`

Append-only log of every device data request served by the edge platform.

```json
{
  "node_id": "node_891",
  "device_id": "lan1::device::482",
  "region_served": "lan2",
  "timestamp": ISODate(...),
  "latency_ms": 84,
  "served_from_tier": 1
}
```

This collection enables:

- Aggregation pipelines for anomaly frequency and device hotspots
- Spatio-temporal popularity metrics (which region is querying which device cluster and how often)
- TTL auto-expiry: old events are irrelevant after a retention window, keeping the collection bounded

This is where MongoDB's aggregation framework earns its place — time-window grouping by `device_id` and `region_served` drives the Data Manager's tier escalation signals.

---

# Request Types

## 1. Device Status Read (Primary Data Gravity Driver)

```
GET /device/<device_id>/latest
```

Edge server:

- Fetch current `sensor_reports` document for `device_id` (via `VIP_Dados`)
- Fetch requesting node's `device_registry` entry to apply alert thresholds
- Evaluate alert state (lightweight compute: compare `payload.value` against threshold)
- Render status response (JSON or HTML fragment)
- Append to `query_events`

This creates:

- 2–3 DB reads per request (sensor_reports + device_registry + write to query_events)
- Cross-region dependency when `device_id` region origin ≠ requesting node's region
- Moderate compute cost (threshold evaluation)
- Direct $T_{dados}$ amplification: each HTTP request generates at least two `VIP_Dados` queries

---

## 2. Anomaly Detection Query (Aggregation Driver)

```
GET /anomalies?region=lan2&window=1h
```

Edge server runs MongoDB aggregation on `query_events` and `sensor_reports`:

- Match `query_events` within time window and `region_served = lan2`
- Group by `device_id`, count queries
- Join with `sensor_reports` to filter devices in `warning` or `critical` status
- Sort by query count descending
- Limit 10

This stresses:

- Aggregation pipeline with `$lookup` across collections
- Index performance on `timestamp` + `region_served` compound index
- Potentially large scans when event volume is high

This validates MongoDB beyond replication:

- Multi-collection aggregation pipeline
- Time-window queries matching realistic IoT monitoring patterns
- TTL indexes on `query_events` to bound collection size automatically

---

## 3. Node Dashboard (Mixed Compute + Data)

```
GET /dashboard/<node_id>
```

Edge server:

- Read `device_registry` for `node_id` to get `subscribed_tags` and `watched_devices`
- Query `sensor_reports` where `tags` intersects `subscribed_tags` (array match)
- Sort results by `metadata.alert_threshold` proximity to `payload.value` (descending urgency)
- Limit N most urgent devices
- Render summary dashboard

This creates:

- Multi-field queries with array intersection (`$in` on tags)
- Index use on `tags` and `region_origin`
- CPU-side ranking: urgency score computed per document before response is rendered

---

# Why This Is Ideal

## It creates all required stresses:

| Component             | Trigger                                                                                          |
| --------------------- | ------------------------------------------------------------------------------------------------ |
| Compute scaling       | Alert evaluation + dashboard ranking per request                                                 |
| Data scaling          | Cross-region device data hotspot (one region's devices become heavily queried by another region) |
| Routing balancing     | Multiple edge servers serving simultaneous dashboard and status requests                         |
| MongoDB justification | Heterogeneous device payloads, tag arrays, aggregation pipelines, TTL, schema flexibility        |

---

# How You Structure the Experiment

## Phase-Based Demand Shift

### Phase 1 — Local Consumption

- lan1 edge nodes query lan1 device data
- lan2 edge nodes query lan2 device data
- Expect: no cross-region replication; both regions served from their own primary at Tier 0

### Phase 2 — Cross-Region Device Hotspot

Simulate:

- A cluster of lan1 industrial sensors enters warning state
- lan2 edge nodes begin polling lan1 device data heavily
- 70% of lan2 traffic issues `/device/<lan1::device::*>/latest` requests

Expected:

- $T_{dados}$ increases in lan2 (queries crossing the inter-region link)
- Data Manager detects sustained $T_{dados} > \tau_{dados}$
- Data Manager deploys a Selective Sync Node in lan2 for the lan1 device data subset
- After synchronization, lan2 queries are served locally; $T_{dados}$ decreases

Measure:

- Time from threshold breach to replica availability
- Latency reduction after tier escalation (Tier 0 → Tier 1)
- Inter-region link traffic reduction

---

### Phase 3 — Compute Spike

Increase the request rate uniformly across both regions (simulating a monitoring surge — all nodes polling all devices at high frequency).

Expected:

- $T_{proc}$ increases across web servers (alert evaluation + dashboard rendering under load)
- Compute Manager detects sustained $T_{proc} > \tau_{proc}$
- Compute Manager spawns additional web server containers via `docker run`
- WSM re-routes traffic; load redistributes across old and new servers

Measure:

- Per-server request distribution before and after scale-out
- CPU utilization distribution across servers
- $T_{proc}$ and $T_{total}$ stabilization time after new servers become active

---

### Phase 4 — Demand Drop

The lan1 device cluster returns to normal state. Traffic returns to baseline: lan2 nodes stop issuing cross-region queries; request rate drops uniformly.

Expected:

- Selective Sync Node TTL cache cools down; hit-count drops; cold documents self-evict
- Data Manager detects $T_{dados}$ back below threshold; removes the lan2 Selective Sync Node (Tier 1 → Tier 0)
- Compute Manager detects idle web servers; removes excess containers (scale-in)
- Resource usage returns to baseline

Measure:

- Time from demand drop to Selective Sync Node removal
- Time from demand drop to web server scale-in
- Latency stability during infrastructure removal (no disruption to active connections)

---

# MongoDB Justification Beyond Replica Sets

This workload lets you demonstrate:

### 1. Flexible schema

Device payload schemas differ entirely by `device_type` — a temperature sensor, a vibration sensor, a GPS tracker, a humidity sensor, a power meter, and a proximity sensor (9 types total) have nothing structurally in common. MongoDB ingests all of them into one collection without schema migrations.

### 2. Aggregation framework

Anomaly detection queries use `$match` (time window + region), `$group` (by `device_id`), `$lookup` (join to `sensor_reports`), `$sort`, `$limit`. These are not achievable with simple key-value lookups.

### 3. TTL indexes

Expire old `query_events` automatically after a retention window (e.g., 24h). This bounds collection growth in a resource-constrained edge node and mirrors how real IoT systems handle event log retention.

### 4. Secondary reads

When replica deployed, reads served locally.

### 5. Nested documents & arrays

Device `tags`, `metadata`, and alert `threshold_override` maps are natural fits. Querying `where tags ∈ subscribed_tags` with `$in` on an array field is precisely the kind of multi-valued attribute matching that document databases handle natively.

That’s a much stronger defense than:

> “We used MongoDB because it supports replication.”

---

# Important: Keep It Simple

Don't build a real IoT platform.

You only need:

- 3 collections (`sensor_reports`, `device_registry`, `query_events`)
- 3 endpoints (`/device/<id>/latest`, `/anomalies`, `/dashboard/<node_id>`)
- A seeding script (populate devices with heterogeneous payloads per region)
- A traffic generator with tunable request mix and phase transitions

> **Implementation details**: see [traffic_generator_plan.md](traffic_generator_plan.md) for the full specification of `export_workload_snapshot.py`, `traffic_generator.py`, and `phases.json`.

That’s enough to produce:

- Elasticity
- Latency shifts
- Balanced routing
- Data gravity

---

# What You Are Actually Proving

Your experiments should demonstrate:

1. Under shifting regional popularity, the system deploys storage only when justified.
2. Under compute spikes, new servers are added without unnecessary replication.
3. Load distributes across servers according to WSM.
4. Latency returns toward baseline after scaling.
5. Resources are reclaimed when demand drops.

That is a coherent orchestration thesis.

---

Now one important question:

Because without those baselines, you can show behavior, but not superiority.

Do you plan to compare against:

- Static full replication
- Static no replication
- Round-robin load balancing
