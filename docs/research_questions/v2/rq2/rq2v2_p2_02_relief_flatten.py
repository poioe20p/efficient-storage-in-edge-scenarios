#!/usr/bin/env python3
"""rq2v2_p2_02_relief_flatten.py — RQ2 v2 secondary relief signal (score flattening).

For each RQ2 ``scale_up`` decision that actually spawned a node
(``selected_action`` = compute|storage), measures whether the targeted tier's
``score_norm`` **stops rising / plateaus** within ``RELIEF_FLATTEN_WINDOW_S``
(CLI ``--flatten-window-s``, default 120 s) after the action, in addition to
the existing below-threshold recovery measured by ``rq2_relief_analysis.py``.

- ``plateau_within_window``: 1 if, within the flatten window, the targeted
  tier's ``score_norm`` stops rising — a later window's score is at or below
  the action-window score (within a small tolerance), i.e. the upward
  trajectory is broken.
- ``recovered_below_threshold``: 1 if the targeted tier's ``score_norm`` falls
  back under its ``*_threshold`` at a later episode window (the existing
  relief signal; may occur after the flatten window).
- ``relief_signal`` = ``plateau_within_window`` OR ``recovered_below_threshold``.

Output: ``relief_flatten.csv`` (one row per spawned scale-up action) with
columns ``window_id, action_ts, selected_action, targeted_tier,
score_norm_at_action, score_norm_peak_after, plateau_within_window,
recovered_below_threshold, relief_signal``.

Robustness: a run with no spawned scale-up actions produces a header-only
``relief_flatten.csv`` and a printed notice — the tool does not fail.

Run-kind guard: only RQ2-arm runs are processed (matches the sibling RQ2
analyzers).

Usage:
    python3 docs/research_questions/v2/rq2/rq2v2_p2_02_relief_flatten.py RUN_DIR \
        [--output FILE] [--flatten-window-s 120]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

_RQ2_ARMS = {"fixed_compute_first", "fixed_storage_first", "bottleneck_aware"}
_EPISODE_SUBSTR = "episode"

# Plateau tolerance: a score is "stopped rising" once it stays at or below
# the action-window score within max(0.5% absolute, 1% relative).
_FLAT_EPS_ABS = 0.005
_FLAT_EPS_REL = 0.01


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


def _fmt(v) -> str:
    return "" if v is None else f"{v:.4f}"


def _within_episode(we: float, eend: float) -> bool:
    return we > 0 and (not eend or we <= eend)


def _peak_after(rows, i: int, target: str, action_ts: float, flatten_s: float,
                wend: dict, eend: float) -> float | None:
    """Max targeted-tier score_norm within [action_ts, action_ts+flatten_s]."""
    horizon = action_ts + flatten_s
    peak: float | None = None
    for later in rows[i + 1:]:
        we = wend.get(later.get("window_id"))
        if not _within_episode(we, eend):
            continue
        ts = _as_float(later.get("ts"))
        if ts > horizon:
            break
        score = _as_float(later.get(f"{target}_score_norm"), -1.0)
        if score >= 0:
            peak = score if peak is None else max(peak, score)
    return peak


def _plateau_within(rows, i: int, target: str, action_ts: float, flatten_s: float,
                    score_at: float, wend: dict, eend: float) -> bool:
    """True if the targeted score stops rising within the flatten window."""
    eps = max(_FLAT_EPS_ABS, _FLAT_EPS_REL * abs(score_at))
    horizon = action_ts + flatten_s
    for later in rows[i + 1:]:
        we = wend.get(later.get("window_id"))
        if not _within_episode(we, eend):
            continue
        ts = _as_float(later.get("ts"))
        if ts > horizon:
            break
        score = _as_float(later.get(f"{target}_score_norm"), -1.0)
        if score >= 0 and score <= score_at + eps:
            return True
    return False


def _recovered_later(rows, i: int, target: str, wend: dict, eend: float) -> int:
    """1 if the targeted score falls back under its threshold by episode end."""
    for later in rows[i + 1:]:
        we = wend.get(later.get("window_id"))
        if not _within_episode(we, eend):
            continue
        score = _as_float(later.get(f"{target}_score_norm"), -1.0)
        thr = _as_float(later.get(f"{target}_threshold"), -1.0)
        if score >= 0 and thr >= 0 and score < thr:
            return 1
    return 0


def _process_lan(run_dir: str, lan: int, eend: float, flatten_s: float) -> list[dict]:
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
        action_ts = _as_float(r.get("ts"))
        score_at = _as_float(r.get(f"{target}_score_norm"), -1.0)
        score_at = score_at if score_at >= 0 else None
        peak = _peak_after(rows, i, target, action_ts, flatten_s, wend, eend)
        plateau = _plateau_within(rows, i, target, action_ts, flatten_s,
                                  score_at if score_at is not None else 0.0,
                                  wend, eend) if score_at is not None else False
        recovered = _recovered_later(rows, i, target, wend, eend)
        out.append({
            "window_id": r.get("window_id", ""),
            "action_ts": _fmt(action_ts),
            "selected_action": sel,
            "targeted_tier": target,
            "score_norm_at_action": _fmt(score_at),
            "score_norm_peak_after": _fmt(peak),
            "plateau_within_window": int(plateau),
            "recovered_below_threshold": recovered,
            "relief_signal": int(plateau or bool(recovered)),
        })
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir")
    ap.add_argument("--output", default="",
                    help="relief-flatten CSV output (default: RUN_DIR/relief_flatten.csv)")
    ap.add_argument("--flatten-window-s", type=float, default=120.0,
                    help="seconds after the action to look for score flattening (default 120)")
    args = ap.parse_args()

    run_dir = args.run_dir
    env = _parse_env(os.path.join(run_dir, "controller_env_snapshot.env"))
    policy = env.get("SCALEUP_POLICY", "dual")
    if policy not in _RQ2_ARMS:
        print(f"[skip] {run_dir}: SCALEUP_POLICY={policy!r} — not an RQ2 run")
        return 0

    min_start = float("inf")
    for lan in (1, 2):
        for w in _load_jsonl(os.path.join(run_dir, f"window_log_lan{lan}.jsonl")):
            min_start = min(min_start, float(w.get("window_end", 0)))
    if min_start == float("inf"):
        print(f"[error] {run_dir}: no window logs found")
        return 1
    _, estart, eend = _episode_info(run_dir, min_start)
    if eend <= 0:
        print(f"[error] {run_dir}: no episode phase in phases_snapshot.json")
        return 1

    rows = _process_lan(run_dir, 1, eend, args.flatten_window_s) + \
        _process_lan(run_dir, 2, eend, args.flatten_window_s)

    out_path = args.output or os.path.join(run_dir, "relief_flatten.csv")
    cols = ["window_id", "action_ts", "selected_action", "targeted_tier",
            "score_norm_at_action", "score_norm_peak_after",
            "plateau_within_window", "recovered_below_threshold", "relief_signal"]
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)

    print(f"RQ2 relief-flatten analysis — run {os.path.basename(run_dir)} "
          f"(policy={policy}, flatten_window={args.flatten_window_s:.0f}s)")
    print(f"  actions              : {len(rows)}")
    if rows:
        n_plateau = sum(r["plateau_within_window"] for r in rows)
        n_rec = sum(r["recovered_below_threshold"] for r in rows)
        n_relief = sum(r["relief_signal"] for r in rows)
        print(f"  plateau within window: {n_plateau}/{len(rows)}")
        print(f"  recovered below thr  : {n_rec}/{len(rows)}")
        print(f"  relief signal (either): {n_relief}/{len(rows)}")
    else:
        print("  notice: no spawned scale_up actions found — header-only output "
              "written, no failure")
    print(f"  wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
