"""Pydantic models for inter-component telemetry messages.

All per-node dicts (``servers``, ``storage_servers``) are keyed by the
node's **MAC address** (e.g. ``"00:00:00:00:00:02"``).  Each container
discovers its own MAC from ``/sys/class/net/eth0/address`` and includes it
in every telemetry event it emits; the aggregator preserves the key as-is.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class EdgeAccessStats(BaseModel):
    """Per-(owner_lan, collection) hotness slice produced by the aggregator
    from the wrapped edge-server reads within one telemetry window.

    Emitted by ``source/docker/local_state_server/aggregator.py`` as part of
    each ``ServerSummary.access`` list. Consumed by
    ``source/sdn_controller/selective_sync/hotness.py``.

    See ``docs/operation/telemetry/telemetry_overview.md``.
    """
    owner_lan: str
    collection: str
    total_hits: int
    cross_region_hits: int
    # pydantic accepts list[list] here since JSON has no tuple; we keep the
    # two-element inner shape by convention (doc_id, hits).
    top_docs: list[tuple[str, int]] = [] # [ (doc_id, hits), ... ]


class ServerSummary(BaseModel):
    avg_time_total_ms: float
    avg_time_db_ms: float
    avg_time_proc_ms: float
    request_count: int
    error_rate: float
    avg_cpu_percent: float
    avg_ram_used_mb: float
    last_report_ts: float = 0.0
    # New — defaulted for backward compatibility with pre-decomposition aggregators.
    avg_time_db_read_ms: float = 0.0
    avg_time_db_write_ms: float = 0.0
    avg_time_db_cmd_count: float = 0.0
    # Tier 1 selective-sync fields (defaulted empty; populated by the aggregator
    # from per-request events enriched by the platform_cache wrapper).
    access: list[EdgeAccessStats] = []
    t_db_p95_ms_per_lan: dict[str, float] = {}
    # {owner_lan: {collection: {op_type: count}}} over the window.
    op_counters: dict[str, dict[str, dict[str, int]]] = {} # 
    state: Literal["active", "draining"] = "active"


class StorageServerSummary(BaseModel):
    avg_repl_lag_s: float | None = None
    avg_connections: float = 0.0
    avg_cpu_percent: float = 0.0
    avg_ram_used_mb: float = 0.0
    sample_count: int = 0
    last_report_ts: float = 0.0
    member_state: str | None = None
    # Tier 1 selective-sync per-collection lag/resume-token/hot-doc snapshot,
    # populated by the aggregator from frames pushed by the
    # edge_selective_storage supervisor (see
    # source/docker/edge_selective_storage/telemetry.py). Absent for full
    # replicas and compute nodes. Merge rule is *last-writer-wins* per
    # collection within a window — see aggregator.
    selective_sync_per_collection: dict[str, "SelectiveSyncCollectionStats"] | None = None


class SelectiveSyncCollectionStats(BaseModel):
    """Per-collection forwarder health for a Tier 1 selective-sync container.

    See ``docs/operation/elasticy_manager/implementation/tier1_selective_sync/telemetry_and_config.md``.
    """
    lag_s: float
    resume_token_age_s: float
    hot_doc_count: int


class DomainSummary(BaseModel):
    total_requests: int
    avg_time_proc_ms: float
    avg_time_db_ms: float
    p95_time_db_ms: float = 0.0
    average_cpu_percent: float
    peak_time_total_ms: float
    avg_storage_cpu_percent: float = 0.0  # domain average across all storage servers
    avg_time_db_read_ms: float = 0.0
    avg_time_db_write_ms: float = 0.0
    avg_time_db_cmd_count: float = 0.0
    # ── Recovery-distress signal ───────────────────────────────────────
    # Aggregated request-lease outcome counters per LAN.
    # Keys: "lan1", "lan2". Each value is {outcome: count} where outcome
    # is one of "success_normal", "success_after_rebind", "failure_terminal".
    request_lease_outcomes_per_lan: dict[str, dict[str, int]] = {}


class TelemetrySummary(BaseModel):
    network_id: str
    window_end: float
    servers: dict[str, ServerSummary]
    storage_servers: dict[str, StorageServerSummary] = {}
    domain_summary: DomainSummary | None = None  # absent in mini-summaries (drain_complete)
    control_events: list[dict] = []  # drain_complete and other control-plane events
