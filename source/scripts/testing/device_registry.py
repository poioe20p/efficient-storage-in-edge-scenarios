#!/usr/bin/env python3
"""
seed_device_registry.py

Populates device_registry with edge node subscription profiles.
Each region's nodes are seeded into that region's own replica-set primary.

Seeded node profiles now serve two purposes:

1. preserve locality-sensitive watched-device patterns for `device_status`
2. create broader `subscribed_tags` fan-out for dashboard-heavy compute phases

Profile family distribution per region:
    ~55% focused_local      — 1-2 tags, mostly local watched devices
    ~30% regional_operator  — 3-4 tags, mixed watched devices
    ~15% global_operator    — 4-6 tags, broad cross-region subscriptions

Usage:
    python3 seed_device_registry.py --mongo-lan1 <uri> --mongo-lan2 <uri> --nodes <N per region>
"""

import argparse
import random
from pymongo import MongoClient, UpdateOne


TAG_POOL = [
    "industrial",
    "high-priority",
    "thermal",
    "mechanical",
    "logistics",
    "environmental",
]

PROFILE_SPECS = {
    "focused_local": {
        "weight": 0.55,
        "tag_range": (1, 2),
        "watch_count_range": (3, 6),
        "watch_mix": {"local": 0.80, "mixed": 0.20, "foreign": 0.00},
    },
    "regional_operator": {
        "weight": 0.30,
        "tag_range": (3, 4),
        "watch_count_range": (4, 8),
        "watch_mix": {"local": 0.45, "mixed": 0.45, "foreign": 0.10},
    },
    "global_operator": {
        "weight": 0.15,
        "tag_range": (4, 6),
        "watch_count_range": (6, 12),
        "watch_mix": {"local": 0.20, "mixed": 0.55, "foreign": 0.25},
    },
}


def pick_weighted_key(weights: dict[str, float]) -> str:
    roll = random.random()
    cumulative = 0.0
    last_key = next(iter(weights))
    for key, weight in weights.items():
        cumulative += weight
        last_key = key
        if roll <= cumulative:
            return key
    return last_key


def build_watched_devices(
    profile_kind: str,
    local_device_ids: list[str],
    foreign_device_ids: list[str],
) -> list[str]:
    spec = PROFILE_SPECS[profile_kind]
    watch_mode = pick_weighted_key(spec["watch_mix"])
    low, high = spec["watch_count_range"]
    target_count = random.randint(low, high)

    if watch_mode == "local":
        return random.sample(local_device_ids, k=min(target_count, len(local_device_ids)))
    if watch_mode == "foreign":
        return random.sample(foreign_device_ids, k=min(target_count, len(foreign_device_ids)))

    foreign_share = {
        "focused_local": 0.25,
        "regional_operator": 0.50,
        "global_operator": 0.70,
    }[profile_kind]
    foreign_count = max(1, min(target_count - 1, round(target_count * foreign_share)))
    local_count = max(1, target_count - foreign_count)
    return (
        random.sample(local_device_ids, k=min(local_count, len(local_device_ids)))
        + random.sample(foreign_device_ids, k=min(foreign_count, len(foreign_device_ids)))
    )


def make_node(region: str, index: int, local_device_ids: list[str], foreign_device_ids: list[str]) -> dict:
    node_id = f"{region}::node::{index:03d}"
    home = region
    profile_kind = pick_weighted_key({
        key: spec["weight"] for key, spec in PROFILE_SPECS.items()
    })
    watched = build_watched_devices(profile_kind, local_device_ids, foreign_device_ids)
    tag_low, tag_high = PROFILE_SPECS[profile_kind]["tag_range"]
    subscribed_tags = random.sample(
        TAG_POOL,
        k=random.randint(tag_low, tag_high),
    )

    return {
        "_id": node_id,
        "home_region": home,
        "profile_kind": profile_kind,
        "subscribed_tags": subscribed_tags,
        "watched_devices": watched,
        "alert_config": {
            "email": f"ops-{region}@example.com",
            "threshold_override": {
                "temperature_sensor": round(random.uniform(70.0, 85.0), 1),
                "vibration_sensor": round(random.uniform(8.0, 12.0), 1),
                "humidity_sensor": round(random.uniform(75.0, 85.0), 1),
                "power_meter": round(random.uniform(40.0, 60.0), 1),
                "proximity_sensor": random.randint(30, 70),
            },
        },
    }


REGIONS = {
    "lan1": "mongodb://10.0.0.4:27018/",
    "lan2": "mongodb://10.0.1.4:27018/",
}


def seed(uri_lan1: str, uri_lan2: str, nodes_per_region: int, devices_per_region: int):
    lan1_device_ids = [f"lan1::device::{i:03d}" for i in range(1, devices_per_region + 1)]
    lan2_device_ids = [f"lan2::device::{i:03d}" for i in range(1, devices_per_region + 1)]
    local_ids = {"lan1": lan1_device_ids, "lan2": lan2_device_ids}
    foreign_ids = {"lan1": lan2_device_ids, "lan2": lan1_device_ids}

    uris = {"lan1": uri_lan1, "lan2": uri_lan2}

    for region, uri in uris.items():
        client = MongoClient(uri)
        db = client["edge_platform"]

        local = local_ids[region]
        foreign = foreign_ids[region]
        ops = []
        for i in range(1, nodes_per_region + 1):
            doc = make_node(region, i, local, foreign)
            ops.append(
                UpdateOne({"_id": doc["_id"]}, {"$set": doc}, upsert=True)
            )

        result = db["device_registry"].bulk_write(ops, ordered=False)
        print(f"[{region}] Upserted: {result.upserted_count}, Modified: {result.modified_count}")
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mongo-lan1", default=REGIONS["lan1"], help="MongoDB URI for LAN 1 primary")
    parser.add_argument("--mongo-lan2", default=REGIONS["lan2"], help="MongoDB URI for LAN 2 primary")
    parser.add_argument("--nodes", type=int, default=40)
    parser.add_argument("--devices", type=int, default=100)
    args = parser.parse_args()
    seed(args.mongo_lan1, args.mongo_lan2, args.nodes, args.devices)
