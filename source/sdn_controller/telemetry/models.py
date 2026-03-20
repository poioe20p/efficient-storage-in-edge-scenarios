from pydantic import BaseModel


class ServerSummary(BaseModel):
    avg_time_total_ms: float
    avg_time_db_ms: float
    avg_time_proc_ms: float
    request_count: int
    error_rate: float
    avg_cpu_percent: float
    avg_ram_used_mb: float


class DomainSummary(BaseModel):
    total_requests: int
    avg_time_proc_ms: float
    avg_time_db_ms: float
    average_cpu_percent: float
    peak_time_total_ms: float


class TelemetrySummary(BaseModel):
    network_id: str
    window_end: float
    servers: dict[str, ServerSummary]
    domain_summary: DomainSummary
