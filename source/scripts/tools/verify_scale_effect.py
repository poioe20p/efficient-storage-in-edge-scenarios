import csv, os, json
from datetime import datetime, timezone

base = "source/scripts/testing/metrics"

for d in os.listdir(base):
    if "push_1" in d:
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
        
        rs_path = os.path.join(run_dir, "resource_stats.csv")
        t0 = None
        rs_rows = []
        if os.path.exists(rs_path):
            rs_rows = list(csv.DictReader(open(rs_path)))
            if rs_rows:
                t0_dt = datetime.fromisoformat(rs_rows[0]["timestamp"].replace("Z", "+00:00"))
                t0 = t0_dt.timestamp()
        
        if t0 is None:
            print("Cannot determine t0")
            break
        
        print(f"=== push_1: storage_storm {storm_start}-{storm_end}s ===")
        
        # Resource transitions
        storm_rs = []
        for r in rs_rows:
            ts_dt = datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00"))
            ts_rel = ts_dt.timestamp() - t0
            if storm_start - 10 <= ts_rel <= storm_end + 10:
                storm_rs.append((ts_rel, r))
        
        print(f"\nResource count transitions (t={storm_start-10:.0f} to t={storm_end+10:.0f}s):")
        prev_s, prev_c = None, None
        for ts_rel, r in storm_rs:
            s = int(r.get("storage_count", 0))
            c = int(r.get("server_count", 0))
            if prev_s is not None and (s != prev_s or c != prev_c):
                marker = " <<< storage_storm START" if abs(ts_rel - storm_start) < 2 else ""
                if abs(ts_rel - storm_end) < 2:
                    marker = " <<< storage_storm END"
                print(f"  t={ts_rel:>7.1f}s  storage: {prev_s}->{s}  compute: {prev_c}->{c}{marker}")
            prev_s, prev_c = s, c
        
        # Failure buckets
        cr_path = os.path.join(run_dir, "client_requests.csv")
        if os.path.exists(cr_path):
            cr_rows = list(csv.DictReader(open(cr_path)))
            storm_reqs = []
            for r in cr_rows:
                ts_dt = datetime.fromisoformat(r["timestamp"].replace("+00:00", "+00:00"))
                ts_rel = ts_dt.timestamp() - t0
                if storm_start - 5 <= ts_rel <= storm_end + 5:
                    storm_reqs.append((ts_rel, r))
            
            bucket_size = 30
            num_buckets = int((storm_end - storm_start) / bucket_size)
            print(f"\nFailure rate by 30s bucket:")
            for b in range(num_buckets):
                b_start = storm_start + b * bucket_size
                b_end = b_start + bucket_size
                bucket_reqs = [(ts, r) for ts, r in storm_reqs if b_start <= ts < b_end]
                if bucket_reqs:
                    fails = sum(1 for _, r in bucket_reqs if r.get("http_status") == "0")
                    total = len(bucket_reqs)
                    bar = "#" * int(fails / max(total, 1) * 50)
                    print(f"  [{b_start:>6.0f}-{b_end:>6.0f}s]  total={total:>5d}  fails={fails:>5d} ({fails/total*100:>5.1f}%)  {bar}")
        
        break
