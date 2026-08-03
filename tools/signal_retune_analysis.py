#!/usr/bin/env python3
"""signal_retune_analysis.py — mean→median latency-signal calibration for the
control-group signal reset (2026-08-03).

Purpose
-------
The controller's decision signals switched from the window MEAN to the window
MEDIAN of per-request latency (LATENCY_SIGNAL_MODE=median). Under right-skew,
median < mean, so the same thresholds (floors/spans/TAUs) will not reproduce the
mean-era operating envelope. This tool quantifies the gap from an existing run
and derives retuned floor/span/TAU values that restore the mean-era envelope.

It works on ANY run that has a window_log_lan*.jsonl (the aggregator emits both
avg_time_* and median_time_* in every domain_summary) joined with
resource_stats.csv (phase per window_end):

  * mean-era run  → shows the mean-era envelope AND the mean→median mapping
                    (controller decided on mean; aggregator recorded both).
  * median-era run → shows whether the retuned config reproduces the envelope.

Usage
-----
    python3 tools/signal_retune_analysis.py <run_folder> [--phase compute_plateau]
        <run_folder>  local run folder containing window_log_lan1.jsonl +
                      resource_stats.csv (or --window-log / --resource-stats)

Reports (per phase):
  * n windows, request volume
  * T_db: mean vs median distributions + ratio  (median/mean per window)
  * T_proc: mean vs median distributions + ratio
  * Storage scale-up: score = clip((x-60)/250) [W_T_DB=1.0]; fraction ≥ τ=0.35
  * Storage scale-down: fraction below TAU_DB_DOWN=150
  * Compute scale-up: score = 0.6*clip((cpu-10)/40)+0.4*clip((proc-25)/50);
    fraction ≥ τ=0.18
  * Compute scale-down: fraction below (cpu<15 AND proc<20)
  * Recommended retune (match mean-era fractions under median):
      - storage span S_db'  (floor F_db' = 60 kept) s.t.
        P(clip((med-60)/S')≥0.35) == P(clip((mean-60)/250)≥0.35)
      - storage TAU' s.t. P(med < TAU') == P(mean < 150)
      - compute span S_proc' s.t. score-median fraction matches score-mean
      - compute TAU_proc' s.t. P(med_proc < TAU') == P(mean_proc < 20)
"""

import argparse
import csv
import json
import statistics
import sys
from collections import defaultdict

# ── Current (mean-era) control-group calibration ─────────────────────────
F_DB = 60.0
S_DB = 250.0
TAU_DB_DOWN = 150.0
TAU_STORAGE_BASE = 0.35

F_PROC = 25.0
S_PROC = 50.0
TAU_PROC_DOWN = 20.0
TAU_CPU_DOWN = 15.0
W_CPU = 0.60
W_T_PROC = 0.40
CPU_FLOOR = 10.0
CPU_SPAN = 40.0
TAU_COMPUTE_BASE = 0.18

# Sliding-window shapes (for context, not used in the point-estimates)
STORAGE_WINDOW, STORAGE_REQUIRED = 5, 2
COMPUTE_WINDOW, COMPUTE_REQUIRED = 5, 3


def clip01(x: float) -> float:
    return min(1.0, max(0.0, x))


