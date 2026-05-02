import os
import statistics
import threading
import time
import logging
from collections import Counter

import zmq

WINDOW_S = float(os.environ.get("WINDOW_S", "10"))
NETWORK_ID = os.environ["NETWORK_ID"]
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")

logger = logging.getLogger("aggregator")

# Duplicated in platform_cache.py and hotness.py (separately-deployed images).
_WRITE_OPS = frozenset({
    "insert_one", "insert_many",
    "update_one", "update_many", "replace_one",
    "delete_one", "delete_many",
    "bulk_write",
    "find_one_and_update", "find_one_and_replace", "find_one_and_delete",
})

# Per-edge cap on the hot-doc list shipped in each ServerSummary.access entry.
# The controller re-trims after merging across edges via SS_HOT_DOC_LIMIT.
SS_TOP_DOCS_PER_EDGE = int(os.environ.get("SS_TOP_DOCS_PER_EDGE", "30"))

_CONTROL_EVENT_TYPES = frozenset({"drain_complete", "rs_secondary_ready"})
_HTTP_REQUIRED_KEYS = frozenset({
    "server_id",
    "time_total_ms",
    "time_db_ms",
    "status_code",
    "cpu_percent",
    "ram_used_mb",
})
_MONGO_REQUIRED_KEYS = frozenset({
    "server_id",
    "connections_current",
    "cpu_percent",
    "ram_used_mb",
})

ctx = zmq.Context()

pull = ctx.socket(zmq.PULL)
_pull_addr = os.environ.get("PULL_ADDR", "tcp://0.0.0.0:5555")
pull.bind(_pull_addr)
logger.info("PULL socket bound to %s", _pull_addr)

pub = ctx.socket(zmq.PUB)
_pub_addr = os.environ.get("PUB_ADDR", "tcp://0.0.0.0:5556")
pub.bind(_pub_addr)
logger.info("PUB socket bound to %s", _pub_addr)

_buffer: list = []
_lock = threading.Lock()


def _is_http_event(event: dict) -> bool:
    return _HTTP_REQUIRED_KEYS.issubset(event)


def _is_mongo_event(event: dict) -> bool:
    return event.get("event_type") == "mongo_stats" and _MONGO_REQUIRED_KEYS.issubset(event)


def _is_heartbeat_event(event: dict) -> bool:
    return event.get("event_type") == "heartbeat" and bool(event.get("server_id"))


def _p95(samples: list[float]) -> float:
    """Return the inclusive p95 for a non-empty sample list."""
    if len(samples) >= 2:
        return statistics.quantiles(samples, n=20, method="inclusive")[18]
    return samples[0]


def _is_selective_sync_event(event: dict) -> bool:
    return (
        isinstance(event.get("selective_sync_per_collection"), dict)
        and bool(event.get("server_mac") or event.get("server_id"))
    )


def _is_known_window_event(event: dict) -> bool:
    return (
        _is_http_event(event)
        or _is_mongo_event(event)
        or _is_heartbeat_event(event)
        or _is_selective_sync_event(event)
    )


def _extract_control_events(event: dict) -> list[dict]:
    etype = event.get("event_type")
    if etype in _CONTROL_EVENT_TYPES:
        return [event]

    controls = event.get("control_events")
    if not isinstance(controls, list):
        return []

    out = []
    for control in controls:
        if not isinstance(control, dict):
            logger.warning("Dropping non-dict control event from frame keys=%s", sorted(event.keys()))
            continue
        if control.get("event_type") not in _CONTROL_EVENT_TYPES:
            logger.warning(
                "Dropping unsupported control event type=%s keys=%s",
                control.get("event_type"), sorted(control.keys()),
            )
            continue
        out.append(control)
    return out


def _publish_control_events(events: list[dict]) -> None:
    if not events:
        return
    mini = {
        "network_id":     NETWORK_ID,
        "window_end":     time.time(),
        "servers":        {},
        "storage_servers": {},
        "control_events": events,
    }
    event_types = [event.get("event_type") for event in events]
    server_ids = [event.get("server_id") for event in events]
    logger.info(
        "Control events received types=%s server_ids=%s - publishing mini-summary",
        event_types, server_ids,
    )
    pub.send_json(mini)


