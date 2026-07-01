"""Replace phases.json with the RQ1 v2 7-phase mixed workload.

Writes the canonical 7-phase spec (baseline → storage_storm → tier1_hotspot →
inter_hotspot_cooldown → reverse_hotspot → compute_spike → demand_drop)
to source/scripts/testing/phases.json.

Usage:
    python fix_phases.py [--dry-run]
"""
import json
import shutil
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
PHASES_PATH = REPO_ROOT / "source" / "scripts" / "testing" / "phases.json"

PHASES_7 = {
    "phases": [
        {
            "name": "baseline",
            "duration_s": 60,
            "rate_per_client": 1.0,
            "cross_region_ratio": 0.0,
            "client_fraction": 0.5,
            "mix": {"device_status": 0.60, "dashboard": 0.25, "service_pressure": 0.15},
        },
        {
            "name": "storage_storm",
            "duration_s": 240,
            "rate_per_client": 4.0,
            "cross_region_ratio": 0.90,
            "hotspot_direction": "",
            "client_fraction": 1.0,
            "mix": {
                "device_status": 0.35, "dashboard": 0.10, "service_pressure": 0.05,
                "device_update": 0.30, "device_aggregate": 0.20,
            },
        },
        {
            "name": "tier1_hotspot",
            "duration_s": 180,
            "rate_per_client": 5.0,
            "cross_region_ratio": 0.95,
            "hotspot_direction": "",
            "client_fraction": 1.0,
            "mix": {
                "device_status": 0.80, "dashboard": 0.05, "service_pressure": 0.05,
                "device_update": 0.05, "device_aggregate": 0.05,
            },
        },
        {
            "name": "inter_hotspot_cooldown",
            "duration_s": 300,
            "rate_per_client": 1.0,
            "cross_region_ratio": 0.0,
            "client_fraction": 0.10,
            "mix": {"device_status": 0.60, "dashboard": 0.25, "service_pressure": 0.15},
        },
        {
            "name": "reverse_hotspot",
            "duration_s": 180,
            "rate_per_client": 5.0,
            "cross_region_ratio": 0.95,
            "hotspot_direction": "",
            "client_fraction": 1.0,
            "mix": {
                "device_status": 0.80, "dashboard": 0.05, "service_pressure": 0.05,
                "device_update": 0.05, "device_aggregate": 0.05,
            },
        },
        {
            "name": "compute_spike",
            "duration_s": 180,
            "rate_per_client": 4.0,
            "cross_region_ratio": 0.05,
            "hotspot_direction": "",
            "client_fraction": 1.0,
            "mix": {"device_status": 0.20, "dashboard": 0.65, "service_pressure": 0.15},
        },
        {
            "name": "demand_drop",
            "duration_s": 300,
            "rate_per_client": 1.0,
            "cross_region_ratio": 0.0,
            "client_fraction": 0.10,
            "mix": {"device_status": 0.60, "dashboard": 0.25, "service_pressure": 0.15},
        },
    ]
}


def fix(dry_run: bool = False) -> None:
    if not PHASES_PATH.exists():
        print(f"ERROR: {PHASES_PATH} not found")
        sys.exit(1)

    current = json.loads(PHASES_PATH.read_text())
    current_names = [p["name"] for p in current.get("phases", [])]
    if current_names == [p["name"] for p in PHASES_7["phases"]]:
        print("phases.json already has the 7-phase workload — no changes needed.")
        return

    if dry_run:
        print(f"Would replace {len(current_names)} phases ({current_names})")
        print(f"With 7 phases: {[p['name'] for p in PHASES_7['phases']]}")
    else:
        shutil.copy(PHASES_PATH, str(PHASES_PATH) + ".bak")
        PHASES_PATH.write_text(json.dumps(PHASES_7, indent=2) + "\n")
        print(f"Written 7 phases to {PHASES_PATH}:")
        for p in PHASES_7["phases"]:
            print(f"  {p['name']}: {p['duration_s']}s")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    fix(dry_run=dry_run)
