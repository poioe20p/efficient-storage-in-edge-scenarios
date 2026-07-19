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
      [--vip-lan1 10.0.0.253:5000] \
      [--vip-lan2 10.0.1.253:5000] \
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
    """Pre-loaded content/user data from exported JSON."""

    content_ids_by_region: dict = field(default_factory=dict)
    user_ids_by_region: dict = field(default_factory=dict)

    @classmethod
    def load(cls, snapshot_dir: str) -> "Snapshot":
        with open(os.path.join(snapshot_dir, "content_items.json")) as f:
            content_items = json.load(f)
        with open(os.path.join(snapshot_dir, "user_profiles.json")) as f:
            user_profiles = json.load(f)

        snap = cls()

        for item in content_items:
            region = item["region_origin"]
            snap.content_ids_by_region.setdefault(region, []).append(item["_id"])

        for profile in user_profiles:
            region = profile["home_region"]
            snap.user_ids_by_region.setdefault(region, []).append(profile["_id"])

        return snap

    @classmethod
    def mock(cls, n_content_items: int = 50, n_users: int = 20) -> "Snapshot":
        """Return synthetic snapshot data for dry-run testing without real files."""
        snap = cls()
        for region in ("lan1", "lan2"):
            snap.content_ids_by_region[region] = [
                f"{region}::content::{i:03d}" for i in range(1, n_content_items + 1)
            ]
            snap.user_ids_by_region[region] = [
                f"{region}::user::{i:03d}" for i in range(1, n_users + 1)
            ]
        return snap


