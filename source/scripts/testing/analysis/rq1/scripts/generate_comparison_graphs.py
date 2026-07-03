"""Generate RQ1 mode-comparison bar charts.

Produces summary PNGs comparing Push, Poll-5s, Poll-12s, and Poll-30s across:
  - Reaction latency (mean, max, combined)
  - Controller CPU% and RSS
  - Information age (staleness)
  - Timeout rate (overall + per-phase)
  - Average failure rate (dedicated)
  - Decision quality (cross-mode per-phase table + CSV)

Usage:
    python -m source.scripts.testing.analysis.rq1.scripts.generate_comparison_graphs \
        --run-dirs-push <push_1> <push_2> <push_3> \
        --run-dirs-poll5 <poll5_1> <poll5_2> <poll5_3> \
        --run-dirs-poll12 <poll12_1> <poll12_2> <poll12_3> \
        --run-dirs-poll30 <poll30_1> <poll30_2> <poll30_3> \
        --output-dir <dir>
"""
from __future__ import annotations

import argparse
import csv
import os
from pathlib import Path

import numpy as np


def _safe_read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def collect_mode_data(run_dirs: list[Path]) -> dict:
    """Collect aggregated metrics for a set of replicate runs."""
    lats = []
    cpus = []
    rams = []
    stales = []
    timeouts = []
    per_phase: dict[str, list[float]] = {}

    for run_dir in run_dirs:
        # Reaction latency
        for row in _safe_read_csv(run_dir / "analysis" / "rq1_reaction_latency.csv"):
            lats.append(float(row["total_reaction_s"]))

        # Controller CPU/RAM
        ctrl_rows = _safe_read_csv(run_dir / "controller_stats.csv")
        if ctrl_rows:
            cpus.append(np.mean([float(r.get("cpu_percent", 0) or 0) for r in ctrl_rows]))
            rams.append(np.mean([float(r.get("mem_usage_mb", 0) or 0) for r in ctrl_rows]))

        # Staleness
        for row in _safe_read_csv(run_dir / "analysis" / "rq1_staleness.csv"):
            stales.append(float(row["staleness_s"]))

        # Timeout rate
        cr_rows = _safe_read_csv(run_dir / "client_requests.csv")
        if cr_rows:
            total = len(cr_rows)
            failed = sum(1 for r in cr_rows if r.get("http_status", "200") == "0")
            timeouts.append((failed / total) * 100 if total else 0)

            # Per-phase
            for r in cr_rows:
                ph = r.get("phase", "unknown")
                if ph not in per_phase:
                    per_phase[ph] = []
            # Compute per-phase rates per run
            phase_counts: dict[str, dict] = {}
            for r in cr_rows:
                ph = r.get("phase", "unknown")
                if ph not in phase_counts:
                    phase_counts[ph] = {"total": 0, "fail": 0}
                phase_counts[ph]["total"] += 1
                if r.get("http_status", "200") == "0":
                    phase_counts[ph]["fail"] += 1
            for ph, d in phase_counts.items():
                rate = (d["fail"] / d["total"]) * 100 if d["total"] else 0
                per_phase.setdefault(ph, []).append(rate)

    return {
        "latency_mean": np.mean(lats) if lats else 0,
        "latency_max": np.max(lats) if lats else 0,
        "cpu_mean": np.mean(cpus) if cpus else 0,
        "ram_mean": np.mean(rams) if rams else 0,
        "staleness_max": np.max(stales) if stales else 0,
        "staleness_values": stales,
        "timeout_mean": np.mean(timeouts) if timeouts else 0,
        "timeout_values": timeouts,
        "per_phase": {ph: np.mean(rates) for ph, rates in per_phase.items()},
    }


# ── Decision quality collection ─────────────────────────────────

DQ_PHASE_ORDER = [
    "baseline", "storage_storm", "tier1_hotspot",
    "inter_hotspot_cooldown", "reverse_hotspot",
    "compute_spike", "demand_drop",
]


