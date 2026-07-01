import csv
from collections import Counter

# v5A
cr = list(csv.DictReader(open("source/scripts/testing/metrics/_v5a_cr.csv")))
total = len(cr)
statuses = Counter(r["http_status"] for r in cr)
phases = Counter(r["phase"] for r in cr)
print(f"v5A Total: {total} | OK={statuses.get('200',0)} ({100*statuses.get('200',0)/total:.1f}%) | fail={statuses.get('0',0)} ({100*statuses.get('0',0)/total:.1f}%)")
print(f"By phase: {dict(sorted(phases.items()))}")

rs = list(csv.DictReader(open("source/scripts/testing/metrics/_v5a_rs.csv")))
for p in sorted(set(r["phase"] for r in rs)):
    p_rows = [r for r in rs if r["phase"] == p]
    if not p_rows:
        continue
    scpu = [float(r["avg_storage_cpu_percent"]) for r in p_rows]
    ecpu = [float(r["average_cpu_percent"]) for r in p_rows]
    srv = sorted(set(r["server_count"] for r in p_rows))
    stor = sorted(set(r["storage_count"] for r in p_rows))
    print(f"{p:25s} stor_cpu={sum(scpu)/len(scpu):5.1f}% edge_cpu={sum(ecpu)/len(ecpu):5.1f}% srv={srv} stor={stor}")
