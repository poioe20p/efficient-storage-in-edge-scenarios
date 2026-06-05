# Traffic Generator

This document describes the HTTP traffic generator that drives the current
9-phase long-cycle experiment described in
[testing_workloads.md](testing_workloads.md). All three edge server endpoints
(`/device/<id>/latest`, `/service_pressure`, `/dashboard/<node_id>`) are already
implemented in the [edge server](../../../source/docker/edge_server/source/app.py).
Client-side request generation and phase orchestration are implemented through
the scripts documented here.

The workload is interpreted in two regimes:

- **Storage-locality regime**: phases dominated by `device_status` traffic so
    cross-region reads remain the main independent pressure.
- **Compute-analytics regime**: phases dominated by `dashboard` traffic so
    edge-server CPU work increases while cross-region pressure stays low.

The client mix itself is read-only. The traffic generator sends only three
client-facing GET request types through `VIP_SERVER`:

| Request type | Endpoint shape | Purpose in the workload |
| --- | --- | --- |
| `device_status` | `/device/<device_id>/latest?node_id=<node_id>` | One-device lookup with enrichment and trend analysis; the main storage-locality driver |
| `service_pressure` | `/service_pressure?window_min=<minutes>&limit=<N>` | Local pressure introspection on the serving edge; a secondary analytics path that adds CPU work without MongoDB traffic |
| `dashboard` | `/dashboard/<node_id>?limit=<N>` | Multi-device ranked overview for one node; the main compute-heavy request |

Other edge-server routes are control-plane or testing helpers and are not part
of the generated client request mix.

---

## Overview

Core scripts:

| Script | Purpose |
| --- | --- |
| `export_workload_snapshot.py` | Pre-export device/node data from MongoDB to JSON — decouples the traffic generator from a live database |
| `traffic_generator.py` | Async Python script that sends phased HTTP traffic from test client namespaces through `VIP_SERVER` |

Phase config files:

| File | Purpose |
| --- | --- |
| `phases.json` | Defines the current 9-phase long-cycle experiment parameters (duration, rate, mix, cross-region ratio) |
| `phases_experiment_integrated_baseline.json` | Defines the integrated readiness profile used when one run must exercise Tier 2 storage, Tier 1 selective-sync, and compute elasticity together |
| `phases_experiment_storage_trigger.json` | Defines the storage-trigger companion profile used when the campaign must force natural Tier 2 storage scale-up |
| `phases_experiment_tier1_hotspot_bidirectional.json` | Defines the bidirectional Tier 1 selective-sync hotspot profile used by the Tier 1 activation stability experiment |

**Location:** all new files go in `source/scripts/testing/`.

The current phase schema supports the following fields per phase:

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | yes | — | Phase identifier |
| `duration_s` | int | yes | — | Phase duration in seconds |
| `rate_per_client` | float | yes | — | Requests per second per active client |
| `cross_region_ratio` | float | no | `0.0` | Fraction of `device_status` requests targeting the foreign LAN |
| `hotspot_direction` | string | no | `"lan2_to_lan1"` | Which LAN sends cross-region requests (`"lan2_to_lan1"` or `"lan1_to_lan2"`) |
| `mix` | dict | yes | — | Weighted distribution of `device_status`, `dashboard`, `service_pressure` |
| `client_fraction` | float | no | `1.0` | Fraction of total clients active during this phase. A random subset is chosen at phase start. Use `<1.0` to simulate idle clients in non-hotspot phases. |

When `client_fraction` is omitted or `1.0`, all clients are active — identical to previous behavior. The integrated baseline exercises multiple mechanisms by varying phase-local rate, mix, cross-region ratio, hotspot direction, and client fraction inside one run. The Tier 1 hotspot profile remains the focused companion workload when the operator wants an isolated selective-sync diagnostic instead of the integrated readiness gate.

---

## Prerequisites

Before running the traffic generator, the following must be ready:

