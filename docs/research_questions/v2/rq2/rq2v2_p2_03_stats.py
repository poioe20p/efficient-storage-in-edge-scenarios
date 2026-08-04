#!/usr/bin/env python3
"""rq2v2_p2_03_stats.py — RQ2 v2 pre-registered statistics on campaign_dataset.csv.

Consumes the campaign dataset produced by
``source/scripts/testing/analysis/rq2/rq2_bottleneck_aware_campaign.py`` and
computes the pre-registered EFFECT-SIZE comparisons (plan §2.5) at n=3:

    per episode (cb, db): aligned vs mis-aligned (headline), ba vs the
    mis-aligned arm, ba vs the aligned arm, on: timeout_rate, failure_rate,
    node-minutes (compute+storage per 1000 requests), time-to-recover.

Alignment: in the compute-bound episode (``cb``) the aligned arm is ``cf``
(fixed_compute_first) and the mis-aligned arm is ``sf``; in the data-bound
episode (``db``) the aligned arm is ``sf`` and the mis-aligned arm is ``cf``.

Statistics: two-sided Mann–Whitney U reported DESCRIPTIVELY (n=3 gives a
minimum p of 0.10, so NO alpha claim is made; pure-python: exact enumeration
for n_a+n_b <= 16, tie-corrected normal approximation with continuity
correction otherwise) and Cliff's delta
``(sum_{i,j}[x_i>y_j] - sum_{i,j}[x_i<y_j]) / (n*m)``. Conclusions rest on
Cliff's delta >= 0.6 (large effect) and 3/3 direction consistency across
replicates.

Rules:
- Only headline/primary pairs are evaluated (MWU + Cliff's delta, reported
  descriptively); exploratory pairs get Cliff's delta only, no MWU claim.
- No censored latency value enters MWU: latency percentiles are descriptive
  only (median-of-replicates + min/max, censoring flag where the value reaches
  the cap, default 30000 ms = the v1 CURL_MAX_TIME). The unit of the latency
  columns is auto-detected (the v1 dataset stores SECONDS despite the ``_ms``
  column suffix), so the cap is compared in the correct scale.
- Missing values: a metric is tested only where >= 3 runs per cell have a
  defined value; otherwise it is excluded and reported as counts + medians.

Output: ``stats_summary.csv`` (rows ``episode, pair, metric, n_a, n_b,
median_a, median_b, mwu_p, clifffs_delta, tested, note``) plus a readable
console table.

Usage:
    python3 docs/research_questions/v2/rq2/rq2v2_p2_03_stats.py \
        --dataset campaign_dataset.csv [--output stats_summary.csv]
"""

from __future__ import annotations

import argparse
import csv
import itertools
import math
import os
import sys

# Candidate columns per metric, tried in order (first with data wins).
_METRIC_COLS: dict[str, list[str]] = {
    "timeout_rate": ["timeout_rate", "timeout_pct", "ep_timeout_pct",
                     "timeout_rate_pct"],
    "failure_rate": ["failure_rate", "ep_failure_pct", "failure_pct"],
    "time_to_recover": ["time_to_recover", "relief_recovery_median_s",
                        "recovery_median_s"],
}
_METRIC_DESC = {
    "timeout_rate": "timeouts / offered",
    "failure_rate": "failed (http != 200) / completed",
    "node_minutes_per_1000": "compute+storage node-minutes per 1000 requests",
    "time_to_recover": "median recovery delay (s) after scale-up",
}
_METRIC_NAMES = ["timeout_rate", "failure_rate", "node_minutes_per_1000",
                 "time_to_recover"]

_EXACT_MAX_N = 16          # n_a + n_b <= 16 -> exact enumeration
_MIN_RUNS = 3              # per cell, defined values required to test

_EPISODE_ALIASES = {"cb": "cb", "compute_bound": "cb", "compute-bound": "cb",
                    "db": "db", "data_bound": "db", "data-bound": "db"}

_LATENCY_COLS = ["ep_p50_ms", "ep_p95_ms", "ep_p99_ms"]


# ---------------------------------------------------------------------------
# Parsing / helpers
# ---------------------------------------------------------------------------

def _opt_float(v) -> float | None:
    """Blank/empty cells are missing values, not zero."""
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


# ---------------------------------------------------------------------------
# Dataset access
# ---------------------------------------------------------------------------

def _metric_values(rows: list[dict], metric: str) -> tuple[list[float], str]:
    """Defined values for a metric across rows + the column mapping used."""
    if metric == "node_minutes_per_1000":
        out: list[float] = []
        for r in rows:
            c = _opt_float(r.get("nm_per1000_compute"))
            s = _opt_float(r.get("nm_per1000_storage"))
            if c is not None and s is not None:
                out.append(c + s)
            elif c is not None:
                out.append(c)
            elif s is not None:
                out.append(s)
        return out, "nm_per1000_compute+nm_per1000_storage"
    for col in _METRIC_COLS[metric]:
        vals = [v for v in (_opt_float(r.get(col)) for r in rows) if v is not None]
        if vals:
            return vals, col
    return [], ""


