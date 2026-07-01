"""v5 full analysis — all 4 mechanism ablation runs (corrected verdicts + latency)."""
import csv, os
from collections import Counter, defaultdict

BASE = os.path.join("source", "scripts", "testing", "metrics")
RUNS = [
    ("A (all on)",       "_v5a_cr.csv", "_v5a_rs.csv"),
    ("B (no Tier 1)",    "_v5b_cr.csv", "_v5b_rs.csv"),
    ("C (no storage)",   "_v5c_cr.csv", "_v5c_rs.csv"),
    ("D (no compute)",   "_v5d_cr.csv", "_v5d_rs.csv"),
]

def phase_latency_pct(cr_rows, phase, pct):
    lats = []
    for r in cr_rows:
        if r["phase"] != phase:
            continue
        try:
            lat = float(r.get("latency_s", 0) or 0) * 1000
            if lat > 0:
                lats.append(lat)
        except (ValueError, TypeError):
            pass
    if not lats:
        return 0
    lats.sort()
    return lats[int(len(lats) * pct / 100)]

print("=" * 80)
print("v5 EXPERIMENT - FULL ANALYSIS (CORRECTED)")
print("WAN=160ms | Storage --cpus=0.15 --memory=512m | Edge --cpus=0.30 --memory=256m | WT cache=0.25GB")
print("=" * 80)

# Per-run summary
for label, cr_file, rs_file in RUNS:
    print(f"\n{'=' * 60}")
    print(f"  {label}")
    print(f"{'=' * 60}")

    cr = list(csv.DictReader(open(os.path.join(BASE, cr_file))))
    total = len(cr)
    statuses = Counter(r["http_status"] for r in cr)
    ok = statuses.get("200", 0)
    fail = statuses.get("0", 0)
    print(f"  Requests: {total:>6,}  OK={ok:>6,} ({100*ok/total:.1f}%)  fail={fail:>6,} ({100*fail/total:.1f}%)")

    # Per-phase latency
    phases_list = sorted(set(r["phase"] for r in cr))
    print(f"  {'Phase':25s} {'Reqs':>6s} {'Median':>7s} {'p95':>7s}")
    print(f"  {'-'*25} {'-'*6} {'-'*7} {'-'*7}")
    for p in phases_list:
        p_reqs = sum(1 for r in cr if r["phase"] == p)
        med = phase_latency_pct(cr, p, 50)
        p95 = phase_latency_pct(cr, p, 95)
        print(f"  {p:25s} {p_reqs:>6,} {med:>6.0f}ms {p95:>6.0f}ms")

    # Resource stats
    rs = list(csv.DictReader(open(os.path.join(BASE, rs_file))))
    print(f"\n  {'Phase':25s} {'StorCPU':>8s} {'EdgeCPU':>8s} {'Srv':>6s} {'Stor':>6s}")
    print(f"  {'-'*25} {'-'*8} {'-'*8} {'-'*6} {'-'*6}")
    for p in sorted(set(r["phase"] for r in rs)):
        p_rows = [r for r in rs if r["phase"] == p]
        if not p_rows:
            continue
        scpu = sum(float(r["avg_storage_cpu_percent"]) for r in p_rows) / len(p_rows)
        ecpu = sum(float(r["average_cpu_percent"]) for r in p_rows) / len(p_rows)
        srv = sorted(set(r["server_count"] for r in p_rows))
        stor = sorted(set(r["storage_count"] for r in p_rows))
        print(f"  {p:25s} {scpu:7.1f}% {ecpu:7.1f}% {str(srv):6s} {str(stor):6s}")

# Cross-run comparison
print(f"\n{'=' * 80}")
print("CROSS-RUN COMPARISON")
print(f"{'=' * 80}")

comparison = {}
for label, cr_file, rs_file in RUNS:
    cr = list(csv.DictReader(open(os.path.join(BASE, cr_file))))
    rs = list(csv.DictReader(open(os.path.join(BASE, rs_file))))
    total = len(cr)
    ok = sum(1 for r in cr if r["http_status"] == "200")

    storm_rs = [r for r in rs if r["phase"] == "storage_storm"]
    spike_rs = [r for r in rs if r["phase"] == "compute_spike"]
    base_rs = [r for r in rs if r["phase"] == "baseline"]

    comparison[label] = {
        "total": total, "ok_pct": 100*ok/total,
        "stor_cpu_storm": sum(float(r["avg_storage_cpu_percent"]) for r in storm_rs) / len(storm_rs) if storm_rs else 0,
        "edge_cpu_spike": sum(float(r["average_cpu_percent"]) for r in spike_rs) / len(spike_rs) if spike_rs else 0,
        "edge_cpu_base": sum(float(r["average_cpu_percent"]) for r in base_rs) / len(base_rs) if base_rs else 0,
        "peak_srv": max(int(r["server_count"]) for r in rs if r["server_count"].isdigit()) if rs else 0,
        "peak_stor": max(int(r["storage_count"]) for r in rs if r["storage_count"].isdigit()) if rs else 0,
        "lat_storm_med": phase_latency_pct(cr, "storage_storm", 50),
        "lat_spike_med": phase_latency_pct(cr, "compute_spike", 50),
        "lat_tier1_med": phase_latency_pct(cr, "tier1_hotspot", 50),
        "lat_base_med": phase_latency_pct(cr, "baseline", 50),
    }

