#!/usr/bin/env python3
"""rq3v2_p3_01_stats.py — RQ3 v2 pre-registered statistics.

Consumes the per-run CSV produced by ``rq3_admission_analysis.py --csv``
(run-level medians; ``void`` runs excluded) and computes the pre-registered
pairs (``docs/operation/testing/experiment/v2/rq3/rq3_v2_rework_plan.md``
§2.4–§2.6, §3.1):

- **Primary pair** ``direct`` vs ``discovery`` on:
    headline   ``gap_timeout_rate_median`` (pool-wide old-backend timeout_rate
               over ``[spawn_started, admitted]``),
    supporting ``gap_failure_rate_median``, ``useful_share_median``,
               ``scale_to_first_success_median_s``,
    manipulation ``spawn_to_admitted_median_s`` (quantization).
  Mann–Whitney U (two-sided; exact enumeration when n_a + n_b <= 16) +
  Cliff's delta; **no confidence intervals**. Conclusions rest on Cliff's
  delta >= 0.6 + direction consistency; MWU p reported descriptively.
- **Sensitivity pair** ``discovery`` vs ``discovery_15`` on the same metrics
  (Cliff's delta ONLY, no MWU), showing the quantization cost scales with the
  discovery period.

Rules:
- ``void`` runs are excluded (min-admissions gate, plan §2.5).
- Missing values: the primary pair is tested only where >= 3 defined runs per
  arm have a value; the sensitivity pair >= 2 (secondary, Cliff's delta only);
  otherwise excluded and reported as counts + medians.
- No censored latency value enters MWU: latency percentiles are descriptive
  only and are not part of the MWU pairs.
- Polarity is normalized per metric (lower-is-better: discovery > direct
  supports the headline; higher-is-better: direct > discovery).

Output: ``stats_summary.csv`` (rows ``pair, metric, n_a, n_b, median_a,
median_b, mwu_p, clifffs_delta, tested, note``) plus a console table.

Usage:
    python3 docs/research_questions/v2/rq3/rq3v2_p3_01_stats.py \\
        --dataset per_run_summary.csv [--output stats_summary.csv]
"""

from __future__ import annotations

import argparse
import csv
import itertools
import math
import os
import sys

# Metrics tested on the pre-registered pairs. Polarity: "lower" = lower-is-
# better (higher value in `discovery` supports the headline), "higher" =
# higher-is-better (higher value in `direct` supports it).
_METRICS: list[tuple[str, str]] = [
    ("gap_timeout_rate_median", "lower"),
    ("gap_failure_rate_median", "lower"),
    ("useful_share_median", "higher"),
    ("scale_to_first_success_median_s", "lower"),
    ("spawn_to_admitted_median_s", "lower"),
]

# (pair_name, arm_a, arm_b, kind, min_runs)
_PAIRS: list[tuple[str, str, str, str, int]] = [
    ("primary", "direct", "discovery", "MWU+Cliff", 3),
    ("sensitivity", "discovery", "discovery_15", "Cliff-only", 2),
]

_EXACT_MAX_N = 16


def _opt_float(v) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _median(vals: list[float]) -> float | None:
    if not vals:
        return None
    s = sorted(vals)
    mid = len(s) // 2
    return s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2.0


def _norm_cdf(z: float) -> float:
    return 0.5 * math.erfc(-z / math.sqrt(2.0))


def _average_ranks(combined: list[float]) -> dict[float, float]:
    """value -> average rank (1-based), ties share the mean rank."""
    ranks: dict[float, float] = {}
    i = 0
    n = len(combined)
    while i < n:
        j = i
        while j < n and combined[j] == combined[i]:
            j += 1
        avg = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[combined[k]] = avg
        i = j
    return ranks


def _mwu_exact(x: list[float], y: list[float]) -> float:
    """Exact two-sided MWU p-value by enumerating all rank allocations."""
    n_a, n_b = len(x), len(y)
    combined = sorted(x + y)
    ranks = _average_ranks(combined)
    ranks_a = [ranks[v] for v in x]
    u_a = sum(ranks_a) - n_a * (n_a + 1) / 2.0
    u_obs = min(u_a, n_a * n_b - u_a)
    total = math.comb(n_a + n_b, n_a)
    count = 0
    for subset in itertools.combinations(range(n_a + n_b), n_a):
        s = sum(ranks[combined[idx]] for idx in subset)
        u = s - n_a * (n_a + 1) / 2.0
        if min(u, n_a * n_b - u) <= u_obs:
            count += 1
    return min(count / total, 1.0)


def _mwu_normal(x: list[float], y: list[float]) -> float:
    """Two-sided MWU p-value via tie-corrected normal approximation."""
    n_a, n_b = len(x), len(y)
    combined = sorted(x + y)
    n = n_a + n_b
    ranks = _average_ranks(combined)
    u_a = sum(ranks[v] for v in x) - n_a * (n_a + 1) / 2.0
    u_obs = min(u_a, n_a * n_b - u_a)
    mean = n_a * n_b / 2.0
    tie_sum = 0.0
    i = 0
    while i < n:
        j = i
        while j < n and combined[j] == combined[i]:
            j += 1
        t = j - i
        tie_sum += t ** 3 - t
        i = j
    var = n_a * n_b / 12.0 * ((n + 1) - tie_sum / (n * (n - 1)))
    if var <= 0:
        return 1.0
    z = (u_obs + 0.5 - mean) / math.sqrt(var)   # continuity correction
    return min(2.0 * _norm_cdf(z), 1.0)


