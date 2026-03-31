#!/usr/bin/env python3
"""
export_workload_snapshot.py

Exports device and node data from MongoDB to JSON files for use by the
traffic generator. Decouples experiment execution from a live database.

Usage:
    python3 export_workload_snapshot.py \
      [--mongo-lan1 mongodb://10.0.0.4:27018/] \
      [--mongo-lan2 mongodb://10.0.1.4:27018/] \
      [--output-dir data/workload_snapshot]
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
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        docs = list(
            client["edge_platform"]["sensor_reports"].find(
                {}, {"_id": 1, "region_origin": 1}
            )
        )
        all_devices.extend(docs)
        client.close()
        print(f"  [{region}] {len(docs)} devices")

    out_devices = os.path.join(output_dir, "sensor_devices.json")
    with open(out_devices, "w") as f:
        json.dump(all_devices, f, indent=2, default=str)
    print(f"Exported {len(all_devices)} devices → {out_devices}")

    # --- device_registry: _id, home_region, subscribed_tags, watched_devices ---
    all_nodes = []
    for region, uri in uris.items():
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        docs = list(
            client["edge_platform"]["device_registry"].find(
                {},
                {"_id": 1, "home_region": 1, "subscribed_tags": 1, "watched_devices": 1},
            )
        )
        all_nodes.extend(docs)
        client.close()
        print(f"  [{region}] {len(docs)} nodes")

    out_nodes = os.path.join(output_dir, "device_registry.json")
    with open(out_nodes, "w") as f:
        json.dump(all_nodes, f, indent=2, default=str)
    print(f"Exported {len(all_nodes)} nodes → {out_nodes}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Export seeded MongoDB data to JSON for the traffic generator"
    )
    parser.add_argument("--mongo-lan1", default=REGIONS["lan1"], metavar="URI")
    parser.add_argument("--mongo-lan2", default=REGIONS["lan2"], metavar="URI")
    parser.add_argument(
        "--output-dir", default="data/workload_snapshot", metavar="DIR"
    )
    args = parser.parse_args()
    export(args.mongo_lan1, args.mongo_lan2, args.output_dir)