1. **Network deployed** — OVS bridges, containers, namespaces active
2. **Data seeded** — `sensor_reports.py` + `device_registry.py` + `create_indexes.py` already run
3. **Snapshot exported** — `export_workload_snapshot.py` already run (produces JSON files)
4. **Test clients created** — `create_test_clients.sh --lan 1 --count N` and `--lan 2 --count N` already run

Execution order:

```text
sensor_reports.py → device_registry.py → create_indexes.py → export_workload_snapshot.py → traffic_generator.py
```

---

## Step 1 — `export_workload_snapshot.py`

Connects to both replica-set primaries and dumps the minimum data the traffic generator needs.

### CLI

```bash
python3 source/scripts/testing/export_workload_snapshot.py \
  [--mongo-lan1 mongodb://10.0.0.4:27018/] \
  [--mongo-lan2 mongodb://10.0.1.4:27018/] \
  [--output-dir data/workload_snapshot]
```

### Output Files

**`data/workload_snapshot/sensor_devices.json`** — device IDs and regions only:

```json
[
  {"_id": "lan1::device::001", "region_origin": "lan1"},
  {"_id": "lan1::device::002", "region_origin": "lan1"},
  {"_id": "lan2::device::001", "region_origin": "lan2"}
]
```

**`data/workload_snapshot/device_registry.json`** — node profiles for request targeting:

```json
[
  {
    "_id": "lan1::node::001",
    "home_region": "lan1",
        "subscribed_tags": ["industrial", "thermal"],
    "watched_devices": []
  },
  {
    "_id": "lan2::node::005",
    "home_region": "lan2",
        "subscribed_tags": ["mechanical", "high-priority", "thermal", "industrial"],
    "watched_devices": ["lan1::device::012", "lan1::device::034"]
  }
]
```

The snapshot should contain a mix of seeded node-profile families expressed via
`subscribed_tags` breadth:

- focused-local nodes with 1-2 tags
- regional-operator nodes with 3-4 tags
- global-operator nodes with 4-6 tags

The traffic generator does not need special node weighting for the baseline;
the heavier compute behavior comes from choosing ordinary node IDs whose seeded
tag breadth already creates broader dashboard fan-out.

### Implementation

```python
#!/usr/bin/env python3
"""
export_workload_snapshot.py

Exports device and node data from MongoDB to JSON files for use by the
traffic generator. Decouples experiment execution from a live database.
"""

import argparse
import json
import os
from pymongo import MongoClient

REGIONS = {
    "lan1": "mongodb://10.0.0.4:27018/",
    "lan2": "mongodb://10.0.1.4:27018/",
}


def export(uri_lan1: str, uri_lan2: str, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    uris = {"lan1": uri_lan1, "lan2": uri_lan2}

    # --- sensor_devices: _id + region_origin only ---
    all_devices = []
    for region, uri in uris.items():
        client = MongoClient(uri)
        docs = list(
            client["edge_platform"]["sensor_reports"].find(
                {}, {"_id": 1, "region_origin": 1}
            )
        )
        all_devices.extend(docs)
        client.close()

    out_devices = os.path.join(output_dir, "sensor_devices.json")
    with open(out_devices, "w") as f:
        json.dump(all_devices, f, indent=2, default=str)
    print(f"Exported {len(all_devices)} devices → {out_devices}")

    # --- device_registry: _id, home_region, subscribed_tags, watched_devices ---
    all_nodes = []
    for region, uri in uris.items():
        client = MongoClient(uri)
        docs = list(
            client["edge_platform"]["device_registry"].find(
                {},
                {"_id": 1, "home_region": 1, "subscribed_tags": 1, "watched_devices": 1},
            )
        )
        all_nodes.extend(docs)
        client.close()

    out_nodes = os.path.join(output_dir, "device_registry.json")
    with open(out_nodes, "w") as f:
        json.dump(all_nodes, f, indent=2, default=str)
    print(f"Exported {len(all_nodes)} nodes → {out_nodes}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mongo-lan1", default=REGIONS["lan1"])
    parser.add_argument("--mongo-lan2", default=REGIONS["lan2"])
    parser.add_argument("--output-dir", default="data/workload_snapshot")
    args = parser.parse_args()
    export(args.mongo_lan1, args.mongo_lan2, args.output_dir)
```

