import csv, os, json, collections, sys

RUN_DIR = sys.argv[1] if len(sys.argv) > 1 else "source/scripts/testing/metrics/20260608_205101_wan_diag_low_tput"

print("=" * 80)
print("FULL ANALYSIS —", os.path.basename(RUN_DIR))
print("=" * 80)

# ── 1. Client Requests ──────────────────────────────────────────
cr = os.path.join(RUN_DIR, "client_requests.csv")
phases = collections.OrderedDict()
lan_stats = {"lan1": {"total": 0, "fail": 0}, "lan2": {"total": 0, "fail": 0}}
ep_stats = {}
total_all = ok_all = fail0_all = 0

with open(cr) as f:
    for row in csv.DictReader(f):
        p = row["phase"]
        s = row["http_status"]
        lan = row.get("client_lan", "")
        ep = row.get("endpoint", "")

        if p not in phases:
            phases[p] = {"total": 0, "ok": 0, "fail0": 0}
        phases[p]["total"] += 1
        total_all += 1
        if s == "200":
            phases[p]["ok"] += 1
            ok_all += 1
        elif s == "0":
            phases[p]["fail0"] += 1
            fail0_all += 1

        if lan in lan_stats:
            lan_stats[lan]["total"] += 1
            if s != "200":
                lan_stats[lan]["fail"] += 1

        if ep not in ep_stats:
            ep_stats[ep] = {"total": 0, "fail": 0}
        ep_stats[ep]["total"] += 1
        if s != "200":
            ep_stats[ep]["fail"] += 1

print("\n--- Phase Breakdown ---")
print("{:30s} {:>8s} {:>8s} {:>8s}".format("Phase", "Total", "Fail%", "HTTP-0"))
for p in ["baseline", "local_moderate", "storage_stress", "cross_region_hotspot",
           "reverse_hotspot", "inter_hotspot_cooldown", "compute_ramp",
           "compute_spike", "sustained_plateau", "demand_drop"]:
    d = phases.get(p)
    if not d or d["total"] == 0:
        continue
    fr = (d["total"] - d["ok"]) / d["total"] * 100
    f0 = d["fail0"]
    print("{:30s} {:>8,d} {:>7.1f}% {:>8,d}".format(p, d["total"], fr, f0))

fr_all = (total_all - ok_all) / total_all * 100 if total_all else 0
print("{:30s} {:>8,d} {:>7.1f}% {:>8,d}".format("OVERALL", total_all, fr_all, fail0_all))

print("\n--- LAN Asymmetry ---")
for lan in ["lan1", "lan2"]:
    d = lan_stats[lan]
    r = d["fail"] / d["total"] * 100 if d["total"] else 0
    print("  {}: {:,}/{:,} = {:.1f}% fail".format(lan, d["fail"], d["total"], r))

print("\n--- Endpoint Breakdown ---")
for ep in sorted(ep_stats.keys()):
    d = ep_stats[ep]
    r = d["fail"] / d["total"] * 100 if d["total"] else 0
    print("  {:25s} {:>8,d} {:>8,d} {:>6.1f}%".format(ep, d["total"], d["fail"], r))

# ── 2. Resource Stats ───────────────────────────────────────────
rs = os.path.join(RUN_DIR, "resource_stats.csv")
if os.path.exists(rs):
    ct_max = {"n1": 0, "n2": 0}
    server_max = 0
    storage_max = 0
    server_dynamic_count = 0
    storage_dynamic_count = 0
    with open(rs) as f:
        for row in csv.DictReader(f):
            ct_max["n1"] = max(ct_max["n1"], int(row.get("conntrack_entries_n1", 0) or 0))
            ct_max["n2"] = max(ct_max["n2"], int(row.get("conntrack_entries_n2", 0) or 0))
            server_max = max(server_max, int(row.get("server_count", 0) or 0))
            storage_max = max(storage_max, int(row.get("storage_count", 0) or 0))
            server_dynamic_count = max(server_dynamic_count, int(row.get("server_dynamic_count", 0) or 0))
            storage_dynamic_count = max(storage_dynamic_count, int(row.get("storage_dynamic_count", 0) or 0))
    print("\n--- Resource Stats ---")
    print("  Conntrack max: n1={} n2={}".format(ct_max["n1"], ct_max["n2"]))
    print("  Server count max: {} (dynamic: {})".format(server_max, server_dynamic_count))
    print("  Storage count max: {} (dynamic: {})".format(storage_max, storage_dynamic_count))

