"""Analyze container events and per-node stats for variance experiment."""
import csv
import os
from collections import defaultdict

RUNS = [
    ("Run B", "source/scripts/testing/metrics/variance_reduction_b"),
    ("Run C", "source/scripts/testing/metrics/variance_reduction_c"),
]

for name, folder in RUNS:
    # Container events
    ce_path = os.path.join(folder, "container_events.csv")
    events_by_phase = defaultdict(list)
    with open(ce_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            phase = row["phase"]
            events_by_phase[phase].append(row)

    print(f"=== {name} — Container events by phase ===")
    for phase in ["storage_stress", "cross_region_hotspot", "reverse_hotspot",
                   "compute_ramp", "compute_spike", "sustained_plateau"]:
        events = events_by_phase.get(phase, [])
        added = [e for e in events if e["event"] == "added"]
        removed = [e for e in events if e["event"] == "removed"]
        state_changes = [e for e in events if e["event"] == "state_change"]
        print(f"  {phase}: {len(events)} events ({len(added)} added, {len(removed)} removed, {len(state_changes)} state_change)")
        for a in added:
            print(f"    + {a['container']} ({a['image']})")
        for r in removed:
            print(f"    - {r['container']} ({r['image']})")

    # Per-node stats — count unique nodes and max servers per phase
    pns_path = os.path.join(folder, "per_node_stats.csv")
    if os.path.exists(pns_path):
        nodes_by_phase = defaultdict(set)
        with open(pns_path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                phase = row.get("phase", "")
                node = row.get("node_id", "")
                if phase and node:
                    nodes_by_phase[phase].add(node)
        print(f"  Unique nodes per phase:")
        for phase in ["compute_ramp", "compute_spike", "sustained_plateau"]:
            nodes = nodes_by_phase.get(phase, set())
            # Filter edge_server nodes
            edge_nodes = [n for n in nodes if "edge_server" in n.lower() or "lan" in n.lower()]
            print(f"    {phase}: {len(nodes)} total nodes")
    print()
