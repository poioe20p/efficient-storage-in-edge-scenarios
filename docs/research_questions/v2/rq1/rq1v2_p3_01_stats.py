#!/usr/bin/env python3
"""rq1v2_p3_01_stats.py — RQ1 v2 pre-registered statistics.

Consumes already-analyzed RQ1 run folders (``rq1_delivery_per_run.py`` output
under each run's ``analysis/rq1_delivery/``) and computes the pre-registered
comparisons at n=5 per arm (plan §3.1):

    Primary attribution pairs (factorial edges — MWU + Cliff's delta):
      delay:  ep vs delayed (A-B, fresh+complete vs stale+complete)
              sp   vs ls      (D-C, fresh+lossy vs stale+lossy)
      loss:   ep vs sp        (A-D, complete+fresh vs lossy+fresh)
              delayed vs ls   (B-C, complete+stale vs lossy+stale)
    Headline tradeoff (descriptive + Cliff's delta ONLY, no significance claim):
      delayed vs sp (B-D, stale+complete vs fresh+lossy)
      ep vs ls       (A-C, fresh+complete vs stale+lossy)

Metrics (per run; experimental unit = the run, LANs aggregated):
  capacity_latency_s       usable-capacity latency (demand-shift -> spawn
                           ready; mean over contributing LANs, coverage noted)
  timeout_rate             PLATEAU timeouts / (offered - canceled)
  failure_rate             PLATEAU failed (completed & !=200) / completed
  timeout_rate_nonsurge    NON-SURGE (baseline+recovery_gap+demand_drop)
                           timeouts / (offered - canceled)   <- C8
  failure_rate_nonsurge    NON-SURGE failed / completed      <- C8
  scale_down_latency_s     recovery_gap start -> first decision-log scale-down
  info_age_decision_s      median info age at decision

Rules (structural mirror of rq2v2_p2_03_stats.py):
- Two-sided Mann–Whitney U reported DESCRIPTIVELY (exact enumeration for
  n_a+n_b <= 16, tie-corrected normal approximation otherwise) + Cliff's
  delta. Conclusions rest on Cliff's delta + direction consistency, not an
  alpha claim at n=5. Pre-registered expected direction per pair: the DELAY
  edges (A->B, D->C) and LOSS edges (A->D, B->C) are expected to worsen
  rates/capacity (delta sign annotated in PAIR_DIRECTION).
- C8 verdict (non-surge): computed from the non-surge metrics across the
  factorial edges — delay penalty (delay edges positive, loss edges ~0),
  null (all |delta| <= 0.2, reported as a null), or unanticipated (any loss
  edge clearly positive -> re-inspection). Canceled rows are EXCLUDED from the
  timeout-rate denominator (phase-boundary drain artifacts).
- No censored latency value enters MWU: plateau p50/p95/p99 are descriptive
  only, with a censoring flag when ANY raw per-LAN percentile reaches
  CURL_MAX_TIME (300 s). None of the MWU metrics is a censored latency
  percentile.
- Missing values: a metric is tested only where >= 3 runs per cell have a
  defined value; otherwise excluded and reported as counts + medians. Partial
  (single-LAN) capacity values are annotated. Legacy v1 folders (no `status`
  column) are detected: they contribute failure/capacity/info-age/scale-down
  but their timeout-rate metrics are excluded (meaningless without the status
  class) with a warning.

Output: ``rq1_stats_summary.csv`` (rows ``pair, metric, n_a, n_b, median_a,
median_b, mwu_p, clifffs_delta, tested, note``) plus a readable console table
with the C8 verdict.

Usage (each --run-dirs-<arm> takes ONE space-separated value; repeat the flag
per group):
    python3 docs/research_questions/v2/rq1/rq1v2_p3_01_stats.py \
        --run-dirs-ep      "ep_1 ep_2 ..." \
        --run-dirs-delayed "delayed_1 ..." \
        --run-dirs-ls      "ls_1 ..." \
        --run-dirs-sp      "sp_1 ..." \
        [--output rq1_stats_summary.csv]
"""

from __future__ import annotations

import argparse
import csv
import itertools
import math
import os
import re
import sys
from datetime import datetime

