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
      --run-dirs-sp      sp_run1 ... \
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

ARM_ORDER = ("ep", "delayed", "ls", "sp")
ARM_LABELS = {"ep": "A · event-preserving",
              "delayed": "B · delayed (+30 s)",
              "ls": "C · latest-state (poll 30)",
              "sp": "D · sampled-push (/3)"}
ARM_COLORS = {"ep": "#4C72B0", "delayed": "#DD8452", "ls": "#55A868",
              "sp": "#C44E52"}

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
    labels = [ARM_LABELS[a] for a in ARM_ORDER]
    colors = [ARM_COLORS[a] for a in ARM_ORDER]
    means, stds, per_run = [], [], []
    for a in ARM_ORDER:
        pr, m, s = _per_run_mean(arms_data[a], "delivery_delay.csv",
                                 lambda r: _fnum(r.get("delay_s")))
        means.append(m); stds.append(s); per_run.append(pr)
    _bar_with_dots(ax, labels, means, stds, per_run, colors,
                   "delivery delay (s) — per-run mean")
    ax.axhline(_read_delay_s(arms_data["delayed"]), color="grey",
               linestyle="--", lw=1, label="DELAY_S")
    ax.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(_plot_path(out_dir, "delivery_delay.png"), dpi=150)
    plt.close(fig)


def graph_info_age(out_dir, arms_data):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    labels = [ARM_LABELS[a] for a in ARM_ORDER]
    colors = [ARM_COLORS[a] for a in ARM_ORDER]
    m1, s1, p1 = [], [], []
    for a in ARM_ORDER:
        pr, m, s = _per_run_mean(
            arms_data[a], "info_age.csv",
            lambda r: _fnum(r.get("info_age_s"))
            if (r.get("action_type") or "").strip() == "scale_up" else None)
        m1.append(m); s1.append(s); p1.append(pr)
    _bar_with_dots(ax1, labels, m1, s1, p1, colors, "info age at scale-up (s)")
    m2, s2, p2 = [], [], []
    for a in ARM_ORDER:
        pr, m, s = _per_run_mean(arms_data[a], "info_age.csv",
                                 lambda r: _fnum(r.get("info_age_s")))
        m2.append(m); s2.append(s); p2.append(pr)
    _bar_with_dots(ax2, labels, m2, s2, p2, colors, "info age at decision (s)")
    fig.tight_layout()
    fig.savefig(_plot_path(out_dir, "info_age.png"), dpi=150)
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

    m1, s1, p1 = lat("compute_plateau", "scale_up_first_ts")
    m2, s2, p2 = lat("compute_plateau", "usable_capacity_ts")
    _bar_with_dots(ax1, labels, m1, s1, p1, colors,
                   "plateau → first scale-up decision (s)")
    _bar_with_dots(ax2, labels, m2, s2, p2, colors,
                   "plateau → usable capacity (s)")
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
            if (r.get("phase") or "").strip() != "recovery_gap":
                return None
            return _fnum(r.get("scale_down_latency_s"))
        pr, m, s = _per_run_mean(arms_data[a], "reaction_timeline.csv", v)
        means.append(m); stds.append(s); per_run.append(pr)
    _bar_with_dots(ax, labels, means, stds, per_run, colors,
                   "plateau end → first scale-down decision (s)")
    fig.tight_layout()
    fig.savefig(_plot_path(out_dir, "scale_down_latency.png"), dpi=150)
    plt.close(fig)


def _run_requests(rd):
    """All client requests for a run (non-empty phase), both LANs combined."""
    return [r for r in _load_rows(os.path.join(rd, "client_requests.csv"))
            if (r.get("phase") or "").strip()]


def _phase_rows(rd, phase):
    return [r for r in _run_requests(rd)
            if (r.get("phase") or "").strip() == phase]


def _ok_rows(rows):
    """Completed+ok requests only — v2: status=completed & http_status=200;
    legacy: http_status not 0 and < 500. Timeout/dropped/canceled rows never
    enter latency percentiles (censoring is reported separately, never
    computed into latency)."""
    out = []
    for r in rows:
        st = (r.get("status") or "").strip()
        hs = str(r.get("http_status") or "").strip()
        if st:
            if st == "completed" and hs == "200":
                out.append(r)
            continue
        try:
            code = int(hs)
        except ValueError:
            continue
        if code != 0 and 100 <= code < 500:
            out.append(r)
    return out