---

## Step 2 — `phases.json`

The JSON config file drives the 9-phase demand shift. Each phase defines:

| Field | Type | Description |
| --- | --- | --- |
| `name` | string | Human-readable phase label (logged in CSV) |
| `duration_s` | int | Phase duration in seconds |
| `rate_per_client` | float | Target requests/second per client namespace |
| `cross_region_ratio` | float 0–1 | Fraction of `device_status` requests targeting foreign-region devices |
| `hotspot_direction` | string | `"lan2_to_lan1"` or `"lan1_to_lan2"` — which region's clients hit the other (default: `"lan2_to_lan1"`) |
| `mix` | object | Request type distribution: `device_status` + `dashboard` + `service_pressure` (must sum to 1.0) |

The standard profile uses one application with two operating regimes:

- storage phases (`storage_stress`, `cross_region_hotspot`, `reverse_hotspot`)
    are `device_status`-dominant
- compute phases (`compute_ramp`, `compute_spike`, `sustained_plateau`) are
    `dashboard`-dominant

### Default Configuration

```json
{
  "phases": [
    {
            "name": "baseline",
            "duration_s": 60,
            "rate_per_client": 1.0,
      "cross_region_ratio": 0.0,
      "mix": {
                "device_status": 0.35,
                "dashboard": 0.35,
                "service_pressure": 0.30
            }
        },
        {
            "name": "local_moderate",
            "duration_s": 90,
            "rate_per_client": 5.0,
            "cross_region_ratio": 0.0,
            "mix": {
                "device_status": 0.35,
                "dashboard": 0.35,
                "service_pressure": 0.30
            }
        },
        {
            "name": "storage_stress",
            "duration_s": 240,
            "rate_per_client": 7.0,
            "cross_region_ratio": 0.5,
            "hotspot_direction": "lan2_to_lan1",
            "mix": {
                "device_status": 0.8,
                "dashboard": 0.1,
                "service_pressure": 0.1
      }
    },
    {
      "name": "cross_region_hotspot",
            "duration_s": 300,
            "rate_per_client": 8.0,
            "cross_region_ratio": 0.85,
      "hotspot_direction": "lan2_to_lan1",
      "mix": {
        "device_status": 0.8,
        "dashboard": 0.1,
        "service_pressure": 0.1
      }
    },
    {
            "name": "reverse_hotspot",
            "duration_s": 300,
            "rate_per_client": 8.0,
            "cross_region_ratio": 0.85,
            "hotspot_direction": "lan1_to_lan2",
      "mix": {
                "device_status": 0.8,
                "dashboard": 0.1,
                "service_pressure": 0.1
            }
        },
        {
            "name": "compute_ramp",
            "duration_s": 120,
            "rate_per_client": 11.0,
            "cross_region_ratio": 0.05,
            "hotspot_direction": "lan2_to_lan1",
            "mix": {
                "device_status": 0.35,
                "dashboard": 0.50,
                "service_pressure": 0.15
            }
        },
        {
            "name": "compute_spike",
            "duration_s": 150,
            "rate_per_client": 17.0,
            "cross_region_ratio": 0.05,
            "hotspot_direction": "lan2_to_lan1",
            "mix": {
                "device_status": 0.25,
                "dashboard": 0.60,
                "service_pressure": 0.15
            }
        },
        {
            "name": "sustained_plateau",
            "duration_s": 120,
            "rate_per_client": 10.0,
            "cross_region_ratio": 0.05,
            "hotspot_direction": "lan2_to_lan1",
            "mix": {
                "device_status": 0.30,
                "dashboard": 0.55,
                "service_pressure": 0.15
      }
    },
    {
      "name": "demand_drop",
            "duration_s": 300,
            "rate_per_client": 1.0,
      "cross_region_ratio": 0.0,
      "mix": {
        "device_status": 0.6,
        "dashboard": 0.3,
        "service_pressure": 0.1
      }
    }
  ]
}
```

