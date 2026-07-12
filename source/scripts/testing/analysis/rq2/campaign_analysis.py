#!/usr/bin/env python3
"""RQ2 campaign aggregation and graph generation.

Aggregates per-run rq2_redistribution_*.csv across all 9 runs,
then generates the 5 graphs specified in the experiment plan.
"""
from __future__ import annotations

import csv
import os
import sys
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

METRICS_DIR = Path("/home/testop/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics")
OUT_DIR = Path("/home/testop/efficient-storage-in-edge-scenarios/source/scripts/testing/metrics/_rq2_campaign_analysis")
GRAPHS_DIR = Path("/home/testop/efficient-storage-in-edge-scenarios/docs/operation/testing/experiment/rq2_evaluation/graphs/20260706_campaign")

RUNS = [
    ("20260706_171835_rq2_th_1", "topology_host"),
    ("20260706_181823_rq2_th_2", "topology_host"),
    ("20260706_190002_rq2_th_3", "topology_host"),
    ("20260706_194238_rq2_ss_1", "topology_slowstart"),
    ("20260706_202401_rq2_ss_2", "topology_slowstart"),
    ("20260706_210552_rq2_ss_3", "topology_slowstart"),
    ("20260706_214625_rq2_tl_1", "topology_lifecycle"),
    ("20260706_222823_rq2_tl_2", "topology_lifecycle"),
    ("20260706_231045_rq2_tl_3", "topology_lifecycle"),
]

MODE_LABELS = {
    "topology_host": "Host\n(no ramp)",
    "topology_slowstart": "Slowstart\n(discovery delay)",
    "topology_lifecycle": "Lifecycle\n(warm lease)",
}
MODE_COLORS = {
    "topology_host": "#e74c3c",
    "topology_slowstart": "#f39c12",
    "topology_lifecycle": "#27ae60",
}
MODE_ORDER = ["topology_host", "topology_slowstart", "topology_lifecycle"]


