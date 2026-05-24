# Testing — Overview

## Purpose

The testing subsystem validates the platform's elastic behavior — compute
scale-out, data-gravity-driven storage replication, and WSM-based load
balancing — under controlled, reproducible workload conditions. It provides the
tooling needed to seed data, generate phased HTTP traffic, add realistic CPU
work to edge server endpoints, and trace individual requests through the full
VIP routing pipeline.

The standard experiment bringup is a self-contained single-host lab: it does
not require outbound Internet access, inbound Internet access, or a specific
physical host NIC assignment before `make setup_network` runs.

## Experiment Operator Workflow

For long VM-backed experiment campaigns, use the custom agent
[`experiment-runner-edge.agent.md`](../../../.github/agents/experiment-runner-edge.agent.md)
together with the durable campaign brief
[`experiment_campaign_brief.md`](experiment_campaign_brief.md).

1. State the campaign objective, the intended run delta, the live checkpoint
  plan, and any allowed between-run edit scope.
2. The default execution host is the cloud VM. The agent enters it with
  `ssh cloud-vm`, changes to `~/efficient-storage-in-edge-scenarios`, syncs
  any required local changes with `scp`, `rsync`, or a similar tool when
  needed, launches the experiment with `sudo -n`, and treats any interactive
  sudo prompt as a configuration failure instead of waiting for user input.
3. During the run, the agent performs only the predeclared read-only checks
  against the active run folder unless the live plan explicitly allows
  snapshot-based analysis outside that folder.
4. If the campaign brief defines stop or restart criteria, the agent may halt
  or relaunch the run when the observed evidence matches those criteria.
5. After the run, if controller logs are no longer needed, the agent follows
  the repository summary workflow from
  [`metrics-run-summary`](../../../.github/skills/metrics-run-summary/SKILL.md)
  on the cloud VM first so the folder is reduced before transfer.
6. Unless instructed otherwise, after every completed cloud run the agent then
  copies the remaining run folder back to the local host with `scp` or a
  similar transfer tool and deletes the remote run folder after the local copy
  is verified.
7. If controller logs still need to be preserved, the agent copies the full run
  folder first or postpones remote cleanup, then updates the campaign brief
  before any next run.

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
  traffic_generator.py              phases.json (9-phase config)
    ├─ reads snapshot + phases      ──────────────────────────────
    ├─ spawns async tasks                baseline → local_moderate → storage_stress
    │   per client namespace             → cross_region_hotspot → reverse_hotspot
    │   (ip netns exec curl)             → compute_ramp → compute_spike
    └─ writes CSV metrics                → sustained_plateau → demand_drop
         │
         ▼
  metrics/client_requests.csv    ←── aggregate rows across the full run, with a
                                   `phase` column for phase-scoped analysis
