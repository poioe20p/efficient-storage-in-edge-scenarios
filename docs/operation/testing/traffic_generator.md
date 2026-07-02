# Traffic Generator

This document describes the generator that drives the current content-discovery
testing workload. The runtime routes already exist in
`source/docker/edge_server/source/monitoring_workload_routes.py`; the scripts
here decide how phase timing, request mix, and client namespaces are combined.

The canonical active profile is `source/scripts/testing/phases.json`. Shorter
validation and diagnostic profiles live under
`source/scripts/testing/phases_override/`.

---

## Workload Request Types

The generator currently supports five request kinds.

| Request type | Endpoint shape | Purpose |
| --- | --- | --- |
| `content_lookup` | `/content/<content_id>?requester=<user_id>` | Primary cross-region point-read driver |
| `feed_ranking` | `/feed/<user_id>?limit=<N>` | Primary edge-compute driver |
| `service_pressure` | `/service_pressure?window_min=<minutes>&limit=<N>` | Local support-state introspection |
| `content_update` | `POST /content` | Storage write amplification and oplog traffic |
| `content_aggregate` | `POST /content/aggregate` | Collection-level aggregation work through `VIP_DATA` |

`content_lookup`, `feed_ranking`, and `service_pressure` are the public
workload-facing routes. `content_update` and `content_aggregate` are auxiliary
generator operations used by the storage-heavy phase mixes in the canonical
profile.

---

## Overview

Core scripts:

| Script | Purpose |
| --- | --- |
| `export_workload_snapshot.py` | Export minimal `content_items` and `user_profiles` data to JSON so traffic generation is decoupled from a live database scan |
| `traffic_generator.py` | Send phased HTTP traffic from namespace-based clients through `VIP_SERVER` |
| `run_experiment.sh` | Wrap setup, optional reseeding, snapshot export, metrics capture, and traffic generation |

Phase config files:

| File | Role |
| --- | --- |
| `phases.json` | Canonical active 6-phase workload profile |
| `phases_override/phases_tier1_smoke.json` | Focused Tier 1 hotspot validation |
| `phases_override/phases_rq1_verify.json` | Short verification profile |
| `phases_override/phases_mini.json` | Minimal smoke profile |

---

## Current Live Interfaces

The current operator-facing interfaces already use content/user naming.

### Seeding

```bash
make -C source/scripts setup_test_data CONTENT_ITEMS=600 USERS=100
```

This expands to:

- `testing/seed_content_items.py --content-items <N>`
- `testing/seed_user_profiles.py --content-items <N> --users <N>`
- `testing/create_indexes.py`
- `testing/export_workload_snapshot.py`

### Full experiment launch

```bash
sudo -n make -C source/scripts setup_network create_clients setup_test_data run_experiment \
  RUN_LABEL=<label> \
  PHASES_CONFIG=testing/phases.json \
  CLIENTS=6 CONTENT_ITEMS=600 USERS=100 \
  SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1
```

`make run_experiment` forwards `CLIENTS`, `CONTENT_ITEMS`, and `USERS` to the
underlying `run_experiment.sh` flags `--clients-per-lan`,
`--seed-content-items`, and `--seed-users`.

---

## Phase Schema

Each phase object supports:

| Field | Type | Meaning |
| --- | --- | --- |
| `name` | string | Phase identifier written into `client_requests.csv` |
| `duration_s` | int | Phase length in seconds |
| `rate_per_client` | float | Requests per second for each active client namespace |
| `cross_region_ratio` | float | Fraction of `content_lookup` requests that target the foreign LAN |
| `hotspot_direction` | string | Which LAN emits those cross-region `content_lookup` requests |
| `mix` | dict | Weighted request distribution across the supported request kinds |
| `client_fraction` | float | Fraction of all clients that are active during the phase |

Important behavior:

- `cross_region_ratio` applies only to `content_lookup`.
- `feed_ranking` always targets the requester's home LAN but may read content
  candidates from all LANs.
- `content_update` writes to the requester's home LAN primary.
- `content_aggregate` runs a VIP-routed aggregation against the requester's
  home LAN.

---

## Prerequisites

Before running the generator, make sure the following are ready:

1. The network has been deployed.
2. Test data has been seeded with `content_items` and `user_profiles`.
3. A snapshot has been exported to `data/workload_snapshot/`.
4. Namespace-based test clients exist on both LANs.

Execution order:

```text
seed_content_items.py -> seed_user_profiles.py -> create_indexes.py
-> export_workload_snapshot.py -> traffic_generator.py
```

---

## Step 1 -- `export_workload_snapshot.py`

This script exports only the fields the generator needs.

### Export CLI

```bash
python3 source/scripts/testing/export_workload_snapshot.py \
  [--mongo-lan1 mongodb://10.0.0.4:27018/] \
  [--mongo-lan2 mongodb://10.0.1.4:27018/] \
  [--output-dir data/workload_snapshot]
```

### Output files

