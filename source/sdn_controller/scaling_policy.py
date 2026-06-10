"""scaling_policy.py — Scaling decision engine (Strategy pattern).

Owns sliding-window deques and cooldown timestamps. Evaluates DomainSummary
metrics and returns scaling decisions. Does NOT submit alerts or access
the ElasticityManager — the mediator handles that.

Thread safety: all methods are called exclusively from Thread 2.
"""

import logging
import time
from collections import deque

from .scaling_config import (
    _W_STORAGE_CPU, _W_T_DB,
    _STORAGE_CPU_FLOOR, _STORAGE_CPU_SPAN,
    _T_DB_FLOOR, _T_DB_SPAN,
    _W_CPU, _W_T_PROC,
    _CPU_FLOOR, _CPU_SPAN,
    _T_PROC_FLOOR, _T_PROC_SPAN,
    _SCALE_UP_WINDOW_SIZE, _SCALE_UP_REQUIRED,
    _SCALEUP_COMPUTE_BASE_THRESHOLD, _SCALEUP_COMPUTE_THRESHOLD_INCREMENT,
    _SCALEUP_COMPUTE_MAX_THRESHOLD, _SCALEUP_COMPUTE_COOLDOWN_S,
    _SCALEUP_COMPUTE_PEER_RELIEF, _SCALEUP_COMPUTE_PEER_HEALTH_THRESHOLD,
    _SCALEUP_STORAGE_BASE_THRESHOLD, _SCALEUP_STORAGE_THRESHOLD_INCREMENT,
    _SCALEUP_STORAGE_MIN_INCREMENT, _SCALEUP_STORAGE_MAX_THRESHOLD,
    _SCALEUP_STORAGE_WINDOW_SIZE,
    _SCALEUP_STORAGE_REQUIRED,
    _TAU_CPU_DOWN, _TAU_PROC_DOWN_MS,
    _TAU_STORAGE_CPU_DOWN, _TAU_DB_DOWN_MS,
    _SCALE_DOWN_PROC_TIMEOUT_CEILING_MS, _SCALE_DOWN_DB_TIMEOUT_CEILING_MS,
    _SCALE_DOWN_COMPUTE_WINDOW_SIZE, _SCALE_DOWN_COMPUTE_REQUIRED,
    _SCALE_DOWN_STORAGE_WINDOW_SIZE, _SCALE_DOWN_STORAGE_REQUIRED,
    _SCALEDOWN_STORAGE_COOLDOWN_S, _SCALEDOWN_COMPUTE_COOLDOWN_S,
    _SCALEUP_STORAGE_COOLDOWN_S,
    _MAX_DYNAMIC_STORAGE, _MAX_DYNAMIC_COMPUTE,
)
from .elasticity.elasticity import ComputeAlert, DataAlert
from .telemetry.models import DomainSummary

logger = logging.getLogger('os_ken.scaling_policy')


