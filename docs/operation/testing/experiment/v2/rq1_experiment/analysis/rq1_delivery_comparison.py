#!/usr/bin/env python3
"""RQ1 delivery-semantics — cross-mode comparison graphs.

Groups analyzed runs by arm and renders the RQ1 delivery-semantics graph suite
with per-replicate variance, matching the visual conventions of the old
``rq1-cross-mode-comparison`` graphs (scatter dots on bars, per-event dots on
box plots, error bars).

Requires each run to have been analyzed first by ``rq1_delivery_per_run.py``
(<run_dir>/analysis/rq1_delivery/). Arm grouping is by the CLI argument used,
not by folder name — pre-flight runs are simply not passed in the replicate
lists.

Usage:
  python rq1_delivery_comparison.py \
      --run-dirs-ep      ep_run1 ep_run2 ... \
      --run-dirs-delayed delayed_run1 ... \
      --run-dirs-ls      ls_run1 ... \
      --output-dir       <experiment>/graphs/comparison
"""

import argparse
import csv
import math
import os
import statistics
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ARM_ORDER = ("ep", "delayed", "ls")
ARM_LABELS = {"ep": "A · event-preserving",
              "delayed": "B · delayed (+30 s)",
              "ls": "C · latest-state (poll 30)"}
ARM_COLORS = {"ep": "#4C72B0", "delayed": "#DD8452", "ls": "#55A868"}

ANALYSIS_SUBDIR = os.path.join("analysis", "rq1_delivery")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _fnum(value):
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _per_run_mean(run_dirs, filename, value_fn):
    """Per-run mean of ``value_fn(row)`` across that run's rows.

    Returns (per_run_values, mean, std). Runs with no usable rows are skipped.
    """
    per_run = []
    for rd in run_dirs:
        rows = _load_rows(os.path.join(rd, ANALYSIS_SUBDIR, filename))
        vals = [v for v in (value_fn(r) for r in rows) if v is not None]
        if vals:
            per_run.append(statistics.mean(vals))
    if not per_run:
        return [], float("nan"), float("nan")
    mean = statistics.mean(per_run)
    std = statistics.stdev(per_run) if len(per_run) > 1 else 0.0
    return per_run, mean, std


def _per_run_collect(run_dirs, filename, value_fn):
    """Collect every non-None value across all runs (for per-event boxes)."""
    out = []
    for rd in run_dirs:
        rows = _load_rows(os.path.join(rd, ANALYSIS_SUBDIR, filename))
        out.extend(v for v in (value_fn(r) for r in rows) if v is not None)
    return out