This default schedule totals 1680 s, about 28 minutes.

`cross_region_ratio` applies only to `device_status` requests. Because only the
source side of `hotspot_direction` emits those remote reads, the effective
whole-workload cross-region share is lower than the raw ratio. `storage_stress`
therefore uses a lower ratio than the full hotspot phases so Tier 2 can trigger
during buildup instead of only after the strongest cross-region window begins.

### Rationale per Phase

| Phase | Why this config |
| --- | --- |
| `baseline` | Establishes Tier 0 steady state with no cross-region pressure. |
| `local_moderate` | Warms the system locally before any storage-sensitive phase begins. |
| `storage_stress` | First sustained storage-pressure window. Lower cross-region ratio than the hotspot phases so it acts as buildup instead of duplicating the hotspot. |
| `cross_region_hotspot` | Long observation window after the initial trigger, intended to show whether Tier 2 helps once a new secondary is actually ready. |
| `reverse_hotspot` | Repeats the hotspot test in the opposite direction to expose asymmetry between LANs. |
| `compute_ramp` | Reduces cross-region pressure while raising total rate so compute behavior can be evaluated with less storage confounding. |
| `compute_spike` | Peak compute demand with the same low cross-region ratio. |
| `sustained_plateau` | Holds compute pressure after the spike to observe post-scale stabilization. |
| `demand_drop` | Stays low long enough to expose cooldown-gated storage and compute scale-down. |

### Storage-Trigger Companion Profile

When the campaign objective is to force storage elasticity rather than preserve
the balanced hybrid reference profile, use
`source/scripts/testing/phases_experiment_storage_trigger.json` together with a
larger seeded working set. The wrapper now accepts explicit workload-size flags
for this purpose, and `make run_experiment` forwards the existing `CLIENTS`,
`DEVICES`, and `NODES` variables to those flags.

Recommended launch shape for the next storage-focused runs:

```bash
sudo make -C source/scripts run_experiment \
    CLIENTS=6 DEVICES=600 NODES=100 \
    PHASES_CONFIG=testing/phases_experiment_storage_trigger.json \
    RUN_LABEL=storage_trigger_ws600 \
    SKIP_CLIENTS=0 SKIP_SEED=0 SKIP_SNAPSHOT=0
```

This companion profile keeps the same request generator and data model, but it
removes the compute-dominant phases and lengthens `storage_stress`,
`cross_region_hotspot`, and `reverse_hotspot` so the storage controller sees a
sustained hotspot under a larger working set.

---

## Step 3 — `traffic_generator.py`

### Architecture

```
┌─────────────────────┐
│  traffic_generator   │  (runs on host as root)
│                     │
│  reads phases.json  │
│  reads snapshot/    │
│                     │
│  ┌───────────────┐  │
│  │ asyncio loop  │  │
│  │               │  │
│  │ Task(client_1)│──┼──► ip netns exec test_client_1 curl … http://10.0.0.100:5000/…
│  │ Task(client_2)│──┼──► ip netns exec test_client_2 curl … http://10.0.0.100:5000/…
│  │ Task(client_3)│──┼──► ip netns exec test_client_3 curl … http://10.0.0.100:5000/…
│  │ …             │  │
│  └───────────────┘  │
│                     │
│  writes CSV output  │
└─────────────────────┘
```

Each request originates from the namespace's IP address, so the SDN controller sees the correct source and routes via `VIP_SERVER` (10.0.0.100:5000).

### CLI

```bash
sudo python3 source/scripts/testing/traffic_generator.py \
  --config source/scripts/testing/phases.json \
  --clients-lan1 test_client_1,test_client_2,test_client_3 \
  --clients-lan2 test_client_4,test_client_5,test_client_6 \
  --snapshot-dir data/workload_snapshot \
  --output metrics/client_requests.csv \
  [--vip 10.0.0.100:5000] \
  [--dry-run]
```

