#!/usr/bin/env python3
"""RQ1 delivery-semantics — per-run analyzer.

Consumes the four RQ1 artifacts (window log, delivery log, decision log, ack
log) plus the standard run artifacts and emits a per-run metrics bundle under
``<run_dir>/analysis/rq1_delivery/``:

  delivery_integrity.csv       per-LAN completeness + missed-overload summary
  delivery_delay.csv           per delivered window: delay_s, phase, mode
  info_age.csv                 per decision: information age at decision
  overload_observability.csv   per overload window (+ episode_id)
  overload_episodes.csv        per overload episode visibility summary
  reaction_timeline.csv        per phase per LAN: demand-shift -> decision/capacity
  phase_service_quality.csv    per phase per LAN: p50/p95/p99, failure, completed
  overhead.csv                 per controller container: CPU% + RSS
  run_meta.csv                 arm / bounds / phase-derived provenance

Implements the analysis rules in
``docs/operation/testing/experiment/v2/rq1/analysis_focus.md`` §2b
(universe bounds, phase anchoring, overload-episode definition) and honors the
delivery-log row conventions in ``delivery_log.py``.

Usage:
  python rq1_delivery_per_run.py <run_dir>
"""

import argparse
import csv
import json
import math
import os
import re
import sys
from datetime import datetime, timezone

LAN_IDS = ("lan1", "lan2")
DEFAULT_WINDOW_S = 10
DEFAULT_DELAY_S = 30

# Dynamic compute containers spawned by the elasticity manager, e.g.
# edge_server_lan1_dyn3 (see compute_node_manager.py). Group 1 captures the LAN.
DYN_COMPUTE_RE = re.compile(r"^edge_server_lan(\d+)_dyn\d+$", re.IGNORECASE)

DECISION_ACTION_TYPES = ("scale_up", "scale_down")
# Scale-down actions that reflect the demand drop (cooldown-gated compute/
# storage), excluding housekeeping actions (absent / reserve_loss).
SCALE_DOWN_ACTIONS = ("compute", "storage")

# Mapping container -> LAN for controller overhead.
CONTAINER_TO_LAN = {"osken": "lan1", "osken_2": "lan2"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _iso_to_epoch(value):
    """Parse an ISO-8601 UTC timestamp or a float epoch into epoch seconds."""
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


def _read_env_snapshot(path):
    """Return {KEY: value} parsed from a run's *env_snapshot.env file."""
    out = {}
    if not path or not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            out[key.strip()] = val.strip()
    return out


def _load_jsonl(path):
    recs = []
    malformed = 0
    if not os.path.exists(path):
        return recs, malformed
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except json.JSONDecodeError:
                malformed += 1
    return recs, malformed


def _load_csv(path):
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)
    return rows


