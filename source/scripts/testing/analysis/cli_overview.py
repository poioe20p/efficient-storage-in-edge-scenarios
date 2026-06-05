"""cli_overview — one-page dashboard for a run directory.

Produces <run_dir>/analysis/overview.png with stacked time-series panels:
  - request rate (from client CSV, concatenated across phases)
  - compute CPU (domain median + per-node thin lines)
  - storage CPU (domain median + per-node thin lines)
  - T_proc
  - T_db (total, read, write)
  - node counts (compute, storage)

Usage:
    python -m source.scripts.testing.analysis.cli_overview --run-dir <dir>
"""
from __future__ import annotations

import argparse
import os
import warnings
from pathlib import Path


def _safe_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _col(row: dict, *names: str, default=0.0):
    """Return the first available column value from *names* (backward compat)."""
    for name in names:
        val = row.get(name)
        if val is not None and str(val).strip() != "":
            return _safe_float(val, default)
    return default


def run(run_dir: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[cli_overview] matplotlib not installed — install via analysis/requirements.txt")
        return

    from .loader import load_run
    from .phase_window import phase_boundaries
    from .plots import shade_phases, overlay_events

    r = load_run(run_dir)
    out_dir = run_dir / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)

    bounds = phase_boundaries(r.t0, r.phases)
    t_domain = [_safe_float(row["window_end"]) - r.t0 for row in r.domain_rows]

    has_db_decomp = (
        any(row.get("avg_time_db_read_ms") for row in r.domain_rows)
        or any(row.get("avg_time_db_read_ms") for row in r.debug_rows)
    )
    # Prefer debug_rows for decomposed DB fields when domain_rows doesn't have them
    _db_rows = r.debug_rows if r.debug_rows and not any(
        row.get("avg_time_db_read_ms") for row in r.domain_rows
    ) else r.domain_rows
    has_nodes = bool(r.node_rows)

    n_panels = 6
    fig, axes = plt.subplots(n_panels, 1, figsize=(14, 3 * n_panels), sharex=True)
    fig.suptitle(f"Run overview — {run_dir.name}", fontsize=12)

    # ── Panel 0: request rate ────────────────────────────────────────────────
    ax = axes[0]
    req = [_safe_float(row.get("total_requests", 0)) for row in r.domain_rows]
    ax.plot(t_domain, req, color="#1a7abf")
    ax.set_ylabel("requests / window")
    ax.set_title("Request rate")
    shade_phases(ax, bounds, r.t0)
    overlay_events(ax, r.events, r.t0)

    # ── Panel 1: compute CPU ─────────────────────────────────────────────────
    ax = axes[1]
    cpu = [_col(row, "average_cpu_percent", "median_cpu_percent") for row in r.domain_rows]
    ax.plot(t_domain, cpu, color="#1a7abf", linewidth=1.5, label="avg")
    if has_nodes:
        for sid in {row["server_id"] for row in r.node_rows if row.get("role") == "compute"}:
            nrows = [row for row in r.node_rows
                     if row.get("role") == "compute" and row["server_id"] == sid]
            nt = [_safe_float(row["window_end"]) - r.t0 for row in nrows]
            nc = [_safe_float(row.get("cpu_percent")) for row in nrows]
            ax.plot(nt, nc, color="#aac8e0", linewidth=0.5, alpha=0.6)
    ax.set_ylabel("CPU %")
    ax.set_title("Compute CPU")
    shade_phases(ax, bounds, r.t0)
    overlay_events(ax, r.events, r.t0, tier="compute")

    # ── Panel 2: storage CPU ─────────────────────────────────────────────────
    ax = axes[2]
    stcpu = [_col(row, "avg_storage_cpu_percent", "median_storage_cpu_percent") for row in r.domain_rows]
    ax.plot(t_domain, stcpu, color="#bf5a1a", linewidth=1.5, label="avg")
    if has_nodes:
        for sid in {row["server_id"] for row in r.node_rows if row.get("role") == "storage"}:
            nrows = [row for row in r.node_rows
                     if row.get("role") == "storage" and row["server_id"] == sid]
            nt = [_safe_float(row["window_end"]) - r.t0 for row in nrows]
            nc = [_safe_float(row.get("cpu_percent")) for row in nrows]
            ax.plot(nt, nc, color="#e0b89a", linewidth=0.5, alpha=0.6)
    ax.set_ylabel("CPU %")
    ax.set_title("Storage CPU")
    shade_phases(ax, bounds, r.t0)
    overlay_events(ax, r.events, r.t0, tier="storage")

    # ── Panel 3: T_proc ──────────────────────────────────────────────────────
    ax = axes[3]
    tproc = [_col(row, "avg_time_proc_ms", "median_time_proc_ms") for row in r.domain_rows]
    ax.plot(t_domain, tproc, color="#1abf4a")
    ax.set_ylabel("ms")
    ax.set_title("T_proc (median)")
    shade_phases(ax, bounds, r.t0)

    # ── Panel 4: T_db ────────────────────────────────────────────────────────
    ax = axes[4]
    tdb = [_col(row, "avg_time_db_ms", "median_time_db_ms") for row in r.domain_rows]
    ax.plot(t_domain, tdb, color="#bf1a8c", linewidth=1.5, label="T_db total")
    if has_db_decomp:
        tr = [_safe_float(row.get("avg_time_db_read_ms")) for row in _db_rows]
        tw = [_safe_float(row.get("avg_time_db_write_ms")) for row in _db_rows]
        ax.fill_between(t_domain, 0, tr, alpha=0.3, color="#1a7abf", label="read")
        ax.fill_between(t_domain, tr, [a + b for a, b in zip(tr, tw)],
                        alpha=0.3, color="#bf5a1a", label="write")
    else:
        warnings.warn("avg_time_db_read/write_ms columns missing — T_db decomposition skipped.")
    ax.set_ylabel("ms")
    ax.set_title("T_db")
    ax.legend(fontsize=7)
    shade_phases(ax, bounds, r.t0)

    # ── Panel 5: node counts ─────────────────────────────────────────────────
    ax = axes[5]
    nc = [_safe_float(row.get("server_count", 0)) for row in r.domain_rows]
    ns = [_safe_float(row.get("storage_count", 0)) for row in r.domain_rows]
    ax.plot(t_domain, nc, color="#1a7abf", label="compute")
    ax.plot(t_domain, ns, color="#bf5a1a", label="storage")
    ax.set_ylabel("nodes")
    ax.set_xlabel("time (s)")
    ax.set_title("Node counts")
    ax.legend(fontsize=7)
    shade_phases(ax, bounds, r.t0)
    overlay_events(ax, r.events, r.t0)

    plt.tight_layout()
    out_path = out_dir / "overview.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    print(f"[cli_overview] wrote {out_path}")

    _append_summary(out_dir / "summary.md", run_dir)


def _append_summary(summary_path: Path, run_dir: Path) -> None:
    with summary_path.open("a", encoding="utf-8") as f:
        f.write(f"\n## Overview\n\nSee `analysis/overview.png` — "
                f"generated from `{run_dir.name}`.\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, metavar="DIR")
    args = parser.parse_args()
    run(Path(args.run_dir))


if __name__ == "__main__":
    main()
