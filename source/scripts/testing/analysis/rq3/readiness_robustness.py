#!/usr/bin/env python3
"""RQ3 robustness and QoE-consequence campaign analysis.

Read-only artifact analysis. Subcommands:

  classify            per-backend outcome rows for one or more runs
  stage1              Stage 1 loss-cell hypotheses (H1/H2/H3)
  restart-observation post-restart pending-backend outcomes per arm
  qoe-screen          Family 3 (rq3_qoe) C1/C2/C3 discovery gates
  qoe-campaign        Family 3 (rq3_qoe) E-stage H-Q1..H-Q4 verdicts
  timing-screen       Family rq3_timing P1/P2/lock preflight gates
  timing-campaign     Family rq3_timing E-stage H-T1..H-T3 verdicts

Family 3 measures the visible/bounded QoE consequence of readiness-event
loss under a uniform EDGE_CPUS quota ladder; see
docs/operation/testing/experiment/v3/rq3_qoe/experiment_plan.md.
"""
from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import re
import statistics
import sys
from pathlib import Path
from typing import Any

from .readiness_low_headroom import (
    PHASE,
    capacity_summary,
    cpu_values,
    is_completed,
    is_success,
    load_window_log,
    parse_ready_epoch,
    percentile,
    phase_bounds,
    read_csv,
    request_rows,
    timestamp,
    write_csv,
    write_json,
)

LABEL_RE = re.compile(r"rq3rob_(none|loss_all|loss_alt|restart)_(event_only|hybrid|reconcile)_(\d+)$")
QOE_LABEL_RE = re.compile(r"rq3qoe_(none|loss_all|loss_alt)_(event_only|hybrid|reconcile)_(\d+)$")
DYNAMIC_RE = re.compile(r"^edge_server_lan[12]_dyn\d+$")
RUNNING_STATES = {"running", "created", "restarting"}

# Family 3 (rq3_qoe) pre-registered contract constants. Floors follow the
# frozen P4 workload: plateau ~21.6k rows/LAN, baseline ~120 rows/LAN (2
# active clients/LAN at client_fraction 0.1). The baseline floors below are the
# amended artifact-sanity minimums (pooled >=100, per-LAN >=50) so the
# baseline bad_rate <=1% read is meaningful; the earlier draft's 1000/LAN
# baseline figure is unreachable and was amended 2026-09-07 (see
# docs/operation/testing/experiment/v3/rq3_qoe/experiment_plan.md §3).
QOE_LADDER = ("0.13", "0.12", "0.11", "0.10", "0.09")
PLATEAU_MIN_POOLED = 5000
PLATEAU_MIN_PER_LAN = 1000
BASELINE_MIN_POOLED = 100
BASELINE_MIN_PER_LAN = 50
CONTRAST_PP = 0.05
CONTROL_BAD_MAX = 0.01
BOUNDED_BAD_MAX = 0.15

# Slow-share axis (amendment 2026-09-08, user-approved; see
# docs/operation/testing/experiment/v3/rq3_qoe/experiment_plan.md §3/§4/§5).
# QoE worsening = "higher latency and/or timeouts": slow_rate counts plateau
# service rows with status==timeout (unconditional; driver cap 300 s > T) or
# latency_s > T. Controls slow ceiling 2 pp; event_only slow boundedness
# ceiling 25 %; slow contrast bar reuses CONTRAST_PP (5 pp).
QOE_SLOW_S = 1.0
SLOW_CONTROL_MAX = 0.02
SLOW_BOUNDED_EVENT_MAX = 0.25


