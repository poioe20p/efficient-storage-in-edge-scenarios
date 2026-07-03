import csv, os

base = "source/scripts/testing/metrics"
runs = [
    "rq1_v2final_push_1", "rq1_v2final_push_2", "rq1_v2final_push_3",
    "rq1_v2final_poll5_1", "rq1_v2final_poll5_2", "rq1_v2final_poll5_3",
    "rq1_v2final_poll12_1", "rq1_v2final_poll12_2", "rq1_v2final_poll12_3",
    "rq1_v2final_poll30_1", "rq1_v2final_poll30_2", "rq1_v2final_poll30_3",
]
phases_order = ["baseline", "storage_storm", "tier1_hotspot", "inter_hotspot_cooldown", "reverse_hotspot", "compute_spike", "demand_drop"]

print("Per-phase failure rates for ALL runs:")
print(f"{'Run':<30s} {'Total':>6s} {'Rate':>7s}  baseline  demand_drop  storage_storm  tier1_hotspot  reverse_hotspot  compute_spike")
print("-" * 130)

for r in runs:
    for d in os.listdir(base):
        if r in d:
            path = os.path.join(base, d, "client_requests.csv")
            if not os.path.exists(path):
                continue
            rows = list(csv.DictReader(open(path)))
            from collections import Counter
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
            for ph in ["baseline", "demand_drop", "storage_storm", "tier1_hotspot", "reverse_hotspot", "compute_spike"]:
                if pc.get(ph, 0) > 0:
                    parts.append(f"{pf[ph]/pc[ph]*100:5.1f}%")
                else:
                    parts.append("   n/a")
            print(f"{r:<30s} {total:>6d} {rate:>6.2f}%  {parts[0]:>8s}  {parts[1]:>8s}  {parts[2]:>13s}  {parts[3]:>11s}  {parts[4]:>13s}  {parts[5]:>11s}")
            break