def _write_csv(path, fieldnames, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _fnum(value, default=None):
    """Best-effort finite-float parse returning ``default`` (None) on failure."""
    if value is None:
        return default
    s = str(value).strip()
    if not s:
        return default
    try:
        f = float(s)
    except ValueError:
        return default
    if not math.isfinite(f):
        return default
    return f


def _percentiles(values, ps=(50, 95, 99)):
    """Nearest-rank percentiles of a list."""
    if not values:
        return {p: None for p in ps}
    vals = sorted(values)
    out = {}
    for p in ps:
        k = max(1, math.ceil(len(vals) * p / 100.0))
        out[p] = vals[min(k - 1, len(vals) - 1)]
    return out


def _env_int(env, keys, default):
    """First present key in ``keys`` parsed as int, else ``default``."""
    for key in keys:
        if key in env:
            try:
                return int(float(env[key]))
            except (TypeError, ValueError):
                continue
    return default


def _fmt(ts):
    return f"{ts:.3f}" if ts is not None else ""


def _phase_of(window_end, phases):
    """Return the name of the phase whose [start, end) contains window_end."""
    for name, start, end in phases:
        if start <= window_end < end:
            return name
    return "transition"


# ---------------------------------------------------------------------------
# Per-LAN analysis
# ---------------------------------------------------------------------------

def analyze_lan(lan, run_dir, window_s, delay_s, arm, traffic_bounds,
                phase_times, lan_capacity_epochs):
    """Compute per-LAN RQ1 metrics; returns a dict of output row groups.

    ``phase_times`` is a list of (name, start, end) derived in main().
    ``lan_capacity_epochs`` is this LAN's sorted list of dynamic-compute
    running timestamps (wall-clock epoch) used for usable-capacity detection.
    """
    window_log, malformed = _load_jsonl(
        os.path.join(run_dir, f"window_log_{lan}.jsonl"))
    if malformed:
        sys.stderr.write(f"[warn] {lan}: {malformed} malformed window-log "
                         f"line(s) skipped.\n")
    delivery_rows = _load_csv(
        os.path.join(run_dir, f"telemetry_delivery_log_{lan}.csv"))
    decision_rows = _load_csv(
        os.path.join(run_dir, f"decision_log_{lan}.csv"))
    ack_recs, ack_malformed = _load_jsonl(
        os.path.join(run_dir, f"ack_log_{lan}.jsonl"))
    if ack_malformed:
        sys.stderr.write(f"[warn] {lan}: {ack_malformed} malformed ack-log "
                         f"line(s) skipped (ack_count may undercount).\n")

    lo, hi = traffic_bounds

    # Universe (bounded to the active traffic window).
    universe = []
    for w in window_log:
        we = _fnum(w.get("window_end"))
        if we is None or we < lo or we > hi:
            continue
        universe.append(w)

    def wid(w):
        return w.get("window_id") or ""

    universe_by_id = {wid(w): w for w in universe if wid(w)}
    universe_last_end = max((_fnum(w.get("window_end"), 0.0) for w in universe),
                            default=0.0)

    # Delivered windows (dedup by window_id; only rows with a non-empty id).
    delivered_by_id = {}
    for r in delivery_rows:
        rid = (r.get("window_id") or "").strip()
        if not rid:
            continue
        delivered_by_id.setdefault(rid, r)

    # Gap / processing-error rows (window_id empty).
    gap_recovery = sum(
        1 for r in delivery_rows
        if not (r.get("window_id") or "").strip()
        and (r.get("mode") or "").strip() == "gap_recovery")
    processing_error = sum(
        1 for r in delivery_rows
        if not (r.get("window_id") or "").strip()
        and (r.get("mode") or "").strip() == "processing_error")

    delivered_ids = set(delivered_by_id) & set(universe_by_id)
    delivered_count = len(delivered_ids)
    universe_count = len(universe)

    # in-delay-at-run-end: arm B only — not delivered AND released after run end.
    in_delay_ids = set()
    if arm == "delayed":
        for w in universe:
            we = _fnum(w.get("window_end"))
            if wid(w) not in delivered_ids and we is not None \
                    and we + delay_s > universe_last_end:
                in_delay_ids.add(wid(w))
    in_delay_count = len(in_delay_ids)

    overload_total = sum(1 for w in universe if bool(w.get("overload")))
    overload_delivered = sum(
        1 for w in universe if bool(w.get("overload")) and wid(w) in delivered_ids)
    overload_in_delay = sum(
        1 for w in universe if bool(w.get("overload")) and wid(w) in in_delay_ids)
    overload_missed = overload_total - overload_delivered - overload_in_delay

    delivered_frac = (delivered_count / universe_count) if universe_count else None

    # --- delivery_delay rows (per delivered window) ---
    delay_rows = []
    for rid in sorted(delivered_ids):
        row = delivered_by_id[rid]
        w = universe_by_id[rid]
        we = _fnum(w.get("window_end"), 0.0)
        dt = _fnum(row.get("delivery_ts"), we)
        delay_rows.append({
            "network_id": lan,
            "window_id": rid,
            "window_end": f"{we:.3f}",
            "delivery_ts": f"{dt:.3f}",
            "delay_s": f"{max(0.0, dt - we):.3f}",
            "release_ts": (row.get("release_ts") or ""),
            "mode": (row.get("mode") or arm),
            "phase": _phase_of(we, phase_times),
        })

    # --- info_age rows (per decision joinable to a universe window) ---
    info_rows = []
    for r in decision_rows:
        rid = (r.get("window_id") or "").strip()
        if not rid or rid not in universe_by_id:
            continue
        ts = _fnum(r.get("ts"))
        we = _fnum(universe_by_id[rid].get("window_end"))
        if ts is None or we is None:
            continue
        info_rows.append({
            "ts": f"{ts:.3f}",
            "window_id": rid,
            "window_end": f"{we:.3f}",
            "info_age_s": f"{max(0.0, ts - we):.3f}",
            "action_type": (r.get("action_type") or ""),
            "action": (r.get("action") or ""),
        })

    # First decision per window (scale actions only).
    first_decision = {}
    for r in decision_rows:
        rid = (r.get("window_id") or "").strip()
        atype = (r.get("action_type") or "").strip()
        if not rid or atype not in DECISION_ACTION_TYPES:
            continue
        ts = _fnum(r.get("ts"))
        if ts is None:
            continue
        if rid not in first_decision or ts < first_decision[rid][0]:
            first_decision[rid] = (ts, atype, r.get("action") or "")

    # --- overload observability (per overload window + episodes) ---
    overload_windows = sorted(
        (w for w in universe if bool(w.get("overload"))),
        key=lambda w: _fnum(w.get("window_end"), 0.0))

    obs_rows = []
    ep_rows = []
    episode_id = 0
    prev_seq = None
    episodes = {}

    for w in overload_windows:
        seq = w.get("window_seq")
        # Episode rule (§2b): consecutive overload windows with at most one
        # intervening non-overload window share an episode (seq diff <= 2).
        if prev_seq is None or not isinstance(seq, int) \
                or not isinstance(prev_seq, int) or (seq - prev_seq) > 2:
            episode_id += 1
        episodes.setdefault(episode_id, []).append(w)
        prev_seq = seq

        rid = wid(w)
        delivered = rid in delivered_ids
        fd = first_decision.get(rid)
        obs_rows.append({
            "window_id": rid,
            "window_end": _fmt(_fnum(w.get("window_end"), 0.0)),
            "overload": "1",
            "delivered": "1" if delivered else "0",
            "episode_id": episode_id,
            "first_decision_ts": _fmt(fd[0] if fd else None),
            "detection_delay_s": _fmt(max(0.0, fd[0] - _fnum(w.get("window_end"), 0.0))
                                      if fd else None),
            "acted": "1" if fd else "0",
        })

    # Episodes: also count delivered windows within one WINDOW_S of the episode
    # as evidence (§2b "or within one WINDOW_S of it").
    for eid, wins in episodes.items():
        ep_min = min(_fnum(w.get("window_end"), 0.0) for w in wins)
        ep_max = max(_fnum(w.get("window_end"), 0.0) for w in wins)
        ep_wids = {wid(w) for w in wins}
        evidence_wids = ep_wids | {
            wid(w2) for w2 in universe_by_id.values()
            if (_fnum(w2.get("window_end"), 0.0) >= ep_min - window_s)
            and (_fnum(w2.get("window_end"), 0.0) <= ep_max + window_s)
        }
        delivered_any = any(wid(w) in delivered_ids for w in wins)
        visible = any(
            wid(w) in first_decision and wid(w) in delivered_ids
            for w in universe_by_id.values() if wid(w) in evidence_wids)
        fd_ts = min((first_decision[wid(w)][0] for w in wins
                     if wid(w) in first_decision), default=None)
        ep_rows.append({
            "episode_id": eid,
            "n_windows": len(wins),
            "window_ids": ";".join(wid(w) for w in wins),
            "delivered_any": "1" if delivered_any else "0",
            "visible": "1" if visible else "0",
            "first_decision_ts": _fmt(fd_ts),
        })

    # --- reaction timeline (per phase) ---
    scale_up_ts = [_fnum(r.get("ts")) for r in decision_rows
                   if (r.get("action_type") or "").strip() == "scale_up"]
    scale_up_ts = [t for t in scale_up_ts if t is not None]
    # Scale-down: only the cooldown-gated compute/storage actions reflect the
    # demand drop; housekeeping (absent / reserve_loss) is excluded.
    scale_down_ts = [_fnum(r.get("ts")) for r in decision_rows
                     if (r.get("action_type") or "").strip() == "scale_down"
                     and (r.get("action") or "").strip() in SCALE_DOWN_ACTIONS]
    scale_down_ts = [t for t in scale_down_ts if t is not None]

    # Post-plateau scale-down anchor (control-group rebase 2026-08-01): the
    # demand decrease is the end of the overload phase, which equals
    # recovery_gap start. The first cooldown-gated scale-down after the plateau
    # may land in recovery_gap (arms A/B) or demand_drop (arm C, poll-30); the
    # latency is measured from recovery_gap start uniformly across arms.
    post_plateau_start = None
    for _nm, _st, _en in phase_times:
        if _nm == "recovery_gap":
            post_plateau_start = _st
            break
    down_first_post = (min((t for t in scale_down_ts
                            if t >= post_plateau_start), default=None)
                       if post_plateau_start is not None else None)

    timeline = []
    for name, start, end in phase_times:
        up_first = min((t for t in scale_up_ts if t >= start), default=None)
        down_first = min((t for t in scale_down_ts if t >= start), default=None)
        # Usable capacity is the scale-up (demand-shift) metric: meaningful only
        # in the overload phase (compute_plateau), per LAN.
        cap_first = (min((t for t in lan_capacity_epochs if t >= start),
                         default=None) if name == "compute_plateau" else None)
        timeline.append({
            "phase": name,
            "network_id": lan,
            "phase_start": _fmt(start),
            "scale_up_first_ts": _fmt(up_first),
            "scale_down_first_ts": _fmt(down_first),
            "usable_capacity_ts": _fmt(cap_first),
            "decision_latency_s": (_fmt(up_first - start)
                                   if name == "compute_plateau" and up_first
                                   else ""),
            "capacity_latency_s": (_fmt(cap_first - start)
                                   if name == "compute_plateau" and cap_first
                                   else ""),
            # Carried on the recovery_gap row only (post-plateau anchor).
            "scale_down_latency_s": (_fmt(down_first_post - start)
                                     if name == "recovery_gap"
                                     and down_first_post is not None
                                     else ""),
        })

    return {
        "integrity": {
            "network_id": lan,
            "arm": arm,
            "universe": universe_count,
            "delivered": delivered_count,
            "delivered_frac": (f"{delivered_frac:.4f}"
                               if delivered_frac is not None else ""),
            "overload_total": overload_total,
            "overload_delivered": overload_delivered,
            "overload_missed": overload_missed,
            "in_delay_at_end": in_delay_count,
            "gap_recovery": gap_recovery,
            "processing_error": processing_error,
            "ack_count": len(ack_recs),
        },
        "delay_rows": delay_rows,
        "info_rows": info_rows,
        "obs_rows": obs_rows,
        "ep_rows": ep_rows,
        "timeline": timeline,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

REQUIRED_ARTIFACTS = []
for _lan in LAN_IDS:
    REQUIRED_ARTIFACTS += [
        f"window_log_{_lan}.jsonl",
        f"telemetry_delivery_log_{_lan}.csv",
        f"decision_log_{_lan}.csv",
    ]


def main():
    parser = argparse.ArgumentParser(
        description="RQ1 delivery-semantics per-run analyzer.")
    parser.add_argument("run_dir", help="Run folder (metrics/<timestamp>_<label>).")
    parser.add_argument("--skip-phase-validation", action="store_true",
                        help="Skip the generator-phase vs anchored-boundary "
                             "check (use only for legacy v1 folders with the "
                             "known plateau overrun; v2 runs must validate).")
    args = parser.parse_args()

    run_dir = os.path.abspath(args.run_dir)
    if not os.path.isdir(run_dir):
        sys.stderr.write(f"ERROR: run folder not found: {run_dir}\n")
        return 2

    missing = [name for name in REQUIRED_ARTIFACTS
               if not os.path.exists(os.path.join(run_dir, name))]
    if missing:
        sys.stderr.write("ERROR: missing required RQ1 artifact(s): "
                         + ", ".join(missing) + "\n")
        return 1

    out_dir = os.path.join(run_dir, "analysis", "rq1_delivery")

    controller_env_path = os.path.join(run_dir, "controller_env_snapshot.env")
    if not os.path.exists(controller_env_path):
        sys.stderr.write("ERROR: controller_env_snapshot.env not found — "
                         "required for arm/delay provenance.\n")
        return 1
    controller_env = _read_env_snapshot(controller_env_path)
    aggregator_env = _read_env_snapshot(
        os.path.join(run_dir, "aggregator_env_snapshot.env"))

    arm = (controller_env.get("TELEMETRY_SOURCE") or "unknown").strip()
    arm_short = {"event_preserving": "ep", "delayed_event_preserving": "delayed",
                 "poll": "ls", "sampled_push": "sp", "zmq": "zmq"}.get(arm, arm)
    # The aggregator snapshot uses per-container keys (WINDOW_S_n1 / WINDOW_S_n2).
    window_s = _env_int(aggregator_env,
                        ("WINDOW_S", "WINDOW_S_n1", "WINDOW_S_n2"),
                        _env_int(controller_env, ("WINDOW_S",),
                                 DEFAULT_WINDOW_S))
    delay_s = _env_int(controller_env, ("DELAY_S",), DEFAULT_DELAY_S)

    # --- client-driven traffic bounds + phase anchoring (§2b) ---
    req_path = os.path.join(run_dir, "client_requests.csv")
    if not os.path.exists(req_path):
        sys.stderr.write("ERROR: client_requests.csv not found — cannot bound "
                         "the universe.\n")
        return 1
    sent = [t for t in (_iso_to_epoch(r.get("sent_at"))
                        for r in _load_csv(req_path)) if t is not None]
    if not sent:
        sys.stderr.write("ERROR: client_requests.csv has no valid sent_at "
                         "timestamps.\n")
        return 1
    traffic_start = (min(sent) // window_s) * window_s
    traffic_end = -(-max(sent) // window_s) * window_s  # ceiling

    phases_path = os.path.join(run_dir, "phases_snapshot.json")
    if not os.path.exists(phases_path):
        sys.stderr.write("ERROR: phases_snapshot.json not found — cannot derive "
                         "phase boundaries.\n")
        return 1
    with open(phases_path, "r", encoding="utf-8") as fh:
        phases_cfg = json.load(fh).get("phases", [])

    phase_times = []
    acc = traffic_start
    for p in phases_cfg:
        start = acc
        end = acc + float(p.get("duration_s", 0))
        phase_times.append((p.get("name", "phase"), start, end))
        acc = end

    # --- request rows (status + generator phase label) + phase derivation ---
    req_rows = _load_csv(req_path)
    has_status = bool(req_rows) and "status" in req_rows[0]
    has_phase_label = bool(req_rows) and any(
        (r.get("phase") or "").strip() for r in req_rows)
    known_phases = [p[0] for p in phase_times]

    # Open-loop schedule provenance (drain/window) — additive keys written by
    # the supervisor; absent on legacy sync runs.
    drain_s = 0.0
    sched_path = os.path.join(run_dir, "open_loop_schedule.json")
    if os.path.exists(sched_path):
        try:
            with open(sched_path, "r", encoding="utf-8") as fh:
                drain_s = float(json.load(fh).get("drain_s", 0.0) or 0.0)
        except (ValueError, OSError):
            drain_s = 0.0

    if has_phase_label:
        # RQ1 v2 rule (§2.3): phase boundaries are DERIVED from the generator
        # `phase` label — the authoritative record of what the driver actually
        # executed. The open-loop supervisor dispatches each phase for its
        # nominal duration but shifts every later phase by the phase-boundary
        # drains, so contiguous anchoring is wrong whenever a drain actually
        # delays dispatch. Workers also progress through phases independently
        # (per-worker drain durations differ), so per-phase label ranges can
        # overlap across workers; only phase ORDER is globally monotonic.
        label_times = {}
        for name in known_phases:
            ts = [t for t in (_iso_to_epoch(r.get("sent_at")) for r in req_rows
                              if (r.get("phase") or "").strip() == name)
                  if t is not None]
            if ts:
                label_times[name] = (min(ts), max(ts))
        derived = []
        for name, start, end in phase_times:
            if name in label_times:
                d_start, d_end = label_times[name]
                derived.append((name, d_start, d_end))
            else:
                derived.append((name, start, end))  # no rows -> contiguous fallback
        phase_times = derived

        if not args.skip_phase_validation:
            # Ordering validation: phases must start in schedule order. A worker
            # can only enter phase i+1 after phase i's nominal duration elapsed,
            # so min(sent_at) is non-decreasing across phases in any legitimate
            # run; a violation means the labels are corrupt. (Overlap across
            # workers is expected and NOT an error.)
            prev_min = None
            for name, d_start, _end in phase_times:
                if name not in label_times:
                    continue
                if prev_min is not None and d_start < prev_min - 1e-6:
                    sys.stderr.write(
                        f"ERROR: phase '{name}' starts at {d_start:.1f} before "
                        f"the previous phase's first request ({prev_min:.1f}) — "
                        "generator phase labels are not ordered. "
                        "Use --skip-phase-validation to force processing.\n")
                    return 1
                prev_min = d_start
            # Informational span check (non-fatal): the open-loop supervisor is
            # time-bounded per phase, so a span far beyond nominal + 2 drains +
            # 2 windows (cross-worker stagger budget) indicates schedule/label
            # corruption. Not fatal — the v1 plateau-overrun artifact is
            # structurally impossible under the open-loop supervisor.
            for i, (name, _s, end) in enumerate(phase_times):
                if name not in label_times:
                    continue
                duration = float(phases_cfg[i].get("duration_s", 0))
                if (end - label_times[name][0]) > duration + 2 * drain_s + 2 * window_s:
                    sys.stderr.write(
                        f"[warn] phase '{name}' span "
                        f"{end - label_times[name][0]:.1f}s exceeds nominal "
                        f"{duration:.1f}s + 2 drains + 2 windows — inspect "
                        "the schedule/labels.\n")

    # --- per-LAN usable-capacity candidates from container_events ---
    capacity_by_lan = {lan: [] for lan in LAN_IDS}
    ce_path = os.path.join(run_dir, "container_events.csv")
    if os.path.exists(ce_path):
        for r in _load_csv(ce_path):
            m = DYN_COMPUTE_RE.match((r.get("container") or "").strip())
            if not m:
                continue
            t = _iso_to_epoch(r.get("timestamp_iso") or r.get("timestamp"))
            if t is not None and (r.get("state") or "").strip() == "running":
                lan = f"lan{m.group(1)}"
                if lan in capacity_by_lan:
                    capacity_by_lan[lan].append(t)
    for lan in LAN_IDS:
        capacity_by_lan[lan].sort()

    # --- per-LAN analysis ---
    all_integrity = []
    all_delay = []
    all_info = []
    all_obs = []
    all_ep = []
    all_timeline = []

    for lan in LAN_IDS:
        result = analyze_lan(
            lan, run_dir, window_s, delay_s, arm_short,
            (traffic_start, traffic_end), phase_times, capacity_by_lan[lan])
        all_integrity.append(result["integrity"])
        all_delay.extend(result["delay_rows"])
        all_info.extend(result["info_rows"])
        all_obs.extend(result["obs_rows"])
        all_ep.extend(result["ep_rows"])
        all_timeline.extend(result["timeline"])

    # --- service quality per phase per LAN (status-aware, RQ1 v2 contract) ---
    # Row contract (open-loop driver, 14th `status` column):
    #   completed -> http_status is the real HTTP code (200 = ok, >=500 = failure)
    #   timeout   -> http_status="000", latency_s = elapsed to timeout
    #   dropped/canceled -> http_status="", latency_s=""
    # Failure rate = completed-only (completed & http_status != 200).
    # Timeout rate = status=timeout / offered. Latency percentiles are
    # descriptive, over completed+ok requests only; timeout/canceled/dropped
    # rows never enter latency or failure (censoring is reported by the
    # comparison/stats layer, never conflated here).

    def _legacy_failed(status):
        s = str(status or "").strip()
        if s == "0":
            return True
        try:
            return int(s) >= 500
        except ValueError:
            return False

    def _row_outcome(r, has_status):
        if has_status:
            st = (r.get("status") or "").strip()
            if st == "completed":
                # Contract: failure = completed & http_status != 200. Only 200
                # is success for this edge service (3xx/4xx under VIP misrouting
                # are failures, not successes).
                return ("completed_ok"
                        if str(r.get("http_status") or "").strip() == "200"
                        else "failure")
            if st == "timeout":
                return "timeout"
            if st == "dropped":
                return "dropped"
            if st == "canceled":
                return "canceled"
            # Unknown/missing status: consistent with completed (200-only).
            return ("completed_ok"
                    if str(r.get("http_status") or "").strip() == "200"
                    else "failure")
        # Legacy (no status column): v1 semantics (http_status 0 or >=500 failed).
        return ("completed_ok" if not _legacy_failed(r.get("http_status"))
                else "failure")

    def _bucket(r, has_phase_label):
        """Client-side phase attribution: generator `phase` label (v2 rule),
        else the anchored boundary fallback (legacy runs)."""
        if has_phase_label:
            lbl = (r.get("phase") or "").strip()
            return lbl if lbl in known_phases else "transition"
        t = _iso_to_epoch(r.get("sent_at"))
        if t is None:
            return "transition"
        for name, start, end in phase_times:
            if start <= t < end:
                return name
        return "transition"

    sq = []
    sq_phases = known_phases + (["transition"] if has_phase_label else [])
    for lan in LAN_IDS:
        lan_reqs = [r for r in req_rows
                    if (r.get("client_lan") or "").strip() == lan]
        for name in sq_phases:
            phase_rows = [r for r in lan_reqs if _bucket(r, has_phase_label) == name]
            outcomes = [_row_outcome(r, has_status) for r in phase_rows]
            # Latency percentiles over completed+ok requests only.
            lat = [v for v in (_fnum(r.get("latency_s")) for r, o in
                               zip(phase_rows, outcomes) if o == "completed_ok")
                   if v is not None]
            pcts = _percentiles(lat)
            completed_ok = outcomes.count("completed_ok")
            failures = outcomes.count("failure")
            timeouts = outcomes.count("timeout")
            dropped = outcomes.count("dropped")
            canceled = outcomes.count("canceled")
            offered = len(phase_rows)
            completed = completed_ok + failures
            # Status-dependent columns are undefined for legacy runs (no status
            # column): blank, not a misleading 0.
            sq.append({
                "phase": name,
                "network_id": lan,
                "offered": offered,
                "completed": completed,
                "p50": _fmt(pcts[50]),
                "p95": _fmt(pcts[95]),
                "p99": _fmt(pcts[99]),
                "failure_count": failures,
                # v2: failure over completed-only; legacy (no status column)
                # keeps the v1 denominator (all rows), preserving the archived
                # v1 failure-rate convention for the supporting record.
                "failure_rate": (f"{failures / completed:.4f}"
                                 if has_status and completed
                                 else (f"{failures / offered:.4f}" if offered
                                       else "")),
                "timeout_count": (timeouts if has_status else ""),
                # Timeout-rate denominator excludes rows that never reached the
                # service and can never time out: canceled (phase-boundary
                # drain artifacts) AND dropped (client-side admission, window
                # full).
                "timeout_rate": (
                    f"{timeouts / (offered - canceled - dropped):.4f}"
                    if has_status and offered - canceled - dropped > 0 else ""),
                "dropped_count": (dropped if has_status else ""),
                "canceled_count": (canceled if has_status else ""),
            })

    # --- controller overhead ---
    overhead = []
    cs_path = os.path.join(run_dir, "controller_stats.csv")
    if os.path.exists(cs_path):
        cs_rows = _load_csv(cs_path)
        for container, cl in CONTAINER_TO_LAN.items():
            rows = [r for r in cs_rows
                    if (r.get("container") or "").strip() == container]
            ts = [_iso_to_epoch(r.get("timestamp") or r.get("timestamp_iso"))
                  for r in rows]
            rows = [r for r, t in zip(rows, ts)
                    if t is not None and traffic_start <= t <= traffic_end]
            cpus = [_fnum(r.get("cpu_percent")) for r in rows]
            mems = [_fnum(r.get("mem_usage_mb")) for r in rows]
            cpus = [v for v in cpus if v is not None]
            mems = [v for v in mems if v is not None]
            overhead.append({
                "container": container,
                "network_id": cl,
                "sample_count": len(rows),
                "mean_cpu_percent": (f"{sum(cpus) / len(cpus):.3f}" if cpus
                                     else ""),
                "mean_mem_usage_mb": (f"{sum(mems) / len(mems):.2f}" if mems
                                      else ""),
            })

    # --- write outputs ---
    _write_csv(os.path.join(out_dir, "delivery_integrity.csv"),
               ["network_id", "arm", "universe", "delivered", "delivered_frac",
                "overload_total", "overload_delivered", "overload_missed",
                "in_delay_at_end", "gap_recovery", "processing_error",
                "ack_count"],
               all_integrity)
    _write_csv(os.path.join(out_dir, "delivery_delay.csv"),
               ["network_id", "window_id", "window_end", "delivery_ts",
                "delay_s", "release_ts", "mode", "phase"],
               all_delay)
    _write_csv(os.path.join(out_dir, "info_age.csv"),
               ["ts", "window_id", "window_end", "info_age_s", "action_type",
                "action"],
               all_info)
    _write_csv(os.path.join(out_dir, "overload_observability.csv"),
               ["window_id", "window_end", "overload", "delivered",
                "episode_id", "first_decision_ts", "detection_delay_s", "acted"],
               all_obs)
    _write_csv(os.path.join(out_dir, "overload_episodes.csv"),
               ["episode_id", "n_windows", "window_ids", "delivered_any",
                "visible", "first_decision_ts"],
               all_ep)
    _write_csv(os.path.join(out_dir, "reaction_timeline.csv"),
               ["phase", "network_id", "phase_start", "scale_up_first_ts",
                "scale_down_first_ts", "usable_capacity_ts",
                "decision_latency_s", "capacity_latency_s",
                "scale_down_latency_s"],
               all_timeline)
    _write_csv(os.path.join(out_dir, "phase_service_quality.csv"),
               ["phase", "network_id", "offered", "completed", "p50", "p95",
                "p99", "failure_count", "failure_rate", "timeout_count",
                "timeout_rate", "dropped_count", "canceled_count"],
               sq)
    _write_csv(os.path.join(out_dir, "overhead.csv"),
               ["container", "network_id", "sample_count", "mean_cpu_percent",
                "mean_mem_usage_mb"],
               overhead)
    _write_csv(os.path.join(out_dir, "run_meta.csv"),
               ["key", "value"],
               [{"key": k, "value": str(v)} for k, v in {
                   "arm": arm_short,
                   "telem_source": arm,
                   "window_s": window_s,
                   "delay_s": delay_s,
                   "traffic_start": _fmt(traffic_start),
                   "traffic_end": _fmt(traffic_end),
                   "phase_names": ";".join(p[0] for p in phase_times),
               }.items()])

    print(f"RQ1 per-run analysis written to {out_dir}")
    for row in all_integrity:
        print(f"  {row['network_id']}: universe={row['universe']} "
              f"delivered={row['delivered']} "
              f"overload={row['overload_total']}/delivered={row['overload_delivered']} "
              f"missed={row['overload_missed']} "
              f"in_delay={row['in_delay_at_end']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