def _completed_rows(rows):
    """Completed requests only (offered minus timeout/dropped/canceled)."""
    if rows and any((r.get("status") or "").strip() for r in rows):
        return [r for r in rows if (r.get("status") or "").strip() == "completed"]
    return rows


def _pct(values, q):
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


def _phase_pct_per_run(run_dirs, phase, q):
    """Per-run percentile ``q`` of latency within ``phase`` (raw phase label),
    over completed+ok requests only — timeout/dropped/canceled and failed rows
    never enter latency percentiles."""
    per_run = []
    for rd in run_dirs:
        vals = [_fnum(r.get("latency_s"))
                for r in _ok_rows(_phase_rows(rd, phase))
                if _fnum(r.get("latency_s")) is not None]
        v = _pct(vals, q)
        if v is not None:
            per_run.append(v)
    return per_run


def _all_phases(arms_data):
    out = []
    for a in ARM_ORDER:
        for rd in arms_data[a]:
            for r in _run_requests(rd):
                ph = (r.get("phase") or "").strip()
                if ph and ph not in out:
                    out.append(ph)
    return out


def graph_phase_latency(out_dir, arms_data):
    # Cross-phase x mode latency, computed from the raw generator `phase`
    # labels (the analyzer's anchored bucketing is misaligned — plateau
    # overrun — so phase_service_quality.csv is not used here).
    phases = _all_phases(arms_data)
    n = len(phases)
    if not n:
        return
    colors = [ARM_COLORS[a] for a in ARM_ORDER]
    labels = [ARM_LABELS[a] for a in ARM_ORDER]
    pcols = (("p50", 0.5, 0.95), ("p95", 0.95, 0.65), ("p99", 0.99, 0.35))
    fig, axes = plt.subplots(1, n, figsize=(4.6 * n, 4.4), squeeze=False)
    for col, phase in enumerate(phases):
        ax = axes[0][col]
        for ai, a in enumerate(ARM_ORDER):
            for pi, (pc, q, alpha) in enumerate(pcols):
                pr = _phase_pct_per_run(arms_data[a], phase, q)
                m = statistics.mean(pr) if pr else float("nan")
                s = statistics.stdev(pr) if len(pr) > 1 else 0.0
                ax.bar(ai * 3 + pi, m, yerr=s, width=0.8,
                       color=colors[ai], alpha=alpha,
                       error_kw=dict(ecolor="black", lw=0.8, capsize=2))
                for i, v in enumerate(pr):
                    ax.scatter(ai * 3 + pi + (i - (len(pr) - 1) / 2.0) * 0.06,
                               v, color="black", s=12, zorder=3, alpha=0.7)
        n_arms = len(ARM_ORDER)
        ax.set_xticks([ai * 3 + 1 for ai in range(n_arms)])
        ax.set_xticklabels([f"{labels[ai]}\np50 p95 p99"
                            for ai in range(n_arms)], fontsize=7)
        ax.set_ylabel("latency (s)")
        ax.set_title(phase)
        ax.grid(axis="y", linestyle=":", alpha=0.4)
    handles = [plt.Rectangle((0, 0), 1, 1, color="black", alpha=a)
               for _, _, a in pcols]
    fig.legend(handles, ["p50", "p95", "p99"], loc="lower right",
               fontsize=8, ncol=3)
    fig.suptitle("Per-phase latency (raw phase labels; p50 / p95 / p99)")
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
# Raw client-request graphs (old-v13-inspired; corrected raw phase labels)
# ---------------------------------------------------------------------------

def _per_run_req(run_dirs, fn):
    """Per-run value of ``fn(rows)`` over all client requests (both LANs)."""
    per_run = []
    for rd in run_dirs:
        rows = _run_requests(rd)
        if rows:
            v = fn(rows)
            if v is not None:
                per_run.append(v)
    return per_run


