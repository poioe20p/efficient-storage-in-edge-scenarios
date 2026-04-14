#!/usr/bin/env python3
"""
seed_device_registry.py

Populates device_registry with edge node subscription profiles.
Each region's nodes are seeded into that region's own replica-set primary.

watched_devices distribution per region:
  ~70%  local-only   — watch 3-8 devices from own region
  ~25%  mixed        — watch devices from both own and foreign region
  ~5%   foreign-only — watch 3-8 devices from the other region
This creates the cross-region access pattern needed for Phase 2.

Usage:
    python3 seed_device_registry.py --mongo-lan1 <uri> --mongo-lan2 <uri> --nodes <N per region>
"""

import argparse
import random
from pymongo import MongoClient, UpdateOne


def make_node(region: str, index: int, local_device_ids: list[str], foreign_device_ids: list[str]) -> dict:
    node_id = f"{region}::node::{index:03d}"
    home = region

    # Distribution: ~70% local-only, ~25% mixed (local+foreign), ~5% foreign-only
    roll = random.random()
    k = random.randint(3, 8)
    if roll < 0.70:
        # Local-only: watch devices from own region
        watched = random.sample(local_device_ids, k=min(k, len(local_device_ids)))
    elif roll < 0.95:
        # Mixed: some local + some foreign
        n_foreign = random.randint(1, max(1, k // 2))
        n_local = k - n_foreign
        watched = (
            random.sample(local_device_ids, k=min(n_local, len(local_device_ids)))
            + random.sample(foreign_device_ids, k=min(n_foreign, len(foreign_device_ids)))
        )
    else:
        # Foreign-only: watch devices from the other region
        watched = random.sample(foreign_device_ids, k=min(k, len(foreign_device_ids)))

    return {
        "_id": node_id,
        "home_region": home,
        "subscribed_tags": random.sample(
            ["industrial", "high-priority", "thermal", "mechanical",
             "logistics", "environmental"],
            k=random.randint(1, 3)
        ),
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