@dataclass
class PhaseConfig:
    name: str
    duration_s: int
    rate_per_client: float
    cross_region_ratio: float
    hotspot_direction: str
    mix: dict
    client_fraction: float = 1.0

    @classmethod
    def from_dict(cls, d: dict) -> "PhaseConfig":
        hotspot_direction = d.get("hotspot_direction") or "bidirectional"
        if hotspot_direction not in {"bidirectional", "lan2_to_lan1", "lan1_to_lan2"}:
            raise ValueError(
                "hotspot_direction must be bidirectional, lan2_to_lan1, lan1_to_lan2, or blank"
            )
        return cls(
            name=d["name"],
            duration_s=d["duration_s"],
            rate_per_client=d["rate_per_client"],
            cross_region_ratio=d.get("cross_region_ratio", 0.0),
            hotspot_direction=hotspot_direction,
            mix=d["mix"],
            client_fraction=d.get("client_fraction", 1.0),
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
    """Select content_id, user_id, and target_region for one request."""
    home = client_lan
    foreign = "lan2" if home == "lan1" else "lan1"

    if request_type == "content_lookup":
        is_cross = random.random() < phase.cross_region_ratio

        # The canonical integrated profile leaves hotspot_direction blank, which
        # means both LANs may emit cross-region lookups subject to the shared
        # cross_region_ratio. Directional override profiles can pin one source
        # LAN explicitly for focused hotspot validation.
        if phase.hotspot_direction == "lan2_to_lan1" and home == "lan1":
            is_cross = False
        elif phase.hotspot_direction == "lan1_to_lan2" and home == "lan2":
            is_cross = False

        target_lan = foreign if is_cross else home
        content_id = random.choice(snap.content_ids_by_region[target_lan])
        user_id = random.choice(snap.user_ids_by_region[home])
        return {"content_id": content_id, "user_id": user_id, "target_region": target_lan}

    if request_type == "feed_ranking":
        user_id = random.choice(snap.user_ids_by_region[home])
        return {"content_id": "", "user_id": user_id, "target_region": home}

    if request_type == "service_pressure":
        return {"content_id": "", "user_id": "", "target_region": home}

    if request_type == "content_update":
        content_id = random.choice(snap.content_ids_by_region[home])
        return {"content_id": content_id, "user_id": "", "target_region": home}

    if request_type == "content_aggregate":
        # Aggregation is a collection-level operation — no specific content item needed.
        # Target region is always local (aggregation runs on the client's own
        # LAN's MongoDB; the aggregator doesn't cross regions).
        return {
            "content_id": "",
            "user_id": "",
            "target_region": client_lan,
        }

    raise ValueError(f"Unsupported request type: {request_type}")


def build_url(vip: str, request_type: str, target: dict) -> str:
    """Build the full URL for a request."""
    base = f"http://{vip}"

    if request_type == "content_lookup":
        return f"{base}/content/{target['content_id']}?requester={target['user_id']}"
    if request_type == "feed_ranking":
        return f"{base}/feed/{target['user_id']}?limit=10"
    if request_type == "service_pressure":
        return f"{base}/service_pressure?window_min=1&limit=10"
    if request_type == "content_update":
        return f"{base}/content"
    if request_type == "content_aggregate":
        return f"{base}/content/aggregate"

    raise ValueError(f"Unsupported request type: {request_type}")


# ---------------------------------------------------------------------------
# Curl execution
# ---------------------------------------------------------------------------


_curl_warn_shown = False


async def exec_curl(ns: str, url: str, dry_run: bool = False, body: str | None = None) -> tuple:
    """Execute curl inside a network namespace. Returns (http_status, latency_s).

    When *body* is not None the request is sent as POST with
    ``Content-Type: application/json``.
    """
    global _curl_warn_shown
    curl_max_time = os.environ.get("CURL_MAX_TIME") or "30"

    cmd = [
        "ip", "netns", "exec", ns,
        "curl", "-s", "-o", "/dev/null",
        "-w", "\n%{http_code} %{time_total}",
        "--max-time", curl_max_time,
    ]
    if body is not None:
        cmd += ["-X", "POST", "-H", "Content-Type: application/json", "-d", body]
    cmd.append(url)

    if dry_run:
        print(f"[DRY-RUN] {' '.join(cmd)}")
        return 200, 0.0

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()

    output = stdout.decode().strip()
    # -w output is on the last line (prefixed with \n to separate from any body leak)
    last_line = output.split("\n")[-1].strip() if output else ""
    parts = last_line.split()

    if len(parts) == 2:
        try:
            return int(parts[0]), float(parts[1])
        except ValueError:
            pass

    # Diagnostic: show why parsing failed (only first occurrence per client)
    if not _curl_warn_shown:
        _curl_warn_shown = True
        err = stderr.decode().strip()[:200] if stderr else "(empty)"
        print(f"  [DIAG] curl parse failed in {ns} (rc={proc.returncode})")
        print(f"         stdout={output[:200]!r}")
        print(f"         stderr={err!r}")

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
    csv_targets,
    csv_lock: asyncio.Lock,
    dry_run: bool,
):
    """One async task per client namespace for a single phase."""
    if dry_run:
        # Bounded preview mode: emit each active request type once so validation
        # can confirm the renamed surface without replaying full phase timing.
        for req_type, weight in phase.mix.items():
            if weight <= 0:
                continue

            target = pick_target(client_lan, phase, snap, req_type)
            url = build_url(vip, req_type, target)

            body = None
            if req_type == "content_update":
                update_padding = "x" * 1024  # 1KB of padding to inflate oplog entries
                body = (
                    f'{{"content_id":"{target["content_id"]}",'
                    f'"engagement":{random.randint(0,100)},'
                    f'"lan":"{client_lan}",'
                    f'"update_padding":"{update_padding}"}}'
                )
            if req_type == "content_aggregate":
                body = (
                    f'{{"lan":"{client_lan}",'
                    f'"engagement_threshold":{random.randint(30,70)}}}'
                )

            sent_at = datetime.now(timezone.utc).isoformat()
            phase_name = phase.name

            http_status, latency_s = await exec_curl(ns, url, dry_run, body)

            row = [
                sent_at,
                phase_name,
                ns,
                client_lan,
                req_type,
                target.get("content_id", ""),
                target.get("user_id", ""),
                target.get("target_region", ""),
                http_status,
                round(latency_s, 4),
                datetime.now(timezone.utc).isoformat(),
            ]
            async with csv_lock:
                for csv_writer, csv_file in csv_targets:
                    csv_writer.writerow(row)
                for _, csv_file in csv_targets:
                    csv_file.flush()
        return

    phase_end = time.monotonic() + phase.duration_s
    interval = 1.0 / phase.rate_per_client
    request_count = 0
    last_log = time.monotonic()
    log_interval = 10  # seconds between progress logs

    while time.monotonic() < phase_end:
        t0 = time.monotonic()

        req_type = pick_request_type(phase.mix)
        target = pick_target(client_lan, phase, snap, req_type)
        url = build_url(vip, req_type, target)

        body = None
        if req_type == "content_update":
            update_padding = "x" * 1024  # 1KB of padding to inflate oplog entries
            body = (
                f'{{"content_id":"{target["content_id"]}",'
                f'"engagement":{random.randint(0,100)},'
                f'"lan":"{client_lan}",'
                f'"update_padding":"{update_padding}"}}'
            )
        if req_type == "content_aggregate":
            body = (
                f'{{"lan":"{client_lan}",'
                f'"engagement_threshold":{random.randint(30,70)}}}'
            )
        sent_at = datetime.now(timezone.utc).isoformat()
        phase_name = phase.name
        http_status, latency_s = await exec_curl(ns, url, dry_run, body)
        request_count += 1

        row = [
            sent_at,
            phase_name,
            ns,
            client_lan,
            req_type,
            target.get("content_id", ""),
            target.get("user_id", ""),
            target.get("target_region", ""),
            http_status,
            round(latency_s, 4),
            datetime.now(timezone.utc).isoformat(),
        ]
        async with csv_lock:
            for csv_writer, csv_file in csv_targets:
                csv_writer.writerow(row)
            for _, csv_file in csv_targets:
                csv_file.flush()

        now = time.monotonic()
        remaining = max(0, phase_end - now)
        if now - last_log >= log_interval:
            print(f"  [{ns}] {request_count} reqs sent, "
                  f"{int(remaining)}s remaining, last status={http_status}")
            last_log = now

        elapsed = time.monotonic() - t0
        sleep_time = max(0.0, interval - elapsed + random.uniform(-0.05, 0.05))
        await asyncio.sleep(sleep_time)


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------