```

Separately, `trace_request.sh` can be used at any time to fire a single request
and collect a formatted trace of every hop (VIP\_SERVER routing → edge server →
VIP\_DATA routing → storage node).

---

## Client-Facing Workload Requests

The active client workload is deliberately simple and effectively read-only.
Test clients do not perform ordinary online MongoDB writes. Instead they send
three HTTP GET request types through `VIP_SERVER` to the edge-server service,
and each request type exists to stress a different part of the architecture.

| Request type | Endpoint | Purpose | Main pressure created |
| --- | --- | --- | --- |
| `device_status` | `/device/<device_id>/latest?node_id=<node_id>` | Fetch the latest state of one device for a monitoring node, enrich it with node-specific threshold overrides, compute severity, and derive a short local trend. | Storage-locality pressure via targeted reads to `sensor_reports` and `device_registry` |
| `service_pressure` | `/service_pressure?window_min=<minutes>&limit=<N>` | Ask one edge server how much recent demand it has been under by summarizing its local in-memory request buffer. | Edge-local CPU pressure from local analytics, with no synchronous MongoDB read/write path |
| `dashboard` | `/dashboard/<node_id>?limit=<N>` | Return a ranked overview of the most urgent devices relevant to one monitoring node. | Compute pressure from multi-LAN reads, urgency scoring, sorting, and fleet summarization |

Useful shorthand:

- `device_status` = one-device lookup and the primary storage-oriented request
- `dashboard` = many-device ranked overview and the primary compute-oriented request
- `service_pressure` = edge-server introspection over recent local request activity

These are the only client-facing workload requests in the current testing
model. Other HTTP routes exposed by the edge server belong to the control
plane or test harness, not to the normal client mix.

---

## Components

### 1. Workload Design — [`testing_workloads.md`](testing_workloads.md)

Defines the experimental workload: a multi-region IoT edge monitoring platform
with 2 MongoDB collections (`sensor_reports`, `device_registry`), 1 bounded
edge-local support-state buffer (`local_request_activity`), and 3 edge server
endpoints (`/device/<id>/latest`, `/service_pressure`, `/dashboard/<node_id>`).

Key decisions:

- **Read-heavy, metadata-rich** workload that justifies MongoDB beyond simple
  replication (flexible schema, array queries, secondary reads, and
  application-side enrichment from heterogeneous documents) while keeping
  support-state analytics local to the edge server.
- **Request-scoped local pressure accounting** that records both
  `device_status` and `dashboard` demand in the edge-local buffer, computes
  Tier 1 hit ratio from actual Tier 1-eligible point reads, and surfaces
  truncation explicitly if the in-memory safety cap is reached.
- **9-phase two-regime demand progression** that separates storage-locality
  pressure from compute-analytics pressure: `storage_stress` acts as a Tier 2
  buildup window, `cross_region_hotspot` and `reverse_hotspot` are long
  post-trigger observation phases, the compute phases are intentionally
  dashboard-dominant while keeping cross-region traffic low, and `demand_drop`
  is long enough to expose cooldown-gated scale-in.
- **Measurable outcomes**: time-to-replica, latency reduction after tier
  escalation, CPU distribution after scale-out, resource reclamation timing.

### 2. Traffic Generator — [`traffic_generator.md`](traffic_generator.md)

Current reference for the client-side experiment driver.

| Script | Purpose |
|---|---|
| `export_workload_snapshot.py` | Pre-exports device/node data from MongoDB to JSON — decouples traffic generation from live DB access |
| `traffic_generator.py` | Async Python script: phases × clients → `curl` inside network namespaces through `VIP_SERVER` |
| `phases.json` | Declarative 9-phase config (duration, rate, cross-region ratio, request mix) |

The shared runner [`run_experiment.sh`](../../../source/scripts/testing/run_experiment.sh)
accepts `--phases-config <file>` for short targeted-validation recipes and can
also accept an optional `--fault-plan <file>` for separate synthetic-failure
campaigns. The hybrid recovery-validation runs described here use only the
phase override and do not pass `--fault-plan`.

When old run folders on `cloud-vm` need to be reclaimed, use the approved
cleanup path `sudo -n make -C source/scripts cleanup_metrics`. That target
removes only run directories directly under `source/scripts/testing/metrics/`.

Output: aggregate `metrics/client_requests.csv` with per-request timestamp,
phase, endpoint, target region, HTTP status, and latency. Phase-scoped
analysis is derived from the `phase` column in that aggregate file.

Current default schedule: `baseline` 60 s, `local_moderate` 90 s,
`storage_stress` 240 s, `cross_region_hotspot` 300 s,
`reverse_hotspot` 300 s, `compute_ramp` 120 s, `compute_spike` 150 s,
`sustained_plateau` 120 s, `demand_drop` 300 s. Total duration: about
28 minutes. Interpret this as one application with two regimes: storage phases
are `device_status`-dominant, while compute phases are `dashboard`-dominant.

### 3. Edge Server Compute Load — [`edge_server_compute_load.md`](edge_server_compute_load.md)

Current reference for the implemented edge-server CPU work that makes the
endpoints produce meaningful CPU work so that $T_{proc} = T_{total} - T_{dados}$
is non-trivial.

| Endpoint | Added Compute | $T_{proc}$ Impact |
|---|---|---|
| `/device/<id>/latest` | Multi-level severity scoring + linear regression trend analysis | ~5–15 ms |
| `/service_pressure` | Local pressure summary, concentration scoring, and tag/device ranking | ~3–10 ms |
| `/dashboard/<node_id>` | Multi-factor urgency scoring (tag priority, staleness decay) + fleet summary stats | ~5–20 ms |

All compute is implemented in a pure-stdlib module (`compute.py`) with no I/O
dependencies — execution time flows entirely into $T_{proc}$.

### 4. Request Trace — [`trace_request.md`](trace_request.md)

Current reference for a debugging/demonstration script that traces a single
request end-to-end through the platform.

```
CLIENT (namespace) → VIP_SERVER (SDN selects edge server)
                   → Edge Server (HTTP + MongoDB via VIP_DATA)
                   → VIP_DATA (SDN selects storage node)
                   → Response back to client