def _phase_req_per_run(run_dirs, phase, fn):
    """Per-run value of ``fn(rows)`` over requests in ``phase`` (raw label)."""
    per_run = []
    for rd in run_dirs:
        rows = _phase_rows(rd, phase)
        if rows:
            v = fn(rows)
            if v is not None:
                per_run.append(v)
    return per_run


def _grouped_phase_bars(ax, phases, stat_fn, ylabel, arms_data, legend_loc):
    """Grouped bars (one group per phase, one bar per arm) + per-replicate dots."""
    colors = [ARM_COLORS[a] for a in ARM_ORDER]
    labels = [ARM_LABELS[a] for a in ARM_ORDER]
    n_modes = len(ARM_ORDER)
    w = 0.26
    for pi, phase in enumerate(phases):
        xc = pi * (n_modes + 0.8)
        for ai, a in enumerate(ARM_ORDER):
            pr = stat_fn(arms_data[a], phase)
            m = statistics.mean(pr) if pr else float("nan")
            s = statistics.stdev(pr) if len(pr) > 1 else 0.0
            ax.bar(xc + ai * w, m, width=w, yerr=s, color=colors[ai],
                   error_kw=dict(ecolor="black", lw=1, capsize=3))
            for i, v in enumerate(pr):
                ax.scatter(xc + ai * w + (i - (len(pr) - 1) / 2.0) * 0.05,
                           v, color="black", s=14, zorder=3, alpha=0.7)
    ax.set_xticks([pi * (n_modes + 0.8) + (n_modes - 1) * w / 2
                   for pi in range(len(phases))])
    ax.set_xticklabels(phases)
    ax.set_ylabel(ylabel)
    handles = [plt.Rectangle((0, 0), 1, 1, color=colors[ai])
               for ai in range(n_modes)]
    ax.legend(handles, labels, loc=legend_loc, fontsize=8)
    ax.grid(axis="y", linestyle=":", alpha=0.4)


def graph_per_phase_latency(out_dir, arms_data, q):
    phases = _all_phases(arms_data)
    if not phases:
        return
    fig, ax = plt.subplots(figsize=(3.4 * len(phases), 5))
    _grouped_phase_bars(
        ax, phases,
        lambda arm, ph: _phase_pct_per_run(arm, ph, q),
        f"latency p{int(q * 100)} (s)", arms_data, "upper left")
    fig.tight_layout()
    fig.savefig(_plot_path(out_dir, f"per_phase_latency_p{int(q * 100)}.png"),
                dpi=150)
    plt.close(fig)


def graph_throughput(out_dir, arms_data):
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = [ARM_LABELS[a] for a in ARM_ORDER]
    colors = [ARM_COLORS[a] for a in ARM_ORDER]
    means, stds, per_run = [], [], []
    for a in ARM_ORDER:
        pr = _per_run_req(arms_data[a],
                          lambda rows: len(_completed_rows(rows)))
        means.append(statistics.mean(pr) if pr else float("nan"))
        stds.append(statistics.stdev(pr) if len(pr) > 1 else 0.0)
        per_run.append(pr)
    _bar_with_dots(ax, labels, means, stds, per_run, colors,
                   "requests served per run (completed)")
    fig.tight_layout()
    fig.savefig(_plot_path(out_dir, "throughput.png"), dpi=150)
    plt.close(fig)


def graph_throughput_per_phase(out_dir, arms_data):
    phases = _all_phases(arms_data)
    if not phases:
        return
    fig, ax = plt.subplots(figsize=(3.4 * len(phases), 5))
    _grouped_phase_bars(
        ax, phases,
        lambda arm, ph: _phase_req_per_run(
            arm, ph, lambda rows: len(_completed_rows(rows))),
        "requests per phase (completed)", arms_data, "upper right")
    fig.tight_layout()
    fig.savefig(_plot_path(out_dir, "throughput_per_phase.png"), dpi=150)
    plt.close(fig)