def _collect_dq_for_mode(run_dirs: list[Path]) -> dict[str, dict]:
    """Read per-run rq1_decision_quality.csv files and aggregate across
    replicates. Returns {phase_name: {breached_pct: [vals], spawns: [vals]}}."""
    phase_data: dict[str, dict] = {}
    for run_dir in run_dirs:
        dq_csv = run_dir / "analysis" / "rq1" / "rq1_decision_quality.csv"
        if not dq_csv.exists():
            continue
        with open(dq_csv) as f:
            rows = list(csv.DictReader(f))
        for r in rows:
            ph = r["phase"]
            if ph not in phase_data:
                phase_data[ph] = {"breached_pct": [], "spawns": []}
            tw = int(r.get("total_windows", 0))
            bw = int(r.get("breached_windows", 0))
            sp = int(r.get("spawns_initiated", 0))
            pct = (bw / tw * 100) if tw > 0 else 0.0
            phase_data[ph]["breached_pct"].append(pct)
            phase_data[ph]["spawns"].append(sp)
    # Average across replicates
    result: dict[str, dict] = {}
    for ph, d in phase_data.items():
        result[ph] = {
            "breached_pct": np.mean(d["breached_pct"]) if d["breached_pct"] else 0,
            "spawns": np.mean(d["spawns"]) if d["spawns"] else 0,
        }
    return result