def _log_malformed_events(events: list[dict]) -> None:
    for event in events:
        logger.warning(
            "Dropping malformed telemetry frame keys=%s event_type=%s server_id=%s server_mac=%s",
            sorted(event.keys()),
            event.get("event_type"),
            event.get("server_id"),
            event.get("server_mac"),
        )


def _receive_loop() -> None:
    logger.info("Receive loop started")
    while True:
        event = pull.recv_json()
        if not isinstance(event, dict):
            logger.warning("Dropping non-dict telemetry frame type=%s", type(event).__name__)
            continue
        controls = event.get("control_events")
        control_count = len(controls) if isinstance(controls, list) else 0
        logger.debug(
            "Received event from server_id=%s server_mac=%s event_type=%s control_events=%s",
            event.get("server_id"), event.get("server_mac"), event.get("event_type"),
            control_count,
        )
        control_events = _extract_control_events(event)
        if control_events:
            # Forward control events immediately as mini-summaries and do not
            # buffer them into the aggregation window. The controller needs
            # these signals as fast as possible.
            _publish_control_events(control_events)
            continue  # do not also buffer into the window
        with _lock:
            _buffer.append(event)


def _publish_loop() -> None:
    logger.info("Publish loop started: network_id=%s window=%.1fs", NETWORK_ID, WINDOW_S)
    while True:
        time.sleep(WINDOW_S)
        with _lock:
            window, _buffer[:] = list(_buffer), []

        last_seen: dict[str, float] = {}
        for event in window:
            sid = event.get("server_id")
            ts  = event.get("ts", 0.0)
            if sid and ts > last_seen.get(sid, 0.0):
                last_seen[sid] = ts

        if not window:
            logger.debug("Window empty, skipping publish")
            continue

        http_events  = [e for e in window if _is_http_event(e)]
        mongo_events = [e for e in window if _is_mongo_event(e)]
        heartbeats   = [e for e in window if _is_heartbeat_event(e)]
        # Tier 1 selective-sync supervisor frames — one per Change Stream event
        # per collection. Keyed by ``server_mac`` (not ``server_id``); no
        # ``event_type`` field. See source/docker/edge_selective_storage/telemetry.py.
        ss_events = [e for e in window if _is_selective_sync_event(e)]
        malformed_events = [e for e in window if not _is_known_window_event(e)]
        if malformed_events:
            _log_malformed_events(malformed_events)
        if not (http_events or mongo_events or heartbeats or ss_events):
            logger.debug("Window contained no valid telemetry events, skipping publish")
            continue

        # ── Per-server HTTP stats ─────────────────────────────────────────────
        by_server: dict = {}
        for event in http_events:
            by_server.setdefault(event["server_id"], []).append(event)

        servers = {}
        for server_id, events in by_server.items():
            time_totals = [event["time_total_ms"] for event in events]
            time_db     = [event["time_db_ms"] for event in events]
            time_procs  = [event["time_total_ms"] - event["time_db_ms"] for event in events]
            errors      = sum(1 for event in events if event["status_code"] >= 500)

            # --- Tier 1 selective-sync roll-up ---
            # 1) p95 per owner_lan across every request this server made.
            per_lan_samples: dict[str, list[float]] = {} # {owner_lan: [t_db_ms, t_db_ms, ...]} across every request this server made
            for ev in events:
                # time_db_ms_per_lan is a {owner_lan: t_db_ms}
                for lan, ms in (ev.get("time_db_ms_per_lan") or {}).items():
                    per_lan_samples.setdefault(lan, []).append(ms)
            # p95 computed with stdlib only:
            #   quantiles(n=20) splits samples into 20 equal buckets and returns
            #   the 19 cut points (p5, p10, ..., p95). Index [18] is p95 — the
            #   last cut point. n=20 is the smallest n that lands exactly on p95
            #   (5% granularity) and avoids a numpy dependency.
            #   method="inclusive" treats samples as the full population and
            #   interpolates, so it works for any len >= 2 (the "exclusive"
            #   method would require len >= n+1 = 21 and raise otherwise).
            #   The len==1 branch falls back to the lone sample since no
            #   quantile math is possible with a single point.
            t_db_p95_ms_per_lan = {}
            for lan, samples in per_lan_samples.items():
                t_db_p95_ms_per_lan[lan] = _p95(samples)

            # 2) Leaf-sum op_counts across every request.
            # Create a dict with the number of ops per owner_lan, collection and operation type
            #  across every request this server made.
            # This is the source of truth for op mix and total_hits (derived from non-write ops).
            op_counters: dict[str, dict[str, dict[str, int]]] = {} # {owner_lan: {collection: {op_type: count}}}
            for ev in events:
                # op_counts is a {owner_lan: {collection: {op_type: count}}}
                for owner_lan, by_coll in (ev.get("op_counts") or {}).items():
                    dst_coll = op_counters.setdefault(owner_lan, {})
                    for coll, by_op in by_coll.items():
                        dst_op = dst_coll.setdefault(coll, {})
                        for op, n in by_op.items():
                            dst_op[op] = dst_op.get(op, 0) + n

            # 3) Fold access_records → per (owner, coll) stats.
            #    total_hits is derived from op_counters (op_types ∉ _WRITE_OPS)
            #    so it cannot drift from the op-mix source of truth.
            per_key_doc_hits: dict[tuple[str, str], Counter] = {} # {(owner_lan, collection): Counter(doc_id: count)}
            per_key_xregion: dict[tuple[str, str], int] = {} # {(owner_lan, collection): cross_region_hits}
            for ev in events:
                # access_recors is a [{"owner_lan": str, "collection": str, "doc_id": str}, ...]
                for rec in (ev.get("access_records") or []):
                    key = (rec["owner_lan"], rec["collection"])
                    per_key_doc_hits.setdefault(key, Counter())[rec["doc_id"]] += 1
                    per_key_xregion[key] = per_key_xregion.get(key, 0) + 1

            access_list = []
            for (owner_lan, coll), doc_hits in per_key_doc_hits.items():
                by_op = op_counters.get(owner_lan, {}).get(coll, {})
                total_hits = sum(n for op, n in by_op.items() if op not in _WRITE_OPS)
                access_list.append({
                    "owner_lan":         owner_lan,
                    "collection":        coll,
                    "total_hits":        total_hits,
                    "cross_region_hits": per_key_xregion[(owner_lan, coll)],
                    "top_docs":          doc_hits.most_common(SS_TOP_DOCS_PER_EDGE),
                })

            servers[server_id] = {
                "avg_time_total_ms": statistics.mean(time_totals),
                "avg_time_db_ms":    statistics.mean(time_db),
                "avg_time_proc_ms":  statistics.mean(time_procs),
                "request_count":     len(events),
                "error_rate":        errors / len(events),
                "avg_cpu_percent":   statistics.mean([event["cpu_percent"] for event in events]),
                "avg_ram_used_mb":   statistics.mean([event["ram_used_mb"] for event in events]),
                "last_report_ts":    last_seen.get(server_id, 0.0),
                "avg_time_db_read_ms":   statistics.mean(e.get("time_db_read_ms", 0) for e in events),
                "avg_time_db_write_ms":  statistics.mean(e.get("time_db_write_ms", 0) for e in events),
                "avg_time_db_cmd_count": statistics.mean(e.get("time_db_cmd_count", 0) for e in events),
                # Tier 1 selective-sync fields (default-empty for non-SS workloads).
                "t_db_p95_ms_per_lan":   t_db_p95_ms_per_lan,
                "op_counters":           op_counters,
                "access":                access_list,
            }
            logger.debug(
                "server_id=%s requests=%d error_rate=%.2f avg_total_ms=%.1f avg_db_ms=%.1f",
                server_id, len(events), errors / len(events),
                statistics.mean(time_totals), statistics.mean(time_db),
            )

        # ── Per-server mongo stats ────────────────────────────────────────────
        by_storage: dict = {}
        for event in mongo_events:
            by_storage.setdefault(event["server_id"], []).append(event)

        storage_servers = {}
        for server_id, events in by_storage.items():
            lags = [e["repl_lag_s"] for e in events if e.get("repl_lag_s") is not None]
            storage_servers[server_id] = {
                "avg_repl_lag_s":  statistics.mean(lags) if lags else None,
                "avg_connections": statistics.mean([e["connections_current"] for e in events]),
                "avg_cpu_percent": statistics.mean([e["cpu_percent"] for e in events]),
                "avg_ram_used_mb": statistics.mean([e["ram_used_mb"] for e in events]),
                "sample_count":    len(events),
                "last_report_ts":  last_seen.get(server_id, 0.0),
                "member_state":    events[-1].get("member_state"),
            }

        # ── Heartbeat-only nodes (idle but alive) ─────────────────────────────
        for hb in heartbeats:
            sid = hb.get("server_id")
            if not sid:
                continue
            if "connections_current" in hb:          # storage sidecar heartbeat
                if sid not in storage_servers:
                    storage_servers[sid] = {
                        "avg_repl_lag_s":  hb.get("repl_lag_s"),
                        "avg_connections": float(hb.get("connections_current", 0)),
                        "avg_cpu_percent": hb.get("cpu_percent", 0.0),
                        "avg_ram_used_mb": hb.get("ram_used_mb", 0.0),
                        "sample_count":    0,
                        "last_report_ts":  last_seen.get(sid, hb.get("ts", 0.0)),
                        "member_state":    hb.get("member_state"),
                    }
            else:                                     # edge server heartbeat
                if sid not in servers:
                    servers[sid] = {
                        "avg_time_total_ms": 0.0,
                        "avg_time_db_ms":    0.0,
                        "avg_time_proc_ms":  0.0,
                        "request_count":     0,
                        "error_rate":        0.0,
                        "avg_cpu_percent":   hb.get("cpu_percent", 0.0),
                        "avg_ram_used_mb":   hb.get("ram_used_mb", 0.0),
                        "last_report_ts":    last_seen.get(sid, hb.get("ts", 0.0)),
                    }

        # ── Tier 1 selective-sync frames — last-writer-wins per collection ─────
        # The supervisor pushes one frame per Change Stream event per
        # collection; within a window the freshest observation per collection
        # is what the controller's _is_stale drain check must see, so we walk
        # frames in timestamp order and overwrite each per-collection entry.
        # Averaging would mask a transient lag spike.
        if ss_events:
            ss_events_sorted = sorted(ss_events, key=lambda e: e.get("ts", 0.0))
            for ev in ss_events_sorted:
                mac = ev.get("server_mac") or ev.get("server_id")
                if not mac:
                    continue
                entry = storage_servers.setdefault(mac, {
                    "avg_repl_lag_s":  None,
                    "avg_connections": 0.0,
                    "avg_cpu_percent": 0.0,
                    "avg_ram_used_mb": 0.0,
                    "sample_count":    0,
                    "last_report_ts":  ev.get("ts", 0.0),
                    "member_state":    ev.get("member_state"),
                })
                # Refresh metadata each frame so member_state tracks the
                # freshest report even if the entry was first created by an
                # earlier mongo_stats heartbeat.
                if ev.get("member_state") is not None:
                    entry["member_state"] = ev["member_state"]
                ts = ev.get("ts", 0.0)
                if ts > entry.get("last_report_ts", 0.0):
                    entry["last_report_ts"] = ts
                    last_seen[mac] = ts
                per_coll = entry.setdefault("selective_sync_per_collection", {})
                for coll, stats in ev.get("selective_sync_per_collection", {}).items():
                    per_coll[coll] = {
                        "lag_s":              float(stats.get("lag_s", 0.0)),
                        "resume_token_age_s": float(stats.get("resume_token_age_s", 0.0)),
                        "hot_doc_count":      int(stats.get("hot_doc_count", 0)),
                    }

        # ── Domain summary (HTTP only) ────────────────────────────────────────
        if http_events:
            time_procs_all  = [e["time_total_ms"] - e["time_db_ms"] for e in http_events]
            time_dbs_all    = [e["time_db_ms"] for e in http_events]
            cpus_all        = [e["cpu_percent"] for e in http_events]
            time_totals_all = [e["time_total_ms"] for e in http_events]
            rams_all        = [e["ram_used_mb"] for e in http_events]

            avg_time_proc   = statistics.mean(time_procs_all)
            avg_time_db     = statistics.mean(time_dbs_all)
            p95_time_db     = _p95(time_dbs_all)
            avg_cpu_percent = statistics.mean(cpus_all)
            peak_time_total = max(time_totals_all)
            total_requests  = len(http_events)

            median_time_proc   = statistics.median(time_procs_all)
            median_time_db     = statistics.median(time_dbs_all)
            median_cpu_percent = statistics.median(cpus_all)
            median_time_total  = statistics.median(time_totals_all)
            median_ram_used_mb = statistics.median(rams_all)

            avg_time_db_read_ms   = statistics.mean(e.get("time_db_read_ms", 0) for e in http_events)
            avg_time_db_write_ms  = statistics.mean(e.get("time_db_write_ms", 0) for e in http_events)
            avg_time_db_cmd_count = statistics.mean(e.get("time_db_cmd_count", 0) for e in http_events)
        else:
            avg_time_proc = avg_time_db = avg_cpu_percent = peak_time_total = 0.0
            p95_time_db = 0.0
            median_time_proc = median_time_db = median_cpu_percent = 0.0
            median_time_total = median_ram_used_mb = 0.0
            total_requests = 0
            avg_time_db_read_ms = avg_time_db_write_ms = avg_time_db_cmd_count = 0.0

        # ── Domain-average storage CPU (across all storage server entries) ────
        storage_cpu_values = [
            ss["avg_cpu_percent"]
            for ss in storage_servers.values()
            if ss.get("avg_cpu_percent") is not None
        ]
        avg_storage_cpu_percent = statistics.mean(storage_cpu_values) if storage_cpu_values else 0.0

        storage_ram_values = [
            ss["avg_ram_used_mb"]
            for ss in storage_servers.values()
            if ss.get("avg_ram_used_mb") is not None
        ]
        median_storage_cpu_percent = statistics.median(storage_cpu_values) if storage_cpu_values else 0.0
        median_storage_ram_used_mb = statistics.median(storage_ram_values) if storage_ram_values else 0.0

        summary = {
            "network_id":      NETWORK_ID,
            "window_end":      time.time(),
            "servers":         servers,
            "storage_servers": storage_servers,
            "control_events":  [],
            "domain_summary": {
                "total_requests":          total_requests,
                "avg_time_proc_ms":        avg_time_proc,
                "avg_time_db_ms":          avg_time_db,
                "p95_time_db_ms":          p95_time_db,
                "average_cpu_percent":     avg_cpu_percent,
                "peak_time_total_ms":      peak_time_total,
                "avg_storage_cpu_percent": avg_storage_cpu_percent,
                "median_cpu_percent":          median_cpu_percent,
                "median_ram_used_mb":          median_ram_used_mb,
                "median_storage_cpu_percent":  median_storage_cpu_percent,
                "median_storage_ram_used_mb":  median_storage_ram_used_mb,
                "median_time_proc_ms":         median_time_proc,
                "median_time_db_ms":           median_time_db,
                "median_time_total_ms":        median_time_total,
                "avg_time_db_read_ms":         avg_time_db_read_ms,
                "avg_time_db_write_ms":        avg_time_db_write_ms,
                "avg_time_db_cmd_count":       avg_time_db_cmd_count,
            },
        }
        logger.info(
            "Publishing summary: network_id=%s total_requests=%d avg_cpu=%.1f%% peak_total_ms=%.1f",
            NETWORK_ID,
            summary["domain_summary"]["total_requests"],
            summary["domain_summary"]["average_cpu_percent"],
            summary["domain_summary"]["peak_time_total_ms"],
        )
        logger.debug("Full summary: %s", summary)
        pub.send_json(summary)


threading.Thread(target=_receive_loop, daemon=True).start()
_publish_loop()