def _timeout_rate(rows):
    if rows and "status" in rows[0]:
        # RQ1 v2 contract: timeout is a distinct outcome class (never merged
        # into failure; latency percentiles are descriptive-only).
        return 100.0 * sum(1 for r in rows
                           if (r.get("status") or "").strip() == "timeout"
                           ) / len(rows)
    # Legacy (no status column): curl timeout was http_status=0.
    return 100.0 * sum(1 for r in rows
                       if str(r.get("http_status")).strip() == "0") / len(rows)


def graph_timeout(out_dir, arms_data):
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = [ARM_LABELS[a] for a in ARM_ORDER]
    colors = [ARM_COLORS[a] for a in ARM_ORDER]
    means, stds, per_run = [], [], []
    for a in ARM_ORDER:
        pr = _per_run_req(arms_data[a], _timeout_rate)
        means.append(statistics.mean(pr) if pr else float("nan"))
        stds.append(statistics.stdev(pr) if len(pr) > 1 else 0.0)
        per_run.append(pr)
    _bar_with_dots(ax, labels, means, stds, per_run, colors,
                   "timeout rate (http_status=0, %)")
    fig.tight_layout()
    fig.savefig(_plot_path(out_dir, "timeout_comparison.png"), dpi=150)
    plt.close(fig)


def graph_per_phase_timeout(out_dir, arms_data):
    phases = _all_phases(arms_data)
    if not phases:
        return
    fig, ax = plt.subplots(figsize=(3.4 * len(phases), 5))
    _grouped_phase_bars(
        ax, phases,
        lambda arm, ph: _phase_req_per_run(arm, ph, _timeout_rate),
        "timeout rate (http_status=0, %)", arms_data, "upper right")
    fig.tight_layout()
    fig.savefig(_plot_path(out_dir, "per_phase_timeout.png"), dpi=150)
    plt.close(fig)


def graph_degraded(out_dir, arms_data, threshold):
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = [ARM_LABELS[a] for a in ARM_ORDER]
    colors = [ARM_COLORS[a] for a in ARM_ORDER]
    means, stds, per_run = [], [], []
    for a in ARM_ORDER:
        pr = _per_run_req(
            arms_data[a],
            lambda rows, X=threshold: (lambda done: (
                100.0 * sum(1 for r in done
                            if (_fnum(r.get("latency_s")) or 0) > X
                            and str(r.get("http_status") or "").strip() == "200")
                / len(done)) if done else None)(_completed_rows(rows)))
        means.append(statistics.mean(pr) if pr else float("nan"))
        stds.append(statistics.stdev(pr) if len(pr) > 1 else 0.0)
        per_run.append(pr)
    _bar_with_dots(ax, labels, means, stds, per_run, colors,
                   f"completed requests with latency > {threshold}s (%)")
    fig.tight_layout()
    fig.savefig(_plot_path(out_dir, f"degraded_{threshold}s.png"), dpi=150)
    plt.close(fig)


def graph_endpoint_latency(out_dir, arms_data, q):
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = [ARM_LABELS[a] for a in ARM_ORDER]
    colors = [ARM_COLORS[a] for a in ARM_ORDER]
    means, stds, per_run = [], [], []
    for a in ARM_ORDER:
        pr = _per_run_req(
            arms_data[a],
            lambda rows: _pct([_fnum(r.get("latency_s"))
                               for r in _ok_rows(rows)
                               if _fnum(r.get("latency_s")) is not None], q))
        means.append(statistics.mean(pr) if pr else float("nan"))
        stds.append(statistics.stdev(pr) if len(pr) > 1 else 0.0)
        per_run.append(pr)
    _bar_with_dots(ax, labels, means, stds, per_run, colors,
                   f"endpoint latency p{int(q * 100)} (s)")
    fig.tight_layout()
    fig.savefig(_plot_path(out_dir, f"endpoint_latency_p{int(q * 100)}.png"),
                dpi=150)
    plt.close(fig)


