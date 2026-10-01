#!/usr/bin/env python3
"""RQ2 thesis figures — consequence map, compute engagement, storage relief.

Produces the three RQ2 figures referenced by section 5.3 (results, RQ2):

  1. rq2_consequence_map.png
     Episode endpoint latency per cell against the no-action comparator.
     Left panel: data-access-bound episode, p95 (the pre-registered storage
     metric); right panel: compute-bound episode, p50 (the null reading —
     p95 on this episode is dominated by the v3 start-up transient that the
     extension build lacks, so it is not comparable across eras).
     Convention: status=completed only, both lanes pooled per replicate,
     nearest-rank percentile (qa_verify.py / latency_summary convention).

  2. rq2_compute_engagement.png
     Compute-action engagement on the compute-bound episode.
     Left: share of each lane's requests served by the added backends after
     the first compute addition (dots = per-lane values, bars = medians;
     original vs added segments), with the storage-only cell as the scaled-
     nothing reference. Right: lane compute as the sum of per-backend CPU
     medians (original + added servers) against the single-backend load of
     the storage-only cell. Added backends are classified by first
     per_node_stats appearance at/after the lane's first compute add.
     Convention matches temp/qa_dist.py (per-server medians; lane total =
     sum of per-server medians), which the section-5.3 numbers use.

  3. rq2_storage_relief_v2.png
     Storage-tier relief on the data-access-bound episode, restyled from the
     B2 synthesis (rq2_v3_b2_synthesis.py): per-lane post/pre peak storage
     CPU ratio from each run's analysis/rq2_v3_windows.csv, per-replicate
     value = mean of the two lanes, bars = mean +/- std, dots = replicates,
     against the pre-registered 0.75 threshold.

Run on the VM (reads the run folders):

    python3 generate_thesis_figures.py --out-dir /tmp/rq2_thesis_figs

Also writes rq2_thesis_figure_data.csv (every value drawn).
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import re
import statistics
from datetime import datetime

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RUN_RE = re.compile(r"^\d{8}_\d{6}_rq2_(nn|cf|sf|ba)_(cb|db)_([1-6])$")
EP_PHASE = {"cb": "compute_bound_episode", "db": "data_bound_episode"}
COLOR = {"cf": "#4C72B0", "sf": "#DD8452", "ba": "#55A868", "nn": "#9E9E9E"}
GREY = "#BFBFBF"
LABEL = {"nn": "No action", "cf": "Compute-only", "sf": "Storage-only",
         "ba": "Bottleneck-aware"}

plt.rcParams.update({"font.size": 12, "axes.labelsize": 12,
                     "xtick.labelsize": 10.5, "ytick.labelsize": 11,
                     "figure.dpi": 150, "savefig.dpi": 200,
                     "savefig.bbox": "tight"})


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def pct(v, q):
    """Nearest-rank percentile (matches qa_verify.py)."""
    v = sorted(v)
    if not v:
        return None
    return v[min(len(v) - 1, int(round(q * (len(v) - 1))))]


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def ts_iso(s):
    try:
        return datetime.fromisoformat((s or "").strip().replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def ts_el(s):
    s = (s or "").strip().strip('"')
    for fmt in ("%Y-%m-%d %H:%M:%S,%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(s, fmt).timestamp()
        except ValueError:
            pass
    return None


def run_files(path):
    agg = os.path.join(path, "client_requests.csv")
    if os.path.exists(agg):
        return [agg]
    return sorted(glob.glob(os.path.join(path, "client_requests_lan*_client_*.csv")))


def runs(metrics, policy, episode):
    out = []
    for p in sorted(glob.glob(os.path.join(metrics, f"*_rq2_{policy}_{episode}_[1-6]"))):
        name = os.path.basename(p)
        if os.path.isdir(p) and RUN_RE.match(name):
            out.append((name, p))
    return out


def episode_lat(path, phase):
    """Completed-only episode latencies (both lanes pooled)."""
    out = []
    for f in run_files(path):
        with open(f, newline="", encoding="utf-8", errors="replace") as fh:
            for r in csv.DictReader(fh):
                if (r.get("phase") or "").strip() != phase:
                    continue
                if (r.get("status") or "").strip() != "completed":
                    continue
                try:
                    out.append(float(r.get("latency_s") or "nan"))
                except ValueError:
                    pass
    return out


def first_compute_add(path):
    """lan -> first compute add epoch (node_lifecycle_timings.csv)."""
    out = {}
    p = os.path.join(path, "node_lifecycle_timings.csv")
    if not os.path.exists(p):
        return out
    with open(p, newline="", encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh):
            if (r.get("operation") or "").strip() != "add":
                continue
            if (r.get("node_type") or "").strip() != "compute":
                continue
            t = ts_el(r.get("timestamp"))
            lan = (r.get("controller") or "").strip()
            if t is None or not lan:
                continue
            if lan not in out or t < out[lan]:
                out[lan] = t
    return out


def engagement_stats(path):
    """Per-lane added/original request shares and per-backend CPU."""
    adds = first_compute_add(path)
    rows = []
    pns = os.path.join(path, "per_node_stats.csv")
    if not os.path.exists(pns):
        return {}
    with open(pns, newline="", encoding="utf-8", errors="replace") as fh:
        for r in csv.DictReader(fh):
            if (r.get("phase") or "").strip() != "compute_bound_episode":
                continue
            if (r.get("role") or "").strip() != "compute":
                continue
            t = ts_iso(r.get("timestamp"))
            if t is None:
                continue
            try:
                cpu = float(r.get("cpu_percent") or "nan")
            except ValueError:
                cpu = float("nan")
            try:
                rc = int(float(r.get("request_count") or 0))
            except ValueError:
                rc = 0
            rows.append((t, (r.get("network_id") or "").strip(),
                         (r.get("server_id") or "").strip(), cpu, rc))
    out = {}
    for lan in sorted({r[1] for r in rows}):
        lr = [r for r in rows if r[1] == lan]
        add_t = adds.get(lan)
        srv = {}
        for t, _, sid, cpu, rc in lr:
            s = srv.setdefault(sid, dict(cpu=[], rc_post=0, first=1e18))
            s["cpu"].append(cpu)
            # without a compute add the whole episode is the reference window
            if add_t is None or t >= add_t:
                s["rc_post"] += rc
            s["first"] = min(s["first"], t)
        if add_t is None:
            orig, added = dict(srv), {}
        else:
            orig = {s: v for s, v in srv.items() if v["first"] < add_t - 10.0}
            added = {s: v for s, v in srv.items() if s not in orig}
        post_tot = sum(v["rc_post"] for v in srv.values())
        post_orig = sum(v["rc_post"] for v in orig.values())
        out[lan] = dict(
            nserv=len(srv), n_orig=len(orig), n_add=len(added),
            added_share_post=100.0 * (post_tot - post_orig) / post_tot if post_tot else None,
            orig_cpu=med([med(v["cpu"]) for v in orig.values()]),
            added_cpu=med([med(v["cpu"]) for v in added.values()]) if added else None,
            total_cpu=sum(med(v["cpu"]) for v in srv.values()),
        )
    return out


def relief_lane_ratios(path):
    """(lan1_ratio, lan2_ratio) from the run's pinned-window analysis CSV."""
    w = os.path.join(path, "analysis", "rq2_v3_windows.csv")
    if not os.path.exists(w):
        return None
    with open(w, newline="", encoding="utf-8", errors="replace") as fh:
        row = next(csv.DictReader(fh), None)
    if not row:
        return None
    out = []
    for lan in (1, 2):
        v = row.get(f"stor_{lan}_cpu_ratio")
        try:
            out.append(float(v))
        except (TypeError, ValueError):
            out.append(None)
    return out