| Flag | Default | Description |
|---|---|---|
| `--config` | *required* | Path to `phases.json` |
| `--clients-lan1` | *required* | Comma-separated list of LAN1 namespace names |
| `--clients-lan2` | *required* | Comma-separated list of LAN2 namespace names |
| `--snapshot-dir` | `data/workload_snapshot` | Directory containing exported JSON files |
| `--output` | `metrics/client_requests.csv` | Aggregate CSV output path; phase-scoped analysis is derived from the `phase` column |
| `--vip` | `10.0.0.100:5000` | VIP\_SERVER address:port |
| `--dry-run` | `false` | Print curl commands without executing |

### Core Data Structures

```python
import json
import random
from dataclasses import dataclass, field


@dataclass
class Snapshot:
    """Pre-loaded device/node data from exported JSON."""

    devices_by_region: dict[str, list[str]] = field(default_factory=dict)
    nodes_by_region: dict[str, list[str]] = field(default_factory=dict)
    watched_devices: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def load(cls, snapshot_dir: str) -> "Snapshot":
        with open(f"{snapshot_dir}/sensor_devices.json") as f:
            devices = json.load(f)
        with open(f"{snapshot_dir}/device_registry.json") as f:
            nodes = json.load(f)

        snap = cls()

        # Index devices by region
        for d in devices:
            region = d["region_origin"]
            snap.devices_by_region.setdefault(region, []).append(d["_id"])

        # Index nodes by region + build watched_devices map
        for n in nodes:
            region = n["home_region"]
            snap.nodes_by_region.setdefault(region, []).append(n["_id"])
            if n.get("watched_devices"):
                snap.watched_devices[n["_id"]] = n["watched_devices"]

        return snap


@dataclass
class PhaseConfig:
    name: str
    duration_s: int
    rate_per_client: float
    cross_region_ratio: float
    hotspot_direction: str
    mix: dict[str, float]

    @classmethod
    def from_dict(cls, d: dict) -> "PhaseConfig":
        return cls(
            name=d["name"],
            duration_s=d["duration_s"],
            rate_per_client=d["rate_per_client"],
            cross_region_ratio=d.get("cross_region_ratio", 0.0),
            hotspot_direction=d.get("hotspot_direction", "lan2_to_lan1"),
            mix=d["mix"],
        )
```

### Request Target Selection

```python
def pick_target(
    client_lan: str,
    phase: PhaseConfig,
    snap: Snapshot,
    request_type: str,
) -> dict:
    """Select device_id, node_id, and target_region for one request."""

    home = client_lan          # "lan1" or "lan2"
    foreign = "lan2" if home == "lan1" else "lan1"

    if request_type == "device_status":
        # Decide if this request is cross-region
        is_cross = random.random() < phase.cross_region_ratio

        # Respect hotspot_direction: only the "source" region does cross-region
        if phase.hotspot_direction == "lan2_to_lan1" and home == "lan1":
            is_cross = False
        elif phase.hotspot_direction == "lan1_to_lan2" and home == "lan2":
            is_cross = False

        if is_cross:
            device_id = random.choice(snap.devices_by_region[foreign])
        else:
            device_id = random.choice(snap.devices_by_region[home])

        # Pick a node from the client's own LAN for threshold override
        node_id = random.choice(snap.nodes_by_region[home])

        target_region = foreign if is_cross else home
        return {"device_id": device_id, "node_id": node_id, "target_region": target_region}

    elif request_type == "dashboard":
        node_id = random.choice(snap.nodes_by_region[home])
        return {"device_id": "", "node_id": node_id, "target_region": home}

    elif request_type == "service_pressure":
        return {"device_id": "", "node_id": "", "target_region": home}

    return {}
```

### Request Mix Selection

```python
def pick_request_type(mix: dict[str, float]) -> str:
    """Weighted random selection from the mix distribution."""
    r = random.random()
    cumulative = 0.0
    for req_type, weight in mix.items():
        cumulative += weight
        if r <= cumulative:
            return req_type
    return list(mix.keys())[-1]  # fallback
```

