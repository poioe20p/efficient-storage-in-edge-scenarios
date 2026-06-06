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

The implemented workload is best understood as one application with two
operating regimes rather than one blended stress profile:

- **Storage-locality regime**: phases dominated by `device_status` traffic so
  cross-region reads pressure `VIP_DATA` and expose when local data placement
  helps.
- **Compute-analytics regime**: phases dominated by `dashboard` traffic so
  edge-server CPU work rises while cross-region pressure stays intentionally
  low.

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
- Realistic IoT read patterns (poll-heavy reads with thin local event logging)

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
  "_id": "lan2::node::005",
  "home_region": "lan2",
  "subscribed_tags": ["industrial", "high-priority", "thermal", "mechanical"],
  "watched_devices": ["lan1::device::482", "lan1::device::501", "lan2::device::017"],
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

### 3. `local_request_activity`

Bounded in-memory support state maintained by each edge server for the recent
requests it has personally served.

```json
{
  "request_kind": "device_status",
  "node_id": "lan2::node::005",
  "device_id": "lan1::device::482",
  "timestamp_epoch": 1716030123.12,
  "latency_ms": 84,
  "served_from_tier": 1,
  "tier1_hit_ratio": 1.0,
  "tier1_eligible_reads": 1,
  "severity": "warning",
  "status": "elevated",
  "tags": ["industrial", "thermal"]
}
```

This support state enables:

- Local temporal trend estimation for `/device/<id>/latest`
- Recent edge-local pressure summaries for `/service_pressure`
- Bounded retention through a fixed-size in-memory buffer sized for the default look-back window, with truncation surfaced in the `/service_pressure` response when the safety cap is reached

This state is intentionally **support state**, not the main data-gravity path.
It stays local to the serving edge process, while cross-region pressure still
comes from `sensor_reports` and `device_registry` reads.

`device_status` requests record per-device activity. `dashboard` requests also
enter this buffer so `/service_pressure` reflects compute-regime demand, but
those entries are node-scoped (`device_id = null`) and contribute mainly to
request counts, latency, and tag concentration rather than per-device ranking.

### Two-Regime Interpretation

The workload stays simple by keeping the same collections and endpoints while
changing only which request type dominates each phase:

- **Storage-locality regime**: `device_status` dominates. The interesting
  question is whether cross-region reads stay remote or become worth serving
  from a closer replica.
- **Compute-analytics regime**: `dashboard` dominates. The interesting question
  is whether metadata-rich ranking and summary work is heavy enough to justify
  extra edge-server capacity without confounding it with peak cross-region load.

`local_request_activity` remains useful in both regimes, but as local
analytics support for trend estimation and service-pressure summaries rather
than as the main source of cross-region pressure.

---

# Request Types

Before the detailed request-by-request walkthrough, keep the high-level model
in mind:

- The active client workload is read-only from the application's point of
  view. Test clients issue only GET requests to the three routes below.
- These three requests are intentionally different because each one stresses a
  different subsystem: storage locality, edge compute, or edge-local service
  introspection.
- Control-plane routes such as `/health`, `/drain`, `/vip_data`,
  `/tier1_manifest`, and `/wait_time` are not part of the normal client mix.

| Request type | Endpoint | Purpose | Why it exists |
| --- | --- | --- | --- |
| `device_status` | `/device/<device_id>/latest?node_id=<node_id>` | Return one device's latest state for a monitoring node. | It is the primary data-locality request and the main driver of cross-region storage pressure. |
| `service_pressure` | `/service_pressure?window_min=<minutes>&limit=<N>` | Summarize recent pressure seen by the serving edge. | It exposes local analytics pressure without adding synchronous MongoDB traffic. |
| `dashboard` | `/dashboard/<node_id>?limit=<N>` | Return a ranked overview of urgent devices for one node. | It is the primary compute-heavy request and justifies edge-server scaling. |

## 1. Device Status Read (Primary Data Gravity Driver)

```
GET /device/<device_id>/latest?node_id=<node_id>
```

Edge server:

- Fetch current `sensor_reports` document for `device_id` (via `VIP_Dados` for the device's LAN)
- Fetch requesting node's `device_registry` entry (via `VIP_Dados` for the node's LAN) to get `alert_config.threshold_override`
- Compute severity via `score_device_severity()`: multi-level classification (critical/warning/elevated/normal) using calibrated threshold ratio with per-device calibration hash and exponential weighting by device type
- Fetch recent local request activity for the same device (last 20 entries)
- Compute trend via `compute_trend()`: linear regression over `latency_ms` vs `timestamp`, classifies as rising/falling/stable with mean and std
- Stage a local request-activity event that is committed after the response with request-scoped latency and Tier 1 point-read hit metadata

