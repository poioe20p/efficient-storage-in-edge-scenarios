# Plan: Decompose `_on_telemetry_update` into Composition-Based Components

## TL;DR

Break the monolithic `_on_telemetry_update` and its 14 helper methods out of
`main_n1.py` / `main_n2.py` into four composed components (Strategy + Registry +
Event Dispatcher + Mediator) plus a shared constants module. Keep both main files
separate.

## Decisions

- **Pattern:** Composition (Strategy + Registry + Dispatcher + Mediator) instead
  of a single mixin. Gives cleaner isolation, testability, and explicit
  dependency wiring.
- **Keep main_n1/n2 separate** — no unification.
- **Thread safety:** All composed components are created and called exclusively
  from Thread 2. The `ElasticityManager` reference is passed in at construction;
  the composed objects never spawn threads or hold locks.
- **Logger:** Each module uses `logging.getLogger(__name__)`. `self._lan_id` is
  passed as context where needed so log messages remain distinguishable per LAN.

---

## Identified Concerns

| # | Concern                           | Responsibility                                                      | Design pattern   |
| - | --------------------------------- | ------------------------------------------------------------------- | ---------------- |
| 1 | **Scaling Policy**          | Decide *whether* to scale up/down based on aggregate metrics     | Strategy         |
| 2 | **Node Lifecycle Tracking** | Track dynamic nodes, detect disappearances, find removal candidates | Registry         |
| 3 | **Control Event Handling**  | React to ZMQ control signals (drain, secondary ready, VIP fallback) | Event Dispatcher |
| 4 | **Orchestration**           | Sequence the above, apply gating (network filter, busy, cooldowns)  | Mediator         |

### Concern boundaries

- **Scaling Policy** can change independently — swap degradation score formula,
  change window sizes, add new scaling dimensions — without touching event
  handling or node tracking.
- **Node Lifecycle Tracking** can evolve (e.g. add health checks, change
  LIFO→priority-based selection) without affecting how scale-up decisions are
  made.
- **Control Event Handling** is a set of `if event_type == X: do Y` dispatchers.
  Adding new control events doesn't touch scaling logic.
- **Orchestration** is the only piece that knows the execution order. It can be
  modified (e.g. skip scale-down if no dynamic nodes exist) without changing any
  of the other three.

### Coupling resolution

The earlier coupling issue (scale-down evaluation → node tracking for
`_find_last_dynamic_*` / `_submit_scale_down_alert`) disappears with the
mediator. The policy returns **what** to do ("scale down compute"), the mediator
asks the registry **who** to remove, and submits the alert. Neither the policy
nor the registry knows about the other.

---

## Steps

### Phase 1: Extract shared constants

**Create** `source/sdn_controller/scaling_config.py`

