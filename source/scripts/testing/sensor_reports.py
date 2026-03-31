#!/usr/bin/env python3
"""
seed_sensor_reports.py

Populates the sensor_reports collection with heterogeneous device documents.
Each region's devices are seeded into that region's own replica-set primary.

Usage:
    python3 seed_sensor_reports.py --mongo-lan1 <uri> --mongo-lan2 <uri> --devices <N per region>
"""

import argparse
import random
from datetime import datetime, timezone
from pymongo import MongoClient, UpdateOne

DEVICE_TYPES = {
    "temperature_sensor": {
        "unit": "celsius",
        "payload_fn": lambda: {
            "value": round(random.uniform(18.0, 90.0), 2),
            "status": random.choice(["normal", "warning", "critical"]),
            "calibration_offset": round(random.uniform(-1.0, 1.0), 2),
        },
        "metadata_fn": lambda: {
            "firmware": random.choice(["v2.1.4", "v2.2.0", "v3.0.1"]),
            "location": f"floor_{random.randint(1,5)}_zone_{random.choice('ABCD')}",
            "alert_threshold": 80.0,
        },
    },
    "vibration_sensor": {
        "unit": "mm/s",
        "payload_fn": lambda: {
            "rms_velocity": round(random.uniform(0.1, 15.0), 3),
            "peak_frequency_hz": random.randint(10, 500),
            "status": random.choice(["normal", "warning", "critical"]),
            "bearing_fault_index": round(random.uniform(0.0, 1.0), 3),
        },
        "metadata_fn": lambda: {
            "firmware": random.choice(["v1.0.0", "v1.1.2"]),
            "machine_id": f"pump_{random.randint(100, 199)}",
            "alert_threshold": 10.0,
            "maintenance_due": random.choice([True, False]),
        },
    },
    "gps_tracker": {
        "unit": "degrees",
        "payload_fn": lambda: {
            "latitude": round(random.uniform(38.5, 38.8), 6),
            "longitude": round(random.uniform(-9.2, -9.0), 6),
            "speed_kmh": round(random.uniform(0.0, 120.0), 1),
            "status": random.choice(["normal", "warning"]),
            "hdop": round(random.uniform(0.8, 3.0), 1),
        },
        "metadata_fn": lambda: {
            "firmware": "v4.0.0",
            "vehicle_id": f"truck_{random.randint(200, 299)}",
            "alert_threshold": None,
            "route_id": f"route_{random.randint(1, 10)}",
        },
    },
    "air_quality_sensor": {
        "unit": "AQI",
        "payload_fn": lambda: {
            "aqi": random.randint(0, 300),
            "pm2_5": round(random.uniform(0.0, 150.0), 1),
            "pm10": round(random.uniform(0.0, 200.0), 1),
            "co2_ppm": random.randint(400, 2000),
            "status": random.choice(["normal", "warning", "critical"]),
        },
        "metadata_fn": lambda: {
            "firmware": random.choice(["v1.5.0", "v1.6.1"]),
            "location": f"building_{random.randint(1, 10)}_roof",
            "alert_threshold": 150,
            "outdoor": random.choice([True, False]),
        },
    },
    "pressure_sensor": {
        "unit": "bar",
        "payload_fn": lambda: {
            "value": round(random.uniform(0.5, 16.0), 3),
            "status": random.choice(["normal", "warning", "critical"]),
            "spike_detected": random.choice([True, False]),
        },
        "metadata_fn": lambda: {
            "firmware": random.choice(["v1.2.0", "v1.3.1"]),
            "pipe_id": f"pipe_{random.randint(1, 50)}",
            "alert_threshold": 10.0,
            "installation_year": random.randint(2018, 2024),
        },
    },
    "humidity_sensor": {
        "unit": "%RH",
        "payload_fn": lambda: {
            "value": round(random.uniform(10.0, 100.0), 2),
            "status": random.choice(["normal", "warning", "critical"]),
            "dew_point_celsius": round(random.uniform(5.0, 30.0), 1),
        },
        "metadata_fn": lambda: {
            "firmware": random.choice(["v2.0.0", "v2.1.0"]),
            "location": f"floor_{random.randint(1, 5)}_zone_{random.choice('ABCD')}",
            "alert_threshold": 80.0,
            "condensation_risk": random.choice([True, False]),
        },
    },
    "power_meter": {
        "unit": "kW",
        "payload_fn": lambda: {
            "consumption_kw": round(random.uniform(0.5, 100.0), 2),
            "voltage_v": round(random.uniform(210.0, 240.0), 1),
            "current_a": round(random.uniform(1.0, 50.0), 2),
            "status": random.choice(["normal", "warning", "critical"]),
            "power_factor": round(random.uniform(0.7, 1.0), 3),
        },
        "metadata_fn": lambda: {
            "firmware": random.choice(["v3.0.0", "v3.1.2"]),
            "panel_id": f"panel_{random.randint(1, 20)}",
            "alert_threshold": 50.0,
            "circuit_breaker": f"CB_{random.randint(1, 100)}",
        },
    },
    "flow_meter": {
        "unit": "L/min",
        "payload_fn": lambda: {
            "flow_rate": round(random.uniform(0.0, 400.0), 2),
            "status": random.choice(["normal", "warning", "critical"]),
            "total_volume_l": round(random.uniform(0.0, 10000.0), 1),
            "temperature_celsius": round(random.uniform(5.0, 80.0), 1),
        },
        "metadata_fn": lambda: {
            "firmware": random.choice(["v1.0.0", "v1.1.0"]),
            "pipe_id": f"pipe_{random.randint(1, 50)}",
            "alert_threshold": 200.0,
            "fluid_type": random.choice(["water", "coolant", "hydraulic_oil"]),
        },
    },
    "proximity_sensor": {
        "unit": "cm",
        "payload_fn": lambda: {
            "distance_cm": round(random.uniform(0.0, 200.0), 1),
            "motion_detected": random.choice([True, False]),
            "status": random.choice(["normal", "warning", "critical"]),
        },
        "metadata_fn": lambda: {
            "firmware": random.choice(["v1.0.0", "v1.0.5"]),
            "zone": f"zone_{random.choice('ABCDEF')}",
            "alert_threshold": 50,
            "mount_height_cm": random.randint(200, 500),
        },
    },
}

