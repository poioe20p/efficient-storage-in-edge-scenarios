#!/usr/bin/env python3
"""
traffic_generator.py

Sends phased HTTP traffic from Linux network namespaces through VIP_SERVER.
Each request is spawned as `ip netns exec <ns> curl ...` so the SDN controller
sees the correct source IP and routes via the VIP mechanism.

Requires root (for ip netns exec).

Usage:
    sudo python3 traffic_generator.py \
      --config phases.json \
      --clients-lan1 test_client_1,test_client_2,test_client_3 \
      --clients-lan2 test_client_4,test_client_5,test_client_6 \
      --snapshot-dir data/workload_snapshot \
      --output metrics/client_requests.csv \
      [--vip 10.0.0.100:5000] \
      [--dry-run]
"""

import argparse
import asyncio
import csv
import json
import os
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Snapshot:
    """Pre-loaded device/node data from exported JSON."""

    devices_by_region: dict = field(default_factory=dict)
    nodes_by_region: dict = field(default_factory=dict)

    @classmethod
    def load(cls, snapshot_dir: str) -> "Snapshot":
        with open(os.path.join(snapshot_dir, "sensor_devices.json")) as f:
            devices = json.load(f)
        with open(os.path.join(snapshot_dir, "device_registry.json")) as f:
            nodes = json.load(f)

        snap = cls()

        for d in devices:
            region = d["region_origin"]
            snap.devices_by_region.setdefault(region, []).append(d["_id"])

        for n in nodes:
            region = n["home_region"]
            snap.nodes_by_region.setdefault(region, []).append(n["_id"])

        return snap


@dataclass
class PhaseConfig:
    name: str
    duration_s: int
    rate_per_client: float
    cross_region_ratio: float
    hotspot_direction: str
    mix: dict

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


# ---------------------------------------------------------------------------
# Request helpers
# ---------------------------------------------------------------------------


def pick_request_type(mix: dict) -> str:
    """Weighted random selection from the mix distribution."""
    r = random.random()
    cumulative = 0.0
    for req_type, weight in mix.items():
        cumulative += weight
        if r <= cumulative:
            return req_type
    return list(mix.keys())[-1]


def pick_target(client_lan: str, phase: PhaseConfig, snap: Snapshot, request_type: str) -> dict:
    """Select device_id, node_id, and target_region for one request."""
    home = client_lan
    foreign = "lan2" if home == "lan1" else "lan1"

    if request_type == "device_status":
        is_cross = random.random() < phase.cross_region_ratio

        # Only the source region defined in hotspot_direction sends cross-region requests
        if phase.hotspot_direction == "lan2_to_lan1" and home == "lan1":
            is_cross = False
        elif phase.hotspot_direction == "lan1_to_lan2" and home == "lan2":
            is_cross = False

        target_lan = foreign if is_cross else home
        device_id = random.choice(snap.devices_by_region[target_lan])
        node_id = random.choice(snap.nodes_by_region[home])
        return {"device_id": device_id, "node_id": node_id, "target_region": target_lan}

    elif request_type == "dashboard":
        node_id = random.choice(snap.nodes_by_region[home])
        return {"device_id": "", "node_id": node_id, "target_region": home}

    elif request_type == "anomalies":
        return {"device_id": "", "node_id": "", "target_region": home}

    return {}


def build_url(vip: str, request_type: str, target: dict) -> str:
    """Build the full URL for a request."""
    base = f"http://{vip}"

    if request_type == "device_status":
        return f"{base}/device/{target['device_id']}/latest?node_id={target['node_id']}"
    elif request_type == "dashboard":
        return f"{base}/dashboard/{target['node_id']}?limit=10"
    elif request_type == "anomalies":
        return f"{base}/anomalies?region={target['target_region']}&window=1"

    return base


# ---------------------------------------------------------------------------
# Curl execution
# ---------------------------------------------------------------------------


async def exec_curl(ns: str, url: str, dry_run: bool = False) -> tuple:
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


# ---------------------------------------------------------------------------
# Per-client task
# ---------------------------------------------------------------------------


