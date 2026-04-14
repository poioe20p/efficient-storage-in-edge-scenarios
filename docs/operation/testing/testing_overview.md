# Testing — Overview

## Purpose

The testing subsystem validates the platform's elastic behavior — compute
scale-out, data-gravity-driven storage replication, and WSM-based load
balancing — under controlled, reproducible workload conditions. It provides the
tooling needed to seed data, generate phased HTTP traffic, add realistic CPU
work to edge server endpoints, and trace individual requests through the full
VIP routing pipeline.

---

## Architecture: Experiment Data Flow

```
  sensor_reports.py ──► MongoDB (seed)
  device_registry.py ─► MongoDB (seed)
  create_indexes.py ──► MongoDB (indexes)
         │
         ▼
  export_workload_snapshot.py ──► data/workload_snapshot/
                                    ├── sensor_devices.json
                                    └── device_registry.json
                                              │
         ┌────────────────────────────────────┘
         ▼
  traffic_generator.py              phases.json (4-phase config)
    ├─ reads snapshot + phases      ──────────────────────────────
    ├─ spawns async tasks                Phase 1: Local Consumption
    │   per client namespace             Phase 2: Cross-Region Hotspot
    │   (ip netns exec curl)             Phase 3: Compute Spike
    └─ writes CSV metrics                Phase 4: Demand Drop
         │
         ▼
  metrics/client_requests.csv    ←── one row per request (latency, status, phase)
```

Separately, `trace_request.sh` can be used at any time to fire a single request
and collect a formatted trace of every hop (VIP\_SERVER routing → edge server →
VIP\_DATA routing → storage node).

---

## Components

### 1. Workload Design — [`testing_workloads.md`](testing_workloads.md)

Defines the experimental workload: a multi-region IoT edge monitoring platform
with 3 MongoDB collections (`sensor_reports`, `device_registry`,
`query_events`) and 3 edge server endpoints (`/device/<id>/latest`,
`/anomalies`, `/dashboard/<node_id>`).

Key decisions:

- **Read-heavy, aggregation-rich** workload that justifies MongoDB beyond simple
  replication (flexible schema, `$lookup` pipelines, TTL indexes, array
  queries).
- **4-phase demand shift** that exercises every elasticity pathway: local
  baseline → cross-region data gravity → compute spike → demand drop and
  scale-in.
- **Measurable outcomes**: time-to-replica, latency reduction after tier
  escalation, CPU distribution after scale-out, resource reclamation timing.

### 2. Traffic Generator — [`traffic_generator_plan.md`](traffic_generator_plan.md)

Implementation plan for the client-side experiment driver.

| Script | Purpose |
|---|---|
| `export_workload_snapshot.py` | Pre-exports device/node data from MongoDB to JSON — decouples traffic generation from live DB access |
| `traffic_generator.py` | Async Python script: phases × clients → `curl` inside network namespaces through `VIP_SERVER` |
| `phases.json` | Declarative 4-phase config (duration, rate, cross-region ratio, request mix) |

Output: `metrics/client_requests.csv` with per-request timestamp, phase,
endpoint, target region, HTTP status, and latency.

### 3. Edge Server Compute Load — [`edge_server_compute_load_plan.md`](edge_server_compute_load_plan.md)

Implementation plan for making edge server endpoints produce meaningful CPU
work so that $T_{proc} = T_{total} - T_{dados}$ is non-trivial.

| Endpoint | Added Compute | $T_{proc}$ Impact |
|---|---|---|
| `/device/<id>/latest` | Multi-level severity scoring + linear regression trend analysis | ~5–15 ms |
| `/anomalies` | Z-score normalization + composite risk re-ranking | ~3–10 ms |
| `/dashboard/<node_id>` | Multi-factor urgency scoring (tag priority, staleness decay) + fleet summary stats | ~5–20 ms |

All compute is implemented in a pure-stdlib module (`compute.py`) with no I/O
dependencies — execution time flows entirely into $T_{proc}$.

### 4. Request Trace — [`trace_request_plan.md`](trace_request_plan.md)

Implementation plan for a debugging/demonstration script that traces a single
request end-to-end through the platform.

```
CLIENT (namespace) → VIP_SERVER (SDN selects edge server)
                   → Edge Server (HTTP + MongoDB via VIP_DATA)
                   → VIP_DATA (SDN selects storage node)
                   → Response back to client
```

Collects `docker logs` from controllers and edge servers within the request's
time window and formats a color-coded trace showing each routing decision.

---

## Execution Order

