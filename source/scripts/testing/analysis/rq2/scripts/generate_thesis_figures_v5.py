"""Thesis figures for the RQ2 v5 scaling-action campaign.

Reads the cell-level summary produced by ``analysis/rq2v5_cell_stats.py``
(``rq2v5_cell_stats.csv``) and writes the three figures used by the RQ2
results section:

1. ``rq2_mixed_press.png`` -- mixed press: request-path components and
   completion by scaling policy.
2. ``rq2_data_press.png`` -- data-access press: same panels, components on a
   logarithmic axis.
3. ``rq2_storage_relief_v3.png`` -- storage tier utilisation and members
   serving the episode, both presses.

The superseded ``rq2v5_stor_db_43`` run (edge OOM at press onset, replaced by
``rq2v5_stor_db_43_r1``) is excluded from every panel.

Usage (from the repo root):

    python source/scripts/testing/analysis/rq2/scripts/generate_thesis_figures_v5.py \
        --cells docs/operation/testing/experiment/v5/rq2/rq2v5_cell_stats.csv \
        --outdir tese/images
"""

from __future__ import annotations

import argparse
import csv
import statistics as st
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

MODES = ["none", "comp", "stor", "both"]
LABELS = {
    "none": "no scaling",
    "comp": "compute-only",
    "stor": "storage-only",
    "both": "bottleneck-aware",
}
EXCLUDED = {"rq2v5_stor_db_43"}

COL_PROC = "#4472C4"
COL_DB = "#ED7D31"
COL_MIXED = "#8E24AA"
COL_DATA = "#00897B"
GREY = "#333333"

