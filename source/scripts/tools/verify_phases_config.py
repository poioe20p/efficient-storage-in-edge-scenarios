import json, sys

# Read from the first run's phases_snapshot
path = sys.argv[1] if len(sys.argv) > 1 else "source/scripts/testing/metrics/20260703_004628_rq1_v2final_push_1/phases_snapshot.json"
with open(path) as f:
    d = json.load(f)
print("Phase                           Dur(s)  Rate  Cross%  Write%")
print("-" * 75)
for p in d["phases"]:
    mix = p.get("mix", {})
    writes = sum(v for k, v in mix.items() if "update" in k or "aggregate" in k)
    total = sum(mix.values())
    writes_pct = writes/total*100 if total else 0
    cross = p.get("cross_region_ratio", 0)*100
    rate = p.get("rate_per_client", 0)
    rtypes = ", ".join(f"{k}={v:.2f}" for k, v in sorted(mix.items()))
    print(f"{p['name']:<32s} {p['duration_s']:>4d}  {rate:>4.1f}  {cross:>5.0f}%  {writes_pct:>5.0f}%   [{rtypes}]")
