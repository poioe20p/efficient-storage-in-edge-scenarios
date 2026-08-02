#!/usr/bin/env python3
"""rq2_bottleneck_validation.py — RQ2 induced-bottleneck validation.

Independent of the controller: reads the run's window logs (raw domain_summary
signals) and the phases snapshot, and checks that the induced episode produced
the intended bottleneck across all policy arms.

Ground truth = the episode phase name in ``phases_snapshot.json``
(``compute_bound_episode`` -> compute-bound; ``data_bound_episode`` ->
data-bound).

Run-kind guard: only processes runs whose ``controller_env_snapshot.env`` sets
``SCALEUP_POLICY`` to one of the three RQ2 arms (``dual``/absent runs are
skipped — those belong to RQ1/canonical analyzers).

Usage:
    python3 docs/research_questions/v2/rq2/rq2_bottleneck_validation.py RUN_DIR [--lan 1|2] [--csv OUT]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from statistics import median

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
    """Return (episode_label, episode_start_epoch, episode_end_epoch)."""
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


def _signals(window: dict) -> dict[str, float]:
    ds = window.get("domain_summary") or {}
    return {
        "proc_ms": float(ds.get("avg_time_proc_ms", 0.0)),
        "cpu_pct": float(ds.get("average_cpu_percent", 0.0)),
        "db_ms": float(ds.get("avg_time_db_ms", 0.0)),
        "storage_cpu_pct": float(ds.get("avg_storage_cpu_percent", 0.0)),
    }


def _validate_lan(run_dir: str, lan: int, episode_label: str,
                  estart: float, eend: float) -> dict | None:
    wlog = _load_jsonl(os.path.join(run_dir, f"window_log_lan{lan}.jsonl"))
    if not wlog:
        return None
    ep = [w for w in wlog
          if estart <= float(w.get("window_end", 0)) <= eend
          and w.get("domain_summary")]
    if not ep:
        return None
    # MEDIAN (not mean): the per-window db_ms signal is contaminated by a few
    # dynamic-server lifecycle/spawn-removal transients (the scale action's own
    # replica-sync cost), which can reach hundreds of ms and would dominate an
    # arithmetic mean. The median measures the SUSTAINED induced bottleneck and
    # is consistent with the platform's robust-percentile practice (RQ1).
    agg = {k: median(_signals(w)[k] for w in ep) for k in
           ("proc_ms", "cpu_pct", "db_ms", "storage_cpu_pct")}
    n = len(ep)
    # Verdict on the PRIMARY latency axis only. avg_time_proc_ms is pure
    # processing time (total - db, see aggregator.py), so proc-vs-db cleanly
    # separates compute-bound from data-bound pressure. The CPU axis is
    # reported as information only (a CPU-only compute episode that never
    # elevates T_proc is outside this proxy).
    if episode_label == "compute_bound":
        ok = agg["proc_ms"] >= agg["db_ms"]
    else:
        ok = agg["db_ms"] >= agg["proc_ms"]
    return {"lan": lan, "episode": episode_label, "n_windows": n, **agg,
            "verdict": "PASS" if ok else "FAIL"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dir")
    ap.add_argument("--lan", type=int, default=0, help="LAN to validate (0 = both)")
    ap.add_argument("--csv", default="", help="optional CSV output path")
    args = ap.parse_args()

    env = _parse_env(os.path.join(args.run_dir, "controller_env_snapshot.env"))
    policy = env.get("SCALEUP_POLICY", "dual")
    if policy not in _RQ2_ARMS:
        print(f"[skip] {args.run_dir}: SCALEUP_POLICY={policy!r} — not an RQ2 run")
        return 0

    # Earliest window_end across LAN logs = approximate run start.
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

    lans = (1, 2) if args.lan == 0 else (args.lan,)
    rows = []
    for lan in lans:
        row = _validate_lan(args.run_dir, lan, episode_label, estart, eend)
        if row:
            rows.append(row)

    if not rows:
        print(f"[error] {args.run_dir}: no episode windows with domain_summary found")
        return 1

    print(f"RQ2 bottleneck validation — run {os.path.basename(args.run_dir)} "
          f"(policy={policy}, episode={episode_label})")
    hdr = ("lan,episode,n_windows,proc_ms,cpu_pct,db_ms,storage_cpu_pct,verdict")
    print(hdr)
    for r in rows:
        print(f"{r['lan']},{r['episode']},{r['n_windows']},"
              f"{r['proc_ms']:.2f},{r['cpu_pct']:.2f},{r['db_ms']:.2f},"
              f"{r['storage_cpu_pct']:.2f},{r['verdict']}")

    if args.csv:
        with open(args.csv, "w", encoding="utf-8") as fh:
            fh.write(hdr + "\n")
            for r in rows:
                fh.write(f"{r['lan']},{r['episode']},{r['n_windows']},"
                         f"{r['proc_ms']:.2f},{r['cpu_pct']:.2f},{r['db_ms']:.2f},"
                         f"{r['storage_cpu_pct']:.2f},{r['verdict']}\n")
        print(f"wrote {args.csv}")

    bad = [r for r in rows if r["verdict"] != "PASS"]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