async def client_loop(
    ns: str,
    client_lan: str,
    phase: PhaseConfig,
    snap: Snapshot,
    vip: str,
    csv_writer,
    csv_lock: asyncio.Lock,
    dry_run: bool,
):
    """One async task per client namespace for a single phase."""
    phase_end = time.monotonic() + phase.duration_s
    interval = 1.0 / phase.rate_per_client

    while time.monotonic() < phase_end:
        t0 = time.monotonic()

        req_type = pick_request_type(phase.mix)
        target = pick_target(client_lan, phase, snap, req_type)
        url = build_url(vip, req_type, target)

        http_status, latency_s = await exec_curl(ns, url, dry_run)

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

        elapsed = time.monotonic() - t0
        sleep_time = max(0.0, interval - elapsed + random.uniform(-0.05, 0.05))
        await asyncio.sleep(sleep_time)


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


async def run(args):
    with open(args.config) as f:
        raw = json.load(f)
    phases = [PhaseConfig.from_dict(p) for p in raw["phases"]]

    snap = Snapshot.load(args.snapshot_dir)
    n_devices = sum(len(v) for v in snap.devices_by_region.values())
    n_nodes = sum(len(v) for v in snap.nodes_by_region.values())
    print(f"Snapshot: {n_devices} devices, {n_nodes} nodes")

    lan1_clients = [c for c in args.clients_lan1.split(",") if c] if args.clients_lan1 else []
    lan2_clients = [c for c in args.clients_lan2.split(",") if c] if args.clients_lan2 else []
    all_clients = [(ns, "lan1") for ns in lan1_clients] + [(ns, "lan2") for ns in lan2_clients]

    if not all_clients:
        print("ERROR: no clients specified (use --clients-lan1 and/or --clients-lan2)")
        return

    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    csv_file = open(args.output, "w", newline="")
    writer = csv.writer(csv_file)
    writer.writerow([
        "timestamp", "phase", "client_ns", "client_lan", "endpoint",
        "device_id", "node_id", "target_region", "http_status", "latency_s",
    ])
    csv_lock = asyncio.Lock()

    total_s = sum(p.duration_s for p in phases)
    print(f"{len(phases)} phases, {total_s}s total, {len(all_clients)} clients")
    for p in phases:
        print(f"  {p.name}: {p.duration_s}s @ {p.rate_per_client} req/s/client, "
              f"cross_region={p.cross_region_ratio}")

    for i, phase in enumerate(phases):
        # Write phase boundary marker
        writer.writerow([
            datetime.now(timezone.utc).isoformat(),
            f"PHASE_START:{phase.name}",
            "", "", "", "", "", "", "", "",
        ])
        csv_file.flush()

        print(f"\n{'='*60}")
        print(f"Phase {i + 1}/{len(phases)}: {phase.name} ({phase.duration_s}s)")
        print(f"{'='*60}")

        tasks = [
            asyncio.create_task(
                client_loop(ns, lan, phase, snap, args.vip, writer, csv_lock, args.dry_run)
            )
            for ns, lan in all_clients
        ]
        await asyncio.gather(*tasks)

    csv_file.close()
    print(f"\nDone. Results written to {args.output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Traffic generator for the edge IoT workload experiment"
    )
    parser.add_argument("--config", required=True, help="Path to phases.json")
    parser.add_argument(
        "--clients-lan1", default="",
        help="Comma-separated LAN1 namespace names (e.g. test_client_1,test_client_2)"
    )
    parser.add_argument(
        "--clients-lan2", default="",
        help="Comma-separated LAN2 namespace names (e.g. test_client_4,test_client_5)"
    )
    parser.add_argument("--snapshot-dir", default="data/workload_snapshot", metavar="DIR")
    parser.add_argument("--output", default="metrics/client_requests.csv", metavar="FILE")
    parser.add_argument(
        "--vip", default="10.0.0.100:5000",
        help="VIP_SERVER address:port (default: 10.0.0.100:5000)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print curl commands without executing them"
    )

    args = parser.parse_args()
    asyncio.run(run(args))
