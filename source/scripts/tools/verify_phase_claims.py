import csv, os, sys
from collections import Counter

base = "source/scripts/testing/metrics"
runs = [
    "rq1_v2final_push_1", "rq1_v2final_push_2", "rq1_v2final_push_3",
    "rq1_v2final_poll5_1", "rq1_v2final_poll5_2", "rq1_v2final_poll5_3",
    "rq1_v2final_poll12_1", "rq1_v2final_poll12_2", "rq1_v2final_poll12_3",
    "rq1_v2final_poll30_1", "rq1_v2final_poll30_2", "rq1_v2final_poll30_3"
]

phases_order = ["baseline", "storage_storm", "tier1_hotspot", "inter_hotspot_cooldown", "reverse_hotspot", "compute_spike", "demand_drop"]

print("=" * 100)
print(f"{'Run':<30s} {'Total':>6s} {'Fails':>6s} {'Rate':>7s}  storage_storm  tier1_hotspot reverse_hotspot compute_spike")
print("=" * 100)

for r in runs:
    for d in os.listdir(base):
        if r in d:
            path = os.path.join(base, d, "client_requests.csv")
            if not os.path.exists(path):
                print(f"{r:<30s} NO FILE")
                continue
            rows = list(csv.DictReader(open(path)))
            pc = Counter()
            pf = Counter()
            for row in rows:
                ph = row["phase"]
                pc[ph] += 1
                if row["http_status"] == "0":
                    pf[ph] += 1
            
            total = len(rows)
            fails = sum(pf.values())
            rate = fails/total*100
            
            parts = []
            for ph in ["storage_storm", "tier1_hotspot", "reverse_hotspot", "compute_spike"]:
                if pc[ph] > 0:
                    parts.append(f"{pf[ph]/pc[ph]*100:5.1f}%")
                else:
                    parts.append("   n/a")
            
            print(f"{r:<30s} {total:>6d} {fails:>6d} {rate:>6.2f}%  {parts[0]:>11s}  {parts[1]:>11s}  {parts[2]:>11s}  {parts[3]:>11s}")
            break

print()

# Now aggregate by mode (healthy runs only - rate < 5%)
print("=" * 80)
print("HEALTHY RUNS ONLY (rate < 5pct)")
print("=" * 80)
modes = {"push": [], "poll5": [], "poll12": [], "poll30": []}
for r in runs:
    for d in os.listdir(base):
        if r in d:
            path = os.path.join(base, d, "client_requests.csv")
            if not os.path.exists(path):
                continue
            rows = list(csv.DictReader(open(path)))
            total = len(rows)
            fails = sum(1 for row in rows if row["http_status"] == "0")
            rate = fails/total*100
            if rate < 5.0:
                for mode in modes:
                    if mode in r:
                        modes[mode].append((r, rate, rows))
            break

for mode, run_list in sorted(modes.items()):
    if not run_list:
        print(f"\n{mode}: NO healthy runs")
        continue
    print(f"\n{mode} ({len(run_list)} healthy runs):")
    for rname, rate, rows in run_list:
        pc = Counter()
        pf = Counter()
        for row in rows:
            ph = row["phase"]
            pc[ph] += 1
            if row["http_status"] == "0":
                pf[ph] += 1
        total = len(rows)
        phase_rates = {}
        for ph in phases_order:
            if pc[ph] > 0:
                phase_rates[ph] = pf[ph]/pc[ph]*100
        phase_str = " ".join(f"{ph}={phase_rates.get(ph,0):.1f}%" for ph in phases_order if pc.get(ph,0) > 0)
        print(f"  {rname}: {rate:.1f}%  [{phase_str}]")