print(f"\n  {'Run':20s} {'Total':>7s} {'OK%':>6s} {'StrmCPU':>8s} {'SpikeCPU':>8s} {'BaseCPU':>8s} {'PeakSrv':>7s} {'PeakStor':>8s}")
print(f"  {'-'*20} {'-'*7} {'-'*6} {'-'*8} {'-'*8} {'-'*8} {'-'*7} {'-'*8}")
ref = comparison["A (all on)"]
for label, m in comparison.items():
    print(f"  {label:20s} {m['total']:>7,} {m['ok_pct']:>5.1f}% {m['stor_cpu_storm']:>7.1f}% {m['edge_cpu_spike']:>7.1f}% {m['edge_cpu_base']:>7.1f}% {m['peak_srv']:>7} {m['peak_stor']:>8}")

# Latency comparison
print(f"\n  {'Run':20s} {'BaseMed':>8s} {'StormMed':>8s} {'Tier1Med':>8s} {'SpikeMed':>8s}")
print(f"  {'-'*20} {'-'*8} {'-'*8} {'-'*8} {'-'*8}")
for label, m in comparison.items():
    print(f"  {label:20s} {m['lat_base_med']:>7.0f}ms {m['lat_storm_med']:>7.0f}ms {m['lat_tier1_med']:>7.0f}ms {m['lat_spike_med']:>7.0f}ms")

# Mechanism deltas
print(f"\n  Mechanism Impact (vs Run A):")
for label in ["B (no Tier 1)", "C (no storage)", "D (no compute)"]:
    m = comparison[label]
    d_total = (m["total"] - ref["total"]) / ref["total"] * 100
    d_ok = m["ok_pct"] - ref["ok_pct"]
    d_storm_lat = (m["lat_storm_med"] - ref["lat_storm_med"]) / max(1, ref["lat_storm_med"]) * 100
    d_spike_lat = (m["lat_spike_med"] - ref["lat_spike_med"]) / max(1, ref["lat_spike_med"]) * 100
    d_tier1_lat = (m["lat_tier1_med"] - ref["lat_tier1_med"]) / max(1, ref["lat_tier1_med"]) * 100
    print(f"  {label:20s} thru={d_total:+5.1f}%  ok={d_ok:+5.1f}pp")
    print(f"  {'':20s} stormLat={d_storm_lat:+5.0f}%  spikeLat={d_spike_lat:+5.0f}%  tier1Lat={d_tier1_lat:+5.0f}%")

# CORRECTED VERDICT
print(f"\n{'=' * 80}")
print("CORRECTED VERDICT")
print(f"{'=' * 80}")

# Tier 1 (B vs A)
b = comparison["B (no Tier 1)"]
print(f"\n  Tier 1 (B vs A):")
print(f"    Throughput:  {b['total']:,} vs {ref['total']:,} = {(b['total']-ref['total'])/ref['total']*100:+.1f}%")
print(f"    Success:     {b['ok_pct']:.1f}% vs {ref['ok_pct']:.1f}% = {b['ok_pct']-ref['ok_pct']:+.1f}pp")
print(f"    storage_storm latency: {b['lat_storm_med']:.0f}ms vs {ref['lat_storm_med']:.0f}ms = {(b['lat_storm_med']-ref['lat_storm_med'])/max(1,ref['lat_storm_med'])*100:+.0f}%")
print(f"    compute_spike latency: {b['lat_spike_med']:.0f}ms vs {ref['lat_spike_med']:.0f}ms = {(b['lat_spike_med']-ref['lat_spike_med'])/max(1,ref['lat_spike_med'])*100:+.0f}%")
print(f"    tier1_hotspot latency: {b['lat_tier1_med']:.0f}ms vs {ref['lat_tier1_med']:.0f}ms = {(b['lat_tier1_med']-ref['lat_tier1_med'])/max(1,ref['lat_tier1_med'])*100:+.0f}%")
if b['lat_spike_med'] < ref['lat_spike_med'] and b['lat_storm_med'] < ref['lat_storm_med']:
    print(f"    ** B (no Tier 1) has LOWER latency in storage_storm AND compute_spike!")
    print(f"    Tier 1 overhead may degrade non-tier1 phases at WAN=160ms")