- `data/workload_snapshot/content_items.json`
  Minimal content-item identity data used for request targeting.
- `data/workload_snapshot/user_profiles.json`
  Minimal user-profile identity data used for requester and feed targeting.

Example shapes:

```json
[
  {"_id": "lan1::content::001", "region_origin": "lan1"},
  {"_id": "lan2::content::001", "region_origin": "lan2"}
]
```

```json
[
  {
    "_id": "lan1::user::001",
    "home_region": "lan1",
    "subscribed_tags": ["news", "technology"],
    "watched_content": ["lan1::content::002"]
  }
]
```

---

## Step 2 -- `phases.json`

The canonical active profile is the 6-phase schedule below.

| Phase | Duration | Rate/client | `cross_region_ratio` | Mix |
| --- | ---: | ---: | ---: | --- |
| `baseline` | 60 s | 1.0 | 0.00 | `content_lookup=0.60`, `feed_ranking=0.25`, `service_pressure=0.15` |
| `storage_storm` | 240 s | 4.0 | 0.90 | `content_lookup=0.35`, `feed_ranking=0.10`, `service_pressure=0.05`, `content_update=0.30`, `content_aggregate=0.20` |
| `tier1_hotspot` | 180 s | 5.0 | 0.95 | `content_lookup=0.80`, `feed_ranking=0.05`, `service_pressure=0.05`, `content_update=0.05`, `content_aggregate=0.05` |
| `inter_hotspot_cooldown` | 300 s | 1.0 | 0.00 | `content_lookup=0.60`, `feed_ranking=0.25`, `service_pressure=0.15` |
| `compute_spike` | 180 s | 4.0 | 0.05 | `content_lookup=0.20`, `feed_ranking=0.65`, `service_pressure=0.15` |
| `cooldown` | 120 s | 1.0 | 0.00 | `content_lookup=0.60`, `feed_ranking=0.25`, `service_pressure=0.15` |

Total duration: 1080 seconds, about 18 minutes.

Interpretation:

- `storage_storm` and `tier1_hotspot` are the storage-heavy phases.
- `compute_spike` is the compute-heavy phase.
- `inter_hotspot_cooldown` and `cooldown` provide recovery and scale-in
  observation windows.

---

## Step 3 -- `traffic_generator.py`

### Architecture

```text
traffic_generator.py
  reads phases.json + workload snapshot
  -> chooses request type from phase mix
  -> chooses content_id/user_id/target_region for that request
  -> executes curl from a client namespace through VIP_SERVER
  -> writes one row to metrics/client_requests.csv
```

### Generator CLI

```bash
sudo python3 source/scripts/testing/traffic_generator.py \
  --config source/scripts/testing/phases.json \
  --clients-lan1 lan1_client_1,lan1_client_2,lan1_client_3 \
  --clients-lan2 lan2_client_1,lan2_client_2,lan2_client_3 \
  --snapshot-dir data/workload_snapshot \
  --output metrics/client_requests.csv \
  [--vip 10.0.0.253:5000] \
  [--dry-run]
```

### Request construction details

- `content_lookup` builds `/content/<content_id>?requester=<user_id>`
- `feed_ranking` builds `/feed/<user_id>?limit=10`
- `service_pressure` builds `/service_pressure?window_min=10&limit=10`
- `content_update` sends `POST /content` with `content_id`, `engagement`,
  `lan`, and a 1 KB padding string to enlarge oplog entries
- `content_aggregate` sends `POST /content/aggregate` with `lan` and a random
  `engagement_threshold`

Unsupported request types fail fast with `ValueError`, which is why the Phase C
phase-file rename matters: the generator already expects the content/user names.

---

## Output Contract

The generator writes one aggregate CSV:

- `metrics/client_requests.csv`

Columns:

| Column | Meaning |
| --- | --- |
| `timestamp` | Wall-clock request timestamp |
| `phase` | Phase name from the config |
| `client_ns` | Namespace that sent the request |
| `client_lan` | LAN of that namespace |
| `endpoint` | Request type (`content_lookup`, `feed_ranking`, `service_pressure`, `content_update`, `content_aggregate`) |
| `content_id` | Target content item when applicable |
| `user_id` | Target requester when applicable |
| `target_region` | Region targeted by the request |
| `http_status` | Curl-reported HTTP status |
| `latency_s` | Request latency in seconds |

Phase-scoped analysis is derived from the `phase` column; separate per-phase
CSV files are not part of the default contract.

---

## Validation Overrides

Use the override profiles when you do not want the full canonical run:

- `testing/phases_override/phases_tier1_smoke.json`
  Focused Tier 1 hotspot validation with both directions.
- `testing/phases_override/phases_rq1_verify.json`
  Condensed verification profile for short checks.
- `testing/phases_override/phases_mini.json`
  Minimal smoke profile for wiring checks and quick turnaround.

These files are non-canonical helpers. `testing/phases.json` remains the sole
canonical active workload profile.
