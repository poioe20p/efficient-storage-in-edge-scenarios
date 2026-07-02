# Testing - Overview

## Purpose

The testing subsystem validates the platform's elastic behavior -- compute
scale-out, data-gravity-driven storage adaptation, Tier 1 selective sync, and
WSM-based load balancing -- under controlled, reproducible workload
conditions.

The current active workload is a content-discovery application. It uses the
runtime paths already implemented in the edge server, the canonical phase
profile in `source/scripts/testing/phases.json`, and the current operator
interfaces exposed by `source/scripts/Makefile` and
`source/scripts/testing/run_experiment.sh`.

---

## Experiment Operator Workflow

For long VM-backed experiment campaigns, use the custom agent
[`experiment-runner-edge.agent.md`](../../../.github/agents/experiment-runner-edge.agent.md)
together with the durable campaign brief
[`experiment_campaign_brief.md`](experiment_campaign_brief.md).

1. State the campaign objective, intended run delta, live checkpoint plan, and
   any allowed between-run edit scope.
2. Sync any required local changes to `cloud-vm`, launch from
   `~/efficient-storage-in-edge-scenarios`, and treat any interactive `sudo`
   prompt as a configuration failure.
3. During the run, perform only the predeclared read-only checks against the
   active run folder unless the plan explicitly allows snapshot-based analysis.
4. After completion, copy the run folder back locally unless the plan says
   otherwise, then decide whether remote cleanup is allowed.

---

## Architecture: Experiment Data Flow

```text
  seed_content_items.py  -> MongoDB (seed)
  seed_user_profiles.py  -> MongoDB (seed)
  create_indexes.py      -> MongoDB (indexes)
           |
           v
  export_workload_snapshot.py -> data/workload_snapshot/
                                   |- content_items.json
                                   `- user_profiles.json
                                              |
           .----------------------------------'
           v
  traffic_generator.py             phases.json (canonical 6-phase profile)
    |- reads snapshot + phases     ----------------------------------------
    |- spawns async tasks              baseline -> storage_storm
    |  per client namespace            -> tier1_hotspot -> inter_hotspot_cooldown
    |  (ip netns exec curl)            -> compute_spike -> cooldown
    `- writes CSV metrics
           |
           v
  metrics/client_requests.csv  <- aggregate rows with a `phase` column
```

The canonical profile keeps one workload family but changes which request kind
dominates each phase. The storage-heavy phases also inject `content_update` and
`content_aggregate` so MongoDB-side work is visible without inventing a second
application.

`trace_request.sh` can be used at any time to fire a single request and collect
a formatted trace of every hop: VIP server routing, edge-server processing, and
VIP data routing.

---

## Standard Run Artifact Contract

After a completed experiment run, the run directory contains these default
artifacts:

| # | Artifact | Source | Purpose |
| --- | --- | --- | --- |
| 1 | `client_requests.csv` | `traffic_generator.py` | Aggregate per-request latency CSV |
| 2 | `resource_stats.csv` | `collect_resource_stats.py` | Trimmed domain metrics for elasticity reasoning |
| 3 | `resource_stats_debug.csv` | `collect_resource_stats.py` | Broad diagnostic domain metrics |
| 4 | `policy_state.csv` | `reconstruct_policy_state.py` | Reconstructed per-window per-LAN policy state |
| 5 | `per_node_stats.csv` | `collect_resource_stats.py` | Per-container per-window metrics |
| 6 | `container_events.csv` | `poll_container_events.py` | Docker container lifecycle events |
| 7 | `elasticity_events.csv` | `parse_elasticity_logs.py` | Parsed controller log events |
| 8 | `controller_lan1.log` | `docker logs -f osken` | Raw SDN controller log for LAN 1 |
| 9 | `controller_lan2.log` | `docker logs -f osken_2` | Raw SDN controller log for LAN 2 |
| 10 | `controller_env_snapshot.env` | captured from the running controller | Exact thresholds, weights, cooldowns, and caps used by the run |
| 11 | `phases_snapshot.json` | copied from phases config | Phase configuration used for the run |
| 12 | `service_logs/` | `capture_service_logs.py` | Edge and storage container logs during the run |

The single aggregate `client_requests.csv` remains the default contract; the
`phase` column is the source of phase-scoped request analysis.

---

## Golden Configuration

The canonical workload sizing, mechanism toggles, and trigger thresholds that
exercise the current architecture are documented in
[`golden_config.md`](golden_config.md).

All current values are encoded in
[`current_state_integrated.env`](../../../source/scripts/testing/controller_env_overrides/current_state_integrated.env).

Canonical launch:

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  OSKEN_ENV_OVERRIDE_FILE=testing/controller_env_overrides/current_state_integrated.env \
  RUN_LABEL=<label> \
  PHASES_CONFIG=testing/phases.json \
  WAN_RTT_MS=260 CLIENTS=48 CONTENT_ITEMS=6000 USERS=100 STORAGE_CPUS=0.10 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

The canonical active phase profile is always `testing/phases.json`. Focused
diagnostic or smoke profiles live under `testing/phases_override/`.

---

