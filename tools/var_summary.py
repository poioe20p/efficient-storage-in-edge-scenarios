"""Final variance summary — comparison of complete runs B and C."""
import csv

RUNS = [
    ("Run B", "source/scripts/testing/metrics/variance_reduction_b/client_requests.csv"),
    ("Run C", "source/scripts/testing/metrics/variance_reduction_c/client_requests.csv"),
]

# Also read Run A for non-compute phase comparison
RUN_A_PATH = "source/scripts/testing/metrics/variance_reduction_a/client_requests.csv"

print("=" * 70)
print("VARIANCE REDUCTION EXPERIMENT — FINAL ANALYSIS")
print("=" * 70)

all_data = {}
for name, path in RUNS:
    phases = {}
    total = 0
    fail = 0
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            status = int(row["http_status"])
            if status != 200:
                fail += 1
            p = row["phase"]
            if p not in phases:
                phases[p] = {"total": 0, "fail": 0}
            phases[p]["total"] += 1
            if status != 200:
                phases[p]["fail"] += 1
    all_data[name] = {"total": total, "fail": fail, "phases": phases}
    print(f"\n{name}: {total} reqs, {fail} fail ({fail/total*100:.2f}%)")

# Add Run A
phases_a = {}
total_a = 0
fail_a = 0
with open(RUN_A_PATH, newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        total_a += 1
        status = int(row["http_status"])
        if status != 200:
            fail_a += 1
        p = row["phase"]
        if p not in phases_a:
            phases_a[p] = {"total": 0, "fail": 0}
        phases_a[p]["total"] += 1
        if status != 200:
            phases_a[p]["fail"] += 1
all_data["Run A"] = {"total": total_a, "fail": fail_a, "phases": phases_a}
print(f"Run A (partial, 6/10): {total_a} reqs, {fail_a} fail ({fail_a/total_a*100:.2f}%)")

# Per-phase comparison (shared phases across all runs)
print("\n--- Per-Phase Failure Rate Comparison ---")
print(f"{'Phase':<28} {'Run A':>10} {'Run B':>10} {'Run C':>10} {'Range(B,C)':>12}")
print("-" * 70)

all_phases = ["baseline", "local_moderate", "storage_stress", "cross_region_hotspot",
              "inter_hotspot_cooldown", "reverse_hotspot",
              "compute_ramp", "compute_spike", "sustained_plateau", "demand_drop"]

for phase in all_phases:
    rates = {}
    for name in ["Run A", "Run B", "Run C"]:
        pdata = all_data[name]["phases"].get(phase)
        if pdata and pdata["total"] > 0:
            rates[name] = pdata["fail"] / pdata["total"] * 100
        else:
            rates[name] = None

    # Compute range for complete runs only (B, C)
    r_b = rates.get("Run B")
    r_c = rates.get("Run C")
    rng = ""
    if r_b is not None and r_c is not None:
        rng = f"{abs(r_b - r_c):.1f} pp"

    def fmt(v):
        return f"{v:>9.2f}%" if v is not None else "       N/A"

    print(f"{phase:<28} {fmt(rates.get('Run A'))} {fmt(rates.get('Run B'))} {fmt(rates.get('Run C'))} {rng:>12}")

# Variance metrics (B and C only — complete runs)
print("\n--- Variance Metrics (Runs B & C — complete 10-phase runs) ---")
b = all_data["Run B"]
c = all_data["Run C"]
b_rate = b["fail"] / b["total"] * 100
c_rate = c["fail"] / c["total"] * 100
print(f"Overall failure rate: B={b_rate:.2f}%, C={c_rate:.2f}%")
print(f"Range (max-min): {abs(b_rate - c_rate):.2f} percentage points")
print(f"Mean: {(b_rate + c_rate)/2:.2f}%")
print(f"Target: <=3 pp range => {'MET' if abs(b_rate - c_rate) <= 3 else 'MISSED — ' + str(abs(b_rate - c_rate)):.1f} pp")

# Non-compute phase variance (phases 1-6)
non_compute_phases = ["baseline", "local_moderate", "storage_stress", "cross_region_hotspot",
                       "inter_hotspot_cooldown", "reverse_hotspot"]
print("\n--- Non-Compute Phases (1-6) Variance ---")
for phase in non_compute_phases:
    pb = b["phases"].get(phase, {"total": 0, "fail": 0})
    pc = c["phases"].get(phase, {"total": 0, "fail": 0})
    rb = pb["fail"] / pb["total"] * 100 if pb["total"] else 0
    rc = pc["fail"] / pc["total"] * 100 if pc["total"] else 0
    rng = abs(rb - rc)
    status = "OK" if rng <= 5 else "HIGH"
    print(f"  {phase:<28}: B={rb:.2f}% C={rc:.2f}% range={rng:.2f} pp [{status}]")

# Compute phase variance
print("\n--- Compute Phases (7-9) Variance ---")
for phase in ["compute_ramp", "compute_spike", "sustained_plateau"]:
    pb = b["phases"].get(phase, {"total": 0, "fail": 0})
    pc = c["phases"].get(phase, {"total": 0, "fail": 0})
    rb = pb["fail"] / pb["total"] * 100 if pb["total"] else 0
    rc = pc["fail"] / pc["total"] * 100 if pc["total"] else 0
    rng = abs(rb - rc)
    status = "OK" if rng <= 5 else "EXTREME"
    print(f"  {phase:<28}: B={rb:.2f}% C={rc:.2f}% range={rng:.2f} pp [{status}]")

# Total request volume
print(f"\nRequest volume: B={b['total']}, C={c['total']}")
vol_range = abs(b["total"] - c["total"]) / ((b["total"] + c["total"]) / 2) * 100
print(f"Volume range: {vol_range:.1f}% of mean (target <=10%) => {'MET' if vol_range <= 10 else 'MISSED'}")

print("\n" + "=" * 70)
print("KEY FINDING: Run B suffered catastrophic failure in compute phases")
print("due to elasticity scale-DOWN during peak load (net removal of edge")  
print("servers during compute_spike). Run C scaled UP properly.")
print("=" * 70)