# --------------------------------------------------------------------------
# figure 1 - consequence map
# --------------------------------------------------------------------------
def fig_consequence_map(metrics, out_dir, data_rows):
    cells = {
        "db": ["nn_db", "cf_db", "sf_db", "ba_db"],
        "cb": ["nn_cb", "cf_cb", "sf_cb", "ba_cb"],
    }
    values = {}
    for ep, tags in cells.items():
        for tag in tags:
            pol, epsilon = tag.split("_")
            vals = []
            for name, path in runs(metrics, pol, epsilon):
                lats = episode_lat(path, EP_PHASE[epsilon])
                p50, p95 = pct(lats, .5), pct(lats, .95)
                vals.append(dict(run=name, p50=p50, p95=p95))
                data_rows.append(dict(figure="map", cell=tag, run=name,
                                      metric="ep_p50_s", value=p50))
                data_rows.append(dict(figure="map", cell=tag, run=name,
                                      metric="ep_p95_s", value=p95))
            values[tag] = vals

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.6))
    x = range(4)
    for ax, ep, metric, ylab, log in (
            (axes[0], "db", "p95", "Episode latency p95 (s)", True),
            (axes[1], "cb", "p50", "Episode latency p50 (ms)", False)):
        tags = cells[ep]
        meds = []
        for i, tag in enumerate(tags):
            pol = tag.split("_")[0]
            v = [d[metric] for d in values[tag] if d[metric] is not None]
            if metric == "p50":
                v = [x_ * 1000 for x_ in v]
            m = med(v)
            meds.append(m)
            ax.bar(i, m, width=0.6, color=COLOR[pol], alpha=0.88)
            jit = [i + (j - (len(v) - 1) / 2.0) * 0.07 for j in range(len(v))]
            ax.scatter(jit, v, color="black", s=20, zorder=4, alpha=0.75)
        ax.set_xticks(list(x))
        ax.set_xticklabels([LABEL[t.split("_")[0]] for t in tags])
        ax.set_ylabel(ylab)
        if log:
            ax.set_yscale("log")
        ax.grid(axis="y", linestyle=":", alpha=0.4)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        # cross-era label on the no-action comparator
        ax.annotate("extension campaign\n(cross-era label)", xy=(0, meds[0]),
                    xytext=(0.0, 1.02), textcoords="axes fraction",
                    ha="left", va="bottom", fontsize=8.5, color="#666666")

    fig.tight_layout()
    out = os.path.join(out_dir, "rq2_consequence_map.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"wrote {out}")
    for tag, vals in values.items():
        p95s = [d["p95"] for d in vals]
        p50s = [d["p50"] * 1000 for d in vals]
        print(f"  {tag}: n={len(vals)} p95 median={med(p95s):.3f}s "
              f"[{min(p95s):.3f}-{max(p95s):.3f}] p50 median={med(p50s):.2f}ms")


# --------------------------------------------------------------------------
# figure 2 - compute engagement
# --------------------------------------------------------------------------
def fig_compute_engagement(metrics, out_dir, data_rows):
    stats = {}
    for pol, ep in (("cf", "cb"), ("ba", "cb"), ("sf", "cb")):
        lane_rows = []
        for name, path in runs(metrics, pol, ep):
            st = engagement_stats(path)
            for lan, s in sorted(st.items()):
                s = dict(s)
                s["run"] = name
                s["lan"] = lan
                lane_rows.append(s)
                data_rows.append(dict(figure="engagement", cell=f"{pol}_{ep}",
                                      run=name, metric=f"added_share_post_{lan}",
                                      value=s["added_share_post"]))
                data_rows.append(dict(figure="engagement", cell=f"{pol}_{ep}",
                                      run=name, metric=f"total_cpu_{lan}",
                                      value=s["total_cpu"]))
        stats[f"{pol}_{ep}"] = lane_rows

    fig, axes = plt.subplots(1, 2, figsize=(11.2, 4.6))
    groups = ["cf_cb", "ba_cb", "sf_cb"]
    # -- panel a: request share
    ax = axes[0]
    for i, tag in enumerate(groups):
        pol = tag.split("_")[0]
        rows_g = stats[tag]
        add_sh = [s["added_share_post"] for s in rows_g if s["added_share_post"] is not None]
        m_add = med(add_sh)
        ax.bar(i, m_add, width=0.6, color=COLOR[pol], alpha=0.88)
        ax.bar(i, 100 - m_add, width=0.6, bottom=m_add, color=GREY, alpha=0.55)
        if add_sh and max(add_sh) > 0:
            jit = [i + (j - (len(add_sh) - 1) / 2.0) * 0.06 for j in range(len(add_sh))]
            ax.scatter(jit, add_sh, color="black", s=20, zorder=4, alpha=0.75)
        if m_add and m_add > 8:
            ax.text(i, m_add / 2, f"{m_add:.0f}%", ha="center", va="center",
                    fontsize=10, color="black", fontweight="bold")
        if m_add < 99:
            ax.text(i, m_add + (100 - m_add) / 2, f"{100 - m_add:.0f}%",
                    ha="center", va="center", fontsize=10, color="black")
        else:
            ax.text(i, 50, "not scaled", ha="center", va="center", fontsize=9.5,
                    color="#333333")
    ax.set_xticks(range(3))
    ax.set_xticklabels(["Compute-only", "Bottleneck-aware", "Storage-only"])
    ax.set_ylabel("Request share after first addition (%)")
    ax.set_ylim(0, 108)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # -- panel b: lane compute
    ax = axes[1]
    for i, tag in enumerate(groups):
        pol = tag.split("_")[0]
        rows_g = stats[tag]
        orig = med([s["orig_cpu"] for s in rows_g])
        adds = med([s["added_cpu"] for s in rows_g if s["added_cpu"] is not None])
        total = med([s["total_cpu"] for s in rows_g])
        if adds is None:  # storage-only: single backend
            ax.bar(i, total, width=0.6, color=COLOR[pol], alpha=0.88)
        else:
            # stacked approximation of the lane total: original + summed adds
            ax.bar(i, orig, width=0.6, color=GREY, alpha=0.55)
            ax.bar(i, total - orig, width=0.6, bottom=orig,
                   color=COLOR[pol], alpha=0.88)
        totals = [s["total_cpu"] for s in rows_g]
        jit = [i + (j - (len(totals) - 1) / 2.0) * 0.06 for j in range(len(totals))]
        ax.scatter(jit, totals, color="black", s=20, zorder=4, alpha=0.75)
        if adds is not None:
            ax.annotate(f"{total:.0f}", xy=(i, total - 15),
                        xytext=(0, 0), textcoords="offset points",
                        ha="center", va="top", fontsize=11, color="white",
                        fontweight="bold")
    base = med([s["total_cpu"] for s in stats["sf_cb"]])
    for i in (0, 1):
        total = med([s["total_cpu"] for s in stats[groups[i]]])
        ax.annotate(f"x{total / base:.1f}", xy=(i, total), xytext=(0, 18),
                    textcoords="offset points", ha="center", fontsize=10,
                    color="#333333")
    ax.axhline(base, color="#666666", linestyle="--", lw=1)
    ax.text(2.45, base + 2.5, "single-backend load", ha="right", va="bottom",
            fontsize=9, color="#666666")
    ax.set_xticks(range(3))
    ax.set_xticklabels(["Compute-only", "Bottleneck-aware", "Storage-only"])
    ax.set_ylabel("Lane compute (summed per-backend CPU, %)")
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    fig.tight_layout()
    out = os.path.join(out_dir, "rq2_compute_engagement.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"wrote {out}")
    for tag in groups:
        rows_g = stats[tag]
        add_sh = [s["added_share_post"] for s in rows_g if s["added_share_post"] is not None]
        tot = med([s["total_cpu"] for s in rows_g])
        print(f"  {tag}: n_lanes={len(rows_g)} added_share med={med(add_sh):.1f} "
              f"[{min(add_sh):.1f}-{max(add_sh):.1f}] total med={tot:.1f} "
              f"orig med={med([s['orig_cpu'] for s in rows_g]):.1f} "
              f"added med={med([s['added_cpu'] for s in rows_g if s['added_cpu'] is not None])}")
    return base


# --------------------------------------------------------------------------
# figure 3 - storage relief (restyle)
# --------------------------------------------------------------------------
def fig_storage_relief(metrics, out_dir, data_rows):
    cells = ["sf_db", "ba_db", "cf_db"]
    per_run = {}
    for tag in cells:
        pol, ep = tag.split("_")
        per_run[tag] = []
        for name, path in runs(metrics, pol, ep):
            ratios = relief_lane_ratios(path)
            if ratios is None:
                continue
            good = [r for r in ratios if r is not None]
            mean_ratio = statistics.mean(good) if good else None
            per_run[tag].append(dict(run=name, lanes=ratios, mean=mean_ratio))
            for k, r in enumerate(ratios, 1):
                data_rows.append(dict(figure="relief", cell=tag, run=name,
                                      metric=f"lane{k}_ratio", value=r))

    fig, ax = plt.subplots(figsize=(7.6, 4.6))
    for i, tag in enumerate(cells):
        pol = tag.split("_")[0]
        vals = [d["mean"] for d in per_run[tag] if d["mean"] is not None]
        if vals:
            m = statistics.mean(vals)
            s = statistics.stdev(vals) if len(vals) > 1 else 0.0
            ax.bar(i, m, width=0.6, color=COLOR[pol], alpha=0.88, yerr=s,
                   error_kw=dict(ecolor="black", lw=1, capsize=3))
            jit = [i + (j - (len(vals) - 1) / 2.0) * 0.07 for j in range(len(vals))]
            ax.scatter(jit, vals, color="black", s=22, zorder=4, alpha=0.8)
        else:
            ax.annotate("no reserve\nactivated", xy=(i, 0.35), ha="center",
                        fontsize=9.5, color="#666666")
    ax.axhline(0.75, color="#666666", linestyle="--", lw=1)
    ax.text(2.42, 0.75, "pre-registered threshold", ha="right", va="bottom",
            fontsize=9, color="#666666")
    ax.set_xticks(range(3))
    ax.set_xticklabels(["Storage-only", "Bottleneck-aware", "Compute-only"])
    ax.set_ylabel("Post/pre peak storage CPU (ratio)")
    ax.set_ylim(0, 1.0)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    fig.tight_layout()
    out = os.path.join(out_dir, "rq2_storage_relief_v2.png")
    fig.savefig(out)
    plt.close(fig)
    print(f"wrote {out}")
    for tag in cells:
        vals = [d["mean"] for d in per_run[tag] if d["mean"] is not None]
        lanes_ok = [r for d in per_run[tag] for r in d["lanes"] if r is not None]
        if vals:
            print(f"  {tag}: n_reps={len(vals)} mean-of-lanes med={med(vals):.3f} "
                  f"[{min(vals):.3f}-{max(vals):.3f}] lanes_below_0.75="
                  f"{sum(1 for r in lanes_ok if r < 0.75)}/{len(lanes_ok)}")


# --------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--metrics-dir",
                    default=os.path.expanduser(
                        "~/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics"))
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()
    os.makedirs(args.out_dir, exist_ok=True)
    data_rows = []

    fig_consequence_map(args.metrics_dir, args.out_dir, data_rows)
    fig_compute_engagement(args.metrics_dir, args.out_dir, data_rows)
    fig_storage_relief(args.metrics_dir, args.out_dir, data_rows)

    csv_path = os.path.join(args.out_dir, "rq2_thesis_figure_data.csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["figure", "cell", "run", "metric", "value"])
        w.writeheader()
        for r in data_rows:
            w.writerow(r)
    print(f"wrote {csv_path}")


if __name__ == "__main__":
    main()
