from __future__ import annotations

import os
from dataclasses import dataclass

from compute import TREND_WINDOW_SIZE

# ── Read preference for the VIP read path (data-path fix, 2026-08-03) ────────
# The edge's epoch (read) client connects to the VIP with directConnection=True
# and default readPreference=primary. When the VIP's per-edge flow DNATs the
# connection to a storage SECONDARY, primary-pref reads are rejected server-side
# with NotPrimaryOrSecondary (code 13436) — storage scale-out produced ~zero
# usable read capacity. secondaryPreferred declares secondaryOk so secondaries
# serve reads. Config-gated via EDGE_MONGO_READ_PREFERENCE — default
# secondaryPreferred is the go-to read path (2026-08-03); "primary" is the
# explicit pre-fix opt-out. See
# docs/operation/testing/experiment/v2/read_preference_data_path_finding.md.
# NOTE (probe 2026-08-03): these MUST be mode STRINGS, not pymongo
# ReadPreference instances. pymongo 4.17's MongoClient validation
# (common.validate_read_preference_mode) rejects _ServerMode instances with
# "... is not a valid read preference" and accepts the string form, so the
# probe's reads all failed client-side with ValueError before ever reaching
# the DB. See read_preference_data_path_finding.md.
_READ_PREF_MAP = {
    "primary": "primary",
    "secondarypreferred": "secondaryPreferred",
    "secondary": "secondary",
}


def resolve_mongo_read_preference() -> str:
    """Map the EDGE_MONGO_READ_PREFERENCE string (lowercased, underscores
    stripped) to a pymongo read-preference mode string. Unknown values fall
    back to "secondaryPreferred" (the default go-to read path, 2026-08-03);
    set EDGE_MONGO_READ_PREFERENCE=primary for the pre-fix opt-out. Kept in
    the config module so both the VIP epoch client and the Tier1 manifest
    client can import it without a circular dependency."""
    key = (os.environ.get("EDGE_MONGO_READ_PREFERENCE", "secondaryPreferred").strip()
           .lower().replace("_", ""))
    return _READ_PREF_MAP.get(key, "secondaryPreferred")


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
    local_request_per_content_window: int
    service_pressure_default_limit: int
    mongo_client_retire_grace_s: float
    feed_candidate_limit: int
    feed_integrity_work_factor: int
    mongo_retry_backoff_ms: int
    mongo_retry_max_attempts: int
    mongo_server_selection_timeout_ms: int
    mongo_read_preference: str
    mongo_max_pool_size: int
    mongo_primary_lan1: str
    mongo_primary_lan2: str

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
            local_request_per_content_window=int(
                os.environ.get(
                    "LOCAL_REQUEST_PER_CONTENT_WINDOW",
                    str(max(TREND_WINDOW_SIZE * 4, 50)),
                )
            ),
            service_pressure_default_limit=int(
                os.environ.get("SERVICE_PRESSURE_DEFAULT_LIMIT", "10")
            ),
            mongo_client_retire_grace_s=float(
                os.environ.get("MONGO_CLIENT_RETIRE_GRACE_S", "30")
            ),
            feed_candidate_limit=int(
                os.environ.get("FEED_CANDIDATE_LIMIT", "500")
            ),
            feed_integrity_work_factor=int(
                os.environ.get("FEED_INTEGRITY_WORK_FACTOR", "200")
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
            # Read preference for the VIP-based read path (epoch client).
            # Default "secondaryPreferred" (the go-to path, 2026-08-03) lets
            # the VIP's per-edge flows be served by storage secondaries.
            # "primary" is the explicit pre-fix opt-out. See
            # docs/operation/testing/experiment/v2/read_preference_data_path_finding.md.
            mongo_read_preference=os.environ.get(
                "EDGE_MONGO_READ_PREFERENCE", "secondaryPreferred"
            ),
            # MongoDB connection-pool size for the VIP read path (Approach B,
            # 2026-08-03). Default 1 = one connection per edge, pinned to one
            # storage backend (pre-fix behavior; RQ1/RQ3 byte-identical).
            # >1 fans an edge's connections out across storage backends when
            # the controller runs with VIP_DATA_PER_CONNECTION_FLOWS=1.
            mongo_max_pool_size=int(
                os.environ.get("EDGE_MONGO_MAX_POOL_SIZE", "1")
            ),
            mongo_primary_lan1=os.environ.get(
                "EDGE_MONGO_PRIMARY_LAN1", "mongodb://10.0.0.4:27018/"
            ),
            mongo_primary_lan2=os.environ.get(
                "EDGE_MONGO_PRIMARY_LAN2", "mongodb://10.0.1.4:27018/"
            ),
        )


CONFIG = EdgeServerConfig.from_env()