async def run(args):
    # Fix random seed before any workload decisions for reproducible runs
    if args.random_seed is not None:
        random.seed(args.random_seed)
        print(f"Random seed fixed: {args.random_seed}")

    with open(args.config) as f:
        raw = json.load(f)
    phases = [PhaseConfig.from_dict(p) for p in raw["phases"]]

    if args.dry_run:
        try:
            snap = Snapshot.load(args.snapshot_dir)
        except FileNotFoundError:
            snap = Snapshot.mock()
            print("[DRY-RUN] Snapshot files not found — using synthetic data")
    else:
        snap = Snapshot.load(args.snapshot_dir)
    n_content_items = sum(len(v) for v in snap.content_ids_by_region.values())
    n_users = sum(len(v) for v in snap.user_ids_by_region.values())
    print(f"Snapshot: {n_content_items} content items, {n_users} user profiles")

    lan1_clients = [c for c in args.clients_lan1.split(",") if c] if args.clients_lan1 else []
    lan2_clients = [c for c in args.clients_lan2.split(",") if c] if args.clients_lan2 else []
    all_clients = [(ns, "lan1") for ns in lan1_clients] + [(ns, "lan2") for ns in lan2_clients]

    if not all_clients:
        print("ERROR: no clients specified (use --clients-lan1 and/or --clients-lan2)")
        return

    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    csv_lock = asyncio.Lock()

    total_s = sum(p.duration_s for p in phases)
    print(f"{len(phases)} phases, {total_s}s total, {len(all_clients)} clients")
    for p in phases:
        print(f"  {p.name}: {p.duration_s}s @ {p.rate_per_client} req/s/client, "
              f"cross_region={p.cross_region_ratio}")

    # Phase file: signals the current phase to sibling processes (e.g. resource stats collector)
    phase_state_file = os.path.join(output_dir, "current_phase.txt") if output_dir else "current_phase.txt"
    header = [
        "sent_at", "phase", "client_ns", "client_lan", "endpoint",
        "content_id", "user_id", "target_region", "http_status", "latency_s",
        "completed_at",
    ]

    aggregate_file = open(args.output, "w", newline="")
    aggregate_writer = csv.writer(aggregate_file)
    aggregate_writer.writerow(header)
    csv_targets = [(aggregate_writer, aggregate_file)]

    try:
        for i, phase in enumerate(phases):
            # Write current phase name so other processes can read it
            with open(phase_state_file, "w") as pf:
                pf.write(phase.name)

            # Select active client subset for this phase (client_fraction < 1.0
            # simulates some clients being idle, as in real deployments).
            # Per-LAN proportional sampling ensures balanced traffic across LANs
            # instead of global random sample which can skew toward one LAN.
            fraction = getattr(phase, 'client_fraction', 1.0)
            if fraction < 1.0:
                n_lan1 = max(1, int(len(lan1_clients) * fraction))
                n_lan2 = max(1, int(len(lan2_clients) * fraction))
                lan1_active = [(ns, lan) for ns, lan in random.sample(
                    [(ns, "lan1") for ns in lan1_clients], n_lan1)]
                lan2_active = [(ns, lan) for ns, lan in random.sample(
                    [(ns, "lan2") for ns in lan2_clients], n_lan2)]
                phase_clients = lan1_active + lan2_active
            else:
                phase_clients = all_clients

            print(f"\n{'='*60}")
            print(f"Phase {i + 1}/{len(phases)}: {phase.name} ({phase.duration_s}s)")
            print(f"  Output: {args.output}")
            if fraction < 1.0:
                print(f"  Clients: {len(phase_clients)}/{len(all_clients)} active (fraction={fraction})")
            print(f"{'='*60}")

            tasks = [
                asyncio.create_task(
                    client_loop(ns, lan, phase, snap,
                                args.vip_lan1 if lan == "lan1" else args.vip_lan2,
                                csv_targets, csv_lock, args.dry_run)
                )
                for ns, lan in phase_clients
            ]
            await asyncio.gather(*tasks)
    finally:
        aggregate_file.close()

    # Signal that all phases are complete
    with open(phase_state_file, "w") as pf:
        pf.write("idle")

    print("\nDone. Results written to:")
    print(f"  {args.output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Traffic generator for the edge content-discovery workload experiment"
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
        "--vip-lan1", default="10.0.0.253:5000",
        help="VIP_SERVER_N1 address:port for LAN1 clients (default: 10.0.0.253:5000)"
    )
    parser.add_argument(
        "--vip-lan2", default="10.0.1.253:5000",
        help="VIP_SERVER_N2 address:port for LAN2 clients (default: 10.0.1.253:5000)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print curl commands without executing them"
    )
    parser.add_argument(
        "--random-seed", type=int, default=None,
        help="Fixed random seed for reproducible request sequences (default: system random)"
    )

    args = parser.parse_args()
    asyncio.run(run(args))