```bash
# 1. Seed data
python3 source/scripts/testing/sensor_reports.py --devices 100
python3 source/scripts/testing/device_registry.py --nodes 40 --devices 100
python3 source/scripts/testing/create_indexes.py

# 2. Export snapshot
python3 source/scripts/testing/export_workload_snapshot.py \
  --output-dir data/workload_snapshot

# 3. Create test client namespaces
sudo ./source/scripts/network/clients/create_test_clients.sh --lan 1 --count 3
sudo ./source/scripts/network/clients/create_test_clients.sh --lan 2 --count 3

# 4. Run the experiment
sudo python3 source/scripts/testing/traffic_generator.py \
  --config source/scripts/testing/phases.json \
  --clients-lan1 test_client_1,test_client_2,test_client_3 \
  --clients-lan2 test_client_4,test_client_5,test_client_6 \
  --output metrics/client_requests.csv

# (optional) Trace a single request for debugging
sudo bash source/scripts/testing/trace_request.sh \
  --ns lan1_client_1 \
  -- curl -s "http://10.0.0.100:5000/device/lan1::device::001/latest?node_id=lan1::node::001"
```

---

## What the Experiments Prove

| # | Claim | How It Is Demonstrated |
|---|---|---|
| 1 | Storage deploys only when justified | Phase 2 cross-region hotspot triggers Data Manager; Phase 1/4 show no unnecessary replication |
| 2 | Compute scales independently of storage | Phase 3 high RPS triggers Compute Manager without triggering data replication |
| 3 | Load distributes via WSM | Per-server request counts and CPU utilization converge after scale-out |
| 4 | Latency recovers after scaling | $T_{total}$ returns toward baseline once new resources are active |
| 5 | Resources are reclaimed on demand drop | Phase 4 observes over-provisioned state and (when implemented) scale-in |

---

## Experiment Results — Run `20260411_235936`

### Summary

Full 9-phase workload (baseline → local_moderate → storage_stress →
cross_region_hotspot → reverse_hotspot → compute_ramp → compute_spike →
sustained_plateau → demand_drop). Total duration ~22 min.

### Observations by Phase

**Stable phases (baseline – compute_ramp, 22:59 – 23:12):**
Both LANs ran with 1 server + 1 storage each. CPU and storage metrics ramped
smoothly. No scale events. Peak storage CPU ~70 %, T_db ~27 ms, T_proc ~3 ms.

**compute_spike (23:12 – 23:17) — instability window:**

Scale-up triggered on both LANs at ~23:13:36–23:13:38 after the degradation
score exceeded τ=0.85 for 3 of 5 windows. However the time between the first
visible degradation (~23:12:08, score=0.35) and the trigger (~23:13:38) was
**90 seconds**, during which the system accumulated severe backpressure:

- lan1 `edge_server_n1` hit CPU 91 % and **stopped sending telemetry** at
  23:13:58 (`server_count=0` in CSV).
- First client errors appeared at 23:13:49 (HTTP 0 = connection timeout, then
  HTTP 503 = server overloaded).
- Newly spawned nodes took 10–31 s to boot; during this time the scale-down
  evaluator saw them as idle and removed them within ~60–120 s.

**Error breakdown (compute_spike phase only):**

| Metric | Value |
|--------|-------|
| Total requests | 7 511 |
| HTTP 503 errors | 5 352 |
| Connection timeouts (HTTP 0) | 63 |
| Error rate | 72 % |
| lan1 share of errors | 80 % |
| Error window | 23:13:49 – 23:17:49 (~4 min) |

**sustained_plateau (23:17 – 23:20):**
System recovered. 5 233 requests, 1 487 errors (503, all on lan2, early in
phase while lan2 was still recovering from failed storage scale-down).
Latency returned to normal by 23:18:09.

**demand_drop (23:20 – 23:21):**
Clean wind-down. 1 078 requests, 0 errors. Both LANs at 1 server + 1 storage.

### Root Causes of Instability

Three interacting issues caused the thrashing — detailed analysis with code
snippets and proposed fixes documented in
[`elasticity_overview.md` § Known Issues](../elasticy_manager/elasticity_overview.md#known-issues--scale-up--scale-down-thrashing-2026-04-11-run):

1. **No scale-down grace period after scale-up** — newly spawned nodes were
   evaluated for underutilization before they could start serving traffic.
2. **Scale-up threshold too high / too slow** — τ=0.85 with 3-of-5 triggered
   90 s after the first sign of degradation, by which time the system was
   already failing.
3. **Absent-node detection counts boot time** — nodes in RS-join or container
   boot counted as "absent", contributing to premature scale-down.

### Telemetry vs CSV Discrepancies

`resource_stats.csv` reported `server_count=0` or `storage_count=0` during
periods when the nodes were still reachable via VIP routing. This is expected:
the CSV counts nodes that *emitted telemetry* in the aggregation window, while
the VIP pool tracks nodes registered via `add_server_mac()`.
See [`elasticity_overview.md` § Telemetry vs VIP Pool Discrepancy](../elasticy_manager/elasticity_overview.md#telemetry-vs-vip-pool-discrepancy)
for details.

---

## File Layout

```
docs/operation/testing/
├── testing_overview.md              ← this file
├── testing_workloads.md             ← workload design & phase definitions
├── traffic_generator_plan.md        ← traffic generator implementation plan
├── edge_server_compute_load_plan.md ← compute.py & app.py changes
└── trace_request_plan.md            ← trace_request.sh implementation plan
```