def container_events(run_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    path = run_dir / "container_events.csv"
    if not path.exists():
        return rows
    for row in csv.DictReader(path.open(newline="", encoding="utf-8", errors="replace")):
        parsed = timestamp(row.get("timestamp_iso"))
        if parsed is None:
            continue
        item = dict(row)
        item["_ts"] = parsed
        rows.append(item)
    return rows


def restart_markers(run_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    path = run_dir / "experiment_fault_events.csv"
    if not path.exists():
        return rows
    for row in csv.DictReader(path.open(newline="", encoding="utf-8", errors="replace")):
        if row.get("action_type") == "docker_restart" and row.get("status") == "executed":
            parsed = timestamp(row.get("timestamp"))
            if parsed is not None:
                item = dict(row)
                item["_ts"] = parsed
                rows.append(item)
    return rows


def admission_rows(run_dir: Path) -> list[dict[str, Any]]:
    """All admission-log rows (admitted and abandoned) with true readiness."""
    rows: list[dict[str, Any]] = []
    for lan in (1, 2):
        path = run_dir / f"admission_log_lan{lan}.csv"
        if not path.exists():
            continue
        for row in csv.DictReader(path.open(newline="", encoding="utf-8", errors="replace")):
            item = dict(row)
            item["lan"] = lan
            item["_admitted_ts"] = timestamp(row.get("admitted_ts"))
            item["_abandoned_ts"] = timestamp(row.get("app_ready_ts")) if row.get("result") == "abandoned" else None
            item["_true_ready"] = parse_ready_epoch(
                run_dir / "service_logs" / f"{row.get('container', '')}.log"
            )
            rows.append(item)
    return rows


def classify(run_dir: Path) -> dict[str, Any]:
    """Per-run classification of every dynamic compute backend."""
    events = container_events(run_dir)
    adm = admission_rows(run_dir)
    admitted_by_container = {
        row.get("container"): row for row in adm if row.get("result") == "admitted"
    }
    abandoned_by_container = {
        row.get("container"): row for row in adm if row.get("result") == "abandoned"
    }
    spawn: dict[str, float] = {}
    final_state: dict[str, str] = {}
    last_event_ts: dict[str, float] = {}
    for event in events:
        container = event.get("container", "")
        if not DYNAMIC_RE.match(container):
            continue
        if container not in spawn:
            spawn[container] = event["_ts"]
        final_state[container] = event.get("state", final_state.get(container, ""))
        last_event_ts[container] = event["_ts"]
    removed: dict[str, float] = {
        container: last_event_ts[container]
        for container in spawn
        if final_state.get(container, "") not in RUNNING_STATES
    }
    first_abandon = min(
        (row["_abandoned_ts"] for row in abandoned_by_container.values()
         if row["_abandoned_ts"] is not None),
        default=None,
    )
    backends: list[dict[str, Any]] = []
    for container, spawn_ts in sorted(spawn.items(), key=lambda pair: pair[1]):
        admitted = admitted_by_container.get(container)
        abandoned = abandoned_by_container.get(container)
        outcome = ""
        admit_source = ""
        admitted_ts = None
        if admitted is not None:
            outcome = "admitted"
            admit_source = admitted.get("admit_source", "")
            admitted_ts = admitted["_admitted_ts"]
        elif abandoned is not None:
            outcome = "abandoned"
            admit_source = "abandoned"
            admitted_ts = None
        elif container in removed:
            outcome = "removed_without_admission"
        else:
            outcome = "orphaned_dark"
        pre_churn = first_abandon is None or spawn_ts < first_abandon
        backends.append({
            "container": container,
            "lan": int(re.search(r"lan(\d)", container).group(1)),
            "spawn_ts": spawn_ts,
            "outcome": outcome,
            "admit_source": admit_source,
            "true_ready_ts": (admitted or abandoned or {}).get("_true_ready"),
            "admitted_ts": admitted_ts,
            "abandoned_ts": (abandoned or {}).get("_abandoned_ts"),
            "removed_ts": removed.get(container),
            "pre_churn": pre_churn,
            "dark_s": (admitted_ts - (admitted or {}).get("_true_ready")
                       if admitted_ts is not None and (admitted or {}).get("_true_ready") is not None
                       else None),
            "spawn_admit_s": (admitted_ts - spawn_ts
                              if admitted_ts is not None else None),
        })
    per_lan = {lan: {
        "pre_churn_spawned": sum(b["pre_churn"] for b in backends if b["lan"] == lan),
        "admitted": sum(b["pre_churn"] and b["outcome"] == "admitted"
                        for b in backends if b["lan"] == lan),
    } for lan in (1, 2)}
    pre_churn_spawned = sum(per_lan[lan]["pre_churn_spawned"] for lan in (1, 2))
    admitted_pre_churn = sum(per_lan[lan]["admitted"] for lan in (1, 2))
    return {
        "run": run_dir.name,
        "backends": backends,
        "first_abandon_ts": first_abandon,
        "spawned": len(backends),
        "pre_churn_spawned": pre_churn_spawned,
        "admitted": sum(item["outcome"] == "admitted" for item in backends),
        "abandoned": sum(item["outcome"] == "abandoned" for item in backends),
        "orphaned_dark": sum(item["outcome"] == "orphaned_dark" for item in backends),
        "removed_without_admission": sum(
            item["outcome"] == "removed_without_admission" for item in backends),
        "preservation": (admitted_pre_churn / pre_churn_spawned
                         if pre_churn_spawned else None),
        "per_lan_preservation": {
            lan: (per_lan[lan]["admitted"] / per_lan[lan]["pre_churn_spawned"]
                  if per_lan[lan]["pre_churn_spawned"] else None)
            for lan in (1, 2)
        },
    }


def label_parts(run_name: str) -> tuple[str, str, str] | None:
    match = LABEL_RE.search(run_name)
    return (match.group(1), match.group(2), match.group(3)) if match else None


def exact_mwu(x: list[float], y: list[float]) -> float:
    n1, n2 = len(x), len(y)
    if n1 == 0 or n2 == 0:
        return float("nan")
    allv = sorted(x + y)
    ranks = {value: index + 1 for index, value in enumerate(allv)}
    u = sum(ranks[value] for value in x) - n1 * (n1 + 1) / 2
    mean = n1 * n2 / 2
    total = extreme = 0
    for selection in itertools.combinations(range(n1 + n2), n1):
        u_perm = sum(sorted((ranks[allv[i]] for i in selection))) - n1 * (n1 + 1) / 2
        total += 1
        if abs(u_perm - mean) >= abs(u - mean):
            extreme += 1
    return extreme / total


def cliffs(x: list[float], y: list[float]) -> float:
    gt = sum(1 for i in x for j in y if i > j)
    lt = sum(1 for i in x for j in y if i < j)
    return (gt - lt) / (len(x) * len(y))


def classify_command(args: argparse.Namespace) -> int:
    rows: list[dict[str, Any]] = []
    for path in args.run_dir:
        result = classify(Path(path))
        for backend in result["backends"]:
            rows.append({"run": result["run"], **backend})
        print(json.dumps({key: result[key] for key in
                          ("run", "spawned", "admitted", "abandoned",
                           "orphaned_dark", "removed_without_admission",
                           "preservation")}, indent=2))
    write_csv(Path(args.out), rows)
    return 0


def stage1_command(args: argparse.Namespace) -> int:
    cells: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for path in args.run_dir:
        parts = label_parts(Path(path).name)
        if parts is None:
            raise ValueError(f"cannot parse run label: {Path(path).name}")
        cell, arm, _ = parts
        cells.setdefault((cell, arm), []).append(classify(Path(path)))
    report: dict[str, Any] = {"runs": len(args.run_dir)}
    failures: list[str] = []
    for (cell, arm), runs in sorted(cells.items()):
        preservation = [run["preservation"] for run in runs if run["preservation"] is not None]
        report[f"{cell}_{arm}"] = {
            "preservation": preservation,
            "median_preservation": statistics.median(preservation) if preservation else None,
            "abandoned": [run["abandoned"] for run in runs],
        }
    loss_all_event = report.get("loss_all_event_only", {}).get("preservation", [])
    loss_all_hybrid = report.get("loss_all_hybrid", {}).get("preservation", [])
    loss_all_reconcile = report.get("loss_all_reconcile", {}).get("preservation", [])
    if loss_all_event and any(value != 0.0 for value in loss_all_event):
        failures.append("H1 event_only loss_all preservation != 0.0")
    if loss_all_hybrid and any(value != 1.0 for value in loss_all_hybrid):
        failures.append("H1 hybrid loss_all preservation != 1.0")
    if loss_all_reconcile and any(value != 1.0 for value in loss_all_reconcile):
        failures.append("H1 reconcile loss_all preservation != 1.0")
    alt = report.get("loss_alt_event_only", {}).get("preservation", [])
    if alt and not all(0.3 <= value <= 0.7 for value in alt):
        failures.append("H2 event_only loss_alt preservation outside [0.3,0.7]")
    alt_hybrid_units = [
        run["per_lan_preservation"][lan]
        for run in cells.get(("loss_alt", "hybrid"), [])
        for lan in (1, 2) if run["per_lan_preservation"][lan] is not None
    ]
    alt_reconcile_units = [
        run["per_lan_preservation"][lan]
        for run in cells.get(("loss_alt", "reconcile"), [])
        for lan in (1, 2) if run["per_lan_preservation"][lan] is not None
    ]
    if alt_hybrid_units and any(value != 1.0 for value in alt_hybrid_units):
        failures.append("H2 hybrid loss_alt per-LAN preservation != 1.0")
    if alt_reconcile_units and any(value != 1.0 for value in alt_reconcile_units):
        failures.append("H2 reconcile loss_alt per-LAN preservation != 1.0")
    hybrid_loss = [run for run in cells.get(("loss_all", "hybrid"), [])]
    hybrid_none = [run for run in cells.get(("none", "hybrid"), [])]
    if hybrid_loss and hybrid_none:
        def per_run_medians(runs: list[dict[str, Any]], field: str) -> list[float]:
            medians: list[float] = []
            for run in runs:
                values = [item[field] for item in run["backends"]
                          if item["outcome"] == "admitted" and item.get(field) is not None]
                if values:
                    medians.append(statistics.median(values))
            return medians

        # H3 PRIMARY (pre-registered): spawn->admit, the fallback-cadence
        # anchor (fallback 20 s + probe retry + timeout). Window [20, 26] s.
        spawn_loss = per_run_medians(hybrid_loss, "spawn_admit_s")
        spawn_none = per_run_medians(hybrid_none, "spawn_admit_s")
        # H3 SECONDARY (descriptive only, never gated): true-ready->admit.
        ready_loss = per_run_medians(hybrid_loss, "dark_s")
        ready_none = per_run_medians(hybrid_none, "dark_s")
        if spawn_loss and spawn_none:
            report["H3"] = {
                "metric": "spawn_admit_s",
                "per_run_median_spawn_admit_loss_all": spawn_loss,
                "per_run_median_spawn_admit_none": spawn_none,
                "mwu_p": exact_mwu(spawn_loss, spawn_none),
                "cliffs_delta": cliffs(spawn_loss, spawn_none),
                "within_20_26": 20.0 <= statistics.median(spawn_loss) <= 26.0,
                "true_ready_anchor_descriptive": {
                    "per_run_median_dark_loss_all": ready_loss,
                    "per_run_median_dark_none": ready_none,
                },
            }
            if not report["H3"]["within_20_26"]:
                failures.append(
                    "H3 hybrid loss_all median spawn->admit outside [20,26] s")
            if statistics.median(spawn_loss) <= statistics.median(spawn_none):
                failures.append(
                    "H3 hybrid loss_all spawn->admit not above none cell")
    report["failures"] = failures
    report["pass"] = not failures
    write_json(Path(args.out), report)
    print(json.dumps({"pass": report["pass"], "failures": failures}, indent=2))
    return 0 if report["pass"] else 2


def restart_command(args: argparse.Namespace) -> int:
    arms: dict[str, list[dict[str, Any]]] = {}
    for path in args.run_dir:
        run_dir = Path(path)
        markers = restart_markers(run_dir)
        if not markers:
            raise ValueError(f"no executed docker_restart marker in {run_dir.name}")
        restart_ts = min(marker["_ts"] for marker in markers)
        result = classify(run_dir)
        pending = []
        for backend in result["backends"]:
            admitted = backend["admitted_ts"]
            failed_before = (
                (backend["abandoned_ts"] is not None
                 and backend["abandoned_ts"] < restart_ts)
                or (backend["removed_ts"] is not None
                    and backend["removed_ts"] < restart_ts)
            )
            pending_at_restart = (backend["spawn_ts"] < restart_ts
                                  and not failed_before
                                  and (admitted is None or admitted > restart_ts))
            if pending_at_restart:
                pending.append({"container": backend["container"],
                                "spawn_ts": backend["spawn_ts"],
                                "outcome": backend["outcome"],
                                "admitted_ts": admitted,
                                "admitted_after_restart": admitted is not None and admitted > restart_ts})
        arm = label_parts(run_dir.name)[1] if label_parts(run_dir.name) else "?"
        arms.setdefault(arm, []).append({"run": run_dir.name,
                                         "restart_ts": restart_ts,
                                         "pending_at_restart": pending,
                                         "spawned": result["spawned"],
                                         "admitted": result["admitted"],
                                         "orphaned_dark": result["orphaned_dark"]})
    write_json(Path(args.out), {"arms": arms})
    print(json.dumps({"arms": {arm: [run["pending_at_restart"] for run in runs]
                               for arm, runs in arms.items()}}, indent=2, default=str))
    return 0


# ---------------------------------------------------------------------------
# Family 3 (rq3_qoe): QoE-consequence measurement + discovery/evidence gates
# ---------------------------------------------------------------------------


def qoe_label_parts(run_name: str) -> tuple[str, str, str] | None:
    match = QOE_LABEL_RE.search(run_name)
    return (match.group(1), match.group(2), match.group(3)) if match else None


def _qoe_status(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """status_rates-equivalent with the aggregate bad_rate pre-registered in
    the QoE measurement contract:
      timeout_rate = timeouts / (completed + timeout)
      failure_rate = failures / completed
      bad_rate = (timeout + failure) / (completed + timeout)   # aggregate
    canceled/dropped are counted in offered but excluded from the rates.
    """
    offered = len(rows)
    canceled = sum(row.get("status") in {"canceled", "dropped"} for row in rows)
    service = [row for row in rows if row.get("status") in {"completed", "timeout"}]
    completed = sum(is_completed(row) for row in service)
    timeouts = sum(row.get("status") == "timeout" for row in service)
    failures = sum(is_completed(row) and not is_success(row) for row in service)
    service_n = len(service)
    # Slow-share axis: a timeout is slow unconditionally (its latency_s is
    # elapsed-to-cap, and a missing/unparseable latency must never drop it);
    # completed rows are slow when latency_s exceeds the threshold.
    slow = sum(1 for row in service
               if row.get("status") == "timeout"
               or (row.get("_latency") is not None
                   and row["_latency"] > QOE_SLOW_S))
    slow5 = sum(1 for row in service
                if row.get("status") == "timeout"
                or (row.get("_latency") is not None and row["_latency"] > 5.0))
    completed_rows = [row for row in service if is_completed(row)]
    lat = [row["_latency"] for row in completed_rows
           if row.get("_latency") is not None
           and math.isfinite(row["_latency"])]
    return {
        "offered": offered,
        "canceled_dropped": canceled,
        "cancel_rate": canceled / offered if offered else None,
        "http000": sum(row.get("http_status") == "000" for row in rows),
        "completed": completed,
        "timeouts": timeouts,
        "failures": failures,
        "timeout_rate": timeouts / service_n if service_n else None,
        "failure_rate": failures / completed if completed else None,
        "bad_rate": (timeouts + failures) / service_n if service_n else None,
        "service_requests": service_n,
        "slow_n": slow,
        "slow_rate": slow / service_n if service_n else None,
        "slow5_n": slow5,
        "slow5_rate": slow5 / service_n if service_n else None,
        "lat_completed_n": len(lat),
        "lat_completed_p50": percentile(lat, 0.50) if lat else None,
        "lat_completed_p95": percentile(lat, 0.95) if lat else None,
        "lat_completed_p99": percentile(lat, 0.99) if lat else None,
    }


def _qoe_window(run_dir: Path, rows: list[dict[str, Any]],
                bounds: dict[str, tuple[float, float]], name: str) -> dict[str, Any]:
    start, end = bounds[name]
    selected = [row for row in rows
                if start <= row["_sent"] < end and row.get("phase") == name]
    pooled = _qoe_status(selected)
    per_lan = {lan: _qoe_status([row for row in selected
                                 if row.get("client_lan") == f"lan{lan}"])
               for lan in (1, 2)}
    return {"pooled": pooled, "per_lan": per_lan}


def qoe_rate_metrics(run_dir: Path) -> dict[str, Any]:
    """Plateau/baseline QoE rates (pooled + per LAN) with contract floors."""
    rows = request_rows(run_dir)
    bounds = phase_bounds(run_dir)
    plateau = _qoe_window(run_dir, rows, bounds, PHASE)
    baseline = _qoe_window(run_dir, rows, bounds, "baseline")
    floors = {
        "plateau_pooled_ge_5000":
            (plateau["pooled"]["service_requests"] or 0) >= PLATEAU_MIN_POOLED,
        "plateau_per_lan_ge_1000": all(
            (plateau["per_lan"][lan]["service_requests"] or 0) >= PLATEAU_MIN_PER_LAN
            for lan in (1, 2)),
        "baseline_pooled_ge_100":
            (baseline["pooled"]["service_requests"] or 0) >= BASELINE_MIN_POOLED,
        "baseline_per_lan_ge_50": all(
            (baseline["per_lan"][lan]["service_requests"] or 0) >= BASELINE_MIN_PER_LAN
            for lan in (1, 2)),
    }
    return {
        "run": run_dir.name,
        "parts": qoe_label_parts(run_dir.name),
        "plateau": plateau,
        "baseline": baseline,
        "floors": floors,
        "driver_clean": (plateau["pooled"]["cancel_rate"] or 0) < 0.05,
        "baseline_http000_zero": (baseline["pooled"]["http000"] or 0) == 0,
    }


def qoe_mechanism(run_dir: Path) -> dict[str, Any]:
    """Per-arm admission mechanism facts from the admission logs."""
    adm = admission_rows(run_dir)
    admitted = [row for row in adm if row.get("result") == "admitted"]
    abandoned = [row for row in adm if row.get("result") == "abandoned"]
    per_lan_admitted = {lan: sum(1 for row in admitted if row["lan"] == lan)
                        for lan in (1, 2)}
    per_lan_abandoned = {lan: sum(1 for row in abandoned if row["lan"] == lan)
                         for lan in (1, 2)}
    per_lan_sources = {lan: sorted({row.get("admit_source", "")
                                    for row in admitted if row["lan"] == lan})
                       for lan in (1, 2)}
    probe_fallback = sum(1 for row in admitted
                         if row.get("admit_source") == "probe_fallback")
    event_admitted = sum(1 for row in admitted
                         if row.get("admit_source") == "event")
    probe_admitted = sum(1 for row in admitted
                         if row.get("admit_source") == "probe")
    return {
        "admitted_total": len(admitted),
        "abandoned_total": len(abandoned),
        "per_lan_admitted": per_lan_admitted,
        "per_lan_abandoned": per_lan_abandoned,
        "per_lan_sources": per_lan_sources,
        "probe_fallback_admitted": probe_fallback,
        "event_admitted": event_admitted,
        "probe_admitted": probe_admitted,
        "event_fraction": event_admitted / len(admitted) if admitted else None,
    }


def qoe_drop_modes(run_dir: Path) -> list[str]:
    modes: set[str] = set()
    for lan in (1, 2):
        path = run_dir / f"controller_lan{lan}.log"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            for match in re.finditer(r"\bmode=(all|alternate)\b", line):
                modes.add(match.group(1))
    return sorted(modes)


def qoe_scale_down_in_plateau(run_dir: Path) -> bool:
    bounds = phase_bounds(run_dir)
    start, end = bounds[PHASE]
    for event in read_csv(run_dir / "elasticity_events.csv"):
        event_time = timestamp(event.get("timestamp_s") or event.get("timestamp"))
        kind = (event.get("event_type") or event.get("event") or "").lower()
        if event_time is not None and start <= event_time < end and "scale_down" in kind:
            return True
    return False


def qoe_quota(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "quota_snapshot.json"
    if not path.exists():
        return {"requested_edge_cpus": None, "all_compute_containers_match": False,
                "present": False}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        "requested_edge_cpus": data.get("requested_edge_cpus"),
        "all_compute_containers_match": bool(data.get("all_compute_containers_match")),
        "present": True,
    }


def qoe_pressure(run_dir: Path) -> dict[str, Any]:
    """Old-backend CPU pressure before first readiness in the plateau.

    Primary method: capacity_summary's 30 s pre-first-true-ready window, used
    only when the run has >=1 admission (the anchor is defined). The
    zero-admission cell (event_only loss_all: every spawn abandoned) has no
    first-ready anchor, so it uses the plateau_first_120s measure — the static
    tier carries the plateau while every spawn is abandoned. Any OTHER
    capacity_summary failure is surfaced as an error (never silently
    reinterpreted as the fallback).
    """
    admitted = sum(1 for row in admission_rows(run_dir)
                   if row.get("result") == "admitted")
    if admitted == 0:
        bounds = phase_bounds(run_dir)
        start = bounds[PHASE][0]
        end = start + 120.0
        pre: dict[int, dict[str, Any]] = {}
        for lan in (1, 2):
            window = load_window_log(run_dir, lan)
            early = [row for row in window if start <= row["_window_end"] < end]
            ids: set[str] = set()
            for row in early:
                ids.update((row.get("servers") or {}).keys())
            values = cpu_values(window, start, end, ids) if ids else []
            pre[lan] = {"median": statistics.median(values) if values else None,
                        "p95": percentile(values, 0.95)}
        return {"pre_cpu": pre, "method": "plateau_first_120s", "error": None}
    try:
        summary = capacity_summary(run_dir)
        pre = summary["pre_cpu"]
        return {"pre_cpu": {lan: {"median": pre[lan]["median"], "p95": pre[lan]["p95"]}
                            for lan in (1, 2)},
                "method": "pre_first_ready", "error": None}
    except Exception as exc:  # noqa: BLE001 - artifact-dependent by design
        return {"pre_cpu": {1: {"median": None, "p95": None},
                            2: {"median": None, "p95": None}},
                "method": "error",
                "error": f"capacity_summary failed: {exc}"}


def qoe_pressure_ok(pressure: dict[str, Any]) -> bool:
    return all(
        value["median"] is not None and value["p95"] is not None
        and 60.0 <= value["median"] <= 85.0 and value["p95"] <= 95.0
        for value in pressure["pre_cpu"].values()
    )


def qoe_run_metrics(run_dir: Path) -> dict[str, Any]:
    run_dir = Path(run_dir)
    metrics = qoe_rate_metrics(run_dir)
    metrics["mechanism"] = qoe_mechanism(run_dir)
    metrics["drop_modes"] = qoe_drop_modes(run_dir)
    metrics["scale_down_in_plateau"] = qoe_scale_down_in_plateau(run_dir)
    metrics["quota"] = qoe_quota(run_dir)
    metrics["pressure"] = qoe_pressure(run_dir)
    metrics["pressure_ok"] = qoe_pressure_ok(metrics["pressure"])
    return metrics


def _pooled_bad(m: dict[str, Any], window: str = "plateau") -> float | None:
    return m[window]["pooled"]["bad_rate"]


def _pooled_timeout(m: dict[str, Any], window: str = "plateau") -> float | None:
    return m[window]["pooled"]["timeout_rate"]


def _pooled_slow(m: dict[str, Any], window: str = "plateau") -> float | None:
    return m[window]["pooled"]["slow_rate"]


def _base_gates(m: dict[str, Any], rung: str) -> dict[str, bool]:
    """Run-level gates shared by every screen: floors, driver, baseline health,
    quota match, no plateau scale-down, pressure."""
    baseline_bad = _pooled_bad(m, "baseline")
    return {
        "floors": all(m["floors"].values()),
        "driver_clean": m["driver_clean"],
        "baseline_bad_le_1pct": (baseline_bad is not None
                                  and baseline_bad <= CONTROL_BAD_MAX),
        "baseline_http000_zero": m["baseline_http000_zero"],
        "quota_matches": (m["quota"]["present"]
                          and m["quota"]["all_compute_containers_match"]
                          and str(m["quota"]["requested_edge_cpus"]) == str(rung)),
        "no_plateau_scale_down": not m["scale_down_in_plateau"],
        "pressure_ok": m["pressure_ok"],
    }


def _mechanism_gate(m: dict[str, Any], arm: str, fault: str) -> dict[str, bool]:
    mech = m["mechanism"]
    if fault == "loss_all":
        if arm == "event_only":
            return {
                "zero_admitted": mech["admitted_total"] == 0,
                "abandoned_ge_2_per_lan": all(
                    mech["per_lan_abandoned"][lan] >= 2 for lan in (1, 2)),
                "zero_probe_fallback": mech["probe_fallback_admitted"] == 0,
                "drop_mode_all": "all" in m["drop_modes"],
            }
        if arm == "hybrid":
            return {
                "all_admitted_probe_fallback": (
                    mech["admitted_total"] > 0
                    and mech["probe_fallback_admitted"] == mech["admitted_total"]),
                "admit_ge_1_per_lan": all(
                    mech["per_lan_admitted"][lan] >= 1 for lan in (1, 2)),
                "zero_abandoned": mech["abandoned_total"] == 0,
            }
        if arm == "reconcile":
            return {
                "all_admitted_probe": (
                    mech["admitted_total"] > 0
                    and mech["probe_admitted"] == mech["admitted_total"]),
                "admit_ge_1_per_lan": all(
                    mech["per_lan_admitted"][lan] >= 1 for lan in (1, 2)),
                "zero_abandoned": mech["abandoned_total"] == 0,
            }
    if fault == "none" and arm == "event_only":
        return {
            "event_fraction_1": mech["event_fraction"] == 1.0,
            "event_admit_ge_1_per_lan": all(
                "event" in mech["per_lan_sources"][lan] for lan in (1, 2)),
            "zero_abandoned": mech["abandoned_total"] == 0,
        }
    return {}


def _contrast_delta(event_m: dict[str, Any], hybrid_m: dict[str, Any],
                    reconcile_m: dict[str, Any]) -> float | None:
    event_timeout = _pooled_timeout(event_m)
    controls = [value for value in (_pooled_timeout(hybrid_m),
                                    _pooled_timeout(reconcile_m))
                if value is not None]
    if event_timeout is None or not controls:
        return None
    return event_timeout - max(controls)


def _contrast_delta_slow(event_m: dict[str, Any], hybrid_m: dict[str, Any],
                         reconcile_m: dict[str, Any]) -> float | None:
    event_slow = _pooled_slow(event_m)
    controls = [value for value in (_pooled_slow(hybrid_m),
                                    _pooled_slow(reconcile_m))
                if value is not None]
    if event_slow is None or not controls:
        return None
    return event_slow - max(controls)


def _screen_run_row(m: dict[str, Any], rung: str, arm: str, fault: str) -> dict[str, Any]:
    base = _base_gates(m, rung)
    mechanism = _mechanism_gate(m, arm, fault)
    is_control = (fault == "loss_all" and arm in ("hybrid", "reconcile")) \
        or (fault == "none" and arm == "event_only")
    bad = _pooled_bad(m)
    slow = _pooled_slow(m)
    control = (bad is not None and bad <= CONTROL_BAD_MAX) if is_control else None
    control_slow = (slow is not None and slow <= SLOW_CONTROL_MAX) if is_control else None
    base_ok = all(base.values())
    mech_ok = bool(mechanism) and all(mechanism.values())
    gates = {**base, **mechanism}
    gates["control_bad_le_1pct"] = control
    gates["control_slow_le_2pp"] = control_slow
    return {
        "run": m["run"],
        "cell": m["parts"][0] if m["parts"] else None,
        "arm": m["parts"][1] if m["parts"] else None,
        "quota_requested": m["quota"]["requested_edge_cpus"],
        "bad_rate_plateau_pooled": _pooled_bad(m),
        "timeout_rate_plateau_pooled": _pooled_timeout(m),
        "slow_rate_plateau_pooled": slow,
        "slow5_rate_plateau_pooled": m["plateau"]["pooled"]["slow5_rate"],
        "lat_completed_p95_plateau_pooled": m["plateau"]["pooled"]["lat_completed_p95"],
        "cancel_rate_plateau_pooled": m["plateau"]["pooled"]["cancel_rate"],
        "gates": gates,
        "base_ok": base_ok,
        "mechanism_ok": mech_ok,
        "pressure_method": m["pressure"]["method"],
        "pressure_error": m["pressure"].get("error"),
        "eligible_run": base_ok and mech_ok
            and (control is None or control)
            and (control_slow is None or control_slow),
    }


def qoe_screen_exit(verdict: str) -> int:
    return {"lock": 0, "descend": 2, "stop_null": 3}[verdict]


def _qoe_stop(message: str) -> int:
    print(f"ERROR: {message}", file=sys.stderr)
    return 3


def _event_bounded(m: dict[str, Any]) -> tuple[float | None, float | None, bool]:
    bad = _pooled_bad(m)
    slow = _pooled_slow(m)
    return (bad, slow,
            bad is not None and bad <= BOUNDED_BAD_MAX
            and slow is not None and slow <= SLOW_BOUNDED_EVENT_MAX)


def qoe_screen_command(args: argparse.Namespace) -> int:
    try:
        return _qoe_screen_body(args)
    except ValueError as exc:
        # Malformed invocations (bad labels, wrong arm sets) must never be
        # mistaken for a legitimate "descend" (exit 2): STOP for diagnosis.
        return _qoe_stop(str(exc))


def _qoe_screen_body(args: argparse.Namespace) -> int:
    if args.stage in ("c2", "c3"):
        if not args.c1_json:
            raise ValueError(f"--c1-json is required for --stage {args.stage}")
    pairs = [(qoe_label_parts(Path(path).name), Path(path)) for path in args.run_dir]
    unparsed = [str(path) for label, path in pairs if label is None]
    if unparsed:
        raise ValueError(f"cannot parse qoe labels for: {unparsed}")
    labels = [label for label, _ in pairs]
    for label in labels:
        if labels.count(label) > 1:
            raise ValueError(f"duplicate run label in screen: {'_'.join(label)}")
    runs = {label: qoe_run_metrics(path) for label, path in pairs}
    rung = args.rung
    rows: list[dict[str, Any]] = []

    if args.stage == "c1":
        expected = {("loss_all", "event_only"), ("loss_all", "hybrid"),
                    ("loss_all", "reconcile")}
        found = {label[:2] for label in runs if label is not None}
        if found != expected:
            raise ValueError(f"C1 screen needs the 3 loss_all arms; got {sorted(found)}")
        by_arm = {label[1]: runs[label] for label in runs if label is not None}
        for arm in ("event_only", "hybrid", "reconcile"):
            rows.append(_screen_run_row(by_arm[arm], rung, arm, "loss_all"))
        delta = _contrast_delta(by_arm["event_only"], by_arm["hybrid"],
                                by_arm["reconcile"])
        delta_slow = _contrast_delta_slow(by_arm["event_only"], by_arm["hybrid"],
                                          by_arm["reconcile"])
        eligible = all(row["eligible_run"] for row in rows) \
            and (delta is not None or delta_slow is not None)
        # Slow-first precedence (deterministic, pre-registered): the slow
        # axis is the user-facing QoE axis.
        lock_component = None
        if delta_slow is not None and delta_slow >= CONTRAST_PP:
            lock_component = "slow"
        elif delta is not None and delta >= CONTRAST_PP:
            lock_component = "timeout"
        event_bad, event_slow, bounded_ok = _event_bounded(by_arm["event_only"])
        visible = lock_component is not None
        verdict = ("stop_null" if eligible and visible and not bounded_ok
                   else "lock" if eligible and visible and bounded_ok
                   else "descend")
        output = {"stage": "c1", "rung": rung, "seed": args.seed, "runs": rows,
                  "contract_version": 2,
                  "delta_pp": round(delta * 100.0, 2) if delta is not None else None,
                  "delta_slow_pp": round(delta_slow * 100.0, 2)
                  if delta_slow is not None else None,
                  "lock_component": lock_component,
                  "event_only_bounded": {
                      "bad_ok": event_bad is not None and event_bad <= BOUNDED_BAD_MAX,
                      "slow_ok": event_slow is not None
                      and event_slow <= SLOW_BOUNDED_EVENT_MAX,
                      "bad_rate": event_bad, "slow_rate": event_slow},
                  "bounded_ok": bounded_ok, "verdict": verdict,
                  "lock_candidate": verdict == "lock", "eligible": eligible}
    elif args.stage == "c2":
        c1_path = Path(args.c1_json)
        try:
            c1 = json.loads(c1_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return _qoe_stop(f"cannot read c1 json {c1_path}: {exc}")
        if c1.get("contract_version") != 2:
            return _qoe_stop(
                f"c1 json must be contract_version 2 (slow-share amendment), "
                f"got {c1.get('contract_version')!r}: {c1_path}")
        verdict = c1.get("verdict")
        lock_component = c1.get("lock_component")
        bounded_ok = c1.get("bounded_ok")
        if verdict == "lock":
            component_delta = (c1.get("delta_slow_pp")
                               if lock_component == "slow" else c1.get("delta_pp"))
            coherent = (bounded_ok is True
                        and lock_component in ("timeout", "slow")
                        and component_delta is not None
                        and component_delta >= CONTRAST_PP * 100.0)
        elif verdict in ("descend", "stop_null"):
            coherent = True
        else:
            coherent = False
        if not coherent:
            return _qoe_stop(
                f"c1 json incoherent for verdict {verdict!r} "
                f"(lock_component={lock_component!r}, bounded_ok={bounded_ok!r}, "
                f"delta_pp={c1.get('delta_pp')!r}, "
                f"delta_slow_pp={c1.get('delta_slow_pp')!r}): {c1_path}")
        output = {"stage": "c2", "rung": rung, "seed": args.seed,
                  "c1_json": args.c1_json, "contract_version": 2,
                  "delta_pp": c1.get("delta_pp"),
                  "delta_slow_pp": c1.get("delta_slow_pp"),
                  "lock_component": lock_component,
                  "bounded_ok": bounded_ok,
                  "verdict": verdict,
                  "lock_candidate": verdict == "lock"}
    elif args.stage == "c3":
        c1_path = Path(args.c1_json)
        try:
            c1 = json.loads(c1_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return _qoe_stop(f"cannot read c1 json {c1_path}: {exc}")
        if c1.get("contract_version") != 2:
            return _qoe_stop(
                f"c1 json must be contract_version 2 (slow-share amendment), "
                f"got {c1.get('contract_version')!r}: {c1_path}")
        lock_component = c1.get("lock_component")
        if c1.get("verdict") != "lock" or lock_component not in ("timeout", "slow"):
            return _qoe_stop(
                f"C3 requires a locked c1.json (verdict=lock), got "
                f"verdict={c1.get('verdict')!r} lock_component={lock_component!r}")
        expected = {("loss_all", "event_only"), ("loss_all", "hybrid"),
                    ("loss_all", "reconcile"), ("none", "event_only")}
        found = {label[:2] for label in runs if label is not None}
        if found != expected:
            raise ValueError(f"C3 screen needs 3 loss_all arms + none event_only; got {sorted(found)}")
        by_key = {label[:2]: runs[label] for label in runs if label is not None}
        for key in (("loss_all", "event_only"), ("loss_all", "hybrid"),
                    ("loss_all", "reconcile"), ("none", "event_only")):
            arm, fault = key[1], key[0]
            rows.append(_screen_run_row(by_key[key], rung, arm, fault))
        delta = _contrast_delta(by_key[("loss_all", "event_only")],
                                by_key[("loss_all", "hybrid")],
                                by_key[("loss_all", "reconcile")])
        delta_slow = _contrast_delta_slow(by_key[("loss_all", "event_only")],
                                          by_key[("loss_all", "hybrid")],
                                          by_key[("loss_all", "reconcile")])
        confirm_delta = delta_slow if lock_component == "slow" else delta
        event_bad, event_slow, bounded_ok = _event_bounded(
            by_key[("loss_all", "event_only")])
        none_row = next(row for row in rows
                        if row["arm"] == "event_only" and row["cell"] == "none")
        none_health_fail = (
            none_row["gates"].get("control_bad_le_1pct") is False
            or none_row["gates"].get("control_slow_le_2pp") is False)
        seed_gates_ok = all(row["eligible_run"] for row in rows)
        seed_confirm = bool(seed_gates_ok and confirm_delta is not None
                            and confirm_delta >= CONTRAST_PP and bounded_ok)
        # Monotone-gate failure (boundedness / none-cell health) at the first
        # visible rung terminates the family (STOP-NULL); contrast
        # non-reproduction follows the existing next-rung rule (descend).
        verdict = ("lock" if seed_confirm
                   else "stop_null" if (not bounded_ok or none_health_fail)
                   else "descend")
        output = {"stage": "c3", "rung": rung, "seed": args.seed, "runs": rows,
                  "contract_version": 2, "lock_component": lock_component,
                  "delta_pp": round(delta * 100.0, 2) if delta is not None else None,
                  "delta_slow_pp": round(delta_slow * 100.0, 2)
                  if delta_slow is not None else None,
                  "bounded_ok": bounded_ok,
                  "seed_gates_ok": seed_gates_ok,
                  "none_health_fail": none_health_fail,
                  "seed_confirm": seed_confirm,
                  "verdict": verdict}
    else:  # pragma: no cover - argparse restricts choices
        raise ValueError(f"unknown qoe-screen stage: {args.stage}")

    write_json(Path(args.out), output)
    print(json.dumps(output, indent=2, default=str))
    return qoe_screen_exit(output["verdict"])


def _campaign_run_rates(run_dir: Path) -> dict[str, Any]:
    m = qoe_rate_metrics(run_dir)
    return {"run": m["run"], "parts": m["parts"],
            "bad": _pooled_bad(m), "timeout": _pooled_timeout(m),
            "slow": _pooled_slow(m),
            "floors_ok": all(m["floors"].values()),
            "driver_clean": m["driver_clean"]}


def _campaign_mechanisms(run_dir: Path) -> dict[str, Any]:
    result = classify(run_dir)
    return {
        "run": run_dir.name,
        "parts": qoe_label_parts(run_dir.name),
        "preservation": result["preservation"],
        "per_lan_preservation": result["per_lan_preservation"],
        "admitted": result["admitted"],
        "abandoned": result["abandoned"],
        "spawned": result["spawned"],
    }


def qoe_campaign_command(args: argparse.Namespace) -> int:
    run_dirs = [Path(path) for path in args.run_dir]
    rate_rows = {path.name: _campaign_run_rates(path) for path in run_dirs}
    mech_rows = {path.name: _campaign_mechanisms(path) for path in run_dirs}
    cells: dict[tuple[int, str, str], dict[str, Any]] = {}
    for path in run_dirs:
        info = rate_rows[path.name]
        parts = info["parts"]
        if parts is None:
            raise ValueError(f"cannot parse qoe label: {path.name}")
        cell, arm, block = parts
        key = (int(block), cell, arm)
        if key in cells:
            raise ValueError(f"duplicate run for cell/arm/block {key}")
        cells[key] = info
    blocks = sorted({key[0] for key in cells})
    if blocks != list(range(1, 7)):
        raise ValueError(f"expected E blocks 1..6, got {blocks}")

    block_contrast: list[float] = []
    block_slow_contrast: list[float] = []
    block_bad: dict[tuple[int, str], float | None] = {}
    block_slow: dict[tuple[int, str], float | None] = {}
    assessable_blocks: list[int] = []
    assessable_slow_blocks: list[int] = []
    exclusions: dict[int, str] = {}
    exclusions_slow: dict[int, str] = {}
    for block in blocks:
        def val(cell: str, arm: str) -> dict[str, Any]:
            return cells[(block, cell, arm)]
        eo = val("loss_all", "event_only")
        hy = val("loss_all", "hybrid")
        rc = val("loss_all", "reconcile")
        none_eo = val("none", "event_only")
        none_hy = val("none", "hybrid")
        none_rc = val("none", "reconcile")
        for arm in ("event_only", "hybrid", "reconcile"):
            for cell in ("none", "loss_all", "loss_alt"):
                block_bad[(block, cell, arm)] = cells[(block, cell, arm)]["bad"]
                block_slow[(block, cell, arm)] = cells[(block, cell, arm)]["slow"]
        alt_eo = val("loss_alt", "event_only")
        alt_hy = val("loss_alt", "hybrid")
        alt_rc = val("loss_alt", "reconcile")
        controls = [hy["bad"], rc["bad"]]
        controls_slow = [hy["slow"], rc["slow"]]
        floors = all(info["floors_ok"] and info["driver_clean"]
                     for info in (eo, hy, rc, none_eo, none_hy, none_rc,
                                  alt_eo, alt_hy, alt_rc))
        controls_ok = all(value is not None and value <= CONTROL_BAD_MAX
                          for value in controls)
        controls_slow_ok = all(value is not None and value <= SLOW_CONTROL_MAX
                               for value in controls_slow)
        delta = None
        if eo["timeout"] is not None and hy["timeout"] is not None \
                and rc["timeout"] is not None:
            delta = eo["timeout"] - max(hy["timeout"], rc["timeout"])
        delta_slow = None
        if eo["slow"] is not None and hy["slow"] is not None \
                and rc["slow"] is not None:
            delta_slow = eo["slow"] - max(hy["slow"], rc["slow"])
        if floors and controls_ok and delta is not None:
            assessable_blocks.append(block)
            block_contrast.append(delta)
        else:
            reasons = []
            if not floors:
                reasons.append("floors_or_driver_clean")
            if not controls_ok:
                reasons.append("controls_bad_rate_gt_1pct")
            if delta is None:
                reasons.append("missing_timeout")
            exclusions[block] = "|".join(reasons)
        if floors and controls_ok and controls_slow_ok and delta_slow is not None:
            assessable_slow_blocks.append(block)
            block_slow_contrast.append(delta_slow)
        else:
            reasons_slow = []
            if not floors:
                reasons_slow.append("floors_or_driver_clean")
            if not controls_ok:
                reasons_slow.append("controls_bad_rate_gt_1pct")
            if not controls_slow_ok:
                reasons_slow.append("controls_slow_rate_gt_2pp")
            if delta_slow is None:
                reasons_slow.append("missing_slow")
            exclusions_slow[block] = "|".join(reasons_slow)

    # H-Q1 headline contrast + boundedness (timeout-assessable blocks).
    n_assessable = len(assessable_blocks)
    contrast_hits = sum(1 for delta in block_contrast if delta >= CONTRAST_PP)
    contrast_median = statistics.median(block_contrast) if block_contrast else None
    hq1_contrast_pass = (n_assessable >= 4 and contrast_hits >= 4
                         and contrast_median is not None
                         and contrast_median >= CONTRAST_PP)
    # H-Q1b slow-share co-primary (slow-assessable blocks; same statistic
    # shape as H-Q1: hits >=4/6 + median, one-sample MWU/Cliff vs zero).
    n_slow_assessable = len(assessable_slow_blocks)
    slow_hits = sum(1 for delta in block_slow_contrast if delta >= CONTRAST_PP)
    slow_contrast_median = statistics.median(block_slow_contrast) \
        if block_slow_contrast else None
    hq1b_contrast_pass = (n_slow_assessable >= 4 and slow_hits >= 4
                          and slow_contrast_median is not None
                          and slow_contrast_median >= CONTRAST_PP)
    # Boundedness: bad over timeout-assessable blocks; slow over
    # slow-assessable blocks. Both ceilings are hard family requirements
    # regardless of which co-primary fires ("visible AND bounded").
    eo_bads = [block_bad[(block, "loss_all", "event_only")] for block in assessable_blocks]
    eo_bads_num = [value for value in eo_bads if value is not None]
    bounded_hits = sum(1 for value in eo_bads_num if value <= BOUNDED_BAD_MAX)
    bounded_median = statistics.median(eo_bads_num) if eo_bads_num else None
    boundedness_pass = (len(eo_bads_num) >= 4 and bounded_hits >= 4
                        and bounded_median is not None and bounded_median <= BOUNDED_BAD_MAX)
    eo_slows = [block_slow[(block, "loss_all", "event_only")]
                for block in assessable_slow_blocks]
    eo_slows_num = [value for value in eo_slows if value is not None]
    slow_bounded_hits = sum(1 for value in eo_slows_num
                            if value <= SLOW_BOUNDED_EVENT_MAX)
    slow_bounded_median = statistics.median(eo_slows_num) if eo_slows_num else None
    slow_boundedness_pass = (len(eo_slows_num) >= 4 and slow_bounded_hits >= 4
                             and slow_bounded_median is not None
                             and slow_bounded_median <= SLOW_BOUNDED_EVENT_MAX)
    if n_assessable < 4:
        hq1_assessable = False
        boundedness_assessable = False
    else:
        hq1_assessable = True
        boundedness_assessable = True
    if n_slow_assessable < 4:
        hq1b_assessable = False
        slow_boundedness_assessable = False
    else:
        hq1b_assessable = True
        slow_boundedness_assessable = True

    # H-Q2 dose ordering per assessable block + supporting MWU (bad axis).
    order_hits = 0
    dose_pairs: list[tuple[float, float]] = []
    for block in assessable_blocks:
        bad_all = block_bad[(block, "loss_all", "event_only")]
        bad_alt = block_bad[(block, "loss_alt", "event_only")]
        bad_none = block_bad[(block, "none", "event_only")]
        if None in (bad_all, bad_alt, bad_none):
            continue
        if bad_all >= bad_alt >= bad_none:
            order_hits += 1
        dose_pairs.append((bad_all, bad_alt))
    dose_pass = order_hits >= 4
    mwu_dose = (exact_mwu([pair[0] for pair in dose_pairs],
                          [pair[1] for pair in dose_pairs])
                if len(dose_pairs) >= 4 else float("nan"))
    cliffs_dose = (cliffs([pair[0] for pair in dose_pairs],
                          [pair[1] for pair in dose_pairs])
                   if len(dose_pairs) >= 4 else float("nan"))
    # H-Q2b slow-dose ordering (slow axis, slow-assessable blocks).
    slow_order_hits = 0
    slow_dose_pairs: list[tuple[float, float]] = []
    for block in assessable_slow_blocks:
        slow_all = block_slow[(block, "loss_all", "event_only")]
        slow_alt = block_slow[(block, "loss_alt", "event_only")]
        slow_none = block_slow[(block, "none", "event_only")]
        if None in (slow_all, slow_alt, slow_none):
            continue
        if slow_all >= slow_alt >= slow_none:
            slow_order_hits += 1
        slow_dose_pairs.append((slow_all, slow_alt))
    slow_dose_pass = slow_order_hits >= 4
    mwu_slow_dose = (exact_mwu([pair[0] for pair in slow_dose_pairs],
                               [pair[1] for pair in slow_dose_pairs])
                     if len(slow_dose_pairs) >= 4 else float("nan"))
    cliffs_slow_dose = (cliffs([pair[0] for pair in slow_dose_pairs],
                               [pair[1] for pair in slow_dose_pairs])
                        if len(slow_dose_pairs) >= 4 else float("nan"))

    # H-Q3 mechanism carryover via classify().
    preservation_failures: list[str] = []
    loss_alt_observations: list[str] = []
    for name, info in mech_rows.items():
        parts = info["parts"]
        if parts is None:
            continue
        cell, arm, _ = parts
        preservation = info["preservation"]
        if cell == "loss_all":
            if arm == "event_only" and preservation is not None and preservation != 0.0:
                preservation_failures.append(f"H-Q3 {name}: event_only preservation {preservation}")
            if arm in ("hybrid", "reconcile") and preservation is not None \
                    and preservation != 1.0:
                preservation_failures.append(f"H-Q3 {name}: {arm} preservation {preservation}")
        if cell == "loss_alt" and arm == "event_only" and preservation is not None \
                and not (0.3 <= preservation <= 0.7):
            # Hypothesis range only — never a void reason, never a gate.
            loss_alt_observations.append(
                f"H-Q3 {name}: loss_alt event_only preservation {preservation} outside [0.3,0.7]")
        if cell == "loss_alt" and arm in ("hybrid", "reconcile"):
            for lan in (1, 2):
                value = info["per_lan_preservation"].get(lan)
                if value is not None and value != 1.0:
                    preservation_failures.append(
                        f"H-Q3 {name}: loss_alt {arm} lan{lan} preservation {value}")

    # H-Q4 none-cell health floor: bad <=1% AND slow <=2pp, all three arms.
    none_healthy = all(
        (block_bad[(block, "none", arm)] is not None
         and block_bad[(block, "none", arm)] <= CONTROL_BAD_MAX
         and block_slow[(block, "none", arm)] is not None
         and block_slow[(block, "none", arm)] <= SLOW_CONTROL_MAX)
        for block in blocks for arm in ("event_only", "hybrid", "reconcile")
    )

    # Direction checks at blocks 3 (2-of-3) and 5 (3-of-5), per axis.
    def direction_ok(contrasts: list[float], assessable: list[int],
                     limit: int, required: int) -> bool:
        deltas = [contrasts[i]
                  for i, block in enumerate(assessable) if block <= limit]
        return sum(1 for value in deltas if value >= CONTRAST_PP) >= required

    direction_b3 = direction_ok(block_contrast, assessable_blocks, 3, 2)
    direction_b5 = direction_ok(block_contrast, assessable_blocks, 5, 3)
    direction_slow_b3 = direction_ok(block_slow_contrast, assessable_slow_blocks, 3, 2)
    direction_slow_b5 = direction_ok(block_slow_contrast, assessable_slow_blocks, 5, 3)

    # Overall pass: either co-primary certifies (its contrast + its dose);
    # BOTH boundedness components, mechanism carryover and none-cell health
    # are hard requirements regardless of which co-primary fires.
    component_timeout = hq1_contrast_pass and dose_pass
    component_slow = hq1b_contrast_pass and slow_dose_pass
    bounded_all = boundedness_pass and slow_boundedness_pass
    campaign_pass = ((component_timeout or component_slow) and bounded_all
                     and not preservation_failures and none_healthy)

    report: dict[str, Any] = {
        "locked_rung": args.rung,
        "runs": len(run_dirs),
        "assessable_blocks": assessable_blocks,
        "assessable_slow_blocks": assessable_slow_blocks,
        "block_exclusions": exclusions,
        "block_slow_exclusions": exclusions_slow,
        "block_contrasts_pp": [round(value * 100.0, 2) for value in block_contrast],
        "block_slow_contrasts_pp": [round(value * 100.0, 2)
                                    for value in block_slow_contrast],
        "H-Q1": {
            "metric": "timeout_rate",
            "delta_definition": "event_only_loss_all - max(hybrid, reconcile)_loss_all",
            "contrast_ge_5pp_blocks": contrast_hits,
            "contrast_median_pp": round(contrast_median * 100.0, 2)
            if contrast_median is not None else None,
            "assessable": hq1_assessable,
            "pass": hq1_contrast_pass,
            "mwu_p": exact_mwu(block_contrast, [0.0] * len(block_contrast))
            if block_contrast else float("nan"),
            "cliffs_delta": cliffs(block_contrast, [0.0] * len(block_contrast))
            if block_contrast else float("nan"),
            "controls_bad_max_pp": CONTROL_BAD_MAX * 100.0,
        },
        "H-Q1b": {
            "metric": "slow_rate",
            "slow_threshold_s": QOE_SLOW_S,
            "delta_definition": "event_only_loss_all - max(hybrid, reconcile)_loss_all",
            "contrast_ge_5pp_blocks": slow_hits,
            "contrast_median_pp": round(slow_contrast_median * 100.0, 2)
            if slow_contrast_median is not None else None,
            "assessable": hq1b_assessable,
            "pass": hq1b_contrast_pass,
            "mwu_p": exact_mwu(block_slow_contrast, [0.0] * len(block_slow_contrast))
            if block_slow_contrast else float("nan"),
            "cliffs_delta": cliffs(block_slow_contrast,
                                   [0.0] * len(block_slow_contrast))
            if block_slow_contrast else float("nan"),
            "controls_slow_max_pp": SLOW_CONTROL_MAX * 100.0,
        },
        "H-Q1_boundedness": {
            "metric": "bad_rate",
            "event_only_bad_rate_blocks": [round(value, 4) for value in eo_bads_num],
            "median": bounded_median,
            "blocks_le_15pct": bounded_hits,
            "assessable": boundedness_assessable,
            "pass": boundedness_pass,
        },
        "H-Q1b_boundedness": {
            "metric": "slow_rate",
            "event_only_slow_rate_blocks": [round(value, 4) for value in eo_slows_num],
            "median": slow_bounded_median,
            "blocks_le_25pct": slow_bounded_hits,
            "assessable": slow_boundedness_assessable,
            "pass": slow_boundedness_pass,
        },
        "H-Q2": {
            "order_hits": order_hits,
            "pass": dose_pass,
            "mwu_p": mwu_dose,
            "cliffs_delta": cliffs_dose,
        },
        "H-Q2b": {
            "metric": "slow_rate",
            "order_hits": slow_order_hits,
            "pass": slow_dose_pass,
            "mwu_p": mwu_slow_dose,
            "cliffs_delta": cliffs_slow_dose,
        },
        "H-Q3": {"preservation_failures": preservation_failures,
                 "loss_alt_event_only_observations": loss_alt_observations,
                 "pass": not preservation_failures},
        "H-Q4": {"none_cell_healthy": none_healthy, "pass": none_healthy},
        "direction_checks": {"block3_2_of_3": direction_b3,
                             "block5_3_of_5": direction_b5},
        "direction_checks_slow": {"block3_2_of_3": direction_slow_b3,
                                  "block5_3_of_5": direction_slow_b5},
        "component_notes": [],
        "failures": [],
    }
    # Component-level misses are diagnostic notes; they enter "failures" only
    # when no co-primary certifies (pass = not failures, as in stage1).
    component_notes: list[str] = []
    if not hq1_assessable:
        component_notes.append("H-Q1 not assessable (<4 timeout-assessable blocks)")
    elif not hq1_contrast_pass:
        component_notes.append("H-Q1 contrast not reproduced (>=5 pp in >=4/6 + median)")
    if not hq1b_assessable:
        component_notes.append("H-Q1b not assessable (<4 slow-assessable blocks)")
    elif not hq1b_contrast_pass:
        component_notes.append("H-Q1b slow contrast not reproduced (>=5 pp in >=4/6 + median)")
    if not dose_pass:
        component_notes.append("H-Q2 bad-dose ordering not reproduced in >=4/6 blocks")
    if not slow_dose_pass:
        component_notes.append("H-Q2b slow-dose ordering not reproduced in >=4/6 blocks")
    failures: list[str] = []
    if not (component_timeout or component_slow):
        failures.extend(component_notes)
    if not boundedness_pass:
        failures.append(
            "H-Q1 boundedness not assessable (<4 assessable blocks)"
            if len(eo_bads_num) < 4 else
            "H-Q1 boundedness component FAIL "
            "(event_only bad_rate median/>=4 blocks >15%)")
    if not slow_boundedness_pass:
        failures.append(
            "H-Q1b boundedness not assessable (<4 slow-assessable blocks)"
            if len(eo_slows_num) < 4 else
            "H-Q1b boundedness component FAIL "
            "(event_only slow_rate median/>=4 blocks >25%)")
    failures.extend(preservation_failures)
    if not none_healthy:
        failures.append("H-Q4 none-cell health floor violated (bad>1% or slow>2pp)")
    report["component_notes"] = component_notes
    report["failures"] = failures
    # Direction checks are reported, never chased: they never enter "failures"
    # nor affect "pass".
    report["pass"] = campaign_pass
    write_json(Path(args.out), report)
    print(json.dumps({"pass": report["pass"], "assessable_blocks": assessable_blocks,
                      "assessable_slow_blocks": assessable_slow_blocks,
                      "failures": report["failures"]}, indent=2))
    return 0 if report["pass"] else 2


# ---------------------------------------------------------------------------
# Family rq3_timing (2026-09-08, user-approved): readiness-loss relief contrast
# under demand escalation. Single gated axis = slow-share (the timeout class is
# descriptive-only here — the per-phase driver drain truncates long in-flight
# requests, so timeouts can only come from the first ~300 s of the plateau).
# ---------------------------------------------------------------------------

TIMING_LABEL_RE = re.compile(
    r"rq3tim_(none|loss_all)_(event_only|hybrid|reconcile)_(\d+)$")
TIMING_RATE_LADDER = ("2.0", "2.5", "3.0")
TIMING_QUOTA = "0.12"
TIMING_TAIL_S = 300.0           # plateau tail = relief-completion window
TIMING_ONSET_S = 150.0          # onset window = acute demand transient (co-primary)
TIMING_CONTRACT = 2             # contract v2 (2026-09-08): onset-window co-primary
TIMING_TTR_MAX_S = 120.0        # H-T2 time-to-relief bound
TIMING_MEDIAN_MARGIN_PP = 0.07  # preflight power margin on the screen median
TIMING_PRESSURE_MEDIAN_MIN = 60.0  # rq3tim V1: old tier evidenced as bottleneck
TIMING_DYNAMIC_RE = re.compile(r"^edge_server_lan[12]_dyn")


def timing_label_parts(run_name: str) -> tuple[str, str, str] | None:
    match = TIMING_LABEL_RE.search(run_name)
    return (match.group(1), match.group(2), match.group(3)) if match else None


def timing_pressure_ok(m: dict[str, Any]) -> bool:
    """rq3tim V1: old tier evidenced as the bottleneck on the hybrid run.

    Pre-first-ready old-tier pool CPU median >= TIMING_PRESSURE_MEDIAN_MIN on
    both LANs (method pre_first_ready). No p95 upper cap (amendment
    2026-09-08, user-approved): the demand-escalation design makes pre-ready
    p95 spikes expected; regime reasonableness is enforced by relief
    completion, event_only boundedness, and driver-clean instead.
    """
    pressure = m.get("pressure") or {}
    if pressure.get("method") != "pre_first_ready":
        return False
    pre = pressure.get("pre_cpu") or {}
    return all(value.get("median") is not None
               and value["median"] >= TIMING_PRESSURE_MEDIAN_MIN
               for value in pre.values())


def timing_tail_slow(run_dir: Path) -> float | None:
    """slow_rate over the last TIMING_TAIL_S of compute_plateau (pooled).

    Relief-completion gate: controls must recover to healthy slowness in the
    plateau tail (a fixed temporal window, never per-admission attribution).
    """
    rows = request_rows(run_dir)
    bounds = phase_bounds(run_dir)
    start, end = bounds[PHASE]
    tail = [row for row in rows
            if end - TIMING_TAIL_S <= row["_sent"] < end
            and row.get("phase") == PHASE]
    return _qoe_status(tail)["slow_rate"]


def timing_onset_slow(run_dir: Path) -> float | None:
    """slow_rate over the first TIMING_ONSET_S of compute_plateau (pooled).

    Onset-window co-primary (amendment 2026-09-08, user-approved): the
    readiness-loss contrast is onset-transient-dominated, so the acute
    demand-onset window is measured alongside the full plateau. Both deltas
    are primary at the screen (>=5 pp bar) and both carry the lock median
    power margin (>=7 pp). Rows are driver-labeled compute_plateau rows with
    sent_at in [onset, onset+TIMING_ONSET_S).
    """
    rows = request_rows(run_dir)
    bounds = phase_bounds(run_dir)
    start, end = bounds[PHASE]
    onset = [row for row in rows
             if start <= row["_sent"] < min(start + TIMING_ONSET_S, end)
             and row.get("phase") == PHASE]
    return _qoe_status(onset)["slow_rate"]


def timing_relief_metrics(run_dir: Path) -> dict[str, Any]:
    """Plateau-onset -> first new-backend success (time-to-relief, seconds).

    A new backend is any backend_id matching edge_server_lan{1,2}_dynN (the
    X-Backend-ID response header recorded per client row). Onset = the first
    labeled compute_plateau sent_at (driver-labeled rows, not the snapshot).
    """
    rows = request_rows(run_dir)
    bounds = phase_bounds(run_dir)
    onset = bounds[PHASE][0]
    served = [row for row in rows
              if row.get("phase") == PHASE
              and is_completed(row) and is_success(row)
              and TIMING_DYNAMIC_RE.search(row.get("backend_id", "") or "")]
    if not served:
        return {"ttr_s": None, "new_backend_successes": 0,
                "first_success_sent_s": None}
    first = min(row["_sent"] for row in served)
    return {"ttr_s": first - onset, "new_backend_successes": len(served),
            "first_success_sent_s": first}


def _timing_row(path: Path, cell: str, arm: str) -> dict[str, Any]:
    """Screen row for a timing run.

    rq3tim evaluates V1 pressure and control health at the screen level, not
    per row:
      - V1 uses the hybrid run's pre-first-ready median (timing_pressure_ok);
        the reused qoe per-row pressure band ([60,85]/p95<=95) does not apply,
        so per-row pressure is neutralized (both the dict AND the precomputed
        pressure_ok flag that _base_gates actually reads).
      - loss_all control health is the plateau TAIL (relief completion),
        judged at the screen level; a control's full-plateau slow carries the
        legitimate early-window cost and must NOT gate the row.
      - none-cell health (amendment 2026-09-08, user-approved): the no-fault
        cell also pays the universal demand-onset transient (no dynamic
        backend is ready for the first ~40-60 s of the plateau), so a
        full-plateau <=2 pp slow ceiling is structurally unreachable at rate
        S even for a healthy no-fault run. The none-cell slow health floor is
        therefore the plateau TAIL (relief-completion), consistent with the
        loss_all controls; bad stays <=1% on the full plateau.
    """
    metrics = qoe_run_metrics(path)
    metrics = dict(metrics)
    metrics["parts"] = (cell, arm, "1")
    metrics["pressure"] = {
        "pre_cpu": {lan: {"median": 70.0, "p95": 80.0} for lan in (1, 2)},
        "method": "pre_first_ready", "error": None}
    metrics["pressure_ok"] = True
    row = _screen_run_row(metrics, TIMING_QUOTA, arm, cell)
    if cell == "loss_all" and arm in ("hybrid", "reconcile"):
        row["gates"]["control_bad_le_1pct"] = None
        row["gates"]["control_slow_le_2pp"] = None
        row["eligible_run"] = row["base_ok"] and row["mechanism_ok"]
    elif cell == "none":
        # Contract v2 (amendment 2026-09-08): none-cell slow health floor is
        # the plateau TAIL (relief-completion), not the full plateau. bad
        # stays <=1% on the full plateau (full-plateau bad is not inflated by
        # the onset transient the way pooled slow is).
        none_tail = timing_tail_slow(path)
        row["gates"]["control_slow_le_2pp"] = (
            none_tail is not None and none_tail <= SLOW_CONTROL_MAX)
        bad_ok = row["gates"].get("control_bad_le_1pct")
        row["eligible_run"] = row["base_ok"] and row["mechanism_ok"] \
            and (bad_ok is None or bad_ok is True)
    return row


def timing_screen_exit(verdict: str) -> int:
    return {"lock": 0, "candidate": 0, "confirm": 0, "descend": 2,
            "marginal": 2, "stop_null": 3}[verdict]


def _timing_tails(runs: dict[tuple[str, str, str], Path]) -> dict[str, float | None]:
    def tail(arm: str) -> float | None:
        for label, path in runs.items():
            if label[0] == "loss_all" and label[1] == arm:
                return timing_tail_slow(path)
        return None

    return {"hybrid": tail("hybrid"), "reconcile": tail("reconcile")}


def _timing_onsets(runs: dict[tuple[str, str, str], Path]) -> dict[str, float | None]:
    def onset(arm: str) -> float | None:
        for label, path in runs.items():
            if label[0] == "loss_all" and label[1] == arm:
                return timing_onset_slow(path)
        return None

    return {"event_only": onset("event_only"), "hybrid": onset("hybrid"),
            "reconcile": onset("reconcile")}


def _contrast_onset_delta(event_o: float | None, hybrid_o: float | None,
                          reconcile_o: float | None) -> float | None:
    controls = [value for value in (hybrid_o, reconcile_o)
                if value is not None]
    if event_o is None or not controls:
        return None
    return event_o - max(controls)


def timing_screen_command(args: argparse.Namespace) -> int:
    try:
        return _timing_screen_body(args)
    except ValueError as exc:
        # Malformed invocations must never be mistaken for "descend".
        return _qoe_stop(str(exc))


def _timing_screen_body(args: argparse.Namespace) -> int:
    pairs = [(timing_label_parts(Path(path).name), Path(path))
             for path in args.run_dir]
    unparsed = [str(path) for label, path in pairs if label is None]
    if unparsed:
        raise ValueError(f"cannot parse timing labels for: {unparsed}")
    runs = {label: path for label, path in pairs}

    if args.stage == "p1":
        expected = {("loss_all", "event_only"), ("loss_all", "hybrid"),
                    ("loss_all", "reconcile")}
        found = {label[:2] for label in runs}
        if found != expected:
            raise ValueError(f"P1 screen needs the 3 loss_all arms; got {sorted(found)}")
        rows = [_timing_row(runs[label], label[0], label[1])
                for label in sorted(runs)]
        by_arm = {label[1]: qoe_run_metrics(runs[label]) for label in runs}
        delta = _contrast_delta_slow(by_arm["event_only"], by_arm["hybrid"],
                                     by_arm["reconcile"])
        onsets = _timing_onsets(runs)
        onset_delta = _contrast_onset_delta(onsets["event_only"],
                                            onsets["hybrid"],
                                            onsets["reconcile"])
        _, _, bounded_ok = _event_bounded(by_arm["event_only"])
        tails = _timing_tails(runs)
        relief_ok = all(value is not None and value <= SLOW_CONTROL_MAX
                        for value in tails.values())
        # V1 pressure anchors on the hybrid run (30 s pre-first-ready); the
        # rung's spawn epoch is arm-independent, so event_only/reconcile
        # inherit the qualification. Amended 2026-09-08 (user-approved): the
        # escalation design makes pre-ready p95 spikes expected, so V1 = the
        # old tier is the bottleneck = pre-ready median CPU >=60 % (no p95
        # upper cap; collapse guarded by relief completion + boundedness +
        # driver-clean).
        pressure_ok = timing_pressure_ok(by_arm["hybrid"])
        eligible = all(row["eligible_run"] for row in rows) and pressure_ok \
            and relief_ok and delta is not None and onset_delta is not None
        # Contract v2 (amendment 2026-09-08): onset-window Delta is a
        # co-primary -- the candidate/confirm verdict requires BOTH the
        # full-plateau contrast >=5 pp AND the onset-window contrast >=5 pp.
        visible = (delta is not None and delta >= CONTRAST_PP
                   and onset_delta is not None and onset_delta >= CONTRAST_PP)
        verdict = ("stop_null" if eligible and visible and not bounded_ok
                   else "candidate" if eligible and visible and bounded_ok
                   else "descend")
        output = {"stage": "p1", "rate": args.rate, "seed": args.seed,
                  "timing_version": TIMING_CONTRACT, "runs": rows,
                  "delta_slow_pp": round(delta * 100.0, 2)
                  if delta is not None else None,
                  "onset_slow": onsets,
                  "onset_delta_slow_pp": round(onset_delta * 100.0, 2)
                  if onset_delta is not None else None,
                  "control_tail_slow": tails, "relief_ok": relief_ok,
                  "pressure_ok": pressure_ok, "bounded_ok": bounded_ok,
                  "eligible": eligible, "verdict": verdict}
    elif args.stage == "p2":
        expected = {("loss_all", "event_only"), ("loss_all", "hybrid"),
                    ("loss_all", "reconcile"), ("none", "event_only")}
        found = {label[:2] for label in runs}
        if found != expected:
            raise ValueError(
                f"P2 screen needs 3 loss_all arms + none event_only; got {sorted(found)}")
        rows = [_timing_row(runs[label], label[0], label[1])
                for label in sorted(runs)]
        by_arm = {label[1]: qoe_run_metrics(runs[label])
                  for label in runs if label[0] == "loss_all"}
        delta = _contrast_delta_slow(by_arm["event_only"], by_arm["hybrid"],
                                     by_arm["reconcile"])
        onsets = _timing_onsets(runs)
        onset_delta = _contrast_onset_delta(onsets["event_only"],
                                            onsets["hybrid"],
                                            onsets["reconcile"])
        _, _, bounded_ok = _event_bounded(by_arm["event_only"])
        tails = _timing_tails(runs)
        relief_ok = all(value is not None and value <= SLOW_CONTROL_MAX
                        for value in tails.values())
        none_row = next(row for row in rows if row["cell"] == "none")
        none_health_fail = (
            none_row["gates"].get("control_bad_le_1pct") is False
            or none_row["gates"].get("control_slow_le_2pp") is False)
        seed_gates_ok = all(row["eligible_run"] for row in rows)
        # Contract v2 (amendment 2026-09-08): onset-window Delta is a
        # co-primary -- confirm requires BOTH the full-plateau contrast >=5 pp
        # AND the onset-window contrast >=5 pp.
        confirm = bool(seed_gates_ok and relief_ok and bounded_ok
                       and not none_health_fail and delta is not None
                       and delta >= CONTRAST_PP and onset_delta is not None
                       and onset_delta >= CONTRAST_PP)
        # Monotone failures (controls never recover / none-cell sick /
        # unbounded) terminate the family; the rest descends the S ladder.
        verdict = ("confirm" if confirm
                   else "stop_null" if (not bounded_ok or none_health_fail
                                        or not relief_ok)
                   else "descend")
        output = {"stage": "p2", "rate": args.rate, "seed": args.seed,
                  "timing_version": TIMING_CONTRACT, "runs": rows,
                  "delta_slow_pp": round(delta * 100.0, 2)
                  if delta is not None else None,
                  "onset_slow": onsets,
                  "onset_delta_slow_pp": round(onset_delta * 100.0, 2)
                  if onset_delta is not None else None,
                  "control_tail_slow": tails, "relief_ok": relief_ok,
                  "bounded_ok": bounded_ok,
                  "none_health_fail": none_health_fail,
                  "seed_gates_ok": seed_gates_ok, "verdict": verdict}
    elif args.stage == "lock":
        if not args.screen_json:
            raise ValueError("--screen-json is required for --stage lock")
        screens = [json.loads(Path(path).read_text(encoding="utf-8"))
                   for path in args.screen_json]
        for screen in screens:
            if screen.get("timing_version") != TIMING_CONTRACT:
                raise ValueError(
                    f"screen must be timing_version {TIMING_CONTRACT}: "
                    f"{screen.get('timing_version')!r}")
        p1 = next((s for s in screens if s.get("stage") == "p1"), None)
        p2s = [s for s in screens if s.get("stage") == "p2"]
        if p1 is None or not p2s:
            raise ValueError("lock needs exactly one p1 screen plus p2 screens")
        # Contract v2: full-plateau AND onset-window deltas are co-primaries;
        # the lock bar (>=5 pp per screen, >=7 pp median power margin) applies
        # to BOTH.
        deltas = [screen.get("delta_slow_pp") for screen in screens]
        onset_deltas = [screen.get("onset_delta_slow_pp")
                        for screen in screens]
        valid = (all(value is not None and value >= CONTRAST_PP * 100.0
                     for value in deltas)
                 and all(value is not None and value >= CONTRAST_PP * 100.0
                         for value in onset_deltas))
        median = statistics.median([value for value in deltas
                                    if value is not None]) if deltas and all(
            value is not None for value in deltas) else None
        onset_median = statistics.median(
            [value for value in onset_deltas if value is not None]
        ) if onset_deltas and all(value is not None
                                  for value in onset_deltas) else None
        verdict_ok = (p1.get("verdict") == "candidate"
                      and all(s.get("verdict") == "confirm" for s in p2s))
        bounded_all = all(s.get("bounded_ok") is True for s in screens)
        relief_all = all(s.get("relief_ok") is True for s in screens)
        if verdict_ok and valid and bounded_all and relief_all:
            verdict = ("lock" if (median is not None and onset_median is not None
                                  and median >= TIMING_MEDIAN_MARGIN_PP * 100.0
                                  and onset_median
                                  >= TIMING_MEDIAN_MARGIN_PP * 100.0)
                       else "marginal")
        else:
            verdict = "descend"
        output = {"stage": "lock", "rate": args.rate,
                  "timing_version": TIMING_CONTRACT, "screens": len(screens),
                  "deltas_pp": deltas, "median_delta_pp": median,
                  "onset_deltas_pp": onset_deltas,
                  "onset_median_delta_pp": onset_median,
                  "verdict": verdict, "lock": verdict == "lock"}
        if verdict == "lock" and args.lock_out:
            Path(args.lock_out).write_text(json.dumps(
                {"family": "rq3_timing", "rate": args.rate,
                 "quota": TIMING_QUOTA, "timing_version": TIMING_CONTRACT,
                 "screens": len(screens),
                 "deltas_pp": deltas, "median_delta_pp": median,
                 "onset_deltas_pp": onset_deltas,
                 "onset_median_delta_pp": onset_median,
                 "seeds": [screen.get("seed") for screen in screens]},
                indent=2, sort_keys=True) + "\n", encoding="utf-8")
    else:  # pragma: no cover - argparse restricts choices
        raise ValueError(f"unknown timing-screen stage: {args.stage}")

    write_json(Path(args.out), output)
    print(json.dumps(output, indent=2, default=str))
    return timing_screen_exit(output["verdict"])


def timing_campaign_command(args: argparse.Namespace) -> int:
    run_dirs = [Path(path) for path in args.run_dir]
    cells: dict[tuple[int, str, str], Path] = {}
    for path in run_dirs:
        parts = timing_label_parts(path.name)
        if parts is None:
            raise ValueError(f"cannot parse timing label: {path.name}")
        cell, arm, block = parts
        key = (int(block), cell, arm)
        if key in cells:
            raise ValueError(f"duplicate run for cell/arm/block {key}")
        cells[key] = path
    blocks = sorted({key[0] for key in cells})
    if blocks != list(range(1, 7)):
        raise ValueError(f"expected E blocks 1..6, got {blocks}")

    block_delta: list[float] = []
    block_onset_delta: list[float] = []
    assessable: list[int] = []
    exclusions: dict[int, str] = {}
    tail_slow: dict[tuple[int, str], float | None] = {}
    onset_slow: dict[tuple[int, str], float | None] = {}
    none_bad: dict[tuple[int, str], float | None] = {}
    none_slow: dict[tuple[int, str], float | None] = {}
    eo_slows: dict[int, float | None] = {}
    ttrs: dict[int, dict[str, float | None]] = {}
    eo_new_successes: dict[int, int] = {}
    for block in blocks:
        infos = {key: _campaign_run_rates(cells[(block, *key)])
                 for key in (("loss_all", "event_only"), ("loss_all", "hybrid"),
                             ("loss_all", "reconcile"), ("none", "event_only"),
                             ("none", "hybrid"), ("none", "reconcile"))}
        floors = all(info["floors_ok"] and info["driver_clean"]
                     for info in infos.values())
        eo = infos[("loss_all", "event_only")]
        hy = infos[("loss_all", "hybrid")]
        rc = infos[("loss_all", "reconcile")]
        tails = {arm: timing_tail_slow(cells[(block, "loss_all", arm)])
                 for arm in ("hybrid", "reconcile")}
        for arm in ("hybrid", "reconcile"):
            tail_slow[(block, arm)] = tails[arm]
        controls_tail_ok = all(value is not None and value <= SLOW_CONTROL_MAX
                               for value in tails.values())
        delta_slow = None
        if eo["slow"] is not None and hy["slow"] is not None \
                and rc["slow"] is not None:
            delta_slow = eo["slow"] - max(hy["slow"], rc["slow"])
        # Contract v2 co-primary: onset-window Delta (first 150 s of the
        # compute_plateau), event_only - max(hybrid, reconcile).
        on_vals = {arm: timing_onset_slow(cells[(block, "loss_all", arm)])
                   for arm in ("event_only", "hybrid", "reconcile")}
        for arm in ("event_only", "hybrid", "reconcile"):
            onset_slow[(block, arm)] = on_vals[arm]
        onset_delta_slow = None
        if on_vals["event_only"] is not None and on_vals["hybrid"] is not None \
                and on_vals["reconcile"] is not None:
            onset_delta_slow = (on_vals["event_only"]
                                - max(on_vals["hybrid"], on_vals["reconcile"]))
        if floors and controls_tail_ok and delta_slow is not None:
            assessable.append(block)
            block_delta.append(delta_slow)
            block_onset_delta.append(onset_delta_slow)
        else:
            reasons = []
            if not floors:
                reasons.append("floors_or_driver_clean")
            if not controls_tail_ok:
                reasons.append("controls_tail_slow_gt_2pp")
            if delta_slow is None:
                reasons.append("missing_slow")
            exclusions[block] = "|".join(reasons)
        eo_slows[block] = eo["slow"]
        for arm in ("event_only", "hybrid", "reconcile"):
            none_bad[(block, arm)] = infos[("none", arm)]["bad"]
            # Contract v2 (amendment 2026-09-08): none-cell slow health floor
            # is the plateau TAIL (relief-completion), consistent with the
            # loss_all controls and the P2 screen; the full-plateau slow of a
            # no-fault run carries the universal onset transient.
            none_slow[(block, arm)] = timing_tail_slow(
                cells[(block, "none", arm)])
        relief = {arm: timing_relief_metrics(cells[(block, "loss_all", arm)])
                  for arm in ("event_only", "hybrid", "reconcile")}
        ttrs[block] = {arm: relief[arm]["ttr_s"]
                       for arm in ("hybrid", "reconcile")}
        eo_new_successes[block] = relief["event_only"]["new_backend_successes"]

    # H-T1 headline: per-block delta_slow AND onset delta (assessable blocks
    # only). Contract v2 (amendment 2026-09-08): the onset-window contrast is
    # a co-primary -- H-T1 passes only when BOTH the full-plateau contrast and
    # the onset-window contrast hold (>=5 pp in >=4/6 assessable blocks, each
    # median >=5 pp).
    hits = sum(1 for value in block_delta if value >= CONTRAST_PP)
    median = statistics.median(block_delta) if block_delta else None
    h1_full_pass = (len(assessable) >= 4 and hits >= 4
                    and median is not None and median >= CONTRAST_PP)
    onset_hits = sum(1 for value in block_onset_delta
                     if value is not None and value >= CONTRAST_PP)
    onset_deltas_num = [value for value in block_onset_delta
                        if value is not None]
    onset_median = (statistics.median(onset_deltas_num)
                    if onset_deltas_num else None)
    h1_onset_pass = (len(assessable) >= 4 and onset_hits >= 4
                     and onset_median is not None
                     and onset_median >= CONTRAST_PP)
    h1_pass = h1_full_pass and h1_onset_pass
    eo_slows_num = [value for value in (eo_slows[b] for b in assessable)
                    if value is not None]
    bounded_hits = sum(1 for value in eo_slows_num
                       if value <= SLOW_BOUNDED_EVENT_MAX)
    bounded_median = statistics.median(eo_slows_num) if eo_slows_num else None
    boundedness_pass = (len(eo_slows_num) >= 4 and bounded_hits >= 4
                        and bounded_median is not None
                        and bounded_median <= SLOW_BOUNDED_EVENT_MAX)

    # H-T2 relief completion + ordering.
    relief_blocks = [block for block in blocks
                     if tail_slow[(block, "hybrid")] is not None
                     and tail_slow[(block, "hybrid")] <= SLOW_CONTROL_MAX
                     and tail_slow[(block, "reconcile")] is not None
                     and tail_slow[(block, "reconcile")] <= SLOW_CONTROL_MAX]
    ttr_hy = [value for value in (ttrs[b]["hybrid"] for b in blocks)
              if value is not None and value <= TIMING_TTR_MAX_S]
    ttr_rc = [value for value in (ttrs[b]["reconcile"] for b in blocks)
              if value is not None and value <= TIMING_TTR_MAX_S]
    ttr_order = bool(ttr_hy and ttr_rc
                     and statistics.median(ttr_hy) > statistics.median(ttr_rc))
    eo_zero = sum(1 for block in blocks if eo_new_successes[block] == 0) >= 5
    h2_pass = (len(relief_blocks) >= 5 and len(ttr_hy) >= 5 and len(ttr_rc) >= 5
               and ttr_order and eo_zero)

    # H-T3 none-cell health floor (bad <=1% full plateau AND plateau-TAIL
    # slow <=2pp, all arms) -- contract v2 none-cell amendment 2026-09-08.
    none_healthy = all(
        none_bad[(block, arm)] is not None
        and none_bad[(block, arm)] <= CONTROL_BAD_MAX
        and none_slow[(block, arm)] is not None
        and none_slow[(block, arm)] <= SLOW_CONTROL_MAX
        for block in blocks for arm in ("event_only", "hybrid", "reconcile"))

    campaign_pass = h1_pass and boundedness_pass and h2_pass and none_healthy

    report: dict[str, Any] = {
        "family": "rq3_timing", "rate": args.rate,
        "timing_version": TIMING_CONTRACT,
        "runs": len(run_dirs), "assessable_blocks": assessable,
        "block_exclusions": exclusions,
        "block_delta_slow_pp": [round(value * 100.0, 2)
                                 for value in block_delta],
        "block_onset_delta_slow_pp": [round(value * 100.0, 2)
                                       if value is not None else None
                                       for value in block_onset_delta],
        "onset_slow": {f"b{block}_{arm}": onset_slow[(block, arm)]
                       for block in blocks for arm in
                       ("event_only", "hybrid", "reconcile")},
        "H-T1": {"delta_slow_ge_5pp_blocks": hits,
                 "median_pp": round(median * 100.0, 2) if median is not None else None,
                 "onset_delta_ge_5pp_blocks": onset_hits,
                 "onset_median_pp": (round(onset_median * 100.0, 2)
                                      if onset_median is not None else None),
                 "full_pass": h1_full_pass, "onset_pass": h1_onset_pass,
                 "pass": h1_pass,
                 "mwu_p": exact_mwu(block_delta, [0.0] * len(block_delta))
                 if block_delta else float("nan"),
                 "cliffs_delta": cliffs(block_delta, [0.0] * len(block_delta))
                 if block_delta else float("nan")},
        "H-T1_boundedness": {"event_only_slow_blocks":
                             [round(value, 4) for value in eo_slows_num],
                             "median": bounded_median,
                             "blocks_le_25pct": bounded_hits,
                             "pass": boundedness_pass},
        "H-T2": {"relief_blocks": relief_blocks,
                 "ttr_hybrid_s": ttr_hy, "ttr_reconcile_s": ttr_rc,
                 "ttr_order_hybrid_gt_reconcile": ttr_order,
                 "event_only_zero_new_success_blocks": eo_zero,
                 "pass": h2_pass},
        "H-T3": {"none_cell_healthy": none_healthy, "pass": none_healthy},
        "failures": [],
        "pass": campaign_pass,
    }
    if len(assessable) < 4:
        report["failures"].append("H-T1 not assessable (<4 assessable blocks)")
    elif not h1_full_pass:
        report["failures"].append(
            "H-T1 full-plateau contrast not reproduced (>=5 pp in >=4/6 + median)")
    elif not h1_onset_pass:
        report["failures"].append(
            "H-T1 onset-window contrast not reproduced (>=5 pp in >=4/6 + median)")
    if not boundedness_pass:
        report["failures"].append(
            "H-T1 boundedness FAIL (event_only slow_rate median/>=4 blocks >25%)")
    if not h2_pass:
        report["failures"].append("H-T2 relief completion/ordering not reproduced")
    if not none_healthy:
        report["failures"].append("H-T3 none-cell health floor violated (bad>1% or slow>2pp)")
    write_json(Path(args.out), report)
    print(json.dumps({"pass": report["pass"], "assessable_blocks": assessable,
                      "failures": report["failures"]}, indent=2))
    return 0 if report["pass"] else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    classify_parser = sub.add_parser("classify")
    classify_parser.add_argument("--run-dir", nargs="+", required=True)
    classify_parser.add_argument("--out", required=True)
    classify_parser.set_defaults(func=classify_command)
    stage1 = sub.add_parser("stage1")
    stage1.add_argument("--run-dir", nargs="+", required=True)
    stage1.add_argument("--out", required=True)
    stage1.set_defaults(func=stage1_command)
    restart = sub.add_parser("restart-observation")
    restart.add_argument("--run-dir", nargs="+", required=True)
    restart.add_argument("--out", required=True)
    restart.set_defaults(func=restart_command)
    screen = sub.add_parser("qoe-screen")
    screen.add_argument("--stage", required=True, choices=("c1", "c2", "c3"))
    screen.add_argument("--rung", required=True)
    screen.add_argument("--seed", required=True)
    screen.add_argument("--run-dir", nargs="*", default=[])
    screen.add_argument("--c1-json", default=None)
    screen.add_argument("--out", required=True)
    screen.set_defaults(func=qoe_screen_command)
    campaign = sub.add_parser("qoe-campaign")
    campaign.add_argument("--run-dir", nargs="+", required=True)
    campaign.add_argument("--rung", required=True)
    campaign.add_argument("--out", required=True)
    campaign.set_defaults(func=qoe_campaign_command)
    timing_screen = sub.add_parser("timing-screen")
    timing_screen.add_argument("--stage", required=True,
                               choices=("p1", "p2", "lock"))
    timing_screen.add_argument("--rate", required=True)
    timing_screen.add_argument("--seed", required=True)
    timing_screen.add_argument("--run-dir", nargs="*", default=[])
    timing_screen.add_argument("--screen-json", nargs="+", default=[])
    timing_screen.add_argument("--out", required=True)
    timing_screen.add_argument("--lock-out", default=None)
    timing_screen.set_defaults(func=timing_screen_command)
    timing_campaign = sub.add_parser("timing-campaign")
    timing_campaign.add_argument("--run-dir", nargs="+", required=True)
    timing_campaign.add_argument("--rate", required=True)
    timing_campaign.add_argument("--out", required=True)
    timing_campaign.set_defaults(func=timing_campaign_command)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
