#!/usr/bin/env python3
"""rq2_node_minutes.py — RQ2 compute/storage node-minutes per run.

Counts actual spawns only (decision rows with ``action_type="scale_up"`` and
``selected_action == tier``) and pairs each spawn to its removal in LIFO order
(matching the candidate-based removal of the controller):

- ``scale_down`` rows with ``action`` = ``compute``/``storage`` terminate the
  most recent unpaired spawn of that tier.
- tier-ambiguous removal rows (``absent``/``absent_cleanup``/``reserve_loss``)
  terminate the most recent unpaired spawn across both tiers (documented
  approximation — the decision log does not record the tier for those rows).
- a node never removed lives until run end (max decision-log ts).

Node-minutes = Σ(spawn lifetime in minutes) per tier, optionally normalised per
unit of completed demand from ``client_requests.csv``.

Run-kind guard: only RQ2-arm runs are processed.

Usage:
    python3 docs/research_questions/v2/rq2/rq2_node_minutes.py RUN_DIR [--csv OUT]
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys

_RQ2_ARMS = {"fixed_compute_first", "fixed_storage_first", "bottleneck_aware"}
_TIER_REMOVALS = {"compute", "storage"}
# Tier-ambiguous removal rows carry no tier in the decision log and terminate
# nothing (plan T7); their nodes are accounted as live-until-run-end.
_AMBIG_REMOVALS = {"absent", "absent_cleanup", "reserve_loss"}


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


def _as_float(v, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _completed_demand(run_dir: str) -> float | None:
    path = os.path.join(run_dir, "client_requests.csv")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        # Skip header; each data row is one request.
        return max(0, sum(1 for _ in fh) - 1)


def _process_lan(run_dir: str, lan: int, run_end: float) -> dict[str, float]:
    rows = _load_decision_csv(os.path.join(run_dir, f"decision_log_lan{lan}.csv"))
    # Dedup by (window_id, action_type) — robust to controller restarts.
    seen = set()
    deduped = []
    for r in rows:
        key = (r.get("window_id"), r.get("action_type"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(r)
    rows = deduped
    spawns = [(r.get("selected_action"), _as_float(r.get("ts")))
              for r in rows
              if r.get("action_type") == "scale_up"
              and r.get("selected_action") in ("compute", "storage")]
    removals = [(r.get("action"), _as_float(r.get("ts")))
                for r in rows if r.get("action_type") == "scale_down"]
    events = [("spawn", *s) for s in spawns] + [("removal", *r) for r in removals]
    events.sort(key=lambda e: e[2])

    stacks: dict[str, list[float]] = {"compute": [], "storage": []}
    node_minutes: dict[str, float] = {"compute": 0.0, "storage": 0.0}

    for kind, payload, ts in events:
        if kind == "spawn":
            stacks[payload].append(ts)
            continue
        # Removal
        if payload in _TIER_REMOVALS:
            tier = payload
            if stacks[tier]:
                node_minutes[tier] += (ts - stacks[tier].pop()) / 60.0
        elif payload in _AMBIG_REMOVALS:
            # Tier-ambiguous (no tier in the decision log) — terminates nothing
            # (plan T7); that node is accounted as live-until-run-end below.
            continue

    # Unremoved nodes live until run end.
    for tier, stack in stacks.items():
        for spawn_ts in stack:
            node_minutes[tier] += (run_end - spawn_ts) / 60.0

    return node_minutes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir")
    ap.add_argument("--csv", default="", help="optional node-minutes CSV output")
    args = ap.parse_args()

    env = _parse_env(os.path.join(args.run_dir, "controller_env_snapshot.env"))
    policy = env.get("SCALEUP_POLICY", "dual")
    if policy not in _RQ2_ARMS:
        print(f"[skip] {args.run_dir}: SCALEUP_POLICY={policy!r} — not an RQ2 run")
        return 0

    # Run end = max decision-log ts AND max window_end across both LANs (a run
    # whose last decision is early must not truncate never-removed node lives).
    run_end = float("-inf")
    all_rows = []
    for lan in (1, 2):
        rows = _load_decision_csv(os.path.join(args.run_dir, f"decision_log_lan{lan}.csv"))
        all_rows.append(rows)
        for r in rows:
            run_end = max(run_end, _as_float(r.get("ts")))
        for w in _load_jsonl(os.path.join(args.run_dir, f"window_log_lan{lan}.jsonl")):
            run_end = max(run_end, _as_float(w.get("window_end")))
    if run_end == float("-inf"):
        print(f"[error] {args.run_dir}: no decision log rows found")
        return 1

    total = {"compute": 0.0, "storage": 0.0}
    out_rows = []
    for lan, rows in ((1, all_rows[0]), (2, all_rows[1])):
        if not rows:
            continue
        nm = _process_lan(args.run_dir, lan, run_end)
        for tier in ("compute", "storage"):
            total[tier] += nm[tier]
            out_rows.append({"lan": lan, "tier": tier, "node_minutes": round(nm[tier], 3)})

    demand = _completed_demand(args.run_dir)
    print(f"RQ2 node-minutes — run {os.path.basename(args.run_dir)} (policy={policy})")
    print(f"  compute node-minutes : {total['compute']:.2f}")
    print(f"  storage node-minutes : {total['storage']:.2f}")
    if demand:
        print(f"  per 1000 recorded req: compute={total['compute'] / demand * 1000:.3f} "
              f"storage={total['storage'] / demand * 1000:.3f} "
              f"(recorded_requests={demand}; includes failures — refine with a "
              f"status column when the schema is known)")
    else:
        print("  (client_requests.csv absent — raw node-minutes only)")

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["lan", "tier", "node_minutes"])
            writer.writeheader()
            writer.writerows(out_rows)
        print(f"wrote {args.csv}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