def _mwu_p(x: list[float], y: list[float]) -> tuple[float | None, str]:
    """Two-sided MWU p-value. Exact for small n, normal approximation otherwise."""
    if not x or not y:
        return None, ""
    if len(x) + len(y) <= _EXACT_MAX_N:
        return _mwu_exact(x, y), "exact"
    return _mwu_normal(x, y), "approx(normal)"


def _cliffs_delta(x: list[float], y: list[float]) -> float | None:
    """Cliff's delta: (sum[x_i>y_j] - sum[x_i<y_j]) / (n*m)."""
    if not x or not y:
        return None
    greater = less = 0.0
    for xi in x:
        for yj in y:
            if xi > yj:
                greater += 1
            elif xi < yj:
                less += 1
    return (greater - less) / (len(x) * len(y))


def _fmt(v, nd: int = 4) -> str:
    return "" if v is None else f"{v:.{nd}f}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", required=True,
                    help="per-run CSV from rq3_admission_analysis.py --csv")
    ap.add_argument("--output", default="stats_summary.csv",
                    help="stats summary CSV output (default: stats_summary.csv)")
    args = ap.parse_args()

    if not os.path.exists(args.dataset):
        print(f"[error] dataset not found: {args.dataset}")
        return 1
    with open(args.dataset, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
    print(f"Dataset: {args.dataset} — {len(rows)} runs")
    runs = [r for r in rows if (r.get("void") or "").strip().lower() != "true"]
    print(f"Non-void runs: {len(runs)} ({len(rows) - len(runs)} void excluded)")

    out_cols = ["pair", "metric", "n_a", "n_b", "median_a", "median_b",
                "mwu_p", "clifffs_delta", "tested", "note"]
    out_rows: list[dict] = []

    def _arm_values(arm: str, metric: str) -> list[float]:
        return [v for v in (_opt_float(r.get(metric)) for r in runs
                            if (r.get("arm") or "") == arm) if v is not None]

    for pair_name, arm_a, arm_b, kind, min_runs in _PAIRS:
        print(f"\n=== pair: {pair_name} ({arm_a} vs {arm_b}, {kind}) ===")
        for metric, polarity in _METRICS:
            va = _arm_values(arm_a, metric)
            vb = _arm_values(arm_b, metric)
            note = ""
            if len(va) < min_runs or len(vb) < min_runs:
                row = {
                    "pair": pair_name, "metric": metric, "n_a": len(va),
                    "n_b": len(vb), "median_a": _fmt(_median(va)),
                    "median_b": _fmt(_median(vb)), "mwu_p": "", "clifffs_delta": "",
                    "tested": "0",
                    "note": f"excluded: < {min_runs} defined runs/cell",
                }
                out_rows.append(row)
                print(f"    {metric:<32} EXCLUDED "
                      f"(n={len(va)}/{len(vb)}, med {_fmt(_median(va))} vs "
                      f"{_fmt(_median(vb))})")
                continue
            d = _cliffs_delta(va, vb)
            mwu_p, mwu_kind = None, ""
            if kind == "MWU+Cliff":
                mwu_p, mwu_kind = _mwu_p(va, vb)
            mwu_p_str = "" if mwu_p is None else f"{mwu_p:.4f} ({mwu_kind})"
            med_a, med_b = _median(va), _median(vb)
            if pair_name == "primary" and d is not None:
                # Headline support from the Cliff's-delta sign, polarity-
                # normalized (lower-is-better: negative d — discovery > direct —
                # supports; higher-is-better: positive d supports).
                supports = (d < 0) if polarity == "lower" else (d > 0)
                note = f"polarity={polarity} supports_headline={supports}"
            else:
                # Sensitivity: the quantization cost should scale with the
                # interval (lower-is-better: discovery_15 > discovery ⇒
                # med_b > med_a) — a robustness check; no headline.
                scales = (med_a is not None and med_b is not None
                          and (med_a < med_b) if polarity == "lower" else
                          (med_a is not None and med_b is not None
                           and (med_a > med_b)))
                note = f"scales_with_interval={scales} [descriptive, no MWU]"
            row = {
                "pair": pair_name, "metric": metric, "n_a": len(va),
                "n_b": len(vb), "median_a": _fmt(med_a), "median_b": _fmt(med_b),
                "mwu_p": mwu_p_str,
                "clifffs_delta": _fmt(d), "tested": "1", "note": note,
            }
            out_rows.append(row)
            print(f"    {metric:<32} n={len(va)}/{len(vb)} "
                  f"med {_fmt(med_a)} vs {_fmt(med_b)}"
                  + (f"  MWU p={mwu_p_str}" if mwu_p_str else "")
                  + f"  d={_fmt(d)}  [{note}]")

    with open(args.output, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=out_cols)
        w.writeheader()
        w.writerows(out_rows)
    print(f"\nwrote stats summary: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