This creates:

- 2 **locality-sensitive reads** (`sensor_reports` + `device_registry`) that drive
  cross-region pressure when the device and requester live on different LANs
- 1 **local support write** into the serving edge server's bounded in-memory buffer
- 1 **local support read** from that same local buffer for trend estimation
- Moderate server-side compute cost from severity scoring and linear regression
- Direct $T_{dados}$ amplification from the first two reads, which is why this
  route remains the primary storage-locality driver

---

## 2. Service Pressure Summary (Local Support Compute)

```
GET /service_pressure?window_min=<minutes>&limit=<N>
```

Edge server scans recent `local_request_activity` for the serving edge only and computes a summary of recent request pressure:

- Filter the local buffer to the requested time window
- Compute request count, unique devices, request rate, latency mean, and latency p95
- Compute Tier 1 hit ratio by weighting request-scoped Tier 1 ratios by their eligible point-read count
- Report `request_kind_counts` so `device_status` and `dashboard` pressure remain distinguishable in the local summary
- Rank top devices by local request concentration and average latency
- Rank top tags by local request count and unique-device count
- Compute a composite `pressure_score` from request rate, latency, concentration, and Tier 1 misses
- Return `window_truncated=true` and `retained_window_seconds` when the safety cap prevented a full look-back window from being retained in memory

This stresses:

- Local buffer scans over recent request activity
- CPU-side ranking and summary-statistics work on the edge server
- No MongoDB reads or writes on the synchronous support path

This is a **secondary analytics path** in the two-regime model: it justifies
local compute on the edge server and contributes some CPU work, but it is not
the main trigger the workload uses to isolate compute scaling.

---

## 3. Node Dashboard (Primary Compute-Regime Driver)

```
GET /dashboard/<node_id>?limit=<N>
```

Edge server:

- Read `device_registry` for `node_id` (via `VIP_Dados` for the node's LAN) to get `subscribed_tags`
- Query `sensor_reports` across **all LANs** where `tags` intersects `subscribed_tags` (`$in` array match), sorted by `last_updated` descending and limited to `DASHBOARD_CANDIDATE_LIMIT` (default 500) — bounding the result set to a constant-size candidate pool regardless of total collection size
- Compute urgency via `score_dashboard_urgency()`: 4-factor scoring per device
  - Threshold proximity (40%): `(value / alert_threshold)^3` — exponential near threshold
  - Tag priority (25%): average of per-tag weights (e.g. high-priority=2.0, industrial=1.3)
  - Status severity (20%): critical=3.0, warning=2.0, elevated=1.5, normal=1.0
  - Staleness decay (15%): exponential decay from `last_updated` with 300s half-life
- Verify fleet integrity via `verify_fleet_integrity()`: iterated SHA-256 over each device's payload, producing a deterministic integrity fingerprint as CPU-bound work
- Sort by urgency score descending, limit to N
- Compute fleet summary via `compute_dashboard_summary()`: urgency mean/std/max and status distribution across returned devices

This creates:

- Multi-LAN queries: `sensor_reports` fetched from every region, not just the node's home LAN
- Array intersection queries (`$in` on tags)
- Significant CPU-side compute: 4-factor urgency scoring with exponential functions per device + fleet statistics
- Local support-state write after the response so `/service_pressure` includes dashboard demand in compute-heavy phases

In the compute regime, this endpoint is intentionally the dominant request type.
It keeps the application read-heavy while shifting the main pressure toward
metadata-rich ranking and summary work on the edge server.

---

# Why This Is Ideal

## It creates all required stresses

| Component             | Trigger                                                                                          |
| --------------------- | ------------------------------------------------------------------------------------------------ |
| Compute scaling       | Dashboard-led metadata analytics and fleet summary work during compute phases                    |
| Data scaling          | Cross-region device-status hotspot during storage phases                                         |
| Routing balancing     | Multiple edge servers serving simultaneous dashboard and status requests                         |
| MongoDB justification | Heterogeneous device payloads, tag arrays, aggregation pipelines, TTL, schema flexibility        |

---

# How You Structure the Experiment

## Phase-Based Demand Shift

The implemented default workload is a 9-phase long-cycle schedule aligned to
the current controller timing budget. It contains two evaluation regimes inside
one application:

- **Storage-locality regime**: `storage_stress`, `cross_region_hotspot`, and
  `reverse_hotspot` are dominated by `device_status` so cross-region reads stay
  the main independent pressure.
- **Compute-analytics regime**: `compute_ramp`, `compute_spike`, and
  `sustained_plateau` are dominated by `dashboard` so edge-server CPU work can
  rise without peak data-gravity load obscuring the signal.

The storage-sensitive phases are long enough to let Tier 2 trigger, complete
replica-set join, and still be observed under active hotspot load;
`demand_drop` is intentionally long enough to expose cooldown-gated scale-down.

`cross_region_ratio` is not the fraction of all requests that go remote. In the
traffic generator it applies only to `device_status` requests, and only clients
on the source side of `hotspot_direction` emit those cross-region reads. The
effective whole-workload cross-region share is therefore lower than the raw
ratio, which is why `storage_stress` intentionally uses a lower ratio than the
hotspot phases.

| Phase | Duration | Rate/client | `cross_region_ratio` | Mix (`device_status / dashboard / service_pressure`) | Role |
| --- | ---: | ---: | ---: | --- | --- |
| `baseline` | 60 s | 1.0 | 0.00 | `0.35 / 0.35 / 0.30` | Tier 0 control |
| `local_moderate` | 90 s | 5.0 | 0.00 | `0.35 / 0.35 / 0.30` | Local warm-up without cross-region pressure |
| `storage_stress` | 240 s | 7.0 | 0.50 | `0.80 / 0.10 / 0.10` | Tier 2 pressure build-up; deliberately milder than full hotspot |
| `cross_region_hotspot` | 300 s | 8.0 | 0.85 | `0.80 / 0.10 / 0.10` | Observe Tier 2 benefit after readiness on `lan2_to_lan1` |
| `reverse_hotspot` | 300 s | 8.0 | 0.85 | `0.80 / 0.10 / 0.10` | Same observation window in the opposite direction |
| `compute_ramp` | 120 s | 11.0 | 0.05 | `0.35 / 0.50 / 0.15` | Shift emphasis from data gravity toward dashboard-led server-side work |
| `compute_spike` | 150 s | 17.0 | 0.05 | `0.25 / 0.60 / 0.15` | Peak compute stress with dashboard as the dominant route |
| `sustained_plateau` | 120 s | 10.0 | 0.05 | `0.30 / 0.55 / 0.15` | Hold compute pressure after the spike |
| `demand_drop` | 300 s | 1.0 | 0.00 | `0.60 / 0.30 / 0.10` | Observe cooldown-gated scale-in |

### Node-Profile Seeding

To make dashboard traffic meaningfully heavier without adding a fourth
endpoint, `device_registry` should be seeded with three profile families:

- **focused_local**: 1-2 subscribed tags, mostly local interests
- **regional_operator**: 3-4 subscribed tags, broader regional visibility
- **global_operator**: 4-6 subscribed tags, cross-region broad subscriptions

The compute regime relies on these broader `subscribed_tags` sets to increase
`sensor_reports` candidate fan-out during dashboard requests.

Expected signatures:

- `baseline` and `local_moderate` should remain stable at Tier 0 with no
  elasticity.
- `storage_stress` should create the first sustained storage-pressure window and
  is the phase most likely to trip the initial Tier 2 alert.
- `cross_region_hotspot` and `reverse_hotspot` are long observation windows:
  if Tier 2 helps, latency should improve within the same phase after
  `rs_secondary_ready`, not only after the hotspot has already ended.
- `compute_ramp`, `compute_spike`, and `sustained_plateau` keep cross-region
  traffic low so dashboard-driven CPU work, not peak data-gravity load,
  dominates the compute signal.
- `demand_drop` remains low for 300 s so storage and compute scale-down can arm
  after their respective cooldowns.

Measure:

- Time from first storage alert to service readiness; when controller logs are
  flattened this should map to the storage `operation=ready` row, sourced from
  `rs_secondary_ready` or the telemetry fallback if the fast path is absent
- Latency delta before and after readiness within the hotspot phases
- Whether `demand_drop` is long enough to trigger storage and compute scale-in
- Latency stability during infrastructure removal

### Storage-Trigger Companion Profile

Keep the 9-phase schedule above as the balanced hybrid reference profile. When
the next run must *force* natural Tier 2 storage scale-up under the unchanged
controller thresholds, use the storage-trigger companion profile in
`source/scripts/testing/phases_experiment_storage_trigger.json` together with a
larger working set.

Recommended starting point for that campaign:

- `CLIENTS=6`
- `DEVICES=600`
- `NODES=100`

This companion profile deliberately removes the compute-dominant phases and
extends the storage-locality window so the controller sees several sustained
10-second telemetry windows above the storage CPU or DB-latency floor without
retuning the controller policy.

| Phase | Duration | Rate/client | `cross_region_ratio` | Mix (`device_status / dashboard / service_pressure`) | Role |
| --- | ---: | ---: | ---: | --- | --- |
| `baseline` | 60 s | 2.0 | 0.00 | `0.60 / 0.25 / 0.15` | Short Tier 0 control before the storage-focused ramp |
| `local_moderate` | 120 s | 6.0 | 0.00 | `0.75 / 0.15 / 0.10` | Local warm-up with a larger working set but no cross-region reads |
| `storage_stress` | 420 s | 10.0 | 0.75 | `0.90 / 0.05 / 0.05` | Long pre-trigger storage build-up intended to arm the first Tier 2 alert |
| `cross_region_hotspot` | 420 s | 12.0 | 0.95 | `0.90 / 0.05 / 0.05` | Main Tier 2 observation window on `lan2_to_lan1` |
| `reverse_hotspot` | 420 s | 12.0 | 0.95 | `0.90 / 0.05 / 0.05` | Same Tier 2 observation window in the opposite direction |
| `demand_drop` | 360 s | 1.0 | 0.00 | `0.70 / 0.20 / 0.10` | Cooldown and storage scale-down observation |

Expected signatures for this companion profile:

- `median_storage_cpu_percent` should clear the storage CPU floor more often
  than in the current hybrid-observation runs.
- `t_db_p95_ms_owner_lan` should stay high for long enough to satisfy the
  storage 2-of-5 debounce while the hotspot is still active.
- `storage_count` should move above 1 during one or both hotspot phases if the
  current code still supports natural Tier 2 activation under storage-heavy
  demand.

---

# MongoDB Justification Beyond Replica Sets

This workload lets you demonstrate:

## 1. Flexible schema

Device payload schemas differ entirely by `device_type` — a temperature sensor, a vibration sensor, a GPS tracker, a humidity sensor, a power meter, and a proximity sensor (9 types total) have nothing structurally in common. MongoDB ingests all of them into one collection without schema migrations.

## 2. Metadata-rich filtering

Dashboard requests query `sensor_reports` with `$in` array matching on `tags`,
read `device_registry` for each requesting node, and then perform application-
side enrichment over heterogeneous documents. This still exercises MongoDB on
multi-valued attributes and nested fields without forcing support-state writes
through the storage path.

## 3. Secondary reads

When replica deployed, reads served locally.

## 4. Nested documents & arrays

Device `tags`, `metadata`, and alert `threshold_override` maps are natural fits. Querying `where tags ∈ subscribed_tags` with `$in` on an array field is precisely the kind of multi-valued attribute matching that document databases handle natively.

That’s a much stronger defense than:

> “We used MongoDB because it supports replication.”

---

# Important: Keep It Simple

Don't build a real IoT platform.

You only need:

- 2 MongoDB collections (`sensor_reports`, `device_registry`)
- 1 bounded local support-state buffer (`local_request_activity`)
- 3 endpoints (`/device/<id>/latest`, `/service_pressure`, `/dashboard/<node_id>`)
- A seeding script (populate devices with heterogeneous payloads per region)
- A traffic generator with tunable request mix and phase transitions

> **Implementation details**: see [traffic_generator.md](traffic_generator.md) for the current specification of `export_workload_snapshot.py`, `traffic_generator.py`, and `phases.json`.

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

# How This Fits the Thesis RQs

- **RQ1 — telemetry acquisition mode**: keep this same workload and vary only
  how the controller receives telemetry summaries.
- **RQ2 — metadata-aware backend selection**: keep this same workload and vary
  only the routing policy mode. The storage regime exposes data-plane choices;
  the compute regime exposes compute-plane choices.
- **RQ3 — locality / readiness strategy**: keep this same workload and vary
  only the data-locality strategy under shifting cross-region demand.

# Baseline Families

Use baseline families that match the advanced RQ map instead of a single open
comparison question:

- **RQ2 backend-selection baselines**:
  - `topology_only`
  - `topology_host`
  - current metadata-aware policy
- **RQ3 locality / readiness baselines**:
  - remote serving only
  - selective partial replication (when enabled)
  - cold-start full replica placement
  - reserved-standby full replica promotion (when implemented)
