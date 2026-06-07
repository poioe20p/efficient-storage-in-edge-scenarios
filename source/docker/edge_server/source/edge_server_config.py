from __future__ import annotations

import os
from dataclasses import dataclass

from compute import TREND_WINDOW_SIZE


@dataclass(frozen=True)
class EdgeServerConfig:
    bind_host: str
    bind_port: int
    db_name: str
    lan_id: str
    db_port: int
    max_idle_ms: int
    tau_dados_ms: float
    drain_poll_interval_s: float
    drain_quiet_period_s: float
    service_pressure_default_window_min: float
    local_request_buffer_target_rps: float
    local_request_buffer_max_events: int
    local_request_per_device_window: int
    service_pressure_default_limit: int
    mongo_client_retire_grace_s: float
    dashboard_candidate_limit: int
    dashboard_integrity_work_factor: int
    mongo_retry_backoff_ms: int
    mongo_retry_max_attempts: int
    mongo_server_selection_timeout_ms: int

    @classmethod
    def from_env(cls) -> "EdgeServerConfig":
        service_pressure_default_window_min = float(
            os.environ.get("SERVICE_PRESSURE_DEFAULT_WINDOW_MIN", "10")
        )
        local_request_buffer_target_rps = float(
            os.environ.get("LOCAL_REQUEST_BUFFER_TARGET_RPS", "120")
        )
        return cls(
            bind_host=os.environ.get("BIND_HOST", "0.0.0.0"),
            bind_port=int(os.environ.get("BIND_PORT", "5000")),
            db_name=os.environ.get("DB_NAME", "edge_platform"),
            lan_id=os.environ.get("LAN_ID", "lan1"),
            db_port=int(os.environ.get("DB_PORT", "27018")),
            max_idle_ms=int(
                os.environ.get(
                    "MAX_IDLE_MS",
                    str(int(os.environ.get("VIP_IDLE_TIMEOUT", "30")) * 1000),
                )
            ),
            tau_dados_ms=float(os.environ.get("TAU_DADOS_MS", "65")),
            drain_poll_interval_s=float(os.environ.get("DRAIN_POLL_INTERVAL_S", "0.5")),
            drain_quiet_period_s=float(os.environ.get("DRAIN_QUIET_PERIOD_S", "1.0")),
            service_pressure_default_window_min=service_pressure_default_window_min,
            local_request_buffer_target_rps=local_request_buffer_target_rps,
            local_request_buffer_max_events=int(
                os.environ.get(
                    "LOCAL_REQUEST_BUFFER_MAX_EVENTS",
                    str(
                        max(
                            5000,
                            int(
                                service_pressure_default_window_min
                                * 60
                                * local_request_buffer_target_rps
                            ),
                        )
                    ),
                )
            ),
            local_request_per_device_window=int(
                os.environ.get(
                    "LOCAL_REQUEST_PER_DEVICE_WINDOW",
                    str(max(TREND_WINDOW_SIZE * 4, 50)),
                )
            ),
            service_pressure_default_limit=int(
                os.environ.get("SERVICE_PRESSURE_DEFAULT_LIMIT", "10")
            ),
            mongo_client_retire_grace_s=float(
                os.environ.get("MONGO_CLIENT_RETIRE_GRACE_S", "30")
            ),
            dashboard_candidate_limit=int(
                os.environ.get("DASHBOARD_CANDIDATE_LIMIT", "500")
            ),
            dashboard_integrity_work_factor=int(
                os.environ.get("DASHBOARD_INTEGRITY_WORK_FACTOR", "200")
            ),
            mongo_retry_backoff_ms=int(
                os.environ.get("MONGO_RETRY_BACKOFF_MS", "100")
            ),
            mongo_retry_max_attempts=int(
                os.environ.get("MONGO_RETRY_MAX_ATTEMPTS", "3")
            ),
            mongo_server_selection_timeout_ms=int(
                os.environ.get("MONGO_SERVER_SELECTION_TIMEOUT_MS", "3000")
            ),
        )


CONFIG = EdgeServerConfig.from_env()