ANALYSIS_SUBDIR = os.path.join("analysis", "rq1_delivery")

ARMS = ("ep", "delayed", "ls", "sp")
ARM_LABELS = {"ep": "A ep", "delayed": "B delayed", "ls": "C ls", "sp": "D sp"}
ARM_FROM_SOURCE = {"event_preserving": "ep", "delayed_event_preserving": "delayed",
                   "poll": "ls", "sampled_push": "sp", "zmq": "zmq"}

NON_SURGE_PHASES = ("baseline", "recovery_gap", "demand_drop")

# Primary attribution pairs (factorial edges) + headline tradeoff pairs.
PRIMARY_PAIRS = [
    ("delay_fresh", "ep", "delayed"),
    ("delay_lossy", "sp", "ls"),
    ("loss_fresh", "ep", "sp"),
    ("loss_stale", "delayed", "ls"),
]
HEADLINE_PAIRS = [
    ("stale_complete_vs_fresh_lossy", "delayed", "sp"),
    ("fresh_complete_vs_stale_lossy", "ep", "ls"),
]
# Pre-registered expected direction: which side is expected WORSE (higher
# rates / higher capacity latency). Smaller-is-better for every metric here.
PAIR_DIRECTION = {
    "delay_fresh": "expect B (delayed) worse than A (ep) -> delta < 0",
    "delay_lossy": "expect C (ls) worse than D (sp) -> delta < 0",
    "loss_fresh": "expect D (sp) worse than A (ep) -> delta < 0",
    "loss_stale": "expect C (ls) worse than B (delayed) -> delta < 0",
    "stale_complete_vs_fresh_lossy": "headline tradeoff, no expected sign",
    "fresh_complete_vs_stale_lossy": "headline tradeoff, no expected sign",
}

METRICS = ["capacity_latency_s", "timeout_rate", "failure_rate",
           "timeout_rate_nonsurge", "failure_rate_nonsurge",
           "scale_down_latency_s", "info_age_decision_s"]
METRIC_DESC = {
    "capacity_latency_s": "usable-capacity latency (s)",
    "timeout_rate": "PLATEAU timeouts / (offered-canceled)",
    "failure_rate": "PLATEAU failed (completed & !=200) / completed",
    "timeout_rate_nonsurge": "NON-SURGE timeouts / (offered-canceled) [C8]",
    "failure_rate_nonsurge": "NON-SURGE failed / completed [C8]",
    "scale_down_latency_s": "recovery_gap start -> first decision-log scale-down (s)",
    "info_age_decision_s": "median info age at decision (s)",
}

LATENCY_CAP_S = 300.0          # CURL_MAX_TIME
LATENCY_PCTS = ("p50", "p95", "p99")

DYN_COMPUTE_RE = re.compile(r"^edge_server_lan(\d+)_dyn\d+$", re.IGNORECASE)
SCALE_ACTIONS = ("scale_up", "scale_down")

_EXACT_MAX_N = 16
_MIN_RUNS = 3


# ---------------------------------------------------------------------------
# Statistics helpers (mirror rq2v2_p2_03_stats.py)
# ---------------------------------------------------------------------------

def _opt_float(v) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _iso_to_epoch(value):
    """Parse an ISO-8601 UTC timestamp or a numeric epoch into epoch seconds.
    (container_events.csv stores `timestamp_iso` as ISO-8601.)"""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        pass
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
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
    ranks: dict[float, float] = {}
    i, n = 0, len(combined)
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
    n_a, n_b = len(x), len(y)
    combined = sorted(x + y)
    ranks = _average_ranks(combined)
    u_a = sum(ranks[v] for v in x) - n_a * (n_a + 1) / 2.0
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
    z = (u_obs + 0.5 - mean) / math.sqrt(var)
    return min(2.0 * _norm_cdf(z), 1.0)


def _mwu_p(x: list[float], y: list[float]) -> tuple[float | None, str]:
    if not x or not y:
        return None, ""
    if len(x) + len(y) <= _EXACT_MAX_N:
        return _mwu_exact(x, y), "exact"
    return _mwu_normal(x, y), "approx(normal)"