def _episode_of(r) -> str:
    raw = (r.get("episode") or "").strip().lower()
    return _EPISODE_ALIASES.get(raw, raw)


def _pairs(episode: str) -> list[tuple[str, str, str, str, str]]:
    """(pair_name, policy_a, policy_b, kind, role) for one episode.

    Effect-size hierarchy at n=3 (no alpha claims): headline = aligned vs
    mis-aligned (the cross-over); primary = ba vs mis-aligned (value-of-
    information) and ba vs aligned (equivalence); exploratory = cf vs sf.
    """
    aligned = "cf" if episode == "cb" else "sf"
    mis = "sf" if episode == "cb" else "cf"
    return [
        ("aligned_vs_misaligned", aligned, mis, "headline", "headline"),
        ("ba_vs_misaligned", "ba", mis, "primary", "primary"),
        ("ba_vs_aligned", "ba", aligned, "primary", "primary"),
        ("cf_vs_sf", "cf", "sf", "exploratory", "exploratory"),
    ]


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def _console(rows: list[dict], col_map: dict[str, str], cap_value: float | None,
             latency_unit: str) -> None:
    print("\nRQ2 v2 stats — campaign dataset")
    mapped = ", ".join("{}->{}".format(k, v or "MISSING") for k, v in col_map.items())
    print(f"  metric column mappings used: {mapped}")
    if cap_value is not None:
        print(f"  latency columns detected as {latency_unit} "
              f"(cap={cap_value:g}{latency_unit}); values reaching the cap are "
              f"flagged censored")
    for episode in ("cb", "db"):
        ep_rows = [r for r in rows if r["episode"] == episode]
        metric_rows = [r for r in ep_rows if r["metric"] in _METRIC_NAMES]
        lat_rows = [r for r in ep_rows if r["metric"] in _LATENCY_COLS]
        print(f"\n  episode={episode}")
        for row in metric_rows:
            flag = " [TESTED]" if row["tested"] else ""
            print(f"    {row['metric']:<22} {row['pair']:<10} "
                  f"n={row['n_a']}/{row['n_b']} "
                  f"med {row['median_a']} vs {row['median_b']}"
                  f"{'  MWU p=' + row['mwu_p'] if row['mwu_p'] else ''}"
                  f"{'  d=' + row['clifffs_delta'] if row['clifffs_delta'] != '' else ''}"
                  f"{flag}  [{row['note']}]")
        if lat_rows:
            print("    descriptive latency (median-of-replicates; censoring flag):")
            for row in lat_rows:
                print(f"      {row['pair']:<10} {row['metric']:<10} "
                      f"n={row['n_a']} median={row['median_a']}  [{row['note']}]")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", required=True,
                    help="campaign_dataset.csv produced by rq2_bottleneck_aware_campaign.py")
    ap.add_argument("--output", default="stats_summary.csv",
                    help="stats summary CSV output (default: stats_summary.csv)")
    ap.add_argument("--latency-cap-ms", type=float, default=30000.0,
                    help="latency cap in ms; percentile values reaching it are "
                         "flagged censored (default 30000 = v1 CURL_MAX_TIME). "
                         "The unit of the dataset columns is auto-detected (the "
                         "v1 dataset stores seconds despite the _ms suffix).")
    ap.add_argument("--latency-unit", choices=["auto", "seconds", "milliseconds"],
                    default="auto",
                    help="unit of the ep_pXX_ms latency columns: auto (default; "
                         "a dataset whose max value < 1000 is treated as seconds, "
                         "the v1 convention), seconds, or milliseconds. Pin it "
                         "explicitly to avoid ambiguity when all values < 1000.")
    args = ap.parse_args()

    if not os.path.exists(args.dataset):
        print(f"[error] dataset not found: {args.dataset}")
        return 1
    with open(args.dataset, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        rows = list(reader)
        cols = reader.fieldnames or []
    print(f"Dataset: {args.dataset} — {len(rows)} runs, {len(cols)} columns")

    col_map: dict[str, str] = {}
    for metric in _METRIC_NAMES:
        _, col = _metric_values(rows, metric)
        col_map[metric] = col
    for col in ("ep_p50_ms", "ep_p95_ms", "ep_p99_ms"):
        present = any(_opt_float(r.get(col)) is not None for r in rows)
        col_map[col] = col if present else "MISSING"

    # Latency columns: the v1 dataset stores SECONDS despite the ``_ms``
    # suffix (e.g. ``ep_p99_ms=30.000017`` at the 30 s cap). Auto-detect the
    # unit so the censoring flag compares against the cap in the right scale.
    all_lat = [v for pct in _LATENCY_COLS
               for v in (_opt_float(r.get(pct)) for r in rows) if v is not None]
    latency_unit = "ms"
    if args.latency_unit == "seconds":
        latency_unit = "s"
    elif args.latency_unit == "milliseconds":
        latency_unit = "ms"
    else:  # auto
        if all_lat and max(all_lat) < 1000.0:
            # Ambiguous: every observed latency value < 1000 — could be the v1
            # seconds convention OR sub-1000 true milliseconds. Default to the
            # v1 seconds convention; pin --latency-unit milliseconds if the
            # dataset stores true ms.
            latency_unit = "s"
            print("  [warn] --latency-unit=auto: all latency values < 1000 — "
                  "assuming SECONDS (v1 convention). Use --latency-unit "
                  "milliseconds if the dataset stores true ms.")
    cap_value = (args.latency_cap_ms if latency_unit == "ms"
                 else args.latency_cap_ms / 1000.0)

    summary: list[dict] = []
    for episode in ("cb", "db"):
        erows = [r for r in rows if _episode_of(r) == episode]
        for metric in _METRIC_NAMES:
            for pair_name, a_pol, b_pol, kind, role in _pairs(episode):
                vals_a, col_a = _metric_values(
                    [r for r in erows if r.get("policy") == a_pol], metric)
                vals_b, col_b = _metric_values(
                    [r for r in erows if r.get("policy") == b_pol], metric)
                n_a, n_b = len(vals_a), len(vals_b)
                med_a, med_b = _median(vals_a), _median(vals_b)
                present = bool(_metric_values(erows, metric)[0])
                tested = bool(role in ("headline", "primary") and present
                              and n_a >= _MIN_RUNS and n_b >= _MIN_RUNS)
                mwu_p, method = "", ""
                if tested:
                    p, method = _mwu_p(vals_a, vals_b)
                    mwu_p = f"{p:.4g}" if p is not None else ""
                delta = ""
                if n_a >= 1 and n_b >= 1:
                    d = _cliffs_delta(vals_a, vals_b)
                    delta = f"{d:.4f}"
                note_parts = [kind]
                if not present:
                    note_parts.append(f"metric absent from dataset "
                                      f"(no {metric} column)")
                elif n_a < _MIN_RUNS or n_b < _MIN_RUNS:
                    note_parts.append(f"missing: <{_MIN_RUNS} runs per cell "
                                      f"({n_a}/{n_b} defined)")
                if method:
                    note_parts.append(method)
                if metric == "failure_rate" and col_map[metric]:
                    note_parts.append("v1 ep_failure_pct includes timeouts")
                if role in ("headline", "primary"):
                    note_parts.append("n=3 no alpha claim (effect-size)")
                elif role == "exploratory":
                    note_parts.append("no significance claim")
                summary.append({
                    "episode": episode, "pair": pair_name, "metric": metric,
                    "n_a": n_a, "n_b": n_b,
                    "median_a": f"{med_a:.4g}" if med_a is not None else "",
                    "median_b": f"{med_b:.4g}" if med_b is not None else "",
                    "mwu_p": mwu_p, "clifffs_delta": delta,
                    "tested": int(tested), "note": "; ".join(note_parts),
                })

        # Descriptive latency per cell (never enters MWU).
        cells = sorted({r.get("cell") for r in erows if r.get("cell")})
        for cell in cells:
            for pct in _LATENCY_COLS:
                vals = [_opt_float(r.get(pct)) for r in erows if r.get("cell") == cell]
                vals = [v for v in vals if v is not None]
                if not vals:
                    continue
                med = _median(vals)
                mn, mx = min(vals), max(vals)
                censored = any(v + 1e-6 >= cap_value for v in vals)
                note = (f"descriptive only ({latency_unit}); "
                        f"min={mn:g} max={mx:g}")
                if censored:
                    note += f"; CENSORED at cap={cap_value:g}{latency_unit}"
                summary.append({
                    "episode": episode, "pair": cell, "metric": pct,
                    "n_a": len(vals), "n_b": "",
                    "median_a": f"{med:.4g}", "median_b": "",
                    "mwu_p": "", "clifffs_delta": "", "tested": 0, "note": note,
                })

    cols_out = ["episode", "pair", "metric", "n_a", "n_b", "median_a",
                "median_b", "mwu_p", "clifffs_delta", "tested", "note"]
    with open(args.output, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols_out, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summary)

    n_tested = sum(r["tested"] for r in summary)
    n_total = len(_METRIC_NAMES) * 2 * sum(
        1 for *_x, role in _pairs("cb") if role in ("headline", "primary"))
    print(f"  comparisons evaluated : {n_tested}/{n_total} "
          f"(effect-size at n=3; no alpha claims)")
    _console(summary, col_map, cap_value, latency_unit)
    print(f"\n  wrote {args.output} ({len(summary)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