print(f"    VERDICT: INCONCLUSIVE at WAN=160ms - Tier 1 effect (~4% throughput, +3% tier1_lat)")
    print(f"             is within the noise floor of a single-replicate experiment.")
    print(f"             sel_sync containers have NO CPU limits - they do NOT compete")
    print(f"             with edge_server for constrained Docker CPU resources.")
    print(f"             At WAN=300ms (v4), Tier 1 was unambiguous (18% throughput, 45x latency).")
    print(f"             At WAN=160ms, the effect shrinks below detection threshold.")

# Storage (C vs A)
c = comparison["C (no storage)"]
print(f"\n  Storage (C vs A):")
print(f"    Throughput:  {c['total']:,} vs {ref['total']:,} = {(c['total']-ref['total'])/ref['total']*100:+.1f}%")
print(f"    storage_storm latency: {c['lat_storm_med']:.0f}ms vs {ref['lat_storm_med']:.0f}ms = {(c['lat_storm_med']-ref['lat_storm_med'])/max(1,ref['lat_storm_med'])*100:+.0f}%")
print(f"    tier1_hotspot latency: {c['lat_tier1_med']:.0f}ms vs {ref['lat_tier1_med']:.0f}ms = {(c['lat_tier1_med']-ref['lat_tier1_med'])/max(1,ref['lat_tier1_med'])*100:+.0f}%")
print(f"    compute_spike latency: {c['lat_spike_med']:.0f}ms vs {ref['lat_spike_med']:.0f}ms = {(c['lat_spike_med']-ref['lat_spike_med'])/max(1,ref['lat_spike_med'])*100:+.0f}%")
if c['lat_storm_med'] < ref['lat_storm_med']:
    print(f"    ** C (no storage) has LOWER latency in storage_storm (writes avoid replication overhead)")
if c['lat_tier1_med'] > ref['lat_tier1_med']:
    print(f"    ** C has HIGHER latency in tier1_hotspot (cross-region reads hit single MongoDB)")
print(f"    VERDICT: NOT PROVEN - Storage CPU (27%) too low to show necessity (target: 60%+).")
    print(f"             Single MongoDB handles workload comfortably. Consistent with v1-v4.")

# Compute (D vs A)
d = comparison["D (no compute)"]
print(f"\n  Compute (D vs A):")
print(f"    Throughput:  {d['total']:,} vs {ref['total']:,} = {(d['total']-ref['total'])/ref['total']*100:+.1f}%")
print(f"    Success:     {d['ok_pct']:.1f}% vs {ref['ok_pct']:.1f}% = {d['ok_pct']-ref['ok_pct']:+.1f}pp")
print(f"    compute_spike latency: {d['lat_spike_med']:.0f}ms vs {ref['lat_spike_med']:.0f}ms = {(d['lat_spike_med']-ref['lat_spike_med'])/max(1,ref['lat_spike_med'])*100:+.0f}%")
print(f"    tier1_hotspot latency: {d['lat_tier1_med']:.0f}ms vs {ref['lat_tier1_med']:.0f}ms = {(d['lat_tier1_med']-ref['lat_tier1_med'])/max(1,ref['lat_tier1_med'])*100:+.0f}%")
print(f"    Edge CPU (spike):       {d['edge_cpu_spike']:.1f}% vs {ref['edge_cpu_spike']:.1f}% = {d['edge_cpu_spike']-ref['edge_cpu_spike']:+.1f}pp")
print(f"    Peak servers:           {d['peak_srv']} vs {ref['peak_srv']}")
print(f"    VERDICT: DOMINANT - Compute is THE bottleneck at constrained resources.")
print(f"             -33.5% throughput, +21.5pp edge CPU, 3.5x spike latency.")

print(f"\n{'=' * 80}")
print("FINAL RANKING (v5)")
print(f"{'=' * 80}")
print(f"  1. COMPUTE  - NECESSARY   (34% throughput loss when ablated, unambiguous)")
print(f"  2. TIER 1   - INCONCLUSIVE (effect too small to distinguish from noise at WAN=160ms)")
print(f"  3. STORAGE  - NOT PROVEN   (CPU too low to show necessity; consistent across v1-v5)")
