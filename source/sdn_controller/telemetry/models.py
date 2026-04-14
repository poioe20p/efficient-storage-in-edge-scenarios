"""Pydantic models for inter-component telemetry messages.

All per-node dicts (``servers``, ``storage_servers``) are keyed by the
node's **MAC address** (e.g. ``"00:00:00:00:00:02"``).  Each container
discovers its own MAC from ``/sys/class/net/eth0/address`` and includes it
in every telemetry event it pushes; the aggregator preserves the key as-is.
"""
from __future__ import annotations

from pydantic import BaseModel


class ServerSummary(BaseModel):
    avg_time_total_ms: float
    avg_time_db_ms: float
    avg_time_proc_ms: float
    request_count: int
    error_rate: float
    avg_cpu_percent: float
    avg_ram_used_mb: float
    last_report_ts: float = 0.0


class StorageServerSummary(BaseModel):
    avg_repl_lag_s: float | None
    avg_connections: float
    avg_cpu_percent: float
    avg_ram_used_mb: float
    sample_count: int
    last_report_ts: float = 0.0
    member_state: str | None = None


class DomainSummary(BaseModel):
    total_requests: int
    avg_time_proc_ms: float
    avg_time_db_ms: float
    average_cpu_percent: float
    peak_time_total_ms: float
    avg_storage_cpu_percent: float = 0.0  # domain average across all storage servers


class TelemetrySummary(BaseModel):
    network_id: str
    window_end: float
    servers: dict[str, ServerSummary]
    storage_servers: dict[str, StorageServerSummary] = {}
    domain_summary: DomainSummary | None = None  # absent in mini-summaries (drain_complete)
    control_events: list[dict] = []  # drain_complete and other control-plane events
