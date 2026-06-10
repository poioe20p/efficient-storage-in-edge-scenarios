"""Variance reduction analysis — per-run, per-LAN, per-phase breakdown."""
import csv
import sys
import os

RUNS = [
    ("Run A", os.path.join("source", "scripts", "testing", "metrics", "variance_reduction_a", "client_requests.csv")),
    ("Run B", os.path.join("source", "scripts", "testing", "metrics", "variance_reduction_b", "client_requests.csv")),
    ("Run C", os.path.join("source", "scripts", "testing", "metrics", "variance_reduction_c", "client_requests.csv")),
]

for name, path in RUNS:
    lan_stats = {}
    phase_lan = {}
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            lan = row["client_lan"]
            status = int(row["http_status"])
            phase = row["phase"]

            if lan not in lan_stats:
                lan_stats[lan] = {"total": 0, "fail": 0}
            lan_stats[lan]["total"] += 1
            if status != 200:
                lan_stats[lan]["fail"] += 1

            key = (phase, lan)
            if key not in phase_lan:
                phase_lan[key] = {"total": 0, "fail": 0}
            phase_lan[key]["total"] += 1
            if status != 200:
                phase_lan[key]["fail"] += 1

    print(f"=== {name} — LAN-specific ===")
    for lan in sorted(lan_stats.keys()):
        s = lan_stats[lan]
        r = (s["fail"] / s["total"] * 100) if s["total"] else 0
        print(f"  {lan}: {s['total']} reqs, {s['fail']} fail ({r:.2f}%)")

    for phase in ["compute_ramp", "compute_spike", "sustained_plateau"]:
        for lan in ["lan1", "lan2"]:
            key = (phase, lan)
            if key in phase_lan:
                s = phase_lan[key]
                r = (s["fail"] / s["total"] * 100) if s["total"] else 0
                print(f"  {phase}/{lan}: {s['total']} reqs, {s['fail']} fail ({r:.2f}%)")
    print()
