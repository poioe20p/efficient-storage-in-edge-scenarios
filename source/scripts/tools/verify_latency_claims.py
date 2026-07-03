import csv, os

base = "source/scripts/testing/metrics"
runs = [
    "rq1_v2final_push_1", "rq1_v2final_push_2", "rq1_v2final_push_3",
    "rq1_v2final_poll5_1", "rq1_v2final_poll5_2", "rq1_v2final_poll5_3",
    "rq1_v2final_poll12_1", "rq1_v2final_poll12_2", "rq1_v2final_poll12_3",
    "rq1_v2final_poll30_1", "rq1_v2final_poll30_2", "rq1_v2final_poll30_3"
]

for r in runs:
    for d in os.listdir(base):
        if r in d:
            path = os.path.join(base, d, "client_requests.csv")
            if not os.path.exists(path):
                print(f"{r}: NO client_requests.csv")
                continue
            rows = list(csv.DictReader(open(path)))
            oks = [float(r2["latency_s"]) for r2 in rows if r2["http_status"] != "0" and r2["latency_s"]]
            if not oks:
                print(f"{r}: no OK requests")
                continue
            oks_sorted = sorted(oks)
            n = len(oks_sorted)
            p50 = oks_sorted[n//2]
            p95 = oks_sorted[int(n*0.95)]
            p99 = oks_sorted[int(n*0.99)]
            max_lat = max(oks)
            total = len(rows)
            fails = sum(1 for r2 in rows if r2["http_status"] == "0")
            rate = fails/total*100
            print(f"{r}: total={total} fails={fails} ({rate:.1f}%) p50={p50:.2f}s p95={p95:.2f}s p99={p99:.2f}s max={max_lat:.2f}s")
            break