def read_csv(path: Path) -> list[dict]:
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    GRAPHS_DIR.mkdir(parents=True, exist_ok=True)

    # ── Aggregate profiles ──────────────────────────────────────────
    all_profiles = []
    for run_dir, mode in RUNS:
        p = METRICS_DIR / run_dir / "analysis" / "rq2_redistribution_profile.csv"
        if p.exists():
            for row in read_csv(p):
                row["run"] = run_dir
                all_profiles.append(row)

    # ── Aggregate summaries ─────────────────────────────────────────
    all_summaries = []
    for run_dir, mode in RUNS:
        p = METRICS_DIR / run_dir / "analysis" / "rq2_redistribution_summary.csv"
        if p.exists():
            for row in read_csv(p):
                row["run"] = run_dir
                all_summaries.append(row)

    # ── Aggregate transition quality ────────────────────────────────
    all_quality = []
    for run_dir, mode in RUNS:
        p = METRICS_DIR / run_dir / "analysis" / "rq2_transition_quality.csv"
        if p.exists():
            for row in read_csv(p):
                row["run"] = run_dir
                row["mode"] = mode
                all_quality.append(row)

    # ── Aggregate cumulative load ───────────────────────────────────
    all_cumulative = []
    for run_dir, mode in RUNS:
        p = METRICS_DIR / run_dir / "analysis" / "rq2_cumulative_load.csv"
        if p.exists():
            for row in read_csv(p):
                row["run"] = run_dir
                row["mode"] = mode
                all_cumulative.append(row)

    print(f"Profiles: {len(all_profiles)} rows")
    print(f"Summaries: {len(all_summaries)} events")
    print(f"Quality: {len(all_quality)} rows")
    print(f"Cumulative: {len(all_cumulative)} rows")

    # ── Event counts per mode ───────────────────────────────────────
    event_counts = defaultdict(int)
    for s in all_summaries:
        event_counts[s["mode"]] += 1
    print(f"Events per mode: {dict(event_counts)}")

    # ═════════════════════════════════════════════════════════════════
    # GRAPH 1: Redistribution Profile — load share vs time per mode
    # ═════════════════════════════════════════════════════════════════
    fig, ax = plt.subplots(figsize=(10, 6))
    for mode in MODE_ORDER:
        mode_rows = [r for r in all_profiles if r["mode"] == mode]
        if not mode_rows:
            continue
        times = sorted(set(float(r["time_since_spawn_s"]) for r in mode_rows))
        means = []
        for t in times:
            t_rows = [r for r in mode_rows if float(r["time_since_spawn_s"]) == t]
            n_total = sum(int(r["n_events"]) for r in t_rows)
            weighted = sum(float(r["mean_share"]) * int(r["n_events"]) for r in t_rows) / max(n_total, 1)
            means.append(weighted)
        ax.plot(times, means, "o-", color=MODE_COLORS[mode],
                label=MODE_LABELS[mode], linewidth=2, markersize=8)

    ax.set_xlabel("Time since spawn (s)", fontsize=12)
    ax.set_ylabel("Mean load share", fontsize=12)
    ax.set_title("Graph 1: Load Share vs Time Since Spawn (per mode, compute tier)", fontsize=13)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    ax.set_ylim(0, 1)
    fig.tight_layout()
    fig.savefig(GRAPHS_DIR / "graph1_redistribution_profile.png", dpi=150)
    plt.close(fig)
    print("✓ Graph 1 saved")

    # ═════════════════════════════════════════════════════════════════
    # GRAPH 2: Redistribution Summary — per-event redistribution times
    # ═════════════════════════════════════════════════════════════════
    fig, ax = plt.subplots(figsize=(10, 6))
    redistribution_data = {}
    for mode in MODE_ORDER:
        times = []
        for s in all_summaries:
            if s["mode"] == mode and s["redistribution_s"]:
                try:
                    times.append(float(s["redistribution_s"]))
                except ValueError:
                    pass
        redistribution_data[mode] = times

    if any(redistribution_data.values()):
        positions = list(range(len(MODE_ORDER)))
        bp = ax.boxplot([redistribution_data[m] for m in MODE_ORDER],
                         positions=positions, widths=0.5, patch_artist=True)
        for i, mode in enumerate(MODE_ORDER):
            bp["boxes"][i].set_facecolor(MODE_COLORS[mode])
            n = len(redistribution_data[mode])
            ax.annotate(f"n={n}", (positions[i], 0), ha="center", va="bottom", fontsize=8,
                        xytext=(0, -15), textcoords="offset points")
        ax.set_xticklabels([MODE_LABELS[m] for m in MODE_ORDER])
        ax.set_ylabel("Redistribution time (s)", fontsize=12)
        ax.set_title("Graph 2: Per-Event Redistribution Time (compute tier)", fontsize=13)
        ax.grid(True, alpha=0.3, axis="y")
    else:
        ax.text(0.5, 0.5, "No events reached equilibrium\n(redistribution time not measurable)",
                ha="center", va="center", fontsize=14, transform=ax.transAxes)
        ax.set_title("Graph 2: Redistribution Time — NOT MEASURABLE", fontsize=13)

    fig.tight_layout()
    fig.savefig(GRAPHS_DIR / "graph2_redistribution_summary.png", dpi=150)
    plt.close(fig)
    print("✓ Graph 2 saved")

    # ═════════════════════════════════════════════════════════════════
    # GRAPH 3: Transition Quality — p95 latency & failure rate per mode
    # ═════════════════════════════════════════════════════════════════
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    mode_latency = {}
    mode_failure = {}
    for mode in MODE_ORDER:
        m_rows = [r for r in all_quality if r["mode"] == mode]
        mode_latency[mode] = [float(r["p95_latency_ms"]) for r in m_rows if r.get("p95_latency_ms")]
        mode_failure[mode] = [float(r["failure_rate_pct"]) for r in m_rows if r.get("failure_rate_pct")]

    x = np.arange(len(MODE_ORDER))
    width = 0.35

    lat_means = [np.mean(mode_latency[m]) if mode_latency[m] else 0 for m in MODE_ORDER]
    fail_means = [np.mean(mode_failure[m]) if mode_failure[m] else 0 for m in MODE_ORDER]

    bars1 = ax1.bar(x, lat_means, width, color=[MODE_COLORS[m] for m in MODE_ORDER])
    ax1.set_xticks(x)
    ax1.set_xticklabels([MODE_LABELS[m] for m in MODE_ORDER])
    ax1.set_ylabel("p95 Latency (ms)", fontsize=12)
    ax1.set_title("p95 Latency", fontsize=12)
    ax1.grid(True, alpha=0.3, axis="y")

    bars2 = ax2.bar(x, fail_means, width, color=[MODE_COLORS[m] for m in MODE_ORDER])
    ax2.set_xticks(x)
    ax2.set_xticklabels([MODE_LABELS[m] for m in MODE_ORDER])
    ax2.set_ylabel("Failure Rate (%)", fontsize=12)
    ax2.set_title("Failure Rate", fontsize=12)
    ax2.grid(True, alpha=0.3, axis="y")

    fig.suptitle("Graph 3: Transition Quality — Per-Mode p95 Latency & Failure Rate", fontsize=13)
    fig.tight_layout()
    fig.savefig(GRAPHS_DIR / "graph3_transition_quality.png", dpi=150)
    plt.close(fig)
    print("✓ Graph 3 saved")

    # ═════════════════════════════════════════════════════════════════
    # GRAPH 4: Cumulative Load over time per mode
    # ═════════════════════════════════════════════════════════════════
    fig, ax = plt.subplots(figsize=(10, 6))
    for mode in MODE_ORDER:
        mode_rows = [r for r in all_cumulative if r["mode"] == mode]
        if not mode_rows:
            continue
        times = sorted(set(float(r["time_since_spawn_s"]) for r in mode_rows))
        loads = []
        for t in times:
            t_rows = [r for r in mode_rows if float(r["time_since_spawn_s"]) == t]
            n_total = sum(int(r["n_events"]) for r in t_rows)
            weighted = sum(float(r["mean_cumulative_load"]) * int(r["n_events"]) for r in t_rows) / max(n_total, 1)
            loads.append(weighted)
        ax.plot(times, loads, "s-", color=MODE_COLORS[mode],
                label=MODE_LABELS[mode], linewidth=2, markersize=8)

    ax.set_xlabel("Time since spawn (s)", fontsize=12)
    ax.set_ylabel("Mean cumulative requests served", fontsize=12)
    ax.set_title("Graph 4: Cumulative Load Over Time (per mode, compute tier)", fontsize=13)
    ax.legend(fontsize=10)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(GRAPHS_DIR / "graph4_cumulative_load.png", dpi=150)
    plt.close(fig)
    print("✓ Graph 4 saved")

    # ═════════════════════════════════════════════════════════════════
    # GRAPH 5: Coordination Gap — slowstart_median − lifecycle_median
    # ═════════════════════════════════════════════════════════════════
    fig, ax = plt.subplots(figsize=(8, 5))
    ss_times = redistribution_data.get("topology_slowstart", [])
    tl_times = redistribution_data.get("topology_lifecycle", [])
    host_times = redistribution_data.get("topology_host", [])

    if ss_times and tl_times:
        gap = np.median(ss_times) - np.median(tl_times)
        roles = ["compute"]
        gaps = [gap]
        colors = ["#3498db" if gap >= 0 else "#e74c3c"]
        ax.bar(roles, gaps, color=colors)
        ax.axhline(y=0, color="black", linewidth=0.8)
        ax.set_ylabel("Redistribution time gap (s)", fontsize=12)
        ax.set_title(f"Graph 5: Coordination Gap\nslowstart − lifecycle = {gap:.1f}s (compute tier)", fontsize=13)
        ax.grid(True, alpha=0.3, axis="y")
    else:
        ax.text(0.5, 0.5,
                "Coordination gap not measurable\n(no events reached equilibrium in either mode)",
                ha="center", va="center", fontsize=14, transform=ax.transAxes)
        ax.set_title("Graph 5: Coordination Gap — NOT MEASURABLE", fontsize=13)

    fig.tight_layout()
    fig.savefig(GRAPHS_DIR / "graph5_coordination_gap.png", dpi=150)
    plt.close(fig)
    print("✓ Graph 5 saved")

    # ── Write aggregated CSV ────────────────────────────────────────
    # Per-mode summary table
    mode_summary = []
    for mode in MODE_ORDER:
        m_summaries = [s for s in all_summaries if s["mode"] == mode]
        m_quality = [r for r in all_quality if r.get("mode") == mode]
        n_events = len(m_summaries)
        n_equil = sum(1 for s in m_summaries if s.get("redistribution_s"))
        rt_vals = [float(s["redistribution_s"]) for s in m_summaries if s.get("redistribution_s")]
        lat_vals = [float(r["p95_latency_ms"]) for r in m_quality if r.get("p95_latency_ms")]
        fail_vals = [float(r["failure_rate_pct"]) for r in m_quality if r.get("failure_rate_pct")]
        mean_load = None
        m_profiles = [r for r in all_profiles if r["mode"] == mode]
        if m_profiles:
            loads = [float(r["mean_share"]) for r in m_profiles]
            mean_load = np.mean(loads)

        mode_summary.append({
            "mode": mode,
            "n_runs": 3,
            "n_events_total": n_events,
            "n_events_equil": n_equil,
            "redist_median_s": f"{np.median(rt_vals):.1f}" if rt_vals else "N/A",
            "redist_p95_s": f"{np.percentile(rt_vals, 95):.1f}" if rt_vals else "N/A",
            "p95_latency_ms": f"{np.mean(lat_vals):.1f}" if lat_vals else "N/A",
            "failure_rate_pct": f"{np.mean(fail_vals):.2f}" if fail_vals else "N/A",
            "mean_initial_share": f"{mean_load:.3f}" if mean_load is not None else "N/A",
        })

    with open(OUT_DIR / "campaign_summary.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=mode_summary[0].keys())
        w.writeheader()
        w.writerows(mode_summary)

    print("\n=== CAMPAIGN SUMMARY ===")
    for row in mode_summary:
        print(f"  {row['mode']}: {row['n_events_total']} events, "
              f"{row['n_events_equil']} reached equilibrium, "
              f"redist_median={row['redist_median_s']}s, "
              f"p95_lat={row['p95_latency_ms']}ms, "
              f"fail_rate={row['failure_rate_pct']}%, "
              f"init_share={row['mean_initial_share']}")

    print(f"\nAll graphs saved to: {GRAPHS_DIR}")
    print(f"Campaign summary: {OUT_DIR / 'campaign_summary.csv'}")


if __name__ == "__main__":
    main()