### URL Construction

```python
def build_url(vip: str, request_type: str, target: dict) -> str:
    """Build the full URL for a request."""
    base = f"http://{vip}"

    if request_type == "device_status":
        device_id = target["device_id"]
        node_id = target["node_id"]
        return f"{base}/device/{device_id}/latest?node_id={node_id}"

    elif request_type == "dashboard":
        node_id = target["node_id"]
        return f"{base}/dashboard/{node_id}?limit=10"

    elif request_type == "service_pressure":
        return f"{base}/service_pressure?window_min=10&limit=10"

    return base
```

### Curl Execution via Namespace

```python
import asyncio
import time


async def exec_curl(ns: str, url: str, dry_run: bool = False) -> tuple[int, float]:
    """Execute curl inside a network namespace. Returns (http_status, latency_s)."""

    cmd = [
        "ip", "netns", "exec", ns,
        "curl", "-s", "-o", "/dev/null",
        "-w", "%{http_code} %{time_total}",
        "--max-time", "10",
        url,
    ]

    if dry_run:
        print(f"[DRY-RUN] {' '.join(cmd)}")
        return 200, 0.0

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()

    parts = stdout.decode().strip().split()
    if len(parts) == 2:
        return int(parts[0]), float(parts[1])
    return 0, 0.0
```

### Per-Client Task Loop

```python
import csv


async def client_loop(
    ns: str,
    client_lan: str,
    phases: list[PhaseConfig],
    snap: Snapshot,
    vip: str,
    csv_writer,
    csv_lock: asyncio.Lock,
    dry_run: bool,
):
    """One async task per client namespace. Runs through all phases sequentially."""

    for phase in phases:
        phase_end = time.monotonic() + phase.duration_s
        interval = 1.0 / phase.rate_per_client

        while time.monotonic() < phase_end:
            t0 = time.monotonic()

            # Pick request type and target
            req_type = pick_request_type(phase.mix)
            target = pick_target(client_lan, phase, snap, req_type)
            url = build_url(vip, req_type, target)

            # Execute
            http_status, latency_s = await exec_curl(ns, url, dry_run)

            # Log to CSV
            row = [
                datetime.now(timezone.utc).isoformat(),
                phase.name,
                ns,
                client_lan,
                req_type,
                target.get("device_id", ""),
                target.get("node_id", ""),
                target.get("target_region", ""),
                http_status,
                round(latency_s, 4),
            ]
            async with csv_lock:
                csv_writer.writerow(row)

            # Pace: sleep for remaining interval (with jitter)
            elapsed = time.monotonic() - t0
            sleep_time = max(0, interval - elapsed + random.uniform(-0.05, 0.05))
            await asyncio.sleep(sleep_time)
```

### Main Orchestration

```python
from datetime import datetime, timezone


async def main(args):
    # Load config
    with open(args.config) as f:
        raw = json.load(f)
    phases = [PhaseConfig.from_dict(p) for p in raw["phases"]]

    # Load snapshot
    snap = Snapshot.load(args.snapshot_dir)
    print(f"Loaded snapshot: {sum(len(v) for v in snap.devices_by_region.values())} devices, "
          f"{sum(len(v) for v in snap.nodes_by_region.values())} nodes")

    # Parse client lists
    lan1_clients = args.clients_lan1.split(",") if args.clients_lan1 else []
    lan2_clients = args.clients_lan2.split(",") if args.clients_lan2 else []
    all_clients = [(ns, "lan1") for ns in lan1_clients] + [(ns, "lan2") for ns in lan2_clients]

    if not all_clients:
        print("ERROR: No clients specified")
        return

    # Prepare CSV output
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    csv_file = open(args.output, "w", newline="")
    csv_writer = csv.writer(csv_file)
    csv_writer.writerow([
        "timestamp", "phase", "client_ns", "client_lan", "endpoint",
        "device_id", "node_id", "target_region", "http_status", "latency_s",
    ])
    csv_lock = asyncio.Lock()

    vip = args.vip

    # Log phase plan
    total_s = sum(p.duration_s for p in phases)
    print(f"Running {len(phases)} phases ({total_s}s total) "
          f"with {len(all_clients)} clients")
    for p in phases:
        print(f"  {p.name}: {p.duration_s}s @ {p.rate_per_client} req/s/client, "
              f"cross_region={p.cross_region_ratio}")

    # Write phase markers and launch tasks
    for i, phase in enumerate(phases):
        phase_marker = [
            datetime.now(timezone.utc).isoformat(),
            f"PHASE_START:{phase.name}",
            "", "", "", "", "", "", "", "",
        ]
        csv_writer.writerow(phase_marker)
        csv_file.flush()

        print(f"\n{'='*60}")
        print(f"Phase {i+1}/{len(phases)}: {phase.name} ({phase.duration_s}s)")
        print(f"{'='*60}")

        # Run all clients concurrently for this phase
        tasks = [
            asyncio.create_task(
                client_loop(
                    ns, lan, [phase], snap, vip,
                    csv_writer, csv_lock, args.dry_run,
                )
            )
            for ns, lan in all_clients
        ]
        await asyncio.gather(*tasks)

    csv_file.close()
    print(f"\nDone. Results written to {args.output}")
```