```

Collects `docker logs` from controllers and edge servers within the request's
time window and formats a color-coded trace showing each routing decision.

### 5. Run Analysis Toolchain — [`analysis_toolchain.md`](analysis_toolchain.md)

Offline package that ingests a run directory and emits phase-aligned plots and
diagnostic tables. Read-only — does not modify telemetry, scaling, or the
traffic generator.

| CLI | Purpose |
|---|---|
| `cli_overview` | One-page dashboard: request rate, CPU, T_proc, T_db (read/write stacked), node counts with phase shading and elasticity-event overlays |
| `cli_simple_run` | Simpler per-run plots: average latency, p95 latency, failure rate, total active nodes, and active nodes by type |
| `cli_simple_compare` | Simpler multi-run comparison plots: overall latency, failure rate, node-count summaries, and per-phase latency/failure comparisons |
| `cli_cpu_drivers` | Per-node CPU vs request-count; old-vs-new node CPU table to detect load-balance failures |
| `cli_scale_down` | Reconstructs the scale-down predicate from CSV and cross-checks against controller log lines |
| `cli_tdb_drivers` | OLS regression `T_db_write ~ a + b·storage_count + c·cross_region_ratio` to falsify the "more storage = slower writes" hypothesis |

Consumes `resource_stats.csv` (domain), `per_node_stats.csv` (per-container),
`client_requests.csv`, `container_events.csv`, `phases_snapshot.json`, and the
controller log files. Phase-scoped latency and failure analysis is derived
from the aggregate request CSV via its `phase` column. Missing fields on older
runs degrade gracefully with warnings.

The analysis package now also includes
[`cli_recovery_validation.py`](../../../source/scripts/testing/analysis/cli_recovery_validation.py),
which summarizes request-lease outcome logs and controller
recovery-avoidance markers, and can optionally correlate those with explicit
fault events when a separate synthetic-failure workflow uses them.

### 5a. Hybrid Recovery Validation — [`experiment_hybrid_recovery_validation.md`](experiment_hybrid_recovery_validation.md)

Current reference for the hybrid run family that validates the MongoDB
request-lease state machine and observes controller failed-backend avoidance
signals with two short targeted runs before reusing the standard long-cycle
workload for broader architecture observation.

This run family adds:

- one targeted `n1` validation recipe and one targeted `n2` recipe via
  `--phases-config`;
- a focused offline summary through
  [`cli_recovery_validation.py`](../../../source/scripts/testing/analysis/cli_recovery_validation.py);
- no synthetic backend stop or injected-fault artifact; the runs are pure
  workload observations;
- an image-rebuild gate: host-side harness and controller-script changes do
  not require image rebuilds, but a stale `edge_server` image still must be
  rebuilt before execution if the request-lease implementation in the remote
  image is uncertain.

### 6. Ablation Batch Results — [`elasticity_ablation_batch1_results.md`](elasticity_ablation_batch1_results.md)

Records the first completed `C0-C4` comparison batch for the elasticity
ablation matrix. It synthesizes the per-run summaries into mechanism-level
findings for Tier 1, Tier 2, compute elasticity, and overall run health, and
serves as the stable Batch 1 reference if later reruns are produced.

### 7. Ablation Batch 2 Results — [`elasticity_ablation_batch2_results.md`](elasticity_ablation_batch2_results.md)

Records the long-cycle rerun of the same `C0-C4` matrix. It compares the second
batch against Batch 1 and captures the key reversal in the results: Tier 2
becomes the strongest positive mechanism once the storage-sensitive phases are
long enough, while Tier 1 and the combined Tier 1 plus Tier 2 path remain
defect-prone in the rerun artifacts.

### 8. Ablation Batch 5 Results — [`elasticity_ablation_batch5_results.md`](elasticity_ablation_batch5_results.md)

Records the completed normal-workload validation batch for the post-Batch-4
elasticity changes. It compares the static, storage-only, combined, and full
policy rows under the unchanged standard workload and captures the resulting
Tier 1, Tier 2, and compute-elasticity evidence.

#### `resource_stats.csv` — Tier 1 columns

The collector ([`collect_resource_stats.py`](../../../source/scripts/testing/collect_resource_stats.py)) appends 16 Tier 1 observability columns derived by [`tier1_stats.py`](../../../source/scripts/testing/tier1_stats.py). The first eleven come from each aggregator's `TelemetrySummary`; the last five from the controller's coordinator-state PUB ([`state_publisher.py`](../../../source/sdn_controller/selective_sync/state_publisher.py)).

| Column | Source | Maps to |
|---|---|---|
| `total_reads` | `op_counters` (find + find_one) | Workload denominator |
| `cross_region_reads` | `access[*].cross_region_hits` | Footprint numerator |
| `cross_region_ratio` | derived (Σ over all owner_lans/colls) | Aggregate read mix; **diluted** by same-region collections — diagnostic only |
| `max_per_owner_coll_xratio` | max of `cross_region_hits / total_hits` over `(owner_lan, coll)` | Mirrors the actual `SS_PROMOTION_CROSS_REGION_THRESHOLD` gate |
| `t_db_p95_ms_owner_lan` | max of `t_db_p95_ms_per_lan[my_lan]` | Local p95 |
| `t_db_p95_ms_peer_lan` | max of `t_db_p95_ms_per_lan[peer_lan]` | Drives breach gate (`TAU_DADOS_MS`) |
| `top_hot_doc_hits` | max over `access[*].top_docs` | Hottest single doc |
| `tier1_active_count` | storage_servers with non-null `selective_sync_per_collection` | Tier 1 supply count |
| `avg_tier1_lag_s` | mean of forwarder `lag_s` | Replication freshness |
| `max_tier1_resume_token_age_s` | max of `resume_token_age_s` | Change Stream health |
| `tier1_hot_doc_total` | sum of `hot_doc_count` | Footprint size |
| `coord_state_owner_lan` | `Tier1OwnerState.state` | NONE / SPAWNING / ACTIVE / DRAINING |
| `coord_breach_fill_pct` | `breach_ring_filled / capacity * 100` | M-of-N progress toward firing |
| `coord_cooldown_remaining_s` | `Tier1OwnerState.cooldown_remaining_s` | Why a re-promotion is suppressed |
| `coord_hot_doc_total` | `Tier1OwnerState.hot_doc_total` | Hot set size held by coordinator |
| `tier1_lifecycle_active_count` | derived from `coord_state_owner_lan == ACTIVE` | Tier 1 lifecycle truth for ACTIVE windows |

`tier1_active_count` is intentionally a supply-side reporting metric, not a lifecycle truth signal: quiet Tier 1 windows can keep it at `0` even when the coordinator state is `ACTIVE`. Use `tier1_lifecycle_active_count` or `coord_state_owner_lan` when the question is whether Tier 1 actually reached service.

Empty/baseline rows (no telemetry, `SS_ENABLED=0`) yield zeros and `coord_state_owner_lan="NONE"`.

#### `container_events.csv` — container life-cycle audit

A second background process, [`poll_container_events.py`](../../../source/scripts/testing/poll_container_events.py), runs `docker ps -a` once per second and emits a CSV row whenever a tracked container appears, disappears, or changes state. This is the authoritative ground truth for *what was actually running* during the experiment — independent of telemetry liveness, controller logs, or scaling decisions; it also captures crashes and Docker-restart loops the other artifacts miss.

Default name filter: `^(edge_|sel_sync_|nat-router|osken|local_state_)` (override with `CONTAINER_EVENTS_FILTER` / `CONTAINER_EVENTS_INTERVAL` before invoking [`run_experiment.sh`](../../../source/scripts/testing/run_experiment.sh)). This includes Tier 1 selective-sync containers (`sel_sync_*`) alongside the existing compute, storage, controller, and router containers. Namespace-based test clients are created separately and are not visible to the `docker ps` poller.

| Column | Meaning |
|---|---|
| `timestamp_iso` | Wall-clock time of the diff (UTC, millisecond precision) |
| `monotonic_s` | Seconds since the poller started — robust to wall-clock skew |
| `phase` | Current workload phase from `current_phase.txt` (same source as `resource_stats.csv`) |
| `event` | `initial` (first tick), `added`, `removed`, `state_change`, or `final` (shutdown snapshot) |
| `container` | Container name, e.g. `edge_server_lan1_dyn1` |
| `image` | Image tag from `docker ps` |
| `state` / `status` | Docker `State` (e.g. `running`, `exited`) and `Status` (e.g. `Up 12 minutes`) |
| `prev_state` | Previous `State` for `state_change` and `removed` rows; empty otherwise |
| `container_id` | Full container ID (useful for cross-referencing `docker inspect`) |

Lifetime reconstruction: a container's lifetime begins at its first `initial` or `added` row and ends at the matching `removed` row (or the trailing `final` row if it was still up at shutdown).

---

## Execution Order

> **Prerequisite — WAN emulation.** Tier 1 experiments rely on the breach gate
> `t_db_p95_ms_peer_lan ≥ TAU_DADOS_MS` (default `65 ms`). Without inter-LAN
> latency injection the raw veth path measures ~5–15 ms and the gate never
> fires. The bringup applies the `metro` profile (`WAN_RTT_MS=10`) by default;
> override per run via [`source/scripts/wan.env`](../../../source/scripts/wan.env)
> This is internal latency emulation on the host lab topology, not an external
> Internet uplink requirement.
> or at runtime with [`wan_set.sh`](../../../source/scripts/tools/wan_set.sh).
> See [Topology — WAN Emulation](../topology/topology_overview.md#wan-emulation-inter-lan-latency)
> for the four available profiles.

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

# 5. Generate analysis artifacts from the run directory
python -m source.scripts.testing.analysis.cli_overview    --run-dir metrics/<ts>
python -m source.scripts.testing.analysis.cli_cpu_drivers --run-dir metrics/<ts>
python -m source.scripts.testing.analysis.cli_scale_down  --run-dir metrics/<ts>
python -m source.scripts.testing.analysis.cli_tdb_drivers --run-dir metrics/<ts>

# (optional) Trace a single request for debugging
sudo bash source/scripts/testing/trace_request.sh \
  --ns lan1_client_1 \
  -- curl -s "http://10.0.0.100:5000/device/lan1::device::001/latest?node_id=lan1::node::001"
```

