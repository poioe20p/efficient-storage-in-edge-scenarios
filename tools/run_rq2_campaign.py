#!/usr/bin/env python3
"""
Autonomous RQ2 v2 campaign orchestrator (n=6, 36 runs) on cloud-vm-rq2.

Reads the counterbalance order (counterbalance_order_v2.csv), launches each
run via the canonical nohup make chain, waits for completion by polling
active_run.json (same semantics as watch_run.py), then launches the next.
Stops on a failed run (optionally retries once) and writes a campaign log.

Usage:
    python tools/run_rq2_campaign.py \
        --host cloud-vm-rq2 \
        --order docs/operation/testing/experiment/v2/rq2/counterbalance_order_v2.csv \
        [--start-at rq2_cf_cb_2] [--max-retries 1] [--poll-interval 20]

Exit codes:
    0 — all remaining runs completed
    1 — a run failed (after retries) or the campaign was interrupted
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time


# cell -> (env file, phases file, shell CPU vars) relative to the VM repo
# layout. CPU vars are the calibrated per-cell config.
#   Compute-bound cells (cf_cb/ba_cb/sf_cb): Series-C 2026-08-06 (B1 validated).
#   Data-bound cells (cf_db/sf_db/ba_db): storage-bind locked config 2026-08-07
#   (F4a/F4b PASS: edge 1.20 / storage 0.15 / rate 5.0 / lookup-heavy / pool 48).
CELLS: dict[str, tuple[str, str, str]] = {
    "cf_cb": ("rq2_compute_first.env", "phases_rq2_compute_bound.json",
               "STORAGE_CPUS=0.08 EDGE_CPUS=0.15"),
    "cf_db": ("rq2_compute_first.env", "phases_rq2_data_bound.json",
               "STORAGE_CPUS=0.15 EDGE_CPUS=1.20"),
    "sf_cb": ("rq2_storage_first.env", "phases_rq2_compute_bound.json",
               "STORAGE_CPUS=0.15 EDGE_CPUS=0.30"),
    "sf_db": ("rq2_storage_first.env", "phases_rq2_data_bound.json",
               "STORAGE_CPUS=0.15 EDGE_CPUS=1.20"),
    "ba_cb": ("rq2_bottleneck_aware.env", "phases_rq2_compute_bound.json",
               "STORAGE_CPUS=0.08 EDGE_CPUS=0.15"),
    "ba_db": ("rq2_bottleneck_aware.env", "phases_rq2_data_bound.json",
               "STORAGE_CPUS=0.15 EDGE_CPUS=1.20"),
}

REPO = "~/efficient-storage-in-edge-scenarios"
METRICS = f"{REPO}/source/scripts/testing/metrics"
ACTIVE_RUN = f"{METRICS}/active_run.json"

# Shared shell env (pool 48 after the 2026-08-07 storage-bind lock — the
# read-spread enabler for the data-bound cells; CPU vars are per-cell and
# prepended by launch()).
BASE_ENV = ("WAN_RTT_MS=185 RANDOM_SEED=42 "
            "EDGE_MONGO_READ_PREFERENCE=secondaryPreferred "
            "EDGE_MONGO_MAX_POOL_SIZE=48 VIP_DATA_PER_CONNECTION_FLOWS=1")


def ssh(host: str, cmd: str, timeout: int = 15) -> subprocess.CompletedProcess | None:
    """Run a remote command. Returns None on ANY failure (ssh error, timeout,
    missing binary) so callers never crash on transient connectivity issues."""
    try:
        return subprocess.run(
            ["ssh", "-o", "ConnectTimeout=8", "-o", "BatchMode=yes", host, cmd],
            capture_output=True, text=True, timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError):
        return None


def read_active_run(host: str) -> dict | None:
    r = ssh(host, f"cat {ACTIVE_RUN} 2>/dev/null || true")
    if r is not None and r.returncode == 0 and r.stdout.strip():
        try:
            return json.loads(r.stdout)
        except json.JSONDecodeError:
            return None
    return None


def is_run_running(host: str, label: str) -> bool:
    """True if a make/run_experiment process with RUN_LABEL=<label> is alive.

    The last char of the label is bracketed ([x]) so the pgrep regex cannot
    match the checker's own command line (which literally contains the
    pattern) — otherwise pgrep -f always self-matches and reports RUNNING.
    """
    pat = f"RUN_LABEL={label[:-1]}[{label[-1]}]"
    r = ssh(host, f"pgrep -f '{pat}' >/dev/null && echo RUNNING || echo NOT")
    return bool(r is not None and r.stdout.strip() == "RUNNING")


def is_run_completed(host: str, label: str) -> bool:
    """True if a run folder for ``label`` already exists AND is marked
    completed/failed in its run_status.json. Checks the folder directly, so it
    works even when active_run.json points at a later run."""
    r = ssh(host, (
        f"ls -dt {METRICS}/*_{label} 2>/dev/null | head -1 | "
        f"xargs -r grep -h '\"status\"' "
        f"--include=run_status.json -r 2>/dev/null | "
        f"grep -qE 'completed|failed' && echo DONE || echo NOT"
    ))
    return bool(r is not None and r.stdout.strip() == "DONE")


def launch(host: str, label: str, cell: str, env: str, phases: str,
           cpus: str) -> bool:
    """Launch one run via nohup. Returns True if the make chain started."""
    remote = (
        f"cd {REPO} && nohup sudo -n {cpus} {BASE_ENV} "
        f"make -C source/scripts setup_network create_clients setup_test_data "
        f"run_experiment "
        f"OSKEN_ENV_OVERRIDE_FILE=../../rq2_env/{env} "
        f"RUN_LABEL={label} "
        f"PHASES_CONFIG=testing/phases_override/{phases} "
        f"CLIENTS=24 CONTENT_ITEMS=3000 USERS=100 DATA_SEED=42 "
        f"CURL_MAX_TIME=300 TRAFFIC_DRIVER_MODE=open_loop "
        f"INFLIGHT_WINDOW=1024 DRAIN_S=30 "
        f"SKIP_CLIENTS=1 SKIP_SEED=1 SKIP_SNAPSHOT=1 "
        f"> /tmp/{label}.log 2>&1 &"
    )
    print(f"  launching {label} ({cell}) ...", flush=True)
    ssh(host, remote, timeout=20)  # nohup + & makes ssh hang; run continues in bg
    # Give the make chain a moment to spawn, then confirm via process list.
    time.sleep(8)
    up = is_run_running(host, label)
    print(f"    -> {'UP' if up else 'DOWN (launch may have failed)'}", flush=True)
    return up


def wait_completion(host: str, label: str, poll: int, timeout_s: int) -> tuple[int, str]:
    """Poll active_run.json until the label completes/fails. Returns (exit_code, note)."""
    deadline = time.time() + timeout_s
    seen_running = False
    while time.time() < deadline:
        st = read_active_run(host)
        if st and st.get("run_label") == label:
            seen_running = True
            s = st.get("status", "")
            if s == "completed":
                return 0, f"completed (run_id={st.get('run_id')})"
            if s == "failed":
                return st.get("exit_code") or 1, f"failed (run_id={st.get('run_id')})"
        time.sleep(poll)
    return 1, "timeout waiting for completion"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="cloud-vm-rq2")
    ap.add_argument("--order", required=True,
                    help="path to counterbalance_order_v2.csv")
    ap.add_argument("--start-at", default=None,
                    help="run_label to start at (skips earlier rows)")
    ap.add_argument("--max-retries", type=int, default=1)
    ap.add_argument("--poll-interval", type=int, default=20)
    ap.add_argument("--timeout-per-run", type=int, default=4200,
                    help="seconds to wait per run before timing out (default 4200 = 70 min)")
    ap.add_argument("--log", default=None, help="campaign log file (append)")
    args = ap.parse_args()

    with open(args.order, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    plan = [(r["run_label"], r["cell"]) for r in rows]

    log = args.log
    def out(msg: str) -> None:
        line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
        print(line, flush=True)
        if log:
            with open(log, "a", encoding="utf-8") as f:
                f.write(line + "\n")

    if args.start_at:
        idx = next((i for i, (lab, _) in enumerate(plan) if lab == args.start_at), None)
        if idx is None:
            out(f"[error] start_at label {args.start_at} not in order file")
            return 1
        plan = plan[idx:]

    out(f"RQ2 campaign orchestrator: {len(plan)} remaining runs on {args.host}")

    for i, (label, cell) in enumerate(plan, 1):
        env, phases, cpus = CELLS[cell]
        # Skip runs already completed/failed in a run folder (covers runs that
        # finished while active_run.json pointed at a different run).
        if is_run_completed(args.host, label):
            out(f"[{i}/{len(plan)}] {label} already completed — skipping")
            continue

        # If the run is already in flight (e.g. orchestrator restarted after a
        # crash, or a previous run launched it), do NOT re-launch — just wait.
        if is_run_running(args.host, label):
            out(f"[{i}/{len(plan)}] {label} ({cell}) already RUNNING — waiting for it")
            code, note = wait_completion(args.host, label, args.poll_interval,
                                         args.timeout_per_run)
            out(f"  {label} {note}")
            if code != 0:
                out(f"[campaign STOP] run {label} failed")
                return 1
            continue

        attempts = 0
        ok = False
        while attempts <= args.max_retries:
            attempts += 1
            out(f"[{i}/{len(plan)}] {label} ({cell}) attempt {attempts}/{args.max_retries+1}")
            up = launch(args.host, label, cell, env, phases, cpus)
            if not up:
                out(f"  launch not confirmed for {label}; waiting 30s then checking again")
                time.sleep(30)
                up = launch(args.host, label, cell, env, phases, cpus)
            code, note = wait_completion(args.host, label, args.poll_interval,
                                         args.timeout_per_run)
            if code == 0:
                out(f"  {label} {note}")
                ok = True
                break
            out(f"  {label} {note}")
            if attempts > args.max_retries:
                break
            out(f"  retrying {label} ...")
            # Clear stale active_run before retry so the fresh run's status wins.
            ssh(args.host, f"rm -f {ACTIVE_RUN}")
        if not ok:
            out(f"[campaign STOP] run {label} failed after {args.max_retries+1} attempts")
            return 1

    out("RQ2 campaign complete: all remaining runs finished")
    return 0


if __name__ == "__main__":
    sys.exit(main())
