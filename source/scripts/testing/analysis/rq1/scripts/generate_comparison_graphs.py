"""Generate RQ1 mode-comparison bar charts.

Produces summary PNGs comparing Push, Poll-5s, Poll-12s, and Poll-30s across:
  - Reaction latency (mean + max)
  - Controller CPU% and RSS
  - Information age (staleness)
  - Timeout rate (overall + per-phase)

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
        "timeout_mean": np.mean(timeouts) if timeouts else 0,
        "per_phase": {ph: np.mean(rates) for ph, rates in per_phase.items()},
    }


PHASE_ORDER = [
    "baseline", "storage_storm", "tier1_hotspot",
    "inter_hotspot_cooldown", "reverse_hotspot",
    "compute_spike", "demand_drop",
]
MODE_COLORS = ["#2196F3", "#4CAF50", "#FF9800", "#F44336"]


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

    modes = ["Push", "Poll-5s", "Poll-12s", "Poll-30s"]
    all_dirs = [push_dirs, poll5_dirs, poll12_dirs, poll30_dirs]
    data = [collect_mode_data(dirs) for dirs in all_dirs]
    x = np.arange(len(modes))

    # --- Graph 1: Reaction Latency ---
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    ax1.bar(x, [d["latency_mean"] for d in data], color=MODE_COLORS, edgecolor="black")
    ax1.set_xticks(x); ax1.set_xticklabels(modes)
    ax1.set_ylabel("Mean Reaction Latency (s)")
    ax1.set_title("RQ1 v2 — Mean Reaction Latency per Mode")
    for i, d in enumerate(data):
        ax1.text(i, d["latency_mean"] + 1, f'{d["latency_mean"]:.1f}s', ha="center", fontweight="bold")

    ax2.bar(x, [d["latency_max"] for d in data], color=MODE_COLORS, edgecolor="black")
    ax2.set_xticks(x); ax2.set_xticklabels(modes)
    ax2.set_ylabel("Max Reaction Latency (s)")
    ax2.set_title("RQ1 v2 — Max Reaction Latency per Mode")
    for i, d in enumerate(data):
        ax2.text(i, d["latency_max"] + 2, f'{d["latency_max"]:.1f}s', ha="center", fontweight="bold")
    plt.tight_layout()
    fig.savefig(output_dir / "rq1_v2_latency_comparison.png", dpi=150)
    plt.close(fig)
    print(f"Wrote {output_dir / 'rq1_v2_latency_comparison.png'}")

    # --- Graph 2: Controller Overhead ---
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))
    ax1.bar(x, [d["cpu_mean"] for d in data], color=MODE_COLORS, edgecolor="black")
    ax1.set_xticks(x); ax1.set_xticklabels(modes)
    ax1.set_ylabel("CPU %"); ax1.set_title("RQ1 v2 — Avg Controller CPU per Mode")
    for i, d in enumerate(data):
        ax1.text(i, d["cpu_mean"] + 0.1, f'{d["cpu_mean"]:.1f}%', ha="center", fontweight="bold")

    ax2.bar(x, [d["ram_mean"] for d in data], color=MODE_COLORS, edgecolor="black")
    ax2.set_xticks(x); ax2.set_xticklabels(modes)
    ax2.set_ylabel("RSS (MB)"); ax2.set_title("RQ1 v2 — Avg Controller RAM per Mode")
    for i, d in enumerate(data):
        ax2.text(i, d["ram_mean"] + 1, f'{d["ram_mean"]:.0f}MB', ha="center", fontweight="bold")
    plt.tight_layout()
    fig.savefig(output_dir / "rq1_v2_overhead_comparison.png", dpi=150)
    plt.close(fig)
    print(f"Wrote {output_dir / 'rq1_v2_overhead_comparison.png'}")

    # --- Graph 3: Staleness ---
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(x, [d["staleness_max"] for d in data], color=MODE_COLORS, edgecolor="black")
    ax.set_xticks(x); ax.set_xticklabels(modes)
    ax.set_ylabel("Max Staleness (s)")
    ax.set_title("RQ1 v2 — Max Information Age (Staleness) per Mode")
    for i, d in enumerate(data):
        ax.text(i, d["staleness_max"] + 0.2, f'{d["staleness_max"]:.1f}s', ha="center", fontweight="bold")
    plt.tight_layout()
    fig.savefig(output_dir / "rq1_v2_staleness_comparison.png", dpi=150)
    plt.close(fig)
    print(f"Wrote {output_dir / 'rq1_v2_staleness_comparison.png'}")

    # --- Graph 4: Timeout Rate ---
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(x, [d["timeout_mean"] for d in data], color=MODE_COLORS, edgecolor="black")
    ax.set_xticks(x); ax.set_xticklabels(modes)
    ax.set_ylabel("Timeout Rate (%)")
    ax.set_title("RQ1 v2 — Mean Timeout Rate per Mode")
    for i, d in enumerate(data):
        ax.text(i, d["timeout_mean"] + 0.5, f'{d["timeout_mean"]:.1f}%', ha="center", fontweight="bold")
    plt.tight_layout()
    fig.savefig(output_dir / "rq1_v2_timeout_comparison.png", dpi=150)
    plt.close(fig)
    print(f"Wrote {output_dir / 'rq1_v2_timeout_comparison.png'}")

    # --- Graph 5: Per-Phase Timeout ---
    fig, ax = plt.subplots(figsize=(14, 6))
    phase_x = np.arange(len(PHASE_ORDER))
    width = 0.2
    for i, (mode, d) in enumerate(zip(modes, data)):
        values = [d["per_phase"].get(ph, 0) for ph in PHASE_ORDER]
        ax.bar(phase_x + i * width, values, width, label=mode, color=MODE_COLORS[i], edgecolor="black")
    ax.set_xticks(phase_x + width * 1.5)
    ax.set_xticklabels([p.replace("_", "\n") for p in PHASE_ORDER], fontsize=8)
    ax.set_ylabel("Timeout Rate (%)")
    ax.set_title("RQ1 v2 — Per-Phase Timeout Rate by Mode")
    ax.legend()
    plt.tight_layout()
    fig.savefig(output_dir / "rq1_v2_per_phase_timeout.png", dpi=150)
    plt.close(fig)
    print(f"Wrote {output_dir / 'rq1_v2_per_phase_timeout.png'}")

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
