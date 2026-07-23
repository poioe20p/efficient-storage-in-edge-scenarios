#!/usr/bin/env python3
"""RQ2 v3 campaign aggregation and thesis graph generation.

Aggregates per-run rq2_spawn_metrics.csv and client_requests.csv across all
runs, then generates the 11 thesis graphs (G1–G8 + G2b, G4b, G5b).

Usage:
    python -m source.scripts.testing.analysis.rq2.campaign_analysis \
        --run label:mode:path/to/run_folder \
        --run label2:mode2:path/to/run_folder2 \
        ... \
        --out-dir path/to/graphs
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODE_LABELS = {
    "topology_host":        "Host\n(round-robin)",
    "topology_slowstart":   "Slowstart\n(discovery delay)",
    "topology_lifecycle":   "Lifecycle\n(warm lease)",
}
MODE_COLORS = {
    "topology_host":        "#e74c3c",
    "topology_slowstart":   "#f39c12",
    "topology_lifecycle":   "#27ae60",
}
MODE_ORDER = ["topology_host", "topology_slowstart", "topology_lifecycle"]

NON_STRESS_PHASES = {"baseline", "cooldown_1", "cooldown_2", "cooldown_3", "demand_drop"}
STORAGE_PHASES = {"storage_storm", "storage_storm_2"}
COMPUTE_PHASES = {"compute_spike", "compute_spike_2"}
BASELINE_PHASE = {"baseline"}
POST_STRESS_PHASES = {"cooldown_1", "cooldown_2", "cooldown_3", "demand_drop"}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_spawn_metrics(run_dir: Path, mode: str) -> list[dict]:
    """Load rq2_spawn_metrics.csv from a run folder."""
    p = run_dir / "analysis" / "rq2_spawn_metrics.csv"
    if not p.exists():
        return []
    rows = []
    with open(p) as f:
        for row in csv.DictReader(f):
            row["run"] = run_dir.name
            row["mode"] = mode
            rows.append(row)
    return rows


def load_client_requests(run_dir: Path, mode: str) -> list[dict]:
    """Load client_requests.csv from a run folder."""
    p = run_dir / "client_requests.csv"
    if not p.exists():
        return []
    rows = []
    with open(p) as f:
        for row in csv.DictReader(f):
            row["run"] = run_dir.name
            row["mode"] = mode
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# Graph helpers
# ---------------------------------------------------------------------------

def _boxplot_with_scatter(ax, data: dict[str, list[float]], colors: dict[str, str],
                          ylabel: str, title: str):
    """Draw a box plot with individual data points overlaid."""
    modes = [m for m in MODE_ORDER if m in data and data[m]]
    if not modes:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
        return
    positions = list(range(len(modes)))
    bp = ax.boxplot([data[m] for m in modes], positions=positions, widths=0.5,
                     patch_artist=True)
    for i, mode in enumerate(modes):
        bp["boxes"][i].set_facecolor(colors[mode])
        vals = data[mode]
        x_jitter = np.random.default_rng(42).uniform(-0.12, 0.12, len(vals))
        ax.scatter(np.full(len(vals), positions[i]) + x_jitter, vals,
                   color="black", alpha=0.4, s=20, zorder=5)
        ax.annotate(f"n={len(vals)}", (positions[i], ax.get_ylim()[0] if ax.get_ylim()[0] > 0 else 0),
                    ha="center", va="top", fontsize=8,
                    xytext=(0, -15), textcoords="offset points")
    ax.set_xticks(positions)
    ax.set_xticklabels([MODE_LABELS[m] for m in modes], fontsize=9)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_title(title, fontsize=12)
    ax.grid(True, alpha=0.3, axis="y")


def _grouped_bar_with_error(ax, groups: list[str], mode_data: dict[str, dict[str, list[float]]],
                            colors: dict[str, str], ylabel: str, title: str):
    """Draw grouped bars with SEM error bars and scatter dots."""
    modes = [m for m in MODE_ORDER if m in mode_data]
    if not modes or not groups:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
        return
    x = np.arange(len(groups))
    n_modes = len(modes)
    width = 0.7 / n_modes
    rng = np.random.default_rng(42)
    for j, mode in enumerate(modes):
        means = []
        sems = []
        for g in groups:
            vals = mode_data[mode].get(g, [])
            if vals:
                means.append(np.mean(vals))
                sems.append(np.std(vals, ddof=1) / np.sqrt(len(vals)) if len(vals) > 1 else 0)
            else:
                means.append(0)
                sems.append(0)
        offset = (j - (n_modes - 1) / 2) * width
        bars = ax.bar(x + offset, means, width, label=MODE_LABELS[mode],
                      color=colors[mode], alpha=0.85)
        ax.errorbar(x + offset, means, yerr=sems, fmt="none", color="black", capsize=3)
        for gi, g in enumerate(groups):
            vals = mode_data[mode].get(g, [])
            if vals:
                x_jitter = rng.uniform(-width * 0.35, width * 0.35, len(vals))
                ax.scatter(np.full(len(vals), x[gi] + offset) + x_jitter, vals,
                           color="black", alpha=0.35, s=15, zorder=5)
    ax.set_xticks(x)
    ax.set_xticklabels(groups, fontsize=8, rotation=30, ha="right")
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_title(title, fontsize=12)
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3, axis="y")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="RQ2 v3 campaign analysis and graph generation")
    parser.add_argument("--run", action="append", dest="runs", default=[],
                        help="Format: label:mode:path (repeatable)")
    parser.add_argument("--out-dir", type=Path, required=True,
                        help="Output directory for graphs")
    args = parser.parse_args()

    if not args.runs:
        print("ERROR: at least one --run required")
        return 1

    # Parse run specs
    run_specs = []
    for spec in args.runs:
        parts = spec.split(":", 2)
        if len(parts) != 3:
            print(f"ERROR: invalid run spec '{spec}' — use label:mode:path")
            return 1
        run_specs.append((parts[0], parts[1], Path(parts[2])))

    args.out_dir.mkdir(parents=True, exist_ok=True)

    # ── Load spawn metrics ──────────────────────────────────────────
    all_spawns: list[dict] = []
    for label, mode, path in run_specs:
        rows = load_spawn_metrics(path, mode)
        print(f"{label} ({mode}): {len(rows)} spawn events")
        all_spawns.extend(rows)

    if not all_spawns:
        print("ERROR: no spawn metrics found — run extract_spawn_metrics.py first")
        return 1

    # ── Load client requests ────────────────────────────────────────
    all_requests: list[dict] = []
    for label, mode, path in run_specs:
        rows = load_client_requests(path, mode)
        all_requests.extend(rows)

    # ═════════════════════════════════════════════════════════════════
    # G1 — TTFT Distribution by Mode
    # ═════════════════════════════════════════════════════════════════
    ttft_data: dict[str, list[float]] = defaultdict(list)
    for s in all_spawns:
        if s.get("ttft_s"):
            ttft_data[s["mode"]].append(float(s["ttft_s"]))
    fig, ax = plt.subplots(figsize=(9, 6))
    _boxplot_with_scatter(ax, ttft_data, MODE_COLORS,
                          "TTFT (s)", "G1 — TTFT Distribution by Mode")
    fig.tight_layout()
    fig.savefig(args.out_dir / "g1_ttft.png", dpi=150)
    plt.close(fig)
    print("✓ G1 — TTFT Distribution by Mode")

    # ═════════════════════════════════════════════════════════════════
    # G2 — TFR Distribution by Mode
    # ═════════════════════════════════════════════════════════════════
    tfr_data: dict[str, list[float]] = defaultdict(list)
    for s in all_spawns:
        if s.get("tfr_s"):
            tfr_data[s["mode"]].append(float(s["tfr_s"]))
    fig, ax = plt.subplots(figsize=(9, 6))
    _boxplot_with_scatter(ax, tfr_data, MODE_COLORS,
                          "TFR (s)", "G2 — TFR Distribution by Mode")
    fig.tight_layout()
    fig.savefig(args.out_dir / "g2_tfr.png", dpi=150)
    plt.close(fig)
    print("✓ G2 — TFR Distribution by Mode")

    # ═════════════════════════════════════════════════════════════════
    # G2b — TTFT vs TFR Scatter by Mode
    # ═════════════════════════════════════════════════════════════════
    fig, ax = plt.subplots(figsize=(9, 7))
    for mode in MODE_ORDER:
        xs = [float(s["ttft_s"]) for s in all_spawns
              if s["mode"] == mode and s.get("ttft_s") and s.get("tfr_s")]
        ys = [float(s["tfr_s"]) for s in all_spawns
              if s["mode"] == mode and s.get("ttft_s") and s.get("tfr_s")]
        if xs:
            ax.scatter(xs, ys, color=MODE_COLORS[mode], alpha=0.6, s=40,
                       label=MODE_LABELS[mode], edgecolors="black", linewidth=0.3)
    lims = [0, max(ax.get_xlim()[1], ax.get_ylim()[1])]
    ax.plot(lims, lims, "k--", alpha=0.3, linewidth=1)
    ax.set_xlabel("TTFT (s)", fontsize=11)
    ax.set_ylabel("TFR (s)", fontsize=11)
    ax.set_title("G2b — TTFT vs TFR by Mode\n(diagonal = backend ready when traffic arrived)", fontsize=12)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(args.out_dir / "g2b_ttft_vs_tfr.png", dpi=150)
    plt.close(fig)
    print("✓ G2b — TTFT vs TFR Scatter")

    # ═════════════════════════════════════════════════════════════════
    # G3 — Backend Initialisation Time by Mode
    # ═════════════════════════════════════════════════════════════════
    init_data: dict[str, list[float]] = defaultdict(list)
    for s in all_spawns:
        if s.get("init_time_s"):
            init_data[s["mode"]].append(float(s["init_time_s"]))
    fig, ax = plt.subplots(figsize=(9, 6))
    _boxplot_with_scatter(ax, init_data, MODE_COLORS,
                          "Init Time (s)", "G3 — Backend Initialisation Time (TFR − TTFT) by Mode")
    fig.tight_layout()
    fig.savefig(args.out_dir / "g3_init_time.png", dpi=150)
    plt.close(fig)
    print("✓ G3 — Backend Initialisation Time by Mode")

    # ═════════════════════════════════════════════════════════════════
    # G4 — Initial Load Share Distribution by Mode
    # ═════════════════════════════════════════════════════════════════
    share_data: dict[str, list[float]] = defaultdict(list)
    for s in all_spawns:
        if s.get("initial_share"):
            share_data[s["mode"]].append(float(s["initial_share"]))
    fig, ax = plt.subplots(figsize=(9, 6))
    _boxplot_with_scatter(ax, share_data, MODE_COLORS,
                          "Initial Load Share", "G4 — Initial Load Share Distribution by Mode")
    fig.tight_layout()
    fig.savefig(args.out_dir / "g4_initial_share.png", dpi=150)
    plt.close(fig)
    print("✓ G4 — Initial Load Share Distribution by Mode")

    # ═════════════════════════════════════════════════════════════════
    # G4b — TTFT vs Initial Share Scatter by Mode
    # ═════════════════════════════════════════════════════════════════
    fig, ax = plt.subplots(figsize=(9, 7))
    for mode in MODE_ORDER:
        xs = [float(s["ttft_s"]) for s in all_spawns
              if s["mode"] == mode and s.get("ttft_s") and s.get("initial_share")]
        ys = [float(s["initial_share"]) for s in all_spawns
              if s["mode"] == mode and s.get("ttft_s") and s.get("initial_share")]
        if xs:
            ax.scatter(xs, ys, color=MODE_COLORS[mode], alpha=0.6, s=40,
                       label=MODE_LABELS[mode], edgecolors="black", linewidth=0.3)
    ax.set_xlabel("TTFT (s)", fontsize=11)
    ax.set_ylabel("Initial Load Share", fontsize=11)
    ax.set_title("G4b — TTFT vs Initial Load Share by Mode", fontsize=12)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(args.out_dir / "g4b_ttft_vs_share.png", dpi=150)
    plt.close(fig)
    print("✓ G4b — TTFT vs Initial Share Scatter")

    # ── Build per-phase latency data ────────────────────────────────
    run_phase_raw: dict[str, dict[str, dict[str, list[float]]]] = \
        defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for r in all_requests:
        mode = r.get("mode", "")
        phase = r.get("phase", "")
        run_label = r.get("run", "")
        latency = float(r.get("latency_s", 0)) * 1000  # ms
        if mode and phase and run_label and latency >= 0:
            run_phase_raw[mode][phase][run_label].append(latency)

    # Per-mode per-phase p50 across replicates (for error bars)
    mode_phase_p50_reps: dict[str, dict[str, list[float]]] = \
        defaultdict(lambda: defaultdict(list))
    for mode in run_phase_raw:
        for phase in run_phase_raw[mode]:
            for run_label in run_phase_raw[mode][phase]:
                vals = run_phase_raw[mode][phase][run_label]
                mode_phase_p50_reps[mode][phase].append(np.percentile(vals, 50))

    # ═════════════════════════════════════════════════════════════════
    # G5 — Baseline p50 Latency by Mode
    # ═════════════════════════════════════════════════════════════════
    g5_data: dict[str, dict[str, list[float]]] = defaultdict(dict)
    for mode in MODE_ORDER:
        if "baseline" in mode_phase_p50_reps.get(mode, {}):
            g5_data[mode]["baseline"] = mode_phase_p50_reps[mode]["baseline"]
    fig, ax = plt.subplots(figsize=(6, 6))
    if g5_data:
        _grouped_bar_with_error(ax, ["baseline"], g5_data, MODE_COLORS,
                                "p50 Latency (ms)", "G5 — Baseline p50 Latency by Mode")
    else:
        ax.text(0.5, 0.5, "No baseline data", ha="center", va="center")
    fig.tight_layout()
    fig.savefig(args.out_dir / "g5_baseline_p50.png", dpi=150)
    plt.close(fig)
    print("✓ G5 — Baseline p50 Latency by Mode")

    # ═════════════════════════════════════════════════════════════════
    # G5b — Non-Stress p50 Latency by Mode
    # ═════════════════════════════════════════════════════════════════
    non_stress_phases = sorted(NON_STRESS_PHASES)
    g5b_data: dict[str, dict[str, list[float]]] = defaultdict(dict)
    for mode in MODE_ORDER:
        for phase in non_stress_phases:
            if phase in mode_phase_p50_reps.get(mode, {}):
                g5b_data[mode][phase] = mode_phase_p50_reps[mode][phase]
    fig, ax = plt.subplots(figsize=(12, 6))
    if g5b_data:
        _grouped_bar_with_error(ax, non_stress_phases, g5b_data, MODE_COLORS,
                                "p50 Latency (ms)", "G5b — Non-Stress p50 Latency by Mode")
    else:
        ax.text(0.5, 0.5, "No non-stress data", ha="center", va="center")
    fig.tight_layout()
    fig.savefig(args.out_dir / "g5b_nonstress_p50.png", dpi=150)
    plt.close(fig)
    print("✓ G5b — Non-Stress p50 Latency by Mode")

    # ═════════════════════════════════════════════════════════════════
    # G6 — Per-Phase p50 Latency by Mode (master graph)
    # ═════════════════════════════════════════════════════════════════
    all_phases = sorted(set(p for mode_data in mode_phase_p50_reps.values() for p in mode_data))
    g6_data: dict[str, dict[str, list[float]]] = defaultdict(dict)
    for mode in MODE_ORDER:
        for phase in all_phases:
            if phase in mode_phase_p50_reps.get(mode, {}):
                g6_data[mode][phase] = mode_phase_p50_reps[mode][phase]
    fig, ax = plt.subplots(figsize=(16, 7))
    if g6_data:
        _grouped_bar_with_error(ax, all_phases, g6_data, MODE_COLORS,
                                "p50 Latency (ms)", "G6 — Per-Phase p50 Latency by Mode")
    else:
        ax.text(0.5, 0.5, "No phase data", ha="center", va="center")
    fig.tight_layout()
    fig.savefig(args.out_dir / "g6_per_phase_p50.png", dpi=150)
    plt.close(fig)
    print("✓ G6 — Per-Phase p50 Latency by Mode")

    # ═════════════════════════════════════════════════════════════════
    # G7 — Per-Mode Latency Percentiles (p50/p95/p99)
    # ═════════════════════════════════════════════════════════════════
    run_pct_data: dict[str, dict[str, list[float]]] = \
        defaultdict(lambda: defaultdict(list))
    for r in all_requests:
        mode = r.get("mode", "")
        run_label = r.get("run", "")
        latency = float(r.get("latency_s", 0)) * 1000
        if mode and run_label and latency >= 0:
            run_pct_data[mode][run_label].append(latency)

    g7_data: dict[str, dict[str, list[float]]] = defaultdict(dict)
    for mode in MODE_ORDER:
        p50s, p95s, p99s = [], [], []
        for run_label in run_pct_data.get(mode, {}):
            vals = run_pct_data[mode][run_label]
            p50s.append(np.percentile(vals, 50))
            p95s.append(np.percentile(vals, 95))
            p99s.append(np.percentile(vals, 99))
        g7_data[mode]["p50"] = p50s
        g7_data[mode]["p95"] = p95s
        g7_data[mode]["p99"] = p99s

    fig, ax = plt.subplots(figsize=(10, 6))
    groups = ["p50", "p95", "p99"]
    _grouped_bar_with_error(ax, groups, g7_data, MODE_COLORS,
                            "Latency (ms)", "G7 — Per-Mode Latency Percentiles")
    ax.set_yscale("log")
    fig.tight_layout()
    fig.savefig(args.out_dir / "g7_percentiles.png", dpi=150)
    plt.close(fig)
    print("✓ G7 — Per-Mode Latency Percentiles")

    # ═════════════════════════════════════════════════════════════════
    # G8 — Latency by Phase Type (baseline / post-stress / storage / compute)
    # ═════════════════════════════════════════════════════════════════
    type_groups = {
        "Baseline": BASELINE_PHASE,
        "Post-stress": POST_STRESS_PHASES,
        "Storage": STORAGE_PHASES,
        "Compute": COMPUTE_PHASES,
    }
    g8_data: dict[str, dict[str, list[float]]] = defaultdict(dict)
    for mode in MODE_ORDER:
        if mode not in run_phase_raw:
            continue
        # Collect per-run p95 per phase type
        run_type_p95: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for phase in run_phase_raw[mode]:
            for type_name, phases in type_groups.items():
                if phase in phases:
                    for run_label in run_phase_raw[mode][phase]:
                        vals = run_phase_raw[mode][phase][run_label]
                        run_type_p95[run_label][type_name].extend(vals)
        for type_name in type_groups:
            reps = []
            for run_label in run_type_p95:
                vals = run_type_p95[run_label].get(type_name, [])
                if vals:
                    reps.append(np.percentile(vals, 95))
            if reps:
                g8_data[mode][type_name] = reps

    fig, ax = plt.subplots(figsize=(12, 7))
    type_order = ["Baseline", "Post-stress", "Storage", "Compute"]
    _grouped_bar_with_error(ax, type_order, g8_data, MODE_COLORS,
                            "p95 Latency (ms)", "G8 — Latency by Phase Type (p95)")
    fig.tight_layout()
    fig.savefig(args.out_dir / "g8_phase_type_p95.png", dpi=150)
    plt.close(fig)
    print("✓ G8 — Latency by Phase Type")

    # ── Summary statistics ──────────────────────────────────────────
    print("\n=== Campaign Summary ===")
    for mode in MODE_ORDER:
        for metric_name, key in [("TTFT", "ttft_s"), ("TFR", "tfr_s"),
                                  ("Init Time", "init_time_s"),
                                  ("Initial Share", "initial_share")]:
            vals = [float(s[key]) for s in all_spawns
                    if s["mode"] == mode and s.get(key)]
            if vals:
                print(f"  {mode} {metric_name}: n={len(vals)}  "
                      f"median={np.median(vals):.1f}  mean={np.mean(vals):.1f}  "
                      f"p95={np.percentile(vals, 95):.1f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