def _plot_decision_quality_table(
    all_dq: list[dict[str, dict]],
    output_dir: Path,
) -> None:
    """Render a cross-mode decision quality comparison table as PNG.

    Columns: Phase | Push Br% | Push Spwn | Poll-5s Br% | Poll-5s Spwn |
             Poll-12s Br% | Poll-12s Spwn | Poll-30s Br% | Poll-30s Spwn

    Footnote explains Br% and Spwn formulas.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    col_labels = [
        "Phase",
        "Push\nBr%", "Push\nSpwn",
        "Poll-5s\nBr%", "Poll-5s\nSpwn",
        "Poll-12s\nBr%", "Poll-12s\nSpwn",
        "Poll-30s\nBr%", "Poll-30s\nSpwn",
    ]
    cell_text: list[list[str]] = []
    for ph in DQ_PHASE_ORDER:
        row: list[str] = [ph.replace("_", "\n")]
        for dq in all_dq:
            entry = dq.get(ph, {"breached_pct": 0, "spawns": 0})
            br_pct = entry["breached_pct"]
            sp = entry["spawns"]
            row.append(f"{br_pct:.0f}%" if br_pct > 0 else "-")
            row.append(f"{sp:.1f}" if sp > 0 else "-")
        cell_text.append(row)

    n_phases = len(DQ_PHASE_ORDER)
    fig, ax = plt.subplots(figsize=(18, max(3.5, n_phases * 0.6 + 2.5)))
    ax.axis("off")
    fig.suptitle("RQ1 v2 — Decision Quality: Breached Windows & Spawns by Phase / Mode",
                 fontsize=13, fontweight="bold")

    table = ax.table(
        cellText=cell_text,
        colLabels=col_labels,
        loc="upper center",
        cellLoc="center",
    )
    table.auto_set_font_size(False)
    table.set_fontsize(8.5)
    table.auto_set_column_width(list(range(len(col_labels))))

    # Highlight phases with any breach activity
    for i, ph in enumerate(DQ_PHASE_ORDER):
        has_breach = any(
            dq.get(ph, {}).get("breached_pct", 0) > 0
            for dq in all_dq
        )
        if has_breach:
            for j in range(len(col_labels)):
                cell = table[i + 1, j]
                cell.set_facecolor("#fff3e0")

    # Footnote with formula explanation
    footnote = (
        "Br% = mean(breached_windows / total_windows × 100) across replicates  |  "
        "Spwn = mean(spawns_initiated) across replicates  |  "
        "Orange rows = at least one mode recorded breached windows in that phase"
    )
    fig.text(0.5, 0.02, footnote, ha="center", fontsize=8, style="italic", color="#555555")

    fig.tight_layout(rect=[0, 0.06, 1, 0.95])
    path = output_dir / "rq1_v2_decision_quality.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"Wrote {path}")


def _write_decision_quality_csv(
    all_dq: list[dict[str, dict]],
    output_dir: Path,
) -> None:
    """Write cross-mode decision quality CSV."""
    path = output_dir / "rq1_v2_decision_quality.csv"
    with path.open("w", newline="", encoding="utf-8") as f:
        fieldnames = [
            "phase",
            "push_breached_pct", "push_spawns",
            "poll5_breached_pct", "poll5_spawns",
            "poll12_breached_pct", "poll12_spawns",
            "poll30_breached_pct", "poll30_spawns",
        ]
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for ph in DQ_PHASE_ORDER:
            row: dict = {"phase": ph}
            for i, mode_key in enumerate(["push", "poll5", "poll12", "poll30"]):
                entry = all_dq[i].get(ph, {"breached_pct": 0, "spawns": 0})
                row[f"{mode_key}_breached_pct"] = round(entry["breached_pct"], 1)
                row[f"{mode_key}_spawns"] = round(entry["spawns"], 1)
            w.writerow(row)
    print(f"Wrote {path}")


PHASE_ORDER = [
    "baseline", "storage_storm", "tier1_hotspot",
    "inter_hotspot_cooldown", "reverse_hotspot",
    "compute_spike", "demand_drop",
]
MODE_COLORS = ["#2196F3", "#4CAF50", "#FF9800", "#F44336"]
MODE_LABELS = ["Push", "Poll-5s", "Poll-12s", "Poll-30s"]

# ── Style constants ──────────────────────────────────────────────
FIG_SINGLE = (10, 6)
FIG_DOUBLE = (14, 6)
FIG_PER_PHASE = (14, 6)
TITLE_SIZE = 13
LABEL_SIZE = 12
TICK_SIZE = 11
ANNO_SIZE = 11
DOT_SIZE = 50
BAR_ALPHA = 0.75
GRID_ALPHA = 0.25
RNG = np.random.default_rng(42)


def _style_bar_ax(ax, x, modes, ylabel, title):
    """Apply consistent styling to a single bar-chart axis."""
    ax.set_xticks(x)
    ax.set_xticklabels(modes, fontsize=TICK_SIZE)
    ax.set_ylabel(ylabel, fontsize=LABEL_SIZE)
    ax.set_title(title, fontsize=TITLE_SIZE, fontweight="bold")
    ax.grid(axis="y", alpha=GRID_ALPHA, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def _add_scatter_dots(ax, x, data, key):
    """Add per-replicate scatter dots overlaid on bars."""
    for i, d in enumerate(data):
        vals = d.get(key, [])
        if vals and len(vals) > 1:
            jitter = RNG.uniform(-0.14, 0.14, len(vals))
            ax.scatter(
                np.full(len(vals), x[i]) + jitter, vals,
                color="black", s=DOT_SIZE, zorder=5,
                edgecolors="white", linewidth=1,
            )


def _add_bar_labels(ax, x, data, key, fmt, offset):
    """Add value labels above each bar."""
    for i, d in enumerate(data):
        v = d[key]
        ax.text(i, v + offset, fmt.format(v), ha="center",
                fontweight="bold", fontsize=ANNO_SIZE)



def generate_graphs(
    push_dirs: list[Path],
    poll5_dirs: list[Path],
    poll12_dirs: list[Path],
    poll30_dirs: list[Path],
    output_dir: Path,
) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[generate_comparison_graphs] matplotlib not installed")
        return

    output_dir.mkdir(parents=True, exist_ok=True)

    all_dirs = [push_dirs, poll5_dirs, poll12_dirs, poll30_dirs]
    data = [collect_mode_data(dirs) for dirs in all_dirs]
    x = np.arange(len(MODE_LABELS))

    # ── Graph 1a: Mean Reaction Latency ──────────────────────────
    fig, ax = plt.subplots(figsize=FIG_SINGLE)
    _style_bar_ax(ax, x, MODE_LABELS, "Mean Reaction Latency (s)",
                  "RQ1 v2 — Mean Reaction Latency by Telemetry Mode")
    ax.bar(x, [d["latency_mean"] for d in data], color=MODE_COLORS,
            edgecolor="black", alpha=BAR_ALPHA)
    _add_bar_labels(ax, x, data, "latency_mean", "{:.1f}s", 2)
    plt.tight_layout()
    fig.savefig(output_dir / "rq1_v2_latency_mean.png", dpi=150)
    plt.close(fig)
    print(f"Wrote {output_dir / 'rq1_v2_latency_mean.png'}")

    # ── Graph 1b: Max Reaction Latency ───────────────────────────
    fig, ax = plt.subplots(figsize=FIG_SINGLE)
    _style_bar_ax(ax, x, MODE_LABELS, "Max Reaction Latency (s)",
                  "RQ1 v2 — Max Reaction Latency by Telemetry Mode")
    ax.bar(x, [d["latency_max"] for d in data], color=MODE_COLORS,
            edgecolor="black", alpha=BAR_ALPHA)
    _add_bar_labels(ax, x, data, "latency_max", "{:.1f}s", 3)
    plt.tight_layout()
    fig.savefig(output_dir / "rq1_v2_latency_max.png", dpi=150)
    plt.close(fig)
    print(f"Wrote {output_dir / 'rq1_v2_latency_max.png'}")

    # ── Graph 1c: Reaction Latency Comparison (combined) ─────────
    fig, ax = plt.subplots(figsize=FIG_SINGLE)
    w = 0.35
    ax.bar(x - w/2, [d["latency_mean"] for d in data], w, label="Mean",
           color="#90CAF9", edgecolor="black", alpha=BAR_ALPHA)
    ax.bar(x + w/2, [d["latency_max"] for d in data], w, label="Max",
           color="#1565C0", edgecolor="black", alpha=BAR_ALPHA)
    _style_bar_ax(ax, x, MODE_LABELS, "Reaction Latency (s)",
                  "RQ1 v2 — Reaction Latency by Telemetry Mode")
    ax.legend(fontsize=TICK_SIZE - 1)
    # Annotate values
    for i in range(len(data)):
        ax.text(i - w/2, data[i]["latency_mean"] + 1, f'{data[i]["latency_mean"]:.0f}s',
                ha="center", fontsize=ANNO_SIZE - 2, fontweight="bold", color="#1565C0")
        ax.text(i + w/2, data[i]["latency_max"] + 1, f'{data[i]["latency_max"]:.0f}s',
                ha="center", fontsize=ANNO_SIZE - 2, fontweight="bold", color="#0D47A1")
    plt.tight_layout()
    fig.savefig(output_dir / "rq1_v2_reaction_latency.png", dpi=150)
    plt.close(fig)
    print(f"Wrote {output_dir / 'rq1_v2_reaction_latency.png'}")

    # ── Graph 2: Controller Overhead ─────────────────────────────
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=FIG_DOUBLE)
    _style_bar_ax(ax1, x, MODE_LABELS, "CPU %",
                  "RQ1 v2 — Avg Controller CPU by Telemetry Mode")
    ax1.bar(x, [d["cpu_mean"] for d in data], color=MODE_COLORS,
            edgecolor="black", alpha=BAR_ALPHA)
    _add_bar_labels(ax1, x, data, "cpu_mean", "{:.1f}%", 0.15)
    _style_bar_ax(ax2, x, MODE_LABELS, "RSS (MB)",
                  "RQ1 v2 — Avg Controller RAM by Telemetry Mode")
    ax2.bar(x, [d["ram_mean"] for d in data], color=MODE_COLORS,
            edgecolor="black", alpha=BAR_ALPHA)
    _add_bar_labels(ax2, x, data, "ram_mean", "{:.0f} MB", 2)
    plt.tight_layout()
    fig.savefig(output_dir / "rq1_v2_overhead_comparison.png", dpi=150)
    plt.close(fig)
    print(f"Wrote {output_dir / 'rq1_v2_overhead_comparison.png'}")

    # ── Graph 3: Staleness ───────────────────────────────────────
    fig, ax = plt.subplots(figsize=FIG_SINGLE)
    _style_bar_ax(ax, x, MODE_LABELS, "Max Staleness (s)",
                  "RQ1 v2 — Max Information Age (Staleness) by Telemetry Mode")
    ax.bar(x, [d["staleness_max"] for d in data], color=MODE_COLORS,
           edgecolor="black", alpha=BAR_ALPHA)
    _add_bar_labels(ax, x, data, "staleness_max", "{:.1f}s", 0.3)
    plt.tight_layout()
    fig.savefig(output_dir / "rq1_v2_staleness_comparison.png", dpi=150)
    plt.close(fig)
    print(f"Wrote {output_dir / 'rq1_v2_staleness_comparison.png'}")

    # ── Graph 4: Timeout Rate ────────────────────────────────────
    fig, ax = plt.subplots(figsize=FIG_SINGLE)
    _style_bar_ax(ax, x, MODE_LABELS, "Timeout Rate (%)",
                  "RQ1 v2 — Mean Timeout Rate by Telemetry Mode")
    ax.bar(x, [d["timeout_mean"] for d in data], color=MODE_COLORS,
           edgecolor="black", alpha=BAR_ALPHA)
    _add_bar_labels(ax, x, data, "timeout_mean", "{:.1f}%", 2)
    plt.tight_layout()
    fig.savefig(output_dir / "rq1_v2_timeout_comparison.png", dpi=150)
    plt.close(fig)
    print(f"Wrote {output_dir / 'rq1_v2_timeout_comparison.png'}")

    # ── Graph 5: Per-Phase Timeout ───────────────────────────────
    fig, ax = plt.subplots(figsize=FIG_PER_PHASE)
    phase_x = np.arange(len(PHASE_ORDER))
    width = 0.2
    for i, (mode, d) in enumerate(zip(MODE_LABELS, data)):
        values = [d["per_phase"].get(ph, 0) for ph in PHASE_ORDER]
        ax.bar(phase_x + i * width, values, width, label=mode,
               color=MODE_COLORS[i], edgecolor="black", alpha=BAR_ALPHA)
    ax.set_xticks(phase_x + width * 1.5)
    ax.set_xticklabels([p.replace("_", "\n") for p in PHASE_ORDER],
                       fontsize=TICK_SIZE - 1)
    ax.set_ylabel("Timeout Rate (%)", fontsize=LABEL_SIZE)
    ax.set_title("RQ1 v2 — Per-Phase Timeout Rate by Telemetry Mode",
                 fontsize=TITLE_SIZE, fontweight="bold")
    ax.legend(fontsize=TICK_SIZE - 1, framealpha=0.8)
    ax.grid(axis="y", alpha=GRID_ALPHA, linestyle="--")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    fig.savefig(output_dir / "rq1_v2_per_phase_timeout.png", dpi=150)
    plt.close(fig)
    print(f"Wrote {output_dir / 'rq1_v2_per_phase_timeout.png'}")

    # ── Graph 6: Average Failure Rate (dedicated) ────────────────
    fig, ax = plt.subplots(figsize=FIG_SINGLE)
    _style_bar_ax(ax, x, MODE_LABELS, "Average Failure Rate (%)",
                  "RQ1 v2 — Average Failure Rate by Telemetry Mode")
    ax.bar(x, [d["timeout_mean"] for d in data], color=MODE_COLORS,
           edgecolor="black", alpha=BAR_ALPHA)
    _add_bar_labels(ax, x, data, "timeout_mean", "{:.1f}%", 2)
    # Add reference line for healthy baseline
    ax.axhline(y=2.0, color="green", linestyle="--", alpha=0.4,
               label="~2% healthy baseline")
    ax.legend(fontsize=TICK_SIZE - 1)
    plt.tight_layout()
    fig.savefig(output_dir / "rq1_v2_avg_failure_rate.png", dpi=150)
    plt.close(fig)
    print(f"Wrote {output_dir / 'rq1_v2_avg_failure_rate.png'}")

    # ── Graph 7: Decision Quality Comparison Table ───────────────
    all_dq = [_collect_dq_for_mode(dirs) for dirs in all_dirs]
    _plot_decision_quality_table(all_dq, output_dir)
    _write_decision_quality_csv(all_dq, output_dir)

    print("\nAll comparison graphs generated.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate RQ1 mode-comparison graphs")
    parser.add_argument("--run-dirs-push", nargs="+", required=True, dest="push",
                        help="Push mode run directories (3 replicates)")
    parser.add_argument("--run-dirs-poll5", nargs="+", required=True, dest="poll5",
                        help="Poll-5s mode run directories (3 replicates)")
    parser.add_argument("--run-dirs-poll12", nargs="+", required=True, dest="poll12",
                        help="Poll-12s mode run directories (3 replicates)")
    parser.add_argument("--run-dirs-poll30", nargs="+", required=True, dest="poll30",
                        help="Poll-30s mode run directories (3 replicates)")
    parser.add_argument("--output-dir", required=True, dest="output",
                        help="Output directory for PNGs")
    args = parser.parse_args()

    generate_graphs(
        push_dirs=[Path(d) for d in args.push],
        poll5_dirs=[Path(d) for d in args.poll5],
        poll12_dirs=[Path(d) for d in args.poll12],
        poll30_dirs=[Path(d) for d in args.poll30],
        output_dir=Path(args.output),
    )


if __name__ == "__main__":
    main()
