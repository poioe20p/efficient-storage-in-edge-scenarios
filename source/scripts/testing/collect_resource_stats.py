#!/usr/bin/env python3
"""
collect_resource_stats.py

Subscribes to both LAN aggregator ZMQ PUB sockets and writes domain-level
CPU / RAM summaries to a CSV file, one row per LAN per aggregation window.

Designed to run as a background process launched by run_experiment.sh before
the traffic generator starts and stopped (SIGTERM) after it finishes.

Usage:
    python3 collect_resource_stats.py \
      [--lan1-pub tcp://10.0.0.5:5556] \
      [--lan2-pub tcp://10.0.1.5:5556] \
      [--output metrics/resource_stats.csv]
"""

import argparse
import csv
import json
import os
import signal
import statistics
import time

import zmq

from tier1_stats import TIER1_ALL_COLUMNS, build_tier1_row, peer_lan

# ---------------------------------------------------------------------------
# CSV columns
# ---------------------------------------------------------------------------
FIELDNAMES = [
    "timestamp",
    "phase",
    "network_id",
    "window_end",
    "total_requests",
    "median_cpu_percent",
    "median_ram_used_mb",
    "median_storage_cpu_percent",
    "median_storage_ram_used_mb",
    "median_time_proc_ms",
    "median_time_db_ms",
    "median_time_total_ms",
    "server_count",
    "storage_count",
    # --- appended columns ---
    "avg_repl_lag_ms",
    "avg_time_db_read_ms",
    "avg_time_db_write_ms",
    "avg_time_db_cmd_count",
] + TIER1_ALL_COLUMNS

PER_NODE_FIELDNAMES = [
    "timestamp", "phase", "network_id", "window_end",
    "server_id", "role", "request_count",
    "cpu_percent", "ram_used_mb",
    "avg_time_proc_ms", "avg_time_db_ms",
    "avg_time_db_read_ms", "avg_time_db_write_ms", "avg_time_db_cmd_count",
    "avg_repl_lag_s", "member_state", "last_report_ts",
]

# ---------------------------------------------------------------------------
# Graceful shutdown
# ---------------------------------------------------------------------------
_running = True


def _handle_signal(signum, frame):
    global _running
    _running = False


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


# ---------------------------------------------------------------------------
# Domain RAM helpers
# ---------------------------------------------------------------------------

def _mean_or_none(values):
    clean = [v for v in values if v is not None]
    return statistics.mean(clean) if clean else None


def _domain_avg_repl_lag_ms(storage: dict) -> float:
    """Compute mean replication lag in milliseconds across storage nodes."""
    lags = [s.get("avg_repl_lag_s") for s in storage.values()
            if s.get("avg_repl_lag_s") is not None]
    return (statistics.mean(lags) * 1000.0) if lags else 0.0


def _emit_per_node_rows(writer, summary: dict, phase: str, ts: str,
                        network_id: str, window_end) -> None:
    """Write one row per compute and storage container to the per-node CSV."""
    for sid, s in summary.get("servers", {}).items():
        writer.writerow({
            "timestamp": ts, "phase": phase, "network_id": network_id,
            "window_end": window_end, "server_id": sid, "role": "compute",
            "request_count":         s.get("request_count", 0),
            "cpu_percent":           s.get("avg_cpu_percent", ""),
            "ram_used_mb":           s.get("avg_ram_used_mb", ""),
            "avg_time_proc_ms":      s.get("avg_time_proc_ms", ""),
            "avg_time_db_ms":        s.get("avg_time_db_ms", ""),
            "avg_time_db_read_ms":   s.get("avg_time_db_read_ms", ""),
            "avg_time_db_write_ms":  s.get("avg_time_db_write_ms", ""),
            "avg_time_db_cmd_count": s.get("avg_time_db_cmd_count", ""),
            "avg_repl_lag_s":        "", "member_state": "",
            "last_report_ts":        s.get("last_report_ts", ""),
        })
    for sid, s in summary.get("storage_servers", {}).items():
        writer.writerow({
            "timestamp": ts, "phase": phase, "network_id": network_id,
            "window_end": window_end, "server_id": sid, "role": "storage",
            "request_count":         s.get("sample_count", 0),
            "cpu_percent":           s.get("avg_cpu_percent", ""),
            "ram_used_mb":           s.get("avg_ram_used_mb", ""),
            "avg_time_proc_ms":      "", "avg_time_db_ms": "",
            "avg_time_db_read_ms":   "", "avg_time_db_write_ms": "",
            "avg_time_db_cmd_count": "",
            "avg_repl_lag_s":        s.get("avg_repl_lag_s", ""),
            "member_state":          s.get("member_state", "") or "",
            "last_report_ts":        s.get("last_report_ts", ""),
        })