def load_windows(window_log: str) -> list[dict]:
    """Per-window domain stats from the aggregator window log (both LANs merged
    is fine for signal calibration; here we read whatever file is given)."""
    rows = []
    with open(window_log, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                w = json.loads(line)
            except json.JSONDecodeError:
                continue
            ds = w.get("domain_summary")
            if not ds:
                continue
            total = ds.get("total_requests", 0) or 0
            if total <= 0:
                continue
            rows.append({
                "window_end": w.get("window_end"),
                "reqs": total,
                "avg_db": ds.get("avg_time_db_ms"),
                "med_db": ds.get("median_time_db_ms"),
                "avg_proc": ds.get("avg_time_proc_ms"),
                "med_proc": ds.get("median_time_proc_ms"),
                "avg_cpu": ds.get("average_cpu_percent"),
                "avg_st_cpu": ds.get("avg_storage_cpu_percent"),
            })
    return rows


def load_phases(resource_stats: str) -> dict[float, str]:
    ph = {}
    with open(resource_stats, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                we = float(row["window_end"])
            except (ValueError, KeyError):
                continue
            ph[we] = row.get("phase", "")
    return ph


def pct(vals, q):
    if not vals:
        return float("nan")
    s = sorted(vals)
    i = min(len(s) - 1, int(q * len(s)))
    return s[i]


def dist(vals):
    if not vals:
        return "n/a"
    return (f"p25={pct(vals, 0.25):7.1f} p50={pct(vals, 0.50):7.1f} "
            f"p75={pct(vals, 0.75):7.1f} p90={pct(vals, 0.90):7.1f}")


def frac(vals, pred):
    if not vals:
        return float("nan")
    return sum(1 for v in vals if pred(v)) / len(vals)


def quantile(vals, q):
    s = sorted(vals)
    i = min(len(s) - 1, int(q * len(s)))
    return s[i]


def match_quantile(xs, xq, ys, yq):
    """Return the y-threshold whose quantile-q value equals xs's quantile-q."""
    xv = quantile(xs, xq)
    yv = quantile(ys, xq)  # same quantile in y space
    return xv, yv


def analyze(rows: list[dict], phase_rows: dict[float, str], phase: str) -> None:
    # group by phase
    by_phase = defaultdict(list)
    for r in rows:
        p = phase_rows.get(r["window_end"], "?")
        by_phase[p].append(r)

    print(f"\n{'='*78}\nPhases present: {sorted(by_phase)}")
    for p in sorted(by_phase):
        if phase and p != phase:
            continue
        grp = by_phase[p]
        reqs = [r["reqs"] for r in grp]
        avg_db = [r["avg_db"] for r in grp if r["avg_db"] is not None]
        med_db = [r["med_db"] for r in grp if r["med_db"] is not None]
        avg_proc = [r["avg_proc"] for r in grp if r["avg_proc"] is not None]
        med_proc = [r["med_proc"] for r in grp if r["med_proc"] is not None]
        cpus = [r["avg_cpu"] for r in grp if r["avg_cpu"] is not None]
        stcpus = [r["avg_st_cpu"] for r in grp if r["avg_st_cpu"] is not None]

        # per-window mean/median ratio (db and proc), only where mean>0
        db_ratio = [m / a for a, m in zip(avg_db, med_db) if a and a > 0]
        proc_ratio = [m / a for a, m in zip(avg_proc, med_proc) if a and a > 0]

        print(f"\n{'─'*78}\nPhase: {p}   windows={len(grp)}  "
              f"reqs/window p50={statistics.median(reqs):.0f}")
        print(f"  T_db  mean   : {dist(avg_db)}")
        print(f"  T_db  median : {dist(med_db)}")
        print(f"  T_db  med/mean per-window: p50={statistics.median(db_ratio):.2f} "
              f"p25={pct(db_ratio, 0.25):.2f} p90={pct(db_ratio, 0.90):.2f}")
        print(f"  T_proc mean  : {dist(avg_proc)}")
        print(f"  T_proc median: {dist(med_proc)}")
        print(f"  T_proc med/mean per-window: p50={statistics.median(proc_ratio):.2f} "
              f"p25={pct(proc_ratio, 0.25):.2f} p90={pct(proc_ratio, 0.90):.2f}")

        # ── Storage scale-up under current thresholds ──
        score_mean = [clip01((a - F_DB) / S_DB) for a in avg_db]
        score_med = [clip01((m - F_DB) / S_DB) for m in med_db]
        f_mean = frac(score_mean, lambda s: s >= TAU_STORAGE_BASE)
        f_med = frac(score_med, lambda s: s >= TAU_STORAGE_BASE)
        print(f"\n  STORAGE scale-up (score=clip((x-{F_DB:.0f})/{S_DB:.0f}), "
              f"τ={TAU_STORAGE_BASE}):")
        print(f"    fraction windows score≥τ  mean-driven={f_mean:.3f}  "
              f"median-driven={f_med:.3f}  (target: reproduce {f_mean:.3f})")

        # storage span retune: find S' s.t. median fraction matches mean fraction
        if f_med < f_mean:
            lo, hi = 10.0, S_DB
            for _ in range(60):
                mid = (lo + hi) / 2
                fm = frac([clip01((m - F_DB) / mid) for m in med_db],
                          lambda s: s >= TAU_STORAGE_BASE)
                if fm >= f_mean:
                    hi = mid
                else:
                    lo = mid
            print(f"    retune: keep floor {F_DB:.0f}, span {S_DB:.0f} → "
                  f"S_db'≈{hi:.0f}  (median-driven fraction → {f_mean:.3f})")
        else:
            print(f"    retune: span {S_DB:.0f} OK (median already ≥ mean fraction)")

        # ── Storage scale-down under current thresholds ──
        f_down_mean = frac(avg_db, lambda v: v < TAU_DB_DOWN)
        f_down_med = frac(med_db, lambda v: v < TAU_DB_DOWN)
        print(f"  STORAGE scale-down (below={TAU_DB_DOWN:.0f}ms):")
        print(f"    fraction below   mean-driven={f_down_mean:.3f}  "
              f"median-driven={f_down_med:.3f}")
        # find TAU' s.t. median below-fraction == mean-era below-fraction
        q = f_down_mean
        if q <= 0:
            print(f"    retune: TAU_db' < all medians (target fraction 0)")
        elif q >= 1:
            print(f"    retune: TAU_db' above all medians (target fraction 1)")
        else:
            tau_prime = quantile(med_db, q)
            print(f"    retune: TAU_db_down {TAU_DB_DOWN:.0f} → "
                  f"{tau_prime:.0f}  (median-driven fraction → {f_down_mean:.3f})")

        # ── Compute scale-up (CPU+latency) ──
        def cscore(cpu, proc):
            return (W_CPU * clip01((cpu - CPU_FLOOR) / CPU_SPAN)
                    + W_T_PROC * clip01((proc - F_PROC) / S_PROC))

        cscore_mean = [cscore(c, p) for c, p in zip(cpus, avg_proc)]
        cscore_med = [cscore(c, p) for c, p in zip(cpus, med_proc)]
        cf_mean = frac(cscore_mean, lambda s: s >= TAU_COMPUTE_BASE)
        cf_med = frac(cscore_med, lambda s: s >= TAU_COMPUTE_BASE)
        print(f"\n  COMPUTE scale-up (0.6*cpu_clip + 0.4*proc_clip, τ={TAU_COMPUTE_BASE}):")
        print(f"    fraction windows score≥τ  mean-driven={cf_mean:.3f}  "
              f"median-driven={cf_med:.3f}")
        if cf_med < cf_mean:
            lo, hi = 10.0, S_PROC
            for _ in range(60):
                mid = (lo + hi) / 2
                fm = frac([cscore(c, p) for c, p in zip(cpus, med_proc)],
                          lambda s: s >= TAU_COMPUTE_BASE)
                if fm >= cf_mean:
                    hi = mid
                else:
                    lo = mid
            print(f"    retune: proc span {S_PROC:.0f} → {hi:.0f} "
                  f"(median-driven fraction → {cf_mean:.3f})")
        else:
            print(f"    retune: proc span {S_PROC:.0f} OK")

        # ── Compute scale-down ──
        fcd_mean = frac([(c, p) for c, p in zip(cpus, avg_proc)],
                        lambda cp: cp[0] < TAU_CPU_DOWN and cp[1] < TAU_PROC_DOWN)
        fcd_med = frac([(c, p) for c, p in zip(cpus, med_proc)],
                       lambda cp: cp[0] < TAU_CPU_DOWN and cp[1] < TAU_PROC_DOWN)
        print(f"  COMPUTE scale-down (cpu<{TAU_CPU_DOWN:.0f} AND proc<{TAU_PROC_DOWN:.0f}):")
        print(f"    fraction below   mean-driven={fcd_mean:.3f}  "
              f"median-driven={fcd_med:.3f}")
        if 0 < fcd_mean < 1:
            # approximate: hold CPU TAU, retune proc TAU so joint fraction matches
            lo, hi = 1.0, 200.0
            for _ in range(60):
                mid = (lo + hi) / 2
                fm = frac([(c, p) for c, p in zip(cpus, med_proc)],
                          lambda cp, m=mid: cp[0] < TAU_CPU_DOWN and cp[1] < m)
                if fm >= fcd_mean:
                    hi = mid
                else:
                    lo = mid
            print(f"    retune: proc TAU {TAU_PROC_DOWN:.0f} → {hi:.0f} "
                  f"(median-driven fraction → {fcd_mean:.3f})")

    print(f"\n{'='*78}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("run_folder", nargs="?", help="run folder with window_log_lan1.jsonl + resource_stats.csv")
    ap.add_argument("--window-log", help="explicit window_log_lan*.jsonl path")
    ap.add_argument("--resource-stats", help="explicit resource_stats.csv path")
    ap.add_argument("--phase", default="", help="only analyze this phase (default: all)")
    args = ap.parse_args()

    wl = args.window_log or (args.run_folder + "/window_log_lan1.jsonl")
    rs = args.resource_stats or (args.run_folder + "/resource_stats.csv")
    try:
        rows = load_windows(wl)
    except FileNotFoundError:
        print(f"ERROR: window log not found: {wl}")
        sys.exit(1)
    try:
        phases = load_phases(rs)
    except FileNotFoundError:
        phases = {}
        print(f"WARNING: resource_stats not found ({rs}) — phases unknown")
    print(f"loaded {len(rows)} windows from {wl}")
    analyze(rows, phases, args.phase)


if __name__ == "__main__":
    main()
