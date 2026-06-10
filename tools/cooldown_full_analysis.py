"""Full analysis of cooldown_180_verify — LAN breakdown, elasticity, container lifecycle."""
import csv
from collections import defaultdict

RUN = "source/scripts/testing/metrics/cooldown_180_verify"
PHASES_ORDER = [
    "baseline", "local_moderate", "storage_stress", "cross_region_hotspot",
    "inter_hotspot_cooldown", "reverse_hotspot",
    "compute_ramp", "compute_spike", "sustained_plateau", "demand_drop",
]

print("=" * 70)
print("COOLDOWN_180_VERIFY — FULL ANALYSIS")
print("=" * 70)

# ── 1. Client requests: overall + per-phase + per-LAN ──────────────────
print("\n── 1. Client Requests ──")
total = 0
failures = 0
phases = defaultdict(lambda: {"total": 0, "fail": 0})
phase_lan = defaultdict(lambda: {"total": 0, "fail": 0})
lan_stats = defaultdict(lambda: {"total": 0, "fail": 0})
http_codes = defaultdict(int)

with open(f"{RUN}/client_requests.csv", newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        total += 1
        status = int(row["http_status"])
        if status != 200:
            failures += 1
        http_codes[str(status)] += 1
        p = row["phase"]
        lan = row["client_lan"]
        phases[p]["total"] += 1
        if status != 200:
            phases[p]["fail"] += 1
        phase_lan[(p, lan)]["total"] += 1
        if status != 200:
            phase_lan[(p, lan)]["fail"] += 1
        lan_stats[lan]["total"] += 1
        if status != 200:
            lan_stats[lan]["fail"] += 1

print(f"Total: {total}, Failures: {failures}, Rate: {failures/total*100:.2f}%")
print(f"HTTP codes: {dict(http_codes)}")

print("\nPer-phase:")
print(f"{'Phase':<28} {'Total':>7} {'Fail':>7} {'Rate':>8} {'LAN1':>8} {'LAN2':>8}")
print("-" * 70)
for p in PHASES_ORDER:
    if p in phases:
        pt = phases[p]["total"]
        pf = phases[p]["fail"]
        pr = pf/pt*100 if pt else 0
        l1 = phase_lan.get((p, "lan1"), {"total": 0, "fail": 0})
        l2 = phase_lan.get((p, "lan2"), {"total": 0, "fail": 0})
        r1 = l1["fail"]/l1["total"]*100 if l1["total"] else 0
        r2 = l2["fail"]/l2["total"]*100 if l2["total"] else 0
        print(f"{p:<28} {pt:>7} {pf:>7} {pr:>7.2f}% {r1:>7.2f}% {r2:>7.2f}%")

print(f"\nLAN totals:")
for lan in sorted(lan_stats):
    s = lan_stats[lan]
    r = s["fail"]/s["total"]*100 if s["total"] else 0
    print(f"  {lan}: {s['total']} reqs, {s['fail']} fail ({r:.2f}%)")

# ── 2. Container events ────────────────────────────────────────────────
print("\n── 2. Container Events ──")
ce_path = f"{RUN}/container_events.csv"
events_by_phase = defaultdict(list)
with open(ce_path, newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        events_by_phase[row["phase"]].append(row)

for p in PHASES_ORDER:
    events = events_by_phase.get(p, [])
    added = [e for e in events if e["event"] == "added"]
    removed = [e for e in events if e["event"] == "removed"]
    print(f"\n  {p}: {len(events)} events ({len(added)} + / {len(removed)} -)")
    for a in added:
        print(f"    + {a['container']} ({a['image']})")
    for r in removed:
        print(f"    - {r['container']} ({r['image']})")

# ── 3. Elasticity events ────────────────────────────────────────────────
print("\n── 3. Elasticity Events ──")
ee_path = f"{RUN}/elasticity_events.csv"
ee_by_type = defaultdict(list)
with open(ee_path, newline="") as f:
    reader = csv.DictReader(f)
    for row in reader:
        ee_by_type[row.get("event_type", row.get("type", "unknown"))].append(row)

for etype, events in sorted(ee_by_type.items()):
    print(f"  {etype}: {len(events)} events")
    if len(events) <= 5:
        for e in events:
            print(f"    {e}")

# ── 4. Comparison with Run B and Run C ──────────────────────────────────
print("\n── 4. Cross-Run Comparison ──")
REF_RUNS = {
    "Run B (120s)": "source/scripts/testing/metrics/variance_reduction_b/client_requests.csv",
    "Run C (120s)": "source/scripts/testing/metrics/variance_reduction_c/client_requests.csv",
}
results = {}
for name, path in REF_RUNS.items():
    t = 0; f_ = 0; ph = defaultdict(lambda: {"total": 0, "fail": 0})
    with open(path, newline="") as ff:
        reader = csv.DictReader(ff)
        for row in reader:
            t += 1
            if int(row["http_status"]) != 200:
                f_ += 1
            ph[row["phase"]]["total"] += 1
            if int(row["http_status"]) != 200:
                ph[row["phase"]]["fail"] += 1
    results[name] = {"total": t, "fail": f_, "phases": ph}

# Also add this run
results["Verify (180s)"] = {"total": total, "fail": failures, "phases": dict(phases)}

COMPUTE_PHASES = ["compute_ramp", "compute_spike", "sustained_plateau", "demand_drop"]
print(f"{'Phase':<22} {'Run B (120s)':>14} {'Run C (120s)':>14} {'Verify (180s)':>15}")
print("-" * 68)
for p in COMPUTE_PHASES:
    vals = []
    for name in ["Run B (120s)", "Run C (120s)", "Verify (180s)"]:
        pd = results[name]["phases"].get(p, {"total": 0, "fail": 0})
        r = pd["fail"]/pd["total"]*100 if pd["total"] else 0
        vals.append(f"{r:.2f}%")
    print(f"{p:<22} {vals[0]:>14} {vals[1]:>14} {vals[2]:>15}")

# Overall
print("-" * 68)
vals = []
for name in ["Run B (120s)", "Run C (120s)", "Verify (180s)"]:
    r = results[name]["fail"]/results[name]["total"]*100
    vals.append(f"{r:.2f}%")
print(f"{'OVERALL':<22} {vals[0]:>14} {vals[1]:>14} {vals[2]:>15}")

print("\n── 5. Verdict ──")
v_rate = failures/total*100
print(f"Verification run: {v_rate:.2f}% overall")
print(f"Run C (best prior): 0.26%")
print(f"Difference: {abs(v_rate - 0.26):.2f} pp")
if v_rate <= 1.0:
    print("✅ PASS — well within ≤3% target")
else:
    print("❌ FAIL")

# Check compute phase ceiling
max_compute = max(
    phases[p]["fail"]/phases[p]["total"]*100
    for p in COMPUTE_PHASES
    if p in phases and phases[p]["total"] > 0
)
print(f"Max compute phase failure: {max_compute:.2f}% (target ≤5%)")
if max_compute <= 5:
    print("✅ PASS — all compute phases ≤5%")
else:
    print("⚠️  Some compute phases exceed 5%")

print("\n" + "=" * 70)
