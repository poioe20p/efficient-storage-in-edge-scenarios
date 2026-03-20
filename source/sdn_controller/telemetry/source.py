from abc import ABC, abstractmethod

from .models import TelemetrySummary


class TelemetryEventSource(ABC):
    """Transport-agnostic interface for telemetry state access.

    All transport-specific configuration (endpoints, credentials, etc.) is
    handled in each implementation's __init__. The controller only ever
    calls start() once at startup, then get_latest() on demand.
    """

    @abstractmethod
    def start(self) -> None:
        """Begin receiving summaries in the background.

        For ZMQ: spawns the daemon receive thread.
        For a future MongoDB source: opens the Change Stream cursor.
        Called once at controller startup.
        """

    @abstractmethod
    def get_latest(self, network_id: str) -> TelemetrySummary | None:
        """Return the most recently received summary for network_id, or None
        if no summary has been received yet.
        """