TAGS_POOL = {
    "temperature_sensor": ["industrial", "high-priority", "thermal"],
    "vibration_sensor": ["industrial", "mechanical", "predictive-maintenance"],
    "gps_tracker": ["logistics", "mobile", "fleet"],
    "air_quality_sensor": ["environmental", "outdoor", "compliance"],
    "pressure_sensor": ["industrial", "mechanical", "high-priority"],
    "humidity_sensor": ["environmental", "thermal", "compliance"],
    "power_meter": ["industrial", "high-priority", "logistics"],
    "flow_meter": ["industrial", "mechanical", "logistics"],
    "proximity_sensor": ["industrial", "logistics", "environmental"],
}


def make_device(region: str, index: int) -> dict:
    device_type = random.choice(list(DEVICE_TYPES.keys()))
    spec = DEVICE_TYPES[device_type]
    device_id = f"{region}::device::{index:03d}"
    tags = random.sample(TAGS_POOL[device_type], k=random.randint(1, len(TAGS_POOL[device_type])))

    return {
        "_id": device_id,
        "region_origin": region,
        "device_type": device_type,
        "tags": tags,
        "unit": spec["unit"],
        "payload": spec["payload_fn"](),
        "metadata": spec["metadata_fn"](),
        "last_updated": datetime.now(timezone.utc),
    }


REGIONS = {
    "lan1": "mongodb://10.0.0.4:27018/",
    "lan2": "mongodb://10.0.1.4:27018/",
}


def seed(uri_lan1: str, uri_lan2: str, devices_per_region: int):
    uris = {"lan1": uri_lan1, "lan2": uri_lan2}

    for region, uri in uris.items():
        client = MongoClient(uri)
        collection = client["edge_platform"]["sensor_reports"]

        ops = []
        for i in range(1, devices_per_region + 1):
            doc = make_device(region, i)
            ops.append(
                UpdateOne({"_id": doc["_id"]}, {"$set": doc}, upsert=True)
            )

        result = collection.bulk_write(ops, ordered=False)
        print(f"[{region}] Upserted: {result.upserted_count}, Modified: {result.modified_count}")
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mongo-lan1", default=REGIONS["lan1"], help="MongoDB URI for LAN 1 primary")
    parser.add_argument("--mongo-lan2", default=REGIONS["lan2"], help="MongoDB URI for LAN 2 primary")
    parser.add_argument("--devices", type=int, default=50, help="Devices per region")
    args = parser.parse_args()
    seed(args.mongo_lan1, args.mongo_lan2, args.devices)