### Entry Point

```python
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Traffic generator for the edge IoT workload experiment"
    )
    parser.add_argument("--config", required=True, help="Path to phases.json")
    parser.add_argument("--clients-lan1", default="", help="Comma-separated LAN1 namespace names")
    parser.add_argument("--clients-lan2", default="", help="Comma-separated LAN2 namespace names")
    parser.add_argument("--snapshot-dir", default="data/workload_snapshot")
    parser.add_argument("--output", default="metrics/client_requests.csv")
    parser.add_argument("--vip", default="10.0.0.100:5000", help="VIP_SERVER address:port")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing")

    args = parser.parse_args()
    asyncio.run(main(args))
```

---

## CSV Output Format

One row per request:

| Column | Type | Example |
|---|---|---|
| `timestamp` | ISO 8601 UTC | `2026-03-31T14:22:01.123Z` |
| `phase` | string | `cross_region_hotspot` |
| `client_ns` | string | `test_client_2` |
| `client_lan` | string | `lan1` |
| `endpoint` | string | `device_status` / `dashboard` / `service_pressure` |
| `device_id` | string | `lan1::device::042` |
| `node_id` | string | `lan2::node::005` |
| `target_region` | string | `lan1` |
| `http_status` | int | `200` |
| `latency_s` | float | `0.0342` |

Phase boundaries are marked with a `PHASE_START:<name>` row for post-processing.

---

## Execution Flow

### Full experiment run

```bash
# 1. Create test clients (once per network deployment)
sudo ./source/scripts/network/clients/create_test_clients.sh --lan 1 --count 3
sudo ./source/scripts/network/clients/create_test_clients.sh --lan 2 --count 3

# 2. Seed data (once per experiment)
python3 source/scripts/testing/sensor_reports.py --devices 100
python3 source/scripts/testing/device_registry.py --nodes 40 --devices 100
python3 source/scripts/testing/create_indexes.py

# 3. Export snapshot (once per seeding)
python3 source/scripts/testing/export_workload_snapshot.py \
  --output-dir data/workload_snapshot

# 4. Run traffic generator
sudo python3 source/scripts/testing/traffic_generator.py \
  --config source/scripts/testing/phases.json \
  --clients-lan1 test_client_1,test_client_2,test_client_3 \
  --clients-lan2 test_client_4,test_client_5,test_client_6 \
  --snapshot-dir data/workload_snapshot \
  --output metrics/client_requests.csv
```

### Quick smoke test

