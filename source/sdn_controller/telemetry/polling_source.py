"""Polling telemetry source — polls aggregator HTTP cache endpoints.

Used for RQ1 delivery-cadence evaluation. Implements the same
TelemetryEventSource ABC as ZmqTelemetrySource so the controller is
transport-agnostic.
"""

import logging

import requests
from os_ken.lib import hub

from .models import TelemetrySummary
from .source import TelemetryEventSource

logger = logging.getLogger("os_ken.telemetry.polling_source")


class PollingTelemetrySource(TelemetryEventSource):
    """Polls aggregator /latest_summary endpoints at a fixed interval.

    Deduplicates by window_end so the controller's _on_telemetry_update is
    only called when a genuinely new summary is available — not on every
    poll iteration.
    """

    def __init__(
        self,
        endpoints: list[str],
        interval_s: float = 10.0,
        on_update=None,
        on_topology_update=None,
    ) -> None:
        """
        endpoints:   list of HTTP base URLs to aggregator cache endpoints.
                     Example: ["http://10.0.0.5:5558", "http://10.0.1.5:5558"]
        interval_s:  seconds between poll cycles.
        on_update:   optional callable(summary: TelemetrySummary).
        on_topology_update: not used by polling source (topology comes via
                     a separate mechanism); accepted for interface compatibility.
        """
        self._endpoints = endpoints
        self._interval_s = interval_s
        self._on_update = on_update
        self._on_topology_update = on_topology_update
        self._latest: dict[str, TelemetrySummary] = {} # network_id -> latest summary
        # Dedup: only fire on_update when window_end advances.
        self._last_window_end: dict[str, float] = {} # network_id -> last seen window_end

    # ------------------------------------------------------------------
    # TelemetryEventSource interface
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Spawn the background greenthread that polls aggregators."""
        logger.info(
            "polling telemetry source starting: endpoints=%s interval=%.1fs",
            self._endpoints,
            self._interval_s,
        )
        hub.spawn(self._poll_loop)

    def get_latest(self, network_id: str) -> TelemetrySummary | None:
        return self._latest.get(network_id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _poll_loop(self) -> None:
        while True:
            # Poll all aggregators concurrently so summaries arrive at nearly
            # the same instant — minimises skew between LAN1/LAN2 data views.
            tasks = [hub.spawn(self._poll_one, url) for url in self._endpoints]
            for t in tasks:
                t.wait()
            hub.sleep(self._interval_s)

    def _poll_one(self, url: str) -> None:
        try:
            resp = requests.get(
                f"{url}/latest_summary",
                timeout=5,
            )
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, dict) or not data:
                # Aggregator hasn't produced a summary yet (empty dict).
                return
            summary = TelemetrySummary.model_validate(data)
        except Exception:
            logger.exception("poll failed for %s", url)
            return

        # Mini-summaries (control-event pass-throughs) have empty
        # servers/storage_servers. Do not cache them — they would corrupt
        # WSM cost inputs. This matches ZmqTelemetrySource behavior.
        if not summary.servers and not summary.storage_servers:
            logger.debug("skipping mini-summary from %s", url)
            return

        network_id = summary.network_id
        prev = self._last_window_end.get(network_id, 0.0)

        if summary.window_end > prev:
            # New window — cache and notify.
            self._last_window_end[network_id] = summary.window_end
            self._latest[network_id] = summary
            if self._on_update is not None:
                self._on_update(summary)
            logger.debug(
                "new summary network=%s window_end=%.3f",
                network_id,
                summary.window_end,
            )
        else:
            # Same window as last poll — skip to avoid re-triggering
            # controller logic with identical data.
            logger.debug(
                "duplicate summary network=%s window_end=%.3f (last=%.3f), skipping",
                network_id,
                summary.window_end,
                prev,
            )