def _extract_domain_ram(summary: dict) -> tuple:
    """
    Compute domain-average RAM for edge servers and storage servers.
    The aggregator's published domain_summary does not include RAM, so we
    average it from the per-server dicts that are also in the payload.

    Returns (avg_ram_used_mb, avg_storage_ram_used_mb) — either may be None.
    """
    servers = summary.get("servers", {})
    storage = summary.get("storage_servers", {})

    ram_edge = _mean_or_none([s.get("avg_ram_used_mb") for s in servers.values()])
    ram_storage = _mean_or_none([s.get("avg_ram_used_mb") for s in storage.values()])
    return ram_edge, ram_storage


def _read_phase(phase_file: str) -> str:
    """Read current phase from the shared phase file. Returns 'transition' on failure."""
    try:
        with open(phase_file, "r") as f:
            phase = f.read().strip()
        return phase if phase else "transition"
    except (FileNotFoundError, OSError):
        return "transition"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Collect CPU/RAM stats from aggregator ZMQ PUB sockets"
    )
    parser.add_argument("--lan1-pub", default="tcp://10.0.0.5:5556", metavar="ADDR")
    parser.add_argument("--lan2-pub", default="tcp://10.0.1.5:5556", metavar="ADDR")
    parser.add_argument(
        "--lan1-coord-pub", default="tcp://127.0.0.1:5561", metavar="ADDR",
        help="LAN1 SDN controller coordinator-state PUB endpoint",
    )
    parser.add_argument(
        "--lan2-coord-pub", default="tcp://127.0.0.1:5562", metavar="ADDR",
        help="LAN2 SDN controller coordinator-state PUB endpoint",
    )
    parser.add_argument(
        "--output", default="metrics/resource_stats.csv", metavar="FILE"
    )
    parser.add_argument(
        "--phase-file", default=None, metavar="FILE",
        help="Path to current_phase.txt written by traffic_generator (default: <output_dir>/current_phase.txt)"
    )
    args = parser.parse_args()

    # Derive phase file path from output directory if not explicitly given
    if args.phase_file is None:
        output_dir = os.path.dirname(args.output)
        args.phase_file = os.path.join(output_dir, "current_phase.txt") if output_dir else "current_phase.txt"

    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    ctx = zmq.Context()

    sub1 = ctx.socket(zmq.SUB)
    sub1.connect(args.lan1_pub)
    sub1.setsockopt_string(zmq.SUBSCRIBE, "")

    sub2 = ctx.socket(zmq.SUB)
    sub2.connect(args.lan2_pub)
    sub2.setsockopt_string(zmq.SUBSCRIBE, "")

    # Coordinator-state subscribers (one per LAN). The controllers publish
    # one frame per telemetry window after evaluate(); we keep the most
    # recent frame per network_id and merge it into outgoing rows.
    coord_sub1 = ctx.socket(zmq.SUB)
    coord_sub1.connect(args.lan1_coord_pub)
    coord_sub1.setsockopt_string(zmq.SUBSCRIBE, "")

    coord_sub2 = ctx.socket(zmq.SUB)
    coord_sub2.connect(args.lan2_coord_pub)
    coord_sub2.setsockopt_string(zmq.SUBSCRIBE, "")

    # Latest coordinator frame keyed by network_id. Empty until first PUB.
    coord_state_by_lan: dict[str, dict] = {}

    poller = zmq.Poller()
    poller.register(sub1, zmq.POLLIN)
    poller.register(sub2, zmq.POLLIN)
    poller.register(coord_sub1, zmq.POLLIN)
    poller.register(coord_sub2, zmq.POLLIN)

    print(
        f"[collect_resource_stats] Subscribing to:\n"
        f"  LAN1: {args.lan1_pub}\n"
        f"  LAN2: {args.lan2_pub}\n"
        f"  LAN1 coord: {args.lan1_coord_pub}\n"
        f"  LAN2 coord: {args.lan2_coord_pub}\n"
        f"  Output: {args.output}\n"
        f"  Phase file: {args.phase_file}",
        flush=True,
    )

    csv_file = open(args.output, "w", newline="")
    writer = csv.DictWriter(csv_file, fieldnames=FIELDNAMES)
    writer.writeheader()
    csv_file.flush()

    per_node_path = os.path.join(output_dir or ".", "per_node_stats.csv")
    per_node_file = open(per_node_path, "w", newline="")
    per_node_writer = csv.DictWriter(per_node_file, fieldnames=PER_NODE_FIELDNAMES)
    per_node_writer.writeheader()
    per_node_file.flush()

    try:
        while _running:
            # 500 ms poll timeout so SIGTERM is handled promptly
            socks = dict(poller.poll(timeout=500))

            # Drain coordinator-state frames first so the next aggregator
            # row sees the freshest snapshot.
            for coord_sock in (coord_sub1, coord_sub2):
                if socks.get(coord_sock) != zmq.POLLIN:
                    continue
                try:
                    raw = coord_sock.recv_string(flags=zmq.NOBLOCK)
                    frame = json.loads(raw)
                except (zmq.ZMQError, json.JSONDecodeError):
                    continue
                lan = frame.get("network_id")
                if lan:
                    coord_state_by_lan[lan] = frame

            for sock in (sub1, sub2):
                if socks.get(sock) != zmq.POLLIN:
                    continue

                raw = sock.recv_string()
                try:
                    summary = json.loads(raw)
                except json.JSONDecodeError:
                    continue

                domain = summary.get("domain_summary")
                if domain is None:
                    # drain_complete mini-summaries carry no domain_summary — skip
                    continue

                row = {
                    "timestamp":                   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "phase":                       _read_phase(args.phase_file),
                    "network_id":                  summary.get("network_id", ""),
                    "window_end":                  summary.get("window_end", ""),
                    "total_requests":              domain.get("total_requests", 0),
                    "median_cpu_percent":           domain.get("median_cpu_percent", ""),
                    "median_ram_used_mb":           domain.get("median_ram_used_mb", ""),
                    "median_storage_cpu_percent":   domain.get("median_storage_cpu_percent", ""),
                    "median_storage_ram_used_mb":   domain.get("median_storage_ram_used_mb", ""),
                    "median_time_proc_ms":          domain.get("median_time_proc_ms", ""),
                    "median_time_db_ms":            domain.get("median_time_db_ms", ""),
                    "median_time_total_ms":         domain.get("median_time_total_ms", ""),
                    "server_count":                len(summary.get("servers", {})),
                    "storage_count":               len(summary.get("storage_servers", {})),
                    "avg_repl_lag_ms":             _domain_avg_repl_lag_ms(summary.get("storage_servers", {})),
                    "avg_time_db_read_ms":         domain.get("avg_time_db_read_ms", ""),
                    "avg_time_db_write_ms":        domain.get("avg_time_db_write_ms", ""),
                    "avg_time_db_cmd_count":       domain.get("avg_time_db_cmd_count", ""),
                }
                network_id = summary.get("network_id", "")
                coord_lan = peer_lan(network_id) if network_id in ("lan1", "lan2") else network_id
                row.update(build_tier1_row(
                    summary,
                    coord_state_by_lan.get(coord_lan, {}),
                ))
                writer.writerow(row)
                csv_file.flush()

                ts_str = row["timestamp"]
                _emit_per_node_rows(
                    per_node_writer, summary,
                    phase=row["phase"], ts=ts_str,
                    network_id=row["network_id"], window_end=row["window_end"],
                )
                per_node_file.flush()

    finally:
        csv_file.close()
        per_node_file.close()
        sub1.close()
        sub2.close()
        coord_sub1.close()
        coord_sub2.close()
        ctx.destroy(linger=0)
        print("[collect_resource_stats] Stopped. Output: " + args.output, flush=True)


if __name__ == "__main__":
    main()