def _bar_with_dots(ax, labels, means, stds, per_run, colors, ylabel):
    """Bars with error bars and per-run scatter dots (jittered)."""
    x = list(range(len(labels)))
    ax.bar(x, means, yerr=stds, color=colors, alpha=0.85,
           error_kw=dict(ecolor="black", lw=1, capsize=3))
    for xi, pr in zip(x, per_run):
        if not pr:
            continue
        jittered = [xi + (i - (len(pr) - 1) / 2.0) * 0.08
                    for i in range(len(pr))]
        ax.scatter(jittered, pr, color="black", s=16, zorder=3, alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", linestyle=":", alpha=0.4)


def _read_delay_s(run_dirs):
    """Read DELAY_S from the delayed arm's run_meta.csv (default 30)."""
    for rd in run_dirs:
        for r in _load_rows(os.path.join(rd, ANALYSIS_SUBDIR, "run_meta.csv")):
            if (r.get("key") or "").strip() == "delay_s":
                v = _fnum(r.get("value"))
                if v is not None:
                    return int(v)
    return 30


def _box_with_dots(ax, data, labels, colors, ylabel):
    """Box plot plus per-event scatter dots (jittered) per arm.

    Arms with no data are labelled "no data" instead of crashing.
    """
    valid = [(i, vals) for i, vals in enumerate(data) if vals]
    if valid:
        valid_pos = [i for i, _ in valid]
        bp = ax.boxplot([vals for _, vals in valid], positions=valid_pos,
                        widths=0.55, patch_artist=True, showfliers=False)
        for patch, color in zip(bp["boxes"], [colors[i] for i, _ in valid]):
            patch.set_facecolor(color)
            patch.set_alpha(0.7)
        for bp_line in bp["medians"]:
            bp_line.set_color("black")
    for i, vals in enumerate(data):
        if not vals:
            ax.text(i, 0, "no data", ha="center", va="top", fontsize=8,
                    color="grey")
            continue
        jitter = [i + (j - (len(vals) - 1) / 2.0) * 0.012
                  for j in range(len(vals))]
        ax.scatter(jitter, vals, color="black", s=5, alpha=0.35, zorder=3)
        ax.text(i, max(vals), f"n={len(vals)}", ha="center", va="bottom",
                fontsize=8)
    ax.set_xticks(list(range(len(data))))
    ax.set_xticklabels(labels)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", linestyle=":", alpha=0.4)


def _plot_path(output_dir, name):
    return os.path.join(output_dir, name)


# ---------------------------------------------------------------------------
# Graph builders
# ---------------------------------------------------------------------------

def graph_delivery_completeness(out_dir, arms_data):
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = [ARM_LABELS[a] for a in ARM_ORDER]
    colors = [ARM_COLORS[a] for a in ARM_ORDER]
    frac_means, frac_stds, frac_per_run = [], [], []
    oload_frac_means, oload_frac_stds, oload_per_run = [], [], []
    for a in ARM_ORDER:
        _, fm, fs = _per_run_mean(arms_data[a], "delivery_integrity.csv",
                                  lambda r: _fnum(r.get("delivered_frac")))
        _, om, os_ = _per_run_mean(arms_data[a], "delivery_integrity.csv",
                                   lambda r: _od_frac(r))
        frac_means.append(fm); frac_stds.append(fs)
        frac_per_run.append(_per_run_mean(
            arms_data[a], "delivery_integrity.csv",
            lambda r: _fnum(r.get("delivered_frac")))[0])
        oload_frac_means.append(om); oload_frac_stds.append(os_)
        oload_per_run.append(_per_run_mean(
            arms_data[a], "delivery_integrity.csv", _od_frac)[0])
    x = list(range(len(labels)))
    w = 0.38
    ax.bar([i - w / 2 for i in x], frac_means, width=w,
           yerr=frac_stds, color=colors, alpha=0.85,
           error_kw=dict(ecolor="black", lw=1, capsize=3),
           label="delivered % of universe")
    ax.bar([i + w / 2 for i in x], oload_frac_means, width=w,
           yerr=oload_frac_stds, color=colors, alpha=0.45,
           error_kw=dict(ecolor="black", lw=1, capsize=3),
           label="delivered % of overload windows")
    for xi, pr, pr2 in zip(x, frac_per_run, oload_per_run):
        for vals, off in ((pr, -w / 2), (pr2, w / 2)):
            for i, v in enumerate(vals):
                ax.scatter(xi + off + (i - (len(vals) - 1) / 2.0) * 0.05,
                           v, color="black", s=16, zorder=3, alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("delivered fraction")
    ax.set_ylim(0, 1.05)
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(_plot_path(out_dir, "delivery_completeness.png"), dpi=150)
    plt.close(fig)


def _od_frac(r):
    total = _fnum(r.get("overload_total"))
    delivered = _fnum(r.get("overload_delivered"))
    if total is None or delivered is None or total <= 0:
        return None
    return delivered / total


def graph_delivery_delay(out_dir, arms_data):
    fig, ax = plt.subplots(figsize=(8, 5))
    data = [_per_run_collect(arms_data[a], "delivery_delay.csv",
                             lambda r: _fnum(r.get("delay_s")))
            for a in ARM_ORDER]
    _box_with_dots(ax, data, [ARM_LABELS[a] for a in ARM_ORDER],
                   [ARM_COLORS[a] for a in ARM_ORDER], "delivery delay_s (s)")
    ax.axhline(_read_delay_s(arms_data["delayed"]), color="grey",
               linestyle="--", lw=1, label="DELAY_S")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(_plot_path(out_dir, "delivery_delay_box.png"), dpi=150)
    plt.close(fig)


def graph_info_age(out_dir, arms_data):
    fig, ax = plt.subplots(figsize=(8, 5))
    data = [_per_run_collect(arms_data[a], "info_age.csv",
                             lambda r: _fnum(r.get("info_age_s")))
            for a in ARM_ORDER]
    _box_with_dots(ax, data, [ARM_LABELS[a] for a in ARM_ORDER],
                   [ARM_COLORS[a] for a in ARM_ORDER],
                   "info age at decision (s)")
    fig.tight_layout()
    fig.savefig(_plot_path(out_dir, "info_age_at_decision_box.png"), dpi=150)
    plt.close(fig)


def graph_missed_overload(out_dir, arms_data):
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = [ARM_LABELS[a] for a in ARM_ORDER]
    colors = [ARM_COLORS[a] for a in ARM_ORDER]
    total_m, total_s, total_pr = [], [], []
    del_m, del_s, del_pr = [], [], []
    miss_m, miss_s, miss_pr = [], [], []
    for a in ARM_ORDER:
        _, tm, ts = _per_run_mean(arms_data[a], "delivery_integrity.csv",
                                  lambda r: _fnum(r.get("overload_total")))
        _, dm, ds = _per_run_mean(arms_data[a], "delivery_integrity.csv",
                                  lambda r: _fnum(r.get("overload_delivered")))
        _, mm, ms = _per_run_mean(arms_data[a], "delivery_integrity.csv",
                                  lambda r: _fnum(r.get("overload_missed")))
        total_m.append(tm); total_s.append(ts)
        del_m.append(dm); del_s.append(ds)
        miss_m.append(mm); miss_s.append(ms)
        total_pr.append(_per_run_mean(
            arms_data[a], "delivery_integrity.csv",
            lambda r: _fnum(r.get("overload_total")))[0])
        del_pr.append(_per_run_mean(
            arms_data[a], "delivery_integrity.csv",
            lambda r: _fnum(r.get("overload_delivered")))[0])
        miss_pr.append(_per_run_mean(
            arms_data[a], "delivery_integrity.csv",
            lambda r: _fnum(r.get("overload_missed")))[0])
    x = list(range(len(labels)))
    w = 0.26
    sets = [("universe", total_m, total_s, total_pr, 1.0),
            ("delivered", del_m, del_s, del_pr, 0.7),
            ("missed", miss_m, miss_s, miss_pr, 0.4)]
    for name, m, s, pr, alpha in sets:
        ax.bar([i + ({"universe": -1, "delivered": 0, "missed": 1}[name]) * w
                for i in x],
               m, width=w, yerr=s, color=colors, alpha=alpha,
               error_kw=dict(ecolor="black", lw=1, capsize=3), label=name)
        for xi, vals in zip(x, pr):
            for i, v in enumerate(vals):
                ax.scatter(
                    xi + ({"universe": -1, "delivered": 0, "missed": 1}[name]) * w
                    + (i - (len(vals) - 1) / 2.0) * 0.04,
                    v, color="black", s=14, zorder=3, alpha=0.7)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.set_ylabel("overload windows (mean per run)")
    ax.grid(axis="y", linestyle=":", alpha=0.4)
    ax.legend(loc="upper right")
    fig.tight_layout()
    fig.savefig(_plot_path(out_dir, "missed_overload.png"), dpi=150)
    plt.close(fig)


def graph_overload_detection_delay(out_dir, arms_data):
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = [ARM_LABELS[a] for a in ARM_ORDER]
    colors = [ARM_COLORS[a] for a in ARM_ORDER]
    means, stds, per_run = [], [], []
    for a in ARM_ORDER:
        pr, m, s = _per_run_mean(
            arms_data[a], "overload_observability.csv",
            lambda r: _fnum(r.get("detection_delay_s")))
        means.append(m); stds.append(s); per_run.append(pr)
    _bar_with_dots(ax, labels, means, stds, per_run, colors,
                   "overload detection delay (s)")
    fig.tight_layout()
    fig.savefig(_plot_path(out_dir, "overload_detection_delay.png"), dpi=150)
    plt.close(fig)


def graph_scale_reaction(out_dir, arms_data):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    labels = [ARM_LABELS[a] for a in ARM_ORDER]
    colors = [ARM_COLORS[a] for a in ARM_ORDER]

    def lat(phase_col, key_col):
        means, stds, per_run = [], [], []
        for a in ARM_ORDER:
            pr, m, s = _per_run_mean(
                arms_data[a], "reaction_timeline.csv",
                lambda r, pc=phase_col, kc=key_col:
                (lambda sd, ps: (sd - ps) if (sd is not None and ps is not None)
                 else None)(
                    _fnum(r.get(kc)), _fnum(r.get("phase_start")))
                if (r.get("phase") or "").strip() == pc else None)
            means.append(m); stds.append(s); per_run.append(pr)
        return means, stds, per_run

    m1, s1, p1 = lat("overload_surge", "scale_up_first_ts")
    m2, s2, p2 = lat("overload_surge", "usable_capacity_ts")
    _bar_with_dots(ax1, labels, m1, s1, p1, colors,
                   "surge → first scale-up decision (s)")
    _bar_with_dots(ax2, labels, m2, s2, p2, colors,
                   "surge → usable capacity (s)")
    fig.tight_layout()
    fig.savefig(_plot_path(out_dir, "scale_reaction_latency.png"), dpi=150)
    plt.close(fig)


def graph_scale_down(out_dir, arms_data):
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = [ARM_LABELS[a] for a in ARM_ORDER]
    colors = [ARM_COLORS[a] for a in ARM_ORDER]
    means, stds, per_run = [], [], []
    for a in ARM_ORDER:
        def v(r, _a=a):
            if (r.get("phase") or "").strip() != "demand_drop":
                return None
            return _fnum(r.get("scale_down_latency_s"))
        pr, m, s = _per_run_mean(arms_data[a], "reaction_timeline.csv", v)
        means.append(m); stds.append(s); per_run.append(pr)
    _bar_with_dots(ax, labels, means, stds, per_run, colors,
                   "drop → first scale-down decision (s)")
    fig.tight_layout()
    fig.savefig(_plot_path(out_dir, "scale_down_latency.png"), dpi=150)
    plt.close(fig)


def graph_phase_latency(out_dir, arms_data):
    # Collect phase names present across all arms.
    phase_names = []
    for a in ARM_ORDER:
        for rd in arms_data[a]:
            for r in _load_rows(os.path.join(rd, ANALYSIS_SUBDIR,
                                             "phase_service_quality.csv")):
                name = (r.get("phase") or "").strip()
                if name and name not in phase_names:
                    phase_names.append(name)
    n = len(phase_names)
    if not n:
        return
    colors = [ARM_COLORS[a] for a in ARM_ORDER]
    labels = [ARM_LABELS[a] for a in ARM_ORDER]
    pcols = ("p50", "p95", "p99")
    pshades = (0.95, 0.65, 0.35)
    fig, axes = plt.subplots(1, n, figsize=(4.6 * n, 4.4), squeeze=False)
    for col, phase in enumerate(phase_names):
        ax = axes[0][col]
        for ai, a in enumerate(ARM_ORDER):
            for pi, pc in enumerate(pcols):
                _, m, s = _per_run_mean(
                    arms_data[a], "phase_service_quality.csv",
                    lambda r, p=phase, k=pc: _fnum(r.get(k))
                    if (r.get("phase") or "").strip() == p else None)
                ax.bar(ai * 3 + pi, m, yerr=s, width=0.8,
                       color=colors[ai], alpha=pshades[pi],
                       error_kw=dict(ecolor="black", lw=0.8, capsize=2))
        ax.set_xticks([1, 4, 7])
        ax.set_xticklabels([f"{labels[0]}\np50 p95 p99",
                            f"{labels[1]}\np50 p95 p99",
                            f"{labels[2]}\np50 p95 p99"], fontsize=7)
        ax.set_ylabel("latency (s)")
        ax.set_title(phase)
        ax.grid(axis="y", linestyle=":", alpha=0.4)
    handles = [plt.Rectangle((0, 0), 1, 1, color="black", alpha=a)
               for a in pshades]
    fig.legend(handles, ["p50", "p95", "p99"], loc="lower right",
               fontsize=8, ncol=3)
    fig.suptitle("Per-phase latency (p50 / p95 / p99)")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    fig.savefig(_plot_path(out_dir, "phase_latency.png"), dpi=150)
    plt.close(fig)


def graph_overhead(out_dir, arms_data):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    labels = [ARM_LABELS[a] for a in ARM_ORDER]
    colors = [ARM_COLORS[a] for a in ARM_ORDER]
    cpu_m, cpu_s, cpu_pr = [], [], []
    mem_m, mem_s, mem_pr = [], [], []
    for a in ARM_ORDER:
        _, cm, cs = _per_run_mean(arms_data[a], "overhead.csv",
                                  lambda r: _fnum(r.get("mean_cpu_percent")))
        _, mm, ms = _per_run_mean(arms_data[a], "overhead.csv",
                                  lambda r: _fnum(r.get("mean_mem_usage_mb")))
        cpu_m.append(cm); cpu_s.append(cs); mem_m.append(mm); mem_s.append(ms)
        cpu_pr.append(_per_run_mean(arms_data[a], "overhead.csv",
                                    lambda r: _fnum(r.get("mean_cpu_percent")))[0])
        mem_pr.append(_per_run_mean(arms_data[a], "overhead.csv",
                                    lambda r: _fnum(r.get("mean_mem_usage_mb")))[0])
    _bar_with_dots(ax1, labels, cpu_m, cpu_s, cpu_pr, colors,
                   "mean controller CPU%")
    _bar_with_dots(ax2, labels, mem_m, mem_s, mem_pr, colors,
                   "mean controller RSS (MB)")
    fig.tight_layout()
    fig.savefig(_plot_path(out_dir, "overhead.png"), dpi=150)
    plt.close(fig)


def graph_completeness_vs_infoage(out_dir, arms_data):
    fig, ax = plt.subplots(figsize=(8, 6))
    for a in ARM_ORDER:
        xs, ys = [], []
        for rd in arms_data[a]:
            frac = _per_run_mean(rd and [rd], "delivery_integrity.csv",
                                 lambda r: _fnum(r.get("delivered_frac")))[0]
            age_pr, _, _ = _per_run_mean(
                [rd], "info_age.csv", lambda r: _fnum(r.get("info_age_s")))
            if frac and age_pr:
                xs.append(statistics.mean(frac))
                ys.append(statistics.mean(age_pr))
        if xs:
            ax.scatter(xs, ys, color=ARM_COLORS[a], s=45,
                       label=ARM_LABELS[a], zorder=3)
            ax.scatter([statistics.mean(xs)], [statistics.mean(ys)],
                       marker="X", s=140, color=ARM_COLORS[a], zorder=4,
                       edgecolor="black")
    ax.set_xlabel("mean delivered fraction")
    ax.set_xlim(0, 1.05)
    ax.set_ylabel("mean info age at decision (s)")
    ax.grid(linestyle=":", alpha=0.4)
    ax.legend()
    fig.tight_layout()
    fig.savefig(_plot_path(out_dir, "completeness_vs_infoage.png"), dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _parse_run_dirs(values):
    out = []
    for v in values or []:
        out.extend(v.split())
    result = []
    for p in out:
        if os.path.isdir(p):
            result.append(os.path.abspath(p))
        else:
            print(f"[warn] run folder not found (dropped): {p}")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="RQ1 delivery-semantics cross-mode comparison graphs.")
    parser.add_argument("--run-dirs-ep", action="append", default=[],
                        metavar="DIR", help="Event-preserving (arm A) run folders")
    parser.add_argument("--run-dirs-delayed", action="append", default=[],
                        metavar="DIR", help="Delayed (arm B) run folders")
    parser.add_argument("--run-dirs-ls", action="append", default=[],
                        metavar="DIR", help="Latest-state (arm C) run folders")
    parser.add_argument("--output-dir", required=True,
                        help="Where to write the graph suite.")
    args = parser.parse_args()

    arms_data = {
        "ep": _parse_run_dirs(args.run_dirs_ep),
        "delayed": _parse_run_dirs(args.run_dirs_delayed),
        "ls": _parse_run_dirs(args.run_dirs_ls),
    }
    for a in ARM_ORDER:
        kept = [rd for rd in arms_data[a]
                if os.path.isdir(os.path.join(rd, ANALYSIS_SUBDIR))]
        dropped = [rd for rd in arms_data[a] if rd not in kept]
        if dropped:
            print(f"[warn] {a}: {len(dropped)} run(s) have no analysis/ "
                  f"subdir — dropped: {dropped[0]}")
        arms_data[a] = kept

    total = sum(len(arms_data[a]) for a in ARM_ORDER)
    if total == 0:
        sys.stderr.write("ERROR: no valid run folders supplied.\n")
        return 2

    os.makedirs(args.output_dir, exist_ok=True)
    for a in ARM_ORDER:
        print(f"{a}: {len(arms_data[a])} run(s)")

    graph_delivery_completeness(args.output_dir, arms_data)
    graph_delivery_delay(args.output_dir, arms_data)
    graph_info_age(args.output_dir, arms_data)
    graph_missed_overload(args.output_dir, arms_data)
    graph_overload_detection_delay(args.output_dir, arms_data)
    graph_scale_reaction(args.output_dir, arms_data)
    graph_scale_down(args.output_dir, arms_data)
    graph_phase_latency(args.output_dir, arms_data)
    graph_overhead(args.output_dir, arms_data)
    graph_completeness_vs_infoage(args.output_dir, arms_data)

    print(f"RQ1 comparison graphs written to {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
