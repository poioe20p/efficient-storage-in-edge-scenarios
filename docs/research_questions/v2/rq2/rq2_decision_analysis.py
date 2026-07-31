#!/usr/bin/env python3
"""rq2_decision_analysis.py — RQ2 per-run decision/action table.

Filters the RQ2 ``scale_up`` decision rows from both LAN decision logs, joins
each row's ``window_id`` to the window log for ``window_end`` (info-age at
decision), attaches the induced episode label from ``phases_snapshot.json``
(post-hoc, D5), and emits per-run statistics:

- per-window decision rows (evidence, selected/rejected, bottleneck_class,
  budget, reason), deduplicated by (window_id, action_type);
- per-tier scale-up action counts and max budget used per LAN (D4);
- classifier-vs-episode agreement over EPISODE windows where BOTH tiers were
  eligible (excludes cooldown/eligibility-contaminated windows and "n/a");
- the T9.8 fire-keyed scale-down protection check (no cooldown-gated scale-down
  within SCALEDOWN_*_COOLDOWN_S after a *_fired=1 window);
- the counterbalance matrix cell (policy × episode; this run = one replicate).

Run-kind guard: only RQ2-arm runs are processed.

Usage:
    python3 docs/research_questions/v2/rq2/rq2_decision_analysis.py RUN_DIR [--csv OUT]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

_RQ2_ARMS = {"fixed_compute_first", "fixed_storage_first", "bottleneck_aware"}
_EPISODE_SUBSTR = "episode"
_DEFAULT_SCALEDOWN_COOLDOWN_S = {"compute": 40.0, "storage": 120.0}


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


def _load_decision_csv(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        return [row for row in reader]


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
    label = "compute_bound" if "compute" in episode.get("name", "") else "data_bound"
    return label, start, end


def _as_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _as_int(v, default: int = 0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _process_lan(run_dir: str, lan: int) -> list[dict]:
    rows = _load_decision_csv(os.path.join(run_dir, f"decision_log_lan{lan}.csv"))
    wlog = _load_jsonl(os.path.join(run_dir, f"window_log_lan{lan}.jsonl"))
    wend = {w.get("window_id"): float(w.get("window_end", 0)) for w in wlog}
    out = []
    for r in rows:
        if r.get("action_type") != "scale_up":
            continue
        ts = _as_float(r.get("ts"))
        wid = r.get("window_id", "")
        we = wend.get(wid, 0.0)
        out.append({
            "lan": lan,
            "window_id": wid,
            "decision_ts": ts,
            "window_end": we,
            "info_age_s": (ts - we) if we else "",
            "compute_score_norm": r.get("compute_score_norm", ""),
            "storage_score_norm": r.get("storage_score_norm", ""),
            "compute_threshold": r.get("compute_threshold", ""),
            "storage_threshold": r.get("storage_threshold", ""),
            "bottleneck_class": r.get("bottleneck_class", ""),
            "selected_action": r.get("selected_action", ""),
            "rejected_action": r.get("rejected_action", ""),
            "reason": r.get("reason", ""),
            "compute_fired": _as_int(r.get("compute_fired")),
            "storage_fired": _as_int(r.get("storage_fired")),
            "compute_eligible": _as_int(r.get("compute_eligible")),
            "storage_eligible": _as_int(r.get("storage_eligible")),
            "compute_budget_used": _as_int(r.get("compute_budget_used")),
            "storage_budget_used": _as_int(r.get("storage_budget_used")),
        })
    return out


def _scale_down_protection_violations(run_dir: str, lan: int,
                                      cooldowns: dict[str, float]) -> list[str]:
    """T9.8: no cooldown-gated scale-down within cooldown after a fired window."""
    rows = _load_decision_csv(os.path.join(run_dir, f"decision_log_lan{lan}.csv"))
    scale_ups = [r for r in rows if r.get("action_type") == "scale_up"]
    scale_downs = [r for r in rows
                   if r.get("action_type") == "scale_down"
                   and r.get("action") in ("compute", "storage")]
    violations = []
    for su in scale_ups:
        t = _as_float(su.get("ts"))
        for tier in ("compute", "storage"):
            if not _as_int(su.get(f"{tier}_fired")):
                continue
            cd = cooldowns[tier]
            for sd in scale_downs:
                if sd.get("action") != tier:
                    continue
                st = _as_float(sd.get("ts"))
                if 0 < st - t < cd:
                    violations.append(
                        f"lan{lan}: {tier} scale-down at {st:.1f}s within "
                        f"{cd:.0f}s cooldown after fired window {su.get('window_id')}")
                    break
    return violations


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir")
    ap.add_argument("--csv", default="", help="optional decision-table CSV output")
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

    episode_label, estart, eend = _episode_info(args.run_dir, min_start)
    if episode_label is None:
        print(f"[error] {args.run_dir}: no episode phase in phases_snapshot.json")
        return 1

    rows = _process_lan(args.run_dir, 1) + _process_lan(args.run_dir, 2)
    if not rows:
        print(f"[error] {args.run_dir}: no scale_up decision rows found")
        return 1

    # Dedup the RQ2 universe by (window_id, action_type) — robust to restarts.
    seen = set()
    dedup = []
    for r in rows:
        key = (r["window_id"], "scale_up")
        if key in seen:
            continue
        seen.add(key)
        dedup.append(r)
    rows = dedup

    cooldowns = {
        "compute": _as_float(env.get("SCALEDOWN_COMPUTE_COOLDOWN_S"),
                             _DEFAULT_SCALEDOWN_COOLDOWN_S["compute"]),
        "storage": _as_float(env.get("SCALEDOWN_STORAGE_COOLDOWN_S"),
                              _DEFAULT_SCALEDOWN_COOLDOWN_S["storage"]),
    }

    # Per-tier action counts (actual spawns) + max budget used per LAN (D4).
    counts = {"compute": 0, "storage": 0}
    budget_by_lan = {lan: {"compute": 0, "storage": 0} for lan in (1, 2)}
    for r in rows:
        if r["selected_action"] in counts:
            counts[r["selected_action"]] += 1
        budget_by_lan[r["lan"]]["compute"] = max(budget_by_lan[r["lan"]]["compute"],
                                                   r["compute_budget_used"])
        budget_by_lan[r["lan"]]["storage"] = max(budget_by_lan[r["lan"]]["storage"],
                                                    r["storage_budget_used"])

    # Classifier-vs-episode agreement over episode windows where BOTH tiers were
    # eligible (excludes eligibility/cooldown-contaminated windows and "n/a").
    expected = "compute" if episode_label == "compute_bound" else "storage"
    ep_rows = [r for r in rows
               if estart <= r["window_end"] <= eend
               and r["compute_eligible"] and r["storage_eligible"]
               and r["bottleneck_class"] in ("compute", "storage")]
    agree = sum(1 for r in ep_rows if r["bottleneck_class"] == expected)
    ep_n = len(ep_rows)

    # T9.8 fire-keyed scale-down protection.
    violations = []
    for lan in (1, 2):
        violations += _scale_down_protection_violations(args.run_dir, lan, cooldowns)

    print(f"RQ2 decision analysis — run {os.path.basename(args.run_dir)} "
          f"(policy={policy}, episode={episode_label})")
    print(f"  scale_up rows (deduped)     : {len(rows)}")
    print(f"  action counts               : compute={counts['compute']} storage={counts['storage']}")
    print(f"  budget used per LAN (max)   : "
          f"lan1 c={budget_by_lan[1]['compute']} s={budget_by_lan[1]['storage']}; "
          f"lan2 c={budget_by_lan[2]['compute']} s={budget_by_lan[2]['storage']}")
    if ep_n:
        agree_pct = f"{agree}/{ep_n} ({(agree / ep_n * 100):.1f}%)"
    else:
        agree_pct = "n/a (no both-eligible episode windows)"
    print(f"  classifier-vs-episode agree : {agree_pct}")
    print(f"  T9.8 fire-keyed scale-down  : {'OK' if not violations else 'VIOLATIONS=' + str(len(violations))}")
    for v in violations[:10]:
        print(f"    - {v}")
    print(f"  counterbalance cell         : policy={policy}, episode={episode_label}, "
          f"replicate={os.path.basename(args.run_dir)}")

    if args.csv:
        cols = ["lan", "window_id", "decision_ts", "window_end", "info_age_s",
                "compute_score_norm", "storage_score_norm",
                "compute_threshold", "storage_threshold",
                "compute_fired", "storage_fired",
                "compute_eligible", "storage_eligible",
                "bottleneck_class", "selected_action", "rejected_action", "reason",
                "compute_budget_used", "storage_budget_used"]
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        print(f"wrote {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
