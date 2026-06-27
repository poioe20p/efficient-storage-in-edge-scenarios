"""cli_mechanism_compare — mechanism-necessity cross-run comparison.

Produces a single multi-panel PNG in the chosen output directory:
  - mechanism_compare.png

Panels (2 columns × 3 rows):
  Row 1: Avg latency by phase   | Failure rate by phase
  Row 2: Avg compute CPU%       | Avg storage CPU%
  Row 3: Avg compute RAM (MB)   | Avg storage RAM (MB)

Each panel is a grouped bar chart with one group per phase and one bar per run.
CPU and RAM values are computed from per_node_stats.csv (per-container data),
aggregated by role (compute = edge_server_*, storage = edge_storage_*) and
averaged across all containers of that role active in each phase.

Usage:
    python -m source.scripts.testing.analysis.cli_mechanism_compare \
        --run-dir <dir1> --run-dir <dir2> --run-dir <dir3> --run-dir <dir4> \
        [--output-dir <dir>]
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path


def _safe_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _summarize_node_rows_by_phase_role(
    node_rows: list[dict],
    phase_names: list[str],
) -> dict[str, dict[str, dict[str, float]]]:
    """Aggregate per-node CPU and RAM by phase and role.

    Returns:
        {phase_name: {role: {"cpu": avg_cpu_pct, "ram": avg_ram_mb}}}
    """
    buckets: dict[str, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for row in node_rows:
        phase = str(row.get("phase", ""))
        role = str(row.get("role", ""))
        if not phase or not role:
            continue
        buckets[phase][role].append(row)

    result: dict[str, dict[str, dict[str, float]]] = {}
    for phase in phase_names:
        result[phase] = {}
        for role in ("compute", "storage"):
            rows = buckets.get(phase, {}).get(role, [])
            cpu_vals = [_safe_float(r.get("cpu_percent")) for r in rows
                        if r.get("cpu_percent") not in ("", None)]
            ram_vals = [_safe_float(r.get("ram_used_mb")) for r in rows
                        if r.get("ram_used_mb") not in ("", None)]
            result[phase][role] = {
                "cpu": sum(cpu_vals) / len(cpu_vals) if cpu_vals else 0.0,
                "ram": sum(ram_vals) / len(ram_vals) if ram_vals else 0.0,
            }
    return result


def run(run_dirs: list[Path], output_dir: Path | None = None) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("[cli_mechanism_compare] matplotlib not installed — install via analysis/requirements.txt")
        return

    from .loader import load_run
    from .simple_metrics import summarize_client_rows_by_phase

    runs = [load_run(Path(run_dir)) for run_dir in run_dirs]
    if not runs:
        print("[cli_mechanism_compare] no run directories provided")
        return

    out_dir = Path(output_dir) if output_dir is not None else Path.cwd() / "mechanism_compare"
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Phase name ordering (union across all runs, in first-run order) ──
    phase_names: list[str] = []
    seen: set[str] = set()
    for run_data in runs:
        for phase in run_data.phases:
            if phase.name not in seen:
                phase_names.append(phase.name)
                seen.add(phase.name)

    # ── Per-phase client-request summaries (latency, failure) ────────────
    phase_summaries: list[dict] = []
    for run_data in runs:
        ph = {
            row["phase"]: row
            for row in summarize_client_rows_by_phase(run_data.all_client_rows, phase_names)
        }
        phase_summaries.append(ph)

    # ── Per-phase per-role CPU/RAM summaries ─────────────────────────────
    node_summaries: list[dict] = []
    for run_data in runs:
        node_summaries.append(
            _summarize_node_rows_by_phase_role(run_data.node_rows, phase_names)
        )

    run_names = [r.run_dir.name for r in runs]
    run_count = len(runs)

    # ── Plot ────────────────────────────────────────────────────────────
    fig, axes = plt.subplots(3, 2, figsize=(22, 18))
    fig.suptitle("Mechanism Necessity — cross-run comparison", fontsize=14, fontweight="bold")

    x = np.arange(len(phase_names))
    bar_width = max(0.08, 0.7 / max(run_count, 1))

    # Colour palette — consistent across panels
    palette = ["#1a7abf", "#bf5a1a", "#1abf4a", "#8b1a8b"][:run_count]

    # ── Row 1, Col 0: Avg latency by phase ──────────────────────────────
    ax = axes[0][0]
    for i, (ph, name, color) in enumerate(zip(phase_summaries, run_names, palette)):
        offset = (i - (run_count - 1) / 2.0) * bar_width
        values = [ph.get(p, {}).get("avg_latency_ms", 0.0) for p in phase_names]
        ax.bar(x + offset, values, bar_width, label=name, color=color, alpha=0.85)
    ax.set_ylabel("ms")
    ax.set_title("Average latency by phase")
    ax.set_xticks(x)
    ax.set_xticklabels(phase_names, rotation=30, ha="right", fontsize=8)
    ax.legend(fontsize=7)
    ax.grid(axis="y", alpha=0.3)

    # ── Row 1, Col 1: Failure rate by phase ─────────────────────────────
    ax = axes[0][1]
    for i, (ph, name, color) in enumerate(zip(phase_summaries, run_names, palette)):
        offset = (i - (run_count - 1) / 2.0) * bar_width
        values = [ph.get(p, {}).get("failure_rate_pct", 0.0) for p in phase_names]
        ax.bar(x + offset, values, bar_width, label=name, color=color, alpha=0.85)
    ax.set_ylabel("%")
    ax.set_title("Failure rate by phase")
    ax.set_xticks(x)
    ax.set_xticklabels(phase_names, rotation=30, ha="right", fontsize=8)
    ax.legend(fontsize=7)
    ax.grid(axis="y", alpha=0.3)

    # ── Row 2, Col 0: Avg compute CPU% by phase ─────────────────────────
    ax = axes[1][0]
    for i, (ns, name, color) in enumerate(zip(node_summaries, run_names, palette)):
        offset = (i - (run_count - 1) / 2.0) * bar_width
        values = [ns.get(p, {}).get("compute", {}).get("cpu", 0.0) for p in phase_names]
        ax.bar(x + offset, values, bar_width, label=name, color=color, alpha=0.85)
    ax.set_ylabel("CPU %")
    ax.set_title("Average compute CPU% by phase")
    ax.set_xticks(x)
    ax.set_xticklabels(phase_names, rotation=30, ha="right", fontsize=8)
    ax.legend(fontsize=7)
    ax.grid(axis="y", alpha=0.3)

    # ── Row 2, Col 1: Avg storage CPU% by phase ─────────────────────────
    ax = axes[1][1]
    for i, (ns, name, color) in enumerate(zip(node_summaries, run_names, palette)):
        offset = (i - (run_count - 1) / 2.0) * bar_width
        values = [ns.get(p, {}).get("storage", {}).get("cpu", 0.0) for p in phase_names]
        ax.bar(x + offset, values, bar_width, label=name, color=color, alpha=0.85)
    ax.set_ylabel("CPU %")
    ax.set_title("Average storage CPU% by phase")
    ax.set_xticks(x)
    ax.set_xticklabels(phase_names, rotation=30, ha="right", fontsize=8)
    ax.legend(fontsize=7)
    ax.grid(axis="y", alpha=0.3)

    # ── Row 3, Col 0: Avg compute RAM (MB) by phase ─────────────────────
    ax = axes[2][0]
    for i, (ns, name, color) in enumerate(zip(node_summaries, run_names, palette)):
        offset = (i - (run_count - 1) / 2.0) * bar_width
        values = [ns.get(p, {}).get("compute", {}).get("ram", 0.0) for p in phase_names]
        ax.bar(x + offset, values, bar_width, label=name, color=color, alpha=0.85)
    ax.set_ylabel("MB")
    ax.set_title("Average compute RAM (MB) by phase")
    ax.set_xticks(x)
    ax.set_xticklabels(phase_names, rotation=30, ha="right", fontsize=8)
    ax.legend(fontsize=7)
    ax.grid(axis="y", alpha=0.3)

    # ── Row 3, Col 1: Avg storage RAM (MB) by phase ─────────────────────
    ax = axes[2][1]
    for i, (ns, name, color) in enumerate(zip(node_summaries, run_names, palette)):
        offset = (i - (run_count - 1) / 2.0) * bar_width
        values = [ns.get(p, {}).get("storage", {}).get("ram", 0.0) for p in phase_names]
        ax.bar(x + offset, values, bar_width, label=name, color=color, alpha=0.85)
    ax.set_ylabel("MB")
    ax.set_title("Average storage RAM (MB) by phase")
    ax.set_xticks(x)
    ax.set_xticklabels(phase_names, rotation=30, ha="right", fontsize=8)
    ax.legend(fontsize=7)
    ax.grid(axis="y", alpha=0.3)

    plt.tight_layout()
    out_path = out_dir / "mechanism_compare.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"[cli_mechanism_compare] wrote {out_path}")

    # ── Text summary ────────────────────────────────────────────────────
    _write_summary(out_dir / "mechanism_compare.md", run_names, phase_names,
                   phase_summaries, node_summaries)


def _write_summary(
    summary_path: Path,
    run_names: list[str],
    phase_names: list[str],
    phase_summaries: list[dict],
    node_summaries: list[dict],
) -> None:
    with summary_path.open("w", encoding="utf-8") as f:
        f.write("# Mechanism Necessity — Cross-Run Comparison\n\n")
        f.write("See `mechanism_compare.png` for the full chart.\n\n")

        f.write("## Per-Phase Latency & Failure\n\n")
        f.write("| Phase | " + " | ".join(f"{name} lat" for name in run_names))
        f.write(" | " + " | ".join(f"{name} fail%" for name in run_names) + " |\n")
        f.write("|-------|" + "|".join(["---" for _ in range(len(run_names) * 2)]) + "|\n")
        for p in phase_names:
            lat_vals = [f"{ps.get(p, {}).get('avg_latency_ms', 0):.0f} ms" for ps in phase_summaries]
            fail_vals = [f"{ps.get(p, {}).get('failure_rate_pct', 0):.1f}%" for ps in phase_summaries]
            f.write(f"| {p} | " + " | ".join(lat_vals) + " | " + " | ".join(fail_vals) + " |\n")

        f.write("\n## Per-Phase Compute CPU% & RAM\n\n")
        f.write("| Phase | " + " | ".join(f"{name} CPU%" for name in run_names))
        f.write(" | " + " | ".join(f"{name} RAM" for name in run_names) + " |\n")
        f.write("|-------|" + "|".join(["---" for _ in range(len(run_names) * 2)]) + "|\n")
        for p in phase_names:
            cpu_vals = [f"{ns.get(p, {}).get('compute', {}).get('cpu', 0):.1f}%" for ns in node_summaries]
            ram_vals = [f"{ns.get(p, {}).get('compute', {}).get('ram', 0):.0f} MB" for ns in node_summaries]
            f.write(f"| {p} | " + " | ".join(cpu_vals) + " | " + " | ".join(ram_vals) + " |\n")

        f.write("\n## Per-Phase Storage CPU% & RAM\n\n")
        f.write("| Phase | " + " | ".join(f"{name} CPU%" for name in run_names))
        f.write(" | " + " | ".join(f"{name} RAM" for name in run_names) + " |\n")
        f.write("|-------|" + "|".join(["---" for _ in range(len(run_names) * 2)]) + "|\n")
        for p in phase_names:
            cpu_vals = [f"{ns.get(p, {}).get('storage', {}).get('cpu', 0):.1f}%" for ns in node_summaries]
            ram_vals = [f"{ns.get(p, {}).get('storage', {}).get('ram', 0):.0f} MB" for ns in node_summaries]
            f.write(f"| {p} | " + " | ".join(cpu_vals) + " | " + " | ".join(ram_vals) + " |\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", action="append", required=True, metavar="DIR")
    parser.add_argument("--output-dir", metavar="DIR")
    args = parser.parse_args()
    out_dir = Path(args.output_dir) if args.output_dir else None
    run([Path(run_dir) for run_dir in args.run_dir], out_dir)


if __name__ == "__main__":
    main()