def _cliffs_delta(x: list[float], y: list[float]) -> float | None:
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
# Per-run metric extraction from analyzer outputs
# ---------------------------------------------------------------------------

def _load_rows(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _is_v2_run(run_dir: str) -> bool:
    """v2 open-loop runs carry the `status` column in client_requests.csv;
    legacy v1 folders do not (their timeout-rate metrics would be meaningless)."""
    req = _load_rows(os.path.join(run_dir, "client_requests.csv"))
    return bool(req) and "status" in req[0]


def _read_arm(run_dir: str) -> str | None:
    for r in _load_rows(os.path.join(run_dir, ANALYSIS_SUBDIR, "run_meta.csv")):
        if (r.get("key") or "").strip() == "telem_source":
            return ARM_FROM_SOURCE.get((r.get("value") or "").strip())
    return None


def _removal_latency(run_dir: str, recovery_gap_start) -> float | None:
    """Mean over LANs of the first dynamic-compute removal latency after
    recovery_gap start, from container_events.csv (``event == removed``;
    ISO-8601 ``timestamp_iso``). This is the container_events cross-check for
    the decision-log scale-down metric (joint reporting rule §0.5). Best-effort
    and churn-inclusive (v1 G8: removals include replacement/churn) — a
    cross-check, never the primary metric; None when no removal is found."""
    if recovery_gap_start is None:
        return None
    events = _load_rows(os.path.join(run_dir, "container_events.csv"))
    if not events:
        return None
    per_lan: dict[str, list[float]] = {"lan1": [], "lan2": []}
    for r in events:
        if (r.get("event") or "").strip() != "removed":
            continue
        m = DYN_COMPUTE_RE.match((r.get("container") or "").strip())
        if not m or m.group(1) not in ("1", "2"):
            continue
        t = _iso_to_epoch(r.get("timestamp_iso"))
        if t is None or t < recovery_gap_start:
            continue
        per_lan[f"lan{m.group(1)}"].append(t - recovery_gap_start)
    firsts = [min(v) for v in per_lan.values() if v]
    return (sum(firsts) / len(firsts)) if firsts else None


def _run_metrics(run_dir: str) -> dict:
    """Per-run metric values from the per-run analyzer output. Counts are
    summed across LANs and (for non-surge) across non-surge phases; latency
    values are LAN-mean/median-aggregated with coverage recorded. Legacy v1
    runs omit the status-dependent metrics. The run's arm is recorded for
    arm-vs-folder validation."""
    ad = os.path.join(run_dir, ANALYSIS_SUBDIR)
    out: dict = {}
    out["arm"] = _read_arm(run_dir)
    out["v2"] = _is_v2_run(run_dir)

    timeline = _load_rows(os.path.join(ad, "reaction_timeline.csv"))
    caps = []
    rg_start = None
    for r in timeline:
        ph = (r.get("phase") or "").strip()
        v = _opt_float(r.get("capacity_latency_s"))
        if ph == "compute_plateau" and v is not None:
            caps.append(v)
        if ph == "recovery_gap":
            rg_start = _opt_float(r.get("phase_start"))
    if caps:
        out["capacity_latency_s"] = sum(caps) / len(caps)
        out["capacity_lan_count"] = len(caps)      # 1 = partial-LAN value
    downs = [_opt_float(r.get("scale_down_latency_s")) for r in timeline
             if (r.get("phase") or "").strip() == "recovery_gap"]
    downs = [v for v in downs if v is not None]
    if downs:
        out["scale_down_latency_s"] = sum(downs) / len(downs)
    out["removal_latency_s"] = _removal_latency(run_dir, rg_start)

    # Plateau vs non-surge counts (per-LAN percentile values kept raw for the
    # censoring flag).
    offered = failed = completed = timed_out = canceled = dropped = 0
    ns_offered = ns_failed = ns_completed = ns_timed_out = ns_canceled = 0
    ns_dropped = 0
    plateau_pcts: dict[str, list[float]] = {p: [] for p in LATENCY_PCTS}
    for r in _load_rows(os.path.join(ad, "phase_service_quality.csv")):
        ph = (r.get("phase") or "").strip()
        o = int(r.get("offered") or 0)
        c = int(r.get("canceled_count") or 0)
        d = int(r.get("dropped_count") or 0)
        if ph == "compute_plateau":
            offered += o
            failed += int(r.get("failure_count") or 0)
            completed += int(r.get("completed") or 0)
            timed_out += int(r.get("timeout_count") or 0)
            canceled += c
            dropped += d
            for p in LATENCY_PCTS:
                v = _opt_float(r.get(p))
                if v is not None:
                    plateau_pcts[p].append(v)
        elif ph in NON_SURGE_PHASES:
            ns_offered += o
            ns_failed += int(r.get("failure_count") or 0)
            ns_completed += int(r.get("completed") or 0)
            ns_timed_out += int(r.get("timeout_count") or 0)
            ns_canceled += c
            ns_dropped += d
    out["offered"] = offered
    if out["v2"]:
        # Timeout-rate denominator excludes rows that never reached the service
        # and can never time out: canceled (phase-boundary drain artifacts) AND
        # dropped (client-side admission, window full).
        if offered - canceled - dropped > 0:
            out["timeout_rate"] = timed_out / (offered - canceled - dropped)
        if ns_offered - ns_canceled - ns_dropped > 0:
            out["timeout_rate_nonsurge"] = ns_timed_out / (
                ns_offered - ns_canceled - ns_dropped)
    if out["v2"]:
        if completed:
            out["failure_rate"] = failed / completed
        if ns_completed:
            out["failure_rate_nonsurge"] = ns_failed / ns_completed
    # Legacy v1 runs emit NO rate metrics: their failure-rate convention (v1
    # all-rows denominator) is not comparable to the v2 completed-only
    # denominator, so mixing them into the same cell would compare different
    # definitions. Legacy runs still contribute capacity / info-age /
    # scale-down (denominator-independent).
    for p in LATENCY_PCTS:
        if plateau_pcts[p]:
            # Run-level value = median of the per-LAN percentiles; the RAW
            # per-LAN values are kept for the censoring flag.
            out[f"plateau_{p}"] = _median(plateau_pcts[p])
            out[f"plateau_{p}_raw"] = plateau_pcts[p]

    # Info age at decision: scale actions only (housekeeping rows such as
    # absent / reserve_loss are not evidence-backed decisions).
    ages = [_opt_float(r.get("info_age_s")) for r in
            _load_rows(os.path.join(ad, "info_age.csv"))
            if (r.get("action_type") or "").strip() in SCALE_ACTIONS]
    ages = [v for v in ages if v is not None]
    if ages:
        out["info_age_decision_s"] = _median(ages)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _parse_run_dirs(values):
    out = []
    for v in values or []:
        out.extend(v.split())
    result = []
    for p in out:
        if os.path.isdir(p):
            result.append(os.path.abspath(p))
        else:
            print(f"[warn] run folder not found (dropped): {p}")
    return result


def _edge_deltas(cells, metric, pairs):
    """Cliff's deltas for the given edges, only where BOTH cells have >= _MIN_RUNS
    defined values (the same >= 3 floor as the primary comparisons)."""
    out = []
    for _name, a, b in pairs:
        va = [m[metric] for m in cells[a] if metric in m]
        vb = [m[metric] for m in cells[b] if metric in m]
        if len(va) >= _MIN_RUNS and len(vb) >= _MIN_RUNS:
            d = _cliffs_delta(va, vb)
            if d is not None:
                out.append(d)
    return out


def _c8_verdict(cells) -> str:
    """C8 decision from the non-surge metrics across the factorial edges.

    delta sign: _cliffs_delta(x, y) with x = first arm of each pair; the
    pre-registered expected direction is the SECOND arm worse (higher non-surge
    rate) -> delta < 0 is the degradation direction. Flags are aggregated
    across BOTH non-surge metrics so a loss-edge degradation on a single
    metric is never masked by a delay penalty on the other. Decision (matching
    experiment_plan.md criterion 8): loss-edge degradation OR any direction
    reversal (|delta| > 0.2 with the wrong sign) -> UNANTICIPATED; else delay
    edges degrade (delta < -0.2) -> DELAY PENALTY (pass); else NULL (all
    |delta| <= 0.2).
    """
    delay_degrades = False
    loss_degrades = False
    reversal = False
    delay_tested = False
    loss_tested = False
    for metric in ("timeout_rate_nonsurge", "failure_rate_nonsurge"):
        dd = _edge_deltas(cells, metric, PRIMARY_PAIRS[:2])   # delay edges
        ld = _edge_deltas(cells, metric, PRIMARY_PAIRS[2:])   # loss edges
        delay_tested = delay_tested or bool(dd)
        loss_tested = loss_tested or bool(ld)
        for d in dd:
            if d < -0.2:
                delay_degrades = True
            elif d > 0.2:
                reversal = True
        for d in ld:
            if d < -0.2:
                loss_degrades = True
            elif d > 0.2:
                reversal = True
    if not delay_tested and not loss_tested:
        return ("INSUFFICIENT DATA (no edge met the >= 3-runs floor on a "
                "non-surge metric)")
    if loss_degrades or reversal:
        return ("UNANTICIPATED (loss-edge non-surge degradation or a "
                "direction reversal present) — inspect")
    if delay_degrades:
        loss_note = "loss edges ~0" if loss_tested else "loss edges untested"
        return (f"DELAY PENALTY (C8 pass: delay edges degrade non-surge; "
                f"{loss_note})")
    return "NULL (no discriminative non-surge difference)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    for arm in ARMS:
        ap.add_argument(f"--run-dirs-{arm}", action="append", default=[],
                        metavar="DIR", help=f"{ARM_LABELS[arm]} run folders")
    ap.add_argument("--output", default="rq1_stats_summary.csv",
                    help="stats summary CSV output (default: rq1_stats_summary.csv)")
    args = ap.parse_args()

    cells = {arm: [] for arm in ARMS}
    legacy_counts = {arm: 0 for arm in ARMS}
    for arm in ARMS:
        for rd in _parse_run_dirs(getattr(args, f"run_dirs_{arm}")):
            if not os.path.isdir(os.path.join(rd, ANALYSIS_SUBDIR)):
                print(f"[warn] {arm}: no analysis/ subdir — dropped: {rd}")
                continue
            m = _run_metrics(rd)
            # Arm-vs-folder validation: never let a mis-grouped or unprovenanced
            # folder contaminate a cell.
            decl = m.get("arm")
            if decl is None:
                print(f"[warn] {arm}: run has no declared/mapped arm — "
                      f"dropped: {rd}")
                continue
            if decl != arm:
                print(f"[warn] {arm}: run declares arm '{decl}' — dropped: {rd}")
                continue
            if not m.get("v2"):
                legacy_counts[arm] += 1
                print(f"[warn] {arm}: legacy v1 folder (no `status` column) — "
                      f"rate metrics (timeout/failure, plateau + non-surge) "
                      f"excluded for {os.path.basename(rd)}")
            m["run"] = os.path.basename(rd)
            cells[arm].append(m)
        print(f"{arm}: {len(cells[arm])} run(s) with metrics"
              + (f" ({legacy_counts[arm]} legacy)" if legacy_counts[arm] else ""))

    if not any(cells.values()):
        sys.stderr.write("ERROR: no valid analyzed run folders supplied.\n")
        return 2

    # --- primary + headline pairs -------------------------------------------
    summary: list[dict] = []
    pairs = [(name, a, b, "primary") for name, a, b in PRIMARY_PAIRS]
    pairs += [(name, a, b, "headline") for name, a, b in HEADLINE_PAIRS]

    for pair_name, a_arm, b_arm, kind in pairs:
        print(f"\n  pair {pair_name}: {ARM_LABELS[a_arm]} vs "
              f"{ARM_LABELS[b_arm]}  [{PAIR_DIRECTION[pair_name]}]")
        for metric in METRICS:
            vals_a = [m[metric] for m in cells[a_arm] if metric in m]
            vals_b = [m[metric] for m in cells[b_arm] if metric in m]
            n_a, n_b = len(vals_a), len(vals_b)
            med_a, med_b = _median(vals_a), _median(vals_b)
            present = bool(vals_a or vals_b)
            tested = bool(kind == "primary" and present
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
            if n_a < _MIN_RUNS or n_b < _MIN_RUNS:
                note_parts.append(f"missing: <{_MIN_RUNS} runs per cell "
                                  f"({n_a}/{n_b} defined)")
            elif n_a == _MIN_RUNS or n_b == _MIN_RUNS:
                note_parts.append(f"at the >= {_MIN_RUNS} floor ({n_a}/{n_b})")
            if metric == "capacity_latency_s":
                part_a = sum(1 for m in cells[a_arm]
                             if m.get("capacity_lan_count") == 1)
                part_b = sum(1 for m in cells[b_arm]
                             if m.get("capacity_lan_count") == 1)
                if part_a or part_b:
                    note_parts.append(
                        f"partial-LAN capacity in {part_a}/{part_b} runs")
            if vals_a and vals_b and all(v == vals_a[0] for v in vals_a + vals_b):
                note_parts.append("all values equal (degenerate — no separation)")
            if method:
                note_parts.append(method)
            if kind == "headline":
                note_parts.append("Cliff's delta only — no significance claim")
            summary.append({
                "pair": pair_name, "metric": metric, "n_a": n_a, "n_b": n_b,
                "median_a": f"{med_a:.4g}" if med_a is not None else "",
                "median_b": f"{med_b:.4g}" if med_b is not None else "",
                "mwu_p": mwu_p, "clifffs_delta": delta,
                "tested": int(tested), "note": "; ".join(note_parts),
            })

    # --- descriptive plateau latency percentiles (never enter MWU) ----------
    for arm in ARMS:
        for p in LATENCY_PCTS:
            vals = [m.get(f"plateau_{p}") for m in cells[arm]
                    if f"plateau_{p}" in m]
            vals = [v for v in vals if v is not None]
            if not vals:
                continue
            med = _median(vals)
            raw = [v for m in cells[arm] for v in m.get(f"plateau_{p}_raw", [])]
            raw = raw or vals
            mn, mx = min(raw), max(raw)
            censored = any(v + 1e-6 >= LATENCY_CAP_S for v in raw)
            note = f"descriptive only (s); min={mn:g} max={mx:g}"
            if censored:
                note += f"; CENSORED at cap={LATENCY_CAP_S:g}s"
            summary.append({
                "pair": arm, "metric": f"plateau_{p}", "n_a": len(vals),
                "n_b": "", "median_a": f"{med:.4g}", "median_b": "",
                "mwu_p": "", "clifffs_delta": "", "tested": 0, "note": note,
            })

    # --- descriptive scale-down cross-check (container_events) per arm -------
    for arm in ARMS:
        vals = [m["removal_latency_s"] for m in cells[arm]
                if m.get("removal_latency_s") is not None]
        if vals:
            summary.append({
                "pair": arm, "metric": "removal_latency_s",
                "n_a": len(vals), "n_b": "", "median_a": f"{_median(vals):.4g}",
                "median_b": "", "mwu_p": "", "clifffs_delta": "", "tested": 0,
                "note": "container_events first removal (joint cross-check)",
            })

    cols_out = ["pair", "metric", "n_a", "n_b", "median_a", "median_b",
                "mwu_p", "clifffs_delta", "tested", "note"]
    with open(args.output, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols_out, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summary)

    # console
    print("\nRQ1 v2 stats — pre-registered comparisons (n=5; effect-size, "
          "no alpha claim)")
    for row in summary:
        flag = " [TESTED]" if row["tested"] else ""
        print(f"  {row['metric']:<24} {row['pair']:<32} "
              f"n={row['n_a']}/{row['n_b']} "
              f"med {row['median_a']} vs {row['median_b']}"
              f"{'  MWU p=' + row['mwu_p'] if row['mwu_p'] else ''}"
              f"{'  d=' + row['clifffs_delta'] if row['clifffs_delta'] != '' else ''}"
              f"{flag}  [{row['note']}]")
    print(f"\n  C8 verdict (non-surge): {_c8_verdict(cells)}")
    n_tested = sum(r["tested"] for r in summary)
    print(f"  comparisons evaluated : {n_tested} (pre-registered primary pairs)")
    print(f"  wrote {args.output} ({len(summary)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
