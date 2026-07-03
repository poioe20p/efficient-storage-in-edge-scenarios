import csv, os

base = "source/scripts/testing/metrics"
runs = [
    "rq1_v2final_push_1", "rq1_v2final_push_2", "rq1_v2final_push_3",
    "rq1_v2final_poll5_1", "rq1_v2final_poll5_2", "rq1_v2final_poll5_3",
    "rq1_v2final_poll12_1", "rq1_v2final_poll12_2", "rq1_v2final_poll12_3",
    "rq1_v2final_poll30_1", "rq1_v2final_poll30_2", "rq1_v2final_poll30_3",
]

for r in runs:
    for d in os.listdir(base):
        if r in d:
            dq_path = os.path.join(base, d, "decision_quality.csv")
            if not os.path.exists(dq_path):
                print(f"{r}: NO decision_quality.csv")
                continue
            rows = list(csv.DictReader(open(dq_path)))
            # Filter storage_storm phase
            storm = [row for row in rows if row.get("phase") == "storage_storm"]
            if not storm:
                print(f"{r}: no storage_storm rows in decision_quality")
                continue
            
            # Get unique breaches and spawns
            print(f"\n=== {r} ===")
            print(f"  Total decision_quality rows in storage_storm: {len(storm)}")
            
            # Show all rows with spawns or breaches
            for row in storm:
                if int(row.get("storage_breach_count",0)) > 0 or int(row.get("compute_breach_count",0)) > 0 or int(row.get("storage_spawn",0)) > 0 or int(row.get("compute_spawn",0)) > 0:
                    print(f"  ts={row['timestamp_s']:>8s}  phase={row['phase']:<25s}  "
                          f"s_breach={row['storage_breach_count']:>3s}  c_breach={row['compute_breach_count']:>3s}  "
                          f"s_spawn={row['storage_spawn']:>3s}  c_spawn={row['compute_spawn']:>3s}  "
                          f"s_total={row['storage_total']:>3s}  c_total={row['compute_total']:>3s}  "
                          f"s_breached_nodes={row.get('storage_breached_nodes','?'):>4s}")
            break