---

## What the Experiments Prove

| # | Claim | How It Is Demonstrated |
|---|---|---|
| 1 | Storage deploys only when justified | `storage_stress` provides the buildup window, while `cross_region_hotspot` and `reverse_hotspot` provide long post-trigger observation windows that should justify and then measure storage expansion |
| 2 | Compute scales independently of storage | `compute_ramp`, `compute_spike`, and `sustained_plateau` reduce cross-region demand and instead push higher local request rates |
| 3 | Load distributes via WSM | Per-server request counts and CPU utilization converge after scale-out |
| 4 | Latency recovers after scaling | $T_{total}$ returns toward baseline once new resources are active |
| 5 | Resources are reclaimed on demand drop | `demand_drop` deliberately lasts long enough to observe the over-provisioned state through cooldown and, when enabled, should trigger scale-in |

### Planned — `tier1_hotspot` scenario

A new workload phase targeting the Tier 1 selective-sync path. Design:

- Pin a small subset of documents (e.g. 30 hot device ids on LAN 1) and
  generate sustained cross-region read traffic from LAN 2 clients with a
  write ratio below `SS_WRITE_RATIO_MAX` and read count above
  `SS_MIN_READS_PER_WINDOW`.
- Run with `SS_ENABLED=1` and again with `SS_ENABLED=0` as the control.
- Measure: per-LAN `T_db` p95 across the ramp, the timestamp of
  `SelectiveSyncAlert` emission, manifest broadcast latency, and Change
  Stream `lag_s` throughout the `ACTIVE` window. The expected signature is a
  `T_db`-p95 drop on LAN 2 within ~1–2 telemetry windows after promotion.