def graph_reaction_max(out_dir, arms_data):
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = [ARM_LABELS[a] for a in ARM_ORDER]
    colors = [ARM_COLORS[a] for a in ARM_ORDER]
    means, stds, per_run = [], [], []
    for a in ARM_ORDER:
        pr = []
        for rd in arms_data[a]:
            rows = [r for r in _load_rows(
                os.path.join(rd, ANALYSIS_SUBDIR, "reaction_timeline.csv"))
                if (r.get("phase") or "").strip() == "compute_plateau"]
            vals = [(_fnum(r.get("scale_up_first_ts")) - _fnum(r.get("phase_start")))
                    for r in rows
                    if _fnum(r.get("scale_up_first_ts")) is not None
                    and _fnum(r.get("phase_start")) is not None]
            if vals:
                pr.append(max(vals))
        means.append(statistics.mean(pr) if pr else float("nan"))
        stds.append(statistics.stdev(pr) if len(pr) > 1 else 0.0)
        per_run.append(pr)
    _bar_with_dots(ax, labels, means, stds, per_run, colors,
                   "plateau → first scale-up decision, max over LANs (s)")
    fig.tight_layout()
    fig.savefig(_plot_path(out_dir, "reaction_latency_max.png"), dpi=150)
    plt.close(fig)


def _role_cpu_per_run(run_dirs, role):
    """Per-run mean node CPU% for a role during compute_plateau."""
    per_run = []
    for rd in run_dirs:
        rows = [r for r in _load_rows(os.path.join(rd, "per_node_stats.csv"))
                if (r.get("phase") or "").strip() == "compute_plateau"
                and (r.get("role") or "").strip() == role]
        vals = [_fnum(r.get("cpu_percent")) for r in rows
                if _fnum(r.get("cpu_percent")) is not None]
        if vals:
            per_run.append(statistics.mean(vals))
    return per_run


def _role_cpu_graph(out_dir, arms_data, role, fname, label):
    fig, ax = plt.subplots(figsize=(8, 5))
    labels = [ARM_LABELS[a] for a in ARM_ORDER]
    colors = [ARM_COLORS[a] for a in ARM_ORDER]
    means, stds, per_run = [], [], []
    for a in ARM_ORDER:
        pr = _role_cpu_per_run(arms_data[a], role)
        means.append(statistics.mean(pr) if pr else float("nan"))
        stds.append(statistics.stdev(pr) if len(pr) > 1 else 0.0)
        per_run.append(pr)
    _bar_with_dots(ax, labels, means, stds, per_run, colors, label)
    fig.tight_layout()
    fig.savefig(_plot_path(out_dir, fname), dpi=150)
    plt.close(fig)


def graph_compute_cpu(out_dir, arms_data):
    _role_cpu_graph(out_dir, arms_data, "compute", "compute_cpu.png",
                    "avg compute node CPU% (compute_plateau)")


def graph_storage_cpu(out_dir, arms_data):
    _role_cpu_graph(out_dir, arms_data, "storage", "storage_cpu.png",
                    "avg storage node CPU% (compute_plateau)")


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
    parser.add_argument("--run-dirs-sp", action="append", default=[],
                        metavar="DIR", help="Sampled-push (arm D) run folders")
    parser.add_argument("--output-dir", required=True,
                        help="Where to write the graph suite.")
    args = parser.parse_args()

    arms_data = {
        "ep": _parse_run_dirs(args.run_dirs_ep),
        "delayed": _parse_run_dirs(args.run_dirs_delayed),
        "ls": _parse_run_dirs(args.run_dirs_ls),
        "sp": _parse_run_dirs(args.run_dirs_sp),
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
    # cross-phase / cross-run / per-mode latency (raw phase labels)
    for q in (0.5, 0.95, 0.99):
        graph_per_phase_latency(args.output_dir, arms_data, q)
    # old-v13-inspired service-quality graphs (from client_requests)
    graph_throughput(args.output_dir, arms_data)
    graph_throughput_per_phase(args.output_dir, arms_data)
    graph_timeout(args.output_dir, arms_data)
    graph_per_phase_timeout(args.output_dir, arms_data)
    for x in (5, 10, 20):
        graph_degraded(args.output_dir, arms_data, x)
    for q in (0.5, 0.95):
        graph_endpoint_latency(args.output_dir, arms_data, q)
    graph_reaction_max(args.output_dir, arms_data)
    graph_compute_cpu(args.output_dir, arms_data)
    graph_storage_cpu(args.output_dir, arms_data)

    print(f"RQ1 comparison graphs written to {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