class ScalingPolicy:
    """Decides whether to scale up or down based on DomainSummary metrics.

    Returns scaling decisions — does NOT submit alerts directly.
    """

    def __init__(self) -> None:
        # Scale-up sliding windows
        self._scale_up_compute_window: deque[bool] = deque(maxlen=_SCALE_UP_WINDOW_SIZE)
        self._scale_up_storage_window: deque[bool] = deque(maxlen=_SCALEUP_STORAGE_WINDOW_SIZE)
        # Scale-down sliding windows
        self._scale_down_compute_window: deque[bool] = deque(maxlen=_SCALE_DOWN_COMPUTE_WINDOW_SIZE)
        self._scale_down_storage_window: deque[bool] = deque(maxlen=_SCALE_DOWN_STORAGE_WINDOW_SIZE)
        # Cooldown timestamps (initialised to -inf → no cooldown at startup)
        self._last_storage_scale_up_ts: float = float('-inf')
        self._last_compute_scale_up_ts: float = float('-inf')
        # Previous armed state — used to detect the False → True rising edge
        self._prev_scale_down_compute_armed: bool = False
        self._prev_scale_down_storage_armed: bool = False

        logger.info(
            "scale-up: compute[τ_base=%.2f incr=%.2f cap=%.2f window=%d/%d cooldown=%.0fs "
            "peer_relief=%.2f w_cpu=%.1f w_lat=%.1f max_nodes=%d]  "
            "storage[τ_base=%.2f incr=%.2f cap=%.2f window=%d/%d "
            "w_cpu=%.1f w_lat=%.1f cooldown=%.0fs max_nodes=%d]",
            _SCALEUP_COMPUTE_BASE_THRESHOLD,
            _SCALEUP_COMPUTE_THRESHOLD_INCREMENT,
            _SCALEUP_COMPUTE_MAX_THRESHOLD,
            _SCALE_UP_REQUIRED, _SCALE_UP_WINDOW_SIZE,
            _SCALEUP_COMPUTE_COOLDOWN_S,
            _SCALEUP_COMPUTE_PEER_RELIEF,
            _W_CPU, _W_T_PROC,
            _MAX_DYNAMIC_COMPUTE,
            _SCALEUP_STORAGE_BASE_THRESHOLD, _SCALEUP_STORAGE_THRESHOLD_INCREMENT,
            _SCALEUP_STORAGE_MAX_THRESHOLD, _SCALEUP_STORAGE_REQUIRED, _SCALEUP_STORAGE_WINDOW_SIZE,
            _W_STORAGE_CPU, _W_T_DB, _SCALEUP_STORAGE_COOLDOWN_S,
            _MAX_DYNAMIC_STORAGE,
        )

    # ── Pure helpers ─────────────────────────────────────────────────────

    @staticmethod
    def degradation_score(cpu: float, latency: float,
                          w_cpu: float, w_lat: float,
                          cpu_floor: float, cpu_span: float,
                          lat_floor: float, lat_span: float) -> float:
        """Weighted degradation score in [0, w_cpu + w_lat].

        Both components saturate at 1.0 so a single extreme latency window
        cannot dominate the sliding-window hit count; sustained badness is
        expressed via WINDOW_SIZE / REQUIRED instead of unbounded magnitude.
        """
        cpu_component = min(1.0, max(0.0, cpu - cpu_floor) / cpu_span) if cpu_span else 0.0
        lat_component = min(1.0, max(0.0, latency - lat_floor) / lat_span) if lat_span else 0.0
        return w_cpu * cpu_component + w_lat * lat_component

    @staticmethod
    def storage_latency_signal(ds: DomainSummary) -> float:
        """Use a tail-aware DB latency signal for predictive storage scale-up."""
        return max(ds.avg_time_db_ms, ds.p95_time_db_ms)

    # ── Cooldown queries ─────────────────────────────────────────────────

    def compute_cooldown_remaining(self) -> float:
        return max(0.0, _SCALEDOWN_COMPUTE_COOLDOWN_S - (time.monotonic() - self._last_compute_scale_up_ts))

    def storage_cooldown_remaining(self) -> float:
        return max(0.0, _SCALEDOWN_STORAGE_COOLDOWN_S - (time.monotonic() - self._last_storage_scale_up_ts))

    def compute_scaleup_cooldown_remaining(self) -> float:
        return max(0.0, _SCALEUP_COMPUTE_COOLDOWN_S - (time.monotonic() - self._last_compute_scale_up_ts))

    def storage_scaleup_cooldown_remaining(self) -> float:
        return max(0.0, _SCALEUP_STORAGE_COOLDOWN_S - (time.monotonic() - self._last_storage_scale_up_ts))

    def record_storage_activation(self) -> None:
        """Bookkeeping after a reserve activation: reset cooldown and scale-down window.

        Called by the mediator after a reserved storage node is consumed
        into active service. This is the same cross-direction reset that a
        normal ``DataAlert`` submission would trigger inside
        ``_evaluate_storage_scale_up``.
        """
        self._last_storage_scale_up_ts = time.monotonic()
        self.clear_scale_down_storage_window()

    # ── Scale-up evaluation ──────────────────────────────────────────────

    def evaluate_scale_up(self, ds: DomainSummary, lan: int, network_id: str,
                          dynamic_storage_count: int,
                          dynamic_compute_count: int,
                          peer_ds: DomainSummary | None = None,
                          *,
                          allow_compute: bool = True,
                          allow_storage: bool = True) -> list[ComputeAlert | DataAlert]:
        """Evaluate Compute and Storage scale-up. Returns list of alerts to submit."""
        alerts: list[ComputeAlert | DataAlert] = []

        # ── Compute ──
        if allow_compute:
            remaining = self.compute_scaleup_cooldown_remaining()
            if remaining > 0:
                logger.debug("[scale-up] compute within %.0fs scale-up cooldown — skipping", remaining)
            else:
                compute_alert = self._evaluate_compute_scale_up(
                    ds, lan, network_id, dynamic_compute_count, peer_ds
                )
                if compute_alert:
                    alerts.append(compute_alert)

        # ── Storage (with its own scale-up cooldown) ──
        if allow_storage:
            remaining = self.storage_scaleup_cooldown_remaining()
            if remaining > 0:
                logger.debug("[scale-up] storage within %.0fs scale-up cooldown — skipping", remaining)
            else:
                storage_alert = self._evaluate_storage_scale_up(ds, lan, network_id, dynamic_storage_count)
                if storage_alert:
                    alerts.append(storage_alert)

        return alerts

    def _compute_peer_relief(self, peer_ds: DomainSummary | None) -> tuple[float, float | None]:
        if peer_ds is None:
            return 0.0, None

        peer_score = self.degradation_score(
            peer_ds.average_cpu_percent, peer_ds.avg_time_proc_ms,
            _W_CPU, _W_T_PROC,
            _CPU_FLOOR, _CPU_SPAN,
            _T_PROC_FLOOR, _T_PROC_SPAN,
        )
        if peer_score <= _SCALEUP_COMPUTE_PEER_HEALTH_THRESHOLD:
            return _SCALEUP_COMPUTE_PEER_RELIEF, peer_score
        return 0.0, peer_score

    def _evaluate_compute_scale_up(self, ds: DomainSummary, lan: int,
                                   network_id: str,
                                   dynamic_compute_count: int,
                                   peer_ds: DomainSummary | None) -> ComputeAlert | None:
        if dynamic_compute_count >= _MAX_DYNAMIC_COMPUTE:
            logger.debug(
                "[scale-up] compute cap reached (%d/%d) — skipping",
                dynamic_compute_count, _MAX_DYNAMIC_COMPUTE,
            )
            return None

        compute_score = self.degradation_score(
            ds.average_cpu_percent, ds.avg_time_proc_ms,
            _W_CPU, _W_T_PROC,
            _CPU_FLOOR, _CPU_SPAN,
            _T_PROC_FLOOR, _T_PROC_SPAN,
        )

        base_threshold = min(
            _SCALEUP_COMPUTE_BASE_THRESHOLD
            + dynamic_compute_count * _SCALEUP_COMPUTE_THRESHOLD_INCREMENT,
            _SCALEUP_COMPUTE_MAX_THRESHOLD,
        )
        peer_relief, peer_score = self._compute_peer_relief(peer_ds)
        effective_threshold = min(
            base_threshold + peer_relief,
            _SCALEUP_COMPUTE_MAX_THRESHOLD,
        )

        above = compute_score >= effective_threshold
        self._scale_up_compute_window.append(above)
        peer_score_display = "n/a" if peer_score is None else f"{peer_score:.2f}"
        window_hits = sum(self._scale_up_compute_window)
        window_size = len(self._scale_up_compute_window)
        logger.debug(
            "[scale-up] compute score=%.2f (τ_eff=%.2f, τ_base=%.2f, peer_relief=%.2f, peer_score=%s, dyn=%d) "
            "cpu=%.1f%% T_proc=%.1fms window=%d/%d on %s",
            compute_score, effective_threshold, base_threshold, peer_relief,
            peer_score_display, dynamic_compute_count,
            ds.average_cpu_percent, ds.avg_time_proc_ms,
            window_hits, window_size,
            network_id,
        )
        if window_hits >= _SCALE_UP_REQUIRED:
            logger.info(
                "[scale-up] compute triggered: %d/%d windows ≥ %.2f "
                "(τ_eff=%.2f, τ_base=%.2f, peer_relief=%.2f, peer_score=%s, dyn=%d, last score=%.2f, cpu=%.1f%%, T_proc=%.1fms) on %s",
                window_hits,
                window_size,
                effective_threshold,
                effective_threshold,
                base_threshold,
                peer_relief,
                peer_score_display,
                dynamic_compute_count,
                compute_score,
                ds.average_cpu_percent, ds.avg_time_proc_ms, network_id,
            )
            self._scale_up_compute_window.clear()
            self._scale_down_compute_window.clear()  # cross-direction reset
            self._last_compute_scale_up_ts = time.monotonic()
            return ComputeAlert(lan=lan, network_id=network_id)
        return None

    def _evaluate_storage_scale_up(self, ds: DomainSummary, lan: int,
                                   network_id: str,
                                   dynamic_storage_count: int) -> DataAlert | None:
        if dynamic_storage_count >= _MAX_DYNAMIC_STORAGE:
            logger.debug(
                "[scale-up] storage cap reached (%d/%d) — skipping",
                dynamic_storage_count, _MAX_DYNAMIC_STORAGE,
            )
            return None

        storage_latency_ms = self.storage_latency_signal(ds)
        storage_score = self.degradation_score(
            ds.avg_storage_cpu_percent, storage_latency_ms,
            _W_STORAGE_CPU, _W_T_DB,
            _STORAGE_CPU_FLOOR, _STORAGE_CPU_SPAN,
            _T_DB_FLOOR, _T_DB_SPAN,
        )
        # Adaptive threshold: diminishing increment per node (halves each node, floored)
        cumulative = sum(
            max(_SCALEUP_STORAGE_THRESHOLD_INCREMENT * 0.5 ** i,
                _SCALEUP_STORAGE_MIN_INCREMENT)
            for i in range(dynamic_storage_count)
        )
        effective_threshold = min(
            _SCALEUP_STORAGE_BASE_THRESHOLD + cumulative,
            _SCALEUP_STORAGE_MAX_THRESHOLD,
        )
        above = storage_score >= effective_threshold
        self._scale_up_storage_window.append(above)
        logger.debug(
            "[scale-up] storage score=%.2f (τ_eff=%.2f, base=%.2f +Σdim(%d)=%.3f) "
            "cpu_s=%.1f%% T_db_avg=%.1fms T_db_p95=%.1fms signal=%.1fms  window=%d/%d on %s",
            storage_score, effective_threshold,
            _SCALEUP_STORAGE_BASE_THRESHOLD, dynamic_storage_count, cumulative,
            ds.avg_storage_cpu_percent, ds.avg_time_db_ms, ds.p95_time_db_ms, storage_latency_ms,
            sum(self._scale_up_storage_window), len(self._scale_up_storage_window),
            network_id,
        )
        if sum(self._scale_up_storage_window) >= _SCALEUP_STORAGE_REQUIRED:
            logger.info(
                "[scale-up] storage triggered: %d/%d windows ≥ %.2f "
                "(eff_τ=%.2f, dyn_nodes=%d, Σdim=%.3f, last score=%.2f, cpu_s=%.1f%%, T_db_avg=%.1fms, T_db_p95=%.1fms, signal=%.1fms) on %s",
                sum(self._scale_up_storage_window),
                len(self._scale_up_storage_window),
                effective_threshold, effective_threshold, dynamic_storage_count,
                cumulative, storage_score,
                ds.avg_storage_cpu_percent, ds.avg_time_db_ms, ds.p95_time_db_ms, storage_latency_ms,
                network_id,
            )
            self._scale_up_storage_window.clear()
            self._scale_down_storage_window.clear()  # cross-direction reset
            self._last_storage_scale_up_ts = time.monotonic()
            return DataAlert(
                lan=lan,
                network_id=network_id,
                rs_name=f"rs_net{lan}",
                primary_container=f"edge_storage_server_n{lan}",
            )
        return None

    # ── Scale-down evaluation ────────────────────────────────────────────

    def evaluate_scale_down_compute(self, ds: DomainSummary) -> bool:
        """Returns True if compute underutilisation threshold met."""
        if ds.avg_time_proc_ms > _SCALE_DOWN_PROC_TIMEOUT_CEILING_MS:
            logger.debug(
                "[scale-down] compute eval: proc=%.1f exceeds ceiling (%.0f) — window skipped",
                ds.avg_time_proc_ms, _SCALE_DOWN_PROC_TIMEOUT_CEILING_MS,
            )
            return False

        below = (ds.average_cpu_percent < _TAU_CPU_DOWN
                 and ds.avg_time_proc_ms < _TAU_PROC_DOWN_MS)
        self._scale_down_compute_window.append(below)
        hits = sum(self._scale_down_compute_window)
        armed = hits >= _SCALE_DOWN_COMPUTE_REQUIRED

        logger.debug(
            "[scale-down] compute eval: cpu=%.1f/%.0f proc=%.1f/%.1f below=%s hits=%d/%d armed=%s",
            ds.average_cpu_percent, _TAU_CPU_DOWN,
            ds.avg_time_proc_ms, _TAU_PROC_DOWN_MS,
            below, hits, _SCALE_DOWN_COMPUTE_REQUIRED, armed,
        )
        if armed and not self._prev_scale_down_compute_armed:
            logger.info(
                "[scale-down] compute ARMED: hits=%d/%d cpu=%.1f proc=%.1f",
                hits, _SCALE_DOWN_COMPUTE_REQUIRED,
                ds.average_cpu_percent, ds.avg_time_proc_ms,
            )
        self._prev_scale_down_compute_armed = armed
        return armed

    def evaluate_scale_down_storage(self, ds: DomainSummary) -> bool:
        """Returns True if storage underutilisation threshold met."""
        if ds.avg_time_db_ms > _SCALE_DOWN_DB_TIMEOUT_CEILING_MS:
            logger.info(
                "[scale-down] storage eval: db=%.1f exceeds ceiling (%.0f) — window skipped",
                ds.avg_time_db_ms, _SCALE_DOWN_DB_TIMEOUT_CEILING_MS,
            )
            return False

        below = (ds.avg_storage_cpu_percent < _TAU_STORAGE_CPU_DOWN
                 and ds.avg_time_db_ms < _TAU_DB_DOWN_MS)
        self._scale_down_storage_window.append(below)
        hits = sum(self._scale_down_storage_window)
        armed = hits >= _SCALE_DOWN_STORAGE_REQUIRED

        logger.info(
            "[scale-down] storage eval: stCpu=%.1f/%.0f db=%.1f/%.0f below=%s hits=%d/%d armed=%s",
            ds.avg_storage_cpu_percent, _TAU_STORAGE_CPU_DOWN,
            ds.avg_time_db_ms, _TAU_DB_DOWN_MS,
            below, hits, _SCALE_DOWN_STORAGE_REQUIRED, armed,
        )
        if armed and not self._prev_scale_down_storage_armed:
            logger.info(
                "[scale-down] storage ARMED: hits=%d/%d stCpu=%.1f db=%.1f",
                hits, _SCALE_DOWN_STORAGE_REQUIRED,
                ds.avg_storage_cpu_percent, ds.avg_time_db_ms,
            )
        self._prev_scale_down_storage_armed = armed
        return armed

    def clear_scale_down_compute_window(self) -> None:
        self._scale_down_compute_window.clear()

    def clear_scale_down_storage_window(self) -> None:
        self._scale_down_storage_window.clear()
