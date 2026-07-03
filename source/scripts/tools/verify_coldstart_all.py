import csv, os, json
from datetime import datetime, timezone

base = "source/scripts/testing/metrics"
targets = [
    "push_1", "push_2", "push_3",
    "poll5_1", "poll5_2", "poll5_3",
    "poll12_1", "poll12_2", "poll12_3",
    "poll30_1", "poll30_2", "poll30_3",
]

print(f"{'Run':<15s} {'Mode':<7s} {'First 60s reqs':>14s} {'First 60s fails':>15s} {'Rate':>7s} {'Post-120s reqs':>14s} {'Post-120s fails':>15s} {'Rate':>7s}")
print("-" * 105)

for target in targets:
    for d in os.listdir(base):
        if target in d:
            run_dir = os.path.join(base, d)
            
            ps_path = os.path.join(run_dir, "phases_snapshot.json")
            phases = []
            if os.path.exists(ps_path):
                pd = json.load(open(ps_path))
                t = 0
                for p in pd["phases"]:
                    phases.append((p["name"], t, t + p["duration_s"]))
                    t += p["duration_s"]
            
            storm_start, storm_end = None, None
            for name, s, e in phases:
                if name == "storage_storm":
                    storm_start, storm_end = s, e
            
            cr_path = os.path.join(run_dir, "client_requests.csv")
            if not os.path.exists(cr_path):
                continue
            
            cr_rows = list(csv.DictReader(open(cr_path)))
            
            # Get t0 from resource_stats
            rs_path = os.path.join(run_dir, "resource_stats.csv")
            t0 = None
            if os.path.exists(rs_path):
                rs_rows = list(csv.DictReader(open(rs_path)))
                if rs_rows:
                    t0 = t0_dt = datetime.fromisoformat(rs_rows[0]["timestamp"].replace("Z", "+00:00")).timestamp()
            
            if t0 is None:
                continue
            
            # Categorize requests
            first60 = []
            post120 = []
            for r in cr_rows:
                ts_dt = datetime.fromisoformat(r["timestamp"].replace("+00:00", "+00:00"))
                ts_rel = ts_dt.timestamp() - t0
                if storm_start <= ts_rel < storm_start + 60:
                    first60.append(r)
                elif storm_start + 120 <= ts_rel <= storm_end:
                    post120.append(r)
            
            f60_total = len(first60)
            f60_fails = sum(1 for r in first60 if r.get("http_status") == "0")
            f60_rate = f60_fails / max(f60_total, 1) * 100
            
            p120_total = len(post120)
            p120_fails = sum(1 for r in post120 if r.get("http_status") == "0")
            p120_rate = p120_fails / max(p120_total, 1) * 100
            
            mode = "push" if "push" in target else ("poll5" if "poll5" in target else ("poll12" if "poll12" in target else "poll30"))
            
            print(f"{target:<15s} {mode:<7s} {f60_total:>14d} {f60_fails:>15d} {f60_rate:>6.1f}% {p120_total:>14d} {p120_fails:>15d} {p120_rate:>6.1f}%")
            break