## Client-Facing Workload Requests

The active read-path narrative is deliberately simple. Test clients primarily
exercise three request types through `VIP_SERVER` to the edge-server service.

| Request type | Endpoint | Purpose | Main pressure created |
| --- | --- | --- | --- |
| `content_lookup` | `/content/<content_id>?requester=<user_id>` | Fetch one content item for one requester, enrich it with requester-specific relevance context, and compute a short trend. | Storage-locality pressure via targeted reads to `content_items` and `user_profiles` |
| `service_pressure` | `/service_pressure?window_min=<minutes>&limit=<N>` | Ask one edge server how much recent demand it has been under by summarizing its local in-memory request buffer. | Edge-local CPU pressure from local analytics, with no synchronous MongoDB read/write path |
| `feed_ranking` | `/feed/<user_id>?limit=<N>` | Return a ranked set of relevant content for one user profile. | Compute pressure from multi-LAN reads, scoring, sorting, and summary work |

Useful shorthand:

- `content_lookup` = one-content lookup and the primary storage-oriented path
- `feed_ranking` = ranked feed generation and the primary compute-oriented path
- `service_pressure` = edge-local introspection over recent request activity

The canonical phase profile also uses two auxiliary generator-driven request
types in storage-heavy windows:

- `content_update` for write amplification
- `content_aggregate` for aggregation-heavy storage work

These two POST routes are real runtime paths, but they are auxiliary to the
three-route read-path story above.

---

## Components

### 1. Workload Design - [`testing_workloads.md`](testing_workloads.md)

Defines the content-discovery workload, its collections, support state,
request types, and canonical/override phase profiles.

### 2. Traffic Generator - [`traffic_generator.md`](traffic_generator.md)

Documents `export_workload_snapshot.py`, `traffic_generator.py`, the canonical
6-phase profile in `phases.json`, and the validation/diagnostic overrides in
`phases_override/`.

### 3. Edge Server Compute Load - [`edge_server_compute_load.md`](edge_server_compute_load.md)

Explains the implemented compute paths that make `T_proc` non-trivial:
content relevance scoring, feed ranking, feed integrity verification, trend
analysis, and local service-pressure summaries.

### 4. Request Trace - [`trace_request.md`](trace_request.md)

Documents a debugging and demonstration script that traces one request
end-to-end through VIP routing and edge-server processing.

### 5. Run Analysis Toolchain - [`analysis_toolchain.md`](analysis_toolchain.md)

Documents the offline analysis CLIs that ingest one run directory and emit
phase-aligned plots, summaries, and diagnostic tables.

---

## Execution Order

```bash
# 1. Seed data with the current live interface
make -C source/scripts setup_test_data CONTENT_ITEMS=100 USERS=40

# 2. Create namespace-based test clients if they do not already exist
sudo bash source/scripts/network/clients/create_test_clients.sh --lan 1 --count 3
sudo bash source/scripts/network/clients/create_test_clients.sh --lan 2 --count 3

# 3. Run the canonical experiment profile
sudo -n make -C source/scripts run_experiment \
  RUN_LABEL=demo_content_profile \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=3 CONTENT_ITEMS=100 USERS=40 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1

# 4. Generate analysis artifacts from the run directory
python -m source.scripts.testing.analysis.cli_overview --run-dir source/scripts/testing/metrics/<ts>
python -m source.scripts.testing.analysis.cli_cpu_drivers --run-dir source/scripts/testing/metrics/<ts>

# 5. Trace a single request for debugging
sudo bash source/scripts/testing/trace_request.sh \
  --ns lan1_client_1 \
  -- curl -s "http://10.0.0.253:5000/content/lan1::content::001?requester=lan1::user::001"
```

---

## What The Experiments Prove

| # | Claim | How the current workload demonstrates it |
| --- | --- | --- |
| 1 | Storage deploys only when justified | `storage_storm` and `tier1_hotspot` create the sustained storage-side and cross-region pressure needed for activation |
| 2 | Tier 1 reacts to concentrated hotspots | `tier1_hotspot` and the focused Tier 1 override exercise concentrated cross-region point reads |
| 3 | Compute scales independently of storage | `compute_spike` pushes `feed_ranking` work while keeping cross-region pressure low |
| 4 | Load distributes via WSM | Per-server request counts and CPU utilization converge after scale-out |
| 5 | Resources are reclaimed after pressure falls | `inter_hotspot_cooldown` and `cooldown` expose cooldown-gated drain and scale-in behavior |

### Focused Companion Profiles

- Tier 1 smoke profile:
  `source/scripts/testing/phases_override/phases_tier1_smoke.json`
  Use this when the question is whether Tier 1 activates and drains cleanly in
  both directions under a short hotspot profile.
- Short verification profile:
  `source/scripts/testing/phases_override/phases_rq1_verify.json`
  Use this when you need a shorter end-to-end verification run that still
  exercises storage and compute shifts.
- Mini smoke profile:
  `source/scripts/testing/phases_override/phases_mini.json`
  Use this for minimal wiring checks.

The canonical active integrated profile is `source/scripts/testing/phases.json`.