# ── 3. Container Events ─────────────────────────────────────────
ce = os.path.join(RUN_DIR, "container_events.csv")
if os.path.exists(ce):
    added_compute = 0
    removed_compute = 0
    added_storage = 0
    removed_storage = 0
    with open(ce) as f:
        for row in csv.DictReader(f):
            ev = row.get("event", "")
            name = row.get("container_name", "")
            if ev == "start" and "edge_server" in name:
                added_compute += 1
            elif ev == "die" and "edge_server" in name:
                removed_compute += 1
            elif ev == "start" and "edge_storage" in name:
                added_storage += 1
            elif ev == "die" and "edge_storage" in name:
                removed_storage += 1
    print("\n--- Container Events ---")
    print("  Compute: +{} added, -{} removed".format(added_compute, removed_compute))
    print("  Storage: +{} added, -{} removed".format(added_storage, removed_storage))
    print("  Orphaned: compute={} storage={}".format(added_compute - removed_compute, added_storage - removed_storage))

# ── 4. Controller Log Quick Checks ──────────────────────────────
for lan_id, log_name in [("lan1", "controller_lan1.log"), ("lan2", "controller_lan2.log")]:
    log_path = os.path.join(RUN_DIR, log_name)
    if not os.path.exists(log_path):
        continue
    scale_up_compute = 0
    scale_up_storage = 0
    scale_down_compute = 0
    scale_down_storage = 0
    vip_warnings = 0
    storage_eval_lines = 0
    with open(log_path, errors="replace") as f:
        for line in f:
            if "ComputeAlert" in line and "alert submitted" in line:
                scale_up_compute += 1
            elif "DataAlert" in line and "alert submitted" in line:
                scale_up_storage += 1
            elif "ScaleDownComputeAlert" in line and "alert submitted" in line:
                scale_down_compute += 1
            elif "ScaleDownDataAlert" in line and "alert submitted" in line:
                scale_down_storage += 1
            elif "IP unknown" in line:
                vip_warnings += 1
            elif "scale-down] storage eval:" in line:
                storage_eval_lines += 1

    print("\n--- Controller {} ---".format(lan_id.upper()))
    print("  Compute: +{} scale-up, -{} scale-down".format(scale_up_compute, scale_down_compute))
    print("  Storage: +{} scale-up, -{} scale-down".format(scale_up_storage, scale_down_storage))
    print("  VIP IP-unknown warnings: {}".format(vip_warnings))
    print("  Storage eval log lines: {}".format(storage_eval_lines))

# ── 5. Elasticity Events ────────────────────────────────────────
ee = os.path.join(RUN_DIR, "elasticity_events.csv")
if os.path.exists(ee):
    print("\n--- Elasticity Events (sample) ---")
    with open(ee) as f:
        lines = f.readlines()
        print("  {} total events".format(len(lines) - 1))
        # Show last 5
        for line in lines[-6:]:
            print("  ", line.strip()[:120])

# ── 6. Phases Snapshot ──────────────────────────────────────────
ps = os.path.join(RUN_DIR, "phases_snapshot.json")
if os.path.exists(ps):
    with open(ps) as f:
        snap = json.load(f)
    print("\n--- Phases Snapshot ---")
    for ph in snap.get("phases", snap):
        if isinstance(ph, dict):
            print("  {}: {}s @ {} req/s/client, cross_region={}".format(
                ph.get("name", "?"), ph.get("duration_seconds", "?"),
                ph.get("requests_per_second", "?"), ph.get("cross_region_ratio", "?")))

print("\n" + "=" * 80)
print("ANALYSIS COMPLETE")
print("=" * 80)