plt.rcParams.update(
    {
        "font.size": 10,
        "axes.labelsize": 10,
        "legend.fontsize": 9,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "figure.dpi": 150,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)


def _f(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def load_runs(path: Path) -> dict[tuple[str, str], list[dict]]:
    runs: dict[tuple[str, str], list[dict]] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["label"] in EXCLUDED:
                continue
            lanes = {}
            for key in (
                "t_db_ms",
                "t_proc_ms",
                "completion_pct",
                "sto_cpu",
                "members",
            ):
                a, b = _f(row[f"lan1_{key}"]), _f(row[f"lan2_{key}"])
                if a is None or b is None:
                    raise ValueError(f"missing {key} in {row['label']}")
                lanes[key] = (a + b) / 2
            runs.setdefault((row["regime"], row["mode"]), []).append(lanes)
    return runs


def _stats(values: list[float]) -> tuple[float, float, float]:
    return st.median(values), min(values), max(values)


def _draw_grouped(
    ax,
    runs: dict,
    regime: str,
    key: str,
    colour: str,
    label: str,
    offset: float,
    width: float,
    log: bool = False,
) -> None:
    xs = np.arange(len(MODES)) + offset
    medians, lows, highs, dots_x, dots_y = [], [], [], [], []
    for i, mode in enumerate(MODES):
        med, low, high = _stats([r[key] for r in runs[(regime, mode)]])
        medians.append(med)
        lows.append(med - low)
        highs.append(high - med)
        for j, value in enumerate([r[key] for r in runs[(regime, mode)]]):
            dots_x.append(i + offset + (j - 3) * width / 9)
            dots_y.append(value)
    ax.bar(
        xs,
        medians,
        width,
        color=colour,
        alpha=0.85,
        edgecolor="white",
        label=label,
        zorder=2,
    )
    ax.errorbar(
        xs,
        medians,
        yerr=[lows, highs],
        fmt="none",
        ecolor=GREY,
        capsize=3,
        linewidth=1,
        zorder=3,
    )
    ax.scatter(dots_x, dots_y, s=14, color=GREY, alpha=0.75, zorder=4, linewidths=0)
    if log:
        ax.set_yscale("log")


def _finish_axes(ax, title: str, ylabel: str) -> None:
    ax.set_xticks(np.arange(len(MODES)))
    ax.set_xticklabels(
        [LABELS[m] for m in MODES],
        rotation=18,
        ha="right",
        rotation_mode="anchor",
    )
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", color="#E0E0E0", linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    ax.set_title(title, loc="left", fontsize=10, fontweight="bold")


def fig_press(runs: dict, regime: str, out: Path, log: bool) -> None:
    fig, (left, right) = plt.subplots(1, 2, figsize=(8.2, 3.6))

    width = 0.36
    _draw_grouped(left, runs, regime, "t_proc_ms", COL_PROC, "Processing", -width / 2, width)
    _draw_grouped(left, runs, regime, "t_db_ms", COL_DB, "Data access", width / 2, width, log=log)
    _finish_axes(
        left,
        "(a) Request-path components",
        "Component latency (ms, log scale)" if log else "Component latency (ms)",
    )
    left.legend(frameon=False, loc="upper right")

    _draw_grouped(right, runs, regime, "completion_pct", "#607D8B", "Completion", 0.0, 0.5)
    _finish_axes(right, "(b) Completion", "Completed requests (%)")
    right.set_ylim(0, 105)

    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def fig_relief(runs: dict, out: Path) -> None:
    fig, (left, right) = plt.subplots(1, 2, figsize=(8.2, 3.6))
    width = 0.38
    xs = np.arange(len(MODES))

    for offset, regime, colour, label in (
        (-width / 2, "mx", COL_MIXED, "Mixed press"),
        (width / 2, "db", COL_DATA, "Data-access press"),
    ):
        medians, lows, highs, dots_x, dots_y = [], [], [], [], []
        for i, mode in enumerate(MODES):
            values = [r["sto_cpu"] for r in runs[(regime, mode)]]
            med, low, high = _stats(values)
            medians.append(med)
            lows.append(med - low)
            highs.append(high - med)
            for j, value in enumerate(values):
                dots_x.append(i + offset + (j - 3) * width / 10)
                dots_y.append(value)
        left.bar(
            xs + offset,
            medians,
            width,
            color=colour,
            alpha=0.85,
            edgecolor="white",
            label=label,
            zorder=2,
        )
        left.errorbar(
            xs + offset,
            medians,
            yerr=[lows, highs],
            fmt="none",
            ecolor=GREY,
            capsize=3,
            linewidth=1,
            zorder=3,
        )
        left.scatter(dots_x, dots_y, s=14, color=GREY, alpha=0.75, zorder=4, linewidths=0)

        medians, lows, highs, dots_x, dots_y = [], [], [], [], []
        for i, mode in enumerate(MODES):
            values = [r["members"] for r in runs[(regime, mode)]]
            med, low, high = _stats(values)
            medians.append(med)
            lows.append(med - low)
            highs.append(high - med)
            for j, value in enumerate(values):
                dots_x.append(i + offset + (j - 3) * width / 10)
                dots_y.append(value)
        right.bar(
            xs + offset,
            medians,
            width,
            color=colour,
            alpha=0.85,
            edgecolor="white",
            label=label,
            zorder=2,
        )
        right.errorbar(
            xs + offset,
            medians,
            yerr=[lows, highs],
            fmt="none",
            ecolor=GREY,
            capsize=3,
            linewidth=1,
            zorder=3,
        )
        right.scatter(dots_x, dots_y, s=14, color=GREY, alpha=0.75, zorder=4, linewidths=0)

    _finish_axes(left, "(a) Storage tier utilisation", "Storage tier CPU (%)")
    left.legend(frameon=False, loc="upper right")
    _finish_axes(right, "(b) Members serving the episode", "Members")
    right.set_ylim(0, 6)

    fig.tight_layout()
    fig.savefig(out)
    plt.close(fig)


def report(runs: dict) -> None:
    for regime in ("mx", "db"):
        for mode in MODES:
            rows = runs[(regime, mode)]
            proc = _stats([r["t_proc_ms"] for r in rows])
            db = _stats([r["t_db_ms"] for r in rows])
            comp = _stats([r["completion_pct"] for r in rows])
            cpu = st.median([r["sto_cpu"] for r in rows])
            mem = st.median([r["members"] for r in rows])
            print(
                f"{regime:>3} {mode:<5} n={len(rows)} "
                f"proc={proc[0]:.0f} ({proc[1]:.0f}-{proc[2]:.0f}) "
                f"db={db[0]:.0f} ({db[1]:.0f}-{db[2]:.0f}) "
                f"completion={comp[0]:.1f} ({comp[1]:.1f}-{comp[2]:.1f}) "
                f"storage_cpu={cpu:.0f} members={mem:.1f}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cells",
        default="docs/operation/testing/experiment/v5/rq2/rq2v5_cell_stats.csv",
    )
    parser.add_argument("--outdir", default="tese/images")
    args = parser.parse_args()

    runs = load_runs(Path(args.cells))
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    fig_press(runs, "mx", outdir / "rq2_mixed_press.png", log=False)
    fig_press(runs, "db", outdir / "rq2_data_press.png", log=True)
    fig_relief(runs, outdir / "rq2_storage_relief_v3.png")
    report(runs)
    print(f"wrote 3 figures to {outdir}")


if __name__ == "__main__":
    main()
