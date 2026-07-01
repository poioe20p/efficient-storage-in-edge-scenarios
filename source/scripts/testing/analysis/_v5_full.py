"""v5 full analysis — all 4 mechanism ablation runs."""
import csv
from collections import Counter

RUNS = {
    "A (all on)":       ("_v5a_cr.csv", "_v5a_rs.csv"),
    "B (no Tier 1)":    ("_v5b_cr.csv", "_v5b_rs.csv"),
    "C (no storage)":   ("_v5c_cr.csv", "_v5c_rs.csv"),
    "D (no compute)":   ("_v5d_cr.csv", "_v5d_rs.csv"),
}
BASE = "source/scripts/testing/metrics"

print("=" * 80)
print("v5 EXPERIMENT — FULL ANALYSIS")
print("WAN=160ms | Storage --cpus=0.15 --memory=512m | Edge --cpus=0.30 --memory=256m | WT cache=0.25GB")
print("=" * 80)

# ── Per-run summary ──────────────────────────────────────────────
for label, (cr_file, rs_file) in RUNS.items():
    print(f"\n{'─' * 60}")
    print(f"  {label}")
    print(f"{'─' * 60}")

    # Client requests
    cr = list(csv.DictReader(open(f"{BASE}/{cr_file}")))
    total = len(cr)
    statuses = Counter(r["http_status"] for r in cr)
    phases = Counter(r["phase"] for r in cr)
    ok = statuses.get("200", 0)
    fail = statuses.get("0", 0)
    print(f"  Requests: {total:>6,}  OK={ok:>6,} ({100*ok/total:.1f}%)  fail={fail:>6,} ({100*fail/total:.1f}%)")
    print(f"  Phases:   {dict(sorted(phases.items()))}")

    # Resource stats
    rs = list(csv.DictReader(open(f"{BASE}/{rs_file}")))
    print(f"  {'Phase':25s} {'StorCPU':>8s} {'EdgeCPU':>8s} {'Srv':>6s} {'Stor':>6s}")
    print(f"  {'─'*25} {'─'*8} {'─'*8} {'─'*6} {'─'*6}")
    for p in sorted(set(r["phase"] for r in rs)):
        p_rows = [r for r in rs if r["phase"] == p]
        if not p_rows:
            continue
        scpu = sum(float(r["avg_storage_cpu_percent"]) for r in p_rows) / len(p_rows)
        ecpu = sum(float(r["average_cpu_percent"]) for r in p_rows) / len(p_rows)
        srv = sorted(set(r["server_count"] for r in p_rows))
        stor = sorted(set(r["storage_count"] for r in p_rows))
        print(f"  {p:25s} {scpu:7.1f}% {ecpu:7.1f}% {str(srv):6s} {str(stor):6s}")

# ── Cross-run comparison ─────────────────────────────────────────
print(f"\n{'=' * 80}")
print("CROSS-RUN COMPARISON")
print(f"{'=' * 80}")

# Gather key metrics
comparison = {}
for label, (cr_file, rs_file) in RUNS.items():
    cr = list(csv.DictReader(open(f"{BASE}/{cr_file}")))
    rs = list(csv.DictReader(open(f"{BASE}/{rs_file}")))
    total = len(cr)
    ok = sum(1 for r in cr if r["http_status"] == "200")
    
    # Storage CPU in storage_storm
    storm = [r for r in rs if r["phase"] == "storage_storm"]
    stor_cpu = sum(float(r["avg_storage_cpu_percent"]) for r in storm) / len(storm) if storm else 0
    
    # Edge CPU in compute_spike
    spike = [r for r in rs if r["phase"] == "compute_spike"]
    edge_cpu = sum(float(r["average_cpu_percent"]) for r in spike) / len(spike) if spike else 0
    
    # Peak server/storage counts
    peak_srv = max(int(r["server_count"]) for r in rs if r["server_count"].isdigit()) if rs else 0
    peak_stor = max(int(r["storage_count"]) for r in rs if r["storage_count"].isdigit()) if rs else 0
    
    comparison[label] = {
        "total": total, "ok_pct": 100*ok/total,
        "stor_cpu": stor_cpu, "edge_cpu": edge_cpu,
        "peak_srv": peak_srv, "peak_stor": peak_stor,
    }

print(f"\n  {'Run':20s} {'Total':>7s} {'OK%':>6s} {'StorCPU':>8s} {'EdgeCPU':>8s} {'PeakSrv':>8s} {'PeakStor':>8s}")
print(f"  {'─'*20} {'─'*7} {'─'*6} {'─'*8} {'─'*8} {'─'*8} {'─'*8}")
ref = comparison["A (all on)"]
for label, m in comparison.items():
    print(f"  {label:20s} {m['total']:>7,} {m['ok_pct']:>5.1f}% {m['stor_cpu']:>7.1f}% {m['edge_cpu']:>7.1f}% {m['peak_srv']:>8} {m['peak_stor']:>8}")

# Mechanism deltas
print(f"\n  Mechanism Impact (vs Run A):")
for label in ["B (no Tier 1)", "C (no storage)", "D (no compute)"]:
    m = comparison[label]
    d_total = (m["total"] - ref["total"]) / ref["total"] * 100
    d_ok = m["ok_pct"] - ref["ok_pct"]
    d_stor = m["stor_cpu"] - ref["stor_cpu"]
    d_edge = m["edge_cpu"] - ref["edge_cpu"]
    print(f"  {label:20s} thru={d_total:+5.1f}%  ok={d_ok:+5.1f}pp  storCPU={d_stor:+5.1f}%  edgeCPU={d_edge:+5.1f}%")

print(f"\n{'=' * 80}")
print("VERDICT")
print(f"{'=' * 80}")

# Tier 1 impact
b = comparison["B (no Tier 1)"]
tier1_loss = (ref["total"] - b["total"]) / ref["total"] * 100
print(f"  Tier 1:    Removing costs {tier1_loss:.0f}% throughput, {ref['ok_pct']-b['ok_pct']:.1f}pp success rate")
print(f"              DOMINANT mechanism at WAN=160ms with constrained resources")

# Storage impact
c = comparison["C (no storage)"]
stor_diff = (c["total"] - ref["total"]) / ref["total"] * 100
print(f"  Storage:   Removing changes throughput by {stor_diff:+.1f}%")
if abs(stor_diff) < 3:
    print(f"              NOT NEEDED at this workload scale")

# Compute impact
d = comparison["D (no compute)"]
comp_diff = (d["total"] - ref["total"]) / ref["total"] * 100
print(f"  Compute:   Removing costs {abs(comp_diff):.0f}% throughput")
if abs(comp_diff) < 5:
    print(f"              MARGINAL — WAN bottleneck limits per-client throughput")