- Teardown path is exercised by tailing off the hotspot below
  `SS_SCALEDOWN_THRESHOLD` for `SS_SCALEDOWN_WINDOW` consecutive windows and
  asserting a single `ScaleDownSelectiveAlert` (Phase A) followed by
  `CleanupSelectiveAlert` (Phase B) on `drain_complete`.

Overview docs: [`selective_sync/selective_sync_overview.md`](../selective_sync/selective_sync_overview.md).

---

## Experiment Results — Run `20260411_235936`

### Summary

Full 9-phase workload (baseline → local_moderate → storage_stress →
cross_region_hotspot → reverse_hotspot → compute_ramp → compute_spike →
sustained_plateau → demand_drop) using the shorter pre-Batch 2 schedule.
Total duration ~22 min.

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
├── traffic_generator.md             ← traffic generator reference
├── edge_server_compute_load.md      ← compute.py & app.py changes
├── trace_request.md                 ← trace_request.sh reference
├── analysis_toolchain.md            ← offline run analysis package
├── elasticity_ablation_batch*_results.md
└── experiment_campaign_brief.md     ← campaign record and operator workflow

docs/operation/archive/testing/
├── elasticity_ablation_batch4_plan.md
└── elasticity_ablation_batch5_plan.md

source/scripts/testing/
├── collect_resource_stats.py    ← now also writes per_node_stats.csv
└── analysis/                    ← NEW — offline analysis package
    ├── __init__.py
    ├── loader.py
    ├── events.py
    ├── phase_window.py
    ├── plots.py
    ├── cli_overview.py
    ├── cli_cpu_drivers.py
    ├── cli_scale_down.py
    ├── cli_tdb_drivers.py
    └── requirements.txt
```
