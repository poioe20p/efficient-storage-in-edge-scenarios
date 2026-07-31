#!/usr/bin/env python3
"""rq2_relief_analysis.py — RQ2 relief-in-targeted-tier / time-to-recovery.

For each RQ2 ``scale_up`` decision row that actually spawned a node
(``selected_action`` = compute|storage), scans the same LAN's per-window
evidence series (the decision log) for the first subsequent window where the
targeted tier's ``score_norm`` falls back under its ``*_threshold``.

- ``recovered``: True if such a window exists before run end.
- ``recovery_delay_s``: action decision time -> that window's decision time.
- ``other_tier_high``: whether the non-targeted tier was still above its
  threshold at recovery (targeted relief).

Run-kind guard: only RQ2-arm runs are processed.

Usage:
    python3 docs/research_questions/v2/rq2/rq2_relief_analysis.py RUN_DIR [--csv OUT]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

_RQ2_ARMS = {"fixed_compute_first", "fixed_storage_first", "bottleneck_aware"}
_EPISODE_SUBSTR = "episode"


def _parse_env(path: str) -> dict[str, str]:
    out: dict[str, str] = {}
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def _load_decision_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        return [row for row in csv.DictReader(fh)]


def _load_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    out: list[dict] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def _episode_info(run_dir: str, min_start: float) -> tuple[str | None, float, float]:
    snap_path = os.path.join(run_dir, "phases_snapshot.json")
    if not os.path.exists(snap_path):
        return None, 0.0, 0.0
    with open(snap_path, "r", encoding="utf-8") as fh:
        phases = json.load(fh).get("phases", [])
    episode = None
    for ph in phases:
        if _EPISODE_SUBSTR in ph.get("name", ""):
            episode = ph
            break
    if episode is None:
        return None, 0.0, 0.0
    elapsed = 0.0
    for ph in phases:
        if ph is episode:
            break
        elapsed += float(ph.get("duration_s", 0))
    start = min_start + elapsed
    end = start + float(episode.get("duration_s", 0))
    return None, start, end


def _as_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _process_lan(run_dir: str, lan: int, eend: float) -> list[dict]:
    rows = [r for r in _load_decision_csv(os.path.join(run_dir, f"decision_log_lan{lan}.csv"))
            if r.get("action_type") == "scale_up"]
    wend = {w.get("window_id"): float(w.get("window_end", 0))
            for w in _load_jsonl(os.path.join(run_dir, f"window_log_lan{lan}.jsonl"))}
    # Sort by decision time (they are appended in order, but be defensive).
    rows.sort(key=lambda r: _as_float(r.get("ts")))
    out = []
    for i, r in enumerate(rows):
        sel = r.get("selected_action", "")
        if sel not in ("compute", "storage"):
            continue
        target = sel
        other = "storage" if target == "compute" else "compute"
        t_score_col = f"{target}_score_norm"
        t_thr_col = f"{target}_threshold"
        o_score_col = f"{other}_score_norm"
        o_thr_col = f"{other}_threshold"
        action_ts = _as_float(r.get("ts"))
        recovered = False
        recovery_delay_s = ""
        other_high = ""
        for later in rows[i + 1:]:
            # Only count recovery while the episode is still running — a score
            # drop after episode end reflects the demand drop, not the action.
            we = wend.get(later.get("window_id"))
            if we is None or we <= 0:
                continue  # unknown window_end (gap/truncation) — skip, not past-episode
            if eend and we > eend:
                break
            score = _as_float(later.get(t_score_col), -1.0)
            thr = _as_float(later.get(t_thr_col), -1.0)
            if score >= 0 and thr >= 0 and score < thr:
                recovered = True
                recovery_delay_s = _as_float(later.get("ts")) - action_ts
                other_high = _as_float(later.get(o_score_col), 0.0) >= _as_float(later.get(o_thr_col), 1.0)
                break
        out.append({
            "lan": lan,
            "window_id": r.get("window_id", ""),
            "action_ts": action_ts,
            "selected_action": sel,
            "rejected_action": r.get("rejected_action", ""),
            "recovered": 1 if recovered else 0,
            "recovery_delay_s": recovery_delay_s,
            "other_tier_high": int(other_high) if other_high != "" else "",
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir")
    ap.add_argument("--csv", default="", help="optional relief-table CSV output")
    args = ap.parse_args()

    env = _parse_env(os.path.join(args.run_dir, "controller_env_snapshot.env"))
    policy = env.get("SCALEUP_POLICY", "dual")
    if policy not in _RQ2_ARMS:
        print(f"[skip] {args.run_dir}: SCALEUP_POLICY={policy!r} — not an RQ2 run")
        return 0

    min_start = float("inf")
    for lan in (1, 2):
        for w in _load_jsonl(os.path.join(args.run_dir, f"window_log_lan{lan}.jsonl")):
            min_start = min(min_start, float(w.get("window_end", 0)))
    if min_start == float("inf"):
        print(f"[error] {args.run_dir}: no window logs found")
        return 1
    _, estart, eend = _episode_info(args.run_dir, min_start)
    if eend <= 0:
        print(f"[error] {args.run_dir}: no episode phase in phases_snapshot.json")
        return 1

    rows = _process_lan(args.run_dir, 1, eend) + _process_lan(args.run_dir, 2, eend)
    if not rows:
        print(f"[error] {args.run_dir}: no spawned scale_up actions found")
        return 1

    delays = [r["recovery_delay_s"] for r in rows if r["recovered"] and r["recovery_delay_s"] != ""]
    n_rec = sum(r["recovered"] for r in rows)
    print(f"RQ2 relief analysis — run {os.path.basename(args.run_dir)} (policy={policy})")
    print(f"  actions            : {len(rows)}")
    print(f"  recovered in-tier  : {n_rec}/{len(rows)}")
    if delays:
        print(f"  median recovery_s  : {sorted(delays)[len(delays)//2]:.1f}")

    if args.csv:
        cols = ["lan", "window_id", "action_ts", "selected_action", "rejected_action",
                "recovered", "recovery_delay_s", "other_tier_high"]
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        print(f"wrote {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