```bash
# Single phase, short duration, 1 client per LAN
cat > /tmp/smoke.json << 'EOF'
{
  "phases": [
    {"name": "smoke_test", "duration_s": 30, "rate_per_client": 1.0,
     "cross_region_ratio": 0.0, "mix": {"device_status": 0.6, "dashboard": 0.3, "service_pressure": 0.1}}
  ]
}
EOF

sudo python3 source/scripts/testing/traffic_generator.py \
  --config /tmp/smoke.json \
  --clients-lan1 test_client_1 \
  --clients-lan2 test_client_4 \
  --output /tmp/smoke_results.csv
```

### Dry run (no network required)

```bash
python3 source/scripts/testing/traffic_generator.py \
  --config source/scripts/testing/phases.json \
  --clients-lan1 test_client_1,test_client_2 \
  --clients-lan2 test_client_4,test_client_5 \
  --snapshot-dir data/workload_snapshot \
  --dry-run
```

---

## Design Decisions

### Why `ip netns exec curl` instead of aiohttp

The SDN controller intercepts traffic based on source IP. Test client namespaces have isolated network stacks with unique IPs (e.g., `10.0.0.30`, `10.0.1.31`). Using `aiohttp` from the host would send all requests from the host IP, bypassing the VIP\_SERVER routing mechanism entirely. Spawning `curl` inside each namespace ensures the packet enters the OVS bridge from the correct veth port.

### Why pre-exported JSON snapshot

The traffic generator runs on the host and cannot reach the MongoDB primaries (which are inside Docker containers on OVS networks). Even if it could, connecting to MongoDB during the experiment would introduce uncontrolled traffic. The snapshot is a clean read-once input.

### Why external phases.json

Reproducibility: the same config file produces the same experiment. Parameter sweeps (vary rate, cross-region ratio, phase duration) are JSON edits, not code changes.

### Why per-phase sequential, per-client concurrent

All clients run concurrently within a phase (reflecting realistic multi-user load), but phases execute sequentially (the experiment is a controlled temporal sequence). The `asyncio.gather` per phase + sequential phase loop achieves this naturally.

---

## Verification Checklist

| # | Test | Expected |
|---|---|---|
| 1 | Run `export_workload_snapshot.py` after seeding | Two JSON files with 200 devices + 80 nodes (default counts) |
| 2 | Run `traffic_generator.py --dry-run` | Printed curl commands show correct URLs; no subprocesses spawned |
| 3 | Smoke test (`baseline` only, 30s, 1 client/LAN) | CSV has rows with `http_status=200`, `latency_s` between 0.01–1.0 |
| 4 | `cross_region_hotspot` cross-region check (30s) | For the source LAN of `hotspot_direction`, most `device_status` rows target peer-region device IDs |
| 5 | Rate accuracy (`compute_spike`, 60s, 1 client) | Total rows ≈ `17 × 60 = 1020` (±10%) |
| 6 | Aggregate output present | Run directory contains `client_requests.csv` and `current_phase.txt` |

---

## Scope & Limitations

### Included

- Snapshot export script
- Traffic generator with 9-phase long-cycle support
- CSV per-request metrics
- Dry-run mode
- Default `phases.json`

### Excluded (future work)

- **Baseline mode switching** (B0/B1/B2/S env-var gating) — requires controller-side changes
- **Grafana/Prometheus** integration — host-side metrics exporter
- **Experiment orchestration** (`run_experiment.sh`) — full automation across modes and repetitions
- **Aggregator CSV sink** — server-side telemetry file export
- **Post-experiment analysis** — pandas/matplotlib notebooks for result interpretation

### Known Constraints

1. **`curl` subprocess overhead** — each request spawns a process. At 10 req/s/client × 6 clients = 60 concurrent `curl` processes. This is acceptable for experiment timescales but would not scale to hundreds of clients. If higher concurrency is needed, consider a C-based HTTP client binary or running a Python HTTP client inside each namespace directly.

2. **Phase 4 scale-down** — node removal is not yet implemented in the controller. Phase 4 will observe over-provisioned latency behavior but will not trigger infrastructure reclamation.

3. **Rate precision** — `asyncio.sleep` is not real-time. Actual rates may drift ±5% from target, especially under high subprocess load. The CSV timestamps allow post-hoc rate calculation for verification.