Move ALL 35 module-level env-var constants from main_n1/n2 (they're identical):

```python
"""scaling_config.py — environment-based scaling constants.

Shared by ScalingPolicy, DynamicNodeRegistry, and the mediator.
"""

import os

# ── Scale-up: weighted degradation score ────────────────────────────────
#
#  score = W_CPU * max(0, cpu - FLOOR) / SPAN  +  W_T * max(0, lat - FLOOR) / SPAN
#
# W_T is _W_T_PROC (compute) or _W_T_DB (storage) depending on the tier.
#
# Score ≥ THRESHOLD for at least REQUIRED of the last WINDOW_SIZE windows
# triggers scale-up.

# Storage score weights & normalisation
_W_STORAGE_CPU     = float(os.environ.get("SCALEUP_W_STORAGE_CPU",     "0.3"))
_W_T_DB            = float(os.environ.get("SCALEUP_W_T_DB",            "0.7"))
_STORAGE_CPU_FLOOR = float(os.environ.get("SCALEUP_STORAGE_CPU_FLOOR", "50"))
_STORAGE_CPU_SPAN  = float(os.environ.get("SCALEUP_STORAGE_CPU_SPAN",  "35"))
_T_DB_FLOOR        = float(os.environ.get("SCALEUP_T_DB_FLOOR",        "15"))
_T_DB_SPAN         = float(os.environ.get("SCALEUP_T_DB_SPAN",         "75"))

# Compute score weights & normalisation
_W_CPU        = float(os.environ.get("SCALEUP_W_CPU",      "0.3"))
_W_T_PROC     = float(os.environ.get("SCALEUP_W_T_PROC",   "0.7"))
_CPU_FLOOR    = float(os.environ.get("SCALEUP_CPU_FLOOR",  "50"))
_CPU_SPAN     = float(os.environ.get("SCALEUP_CPU_SPAN",   "35"))
_T_PROC_FLOOR = float(os.environ.get("SCALEUP_T_PROC_FLOOR", "1"))
_T_PROC_SPAN  = float(os.environ.get("SCALEUP_T_PROC_SPAN",  "11"))

# Compute scale-up sliding window
_SCALE_UP_SCORE_THRESHOLD = float(os.environ.get("SCALEUP_SCORE_THRESHOLD", "0.40"))
_SCALE_UP_WINDOW_SIZE     = int(os.environ.get("SCALEUP_WINDOW_SIZE",       "5"))
_SCALE_UP_REQUIRED        = int(os.environ.get("SCALEUP_REQUIRED",          "2"))

# Adaptive storage scale-up threshold (lower base, increment per dynamic node)
_SCALEUP_STORAGE_BASE_THRESHOLD      = float(os.environ.get("SCALEUP_STORAGE_BASE_THRESHOLD",      "0.25"))
_SCALEUP_STORAGE_THRESHOLD_INCREMENT = float(os.environ.get("SCALEUP_STORAGE_THRESHOLD_INCREMENT",  "0.10"))
_SCALEUP_STORAGE_MAX_THRESHOLD       = float(os.environ.get("SCALEUP_STORAGE_MAX_THRESHOLD",        "0.65"))
_SCALEUP_STORAGE_WINDOW_SIZE         = int(os.environ.get("SCALEUP_STORAGE_WINDOW_SIZE",             "5"))
_SCALEUP_STORAGE_REQUIRED            = int(os.environ.get("SCALEUP_STORAGE_REQUIRED",                "2"))

# Scale-down thresholds
_TAU_CPU_DOWN              = float(os.environ.get("TAU_CPU_DOWN",              "65"))
_TAU_PROC_DOWN_MS          = float(os.environ.get("TAU_PROC_DOWN_MS",          "5"))
_TAU_STORAGE_CPU_DOWN      = float(os.environ.get("TAU_STORAGE_CPU_DOWN",      "60"))
_TAU_DB_DOWN_MS            = float(os.environ.get("TAU_DB_DOWN_MS",            "100"))
_TELEMETRY_TIMEOUT_WINDOWS = int(os.environ.get("TELEMETRY_TIMEOUT_WINDOWS",   "18"))

# Timeout ceiling — indeterminate windows (neither increment nor reset)
_SCALE_DOWN_PROC_TIMEOUT_CEILING_MS = float(os.environ.get("SCALE_DOWN_PROC_TIMEOUT_CEILING_MS", "5000"))
_SCALE_DOWN_DB_TIMEOUT_CEILING_MS   = float(os.environ.get("SCALE_DOWN_DB_TIMEOUT_CEILING_MS",   "5000"))

# Scale-down sliding window
_SCALE_DOWN_COMPUTE_WINDOW_SIZE = int(os.environ.get("SCALE_DOWN_COMPUTE_WINDOW_SIZE", "12"))
_SCALE_DOWN_COMPUTE_REQUIRED    = int(os.environ.get("SCALE_DOWN_COMPUTE_REQUIRED",     "7"))
_SCALE_DOWN_STORAGE_WINDOW_SIZE = int(os.environ.get("SCALE_DOWN_STORAGE_WINDOW_SIZE", "15"))
_SCALE_DOWN_STORAGE_REQUIRED    = int(os.environ.get("SCALE_DOWN_STORAGE_REQUIRED",     "9"))

# Cooldowns — suppress evaluation for a grace period after scale-up
_SCALEDOWN_STORAGE_COOLDOWN_S = float(os.environ.get("SCALEDOWN_STORAGE_COOLDOWN_S", "120"))
_SCALEDOWN_COMPUTE_COOLDOWN_S = float(os.environ.get("SCALEDOWN_COMPUTE_COOLDOWN_S",  "40"))
_SCALEUP_STORAGE_COOLDOWN_S   = float(os.environ.get("SCALEUP_STORAGE_COOLDOWN_S",   "120"))

# Birth grace — skip absent-node detection for newly spawned nodes
_NODE_BIRTH_GRACE_S = float(os.environ.get("NODE_BIRTH_GRACE_S", "60"))
```

### Phase 2: Create ScalingPolicy (Strategy)

**Create** `source/sdn_controller/scaling_policy.py`

```python
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
    _SCALE_UP_SCORE_THRESHOLD, _SCALE_UP_WINDOW_SIZE, _SCALE_UP_REQUIRED,
    _SCALEUP_STORAGE_BASE_THRESHOLD, _SCALEUP_STORAGE_THRESHOLD_INCREMENT,
    _SCALEUP_STORAGE_MAX_THRESHOLD, _SCALEUP_STORAGE_WINDOW_SIZE,
    _SCALEUP_STORAGE_REQUIRED,
    _TAU_CPU_DOWN, _TAU_PROC_DOWN_MS,
    _TAU_STORAGE_CPU_DOWN, _TAU_DB_DOWN_MS,
    _SCALE_DOWN_PROC_TIMEOUT_CEILING_MS, _SCALE_DOWN_DB_TIMEOUT_CEILING_MS,
    _SCALE_DOWN_COMPUTE_WINDOW_SIZE, _SCALE_DOWN_COMPUTE_REQUIRED,
    _SCALE_DOWN_STORAGE_WINDOW_SIZE, _SCALE_DOWN_STORAGE_REQUIRED,
    _SCALEDOWN_STORAGE_COOLDOWN_S, _SCALEDOWN_COMPUTE_COOLDOWN_S,
    _SCALEUP_STORAGE_COOLDOWN_S,
)
from .elasticity.elasticity import ComputeAlert, DataAlert
from .telemetry.models import DomainSummary

logger = logging.getLogger(__name__)


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

        logger.info(
            "scale-up: compute[τ=%.2f window=%d/%d w_cpu=%.1f w_lat=%.1f]  "
            "storage[τ_base=%.2f incr=%.2f cap=%.2f window=%d/%d w_cpu=%.1f w_lat=%.1f cooldown=%.0fs]",
            _SCALE_UP_SCORE_THRESHOLD, _SCALE_UP_REQUIRED, _SCALE_UP_WINDOW_SIZE,
            _W_CPU, _W_T_PROC,
            _SCALEUP_STORAGE_BASE_THRESHOLD, _SCALEUP_STORAGE_THRESHOLD_INCREMENT,
            _SCALEUP_STORAGE_MAX_THRESHOLD, _SCALEUP_STORAGE_REQUIRED, _SCALEUP_STORAGE_WINDOW_SIZE,
            _W_STORAGE_CPU, _W_T_DB, _SCALEUP_STORAGE_COOLDOWN_S,
        )

    # ── Pure helpers ─────────────────────────────────────────────────────

    @staticmethod
    def degradation_score(cpu: float, latency: float,
                          w_cpu: float, w_lat: float,
                          cpu_floor: float, cpu_span: float,
                          lat_floor: float, lat_span: float) -> float:
        """Weighted degradation score in [0, +inf)."""
        cpu_component = max(0.0, cpu - cpu_floor) / cpu_span if cpu_span else 0.0
        lat_component = max(0.0, latency - lat_floor) / lat_span if lat_span else 0.0
        return w_cpu * cpu_component + w_lat * lat_component

    # ── Cooldown queries ─────────────────────────────────────────────────

    def compute_cooldown_remaining(self) -> float:
        return max(0.0, _SCALEDOWN_COMPUTE_COOLDOWN_S - (time.monotonic() - self._last_compute_scale_up_ts))

    def storage_cooldown_remaining(self) -> float:
        return max(0.0, _SCALEDOWN_STORAGE_COOLDOWN_S - (time.monotonic() - self._last_storage_scale_up_ts))

    def storage_scaleup_cooldown_remaining(self) -> float:
        return max(0.0, _SCALEUP_STORAGE_COOLDOWN_S - (time.monotonic() - self._last_storage_scale_up_ts))

    # ── Scale-up evaluation ──────────────────────────────────────────────

    def evaluate_scale_up(self, ds: DomainSummary, lan: int, network_id: str,
                          dynamic_storage_count: int) -> list[ComputeAlert | DataAlert]:
        """Evaluate Compute and Storage scale-up. Returns list of alerts to submit."""
        alerts: list[ComputeAlert | DataAlert] = []

        # ── Compute ──
        compute_alert = self._evaluate_compute_scale_up(ds, lan, network_id)
        if compute_alert:
            alerts.append(compute_alert)

        # ── Storage (with its own scale-up cooldown) ──
        remaining = self.storage_scaleup_cooldown_remaining()
        if remaining > 0:
            logger.debug("[scale-up] storage within %.0fs scale-up cooldown — skipping", remaining)
        else:
            storage_alert = self._evaluate_storage_scale_up(ds, lan, network_id, dynamic_storage_count)
            if storage_alert:
                alerts.append(storage_alert)

        return alerts

    def _evaluate_compute_scale_up(self, ds: DomainSummary, lan: int,
                                   network_id: str) -> ComputeAlert | None:
        compute_score = self.degradation_score(
            ds.average_cpu_percent, ds.avg_time_proc_ms,
            _W_CPU, _W_T_PROC,
            _CPU_FLOOR, _CPU_SPAN,
            _T_PROC_FLOOR, _T_PROC_SPAN,
        )
        above = compute_score >= _SCALE_UP_SCORE_THRESHOLD
        self._scale_up_compute_window.append(above)
        logger.debug(
            "[scale-up] compute score=%.2f (τ=%.2f) cpu=%.1f%% T_proc=%.1fms  "
            "window=%d/%d on %s",
            compute_score, _SCALE_UP_SCORE_THRESHOLD,
            ds.average_cpu_percent, ds.avg_time_proc_ms,
            sum(self._scale_up_compute_window), len(self._scale_up_compute_window),
            network_id,
        )
        if sum(self._scale_up_compute_window) >= _SCALE_UP_REQUIRED:
            logger.info(
                "[scale-up] compute triggered: %d/%d windows ≥ %.2f "
                "(last score=%.2f, cpu=%.1f%%, T_proc=%.1fms) on %s",
                sum(self._scale_up_compute_window),
                len(self._scale_up_compute_window),
                _SCALE_UP_SCORE_THRESHOLD, compute_score,
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
        storage_score = self.degradation_score(
            ds.avg_storage_cpu_percent, ds.avg_time_db_ms,
            _W_STORAGE_CPU, _W_T_DB,
            _STORAGE_CPU_FLOOR, _STORAGE_CPU_SPAN,
            _T_DB_FLOOR, _T_DB_SPAN,
        )
        # Adaptive threshold: increases with each dynamic storage node
        effective_threshold = min(
            _SCALEUP_STORAGE_BASE_THRESHOLD
            + dynamic_storage_count * _SCALEUP_STORAGE_THRESHOLD_INCREMENT,
            _SCALEUP_STORAGE_MAX_THRESHOLD,
        )
        above = storage_score >= effective_threshold
        self._scale_up_storage_window.append(above)
        logger.debug(
            "[scale-up] storage score=%.2f (τ_eff=%.2f, base=%.2f +%d×%.2f) "
            "cpu_s=%.1f%% T_db=%.1fms  window=%d/%d on %s",
            storage_score, effective_threshold,
            _SCALEUP_STORAGE_BASE_THRESHOLD, dynamic_storage_count,
            _SCALEUP_STORAGE_THRESHOLD_INCREMENT,
            ds.avg_storage_cpu_percent, ds.avg_time_db_ms,
            sum(self._scale_up_storage_window), len(self._scale_up_storage_window),
            network_id,
        )
        if sum(self._scale_up_storage_window) >= _SCALEUP_STORAGE_REQUIRED:
            logger.info(
                "[scale-up] storage triggered: %d/%d windows ≥ %.2f "
                "(eff_τ=%.2f, dyn_nodes=%d, last score=%.2f, cpu_s=%.1f%%, T_db=%.1fms) on %s",
                sum(self._scale_up_storage_window),
                len(self._scale_up_storage_window),
                effective_threshold, effective_threshold, dynamic_storage_count,
                storage_score, ds.avg_storage_cpu_percent, ds.avg_time_db_ms,
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
                "[scale-down] compute: avg_time_proc_ms=%.1f exceeds timeout ceiling (%.0f) — skipping window",
                ds.avg_time_proc_ms, _SCALE_DOWN_PROC_TIMEOUT_CEILING_MS,
            )
            return False

        below = (ds.average_cpu_percent < _TAU_CPU_DOWN
                 and ds.avg_time_proc_ms < _TAU_PROC_DOWN_MS)
        self._scale_down_compute_window.append(below)
        return sum(self._scale_down_compute_window) >= _SCALE_DOWN_COMPUTE_REQUIRED

    def evaluate_scale_down_storage(self, ds: DomainSummary) -> bool:
        """Returns True if storage underutilisation threshold met."""
        if ds.avg_time_db_ms > _SCALE_DOWN_DB_TIMEOUT_CEILING_MS:
            logger.debug(
                "[scale-down] storage: avg_time_db_ms=%.1f exceeds timeout ceiling (%.0f) — skipping window",
                ds.avg_time_db_ms, _SCALE_DOWN_DB_TIMEOUT_CEILING_MS,
            )
            return False

        below = (ds.avg_storage_cpu_percent < _TAU_STORAGE_CPU_DOWN
                 and ds.avg_time_db_ms < _TAU_DB_DOWN_MS)
        self._scale_down_storage_window.append(below)
        return sum(self._scale_down_storage_window) >= _SCALE_DOWN_STORAGE_REQUIRED

    def clear_scale_down_compute_window(self) -> None:
        self._scale_down_compute_window.clear()

    def clear_scale_down_storage_window(self) -> None:
        self._scale_down_storage_window.clear()
```

### Phase 3: Create DynamicNodeRegistry (Registry)

**Create** `source/sdn_controller/node_registry.py`

```python
"""node_registry.py — Dynamic node lifecycle tracking (Registry pattern).

Tracks which dynamically added nodes exist, detects disappeared nodes,
and builds scale-down alerts. Does NOT submit alerts or access the
ElasticityManager beyond consuming completions.

Thread safety: all methods are called exclusively from Thread 2.
"""

import logging
import time

from .scaling_config import _TELEMETRY_TIMEOUT_WINDOWS, _NODE_BIRTH_GRACE_S
from .elasticity.elasticity import ElasticityManager, ScaleDownComputeAlert, ScaleDownDataAlert
from .elasticity.node_common import NodeInfo
from .telemetry.models import TelemetrySummary

logger = logging.getLogger(__name__)


class DynamicNodeRegistry:
    """Tracks dynamically added nodes for scale-down and absence detection.

    Owns: MAC tracking sets, active node map, absence counters, birth timestamps.
    Answers queries — does NOT submit alerts or touch the elasticity manager.
    """

    def __init__(self) -> None:
        self._dynamic_node_macs: set[str] = set()
        self._active: dict[str, NodeInfo] = {}     # mac → NodeInfo, insertion order = LIFO
        self._absent_window_count: dict[str, int] = {}
        self._birth_ts: dict[str, float] = {}

    # ── Thread 3 → Thread 2 sync ────────────────────────────────────────

    def sync(self, elasticity: ElasticityManager) -> None:
        """Consume removal and addition completions from Thread 3."""
        for mac in elasticity.consume_removal_completions():
            self._dynamic_node_macs.discard(mac)
            self._absent_window_count.pop(mac, None)
            self._active.pop(mac, None)
            self._birth_ts.pop(mac, None)
            logger.info("[registry] removed MAC %s from tracking after cleanup", mac)

        for info in elasticity.consume_addition_completions():
            self._dynamic_node_macs.add(info.mac)
            self._active[info.mac] = info
            self._birth_ts[info.mac] = time.monotonic()
            logger.info("[registry] tracking new dynamic %s node mac=%s name=%s",
                        info.node_type, info.mac, info.name)

    # ── Absence detection ────────────────────────────────────────────────

    def detect_absent(self, summary: TelemetrySummary) -> list[str]:
        """Return MACs that exceeded TELEMETRY_TIMEOUT_WINDOWS consecutive absent windows."""
        now = time.monotonic()
        timed_out: list[str] = []
        for mac in list(self._dynamic_node_macs):
            # Skip freshly spawned nodes still booting
            if now - self._birth_ts.get(mac, float('-inf')) < _NODE_BIRTH_GRACE_S:
                continue

            present = (mac in summary.servers) or (mac in summary.storage_servers)
            if present:
                self._absent_window_count[mac] = 0
            else:
                self._absent_window_count[mac] = self._absent_window_count.get(mac, 0) + 1
                count = self._absent_window_count[mac]
                logger.debug("[registry] mac=%s absent for %d windows", mac, count)
                if count >= _TELEMETRY_TIMEOUT_WINDOWS:
                    logger.warning("[registry] mac=%s absent for %d windows — triggering removal", mac, count)
                    self._absent_window_count[mac] = 0
                    timed_out.append(mac)
        return timed_out

    # ── Queries ──────────────────────────────────────────────────────────

    def find_last_dynamic(self, node_type: str) -> NodeInfo | None:
        """LIFO lookup for most recently added dynamic node of the given type."""
        for mac, info in reversed(list(self._active.items())):
            if info.node_type == node_type and mac in self._dynamic_node_macs:
                return info
        return None

    def count_dynamic(self, node_type: str) -> int:
        """Count dynamic nodes of the given type."""
        return sum(
            1 for info in self._active.values()
            if info.node_type == node_type
        )

    def get_node_info(self, mac: str) -> NodeInfo | None:
        return self._active.get(mac)

    def is_tracked(self, mac: str) -> bool:
        return mac in self._dynamic_node_macs

    # ── Alert building ───────────────────────────────────────────────────

    def build_scale_down_alert(self, mac: str) -> ScaleDownComputeAlert | ScaleDownDataAlert | None:
        """Build the appropriate scale-down alert from NodeInfo. Returns None if MAC not tracked."""
        if mac not in self._dynamic_node_macs:
            logger.warning("[registry] mac=%s not in dynamic_node_macs — ignoring", mac)
            return None
        info = self._active.get(mac)
        if info is None:
            logger.warning("[registry] no NodeInfo for mac=%s — cannot build alert", mac)
            return None

        if info.node_type == "compute":
            return ScaleDownComputeAlert(
                lan=info.lan,
                network_id=info.network_id,
                container_name=info.name,
                mac=mac,
                ip=info.ip,
            )
        else:
            return ScaleDownDataAlert(
                lan=info.lan,
                network_id=info.network_id,
                container_name=info.name,
                mac=mac,
                ip=info.ip,
                rs_name=info.rs_name,
                primary_container=info.primary_container,
                port=info.port,
            )
```

### Phase 4: Create ControlEventDispatcher (Event Dispatcher)

**Create** `source/sdn_controller/control_events.py`

```python
"""control_events.py — ZMQ control event dispatcher.

Dispatches drain_complete, rs_secondary_ready, and telemetry-based
VIP promotions. Fully stateless — all dependencies passed as arguments.

Thread safety: all methods are called exclusively from Thread 2.
"""

import logging
from typing import Callable

from .elasticity.elasticity import ElasticityManager
from .node_registry import DynamicNodeRegistry
from .telemetry.models import TelemetrySummary

logger = logging.getLogger(__name__)


class ControlEventDispatcher:
    """Dispatches ZMQ control events and telemetry-based VIP promotions.

    Stateless — all state is read from the node registry and topology mixin.
    """

    def process_drain_events(self, summary: TelemetrySummary,
                             elasticity: ElasticityManager) -> None:
        """Handle drain_complete control events forwarded by the aggregator."""
        for event in summary.control_events:
            if event.get("event_type") == "drain_complete":
                mac = event.get("server_id")
                if mac and elasticity.has_pending_drain(mac):
                    logger.info("[control] drain_complete received for mac=%s — submitting Phase B cleanup", mac)
                    elasticity.submit_cleanup_compute(mac)

    def process_secondary_events(
        self,
        summary: TelemetrySummary,
        registry: DynamicNodeRegistry,
        add_storage_mac_fn: Callable[[str, str], None],
    ) -> None:
        """Handle rs_secondary_ready control events — add storage node to VIP pool."""
        for event in summary.control_events:
            if event.get("event_type") == "rs_secondary_ready":
                mac = event.get("server_id")
                if not mac:
                    continue
                info = registry.get_node_info(mac)
                if info is None:
                    logger.warning("[control] rs_secondary_ready for unknown mac=%s — ignoring", mac)
                    continue
                if info.node_type != "storage":
                    logger.warning("[control] rs_secondary_ready for non-storage mac=%s — ignoring", mac)
                    continue
                add_storage_mac_fn(mac, f"n{info.lan}")
                logger.info(
                    "[control] rs_secondary_ready received for mac=%s — "
                    "added to VIP storage pool (ip=%s, name=%s)",
                    mac, info.ip, info.name,
                )

    def promote_storage_from_telemetry(
        self,
        summary: TelemetrySummary,
        registry: DynamicNodeRegistry,
        local_storage_macs_n1: set[str],
        local_storage_macs_n2: set[str],
        add_storage_mac_fn: Callable[[str, str], None],
    ) -> None:
        """Fallback VIP promotion: detect SECONDARY from regular telemetry.

        If a storage node reports member_state=="SECONDARY" in its aggregated
        telemetry but has not been added to the VIP pool yet, promote it now.
        """
        for mac, ss in summary.storage_servers.items():
            if ss.member_state != "SECONDARY":
                continue
            info = registry.get_node_info(mac)
            if info is None or info.node_type != "storage":
                continue
            domain = f"n{info.lan}"
            already_in = (
                mac in local_storage_macs_n1 if domain == "n1"
                else mac in local_storage_macs_n2
            )
            if already_in:
                continue
            add_storage_mac_fn(mac, domain)
            logger.info(
                "[control] promoting storage mac=%s via telemetry fallback "
                "(member_state=SECONDARY, ip=%s, name=%s)",
                mac, info.ip, info.name,
            )
```

### Phase 5: Wire Orchestrator in main_n1.py and main_n2.py (Mediator)

**Modify** both `source/sdn_controller/main_n1.py` and `main_n2.py`.

#### 5a. New imports (replace old ones)

```python
# REMOVE these imports:
# from collections import deque
# from .elasticity.elasticity import ComputeAlert, DataAlert, ScaleDownComputeAlert, ScaleDownDataAlert

# ADD these imports:
from .scaling_policy import ScalingPolicy
from .node_registry import DynamicNodeRegistry
from .control_events import ControlEventDispatcher
```

Imports that remain unchanged:

```python
import logging
import os
import time

from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from os_ken.lib.packet import ethernet, ether_types, packet
from os_ken.ofproto import ofproto_v1_3
from os_ken import cfg

from .elasticity.elasticity import ElasticityManager   # still needed for __init__
from .telemetry.models import TelemetrySummary          # still needed for type hint
from .telemetry.zmq_source import ZmqTelemetrySource    # still needed for __init__
from .topology.topology import TopologyMixin
from .vip_routing import VipRoutingMixin
```

#### 5b. Module-level (stays in main files, do NOT move)

```python
# Do NOT move — OS-Ken resolves from sys.modules[cls.__module__]
_REQUIRED_APP = ['os_ken.topology.switches']

logger = logging.getLogger('os_ken.main_n1')  # or 'os_ken.main_n2'
```

All 35 env-var constants are REMOVED from the main files.

#### 5c. New `__init__` (what changes)

```python
class KenLearnAndLog(VipRoutingMixin, TopologyMixin, app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        cfg.CONF.observe_links = True
        cfg.CONF.observe_hosts = True

        super(KenLearnAndLog, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.enable_reactive_learning = True
        self.datapaths = []
        self._datapath_by_id = {}
        self._lan_id = os.environ.get("LAN_ID", "lan1")  # "lan2" in main_n2

        _aggregator_endpoints = [
            ep.strip()
            for ep in os.environ.get(
                "AGGREGATOR_ENDPOINTS", "tcp://10.0.0.5:5556,tcp://10.0.1.5:5556"
            ).split(",")
            if ep.strip()
        ]
        _peer_endpoints = [
            ep.strip()
            for ep in os.environ.get("PEER_TOPOLOGY_ENDPOINTS", "").split(",")
            if ep.strip()
        ]
        logger.info("aggregator endpoints: %s", _aggregator_endpoints)
        logger.info("peer topology endpoints: %s", _peer_endpoints)

        # Thread 3 — must be created before ZmqTelemetrySource
        self._elasticity = ElasticityManager(topology_mixin=self)
        self._elasticity.start()

        # ── Composed components (Thread 2 only) ──
        self._scaling_policy = ScalingPolicy()
        self._node_registry = DynamicNodeRegistry()
        self._control_events = ControlEventDispatcher()

        # Thread 2 — ZMQ subscriber
        self._telemetry = ZmqTelemetrySource(
            endpoints=_aggregator_endpoints + _peer_endpoints,
            on_update=self._on_telemetry_update,
            on_topology_update=self.on_topology_update,
        )
        self._telemetry.start()
```

REMOVED from `__init__`:

- All deque initialisations (`_scale_up_compute_window`, etc.)
- All tracking dicts (`_dynamic_node_macs`, `_active`, `_absent_window_count`, `_birth_ts`)
- All cooldown timestamps (`_last_storage_scale_up_ts`, `_last_compute_scale_up_ts`)
- The startup config log (moved to `ScalingPolicy.__init__`)

#### 5d. New `_on_telemetry_update` (mediator)

```python
def _on_telemetry_update(self, summary: TelemetrySummary) -> None:
    """Thread 2 callback — thin mediator that orchestrates composed components."""
    if summary.network_id != self._lan_id:
        logger.debug("ignoring telemetry for %s (this controller owns %s)",
                     summary.network_id, self._lan_id)
        return

    # 1. Sync node tracking (Thread 3 → Thread 2)
    self._node_registry.sync(self._elasticity)

    # 2. Dispatch control events
    self._control_events.process_drain_events(summary, self._elasticity)
    self._control_events.process_secondary_events(
        summary, self._node_registry, self.add_storage_mac,
    )

    # Mini-summaries (control event pass-throughs) have empty server dicts.
    if not summary.servers and not summary.storage_servers:
        return

    # Guard: domain_summary is Optional (None in mini-summaries, but the
    # mini-summary early-return above should catch those).  Defensive check
    # for any edge case where a non-mini summary arrives without metrics.
    if summary.domain_summary is None:
        logger.warning("non-mini summary with domain_summary=None — skipping scaling")
        return

    # 3. Observability
    self._log_and_update_stats(summary)

    # 4. Fallback VIP promotion
    self._control_events.promote_storage_from_telemetry(
        summary, self._node_registry,
        self._local_storage_macs_n1, self._local_storage_macs_n2,
        self.add_storage_mac,
    )

    try:
        lan = int(summary.network_id.replace("lan", ""))
    except ValueError:
        logger.warning("could not parse LAN from network_id=%s", summary.network_id)
        return

    # 5. Absent node detection → alert submission
    for mac in self._node_registry.detect_absent(summary):
        if self._elasticity.has_pending_drain(mac):
            logger.info("[scale-down] pending drain for mac=%s — submitting CleanupComputeAlert", mac)
            self._elasticity.submit_cleanup_compute(mac)
        else:
            alert = self._node_registry.build_scale_down_alert(mac)
            if alert:
                logger.info("[scale-down] submitting alert: %s", alert)
                self._elasticity.submit(alert)

    if self._elasticity.is_busy():
        logger.debug("[scale-down] elasticity manager is busy — skipping scaling evaluation")
        return

    ds = summary.domain_summary

    # 6. Scale-up evaluation
    dynamic_storage_count = self._node_registry.count_dynamic("storage")
    for alert in self._scaling_policy.evaluate_scale_up(ds, lan, summary.network_id, dynamic_storage_count):
        self._elasticity.submit(alert)

    # 7. Scale-down evaluation (with cooldown gating)
    remaining = self._scaling_policy.compute_cooldown_remaining()
    if remaining > 0:
        logger.debug("[scale-down] compute within %.0fs cooldown — skipping", remaining)
    else:
        if self._scaling_policy.evaluate_scale_down_compute(ds):
            node = self._node_registry.find_last_dynamic("compute")
            if node:
                logger.info(
                    "[scale-down] compute underutilisation — removing %s", node.name)
                alert = self._node_registry.build_scale_down_alert(node.mac)
                if alert:
                    self._elasticity.submit(alert)
            self._scaling_policy.clear_scale_down_compute_window()

    remaining = self._scaling_policy.storage_cooldown_remaining()
    if remaining > 0:
        logger.debug("[scale-down] storage within %.0fs cooldown — skipping", remaining)
    else:
        if self._scaling_policy.evaluate_scale_down_storage(ds):
            node = self._node_registry.find_last_dynamic("storage")
            if node:
                logger.info(
                    "[scale-down] storage underutilisation — removing %s", node.name)
                alert = self._node_registry.build_scale_down_alert(node.mac)
                if alert:
                    self._elasticity.submit(alert)
            self._scaling_policy.clear_scale_down_storage_window()
```

#### 5e. `_log_and_update_stats` stays on main class

```python
def _log_and_update_stats(self, summary: TelemetrySummary) -> None:
    """Print domain summary metrics and push per-server stats to Thread 1."""
    ds = summary.domain_summary
    print(
        f"[telemetry] network={summary.network_id} "
        f"proc_ms={ds.avg_time_proc_ms:.1f} "
        f"db_ms={ds.avg_time_db_ms:.1f} "
        f"requests={ds.total_requests} "
        f"cpu={ds.average_cpu_percent:.1f}%"
    )
    self.update_server_stats(summary.servers)
    self.update_storage_stats(summary.storage_servers)
```

#### 5f. Methods that remain unchanged on main class

- `_install_flow`
- `add_flow`
- `switch_features_handler`
- `packet_in_handler`

#### 5g. Methods REMOVED from main class (14 extracted + 1 replaced = 15 total)

| Method | Now in |
|--------|--------|
| `_degradation_score` | `ScalingPolicy.degradation_score` |
| `_evaluate_scale_up` | `ScalingPolicy.evaluate_scale_up` |
| `_evaluate_storage_scale_up` | `ScalingPolicy._evaluate_storage_scale_up` |
| `_evaluate_scale_down_compute` | `ScalingPolicy.evaluate_scale_down_compute` |
| `_evaluate_scale_down_storage` | `ScalingPolicy.evaluate_scale_down_storage` |
| `_count_dynamic_storage_nodes` | `DynamicNodeRegistry.count_dynamic("storage")` |
| `_sync_node_tracking` | `DynamicNodeRegistry.sync` |
| `_detect_absent_nodes` | `DynamicNodeRegistry.detect_absent` |
| `_find_last_dynamic_compute_node` | `DynamicNodeRegistry.find_last_dynamic("compute")` |
| `_find_last_dynamic_storage_node` | `DynamicNodeRegistry.find_last_dynamic("storage")` |
| `_submit_scale_down_alert` | `DynamicNodeRegistry.build_scale_down_alert` + mediator submit |
| `_process_drain_events` | `ControlEventDispatcher.process_drain_events` |
| `_process_secondary_events` | `ControlEventDispatcher.process_secondary_events` |
| `_promote_storage_from_telemetry` | `ControlEventDispatcher.promote_storage_from_telemetry` |
| `_on_telemetry_update` (old) | Replaced by new mediator version (same name) |

#### 5h. Constraints

- **Do NOT move** `_REQUIRED_APP = ['os_ken.topology.switches']` — OS-Ken
  resolves this from `sys.modules[cls.__module__]`, must stay in entry-point
  modules.
- **Do NOT remove** `ElasticityManager` import — still needed for `__init__`.
- **Do NOT remove** `ZmqTelemetrySource` import — still needed for `__init__`.
- `_install_flow`, `add_flow`, `switch_features_handler`, `packet_in_handler`
  remain untouched.
- **Per-file divergences** (must NOT be merged): `_lan_id` default is `"lan1"`
  in main_n1.py and `"lan2"` in main_n2.py; logger name is `'os_ken.main_n1'`
  vs `'os_ken.main_n2'`.
- **Mutable sets by reference:** The mediator passes `self._local_storage_macs_n1`
  and `self._local_storage_macs_n2` (from TopologyMixin) to
  `promote_storage_from_telemetry`. These are the live mutable sets — mutations
  from `add_storage_mac` in step 2 are visible in step 4 within the same
  callback invocation. This matches the original code’s behaviour and is
  intentional (the fallback check sees up-to-date membership).

---

## Relevant files

| File | Action |
|------|--------|
| `source/sdn_controller/scaling_config.py` | **NEW** ~65 lines. Env-var constants. |
| `source/sdn_controller/scaling_policy.py` | **NEW** ~200 lines. ScalingPolicy (Strategy). |
| `source/sdn_controller/node_registry.py` | **NEW** ~120 lines. DynamicNodeRegistry (Registry). |
| `source/sdn_controller/control_events.py` | **NEW** ~100 lines. ControlEventDispatcher. |
| `source/sdn_controller/main_n1.py` | Remove ~400 lines. Add 3 imports + 3 object constructions + mediator method. |
| `source/sdn_controller/main_n2.py` | Same as main_n1.py. |
| `source/sdn_controller/elasticity/elasticity.py` | Reference only (alert types, ElasticityManager API). |
| `source/sdn_controller/elasticity/node_common.py` | Reference only (NodeInfo). |
| `source/sdn_controller/telemetry/models.py` | Reference only (TelemetrySummary, DomainSummary). |
| `source/sdn_controller/vip_routing.py` | Reference only (update_server_stats, update_storage_stats). |
| `source/sdn_controller/topology/topology.py` | Reference only (add_storage_mac, _local_storage_macs_*). |

## Verification

1. Import checks: `from source.sdn_controller.scaling_config import _SCALE_UP_SCORE_THRESHOLD`
2. Import checks: `from source.sdn_controller.scaling_policy import ScalingPolicy`
3. Import checks: `from source.sdn_controller.node_registry import DynamicNodeRegistry`
4. Import checks: `from source.sdn_controller.control_events import ControlEventDispatcher`
5. Full class resolution: import `KenLearnAndLog` from both main modules
6. Grep both main files: no leftover `_evaluate_scale`, `_degradation_score`,
   `_detect_absent`, `_sync_node_tracking`, `_process_drain`,
   `_process_secondary`, `_promote_storage`, `_find_last_dynamic`,
   `_submit_scale_down_alert`, `_count_dynamic_storage_nodes`,
   `_evaluate_storage_scale_up` methods
7. Grep `scaling_policy.py`: no `self._elasticity`, no `self.add_storage_mac`
   (policy has no external dependencies)
8. Grep `node_registry.py`: no `self.add_storage_mac`, no `self._elasticity`
   stored as attribute (elasticity passed as argument to `sync()`)
9. Grep `control_events.py`: no stored references (all deps passed as args)
10. Confirm `_REQUIRED_APP` is still present in both main_n1.py and main_n2.py
